#!/usr/bin/env python3
"""
Super Architecture — Period Analyzer
======================================

Analyze animation data to detect the true period for seamless looping.

For each animation:
  1. If animation.length > 0, use it as the period (trust the source)
  2. Otherwise, analyze keyframe times and values:
     a. Collect all keyframe times for rotation channels
     b. Compute time intervals between consecutive keyframes
     c. Find the greatest common divisor (GCD) of intervals
     d. The period is likely a multiple of this GCD
     e. Use autocorrelation of the value signal to confirm
  3. Set animation.period = detected_period

The period is used by the loop aligner to ensure seamless loops.
"""

from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

from core.types import (
    AXES,
    CHANNELS,
    AnimationIR,
    BoneAnimationIR,
    KeyframeData,
)
from core.math_utils import compute_animation_period, lcm

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_gcd_of_intervals(times: List[float]) -> Optional[float]:
    """Compute the GCD of time intervals between consecutive keyframes.

    This helps determine the fundamental time step of the animation,
    which constrains possible periods to multiples of this step.

    Args:
        times: Sorted list of unique keyframe times.

    Returns:
        The GCD of the intervals in seconds, or None if there are
        fewer than 2 time points.
    """
    if len(times) < 2:
        return None

    intervals: List[float] = []
    for i in range(1, len(times)):
        dt = times[i] - times[i - 1]
        if dt > 1e-8:
            intervals.append(round(dt, 6))

    if not intervals:
        return None

    # Compute GCD iteratively using the lcm helper (which uses integer
    # rounding for stability).  Actually, for GCD we want the greatest
    # common divisor, not the least common multiple.
    # Use the standard math.gcd on scaled integers.
    scaled = [round(iv * 10000) for iv in intervals]
    scaled = [s for s in scaled if s > 0]

    if not scaled:
        return None

    result = scaled[0]
    for s in scaled[1:]:
        result = math.gcd(result, s)
        if result <= 0:
            break

    if result <= 0:
        return None

    return result / 10000.0


def _detect_period_from_data(anim: AnimationIR, model_name: str) -> Optional[float]:
    """Detect the animation period from keyframe data using autocorrelation.

    Strategy:
      1. Collect rotation keyframe times and values across all bones.
      2. Use autocorrelation on the dominant signal to find the period.
      3. Validate against the GCD of keyframe intervals.

    Args:
        anim: The animation to analyze.
        model_name: Model name for logging.

    Returns:
        Detected period in seconds, or None if period cannot be determined.
    """
    # Collect the best rotation signal for autocorrelation.
    # Pick the bone with the most rotation keyframes and the largest
    # value range (most "active" bone).
    best_times: List[float] = []
    best_values: List[float] = []
    best_range = 0.0

    for bone_name, bone_anim in anim.bones.items():
        # Get rotation keyframes for this bone
        rot_kfs = [kf for kf in bone_anim.keyframes if kf.channel == "rotation"]
        if len(rot_kfs) < 4:
            continue

        # Sort by time
        rot_kfs.sort(key=lambda k: k.time)

        # Use the axis with the largest range
        for axis in AXES:
            times: List[float] = []
            values: List[float] = []
            for kf in rot_kfs:
                val = getattr(kf, axis).value
                times.append(kf.time)
                values.append(val)

            if not values:
                continue

            val_range = max(values) - min(values)
            if val_range > best_range and len(times) >= 4:
                best_range = val_range
                best_times = times
                best_values = values

    if not best_times or best_range < 1e-6:
        # No significant rotation signal; try position channels
        for bone_name, bone_anim in anim.bones.items():
            pos_kfs = [kf for kf in bone_anim.keyframes if kf.channel == "position"]
            if len(pos_kfs) < 4:
                continue

            pos_kfs.sort(key=lambda k: k.time)

            for axis in AXES:
                times: List[float] = []
                values: List[float] = []
                for kf in pos_kfs:
                    val = getattr(kf, axis).value
                    times.append(kf.time)
                    values.append(val)

                if not values:
                    continue

                val_range = max(values) - min(values)
                if val_range > best_range and len(times) >= 4:
                    best_range = val_range
                    best_times = times
                    best_values = values

    # Use autocorrelation to detect the period
    if best_times and len(best_values) >= 4:
        period = compute_animation_period(best_times, best_values)
        if period is not None and period > 1e-6:
            return period

    # Fallback: use the time range of all keyframes
    all_times: List[float] = []
    for bone_anim in anim.bones.values():
        for kf in bone_anim.keyframes:
            all_times.append(kf.time)

    if not all_times:
        return None

    t_max = max(all_times)
    if t_max > 0:
        return t_max

    return None


# ---------------------------------------------------------------------------
# Main period analysis function
# ---------------------------------------------------------------------------

def analyze_periods(
    animations: Dict[str, AnimationIR],
    model_name: str = "",
) -> Dict[str, AnimationIR]:
    """Detect and set the period for each animation.

    For each animation:
    1. If animation.length > 0, use it as the period (trust the source)
    2. Otherwise, analyze keyframe times and values:
       a. Collect all keyframe times for rotation channels
       b. Compute time intervals between consecutive keyframes
       c. Find the greatest common divisor (GCD) of intervals
       d. The period is likely a multiple of this GCD
       e. Use autocorrelation of the value signal to confirm
    3. Set animation.period = detected_period

    The period is used by the loop aligner to ensure seamless loops.

    Args:
        animations: Dict mapping animation_name -> AnimationIR.
        model_name: Optional model name for logging context.

    Returns:
        New dict of animations with period set.
    """
    result: Dict[str, AnimationIR] = {}

    for anim_name, anim in animations.items():
        period: Optional[float] = None

        # Strategy 1: Trust the source-provided animation length
        if anim.length > 0:
            period = anim.length
            logger.debug(
                "[%s] %s: Using source length %.4f as period",
                model_name, anim_name, period,
            )
        else:
            # Strategy 2: Detect from keyframe data
            period = _detect_period_from_data(anim, model_name)
            if period is not None:
                logger.debug(
                    "[%s] %s: Detected period %.4f from data",
                    model_name, anim_name, period,
                )
            else:
                logger.debug(
                    "[%s] %s: Could not detect period",
                    model_name, anim_name,
                )

        # Create new AnimationIR with period set
        result[anim_name] = AnimationIR(
            name=anim.name,
            loop=anim.loop,
            length=anim.length,
            bones=anim.bones,
            period=period,
        )

    return result
