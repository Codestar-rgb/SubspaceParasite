#!/usr/bin/env python3
"""
AnimEngineV2 — Validator
=========================
Validates and cleans parsed AnimationData.

This stage is responsible for:
- Checking for NaN, Infinity values
- Validating time >= 0 and time <= animation_length
- Warning on duplicate time points
- Warning on empty animations
- Normalizing rotation values to [-360, 360]
- Removing invalid keyframes with warnings
- Detecting snap-heavy animations (suggests linear interpolation)

This stage does NOT:
- Apply carry-forward (see transform.py)
- Generate UUIDs (see serializer.py)
"""

from __future__ import annotations

import logging
import math
from typing import Dict, List, Tuple

from .types import (
    AXES,
    AnimKeyframe,
    AnimationData,
    BoneAnimation,
    ROTATION_MAX,
    ROTATION_MIN,
)
from .utils import is_valid_number, normalize_rotation, values_match

logger = logging.getLogger(__name__)


class ValidationResult:
    """Result of validating animations.

    Attributes:
        animations: Cleaned AnimationData dict.
        warnings: Warning messages generated during validation.
        stats: Validation statistics.
    """

    def __init__(self) -> None:
        self.animations: Dict[str, AnimationData] = {}
        self.warnings: List[str] = []
        self.stats: dict = {
            "total_keyframes_in": 0,
            "total_keyframes_out": 0,
            "invalid_keyframes_removed": 0,
            "duplicate_times_merged": 0,
            "rotations_normalized": 0,
            "empty_bones_removed": 0,
            "empty_animations_removed": 0,
        }


def validate_animations(
    animations: Dict[str, AnimationData],
    model_name: str = "",
) -> ValidationResult:
    """Validate and clean all parsed animations.

    Args:
        animations: Dict from parser stage (anim_name -> AnimationData).
        model_name: Model name for logging context.

    Returns:
        ValidationResult with cleaned animations, warnings, and stats.
    """
    result = ValidationResult()

    for anim_name, anim_data in animations.items():
        try:
            cleaned = _validate_single_animation(anim_data, model_name, result.warnings)
            if cleaned.bones:
                result.animations[anim_name] = cleaned
            else:
                result.stats["empty_animations_removed"] += 1
                result.warnings.append(
                    f"[{model_name}] Animation '{anim_name}' has no valid bones after validation"
                )
        except Exception as e:
            result.warnings.append(
                f"[{model_name}] Validation failed for '{anim_name}': {e}"
            )
            continue

    return result


def _validate_single_animation(
    anim: AnimationData,
    model_name: str,
    warnings: List[str],
) -> AnimationData:
    """Validate and clean a single animation.

    Args:
        anim: The AnimationData to validate.
        model_name: Model name for logging.
        warnings: List to append warnings to.

    Returns:
        New AnimationData with cleaned keyframes.
    """
    cleaned_bones: Dict[str, BoneAnimation] = {}

    for bone_name, bone_anim in anim.bones.items():
        cleaned_kfs = _validate_bone_keyframes(
            bone_anim.keyframes, anim.length, anim.name, bone_name, model_name, warnings
        )

        # Deduplicate time points (same time + same channel)
        cleaned_kfs = _deduplicate_keyframes(cleaned_kfs, anim.name, bone_name, model_name, warnings)

        if cleaned_kfs:
            cleaned_bones[bone_name] = BoneAnimation(
                bone_name=bone_name,
                keyframes=cleaned_kfs,
            )
        else:
            # Bone had only invalid keyframes
            pass  # silently skip empty bones

    return AnimationData(
        name=anim.name,
        loop=anim.loop,
        length=anim.length,
        bones=cleaned_bones,
    )


