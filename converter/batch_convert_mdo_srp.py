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


def _compute_y_offset(bones: list, abs_pivots: dict) -> float:
    """Compute the Y offset needed to position the model so its bottom is at Y=0.

    In the .bbmodel format, Y=0 is the ground plane. Models should be
    positioned so the lowest point of their geometry is at approximately Y=0.
    If the model extends below Y=0, it "sinks into the ground."
    If the model floats above Y=0, it appears to hover.

    This function examines all cube positions in the source geo.json (which
    uses absolute coordinates) and computes the minimum Y value. The Y offset
    is -min_y, which shifts the entire model up (or down) so the bottom
    aligns with the ground plane.

    Args:
        bones: List of bone dicts from geo.json (with original absolute coords)
        abs_pivots: Dict mapping bone_name -> [x, y, z] absolute pivots

    Returns:
        Y offset to add to root bone pivot Y (positive = shift up)
    """
    min_y = float('inf')

    for bone in bones:
        bone_name = bone['name']
        abs_pivot = abs_pivots.get(bone_name, [0.0, 0.0, 0.0])

        for cube in bone.get('cubes', []):
            # Cube origin is ABSOLUTE in the source geo.json
            origin = cube.get('origin', [0.0, 0.0, 0.0])
            size = cube.get('size', [0.0, 0.0, 0.0])

            # Minimum Y of this cube
            cube_min_y = min(origin[1], origin[1] + size[1])
            min_y = min(min_y, cube_min_y)

    if min_y == float('inf') or abs(min_y) < 0.01:
        # No cubes found, or already at Y=0
        return 0.0

    # Shift model so bottom is at Y=0
    # If min_y < 0, y_offset > 0 (shift up to fix sinking)
    # If min_y > 0, y_offset < 0 (shift down to fix floating)
    y_offset = -min_y

    return y_offset


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

    CRITICAL FIX 1: The source Bedrock geo.json files from SRParasites use
    ABSOLUTE bone pivots and ABSOLUTE cube origins (both in world-space
    coordinates), NOT relative ones. BBModelGenerator expects RELATIVE pivots
    (relative to parent) and RELATIVE cube origins (relative to bone pivot).
    We must convert:
      - Cube origins: cube_rel = cube_abs - bone_abs_pivot  (MUST be done first)
      - Bone pivots:  child_rel = child_abs - parent_abs    (done second)

    CRITICAL FIX 2: Many source geo.json files have incorrect entity heights,
    causing models to sink into the ground or float above it. We compute the
    Y bounding box of the model and shift the root bone pivot so the model
    bottom aligns with Y=0 (the ground plane in .bbmodel).
    """
    geom_list = geo_data.get('minecraft:geometry', [])
    if geom_list:
        geom = geom_list[0]
        desc = geom.get('description', {})
        identifier = desc.get('identifier', 'model.unknown')
        if identifier.startswith('geometry.'):
            identifier = identifier[len('geometry.'):]

        bones = geom.get('bones', [])

        # ------------------------------------------------------------------
        # Convert ABSOLUTE pivots and cube origins to RELATIVE
        # ------------------------------------------------------------------
        # Build bone map for parent lookup
        bone_map = {b['name']: b for b in bones}

        # Step 1: Save all original absolute pivots BEFORE any conversion
        # This is critical — we need the original absolute values for both
        # cube origin conversion and pivot relative conversion.
        abs_pivots_original = {}
        for bone in bones:
            abs_pivots_original[bone['name']] = list(bone.get('pivot', [0.0, 0.0, 0.0]))

        # Step 1.5: Compute Y offset to fix model placement height
        # We must do this BEFORE converting to relative, while cube origins
        # are still in absolute coordinates.
        y_offset = _compute_y_offset(bones, abs_pivots_original)

        # Step 2: Convert cube origins from absolute to relative
        # cube_rel = cube_abs - bone_abs_pivot
        for bone in bones:
            abs_pivot = abs_pivots_original[bone['name']]
            cubes = bone.get('cubes', [])
            for cube in cubes:
                abs_origin = cube.get('origin', [0.0, 0.0, 0.0])
                # Convert absolute cube origin to relative (relative to bone pivot)
                relative_origin = [
                    abs_origin[0] - abs_pivot[0],
                    abs_origin[1] - abs_pivot[1],
                    abs_origin[2] - abs_pivot[2],
                ]
                cube['origin'] = relative_origin

        # Step 3: Convert bone pivots from absolute to relative
        # Root bones keep their pivot as-is (already at correct absolute position).
        # Child bones: child_rel = child_abs - parent_abs (using ORIGINAL absolute values)
        for bone in bones:
            parent_name = bone.get('parent')
            if parent_name is None:
                # Root-level bone: apply Y offset to fix placement height
                # This shifts the entire model so bottom is at Y=0
                bone['pivot'][1] += y_offset
                continue
            parent_abs = abs_pivots_original.get(parent_name)
            if parent_abs is None:
                continue

            child_abs = abs_pivots_original[bone['name']]

            # Convert absolute pivot to relative: child_rel = child_abs - parent_abs
            relative_pivot = [
                child_abs[0] - parent_abs[0],
                child_abs[1] - parent_abs[1],
                child_abs[2] - parent_abs[2],
            ]
            bone['pivot'] = relative_pivot

        return {
            'model': {
                'identifier': identifier,
                'texture_width': desc.get('texture_width', 256),
                'texture_height': desc.get('texture_height', 256),
                'bones': bones,
                '_y_offset': y_offset,  # Pass Y offset to generator for animation adjustment
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
        'anim_stats': {
            'total_keyframes': 0,
            'total_bones': 0,
            'total_animations': 0,
            'molang_keyframes': 0,
            'carry_forward_applied': 0,
            'loop_alignments': 0,
            'rotations_normalized': 0,
            'warnings': 0,
        },
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

            # Collect animation conversion stats from AnimEngineV2
            anim_result = bbmodel_generator.get_last_anim_result()
            if anim_result:
                anim_stats = anim_result.stats
                pipeline = anim_stats.get('pipeline_stages', {})

                stats['anim_stats']['total_keyframes'] += anim_stats.get('total_keyframes', 0)
                stats['anim_stats']['total_bones'] += anim_stats.get('total_bones', 0)
                stats['anim_stats']['total_animations'] += anim_stats.get('total_animations', 0)
                stats['anim_stats']['molang_keyframes'] += anim_stats.get('molang_keyframes', 0)
                stats['anim_stats']['warnings'] += len(anim_result.warnings)

                # Transform stage stats
                transform_stats = pipeline.get('transform', {})
                stats['anim_stats']['carry_forward_applied'] += transform_stats.get('carry_forward_applied', 0)
                stats['anim_stats']['loop_alignments'] += transform_stats.get('loop_alignments', 0)

                # Validate stage stats
                validate_stats = pipeline.get('validate', {})
                stats['anim_stats']['rotations_normalized'] += validate_stats.get('rotations_normalized', 0)

                # Show keyframe count in status line
                kf_count = anim_stats.get('total_keyframes', 0)
                if kf_count > 0:
                    status_parts.append(f"kf={kf_count}")

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

    # Animation Engine V2 Stats
    anim_s = stats['anim_stats']
    if anim_s['total_animations'] > 0:
        print(f"  --- Animation Engine V2 ---")
        print(f"  Total animations:       {anim_s['total_animations']}")
        print(f"  Total keyframes:        {anim_s['total_keyframes']}")
        print(f"  Total animated bones:   {anim_s['total_bones']}")
        print(f"  Molang keyframes:       {anim_s['molang_keyframes']}")
        print(f"  Carry-forward fixes:    {anim_s['carry_forward_applied']}")
        print(f"  Loop alignments:        {anim_s['loop_alignments']}")
        print(f"  Rotations normalized:   {anim_s['rotations_normalized']}")
        print(f"  Conversion warnings:    {anim_s['warnings']}")
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
