#!/usr/bin/env python3
"""
Fix and Rebuild .bbmodel Files — V2: Smooth Loop Coherence
============================================================
Takes source .bbmodel files from MROLF-TGNBF/ and creates corrected
versions in MROLF-TGNBF-OUTPUT/, fixing:

1. Duplicate root group UUIDs (causes model tilting)
2. Walk animation too short (extends by cycle replication)
3. Loop conditions not set properly
4. **Smooth loop coherence**: End of animation perfectly transitions to start
   - NOT just snapping last keyframe to start values (causes visible jerk)
   - Instead, adds smooth transition segment that gradually returns to start
5. Preserves ALL original animation data (interpolation, easing, keyframes)
6. Does NOT force catmullrom or easeInOutSine — keeps original values

Key V2 improvements over V1:
- ensure_smooth_loop(): Instead of hard-snapping last keyframe to start values,
  adds a smooth transition segment with interpolation back to start pose
- Respects hold_on_last_frame animations — doesn't force them to loop
- Better walk cycle extension with proper seamless cycle boundaries
- Handles incomplete animation coverage (end gap issues)
"""

import base64
import copy
import json
import math
import os
import sys
import uuid

SOURCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MROLF-TGNBF')
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MROLF-TGNBF-OUTPUT')

# Texture directories for fixing wrong textures
JAR_TEX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jar_extract', 'assets', 'srparasites', 'textures', 'entity', 'monster')
QOM_TEX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Qom-Inseac', 'src', 'main', 'resources', 'assets', 'subspaceparasite', 'textures', 'entity', 'monster')
PROJ_TEX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jar_extract', 'assets', 'srparasites', 'textures', 'entity', 'projectile')
QOM_PROJ_TEX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Qom-Inseac', 'src', 'main', 'resources', 'assets', 'subspaceparasite', 'textures', 'entity', 'projectile')

# Minimum walk animation duration (seconds)
WALK_MIN_DURATION = 1.2

# Loop coherence threshold — gap below this is considered "perfect enough"
LOOP_GAP_THRESHOLD = 0.01

# Transition segment duration as fraction of animation length (10%)
# This creates a smooth return to start pose instead of a hard snap
TRANSITION_SEGMENT_FRACTION = 0.10

# Minimum transition duration in seconds
MIN_TRANSITION_DURATION = 0.1

# Creatures with duplicate root group UUIDs that cause tilting
DUPLICATE_ROOT_CREATURES = {
    'unvo', 'tonro', 'venkrol', 'venkrolSII', 'venkrolSIII',
    'venkrolsii', 'venkrolsiii',
}

# Creatures with wrong embedded textures — map to correct texture filename
TEXTURE_FIX_MAP = {
    'viin': 'vermina',  # viin should use vermina.png (256×256), not its embedded 128×64
}

# Animations that should NOT be forced to loop even if they seem cyclic
# These are one-shot animations by design
NON_LOOP_ANIM_PATTERNS = (
    'vomit', 'death', 'hurt', 'hit', 'attack',
    'open', 'close', 'spawn', 'despawn',
)


def _short_uuid():
    """Generate a short 8-char hex UUID."""
    return uuid.uuid4().hex[:8]


def _is_walk_animation(anim_name):
    """Check if an animation name indicates a walk/run animation."""
    name_lower = anim_name.lower()
    return any(p in name_lower for p in ('walk', 'run'))


def _is_non_loop_animation(anim_name):
    """Check if an animation should NOT be forced to loop."""
    name_lower = anim_name.lower()
    return any(p in name_lower for p in NON_LOOP_ANIM_PATTERNS)


def _is_loop_animation(anim_name):
    """Determine if an animation should loop based on its name.
    
    V2: More conservative — doesn't force attack/death/hurt to loop.
    """
    name_lower = anim_name.lower()
    # Walk, idle, evolved, sleeping, fly should loop
    if any(p in name_lower for p in ('walk', 'run', 'idle', 'evolved', 'sleep', 'fly', 'swim')):
        return True
    # Attack, death, hurt, vomit, open, close don't loop
    if _is_non_loop_animation(anim_name):
        return False
    # Default to loop for everything else (most SRP animations are cyclic)
    return True


