#!/usr/bin/env python3
"""
UniversalAnimationConverter - Unified Animation Conversion Pipeline
====================================================================
A universal animation conversion pipeline for MinecraftModelMigrator-Pro that
eliminates code duplication between creature-specific generators and introduces
C1 continuity, auto loop detection, adaptive sampling, and smart duration
optimization.

Two input paths converge into a single unified pipeline:

  PATH A: Java Source → JavaAnimationParser → eval functions
  PATH B: User-provided eval function callbacks

Both paths feed into:
  FrequencyAnalyzer → SmartDurationOptimizer → AdaptiveSampler →
  C1ContinuityEnforcer → DouglasPeuckerSimplifier → GeckoLibJSONBuilder

Key Conversions:
  - M_MODEL = diag(1, -1, -1): rx stays, ry→-ry, rz→-rz for rotation
  - Position: ox stays, oy→-oy, oz→-oz
  - Radians to degrees for GeckoLib rotation output
  - Time in seconds (20 ticks per second in MC)

DO NOT MODIFY: core_math.py
"""

import math
import re
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Callable, Any

from core_math import convert_model_rot, rad_to_deg

# ============================================================================
# Constants
# ============================================================================

TICKS_PER_SECOND = 20.0
RAD_TO_DEG = 180.0 / math.pi


# ============================================================================
# Configuration Dataclasses
# ============================================================================

@dataclass
class ConverterConfig:
    """Master configuration for UniversalAnimationConverter.

    All parameters have sensible defaults; per-animation overrides are
    possible via AnimationStateConfig.
    """

    # --- Sampling ---
    base_sample_rate: float = 60.0          # Base fps
    min_sample_rate: float = 60.0
    max_sample_rate: float = 600.0
    nyquist_factor: float = 4.0             # Nyquist multiplier

    # --- Douglas-Peucker ---
    dp_epsilon_rotation: float = 0.08       # degrees
    dp_epsilon_position: float = 0.01       # pixels

    # --- Loop detection ---
    min_loop_duration: float = 2.0          # seconds
    max_loop_duration: float = 30.0         # seconds
    loop_position_tolerance: float = 0.002  # radians (rotation) or pixels (position)
    loop_velocity_tolerance: float = 0.01   # rad/s or pixels/s

    # --- C1 continuity ---
    blend_window_ratio: float = 0.05        # 5% of duration
    max_blend_window: float = 0.15          # max seconds
    velocity_match_threshold_rot: float = 0.5   # degrees/s
    velocity_match_threshold_pos: float = 0.05  # pixels/s

    # --- Duration optimization ---
    duration_search_step: float = 0.01      # seconds
    phase_error_tolerance: float = 0.01     # radians

    # --- Java parsing ---
    swing_limb_swing_amount: float = 0.5
    default_walk_speed_factor: float = 0.3

    # --- Output ---
    keyframe_precision: int = 4             # decimal places for time
    value_precision: int = 6                # decimal places for values
    filter_zero_threshold: float = 0.001    # skip channels with only tiny values


@dataclass
class AnimationStateConfig:
    """Per-animation-state configuration override.

    Any field set to None inherits from ConverterConfig defaults.
    """
    name: str                               # e.g., "idle", "attack", "fly"
    animation_name: str = ""                # e.g., "animation.model.idle"
    loop_mode: str = "loop"                 # "loop" or "hold_on_last_frame"
    eval_func: Optional[Callable] = None    # Callback: t_seconds -> Dict[bone, {rx,ry,rz,ox,oy,oz}]
    duration: Optional[float] = None        # None = auto-detect
    sample_rate: Optional[float] = None     # None = auto-adapt
    dp_epsilon: Optional[float] = None      # None = use global default
    force_recompute: bool = False


# ============================================================================
# Frequency Analysis
# ============================================================================

@dataclass
class FrequencyReport:
    """Result of frequency analysis on animation channels."""
    channel_frequencies: Dict[str, Dict[str, List[float]]]  # bone.channel -> [freq_hz, ...]
    max_frequency_hz: float
    recommended_sample_rate: float
    estimated_loop_periods: List[float]  # seconds, one per dominant frequency


