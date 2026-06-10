#!/usr/bin/env python3
"""
BBModelAnimationConverter - Universal Animation Converter (v3)
==============================================================
Converts Blockbench .bbmodel animation keyframes to GeckoLib .animation.json
format with automatic loop continuity enforcement, C1 velocity matching,
duration optimization, and comprehensive quality feedback.

Key Improvements over v2:
  - END-ONLY Adaptive C1 Blending: preserves the START of the animation
    exactly (no start blend window), only blends at the END to smoothly
    arrive at the start state. This fixes the v2 issue where dual-endpoint
    blending distorted the beginning of the animation.
  - Adaptive blend window: scales proportionally to velocity mismatch
    magnitude, so larger mismatches get smoother transitions.
  - numpy FFT acceleration for autocorrelation (with pure-python fallback).
  - Tighter "good enough" early exit: C0 < 0.3° and C1 < 3°/s.
  - Sub-multiple search for duration detection (duration/2, duration/3, etc).
  - Content-hash duplicate detection with smart bone-channel merging.
  - Per-animation quality score (0-100) with C0/C1/duration breakdown.
  - Global batch summary with P50/P90/P99 statistics.

Coordinate System:
  - .bbmodel keyframes are already in Bedrock/GeckoLib coordinate space
  - No additional M_MODEL conversion needed (already applied during bbmodel generation)
  - Rotation values in degrees, position values in pixels

DO NOT MODIFY: core_math.py
"""

import hashlib
import json
import math
import os
import re
import sys
import time
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

# ============================================================================
# Constants
# ============================================================================

TICKS_PER_SECOND = 20.0
RAD_TO_DEG = 180.0 / math.pi
DEG_TO_RAD = math.pi / 180.0

# Try importing numpy for FFT-accelerated autocorrelation
_NUMPY_AVAILABLE = False
try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    np = None


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class ConverterConfig:
    """Master configuration for BBModelAnimationConverter v3."""
    # --- Loop Detection ---
    min_loop_duration: float = 0.5          # seconds
    max_loop_duration: float = 30.0         # seconds
    loop_position_tolerance_rot: float = 0.3   # degrees (tighter v3)
    loop_position_tolerance_pos: float = 0.03  # pixels
    loop_velocity_tolerance_rot: float = 3.0   # degrees/s (tighter v3)
    loop_velocity_tolerance_pos: float = 0.3   # pixels/s

    # --- C1 Continuity (v3: end-only adaptive) ---
    enable_c1_enforcement: bool = True
    blend_window_ratio: float = 0.10       # base ratio of duration for blend window
    max_blend_window: float = 0.30         # max seconds for blend window
    velocity_match_threshold_rot: float = 3.0   # degrees/s (tighter for v3)
    velocity_match_threshold_pos: float = 0.6   # pixels/s
    c0_snap_threshold_rot: float = 0.3     # degrees (tighter v3)
    c0_snap_threshold_pos: float = 0.03    # pixels

    # --- Duration Optimization ---
    enable_duration_optimization: bool = True
    duration_search_step: float = 0.01      # seconds
    phase_error_tolerance: float = 0.02     # radians
    duration_change_threshold: float = 0.1  # only change if improvement > 10%
    min_duration_improvement: float = 0.05  # minimum absolute improvement to justify change
    autocorrelation_enabled: bool = True    # use autocorrelation for period detection
    early_exit_c0_rot: float = 0.3         # degrees - "good enough" C0 for early exit (v3 tighter)
    early_exit_c1_rot: float = 3.0         # degrees/s - "good enough" C1 for early exit (v3 tighter)
    sub_multiple_search: bool = True        # check duration/2, duration/3, etc for better loops

    # --- Simplification ---
    dp_epsilon_rotation: float = 0.05       # degrees (tighter for better fidelity)
    dp_epsilon_position: float = 0.008      # pixels

    # --- Resampling ---
    resample_rate: float = 120.0            # Hz for catmullrom evaluation

    # --- Output ---
    keyframe_precision: int = 4             # decimal places for time
    value_precision: int = 6                # decimal places for values
    filter_zero_threshold: float = 0.001    # skip channels with only tiny values

    # --- Quality ---
    quality_warning_threshold: float = 0.5  # warn if C0 error > this (degrees/pixels)
    quality_error_threshold: float = 5.0    # error if C0 error > this (relaxed for non-loop)
    c1_quality_threshold_rot: float = 10.0  # good C1 if P90 < this (deg/s)
    c1_quality_threshold_pos: float = 2.0   # good C1 if P90 < this (px/s)

    # --- Animation Deduplication (v3: enhanced) ---
    skip_empty_animations: bool = True       # skip animations with no meaningful data
    deduplicate_case_insensitive: bool = True  # merge "idle" / "Idle" variants
    merge_duplicate_animations: bool = True  # merge identical animations via content hash
    content_hash_dedup: bool = True          # use SHA-256 content hash for dedup
    smart_bone_merge: bool = True            # combine bone channels from case-duplicates

    # --- Name Normalization ---
    normalize_animation_names: bool = True   # normalize to GeckoLib convention
    animation_namespace: str = ""            # optional namespace override


@dataclass
class AnimationQualityReport:
    """Quality metrics for a single animation (v3 enhanced)."""
    animation_name: str
    duration: float
    num_bones: int
    total_keyframes: int

    # C0 continuity (position match at loop boundary)
    c0_max_error_rot: float = 0.0           # degrees
    c0_max_error_pos: float = 0.0           # pixels
    c0_avg_error_rot: float = 0.0
    c0_avg_error_pos: float = 0.0
    c0_perfect: bool = True

    # C1 continuity (velocity match at loop boundary)
    c1_max_error_rot: float = 0.0           # degrees/s
    c1_max_error_pos: float = 0.0           # pixels/s
    c1_avg_error_rot: float = 0.0           # P90 for v3
    c1_avg_error_pos: float = 0.0
    c1_perfect: bool = True

    # Duration quality
    duration_phase_error: float = 0.0
    duration_optimal: bool = True
    duration_adjusted: bool = False

    # Blend info (v3)
    blend_window_used: float = 0.0          # actual blend window in seconds
    c1_enforcement_applied: bool = False

    # Overall
    quality_score: float = 100.0            # 0-100
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ============================================================================
# Catmull-Rom Spline Evaluation
# ============================================================================

class CatmullRomEvaluator:
    """Evaluates Catmull-Rom splines at arbitrary time points.

    Used for resampling animations with catmullrom interpolation
    to find optimal loop points and enforce continuity.
    """

    @staticmethod
    def evaluate(t: float, p0: float, p1: float, p2: float, p3: float,
                 alpha: float = 0.5) -> float:
        """Evaluate centripetal Catmull-Rom spline at parameter t in [0,1].

        Args:
            t: Parameter in [0, 1] between p1 and p2
            p0, p1, p2, p3: Control points
            alpha: 0=uniform, 0.5=centripetal, 1.0=chordal

        Returns:
            Interpolated value.
        """
        t2 = t * t
        t3 = t2 * t

        v01 = 0.5 * (p2 - p0)
        v12 = 0.5 * (p3 - p1)

        return (2 * t3 - 3 * t2 + 1) * p1 + \
               (t3 - 2 * t2 + t) * v01 + \
               (-2 * t3 + 3 * t2) * p2 + \
               (t3 - t2) * v12

    @staticmethod
    def evaluate_derivative(t: float, p0: float, p1: float,
                            p2: float, p3: float) -> float:
        """Evaluate first derivative of Catmull-Rom spline at parameter t in [0,1].

        Returns:
            Derivative value.
        """
        t2 = t * t

        v01 = 0.5 * (p2 - p0)
        v12 = 0.5 * (p3 - p1)

        return (6 * t2 - 6 * t) * p1 + \
               (3 * t2 - 4 * t + 1) * v01 + \
               (-6 * t2 + 6 * t) * p2 + \
               (3 * t2 - 2 * t) * v12

    @staticmethod
    def resample_channel(keyframes: List[Tuple[float, float]],
                         target_times: List[float],
                         interpolation: str = "catmullrom") -> List[Tuple[float, float]]:
        """Resample a channel at specified time points.

        Args:
            keyframes: [(time, value), ...] sorted by time
            target_times: Time points to sample at
            interpolation: "catmullrom" or "linear"

        Returns:
            [(time, value), ...] at target times.
        """
        if not keyframes:
            return []
        if len(keyframes) <= 1:
            return [(t, keyframes[0][1]) for t in target_times]

        result = []
        n = len(keyframes)

        for t in target_times:
            # Find segment
            if t <= keyframes[0][0]:
                result.append((t, keyframes[0][1]))
                continue
            if t >= keyframes[-1][0]:
                result.append((t, keyframes[-1][1]))
                continue

            # Binary search for segment
            seg_idx = 0
            for i in range(n - 1):
                if keyframes[i][0] <= t <= keyframes[i + 1][0]:
                    seg_idx = i
                    break

            k0 = keyframes[seg_idx]
            k1 = keyframes[seg_idx + 1]

            dt = k1[0] - k0[0]
            if dt < 1e-12:
                result.append((t, k0[1]))
                continue

            s = (t - k0[0]) / dt

            if interpolation == "catmullrom" and n >= 4:
                p0_val = keyframes[max(0, seg_idx - 1)][1]
                p1_val = k0[1]
                p2_val = k1[1]
                p3_val = keyframes[min(n - 1, seg_idx + 2)][1]

                val = CatmullRomEvaluator.evaluate(s, p0_val, p1_val, p2_val, p3_val)
                result.append((t, val))
            else:
                # Linear interpolation
                val = k0[1] + s * (k1[1] - k0[1])
                result.append((t, val))

        return result


