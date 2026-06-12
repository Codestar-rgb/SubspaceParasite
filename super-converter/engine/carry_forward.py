#!/usr/bin/env python3
"""
Super Architecture — Explicit Carry-Forward
=============================================

Smart carry-forward using the explicit axis tracking from AxisValue.

KEY IMPROVEMENT over old AnimEngineV2:
The old engine couldn't distinguish "x=0.0 at t=1.0" from "no x data at t=1.0".
It used a heuristic: if x != 0.0, use it; otherwise carry forward.
This was WRONG when the source data explicitly sets x=0.0.

The new engine uses AxisValue.explicit:
  - If AxisValue.explicit is True → use the value as-is (even if 0.0)
  - If AxisValue.explicit is False → carry forward the last explicit value

This produces correct animations in cases like:
  - A bone that rotates to 30° then back to 0° (old engine would incorrectly
    hold at 30° because 0° looked like "no data")
  - A bone that truly has no rotation on one axis (correctly stays at 0.0)

Algorithm per channel:
  1. Sort keyframes by time
  2. Track last_explicit = {x: 0.0, y: 0.0, z: 0.0}
  3. For each keyframe:
     - For each axis:
       - If explicit: use value, update last_explicit
       - If not explicit: use last_explicit[axis]

All transforms produce new data — input is never mutated.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

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
# Per-channel carry-forward
# ---------------------------------------------------------------------------

def apply_carry_forward(
    keyframes: List[KeyframeData],
    bone_name: str,
    model_name: str,
    stats: dict,
) -> List[KeyframeData]:
    """Fill missing axes at each time point using carry-forward.

    KEY IMPROVEMENT over old AnimEngineV2:
    The old engine couldn't distinguish "x=0.0 at t=1.0" from "no x data at t=1.0".
    It used a heuristic: if x != 0.0, use it; otherwise carry forward.
    This was WRONG when the source data explicitly sets x=0.0.

    The new engine uses AxisValue.explicit:
    - If AxisValue.explicit is True → use the value as-is (even if 0.0)
    - If AxisValue.explicit is False → carry forward the last explicit value

    This produces correct animations in cases like:
    - A bone that rotates to 30° then back to 0° (old engine would incorrectly
      hold at 30° because 0° looked like "no data")
    - A bone that truly has no rotation on one axis (correctly stays at 0.0)

    Algorithm per channel:
    1. Sort keyframes by time
    2. Track last_explicit = {x: 0.0, y: 0.0, z: 0.0}
    3. For each keyframe:
       - For each axis:
         - If explicit: use value, update last_explicit
         - If not explicit: use last_explicit[axis]

    Args:
        keyframes: List of KeyframeData for one bone (sorted by time).
        bone_name: Name of the bone (for logging).
        model_name: Model name (for logging).
        stats: Dict to update with carry-forward statistics.

    Returns:
        New list of KeyframeData with all axes filled in.  Missing axes
        (explicit=False) are replaced with the last explicit value.
    """
    if not keyframes:
        return []

    # Group keyframes by channel
    channel_kfs: Dict[str, List[KeyframeData]] = {}
    for kf in keyframes:
        if kf.channel not in channel_kfs:
            channel_kfs[kf.channel] = []
        channel_kfs[kf.channel].append(kf)

    result: List[KeyframeData] = []
    axes_filled = 0

    for channel in CHANNELS:
        kfs = channel_kfs.get(channel, [])
        if not kfs:
            continue

        # Sort by time (should already be sorted, but ensure)
        kfs_sorted = sorted(kfs, key=lambda k: k.time)

        # Track last explicit values for each axis
        last_explicit: Dict[str, float] = {"x": 0.0, "y": 0.0, "z": 0.0}
        # Track last explicit Molang for each axis
        last_molang: Dict[str, str] = {"x": "", "y": "", "z": ""}

        for kf in kfs_sorted:
            # Process each axis
            new_x_val: float
            new_x_explicit: bool
            new_x_molang: str

            new_y_val: float
            new_y_explicit: bool
            new_y_molang: str

            new_z_val: float
            new_z_explicit: bool
            new_z_molang: str

            # X axis
            if kf.x.explicit:
                new_x_val = kf.x.value
                new_x_explicit = True
                new_x_molang = kf.molang_x
                last_explicit["x"] = kf.x.value
                if kf.molang_x:
                    last_molang["x"] = kf.molang_x
            else:
                # Carry forward from last explicit value
                new_x_val = last_explicit["x"]
                new_x_explicit = True  # Now filled in
                new_x_molang = last_molang["x"]
                if kf.x.value != new_x_val:
                    axes_filled += 1

            # Y axis
            if kf.y.explicit:
                new_y_val = kf.y.value
                new_y_explicit = True
                new_y_molang = kf.molang_y
                last_explicit["y"] = kf.y.value
                if kf.molang_y:
                    last_molang["y"] = kf.molang_y
            else:
                new_y_val = last_explicit["y"]
                new_y_explicit = True
                new_y_molang = last_molang["y"]
                if kf.y.value != new_y_val:
                    axes_filled += 1

            # Z axis
            if kf.z.explicit:
                new_z_val = kf.z.value
                new_z_explicit = True
                new_z_molang = kf.molang_z
                last_explicit["z"] = kf.z.value
                if kf.molang_z:
                    last_molang["z"] = kf.molang_z
            else:
                new_z_val = last_explicit["z"]
                new_z_explicit = True
                new_z_molang = last_molang["z"]
                if kf.z.value != new_z_val:
                    axes_filled += 1

            # Create new keyframe with filled axes
            new_kf = KeyframeData(
                time=kf.time,
                channel=kf.channel,
                x=AxisValue(value=new_x_val, explicit=new_x_explicit),
                y=AxisValue(value=new_y_val, explicit=new_y_explicit),
                z=AxisValue(value=new_z_val, explicit=new_z_explicit),
                easing=kf.easing,
                interpolation=kf.interpolation,
                is_molang=kf.is_molang or bool(new_x_molang) or bool(new_y_molang) or bool(new_z_molang),
                molang_x=new_x_molang,
                molang_y=new_y_molang,
                molang_z=new_z_molang,
            )
            result.append(new_kf)

    # Sort by time, then channel for deterministic ordering
    result.sort(key=lambda k: (k.time, k.channel))

    stats["axes_filled"] = stats.get("axes_filled", 0) + axes_filled

    return result


# ---------------------------------------------------------------------------
# Apply to all animations
# ---------------------------------------------------------------------------

def apply_carry_forward_all(
    animations: Dict[str, AnimationIR],
    model_name: str,
    stats: dict,
) -> Dict[str, AnimationIR]:
    """Apply carry-forward to all animations.

    For each animation, for each bone, fill missing axes using the
    explicit carry-forward algorithm.

    Args:
        animations: Dict mapping animation_name -> AnimationIR.
        model_name: Model name for logging.
        stats: Dict to update with carry-forward statistics.

    Returns:
        New dict of animations with carry-forward applied.
    """
    result: Dict[str, AnimationIR] = {}

    for anim_name, anim in animations.items():
        new_bones: Dict[str, BoneAnimationIR] = {}

        for bone_name, bone_anim in anim.bones.items():
            try:
                new_keyframes = apply_carry_forward(
                    bone_anim.keyframes,
                    bone_name,
                    model_name,
                    stats,
                )
                new_bones[bone_name] = BoneAnimationIR(
                    bone_name=bone_name,
                    keyframes=new_keyframes,
                )
            except Exception as e:
                logger.warning(
                    "[%s] Carry-forward error for %s/%s: %s, keeping original",
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
