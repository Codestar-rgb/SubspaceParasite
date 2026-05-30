#!/usr/bin/env python3
"""
BatchAnimationConvert - Universal Batch Animation Converter
===========================================================
Replaces individual per-creature animation generators with a unified
pipeline powered by UniversalAnimationConverter.

Supports:
  - Callback-based conversion (existing eval functions from heblu/kirin generators)
  - Auto loop duration detection with C1 continuity
  - Adaptive sampling rates based on frequency analysis
  - Smart duration optimization via phase error minimization

Usage:
  python batch_animation_convert.py --creature heblu
  python batch_animation_convert.py --creature kirin
  python batch_animation_convert.py --all
  python batch_animation_convert.py --auto java_source.java --mapping mapping.json
"""

import argparse
import json
import math
import os
import sys
import time
from typing import Dict, List, Optional, Callable

# Add converter directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from universal_animation_converter import (
    ConverterConfig,
    AnimationStateConfig,
    UniversalAnimationConverter,
    batch_convert_creature,
)

# ============================================================================
# Creature-specific eval function registries
# ============================================================================

# Import existing eval functions from per-creature generators
# These are the ONLY creature-specific parts that remain
# Everything else (sampling, loop detection, continuity, DP, JSON building)
# is handled by the universal converter

def _get_heblu_states() -> List[AnimationStateConfig]:
    """Get animation state configs for Heblu (Draconite)."""
    from heblu_animation_generator import (
        eval_idle, eval_attack, eval_fly, eval_vomit,
        eval_shaking, eval_cosmic,
        swing_x_8, swing_z_8, move_y,
    )
    
    return [
        AnimationStateConfig(
            name='idle',
            eval_func=lambda t: eval_idle(t, limb_swing_amount=0.5),
            loop_mode='loop',
            duration=2.327,  # Walk cycle period
        ),
        AnimationStateConfig(
            name='attack',
            eval_func=lambda t: eval_attack(t, limb_swing_amount=0.5),
            loop_mode='loop',
            duration=2.094,  # Attack walk cycle period
        ),
        AnimationStateConfig(
            name='fly',
            eval_func=eval_fly,
            loop_mode='loop',
            duration=3.14,  # 2× wing flap period
        ),
        AnimationStateConfig(
            name='vomit',
            eval_func=lambda t: eval_vomit(t, raining=False, flying=False),
            loop_mode='hold_on_last_frame',
            duration=4.0,
        ),
        AnimationStateConfig(
            name='fly_vomit',
            eval_func=lambda t: eval_vomit(t, raining=False, flying=True),
            loop_mode='hold_on_last_frame',
            duration=4.0,
        ),
        AnimationStateConfig(
            name='shaking',
            eval_func=eval_shaking,
            loop_mode='loop',
            duration=2.0,
            sample_rate=240.0,  # Fast oscillation needs higher rate
        ),
        AnimationStateConfig(
            name='cosmic',
            eval_func=lambda t: eval_cosmic(t, shaking=False),
            loop_mode='loop',
            duration=4.0,
            sample_rate=120.0,
        ),
        AnimationStateConfig(
            name='cosmic_shaking',
            eval_func=lambda t: eval_cosmic(t, shaking=True),
            loop_mode='loop',
            duration=2.0,
            sample_rate=300.0,  # Very fast oscillation
        ),
    ]


def _get_kirin_states() -> List[AnimationStateConfig]:
    """Get animation state configs for Kirin."""
    from kirin_animation_generator import (
        eval_idle, eval_shaking, eval_cosmic, eval_cosmic_shaking,
    )
    
    return [
        AnimationStateConfig(
            name='idle',
            eval_func=eval_idle,
            loop_mode='loop',
            duration=5.0,  # Kirin uses longer idle cycle
        ),
        AnimationStateConfig(
            name='shaking',
            eval_func=eval_shaking,
            loop_mode='loop',
            duration=2.0,
            sample_rate=240.0,
        ),
        AnimationStateConfig(
            name='cosmic',
            eval_func=lambda t: eval_cosmic(t),
            loop_mode='loop',
            duration=4.0,
            sample_rate=120.0,
        ),
        AnimationStateConfig(
            name='cosmic_shaking',
            eval_func=eval_cosmic_shaking,
            loop_mode='loop',
            duration=2.0,
            sample_rate=300.0,
        ),
    ]