class FrequencyAnalyzer:
    """FFT-based or zero-crossing frequency detection for animation channels.

    Takes sampled channel data (time, value pairs) already in output space
    (degrees for rotation) and determines dominant frequencies per channel.

    Uses numpy FFT if available, falls back to zero-crossing analysis.
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()
        self._has_numpy = False
        self._has_scipy = False
        try:
            import numpy
            self._has_numpy = True
        except ImportError:
            pass
        try:
            import scipy
            self._has_scipy = True
        except ImportError:
            pass

    def analyze(self, sampled_data: Dict[str, Dict[str, List[Tuple[float, float]]]]) -> FrequencyReport:
        """Analyze sampled channel data for dominant frequencies.

        Args:
            sampled_data: {bone: {channel: [(time, value), ...]}}
                          Values ALREADY in output space (degrees for rotation)

        Returns:
            FrequencyReport with dominant frequencies and recommended sample rate.
        """
        channel_freqs: Dict[str, Dict[str, List[float]]] = {}
        all_freqs: List[float] = []

        for bone_name, channels in sampled_data.items():
            channel_freqs[bone_name] = {}
            for channel, points in channels.items():
                if len(points) < 10:
                    channel_freqs[bone_name][channel] = [1.0]
                    all_freqs.append(1.0)
                    continue

                values = [v for t, v in points]
                # Estimate sample rate from the data
                if len(points) >= 2:
                    dt = points[1][0] - points[0][0]
                    sample_rate = 1.0 / dt if dt > 0 else 60.0
                else:
                    sample_rate = 60.0

                freqs = self.detect_dominant_frequencies(values, sample_rate)
                channel_freqs[bone_name][channel] = freqs
                all_freqs.extend(freqs)

        max_freq = max(all_freqs) if all_freqs else 1.0
        recommended_rate = max(
            self.config.nyquist_factor * 2 * max_freq,
            self.config.base_sample_rate
        )
        recommended_rate = max(self.config.min_sample_rate,
                               min(self.config.max_sample_rate, recommended_rate))

        # Compute estimated loop periods
        periods = []
        for f in sorted(set(all_freqs)):
            if f > 0.01:
                periods.append(1.0 / f)

        return FrequencyReport(
            channel_frequencies=channel_freqs,
            max_frequency_hz=max_freq,
            recommended_sample_rate=recommended_rate,
            estimated_loop_periods=sorted(periods)
        )

    def detect_dominant_frequencies(self, channel_data: List[float],
                                     sample_rate: float = 60.0,
                                     min_freq: float = 0.1) -> List[float]:
        """Detect dominant frequencies in a channel signal.

        Args:
            channel_data: Time-series values [v0, v1, ..., vN]
            sample_rate: Sampling rate in Hz
            min_freq: Minimum frequency to detect

        Returns:
            List of dominant frequencies in Hz.
        """
        if self._has_numpy:
            return self._detect_fft(channel_data, sample_rate, min_freq)
        else:
            return self._detect_zero_crossing(channel_data, sample_rate, min_freq)

    def _detect_fft(self, values: List[float], sample_rate: float,
                     min_freq: float) -> List[float]:
        """FFT-based frequency detection using numpy."""
        try:
            import numpy as np

            arr = np.array(values, dtype=float)
            # Remove DC offset
            arr = arr - np.mean(arr)

            if np.max(np.abs(arr)) < 1e-10:
                return [1.0]

            n = len(arr)
            # Apply Hanning window to reduce spectral leakage
            window = np.hanning(n)
            arr = arr * window

            fft_vals = np.fft.rfft(arr)
            magnitudes = np.abs(fft_vals)

            # Frequency bins
            freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)

            # Find peaks (skip DC at index 0)
            dominant_freqs = []
            if len(magnitudes) > 2:
                # Simple peak detection: local maxima above threshold
                threshold = np.max(magnitudes[1:]) * 0.1  # 10% of max
                for i in range(1, len(magnitudes) - 1):
                    if (magnitudes[i] > magnitudes[i - 1] and
                            magnitudes[i] > magnitudes[i + 1] and
                            magnitudes[i] > threshold and
                            freqs[i] >= min_freq):
                        dominant_freqs.append(float(freqs[i]))

            if not dominant_freqs:
                # Fall back to the single strongest frequency
                if len(magnitudes) > 1:
                    idx = int(np.argmax(magnitudes[1:])) + 1
                    if freqs[idx] >= min_freq:
                        dominant_freqs.append(float(freqs[idx]))

            return dominant_freqs if dominant_freqs else [1.0]

        except Exception:
            return self._detect_zero_crossing(values, sample_rate, min_freq)

    def _detect_zero_crossing(self, values: List[float], sample_rate: float,
                               min_freq: float) -> List[float]:
        """Zero-crossing and peak-based frequency detection (no numpy required)."""
        if len(values) < 10:
            return [1.0]

        # Remove DC offset
        mean_val = sum(values) / len(values)
        centered = [v - mean_val for v in values]

        # Method 1: Zero-crossing counting
        crossings = 0
        for i in range(1, len(centered)):
            if centered[i - 1] * centered[i] < 0:
                crossings += 1

        duration = len(values) / sample_rate

        if crossings < 2:
            # Check for very weak oscillation
            peak_to_peak = max(values) - min(values)
            if peak_to_peak < 1e-6:
                return [1.0]
            return [1.0]

        dominant_freq = crossings / (2 * duration)

        # Method 2: Peak detection
        peaks = []
        for i in range(1, len(centered) - 1):
            if centered[i] > centered[i - 1] and centered[i] > centered[i + 1]:
                peaks.append(i)

        if len(peaks) >= 2:
            peak_intervals = [peaks[i + 1] - peaks[i] for i in range(min(len(peaks) - 1, 10))]
            avg_interval = sum(peak_intervals) / len(peak_intervals)
            freq_from_peaks = sample_rate / avg_interval if avg_interval > 0 else dominant_freq

            result = sorted(set([
                f for f in [dominant_freq, freq_from_peaks]
                if f >= min_freq
            ]), reverse=True)
            return result if result else [1.0]

        return [dominant_freq] if dominant_freq >= min_freq else [1.0]


# ============================================================================
# Auto Loop Detection
# ============================================================================

class AutoLoopDetector:
    """Finds optimal loop duration where ALL channels have C1 continuity.

    Combines two strategies:
    1. Frequency analysis for candidate periods
    2. Empirical search for shortest T with position+velocity match
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()
        self.frequency_analyzer = FrequencyAnalyzer(self.config)

    def find_loop_duration(self, eval_func: Callable, config: ConverterConfig = None) -> float:
        """Find the optimal loop duration for seamless animation looping.

        Args:
            eval_func: Animation evaluator, t(seconds) -> bone->channel->value
            config: Optional config override

        Returns:
            Optimal loop duration in seconds.
        """
        cfg = config or self.config

        # Phase 1: Sample at high rate for analysis
        test_duration = min(10.0, cfg.max_loop_duration)
        high_rate = 300.0
        n_samples = int(test_duration * high_rate)
        dt = test_duration / n_samples

        all_data: Dict[str, List[Tuple[float, float]]] = {}
        for i in range(n_samples + 1):
            t = i * dt
            try:
                bone_values = eval_func(t)
            except Exception:
                continue
            for bone_name, channels in bone_values.items():
                for channel, value in channels.items():
                    key = f"{bone_name}.{channel}"
                    if key not in all_data:
                        all_data[key] = []
                    all_data[key].append((t, value))

        if not all_data:
            return cfg.min_loop_duration

        # Phase 2: Find candidate durations from frequency analysis
        candidate_periods = set()
        for key, data in all_data.items():
            values = [v for t, v in data]
            freqs = self.frequency_analyzer.detect_dominant_frequencies(values, high_rate)
            for f in freqs:
                if f > 0.01:
                    candidate_periods.add(1.0 / f)

        # Phase 3: Generate candidate durations
        candidates = []

        # Multiples of candidate periods
        for period in sorted(candidate_periods):
            for n in range(1, 30):
                T = n * period
                if T < cfg.min_loop_duration:
                    continue
                if T > cfg.max_loop_duration:
                    break
                candidates.append(T)

        # Incremental search
        T = cfg.min_loop_duration
        while T <= cfg.max_loop_duration:
            candidates.append(T)
            T += cfg.duration_search_step

        # Remove duplicates and sort
        candidates = sorted(set(candidates))

        # Phase 4: Evaluate each candidate
        best_duration = None
        best_error = float('inf')

        for T in candidates:
            total_pos_error = 0.0
            total_vel_error = 0.0
            count = 0

            for key, data in all_data.items():
                # Find value at t=T (interpolate)
                val_T = self._interpolate_value(data, T)
                val_0 = data[0][1]

                # Find velocity at t=T and t=0
                vel_T = self._interpolate_velocity(data, T, dt)
                if len(data) >= 2:
                    vel_0 = (data[1][1] - data[0][1]) / (data[1][0] - data[0][0])
                else:
                    vel_0 = 0.0

                total_pos_error += abs(val_T - val_0)
                total_vel_error += abs(vel_T - vel_0)
                count += 1

            if count == 0:
                continue

            avg_pos_error = total_pos_error / count
            avg_vel_error = total_vel_error / count

            # Both position AND velocity must be close
            if (avg_pos_error < cfg.loop_position_tolerance and
                    avg_vel_error < cfg.loop_velocity_tolerance):
                if best_duration is None or T < best_duration:
                    best_duration = T
                    best_error = avg_pos_error + avg_vel_error
                    break  # Take the first good match (sorted shortest first)

        if best_duration is None:
            # Fall back: find duration with minimum combined error
            best_duration = cfg.min_loop_duration
            best_combined = float('inf')
            for T in candidates:
                total_error = 0.0
                count = 0
                for key, data in all_data.items():
                    val_T = self._interpolate_value(data, T)
                    val_0 = data[0][1]
                    total_error += abs(val_T - val_0)
                    count += 1
                avg = total_error / max(count, 1)
                if avg < best_combined:
                    best_combined = avg
                    best_duration = T

        return round(best_duration, 4)

    @staticmethod
    def _interpolate_value(data: List[Tuple[float, float]], t: float) -> float:
        """Linearly interpolate value at time t from sampled data."""
        if t <= data[0][0]:
            return data[0][1]
        if t >= data[-1][0]:
            return data[-1][1]

        for i in range(len(data) - 1):
            if data[i][0] <= t <= data[i + 1][0]:
                t0, v0 = data[i]
                t1, v1 = data[i + 1]
                if t1 == t0:
                    return v0
                alpha = (t - t0) / (t1 - t0)
                return v0 + alpha * (v1 - v0)

        return data[-1][1]

    @staticmethod
    def _interpolate_velocity(data: List[Tuple[float, float]], t: float,
                               dt: float) -> float:
        """Compute velocity at time t via finite differences."""
        # Find surrounding samples
        idx_before = -1
        idx_after = -1
        for i in range(len(data)):
            if data[i][0] <= t:
                idx_before = i
            if data[i][0] >= t and idx_after == -1:
                idx_after = i

        if idx_before < 0:
            idx_before = 0
        if idx_after < 0:
            idx_after = len(data) - 1

        if idx_before == idx_after:
            if idx_before > 0:
                idx_before -= 1
            elif idx_after < len(data) - 1:
                idx_after += 1

        t0, v0 = data[idx_before]
        t1, v1 = data[idx_after]

        if abs(t1 - t0) < 1e-12:
            return 0.0

        return (v1 - v0) / (t1 - t0)


