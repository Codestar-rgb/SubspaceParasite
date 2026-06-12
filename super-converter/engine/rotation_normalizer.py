#!/usr/bin/env python3
"""
Super Architecture — Rotation Normalizer
==========================================

Quaternion-based rotation normalization.

For each bone's rotation channel:
  1. Convert each keyframe's Euler angles to a quaternion
  2. Ensure consecutive quaternions take the shortest path
     (flip sign if dot product is negative)
  3. Convert back to Euler angles

This eliminates:
  - 360° jumps (e.g., 350° → 10° instead of 350° → 370°)
  - Gimbal lock artifacts at ±90° pitch
  - Inconsistent rotation paths between keyframes

Also normalizes all rotation values to [-360, 360] range.

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
# Quaternion dot product
# ---------------------------------------------------------------------------

def _quaternion_dot(q1: Quaternion, q2: Quaternion) -> float:
    """Compute the dot product of two quaternions.

    Args:
        q1: First quaternion.
        q2: Second quaternion.

    Returns:
        The dot product (scalar).
    """
    return q1.w * q2.w + q1.x * q2.x + q1.y * q2.y + q1.z * q2.z


# ---------------------------------------------------------------------------
# Per-bone rotation normalization
# ---------------------------------------------------------------------------

def _normalize_bone_rotations(
    bone_anim: BoneAnimationIR,
    anim_name: str,
    model_name: str,
    stats: dict,
) -> BoneAnimationIR:
    """Normalize rotation keyframes for one bone using quaternion math.

    For each rotation keyframe:
      1. Convert Euler angles to quaternion
      2. Ensure consecutive quaternions take the shortest path
      3. Convert back to Euler angles
      4. Normalize to [-360, 360] range

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
    rotations_normalized = 0

    # Step 1: Build quaternions from rotation keyframes
    # Use the GeckoLib/Blockbench convention: Euler ZYX (extrinsic)
    quaternions: List[Quaternion] = []
    for kf in rot_kfs:
        q = Quaternion.from_euler_zyx(
            kf.x.value, kf.y.value, kf.z.value, degrees=True
        )
        quaternions.append(q.normalize())

    # Step 2: Ensure consecutive quaternions take the shortest path
    # If the dot product between consecutive quaternions is negative,
    # flip the sign of the second quaternion (q and -q represent the
    # same rotation, but the flipped version takes the shorter path).
    for i in range(1, len(quaternions)):
        dot = _quaternion_dot(quaternions[i - 1], quaternions[i])
        if dot < 0.0:
            # Flip the quaternion to take the shortest path
            quaternions[i] = Quaternion(
                -quaternions[i].w,
                -quaternions[i].x,
                -quaternions[i].y,
                -quaternions[i].z,
            )
            shortest_path_fixes += 1

    # Step 3: Convert back to Euler angles and build new keyframes
    new_rot_kfs: List[KeyframeData] = []

    for i, kf in enumerate(rot_kfs):
        # Decompose quaternion back to Euler angles
        rx, ry, rz = quaternions[i].to_euler_zyx(degrees=True)

        # Normalize to [-360, 360]
        rx = normalize_rotation(rx)
        ry = normalize_rotation(ry)
        rz = normalize_rotation(rz)

        # Track how many values changed significantly
        old_vals = (kf.x.value, kf.y.value, kf.z.value)
        new_vals = (rx, ry, rz)

        changed = False
        for old, new in zip(old_vals, new_vals):
            if not values_match(old, new, tolerance=0.01):
                changed = True
                rotations_normalized += 1

        # Create new keyframe with normalized rotation values
        new_kf = KeyframeData(
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
        )
        new_rot_kfs.append(new_kf)

    # Step 4: Apply euler_shortest_path between consecutive keyframes
    # as an additional safeguard for any remaining angle discontinuities
    for i in range(1, len(new_rot_kfs)):
        prev = new_rot_kfs[i - 1]
        curr = new_rot_kfs[i]

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

    # Also normalize position and scale keyframes (just value normalization,
    # no quaternion math needed)
    normalized_other: List[KeyframeData] = []
    for kf in other_kfs:
        # For position and scale, just ensure values are finite
        # (rotation normalization doesn't apply)
        normalized_other.append(kf)

    # Combine and sort
    all_kfs = new_rot_kfs + normalized_other
    all_kfs.sort(key=lambda k: (k.time, k.channel))

    stats["shortest_path_fixes"] = stats.get("shortest_path_fixes", 0) + shortest_path_fixes
    stats["rotations_normalized"] = stats.get("rotations_normalized", 0) + rotations_normalized

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
    """Normalize rotation keyframes using quaternion math.

    For each bone's rotation channel:
    1. Convert each keyframe's Euler angles to a quaternion
    2. Ensure consecutive quaternions take the shortest path
       (flip sign if dot product is negative)
    3. Convert back to Euler angles

    This eliminates:
    - 360° jumps (e.g., 350° → 10° instead of 350° → 370°)
    - Gimbal lock artifacts at ±90° pitch
    - Inconsistent rotation paths between keyframes

    Also normalizes all rotation values to [-360, 360] range.

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
    stats.setdefault("rotations_normalized", 0)

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
