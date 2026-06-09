#!/usr/bin/env python3
"""
BBModelAnimationConverter - Universal Animation Converter (v8)
==============================================================
Converts Blockbench .bbmodel animation keyframes to GeckoLib .animation.json
format with automatic loop continuity enforcement, C1 velocity matching,
duration optimization, and comprehensive quality feedback.

Key Improvements over v7 (7 major improvements):
  1. TRULY-EMPTY ANIMATION PURGE: After C1 enforcement, animations with ALL
     zero bone channel values are purged entirely — not included in output.
     Checked AFTER resampling/C1 to catch tiny correction artifacts.
  2. UNKNOWN ANIMATION RE-CLASSIFICATION: Animations named "unknown" are
     analyzed by content (oscillating legs → walk, static → idle) and
     reclassified to meaningful names.
  3. WALK HALF-CYCLE DETECTION & MIRRORING: Sparse walk animations (3 or
     fewer keyframes per channel) are detected as half-cycles and mirrored
     to produce full walk cycles with C0 continuity at the mirror point.
  4. SMART IDLE DEDUPLICATION ENHANCEMENT: Empty idle + real walk → remove
     empty idle. Cross-model awareness for multi-part entities. Both empty
     idle+evolved → remove both.
  5. ENHANCED C1 VELOCITY CONTINUITY: Periodicity-aware blending for
     transition zones, cubic Hermite with velocity correction, phase-unwrap
     for rotation channels that wrap around.
  6. AUTO-LOOP DURATION WITH VELOCITY ZERO-CROSSING PRIORITY: Walk
     animations prioritize durations where leg rotation velocity crosses
     zero. Tick-snapping for 0.6667s walks. Velocity zero-crossing score
     weighted more heavily than C0 for walks.
  7. ANIMATION FILE SMART OUTPUT: Files where ALL animations are purged
     are not written. Per-file stats tracking: files_skipped_all_empty,
     animations_purged_empty, idle_dedup_removed.

Inherited from v7:
  - CUBIC HERMITE TRANSITION ZONE (C0+C1 at BOTH boundaries)
  - ENHANCED WALK CYCLE DETECTION & MIRRORING (v7 periodic enhancer)
  - IDLE ANIMATION SMART DEDUPLICATION (idle aliases, merge)
  - SMART EMPTY ANIMATION ELIMINATION (static marking, skip_meaningless)
  - AUTO-LOOP WITH VELOCITY MATCHING (±tick, weighted scoring)
  - TEXTURE MAPPING UV FIX
  - QUALITY SCORING ADJUSTMENTS

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
    """Master configuration for BBModelAnimationConverter v8."""
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
    global_cubic_distortion_limit: float = 0.30  # max correction/amplitude ratio before fallback
    static_channel_motion_threshold_rot: float = 0.01  # degrees — below this, channel is "static"
    static_channel_motion_threshold_pos: float = 0.001  # pixels — below this, channel is "static"

    # --- Transition Zone Blend (v6 → v7: cubic Hermite) ---
    transition_zone_ratio: float = 0.20       # last N% of animation is the transition zone
    transition_zone_min_points: int = 12      # minimum resampled points in transition zone
    transition_zone_max_ratio: float = 0.35   # maximum transition zone size
    transition_zone_bounce_damp: float = 0.0  # v7: DISABLED — no more velocity damping

    # --- Periodic Animation Enhancement (v6 → v7: improved) ---
    periodic_enhance_enabled: bool = True     # enable periodic animation detection & enhancement
    periodic_min_period: float = 0.3          # minimum period for periodic detection (seconds)
    periodic_max_period: float = 3.0          # maximum period for periodic detection
    periodic_cycle_complete_threshold: float = 0.85  # fraction of cycle needed to be "complete"
    periodic_autocorrelation_threshold: float = 0.4  # autocorrelation strength for periodic detection
    periodic_name_patterns: tuple = ('walk', 'run', 'fly', 'swim', 'crawl', 'gallop', 'trot', 'flap', 'bounce', 'hop', 'strafe', 'idle', 'move')

    # --- Smart Dedup (v6 → v7: improved idle handling) ---
    bone_coverage_merge_threshold: float = 0.70  # merge only if >70% bone coverage preserved
    tempo_aware_dedup: bool = True               # keep animations with different speeds separate
    skip_empty_animation_files: bool = True      # don't write empty .animation.json files

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

    # --- Animation Deduplication (v5: enhanced → v7: idle aware) ---
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

    # --- v7 NEW Configuration ---
    skip_meaningless_animation_files: bool = True
    c1_scoring_weight: float = 2.0          # C1 weight in duration scoring (was implicit 1.0)
    c0_scoring_weight: float = 5.0          # C0 weight in duration scoring (was 10.0)
    transition_zone_cubic_hermite: bool = True  # Use cubic Hermite in transition zone (v7)
    walk_bone_patterns: tuple = ('leg', 'foot', 'thigh', 'shin', 'knee', 'arm', 'hand', 'wing')
    velocity_zero_crossing_loop: bool = True    # Check velocity zero-crossing for walk loops
    idle_name_aliases: tuple = ('rest', 'breathing', 'ambient', 'pose', 'stand', 'standing')

    # --- v8 NEW Configuration ---
    # Improvement 1: Truly-Empty Animation Purge
    purge_truly_empty_animations: bool = True   # Purge animations where ALL bone channels are zero
    truly_empty_rot_threshold_post: float = 0.01   # degrees — max abs value for "truly empty" after C1
    truly_empty_pos_threshold_post: float = 0.001  # pixels — max abs value for "truly empty" after C1

    # Improvement 2: Unknown Animation Re-classification
    reclassify_unknown_animations: bool = True  # Re-classify "unknown" animations by content

    # Improvement 3: Walk Half-Cycle Detection & Mirroring
    walk_half_cycle_detection: bool = True     # Detect and mirror half-cycle walks
    walk_sparse_keyframe_threshold: int = 3     # Animations with ≤3 keyframes per channel are "sparse"

    # Improvement 4: Smart Idle Dedup Enhancement
    smart_idle_dedup: bool = True              # Remove empty idle when walk/attack exists
    cross_model_idle_dedup: bool = True        # Remove empty idle in one part if another has real idle

    # Improvement 5: Enhanced C1 Velocity Continuity
    periodicity_aware_blending: bool = True    # Use periodicity info in transition zone blending
    rotation_phase_unwrap: bool = True         # Unwrap rotation channels that wrap around

    # Improvement 6: Auto-Loop Duration Velocity Zero-Crossing Priority
    walk_velocity_zero_crossing_weight: float = 3.0  # Weight for zero-crossing score in walk scoring
    walk_tick_snap_durations: tuple = (0.65, 0.6667, 0.70)  # Common walk durations to check

    # Improvement 7: Animation File Smart Output
    skip_all_empty_files: bool = True          # Don't write files where ALL animations are purged


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
    """Quality metrics for a single animation (v8 enhanced)."""
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

    # v6/v7/v8 NEW metrics
    periodicity_score: float = 0.0          # 0.0-1.0, how well the animation is periodic
    transition_smoothness: float = 1.0       # 0.0-1.0, how smooth the loop transition is
    zone_blend_used: bool = False            # whether transition zone blend was applied
    zone_blend_ratio: float = 0.0            # actual transition zone ratio used
    periodic_enhanced: bool = False          # whether periodic enhancement was applied
    original_animation_preserved: float = 1.0  # 0.0-1.0, fraction of animation unchanged
    purged_as_empty: bool = False            # v8: whether this animation was purged as truly empty
    reclassified_from: str = ""              # v8: original name if reclassified from "unknown"
    walk_half_cycle_mirrored: bool = False   # v8: whether walk half-cycle was mirrored

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
# Auto Loop Detector (v8: velocity zero-crossing priority for walks + tick snap)
# ============================================================================

class AutoLoopDetector:
    """Detects optimal loop duration for animations.

    v8 Improvements:
    - Walk velocity zero-crossing priority: heavier weight for walks
    - Tick-snap for common walk durations (0.65, 0.6667, 0.70)
    - Velocity zero-crossing score computed per candidate and factored into scoring

    v7 Improvements:
    - Weighted scoring: c0*5 + c1*2 + comb*0.3 + jerk*0.01 (heavier C1)
    - ±1 tick refinement after finding best candidate
    - Velocity zero-crossing heuristic for walk animations

    v5 Improvements:
    - Harmonic search: check T/n for n=2..6 and n*T for n=2,3
    - Phase-matching across ALL channels simultaneously
    - Tighter early exit thresholds
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

        v7: Added anim_name parameter for walk-cycle heuristic.
        """
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

        # Ultra-fast early exit — if C0 < 0.05 deg AND C1 < 1.0 deg/s, skip ALL search
        if c0_err < 0.05 and c1_err < 1.0:
            diagnostics['method'] = 'early_exit_ultra'
            if cfg.snap_to_ticks:
                current_duration = self._snap_to_tick(current_duration)
            return current_duration, diagnostics

        # "Good enough" early exit (tighter thresholds)
        if c0_err < cfg.early_exit_c0_rot and c1_err < cfg.early_exit_c1_rot:
            diagnostics['method'] = 'early_exit_good_enough'
            if cfg.snap_to_ticks:
                current_duration = self._snap_to_tick(current_duration)
            return current_duration, diagnostics

        # Phase coherence check
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

        # Method 2: Harmonic search — T/n for n=2..6
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

            # v7: Weighted score with heavier C1 weight
            jerk = self._compute_loop_jerk(resampled, T, sample_rate)

            # v8: For walk animations, add velocity zero-crossing score
            is_walk = anim_name and any(p in anim_name.lower() for p in ('walk', 'run'))
            vzc_score = 0.0
            if is_walk and cfg.velocity_zero_crossing_loop:
                vzc_score = self._compute_velocity_zero_crossing_score(
                    resampled, T, sample_rate
                )
                # vzc_score is 0.0 (all zero-crossings) to 1.0 (no zero-crossings)
                # Lower is better, so we add a penalty for missing zero-crossings

            if is_walk and cfg.velocity_zero_crossing_loop:
                score = (c0 * cfg.c0_scoring_weight +
                         c1 * cfg.c1_scoring_weight +
                         comb * 0.3 + jerk * 0.01 +
                         vzc_score * cfg.walk_velocity_zero_crossing_weight)
            else:
                score = c0 * cfg.c0_scoring_weight + c1 * cfg.c1_scoring_weight + comb * 0.3 + jerk * 0.01

            if score < best_score:
                best_score = score
                best_duration = T
                best_combined = comb
                diagnostics['best_c0_error'] = c0
                diagnostics['best_c1_error'] = c1
                diagnostics['best_combined_phase_error'] = comb

        # v7: ±1 tick refinement — check if adjusting by ±0.05s gives better C1 match
        tick = TICK_DURATION
        for delta in [-tick, tick]:
            T_refined = best_duration + delta
            if cfg.min_loop_duration <= T_refined <= cfg.max_loop_duration:
                c0_r, c1_r, comb_r = self._evaluate_continuity_combined(
                    resampled, T_refined, sample_rate
                )
                jerk_r = self._compute_loop_jerk(resampled, T_refined, sample_rate)
                score_r = c0_r * cfg.c0_scoring_weight + c1_r * cfg.c1_scoring_weight + comb_r * 0.3 + jerk_r * 0.01
                if score_r < best_score:
                    best_score = score_r
                    best_duration = T_refined
                    diagnostics['best_c0_error'] = c0_r
                    diagnostics['best_c1_error'] = c1_r
                    diagnostics['best_combined_phase_error'] = comb_r
                    diagnostics['tick_refinement'] = delta

        # v7: Velocity zero-crossing heuristic for walk animations
        if cfg.velocity_zero_crossing_loop and anim_name:
            name_lower = anim_name.lower()
            is_walk = any(p in name_lower for p in ('walk', 'run'))
            if is_walk:
                has_zero_crossing = self._check_velocity_zero_crossing(
                    resampled, best_duration, sample_rate, bone_channels
                )
                diagnostics['velocity_zero_crossing_at_best'] = has_zero_crossing
                if not has_zero_crossing:
                    # Try nearby candidates that DO have zero-crossing
                    for delta_ticks in range(-3, 4):
                        if delta_ticks == 0:
                            continue
                        T_alt = best_duration + delta_ticks * tick
                        if cfg.min_loop_duration <= T_alt <= cfg.max_loop_duration:
                            if self._check_velocity_zero_crossing(
                                resampled, T_alt, sample_rate, bone_channels
                            ):
                                c0_alt, c1_alt, comb_alt = self._evaluate_continuity_combined(
                                    resampled, T_alt, sample_rate
                                )
                                # Accept if C0 is not much worse
                                if c0_alt < diagnostics['best_c0_error'] * 2.0:
                                    best_duration = T_alt
                                    diagnostics['best_c0_error'] = c0_alt
                                    diagnostics['best_c1_error'] = c1_alt
                                    diagnostics['best_combined_phase_error'] = comb_alt
                                    diagnostics['velocity_zero_crossing_adjustment'] = delta_ticks * tick
                                    break

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

    def _check_velocity_zero_crossing(
        self,
        resampled: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        sample_rate: float,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]]
    ) -> bool:
        """v7: Check if leg rotation channels have zero velocity at loop boundary.

        For walk animations, the optimal loop duration is when ALL leg rotation
        channels have zero velocity at the boundary (smoothest loop).
        """
        dt = 1.0 / sample_rate
        cfg = self.config
        walk_patterns = cfg.walk_bone_patterns
        leg_channels_checked = 0
        leg_channels_zero = 0

        for bone_name, channels in resampled.items():
            bone_lower = bone_name.lower()
            is_walk_bone = any(p in bone_lower for p in walk_patterns)
            if not is_walk_bone:
                continue

            for channel, data in channels.items():
                if not channel.startswith('r'):
                    continue
                if len(data) < 6:
                    continue

                leg_channels_checked += 1

                # Velocity at start
                v0 = (self._interpolate(data, dt) - self._interpolate(data, 0.0)) / dt
                # Velocity at end
                vT = (self._interpolate(data, duration) - self._interpolate(data, duration - dt)) / dt

                # Check if both are near-zero (crossing point)
                if abs(v0) < 5.0 and abs(vT) < 5.0:  # degrees/s tolerance
                    leg_channels_zero += 1

        if leg_channels_checked == 0:
            return True  # No leg channels found, don't penalize

        return leg_channels_zero >= leg_channels_checked * 0.5

    def _compute_velocity_zero_crossing_score(
        self,
        resampled: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        sample_rate: float
    ) -> float:
        """v8: Compute a score (0.0-1.0) for how well the duration aligns with
        velocity zero-crossings in leg rotation channels.

        Returns 0.0 if all leg channels have zero velocity at boundary (best).
        Returns 1.0 if none have zero velocity (worst).
        """
        dt = 1.0 / sample_rate
        cfg = self.config
        walk_patterns = cfg.walk_bone_patterns
        leg_channels_total = 0
        leg_channels_zero = 0

        for bone_name, channels in resampled.items():
            bone_lower = bone_name.lower()
            is_walk_bone = any(p in bone_lower for p in walk_patterns)
            if not is_walk_bone:
                continue

            for channel, data in channels.items():
                if not channel.startswith('r'):
                    continue
                if len(data) < 6:
                    continue

                leg_channels_total += 1

                # Velocity at start and end
                v0 = (self._interpolate(data, dt) - self._interpolate(data, 0.0)) / dt
                vT = (self._interpolate(data, duration) - self._interpolate(data, duration - dt)) / dt

                # Score per channel: 1.0 if neither velocity is near-zero
                if abs(v0) < 5.0 and abs(vT) < 5.0:
                    leg_channels_zero += 1

        if leg_channels_total == 0:
            return 0.0

        # Return fraction of channels WITHOUT zero-crossing (higher = worse)
        return 1.0 - (leg_channels_zero / leg_channels_total)

    def _snap_to_tick(self, duration: float) -> float:
        """Snap a duration to the nearest tick boundary (0.05s)."""
        cfg = self.config
        return round(round(duration / cfg.tick_duration) * cfg.tick_duration, 4)

    def _compute_duration_from_keyframes(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]]
    ) -> float:
        """Compute animation duration from keyframe data when length=0."""
        max_time = 0.0
        has_any_motion = False
        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if keyframes:
                    max_time = max(max_time, keyframes[-1][0])
                    if keyframes[-1][0] > 0:
                        has_any_motion = True

        if max_time <= 0:
            return 1.0

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
        """Evaluate C0 and C1 continuity with combined phase error.

        Returns:
            (c0_error_avg, c1_error_avg, combined_phase_error)
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
        """Check if ALL channels have values at T close to values at 0."""
        cfg = self.config
        dt = 1.0 / sample_rate

        for bone_name, channels in resampled.items():
            for channel, data in channels.items():
                if len(data) < 4:
                    continue

                val_0 = self._interpolate(data, 0.0)
                val_T = self._interpolate(data, duration)

                c0_err = abs(val_T - val_0)

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
        """Compute total jerk (derivative of acceleration) at the loop point."""
        dt = 1.0 / sample_rate
        total_jerk = 0.0

        for bone_name, channels in resampled.items():
            for channel, data in channels.items():
                if len(data) < 6:
                    continue

                v0_start = (self._interpolate(data, dt) - self._interpolate(data, 0.0)) / dt
                v0_end = (self._interpolate(data, 0.0) - self._interpolate(data, duration - dt)) / dt

                vT_start = (self._interpolate(data, duration) - self._interpolate(data, duration - dt)) / dt
                vT_end = vT_start

                a0 = (v0_start - v0_end) / dt
                aT = (vT_start - v0_start) / dt

                jerk = abs(aT - a0)
                total_jerk += jerk

        return total_jerk


