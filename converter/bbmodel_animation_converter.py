#!/usr/bin/env python3
"""
BBModelAnimationConverter - Universal Animation Converter (v13)
==============================================================
Converts Blockbench .bbmodel animation keyframes to GeckoLib .animation.json
format with automatic loop continuity enforcement, C1 velocity matching,
C2 acceleration matching, duration optimization, and comprehensive quality feedback.

Key Features:
  - Direct .bbmodel -> .animation.json conversion (no Java source needed)
  - C0 + C1 + C2 continuity enforcement at loop boundaries
  - FIXED: Hermite basis functions used with LINEAR parameter (no smootherstep warp)
  - Symmetric dual-endpoint C1 blending (start AND end blend windows)
  - v13: Quintic Hermite C2 acceleration matching in blend windows
  - Automatic loop duration detection with autocorrelation-based period analysis
  - v13: Walk-specific period detection heuristics
  - v13: Periodic boundary conditions for Catmull-Rom resampling of loop animations
  - v13: Walk animation automatic upsampling for sparse keyframes
  - v13: Smart duplicate merging - keeps all unique names as aliases
  - v13: Animation-type-aware DP epsilon (idle=1.5x, attack=0.8x, walk=1.0x)
  - "Good enough" early exit when C0 < 0.5 deg and C1 < 5 deg/s
  - Intelligent empty/duplicate animation detection and deduplication
  - v13: Fixed name normalization double-namespace bug
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

# v13: Animation type classification patterns
WALK_NAME_PATTERNS = re.compile(
    r'(walk|run|move|stride|trot|gallop|sprint|jog|amble|pace|canter)',
    re.IGNORECASE
)
IDLE_NAME_PATTERNS = re.compile(
    r'(idle|rest|sleep|stand|breathe|pose|ambient)',
    re.IGNORECASE
)
ATTACK_NAME_PATTERNS = re.compile(
    r'(attack|hit|strike|slash|punch|kick|bite|slam|smash)',
    re.IGNORECASE
)


def classify_animation_type(name: str) -> str:
    """Classify an animation name into a type for type-aware processing.

    Returns one of: 'walk', 'idle', 'attack', 'generic'
    """
    name_lower = name.lower()
    if WALK_NAME_PATTERNS.search(name_lower):
        return 'walk'
    if IDLE_NAME_PATTERNS.search(name_lower):
        return 'idle'
    if ATTACK_NAME_PATTERNS.search(name_lower):
        return 'attack'
    return 'generic'


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

    # --- C2 Continuity (v13) ---
    enable_c2_enforcement: bool = True     # v13: enable C2 acceleration matching
    c2_blend_window_ratio: float = 0.15    # v13: wider blend window for C2 (15% per side)
    c2_accel_threshold_rot: float = 50.0   # v13: degrees/s^2 threshold for C2

    # --- Duration Optimization ---
    enable_duration_optimization: bool = True
    duration_search_step: float = 0.01      # seconds
    phase_error_tolerance: float = 0.02     # radians
    duration_change_threshold: float = 0.1  # only change if improvement > 10%
    min_duration_improvement: float = 0.05  # minimum absolute improvement to justify change
    autocorrelation_enabled: bool = True    # use autocorrelation for period detection
    early_exit_c0_rot: float = 0.5         # degrees - "good enough" C0 for early exit
    early_exit_c1_rot: float = 5.0         # degrees/s - "good enough" C1 for early exit

    # --- Walk Period Detection (v13) ---
    walk_period_heuristic: bool = True      # v13: use walk-specific period heuristic
    common_walk_durations: tuple = (0.5, 0.667, 1.0, 1.5, 2.0)  # v13: common walk cycle durations

    # --- Simplification ---
    dp_epsilon_rotation: float = 0.05       # degrees (tighter for better fidelity)
    dp_epsilon_position: float = 0.008      # pixels

    # --- v13: Animation-type-aware DP epsilon multipliers ---
    dp_epsilon_idle_multiplier: float = 1.5    # idle: can afford more simplification
    dp_epsilon_attack_multiplier: float = 0.8  # attack: need more precision
    dp_epsilon_walk_multiplier: float = 1.0    # walk: standard

    # --- Resampling ---
    resample_rate: float = 120.0            # Hz for catmullrom evaluation

    # --- v13: Walk Upsampling ---
    enable_walk_upsampling: bool = True       # v13: auto-upsample sparse walk animations
    walk_upsample_max_kf: int = 6            # v13: upsample if <=6 kf per channel
    walk_upsample_fps: float = 30.0          # v13: target fps for upsampled walk anims

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
    keep_duplicate_aliases: bool = True      # v13: keep duplicate names as aliases

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

    # v13: C2 continuity (acceleration match at loop boundary)
    c2_max_error_rot: float = 0.0           # degrees/s^2
    c2_avg_error_rot: float = 0.0
    c2_perfect: bool = True

    # Duration quality
    duration_phase_error: float = 0.0
    duration_optimal: bool = True

    # v13: Animation type
    animation_type: str = 'generic'

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

    v13: Added periodic boundary condition support for loop animations.
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
    def evaluate_second_derivative(t: float, p0: float, p1: float,
                                   p2: float, p3: float,
                                   dt: float = 1.0) -> float:
        """Evaluate second derivative of Catmull-Rom spline at parameter t in [0,1].

        v13: Added for C2 continuity checking.

        Args:
            t: Parameter in [0, 1]
            p0, p1, p2, p3: Control points
            dt: Segment duration for proper scaling

        Returns:
            Second derivative value.
        """
        v01 = 0.5 * (p2 - p0)
        v12 = 0.5 * (p3 - p1)

        # Second derivative of Catmull-Rom
        d2 = (12 * t - 6) * p1 + \
             (6 * t - 4) * v01 + \
             (-12 * t + 6) * p2 + \
             (6 * t - 2) * v12

        return d2 / (dt * dt) if dt > 1e-12 else 0.0

    @staticmethod
    def resample_channel(keyframes: List[Tuple[float, float]],
                         target_times: List[float],
                         interpolation: str = "catmullrom",
                         periodic: bool = False) -> List[Tuple[float, float]]:
        """Resample a channel at specified time points.

        v13: Added 'periodic' parameter for loop animations.
        When periodic=True, boundary control points wrap around.

        Args:
            keyframes: [(time, value), ...] sorted by time
            target_times: Time points to sample at
            interpolation: "catmullrom" or "linear"
            periodic: v13 - if True, use wrap-around for boundary control points

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

            if interpolation == "catmullrom" and n >= 3:
                # v13: Get control points with periodic boundary support
                if periodic and n >= 3:
                    # v13: Wrap-around for boundary control points
                    if seg_idx == 0:
                        # At first segment: p0 wraps from end
                        p0_val = keyframes[-1][1]
                    else:
                        p0_val = keyframes[seg_idx - 1][1]

                    if seg_idx + 2 >= n:
                        # At last segment: p3 wraps from start
                        p3_val = keyframes[0][1]
                    else:
                        p3_val = keyframes[seg_idx + 2][1]
                else:
                    # Original non-periodic behavior
                    if n < 4:
                        # Fall back to linear for <4 keyframes if not periodic
                        val = k0[1] + s * (k1[1] - k0[1])
                        result.append((t, val))
                        continue
                    p0_val = keyframes[max(0, seg_idx - 1)][1]
                    p3_val = keyframes[min(n - 1, seg_idx + 2)][1]

                p1_val = k0[1]
                p2_val = k1[1]

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

    Improvements (v13):
    - Walk-specific period heuristic for common walk cycle durations
    - Prioritizes sub-multiples matching common walk durations
    - Improved early exit for walk animations
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()

    def detect_optimal_duration(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        current_duration: float,
        interpolation: str = "catmullrom",
        anim_name: str = ""
    ) -> Tuple[float, Dict[str, Any]]:
        """Find the optimal loop duration for an animation.

        v13: Added anim_name parameter for type-specific heuristics.

        Args:
            bone_channels: {bone: {channel: [(t, v), ...]}}
            current_duration: Current animation length in seconds
            interpolation: Interpolation type for resampling
            anim_name: v13 - animation name for type-specific detection

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

        # v13: Walk-specific heuristic
        anim_type = classify_animation_type(anim_name)
        is_walk = anim_type == 'walk'

        if is_walk and cfg.walk_period_heuristic:
            # v13: If animation name contains walk/run and duration < 2s,
            # the duration is likely already correct as a single stride cycle
            if current_duration <= 2.0:
                # Verify with a quick continuity check
                sample_rate = cfg.resample_rate
                n_samples = int(current_duration * sample_rate)
                target_times = [i / sample_rate for i in range(n_samples + 1)]
                resampled = {}
                for bone_name, channels in bone_channels.items():
                    resampled[bone_name] = {}
                    for channel, keyframes in channels.items():
                        resampled[bone_name][channel] = CatmullRomEvaluator.resample_channel(
                            keyframes, target_times, interpolation, periodic=True
                        )
                c0_err, c1_err = self._evaluate_continuity(
                    resampled, current_duration, sample_rate
                )
                # For short walk animations, accept the current duration
                # as it's likely a carefully authored stride cycle
                if c0_err < cfg.loop_position_tolerance_rot * 2:
                    diagnostics['method'] = 'v13_walk_period_heuristic'
                    diagnostics['best_c0_error'] = c0_err
                    diagnostics['best_c1_error'] = c1_err
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

        # Evaluate current duration first - prioritize original if good
        c0_err, c1_err = self._evaluate_continuity(resampled, current_duration, sample_rate)
        diagnostics['current_c0_error'] = c0_err
        diagnostics['current_c1_error'] = c1_err

        # "Good enough" early exit: if original duration already satisfies
        # C0 < 0.5 deg and C1 < 5 deg/s, accept it immediately
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

        # v13: Method 1.5: Prioritize common walk cycle durations
        if is_walk and cfg.walk_period_heuristic:
            for walk_dur in cfg.common_walk_durations:
                if cfg.min_loop_duration <= walk_dur <= cfg.max_loop_duration:
                    candidates.append(walk_dur)
                # Also try sub-multiples of current that are near common walk durations
                for n in range(1, 10):
                    T = current_duration / n
                    for wd in cfg.common_walk_durations:
                        if abs(T - wd) < 0.05 and cfg.min_loop_duration <= T <= cfg.max_loop_duration:
                            candidates.append(T)
                            candidates.append(wd)

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
    """Enforces C1 (velocity) and C2 (acceleration) continuity at loop boundaries.

    The core problem:
      At the end of a looping animation, position may match (C0) but
      velocity (derivative) may differ, causing a visible "bounce-back"
      or "stutter" when the animation loops.

    Solution (v2 - FIXED):
      Use cubic Hermite interpolation in blend windows near BOTH the start
      AND end of the animation to create a proper periodic bridge.

    v13 Enhancement - C2 Continuity:
      After the C0+C1 Hermite blend, apply a second pass using quintic
      Hermite interpolation which supports C2 (acceleration matching).
      The quintic Hermite basis requires 6 constraints: p0, v0, a0, p1, v1, a1.

      Quintic Hermite basis functions (parameter s in [0,1]):
        h00 = 1 - 10s^3 + 15s^4 - 6s^5
        h10 = s - 6s^3 + 8s^4 - 3s^5
        h20 = 0.5s^2 - 1.5s^3 + 1.5s^4 - 0.5s^5
        h01 = 10s^3 - 15s^4 + 6s^5
        h11 = -4s^3 + 7s^4 - 3s^5
        h21 = 0.5s^3 - s^4 + 0.5s^5

    This provides:
      - C0: Perfect position match (last keyframe snaps to first)
      - C1: Smooth velocity transition (Hermite blend in window)
      - C2: Smooth acceleration transition (quintic Hermite in window)
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()

    @staticmethod
    def _quintic_hermite(s: float, p0: float, v0: float, a0: float,
                         p1: float, v1: float, a1: float,
                         dt: float) -> float:
        """Evaluate quintic Hermite interpolation.

        v13: Supports C2 continuity by matching position, velocity, and acceleration.

        Args:
            s: Parameter in [0, 1]
            p0, v0, a0: Start position, velocity, acceleration
            p1, v1, a1: End position, velocity, acceleration
            dt: Time span for velocity/acceleration scaling

        Returns:
            Interpolated value.
        """
        s2 = s * s
        s3 = s2 * s
        s4 = s3 * s
        s5 = s4 * s

        # Quintic Hermite basis functions
        h00 = 1 - 10*s3 + 15*s4 - 6*s5
        h10 = s - 6*s3 + 8*s4 - 3*s5
        h20 = 0.5*s2 - 1.5*s3 + 1.5*s4 - 0.5*s5
        h01 = 10*s3 - 15*s4 + 6*s5
        h11 = -4*s3 + 7*s4 - 3*s5
        h21 = 0.5*s3 - s4 + 0.5*s5

        return (h00 * p0 +
                h10 * dt * v0 +
                h20 * dt * dt * a0 +
                h01 * p1 +
                h11 * dt * v1 +
                h21 * dt * dt * a1)

    def enforce(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        interpolation: str = "catmullrom"
    ) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
        """Apply symmetric dual-endpoint C1+C2 continuity enforcement to all channels.

        Strategy:
          1. Resample each channel at high rate using catmullrom/linear interpolation
             with periodic boundary conditions (v13)
          2. Compute start/end velocity and acceleration from resampled data
          3. If velocity/acceleration mismatch detected:
             a. Apply quintic Hermite blend at the END (v13: C2-capable)
             b. Apply quintic Hermite blend at the START (v13: C2-capable)
          4. Replace original keyframes with resampled + blended data

        Args:
            bone_channels: {bone: {channel: [(t, v), ...]}}
            duration: Animation duration
            interpolation: Interpolation type for resampling

        Returns:
            Modified bone_channels with C1+C2 continuity enforced.
        """
        cfg = self.config
        if not cfg.enable_c1_enforcement:
            return bone_channels

        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if len(keyframes) < 2:
                    continue

                is_rotation = channel in ('rx', 'ry', 'rz', 'x', 'y', 'z')

                # Step 1: Resample at high rate for velocity/acceleration estimation
                # v13: Use periodic boundary conditions for better boundary estimation
                n_resample = max(int(duration * cfg.resample_rate), 60)
                resample_dt = duration / n_resample
                resample_times = [i * resample_dt for i in range(n_resample + 1)]

                # v13: Use periodic resampling for loop animations
                is_loop = True  # this method is only called for loop animations
                resampled = CatmullRomEvaluator.resample_channel(
                    keyframes, resample_times, interpolation,
                    periodic=is_loop
                )

                # Step 2: Compute velocities and accelerations at start and end
                if len(resampled) < 7:
                    continue

                p0 = resampled[0][1]
                pT = resampled[-1][1]

                # Use 3-point forward/backward difference for velocity estimation
                v0 = (-3*resampled[0][1] + 4*resampled[1][1] - resampled[2][1]) / (2*resample_dt)
                vT = (3*resampled[-1][1] - 4*resampled[-2][1] + resampled[-3][1]) / (2*resample_dt)

                # v13: Acceleration estimation using 3-point formula
                # a = (f(x+h) - 2f(x) + f(x-h)) / h^2
                a0 = (resampled[2][1] - 2*resampled[1][1] + resampled[0][1]) / (resample_dt * resample_dt)
                aT = (resampled[-1][1] - 2*resampled[-2][1] + resampled[-3][1]) / (resample_dt * resample_dt)

                # Check if C1 enforcement is needed
                c0_thresh = cfg.c0_snap_threshold_rot if is_rotation else cfg.c0_snap_threshold_pos
                c1_thresh = cfg.velocity_match_threshold_rot if is_rotation else cfg.velocity_match_threshold_pos

                c0_diff = abs(p0 - pT)
                c1_diff = abs(v0 - vT)
                c2_diff = abs(a0 - aT)  # v13: acceleration mismatch

                if c0_diff < c0_thresh and c1_diff < c1_thresh:
                    # Already good enough - just snap C0
                    if c0_diff > 1e-8:
                        # Snap last keyframe to first value
                        channels[channel] = [
                            (t, v) if i < len(keyframes) - 1 else (t, keyframes[0][1])
                            for i, (t, v) in enumerate(keyframes)
                        ]
                    continue

                # v13: Determine blend window - wider for C2 enforcement
                if cfg.enable_c2_enforcement and c2_diff > cfg.c2_accel_threshold_rot:
                    # Use wider window for C2 blend
                    w = min(duration * cfg.c2_blend_window_ratio, cfg.max_blend_window * 1.5)
                else:
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
                # END BLEND
                # ============================================================
                end_blend_start_time = max(0, duration - w)

                # Find resampled points in end blend window
                end_blend_start_idx = 0
                for i, (t, v) in enumerate(resampled):
                    if t >= end_blend_start_time:
                        end_blend_start_idx = i
                        break

                if end_blend_start_idx >= 1 and end_blend_start_idx < len(resampled) - 1:
                    p_end_blend_start = resampled[end_blend_start_idx][1]
                    t_end_blend_start = resampled[end_blend_start_idx][0]

                    # Velocity at end-blend start via central difference
                    v_end_blend_start = (
                        (resampled[end_blend_start_idx + 1][1] -
                         resampled[end_blend_start_idx - 1][1]) /
                        (resampled[end_blend_start_idx + 1][0] -
                         resampled[end_blend_start_idx - 1][0])
                    )

                    # v13: Acceleration at end-blend start
                    a_end_blend_start = (
                        (resampled[end_blend_start_idx + 1][1] -
                         2*resampled[end_blend_start_idx][1] +
                         resampled[end_blend_start_idx - 1][1]) /
                        ((resampled[end_blend_start_idx + 1][0] -
                          resampled[end_blend_start_idx - 1][0]) / 2) ** 2
                    )

                    # Target: position at end = p0, velocity at end = v0
                    p_end_blend_end = p0
                    v_end_blend_end = v0
                    # v13: acceleration at end should match start
                    a_end_blend_end = a0

                    w_end_actual = duration - t_end_blend_start
                    if w_end_actual > 1e-12:
                        # v13: Use quintic Hermite if C2 enforcement enabled
                        use_c2 = (cfg.enable_c2_enforcement and
                                  abs(a_end_blend_start - a0) > cfg.c2_accel_threshold_rot)

                        for i in range(end_blend_start_idx, len(resampled)):
                            t, v = resampled[i]
                            s = (t - t_end_blend_start) / w_end_actual
                            s = max(0.0, min(1.0, s))

                            if use_c2:
                                # v13: Quintic Hermite for C2 continuity
                                new_val = self._quintic_hermite(
                                    s,
                                    p_end_blend_start, v_end_blend_start, a_end_blend_start,
                                    p_end_blend_end, v_end_blend_end, a_end_blend_end,
                                    w_end_actual
                                )
                            else:
                                # Cubic Hermite (C0+C1 only)
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
                # START BLEND
                # ============================================================
                start_blend_end_time = min(w, duration)

                # Find resampled points in start blend window
                start_blend_end_idx = 0
                for i, (t, v) in enumerate(resampled):
                    if t >= start_blend_end_time:
                        start_blend_end_idx = i
                        break

                if start_blend_end_idx >= 1 and start_blend_end_idx < len(resampled) - 1:
                    p_start_blend_end = resampled[start_blend_end_idx][1]
                    t_start_blend_end = resampled[start_blend_end_idx][0]

                    # Velocity at start-blend end via central difference
                    v_start_blend_end = (
                        (resampled[start_blend_end_idx + 1][1] -
                         resampled[start_blend_end_idx - 1][1]) /
                        (resampled[start_blend_end_idx + 1][0] -
                         resampled[start_blend_end_idx - 1][0])
                    )

                    # v13: Acceleration at start-blend end
                    a_start_blend_end = (
                        (resampled[start_blend_end_idx + 1][1] -
                         2*resampled[start_blend_end_idx][1] +
                         resampled[start_blend_end_idx - 1][1]) /
                        ((resampled[start_blend_end_idx + 1][0] -
                          resampled[start_blend_end_idx - 1][0]) / 2) ** 2
                    )

                    # Start of blend: matches the end state (periodic bridge)
                    p_start_blend_start = p0
                    v_start_blend_start = v0
                    a_start_blend_start = a0  # v13

                    w_start_actual = t_start_blend_end
                    if w_start_actual > 1e-12:
                        # v13: Use quintic Hermite if C2 enforcement enabled
                        use_c2 = (cfg.enable_c2_enforcement and
                                  abs(a_start_blend_end - a0) > cfg.c2_accel_threshold_rot)

                        for i in range(0, start_blend_end_idx + 1):
                            t, v = resampled[i]
                            s = (t - 0.0) / w_start_actual
                            s = max(0.0, min(1.0, s))

                            if use_c2:
                                # v13: Quintic Hermite for C2 continuity
                                new_val = self._quintic_hermite(
                                    s,
                                    p_start_blend_start, v_start_blend_start, a_start_blend_start,
                                    p_start_blend_end, v_start_blend_end, a_start_blend_end,
                                    w_start_actual
                                )
                            else:
                                # Cubic Hermite (C0+C1 only)
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
                new_keyframes = []

                # Add original keyframes that are outside both blend windows
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
    """Channel-type-aware Douglas-Peucker simplification.

    v13: Animation-type-aware epsilon multipliers.
    """

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

    def get_epsilon(self, channel: str, animation_type: str = 'generic') -> float:
        """Get channel-appropriate and animation-type-aware DP epsilon.

        v13: Applies animation-type multipliers.
        Idle: 1.5x epsilon (more simplification)
        Attack: 0.8x epsilon (less simplification)
        Walk: 1.0x epsilon (standard)
        """
        cfg = self.config
        if channel in ('rx', 'ry', 'rz', 'x', 'y', 'z'):
            base_epsilon = cfg.dp_epsilon_rotation
        else:
            base_epsilon = cfg.dp_epsilon_position

        # v13: Apply animation-type multiplier
        if animation_type == 'idle':
            multiplier = cfg.dp_epsilon_idle_multiplier
        elif animation_type == 'attack':
            multiplier = cfg.dp_epsilon_attack_multiplier
        elif animation_type == 'walk':
            multiplier = cfg.dp_epsilon_walk_multiplier
        else:
            multiplier = 1.0

        return base_epsilon * multiplier