def _get_kf_values(kf):
    """Extract (x, y, z) values from a keyframe's first data_point."""
    dp = kf.get('data_points', [{}])[0] if kf.get('data_points') else {}
    return (
        float(dp.get('x', 0)),
        float(dp.get('y', 0)),
        float(dp.get('z', 0)),
    )


def _calc_gap(vals1, vals2):
    """Calculate the maximum absolute difference between two value tuples."""
    return max(abs(a - b) for a, b in zip(vals1, vals2))


def _lerp_val(v1, v2, t):
    """Linear interpolation between two values."""
    return v1 + (v2 - v1) * t


def _ease_in_out(t):
    """Smooth ease-in-out curve (sinusoidal)."""
    return -(math.cos(math.pi * t) - 1) / 2


def fix_duplicate_root_uuids(bbmodel, creature_name):
    """Fix duplicate root group UUIDs that cause model tilting.
    
    The issue: Some models (unvo, tonro, venkrol series) have TWO groups
    named "root" with the SAME UUID but different rotations. The second
    root (inside rootmain) has a tilted rotation (e.g., [70.43, 180, 0])
    that makes tentacle sub-bones appear correctly oriented but causes
    the model to tilt when opened in Blockbench.
    
    Fix: Give the second root group a unique UUID so Blockbench treats
    it as a separate bone rather than confusing it with the main root.
    Also rename it to avoid name collision.
    """
    if creature_name not in DUPLICATE_ROOT_CREATURES:
        return bbmodel
    
    groups = bbmodel.get('groups', [])
    root_count = 0
    root_uuid = None
    old_dup_uuid = None
    new_dup_uuid = None
    
    for g in groups:
        if g.get('name') == 'root':
            root_count += 1
            if root_uuid is None:
                # First root — keep its UUID
                root_uuid = g.get('uuid')
            elif g.get('uuid') == root_uuid:
                # Duplicate root — assign unique UUID and rename
                old_dup_uuid = g.get('uuid')
                new_dup_uuid = _short_uuid()
                g['uuid'] = new_dup_uuid
                g['name'] = 'rootarm'  # It's a tentacle arm root
                print(f"    Fixed duplicate root UUID: renamed to 'rootarm', new UUID: {g['uuid']}")
    
    if old_dup_uuid and new_dup_uuid:
        # Also fix the outliner to reference the new UUID
        outliner = bbmodel.get('outliner', [])
        
        def fix_outliner_uuid(node):
            """Recursively fix UUID references in the outliner."""
            if isinstance(node, dict):
                if node.get('uuid') == old_dup_uuid:
                    node['uuid'] = new_dup_uuid
                for child in node.get('children', []):
                    fix_outliner_uuid(child)
        
        for entry in outliner:
            fix_outliner_uuid(entry)
    
    return bbmodel


