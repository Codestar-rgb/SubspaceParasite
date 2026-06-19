#!/usr/bin/env python3
"""
AST Symbol Compiler — Period Locker (LCM-based)
==================================================

Lock the animation period using LCM-based analysis for seamless loops.

KEY IMPROVEMENT over old period_analyzer:
  The old analyzer used autocorrelation on a single axis's signal, which
  could detect wrong periods for multi-period animations. The new Period
  Locker uses a LCM (Least Common Multiple) approach:

  1. If animation.length > 0, trust it as the period (source provides it)
  2. Otherwise, compute per-curve periods using autocorrelation
  3. Take the LCM of all per-curve periods to get the animation period
  4. Validate: the period should be consistent with the animation length

For loop animations, the locked period is used by the loop aligner to
ensure all bones loop seamlessly at the same period boundary.

All transforms produce new data — input is never mutated.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from core.types import AnimationIR, BoneAnimationIR
from core.math_utils import lcm, compute_animation_period
from .symbol_table import SymbolCurve, SymbolTable, SymbolKey

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-curve period detection
# ---------------------------------------------------------------------------

def _detect_curve_period(curve: SymbolCurve) -> Optional[float]:
    """Detect the period of a single curve using its keyframe data.

    Uses autocorrelation on the curve's segment endpoints.

    Args:
        curve: The SymbolCurve to analyze.

    Returns:
        Detected period in seconds, or None if no period detected.
    """
    # Get explicit keyframe times and values
    times = []
    values = []
    for seg in curve.segments:
        times.append(seg.t_start)
        values.append(seg.v_start)
    # Add the last endpoint
    if curve.segments:
        times.append(curve.segments[-1].t_end)
        values.append(curve.segments[-1].v_end)

    if len(times) < 4:
        return None

    # Use autocorrelation
    period = compute_animation_period(times, values)
    return period


# ---------------------------------------------------------------------------
# LCM-based period locking
# ---------------------------------------------------------------------------

def lock_periods(
    symbol_tables: Dict[str, SymbolTable],
    animations: Dict[str, AnimationIR],
    model_name: str = "",
    stats: dict = None,
) -> Dict[str, SymbolTable]:
    """Lock animation periods using LCM-based analysis.

    For each animation:
      1. If animation.length > 0, use it as the period
      2. Otherwise, detect per-curve periods using autocorrelation
      3. Compute LCM of per-curve periods
      4. Set the locked period on the SymbolTable

    Args:
        symbol_tables: Dict mapping animation_name -> SymbolTable.
        animations: Dict mapping animation_name -> AnimationIR (for length).
        model_name: Model name for logging.
        stats: Dict to update with period statistics.

    Returns:
        New dict of symbol tables with periods locked.
    """
    if stats is None:
        stats = {}

    stats.setdefault("periods_from_source", 0)
    stats.setdefault("periods_from_lcm", 0)
    stats.setdefault("periods_undetected", 0)

    result: Dict[str, SymbolTable] = {}

    for anim_name, table in symbol_tables.items():
        anim = animations.get(anim_name)
        anim_length = anim.length if anim else 0.0

        period: Optional[float] = None

        # Strategy 1: Trust source-provided animation length
        if anim_length > 0:
            period = anim_length
            stats["periods_from_source"] = stats.get("periods_from_source", 0) + 1
            logger.debug(
                "[%s] %s: Using source length %.4f as period",
                model_name, anim_name, period,
            )
        else:
            # Strategy 2: Detect per-curve periods and compute LCM
            curve_periods: List[float] = []

            for key, curve in table.all_curves().items():
                if curve.channel != "rotation":
                    continue  # Only use rotation channels for period detection

                curve_period = _detect_curve_period(curve)
                if curve_period is not None and curve_period > 1e-6:
                    curve_periods.append(curve_period)

            if curve_periods:
                # Compute LCM of all detected periods
                # Round to reasonable precision first
                rounded_periods = [round(p, 4) for p in curve_periods]
                # Take unique periods
                unique_periods = list(set(rounded_periods))

                if unique_periods:
                    lcm_period = unique_periods[0]
                    for p in unique_periods[1:]:
                        try:
                            lcm_period = lcm(lcm_period, p)
                        except (ValueError, OverflowError):
                            # Fallback: take the maximum period
                            lcm_period = max(lcm_period, p)

                    period = lcm_period
                    stats["periods_from_lcm"] = stats.get("periods_from_lcm", 0) + 1
                    logger.debug(
                        "[%s] %s: LCM period %.4f from %d curves",
                        model_name, anim_name, period, len(curve_periods),
                    )
                else:
                    # Fallback: use max keyframe time
                    all_times = table.all_keyframe_times()
                    if all_times:
                        period = max(all_times)
            else:
                # No rotation curves or no periods detected
                # Fallback: use max keyframe time
                all_times = table.all_keyframe_times()
                if all_times:
                    period = max(all_times)

            if period is None:
                stats["periods_undetected"] = stats.get("periods_undetected", 0) + 1
                logger.debug(
                    "[%s] %s: Could not detect period",
                    model_name, anim_name,
                )

        # Create new SymbolTable with period set
        new_table = SymbolTable()
        new_table.set_animation_meta(
            name=table.animation_name,
            loop=table.loop,
            length=table.length,
            period=period,
        )

        # Copy all curves
        for key, curve in table.all_curves().items():
            new_table.add_curve(curve)

        result[anim_name] = new_table

    return result
