#!/usr/bin/env python3
"""
Super Architecture — Animation Validator
==========================================

Validate and clean parsed AnimationIR data before processing.

Checks:
  - NaN and Infinity values → remove keyframe with warning
  - Time < 0 → clamp to 0 with warning
  - Time > animation_length → clamp with warning
  - Rotation normalization to [-360, 360]
  - Duplicate time+channel keyframes → keep last, warn
  - Empty bones/animations → remove with warning
  - Detect snap-heavy channels (for interpolation override)

All transforms produce new data — input is never mutated.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.types import (
    AXES,
    CHANNELS,
    AnimationIR,
    AxisValue,
    BoneAnimationIR,
    KeyframeData,
    ROTATION_MAX,
    ROTATION_MIN,
)
from core.math_utils import is_valid_number, normalize_rotation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Snap-heavy detection threshold
# ---------------------------------------------------------------------------

# A rotation delta larger than this (in degrees) between consecutive keyframes
# is considered a "snap" (discontinuous jump).  If more than 50% of consecutive
# pairs in a channel are snaps, the channel is "snap-heavy" and should use
# linear interpolation instead of catmullrom.
SNAP_THRESHOLD_DEGREES: float = 30.0
SNAP_HEAVY_FRACTION: float = 0.5


# ---------------------------------------------------------------------------
# Validation result type
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Result of validating parsed AnimationIR data.

    Attributes:
        animations: Cleaned animations dict (new data, input not mutated).
        warnings: List of warning messages.
        stats: Dict with validation statistics.
    """

    animations: Dict[str, AnimationIR] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_axis_value(
    value: float,
    axis_name: str,
    channel: str,
    bone_name: str,
    anim_name: str,
    model_name: str,
    warnings: List[str],
) -> Optional[float]:
    """Validate a single axis value.

    Checks for NaN, Infinity, and (for rotation) normalization.

    Args:
        value: The axis value to validate.
        axis_name: "x", "y", or "z".
        channel: "rotation", "position", or "scale".
        bone_name: Bone name for warning context.
        anim_name: Animation name for warning context.
        model_name: Model name for warning context.
        warnings: List to append warning messages to.

    Returns:
        The validated (and possibly normalized) value, or None if the
        value should be removed.
    """
    if not is_valid_number(value):
        warnings.append(
            f"[{model_name}] {anim_name}/{bone_name}/{channel}.{axis_name}: "
            f"Invalid value {value}, removing keyframe"
        )
        return None

    # Rotation normalization
    if channel == "rotation":
        normalized = normalize_rotation(value)
        if abs(normalized - value) > 1e-6:
            warnings.append(
                f"[{model_name}] {anim_name}/{bone_name}/{channel}.{axis_name}: "
                f"Rotation {value:.4f} normalized to {normalized:.4f}"
            )
        return normalized

    return value


def _validate_keyframe(
    kf: KeyframeData,
    anim_length: float,
    anim_name: str,
    bone_name: str,
    model_name: str,
    warnings: List[str],
) -> Optional[KeyframeData]:
    """Validate and clean a single keyframe.

    Checks time bounds, NaN/Infinity, rotation normalization.

    Args:
        kf: The keyframe to validate.
        anim_length: Animation length in seconds (0 if unknown).
        anim_name: Animation name for warning context.
        bone_name: Bone name for warning context.
        model_name: Model name for warning context.
        warnings: List to append warning messages to.

    Returns:
        Validated KeyframeData (new instance), or None if the keyframe
        should be removed entirely.
    """
    # Check time bounds
    new_time = kf.time
    if kf.time < 0.0:
        warnings.append(
            f"[{model_name}] {anim_name}/{bone_name}/{kf.channel}: "
            f"Time {kf.time:.4f} < 0, clamping to 0"
        )
        new_time = 0.0

    if anim_length > 0.0 and kf.time > anim_length:
        warnings.append(
            f"[{model_name}] {anim_name}/{bone_name}/{kf.channel}: "
            f"Time {kf.time:.4f} > animation_length {anim_length:.4f}, clamping"
        )
        new_time = anim_length

    # Validate each axis value
    x_val: Optional[float] = None
    y_val: Optional[float] = None
    z_val: Optional[float] = None

    if kf.x.explicit:
        x_val = _validate_axis_value(
            kf.x.value, "x", kf.channel, bone_name, anim_name,
            model_name, warnings,
        )
    else:
        x_val = kf.x.value

    if kf.y.explicit:
        y_val = _validate_axis_value(
            kf.y.value, "y", kf.channel, bone_name, anim_name,
            model_name, warnings,
        )
    else:
        y_val = kf.y.value

    if kf.z.explicit:
        z_val = _validate_axis_value(
            kf.z.value, "z", kf.channel, bone_name, anim_name,
            model_name, warnings,
        )
    else:
        z_val = kf.z.value

    # If any explicit axis is invalid, remove the entire keyframe
    # (we can't have partial axis data in a keyframe)
    if kf.x.explicit and x_val is None:
        return None
    if kf.y.explicit and y_val is None:
        return None
    if kf.z.explicit and z_val is None:
        return None

    # Build new keyframe with validated values
    x_val = x_val if x_val is not None else kf.x.value
    y_val = y_val if y_val is not None else kf.y.value
    z_val = z_val if z_val is not None else kf.z.value

    return KeyframeData(
        time=new_time,
        channel=kf.channel,
        x=AxisValue(value=x_val, explicit=kf.x.explicit),
        y=AxisValue(value=y_val, explicit=kf.y.explicit),
        z=AxisValue(value=z_val, explicit=kf.z.explicit),
        easing=kf.easing,
        interpolation=kf.interpolation,
        is_molang=kf.is_molang,
        molang_x=kf.molang_x,
        molang_y=kf.molang_y,
        molang_z=kf.molang_z,
    )


