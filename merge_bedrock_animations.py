#!/usr/bin/env python3
"""
Merge Missing Animations from Bedrock .animation.json into .bbmodel files
========================================================================
Many source .bbmodel files are missing animations that exist in the
corresponding bedrock .animation.json files. This script:

1. For each .bbmodel in MROLF-TGNBF/, finds matching .animation.json in bedrock/
2. Identifies animations present in .animation.json but NOT in .bbmodel
3. Converts and merges the missing animations into the .bbmodel file
4. Ensures smooth loop coherence for all merged animations

This significantly increases the animation count for many creatures.
"""

import copy
import json
import math
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'converter'))
from bbmodel_generator import BBModelGenerator

SOURCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MROLF-TGNBF')
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MROLF-TGNBF-OUTPUT')
BEDROCK_DIR = os.path.join(SOURCE_DIR, 'bedrock')


def _short_uuid():
    return uuid.uuid4().hex[:8]


def _is_walk_animation(anim_name):
    name_lower = anim_name.lower()
    return any(p in name_lower for p in ('walk', 'run'))


def _is_blend_animation(anim_name):
    """Check if this is a Bedrock blend animation (idle_walk, evolved_walk, etc.)
    
    These are Minecraft Bedrock animation blending controllers that define
    how animations blend when the mob is moving. They're not standalone 
    animations and shouldn't be added as separate animations.
    """
    name_lower = anim_name.lower()
    return '_walk' in name_lower and any(
        p in name_lower for p in ('idle_walk', 'evolved_walk', 'attack_walk', 'death_walk')
    )


def _is_non_loop_animation(anim_name):
    name_lower = anim_name.lower()
    return any(p in name_lower for p in ('attack', 'death', 'hurt', 'hit', 'vomit', 'open', 'close'))


def _is_loop_animation(anim_name):
    name_lower = anim_name.lower()
    if any(p in name_lower for p in ('walk', 'run', 'idle', 'evolved', 'sleep', 'fly', 'swim')):
        return True
    if _is_non_loop_animation(anim_name):
        return False
    return True


def _get_kf_values(kf):
    dp = kf.get('data_points', [{}])[0] if kf.get('data_points') else {}
    return (
        float(dp.get('x', 0)),
        float(dp.get('y', 0)),
        float(dp.get('z', 0)),
    )


def _calc_gap(vals1, vals2):
    return max(abs(a - b) for a, b in zip(vals1, vals2))


def ensure_smooth_loop_for_anim(bb_anim):
    """Ensure smooth loop coherence for a single animation."""
    if bb_anim.get('loop') != 'loop':
        return bb_anim
    
    anim_length = bb_anim.get('length', 0)
    if anim_length <= 0:
        return bb_anim
    
    animators = bb_anim.get('animators', {})
    
    for bone_name, bone_data in animators.items():
        keyframes = bone_data.get('keyframes', [])
        if not keyframes:
            continue
        
        # Group by channel
        channels = {}
        for kf in keyframes:
            ch = kf.get('channel', 'rotation')
            if ch not in channels:
                channels[ch] = []
            channels[ch].append(kf)
        
        for ch, ch_kfs in channels.items():
            sorted_kfs = sorted(ch_kfs, key=lambda k: k.get('time', 0))
            if len(sorted_kfs) < 2:
                continue
            
            first_kf = sorted_kfs[0]
            last_kf = sorted_kfs[-1]
            
            first_vals = _get_kf_values(first_kf)
            last_vals = _get_kf_values(last_kf)
            last_time = last_kf.get('time', 0)
            
            value_gap = _calc_gap(first_vals, last_vals)
            time_gap = abs(last_time - anim_length)
            
            # Already perfect
            if value_gap < 0.01 and time_gap < 0.01:
                continue
            
            # Values match but last kf not at anim_length
            if value_gap < 0.01 and time_gap >= 0.01:
                closing_kf = copy.deepcopy(first_kf)
                closing_kf['uuid'] = _short_uuid()
                closing_kf['time'] = anim_length
                closing_kf['interpolation'] = last_kf.get('interpolation', 'linear')
                keyframes.append(closing_kf)
                continue
            
            # Values don't match — add smooth transition
            transition_duration = max(0.1, anim_length * 0.10)
            transition_start_time = anim_length - transition_duration
            
            # Interpolate values at transition start
            pre_vals = _interpolate_at_time(sorted_kfs, transition_start_time)
            
            # If transition start is before last kf, adjust
            if transition_start_time < last_time:
                transition_start_time = last_time
                transition_duration = anim_length - last_time
                pre_vals = last_vals
                
                if transition_duration < 0.1:
                    # Very short gap — snap
                    dp = last_kf.get('data_points', [{}])[0] if last_kf.get('data_points') else {}
                    first_dp = first_kf.get('data_points', [{}])[0] if first_kf.get('data_points') else {}
                    for axis in ('x', 'y', 'z'):
                        if axis in first_dp:
                            dp[axis] = float(first_dp[axis])
                    last_kf['data_points'] = [dp]
                    last_kf['time'] = anim_length
                    continue
            
            # Anchor keyframe at transition start
            has_near = any(abs(kf.get('time', 0) - transition_start_time) < 0.01 for kf in sorted_kfs)
            if not has_near and transition_start_time > last_time:
                anchor_kf = {
                    'channel': ch,
                    'data_points': [{
                        'x': round(pre_vals[0], 6),
                        'y': round(pre_vals[1], 6),
                        'z': round(pre_vals[2], 6),
                        'easing': 'easeInSine',
                    }],
                    'uuid': _short_uuid(),
                    'time': transition_start_time,
                    'color': -1,
                    'interpolation': 'catmullrom',
                }
                keyframes.append(anchor_kf)
            
            # Closing keyframe at anim_length
            first_dp = first_kf.get('data_points', [{}])[0] if first_kf.get('data_points') else {}
            closing_kf = {
                'channel': ch,
                'data_points': [{
                    'x': float(first_dp.get('x', 0)),
                    'y': float(first_dp.get('y', 0)),
                    'z': float(first_dp.get('z', 0)),
                    'easing': 'easeOutSine',
                }],
                'uuid': _short_uuid(),
                'time': anim_length,
                'color': -1,
                'interpolation': 'catmullrom',
            }
            keyframes.append(closing_kf)
    
    return bb_anim


