#!/usr/bin/env python3
"""
AST Symbol Compiler — Symbol Table & Expression Types
======================================================

This module defines the core data types for the AST Symbol Compiler architecture.

KEY INSIGHT: The old pipeline had a fundamental ordering problem:
  - Stage 2 (CarryForward) used CatmullRom to fill missing axis values
  - Stage 6 (Interpolation) selected interpolation modes PER SEGMENT
  - This means carry-forward used WRONG interpolation (CatmullRom) for
    segments that should be linear, and it created overshoot artifacts.

The AST Symbol Compiler fixes this by:
  1. Building per-axis SymbolCurves with CORRECT per-segment interpolation
  2. Using AST Expression nodes that ENCODE the interpolation mode
  3. Evaluating expressions on-demand — no separate carry-forward step needed
  4. Building in overshoot clamping directly into CatmullRom expressions

Architecture:
  SymbolTable:  Maps (bone, channel, axis) -> SymbolCurve
  SymbolCurve:  Time-series with per-segment interpolation + overshoot clamping
  ExprNode:     Base class for AST expression nodes
  LinearExpr:   Linear interpolation between two values
  CatmullRomExpr: CatmullRom with built-in overshoot clamping
  ConstantExpr: Constant value (no interpolation)
  HoldExpr:     Hold previous value (step function — used only for snap transitions)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# AST Expression Node types
# ---------------------------------------------------------------------------

class ExprNode:
    """Base class for AST expression nodes.

    Each node represents a segment of an animation curve between two time
    points.  The node can be evaluated at any parameter s ∈ [0, 1] to
    produce the interpolated value at that point.
    """

    def evaluate(self, s: float) -> float:
        """Evaluate the expression at parameter s ∈ [0, 1].

        Args:
            s: Interpolation parameter (0 = start, 1 = end).

        Returns:
            Interpolated value.
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


@dataclass(frozen=True)
class ConstantExpr(ExprNode):
    """Constant value — no interpolation.

    Used when:
      - An axis has only one keyframe
      - An axis has no data at all (default 0.0)
    """

    value: float

    def evaluate(self, s: float) -> float:
        return self.value

    def __repr__(self) -> str:
        return f"Const({self.value})"


@dataclass(frozen=True)
class LinearExpr(ExprNode):
    """Linear interpolation between two values.

    Used for:
      - Position and scale channels (default)
      - Rotation segments with large time gaps and small value changes
      - Snap-heavy channels
    """

    v1: float  # Start value
    v2: float  # End value

    def evaluate(self, s: float) -> float:
        s = max(0.0, min(1.0, s))
        return self.v1 + s * (self.v2 - self.v1)

    def __repr__(self) -> str:
        return f"Linear({self.v1} → {self.v2})"


@dataclass(frozen=True)
class HoldExpr(ExprNode):
    """Hold previous value — step function.

    Used for snap transitions where the value should jump instantly
    rather than interpolate smoothly.
    """

    value: float

    def evaluate(self, s: float) -> float:
        return self.value

    def __repr__(self) -> str:
        return f"Hold({self.value})"


