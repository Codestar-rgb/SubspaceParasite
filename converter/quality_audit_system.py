#!/usr/bin/env python3
"""
QualityAuditSystem - Comprehensive Quality Audit for Animation Conversion
=========================================================================
Scans source .bbmodel files, audits converted .animation.json output against
expected data, generates detailed quality reports (JSON + Markdown), and
tracks quality metrics over time.

Key Innovation: Curvature-based naturalness scoring replaces sign-change
counting (which classified 78.8% of animations as unnatural). The new
method evaluates smoothness of curvature changes, acceleration profiles,
and velocity continuity, properly handling periodic animations like walk
cycles.

Usage as CLI:
  python quality_audit_system.py \\
    --source-dir /path/to/bbmodels \\
    --output-dir /path/to/output \\
    --thresholds default \\
    --report-dir /path/to/reports

Usage as library:
  from quality_audit_system import QualityAuditSystem
  system = QualityAuditSystem(thresholds='default')
  profiles = system.scan_source_files('/path/to/bbmodels')
  report = system.audit_converted_output('/path/to/output', profiles)
  system.generate_report_json(report, 'report.json')
  system.generate_report_markdown(report, 'report.md')
"""

import argparse
import json
import math
import os
import sys
import time as _time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Optional numpy for high-quality numerical computation
_NUMPY_AVAILABLE = False
try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore


# ============================================================================
# Utility: Pure-Python Numerical Helpers (fallback when numpy unavailable)
# ============================================================================

def _linspace(start: float, stop: float, num: int) -> List[float]:
    """Generate num evenly-spaced values from start to stop inclusive."""
    if num <= 1:
        return [start]
    step = (stop - start) / (num - 1)
    return [start + i * step for i in range(num)]