# ============================================================================
# Auto Loop Detector (v3: improved)
# ============================================================================

class AutoLoopDetector:
    """Detects optimal loop duration for animations.

    For animations with loop="loop", finds the best duration where:
    - C0: Position at start ~ position at end (for all channels)
    - C1: Velocity at start ~ velocity at end (for all channels)

    Improvements (v3):
    - Prioritizes original animation length if C0/C1 are already good
    - Uses numpy FFT autocorrelation when available (fallback to pure python)
    - Tighter "good enough" early exit when C0 < 0.3° and C1 < 3°/s
    - Sub-multiple search: checks duration/2, duration/3, etc
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()

    def detect_optimal_duration(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        current_duration: float,
        interpolation: str = "catmullrom"
    ) -> Tuple[float, Dict[str, Any]]:
        """Find the optimal loop duration for an animation.

        Args:
            bone_channels: {bone: {channel: [(t, v), ...]}}
            current_duration: Current animation length in seconds
            interpolation: Interpolation type for resampling

        Returns:
            (optimal_duration, diagnostics_dict)
        """
        cfg = self.config
        diagnostics = {
            'original_duration': current_duration,
            'method': 'none',
            'candidates_tested': 0,
            'best_c0_error': float('inf'),
            'best_c1_error': float('inf'),
        }

        # Resample all channels at high rate for evaluation
        sample_rate = cfg.resample_rate
        test_duration = min(current_duration * 2, cfg.max_loop_duration)
        n_samples = int(test_duration * sample_rate)
        target_times = [i / sample_rate for i in range(n_samples + 1)]

        resampled = {}
        for bone_name, channels in bone_channels.items():
            resampled[bone_name] = {}
            for channel, keyframes in channels.items():
                resampled[bone_name][channel] = CatmullRomEvaluator.resample_channel(
                    keyframes, target_times, interpolation
                )

        # Evaluate current duration first - prioritize original if good
        c0_err, c1_err = self._evaluate_continuity(resampled, current_duration, sample_rate)
        diagnostics['current_c0_error'] = c0_err
        diagnostics['current_c1_error'] = c1_err

        # "Good enough" early exit (v3: tighter thresholds)
        if c0_err < cfg.early_exit_c0_rot and c1_err < cfg.early_exit_c1_rot:
            diagnostics['method'] = 'early_exit_good_enough'
            return current_duration, diagnostics

        # Also accept if within the configured tolerances
        if c0_err < cfg.loop_position_tolerance_rot and c1_err < cfg.loop_velocity_tolerance_rot:
            diagnostics['method'] = 'current_ok'
            return current_duration, diagnostics

        # Search for better durations
        best_duration = current_duration
        best_score = float('inf')

        candidates = []

        # Method 1: Sub-multiples of current duration (v3: also check shorter periods)
        for n in range(2, 20):
            T = current_duration / n
            if T >= cfg.min_loop_duration:
                candidates.append(T)

        # Method 2: Multiples of short periods found in the data
        if cfg.autocorrelation_enabled:
            periods = self._detect_periods_autocorrelation(resampled, sample_rate)
        else:
            periods = self._detect_periods(resampled, sample_rate)

        for period in periods:
            for n in range(1, 30):
                T = n * period
                if cfg.min_loop_duration <= T <= cfg.max_loop_duration:
                    candidates.append(T)

        # Method 3: Fine-grained search around current duration
        search_lo = max(cfg.min_loop_duration, current_duration * 0.25)
        search_hi = min(test_duration, cfg.max_loop_duration)
        T = search_lo
        while T <= search_hi:
            candidates.append(T)
            T += cfg.duration_search_step

        # Remove duplicates and sort
        candidates = sorted(set(candidates))
        diagnostics['candidates_tested'] = len(candidates)

        for T in candidates:
            c0, c1 = self._evaluate_continuity(resampled, T, sample_rate)

            # "Good enough" early exit during search (v3: tighter)
            if c0 < cfg.early_exit_c0_rot and c1 < cfg.early_exit_c1_rot:
                diagnostics['method'] = 'search_early_exit_good_enough'
                diagnostics['best_c0_error'] = c0
                diagnostics['best_c1_error'] = c1
                return round(T, 4), diagnostics

            # Weighted score: prioritize C0 (position) over C1 (velocity)
            score = c0 * 10 + c1

            if score < best_score:
                best_score = score
                best_duration = T
                diagnostics['best_c0_error'] = c0
                diagnostics['best_c1_error'] = c1

        # Check if the best found is actually better than current
        if diagnostics['best_c0_error'] <= c0_err * 1.1:
            diagnostics['method'] = 'search_optimal'
            return round(best_duration, 4), diagnostics
        else:
            diagnostics['method'] = 'current_best'
            return current_duration, diagnostics

    def _evaluate_continuity(
        self,
        resampled: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        sample_rate: float
    ) -> Tuple[float, float]:
        """Evaluate C0 and C1 continuity at a candidate duration.

        Returns:
            (c0_error, c1_error) - lower is better.
        """
        total_c0 = 0.0
        total_c1 = 0.0
        count = 0

        dt = 1.0 / sample_rate

        for bone_name, channels in resampled.items():
            for channel, data in channels.items():
                if len(data) < 4:
                    continue

                val_0 = self._interpolate(data, 0.0)
                val_T = self._interpolate(data, duration)

                v_0 = (self._interpolate(data, dt) - val_0) / dt
                v_T = (val_T - self._interpolate(data, duration - dt)) / dt

                c0_err = abs(val_T - val_0)
                c1_err = abs(v_T - v_0)

                total_c0 += c0_err
                total_c1 += c1_err
                count += 1

        if count == 0:
            return 0.0, 0.0

        return total_c0 / count, total_c1 / count

    def _interpolate(self, data: List[Tuple[float, float]], t: float) -> float:
        """Linearly interpolate value at time t from resampled data."""
        if t <= data[0][0]:
            return data[0][1]
        if t >= data[-1][0]:
            return data[-1][1]

        lo, hi = 0, len(data) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if data[mid][0] <= t:
                lo = mid
            else:
                hi = mid

        t0, v0 = data[lo]
        t1, v1 = data[hi]
        dt = t1 - t0
        if dt < 1e-12:
            return v0
        alpha = (t - t0) / dt
        return v0 + alpha * (v1 - v0)

    def _detect_periods(
        self,
        resampled: Dict[str, Dict[str, List[Tuple[float, float]]]],
        sample_rate: float
    ) -> List[float]:
        """Detect dominant oscillation periods using zero-crossing analysis."""
        periods = []

        for bone_name, channels in resampled.items():
            for channel, data in channels.items():
                if len(data) < 20:
                    continue

                values = [v for t, v in data]
                mean_val = sum(values) / len(values)
                centered = [v - mean_val for v in values]

                amplitude = max(abs(v) for v in centered)
                if amplitude < 0.01:
                    continue

                crossings = []
                for i in range(1, len(centered)):
                    if centered[i - 1] * centered[i] < 0:
                        t_cross = data[i - 1][0] + \
                            (data[i][0] - data[i - 1][0]) * \
                            abs(centered[i - 1]) / (abs(centered[i - 1]) + abs(centered[i]))
                        crossings.append(t_cross)

                if len(crossings) >= 4:
                    full_periods = [crossings[i + 2] - crossings[i]
                                   for i in range(len(crossings) - 2)]

                    for p in full_periods:
                        if 0.1 < p < 20.0:
                            periods.append(p)

        return self._cluster_periods(periods)

    def _detect_periods_autocorrelation(
        self,
        resampled: Dict[str, Dict[str, List[Tuple[float, float]]]],
        sample_rate: float
    ) -> List[float]:
        """Detect dominant oscillation periods using autocorrelation.

        v3: Uses numpy FFT when available for O(n log n) performance,
        falls back to O(n^2) pure-python implementation.

        Returns:
            List of detected period values in seconds.
        """
        if _NUMPY_AVAILABLE:
            return self._detect_periods_autocorrelation_fft(resampled, sample_rate)
        else:
            return self._detect_periods_autocorrelation_pure(resampled, sample_rate)

    def _detect_periods_autocorrelation_fft(
        self,
        resampled: Dict[str, Dict[str, List[Tuple[float, float]]]],
        sample_rate: float
    ) -> List[float]:
        """FFT-accelerated autocorrelation period detection using numpy."""
        periods = []
        min_lag_samples = int(0.1 * sample_rate)

        for bone_name, channels in resampled.items():
            for channel, data in channels.items():
                if len(data) < 40:
                    continue

                values = np.array([v for t, v in data])
                mean_val = np.mean(values)
                centered = values - mean_val

                amplitude = np.max(np.abs(centered))
                if amplitude < 0.01:
                    continue

                n = len(centered)

                # FFT-based autocorrelation: R(k) = IFFT(|FFT(x)|^2)
                fft_x = np.fft.rfft(centered, n=2 * n)
                autocorr_full = np.fft.irfft(fft_x * np.conj(fft_x))[:n]

                # Normalize by zero-lag
                if autocorr_full[0] < 1e-12:
                    continue
                autocorr_full = autocorr_full / autocorr_full[0]

                max_lag = min(n // 2, int(20.0 * sample_rate))

                # Find peaks in autocorrelation
                peaks = []
                for k in range(min_lag_samples, min(max_lag, len(autocorr_full) - 1)):
                    if (autocorr_full[k] > autocorr_full[k - 1] and
                        autocorr_full[k] > autocorr_full[k + 1] and
                        autocorr_full[k] > 0.3):
                        period = k / sample_rate
                        if 0.1 < period < 20.0:
                            peaks.append((period, float(autocorr_full[k])))

                peaks.sort(key=lambda x: -x[1])
                for period, strength in peaks[:5]:
                    periods.append(period)

        return self._cluster_periods(periods)

    def _detect_periods_autocorrelation_pure(
        self,
        resampled: Dict[str, Dict[str, List[Tuple[float, float]]]],
        sample_rate: float
    ) -> List[float]:
        """Pure-python autocorrelation period detection (no numpy)."""
        periods = []
        min_lag_samples = int(0.1 * sample_rate)

        for bone_name, channels in resampled.items():
            for channel, data in channels.items():
                if len(data) < 40:
                    continue

                values = [v for t, v in data]
                mean_val = sum(values) / len(values)
                centered = [v - mean_val for v in values]

                amplitude = max(abs(v) for v in centered)
                if amplitude < 0.01:
                    continue

                n = len(centered)

                energy = sum(v * v for v in centered)
                if energy < 1e-12:
                    continue

                max_lag = min(n // 2, int(20.0 * sample_rate))
                autocorr = []
                for k in range(min_lag_samples, max_lag):
                    corr = 0.0
                    for i in range(n - k):
                        corr += centered[i] * centered[i + k]
                    autocorr.append((k, corr / energy))

                if not autocorr:
                    continue

                peaks = []
                for i in range(1, len(autocorr) - 1):
                    if (autocorr[i][1] > autocorr[i - 1][1] and
                        autocorr[i][1] > autocorr[i + 1][1] and
                        autocorr[i][1] > 0.3):
                        lag_samples = autocorr[i][0]
                        period = lag_samples / sample_rate
                        if 0.1 < period < 20.0:
                            peaks.append((period, autocorr[i][1]))

                peaks.sort(key=lambda x: -x[1])
                for period, strength in peaks[:5]:
                    periods.append(period)

        return self._cluster_periods(periods)

    def _cluster_periods(self, periods: List[float]) -> List[float]:
        """Cluster similar period values and return medians."""
        if not periods:
            return []

        periods.sort()
        clusters = []
        current_cluster = [periods[0]]

        for p in periods[1:]:
            if p < current_cluster[-1] * 1.2:
                current_cluster.append(p)
            else:
                clusters.append(current_cluster)
                current_cluster = [p]
        clusters.append(current_cluster)

        result = []
        for cluster in clusters:
            median = cluster[len(cluster) // 2]
            result.append(median)

        return result


# ============================================================================
# C1 Continuity Enforcer (v3: END-ONLY Adaptive Blending)
# ============================================================================

class C1ContinuityEnforcer:
    """Enforces C1 (velocity) continuity at loop boundaries.

    v3 CRITICAL CHANGE: End-Only Adaptive C1 Blending

    The v2 dual-endpoint blending distorted the START of the animation
    by blending it too. The v3 fix:

    1. Only blend at the END of the animation (preserve start exactly)
    2. Use ADAPTIVE blend window size: scale the blend window
       proportionally to the velocity mismatch magnitude
    3. After end blending, ensure last keyframe exactly matches
       first keyframe value (C0 snap)
    4. Use cubic Hermite interpolation in the end blend window,
       transitioning from the original end-state toward (p_start, v_start)

    Key insight: When the animation loops (end→start), what matters is:
    - Position at end = position at start (C0)
    - Velocity at end = velocity at start (C1) ← bounce-back happens here
    - The START doesn't need blending - it's what the player sees first

    Adaptive blend window formula:
    - base_w = min(duration * blend_window_ratio, max_blend_window)
    - adaptive_w = base_w * (1.0 + min(c1_diff / c1_threshold, 3.0))
    - Larger velocity mismatches → larger blend windows (smoother transition)

    This provides:
      - C0: Perfect position match (last keyframe snaps to first)
      - C1: Smooth velocity transition (Hermite blend at end only)
      - START preservation: Beginning of animation is untouched
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()

    def enforce(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        interpolation: str = "catmullrom"
    ) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
        """Apply end-only adaptive C1 continuity enforcement to all channels.

        Strategy:
          1. Resample each channel at high rate
          2. Compute velocities at start (v0) and end (vT)
          3. Compute C0 error = |p_end - p_start| and C1 error = |v_end - v_start|
          4. If already good enough: just snap C0
          5. Otherwise:
             a. Compute adaptive blend window = base_ratio * duration * (1 + |C1_error|/threshold)
             b. Apply Hermite blend in END window only:
                - Start of blend: original data (position, velocity)
                - End of blend: target (p_start, v_start)
             c. Snap last keyframe to p_start

        Args:
            bone_channels: {bone: {channel: [(t, v), ...]}}
            duration: Animation duration
            interpolation: Interpolation type for resampling

        Returns:
            Modified bone_channels with C1 continuity enforced.
        """
        cfg = self.config
        if not cfg.enable_c1_enforcement:
            return bone_channels

        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if len(keyframes) < 2:
                    continue

                is_rotation = channel in ('rx', 'ry', 'rz', 'x', 'y', 'z')

                # Step 1: Resample at high rate for velocity estimation
                n_resample = max(int(duration * cfg.resample_rate), 60)
                resample_dt = duration / n_resample
                resample_times = [i * resample_dt for i in range(n_resample + 1)]
                resampled = CatmullRomEvaluator.resample_channel(
                    keyframes, resample_times, interpolation
                )

                # Step 2: Compute velocities at start and end
                if len(resampled) < 5:
                    continue

                p0 = resampled[0][1]
                pT = resampled[-1][1]

                # 3-point forward/backward difference for velocity estimation
                v0 = (-3*resampled[0][1] + 4*resampled[1][1] - resampled[2][1]) / (2*resample_dt)
                vT = (3*resampled[-1][1] - 4*resampled[-2][1] + resampled[-3][1]) / (2*resample_dt)

                # Check if C1 enforcement is needed
                c0_thresh = cfg.c0_snap_threshold_rot if is_rotation else cfg.c0_snap_threshold_pos
                c1_thresh = cfg.velocity_match_threshold_rot if is_rotation else cfg.velocity_match_threshold_pos

                c0_diff = abs(p0 - pT)
                c1_diff = abs(v0 - vT)

                if c0_diff < c0_thresh and c1_diff < c1_thresh:
                    # Already good enough - just snap C0
                    if c0_diff > 1e-8:
                        channels[channel] = [
                            (t, v) if i < len(keyframes) - 1 else (t, keyframes[0][1])
                            for i, (t, v) in enumerate(keyframes)
                        ]
                    continue

                # Step 3: Compute ADAPTIVE blend window size
                # base_w = min(duration * ratio, max_window)
                # adaptive_w = base_w * (1 + min(c1_diff / c1_thresh, 3.0))
                # → larger velocity mismatches get larger blend windows
                base_w = min(duration * cfg.blend_window_ratio, cfg.max_blend_window)
                adaptive_scale = 1.0 + min(c1_diff / max(c1_thresh, 1e-6), 3.0)
                w = base_w * adaptive_scale

                # Ensure blend window has at least 10 resampled points
                min_samples = 10
                w = max(w, min_samples * resample_dt)

                # For very short animations, expand to at least 15%
                if w < duration * 0.15 and duration < 1.0:
                    w = duration * 0.15

                # Ensure blend window doesn't exceed 60% of animation
                # (we only blend at end, so we can use more than the v2 40% per-side limit)
                if w > duration * 0.6:
                    w = duration * 0.6

                # ============================================================
                # END BLEND ONLY (v3): blend from original end toward (p_start, v_start)
                # ============================================================
                end_blend_start_time = max(0, duration - w)

                # Find resampled points in end blend window
                end_blend_start_idx = 0
                for i, (t, v) in enumerate(resampled):
                    if t >= end_blend_start_time:
                        end_blend_start_idx = i
                        break

                if end_blend_start_idx >= 1 and end_blend_start_idx < len(resampled) - 1:
                    # Get blend boundary values at start of end-blend window
                    p_end_blend_start = resampled[end_blend_start_idx][1]
                    t_end_blend_start = resampled[end_blend_start_idx][0]

                    # Velocity at end-blend start via central difference
                    v_end_blend_start = (
                        (resampled[end_blend_start_idx + 1][1] -
                         resampled[end_blend_start_idx - 1][1]) /
                        (resampled[end_blend_start_idx + 1][0] -
                         resampled[end_blend_start_idx - 1][0])
                    )

                    # Target: position at end = p0, velocity at end = v0
                    p_end_blend_end = p0
                    v_end_blend_end = v0

                    w_end_actual = duration - t_end_blend_start
                    if w_end_actual > 1e-12:
                        # Apply Hermite blend using LINEAR parameter s
                        # Do NOT apply smootherstep - Hermite already provides C1
                        for i in range(end_blend_start_idx, len(resampled)):
                            t, v = resampled[i]
                            s = (t - t_end_blend_start) / w_end_actual  # linear 0→1
                            s = max(0.0, min(1.0, s))

                            # Hermite basis functions with LINEAR parameter s
                            s2 = s * s
                            s3 = s2 * s

                            h00 = 2 * s3 - 3 * s2 + 1
                            h10 = s3 - 2 * s2 + s
                            h01 = -2 * s3 + 3 * s2
                            h11 = s3 - s2

                            new_val = (h00 * p_end_blend_start +
                                       h10 * w_end_actual * v_end_blend_start +
                                       h01 * p_end_blend_end +
                                       h11 * w_end_actual * v_end_blend_end)

                            resampled[i] = (t, new_val)

                # NO START BLEND in v3 - preserve the start exactly as-is
                # This is the key v3 improvement: the beginning of the animation
                # is what the player sees first, so we don't distort it.

                # Step 4: Replace original keyframes with resampled + blended data
                # Keep original keyframes outside the end blend window,
                # use resampled data inside the end blend window.
                new_keyframes = []

                # Add original keyframes that are outside the end blend window
                for t, v in keyframes:
                    if t <= end_blend_start_time + 1e-8:
                        new_keyframes.append((t, v))

                # In the end blend window, add resampled points at reasonable density
                n_blend_target = 8
                end_blend_interval = w_end_actual / max(n_blend_target - 1, 1) if w_end_actual > 0 else float('inf')
                end_blend_interval = max(end_blend_interval, resample_dt * 3)

                last_added_time = end_blend_start_time - end_blend_interval
                for i in range(end_blend_start_idx, len(resampled)):
                    t, v = resampled[i]
                    if (t - last_added_time >= end_blend_interval - 1e-8 or
                        i == end_blend_start_idx or
                        t >= duration - 1e-8):
                        new_keyframes.append((t, v))
                        last_added_time = t

                # Sort all keyframes by time
                new_keyframes.sort(key=lambda x: x[0])

                # Remove near-duplicate times (within 1ms)
                deduped = []
                for t, v in new_keyframes:
                    if deduped and abs(t - deduped[-1][0]) < 0.001:
                        deduped[-1] = (t, v)
                    else:
                        deduped.append((t, v))
                new_keyframes = deduped

                # Ensure last keyframe is exactly at duration with value = p0 (C0 snap)
                if new_keyframes:
                    new_keyframes[-1] = (duration, p0)
                else:
                    new_keyframes.append((0.0, p0))
                    new_keyframes.append((duration, p0))

                # v3: Do NOT modify the first keyframe - preserve start exactly
                # The start of the animation is sacred; only the end gets blended.

                channels[channel] = new_keyframes

        return bone_channels


