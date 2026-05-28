#!/usr/bin/env python3
"""
Batch Geo.json + PNG Exporter for GeckoLib (MC 1.20.1 Forge)
=============================================================
Directly converts Java model source files to Bedrock geo.json + PNG texture,
applying the same coordinate corrections as bbmodel_generator but outputting
the standard Bedrock format that GeckoLib expects.

This skips the bbmodel intermediate step entirely, avoiding double-conversion errors.

Coordinate Corrections (same as bbmodel_generator.py):
  1. N<->S UV Face Swap: The RH->LH Z-flip maps north_RH -> south_LH and
     vice versa, so UV data assigned to 'north' in RH must go to 'south'
     in the geo.json for correct LH rendering.
  2. W<->E UV Swap for mirrored cubes: After geometric X-mirror, the face
     at -X (west) was originally at +X (east) and vice versa.
  3. Root bone 180° Y rotation: Compensates for the Z-flip in the coordinate
     conversion, making the model face the correct direction.
"""

import base64
import json
import os
import sys
import traceback

# Ensure converter directory is in path
CONVERTER_DIR = os.path.dirname(os.path.abspath(__file__))
if CONVERTER_DIR not in sys.path:
    sys.path.insert(0, CONVERTER_DIR)

from model_converter import ModelConverter

# Import texture mapping from batch_convert
from batch_convert import TEXTURE_NAME_MAP, EXTRA_TEX_DIRS, discover_model_files

# Face direction mapping
FACE_NAMES = ["north", "east", "south", "west", "up", "down"]


def find_texture(texture_dir, entity_name):
    """Find texture PNG using the comprehensive mapping from batch_convert."""
    if not texture_dir or not os.path.isdir(texture_dir):
        return None

    tex_name = TEXTURE_NAME_MAP.get(entity_name)
    if tex_name:
        candidate = os.path.join(texture_dir, f"{tex_name}.png")
        if os.path.isfile(candidate):
            return candidate
        parent_dir = os.path.dirname(texture_dir)
        for sub in EXTRA_TEX_DIRS.values():
            sub_candidate = os.path.join(parent_dir, sub, f"{tex_name}.png")
            if os.path.isfile(sub_candidate):
                return sub_candidate

    lower_name = entity_name.lower()
    for suffix in ["", "a", "h", "v", "b"]:
        full_path = os.path.join(texture_dir, f"{lower_name}{suffix}.png")
        if os.path.isfile(full_path):
            return full_path

    return None


def apply_uv_corrections(geo_json):
    """
    Apply UV face corrections to the geo.json for correct LH/Bedrock rendering.

    1. N<->S UV swap for ALL cubes (RH->LH Z-flip correction)
    2. W<->E UV swap for MIRRORED cubes only (geometric X-mirror correction)
    """
    model = geo_json.get('model', geo_json)
    bones = model.get('bones', [])

    for bone in bones:
        # Check if this bone has mirror flag
        bone_mirror = bone.get('mirror', False)

        for cube in bone.get('cubes', []):
            uv = cube.get('uv', {})
            if not uv:
                continue

            # 1. N<->S UV swap (all cubes)
            north_uv = uv.get('north')
            south_uv = uv.get('south')
            if north_uv is not None and south_uv is not None:
                uv['north'] = south_uv
                uv['south'] = north_uv

            # 2. W<->E UV swap (mirrored cubes only)
            cube_mirror = cube.get('mirror', False)
            if bone_mirror or cube_mirror:
                west_uv = uv.get('west')
                east_uv = uv.get('east')
                if west_uv is not None and east_uv is not None:
                    uv['west'] = east_uv
                    uv['east'] = west_uv


def add_root_rotation(geo_json):
    """
    Add 180° Y rotation to the root bone.
    This compensates for the Z-flip in the RH->LH coordinate conversion,
    making the model face the correct direction in-game.
    """
    model = geo_json.get('model', geo_json)
    bones = model.get('bones', [])

    for bone in bones:
        if bone['name'] == 'root':
            rot = bone.get('rotation', [0.0, 0.0, 0.0])
            rot[1] += 180.0
            bone['rotation'] = rot
            break


def convert_to_bedrock_geo(geo_json, short_name):
    """
    Convert the internal geo.json format to the standard Bedrock
    minecraft:geometry format that GeckoLib expects.
    """
    model = geo_json.get('model', geo_json)

    tex_width = model.get('texture_width', 256)
    tex_height = model.get('texture_height', 256)
    bones = model.get('bones', [])

    bedrock_geo = {
        "format_version": "1.12.0",
        "minecraft:geometry": [{
            "description": {
                "identifier": f"geometry.{short_name}",
                "texture_width": tex_width,
                "texture_height": tex_height,
                "visible_bounds_width": 2,
                "visible_bounds_height": 3,
                "visible_bounds_offset": [0, 1.5, 0]
            },
            "bones": bones
        }]
    }

    return bedrock_geo


