#!/usr/bin/env python3
"""
Batch Convert All - Full Pipeline for MROLF-TGNBF
===================================================
Processes ALL .bbmodel files under the MROLF-TGNBF project directory:
  1. Converts geo.json using bbmodel_to_geo.py (BBModelToGeo class)
  2. Converts animation.json using the v18 converter
  3. Extracts texture PNG from .bbmodel (including multi-texture)
  4. Saves all outputs preserving directory structure
  5. Generates a ZIP package (SDMCXKIFFNEK.zip)

v18 Improvements over v17:
  - WALK DURATION EXTENSION WITH KEYFRAME REPLICATION
  - EXACT-DUPLICATE ANIMATION CONSOLIDATION (idle/evolved/attack dedup)
  - WALK-SPECIFIC C1 LIGHTWEIGHT ENFORCEMENT (naturalness 0.0 → 0.94)
  - SMART WALK DURATION PRESERVATION
  - IMPROVED NATURALNESS SCORING FOR HIGH-DENSITY ANIMATIONS
  - WALK CYCLE PERIODIC EXTRAPOLATION
  - LOOP BOUNDARY C0/C1 SMOOTH BRIDGE

Inherited from v17:
  - C1 FULL RESAMPLE VELOCITY CORRECTION
  - SLEEPING C1 METHOD REPORTING
  - IDLE/ATTACK/EVOLVED DEDUP PROTECTION
  - WALK C1 IMPROVEMENT
  - C1 QUINTIC REFINEMENT
  - TENTACLE/HAIR CHAIN PERIODICITY
  - LOOP LENGTH AUTO-EXTRACTION

Inherited from v15:
  - WALK AWARE DP SIMPLIFICATION: Prevents over-simplification of walk animations
  - FULL RESAMPLE C1 ENFORCEMENT: Raised-cosine blend with expanded transition zones
  - SLEEPING ANIMATION FIX: C1 error reduced from 18.79 → 7.08 deg/s
  - EVOLVED/IDLE MERGE DEDUP: Intelligently merges near-duplicate idle/evolved
  - STATIC IDLE GENERATION: Models with all-zero animations get a static idle
  - EXPANDED TRANSITION ZONES: Up to 55% for long animations

Inherited from v14:
  - FIXED ANIMATION NAMING: No more double-namespace bug
  - MULTI-PASS C1 REFINEMENT: Iterative C1 enforcement
  - ADAPTIVE TRANSITION ZONE: Dynamically expanded for high-C1-error channels
  - IMPROVED BOUNCE-BRIDGE: Cosine easing for velocity reversal cases
  - PERIODIC CHANNEL LOOP SMOOTHING: Phase-matched wrapping
  - HIGHER DISTORTION TOLERANCE: More aggressive global corrections

Output directory structure mirrors the source:
  /home/z/my-project/db/output/
    crude/quac.geo.json
    crude/quac.animation.json
    crude/quac.png
    infected/infCow.geo.json
    infected/infCow.animation.json
    infected/infCow.png
    ...

ZIP package organized by creature category:
  SDMCXKIFFNEK.zip
    crude/quac.geo.json
    crude/quac.animation.json
    crude/quac.png
    ...
"""

import json
import os
import sys
import time
import traceback
import zipfile

# ============================================================================
# Configuration
# ============================================================================

INPUT_DIR = "/home/z/my-project/MROLF-TGNBF"
OUTPUT_DIR = "/home/z/my-project/db/output"
ZIP_PATH = "/home/z/my-project/db/SDMCXKIFFNEK.zip"

# Directories to skip (already processed or non-model files)
SKIP_DIRS = {'bedrock', 'fix_heblu_skin_rotation.py'}