# ============================================================================
# Douglas-Peucker Simplifier
# ============================================================================

class DouglasPeuckerSimplifier:
    """Channel-type-aware Douglas-Peucker simplification."""

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()

    def simplify(self, points: List[Tuple[float, float]],
                 epsilon: float) -> List[Tuple[float, float]]:
        """Apply Douglas-Peucker simplification."""
        if len(points) <= 2:
            return points

        stack = [(0, len(points) - 1)]
        keep = set()
        keep.add(0)
        keep.add(len(points) - 1)

        while stack:
            start_idx, end_idx = stack.pop()
            if end_idx - start_idx <= 1:
                continue

            start = points[start_idx]
            end = points[end_idx]
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            line_len_sq = dx * dx + dy * dy

            max_dist = 0.0
            max_idx = start_idx

            for i in range(start_idx + 1, end_idx):
                if line_len_sq < 1e-12:
                    dist = math.hypot(points[i][0] - start[0],
                                      points[i][1] - start[1])
                else:
                    t = ((points[i][0] - start[0]) * dx +
                         (points[i][1] - start[1]) * dy) / line_len_sq
                    t = max(0.0, min(1.0, t))
                    proj_x = start[0] + t * dx
                    proj_y = start[1] + t * dy
                    dist = math.hypot(points[i][0] - proj_x,
                                      points[i][1] - proj_y)

                if dist > max_dist:
                    max_dist = dist
                    max_idx = i

            if max_dist > epsilon:
                keep.add(max_idx)
                stack.append((start_idx, max_idx))
                stack.append((max_idx, end_idx))

        return [points[i] for i in sorted(keep)]

    def get_epsilon(self, channel: str) -> float:
        """Get channel-appropriate DP epsilon."""
        cfg = self.config
        if channel in ('rx', 'ry', 'rz', 'x', 'y', 'z'):
            return cfg.dp_epsilon_rotation
        else:
            return cfg.dp_epsilon_position