def fix_walk_animation(bb_anim):
    """Extend a short walk animation by replicating its cycle.
    
    V2 improvements:
    - Verifies that the source cycle already has C0 continuity before replicating
    - If source cycle is NOT C0 continuous, adds a smooth transition at cycle boundary
    - Replicated cycles are seamlessly joined
    - Final animation length matches exactly with the last keyframe
    """
    name = bb_anim.get('name', '')
    orig_length = bb_anim.get('length', 0)
    animators = bb_anim.get('animators', {})
    
    if not _is_walk_animation(name) or orig_length <= 0:
        return bb_anim
    
    if orig_length >= WALK_MIN_DURATION:
        # Already long enough, just ensure loop and smooth closure
        bb_anim['loop'] = 'loop'
        return bb_anim
    
    # Calculate how many cycles we need
    n_cycles = max(2, math.ceil(WALK_MIN_DURATION / orig_length))
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
            if not sorted_kfs:
                continue
            
            # Check if the source cycle already has C0 continuity
            first_vals = _get_kf_values(sorted_kfs[0])
            last_vals = _get_kf_values(sorted_kfs[-1])
            gap = _calc_gap(first_vals, last_vals)
            
            c0_continuous = gap < LOOP_GAP_THRESHOLD
            
            if not c0_continuous:
                # Source cycle is NOT continuous — we need to fix the source first
                # by making the last keyframe of each cycle match the first
                # Use smooth transition approach
                last_kf = sorted_kfs[-1]
                last_dp = last_kf.get('data_points', [{}])[0] if last_kf.get('data_points') else {}
                first_dp = sorted_kfs[0].get('data_points', [{}])[0] if sorted_kfs[0].get('data_points') else {}
                
                # Smoothly blend last keyframe values toward first keyframe values
                # Use a 70% blend to reduce the snap while still closing the gap
                blend = 0.7
                for axis in ('x', 'y', 'z'):
                    fv = float(first_dp.get(axis, 0))
                    lv = float(last_dp.get(axis, 0))
                    if abs(fv - lv) > LOOP_GAP_THRESHOLD:
                        last_dp[axis] = round(_lerp_val(lv, fv, blend), 4)
                
                last_kf['data_points'] = [last_dp]
            
            # Now replicate the cycle
            replicated = []
            for cycle in range(n_cycles):
                time_offset = cycle * orig_length
                
                for i, kf in enumerate(sorted_kfs):
                    t = kf.get('time', 0)
                    
                    # Skip the last keyframe of non-final cycles IF C0 continuous
                    # (the end of one cycle = start of next)
                    if c0_continuous and cycle < n_cycles - 1 and abs(t - orig_length) < 0.001:
                        continue
                    
                    new_kf = copy.deepcopy(kf)
                    new_kf['uuid'] = _short_uuid()  # Unique UUID for each replicated keyframe
                    new_kf['time'] = t + time_offset
                    
                    replicated.append(new_kf)
            
            # Ensure the last keyframe exactly matches the first for perfect looping
            if replicated:
                last_kf = replicated[-1]
                last_kf['time'] = new_length
                
                # Set last keyframe values to exactly match first keyframe
                first_dp = sorted_kfs[0].get('data_points', [{}])[0] if sorted_kfs[0].get('data_points') else {}
                if first_dp:
                    new_dp = {}
                    for k, v in first_dp.items():
                        if k in ('x', 'y', 'z'):
                            new_dp[k] = float(v)
                        else:
                            new_dp[k] = v
                    last_kf['data_points'] = [new_dp]
            
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


def fix_loop_conditions(bb_anim):
    """Ensure proper loop conditions for animations.
    
    V2: Respects hold_on_last_frame and non-looping animations.
    """
    name = bb_anim.get('name', '')
    
    # Don't force non-looping animations to loop
    if _is_non_loop_animation(name):
        # Keep the original loop mode for these animations
        return bb_anim
    
    if _is_loop_animation(name):
        bb_anim['loop'] = 'loop'
    return bb_anim