# ============================================================================
# Creature Registry
# ============================================================================

CREATURE_STATES = {
    'heblu': _get_heblu_states,
    'kirin': _get_kirin_states,
}


# ============================================================================
# Auto-detect animation states from Java source
# ============================================================================

def auto_detect_states(java_source_path: str, bone_mapping_path: str = None) -> List[AnimationStateConfig]:
    """Auto-detect animation states from Java source code.
    
    Uses the UniversalAnimationConverter's Java parser to extract
    state machine branches and build eval functions automatically.
    """
    with open(java_source_path, 'r', encoding='utf-8') as f:
        java_source = f.read()
    
    bone_mapping = {}
    if bone_mapping_path and os.path.isfile(bone_mapping_path):
        with open(bone_mapping_path, 'r', encoding='utf-8') as f:
            bone_mapping = json.load(f)
    
    config = ConverterConfig()
    converter = UniversalAnimationConverter(config)
    states = converter.java_parser.parse(java_source, bone_mapping)
    
    return states


# ============================================================================
# Batch Conversion
# ============================================================================

def convert_creature(creature_name: str, output_dir: str = None,
                     config: ConverterConfig = None,
                     auto_duration: bool = False) -> dict:
    """Convert all animations for a single creature.
    
    Args:
        creature_name: Name of the creature (must be in CREATURE_STATES)
        output_dir: Directory to save output files
        config: Optional configuration override
        auto_duration: If True, auto-detect loop durations instead of using presets
    
    Returns:
        Complete .animation.json dict
    """
    if creature_name not in CREATURE_STATES:
        raise ValueError(f"Unknown creature: {creature_name}. Available: {list(CREATURE_STATES.keys())}")
    
    if config is None:
        config = ConverterConfig(
            dp_epsilon_rotation=0.08,
            dp_epsilon_position=0.01,
        )
    
    # Get creature-specific state configs
    states = CREATURE_STATES[creature_name]()
    
    # If auto_duration, clear preset durations to trigger auto-detection
    if auto_duration:
        for state in states:
            state.duration = None
            state.sample_rate = None  # Also auto-detect sample rate
    
    print(f"\n  Converting {creature_name} ({len(states)} animation states)...")
    t_start = time.time()
    
    result = batch_convert_creature(
        creature_name=creature_name,
        states=states,
        config=config,
    )
    
    elapsed = time.time() - t_start
    
    # Print statistics
    total_kf = 0
    for anim_name, anim_data in result.get('animations', {}).items():
        n_bones = len(anim_data.get('bones', {}))
        anim_kf = sum(len(ch) for b in anim_data.get('bones', {}).values() for ch in b.values())
        total_kf += anim_kf
        duration = anim_data.get('animation_length', 0)
        loop = anim_data.get('loop', 'unknown')
        print(f"    {anim_name}: {n_bones} bones, {anim_kf} keyframes, "
              f"duration={duration}s, loop={loop}")
    
    print(f"  Total: {total_kf} keyframes in {elapsed:.1f}s")
    
    # Save output
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{creature_name}.animation.json")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"  Saved to: {output_path}")
        
        file_size = os.path.getsize(output_path)
        print(f"  File size: {file_size:,} bytes")
    
    return result


def convert_all_creatures(output_dir: str = None,
                          config: ConverterConfig = None,
                          auto_duration: bool = False) -> Dict[str, dict]:
    """Convert all registered creatures.
    
    Returns:
        Dict mapping creature names to their .animation.json dicts
    """
    results = {}
    for creature_name in CREATURE_STATES:
        print(f"\n{'='*60}")
        print(f"  Converting: {creature_name}")
        print(f"{'='*60}")
        result = convert_creature(creature_name, output_dir, config, auto_duration)
        results[creature_name] = result
    
    return results