# ============================================================================
# Animation Name Normalizer
# ============================================================================

class AnimationNameNormalizer:
    """Normalizes animation names to follow GeckoLib convention.

    GeckoLib convention: animation.<namespace>.<entity>.<state>
    """

    REDUNDANT_PREFIXES = [
        'animation.',
        'anim.',
    ]

    STATE_ALIASES = {
        'idle_pose': 'idle',
        'idlepose': 'idle',
        'stand': 'idle',
        'standing': 'idle',
        'walk_cycle': 'walk',
        'walkcycle': 'walk',
        'run_cycle': 'run',
        'runcycle': 'run',
        'attack_cycle': 'attack',
        'attackcycle': 'attack',
    }

    @staticmethod
    def normalize(name: str, model_name: str = "",
                  namespace: str = "") -> str:
        """Normalize an animation name to GeckoLib convention."""
        if not name:
            return name

        state = name.strip()

        for prefix in AnimationNameNormalizer.REDUNDANT_PREFIXES:
            if state.lower().startswith(prefix):
                state = state[len(prefix):]
                break

        parts = state.split('.')
        if len(parts) >= 2:
            state = parts[-1]

        state_lower = state.lower()
        if state_lower in AnimationNameNormalizer.STATE_ALIASES:
            state = AnimationNameNormalizer.STATE_ALIASES[state_lower]

        state = re.sub(r'[\s\-]+', '_', state)
        state = re.sub(r'[^a-zA-Z0-9_]', '', state)

        entity = model_name if model_name else "entity"
        entity = re.sub(r'[^a-zA-Z0-9_]', '_', entity)
        entity = entity.lower()

        if namespace:
            ns = namespace.lower()
        else:
            ns = entity

        return f"animation.{ns}.{entity}.{state}"


# ============================================================================
# BBModel Animation Extractor (v3: enhanced dedup/empty handling)
# ============================================================================

