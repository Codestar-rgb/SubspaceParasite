#!/usr/bin/env python3
"""
Regenerate BBModel Files from Grounded Geo.json
=================================================
Reads the corrected geo.json files from db/output/ (which have been through
bbmodel_to_geo + _fix_model_grounding), and regenerates .bbmodel files
using the fixed BBModelGenerator.

The geo.json files in db/output/ are the source of truth:
- Cube origins are RELATIVE to bone pivot (GeckoLib standard)
- Pivots are absolute with X-mirror (from bbmodel_to_geo.py)
- Models are grounded (min world Y = 0)

Animation data is preserved from the original .bbmodel files.

Usage:
    python3 regenerate_bbmodels.py
"""

import json
import os
import sys
import traceback

# Ensure converter directory is in path
CONVERTER_DIR = os.path.dirname(os.path.abspath(__file__))
if CONVERTER_DIR not in sys.path:
    sys.path.insert(0, CONVERTER_DIR)

INPUT_DIR = "/home/z/my-project/db/output"
OLD_BBMODEL_DIR = "/home/z/my-project/MCMOD-SRP"
OUTPUT_DIR = "/home/z/my-project/MCMOD-SRP-new"


def find_geo_files(input_dir: str) -> list:
    """Find all .geo.json files in the input directory."""
    geo_files = []
    for root, dirs, files in os.walk(input_dir):
        for fname in sorted(files):
            if fname.endswith('.geo.json'):
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, input_dir)
                geo_files.append(rel_path)
    return sorted(geo_files)


def find_animation_file(input_dir: str, category: str, name: str) -> str:
    """Find the animation.json file for a model."""
    if category:
        anim_path = os.path.join(input_dir, category, f"{name}.animation.json")
    else:
        anim_path = os.path.join(input_dir, f"{name}.animation.json")
    if os.path.exists(anim_path):
        return anim_path
    return None


def find_texture_file(input_dir: str, category: str, name: str) -> str:
    """Find the texture PNG file for a model."""
    if category:
        tex_path = os.path.join(input_dir, category, f"{name}.png")
    else:
        tex_path = os.path.join(input_dir, f"{name}.png")
    if os.path.exists(tex_path):
        return tex_path
    return None


def convert_geckolib_anim_to_converter_format(anim_json: dict) -> dict:
    """Convert GeckoLib animation.json to the converter's internal format.

    GeckoLib format:
    {
      "animations": {
        "anim.name": {
          "bones": {
            "boneName": {
              "rotation": {"0.0": [x, y, z], "0.5": {"vector": [x, y, z], "easing": "..."}},
              "position": {...}
            }
          }
        }
      }
    }

    Converter format:
    {
      "animations": {
        "anim.name": {
          "loop": "...",
          "animation_length": ...,
          "bones": {
            "boneName": {
              "rotation": {
                "x": {"0.0": value_or_obj, ...},
                "y": {...},
                "z": {...}
              }
            }
          }
        }
      }
    }
    """
    if not anim_json or "animations" not in anim_json:
        return anim_json

    result = {"format_version": anim_json.get("format_version", "1.8.0"), "animations": {}}

    for anim_name, anim_data in anim_json["animations"].items():
        new_anim = {
            "loop": anim_data.get("loop", "once"),
            "animation_length": anim_data.get("animation_length", 0.0),
            "bones": {},
        }

        for bone_name, bone_data in anim_data.get("bones", {}).items():
            new_bone = {}

            for channel in ("rotation", "position", "scale"):
                channel_data = bone_data.get(channel)
                if channel_data is None:
                    continue

                per_axis = {"x": {}, "y": {}, "z": {}}

                for time_str, value in channel_data.items():
                    try:
                        t = float(time_str)
                    except (ValueError, TypeError):
                        continue

                    if isinstance(value, list):
                        # Simple vector: [x, y, z]
                        if len(value) >= 3:
                            per_axis["x"][time_str] = float(value[0])
                            per_axis["y"][time_str] = float(value[1])
                            per_axis["z"][time_str] = float(value[2])
                    elif isinstance(value, dict):
                        # Object with vector and easing
                        vector = value.get("vector", [0, 0, 0])
                        easing = value.get("easing", "linear")
                        if len(vector) >= 3:
                            for i, axis in enumerate(["x", "y", "z"]):
                                per_axis[axis][time_str] = {
                                    "vector": float(vector[i]),
                                    "easing": easing,
                                }

                # Only include axes that have data
                new_channel = {}
                for axis in ("x", "y", "z"):
                    if per_axis[axis]:
                        new_channel[axis] = per_axis[axis]

                if new_channel:
                    new_bone[channel] = new_channel

            if new_bone:
                new_anim["bones"][bone_name] = new_bone

        result["animations"][anim_name] = new_anim

    return result