# ============================================================================
# C1 Continuity Enforcer
# ============================================================================

class C1ContinuityEnforcer:
    """Enforces C1 (velocity) continuity at loop boundaries.

    Problem:
      After duration alignment, position at t=0 and t=T approximately match
      (C0 continuity). But velocity (derivative) may differ, causing a
      visible "stutter" or "bounce" at the loop point.

    Solution:
      Use cubic Hermite interpolation in a blend window near the loop boundary
      to smoothly transition from the original end velocity to the start velocity.
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()

    def enforce(self, sampled_data: Dict, duration: float,
                config: ConverterConfig = None) -> Dict:
        """Apply C1 continuity enforcement to sampled animation data.

        Args:
            sampled_data: {bone: {channel: [(t, v), ...]}}
                          Values already in output units (degrees/pixels)
            duration: Loop duration in seconds
            config: Optional config override

        Returns:
            Modified sampled_data with C1 continuity enforced.
        """
        cfg = config or self.config

        for bone_name, channels in sampled_data.items():
            for channel, keyframes in channels.items():
                if len(keyframes) < 3:
                    continue

                # Get boundary values
                p0 = keyframes[0][1]    # start position
                pT = keyframes[-1][1]   # end position

                # Compute velocities via finite differences
                dt_start = keyframes[1][0] - keyframes[0][0]
                dt_end = keyframes[-1][0] - keyframes[-2][0]

                if dt_start < 1e-12 or dt_end < 1e-12:
                    continue

                v0 = (keyframes[1][1] - keyframes[0][1]) / dt_start
                vT = (keyframes[-1][1] - keyframes[-2][1]) / dt_end

                # Determine thresholds based on channel type
                is_rotation = channel.startswith('r')
                pos_thresh = (cfg.velocity_match_threshold_rot if is_rotation
                              else cfg.velocity_match_threshold_pos)
                vel_thresh = pos_thresh * 10  # velocity threshold = 10× position threshold

                needs_blend = abs(p0 - pT) > pos_thresh or abs(v0 - vT) > vel_thresh

                if needs_blend:
                    # Compute blend window
                    w = min(duration * cfg.blend_window_ratio, cfg.max_blend_window)
                    blend_start_time = duration - w

                    # Find samples in blend window
                    blend_indices = [i for i, (t, v) in enumerate(keyframes)
                                     if t >= blend_start_time]

                    if not blend_indices or len(blend_indices) < 1:
                        continue

                    # Get values at blend window boundaries
                    first_blend_idx = blend_indices[0]

                    # Need at least one sample before blend window for velocity
                    if first_blend_idx < 1:
                        continue

                    p_blend_start = keyframes[first_blend_idx][1]
                    t_blend_start = keyframes[first_blend_idx][0]

                    # Velocity at blend start via central finite difference
                    if first_blend_idx + 1 < len(keyframes):
                        v_blend_start = (
                            (keyframes[first_blend_idx + 1][1] -
                             keyframes[first_blend_idx - 1][1]) /
                            (keyframes[first_blend_idx + 1][0] -
                             keyframes[first_blend_idx - 1][0])
                        )
                    else:
                        v_blend_start = vT

                    # Target: position at end = p0, velocity at end = v0
                    p_blend_end = p0      # target position = start of loop
                    v_blend_end = v0      # target velocity = start velocity

                    # Cubic Hermite interpolation for blend window
                    w_actual = duration - t_blend_start
                    if w_actual < 1e-12:
                        continue

                    for idx in blend_indices:
                        t, v = keyframes[idx]
                        s = (t - t_blend_start) / w_actual  # normalized 0→1
                        s = max(0.0, min(1.0, s))

                        # Hermite basis functions
                        h00 = 2 * s ** 3 - 3 * s ** 2 + 1
                        h10 = s ** 3 - 2 * s ** 2 + s
                        h01 = -2 * s ** 3 + 3 * s ** 2
                        h11 = s ** 3 - s ** 2

                        new_val = (h00 * p_blend_start +
                                   h10 * w_actual * v_blend_start +
                                   h01 * p_blend_end +
                                   h11 * w_actual * v_blend_end)

                        keyframes[idx] = (t, new_val)

                # Always snap last keyframe to first for perfect C0
                keyframes[-1] = (keyframes[-1][0], p0)

        return sampled_data


# ============================================================================
# Adaptive Sampler
# ============================================================================

class AdaptiveSampler:
    """Frequency-aware adaptive sampling rate selection.

    Determines optimal sampling rate based on highest frequency component,
    ensuring Nyquist×4 minimum for adequate reconstruction.
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()

    def compute_sample_rate(self, frequency_report: FrequencyReport,
                            config: ConverterConfig = None) -> float:
        """Compute optimal sampling rate for a given animation.

        Args:
            frequency_report: FFT analysis results
            config: Optional config override

        Returns:
            Sampling rate in Hz (samples per second).
        """
        cfg = config or self.config
        rate = max(cfg.nyquist_factor * 2 * frequency_report.max_frequency_hz,
                   cfg.base_sample_rate)
        return max(cfg.min_sample_rate, min(cfg.max_sample_rate, rate))


# ============================================================================
# Smart Duration Optimizer
# ============================================================================

