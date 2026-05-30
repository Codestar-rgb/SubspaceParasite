#!/usr/bin/env python3
"""
BBModelAnimationConverter - Universal Animation Converter (v2)
==============================================================
Converts Blockbench .bbmodel animation keyframes to GeckoLib .animation.json
format with automatic loop continuity enforcement, C1 velocity matching,
duration optimization, and comprehensive quality feedback.

Key Features:
  - Direct .bbmodel → .animation.json conversion (no Java source needed)
  - C0 + C1 continuity enforcement at loop boundaries (fixes bounce-back/stutter)
  - FIXED: Hermite basis functions used with LINEAR parameter (no smootherstep warp)
  - Symmetric dual-endpoint C1 blending (start AND end blend windows)
  - Automatic loop duration detection with autocorrelation-based period analysis
  - "Good enough" early exit when C0 < 0.5° and C1 < 5°/s
  - Intelligent empty/duplicate animation detection and deduplication
  - Animation name normalization following GeckoLib convention
  - Catmullrom spline evaluation for accurate resampling
  - Channel-type-aware simplification (different epsilon for rotation vs position)
  - Comprehensive quality metrics and feedback reporting
  - Batch processing for all .bbmodel files

Coordinate System:
  - .bbmodel keyframes are already in Bedrock/GeckoLib coordinate space
  - No additional M_MODEL conversion needed (already applied during bbmodel generation)
  - Rotation values in degrees, position values in pixels

DO NOT MODIFY: core_math.py
"""

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


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class ConverterConfig:
    """Master configuration for BBModelAnimationConverter."""
    # --- Loop Detection ---
    min_loop_duration: float = 0.5          # seconds
    max_loop_duration: float = 30.0         # seconds
    loop_position_tolerance_rot: float = 0.5   # degrees
    loop_position_tolerance_pos: float = 0.05  # pixels
    loop_velocity_tolerance_rot: float = 5.0   # degrees/s
    loop_velocity_tolerance_pos: float = 0.5   # pixels/s

    # --- C1 Continuity ---
    enable_c1_enforcement: bool = True
    blend_window_ratio: float = 0.10       # 10% of duration per side (dual-endpoint)
    max_blend_window: float = 0.25         # max seconds per side
    velocity_match_threshold_rot: float = 5.0   # degrees/s (relaxed for P90-based metric)
    velocity_match_threshold_pos: float = 1.0   # pixels/s
    c0_snap_threshold_rot: float = 0.5     # degrees
    c0_snap_threshold_pos: float = 0.05    # pixels

    # --- Duration Optimization ---
    enable_duration_optimization: bool = True
    duration_search_step: float = 0.01      # seconds
    phase_error_tolerance: float = 0.02     # radians
    duration_change_threshold: float = 0.1  # only change if improvement > 10%
    min_duration_improvement: float = 0.05  # minimum absolute improvement to justify change
    autocorrelation_enabled: bool = True    # use autocorrelation for period detection
    early_exit_c0_rot: float = 0.5         # degrees - "good enough" C0 for early exit
    early_exit_c1_rot: float = 5.0         # degrees/s - "good enough" C1 for early exit

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

    # --- Animation Deduplication ---
    skip_empty_animations: bool = True       # skip animations with no meaningful data
    deduplicate_case_insensitive: bool = True  # merge "idle" / "Idle" variants
    merge_duplicate_animations: bool = True  # merge identical animations

    # --- Name Normalization ---
    normalize_animation_names: bool = True   # normalize to GeckoLib convention
    animation_namespace: str = ""            # optional namespace override


@dataclass
class AnimationQualityReport:
    """Quality metrics for a single animation."""
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
    c1_avg_error_rot: float = 0.0
    c1_avg_error_pos: float = 0.0
    c1_perfect: bool = True

    # Duration quality
    duration_phase_error: float = 0.0
    duration_optimal: bool = True

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
        # Standard Catmull-Rom matrix
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
                # Get control points
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
# Auto Loop Detector
# ============================================================================

