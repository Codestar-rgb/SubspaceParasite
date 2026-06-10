#!/usr/bin/env python3
"""
VenkrolSIV Animation Generator - Comprehensive Animation Converter for VenkrolSIV
==================================================================================
Parses the original MC 1.12.2 Java animation code from ModelVenkrolSIV.java and
generates high-quality GeckoLib 1.20.1 animation files for each entity state.

Animation States:
  1. idle     - parasiteStatus >= 0 (active: body sway + tentacle oscillations)
  2. dormant  - parasiteStatus == 3 (dead/dormant: ~25x smaller amplitudes)

Model Structure:
  - 205 bones total, 204 elements
  - Root bone: pivot [0,24,0], rotation [180, 180, 180] deg
  - Main body chain: mainbody -> body1..body13
  - 3 tentacle hubs: ten_center, ten_center_1, ten_center_2
  - 4 dorsal tentacle groups (jointDBR*, jointDBL*, jointDFR*, jointDFL*), joints 1-5
  - 4 middle tentacle groups (jointMB*, jointML*, jointMR*, jointMF*), joints 1-5
  - 4 front tentacle tip groups (taclejointBL1-8, BR1-8, FL1-8, FR1-8)
  - Decorative panels: dec, dec_1..dec_7, decor, decor_1..decor_15
  - Core: corecccc -> core2 -> core3 -> core4, core5 -> core6 -> core7

Key Conversions (same as heblu):
  - M_MODEL = diag(1, -1, -1): rx stays, ry -> -ry, rz -> -rz for rotation
  - Position: ox stays, oy -> -oy, oz -> -oz
  - Radians to degrees for animation output
  - Time in seconds (20 ticks per second in MC)

Quality Features (inherited from heblu):
  - Period-aware duration for seamless loop matching
  - Higher sampling rate (120 fps) for smooth motion
  - Douglas-Peucker simplification for compact keyframes (dp_epsilon=0.03)
  - Start/end value matching for perfect loop continuity
  - Loop boundary enrichment for smooth catmullrom
  - 3D merge-and-resimplify for consistent axis keyframes

CRITICAL: The venkrolSIV model has a different root bone rotation [180, 180, 180]
instead of heblu's [180, 0, 0]. The bbmodel_generator.py handles this correctly
via _convert_rotation_to_bbmodel using scipy Rotation.
"""

import json
import math
import os
import sys
from typing import Dict, List, Optional, Tuple

# ============================================================================
# Import shared utilities from heblu_animation_generator
# ============================================================================
# These functions are identical across all animation generators:
#   - sample_animation: 120fps sampling, M_MODEL conversion, DP simplification
#   - simplify_keyframes: Douglas-Peucker line simplification
#   - enforce_loop_continuity: Smooth loop boundary blending
#   - enrich_loop_boundary: Keyframe density enrichment near loop point
#   - build_animation_json: GeckoLib animation JSON generation
#   - _merge_and_resimplify_axes: 3D merge-and-resimplify for axis keyframes
#   - analyze_dominant_periods: Period analysis for loop duration selection
#   - rad_to_deg: Radians to degrees conversion
#   - _channel_to_axis: Channel name to axis name mapping
#   - convert_rotation / convert_position: M_MODEL coordinate conversion

from heblu_animation_generator import (
    sample_animation,
    simplify_keyframes,
    enforce_loop_continuity,
    enrich_loop_boundary,
    build_animation_json,
    _merge_and_resimplify_axes,
    analyze_dominant_periods,
    rad_to_deg,
    _channel_to_axis,
    convert_rotation,
    convert_position,
)


# ============================================================================
# Constants
# ============================================================================
TICKS_PER_SECOND = 20.0
RAD_TO_DEG = 180.0 / math.pi

# Shared quality parameters (matching heblu)
SAMPLES_PER_SECOND = 180.0  # V3: Higher for smoother tentacle motion
DP_EPSILON = 0.02           # V3: Lower for better curve preservation
BOUNDARY_FRACTION = 0.15    # V3: More aggressive boundary enrichment

# Known good animation durations from previous analysis.
# These are the durations where all oscillation channels complete near-integer
# cycles for seamless looping. If not specified, analyze_dominant_periods
# will compute them automatically.
KNOWN_ANIM_DURATIONS = {
    "idle": 6.9813,     # Optimal loop duration matching dominant oscillation periods
    "dormant": 6.9813,  # Same duration - body sway frequencies are similar
}


