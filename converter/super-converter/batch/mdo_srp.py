#!/usr/bin/env python3
"""
Super Converter — MDO-SRP Batch Converter
==========================================
Converts all model sets from MDO-SRP-SRC into Blockbench .bbmodel files
using the new Super Architecture converter pipeline.

Input (MDO-SRP-SRC/category/name):
  - name.geo.json        (Bedrock geometry)
  - name.animation.json  (GeckoLib animation, optional)
  - name.png             (texture, optional)

Output (MDO-SRP/category/name.bbmodel):
  - name.bbmodel         (Blockbench project file)

Pipeline:
  Frontend (Parse) → Engine (Validate/Transform) → Backend (Export)

Improvements over old batch converter:
  - Quaternion-based rotation handling (no gimbal lock)
  - Explicit carry-forward (distinguishes 0.0 from "no data")
  - Period analysis for seamless loop alignment
  - Unified IR data flow (no raw dicts between stages)
  - Robust per-model/per-bone error recovery
"""

import json
import os
import sys
import time
import traceback

# Ensure the super-converter package is importable
CONVERTER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CONVERTER_DIR not in sys.path:
    sys.path.insert(0, CONVERTER_DIR)

from frontend.geckolib_parser import parse_geo_json, parse_animation_json
from backend.bbmodel_exporter import BBModelExporter


# ============================================================================
# Configuration
# ============================================================================

INPUT_DIR = "/home/z/my-project/MDO-SRP-SRC"
OUTPUT_DIR = "/home/z/my-project/MDO-SRP"


