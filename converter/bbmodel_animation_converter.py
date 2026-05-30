#!/usr/bin/env python3
"""
BBModelAnimationConverter - Universal Animation Converter
=========================================================
Converts Blockbench .bbmodel animation keyframes to GeckoLib .animation.json
format with automatic loop continuity enforcement, C1 velocity matching,
duration optimization, and comprehensive quality feedback.

Key Features:
  - Direct .bbmodel → .animation.json conversion (no Java source needed)
  - C0 + C1 continuity enforcement at loop boundaries (fixes bounce-back/stutter)
  - Automatic loop duration detection and optimization
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
    blend_window_ratio: float = 0.08        # 8% of duration
    max_blend_window: float = 0.2           # max seconds
    velocity_match_threshold_rot: float = 2.0   # degrees/s
    velocity_match_threshold_pos: float = 0.2   # pixels/s
    c0_snap_threshold_rot: float = 0.3     # degrees
    c0_snap_threshold_pos: float = 0.03    # pixels

    # --- Duration Optimization ---
    enable_duration_optimization: bool = True
    duration_search_step: float = 0.01      # seconds
    phase_error_tolerance: float = 0.02     # radians

    # --- Simplification ---
    dp_epsilon_rotation: float = 0.08       # degrees
    dp_epsilon_position: float = 0.01       # pixels

    # --- Resampling ---
    resample_rate: float = 120.0            # Hz for catmullrom evaluation

    # --- Output ---
    keyframe_precision: int = 4             # decimal places for time
    value_precision: int = 6                # decimal places for values
    filter_zero_threshold: float = 0.001    # skip channels with only tiny values

    # --- Quality ---
    quality_warning_threshold: float = 0.5  # warn if C0 error > this (degrees/pixels)
    quality_error_threshold: float = 2.0    # error if C0 error > this


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
    - C0: Position at start ≈ position at end (for all channels)
    - C1: Velocity at start ≈ velocity at end (for all channels)

    Uses high-rate resampling of the existing keyframes to evaluate
    continuity at candidate durations.
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

        # Evaluate current duration first
        c0_err, c1_err = self._evaluate_continuity(resampled, current_duration, sample_rate)
        diagnostics['current_c0_error'] = c0_err
        diagnostics['current_c1_error'] = c1_err

        # If current duration is already good, keep it
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
        periods = self._detect_periods(resampled, sample_rate)
        for period in periods:
            for n in range(1, 30):
                T = n * period
                if cfg.min_loop_duration <= T <= cfg.max_loop_duration:
                    candidates.append(T)

        # Method 3: Fine-grained search
        T = cfg.min_loop_duration
        while T <= min(test_duration, cfg.max_loop_duration):
            candidates.append(T)
            T += cfg.duration_search_step

        # Remove duplicates and sort
        candidates = sorted(set(candidates))
        diagnostics['candidates_tested'] = len(candidates)

        for T in candidates:
            c0, c1 = self._evaluate_continuity(resampled, T, sample_rate)

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
                    # Half-periods from consecutive crossings
                    half_periods = [crossings[i + 1] - crossings[i]
                                   for i in range(len(crossings) - 1)]
                    # Full periods from every other crossing
                    full_periods = [crossings[i + 2] - crossings[i]
                                   for i in range(len(crossings) - 2)]

                    for p in full_periods:
                        if 0.1 < p < 20.0:
                            periods.append(p)

        # Cluster similar periods and return medians
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

        # Return median of each significant cluster
        result = []
        for cluster in clusters:
            if len(cluster) >= 2:
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

    Solution:
      Use cubic Hermite interpolation in a blend window near the loop
      boundary to smoothly transition from the original end state to
      match the start state's position AND velocity.

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
        """Apply C1 continuity enforcement to all channels.

        Strategy:
          1. Resample each channel at high rate using catmullrom/linear interpolation
          2. Compute start/end velocity from resampled data
          3. If velocity mismatch detected, apply Hermite blend in the blend window
          4. Replace original keyframes with resampled + blended data

        This ensures sufficient data points for smooth blending even on
        short animations with few keyframes.

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

                # Use multiple points for stable velocity estimation
                # 5-point stencil for numerical derivative
                n_vel = min(5, len(resampled) - 1)
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

                # Step 3: Apply Hermite blend to the resampled data
                # Compute blend window - ensure at least 25% of duration or enough samples
                w_ratio = max(cfg.blend_window_ratio, 0.15)  # at least 15% for short anims
                w = min(duration * w_ratio, cfg.max_blend_window)
                # Ensure blend window has at least 10 resampled points
                min_samples = 10
                w = max(w, min_samples * resample_dt)
                blend_start_time = max(0, duration - w)

                # Find resampled points in blend window
                blend_start_idx = 0
                for i, (t, v) in enumerate(resampled):
                    if t >= blend_start_time:
                        blend_start_idx = i
                        break

                if blend_start_idx < 1 or blend_start_idx >= len(resampled) - 1:
                    continue

                # Get blend boundary values
                p_blend_start = resampled[blend_start_idx][1]
                t_blend_start = resampled[blend_start_idx][0]

                # Velocity at blend start via central difference
                v_blend_start = (
                    (resampled[blend_start_idx + 1][1] -
                     resampled[blend_start_idx - 1][1]) /
                    (resampled[blend_start_idx + 1][0] -
                     resampled[blend_start_idx - 1][0])
                )

                # Target: position at end = p0, velocity at end = v0
                p_blend_end = p0
                v_blend_end = v0

                w_actual = duration - t_blend_start
                if w_actual < 1e-12:
                    continue

                # Apply Hermite blend to resampled data in window
                for i in range(blend_start_idx, len(resampled)):
                    t, v = resampled[i]
                    s = (t - t_blend_start) / w_actual  # normalized 0→1
                    s = max(0.0, min(1.0, s))

                    # Smootherstep for natural acceleration
                    s_smooth = s * s * s * (s * (6 * s - 15) + 10)

                    # Hermite basis functions
                    h00 = 2 * s_smooth ** 3 - 3 * s_smooth ** 2 + 1
                    h10 = s_smooth ** 3 - 2 * s_smooth ** 2 + s_smooth
                    h01 = -2 * s_smooth ** 3 + 3 * s_smooth ** 2
                    h11 = s_smooth ** 3 - s_smooth ** 2

                    new_val = (h00 * p_blend_start +
                               h10 * w_actual * v_blend_start +
                               h01 * p_blend_end +
                               h11 * w_actual * v_blend_end)

                    resampled[i] = (t, new_val)

                # Step 4: Replace original keyframes with resampled + blended data
                # Keep original keyframes outside the blend window
                # Inside blend window, use resampled data for smooth C1 transition
                new_keyframes = []

                # Add original keyframes before blend window
                for t, v in keyframes:
                    if t < blend_start_time - 1e-8:
                        new_keyframes.append((t, v))

                # In the blend window, add resampled points at a density that
                # captures the Hermite blend curve properly.
                # Use enough points to represent the blend curve (typically 6-10).
                # Match the original keyframe density to avoid over-densification.
                n_blend_target = 8  # enough for smooth Hermite representation
                blend_interval = w_actual / max(n_blend_target - 1, 1)
                # Don't add points more densely than 1/3 of the resample rate
                blend_interval = max(blend_interval, resample_dt * 3)

                last_added_time = blend_start_time - blend_interval
                for i in range(blend_start_idx, len(resampled)):
                    t, v = resampled[i]
                    if t - last_added_time >= blend_interval - 1e-8 or i == blend_start_idx or t >= duration - 1e-8:
                        new_keyframes.append((t, v))
                        last_added_time = t

                # Ensure last keyframe is exactly at duration with value = p0
                if new_keyframes:
                    new_keyframes[-1] = (duration, p0)
                else:
                    new_keyframes.append((0.0, p0))
                    new_keyframes.append((duration, p0))

                # Ensure first keyframe value matches
                if abs(new_keyframes[0][1] - p0) < c0_thresh and abs(new_keyframes[0][1] - keyframes[0][1]) > 1e-8:
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
# BBModel Animation Extractor
# ============================================================================