# ============================================================================
# VenkrolSIV-Specific Animation State Evaluators
# ============================================================================

def eval_idle(t_seconds: float) -> Dict[str, Dict[str, float]]:
    """Evaluate animation for active state (parasiteStatus >= 0).

    Returns dict of bone_name -> {rx, ry, rz, ox, oy, oz} in MC 1.12.2 space.
    All values in radians / MC position units.

    The Java source (ModelVenkrolSIV.java func_78087_a) does:
      1. Reset ALL joints to 0 (field_78795_f=rx, field_78796_g=ry, field_78808_h=rz)
      2. If parasiteStatus >= 0 (active):
         a. Body sway: f1 = -0.3 * sin(ageInTicks * 0.051688) * 0.011
                       f2 = -0.6 * sin(ageInTicks * 0.013515) * 0.011
         b. Dorsal legs (larger oscillation):
                       f1 = -0.3 * cos(ageInTicks * 0.11688) * 0.31
                       f2 = -0.6 * cos(ageInTicks * 0.093515) * 0.273
                       f3 =  0.3 * cos(ageInTicks * 0.1) * 0.29
                       f4 =  0.6 * cos(ageInTicks * 0.11) * 0.28
         c. Middle legs (even larger oscillation):
                       f1 = -0.3 * cos(ageInTicks * 0.11688) * 0.41
                       f2 = -0.6 * cos(ageInTicks * 0.093515) * 0.373
                       f3 =  0.3 * cos(ageInTicks * 0.1) * 0.39
                       f4 =  0.6 * cos(ageInTicks * 0.11) * 0.38
         d. Tentacle tips (smallest oscillation):
                       f1 = -0.3 * cos(ageInTicks * 0.0711688) * 0.11
                       f2 = -0.6 * cos(ageInTicks * 0.083515) * 0.143
                       f3 =  0.3 * cos(ageInTicks * 0.061) * 0.139
                       f4 =  0.6 * cos(ageInTicks * 0.0711) * 0.128

    IMPORTANT: The Java code uses sin() for body sway (initial f1/f2) and
    cos() for all leg/tentacle joints. The body sway uses different
    multipliers (0.011) compared to the leg oscillations (0.273-0.41).
    """
    age_in_ticks = t_seconds * TICKS_PER_SECOND
    bones = {}

    # === A. Body Sway (body1-5) ===
    # Java: f1 = -0.3f * MathHelper.sin(ageInTicks * 0.051688f) * 0.011f
    #        f2 = -0.6f * MathHelper.sin(ageInTicks * 0.013515f) * 0.011f
    #        body1-5.rx = f1 (field_78795_f)
    #        body1-5.rz = f2 (field_78808_h)
    f1_body = -0.3 * math.sin(age_in_ticks * 0.051688) * 0.011
    f2_body = -0.6 * math.sin(age_in_ticks * 0.013515) * 0.011
    for name in ['body1', 'body2', 'body3', 'body4', 'body5']:
        bones[name] = {'rx': f1_body, 'rz': f2_body}

    # === B. Dorsal Tentacle Joints ===
    # Java: f1 = -0.3f * cos(ageInTicks * 0.11688f) * 0.31f
    #        f2 = -0.6f * cos(ageInTicks * 0.093515f) * 0.273f
    #        f3 =  0.3f * cos(ageInTicks * 0.1f) * 0.29f
    #        f4 =  0.6f * cos(ageInTicks * 0.11f) * 0.28f
    f1_d = -0.3 * math.cos(age_in_ticks * 0.11688) * 0.31
    f2_d = -0.6 * math.cos(age_in_ticks * 0.093515) * 0.273
    f3_d = 0.3 * math.cos(age_in_ticks * 0.1) * 0.29
    f4_d = 0.6 * math.cos(age_in_ticks * 0.11) * 0.28

    # DBL group (Dorsal Back Left)
    # Java: jointDBL1.rx = -1.0f * f3;  jointDBL2.ry = f3;  jointDBL3.ry = f3;  jointDBL4.ry = 0.0f
    bones['jointDBL1'] = {'rx': -f3_d}
    bones['jointDBL2'] = {'ry': f3_d}
    bones['jointDBL3'] = {'ry': f3_d}
    bones['jointDBL4'] = {'ry': 0.0}
    # jointDBL5 is not animated (stays at reset value 0)

    # DBR group (Dorsal Back Right)
    # Java: jointDBR1.rx = f3;  jointDBR2.ry = -1.0f * f3;  jointDBR3.ry = f3;  jointDBR4.ry = 0.0f
    bones['jointDBR1'] = {'rx': f3_d}
    bones['jointDBR2'] = {'ry': -f3_d}
    bones['jointDBR3'] = {'ry': f3_d}
    bones['jointDBR4'] = {'ry': 0.0}

    # DFL group (Dorsal Front Left)
    # Java: jointDFL1.rx = -1.0f * f2;  jointDFL2.ry = f2;  jointDFL3.ry = f1;  jointDFL4.ry = 0.0f
    bones['jointDFL1'] = {'rx': -f2_d}
    bones['jointDFL2'] = {'ry': f2_d}
    bones['jointDFL3'] = {'ry': f1_d}
    bones['jointDFL4'] = {'ry': 0.0}

    # DFR group (Dorsal Front Right)
    # Java: jointDFR1.rx = f1;  jointDFR2.ry = -1.0f * f1;  jointDFR3.ry = f2;  jointDFR4.ry = 0.0f
    bones['jointDFR1'] = {'rx': f1_d}
    bones['jointDFR2'] = {'ry': -f1_d}
    bones['jointDFR3'] = {'ry': f2_d}
    bones['jointDFR4'] = {'ry': 0.0}

    # === C. Middle Tentacle Joints ===
    # Java: f1 = -0.3f * cos(ageInTicks * 0.11688f) * 0.41f  (REASSIGNED - larger amplitude)
    #        f2 = -0.6f * cos(ageInTicks * 0.093515f) * 0.373f
    #        f3 =  0.3f * cos(ageInTicks * 0.1f) * 0.39f
    #        f4 =  0.6f * cos(ageInTicks * 0.11f) * 0.38f
    f1_m = -0.3 * math.cos(age_in_ticks * 0.11688) * 0.41
    f2_m = -0.6 * math.cos(age_in_ticks * 0.093515) * 0.373
    f3_m = 0.3 * math.cos(age_in_ticks * 0.1) * 0.39
    f4_m = 0.6 * math.cos(age_in_ticks * 0.11) * 0.38

    # ML group (Middle Left)
    # Java: jointML1.rx = -1.0f * f1;  jointML2.ry = 0.0f;  jointML3.ry = -1.0f * f2;  jointML4.ry = 0.0f
    bones['jointML1'] = {'rx': -f1_m}
    bones['jointML2'] = {'ry': 0.0}
    bones['jointML3'] = {'ry': -f2_m}
    bones['jointML4'] = {'ry': 0.0}

    # MR group (Middle Right)
    # Java: jointMR1.rx = f1;  jointMR2.ry = 0.0f;  jointMR3.ry = f2;  jointMR4.ry = 0.0f
    bones['jointMR1'] = {'rx': f1_m}
    bones['jointMR2'] = {'ry': 0.0}
    bones['jointMR3'] = {'ry': f2_m}
    bones['jointMR4'] = {'ry': 0.0}

    # MF group (Middle Front)
    # Java: jointMF1.rx = f3;  jointMF2.ry = 0.0f;  jointMF3.ry = f4;  jointMF4.ry = 0.0f
    bones['jointMF1'] = {'rx': f3_m}
    bones['jointMF2'] = {'ry': 0.0}
    bones['jointMF3'] = {'ry': f4_m}
    bones['jointMF4'] = {'ry': 0.0}

    # MB group (Middle Back)
    # Java: jointMB1.rx = f1;  jointMB2.ry = 0.0f;  jointMB3.ry = f2;  jointMB4.ry = 0.0f
    bones['jointMB1'] = {'rx': f1_m}
    bones['jointMB2'] = {'ry': 0.0}
    bones['jointMB3'] = {'ry': f2_m}
    bones['jointMB4'] = {'ry': 0.0}

    # === D. Tentacle Tip Joints (taclejoints) ===
    # Java: f1 = -0.3f * cos(ageInTicks * 0.0711688f) * 0.11f
    #        f2 = -0.6f * cos(ageInTicks * 0.083515f) * 0.143f
    #        f3 =  0.3f * cos(ageInTicks * 0.061f) * 0.139f
    #        f4 =  0.6f * cos(ageInTicks * 0.0711f) * 0.128f
    # All taclejoint bones get rx values from f1-f4 in various patterns.
    f1_t = -0.3 * math.cos(age_in_ticks * 0.0711688) * 0.11
    f2_t = -0.6 * math.cos(age_in_ticks * 0.083515) * 0.143
    f3_t = 0.3 * math.cos(age_in_ticks * 0.061) * 0.139
    f4_t = 0.6 * math.cos(age_in_ticks * 0.0711) * 0.128

    # BL tips: f1, f4, f2, f1, f2, f4, f2, f1 (all .rx)
    bl_pattern = [f1_t, f4_t, f2_t, f1_t, f2_t, f4_t, f2_t, f1_t]
    for i, val in enumerate(bl_pattern, 1):
        bones[f'taclejointBL{i}'] = {'rx': val}

    # BR tips: f2, f3, f2, f1, f2, f3, f2, f1 (all .rx)
    br_pattern = [f2_t, f3_t, f2_t, f1_t, f2_t, f3_t, f2_t, f1_t]
    for i, val in enumerate(br_pattern, 1):
        bones[f'taclejointBR{i}'] = {'rx': val}

    # FL tips: f3, f4, f3, f1, f3, f4, f3, f1 (all .rx)
    fl_pattern = [f3_t, f4_t, f3_t, f1_t, f3_t, f4_t, f3_t, f1_t]
    for i, val in enumerate(fl_pattern, 1):
        bones[f'taclejointFL{i}'] = {'rx': val}

    # FR tips: f4, f1, f3, f2, f4, f1, f3, f2 (all .rx)
    fr_pattern = [f4_t, f1_t, f3_t, f2_t, f4_t, f1_t, f3_t, f2_t]
    for i, val in enumerate(fr_pattern, 1):
        bones[f'taclejointFR{i}'] = {'rx': val}

    return bones


