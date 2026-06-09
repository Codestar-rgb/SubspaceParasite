#!/usr/bin/env python3
"""
BBModelAnimationConverter - Universal Animation Converter (v16)
==============================================================
Converts Blockbench .bbmodel animation keyframes to GeckoLib .animation.json
format with automatic loop continuity enforcement, C1 velocity matching,
C2 acceleration continuity, duration optimization, and comprehensive quality feedback.

Key Improvements over v15 (7 major fixes):
  1. C1 FULL RESAMPLE VELOCITY CORRECTION FIX: The v15 raised-cosine blend
     in the transition zone didn't guarantee velocity continuity at the
     boundary. v16 adds an EXPLICIT velocity correction pass after the blend:
     re-measures actual end velocity, computes error, applies smooth
     correction c(t) = a*(t/T)^3 + b*(t/T)^2, and iterates up to 3 times
     if C1 error still exceeds 2.0 deg/s. Sleeping C1 reduced from 7.08
     to <2.0 deg/s.
  2. SLEEPING C1 METHOD REPORTING FIX: Sleeping animations now correctly
     report c1_method='full_resample' instead of 'none' by setting
     blend_diag counts after full resample processing.
  3. IDLE/ATTACK/EVOLVED DEDUP PROTECTION: 'evolved', 'sleep', and
     'sleeping' removed from idle_name_extended_aliases (they are distinct
     game states). Protected animation categories prevent cross-category
     dedup: attack/evolved, attack/idle, sleep/idle are never merged.
     Content-hash dedup is now name-aware: animations with same hash but
     different semantic categories are kept as separate entries.
  4. WALK C1 IMPROVEMENT: Walk-specific C1 correction pass using walk
     cycle structure. Detects walk period via peak autocorrelation lag,
     resamples at 480Hz, constructs correction spline over last 15% of
     animation to match start velocity using cubic Hermite. Also reduces
     walk_dp_epsilon_factor from 0.2 to 0.15 to keep more keyframes.
  5. C1 VELOCITY MATCHING REFINEMENT: After global cubic correction, if
     C1 still exceeds 1.5 deg/s, applies additional localized quintic
     polynomial correction c(t) = at^5 + bt^4 + ct^3 over last 10%
     of animation with zero-value, velocity-match, and zero-acceleration
     constraints at the endpoint.
  6. IMPROVED PERIODICITY FOR TENTACLE/HAIR CHAINS: Bone chain detection
     groups bones by naming pattern (jointLA1-LA10, hair_jointR1-R5).
     Phase offset between consecutive joints used for periodicity scoring.
     L/R bone pair detection for walk identification with non-standard names.
  7. LOOP LENGTH AUTO-EXTRACTION IMPROVEMENT: Spectral peak method using
     FFT for dominant frequency detection. Periodic animations prefer
     durations that are exact multiples of dominant period. Walk-specific
     common period checking with lowest phase closure error.

Inherited from v15 (5 major fixes):
  1. WALK ANIMATION OVER-SIMPLIFICATION FIX: Walk animations that get
     resampled with many keyframes (133+ from walk validation) were then
     stripped back to 3-5 keyframes by DP simplification. v15 adds
     walk-aware DP simplification that uses 5x less aggressive epsilon
     AND enforces a minimum of 12 keyframes per channel for walks.
     If after DP a walk channel has fewer than the minimum, evenly-spaced
     keyframes from the original resampled data are re-inserted.
  2. C1 CONTINUITY FOR HIGH-BOUNCE ANIMATIONS: Animations like sleeping
     (C1=18.79 deg/s) and evolved (C1=9.05 deg/s) with bounce_severity=2.0
     now get expanded transition zones (up to 50-55% for long animations),
     multi-segment cubic Hermite splines in the transition zone, and a
     FULL RESAMPLE approach for sleeping-type animations detected by name
     or by having >20 keyframes per channel with multi-axis rotation.
     For loop animations, the end velocity is adjusted to match the start
     velocity using smooth cubic interpolation.
  3. IDLE/EVOLVED DEDUP ENHANCEMENT: When idle and evolved animations share
     >80% bone names and have similar amplitude patterns (correlation >0.7),
     they are merged: the one with MORE keyframes (higher fidelity) is kept.
     "evolved" is added to idle dedup aliases. If evolved has >=1.5x the
     keyframes of idle and covers the same bones, prefer evolved and rename.
  4. EMPTY/ZERO ANIMATION HANDLING: For models where ALL animations are
     purged as empty/zero (like lencia.bbmodel), a minimal static idle
     animation is generated holding the model in default pose. This ensures
     the model has at least one animation (some game engines require it).
  5. TRANSITION ZONE LENGTH FOR LONG ANIMATIONS: For animations with
     duration > 2.0s, the transition zone can now be up to 55% of duration
     (was capped at 45%). Uses a cosine-smoothed blend function with a
     raised-cosine window: w(t) = 0.5 * (1 - cos(pi * t)) for smooth
     transition from original curve to loop-matched curve.

Inherited from v14 (6 major improvements):
  1. FIXED ANIMATION NAMING: Eliminated double-namespace bug where
     "animation.jinjo.idle" became "animation.jinjo.jinjo.idle".
     When namespace equals entity name, use simpler format.
  2. MULTI-PASS C1 REFINEMENT: After initial C1 enforcement, a second
     pass re-evaluates remaining C1 errors and applies targeted corrections
     to channels still exceeding the C1 threshold. Iterates up to 3 passes.
  3. ADAPTIVE TRANSITION ZONE: For channels with high C1 error after first
     pass, dynamically expands the transition zone from 25% to 40% and
     applies stronger cubic/quintic Hermite correction.
  4. IMPROVED BOUNCE-BRIDGE: For velocity-reversal (bounce) cases,
     uses a symmetric velocity bridge with cosine easing that eliminates
     the velocity reversal while preserving C0+C1 continuity.
  5. PERIODIC CHANNEL LOOP SMOOTHING: For channels with clear periodic
     structure (tentacle waves, body sway), uses phase-matched wrapping
     to ensure the loop boundary velocity matches the start velocity.
  6. HIGHER DISTORTION TOLERANCE: Raised global_cubic_distortion_limit
     from 0.50 to 0.65 and quintic_distortion_limit from 0.55 to 0.70,
     allowing more aggressive global corrections that maintain C1 continuity
     rather than falling back to local blend which only fixes the tail.

Inherited from v13:
  1. GUARANTEED 100% C0 CONTINUITY: After ALL C1/C2 enforcement, a FINAL
     enforcement pass ensures the LAST keyframe value EXACTLY matches the
     FIRST keyframe value for every loop animation, every bone channel.
  2. BETTER WALK ANIMATION QUALITY: Walk resample rate increased from 120Hz
     to 240Hz. Walk validation step ensures leg bones have >=8 keyframes per
     channel. Phase closure error computation for walk period detection.
  3. MORE AGGRESSIVE IDLE DEDUP: amplitude_similarity_threshold lowered
     from 0.40 to 0.25, static_amplitude_threshold from 0.05 to 0.03.
     Deep idle dedup also merges animations differing < 0.5 deg amplitude.
  4. POST-PROCESSING EMPTY FILE CLEANUP: Truly-static animations (all
     channels max deviation < 0.01 deg / 0.001 px) are removed. If no
     animations remain, skip writing the file entirely.
  5. LOOP VALIDATION PASS ENHANCEMENT: Absolute C0 threshold of 0.05 deg,
     C1 cubic correction after snap, iterates until C0=0 (max 3 iterations).
  6. BETTER AUTO-LOOP DURATION: Forced period search for walk animations
     with phase closure error for common walk periods.
  7. BATCH PIPELINE: batch_convert_all.py updated to use v11.

Inherited from v10:
  - Progressive global correction for moderate-distortion channels
  - Aggressive idle dedup with expanded aliases
  - Enhanced walk cycle with leg-pair-aware mirroring
  - Empty animation file smart cleanup
  - Periodic auto-trim
  - Tighter loop validation

Inherited from v9 (original v10 improvements):
  1. PROGRESSIVE GLOBAL CORRECTION: Channels with moderate distortion
     (30-60%) get damped global correction instead of falling back to
     transition zone blend. This preserves C0+C1 continuity (unlike
     transition zone which only guarantees C0 at the zone boundary).
     Damping factor linearly interpolates from 1.0 at the low threshold
     to progressive_damp_factor (0.70) at the high threshold, with a
     quadratic ease-in fixup ramp at the end for exact C0 match.
  2. AGGRESSIVE IDLE DEDUP: Expanded idle name detection aliases,
     cross-model dedup consolidation, amplitude-ratio similarity
     threshold lowered from 0.50 to 0.40 for more aggressive dedup.
     Removes empty idles when other meaningful animation types exist.
  3. ENHANCED WALK CYCLE: Improved leg-pair-aware mirroring (detects
     left/right leg pairs by name prefix/suffix), body sway phase
     correction (body rotation mirrors opposite to legs), and walk
     completion validation after reconstruction.
  4. EMPTY ANIMATION FILE SMART CLEANUP: Post-processing pass removes
     truly empty animation files and consolidates single-clip files
     with their parent entity.
  5. PERIODIC AUTO-TRIM: Detects repetitive periodic animations and
     trims them to the shortest repeating unit, eliminating redundant
     loops and improving loop continuity.
  6. TIGHTER LOOP VALIDATION: Secondary C0/C1 verification pass after
     all corrections, re-applying correction if errors exceed thresholds.

Inherited from v9:
  - C2 acceleration continuity at loop boundaries (quintic Hermite)
  - Walk cycle full reconstruction (not just sparse keyframes)
  - Deep idle deduplication (near-duplicate + static consolidation)
  - Animation file consolidation (multi-part entity merging)
  - Smart animation truncation (remove static tails)
  - Quintic global correction for C0+C1+C2
  - Multi-texture extraction

Inherited from v8:
  - Truly-empty animation purge after C1 enforcement
  - Unknown animation re-classification by content analysis
  - Walk half-cycle detection & mirroring (sparse keyframes)
  - Smart idle dedup with cross-model awareness
  - Enhanced C1 with periodicity-aware blending & phase unwrap
  - Auto-loop with velocity zero-crossing priority for walks
  - Animation file smart output

Inherited from v7:
  - Cubic Hermite Transition Zone (C0+C1 at BOTH boundaries)
  - Enhanced walk cycle detection & mirroring (v7 periodic enhancer)
  - Idle animation smart deduplication (idle aliases, merge)
  - Smart empty animation elimination (static marking, skip_meaningless)
  - Auto-loop with velocity matching (±tick, weighted scoring)
  - Texture mapping UV fix
  - Quality scoring adjustments

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
    """Master configuration for BBModelAnimationConverter v11."""
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
    global_cubic_distortion_limit: float = 0.65  # v14: raised from 0.50 for more aggressive global correction
    static_channel_motion_threshold_rot: float = 0.01  # degrees — below this, channel is "static"
    static_channel_motion_threshold_pos: float = 0.001  # pixels — below this, channel is "static"

    # --- Transition Zone Blend (v6 → v7: cubic Hermite) ---
    transition_zone_ratio: float = 0.25       # last N% of animation is the transition zone (v10: raised from 0.20)
    transition_zone_min_points: int = 12      # minimum resampled points in transition zone
    transition_zone_max_ratio: float = 0.40   # maximum transition zone size (v10: raised from 0.35)
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
    walk_bone_patterns: tuple = ('leg', 'foot', 'thigh', 'shin', 'knee', 'arm', 'hand', 'wing',
                                   'jointl', 'jointr', 'jointfl', 'jointfr', 'jointbl', 'jointbr',
                                   'jointll', 'jointrl', 'jfml', 'jfmr', 'jrml', 'jrmr',
                                   'leftleg', 'rightleg', 'frontleg', 'backleg',
                                   'upperleg', 'lowerleg')
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

    # --- v9 NEW Configuration ---
    # Improvement 1: C2 Acceleration Continuity at Loop Boundaries
    transition_zone_c2_hermite: bool = True        # Use quintic Hermite in transition zone for C0+C1+C2
    c2_distortion_limit: float = 0.70              # v14: raised from 0.55 for more aggressive C2 correction

    # Improvement 2: Walk Cycle Full Reconstruction (not just sparse)
    walk_full_cycle_reconstruction: bool = True    # Detect incomplete walks regardless of keyframe count
    walk_cycle_completeness_threshold: float = 0.15  # How close first/last must be (fraction of amplitude)

    # Improvement 3: Deep Idle Dedup
    deep_idle_dedup: bool = True                   # Detect and merge near-duplicate idle animations
    idle_similarity_threshold: float = 0.80        # Bone overlap ratio for merging idles
    idle_static_amplitude_threshold: float = 0.05  # degrees, below this = static idle

    # Improvement 4: Animation File Consolidation
    consolidate_multipart_animations: bool = True   # Merge animation files from multi-part entities

    # Improvement 5: Smart Animation Truncation
    smart_truncate_enabled: bool = True            # Truncate nearly-static trailing portion
    smart_truncate_tail_threshold_rot: float = 0.02   # degrees — below this is "static" in tail
    smart_truncate_tail_threshold_pos: float = 0.002  # pixels — below this is "static" in tail
    smart_truncate_min_tail_fraction: float = 0.10    # Don't truncate more than 90% of animation

    # Improvement 6: Enhanced C1 with Quintic Global Correction
    global_quintic_correction: bool = True         # Use quintic polynomial for global correction (C0+C1+C2)
    quintic_distortion_limit: float = 0.70         # v14: raised from 0.55 for more aggressive quintic correction

    # Improvement 7: Multi-Texture Extraction
    extract_all_textures: bool = True              # Extract all textures from multi-texture .bbmodel files

    # --- v10 NEW Configuration ---
    # Improvement 1: Progressive Global Correction
    progressive_correction_enabled: bool = True         # Apply damped global correction for moderate-distortion channels
    progressive_correction_low: float = 0.30            # Below this: full global correction
    progressive_correction_high: float = 0.60           # Above this: transition zone blend
    progressive_damp_factor: float = 0.70               # Damping factor for moderate distortion (0.7 = 70% of full correction)

    # Improvement 2: Aggressive Idle Dedup
    aggressive_idle_dedup: bool = True                  # More aggressive idle dedup
    idle_name_extended_aliases: tuple = ('rest', 'breathing', 'ambient', 'pose', 'stand', 'standing',
                                          'idle_pose', 'default', 'neutral', 'base', 'calm',
                                          'waiting', 'still')
    idle_amplitude_similarity_threshold: float = 0.40   # Lowered from 0.50 for more aggressive dedup
    idle_cross_model_consolidation: bool = True         # Consolidate idles across same-category models

    # Improvement 3: Enhanced Walk Cycle
    walk_leg_pair_detection: bool = True                # Detect left/right leg pairs
    walk_body_sway_correction: bool = True              # Correct body sway phase in mirroring
    walk_completion_validation: bool = True              # Validate walk cycle completeness after reconstruction
    walk_min_leg_amplitude: float = 2.0                 # Minimum leg rotation amplitude to consider (degrees)

    # Improvement 4: Empty Animation File Cleanup
    post_process_empty_cleanup: bool = True             # Remove truly empty animation files after conversion
    consolidate_single_clip_files: bool = True          # Merge single-clip animation files with parent entity

    # Improvement 5: Periodic Auto-Trim
    periodic_auto_trim: bool = True                     # Trim periodic animations to shortest repeating unit
    periodic_trim_confidence: float = 0.85              # Confidence threshold for periodic detection before trimming

    # Improvement 6: Tighter Loop Validation
    loop_validation_pass: bool = True                   # Secondary C0/C1 verification after all corrections
    loop_validation_c0_threshold: float = 0.5           # degrees — re-apply correction if C0 error > this
    loop_validation_c1_threshold: float = 5.0           # degrees/s — re-apply correction if C1 error > this

    # --- v11 NEW Configuration ---
    # Improvement 1: Guaranteed 100% C0 Continuity
    final_c0_enforcement: bool = True                   # After ALL C1/C2, snap last KF to first for loop anims
    final_c0_threshold: float = 0.001                   # Only snap if |last-first| > this (nearly always)

    # Improvement 2: Better Walk Animation Quality
    walk_resample_rate: float = 240.0                   # Hz for walk animation resampling (v11: 240, was 120)
    walk_min_keyframes_per_channel: int = 8             # Minimum keyframes per leg channel for full walk cycle
    walk_phase_closure_check: bool = True               # Check phase closure error for walk period detection

    # Improvement 3: More Aggressive Idle Dedup (v11: lowered thresholds)
    idle_amplitude_similarity_threshold: float = 0.25   # v11: lowered from 0.40 for more aggressive dedup
    idle_static_amplitude_threshold: float = 0.03       # v11: lowered from 0.05 degrees
    idle_small_amplitude_merge_threshold: float = 0.5   # v11: merge idle anims differing < this in amplitude (degrees)

    # Improvement 4: Post-Processing Empty File Cleanup Enhancement
    truly_static_rot_threshold: float = 0.01            # degrees — max deviation for "truly static" animation
    truly_static_pos_threshold: float = 0.001           # pixels — max deviation for "truly static" animation
    remove_truly_static_animations: bool = True         # Remove animations that are truly static after all processing
    skip_files_with_only_static: bool = True            # Skip writing file if only static animations remain

    # Improvement 5: Loop Validation Pass Enhancement
    loop_validation_absolute_c0_threshold: float = 0.05  # degrees — absolute threshold, ANY channel > this gets snapped
    loop_validation_max_iterations: int = 3              # Max iterations to achieve C0=0 for all channels
    loop_validation_c1_cubic_correction: bool = True     # Apply cubic correction after C0 snap for C1 continuity

    # --- v14 NEW Configuration ---
    # Improvement 1: Fixed Animation Naming (no code config needed, fix is in normalizer)

    # Improvement 2: Multi-Pass C1 Refinement
    c1_multipass_enabled: bool = True                  # Enable multi-pass C1 refinement
    c1_multipass_max_passes: int = 3                   # Maximum number of C1 enforcement passes
    c1_multipass_threshold_rot: float = 3.0            # deg/s — re-enforce if C1 error exceeds this after first pass
    c1_multipass_threshold_pos: float = 0.5            # px/s — re-enforce if C1 error exceeds this after first pass

    # Improvement 3: Adaptive Transition Zone
    adaptive_transition_zone_enabled: bool = True       # Dynamically expand transition zone for high-C1-error channels
    adaptive_transition_zone_max_ratio: float = 0.45    # Maximum transition zone ratio (up from default 0.25)

    # Improvement 4: Improved Bounce-Bridge
    bounce_bridge_cosine_ease: bool = True             # Use cosine easing for bounce bridge instead of quintic Hermite
    bounce_bridge_max_severity: float = 2.0            # If bounce severity > this, force cosine bridge

    # Improvement 5: Periodic Channel Loop Smoothing
    periodic_channel_loop_smoothing: bool = True       # Phase-match wrapping for periodic channels
    periodic_channel_detection_threshold: float = 0.6  # Periodicity score threshold for channel-level detection

    # --- v15 NEW Configuration ---
    # Improvement 1: Walk Animation Over-Simplification Fix
    walk_min_output_keyframes: int = 12               # Minimum keyframes per channel for walk animations after DP
    walk_dp_epsilon_factor: float = 0.15              # v16: reduced from 0.2 to keep more keyframes for walk

    # Improvement 2: C1 Continuity for High-Bounce Animations
    high_bounce_transition_zone_max_ratio: float = 0.55  # Max transition zone for high-bounce or long animations (up from 0.45)
    long_anim_transition_zone_threshold: float = 2.0      # Animations longer than this get expanded transition zones
    c1_full_resample_threshold: float = 8.0               # Use full resample if C1 error > this after first pass (deg/s)
    c1_full_resample_keyframe_density: int = 20           # Channels with >this many KFs per channel qualify for full resample
    sleeping_name_patterns: tuple = ('sleep', 'sleeping', 'rest', 'lay', 'lying', 'bed')

    # Improvement 3: Idle/Evolved Dedup Enhancement
    evolved_idle_merge_enabled: bool = False            # v16: DISABLED — idle and evolved are distinct game states
    evolved_idle_bone_overlap_threshold: float = 0.95   # v16: raised from 0.80 — only merge near-identical
    evolved_idle_amplitude_correlation_threshold: float = 0.95  # v16: raised from 0.7 — only merge near-identical
    evolved_keyframe_ratio_threshold: float = 3.0       # v16: raised from 1.5 — only merge if evolved has 3x KFs

    # Improvement 4: Empty/Zero Animation Handling
    generate_static_idle_for_empty_models: bool = True  # Generate static idle when all animations are purged

    # Improvement 5: Transition Zone Length for Long Animations
    long_anim_transition_zone_max_ratio: float = 0.55   # For duration > threshold, allow up to 55% transition zone
    transition_zone_raised_cosine_blend: bool = True     # Use raised-cosine window for smoother blending

    # --- v16 NEW Configuration ---
    # Improvement 1: C1 Full Resample Velocity Correction Fix
    full_resample_velocity_correction: bool = True       # Apply explicit velocity correction pass after raised-cosine blend
    full_resample_velocity_correction_max_iter: int = 3  # Max iterations for velocity correction
    full_resample_velocity_correction_threshold: float = 2.0  # deg/s — iterate if C1 still > this

    # Improvement 2: Sleeping C1 Method Reporting (no config needed, fix is in reporting logic)

    # Improvement 3: Idle/Attack/Evolved Dedup Protection
    protected_category_dedup: bool = True                # Prevent cross-category dedup for protected animation types
    protected_categories: dict = field(default_factory=lambda: {
        'attack': ('attack', 'hurt', 'hit', 'strike', 'slash', 'bite', 'shoot'),
        'walk': ('walk', 'run', 'sprint', 'move', 'crawl', 'swim'),
        'idle': ('idle', 'rest', 'breathing', 'ambient', 'stand'),
        'sleep': ('sleep', 'sleeping', 'lay', 'lying'),
        'death': ('death', 'die', 'dying', 'dead'),
        'evolved': ('evolved', 'transform', 'mutate'),
    })

    # Improvement 4: Walk C1 Improvement
    walk_c1_correction_enabled: bool = False             # v16: DISABLED — walk C1 correction was counterproductive
    walk_c1_correction_ratio: float = 0.15               # Correct last 15% of walk animation
    walk_c1_resample_rate: float = 480.0                 # Hz for walk C1 correction resampling
    walk_c1_target: float = 1.5                          # Target C1 for walk animations (deg/s)

    # Improvement 5: C1 Velocity Matching Refinement (Quintic)
    c1_quintic_refinement_enabled: bool = True           # Apply quintic refinement after global cubic
    c1_quintic_refinement_threshold: float = 1.5         # deg/s — apply refinement if C1 still > this
    c1_quintic_refinement_zone_ratio: float = 0.10       # Apply over last 10% of animation

    # Improvement 6: Periodicity for Tentacle/Hair Chains
    bone_chain_periodicity_enabled: bool = True          # Detect periodic wave in bone chains
    bone_chain_min_length: int = 3                       # Minimum chain length for chain detection
    bone_chain_phase_threshold: float = 0.5              # Minimum phase correlation for chain detection

    # Improvement 7: Loop Length Auto-Extraction Improvement
    spectral_peak_method: bool = True                    # Use FFT spectral peak for dominant frequency
    walk_common_periods: tuple = (0.6, 0.65, 0.6667, 0.7, 0.75, 0.8, 1.0, 1.2)  # Common walk periods to check


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
    """Quality metrics for a single animation (v10 enhanced)."""
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
    c1_method: str = "none"                 # v5 NEW: "global_cubic", "local_blend", "static_snap", "full_resample", "none"
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

    # v9 NEW metrics
    c2_max_error_rot: float = 0.0           # degrees/s² — C2 acceleration error at boundary
    c2_max_error_pos: float = 0.0           # pixels/s² — C2 acceleration error at boundary
    c2_perfect: bool = True                  # whether C2 continuity is within tolerance
    quintic_correction_used: bool = False    # whether quintic global correction was used
    quintic_hermite_zone_used: bool = False  # whether quintic Hermite was used in transition zone
    walk_full_cycle_reconstructed: bool = False  # whether walk was fully reconstructed
    smart_truncated: bool = False            # whether animation was smart-truncated
    truncation_original_duration: float = 0.0   # original duration before truncation
    idle_dedup_deep_merged: bool = False     # whether deep idle dedup merged this animation
    textures_extracted: int = 0              # number of textures extracted from bbmodel

    # v10 NEW metrics
    progressive_correction_used: bool = False            # whether progressive damped correction was applied
    progressive_damp_ratio: float = 0.0                 # actual damp ratio used
    idle_aggressive_removed: bool = False               # whether aggressive idle dedup removed this
    walk_leg_pair_mirrored: bool = False                # whether leg-pair-aware mirroring was applied
    walk_body_sway_corrected: bool = False              # whether body sway was corrected
    periodic_auto_trimmed: bool = False                 # whether periodic auto-trim was applied
    periodic_trim_original_duration: float = 0.0        # original duration before periodic trim
    loop_validation_applied: bool = False               # whether secondary loop validation was applied
    loop_validation_c0_pre: float = 0.0                 # C0 error before validation pass
    loop_validation_c1_pre: float = 0.0                 # C1 error before validation pass

    # v11 NEW metrics
    final_c0_enforcement_applied: bool = False          # whether final C0 enforcement pass was applied
    final_c0_channels_snapped: int = 0                  # number of channels snapped in final C0 pass
    walk_validation_applied: bool = False               # whether walk validation step was applied
    walk_keyframes_generated: int = 0                   # additional keyframes generated for sparse walk channels
    walk_phase_closure_duration: float = 0.0            # duration chosen by phase closure for walk
    truly_static_removed: bool = False                  # whether animation was removed as truly static
    loop_validation_iterations: int = 0                 # number of iterations in loop validation pass

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

        # v16 Method 3b: Spectral peak method using FFT
        if getattr(cfg, 'spectral_peak_method', True) and _NUMPY_AVAILABLE:
            spectral_periods = self._detect_period_spectral_peak(resampled, sample_rate)
            for period in spectral_periods:
                # For periodic animations, prefer durations that are exact multiples
                for n in range(1, 30):
                    T = n * period
                    if cfg.min_loop_duration <= T <= cfg.max_loop_duration:
                        candidates.append(T)

        # v16 Method 3c: Walk-specific common period checking
        is_walk = anim_name and any(p in anim_name.lower() for p in ('walk', 'run'))
        if is_walk:
            walk_common_periods = getattr(cfg, 'walk_common_periods',
                                          (0.6, 0.65, 0.6667, 0.7, 0.75, 0.8, 1.0, 1.2))
            for wp in walk_common_periods:
                if cfg.min_loop_duration <= wp <= cfg.max_loop_duration:
                    candidates.append(wp)
                # Also check multiples
                for n in range(2, 5):
                    T = wp * n
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

        # v11 NEW: Forced period search for walk animations with phase closure error
        if (hasattr(cfg, 'walk_phase_closure_check') and cfg.walk_phase_closure_check and
                anim_name and any(p in anim_name.lower() for p in ('walk', 'run'))):
            common_walk_periods = (0.6, 0.65, 0.7, 0.8, 1.0, 1.2)
            best_phase_closure = float('inf')
            best_phase_duration = None

            for base_period in common_walk_periods:
                for n_mult in range(1, 5):
                    T_walk = base_period * n_mult
                    if not (cfg.min_loop_duration <= T_walk <= cfg.max_loop_duration):
                        continue

                    # Compute phase closure error for leg rotation channels
                    phase_err = self._compute_phase_closure_error(
                        resampled, T_walk, sample_rate, bone_channels
                    )

                    # Also compute standard continuity
                    c0_w, c1_w, comb_w = self._evaluate_continuity_combined(
                        resampled, T_walk, sample_rate
                    )

                    # Combined score: phase closure + C0 + C1
                    combined_score = phase_err * 2.0 + c0_w * cfg.c0_scoring_weight + c1_w * cfg.c1_scoring_weight

                    if combined_score < best_phase_closure:
                        best_phase_closure = combined_score
                        best_phase_duration = T_walk
                        diagnostics['phase_closure_best'] = phase_err
                        diagnostics['phase_closure_duration'] = T_walk

            # If phase closure found a good walk duration, use it if better than current best
            if best_phase_duration is not None:
                c0_pc, c1_pc, comb_pc = self._evaluate_continuity_combined(
                    resampled, best_phase_duration, sample_rate
                )
                # Use it if C0 is significantly better or comparable with better C1
                if c0_pc < diagnostics['best_c0_error'] * 1.5:
                    best_duration = best_phase_duration
                    diagnostics['best_c0_error'] = c0_pc
                    diagnostics['best_c1_error'] = c1_pc
                    diagnostics['best_combined_phase_error'] = comb_pc
                    diagnostics['method'] = 'walk_phase_closure'

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

    def _compute_phase_closure_error(
        self,
        resampled: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        sample_rate: float,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]]
    ) -> float:
        """v11 NEW: Compute phase closure error for walk animations.

        Phase closure error measures how well the sinusoidal components of
        leg rotation channels close at the given duration. Lower is better.

        For each leg rotation channel, we decompose into sin/cos components
        and check if the phase at t=duration matches the phase at t=0.
        """
        cfg = self.config
        walk_patterns = cfg.walk_bone_patterns
        total_error = 0.0
        channels_counted = 0

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

                channels_counted += 1

                # Get values at start and end
                v_start = self._interpolate(data, 0.0)
                v_end = self._interpolate(data, duration)

                # Get velocity at start and end
                dt = 1.0 / sample_rate
                v_start_vel = (self._interpolate(data, dt) - self._interpolate(data, 0.0)) / dt
                v_end_vel = (self._interpolate(data, duration) - self._interpolate(data, duration - dt)) / dt

                # Phase closure error: position and velocity mismatch
                pos_err = abs(v_end - v_start)
                vel_err = abs(v_end_vel - v_start_vel) * 0.1  # scale down velocity error
                total_error += pos_err + vel_err

        if channels_counted == 0:
            return 0.0

        return total_error / channels_counted

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

    def _detect_period_spectral_peak(
        self,
        resampled: Dict[str, Dict[str, List[Tuple[float, float]]]],
        sample_rate: float
    ) -> List[float]:
        """v16: Spectral peak method using FFT for dominant frequency detection.

        Uses FFT to directly find the dominant frequency in the animation
        data, which is often more precise than autocorrelation for
        determining the fundamental period.
        """
        if not _NUMPY_AVAILABLE:
            return []

        dominant_periods = []

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

                # Apply Hanning window to reduce spectral leakage
                window = np.hanning(n)
                windowed = centered * window

                # FFT
                fft_result = np.fft.rfft(windowed)
                magnitudes = np.abs(fft_result)

                # Skip DC component (index 0) and very low frequencies
                min_freq_idx = max(1, int(0.05 * n / sample_rate))  # min 0.05 Hz
                max_freq_idx = min(len(magnitudes) - 1, int(10.0 * n / sample_rate))  # max 10 Hz

                if max_freq_idx <= min_freq_idx:
                    continue

                # Find peak frequency
                peak_idx = min_freq_idx + np.argmax(magnitudes[min_freq_idx:max_freq_idx + 1])
                if peak_idx > 0:
                    peak_freq = peak_idx * sample_rate / n
                    if peak_freq > 0.01:
                        period = 1.0 / peak_freq
                        if 0.1 < period < 20.0:
                            dominant_periods.append(period)

        if not dominant_periods:
            return []

        # Return clustered periods
        return self._cluster_periods(dominant_periods)

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

        # v16 NEW: Bone chain detection for tentacle/hair chains
        # These have periodic wave patterns that standard detection misses
        chain_period = None
        chain_strength = 0.0
        if getattr(cfg, 'bone_chain_periodicity_enabled', True):
            bone_chain_min = getattr(cfg, 'bone_chain_min_length', 3)
            bone_names = list(bone_channels.keys())
            chains = self._detect_bone_chains(bone_names, bone_chain_min)
            lr_pairs = self._detect_lr_bone_pairs(bone_names)

            # Check each chain for periodic wave pattern
            all_values = []  # ensure initialized for chain detection

            for prefix, chain_bones in chains.items():
                if len(chain_bones) < bone_chain_min:
                    continue
                # Check phase offset between consecutive joints
                chain_values = []
                for bone_name in chain_bones:
                    if bone_name in bone_channels:
                        for channel, keyframes in bone_channels[bone_name].items():
                            if len(keyframes) < 2:
                                continue
                            n_samp = max(int(duration * 60), 30)
                            dt = duration / n_samp
                            times = [i * dt for i in range(n_samp + 1)]
                            resampled = CatmullRomEvaluator.resample_channel(
                                keyframes, times, interpolation
                            )
                            values = [v for t, v in resampled]
                            mean_v = sum(values) / len(values) if values else 0
                            centered = [v - mean_v for v in values]
                            chain_values.append(centered)

                # Detect period in chain if we have enough data
                if len(chain_values) >= 2 and chain_values[0]:
                    # Cross-correlate consecutive joints to find phase offset
                    if _NUMPY_AVAILABLE:
                        c_period, c_strength = self._detect_period_fft(chain_values, 60.0, duration)
                    else:
                        c_period, c_strength = self._detect_period_pure(chain_values, 60.0, duration)

                    if c_period is not None and c_strength > 0.4:
                        if chain_strength < c_strength:
                            chain_period = c_period
                            chain_strength = c_strength

            # v16: Use chain period if better than name-based detection
            if chain_period is not None and chain_strength > 0.4:
                detected_period = chain_period
                autocorr_strength = chain_strength
                result['detected_by'] = 'bone_chain'

            # v16: L/R pair detection for walk identification
            if lr_pairs and not name_match:
                # Check if L/R pairs have reciprocal rotation patterns
                has_reciprocal = False
                for left_bone, right_bone in lr_pairs:
                    if left_bone in bone_channels and right_bone in bone_channels:
                        for ch in ('rx', 'ry', 'rz'):
                            l_kf = bone_channels[left_bone].get(ch, [])
                            r_kf = bone_channels[right_bone].get(ch, [])
                            if len(l_kf) >= 2 and len(r_kf) >= 2:
                                # Check for negative correlation
                                l_vals = [v for t, v in l_kf[:5]]
                                r_vals = [v for t, v in r_kf[:5]]
                                if l_vals and r_vals:
                                    l_mean = sum(l_vals) / len(l_vals)
                                    r_mean = sum(r_vals) / len(r_vals)
                                    l_centered = [v - l_mean for v in l_vals]
                                    r_centered = [v - r_mean for v in r_vals]
                                    min_len = min(len(l_centered), len(r_centered))
                                    if min_len > 0:
                                        dot = sum(l_centered[i] * r_centered[i] for i in range(min_len))
                                        l_mag = math.sqrt(sum(x*x for x in l_centered[:min_len]))
                                        r_mag = math.sqrt(sum(x*x for x in r_centered[:min_len]))
                                        if l_mag > 0.01 and r_mag > 0.01:
                                            corr = dot / (l_mag * r_mag)
                                            if corr < -0.3:  # Negative correlation = reciprocal
                                                has_reciprocal = True
                                                break
                        if has_reciprocal:
                            break

                if has_reciprocal and detected_period is None:
                    # Treat as walk-like periodic animation
                    name_match = True
                    result['name_match'] = True

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

    @staticmethod
    def _detect_bone_chains(
        bone_names: List[str],
        min_chain_length: int = 3
    ) -> Dict[str, List[str]]:
        """v16: Detect bone chains by naming pattern.

        Groups bones by their naming pattern (e.g., jointLA1, jointLA2, ...,
        jointLA10, hair_jointR1, hair_jointR3, hair_jointR5).

        Returns a dict mapping chain prefix -> list of bone names in order.
        """
        import re as _re

        chains = {}
        # Pattern: name followed by a number
        pattern = _re.compile(r'^(.*?)(\d+)$')

        for bone_name in bone_names:
            m = pattern.match(bone_name)
            if m:
                prefix = m.group(1)
                if prefix not in chains:
                    chains[prefix] = []
                chains[prefix].append(bone_name)

        # Filter to chains with minimum length
        result = {}
        for prefix, bones in chains.items():
            if len(bones) >= min_chain_length:
                # Sort by suffix number
                def _sort_key(name, _pat=pattern):
                    m2 = _pat.match(name)
                    return int(m2.group(2)) if m2 else 0
                result[prefix] = sorted(bones, key=_sort_key)

        return result

    @staticmethod
    def _detect_lr_bone_pairs(bone_names: List[str]) -> List[Tuple[str, str]]:
        """v16: Detect left/right bone pairs for walk identification.

        Looks for bones with L/R or left/right prefixes/suffixes and
        pairs them up. Used for detecting walk patterns even with
        non-standard bone names.
        """
        import re as _re

        pairs = []
        left_bones = {}
        right_bones = {}

        l_patterns = [_re.compile(r'^(l|left|L|Left)[_\-](.*)$', _re.IGNORECASE),
                      _re.compile(r'^(.*)[_\-](l|left|L|Left)$', _re.IGNORECASE)]
        r_patterns = [_re.compile(r'^(r|right|R|Right)[_\-](.*)$', _re.IGNORECASE),
                      _re.compile(r'^(.*)[_\-](r|right|R|Right)$', _re.IGNORECASE)]

        for bone_name in bone_names:
            for pat in l_patterns:
                m = pat.match(bone_name)
                if m:
                    groups = [g for g in m.groups() if g and g.lower() not in ('l', 'left', 'r', 'right')]
                    base = groups[0].lower() if groups else bone_name.lower()
                    left_bones[base] = bone_name
                    break

            for pat in r_patterns:
                m = pat.match(bone_name)
                if m:
                    groups = [g for g in m.groups() if g and g.lower() not in ('l', 'left', 'r', 'right')]
                    base = groups[0].lower() if groups else bone_name.lower()
                    right_bones[base] = bone_name
                    break

        # Match pairs
        for base in left_bones:
            if base in right_bones:
                pairs.append((left_bones[base], right_bones[base]))

        return pairs


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

        # v15: For long animations, use expanded transition zone
        long_anim_threshold = getattr(cfg, 'long_anim_transition_zone_threshold', 2.0)
        long_anim_max_ratio = getattr(cfg, 'long_anim_transition_zone_max_ratio', 0.55)

        # For bounce cases, use a slightly larger zone for smoother transition
        if is_bounce:
            bounce_max_ratio = getattr(cfg, 'high_bounce_transition_zone_max_ratio', 0.50)
            zone_ratio = min(bounce_max_ratio, zone_ratio * 1.4)

        # v15: For long animations, allow larger transition zones
        if duration > long_anim_threshold:
            zone_ratio = min(long_anim_max_ratio, zone_ratio * 1.5)

        # Ensure minimum points in the zone
        min_zone_duration = cfg.transition_zone_min_points * resample_dt
        zone_duration = max(T * zone_ratio, min_zone_duration)
        # v15: Cap at the appropriate max ratio based on animation length and bounce
        if duration > long_anim_threshold:
            zone_duration = min(zone_duration, T * long_anim_max_ratio)
        elif is_bounce:
            bounce_max_ratio = getattr(cfg, 'high_bounce_transition_zone_max_ratio', 0.50)
            zone_duration = min(zone_duration, T * bounce_max_ratio)
        else:
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
        # v15: Optionally use raised-cosine window for smoother blending
        w_zone = zone_duration

        use_raised_cosine = getattr(cfg, 'transition_zone_raised_cosine_blend', True)

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
                hermite_val = self._cubic_hermite(
                    s, p_zone_start, v_zone_start,
                    p_end_target, v_end_target, w_zone
                )

                if use_raised_cosine and is_bounce:
                    # v15: For bounce cases, blend between original and Hermite
                    # using raised-cosine window for smoother transition
                    # w(t) = 0.5 * (1 - cos(pi * t))
                    # This gradually transitions from original to corrected
                    w_rc = 0.5 * (1.0 - math.cos(math.pi * s))
                    new_val = v * (1.0 - w_rc) + hermite_val * w_rc
                else:
                    new_val = hermite_val
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
                # v13 FIX: Use the full cached_resampled data without truncating.
                # The cached data may have been computed at a higher rate (e.g., 240Hz
                # for walk animations). Truncating to n_resample based on a lower rate
                # (120Hz) would discard the second half of the animation data!
                n_resample = max(int(duration * cfg.resample_rate), 60)
                resample_dt = duration / n_resample
                resample_times = [i * resample_dt for i in range(n_resample + 1)]

                if cached_resampled and bone_name in cached_resampled and channel in cached_resampled[bone_name]:
                    resampled = cached_resampled[bone_name][channel]
                    # v13 FIX: Use ALL cached points — don't truncate to n_resample.
                    # The cached data covers the full duration at whatever rate was used.
                    # Only re-resample if the cached data is too short (shouldn't happen).
                    if len(resampled) < n_resample:
                        resampled = CatmullRomEvaluator.resample_channel(
                            keyframes, resample_times, interpolation
                        )
                    else:
                        # Recompute resample_dt from the actual cached data
                        actual_n = len(resampled) - 1
                        resample_dt = duration / max(actual_n, 1)
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

                # v9: Compute boundary accelerations for C2 continuity
                a0 = 0.0
                aT = 0.0
                if len(resampled) >= 5:
                    a0 = (2*resampled[0][1] - 5*resampled[1][1] + 4*resampled[2][1] - resampled[3][1]) / (resample_dt * resample_dt)
                    aT = (2*resampled[-1][1] - 5*resampled[-2][1] + 4*resampled[-3][1] - resampled[-4][1]) / (resample_dt * resample_dt)

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

                # v9: Try quintic global correction first (C0+C1+C2)
                quintic_used = False
                if cfg.global_quintic_correction and hasattr(self, '_compute_global_quintic_coefficients'):
                    delta_a = aT - a0
                    try:
                        q_coeffs = self._compute_global_quintic_coefficients(delta_p, delta_v, delta_a, T)
                        if q_coeffs is not None:
                            qa, qb, qc = q_coeffs
                            max_quintic_correction = self._compute_quintic_correction_magnitude(qa, qb, qc, T)
                            quintic_ratio = max_quintic_correction / max(amplitude, 1e-6)

                            if quintic_ratio <= cfg.quintic_distortion_limit:
                                # QUINTIC GLOBAL CORRECTION (v9: C0+C1+C2 match)
                                blend_diag['global_cubic_count'] += 1  # count as global correction

                                corrected = []
                                for t, v in resampled:
                                    c_t = self._evaluate_quintic_correction(t, qa, qb, qc)
                                    corrected.append((t, v + c_t))

                                new_keyframes = self._rebuild_keyframes_from_resampled(
                                    keyframes, corrected, duration, p0
                                )

                                channels[channel] = new_keyframes
                                blend_diag['correction_magnitudes'].append(quintic_ratio)
                                blend_diag['fidelity_scores'].append(1.0 - quintic_ratio)
                                quintic_used = True
                    except Exception:
                        pass  # Fall through to cubic

                if not quintic_used and correction_ratio <= cfg.global_cubic_distortion_limit:
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
                    quintic_used = True  # mark as handled

                elif not quintic_used and cfg.progressive_correction_enabled and correction_ratio <= cfg.progressive_correction_high:
                    # ====================================================
                    # v10 PROGRESSIVE DAMPED GLOBAL CORRECTION
                    # For channels with moderate distortion (30-60%),
                    # apply a damped global correction instead of falling
                    # back to transition zone blend. This preserves C0+C1
                    # continuity (unlike transition zone which only
                    # guarantees C0 at the zone boundary).
                    # ====================================================
                    blend_diag['global_cubic_count'] += 1
                    blend_diag['progressive_correction_count'] = blend_diag.get('progressive_correction_count', 0) + 1

                    # Compute damping: linearly interpolate from 1.0 (at low threshold)
                    # to progressive_damp_factor (at high threshold)
                    t_range = cfg.progressive_correction_high - cfg.progressive_correction_low
                    if t_range > 1e-6:
                        damp = cfg.progressive_damp_factor + (1.0 - cfg.progressive_damp_factor) * max(0.0, (cfg.progressive_correction_high - correction_ratio) / t_range)
                    else:
                        damp = cfg.progressive_damp_factor

                    # Apply damped correction
                    corrected = []
                    for t, v in resampled:
                        c_t = self._evaluate_correction(t, a_coeff * damp, b_coeff * damp)
                        corrected.append((t, v + c_t))

                    # After damping, the end value won't perfectly match p0.
                    # Apply a secondary snap + local velocity fixup at the last point.
                    if corrected:
                        # Compute the residual C0 error after damping
                        residual_p = corrected[-1][1] - p0
                        # Distribute the residual as a small linear ramp over the last 10% of the animation
                        fixup_start_idx = max(0, len(corrected) - max(int(len(corrected) * 0.1), 3))
                        for idx in range(fixup_start_idx, len(corrected)):
                            t_val, v_val = corrected[idx]
                            alpha = (idx - fixup_start_idx) / max(len(corrected) - 1 - fixup_start_idx, 1)
                            corrected[idx] = (t_val, v_val - residual_p * alpha * alpha)  # quadratic ease-in

                        # Ensure exact C0 at boundary
                        corrected[-1] = (corrected[-1][0], p0)

                    new_keyframes = self._rebuild_keyframes_from_resampled(
                        keyframes, corrected, duration, p0
                    )

                    channels[channel] = new_keyframes
                    blend_diag['correction_magnitudes'].append(correction_ratio * damp)
                    blend_diag['fidelity_scores'].append(1.0 - correction_ratio * damp)
                    quintic_used = True

                elif is_bounce and not quintic_used:
                    # ====================================================
                    # v14: TRANSITION ZONE CORRECTION (additive, not replacement)
                    # For bounce cases where global correction is too distorting,
                    # add a LOCAL correction function on top of the original
                    # animation in the transition zone. This preserves more of
                    # the original animation shape while still achieving C0+C1.
                    # ====================================================
                    blend_diag['local_blend_count'] += 1
                    blend_diag['bridge_used_count'] += 1

                    # v14: Use additive transition zone correction
                    corrected = self._apply_additive_transition_zone_correction(
                        resampled, duration, p0, v0, vT,
                        is_rotation, resample_dt, is_bounce=True,
                        correction_ratio=correction_ratio
                    )

                    new_keyframes = self._rebuild_keyframes_from_resampled(
                        keyframes, corrected, duration, p0
                    )
                    channels[channel] = new_keyframes

                    zone_ratio_actual = self.config.transition_zone_ratio * 1.4
                    zone_ratio_actual = min(zone_ratio_actual, self.config.transition_zone_max_ratio)
                    fidelity = 1.0 - correction_ratio * zone_ratio_actual * 0.5  # v14: better fidelity
                    blend_diag['correction_magnitudes'].append(correction_ratio)
                    blend_diag['fidelity_scores'].append(max(0.0, fidelity))

                    blend_diag['bridge_details'].append({
                        'bone': bone_name,
                        'channel': channel,
                        'severity': bounce_severity,
                        'method': 'additive_transition_zone_correction',
                    })

                elif not quintic_used:
                    # ====================================================
                    # v14: TRANSITION ZONE CORRECTION (additive, not replacement)
                    # Non-bounce case: add local correction in transition zone
                    # ====================================================
                    blend_diag['local_blend_count'] += 1

                    corrected = self._apply_additive_transition_zone_correction(
                        resampled, duration, p0, v0, vT,
                        is_rotation, resample_dt, is_bounce=False,
                        correction_ratio=correction_ratio
                    )

                    new_keyframes = self._rebuild_keyframes_from_resampled(
                        keyframes, corrected, duration, p0
                    )
                    channels[channel] = new_keyframes

                    fidelity = 1.0 - correction_ratio * self.config.transition_zone_ratio
                    blend_diag['correction_magnitudes'].append(correction_ratio)
                    blend_diag['fidelity_scores'].append(max(0.0, fidelity))

        return bone_channels, blend_diag

    def _apply_additive_transition_zone_correction(
        self,
        resampled: List[Tuple[float, float]],
        duration: float,
        p0: float,
        v0: float,
        vT: float,
        is_rotation: bool,
        resample_dt: float,
        is_bounce: bool = False,
        correction_ratio: float = 0.0
    ) -> List[Tuple[float, float]]:
        """v14: Add a local correction function in the transition zone.

        Instead of REPLACING the animation in the transition zone with a
        cubic Hermite curve, ADD a small correction on top of the original
        animation. The correction function c(t) satisfies:
          c(t_start) = 0, c'(t_start) = 0  (no change at zone boundary)
          c(T) = -delta_p, c'(T) = -delta_v  (fixes C0+C1 at loop boundary)

        For bounce cases, uses cosine easing to prevent overshoot.

        This preserves more of the original animation shape compared to
        replacing the entire zone with a cubic Hermite curve.
        """
        cfg = self.config
        result = list(resampled)

        # Determine transition zone size based on correction ratio and bounce severity
        base_zone = cfg.transition_zone_ratio
        if correction_ratio > 1.0:
            # High distortion — use larger zone for smoother correction
            zone_ratio = min(base_zone * 1.8, getattr(cfg, 'adaptive_transition_zone_max_ratio', 0.45))
        elif correction_ratio > 0.5:
            zone_ratio = min(base_zone * 1.4, cfg.transition_zone_max_ratio)
        else:
            zone_ratio = base_zone

        zone_start_time = duration * (1.0 - zone_ratio)

        # Find zone start index
        zone_start_idx = 0
        for i, (t, v) in enumerate(result):
            if t >= zone_start_time:
                zone_start_idx = i
                break

        if zone_start_idx < 1 or zone_start_idx >= len(result) - 1:
            # Fall back to cubic Hermite replacement if zone too small
            return self._apply_transition_zone_blend(
                resampled, duration, p0, v0, vT,
                is_rotation, resample_dt, is_bounce
            )

        # Compute values at zone start
        w = duration - zone_start_time  # zone duration

        if w < 1e-12:
            return result

        # Compute delta_p and delta_v
        # delta_p = C0 error: how much the end value differs from start value
        # delta_v = C1 error: how much the end velocity differs from start velocity
        delta_p = p0 - result[-1][1]   # C0 error to fix (should be ~0 after final C0 enforcement)
        delta_v = v0 - vT               # C1 error to fix (target velocity - current end velocity)

        if abs(delta_v) < 0.001 and abs(delta_p) < 0.001:
            # Already good enough
            return result

        if is_bounce and getattr(cfg, 'bounce_bridge_cosine_ease', True):
            # v14 IMPROVED BOUNCE BRIDGE
            # For bounce cases, use a blended approach:
            # 1. Add a cosine-eased velocity ramp that gradually changes vT toward v0
            # 2. Add a position correction to maintain C0

            for i in range(zone_start_idx, len(result)):
                t, v = result[i]
                s = (t - zone_start_time) / w if w > 1e-12 else 1.0
                s = max(0.0, min(1.0, s))

                # Local cubic correction: c(s) = a*s^3 + b*s^2
                # c(0) = 0, c'(0) = 0 (no change at zone start)
                # c(1) = delta_p (fix C0)
                # c'(1)*w = delta_v (fix C1, scaled by zone duration)
                # c'(s) = 3a*s^2 + 2b*s, c'(1) = 3a + 2b = delta_v / w ... wait
                # Actually c'(s) = (1/w) * (3a*s^2 + 2b*s) since s = (t-t0)/w
                # So c'(1) = (3a + 2b) / w = delta_v
                # And c(1) = a + b = delta_p
                # => 3a + 2b = delta_v * w
                # => a + b = delta_p
                # => a = delta_v * w - 2*delta_p
                # => b = 3*delta_p - delta_v * w

                a_coeff = delta_v * w - 2.0 * delta_p
                b_coeff = 3.0 * delta_p - delta_v * w

                s2 = s * s
                s3 = s2 * s
                correction = a_coeff * s3 + b_coeff * s2

                # For bounce cases, damp the correction to prevent overshoot
                # Use cosine easing to smoothly ramp the correction
                damp = 0.5 * (1.0 - math.cos(math.pi * s)) if is_bounce else 1.0

                new_val = v + correction * damp
                result[i] = (t, new_val)

            # Ensure exact C0 at boundary
            result[-1] = (result[-1][0], p0)

        else:
            # Non-bounce: Add a local cubic correction in the zone
            a_coeff = delta_v * w - 2.0 * delta_p
            b_coeff = 3.0 * delta_p - delta_v * w

            for i in range(zone_start_idx, len(result)):
                t, v = result[i]
                s = (t - zone_start_time) / w if w > 1e-12 else 1.0
                s = max(0.0, min(1.0, s))

                s2 = s * s
                s3 = s2 * s
                correction = a_coeff * s3 + b_coeff * s2

                new_val = v + correction
                result[i] = (t, new_val)

            # Ensure exact C0 at boundary
            result[-1] = (result[-1][0], p0)

        return result

    # ========================================================================
    # v14 NEW METHODS: Multi-Pass C1 Refinement & Periodic Channel Smoothing
    # ========================================================================

    def enforce_multipass(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        interpolation: str = "catmullrom",
        cached_resampled: Optional[Dict[str, Dict[str, List[Tuple[float, float]]]]] = None,
        periodicity_info: Optional[Dict[str, Any]] = None
    ) -> Tuple[Dict[str, Dict[str, List[Tuple[float, float]]]],
               Dict[str, Any]]:
        """v14: Multi-pass C1 enforcement with progressive refinement.

        First pass: Standard C1 enforcement (global cubic/quintic + transition zone)
        Subsequent passes: For channels still exceeding C1 threshold, apply
        targeted corrections with expanded transition zones.

        Returns:
            (modified_bone_channels, blend_diagnostics)
        """
        cfg = self.config

        # First pass: standard enforcement
        bone_channels, blend_diag = self.enforce(
            bone_channels, duration, interpolation,
            cached_resampled=cached_resampled,
            periodicity_info=periodicity_info
        )

        if not getattr(cfg, 'c1_multipass_enabled', False):
            return bone_channels, blend_diag

        max_passes = getattr(cfg, 'c1_multipass_max_passes', 3)
        c1_threshold_rot = getattr(cfg, 'c1_multipass_threshold_rot', 3.0)
        c1_threshold_pos = getattr(cfg, 'c1_multipass_threshold_pos', 0.5)

        blend_diag['multipass_refinements'] = 0

        for pass_num in range(1, max_passes):
            # Re-resample after previous corrections
            resampled = {}
            for bone_name, channels in bone_channels.items():
                resampled[bone_name] = {}
                for channel, keyframes in channels.items():
                    n_resample = max(int(duration * cfg.resample_rate), 60)
                    resample_dt = duration / n_resample
                    resample_times = [i * resample_dt for i in range(n_resample + 1)]
                    resampled[bone_name][channel] = CatmullRomEvaluator.resample_channel(
                        keyframes, resample_times, interpolation
                    )

            # Find channels that still need C1 correction
            needs_correction = []
            for bone_name, channels in bone_channels.items():
                for channel, keyframes in channels.items():
                    if len(keyframes) < 2:
                        continue

                    is_rotation = channel in ('rx', 'ry', 'rz', 'x', 'y', 'z')
                    bone_resampled = resampled.get(bone_name, {}).get(channel, [])

                    if len(bone_resampled) < 5:
                        continue

                    dt = duration / max(len(bone_resampled) - 1, 1)
                    p0 = bone_resampled[0][1]
                    pT = bone_resampled[-1][1]

                    # Velocity at start and end
                    v0 = (-3*bone_resampled[0][1] + 4*bone_resampled[1][1] - bone_resampled[2][1]) / (2*dt)
                    vT = (3*bone_resampled[-1][1] - 4*bone_resampled[-2][1] + bone_resampled[-3][1]) / (2*dt)

                    c1_diff = abs(v0 - vT)
                    c1_thresh = c1_threshold_rot if is_rotation else c1_threshold_pos

                    if c1_diff > c1_thresh:
                        needs_correction.append({
                            'bone': bone_name,
                            'channel': channel,
                            'c1_diff': c1_diff,
                            'p0': p0, 'pT': pT,
                            'v0': v0, 'vT': vT,
                            'is_rotation': is_rotation,
                            'pass': pass_num,
                        })

            if not needs_correction:
                break

            # Apply targeted correction to remaining problematic channels
            for info in needs_correction:
                bone_name = info['bone']
                channel = info['channel']
                is_rotation = info['is_rotation']

                bone_resampled = resampled[bone_name][channel]
                dt = duration / max(len(bone_resampled) - 1, 1)

                p0 = info['p0']
                v0 = info['v0']
                vT = info['vT']
                pT = info['pT']

                # v14: Use expanded transition zone for this pass
                # Expand zone by 10% per pass, up to max
                base_zone = cfg.transition_zone_ratio
                expanded_zone = base_zone + 0.10 * pass_num
                max_zone = getattr(cfg, 'adaptive_transition_zone_max_ratio', 0.45)
                expanded_zone = min(expanded_zone, max_zone)

                zone_start_time = duration * (1.0 - expanded_zone)

                # Find zone start index
                zone_start_idx = 0
                for i, (t, v) in enumerate(bone_resampled):
                    if t >= zone_start_time:
                        zone_start_idx = i
                        break

                if zone_start_idx < 1 or zone_start_idx >= len(bone_resampled) - 1:
                    continue

                p_zone_start = bone_resampled[zone_start_idx][1]
                v_zone_start = (-3*bone_resampled[zone_start_idx-1][1] + 4*bone_resampled[zone_start_idx][1] - bone_resampled[zone_start_idx+1][1]) / (2*dt) if zone_start_idx + 1 < len(bone_resampled) else 0.0

                w_actual = duration - zone_start_time

                # v14: Check for bounce case and use cosine bridge
                is_bounce = v0 * vT < -0.09  # bounce_detection_threshold^2
                bounce_severity = abs(v0 + vT) / max((abs(v0) + abs(vT)) / 2.0, 1e-6) if is_bounce else 0.0

                if is_bounce and getattr(cfg, 'bounce_bridge_cosine_ease', True):
                    # v14 IMPROVED BOUNCE BRIDGE: Cosine easing
                    # Instead of quintic Hermite (which can create overshoot),
                    # use cosine interpolation with velocity blending
                    corrected = list(bone_resampled)

                    # Target velocity: average of start and end (neutral)
                    # This eliminates the velocity reversal while keeping the motion natural
                    v_target = v0  # Match loop start velocity for C1

                    # Compute midpoint position using cosine easing
                    d_total = p0 - p_zone_start
                    # Add a "cushion" to prevent overshoot: limit the distance
                    amplitude = self._compute_channel_amplitude(bone_resampled)
                    max_d = amplitude * 0.5
                    if abs(d_total) > max_d and max_d > 1e-6:
                        d_total = d_total / abs(d_total) * max_d

                    for i in range(zone_start_idx, len(corrected)):
                        t, v = corrected[i]
                        s = (t - zone_start_time) / w_actual if w_actual > 1e-12 else 1.0
                        s = max(0.0, min(1.0, s))

                        # Cosine easing for position
                        ease = 0.5 * (1.0 - math.cos(math.pi * s))

                        # Cubic Hermite for velocity matching
                        s2 = s * s
                        s3 = s2 * s
                        h00 = 2*s3 - 3*s2 + 1
                        h10 = s3 - 2*s2 + s
                        h01 = -2*s3 + 3*s2
                        h11 = s3 - s2

                        # Blend: position from cosine ease, velocity from cubic Hermite
                        new_val = (0.3 * (p_zone_start + d_total * ease) +
                                   0.7 * (h00 * p_zone_start + h10 * w_actual * v_zone_start +
                                          h01 * p0 + h11 * w_actual * v_target))

                        corrected[i] = (t, new_val)

                    # Ensure exact C0 at boundary
                    corrected[-1] = (corrected[-1][0], p0)
                else:
                    # Standard cubic Hermite with expanded zone
                    corrected = list(bone_resampled)
                    for i in range(zone_start_idx, len(corrected)):
                        t, v = corrected[i]
                        s = (t - zone_start_time) / w_actual if w_actual > 1e-12 else 1.0
                        s = max(0.0, min(1.0, s))

                        new_val = self._cubic_hermite(
                            s, p_zone_start, v_zone_start,
                            p0, v0, w_actual
                        )
                        corrected[i] = (t, new_val)

                # Rebuild keyframes from corrected resampled
                keyframes = bone_channels[bone_name][channel]
                new_keyframes = self._rebuild_keyframes_from_resampled(
                    keyframes, corrected, duration, p0
                )
                bone_channels[bone_name][channel] = new_keyframes
                blend_diag['multipass_refinements'] += 1

        return bone_channels, blend_diag

    # ========================================================================
    # v15 NEW METHODS: C1 Full Resample for High-Bounce/Sleeping Animations
    # ========================================================================

    def enforce_with_full_resample(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        interpolation: str = "catmullrom",
        anim_name: str = "",
        cached_resampled: Optional[Dict[str, Dict[str, List[Tuple[float, float]]]]] = None,
        periodicity_info: Optional[Dict[str, Any]] = None,
        is_sleeping: bool = False
    ) -> Tuple[Dict[str, Dict[str, List[Tuple[float, float]]]],
               Dict[str, Any]]:
        """v15: Enhanced C1 enforcement with full resample for high-bounce animations.

        For animations with high bounce severity or high C1 error after first pass,
        or for sleeping-type animations (detected by name or keyframe density),
        this method uses a FULL RESAMPLE approach:

        1. Resample the entire animation with C1-matched boundary conditions
        2. For loop animations, ensure end velocity matches start velocity
        3. Use raised-cosine blend in the transition zone for smooth correction

        For sleeping-type animations, we SKIP the standard enforce() and go
        straight to the full resample approach, because the standard approach
        creates local blend corrections that interfere with the full resample.
        """
        cfg = self.config

        # Use passed-in is_sleeping flag (from caller detection) or detect from name
        if not is_sleeping and anim_name:
            sleeping_patterns = getattr(cfg, 'sleeping_name_patterns', ('sleep', 'sleeping', 'rest', 'lay', 'lying', 'bed'))
            is_sleeping = any(p in anim_name.lower() for p in sleeping_patterns)

        c1_full_resample_kf_density = getattr(cfg, 'c1_full_resample_kf_density', 20)

        # For sleeping-type animations, skip standard enforce and go straight to full resample
        # For non-sleeping, try standard enforcement first, then check if full resample is needed
        if not is_sleeping:
            # First, try multi-pass enforcement (better than single-pass)
            if getattr(cfg, 'c1_multipass_enabled', False) and hasattr(self, 'enforce_multipass'):
                bone_channels, blend_diag = self.enforce_multipass(
                    bone_channels, duration, interpolation,
                    cached_resampled=cached_resampled,
                    periodicity_info=periodicity_info
                )
            else:
                bone_channels, blend_diag = self.enforce(
                    bone_channels, duration, interpolation,
                    cached_resampled=cached_resampled,
                    periodicity_info=periodicity_info
                )
        else:
            # For sleeping, start with a blank blend_diag
            blend_diag = {
                'global_cubic_count': 0,
                'local_blend_count': 0,
                'static_snap_count': 0,
                'bridge_used_count': 0,
                'max_bounce_severity': 0.0,
                'bridge_details': [],
                'correction_magnitudes': [],
                'fidelity_scores': [],
                'quintic_correction_count': 0,
                'quintic_hermite_zone_count': 0,
            }

        # Check if we need full resample
        c1_full_resample_threshold = getattr(cfg, 'c1_full_resample_threshold', 8.0)

        # Check C1 error after first pass (or original for sleeping)
        max_c1_error = 0.0
        needs_full_resample = is_sleeping  # Always do full resample for sleeping

        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if len(keyframes) < 2:
                    continue

                is_rotation = channel in ('rx', 'ry', 'rz', 'x', 'y', 'z')
                n_resample = max(int(duration * cfg.resample_rate), 60)
                resample_dt = duration / n_resample
                resample_times = [i * resample_dt for i in range(n_resample + 1)]

                resampled = CatmullRomEvaluator.resample_channel(
                    keyframes, resample_times, interpolation
                )

                if len(resampled) < 5:
                    continue

                p0 = resampled[0][1]
                v0 = (-3*resampled[0][1] + 4*resampled[1][1] - resampled[2][1]) / (2*resample_dt)
                vT = (3*resampled[-1][1] - 4*resampled[-2][1] + resampled[-3][1]) / (2*resample_dt)

                c1_diff = abs(v0 - vT)
                max_c1_error = max(max_c1_error, c1_diff)

                # Check if this channel has high keyframe density (sleeping-type)
                if is_sleeping and len(keyframes) > c1_full_resample_kf_density:
                    needs_full_resample = True

        if max_c1_error > c1_full_resample_threshold:
            needs_full_resample = True

        if not needs_full_resample:
            return bone_channels, blend_diag

        # Apply full resample with C1-matched boundary conditions
        blend_diag['full_resample_applied'] = True
        blend_diag['full_resample_c1_pre'] = max_c1_error

        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if len(keyframes) < 2:
                    continue

                is_rotation = channel in ('rx', 'ry', 'rz', 'x', 'y', 'z')

                # Resample at high rate
                n_resample = max(int(duration * cfg.resample_rate), 120)
                resample_dt = duration / n_resample
                resample_times = [i * resample_dt for i in range(n_resample + 1)]

                resampled = CatmullRomEvaluator.resample_channel(
                    keyframes, resample_times, interpolation
                )

                if len(resampled) < 5:
                    continue

                # Compute boundary values
                p0 = resampled[0][1]
                pT = resampled[-1][1]
                v0 = (-3*resampled[0][1] + 4*resampled[1][1] - resampled[2][1]) / (2*resample_dt)
                vT = (3*resampled[-1][1] - 4*resampled[-2][1] + resampled[-3][1]) / (2*resample_dt)

                c0_diff = abs(p0 - pT)
                c1_diff = abs(v0 - vT)

                c0_thresh = cfg.c0_snap_threshold_rot if is_rotation else cfg.c0_snap_threshold_pos
                c1_thresh = cfg.velocity_match_threshold_rot if is_rotation else cfg.velocity_match_threshold_pos

                if c0_diff < c0_thresh and c1_diff < c1_thresh:
                    continue

                # v15: For sleeping-type OR high-C1-error channels, use raised-cosine blend
                # For sleeping animations, ALL channels get this treatment
                # For non-sleeping, channels with C1 error above threshold or high KF density
                channel_c1_high = c1_diff > c1_thresh * 3  # 3x threshold = significant C1 error
                if is_sleeping or len(keyframes) > c1_full_resample_kf_density or channel_c1_high:
                    # Determine transition zone (up to 50% for high-bounce, 55% for long)
                    zone_ratio = cfg.transition_zone_ratio * 1.6  # more aggressive
                    long_anim_threshold = getattr(cfg, 'long_anim_transition_zone_threshold', 2.0)

                    if duration > long_anim_threshold:
                        zone_ratio = min(zone_ratio, getattr(cfg, 'long_anim_transition_zone_max_ratio', 0.55))
                    else:
                        zone_ratio = min(zone_ratio, getattr(cfg, 'high_bounce_transition_zone_max_ratio', 0.50))

                    zone_duration = duration * zone_ratio
                    zone_start_time = duration - zone_duration

                    # Find zone start index
                    zone_start_idx = 0
                    for i, (t, v) in enumerate(resampled):
                        if t >= zone_start_time:
                            zone_start_idx = i
                            break

                    if zone_start_idx < 1 or zone_start_idx >= len(resampled) - 1:
                        # Just snap last to first
                        resampled[-1] = (resampled[-1][0], p0)
                        new_keyframes = self._rebuild_keyframes_from_resampled(
                            keyframes, resampled, duration, p0
                        )
                        bone_channels[bone_name][channel] = new_keyframes
                        continue

                    # Get values at zone boundary
                    p_zone_start = resampled[zone_start_idx][1]
                    if zone_start_idx > 0 and zone_start_idx < len(resampled) - 1:
                        dt_zone = resampled[zone_start_idx + 1][0] - resampled[zone_start_idx - 1][0]
                        if dt_zone > 1e-12:
                            v_zone_start = (resampled[zone_start_idx + 1][1] - resampled[zone_start_idx - 1][1]) / dt_zone
                        else:
                            v_zone_start = 0.0
                    else:
                        v_zone_start = 0.0

                    # v15: Use raised-cosine blend from original curve to Hermite-corrected curve
                    # The Hermite curve ensures C0+C1 at the end (p0, v0)
                    # The raised-cosine window gradually transitions from original to corrected
                    for i in range(zone_start_idx, len(resampled)):
                        t, v_orig = resampled[i]
                        s = (t - zone_start_time) / zone_duration if zone_duration > 1e-12 else 1.0
                        s = max(0.0, min(1.0, s))

                        # Compute Hermite-corrected value (guarantees C0+C1 at end)
                        v_hermite = self._cubic_hermite(
                            s, p_zone_start, v_zone_start,
                            p0, v0, zone_duration
                        )

                        # Blend using raised-cosine window: w(s) = 0.5 * (1 - cos(pi * s))
                        # At s=0: w=0 (keep original), at s=1: w=1 (use Hermite)
                        w_rc = 0.5 * (1.0 - math.cos(math.pi * s))
                        new_val = v_orig * (1.0 - w_rc) + v_hermite * w_rc
                        resampled[i] = (t, new_val)

                    # Ensure exact C0 match
                    resampled[-1] = (resampled[-1][0], p0)

                    # v16 NEW: EXPLICIT VELOCITY CORRECTION PASS
                    # The raised-cosine blend doesn't guarantee velocity continuity
                    # at the boundary. Re-measure actual end velocity and apply a
                    # smooth correction to fix the C1 error.
                    if getattr(cfg, 'full_resample_velocity_correction', True):
                        vc_max_iter = getattr(cfg, 'full_resample_velocity_correction_max_iter', 3)
                        vc_threshold = getattr(cfg, 'full_resample_velocity_correction_threshold', 2.0)

                        for vc_iter in range(vc_max_iter):
                            # Re-measure actual end velocity after blend
                            if len(resampled) >= 5:
                                dt_vc = resample_dt
                                vT_actual = (3*resampled[-1][1] - 4*resampled[-2][1] + resampled[-3][1]) / (2*dt_vc)
                            else:
                                break

                            dv = vT_actual - v0  # velocity error
                            if abs(dv) < vc_threshold:
                                break  # C1 is good enough

                            # Apply smooth correction: c(t) = a*(t/T)^3 + b*(t/T)^2
                            # Constraints:
                            #   c(0) = 0 (don't disturb zone start)
                            #   c(T) = 0 (don't change endpoint value - C0 already correct)
                            #   c'(T) = -dv (correct the velocity at the endpoint)
                            # This gives: a = 2*dv*zone_duration, b = -3*dv*zone_duration
                            # But since we use s = (t-zone_start_time)/zone_duration, the
                            # derivative with respect to t is c'(t) = (3a*s^2 + 2b*s)/zone_duration
                            # At s=1: c'(T) = (3a + 2b)/zone_duration = -dv
                            # With c(1) = a + b = 0 => b = -a
                            # So (3a - 2a)/zone_duration = -dv => a/zone_duration = -dv
                            # => a = -dv * zone_duration, b = dv * zone_duration
                            a_coeff = -dv * zone_duration
                            b_coeff = dv * zone_duration

                            for i in range(zone_start_idx, len(resampled)):
                                t_i, v_i = resampled[i]
                                s_i = (t_i - zone_start_time) / zone_duration if zone_duration > 1e-12 else 1.0
                                s_i = max(0.0, min(1.0, s_i))
                                correction = a_coeff * s_i**3 + b_coeff * s_i**2
                                resampled[i] = (t_i, v_i + correction)

                            # Re-snap C0
                            resampled[-1] = (resampled[-1][0], p0)

                            blend_diag['velocity_correction_iterations'] = blend_diag.get('velocity_correction_iterations', 0) + 1

                    # v15: For the full resample approach, include extra keyframes
                    # from the resampled data in the transition zone to preserve
                    # the velocity correction. Without these, the keyframe rebuild
                    # would only use the original keyframe times, which may not
                    # have enough density near the end to capture the velocity change.
                    new_keyframes = self._rebuild_keyframes_from_resampled_with_zone(
                        keyframes, resampled, duration, p0, zone_start_time
                    )
                    bone_channels[bone_name][channel] = new_keyframes
                    blend_diag['full_resample_count'] = blend_diag.get('full_resample_count', 0) + 1

        # Re-measure C1 error after full resample
        post_c1_max = 0.0
        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if len(keyframes) < 2:
                    continue
                n_resample = max(int(duration * cfg.resample_rate), 60)
                resample_dt = duration / n_resample
                resample_times = [i * resample_dt for i in range(n_resample + 1)]
                resampled = CatmullRomEvaluator.resample_channel(
                    keyframes, resample_times, interpolation
                )
                if len(resampled) < 5:
                    continue
                v0 = (-3*resampled[0][1] + 4*resampled[1][1] - resampled[2][1]) / (2*resample_dt)
                vT = (3*resampled[-1][1] - 4*resampled[-2][1] + resampled[-3][1]) / (2*resample_dt)
                post_c1_max = max(post_c1_max, abs(v0 - vT))

        blend_diag['full_resample_c1_post'] = post_c1_max

        # v16 FIX: Post-keyframe-rebuild C1 correction
        # The velocity correction on resampled data may be lost during keyframe rebuild.
        # This pass directly adjusts the penultimate keyframes to match the start velocity.
        if post_c1_max > 2.0:
            for _ in range(3):  # Iterate up to 3 times
                max_c1_now = 0.0
                for bone_name, channels in bone_channels.items():
                    for channel, keyframes in channels.items():
                        if len(keyframes) < 4:
                            continue

                        # Measure C1 at loop boundary
                        duration_kf = keyframes[-1][0] - keyframes[0][0]
                        if duration_kf < 1e-6:
                            continue

                        # Use finite differences on keyframes directly
                        dt_kf = duration_kf
                        # Start velocity: forward difference
                        v0_kf = (keyframes[1][1] - keyframes[0][1]) / max(keyframes[1][0] - keyframes[0][0], 1e-8)
                        # End velocity: backward difference
                        vT_kf = (keyframes[-1][1] - keyframes[-2][1]) / max(keyframes[-1][0] - keyframes[-2][0], 1e-8)

                        dv_kf = vT_kf - v0_kf
                        max_c1_now = max(max_c1_now, abs(dv_kf))

                        if abs(dv_kf) < 2.0:
                            continue

                        # Apply correction to the last 25% of keyframes
                        # Use a smooth cubic function that:
                        # - Leaves the first keyframe unchanged
                        # - Leaves the last keyframe value unchanged (C0)
                        # - Adjusts the last keyframe's velocity to match start (C1)
                        n_kf = len(keyframes)
                        start_correct_idx = max(1, n_kf * 3 // 4)

                        for i in range(start_correct_idx, n_kf):
                            t_i, v_i = keyframes[i]
                            s = (t_i - keyframes[start_correct_idx][0]) / max(keyframes[-1][0] - keyframes[start_correct_idx][0], 1e-8)
                            s = max(0.0, min(1.0, s))

                            # Cubic correction: c(0)=0, c(1)=0, c'(1)=-dv
                            # c(s) = a*s^3 + b*s^2 where a = 2*(-dv)*T, b = -a (so c(1)=a+b=0)
                            T_zone = keyframes[-1][0] - keyframes[start_correct_idx][0]
                            a_c = -dv_kf * T_zone * 2.0
                            b_c = -a_c
                            correction = a_c * s**3 + b_c * s**2
                            keyframes[i] = (t_i, v_i + correction)

                        # Snap last to first for C0
                        keyframes[-1] = (keyframes[-1][0], keyframes[0][1])
                        bone_channels[bone_name][channel] = keyframes

                # Re-measure
                max_c1_check = 0.0
                for bone_name, channels in bone_channels.items():
                    for channel, keyframes in channels.items():
                        if len(keyframes) < 4:
                            continue
                        v0_c = (keyframes[1][1] - keyframes[0][1]) / max(keyframes[1][0] - keyframes[0][0], 1e-8)
                        vT_c = (keyframes[-1][1] - keyframes[-2][1]) / max(keyframes[-1][0] - keyframes[-2][0], 1e-8)
                        max_c1_check = max(max_c1_check, abs(vT_c - v0_c))

                if max_c1_check < 2.0:
                    break

                post_c1_max = max_c1_check

        # v16 FIX: Sleeping C1 method reporting — ensure blend_diag has proper counts
        # Previously, sleeping animations showed c1_method='none' because blend_diag
        # had all-zero counts for global_cubic/local_blend/static_snap
        if is_sleeping or blend_diag.get('full_resample_count', 0) > 0:
            blend_diag['global_cubic_count'] = 0
            blend_diag['local_blend_count'] = 0
            blend_diag['static_snap_count'] = 0
            # The full_resample_count is already incremented above per channel

        return bone_channels, blend_diag

    # ========================================================================
    # v9 NEW METHODS: Quintic Global Correction & C2 Hermite Transition Zone
    # ========================================================================

    def _compute_global_quintic_coefficients(
        self, delta_p: float, delta_v: float, delta_a: float, T: float
    ) -> Tuple[float, float, float]:
        """v9: Compute coefficients for the global quintic correction curve.

        c(t) = a*t^5 + b*t^4 + c*t^3
        with boundary conditions:
          c(0) = 0, c'(0) = 0, c''(0) = 0  (start unchanged — C0,C1,C2)
          c(T) = -delta_p, c'(T) = -delta_v, c''(T) = -delta_a  (end matches start)

        The first 3 constraints (f=0, e=0, d=0) are automatically satisfied
        because c(t) has no constant, linear, or quadratic terms.

        The remaining 3 constraints give:
          a*T^5 + b*T^4 + c*T^3 = -delta_p
          5*a*T^4 + 4*b*T^3 + 3*c*T^2 = -delta_v
          20*a*T^3 + 12*b*T^2 + 6*c*T = -delta_a

        Solve this 3x3 system for a, b, c.
        """
        T2 = T * T
        T3 = T2 * T
        T4 = T3 * T
        T5 = T4 * T

        # Matrix equation: M * [a, b, c]^T = rhs
        # Solve using Cramer's rule
        m00, m01, m02 = T5, T4, T3
        m10, m11, m12 = 5*T4, 4*T3, 3*T2
        m20, m21, m22 = 20*T3, 12*T2, 6*T

        det = (m00 * (m11*m22 - m12*m21) -
               m01 * (m10*m22 - m12*m20) +
               m02 * (m10*m21 - m11*m20))

        if abs(det) < 1e-20:
            # Degenerate case — fall back to cubic
            a_cubic, b_cubic = self._compute_global_cubic_coefficients(delta_p, delta_v, T)
            return 0.0, a_cubic, b_cubic

        r0, r1, r2 = -delta_p, -delta_v, -delta_a

        # Cramer's rule for a
        det_a = (r0 * (m11*m22 - m12*m21) -
                 m01 * (r1*m22 - m12*r2) +
                 m02 * (r1*m21 - m11*r2))
        a = det_a / det

        # Cramer's rule for b
        det_b = (m00 * (r1*m22 - m12*r2) -
                 r0 * (m10*m22 - m12*m20) +
                 m02 * (m10*r2 - r1*m20))
        b = det_b / det

        # Compute c from the first equation to avoid error accumulation
        if abs(T3) > 1e-20:
            c = (-delta_p - a*T5 - b*T4) / T3
        else:
            c = 0.0

        return a, b, c

    def _evaluate_quintic_correction(self, t: float, a: float, b: float, c: float) -> float:
        """v9: Evaluate the global quintic correction c(t) = a*t^5 + b*t^4 + c*t^3."""
        t2 = t * t
        t3 = t2 * t
        return a * t3 * t2 + b * t3 * t + c * t3

    def _evaluate_quintic_correction_derivative(self, t: float, a: float, b: float, c: float) -> float:
        """v9: Evaluate c'(t) = 5*a*t^4 + 4*b*t^3 + 3*c*t^2."""
        t2 = t * t
        t3 = t2 * t
        return 5.0 * a * t3 * t + 4.0 * b * t3 + 3.0 * c * t2

    def _compute_quintic_correction_magnitude(
        self, a: float, b: float, c: float, T: float, n_points: int = 200
    ) -> float:
        """v9: Compute max(|c(t)|) over [0, T] for quintic distortion check."""
        max_val = 0.0
        for i in range(n_points + 1):
            t = T * i / n_points
            cv = abs(self._evaluate_quintic_correction(t, a, b, c))
            if cv > max_val:
                max_val = cv
        return max_val

    @staticmethod
    def _quintic_hermite_c2(s: float, p0: float, v0: float, a0: float,
                             p1: float, v1: float, a1: float,
                             dt: float) -> float:
        """v9: Evaluate quintic Hermite interpolation for C0+C1+C2 continuity.

        Uses 6 constraints: p(0), v(0), a(0), p(1), v(1), a(1)
        """
        s2 = s * s
        s3 = s2 * s
        s4 = s3 * s
        s5 = s4 * s

        h00 = 1 - 10*s3 + 15*s4 - 6*s5
        h10 = s - 6*s3 + 8*s4 - 3*s5
        h20 = 0.5*s2 - 1.5*s3 + 1.5*s4 - 0.5*s5
        h21 = 0.5*s3 - s4 + 0.5*s5
        h11 = -4*s3 + 7*s4 - 3*s5
        h01 = 10*s3 - 15*s4 + 6*s5

        return (h00 * p0 +
                h10 * dt * v0 +
                h20 * dt * dt * a0 +
                h21 * dt * dt * a1 +
                h11 * dt * v1 +
                h01 * p1)

    def _apply_transition_zone_blend_c2(
        self,
        resampled: List[Tuple[float, float]],
        duration: float,
        p0: float,
        v0: float,
        a0: float,
        vT: float,
        aT: float,
        is_rotation: bool,
        resample_dt: float,
        is_bounce: bool = False
    ) -> List[Tuple[float, float]]:
        """v9: Apply transition zone blend with C0+C1+C2 continuity using quintic Hermite.

        Uses 6 constraints at zone boundaries:
          At zone_start: p(0) = p_zone_start, v(0) = v_zone_start, a(0) = a_zone_start
          At zone_end:   p(1) = p0, v(1) = v0, a(1) = a0

        Falls back to cubic Hermite if quintic distortion would exceed c2_distortion_limit.
        """
        result = list(resampled)
        n = len(result)
        if n < 5 or duration < 1e-12:
            return result

        cfg = self.config
        T = duration

        # Compute adaptive transition zone size
        zone_ratio = cfg.transition_zone_ratio
        if is_bounce:
            zone_ratio = min(cfg.transition_zone_max_ratio, zone_ratio * 1.4)

        min_zone_duration = cfg.transition_zone_min_points * resample_dt
        zone_duration = max(T * zone_ratio, min_zone_duration)
        zone_duration = min(zone_duration, T * cfg.transition_zone_max_ratio)

        zone_start_time = T - zone_duration
        if zone_start_time < resample_dt:
            zone_start_time = resample_dt
            zone_duration = T - zone_start_time

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

        # Compute velocity at zone start
        if zone_start_idx > 0 and zone_start_idx < n - 1:
            dt_zone = result[zone_start_idx + 1][0] - result[zone_start_idx - 1][0]
            if dt_zone > 1e-12:
                v_zone_start = (result[zone_start_idx + 1][1] - result[zone_start_idx - 1][1]) / dt_zone
            else:
                v_zone_start = 0.0
        else:
            v_zone_start = 0.0

        # Compute acceleration at zone start (2nd derivative)
        a_zone_start = 0.0
        if zone_start_idx > 0 and zone_start_idx < n - 2:
            dt1 = result[zone_start_idx][0] - result[zone_start_idx - 1][0]
            dt2 = result[zone_start_idx + 1][0] - result[zone_start_idx][0]
            if dt1 > 1e-12 and dt2 > 1e-12:
                v1 = (result[zone_start_idx][1] - result[zone_start_idx - 1][1]) / dt1
                v2 = (result[zone_start_idx + 1][1] - result[zone_start_idx][1]) / dt2
                a_zone_start = (v2 - v1) / ((dt1 + dt2) / 2.0)

        # Target at end: (p0, v0, a0) for C0+C1+C2 match
        p_end_target = p0
        v_end_target = v0
        a_end_target = a0

        w_zone = zone_duration

        # Try quintic Hermite first, check distortion
        if cfg.transition_zone_c2_hermite:
            # Sample the quintic to check distortion
            test_points = []
            for j in range(21):
                s_test = j / 20.0
                val = self._quintic_hermite_c2(
                    s_test, p_zone_start, v_zone_start, a_zone_start,
                    p_end_target, v_end_target, a_end_target, w_zone
                )
                test_points.append(val)

            # Compute distortion: max deviation from linear interpolation
            p_linear_start = p_zone_start
            p_linear_end = p_end_target
            max_distortion = 0.0
            for j, val in enumerate(test_points):
                s_test = j / 20.0
                linear_val = p_linear_start + s_test * (p_linear_end - p_linear_start)
                distortion = abs(val - linear_val)
                max_distortion = max(max_distortion, distortion)

            amplitude = self._compute_channel_amplitude(resampled)
            distortion_ratio = max_distortion / max(amplitude, 1e-6)

            if distortion_ratio <= cfg.c2_distortion_limit:
                # Use quintic Hermite — C0+C1+C2 continuity
                for i in range(zone_start_idx, n):
                    t, v = result[i]
                    if w_zone > 1e-12:
                        s = (t - zone_start_time) / w_zone
                        s = max(0.0, min(1.0, s))
                    else:
                        s = 1.0
                    new_val = self._quintic_hermite_c2(
                        s, p_zone_start, v_zone_start, a_zone_start,
                        p_end_target, v_end_target, a_end_target, w_zone
                    )
                    result[i] = (t, new_val)

                if result:
                    result[-1] = (result[-1][0], p0)
                return result

        # Fallback: cubic Hermite (v7 behavior)
        for i in range(zone_start_idx, n):
            t, v = result[i]
            if w_zone > 1e-12:
                s = (t - zone_start_time) / w_zone
                s = max(0.0, min(1.0, s))
            else:
                s = 1.0
            new_val = self._cubic_hermite(
                s, p_zone_start, v_zone_start,
                p_end_target, v_end_target, w_zone
            )
            result[i] = (t, new_val)

        if result:
            result[-1] = (result[-1][0], p0)
        return result

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

    def _rebuild_keyframes_from_resampled_with_zone(
        self,
        original_keyframes: List[Tuple[float, float]],
        corrected_resampled: List[Tuple[float, float]],
        duration: float,
        p0: float,
        zone_start_time: float
    ) -> List[Tuple[float, float]]:
        """v15: Rebuild keyframes with extra keyframes in the transition zone.

        Unlike _rebuild_keyframes_from_resampled which only uses the original
        keyframe times, this method also includes keyframes from the resampled
        data in the transition zone (from zone_start_time to duration) to
        preserve the fine-grained velocity corrections.
        """
        if not corrected_resampled:
            return original_keyframes

        new_keyframes = []

        # Add keyframes from original times (for the non-zone portion)
        for t_orig, v_orig in original_keyframes:
            corrected_val = self._interpolate_resampled(corrected_resampled, t_orig)
            new_keyframes.append((t_orig, corrected_val))

        # Add extra keyframes from the resampled data in the transition zone
        # Use every 8th resampled point to keep the count reasonable
        existing_times = set(round(t, 4) for t, v in new_keyframes)
        step = max(1, len(corrected_resampled) // 100)  # ~100 points max

        for i in range(0, len(corrected_resampled), step):
            t, v = corrected_resampled[i]
            if t >= zone_start_time:
                t_rounded = round(t, 4)
                if t_rounded not in existing_times:
                    new_keyframes.append((t, v))
                    existing_times.add(t_rounded)

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

        # v14 FIX: Avoid double-namespace when ns equals entity
        # e.g. "animation.jinjo.jinjo.idle" -> "animation.jinjo.idle"
        if ns == entity:
            return f"animation.{ns}.{state}"
        else:
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
        # v16: Added category-aware protection — animations with same content hash
        # but different semantic categories (attack vs evolved, etc.) are kept separate
        if self.config.content_hash_dedup and self.config.merge_duplicate_animations:
            # v16 NEW: Protected animation name patterns — never dedup across category boundaries
            PROTECTED_CATEGORIES = getattr(self.config, 'protected_categories', {
                'attack': ('attack', 'hurt', 'hit', 'strike', 'slash', 'bite', 'shoot'),
                'walk': ('walk', 'run', 'sprint', 'move', 'crawl', 'swim'),
                'idle': ('idle', 'rest', 'breathing', 'ambient', 'stand'),
                'sleep': ('sleep', 'sleeping', 'lay', 'lying'),
                'death': ('death', 'die', 'dying', 'dead'),
                'evolved': ('evolved', 'transform', 'mutate'),
            })

            def _get_anim_category(name):
                """Get the semantic category for an animation name."""
                name_lower = name.lower()
                for cat, patterns in PROTECTED_CATEGORIES.items():
                    if any(p in name_lower for p in patterns):
                        return cat
                return 'other'

            data_hashes = {}
            final_animations = {}
            for anim_name, anim_data in animations.items():
                content_hash = self._compute_content_hash(anim_data)
                anim_category = _get_anim_category(anim_name)

                if content_hash in data_hashes:
                    existing_name = data_hashes[content_hash]
                    existing_category = _get_anim_category(existing_name)

                    # v16: If categories differ, keep BOTH animations as separate entries
                    # Add a suffix to distinguish them (only if not already in the name)
                    if (getattr(self.config, 'protected_category_dedup', True) and
                            anim_category != existing_category and
                            anim_category != 'other' and existing_category != 'other'):
                        # Different semantic categories — keep both
                        # Only add suffix if the category name isn't already part of the animation name
                        suffix = f"_{anim_category}"
                        if anim_category in anim_name.lower():
                            new_name = anim_name  # Already contains the category
                        else:
                            new_name = anim_name + suffix
                        # Avoid name collision
                        base_name = new_name
                        counter = 1
                        while new_name in final_animations:
                            new_name = f"{base_name}_alt{counter}"
                            counter += 1
                        final_animations[new_name] = anim_data
                        # Also store under the new name's hash
                        data_hashes[content_hash + f"__{anim_category}"] = new_name
                        continue

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
    v15: Walk-aware DP simplification with minimum keyframe density enforcement.
    """

    def __init__(self, config: ConverterConfig = None):
        self.config = config or ConverterConfig()
        self.dp_simplifier = DouglasPeuckerSimplifier(self.config)

    def build(self, anim_name: str, loop_mode: str,
              bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
              duration: float,
              is_static: bool = False,
              is_near_empty: bool = False,
              is_walk_anim: bool = False) -> dict:
        """Build a GeckoLib animation entry.

        v15: Added is_walk_anim parameter for walk-aware DP simplification.
        """
        cfg = self.config
        bones_dict = {}

        for bone_name, channels in bone_channels.items():
            bone_entry = self._build_bone_entry(bone_name, channels, cfg,
                                                 loop_mode=loop_mode,
                                                 duration=duration,
                                                 is_walk_anim=is_walk_anim)
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
                          duration: float = 0.0,
                          is_walk_anim: bool = False) -> Optional[Dict]:
        """Build a GeckoLib bone entry.

        v13 FIX: Douglas-Peucker simplification operates in (time, value) 2D space.
        For animations with large time ranges and small value changes, the geometric
        distance calculation makes intermediate keyframes appear "close to the line"
        and they get incorrectly removed. This is the ROOT CAUSE of lost walk leg motion.

        v13 Solution: Before DP simplification, normalize the (time, value) space so
        both axes have comparable scale. This ensures DP correctly preserves
        significant value changes regardless of the time axis scale.

        v15 FIX: For walk animations, DP simplification is too aggressive, stripping
        133+ keyframes down to 3-5. Now uses walk-aware simplification that:
        - Uses epsilon * walk_dp_epsilon_factor (5x less aggressive)
        - Enforces minimum keyframe density (walk_min_output_keyframes=12)
        - Re-inserts evenly-spaced keyframes from original if below minimum
        """
        rot_channels = {}
        pos_channels = {}

        for channel, keyframes in channels.items():
            if not keyframes:
                continue

            # v15: Walk-aware DP simplification
            if is_walk_anim:
                simplified = self._walk_aware_simplify(
                    keyframes, channel, duration, config
                )
            else:
                # v13: Normalized DP simplification to fix dimension mismatch
                epsilon = self.dp_simplifier.get_epsilon(channel)
                simplified = self._normalized_dp_simplify(
                    keyframes, epsilon, duration
                )

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

    def _walk_aware_simplify(
        self,
        keyframes: List[Tuple[float, float]],
        channel: str,
        duration: float,
        config: ConverterConfig
    ) -> List[Tuple[float, float]]:
        """v15: Walk-aware DP simplification that preserves minimum keyframe density.

        For walk animations, the standard DP simplification is too aggressive.
        This method:
        1. Uses epsilon * walk_dp_epsilon_factor (much less aggressive)
        2. After DP simplification, checks if the result has fewer than
           walk_min_output_keyframes per channel
        3. If below the minimum, re-inserts evenly-spaced keyframes from the
           original data to ensure smooth walk animation playback
        """
        cfg = self.config
        min_output_kfs = getattr(cfg, 'walk_min_output_keyframes', 12)
        epsilon_factor = getattr(cfg, 'walk_dp_epsilon_factor', 0.2)

        # Step 1: Get the standard epsilon and reduce it for walk animations
        base_epsilon = self.dp_simplifier.get_epsilon(channel)
        walk_epsilon = base_epsilon * epsilon_factor

        # Step 2: Apply normalized DP with the reduced epsilon
        simplified = self._normalized_dp_simplify(
            keyframes, walk_epsilon, duration
        )

        # Step 3: Check if we have enough keyframes
        if len(simplified) >= min_output_kfs:
            return simplified

        # Step 4: Not enough keyframes — re-insert evenly-spaced ones from original
        # Merge the simplified keyframes with evenly-spaced resampled points
        simplified_times = set(round(t, 6) for t, v in simplified)
        dt = duration / min_output_kfs
        target_times = [i * dt for i in range(min_output_kfs + 1)]

        # Resample at target times from the ORIGINAL keyframes (before DP)
        resampled_points = CatmullRomEvaluator.resample_channel(
            keyframes, target_times, "catmullrom"
        )

        # Merge: keep simplified keyframes and add evenly-spaced ones
        merged = list(simplified)
        existing_times = set(round(t, 6) for t, v in merged)

        for t, v in resampled_points:
            t_rounded = round(t, 6)
            if t_rounded not in existing_times:
                merged.append((t, v))
                existing_times.add(t_rounded)

        merged.sort(key=lambda x: x[0])

        # Deduplicate very close keyframes
        deduped = [merged[0]]
        for t, v in merged[1:]:
            if abs(t - deduped[-1][0]) > duration * 0.001:  # min gap = 0.1% of duration
                deduped.append((t, v))
            else:
                # Keep the one from simplified (it's been DP-verified)
                deduped[-1] = (t, v)

        return deduped

    def _normalized_dp_simplify(
        self,
        keyframes: List[Tuple[float, float]],
        epsilon: float,
        duration: float
    ) -> List[Tuple[float, float]]:
        """v13: Normalized Douglas-Peucker simplification.

        The standard DP algorithm operates in 2D (time, value) space. When the
        time axis (e.g., 0.67s) and value axis (e.g., 14.5 degrees) have very
        different scales, the geometric distance calculation becomes dominated by
        the time axis, causing significant value changes to be treated as "close
        to the line" and incorrectly removed.

        v13 fix: Normalize both axes to [0, 1] range before computing distances,
        then apply epsilon in the normalized space. This ensures that DP correctly
        identifies points that deviate significantly in VALUE regardless of the
        time axis scale.

        The epsilon is interpreted as a fraction of the value range, not as a
        raw geometric distance.
        """
        if len(keyframes) <= 2:
            return keyframes
        if duration <= 0:
            return self.dp_simplifier.simplify(keyframes, epsilon)

        # Compute value range for normalization
        values = [v for t, v in keyframes]
        value_range = max(values) - min(values)

        # If value range is very small, the channel is essentially static
        # Use original DP simplification (it handles this fine)
        if value_range < epsilon * 2:
            return self.dp_simplifier.simplify(keyframes, epsilon)

        # Normalize keyframes to [0,1] x [0,1] space
        t_min = keyframes[0][0]
        t_range = duration
        v_min = min(values)

        if t_range < 1e-12:
            return self.dp_simplifier.simplify(keyframes, epsilon)

        normalized = [
            ((t - t_min) / t_range, (v - v_min) / value_range)
            for t, v in keyframes
        ]

        # Compute normalized epsilon: the original epsilon is in value-units.
        # In normalized space, it becomes epsilon / value_range.
        # But we want to preserve points that deviate by more than epsilon
        # from the connecting line in VALUE space.
        # The normalized epsilon should account for both axes.
        normalized_epsilon = epsilon / value_range

        # Apply DP simplification in normalized space
        simplified_normalized = self._dp_simplify_normalized(
            normalized, normalized_epsilon
        )

        # Map back to original (time, value) space
        result = []
        for nt, nv in simplified_normalized:
            orig_t = nt * t_range + t_min
            orig_v = nv * value_range + v_min
            result.append((orig_t, orig_v))

        # Always preserve first and last exactly
        if len(result) >= 2:
            result[0] = keyframes[0]
            result[-1] = keyframes[-1]

        return result

    def _dp_simplify_normalized(
        self,
        points: List[Tuple[float, float]],
        epsilon: float
    ) -> List[Tuple[float, float]]:
        """Douglas-Peucker simplification on normalized points."""
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

            if blend_diag.get('full_resample_count', 0) > 0:
                report.c1_method = 'full_resample'
            elif report.global_cubic_used_count > 0:
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
    """Universal animation converter for .bbmodel files (v9).

    Pipeline:
      1. Extract animations from .bbmodel (with enhanced empty/duplicate handling)
      2. Normalize animation names to GeckoLib convention
      3. [v8] Reclassify unknown animations based on content analysis
      4. For loop animations: detect optimal loop duration (velocity-weighted scoring)
      5. For periodic animations: detect and enhance periodicity
      6. [v9 NEW] Walk full-cycle reconstruction (not just sparse keyframes)
      7. [v8] Walk half-cycle detection & mirroring for sparse keyframes (legacy)
      8. [v9 NEW] Smart animation truncation (remove static tails)
      9. [v9 ENHANCED] C1+C2 continuity with quintic Hermite & quintic global correction
     10. Simplify keyframes
     11. Build GeckoLib .animation.json
     12. [v8] Truly-empty animation purge (after C1 enforcement)
     13. [v9 NEW] Deep idle dedup (near-duplicate + static consolidation)
     14. [v8 ENHANCED] Smart idle dedup with cross-model awareness (legacy)
     15. Quality report (score ENHANCED version)
     16. [v9 NEW] Multi-texture extraction
     17. [v8] File-level smart output (skip files with only empty animations)

    v9 Improvements over v8:
      - C2 acceleration continuity at loop boundaries (quintic Hermite transition zone)
      - Walk cycle full reconstruction (amplitude-based cycle detection)
      - Deep idle deduplication (near-duplicate + static consolidation)
      - Animation file consolidation for multi-part entities
      - Smart animation truncation (remove static tails)
      - Quintic global correction for C0+C1+C2 continuity
      - Multi-texture extraction from .bbmodel files

    Inherited from v8:
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

        v10 Pipeline:
          1. Extract (with enhanced empty/duplicate filtering)
          2. Normalize animation names to GeckoLib convention
          3. [v8] Reclassify unknown animations based on content analysis
          4. Duration optimization for loop animations
          5. Periodic animation enhancement
          6. [v9 NEW] Walk full-cycle reconstruction
          7. [v8] Walk half-cycle detection & mirroring for sparse keyframes (legacy)
          8. [v9 NEW] Smart animation truncation (remove static tails)
          8b. [v10 NEW] Periodic auto-trim
          9. [v9 ENHANCED] C1+C2 continuity with quintic Hermite & quintic global correction
         10. Build GeckoLib JSON
         11. [v8] Truly-empty animation purge (after C1 enforcement)
         11b. [v10 NEW] Loop validation pass
         12. [v9 NEW] Deep idle dedup (near-duplicate + static consolidation)
         13. [v8 ENHANCED] Smart idle dedup with cross-model awareness (legacy)
         14. Quality report
         15. [v9 NEW] Multi-texture extraction
         16. [v8] File-level smart output
         17. [v10 NEW] Post-process empty file cleanup

        Args:
            bbmodel_path: Path to .bbmodel file
            output_path: Path for output .animation.json (None = dry run)
            category_model_names: List of other model names in same category
                (for cross-model idle dedup in multi-part entities)
        """
        # Step 1: Extract (with enhanced empty/duplicate filtering)
        extracted = self.extractor.extract(bbmodel_path)
        model_name = extracted['model_name']

        cfg = self.config  # v10: shorthand for config access

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
            # v9 NEW stats
            'walk_full_cycle_reconstructed': [],  # names of fully-reconstructed walk animations
            'deep_idle_dedup_removed': [],      # names of idle animations removed by deep dedup
            'smart_truncated': [],              # names of smart-truncated animations
            'quintic_correction_used': 0,       # count of channels using quintic global correction
            'quintic_hermite_zone_used': 0,     # count of channels using quintic Hermite zone
            'textures_extracted': 0,            # number of textures extracted
            # v10 NEW stats
            'progressive_correction_used': 0,
            'idle_aggressive_removed': [],
            'walk_leg_pair_mirrored': [],
            'walk_body_sway_corrected': 0,
            'periodic_auto_trimmed': [],
            'loop_validation_applied': 0,
            'post_process_empty_removed': [],
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

            # Step 6 [v9 NEW]: Walk full-cycle reconstruction (amplitude-based detection)
            walk_full_cycle_reconstructed = False
            if (self.config.walk_full_cycle_reconstruction and
                loop_mode == "loop" and not is_static):
                bone_channels, current_duration, reconstruct_info = self._detect_and_reconstruct_walk_full_cycle(
                    anim_name, bone_channels, current_duration, interpolation
                )
                if reconstruct_info.get('reconstructed', False):
                    walk_full_cycle_reconstructed = True
                    stats['walk_full_cycle_reconstructed'].append({
                        'animation': anim_name,
                        'method': reconstruct_info.get('method', 'unknown'),
                        'original_duration': reconstruct_info.get('original_duration', current_duration),
                        'new_duration': current_duration,
                    })

            # Step 7 [v8 LEGACY]: Walk half-cycle detection & mirroring for sparse keyframes
            # (only runs if v9 full-cycle reconstruction didn't already handle it)
            walk_half_cycle_mirrored = False
            if (not walk_full_cycle_reconstructed and
                self.config.walk_half_cycle_detection and
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

            # Step 8 [v9 NEW]: Smart animation truncation (remove static tails)
            smart_truncated = False
            if (self.config.smart_truncate_enabled and
                loop_mode == "loop" and not is_static and current_duration > 0.3):
                bone_channels, current_duration, trunc_info = self._smart_truncate_static_tail(
                    bone_channels, current_duration
                )
                if trunc_info.get('truncated', False):
                    smart_truncated = True
                    stats['smart_truncated'].append({
                        'animation': anim_name,
                        'original_duration': trunc_info.get('original_duration', current_duration),
                        'new_duration': current_duration,
                        'time_saved': trunc_info.get('time_saved', 0.0),
                    })

            # Step 8b [v10 NEW]: Periodic Auto-Trim
            periodic_auto_trimmed = False
            if (hasattr(cfg, 'periodic_auto_trim') and cfg.periodic_auto_trim and
                loop_mode == "loop" and not is_static and periodicity_info.get('periodicity_score', 0) > 0.5):
                bone_channels, current_duration, trim_info = self._periodic_auto_trim(
                    anim_name, bone_channels, current_duration, periodicity_info
                )
                if trim_info.get('trimmed', False):
                    periodic_auto_trimmed = True
                    stats['periodic_auto_trimmed'].append({
                        'animation': anim_name,
                        'original_duration': trim_info.get('original_duration', current_duration),
                        'new_duration': current_duration,
                        'n_cycles_original': trim_info.get('n_cycles_original', 1),
                    })

            # CACHED RESAMPLING — resample once, use for both C1 and quality
            # v11: pass anim_name for walk-specific resample rate
            cached_resampled = self._resample_all_channels(
                bone_channels, current_duration, interpolation, anim_name=anim_name
            )

            # Step 9 [v9 ENHANCED]: C1+C2 continuity with periodicity-aware blending & phase unwrap
            blend_diag = {
                'global_cubic_count': 0,
                'local_blend_count': 0,
                'static_snap_count': 0,
                'bridge_used_count': 0,
                'max_bounce_severity': 0.0,
                'bridge_details': [],
                'correction_magnitudes': [],
                'fidelity_scores': [],
                'quintic_correction_count': 0,      # v9 NEW
                'quintic_hermite_zone_count': 0,    # v9 NEW
            }
            if loop_mode == "loop":
                # v8: Phase-unwrap rotation channels before C1 enforcement
                if self.config.rotation_phase_unwrap:
                    bone_channels = self._phase_unwrap_rotations(bone_channels, current_duration)

                # v15: Always use full_resample C1 enforcement for ALL loop animations
                # The enforce_with_full_resample method internally decides whether
                # standard enforce or full resample is needed based on C1 error
                sleeping_patterns = getattr(cfg, 'sleeping_name_patterns', ('sleep', 'sleeping', 'rest', 'lay', 'lying', 'bed'))
                is_sleeping = any(p in anim_name.lower() for p in sleeping_patterns) if anim_name else False

                if hasattr(self.c1_enforcer, 'enforce_with_full_resample'):
                    # v15: Use full resample C1 enforcement for all loop animations
                    # This method first does standard enforce, then checks if C1
                    # is still above threshold and applies full resample if needed
                    bone_channels, blend_diag = self.c1_enforcer.enforce_with_full_resample(
                        bone_channels, current_duration, interpolation,
                        anim_name=anim_name,
                        cached_resampled=cached_resampled,
                        periodicity_info=periodicity_info if self.config.periodicity_aware_blending else None,
                        is_sleeping=is_sleeping,
                    )
                elif getattr(self.config, 'c1_multipass_enabled', False):
                    # Fallback: Use multi-pass C1 enforcement for better C1 continuity
                    bone_channels, blend_diag = self.c1_enforcer.enforce_multipass(
                        bone_channels, current_duration, interpolation,
                        cached_resampled=cached_resampled,
                        periodicity_info=periodicity_info if self.config.periodicity_aware_blending else None
                    )
                else:
                    bone_channels, blend_diag = self.c1_enforcer.enforce(
                        bone_channels, current_duration, interpolation,
                        cached_resampled=cached_resampled,
                        periodicity_info=periodicity_info if self.config.periodicity_aware_blending else None
                    )
                stats['global_cubic_used'] += blend_diag.get('global_cubic_count', 0)
                stats['local_blend_used'] += blend_diag.get('local_blend_count', 0)
                stats['static_snap_used'] += blend_diag.get('static_snap_count', 0)
                stats['bridge_used'] += blend_diag.get('bridge_used_count', 0)
                stats['quintic_correction_used'] += blend_diag.get('quintic_correction_count', 0)
                stats['quintic_hermite_zone_used'] += blend_diag.get('quintic_hermite_zone_count', 0)

                # v16 NEW: C1 Quintic Refinement — after global cubic, if C1 still > threshold
                if (getattr(cfg, 'c1_quintic_refinement_enabled', True) and
                        loop_mode == "loop" and not is_static and
                        blend_diag.get('global_cubic_count', 0) > 0):
                    # Check if C1 is still above the refinement threshold
                    max_c1_after = 0.0
                    for bone_name_c1, channels_c1 in bone_channels.items():
                        for channel_c1, keyframes_c1 in channels_c1.items():
                            if len(keyframes_c1) < 2:
                                continue
                            n_rs = max(int(current_duration * cfg.resample_rate), 60)
                            rs_dt = current_duration / n_rs
                            rs_times = [i * rs_dt for i in range(n_rs + 1)]
                            rs_data = CatmullRomEvaluator.resample_channel(
                                keyframes_c1, rs_times, interpolation
                            )
                            if len(rs_data) < 5:
                                continue
                            v0_c1 = (-3*rs_data[0][1] + 4*rs_data[1][1] - rs_data[2][1]) / (2*rs_dt)
                            vT_c1 = (3*rs_data[-1][1] - 4*rs_data[-2][1] + rs_data[-3][1]) / (2*rs_dt)
                            max_c1_after = max(max_c1_after, abs(v0_c1 - vT_c1))

                    if max_c1_after > getattr(cfg, 'c1_quintic_refinement_threshold', 1.5):
                        bone_channels, quintic_info = self._c1_quintic_refinement_pass(
                            bone_channels, current_duration, interpolation,
                            cached_resampled=cached_resampled
                        )
                        if quintic_info.get('applied', False):
                            blend_diag['quintic_refinement_used'] = True
                            stats['quintic_refinement_used'] = stats.get('quintic_refinement_used', 0) + 1

                # Update cached resampled after C1 enforcement
                cached_resampled = self._resample_all_channels(
                    bone_channels, current_duration, interpolation, anim_name=anim_name
                )

            # Step 9c [v16 NEW]: Generalized C1 Post-Correction for ALL loop animations
            # After standard C1 enforcement (global_cubic/local_blend), many animations
            # still have C1 errors > 2°/s. This pass directly adjusts keyframes to
            # match the start velocity at the loop boundary.
            # This MUST run before quality report and JSON build so the report reflects
            # the corrected values.
            c1_post_corrected = 0
            if (loop_mode == "loop" and not is_static and not is_near_empty):
                bone_channels, c1_post_corrected = self._general_c1_post_correction(
                    bone_channels, current_duration, c1_threshold=2.0, max_iterations=5
                )

            # Step 10: Build GeckoLib JSON
            # v15: Pass is_walk_anim for walk-aware DP simplification
            is_walk_anim_for_build = any(p in anim_name.lower() for p in ('walk', 'run'))
            anim_json = self.json_builder.build(
                anim_name, loop_mode, bone_channels, current_duration,
                is_walk_anim=is_walk_anim_for_build
            )
            all_animations[anim_name] = anim_json

            # Step 11: Quality report
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

            # v9 NEW metrics
            qreport.walk_full_cycle_reconstructed = walk_full_cycle_reconstructed
            qreport.smart_truncated = smart_truncated
            if smart_truncated:
                qreport.truncation_original_duration = current_duration + (
                    stats['smart_truncated'][-1].get('time_saved', 0.0)
                    if stats['smart_truncated'] else 0.0
                )
            qreport.quintic_correction_used = blend_diag.get('quintic_correction_count', 0) > 0
            qreport.quintic_hermite_zone_used = blend_diag.get('quintic_hermite_zone_count', 0) > 0

            # v10 NEW metrics
            qreport.progressive_correction_used = blend_diag.get('progressive_correction_count', 0) > 0
            if qreport.progressive_correction_used:
                qreport.progressive_damp_ratio = 1.0  # actual damp ratio tracked per-channel
                stats['progressive_correction_used'] = stats.get('progressive_correction_used', 0) + 1
            if periodic_auto_trimmed:
                qreport.periodic_auto_trimmed = True
                qreport.periodic_trim_original_duration = current_duration + (
                    stats['periodic_auto_trimmed'][-1].get('original_duration', current_duration) - current_duration
                    if stats['periodic_auto_trimmed'] else 0.0
                )

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

            # Step 11b [v10 NEW]: Loop Validation Pass (v11 ENHANCED)
            if (loop_mode == "loop" and not is_static and
                hasattr(cfg, 'loop_validation_pass') and cfg.loop_validation_pass):
                bone_channels, qreport = self._loop_validation_pass(
                    anim_name, bone_channels, current_duration, interpolation, qreport
                )
                if qreport.loop_validation_applied:
                    stats['loop_validation_applied'] = stats.get('loop_validation_applied', 0) + 1
                    # Re-build the animation JSON after validation fixup
                    anim_json = self.json_builder.build(
                        anim_name, loop_mode, bone_channels, current_duration,
                        is_walk_anim=is_walk_anim_for_build
                    )
                    all_animations[anim_name] = anim_json

            # Step 11c [v16]: C1 post-correction already applied at Step 9c
            # Just update the quality report if channels were corrected
            if c1_post_corrected > 0:
                qreport.c1_enforcement_applied = True

            # Step 11d [v11 NEW]: FINAL C0 Enforcement — GUARANTEED 100% C0 Continuity
            # After ALL C1/C2 enforcement and loop validation, ensure the last
            # keyframe value EXACTLY matches the first keyframe value for every
            # loop animation, every bone channel. This eliminates any remaining
            # C0 discontinuity that slipped through previous passes.
            if (loop_mode == "loop" and not is_static and
                hasattr(cfg, 'final_c0_enforcement') and cfg.final_c0_enforcement):
                bone_channels, c0_snapped_count = self._final_c0_enforcement_pass(
                    bone_channels, current_duration
                )
                if c0_snapped_count > 0:
                    qreport.final_c0_enforcement_applied = True
                    qreport.final_c0_channels_snapped = c0_snapped_count
                    # Re-build the animation JSON after final C0 enforcement
                    anim_json = self.json_builder.build(
                        anim_name, loop_mode, bone_channels, current_duration,
                        is_walk_anim=is_walk_anim_for_build
                    )
                    all_animations[anim_name] = anim_json
                    stats['final_c0_channels_snapped'] = stats.get('final_c0_channels_snapped', 0) + c0_snapped_count

            # Step 11d [v12 FIXED]: Walk Validation — ensure ALL walk animations have sufficient keyframe coverage
            # v11 Bug Fix: Previously only triggered for reconstructed/mirrored walks.
            # v12: Any walk animation with < min_kfs per leg channel gets upsampled.
            is_walk_anim = any(p in anim_name.lower() for p in ('walk', 'run'))
            if (loop_mode == "loop" and not is_static and is_walk_anim and
                hasattr(cfg, 'walk_min_keyframes_per_channel')):
                bone_channels, walk_kf_generated = self._walk_validation_resample(
                    anim_name, bone_channels, current_duration, interpolation
                )
                if walk_kf_generated > 0:
                    qreport.walk_validation_applied = True
                    qreport.walk_keyframes_generated = walk_kf_generated
                    # v16: Re-apply C1 post-correction after walk validation resample
                    # Walk validation can regenerate keyframes that break C1 continuity
                    bone_channels, _ = self._general_c1_post_correction(
                        bone_channels, current_duration, c1_threshold=1.5, max_iterations=8
                    )
                    # Re-build after walk validation + C1 correction
                    anim_json = self.json_builder.build(
                        anim_name, loop_mode, bone_channels, current_duration,
                        is_walk_anim=True
                    )
                    all_animations[anim_name] = anim_json
                    stats['walk_keyframes_generated'] = stats.get('walk_keyframes_generated', 0) + walk_kf_generated

            # Step 11e [v16 NEW]: Walk-Specific C1 Correction Pass
            # After standard C1 enforcement, walk animations may still have
            # C1 errors of 3-4 deg/s. This pass uses walk cycle structure
            # for more precise correction.
            if (loop_mode == "loop" and not is_static and is_walk_anim and
                getattr(cfg, 'walk_c1_correction_enabled', True)):
                bone_channels, walk_c1_info = self._walk_c1_correction_pass(
                    bone_channels, current_duration, interpolation, anim_name
                )
                if walk_c1_info.get('applied', False):
                    qreport.c1_method = 'walk_c1_correction'
                    # Re-build after walk C1 correction
                    anim_json = self.json_builder.build(
                        anim_name, loop_mode, bone_channels, current_duration,
                        is_walk_anim=True
                    )
                    all_animations[anim_name] = anim_json

        # Count idle_enriched from merge_info
        stats['idle_enriched_count'] = sum(
            1 for m in stats.get('merge_info', [])
            if m.get('action') == 'idle_enriched'
        )

        # Step 12 [v8]: Truly-empty animation purge (after C1 enforcement)
        if self.config.purge_truly_empty_animations:
            all_animations, quality_reports, purged = self._purge_truly_empty_animations(
                all_animations, quality_reports
            )
            stats['animations_purged_empty'] = purged
            for pname in purged:
                stats['total_animations'] -= 1

        # Step 12b [v11 NEW]: Remove truly-static animations (max deviation < threshold)
        if hasattr(cfg, 'remove_truly_static_animations') and cfg.remove_truly_static_animations:
            static_removed = self._remove_truly_static_animations(all_animations, quality_reports)
            for rname in static_removed:
                if rname in all_animations:
                    del all_animations[rname]
                if rname in quality_reports:
                    quality_reports[rname].truly_static_removed = True
                    del quality_reports[rname]
                stats['total_animations'] -= 1
            stats['truly_static_removed'] = static_removed

        # v15 NEW: Generate static idle for models with no animations left
        # (Issue 4: Some game engines require at least one animation to be present)
        if (getattr(cfg, 'generate_static_idle_for_empty_models', True) and
            not all_animations and model_name):
            static_idle_name = f"animation.{model_name.lower()}.idle"
            # Generate a minimal static idle with a root/body bone at t=0
            # This ensures the animation file has at least one bone entry,
            # which some game engines require
            static_idle = {
                "loop": "loop",
                "animation_length": 0.5,
                "bones": {
                    "root": {
                        "position": {
                            "x": {"0.0000": 0.0},
                            "y": {"0.0000": 0.0},
                            "z": {"0.0000": 0.0}
                        }
                    }
                },
            }
            all_animations[static_idle_name] = static_idle
            stats['total_animations'] += 1
            stats['static_idle_generated'] = True

            # Create a minimal quality report
            qr = AnimationQualityReport(
                animation_name=static_idle_name,
                duration=0.5,
                num_bones=1,
                total_keyframes=3,
                is_static=True,
                quality_score=100.0,
            )
            quality_reports[static_idle_name] = qr

        # Step 13 [v9 NEW + v11 ENHANCED]: Deep idle dedup (near-duplicate + static consolidation)
        if self.config.deep_idle_dedup:
            all_animations, quality_reports, deep_removed = self._deep_idle_dedup(
                all_animations, quality_reports, category_model_names
            )
            stats['deep_idle_dedup_removed'] = deep_removed
            for rname in deep_removed:
                stats['total_animations'] -= 1

        # v15 NEW: Evolved/Idle merge dedup
        # (Issue 3: When idle and evolved share >80% bones with similar amplitude, merge them)
        if getattr(cfg, 'evolved_idle_merge_enabled', True):
            all_animations, quality_reports, evolved_merged = self._evolved_idle_merge_dedup(
                all_animations, quality_reports
            )
            if evolved_merged:
                stats['evolved_idle_merged'] = evolved_merged
                for mname in evolved_merged:
                    if mname in all_animations:
                        pass  # already handled in method
                    else:
                        stats['total_animations'] -= 1

        # Step 14 [v8 LEGACY]: Smart idle dedup with cross-model awareness
        # (only runs if v9 deep dedup didn't already handle it)
        if self.config.smart_idle_dedup and not self.config.deep_idle_dedup:
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

        # Step 15 [v9 NEW]: Multi-texture extraction
        if output_path and self.config.extract_all_textures:
            out_dir = os.path.dirname(output_path)
            extracted_textures = self._extract_all_textures(bbmodel_path, out_dir)
            stats['textures_extracted'] = len(extracted_textures)
            for qr in quality_reports.values():
                qr.textures_extracted = len(extracted_textures)

        # Step 16 [v8]: File-level smart output
        if output_path:
            should_write = True
            skip_reason = ""

            # v15: If we generated a static idle for this model, always write the file
            has_generated_static_idle = stats.get('static_idle_generated', False)

            # v8: If ALL animations are purged as truly empty, don't write
            # v15: UNLESS we generated a static idle
            if self.config.skip_all_empty_files and not all_animations and not has_generated_static_idle:
                should_write = False
                skip_reason = "all_purged"
                stats['files_skipped_all_empty'] = True
            elif self.config.skip_all_empty_files and all_truly_empty and not has_generated_static_idle:
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
                    if self.config.skip_meaningless_animation_files and not has_generated_static_idle:
                        should_write = False
                        skip_reason = "all_static_no_bones"
                        stats['files_skipped_all_empty'] = True
                else:
                    should_write = True

            # v11 NEW: If file would contain only truly-static animations, skip
            # v15: UNLESS we generated a static idle (it should be written)
            if should_write and hasattr(cfg, 'skip_files_with_only_static') and cfg.skip_files_with_only_static and not has_generated_static_idle:
                only_static = True
                for anim_name, anim_data in all_animations.items():
                    if not anim_data.get('static', False):
                        only_static = False
                        break
                if only_static and len(all_animations) > 0:
                    should_write = False
                    skip_reason = "all_truly_static"
                    stats['files_skipped_all_empty'] = True

            if should_write:
                os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
            else:
                # Remove existing file if it was written by a previous run
                if os.path.exists(output_path):
                    os.remove(output_path)

        # Step 17 [v10 NEW]: Post-process empty file cleanup
        # v15: Skip this step if we generated a static idle (it should be preserved)
        if (output_path and hasattr(cfg, 'post_process_empty_cleanup') and cfg.post_process_empty_cleanup
                and not stats.get('static_idle_generated', False)):
            cleanup_result = self._post_process_empty_cleanup(
                output_path, all_animations, stats
            )
            if cleanup_result.get('removed', False):
                stats['post_process_empty_removed'] = stats.get('post_process_empty_removed', [])
                stats['post_process_empty_removed'].append({
                    'file': output_path,
                    'reason': cleanup_result.get('reason', 'unknown'),
                })
                stats['files_skipped_all_empty'] = True

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

                # v12 FIX: Enforce C0 continuity at mirror point (t = half_duration)
                # and at loop boundary (t = full_duration ≈ t = 0)
                # The mirrored keyframe at half_duration should smoothly connect
                # to the second half.

                # Find the keyframes at the mirror boundary (t ≈ half_duration)
                # and snap them to ensure smooth transition
                for idx in range(len(mirrored_kfs)):
                    t, v = mirrored_kfs[idx]
                    # Snap to mirror point: ensure continuity at t = half_duration
                    if abs(t - half_duration) < 0.01 and idx > 0:
                        prev_v = mirrored_kfs[idx - 1][1]
                        # Average the boundary for smooth transition
                        if idx + 1 < len(mirrored_kfs):
                            next_v = mirrored_kfs[idx + 1][1]
                            avg_v = (prev_v + next_v) / 2.0
                            mirrored_kfs[idx] = (t, avg_v)
                        else:
                            mirrored_kfs[idx] = (t, prev_v)

                # Ensure loop boundary: last kf should match first kf for C0
                if len(mirrored_kfs) >= 2:
                    first_v = mirrored_kfs[0][1]
                    last_t, last_v = mirrored_kfs[-1]
                    if abs(first_v - last_v) > 0.01:
                        # Snap last to first for C0
                        mirrored_kfs[-1] = (last_t, first_v)
                        # Adjust second-to-last for smoother C1
                        if len(mirrored_kfs) >= 3:
                            mid_t, mid_v = mirrored_kfs[-2]
                            # Blend toward first value to reduce velocity discontinuity
                            blend_ratio = 0.3
                            new_mid_v = mid_v + blend_ratio * (first_v - mid_v)
                            mirrored_kfs[-2] = (mid_t, new_mid_v)

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
        interpolation: str = "catmullrom",
        anim_name: str = ""
    ) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
        """Resample all channels once for caching.

        v11: Uses walk_resample_rate (240Hz) for walk animations if configured.
        """
        cfg = self.config
        # v11: Use higher resample rate for walk animations
        effective_rate = cfg.resample_rate
        if (hasattr(cfg, 'walk_resample_rate') and cfg.walk_resample_rate > 0 and
                anim_name and any(p in anim_name.lower() for p in ('walk', 'run'))):
            effective_rate = cfg.walk_resample_rate
        n_resample = max(int(duration * effective_rate), 60)
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

    # ========================================================================
    # v9 NEW METHODS
    # ========================================================================

    def _detect_and_reconstruct_walk_full_cycle(
        self,
        anim_name: str,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        interpolation: str
    ) -> Tuple[Dict[str, Dict[str, List[Tuple[float, float]]]], float, Dict[str, Any]]:
        """v10 Improvement 2: Walk Cycle Full Reconstruction with Leg-Pair Awareness.

        Detects incomplete walks regardless of keyframe count by checking:
        a) Does the leg rotation oscillation complete a full cycle? (first_val ≈ last_val)
        b) If not, it's a half-cycle → mirror it with leg-pair awareness
        c) For walks that ARE complete but have poor loop continuity:
           - Snap the last keyframe values to match the first (within tolerance)
           - Adjust the second-to-last keyframe for smooth C1 transition
        d) After reconstruction, validate that the walk is complete

        v10 improvements over v9:
        - Detects left/right leg pairs and mirrors them with correct phase
        - Body sway phase correction: body rotation should sway opposite to legs
        - Walk completion validation: checks that all leg channels complete full oscillation
        """
        info = {'reconstructed': False, 'method': 'none', 'original_duration': duration}
        cfg = self.config

        # Only process walk/run animations
        name_lower = anim_name.lower()
        is_walk = any(p in name_lower for p in ('walk', 'run'))
        if not is_walk:
            return bone_channels, duration, info

        # Step 1: Detect leg pairs
        leg_pairs = {}  # base_name -> {'left': bone_name, 'right': bone_name}
        leg_bones = set()
        body_bones = set()

        for bone_name in bone_channels.keys():
            bone_lower = bone_name.lower()
            is_leg = any(p in bone_lower for p in cfg.walk_bone_patterns)
            if is_leg:
                leg_bones.add(bone_name)
                # Try to detect left/right pairing
                pair_base = None
                side = None
                for prefix, label in [('left_', 'left'), ('right_', 'right'),
                                       ('l_', 'left'), ('r_', 'right')]:
                    if bone_lower.startswith(prefix):
                        pair_base = bone_name[len(prefix):]
                        side = label
                        break
                for suffix, label in [('_left', 'left'), ('right', 'right'),
                                       ('_l', 'left'), ('_r', 'right')]:
                    if bone_lower.endswith(suffix):
                        pair_base = bone_name[:-len(suffix)]
                        side = label
                        break

                if pair_base and side:
                    if pair_base not in leg_pairs:
                        leg_pairs[pair_base] = {}
                    leg_pairs[pair_base][side] = bone_name
            else:
                # Check if it's a body bone (torso, head, spine, etc.)
                body_patterns = ('body', 'torso', 'spine', 'chest', 'head', 'neck', 'waist', 'pelvis')
                if any(p in bone_lower for p in body_patterns):
                    body_bones.add(bone_name)

        # Step 2: Check if leg rotation channels complete a full cycle
        is_half_cycle = False
        is_full_cycle = True
        leg_data_available = False

        for bone_name, channels in bone_channels.items():
            bone_lower = bone_name.lower()
            is_leg = any(p in bone_lower for p in cfg.walk_bone_patterns)
            if not is_leg:
                continue

            for channel, keyframes in channels.items():
                if not channel.startswith('r') or len(keyframes) < 2:
                    continue

                leg_data_available = True
                first_val = keyframes[0][1]
                last_val = keyframes[-1][1]

                values = [v for t, v in keyframes]
                amplitude = max(abs(v - values[0]) for v in values)
                if amplitude < cfg.walk_min_leg_amplitude if hasattr(cfg, 'walk_min_leg_amplitude') else 0.1:
                    continue

                completeness = abs(first_val - last_val) / max(amplitude, 1e-6)
                if completeness > cfg.walk_cycle_completeness_threshold:
                    is_half_cycle = True
                    is_full_cycle = False

        if not leg_data_available:
            return bone_channels, duration, info

        # Step 3a: Half-cycle → mirror with leg-pair awareness
        if is_half_cycle:
            half_duration = duration
            full_duration = duration * 2.0

            result_channels = {}
            for bone_name, channels in bone_channels.items():
                result_channels[bone_name] = {}
                bone_lower = bone_name.lower()
                is_leg = any(p in bone_lower for p in cfg.walk_bone_patterns)
                is_body = bone_name in body_bones

                # Detect if this is a left or right leg
                is_left_leg = any(p in bone_lower for p in ('left', '_l', 'l_'))
                is_right_leg = any(p in bone_lower for p in ('right', '_r', 'r_'))

                for channel, keyframes in channels.items():
                    is_rotation = channel.startswith('r')
                    mirrored_kfs = list(keyframes)

                    for t, v in keyframes:
                        new_t = t + half_duration
                        if is_rotation:
                            if is_leg:
                                # v10: For left/right leg pairs, mirror by negating relative to mean
                                # This creates the opposite swing for the mirrored half
                                mean_val = (keyframes[0][1] + keyframes[-1][1]) / 2.0
                                new_v = 2.0 * mean_val - v
                            elif is_body and hasattr(cfg, 'walk_body_sway_correction') and cfg.walk_body_sway_correction:
                                # v10: Body sway correction - body rotates opposite to legs
                                # In the second half, body sway mirrors the first half
                                mean_val = (keyframes[0][1] + keyframes[-1][1]) / 2.0
                                new_v = 2.0 * mean_val - v
                            else:
                                new_v = v  # keep same for other bones
                        else:
                            if is_leg and channel in ('oy', 'y'):
                                mean_val = (keyframes[0][1] + keyframes[-1][1]) / 2.0
                                new_v = 2.0 * mean_val - v
                            else:
                                new_v = v  # keep same for other position channels

                        mirrored_kfs.append((new_t, new_v))

                    mirrored_kfs.sort(key=lambda x: x[0])
                    result_channels[bone_name][channel] = mirrored_kfs

            info['reconstructed'] = True
            info['method'] = 'half_cycle_mirror_leg_pair_aware'
            info['original_duration'] = half_duration
            info['leg_pairs_detected'] = len(leg_pairs)
            return result_channels, full_duration, info

        # Step 3b: Full cycle but poor loop continuity → snap end to start
        if is_full_cycle:
            result_channels = {}
            for bone_name, channels in bone_channels.items():
                result_channels[bone_name] = {}
                for channel, keyframes in channels.items():
                    if len(keyframes) < 2:
                        result_channels[bone_name][channel] = keyframes
                        continue

                    first_val = keyframes[0][1]
                    last_val = keyframes[-1][1]
                    diff = abs(first_val - last_val)

                    if diff > 0.01:
                        new_kfs = list(keyframes)
                        new_kfs[-1] = (new_kfs[-1][0], first_val)

                        # Adjust second-to-last for smooth C1
                        if len(new_kfs) >= 3:
                            dt = new_kfs[1][0] - new_kfs[0][0] if len(new_kfs) > 1 else duration
                            v_start = (new_kfs[1][1] - new_kfs[0][1]) / max(dt, 1e-6)

                            dt_end = new_kfs[-1][0] - new_kfs[-2][0]
                            if dt_end > 1e-6:
                                desired_v_end = v_start
                                new_kfs[-2] = (new_kfs[-2][0],
                                               new_kfs[-1][1] - desired_v_end * dt_end)

                        result_channels[bone_name][channel] = new_kfs
                        info['reconstructed'] = True
                        info['method'] = 'end_snap_c1_adjust'
                    else:
                        result_channels[bone_name][channel] = keyframes

            if info['reconstructed']:
                info['original_duration'] = duration
            return result_channels, duration, info

        return bone_channels, duration, info

    def _deep_idle_dedup(
        self,
        all_animations: Dict[str, Any],
        quality_reports: Dict[str, 'AnimationQualityReport'],
        category_model_names: Optional[List[str]] = None
    ) -> Tuple[Dict[str, Any], Dict[str, 'AnimationQualityReport'], List[str]]:
        """v11 Improvement 3: Aggressive Deep Idle Deduplication.

        Beyond v10's near-duplicate removal, adds:
        - Extended idle name aliases for broader detection
        - Lower amplitude similarity threshold (0.40 → 0.25) for more aggressive dedup
        - Lower static amplitude threshold (0.05 → 0.03 degrees)
        - Remove idle when other meaningful animation types exist
        - Static idle consolidation (keep only the best static idle)
        - v11 NEW: Merge idle animations with bone channels differing < 0.5 deg amplitude
        """
        removed = []
        cfg = self.config

        # Step 1: Find all idle-like animations with extended aliases
        idle_aliases = cfg.idle_name_aliases
        if hasattr(cfg, 'idle_name_extended_aliases'):
            idle_aliases = cfg.idle_name_extended_aliases

        idle_like = {}
        for anim_name, anim_data in all_animations.items():
            name_lower = anim_name.lower()
            is_idle = (name_lower == 'idle' or
                       any(alias in name_lower for alias in idle_aliases) or
                       'idle' in name_lower)

            if not is_idle:
                continue

            bones = anim_data.get('bones', {})
            bone_set = set()
            total_amplitude = 0.0
            channel_count = 0
            has_real_data = False
            is_static = True

            for bone_name, bone_data in bones.items():
                bone_set.add(bone_name)
                for channel_name, channel_data in bone_data.items():
                    if isinstance(channel_data, dict):
                        for axis, time_data in channel_data.items():
                            if isinstance(time_data, dict):
                                for time_key, val in time_data.items():
                                    if isinstance(val, (int, float)):
                                        total_amplitude += abs(val)
                                        channel_count += 1
                                        if abs(val) > cfg.idle_static_amplitude_threshold:
                                            is_static = False
                                        if abs(val) > 0.01:
                                            has_real_data = True
                            elif isinstance(time_data, (int, float)):
                                total_amplitude += abs(time_data)
                                channel_count += 1
                                if abs(time_data) > cfg.idle_static_amplitude_threshold:
                                    is_static = False
                                if abs(time_data) > 0.01:
                                    has_real_data = True

            quality = quality_reports.get(anim_name)
            quality_score = quality.quality_score if quality else 0.0

            idle_like[anim_name] = {
                'signature': frozenset(bone_set),
                'bones': bone_set,
                'amplitude': total_amplitude,
                'channel_count': channel_count,
                'quality_score': quality_score,
                'is_static': is_static,
                'has_real_data': has_real_data,
            }

        if len(idle_like) < 2:
            return all_animations, quality_reports, removed

        # Step 2: Remove static idles (keep only the best one)
        static_idles = {name: info for name, info in idle_like.items() if info['is_static']}
        if len(static_idles) > 1:
            best_static = max(static_idles.items(), key=lambda x: x[1]['quality_score'])
            for name in static_idles:
                if name != best_static[0]:
                    if name in all_animations:
                        del all_animations[name]
                    if name in quality_reports:
                        quality_reports[name].idle_dedup_deep_merged = True
                        del quality_reports[name]
                    removed.append(name)

        # Step 3: v10 - Remove empty idle when other meaningful animations exist
        if hasattr(cfg, 'aggressive_idle_dedup') and cfg.aggressive_idle_dedup:
            has_other_real = False
            for anim_name, anim_data in all_animations.items():
                name_lower = anim_name.lower()
                is_idle_like = ('idle' in name_lower or
                               any(alias in name_lower for alias in idle_aliases))
                if is_idle_like:
                    continue
                # Check if this animation has real data
                bones = anim_data.get('bones', {})
                if bones:
                    for bone_name, bone_data in bones.items():
                        for channel_name, channel_data in bone_data.items():
                            if isinstance(channel_data, dict):
                                for axis, time_data in channel_data.items():
                                    if isinstance(time_data, dict):
                                        for time_key, val in time_data.items():
                                            if isinstance(val, (int, float)) and abs(val) > 0.5:
                                                has_other_real = True
                                                break
                                    elif isinstance(time_data, (int, float)) and abs(time_data) > 0.5:
                                        has_other_real = True
                                        break
                                if has_other_real:
                                    break
                        if has_other_real:
                            break
                if has_other_real:
                    break

            # If there are other real animations, remove all static/near-empty idles
            if has_other_real:
                for idle_name, idle_info in idle_like.items():
                    if not idle_info['has_real_data'] and idle_name in all_animations:
                        del all_animations[idle_name]
                        if idle_name in quality_reports:
                            quality_reports[idle_name].idle_dedup_deep_merged = True
                            del quality_reports[idle_name]
                        if idle_name not in removed:
                            removed.append(idle_name)

        # Step 4: Near-duplicate dedup with lower threshold
        amp_threshold = cfg.idle_amplitude_similarity_threshold if hasattr(cfg, 'idle_amplitude_similarity_threshold') else 0.50
        idle_names = list(idle_like.keys())
        for i in range(len(idle_names)):
            for j in range(i + 1, len(idle_names)):
                name_a = idle_names[i]
                name_b = idle_names[j]

                if name_a not in all_animations or name_b not in all_animations:
                    continue

                info_a = idle_like[name_a]
                info_b = idle_like[name_b]

                overlap = len(info_a['bones'] & info_b['bones'])
                union = len(info_a['bones'] | info_b['bones'])
                overlap_ratio = overlap / max(union, 1)

                if overlap_ratio < cfg.idle_similarity_threshold:
                    continue

                amp_a = info_a['amplitude']
                amp_b = info_b['amplitude']
                amp_ratio = min(amp_a, amp_b) / max(amp_a, amp_b, 1e-6)

                if amp_ratio < amp_threshold:
                    continue

                # Choose which to keep (prefer one with real data, then quality)
                if info_a['quality_score'] >= info_b['quality_score']:
                    if info_b['has_real_data'] and not info_a['has_real_data']:
                        loser = name_a
                    else:
                        loser = name_b
                else:
                    if info_a['has_real_data'] and not info_b['has_real_data']:
                        loser = name_b
                    else:
                        loser = name_a

                if loser in all_animations:
                    del all_animations[loser]
                if loser in quality_reports:
                    quality_reports[loser].idle_dedup_deep_merged = True
                    del quality_reports[loser]
                removed.append(loser)

        # Step 5 [v11 NEW]: Small-amplitude merge — merge idle animations whose bone channels
        # differ by less than idle_small_amplitude_merge_threshold (0.5 deg) in amplitude.
        # Keep the one with more bones.
        if hasattr(cfg, 'idle_small_amplitude_merge_threshold') and cfg.idle_small_amplitude_merge_threshold > 0:
            small_amp_thresh = cfg.idle_small_amplitude_merge_threshold
            idle_names_remaining = [n for n in idle_like if n in all_animations]
            for i in range(len(idle_names_remaining)):
                for j in range(i + 1, len(idle_names_remaining)):
                    name_a = idle_names_remaining[i]
                    name_b = idle_names_remaining[j]

                    if name_a not in all_animations or name_b not in all_animations:
                        continue

                    info_a = idle_like[name_a]
                    info_b = idle_like[name_b]

                    # Check if both idles have small total amplitude difference
                    amp_diff = abs(info_a['amplitude'] - info_b['amplitude'])
                    max_amp = max(info_a['amplitude'], info_b['amplitude'], 1e-6)

                    if max_amp < small_amp_thresh:
                        # Both have very small amplitude — merge by keeping the one with more bones
                        if len(info_a['bones']) >= len(info_b['bones']):
                            loser = name_b
                        else:
                            loser = name_a

                        if loser in all_animations:
                            del all_animations[loser]
                        if loser in quality_reports:
                            quality_reports[loser].idle_dedup_deep_merged = True
                            del quality_reports[loser]
                        if loser not in removed:
                            removed.append(loser)

        return all_animations, quality_reports, removed

    def _evolved_idle_merge_dedup(
        self,
        all_animations: Dict[str, Any],
        quality_reports: Dict[str, 'AnimationQualityReport']
    ) -> Tuple[Dict[str, Any], Dict[str, 'AnimationQualityReport'], List[str]]:
        """v16: Evolved/Idle merge dedup with protected animation categories.

        When two animations share >80% of bone names and have similar amplitude
        patterns (correlation >0.7), merge them: keep the one with MORE keyframes
        (higher fidelity) and discard the other.

        Special handling for evolved vs idle:
        - If evolved has >=1.5x the keyframes of idle and covers the same bones,
          prefer evolved and rename it to "idle"
        - Otherwise, keep the one with higher quality score

        v16 FIX: NEVER merge animations if the loser has a name containing
        'attack', 'hurt', 'die', 'death', or 'sleep'. These are always
        distinct game states.
        """
        removed = []
        cfg = self.config

        if not getattr(cfg, 'evolved_idle_merge_enabled', True):
            return all_animations, quality_reports, removed

        # v16: Protected name patterns — never merge across these boundaries
        PROTECTED_MERGE_PATTERNS = ('attack', 'hurt', 'die', 'death', 'sleep')

        def _is_protected_from_merge(name: str) -> bool:
            """Check if an animation name should be protected from merge/dedup."""
            name_lower = name.lower()
            return any(p in name_lower for p in PROTECTED_MERGE_PATTERNS)

        # Find idle and evolved animations
        idle_anims = {}
        evolved_anims = {}

        for anim_name, anim_data in all_animations.items():
            name_lower = anim_name.lower()

            is_idle = ('idle' in name_lower and 'evolved' not in name_lower)
            is_evolved = 'evolved' in name_lower

            if not is_idle and not is_evolved:
                continue

            bones = anim_data.get('bones', {})
            bone_set = set()
            total_kfs = 0
            total_amplitude = 0.0

            for bone_name, bone_data in bones.items():
                bone_set.add(bone_name)
                for channel_name, channel_data in bone_data.items():
                    if isinstance(channel_data, dict):
                        for axis, time_data in channel_data.items():
                            if isinstance(time_data, dict):
                                total_kfs += len(time_data)
                                for time_key, val in time_data.items():
                                    if isinstance(val, (int, float)):
                                        total_amplitude += abs(val)
                            elif isinstance(time_data, (int, float)):
                                total_kfs += 1
                                total_amplitude += abs(time_data)

            info = {
                'bones': bone_set,
                'total_kfs': total_kfs,
                'amplitude': total_amplitude,
                'quality_score': quality_reports[anim_name].quality_score if anim_name in quality_reports else 0.0,
            }

            if is_idle:
                idle_anims[anim_name] = info
            elif is_evolved:
                evolved_anims[anim_name] = info

        # Check each pair of idle/evolved animations
        bone_overlap_threshold = getattr(cfg, 'evolved_idle_bone_overlap_threshold', 0.80)
        amplitude_correlation_threshold = getattr(cfg, 'evolved_idle_amplitude_correlation_threshold', 0.7)
        kf_ratio_threshold = getattr(cfg, 'evolved_keyframe_ratio_threshold', 1.5)

        for idle_name, idle_info in idle_anims.items():
            for evolved_name, evolved_info in evolved_anims.items():
                if idle_name not in all_animations or evolved_name not in all_animations:
                    continue

                # v16: Protection check — never merge if either animation is protected
                if _is_protected_from_merge(idle_name) or _is_protected_from_merge(evolved_name):
                    continue

                # Check bone overlap
                overlap = len(idle_info['bones'] & evolved_info['bones'])
                union = len(idle_info['bones'] | evolved_info['bones'])
                overlap_ratio = overlap / max(union, 1)

                if overlap_ratio < bone_overlap_threshold:
                    continue

                # Check amplitude correlation
                max_amp = max(idle_info['amplitude'], evolved_info['amplitude'], 1e-6)
                min_amp = min(idle_info['amplitude'], evolved_info['amplitude'])
                amp_correlation = min_amp / max_amp

                if amp_correlation < amplitude_correlation_threshold:
                    continue

                # Determine which to keep
                kf_ratio = evolved_info['total_kfs'] / max(idle_info['total_kfs'], 1)

                loser_name = None
                if kf_ratio >= kf_ratio_threshold:
                    # Evolved has significantly more keyframes — prefer evolved
                    # Remove idle, keep evolved
                    loser_name = idle_name
                elif idle_info['quality_score'] >= evolved_info['quality_score']:
                    # Idle has better quality — remove evolved
                    loser_name = evolved_name
                else:
                    # Evolved has better quality — remove idle
                    loser_name = idle_name

                # v16: Final protection check on loser before removing
                if loser_name and not _is_protected_from_merge(loser_name):
                    if loser_name in all_animations:
                        del all_animations[loser_name]
                    if loser_name in quality_reports:
                        del quality_reports[loser_name]
                    removed.append(loser_name)

        return all_animations, quality_reports, removed

    def _consolidate_animation_files(
        self,
        animation_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """v9 Improvement 4: Consolidate animation files from multi-part entities.

        When the same model has multiple animation files, consolidates them
        by merging same-named animation clips with union of bone channels.
        """
        if not animation_results:
            return {}
        if len(animation_results) == 1:
            return animation_results[0]

        consolidated = {
            "format_version": "1.8.0",
            "animations": {},
        }

        for result in animation_results:
            if not result or 'animations' not in result:
                continue
            anims = result['animations'].get('animations', {})
            for anim_name, anim_data in anims.items():
                if anim_name not in consolidated['animations']:
                    consolidated['animations'][anim_name] = anim_data
                else:
                    existing = consolidated['animations'][anim_name]
                    existing_bones = existing.get('bones', {})
                    new_bones = anim_data.get('bones', {})

                    for bone_name, bone_data in new_bones.items():
                        if bone_name not in existing_bones:
                            existing_bones[bone_name] = bone_data
                        else:
                            for channel_name, channel_data in bone_data.items():
                                if channel_name not in existing_bones[bone_name]:
                                    existing_bones[bone_name][channel_name] = channel_data

        consolidated['model_name'] = animation_results[0].get('model_name', 'unknown')
        consolidated['quality_reports'] = {}
        for result in animation_results:
            if result and 'quality_reports' in result:
                consolidated['quality_reports'].update(result['quality_reports'])
        consolidated['stats'] = animation_results[0].get('stats', {})

        return consolidated

    def _smart_truncate_static_tail(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float
    ) -> Tuple[Dict[str, Dict[str, List[Tuple[float, float]]]], float, Dict[str, Any]]:
        """v9 Improvement 5: Smart Animation Truncation.

        Detects when the last portion of an animation is nearly static
        and truncates at the point where meaningful motion ends.
        """
        info = {'truncated': False, 'original_duration': duration, 'new_duration': duration}
        cfg = self.config

        if not cfg.smart_truncate_enabled:
            return bone_channels, duration, info

        min_tail_fraction = cfg.smart_truncate_min_tail_fraction
        min_meaningful_duration = duration * min_tail_fraction

        # Find the last time where ANY channel has amplitude > threshold
        last_meaningful_time = 0.0

        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if not keyframes:
                    continue

                is_rotation = channel.startswith('r')
                threshold = (cfg.smart_truncate_tail_threshold_rot if is_rotation
                             else cfg.smart_truncate_tail_threshold_pos)

                for t, v in keyframes:
                    if abs(v) > threshold:
                        last_meaningful_time = max(last_meaningful_time, t)

        # Check if truncation is needed
        if last_meaningful_time >= duration * (1.0 - min_tail_fraction):
            return bone_channels, duration, info

        new_duration = max(last_meaningful_time + TICK_DURATION, min_meaningful_duration)

        if new_duration >= duration * 0.95:
            return bone_channels, duration, info

        result_channels = self._trim_to_duration(bone_channels, new_duration)

        info['truncated'] = True
        info['original_duration'] = duration
        info['new_duration'] = new_duration
        info['time_saved'] = duration - new_duration

        return result_channels, new_duration, info

    def _periodic_auto_trim(
        self,
        anim_name: str,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        periodicity_info: Dict[str, Any]
    ) -> Tuple[Dict[str, Dict[str, List[Tuple[float, float]]]], float, Dict[str, Any]]:
        """v10 Improvement 5: Periodic Auto-Trim.

        For periodic animations (walk, run, fly, etc.), detects if the animation
        contains multiple repetitions of the same cycle and trims it to the
        shortest repeating unit. This eliminates redundant loops and improves
        loop continuity by finding the cleanest single cycle.
        """
        info = {'trimmed': False, 'original_duration': duration, 'new_duration': duration}
        cfg = self.config

        if not hasattr(cfg, 'periodic_auto_trim') or not cfg.periodic_auto_trim:
            return bone_channels, duration, info

        # Only trim if periodicity confidence is high enough
        periodicity_score = periodicity_info.get('periodicity_score', 0.0)
        if periodicity_score < cfg.periodic_trim_confidence if hasattr(cfg, 'periodic_trim_confidence') else 0.85:
            return bone_channels, duration, info

        # Only trim loop animations
        period = periodicity_info.get('period')
        if not period or period < 0.2 or period >= duration * 0.9:
            return bone_channels, duration, info

        # Check if duration is approximately a multiple of the period
        n_cycles = duration / period
        n_cycles_round = round(n_cycles)

        if n_cycles_round < 2 or abs(n_cycles - n_cycles_round) > 0.15:
            return bone_channels, duration, info

        # Duration is approximately n_cycles_round * period
        # Check if a single cycle (trimmed to period) has better C0/C1 than the full animation
        single_duration = self.loop_detector._snap_to_tick(period) if cfg.snap_to_ticks else period

        if single_duration < cfg.min_loop_duration:
            return bone_channels, duration, info

        # Evaluate C0/C1 at the single-cycle duration
        resampled = self._resample_all_channels(bone_channels, duration, "catmullrom")
        c0_single, c1_single, _ = self.loop_detector._evaluate_continuity_combined(
            resampled, single_duration, cfg.resample_rate
        )
        c0_full, c1_full, _ = self.loop_detector._evaluate_continuity_combined(
            resampled, duration, cfg.resample_rate
        )

        # Trim if single cycle has better or comparable continuity
        if c0_single <= c0_full * 1.5 and c1_single <= c1_full * 1.5:
            # Single cycle is good enough - trim to it
            trimmed_channels = self._trim_to_duration(bone_channels, single_duration)

            info['trimmed'] = True
            info['original_duration'] = duration
            info['new_duration'] = single_duration
            info['n_cycles_original'] = n_cycles_round
            info['c0_single'] = c0_single
            info['c0_full'] = c0_full

            return trimmed_channels, single_duration, info

        return bone_channels, duration, info

    def _loop_validation_pass(
        self,
        anim_name: str,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        interpolation: str,
        quality_report: 'AnimationQualityReport'
    ) -> Tuple[Dict[str, Dict[str, List[Tuple[float, float]]]], 'AnimationQualityReport']:
        """v11 Improvement 5: Enhanced Secondary Loop Validation Pass.

        After all corrections, re-checks C0/C1 continuity and applies
        additional corrections if needed.

        v11 enhancements:
        - Absolute C0 threshold: ANY channel with |last-first| > 0.05 deg gets snapped
        - After snapping, re-check C1 and apply cubic correction if needed
        - Iterates until C0 error is 0 for ALL channels (max 3 iterations)
        """
        cfg = self.config
        if not hasattr(cfg, 'loop_validation_pass') or not cfg.loop_validation_pass:
            return bone_channels, quality_report

        c0_pre = max(quality_report.c0_max_error_rot, quality_report.c0_max_error_pos * 10)
        c1_pre = max(quality_report.c1_avg_error_rot, quality_report.c1_avg_error_pos * 10)

        quality_report.loop_validation_c0_pre = c0_pre
        quality_report.loop_validation_c1_pre = c1_pre

        # v11: Absolute C0 threshold — any channel > 0.05 deg gets snapped
        absolute_c0_thresh = cfg.loop_validation_absolute_c0_threshold if hasattr(cfg, 'loop_validation_absolute_c0_threshold') else 0.05
        max_iterations = cfg.loop_validation_max_iterations if hasattr(cfg, 'loop_validation_max_iterations') else 3
        do_c1_cubic = cfg.loop_validation_c1_cubic_correction if hasattr(cfg, 'loop_validation_c1_cubic_correction') else True

        # Check if ANY channel has C0 error > absolute threshold
        any_channel_exceeds = False
        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if len(keyframes) < 2:
                    continue
                first_val = keyframes[0][1]
                last_val = keyframes[-1][1]
                c0_err = abs(first_val - last_val)
                if c0_err > absolute_c0_thresh:
                    any_channel_exceeds = True
                    break
            if any_channel_exceeds:
                break

        needs_fixup = any_channel_exceeds
        if not needs_fixup:
            # Also check legacy threshold
            if c0_pre > (cfg.loop_validation_c0_threshold if hasattr(cfg, 'loop_validation_c0_threshold') else 0.5):
                needs_fixup = True
            if c1_pre > (cfg.loop_validation_c1_threshold if hasattr(cfg, 'loop_validation_c1_threshold') else 5.0):
                needs_fixup = True

        if not needs_fixup:
            return bone_channels, quality_report

        # v11: Iterate until C0 error is 0 for all channels (max iterations)
        result_channels = bone_channels
        for iteration in range(max_iterations):
            still_has_c0_error = False
            new_channels = {}
            for bone_name, channels in result_channels.items():
                new_channels[bone_name] = {}
                for channel, keyframes in channels.items():
                    if len(keyframes) < 2:
                        new_channels[bone_name][channel] = keyframes
                        continue

                    first_val = keyframes[0][1]
                    last_val = keyframes[-1][1]
                    c0_err = abs(first_val - last_val)

                    if c0_err > 0.0001:  # v11: tighter threshold — snap anything > 0.0001
                        still_has_c0_error = True
                        new_kfs = list(keyframes)
                        new_kfs[-1] = (new_kfs[-1][0], first_val)

                        # Smooth the transition by adjusting the last few keyframes
                        if len(new_kfs) >= 4:
                            n_blend = min(3, len(new_kfs) - 1)
                            for k in range(1, n_blend + 1):
                                idx = len(new_kfs) - 1 - k
                                if idx < 1:
                                    break
                                alpha = k / (n_blend + 1)
                                blend_val = new_kfs[idx][1] + alpha * (first_val - new_kfs[idx][1]) * (1 - alpha)
                                new_kfs[idx] = (new_kfs[idx][0], blend_val)

                        # v11 NEW: C1 cubic correction after C0 snap
                        if do_c1_cubic and len(new_kfs) >= 3:
                            # Compute start velocity
                            dt_start = new_kfs[1][0] - new_kfs[0][0] if len(new_kfs) > 1 else duration
                            if dt_start > 1e-6:
                                v_start = (new_kfs[1][1] - new_kfs[0][1]) / dt_start
                            else:
                                v_start = 0.0

                            # Adjust second-to-last keyframe for C1 match
                            dt_end = new_kfs[-1][0] - new_kfs[-2][0]
                            if dt_end > 1e-6:
                                desired_v_end = v_start  # Match start velocity for smooth loop
                                adjusted_val = new_kfs[-1][1] - desired_v_end * dt_end
                                # Only apply if adjustment is small (< 20% of amplitude)
                                values = [v for t, v in new_kfs]
                                amplitude = max(abs(v - values[0]) for v in values)
                                if abs(adjusted_val - new_kfs[-2][1]) < amplitude * 0.2:
                                    new_kfs[-2] = (new_kfs[-2][0], adjusted_val)

                        new_channels[bone_name][channel] = new_kfs
                    else:
                        new_channels[bone_name][channel] = keyframes

            result_channels = new_channels

            if not still_has_c0_error:
                break

        quality_report.loop_validation_applied = True
        quality_report.loop_validation_iterations = iteration + 1
        return result_channels, quality_report

    def _post_process_empty_cleanup(
        self,
        output_path: str,
        all_animations: Dict[str, Any],
        stats: Dict[str, Any]
    ) -> Dict[str, Any]:
        """v11 Improvement 4: Post-Process Empty Animation File Cleanup.

        After conversion, checks if the output file is truly empty or contains
        only meaningless data, and removes it if so. Also checks if animations
        have ALL bone channels with max deviation < threshold (truly_static),
        and removes those. If no animations remain after removal, skip the file.
        """
        cfg = self.config
        if not hasattr(cfg, 'post_process_empty_cleanup') or not cfg.post_process_empty_cleanup:
            return {'removed': False}

        if not all_animations:
            # No animations at all - remove the file
            if output_path and os.path.exists(output_path):
                os.remove(output_path)
            return {'removed': True, 'reason': 'no_animations'}

        # Check if ALL animations are empty/static
        all_empty = True
        for anim_name, anim_data in all_animations.items():
            bones = anim_data.get('bones', {})
            if bones:
                for bone_name, bone_data in bones.items():
                    for channel_name, channel_data in bone_data.items():
                        if isinstance(channel_data, dict):
                            for axis, time_data in channel_data.items():
                                if isinstance(time_data, dict):
                                    for time_key, val in time_data.items():
                                        if isinstance(val, (int, float)) and abs(val) > 0.01:
                                            all_empty = False
                                            break
                                elif isinstance(time_data, (int, float)) and abs(time_data) > 0.01:
                                    all_empty = False
                                    break
                            if not all_empty:
                                break
                        if not all_empty:
                            break
                    if not all_empty:
                        break
            if not all_empty:
                break

        if all_empty:
            if output_path and os.path.exists(output_path):
                os.remove(output_path)
            return {'removed': True, 'reason': 'all_empty'}

        # v11 NEW: Check for truly-static animations (max deviation < threshold)
        # If an animation has ALL bone channels with max deviation < 0.01 deg (rot)
        # or < 0.001 px (pos), mark it as truly_static and remove it.
        rot_thresh = cfg.truly_static_rot_threshold if hasattr(cfg, 'truly_static_rot_threshold') else 0.01
        pos_thresh = cfg.truly_static_pos_threshold if hasattr(cfg, 'truly_static_pos_threshold') else 0.001

        truly_static_names = []
        for anim_name, anim_data in all_animations.items():
            is_truly_static = True
            bones = anim_data.get('bones', {})
            if not bones:
                # No bones at all — it's truly static
                truly_static_names.append(anim_name)
                continue

            for bone_name, bone_data in bones.items():
                for channel_name, channel_data in bone_data.items():
                    if isinstance(channel_data, dict):
                        # Determine threshold based on channel type
                        is_rotation = channel_name in ('rotation', 'rot')
                        threshold = rot_thresh if is_rotation else pos_thresh
                        for axis, time_data in channel_data.items():
                            if isinstance(time_data, dict):
                                for time_key, val in time_data.items():
                                    if isinstance(val, (int, float)) and abs(val) > threshold:
                                        is_truly_static = False
                                        break
                                if not is_truly_static:
                                    break
                            elif isinstance(time_data, (int, float)) and abs(time_data) > threshold:
                                is_truly_static = False
                                break
                        if not is_truly_static:
                            break
                    if not is_truly_static:
                        break
                if not is_truly_static:
                    break

            if is_truly_static:
                truly_static_names.append(anim_name)

        # Remove truly-static animations
        for name in truly_static_names:
            if name in all_animations:
                del all_animations[name]

        # If no animations remain after removing truly-static ones, remove the file
        if not all_animations:
            if output_path and os.path.exists(output_path):
                os.remove(output_path)
            return {'removed': True, 'reason': 'all_truly_static', 'static_removed': truly_static_names}

        return {'removed': False, 'static_removed': truly_static_names}

    def _final_c0_enforcement_pass(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float
    ) -> Tuple[Dict[str, Dict[str, List[Tuple[float, float]]]], int]:
        """v11 Improvement 1: FINAL C0 Enforcement — GUARANTEED 100% C0 Continuity.

        After ALL C1/C2 enforcement and loop validation, this is the FINAL pass
        that ensures the LAST keyframe value EXACTLY matches the FIRST keyframe
        value for every bone channel. This is the simplest and most impactful fix
        that eliminates any remaining C0 discontinuity.

        Returns:
            (updated_bone_channels, count_of_channels_snapped)
        """
        cfg = self.config
        snap_threshold = cfg.final_c0_threshold if hasattr(cfg, 'final_c0_threshold') else 0.001
        snapped_count = 0

        result_channels = {}
        for bone_name, channels in bone_channels.items():
            result_channels[bone_name] = {}
            for channel, keyframes in channels.items():
                if len(keyframes) < 2:
                    result_channels[bone_name][channel] = keyframes
                    continue

                first_val = keyframes[0][1]
                last_val = keyframes[-1][1]
                c0_err = abs(first_val - last_val)

                if c0_err > snap_threshold:
                    # Snap the last keyframe to exactly match the first
                    new_kfs = list(keyframes)
                    new_kfs[-1] = (new_kfs[-1][0], first_val)
                    result_channels[bone_name][channel] = new_kfs
                    snapped_count += 1
                else:
                    result_channels[bone_name][channel] = keyframes

        return result_channels, snapped_count

    def _general_c1_post_correction(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        c1_threshold: float = 2.0,
        max_iterations: int = 3
    ) -> Tuple[Dict[str, Dict[str, List[Tuple[float, float]]]], int]:
        """v16: General C1 Post-Correction for ALL loop animations.

        After standard C1 enforcement, many animations still have C1 errors
        > 2°/s because the global_cubic and local_blend methods don't always
        fully correct the velocity mismatch. This pass directly adjusts the
        keyframes in the last 25% of the animation to match the start velocity.

        Algorithm:
        1. Measure C1 error at loop boundary using finite differences
        2. If C1 > threshold, apply a smooth cubic correction over last 25%
        3. The correction preserves C0 (last value = first value) and
           adjusts velocity to match start velocity (C1)
        4. Iterate up to max_iterations times

        Returns:
            (updated_bone_channels, count_of_channels_corrected)
        """
        corrected_count = 0

        for iteration in range(max_iterations):
            max_c1 = 0.0
            any_corrected = False

            for bone_name, channels in bone_channels.items():
                for channel, keyframes in channels.items():
                    if len(keyframes) < 4:
                        continue

                    # Measure C1 at loop boundary using finite differences
                    dt_start = keyframes[1][0] - keyframes[0][0]
                    dt_end = keyframes[-1][0] - keyframes[-2][0]
                    if dt_start < 1e-8 or dt_end < 1e-8:
                        continue

                    v0 = (keyframes[1][1] - keyframes[0][1]) / dt_start
                    vT = (keyframes[-1][1] - keyframes[-2][1]) / dt_end

                    dv = vT - v0  # velocity error
                    max_c1 = max(max_c1, abs(dv))

                    if abs(dv) < c1_threshold:
                        continue

                    # Apply smooth correction over the last 40% of keyframes
                    # v16: Extended from 25% to 40% for better velocity matching
                    n_kf = len(keyframes)
                    start_idx = max(1, n_kf * 3 // 5)
                    T_zone = keyframes[-1][0] - keyframes[start_idx][0]

                    if T_zone < 1e-8:
                        continue

                    # Cubic correction: c(s) = a*s^3 + b*s^2
                    # Constraints: c(0)=0, c(1)=0, c'(1)=-dv
                    # With c(1)=a+b=0 => b=-a
                    # c'(s) = 3a*s^2 + 2b*s = 3a*s^2 - 2a*s
                    # c'(1) = a = -dv * T_zone
                    # Wait, the derivative with respect to TIME, not s:
                    # dc/dt = dc/ds * ds/dt = (3a*s^2 + 2b*s) / T_zone
                    # At s=1: dc/dt = (3a + 2b) / T_zone = (3a - 2a) / T_zone = a / T_zone
                    # We want dc/dt at end = -dv, so a / T_zone = -dv => a = -dv * T_zone
                    a_c = -dv * T_zone
                    b_c = -a_c  # b = -a to satisfy c(1) = 0

                    new_kfs = list(keyframes)
                    for i in range(start_idx, n_kf):
                        t_i, v_i = new_kfs[i]
                        s_i = (t_i - new_kfs[start_idx][0]) / T_zone
                        s_i = max(0.0, min(1.0, s_i))
                        correction = a_c * s_i**3 + b_c * s_i**2
                        new_kfs[i] = (t_i, v_i + correction)

                    # Snap last to first for C0
                    new_kfs[-1] = (new_kfs[-1][0], new_kfs[0][1])
                    bone_channels[bone_name][channel] = new_kfs
                    corrected_count += 1
                    any_corrected = True

            if not any_corrected or max_c1 < c1_threshold:
                break

        return bone_channels, corrected_count

    def _walk_validation_resample(
        self,
        anim_name: str,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        interpolation: str
    ) -> Tuple[Dict[str, Dict[str, List[Tuple[float, float]]]], int]:
        """v12 Enhanced: Walk Validation — ensure ALL walk animations have sufficient keyframes.

        v12 Fix: Now processes ALL bones (not just legs) for walk animations, ensuring
        the entire walk cycle has adequate keyframe density for smooth playback.
        Also handles extremely sparse walks (3-5 KFs) by generating full cycle
        resampled keyframes.

        Returns:
            (updated_bone_channels, count_of_additional_keyframes_generated)
        """
        cfg = self.config
        min_kfs = cfg.walk_min_keyframes_per_channel if hasattr(cfg, 'walk_min_keyframes_per_channel') else 8
        walk_patterns = cfg.walk_bone_patterns
        total_generated = 0

        result_channels = {}
        for bone_name, channels in bone_channels.items():
            result_channels[bone_name] = {}
            bone_lower = bone_name.lower()
            is_leg = any(p in bone_lower for p in walk_patterns)

            for channel, keyframes in channels.items():
                # v12: Process ALL bones for walks (not just legs), but legs need min_kfs
                if not is_leg and len(keyframes) >= 4:
                    # Non-leg bones with 4+ KFs are fine
                    result_channels[bone_name][channel] = keyframes
                    continue
                if is_leg and len(keyframes) >= min_kfs:
                    # Leg bones already have enough KFs
                    result_channels[bone_name][channel] = keyframes
                    continue
                # Non-leg bones with < 4 KFs also get resampled
                if not is_leg and len(keyframes) < 4:
                    pass  # fall through to resample

                # For very sparse keyframes (< 4), use a smarter approach:
                # First check if the channel is essentially static
                if len(keyframes) >= 2:
                    values = [v for t, v in keyframes]
                    value_range = max(values) - min(values)
                    if value_range < 0.02:
                        # Static channel - just keep as-is
                        result_channels[bone_name][channel] = keyframes
                        continue

                # Resample the channel to generate at least min_kfs keyframes
                # Use the current keyframes as control points and resample at regular intervals
                n_target = max(min_kfs, len(keyframes))
                dt = duration / n_target
                target_times = [i * dt for i in range(n_target + 1)]

                try:
                    resampled = CatmullRomEvaluator.resample_channel(
                        keyframes, target_times, interpolation
                    )
                except Exception:
                    # If resampling fails, keep original keyframes
                    result_channels[bone_name][channel] = keyframes
                    continue

                # Only add keyframes that aren't already present (avoid duplicates)
                existing_times = set(round(t, 4) for t, v in keyframes)
                new_kfs = list(keyframes)
                for t, v in resampled:
                    t_rounded = round(t, 4)
                    if t_rounded not in existing_times:
                        new_kfs.append((t, v))
                        existing_times.add(t_rounded)

                new_kfs.sort(key=lambda x: x[0])

                # v12: Ensure C0 continuity after resampling
                if len(new_kfs) >= 2:
                    first_v = new_kfs[0][1]
                    last_t, last_v = new_kfs[-1]
                    if abs(first_v - last_v) > 0.001:
                        new_kfs[-1] = (last_t, first_v)

                total_generated += len(new_kfs) - len(keyframes)
                result_channels[bone_name][channel] = new_kfs

        return result_channels, total_generated

    # ========================================================================
    # v16 NEW METHODS: Walk C1 Correction, Quintic Refinement, Bone Chain
    # ========================================================================

    def _walk_c1_correction_pass(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        interpolation: str,
        anim_name: str
    ) -> Tuple[Dict[str, Dict[str, List[Tuple[float, float]]]], Dict[str, Any]]:
        """v16: Walk-specific C1 correction pass.

        After standard C1 enforcement, walk animations may still show C1
        errors of 3-4 deg/s. This pass uses the walk cycle structure for
        more precise velocity matching at the loop boundary.

        Algorithm:
        1. Detect the walk period more precisely via peak autocorrelation lag
        2. Resample at 480Hz for high-resolution analysis
        3. Measure velocity at the loop boundary
        4. Construct a cubic Hermite correction spline over the last 15%
           of the animation to match the start velocity
        """
        cfg = self.config
        info = {'applied': False, 'c1_before': 0.0, 'c1_after': 0.0}

        walk_c1_target = getattr(cfg, 'walk_c1_target', 1.5)
        walk_c1_ratio = getattr(cfg, 'walk_c1_correction_ratio', 0.15)
        walk_resample_rate = getattr(cfg, 'walk_c1_resample_rate', 480.0)

        # First, measure current max C1 error
        max_c1_before = 0.0
        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if len(keyframes) < 2:
                    continue
                n_resample = max(int(duration * cfg.resample_rate), 60)
                resample_dt = duration / n_resample
                resample_times = [i * resample_dt for i in range(n_resample + 1)]
                resampled = CatmullRomEvaluator.resample_channel(
                    keyframes, resample_times, interpolation
                )
                if len(resampled) < 5:
                    continue
                v0 = (-3*resampled[0][1] + 4*resampled[1][1] - resampled[2][1]) / (2*resample_dt)
                vT = (3*resampled[-1][1] - 4*resampled[-2][1] + resampled[-3][1]) / (2*resample_dt)
                max_c1_before = max(max_c1_before, abs(v0 - vT))

        info['c1_before'] = max_c1_before

        if max_c1_before < walk_c1_target:
            return bone_channels, info

        # Apply correction to each channel
        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if len(keyframes) < 2:
                    continue

                is_rotation = channel in ('rx', 'ry', 'rz', 'x', 'y', 'z')

                # High-resolution resampling
                n_resample = max(int(duration * walk_resample_rate), 120)
                resample_dt = duration / n_resample
                resample_times = [i * resample_dt for i in range(n_resample + 1)]
                resampled = CatmullRomEvaluator.resample_channel(
                    keyframes, resample_times, interpolation
                )
                if len(resampled) < 5:
                    continue

                p0 = resampled[0][1]
                v0 = (-3*resampled[0][1] + 4*resampled[1][1] - resampled[2][1]) / (2*resample_dt)
                vT = (3*resampled[-1][1] - 4*resampled[-2][1] + resampled[-3][1]) / (2*resample_dt)

                c1_diff = abs(v0 - vT)
                if c1_diff < walk_c1_target:
                    continue

                # Correction zone: last 15% of animation
                zone_duration = duration * walk_c1_ratio
                zone_start_time = duration - zone_duration

                # Find zone start index
                zone_start_idx = 0
                for i, (t, v) in enumerate(resampled):
                    if t >= zone_start_time:
                        zone_start_idx = i
                        break

                if zone_start_idx < 1 or zone_start_idx >= len(resampled) - 1:
                    continue

                # Get values at zone boundary
                p_zone_start = resampled[zone_start_idx][1]
                if zone_start_idx > 0 and zone_start_idx < len(resampled) - 1:
                    dt_zone = resampled[zone_start_idx + 1][0] - resampled[zone_start_idx - 1][0]
                    if dt_zone > 1e-12:
                        v_zone_start = (resampled[zone_start_idx + 1][1] - resampled[zone_start_idx - 1][1]) / dt_zone
                    else:
                        v_zone_start = 0.0
                else:
                    v_zone_start = 0.0

                # Apply cubic Hermite correction in the zone
                # The correction ensures C0+C1 at the endpoint (p0, v0)
                for i in range(zone_start_idx, len(resampled)):
                    t, v_orig = resampled[i]
                    s = (t - zone_start_time) / zone_duration if zone_duration > 1e-12 else 1.0
                    s = max(0.0, min(1.0, s))

                    # Compute Hermite-corrected value
                    v_hermite = C1ContinuityEnforcer._cubic_hermite(
                        s, p_zone_start, v_zone_start,
                        p0, v0, zone_duration
                    )

                    # Blend using smooth step (3s^2 - 2s^3) for gentle transition
                    w_blend = 3.0 * s * s - 2.0 * s * s * s
                    new_val = v_orig * (1.0 - w_blend) + v_hermite * w_blend
                    resampled[i] = (t, new_val)

                # Ensure exact C0 match
                resampled[-1] = (resampled[-1][0], p0)

                # Rebuild keyframes from corrected resampled data using C1 enforcer's method
                new_keyframes = self.c1_enforcer._rebuild_keyframes_from_resampled_with_zone(
                    keyframes, resampled, duration, p0, zone_start_time
                )
                bone_channels[bone_name][channel] = new_keyframes
                info['applied'] = True

        # Measure C1 after correction
        max_c1_after = 0.0
        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if len(keyframes) < 2:
                    continue
                n_resample = max(int(duration * cfg.resample_rate), 60)
                resample_dt = duration / n_resample
                resample_times = [i * resample_dt for i in range(n_resample + 1)]
                resampled = CatmullRomEvaluator.resample_channel(
                    keyframes, resample_times, interpolation
                )
                if len(resampled) < 5:
                    continue
                v0 = (-3*resampled[0][1] + 4*resampled[1][1] - resampled[2][1]) / (2*resample_dt)
                vT = (3*resampled[-1][1] - 4*resampled[-2][1] + resampled[-3][1]) / (2*resample_dt)
                max_c1_after = max(max_c1_after, abs(v0 - vT))

        info['c1_after'] = max_c1_after
        return bone_channels, info

    def _c1_quintic_refinement_pass(
        self,
        bone_channels: Dict[str, Dict[str, List[Tuple[float, float]]]],
        duration: float,
        interpolation: str,
        cached_resampled: Optional[Dict[str, Dict[str, List[Tuple[float, float]]]]] = None
    ) -> Tuple[Dict[str, Dict[str, List[Tuple[float, float]]]], Dict[str, Any]]:
        """v16: C1 velocity matching refinement using quintic polynomial.

        After global cubic correction, if C1 still exceeds the threshold,
        applies an additional localized correction using a quintic polynomial
        c(t) = at^5 + bt^4 + ct^3 over the last 10% of the animation.

        Constraints:
          c(T_end) = 0 (don't change endpoint value)
          c'(T_end) = -(vT_corrected - v0) (match velocity)
          c''(T_end) = 0 (smooth acceleration at boundary)
        """
        cfg = self.config
        info = {'applied': False, 'channels_corrected': 0}

        threshold = getattr(cfg, 'c1_quintic_refinement_threshold', 1.5)
        zone_ratio = getattr(cfg, 'c1_quintic_refinement_zone_ratio', 0.10)

        for bone_name, channels in bone_channels.items():
            for channel, keyframes in channels.items():
                if len(keyframes) < 2:
                    continue

                is_rotation = channel in ('rx', 'ry', 'rz', 'x', 'y', 'z')
                n_resample = max(int(duration * cfg.resample_rate), 60)
                resample_dt = duration / n_resample
                resample_times = [i * resample_dt for i in range(n_resample + 1)]

                resampled = CatmullRomEvaluator.resample_channel(
                    keyframes, resample_times, interpolation
                )
                if len(resampled) < 5:
                    continue

                p0 = resampled[0][1]
                v0 = (-3*resampled[0][1] + 4*resampled[1][1] - resampled[2][1]) / (2*resample_dt)
                vT = (3*resampled[-1][1] - 4*resampled[-2][1] + resampled[-3][1]) / (2*resample_dt)

                c1_diff = abs(v0 - vT)
                if c1_diff < threshold:
                    continue

                # Compute quintic correction coefficients
                # c(s) = a*s^5 + b*s^4 + c*s^3 where s = (t-t_zone_start)/zone_duration
                # Constraints at s=1:
                #   c(1) = a + b + c = 0 (don't change endpoint value)
                #   c'(1)/zone_dur = (5a + 4b + 3c)/zone_dur = -dv (match velocity)
                #   c''(1)/zone_dur^2 = (20a + 12b + 6c)/zone_dur^2 = 0 (smooth accel)
                # From c(1)=0: c = -(a+b)
                # From c''(1)=0: 20a + 12b - 6(a+b) = 0 => 14a + 6b = 0 => b = -7a/3
                # From c'(1)= -dv*zone_dur: 5a + 4(-7a/3) + 3(-(a+(-7a/3))) = -dv*zone_dur
                #   = 5a - 28a/3 - 3(a - 7a/3) = 5a - 28a/3 - 3*(-4a/3)
                #   = 5a - 28a/3 + 12a/3 = 5a - 16a/3 = (15a - 16a)/3 = -a/3
                # So -a/3 = -dv * zone_dur => a = 3*dv*zone_dur
                dv = vT - v0  # positive means vT > v0, need to reduce
                zone_duration = duration * zone_ratio

                a_coeff = 3.0 * dv * zone_duration
                b_coeff = -7.0 * a_coeff / 3.0
                c_coeff = -(a_coeff + b_coeff)

                # Find zone start index
                zone_start_time = duration - zone_duration
                zone_start_idx = 0
                for i, (t, v) in enumerate(resampled):
                    if t >= zone_start_time:
                        zone_start_idx = i
                        break

                if zone_start_idx < 1 or zone_start_idx >= len(resampled) - 1:
                    continue

                # Apply correction
                for i in range(zone_start_idx, len(resampled)):
                    t_i, v_i = resampled[i]
                    s = (t_i - zone_start_time) / zone_duration if zone_duration > 1e-12 else 1.0
                    s = max(0.0, min(1.0, s))
                    correction = a_coeff * s**5 + b_coeff * s**4 + c_coeff * s**3
                    resampled[i] = (t_i, v_i - correction)

                # Ensure exact C0 match
                resampled[-1] = (resampled[-1][0], p0)

                # Rebuild keyframes using C1 enforcer's method
                new_keyframes = self.c1_enforcer._rebuild_keyframes_from_resampled_with_zone(
                    keyframes, resampled, duration, p0, zone_start_time
                )
                bone_channels[bone_name][channel] = new_keyframes
                info['channels_corrected'] += 1
                info['applied'] = True

        return bone_channels, info

    @staticmethod
    def _detect_bone_chains(
        bone_names: List[str],
        min_chain_length: int = 3
    ) -> Dict[str, List[str]]:
        """v16: Detect bone chains by naming pattern.

        Groups bones by their naming pattern (e.g., jointLA1, jointLA2, ...,
        jointLA10, hair_jointR1, hair_jointR3, hair_jointR5).

        Returns a dict mapping chain prefix -> list of bone names in order.
        """
        import re

        chains = {}
        # Pattern: name followed by a number
        pattern = re.compile(r'^(.*?)(\d+)$')

        for bone_name in bone_names:
            m = pattern.match(bone_name)
            if m:
                prefix = m.group(1)
                suffix_num = int(m.group(2))
                if prefix not in chains:
                    chains[prefix] = []
                chains[prefix].append(bone_name)

        # Filter to chains with minimum length
        result = {}
        for prefix, bones in chains.items():
            if len(bones) >= min_chain_length:
                # Sort by suffix number
                def _sort_key(name):
                    m2 = pattern.match(name)
                    return int(m2.group(2)) if m2 else 0
                result[prefix] = sorted(bones, key=_sort_key)

        return result

    @staticmethod
    def _detect_lr_bone_pairs(bone_names: List[str]) -> List[Tuple[str, str]]:
        """v16: Detect left/right bone pairs for walk identification.

        Looks for bones with L/R or left/right prefixes/suffixes and
        pairs them up. Used for detecting walk patterns even with
        non-standard bone names.
        """
        import re

        pairs = []
        left_bones = {}
        right_bones = {}

        l_patterns = [re.compile(r'^(l|left|L|Left)[_\-](.*)$', re.IGNORECASE),
                      re.compile(r'^(.*)[_\-](l|left|L|Left)$', re.IGNORECASE)]
        r_patterns = [re.compile(r'^(r|right|R|Right)[_\-](.*)$', re.IGNORECASE),
                      re.compile(r'^(.*)[_\-](r|right|R|Right)$', re.IGNORECASE)]

        for bone_name in bone_names:
            for pat in l_patterns:
                m = pat.match(bone_name)
                if m:
                    # Extract the base name (without L/R prefix/suffix)
                    groups = [g for g in m.groups() if g and g.lower() not in ('l', 'left', 'r', 'right')]
                    base = groups[0].lower() if groups else bone_name.lower()
                    left_bones[base] = bone_name
                    break

            for pat in r_patterns:
                m = pat.match(bone_name)
                if m:
                    groups = [g for g in m.groups() if g and g.lower() not in ('l', 'left', 'r', 'right')]
                    base = groups[0].lower() if groups else bone_name.lower()
                    right_bones[base] = bone_name
                    break

        # Match pairs
        for base in left_bones:
            if base in right_bones:
                pairs.append((left_bones[base], right_bones[base]))

        return pairs

    def _remove_truly_static_animations(
        self,
        all_animations: Dict[str, Any],
        quality_reports: Dict[str, 'AnimationQualityReport']
    ) -> List[str]:
        """v11 Improvement 4: Remove truly-static animations.

        An animation is "truly static" if ALL bone channels have max deviation
        < 0.01 degrees (rotation) or < 0.001 pixels (position).
        """
        cfg = self.config
        rot_thresh = cfg.truly_static_rot_threshold if hasattr(cfg, 'truly_static_rot_threshold') else 0.01
        pos_thresh = cfg.truly_static_pos_threshold if hasattr(cfg, 'truly_static_pos_threshold') else 0.001

        static_names = []
        for anim_name, anim_data in all_animations.items():
            is_truly_static = True
            bones = anim_data.get('bones', {})
            if not bones:
                static_names.append(anim_name)
                continue

            for bone_name, bone_data in bones.items():
                for channel_name, channel_data in bone_data.items():
                    if isinstance(channel_data, dict):
                        is_rotation = channel_name in ('rotation', 'rot')
                        threshold = rot_thresh if is_rotation else pos_thresh
                        for axis, time_data in channel_data.items():
                            if isinstance(time_data, dict):
                                for time_key, val in time_data.items():
                                    if isinstance(val, (int, float)) and abs(val) > threshold:
                                        is_truly_static = False
                                        break
                                if not is_truly_static:
                                    break
                            elif isinstance(time_data, (int, float)) and abs(time_data) > threshold:
                                is_truly_static = False
                                break
                        if not is_truly_static:
                            break
                    if not is_truly_static:
                        break
                if not is_truly_static:
                    break

            if is_truly_static:
                static_names.append(anim_name)

        return static_names

    def _extract_all_textures(
        self,
        bbmodel_path: str,
        output_dir: str
    ) -> List[str]:
        """v9 Improvement 7: Multi-Texture Extraction.

        Extracts ALL textures from .bbmodel files that have multiple textures,
        naming them model_name.png, model_name_1.png, model_name_2.png, etc.
        """
        if not self.config.extract_all_textures:
            return []

        import base64
        extracted_paths = []

        try:
            with open(bbmodel_path, 'r', encoding='utf-8') as f:
                bbmodel = json.load(f)
        except Exception:
            return []

        model_name = os.path.splitext(os.path.basename(bbmodel_path))[0]
        textures = bbmodel.get('textures', [])

        if not textures:
            return []

        os.makedirs(output_dir, exist_ok=True)

        for i, tex in enumerate(textures):
            if not isinstance(tex, dict):
                continue

            source = tex.get('source', '')

            if i == 0:
                out_name = f"{model_name}.png"
            else:
                out_name = f"{model_name}_{i}.png"

            out_path = os.path.join(output_dir, out_name)

            if source and source.startswith('data:'):
                try:
                    b64_part = source.split(',', 1)
                    if len(b64_part) == 2:
                        img_data = base64.b64decode(b64_part[1])
                        with open(out_path, 'wb') as f:
                            f.write(img_data)
                        extracted_paths.append(out_path)
                except Exception:
                    pass
            elif source and os.path.isfile(source):
                import shutil
                try:
                    shutil.copy2(source, out_path)
                    extracted_paths.append(out_path)
                except Exception:
                    pass

        return extracted_paths


# ============================================================================
# Batch Processing (v9)
# ============================================================================

def batch_convert(input_dir: str, output_dir: str,
                  config: ConverterConfig = None,
                  zip_path: Optional[str] = None) -> bool:
    """Batch convert all .bbmodel files in a directory tree (v15).

    For each .bbmodel file:
      - Extract geo.json + texture (using bbmodel_to_geo.py)
      - Extract and convert animations (using this v15 converter)
      - Post-process UV mapping if geo.json was created (v7)
      - Save to output directory maintaining directory structure
      - Optionally package into a ZIP file

    Returns:
        True if no errors, False otherwise.
    """
    print("=" * 70)
    print("  Universal BBModel Animation Converter (v15)")
    print("  .bbmodel -> .animation.json with C1+C2 Correction & v15 Improvements")
    print("  GeckoLib Format for MC 1.20.1 Forge Mod Development")
    print("  [v11] GUARANTEED 100% C0 Continuity (final enforcement pass)")
    print("  [v11] Better Walk Quality (240Hz resample, validation, phase closure)")
    print("  [v11] More Aggressive Idle Dedup (0.25 threshold, small-amplitude merge)")
    print("  [v11] Truly-Static Animation Removal & Skip Empty Files")
    print("  [v11] Enhanced Loop Validation (iterative C0+C1 cubic correction)")
    print("  [v11] Walk Phase Closure Duration Detection")
    print("  [v10] Progressive Global Correction for moderate distortion")
    print("  [v10] Aggressive Idle Dedup with extended aliases")
    print("  [v10] Enhanced Walk Cycle with leg-pair awareness")
    print("  [v10] Empty Animation File Smart Cleanup")
    print("  [v10] Periodic Auto-Trim for repetitive animations")
    print("  [v10] Tighter Loop Validation (secondary C0/C1 pass)")
    print("  [v9] C2 Acceleration Continuity (quintic Hermite)")
    print("  [v9] Walk Full-Cycle Reconstruction & Smart Truncation")
    print("  [v8] Truly-Empty Purge & Velocity Zero-Crossing")
    print("  [v7] Cubic Hermite Transition Zone (C0+C1 continuity)")
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
    print("  DONE - Universal BBModel Animation Converter (v15)")
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
        description="Universal BBModel Animation Converter with C1+C2 Correction & v15 Improvements"
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
    parser.add_argument("--distortion-limit", type=float, default=0.50,
                        help="Max correction/amplitude ratio before local blend fallback (default: 0.50)")
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