@dataclass(frozen=True)
class CatmullRomExpr(ExprNode):
    """CatmullRom interpolation with built-in overshoot clamping.

    This is the CRITICAL fix: the old CatmullRom had no clamping, causing
    values to overshoot/undershoot beyond the intended range on large
    time gaps.  The new CatmullRomExpr clamps the output to:

        [min(v1, v2) - overshoot_margin, max(v1, v2) + overshoot_margin]

    Where overshoot_margin is a fraction of the segment's value range,
    controlled by OVERSHOOT_MARGIN_FRACTION (default 0.15 = 15%).

    The CatmullRom formulation uses four control points:
      v0: Previous control point (or linear extrapolation if at boundary)
      v1: Start of segment
      v2: End of segment
      v3: Next control point (or linear extrapolation if at boundary)

    The matrix form:
      0.5 * [1 s s^2 s^3] * M * [P0 P1 P2 P3]^T
      M = [[ 0,  2,  0,  0],
           [-1,  0,  1,  0],
           [ 2, -5,  4, -1],
           [-1,  3, -3,  1]]
    """

    v0: float  # Previous control point
    v1: float  # Start value
    v2: float  # End value
    v3: float  # Next control point
    clamp_lo: float  # Minimum allowed value
    clamp_hi: float  # Maximum allowed value

    # Default overshoot margin as fraction of segment range
    OVERSHOOT_MARGIN_FRACTION: float = 0.15

    @staticmethod
    def compute_clamp_bounds(
        v1: float,
        v2: float,
        margin_fraction: float = 0.15,
        min_margin: float = 5.0,
    ) -> Tuple[float, float]:
        """Compute overshoot clamp bounds for a CatmullRom segment.

        The bounds are:
          lo = min(v1, v2) - max(min_margin, margin_fraction * range)
          hi = max(v1, v2) + max(min_margin, margin_fraction * range)

        This allows some overshoot (CatmullRom's natural behavior) while
        preventing extreme overshooting on large-gap segments.

        Args:
            v1: Start value.
            v2: End value.
            margin_fraction: Fraction of the value range allowed as overshoot.
            min_margin: Minimum overshoot margin in value units.

        Returns:
            Tuple (lo, hi) clamp bounds.
        """
        val_range = abs(v2 - v1)
        margin = max(min_margin, margin_fraction * val_range)
        lo = min(v1, v2) - margin
        hi = max(v1, v2) + margin
        return (lo, hi)

    @classmethod
    def create(
        cls,
        v0: float,
        v1: float,
        v2: float,
        v3: float,
        margin_fraction: float = 0.15,
        min_margin: float = 5.0,
    ) -> CatmullRomExpr:
        """Create a CatmullRomExpr with computed clamp bounds.

        Args:
            v0: Previous control point.
            v1: Start value.
            v2: End value.
            v3: Next control point.
            margin_fraction: Fraction of range allowed as overshoot.
            min_margin: Minimum overshoot margin in value units.

        Returns:
            CatmullRomExpr with overshoot clamping.
        """
        clamp_lo, clamp_hi = cls.compute_clamp_bounds(v1, v2, margin_fraction, min_margin)
        return cls(v0=v0, v1=v1, v2=v2, v3=v3, clamp_lo=clamp_lo, clamp_hi=clamp_hi)

    def evaluate(self, s: float) -> float:
        """Evaluate CatmullRom with overshoot clamping.

        Args:
            s: Parameter in [0, 1] (0 = v1, 1 = v2).

        Returns:
            Interpolated value, clamped to [clamp_lo, clamp_hi].
        """
        s = max(0.0, min(1.0, s))

        s2 = s * s
        s3 = s2 * s

        # CatmullRom coefficients
        c0 = 2.0 * self.v1
        c1 = -self.v0 + self.v2
        c2 = 2.0 * self.v0 - 5.0 * self.v1 + 4.0 * self.v2 - self.v3
        c3 = -self.v0 + 3.0 * self.v1 - 3.0 * self.v2 + self.v3

        result = 0.5 * (c0 + c1 * s + c2 * s2 + c3 * s3)

        # Apply overshoot clamping
        result = max(self.clamp_lo, min(self.clamp_hi, result))

        return result

    def __repr__(self) -> str:
        return f"CR({self.v0:.1f}, {self.v1:.1f}, {self.v2:.1f}, {self.v3:.1f}, [{self.clamp_lo:.1f}..{self.clamp_hi:.1f}])"