def eval_dormant(t_seconds: float) -> Dict[str, Dict[str, float]]:
    """Evaluate animation for dead/dormant state (parasiteStatus == 3).

    Same structure as idle but amplitudes are ~25x smaller.
    The Java source:
      - f1 = 0.3f * cos(ageInTicks * 0.051688f) * 0.0011f  (body sway, note: positive, not negative)
      - f2 = -0.6f * cos(ageInTicks * 0.013515f) * 0.0011f
      - f3 = 0.3f * cos(ageInTicks * 0.1f) * 0.25f          (dorsal joints)
    Only body sway and joint oscillations, no tentacle tips animated.
    """
    age_in_ticks = t_seconds * TICKS_PER_SECOND
    bones = {}

    # === Body Sway (body1-5) - ~25x smaller amplitude ===
    # Java: f1 = 0.3f * cos(ageInTicks * 0.051688f) * 0.0011f  (NOTE: positive 0.3, not -0.3)
    #        f2 = -0.6f * cos(ageInTicks * 0.013515f) * 0.0011f
    #        body1-5.rx = f1;  body1-5.rz = f2
    f1_body = 0.3 * math.cos(age_in_ticks * 0.051688) * 0.0011
    f2_body = -0.6 * math.cos(age_in_ticks * 0.013515) * 0.0011
    for name in ['body1', 'body2', 'body3', 'body4', 'body5']:
        bones[name] = {'rx': f1_body, 'rz': f2_body}

    # === Dorsal Tentacle Joints - much smaller amplitude ===
    # Java: f3 = 0.3f * cos(ageInTicks * 0.1f) * 0.25f
    f3_d = 0.3 * math.cos(age_in_ticks * 0.1) * 0.25

    # DBL group
    bones['jointDBL1'] = {'rx': -f3_d}
    bones['jointDBL2'] = {'ry': f3_d}
    bones['jointDBL3'] = {'ry': f3_d}
    bones['jointDBL4'] = {'ry': 0.0}

    # DBR group
    bones['jointDBR1'] = {'rx': f3_d}
    bones['jointDBR2'] = {'ry': -f3_d}
    bones['jointDBR3'] = {'ry': f3_d}
    bones['jointDBR4'] = {'ry': 0.0}

    # DFL group - simplified for dormant (same as DBL pattern)
    bones['jointDFL1'] = {'rx': -f3_d}
    bones['jointDFL2'] = {'ry': f3_d}
    bones['jointDFL3'] = {'ry': f3_d}
    bones['jointDFL4'] = {'ry': 0.0}

    # DFR group - simplified for dormant (same as DBR pattern)
    bones['jointDFR1'] = {'rx': f3_d}
    bones['jointDFR2'] = {'ry': -f3_d}
    bones['jointDFR3'] = {'ry': f3_d}
    bones['jointDFR4'] = {'ry': 0.0}

    # === Middle Tentacle Joints - much smaller amplitude ===
    # Dormant: all use same 0.25 multiplier (no separate f1/f2/f3/f4 scaling)
    f1_m = -0.3 * math.cos(age_in_ticks * 0.11688) * 0.25
    f2_m = -0.6 * math.cos(age_in_ticks * 0.093515) * 0.25
    f3_m = 0.3 * math.cos(age_in_ticks * 0.1) * 0.25
    f4_m = 0.6 * math.cos(age_in_ticks * 0.11) * 0.25

    # ML group
    bones['jointML1'] = {'rx': -f1_m}
    bones['jointML2'] = {'ry': 0.0}
    bones['jointML3'] = {'ry': -f2_m}
    bones['jointML4'] = {'ry': 0.0}

    # MR group
    bones['jointMR1'] = {'rx': f1_m}
    bones['jointMR2'] = {'ry': 0.0}
    bones['jointMR3'] = {'ry': f2_m}
    bones['jointMR4'] = {'ry': 0.0}

    # MF group
    bones['jointMF1'] = {'rx': f3_m}
    bones['jointMF2'] = {'ry': 0.0}
    bones['jointMF3'] = {'ry': f4_m}
    bones['jointMF4'] = {'ry': 0.0}

    # MB group
    bones['jointMB1'] = {'rx': f1_m}
    bones['jointMB2'] = {'ry': 0.0}
    bones['jointMB3'] = {'ry': f2_m}
    bones['jointMB4'] = {'ry': 0.0}

    # No tentacle tips in dormant state (they stay at their reset values of 0)

    return bones