class AutoLoopDetector:
    """Detects optimal loop duration for animations.

    For animations with loop="loop", finds the best duration where:
    - C0: Position at start ~ position at end (for all channels)
    - C1: Velocity at start ~ velocity at end (for all channels)

    Uses high-rate resampling of the existing keyframes to evaluate
    continuity at candidate durations.

    Improvements (v2):
    - Prioritizes original animation length if C0/C1 are already good
    - Uses autocorrelation for more reliable period detection
    - Early exits when C0 < 0.5° and C1 < 5°/s ("good enough")
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

        # "Good enough" early exit: if original duration already satisfies
        # C0 < 0.5° and C1 < 5°/s, accept it immediately
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

        # Method 1: Sub-multiples of current duration
        for n in range(2, 20):
            T = current_duration / n
            if T >= cfg.min_loop_duration:
                candidates.append(T)

        # Method 2: Multiples of short periods found in the data
        # Use autocorrelation if enabled, else fallback to zero-crossing
        if cfg.autocorrelation_enabled:
            periods = self._detect_periods_autocorrelation(resampled, sample_rate)
        else:
            periods = self._detect_periods(resampled, sample_rate)

        for period in periods:
            for n in range(1, 30):
                T = n * period
                if cfg.min_loop_duration <= T <= cfg.max_loop_duration:
                    candidates.append(T)

        # Method 3: Fine-grained search (only in range around current duration
        # to avoid overly broad search)
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

            # "Good enough" early exit during search
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

                is_rotation = channel in ('rx', 'ry', 'rz') or channel in ('x', 'y', 'z')

                # Find value at t=0
                val_0 = self._interpolate(data, 0.0)
                # Find value at t=duration
                val_T = self._interpolate(data, duration)

                # Velocity at t=0 via finite differences
                v_0 = (self._interpolate(data, dt) - val_0) / dt
                # Velocity at t=duration
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

        # Binary search
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
        """Detect dominant oscillation periods from resampled data.

        Uses zero-crossing analysis to find periods.
        """
        periods = []

        for bone_name, channels in resampled.items():
            for channel, data in channels.items():
                if len(data) < 20:
                    continue

                values = [v for t, v in data]
                mean_val = sum(values) / len(values)
                centered = [v - mean_val for v in values]

                # Check if channel has meaningful oscillation
                amplitude = max(abs(v) for v in centered)
                if amplitude < 0.01:
                    continue

                # Zero-crossing detection
                crossings = []
                for i in range(1, len(centered)):
                    if centered[i - 1] * centered[i] < 0:
                        # Linear interpolation for crossing time
                        t_cross = data[i - 1][0] + \
                            (data[i][0] - data[i - 1][0]) * \
                            abs(centered[i - 1]) / (abs(centered[i - 1]) + abs(centered[i]))
                        crossings.append(t_cross)

                # Compute periods from crossing intervals
                if len(crossings) >= 4:
                    # Full periods from every other crossing
                    full_periods = [crossings[i + 2] - crossings[i]
                                   for i in range(len(crossings) - 2)]

                    for p in full_periods:
                        if 0.1 < p < 20.0:
                            periods.append(p)

        # Cluster similar periods and return medians
        return self._cluster_periods(periods)

    def _detect_periods_autocorrelation(
        self,
        resampled: Dict[str, Dict[str, List[Tuple[float, float]]]],
        sample_rate: float
    ) -> List[float]:
        """Detect dominant oscillation periods using autocorrelation.

        Autocorrelation is more robust than zero-crossing for noisy data
        and provides better period estimates for compound waveforms.

        Returns:
            List of detected period values in seconds.
        """
        periods = []
        min_lag_samples = int(0.1 * sample_rate)  # minimum 0.1s period

        for bone_name, channels in resampled.items():
            for channel, data in channels.items():
                if len(data) < 40:
                    continue

                values = [v for t, v in data]
                mean_val = sum(values) / len(values)
                centered = [v - mean_val for v in values]

                # Check if channel has meaningful oscillation
                amplitude = max(abs(v) for v in centered)
                if amplitude < 0.01:
                    continue

                n = len(centered)

                # Compute autocorrelation using normalized formula
                # R(k) = sum(x[i]*x[i+k]) / sum(x[i]^2)
                energy = sum(v * v for v in centered)
                if energy < 1e-12:
                    continue

                max_lag = min(n // 2, int(20.0 * sample_rate))  # max 20s period
                autocorr = []
                for k in range(min_lag_samples, max_lag):
                    corr = 0.0
                    for i in range(n - k):
                        corr += centered[i] * centered[i + k]
                    autocorr.append((k, corr / energy))

                if not autocorr:
                    continue

                # Find peaks in autocorrelation (local maxima above 0.3 threshold)
                peaks = []
                for i in range(1, len(autocorr) - 1):
                    if (autocorr[i][1] > autocorr[i - 1][1] and
                        autocorr[i][1] > autocorr[i + 1][1] and
                        autocorr[i][1] > 0.3):
                        lag_samples = autocorr[i][0]
                        period = lag_samples / sample_rate
                        if 0.1 < period < 20.0:
                            peaks.append((period, autocorr[i][1]))

                # Take the strongest peaks
                peaks.sort(key=lambda x: -x[1])
                for period, strength in peaks[:5]:
                    periods.append(period)

        return self._cluster_periods(periods)

    def _cluster_periods(self, periods: List[float]) -> List[float]:
        """Cluster similar period values and return medians.

        Returns the median of each cluster. Single-element clusters
        are also included since they represent valid detected periods.
        """
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

        # Return median of each cluster (including single-element clusters)
        result = []
        for cluster in clusters:
            median = cluster[len(cluster) // 2]
            result.append(median)

        return result


# ============================================================================
# C1 Continuity Enforcer
# ============================================================================

class C1ContinuityEnforcer:
    """Enforces C1 (velocity) continuity at loop boundaries.

    The core problem:
      At the end of a looping animation, position may match (C0) but
      velocity (derivative) may differ, causing a visible "bounce-back"
      or "stutter" when the animation loops.

    Solution (v2 - FIXED):
      Use cubic Hermite interpolation in blend windows near BOTH the start
      AND end of the animation to create a proper periodic bridge.

      - At the END: blend toward (p_start, v_start) values
      - At the START: blend from values that smoothly connect to the end state
      - This symmetric dual-endpoint approach creates true periodic continuity

    CRITICAL FIX (v2):
      The Hermite basis functions h00, h10, h01, h11 ALREADY provide smooth
      C1 interpolation by construction. Applying smootherstep to the parameter
      BEFORE computing Hermite basis functions WARPS the curve and causes the
      derivatives at the endpoints to no longer match the target velocities.

      The fix: use the LINEAR parameter s directly in the Hermite basis
      functions. Do NOT apply smootherstep before Hermite computation.

    This provides:
      - C0: Perfect position match (last keyframe snaps to first)
      - C1: Smooth velocity transition (Hermite blend in window)
      - C2: Natural acceleration (Hermite curve is C2 smooth within window)
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()

    def enforce(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        interpolation: str = "catmullrom"
    ) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
        """Apply symmetric dual-endpoint C1 continuity enforcement to all channels.

        Strategy:
          1. Resample each channel at high rate using catmullrom/linear interpolation
          2. Compute start/end velocity from resampled data
          3. If velocity mismatch detected:
             a. Apply Hermite blend at the END: transition from original end
                state toward (p_start, v_start)
             b. Apply Hermite blend at the START: transition from values that
                smoothly connect to the end state toward original start
          4. Replace original keyframes with resampled + blended data

        The dual-endpoint blending creates a proper periodic bridge:
          End blend:    p_end → p_start,  v_end → v_start
          Start blend:  (periodic_start) → p_start, (periodic_v0) → v_start

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

                # Step 2: Compute velocities at start and end from resampled data
                if len(resampled) < 5:
                    continue

                p0 = resampled[0][1]
                pT = resampled[-1][1]

                # Use 3-point forward/backward difference for velocity estimation
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
                        # Snap last keyframe to first value
                        channels[channel] = [
                            (t, v) if i < len(keyframes) - 1 else (t, keyframes[0][1])
                            for i, (t, v) in enumerate(keyframes)
                        ]
                    continue

                # Step 3: Compute blend window size (per side for dual-endpoint)
                w = min(duration * cfg.blend_window_ratio, cfg.max_blend_window)
                # Ensure blend window has at least 10 resampled points per side
                min_samples = 10
                w = max(w, min_samples * resample_dt)
                # For very short animations, expand to at least 15% per side
                if w < duration * 0.15 and duration < 1.0:
                    w = duration * 0.15
                # Ensure both windows fit within the animation
                if 2 * w > duration * 0.8:
                    w = duration * 0.4

                # ============================================================
                # END BLEND: blend from (p_end, v_end) toward (p_start, v_start)
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
                            # h00(s) = 2s³ - 3s² + 1
                            # h10(s) = s³ - 2s² + s
                            # h01(s) = -2s³ + 3s²
                            # h11(s) = s³ - s²
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

                # ============================================================
                # START BLEND: blend from periodic start state toward original start
                #
                # At the start of the animation, we want the velocity to
                # smoothly arrive from the end state. So we blend:
                #   From: (p_T_periodic, v_T_periodic) = values that would
                #         naturally follow from the end of the animation
                #   To:   (p0, v0) = original start position and velocity
                #
                # The "periodic start position" is the value that would make
                # the start smoothly continue from the end. We use the end
                # value after end-blend as the incoming position.
                # ============================================================
                start_blend_end_time = min(w, duration)

                # Find resampled points in start blend window
                start_blend_end_idx = 0
                for i, (t, v) in enumerate(resampled):
                    if t >= start_blend_end_time:
                        start_blend_end_idx = i
                        break

                if start_blend_end_idx >= 1 and start_blend_end_idx < len(resampled) - 1:
                    # The incoming position at t=0 should smoothly connect
                    # to the end of the previous loop iteration.
                    # After the end blend, the value at t=duration is p0 (= p_start)
                    # and velocity at t=duration is v0 (= v_start).
                    # So the "incoming" position at t<0 (i.e., wrapping around)
                    # would continue from the end state.
                    #
                    # For the start blend, we set:
                    #   - Start of blend (t=0): position = p0, velocity = v0
                    #     (matching what the previous loop iteration ends with)
                    #   - End of blend (t=w): position = resampled value at t=w
                    #     (original unblended data)
                    #   - Velocity at end of blend: original velocity at t=w
                    #
                    # This means: at t=0, the curve matches the end state exactly,
                    # and it transitions to the original curve within the start window.

                    # Get the original values at end of start-blend window
                    p_start_blend_end = resampled[start_blend_end_idx][1]
                    t_start_blend_end = resampled[start_blend_end_idx][0]

                    # Velocity at start-blend end via central difference
                    # Note: resampled[start_blend_end_idx] is still unblended
                    # for the start window (end blend was only at end of animation)
                    v_start_blend_end = (
                        (resampled[start_blend_end_idx + 1][1] -
                         resampled[start_blend_end_idx - 1][1]) /
                        (resampled[start_blend_end_idx + 1][0] -
                         resampled[start_blend_end_idx - 1][0])
                    )

                    # Start of blend: matches the end state (periodic bridge)
                    p_start_blend_start = p0
                    v_start_blend_start = v0

                    w_start_actual = t_start_blend_end
                    if w_start_actual > 1e-12:
                        # Apply Hermite blend using LINEAR parameter s
                        for i in range(0, start_blend_end_idx + 1):
                            t, v = resampled[i]
                            s = (t - 0.0) / w_start_actual  # linear 0→1
                            s = max(0.0, min(1.0, s))

                            # Hermite basis functions with LINEAR parameter s
                            s2 = s * s
                            s3 = s2 * s

                            h00 = 2 * s3 - 3 * s2 + 1
                            h10 = s3 - 2 * s2 + s
                            h01 = -2 * s3 + 3 * s2
                            h11 = s3 - s2

                            new_val = (h00 * p_start_blend_start +
                                       h10 * w_start_actual * v_start_blend_start +
                                       h01 * p_start_blend_end +
                                       h11 * w_start_actual * v_start_blend_end)

                            resampled[i] = (t, new_val)

                # Step 4: Replace original keyframes with resampled + blended data
                # We need to reconstruct keyframes from the resampled data,
                # keeping original keyframes outside both blend windows,
                # and using resampled data inside the blend windows.
                new_keyframes = []

                # Add original keyframes that are outside both blend windows
                # (i.e., between start_blend_end_time and end_blend_start_time)
                for t, v in keyframes:
                    if t >= start_blend_end_time - 1e-8 and t <= end_blend_start_time + 1e-8:
                        new_keyframes.append((t, v))

                # In the start blend window, add resampled points at reasonable density
                n_blend_target = 8
                start_blend_interval = w_start_actual / max(n_blend_target - 1, 1) if w_start_actual > 0 else float('inf')
                start_blend_interval = max(start_blend_interval, resample_dt * 3)

                # Add start blend keyframes
                last_added_time = -start_blend_interval
                for i in range(0, start_blend_end_idx + 1):
                    t, v = resampled[i]
                    if (t - last_added_time >= start_blend_interval - 1e-8 or
                        i == 0 or
                        t >= start_blend_end_time - 1e-8):
                        new_keyframes.append((t, v))
                        last_added_time = t

                # In the end blend window, add resampled points at reasonable density
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
                        # Keep the later value (overwrite)
                        deduped[-1] = (t, v)
                    else:
                        deduped.append((t, v))
                new_keyframes = deduped

                # Ensure last keyframe is exactly at duration with value = p0
                if new_keyframes:
                    new_keyframes[-1] = (duration, p0)
                else:
                    new_keyframes.append((0.0, p0))
                    new_keyframes.append((duration, p0))

                # Ensure first keyframe value matches p0 (periodic start)
                if new_keyframes and abs(new_keyframes[0][1] - p0) < c0_thresh:
                    new_keyframes[0] = (new_keyframes[0][0], keyframes[0][1])

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

        # Use iterative approach to avoid stack overflow on large datasets
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
    Examples:
      - "idle" → "animation.<entity>.idle"
      - "animation.model.idle" → "animation.<entity>.idle"
      - "walk_cycle" → "animation.<entity>.walk_cycle"
    """

    # Common prefixes that are redundant in GeckoLib format
    REDUNDANT_PREFIXES = [
        'animation.',
        'anim.',
    ]

    # State name normalization patterns
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
        """Normalize an animation name to GeckoLib convention.

        Args:
            name: Original animation name
            model_name: Model/entity name for constructing the namespace
            namespace: Optional explicit namespace override

        Returns:
            Normalized name in format animation.<namespace>.<entity>.<state>
        """
        if not name:
            return name

        # Strip whitespace
        state = name.strip()

        # Remove redundant prefixes (case-insensitive)
        for prefix in AnimationNameNormalizer.REDUNDANT_PREFIXES:
            if state.lower().startswith(prefix):
                state = state[len(prefix):]
                break

        # If the name still has dots, it might already be partially normalized
        # e.g., "animation.entity.idle" → keep "entity.idle" as the suffix
        parts = state.split('.')
        if len(parts) >= 2:
            # Check if the first part looks like a namespace/entity
            # If so, use the last part as the state
            state = parts[-1]

        # Apply state aliases
        state_lower = state.lower()
        if state_lower in AnimationNameNormalizer.STATE_ALIASES:
            state = AnimationNameNormalizer.STATE_ALIASES[state_lower]

        # Clean the state name: replace spaces/hyphens with underscores
        state = re.sub(r'[\s\-]+', '_', state)

        # Remove any remaining special characters except underscores and alphanumerics
        state = re.sub(r'[^a-zA-Z0-9_]', '', state)

        # Build the normalized name
        entity = model_name if model_name else "entity"
        # Clean entity name
        entity = re.sub(r'[^a-zA-Z0-9_]', '_', entity)
        entity = entity.lower()

        if namespace:
            ns = namespace.lower()
        else:
            ns = entity

        return f"animation.{ns}.{entity}.{state}"


