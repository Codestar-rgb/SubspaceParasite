#!/usr/bin/env python3
"""Add combined animations: kirin idle_shaking, heblu fly_vomit."""
import json, math, copy

def add_kirin_idle_shaking(bbmodel_path):
    """Add idle_shaking animation = idle + mainbody trembling (2.95 rad/tick)."""
    with open(bbmodel_path) as f:
        d = json.load(f)
    
    idle = next(a for a in d['animations'] if 'idle' in a['name'])
    # Create idle_shaking as copy of idle
    shaking = copy.deepcopy(idle)
    shaking['name'] = shaking['name'].replace('.idle', '.idle_shaking')
    shaking['uuid'] = None  # will be regenerated
    
    import uuid
    shaking['uuid'] = str(uuid.uuid4())
    
    # Add mainbody trembling to the idle_shaking animation
    # Java: mainbody.field_82906_o = sin(ageInTicks * 2.95) * 0.0891
    #       mainbody.field_82907_q = sin(ageInTicks * 2.95) * 0.0891
    # field_82906_o = rotateAngleX, field_82907_q = rotateAngleY
    # Convert rad to deg: 0.0891 rad = 5.1°
    
    # Find mainbody animator
    for aname, adat in shaking['animators'].items():
        if adat.get('name') == 'mainbody':
            # Add trembling keyframes
            length = shaking['length']
            n_samples = 40
            dt = length / (n_samples - 1)
            trembling_kfs = []
            for i in range(n_samples):
                t = i * dt
                age_in_ticks = t * 20.0
                # Trembling motion (high frequency)
                x_val = math.degrees(math.sin(age_in_ticks * 2.95) * 0.0891)
                y_val = math.degrees(math.sin(age_in_ticks * 2.95) * 0.0891)
                trembling_kfs.append({
                    'channel': 'rotation',
                    'data_points': [{'x': round(x_val, 4), 'y': round(y_val, 4), 'z': 0.0}],
                    'uuid': str(uuid.uuid4()),
                    'time': round(t, 4),
                    'color': -1,
                    'interpolation': 'catmullrom',
                })
            adat['keyframes'] = trembling_kfs
            break
    
    d['animations'].append(shaking)
    with open(bbmodel_path, 'w') as f:
        json.dump(d, f)
    print(f'  Added idle_shaking to {bbmodel_path}')

def add_heblu_fly_vomit(bbmodel_path, vomit_anim_path):
    """Add fly_vomit = fly + vomit (jointN1-N5 head shaking) combined."""
    with open(bbmodel_path) as f:
        d = json.load(f)
    with open(vomit_anim_path) as f:
        vomit_up = json.load(f)
    
    fly = next(a for a in d['animations'] if a['name'].endswith('.fly'))
    fly_vomit = copy.deepcopy(fly)
    fly_vomit['name'] = fly_vomit['name'].replace('.fly', '.fly_vomit')
    import uuid
    fly_vomit['uuid'] = str(uuid.uuid4())
    
    # Get vomit bone data (jointN1-N5) from upstream vomit animation
    vomit_bones = vomit_up['animations']['animation.heblu.vomit']['bones']
    
    # Add vomit motion to fly_vomit
    # Find bone animators by name and add vomit keyframes
    for aname, adat in fly_vomit['animators'].items():
        bone_name = adat.get('name', '')
        if bone_name in vomit_bones:
            vomit_data = vomit_bones[bone_name]
            if isinstance(vomit_data, dict) and 'rotation' in vomit_data:
                rot = vomit_data['rotation']
                if isinstance(rot, dict):
                    # Format: {"x": {"0.0": val, "1.0": val}, "y": {...}, ...}
                    # Convert to keyframes
                    all_times = set()
                    for ax in ['x','y','z']:
                        if ax in rot:
                            all_times.update(float(t) for t in rot[ax].keys())
                    all_times = sorted(all_times)
                    
                    new_kfs = []
                    for t in all_times:
                        x_val = rot.get('x', {}).get(f'{t:.4f}', rot.get('x', {}).get(f'{t:.1f}', 0.0))
                        y_val = rot.get('y', {}).get(f'{t:.4f}', rot.get('y', {}).get(f'{t:.1f}', 0.0))
                        z_val = rot.get('z', {}).get(f'{t:.4f}', rot.get('z', {}).get(f'{t:.1f}', 0.0))
                        new_kfs.append({
                            'channel': 'rotation',
                            'data_points': [{'x': float(x_val), 'y': float(y_val), 'z': float(z_val)}],
                            'uuid': str(uuid.uuid4()),
                            'time': round(t, 4),
                            'color': -1,
                            'interpolation': 'catmullrom',
                        })
                    if new_kfs:
                        # Merge with existing fly keyframes for this bone
                        existing_kfs = adat.get('keyframes', [])
                        # Keep non-rotation keyframes, replace rotation
                        non_rot = [k for k in existing_kfs if k.get('channel') != 'rotation']
                        adat['keyframes'] = non_rot + new_kfs
                        adat['keyframes'].sort(key=lambda k: k['time'])
    
    d['animations'].append(fly_vomit)
    with open(bbmodel_path, 'w') as f:
        json.dump(d, f)
    print(f'  Added fly_vomit to {bbmodel_path}')

# Add kirin idle_shaking
print('=== kirin ===')
add_kirin_idle_shaking('/home/z/my-project/GFL/derived/kirin.bbmodel')

# Add heblu fly_vomit
print('=== heblu ===')
add_heblu_fly_vomit('/home/z/my-project/GFL/derived/heblu.bbmodel',
                    '/tmp/my-project/subspace-work/SubspaceParasite/MDO-SRP-SRC/derived/heblu.animation.json')
