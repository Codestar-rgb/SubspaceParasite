#!/usr/bin/env python3
"""
Batch Convert to MODSRP — Full Pipeline
========================================
Takes all .bbmodel files from MCMOD-SRP and converts them through the full
pipeline using the CURRENT converter:

  1. .bbmodel → bbmodel_to_geo → geo.json + PNG
  2. .bbmodel → animation_converter_v21 → .animation.json
  3. geo.json + animation.json + PNG → bbmodel_generator → NEW .bbmodel
  4. Save results to /home/z/my-project/MODSRP/

After successful conversion, MROLF-TGNBF and MROLF-TGNBF-OUTPUT folders
will be deleted.
"""

import json
import os
import sys
import time
import traceback

# ============================================================================
# Configuration
# ============================================================================

INPUT_DIR = "/home/z/my-project/MCMOD-SRP"
OUTPUT_DIR = "/home/z/my-project/converter/output_modsrp"
MODSRP_DIR = "/home/z/my-project/MODSRP"
CONVERTER_DIR = os.path.dirname(os.path.abspath(__file__))

if CONVERTER_DIR not in sys.path:
    sys.path.insert(0, CONVERTER_DIR)


def main():
    print("=" * 70)
    print("  Batch Convert to MODSRP — Full Pipeline")
    print("  MCMOD-SRP .bbmodel → geo+anim+tex → NEW .bbmodel → MODSRP/")
    print("=" * 70)
    print()

    if not os.path.isdir(INPUT_DIR):
        print(f"ERROR: Input directory not found: {INPUT_DIR}")
        sys.exit(1)

    # Import converters
    from bbmodel_to_geo import BBModelToGeo
    from converter_v21 import BBModelAnimationConverterV21
    from bbmodel_generator import BBModelGenerator

    geo_converter = BBModelToGeo()
    anim_converter = BBModelAnimationConverterV21()
    bbmodel_generator = BBModelGenerator()

    print("  [OK] Loaded BBModelToGeo")
    print("  [OK] Loaded BBModelAnimationConverterV21")
    print("  [OK] Loaded BBModelGenerator")
    print()

    # Find all .bbmodel files in MCMOD-SRP
    bbmodel_files = []
    for root, dirs, files in os.walk(INPUT_DIR):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fname in sorted(files):
            if fname.endswith('.bbmodel'):
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, INPUT_DIR)
                bbmodel_files.append(rel_path)

    bbmodel_files.sort()
    print(f"  Found {len(bbmodel_files)} .bbmodel files in MCMOD-SRP")
    print(f"  Intermediate output: {OUTPUT_DIR}")
    print(f"  Final output: {MODSRP_DIR}")
    print()

    # Clean output directories
    import shutil
    for d in [OUTPUT_DIR, MODSRP_DIR]:
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)

    # Statistics
    stats = {
        'total': len(bbmodel_files),
        'geo_ok': 0,
        'geo_fail': 0,
        'anim_ok': 0,
        'anim_no_anim': 0,
        'anim_fail': 0,
        'bbmodel_ok': 0,
        'bbmodel_fail': 0,
        'tex_ok': 0,
        'errors': [],
        'categories': {},
    }

    start_time = time.time()

    for i, rel_path in enumerate(bbmodel_files, 1):
        bbmodel_path = os.path.join(INPUT_DIR, rel_path)
        category = os.path.dirname(rel_path)
        name = os.path.basename(rel_path).replace('.bbmodel', '')
        intermediate_dir = os.path.join(OUTPUT_DIR, category) if category else OUTPUT_DIR
        final_dir = os.path.join(MODSRP_DIR, category) if category else MODSRP_DIR

        os.makedirs(intermediate_dir, exist_ok=True)
        os.makedirs(final_dir, exist_ok=True)

        # Track categories
        if category not in stats['categories']:
            stats['categories'][category] = {'total': 0, 'ok': 0, 'fail': 0}
        stats['categories'][category]['total'] += 1

        print(f"  [{i:3d}/{stats['total']}] {category}/{name}...", end=" ", flush=True)
        status_parts = []

        try:
            # -----------------------------------------------------------
            # Step 1: Convert .bbmodel → geo.json + PNG
            # -----------------------------------------------------------
            geo_result = geo_converter.convert_bbmodel(bbmodel_path, intermediate_dir)

            if not geo_result.get('success'):
                stats['geo_fail'] += 1
                err = geo_result.get('error', 'unknown')
                status_parts.append(f"GEO_FAIL: {err}")
                stats['errors'].append(f"{category}/{name}: geo failed: {err}")
                stats['categories'][category]['fail'] += 1
                print(" | ".join(status_parts))
                continue

            stats['geo_ok'] += 1
            s = geo_result['stats']
            status_parts.append(f"geo({s['bones']}b)")

            if s.get('has_texture'):
                stats['tex_ok'] += 1
                status_parts.append("tex=YES")
            else:
                status_parts.append("tex=NO")

            geo_path = geo_result.get('geo_path')
            tex_path = geo_result.get('texture_path')

            # Fix model grounding in geo.json
            if geo_path and os.path.exists(geo_path):
                grounding_result = _fix_model_grounding(geo_path)
                if grounding_result['shifted']:
                    status_parts.append(f"grounded(-{grounding_result['y_shift']:.1f})")

                # Fix UV bounds
                uv_result = _fix_uv_bounds(geo_path)
                if uv_result['fixed_faces'] > 0:
                    status_parts.append(f"uv_fix+{uv_result['fixed_faces']}")

            # -----------------------------------------------------------
            # Step 2: Convert animations using v21 converter
            # -----------------------------------------------------------
            anim_output_path = os.path.join(intermediate_dir, f"{name}.animation.json")
            if os.path.exists(anim_output_path):
                os.remove(anim_output_path)

            anim_json = None
            try:
                result = anim_converter.convert_file(bbmodel_path, anim_output_path)
                anim_count = result['stats']['total_animations']

                if anim_count == 0:
                    stats['anim_no_anim'] += 1
                    status_parts.append("no_anim")
                else:
                    stats['anim_ok'] += 1
                    status_parts.append(f"anims={anim_count}")

                # Load the animation JSON for bbmodel generation
                if os.path.exists(anim_output_path):
                    with open(anim_output_path, 'r', encoding='utf-8') as f:
                        anim_json = json.load(f)

            except Exception as e:
                stats['anim_fail'] += 1
                status_parts.append(f"ANIM_ERR: {e}")
                # Continue without animations

            # -----------------------------------------------------------
            # Step 3: Generate NEW .bbmodel from geo+anim+texture
            # -----------------------------------------------------------
            # Load geo.json
            with open(geo_path, 'r', encoding='utf-8') as f:
                geo_data = json.load(f)

            # Convert geo.json format for bbmodel_generator
            # bbmodel_generator expects {"model": {"bones": [...], "texture_width": ..., ...}}
            geo_model = _convert_geo_for_generator(geo_data)

            # Find texture
            texture_path_for_gen = tex_path if tex_path and os.path.exists(tex_path) else None

            # Generate .bbmodel
            bbmodel = bbmodel_generator.generate(
                geo_model,
                anim_json=anim_json,
                texture_path=texture_path_for_gen,
                texture_name=name,
                namespace='srparasites',
            )

            # Save to MODSRP
            out_path = os.path.join(final_dir, f"{name}.bbmodel")
            bbmodel_generator.save(bbmodel, out_path)

            stats['bbmodel_ok'] += 1
            stats['categories'][category]['ok'] += 1

            elements = bbmodel.get('elements', [])
            animations = bbmodel.get('animations', [])
            file_size = os.path.getsize(out_path)
            status_parts.append(f"bbmodel({len(elements)}e, {len(animations)}a, {file_size/1024:.0f}KB)")

        except Exception as e:
            stats['bbmodel_fail'] += 1
            stats['categories'][category]['fail'] += 1
            status_parts.append(f"ERROR: {e}")
            stats['errors'].append(f"{category}/{name}: {e}")

        print(" | ".join(status_parts))

        # Periodic garbage collection
        if i % 10 == 0:
            import gc
            gc.collect()

    elapsed = time.time() - start_time

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print()
    print("=" * 70)
    print("  BATCH CONVERSION SUMMARY (MODSRP)")
    print("=" * 70)
    print(f"  Total models:           {stats['total']}")
    print()
    print(f"  --- Step 1: Geometry ---")
    print(f"  Geo converted OK:       {stats['geo_ok']}")
    print(f"  Geo failed:             {stats['geo_fail']}")
    print(f"  Textures extracted:     {stats['tex_ok']}")
    print()
    print(f"  --- Step 2: Animations ---")
    print(f"  Models with animations: {stats['anim_ok']}")
    print(f"  Static models:          {stats['anim_no_anim']}")
    print(f"  Animation failures:     {stats['anim_fail']}")
    print()
    print(f"  --- Step 3: Final .bbmodel ---")
    print(f"  BBModel generated OK:   {stats['bbmodel_ok']}")
    print(f"  BBModel failures:       {stats['bbmodel_fail']}")
    print()
    print(f"  --- By Category ---")
    for cat in sorted(stats['categories'].keys()):
        cs = stats['categories'][cat]
        print(f"  {cat}: {cs['ok']}/{cs['total']} OK")
    print()
    print(f"  --- Output ---")
    print(f"  Final output:   {MODSRP_DIR}")
    print(f"  Intermediate:   {OUTPUT_DIR}")
    print(f"  Elapsed time:   {elapsed:.1f}s")

    if stats['errors']:
        print(f"\n  Errors ({len(stats['errors'])}):")
        for e in stats['errors'][:15]:
            print(f"    X {e}")
        if len(stats['errors']) > 15:
            print(f"    ... and {len(stats['errors']) - 15} more")

    print()
    print("=" * 70)

    # ---------------------------------------------------------------
    # Delete MROLF-TGNBF and MROLF-TGNBF-OUTPUT
    # ---------------------------------------------------------------
    print()
    print("  Cleaning up old folders...")
    for folder in ["/home/z/my-project/MROLF-TGNBF", "/home/z/my-project/MROLF-TGNBF-OUTPUT"]:
        if os.path.exists(folder):
            try:
                shutil.rmtree(folder)
                print(f"  [DELETED] {folder}")
            except Exception as e:
                print(f"  [FAILED] Could not delete {folder}: {e}")
        else:
            print(f"  [SKIP] {folder} does not exist")

    # Clean up intermediate output
    if os.path.exists(OUTPUT_DIR):
        try:
            shutil.rmtree(OUTPUT_DIR)
            print(f"  [DELETED] Intermediate: {OUTPUT_DIR}")
        except Exception as e:
            print(f"  [FAILED] Could not delete {OUTPUT_DIR}: {e}")

    print()
    print("=" * 70)
    print("  DONE — MODSRP batch conversion complete!")
    print(f"  Output: {MODSRP_DIR}")
    print("=" * 70)

    sys.exit(0 if stats['bbmodel_fail'] == 0 else 1)


