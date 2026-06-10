#!/usr/bin/env python3
"""
Batch generate .bbmodel files from MROLF-TGNBF-OUTPUT converted data.
Each .bbmodel embeds the latest converted model, animation, and texture.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'converter'))
from bbmodel_generator import BBModelGenerator

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MROLF-TGNBF-OUTPUT')


def normalize_geo_json(geo_json):
    """Convert Bedrock geo.json format to the format expected by BBModelGenerator.
    
    Input:  {"format_version": "1.12.0", "minecraft:geometry": [{"description": {...}, "bones": [...]}]}
    Output: {"model": {"identifier": "...", "texture_width": N, "texture_height": N, "bones": [...]}}
    """
    if "model" in geo_json:
        return geo_json  # Already in expected format
    
    if "minecraft:geometry" in geo_json:
        mg = geo_json["minecraft:geometry"]
        if isinstance(mg, list):
            mg = mg[0]
        
        desc = mg.get("description", {})
        identifier = desc.get("identifier", "model.unknown")
        tex_width = desc.get("texture_width", 256)
        tex_height = desc.get("texture_height", 256)
        bones = mg.get("bones", [])
        
        return {
            "model": {
                "identifier": identifier,
                "texture_width": tex_width,
                "texture_height": tex_height,
                "bones": bones,
            }
        }
    
    return geo_json  # Return as-is if format unknown


def process_category(category_dir):
    """Process all creatures in a category directory."""
    results = {"generated": 0, "errors": []}
    
    if not os.path.isdir(category_dir):
        return results
    
    # Find all .geo.json files
    for filename in sorted(os.listdir(category_dir)):
        if not filename.endswith(".geo.json"):
            continue
        
        base_name = filename.replace(".geo.json", "")
        geo_path = os.path.join(category_dir, filename)
        anim_path = os.path.join(category_dir, base_name + ".animation.json")
        tex_path = os.path.join(category_dir, base_name + ".png")
        output_path = os.path.join(category_dir, base_name + ".bbmodel")
        
        try:
            # Load and normalize geo.json
            with open(geo_path, "r", encoding="utf-8") as f:
                geo_json = json.load(f)
            geo_json = normalize_geo_json(geo_json)
            
            # Load animation JSON if exists
            anim_json = None
            if os.path.isfile(anim_path):
                with open(anim_path, "r", encoding="utf-8") as f:
                    anim_json = json.load(f)
            
            # Generate .bbmodel using the class directly
            generator = BBModelGenerator()
            bbmodel = generator.generate(
                geo_json,
                anim_json=anim_json,
                texture_path=tex_path if os.path.isfile(tex_path) else None,
                texture_name=base_name,
                namespace="srparasites",
            )
            generator.save(bbmodel, output_path)
            
            elements_count = len(bbmodel.get("elements", []))
            anims_count = len(bbmodel.get("animations", []))
            tex_count = len(bbmodel.get("textures", []))
            print(f"  ✓ {base_name}: {elements_count} elements, {anims_count} animations, {tex_count} textures")
            results["generated"] += 1
            
        except Exception as e:
            import traceback
            print(f"  ✗ {base_name}: {e}")
            traceback.print_exc()
            results["errors"].append(f"{base_name}: {e}")
    
    return results


def main():
    total = {"generated": 0, "errors": []}
    
    for category_name in sorted(os.listdir(OUTPUT_DIR)):
        category_path = os.path.join(OUTPUT_DIR, category_name)
        if not os.path.isdir(category_path):
            continue
        
        print(f"\n[{category_name}]")
        result = process_category(category_path)
        total["generated"] += result["generated"]
        total["errors"].extend(result["errors"])
    
    print(f"\n{'='*60}")
    print(f"Total generated: {total['generated']}")
    print(f"Total errors: {len(total['errors'])}")
    
    if total["errors"]:
        print("\nErrors:")
        for err in total["errors"][:10]:
            print(f"  - {err}")
        if len(total["errors"]) > 10:
            print(f"  ... and {len(total['errors']) - 10} more")


if __name__ == "__main__":
    main()
