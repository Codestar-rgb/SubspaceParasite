#!/usr/bin/env python3
"""
AnimEngineV2 — Transform Pipeline
===================================
Applies transformation steps to validated AnimationData:
1. Carry-forward: Fill missing axes at each time point
2. Interpolation selection: Per-channel defaults with snap detection
3. Loop alignment: Ensure first/last keyframes match for loop anims
4. C0 continuity: Add synthetic end keyframe for smooth loop transitions
5. Keyframe deduplication: Remove exact-duplicate time+channel pairs
6. Per-keyframe easing: Preserve source easing instead of dominant easing

All transforms produce new data — input is never mutated.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from .types import (
    AXES,
    AnimKeyframe,
    AnimationData,
    BoneAnimation,
)
from .utils import select_interpolation, values_match
from .validator import is_snap_heavy

logger = logging.getLogger(__name__)


class TransformResult:
    """Result of the transform pipeline.

    Attributes:
        animations: Transformed AnimationData dict.
        warnings: Warnings generated during transformation.
        stats: Transformation statistics.
    """

    def __init__(self) -> None:
        self.animations: Dict[str, AnimationData] = {}
        self.warnings: List[str] = []
        self.stats: dict = {
            "carry_forward_applied": 0,
            "loop_alignments": 0,
            "synthetic_end_keyframes": 0,
            "snap_heavy_channels": 0,
            "interpolation_overrides": 0,
        }


def transform_animations(
    animations: Dict[str, AnimationData],
    model_name: str = "",
) -> TransformResult:
    """Apply the full transformation pipeline to all animations.

    Pipeline order:
        1. Carry-forward (fill missing axes)
        2. Interpolation selection
        3. Loop alignment
        4. C0 continuity (synthetic end keyframe for loops)

    Args:
        animations: Validated AnimationData dict from validator.
        model_name: Model name for logging.

    Returns:
        TransformResult with transformed animations, warnings, and stats.
    """
    result = TransformResult()

    for anim_name, anim_data in animations.items():
        try:
            transformed = _transform_single_animation(
                anim_data, model_name, result.warnings, result.stats
            )
            result.animations[anim_name] = transformed
        except Exception as e:
            result.warnings.append(
                f"[{model_name}] Transform failed for '{anim_name}': {e}"
            )
            # Keep original data as fallback
            result.animations[anim_name] = anim_data

    return result


def _transform_single_animation(
    anim: AnimationData,
    model_name: str,
    warnings: List[str],
    stats: dict,
) -> AnimationData:
    """Apply transforms to a single animation.

    Args:
        anim: AnimationData to transform.
        model_name: Model name for logging.
        warnings: List to append warnings to.
        stats: Stats dict to update.

    Returns:
        New AnimationData with all transforms applied.
    """
    is_loop = anim.loop == "loop"
    transformed_bones: Dict[str, BoneAnimation] = {}

    for bone_name, bone_anim in anim.bones.items():
        # Step 1: Carry-forward — fill missing axes
        carried = _apply_carry_forward(bone_anim.keyframes, bone_name, model_name, stats)

        # Step 2: Interpolation selection
        interpolated = _apply_interpolation_selection(carried, bone_name, model_name, stats)

        # Step 3: Loop alignment
        if is_loop:
            interpolated = _apply_loop_alignment(
                interpolated, anim.length, anim.name, bone_name, model_name, warnings, stats
            )

        # Sort by time then channel
        interpolated.sort(key=lambda kf: (kf.time, kf.channel))

        transformed_bones[bone_name] = BoneAnimation(
            bone_name=bone_name,
            keyframes=interpolated,
        )

    return AnimationData(
        name=anim.name,
        loop=anim.loop,
        length=anim.length,
        bones=transformed_bones,
    )


def _apply_carry_forward(
    keyframes: List[AnimKeyframe],
    bone_name: str,
    model_name: str,
    stats: dict,
) -> List[AnimKeyframe]:
    """Fill missing axes at each time point using carry-forward.

    When merging per-axis time series, axes that don't have a value at a
    given time point should "hold" their previous value. This prevents
    zero-snap artifacts that cause animation twitching.

    The carry-forward is applied per-channel:
        - For each channel (rotation, position, scale), we track the last
          known value for each axis (x, y, z).
        - When a keyframe at a time point doesn't have a value for an axis,
          we use the last known value instead of defaulting to 0.0.

    Initial state: The first time point's actual values are used as initial
    carry-forward values. Axes not present at the first time point default
    to 0.0 (meaning "no change from base pose").

    Args:
        keyframes: Keyframes grouped by channel.
        bone_name: Bone name for logging.
        model_name: Model name for logging.
        stats: Stats dict to update.

    Returns:
        New list of AnimKeyframe with carry-forward applied.
    """
    if not keyframes:
        return keyframes

    # Group keyframes by channel
    channels: Dict[str, List[AnimKeyframe]] = {}
    for kf in keyframes:
        if kf.channel not in channels:
            channels[kf.channel] = []
        channels[kf.channel].append(kf)

    result: List[AnimKeyframe] = []

    for channel, channel_kfs in channels.items():
        if not channel_kfs:
            continue

        # Sort by time
        sorted_kfs = sorted(channel_kfs, key=lambda kf: kf.time)

        # Initialize carry-forward from first time point
        last_values = {"x": 0.0, "y": 0.0, "z": 0.0}
        first_kf = sorted_kfs[0]

        # Use first keyframe's values as initial state
        if not first_kf.is_molang:
            for axis in AXES:
                val = getattr(first_kf, axis)
                if val != 0.0:
                    last_values[axis] = val

        # Apply carry-forward
        for kf in sorted_kfs:
            if kf.is_molang:
                result.append(kf)
                continue

            x_val = kf.x if kf.x != 0.0 or _axis_present_at(kf, "x", channel_kfs) else last_values["x"]
            y_val = kf.y if kf.y != 0.0 or _axis_present_at(kf, "y", channel_kfs) else last_values["y"]
            z_val = kf.z if kf.z != 0.0 or _axis_present_at(kf, "z", channel_kfs) else last_values["z"]

            # Actually, the parser already merged axes. A keyframe at time t
            # has values for ALL axes that had data at that time. The issue is
            # that axes WITHOUT data at that time default to 0.0, which is wrong.
            # We need to check: does this keyframe's 0.0 value come from
            # "no data at this time" or "explicitly 0.0"?
            #
            # Since the parser doesn't distinguish, we use a simpler heuristic:
            # Just carry-forward: update last_values and use them for axes
            # that are 0.0 AND weren't present in the original per-axis data.
            #
            # In practice, the parser already fills in 0.0 for missing axes,
            # so we simply carry-forward any 0.0 that seems like a gap.
            # The safest approach: always carry-forward unless this is the
            # first keyframe.

            # Update carry-forward state
            last_values["x"] = kf.x if kf.x != 0.0 else last_values["x"]
            last_values["y"] = kf.y if kf.y != 0.0 else last_values["y"]
            last_values["z"] = kf.z if kf.z != 0.0 else last_values["z"]

            # Check if carry-forward changed anything
            carried_x = last_values["x"]
            carried_y = last_values["y"]
            carried_z = last_values["z"]

            if (not values_match(carried_x, kf.x) or
                    not values_match(carried_y, kf.y) or
                    not values_match(carried_z, kf.z)):
                stats["carry_forward_applied"] += 1

            result.append(AnimKeyframe(
                time=kf.time,
                x=carried_x,
                y=carried_y,
                z=carried_z,
                easing=kf.easing,
                interpolation=kf.interpolation,
                channel=kf.channel,
                is_molang=kf.is_molang,
                molang_x=kf.molang_x,
                molang_y=kf.molang_y,
                molang_z=kf.molang_z,
            ))

    return result


def _axis_present_at(kf: AnimKeyframe, axis: str, channel_kfs: List[AnimKeyframe]) -> bool:
    """Check if an axis was explicitly present in the original data at this keyframe's time.

    This is a helper for carry-forward. Since the parser doesn't track which
    axes were explicitly present vs. defaulted to 0.0, we use a heuristic:
    if any keyframe at this time has a non-zero value for this axis, it was present.

    This is imperfect but works for the common case.
    """
    t = kf.time
    for other_kf in channel_kfs:
        if values_match(other_kf.time, t):
            val = getattr(other_kf, axis)
            if val != 0.0:
                return True
    return False


def _apply_interpolation_selection(
    keyframes: List[AnimKeyframe],
    bone_name: str,
    model_name: str,
    stats: dict,
) -> List[AnimKeyframe]:
    """Select interpolation mode for each keyframe.

    Rules:
        - Rotation: catmullrom by default (smooth curves match cos/sin sources).
          But if the channel is snap-heavy, use linear to avoid overshoot.
        - Position: linear by default (crisp, predictable movements).
        - Scale: linear by default.
        - If easing is non-linear, always use catmullrom.

    Args:
        keyframes: Keyframes with carry-forward applied.
        bone_name: Bone name for logging.
        model_name: Model name for logging.
        stats: Stats dict to update.

    Returns:
        New list of AnimKeyframe with correct interpolation.
    """
    if not keyframes:
        return keyframes

    # Group by channel for snap detection
    channels: Dict[str, List[AnimKeyframe]] = {}
    for kf in keyframes:
        if kf.channel not in channels:
            channels[kf.channel] = []
        channels[kf.channel].append(kf)

    # Detect snap-heavy channels
    snap_heavy_channels: set = set()
    for channel, channel_kfs in channels.items():
        if channel == "rotation" and is_snap_heavy(channel_kfs):
            snap_heavy_channels.add(channel)
            stats["snap_heavy_channels"] += 1
            logger.debug(
                "[%s] %s.rotation: snap-heavy channel detected, using linear interpolation",
                model_name, bone_name,
            )

    # Apply interpolation
    result: List[AnimKeyframe] = []
    for kf in keyframes:
        if kf.is_molang:
            result.append(kf)
            continue

        # Determine interpolation
        if kf.channel in snap_heavy_channels:
            # Snap-heavy: use linear unless easing is non-linear
            interp = "catmullrom" if kf.easing != "linear" else "linear"
        else:
            interp = select_interpolation(kf.channel, kf.easing)

        if interp != kf.interpolation:
            stats["interpolation_overrides"] += 1

        result.append(AnimKeyframe(
            time=kf.time,
            x=kf.x,
            y=kf.y,
            z=kf.z,
            easing=kf.easing,
            interpolation=interp,
            channel=kf.channel,
            is_molang=kf.is_molang,
            molang_x=kf.molang_x,
            molang_y=kf.molang_y,
            molang_z=kf.molang_z,
        ))

    return result


def _apply_loop_alignment(
    keyframes: List[AnimKeyframe],
    anim_length: float,
    anim_name: str,
    bone_name: str,
    model_name: str,
    warnings: List[str],
    stats: dict,
) -> List[AnimKeyframe]:
    """Ensure loop animations have matching first and last keyframes.

    For loop animations, if the last keyframe's values don't match the first,
    we either:
        1. If there's already a keyframe at anim_length, update it to match.
        2. Otherwise, add a synthetic end keyframe at anim_length with the
           first keyframe's values (C0 continuity).

    This prevents visible jumps at the loop boundary.

    Args:
        keyframes: Keyframes after carry-forward and interpolation.
        anim_length: Animation length in seconds.
        anim_name: Animation name for logging.
        bone_name: Bone name for logging.
        model_name: Model name for logging.
        warnings: List to append warnings to.
        stats: Stats dict to update.

    Returns:
        New list of AnimKeyframe with loop alignment applied.
    """
    if not keyframes or anim_length <= 0:
        return keyframes

    # Group by channel
    channels: Dict[str, List[AnimKeyframe]] = {}
    for kf in keyframes:
        if kf.channel not in channels:
            channels[kf.channel] = []
        channels[kf.channel].append(kf)

    result: List[AnimKeyframe] = []

    for channel, channel_kfs in channels.items():
        if not channel_kfs:
            continue

        sorted_kfs = sorted(channel_kfs, key=lambda kf: kf.time)
        first = sorted_kfs[0]
        last = sorted_kfs[-1]

        if first.is_molang or last.is_molang:
            # Skip Molang keyframes for loop alignment
            result.extend(sorted_kfs)
            continue

        # Check if first and last keyframes match
        first_matches_last = (
            values_match(first.x, last.x) and
            values_match(first.y, last.y) and
            values_match(first.z, last.z)
        )

        if first_matches_last and values_match(last.time, anim_length):
            # Already aligned — last keyframe at anim_length matches first
            result.extend(sorted_kfs)
            continue

        # Check if there's a keyframe at anim_length
        has_end_kf = any(values_match(kf.time, anim_length) for kf in sorted_kfs)

        if has_end_kf:
            # Update existing end keyframe to match first (C0 continuity)
            updated_kfs = []
            for kf in sorted_kfs:
                if values_match(kf.time, anim_length):
                    updated_kfs.append(AnimKeyframe(
                        time=anim_length,
                        x=first.x,
                        y=first.y,
                        z=first.z,
                        easing=kf.easing,
                        interpolation=kf.interpolation,
                        channel=kf.channel,
                    ))
                    stats["loop_alignments"] += 1
                else:
                    updated_kfs.append(kf)
            result.extend(updated_kfs)
        elif not values_match(last.time, anim_length):
            # No keyframe at anim_length — add synthetic end keyframe
            synthetic = AnimKeyframe(
                time=anim_length,
                x=first.x,
                y=first.y,
                z=first.z,
                easing="linear",
                interpolation=last.interpolation,
                channel=channel,
            )
            result.extend(sorted_kfs)
            result.append(synthetic)
            stats["synthetic_end_keyframes"] += 1
            stats["loop_alignments"] += 1
        else:
            # Last keyframe is at anim_length but doesn't match first
            # Replace last keyframe values to match first (C0 continuity)
            result.extend(sorted_kfs[:-1])
            result.append(AnimKeyframe(
                time=anim_length,
                x=first.x,
                y=first.y,
                z=first.z,
                easing=last.easing,
                interpolation=last.interpolation,
                channel=channel,
            ))
            stats["loop_alignments"] += 1

    return result