# ---------------------------------------------------------------------------
# Segment — one piece of a SymbolCurve
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Segment:
    """One segment of a SymbolCurve between two consecutive keyframes.

    Attributes:
        t_start: Start time in seconds.
        t_end: End time in seconds.
        v_start: Value at t_start.
        v_end: Value at t_end.
        expr: The AST expression node for evaluating this segment.
        is_explicit_start: True if the start value was from source data.
        is_explicit_end: True if the end value was from source data.
        interpolation: The interpolation mode ("linear", "catmullrom", "hold").
    """

    t_start: float
    t_end: float
    v_start: float
    v_end: float
    expr: ExprNode
    is_explicit_start: bool = True
    is_explicit_end: bool = True
    interpolation: str = "linear"

    def evaluate_at_time(self, t: float) -> float:
        """Evaluate this segment at a specific time.

        Args:
            t: Time in seconds (must be within [t_start, t_end]).

        Returns:
            Interpolated value at time t.
        """
        dt = self.t_end - self.t_start
        if dt < 1e-12:
            return self.v_start

        s = (t - self.t_start) / dt
        s = max(0.0, min(1.0, s))

        return self.expr.evaluate(s)

    def __repr__(self) -> str:
        return f"Seg({self.t_start:.3f}→{self.t_end:.3f}, {self.v_start:.2f}→{self.v_end:.2f}, {self.interpolation})"


# ---------------------------------------------------------------------------
# SymbolCurve — per-axis time series with AST expression segments
# ---------------------------------------------------------------------------

@dataclass
class SymbolCurve:
    """A per-axis time series with per-segment AST expression nodes.

    This is the core data structure of the AST Symbol Compiler.  Each
    SymbolCurve represents ONE axis (e.g. bone "head" rotation X) as
    a sequence of Segments, each with its own interpolation mode and
    overshoot clamping.

    Attributes:
        bone_name: Name of the bone.
        channel: "rotation", "position", or "scale".
        axis: "x", "y", or "z".
        segments: Sorted list of Segments (by t_start).
        molang: Molang expression (empty string if not Molang).
        period: Detected period for this curve (None = not yet analyzed).
    """

    bone_name: str
    channel: str
    axis: str
    segments: List[Segment] = field(default_factory=list)
    molang: str = ""
    period: Optional[float] = None

    def evaluate_at_time(self, t: float, rest_pose: float = 0.0) -> float:
        """Evaluate the curve at a specific time.

        For t BEFORE the first keyframe: returns rest_pose (0.0 by default).
          This matches GeckoLib behavior where an axis that hasn't started
          animating yet uses the rest pose value, not the first keyframe's value.
          Example: Y has only one keyframe at t=2 with Y=15. At t=0, Y should
          be 0.0 (rest pose), NOT 15.0 (which would incorrectly hold the first
          keyframe value before the animation starts on that axis).

        For t AFTER the last keyframe: returns the last keyframe's value.
          This matches GeckoLib's "hold on last frame" behavior.

        For t within a segment: evaluates the segment's AST expression.

        Args:
            t: Time in seconds.
            rest_pose: Value to return before the first keyframe (default 0.0).

        Returns:
            Interpolated value at time t.
        """
        if not self.segments:
            return rest_pose

        # Before first keyframe → rest pose (GeckoLib: axis not yet animated)
        if t < self.segments[0].t_start - 1e-9:
            return rest_pose

        # At or very near first keyframe
        if t <= self.segments[0].t_start + 1e-9:
            return self.segments[0].v_start

        # After last keyframe → hold at last value
        if t >= self.segments[-1].t_end:
            return self.segments[-1].v_end

        # Find the segment containing t (binary search)
        lo, hi = 0, len(self.segments) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            seg = self.segments[mid]
            if t < seg.t_start:
                hi = mid - 1
            elif t > seg.t_end:
                lo = mid + 1
            else:
                return seg.evaluate_at_time(t)

        # Fallback: linear scan (should rarely be needed)
        for seg in self.segments:
            if seg.t_start <= t <= seg.t_end:
                return seg.evaluate_at_time(t)

        # Should not reach here
        return self.segments[-1].v_end

    def keyframe_times(self) -> List[float]:
        """Return all unique keyframe times in this curve.

        Returns:
            Sorted list of time points.
        """
        if not self.segments:
            return []

        times = [self.segments[0].t_start]
        for seg in self.segments:
            if seg.t_end != times[-1]:
                times.append(seg.t_end)

        return times

    def explicit_keyframe_times(self) -> List[float]:
        """Return time points where at least one endpoint was from source data.

        Returns:
            Sorted list of time points with explicit data.
        """
        times = set()
        for seg in self.segments:
            if seg.is_explicit_start:
                times.add(seg.t_start)
            if seg.is_explicit_end:
                times.add(seg.t_end)
        return sorted(times)

    def value_range(self) -> Tuple[float, float]:
        """Return the (min, max) value range across all segments.

        Returns:
            Tuple (min_value, max_value).
        """
        if not self.segments:
            return (0.0, 0.0)

        values = []
        for seg in self.segments:
            values.append(seg.v_start)
            values.append(seg.v_end)

        return (min(values), max(values))

    def __repr__(self) -> str:
        return f"SymbolCurve({self.bone_name}.{self.channel}.{self.axis}, {len(self.segments)} segs)"