def _interpolate_at_time(sorted_kfs, target_time):
    if not sorted_kfs:
        return (0.0, 0.0, 0.0)
    if target_time <= sorted_kfs[0].get('time', 0):
        return _get_kf_values(sorted_kfs[0])
    if target_time >= sorted_kfs[-1].get('time', 0):
        return _get_kf_values(sorted_kfs[-1])
    for i in range(len(sorted_kfs) - 1):
        t1 = sorted_kfs[i].get('time', 0)
        t2 = sorted_kfs[i + 1].get('time', 0)
        if t1 <= target_time <= t2:
            v1 = _get_kf_values(sorted_kfs[i])
            v2 = _get_kf_values(sorted_kfs[i + 1])
            if abs(t2 - t1) < 1e-10:
                return v1
            t = (target_time - t1) / (t2 - t1)
            return (
                v1[0] + (v2[0] - v1[0]) * t,
                v1[1] + (v2[1] - v1[1]) * t,
                v1[2] + (v2[2] - v1[2]) * t,
            )
    return _get_kf_values(sorted_kfs[-1])


def extend_walk_animation(bb_anim, min_duration=1.2):
    """Extend a short walk animation by replicating its cycle."""
    name = bb_anim.get('name', '')
    orig_length = bb_anim.get('length', 0)
    animators = bb_anim.get('animators', {})
    
    if not _is_walk_animation(name) or orig_length <= 0:
        return bb_anim
    
    if orig_length >= min_duration:
        bb_anim['loop'] = 'loop'
        return bb_anim
    
    n_cycles = max(2, math.ceil(min_duration / orig_length))
    new_length = orig_length * n_cycles
    new_animators = {}
    
    for bone_name, bone_data in animators.items():
        keyframes = bone_data.get('keyframes', [])
        if not keyframes:
            new_animators[bone_name] = bone_data
            continue
        
        channels = {}
        for kf in keyframes:
            ch = kf.get('channel', 'rotation')
            if ch not in channels:
                channels[ch] = []
            channels[ch].append(kf)
        
        new_keyframes = []
        for channel, ch_kfs in channels.items():
            sorted_kfs = sorted(ch_kfs, key=lambda k: k.get('time', 0))
            if not sorted_kfs:
                continue
            
            first_vals = _get_kf_values(sorted_kfs[0])
            last_vals = _get_kf_values(sorted_kfs[-1])
            c0 = _calc_gap(first_vals, last_vals) < 0.01
            
            if not c0:
                # Blend last toward first
                last_kf = sorted_kfs[-1]
                last_dp = last_kf.get('data_points', [{}])[0] if last_kf.get('data_points') else {}
                first_dp = sorted_kfs[0].get('data_points', [{}])[0] if sorted_kfs[0].get('data_points') else {}
                for axis in ('x', 'y', 'z'):
                    fv = float(first_dp.get(axis, 0))
                    lv = float(last_dp.get(axis, 0))
                    if abs(fv - lv) > 0.01:
                        last_dp[axis] = round(lv + (fv - lv) * 0.7, 4)
            
            replicated = []
            for cycle in range(n_cycles):
                time_offset = cycle * orig_length
                for i, kf in enumerate(sorted_kfs):
                    t = kf.get('time', 0)
                    if c0 and cycle < n_cycles - 1 and abs(t - orig_length) < 0.001:
                        continue
                    new_kf = copy.deepcopy(kf)
                    new_kf['uuid'] = _short_uuid()
                    new_kf['time'] = t + time_offset
                    replicated.append(new_kf)
            
            if replicated:
                last_kf = replicated[-1]
                last_kf['time'] = new_length
                first_dp = sorted_kfs[0].get('data_points', [{}])[0] if sorted_kfs[0].get('data_points') else {}
                if first_dp:
                    new_dp = {}
                    for k, v in first_dp.items():
                        new_dp[k] = float(v) if k in ('x', 'y', 'z') else v
                    last_kf['data_points'] = [new_dp]
            
            new_keyframes.extend(replicated)
        
        new_animators[bone_name] = {
            'name': bone_data.get('name', bone_name),
            'type': bone_data.get('type', 'bone'),
            'keyframes': new_keyframes,
        }
    
    bb_anim['length'] = new_length
    bb_anim['animators'] = new_animators
    bb_anim['loop'] = 'loop'
    return bb_anim