def main():
    print("=" * 70)
    print("  Regenerate BBModel Files from Grounded Geo.json")
    print("=" * 70)
    print()

    # Import the fixed BBModelGenerator
    from bbmodel_generator import BBModelGenerator

    # Find all geo.json files
    geo_files = find_geo_files(INPUT_DIR)
    print(f"Found {len(geo_files)} geo.json files in {INPUT_DIR}")
    print()

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Process each file
    stats = {"success": 0, "failed": 0, "no_geo": 0, "errors": []}

    for i, rel_path in enumerate(geo_files, 1):
        # Parse category and name
        parts = rel_path.replace(".geo.json", "").split(os.sep)
        if len(parts) >= 2:
            category = parts[0]
            name = parts[1]
        else:
            category = ""
            name = parts[0]

        print(f"  [{i:3d}/{len(geo_files)}] {category}/{name}...", end=" ", flush=True)

        try:
            # Read geo.json
            geo_path = os.path.join(INPUT_DIR, rel_path)
            with open(geo_path, 'r', encoding='utf-8') as f:
                geo_json = json.load(f)

            # Find animation file
            anim_path = find_animation_file(INPUT_DIR, category, name)
            anim_json = None
            if anim_path:
                with open(anim_path, 'r', encoding='utf-8') as f:
                    raw_anim = json.load(f)
                # Convert GeckoLib animation format to converter format
                anim_json = convert_geckolib_anim_to_converter_format(raw_anim)

            # Find texture file
            tex_path = find_texture_file(INPUT_DIR, category, name)

            # Also try to get texture from old .bbmodel
            old_bbmodel_path = os.path.join(OLD_BBMODEL_DIR, category, f"{name}.bbmodel") if category else os.path.join(OLD_BBMODEL_DIR, f"{name}.bbmodel")

            # Generate new .bbmodel
            bbgen = BBModelGenerator()
            bbmodel = bbgen.generate(
                geo_json,
                anim_json=anim_json,
                texture_path=tex_path,
                texture_name=name,
                namespace="srparasites",
            )

            # If no texture from PNG file, try to extract from old .bbmodel
            if not tex_path and os.path.exists(old_bbmodel_path):
                try:
                    with open(old_bbmodel_path, 'r', encoding='utf-8') as f:
                        old_data = json.load(f)
                    if old_data.get("textures") and not bbmodel.get("textures", [{}])[0].get("source"):
                        bbmodel["textures"] = old_data["textures"]
                except Exception:
                    pass

            # Also copy animations from old .bbmodel if new one has none
            if not bbmodel.get("animations") and os.path.exists(old_bbmodel_path):
                try:
                    with open(old_bbmodel_path, 'r', encoding='utf-8') as f:
                        old_data = json.load(f)
                    if old_data.get("animations"):
                        bbmodel["animations"] = old_data["animations"]
                except Exception:
                    pass

            # Save new .bbmodel
            out_dir = os.path.join(OUTPUT_DIR, category) if category else OUTPUT_DIR
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"{name}.bbmodel")
            bbgen.save(bbmodel, out_path)

            # Count stats
            n_elements = len(bbmodel.get("elements", []))
            n_groups = len(bbmodel.get("groups", []))
            n_anims = len(bbmodel.get("animations", []))

            # Check grounding
            min_y = float('inf')
            for e in bbmodel.get("elements", []):
                min_y = min(min_y, e["from"][1])
            grounded = "YES" if min_y <= 0.5 else f"NO(Y={min_y:.1f})"

            print(f"OK ({n_elements}elem, {n_groups}grp, {n_anims}anim, ground={grounded})")
            stats["success"] += 1

        except Exception as e:
            print(f"FAILED: {e}")
            stats["failed"] += 1
            stats["errors"].append(f"{category}/{name}: {traceback.format_exc()}")

    # Summary
    print()
    print("=" * 70)
    print("  REGENERATION SUMMARY")
    print("=" * 70)
    print(f"  Total:   {len(geo_files)}")
    print(f"  Success: {stats['success']}")
    print(f"  Failed:  {stats['failed']}")
    print(f"  Output:  {OUTPUT_DIR}")
    print()

    if stats["errors"]:
        print("  Errors:")
        for e in stats["errors"][:10]:
            print(f"    {e[:200]}")
        if len(stats["errors"]) > 10:
            print(f"    ... and {len(stats['errors']) - 10} more")

    print()
    return stats["failed"] == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
