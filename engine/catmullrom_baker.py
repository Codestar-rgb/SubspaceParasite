#!/usr/bin/env python3
"""
Super Architecture — CatmullRom Baking  (v5.0 — Smooth Loop Edition)
=====================================================================

Bake CatmullRom animation curves into dense linear keyframes to avoid
Blockbench's CatmullRom loop boundary wrapping bug.

PROBLEM:
  Blockbench issue #1965: When using smooth (CatmullRom) interpolation
  in looping animations, the last keyframe is NOT properly interpolated
  with the first keyframe of the loop. This causes a visible tangent
  discontinuity at the loop boundary — the animation briefly "pops" or
  "flashes" at each cycle boundary.

  The Bedrock format does NOT enable `animation_loop_wrapping`, so
  Blockbench uses wrong control points for the CatmullRom spline at
  the loop boundary, causing chord-length parameterization distortion.

  ADDITIONAL PROBLEMS (v5.0 fixes):
  1. UNEVEN KEYFRAME SPACING: The previous baker preserved original
     keyframe times alongside regular 0.02s samples. This created
     tiny gaps (0.006-0.013s) near original keyframe times. With
     linear interpolation, these uneven gaps caused velocity micro-
     fluctuations — perceived as animation "stutter" or "jerkiness".

  2. LOOP BOUNDARY TANGENT: The previous baker used linear extrapolation
     for CatmullRom control points at the loop boundary (first/last
     segments). For looping animations, this produces incorrect tangent
     directions near t=0 and t=anim_length, causing the baked keyframes
     near the boundary to have slightly wrong velocities.

SOLUTION:
  1. Sample ONLY at regular intervals (0.02s = 50fps). Do NOT preserve
     original keyframe times in the output. The CatmullRom curve is
     evaluated at regular sample points, which provides uniform spacing
     and eliminates velocity micro-fluctuations.

  2. For LOOPING animations, use proper CatmullRom loop wrapping:
     - First segment's "previous" control point = second-to-last keyframe
     - Last segment's "next" control point = second keyframe
     This ensures C1 continuity across the loop boundary.

  3. Always include a keyframe at t=0 AND t=anim_length (matching values),
     ensuring the loop boundary is seamless.

ALGORITHM:
  For each CatmullRom keyframe segment:
    1. Extract per-axis time series (control points for the curve)
    2. If looping, wrap control points at boundaries for C1 continuity
    3. Sample at regular 0.02s intervals from t=0 to t=anim_length
    4. Evaluate CatmullRom spline at each sample time
    5. Replace with linear keyframes (uniform spacing, no jitter)
  
  For linear keyframes: pass through unchanged (no baking needed).

DENSITY:
  50fps (0.02s interval) provides smooth animation even for fast walk
  cycles (0.6667s = 33 keyframes per cycle). All gaps are exactly 0.02s,
  ensuring constant-velocity linear interpolation.
"""

from __future__ import annotations

import logging
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
# Configuration
# ---------------------------------------------------------------------------

# Target sampling interval for baked linear keyframes (seconds).
# One keyframe every 0.02s = 50fps, provides smooth animation even for
# fast walk cycles (0.6667s = ~33 keyframes per cycle).
BAKE_SAMPLE_INTERVAL: float = 0.02

# Minimum segment duration to trigger baking.
# Segments shorter than this are already dense enough.
MIN_SEGMENT_DURATION_FOR_BAKE: float = 0.03


# ---------------------------------------------------------------------------
# CatmullRom evaluation
# ---------------------------------------------------------------------------

def _catmull_rom_eval(
    s: float,
    v0: float, v1: float, v2: float, v3: float,
) -> float:
    """Evaluate CatmullRom spline at parameter s in [0, 1].

    Uses the standard CatmullRom matrix formulation.
    Matches Blockbench/THREE.SplineCurve behavior.

    Args:
        s: Parameter in [0, 1] (0 = v1, 1 = v2).
        v0: Previous control point.
        v1: Start value.
        v2: End value.
        v3: Next control point.

    Returns:
        Interpolated value at parameter s.
    """
    s2 = s * s
    s3 = s2 * s

    c0 = 2.0 * v1
    c1 = -v0 + v2
    c2 = 2.0 * v0 - 5.0 * v1 + 4.0 * v2 - v3
    c3 = -v0 + 3.0 * v1 - 3.0 * v2 + v3

    return 0.5 * (c0 + c1 * s + c2 * s2 + c3 * s3)


