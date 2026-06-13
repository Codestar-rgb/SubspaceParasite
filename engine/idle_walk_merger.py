#!/usr/bin/env python3
"""
Super Architecture — Idle-Walk Animation Merger
================================================

Merge idle animation data INTO walk animations to simulate GeckoLib's
animation layering behavior.

PROBLEM:
  The SRP (Scape and Run Parasites) mod uses GeckoLib animation LAYERING:
  - idle animation: arm/tentacle/hair/tail sway (always playing)
  - walk animation: leg rotation + body bob (plays ON TOP of idle when walking)

  In Blockbench .bbmodel format, animations are standalone (no layering).
  This means converted walk animations are MISSING the arm/body sway that
  makes them look complete. The walk only moves legs, making it look like
  "slight foot lifts" rather than a full walk cycle.

SOLUTION:
  For each walk animation, find the matching idle animation and merge idle
  data into it:

  1. Bones ONLY in idle (not in walk): add their full animation from idle,
     sampled at regular time points matching the walk timeline.
  2. Bones in BOTH walk and idle: walk values take priority for channels/axes
     where walk has meaningful data. For channels/axes where walk has no
     meaningful data (constant/zero values from carry-forward), use idle values.
  3. Channels only in idle: add them to walk (sampled at walk time points).
  4. Ensure loop closure: first frame = last frame for seamless cycling.
  5. Handle timeline alignment: sample idle cyclically when walk is longer
     than idle (t % idle_length).

PIPELINE POSITION:
  After carry_forward, BEFORE walk_enhancer.

  carry_forward fills missing axes via interpolation (marking them explicit=True).
  This module then distinguishes "meaningful" walk data from carry-forward
  defaults using an axis-range heuristic: axes whose values vary by less than
  AXIS_RANGE_THRESHOLD across all keyframes are treated as "walk has no data"
  and replaced with idle values.

ALGORITHM:
  For each walk animation:
    1. Find the matching idle animation (same model prefix, name with "idle")
    2. For idle-only bones: sample idle at walk's time grid, add to walk
    3. For shared bones: merge at axis level
       - Axes with meaningful walk variation: keep walk values (walk priority)
       - Axes with no walk variation: replace with idle-sampled values
       - Channels only in idle: add wholesale from idle
    4. Ensure loop closure on all merged bones (first frame = last frame)
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

from core.types import (
    AXES,
    CHANNELS,
    AnimationIR,
    AxisValue,
    BoneAnimationIR,
    KeyframeData,
)
from engine.catmullrom_baker import _get_catmullrom_value

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Sampling interval for idle-only bones (seconds).
# Produces ~10 samples/sec which captures idle sway patterns well.
# The CatmullRom baker will further densify these if needed.
IDLE_SAMPLE_INTERVAL: float = 0.1

# Minimum value range (degrees for rotation, units for position/scale) for an
# axis to be considered "meaningful" in the walk animation. Axes with range
# below this threshold are treated as carry-forward defaults and replaced
# with idle-sampled values.
#
# After carry_forward, axes that had NO original data are constant (all 0.0
# or all carry-forward value), so their range is 0. Axes with original data
# have interpolated values with real variation. A threshold of 0.5 safely
# separates the two cases.
AXIS_RANGE_THRESHOLD: float = 0.5


# ---------------------------------------------------------------------------
# Idle-Walk pairing
# ---------------------------------------------------------------------------

def _find_idle_for_animation(
    target_anim: AnimationIR,
    all_animations: List[AnimationIR],
) -> Optional[AnimationIR]:
    """Find the idle animation that corresponds to a locomotion animation.

    Matching strategy (tried in order):
      1. Replace the animation type keyword with "idle" in the name (exact match).
      2. Look for any idle animation sharing the same model prefix
         (the part before the type keyword).
      3. If there's exactly one idle animation, use it as fallback.

    Args:
        target_anim: The target AnimationIR (walk/attack/fly).
        all_animations: All animations for this model.

    Returns:
        The matching idle AnimationIR, or None if not found.
    """
    target_name_lower = target_anim.name.lower()

    # Strategy 1: Replace keyword with "idle"
    for keyword in ("walk", "attack", "fly"):
        idle_candidate = target_name_lower.replace(keyword, "idle")
        for anim in all_animations:
            if anim.name.lower() == idle_candidate:
                return anim

    # Strategy 2: Same model prefix
    # "animation.kirin.walk" → prefix "animation.kirin"
    prefix: Optional[str] = None
    for sep in [".walk", "_walk", "walk", ".attack", "_attack", "attack", ".fly", "_fly", "fly"]:
        idx = target_name_lower.rfind(sep)
        if idx > 0:
            prefix = target_name_lower[:idx]
            break

    if prefix:
        for anim in all_animations:
            anim_lower = anim.name.lower()
            if "idle" in anim_lower and anim_lower.startswith(prefix):
                return anim

    # Strategy 3: Single idle animation fallback
    idle_anims = [a for a in all_animations if "idle" in a.name.lower()]
    if len(idle_anims) == 1:
        return idle_anims[0]

    return None


# ---------------------------------------------------------------------------
# Axis-level analysis
# ---------------------------------------------------------------------------

def _get_axis_range(
    keyframes: List[KeyframeData],
    channel: str,
    axis: str,
) -> float:
    """Compute the value range (max - min) for a specific axis in a channel.

    Args:
        keyframes: List of keyframes for a bone.
        channel: Channel name ("rotation", "position", "scale").
        axis: Axis name ("x", "y", "z").

    Returns:
        Range of values, or 0.0 if no data.
    """
    vals = []
    for kf in keyframes:
        if kf.channel == channel:
            av = getattr(kf, axis)
            if av.explicit:
                vals.append(av.value)

    if not vals:
        return 0.0
    return max(vals) - min(vals)


def _get_walk_owned_axes(
    walk_bone: BoneAnimationIR,
    channel: str,
) -> Set[str]:
    """Determine which axes in a channel the walk animation "owns".

    An axis is "walk-owned" if it has meaningful variation (range > threshold).
    After carry-forward, axes with no original data are constant (all 0.0 or
    a single carry-forward value), yielding zero or near-zero range. Axes with
    original walk data have real variation from interpolation.

    Args:
        walk_bone: Walk animation's bone data.
        channel: Channel name.

    Returns:
        Set of axis names ("x", "y", "z") that walk owns.
    """
    owned: Set[str] = set()
    for axis in AXES:
        rng = _get_axis_range(walk_bone.keyframes, channel, axis)
        if rng > AXIS_RANGE_THRESHOLD:
            owned.add(axis)
    return owned


# ---------------------------------------------------------------------------
# Idle sampling
# ---------------------------------------------------------------------------

def _sample_idle_channel_at_time(
    idle_bone: BoneAnimationIR,
    channel: str,
    t: float,
    idle_length: float,
) -> Dict[str, float]:
    """Sample idle animation values for one channel at a specific time.

    Evaluates the idle animation's per-axis curves at time *t*.
    Since idle loops, uses ``t % idle_length`` for cyclic sampling when
    *t* exceeds the idle animation's length.

    Uses CatmullRom evaluation (via ``_get_catmullrom_value``) which
    correctly handles both CatmullRom and linear interpolation (linear
    is a degenerate case of CatmullRom with 2 control points).

    Args:
        idle_bone: Idle animation's bone data.
        channel: Channel name.
        t: Time to sample at (in walk animation's timeline).
        idle_length: Length of the idle animation for cyclic wrapping.

    Returns:
        Dict mapping axis name ("x"/"y"/"z") → sampled value.
    """
    # Cyclic wrapping for timeline alignment
    if idle_length > 0:
        t_wrapped = t % idle_length
    else:
        t_wrapped = t

    result: Dict[str, float] = {}
    for axis in AXES:
        # Build per-axis time series from idle keyframes
        times: List[float] = []
        values: List[float] = []
        for kf in idle_bone.keyframes:
            if kf.channel == channel:
                av = getattr(kf, axis)
                if av.explicit:
                    times.append(kf.time)
                    values.append(av.value)

        if times:
            result[axis] = _get_catmullrom_value(t_wrapped, times, values)
        else:
            result[axis] = 0.0

    return result


def _collect_walk_time_points(
    walk_anim: AnimationIR,
) -> List[float]:
    """Collect all unique time points from a walk animation.

    These are the times at which we need to evaluate idle data for
    axis-level merging on shared bones.

    Args:
        walk_anim: The walk AnimationIR.

    Returns:
        Sorted list of unique time points.
    """
    times: Set[float] = set()
    for bone_anim in walk_anim.bones.values():
        for kf in bone_anim.keyframes:
            times.add(round(kf.time, 8))

    return sorted(times)


def _generate_idle_sample_times(
    walk_length: float,
) -> List[float]:
    """Generate regular time points for sampling idle-only bones.

    Uses ``IDLE_SAMPLE_INTERVAL`` for density, ensuring *t* = 0 and
    *t* = ``walk_length`` are always included for loop closure.

    Args:
        walk_length: Length of the walk animation in seconds.

    Returns:
        Sorted list of unique time points.
    """
    if walk_length <= 0:
        return [0.0]

    times: List[float] = [0.0]
    t = IDLE_SAMPLE_INTERVAL
    while t < walk_length - 1e-9:
        times.append(round(t, 8))
        t += IDLE_SAMPLE_INTERVAL

    # Always include the end for loop closure
    end = round(walk_length, 8)
    if abs(end - times[-1]) > 1e-9:
        times.append(end)

    return sorted(set(times))


# ---------------------------------------------------------------------------
# Merge logic
# ---------------------------------------------------------------------------

def _merge_walk_bone_with_idle(
    walk_bone: BoneAnimationIR,
    idle_bone: BoneAnimationIR,
    idle_length: float,
    walk_length: float,
) -> BoneAnimationIR:
    """Merge a bone that exists in both walk and idle animations.

    For each channel:
      - Axes where walk has meaningful variation: keep walk values
      - Axes where walk has no variation (carry-forward defaults): use idle values
      - Channels only in idle: add from idle (sampled at regular intervals)

    Args:
        walk_bone: Walk animation's bone data.
        idle_bone: Idle animation's bone data.
        idle_length: Length of the idle animation.
        walk_length: Length of the walk animation.

    Returns:
        New BoneAnimationIR with merged data.
    """
    # Determine which channels each animation has
    walk_channels: Set[str] = set()
    for kf in walk_bone.keyframes:
        walk_channels.add(kf.channel)

    idle_channels: Set[str] = set()
    for kf in idle_bone.keyframes:
        idle_channels.add(kf.channel)

    new_keyframes: List[KeyframeData] = []

    # --- Process channels that walk already has ---
    for channel in CHANNELS:
        if channel not in walk_channels:
            continue

        walk_owned = _get_walk_owned_axes(walk_bone, channel)
        idle_has_channel = channel in idle_channels

        # Check if axis-level merge is needed (idle has data, walk doesn't
        # own all axes)
        needs_idle_fill = idle_has_channel and (walk_owned != set(AXES))

        if needs_idle_fill:
            # Axis-level merge: re-key walk keyframes, filling non-owned
            # axes with idle-sampled values
            walk_kfs = sorted(
                [kf for kf in walk_bone.keyframes if kf.channel == channel],
                key=lambda kf: kf.time,
            )

            for kf in walk_kfs:
                vals: Dict[str, float] = {}
                for axis in AXES:
                    if axis in walk_owned:
                        # Walk owns this axis — use walk value
                        vals[axis] = getattr(kf, axis).value
                    else:
                        # Walk doesn't own this axis — sample from idle
                        idle_vals = _sample_idle_channel_at_time(
                            idle_bone, channel, kf.time, idle_length,
                        )
                        vals[axis] = idle_vals[axis]

                new_kf = KeyframeData(
                    time=kf.time,
                    channel=channel,
                    x=AxisValue.explicit_val(vals["x"]),
                    y=AxisValue.explicit_val(vals["y"]),
                    z=AxisValue.explicit_val(vals["z"]),
                    easing=kf.easing,
                    interpolation=kf.interpolation,
                )
                new_keyframes.append(new_kf)
        else:
            # Walk owns all axes or idle doesn't have this channel.
            # Keep walk keyframes unchanged.
            for kf in walk_bone.keyframes:
                if kf.channel == channel:
                    new_keyframes.append(kf)

    # --- Process channels only in idle (not in walk) ---
    idle_only_channels = idle_channels - walk_channels
    if idle_only_channels:
        time_points = _generate_idle_sample_times(walk_length)
        for channel in idle_only_channels:
            for t in time_points:
                idle_vals = _sample_idle_channel_at_time(
                    idle_bone, channel, t, idle_length,
                )
                new_kf = KeyframeData(
                    time=t,
                    channel=channel,
                    x=AxisValue.explicit_val(idle_vals["x"]),
                    y=AxisValue.explicit_val(idle_vals["y"]),
                    z=AxisValue.explicit_val(idle_vals["z"]),
                    easing="linear",
                    interpolation="catmullrom",
                )
                new_keyframes.append(new_kf)

    # Sort by time, then channel
    new_keyframes.sort(key=lambda kf: (kf.time, kf.channel))

    return BoneAnimationIR(
        bone_name=walk_bone.bone_name,
        keyframes=new_keyframes,
    )


def _create_idle_bone_for_walk(
    idle_bone: BoneAnimationIR,
    walk_length: float,
    idle_length: float,
) -> BoneAnimationIR:
    """Create a bone's animation data from idle for inclusion in walk.

    Used for bones that are ONLY in idle (not in walk). Samples the idle
    animation at regular time points covering walk's duration, producing
    keyframes that replicate the idle sway within the walk timeline.

    Args:
        idle_bone: Idle animation's bone data.
        walk_length: Length of the walk animation.
        idle_length: Length of the idle animation.

    Returns:
        New BoneAnimationIR with sampled idle data.
    """
    time_points = _generate_idle_sample_times(walk_length)

    # Determine which channels idle has
    idle_channels: Set[str] = set()
    for kf in idle_bone.keyframes:
        idle_channels.add(kf.channel)

    new_keyframes: List[KeyframeData] = []

    for channel in CHANNELS:
        if channel not in idle_channels:
            continue

        for t in time_points:
            idle_vals = _sample_idle_channel_at_time(
                idle_bone, channel, t, idle_length,
            )
            new_kf = KeyframeData(
                time=t,
                channel=channel,
                x=AxisValue.explicit_val(idle_vals["x"]),
                y=AxisValue.explicit_val(idle_vals["y"]),
                z=AxisValue.explicit_val(idle_vals["z"]),
                easing="linear",
                interpolation="catmullrom",
            )
            new_keyframes.append(new_kf)

    # Sort by time, then channel
    new_keyframes.sort(key=lambda kf: (kf.time, kf.channel))

    return BoneAnimationIR(
        bone_name=idle_bone.bone_name,
        keyframes=new_keyframes,
    )


# ---------------------------------------------------------------------------
# Loop closure
# ---------------------------------------------------------------------------

def _ensure_loop_closure(
    bone_anim: BoneAnimationIR,
    anim_length: float,
) -> BoneAnimationIR:
    """Ensure the first and last keyframes of each channel have matching values.

    For looping animations, the value at *t* = 0 must equal the value at
    *t* = ``anim_length`` to avoid a visible discontinuity at the loop
    boundary.

    Strategy: if the last keyframe is at (or very near) ``anim_length`` and
    its values differ from the first keyframe, overwrite the last keyframe's
    axis values with the first keyframe's values.

    Args:
        bone_anim: The bone animation to fix.
        anim_length: Animation length in seconds.

    Returns:
        New BoneAnimationIR with loop-closed keyframes.
    """
    if not bone_anim.keyframes:
        return bone_anim

    # Group by channel
    channel_kfs: Dict[str, List[KeyframeData]] = {}
    for kf in bone_anim.keyframes:
        if kf.channel not in channel_kfs:
            channel_kfs[kf.channel] = []
        channel_kfs[kf.channel].append(kf)

    new_keyframes: List[KeyframeData] = []

    for channel in CHANNELS:
        kfs = channel_kfs.get(channel, [])
        if not kfs:
            continue

        kfs_sorted = sorted(kfs, key=lambda kf: kf.time)
        first_kf = kfs_sorted[0]
        last_kf = kfs_sorted[-1]

        # Check if first and last values match
        needs_fix = False
        for axis in AXES:
            first_val = getattr(first_kf, axis).value
            last_val = getattr(last_kf, axis).value
            if abs(first_val - last_val) > 0.01:
                needs_fix = True
                break

        if needs_fix and abs(last_kf.time - anim_length) < 0.05:
            # Replace last keyframe with first keyframe's values to close the loop
            fixed_last = KeyframeData(
                time=last_kf.time,
                channel=channel,
                x=AxisValue.explicit_val(first_kf.x.value),
                y=AxisValue.explicit_val(first_kf.y.value),
                z=AxisValue.explicit_val(first_kf.z.value),
                easing=last_kf.easing,
                interpolation=last_kf.interpolation,
            )
            new_keyframes.extend(kfs_sorted[:-1])
            new_keyframes.append(fixed_last)
        else:
            new_keyframes.extend(kfs_sorted)

    # Sort by time, then channel
    new_keyframes.sort(key=lambda kf: (kf.time, kf.channel))

    return BoneAnimationIR(
        bone_name=bone_anim.bone_name,
        keyframes=new_keyframes,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def merge_idle_into_walk(
    animations: List[AnimationIR],
    model_name: str = "",
) -> List[AnimationIR]:
    """Merge idle animation data into locomotion animations (walk/attack/fly).

    For each walk/attack/fly animation in the list:
      1. Find the matching idle animation (same model prefix, name with "idle")
      2. For bones ONLY in idle: sample their animation at walk's time grid
         and add them to the walk animation
      3. For bones in BOTH: merge at axis level
         - Axes with meaningful walk variation: keep walk values (walk priority)
         - Axes with no walk variation: replace with idle-sampled values
         - Channels only in idle: add wholesale from idle
      4. Ensure loop closure on all merged bones (first frame = last frame)

    This simulates GeckoLib's animation layering where idle always plays
    and walk overlays on top when the entity is moving.

    Should be called AFTER carry_forward but BEFORE walk_enhancer in the
    pipeline, so that:
      - carry_forward has filled all axes (allowing range-based heuristic)
      - walk_enhancer sees the merged animation (can enhance legs correctly)

    Args:
        animations: List of AnimationIR instances.
        model_name: Model name for logging.

    Returns:
        New list of AnimationIR with idle data merged into walk animations.
        Non-walk animations are returned unchanged.
    """
    if not animations:
        return animations

    # Quick check: any locomotion or idle animations at all?
    loco_anims = [a for a in animations
                  if any(k in a.name.lower() for k in ("walk", "attack", "fly"))]
    idle_anims = [a for a in animations if "idle" in a.name.lower()]

    if not loco_anims or not idle_anims:
        logger.debug(
            "[%s] IdleWalkMerger: no locomotion/idle pair found "
            "(%d loco, %d idle)",
            model_name, len(loco_anims), len(idle_anims),
        )
        return animations

    result: List[AnimationIR] = []
    merged_count = 0
    total_bones_added = 0
    total_axes_merged = 0

    for anim in animations:
        # Process locomotion/action animations that layer on top of idle.
        # In SRP's GeckoLib setup, idle (arm/tentacle sway) always plays,
        # and walk/attack/fly overlay on top. We merge idle into these
        # so the converted animations are self-contained.
        anim_name_lower = anim.name.lower()
        is_locomotion = any(
            keyword in anim_name_lower
            for keyword in ("walk", "attack", "fly")
        )
        if not is_locomotion:
            result.append(anim)
            continue

        # Find matching idle animation
        idle_anim = _find_idle_for_animation(anim, animations)
        if idle_anim is None:
            logger.debug(
                "[%s] IdleWalkMerger: no matching idle for '%s'",
                model_name, anim.name,
            )
            result.append(anim)
            continue

        if not idle_anim.bones:
            logger.debug(
                "[%s] IdleWalkMerger: idle '%s' has no bones, skipping",
                model_name, idle_anim.name,
            )
            result.append(anim)
            continue

        # ---- Merge idle into this walk animation ----
        new_bones: Dict[str, BoneAnimationIR] = {}
        walk_bone_names = set(anim.bones.keys())
        idle_bone_names = set(idle_anim.bones.keys())

        bones_added = 0
        axes_merged = 0

        # Process bones that exist in walk
        for bone_name, walk_bone in anim.bones.items():
            if bone_name in idle_bone_names:
                # Bone is in both: merge at axis level
                idle_bone = idle_anim.bones[bone_name]
                merged_bone = _merge_walk_bone_with_idle(
                    walk_bone,
                    idle_bone,
                    idle_length=idle_anim.length,
                    walk_length=anim.length,
                )
                new_bones[bone_name] = merged_bone
                axes_merged += 1
            else:
                # Bone only in walk: keep unchanged
                new_bones[bone_name] = walk_bone

        # Process bones only in idle (not in walk) — these are the key
        # additions: arm/tentacle/hair/tail sway that makes the walk
        # animation look complete.
        idle_only_bones = idle_bone_names - walk_bone_names
        for bone_name in idle_only_bones:
            idle_bone = idle_anim.bones[bone_name]
            sampled_bone = _create_idle_bone_for_walk(
                idle_bone,
                walk_length=anim.length,
                idle_length=idle_anim.length,
            )
            new_bones[bone_name] = sampled_bone
            bones_added += 1

        # Ensure loop closure on all bones (for looping animations)
        is_loop = anim.loop == "loop"
        if is_loop:
            closed_bones: Dict[str, BoneAnimationIR] = {}
            for bone_name, bone_anim in new_bones.items():
                closed_bones[bone_name] = _ensure_loop_closure(
                    bone_anim, anim.length,
                )
            new_bones = closed_bones

        # Create new walk animation with merged data
        merged_anim = AnimationIR(
            name=anim.name,
            loop=anim.loop,
            length=anim.length,
            bones=new_bones,
            period=anim.period,
        )
        result.append(merged_anim)
        merged_count += 1
        total_bones_added += bones_added
        total_axes_merged += axes_merged

        logger.debug(
            "[%s] IdleWalkMerger: merged '%s' ← '%s' "
            "(%d idle bones added, %d shared bones axis-merged)",
            model_name, anim.name, idle_anim.name,
            bones_added, axes_merged,
        )

    if merged_count > 0:
        logger.info(
            "[%s] IdleWalkMerger: merged idle into %d walk animations "
            "(%d idle bones added, %d shared bones axis-merged)",
            model_name, merged_count, total_bones_added, total_axes_merged,
        )

    return result