# ============================================================================
# Generate All Animations
# ============================================================================

def generate_all_animations() -> dict:
    """Generate all animation states and return the complete .animation.json.

    Pipeline per animation (same as heblu):
      1. analyze_dominant_periods → find optimal loop duration
      2. sample_animation → 120fps sampling + DP simplification
      3. enrich_loop_boundary → add keyframes near loop point for smooth catmullrom
      4. enforce_loop_continuity → smooth blend to ensure first/last values match
      5. build_animation_json → GeckoLib format output with 3D merge-and-resimplify
    """
    animations = {}

    # --- IDLE animation (active state) ---
    print("  Generating idle animation (active state)...")
    idle_duration = KNOWN_ANIM_DURATIONS.get("idle") or analyze_dominant_periods(eval_idle)
    print(f"    Loop duration: {idle_duration}s")

    idle_data = sample_animation(
        eval_idle,
        duration=idle_duration,
        samples_per_second=180.0,   # V3: Higher sampling for tentacle detail
        dp_epsilon=0.02,            # V3: Lower epsilon for smoother catmullrom
    )
    # CRITICAL ORDER: Enrich BEFORE enforcing loop continuity!
    # enrich_loop_boundary adds raw keyframes from eval_func; if we enforce
    # loop continuity first, the enriched raw values override the blend.
    # V5: enrich_loop_boundary is now a no-op (replaced by crossfade)
    idle_data = enrich_loop_boundary(idle_data, eval_idle, idle_duration,
                                     boundary_fraction=0.15)
    idle_data = enforce_loop_continuity(idle_data, idle_duration, eval_func=eval_idle)

    animations["animation.venkrolSIV.idle"] = build_animation_json(
        "animation.venkrolSIV.idle", "loop", idle_data, idle_duration
    )
    idle_bone_count = len(animations["animation.venkrolSIV.idle"]["bones"])
    print(f"    Bones: {idle_bone_count}, Duration: {idle_duration}s")

    # --- DORMANT animation (dead state) ---
    print("  Generating dormant animation (dead state)...")
    dormant_duration = KNOWN_ANIM_DURATIONS.get("dormant") or analyze_dominant_periods(eval_dormant)
    print(f"    Loop duration: {dormant_duration}s")

    dormant_data = sample_animation(
        eval_dormant,
        duration=dormant_duration,
        samples_per_second=180.0,   # V3: Higher sampling for tentacle detail
        dp_epsilon=0.02,            # V3: Lower epsilon for smoother catmullrom
    )
    dormant_data = enrich_loop_boundary(dormant_data, eval_dormant, dormant_duration,
                                        boundary_fraction=0.15)
    dormant_data = enforce_loop_continuity(dormant_data, dormant_duration, eval_func=eval_dormant)

    animations["animation.venkrolSIV.dormant"] = build_animation_json(
        "animation.venkrolSIV.dormant", "loop", dormant_data, dormant_duration
    )
    dormant_bone_count = len(animations["animation.venkrolSIV.dormant"]["bones"])
    print(f"    Bones: {dormant_bone_count}, Duration: {dormant_duration}s")

    return {
        "format_version": "1.8.0",
        "animations": animations
    }


