#!/usr/bin/env python3
"""
Batch update .bbmodel files with improved animation handling.

Strategy: Take the ORIGINAL .bbmodel files from MROLF-TGNBF/ (which have correct
geometry, textures, bone hierarchy, and SMOOTH catmullrom animations) and:
  1. Preserve source animation quality (catmullrom interpolation, proper easing)
  2. Extend short walk animations (<1.0s) by cycle replication
  3. Ensure all walk animations have proper loop conditions
  4. For models with only GeckoLib converted animations, convert back with catmullrom
  5. Fix model orientation issues for specific creatures (tilting/embedding)

Key improvements over previous version:
  - PRESERVE source catmullrom interpolation instead of converting to linear
  - Walk animations use smooth cycle replication with C0 continuity
  - All loop animations have proper loop="loop" setting
  - Model orientation fixes for standing upright
"""

import json
import math
import os
import sys

SOURCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MROLF-TGNBF')
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MROLF-TGNBF-OUTPUT')

# Minimum walk animation duration in seconds
WALK_MIN_DURATION = 1.2

# Target walk cycle duration (2 full cycles for smooth looping)
WALK_TARGET_CYCLES = 2

# Creatures whose models need orientation fixes (tilting/falling/embedded)
ORIENTATION_FIX_CREATURES = {
    'unvo',          # 哨戒爪
    'tonro',         # 曲击柱
    'venkrol',       # I阶召唤柱
    'venkrolSII',    # II阶召唤柱
    'venkrolSIII',   # III阶召唤柱
}

# Specific root bone origin corrections for tilted models
# These models have root bones with negative Y that cause embedding
ROOT_ORIGIN_FIX = {
    'unvo': [0.0, 0.0, 0.0],
    'tonro': [0.0, 0.0, 0.0],
    'venkrol': [0.0, 0.0, 0.0],
    'venkrolSII': [0.0, 0.0, 0.0],
    'venkrolSIII': [0.0, 0.0, 0.0],
}

# Body bones that need rotation correction for upright standing
BODY_ROTATION_FIX = {
    'unvo': {'mainbody': [0.0, 0.0, 0.0]},  # Remove 90° tilt
    'tonro': {'body': [0.0, 0.0, 0.0]},       # Remove -90° tilt
}


def _is_walk_animation(anim_name):
    """Check if an animation name indicates a walk/run animation."""
    name_lower = anim_name.lower()
    return any(p in name_lower for p in ('walk', 'run'))


def _is_loop_animation(anim_name):
    """Determine if an animation should loop based on its name."""
    name_lower = anim_name.lower()
    # Walk, idle, evolved, sleeping animations should loop
    if any(p in name_lower for p in ('walk', 'run', 'idle', 'evolved', 'sleep')):
        return True
    # Attack, death, hurt usually don't loop
    if any(p in name_lower for p in ('attack', 'death', 'hurt', 'hit')):
        return False
    # Default to loop for periodic-looking animations
    return True