# ============================================================================
# Animation Name Normalizer
# ============================================================================

class AnimationNameNormalizer:
    """Normalizes animation names to follow GeckoLib convention.

    GeckoLib convention: animation.<namespace>.<entity>.<state>
    Examples:
      - "idle" -> "animation.<namespace>.<entity>.idle"
      - "animation.model.idle" -> "animation.<namespace>.<entity>.idle"
      - "walk_cycle" -> "animation.<namespace>.<entity>.walk_cycle"

    v13 FIX: Fixed double-namespace bug where "animation.ferCow.walk"
    became "animation.fercow.fercow.walk" instead of "animation.fercow.fercow.walk"
    Now properly detects entity part from the original name.
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

        v13 FIX: If the original name already has the GeckoLib format
        (animation.<something>.<state>), just clean it up rather than
        reconstructing from scratch which caused double-namespace bugs.

        Args:
            name: Original animation name
            model_name: Model/entity name for constructing the namespace
            namespace: Optional explicit namespace override

        Returns:
            Normalized name in format animation.<namespace>.<entity>.<state>
        """
        if not name:
            return name

        original = name.strip()

        # v13 FIX: Check if the name already follows GeckoLib convention
        # Pattern: animation.<part1>[.<part2>][...].<state>
        # If it starts with "animation." and has 3+ dot-separated parts,
        # it's likely already in GeckoLib format. Just normalize casing.
        if original.lower().startswith('animation.'):
            parts = original.split('.')
            if len(parts) >= 3:
                # Already in GeckoLib format: animation.<ns/entity>.<entity>.<state>
                # or animation.<entity>.<state>
                # Just normalize each part: lowercase, clean special chars
                cleaned_parts = ['animation']
                for part in parts[1:]:
                    cleaned = re.sub(r'[^a-zA-Z0-9_]', '_', part)
                    cleaned_parts.append(cleaned)  # preserve original casing for entity names
                # Apply state aliases only to the LAST part (state name)
                last = cleaned_parts[-1].lower()
                if last in AnimationNameNormalizer.STATE_ALIASES:
                    cleaned_parts[-1] = AnimationNameNormalizer.STATE_ALIASES[last]
                return '.'.join(cleaned_parts)

        # For simple names (no "animation." prefix), construct GeckoLib format
        state = original

        # Remove redundant prefixes
        for prefix in AnimationNameNormalizer.REDUNDANT_PREFIXES:
            if state.lower().startswith(prefix):
                state = state[len(prefix):]
                break

        # Parse dot-separated parts for entity/state
        parts = state.split('.')
        if len(parts) >= 2:
            # e.g., "ferCow.walk" -> entity from first part, state from last
            entity_part = '.'.join(parts[:-1])
            state = parts[-1]
        else:
            entity_part = ""

        # Apply state aliases
        state_lower = state.lower()
        if state_lower in AnimationNameNormalizer.STATE_ALIASES:
            state = AnimationNameNormalizer.STATE_ALIASES[state_lower]

        # Clean the state name
        state = re.sub(r'[\s\-]+', '_', state)
        state = re.sub(r'[^a-zA-Z0-9_]', '', state)

        # Determine entity
        if entity_part:
            entity = entity_part
        else:
            entity = model_name if model_name else "entity"

        # Clean entity name
        entity = re.sub(r'[^a-zA-Z0-9_]', '_', entity)

        # Determine namespace
        if namespace:
            ns = namespace.lower()
        else:
            ns = entity.lower()

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

    Improvements (v13):
      - Smart duplicate merging: keeps all unique names as aliases
      - Duplicate animations are output as separate entries with same data
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
                        'interpolation': str,
                        'is_empty': bool,
                    }
                },
                'skipped_empty': List[str],
                'deduplicated': List[str],
                'duplicate_aliases': Dict[str, str],  # v13: alias -> canonical name
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
        duplicate_aliases = {}  # v13: alias_name -> canonical_name

        if self.config.deduplicate_case_insensitive:
            # Case-insensitive deduplication
            seen_lower = {}  # lowercase_name -> canonical_name
            for anim_name, anim_data in raw_animations.items():
                lower_name = anim_name.lower()
                if lower_name in seen_lower:
                    canonical = seen_lower[lower_name]
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
                        deduplicated.append(anim_name)
                else:
                    seen_lower[lower_name] = anim_name
                    animations[anim_name] = anim_data
        else:
            animations = raw_animations

        # v13: Smart duplicate merging - keep all unique names as aliases
        if self.config.merge_duplicate_animations:
            data_signatures = {}
            final_animations = {}
            for anim_name, anim_data in animations.items():
                sig = self._compute_animation_signature(anim_data)
                if sig in data_signatures:
                    # v13: Instead of dropping, keep as alias
                    canonical_name = data_signatures[sig]
                    if self.config.keep_duplicate_aliases:
                        # Keep duplicate as a separate animation entry with same data
                        # This ensures mod code referencing the specific name still works
                        final_animations[anim_name] = anim_data
                        duplicate_aliases[anim_name] = canonical_name
                        deduplicated.append(f"{anim_name} (alias of {canonical_name})")
                    else:
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
            'duplicate_aliases': duplicate_aliases,
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
    """Builds GeckoLib 1.20.1 .animation.json format from processed channel data.

    v13: Animation-type-aware DP epsilon for better idle/walk/attack simplification.
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()
        self.dp_simplifier = DouglasPeuckerSimplifier(self.config)

    def build(self, anim_name: str, loop_mode: str,
              bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
              duration: float,
              animation_type: str = 'generic') -> dict:
        """Build a GeckoLib animation entry.

        v13: Added animation_type parameter for type-aware simplification.

        Args:
            anim_name: Animation name (e.g., "animation.model.idle")
            loop_mode: "loop" or "hold_on_last_frame"
            bone_channels: {bone: {channel: [(t, v), ...]}}
            duration: Animation duration
            animation_type: v13 - 'walk', 'idle', 'attack', or 'generic'

        Returns:
            GeckoLib animation dict.
        """
        cfg = self.config
        bones_dict = {}

        for bone_name, channels in bone_channels.items():
            bone_entry = self._build_bone_entry(bone_name, channels, cfg, animation_type)
            if bone_entry:
                bones_dict[bone_name] = bone_entry

        return {
            "loop": loop_mode,
            "animation_length": round(duration, cfg.keyframe_precision),
            "bones": bones_dict
        }

    def _build_bone_entry(self, bone_name: str,
                          channels: Dict[str, List[Tuple[float, float]]],
                          config: ConverterConfig,
                          animation_type: str = 'generic') -> Optional[Dict]:
        """Build a GeckoLib bone entry.

        v13: Uses animation-type-aware DP epsilon.
        """
        rot_channels = {}
        pos_channels = {}

        for channel, keyframes in channels.items():
            if not keyframes:
                continue

            # v13: Apply animation-type-aware DP simplification
            epsilon = self.dp_simplifier.get_epsilon(channel, animation_type)
            simplified = self.dp_simplifier.simplify(keyframes, epsilon)

            # Check if all values are near-zero
            max_abs = max(abs(v) for t, v in simplified) if simplified else 0.0
            if max_abs < config.filter_zero_threshold:
                continue

            axis = channel[-1]  # rx->x, ry->y, rz->z, ox->x, oy->y, oz->z

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
# Quality Reporter
# ============================================================================

class QualityReporter:
    """Generates quality reports for converted animations.

    v13: Added C2 continuity metrics and animation type classification.
    """

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
        anim_type = classify_animation_type(anim_name)

        report = AnimationQualityReport(
            animation_name=anim_name,
            duration=duration,
            num_bones=len(bone_channels),
            total_keyframes=sum(
                len(kfs) for chs in bone_channels.values()
                for kfs in chs.values()
            ),
            animation_type=anim_type,
        )

        c0_errors_rot = []
        c0_errors_pos = []
        c1_errors_rot = []
        c1_errors_pos = []
        c2_errors_rot = []  # v13

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

                # Velocity and acceleration estimation using resampling
                if len(keyframes) >= 2 and duration > 0:
                    n_s = min(120, max(20, int(duration * 30)))
                    s_dt = duration / n_s
                    s_times = [i * s_dt for i in range(n_s + 1)]
                    # v13: Use periodic resampling for loop animations
                    s_data = CatmullRomEvaluator.resample_channel(
                        keyframes, s_times, "catmullrom", periodic=True
                    )
                    if len(s_data) >= 5:
                        # 3-point forward/backward difference for velocity
                        v0 = (-3*s_data[0][1] + 4*s_data[1][1] - s_data[2][1]) / (2*s_dt)
                        vT = (3*s_data[-1][1] - 4*s_data[-2][1] + s_data[-3][1]) / (2*s_dt)
                        c1_err = abs(vT - v0)
                        if is_rotation:
                            c1_errors_rot.append(c1_err)
                        else:
                            c1_errors_pos.append(c1_err)

                        # v13: Acceleration estimation
                        if len(s_data) >= 7:
                            a0 = (s_data[2][1] - 2*s_data[1][1] + s_data[0][1]) / (s_dt * s_dt)
                            aT = (s_data[-1][1] - 2*s_data[-2][1] + s_data[-3][1]) / (s_dt * s_dt)
                            c2_err = abs(aT - a0)
                            if is_rotation:
                                c2_errors_rot.append(c2_err)

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

        # v13: C2 statistics
        if c2_errors_rot:
            report.c2_max_error_rot = max(c2_errors_rot)
            report.c2_avg_error_rot = sum(c2_errors_rot) / len(c2_errors_rot)
            report.c2_perfect = report.c2_avg_error_rot < self.config.c2_accel_threshold_rot

        # Quality assessment
        report.c0_perfect = report.c0_max_error_rot < self.config.c0_snap_threshold_rot and \
                            report.c0_max_error_pos < self.config.c0_snap_threshold_pos
        report.c1_perfect = report.c1_avg_error_rot < self.config.c1_quality_threshold_rot and \
                            report.c1_avg_error_pos < self.config.c1_quality_threshold_pos

        # Compute quality score (0-100)
        score = 100.0
        if not report.c0_perfect:
            score -= min(30, report.c0_max_error_rot * 5 + report.c0_max_error_pos * 30)
        if not report.c1_perfect:
            c1_rot_penalty = min(25, report.c1_avg_error_rot * 1.5)
            c1_pos_penalty = min(15, report.c1_avg_error_pos * 5)
            score -= c1_rot_penalty + c1_pos_penalty
        # v13: C2 penalty
        if not report.c2_perfect and c2_errors_rot:
            c2_penalty = min(10, report.c2_avg_error_rot * 0.01)
            score -= c2_penalty

        report.quality_score = max(0.0, min(100.0, score))

        # Generate warnings/errors
        if report.c0_max_error_rot > self.config.quality_error_threshold:
            report.errors.append(
                f"C0 rotation error too large: {report.c0_max_error_rot:.3f} deg "
                f"(threshold: {self.config.quality_error_threshold} deg)"
            )
        elif report.c0_max_error_rot > self.config.quality_warning_threshold:
            report.warnings.append(
                f"C0 rotation error: {report.c0_max_error_rot:.3f} deg"
            )

        if not report.c1_perfect:
            report.warnings.append(
                f"C1 velocity mismatch: rot={report.c1_max_error_rot:.2f} deg/s, "
                f"pos={report.c1_max_error_pos:.3f}px/s"
            )

        # v13: C2 warning
        if not report.c2_perfect and c2_errors_rot:
            report.warnings.append(
                f"C2 acceleration mismatch: rot={report.c2_max_error_rot:.2f} deg/s^2"
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
      4. v13: Upsample sparse walk animations
      5. Enforce C1+C2 continuity at loop boundaries
      6. Simplify keyframes (animation-type-aware)
      7. Build GeckoLib .animation.json
      8. Generate quality report

    v13 Improvements:
      - Fixed name normalization double-namespace bug
      - Walk animation upsampling for sparse keyframes
      - Periodic boundary conditions in Catmull-Rom resampling
      - C2 acceleration continuity enforcement
      - Walk-specific period detection heuristics
      - Smart duplicate merging with aliases
      - Animation-type-aware DP epsilon
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
            'c2_perfect_count': 0,  # v13
            'duration_adjustments': [],
            'skipped_empty': extracted.get('skipped_empty', []),
            'deduplicated': extracted.get('deduplicated', []),
            'duplicate_aliases': extracted.get('duplicate_aliases', {}),  # v13
            'name_normalizations': [],
            'walk_upsampled': [],  # v13
        }

        for anim_name, anim_data in extracted['animations'].items():
            bone_channels = anim_data['bone_channels']
            current_duration = anim_data['length']
            loop_mode = anim_data['loop']
            interpolation = anim_data['interpolation']

            # v13: Classify animation type
            anim_type = classify_animation_type(anim_name)

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
                    bone_channels, current_duration, interpolation,
                    anim_name=anim_name  # v13: pass name for type-specific heuristics
                )
                current_c0 = loop_diag.get('current_c0_error', float('inf'))
                best_c0 = loop_diag.get('best_c0_error', float('inf'))
                method = loop_diag.get('method', 'none')

                should_change = False
                if method in ('search_optimal', 'search_early_exit_good_enough') and current_c0 > 0.5:
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

            # v13 Step 4: Walk upsampling for sparse animations
            if (loop_mode == "loop" and
                anim_type == 'walk' and
                self.config.enable_walk_upsampling and
                current_duration > 0):
                # Check if any channel has sparse keyframes
                min_kf_per_channel = float('inf')
                for chs in bone_channels.values():
                    for kfs in chs.values():
                        min_kf_per_channel = min(min_kf_per_channel, len(kfs))

                if min_kf_per_channel <= self.config.walk_upsample_max_kf and min_kf_per_channel >= 2:
                    bone_channels = self._upsample_walk_animation(
                        bone_channels, current_duration, interpolation
                    )
                    stats['walk_upsampled'].append(anim_name)

            # Step 5: C1+C2 continuity enforcement for loop animations only
            if loop_mode == "loop":
                bone_channels = self.c1_enforcer.enforce(bone_channels, current_duration, interpolation)

            # Step 6: Build GeckoLib JSON (v13: with animation type)
            anim_json = self.json_builder.build(
                anim_name, loop_mode, bone_channels, current_duration,
                animation_type=anim_type  # v13
            )
            all_animations[anim_name] = anim_json

            # Step 7: Quality report
            qreport = self.quality_reporter.report(anim_name, bone_channels, current_duration)
            quality_reports[anim_name] = qreport

            if qreport.c0_perfect:
                stats['c0_perfect_count'] += 1
            if qreport.c1_perfect:
                stats['c1_perfect_count'] += 1
            if qreport.c2_perfect:
                stats['c2_perfect_count'] += 1

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

    def _upsample_walk_animation(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        interpolation: str
    ) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
        """v13: Upsample sparse walk animations using catmullrom with periodic boundaries.

        For walk animations with few keyframes, resample at 30fps using
        periodic catmullrom to create smooth playback.

        Args:
            bone_channels: {bone: {channel: [(t, v), ...]}}
            duration: Animation duration
            interpolation: Interpolation type

        Returns:
            Upsampled bone_channels.
        """
        target_fps = self.config.walk_upsample_fps
        n_frames = max(int(duration * target_fps), 10)
        dt = duration / n_frames
        target_times = [i * dt for i in range(n_frames + 1)]

        result = {}
        for bone_name, channels in bone_channels.items():
            result[bone_name] = {}
            for channel, keyframes in channels.items():
                if len(keyframes) < 2:
                    result[bone_name][channel] = keyframes
                    continue
                # Resample with periodic boundaries
                upsampled = CatmullRomEvaluator.resample_channel(
                    keyframes, target_times, interpolation, periodic=True
                )
                # Ensure first and last values match for periodicity
                if upsampled:
                    upsampled[-1] = (duration, upsampled[0][1])
                result[bone_name][channel] = upsampled

        return result

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
    print("  Universal BBModel Animation Converter (v13)")
    print("  .bbmodel -> .animation.json with C1+C2 Continuity")
    print("  GeckoLib Format for MC 1.20.1 Forge Mod Development")
    print("  [FIXED] Hermite basis with linear parameter (no smootherstep warp)")
    print("  [v13] Quintic Hermite C2 acceleration matching")
    print("  [v13] Periodic boundary Catmull-Rom for loop animations")
    print("  [v13] Walk upsampling + walk period heuristics")
    print("  [v13] Smart duplicate merging with aliases")
    print("  [v13] Animation-type-aware DP epsilon")
    print("  [v13] Fixed name normalization double-namespace bug")
    print("=" * 70)
    print()

    cfg = config or ConverterConfig()
    converter = BBModelAnimationConverter(cfg)

    # Import geo converter
    try:
        from bbmodel_to_geo import BBModelToGeo
        geo_converter = BBModelToGeo()
    except ImportError:
        geo_converter = None
        print("  WARNING: bbmodel_to_geo not found, skipping geo conversion")

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
    print(f"  C2 enforcement: {'ON' if cfg.enable_c2_enforcement else 'OFF'}")
    print(f"  Duration optimization: {'ON' if cfg.enable_duration_optimization else 'OFF'}")
    print(f"  Autocorrelation: {'ON' if cfg.autocorrelation_enabled else 'OFF'}")
    print(f"  Walk period heuristic: {'ON' if cfg.walk_period_heuristic else 'OFF'}")
    print(f"  Walk upsampling: {'ON' if cfg.enable_walk_upsampling else 'OFF'}")
    print(f"  Blend window: {cfg.blend_window_ratio*100:.0f}% per side (max {cfg.max_blend_window}s)")
    print(f"  C2 blend window: {cfg.c2_blend_window_ratio*100:.0f}% per side")
    print(f"  DP epsilon: rot={cfg.dp_epsilon_rotation} deg, pos={cfg.dp_epsilon_position}px")
    print(f"  DP multipliers: idle={cfg.dp_epsilon_idle_multiplier}x, "
          f"attack={cfg.dp_epsilon_attack_multiplier}x, walk={cfg.dp_epsilon_walk_multiplier}x")
    print(f"  Skip empty: {'ON' if cfg.skip_empty_animations else 'OFF'}")
    print(f"  Deduplicate (case-insensitive): {'ON' if cfg.deduplicate_case_insensitive else 'OFF'}")
    print(f"  Keep duplicate aliases: {'ON' if cfg.keep_duplicate_aliases else 'OFF'}")
    print(f"  Name normalization: {'ON' if cfg.normalize_animation_names else 'OFF'}")
    print()

    total_anims = 0
    total_keyframes = 0
    total_c0_perfect = 0
    total_c1_perfect = 0
    total_c2_perfect = 0
    total_no_anim = 0
    total_skipped_empty = 0
    total_deduplicated = 0
    total_walk_upsampled = 0
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
        geo_ok = "-"
        if geo_converter:
            try:
                geo_result = geo_converter.convert_bbmodel(bbmodel_path, out_dir)
                geo_ok = "+" if geo_result.get('success') else "-"
            except Exception:
                geo_ok = "-"

        # Convert animations
        anim_output_path = os.path.join(out_dir, f"{name}.animation.json")
        if os.path.exists(anim_output_path):
            os.remove(anim_output_path)

        try:
            result = converter.convert_file(bbmodel_path, anim_output_path)
            stats = result['stats']

            anim_count = stats['total_animations']
            kf_count = stats['total_keyframes']
            c0_ok = stats['c0_perfect_count']
            c1_ok = stats['c1_perfect_count']
            c2_ok = stats.get('c2_perfect_count', 0)
            dur_adj = len(stats['duration_adjustments'])
            skipped = len(stats.get('skipped_empty', []))
            deduped = len(stats.get('deduplicated', []))
            walk_up = len(stats.get('walk_upsampled', []))

            total_skipped_empty += skipped
            total_deduplicated += deduped
            total_walk_upsampled += walk_up

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
                if walk_up:
                    extras += f" walk_up={walk_up}"
                print(f"{geo_ok} anims={anim_count} kf={kf_count} "
                      f"C0={c0_ok}/{anim_count} C1={c1_ok}/{anim_count} C2={c2_ok}/{anim_count}"
                      f"{extras}")

            total_anims += anim_count
            total_keyframes += kf_count
            total_c0_perfect += c0_ok
            total_c1_perfect += c1_ok
            total_c2_perfect += c2_ok

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
    print("  CONVERSION SUMMARY (v13)")
    print("=" * 70)
    print(f"  Total models:            {len(bbmodel_files)}")
    print(f"  Models with animations:  {len(bbmodel_files) - total_no_anim}")
    print(f"  Static models:           {total_no_anim}")
    print(f"  Total animations:        {total_anims}")
    print(f"  Total keyframes:         {total_keyframes:,}")
    print(f"  C0 perfect:              {total_c0_perfect}/{total_anims} ({100*total_c0_perfect/max(total_anims,1):.1f}%)")
    print(f"  C1 good (P90):           {total_c1_perfect}/{total_anims} ({100*total_c1_perfect/max(total_anims,1):.1f}%)")
    print(f"  C2 good:                 {total_c2_perfect}/{total_anims} ({100*total_c2_perfect/max(total_anims,1):.1f}%)")
    print(f"  Empty skipped:           {total_skipped_empty}")
    print(f"  Duplicates merged:       {total_deduplicated}")
    print(f"  Walk upsampled:          {total_walk_upsampled}")
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
    print("  DONE - Universal BBModel Animation Converter (v13)")
    print("=" * 70)

    return len(all_errors) == 0


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Universal BBModel Animation Converter with C1+C2 Continuity (v13)"
    )
    parser.add_argument("--input", required=True,
                        help="Input directory with .bbmodel files")
    parser.add_argument("--output", required=True,
                        help="Output directory for .animation.json + .geo.json + .png")
    parser.add_argument("--no-c1", action="store_true",
                        help="Disable C1 continuity enforcement")
    parser.add_argument("--no-c2", action="store_true",
                        help="Disable C2 continuity enforcement (v13)")
    parser.add_argument("--no-duration-opt", action="store_true",
                        help="Disable duration optimization")
    parser.add_argument("--no-autocorr", action="store_true",
                        help="Disable autocorrelation period detection")
    parser.add_argument("--no-walk-heuristic", action="store_true",
                        help="Disable walk period heuristic (v13)")
    parser.add_argument("--no-walk-upsample", action="store_true",
                        help="Disable walk animation upsampling (v13)")
    parser.add_argument("--blend-ratio", type=float, default=0.10,
                        help="C1 blend window ratio per side (default: 0.10)")
    parser.add_argument("--c2-blend-ratio", type=float, default=0.15,
                        help="C2 blend window ratio per side (default: 0.15)")
    parser.add_argument("--dp-rot", type=float, default=0.05,
                        help="DP epsilon for rotation (degrees, default: 0.05)")
    parser.add_argument("--dp-pos", type=float, default=0.008,
                        help="DP epsilon for position (pixels, default: 0.008)")
    parser.add_argument("--no-skip-empty", action="store_true",
                        help="Don't skip empty animations")
    parser.add_argument("--no-dedup", action="store_true",
                        help="Disable case-insensitive deduplication")
    parser.add_argument("--no-aliases", action="store_true",
                        help="Don't keep duplicate names as aliases (v13)")
    parser.add_argument("--no-name-norm", action="store_true",
                        help="Disable animation name normalization")
    parser.add_argument("--namespace", type=str, default="",
                        help="Namespace for animation name normalization")
    args = parser.parse_args()

    config = ConverterConfig(
        enable_c1_enforcement=not args.no_c1,
        enable_c2_enforcement=not args.no_c2,
        enable_duration_optimization=not args.no_duration_opt,
        autocorrelation_enabled=not args.no_autocorr,
        walk_period_heuristic=not args.no_walk_heuristic,
        enable_walk_upsampling=not args.no_walk_upsample,
        blend_window_ratio=args.blend_ratio,
        c2_blend_window_ratio=args.c2_blend_ratio,
        dp_epsilon_rotation=args.dp_rot,
        dp_epsilon_position=args.dp_pos,
        skip_empty_animations=not args.no_skip_empty,
        deduplicate_case_insensitive=not args.no_dedup,
        keep_duplicate_aliases=not args.no_aliases,
        normalize_animation_names=not args.no_name_norm,
        animation_namespace=args.namespace,
    )

    success = batch_convert(args.input, args.output, config)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