# ============================================================================
# Quality Validation
# ============================================================================

def validate_animation(anim_json: dict, name: str = "") -> List[str]:
    """Validate an animation JSON for quality issues.
    
    Checks:
    - C0 continuity (start=end for loop animations)
    - Empty animation states
    - Excessive keyframe counts
    - Missing animation_length
    
    Returns:
        List of warning strings (empty if all checks pass)
    """
    warnings = []
    
    for anim_name, anim_data in anim_json.get('animations', {}).items():
        full_name = f"{name}.{anim_name}" if name else anim_name
        
        # Check animation_length
        if 'animation_length' not in anim_data:
            warnings.append(f"{full_name}: missing animation_length")
        
        # Check bones
        bones = anim_data.get('bones', {})
        if not bones:
            warnings.append(f"{full_name}: no bones animated")
            continue
        
        # Check C0 continuity for loop animations
        loop = anim_data.get('loop', '')
        if loop == 'loop':
            max_diff = 0.0
            worst_channel = ''
            for bone_name, bone_data in bones.items():
                for channel_type, channel_data in bone_data.items():
                    if not isinstance(channel_data, dict):
                        continue
                    for axis, kfs in channel_data.items():
                        if not isinstance(kfs, dict) or len(kfs) < 2:
                            continue
                        times = sorted([float(t) for t in kfs.keys()])
                        first_val = kfs.get(f'{times[0]:.4f}', None)
                        last_val = kfs.get(f'{times[-1]:.4f}', None)
                        if first_val is not None and last_val is not None:
                            diff = abs(first_val - last_val)
                            if diff > max_diff:
                                max_diff = diff
                                worst_channel = f"{bone_name}.{channel_type}.{axis}"
            
            if max_diff > 0.01:
                warnings.append(f"{full_name}: C0 continuity issue in {worst_channel} "
                              f"(diff={max_diff:.6f})")
    
    return warnings


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Universal Batch Animation Converter',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python batch_animation_convert.py --creature heblu
  python batch_animation_convert.py --creature kirin --auto-duration
  python batch_animation_convert.py --all
  python batch_animation_convert.py --validate heblu.animation.json
        """
    )
    
    parser.add_argument('--creature', type=str, help='Creature name to convert')
    parser.add_argument('--all', action='store_true', help='Convert all registered creatures')
    parser.add_argument('--auto-duration', action='store_true',
                       help='Auto-detect loop durations instead of using presets')
    parser.add_argument('--output-dir', type=str, default=None,
                       help='Output directory (default: db/)')
    parser.add_argument('--validate', type=str, help='Validate an existing animation JSON file')
    parser.add_argument('--dp-epsilon', type=float, default=0.08,
                       help='Douglas-Peucker epsilon for rotation (default: 0.08)')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  Universal Batch Animation Converter")
    print("  MC 1.12.2 → GeckoLib 1.20.1")
    print("=" * 60)
    
    # Determine output directory
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = args.output_dir or os.path.join(project_root, 'db')
    
    config = ConverterConfig(dp_epsilon_rotation=args.dp_epsilon)
    
    if args.validate:
        # Validate mode
        with open(args.validate, 'r', encoding='utf-8') as f:
            anim_json = json.load(f)
        warnings = validate_animation(anim_json)
        if warnings:
            print(f"\n  Found {len(warnings)} issues:")
            for w in warnings:
                print(f"    ⚠ {w}")
        else:
            print("\n  ✓ All checks passed!")
        return
    
    if args.all:
        results = convert_all_creatures(output_dir, config, args.auto_duration)
        print(f"\n  Converted {len(results)} creatures")
    elif args.creature:
        result = convert_creature(args.creature, output_dir, config, args.auto_duration)
    else:
        parser.print_help()
        return
    
    print("\n" + "=" * 60)
    print("  DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
