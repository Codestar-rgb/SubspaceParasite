#!/usr/bin/env python3
"""
Super Architecture — Sub-frame Keyframe Insertion
===================================================

Insert intermediate keyframes at uniform intervals for smooth animation playback.

PROBLEM: Some source animations have very few keyframes with large time gaps
(e.g., 1+ seconds between keyframes). When Blockbench renders these with
CatmullRom interpolation, the sparse control points can cause:
  - Overshoot (values going beyond the intended range)
  - Undershoot (values not reaching the intended range)
  - Irregular speed (fast in some areas, slow in others)

SOLUTION: Insert intermediate keyframes at regular intervals (e.g., every
1/24 second = one frame at 24 fps). This ensures that:
  - The interpolation curve is densely sampled
  - Overshoot is minimized (more control points constrain the curve)
  - Playback speed is uniform

The insertion is aware of the animation's interpolation mode:
  - For catmullrom segments: evaluate the Catmull-Rom spline at sub-frame times
  - For linear segments: evaluate linear interpolation at sub-frame times

This stage runs AFTER carry-forward and loop alignment, so all axes are
already filled at every keyframe time point.

All transforms produce new data — input is never mutated.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from core.types import (
    AXES,
    CHANNELS,
    AnimationIR,
    AxisValue,
    BoneAnimationIR,
    KeyframeData,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

# Target frame interval for sub-frame insertion (seconds).
# 1/24 ≈ 0.0417 seconds per frame at 24 fps (Blockbench default).
# We use 1/20 = 0.05 for a good balance between smoothness and file size.
TARGET_FRAME_INTERVAL: float = 1.0 / 20.0

# Minimum time gap between keyframes to trigger sub-frame insertion.
# Gaps smaller than this are already dense enough.
MIN_GAP_FOR_INSERTION: float = 2.0 * TARGET_FRAME_INTERVAL

# Maximum number of sub-frames to insert in a single gap.
# This prevents extremely dense output for very long animations.
MAX_SUBFRAMES_PER_GAP: int = 50


# ---------------------------------------------------------------------------
# Catmull-Rom evaluation for sub-frame insertion
# ---------------------------------------------------------------------------

def _catmull_rom_eval(
    s: float,
    v0: float, v1: float, v2: float, v3: float,
) -> float:
    """Evaluate Catmull-Rom spline at parameter s ∈ [0, 1].

    Args:
        s: Parameter in [0, 1] (0 = v1, 1 = v2).
        v0: Previous control point value.
        v1: Start value.
        v2: End value.
        v3: Next control point value.

    Returns:
        Interpolated value at parameter s.
    """
    s2 = s * s
    s3 = s2 * s

    c0 = 2.0 * v1
    c1 = -v0 + v2
    c2 = 2.0 * v0 - 5.0 * v1 + 4.0 * v2 - v3
    c3 = -v0 + 3.0 * v1 - 3.0 * v2 + v3

    return 0.5 * (c0 + c1 * s + c2 * s2 + c3 * s3)


def _interpolate_keyframe_values(
    s: float,
    kf1: KeyframeData,
    kf2: KeyframeData,
    kf_prev: Optional[KeyframeData],
    kf_next: Optional[KeyframeData],
    interpolation: str,
) -> Tuple[float, float, float]:
    """Interpolate axis values at parameter s between kf1 and kf2.

    Args:
        s: Parameter in [0, 1] (0 = kf1, 1 = kf2).
        kf1: Start keyframe.
        kf2: End keyframe.
        kf_prev: Previous keyframe (for CatmullRom), or None.
        kf_next: Next keyframe (for CatmullRom), or None.
        interpolation: "catmullrom" or "linear".

    Returns:
        Tuple (x, y, z) of interpolated values.
    """
    if interpolation == "catmullrom":
        # CatmullRom interpolation per axis
        results = []
        for axis in AXES:
            v1 = getattr(kf1, axis).value
            v2 = getattr(kf2, axis).value

            # Previous control point
            if kf_prev is not None:
                v0 = getattr(kf_prev, axis).value
            else:
                v0 = 2.0 * v1 - v2  # Linear extrapolation

            # Next control point
            if kf_next is not None:
                v3 = getattr(kf_next, axis).value
            else:
                v3 = 2.0 * v2 - v1  # Linear extrapolation

            results.append(_catmull_rom_eval(s, v0, v1, v2, v3))

        return (results[0], results[1], results[2])
    else:
        # Linear interpolation
        x = kf1.x.value + s * (kf2.x.value - kf1.x.value)
        y = kf1.y.value + s * (kf2.y.value - kf1.y.value)
        z = kf1.z.value + s * (kf2.z.value - kf1.z.value)
        return (x, y, z)


# ---------------------------------------------------------------------------
# Per-channel sub-frame insertion
# ---------------------------------------------------------------------------

def _insert_subframes_channel(
    keyframes: List[KeyframeData],
    channel: str,
    anim_length: float,
    bone_name: str,
    anim_name: str,
    model_name: str,
    stats: dict,
) -> List[KeyframeData]:
    """Insert sub-frame keyframes for one channel.

    For each segment between consecutive keyframes:
      1. If the time gap is large enough, insert intermediate keyframes
      2. Use the same interpolation mode as the segment
      3. Evaluate the interpolation curve at each sub-frame time

    Args:
        keyframes: All keyframes for this bone (sorted by time).
        channel: The channel to process.
        anim_length: Animation length in seconds.
        bone_name: Bone name for logging.
        anim_name: Animation name for logging.
        model_name: Model name for logging.
        stats: Dict to update with insertion statistics.

    Returns:
        New list of keyframes with sub-frames inserted.
    """
    # Filter to keyframes for this channel
    channel_kfs = [kf for kf in keyframes if kf.channel == channel]

    if len(channel_kfs) < 2:
        return list(keyframes)

    # Build index for quick lookup of prev/next keyframes
    kf_list = channel_kfs  # Already sorted by time from input

    result_kfs: List[KeyframeData] = []
    subframes_inserted = 0

    for i in range(len(kf_list)):
        kf = kf_list[i]

        # Add the original keyframe
        result_kfs.append(kf)

        # Check if we need to insert sub-frames after this keyframe
        if i >= len(kf_list) - 1:
            continue

        next_kf = kf_list[i + 1]
        dt = next_kf.time - kf.time

        if dt < MIN_GAP_FOR_INSERTION:
            continue

        # Determine how many sub-frames to insert
        num_subframes = int(dt / TARGET_FRAME_INTERVAL) - 1
        num_subframes = min(num_subframes, MAX_SUBFRAMES_PER_GAP)

        if num_subframes <= 0:
            continue

        # Get prev/next keyframes for CatmullRom boundary conditions
        kf_prev = kf_list[i - 1] if i > 0 else None
        kf_next = kf_list[i + 2] if i + 2 < len(kf_list) else None

        # Use the interpolation mode of the end keyframe
        # (Blockbench applies interpolation from the current keyframe to the next)
        interpolation = next_kf.interpolation

        # Insert sub-frames
        for j in range(1, num_subframes + 1):
            s = j / (num_subframes + 1)
            t = kf.time + s * dt

            # Skip if too close to an existing keyframe
            if abs(t - next_kf.time) < 1e-6:
                continue

            # Interpolate values
            x_val, y_val, z_val = _interpolate_keyframe_values(
                s, kf, next_kf, kf_prev, kf_next, interpolation,
            )

            # Create sub-frame keyframe
            sub_kf = KeyframeData(
                time=t,
                channel=channel,
                x=AxisValue.explicit_val(x_val),
                y=AxisValue.explicit_val(y_val),
                z=AxisValue.explicit_val(z_val),
                easing=kf.easing,
                interpolation=interpolation,
                is_molang=False,
            )
            result_kfs.append(sub_kf)
            subframes_inserted += 1

    # Add keyframes from other channels unchanged
    other_kfs = [kf for kf in keyframes if kf.channel != channel]

    combined = result_kfs + other_kfs
    combined.sort(key=lambda k: (k.time, k.channel))

    stats["subframes_inserted"] = stats.get("subframes_inserted", 0) + subframes_inserted

    return combined


# ---------------------------------------------------------------------------
# Per-bone sub-frame insertion
# ---------------------------------------------------------------------------

def _insert_subframes_bone(
    bone_anim: BoneAnimationIR,
    anim_length: float,
    anim_name: str,
    model_name: str,
    stats: dict,
) -> BoneAnimationIR:
    """Insert sub-frame keyframes for all channels of one bone.

    Args:
        bone_anim: The bone's animation data.
        anim_length: Animation length in seconds.
        anim_name: Animation name for logging.
        model_name: Model name for logging.
        stats: Dict to update with insertion statistics.

    Returns:
        New BoneAnimationIR with sub-frames inserted.
    """
    if not bone_anim.keyframes:
        return bone_anim

    keyframes = bone_anim.keyframes

    # Process rotation channels (most important for smooth animation)
    for channel in ["rotation"]:
        channel_kfs = [kf for kf in keyframes if kf.channel == channel]
        if len(channel_kfs) >= 2:
            keyframes = _insert_subframes_channel(
                keyframes, channel, anim_length,
                bone_anim.bone_name, anim_name, model_name, stats,
            )

    return BoneAnimationIR(
        bone_name=bone_anim.bone_name,
        keyframes=keyframes,
    )


# ---------------------------------------------------------------------------
# Main sub-frame insertion function
# ---------------------------------------------------------------------------

def insert_subframes(
    animations: Dict[str, AnimationIR],
    model_name: str = "",
    stats: dict = None,
) -> Dict[str, AnimationIR]:
    """Insert sub-frame keyframes for smooth animation playback.

    For each animation, for each bone's rotation channel, insert intermediate
    keyframes at regular intervals where there are large time gaps.

    Args:
        animations: Dict mapping animation_name -> AnimationIR.
        model_name: Optional model name for logging context.
        stats: Optional dict to update with insertion statistics.

    Returns:
        New dict of animations with sub-frames inserted.
    """
    if stats is None:
        stats = {}

    stats.setdefault("subframes_inserted", 0)

    result: Dict[str, AnimationIR] = {}

    for anim_name, anim in animations.items():
        anim_length = anim.length
        if anim_length <= 0:
            # Compute from keyframe times
            all_times: List[float] = []
            for bone_anim in anim.bones.values():
                for kf in bone_anim.keyframes:
                    all_times.append(kf.time)
            if all_times:
                anim_length = max(all_times)

        new_bones: Dict[str, BoneAnimationIR] = {}

        for bone_name, bone_anim in anim.bones.items():
            try:
                new_bone = _insert_subframes_bone(
                    bone_anim, anim_length,
                    anim_name, model_name, stats,
                )
                new_bones[bone_name] = new_bone
            except Exception as e:
                logger.warning(
                    "[%s] Sub-frame insertion error for %s/%s: %s, "
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
