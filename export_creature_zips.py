#!/usr/bin/env python3
"""
Creature Model ZIP Exporter for GeckoLib (MC 1.20.1 Forge)
==========================================================
Converts ALL .bbmodel source files to correct geo.json + PNG using
bbmodel_to_geo.py (which matches Blockbench's native export), then
packages each creature into a ZIP file for mod development.

Also includes variant textures from the SRP source repo (e.g. glow,
head, adapted, body variant textures) alongside each model.

Output structure per ZIP:
  <CreatureName>.zip
    ├── <name>.geo.json
    ├── <name>.png
    ├── <name>.animation.json  (if available)
    └── textures/               (variant textures)
        ├── <variant1>.png
        └── <variant2>.png

Master ZIP: SDMCXKIFFNEK.zip containing all models by category.
"""

import json
import os
import shutil
import sys
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path

# Ensure converter directory is in path
CONVERTER_DIR = str(Path(__file__).parent / "converter")
if CONVERTER_DIR not in sys.path:
    sys.path.insert(0, CONVERTER_DIR)

from bbmodel_to_geo import BBModelToGeo

# Base paths
BASE_DIR = Path(__file__).parent
BBMODEL_ROOT = BASE_DIR / "MROLF-TGNBF"
DB_DIR = BASE_DIR / "db"
OUTPUT_DIR = DB_DIR

# Animation files from previous conversion
ANIMATION_DIR = DB_DIR

# Category English name mapping
CATEGORY_ENGLISH = {
    "derived": "Derived",
    "feral": "Feral",
    "awakened": "Awakened",
    "primitive": "Primitive",
    "deterrent": "Deterrent",
    "pure": "Pure",
    "ancient": "Ancient",
    "adapted": "Adapted",
    "infected": "Infected",
    "crude": "Crude",
    "hijacked": "Hijacked",
    "inborn": "Inborn",
    "focused": "Focused",
    "projectile": "Projectile",
    "misc": "Misc",
    "abomination": "Abomination",
}


def find_bbmodel_files(root_dir: Path) -> list:
    """Find all .bbmodel files and return list of (category, model_name, path)."""
    results = []
    for category_dir in sorted(root_dir.iterdir()):
        if not category_dir.is_dir():
            continue
        category = category_dir.name
        # Skip the bedrock output directory
        if category == "bedrock":
            continue

        for bbfile in sorted(category_dir.glob("*.bbmodel")):
            model_name = bbfile.stem
            results.append((category, model_name, bbfile))

    return results