def merge_animations():
    """Merge missing animations from bedrock .animation.json into .bbmodel files."""
    generator = BBModelGenerator()
    
    total_merged = 0
    total_anims_added = 0
    total_walk_extended = 0
    
    for category_name in sorted(os.listdir(SOURCE_DIR)):
        category_path = os.path.join(SOURCE_DIR, category_name)
        if not os.path.isdir(category_path):
            continue
        
        bedrock_category_path = os.path.join(BEDROCK_DIR, category_name)
        output_category_path = os.path.join(OUTPUT_DIR, category_name)
        
        for filename in sorted(os.listdir(category_path)):
            if not filename.endswith('.bbmodel'):
                continue
            
            base_name = filename.replace('.bbmodel', '')
            source_bbmodel_path = os.path.join(category_path, filename)
            output_bbmodel_path = os.path.join(output_category_path, filename)
            
            # Check if there's a bedrock animation file
            bedrock_anim_path = os.path.join(bedrock_category_path, base_name + '.animation.json')
            if not os.path.isfile(bedrock_anim_path):
                continue
            
            # Read the source .bbmodel
            with open(source_bbmodel_path, 'r', encoding='utf-8') as f:
                bbmodel = json.load(f)
            
            # Read the bedrock animation file
            with open(bedrock_anim_path, 'r', encoding='utf-8') as f:
                bedrock_anim = json.load(f)
            
            # Get existing animation names in the .bbmodel
            existing_anims = {a.get('name', '') for a in bbmodel.get('animations', [])}
            
            # Find missing animations (excluding blend animations)
            bedrock_anims = bedrock_anim.get('animations', {})
            missing_anims = {}
            for anim_name, anim_data in bedrock_anims.items():
                if anim_name not in existing_anims and not _is_blend_animation(anim_name):
                    missing_anims[anim_name] = anim_data
            
            if not missing_anims:
                continue
            
            # Convert missing animations to .bbmodel format using BBModelGenerator
            anim_json_for_conversion = {
                "format_version": "1.8.0",
                "animations": missing_anims,
            }
            
            new_bb_anims = generator._build_animations(anim_json_for_conversion)
            
            # Apply loop coherence and walk extension to new animations
            for bb_anim in new_bb_anims:
                anim_name = bb_anim.get('name', '')
                
                # Set loop mode
                if _is_loop_animation(anim_name):
                    bb_anim['loop'] = 'loop'
                elif _is_non_loop_animation(anim_name):
                    bb_anim['loop'] = 'once'
                
                # Extend walk animations
                if _is_walk_animation(anim_name):
                    orig_len = bb_anim.get('length', 0)
                    bb_anim = extend_walk_animation(bb_anim)
                    new_len = bb_anim.get('length', 0)
                    if abs(new_len - orig_len) > 0.01:
                        total_walk_extended += 1
                
                # Ensure smooth loop coherence
                if bb_anim.get('loop') == 'loop':
                    bb_anim = ensure_smooth_loop_for_anim(bb_anim)
            
            # Merge into the .bbmodel
            bbmodel.setdefault('animations', []).extend(new_bb_anims)
            
            # Write the updated .bbmodel to both source and output
            for write_path in [source_bbmodel_path, output_bbmodel_path]:
                try:
                    os.makedirs(os.path.dirname(write_path), exist_ok=True)
                    with open(write_path, 'w', encoding='utf-8') as f:
                        json.dump(bbmodel, f, indent=2, ensure_ascii=False)
                except Exception as e:
                    print(f"    WARNING: Could not write {write_path}: {e}")
            
            total_merged += 1
            total_anims_added += len(new_bb_anims)
            added_names = [a.get('name', '') for a in new_bb_anims]
            print(f'  ✓ {category_name}/{base_name}: added {len(new_bb_anims)} animations: {added_names}')
    
    print()
    print(f"Total files with animations merged: {total_merged}")
    print(f"Total animations added: {total_anims_added}")
    print(f"Walk animations extended: {total_walk_extended}")


if __name__ == '__main__':
    print("=" * 70)
    print("  Merge Missing Animations from Bedrock .animation.json")
    print("=" * 70)
    print()
    merge_animations()
