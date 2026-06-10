#!/usr/bin/env python3
"""
Batch Convert to MDO-SRP — geo.json + animation.json + PNG → .bbmodel
======================================================================
Converts all model sets from MDO-SRP-SRC into Blockbench .bbmodel files
in MDO-SRP using the BBModelGenerator.

Input (MDO-SRP-SRC/category/name):
  - name.geo.json        (Bedrock geometry)
  - name.animation.json  (GeckoLib animation, optional)
  - name.png             (texture, optional)

Output (MDO-SRP/category/name.bbmodel):
  - name.bbmodel         (Blockbench project file)
"""

import json
import os
import sys
import time
import traceback

# ============================================================================
# Configuration
# ============================================================================

INPUT_DIR = "/home/z/my-project/MDO-SRP-SRC"
OUTPUT_DIR = "/home/z/my-project/MDO-SRP"
CONVERTER_DIR = os.path.dirname(os.path.abspath(__file__))

if CONVERTER_DIR not in sys.path:
    sys.path.insert(0, CONVERTER_DIR)


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


def main():
    print("=" * 70)
    print("  Batch Convert to MDO-SRP — geo+anim+tex → .bbmodel")
    print("=" * 70)
    print()

    if not os.path.isdir(INPUT_DIR):
        print(f"ERROR: Input directory not found: {INPUT_DIR}")
        sys.exit(1)

    # Import converter
    from bbmodel_generator import BBModelGenerator
    bbmodel_generator = BBModelGenerator()
    print("  [OK] Loaded BBModelGenerator")
    print()

    # Find all .geo.json files (each represents a model)
    geo_files = []
    for root, dirs, files in os.walk(INPUT_DIR):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fname in sorted(files):
            if fname.endswith('.geo.json'):
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, INPUT_DIR)
                geo_files.append(rel_path)

    geo_files.sort()
    print(f"  Found {len(geo_files)} models in MDO-SRP-SRC")
    print(f"  Output: {OUTPUT_DIR}")
    print()

    # Clean output directory
    import shutil
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Statistics
    stats = {
        'total': len(geo_files),
        'ok': 0,
        'fail': 0,
        'has_anim': 0,
        'has_tex': 0,
        'errors': [],
        'categories': {},
    }

    start_time = time.time()

    for i, rel_path in enumerate(geo_files, 1):
        category = os.path.dirname(rel_path)
        name = os.path.basename(rel_path).replace('.geo.json', '')
        src_dir = os.path.join(INPUT_DIR, category) if category else INPUT_DIR
        out_dir = os.path.join(OUTPUT_DIR, category) if category else OUTPUT_DIR

        os.makedirs(out_dir, exist_ok=True)

        # Track categories
        if category not in stats['categories']:
            stats['categories'][category] = {'total': 0, 'ok': 0, 'fail': 0}
        stats['categories'][category]['total'] += 1

        print(f"  [{i:3d}/{stats['total']}] {category}/{name}...", end=" ", flush=True)
        status_parts = []

        try:
            # Load geo.json
            geo_path = os.path.join(src_dir, f"{name}.geo.json")
            with open(geo_path, 'r', encoding='utf-8') as f:
                geo_data = json.load(f)

            # Convert to BBModelGenerator format
            geo_model = _convert_geo_for_generator(geo_data)

            # Load animation.json (optional)
            anim_json = None
            anim_path = os.path.join(src_dir, f"{name}.animation.json")
            if os.path.exists(anim_path):
                try:
                    with open(anim_path, 'r', encoding='utf-8') as f:
                        anim_json = json.load(f)
                    anim_count = len(anim_json.get('animations', {}))
                    stats['has_anim'] += 1
                    status_parts.append(f"anims={anim_count}")
                except Exception as e:
                    status_parts.append(f"anim_err({e})")
            else:
                status_parts.append("no_anim")

            # Find texture PNG (optional)
            tex_path = os.path.join(src_dir, f"{name}.png")
            if os.path.exists(tex_path):
                stats['has_tex'] += 1
                status_parts.append("tex=YES")
            else:
                tex_path = None
                status_parts.append("tex=NO")

            # Generate .bbmodel
            bbmodel = bbmodel_generator.generate(
                geo_model,
                anim_json=anim_json,
                texture_path=tex_path,
                texture_name=name,
                namespace='srparasites',
            )

            # Save
            out_path = os.path.join(out_dir, f"{name}.bbmodel")
            bbmodel_generator.save(bbmodel, out_path)

            stats['ok'] += 1
            stats['categories'][category]['ok'] += 1

            elements = bbmodel.get('elements', [])
            animations = bbmodel.get('animations', [])
            file_size = os.path.getsize(out_path)
            status_parts.append(f"bbmodel({len(elements)}e, {len(animations)}a, {file_size/1024:.0f}KB)")

        except Exception as e:
            stats['fail'] += 1
            stats['categories'][category]['fail'] += 1
            status_parts.append(f"ERROR: {e}")
            stats['errors'].append(f"{category}/{name}: {traceback.format_exc()}")

        print(" | ".join(status_parts))

        # Periodic GC
        if i % 20 == 0:
            import gc
            gc.collect()

    elapsed = time.time() - start_time

    # Summary
    print()
    print("=" * 70)
    print("  BATCH CONVERSION SUMMARY (MDO-SRP)")
    print("=" * 70)
    print(f"  Total models:           {stats['total']}")
    print(f"  Converted OK:           {stats['ok']}")
    print(f"  Failed:                 {stats['fail']}")
    print(f"  With animations:        {stats['has_anim']}")
    print(f"  With textures:          {stats['has_tex']}")
    print()
    print(f"  --- By Category ---")
    for cat in sorted(stats['categories'].keys()):
        cs = stats['categories'][cat]
        print(f"  {cat}: {cs['ok']}/{cs['total']} OK")
    print()
    print(f"  Output: {OUTPUT_DIR}")
    print(f"  Elapsed: {elapsed:.1f}s")

    if stats['errors']:
        print(f"\n  Errors ({len(stats['errors'])}):")
        for e in stats['errors'][:10]:
            # Show just the first line of each error
            first_line = e.split('\n')[0]
            print(f"    X {first_line}")
        if len(stats['errors']) > 10:
            print(f"    ... and {len(stats['errors']) - 10} more")

    print()
    print("=" * 70)
    print("  DONE — MDO-SRP batch conversion complete!")
    print(f"  Output: {OUTPUT_DIR}")
    print("=" * 70)

    sys.exit(0 if stats['fail'] == 0 else 1)


if __name__ == "__main__":
    main()