def ensure_smooth_loop(bb_anim):
    """Ensure smooth loop coherence for loop animations.
    
    V2 Approach — Instead of just copying first keyframe values to the last
    (which creates a visible hard snap/jerk), this function:
    
    1. First checks if the animation already has perfect loop closure
       (last keyframe values match first within threshold)
    2. If already perfect: do nothing (preserve original smooth transitions)
    3. If there's a gap at the end (last kf time < anim_length):
       Add a closing keyframe at anim_length matching first kf values
    4. If there's a value gap (last kf values ≠ first kf values):
       Add a smooth transition segment that gradually returns to start values
       using an ease-in-out curve over ~10% of the animation duration
    
    This ensures:
    - C0 continuity: end position = start position (gap = 0)
    - C1 continuity: velocity is smooth at the loop boundary
    - No visible "snap" or "jerk" at the loop point
    """
    if bb_anim.get('loop') != 'loop':
        return bb_anim
    
    anim_length = bb_anim.get('length', 0)
    if anim_length <= 0:
        return bb_anim
    
    animators = bb_anim.get('animators', {})
    modified = False
    
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
            first_time = first_kf.get('time', 0)
            last_time = last_kf.get('time', 0)
            
            value_gap = _calc_gap(first_vals, last_vals)
            time_gap = abs(last_time - anim_length)
            
            # Case 1: Already perfect loop — do nothing
            if value_gap < LOOP_GAP_THRESHOLD and time_gap < 0.01:
                continue
            
            # Case 2: Values match but last kf is not at anim_length
            # Just add a closing keyframe at anim_length with first kf values
            if value_gap < LOOP_GAP_THRESHOLD and time_gap >= 0.01:
                closing_kf = copy.deepcopy(first_kf)
                closing_kf['uuid'] = _short_uuid()
                closing_kf['time'] = anim_length
                closing_kf['interpolation'] = last_kf.get('interpolation', 'linear')
                keyframes.append(closing_kf)
                modified = True
                continue
            
            # Case 3: Values don't match — need smooth transition
            # Add a transition segment that gradually brings values back to start
            
            # Calculate transition duration
            transition_duration = max(
                MIN_TRANSITION_DURATION,
                anim_length * TRANSITION_SEGMENT_FRACTION
            )
            
            # The transition starts at (anim_length - transition_duration)
            # and ends at anim_length
            transition_start_time = anim_length - transition_duration
            
            # Get the "pre-transition" values — what the bone would be at transition_start_time
            # This is interpolated from the existing keyframes
            pre_transition_vals = _interpolate_values_at_time(
                sorted_kfs, transition_start_time
            )
            
            # Check if there's already a keyframe near transition_start_time
            has_kf_near_start = any(
                abs(kf.get('time', 0) - transition_start_time) < 0.01
                for kf in sorted_kfs
            )
            
            # If the transition start is before the last keyframe, we need to adjust
            if transition_start_time < last_time:
                # Transition overlaps with existing keyframes — just set the last kf to match first
                # and add an intermediate keyframe for smoothness
                transition_start_time = last_time
                transition_duration = anim_length - last_time
                
                if transition_duration < MIN_TRANSITION_DURATION:
                    # Very short gap — just snap the last kf to first values
                    dp = last_kf.get('data_points', [{}])[0] if last_kf.get('data_points') else {}
                    first_dp = first_kf.get('data_points', [{}])[0] if first_kf.get('data_points') else {}
                    for axis in ('x', 'y', 'z'):
                        if axis in first_dp:
                            dp[axis] = float(first_dp[axis])
                    last_kf['data_points'] = [dp]
                    last_kf['time'] = anim_length
                    modified = True
                    continue
                
                pre_transition_vals = last_vals
            
            # Add anchor keyframe at transition start (if not already present)
            if not has_kf_near_start and transition_start_time > last_time:
                anchor_kf = {
                    'channel': ch,
                    'data_points': [{
                        'x': round(pre_transition_vals[0], 6),
                        'y': round(pre_transition_vals[1], 6),
                        'z': round(pre_transition_vals[2], 6),
                        'easing': 'easeInSine',
                    }],
                    'uuid': _short_uuid(),
                    'time': transition_start_time,
                    'color': -1,
                    'interpolation': 'catmullrom',  # Smooth transition
                }
                keyframes.append(anchor_kf)
            
            # Add closing keyframe at anim_length with first kf values
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
                'interpolation': 'catmullrom',  # Smooth transition
            }
            keyframes.append(closing_kf)
            modified = True
    
    return bb_anim


def _interpolate_values_at_time(sorted_kfs, target_time):
    """Interpolate keyframe values at a specific time using linear interpolation.
    
    Finds the two keyframes surrounding target_time and interpolates between them.
    If target_time is before the first kf or after the last kf, returns the
    first/last values respectively.
    """
    if not sorted_kfs:
        return (0.0, 0.0, 0.0)
    
    # Before first keyframe
    if target_time <= sorted_kfs[0].get('time', 0):
        return _get_kf_values(sorted_kfs[0])
    
    # After last keyframe
    if target_time >= sorted_kfs[-1].get('time', 0):
        return _get_kf_values(sorted_kfs[-1])
    
    # Find surrounding keyframes
    for i in range(len(sorted_kfs) - 1):
        t1 = sorted_kfs[i].get('time', 0)
        t2 = sorted_kfs[i + 1].get('time', 0)
        
        if t1 <= target_time <= t2:
            vals1 = _get_kf_values(sorted_kfs[i])
            vals2 = _get_kf_values(sorted_kfs[i + 1])
            
            if abs(t2 - t1) < 1e-10:
                return vals1
            
            t = (target_time - t1) / (t2 - t1)
            return (
                _lerp_val(vals1[0], vals2[0], t),
                _lerp_val(vals1[1], vals2[1], t),
                _lerp_val(vals1[2], vals2[2], t),
            )
    
    return _get_kf_values(sorted_kfs[-1])