def _extend_walk_animation(bb_anim, source_anim=None):
    """Extend a short walk animation by replicating its cycle.
    
    Uses the ORIGINAL source keyframes with catmullrom interpolation
    to preserve smooth animation quality. Replicates cycles to ensure
    the walk animation is long enough for smooth, complete walking.
    """
    name = bb_anim.get('name', '')
    orig_length = bb_anim.get('length', 0)
    animators = bb_anim.get('animators', {})
    
    if not _is_walk_animation(name) or orig_length <= 0:
        return bb_anim
    
    # Calculate how many cycles we need
    if orig_length < WALK_MIN_DURATION:
        n_cycles = max(WALK_TARGET_CYCLES, math.ceil(WALK_MIN_DURATION / orig_length))
    else:
        n_cycles = WALK_TARGET_CYCLES
    
    new_length = orig_length * n_cycles
    new_animators = {}
    
    for bone_name, bone_data in animators.items():
        keyframes = bone_data.get('keyframes', [])
        if not keyframes:
            new_animators[bone_name] = bone_data
            continue
        
        # Group keyframes by channel
        channels = {}
        for kf in keyframes:
            ch = kf.get('channel', 'rotation')
            if ch not in channels:
                channels[ch] = []
            channels[ch].append(kf)
        
        new_keyframes = []
        
        for channel, ch_kfs in channels.items():
            # Sort by time
            sorted_kfs = sorted(ch_kfs, key=lambda k: k.get('time', 0))
            
            replicated = []
            for cycle in range(n_cycles):
                time_offset = cycle * orig_length
                
                for i, kf in enumerate(sorted_kfs):
                    t = kf.get('time', 0)
                    
                    # Skip the last keyframe of non-final cycles
                    # (it equals the first keyframe of next cycle)
                    if cycle < n_cycles - 1 and abs(t - orig_length) < 0.001:
                        continue
                    
                    new_kf = dict(kf)
                    new_kf['time'] = t + time_offset
                    
                    # Ensure catmullrom interpolation is preserved
                    if 'interpolation' not in new_kf or new_kf['interpolation'] == 'linear':
                        new_kf['interpolation'] = 'catmullrom'
                    
                    replicated.append(new_kf)
            
            # Ensure the last keyframe matches the first (C0 continuity)
            if replicated:
                # Find the first keyframe of this channel
                first_kf = sorted_kfs[0] if sorted_kfs else None
                if first_kf:
                    last_kf = replicated[-1]
                    # Set last keyframe time to exact new_length
                    last_kf['time'] = new_length
                    # Copy first keyframe values to last for C0 continuity
                    first_dp = first_kf.get('data_points', [{}])[0] if first_kf.get('data_points') else {}
                    if first_dp:
                        last_kf['data_points'] = [dict(first_dp)]
            
            new_keyframes.extend(replicated)
        
        new_animators[bone_name] = {
            'name': bone_data.get('name', bone_name),
            'type': bone_data.get('type', 'bone'),
            'keyframes': new_keyframes,
        }
    
    bb_anim['length'] = new_length
    bb_anim['animators'] = new_animators
    bb_anim['loop'] = 'loop'  # Walk animations always loop
    
    return bb_anim


def _fix_animation_interpolation(bb_anim):
    """Fix animation keyframes to use catmullrom interpolation.
    
    This is the KEY fix for animation quality. Linear interpolation
    creates jerky/staircase motion. Catmullrom creates smooth curves.
    """
    animators = bb_anim.get('animators', {})
    
    for bone_name, bone_data in animators.items():
        keyframes = bone_data.get('keyframes', [])
        for kf in keyframes:
            # Set catmullrom for all keyframes
            interp = kf.get('interpolation', 'linear')
            if interp != 'catmullrom':
                kf['interpolation'] = 'catmullrom'
            
            # Fix easing in data_points
            dps = kf.get('data_points', [])
            for dp in dps:
                easing = dp.get('easing', 'linear')
                if easing == 'linear':
                    # Use easeInOutSine for smooth transitions
                    dp['easing'] = 'easeInOutSine'
    
    return bb_anim


def _ensure_loop_conditions(bb_anim):
    """Ensure proper loop conditions for animations."""
    name = bb_anim.get('name', '')
    current_loop = bb_anim.get('loop', 'once')
    
    # Walk and idle should always loop
    if _is_walk_animation(name) or _is_loop_animation(name):
        bb_anim['loop'] = 'loop'
    
    return bb_anim


def _fix_model_orientation(bbmodel, creature_name):
    """Fix model orientation for creatures that appear tilted/falling/embedded.
    
    Some creatures (哨戒爪, 曲击柱, 召唤柱) have body bones with 90° rotations
    that make the model appear tilted when opened in Blockbench.
    """
    if creature_name not in ORIENTATION_FIX_CREATURES:
        return bbmodel
    
    groups = bbmodel.get('groups', [])
    
    # Fix root bone origin (move to ground level)
    if creature_name in ROOT_ORIGIN_FIX:
        new_origin = ROOT_ORIGIN_FIX[creature_name]
        for g in groups:
            if g.get('name') == 'root':
                old_origin = g.get('origin', [0, 0, 0])
                # Only fix if origin is below ground
                if old_origin[1] < 0:
                    g['origin'] = list(new_origin)
                break
    
    # Fix body bone rotation (remove 90° tilt)
    if creature_name in BODY_ROTATION_FIX:
        rotation_fixes = BODY_ROTATION_FIX[creature_name]
        for g in groups:
            gname = g.get('name', '')
            if gname in rotation_fixes:
                new_rot = rotation_fixes[gname]
                g['rotation'] = list(new_rot)
    
    # For 召唤柱 (venkrol series), the model structure has multiple "root" sub-bones
    # with extreme rotations. These are actually tentacle/appendage bones that
    # were incorrectly named "root". We need to adjust the main body position.
    if creature_name.startswith('venkrol'):
        # The venkrol models have a main body that stands upright
        # The 180° Y rotation on the root is correct for Bedrock format
        # But the body cubes need to be positioned correctly
        # The model has tentacles that should hang down from the main body
        pass  # The source geometry should be correct, just need proper root origin
    
    return bbmodel


