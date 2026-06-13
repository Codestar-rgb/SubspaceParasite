#!/usr/bin/env python3
"""
Super Architecture — Adaptive Interpolation Selection (Fixed)
===============================================================

Select interpolation mode for each keyframe, with proper handling of
large time gaps and per-segment analysis.

CRITICAL FIX: The previous implementation applied a single interpolation
mode to an entire channel based on global analysis. This was wrong because:
  1. A channel might have both smooth segments (good for CatmullRom) and
     large-gap segments (where CatmullRom overshoots).
  2. The snap-heavy detection used a global 50% threshold, which could
     misclassify channels.

New approach:
  - For rotation channels: use CatmullRom by default
  - BUT: for individual segments with large time gaps (> 0.5 seconds)
    and small value changes, switch to linear to avoid overshoot
  - For position/scale channels: use linear by default
  - If easing is non-linear, always use CatmullRom

All transforms produce new data — input is never mutated.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.types import (
    AXES,
    CHANNELS,
    DEFAULT_INTERPOLATION,
    AnimationIR,
    AxisValue,
    BoneAnimationIR,
    KeyframeData,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Interpolation selection parameters
# ---------------------------------------------------------------------------

# Time gap above which CatmullRom may overshoot for rotation channels.
# Segments longer than this with small value changes should use linear.
LARGE_GAP_THRESHOLD: float = 0.5  # seconds

# Maximum angular velocity (degrees per second) above which we keep CatmullRom
# even for large gaps (fast rotation is expected to be smooth).
HIGH_ANGULAR_VELOCITY: float = 60.0  # degrees per second

# Threshold for snap-heavy detection (degrees).
SNAP_THRESHOLD_DEGREES: float = 30.0

# Fraction of snaps required for a channel to be considered "snap-heavy."
SNAP_HEAVY_FRACTION: float = 0.5


def _compute_max_axis_delta(
    kf1: KeyframeData,
    kf2: KeyframeData,
) -> float:
    """Compute the maximum axis delta between two keyframes.

    Args:
        kf1: First keyframe.
        kf2: Second keyframe.

    Returns:
        Maximum absolute delta across all axes.
    """
    max_delta = 0.0
    for axis in AXES:
        v1 = getattr(kf1, axis).value
        v2 = getattr(kf2, axis).value
        delta = abs(v2 - v1)
        max_delta = max(max_delta, delta)
    return max_delta


def _is_snap_heavy_channel(
    keyframes: List[KeyframeData],
    channel: str,
) -> bool:
    """Determine if a channel is snap-heavy for interpolation override.

    A channel is "snap-heavy" if more than SNAP_HEAVY_FRACTION of
    consecutive keyframe pairs have a delta > SNAP_THRESHOLD_DEGREES
    on any axis.  This only applies to rotation channels.

    Args:
        keyframes: All keyframes for this bone (sorted by time).
        channel: The channel to check.

    Returns:
        True if the channel should use linear interpolation instead
        of catmullrom due to snap-heavy behavior.
    """
    if channel != "rotation":
        return False

    channel_kfs = [kf for kf in keyframes if kf.channel == channel]
    if len(channel_kfs) < 2:
        return False

    snap_count = 0
    total_checks = 0

    for i in range(1, len(channel_kfs)):
        prev = channel_kfs[i - 1]
        curr = channel_kfs[i]

        for axis in AXES:
            prev_val = getattr(prev, axis).value
            curr_val = getattr(curr, axis).value
            delta = abs(curr_val - prev_val)
            total_checks += 1
            if delta > SNAP_THRESHOLD_DEGREES:
                snap_count += 1

    if total_checks == 0:
        return False

    fraction = snap_count / total_checks
    return fraction > SNAP_HEAVY_FRACTION


def _select_segment_interpolation(
    prev_kf: Optional[KeyframeData],
    curr_kf: KeyframeData,
    channel: str,
    snap_heavy: bool,
) -> str:
    """Select interpolation mode for a specific keyframe segment.

    Per-segment logic:
      - If the segment has non-linear easing → catmullrom
      - If snap-heavy → linear
      - For rotation with large gaps but low angular velocity → linear
      - For rotation with large gaps but high angular velocity → catmullrom
      - Default: use channel default

    Args:
        prev_kf: Previous keyframe in this channel (None for first).
        curr_kf: Current keyframe.
        channel: Channel name.
        snap_heavy: Whether the channel is snap-heavy.

    Returns:
        Interpolation mode string ("catmullrom" or "linear").
    """
    # Non-linear easing always uses catmullrom
    if curr_kf.easing != "linear":
        return "catmullrom"

    # Snap-heavy channels use linear
    if snap_heavy:
        return "linear"

    # Default for position and scale
    if channel in ("position", "scale"):
        return DEFAULT_INTERPOLATION.get(channel, "linear")

    # For rotation channels, check segment-specific conditions
    if channel == "rotation" and prev_kf is not None:
        dt = curr_kf.time - prev_kf.time
        max_delta = _compute_max_axis_delta(prev_kf, curr_kf)

        if dt > LARGE_GAP_THRESHOLD:
            # Large gap — check angular velocity
            angular_velocity = max_delta / dt if dt > 0 else 0

            if angular_velocity < HIGH_ANGULAR_VELOCITY and max_delta < SNAP_THRESHOLD_DEGREES:
                # Large gap with small, slow changes → linear to avoid
                # CatmullRom overshoot artifacts
                return "linear"

            # Large gap with fast changes → keep catmullrom for smoothness
            return "catmullrom"

    # Default
    return DEFAULT_INTERPOLATION.get(channel, "linear")


# ---------------------------------------------------------------------------
# Per-bone interpolation selection
# ---------------------------------------------------------------------------

def _select_bone_interpolation(
    bone_anim: BoneAnimationIR,
    anim_name: str,
    model_name: str,
    stats: dict,
) -> BoneAnimationIR:
    """Select interpolation mode for each keyframe of one bone.

    Uses per-segment analysis for rotation channels to avoid CatmullRom
    overshoot on large time gaps.

    Args:
        bone_anim: The bone's animation data.
        anim_name: Animation name for logging.
        model_name: Model name for logging.
        stats: Dict to update with interpolation statistics.

    Returns:
        New BoneAnimationIR with updated interpolation modes.
    """
    if not bone_anim.keyframes:
        return bone_anim

    # Pre-compute snap-heavy status for each channel
    snap_heavy: Dict[str, bool] = {}
    for channel in CHANNELS:
        snap_heavy[channel] = _is_snap_heavy_channel(
            bone_anim.keyframes, channel
        )

    if snap_heavy.get("rotation", False):
        stats["snap_heavy_overrides"] = stats.get("snap_heavy_overrides", 0) + 1

    # Build per-channel previous keyframe lookup for segment analysis
    channel_prev: Dict[str, Optional[KeyframeData]] = {
        ch: None for ch in CHANNELS
    }

    # Select interpolation for each keyframe
    new_keyframes: List[KeyframeData] = []
    catmullrom_count = 0
    linear_count = 0

    # Process keyframes sorted by time, then channel
    sorted_kfs = sorted(bone_anim.keyframes, key=lambda kf: (kf.time, kf.channel))

    for kf in sorted_kfs:
        # Select interpolation for this segment
        interp = _select_segment_interpolation(
            channel_prev.get(kf.channel),
            kf,
            kf.channel,
            snap_heavy.get(kf.channel, False),
        )

        # Count
        if interp == "catmullrom":
            catmullrom_count += 1
        else:
            linear_count += 1

        # Update previous keyframe for this channel
        channel_prev[kf.channel] = kf

        # Create new keyframe with selected interpolation
        new_kf = KeyframeData(
            time=kf.time,
            channel=kf.channel,
            x=kf.x,
            y=kf.y,
            z=kf.z,
            easing=kf.easing,
            interpolation=interp,
            is_molang=kf.is_molang,
            molang_x=kf.molang_x,
            molang_y=kf.molang_y,
            molang_z=kf.molang_z,
        )
        new_keyframes.append(new_kf)

    stats["catmullrom_count"] = stats.get("catmullrom_count", 0) + catmullrom_count
    stats["linear_count"] = stats.get("linear_count", 0) + linear_count

    return BoneAnimationIR(
        bone_name=bone_anim.bone_name,
        keyframes=new_keyframes,
    )


# ---------------------------------------------------------------------------
# Main interpolation selection function
# ---------------------------------------------------------------------------

def select_interpolation(
    animations: Dict[str, AnimationIR],
    model_name: str = "",
    stats: dict = None,
) -> Dict[str, AnimationIR]:
    """Select interpolation mode for each keyframe with per-segment analysis.

    Rules:
    - Rotation: catmullrom by default, linear for large gaps with slow changes
    - Position: linear by default
    - Scale: linear by default
    - If easing is non-linear, always use catmullrom

    Args:
        animations: Dict mapping animation_name -> AnimationIR.
        model_name: Optional model name for logging context.
        stats: Optional dict to update with interpolation statistics.

    Returns:
        New dict of animations with interpolation modes selected.
    """
    if stats is None:
        stats = {}

    stats.setdefault("catmullrom_count", 0)
    stats.setdefault("linear_count", 0)
    stats.setdefault("snap_heavy_overrides", 0)

    result: Dict[str, AnimationIR] = {}

    for anim_name, anim in animations.items():
        new_bones: Dict[str, BoneAnimationIR] = {}

        for bone_name, bone_anim in anim.bones.items():
            try:
                new_bone = _select_bone_interpolation(
                    bone_anim, anim_name, model_name, stats,
                )
                new_bones[bone_name] = new_bone
            except Exception as e:
                logger.warning(
                    "[%s] Interpolation selection error for %s/%s: %s, "
                    "keeping original",
                    model_name, anim_name, bone_name, e,
                )
                new_bones[bone_name] = bone_anim

        result[anim_name] = AnimationIR(
            name=anim.name,
            loop=anim.loop,
            length=anim.length,
            bones=new_bones,
            period=anim.period,
        )

    return result