def _get_catmullrom_value(
    t: float,
    kf_times: List[float],
    kf_values: List[float],
    is_loop: bool = False,
) -> float:
    """Evaluate a CatmullRom curve at time t from keyframe time-value pairs.

    For looping animations (is_loop=True), uses proper loop wrapping
    for control points at the boundaries to ensure C1 continuity
    across the loop boundary.

    Args:
        t: Time to evaluate at.
        kf_times: Sorted list of keyframe times.
        kf_values: Corresponding keyframe values.
        is_loop: Whether the animation loops (affects boundary handling).

    Returns:
        Interpolated value at time t.
    """
    n = len(kf_times)
    if n == 0:
        return 0.0
    if n == 1:
        return kf_values[0]

    # Clamp to range
    if t <= kf_times[0]:
        return kf_values[0]
    if t >= kf_times[-1]:
        return kf_values[-1]

    # Find segment (binary search)
    lo, hi = 0, n - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if kf_times[mid] <= t:
            lo = mid
        else:
            hi = mid

    idx = lo  # t is between kf_times[idx] and kf_times[idx+1]

    # Compute local parameter s in [0, 1]
    dt = kf_times[idx + 1] - kf_times[idx]
    if dt < 1e-12:
        return kf_values[idx]
    s = (t - kf_times[idx]) / dt

    # Control points
    v1 = kf_values[idx]
    v2 = kf_values[idx + 1]

    # Previous control point
    if idx > 0:
        v0 = kf_values[idx - 1]
    elif is_loop and n >= 3:
        # Loop wrapping: the point "before" the first keyframe is the
        # second-to-last keyframe (the last keyframe = first keyframe
        # for looping, so we go one step further back).
        # This ensures C1 tangent continuity at the loop boundary.
        v0 = kf_values[-2]
    else:
        v0 = 2.0 * v1 - v2  # Linear extrapolation (non-loop)

    # Next control point
    if idx + 2 < n:
        v3 = kf_values[idx + 2]
    elif is_loop and n >= 3:
        # Loop wrapping: the point "after" the last keyframe is the
        # second keyframe (the first keyframe = last keyframe for
        # looping, so we go one step further forward).
        v3 = kf_values[1]
    else:
        v3 = 2.0 * v2 - v1  # Linear extrapolation (non-loop)

    return _catmull_rom_eval(s, v0, v1, v2, v3)


# ---------------------------------------------------------------------------
# Single animation baking
# ---------------------------------------------------------------------------

def bake_animation(anim: AnimationIR) -> AnimationIR:
    """Bake CatmullRom keyframes into dense linear keyframes.

    For each bone, for each channel:
      1. Extract per-axis time series from keyframes
      2. If the channel uses catmullrom, sample it at regular intervals
      3. Replace catmullrom keyframes with sampled linear keyframes
      4. Linear keyframes are passed through unchanged

    Args:
        anim: The AnimationIR to bake.

    Returns:
        New AnimationIR with baked linear keyframes.
    """
    is_loop = anim.loop == "loop"

    new_bones: Dict[str, BoneAnimationIR] = {}

    for bone_name, bone_anim in anim.bones.items():
        new_keyframes = _bake_bone_keyframes(
            bone_anim.keyframes, anim.length, is_loop
        )
        new_bones[bone_name] = BoneAnimationIR(
            bone_name=bone_name,
            keyframes=new_keyframes,
        )

    return AnimationIR(
        name=anim.name,
        loop=anim.loop,
        length=anim.length,
        bones=new_bones,
        period=anim.period,
    )


def _bake_bone_keyframes(
    keyframes: List[KeyframeData],
    anim_length: float,
    is_loop: bool = False,
) -> List[KeyframeData]:
    """Bake CatmullRom keyframes for one bone into linear keyframes.

    Args:
        keyframes: All keyframes for this bone.
        anim_length: Animation length for sampling range.
        is_loop: Whether the animation loops.

    Returns:
        New list of keyframes with CatmullRom baked to linear.
    """
    if not keyframes:
        return []

    result: List[KeyframeData] = []

    # Group by channel
    channel_kfs: Dict[str, List[KeyframeData]] = {}
    for kf in keyframes:
        if kf.channel not in channel_kfs:
            channel_kfs[kf.channel] = []
        channel_kfs[kf.channel].append(kf)

    for channel in CHANNELS:
        kfs = channel_kfs.get(channel, [])
        if not kfs:
            continue

        # Sort by time
        kfs_sorted = sorted(kfs, key=lambda kf: kf.time)

        # Check if any keyframe uses catmullrom
        has_catmullrom = any(kf.interpolation == "catmullrom" for kf in kfs_sorted)

        if not has_catmullrom:
            # All linear — pass through
            result.extend(kfs_sorted)
            continue

        # Bake catmullrom → linear with dense sampling
        baked_kfs = _bake_channel_catmullrom(
            kfs_sorted, channel, anim_length, is_loop
        )
        result.extend(baked_kfs)

    # Sort by time, then channel
    result.sort(key=lambda kf: (kf.time, kf.channel))

    return result


