#!/usr/bin/env python3
"""
Super Architecture — Loop Aligner
===================================

Ensure loop animations have matching first and last keyframes.

For loop animations, the last keyframe should match the first to
prevent visible jumps at the loop boundary.

Algorithm per channel:
  1. If first and last keyframes already match → done
  2. If there's a keyframe at anim_length → update it to match first
  3. If no keyframe at anim_length → add synthetic end keyframe
  4. For rotation channels, use quaternion shortest-path to ensure
     the interpolation takes the shortest rotation path

IMPROVEMENT over old engine:
The old engine only checked value matching. The new engine also
considers the derivative (velocity) at the loop boundary. If the
velocity doesn't match, we add a short "blend" keyframe near
the end to smooth the transition.

Actually, for simplicity and correctness, we'll implement the value-matching
approach first, with quaternion-based shortest-path for rotations.

All transforms produce new data — input is never mutated.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.types import (
    AXES,
    CHANNELS,
    AnimationIR,
    AxisValue,
    BoneAnimationIR,
    KeyframeData,
)
from core.math_utils import values_match
from core.quaternion import euler_shortest_path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Time comparison tolerance
# ---------------------------------------------------------------------------

# Tolerance for matching keyframe times (in seconds).
# Keyframes within this tolerance of anim_length are considered "at the end."
TIME_TOLERANCE: float = 1e-4

# Tolerance for value matching at loop boundary.
VALUE_TOLERANCE: float = 1e-4


# ---------------------------------------------------------------------------
# Per-channel loop alignment
# ---------------------------------------------------------------------------

def _align_channel_loop(
    keyframes: List[KeyframeData],
    channel: str,
    anim_length: float,
    bone_name: str,
    anim_name: str,
    model_name: str,
    stats: dict,
) -> List[KeyframeData]:
    """Align the first and last keyframes of one channel for seamless looping.

    For loop animations:
      1. If first and last keyframes already match → done
      2. If there's a keyframe at anim_length → update it to match first
      3. If no keyframe at anim_length → add synthetic end keyframe
      4. For rotation channels, use quaternion shortest-path

    Args:
        keyframes: All keyframes for this bone (sorted by time, then channel).
        channel: The channel to align ("rotation", "position", "scale").
        anim_length: Animation length in seconds.
        bone_name: Bone name for logging.
        anim_name: Animation name for logging.
        model_name: Model name for logging.
        stats: Dict to update with alignment statistics.

    Returns:
        New list of keyframes with loop alignment applied.
    """
    # Filter to keyframes for this channel only
    channel_kfs = [kf for kf in keyframes if kf.channel == channel]

    if len(channel_kfs) < 2:
        # Not enough keyframes to align
        return list(keyframes)

    first_kf = channel_kfs[0]
    last_kf = channel_kfs[-1]

    # Check if the first and last keyframes already match
    first_values = [first_kf.x.value, first_kf.y.value, first_kf.z.value]
    last_values = [last_kf.x.value, last_kf.y.value, last_kf.z.value]

    values_already_match = all(
        values_match(f, l, VALUE_TOLERANCE)
        for f, l in zip(first_values, last_values)
    )

    # Check if there's already a keyframe at anim_length
    end_kf_idx: Optional[int] = None
    if anim_length > 0:
        for i, kf in enumerate(channel_kfs):
            if abs(kf.time - anim_length) < TIME_TOLERANCE:
                end_kf_idx = i
                break

    # If values already match and last keyframe is at anim_length, done
    if values_already_match and end_kf_idx is not None:
        return list(keyframes)

    # If values match but no keyframe at anim_length, we still need one
    # for Blockbench to know the animation duration
    if values_already_match and anim_length > 0 and end_kf_idx is None:
        # Add synthetic end keyframe matching the first
        synthetic = KeyframeData(
            time=anim_length,
            channel=channel,
            x=AxisValue.explicit_val(first_kf.x.value),
            y=AxisValue.explicit_val(first_kf.y.value),
            z=AxisValue.explicit_val(first_kf.z.value),
            easing=first_kf.easing,
            interpolation=first_kf.interpolation,
            is_molang=first_kf.is_molang,
            molang_x=first_kf.molang_x,
            molang_y=first_kf.molang_y,
            molang_z=first_kf.molang_z,
        )

        # Build result: insert synthetic end keyframe
        result = []
        for kf in keyframes:
            result.append(kf)
        result.append(synthetic)
        result.sort(key=lambda k: (k.time, k.channel))

        stats["synthetic_end_keyframes"] = stats.get(
            "synthetic_end_keyframes", 0
        ) + 1
        stats["alignments"] = stats.get("alignments", 0) + 1

        return result

    # Values don't match — need to align
    # For rotation channels, use quaternion shortest-path to find the
    # closest equivalent of the first keyframe's values
    if channel == "rotation":
        # Use euler_shortest_path to find the closest representation
        # of the first keyframe's rotation relative to the last
        rx_adj, ry_adj, rz_adj = euler_shortest_path(
            last_kf.x.value, last_kf.y.value, last_kf.z.value,
            first_kf.x.value, first_kf.y.value, first_kf.z.value,
        )
        target_x = rx_adj
        target_y = ry_adj
        target_z = rz_adj
    else:
        # For position and scale, just use the first keyframe's values directly
        target_x = first_kf.x.value
        target_y = first_kf.y.value
        target_z = first_kf.z.value

    # Create the aligned end keyframe
    if end_kf_idx is not None:
        # Update existing keyframe at anim_length
        existing_kf = channel_kfs[end_kf_idx]
        aligned_end = KeyframeData(
            time=existing_kf.time,
            channel=channel,
            x=AxisValue.explicit_val(target_x),
            y=AxisValue.explicit_val(target_y),
            z=AxisValue.explicit_val(target_z),
            easing=existing_kf.easing,
            interpolation=existing_kf.interpolation,
            is_molang=existing_kf.is_molang,
            molang_x=existing_kf.molang_x,
            molang_y=existing_kf.molang_y,
            molang_z=existing_kf.molang_z,
        )

        # Replace the existing end keyframe
        result = []
        for kf in keyframes:
            if kf.channel == channel and abs(kf.time - anim_length) < TIME_TOLERANCE:
                result.append(aligned_end)
            else:
                result.append(kf)

        stats["alignments"] = stats.get("alignments", 0) + 1
        return result
    else:
        # Add synthetic end keyframe at anim_length
        if anim_length <= 0:
            # Can't align without a known animation length
            return list(keyframes)

        synthetic = KeyframeData(
            time=anim_length,
            channel=channel,
            x=AxisValue.explicit_val(target_x),
            y=AxisValue.explicit_val(target_y),
            z=AxisValue.explicit_val(target_z),
            easing=first_kf.easing,
            interpolation=first_kf.interpolation,
            is_molang=first_kf.is_molang,
            molang_x=first_kf.molang_x,
            molang_y=first_kf.molang_y,
            molang_z=first_kf.molang_z,
        )

        result = list(keyframes)
        result.append(synthetic)
        result.sort(key=lambda k: (k.time, k.channel))

        stats["synthetic_end_keyframes"] = stats.get(
            "synthetic_end_keyframes", 0
        ) + 1
        stats["alignments"] = stats.get("alignments", 0) + 1

        return result


# ---------------------------------------------------------------------------
# Per-bone loop alignment
# ---------------------------------------------------------------------------

def _align_bone_loop(
    bone_anim: BoneAnimationIR,
    anim_length: float,
    is_loop: bool,
    anim_name: str,
    model_name: str,
    stats: dict,
) -> BoneAnimationIR:
    """Apply loop alignment to all channels of one bone.

    Only applies to loop animations. Non-loop animations are returned
    unchanged.

    Args:
        bone_anim: The bone's animation data.
        anim_length: Animation length in seconds.
        is_loop: True if this is a loop animation.
        anim_name: Animation name for logging.
        model_name: Model name for logging.
        stats: Dict to update with alignment statistics.

    Returns:
        New BoneAnimationIR with loop alignment applied.
    """
    if not is_loop or not bone_anim.keyframes:
        return bone_anim

    keyframes = bone_anim.keyframes

    # Apply alignment to each channel
    for channel in CHANNELS:
        channel_kfs = [kf for kf in keyframes if kf.channel == channel]
        if len(channel_kfs) < 2:
            continue

        keyframes = _align_channel_loop(
            keyframes, channel, anim_length,
            bone_anim.bone_name, anim_name, model_name, stats,
        )

    return BoneAnimationIR(
        bone_name=bone_anim.bone_name,
        keyframes=keyframes,
    )


# ---------------------------------------------------------------------------
# Main loop alignment function
# ---------------------------------------------------------------------------

def align_loops(
    animations: Dict[str, AnimationIR],
    model_name: str = "",
    stats: dict = None,
) -> Dict[str, AnimationIR]:
    """Ensure loop animations have matching first and last keyframes.

    For loop animations, the last keyframe should match the first to
    prevent visible jumps at the loop boundary.

    Algorithm per channel:
    1. If first and last keyframes already match → done
    2. If there's a keyframe at anim_length → update it to match first
    3. If no keyframe at anim_length → add synthetic end keyframe
    4. For rotation channels, use quaternion shortest-path to ensure
       the interpolation takes the shortest rotation path

    IMPROVEMENT over old engine:
    The old engine only checked value matching. The new engine also
    considers the derivative (velocity) at the loop boundary. If the
    velocity doesn't match, we add a short "blend" keyframe near
    the end to smooth the transition.

    Actually, for simplicity and correctness, we'll implement the value-matching
    approach first, with quaternion-based shortest-path for rotations.

    Args:
        animations: Dict mapping animation_name -> AnimationIR.
        model_name: Optional model name for logging context.
        stats: Optional dict to update with alignment statistics.

    Returns:
        New dict of animations with loop alignment applied.
    """
    if stats is None:
        stats = {}

    stats.setdefault("alignments", 0)
    stats.setdefault("synthetic_end_keyframes", 0)

    result: Dict[str, AnimationIR] = {}

    for anim_name, anim in animations.items():
        is_loop = anim.loop == "loop"
        anim_length = anim.length

        # If animation has no explicit length but has a period, use the period
        if anim_length <= 0 and anim.period is not None:
            anim_length = anim.period

        # If still no length, compute from keyframe times
        if anim_length <= 0 and is_loop:
            all_times: List[float] = []
            for bone_anim in anim.bones.values():
                for kf in bone_anim.keyframes:
                    all_times.append(kf.time)
            if all_times:
                anim_length = max(all_times)

        new_bones: Dict[str, BoneAnimationIR] = {}

        for bone_name, bone_anim in anim.bones.items():
            try:
                new_bone = _align_bone_loop(
                    bone_anim, anim_length, is_loop,
                    anim_name, model_name, stats,
                )
                new_bones[bone_name] = new_bone
            except Exception as e:
                logger.warning(
                    "[%s] Loop alignment error for %s/%s: %s, keeping original",
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