def _deduplicate_keyframes(
    keyframes: List[KeyframeData],
    anim_name: str,
    bone_name: str,
    model_name: str,
    warnings: List[str],
) -> List[KeyframeData]:
    """Remove duplicate keyframes at the same (time, channel) pair.

    When two keyframes have the same time and channel, keep the last one
    (which typically overrides earlier values in GeckoLib semantics).

    Args:
        keyframes: Sorted list of keyframes.
        anim_name: Animation name for warning context.
        bone_name: Bone name for warning context.
        model_name: Model name for warning context.
        warnings: List to append warning messages to.

    Returns:
        Deduplicated list of keyframes (new list).
    """
    if not keyframes:
        return []

    # Group by (time, channel), keep last occurrence
    seen: Dict[Tuple[float, str], int] = {}
    result: List[KeyframeData] = []

    for kf in keyframes:
        key = (round(kf.time, 8), kf.channel)
        if key in seen:
            # Replace the previous entry
            idx = seen[key]
            result[idx] = kf
            warnings.append(
                f"[{model_name}] {anim_name}/{bone_name}/{kf.channel}: "
                f"Duplicate keyframe at t={kf.time:.4f}, keeping last"
            )
        else:
            seen[key] = len(result)
            result.append(kf)

    return result


def _is_snap_heavy(keyframes: List[KeyframeData], channel: str) -> bool:
    """Determine if a channel is snap-heavy (has many large jumps).

    A channel is "snap-heavy" if more than SNAP_HEAVY_FRACTION of
    consecutive keyframe pairs have a delta > SNAP_THRESHOLD_DEGREES.

    This is only meaningful for rotation channels; position and scale
    channels always return False.

    Args:
        keyframes: List of keyframes for this bone (sorted by time).
        channel: The channel to check.

    Returns:
        True if the channel is snap-heavy.
    """
    if channel != "rotation":
        return False

    # Filter to keyframes for this channel only
    channel_kfs = [kf for kf in keyframes if kf.channel == channel]
    if len(channel_kfs) < 2:
        return False

    snap_count = 0
    total_pairs = 0

    for i in range(1, len(channel_kfs)):
        prev = channel_kfs[i - 1]
        curr = channel_kfs[i]

        # Only compare explicit axes (after carry-forward, all axes
        # will have values, but we only care about large changes)
        for axis_name in AXES:
            prev_val = getattr(prev, axis_name).value
            curr_val = getattr(curr, axis_name).value
            delta = abs(curr_val - prev_val)
            total_pairs += 1
            if delta > SNAP_THRESHOLD_DEGREES:
                snap_count += 1

    if total_pairs == 0:
        return False

    fraction = snap_count / total_pairs
    return fraction > SNAP_HEAVY_FRACTION