class BBModelAnimationExtractor:
    """Extracts animations from .bbmodel files and converts to internal format.

    v3 Improvements:
    - Content hash dedup using SHA-256 (not just string signatures)
    - Smart bone-channel merging for case-insensitive duplicates
    - NEVER lose real animation data - if in doubt, keep both
    - Better empty detection: check ALL channels for near-zero values
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()

    def extract(self, bbmodel_path: str) -> Dict[str, Any]:
        """Extract all animations from a .bbmodel file.

        Returns:
            {
                'model_name': str,
                'animations': {anim_name: {...}},
                'skipped_empty': List[str],
                'deduplicated': List[str],
            }
        """
        with open(bbmodel_path, 'r', encoding='utf-8') as f:
            bb = json.load(f)

        model_name = bb.get('model_identifier', bb.get('name', 'unknown'))
        raw_animations = {}

        for anim in bb.get('animations', []):
            anim_name = anim.get('name', f'animation.{model_name}.unknown')
            bone_channels = {}

            interpolation_counts = defaultdict(int)

            for bone_name, animator in anim.get('animators', {}).items():
                if animator.get('type') != 'bone':
                    continue

                channels = defaultdict(list)

                for kf in animator.get('keyframes', []):
                    channel = kf.get('channel', 'rotation')
                    time_val = kf.get('time', 0.0)
                    interp = kf.get('interpolation', 'linear')
                    interpolation_counts[interp] += 1

                    data_points = kf.get('data_points', [])
                    if not data_points:
                        continue

                    dp = data_points[0]

                    if channel == 'rotation':
                        x_val = self._parse_float(dp.get('x', 0))
                        y_val = self._parse_float(dp.get('y', 0))
                        z_val = self._parse_float(dp.get('z', 0))
                        channels['rx'].append((time_val, x_val))
                        channels['ry'].append((time_val, y_val))
                        channels['rz'].append((time_val, z_val))
                    elif channel == 'position':
                        x_val = self._parse_float(dp.get('x', 0))
                        y_val = self._parse_float(dp.get('y', 0))
                        z_val = self._parse_float(dp.get('z', 0))
                        channels['ox'].append((time_val, x_val))
                        channels['oy'].append((time_val, y_val))
                        channels['oz'].append((time_val, z_val))
                    elif channel == 'scale':
                        x_val = self._parse_float(dp.get('x', 1))
                        y_val = self._parse_float(dp.get('y', 1))
                        z_val = self._parse_float(dp.get('z', 1))
                        if abs(x_val - 1.0) > 0.001 or abs(y_val - 1.0) > 0.001 or abs(z_val - 1.0) > 0.001:
                            channels['sx'].append((time_val, x_val))
                            channels['sy'].append((time_val, y_val))
                            channels['sz'].append((time_val, z_val))

                # Sort each channel by time and merge duplicates
                merged_channels = {}
                for ch_name, ch_data in channels.items():
                    if not ch_data:
                        continue
                    ch_data.sort(key=lambda x: x[0])
                    merged = {}
                    for t, v in ch_data:
                        merged[t] = v
                    merged_channels[ch_name] = [(t, merged[t]) for t in sorted(merged.keys())]

                if merged_channels:
                    bone_channels[bone_name] = merged_channels

            # Determine dominant interpolation
            dominant_interp = "linear"
            if interpolation_counts:
                dominant_interp = max(interpolation_counts, key=interpolation_counts.get)

            # Check if animation is empty (v3: check ALL bone channels)
            is_empty = self._is_empty_animation(bone_channels)

            raw_animations[anim_name] = {
                'loop': anim.get('loop', 'hold_on_last_frame'),
                'length': anim.get('length', 0.0),
                'snapping': anim.get('snapping', 24),
                'bone_channels': bone_channels,
                'interpolation': dominant_interp,
                'is_empty': is_empty,
            }

        # Post-processing: deduplication and empty filtering
        animations = {}
        skipped_empty = []
        deduplicated = []

        if self.config.deduplicate_case_insensitive:
            # Case-insensitive deduplication with smart bone-channel merging
            seen_lower = {}  # lowercase_name → canonical_name
            for anim_name, anim_data in raw_animations.items():
                lower_name = anim_name.lower()
                if lower_name in seen_lower:
                    canonical = seen_lower[lower_name]
                    if self.config.smart_bone_merge:
                        # Smart merge: combine bone channels from both
                        # Keep channels from whichever animation has them,
                        # or the one with more keyframes for shared bones
                        merged_channels = dict(animations[canonical]['bone_channels'])
                        for bone, channels in anim_data['bone_channels'].items():
                            if bone not in merged_channels:
                                merged_channels[bone] = channels
                            else:
                                # Bone exists in both - keep the one with more keyframes
                                existing_kf = sum(len(kfs) for kfs in merged_channels[bone].values())
                                new_kf = sum(len(kfs) for kfs in channels.values())
                                if new_kf > existing_kf:
                                    merged_channels[bone] = channels
                        animations[canonical]['bone_channels'] = merged_channels
                        # Update is_empty flag
                        animations[canonical]['is_empty'] = self._is_empty_animation(merged_channels)
                    else:
                        # Simple merge: keep the one with more keyframes
                        existing_kf_count = sum(
                            len(kfs) for chs in animations[canonical]['bone_channels'].values()
                            for kfs in chs.values()
                        )
                        new_kf_count = sum(
                            len(kfs) for chs in anim_data['bone_channels'].values()
                            for kfs in chs.values()
                        )
                        if new_kf_count > existing_kf_count:
                            animations[canonical] = anim_data
                    deduplicated.append(anim_name)
                else:
                    seen_lower[lower_name] = anim_name
                    animations[anim_name] = anim_data
        else:
            animations = raw_animations

        # Content-hash dedup (v3: SHA-256 based)
        if self.config.content_hash_dedup and self.config.merge_duplicate_animations:
            data_hashes = {}
            final_animations = {}
            for anim_name, anim_data in animations.items():
                content_hash = self._compute_content_hash(anim_data)
                if content_hash in data_hashes:
                    # Duplicate data found
                    existing_name = data_hashes[content_hash]
                    existing_kf = sum(
                        len(kfs) for chs in animations[existing_name]['bone_channels'].values()
                        for kfs in chs.values()
                    )
                    new_kf = sum(
                        len(kfs) for chs in anim_data['bone_channels'].values()
                        for kfs in chs.values()
                    )
                    # NEVER lose real data - keep both if they have different bone channels
                    existing_bones = set(animations[existing_name]['bone_channels'].keys())
                    new_bones = set(anim_data['bone_channels'].keys())
                    if new_bones - existing_bones:
                        # Different bones - keep both (not truly duplicate)
                        data_hashes[content_hash] = anim_name
                        final_animations[anim_name] = anim_data
                    else:
                        # Same bones, same hash - keep the one with more keyframes
                        if new_kf > existing_kf:
                            del final_animations[existing_name]
                            data_hashes[content_hash] = anim_name
                            final_animations[anim_name] = anim_data
                        else:
                            deduplicated.append(anim_name)
                else:
                    data_hashes[content_hash] = anim_name
                    final_animations[anim_name] = anim_data
            animations = final_animations
        elif self.config.merge_duplicate_animations:
            # Legacy string-signature dedup (fallback)
            data_signatures = {}
            final_animations = {}
            for anim_name, anim_data in animations.items():
                sig = self._compute_animation_signature(anim_data)
                if sig in data_signatures:
                    deduplicated.append(anim_name)
                else:
                    data_signatures[sig] = anim_name
                    final_animations[anim_name] = anim_data
            animations = final_animations

        # Filter empty animations
        if self.config.skip_empty_animations:
            non_empty = {}
            for anim_name, anim_data in animations.items():
                if anim_data['is_empty']:
                    skipped_empty.append(anim_name)
                else:
                    non_empty[anim_name] = anim_data
            animations = non_empty

        return {
            'model_name': model_name,
            'animations': animations,
            'skipped_empty': skipped_empty,
            'deduplicated': deduplicated,
        }

    @staticmethod
    def _is_empty_animation(bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]]) -> bool:
        """Check if an animation has no meaningful keyframe data.

        v3: Check ALL bone channels for near-zero values.
        """
        if not bone_channels:
            return True

        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if not keyframes:
                    continue
                for t, v in keyframes:
                    if channel.startswith('r') or channel in ('x', 'y', 'z'):
                        if abs(v) > 0.01:
                            return False
                    elif channel.startswith('o'):
                        if abs(v) > 0.001:
                            return False
                    elif channel.startswith('s'):
                        if abs(v - 1.0) > 0.001:
                            return False

        return True

    @staticmethod
    def _compute_content_hash(anim_data: Dict[str, Any]) -> str:
        """Compute SHA-256 content hash for an animation's data.

        v3: Uses SHA-256 instead of string concatenation for robust dedup.
        """
        parts = []
        bone_channels = anim_data.get('bone_channels', {})
        for bone_name in sorted(bone_channels.keys()):
            channels = bone_channels[bone_name]
            for channel in sorted(channels.keys()):
                keyframes = channels[channel]
                kf_str = ",".join(f"{t:.4f}:{v:.6f}" for t, v in keyframes)
                parts.append(f"{bone_name}.{channel}={kf_str}")
        content = "|".join(parts)
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    @staticmethod
    def _compute_animation_signature(anim_data: Dict[str, Any]) -> str:
        """Compute a hashable signature for an animation's data (legacy)."""
        parts = []
        bone_channels = anim_data.get('bone_channels', {})
        for bone_name in sorted(bone_channels.keys()):
            channels = bone_channels[bone_name]
            for channel in sorted(channels.keys()):
                keyframes = channels[channel]
                kf_str = ",".join(f"{t:.4f}:{v:.6f}" for t, v in keyframes)
                parts.append(f"{bone_name}.{channel}={kf_str}")
        return "|".join(parts)

    @staticmethod
    def _parse_float(value) -> float:
        """Safely parse a float value."""
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0


