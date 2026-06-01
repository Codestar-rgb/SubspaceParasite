#!/usr/bin/env python3
"""
Comprehensive BBModel -> GeckoLib Bedrock Converter
====================================================
Converts Blockbench .bbmodel files to the full GeckoLib Bedrock format:
  - geo.json   (geometry definition)
  - animation.json (animation keyframes)
  - PNG        (texture)

Usage:
    python3 convert_bedrock.py --input MROLF-TGNBF/derived --output MROLF-TGNBF/bedrock/derived
    python3 convert_bedrock.py --input MROLF-TGNBF/deterrent --output MROLF-TGNBF/bedrock/deterrent
"""

import base64
import json
import math
import os
import sys
import traceback

# Add converter to path
CONVERTER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "converter")
if CONVERTER_DIR not in sys.path:
    sys.path.insert(0, CONVERTER_DIR)

from bbmodel_to_geo import BBModelToGeo


def extract_animation_json(bbmodel: dict, short_name: str) -> dict:
    """Extract animation data from .bbmodel and convert to GeckoLib .animation.json format.
    
    The .bbmodel stores animations in Blockbench's internal format:
      animators -> { boneName: { keyframes: [{ channel, data_points, time, interpolation }] } }
    
    GeckoLib .animation.json format:
      { "format_version": "1.8.0", "animations": { "anim.name": { "loop": ..., "bones": { ... } } } }
    """
    bb_anims = bbmodel.get("animations", [])
    if not bb_anims:
        return None

    animations = {}

    for anim in bb_anims:
        anim_name = anim.get("name", f"animation.model.{short_name}")
        loop_mode = anim.get("loop", "once")
        anim_length = anim.get("length", 0.0)
        animators = anim.get("animators", {})

        bones_data = {}

        for bone_name, animator in animators.items():
            if animator.get("type") != "bone":
                continue

            keyframes = animator.get("keyframes", [])
            if not keyframes:
                continue

            bone_anim = {}

            for kf in keyframes:
                channel = kf.get("channel")  # "rotation", "position", "scale"
                time = kf.get("time", 0.0)
                data_points = kf.get("data_points", [{}])
                interpolation = kf.get("interpolation", "linear")

                if not data_points:
                    continue

                dp = data_points[0]
                time_str = f"{time:.4f}"

                if channel not in bone_anim:
                    bone_anim[channel] = {}

                # Build value for each axis
                for axis in ("x", "y", "z"):
                    val = dp.get(axis, 0.0)
                    easing = dp.get("easing", interpolation)

                    if axis not in bone_anim[channel]:
                        bone_anim[channel][axis] = {}

                    if easing and easing != "linear":
                        bone_anim[channel][axis][time_str] = {
                            "vector": round(float(val), 6),
                            "easing": easing
                        }
                    else:
                        bone_anim[channel][axis][time_str] = round(float(val), 6)

            if bone_anim:
                bones_data[bone_name] = bone_anim

        if bones_data:
            animations[anim_name] = {
                "loop": loop_mode,
                "animation_length": round(float(anim_length), 4),
                "bones": bones_data
            }

    if not animations:
        return None

    return {
        "format_version": "1.8.0",
        "animations": animations
    }


def convert_single(bbmodel_path: str, output_dir: str) -> dict:
    """Convert a single .bbmodel file to full GeckoLib format."""
    try:
        with open(bbmodel_path, 'r', encoding='utf-8') as f:
            bb = json.load(f)

        short_name = bb.get('model_identifier', bb.get('name', 'unknown'))

        os.makedirs(output_dir, exist_ok=True)

        # --- Step 1: Convert geometry (geo.json + PNG) ---
        converter = BBModelToGeo()
        result = converter.convert_bbmodel(bbmodel_path, output_dir)

        if not result['success']:
            return result

        # --- Step 2: Extract animation.json ---
        anim_json = extract_animation_json(bb, short_name)
        anim_path = None
        if anim_json:
            anim_path = os.path.join(output_dir, f"{short_name}.animation.json")
            with open(anim_path, 'w', encoding='utf-8') as f:
                json.dump(anim_json, f, indent=2, ensure_ascii=False)

        # Build result
        anim_count = len(anim_json.get('animations', {})) if anim_json else 0
        result['animation_path'] = anim_path
        result['stats']['animations'] = anim_count

        return result

    except Exception as e:
        return {
            'success': False,
            'error': f"{type(e).__name__}: {e}",
            'traceback': traceback.format_exc(),
        }


def batch_convert(input_dir: str, output_dir: str) -> bool:
    """Batch convert all .bbmodel files in input_dir to GeckoLib format."""
    print("=" * 70)
    print("  BBModel -> GeckoLib Bedrock Full Converter")
    print("  (geo.json + animation.json + PNG)")
    print("=" * 70)
    print()

    # Find all .bbmodel files
    bbmodel_files = []
    for fname in sorted(os.listdir(input_dir)):
        if fname.endswith('.bbmodel'):
            bbmodel_files.append(fname)

    print(f"Input:  {input_dir}")
    print(f"Output: {output_dir}")
    print(f"Found {len(bbmodel_files)} .bbmodel files")
    print()

    ok_results = []
    fail_results = []

    for i, fname in enumerate(bbmodel_files, 1):
        name = fname.replace('.bbmodel', '')
        bbmodel_path = os.path.join(input_dir, fname)

        print(f"  [{i:3d}/{len(bbmodel_files)}] {name}...", end=" ", flush=True)

        result = convert_single(bbmodel_path, output_dir)

        if result['success']:
            s = result['stats']
            anim_info = f", {s.get('animations', 0)} anims" if s.get('animations', 0) > 0 else ""
            tex_mark = "tex=YES" if s['has_texture'] else "tex=NO"
            print(f"OK ({s['bones']}b, {s['cubes']}c, {s['texture_size']}, {tex_mark}{anim_info})")
            ok_results.append((name, s))
        else:
            print(f"FAILED: {result['error']}")
            fail_results.append((name, result.get('error', '?')))

    # Summary
    print()
    print("=" * 70)
    print("  CONVERSION SUMMARY")
    print("=" * 70)
    print(f"  Total:       {len(bbmodel_files)}")
    print(f"  Successful:  {len(ok_results)}")
    print(f"  Failed:      {len(fail_results)}")

    with_tex = sum(1 for _, s in ok_results if s.get('has_texture'))
    with_anim = sum(1 for _, s in ok_results if s.get('animations', 0) > 0)
    print(f"  With textures: {with_tex}")
    print(f"  With animations: {with_anim}")

    if fail_results:
        print("\n  Failed models:")
        for name, err in fail_results:
            print(f"    - {name}: {err}")

    total_bones = sum(s['bones'] for _, s in ok_results)
    total_cubes = sum(s['cubes'] for _, s in ok_results)
    print(f"\n  Total bones: {total_bones}")
    print(f"  Total cubes: {total_cubes}")
    print(f"  Output: {output_dir}")

    return len(fail_results) == 0


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert .bbmodel files to full GeckoLib format (geo.json + animation.json + PNG)"
    )
    parser.add_argument("--input", required=True, help="Input directory with .bbmodel files")
    parser.add_argument("--output", required=True, help="Output directory for geo.json + animation.json + PNG")
    args = parser.parse_args()

    success = batch_convert(args.input, args.output)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