# ---------------------------------------------------------------------------
# SymbolTable — the complete compiled symbol table for one animation
# ---------------------------------------------------------------------------

# Key type for looking up curves in the symbol table
SymbolKey = Tuple[str, str, str]  # (bone_name, channel, axis)


class SymbolTable:
    """The complete compiled symbol table for one animation.

    Maps (bone_name, channel, axis) -> SymbolCurve for all animated
    axes in the animation.  This is the output of the SymbolCompiler
    stage and the input to the SymbolEvaluator stage.

    The symbol table replaces the old carry-forward stage entirely:
    instead of filling missing axis values with interpolated data,
    we evaluate the symbol table on-demand at each time point.
    """

    def __init__(self) -> None:
        self._curves: Dict[SymbolKey, SymbolCurve] = {}
        self._animation_name: str = ""
        self._loop: str = "once"
        self._length: float = 0.0
        self._period: Optional[float] = None

    def set_animation_meta(
        self,
        name: str,
        loop: str,
        length: float,
        period: Optional[float] = None,
    ) -> None:
        """Set animation metadata."""
        self._animation_name = name
        self._loop = loop
        self._length = length
        self._period = period

    @property
    def animation_name(self) -> str:
        return self._animation_name

    @property
    def loop(self) -> str:
        return self._loop

    @property
    def length(self) -> float:
        return self._length

    @property
    def period(self) -> Optional[float]:
        return self._period

    @period.setter
    def period(self, value: Optional[float]) -> None:
        self._period = value

    def add_curve(self, curve: SymbolCurve) -> None:
        """Add a SymbolCurve to the table."""
        key = (curve.bone_name, curve.channel, curve.axis)
        self._curves[key] = curve

    def get_curve(self, bone_name: str, channel: str, axis: str) -> Optional[SymbolCurve]:
        """Get a SymbolCurve, or None if not found."""
        return self._curves.get((bone_name, channel, axis))

    def all_curves(self) -> Dict[SymbolKey, SymbolCurve]:
        """Return all curves in the table."""
        return dict(self._curves)

    def bone_names(self) -> set:
        """Return all bone names with curves."""
        return {key[0] for key in self._curves}

    def evaluate_at_time(
        self,
        bone_name: str,
        channel: str,
        axis: str,
        t: float,
        rest_pose: float = 0.0,
    ) -> Optional[float]:
        """Evaluate a specific curve at a specific time.

        Args:
            bone_name: Bone name.
            channel: Channel name.
            axis: Axis name.
            t: Time in seconds.
            rest_pose: Value to return before the first keyframe (default 0.0).

        Returns:
            Interpolated value, or None if no curve exists.
        """
        curve = self.get_curve(bone_name, channel, axis)
        if curve is None:
            return None
        return curve.evaluate_at_time(t, rest_pose=rest_pose)

    def all_keyframe_times(self) -> List[float]:
        """Return all unique keyframe times across all curves.

        Returns:
            Sorted list of time points.
        """
        times: set = set()
        for curve in self._curves.values():
            times.update(curve.keyframe_times())
        return sorted(times)

    def merged_time_points(self) -> List[float]:
        """Return merged time points for all curves.

        These are the time points where at least one curve has a keyframe.
        When evaluating for export, we need values at ALL of these time
        points for every animated bone.

        Returns:
            Sorted list of merged time points.
        """
        return self.all_keyframe_times()

    def __repr__(self) -> str:
        return f"SymbolTable({self._animation_name}, {len(self._curves)} curves, period={self._period})"