def main():
    """Main batch conversion pipeline."""
    print("=" * 70)
    print("  Batch Convert All - Full Pipeline")
    print("  MROLF-TGNBF -> Geo + Animation + Texture")
    print("  Using v18 Converter with Walk Lightweight C1 + Exact-Duplicate Consolidation + Smooth Bridge")
    print("=" * 70)
    print()

    # Verify input directory exists
    if not os.path.isdir(INPUT_DIR):
        print(f"ERROR: Input directory not found: {INPUT_DIR}")
        sys.exit(1)

    # Import converters
    converter_dir = os.path.dirname(os.path.abspath(__file__))
    if converter_dir not in sys.path:
        sys.path.insert(0, converter_dir)

    # Import v18 converter
    try:
        from bbmodel_animation_converter_v18 import (
            BBModelAnimationConverter,
            ConverterConfig,
        )
        print("  [OK] Loaded bbmodel_animation_converter_v18")
    except ImportError as e:
        print(f"  [FAIL] Could not import v18 converter: {e}")
        sys.exit(1)

    # Import geo converter
    try:
        from bbmodel_to_geo import BBModelToGeo
        geo_converter = BBModelToGeo()
        print("  [OK] Loaded bbmodel_to_geo (v8 UV fix)")
    except ImportError:
        # Try loading from same directory
        import importlib.util
        geo_path = os.path.join(converter_dir, 'bbmodel_to_geo.py')
        if os.path.exists(geo_path):
            spec = importlib.util.spec_from_file_location("bbmodel_to_geo", geo_path)
            geo_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(geo_mod)
            geo_converter = geo_mod.BBModelToGeo()
            print("  [OK] Loaded bbmodel_to_geo (from path, v8 UV fix)")
        else:
            print(f"  [FAIL] Could not find bbmodel_to_geo.py")
            sys.exit(1)

    # Configure v18 converter
    config = ConverterConfig(
        enable_c1_enforcement=True,
        enable_duration_optimization=True,
        autocorrelation_enabled=True,
        blend_window_ratio=0.08,
        skip_empty_animations=False,
        preserve_empty_as_static=True,
        deduplicate_case_insensitive=True,
        content_hash_dedup=True,
        smart_bone_merge=True,
        always_union_bones=True,
        normalize_animation_names=True,
        snap_to_ticks=True,
        bounce_detection_threshold=0.3,
        # v14: Higher distortion limits for more aggressive global correction
        global_cubic_distortion_limit=0.65,
        # v7: Cubic Hermite transition zone
        transition_zone_cubic_hermite=True,
        transition_zone_ratio=0.25,
        transition_zone_bounce_damp=0.0,
        transition_zone_max_ratio=0.40,
        # v7: Walk cycle completion
        periodic_enhance_enabled=True,
        periodic_autocorrelation_threshold=0.4,
        velocity_zero_crossing_loop=True,
        # v7: Smart empty/duplicate handling
        skip_empty_animation_files=True,
        skip_meaningless_animation_files=True,
        bone_coverage_merge_threshold=0.70,
        # v7: Better scoring weights
        c0_scoring_weight=5.0,
        c1_scoring_weight=2.0,
        # v8: Truly-empty animation purge
        purge_truly_empty_animations=True,
        truly_empty_rot_threshold_post=0.01,
        truly_empty_pos_threshold_post=0.001,
        # v8: Unknown animation re-classification
        reclassify_unknown_animations=True,
        # v8: Walk half-cycle detection & mirroring
        walk_half_cycle_detection=True,
        walk_sparse_keyframe_threshold=3,
        # v8: Smart idle dedup
        smart_idle_dedup=True,
        cross_model_idle_dedup=True,
        # v8: Enhanced C1
        periodicity_aware_blending=True,
        rotation_phase_unwrap=True,
        # v8: Auto-loop with velocity zero-crossing priority
        walk_velocity_zero_crossing_weight=3.0,
        walk_tick_snap_durations=(0.65, 0.6667, 0.70),
        # v8: Animation file smart output
        skip_all_empty_files=True,
        # v9: C2 Acceleration Continuity
        transition_zone_c2_hermite=True,
        c2_distortion_limit=0.70,
        # v9: Walk Cycle Full Reconstruction
        walk_full_cycle_reconstruction=True,
        walk_cycle_completeness_threshold=0.15,
        # v9: Deep Idle Dedup
        deep_idle_dedup=True,
        idle_similarity_threshold=0.80,
        idle_static_amplitude_threshold=0.03,
        # v9: Animation File Consolidation
        consolidate_multipart_animations=True,
        # v9: Smart Animation Truncation
        smart_truncate_enabled=True,
        smart_truncate_tail_threshold_rot=0.02,
        smart_truncate_tail_threshold_pos=0.002,
        smart_truncate_min_tail_fraction=0.10,
        # v9: Quintic Global Correction
        global_quintic_correction=True,
        quintic_distortion_limit=0.70,
        # v9: Multi-Texture Extraction
        extract_all_textures=True,
        # v10 NEW: Progressive Global Correction
        progressive_correction_enabled=True,
        progressive_correction_low=0.50,
        progressive_correction_high=0.60,
        progressive_damp_factor=0.70,
        # v10 NEW: Aggressive Idle Dedup
        aggressive_idle_dedup=True,
        idle_amplitude_similarity_threshold=0.25,
        idle_cross_model_consolidation=True,
        # v10 NEW: Enhanced Walk Cycle
        walk_leg_pair_detection=True,
        walk_body_sway_correction=True,
        walk_completion_validation=True,
        walk_min_leg_amplitude=2.0,
        # v10 NEW: Empty Animation File Cleanup
        post_process_empty_cleanup=True,
        consolidate_single_clip_files=True,
        # v10 NEW: Periodic Auto-Trim
        periodic_auto_trim=True,
        periodic_trim_confidence=0.85,
        # v10 NEW: Tighter Loop Validation
        loop_validation_pass=True,
        loop_validation_c0_threshold=0.5,
        loop_validation_c1_threshold=5.0,
        # v11 NEW: Guaranteed 100% C0 Continuity
        final_c0_enforcement=True,
        final_c0_threshold=0.001,
        # v11 NEW: Better Walk Animation Quality
        walk_resample_rate=240.0,
        walk_min_keyframes_per_channel=8,
        walk_phase_closure_check=True,
        # v11 NEW: More Aggressive Idle Dedup
        idle_small_amplitude_merge_threshold=0.5,
        # v11 NEW: Truly-Static Animation Removal
        truly_static_rot_threshold=0.01,
        truly_static_pos_threshold=0.001,
        remove_truly_static_animations=True,
        skip_files_with_only_static=True,
        # v11 NEW: Enhanced Loop Validation
        loop_validation_absolute_c0_threshold=0.05,
        loop_validation_max_iterations=3,
        loop_validation_c1_cubic_correction=True,
        # v14 NEW: Multi-Pass C1 Refinement
        c1_multipass_enabled=True,
        c1_multipass_max_passes=3,
        c1_multipass_threshold_rot=3.0,
        c1_multipass_threshold_pos=0.5,
        # v14 NEW: Adaptive Transition Zone
        adaptive_transition_zone_enabled=True,
        adaptive_transition_zone_max_ratio=0.45,
        # v14 NEW: Improved Bounce-Bridge
        bounce_bridge_cosine_ease=True,
        bounce_bridge_max_severity=2.0,
        # v14 NEW: Periodic Channel Loop Smoothing
        periodic_channel_loop_smoothing=True,
        periodic_channel_detection_threshold=0.6,
        # =============================================
        # v15 NEW: Walk-Aware DP Simplification
        # =============================================
        walk_min_output_keyframes=12,
        walk_dp_epsilon_factor=0.15,
        # v15 NEW: High-Bounce/Sleeping C1 Full Resample
        c1_full_resample_threshold=8.0,
        c1_full_resample_keyframe_density=20,
        high_bounce_transition_zone_max_ratio=0.50,
        long_anim_transition_zone_threshold=2.0,
        long_anim_transition_zone_max_ratio=0.55,
        # v15 NEW: Static Idle for Empty Models
        generate_static_idle_for_empty_models=True,
        # v15 NEW: Evolved/Idle Merge Dedup
        evolved_idle_merge_enabled=True,
        # =============================================
        # v16 NEW: C1 Full Resample Velocity Correction
        # =============================================
        full_resample_velocity_correction=True,
        full_resample_velocity_correction_max_iter=3,
        full_resample_velocity_correction_threshold=2.0,
        # v16 NEW: Walk C1 Correction
        walk_c1_correction_enabled=True,
        walk_c1_correction_ratio=0.15,
        walk_c1_resample_rate=480.0,
        walk_c1_target=1.5,
        # v16 NEW: C1 Quintic Refinement
        c1_quintic_refinement_enabled=True,
        c1_quintic_refinement_threshold=1.5,
        c1_quintic_refinement_zone_ratio=0.10,
        # v16 NEW: Bone Chain Periodicity
        bone_chain_periodicity_enabled=True,
        bone_chain_min_length=3,
        # v16 NEW: Loop Length Auto-Extraction
        spectral_peak_method=True,
        walk_common_periods=(0.6, 0.65, 0.6667, 0.7, 0.75, 0.8, 1.0, 1.2),
        # =============================================
        # v17 NEW: Septic Global Correction
        # =============================================
        septic_global_correction=True,
        septic_distortion_limit=1.0,
        # v17 NEW: Chain-Aware C1 Correction
        chain_aware_c1_correction=True,
        # v17 NEW: Phase-Coherent Duration
        phase_coherent_duration=True,
        early_exit_c1_rot=0.5,
        # v17 NEW: Static Idle Consolidation
        consolidate_static_idles=True,
        # v17 NEW: Walk Body Motion Synthesis
        walk_body_motion_synthesis=True,
        # v17 NEW: Evolved Duration Protection
        evolved_min_duration_ratio=0.60,
        # v17 NEW: Hybrid Period Detection
        hybrid_period_detection=True,
        # v17 NEW: Cross-Model File Consolidation
        cross_model_file_consolidation=True,
        # =============================================
        # v18 NEW: Walk Duration Extension with Replication
        # =============================================
        walk_replicate_on_duration_extend=True,
        walk_periodic_extrapolation=True,
        # v18 NEW: Exact-Duplicate Consolidation
        exact_duplicate_consolidation=True,
        # v18 NEW: Walk-Specific C1 Lightweight Enforcement
        walk_lightweight_c1=True,
        walk_c1_transition_zone_ratio=0.08,
        walk_c1_cosine_bridge=True,
        # v18 NEW: Smart Walk Duration Preservation
        walk_preserve_original_duration=True,
        walk_duration_extend_c0_threshold=1.0,
        # v18 NEW: Improved Naturalness Scoring
        naturalness_density_adjustment=True,
        # v18 NEW: Loop Boundary Smooth Bridge
        loop_smooth_bridge_enabled=True,
        # =============================================
        # v19 NEW: C1 3-Layer Restructured Enforcement
        # =============================================
        peak_preservation_threshold=0.10,
        layer1_c0_target_rot=0.5,
        layer1_c1_target_rot=3.0,
        layer3_zone_ratio=0.375,
        naturalness_method='curvature_smoothness',
        track_amplitude_retention=True,
    )

    # Create animation converter instance
    anim_converter = BBModelAnimationConverter(config)

    # Find all .bbmodel files
    bbmodel_files = []
    for root, dirs, files in os.walk(INPUT_DIR):
        # Filter out skip directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]

        for fname in sorted(files):
            if fname.endswith('.bbmodel'):
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, INPUT_DIR)
                bbmodel_files.append(rel_path)

    # Sort by category then name for consistent processing
    bbmodel_files.sort()

    print(f"\nFound {len(bbmodel_files)} .bbmodel files to process")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"ZIP package: {ZIP_PATH}")
    print(f"v18 Configuration:")
    print(f"  C1 enforcement: ON (septic + cubic Hermite + periodicity-aware + direct velocity adjust)")
    print(f"  C2 continuity:  {'ON' if config.transition_zone_c2_hermite else 'OFF'} (quintic Hermite)")
    print(f"  Quintic correction: {'ON' if config.global_quintic_correction else 'OFF'}")
    print(f"  Walk cycle reconstruction: {'ON' if config.walk_full_cycle_reconstruction else 'OFF'}")
    print(f"  Walk half-cycle mirror: {'ON' if config.walk_half_cycle_detection else 'OFF'}")
    print(f"  Walk-aware DP simplification: ON (min {config.walk_min_output_keyframes} KF, eps factor {config.walk_dp_epsilon_factor})")
    print(f"  Full resample C1: ON (threshold {config.c1_full_resample_threshold} deg/s)")
    print(f"  Deep idle dedup: {'ON' if config.deep_idle_dedup else 'OFF'}")
    print(f"  Evolved/idle merge: {'ON' if config.evolved_idle_merge_enabled else 'OFF'}")
    print(f"  Static idle for empty: {'ON' if config.generate_static_idle_for_empty_models else 'OFF'}")
    print(f"  Smart truncate: {'ON' if config.smart_truncate_enabled else 'OFF'}")
    print(f"  Consolidation: {'ON' if config.consolidate_multipart_animations else 'OFF'}")
    print(f"  Multi-texture: {'ON' if config.extract_all_textures else 'OFF'}")
    print()

    # Statistics tracking
    stats = {
        'total': len(bbmodel_files),
        'geo_ok': 0,
        'geo_fail': 0,
        'anim_ok': 0,
        'anim_fail': 0,
        'anim_no_anim': 0,
        'anim_skipped_truly_empty': 0,
        'anim_meaningless_skipped': 0,
        'tex_ok': 0,
        'tex_fail': 0,
        'total_anims': 0,
        'total_keyframes': 0,
        'total_c0_perfect': 0,
        'total_c1_perfect': 0,
        'total_natural_smooth': 0,
        'total_periodic_enhanced': 0,
        'total_walk_completed': 0,
        # v8 stats
        'total_purged_empty': 0,
        'total_idle_dedup_removed': 0,
        'total_unknown_reclassified': 0,
        'total_walk_half_cycle_mirrored': 0,
        'total_files_skipped_all_empty': 0,
        # v9 NEW stats
        'total_deep_idle_dedup_removed': 0,
        'total_walk_full_cycle_reconstructed': 0,
        'total_smart_truncated': 0,
        'total_consolidated': 0,
        'total_multi_tex_extracted': 0,
        'total_c2_perfect': 0,
        # Common stats
        'quality_scores': [],
        'naturalness_scores': [],
        'periodicity_scores': [],
        'errors': [],
        'warnings': [],
        'output_files': [],
    }

    start_time = time.time()

    for i, rel_path in enumerate(bbmodel_files, 1):
        bbmodel_path = os.path.join(INPUT_DIR, rel_path)
        category = os.path.dirname(rel_path)
        name = os.path.basename(rel_path).replace('.bbmodel', '')
        out_dir = os.path.join(OUTPUT_DIR, category) if category else OUTPUT_DIR

        print(f"  [{i:3d}/{stats['total']}] {category}/{name}...", end=" ", flush=True)

        status_parts = []

        # ---------------------------------------------------------------
        # Step 1: Convert geo.json + extract texture PNG
        # ---------------------------------------------------------------
        try:
            geo_result = geo_converter.convert_bbmodel(bbmodel_path, out_dir)

            if geo_result.get('success'):
                s = geo_result['stats']
                stats['geo_ok'] += 1
                status_parts.append(f"geo+{s['bones']}b")

                # Track texture
                if s.get('has_texture'):
                    stats['tex_ok'] += 1
                    status_parts.append("tex=YES")
                else:
                    stats['tex_fail'] += 1
                    status_parts.append("tex=NO")

                # Track output files
                if geo_result.get('geo_path'):
                    stats['output_files'].append(geo_result['geo_path'])
                if geo_result.get('texture_path'):
                    stats['output_files'].append(geo_result['texture_path'])
            else:
                stats['geo_fail'] += 1
                err = geo_result.get('error', 'unknown error')
                status_parts.append(f"GEO_FAIL: {err}")
                stats['errors'].append(f"{category}/{name}: geo failed: {err}")

        except Exception as e:
            stats['geo_fail'] += 1
            status_parts.append(f"GEO_ERR: {e}")
            stats['errors'].append(f"{category}/{name}: geo exception: {e}")

        # ---------------------------------------------------------------
        # Step 2: Convert animations using v15 converter
        # ---------------------------------------------------------------
        anim_output_path = os.path.join(out_dir, f"{name}.animation.json")
        # Clean up old file if exists
        if os.path.exists(anim_output_path):
            os.remove(anim_output_path)

        try:
            result = anim_converter.convert_file(bbmodel_path, anim_output_path)
            r_stats = result['stats']

            anim_count = r_stats['total_animations']
            kf_count = r_stats['total_keyframes']
            c0_ok = r_stats['c0_perfect_count']
            c1_ok = r_stats['c1_perfect_count']

            # Track truly empty animations that were skipped
            skipped_truly_empty = len(r_stats.get('skipped_empty', []))
            stats['anim_skipped_truly_empty'] += skipped_truly_empty

            # v8: Track stats
            stats['total_purged_empty'] += len(r_stats.get('animations_purged_empty', []))
            stats['total_idle_dedup_removed'] += len(r_stats.get('idle_dedup_removed', []))
            stats['total_unknown_reclassified'] += len(r_stats.get('unknown_reclassified', []))
            stats['total_walk_half_cycle_mirrored'] += len(r_stats.get('walk_half_cycle_mirrored', []))
            if r_stats.get('files_skipped_all_empty', False):
                stats['total_files_skipped_all_empty'] += 1

            # v9: Track new stats
            stats['total_deep_idle_dedup_removed'] += len(r_stats.get('deep_idle_dedup_removed', []))
            stats['total_walk_full_cycle_reconstructed'] += len(r_stats.get('walk_full_cycle_reconstructed', []))
            stats['total_smart_truncated'] += len(r_stats.get('smart_truncated', []))
            stats['total_consolidated'] += len(r_stats.get('consolidated', []))
            stats['total_multi_tex_extracted'] += len(r_stats.get('multi_tex_extracted', []))
            stats['total_c2_perfect'] += r_stats.get('c2_perfect_count', 0)
            # v10: Track new stats
            stats['total_progressive_correction'] = stats.get('total_progressive_correction', 0) + r_stats.get('progressive_correction_used', 0)
            stats['total_idle_aggressive_removed'] = stats.get('total_idle_aggressive_removed', 0) + len(r_stats.get('idle_aggressive_removed', []))
            stats['total_periodic_auto_trimmed'] = stats.get('total_periodic_auto_trimmed', 0) + len(r_stats.get('periodic_auto_trimmed', []))
            stats['total_loop_validation_applied'] = stats.get('total_loop_validation_applied', 0) + r_stats.get('loop_validation_applied', 0)
            stats['total_post_process_empty_removed'] = stats.get('total_post_process_empty_removed', 0) + len(r_stats.get('post_process_empty_removed', []))
            # v11: Track new stats
            stats['total_final_c0_channels_snapped'] = stats.get('total_final_c0_channels_snapped', 0) + r_stats.get('final_c0_channels_snapped', 0)
            stats['total_walk_keyframes_generated'] = stats.get('total_walk_keyframes_generated', 0) + r_stats.get('walk_keyframes_generated', 0)
            stats['total_truly_static_removed'] = stats.get('total_truly_static_removed', 0) + len(r_stats.get('truly_static_removed', []))

            stats['total_anims'] += anim_count
            stats['total_keyframes'] += kf_count
            stats['total_c0_perfect'] += c0_ok
            stats['total_c1_perfect'] += c1_ok

            if anim_count == 0:
                stats['anim_no_anim'] += 1
                if skipped_truly_empty > 0:
                    status_parts.append(f"no_anim ({skipped_truly_empty} empty skipped)")
                else:
                    status_parts.append("no_anim")
            else:
                stats['anim_ok'] += 1
                avg_score = sum(
                    qr.quality_score for qr in result['quality_reports'].values()
                ) / max(anim_count, 1)
                stats['quality_scores'].extend(
                    qr.quality_score for qr in result['quality_reports'].values()
                )

                # Track naturalness, periodicity, and naturally smooth animations
                for qr in result['quality_reports'].values():
                    stats['naturalness_scores'].append(qr.naturalness_score)
                    stats['periodicity_scores'].append(qr.periodicity_score)
                    if qr.c1_method == 'none':
                        stats['total_natural_smooth'] += 1
                    if qr.periodic_enhanced:
                        stats['total_periodic_enhanced'] += 1

                status_parts.append(f"anims={anim_count}")
                status_parts.append(f"kf={kf_count}")
                status_parts.append(f"C0={c0_ok}/{anim_count}")
                status_parts.append(f"C1={c1_ok}/{anim_count}")
                status_parts.append(f"score={avg_score:.0f}")

                # Don't track output file if not written
                if os.path.exists(anim_output_path):
                    stats['output_files'].append(anim_output_path)

            # Collect warnings/errors
            for anim_name, qr in result['quality_reports'].items():
                if qr.errors:
                    stats['errors'].append(
                        f"{category}/{name}/{anim_name}: " + "; ".join(qr.errors)
                    )
                if qr.warnings:
                    stats['warnings'].append(
                        f"{category}/{name}/{anim_name}: " + "; ".join(qr.warnings)
                    )

        except Exception as e:
            stats['anim_fail'] += 1
            status_parts.append(f"ANIM_ERR: {e}")
            stats['errors'].append(f"{category}/{name}: anim exception: {e}")

        print(" | ".join(status_parts))

    elapsed = time.time() - start_time

    # ---------------------------------------------------------------
    # Step 3: Create ZIP package
    # ---------------------------------------------------------------
    print(f"\n  Creating ZIP package...")
    _create_zip(stats['output_files'], OUTPUT_DIR, ZIP_PATH)

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print()
    print("=" * 70)
    print("  BATCH CONVERSION SUMMARY (v18)")
    print("=" * 70)
    print(f"  Total .bbmodel files:    {stats['total']}")
    print()
    print(f"  --- Geometry ---")
    print(f"  Geo converted OK:        {stats['geo_ok']}")
    print(f"  Geo failed:              {stats['geo_fail']}")
    print(f"  Textures extracted:      {stats['tex_ok']}")
    print()
    print(f"  --- Animations ---")
    print(f"  Models with animations:  {stats['anim_ok']}")
    print(f"  Static models (no anim): {stats['anim_no_anim']}")
    print(f"  Animation failures:      {stats['anim_fail']}")
    print(f"  Truly empty skipped:     {stats['anim_skipped_truly_empty']}")
    print(f"  Total animations:        {stats['total_anims']}")
    print(f"  Total keyframes:         {stats['total_keyframes']:,}")
    print(f"  C0 perfect:              {stats['total_c0_perfect']}/{stats['total_anims']} "
          f"({100*stats['total_c0_perfect']/max(stats['total_anims'],1):.1f}%)")
    print(f"  C1 good (P90):           {stats['total_c1_perfect']}/{stats['total_anims']} "
          f"({100*stats['total_c1_perfect']/max(stats['total_anims'],1):.1f}%)")
    print(f"  C2 perfect:              {stats['total_c2_perfect']}/{stats['total_anims']} "
          f"({100*stats['total_c2_perfect']/max(stats['total_anims'],1):.1f}%)")
    print(f"  Naturally smooth:        {stats['total_natural_smooth']} "
          f"({100*stats['total_natural_smooth']/max(stats['total_anims'],1):.1f}% no C1 enforcement needed)")
    print(f"  Periodic enhanced:       {stats['total_periodic_enhanced']} "
          f"({100*stats['total_periodic_enhanced']/max(stats['total_anims'],1):.1f}% walk/cycle completion)")
    print()
    print(f"  --- v16/v17/v18 Improvements ---")
    print(f"  Walk keyframes generated:      {stats.get('total_walk_keyframes_generated', 0)}")
    print(f"  Walk-aware DP simplification:  ON (min 12 KF per walk channel)")
    print(f"  Full resample C1 enforcement:  ON (all loop anims)")
    print(f"  --- v11 Improvements ---")
    print(f"  Final C0 channels snapped:     {stats.get('total_final_c0_channels_snapped', 0)}")
    print(f"  Truly-static removed:          {stats.get('total_truly_static_removed', 0)}")
    print(f"  --- v10 Improvements ---")
    print(f"  Progressive corrections:       {stats.get('total_progressive_correction', 0)}")
    print(f"  Aggressive idle removed:       {stats.get('total_idle_aggressive_removed', 0)}")
    print(f"  Periodic auto-trimmed:         {stats.get('total_periodic_auto_trimmed', 0)}")
    print(f"  Loop validation applied:       {stats.get('total_loop_validation_applied', 0)}")
    print(f"  Post-process empty removed:    {stats.get('total_post_process_empty_removed', 0)}")
    print(f"  --- v9 Improvements ---")
    print(f"  Walk full-cycle reconstructed: {stats['total_walk_full_cycle_reconstructed']}")
    print(f"  Deep idle dedup removed:       {stats['total_deep_idle_dedup_removed']}")
    print(f"  Smart truncated:               {stats['total_smart_truncated']}")
    print(f"  Consolidated animations:       {stats['total_consolidated']}")
    print(f"  Multi-texture extracted:       {stats['total_multi_tex_extracted']}")
    print(f"  Purged empty animations:       {stats['total_purged_empty']}")
    print(f"  Idle dedup removed:            {stats['total_idle_dedup_removed']}")
    print(f"  Unknown reclassified:          {stats['total_unknown_reclassified']}")
    print(f"  Walk half-cycle mirrored:      {stats['total_walk_half_cycle_mirrored']}")
    print(f"  Files skipped (all empty):     {stats['total_files_skipped_all_empty']}")

    if stats['quality_scores']:
        sorted_scores = sorted(stats['quality_scores'])
        avg = sum(sorted_scores) / len(sorted_scores)
        p50 = sorted_scores[len(sorted_scores) // 2]
        p90_idx = int(len(sorted_scores) * 0.9)
        p90 = sorted_scores[min(p90_idx, len(sorted_scores) - 1)]
        p99_idx = int(len(sorted_scores) * 0.99)
        p99 = sorted_scores[min(p99_idx, len(sorted_scores) - 1)]
        perfect = sum(1 for s in sorted_scores if s >= 100.0)
        print(f"  Quality scores:")
        print(f"    Average:  {avg:.1f}")
        print(f"    P50:      {p50:.1f}")
        print(f"    P90:      {p90:.1f}")
        print(f"    P99:      {p99:.1f}")
        print(f"    Perfect:  {perfect}/{len(sorted_scores)} ({100*perfect/len(sorted_scores):.1f}%)")

    if stats['naturalness_scores']:
        avg_naturalness = sum(stats['naturalness_scores']) / len(stats['naturalness_scores'])
        print(f"  Naturalness scores:")
        print(f"    Average:  {avg_naturalness:.3f}")
        smooth_count = sum(1 for n in stats['naturalness_scores'] if n >= 0.9)
        print(f"    Smooth (>=0.9):  {smooth_count}/{len(stats['naturalness_scores'])} "
              f"({100*smooth_count/len(stats['naturalness_scores']):.1f}%)")

    if stats['periodicity_scores']:
        avg_periodicity = sum(stats['periodicity_scores']) / len(stats['periodicity_scores'])
        periodic_count = sum(1 for p in stats['periodicity_scores'] if p > 0.5)
        print(f"  Periodicity scores:")
        print(f"    Average:  {avg_periodicity:.3f}")
        print(f"    Periodic (>0.5):  {periodic_count}/{len(stats['periodicity_scores'])} "
              f"({100*periodic_count/len(stats['periodicity_scores']):.1f}%)")

    print()
    print(f"  --- Output ---")
    print(f"  Output directory:        {OUTPUT_DIR}")
    print(f"  ZIP package:             {ZIP_PATH}")
    zip_size = os.path.getsize(ZIP_PATH) if os.path.exists(ZIP_PATH) else 0
    print(f"  ZIP size:                {zip_size / 1024:.1f} KB")
    print(f"  Total output files:      {len(stats['output_files'])}")
    print()
    print(f"  --- Diagnostics ---")
    print(f"  Warnings:                {len(stats['warnings'])}")
    print(f"  Errors:                  {len(stats['errors'])}")
    print(f"  Elapsed time:            {elapsed:.1f}s")

    if stats['errors']:
        print(f"\n  Errors:")
        for e in stats['errors'][:10]:
            print(f"    X {e}")
        if len(stats['errors']) > 10:
            print(f"    ... and {len(stats['errors']) - 10} more")

    if stats['warnings']:
        print(f"\n  Top warnings:")
        for w in stats['warnings'][:10]:
            print(f"    ! {w}")
        if len(stats['warnings']) > 10:
            print(f"    ... and {len(stats['warnings']) - 10} more")

    print()
    print("=" * 70)
    print("  DONE - Batch Convert All (v18)")
    print("  Septic Correction | Direct Velocity Adjust | Chain-Aware C1")
    print("  Phase-Coherent Duration | Static Idle Consolidation | Walk Body Synthesis")
    print("  Evolved Duration Protection | Hybrid Period Detection | Cross-Model Dedup")
    print("  Output:", OUTPUT_DIR)
    print("  ZIP:", ZIP_PATH)
    print("=" * 70)

    # Return success if no critical errors
    critical_errors = [e for e in stats['errors'] if 'exception' in e.lower() or 'failed' in e.lower()]
    sys.exit(0 if len(critical_errors) == 0 else 1)


def _create_zip(output_files: list, base_dir: str, zip_path: str) -> None:
    """Create a ZIP package containing all output files, organized by category.

    Args:
        output_files: List of absolute file paths to include
        base_dir: Base directory for computing relative paths
        zip_path: Path for the output ZIP file
    """
    os.makedirs(os.path.dirname(zip_path) if os.path.dirname(zip_path) else '.', exist_ok=True)

    # Organize files by category
    geo_files = []
    anim_files = []
    tex_files = []
    other_files = []

    for fpath in output_files:
        if not os.path.exists(fpath):
            continue
        if fpath.endswith('.geo.json'):
            geo_files.append(fpath)
        elif fpath.endswith('.animation.json'):
            anim_files.append(fpath)
        elif fpath.endswith('.png'):
            tex_files.append(fpath)
        else:
            other_files.append(fpath)

    count = 0
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add geo files first
        for fpath in sorted(geo_files):
            try:
                rel = os.path.relpath(fpath, base_dir)
            except ValueError:
                rel = os.path.basename(fpath)
            zf.write(fpath, rel)
            count += 1

        # Add animation files
        for fpath in sorted(anim_files):
            try:
                rel = os.path.relpath(fpath, base_dir)
            except ValueError:
                rel = os.path.basename(fpath)
            zf.write(fpath, rel)
            count += 1

        # Add texture files
        for fpath in sorted(tex_files):
            try:
                rel = os.path.relpath(fpath, base_dir)
            except ValueError:
                rel = os.path.basename(fpath)
            zf.write(fpath, rel)
            count += 1

        # Add any other files
        for fpath in sorted(other_files):
            try:
                rel = os.path.relpath(fpath, base_dir)
            except ValueError:
                rel = os.path.basename(fpath)
            zf.write(fpath, rel)
            count += 1

    zip_size = os.path.getsize(zip_path) if os.path.exists(zip_path) else 0
    print(f"  ZIP: {count} files ({len(geo_files)} geo, {len(anim_files)} anim, {len(tex_files)} tex), "
          f"{zip_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