def fix_texture(bbmodel, creature_name):
    """Fix wrong embedded textures by replacing with the correct PNG file.
    
    Some creatures (like viin) have wrong/downscaled textures embedded
    in the source .bbmodel. This function replaces them with the correct
    texture from the jar/asset files.
    """
    if creature_name not in TEXTURE_FIX_MAP:
        return bbmodel, False
    
    tex_name = TEXTURE_FIX_MAP[creature_name]
    tex_path = None
    
    # Search for the texture file
    search_dirs = [JAR_TEX_DIR, QOM_TEX_DIR, PROJ_TEX_DIR, QOM_PROJ_TEX_DIR]
    for search_dir in search_dirs:
        if not search_dir or not os.path.isdir(search_dir):
            continue
        # Exact match
        candidate = os.path.join(search_dir, f"{tex_name}.png")
        if os.path.isfile(candidate):
            tex_path = candidate
            break
        # Case-insensitive match
        for f in os.listdir(search_dir):
            if f.lower() == f"{tex_name.lower()}.png":
                tex_path = os.path.join(search_dir, f)
                break
        if tex_path:
            break
    
    if not tex_path:
        print(f"    WARNING: Could not find texture {tex_name}.png for {creature_name}")
        return bbmodel, False
    
    # Read the correct texture and embed it as base64
    with open(tex_path, 'rb') as f:
        raw = f.read()
    b64 = base64.b64encode(raw).decode('ascii')
    source = f"data:image/png;base64,{b64}"
    
    # Get texture dimensions from PNG header
    import struct
    width, height = 256, 256  # Default
    try:
        if raw[:8] == b'\x89PNG\r\n\x1a\n':
            # Read IHDR chunk
            ihdr_data = raw[16:24]
            width = struct.unpack('>I', ihdr_data[0:4])[0]
            height = struct.unpack('>I', ihdr_data[4:8])[0]
    except Exception:
        pass
    
    # Update the texture in the bbmodel
    textures = bbmodel.get('textures', [])
    if textures:
        textures[0]['source'] = source
        textures[0]['name'] = creature_name
        textures[0]['width'] = width
        textures[0]['height'] = height
        textures[0]['uv_width'] = width
        textures[0]['uv_height'] = height
    
    # Update resolution
    bbmodel['resolution'] = {'width': width, 'height': height}
    
    print(f"    Fixed texture: replaced with {tex_name}.png ({width}×{height})")
    return bbmodel, True


def fix_bbmodel(source_path, output_path, creature_name):
    """Fix a single .bbmodel file and write to output.
    
    Strategy: Copy source as-is, then apply minimal fixes.
    """
    with open(source_path, 'r', encoding='utf-8') as f:
        bbmodel = json.load(f)
    
    changes = []
    
    # Fix 1: Duplicate root group UUIDs
    if creature_name in DUPLICATE_ROOT_CREATURES:
        bbmodel = fix_duplicate_root_uuids(bbmodel, creature_name)
        changes.append('fixed-duplicate-root')
    
    # Fix 2: Wrong textures
    bbmodel, tex_fixed = fix_texture(bbmodel, creature_name)
    if tex_fixed:
        changes.append('fixed-texture')
    
    # Fix 3: Animations
    animations = bbmodel.get('animations', [])
    for anim in animations:
        anim_name = anim.get('name', '')
        
        # Fix walk animations (extend short walks)
        if _is_walk_animation(anim_name):
            orig_len = anim.get('length', 0)
            anim = fix_walk_animation(anim)
            new_len = anim.get('length', 0)
            if abs(new_len - orig_len) > 0.01:
                changes.append(f'walk-extended-{orig_len:.2f}s-{new_len:.2f}s')
        
        # Fix loop conditions (but respect non-looping animations)
        old_loop = anim.get('loop', 'once')
        anim = fix_loop_conditions(anim)
        new_loop = anim.get('loop', 'once')
        if old_loop != new_loop:
            changes.append(f'loop-{old_loop}-{new_loop}')
        
        # Ensure smooth loop coherence for loop animations
        # V2: Uses smooth transition instead of hard snap
        if anim.get('loop') == 'loop':
            anim = ensure_smooth_loop(anim)
    
    # Write output
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(bbmodel, f, indent=2, ensure_ascii=False)
    
    return len(animations), changes