class SmartDurationOptimizer:
    """Multi-frequency duration alignment for seamless looping.

    Given multiple cosine components with different frequencies, find
    the shortest duration T where ALL components return to their
    starting phase (position AND velocity).
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()

    def optimize_duration(self, eval_func: Callable,
                          frequency_report: FrequencyReport,
                          config: ConverterConfig = None) -> float:
        """Find optimal loop duration using frequency analysis.

        Args:
            eval_func: Animation evaluator
            frequency_report: Pre-computed frequency analysis results
            config: Optional config override

        Returns:
            Optimal loop duration in seconds.
        """
        cfg = config or self.config

        # Get periods from frequency report
        periods = frequency_report.estimated_loop_periods
        if not periods:
            return cfg.min_loop_duration

        # Collect all dominant frequencies from all channels
        all_freqs = []
        for bone_name, channels in frequency_report.channel_frequencies.items():
            for channel, freqs in channels.items():
                all_freqs.extend(freqs)

        if not all_freqs:
            return cfg.min_loop_duration

        # Remove duplicates and sort
        all_freqs = sorted(set(all_freqs))

        # Method 1: Try multiples of candidate periods
        candidates = []
        for period in periods:
            for n in range(1, 50):
                T = n * period
                if T < cfg.min_loop_duration:
                    continue
                if T > cfg.max_loop_duration:
                    break
                candidates.append(T)

        # Method 2: Incremental search with phase error
        T = cfg.min_loop_duration
        while T <= cfg.max_loop_duration:
            candidates.append(T)
            T += cfg.duration_search_step

        # Remove duplicates and sort
        candidates = sorted(set(candidates))

        # Evaluate each candidate by total phase error
        best_duration = cfg.min_loop_duration
        best_error = float('inf')

        for T in candidates:
            total_phase_error = 0.0
            for fi in all_freqs:
                if fi < 0.001:
                    continue
                # Phase error: how far from completing integer cycles
                n_cycles = T * fi
                fractional = n_cycles - round(n_cycles)
                phase_error = abs(math.sin(math.pi * fractional * 2))
                total_phase_error += phase_error

            if total_phase_error < best_error:
                best_error = total_phase_error
                best_duration = T

        # If we found a good match with low phase error, return it
        if best_error < len(all_freqs) * cfg.phase_error_tolerance:
            return round(best_duration, 4)

        # Try continued-fraction approximation for the most common case
        if len(periods) >= 2:
            cf_duration = self._continued_fraction_lcm(periods, cfg)
            if cf_duration is not None:
                # Validate with phase error
                total_error = 0.0
                for fi in all_freqs:
                    if fi < 0.001:
                        continue
                    n_cycles = cf_duration * fi
                    fractional = n_cycles - round(n_cycles)
                    total_error += abs(math.sin(math.pi * fractional * 2))
                if total_error < best_error:
                    return round(cf_duration, 4)

        return round(best_duration, 4)

    def _continued_fraction_lcm(self, periods: List[float],
                                 config: ConverterConfig) -> Optional[float]:
        """Find approximate LCM using continued fraction expansion.

        Args:
            periods: List of oscillation periods in seconds
            config: Configuration

        Returns:
            Approximate LCM duration, or None if not found within bounds.
        """
        if len(periods) < 2:
            return None

        # Sort by period (longest first)
        sorted_periods = sorted(periods, reverse=True)

        # For each pair, find rational approximation
        def _rational_approx(x: float, max_denom: int = 100) -> Tuple[int, int]:
            """Find rational approximation p/q ≈ x using continued fractions."""
            best_p, best_q = round(x), 1
            best_err = abs(x - best_p)

            a0 = int(x)
            frac = x - a0
            p_prev, p_curr = 1, a0
            q_prev, q_curr = 0, 1

            for _ in range(20):
                if abs(frac) < 1e-10:
                    break
                recip = 1.0 / frac
                a = int(recip)
                frac = recip - a

                p_next = a * p_curr + p_prev
                q_next = a * q_curr + q_prev

                if q_next > max_denom:
                    break

                err = abs(x - p_next / q_next)
                if err < best_err:
                    best_err = err
                    best_p = p_next
                    best_q = q_next

                p_prev, p_curr = p_curr, p_next
                q_prev, q_curr = q_curr, q_next

            return best_p, best_q

        # Find LCM of period ratios
        base_period = sorted_periods[0]
        denominators = [1]
        for p in sorted_periods[1:]:
            if base_period < 1e-12:
                continue
            ratio = base_period / p
            _, q = _rational_approx(ratio)
            denominators.append(q)

        # LCM of denominators
        from math import gcd
        lcm = 1
        for d in denominators:
            lcm = lcm * d // gcd(lcm, d)

        result = base_period * lcm
        if config.min_loop_duration <= result <= config.max_loop_duration:
            return result

        return None


# ============================================================================
# Douglas-Peucker Simplifier
# ============================================================================

class DouglasPeuckerSimplifier:
    """Unified Douglas-Peucker simplification with channel-type-aware epsilon.

    Uses different epsilon values for rotation (degrees) vs position (pixels)
    channels, since their units and perceptual thresholds differ.
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()

    def simplify(self, points: List[Tuple[float, float]],
                 epsilon: float) -> List[Tuple[float, float]]:
        """Apply Douglas-Peucker simplification to a list of (time, value) pairs.

        Args:
            points: Sorted (time, value) keyframe pairs
            epsilon: Maximum perpendicular distance threshold

        Returns:
            Simplified keyframe list.
        """
        if len(points) <= 2:
            return points

        start, end = points[0], points[-1]
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        line_len_sq = dx * dx + dy * dy

        max_dist = 0.0
        max_idx = 0
        for i in range(1, len(points) - 1):
            if line_len_sq < 1e-12:
                dist = math.hypot(points[i][0] - start[0], points[i][1] - start[1])
            else:
                t = ((points[i][0] - start[0]) * dx +
                     (points[i][1] - start[1]) * dy) / line_len_sq
                t = max(0.0, min(1.0, t))
                proj_x = start[0] + t * dx
                proj_y = start[1] + t * dy
                dist = math.hypot(points[i][0] - proj_x, points[i][1] - proj_y)

            if dist > max_dist:
                max_dist = dist
                max_idx = i

        if max_dist > epsilon:
            left = self.simplify(points[:max_idx + 1], epsilon)
            right = self.simplify(points[max_idx:], epsilon)
            return left[:-1] + right
        else:
            return [points[0], points[-1]]

    def get_epsilon(self, channel: str, config: ConverterConfig = None) -> float:
        """Get channel-appropriate DP epsilon.

        Args:
            channel: Channel name ("rx", "ry", "rz", "ox", "oy", "oz")
            config: Optional config override

        Returns:
            Epsilon value in output units.
        """
        cfg = config or self.config
        if channel in ('rx', 'ry', 'rz'):
            return cfg.dp_epsilon_rotation
        else:
            return cfg.dp_epsilon_position


# ============================================================================
# GeckoLib JSON Builder
# ============================================================================