def convert_model(java_path, output_dir, output_name, texture_path=None,
                  namespace="srparasites"):
    """
    Convert a single Java model file directly to geo.json + PNG.
    """
    try:
        # Read Java source
        with open(java_path, 'r', encoding='utf-8') as f:
            source = f.read()

        # Step 1: Convert to geo.json using ModelConverter
        converter = ModelConverter()
        identifier = f"model.{output_name}"
        result = converter.convert(source, identifier)

        geo_json = result['geo_json']
        bones = geo_json['model']['bones']
        total_cubes = sum(len(b.get('cubes', [])) for b in bones)
        tex_w = geo_json['model']['texture_width']
        tex_h = geo_json['model']['texture_height']

        # Step 2: Apply UV corrections (N<->S swap, W<->E swap for mirrored)
        apply_uv_corrections(geo_json)

        # Step 3: Add 180° Y rotation to root bone
        add_root_rotation(geo_json)

        # Step 4: Convert to Bedrock format
        bedrock_geo = convert_to_bedrock_geo(geo_json, output_name)

        # Step 5: Save geo.json
        os.makedirs(output_dir, exist_ok=True)
        geo_path = os.path.join(output_dir, f"{output_name}.geo.json")
        with open(geo_path, 'w', encoding='utf-8') as f:
            json.dump(bedrock_geo, f, indent=2, ensure_ascii=False)

        # Step 6: Copy texture PNG
        texture_out = None
        if texture_path and os.path.isfile(texture_path):
            texture_out = os.path.join(output_dir, f"{output_name}.png")
            with open(texture_path, 'rb') as src:
                with open(texture_out, 'wb') as dst:
                    dst.write(src.read())

        return {
            'success': True,
            'geo_path': geo_path,
            'texture_path': texture_out,
            'stats': {
                'bones': len(bones),
                'cubes': total_cubes,
                'texture_size': f"{tex_w}x{tex_h}",
                'has_texture': texture_out is not None,
            }
        }

    except Exception as e:
        return {
            'success': False,
            'error': f"{type(e).__name__}: {e}",
            'traceback': traceback.format_exc(),
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Batch convert SRParasites Java models to Bedrock geo.json + PNG for GeckoLib"
    )
    parser.add_argument("--source", required=True, help="Path to source repo src/ directory")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--textures", help="Path to textures directory")
    parser.add_argument("--namespace", default="srparasites")
    parser.add_argument("--skip-errors", action="store_true")

    args = parser.parse_args()

    print("=" * 70)
    print("  SRParasites Java -> Bedrock geo.json + PNG Exporter")
    print("  For GeckoLib MC 1.20.1 Forge Mod Development")
    print("=" * 70)
    print()

    # Discover model files
    print("[1/3] Discovering model files...")
    models = discover_model_files(args.source)
    print(f"      Found {len(models)} model files")

    # Group by category
    categories = {}
    for _, cat, name in models:
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(name)

    print()
    for cat in sorted(categories.keys()):
        print(f"  {cat}: {len(categories[cat])} models")

    # Convert
    print(f"\n[2/3] Converting {len(models)} models to geo.json + PNG...")
    print("-" * 70)

    ok_results = []
    fail_results = []

    for i, (java_path, category, output_name) in enumerate(models, 1):
        tex_path = find_texture(args.textures, output_name) if args.textures else None

        cat_dir = os.path.join(args.output, category)
        print(f"  [{i:3d}/{len(models)}] {category}/{output_name}...", end=" ", flush=True)

        result = convert_model(
            java_path, cat_dir, output_name,
            texture_path=tex_path,
            namespace=args.namespace,
        )

        if result['success']:
            s = result['stats']
            tex_mark = "tex=YES" if s['has_texture'] else "tex=NO"
            print(f"OK ({s['bones']}b, {s['cubes']}c, {s['texture_size']}, {tex_mark})")
            ok_results.append((category, output_name, s))
        else:
            print(f"FAILED: {result['error']}")
            fail_results.append((category, output_name, result.get('error', '?')))
            if not args.skip_errors and 'traceback' in result:
                print(f"\n{result['traceback']}")

    # Summary
    print()
    print("=" * 70)
    print("  EXPORT SUMMARY")
    print("=" * 70)
    print(f"  Total:       {len(models)}")
    print(f"  Successful:  {len(ok_results)}")
    print(f"  Failed:      {len(fail_results)}")

    with_tex = sum(1 for _, _, s in ok_results if s.get('has_texture'))
    print(f"  With textures: {with_tex}")

    if fail_results:
        print("\n  Failed models:")
        for cat, name, err in fail_results:
            print(f"    - {cat}/{name}: {err}")

    total_bones = sum(s['bones'] for _, _, s in ok_results)
    total_cubes = sum(s['cubes'] for _, _, s in ok_results)
    print(f"\n  Total bones: {total_bones}")
    print(f"  Total cubes: {total_cubes}")
    print(f"  Output: {args.output}")

    for cat in sorted(categories.keys()):
        cat_dir = os.path.join(args.output, cat)
        if os.path.isdir(cat_dir):
            geo_count = len([f for f in os.listdir(cat_dir) if f.endswith('.geo.json')])
            png_count = len([f for f in os.listdir(cat_dir) if f.endswith('.png')])
            print(f"    {cat}/: {geo_count} geo.json, {png_count} png")

    return len(fail_results) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
