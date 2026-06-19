#!/usr/bin/env python3
"""
Head Tracking Injector (v6.2)
=============================
Injects a Molang-driven head tracking animation into the .bbmodel output.

BACKGROUND:
  145 of 154 SRP models have head tracking in the original Java:
    this.jointH.field_78796_g = netHeadYaw * 0.016f;   // rotateAngleY (yaw)
    this.jointH.field_78795_f = headPitch * 0.016f;   // rotateAngleX (pitch)
  The upstream Qom-Inseac extraction drops this entirely because netHeadYaw
  and headPitch are runtime variables that can't be baked into static keyframes.

SOLUTION:
  Create a SEPARATE animation `animation.srparasites.<name>.head_track` that
  contains ONE keyframe at t=0 on the head bone, with Molang expressions:
    rotation_y = -sign(yaw_coeff) * query.head_yaw * (|yaw_coeff| * 57.2958)
    rotation_x =  sign(pitch_coeff) * query.head_pitch * (|pitch_coeff| * 57.2958)

  At runtime, GeckoLib 4 (MC 1.20.1) evaluates these Molang expressions to
  rotate the head bone based on the entity's actual head yaw/pitch.

  The mod developer enables this animation alongside idle/walk via GeckoLib's
  animation layering (both play simultaneously; head_track overrides the head
  bone's rotation).

COORDINATE TRANSFORM:
  Java ModelRenderer uses RH, Y-down; Blockbench uses LH, Y-up.
  The transform M = diag(1, -1, -1) negates Y and Z rotations.
  So Java rotateAngleY → BB rotation_y is negated.
  Java rotateAngleX → BB rotation_x is NOT negated.

COEFFICIENT CONVERSION:
  Java: rotateAngleY_rad = netHeadYaw_deg * 0.016  (0.016 ≈ π/180)
  BB:   rotation_y_deg = rotateAngleY_rad * 57.2958 = netHeadYaw_deg * 0.9167
  GeckoLib query.head_yaw returns degrees (matching Java's netHeadYaw).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from engine.java_analyzer import HeadTrackingInfo, ModelMetadata

logger = logging.getLogger(__name__)

RAD2DEG = 57.29577951308232  # 180 / pi


def _make_uuid() -> str:
    return str(uuid.uuid4()).replace("-", "")[:16]


def build_head_track_animation(
    meta: ModelMetadata,
    bone_uuids: Dict[str, str],
) -> Optional[dict]:
    """Build a head tracking animation dict ready to insert into .bbmodel.

    Args:
        meta: ModelMetadata with head_tracking info.
        bone_uuids: Dict mapping bone_name → uuid (from the model's outliner).

    Returns:
        Animation dict, or None if no head tracking or head bone not found.
    """
    if not meta.head_tracking:
        return None

    ht = meta.head_tracking
    head_bone = ht.bone_name

    # Find the bone's UUID in the model
    animator_key = bone_uuids.get(head_bone)
    if not animator_key:
        # Try case-insensitive match
        for bname, buuid in bone_uuids.items():
            if bname.lower() == head_bone.lower():
                animator_key = buuid
                head_bone = bname
                break
    if not animator_key:
        logger.debug("[%s] head_track: head bone '%s' not in model", meta.model_name, head_bone)
        return None

    # Compute Molang expressions
    # Yaw: Java rotateAngle{Y or Z} = netHeadYaw * yaw_coeff (radians)
    #   BB rotation = -(sign(yaw_coeff)) * query.head_yaw * (|yaw_coeff| * RAD2DEG)
    #   The leading - is the RH→LH flip (applies to both Y and Z axes).
    yaw_mag = abs(ht.yaw_coeff) * RAD2DEG  # degrees per degree of head yaw
    yaw_sign = -1.0 if ht.yaw_coeff > 0 else 1.0  # RH→LH flip + Java sign
    if yaw_sign < 0:
        yaw_molang = f"-query.head_yaw * {yaw_mag:.4f}"
    else:
        yaw_molang = f"query.head_yaw * {yaw_mag:.4f}"

    # Pitch: Java rotateAngleX = headPitch * pitch_coeff (radians)
    #   BB rotation_x = sign(pitch_coeff) * query.head_pitch * (|pitch_coeff| * RAD2DEG)
    #   No RH→LH flip for X axis.
    pitch_mag = abs(ht.pitch_coeff) * RAD2DEG
    pitch_sign = 1.0 if ht.pitch_coeff > 0 else -1.0
    if pitch_sign < 0:
        pitch_molang = f"-query.head_pitch * {pitch_mag:.4f}"
    else:
        pitch_molang = f"query.head_pitch * {pitch_mag:.4f}"

    # Build the keyframe with Molang string values
    # The yaw axis can be Y (field_78796_g) or Z (field_78808_h) depending on the model.
    # Pitch is always X (field_78795_f).
    yaw_axis = ht.yaw_axis  # "y" or "z"
    dp = {"x": "0", "y": "0", "z": "0"}
    if ht.pitch_coeff != 0:
        dp["x"] = pitch_molang
    if ht.yaw_coeff != 0:
        dp[yaw_axis] = yaw_molang

    keyframe = {
        "channel": "rotation",
        "data_points": [
            {
                "easing": "linear",
                **dp,
            }
        ],
        "uuid": _make_uuid(),
        "time": 0.0,
        "color": -1,
        "interpolation": "linear",
    }

    animation = {
        "name": f"animation.srparasites.{meta.model_name}.head_track",
        "uuid": _make_uuid(),
        "loop": "loop",
        "override": False,
        "length": 0.0,
        "snapping": 24,
        "selected": False,
        "anim_time_update": "",
        "blend_weight": "",
        "animators": {
            animator_key: {
                "name": head_bone,
                "type": "bone",
                "keyframes": [keyframe],
            }
        },
    }

    logger.debug(
        "[%s] head_track: bone=%s, yaw=%s, pitch=%s",
        meta.model_name, head_bone, yaw_molang, pitch_molang,
    )
    return animation