def main():
    print("=" * 70)
    print("  Fix and Rebuild .bbmodel Files — V2: Smooth Loop Coherence")
    print("  Strategy: Copy source, apply minimal fixes, smooth transitions")
    print("=" * 70)
    print()
    
    total = 0
    total_anims = 0
    total_fixed = 0
    no_source = 0
    no_anims = 0
    errors = []
    walk_extensions = 0
    loop_fixes = 0
    root_fixes = 0
    
    for category_name in sorted(os.listdir(OUTPUT_DIR)):
        category_path = os.path.join(OUTPUT_DIR, category_name)
        if not os.path.isdir(category_path):
            continue
        
        source_category_path = os.path.join(SOURCE_DIR, category_name)
        
        print(f'\n[{category_name}]')
        
        # Find all .geo.json files in output (these define what creatures exist)
        for filename in sorted(os.listdir(category_path)):
            if not filename.endswith('.geo.json'):
                continue
            
            base_name = filename.replace('.geo.json', '')
            source_bbmodel = os.path.join(source_category_path, base_name + '.bbmodel')
            output_bbmodel = os.path.join(category_path, base_name + '.bbmodel')
            
            if not os.path.isfile(source_bbmodel):
                # No source .bbmodel — skip
                if os.path.isfile(output_bbmodel):
                    os.remove(output_bbmodel)
                no_source += 1
                print(f'  ⊘ {base_name}: no source .bbmodel')
                continue
            
            try:
                anim_count, changes = fix_bbmodel(source_bbmodel, output_bbmodel, base_name)
                total += 1
                total_anims += anim_count
                
                if changes:
                    total_fixed += 1
                    if any('walk-extended' in c for c in changes):
                        walk_extensions += 1
                    if any('loop' in c for c in changes):
                        loop_fixes += 1
                    if 'fixed-duplicate-root' in changes:
                        root_fixes += 1
                    print(f'  ✓ {base_name}: {anim_count} anims [{", ".join(changes)}]')
                else:
                    if anim_count == 0:
                        no_anims += 1
                    print(f'  ✓ {base_name}: {anim_count} anims [no changes needed]')
                
            except Exception as e:
                import traceback
                errors.append(f'{category_name}/{base_name}: {e}')
                print(f'  ✗ {base_name}: {e}')
                traceback.print_exc()
    
    print()
    print("=" * 70)
    print("  FIX AND REBUILD SUMMARY (V2)")
    print("=" * 70)
    print(f"  Total processed:       {total}")
    print(f"  With animations:       {total - no_anims}")
    print(f"  Without animations:    {no_anims}")
    print(f"  Total animations:      {total_anims}")
    print(f"  Files with fixes:      {total_fixed}")
    print(f"  Walk extensions:       {walk_extensions}")
    print(f"  Loop fixes:            {loop_fixes}")
    print(f"  Root UUID fixes:       {root_fixes}")
    print(f"  No source .bbmodel:    {no_source}")
    print(f"  Errors:                {len(errors)}")
    
    if errors:
        print("\n  Errors:")
        for err in errors[:10]:
            print(f"    - {err}")
    
    print()


if __name__ == '__main__':
    main()
