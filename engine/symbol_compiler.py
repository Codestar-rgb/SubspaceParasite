#!/usr/bin/env python3
"""
AST Symbol Compiler — Build Symbol Table from Validated IR
============================================================

This module builds the SymbolTable from validated AnimationIR data.

KEY ARCHITECTURE: Instead of the old pipeline:
  Validate → CarryForward (uses CatmullRom to fill) → ... → Interpolation (selects mode)

We now do:
  Validate → SymbolCompile (selects interpolation FIRST, builds AST) → ... → Evaluate

The SymbolCompiler:
  1. Extracts per-axis time series from KeyframeData
  2. Selects per-segment interpolation mode BEFORE building expressions
  3. Builds AST Expression nodes with correct interpolation + overshoot clamping
  4. Stores everything in a SymbolTable for later evaluation

This eliminates the chicken-and-egg problem where carry-forward needed
interpolation before the interpolation stage had run.

Interpolation Selection Rules (per segment):
  - If easing is non-linear → catmullrom
  - If channel is position or scale → linear (default)
  - If channel is rotation:
    - If snap-heavy channel → linear
    - If large time gap (> 0.5s) with slow angular velocity → linear
    - If large time gap with fast angular velocity → catmullrom (with clamping)
    - Default → catmullrom (with clamping)

Overshoot Clamping:
  - CatmullRom expressions are clamped to:
    [min(v1, v2) - margin, max(v1, v2) + margin]
  - margin = max(5.0, 0.15 * |v2 - v1|)
  - This prevents extreme overshooting while allowing natural CatmullRom curves
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from core.types import (
    AXES,
    CHANNELS,
    DEFAULT_INTERPOLATION,
    AnimationIR,
    AxisValue,
    BoneAnimationIR,
    KeyframeData,
)
from .symbol_table import (
    CatmullRomExpr,
    ConstantExpr,
    ExprNode,
    HoldExpr,
    LinearExpr,
    Segment,
    SymbolCurve,
    SymbolKey,
    SymbolTable,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Interpolation selection parameters
# ---------------------------------------------------------------------------

# Time gap above which CatmullRom may overshoot for rotation channels.
LARGE_GAP_THRESHOLD: float = 0.5  # seconds

# Maximum angular velocity (degrees per second) above which we keep CatmullRom
# even for large gaps (fast rotation is expected to be smooth).
HIGH_ANGULAR_VELOCITY: float = 60.0  # degrees per second

# Threshold for snap-heavy detection (degrees).
SNAP_THRESHOLD_DEGREES: float = 30.0

# Fraction of snaps required for a channel to be considered "snap-heavy."
SNAP_HEAVY_FRACTION: float = 0.5

# CatmullRom overshoot margin fraction
OVERSHOOT_MARGIN_FRACTION: float = 0.15

# CatmullRom minimum overshoot margin in degrees
OVERSHOOT_MIN_MARGIN: float = 5.0


# ---------------------------------------------------------------------------
# Per-axis time series extraction
# ---------------------------------------------------------------------------

class AxisTimePoint:
    """A single time-value point in a per-axis time series."""

    __slots__ = ("time", "value", "explicit")

    def __init__(self, time: float, value: float, explicit: bool) -> None:
        self.time = time
        self.value = value
        self.explicit = explicit

    def __repr__(self) -> str:
        tag = "E" if self.explicit else "D"
        return f"ATP(t={self.time:.4f}, v={self.value:.2f}, {tag})"


def _extract_axis_series(
    keyframes: List[KeyframeData],
    channel: str,
    axis: str,
) -> List[AxisTimePoint]:
    """Extract a per-axis time series from keyframes.

    Args:
        keyframes: All keyframes for this bone (sorted by time).
        channel: The channel to extract.
        axis: The axis to extract ("x", "y", or "z").

    Returns:
        Sorted list of AxisTimePoint with time, value, and explicit flag.
    """
    points: List[AxisTimePoint] = []

    for kf in keyframes:
        if kf.channel != channel:
            continue

        av: AxisValue = getattr(kf, axis)
        if av.explicit:
            points.append(AxisTimePoint(time=kf.time, value=av.value, explicit=True))

    # Sort by time
    points.sort(key=lambda p: p.time)

    # Remove duplicates (keep last at each time point)
    seen: Dict[float, int] = {}
    deduped: List[AxisTimePoint] = []
    for i, pt in enumerate(points):
        t_rounded = round(pt.time, 8)
        if t_rounded in seen:
            deduped[seen[t_rounded]] = pt
        else:
            seen[t_rounded] = len(deduped)
            deduped.append(pt)

    return deduped


# ---------------------------------------------------------------------------
# Snap-heavy detection
# ---------------------------------------------------------------------------

def _is_axis_snap_heavy(
    points: List[AxisTimePoint],
) -> bool:
    """Determine if a per-axis series is snap-heavy.

    A series is "snap-heavy" if more than SNAP_HEAVY_FRACTION of
    consecutive pairs have a delta > SNAP_THRESHOLD_DEGREES.

    Args:
        points: Per-axis time series (sorted by time).

    Returns:
        True if the series should use linear interpolation.
    """
    if len(points) < 2:
        return False

    snap_count = 0
    total_pairs = len(points) - 1

    for i in range(1, len(points)):
        delta = abs(points[i].value - points[i - 1].value)
        if delta > SNAP_THRESHOLD_DEGREES:
            snap_count += 1

    if total_pairs == 0:
        return False

    return (snap_count / total_pairs) > SNAP_HEAVY_FRACTION


# ---------------------------------------------------------------------------
# Per-segment interpolation selection
# ---------------------------------------------------------------------------

def _select_segment_interpolation(
    v1: float,
    v2: float,
    dt: float,
    channel: str,
    snap_heavy: bool,
    easing: str,
) -> str:
    """Select interpolation mode for one segment.

    Args:
        v1: Start value.
        v2: End value.
        dt: Time gap in seconds.
        channel: Channel name.
        snap_heavy: Whether this axis is snap-heavy.
        easing: Easing function name.

    Returns:
        "linear", "catmullrom", or "hold".
    """
    # Non-linear easing always uses catmullrom
    if easing != "linear":
        return "catmullrom"

    # Snap-heavy axes use linear
    if snap_heavy:
        return "linear"

    # Position and scale default to linear
    if channel in ("position", "scale"):
        return "linear"

    # Rotation: check segment-specific conditions
    if channel == "rotation":
        max_delta = abs(v2 - v1)

        if dt > LARGE_GAP_THRESHOLD:
            angular_velocity = max_delta / dt if dt > 0 else 0

            if angular_velocity < HIGH_ANGULAR_VELOCITY and max_delta < SNAP_THRESHOLD_DEGREES:
                # Large gap with small, slow changes → linear
                return "linear"

            # Large gap with fast changes → catmullrom with clamping
            return "catmullrom"

        # Small gap → default for rotation is catmullrom
        return "catmullrom"

    # Default
    return DEFAULT_INTERPOLATION.get(channel, "linear")


# ---------------------------------------------------------------------------
# Segment builder — creates AST expression for each segment
# ---------------------------------------------------------------------------

def _build_segment_expr(
    v0: Optional[float],
    v1: float,
    v2: float,
    v3: Optional[float],
    interpolation: str,
    channel: str,
) -> ExprNode:
    """Build an AST expression node for one segment.

    Args:
        v0: Previous control point (None for boundary).
        v1: Start value.
        v2: End value.
        v3: Next control point (None for boundary).
        interpolation: "linear", "catmullrom", or "hold".
        channel: Channel name (for margin calculation).

    Returns:
        ExprNode for evaluating this segment.
    """
    if interpolation == "hold":
        return HoldExpr(value=v1)

    if interpolation == "linear":
        return LinearExpr(v1=v1, v2=v2)

    # CatmullRom with overshoot clamping
    # Boundary conditions: linear extrapolation for missing control points
    if v0 is None:
        v0 = 2.0 * v1 - v2  # Linear extrapolation
    if v3 is None:
        v3 = 2.0 * v2 - v1  # Linear extrapolation

    # Choose margin based on channel
    if channel == "rotation":
        margin_fraction = OVERSHOOT_MARGIN_FRACTION
        min_margin = OVERSHOOT_MIN_MARGIN
    else:
        # For position/scale, tighter clamping
        margin_fraction = 0.10
        min_margin = 1.0

    return CatmullRomExpr.create(
        v0=v0, v1=v1, v2=v2, v3=v3,
        margin_fraction=margin_fraction,
        min_margin=min_margin,
    )


def _build_axis_segments(
    points: List[AxisTimePoint],
    channel: str,
    snap_heavy: bool,
    easing: str,
) -> List[Segment]:
    """Build segments for one axis's time series.

    Args:
        points: Per-axis time series (sorted by time, deduplicated).
        channel: Channel name.
        snap_heavy: Whether this axis is snap-heavy.
        easing: Best easing from the source data.

    Returns:
        List of Segment instances covering the entire time range.
    """
    if not points:
        # No data → constant 0.0
        return [Segment(
            t_start=0.0,
            t_end=0.0,
            v_start=0.0,
            v_end=0.0,
            expr=ConstantExpr(value=0.0),
            is_explicit_start=False,
            is_explicit_end=False,
            interpolation="constant",
        )]

    if len(points) == 1:
        # Single keyframe → constant value
        pt = points[0]
        return [Segment(
            t_start=pt.time,
            t_end=pt.time,
            v_start=pt.value,
            v_end=pt.value,
            expr=ConstantExpr(value=pt.value),
            is_explicit_start=pt.explicit,
            is_explicit_end=pt.explicit,
            interpolation="constant",
        )]

    # Multiple keyframes → build segments
    segments: List[Segment] = []

    for i in range(len(points) - 1):
        pt1 = points[i]
        pt2 = points[i + 1]

        dt = pt2.time - pt1.time
        if dt < 1e-12:
            # Zero-duration segment → skip
            continue

        # Select interpolation for this segment
        interp = _select_segment_interpolation(
            pt1.value, pt2.value, dt, channel, snap_heavy, easing,
        )

        # Get control points for CatmullRom
        v0 = points[i - 1].value if i > 0 else None
        v3 = points[i + 2].value if i + 2 < len(points) else None

        # Build AST expression
        expr = _build_segment_expr(v0, pt1.value, pt2.value, v3, interp, channel)

        segments.append(Segment(
            t_start=pt1.time,
            t_end=pt2.time,
            v_start=pt1.value,
            v_end=pt2.value,
            expr=expr,
            is_explicit_start=pt1.explicit,
            is_explicit_end=pt2.explicit,
            interpolation=interp,
        ))

    return segments


# ---------------------------------------------------------------------------
# Main compilation function
# ---------------------------------------------------------------------------

def compile_symbol_table(
    animations: Dict[str, AnimationIR],
    model_name: str = "",
    stats: dict = None,
) -> Dict[str, SymbolTable]:
    """Compile symbol tables from validated AnimationIR data.

    For each animation:
      1. Extract per-axis time series from keyframes
      2. Select per-segment interpolation mode
      3. Build AST expression nodes with overshoot clamping
      4. Store in SymbolTable

    This replaces the old CarryForward stage entirely — the symbol table
    can be evaluated at any time point to produce the correct interpolated
    value, with the correct interpolation mode already baked in.

    Args:
        animations: Dict mapping animation_name -> AnimationIR (validated).
        model_name: Model name for logging.
        stats: Dict to update with compilation statistics.

    Returns:
        Dict mapping animation_name -> SymbolTable.
    """
    if stats is None:
        stats = {}

    stats.setdefault("curves_compiled", 0)
    stats.setdefault("segments_compiled", 0)
    stats.setdefault("catmullrom_segments", 0)
    stats.setdefault("linear_segments", 0)
    stats.setdefault("hold_segments", 0)
    stats.setdefault("constant_segments", 0)
    stats.setdefault("snap_heavy_axes", 0)

    result: Dict[str, SymbolTable] = {}

    for anim_name, anim in animations.items():
        table = SymbolTable()
        table.set_animation_meta(
            name=anim.name,
            loop=anim.loop,
            length=anim.length,
            period=anim.period,
        )

        for bone_name, bone_anim in anim.bones.items():
            try:
                _compile_bone_curves(
                    bone_anim, bone_name, anim_name, model_name,
                    table, stats,
                )
            except Exception as e:
                logger.warning(
                    "[%s] Symbol compile error for %s/%s: %s, skipping",
                    model_name, anim_name, bone_name, e,
                )

        result[anim_name] = table

    logger.info(
        "[%s] SymbolCompile: %d animations, %d curves, %d segments "
        "(%d CR, %d linear, %d hold, %d constant, %d snap-heavy axes)",
        model_name, len(result),
        stats.get("curves_compiled", 0),
        stats.get("segments_compiled", 0),
        stats.get("catmullrom_segments", 0),
        stats.get("linear_segments", 0),
        stats.get("hold_segments", 0),
        stats.get("constant_segments", 0),
        stats.get("snap_heavy_axes", 0),
    )

    return result


def _compile_bone_curves(
    bone_anim: BoneAnimationIR,
    bone_name: str,
    anim_name: str,
    model_name: str,
    table: SymbolTable,
    stats: dict,
) -> None:
    """Compile symbol curves for one bone.

    Args:
        bone_anim: The bone's animation data.
        bone_name: Bone name.
        anim_name: Animation name for logging.
        model_name: Model name for logging.
        table: SymbolTable to add curves to.
        stats: Stats dict to update.
    """
    if not bone_anim.keyframes:
        return

    for channel in CHANNELS:
        # Check if this channel has any keyframes
        channel_kfs = [kf for kf in bone_anim.keyframes if kf.channel == channel]
        if not channel_kfs:
            continue

        # Determine best easing from the channel's keyframes
        best_easing = "linear"
        for kf in channel_kfs:
            if kf.easing != "linear":
                best_easing = kf.easing
                break

        for axis in AXES:
            # Extract per-axis time series
            points = _extract_axis_series(bone_anim.keyframes, channel, axis)

            if not points:
                # No data for this axis → skip (evaluator will use 0.0)
                continue

            # Detect snap-heavy
            snap_heavy = _is_axis_snap_heavy(points)
            if snap_heavy and channel == "rotation":
                stats["snap_heavy_axes"] = stats.get("snap_heavy_axes", 0) + 1

            # Build segments
            segments = _build_axis_segments(points, channel, snap_heavy, best_easing)

            # Create SymbolCurve
            molang = ""
            for kf in channel_kfs:
                molang_attr = f"molang_{axis}"
                m = getattr(kf, molang_attr, "")
                if m:
                    molang = m
                    break

            curve = SymbolCurve(
                bone_name=bone_name,
                channel=channel,
                axis=axis,
                segments=segments,
                molang=molang,
            )

            table.add_curve(curve)

            # Update stats
            stats["curves_compiled"] = stats.get("curves_compiled", 0) + 1
            stats["segments_compiled"] = stats.get("segments_compiled", 0) + len(segments)

            for seg in segments:
                if seg.interpolation == "catmullrom":
                    stats["catmullrom_segments"] = stats.get("catmullrom_segments", 0) + 1
                elif seg.interpolation == "linear":
                    stats["linear_segments"] = stats.get("linear_segments", 0) + 1
                elif seg.interpolation == "hold":
                    stats["hold_segments"] = stats.get("hold_segments", 0) + 1
                else:
                    stats["constant_segments"] = stats.get("constant_segments", 0) + 1