class BBModelAnimationExtractor:
    """Extracts animations from .bbmodel files and converts to internal format.

    Handles the bbmodel keyframe format:
      - Per-bone animators with rotation/position/scale channels
      - Each keyframe has time, channel, interpolation, data_points with x/y/z
      - Supports linear and catmullrom interpolation
    """

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
                    }
                }
            }
        """
        with open(bbmodel_path, 'r', encoding='utf-8') as f:
            bb = json.load(f)

        model_name = bb.get('model_identifier', bb.get('name', 'unknown'))
        animations = {}

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

            animations[anim_name] = {
                'loop': anim.get('loop', 'hold_on_last_frame'),
                'length': anim.get('length', 0.0),
                'snapping': anim.get('snapping', 24),
                'bone_channels': bone_channels,
                'interpolation': dominant_interp,
            }

        return {
            'model_name': model_name,
            'animations': animations,
        }

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
        report.c1_perfect = report.c1_max_error_rot < self.config.velocity_match_threshold_rot and \
                            report.c1_max_error_pos < self.config.velocity_match_threshold_pos

        # Compute quality score (0-100)
        score = 100.0
        # Penalize C0 errors
        if not report.c0_perfect:
            score -= min(30, report.c0_max_error_rot * 10 + report.c0_max_error_pos * 20)
        # Penalize C1 errors
        if not report.c1_perfect:
            score -= min(30, report.c1_max_error_rot * 2 + report.c1_max_error_pos * 10)

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
      1. Extract animations from .bbmodel
      2. For loop animations: detect optimal loop duration
      3. Enforce C1 continuity at loop boundaries
      4. Simplify keyframes
      5. Build GeckoLib .animation.json
      6. Generate quality report
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()
        self.extractor = BBModelAnimationExtractor()
        self.loop_detector = AutoLoopDetector(self.config)
        self.c1_enforcer = C1ContinuityEnforcer(self.config)
        self.json_builder = GeckoLibJSONBuilder(self.config)
        self.quality_reporter = QualityReporter(self.config)

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
        # Step 1: Extract
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
        }

        for anim_name, anim_data in extracted['animations'].items():
            bone_channels = anim_data['bone_channels']
            current_duration = anim_data['length']
            loop_mode = anim_data['loop']
            interpolation = anim_data['interpolation']

            stats['total_animations'] += 1
            for chs in bone_channels.values():
                for kfs in chs.values():
                    stats['total_keyframes'] += len(kfs)

            # Step 2: Duration optimization for loop animations
            if loop_mode == "loop" and self.config.enable_duration_optimization:
                optimal_duration, loop_diag = self.loop_detector.detect_optimal_duration(
                    bone_channels, current_duration, interpolation
                )
                if abs(optimal_duration - current_duration) > 0.01:
                    stats['duration_adjustments'].append({
                        'animation': anim_name,
                        'from': current_duration,
                        'to': optimal_duration,
                        'method': loop_diag.get('method', 'unknown'),
                    })
                    # Trim keyframes to new duration
                    bone_channels = self._trim_to_duration(bone_channels, optimal_duration)
                    current_duration = optimal_duration
            else:
                current_duration = anim_data['length']

            # Step 3: C1 continuity enforcement for loop animations
            if loop_mode == "loop":
                bone_channels = self.c1_enforcer.enforce(bone_channels, current_duration, interpolation)

            # Step 4: Build GeckoLib JSON
            anim_json = self.json_builder.build(
                anim_name, loop_mode, bone_channels, current_duration
            )
            all_animations[anim_name] = anim_json

            # Step 5: Quality report
            qreport = self.quality_reporter.report(anim_name, bone_channels, current_duration)
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
    print("  Universal BBModel Animation Converter")
    print("  .bbmodel → .animation.json with C1 Continuity")
    print("  GeckoLib Format for MC 1.20.1 Forge Mod Development")
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
    print(f"  Blend window: {cfg.blend_window_ratio*100:.0f}% (max {cfg.max_blend_window}s)")
    print(f"  DP epsilon: rot={cfg.dp_epsilon_rotation}°, pos={cfg.dp_epsilon_position}px")
    print()

    total_anims = 0
    total_keyframes = 0
    total_c0_perfect = 0
    total_c1_perfect = 0
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

        # Convert animations
        anim_output_path = os.path.join(out_dir, f"{name}.animation.json")
        try:
            result = converter.convert_file(bbmodel_path, anim_output_path)
            stats = result['stats']

            # Quality summary
            geo_ok = "✓" if geo_result.get('success') else "✗"
            anim_count = stats['total_animations']
            kf_count = stats['total_keyframes']
            c0_ok = stats['c0_perfect_count']
            c1_ok = stats['c1_perfect_count']
            dur_adj = len(stats['duration_adjustments'])

            print(f"{geo_ok} anims={anim_count} kf={kf_count} "
                  f"C0={c0_ok}/{anim_count} C1={c1_ok}/{anim_count}"
                  f"{' dur_adj=' + str(dur_adj) if dur_adj else ''}")

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
    print(f"  Total models:          {len(bbmodel_files)}")
    print(f"  Total animations:      {total_anims}")
    print(f"  Total keyframes:       {total_keyframes:,}")
    print(f"  C0 perfect:            {total_c0_perfect}/{total_anims} ({100*total_c0_perfect/max(total_anims,1):.1f}%)")
    print(f"  C1 perfect:            {total_c1_perfect}/{total_anims} ({100*total_c1_perfect/max(total_anims,1):.1f}%)")
    print(f"  Warnings:              {len(all_warnings)}")
    print(f"  Errors:                {len(all_errors)}")
    print(f"  Elapsed time:          {elapsed:.1f}s")
    print(f"  Output directory:      {output_dir}")

    if all_warnings:
        print(f"\n  Top warnings:")
        for w in all_warnings[:10]:
            print(f"    ⚠ {w}")
        if len(all_warnings) > 10:
            print(f"    ... and {len(all_warnings) - 10} more")

    if all_errors:
        print(f"\n  Errors:")
        for e in all_errors[:5]:
            print(f"    ✗ {e}")
        if len(all_errors) > 5:
            print(f"    ... and {len(all_errors) - 5} more")

    print()
    print("=" * 70)
    print("  DONE - Universal BBModel Animation Converter")
    print("=" * 70)

    return len(all_errors) == 0


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Universal BBModel Animation Converter with C1 Continuity"
    )
    parser.add_argument("--input", required=True,
                        help="Input directory with .bbmodel files")
    parser.add_argument("--output", required=True,
                        help="Output directory for .animation.json + .geo.json + .png")
    parser.add_argument("--no-c1", action="store_true",
                        help="Disable C1 continuity enforcement")
    parser.add_argument("--no-duration-opt", action="store_true",
                        help="Disable duration optimization")
    parser.add_argument("--blend-ratio", type=float, default=0.08,
                        help="C1 blend window ratio (default: 0.08)")
    parser.add_argument("--dp-rot", type=float, default=0.08,
                        help="DP epsilon for rotation (degrees, default: 0.08)")
    parser.add_argument("--dp-pos", type=float, default=0.01,
                        help="DP epsilon for position (pixels, default: 0.01)")
    args = parser.parse_args()

    config = ConverterConfig(
        enable_c1_enforcement=not args.no_c1,
        enable_duration_optimization=not args.no_duration_opt,
        blend_window_ratio=args.blend_ratio,
        dp_epsilon_rotation=args.dp_rot,
        dp_epsilon_position=args.dp_pos,
    )

    success = batch_convert(args.input, args.output, config)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
