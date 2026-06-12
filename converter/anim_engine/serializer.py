#!/usr/bin/env python3
"""
AnimEngineV2 — Serializer
==========================
Converts intermediate AnimationData to bbmodel animation format.

This stage is responsible for:
- Building animators dict with keyframes
- Generating proper UUIDs (16-hex-char to reduce collision risk)
- Handling Molang expressions as special keyframes
- Ensuring proper sort order
- Outputting the final bbmodel-compatible animation list

Input:  Dict[str, AnimationData] from transform stage
Output: List[dict] — ready for inclusion in bbmodel["animations"]
"""

from __future__ import annotations

import logging
from typing import Dict, List

from .types import AnimKeyframe, AnimationData, BoneAnimation
from .utils import generate_uuid, round_for_bbmodel

logger = logging.getLogger(__name__)


class SerializeResult:
    """Result of serialization.

    Attributes:
        animations: List of bbmodel-format animation dicts.
        warnings: Warnings generated during serialization.
        stats: Serialization statistics.
    """

    def __init__(self) -> None:
        self.animations: List[dict] = []
        self.warnings: List[str] = []
        self.stats: dict = {
            "total_animations": 0,
            "total_bones": 0,
            "total_keyframes": 0,
            "molang_keyframes": 0,
        }


def serialize_animations(
    animations: Dict[str, AnimationData],
    model_name: str = "",
) -> SerializeResult:
    """Serialize all animations to bbmodel format.

    Args:
        animations: Transformed AnimationData dict.
        model_name: Model name for logging.

    Returns:
        SerializeResult with bbmodel animation list, warnings, and stats.
    """
    result = SerializeResult()

    for anim_name, anim_data in animations.items():
        try:
            anim_dict = _serialize_single_animation(anim_data, model_name, result.stats)
            result.animations.append(anim_dict)
            result.stats["total_animations"] += 1
        except Exception as e:
            result.warnings.append(
                f"[{model_name}] Serialization failed for '{anim_name}': {e}"
            )
            continue

    return result


def _serialize_single_animation(
    anim: AnimationData,
    model_name: str,
    stats: dict,
) -> dict:
    """Serialize one animation to bbmodel format.

    Output format:
        {
            "name": "animation.model.idle",
            "uuid": "...",
            "loop": "loop",
            "override": false,
            "length": 6.2832,
            "snapping": 24,
            "selected": false,
            "anim_time_update": "",
            "blend_weight": "",
            "animators": {
                "boneName": {
                    "name": "boneName",
                    "type": "bone",
                    "keyframes": [ ... ]
                }
            }
        }

    Args:
        anim: AnimationData to serialize.
        model_name: Model name for logging.
        stats: Stats dict to update.

    Returns:
        Dict in bbmodel animation format.
    """
    animators = {}

    for bone_name, bone_anim in anim.bones.items():
        keyframes = _serialize_keyframes(bone_anim.keyframes, model_name, stats)

        if keyframes:
            animators[bone_name] = {
                "name": bone_name,
                "type": "bone",
                "keyframes": keyframes,
            }
            stats["total_bones"] += 1

    return {
        "name": anim.name,
        "uuid": generate_uuid(),
        "loop": anim.loop,
        "override": False,
        "length": float(anim.length),
        "snapping": 24,
        "selected": False,
        "anim_time_update": "",
        "blend_weight": "",
        "animators": animators,
    }


def _serialize_keyframes(
    keyframes: List[AnimKeyframe],
    model_name: str,
    stats: dict,
) -> List[dict]:
    """Serialize a list of AnimKeyframe to bbmodel keyframe format.

    Output format:
        {
            "channel": "rotation",
            "data_points": [{"x": ..., "y": ..., "z": ..., "easing": "linear"}],
            "uuid": "...",
            "time": 0.0,
            "color": -1,
            "interpolation": "catmullrom"
        }

    For Molang keyframes, the data_points use string values instead of numbers.

    Args:
        keyframes: List of AnimKeyframe to serialize.
        model_name: Model name for logging.
        stats: Stats dict to update.

    Returns:
        List of dicts in bbmodel keyframe format.
    """
    result = []

    for kf in keyframes:
        # Build data_points
        if kf.is_molang and (kf.molang_x or kf.molang_y or kf.molang_z):
            # Molang keyframe — use string values for Molang axes
            data_point = {
                "x": kf.molang_x if kf.molang_x else round_for_bbmodel(kf.x),
                "y": kf.molang_y if kf.molang_y else round_for_bbmodel(kf.y),
                "z": kf.molang_z if kf.molang_z else round_for_bbmodel(kf.z),
                "easing": kf.easing,
            }
            stats["molang_keyframes"] += 1
        else:
            # Normal numeric keyframe
            data_point = {
                "x": round_for_bbmodel(kf.x),
                "y": round_for_bbmodel(kf.y),
                "z": round_for_bbmodel(kf.z),
                "easing": kf.easing,
            }

        kf_dict = {
            "channel": kf.channel,
            "data_points": [data_point],
            "uuid": generate_uuid(),
            "time": round_for_bbmodel(kf.time),
            "color": -1,
            "interpolation": kf.interpolation,
        }

        result.append(kf_dict)
        stats["total_keyframes"] += 1

    return result