# ============================================================================
# Periodic Animation Enhancer (v7: enhanced walk cycle detection + mirroring)
# ============================================================================

class PeriodicAnimationEnhancer:
    """Detects and enhances periodic animations (walk, fly, swim, etc.)

    v7 Improvements:
    - More bone name patterns for leg detection via walk_bone_patterns config
    - Better half-cycle detection: walk/run + duration in 0.35-0.75*period
    - Improved mirroring: mean-shifted rotation, time-reversed position, endpoint matching

    v6: For animations that represent periodic motions:
    - Detect the period using autocorrelation and name patterns
    - If the animation is shorter than one period, consider extending it
    - If the animation is a partial cycle, complete it by mirroring
    - Ensure the animation loops smoothly by checking cycle completeness
    - Auto-correct duration to match detected period
    """

    # Common MC walk cycle durations in seconds (at 20 TPS)
    COMMON_WALK_PERIODS = [0.4, 0.5, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 2.0]

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()

    def detect_periodicity(
        self,
        anim_name: str,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        interpolation: str = "catmullrom"
    ) -> Dict[str, Any]:
        """Detect if an animation is periodic and return metrics."""
        cfg = self.config
        result = {
            'is_periodic': False,
            'period': None,
            'periodicity_score': 0.0,
            'cycle_completeness': 0.0,
            'name_match': False,
            'detected_by': 'none',
            'should_enhance': False,
        }

        # Step 1: Check name pattern
        name_lower = anim_name.lower()
        name_match = any(p in name_lower for p in cfg.periodic_name_patterns)
        result['name_match'] = name_match

        if not bone_channels or duration <= 0:
            return result

        # Step 2: Detect period via autocorrelation
        detected_period = None
        autocorr_strength = 0.0

        # v7.1: For name-matched walk animations, try keyframe timing pattern detection FIRST
        # Many walk animations have very few keyframes (3 per channel: start, mid, end)
        # but the timing pattern reveals the period clearly.
        if name_match and duration > 0:
            timing_period = self._detect_period_from_keyframe_timing(bone_channels, duration)
            if timing_period is not None:
                detected_period = timing_period
                autocorr_strength = 0.6  # moderate confidence from timing
                result['detected_by'] = 'keyframe_timing'

        # Collect all channels for period detection (lowered threshold to 2 keyframes)
        all_values = []
        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if len(keyframes) < 2:
                    continue
                n_samp = max(int(duration * 60), 30)
                dt = duration / n_samp
                times = [i * dt for i in range(n_samp + 1)]
                resampled = CatmullRomEvaluator.resample_channel(
                    keyframes, times, interpolation
                )
                values = [v for t, v in resampled]
                mean_v = sum(values) / len(values)
                centered = [v - mean_v for v in values]
                amplitude = max(abs(v) for v in centered)
                if amplitude > 0.01:
                    all_values.append(centered)

        if not all_values and detected_period is None:
            return result

        # Average autocorrelation across channels (only if we have values)
        if all_values and detected_period is None:
            if _NUMPY_AVAILABLE:
                period, strength = self._detect_period_fft(all_values, 60.0, duration)
            else:
                period, strength = self._detect_period_pure(all_values, 60.0, duration)

            if period is not None and strength > cfg.periodic_autocorrelation_threshold:
                detected_period = period
                autocorr_strength = strength

        # Step 3: Also check common MC walk periods
        if detected_period is None and name_match and all_values:
            best_common = None
            best_strength = 0.0
            for T in self.COMMON_WALK_PERIODS:
                if T > duration:
                    continue
                fit = self._check_period_fit(all_values, T, 60.0, duration)
                if fit > best_strength:
                    best_strength = fit
                    best_common = T
            if best_common and best_strength > cfg.periodic_autocorrelation_threshold * 0.7:
                detected_period = best_common
                autocorr_strength = best_strength
                result['detected_by'] = result.get('detected_by') or 'common_period'

        # Step 3.5: v7.1: For name-matched animations with no other detection,
        # assume the animation IS one complete period (duration = period)
        if detected_period is None and name_match and duration > 0:
            detected_period = duration
            autocorr_strength = 0.4  # low confidence but name-matched
            result['detected_by'] = 'name_duration_assume'

        # Step 4: Compute periodicity score
        if detected_period is not None:
            base_score = autocorr_strength
            if name_match:
                base_score = min(1.0, base_score * 1.3)

            result['period'] = detected_period
            result['periodicity_score'] = min(1.0, base_score)
            result['detected_by'] = result['detected_by'] or 'autocorrelation'

            if duration >= detected_period:
                ratio = duration / detected_period
                nearest_int = round(ratio)
                completeness = 1.0 - abs(ratio - nearest_int) / max(nearest_int, 1)
                result['cycle_completeness'] = max(0.0, min(1.0, completeness))
            else:
                result['cycle_completeness'] = duration / detected_period

            result['is_periodic'] = result['periodicity_score'] > 0.4

            if result['is_periodic']:
                if result['cycle_completeness'] < cfg.periodic_cycle_complete_threshold:
                    result['should_enhance'] = True
                elif name_match and duration < detected_period * 0.9:
                    result['should_enhance'] = True

        return result

    def _detect_period_from_keyframe_timing(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float
    ) -> Optional[float]:
        """v7.1: Detect period from keyframe timing patterns.

        For walk animations with sparse keyframes (3 per channel: start, mid, end),
        the mid-keyframe time reveals the half-period. Two common patterns:
        - Symmetric: mid = duration/2 → period = duration (full cycle in one loop)
        - Half-cycle: mid ≈ duration → period ≈ 2*duration (half cycle, needs mirroring)

        For longer animations with more keyframes, look for repeating timing patterns.

        Returns:
            Detected period in seconds, or None if no clear pattern found.
        """
        # Collect timing of interior keyframes from rotation channels
        mid_times = []
        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if not keyframes or channel not in ('rx', 'ry', 'rz', 'x', 'y', 'z'):
                    continue

                # Check amplitude — skip static channels
                values = [v for t, v in keyframes]
                if len(values) < 2:
                    continue
                max_val = max(abs(v) for v in values)
                if max_val < 0.5:  # less than 0.5 degrees — static
                    continue

                if len(keyframes) == 3:
                    # Classic 3-keyframe pattern: start, mid, end
                    # The mid time is the half-period point
                    mid_time = keyframes[1][0]
                    mid_times.append(mid_time)
                elif len(keyframes) > 3:
                    # Multiple keyframes — look for periodic timing
                    # The period is the time between the first and last interior keyframe
                    # that has a value matching the start value
                    start_val = keyframes[0][1]
                    for i in range(1, len(keyframes) - 1):
                        if abs(keyframes[i][1] - start_val) < 0.5:
                            mid_times.append(keyframes[i][0])
                            break

        if not mid_times:
            return None

        # Find the most common mid-time (clustered)
        mid_times.sort()

        # Use the median mid-time as the half-period indicator
        median_mid = mid_times[len(mid_times) // 2]

        # If the mid-time is close to duration/2, the animation is a full cycle
        # with period = duration
        if abs(median_mid - duration / 2) < duration * 0.15:
            return duration

        # If the mid-time is close to duration, it's a half-cycle
        # with period ≈ 2 * mid_time or period ≈ duration
        if abs(median_mid - duration) < duration * 0.15:
            return duration

        # Otherwise, the period is approximately 2 * median_mid
        # (assuming the mid-time represents the half-period)
        period = 2 * median_mid

        # Validate: period should be reasonable (0.3s to 3.0s)
        if 0.3 <= period <= 3.0:
            return period

        return None

    def enhance_periodic(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        periodicity: Dict[str, Any],
        anim_name: str = "",
        interpolation: str = "catmullrom"
    ) -> Tuple[Dict[str, Dict[str, List[Tuple[float, float]]]], float, Dict[str, Any]]:
        """Enhance a periodic animation for better looping.

        v7: Added anim_name parameter for walk-specific half-cycle detection.
        """
        period = periodicity.get('period')
        if period is None or period <= 0:
            return bone_channels, duration, {'enhanced': False}

        info = {'enhanced': False, 'method': 'none'}

        # Strategy: Adjust duration to nearest period multiple
        ratio = duration / period
        nearest_n = max(1, round(ratio))
        target_duration = period * nearest_n

        # v7: Better half-cycle detection for walk/run animations
        name_lower = anim_name.lower()
        is_walk_or_run = 'walk' in name_lower or 'run' in name_lower
        is_half_cycle = (0.35 < ratio < 0.75) if is_walk_or_run else (0.4 < ratio < 0.75)

        # If current duration is close to a period multiple, just adjust
        if abs(duration - target_duration) < period * 0.15:
            if abs(target_duration - duration) > 0.01:
                if target_duration < duration:
                    bone_channels = self._trim_channels(bone_channels, target_duration)
                else:
                    bone_channels = self._extend_channels(
                        bone_channels, duration, target_duration, period, interpolation
                    )
                duration = target_duration
                info = {'enhanced': True, 'method': 'duration_snap_to_period'}

        # Strategy: If duration is roughly half-period, mirror to complete
        elif is_half_cycle:
            half_period = duration
            bone_channels = self._mirror_cycle(bone_channels, half_period, interpolation)
            duration = half_period * 2
            info = {'enhanced': True, 'method': 'mirror_half_cycle'}

        # Strategy: If significantly shorter than period, extend
        elif ratio < 0.4 and periodicity.get('name_match', False):
            bone_channels = self._extend_channels(
                bone_channels, duration, period, period, interpolation
            )
            duration = period
            info = {'enhanced': True, 'method': 'extend_to_period'}

        return bone_channels, duration, info

    def _trim_channels(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        target_duration: float
    ) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
        """Trim all channels to target duration."""
        result = {}
        for bone_name, channels in bone_channels.items():
            result[bone_name] = {}
            for channel, keyframes in channels.items():
                trimmed = [(t, v) for t, v in keyframes if t <= target_duration + 0.0001]
                if trimmed and abs(trimmed[-1][0] - target_duration) > 0.001:
                    for i in range(len(keyframes) - 1):
                        if keyframes[i][0] <= target_duration <= keyframes[i + 1][0]:
                            dt = keyframes[i + 1][0] - keyframes[i][0]
                            if dt > 1e-12:
                                alpha = (target_duration - keyframes[i][0]) / dt
                                val = keyframes[i][1] + alpha * (keyframes[i + 1][1] - keyframes[i][1])
                                trimmed.append((target_duration, val))
                            break
                trimmed.sort(key=lambda x: x[0])
                if trimmed:
                    result[bone_name][channel] = trimmed
        return result

    def _extend_channels(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        current_duration: float,
        target_duration: float,
        period: float,
        interpolation: str
    ) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
        """Extend channels by repeating the animation with overlap blending."""
        result = {}
        for bone_name, channels in bone_channels.items():
            result[bone_name] = {}
            for channel, keyframes in channels.items():
                if not keyframes:
                    continue
                n_samp = max(int(current_duration * 120), 30)
                dt = current_duration / n_samp
                times = [i * dt for i in range(n_samp + 1)]
                resampled = CatmullRomEvaluator.resample_channel(
                    keyframes, times, interpolation
                )

                extended = list(resampled)
                t_offset = current_duration
                while t_offset < target_duration - dt:
                    for t, v in resampled:
                        new_t = t_offset + t
                        if new_t <= target_duration + 0.001:
                            extended.append((new_t, v))
                    t_offset += current_duration

                extended.sort(key=lambda x: x[0])
                deduped = []
                for t, v in extended:
                    if deduped and abs(t - deduped[-1][0]) < 0.001:
                        deduped[-1] = (t, v)
                    else:
                        deduped.append((t, v))

                dp = DouglasPeuckerSimplifier(self.config)
                epsilon = dp.get_epsilon(channel)
                simplified = dp.simplify(deduped, epsilon)

                if simplified:
                    result[bone_name][channel] = simplified
        return result

    def _mirror_cycle(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        half_duration: float,
        interpolation: str
    ) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
        """Mirror the first half of a cycle to create a complete cycle.

        v7 improvements:
        - For rotation channels: negate values AND shift by the mean
          (to center around the resting pose)
        - For position channels: use time-reversed pattern (mirror the
          temporal shape)
        - Better endpoint matching: ensure the mirrored cycle starts and
          ends at the same value for seamless looping
        """
        full_duration = half_duration * 2
        result = {}

        for bone_name, channels in bone_channels.items():
            result[bone_name] = {}
            for channel, keyframes in channels.items():
                if not keyframes:
                    continue

                is_rotation = channel.startswith('r')

                # Resample first half
                n_samp = max(int(half_duration * 120), 20)
                dt = half_duration / n_samp
                times = [i * dt for i in range(n_samp + 1)]
                resampled = CatmullRomEvaluator.resample_channel(
                    keyframes, times, interpolation
                )

                # Compute the mean value of the first half (for mean-shifting)
                values_first_half = [v for t, v in resampled]
                mean_val = sum(values_first_half) / len(values_first_half) if values_first_half else 0.0

                # Store the first and last values for endpoint matching
                p_start = resampled[0][1] if resampled else 0.0

                # Create mirrored second half
                extended = list(resampled)
                for t, v in resampled:
                    new_t = half_duration + (half_duration - t)
                    if new_t > half_duration + 0.001:
                        if is_rotation:
                            # v7: Negate AND shift by mean to center around resting pose
                            # The mirrored value should be: mean - (v - mean) = 2*mean - v
                            new_v = 2.0 * mean_val - v
                        else:
                            # v7: For position channels, use time-reversed pattern
                            # (mirror the temporal shape, keeping values as-is)
                            new_v = v
                        extended.append((new_t, new_v))

                extended.sort(key=lambda x: x[0])

                # v7: Better endpoint matching — ensure mirrored cycle starts and
                # ends at the same value for seamless looping
                if extended:
                    p0 = extended[0][1]
                    pT = extended[-1][1]
                    if abs(pT - p0) > 0.001:
                        # Blend the last few points to match the start value
                        # This ensures C0 continuity at the loop boundary
                        blend_zone = max(int(len(extended) * 0.05), 2)
                        for i in range(max(0, len(extended) - blend_zone), len(extended)):
                            t, v = extended[i]
                            # Linear blend from original to p0
                            blend_s = (i - (len(extended) - blend_zone)) / max(blend_zone, 1)
                            blend_s = min(1.0, max(0.0, blend_s))
                            blended_v = v * (1.0 - blend_s) + p0 * blend_s
                            extended[i] = (t, blended_v)
                        # Force exact match at boundary
                        extended[-1] = (extended[-1][0], p0)

                # Remove near-duplicates
                deduped = []
                for t, v in extended:
                    if deduped and abs(t - deduped[-1][0]) < 0.001:
                        deduped[-1] = (t, v)
                    else:
                        deduped.append((t, v))

                # Simplify
                dp = DouglasPeuckerSimplifier(self.config)
                epsilon = dp.get_epsilon(channel)
                simplified = dp.simplify(deduped, epsilon)

                if simplified:
                    result[bone_name][channel] = simplified

        return result

    def _detect_period_fft(
        self,
        all_values: List[List[float]],
        sample_rate: float,
        duration: float
    ) -> Tuple[Optional[float], float]:
        """Detect period using FFT-based autocorrelation."""
        if not _NUMPY_AVAILABLE:
            return self._detect_period_pure(all_values, sample_rate, duration)

        import numpy as np

        best_period = None
        best_strength = 0.0

        for values in all_values:
            arr = np.array(values, dtype=np.float64)
            n = len(arr)

            fft_x = np.fft.rfft(arr, n=2 * n)
            autocorr = np.fft.irfft(fft_x * np.conj(fft_x))[:n]

            if autocorr[0] < 1e-12:
                continue
            autocorr = autocorr / autocorr[0]

            min_lag = max(int(0.1 * sample_rate), 1)
            max_lag = min(n // 2, int(3.0 * sample_rate))

            for k in range(min_lag, min(max_lag, len(autocorr) - 1)):
                if (autocorr[k] > autocorr[k - 1] and
                    autocorr[k] > autocorr[k + 1] and
                    autocorr[k] > best_strength):
                    period = k / sample_rate
                    if self.config.periodic_min_period <= period <= self.config.periodic_max_period:
                        best_period = period
                        best_strength = float(autocorr[k])

        return best_period, best_strength

    def _detect_period_pure(
        self,
        all_values: List[List[float]],
        sample_rate: float,
        duration: float
    ) -> Tuple[Optional[float], float]:
        """Detect period using pure-python autocorrelation."""
        best_period = None
        best_strength = 0.0

        for values in all_values:
            n = len(values)
            energy = sum(v * v for v in values)
            if energy < 1e-12:
                continue

            min_lag = max(int(0.1 * sample_rate), 1)
            max_lag = min(n // 2, int(3.0 * sample_rate))

            for k in range(min_lag, max_lag):
                corr = sum(values[i] * values[i + k] for i in range(n - k))
                corr /= energy

                if corr > best_strength:
                    period = k / sample_rate
                    if self.config.periodic_min_period <= period <= self.config.periodic_max_period:
                        best_period = period
                        best_strength = corr

        return best_period, best_strength

    def _check_period_fit(
        self,
        all_values: List[List[float]],
        period: float,
        sample_rate: float,
        duration: float
    ) -> float:
        """Check how well a specific period fits the data."""
        period_samples = int(period * sample_rate)
        if period_samples <= 0:
            return 0.0

        total_fit = 0.0
        count = 0

        for values in all_values:
            n = len(values)
            if n < period_samples * 2:
                continue

            first = values[:period_samples]
            second = values[period_samples:period_samples * 2]

            if len(first) != len(second):
                min_len = min(len(first), len(second))
                first = first[:min_len]
                second = second[:min_len]

            mean1 = sum(first) / len(first)
            mean2 = sum(second) / len(second)
            f1 = [v - mean1 for v in first]
            f2 = [v - mean2 for v in second]

            energy1 = sum(v * v for v in f1)
            energy2 = sum(v * v for v in f2)

            if energy1 < 1e-12 or energy2 < 1e-12:
                continue

            corr = sum(a * b for a, b in zip(f1, f2))
            corr /= math.sqrt(energy1 * energy2)
            total_fit += max(0.0, corr)
            count += 1

        return total_fit / max(count, 1)


# ============================================================================
# C1 Continuity Enforcer (v7: cubic Hermite transition zone + no damping)
# ============================================================================

class C1ContinuityEnforcer:
    """Enforces C1 (velocity) continuity at loop boundaries.

    v7 CRITICAL CHANGE: Cubic Hermite Transition Zone (replaces quintic)

    The transition zone now uses CUBIC Hermite interpolation instead of
    quintic Hermite. This provides GUARANTEED C0+C1 continuity at BOTH
    the zone start boundary AND the loop boundary, because:

    - At zone_start: p(0) = p_zone_start, v(0) = v_zone_start
      (matches original animation exactly — NO damping)
    - At duration:   p(1) = p_end_target, v(1) = v_end_target
      (matches loop start for C0+C1)

    The cubic Hermite formula with 4 constraints:
      h00 = 2s^3 - 3s^2 + 1
      h10 = s^3 - 2s^2 + s
      h01 = -2s^3 + 3s^2
      h11 = s^3 - s^2
      value = h00*p_start + h10*w*v_start + h01*p_end + h11*w*v_end

    where s = (t - zone_start_time) / zone_duration, w = zone_duration

    v7: velocity damping for bounce cases is DISABLED (damp = 0.0).
    The original velocity at the zone start is preserved exactly,
    ensuring C1 continuity at the zone boundary.

    HYBRID APPROACH (inherited from v5/v6):
    - Primary: Global Cubic Correction for ALL channels (guaranteed C0+C1)
    - Fallback: For channels where global correction would cause >30%
      distortion, use transition zone blend with cubic Hermite
    - Special: For near-static channels, just snap last keyframe to first
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()

    @staticmethod
    def _quintic_hermite(s: float, p0: float, v0: float, a0: float,
                          p1: float, v1: float, a1: float,
                          dt: float) -> float:
        """Evaluate quintic Hermite interpolation (legacy, kept for compat)."""
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

    @staticmethod
    def _cubic_hermite(s: float, p_start: float, v_start: float,
                        p_end: float, v_end: float, w: float) -> float:
        """v7: Evaluate cubic Hermite interpolation.

        Cubic Hermite with 4 constraints:
          p(0) = p_start, v(0) = v_start
          p(1) = p_end,   v(1) = v_end

        where w = zone_duration (for velocity scaling).

        Formula:
          h00 = 2s^3 - 3s^2 + 1
          h10 = s^3 - 2s^2 + s
          h01 = -2s^3 + 3s^2
          h11 = s^3 - s^2
          value = h00*p_start + h10*w*v_start + h01*p_end + h11*w*v_end
        """
        s2 = s * s
        s3 = s2 * s

        h00 = 2.0 * s3 - 3.0 * s2 + 1.0
        h10 = s3 - 2.0 * s2 + s
        h01 = -2.0 * s3 + 3.0 * s2
        h11 = s3 - s2

        return (h00 * p_start +
                h10 * w * v_start +
                h01 * p_end +
                h11 * w * v_end)

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
        """
        T2 = T * T
        T3 = T2 * T

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
        """Compute max(|c(t)|) over [0, T] for distortion check."""
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
        """Compute per-channel adaptive blend window."""
        cfg = self.config
        base_w = duration * cfg.blend_window_ratio
        adaptive_scale = 1.0 + min(c1_diff / max(c1_threshold, 1e-6), 3.0)
        w = base_w * adaptive_scale

        min_w = cfg.adaptive_blend_min_points * resample_dt
        w = max(w, min_w)

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

        blend_start_idx = 0
        for i, (t, v) in enumerate(result):
            if t >= t_start_blend:
                blend_start_idx = i
                break

        if blend_start_idx < 1 or blend_start_idx >= len(result) - 1:
            return result

        p_end_target = p0
        v_end_target = v0

        if is_bounce and bounce_severity > 0.1:
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
            # v7: Use cubic Hermite for local blend too
            for i in range(blend_start_idx, len(result)):
                t, v = result[i]
                s = (t - t_start_blend) / w_actual
                s = max(0.0, min(1.0, s))

                new_val = self._cubic_hermite(
                    s, p_start_blend, v_start_blend,
                    p_end_target, v_end_target, w_actual
                )
                result[i] = (t, new_val)

        return result

    def _apply_transition_zone_blend(
        self,
        resampled: List[Tuple[float, float]],
        duration: float,
        p0: float,
        v0: float,
        vT: float,
        is_rotation: bool,
        resample_dt: float,
        is_bounce: bool = False
    ) -> List[Tuple[float, float]]:
        """v7: Apply transition zone blend for loop continuity using CUBIC HERMITE.

        NON-DESTRUCTIVE: Only modifies the last N% of the animation
        (the "transition zone"), preserving the original shape for
        75-85% of the animation.

        v7 CRITICAL FIX: Uses CUBIC Hermite instead of quintic Hermite
        within the transition zone, providing GUARANTEED C0+C1 continuity
        at BOTH boundaries:

        - At zone_start: Match original position AND original velocity
          (NO damping — the v6 damping was wrong)
        - At duration:   Match target position p0 AND target velocity v0

        The 4 constraints are exactly satisfied by cubic Hermite:
          p(0) = p_zone_start, v(0) = v_zone_start  (original at zone boundary)
          p(1) = p_end_target,  v(1) = v_end_target  (loop start for C0+C1)

        Args:
            resampled: Resampled channel data [(t, v), ...]
            duration: Animation duration T
            p0: Value at start (target for C0 match at end)
            v0: Velocity at start (target for C1 match at end)
            vT: Velocity at end (before correction)
            is_rotation: Whether this is a rotation channel
            resample_dt: Time step between resampled points
            is_bounce: Whether this is a bounce case (v0*vT < 0)

        Returns:
            Modified resampled data with transition zone blending applied.
        """
        result = list(resampled)
        n = len(result)
        if n < 5 or duration < 1e-12:
            return result

        cfg = self.config
        T = duration

        # Compute adaptive transition zone size
        zone_ratio = cfg.transition_zone_ratio

        # For bounce cases, use a slightly larger zone for smoother transition
        if is_bounce:
            zone_ratio = min(cfg.transition_zone_max_ratio, zone_ratio * 1.4)

        # Ensure minimum points in the zone
        min_zone_duration = cfg.transition_zone_min_points * resample_dt
        zone_duration = max(T * zone_ratio, min_zone_duration)
        zone_duration = min(zone_duration, T * cfg.transition_zone_max_ratio)

        zone_start_time = T - zone_duration

        if zone_start_time < resample_dt:
            zone_start_time = resample_dt
            zone_duration = T - zone_start_time

        # Find the zone start index
        zone_start_idx = 0
        for i, (t, v) in enumerate(result):
            if t >= zone_start_time:
                zone_start_idx = i
                break

        if zone_start_idx < 1 or zone_start_idx >= n - 1:
            if result:
                result[-1] = (result[-1][0], p0)
            return result

        # Get original values at zone start
        p_zone_start = result[zone_start_idx][1]

        # Compute velocity at zone start from surrounding points
        # v7: NO damping — use the actual original velocity
        if zone_start_idx > 0 and zone_start_idx < n - 1:
            dt_zone = result[zone_start_idx + 1][0] - result[zone_start_idx - 1][0]
            if dt_zone > 1e-12:
                v_zone_start = (result[zone_start_idx + 1][1] - result[zone_start_idx - 1][1]) / dt_zone
            else:
                v_zone_start = 0.0
        else:
            v_zone_start = 0.0

        # v7: NO velocity damping for bounce cases — the damping was wrong
        # The cubic Hermite handles bounce cases correctly by matching
        # the actual velocity at the zone start boundary.
        # (v6 code: v_zone_start = v_zone_start * (1.0 - damp * 0.3) — REMOVED)

        # Target at end: (p0, v0) for C0+C1 match
        p_end_target = p0
        v_end_target = v0

        # v7: Apply CUBIC HERMITE blend within the transition zone
        # This replaces the v6 quintic Hermite approach
        w_zone = zone_duration

        for i in range(zone_start_idx, n):
            t, v = result[i]

            if w_zone > 1e-12:
                s = (t - zone_start_time) / w_zone
                s = max(0.0, min(1.0, s))
            else:
                s = 1.0

            if cfg.transition_zone_cubic_hermite:
                # v7: Cubic Hermite with 4 constraints
                # p(0) = p_zone_start, v(0) = v_zone_start
                # p(1) = p_end_target,  v(1) = v_end_target
                new_val = self._cubic_hermite(
                    s, p_zone_start, v_zone_start,
                    p_end_target, v_end_target, w_zone
                )
            else:
                # Legacy quintic Hermite (fallback if config disabled)
                new_val = self._quintic_hermite(
                    s, p_zone_start, v_zone_start, 0.0,
                    p_end_target, v_end_target, 0.0, w_zone
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
        cached_resampled: Optional[Dict[str, Dict[str, List[Tuple[float, float]]]]] = None,
        periodicity_info: Optional[Dict[str, Any]] = None
    ) -> Tuple[Dict[str, Dict[str, List[Tuple[float, float]]]],
               Dict[str, Any]]:
        """Apply hybrid C1 continuity enforcement.

        v8: Added periodicity_info parameter for periodicity-aware blending.

        Primary: Global Cubic Correction (distributed across entire animation)
        Fallback: Transition Zone Blend with cubic Hermite (v7)
        Special: Static snap (for near-zero motion channels)

        Args:
            bone_channels: {bone: {channel: [(t, v), ...]}}
            duration: Animation duration
            interpolation: Interpolation type for resampling
            cached_resampled: Pre-computed resampled data
            periodicity_info: v8 Optional periodicity detection results for
                periodicity-aware blending in transition zones

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
            'correction_magnitudes': [],
            'fidelity_scores': [],
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
                delta_p = pT - p0
                delta_v = vT - v0

                T = duration
                if T < 1e-12:
                    continue

                a_coeff, b_coeff = self._compute_global_cubic_coefficients(delta_p, delta_v, T)

                max_correction = self._compute_correction_magnitude(a_coeff, b_coeff, T)
                amplitude = self._compute_channel_amplitude(resampled)

                correction_ratio = max_correction / max(amplitude, 1e-6)

                is_bounce = self._is_bounce_case(v0, vT)

                if correction_ratio <= cfg.global_cubic_distortion_limit:
                    # ====================================================
                    # GLOBAL CUBIC CORRECTION (v5 primary method)
                    # ====================================================
                    blend_diag['global_cubic_count'] += 1

                    corrected = []
                    for t, v in resampled:
                        c_t = self._evaluate_correction(t, a_coeff, b_coeff)
                        corrected.append((t, v + c_t))

                    new_keyframes = self._rebuild_keyframes_from_resampled(
                        keyframes, corrected, duration, p0
                    )

                    channels[channel] = new_keyframes
                    blend_diag['correction_magnitudes'].append(correction_ratio)
                    blend_diag['fidelity_scores'].append(1.0 - correction_ratio)

                elif is_bounce:
                    # ====================================================
                    # TRANSITION ZONE BLEND — v7: cubic Hermite, NO damping
                    # ====================================================
                    blend_diag['local_blend_count'] += 1
                    blend_diag['bridge_used_count'] += 1

                    corrected = self._apply_transition_zone_blend(
                        resampled, duration, p0, v0, vT,
                        is_rotation, resample_dt, is_bounce=True
                    )

                    new_keyframes = self._rebuild_keyframes_from_resampled(
                        keyframes, corrected, duration, p0
                    )
                    channels[channel] = new_keyframes

                    zone_ratio_actual = self.config.transition_zone_ratio * 1.4
                    zone_ratio_actual = min(zone_ratio_actual, self.config.transition_zone_max_ratio)
                    fidelity = 1.0 - correction_ratio * zone_ratio_actual
                    blend_diag['correction_magnitudes'].append(correction_ratio)
                    blend_diag['fidelity_scores'].append(max(0.0, fidelity))

                    blend_diag['bridge_details'].append({
                        'bone': bone_name,
                        'channel': channel,
                        'severity': bounce_severity,
                        'method': 'transition_zone_blend_cubic_hermite',
                    })

                else:
                    # ====================================================
                    # TRANSITION ZONE BLEND — v7: cubic Hermite (non-bounce)
                    # ====================================================
                    blend_diag['local_blend_count'] += 1

                    corrected = self._apply_transition_zone_blend(
                        resampled, duration, p0, v0, vT,
                        is_rotation, resample_dt, is_bounce=False
                    )

                    new_keyframes = self._rebuild_keyframes_from_resampled(
                        keyframes, corrected, duration, p0
                    )
                    channels[channel] = new_keyframes

                    fidelity = 1.0 - correction_ratio * self.config.transition_zone_ratio
                    blend_diag['correction_magnitudes'].append(correction_ratio)
                    blend_diag['fidelity_scores'].append(max(0.0, fidelity))

        return bone_channels, blend_diag

    def _rebuild_keyframes_from_resampled(
        self,
        original_keyframes: List[Tuple[float, float]],
        corrected_resampled: List[Tuple[float, float]],
        duration: float,
        p0: float
    ) -> List[Tuple[float, float]]:
        """Rebuild keyframes from corrected resampled data."""
        if not corrected_resampled:
            return original_keyframes

        new_keyframes = []

        for t_orig, v_orig in original_keyframes:
            corrected_val = self._interpolate_resampled(corrected_resampled, t_orig)
            new_keyframes.append((t_orig, corrected_val))

        if new_keyframes:
            new_keyframes[-1] = (duration, p0)
        else:
            new_keyframes.append((0.0, p0))
            new_keyframes.append((duration, p0))

        new_keyframes.sort(key=lambda x: x[0])

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
# Animation Name Normalizer (v7: idle aliases)
# ============================================================================

class AnimationNameNormalizer:
    """Normalizes animation names to follow GeckoLib convention.

    v7: Added idle name aliases (rest, breathing, ambient, pose).
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
        'rest': 'idle',          # v7 NEW
        'breathing': 'idle',     # v7 NEW
        'ambient': 'idle',       # v7 NEW
        'pose': 'idle',          # v7 NEW
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
        """Normalize a name for semantic deduplication comparison."""
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
# BBModel Animation Extractor (v7: idle smart dedup)
# ============================================================================

class BBModelAnimationExtractor:
    """Extracts animations from .bbmodel files and converts to internal format.

    v7 Improvements:
    - Idle name aliases: rest, breathing, ambient, pose → idle
    - When merging duplicate idle animations, always take the one with MORE keyframes per bone
    - If merged idle result has >50% more keyframes than either source alone, log as "idle_enriched"
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()

    def extract(self, bbmodel_path: str) -> Dict[str, Any]:
        """Extract all animations from a .bbmodel file."""
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

            dominant_interp = "linear"
            if interpolation_counts:
                dominant_interp = max(interpolation_counts, key=interpolation_counts.get)

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

        # Step 1: Semantic deduplication (by normalized name)
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
                    primary_name, primary_data = group[0]
                    primary_bones = set(primary_data['bone_channels'].keys())

                    to_merge = []
                    to_keep_separate = []

                    for alt_name, alt_data in group[1:]:
                        alt_bones = set(alt_data['bone_channels'].keys())

                        if not primary_bones and not alt_bones:
                            to_merge.append((alt_name, alt_data))
                            continue

                        if not primary_bones or not alt_bones:
                            to_keep_separate.append((alt_name, alt_data))
                            continue

                        overlap = primary_bones & alt_bones
                        union = primary_bones | alt_bones
                        overlap_ratio = len(overlap) / len(union) if union else 0.0

                        if overlap_ratio >= 0.5:
                            to_merge.append((alt_name, alt_data))
                        else:
                            to_keep_separate.append((alt_name, alt_data))

                    # v7: For idle animations, always take the one with MORE keyframes per bone
                    is_idle = norm_name == 'idle' or any(
                        alias in norm_name for alias in self.config.idle_name_aliases
                    )

                    if is_idle:
                        # Sort by total keyframes (most keyframes first)
                        group_with_primary = [(primary_name, primary_data)] + to_merge
                        group_with_primary.sort(key=lambda x: sum(
                            len(kfs) for chs in x[1]['bone_channels'].values()
                            for kfs in chs.values()
                        ), reverse=True)
                    else:
                        group_with_primary = [(primary_name, primary_data)] + to_merge
                        group_with_primary.sort(key=lambda x: sum(
                            len(kfs) for chs in x[1]['bone_channels'].values()
                            for kfs in chs.values()
                        ), reverse=True)

                    primary_name, primary_data = group_with_primary[0]
                    primary_kf_count = sum(
                        len(kfs) for chs in primary_data['bone_channels'].values()
                        for kfs in chs.values()
                    )

                    merged_channels = dict(primary_data['bone_channels'])

                    for alt_name, alt_data in group_with_primary[1:]:
                        alt_kf_count = sum(
                            len(kfs) for chs in alt_data['bone_channels'].values()
                            for kfs in chs.values()
                        )
                        alt_channels = alt_data['bone_channels']

                        # v7: For idle, always use the version with more keyframes per bone
                        if is_idle:
                            merged_channels, merge_actions = self._union_bone_channels_idle(
                                merged_channels, alt_channels, primary_name, alt_name
                            )
                        else:
                            merged_channels, merge_actions = self._union_bone_channels(
                                merged_channels, alt_channels, primary_name, alt_name
                            )
                        merge_info.extend(merge_actions)
                        deduplicated.append(alt_name)

                        # v7: Check for idle_enriched
                        merged_kf_count = sum(
                            len(kfs) for chs in merged_channels.values()
                            for kfs in chs.values()
                        )
                        if is_idle and merged_kf_count > max(primary_kf_count, alt_kf_count) * 1.5:
                            merge_info.append({
                                'animation': primary_name,
                                'action': 'idle_enriched',
                                'source': alt_name,
                                'primary_kf': primary_kf_count,
                                'alt_kf': alt_kf_count,
                                'merged_kf': merged_kf_count,
                            })

                    primary_data['bone_channels'] = merged_channels
                    emptiness = self._classify_emptiness(merged_channels)
                    primary_data['is_empty'] = emptiness == 'truly_empty'
                    primary_data['is_near_empty'] = emptiness == 'near_empty'
                    primary_data['emptiness'] = emptiness
                    animations[primary_name] = primary_data

                    for alt_name, alt_data in to_keep_separate:
                        animations[alt_name] = alt_data
        elif self.config.deduplicate_case_insensitive:
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
        if self.config.preserve_empty_as_static:
            to_remove = []
            for anim_name, anim_data in animations.items():
                if anim_data['is_empty']:
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
                            anim_data['length'] = max_time + TICK_DURATION
                        else:
                            anim_data['length'] = 1.0
                    static_preserved.append(anim_name)
                elif anim_data.get('is_near_empty', False):
                    anim_data['static'] = True
                    near_empty_list.append(anim_name)

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
        """Classify animation emptiness level."""
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
                        if abs(v) > cfg.truly_empty_rot_threshold:
                            has_near_motion = True
                        if abs(v) > cfg.near_empty_rot_threshold:
                            has_any_motion = True
                    elif channel.startswith('o'):
                        if abs(v) > cfg.truly_empty_pos_threshold:
                            has_near_motion = True
                        if abs(v) > cfg.near_empty_pos_threshold:
                            has_any_motion = True
                    elif channel.startswith('s'):
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
        """Union bone channels from two animation sources."""
        merged = dict(primary_channels)
        actions = []

        for bone, channels in alt_channels.items():
            if bone not in merged:
                merged[bone] = channels
                actions.append({
                    'animation': primary_name,
                    'bone': bone,
                    'action': 'added_from_duplicate',
                    'source': alt_name,
                })
            else:
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

    def _union_bone_channels_idle(
        self,
        primary_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        alt_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        primary_name: str,
        alt_name: str
    ) -> Tuple[Dict[str, Dict[str, List[Tuple[float, float]]]], List[Dict]]:
        """v7: Union bone channels for idle animations — always prefer MORE keyframes."""
        merged = dict(primary_channels)
        actions = []

        for bone, channels in alt_channels.items():
            if bone not in merged:
                merged[bone] = channels
                actions.append({
                    'animation': primary_name,
                    'bone': bone,
                    'action': 'added_from_duplicate_idle',
                    'source': alt_name,
                })
            else:
                merged_bone = dict(merged[bone])
                for ch_name, ch_data in channels.items():
                    if ch_name not in merged_bone:
                        merged_bone[ch_name] = ch_data
                        actions.append({
                            'animation': primary_name,
                            'bone': bone,
                            'channel': ch_name,
                            'action': 'channel_added_from_idle',
                            'source': alt_name,
                        })
                    else:
                        # v7: For idle, ALWAYS take the one with MORE keyframes
                        existing_kf = len(merged_bone[ch_name])
                        new_kf = len(ch_data)
                        if new_kf >= existing_kf:
                            merged_bone[ch_name] = ch_data
                            actions.append({
                                'animation': primary_name,
                                'bone': bone,
                                'channel': ch_name,
                                'action': 'idle_channel_replaced_more_keyframes',
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
# GeckoLib JSON Builder (v7: static + near-empty support)
# ============================================================================

class GeckoLibJSONBuilder:
    """Builds GeckoLib 1.20.1 .animation.json format from processed channel data.

    v7: Supports "static": true flag, minimal static pose for near-empty.
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

        # v7: For near-empty animations, write minimal static pose with just first keyframe
        if is_near_empty and bones_dict:
            minimal_bones = {}
            for bone_name, channels in bone_channels.items():
                bone_entry = {}
                for channel, keyframes in channels.items():
                    if not keyframes:
                        continue
                    # Only keep the first keyframe value
                    first_val = keyframes[0][1]
                    axis = channel[-1]
                    kf_dict = {"0.0000": round(first_val, cfg.value_precision)}
                    if channel in ('rx', 'ry', 'rz'):
                        if 'rotation' not in bone_entry:
                            bone_entry['rotation'] = {}
                        bone_entry['rotation'][axis] = kf_dict
                    elif channel in ('ox', 'oy', 'oz'):
                        if 'position' not in bone_entry:
                            bone_entry['position'] = {}
                        bone_entry['position'][axis] = kf_dict
                if bone_entry:
                    minimal_bones[bone_name] = bone_entry
            bones_dict = minimal_bones

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
        """Build a GeckoLib bone entry."""
        rot_channels = {}
        pos_channels = {}

        for channel, keyframes in channels.items():
            if not keyframes:
                continue

            epsilon = self.dp_simplifier.get_epsilon(channel)
            simplified = self.dp_simplifier.simplify(keyframes, epsilon)

            max_abs = max(abs(v) for t, v in simplified) if simplified else 0.0
            if max_abs < config.filter_zero_threshold:
                continue

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
        """Enforce C1 velocity match at loop boundary after DP simplification."""
        if len(keyframes) < 3 or duration <= 0:
            return keyframes

        p0 = keyframes[0][1]
        pT = keyframes[-1][1]

        if abs(pT - p0) > 1e-8:
            keyframes = keyframes[:-1] + [(keyframes[-1][0], p0)]
            pT = p0

        dt_start = keyframes[1][0] - keyframes[0][0]
        v_start = (keyframes[1][1] - p0) / dt_start if dt_start > 1e-12 else 0.0

        dt_end = keyframes[-1][0] - keyframes[-2][0]
        v_end = (pT - keyframes[-2][1]) / dt_end if dt_end > 1e-12 else 0.0

        c1_diff = abs(v_start - v_end)
        is_rotation = channel in ('rx', 'ry', 'rz')
        c1_thresh = config.velocity_match_threshold_rot if is_rotation else config.velocity_match_threshold_pos

        if c1_diff < c1_thresh:
            return keyframes

        target_v = v_start
        result = list(keyframes)
        tick = config.tick_duration

        t_hint_end = duration - tick
        v_hint_end = pT - target_v * tick

        insert_end = True
        for i, (t, v) in enumerate(result):
            if abs(t - t_hint_end) < tick * 0.5:
                result[i] = (t, v_hint_end)
                insert_end = False
                break

        if insert_end and t_hint_end > result[-2][0] + tick * 0.5:
            result.append((t_hint_end, v_hint_end))
            result.sort(key=lambda x: x[0])

        if abs(result[-1][1] - p0) > 1e-8:
            result[-1] = (result[-1][0], p0)

        deduped = []
        for t, v in result:
            if deduped and abs(t - deduped[-1][0]) < 0.001:
                deduped[-1] = (t, v)
            else:
                deduped.append((t, v))

        return deduped


# ============================================================================
# Quality Reporter (v7: periodic bonus, harsher bounce, score ENHANCED)
# ============================================================================

class QualityReporter:
    """Generates quality reports for converted animations (v7 enhanced).

    v7 improvements:
    - Periodic animations with periodicity_score > 0.7 AND c1_method == 'none': +5 bonus
    - Bounce-back severity > 0.8: -15 penalty (was -10)
    - Score the ENHANCED version when periodic enhancement was applied
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

                if len(keyframes) >= 2 and duration > 0:
                    dt_start = keyframes[1][0] - keyframes[0][0]
                    if dt_start > 1e-12:
                        v0 = (keyframes[1][1] - keyframes[0][1]) / dt_start
                    else:
                        v0 = 0.0

                    dt_end = keyframes[-1][0] - keyframes[-2][0]
                    if dt_end > 1e-12:
                        vT = (keyframes[-1][1] - keyframes[-2][1]) / dt_end
                    else:
                        vT = 0.0

                    c1_err = abs(vT - v0)

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

        # Correction magnitude and fidelity from blend diagnostics
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

        # Update per-bone breakdown with correction magnitude
        if blend_diag and blend_diag.get('correction_magnitudes'):
            all_mags = blend_diag['correction_magnitudes']
            all_fidelity = blend_diag['fidelity_scores']
            n_channels = len(all_mags)
            if n_channels > 0 and bone_breakdowns:
                avg_mag = sum(all_mags) / n_channels
                avg_fidelity = sum(all_fidelity) / n_channels
                for b in bone_breakdowns:
                    b.correction_magnitude = avg_mag
                    b.fidelity_score = avg_fidelity

        # Naturalness score
        naturalness, sign_changes = self._compute_naturalness(
            bone_channels, duration, cached_resampled
        )
        report.naturalness_score = naturalness
        report.second_derivative_sign_changes = sign_changes

        # Per-bone breakdown — sort by worst and keep top 3
        bone_breakdowns.sort(key=lambda b: b.worst_c0 + b.worst_c1, reverse=True)
        report.bone_breakdown = bone_breakdowns
        report.worst_bones = [b.bone_name for b in bone_breakdowns[:3]]

        # Quality assessment
        report.c0_perfect = report.c0_max_error_rot < self.config.c0_perfect_threshold_rot and \
                            report.c0_max_error_pos < self.config.c0_perfect_threshold_pos
        report.c1_perfect = report.c1_avg_error_rot < self.config.c1_perfect_threshold_rot and \
                            report.c1_avg_error_pos < self.config.c1_perfect_threshold_pos

        # Compute quality score (0-100) — v7 enhanced
        score = 100.0

        # C0 penalties
        if not report.c0_perfect:
            score -= min(30, report.c0_max_error_rot * 5 + report.c0_max_error_pos * 30)

        # C1 penalties using P90
        if not report.c1_perfect:
            c1_rot_penalty = min(25, report.c1_avg_error_rot * 1.5)
            c1_pos_penalty = min(15, report.c1_avg_error_pos * 5)
            score -= c1_rot_penalty + c1_pos_penalty

        # v7: Bounce-back penalty — harsher for severe bounce (> 0.8)
        if report.bounce_back_severity > 0.8:
            score -= min(15, report.bounce_back_severity * 7.5)
        elif report.bounce_back_severity > 0.5:
            score -= min(10, report.bounce_back_severity * 5)

        # Correction magnitude penalty
        if report.correction_magnitude_max > 0.10:
            score -= min(10, report.correction_magnitude_max * 20)

        # Method bonus — global cubic gets a bonus
        if report.c1_method == 'global_cubic':
            score = min(100.0, score + 2.0)

        # Fidelity score influence
        if report.fidelity_score_avg < 0.90:
            score -= min(5, (1.0 - report.fidelity_score_avg) * 20)

        # Naturalness penalty
        if report.naturalness_score < 0.8:
            score -= min(8, (1.0 - report.naturalness_score) * 15)

        # v7: No-enforcement bonus — naturally smooth at loop boundaries
        if report.c1_method == 'none':
            score = min(100.0, score + 3.0)

        # v7: Periodic bonus — well-periodic animations that need NO C1 correction
        # are naturally smooth at loop boundaries (bonus: +5)
        if report.periodicity_score > 0.7 and report.c1_method == 'none':
            score = min(100.0, score + 5.0)

        # Periodicity bonus (general)
        if report.periodicity_score > 0.7:
            score = min(100.0, score + 2.0)

        # Transition smoothness bonus
        if report.transition_smoothness > 0.9:
            score = min(100.0, score + 2.0)

        # Preservation bonus
        if report.original_animation_preserved > 0.95:
            score = min(100.0, score + 1.0)

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

        if report.bounce_back_severity > 0.3:
            report.warnings.append(
                f"Bounce-back severity: {report.bounce_back_severity:.2f} "
                f"(worst bones: {', '.join(report.worst_bones)})"
            )

        if report.correction_magnitude_max > 0.10:
            report.warnings.append(
                f"Correction magnitude: {report.correction_magnitude_max:.3f} "
                f"(avg: {report.correction_magnitude_avg:.3f}), "
                f"fidelity: {report.fidelity_score_avg:.3f}"
            )

        if report.c1_method != 'none':
            report.warnings.append(
                f"C1 method: {report.c1_method} "
                f"(cubic={report.global_cubic_used_count}, "
                f"blend={report.local_blend_used_count}, "
                f"snap={report.static_snap_count})"
            )

        for b in bone_breakdowns[:3]:
            if b.worst_c0 > self.config.quality_warning_threshold or b.worst_c1 > self.config.c1_quality_threshold_rot:
                report.warnings.append(
                    f"  Bone '{b.bone_name}': C0_rot={b.c0_error_rot:.3f}deg, "
                    f"C1_rot={b.c1_error_rot:.2f}deg/s, "
                    f"bounce={b.bounce_severity:.2f}, "
                    f"correction_mag={b.correction_magnitude:.3f}, "
                    f"fidelity={b.fidelity_score:.3f}"
                )

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
        """Compute naturalness score by detecting wobbles in the animation."""
        total_sign_changes = 0
        total_channels = 0

        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if len(keyframes) < 4:
                    continue

                if cached_resampled and bone_name in cached_resampled and channel in cached_resampled[bone_name]:
                    data = cached_resampled[bone_name][channel]
                else:
                    data = keyframes

                if len(data) < 4:
                    continue

                values = [v for t, v in data]
                n = len(values)

                first_deriv = []
                for i in range(n - 1):
                    dt = data[i + 1][0] - data[i][0]
                    if dt > 1e-12:
                        first_deriv.append((values[i + 1] - values[i]) / dt)
                    else:
                        first_deriv.append(0.0)

                second_deriv = []
                for i in range(len(first_deriv) - 1):
                    dt = data[i + 2][0] - data[i][0]
                    if dt > 1e-12:
                        second_deriv.append((first_deriv[i + 1] - first_deriv[i]) / dt)
                    else:
                        second_deriv.append(0.0)

                sign_changes = 0
                for i in range(1, len(second_deriv)):
                    if second_deriv[i] * second_deriv[i - 1] < 0:
                        if abs(second_deriv[i]) > 0.01 or abs(second_deriv[i - 1]) > 0.01:
                            sign_changes += 1

                total_sign_changes += sign_changes
                total_channels += 1

        if total_channels == 0:
            return 1.0, 0

        avg_sign_changes = total_sign_changes / total_channels
        expected_per_channel = max(2.0, duration * 3.0)

        if avg_sign_changes <= expected_per_channel:
            naturalness = 1.0
        else:
            excess = avg_sign_changes - expected_per_channel
            naturalness = max(0.0, 1.0 - excess / (expected_per_channel * 2.0))

        return naturalness, total_sign_changes

# ============================================================================
# Main Converter (v8: truly-empty purge, unknown reclass, walk mirror, smart output)
# ============================================================================

class BBModelAnimationConverter:
    """Universal animation converter for .bbmodel files (v8).

    Pipeline:
      1. Extract animations from .bbmodel (with enhanced empty/duplicate handling)
      2. Normalize animation names to GeckoLib convention
      3. [v8 NEW] Reclassify unknown animations based on content analysis
      4. For loop animations: detect optimal loop duration (velocity-weighted scoring)
      5. For periodic animations: detect and enhance periodicity
      6. [v8 NEW] Walk half-cycle detection & mirroring for sparse keyframes
      7. [v8 ENHANCED] C1 continuity with periodicity-aware blending & phase unwrap
      8. Simplify keyframes
      9. Build GeckoLib .animation.json
     10. [v8 NEW] Truly-empty animation purge (after C1 enforcement)
     11. [v8 ENHANCED] Smart idle dedup with cross-model awareness
     12. Quality report (score ENHANCED version)
     13. [v8 NEW] File-level smart output (skip files with only empty animations)

    v8 Improvements over v7:
      - Truly-empty animation purge after C1 enforcement
      - Unknown animation re-classification by content analysis
      - Walk half-cycle detection & mirroring
      - Smart idle dedup with cross-model awareness
      - Enhanced C1 with periodicity-aware blending & phase unwrap
      - Auto-loop with velocity zero-crossing priority for walks
      - Animation file smart output

    Inherited from v7:
      - Cubic Hermite Transition Zone (C0+C1 at BOTH boundaries)
      - Enhanced walk cycle detection & mirroring (periodic enhancer)
      - Idle animation smart deduplication (idle aliases, merge)
      - Smart empty animation elimination (static marking, skip_meaningless)
      - Auto-loop with velocity matching (±tick, weighted scoring)
      - UV mapping post-processing
      - Quality scoring adjustments
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()
        self.extractor = BBModelAnimationExtractor(self.config)
        self.loop_detector = AutoLoopDetector(self.config)
        self.c1_enforcer = C1ContinuityEnforcer(self.config)
        self.json_builder = GeckoLibJSONBuilder(self.config)
        self.quality_reporter = QualityReporter(self.config)
        self.name_normalizer = AnimationNameNormalizer()
        self.periodic_enhancer = PeriodicAnimationEnhancer(self.config)

    def convert_file(self, bbmodel_path: str,
                     output_path: Optional[str] = None,
                     category_model_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """Convert all animations in a .bbmodel file.

        v8 Pipeline:
          1. Extract (with enhanced empty/duplicate filtering)
          2. Normalize animation names to GeckoLib convention
          3. [v8] Reclassify unknown animations based on content analysis
          4. Duration optimization for loop animations
          5. Periodic animation enhancement
          6. [v8] Walk half-cycle detection & mirroring for sparse keyframes
          7. [v8] C1 enforcement with periodicity-aware blending & phase unwrap
          8. Build GeckoLib JSON
          9. [v8] Truly-empty animation purge (after C1 enforcement)
         10. [v8] Smart idle dedup with cross-model awareness
         11. Quality report
         12. [v8] File-level smart output

        Args:
            bbmodel_path: Path to .bbmodel file
            output_path: Path for output .animation.json (None = dry run)
            category_model_names: List of other model names in same category
                (for cross-model idle dedup in multi-part entities)
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
            'static_preserved': extracted.get('static_preserved', []),
            'near_empty': extracted.get('near_empty', []),
            'merge_info': extracted.get('merge_info', []),
            'name_normalizations': [],
            'global_cubic_used': 0,
            'local_blend_used': 0,
            'static_snap_used': 0,
            'bridge_used': 0,
            'health_score': 0.0,
            'idle_enriched_count': 0,
            # v8 NEW stats
            'animations_purged_empty': [],      # names of purged truly-empty animations
            'idle_dedup_removed': [],           # names of removed idle animations
            'unknown_reclassified': [],         # old_name -> new_name reclassifications
            'walk_half_cycle_mirrored': [],     # names of mirrored walk animations
            'files_skipped_all_empty': False,   # whether this file was skipped entirely
        }

        for anim_name, anim_data in extracted['animations'].items():
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

            # Step 3 [v8 NEW]: Reclassify unknown animations
            reclassified_from = ""
            if self.config.reclassify_unknown_animations:
                new_name = self._reclassify_unknown_animation(
                    anim_name, bone_channels, current_duration, extracted['animations'].keys()
                )
                if new_name != anim_name:
                    reclassified_from = anim_name
                    stats['unknown_reclassified'].append({
                        'original': anim_name,
                        'reclassified': new_name,
                    })
                    anim_name = new_name

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
                    reclassified_from=reclassified_from,
                )
                quality_reports[anim_name] = qreport
                continue

            # Compute duration from keyframes if length=0
            if current_duration <= 0:
                current_duration = self._compute_duration_from_keyframes(bone_channels)
                if current_duration <= 0:
                    current_duration = 1.0

            # Step 4: Duration optimization for loop animations only
            duration_change_reason = ""
            if loop_mode == "loop" and self.config.enable_duration_optimization:
                optimal_duration, loop_diag = self.loop_detector.detect_optimal_duration(
                    bone_channels, current_duration, interpolation, anim_name=anim_name
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

                # v8: For walk animations with common 0.6667s durations, also check
                # if snapping to 0.65 or 0.70 gives better C1
                if self.config.walk_tick_snap_durations and anim_name:
                    name_lower = anim_name.lower()
                    is_walk = any(p in name_lower for p in ('walk', 'run'))
                    if is_walk and not should_change:
                        for snap_dur in self.config.walk_tick_snap_durations:
                            if abs(current_duration - snap_dur) < 0.02:
                                # Check if snapping to the tick boundary is better
                                snap_candidate = self.loop_detector._snap_to_tick(snap_dur)
                                c0_snap, c1_snap, _ = self.loop_detector._evaluate_continuity_combined(
                                    self._resample_all_channels(bone_channels, current_duration, interpolation),
                                    snap_candidate, self.config.resample_rate
                                ) if loop_diag.get('resampled') else (float('inf'), float('inf'), float('inf'))
                                if c0_snap < current_c0 * 0.9 or c1_snap < loop_diag.get('current_c1_error', float('inf')) * 0.8:
                                    optimal_duration = snap_candidate
                                    should_change = True
                                    method = 'walk_tick_snap'
                                    break

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

            # Step 5: Periodic Animation Enhancement
            periodicity_info = {
                'is_periodic': False,
                'period': None,
                'periodicity_score': 0.0,
                'cycle_completeness': 0.0,
                'should_enhance': False,
            }
            periodic_enhanced = False
            periodic_method = 'none'

            if (self.config.periodic_enhance_enabled and
                loop_mode == "loop" and not is_static):
                periodicity_info = self.periodic_enhancer.detect_periodicity(
                    anim_name, bone_channels, current_duration, interpolation
                )

                if periodicity_info.get('should_enhance', False):
                    old_dur = current_duration
                    bone_channels, current_duration, enhance_info = \
                        self.periodic_enhancer.enhance_periodic(
                            bone_channels, current_duration, periodicity_info,
                            anim_name=anim_name, interpolation=interpolation
                        )
                    if enhance_info.get('enhanced', False):
                        periodic_enhanced = True
                        periodic_method = enhance_info.get('method', 'unknown')
                        stats['duration_adjustments'].append({
                            'animation': anim_name,
                            'from': old_dur,
                            'to': current_duration,
                            'method': f'periodic_{periodic_method}',
                            'reason': f'Periodic enhancement: {periodic_method}',
                        })

            # Step 6 [v8 NEW]: Walk half-cycle detection & mirroring for sparse keyframes
            walk_half_cycle_mirrored = False
            if (self.config.walk_half_cycle_detection and
                loop_mode == "loop" and not is_static):
                bone_channels, current_duration, mirror_info = self._detect_and_mirror_walk_half_cycle(
                    anim_name, bone_channels, current_duration, interpolation
                )
                if mirror_info.get('mirrored', False):
                    walk_half_cycle_mirrored = True
                    stats['walk_half_cycle_mirrored'].append({
                        'animation': anim_name,
                        'method': mirror_info.get('method', 'unknown'),
                        'original_duration': mirror_info.get('original_duration', current_duration),
                        'new_duration': current_duration,
                    })

            # CACHED RESAMPLING — resample once, use for both C1 and quality
            cached_resampled = self._resample_all_channels(
                bone_channels, current_duration, interpolation
            )

            # Step 7 [v8 ENHANCED]: C1 continuity with periodicity-aware blending & phase unwrap
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
                # v8: Phase-unwrap rotation channels before C1 enforcement
                if self.config.rotation_phase_unwrap:
                    bone_channels = self._phase_unwrap_rotations(bone_channels, current_duration)

                bone_channels, blend_diag = self.c1_enforcer.enforce(
                    bone_channels, current_duration, interpolation,
                    cached_resampled=cached_resampled,
                    periodicity_info=periodicity_info if self.config.periodicity_aware_blending else None
                )
                stats['global_cubic_used'] += blend_diag.get('global_cubic_count', 0)
                stats['local_blend_used'] += blend_diag.get('local_blend_count', 0)
                stats['static_snap_used'] += blend_diag.get('static_snap_count', 0)
                stats['bridge_used'] += blend_diag.get('bridge_used_count', 0)

                # Update cached resampled after C1 enforcement
                cached_resampled = self._resample_all_channels(
                    bone_channels, current_duration, interpolation
                )

            # Step 8: Build GeckoLib JSON
            anim_json = self.json_builder.build(
                anim_name, loop_mode, bone_channels, current_duration
            )
            all_animations[anim_name] = anim_json

            # Step 9: Quality report
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

            # Periodicity and transition smoothness metrics
            qreport.periodicity_score = periodicity_info.get('periodicity_score', 0.0)
            qreport.periodic_enhanced = periodic_enhanced
            qreport.zone_blend_used = blend_diag.get('bridge_used_count', 0) > 0
            qreport.zone_blend_ratio = self.config.transition_zone_ratio if qreport.zone_blend_used else 0.0

            # v8 metrics
            qreport.reclassified_from = reclassified_from
            qreport.walk_half_cycle_mirrored = walk_half_cycle_mirrored

            # Transition smoothness score
            if loop_mode == "loop" and qreport.c0_perfect:
                qreport.transition_smoothness = 1.0
            elif loop_mode == "loop":
                c0_err = max(qreport.c0_max_error_rot, qreport.c0_max_error_pos * 10)
                c1_err = max(qreport.c1_avg_error_rot, qreport.c1_avg_error_pos * 10)
                smoothness = max(0.0, 1.0 - (c0_err * 5 + c1_err * 0.5) / 10.0)
                qreport.transition_smoothness = min(1.0, max(0.0, smoothness))

            # Original animation preservation ratio
            if periodic_enhanced or walk_half_cycle_mirrored:
                qreport.original_animation_preserved = 0.6
            elif blend_diag.get('global_cubic_count', 0) > 0:
                qreport.original_animation_preserved = 0.95
            elif blend_diag.get('local_blend_count', 0) > 0:
                qreport.original_animation_preserved = 1.0 - self.config.transition_zone_ratio
            else:
                qreport.original_animation_preserved = 1.0

            quality_reports[anim_name] = qreport

            if qreport.c0_perfect:
                stats['c0_perfect_count'] += 1
            if qreport.c1_perfect:
                stats['c1_perfect_count'] += 1

        # Count idle_enriched from merge_info
        stats['idle_enriched_count'] = sum(
            1 for m in stats.get('merge_info', [])
            if m.get('action') == 'idle_enriched'
        )

        # Step 10 [v8 NEW]: Truly-empty animation purge (after C1 enforcement)
        if self.config.purge_truly_empty_animations:
            all_animations, quality_reports, purged = self._purge_truly_empty_animations(
                all_animations, quality_reports
            )
            stats['animations_purged_empty'] = purged
            for pname in purged:
                stats['total_animations'] -= 1

        # Step 11 [v8 ENHANCED]: Smart idle dedup with cross-model awareness
        if self.config.smart_idle_dedup:
            all_animations, quality_reports, idle_removed = self._smart_idle_dedup(
                all_animations, quality_reports, category_model_names
            )
            stats['idle_dedup_removed'] = idle_removed
            for rname in idle_removed:
                if rname in stats['total_animations']:
                    pass  # already counted

        # v7 Step: Smart Empty Animation Elimination
        all_static = True
        all_truly_empty = True
        for anim_name, anim_data in all_animations.items():
            bones = anim_data.get('bones', {})
            if bones:
                all_truly_empty = False
                if not anim_data.get('static', False):
                    all_static = False
            else:
                # No bones at all
                pass

        # Mark all animations as static if they're all near-empty
        if all_static and not all_truly_empty:
            for anim_name in all_animations:
                all_animations[anim_name]['static'] = True

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

        # Step 12 [v8 NEW]: File-level smart output
        if output_path:
            should_write = True
            skip_reason = ""

            # v8: If ALL animations are purged as truly empty, don't write
            if self.config.skip_all_empty_files and not all_animations:
                should_write = False
                skip_reason = "all_purged"
                stats['files_skipped_all_empty'] = True
            elif self.config.skip_all_empty_files and all_truly_empty:
                should_write = False
                skip_reason = "all_truly_empty"
                stats['files_skipped_all_empty'] = True
            elif not all_animations:
                if not self.config.skip_meaningless_animation_files:
                    should_write = True
                else:
                    should_write = False
                    skip_reason = "no_animations"
                    stats['files_skipped_all_empty'] = True
            elif self.config.skip_empty_animation_files:
                # Check if all animations are just static poses with no meaningful data
                has_meaningful = False
                for anim_name, anim_data in all_animations.items():
                    bones = anim_data.get('bones', {})
                    if bones:
                        has_meaningful = True
                        break
                if not has_meaningful:
                    if self.config.skip_meaningless_animation_files:
                        should_write = False
                        skip_reason = "all_static_no_bones"
                        stats['files_skipped_all_empty'] = True
                else:
                    should_write = True
            else:
                should_write = True

            if should_write:
                os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
            else:
                # Remove existing file if it was written by a previous run
                if os.path.exists(output_path):
                    os.remove(output_path)

        return {
            'model_name': model_name,
            'animations': result,
            'quality_reports': quality_reports,
            'stats': stats,
        }

    # ========================================================================
    # v8 NEW METHODS
    # ========================================================================

    def _is_truly_empty_animation(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]]
    ) -> bool:
        """v8 Improvement 1: Check if an animation has ALL zero values across ALL bone channels.

        A channel is "truly empty" if:
        - For rotation channels: max absolute value < 0.01 degrees
        - For position channels: max absolute value < 0.001 pixels

        This should be checked AFTER resampling/C1 enforcement, not before.
        """
        cfg = self.config
        rot_thresh = cfg.truly_empty_rot_threshold_post
        pos_thresh = cfg.truly_empty_pos_threshold_post

        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if not keyframes:
                    continue
                is_rotation = channel.startswith('r')
                threshold = rot_thresh if is_rotation else pos_thresh

                for t, v in keyframes:
                    if abs(v) > threshold:
                        return False
        return True

    def _purge_truly_empty_animations(
        self,
        all_animations: Dict[str, Any],
        quality_reports: Dict[str, AnimationQualityReport]
    ) -> Tuple[Dict[str, Any], Dict[str, AnimationQualityReport], List[str]]:
        """v8 Improvement 1: Purge truly-empty animations from output.

        After C1 enforcement, check if an animation has ALL zero values.
        If so, mark it as purged and remove from output.

        Returns:
            (filtered_animations, filtered_reports, list_of_purged_names)
        """
        purged = []
        filtered_animations = {}
        filtered_reports = {}

        for anim_name, anim_data in all_animations.items():
            # Check if the animation has any bone data with real values
            bones = anim_data.get('bones', {})
            if not bones:
                # No bones at all → truly empty
                purged.append(anim_name)
                if anim_name in quality_reports:
                    quality_reports[anim_name].purged_as_empty = True
                continue

            # Check each bone's channels for real values
            # GeckoLib format: bones.{bone}.{channel}.{axis}.{time: value}
            # e.g. {'rotation': {'x': {'0.0': 5.0, '0.5': 10.0}}}
            has_real_data = False
            for bone_name, bone_data in bones.items():
                for channel_name, channel_data in bone_data.items():
                    if isinstance(channel_data, dict):
                        # GeckoLib axis-keyed format: {'x': {'0.0': 5.0, ...}, 'y': {...}}
                        for axis, time_data in channel_data.items():
                            if isinstance(time_data, dict):
                                # time_data = {'0.0': 5.0, '0.5': 10.0, ...}
                                for time_key, val in time_data.items():
                                    if isinstance(val, (int, float)) and abs(val) > 0.001:
                                        has_real_data = True
                                        break
                            elif isinstance(time_data, (int, float)) and abs(time_data) > 0.001:
                                has_real_data = True
                                break
                            if has_real_data:
                                break
                    elif isinstance(channel_data, list):
                        # Fallback: list of keyframes
                        for kf in channel_data:
                            if isinstance(kf, (int, float)) and abs(kf) > 0.001:
                                has_real_data = True
                                break
                            elif isinstance(kf, dict):
                                for key, values in kf.items():
                                    if isinstance(values, list):
                                        for v in values:
                                            if isinstance(v, (int, float)) and abs(v) > 0.001:
                                                has_real_data = True
                                                break
                                    elif isinstance(values, (int, float)) and abs(values) > 0.001:
                                        has_real_data = True
                                        break
                            if has_real_data:
                                break
                    if has_real_data:
                        break
                if has_real_data:
                    break

            if has_real_data:
                filtered_animations[anim_name] = anim_data
                if anim_name in quality_reports:
                    filtered_reports[anim_name] = quality_reports[anim_name]
            else:
                purged.append(anim_name)
                if anim_name in quality_reports:
                    quality_reports[anim_name].purged_as_empty = True

        return filtered_animations, filtered_reports, purged

    def _reclassify_unknown_animation(
        self,
        anim_name: str,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        all_anim_names: Any
    ) -> str:
        """v8 Improvement 2: Reclassify animations named "unknown" based on content.

        Rules:
        - If the animation has a single keyframe at t=0 and t=T with zero values → "idle"
        - If the animation has keyframes with oscillating rotation on leg/body bones → "walk"
        - If the animation name contains "unknown", check if the same model has
          another animation with similar bone channel structure and use that type
        """
        # Only reclassify animations with "unknown" in the name
        name_lower = anim_name.lower()
        if 'unknown' not in name_lower:
            return anim_name

        cfg = self.config

        # Check if animation has any real content
        has_content = False
        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if keyframes:
                    max_val = max(abs(v) for t, v in keyframes)
                    if max_val > cfg.truly_empty_rot_threshold:
                        has_content = True
                        break
            if has_content:
                break

        if not has_content:
            # Truly empty unknown → idle
            return anim_name.replace('unknown', 'idle').replace('Unknown', 'idle')

        # Check for oscillating rotation on leg/body bones → walk
        has_leg_oscillation = False
        walk_patterns = cfg.walk_bone_patterns
        for bone_name, channels in bone_channels.items():
            bone_lower = bone_name.lower()
            is_leg = any(p in bone_lower for p in walk_patterns)

            if is_leg:
                for channel, keyframes in channels.items():
                    if not channel.startswith('r') or len(keyframes) < 2:
                        continue
                    # Check for oscillation: values change sign
                    values = [v for t, v in keyframes]
                    has_positive = any(v > 1.0 for v in values)
                    has_negative = any(v < -1.0 for v in values)
                    if has_positive and has_negative:
                        has_leg_oscillation = True
                        break
            if has_leg_oscillation:
                break

        if has_leg_oscillation:
            return anim_name.replace('unknown', 'walk').replace('Unknown', 'walk')

        # Check if any other animation in the model has similar bone structure
        # (e.g., if there's a "walk" animation, "unknown" might be another walk variant)
        for other_name in all_anim_names:
            other_lower = other_name.lower()
            if 'unknown' in other_lower:
                continue
            # Check common animation type names
            for type_name in ('walk', 'idle', 'attack', 'hurt', 'death', 'fly'):
                if type_name in other_lower:
                    return anim_name.replace('unknown', type_name).replace('Unknown', type_name)

        # Default: keep "unknown" but replace with "idle" since it has some content
        # but we can't determine what it is
        return anim_name.replace('unknown', 'idle').replace('Unknown', 'idle')

    def _detect_and_mirror_walk_half_cycle(
        self,
        anim_name: str,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        interpolation: str
    ) -> Tuple[Dict[str, Dict[str, List[Tuple[float, float]]]], float, Dict[str, Any]]:
        """v8 Improvement 3: Detect and mirror walk half-cycles for sparse keyframes.

        For walk animations with sparse keyframes (3 or fewer per channel):
        1. Detect if the animation is only a half-cycle
        2. If half-cycle: mirror the second half
        3. Ensure C0 continuity at mirror point and loop boundary

        Returns:
            (modified_bone_channels, new_duration, mirror_info)
        """
        info = {'mirrored': False, 'method': 'none', 'original_duration': duration}
        cfg = self.config

        # Only process walk/run animations
        name_lower = anim_name.lower()
        is_walk = any(p in name_lower for p in ('walk', 'run'))
        if not is_walk:
            return bone_channels, duration, info

        # Check sparseness: max keyframes per channel
        max_kf = 0
        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                max_kf = max(max_kf, len(keyframes))

        if max_kf > cfg.walk_sparse_keyframe_threshold:
            return bone_channels, duration, info

        # Check if this is a half-cycle:
        # A half-cycle has first and last keyframe values that are NOT equal
        # (half-cycle: leg swings one way, needs mirror to swing back)
        # A full cycle has first == last (leg swings out and back)
        is_half_cycle = False
        for bone_name, channels in bone_channels.items():
            bone_lower = bone_name.lower()
            is_leg = any(p in bone_lower for p in cfg.walk_bone_patterns)
            if not is_leg:
                continue
            for channel, keyframes in channels.items():
                if not channel.startswith('r') or len(keyframes) < 2:
                    continue
                first_val = keyframes[0][1]
                last_val = keyframes[-1][1]
                # If first and last are NOT approximately equal, it's a half-cycle
                if abs(first_val - last_val) > 1.0:  # more than 1 degree difference
                    is_half_cycle = True
                    break
            if is_half_cycle:
                break

        if not is_half_cycle:
            return bone_channels, duration, info

        # Mirror the half-cycle to create a full cycle
        half_duration = duration
        full_duration = duration * 2.0

        result_channels = {}
        for bone_name, channels in bone_channels.items():
            result_channels[bone_name] = {}
            bone_lower = bone_name.lower()
            is_leg = any(p in bone_lower for p in cfg.walk_bone_patterns)

            for channel, keyframes in channels.items():
                is_rotation = channel.startswith('r')
                mirrored_kfs = list(keyframes)

                for t, v in keyframes:
                    new_t = t + half_duration
                    if is_rotation:
                        # For rotation: mirror by negating (symmetric leg swing)
                        # Mean-shift: center around the mean for resting-pose centering
                        if is_leg:
                            mean_val = (keyframes[0][1] + keyframes[-1][1]) / 2.0
                            new_v = 2.0 * mean_val - v
                        else:
                            # Non-leg rotation: time-reverse (body sway mirrors)
                            new_v = v  # keep same
                    else:
                        # Position channels: mirror Y displacement for legs
                        if is_leg and channel in ('oy', 'y'):
                            mean_val = (keyframes[0][1] + keyframes[-1][1]) / 2.0
                            new_v = 2.0 * mean_val - v
                        else:
                            new_v = v  # keep same for other position channels

                    mirrored_kfs.append((new_t, new_v))

                # Sort by time
                mirrored_kfs.sort(key=lambda x: x[0])

                # Ensure C0 continuity at mirror point (t = half_duration)
                # and at loop boundary (t = full_duration ≈ t = 0)
                # The mirrored keyframe at half_duration should smoothly connect
                # to the second half. Add a small blend if needed.

                result_channels[bone_name][channel] = mirrored_kfs

        info['mirrored'] = True
        info['method'] = 'half_cycle_mirror'
        info['original_duration'] = half_duration

        return result_channels, full_duration, info

    def _smart_idle_dedup(
        self,
        all_animations: Dict[str, Any],
        quality_reports: Dict[str, AnimationQualityReport],
        category_model_names: Optional[List[str]] = None
    ) -> Tuple[Dict[str, Any], Dict[str, AnimationQualityReport], List[str]]:
        """v8 Improvement 4: Enhanced smart idle deduplication.

        Rules:
        - If model has empty idle AND real walk/attack → remove empty idle
        - If model has both "idle" and "evolved" and BOTH are empty → remove both
        - If "idle" is empty but "evolved" has real data → keep "evolved", drop "idle"
        - For multi-part entities: if one part has empty idle and another has real idle,
          remove the empty one
        """
        removed = []
        cfg = self.config

        # Find idle and other animations
        idle_names = []
        other_real_names = []
        evolved_names = []

        for anim_name, anim_data in all_animations.items():
            name_lower = anim_name.lower()
            is_idle = (name_lower == 'idle' or
                       any(alias in name_lower for alias in cfg.idle_name_aliases))
            is_evolved = 'evolved' in name_lower or 'evolve' in name_lower

            # Check if animation has real content
            # GeckoLib format: bones.{bone}.{channel}.{axis}.{time: value}
            bones = anim_data.get('bones', {})
            has_real_data = False
            if bones:
                for bone_name, bone_data in bones.items():
                    for channel_name, channel_data in bone_data.items():
                        if isinstance(channel_data, dict):
                            for axis, time_data in channel_data.items():
                                if isinstance(time_data, dict):
                                    for time_key, val in time_data.items():
                                        if isinstance(val, (int, float)) and abs(val) > 0.01:
                                            has_real_data = True
                                            break
                                elif isinstance(time_data, (int, float)) and abs(time_data) > 0.01:
                                    has_real_data = True
                                    break
                                if has_real_data:
                                    break
                        elif isinstance(channel_data, list):
                            for kf in channel_data:
                                if isinstance(kf, (int, float)) and abs(kf) > 0.01:
                                    has_real_data = True
                                    break
                                elif isinstance(kf, dict):
                                    for key, values in kf.items():
                                        if isinstance(values, list):
                                            for v in values:
                                                if isinstance(v, (int, float)) and abs(v) > 0.01:
                                                    has_real_data = True
                                                    break
                                        elif isinstance(values, (int, float)) and abs(values) > 0.01:
                                            has_real_data = True
                                            break
                                if has_real_data:
                                    break
                        if has_real_data:
                            break
                    if has_real_data:
                        break

            if is_idle:
                if not has_real_data:
                    idle_names.append(anim_name)
            elif is_evolved:
                evolved_names.append((anim_name, has_real_data))
            else:
                if has_real_data:
                    other_real_names.append(anim_name)

        # Rule 1: Remove empty idle when real walk/attack exists
        if idle_names and other_real_names:
            for idle_name in idle_names:
                if idle_name in all_animations:
                    del all_animations[idle_name]
                    if idle_name in quality_reports:
                        del quality_reports[idle_name]
                    removed.append(idle_name)

        # Rule 2: If both "idle" and "evolved" are empty, remove both
        if idle_names and evolved_names:
            for evolved_name, has_data in evolved_names:
                if not has_data:
                    # Both idle and evolved are empty → remove both
                    for idle_name in idle_names:
                        if idle_name in all_animations:
                            del all_animations[idle_name]
                            if idle_name in quality_reports:
                                del quality_reports[idle_name]
                            if idle_name not in removed:
                                removed.append(idle_name)
                    if evolved_name in all_animations:
                        del all_animations[evolved_name]
                        if evolved_name in quality_reports:
                            del quality_reports[evolved_name]
                        removed.append(evolved_name)

        # Rule 3: If "idle" is empty but "evolved" has real data → keep evolved, drop idle
        if idle_names and evolved_names:
            for evolved_name, has_data in evolved_names:
                if has_data:
                    for idle_name in idle_names:
                        if idle_name in all_animations:
                            del all_animations[idle_name]
                            if idle_name in quality_reports:
                                del quality_reports[idle_name]
                            if idle_name not in removed:
                                removed.append(idle_name)

        return all_animations, quality_reports, removed

    def _phase_unwrap_rotations(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float
    ) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
        """v8 Improvement 5: Unwrap rotation channels that wrap around.

        If rotation channels go from e.g. -170° to +170° (wrapping around
        ±180°), unwrap them to ensure smooth interpolation.
        """
        if not self.config.rotation_phase_unwrap:
            return bone_channels

        result = {}
        for bone_name, channels in bone_channels.items():
            result[bone_name] = {}
            for channel, keyframes in channels.items():
                if not channel.startswith('r') or len(keyframes) < 2:
                    result[bone_name][channel] = keyframes
                    continue

                # Unwrap: if consecutive values differ by more than 180°,
                # adjust by ±360° to minimize the jump
                unwrapped = list(keyframes)
                for i in range(1, len(unwrapped)):
                    diff = unwrapped[i][1] - unwrapped[i-1][1]
                    if diff > 180.0:
                        unwrapped[i] = (unwrapped[i][0], unwrapped[i][1] - 360.0)
                    elif diff < -180.0:
                        unwrapped[i] = (unwrapped[i][0], unwrapped[i][1] + 360.0)

                result[bone_name][channel] = unwrapped

        return result

    def _fix_uv_mapping(self, geo_json: Dict[str, Any],
                         texture_width: int, texture_height: int) -> Dict[str, Any]:
        """v7: Post-process geo.json output to fix UV issues.

        Fixes:
        - UV coordinates that exceed texture bounds → clamp
        - Up/down faces with negative uv_size → convert to positive by adjusting origin
        - Log any fixes made

        Args:
            geo_json: The geo.json dictionary to fix (modified in-place and returned)
            texture_width: Texture width in pixels
            texture_height: Texture height in pixels

        Returns:
            The modified geo_json dictionary with UV fixes applied.
        """
        fixes_log = []

        def _fix_uv_in_bone(bone: Dict[str, Any], bone_name: str = "root") -> None:
            """Recursively fix UV in bones."""
            cubes = bone.get('cubes', [])
            for cube_idx, cube in enumerate(cubes):
                uv = cube.get('uv')
                size = cube.get('size')
                if uv is None or size is None:
                    continue

                cube_id = f"{bone_name}/cube[{cube_idx}]"

                # Handle face-based UV mapping
                faces = cube.get('faces')
                if faces:
                    for face_name, face_data in faces.items():
                        face_uv = face_data.get('uv')
                        face_uv_size = face_data.get('uv_size')
                        if face_uv is None:
                            continue

                        # Clamp UV coordinates to texture bounds
                        clamped = False
                        if isinstance(face_uv, list) and len(face_uv) >= 2:
                            for i in range(2):
                                max_val = texture_width if i == 0 else texture_height
                                if face_uv[i] < 0:
                                    face_uv[i] = 0.0
                                    clamped = True
                                elif face_uv[i] > max_val:
                                    face_uv[i] = float(max_val)
                                    clamped = True

                        # Fix negative uv_size on up/down faces
                        if face_uv_size is not None and isinstance(face_uv_size, list) and len(face_uv_size) >= 2:
                            for i in range(2):
                                if face_uv_size[i] < 0:
                                    # Convert negative size to positive by adjusting origin
                                    face_uv[i] += face_uv_size[i]
                                    face_uv_size[i] = abs(face_uv_size[i])
                                    clamped = True

                        if clamped:
                            fixes_log.append(f"{cube_id}/face[{face_name}]: UV clamped/fixed")

                # Handle per-cube UV (array format)
                elif isinstance(uv, list):
                    clamped = False
                    for i in range(len(uv)):
                        max_val = texture_width if i % 2 == 0 else texture_height
                        if uv[i] < 0:
                            uv[i] = 0.0
                            clamped = True
                        elif uv[i] > max_val:
                            uv[i] = float(max_val)
                            clamped = True
                    if clamped:
                        fixes_log.append(f"{cube_id}: UV coords clamped")

            # Recurse into children
            for child in bone.get('children', []):
                child_name = child.get('name', bone_name + '/child')
                _fix_uv_in_bone(child, child_name)

        # Process all bones
        if 'bones' in geo_json:
            for bone in geo_json['bones']:
                bone_name = bone.get('name', 'unknown')
                _fix_uv_in_bone(bone, bone_name)

        if fixes_log:
            warnings.warn(
                f"UV mapping fixes applied ({len(fixes_log)} fixes): " +
                "; ".join(fixes_log[:5]) + ("..." if len(fixes_log) > 5 else "")
            )

        return geo_json

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
        """Compute animation duration from keyframe data when length=0."""
        max_time = 0.0
        has_any_motion = False
        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if keyframes:
                    max_time = max(max_time, keyframes[-1][0])
                    if keyframes[-1][0] > 0:
                        has_any_motion = True

        if max_time <= 0:
            return 1.0

        padded = max_time + TICK_DURATION
        return padded


# ============================================================================
# Batch Processing (v7)
# ============================================================================

def batch_convert(input_dir: str, output_dir: str,
                  config: ConverterConfig = None,
                  zip_path: Optional[str] = None) -> bool:
    """Batch convert all .bbmodel files in a directory tree (v7).

    For each .bbmodel file:
      - Extract geo.json + texture (using bbmodel_to_geo.py)
      - Extract and convert animations (using this v7 converter)
      - Post-process UV mapping if geo.json was created (v7)
      - Save to output directory maintaining directory structure
      - Optionally package into a ZIP file

    Returns:
        True if no errors, False otherwise.
    """
    print("=" * 70)
    print("  Universal BBModel Animation Converter (v7)")
    print("  .bbmodel -> .animation.json with Cubic Hermite C1 Correction")
    print("  GeckoLib Format for MC 1.20.1 Forge Mod Development")
    print("  [v7] Cubic Hermite Transition Zone (guaranteed C0+C1 continuity)")
    print("  [v7] No Velocity Damping for Bounce Cases")
    print("  [v7] Enhanced Walk Cycle Detection & Mirroring")
    print("  [v7] Idle Animation Smart Deduplication")
    print("  [v7] Smart Empty Animation Elimination")
    print("  [v7] Velocity-Weighted Duration Scoring (±tick refinement)")
    print("  [v7] UV Mapping Post-Processing")
    print("  [v7] Quality Scoring: Periodic Bonus, Harsher Bounce Penalty")
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
    print(f"  C1 mode: Global Cubic Correction + Cubic Hermite Transition Zone (v7)")
    print(f"  Distortion limit: {cfg.global_cubic_distortion_limit*100:.0f}%")
    print(f"  Transition zone: {cfg.transition_zone_ratio*100:.0f}% (cubic Hermite: {'ON' if cfg.transition_zone_cubic_hermite else 'OFF'})")
    print(f"  Bounce damping: {cfg.transition_zone_bounce_damp} (v7: DISABLED)")
    print(f"  Duration optimization: {'ON' if cfg.enable_duration_optimization else 'OFF'}")
    print(f"  Scoring weights: C0={cfg.c0_scoring_weight}, C1={cfg.c1_scoring_weight}")
    print(f"  Autocorrelation: {'ON (FFT)' if cfg.autocorrelation_enabled and _NUMPY_AVAILABLE else 'ON (pure)' if cfg.autocorrelation_enabled else 'OFF'}")
    print(f"  Harmonic search: {'ON' if cfg.harmonic_search_enabled else 'OFF'}")
    print(f"  Velocity zero-crossing: {'ON' if cfg.velocity_zero_crossing_loop else 'OFF'}")
    print(f"  Blend window: {cfg.blend_window_ratio*100:.0f}% base (adaptive per-channel)")
    print(f"  Early exit: C0 < {cfg.early_exit_c0_rot}deg, C1 < {cfg.early_exit_c1_rot}deg/s")
    print(f"  DP epsilon: rot={cfg.dp_epsilon_rotation}deg, pos={cfg.dp_epsilon_position}px")
    print(f"  Preserve empty as static: {'ON' if cfg.preserve_empty_as_static else 'OFF'}")
    print(f"  Skip meaningless files: {'ON' if cfg.skip_meaningless_animation_files else 'OFF'}")
    print(f"  Semantic dedup: {'ON' if cfg.semantic_dedup_enabled else 'OFF'}")
    print(f"  Content-hash dedup: {'ON' if cfg.content_hash_dedup else 'OFF'}")
    print(f"  Smart bone merge: {'ON' if cfg.smart_bone_merge else 'OFF'}")
    print(f"  Always union bones: {'ON' if cfg.always_union_bones else 'OFF'}")
    print(f"  Tick snapping: {'ON' if cfg.snap_to_ticks else 'OFF'}")
    print(f"  Name normalization: {'ON' if cfg.normalize_animation_names else 'OFF'}")
    print(f"  Walk bone patterns: {cfg.walk_bone_patterns}")
    print(f"  Idle name aliases: {cfg.idle_name_aliases}")
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
    total_idle_enriched = 0
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
        geo_json_path = None
        if geo_converter:
            geo_result = geo_converter.convert_bbmodel(bbmodel_path, out_dir)
            geo_ok = geo_result.get('success', False)
            if geo_ok:
                if geo_result.get('geo_path'):
                    all_output_files.append(geo_result['geo_path'])
                    geo_json_path = geo_result['geo_path']
                if geo_result.get('texture_path'):
                    all_output_files.append(geo_result['texture_path'])

        # Convert animations
        anim_output_path = os.path.join(out_dir, f"{name}.animation.json")
        if os.path.exists(anim_output_path):
            os.remove(anim_output_path)

        try:
            result = converter.convert_file(bbmodel_path, anim_output_path)
            stats = result['stats']

            # v7: Post-process UV mapping on geo.json if it was created
            if geo_json_path and os.path.exists(geo_json_path):
                try:
                    with open(geo_json_path, 'r', encoding='utf-8') as f:
                        geo_data = json.load(f)
                    # Get texture dimensions from the geo data
                    tex_w = geo_data.get('texture_width', 64)
                    tex_h = geo_data.get('texture_height', 64)
                    converter._fix_uv_mapping(geo_data, tex_w, tex_h)
                    with open(geo_json_path, 'w', encoding='utf-8') as f:
                        json.dump(geo_data, f, indent=2, ensure_ascii=False)
                except Exception as e:
                    pass  # UV fix is best-effort, don't fail the conversion

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
            idle_enriched = stats.get('idle_enriched_count', 0)

            total_skipped_empty += skipped
            total_deduplicated += deduped
            total_static_preserved += static_pres
            total_near_empty += near_empty
            total_global_cubic += global_cubic
            total_local_blend += local_blend
            total_bridge += bridge
            total_static_snap += static_snap
            total_idle_enriched += idle_enriched

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
                if idle_enriched:
                    extras += f" idle_rich={idle_enriched}"
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
    print("  CONVERSION SUMMARY (v7)")
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
    print(f"  Idle enriched:           {total_idle_enriched}")
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
    print("  DONE - Universal BBModel Animation Converter (v7)")
    print("  Cubic Hermite C1 Correction | No Velocity Damping | Adaptive Blend")
    print("  Enhanced Walk Cycle | Idle Smart Dedup | UV Mapping Fix")
    print("  Velocity-Weighted Scoring | Periodic Bonus | Smart Empty Elimination")
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
        description="Universal BBModel Animation Converter with Cubic Hermite C1 Correction (v7)"
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
    parser.add_argument("--distortion-limit", type=float, default=0.30,
                        help="Max correction/amplitude ratio before local blend fallback (default: 0.30)")
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
    parser.add_argument("--no-uv-fix", action="store_true",
                        help="Disable UV mapping post-processing (v7)")
    parser.add_argument("--no-velocity-zero-crossing", action="store_true",
                        help="Disable velocity zero-crossing heuristic for walk loops (v7)")
    parser.add_argument("--no-cubic-hermite", action="store_true",
                        help="Disable cubic Hermite in transition zone (use legacy quintic)")
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
        transition_zone_cubic_hermite=not args.no_cubic_hermite,
        velocity_zero_crossing_loop=not args.no_velocity_zero_crossing,
    )

    success = batch_convert(args.input, args.output, config, args.zip)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