def _validate_bone(
    bone_anim: BoneAnimationIR,
    anim_length: float,
    anim_name: str,
    model_name: str,
    warnings: List[str],
    stats: Dict[str, Any],
) -> Optional[BoneAnimationIR]:
    """Validate all keyframes for one bone.

    Args:
        bone_anim: The bone's animation data.
        anim_length: Animation length in seconds.
        anim_name: Animation name for warning context.
        model_name: Model name for warning context.
        warnings: List to append warning messages to.
        stats: Dict to update with statistics.

    Returns:
        Validated BoneAnimationIR (new instance), or None if the bone
        should be removed.
    """
    if not bone_anim.keyframes:
        warnings.append(
            f"[{model_name}] {anim_name}/{bone_anim.bone_name}: "
            f"Empty bone, removing"
        )
        stats["empty_bones_removed"] = stats.get("empty_bones_removed", 0) + 1
        return None

    # Validate each keyframe
    validated_kfs: List[KeyframeData] = []
    removed_count = 0

    for kf in bone_anim.keyframes:
        validated = _validate_keyframe(
            kf, anim_length, anim_name, bone_anim.bone_name,
            model_name, warnings,
        )
        if validated is not None:
            validated_kfs.append(validated)
        else:
            removed_count += 1

    stats["keyframes_removed_invalid"] = stats.get(
        "keyframes_removed_invalid", 0
    ) + removed_count

    if not validated_kfs:
        warnings.append(
            f"[{model_name}] {anim_name}/{bone_anim.bone_name}: "
            f"All keyframes invalid, removing bone"
        )
        stats["empty_bones_removed"] = stats.get("empty_bones_removed", 0) + 1
        return None

    # Sort by time, then channel
    validated_kfs.sort(key=lambda k: (k.time, k.channel))

    # Deduplicate
    deduped = _deduplicate_keyframes(
        validated_kfs, anim_name, bone_anim.bone_name,
        model_name, warnings,
    )
    stats["duplicates_removed"] = stats.get("duplicates_removed", 0) + (
        len(validated_kfs) - len(deduped)
    )

    # Detect snap-heavy channels
    snap_heavy_channels: List[str] = []
    for channel in CHANNELS:
        if _is_snap_heavy(deduped, channel):
            snap_heavy_channels.append(channel)

    stats["snap_heavy_channels"] = stats.get("snap_heavy_channels", 0) + len(
        snap_heavy_channels
    )

    return BoneAnimationIR(
        bone_name=bone_anim.bone_name,
        keyframes=deduped,
    )


def _validate_animation(
    anim: AnimationIR,
    model_name: str,
    warnings: List[str],
    stats: Dict[str, Any],
) -> Optional[AnimationIR]:
    """Validate one animation.

    Args:
        anim: The animation to validate.
        model_name: Model name for warning context.
        warnings: List to append warning messages to.
        stats: Dict to update with statistics.

    Returns:
        Validated AnimationIR (new instance), or None if the animation
        should be removed.
    """
    anim_name = anim.name

    # Validate each bone
    validated_bones: Dict[str, BoneAnimationIR] = {}
    for bone_name, bone_anim in anim.bones.items():
        try:
            validated_bone = _validate_bone(
                bone_anim, anim.length, anim_name,
                model_name, warnings, stats,
            )
            if validated_bone is not None:
                validated_bones[bone_name] = validated_bone
        except Exception as e:
            warnings.append(
                f"[{model_name}] {anim_name}/{bone_name}: "
                f"Validation error: {e}, skipping bone"
            )
            stats["bone_validation_errors"] = stats.get(
                "bone_validation_errors", 0
            ) + 1

    if not validated_bones:
        warnings.append(
            f"[{model_name}] {anim_name}: "
            f"No valid bones, removing animation"
        )
        stats["empty_animations_removed"] = stats.get(
            "empty_animations_removed", 0
        ) + 1
        return None

    return AnimationIR(
        name=anim.name,
        loop=anim.loop,
        length=anim.length,
        bones=validated_bones,
        period=anim.period,
    )


# ---------------------------------------------------------------------------
# Main validation function
# ---------------------------------------------------------------------------

def validate_animations(
    animations: Dict[str, AnimationIR],
    model_name: str = "",
) -> ValidationResult:
    """Validate all parsed animations.

    Checks:
    - NaN and Infinity values → remove keyframe with warning
    - Time < 0 → clamp to 0 with warning
    - Time > animation_length → clamp with warning
    - Rotation normalization to [-360, 360]
    - Duplicate time+channel keyframes → keep last, warn
    - Empty bones/animations → remove with warning
    - Detect snap-heavy channels (for interpolation override)

    All transforms produce new data — input is never mutated.

    Args:
        animations: Dict mapping animation_name -> AnimationIR, as produced
                    by the frontend parser.
        model_name: Optional model name for logging context.

    Returns:
        ValidationResult with cleaned animations, warnings, and stats.
    """
    warnings: List[str] = []
    stats: Dict[str, Any] = {
        "keyframes_removed_invalid": 0,
        "empty_bones_removed": 0,
        "empty_animations_removed": 0,
        "duplicates_removed": 0,
        "snap_heavy_channels": 0,
        "bone_validation_errors": 0,
        "rotations_normalized": 0,
    }
    validated: Dict[str, AnimationIR] = {}

    for anim_name, anim in animations.items():
        try:
            validated_anim = _validate_animation(
                anim, model_name, warnings, stats
            )
            if validated_anim is not None:
                validated[anim_name] = validated_anim
        except Exception as e:
            warnings.append(
                f"[{model_name}] {anim_name}: "
                f"Validation error: {e}, skipping animation"
            )
            stats["empty_animations_removed"] = stats.get(
                "empty_animations_removed", 0
            ) + 1

    # Count total validated keyframes
    total_kfs = 0
    for anim in validated.values():
        for bone_anim in anim.bones.values():
            total_kfs += len(bone_anim.keyframes)

    stats["total_keyframes"] = total_kfs

    return ValidationResult(
        animations=validated,
        warnings=warnings,
        stats=stats,
    )
