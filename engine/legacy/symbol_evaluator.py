#!/usr/bin/env python3
"""
AST Symbol Compiler — Symbol Evaluator
=========================================

Evaluate the SymbolTable at merged time points to produce KeyframeData
for export to .bbmodel format.

KEY ARCHITECTURE: The evaluator replaces THREE old pipeline stages:
  1. CarryForward — filling missing axis values at merged time points
  2. Interpolation — selecting per-keyframe interpolation modes
  3. SubFrameInsert — inserting intermediate keyframes

The evaluator does all three in one pass:
  1. Collect all merged time points across all curves
  2. Optionally insert sub-frame time points for smooth playback
  3. At each time point, evaluate all curves to get values
  4. Determine the interpolation mode for each keyframe from the
     segment it falls in (or starts)

This is fundamentally more correct than the old approach because:
  - Values are computed from the CORRECT interpolation (already compiled)
  - No chicken-and-egg problem with carry-forward before interpolation
  - Overshoot clamping is already built into the CatmullRom expressions
  - Sub-frame insertion uses the same AST evaluation (no re-interpolation)
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from core.types import (
    AXES,
    CHANNELS,
    AnimationIR,
    AxisValue,
    BoneAnimationIR,
    KeyframeData,
)
from .symbol_table import (
    Segment,
    SymbolCurve,
    SymbolKey,
    SymbolTable,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sub-frame insertion parameters
# ---------------------------------------------------------------------------

# Target frame interval for sub-frame insertion (seconds).
TARGET_FRAME_INTERVAL: float = 1.0 / 20.0

# Minimum time gap between keyframes to trigger sub-frame insertion.
MIN_GAP_FOR_INSERTION: float = 2.0 * TARGET_FRAME_INTERVAL

# Maximum number of sub-frames to insert in a single gap.
MAX_SUBFRAMES_PER_GAP: int = 50


# ---------------------------------------------------------------------------
# Merged time point collection
# ---------------------------------------------------------------------------

def _collect_merged_times(
    table: SymbolTable,
    anim_length: float,
    insert_subframes: bool = True,
) -> List[float]:
    """Collect all merged time points for evaluation.

    This includes:
      - All explicit keyframe times from all curves
      - Animation length (if > 0) for loop boundary
      - Sub-frame times inserted in large gaps (if enabled)

    Args:
        table: The SymbolTable to collect times from.
        anim_length: Animation length in seconds.
        insert_subframes: Whether to insert sub-frame time points.

    Returns:
        Sorted, deduplicated list of time points.
    """
    # Start with all keyframe times from all curves
    times: set = set()
    for curve in table.all_curves().values():
        for seg in curve.segments:
            times.add(round(seg.t_start, 8))
            times.add(round(seg.t_end, 8))

    # Add animation length as a time point (for loop boundary)
    if anim_length > 0:
        times.add(round(anim_length, 8))

    sorted_times = sorted(times)

    if not insert_subframes or not sorted_times:
        return sorted_times

    # Insert sub-frame time points in large gaps
    result: List[float] = []
    for i in range(len(sorted_times)):
        result.append(sorted_times[i])

        if i < len(sorted_times) - 1:
            dt = sorted_times[i + 1] - sorted_times[i]

            if dt >= MIN_GAP_FOR_INSERTION:
                num_sub = int(dt / TARGET_FRAME_INTERVAL) - 1
                num_sub = min(num_sub, MAX_SUBFRAMES_PER_GAP)

                for j in range(1, num_sub + 1):
                    t = sorted_times[i] + j * TARGET_FRAME_INTERVAL
                    # Snap to avoid floating-point drift
                    t = round(t, 8)
                    result.append(t)

    # Deduplicate and sort
    result = sorted(set(result))
    return result


# ---------------------------------------------------------------------------
# Per-bone evaluation
# ---------------------------------------------------------------------------

def _evaluate_bone_at_time(
    table: SymbolTable,
    bone_name: str,
    t: float,
    anim_length: float,
) -> Dict[str, Tuple[float, float, float, str, str, Dict[str, str]]]:
    """Evaluate all channels for one bone at a specific time.

    Args:
        table: The SymbolTable to evaluate.
        bone_name: Name of the bone.
        t: Time to evaluate at.
        anim_length: Animation length for boundary handling.

    Returns:
        Dict mapping channel -> (x, y, z, easing, interpolation, molang_dict).
        Only includes channels that have data for this bone.
    """
    result: Dict[str, Tuple[float, float, float, str, str, Dict[str, str]]] = {}

    for channel in CHANNELS:
        values: Dict[str, float] = {}
        molangs: Dict[str, str] = {}
        interpolations: Dict[str, str] = {}
        easings: Dict[str, str] = {}

        for axis in AXES:
            curve = table.get_curve(bone_name, channel, axis)

            if curve is None:
                # No curve for this axis → default 0.0
                values[axis] = 0.0
                continue

            # If the curve uses Molang, pass through the expression
            if curve.molang:
                molangs[axis] = curve.molang
                # For Molang, evaluate anyway (for the non-Molang axes)
                val = curve.evaluate_at_time(t)
                values[axis] = val
            else:
                val = curve.evaluate_at_time(t)
                values[axis] = val

            # Determine the interpolation mode at this time point.
            # We use the interpolation of the segment that STARTS at or
            # just before this time point. This matches Blockbench's behavior
            # where the interpolation mode is set on the "from" keyframe.
            interp = _get_interpolation_at_time(curve, t, anim_length)
            interpolations[axis] = interp

            # Easing — check if any keyframe at this time has a non-linear easing
            # For now, use "linear" as default (easing was already considered
            # during symbol compilation for interpolation selection)
            easings[axis] = "linear"

        if not values:
            continue

        x_val = values.get("x", 0.0)
        y_val = values.get("y", 0.0)
        z_val = values.get("z", 0.0)

        # Determine the best interpolation for this keyframe.
        # Use the most common interpolation across axes, preferring catmullrom
        # (since it's the most common for rotation).
        interp_counts: Dict[str, int] = {}
        for axis_interp in interpolations.values():
            interp_counts[axis_interp] = interp_counts.get(axis_interp, 0) + 1

        # Choose the interpolation with the highest count
        # In case of tie, prefer catmullrom > linear > hold
        best_interp = "linear"
        best_count = 0
        for interp_name in ["catmullrom", "linear", "hold", "constant"]:
            count = interp_counts.get(interp_name, 0)
            if count > best_count:
                best_count = count
                best_interp = interp_name

        # Best easing (prefer non-linear)
        best_easing = "linear"
        for axis_easing in easings.values():
            if axis_easing != "linear":
                best_easing = axis_easing
                break

        result[channel] = (x_val, y_val, z_val, best_easing, best_interp, molangs)

    return result


def _get_interpolation_at_time(
    curve: SymbolCurve,
    t: float,
    anim_length: float,
) -> str:
    """Get the interpolation mode for a curve at a specific time.

    The interpolation mode comes from the segment that contains this
    time point. For time points at segment boundaries, we use the
    outgoing segment (the one that starts at this time).

    Args:
        curve: The SymbolCurve.
        t: Time in seconds.
        anim_length: Animation length.

    Returns:
        Interpolation mode string.
    """
    if not curve.segments:
        return "linear"

    # Find the segment that starts at or just before t
    best_seg = curve.segments[0]
    for seg in curve.segments:
        if seg.t_start <= t + 1e-9:
            best_seg = seg
        else:
            break

    return best_seg.interpolation


# ---------------------------------------------------------------------------
# Main evaluation function
# ---------------------------------------------------------------------------

def evaluate_symbol_tables(
    symbol_tables: Dict[str, SymbolTable],
    model_name: str = "",
    stats: dict = None,
) -> Dict[str, AnimationIR]:
    """Evaluate symbol tables to produce AnimationIR for export.

    For each animation:
      1. Collect merged time points (including sub-frames)
      2. At each time point, evaluate all curves for all bones
      3. Produce KeyframeData with correct interpolation modes
      4. Return AnimationIR ready for .bbmodel export

    This replaces the old CarryForward + Interpolation + SubFrameInsert stages.

    Args:
        symbol_tables: Dict mapping animation_name -> SymbolTable.
        model_name: Model name for logging.
        stats: Dict to update with evaluation statistics.

    Returns:
        Dict mapping animation_name -> AnimationIR with evaluated keyframes.
    """
    if stats is None:
        stats = {}

    stats.setdefault("total_keyframes_evaluated", 0)
    stats.setdefault("subframes_inserted", 0)
    stats.setdefault("total_bones_evaluated", 0)

    result: Dict[str, AnimationIR] = {}

    for anim_name, table in symbol_tables.items():
        anim_length = table.length
        if anim_length <= 0 and table.period is not None:
            anim_length = table.period

        # Compute animation length from curves if not set
        if anim_length <= 0:
            all_times = table.all_keyframe_times()
            if all_times:
                anim_length = max(all_times)

        # Collect merged time points (with sub-frame insertion)
        explicit_times = table.all_keyframe_times()
        merged_times = _collect_merged_times(table, anim_length, insert_subframes=True)

        # Count sub-frames inserted
        subframe_count = len(merged_times) - len(set(round(t, 8) for t in explicit_times))
        stats["subframes_inserted"] = stats.get("subframes_inserted", 0) + max(0, subframe_count)

        # Build keyframes for each bone
        bones: Dict[str, BoneAnimationIR] = {}

        for bone_name in table.bone_names():
            keyframes: List[KeyframeData] = []

            for t in merged_times:
                channel_data = _evaluate_bone_at_time(
                    table, bone_name, t, anim_length,
                )

                for channel, (x_val, y_val, z_val, easing, interpolation, molangs) in channel_data.items():
                    is_molang = bool(molangs)
                    molang_x = molangs.get("x", "")
                    molang_y = molangs.get("y", "")
                    molang_z = molangs.get("z", "")

                    kf = KeyframeData(
                        time=t,
                        channel=channel,
                        x=AxisValue.explicit_val(x_val),
                        y=AxisValue.explicit_val(y_val),
                        z=AxisValue.explicit_val(z_val),
                        easing=easing,
                        interpolation=interpolation,
                        is_molang=is_molang,
                        molang_x=molang_x,
                        molang_y=molang_y,
                        molang_z=molang_z,
                    )
                    keyframes.append(kf)

            if keyframes:
                # Sort by time, then channel
                keyframes.sort(key=lambda kf: (kf.time, kf.channel))
                bones[bone_name] = BoneAnimationIR(
                    bone_name=bone_name,
                    keyframes=keyframes,
                )

                stats["total_keyframes_evaluated"] = stats.get(
                    "total_keyframes_evaluated", 0
                ) + len(keyframes)

        stats["total_bones_evaluated"] = stats.get("total_bones_evaluated", 0) + len(bones)

        # Compute animation length from keyframes if still 0
        if anim_length <= 0:
            all_times = []
            for bone_anim in bones.values():
                for kf in bone_anim.keyframes:
                    all_times.append(kf.time)
            if all_times:
                anim_length = max(all_times)

        result[anim_name] = AnimationIR(
            name=table.animation_name,
            loop=table.loop,
            length=anim_length,
            bones=bones,
            period=table.period,
        )

    logger.info(
        "[%s] SymbolEvaluate: %d animations, %d keyframes evaluated, "
        "%d sub-frames inserted, %d bones",
        model_name, len(result),
        stats.get("total_keyframes_evaluated", 0),
        stats.get("subframes_inserted", 0),
        stats.get("total_bones_evaluated", 0),
    )

    return result
