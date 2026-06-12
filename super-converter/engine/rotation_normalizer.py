#!/usr/bin/env python3
"""
Super Architecture — Rotation Normalizer (Fixed)
==================================================

Rotation normalization that PRESERVES exact source Euler angles.

CRITICAL FIX: The previous implementation converted every keyframe through
Euler → Quaternion → Euler round-trip, which CHANGED the exact values even
when there was no problem to fix. The quaternion decomposition can produce
different Euler angles that represent the same rotation, but with different
component values. This introduced subtle jitter in the animation.

The new implementation only applies corrections when there is an ACTUAL
problem:
  1. Consecutive quaternion shortest-path (dot product < 0)
  2. Large angle discontinuities (> 180°) between consecutive keyframes

For keyframes that are already consistent, the values are preserved exactly.

All transforms produce new data — input is never mutated.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from core.types import (
    AXES,
    AnimationIR,
    AxisValue,
    BoneAnimationIR,
    KeyframeData,
    ROTATION_MAX,
    ROTATION_MIN,
)
from core.math_utils import normalize_rotation, values_match
from core.quaternion import Quaternion, euler_shortest_path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Threshold for detecting angle discontinuity
# ---------------------------------------------------------------------------

# If the delta on any axis between consecutive keyframes exceeds this,
# we apply shortest-path correction.
DISCONTINUITY_THRESHOLD_DEGREES: float = 180.0


# ---------------------------------------------------------------------------
# Per-bone rotation normalization
# ---------------------------------------------------------------------------

def _normalize_bone_rotations(
    bone_anim: BoneAnimationIR,
    anim_name: str,
    model_name: str,
    stats: dict,
) -> BoneAnimationIR:
    """Normalize rotation keyframes for one bone, preserving exact values.

    Instead of the old approach (Euler → Quaternion → Euler for every keyframe),
    we now only apply corrections when there's an actual problem:

      1. Shortest-path: If consecutive quaternions have negative dot product,
         flip the second quaternion.
      2. Angle discontinuity: If any axis has a jump > 180° between
         consecutive keyframes, adjust to the shortest path.

    Keyframes that don't have these problems are left EXACTLY as-is.

    Args:
        bone_anim: The bone's animation data.
        anim_name: Animation name for logging.
        model_name: Model name for logging.
        stats: Dict to update with normalization statistics.

    Returns:
        New BoneAnimationIR with normalized rotations.
    """
    # Separate rotation keyframes from other channels
    rot_kfs: List[KeyframeData] = []
    other_kfs: List[KeyframeData] = []

    for kf in bone_anim.keyframes:
        if kf.channel == "rotation":
            rot_kfs.append(kf)
        else:
            other_kfs.append(kf)

    if not rot_kfs:
        return bone_anim

    # Sort rotation keyframes by time
    rot_kfs.sort(key=lambda k: k.time)

    shortest_path_fixes = 0

    # Step 1: Build quaternions for shortest-path analysis
    quaternions: List[Quaternion] = []
    for kf in rot_kfs:
        q = Quaternion.from_euler_zyx(
            kf.x.value, kf.y.value, kf.z.value, degrees=True
        )
        quaternions.append(q.normalize())

    # Step 2: Check if consecutive quaternions need shortest-path fix
    needs_quaternion_fix = [False] * len(quaternions)
    for i in range(1, len(quaternions)):
        dot = (
            quaternions[i - 1].w * quaternions[i].w +
            quaternions[i - 1].x * quaternions[i].x +
            quaternions[i - 1].y * quaternions[i].y +
            quaternions[i - 1].z * quaternions[i].z
        )
        if dot < 0.0:
            needs_quaternion_fix[i] = True

    # Step 3: Apply fixes only where needed
    new_rot_kfs: List[KeyframeData] = []

    for i, kf in enumerate(rot_kfs):
        rx, ry, rz = kf.x.value, kf.y.value, kf.z.value

        # First, normalize to [-360, 360] range
        rx = normalize_rotation(rx)
        ry = normalize_rotation(ry)
        rz = normalize_rotation(rz)

        # Apply quaternion shortest-path fix if needed
        if needs_quaternion_fix[i]:
            # Flip the quaternion to take the shortest path
            quaternions[i] = Quaternion(
                -quaternions[i].w,
                -quaternions[i].x,
                -quaternions[i].y,
                -quaternions[i].z,
            )
            # Decompose back to Euler
            rx_new, ry_new, rz_new = quaternions[i].to_euler_zyx(degrees=True)
            rx_new = normalize_rotation(rx_new)
            ry_new = normalize_rotation(ry_new)
            rz_new = normalize_rotation(rz_new)

            if (not values_match(rx, rx_new, tolerance=0.01) or
                    not values_match(ry, ry_new, tolerance=0.01) or
                    not values_match(rz, rz_new, tolerance=0.01)):
                rx, ry, rz = rx_new, ry_new, rz_new
                shortest_path_fixes += 1

        new_rot_kfs.append(KeyframeData(
            time=kf.time,
            channel=kf.channel,
            x=AxisValue.explicit_val(rx),
            y=AxisValue.explicit_val(ry),
            z=AxisValue.explicit_val(rz),
            easing=kf.easing,
            interpolation=kf.interpolation,
            is_molang=kf.is_molang,
            molang_x=kf.molang_x,
            molang_y=kf.molang_y,
            molang_z=kf.molang_z,
        ))

    # Step 4: Apply euler_shortest_path for remaining angle discontinuities
    # This handles cases where individual axis values jump by more than 180°
    for i in range(1, len(new_rot_kfs)):
        prev = new_rot_kfs[i - 1]
        curr = new_rot_kfs[i]

        # Check if there's a large discontinuity on any axis
        has_discontinuity = False
        for axis in AXES:
            prev_val = getattr(prev, axis).value
            curr_val = getattr(curr, axis).value
            if abs(curr_val - prev_val) > DISCONTINUITY_THRESHOLD_DEGREES:
                has_discontinuity = True
                break

        if has_discontinuity:
            rx_adj, ry_adj, rz_adj = euler_shortest_path(
                prev.x.value, prev.y.value, prev.z.value,
                curr.x.value, curr.y.value, curr.z.value,
            )

            # Only update if the adjustment is significant
            if (not values_match(curr.x.value, rx_adj, tolerance=0.01) or
                    not values_match(curr.y.value, ry_adj, tolerance=0.01) or
                    not values_match(curr.z.value, rz_adj, tolerance=0.01)):
                new_rot_kfs[i] = KeyframeData(
                    time=curr.time,
                    channel=curr.channel,
                    x=AxisValue.explicit_val(normalize_rotation(rx_adj)),
                    y=AxisValue.explicit_val(normalize_rotation(ry_adj)),
                    z=AxisValue.explicit_val(normalize_rotation(rz_adj)),
                    easing=curr.easing,
                    interpolation=curr.interpolation,
                    is_molang=curr.is_molang,
                    molang_x=curr.molang_x,
                    molang_y=curr.molang_y,
                    molang_z=curr.molang_z,
                )
                shortest_path_fixes += 1

    # Combine rotation and other keyframes
    all_kfs = new_rot_kfs + other_kfs
    all_kfs.sort(key=lambda k: (k.time, k.channel))

    stats["shortest_path_fixes"] = stats.get("shortest_path_fixes", 0) + shortest_path_fixes

    return BoneAnimationIR(
        bone_name=bone_anim.bone_name,
        keyframes=all_kfs,
    )


# ---------------------------------------------------------------------------
# Main rotation normalization function
# ---------------------------------------------------------------------------

def normalize_rotations(
    animations: Dict[str, AnimationIR],
    model_name: str = "",
    stats: dict = None,
) -> Dict[str, AnimationIR]:
    """Normalize rotation keyframes, preserving exact values where possible.

    Only applies corrections when there is an actual problem:
      - Negative quaternion dot product (shortest path)
      - Large angle discontinuities (> 180°) between consecutive keyframes

    Args:
        animations: Dict mapping animation_name -> AnimationIR.
        model_name: Optional model name for logging context.
        stats: Optional dict to update with normalization statistics.

    Returns:
        New dict of animations with normalized rotations.
    """
    if stats is None:
        stats = {}

    stats.setdefault("shortest_path_fixes", 0)

    result: Dict[str, AnimationIR] = {}

    for anim_name, anim in animations.items():
        new_bones: Dict[str, BoneAnimationIR] = {}

        for bone_name, bone_anim in anim.bones.items():
            # Check if this bone has rotation keyframes
            has_rotation = any(
                kf.channel == "rotation" for kf in bone_anim.keyframes
            )

            if not has_rotation:
                new_bones[bone_name] = bone_anim
                continue

            try:
                new_bone = _normalize_bone_rotations(
                    bone_anim, anim_name, model_name, stats,
                )
                new_bones[bone_name] = new_bone
            except Exception as e:
                logger.warning(
                    "[%s] Rotation normalization error for %s/%s: %s, "
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