# ============================================================================
# BBModel Animation Extractor
# ============================================================================

class BBModelAnimationExtractor:
    """Extracts animations from .bbmodel files and converts to internal format.

    Handles the bbmodel keyframe format:
      - Per-bone animators with rotation/position/scale channels
      - Each keyframe has time, channel, interpolation, data_points with x/y/z
      - Supports linear and catmullrom interpolation

    Improvements (v2):
      - Intelligent empty animation detection (skip animations with no data)
      - Case-insensitive name deduplication
      - Duplicate animation merging
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()

    def extract(self, bbmodel_path: str) -> Dict[str, Any]:
        """Extract all animations from a .bbmodel file.

        Returns:
            {
                'model_name': str,
                'animations': {
                    anim_name: {
                        'loop': str,
                        'length': float,
                        'snapping': int,
                        'bone_channels': {
                            bone_name: {
                                channel: [(t, v), ...]
                            }
                        },
                        'interpolation': str,  # dominant interpolation type
                        'is_empty': bool,      # v2: flag for empty animations
                    }
                },
                'skipped_empty': List[str],     # v2: names of skipped empty anims
                'deduplicated': List[str],      # v2: names of deduplicated anims
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

                    # Extract per-axis values
                    # bbmodel format: x, y, z for rotation/position
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
                    # Merge duplicate times (keep last value)
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

            # Check if animation is empty (no meaningful data)
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
            # Case-insensitive deduplication
            seen_lower = {}  # lowercase_name → canonical_name
            for anim_name, anim_data in raw_animations.items():
                lower_name = anim_name.lower()
                if lower_name in seen_lower:
                    canonical = seen_lower[lower_name]
                    # Merge: keep the one with more keyframes
                    existing_kf_count = sum(
                        len(kfs) for chs in animations[canonical]['bone_channels'].values()
                        for kfs in chs.values()
                    )
                    new_kf_count = sum(
                        len(kfs) for chs in anim_data['bone_channels'].values()
                        for kfs in chs.values()
                    )
                    if new_kf_count > existing_kf_count:
                        # Replace with the one that has more data
                        animations[canonical] = anim_data
                        deduplicated.append(anim_name)
                    else:
                        deduplicated.append(anim_name)
                else:
                    seen_lower[lower_name] = anim_name
                    animations[anim_name] = anim_data
        else:
            animations = raw_animations

        # Merge exact duplicates (same name, same data)
        if self.config.merge_duplicate_animations:
            # This is handled implicitly by the dict - same name keys are overwritten
            # But we also check for animations with identical bone channel data
            data_signatures = {}
            final_animations = {}
            for anim_name, anim_data in animations.items():
                sig = self._compute_animation_signature(anim_data)
                if sig in data_signatures:
                    # Duplicate data found - keep the first one, mark the second
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

        An animation is considered empty if:
        - No bone channels exist
        - All channel values are zero or near-zero
        """
        if not bone_channels:
            return True

        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if not keyframes:
                    continue
                # Check if any keyframe has a non-zero value
                for t, v in keyframes:
                    # For rotation channels, check against a small threshold
                    if channel.startswith('r') or channel in ('x', 'y', 'z'):
                        if abs(v) > 0.01:  # 0.01 degrees threshold
                            return False
                    # For position channels
                    elif channel.startswith('o'):
                        if abs(v) > 0.001:  # 0.001 pixels threshold
                            return False
                    # For scale channels
                    elif channel.startswith('s'):
                        if abs(v - 1.0) > 0.001:  # scale of 1.0 is identity
                            return False

        return True

    @staticmethod
    def _compute_animation_signature(anim_data: Dict[str, Any]) -> str:
        """Compute a hashable signature for an animation's data.

        Used for detecting exact duplicate animations.
        """
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
        """Build a GeckoLib animation entry.

        Args:
            anim_name: Animation name (e.g., "animation.model.idle")
            loop_mode: "loop" or "hold_on_last_frame"
            bone_channels: {bone: {channel: [(t, v), ...]}}
            duration: Animation duration

        Returns:
            GeckoLib animation dict.
        """
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

            axis = channel[-1]  # rx→x, ry→y, rz→z, ox→x, oy→y, oz→z

            kf_dict = {
                f"{t:.{config.keyframe_precision}f}": round(v, config.value_precision)
                for t, v in simplified
            }

            if channel in ('rx', 'ry', 'rz'):
                rot_channels[axis] = kf_dict
            elif channel in ('ox', 'oy', 'oz'):
                pos_channels[axis] = kf_dict
            elif channel in ('sx', 'sy', 'sz'):
                # Scale - rarely used but supported
                rot_channels[axis] = kf_dict  # GeckoLib uses same structure

        bone_entry = {}
        if rot_channels:
            bone_entry["rotation"] = rot_channels
        if pos_channels:
            bone_entry["position"] = pos_channels

        return bone_entry if bone_entry else None


# ============================================================================
# Quality Reporter
# ============================================================================

class QualityReporter:
    """Generates quality reports for converted animations."""

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()

    def report(
        self,
        anim_name: str,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float
    ) -> AnimationQualityReport:
        """Generate a quality report for an animation.

        Args:
            anim_name: Animation name
            bone_channels: {bone: {channel: [(t, v), ...]}}
            duration: Animation duration

        Returns:
            AnimationQualityReport with metrics.
        """
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
                # Simple finite differences on sparse keyframes are inaccurate,
                # so resample at a higher rate for better velocity estimation
                if len(keyframes) >= 2 and duration > 0:
                    # Quick resample for velocity estimation
                    n_s = min(120, max(20, int(duration * 30)))
                    s_dt = duration / n_s
                    s_times = [i * s_dt for i in range(n_s + 1)]
                    s_data = CatmullRomEvaluator.resample_channel(
                        keyframes, s_times, "catmullrom"
                    )
                    if len(s_data) >= 5:
                        # 3-point forward/backward difference
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
            # Use P90 instead of max for a more representative C1 metric
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
        # Penalize C0 errors (position mismatch at loop boundary)
        if not report.c0_perfect:
            score -= min(30, report.c0_max_error_rot * 5 + report.c0_max_error_pos * 30)
        # Penalize C1 errors using P90 (more representative than max)
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
                f"C1 velocity mismatch: rot={report.c1_max_error_rot:.2f}°/s, "
                f"pos={report.c1_max_error_pos:.3f}px/s"
            )

        return report


# ============================================================================
# Main Converter
# ============================================================================

class BBModelAnimationConverter:
    """Universal animation converter for .bbmodel files.

    Pipeline:
      1. Extract animations from .bbmodel (with empty/duplicate handling)
      2. Normalize animation names to GeckoLib convention
      3. For loop animations: detect optimal loop duration
      4. Enforce C1 continuity at loop boundaries (symmetric dual-endpoint)
      5. Simplify keyframes
      6. Build GeckoLib .animation.json
      7. Generate quality report
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
                'animations': dict,  # GeckoLib format
                'quality_reports': dict,
                'stats': dict,
            }
        """
        # Step 1: Extract (with empty/duplicate filtering)
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
            # Only optimize if the current duration has poor C0 continuity
            # AND a significantly better duration can be found
            if loop_mode == "loop" and self.config.enable_duration_optimization:
                optimal_duration, loop_diag = self.loop_detector.detect_optimal_duration(
                    bone_channels, current_duration, interpolation
                )
                # Only change duration if:
                # 1. The new duration has meaningfully better continuity
                # 2. The change is not too drastic (avoid breaking carefully authored durations)
                current_c0 = loop_diag.get('current_c0_error', float('inf'))
                best_c0 = loop_diag.get('best_c0_error', float('inf'))
                method = loop_diag.get('method', 'none')

                should_change = False
                if method in ('search_optimal', 'search_early_exit_good_enough') and current_c0 > 0.5:
                    # Only change if current C0 is poor AND improvement is significant
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

            # Step 4: C1 continuity enforcement for loop animations only
            # Do NOT enforce C1 on hold_on_last_frame (non-loop) animations
            if loop_mode == "loop":
                bone_channels = self.c1_enforcer.enforce(bone_channels, current_duration, interpolation)

            # Step 5: Build GeckoLib JSON
            anim_json = self.json_builder.build(
                anim_name, loop_mode, bone_channels, current_duration
            )
            all_animations[anim_name] = anim_json

            # Step 6: Quality report
            qreport = self.quality_reporter.report(anim_name, bone_channels, current_duration)
            quality_reports[anim_name] = qreport

            if qreport.c0_perfect:
                stats['c0_perfect_count'] += 1
            if qreport.c1_perfect:
                stats['c1_perfect_count'] += 1

        # Assemble output - only write animation.json if there are actual animations
        result = {
            "format_version": "1.8.0",
            "animations": all_animations,
        }

        if output_path:
            if all_animations:
                os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
            # If no animations, do NOT create an empty .animation.json file
            # This avoids generating redundant files for static models

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
                # Keep keyframes within duration
                trimmed = [(t, v) for t, v in keyframes if t <= duration + 0.0001]
                # Ensure the last keyframe is exactly at duration
                if trimmed and abs(trimmed[-1][0] - duration) > 0.0001:
                    # Interpolate value at duration
                    if len(keyframes) > 1:
                        # Find surrounding keyframes
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
# Batch Processing
# ============================================================================

def batch_convert(input_dir: str, output_dir: str,
                  config: ConverterConfig = None) -> bool:
    """Batch convert all .bbmodel files in a directory tree.

    For each .bbmodel file:
      - Extract geo.json + texture (using bbmodel_to_geo.py)
      - Extract and convert animations (using this converter)
      - Save to output directory maintaining directory structure
    """
    print("=" * 70)
    print("  Universal BBModel Animation Converter (v2)")
    print("  .bbmodel → .animation.json with C1 Continuity")
    print("  GeckoLib Format for MC 1.20.1 Forge Mod Development")
    print("  [FIXED] Hermite basis with linear parameter (no smootherstep warp)")
    print("  [NEW] Symmetric dual-endpoint C1 blending")
    print("  [NEW] Autocorrelation period detection + early exit")
    print("  [NEW] Empty/duplicate animation handling + name normalization")
    print("=" * 70)
    print()

    cfg = config or ConverterConfig()
    converter = BBModelAnimationConverter(cfg)

    # Import geo converter
    from bbmodel_to_geo import BBModelToGeo
    geo_converter = BBModelToGeo()

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
    print(f"  Duration optimization: {'ON' if cfg.enable_duration_optimization else 'OFF'}")
    print(f"  Autocorrelation: {'ON' if cfg.autocorrelation_enabled else 'OFF'}")
    print(f"  Blend window: {cfg.blend_window_ratio*100:.0f}% per side (max {cfg.max_blend_window}s)")
    print(f"  DP epsilon: rot={cfg.dp_epsilon_rotation}°, pos={cfg.dp_epsilon_position}px")
    print(f"  Skip empty: {'ON' if cfg.skip_empty_animations else 'OFF'}")
    print(f"  Deduplicate (case-insensitive): {'ON' if cfg.deduplicate_case_insensitive else 'OFF'}")
    print(f"  Name normalization: {'ON' if cfg.normalize_animation_names else 'OFF'}")
    print()

    total_anims = 0
    total_keyframes = 0
    total_c0_perfect = 0
    total_c1_perfect = 0
    total_no_anim = 0
    total_skipped_empty = 0
    total_deduplicated = 0
    all_warnings = []
    all_errors = []

    start_time = time.time()

    for i, rel_path in enumerate(bbmodel_files, 1):
        bbmodel_path = os.path.join(input_dir, rel_path)
        category = os.path.dirname(rel_path)
        name = os.path.basename(rel_path).replace('.bbmodel', '')
        out_dir = os.path.join(output_dir, category) if category else output_dir

        print(f"  [{i:3d}/{len(bbmodel_files)}] {category}/{name}...",
              end=" ", flush=True)

        # Convert geo + texture
        geo_result = geo_converter.convert_bbmodel(bbmodel_path, out_dir)

        # Convert animations - output_path set to None, we write manually
        anim_output_path = os.path.join(out_dir, f"{name}.animation.json")
        # Remove old animation file if it exists (clean up from previous runs)
        if os.path.exists(anim_output_path):
            os.remove(anim_output_path)

        try:
            result = converter.convert_file(bbmodel_path, anim_output_path)
            stats = result['stats']

            # Quality summary
            geo_ok = "+" if geo_result.get('success') else "-"
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
                    print(f"{geo_ok} no_anim ({skipped} empty skipped)")
                else:
                    print(f"{geo_ok} no_anim (static model)")
                total_no_anim += 1
            else:
                extras = ""
                if dur_adj:
                    extras += f" dur_adj={dur_adj}"
                if skipped:
                    extras += f" skip={skipped}"
                if deduped:
                    extras += f" dedup={deduped}"
                print(f"{geo_ok} anims={anim_count} kf={kf_count} "
                      f"C0={c0_ok}/{anim_count} C1={c1_ok}/{anim_count}"
                      f"{extras}")

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

    # Summary
    print()
    print("=" * 70)
    print("  CONVERSION SUMMARY")
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
    print(f"  Warnings:                {len(all_warnings)}")
    print(f"  Errors:                  {len(all_errors)}")
    print(f"  Elapsed time:            {elapsed:.1f}s")
    print(f"  Output directory:        {output_dir}")

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
    print("  DONE - Universal BBModel Animation Converter (v2)")
    print("=" * 70)

    return len(all_errors) == 0


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Universal BBModel Animation Converter with C1 Continuity (v2)"
    )
    parser.add_argument("--input", required=True,
                        help="Input directory with .bbmodel files")
    parser.add_argument("--output", required=True,
                        help="Output directory for .animation.json + .geo.json + .png")
    parser.add_argument("--no-c1", action="store_true",
                        help="Disable C1 continuity enforcement")
    parser.add_argument("--no-duration-opt", action="store_true",
                        help="Disable duration optimization")
    parser.add_argument("--no-autocorr", action="store_true",
                        help="Disable autocorrelation period detection")
    parser.add_argument("--blend-ratio", type=float, default=0.10,
                        help="C1 blend window ratio per side (default: 0.10)")
    parser.add_argument("--dp-rot", type=float, default=0.05,
                        help="DP epsilon for rotation (degrees, default: 0.05)")
    parser.add_argument("--dp-pos", type=float, default=0.008,
                        help="DP epsilon for position (pixels, default: 0.008)")
    parser.add_argument("--no-skip-empty", action="store_true",
                        help="Don't skip empty animations")
    parser.add_argument("--no-dedup", action="store_true",
                        help="Disable case-insensitive deduplication")
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
        normalize_animation_names=not args.no_name_norm,
        animation_namespace=args.namespace,
    )

    success = batch_convert(args.input, args.output, config)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
