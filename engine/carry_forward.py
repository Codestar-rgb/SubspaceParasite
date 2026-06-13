#!/usr/bin/env python3
"""
Super Architecture — Interpolation-Aware Carry-Forward
=======================================================

SMART carry-forward using per-axis interpolation from the axis's own time series.

CRITICAL FIX over the previous carry-forward:
The previous implementation used "last explicit value" for missing axes at
merged time points. This created STEP FUNCTIONS where GeckoLib expects SMOOTH
INTERPOLATION.

Example of the problem:
  Source rotation: {
    x: {0.0: 0, 1.0: 30, 2.0: 0},
    y: {0.0: 0, 0.5: 15, 1.5: -15, 2.0: 0}
  }
  After merge, we need keyframes at t=0.0, 0.5, 1.0, 1.5, 2.0.

  OLD (broken): at t=0.5, x has no data → carry-forward x=0 from t=0.0
  NEW (correct): at t=0.5, x has no data → INTERPOLATE x=15 from x's own curve

This is the ROOT CAUSE of animation frame skipping, stuttering, and speed
anomalies. GeckoLib renders each axis independently with its own interpolation,
so when we merge keyframes into unified time points, we must simulate the same
interpolation that GeckoLib would use.

Algorithm per channel:
  1. For each axis, store its own time series (time → value) from the source
  2. At each merged time point, for each axis:
     - If the axis has explicit data at this time → use it
     - If not → interpolate from the axis's own time series using Catmull-Rom
  3. All interpolated values are marked explicit=True (they represent the
     correct animated value, not a carry-forward placeholder)

All transforms produce new data — input is never mutated.
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

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Catmull-Rom interpolation for per-axis curves
# ---------------------------------------------------------------------------

def _catmull_rom_interpolate(
    t: float,
    t0: float, v0: float,
    t1: float, v1: float,
    t2: float, v2: float,
    t3: float, v3: float,
) -> float:
    """Catmull-Rom spline interpolation at time t between t1 and t2.

    Uses the standard Catmull-Rom formulation with four control points.
    This matches GeckoLib/Blockbench Catmull-Rom interpolation behavior.

    Args:
        t: Time to evaluate at.
        t0, v0: Previous control point (time, value).
        t1, v1: Start of segment (time, value).
        t2, v2: End of segment (time, value).
        t3, v3: Next control point (time, value).

    Returns:
        Interpolated value at time t.
    """
    # Normalize t to [0, 1] within the segment [t1, t2]
    dt = t2 - t1
    if dt < 1e-12:
        return v1

    s = (t - t1) / dt
    s = max(0.0, min(1.0, s))

    s2 = s * s
    s3 = s2 * s

    # Catmull-Rom coefficients (uniform parameterization)
    # Using the matrix form: 0.5 * [1 s s^2 s^3] * M * [P0 P1 P2 P3]^T
    # M = [[ 0,  2,  0,  0],
    #      [-1,  0,  1,  0],
    #      [ 2, -5,  4, -1],
    #      [-1,  3, -3,  1]]

    c0 = 2.0 * v1
    c1 = -v0 + v2
    c2 = 2.0 * v0 - 5.0 * v1 + 4.0 * v2 - v3
    c3 = -v0 + 3.0 * v1 - 3.0 * v2 + v3

    return 0.5 * (c0 + c1 * s + c2 * s2 + c3 * s3)


def _linear_interpolate(
    t: float,
    t1: float, v1: float,
    t2: float, v2: float,
) -> float:
    """Linear interpolation between two points.

    Args:
        t: Time to evaluate at.
        t1, v1: Start point (time, value).
        t2, v2: End point (time, value).

    Returns:
        Interpolated value at time t.
    """
    dt = t2 - t1
    if dt < 1e-12:
        return v1
    s = (t - t1) / dt
    s = max(0.0, min(1.0, s))
    return v1 + s * (v2 - v1)


def _interpolate_axis_value(
    t: float,
    axis_times: List[float],
    axis_values: List[float],
    channel: str,
) -> Optional[float]:
    """Interpolate the value of one axis at time t from its own time series.

    Uses Catmull-Rom interpolation for rotation channels (matching GeckoLib
    behavior) and linear interpolation for position/scale channels.

    For boundary conditions (t before first or after last keyframe), uses
    the first/last value (clamp).

    Args:
        t: Time to interpolate at.
        axis_times: Sorted list of times for this axis.
        axis_values: Corresponding list of values for this axis.
        channel: Channel name for interpolation mode selection.

    Returns:
        Interpolated value, or None if the axis has no data at all.
    """
    n = len(axis_times)
    if n == 0:
        return None

    # Clamp to range
    if t <= axis_times[0]:
        return axis_values[0]
    if t >= axis_times[-1]:
        return axis_values[-1]

    # Find the segment containing t (binary search)
    lo, hi = 0, n - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if axis_times[mid] <= t:
            lo = mid
        else:
            hi = mid

    # lo is the segment start, hi is the segment end
    idx = lo  # t is between axis_times[idx] and axis_times[idx+1]

    if channel in ("rotation", "position", "scale"):
        # CatmullRom interpolation for all channels (GeckoLib 1.8.0 default)
        # Need four control points: idx-1, idx, idx+1, idx+2
        # Use boundary extension for endpoints
        t1 = axis_times[idx]
        t2 = axis_times[idx + 1]
        v1 = axis_values[idx]
        v2 = axis_values[idx + 1]

        # Previous control point (extend if at boundary)
        if idx > 0:
            t0 = axis_times[idx - 1]
            v0 = axis_values[idx - 1]
        else:
            # Extend: mirror v1-v2 direction
            dt = t2 - t1
            t0 = t1 - dt
            v0 = 2.0 * v1 - v2  # Linear extrapolation

        # Next control point (extend if at boundary)
        if idx + 2 < n:
            t3 = axis_times[idx + 2]
            v3 = axis_values[idx + 2]
        else:
            dt = t2 - t1
            t3 = t2 + dt
            v3 = 2.0 * v2 - v1  # Linear extrapolation

        return _catmull_rom_interpolate(t, t0, v0, t1, v1, t2, v2, t3, v3)
    else:
        # Fallback: linear interpolation for unknown channels
        return _linear_interpolate(
            t,
            axis_times[idx], axis_values[idx],
            axis_times[idx + 1], axis_values[idx + 1],
        )


# ---------------------------------------------------------------------------
# Per-channel interpolation-aware fill
# ---------------------------------------------------------------------------

def apply_carry_forward(
    keyframes: List[KeyframeData],
    bone_name: str,
    model_name: str,
    stats: dict,
) -> List[KeyframeData]:
    """Fill missing axes at each time point using interpolation from per-axis curves.

    KEY FIX: Instead of carrying forward the last explicit value (which creates
    step functions), we INTERPOLATE the value from the axis's own time series.
    This matches GeckoLib's behavior where each axis is independently interpolated.

    Algorithm per channel:
      1. Collect each axis's own time series (time → value) from explicit data
      2. At each merged time point, for each axis:
         - If the axis has explicit data at this time → use it
         - If not → interpolate from the axis's own time series
         - If the axis has no data at all → use 0.0
      3. All filled values are marked explicit=True (they represent the correct
         animated value that GeckoLib would compute)

    Args:
        keyframes: List of KeyframeData for one bone (sorted by time).
        bone_name: Name of the bone (for logging).
        model_name: Model name (for logging).
        stats: Dict to update with carry-forward statistics.

    Returns:
        New list of KeyframeData with all axes filled in via interpolation.
    """
    if not keyframes:
        return []

    # Group keyframes by channel
    channel_kfs: Dict[str, List[KeyframeData]] = {}
    for kf in keyframes:
        if kf.channel not in channel_kfs:
            channel_kfs[kf.channel] = []
        channel_kfs[kf.channel].append(kf)

    result: List[KeyframeData] = []
    axes_filled = 0
    axes_interpolated = 0

    for channel in CHANNELS:
        kfs = channel_kfs.get(channel, [])
        if not kfs:
            continue

        # Sort by time
        kfs_sorted = sorted(kfs, key=lambda k: k.time)

        # Step 1: Build per-axis time series from EXPLICIT data only
        axis_times: Dict[str, List[float]] = {"x": [], "y": [], "z": []}
        axis_values: Dict[str, List[float]] = {"x": [], "y": [], "z": []}
        axis_molang: Dict[str, str] = {"x": "", "y": "", "z": ""}

        for kf in kfs_sorted:
            for axis in AXES:
                av: AxisValue = getattr(kf, axis)
                if av.explicit:
                    axis_times[axis].append(kf.time)
                    axis_values[axis].append(av.value)
                    # Track molang expressions
                    molang_attr = f"molang_{axis}"
                    molang_expr = getattr(kf, molang_attr, "")
                    if molang_expr:
                        axis_molang[axis] = molang_expr

        # Step 2: For each keyframe, fill missing axes via interpolation
        for kf in kfs_sorted:
            new_vals: Dict[str, float] = {}
            new_molang: Dict[str, str] = {}

            for axis in AXES:
                av: AxisValue = getattr(kf, axis)
                molang_attr = f"molang_{axis}"
                molang_expr = getattr(kf, molang_attr, "")

                if av.explicit:
                    # Axis has explicit data → use it
                    new_vals[axis] = av.value
                    if molang_expr:
                        new_molang[axis] = molang_expr
                    elif axis_molang[axis]:
                        new_molang[axis] = axis_molang[axis]
                else:
                    # Axis has no explicit data at this time point
                    # → INTERPOLATE from the axis's own time series
                    interp_val = _interpolate_axis_value(
                        kf.time,
                        axis_times[axis],
                        axis_values[axis],
                        channel,
                    )

                    if interp_val is not None:
                        new_vals[axis] = interp_val
                        axes_interpolated += 1
                    else:
                        # Axis has NO data at all → use 0.0
                        new_vals[axis] = 0.0
                        axes_filled += 1

                    # Propagate molang if the axis uses it globally
                    if axis_molang[axis]:
                        new_molang[axis] = axis_molang[axis]

            # Create new keyframe with all axes filled
            is_molang = bool(new_molang.get("x")) or bool(new_molang.get("y")) or bool(new_molang.get("z"))

            new_kf = KeyframeData(
                time=kf.time,
                channel=kf.channel,
                x=AxisValue.explicit_val(new_vals["x"]),
                y=AxisValue.explicit_val(new_vals["y"]),
                z=AxisValue.explicit_val(new_vals["z"]),
                easing=kf.easing,
                interpolation=kf.interpolation,
                is_molang=is_molang or kf.is_molang,
                molang_x=new_molang.get("x", ""),
                molang_y=new_molang.get("y", ""),
                molang_z=new_molang.get("z", ""),
            )
            result.append(new_kf)

    # Sort by time, then channel for deterministic ordering
    result.sort(key=lambda k: (k.time, k.channel))

    stats["axes_filled"] = stats.get("axes_filled", 0) + axes_filled
    stats["axes_interpolated"] = stats.get("axes_interpolated", 0) + axes_interpolated

    return result


# ---------------------------------------------------------------------------
# Apply to all animations
# ---------------------------------------------------------------------------

def apply_carry_forward_all(
    animations: Dict[str, AnimationIR],
    model_name: str,
    stats: dict,
) -> Dict[str, AnimationIR]:
    """Apply interpolation-aware carry-forward to all animations.

    For each animation, for each bone, fill missing axes using interpolation
    from per-axis curves instead of simple carry-forward.

    Args:
        animations: Dict mapping animation_name -> AnimationIR.
        model_name: Model name for logging.
        stats: Dict to update with carry-forward statistics.

    Returns:
        New dict of animations with interpolation-based fill applied.
    """
    result: Dict[str, AnimationIR] = {}

    for anim_name, anim in animations.items():
        new_bones: Dict[str, BoneAnimationIR] = {}

        for bone_name, bone_anim in anim.bones.items():
            try:
                new_keyframes = apply_carry_forward(
                    bone_anim.keyframes,
                    bone_name,
                    model_name,
                    stats,
                )
                new_bones[bone_name] = BoneAnimationIR(
                    bone_name=bone_name,
                    keyframes=new_keyframes,
                )
            except Exception as e:
                logger.warning(
                    "[%s] Carry-forward error for %s/%s: %s, keeping original",
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