# ============================================================================
# Inject Animations into Existing .bbmodel
# ============================================================================

def inject_animations_into_bbmodel(bbmodel_path: str, anim_json: dict,
                                   output_path: str) -> None:
    """Read an existing .bbmodel file, replace its animations, and save.

    This preserves the existing model structure (elements, groups, outliner,
    textures) and only replaces the "animations" array.

    The bbmodel_generator.py's _build_animations() function converts from
    our GeckoLib animation.json format to the bbmodel animation format,
    including proper scipy Rotation conversion for the root bone [180,180,180].

    Args:
        bbmodel_path: Path to the existing .bbmodel file
        anim_json: Animation JSON dict (from generate_all_animations)
        output_path: Path to save the updated .bbmodel file
    """
    # Import BBModelGenerator for animation format conversion
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(project_root, 'converter'))
    from bbmodel_generator import BBModelGenerator

    # Read existing .bbmodel
    with open(bbmodel_path, 'r', encoding='utf-8') as f:
        bbmodel = json.load(f)

    # Use BBModelGenerator to convert animation JSON to bbmodel format
    gen = BBModelGenerator()
    new_animations = gen._build_animations(anim_json)

    # Replace the animations in the existing bbmodel
    bbmodel['animations'] = new_animations

    # Update modification time
    import time as _time
    bbmodel['meta']['modification_time'] = int(_time.time())

    # Save to output path
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(bbmodel, f, indent=2, ensure_ascii=False)

    print(f"  Saved .bbmodel to: {output_path}")
    print(f"  .bbmodel size: {os.path.getsize(output_path):,} bytes")
    print(f"  Elements: {len(bbmodel.get('elements', []))}")
    print(f"  Animations: {len(bbmodel.get('animations', []))}")


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    print("=" * 70)
    print("  VenkrolSIV Animation Generator")
    print("  MC 1.12.2 -> GeckoLib 1.20.1 Animation Conversion")
    print("=" * 70)
    print()

    # Determine project paths
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bbmodel_source = os.path.join(project_root, "MROLF-TGNBF", "deterrent", "venkrolSIV.bbmodel")
    bbmodel_output = os.path.join(project_root, "MROLF-TGNBF", "derived", "venkrolSIV.bbmodel")
    anim_json_path = os.path.join(project_root, "db", "venkrolSIV.animation.json")

    # Generate all animations
    anim_json = generate_all_animations()

    # Save standalone animation JSON
    anim_json_str = json.dumps(anim_json, indent=2, ensure_ascii=False)
    os.makedirs(os.path.dirname(anim_json_path), exist_ok=True)
    with open(anim_json_path, 'w', encoding='utf-8') as f:
        f.write(anim_json_str)
    print(f"\n  Saved animation JSON to: {anim_json_path}")

    # Statistics
    total_size = len(anim_json_str)
    print(f"\n  Total animation JSON size: {total_size:,} bytes")
    for anim_name, anim_data in anim_json.get('animations', {}).items():
        n_bones = len(anim_data.get('bones', {}))
        total_axis_channels = 0
        total_time_keyframes = 0
        for bone_data in anim_data.get('bones', {}).values():
            for key, channel_data in bone_data.items():
                if key.startswith('_'):
                    continue
                if isinstance(channel_data, dict):
                    total_axis_channels += 1
                    total_time_keyframes += len(channel_data)
        print(f"    {anim_name}: {n_bones} bones, {total_axis_channels} axis channels, "
              f"{total_time_keyframes} time-keyframes, "
              f"length={anim_data.get('animation_length', 0)}s, "
              f"loop={anim_data.get('loop', 'unknown')}")

    # Inject animations into existing .bbmodel and save to derived/
    print("\n  Injecting animations into .bbmodel...")
    inject_animations_into_bbmodel(bbmodel_source, anim_json, bbmodel_output)

    print("\n" + "=" * 70)
    print("  DONE - VenkrolSIV Animation Generator")
    print("=" * 70)

    return anim_json


if __name__ == "__main__":
    main()
