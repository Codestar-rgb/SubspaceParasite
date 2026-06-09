#!/usr/bin/env python3
"""
BBModelAnimationConverter - Universal Animation Converter (v5)
==============================================================
Converts Blockbench .bbmodel animation keyframes to GeckoLib .animation.json
format with automatic loop continuity enforcement, C1 velocity matching,
duration optimization, and comprehensive quality feedback.

Key Improvements over v4:
  - GLOBAL CUBIC C1 CORRECTION: Replaces end-only Hermite blend / velocity
    transition bridge with a correction curve distributed across the ENTIRE
    animation. Computes c(t) = a*t^3 + b*t^2 that guarantees C0+C1 match
    at loop boundaries while preserving the start of the animation exactly.
  - HYBRID C1 ENFORCER: Primary method is Global Cubic Correction (guaranteed
    C0+C1). Falls back to local end-blend with velocity bridge when global
    correction would cause >15% distortion. Special handling for near-static
    channels (snap last keyframe to first).
  - PER-CHANNEL ADAPTIVE BLEND WINDOW: Each channel gets its own blend window
    based on its C1 error, with minimum 10 resampled points and maximum 40%
    of duration.
  - ENHANCED EMPTY ANIMATION CONSOLIDATION: Truly-empty detection (all values
    below threshold), near-empty detection (mark as static but keep), semantic
    deduplication (same name after normalization), cross-animation bone
    consolidation (union of bone channels from duplicates).
  - IMPROVED QUALITY SCORING: Stricter thresholds (C0 < 0.1 deg, C1 < 1.5
    deg/s), new correction-magnitude metric, fidelity-score metric (percentage
    of animation preserved). Higher scores for global cubic vs local blend.
  - ENHANCED DURATION OPTIMIZATION: Phase-matching across ALL channels
    simultaneously, harmonic search (T/n for n=2,3,4,... and n*T for n=2,3),
    combined phase error minimization.

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
TICK_DURATION = 1.0 / TICKS_PER_SECOND  # 0.05s
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
    """Master configuration for BBModelAnimationConverter v5."""
    # --- Loop Detection ---
    min_loop_duration: float = 0.5          # seconds
    max_loop_duration: float = 30.0         # seconds
    loop_position_tolerance_rot: float = 0.1    # degrees (tighter than v4 0.2)
    loop_position_tolerance_pos: float = 0.01   # pixels (tighter than v4 0.02)
    loop_velocity_tolerance_rot: float = 1.5     # degrees/s (tighter than v4 2.5)
    loop_velocity_tolerance_pos: float = 0.15    # pixels/s (tighter than v4 0.25)

    # --- C1 Continuity (v5: Global Cubic Correction) ---
    enable_c1_enforcement: bool = True
    blend_window_ratio: float = 0.10       # base ratio of duration for blend window (fallback)
    max_blend_window: float = 0.40         # max blend window as fraction of duration
    velocity_match_threshold_rot: float = 2.0   # degrees/s
    velocity_match_threshold_pos: float = 0.3   # pixels/s (tighter than v4 0.5)
    c0_snap_threshold_rot: float = 0.1     # degrees (tighter than v4 0.2)
    c0_snap_threshold_pos: float = 0.01    # pixels (tighter than v4 0.02)
    bounce_detection_threshold: float = 0.3  # if vT*v0 < -threshold^2, use bridge

    # --- Global Cubic Correction (v5 NEW) ---
    global_cubic_distortion_limit: float = 0.30  # max correction/amplitude ratio before fallback (v5: raised from 0.15)
    static_channel_motion_threshold_rot: float = 0.01  # degrees — below this, channel is "static"
    static_channel_motion_threshold_pos: float = 0.001  # pixels — below this, channel is "static"

    # --- Per-Channel Adaptive Blend (v5 NEW) ---
    adaptive_blend_min_points: int = 10    # minimum resampled points in blend window
    adaptive_blend_max_ratio: float = 0.40 # maximum blend window as fraction of duration

    # --- Duration Optimization ---
    enable_duration_optimization: bool = True
    duration_search_step: float = 0.01      # seconds
    phase_error_tolerance: float = 0.02     # radians
    duration_change_threshold: float = 0.03  # 3% improvement required
    min_duration_improvement: float = 0.02   # seconds
    autocorrelation_enabled: bool = True
    early_exit_c0_rot: float = 0.1         # degrees — tighter than v4 (0.2)
    early_exit_c1_rot: float = 2.0         # degrees/s
    sub_multiple_search: bool = True
    snap_to_ticks: bool = True
    tick_duration: float = 0.05             # 1/20 second

    # --- Harmonic Search (v5 NEW) ---
    harmonic_search_enabled: bool = True    # check T/n and n*T candidates
    harmonic_search_max_sub: int = 6        # check T/2, T/3, ..., T/6
    harmonic_search_max_super: int = 3      # check 2*T, 3*T

    # --- Simplification ---
    dp_epsilon_rotation: float = 0.04       # same as v4
    dp_epsilon_position: float = 0.006      # same as v4

    # --- Resampling ---
    resample_rate: float = 120.0            # Hz for catmullrom evaluation

    # --- Output ---
    keyframe_precision: int = 4             # decimal places for time
    value_precision: int = 6                # decimal places for values
    filter_zero_threshold: float = 0.001    # skip channels with only tiny values

    # --- Quality ---
    quality_warning_threshold: float = 0.3  # tighter than v4 (0.4)
    quality_error_threshold: float = 5.0    # error if C0 error > this
    c1_quality_threshold_rot: float = 8.0   # degrees/s P90
    c1_quality_threshold_pos: float = 1.0   # tighter than v4 (1.5)

    # --- Quality Scoring Thresholds (v5 NEW) ---
    c0_perfect_threshold_rot: float = 0.1   # degrees — stricter than v4's 0.2
    c0_perfect_threshold_pos: float = 0.01  # pixels
    c1_perfect_threshold_rot: float = 1.5   # degrees/s — stricter than v4's 2.5
    c1_perfect_threshold_pos: float = 0.3   # pixels/s

    # --- Animation Deduplication (v5: enhanced) ---
    skip_empty_animations: bool = False     # don't skip, keep as static
    preserve_empty_as_static: bool = True   # keep empty anims as static poses
    deduplicate_case_insensitive: bool = True  # merge "idle" / "Idle" variants
    merge_duplicate_animations: bool = True  # merge identical animations via content hash
    content_hash_dedup: bool = True          # use SHA-256 content hash for dedup
    smart_bone_merge: bool = True            # combine bone channels from case-duplicates
    always_union_bones: bool = True          # always union bone channels
    semantic_dedup_enabled: bool = True      # v5 NEW: deduplicate by normalized name

    # --- Near-Empty / Truly-Empty Detection (v5 NEW) ---
    truly_empty_rot_threshold: float = 0.01     # degrees — all values below this = truly empty
    truly_empty_pos_threshold: float = 0.001    # pixels
    near_empty_rot_threshold: float = 0.05      # degrees — near-empty but not truly empty
    near_empty_pos_threshold: float = 0.005     # pixels

    # --- Name Normalization ---
    normalize_animation_names: bool = True
    animation_namespace: str = ""


@dataclass
class BoneQualityBreakdown:
    """Per-bone quality metrics (v5 enhanced)."""
    bone_name: str
    c0_error_rot: float = 0.0
    c0_error_pos: float = 0.0
    c1_error_rot: float = 0.0
    c1_error_pos: float = 0.0
    bounce_severity: float = 0.0       # ratio of velocity reversal to avg velocity
    correction_magnitude: float = 0.0  # v5 NEW: max(|c(t)|) / amplitude for this bone
    fidelity_score: float = 1.0        # v5 NEW: 1.0 - correction_ratio

    @property
    def worst_c0(self) -> float:
        return max(self.c0_error_rot, self.c0_error_pos * 10.0)

    @property
    def worst_c1(self) -> float:
        return max(self.c1_error_rot, self.c1_error_pos * 10.0)


@dataclass
class AnimationQualityReport:
    """Quality metrics for a single animation (v5 enhanced)."""
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
    c1_avg_error_rot: float = 0.0           # P90
    c1_avg_error_pos: float = 0.0
    c1_perfect: bool = True

    # Duration quality
    duration_phase_error: float = 0.0
    duration_optimal: bool = True
    duration_adjusted: bool = False
    duration_change_reason: str = ""

    # Blend info
    blend_window_used: float = 0.0
    c1_enforcement_applied: bool = False
    c1_method: str = "none"                 # v5 NEW: "global_cubic", "local_blend", "static_snap", "none"
    bridge_used: bool = False
    bounce_back_severity: float = 0.0

    # Correction metrics (v5 NEW)
    correction_magnitude_max: float = 0.0   # max correction/amplitude across all channels
    correction_magnitude_avg: float = 0.0   # avg correction/amplitude across all channels
    fidelity_score_avg: float = 1.0         # avg fidelity across all channels
    global_cubic_used_count: int = 0        # how many channels used global cubic
    local_blend_used_count: int = 0         # how many channels used local blend fallback
    static_snap_count: int = 0              # how many channels were snapped as near-static

    # Naturalness metric (v5.1 NEW)
    naturalness_score: float = 1.0          # 1.0 = no wobbles, lower = more wobbles
    second_derivative_sign_changes: int = 0  # count of sign changes in correction curve

    # Per-bone breakdown
    bone_breakdown: List[BoneQualityBreakdown] = field(default_factory=list)
    worst_bones: List[str] = field(default_factory=list)

    # Overall
    quality_score: float = 100.0            # 0-100
    is_static: bool = False
    is_near_empty: bool = False             # v5 NEW
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ============================================================================
# Catmull-Rom Spline Evaluation (same as v3/v4 — proven correct)
# ============================================================================

class CatmullRomEvaluator:
    """Evaluates Catmull-Rom splines at arbitrary time points.

    Used for resampling animations with catmullrom interpolation
    to find optimal loop points and enforce continuity.
    """

    @staticmethod
    def evaluate(t: float, p0: float, p1: float, p2: float, p3: float,
                 alpha: float = 0.5) -> float:
        """Evaluate centripetal Catmull-Rom spline at parameter t in [0,1]."""
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
        """Evaluate first derivative of Catmull-Rom spline at parameter t in [0,1]."""
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
        """Resample a channel at specified time points."""
        if not keyframes:
            return []
        if len(keyframes) <= 1:
            return [(t, keyframes[0][1]) for t in target_times]

        result = []
        n = len(keyframes)

        for t in target_times:
            if t <= keyframes[0][0]:
                result.append((t, keyframes[0][1]))
                continue
            if t >= keyframes[-1][0]:
                result.append((t, keyframes[-1][1]))
                continue

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
                val = k0[1] + s * (k1[1] - k0[1])
                result.append((t, val))

        return result


# ============================================================================
# Auto Loop Detector (v5: harmonic search + phase-matching)
# ============================================================================

class AutoLoopDetector:
    """Detects optimal loop duration for animations.

    v5 Improvements:
    - Harmonic search: check T/n for n=2..6 and n*T for n=2,3
    - Phase-matching across ALL channels simultaneously: combined phase error
      = sum of |val(T)-val(0)| + |vel(T)-vel(0)| across all channels
    - Tighter early exit thresholds (C0 < 0.1 deg, C1 < 1.5 deg/s)
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()

    def detect_optimal_duration(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        current_duration: float,
        interpolation: str = "catmullrom"
    ) -> Tuple[float, Dict[str, Any]]:
        """Find the optimal loop duration for an animation."""
        cfg = self.config
        diagnostics = {
            'original_duration': current_duration,
            'method': 'none',
            'candidates_tested': 0,
            'best_c0_error': float('inf'),
            'best_c1_error': float('inf'),
            'best_combined_phase_error': float('inf'),
        }

        if current_duration <= 0:
            current_duration = self._compute_duration_from_keyframes(bone_channels)
            diagnostics['duration_from_keyframes'] = True
            if current_duration <= 0:
                return current_duration, diagnostics

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

        # Evaluate current duration first
        c0_err, c1_err, combined = self._evaluate_continuity_combined(
            resampled, current_duration, sample_rate
        )
        diagnostics['current_c0_error'] = c0_err
        diagnostics['current_c1_error'] = c1_err
        diagnostics['current_combined_phase_error'] = combined

        # v5.1: Ultra-fast early exit — if C0 < 0.05 deg AND C1 < 1.0 deg/s, skip ALL search
        if c0_err < 0.05 and c1_err < 1.0:
            diagnostics['method'] = 'early_exit_ultra'
            if cfg.snap_to_ticks:
                current_duration = self._snap_to_tick(current_duration)
            return current_duration, diagnostics

        # "Good enough" early exit (v5: tighter thresholds)
        if c0_err < cfg.early_exit_c0_rot and c1_err < cfg.early_exit_c1_rot:
            diagnostics['method'] = 'early_exit_good_enough'
            if cfg.snap_to_ticks:
                current_duration = self._snap_to_tick(current_duration)
            return current_duration, diagnostics

        # v5.1: Phase coherence check — verify ALL channels match at duration T
        # (not just average — a single bad channel can cause visible pops)
        phase_coherent = self._check_phase_coherence(resampled, current_duration, sample_rate)
        if phase_coherent and c0_err < cfg.loop_position_tolerance_rot and c1_err < cfg.loop_velocity_tolerance_rot:
            diagnostics['method'] = 'current_ok'
            if cfg.snap_to_ticks:
                current_duration = self._snap_to_tick(current_duration)
            return current_duration, diagnostics

        # Search for better durations
        best_duration = current_duration
        best_score = float('inf')
        best_combined = combined

        candidates = []

        # Method 1: Sub-multiples of current duration
        for n in range(2, 20):
            T = current_duration / n
            if T >= cfg.min_loop_duration:
                candidates.append(T)

        # Method 2: v5 Harmonic search — T/n for n=2..6
        if cfg.harmonic_search_enabled:
            for n in range(2, cfg.harmonic_search_max_sub + 1):
                T = current_duration / n
                if T >= cfg.min_loop_duration:
                    candidates.append(T)
            # n*T for n=2,3
            for n in range(2, cfg.harmonic_search_max_super + 1):
                T = current_duration * n
                if cfg.min_loop_duration <= T <= cfg.max_loop_duration:
                    candidates.append(T)

        # Method 3: Autocorrelation period detection
        if cfg.autocorrelation_enabled:
            periods = self._detect_periods_autocorrelation(resampled, sample_rate)
        else:
            periods = self._detect_periods(resampled, sample_rate)

        for period in periods:
            for n in range(1, 30):
                T = n * period
                if cfg.min_loop_duration <= T <= cfg.max_loop_duration:
                    candidates.append(T)

        # Method 4: Fine-grained search around current duration
        search_lo = max(cfg.min_loop_duration, current_duration * 0.25)
        search_hi = min(test_duration, cfg.max_loop_duration)
        T = search_lo
        while T <= search_hi:
            candidates.append(T)
            T += cfg.duration_search_step

        # Snap to tick boundaries if enabled
        if cfg.snap_to_ticks:
            snapped_candidates = set()
            for T in candidates:
                snapped = self._snap_to_tick(T)
                if cfg.min_loop_duration <= snapped <= cfg.max_loop_duration:
                    snapped_candidates.add(snapped)
            candidates = sorted(snapped_candidates)
        else:
            candidates = sorted(set(candidates))

        diagnostics['candidates_tested'] = len(candidates)

        for T in candidates:
            c0, c1, comb = self._evaluate_continuity_combined(
                resampled, T, sample_rate
            )

            if c0 < cfg.early_exit_c0_rot and c1 < cfg.early_exit_c1_rot:
                diagnostics['method'] = 'search_early_exit_good_enough'
                diagnostics['best_c0_error'] = c0
                diagnostics['best_c1_error'] = c1
                diagnostics['best_combined_phase_error'] = comb
                return round(T, 4), diagnostics

            # v5: Weighted score uses combined phase error (across all channels)
            # v5.1: Also include minimum-jerk penalty for smoother loop transitions
            jerk = self._compute_loop_jerk(resampled, T, sample_rate)
            score = c0 * 10 + c1 + comb * 0.5 + jerk * 0.01

            if score < best_score:
                best_score = score
                best_duration = T
                best_combined = comb
                diagnostics['best_c0_error'] = c0
                diagnostics['best_c1_error'] = c1
                diagnostics['best_combined_phase_error'] = comb

        # Fallback: use the best found
        if diagnostics['best_c0_error'] <= c0_err * 1.1:
            diagnostics['method'] = 'search_optimal'
            return round(best_duration, 4), diagnostics
        else:
            if diagnostics['best_c1_error'] < c1_err * 0.5:
                diagnostics['method'] = 'search_optimal_c1_priority'
                return round(best_duration, 4), diagnostics
            diagnostics['method'] = 'current_best'
            if cfg.snap_to_ticks:
                current_duration = self._snap_to_tick(current_duration)
            return current_duration, diagnostics

    def _snap_to_tick(self, duration: float) -> float:
        """Snap a duration to the nearest tick boundary (0.05s)."""
        cfg = self.config
        return round(round(duration / cfg.tick_duration) * cfg.tick_duration, 4)

    def _compute_duration_from_keyframes(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]]
    ) -> float:
        """Compute animation duration from keyframe data when length=0.

        v5.1 improvements:
        - If the animation is truly static (no keyframes at all or all at t=0),
          return 1.0s as a reasonable default for static poses.
        - If keyframes exist, add a small padding (1 tick = 0.05s) after the
          last keyframe to ensure the last keyframe is fully visible.
        """
        max_time = 0.0
        has_any_motion = False
        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if keyframes:
                    max_time = max(max_time, keyframes[-1][0])
                    if keyframes[-1][0] > 0:
                        has_any_motion = True

        if max_time <= 0:
            # Truly static — no temporal extent
            return 1.0

        # Add 1 tick padding after last keyframe to ensure it's fully visible
        padded = max_time + TICK_DURATION

        return padded

    def _evaluate_continuity(
        self,
        resampled: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        sample_rate: float
    ) -> Tuple[float, float]:
        """Evaluate C0 and C1 continuity at a candidate duration."""
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

    def _evaluate_continuity_combined(
        self,
        resampled: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        sample_rate: float
    ) -> Tuple[float, float, float]:
        """v5: Evaluate C0 and C1 continuity with combined phase error.

        Returns:
            (c0_error_avg, c1_error_avg, combined_phase_error)
            combined_phase_error = sum of |val(T)-val(0)| + |vel(T)-vel(0)| across ALL channels
        """
        total_c0 = 0.0
        total_c1 = 0.0
        combined_phase = 0.0
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
                combined_phase += c0_err + c1_err
                count += 1

        if count == 0:
            return 0.0, 0.0, 0.0

        return total_c0 / count, total_c1 / count, combined_phase

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
        """Detect dominant oscillation periods using autocorrelation."""
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

                fft_x = np.fft.rfft(centered, n=2 * n)
                autocorr_full = np.fft.irfft(fft_x * np.conj(fft_x))[:n]

                if autocorr_full[0] < 1e-12:
                    continue
                autocorr_full = autocorr_full / autocorr_full[0]

                max_lag = min(n // 2, int(20.0 * sample_rate))

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

    def _check_phase_coherence(
        self,
        resampled: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        sample_rate: float
    ) -> bool:
        """v5.1: Check if ALL channels have values at T close to values at 0.

        Phase coherence means every individual channel has good C0 match,
        not just the average. A single bad channel can cause visible pops
        even if the average looks good.

        Returns:
            True if all channels are phase-coherent at the given duration.
        """
        cfg = self.config
        dt = 1.0 / sample_rate

        for bone_name, channels in resampled.items():
            for channel, data in channels.items():
                if len(data) < 4:
                    continue

                val_0 = self._interpolate(data, 0.0)
                val_T = self._interpolate(data, duration)

                c0_err = abs(val_T - val_0)

                # Each channel must individually meet the C0 threshold
                if channel.startswith('r') or channel in ('x', 'y', 'z'):
                    if c0_err > cfg.loop_position_tolerance_rot * 2.0:
                        return False
                else:
                    if c0_err > cfg.loop_position_tolerance_pos * 2.0:
                        return False

        return True

    def _compute_loop_jerk(
        self,
        resampled: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        sample_rate: float
    ) -> float:
        """v5.1: Compute total jerk (derivative of acceleration) at the loop point.

        Minimizing jerk at the loop boundary produces smoother transitions.
        Jerk is estimated as the second finite difference of velocity at
        the loop boundary.

        Returns:
            Total jerk magnitude across all channels at the loop boundary.
        """
        dt = 1.0 / sample_rate
        total_jerk = 0.0

        for bone_name, channels in resampled.items():
            for channel, data in channels.items():
                if len(data) < 6:
                    continue

                # Velocity at start: finite difference
                v0_start = (self._interpolate(data, dt) - self._interpolate(data, 0.0)) / dt
                v0_end = (self._interpolate(data, 0.0) - self._interpolate(data, duration - dt)) / dt

                # Velocity at end
                vT_start = (self._interpolate(data, duration) - self._interpolate(data, duration - dt)) / dt
                vT_end = vT_start  # can't go beyond duration

                # Acceleration at start and end
                a0 = (v0_start - v0_end) / dt
                aT = (vT_start - v0_start) / dt  # proxy

                # Jerk = change in acceleration at loop boundary
                jerk = abs(aT - a0)
                total_jerk += jerk

        return total_jerk


# ============================================================================
# C1 Continuity Enforcer (v5: Global Cubic Correction + Hybrid)
# ============================================================================

class C1ContinuityEnforcer:
    """Enforces C1 (velocity) continuity at loop boundaries.

    v5 CRITICAL CHANGE: Global Cubic Correction (replaces end-only blend)

    Instead of blending only the end of the animation, the v5 computes a
    correction curve c(t) = a*t^3 + b*t^2 that is ADDED to the entire
    animation signal. This correction:

    - c(0) = 0, c'(0) = 0           (start is UNCHANGED)
    - c(T) = -delta_p, c'(T) = -delta_v  (end matches start in C0+C1)

    The coefficients are:
    - delta_p = p(T) - p(0)   (position gap at loop boundary)
    - delta_v = v(T) - v(0)   (velocity gap at loop boundary)
    - a = (2*delta_p - delta_v*T) / T^3
    - b = (-3*delta_p + delta_v*T) / T^2

    HYBRID APPROACH:
    - Primary: Global Cubic Correction for ALL channels (guaranteed C0+C1)
    - Fallback: For channels where global correction would cause >15%
      distortion (max|c(t)| / amplitude > 0.15), use local end-blend
      with velocity transition bridge (from v4)
    - Special: For near-static channels, just snap last keyframe to first

    BOUNCE CASES: When v0*vT < 0, the symmetric velocity blending approach
    is used (v5.1). Instead of the global cubic correction (which creates
    S-shaped distortion for bounce cases), a TWO-PHASE approach is applied:
    - Phase 1 (first half): smooth start velocity to zero at midpoint
    - Phase 2 (second half): smooth from zero to match start velocity at end
    This eliminates the velocity reversal that causes bounce-back artifacts.
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()

    @staticmethod
    def _quintic_hermite(s: float, p0: float, v0: float, a0: float,
                          p1: float, v1: float, a1: float,
                          dt: float) -> float:
        """Evaluate quintic Hermite interpolation (for fallback bridge)."""
        s2 = s * s
        s3 = s2 * s
        s4 = s3 * s
        s5 = s4 * s

        h0 = 1 - 10*s3 + 15*s4 - 6*s5
        h1 = s - 6*s3 + 8*s4 - 3*s5
        h2 = 0.5*s2 - 1.5*s3 + 1.5*s4 - 0.5*s5
        h3 = 0.5*s3 - s4 + 0.5*s5
        h4 = -4*s3 + 7*s4 - 3*s5
        h5 = 10*s3 - 15*s4 + 6*s5

        return (h0 * p0 +
                h1 * dt * v0 +
                h2 * dt * dt * a0 +
                h3 * dt * dt * a1 +
                h4 * dt * v1 +
                h5 * p1)

    def _is_bounce_case(self, v_start: float, v_end: float) -> bool:
        """Check if velocities have opposite signs (bounce case)."""
        threshold_sq = self.config.bounce_detection_threshold ** 2
        return v_start * v_end < -threshold_sq

    def _compute_global_cubic_coefficients(
        self, delta_p: float, delta_v: float, T: float
    ) -> Tuple[float, float]:
        """Compute coefficients for the global cubic correction curve.

        c(t) = a*t^3 + b*t^2
        with boundary conditions:
          c(0) = 0, c'(0) = 0  (start unchanged)
          c(T) = -delta_p, c'(T) = -delta_v  (end matches start)

        Returns:
            (a, b) coefficients
        """
        T2 = T * T
        T3 = T2 * T

        # c(T)  = a*T^3 + b*T^2 = -delta_p
        # c'(T) = 3*a*T^2 + 2*b*T = -delta_v
        #
        # Solving:
        # a*T^3 + b*T^2 = -delta_p       ... (1)
        # 3*a*T^2 + 2*b*T = -delta_v     ... (2)
        #
        # From (2): b = (-delta_v - 3*a*T^2) / (2*T)
        # Substitute into (1):
        # a*T^3 + T^2 * (-delta_v - 3*a*T^2) / (2*T) = -delta_p
        # a*T^3 + T*(-delta_v - 3*a*T^2)/2 = -delta_p
        # a*T^3 - delta_v*T/2 - 3*a*T^3/2 = -delta_p
        # a*(T^3 - 3*T^3/2) - delta_v*T/2 = -delta_p
        # a*(-T^3/2) - delta_v*T/2 = -delta_p
        # a*(-T^3/2) = -delta_p + delta_v*T/2
        # a = (2*delta_p - delta_v*T) / T^3

        a = (2.0 * delta_p - delta_v * T) / T3
        b = (-3.0 * delta_p + delta_v * T) / T2

        return a, b

    def _evaluate_correction(self, t: float, a: float, b: float) -> float:
        """Evaluate the global cubic correction c(t) = a*t^3 + b*t^2."""
        return a * t * t * t + b * t * t

    def _evaluate_correction_derivative(self, t: float, a: float, b: float) -> float:
        """Evaluate c'(t) = 3*a*t^2 + 2*b*t."""
        return 3.0 * a * t * t + 2.0 * b * t

    def _compute_correction_magnitude(
        self, a: float, b: float, T: float, n_points: int = 200
    ) -> float:
        """Compute max(|c(t)|) over [0, T] for distortion check.

        Uses dense sampling to find the maximum.
        """
        max_val = 0.0
        for i in range(n_points + 1):
            t = T * i / n_points
            c = abs(self._evaluate_correction(t, a, b))
            if c > max_val:
                max_val = c
        return max_val

    def _compute_channel_amplitude(
        self, resampled: List[Tuple[float, float]]
    ) -> float:
        """Compute the amplitude of a channel: max(|v - mean|)."""
        if len(resampled) < 2:
            return 0.0
        values = [v for t, v in resampled]
        mean_val = sum(values) / len(values)
        return max(abs(v - mean_val) for v in values)

    def _is_near_static_channel(
        self, resampled: List[Tuple[float, float]], is_rotation: bool
    ) -> bool:
        """Check if a channel has near-zero motion (static)."""
        cfg = self.config
        if len(resampled) < 2:
            return True
        values = [v for t, v in resampled]
        max_deviation = max(abs(v - values[0]) for v in values)
        threshold = (cfg.static_channel_motion_threshold_rot if is_rotation
                     else cfg.static_channel_motion_threshold_pos)
        return max_deviation < threshold

    def _compute_adaptive_blend_window(
        self, duration: float, c1_diff: float, c1_threshold: float,
        resample_dt: float
    ) -> float:
        """v5: Compute per-channel adaptive blend window.

        - Base window: duration * blend_window_ratio
        - Adaptive scale: 1.0 + (c1_diff / c1_threshold)
        - Minimum: 10 resampled points
        - Maximum: 40% of duration
        """
        cfg = self.config
        base_w = duration * cfg.blend_window_ratio
        adaptive_scale = 1.0 + min(c1_diff / max(c1_threshold, 1e-6), 3.0)
        w = base_w * adaptive_scale

        # Minimum: 10 resampled points
        min_w = cfg.adaptive_blend_min_points * resample_dt
        w = max(w, min_w)

        # Maximum: 40% of duration
        max_w = duration * cfg.adaptive_blend_max_ratio
        w = min(w, max_w)

        return w

    def _apply_local_blend(
        self,
        resampled: List[Tuple[float, float]],
        duration: float,
        blend_window: float,
        p0: float, v0: float,
        v_start_blend: float, p_start_blend: float,
        t_start_blend: float,
        is_bounce: bool,
        bounce_severity: float
    ) -> List[Tuple[float, float]]:
        """Apply local end-blend (v4 approach) as fallback.

        Returns modified resampled data.
        """
        result = list(resampled)
        w_actual = duration - t_start_blend

        if w_actual < 1e-12:
            return result

        # Find start index of blend window
        blend_start_idx = 0
        for i, (t, v) in enumerate(result):
            if t >= t_start_blend:
                blend_start_idx = i
                break

        if blend_start_idx < 1 or blend_start_idx >= len(result) - 1:
            return result

        p_end_target = p0  # C0 target
        v_end_target = v0  # C1 target

        if is_bounce and bounce_severity > 0.1:
            # Velocity transition bridge (v4)
            v_abs_start = abs(v_start_blend)
            v_abs_end = abs(v_end_target)
            v_total = v_abs_start + v_abs_end

            d_to_end = abs(p_end_target - p_start_blend)
            if v_total > 1e-6:
                start_weight = v_abs_start / v_total
                p_mid = p_start_blend + d_to_end * (0.5 + 0.1 * (start_weight - 0.5))
            else:
                p_mid = p_start_blend + d_to_end * 0.5

            w_phase1 = w_actual / 2.0
            w_phase2 = w_actual / 2.0
            mid_time = t_start_blend + w_phase1

            for i in range(blend_start_idx, len(result)):
                t, v = result[i]

                if t <= mid_time + 1e-10:
                    if w_phase1 > 1e-12:
                        s = (t - t_start_blend) / w_phase1
                        s = max(0.0, min(1.0, s))
                    else:
                        s = 1.0
                    new_val = self._quintic_hermite(
                        s, p_start_blend, v_start_blend, 0.0,
                        p_mid, 0.0, 0.0, w_phase1
                    )
                else:
                    if w_phase2 > 1e-12:
                        s = (t - mid_time) / w_phase2
                        s = max(0.0, min(1.0, s))
                    else:
                        s = 1.0
                    new_val = self._quintic_hermite(
                        s, p_mid, 0.0, 0.0,
                        p_end_target, v_end_target, 0.0, w_phase2
                    )
                result[i] = (t, new_val)
        else:
            # Cubic Hermite blend (non-bounce)
            for i in range(blend_start_idx, len(result)):
                t, v = result[i]
                s = (t - t_start_blend) / w_actual
                s = max(0.0, min(1.0, s))

                s2 = s * s
                s3 = s2 * s

                h00 = 2 * s3 - 3 * s2 + 1
                h10 = s3 - 2 * s2 + s
                h01 = -2 * s3 + 3 * s2
                h11 = s3 - s2

                new_val = (h00 * p_start_blend +
                           h10 * w_actual * v_start_blend +
                           h01 * p_end_target +
                           h11 * w_actual * v_end_target)
                result[i] = (t, new_val)

        return result

    def _apply_symmetric_velocity_blend(
        self,
        resampled: List[Tuple[float, float]],
        duration: float,
        p0: float,
        v0: float,
        vT: float,
        is_rotation: bool,
        resample_dt: float
    ) -> List[Tuple[float, float]]:
        """v5.1: Apply symmetric velocity blending for bounce cases.

        When v0*vT < 0, the global cubic correction creates S-shaped
        distortion. This method instead uses a TWO-PHASE approach:

        Phase 1 (first half): Smooth the start velocity to zero at the
            midpoint using a quintic Hermite blend.
        Phase 2 (second half): Smooth from zero at the midpoint to
            match the start velocity (v0) at the end, ensuring the
            final position equals p0 (C0 continuity).

        The key insight: when v0*vT < 0, GeckoLib's catmullrom interpolation
        at the loop point "sees" opposite velocities and creates a jerk. By
        making the velocity go through zero in the middle and matching at
        the end, we get smooth loops without the bounce-back artifact.

        Args:
            resampled: Resampled channel data [(t, v), ...]
            duration: Animation duration T
            p0: Value at start (target for C0 match at end)
            v0: Velocity at start (target for C1 match at end)
            vT: Velocity at end (before correction)
            is_rotation: Whether this is a rotation channel
            resample_dt: Time step between resampled points

        Returns:
            Modified resampled data with symmetric velocity blending applied.
        """
        result = list(resampled)
        n = len(result)
        if n < 5 or duration < 1e-12:
            return result

        T = duration
        T_half = T / 2.0

        # Find the midpoint index
        mid_idx = 0
        for i, (t, v) in enumerate(result):
            if t >= T_half:
                mid_idx = i
                break

        if mid_idx < 1 or mid_idx >= n - 1:
            return result

        # Get values at the midpoint
        p_mid_actual = result[mid_idx][1]

        # Compute the midpoint value needed for C0 continuity.
        # Phase 2 goes from p_mid with velocity=0 to p0 with velocity=v0.
        # We need p_mid such that the quintic Hermite from (p_mid, 0) to
        # (p0, v0) produces a smooth transition. For exact C0, the endpoint
        # is p0 by construction.
        #
        # For Phase 1: we blend from (p0, v0) at t=0 to (p_mid, 0) at t=T_half.
        # For Phase 2: we blend from (p_mid, 0) at t=T_half to (p0, v0) at t=T.
        #
        # The p_mid value is chosen to be the actual midpoint value to minimize
        # distortion, but we adjust it slightly if needed for C0.

        # Use the actual midpoint value as-is for minimal distortion
        p_mid = p_mid_actual

        # Phase 1: [0, T_half] — blend from (p0, v0) to (p_mid, v=0)
        # Phase 2: [T_half, T] — blend from (p_mid, v=0) to (p0, v0)
        w_phase1 = T_half
        w_phase2 = T_half

        for i in range(n):
            t, v = result[i]

            if t <= T_half + 1e-10:
                # Phase 1: smooth from start to midpoint with velocity -> 0
                if w_phase1 > 1e-12:
                    s = t / w_phase1
                    s = max(0.0, min(1.0, s))
                else:
                    s = 1.0

                # Quintic Hermite: position and velocity interpolation
                # Start: (p0, v0, accel=0), End: (p_mid, v=0, accel=0)
                new_val = self._quintic_hermite(
                    s, p0, v0, 0.0,
                    p_mid, 0.0, 0.0, w_phase1
                )
                result[i] = (t, new_val)
            else:
                # Phase 2: smooth from midpoint to end with velocity 0 -> v0
                if w_phase2 > 1e-12:
                    s = (t - T_half) / w_phase2
                    s = max(0.0, min(1.0, s))
                else:
                    s = 1.0

                # Quintic Hermite: (p_mid, v=0, accel=0) -> (p0, v0, accel=0)
                new_val = self._quintic_hermite(
                    s, p_mid, 0.0, 0.0,
                    p0, v0, 0.0, w_phase2
                )
                result[i] = (t, new_val)

        # Ensure exact C0 match at the boundary (last point = p0)
        if result:
            result[-1] = (result[-1][0], p0)

        return result

    def enforce(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        interpolation: str = "catmullrom",
        cached_resampled: Optional[Dict[str, Dict[str, List[Tuple[float, float]]]]] = None
    ) -> Tuple[Dict[str, Dict[str, List[Tuple[float, float]]]],
               Dict[str, Any]]:
        """Apply hybrid C1 continuity enforcement.

        Primary: Global Cubic Correction (distributed across entire animation)
        Fallback: Symmetric Velocity Blend for bounce cases (v5.1)
        Fallback: Local end-blend for high-distortion non-bounce cases
        Special: Static snap (for near-zero motion channels)

        Args:
            bone_channels: {bone: {channel: [(t, v), ...]}}
            duration: Animation duration
            interpolation: Interpolation type for resampling
            cached_resampled: Pre-computed resampled data

        Returns:
            (modified_bone_channels, blend_diagnostics)
        """
        cfg = self.config
        blend_diag = {
            'global_cubic_count': 0,
            'local_blend_count': 0,
            'static_snap_count': 0,
            'bridge_used_count': 0,
            'max_bounce_severity': 0.0,
            'bridge_details': [],
            'correction_magnitudes': [],   # v5: per-channel correction ratios
            'fidelity_scores': [],         # v5: per-channel fidelity scores
        }

        if not cfg.enable_c1_enforcement:
            return bone_channels, blend_diag

        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if len(keyframes) < 2:
                    continue

                is_rotation = channel in ('rx', 'ry', 'rz', 'x', 'y', 'z')

                # Step 1: Resample at high rate
                n_resample = max(int(duration * cfg.resample_rate), 60)
                resample_dt = duration / n_resample
                resample_times = [i * resample_dt for i in range(n_resample + 1)]

                if cached_resampled and bone_name in cached_resampled and channel in cached_resampled[bone_name]:
                    resampled = cached_resampled[bone_name][channel]
                    if len(resampled) >= n_resample:
                        resampled = resampled[:n_resample + 1]
                    else:
                        resampled = CatmullRomEvaluator.resample_channel(
                            keyframes, resample_times, interpolation
                        )
                else:
                    resampled = CatmullRomEvaluator.resample_channel(
                        keyframes, resample_times, interpolation
                    )

                if len(resampled) < 5:
                    continue

                # Step 2: Compute boundary values and velocities
                p0 = resampled[0][1]
                pT = resampled[-1][1]

                v0 = (-3*resampled[0][1] + 4*resampled[1][1] - resampled[2][1]) / (2*resample_dt)
                vT = (3*resampled[-1][1] - 4*resampled[-2][1] + resampled[-3][1]) / (2*resample_dt)

                # Check if enforcement is needed
                c0_thresh = cfg.c0_snap_threshold_rot if is_rotation else cfg.c0_snap_threshold_pos
                c1_thresh = cfg.velocity_match_threshold_rot if is_rotation else cfg.velocity_match_threshold_pos

                c0_diff = abs(p0 - pT)
                c1_diff = abs(v0 - vT)

                if c0_diff < c0_thresh and c1_diff < c1_thresh:
                    blend_diag['static_snap_count'] += 1
                    if c0_diff > 1e-8:
                        channels[channel] = [
                            (t, v) if i < len(keyframes) - 1 else (t, keyframes[0][1])
                            for i, (t, v) in enumerate(keyframes)
                        ]
                    blend_diag['correction_magnitudes'].append(0.0)
                    blend_diag['fidelity_scores'].append(1.0)
                    continue

                # Compute bounce severity
                avg_vel = (abs(vT) + abs(v0)) / 2.0
                bounce_severity = 0.0
                if avg_vel > 1e-6 and v0 * vT < 0:
                    bounce_severity = abs(v0 + vT) / avg_vel

                if bounce_severity > blend_diag['max_bounce_severity']:
                    blend_diag['max_bounce_severity'] = bounce_severity

                # ============================================================
                # Step 3: Check if near-static channel
                # ============================================================
                if self._is_near_static_channel(resampled, is_rotation):
                    # Static channel: just snap last keyframe to first
                    blend_diag['static_snap_count'] += 1
                    channels[channel] = [
                        (t, v) if i < len(keyframes) - 1 else (t, keyframes[0][1])
                        for i, (t, v) in enumerate(keyframes)
                    ]
                    blend_diag['correction_magnitudes'].append(0.0)
                    blend_diag['fidelity_scores'].append(1.0)
                    continue

                # ============================================================
                # Step 4: Try Global Cubic Correction
                # ============================================================
                delta_p = pT - p0    # position gap
                delta_v = vT - v0    # velocity gap

                T = duration
                if T < 1e-12:
                    continue

                a_coeff, b_coeff = self._compute_global_cubic_coefficients(delta_p, delta_v, T)

                # Compute correction magnitude
                max_correction = self._compute_correction_magnitude(a_coeff, b_coeff, T)
                amplitude = self._compute_channel_amplitude(resampled)

                correction_ratio = max_correction / max(amplitude, 1e-6)

                # Check distortion threshold
                is_bounce = self._is_bounce_case(v0, vT)

                if correction_ratio <= cfg.global_cubic_distortion_limit:
                    # ====================================================
                    # GLOBAL CUBIC CORRECTION (v5 primary method)
                    # ====================================================
                    blend_diag['global_cubic_count'] += 1

                    # Apply correction to each resampled point
                    corrected = []
                    for t, v in resampled:
                        c_t = self._evaluate_correction(t, a_coeff, b_coeff)
                        corrected.append((t, v + c_t))

                    # Rebuild keyframes from corrected resampled data
                    new_keyframes = self._rebuild_keyframes_from_resampled(
                        keyframes, corrected, duration, p0
                    )

                    channels[channel] = new_keyframes
                    blend_diag['correction_magnitudes'].append(correction_ratio)
                    blend_diag['fidelity_scores'].append(1.0 - correction_ratio)

                elif is_bounce:
                    # ====================================================
                    # SYMMETRIC VELOCITY BLEND (v5.1: bounce case)
                    # ====================================================
                    # When v0*vT < 0, the global cubic creates S-shaped
                    # distortion. Instead, use a two-phase approach that
                    # brings velocity to zero at the midpoint, then from
                    # zero to match the start velocity at the end.
                    # ====================================================
                    blend_diag['local_blend_count'] += 1
                    blend_diag['bridge_used_count'] += 1

                    corrected = self._apply_symmetric_velocity_blend(
                        resampled, duration, p0, v0, vT,
                        is_rotation, resample_dt
                    )

                    new_keyframes = self._rebuild_keyframes_from_resampled(
                        keyframes, corrected, duration, p0
                    )
                    channels[channel] = new_keyframes

                    blend_diag['correction_magnitudes'].append(correction_ratio)
                    blend_diag['fidelity_scores'].append(max(0.0, 1.0 - correction_ratio))

                    blend_diag['bridge_details'].append({
                        'bone': bone_name,
                        'channel': channel,
                        'severity': bounce_severity,
                        'method': 'symmetric_velocity_blend',
                    })

                else:
                    # ====================================================
                    # LOCAL BLEND (fallback: distortion too high, non-bounce)
                    # ====================================================
                    blend_diag['local_blend_count'] += 1

                    w = self._compute_adaptive_blend_window(
                        duration, c1_diff, c1_thresh, resample_dt
                    )

                    blend_start_time = max(0, duration - w)

                    blend_start_idx = 0
                    for i, (t, v) in enumerate(resampled):
                        if t >= blend_start_time:
                            blend_start_idx = i
                            break

                    if blend_start_idx >= 1 and blend_start_idx < len(resampled) - 1:
                        p_start_blend = resampled[blend_start_idx][1]
                        t_start_blend = resampled[blend_start_idx][0]

                        v_start_blend = (
                            (resampled[blend_start_idx + 1][1] -
                             resampled[blend_start_idx - 1][1]) /
                            (resampled[blend_start_idx + 1][0] -
                             resampled[blend_start_idx - 1][0])
                        )

                        corrected = self._apply_local_blend(
                            resampled, duration, w,
                            p0, v0,
                            v_start_blend, p_start_blend, t_start_blend,
                            False, 0.0
                        )

                        new_keyframes = self._rebuild_keyframes_from_resampled(
                            keyframes, corrected, duration, p0
                        )
                        channels[channel] = new_keyframes

                    blend_diag['correction_magnitudes'].append(correction_ratio)
                    blend_diag['fidelity_scores'].append(max(0.0, 1.0 - correction_ratio))

        return bone_channels, blend_diag

    def _rebuild_keyframes_from_resampled(
        self,
        original_keyframes: List[Tuple[float, float]],
        corrected_resampled: List[Tuple[float, float]],
        duration: float,
        p0: float
    ) -> List[Tuple[float, float]]:
        """Rebuild keyframes from corrected resampled data.

        Strategy:
        - Keep original keyframes that are before the corrected region
        - In the corrected region, sample at a reasonable density
        - Ensure last keyframe is exactly at duration with value = p0
        """
        if not corrected_resampled:
            return original_keyframes

        # For global cubic correction, the ENTIRE signal is modified,
        # so we need to rebuild all keyframes from the corrected data.
        # Strategy: use the original keyframe times but with corrected values.

        new_keyframes = []

        # For each original keyframe time, find the corrected value
        for t_orig, v_orig in original_keyframes:
            # Find closest resampled point or interpolate
            corrected_val = self._interpolate_resampled(corrected_resampled, t_orig)
            new_keyframes.append((t_orig, corrected_val))

        # Ensure last keyframe is exactly at duration with value = p0
        if new_keyframes:
            new_keyframes[-1] = (duration, p0)
        else:
            new_keyframes.append((0.0, p0))
            new_keyframes.append((duration, p0))

        # Sort by time
        new_keyframes.sort(key=lambda x: x[0])

        # Remove near-duplicate times (within 1ms)
        deduped = []
        for t, v in new_keyframes:
            if deduped and abs(t - deduped[-1][0]) < 0.001:
                deduped[-1] = (t, v)
            else:
                deduped.append((t, v))

        return deduped

    @staticmethod
    def _interpolate_resampled(
        resampled: List[Tuple[float, float]], t: float
    ) -> float:
        """Linearly interpolate a value from resampled data at time t."""
        if not resampled:
            return 0.0
        if t <= resampled[0][0]:
            return resampled[0][1]
        if t >= resampled[-1][0]:
            return resampled[-1][1]

        lo, hi = 0, len(resampled) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if resampled[mid][0] <= t:
                lo = mid
            else:
                hi = mid

        t0, v0 = resampled[lo]
        t1, v1 = resampled[hi]
        dt = t1 - t0
        if dt < 1e-12:
            return v0
        alpha = (t - t0) / dt
        return v0 + alpha * (v1 - v0)


# ============================================================================
# Douglas-Peucker Simplifier (same as v3/v4 — proven correct)
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
# Animation Name Normalizer (same as v3/v4 — proven correct)
# ============================================================================

class AnimationNameNormalizer:
    """Normalizes animation names to follow GeckoLib convention."""

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

    @staticmethod
    def normalize_for_dedup(name: str) -> str:
        """v5: Normalize a name for semantic deduplication comparison.

        Strips namespace and entity parts, keeps only the state,
        lowercased and underscore-normalized.
        """
        if not name:
            return ""
        state = name.strip()
        for prefix in AnimationNameNormalizer.REDUNDANT_PREFIXES:
            if state.lower().startswith(prefix):
                state = state[len(prefix):]
                break
        parts = state.split('.')
        if len(parts) >= 1:
            state = parts[-1]
        state = re.sub(r'[\s\-]+', '_', state.lower())
        state = re.sub(r'[^a-z0-9_]', '', state)
        return state


# ============================================================================
# BBModel Animation Extractor (v5: enhanced empty/consolidation)
# ============================================================================

class BBModelAnimationExtractor:
    """Extracts animations from .bbmodel files and converts to internal format.

    v5 Improvements:
    - Truly Empty Detection: all rotation < 0.01 deg, position < 0.001 px
    - Near-Empty Detection: values near-zero but with keyframes → mark static
    - Semantic Deduplication: same name after normalization = duplicate
    - Cross-Animation Bone Consolidation: union of bone channels when merging
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
                'static_preserved': List[str],
                'near_empty': List[str],           # v5 NEW
                'merge_info': List[Dict],
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

            # v5: Classify animation emptiness
            emptiness = self._classify_emptiness(bone_channels)

            raw_animations[anim_name] = {
                'loop': anim.get('loop', 'hold_on_last_frame'),
                'length': anim.get('length', 0.0),
                'snapping': anim.get('snapping', 24),
                'bone_channels': bone_channels,
                'interpolation': dominant_interp,
                'is_empty': emptiness == 'truly_empty',
                'is_near_empty': emptiness == 'near_empty',
                'emptiness': emptiness,
            }

        # Post-processing: deduplication and empty handling
        animations = {}
        skipped_empty = []
        deduplicated = []
        static_preserved = []
        near_empty_list = []
        merge_info = []

        # v5 Step 1: Semantic deduplication (by normalized name)
        if self.config.semantic_dedup_enabled:
            semantic_groups = defaultdict(list)
            for anim_name, anim_data in raw_animations.items():
                norm_name = AnimationNameNormalizer.normalize_for_dedup(anim_name)
                semantic_groups[norm_name].append((anim_name, anim_data))

            for norm_name, group in semantic_groups.items():
                if len(group) == 1:
                    anim_name, anim_data = group[0]
                    animations[anim_name] = anim_data
                else:
                    # Multiple animations with same semantic name
                    # v5.1: Before merging, check bone overlap.
                    # If animations have completely different bones (< 50% overlap),
                    # keep them both — they're different animations that just happen
                    # to have the same normalized name.
                    primary_name, primary_data = group[0]
                    primary_bones = set(primary_data['bone_channels'].keys())

                    to_merge = []
                    to_keep_separate = []

                    for alt_name, alt_data in group[1:]:
                        alt_bones = set(alt_data['bone_channels'].keys())

                        if not primary_bones and not alt_bones:
                            # Both empty — merge (doesn't matter)
                            to_merge.append((alt_name, alt_data))
                            continue

                        if not primary_bones or not alt_bones:
                            # One is empty, other is not — keep both
                            to_keep_separate.append((alt_name, alt_data))
                            continue

                        # Compute bone overlap ratio
                        overlap = primary_bones & alt_bones
                        union = primary_bones | alt_bones
                        overlap_ratio = len(overlap) / len(union) if union else 0.0

                        if overlap_ratio >= 0.5:
                            # >50% bone overlap — these are likely variants,
                            # merge them (union of bone channels)
                            to_merge.append((alt_name, alt_data))
                        else:
                            # <50% overlap — completely different animations
                            # that just share a name. Keep both.
                            to_keep_separate.append((alt_name, alt_data))

                    # Sort primary group by most data
                    group_with_primary = [(primary_name, primary_data)] + to_merge
                    group_with_primary.sort(key=lambda x: sum(
                        len(kfs) for chs in x[1]['bone_channels'].values()
                        for kfs in chs.values()
                    ), reverse=True)

                    primary_name, primary_data = group_with_primary[0]
                    merged_channels = dict(primary_data['bone_channels'])

                    for alt_name, alt_data in group_with_primary[1:]:
                        alt_channels = alt_data['bone_channels']
                        merged_channels, merge_actions = self._union_bone_channels(
                            merged_channels, alt_channels, primary_name, alt_name
                        )
                        merge_info.extend(merge_actions)
                        deduplicated.append(alt_name)

                    primary_data['bone_channels'] = merged_channels
                    emptiness = self._classify_emptiness(merged_channels)
                    primary_data['is_empty'] = emptiness == 'truly_empty'
                    primary_data['is_near_empty'] = emptiness == 'near_empty'
                    primary_data['emptiness'] = emptiness
                    animations[primary_name] = primary_data

                    # Keep separate animations with different bones
                    for alt_name, alt_data in to_keep_separate:
                        animations[alt_name] = alt_data
        elif self.config.deduplicate_case_insensitive:
            # Case-insensitive deduplication with UNION bone-channel merging
            seen_lower = {}
            for anim_name, anim_data in raw_animations.items():
                lower_name = anim_name.lower()
                if lower_name in seen_lower:
                    canonical = seen_lower[lower_name]
                    if self.config.smart_bone_merge:
                        merged_channels = dict(animations[canonical]['bone_channels'])
                        new_channels = anim_data['bone_channels']
                        merged_channels, merge_actions = self._union_bone_channels(
                            merged_channels, new_channels, canonical, anim_name
                        )
                        merge_info.extend(merge_actions)
                        animations[canonical]['bone_channels'] = merged_channels
                        emptiness = self._classify_emptiness(merged_channels)
                        animations[canonical]['is_empty'] = emptiness == 'truly_empty'
                        animations[canonical]['is_near_empty'] = emptiness == 'near_empty'
                        animations[canonical]['emptiness'] = emptiness
                    else:
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

        # Content-hash dedup (SHA-256 based)
        if self.config.content_hash_dedup and self.config.merge_duplicate_animations:
            data_hashes = {}
            final_animations = {}
            for anim_name, anim_data in animations.items():
                content_hash = self._compute_content_hash(anim_data)
                if content_hash in data_hashes:
                    existing_name = data_hashes[content_hash]
                    existing_bones = set(animations[existing_name]['bone_channels'].keys())
                    new_bones = set(anim_data['bone_channels'].keys())

                    if new_bones - existing_bones or existing_bones - new_bones:
                        # Different bones — keep both, but consolidate
                        merged_channels = dict(animations[existing_name]['bone_channels'])
                        alt_channels = anim_data['bone_channels']
                        merged_channels, merge_actions = self._union_bone_channels(
                            merged_channels, alt_channels, existing_name, anim_name
                        )
                        merge_info.extend(merge_actions)
                        animations[existing_name]['bone_channels'] = merged_channels
                        data_hashes[content_hash] = anim_name
                        final_animations[anim_name] = anim_data
                    else:
                        # Same bones, same hash — union per-channel
                        if self.config.always_union_bones:
                            merged_channels = dict(animations[existing_name]['bone_channels'])
                            for bone, channels in anim_data['bone_channels'].items():
                                if bone in merged_channels:
                                    merged_bone = dict(merged_channels[bone])
                                    for ch_name, ch_data in channels.items():
                                        if ch_name in merged_bone:
                                            existing_kf = len(merged_bone[ch_name])
                                            new_kf = len(ch_data)
                                            if new_kf > existing_kf:
                                                merged_bone[ch_name] = ch_data
                                        else:
                                            merged_bone[ch_name] = ch_data
                                    merged_channels[bone] = merged_bone
                                else:
                                    merged_channels[bone] = channels
                            animations[existing_name]['bone_channels'] = merged_channels
                            deduplicated.append(anim_name)
                        else:
                            existing_kf = sum(
                                len(kfs) for chs in animations[existing_name]['bone_channels'].values()
                                for kfs in chs.values()
                            )
                            new_kf = sum(
                                len(kfs) for chs in anim_data['bone_channels'].values()
                                for kfs in chs.values()
                            )
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

        # Handle empty animations
        # v5.1: Truly empty animations with NO bone_channels at all should be
        # marked as should_skip=True — they produce empty .animation.json files
        # that serve no purpose. Animations with bone_channels but near-zero
        # values are still preserved as static poses.
        if self.config.preserve_empty_as_static:
            to_remove = []
            for anim_name, anim_data in animations.items():
                if anim_data['is_empty']:
                    # v5.1: If bone_channels is completely empty, skip it entirely
                    if not anim_data.get('bone_channels'):
                        anim_data['should_skip'] = True
                        skipped_empty.append(anim_name)
                        to_remove.append(anim_name)
                        continue

                    anim_data['static'] = True
                    if anim_data['loop'] not in ('loop', 'hold_on_last_frame'):
                        anim_data['loop'] = 'loop'
                    if anim_data['length'] <= 0:
                        max_time = 0.0
                        for bone_channels in anim_data['bone_channels'].values():
                            for channel, keyframes in bone_channels.items():
                                if keyframes:
                                    max_time = max(max_time, keyframes[-1][0])
                        if max_time > 0:
                            # v5.1: Add 1 tick padding after last keyframe
                            anim_data['length'] = max_time + TICK_DURATION
                        else:
                            anim_data['length'] = 1.0
                    static_preserved.append(anim_name)
                elif anim_data.get('is_near_empty', False):
                    # v5: Near-empty animations — mark as static but don't drop
                    anim_data['static'] = True
                    near_empty_list.append(anim_name)

            # Remove truly empty animations that should be skipped
            for anim_name in to_remove:
                del animations[anim_name]
        elif self.config.skip_empty_animations:
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
            'static_preserved': static_preserved,
            'near_empty': near_empty_list,
            'merge_info': merge_info,
        }

    def _classify_emptiness(
        self, bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]]
    ) -> str:
        """v5: Classify animation emptiness level.

        Returns:
            'truly_empty' - all values below strict thresholds
            'near_empty'  - values exist but are very small
            'non_empty'   - meaningful animation data
        """
        if not bone_channels:
            return 'truly_empty'

        cfg = self.config
        has_any_motion = False
        has_near_motion = False

        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if not keyframes:
                    continue
                for t, v in keyframes:
                    if channel.startswith('r') or channel in ('x', 'y', 'z'):
                        # Rotation channel
                        if abs(v) > cfg.truly_empty_rot_threshold:
                            has_near_motion = True
                        if abs(v) > cfg.near_empty_rot_threshold:
                            has_any_motion = True
                    elif channel.startswith('o'):
                        # Position channel
                        if abs(v) > cfg.truly_empty_pos_threshold:
                            has_near_motion = True
                        if abs(v) > cfg.near_empty_pos_threshold:
                            has_any_motion = True
                    elif channel.startswith('s'):
                        # Scale channel
                        if abs(v - 1.0) > cfg.truly_empty_pos_threshold:
                            has_near_motion = True
                        if abs(v - 1.0) > cfg.near_empty_pos_threshold:
                            has_any_motion = True

        if has_any_motion:
            return 'non_empty'
        elif has_near_motion:
            return 'near_empty'
        else:
            return 'truly_empty'

    def _union_bone_channels(
        self,
        primary_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        alt_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        primary_name: str,
        alt_name: str
    ) -> Tuple[Dict[str, Dict[str, List[Tuple[float, float]]]], List[Dict]]:
        """v5: Union bone channels from two animation sources.

        For each bone/channel:
        - If only in one source: add it
        - If in both: keep the one with more keyframes (or larger amplitude if tied)

        Returns:
            (merged_channels, merge_actions)
        """
        merged = dict(primary_channels)
        actions = []

        for bone, channels in alt_channels.items():
            if bone not in merged:
                # New bone — always add
                merged[bone] = channels
                actions.append({
                    'animation': primary_name,
                    'bone': bone,
                    'action': 'added_from_duplicate',
                    'source': alt_name,
                })
            else:
                # Bone exists in both — merge per-channel
                merged_bone = dict(merged[bone])
                for ch_name, ch_data in channels.items():
                    if ch_name not in merged_bone:
                        merged_bone[ch_name] = ch_data
                        actions.append({
                            'animation': primary_name,
                            'bone': bone,
                            'channel': ch_name,
                            'action': 'channel_added_from_duplicate',
                            'source': alt_name,
                        })
                    else:
                        # Same channel — pick the one with MORE keyframes
                        existing_kf = len(merged_bone[ch_name])
                        new_kf = len(ch_data)
                        if new_kf > existing_kf:
                            merged_bone[ch_name] = ch_data
                            actions.append({
                                'animation': primary_name,
                                'bone': bone,
                                'channel': ch_name,
                                'action': 'channel_replaced_more_keyframes',
                                'source': alt_name,
                            })
                        elif new_kf == existing_kf and existing_kf > 0:
                            # Same keyframes — prefer larger amplitude
                            existing_amp = max(abs(v) for _, v in merged_bone[ch_name])
                            new_amp = max(abs(v) for _, v in ch_data)
                            if new_amp > existing_amp:
                                merged_bone[ch_name] = ch_data
                                actions.append({
                                    'animation': primary_name,
                                    'bone': bone,
                                    'channel': ch_name,
                                    'action': 'channel_replaced_larger_amplitude',
                                    'source': alt_name,
                                })
                merged[bone] = merged_bone

        return merged, actions

    @staticmethod
    def _is_empty_animation(bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]]) -> bool:
        """Check if an animation has no meaningful keyframe data (legacy compat)."""
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
        """Compute SHA-256 content hash for an animation's data."""
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
# GeckoLib JSON Builder (v5: support for static + near-empty)
# ============================================================================

class GeckoLibJSONBuilder:
    """Builds GeckoLib 1.20.1 .animation.json format from processed channel data.

    v5: Supports "static": true flag for empty/near-empty animations.
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()
        self.dp_simplifier = DouglasPeuckerSimplifier(self.config)

    def build(self, anim_name: str, loop_mode: str,
              bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
              duration: float,
              is_static: bool = False,
              is_near_empty: bool = False) -> dict:
        """Build a GeckoLib animation entry."""
        cfg = self.config
        bones_dict = {}

        for bone_name, channels in bone_channels.items():
            bone_entry = self._build_bone_entry(bone_name, channels, cfg,
                                                 loop_mode=loop_mode,
                                                 duration=duration)
            if bone_entry:
                bones_dict[bone_name] = bone_entry

        result = {
            "loop": loop_mode,
            "animation_length": round(duration, cfg.keyframe_precision),
            "bones": bones_dict
        }

        if is_static or is_near_empty:
            result["static"] = True

        return result

    def _build_bone_entry(self, bone_name: str,
                          channels: Dict[str, List[Tuple[float, float]]],
                          config: ConverterConfig,
                          loop_mode: str = "loop",
                          duration: float = 0.0) -> Optional[Dict]:
        """Build a GeckoLib bone entry.

        v5: After DP simplification, enforces C1 velocity matching for loop
        animations by adjusting the second-to-last keyframe to produce the
        correct velocity at the loop boundary.
        """
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

            # v5: For loop animations, enforce C1 velocity at the loop boundary
            if loop_mode == "loop" and len(simplified) >= 3 and duration > 0:
                simplified = self._enforce_keyframe_velocity(
                    simplified, duration, channel, config
                )

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

    def _enforce_keyframe_velocity(
        self,
        keyframes: List[Tuple[float, float]],
        duration: float,
        channel: str,
        config: ConverterConfig
    ) -> List[Tuple[float, float]]:
        """v5: Enforce C1 velocity match at loop boundary after DP simplification.

        After DP simplification removes keyframes, the velocity at the loop
        boundary may not match. This method INSERTS additional keyframes near
        the boundary (instead of modifying existing ones) to restore velocity
        matching while preserving the DP-simplified shape.

        Strategy:
        1. Compute the start and end velocities from the simplified keyframes
        2. If they don't match, insert a "velocity hint" keyframe just before
           the end and/or just after the start, with values computed to create
           the correct velocity at the boundary.
        3. These hint keyframes give GeckoLib's Catmull-Rom interpolation the
           information needed for smooth velocity at the loop point.
        """
        if len(keyframes) < 3 or duration <= 0:
            return keyframes

        p0 = keyframes[0][1]
        pT = keyframes[-1][1]

        # Ensure C0: snap last keyframe to first value
        if abs(pT - p0) > 1e-8:
            keyframes = keyframes[:-1] + [(keyframes[-1][0], p0)]
            pT = p0

        # Compute velocities at start and end from keyframe finite differences
        dt_start = keyframes[1][0] - keyframes[0][0]
        v_start = (keyframes[1][1] - p0) / dt_start if dt_start > 1e-12 else 0.0

        dt_end = keyframes[-1][0] - keyframes[-2][0]
        v_end = (pT - keyframes[-2][1]) / dt_end if dt_end > 1e-12 else 0.0

        # Check if C1 is already good enough
        c1_diff = abs(v_start - v_end)
        is_rotation = channel in ('rx', 'ry', 'rz')
        c1_thresh = config.velocity_match_threshold_rot if is_rotation else config.velocity_match_threshold_pos

        if c1_diff < c1_thresh:
            return keyframes  # Already good

        # C1 mismatch: insert velocity hint keyframes
        # The target velocity is the start velocity (preserved by global cubic correction)
        target_v = v_start

        result = list(keyframes)
        tick = config.tick_duration  # 0.05s

        # Insert a keyframe at t = duration - tick to set end velocity
        # We want the last segment's slope to be target_v
        # So the value at t = duration - tick should be:
        # pT - target_v * tick
        t_hint_end = duration - tick
        v_hint_end = pT - target_v * tick

        # Only insert if it doesn't overlap with existing keyframes
        insert_end = True
        for i, (t, v) in enumerate(result):
            if abs(t - t_hint_end) < tick * 0.5:
                # Keyframe already exists near this time — adjust it instead
                result[i] = (t, v_hint_end)
                insert_end = False
                break

        if insert_end and t_hint_end > result[-2][0] + tick * 0.5:
            result.append((t_hint_end, v_hint_end))
            result.sort(key=lambda x: x[0])

        # Snap last keyframe to p0 again (in case insertion changed it)
        if abs(result[-1][1] - p0) > 1e-8:
            result[-1] = (result[-1][0], p0)

        # Remove near-duplicate times
        deduped = []
        for t, v in result:
            if deduped and abs(t - deduped[-1][0]) < 0.001:
                deduped[-1] = (t, v)
            else:
                deduped.append((t, v))

        return deduped


# ============================================================================
# Quality Reporter (v5: correction magnitude + fidelity metrics)
# ============================================================================

class QualityReporter:
    """Generates quality reports for converted animations (v5 enhanced).

    v5 improvements:
    - Stricter thresholds: C0 < 0.1 deg, C1 < 1.5 deg/s
    - Correction magnitude metric: max(|c(t)|) / amplitude per channel
    - Fidelity score: 1.0 - correction_ratio per channel
    - Higher scores for global cubic vs local blend
    - Per-bone correction magnitude and fidelity score
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()

    def report(
        self,
        anim_name: str,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        cached_resampled: Optional[Dict[str, Dict[str, List[Tuple[float, float]]]]] = None,
        blend_diag: Optional[Dict[str, Any]] = None
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

        bone_breakdowns = []

        for bone_name, channels in bone_channels.items():
            breakdown = BoneQualityBreakdown(bone_name=bone_name)

            for channel, keyframes in channels.items():
                if len(keyframes) < 2:
                    continue

                is_rotation = channel in ('rx', 'ry', 'rz')

                p0 = keyframes[0][1]
                pT = keyframes[-1][1]
                c0_err = abs(pT - p0)

                if is_rotation:
                    c0_errors_rot.append(c0_err)
                    breakdown.c0_error_rot = max(breakdown.c0_error_rot, c0_err)
                else:
                    c0_errors_pos.append(c0_err)
                    breakdown.c0_error_pos = max(breakdown.c0_error_pos, c0_err)

                # v5: Velocity estimation from keyframe-level finite differences
                # This matches what GeckoLib actually renders — the velocity at
                # the boundary depends on the first/last two keyframes.
                if len(keyframes) >= 2 and duration > 0:
                    # Start velocity: from first two keyframes
                    dt_start = keyframes[1][0] - keyframes[0][0]
                    if dt_start > 1e-12:
                        v0 = (keyframes[1][1] - keyframes[0][1]) / dt_start
                    else:
                        v0 = 0.0

                    # End velocity: from last two keyframes
                    dt_end = keyframes[-1][0] - keyframes[-2][0]
                    if dt_end > 1e-12:
                        vT = (keyframes[-1][1] - keyframes[-2][1]) / dt_end
                    else:
                        vT = 0.0

                    c1_err = abs(vT - v0)

                    # Bounce-back severity
                    avg_vel = (abs(vT) + abs(v0)) / 2.0
                    if avg_vel > 1e-6 and v0 * vT < 0:
                        bounce = abs(v0 + vT) / avg_vel
                        breakdown.bounce_severity = max(breakdown.bounce_severity, bounce)

                    if is_rotation:
                        c1_errors_rot.append(c1_err)
                        breakdown.c1_error_rot = max(breakdown.c1_error_rot, c1_err)
                    else:
                        c1_errors_pos.append(c1_err)
                        breakdown.c1_error_pos = max(breakdown.c1_error_pos, c1_err)

            # v5: Correction magnitude from blend diagnostics
            if blend_diag and blend_diag.get('correction_magnitudes'):
                # Map corrections to bones (best effort: use worst for this bone)
                # We'll compute a per-channel correction magnitude separately
                pass

            bone_breakdowns.append(breakdown)

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
            p90_idx = int(len(sorted_c1) * 0.9)
            report.c1_avg_error_rot = sorted_c1[min(p90_idx, len(sorted_c1)-1)]
        if c1_errors_pos:
            sorted_c1 = sorted(c1_errors_pos)
            report.c1_max_error_pos = sorted_c1[-1]
            p90_idx = int(len(sorted_c1) * 0.9)
            report.c1_avg_error_pos = sorted_c1[min(p90_idx, len(sorted_c1)-1)]

        # Bounce-back severity
        if bone_breakdowns:
            report.bounce_back_severity = max(b.bounce_severity for b in bone_breakdowns)

        # v5: Correction magnitude and fidelity from blend diagnostics
        if blend_diag:
            correction_mags = blend_diag.get('correction_magnitudes', [])
            fidelity_scores = blend_diag.get('fidelity_scores', [])

            if correction_mags:
                report.correction_magnitude_max = max(correction_mags)
                report.correction_magnitude_avg = sum(correction_mags) / len(correction_mags)
            if fidelity_scores:
                report.fidelity_score_avg = sum(fidelity_scores) / len(fidelity_scores)

            report.global_cubic_used_count = blend_diag.get('global_cubic_count', 0)
            report.local_blend_used_count = blend_diag.get('local_blend_count', 0)
            report.static_snap_count = blend_diag.get('static_snap_count', 0)

            if report.global_cubic_used_count > 0:
                report.c1_method = 'global_cubic'
            elif report.local_blend_used_count > 0:
                report.c1_method = 'local_blend'
            elif report.static_snap_count > 0:
                report.c1_method = 'static_snap'

        # v5: Update per-bone breakdown with correction magnitude
        # Distribute the correction magnitudes to bone breakdowns proportionally
        if blend_diag and blend_diag.get('correction_magnitudes'):
            all_mags = blend_diag['correction_magnitudes']
            all_fidelity = blend_diag['fidelity_scores']
            # Assign average to each bone for now (per-channel tracking would require
            # channel-level diagnostics which we don't have here)
            n_channels = len(all_mags)
            if n_channels > 0 and bone_breakdowns:
                avg_mag = sum(all_mags) / n_channels
                avg_fidelity = sum(all_fidelity) / n_channels
                for b in bone_breakdowns:
                    b.correction_magnitude = avg_mag
                    b.fidelity_score = avg_fidelity

        # v5.1: Compute naturalness score (wobble detection)
        # Check if the correction curve creates visible wobbles by counting
        # sign changes in the second derivative of the corrected animation.
        naturalness, sign_changes = self._compute_naturalness(
            bone_channels, duration, cached_resampled
        )
        report.naturalness_score = naturalness
        report.second_derivative_sign_changes = sign_changes

        # Per-bone breakdown — sort by worst and keep top 3
        bone_breakdowns.sort(key=lambda b: b.worst_c0 + b.worst_c1, reverse=True)
        report.bone_breakdown = bone_breakdowns
        report.worst_bones = [b.bone_name for b in bone_breakdowns[:3]]

        # Quality assessment (v5: stricter thresholds)
        report.c0_perfect = report.c0_max_error_rot < self.config.c0_perfect_threshold_rot and \
                            report.c0_max_error_pos < self.config.c0_perfect_threshold_pos
        report.c1_perfect = report.c1_avg_error_rot < self.config.c1_perfect_threshold_rot and \
                            report.c1_avg_error_pos < self.config.c1_perfect_threshold_pos

        # Compute quality score (0-100) — v5 enhanced
        score = 100.0

        # C0 penalties
        if not report.c0_perfect:
            score -= min(30, report.c0_max_error_rot * 5 + report.c0_max_error_pos * 30)

        # C1 penalties using P90
        if not report.c1_perfect:
            c1_rot_penalty = min(25, report.c1_avg_error_rot * 1.5)
            c1_pos_penalty = min(15, report.c1_avg_error_pos * 5)
            score -= c1_rot_penalty + c1_pos_penalty

        # Bounce-back penalty
        if report.bounce_back_severity > 0.5:
            score -= min(10, report.bounce_back_severity * 5)

        # v5: Correction magnitude penalty
        if report.correction_magnitude_max > 0.10:
            score -= min(10, report.correction_magnitude_max * 20)

        # v5: Method bonus — global cubic gets a bonus for being "cleaner"
        if report.c1_method == 'global_cubic':
            score = min(100.0, score + 2.0)  # small bonus

        # v5: Fidelity score influence
        if report.fidelity_score_avg < 0.90:
            score -= min(5, (1.0 - report.fidelity_score_avg) * 20)

        # v5.1: Naturalness penalty — wobbles in the correction curve
        if report.naturalness_score < 0.8:
            score -= min(8, (1.0 - report.naturalness_score) * 15)

        # v5.1: No-enforcement bonus — animations that needed no C1 correction
        # at all get a bonus for being naturally smooth at loop boundaries
        if report.c1_method == 'none':
            score = min(100.0, score + 3.0)  # bonus for natural smoothness

        report.quality_score = max(0.0, min(100.0, score))

        # Generate warnings/errors
        if report.c0_max_error_rot > self.config.quality_error_threshold:
            report.errors.append(
                f"C0 rotation error too large: {report.c0_max_error_rot:.3f}deg "
                f"(threshold: {self.config.quality_error_threshold}deg)"
            )
        elif report.c0_max_error_rot > self.config.quality_warning_threshold:
            report.warnings.append(
                f"C0 rotation error: {report.c0_max_error_rot:.3f}deg"
            )

        if not report.c1_perfect:
            report.warnings.append(
                f"C1 velocity mismatch: rot={report.c1_max_error_rot:.2f}deg/s "
                f"(P90={report.c1_avg_error_rot:.2f}deg/s), "
                f"pos={report.c1_max_error_pos:.3f}px/s"
            )

        # Bounce-back warning
        if report.bounce_back_severity > 0.3:
            report.warnings.append(
                f"Bounce-back severity: {report.bounce_back_severity:.2f} "
                f"(worst bones: {', '.join(report.worst_bones)})"
            )

        # v5: Correction magnitude warning
        if report.correction_magnitude_max > 0.10:
            report.warnings.append(
                f"Correction magnitude: {report.correction_magnitude_max:.3f} "
                f"(avg: {report.correction_magnitude_avg:.3f}), "
                f"fidelity: {report.fidelity_score_avg:.3f}"
            )

        # v5: C1 method info
        if report.c1_method != 'none':
            report.warnings.append(
                f"C1 method: {report.c1_method} "
                f"(cubic={report.global_cubic_used_count}, "
                f"blend={report.local_blend_used_count}, "
                f"snap={report.static_snap_count})"
            )

        # Per-bone breakdown warning for worst bones
        for b in bone_breakdowns[:3]:
            if b.worst_c0 > self.config.quality_warning_threshold or b.worst_c1 > self.config.c1_quality_threshold_rot:
                report.warnings.append(
                    f"  Bone '{b.bone_name}': C0_rot={b.c0_error_rot:.3f}deg, "
                    f"C1_rot={b.c1_error_rot:.2f}deg/s, "
                    f"bounce={b.bounce_severity:.2f}, "
                    f"correction_mag={b.correction_magnitude:.3f}, "
                    f"fidelity={b.fidelity_score:.3f}"
                )

        # v5.1: Naturalness warning
        if report.naturalness_score < 0.8:
            report.warnings.append(
                f"Naturalness score: {report.naturalness_score:.3f} "
                f"({report.second_derivative_sign_changes} sign changes in 2nd derivative)"
            )

        return report

    def _compute_naturalness(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        cached_resampled: Optional[Dict[str, Dict[str, List[Tuple[float, float]]]]] = None
    ) -> Tuple[float, int]:
        """v5.1: Compute naturalness score by detecting wobbles in the animation.

        Wobbles are detected by counting sign changes in the second derivative
        (acceleration) of each channel. A high number of sign changes indicates
        the correction curve has introduced visible oscillations.

        Returns:
            (naturalness_score, total_sign_changes)
            naturalness_score: 1.0 = perfectly smooth, lower = more wobbles
        """
        total_sign_changes = 0
        total_channels = 0

        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if len(keyframes) < 4:
                    continue

                # Use cached resampled data if available, otherwise compute from keyframes
                if cached_resampled and bone_name in cached_resampled and channel in cached_resampled[bone_name]:
                    data = cached_resampled[bone_name][channel]
                else:
                    data = keyframes

                if len(data) < 4:
                    continue

                # Compute second derivative via finite differences
                values = [v for t, v in data]
                n = len(values)

                # First derivative
                first_deriv = []
                for i in range(n - 1):
                    dt = data[i + 1][0] - data[i][0]
                    if dt > 1e-12:
                        first_deriv.append((values[i + 1] - values[i]) / dt)
                    else:
                        first_deriv.append(0.0)

                # Second derivative
                second_deriv = []
                for i in range(len(first_deriv) - 1):
                    dt = data[i + 2][0] - data[i][0]
                    if dt > 1e-12:
                        second_deriv.append((first_deriv[i + 1] - first_deriv[i]) / dt)
                    else:
                        second_deriv.append(0.0)

                # Count sign changes in second derivative
                sign_changes = 0
                for i in range(1, len(second_deriv)):
                    if second_deriv[i] * second_deriv[i - 1] < 0:
                        # Only count if the magnitude is significant
                        if abs(second_deriv[i]) > 0.01 or abs(second_deriv[i - 1]) > 0.01:
                            sign_changes += 1

                total_sign_changes += sign_changes
                total_channels += 1

        if total_channels == 0:
            return 1.0, 0

        # Normalize: a reasonable animation might have ~2-3 sign changes per channel
        # per second. More than that suggests wobble.
        avg_sign_changes = total_sign_changes / total_channels
        expected_per_channel = max(2.0, duration * 3.0)  # ~3 per second, minimum 2

        # Naturalness score: 1.0 if at or below expected, decreasing as wobbles increase
        if avg_sign_changes <= expected_per_channel:
            naturalness = 1.0
        else:
            # Excess sign changes above expected
            excess = avg_sign_changes - expected_per_channel
            naturalness = max(0.0, 1.0 - excess / (expected_per_channel * 2.0))

        return naturalness, total_sign_changes


# ============================================================================
# Main Converter (v5: with global cubic C1 correction)
# ============================================================================

class BBModelAnimationConverter:
    """Universal animation converter for .bbmodel files (v5).

    Pipeline:
      1. Extract animations from .bbmodel (with enhanced empty/duplicate handling)
      2. Normalize animation names to GeckoLib convention
      3. For loop animations: detect optimal loop duration (with harmonic search)
      4. Enforce C1 continuity at loop boundaries (global cubic correction)
      5. Simplify keyframes
      6. Build GeckoLib .animation.json
      7. Generate quality report with correction magnitude and fidelity metrics

    v5 Improvements:
      - Global Cubic C1 Correction: distributes correction across entire animation
      - Hybrid C1 Enforcer: primary global cubic, fallback local blend, static snap
      - Per-channel adaptive blend window
      - Enhanced empty animation consolidation
      - Improved quality scoring with correction magnitude and fidelity
      - Enhanced duration optimization with harmonic search and phase-matching
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
        """Convert all animations in a .bbmodel file."""
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
            'static_preserved': extracted.get('static_preserved', []),
            'near_empty': extracted.get('near_empty', []),
            'merge_info': extracted.get('merge_info', []),
            'name_normalizations': [],
            'global_cubic_used': 0,
            'local_blend_used': 0,
            'static_snap_used': 0,
            'bridge_used': 0,
            'health_score': 0.0,
        }

        for anim_name, anim_data in extracted['animations'].items():
            # v5.1: Skip truly empty animations that have no bone channels at all
            if anim_data.get('should_skip', False):
                continue

            bone_channels = anim_data['bone_channels']
            current_duration = anim_data['length']
            loop_mode = anim_data['loop']
            interpolation = anim_data['interpolation']
            is_static = anim_data.get('static', False)
            is_near_empty = anim_data.get('is_near_empty', False)

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

            # For static/near-empty animations, skip C1 and duration optimization
            if is_static:
                anim_json = self.json_builder.build(
                    anim_name, loop_mode, bone_channels, current_duration,
                    is_static=True, is_near_empty=is_near_empty
                )
                all_animations[anim_name] = anim_json
                qreport = AnimationQualityReport(
                    animation_name=anim_name,
                    duration=current_duration,
                    num_bones=len(bone_channels),
                    total_keyframes=sum(
                        len(kfs) for chs in bone_channels.values()
                        for kfs in chs.values()
                    ),
                    is_static=True,
                    is_near_empty=is_near_empty,
                    quality_score=100.0,
                    c1_method='static_snap' if is_near_empty else 'none',
                )
                quality_reports[anim_name] = qreport
                continue

            # Compute duration from keyframes if length=0
            if current_duration <= 0:
                current_duration = self._compute_duration_from_keyframes(bone_channels)
                if current_duration <= 0:
                    current_duration = 1.0

            # Step 3: Duration optimization for loop animations only
            duration_change_reason = ""
            if loop_mode == "loop" and self.config.enable_duration_optimization:
                optimal_duration, loop_diag = self.loop_detector.detect_optimal_duration(
                    bone_channels, current_duration, interpolation
                )
                current_c0 = loop_diag.get('current_c0_error', float('inf'))
                best_c0 = loop_diag.get('best_c0_error', float('inf'))
                method = loop_diag.get('method', 'none')

                should_change = False
                if method in ('search_optimal', 'search_early_exit_good_enough',
                              'search_optimal_c1_priority') and current_c0 > 0.1:
                    improvement = (current_c0 - best_c0) / max(current_c0, 0.001)
                    if (improvement > self.config.duration_change_threshold and
                        current_c0 - best_c0 > self.config.min_duration_improvement):
                        should_change = True

                if should_change and abs(optimal_duration - current_duration) > 0.005:
                    old_dur = current_duration
                    new_dur = optimal_duration
                    if new_dur < old_dur:
                        ratio = old_dur / new_dur
                        if abs(ratio - round(ratio)) < 0.1:
                            n = round(ratio)
                            duration_change_reason = (
                                f"shortened {old_dur:.2f}s -> {new_dur:.2f}s "
                                f"— {n}x sub-multiple cycle"
                            )
                        else:
                            duration_change_reason = (
                                f"shortened {old_dur:.2f}s -> {new_dur:.2f}s "
                                f"— better C0 ({current_c0:.3f} -> {best_c0:.3f})"
                            )
                    else:
                        duration_change_reason = (
                            f"lengthened {old_dur:.2f}s -> {new_dur:.2f}s "
                            f"— better C0 ({current_c0:.3f} -> {best_c0:.3f})"
                        )

                    stats['duration_adjustments'].append({
                        'animation': anim_name,
                        'from': current_duration,
                        'to': optimal_duration,
                        'method': method,
                        'reason': duration_change_reason,
                    })
                    bone_channels = self._trim_to_duration(bone_channels, optimal_duration)
                    current_duration = optimal_duration
                else:
                    current_duration = anim_data['length']
            else:
                current_duration = anim_data['length']

            # CACHED RESAMPLING — resample once, use for both C1 and quality
            cached_resampled = self._resample_all_channels(
                bone_channels, current_duration, interpolation
            )

            # Step 4: C1 continuity enforcement with global cubic correction
            blend_diag = {
                'global_cubic_count': 0,
                'local_blend_count': 0,
                'static_snap_count': 0,
                'bridge_used_count': 0,
                'max_bounce_severity': 0.0,
                'bridge_details': [],
                'correction_magnitudes': [],
                'fidelity_scores': [],
            }
            if loop_mode == "loop":
                bone_channels, blend_diag = self.c1_enforcer.enforce(
                    bone_channels, current_duration, interpolation,
                    cached_resampled=cached_resampled
                )
                stats['global_cubic_used'] += blend_diag.get('global_cubic_count', 0)
                stats['local_blend_used'] += blend_diag.get('local_blend_count', 0)
                stats['static_snap_used'] += blend_diag.get('static_snap_count', 0)
                stats['bridge_used'] += blend_diag.get('bridge_used_count', 0)

                # Update cached resampled after C1 enforcement
                cached_resampled = self._resample_all_channels(
                    bone_channels, current_duration, interpolation
                )

            # Step 5: Build GeckoLib JSON
            anim_json = self.json_builder.build(
                anim_name, loop_mode, bone_channels, current_duration
            )
            all_animations[anim_name] = anim_json

            # Step 6: Quality report (v5: with correction magnitude and fidelity)
            qreport = self.quality_reporter.report(
                anim_name, bone_channels, current_duration,
                cached_resampled=cached_resampled,
                blend_diag=blend_diag
            )
            qreport.duration_adjusted = any(
                d['animation'] == anim_name for d in stats['duration_adjustments']
            )
            qreport.duration_change_reason = duration_change_reason
            qreport.bridge_used = blend_diag.get('bridge_used_count', 0) > 0
            qreport.bounce_back_severity = blend_diag.get('max_bounce_severity', 0.0)
            quality_reports[anim_name] = qreport

            if qreport.c0_perfect:
                stats['c0_perfect_count'] += 1
            if qreport.c1_perfect:
                stats['c1_perfect_count'] += 1

        # Compute per-model health score
        if quality_reports:
            stats['health_score'] = sum(
                qr.quality_score for qr in quality_reports.values()
            ) / len(quality_reports)

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

    def _resample_all_channels(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        interpolation: str = "catmullrom"
    ) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
        """Resample all channels once for caching."""
        cfg = self.config
        n_resample = max(int(duration * cfg.resample_rate), 60)
        resample_dt = duration / n_resample
        resample_times = [i * resample_dt for i in range(n_resample + 1)]

        resampled = {}
        for bone_name, channels in bone_channels.items():
            resampled[bone_name] = {}
            for channel, keyframes in channels.items():
                resampled[bone_name][channel] = CatmullRomEvaluator.resample_channel(
                    keyframes, resample_times, interpolation
                )

        return resampled

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

    def _compute_duration_from_keyframes(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]]
    ) -> float:
        """Compute animation duration from keyframe data when length=0.

        v5.1 improvements:
        - If the animation is truly static (no keyframes at all or all at t=0),
          return 1.0s as a reasonable default for static poses.
        - If keyframes exist, add a small padding (1 tick = 0.05s) after the
          last keyframe to ensure the last keyframe is fully visible.
        """
        max_time = 0.0
        has_any_motion = False
        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if keyframes:
                    max_time = max(max_time, keyframes[-1][0])
                    if keyframes[-1][0] > 0:
                        has_any_motion = True

        if max_time <= 0:
            # Truly static — no temporal extent
            return 1.0

        # Add 1 tick padding after last keyframe to ensure it's fully visible
        padded = max_time + TICK_DURATION

        return padded


# ============================================================================
# Batch Processing (v5: with ZIP packaging)
# ============================================================================

def batch_convert(input_dir: str, output_dir: str,
                  config: ConverterConfig = None,
                  zip_path: Optional[str] = None) -> bool:
    """Batch convert all .bbmodel files in a directory tree (v5).

    For each .bbmodel file:
      - Extract geo.json + texture (using bbmodel_to_geo.py)
      - Extract and convert animations (using this v5 converter)
      - Save to output directory maintaining directory structure
      - Optionally package into a ZIP file

    Returns:
        True if no errors, False otherwise.
    """
    print("=" * 70)
    print("  Universal BBModel Animation Converter (v5)")
    print("  .bbmodel -> .animation.json with Global Cubic C1 Correction")
    print("  GeckoLib Format for MC 1.20.1 Forge Mod Development")
    print("  [v5] Global Cubic C1 Correction (distributed across animation)")
    print("  [v5] Hybrid C1 Enforcer (primary: global cubic, fallback: local blend)")
    print("  [v5] Per-Channel Adaptive Blend Window")
    print("  [v5] Enhanced Empty Animation Consolidation")
    print("  [v5] Improved Quality Scoring (correction magnitude + fidelity)")
    print("  [v5] Enhanced Duration Optimization (harmonic search + phase-matching)")
    print("=" * 70)
    print()

    cfg = config or ConverterConfig()
    converter = BBModelAnimationConverter(cfg)

    # Import geo converter
    try:
        from bbmodel_to_geo import BBModelToGeo
        geo_converter = BBModelToGeo()
    except ImportError:
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
    print(f"  C1 mode: Global Cubic Correction (v5)")
    print(f"  Distortion limit: {cfg.global_cubic_distortion_limit*100:.0f}%")
    print(f"  Duration optimization: {'ON' if cfg.enable_duration_optimization else 'OFF'}")
    print(f"  Autocorrelation: {'ON (FFT)' if cfg.autocorrelation_enabled and _NUMPY_AVAILABLE else 'ON (pure)' if cfg.autocorrelation_enabled else 'OFF'}")
    print(f"  Harmonic search: {'ON' if cfg.harmonic_search_enabled else 'OFF'}")
    print(f"  Blend window: {cfg.blend_window_ratio*100:.0f}% base (adaptive per-channel)")
    print(f"  Early exit: C0 < {cfg.early_exit_c0_rot}deg, C1 < {cfg.early_exit_c1_rot}deg/s")
    print(f"  DP epsilon: rot={cfg.dp_epsilon_rotation}deg, pos={cfg.dp_epsilon_position}px")
    print(f"  Preserve empty as static: {'ON' if cfg.preserve_empty_as_static else 'OFF'}")
    print(f"  Semantic dedup: {'ON' if cfg.semantic_dedup_enabled else 'OFF'}")
    print(f"  Content-hash dedup: {'ON' if cfg.content_hash_dedup else 'OFF'}")
    print(f"  Smart bone merge: {'ON' if cfg.smart_bone_merge else 'OFF'}")
    print(f"  Always union bones: {'ON' if cfg.always_union_bones else 'OFF'}")
    print(f"  Tick snapping: {'ON' if cfg.snap_to_ticks else 'OFF'}")
    print(f"  Name normalization: {'ON' if cfg.normalize_animation_names else 'OFF'}")
    print()

    total_anims = 0
    total_keyframes = 0
    total_c0_perfect = 0
    total_c1_perfect = 0
    total_no_anim = 0
    total_skipped_empty = 0
    total_deduplicated = 0
    total_static_preserved = 0
    total_near_empty = 0
    total_global_cubic = 0
    total_local_blend = 0
    total_bridge = 0
    total_static_snap = 0
    all_quality_scores = []
    all_health_scores = []
    all_warnings = []
    all_errors = []
    all_output_files = []

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

            geo_mark = "+" if geo_ok else "-"
            anim_count = stats['total_animations']
            kf_count = stats['total_keyframes']
            c0_ok = stats['c0_perfect_count']
            c1_ok = stats['c1_perfect_count']
            dur_adj = len(stats['duration_adjustments'])
            skipped = len(stats.get('skipped_empty', []))
            deduped = len(stats.get('deduplicated', []))
            static_pres = len(stats.get('static_preserved', []))
            near_empty = len(stats.get('near_empty', []))
            global_cubic = stats.get('global_cubic_used', 0)
            local_blend = stats.get('local_blend_used', 0)
            bridge = stats.get('bridge_used', 0)
            static_snap = stats.get('static_snap_used', 0)
            health = stats.get('health_score', 0.0)

            total_skipped_empty += skipped
            total_deduplicated += deduped
            total_static_preserved += static_pres
            total_near_empty += near_empty
            total_global_cubic += global_cubic
            total_local_blend += local_blend
            total_bridge += bridge
            total_static_snap += static_snap

            if anim_count == 0:
                if skipped > 0:
                    print(f"{geo_mark} no_anim ({skipped} empty skipped)")
                else:
                    print(f"{geo_mark} no_anim (static model)")
                total_no_anim += 1
            else:
                for anim_name, qr in result['quality_reports'].items():
                    all_quality_scores.append(qr.quality_score)

                avg_score = sum(qr.quality_score for qr in result['quality_reports'].values()) / max(anim_count, 1)
                all_health_scores.append(health)

                extras = ""
                if dur_adj:
                    extras += f" dur_adj={dur_adj}"
                if skipped:
                    extras += f" skip={skipped}"
                if deduped:
                    extras += f" dedup={deduped}"
                if static_pres:
                    extras += f" static={static_pres}"
                if near_empty:
                    extras += f" near_empty={near_empty}"
                if global_cubic:
                    extras += f" cubic={global_cubic}"
                if local_blend:
                    extras += f" blend={local_blend}"
                if bridge:
                    extras += f" bridge={bridge}"
                print(f"{geo_mark} anims={anim_count} kf={kf_count} "
                      f"C0={c0_ok}/{anim_count} C1={c1_ok}/{anim_count} "
                      f"score={avg_score:.0f} health={health:.0f}{extras}")

                if os.path.exists(anim_output_path):
                    all_output_files.append(anim_output_path)

            total_anims += anim_count
            total_keyframes += kf_count
            total_c0_perfect += c0_ok
            total_c1_perfect += c1_ok

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

    # Global batch summary
    print()
    print("=" * 70)
    print("  CONVERSION SUMMARY (v5)")
    print("=" * 70)
    print(f"  Total models:            {len(bbmodel_files)}")
    print(f"  Models with animations:  {len(bbmodel_files) - total_no_anim}")
    print(f"  Static models:           {total_no_anim}")
    print(f"  Total animations:        {total_anims}")
    print(f"  Total keyframes:         {total_keyframes:,}")
    print(f"  C0 perfect:              {total_c0_perfect}/{total_anims} ({100*total_c0_perfect/max(total_anims,1):.1f}%)")
    print(f"  C1 good (P90):           {total_c1_perfect}/{total_anims} ({100*total_c1_perfect/max(total_anims,1):.1f}%)")
    print(f"  Empty skipped:           {total_skipped_empty}")
    print(f"  Static preserved:        {total_static_preserved}")
    print(f"  Near-empty preserved:    {total_near_empty}")
    print(f"  Duplicates merged:       {total_deduplicated}")
    print(f"  Global cubic corrections:{total_global_cubic}")
    print(f"  Local blend fallbacks:   {total_local_blend}")
    print(f"  Velocity bridge used:    {total_bridge}")
    print(f"  Static snaps:            {total_static_snap}")

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

    # Health score statistics
    if all_health_scores:
        avg_health = sum(all_health_scores) / len(all_health_scores)
        print(f"  Model health scores:")
        print(f"    Average:  {avg_health:.1f}")

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
    print("  DONE - Universal BBModel Animation Converter (v5)")
    print("  Global Cubic C1 Correction | Hybrid C1 Enforcer | Adaptive Blend")
    print("  Enhanced Empty Consolidation | Correction Magnitude | Fidelity Score")
    print("  Harmonic Search | Phase-Matching | Per-Channel Adaptive")
    print("=" * 70)

    return len(all_errors) == 0


def _create_zip_package(output_files: List[str], base_dir: str, zip_path: str) -> None:
    """Create a ZIP package containing all output files."""
    import zipfile

    print(f"\n  Creating ZIP package: {zip_path}")
    os.makedirs(os.path.dirname(zip_path) if os.path.dirname(zip_path) else '.', exist_ok=True)

    count = 0
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fpath in output_files:
            if os.path.exists(fpath):
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
        description="Universal BBModel Animation Converter with Global Cubic C1 Correction (v5)"
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
    parser.add_argument("--no-harmonic", action="store_true",
                        help="Disable harmonic search for duration optimization")
    parser.add_argument("--blend-ratio", type=float, default=0.10,
                        help="Base C1 blend window ratio (default: 0.10, adaptive per-channel)")
    parser.add_argument("--distortion-limit", type=float, default=0.15,
                        help="Max correction/amplitude ratio before local blend fallback (default: 0.15)")
    parser.add_argument("--dp-rot", type=float, default=0.04,
                        help="DP epsilon for rotation (degrees, default: 0.04)")
    parser.add_argument("--dp-pos", type=float, default=0.006,
                        help="DP epsilon for position (pixels, default: 0.006)")
    parser.add_argument("--no-preserve-empty", action="store_true",
                        help="Don't preserve empty animations as static poses")
    parser.add_argument("--skip-empty", action="store_true",
                        help="Skip empty animations entirely (legacy v3 behavior)")
    parser.add_argument("--no-dedup", action="store_true",
                        help="Disable case-insensitive deduplication")
    parser.add_argument("--no-semantic-dedup", action="store_true",
                        help="Disable semantic deduplication by normalized name")
    parser.add_argument("--no-content-hash", action="store_true",
                        help="Disable SHA-256 content-hash dedup")
    parser.add_argument("--no-smart-merge", action="store_true",
                        help="Disable smart bone-channel merging for duplicates")
    parser.add_argument("--no-union-bones", action="store_true",
                        help="Disable always-union bone channel merging")
    parser.add_argument("--no-name-norm", action="store_true",
                        help="Disable animation name normalization")
    parser.add_argument("--no-tick-snap", action="store_true",
                        help="Disable tick-boundary snapping for durations")
    parser.add_argument("--namespace", type=str, default="",
                        help="Namespace for animation name normalization")
    parser.add_argument("--bounce-threshold", type=float, default=0.3,
                        help="Bounce detection threshold for velocity bridge (default: 0.3)")
    args = parser.parse_args()

    config = ConverterConfig(
        enable_c1_enforcement=not args.no_c1,
        enable_duration_optimization=not args.no_duration_opt,
        autocorrelation_enabled=not args.no_autocorr,
        harmonic_search_enabled=not args.no_harmonic,
        blend_window_ratio=args.blend_ratio,
        global_cubic_distortion_limit=args.distortion_limit,
        dp_epsilon_rotation=args.dp_rot,
        dp_epsilon_position=args.dp_pos,
        preserve_empty_as_static=not args.no_preserve_empty and not args.skip_empty,
        skip_empty_animations=args.skip_empty,
        deduplicate_case_insensitive=not args.no_dedup,
        semantic_dedup_enabled=not args.no_semantic_dedup,
        content_hash_dedup=not args.no_content_hash,
        smart_bone_merge=not args.no_smart_merge,
        always_union_bones=not args.no_union_bones,
        normalize_animation_names=not args.no_name_norm,
        animation_namespace=args.namespace,
        snap_to_ticks=not args.no_tick_snap,
        bounce_detection_threshold=args.bounce_threshold,
    )

    success = batch_convert(args.input, args.output, config, args.zip)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