# ============================================================================
# GeckoLib JSON Builder
# ============================================================================

class GeckoLibJSONBuilder:
    """Builds GeckoLib 1.20.1 .animation.json format from processed channel data."""

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()
        self.dp_simplifier = DouglasPeuckerSimplifier(self.config)

    def build(self, anim_name: str, loop_mode: str,
              bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
              duration: float) -> dict:
        """Build a GeckoLib animation entry."""
        cfg = self.config
        bones_dict = {}

        for bone_name, channels in bone_channels.items():
            bone_entry = self._build_bone_entry(bone_name, channels, cfg)
            if bone_entry:
                bones_dict[bone_name] = bone_entry

        return {
            "loop": loop_mode,
            "animation_length": round(duration, cfg.keyframe_precision),
            "bones": bones_dict
        }

    def _build_bone_entry(self, bone_name: str,
                          channels: Dict[str, List[Tuple[float, float]]],
                          config: ConverterConfig) -> Optional[Dict]:
        """Build a GeckoLib bone entry."""
        rot_channels = {}
        pos_channels = {}

        for channel, keyframes in channels.items():
            if not keyframes:
                continue

            # Apply DP simplification
            epsilon = self.dp_simplifier.get_epsilon(channel)
            simplified = self.dp_simplifier.simplify(keyframes, epsilon)

            # Check if all values are near-zero
            max_abs = max(abs(v) for t, v in simplified) if simplified else 0.0
            if max_abs < config.filter_zero_threshold:
                continue

            axis = channel[-1]

            kf_dict = {
                f"{t:.{config.keyframe_precision}f}": round(v, config.value_precision)
                for t, v in simplified
            }

            if channel in ('rx', 'ry', 'rz'):
                rot_channels[axis] = kf_dict
            elif channel in ('ox', 'oy', 'oz'):
                pos_channels[axis] = kf_dict
            elif channel in ('sx', 'sy', 'sz'):
                rot_channels[axis] = kf_dict

        bone_entry = {}
        if rot_channels:
            bone_entry["rotation"] = rot_channels
        if pos_channels:
            bone_entry["position"] = pos_channels

        return bone_entry if bone_entry else None


# ============================================================================
# Quality Reporter (v3: enhanced with per-animation score)
# ============================================================================

class QualityReporter:
    """Generates quality reports for converted animations (v3 enhanced).

    v3 improvements:
    - Per-animation quality score (0-100) with C0/C1/duration breakdown
    - P90 C1 metric (more representative than max)
    - Blend window info tracking
    - Duration adjustment tracking
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()

    def report(
        self,
        anim_name: str,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float
    ) -> AnimationQualityReport:
        """Generate a quality report for an animation."""
        report = AnimationQualityReport(
            animation_name=anim_name,
            duration=duration,
            num_bones=len(bone_channels),
            total_keyframes=sum(
                len(kfs) for chs in bone_channels.values()
                for kfs in chs.values()
            ),
        )

        c0_errors_rot = []
        c0_errors_pos = []
        c1_errors_rot = []
        c1_errors_pos = []

        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if len(keyframes) < 2:
                    continue

                is_rotation = channel in ('rx', 'ry', 'rz')

                p0 = keyframes[0][1]
                pT = keyframes[-1][1]
                c0_err = abs(pT - p0)

                if is_rotation:
                    c0_errors_rot.append(c0_err)
                else:
                    c0_errors_pos.append(c0_err)

                # Velocity estimation using resampling for accuracy
                if len(keyframes) >= 2 and duration > 0:
                    n_s = min(120, max(20, int(duration * 30)))
                    s_dt = duration / n_s
                    s_times = [i * s_dt for i in range(n_s + 1)]
                    s_data = CatmullRomEvaluator.resample_channel(
                        keyframes, s_times, "catmullrom"
                    )
                    if len(s_data) >= 5:
                        v0 = (-3*s_data[0][1] + 4*s_data[1][1] - s_data[2][1]) / (2*s_dt)
                        vT = (3*s_data[-1][1] - 4*s_data[-2][1] + s_data[-3][1]) / (2*s_dt)
                        c1_err = abs(vT - v0)
                        if is_rotation:
                            c1_errors_rot.append(c1_err)
                        else:
                            c1_errors_pos.append(c1_err)

        # Compute statistics
        if c0_errors_rot:
            report.c0_max_error_rot = max(c0_errors_rot)
            report.c0_avg_error_rot = sum(c0_errors_rot) / len(c0_errors_rot)
        if c0_errors_pos:
            report.c0_max_error_pos = max(c0_errors_pos)
            report.c0_avg_error_pos = sum(c0_errors_pos) / len(c0_errors_pos)
        if c1_errors_rot:
            sorted_c1 = sorted(c1_errors_rot)
            report.c1_max_error_rot = sorted_c1[-1]
            # P90 for C1 (more representative than max)
            p90_idx = int(len(sorted_c1) * 0.9)
            report.c1_avg_error_rot = sorted_c1[min(p90_idx, len(sorted_c1)-1)]
        if c1_errors_pos:
            sorted_c1 = sorted(c1_errors_pos)
            report.c1_max_error_pos = sorted_c1[-1]
            p90_idx = int(len(sorted_c1) * 0.9)
            report.c1_avg_error_pos = sorted_c1[min(p90_idx, len(sorted_c1)-1)]

        # Quality assessment
        report.c0_perfect = report.c0_max_error_rot < self.config.c0_snap_threshold_rot and \
                            report.c0_max_error_pos < self.config.c0_snap_threshold_pos
        report.c1_perfect = report.c1_avg_error_rot < self.config.c1_quality_threshold_rot and \
                            report.c1_avg_error_pos < self.config.c1_quality_threshold_pos

        # Compute quality score (0-100)
        score = 100.0
        # C0 penalties
        if not report.c0_perfect:
            score -= min(30, report.c0_max_error_rot * 5 + report.c0_max_error_pos * 30)
        # C1 penalties using P90
        if not report.c1_perfect:
            c1_rot_penalty = min(25, report.c1_avg_error_rot * 1.5)
            c1_pos_penalty = min(15, report.c1_avg_error_pos * 5)
            score -= c1_rot_penalty + c1_pos_penalty

        report.quality_score = max(0.0, min(100.0, score))

        # Generate warnings/errors
        if report.c0_max_error_rot > self.config.quality_error_threshold:
            report.errors.append(
                f"C0 rotation error too large: {report.c0_max_error_rot:.3f}° "
                f"(threshold: {self.config.quality_error_threshold}°)"
            )
        elif report.c0_max_error_rot > self.config.quality_warning_threshold:
            report.warnings.append(
                f"C0 rotation error: {report.c0_max_error_rot:.3f}°"
            )

        if not report.c1_perfect:
            report.warnings.append(
                f"C1 velocity mismatch: rot={report.c1_max_error_rot:.2f}°/s (P90={report.c1_avg_error_rot:.2f}°/s), "
                f"pos={report.c1_max_error_pos:.3f}px/s"
            )

        return report


# ============================================================================
# Main Converter
# ============================================================================

class BBModelAnimationConverter:
    """Universal animation converter for .bbmodel files (v3).

    Pipeline:
      1. Extract animations from .bbmodel (with enhanced empty/duplicate handling)
      2. Normalize animation names to GeckoLib convention
      3. For loop animations: detect optimal loop duration
      4. Enforce C1 continuity at loop boundaries (end-only adaptive)
      5. Simplify keyframes
      6. Build GeckoLib .animation.json
      7. Generate quality report with per-animation score
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()
        self.extractor = BBModelAnimationExtractor(self.config)
        self.loop_detector = AutoLoopDetector(self.config)
        self.c1_enforcer = C1ContinuityEnforcer(self.config)
        self.json_builder = GeckoLibJSONBuilder(self.config)
        self.quality_reporter = QualityReporter(self.config)
        self.name_normalizer = AnimationNameNormalizer()

    def convert_file(self, bbmodel_path: str,
                     output_path: Optional[str] = None) -> Dict[str, Any]:
        """Convert all animations in a .bbmodel file.

        Args:
            bbmodel_path: Path to .bbmodel file
            output_path: Optional output path for .animation.json

        Returns:
            {
                'model_name': str,
                'animations': dict,
                'quality_reports': dict,
                'stats': dict,
            }
        """
        # Step 1: Extract (with enhanced empty/duplicate filtering)
        extracted = self.extractor.extract(bbmodel_path)
        model_name = extracted['model_name']

        all_animations = {}
        quality_reports = {}
        stats = {
            'total_animations': 0,
            'total_keyframes': 0,
            'c0_perfect_count': 0,
            'c1_perfect_count': 0,
            'duration_adjustments': [],
            'skipped_empty': extracted.get('skipped_empty', []),
            'deduplicated': extracted.get('deduplicated', []),
            'name_normalizations': [],
        }

        for anim_name, anim_data in extracted['animations'].items():
            bone_channels = anim_data['bone_channels']
            current_duration = anim_data['length']
            loop_mode = anim_data['loop']
            interpolation = anim_data['interpolation']

            # Step 2: Normalize animation name
            if self.config.normalize_animation_names:
                normalized_name = AnimationNameNormalizer.normalize(
                    anim_name, model_name, self.config.animation_namespace
                )
                if normalized_name != anim_name:
                    stats['name_normalizations'].append({
                        'original': anim_name,
                        'normalized': normalized_name,
                    })
                    anim_name = normalized_name

            stats['total_animations'] += 1
            for chs in bone_channels.values():
                for kfs in chs.values():
                    stats['total_keyframes'] += len(kfs)

            # Step 3: Duration optimization for loop animations only
            if loop_mode == "loop" and self.config.enable_duration_optimization:
                optimal_duration, loop_diag = self.loop_detector.detect_optimal_duration(
                    bone_channels, current_duration, interpolation
                )
                current_c0 = loop_diag.get('current_c0_error', float('inf'))
                best_c0 = loop_diag.get('best_c0_error', float('inf'))
                method = loop_diag.get('method', 'none')

                should_change = False
                if method in ('search_optimal', 'search_early_exit_good_enough') and current_c0 > 0.3:
                    improvement = (current_c0 - best_c0) / max(current_c0, 0.001)
                    if (improvement > self.config.duration_change_threshold and
                        current_c0 - best_c0 > self.config.min_duration_improvement):
                        should_change = True

                if should_change and abs(optimal_duration - current_duration) > 0.01:
                    stats['duration_adjustments'].append({
                        'animation': anim_name,
                        'from': current_duration,
                        'to': optimal_duration,
                        'method': method,
                    })
                    bone_channels = self._trim_to_duration(bone_channels, optimal_duration)
                    current_duration = optimal_duration
                else:
                    current_duration = anim_data['length']
            else:
                current_duration = anim_data['length']

            # Step 4: C1 continuity enforcement (end-only adaptive) for loop animations only
            if loop_mode == "loop":
                bone_channels = self.c1_enforcer.enforce(bone_channels, current_duration, interpolation)

            # Step 5: Build GeckoLib JSON
            anim_json = self.json_builder.build(
                anim_name, loop_mode, bone_channels, current_duration
            )
            all_animations[anim_name] = anim_json

            # Step 6: Quality report
            qreport = self.quality_reporter.report(anim_name, bone_channels, current_duration)
            qreport.duration_adjusted = len(stats['duration_adjustments']) > 0
            quality_reports[anim_name] = qreport

            if qreport.c0_perfect:
                stats['c0_perfect_count'] += 1
            if qreport.c1_perfect:
                stats['c1_perfect_count'] += 1

        # Assemble output
        result = {
            "format_version": "1.8.0",
            "animations": all_animations,
        }

        if output_path:
            if all_animations:
                os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)

        return {
            'model_name': model_name,
            'animations': result,
            'quality_reports': quality_reports,
            'stats': stats,
        }

    def _trim_to_duration(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float
    ) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
        """Trim all keyframes to the specified duration."""
        result = {}
        for bone_name, channels in bone_channels.items():
            result[bone_name] = {}
            for channel, keyframes in channels.items():
                trimmed = [(t, v) for t, v in keyframes if t <= duration + 0.0001]
                if trimmed and abs(trimmed[-1][0] - duration) > 0.0001:
                    if len(keyframes) > 1:
                        for i in range(len(keyframes) - 1):
                            if keyframes[i][0] <= duration <= keyframes[i + 1][0]:
                                dt = keyframes[i + 1][0] - keyframes[i][0]
                                if dt > 1e-12:
                                    alpha = (duration - keyframes[i][0]) / dt
                                    interp_val = keyframes[i][1] + alpha * (keyframes[i + 1][1] - keyframes[i][1])
                                    trimmed.append((duration, interp_val))
                                break
                trimmed.sort(key=lambda x: x[0])
                result[bone_name][channel] = trimmed
        return result