def _catmull_rom_interp(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    """Catmull-Rom interpolation at parameter t in [0,1] between p1 and p2."""
    t2 = t * t
    t3 = t2 * t
    return 0.5 * (
        (2.0 * p1) +
        (-p0 + p2) * t +
        (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2 +
        (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
    )


def _catmull_rom_derivative(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    """First derivative of Catmull-Rom spline at t in [0,1]."""
    t2 = t * t
    return 0.5 * (
        (-p0 + p2) +
        (4.0 * p0 - 10.0 * p1 + 8.0 * p2 - 2.0 * p3) * t +
        (-3.0 * p0 + 9.0 * p1 - 9.0 * p2 + 3.0 * p3) * t2
    )


def _catmull_rom_second_derivative(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    """Second derivative of Catmull-Rom spline at t in [0,1]."""
    return 0.5 * (
        (4.0 * p0 - 10.0 * p1 + 8.0 * p2 - 2.0 * p3) +
        (-6.0 * p0 + 18.0 * p1 - 18.0 * p2 + 6.0 * p3) * t
    )


def _resample_channel_catmull(times: List[float], values: List[float],
                               duration: float, rate: float = 120.0) -> Tuple[List[float], List[float]]:
    """Resample a channel using Catmull-Rom interpolation at uniform rate.

    Returns (sample_times, sample_values).
    """
    if len(times) < 2:
        return [0.0], [values[0] if values else 0.0]

    n_samples = max(2, int(duration * rate) + 1)
    sample_times = _linspace(0.0, duration, n_samples)
    sample_values = []

    n_kf = len(times)
    for st in sample_times:
        # Find segment
        seg = 0
        for i in range(n_kf - 1):
            if times[i] <= st + 1e-9:
                seg = i
        seg = min(seg, n_kf - 2)

        t0 = times[seg]
        t1 = times[seg + 1]
        dt = t1 - t0
        if dt < 1e-12:
            sample_values.append(values[seg])
            continue

        local_t = (st - t0) / dt
        local_t = max(0.0, min(1.0, local_t))

        # Catmull-Rom control points
        p0 = values[seg - 1] if seg > 0 else 2.0 * values[seg] - values[seg + 1]
        p1 = values[seg]
        p2 = values[seg + 1]
        p3 = values[seg + 2] if seg + 2 < n_kf else 2.0 * values[seg + 1] - values[seg]

        sample_values.append(_catmull_rom_interp(p0, p1, p2, p3, local_t))

    return sample_times, sample_values


def _compute_derivatives(values: List[float], dt: float) -> Tuple[List[float], List[float], List[float]]:
    """Compute velocity, acceleration, jerk from uniformly-sampled values.

    Uses central differences for interior points, forward/backward at edges.
    Returns (velocity, acceleration, jerk).
    """
    n = len(values)
    if n < 2:
        return [0.0], [0.0], [0.0]

    # Velocity (1st derivative)
    vel = [0.0] * n
    if n >= 3:
        vel[0] = (values[1] - values[0]) / dt
        vel[-1] = (values[-1] - values[-2]) / dt
        for i in range(1, n - 1):
            vel[i] = (values[i + 1] - values[i - 1]) / (2.0 * dt)
    else:
        vel[0] = (values[1] - values[0]) / dt
        vel[-1] = vel[0]

    # Acceleration (2nd derivative)
    acc = [0.0] * n
    if n >= 3:
        acc[0] = (values[2] - 2.0 * values[1] + values[0]) / (dt * dt)
        acc[-1] = (values[-1] - 2.0 * values[-2] + values[-3]) / (dt * dt)
        for i in range(1, n - 1):
            acc[i] = (values[i + 1] - 2.0 * values[i] + values[i - 1]) / (dt * dt)
    else:
        acc[0] = 0.0
        acc[-1] = 0.0

    # Jerk (3rd derivative = derivative of acceleration)
    jerk = [0.0] * n
    if n >= 4:
        jerk[0] = (acc[1] - acc[0]) / dt
        jerk[-1] = (acc[-1] - acc[-2]) / dt
        for i in range(1, n - 1):
            jerk[i] = (acc[i + 1] - acc[i - 1]) / (2.0 * dt)
    else:
        jerk[0] = 0.0
        jerk[-1] = 0.0

    return vel, acc, jerk


def _variance(values: List[float]) -> float:
    """Compute population variance of a list of floats."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


def _std(values: List[float]) -> float:
    """Compute population standard deviation."""
    return math.sqrt(_variance(values))


def _autocorrelation_period(values: List[float], dt: float,
                             min_period: float = 0.2, max_period: float = 5.0) -> Optional[float]:
    """Estimate the dominant period of a signal using autocorrelation.

    Returns the period in seconds, or None if no clear periodicity found.
    """
    n = len(values)
    if n < 10:
        return None

    mean = sum(values) / n
    centered = [v - mean for v in values]

    # Compute autocorrelation at integer lags
    max_lag = min(n // 2, int(max_period / dt))
    min_lag = max(1, int(min_period / dt))

    if max_lag <= min_lag:
        return None

    # Normalization: autocorrelation at lag 0
    norm = sum(c * c for c in centered)
    if norm < 1e-15:
        return None

    best_lag = None
    best_corr = 0.0
    for lag in range(min_lag, max_lag + 1):
        corr = 0.0
        count = n - lag
        for i in range(count):
            corr += centered[i] * centered[i + lag]
        corr /= norm
        if corr > best_corr:
            best_corr = corr
            best_lag = lag

    if best_corr > 0.3 and best_lag is not None:
        return best_lag * dt
    return None


def _sinusoidal_fit_score(values: List[float], dt: float) -> float:
    """Score how well a signal matches a sinusoidal template.

    Fits amplitude, phase, and frequency, then returns R^2 of the fit.
    Returns 0.0 if the signal is essentially flat or too short.
    """
    n = len(values)
    if n < 8:
        return 0.0

    amplitude = (max(values) - min(values)) / 2.0
    if amplitude < 0.01:  # Essentially static
        return 1.0  # Static is perfectly smooth

    mean_val = sum(values) / n
    centered = [v - mean_val for v in values]

    # Estimate frequency via zero crossings
    crossings = 0
    for i in range(1, n):
        if centered[i - 1] * centered[i] < 0:
            crossings += 1

    if crossings < 2:
        # Try autocorrelation
        period = _autocorrelation_period(values, dt, 0.2, min(n * dt * 0.5, 5.0))
        if period is None:
            return 0.5  # No periodicity, give moderate score
        freq = 1.0 / period
    else:
        freq = (crossings / 2.0) / (n * dt)

    # Fit sinusoidal: A * sin(2*pi*f*t + phi)
    # Try multiple phases and pick best
    best_r2 = -1e10
    best_template = None
    for phase_offset_idx in range(20):
        phi = phase_offset_idx * math.pi / 10.0
        template = [amplitude * math.sin(2.0 * math.pi * freq * i * dt + phi) for i in range(n)]

        # Compute R^2
        ss_res = sum((centered[i] - template[i]) ** 2 for i in range(n))
        ss_tot = sum(c ** 2 for c in centered)
        if ss_tot < 1e-15:
            return 1.0
        r2 = 1.0 - ss_res / ss_tot

        if r2 > best_r2:
            best_r2 = r2
            best_template = template

    # Also try cosine phase with mean adjustment
    # Try fitting A*sin + B*cos
    if n > 4:
        sin_vals = [math.sin(2.0 * math.pi * freq * i * dt) for i in range(n)]
        cos_vals = [math.cos(2.0 * math.pi * freq * i * dt) for i in range(n)]

        # Least squares: centered = A*sin + B*cos
        sin_sin = sum(s * s for s in sin_vals)
        cos_cos = sum(c * c for c in cos_vals)
        sin_cos = sum(s * c for s, c in zip(sin_vals, cos_vals))
        sin_data = sum(s * d for s, d in zip(sin_vals, centered))
        cos_data = sum(c * d for c, d in zip(cos_vals, centered))

        det = sin_sin * cos_cos - sin_cos * sin_cos
        if abs(det) > 1e-15:
            A = (sin_data * cos_cos - cos_data * sin_cos) / det
            B = (cos_data * sin_sin - sin_data * sin_cos) / det

            fitted = [A * sin_vals[i] + B * cos_vals[i] for i in range(n)]
            ss_res = sum((centered[i] - fitted[i]) ** 2 for i in range(n))
            ss_tot = sum(c ** 2 for c in centered)
            if ss_tot > 1e-15:
                r2 = 1.0 - ss_res / ss_tot
                if r2 > best_r2:
                    best_r2 = r2

    return max(0.0, min(1.0, best_r2))


# ============================================================================
# QualityThresholds
# ============================================================================

class QualityThresholds:
    """Configurable quality thresholds for strict/default/lenient modes."""

    # Strict mode
    c0_strict_rot: float = 0.05        # degrees
    c1_strict_rot: float = 1.0         # deg/s
    naturalness_strict: float = 0.9
    amplitude_retention_strict: float = 0.95

    # Default mode
    c0_default_rot: float = 0.1
    c1_default_rot: float = 1.5
    naturalness_default: float = 0.8
    amplitude_retention_default: float = 0.90

    # Lenient mode
    c0_lenient_rot: float = 0.5
    c1_lenient_rot: float = 5.0
    naturalness_lenient: float = 0.6
    amplitude_retention_lenient: float = 0.80

    # Position thresholds (shared across modes — less critical)
    c0_default_pos: float = 0.01       # pixels
    c1_default_pos: float = 0.3        # pixels/s

    # Quality grade boundaries (fractional scores)
    grade_a_min: float = 0.90
    grade_b_min: float = 0.80
    grade_c_min: float = 0.65
    grade_d_min: float = 0.50

    def __init__(self, mode: str = 'default'):
        self.mode = mode
        if mode == 'strict':
            self.c0_rot = self.c0_strict_rot
            self.c1_rot = self.c1_strict_rot
            self.naturalness = self.naturalness_strict
            self.amplitude_retention = self.amplitude_retention_strict
        elif mode == 'lenient':
            self.c0_rot = self.c0_lenient_rot
            self.c1_rot = self.c1_lenient_rot
            self.naturalness = self.naturalness_lenient
            self.amplitude_retention = self.amplitude_retention_lenient
        else:  # default
            self.c0_rot = self.c0_default_rot
            self.c1_rot = self.c1_default_rot
            self.naturalness = self.naturalness_default
            self.amplitude_retention = self.amplitude_retention_default

        self.c0_pos = self.c0_default_pos
        self.c1_pos = self.c1_default_pos

    def to_dict(self) -> Dict[str, float]:
        return {
            'mode': self.mode,
            'c0_rot': self.c0_rot,
            'c1_rot': self.c1_rot,
            'naturalness': self.naturalness,
            'amplitude_retention': self.amplitude_retention,
            'c0_pos': self.c0_pos,
            'c1_pos': self.c1_pos,
        }


# ============================================================================
# SourceAnimationProfile
# ============================================================================

@dataclass
class SourceAnimationProfile:
    """Profile of a source animation extracted from .bbmodel."""
    model_name: str
    animation_name: str
    num_bones: int
    bone_names: List[str]
    duration: float
    # Per-channel amplitude (max - min) from source
    # {bone: {channel: amplitude}}
    source_amplitudes: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # Per-channel peak values
    # {bone: {channel: (min, max)}}
    source_peaks: Dict[str, Dict[str, Tuple[float, float]]] = field(default_factory=dict)
    # Raw keyframe data for detailed comparison
    # {bone: {channel: {axis: [(time, value), ...]}}}
    source_keyframes: Dict[str, Dict[str, Dict[str, List[Tuple[float, float]]]]] = field(default_factory=dict)
    # Is this a loop animation?
    loop: bool = True
    # Animation category (idle, walk, attack, etc.)
    category: str = 'unknown'


# ============================================================================
# ConversionQualityMetrics
# ============================================================================

@dataclass
class ConversionQualityMetrics:
    """Quality metrics for a single converted animation."""
    model_name: str
    animation_name: str
    # C0 continuity
    c0_max_error_rot: float = 0.0
    c0_max_error_pos: float = 0.0
    c0_perfect: bool = False
    # C1 continuity
    c1_max_error_rot: float = 0.0
    c1_p90_error_rot: float = 0.0
    c1_perfect: bool = False
    # Naturalness
    naturalness_score: float = 0.0
    naturalness_method: str = 'curvature_smoothness'
    # Amplitude retention
    amplitude_retention_avg: float = 1.0
    amplitude_retention_min: float = 1.0
    channels_with_amplitude_loss: List[str] = field(default_factory=list)
    # Animation completeness
    expected_bones: int = 0
    actual_bones: int = 0
    missing_bones: List[str] = field(default_factory=list)
    expected_duration: float = 0.0
    actual_duration: float = 0.0
    # Overall quality
    quality_score: float = 0.0
    quality_grade: str = 'F'
    issues: List[str] = field(default_factory=list)
    # Per-bone-channel detail for debugging
    per_channel_scores: Dict[str, Dict[str, float]] = field(default_factory=dict)


# ============================================================================
# QualityAuditReport
# ============================================================================

@dataclass
class QualityAuditReport:
    """Full audit report for all converted models."""
    timestamp: str = ''
    total_models: int = 0
    total_animations: int = 0
    # Summary statistics
    c0_perfect_rate: float = 0.0
    c1_perfect_rate: float = 0.0
    naturalness_avg: float = 0.0
    naturalness_below_threshold: int = 0
    amplitude_retention_avg: float = 0.0
    amplitude_below_threshold: int = 0
    # Per-animation metrics
    animation_metrics: Dict[str, ConversionQualityMetrics] = field(default_factory=dict)
    # Category summaries {category: {metric_name: value}}
    category_summaries: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # Problem models
    critical_issues: List[Dict[str, Any]] = field(default_factory=list)
    important_issues: List[Dict[str, Any]] = field(default_factory=list)
    # Comparison with previous report
    improvement_over_previous: Optional[Dict[str, float]] = None
    # Thresholds used
    thresholds_used: str = 'default'
    # Quality grade distribution
    grade_distribution: Dict[str, int] = field(default_factory=dict)


# ============================================================================
# BBModel Parser (source file reader)
# ============================================================================

def _parse_bbmodel_keyframes(animator_data: Dict) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
    """Parse keyframes from a bbmodel animator into {channel: {axis: [(time, value), ...]}}.

    bbmodel keyframe format:
    {
      "channel": "rotation" or "position",
      "data_points": [{"x": ..., "y": ..., "z": ...}],
      "time": 0.0,
      "interpolation": "catmullrom" | "linear" | "step"
    }
    """
    channels: Dict[str, Dict[str, List[Tuple[float, float]]]] = {}
    keyframes = animator_data.get('keyframes', [])
    if not keyframes:
        return channels

    for kf in keyframes:
        channel = kf.get('channel', 'rotation')
        t = kf.get('time', 0.0)
        data_points = kf.get('data_points', [])
        if not data_points:
            continue
        dp = data_points[0]

        for axis in ('x', 'y', 'z'):
            val = dp.get(axis, 0.0)
            if isinstance(val, (int, float)):
                if channel not in channels:
                    channels[channel] = {}
                if axis not in channels[channel]:
                    channels[channel][axis] = []
                channels[channel][axis].append((t, val))

    # Sort by time
    for ch in channels.values():
        for axis in ch:
            ch[axis].sort(key=lambda p: p[0])

    return channels


def _compute_channel_amplitude(keyframes: List[Tuple[float, float]]) -> Tuple[float, Tuple[float, float]]:
    """Compute amplitude and (min, max) for a list of (time, value) keyframes."""
    if not keyframes:
        return 0.0, (0.0, 0.0)
    values = [v for _, v in keyframes]
    mn = min(values)
    mx = max(values)
    return mx - mn, (mn, mx)


def _classify_animation(name: str) -> str:
    """Classify an animation name into a category."""
    name_lower = name.lower()
    if any(p in name_lower for p in ('walk', 'run', 'sprint', 'move', 'crawl', 'swim', 'gallop', 'trot', 'strafe')):
        return 'walk'
    if any(p in name_lower for p in ('idle', 'rest', 'breathing', 'ambient', 'stand', 'pose')):
        return 'idle'
    if any(p in name_lower for p in ('attack', 'hit', 'strike', 'slash', 'bite', 'shoot', 'hurt')):
        return 'attack'
    if any(p in name_lower for p in ('sleep', 'sleeping', 'lay', 'lying')):
        return 'sleep'
    if any(p in name_lower for p in ('death', 'die', 'dying', 'dead')):
        return 'death'
    if any(p in name_lower for p in ('evolved', 'transform', 'mutate')):
        return 'evolved'
    if any(p in name_lower for p in ('fly', 'flap', 'glide')):
        return 'fly'
    return 'other'


# ============================================================================
# Converted Animation Parser (output .animation.json reader)
# ============================================================================

def _parse_converted_channel(channel_data: Any) -> List[Tuple[float, float]]:
    """Parse a single channel from converted .animation.json format.

    Channel data can be:
      - Dict of {time_str: value} or {time_str: {"vector": value, "easing": ...}}
      - List [x, y, z] for single-point channels
    """
    keyframes = []

    if isinstance(channel_data, dict):
        for time_str, val in channel_data.items():
            try:
                t = float(time_str)
            except (ValueError, TypeError):
                continue
            if isinstance(val, dict):
                v = val.get('vector', 0.0)
            elif isinstance(val, (int, float)):
                v = val
            else:
                continue
            keyframes.append((t, float(v)))
    elif isinstance(channel_data, list):
        # Single value (common for position channels with one keyframe)
        if len(channel_data) >= 1:
            keyframes.append((0.0, float(channel_data[0])))

    keyframes.sort(key=lambda p: p[0])
    return keyframes


def _extract_converted_bones(anim_data: Dict) -> Dict[str, Dict[str, Dict[str, List[Tuple[float, float]]]]]:
    """Extract bone channel data from converted .animation.json animation entry.

    Returns {bone_name: {channel: {axis: [(time, value), ...]}}}
    """
    result: Dict[str, Dict[str, Dict[str, List[Tuple[float, float]]]]] = {}
    bones = anim_data.get('bones', {})

    for bone_name, bone_data in bones.items():
        channels: Dict[str, Dict[str, List[Tuple[float, float]]]] = {}

        for channel_name in ('rotation', 'position'):
            ch_data = bone_data.get(channel_name)
            if ch_data is None:
                continue

            if isinstance(ch_data, dict):
                # {axis: {time: value}}
                for axis in ('x', 'y', 'z'):
                    axis_data = ch_data.get(axis)
                    if axis_data is not None:
                        kfs = _parse_converted_channel(axis_data)
                        if kfs:
                            if channel_name not in channels:
                                channels[channel_name] = {}
                            channels[channel_name][axis] = kfs

        if channels:
            result[bone_name] = channels

    return result


# ============================================================================
# QualityAuditSystem
# ============================================================================

class QualityAuditSystem:
    """Comprehensive quality audit system for animation conversion."""

    def __init__(self, thresholds: str = 'default'):
        """Initialize with threshold mode ('strict', 'default', or 'lenient')."""
        self.thresholds = QualityThresholds(thresholds)
        self.warnings: List[str] = []

    # ------------------------------------------------------------------
    # Source Scanning
    # ------------------------------------------------------------------

    def scan_source_files(self, source_dir: str) -> Dict[str, List[SourceAnimationProfile]]:
        """Scan all source .bbmodel files and build expected profiles.

        Returns {model_name: [SourceAnimationProfile, ...]}
        """
        profiles: Dict[str, List[SourceAnimationProfile]] = {}
        source_path = Path(source_dir)

        if not source_path.exists():
            self.warnings.append(f"Source directory does not exist: {source_dir}")
            return profiles

        bbmodel_files = list(source_path.rglob('*.bbmodel'))
        if not bbmodel_files:
            self.warnings.append(f"No .bbmodel files found in {source_dir}")
            return profiles

        for bbmodel_file in bbmodel_files:
            try:
                with open(bbmodel_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                self.warnings.append(f"Failed to read {bbmodel_file}: {e}")
                continue

            model_name = data.get('name', bbmodel_file.stem)
            animations = data.get('animations', [])

            model_profiles = []
            for anim in animations:
                anim_name = anim.get('name', 'unknown')
                duration = anim.get('length', 0.0)
                loop = anim.get('loop', 'loop') in ('loop', True)

                animators = anim.get('animators', {})
                bone_names = list(animators.keys())
                num_bones = len(bone_names)

                # Extract keyframe data per bone
                source_amplitudes: Dict[str, Dict[str, float]] = {}
                source_peaks: Dict[str, Dict[str, Tuple[float, float]]] = {}
                source_keyframes: Dict[str, Dict[str, Dict[str, List[Tuple[float, float]]]]] = {}

                for bone_name, animator in animators.items():
                    if not isinstance(animator, dict):
                        continue
                    channels = _parse_bbmodel_keyframes(animator)
                    source_keyframes[bone_name] = channels

                    bone_amps: Dict[str, float] = {}
                    bone_peaks: Dict[str, Tuple[float, float]] = {}

                    for ch_name, axes in channels.items():
                        for axis, kfs in axes.items():
                            ch_key = f"{ch_name}_{axis}"
                            amp, peaks = _compute_channel_amplitude(kfs)
                            bone_amps[ch_key] = amp
                            bone_peaks[ch_key] = peaks

                    source_amplitudes[bone_name] = bone_amps
                    source_peaks[bone_name] = bone_peaks

                category = _classify_animation(anim_name)

                profile = SourceAnimationProfile(
                    model_name=model_name,
                    animation_name=anim_name,
                    num_bones=num_bones,
                    bone_names=bone_names,
                    duration=duration,
                    source_amplitudes=source_amplitudes,
                    source_peaks=source_peaks,
                    source_keyframes=source_keyframes,
                    loop=loop,
                    category=category,
                )
                model_profiles.append(profile)

            if model_profiles:
                profiles[model_name] = model_profiles

        return profiles

    # ------------------------------------------------------------------
    # Core Audit
    # ------------------------------------------------------------------

    def audit_converted_output(self, output_dir: str,
                                source_profiles: Dict[str, List[SourceAnimationProfile]]) -> QualityAuditReport:
        """Audit all converted output files against source profiles.

        Compares every converted .animation.json against its corresponding
        source .bbmodel profile and computes quality metrics.
        """
        report = QualityAuditReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            thresholds_used=self.thresholds.mode,
        )

        output_path = Path(output_dir)
        if not output_path.exists():
            self.warnings.append(f"Output directory does not exist: {output_dir}")
            return report

        # Map model_name -> converted .animation.json files
        # Convention: model_name.animation.json
        converted_files: Dict[str, Path] = {}
        for anim_file in output_path.rglob('*.animation.json'):
            # Derive model name from filename
            stem = anim_file.stem
            if stem.endswith('.animation'):
                model_name = stem[:-10]  # strip .animation
            else:
                model_name = stem
            converted_files[model_name] = anim_file

        # Also check for subdirectories (model_name/model_name.animation.json)
        for subdir in output_path.iterdir():
            if subdir.is_dir():
                for anim_file in subdir.rglob('*.animation.json'):
                    stem = anim_file.stem
                    if stem.endswith('.animation'):
                        model_name = stem[:-10]
                    else:
                        model_name = stem
                    if model_name not in converted_files:
                        converted_files[model_name] = anim_file

        report.total_models = len(source_profiles)

        for model_name, model_profiles in source_profiles.items():
            for profile in model_profiles:
                report.total_animations += 1

                # Find matching converted animation
                converted_data = self._find_converted_animation(
                    converted_files, model_name, profile.animation_name
                )

                metrics = self._compute_metrics(profile, converted_data, model_name)
                key = f"{model_name}/{profile.animation_name}"
                report.animation_metrics[key] = metrics

        # Compute summary statistics
        self._compute_report_summary(report)

        return report

    def _find_converted_animation(self, converted_files: Dict[str, Path],
                                   model_name: str, animation_name: str) -> Optional[Dict]:
        """Find a specific animation in the converted output files."""
        # Try direct model name match
        anim_path = converted_files.get(model_name)
        if anim_path is None:
            # Try stripped/normalized names
            for mn, mp in converted_files.items():
                if mn.lower() == model_name.lower():
                    anim_path = mp
                    break

        if anim_path is None or not anim_path.exists():
            return None

        try:
            with open(anim_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        animations = data.get('animations', {})
        # Direct match
        if animation_name in animations:
            return animations[animation_name]

        # Try matching by suffix
        for anim_key, anim_data in animations.items():
            if anim_key.endswith(animation_name) or animation_name.endswith(anim_key):
                return anim_data

        # Try partial match (the animation name from .bbmodel might differ from converted)
        name_suffix = animation_name.split('.')[-1] if '.' in animation_name else animation_name
        for anim_key, anim_data in animations.items():
            key_suffix = anim_key.split('.')[-1] if '.' in anim_key else anim_key
            if key_suffix == name_suffix:
                return anim_data

        return None

    def _compute_metrics(self, profile: SourceAnimationProfile,
                          converted_data: Optional[Dict],
                          model_name: str) -> ConversionQualityMetrics:
        """Compute quality metrics for a single animation."""
        metrics = ConversionQualityMetrics(
            model_name=model_name,
            animation_name=profile.animation_name,
            expected_bones=profile.num_bones,
            expected_duration=profile.duration,
        )

        issues: List[str] = []

        if converted_data is None:
            issues.append("CONVERSION_MISSING: No converted animation found")
            metrics.issues = issues
            metrics.quality_score = 0.0
            metrics.quality_grade = 'F'
            metrics.missing_bones = list(profile.bone_names)
            return metrics

        # Extract converted bone data
        converted_bones = _extract_converted_bones(converted_data)
        actual_duration = converted_data.get('animation_length', profile.duration)

        metrics.actual_bones = len(converted_bones)
        metrics.actual_duration = actual_duration

        # Check missing bones
        expected_set = set(profile.bone_names)
        actual_set = set(converted_bones.keys())
        metrics.missing_bones = sorted(list(expected_set - actual_set))
        if metrics.missing_bones:
            issues.append(f"MISSING_BONES: {len(metrics.missing_bones)} bones missing: "
                          f"{metrics.missing_bones[:5]}")

        # Duration mismatch
        duration_diff = abs(actual_duration - profile.duration)
        if duration_diff > 0.1:
            issues.append(f"DURATION_MISMATCH: expected {profile.duration:.4f}s, "
                          f"got {actual_duration:.4f}s (diff={duration_diff:.4f}s)")

        # C0/C1 continuity check (for loop animations)
        c0_errors_rot: List[float] = []
        c0_errors_pos: List[float] = []
        c1_errors_rot: List[float] = []
        c1_errors_pos: List[float] = []
        naturalness_scores: List[float] = []
        amplitude_retentions: Dict[str, float] = {}
        per_channel_scores: Dict[str, Dict[str, float]] = {}

        for bone_name, bone_channels in converted_bones.items():
            for channel_name, axes in bone_channels.items():
                for axis, kfs in axes.items():
                    ch_key = f"{bone_name}/{channel_name}/{axis}"

                    # Skip channels with too few keyframes for meaningful analysis
                    if len(kfs) < 2:
                        continue

                    times = [t for t, v in kfs]
                    values = [v for t, v in kfs]

                    # C0 continuity: check loop boundary
                    if profile.loop and len(times) >= 2:
                        first_val = values[0]
                        last_val = values[-1]
                        c0_err = abs(last_val - first_val)

                        if channel_name == 'rotation':
                            c0_errors_rot.append(c0_err)
                        else:
                            c0_errors_pos.append(c0_err)

                    # C1 continuity: check velocity at loop boundary
                    if profile.loop and len(times) >= 3:
                        dur = times[-1] - times[0]
                        if dur > 1e-6:
                            # Velocity at start
                            v_start = (values[1] - values[0]) / max(times[1] - times[0], 1e-9)
                            # Velocity at end
                            v_end = (values[-1] - values[-2]) / max(times[-1] - times[-2], 1e-9)
                            c1_err = abs(v_end - v_start)

                            if channel_name == 'rotation':
                                c1_errors_rot.append(c1_err)
                            else:
                                c1_errors_pos.append(c1_err)

                    # Naturalness
                    nat = self.compute_curvature_naturalness_for_channel(
                        times, values, actual_duration
                    )
                    naturalness_scores.append(nat)
                    per_channel_scores[ch_key] = {'naturalness': nat}

                    # Amplitude retention
                    source_amp = 0.0
                    if bone_name in profile.source_amplitudes:
                        ch_amp_key = f"{channel_name}_{axis}"
                        source_amp = profile.source_amplitudes[bone_name].get(ch_amp_key, 0.0)

                    conv_amp, _ = _compute_channel_amplitude(kfs)

                    if source_amp > 0.01:
                        retention = conv_amp / source_amp
                        retention = min(retention, 2.0)  # Cap at 2x (gain isn't really >100%)
                        amplitude_retentions[ch_key] = retention
                        per_channel_scores[ch_key]['amplitude_retention'] = retention

                        if retention < self.thresholds.amplitude_retention:
                            metrics.channels_with_amplitude_loss.append(ch_key)
                    else:
                        # Source amplitude near zero — if converted is also near zero, that's fine
                        amplitude_retentions[ch_key] = 1.0 if conv_amp < 0.1 else 0.0
                        per_channel_scores[ch_key]['amplitude_retention'] = amplitude_retentions[ch_key]

        # Aggregate C0
        metrics.c0_max_error_rot = max(c0_errors_rot) if c0_errors_rot else 0.0
        metrics.c0_max_error_pos = max(c0_errors_pos) if c0_errors_pos else 0.0
        metrics.c0_perfect = (metrics.c0_max_error_rot <= self.thresholds.c0_rot and
                              metrics.c0_max_error_pos <= self.thresholds.c0_pos)

        # Aggregate C1
        metrics.c1_max_error_rot = max(c1_errors_rot) if c1_errors_rot else 0.0
        if c1_errors_rot:
            sorted_c1 = sorted(c1_errors_rot)
            p90_idx = int(len(sorted_c1) * 0.9)
            metrics.c1_p90_error_rot = sorted_c1[min(p90_idx, len(sorted_c1) - 1)]
        metrics.c1_perfect = (metrics.c1_max_error_rot <= self.thresholds.c1_rot)

        # Aggregate naturalness
        if naturalness_scores:
            metrics.naturalness_score = sum(naturalness_scores) / len(naturalness_scores)
        else:
            metrics.naturalness_score = 1.0  # No channels to evaluate = perfect by default

        # Aggregate amplitude retention
        if amplitude_retentions:
            metrics.amplitude_retention_avg = sum(amplitude_retentions.values()) / len(amplitude_retentions)
            metrics.amplitude_retention_min = min(amplitude_retentions.values())
        else:
            metrics.amplitude_retention_avg = 1.0
            metrics.amplitude_retention_min = 1.0

        # Check thresholds for issues
        if not metrics.c0_perfect:
            issues.append(f"C0_ERROR: max rotation error {metrics.c0_max_error_rot:.4f} deg "
                          f"(threshold {self.thresholds.c0_rot})")
        if not metrics.c1_perfect:
            issues.append(f"C1_ERROR: max rotation error {metrics.c1_max_error_rot:.4f} deg/s "
                          f"(threshold {self.thresholds.c1_rot})")
        if metrics.naturalness_score < self.thresholds.naturalness:
            issues.append(f"LOW_NATURALNESS: score {metrics.naturalness_score:.4f} "
                          f"(threshold {self.thresholds.naturalness})")
        if metrics.amplitude_retention_min < self.thresholds.amplitude_retention:
            issues.append(f"AMPLITUDE_LOSS: min retention {metrics.amplitude_retention_min:.4f} "
                          f"(threshold {self.thresholds.amplitude_retention})")

        # Compute overall quality score (0-100)
        metrics.quality_score = self._compute_quality_score(metrics)
        metrics.quality_grade = self._compute_quality_grade(metrics.quality_score)
        metrics.issues = issues
        metrics.per_channel_scores = per_channel_scores

        return metrics

    def _compute_quality_score(self, metrics: ConversionQualityMetrics) -> float:
        """Compute a 0-100 quality score from individual metrics."""
        # Weighted combination
        score = 0.0

        # C0 continuity (weight 25%)
        if metrics.c0_perfect:
            c0_score = 1.0
        else:
            # Exponential decay from threshold
            if self.thresholds.c0_rot > 0:
                ratio = metrics.c0_max_error_rot / self.thresholds.c0_rot
                c0_score = max(0.0, math.exp(-(ratio - 1.0) * 2.0))
            else:
                c0_score = 0.0 if metrics.c0_max_error_rot > 0 else 1.0
        score += c0_score * 25.0

        # C1 continuity (weight 20%)
        if metrics.c1_perfect:
            c1_score = 1.0
        else:
            if self.thresholds.c1_rot > 0:
                ratio = metrics.c1_max_error_rot / self.thresholds.c1_rot
                c1_score = max(0.0, math.exp(-(ratio - 1.0) * 1.5))
            else:
                c1_score = 0.0 if metrics.c1_max_error_rot > 0 else 1.0
        score += c1_score * 20.0

        # Naturalness (weight 25%)
        nat_score = min(1.0, max(0.0, metrics.naturalness_score))
        score += nat_score * 25.0

        # Amplitude retention (weight 20%)
        amp_score = min(1.0, max(0.0, metrics.amplitude_retention_avg))
        score += amp_score * 20.0

        # Completeness (weight 10%)
        if metrics.expected_bones > 0:
            completeness = metrics.actual_bones / metrics.expected_bones
        else:
            completeness = 1.0
        score += min(1.0, completeness) * 10.0

        return round(score, 2)

    def _compute_quality_grade(self, score: float) -> str:
        """Convert a 0-100 score to a letter grade."""
        frac = score / 100.0
        if frac >= self.thresholds.grade_a_min:
            return 'A'
        elif frac >= self.thresholds.grade_b_min:
            return 'B'
        elif frac >= self.thresholds.grade_c_min:
            return 'C'
        elif frac >= self.thresholds.grade_d_min:
            return 'D'
        else:
            return 'F'

    # ------------------------------------------------------------------
    # Amplitude Retention
    # ------------------------------------------------------------------

    def compute_amplitude_retention(self, source_profile: SourceAnimationProfile,
                                     converted_animation: Dict) -> Dict[str, float]:
        """Compare source vs converted amplitude for each channel.

        Returns {channel_key: retention_ratio} where retention = converted_amp / source_amp.
        """
        result: Dict[str, float] = {}
        converted_bones = _extract_converted_bones(converted_animation)

        for bone_name, bone_channels in converted_bones.items():
            for channel_name, axes in bone_channels.items():
                for axis, kfs in axes.items():
                    ch_key = f"{bone_name}/{channel_name}/{axis}"
                    conv_amp, _ = _compute_channel_amplitude(kfs)

                    source_amp = 0.0
                    if bone_name in source_profile.source_amplitudes:
                        ch_amp_key = f"{channel_name}_{axis}"
                        source_amp = source_profile.source_amplitudes[bone_name].get(ch_amp_key, 0.0)

                    if source_amp > 0.01:
                        result[ch_key] = min(conv_amp / source_amp, 2.0)
                    else:
                        result[ch_key] = 1.0 if conv_amp < 0.1 else 0.0

        return result

    # ------------------------------------------------------------------
    # Curvature-Based Naturalness (KEY INNOVATION)
    # ------------------------------------------------------------------

    def compute_curvature_naturalness(self, bone_channels: Dict, duration: float) -> float:
        """Compute naturalness using curvature smoothness.

        This replaces the legacy sign-change counting method which incorrectly
        classified 78.8% of animations as unnatural.

        Method:
        1. Resample each channel at uniform rate (120Hz)
        2. Compute first and second derivatives numerically
        3. For rotation channels: measure acceleration smoothness
           (how gradually acceleration changes)
        4. Use a robust scoring method that doesn't penalize high-frequency
           but smooth oscillations (like walk cycles)
        5. Score periodic animations based on how well they match a
           sinusoidal template

        Args:
            bone_channels: Dict with channel data structure.
                Can be either:
                - {channel_name: {axis: [(time, value), ...]}} (from source)
                - A dict from converted bone data
            duration: Animation duration in seconds

        Returns:
            Naturalness score in [0, 1] where 1.0 = perfectly natural.
        """
        all_scores: List[float] = []

        for channel_name, axes in bone_channels.items():
            if not isinstance(axes, dict):
                continue
            for axis, kfs in axes.items():
                if not isinstance(kfs, list) or len(kfs) < 2:
                    continue

                times = [t for t, v in kfs]
                values = [v for t, v in kfs]

                score = self.compute_curvature_naturalness_for_channel(
                    times, values, duration
                )
                all_scores.append(score)

        if not all_scores:
            return 1.0

        return sum(all_scores) / len(all_scores)

    def compute_curvature_naturalness_for_channel(self,
                                                    times: List[float],
                                                    values: List[float],
                                                    duration: float) -> float:
        """Compute curvature-based naturalness for a single channel.

        This is the core algorithm. It evaluates three components using
        scale-invariant, outlier-robust metrics:

        1. **Velocity predictability** (weight 0.4): How well can each
           velocity sample be predicted from its neighbors using linear
           extrapolation? Natural motion (including smooth sinusoids) is
           highly predictable; noisy/jerky motion is not. Measured as
           median relative prediction error with exponential decay scoring.

        2. **Acceleration smoothness** (weight 0.3): How gradually
           acceleration changes. Uses the median ratio |jerk|/|acc|
           (relative jerk) with exponential decay, which is scale-invariant
           and robust to outliers. A sinusoid has moderate relative jerk
           that scales with frequency, NOT with amplitude.

        3. **Velocity uniformity** (weight 0.3): How uniformly velocity
           changes. Uses percentile-based comparison (P90/median of |Δv|)
           with log-scaling, robust to spike artifacts.

        For periodic animations (walk cycles, breathing), a sinusoidal
        template matching bonus is applied — smooth periodic motion should
        score highly even though its curvature varies.

        KEY DESIGN PRINCIPLES:
        - All metrics are scale-invariant (normalized by signal magnitude)
        - Predictability-based: doesn't penalize smooth oscillations
        - Percentile-based (median, P90) for outlier robustness
        - Exponential/log decay to prevent extreme ratios from collapsing

        Args:
            times: List of keyframe times
            values: List of keyframe values
            duration: Animation duration in seconds

        Returns:
            Score in [0, 1]
        """
        if len(times) < 3 or duration < 1e-6:
            return 1.0

        # Check if signal is essentially constant
        value_range = max(values) - min(values)
        if value_range < 0.01:
            return 1.0

        # Step 1: Resample at 120Hz using Catmull-Rom
        resample_rate = 120.0
        n_samples = max(4, int(duration * resample_rate) + 1)

        # Use numpy if available for better performance
        if _NUMPY_AVAILABLE and len(times) >= 4:
            try:
                return self._compute_curvature_naturalness_numpy(times, values, duration, n_samples)
            except Exception:
                pass

        # Pure Python path
        _, resampled = _resample_channel_catmull(times, values, duration, resample_rate)

        if len(resampled) < 4:
            return 1.0

        dt = duration / max(len(resampled) - 1, 1)
        if dt < 1e-12:
            return 1.0

        # Step 2: Compute derivatives
        vel, acc, jerk = _compute_derivatives(resampled, dt)

        # Step 3: Compute component scores

        # 3a. Velocity predictability (weight 0.4)
        # For each sample i, predict v[i] from v[i-1] and v[i-2]:
        #   predicted = v[i-1] + (v[i-1] - v[i-2]) = 2*v[i-1] - v[i-2]
        # This is linear extrapolation. For a sinusoid (or any smooth curve),
        # the prediction error is O(dt²), which is very small at 120Hz.
        # For noisy/jerky motion, the error is much larger.
        if len(vel) >= 4:
            prediction_errors = []
            for i in range(2, len(vel)):
                predicted = 2.0 * vel[i - 1] - vel[i - 2]
                error = abs(vel[i] - predicted)
                # Normalize by signal amplitude to make scale-invariant
                local_scale = max(abs(vel[i]), abs(vel[i - 1]), 1e-6)
                relative_error = error / local_scale
                prediction_errors.append(relative_error)

            if prediction_errors:
                prediction_errors.sort()
                median_pred_err = prediction_errors[len(prediction_errors) // 2]
                # Exponential decay: small median error → high score
                # A sinusoid at 1Hz/120Hz has median_pred_err ≈ 0.001 → score ≈ 1.0
                # A noisy signal has median_pred_err ≈ 0.5 → score ≈ 0.6
                velocity_predictability = math.exp(-5.0 * median_pred_err)
            else:
                velocity_predictability = 1.0
        else:
            velocity_predictability = 1.0

        # 3b. Acceleration smoothness (weight 0.3)
        # Relative jerk = |jerk| / (|acc| + ε)
        # Use MEDIAN for robustness to outlier spikes
        if len(acc) >= 3 and len(jerk) >= 3:
            relative_jerks = []
            for i in range(len(jerk)):
                rel = abs(jerk[i]) / (abs(acc[i]) + 1e-6)
                relative_jerks.append(rel)
            relative_jerks.sort()
            median_rel_jerk = relative_jerks[len(relative_jerks) // 2]

            # For a sinusoid at frequency f sampled at rate R:
            #   rel_jerk ≈ 2πf / R * R = 2πf (approximately)
            # At 1Hz: rel_jerk ≈ 6.3 → exp(-0.02*6.3) ≈ 0.88 ✓
            # At 2Hz: rel_jerk ≈ 12.6 → exp(-0.02*12.6) ≈ 0.78 ✓
            # For jerky motion: rel_jerk >> 50 → score drops
            acceleration_smoothness = math.exp(-0.02 * median_rel_jerk)
        else:
            acceleration_smoothness = 1.0

        # 3c. Velocity uniformity (weight 0.3)
        # Compare P90 of |Δv| to median of |Δv|
        vel_changes = [abs(vel[i] - vel[i - 1]) for i in range(1, len(vel))]
        if len(vel_changes) >= 3:
            vel_changes_sorted = sorted(vel_changes)
            median_vc = vel_changes_sorted[len(vel_changes_sorted) // 2]
            p90_idx = int(len(vel_changes_sorted) * 0.9)
            p90_vc = vel_changes_sorted[min(p90_idx, len(vel_changes_sorted) - 1)]

            if median_vc > 1e-10:
                spike_ratio = p90_vc / median_vc
                # Log-scaling: ratio of 2 → 0.69, ratio of 5 → 0.55
                velocity_uniformity = 1.0 / (1.0 + math.log1p(spike_ratio - 1.0))
            else:
                velocity_uniformity = 1.0
        else:
            velocity_uniformity = 1.0

        # Step 4: Weighted combination
        score = (
            0.4 * velocity_predictability +
            0.3 * acceleration_smoothness +
            0.3 * velocity_uniformity
        )

        # Step 5: Periodic animation bonus
        sin_score = _sinusoidal_fit_score(resampled, dt)
        if sin_score > 0.7:
            # Periodic and smooth — boost the score
            boost = 0.20 * sin_score  # Up to +0.20 bonus
            score = min(1.0, score + boost)

        return max(0.0, min(1.0, score))

    def _compute_curvature_naturalness_numpy(self, times: List[float], values: List[float],
                                              duration: float, n_samples: int) -> float:
        """Numpy-accelerated curvature naturalness computation.

        Uses the same robust normalization as the pure-Python version.
        """
        times_arr = np.array(times)
        values_arr = np.array(values)

        # Resample using numpy interpolation (linear for speed, then smooth)
        sample_times = np.linspace(0.0, duration, n_samples)
        resampled = np.interp(sample_times, times_arr, values_arr)

        if len(resampled) < 4:
            return 1.0

        dt = duration / max(len(resampled) - 1, 1)
        if dt < 1e-12:
            return 1.0

        # Compute derivatives using numpy gradient (central differences)
        vel = np.gradient(resampled, dt)
        acc = np.gradient(vel, dt)
        jerk = np.gradient(acc, dt)

        # Velocity predictability
        if len(vel) >= 4:
            predicted = 2.0 * vel[1:-1] - vel[:-2]
            actual = vel[2:]
            errors = np.abs(actual - predicted)
            local_scale = np.maximum(np.abs(actual), np.abs(vel[1:-1]))
            local_scale = np.maximum(local_scale, 1e-6)
            relative_errors = errors / local_scale
            median_pred_err = float(np.median(relative_errors))
            velocity_predictability = math.exp(-5.0 * median_pred_err)
        else:
            velocity_predictability = 1.0

        # Acceleration smoothness (relative jerk, median-based)
        if len(acc) >= 3 and len(jerk) >= 3:
            relative_jerks = np.abs(jerk) / (np.abs(acc) + 1e-6)
            median_rel_jerk = float(np.median(relative_jerks))
            acceleration_smoothness = math.exp(-0.02 * median_rel_jerk)
        else:
            acceleration_smoothness = 1.0

        # Velocity uniformity (percentile-based)
        vel_changes = np.abs(np.diff(vel))
        if len(vel_changes) >= 3:
            median_vc = float(np.median(vel_changes))
            p90_vc = float(np.percentile(vel_changes, 90))

            if median_vc > 1e-10:
                spike_ratio = p90_vc / median_vc
                velocity_uniformity = 1.0 / (1.0 + math.log1p(spike_ratio - 1.0))
            else:
                velocity_uniformity = 1.0
        else:
            velocity_uniformity = 1.0

        # Weighted combination
        score = (
            0.4 * velocity_predictability +
            0.3 * acceleration_smoothness +
            0.3 * velocity_uniformity
        )

        # Periodic animation bonus
        sin_score = _sinusoidal_fit_score(resampled.tolist(), dt)
        if sin_score > 0.7:
            boost = 0.20 * sin_score
            score = min(1.0, score + boost)

        return max(0.0, min(1.0, score))

    # ------------------------------------------------------------------
    # Report Generation
    # ------------------------------------------------------------------

    def generate_report_json(self, report: QualityAuditReport, output_path: str):
        """Generate JSON report."""
        report_dict = self._report_to_dict(report)

        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report_dict, f, indent=2, default=str, ensure_ascii=False)

    def generate_report_markdown(self, report: QualityAuditReport, output_path: str):
        """Generate Markdown report with tables and summaries."""
        lines: List[str] = []

        lines.append("# Quality Audit Report")
        lines.append("")
        lines.append(f"**Timestamp:** {report.timestamp}")
        lines.append(f"**Threshold Mode:** {report.thresholds_used}")
        lines.append(f"**Total Models:** {report.total_models}")
        lines.append(f"**Total Animations:** {report.total_animations}")
        lines.append("")

        # 1. Executive Summary Table
        lines.append("## 1. Executive Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| C0 Perfect Rate | {report.c0_perfect_rate:.1%} |")
        lines.append(f"| C1 Perfect Rate | {report.c1_perfect_rate:.1%} |")
        lines.append(f"| Average Naturalness | {report.naturalness_avg:.4f} |")
        lines.append(f"| Naturalness Below Threshold | {report.naturalness_below_threshold} |")
        lines.append(f"| Average Amplitude Retention | {report.amplitude_retention_avg:.4f} |")
        lines.append(f"| Amplitude Below Threshold | {report.amplitude_below_threshold} |")
        lines.append(f"| Critical Issues | {len(report.critical_issues)} |")
        lines.append(f"| Important Issues | {len(report.important_issues)} |")
        lines.append("")

        # 2. Overall Statistics
        lines.append("## 2. Overall Statistics")
        lines.append("")
        if report.animation_metrics:
            scores = [m.quality_score for m in report.animation_metrics.values()]
            nat_scores = [m.naturalness_score for m in report.animation_metrics.values()]
            c0_errs = [m.c0_max_error_rot for m in report.animation_metrics.values()]
            c1_errs = [m.c1_max_error_rot for m in report.animation_metrics.values()]

            lines.append("| Statistic | Quality Score | Naturalness | C0 Max Error (deg) | C1 Max Error (deg/s) |")
            lines.append("|-----------|--------------|-------------|--------------------|---------------------|")
            lines.append(f"| Mean | {sum(scores)/len(scores):.2f} | {sum(nat_scores)/len(nat_scores):.4f} | "
                         f"{sum(c0_errs)/len(c0_errs):.4f} | {sum(c1_errs)/len(c1_errs):.4f} |")
            lines.append(f"| Min | {min(scores):.2f} | {min(nat_scores):.4f} | "
                         f"{min(c0_errs):.4f} | {min(c1_errs):.4f} |")
            lines.append(f"| Max | {max(scores):.2f} | {max(nat_scores):.4f} | "
                         f"{max(c0_errs):.4f} | {max(c1_errs):.4f} |")
        lines.append("")

        # 3. Quality Grade Distribution
        lines.append("## 3. Quality Grade Distribution")
        lines.append("")
        grade_order = ['A', 'B', 'C', 'D', 'F']
        total = sum(report.grade_distribution.values()) or 1
        for grade in grade_order:
            count = report.grade_distribution.get(grade, 0)
            pct = count / total * 100
            bar = '█' * int(pct / 2)
            lines.append(f"  {grade}: {count:3d} ({pct:5.1f}%) {bar}")
        lines.append("")

        # 4. Per-Category Breakdown Table
        lines.append("## 4. Per-Category Breakdown")
        lines.append("")
        if report.category_summaries:
            lines.append("| Category | Count | Avg Score | Avg Naturalness | C0 Perfect % | C1 Perfect % |")
            lines.append("|----------|-------|-----------|----------------|-------------|-------------|")
            for cat, stats in sorted(report.category_summaries.items()):
                count = int(stats.get('count', 0))
                avg_score = stats.get('avg_quality_score', 0.0)
                avg_nat = stats.get('avg_naturalness', 0.0)
                c0_pct = stats.get('c0_perfect_rate', 0.0) * 100
                c1_pct = stats.get('c1_perfect_rate', 0.0) * 100
                lines.append(f"| {cat} | {count} | {avg_score:.1f} | {avg_nat:.4f} | "
                             f"{c0_pct:.1f}% | {c1_pct:.1f}% |")
        lines.append("")

        # 5. Critical Issues List
        lines.append("## 5. Critical Issues")
        lines.append("")
        if report.critical_issues:
            for i, issue in enumerate(report.critical_issues[:20], 1):
                lines.append(f"{i}. **{issue.get('model', '?')}/{issue.get('animation', '?')}**: "
                             f"{issue.get('description', 'Unknown')}")
        else:
            lines.append("_No critical issues found._")
        lines.append("")

        # 6. Important Issues List
        lines.append("## 6. Important Issues")
        lines.append("")
        if report.important_issues:
            for i, issue in enumerate(report.important_issues[:20], 1):
                lines.append(f"{i}. **{issue.get('model', '?')}/{issue.get('animation', '?')}**: "
                             f"{issue.get('description', 'Unknown')}")
        else:
            lines.append("_No important issues found._")
        lines.append("")

        # 7. Top 10 Worst Animations
        lines.append("## 7. Top 10 Worst Animations")
        lines.append("")
        sorted_metrics = sorted(report.animation_metrics.values(), key=lambda m: m.quality_score)
        worst = sorted_metrics[:10]
        if worst:
            lines.append("| # | Animation | Score | Grade | C0 Error | C1 Error | Naturalness | Amp Retention |")
            lines.append("|---|-----------|-------|-------|----------|----------|-------------|--------------|")
            for i, m in enumerate(worst, 1):
                lines.append(f"| {i} | {m.model_name}/{m.animation_name} | {m.quality_score:.1f} | "
                             f"{m.quality_grade} | {m.c0_max_error_rot:.4f} | {m.c1_max_error_rot:.4f} | "
                             f"{m.naturalness_score:.4f} | {m.amplitude_retention_avg:.4f} |")
        lines.append("")

        # 8. Amplitude Retention Analysis
        lines.append("## 8. Amplitude Retention Analysis")
        lines.append("")
        all_retentions: List[float] = []
        channels_below: List[Tuple[str, str, float]] = []
        for key, m in report.animation_metrics.items():
            for ch_key, scores in m.per_channel_scores.items():
                ret = scores.get('amplitude_retention', 1.0)
                all_retentions.append(ret)
                if ret < self.thresholds.amplitude_retention:
                    channels_below.append((key, ch_key, ret))

        if all_retentions:
            lines.append(f"- **Average retention:** {sum(all_retentions)/len(all_retentions):.4f}")
            lines.append(f"- **Minimum retention:** {min(all_retentions):.4f}")
            lines.append(f"- **Channels below threshold:** {len(channels_below)}")
            if channels_below:
                lines.append("")
                lines.append("Worst retention channels:")
                channels_below.sort(key=lambda x: x[2])
                for anim_key, ch_key, ret in channels_below[:10]:
                    lines.append(f"  - {anim_key} / {ch_key}: {ret:.4f}")
        lines.append("")

        # 9. Naturalness Analysis
        lines.append("## 9. Naturalness Analysis")
        lines.append("")
        lines.append(f"- **Method:** curvature_smoothness (replaces legacy sign-change counting)")
        lines.append(f"- **Average naturalness:** {report.naturalness_avg:.4f}")
        lines.append(f"- **Below threshold ({self.thresholds.naturalness}):** "
                     f"{report.naturalness_below_threshold} animations")

        low_nat = [(key, m) for key, m in report.animation_metrics.items()
                    if m.naturalness_score < self.thresholds.naturalness]
        if low_nat:
            low_nat.sort(key=lambda x: x[1].naturalness_score)
            lines.append("")
            lines.append("Animations with lowest naturalness:")
            for anim_key, m in low_nat[:10]:
                lines.append(f"  - {anim_key}: {m.naturalness_score:.4f} "
                             f"(method: {m.naturalness_method})")
        lines.append("")

        # 10. Improvement Over Previous
        lines.append("## 10. Improvement Over Previous")
        lines.append("")
        if report.improvement_over_previous:
            for metric, delta in report.improvement_over_previous.items():
                direction = "↑" if delta > 0 else "↓"
                lines.append(f"- **{metric}:** {delta:+.4f} {direction}")
        else:
            lines.append("_No previous report available for comparison._")
        lines.append("")

        # Write the file
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

    # ------------------------------------------------------------------
    # History Tracking
    # ------------------------------------------------------------------

    def compare_with_history(self, report: QualityAuditReport, history_dir: str) -> Dict[str, float]:
        """Compare current report with previous reports to track improvement.

        Returns {metric_name: delta} where positive delta = improvement.
        """
        history_path = Path(history_dir)
        if not history_path.exists():
            return {}

        # Find the most recent previous report
        history_files = sorted(history_path.glob('audit_*.json'))
        if not history_files:
            return {}

        latest = history_files[-1]
        try:
            with open(latest, 'r', encoding='utf-8') as f:
                prev_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

        deltas: Dict[str, float] = {}

        # Compare key metrics
        prev_c0 = prev_data.get('c0_perfect_rate', 0.0)
        prev_c1 = prev_data.get('c1_perfect_rate', 0.0)
        prev_nat = prev_data.get('naturalness_avg', 0.0)
        prev_amp = prev_data.get('amplitude_retention_avg', 0.0)

        if isinstance(prev_c0, (int, float)):
            deltas['c0_perfect_rate'] = report.c0_perfect_rate - float(prev_c0)
        if isinstance(prev_c1, (int, float)):
            deltas['c1_perfect_rate'] = report.c1_perfect_rate - float(prev_c1)
        if isinstance(prev_nat, (int, float)):
            deltas['naturalness_avg'] = report.naturalness_avg - float(prev_nat)
        if isinstance(prev_amp, (int, float)):
            deltas['amplitude_retention_avg'] = report.amplitude_retention_avg - float(prev_amp)

        return deltas

    def save_history(self, report: QualityAuditReport, history_dir: str):
        """Save report to history for trend tracking."""
        history_path = Path(history_dir)
        history_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"audit_{timestamp}.json"
        filepath = history_path / filename

        report_dict = self._report_to_dict(report)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report_dict, f, indent=2, default=str, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _compute_report_summary(self, report: QualityAuditReport):
        """Compute summary statistics from per-animation metrics."""
        if not report.animation_metrics:
            return

        metrics_list = list(report.animation_metrics.values())
        n = len(metrics_list)

        # C0/C1 perfect rates
        c0_perfect_count = sum(1 for m in metrics_list if m.c0_perfect)
        c1_perfect_count = sum(1 for m in metrics_list if m.c1_perfect)
        report.c0_perfect_rate = c0_perfect_count / n if n > 0 else 0.0
        report.c1_perfect_rate = c1_perfect_count / n if n > 0 else 0.0

        # Naturalness
        nat_scores = [m.naturalness_score for m in metrics_list]
        report.naturalness_avg = sum(nat_scores) / n if n > 0 else 0.0
        report.naturalness_below_threshold = sum(
            1 for s in nat_scores if s < self.thresholds.naturalness
        )

        # Amplitude retention
        amp_avgs = [m.amplitude_retention_avg for m in metrics_list]
        report.amplitude_retention_avg = sum(amp_avgs) / n if n > 0 else 0.0
        report.amplitude_below_threshold = sum(
            1 for a in amp_avgs if a < self.thresholds.amplitude_retention
        )

        # Grade distribution
        grade_dist: Dict[str, int] = defaultdict(int)
        for m in metrics_list:
            grade_dist[m.quality_grade] += 1
        report.grade_distribution = dict(grade_dist)

        # Category summaries
        cat_metrics: Dict[str, List[ConversionQualityMetrics]] = defaultdict(list)
        for key, m in report.animation_metrics.items():
            # Extract category from animation name
            cat = _classify_animation(m.animation_name)
            cat_metrics[cat].append(m)

        for cat, cat_list in cat_metrics.items():
            cn = len(cat_list)
            report.category_summaries[cat] = {
                'count': cn,
                'avg_quality_score': sum(m.quality_score for m in cat_list) / cn,
                'avg_naturalness': sum(m.naturalness_score for m in cat_list) / cn,
                'c0_perfect_rate': sum(1 for m in cat_list if m.c0_perfect) / cn,
                'c1_perfect_rate': sum(1 for m in cat_list if m.c1_perfect) / cn,
                'avg_amplitude_retention': sum(m.amplitude_retention_avg for m in cat_list) / cn,
            }

        # Critical issues: C0 > 5 deg or missing animations
        for m in metrics_list:
            if m.c0_max_error_rot > 5.0:
                report.critical_issues.append({
                    'model': m.model_name,
                    'animation': m.animation_name,
                    'description': f"C0 error {m.c0_max_error_rot:.2f} deg exceeds 5 deg critical threshold",
                    'severity': 'critical',
                    'metric': 'c0_max_error_rot',
                    'value': m.c0_max_error_rot,
                })
            if m.missing_bones:
                report.critical_issues.append({
                    'model': m.model_name,
                    'animation': m.animation_name,
                    'description': f"Missing {len(m.missing_bones)} bones: {m.missing_bones[:3]}",
                    'severity': 'critical',
                    'metric': 'missing_bones',
                    'value': len(m.missing_bones),
                })

        # Important issues: poor C1 or low naturalness
        for m in metrics_list:
            if m.c1_max_error_rot > self.thresholds.c1_rot * 3:
                report.important_issues.append({
                    'model': m.model_name,
                    'animation': m.animation_name,
                    'description': f"C1 error {m.c1_max_error_rot:.2f} deg/s is >3x threshold "
                                   f"({self.thresholds.c1_rot * 3:.2f})",
                    'severity': 'important',
                    'metric': 'c1_max_error_rot',
                    'value': m.c1_max_error_rot,
                })
            if m.naturalness_score < self.thresholds.naturalness * 0.5:
                report.important_issues.append({
                    'model': m.model_name,
                    'animation': m.animation_name,
                    'description': f"Naturalness {m.naturalness_score:.4f} is <50% of threshold "
                                   f"({self.thresholds.naturalness})",
                    'severity': 'important',
                    'metric': 'naturalness_score',
                    'value': m.naturalness_score,
                })

        # Sort issues by severity
        report.critical_issues.sort(key=lambda x: x.get('value', 0), reverse=True)
        report.important_issues.sort(key=lambda x: x.get('value', 0), reverse=True)

    def _report_to_dict(self, report: QualityAuditReport) -> Dict[str, Any]:
        """Convert report to a JSON-serializable dictionary."""
        result: Dict[str, Any] = {
            'timestamp': report.timestamp,
            'total_models': report.total_models,
            'total_animations': report.total_animations,
            'c0_perfect_rate': report.c0_perfect_rate,
            'c1_perfect_rate': report.c1_perfect_rate,
            'naturalness_avg': report.naturalness_avg,
            'naturalness_below_threshold': report.naturalness_below_threshold,
            'amplitude_retention_avg': report.amplitude_retention_avg,
            'amplitude_below_threshold': report.amplitude_below_threshold,
            'thresholds_used': report.thresholds_used,
            'grade_distribution': report.grade_distribution,
            'category_summaries': report.category_summaries,
            'critical_issues': report.critical_issues,
            'important_issues': report.important_issues,
            'improvement_over_previous': report.improvement_over_previous,
        }

        # Per-animation metrics (serialize dataclass)
        anim_dict = {}
        for key, m in report.animation_metrics.items():
            anim_dict[key] = {
                'model_name': m.model_name,
                'animation_name': m.animation_name,
                'c0_max_error_rot': m.c0_max_error_rot,
                'c0_max_error_pos': m.c0_max_error_pos,
                'c0_perfect': m.c0_perfect,
                'c1_max_error_rot': m.c1_max_error_rot,
                'c1_p90_error_rot': m.c1_p90_error_rot,
                'c1_perfect': m.c1_perfect,
                'naturalness_score': m.naturalness_score,
                'naturalness_method': m.naturalness_method,
                'amplitude_retention_avg': m.amplitude_retention_avg,
                'amplitude_retention_min': m.amplitude_retention_min,
                'channels_with_amplitude_loss': m.channels_with_amplitude_loss,
                'expected_bones': m.expected_bones,
                'actual_bones': m.actual_bones,
                'missing_bones': m.missing_bones,
                'expected_duration': m.expected_duration,
                'actual_duration': m.actual_duration,
                'quality_score': m.quality_score,
                'quality_grade': m.quality_grade,
                'issues': m.issues,
            }
        result['animation_metrics'] = anim_dict

        # Thresholds
        result['thresholds'] = self.thresholds.to_dict()

        return result


# ============================================================================
# CLI Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Quality Audit System for Animation Conversion',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python quality_audit_system.py --source-dir ./bbmodels --output-dir ./output --thresholds default
  python quality_audit_system.py --source-dir ./source --output-dir ./converted --thresholds strict --report-dir ./reports
        """
    )
    parser.add_argument('--source-dir', required=True,
                        help='Directory containing source .bbmodel files')
    parser.add_argument('--output-dir', required=True,
                        help='Directory containing converted .animation.json files')
    parser.add_argument('--thresholds', choices=['strict', 'default', 'lenient'],
                        default='default',
                        help='Quality threshold mode (default: default)')
    parser.add_argument('--report-dir', default=None,
                        help='Directory to write reports (default: output-dir/reports)')
    parser.add_argument('--history-dir', default=None,
                        help='Directory for history tracking (default: report-dir/history)')
    parser.add_argument('--no-json', action='store_true',
                        help='Skip JSON report generation')
    parser.add_argument('--no-markdown', action='store_true',
                        help='Skip Markdown report generation')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Print detailed progress information')

    args = parser.parse_args()

    # Determine report directory
    report_dir = args.report_dir or os.path.join(args.output_dir, 'reports')
    history_dir = args.history_dir or os.path.join(report_dir, 'history')

    # Initialize system
    system = QualityAuditSystem(thresholds=args.thresholds)

    if args.verbose:
        print(f"Quality Audit System")
        print(f"  Source dir:  {args.source_dir}")
        print(f"  Output dir:  {args.output_dir}")
        print(f"  Report dir:  {report_dir}")
        print(f"  History dir: {history_dir}")
        print(f"  Thresholds:  {args.thresholds}")
        print(f"  Numpy:       {'available' if _NUMPY_AVAILABLE else 'not available (using pure Python)'}")
        print()

    # Step 1: Scan source files
    if args.verbose:
        print("Scanning source .bbmodel files...")
    profiles = system.scan_source_files(args.source_dir)
    total_anims = sum(len(pl) for pl in profiles.values())
    if args.verbose:
        print(f"  Found {len(profiles)} models with {total_anims} animations")
        for model_name, model_profiles in profiles.items():
            for p in model_profiles:
                print(f"    {model_name}/{p.animation_name}: "
                      f"{p.num_bones} bones, {p.duration:.4f}s, category={p.category}")

    if not profiles:
        print("ERROR: No source .bbmodel files found. Check --source-dir path.")
        sys.exit(1)

    # Step 2: Audit converted output
    if args.verbose:
        print("\nAuditing converted output...")
    report = system.audit_converted_output(args.output_dir, profiles)

    if args.verbose:
        print(f"  Audited {report.total_animations} animations")
        print(f"  C0 Perfect Rate: {report.c0_perfect_rate:.1%}")
        print(f"  C1 Perfect Rate: {report.c1_perfect_rate:.1%}")
        print(f"  Avg Naturalness: {report.naturalness_avg:.4f}")
        print(f"  Critical Issues: {len(report.critical_issues)}")
        print(f"  Important Issues: {len(report.important_issues)}")

    # Step 3: Compare with history
    improvement = system.compare_with_history(report, history_dir)
    if improvement:
        report.improvement_over_previous = improvement
        if args.verbose:
            print("\nImprovement over previous:")
            for metric, delta in improvement.items():
                direction = "improved" if delta > 0 else "regressed"
                print(f"  {metric}: {delta:+.4f} ({direction})")

    # Step 4: Save history
    system.save_history(report, history_dir)
    if args.verbose:
        print(f"\nHistory saved to {history_dir}")

    # Step 5: Generate reports
    os.makedirs(report_dir, exist_ok=True)

    if not args.no_json:
        json_path = os.path.join(report_dir, 'quality_audit.json')
        system.generate_report_json(report, json_path)
        if args.verbose:
            print(f"JSON report: {json_path}")

    if not args.no_markdown:
        md_path = os.path.join(report_dir, 'quality_audit.md')
        system.generate_report_markdown(report, md_path)
        if args.verbose:
            print(f"Markdown report: {md_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("QUALITY AUDIT SUMMARY")
    print("=" * 60)
    print(f"  Models:           {report.total_models}")
    print(f"  Animations:       {report.total_animations}")
    print(f"  C0 Perfect Rate:  {report.c0_perfect_rate:.1%}")
    print(f"  C1 Perfect Rate:  {report.c1_perfect_rate:.1%}")
    print(f"  Avg Naturalness:  {report.naturalness_avg:.4f}")
    print(f"  Avg Amp Retention:{report.amplitude_retention_avg:.4f}")
    print(f"  Grade Distribution: {dict(report.grade_distribution)}")
    print(f"  Critical Issues:  {len(report.critical_issues)}")
    print(f"  Important Issues: {len(report.important_issues)}")
    print("=" * 60)

    # Exit with error code if there are critical issues
    if report.critical_issues:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