def _bake_channel_catmullrom(
    keyframes: List[KeyframeData],
    channel: str,
    anim_length: float,
    is_loop: bool = False,
) -> List[KeyframeData]:
    """Bake CatmullRom keyframes for one channel into dense linear keyframes.

    KEY FIXES (v5.0):
    1. Sample ONLY at regular 0.02s intervals — no original keyframe times.
       This ensures uniform spacing and eliminates velocity micro-fluctuations.
    2. Use proper CatmullRom loop wrapping for boundary control points
       when is_loop=True, ensuring C1 continuity across the loop boundary.
    3. Always include keyframes at t=0 and t=anim_length with matching values.

    Args:
        keyframes: Sorted keyframes for one channel.
        channel: Channel name.
        anim_length: Animation length.
        is_loop: Whether the animation loops.

    Returns:
        New list of linear keyframes with baked CatmullRom values.
    """
    # Extract per-axis time series (these are the CatmullRom CONTROL POINTS)
    axis_times: Dict[str, List[float]] = {}
    axis_values: Dict[str, List[float]] = {}
    axis_molang: Dict[str, str] = {}

    for axis in AXES:
        times = []
        values = []
        for kf in keyframes:
            av: AxisValue = getattr(kf, axis)
            if av.explicit:
                times.append(kf.time)
                values.append(av.value)
            molang_attr = f"molang_{axis}"
            molang_expr = getattr(kf, molang_attr, "")
            if molang_expr:
                axis_molang[axis] = molang_expr

        axis_times[axis] = times
        axis_values[axis] = values

    # ---- Generate UNIFORM sample times ----
    # KEY FIX (v5.0): Use ADAPTIVE interval that divides evenly into
    # anim_length. This ensures perfectly uniform spacing with NO
    # short gaps at the loop boundary.
    #
    # Problem with fixed 0.02s: anim_length=0.6667 / 0.02 = 33.335
    # → last gap is only 0.0067s (0.6667 - 0.66), causing micro-stutter.
    #
    # Solution: Round the number of segments to the nearest integer,
    # then compute the exact interval as anim_length / num_segments.
    # For 0.6667s: num_segments = 33, interval = 0.6667/33 = 0.020202s
    # → perfectly uniform: 0.0, 0.0202, 0.0404, ..., 0.6667

    if anim_length <= 0:
        # Fallback: use keyframe range
        min_time = min(kf.time for kf in keyframes)
        max_time = max(kf.time for kf in keyframes)
        effective_length = max_time - min_time
    else:
        min_time = 0.0
        max_time = anim_length
        effective_length = anim_length

    sample_times: List[float] = []

    if effective_length > 0:
        # Compute adaptive interval that divides evenly
        num_segments = max(1, round(effective_length / BAKE_SAMPLE_INTERVAL))
        adaptive_interval = effective_length / num_segments

        for i in range(num_segments + 1):
            t = min_time + i * adaptive_interval
            sample_times.append(round(t, 8))
    else:
        # Single keyframe animation
        sample_times.append(round(min_time, 8))

    # ---- Evaluate CatmullRom at each sample time ----
    result: List[KeyframeData] = []

    for t in sample_times:
        vals: Dict[str, float] = {}
        for axis in AXES:
            if axis_times[axis] and axis_values[axis]:
                vals[axis] = _get_catmullrom_value(
                    t, axis_times[axis], axis_values[axis], is_loop
                )
            elif axis_times[axis]:
                # No values — use 0.0
                vals[axis] = 0.0
            else:
                vals[axis] = 0.0

        is_molang = bool(axis_molang)

        kf = KeyframeData(
            time=t,
            channel=channel,
            x=AxisValue.explicit_val(vals["x"]),
            y=AxisValue.explicit_val(vals["y"]),
            z=AxisValue.explicit_val(vals["z"]),
            easing="linear",
            interpolation="linear",  # Baked → always linear
            is_molang=is_molang,
            molang_x=axis_molang.get("x", ""),
            molang_y=axis_molang.get("y", ""),
            molang_z=axis_molang.get("z", ""),
        )
        result.append(kf)

    return result


# ---------------------------------------------------------------------------
# Apply to all animations
# ---------------------------------------------------------------------------

def bake_all_animations(
    animations: List[AnimationIR],
    model_name: str = "",
) -> List[AnimationIR]:
    """Bake CatmullRom keyframes in all animations to linear.

    Args:
        animations: List of AnimationIR instances.
        model_name: Model name for logging.

    Returns:
        New list of AnimationIR with baked keyframes.
    """
    result: List[AnimationIR] = []
    baked_count = 0

    for anim in animations:
        # Bake ALL animations that have CatmullRom keyframes.
        # Previously only loop animations were baked, but non-loop
        # animations also benefit from baking to ensure consistent
        # interpolation behavior in Blockbench.
        has_catmullrom = any(
            kf.interpolation == "catmullrom"
            for bone in anim.bones.values()
            for kf in bone.keyframes
        )
        if has_catmullrom or anim.loop == "loop":
            baked = bake_animation(anim)
            baked_count += 1
            result.append(baked)
        else:
            result.append(anim)

    if baked_count > 0:
        logger.info(
            "[%s] CatmullRomBaker: baked %d/%d loop animations to linear",
            model_name, baked_count, len(animations),
        )

    return result