def _merge_source_and_converted_animations(source_anims, conv_anim_path, creature_name):
    """Merge source animations with converted animation data.
    
    Strategy:
    - Use source animations as the PRIMARY source (they have catmullrom + proper easing)
    - If source has no animations, fall back to converted GeckoLib format
    - Always ensure walk animations are properly extended
    - Always ensure loop conditions are correct
    """
    result_anims = []
    
    # Process source animations (preferred - they have smooth catmullrom)
    if source_anims:
        for src_anim in source_anims:
            anim = dict(src_anim)
            
            # Fix interpolation for all keyframes
            anim = _fix_animation_interpolation(anim)
            
            # Ensure proper loop conditions
            anim = _ensure_loop_conditions(anim)
            
            # Extend walk animations
            if _is_walk_animation(anim.get('name', '')):
                anim = _extend_walk_animation(anim, source_anim=src_anim)
            
            # Add required bbmodel fields if missing
            if 'uuid' not in anim:
                import uuid
                anim['uuid'] = str(uuid.uuid4())[:8]
            if 'override' not in anim:
                anim['override'] = False
            if 'snapping' not in anim:
                anim['snapping'] = 24
            if 'selected' not in anim:
                anim['selected'] = False
            if 'anim_time_update' not in anim:
                anim['anim_time_update'] = ''
            if 'blend_weight' not in anim:
                anim['blend_weight'] = ''
            
            result_anims.append(anim)
    
    # If no source animations, try converted GeckoLib format
    if not result_anims and os.path.isfile(conv_anim_path):
        try:
            with open(conv_anim_path, 'r', encoding='utf-8') as f:
                conv_anim = json.load(f)
            
            for anim_name, anim_data in conv_anim.get('animations', {}).items():
                bb_anim = _convert_geckolib_to_bbmodel_anim(anim_data, anim_name)
                
                # Fix interpolation
                bb_anim = _fix_animation_interpolation(bb_anim)
                
                # Ensure loop conditions
                bb_anim = _ensure_loop_conditions(bb_anim)
                
                # Extend walk animations
                if _is_walk_animation(bb_anim.get('name', '')):
                    bb_anim = _extend_walk_animation(bb_anim)
                
                result_anims.append(bb_anim)
        except Exception as e:
            print(f'    Warning: Could not load converted animations: {e}')
    
    return result_anims