def _convert_geo_for_generator(geo_data: dict) -> dict:
    """Convert Bedrock geo.json format to the format expected by BBModelGenerator.

    BBModelGenerator expects:
    {
        "model": {
            "identifier": "model.name",
            "texture_width": 256,
            "texture_height": 256,
            "bones": [...]
        }
    }

    Bedrock geo.json is:
    {
        "format_version": "1.12.0",
        "minecraft:geometry": [{
            "description": {
                "identifier": "geometry.model.name",
                "texture_width": 256,
                "texture_height": 256,
                ...
            },
            "bones": [...]
        }]
    }
    """
    geom_list = geo_data.get('minecraft:geometry', [])
    if geom_list:
        geom = geom_list[0]
        desc = geom.get('description', {})
        identifier = desc.get('identifier', 'model.unknown')
        # Convert "geometry.model.name" -> "model.name"
        if identifier.startswith('geometry.'):
            identifier = identifier[len('geometry.'):]

        return {
            'model': {
                'identifier': identifier,
                'texture_width': desc.get('texture_width', 256),
                'texture_height': desc.get('texture_height', 256),
                'bones': geom.get('bones', []),
            }
        }
    else:
        # Already in the expected format
        return geo_data


def _fix_model_grounding(geo_path: str) -> dict:
    """Fix model floating by shifting geometry down so lowest point is at Y=0."""
    try:
        with open(geo_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return {'shifted': False, 'y_shift': 0.0}

    geom_list = data.get('minecraft:geometry', [])
    if not geom_list:
        return {'shifted': False, 'y_shift': 0.0}

    geom = geom_list[0]
    bones = geom.get('bones', [])
    desc = geom.get('description', {})

    min_y = float('inf')
    has_cubes = False
    for bone in bones:
        for cube in bone.get('cubes', []):
            origin = cube.get('origin', [0, 0, 0])
            min_y = min(min_y, origin[1])
            has_cubes = True

    if not has_cubes or min_y == float('inf') or min_y <= 0.5:
        return {'shifted': False, 'y_shift': 0.0}

    y_shift = min_y

    for bone in bones:
        for cube in bone.get('cubes', []):
            origin = cube.get('origin', [0, 0, 0])
            cube['origin'] = [origin[0], origin[1] - y_shift, origin[2]]
        pivot = bone.get('pivot')
        if pivot:
            bone['pivot'] = [pivot[0], pivot[1] - y_shift, pivot[2]]

    vbo = desc.get('visible_bounds_offset', [0, 0, 0])
    desc['visible_bounds_offset'] = [vbo[0], vbo[1] - y_shift, vbo[2]]

    try:
        with open(geo_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return {'shifted': True, 'y_shift': y_shift}
    except Exception:
        return {'shifted': False, 'y_shift': 0.0}


def _fix_uv_bounds(geo_path: str) -> dict:
    """Fix UV coordinates that extend beyond texture bounds."""
    try:
        with open(geo_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return {'fixed_faces': 0}

    geom_list = data.get('minecraft:geometry', [])
    if not geom_list:
        return {'fixed_faces': 0}

    geom = geom_list[0]
    desc = geom.get('description', {})
    tex_w = desc.get('texture_width', 256)
    tex_h = desc.get('texture_height', 256)
    bones = geom.get('bones', [])

    fixed = 0
    margin = 0.5

    for bone in bones:
        for cube in bone.get('cubes', []):
            uv = cube.get('uv', {})
            for face_name, face_uv in uv.items():
                if not isinstance(face_uv, dict):
                    continue
                u = face_uv.get('uv', [0, 0])
                s = face_uv.get('uv_size', [0, 0])

                u_clamped = [
                    max(-margin, min(u[0], tex_w - margin)),
                    max(-margin, min(u[1], tex_h - margin))
                ]
                s_clamped = [
                    max(0.1, min(s[0], tex_w - u_clamped[0] + margin)),
                    max(0.1, min(s[1], tex_h - u_clamped[1] + margin))
                ]

                if u_clamped != u or s_clamped != s:
                    face_uv['uv'] = u_clamped
                    face_uv['uv_size'] = s_clamped
                    fixed += 1

    if fixed > 0:
        try:
            with open(geo_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    return {'fixed_faces': fixed}


if __name__ == "__main__":
    main()
