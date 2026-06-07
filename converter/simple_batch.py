#!/usr/bin/env python3
"""Simple batch conversion script - minimal overhead."""
import sys, os, time, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bbmodel_animation_converter_v18 import BBModelAnimationConverter, ConverterConfig
from bbmodel_to_geo import BBModelToGeo

INPUT_DIR = "/home/z/my-project/MROLF-TGNBF"
OUTPUT_DIR = "/home/z/my-project/db/output"
SKIP_DIRS = {'bedrock', 'fix_heblu_skin_rotation.py'}

# Same config as batch_convert_all.py but minimal
config = ConverterConfig(
    enable_c1_enforcement=True,
    walk_min_output_keyframes=16,
)
converter = BBModelAnimationConverter(config)
geo_converter = BBModelToGeo()

# Find all bbmodel files
bbmodel_files = []
for root, dirs, files in os.walk(INPUT_DIR):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
    for fname in sorted(files):
        if fname.endswith('.bbmodel'):
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, INPUT_DIR)
            bbmodel_files.append(rel_path)

bbmodel_files.sort()
print(f"Found {len(bbmodel_files)} files", flush=True)

errors = 0
start = time.time()

for i, rel_path in enumerate(bbmodel_files):
    bbmodel_path = os.path.join(INPUT_DIR, rel_path)
    category = os.path.dirname(rel_path)
    name = os.path.basename(rel_path).replace('.bbmodel', '')
    out_dir = os.path.join(OUTPUT_DIR, category) if category else OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    
    try:
        # Geo conversion
        geo_result = geo_converter.convert_bbmodel(bbmodel_path, out_dir)
        
        # Fix grounding
        geo_path = geo_result.get('geo_path')
        if geo_path and os.path.exists(geo_path):
            with open(geo_path, 'r') as f:
                geo_data = json.load(f)
            geom_list = geo_data.get('minecraft:geometry', [])
            if geom_list:
                bones = geom_list[0].get('bones', [])
                desc = geom_list[0].get('description', {})
                min_y = float('inf')
                has_cubes = False
                for bone in bones:
                    for cube in bone.get('cubes', []):
                        origin = cube.get('origin', [0, 0, 0])
                        min_y = min(min_y, origin[1])
                        has_cubes = True
                if has_cubes and min_y > 0.5:
                    for bone in bones:
                        for cube in bone.get('cubes', []):
                            origin = cube.get('origin', [0, 0, 0])
                            cube['origin'] = [origin[0], origin[1] - min_y, origin[2]]
                        pivot = bone.get('pivot')
                        if pivot:
                            bone['pivot'] = [pivot[0], pivot[1] - min_y, pivot[2]]
                    vbo = desc.get('visible_bounds_offset', [0, 0, 0])
                    desc['visible_bounds_offset'] = [vbo[0], vbo[1] - min_y, vbo[2]]
                    with open(geo_path, 'w') as f:
                        json.dump(geo_data, f, indent=2, ensure_ascii=False)
        
        # Animation conversion
        anim_output = os.path.join(out_dir, f"{name}.animation.json")
        if os.path.exists(anim_output):
            os.remove(anim_output)
        result = converter.convert_file(bbmodel_path, anim_output)
        anim_count = result['stats']['total_animations']
        
        print(f"[{i+1:3d}/{len(bbmodel_files)}] {category}/{name}: {anim_count} anims", flush=True)
    except Exception as e:
        errors += 1
        print(f"[{i+1:3d}/{len(bbmodel_files)}] {category}/{name}: ERROR {e}", flush=True)

elapsed = time.time() - start
print(f"\nDone! {len(bbmodel_files)} models, {errors} errors, {elapsed:.0f}s", flush=True)