class GeckoLibJSONBuilder:
    """Builds GeckoLib 1.20.1 .animation.json format from sampled data.

    Handles:
    - DP simplification per-channel with appropriate epsilon
    - Channel name mapping (rx→x, ry→y, rz→z for GeckoLib)
    - Separation of rotation and position into GeckoLib bone entries
    - Filtering near-zero values
    - Time/value formatting precision
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()
        self.dp_simplifier = DouglasPeuckerSimplifier(self.config)

    def build(self, anim_name: str, loop_mode: str,
              sampled_data: Dict, duration: float,
              config: ConverterConfig = None) -> dict:
        """Build a GeckoLib animation entry from sampled data.

        Args:
            anim_name: Animation name (e.g., "animation.model.idle")
            loop_mode: "loop" or "hold_on_last_frame"
            sampled_data: {bone: {channel: [(t, v), ...]}}
                          Values already M_MODEL converted and in degrees/pixels
            duration: Animation duration in seconds
            config: Optional config override

        Returns:
            GeckoLib animation dict ready for JSON serialization.
        """
        cfg = config or self.config
        bones_dict = {}

        for bone_name, channels in sampled_data.items():
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
        """Build a GeckoLib bone entry from converted channel data.

        Args:
            bone_name: Bone identifier
            channels: {channel: [(t, v), ...]} in output units
            config: Configuration

        Returns:
            GeckoLib bone dict with "rotation" and/or "position" keys,
            or None if all channels are near-zero.
        """
        rot_channels = {}
        pos_channels = {}

        for channel, keyframes in channels.items():
            if not keyframes:
                continue

            # Apply DP simplification
            epsilon = self.dp_simplifier.get_epsilon(channel, config)
            simplified = self.dp_simplifier.simplify(keyframes, epsilon)

            # Check if all values are near-zero
            max_abs = max(abs(v) for t, v in simplified) if simplified else 0.0
            if max_abs < config.filter_zero_threshold:
                continue

            axis = self._channel_to_axis(channel)

            if channel in ('rx', 'ry', 'rz'):
                rot_channels[axis] = {
                    f"{t:.{config.keyframe_precision}f}": round(v, config.value_precision)
                    for t, v in simplified
                }
            elif channel in ('ox', 'oy', 'oz'):
                pos_channels[axis] = {
                    f"{t:.{config.keyframe_precision}f}": round(v, config.value_precision)
                    for t, v in simplified
                }

        bone_entry = {}
        if rot_channels:
            bone_entry["rotation"] = rot_channels
        if pos_channels:
            bone_entry["position"] = pos_channels

        return bone_entry if bone_entry else None

    @staticmethod
    def _channel_to_axis(channel: str) -> str:
        """Convert internal channel name to GeckoLib axis.
        rx → x, ry → y, rz → z, ox → x, oy → y, oz → z
        """
        return channel[-1]


# ============================================================================
# Java Animation Parser
# ============================================================================

class JavaAnimationParser:
    """Enhanced Java source parser with state machine detection.

    Parses decompiled MC 1.12.2 model classes to extract:
    1. State machine branches (if/else based on entity state variables)
    2. Rotation/position assignments per state
    3. Helper function definitions (swingX, swingZ, moveY)
    4. Intermediate variable resolution (last-assignment-wins semantics)
    """

    # SRG field → axis mapping
    AXIS_MAP = {
        'field_78795_f': 'rx',
        'field_78796_g': 'ry',
        'field_78808_h': 'rz',
        'rotateAngleX': 'rx',
        'rotateAngleY': 'ry',
        'rotateAngleZ': 'rz',
    }

    # Position offset SRG field mapping
    OFFSET_MAP = {
        'field_82906_o': 'ox',   # offsetX
        'field_82907_q': 'oz',   # offsetZ
        'field_82908_p': 'oy',   # offsetY (sometimes)
        'offsetX': 'ox',
        'offsetY': 'oy',
        'offsetZ': 'oz',
    }

    # State detection patterns
    STATE_PATTERNS = [
        (r'parasiteStatus\s*==\s*0', 'idle'),
        (r'i\s*==\s*0', 'idle'),
        (r'parasiteStatus\s*==\s*[12]', 'attack'),
        (r'i\s*==\s*1', 'attack'),
        (r'i\s*>\s*0', 'attack'),
        (r'getFlyingState\s*\(\s*\)', 'fly'),
        (r'flag\b', 'fly'),
        (r'vomit\s*>\s*0', 'vomit'),
        (r'shakingC\s*>\s*0', 'shaking'),
        (r'getCloneC\s*\(\s*\)', 'cosmic'),
    ]

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()
        self.warnings: List[str] = []

    def parse(self, java_source: str,
              bone_mapping: Dict[str, str]) -> List[AnimationStateConfig]:
        """Parse a Java source file and extract animation state definitions.

        Args:
            java_source: Full Java source code of a ModelBase class
            bone_mapping: Dict mapping Java var names to GeckoLib bone IDs

        Returns:
            List of AnimationStateConfig with eval_func populated.
        """
        self.warnings = []

        # Extract setRotationAngles method body
        method_body = self._extract_method_body(java_source)
        if not method_body:
            self.warnings.append("Could not find setRotationAngles method")
            return []

        # Detect state branches
        branches = self._detect_state_branches(method_body)
        if not branches:
            # Single-state animation (no if/else branching)
            branches = [('', method_body, 'idle')]

        # Parse common variables from the full method body (before any if/else)
        common_vars = self._parse_intermediate_variables(method_body)

        # Parse each branch
        states = []
        for condition, body, state_name in branches:
            eval_func = self._build_eval_function(body, bone_mapping, state_name, common_vars)
            if eval_func is not None:
                anim_name = f"animation.model.{state_name}"
                states.append(AnimationStateConfig(
                    name=state_name,
                    animation_name=anim_name,
                    loop_mode="loop",
                    eval_func=eval_func,
                ))

        return states

    def _extract_method_body(self, java_source: str) -> Optional[str]:
        """Extract the body of setRotationAngles (func_78087_a)."""
        # Try SRG name first
        patterns = [
            re.compile(r'public\s+void\s+func_78087_a\s*\([^)]+\)\s*\{', re.DOTALL),
            re.compile(r'public\s+void\s+setRotationAngles\s*\([^)]+\)\s*\{', re.DOTALL),
        ]

        for pattern in patterns:
            match = pattern.search(java_source)
            if match:
                # Count braces to find matching closing brace
                start_pos = match.end() - 1
                depth = 0
                for i in range(start_pos, len(java_source)):
                    if java_source[i] == '{':
                        depth += 1
                    elif java_source[i] == '}':
                        depth -= 1
                        if depth == 0:
                            return java_source[start_pos + 1:i]

        return None

    def _detect_state_branches(self, method_body: str) -> List[Tuple[str, str, str]]:
        """Identify if/else branches that form animation states.

        Returns:
            List of (condition, body, state_name) tuples.
        """
        branches = []

        # Find if/else blocks
        # Simple approach: split on 'if' statements at top level
        depth = 0
        current_start = 0
        if_positions = []

        i = 0
        while i < len(method_body):
            if method_body[i] == '{':
                depth += 1
            elif method_body[i] == '}':
                depth -= 1
            elif depth == 0 and method_body[i:i + 2] == 'if':
                if_positions.append(i)
            i += 1

        if not if_positions:
            return []

        # For each if statement, try to extract the condition and body
        for pos in if_positions:
            # Extract condition
            paren_start = method_body.find('(', pos)
            if paren_start < 0:
                continue
            paren_depth = 0
            paren_end = paren_start
            for j in range(paren_start, len(method_body)):
                if method_body[j] == '(':
                    paren_depth += 1
                elif method_body[j] == ')':
                    paren_depth -= 1
                    if paren_depth == 0:
                        paren_end = j
                        break

            condition = method_body[paren_start + 1:paren_end].strip()

            # Determine state name from condition
            state_name = self._infer_state_name(condition)

            # Extract body (matching braces)
            brace_start = method_body.find('{', paren_end)
            if brace_start < 0:
                continue

            brace_depth = 0
            brace_end = brace_start
            for j in range(brace_start, len(method_body)):
                if method_body[j] == '{':
                    brace_depth += 1
                elif method_body[j] == '}':
                    brace_depth -= 1
                    if brace_depth == 0:
                        brace_end = j
                        break

            body = method_body[brace_start + 1:brace_end]
            branches.append((condition, body, state_name))

        return branches

    def _infer_state_name(self, condition: str) -> str:
        """Infer animation state name from condition expression."""
        for pattern, name in self.STATE_PATTERNS:
            if re.search(pattern, condition):
                return name
        # Default: try to extract a meaningful name from the condition
        return "unknown"

    def _build_eval_function(self, branch_body: str,
                             bone_mapping: Dict[str, str],
                             state_name: str,
                             common_vars: Dict[str, str] = None) -> Optional[Callable]:
        """Construct a Python eval function for an animation state.

        The returned function signature: f(t_seconds) -> Dict[bone, {rx,ry,rz,ox,oy,oz}]
        """
        # Parse intermediate variables from branch body
        branch_vars = self._parse_intermediate_variables(branch_body)

        # Merge with common variables (branch vars override common)
        vars_def = dict(common_vars or {})
        vars_def.update(branch_vars)

        # Parse rotation assignments
        assignments = self._parse_rotation_assignments(branch_body, vars_def)

        # Parse helper function calls (swingX, swingZ, moveY)
        helper_assignments = self._parse_helper_calls(branch_body, bone_mapping)
        assignments.extend(helper_assignments)

        if not assignments:
            return None

        # Build a frozen set of expressions per bone/channel
        bone_exprs: Dict[str, Dict[str, str]] = {}
        for bone_var, channel, expression in assignments:
            bone_name = bone_mapping.get(bone_var, bone_var)
            if bone_name not in bone_exprs:
                bone_exprs[bone_name] = {}
            # Last assignment wins
            bone_exprs[bone_name][channel] = expression

        def eval_func(t_seconds: float) -> Dict[str, Dict[str, float]]:
            age_in_ticks = t_seconds * TICKS_PER_SECOND
            limb_swing_amount = self.config.swing_limb_swing_amount
            limb_swing = limb_swing_amount * age_in_ticks

            # Build evaluation context
            eval_context = {
                'math': math,
                'age_in_ticks': age_in_ticks,
                'limb_swing': limb_swing,
                'limb_swing_amount': limb_swing_amount,
                'cos': math.cos,
                'sin': math.sin,
                'sqrt': math.sqrt,
                'abs': abs,
                'max': max,
                'min': min,
                'pi': math.pi,
            }

            # Resolve intermediate variables
            resolved_vars = {}
            for var_name, var_expr in vars_def.items():
                try:
                    py_expr = self._prepare_expression(var_expr)
                    val = eval(py_expr, {"__builtins__": {}}, {**eval_context, **resolved_vars})
                    resolved_vars[var_name] = val
                except Exception:
                    resolved_vars[var_name] = 0.0

            # Evaluate bone expressions
            result = {}
            for bone_name, channels in bone_exprs.items():
                result[bone_name] = {}
                for channel, expr in channels.items():
                    try:
                        py_expr = self._prepare_expression(expr)
                        val = eval(py_expr, {"__builtins__": {}},
                                   {**eval_context, **resolved_vars})
                        result[bone_name][channel] = float(val)
                    except Exception:
                        result[bone_name][channel] = 0.0

            return result

        return eval_func

    def _parse_intermediate_variables(self, body: str) -> Dict[str, str]:
        """Parse intermediate variable definitions (last-assignment-wins)."""
        vars_def: Dict[str, str] = {}

        # Pattern for: float f11 = expression;  OR  f11 = expression;
        var_pattern = re.compile(r'(?:float\s+)?(f\d+)\s*=\s*([^;]+);')

        for match in var_pattern.finditer(body):
            var_name = match.group(1)
            var_expr = match.group(2).strip()

            # Skip if this is a bone rotation assignment
            if any(field in var_expr for field in
                   ['field_78795_f', 'field_78796_g', 'field_78808_h',
                    'rotateAngleX', 'rotateAngleY', 'rotateAngleZ']):
                continue

            vars_def[var_name] = var_expr

        return vars_def

    def _parse_rotation_assignments(self, body: str,
                                     vars_def: Dict[str, str]) -> List[Tuple[str, str, str]]:
        """Parse rotation and position assignments.

        Returns:
            List of (bone_var, channel, expression) tuples.
        """
        assignments = []

        # Pattern for rotation: this.boneVar.field_78795_f = expression;
        rot_pattern = re.compile(
            r'this\.(\w+)\.(field_78795_f|field_78796_g|field_78808_h|'
            r'rotateAngleX|rotateAngleY|rotateAngleZ)\s*=\s*([^;]+);'
        )

        for match in rot_pattern.finditer(body):
            bone_var = match.group(1)
            axis_field = match.group(2)
            expression = match.group(3).strip()

            channel = self.AXIS_MAP.get(axis_field)
            if not channel:
                continue

            # Handle compound assignments: this.bone.field = f11 = expression;
            compound_match = re.match(r'(\w+)\s*=\s*(.+)', expression)
            if compound_match and compound_match.group(1) in vars_def:
                var_name = compound_match.group(1)
                actual_expr = compound_match.group(2).strip()
                vars_def[var_name] = actual_expr
                expression = var_name

            assignments.append((bone_var, channel, expression))

        # Pattern for position offsets: this.boneVar.field_82906_o = expression;
        pos_pattern = re.compile(
            r'this\.(\w+)\.(field_82906_o|field_82907_q|field_82908_p|'
            r'offsetX|offsetY|offsetZ)\s*=\s*([^;]+);'
        )

        for match in pos_pattern.finditer(body):
            bone_var = match.group(1)
            offset_field = match.group(2)
            expression = match.group(3).strip()

            channel = self.OFFSET_MAP.get(offset_field)
            if not channel:
                continue

            assignments.append((bone_var, channel, expression))

        return assignments

    def _parse_helper_calls(self, body: str,
                            bone_mapping: Dict[str, str]) -> List[Tuple[str, str, str]]:
        """Parse swingX, swingZ, moveY helper function calls.

        swingX(bone, speed, degree, invert, offset, weight, limbSwing, limbSwingAmount)
          → bone.rx = invert * limbSwingAmount * degree * cos(limbSwing * speed + offset) + weight * limbSwingAmount

        swingZ(bone, speed, degree, invert, offset, weight, limbSwing, limbSwingAmount)
          → bone.rz = invert * limbSwingAmount * degree * cos(limbSwing * speed + offset) + weight * limbSwingAmount

        moveY(bone, speed, invert, f, f1, distance)
          → bone.oy = invert * cos(f * speed) * f1 * distance
        """
        assignments = []

        # swingX pattern
        swing_x_pattern = re.compile(
            r'swingX\s*\(\s*this\.(\w+)\s*,\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^,]+)\s*,'
            r'\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^)]+)\s*\)'
        )

        for match in swing_x_pattern.finditer(body):
            bone_var = match.group(1)
            speed = match.group(2).strip()
            degree = match.group(3).strip()
            invert = match.group(4).strip()
            offset = match.group(5).strip()
            weight = match.group(6).strip()
            f = match.group(7).strip()
            f1 = match.group(8).strip()

            expr = (f"({invert}) * ({f1}) * ({degree}) * "
                    f"cos(({f}) * ({speed}) + ({offset})) + ({weight}) * ({f1})")
            assignments.append((bone_var, 'rx', expr))

        # swingZ pattern
        swing_z_pattern = re.compile(
            r'swingZ\s*\(\s*this\.(\w+)\s*,\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^,]+)\s*,'
            r'\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^)]+)\s*\)'
        )

        for match in swing_z_pattern.finditer(body):
            bone_var = match.group(1)
            speed = match.group(2).strip()
            degree = match.group(3).strip()
            invert = match.group(4).strip()
            offset = match.group(5).strip()
            weight = match.group(6).strip()
            f = match.group(7).strip()
            f1 = match.group(8).strip()

            expr = (f"({invert}) * ({f1}) * ({degree}) * "
                    f"cos(({f}) * ({speed}) + ({offset})) + ({weight}) * ({f1})")
            assignments.append((bone_var, 'rz', expr))

        # moveY pattern
        move_y_pattern = re.compile(
            r'moveY\s*\(\s*this\.(\w+)\s*,\s*([^,]+)\s*,\s*([^,]+)\s*,'
            r'\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^)]+)\s*\)'
        )

        for match in move_y_pattern.finditer(body):
            bone_var = match.group(1)
            speed = match.group(2).strip()
            invert = match.group(3).strip()
            f = match.group(4).strip()
            f1 = match.group(5).strip()
            distance = match.group(6).strip()

            expr = f"({invert}) * cos(({f}) * ({speed})) * ({f1}) * ({distance})"
            assignments.append((bone_var, 'oy', expr))

        return assignments

    def _prepare_expression(self, expr: str) -> str:
        """Convert a Java expression to Python-evaluable form.

        Replaces Java math functions with Python equivalents.
        """
        py_expr = expr

        # Replace MathHelper SRG names
        replacements = [
            (r'MathHelper\.func_76134_b', 'math.cos'),
            (r'MathHelper\.func_76126_a', 'math.sin'),
            (r'MathHelper\.func_76133_a', 'math.sin'),
            (r'MathHelper\.func_76129_a', 'math.sqrt'),
            (r'MathHelper\.func_76130_a', 'math.sqrt'),
            (r'MathHelper\.func_76142_g', 'math.floor'),
            (r'MathHelper\.func_76128_c', 'abs'),
            (r'MathHelper\.func_76131_a', 'min'),  # clamp approximation
            (r'MathHelper\.cos', 'math.cos'),
            (r'MathHelper\.sin', 'math.sin'),
            (r'MathHelper\.sqrt', 'math.sqrt'),
            (r'MathHelper\.abs', 'abs'),
            (r'Math\.cos', 'math.cos'),
            (r'Math\.sin', 'math.sin'),
            (r'Math\.sqrt', 'math.sqrt'),
            (r'Math\.abs', 'abs'),
            (r'Math\.floor', 'math.floor'),
            (r'Math\.ceil', 'math.ceil'),
            (r'Math\.max', 'max'),
            (r'Math\.min', 'min'),
            (r'Math\.toRadians', 'math.radians'),
            (r'Math\.toDegrees', 'math.degrees'),
            (r'Math\.PI', str(math.pi)),
        ]

        for pattern, replacement in replacements:
            py_expr = re.sub(pattern, replacement, py_expr)

        # Replace Java float suffixes
        py_expr = re.sub(r'(\d+(?:\.\d+)?)[fF](?!\w)', r'\1', py_expr)

        # Replace parameter references
        py_expr = py_expr.replace('ageInTicks', 'age_in_ticks')
        py_expr = py_expr.replace('limbSwingAmount', 'limb_swing_amount')
        py_expr = py_expr.replace('limbSwing', 'limb_swing')

        # Remove explicit casts
        py_expr = re.sub(r'\(float\)', '', py_expr)
        py_expr = re.sub(r'\(double\)', '', py_expr)
        py_expr = re.sub(r'\(int\)', '', py_expr)

        # Handle partialTick / partialTicks
        py_expr = re.sub(r'\bpartialTick[s]?\b', '0.0', py_expr)

        return py_expr


# ============================================================================
# Universal Animation Converter (Main Orchestrator)
# ============================================================================

class UniversalAnimationConverter:
    """Main orchestrator for the universal animation conversion pipeline.

    Coordinates all sub-components to convert MC 1.12.2 animations to
    GeckoLib 1.20.1 format, handling both:
    - Automatic Java source parsing (PATH A)
    - Callback-based eval functions (PATH B)

    Pipeline:
    1. Get eval functions (from Java parser or user callbacks)
    2. Auto-detect duration via AutoLoopDetector
    3. Frequency analysis via FrequencyAnalyzer
    4. Smart duration optimization via SmartDurationOptimizer
    5. Adaptive sampling rate via AdaptiveSampler
    6. Sample eval functions
    7. Apply M_MODEL conversion + rad→deg
    8. Enforce C1 continuity (for loop animations)
    9. Douglas-Peucker simplification
    10. Build GeckoLib JSON
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()
        self.frequency_analyzer = FrequencyAnalyzer(self.config)
        self.loop_detector = AutoLoopDetector(self.config)
        self.c1_enforcer = C1ContinuityEnforcer(self.config)
        self.adaptive_sampler = AdaptiveSampler(self.config)
        self.duration_optimizer = SmartDurationOptimizer(self.config)
        self.dp_simplifier = DouglasPeuckerSimplifier(self.config)
        self.json_builder = GeckoLibJSONBuilder(self.config)
        self.java_parser = JavaAnimationParser(self.config)

    def convert_from_callbacks(self, states: List[AnimationStateConfig],
                                model_name: str = "model") -> dict:
        """Convert animations from user-provided eval functions.

        This is PATH B - for migration from existing generators.
        User provides eval functions that return Dict[bone_name, {rx,ry,rz,ox,oy,oz}]
        in MC space.

        Args:
            states: List of AnimationStateConfig with eval_func populated
            model_name: Name for the animation namespace

        Returns:
            Complete .animation.json dict
        """
        animations = {}

        for state in states:
            if state.eval_func is None:
                continue

            anim_name = state.animation_name or f"animation.{model_name}.{state.name}"

            # Step 1: Determine duration
            if state.duration is not None:
                duration = state.duration
            else:
                duration = self.loop_detector.find_loop_duration(
                    state.eval_func, self.config
                )

            # Step 2: Sample at base rate for frequency analysis
            initial_data = self._sample_eval_func(
                state.eval_func, duration, self.config.base_sample_rate
            )

            # Step 3: Frequency analysis
            freq_report = self.frequency_analyzer.analyze(initial_data)

            # Step 4: Smart duration optimization (if not specified)
            if state.duration is None:
                optimized = self.duration_optimizer.optimize_duration(
                    state.eval_func, freq_report, self.config
                )
                if optimized > 0:
                    duration = optimized

            # Step 5: Determine sample rate
            if state.sample_rate is not None:
                sample_rate = state.sample_rate
            else:
                sample_rate = self.adaptive_sampler.compute_sample_rate(
                    freq_report, self.config
                )

            # Step 6: Re-sample at optimized rate with optimized duration
            sampled_data = self._sample_eval_func(
                state.eval_func, duration, sample_rate
            )

            # Step 7: Enforce C1 continuity (for loop animations)
            if state.loop_mode == "loop":
                sampled_data = self.c1_enforcer.enforce(
                    sampled_data, duration, self.config
                )

            # Step 8: Build animation JSON (with DP simplification inside)
            anim_entry = self.json_builder.build(
                anim_name, state.loop_mode, sampled_data, duration, self.config
            )

            animations[anim_name] = anim_entry

        return {
            "format_version": "1.8.0",
            "animations": animations
        }

    def convert_from_java(self, java_source: str,
                          bone_mapping: Dict[str, str],
                          model_name: str = "model") -> dict:
        """Convert animations from Java source code.

        This is PATH A - fully automated.

        Args:
            java_source: Full Java source code of a ModelBase class
            bone_mapping: Dict mapping Java var names to GeckoLib bone IDs
            model_name: Name for the animation namespace

        Returns:
            Complete .animation.json dict
        """
        states = self.java_parser.parse(java_source, bone_mapping)
        return self.convert_from_callbacks(states, model_name)

    def _sample_eval_func(self, eval_func: Callable, duration: float,
                          sample_rate: float) -> Dict:
        """Sample an eval function over time.

        Returns: {bone_name: {channel: [(time, value), ...]}}
        Values are sampled in MC space (radians for rotation, pixels for position),
        then M_MODEL conversion is applied, and rotation is converted to degrees.

        Args:
            eval_func: Animation evaluator, t(seconds) -> bone->channel->value
            duration: Total duration in seconds
            sample_rate: Samples per second
        """
        n_samples = max(int(duration * sample_rate), 120)
        dt = duration / n_samples
        raw_channels: Dict[str, Dict[str, List[Tuple[float, float]]]] = {}

        for i in range(n_samples + 1):
            t = i * dt
            try:
                bone_values = eval_func(t)
            except Exception:
                continue

            for bone_name, channels in bone_values.items():
                if bone_name not in raw_channels:
                    raw_channels[bone_name] = {}
                for channel, value in channels.items():
                    if channel not in raw_channels[bone_name]:
                        raw_channels[bone_name][channel] = []
                    raw_channels[bone_name][channel].append((t, value))

        # Apply M_MODEL conversion + rad→deg
        return self._apply_model_conversion(raw_channels)

    def _apply_model_conversion(self, sampled_data: Dict) -> Dict:
        """Apply M_MODEL conversion to sampled data.

        Rotation: rx stays, ry→-ry, rz→-rz, then rad→deg
        Position: ox stays, oy→-oy, oz→-oz (stays in pixels)
        """
        result = {}
        for bone_name, channels in sampled_data.items():
            result[bone_name] = {}
            for channel, points in channels.items():
                converted = []
                for t, val in points:
                    if channel == 'rx':
                        converted.append((t, val))
                    elif channel == 'ry':
                        converted.append((t, -val))
                    elif channel == 'rz':
                        converted.append((t, -val))
                    elif channel == 'ox':
                        converted.append((t, val))
                    elif channel == 'oy':
                        converted.append((t, -val))
                    elif channel == 'oz':
                        converted.append((t, -val))
                    else:
                        converted.append((t, val))

                # Convert rotation from radians to degrees
                if channel in ('rx', 'ry', 'rz'):
                    converted = [(t, rad_to_deg(v)) for t, v in converted]

                result[bone_name][channel] = converted

        return result