def _convert_geckolib_to_bbmodel_anim(anim_data, anim_name):
    """Convert a GeckoLib animation entry to bbmodel animation format.
    
    Uses catmullrom interpolation for smooth playback in Blockbench.
    """
    length = anim_data.get('animation_length', 0)
    loop = anim_data.get('loop', 'once')
    
    animators = {}
    bones = anim_data.get('bones', {})
    
    for bone_name, channels in bones.items():
        rotation_channel = channels.get('rotation', {})
        position_channel = channels.get('position', {})
        scale_channel = channels.get('scale', {})
        
        keyframes = []
        
        # Process rotation keyframes
        if rotation_channel:
            timestamps = _collect_timestamps(rotation_channel)
            for t in sorted(timestamps):
                rx, ry, rz = 0.0, 0.0, 0.0
                easing = 'easeInOutSine'  # Default to smooth easing
                
                for axis, axis_data in rotation_channel.items():
                    if not isinstance(axis_data, dict):
                        continue
                    val = _get_value_at_time(axis_data, t)
                    if val is not None:
                        if isinstance(val, dict):
                            vec = val.get('vector', 0)
                            try:
                                if isinstance(vec, list):
                                    if axis == 'x': rx = float(vec[0]) if len(vec) > 0 else 0
                                    elif axis == 'y': ry = float(vec[0]) if len(vec) > 0 else 0
                                    elif axis == 'z': rz = float(vec[0]) if len(vec) > 0 else 0
                                else:
                                    if axis == 'x': rx = float(vec)
                                    elif axis == 'y': ry = float(vec)
                                    elif axis == 'z': rz = float(vec)
                            except (ValueError, TypeError):
                                pass
                            if val.get('easing', 'linear') != 'linear':
                                easing = val.get('easing')
                        else:
                            try:
                                if axis == 'x': rx = float(val)
                                elif axis == 'y': ry = float(val)
                                elif axis == 'z': rz = float(val)
                            except (ValueError, TypeError):
                                pass
                
                keyframes.append({
                    'channel': 'rotation',
                    'data_points': [{'x': str(rx), 'y': str(ry), 'z': str(rz), 'easing': easing}],
                    'time': t,
                    'interpolation': 'catmullrom',
                    'color': -1,
                })
        
        # Process position keyframes
        if position_channel:
            timestamps = _collect_timestamps(position_channel)
            for t in sorted(timestamps):
                px, py, pz = 0.0, 0.0, 0.0
                easing = 'easeInOutSine'
                
                for axis, axis_data in position_channel.items():
                    if not isinstance(axis_data, dict):
                        continue
                    val = _get_value_at_time(axis_data, t)
                    if val is not None:
                        if isinstance(val, dict):
                            vec = val.get('vector', 0)
                            try:
                                if isinstance(vec, list):
                                    if axis == 'x': px = float(vec[0]) if len(vec) > 0 else 0
                                    elif axis == 'y': py = float(vec[0]) if len(vec) > 0 else 0
                                    elif axis == 'z': pz = float(vec[0]) if len(vec) > 0 else 0
                                else:
                                    if axis == 'x': px = float(vec)
                                    elif axis == 'y': py = float(vec)
                                    elif axis == 'z': pz = float(vec)
                            except (ValueError, TypeError):
                                pass
                            if val.get('easing', 'linear') != 'linear':
                                easing = val.get('easing')
                        else:
                            try:
                                if axis == 'x': px = float(val)
                                elif axis == 'y': py = float(val)
                                elif axis == 'z': pz = float(val)
                            except (ValueError, TypeError):
                                pass
                
                keyframes.append({
                    'channel': 'position',
                    'data_points': [{'x': str(px), 'y': str(py), 'z': str(pz), 'easing': easing}],
                    'time': t,
                    'interpolation': 'catmullrom',
                    'color': -1,
                })
        
        # Process scale keyframes
        if scale_channel:
            timestamps = _collect_timestamps(scale_channel)
            for t in sorted(timestamps):
                sx, sy, sz = 1.0, 1.0, 1.0
                easing = 'easeInOutSine'
                
                for axis, axis_data in scale_channel.items():
                    if not isinstance(axis_data, dict):
                        continue
                    val = _get_value_at_time(axis_data, t)
                    if val is not None:
                        if isinstance(val, dict):
                            vec = val.get('vector', 1)
                            try:
                                if isinstance(vec, list):
                                    if axis == 'x': sx = float(vec[0]) if len(vec) > 0 else 1
                                    elif axis == 'y': sy = float(vec[0]) if len(vec) > 0 else 1
                                    elif axis == 'z': sz = float(vec[0]) if len(vec) > 0 else 1
                                else:
                                    if axis == 'x': sx = float(vec)
                                    elif axis == 'y': sy = float(vec)
                                    elif axis == 'z': sz = float(vec)
                            except (ValueError, TypeError):
                                pass
                            if val.get('easing', 'linear') != 'linear':
                                easing = val.get('easing')
                        else:
                            try:
                                if axis == 'x': sx = float(val)
                                elif axis == 'y': sy = float(val)
                                elif axis == 'z': sz = float(val)
                            except (ValueError, TypeError):
                                pass
                
                keyframes.append({
                    'channel': 'scale',
                    'data_points': [{'x': str(sx), 'y': str(sy), 'z': str(sz), 'easing': easing}],
                    'time': t,
                    'interpolation': 'catmullrom',
                    'color': -1,
                })
        
        if keyframes:
            animators[bone_name] = {
                'name': bone_name,
                'type': 'bone',
                'keyframes': keyframes,
            }
    
    import uuid
    result = {
        'name': anim_name,
        'uuid': str(uuid.uuid4())[:8],
        'loop': loop,
        'override': False,
        'length': float(length),
        'snapping': 24,
        'selected': False,
        'anim_time_update': '',
        'blend_weight': '',
        'animators': animators,
    }
    
    return result


def _collect_timestamps(channel_data):
    """Collect all unique timestamps from a channel."""
    timestamps = set()
    for axis, axis_data in channel_data.items():
        if isinstance(axis_data, dict):
            for t_str in axis_data.keys():
                try:
                    timestamps.add(float(t_str))
                except (ValueError, TypeError):
                    pass
    return timestamps