def _validate_bone_keyframes(
    keyframes: List[AnimKeyframe],
    anim_length: float,
    anim_name: str,
    bone_name: str,
    model_name: str,
    warnings: List[str],
) -> List[AnimKeyframe]:
    """Validate individual keyframes, removing invalid ones.

    Checks:
        - NaN and Infinity values
        - Time < 0 or time > anim_length (clamp, warn)
        - Rotation normalization

    Args:
        keyframes: List of keyframes to validate.
        anim_length: Animation length for time validation.
        anim_name: Animation name for logging.
        bone_name: Bone name for logging.
        model_name: Model name for logging.
        warnings: List to append warnings to.

    Returns:
        List of valid, cleaned AnimKeyframe.
    """
    valid_kfs: List[AnimKeyframe] = []

    for kf in keyframes:
        # Skip Molang keyframes — they don't have numeric values to validate
        if kf.is_molang:
            valid_kfs.append(kf)
            continue

        # Check for NaN / Infinity
        if not is_valid_number(kf.x) or not is_valid_number(kf.y) or not is_valid_number(kf.z):
            warnings.append(
                f"[{model_name}] {anim_name}/{bone_name}: "
                f"Invalid numeric value at t={kf.time:.4f} "
                f"(x={kf.x}, y={kf.y}, z={kf.z}), removing keyframe"
            )
            continue

        # Validate time
        time = kf.time
        if time < 0:
            warnings.append(
                f"[{model_name}] {anim_name}/{bone_name}: "
                f"Negative time {time:.4f}, clamping to 0"
            )
            time = 0.0
        if anim_length > 0 and time > anim_length:
            warnings.append(
                f"[{model_name}] {anim_name}/{bone_name}: "
                f"Time {time:.4f} exceeds animation length {anim_length:.4f}, clamping"
            )
            time = anim_length

        # Normalize rotation values
        x_val, y_val, z_val = kf.x, kf.y, kf.z
        if kf.channel == "rotation":
            x_norm = normalize_rotation(kf.x)
            y_norm = normalize_rotation(kf.y)
            z_norm = normalize_rotation(kf.z)

            if not values_match(x_norm, kf.x) or not values_match(y_norm, kf.y) or not values_match(z_norm, kf.z):
                # Only log if the normalization actually changed something significant
                if (abs(x_norm - kf.x) > 0.01 or abs(y_norm - kf.y) > 0.01 or abs(z_norm - kf.z) > 0.01):
                    logger.debug(
                        "[%s] %s/%s: Normalized rotation at t=%.4f: "
                        "(%.2f, %.2f, %.2f) -> (%.2f, %.2f, %.2f)",
                        model_name, anim_name, bone_name, kf.time,
                        kf.x, kf.y, kf.z, x_norm, y_norm, z_norm,
                    )

                x_val, y_val, z_val = x_norm, y_norm, z_norm

        # Create cleaned keyframe (immutable — new instance)
        cleaned = AnimKeyframe(
            time=time,
            x=x_val,
            y=y_val,
            z=z_val,
            easing=kf.easing,
            interpolation=kf.interpolation,
            channel=kf.channel,
            is_molang=kf.is_molang,
            molang_x=kf.molang_x,
            molang_y=kf.molang_y,
            molang_z=kf.molang_z,
        )
        valid_kfs.append(cleaned)

    return valid_kfs


def _deduplicate_keyframes(
    keyframes: List[AnimKeyframe],
    anim_name: str,
    bone_name: str,
    model_name: str,
    warnings: List[str],
) -> List[AnimKeyframe]:
    """Remove duplicate time+channel keyframes, keeping the last one.

    Different axes may produce the same time point. After merging per-axis
    into unified keyframes (done in parser), we may still have duplicates
    if two channels happen to have keyframes at the same time.

    Since each keyframe already has a specific channel, we deduplicate
    by (time, channel) pairs, keeping the last occurrence.

    Args:
        keyframes: Sorted list of keyframes.
        anim_name: Animation name for logging.
        bone_name: Bone name for logging.
        model_name: Model name for logging.
        warnings: List to append warnings to.

    Returns:
        Deduplicated list of keyframes.
    """
    if len(keyframes) <= 1:
        return keyframes

    seen: Dict[Tuple[float, str], AnimKeyframe] = {}
    for kf in keyframes:
        key = (round(kf.time, 8), kf.channel)
        seen[key] = kf  # Last one wins

    deduped = sorted(seen.values(), key=lambda kf: (kf.time, kf.channel))

    if len(deduped) < len(keyframes):
        removed = len(keyframes) - len(deduped)
        logger.debug(
            "[%s] %s/%s: Removed %d duplicate time+channel keyframes",
            model_name, anim_name, bone_name, removed,
        )

    return deduped


def is_snap_heavy(keyframes: List[AnimKeyframe], threshold: float = 0.05) -> bool:
    """Detect if an animation is "snap-heavy" (large value jumps between keyframes).

    This suggests the animation uses deliberate snap transitions rather than
    smooth curves. In such cases, linear interpolation may be more appropriate
    than catmullrom to avoid overshoot artifacts.

    A rotation channel is considered snap-heavy if more than 50% of its
    consecutive keyframe pairs have delta > threshold degrees.

    Args:
        keyframes: List of keyframes for a single channel.
        threshold: Minimum delta to count as a "snap" (in degrees for rotation).

    Returns:
        True if the animation appears snap-heavy.
    """
    if len(keyframes) < 3:
        return False

    channel_kfs = [kf for kf in keyframes if not kf.is_molang]
    if len(channel_kfs) < 3:
        return False

    snap_count = 0
    total_pairs = 0

    for i in range(1, len(channel_kfs)):
        prev = channel_kfs[i - 1]
        curr = channel_kfs[i]

        dx = abs(curr.x - prev.x)
        dy = abs(curr.y - prev.y)
        dz = abs(curr.z - prev.z)
        max_delta = max(dx, dy, dz)

        total_pairs += 1
        if max_delta > threshold:
            snap_count += 1

    if total_pairs == 0:
        return False

    # More than 50% snaps → snap-heavy
    return (snap_count / total_pairs) > 0.5
