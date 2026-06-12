#!/usr/bin/env python3
"""
Super Architecture — Adaptive Interpolation Selection
=======================================================

Select interpolation mode for each keyframe.

Rules:
  - Rotation: catmullrom by default (smooth curves match cos/sin sources)
    But if the channel is snap-heavy (>50% large jumps), use linear
  - Position: linear by default (crisp, predictable movements)
  - Scale: linear by default
  - If easing is non-linear, always use catmullrom

A channel is "snap-heavy" if more than 50% of consecutive keyframe
pairs have a delta > threshold degrees (default 30° for rotation).

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
# Snap-heavy detection
# ---------------------------------------------------------------------------

# Threshold for rotation snap detection (degrees).
# A delta larger than this between consecutive keyframes is a "snap."
SNAP_THRESHOLD_DEGREES: float = 30.0

# Fraction of snaps required for a channel to be considered "snap-heavy."
SNAP_HEAVY_FRACTION: float = 0.5


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

    # Filter to keyframes for this channel only
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

    Rules:
    - Rotation: catmullrom by default, linear if snap-heavy
    - Position: linear by default
    - Scale: linear by default
    - If easing is non-linear, always use catmullrom

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

    # Select interpolation for each keyframe
    new_keyframes: List[KeyframeData] = []
    catmullrom_count = 0
    linear_count = 0

    for kf in bone_anim.keyframes:
        # Determine interpolation based on channel and easing
        if kf.easing != "linear":
            # Non-linear easing always uses catmullrom
            interp = "catmullrom"
        elif snap_heavy.get(kf.channel, False):
            # Snap-heavy channels use linear
            interp = "linear"
        else:
            # Use default interpolation for this channel
            interp = DEFAULT_INTERPOLATION.get(kf.channel, "linear")

        # Count
        if interp == "catmullrom":
            catmullrom_count += 1
        else:
            linear_count += 1

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
    """Select interpolation mode for each keyframe.

    Rules:
    - Rotation: catmullrom by default (smooth curves match cos/sin sources)
      But if the channel is snap-heavy (>50% large jumps), use linear
    - Position: linear by default (crisp, predictable movements)
    - Scale: linear by default
    - If easing is non-linear, always use catmullrom

    A channel is "snap-heavy" if more than 50% of consecutive keyframe
    pairs have a delta > threshold degrees (default 30° for rotation).

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