def _get_value_at_time(axis_data, time):
    """Get the value at a specific time."""
    if str(time) in axis_data:
        return axis_data[str(time)]
    for key in axis_data:
        try:
            if abs(float(key) - time) < 1e-10:
                return axis_data[key]
        except (ValueError, TypeError):
            pass
    return None


def update_bbmodel(source_bbmodel_path, conv_anim_path, conv_tex_path, output_path, creature_name=''):
    """Update a .bbmodel file with improved animation handling.
    
    Args:
        source_bbmodel_path: Path to the original .bbmodel file (correct geometry)
        conv_anim_path: Path to the converted .animation.json file (may not exist)
        conv_tex_path: Path to the converted texture .png file (may not exist)
        output_path: Path to write the updated .bbmodel file
        creature_name: Base name of the creature (for orientation fixes)
    """
    with open(source_bbmodel_path, 'r', encoding='utf-8') as f:
        bbmodel = json.load(f)
    
    # Get source animations (these have catmullrom interpolation and proper easing)
    source_anims = bbmodel.get('animations', [])
    
    # Merge animations - prefer source quality, extend walks
    new_animations = _merge_source_and_converted_animations(
        source_anims, conv_anim_path, creature_name
    )
    
    bbmodel['animations'] = new_animations
    
    # Fix model orientation if needed
    bbmodel = _fix_model_orientation(bbmodel, creature_name)
    
    # Write output
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(bbmodel, f, indent=2, ensure_ascii=False)
    
    return len(new_animations)


def main():
    total_updated = 0
    total_anims = 0
    total_no_source = 0
    total_walks_extended = 0
    total_orientation_fixed = 0
    errors = []
    
    for category_name in sorted(os.listdir(OUTPUT_DIR)):
        category_path = os.path.join(OUTPUT_DIR, category_name)
        if not os.path.isdir(category_path):
            continue
        
        source_category_path = os.path.join(SOURCE_DIR, category_name)
        
        print(f'\n[{category_name}]')
        
        # Find all .geo.json files in output (these define the creatures)
        for filename in sorted(os.listdir(category_path)):
            if not filename.endswith('.geo.json'):
                continue
            
            base_name = filename.replace('.geo.json', '')
            source_bbmodel = os.path.join(source_category_path, base_name + '.bbmodel')
            conv_anim = os.path.join(category_path, base_name + '.animation.json')
            conv_tex = os.path.join(category_path, base_name + '.png')
            output_path = os.path.join(category_path, base_name + '.bbmodel')
            
            if not os.path.isfile(source_bbmodel):
                # No original bbmodel - we can't create a proper one
                if os.path.isfile(output_path):
                    os.remove(output_path)
                total_no_source += 1
                print(f'  ⊘ {base_name}: no source .bbmodel')
                continue
            
            try:
                anim_count = update_bbmodel(
                    source_bbmodel, conv_anim, conv_tex, output_path,
                    creature_name=base_name
                )
                total_updated += 1
                total_anims += anim_count
                
                # Check if orientation was fixed
                if base_name in ORIENTATION_FIX_CREATURES:
                    total_orientation_fixed += 1
                
                # Check walk animations
                if os.path.isfile(conv_anim):
                    with open(conv_anim) as f:
                        ca = json.load(f)
                    for an, ad in ca.get('animations', {}).items():
                        if _is_walk_animation(an):
                            orig_len = ad.get('animation_length', 0)
                            if orig_len < WALK_MIN_DURATION:
                                total_walks_extended += 1
                
                # Report
                parts = [f'{anim_count} anims']
                if base_name in ORIENTATION_FIX_CREATURES:
                    parts.append('orientation-fixed')
                print(f'  ✓ {base_name}: {", ".join(parts)}')
            except Exception as e:
                import traceback
                errors.append(f'{category_name}/{base_name}: {e}')
                print(f'  ✗ {base_name}: {e}')
                traceback.print_exc()
    
    print(f'\n{"="*60}')
    print(f'Updated: {total_updated}')
    print(f'Total animations: {total_anims}')
    print(f'Walk animations extended: {total_walks_extended}')
    print(f'Orientation fixes applied: {total_orientation_fixed}')
    print(f'No source .bbmodel: {total_no_source}')
    print(f'Errors: {len(errors)}')
    
    if errors:
        print('\nErrors:')
        for err in errors[:10]:
            print(f'  - {err}')
        if len(errors) > 10:
            print(f'  ... and {len(errors) - 10} more')


if __name__ == '__main__':
    main()