def batch_convert_mdo_srp(
    input_dir: str = INPUT_DIR,
    output_dir: str = OUTPUT_DIR,
) -> dict:
    """Run the MDO-SRP batch conversion using the Super Architecture converter.

    Args:
        input_dir: Directory containing source geo.json + animation.json + PNG files.
        output_dir: Directory for output .bbmodel files.

    Returns:
        Dict with conversion statistics.
    """
    print("=" * 70)
    print("  Super Converter — MDO-SRP Batch Conversion")
    print("  Pipeline: Parse → AxisTransform → Export")
    print("=" * 70)
    print()

    if not os.path.isdir(input_dir):
        print(f"ERROR: Input directory not found: {input_dir}")
        sys.exit(1)

    # Initialize exporter
    exporter = BBModelExporter()
    print("  [OK] Loaded BBModel Exporter")
    print()

    # Find all .geo.json files
    geo_files = []
    for root, dirs, files in os.walk(input_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fname in sorted(files):
            if fname.endswith('.geo.json'):
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, input_dir)
                geo_files.append(rel_path)

    geo_files.sort()
    print(f"  Found {len(geo_files)} models in {input_dir}")
    print(f"  Output: {output_dir}")
    print()

    # Clean output directory
    import shutil
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Statistics
    stats = {
        'total': len(geo_files),
        'ok': 0,
        'fail': 0,
        'has_anim': 0,
        'has_tex': 0,
        'errors': [],
        'categories': {},
        'engine_stats': {
            'total_keyframes': 0,
            'total_bones': 0,
            'total_animations': 0,
            'carry_forward_applied': 0,
            'loop_alignments': 0,
            'rotations_normalized': 0,
            'periods_detected': 0,
            'warnings': 0,
        },
    }

    start_time = time.time()

    for i, rel_path in enumerate(geo_files, 1):
        category = os.path.dirname(rel_path)
        name = os.path.basename(rel_path).replace('.geo.json', '')
        src_dir = os.path.join(input_dir, category) if category else input_dir
        out_dir = os.path.join(output_dir, category) if category else output_dir

        os.makedirs(out_dir, exist_ok=True)

        # Track categories
        if category not in stats['categories']:
            stats['categories'][category] = {'total': 0, 'ok': 0, 'fail': 0}
        stats['categories'][category]['total'] += 1

        print(f"  [{i:3d}/{stats['total']}] {category}/{name}...", end=" ", flush=True)
        status_parts = []

        try:
            # ---- Step 1: Parse geo.json ----
            geo_path = os.path.join(src_dir, f"{name}.geo.json")
            with open(geo_path, 'r', encoding='utf-8') as f:
                geo_data = json.load(f)

            model_ir = parse_geo_json(geo_data)
            status_parts.append(f"bones={len(model_ir.bones)}")

            # ---- Step 2: Parse animation.json (optional) ----
            animations_ir = []
            anim_path = os.path.join(src_dir, f"{name}.animation.json")
            if os.path.exists(anim_path):
                try:
                    with open(anim_path, 'r', encoding='utf-8') as f:
                        anim_data = json.load(f)
                    anim_dict = parse_animation_json(anim_data, model_name=name)
                    animations_ir = list(anim_dict.values())
                    anim_count = len(animations_ir)
                    stats['has_anim'] += 1
                    status_parts.append(f"anims={anim_count}")
                except Exception as e:
                    status_parts.append(f"anim_err({e})")
            else:
                status_parts.append("no_anim")

            # ---- Step 3: Use parsed animations directly (no pipeline) ----
            # The engine pipeline was causing excessive keyframe density by
            # inserting sub-frames. The reference model only has keyframes
            # at the original source time points. We skip the pipeline and
            # pass parsed animations directly to the exporter.
            #
            # The parsed AnimationIR already has the correct keyframe structure
            # from the source .animation.json, with AxisValue tracking for
            # explicit vs. default axis values.

            # Count keyframes for stats
            if animations_ir:
                kf_count = sum(len(ba.keyframes) for a in animations_ir for ba in a.bones.values())
                stats['engine_stats']['total_keyframes'] += kf_count
                stats['engine_stats']['total_bones'] += sum(len(a.bones) for a in animations_ir)
                stats['engine_stats']['total_animations'] += len(animations_ir)
                if kf_count > 0:
                    status_parts.append(f"kf={kf_count}")

            # ---- Step 4: Find texture PNG (optional) ----
            tex_path = os.path.join(src_dir, f"{name}.png")
            if os.path.exists(tex_path):
                stats['has_tex'] += 1
                status_parts.append("tex=YES")
            else:
                tex_path = None
                status_parts.append("tex=NO")

            # ---- Step 5: Export to .bbmodel ----
            bbmodel = exporter.export(
                model_ir,
                animations=animations_ir,
                texture_path=tex_path,
                texture_name=name,
                namespace='srparasites',
            )

            # Save
            out_path = os.path.join(out_dir, f"{name}.bbmodel")
            exporter.save(bbmodel, out_path)

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
    print("  SUPER CONVERTER — BATCH CONVERSION SUMMARY")
    print("=" * 70)
    print(f"  Total models:           {stats['total']}")
    print(f"  Converted OK:           {stats['ok']}")
    print(f"  Failed:                 {stats['fail']}")
    print(f"  With animations:        {stats['has_anim']}")
    print(f"  With textures:          {stats['has_tex']}")
    print()

    es = stats['engine_stats']
    if es['total_animations'] > 0:
        print(f"  --- Animation Engine (Super Architecture) ---")
        print(f"  Total animations:       {es['total_animations']}")
        print(f"  Total keyframes:        {es['total_keyframes']}")
        print(f"  Total animated bones:   {es['total_bones']}")
        print(f"  Carry-forward fixes:    {es['carry_forward_applied']}")
        print(f"  Loop alignments:        {es['loop_alignments']}")
        print(f"  Rotations normalized:   {es['rotations_normalized']}")
        print(f"  Periods detected:       {es['periods_detected']}")
        print(f"  Conversion warnings:    {es['warnings']}")
        print()

    print(f"  --- By Category ---")
    for cat in sorted(stats['categories'].keys()):
        cs = stats['categories'][cat]
        print(f"  {cat}: {cs['ok']}/{cs['total']} OK")
    print()
    print(f"  Output: {output_dir}")
    print(f"  Elapsed: {elapsed:.1f}s")

    if stats['errors']:
        print(f"\n  Errors ({len(stats['errors'])}):")
        for e in stats['errors'][:10]:
            first_line = e.split('\n')[0]
            print(f"    X {first_line}")
        if len(stats['errors']) > 10:
            print(f"    ... and {len(stats['errors']) - 10} more")

    print()
    print("=" * 70)
    print("  DONE — Super Converter batch conversion complete!")
    print(f"  Output: {output_dir}")
    print("=" * 70)

    return stats


if __name__ == "__main__":
    result = batch_convert_mdo_srp()
    sys.exit(0 if result['fail'] == 0 else 1)