def find_animation(category: str, model_name: str) -> Path:
    """Find animation file for a model, checking multiple locations."""
    # Check db/ first (for derived models)
    candidates = [
        ANIMATION_DIR / f"{model_name}.animation.json",
        BBMODEL_ROOT / "bedrock" / category / f"{model_name}.animation.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def load_variant_map() -> dict:
    """Load the texture variant mapping from texture_variants.json."""
    variant_path = BBMODEL_ROOT / "texture_variants.json"
    if variant_path.exists():
        with open(variant_path) as f:
            return json.load(f)
    return {}


def find_variant_textures(model_name: str, variant_map: dict) -> list:
    """Find all variant texture PNGs for a model."""
    key = model_name.lower()
    variants = []
    
    if key in variant_map:
        model_info = variant_map[key]
        for v in model_info.get("variants", []):
            local_path = BBMODEL_ROOT / v["local_path"]
            if local_path.exists():
                variants.append(local_path)
    
    # Also check layer textures
    layer_key = "_layer_textures"
    if layer_key in variant_map:
        for layer in variant_map[layer_key]:
            layer_model = layer.get("model")
            if layer_model and layer_model.lower() == key:
                local_path = BBMODEL_ROOT / layer["local_path"]
                if local_path.exists():
                    variants.append(local_path)
    
    return variants


def convert_all_models(bbmodel_files: list, temp_dir: Path) -> dict:
    """Convert all bbmodel files to geo.json + PNG using bbmodel_to_geo.py.
    
    Returns dict: (category, model_name) -> {"geo": path, "texture": path, "animation": path_or_None, "variants": [paths]}
    """
    converter = BBModelToGeo()
    models = {}
    variant_map = load_variant_map()
    
    for category, model_name, bbmodel_path in bbmodel_files:
        # Create output subdir in temp
        out_dir = temp_dir / category
        out_dir.mkdir(parents=True, exist_ok=True)
        
        result = converter.convert_bbmodel(str(bbmodel_path), str(out_dir))
        
        if result['success']:
            files = {"geo": None, "texture": None, "animation": None, "variants": []}
            
            geo_path = Path(result['geo_path'])
            if geo_path.exists():
                files["geo"] = geo_path
            
            tex_path = result.get('texture_path')
            if tex_path and Path(tex_path).exists():
                files["texture"] = Path(tex_path)
            
            # Find animation
            anim_path = find_animation(category, model_name)
            if anim_path:
                files["animation"] = anim_path
            
            # Find variant textures
            variant_textures = find_variant_textures(model_name, variant_map)
            files["variants"] = variant_textures
            
            models[(category, model_name)] = files
            
            s = result['stats']
            parts = []
            if files["geo"]: parts.append("geo")
            if files["texture"]: parts.append("tex")
            if files["animation"]: parts.append("anim")
            if variant_textures: parts.append(f"+{len(variant_textures)}var")
            content = "+".join(parts)
            
            print(f"  {category:15s}/{model_name:25s}  [{content:17s}]  "
                  f"({s['bones']}b, {s['cubes']}c, {s['texture_size']})")
        else:
            print(f"  {category:15s}/{model_name:25s}  FAILED: {result['error']}")
    
    return models


def create_creature_zip(zip_path: Path, model_name: str, category: str, files: dict):
    """Create a ZIP file for a single creature model."""
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        if files.get("geo"):
            zf.write(files["geo"], f"{model_name}.geo.json")
        if files.get("texture"):
            zf.write(files["texture"], f"{model_name}.png")
        if files.get("animation"):
            zf.write(files["animation"], f"{model_name}.animation.json")
        # Add variant textures
        for var_path in files.get("variants", []):
            var_name = var_path.name
            zf.write(var_path, f"textures/{var_name}")


def create_master_zip(zip_path: Path, all_models: dict):
    """Create a master ZIP containing all creature models organized by category."""
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for (category, model_name), files in sorted(all_models.items()):
            prefix = f"{category}/{model_name}"
            if files.get("geo"):
                zf.write(files["geo"], f"{prefix}.geo.json")
            if files.get("texture"):
                zf.write(files["texture"], f"{prefix}.png")
            if files.get("animation"):
                zf.write(files["animation"], f"{prefix}.animation.json")
            # Add variant textures
            for var_path in files.get("variants", []):
                var_name = var_path.name
                zf.write(var_path, f"{prefix}/textures/{var_name}")
        
        # Also add standalone layer textures
        variant_map = load_variant_map()
        layer_key = "_layer_textures"
        if layer_key in variant_map:
            for layer in variant_map[layer_key]:
                local_path = BBMODEL_ROOT / layer["local_path"]
                if local_path.exists():
                    zf.write(local_path, f"_layers/{layer['filename']}")


def main():
    print("=" * 70)
    print("  Creature Model ZIP Exporter (bbmodel → geo.json)")
    print("  GeckoLib Format for MC 1.20.1 Forge Mod Development")
    print("  Using bbmodel_to_geo.py (matches Blockbench native export)")
    print("=" * 70)
    print()

    # Find all bbmodel files
    print("[1/4] Finding .bbmodel source files...")
    bbmodel_files = find_bbmodel_files(BBMODEL_ROOT)
    
    # Group by category
    by_category = defaultdict(list)
    for cat, name, path in bbmodel_files:
        by_category[cat].append((name, path))
    
    print(f"      Found {len(bbmodel_files)} .bbmodel files")
    for cat in sorted(by_category.keys()):
        print(f"        {cat}: {len(by_category[cat])} models")
    print()

    # Convert all models
    print("[2/4] Converting .bbmodel → geo.json + PNG...")
    print("-" * 70)
    
    temp_dir = Path(tempfile.mkdtemp(prefix="geo_export_"))
    models = convert_all_models(bbmodel_files, temp_dir)
    print()

    # Create individual ZIP files
    print("[3/4] Creating individual ZIP packages...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    zip_files = []
    for (category, model_name), files in sorted(models.items()):
        if not files.get("geo"):
            continue

        zip_name = f"{model_name}.zip"
        zip_path = OUTPUT_DIR / zip_name
        create_creature_zip(zip_path, model_name, category, files)
        
        zip_size = zip_path.stat().st_size
        parts = []
        if files.get("geo"): parts.append("geo")
        if files.get("texture"): parts.append("tex")
        if files.get("animation"): parts.append("anim")
        content = "+".join(parts)
        
        print(f"  {category:15s}/{model_name:25s}  [{content:13s}]  "
              f"zip={zip_size/1024:.1f}KB")
        zip_files.append((category, model_name, zip_path))

    # Create master ZIP
    print()
    print("[4/4] Creating master ZIP: SDMCXKIFFNEK.zip...")
    master_path = OUTPUT_DIR / "SDMCXKIFFNEK.zip"
    create_master_zip(master_path, models)
    master_size = master_path.stat().st_size
    print(f"      SDMCXKIFFNEK.zip ({master_size/1024/1024:.1f}MB)")

    # Also update bedrock directory with correct geo.json files
    print()
    print("Updating MROLF-TGNBF/bedrock/ with correct geo.json files...")
    bedrock_dir = BBMODEL_ROOT / "bedrock"
    updated = 0
    for (category, model_name), files in models.items():
        if files.get("geo"):
            cat_dir = bedrock_dir / category
            cat_dir.mkdir(parents=True, exist_ok=True)
            dst_geo = cat_dir / f"{model_name}.geo.json"
            shutil.copy2(str(files["geo"]), str(dst_geo))
            if files.get("texture"):
                dst_tex = cat_dir / f"{model_name}.png"
                shutil.copy2(str(files["texture"]), str(dst_tex))
            updated += 1
    print(f"      Updated {updated} models in bedrock/")

    # Cleanup temp
    shutil.rmtree(temp_dir, ignore_errors=True)

    # Summary
    print()
    print("=" * 70)
    print("  EXPORT SUMMARY")
    print("=" * 70)

    total_geo = sum(1 for f in models.values() if f.get("geo"))
    total_tex = sum(1 for f in models.values() if f.get("texture"))
    total_anim = sum(1 for f in models.values() if f.get("animation"))
    
    print(f"  Total models:      {len(models)}")
    print(f"  With geo.json:     {total_geo}")
    print(f"  With texture:      {total_tex}")
    print(f"  With animation:    {total_anim}")
    print(f"  Individual ZIPs:   {len(zip_files)}")
    print(f"  Master ZIP:        SDMCXKIFFNEK.zip")
    print(f"  Output directory:  {OUTPUT_DIR}")
    
    # List models with animation
    with_anim = [(cat, name) for (cat, name), f in models.items() if f.get("animation")]
    if with_anim:
        print(f"\n  Models with animations ({len(with_anim)}):")
        for cat, name in with_anim:
            print(f"    - {cat}/{name}")
    
    # List missing textures
    missing_tex = [(cat, name) for (cat, name), f in models.items()
                   if f.get("geo") and not f.get("texture")]
    if missing_tex:
        print(f"\n  Models missing textures ({len(missing_tex)}):")
        for cat, name in missing_tex:
            print(f"    - {cat}/{name}")
    
    return True


if __name__ == "__main__":
    main()
