#!/usr/bin/env python3
"""
Regenerate MCMOD-SRP - Create .bbmodel files from converter output
====================================================================
Reads the geo.json + animation.json + PNG files from db/output/ and
regenerates the .bbmodel files for the MCMOD-SRP folder using
BBModelGenerator.

This is the final step in the pipeline:
  .bbmodel → geo.json + animation.json + PNG → .bbmodel (round-trip)
"""

import json
import os
import sys
import time
import traceback

# Add converter directory to path
CONVERTER_DIR = os.path.dirname(os.path.abspath(__file__))
if CONVERTER_DIR not in sys.path:
    sys.path.insert(0, CONVERTER_DIR)

BASE_DIR = os.path.join(CONVERTER_DIR, "..")
OUTPUT_DIR = os.path.join(BASE_DIR, "db", "output")
SRP_DIR = os.path.join(BASE_DIR, "MCMOD-SRP")


def main():
    print("=" * 70)
    print("  Regenerate MCMOD-SRP - .bbmodel from Converter Output")
    print("=" * 70)
    print()

    if not os.path.isdir(OUTPUT_DIR):
        print(f"ERROR: Output directory not found: {OUTPUT_DIR}")
        sys.exit(1)

    from bbmodel_generator import BBModelGenerator
    gen = BBModelGenerator()
    print("  [OK] Loaded BBModelGenerator")

    # Find all .geo.json files in output
    geo_files = []
    for root, dirs, files in os.walk(OUTPUT_DIR):
        for f in sorted(files):
            if f.endswith('.geo.json'):
                rel_path = os.path.relpath(os.path.join(root, f), OUTPUT_DIR)
                geo_files.append(rel_path)

    print(f"  Found {len(geo_files)} .geo.json files to process")
    print()

    # Clean and create SRP directory
    if os.path.exists(SRP_DIR):
        import shutil
        shutil.rmtree(SRP_DIR)
    os.makedirs(SRP_DIR, exist_ok=True)

    stats = {
        'total': len(geo_files),
        'ok': 0,
        'fail': 0,
        'no_geo': 0,
        'errors': [],
    }

    start_time = time.time()

    for i, rel_path in enumerate(geo_files, 1):
        category = os.path.dirname(rel_path)
        name = os.path.basename(rel_path).replace('.geo.json', '')

        geo_path = os.path.join(OUTPUT_DIR, rel_path)
        anim_path = os.path.join(OUTPUT_DIR, category, f"{name}.animation.json") if category else os.path.join(OUTPUT_DIR, f"{name}.animation.json")
        tex_path = os.path.join(OUTPUT_DIR, category, f"{name}.png") if category else os.path.join(OUTPUT_DIR, f"{name}.png")

        print(f"  [{i:3d}/{stats['total']}] {category}/{name}...", end=" ", flush=True)

        try:
            # Load geo.json
            with open(geo_path, 'r', encoding='utf-8') as f:
                geo_json = json.load(f)

            # Load animation.json (optional)
            anim_json = None
            if os.path.exists(anim_path):
                try:
                    with open(anim_path, 'r', encoding='utf-8') as f:
                        anim_json = json.load(f)
                except Exception:
                    pass

            # Find texture path
            texture_path = tex_path if os.path.exists(tex_path) else None

            # Generate .bbmodel
            bbmodel = gen.generate(
                geo_json,
                anim_json=anim_json,
                texture_path=texture_path,
                texture_name=name,
                namespace='srparasites',
            )

            # Save
            out_dir = os.path.join(SRP_DIR, category) if category else SRP_DIR
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"{name}.bbmodel")
            gen.save(bbmodel, out_path)

            elements = bbmodel.get('elements', [])
            animations = bbmodel.get('animations', [])
            anim_count = len(animations)
            file_size = os.path.getsize(out_path)

            status = f"OK ({len(elements)} elems, {anim_count} anims, {file_size/1024:.0f}KB)"
            stats['ok'] += 1

        except Exception as e:
            status = f"FAILED: {e}"
            stats['fail'] += 1
            stats['errors'].append(f"{category}/{name}: {e}")

        print(status)

    elapsed = time.time() - start_time

    # Summary
    print()
    print("=" * 70)
    print("  REGENERATION SUMMARY")
    print("=" * 70)
    print(f"  Total models:   {stats['total']}")
    print(f"  Successful:     {stats['ok']}")
    print(f"  Failed:         {stats['fail']}")
    print(f"  Elapsed:        {elapsed:.1f}s")
    print(f"  Output:         {SRP_DIR}")

    if stats['errors']:
        print(f"\n  Errors:")
        for e in stats['errors'][:10]:
            print(f"    X {e}")
        if len(stats['errors']) > 10:
            print(f"    ... and {len(stats['errors']) - 10} more")

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