# ============================================================================
# Batch Processing (v3: with ZIP packaging)
# ============================================================================

def batch_convert(input_dir: str, output_dir: str,
                  config: ConverterConfig = None,
                  zip_path: Optional[str] = None) -> bool:
    """Batch convert all .bbmodel files in a directory tree (v3).

    For each .bbmodel file:
      - Extract geo.json + texture (using bbmodel_to_geo.py)
      - Extract and convert animations (using this v3 converter)
      - Save to output directory maintaining directory structure
      - Optionally package into a ZIP file

    Args:
        input_dir: Directory containing .bbmodel files
        output_dir: Output directory for converted files
        config: Converter configuration
        zip_path: Optional path for ZIP packaging

    Returns:
        True if no errors, False otherwise.
    """
    print("=" * 70)
    print("  Universal BBModel Animation Converter (v3)")
    print("  .bbmodel → .animation.json with End-Only Adaptive C1 Continuity")
    print("  GeckoLib Format for MC 1.20.1 Forge Mod Development")
    print("  [v3] End-Only Adaptive C1 Blending (preserves animation start)")
    print("  [v3] numpy FFT autocorrelation (with pure-python fallback)")
    print("  [v3] Content-hash dedup + smart bone-channel merging")
    print("  [v3] Per-animation quality score (0-100)")
    print("=" * 70)
    print()

    cfg = config or ConverterConfig()
    converter = BBModelAnimationConverter(cfg)

    # Import geo converter
    try:
        from bbmodel_to_geo import BBModelToGeo
        geo_converter = BBModelToGeo()
    except ImportError:
        # Try relative import
        import importlib.util
        geo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bbmodel_to_geo.py')
        if os.path.exists(geo_path):
            spec = importlib.util.spec_from_file_location("bbmodel_to_geo", geo_path)
            geo_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(geo_mod)
            geo_converter = geo_mod.BBModelToGeo()
        else:
            print("  WARNING: bbmodel_to_geo.py not found, geo conversion will be skipped")
            geo_converter = None

    # Find all .bbmodel files
    bbmodel_files = []
    for root, dirs, files in os.walk(input_dir):
        for fname in sorted(files):
            if fname.endswith('.bbmodel'):
                rel_path = os.path.relpath(
                    os.path.join(root, fname), input_dir
                )
                bbmodel_files.append(rel_path)

    print(f"Found {len(bbmodel_files)} .bbmodel files")
    print(f"Configuration:")
    print(f"  C1 enforcement: {'ON' if cfg.enable_c1_enforcement else 'OFF'}")
    print(f"  C1 mode: End-Only Adaptive (v3)")
    print(f"  Duration optimization: {'ON' if cfg.enable_duration_optimization else 'OFF'}")
    print(f"  Autocorrelation: {'ON (FFT)' if cfg.autocorrelation_enabled and _NUMPY_AVAILABLE else 'ON (pure)' if cfg.autocorrelation_enabled else 'OFF'}")
    print(f"  Blend window: {cfg.blend_window_ratio*100:.0f}% base (adaptive up to 4x)")
    print(f"  Early exit: C0 < {cfg.early_exit_c0_rot}°, C1 < {cfg.early_exit_c1_rot}°/s")
    print(f"  DP epsilon: rot={cfg.dp_epsilon_rotation}°, pos={cfg.dp_epsilon_position}px")
    print(f"  Skip empty: {'ON' if cfg.skip_empty_animations else 'OFF'}")
    print(f"  Content-hash dedup: {'ON' if cfg.content_hash_dedup else 'OFF'}")
    print(f"  Smart bone merge: {'ON' if cfg.smart_bone_merge else 'OFF'}")
    print(f"  Name normalization: {'ON' if cfg.normalize_animation_names else 'OFF'}")
    print()

    total_anims = 0
    total_keyframes = 0
    total_c0_perfect = 0
    total_c1_perfect = 0
    total_no_anim = 0
    total_skipped_empty = 0
    total_deduplicated = 0
    all_quality_scores = []
    all_warnings = []
    all_errors = []
    all_output_files = []  # Track files for ZIP packaging

    start_time = time.time()

    for i, rel_path in enumerate(bbmodel_files, 1):
        bbmodel_path = os.path.join(input_dir, rel_path)
        category = os.path.dirname(rel_path)
        name = os.path.basename(rel_path).replace('.bbmodel', '')
        out_dir = os.path.join(output_dir, category) if category else output_dir

        print(f"  [{i:3d}/{len(bbmodel_files)}] {category}/{name}...",
              end=" ", flush=True)

        # Convert geo + texture
        geo_ok = False
        if geo_converter:
            geo_result = geo_converter.convert_bbmodel(bbmodel_path, out_dir)
            geo_ok = geo_result.get('success', False)
            if geo_ok:
                # Track output files
                if geo_result.get('geo_path'):
                    all_output_files.append(geo_result['geo_path'])
                if geo_result.get('texture_path'):
                    all_output_files.append(geo_result['texture_path'])

        # Convert animations
        anim_output_path = os.path.join(out_dir, f"{name}.animation.json")
        if os.path.exists(anim_output_path):
            os.remove(anim_output_path)

        try:
            result = converter.convert_file(bbmodel_path, anim_output_path)
            stats = result['stats']

            # Quality summary
            geo_mark = "+" if geo_ok else "-"
            anim_count = stats['total_animations']
            kf_count = stats['total_keyframes']
            c0_ok = stats['c0_perfect_count']
            c1_ok = stats['c1_perfect_count']
            dur_adj = len(stats['duration_adjustments'])
            skipped = len(stats.get('skipped_empty', []))
            deduped = len(stats.get('deduplicated', []))

            total_skipped_empty += skipped
            total_deduplicated += deduped

            if anim_count == 0:
                if skipped > 0:
                    print(f"{geo_mark} no_anim ({skipped} empty skipped)")
                else:
                    print(f"{geo_mark} no_anim (static model)")
                total_no_anim += 1
            else:
                # Collect quality scores
                for anim_name, qr in result['quality_reports'].items():
                    all_quality_scores.append(qr.quality_score)

                # Compute average quality score for this model
                avg_score = sum(qr.quality_score for qr in result['quality_reports'].values()) / max(anim_count, 1)

                extras = ""
                if dur_adj:
                    extras += f" dur_adj={dur_adj}"
                if skipped:
                    extras += f" skip={skipped}"
                if deduped:
                    extras += f" dedup={deduped}"
                print(f"{geo_mark} anims={anim_count} kf={kf_count} "
                      f"C0={c0_ok}/{anim_count} C1={c1_ok}/{anim_count} "
                      f"score={avg_score:.0f}{extras}")

                # Track animation output file
                if os.path.exists(anim_output_path):
                    all_output_files.append(anim_output_path)

            total_anims += anim_count
            total_keyframes += kf_count
            total_c0_perfect += c0_ok
            total_c1_perfect += c1_ok

            # Collect warnings/errors
            for anim_name, qr in result['quality_reports'].items():
                if qr.errors:
                    all_errors.append(f"{category}/{name}/{anim_name}: " +
                                      "; ".join(qr.errors))
                if qr.warnings:
                    all_warnings.append(f"{category}/{name}/{anim_name}: " +
                                        "; ".join(qr.warnings))

        except Exception as e:
            print(f"ANIM FAILED: {e}")
            all_errors.append(f"{category}/{name}: animation conversion failed: {e}")

    elapsed = time.time() - start_time

    # Global batch summary with statistics
    print()
    print("=" * 70)
    print("  CONVERSION SUMMARY (v3)")
    print("=" * 70)
    print(f"  Total models:            {len(bbmodel_files)}")
    print(f"  Models with animations:  {len(bbmodel_files) - total_no_anim}")
    print(f"  Static models:           {total_no_anim}")
    print(f"  Total animations:        {total_anims}")
    print(f"  Total keyframes:         {total_keyframes:,}")
    print(f"  C0 perfect:              {total_c0_perfect}/{total_anims} ({100*total_c0_perfect/max(total_anims,1):.1f}%)")
    print(f"  C1 good (P90):           {total_c1_perfect}/{total_anims} ({100*total_c1_perfect/max(total_anims,1):.1f}%)")
    print(f"  Empty skipped:           {total_skipped_empty}")
    print(f"  Duplicates merged:       {total_deduplicated}")

    # Quality score statistics
    if all_quality_scores:
        sorted_scores = sorted(all_quality_scores)
        p50 = sorted_scores[len(sorted_scores) // 2]
        p90_idx = int(len(sorted_scores) * 0.9)
        p90 = sorted_scores[min(p90_idx, len(sorted_scores) - 1)]
        p99_idx = int(len(sorted_scores) * 0.99)
        p99 = sorted_scores[min(p99_idx, len(sorted_scores) - 1)]
        avg_score = sum(all_quality_scores) / len(all_quality_scores)
        print(f"  Quality scores:")
        print(f"    Average:  {avg_score:.1f}")
        print(f"    P50:      {p50:.1f}")
        print(f"    P90:      {p90:.1f}")
        print(f"    P99:      {p99:.1f}")
        perfect_count = sum(1 for s in all_quality_scores if s >= 100.0)
        print(f"    Perfect:  {perfect_count}/{len(all_quality_scores)} ({100*perfect_count/len(all_quality_scores):.1f}%)")

    print(f"  Warnings:                {len(all_warnings)}")
    print(f"  Errors:                  {len(all_errors)}")
    print(f"  Elapsed time:            {elapsed:.1f}s")
    print(f"  Output directory:        {output_dir}")

    # ZIP packaging
    if zip_path:
        _create_zip_package(all_output_files, output_dir, zip_path)

    if all_warnings:
        print(f"\n  Top warnings:")
        for w in all_warnings[:10]:
            print(f"    ! {w}")
        if len(all_warnings) > 10:
            print(f"    ... and {len(all_warnings) - 10} more")

    if all_errors:
        print(f"\n  Errors:")
        for e in all_errors[:5]:
            print(f"    X {e}")
        if len(all_errors) > 5:
            print(f"    ... and {len(all_errors) - 5} more")

    print()
    print("=" * 70)
    print("  DONE - Universal BBModel Animation Converter (v3)")
    print("  End-Only Adaptive C1 Blending | Content-Hash Dedup | Quality Scoring")
    print("=" * 70)

    return len(all_errors) == 0


def _create_zip_package(output_files: List[str], base_dir: str, zip_path: str) -> None:
    """Create a ZIP package containing all output files.

    Args:
        output_files: List of absolute file paths to include
        base_dir: Base directory for computing relative paths
        zip_path: Path for the output ZIP file
    """
    import zipfile

    print(f"\n  Creating ZIP package: {zip_path}")
    os.makedirs(os.path.dirname(zip_path) if os.path.dirname(zip_path) else '.', exist_ok=True)

    count = 0
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fpath in output_files:
            if os.path.exists(fpath):
                # Compute relative path from base_dir
                try:
                    rel = os.path.relpath(fpath, base_dir)
                except ValueError:
                    rel = os.path.basename(fpath)
                zf.write(fpath, rel)
                count += 1

    zip_size = os.path.getsize(zip_path) if os.path.exists(zip_path) else 0
    print(f"  ZIP created: {count} files, {zip_size / 1024:.1f} KB")


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Universal BBModel Animation Converter with End-Only Adaptive C1 Continuity (v3)"
    )
    parser.add_argument("--input", required=True,
                        help="Input directory with .bbmodel files")
    parser.add_argument("--output", required=True,
                        help="Output directory for .animation.json + .geo.json + .png")
    parser.add_argument("--zip", type=str, default=None,
                        help="Path for ZIP packaging of output files")
    parser.add_argument("--no-c1", action="store_true",
                        help="Disable C1 continuity enforcement")
    parser.add_argument("--no-duration-opt", action="store_true",
                        help="Disable duration optimization")
    parser.add_argument("--no-autocorr", action="store_true",
                        help="Disable autocorrelation period detection")
    parser.add_argument("--blend-ratio", type=float, default=0.10,
                        help="Base C1 blend window ratio (default: 0.10, adaptive up to 4x)")
    parser.add_argument("--dp-rot", type=float, default=0.05,
                        help="DP epsilon for rotation (degrees, default: 0.05)")
    parser.add_argument("--dp-pos", type=float, default=0.008,
                        help="DP epsilon for position (pixels, default: 0.008)")
    parser.add_argument("--no-skip-empty", action="store_true",
                        help="Don't skip empty animations")
    parser.add_argument("--no-dedup", action="store_true",
                        help="Disable case-insensitive deduplication")
    parser.add_argument("--no-content-hash", action="store_true",
                        help="Disable SHA-256 content-hash dedup")
    parser.add_argument("--no-smart-merge", action="store_true",
                        help="Disable smart bone-channel merging for duplicates")
    parser.add_argument("--no-name-norm", action="store_true",
                        help="Disable animation name normalization")
    parser.add_argument("--namespace", type=str, default="",
                        help="Namespace for animation name normalization")
    args = parser.parse_args()

    config = ConverterConfig(
        enable_c1_enforcement=not args.no_c1,
        enable_duration_optimization=not args.no_duration_opt,
        autocorrelation_enabled=not args.no_autocorr,
        blend_window_ratio=args.blend_ratio,
        dp_epsilon_rotation=args.dp_rot,
        dp_epsilon_position=args.dp_pos,
        skip_empty_animations=not args.no_skip_empty,
        deduplicate_case_insensitive=not args.no_dedup,
        content_hash_dedup=not args.no_content_hash,
        smart_bone_merge=not args.no_smart_merge,
        normalize_animation_names=not args.no_name_norm,
        animation_namespace=args.namespace,
    )

    success = batch_convert(args.input, args.output, config, args.zip)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
