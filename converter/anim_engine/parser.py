#!/usr/bin/env python3
"""
AnimEngineV2 — Parser
======================
Parses GeckoLib animation.json into the intermediate AnimationData format.

Input:  Raw GeckoLib animation.json dict
Output: Dict[str, AnimationData] — one AnimationData per animation

This stage is responsible for:
- Extracting per-axis time series from the raw JSON
- Handling all GeckoLib value types (plain number, {"vector": N, "easing": S}, Molang string)
- Merging per-axis data into unified keyframes at each unique time point
- Preserving Molang expressions as special keyframe markers

This stage does NOT:
- Validate values (see validator.py)
- Apply carry-forward (see transform.py)
- Select interpolation (see transform.py)
- Generate UUIDs or bbmodel dicts (see serializer.py)
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from .types import (
    AXES,
    AnimKeyframe,
    AnimationData,
    BoneAnimation,
    VALID_LOOP_MODES,
)
from .utils import parse_geckolib_value

logger = logging.getLogger(__name__)


def parse_animations(anim_json: dict, model_name: str = "") -> Dict[str, AnimationData]:
    """Parse a GeckoLib animation.json into AnimationData objects.

    Args:
        anim_json: The raw animation.json dict with "animations" key.
        model_name: Optional model name for logging context.

    Returns:
        Dict mapping animation_name -> AnimationData.
    """
    result: Dict[str, AnimationData] = {}
    animations = anim_json.get("animations", {})

    for anim_name, anim_data in animations.items():
        try:
            parsed = _parse_single_animation(anim_name, anim_data, model_name)
            result[anim_name] = parsed
        except Exception as e:
            logger.warning(
                "[%s] Failed to parse animation '%s': %s",
                model_name, anim_name, e,
            )
            continue

    return result


def _parse_single_animation(
    anim_name: str, anim_data: dict, model_name: str
) -> AnimationData:
    """Parse one animation entry from the JSON.

    Args:
        anim_name: Animation identifier (e.g. "animation.kirin.idle").
        anim_data: The animation's dict with loop, animation_length, bones, etc.
        model_name: Model name for logging.

    Returns:
        AnimationData instance.
    """
    loop_mode = anim_data.get("loop", "once")
    if loop_mode not in VALID_LOOP_MODES:
        logger.debug(
            "[%s] Unknown loop mode '%s' in '%s', defaulting to 'once'",
            model_name, loop_mode, anim_name,
        )
        loop_mode = "once"

    anim_length = float(anim_data.get("animation_length", 0.0))
    bones_data = anim_data.get("bones", {})

    bones: Dict[str, BoneAnimation] = {}

    for bone_name, bone_anim in bones_data.items():
        try:
            bone_anim_data = _parse_bone_animation(bone_name, bone_anim, model_name)
            if bone_anim_data.keyframes:
                bones[bone_name] = bone_anim_data
        except Exception as e:
            logger.warning(
                "[%s] Failed to parse bone '%s' in '%s': %s",
                model_name, bone_name, anim_name, e,
            )
            continue

    return AnimationData(
        name=anim_name,
        loop=loop_mode,
        length=anim_length,
        bones=bones,
    )


def _parse_bone_animation(
    bone_name: str, bone_anim: dict, model_name: str
) -> BoneAnimation:
    """Parse one bone's animation data across all channels.

    Args:
        bone_name: Name of the bone.
        bone_anim: Dict with "rotation", "position", "scale" keys.
        model_name: Model name for logging.

    Returns:
        BoneAnimation with all keyframes (not yet sorted or transformed).
    """
    keyframes: List[AnimKeyframe] = []

    for channel in ("rotation", "position", "scale"):
        channel_data = bone_anim.get(channel, {})
        if not channel_data:
            continue

        channel_keyframes = _parse_channel(channel_data, channel, bone_name, model_name)
        keyframes.extend(channel_keyframes)

    # Sort by time, then channel for deterministic ordering
    keyframes.sort(key=lambda kf: (kf.time, kf.channel))

    return BoneAnimation(bone_name=bone_name, keyframes=keyframes)


def _parse_channel(
    channel_data: dict, channel: str, bone_name: str, model_name: str
) -> List[AnimKeyframe]:
    """Parse one channel (rotation/position/scale) of one bone.

    The channel data is per-axis:
        {
          "x": { "time_str": value_or_object, ... },
          "y": { "time_str": value_or_object, ... },
          "z": { "time_str": value_or_object, ... }
        }

    Where value_or_object is either:
        - A plain number
        - A string (Molang expression)
        - An object: {"vector": number, "easing": "easeOutSine"}

    We merge per-axis keyframes into unified keyframes at each unique time point.
    Axes without a value at a given time are left as 0.0 (carry-forward is
    applied in the transform stage, not here).

    Args:
        channel_data: Per-axis time series dict.
        channel: "rotation", "position", or "scale".
        bone_name: Name of the bone (for logging).
        model_name: Model name (for logging).

    Returns:
        List of AnimKeyframe at each unique time point.
    """
    if not channel_data:
        return []

    # Step 1: Collect all time points and axis values
    # time_float -> {axis: (value, easing)}  or  {axis: molang_string}
    time_points: Dict[float, dict] = {}

    # Track Molang axes
    # axis -> molang_expression
    molang_axes: Dict[str, str] = {}

    for axis in AXES:
        axis_data = channel_data.get(axis)
        if axis_data is None:
            continue

        # Molang: axis value is a string (not a time-series dict)
        if isinstance(axis_data, str):
            molang_axes[axis] = axis_data
            continue

        # Time-series dict: {"0.0": value, "1.0": value, ...}
        if not isinstance(axis_data, dict):
            logger.debug(
                "[%s] Unexpected axis data type for %s.%s.%s: %s",
                model_name, bone_name, channel, axis, type(axis_data).__name__,
            )
            continue

        for time_str, value in axis_data.items():
            try:
                t = float(time_str)
            except (ValueError, TypeError):
                logger.warning(
                    "[%s] Invalid time '%s' in %s.%s.%s, skipping",
                    model_name, time_str, bone_name, channel, axis,
                )
                continue

            if t not in time_points:
                time_points[t] = {}

            try:
                val, easing = parse_geckolib_value(value)
                time_points[t][axis] = (val, easing)
            except ValueError:
                # Molang expression at a specific time point
                molang_str = str(value)
                time_points[t][axis] = molang_str
            except TypeError as e:
                logger.warning(
                    "[%s] Unrecognized value in %s.%s.%s at t=%s: %s",
                    model_name, bone_name, channel, axis, time_str, e,
                )
                continue

    if not time_points and not molang_axes:
        return []

    # Step 2: Handle global Molang axes (not time-varying)
    # If an axis has a global Molang string, we create a single keyframe at t=0
    # with the Molang expression. This is handled specially in serialization.
    if molang_axes and not time_points:
        # All axes are Molang — create a single keyframe at t=0
        kf = AnimKeyframe(
            time=0.0,
            channel=channel,
            is_molang=True,
            molang_x=molang_axes.get("x", ""),
            molang_y=molang_axes.get("y", ""),
            molang_z=molang_axes.get("z", ""),
        )
        return [kf]

    # Step 3: Build unified keyframes from merged time points
    keyframes: List[AnimKeyframe] = []
    sorted_times = sorted(time_points.keys())

    for t in sorted_times:
        axis_data = time_points[t]

        # Extract values and easing for numeric axes
        x_val, y_val, z_val = 0.0, 0.0, 0.0
        # Track per-keyframe easing — use the most specific (non-linear) easing
        per_axis_easings: Dict[str, str] = {}

        molang_x, molang_y, molang_z = "", "", ""
        has_molang_at_time = False

        for axis in AXES:
            if axis in axis_data:
                entry = axis_data[axis]
                if isinstance(entry, str):
                    # Molang at this time point
                    has_molang_at_time = True
                    if axis == "x":
                        molang_x = entry
                    elif axis == "y":
                        molang_y = entry
                    elif axis == "z":
                        molang_z = entry
                elif isinstance(entry, tuple):
                    val, easing = entry
                    if axis == "x":
                        x_val = val
                    elif axis == "y":
                        y_val = val
                    elif axis == "z":
                        z_val = val
                    if easing != "linear":
                        per_axis_easings[axis] = easing

        # Use first non-linear easing as the keyframe easing
        # (This is a simplification; per-keyframe easing is preserved in data_points)
        best_easing = "linear"
        for axis in AXES:
            if axis in per_axis_easings:
                best_easing = per_axis_easings[axis]
                break

        # Also incorporate global Molang axes if not already set at this time
        if "x" not in axis_data and "x" in molang_axes:
            molang_x = molang_axes["x"]
            has_molang_at_time = True
        if "y" not in axis_data and "y" in molang_axes:
            molang_y = molang_axes["y"]
            has_molang_at_time = True
        if "z" not in axis_data and "z" in molang_axes:
            molang_z = molang_axes["z"]
            has_molang_at_time = True

        kf = AnimKeyframe(
            time=t,
            x=x_val,
            y=y_val,
            z=z_val,
            easing=best_easing,
            interpolation="catmullrom" if best_easing != "linear" else "linear",
            channel=channel,
            is_molang=has_molang_at_time or bool(molang_axes),
            molang_x=molang_x,
            molang_y=molang_y,
            molang_z=molang_z,
        )
        keyframes.append(kf)

    return keyframes