# ============================================================================
# Convenience Functions (backward compatible)
# ============================================================================

def sample_animation(eval_func: Callable, duration: float,
                     samples_per_second: float = 60.0,
                     dp_epsilon: float = 0.15) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
    """Backward-compatible wrapper - same API as existing generators.

    Samples an animation function over time and applies M_MODEL conversion
    and Douglas-Peucker simplification.

    Args:
        eval_func: Animation evaluator, t(seconds) -> bone->channel->value
        duration: Animation duration in seconds
        samples_per_second: Sampling rate (default 60 fps)
        dp_epsilon: DP simplification threshold (default 0.15 degrees)

    Returns:
        {bone_name: {channel: [(time, value), ...]}}
        Values in GeckoLib output units (degrees/pixels).
    """
    config = ConverterConfig(
        base_sample_rate=samples_per_second,
        dp_epsilon_rotation=dp_epsilon,
        dp_epsilon_position=dp_epsilon * 0.1,
    )
    converter = UniversalAnimationConverter(config)
    return converter._sample_eval_func(eval_func, duration, samples_per_second)


def build_animation_json(anim_name: str, loop_mode: str,
                         sampled_data: Dict[str, Dict[str, List[Tuple[float, float]]]],
                         duration: float) -> dict:
    """Backward-compatible wrapper for building GeckoLib animation JSON.

    Args:
        anim_name: Animation name
        loop_mode: "loop" or "hold_on_last_frame"
        sampled_data: {bone: {channel: [(t, v), ...]}}
        duration: Animation duration in seconds

    Returns:
        GeckoLib animation dict.
    """
    config = ConverterConfig()
    builder = GeckoLibJSONBuilder(config)
    return builder.build(anim_name, loop_mode, sampled_data, duration, config)


def enforce_loop_continuity(sampled_data: Dict, duration: float,
                            rot_threshold: float = 0.1,
                            pos_threshold: float = 0.01) -> Dict:
    """Backward-compatible wrapper with C1 enhancement.

    Enforces loop continuity using C1 continuity enforcement when possible,
    falling back to simple C0 snapping for backward compatibility.

    Args:
        sampled_data: {bone: {channel: [(t, v), ...]}}
        duration: Animation duration in seconds
        rot_threshold: Rotation threshold in degrees
        pos_threshold: Position threshold in pixels

    Returns:
        Modified sampled_data with continuity enforced.
    """
    config = ConverterConfig(
        velocity_match_threshold_rot=rot_threshold,
        velocity_match_threshold_pos=pos_threshold,
    )
    enforcer = C1ContinuityEnforcer(config)
    return enforcer.enforce(sampled_data, duration, config)


# ============================================================================
# Batch Conversion
# ============================================================================

def batch_convert_creature(creature_name: str,
                           eval_functions: Dict[str, Callable] = None,
                           bone_mapping: Dict[str, str] = None,
                           config: ConverterConfig = None,
                           states: List[AnimationStateConfig] = None) -> dict:
    """Convert all animations for a creature at once.

    Args:
        creature_name: Name for the animation (e.g., "heblu", "kirin")
        eval_functions: Dict mapping state names to eval functions
                       e.g., {"idle": eval_idle, "attack": eval_attack, ...}
                       All states default to loop_mode="loop".
                       For finer control, use the `states` parameter instead.
        bone_mapping: Optional bone name mapping
        config: Optional configuration override
        states: Optional list of AnimationStateConfig objects with full
                per-state settings (duration, loop_mode, sample_rate, etc.).
                If provided, `eval_functions` is ignored.

    Returns:
        Complete .animation.json dict
    """
    cfg = config or ConverterConfig()
    converter = UniversalAnimationConverter(cfg)

    if states is not None:
        # Use provided AnimationStateConfig objects directly
        anim_states = states
    elif eval_functions is not None:
        # Build AnimationStateConfig from simple eval_functions dict
        anim_states = []
        for state_name, eval_func in eval_functions.items():
            anim_name = f"animation.{creature_name}.{state_name}"
            anim_states.append(AnimationStateConfig(
                name=state_name,
                animation_name=anim_name,
                loop_mode="loop",
                eval_func=eval_func,
            ))
    else:
        raise ValueError("Either eval_functions or states must be provided")

    return converter.convert_from_callbacks(anim_states, creature_name)
