#!/usr/bin/env python3
"""
Batch Converter - Convert ALL SRParasites creature models to .bbmodel
======================================================================
Reads all Model*.java files from the source repo, converts each to
geo.json then .bbmodel, and outputs organized by category directory.

Usage:
    python3 batch_convert.py --source /path/to/Qom-Inseac/src --output /path/to/output [--textures /path/to/textures]

Output structure:
    output/
      inborn/ata.bbmodel
      primitive/bano.bbmodel
      adapted/banoAdapted.bbmodel
      ...
"""

import argparse
import json
import os
import sys
import re
import traceback

# Ensure converter directory is in path
CONVERTER_DIR = os.path.dirname(os.path.abspath(__file__))
if CONVERTER_DIR not in sys.path:
    sys.path.insert(0, CONVERTER_DIR)


# ========================================================================
# Model file discovery and name mapping
# ========================================================================

# Map source directory names to output category names
# Some directories are nested (deterrent/nexus -> deterrent, pure/preeminent -> pure, etc.)
CATEGORY_MAP = {
    "inborn": "inborn",
    "primitive": "primitive",
    "adapted": "adapted",
    "focused": "focused",
    "crude": "crude",
    "deterrent": "deterrent",
    "nexus": "deterrent",       # deterrent/nexus -> deterrent
    "derived": "derived",
    "infected": "infected",
    "head": "infected",          # infected/head -> infected
    "special": "infected",       # infected/special -> infected
    "feral": "feral",
    "hijacked": "hijacked",
    "abomination": "abomination",
    "pure": "pure",
    "preeminent": "pure",        # pure/preeminent -> pure
    "ancient": "ancient",
    "awakened": "awakened",
    "misc": "misc",
    "projectile": "projectile",
}

# Files to skip (base classes, not actual models)
SKIP_FILES = {"ModelSP.java", "ModelEffect.java", "SPModelArmorBase.java", "SPModelBiped.java"}


def discover_model_files(source_dir: str) -> list:
    """
    Discover all Model*.java files in the source directory.
    Returns a list of (java_path, category, output_name) tuples.
    """
    models = []
    model_base = os.path.join(source_dir, "main", "java", "com", "subspaceparasite", "client", "model", "entity")

    if not os.path.isdir(model_base):
        # Try alternate path structure
        model_base = os.path.join(source_dir, "main", "java", "com", "dhanantry", "scapeandrunparasites", "client", "model", "entity")

    if not os.path.isdir(model_base):
        print(f"ERROR: Model directory not found. Tried:")
        print(f"  {os.path.join(source_dir, 'main/java/com/subspaceparasite/client/model/entity')}")
        print(f"  {os.path.join(source_dir, 'main/java/com/dhanantry/scapeandrunparasites/client/model/entity')}")
        sys.exit(1)

    # Walk the directory tree
    for root, dirs, files in os.walk(model_base):
        for fname in sorted(files):
            if not fname.startswith("Model") or not fname.endswith(".java"):
                continue
            if fname in SKIP_FILES:
                continue

            java_path = os.path.join(root, fname)

            # Determine category from directory structure
            rel_path = os.path.relpath(root, model_base)
            parts = rel_path.split(os.sep)

            # Use the deepest meaningful directory as category
            category = "misc"  # default
            for part in reversed(parts):
                if part == ".":
                    continue
                if part in CATEGORY_MAP:
                    category = CATEGORY_MAP[part]
                    break

            # For files directly in entity/ (like ModelProjectileHomming.java)
            if len(parts) == 1 and parts[0] == ".":
                # Check filename for category hints
                if "Projectile" in fname:
                    category = "misc"
                else:
                    category = "misc"

            # Derive output name from Java class name
            # ModelAta.java -> ata
            # ModelBanoAdapted.java -> banoAdapted
            # ModelDodSII.java -> dodSII
            # ModelInfBear.java -> infBear
            # ModelHiGolem.java -> hiGolem
            # ModelFerCow.java -> ferCow
            # ModelAboBodies.java -> aboBodies
            # ModelSpeBear.java -> speBear
            # ModelOroncoAW.java -> oroncoAW
            # ModelCruxA.java -> cruxA
            # ModelTendrilAnged.java -> tendrilAnged
            # ModelInfCowHead.java -> infCowHead
            # ModelProjectileHomming.java -> projectileHomming

            class_name = fname.replace(".java", "")  # ModelAta
            if class_name.startswith("Model"):
                output_name = class_name[5:]  # Ata
                # Lowercase first letter
                output_name = output_name[0].lower() + output_name[1:]  # ata
            else:
                output_name = class_name[0].lower() + class_name[1:]

            models.append((java_path, category, output_name))

    return models


# Comprehensive model-name -> texture-file mapping
# Keys are the output_name from batch conversion, values are the PNG filename (without .png)
# This mapping handles the many naming convention differences between model classes and textures.
TEXTURE_NAME_MAP = {
    # abomination
    "aboBodies": "abobodies",
    "aboHead": "abohead",
    # adapted
    "banoAdapted": "banoa",
    "canraAdapted": "canraa",
    "emanaAdapted": "emanaa",
    "gimAdapted": "gima",
    "hullAdapted": "hull",
    "ikiAdapted": "ikia",
    "lumAdapted": "luma",
    "noglaAdapted": "noglaa",
    "ranracAdapted": "ranraca",
    "shycoAdapted": "shycoa",
    "wymoAdapted": "wymoa",
    "zaaAdapted": "zaaa",
    # ancient
    "oronco": "oronco",
    "oroncoTen": "oroncoten1",
    "terla": "terla",
    # awakened
    "oroncoAW": "oronco",
    "oroncoAWFL": "oronco",
    # crude
    "cruxA": "cruxa",
    "cruxB": "cruxb",
    "done": "done",
    "heed": "heed",
    "host": "host",
    "hostII": "hostii",
    "inhooM": "inhoom",
    "inhooS": "inhoos",
    "leer": "leer",
    "mes": "mes",
    "quac": "quac",
    # derived
    "heblu": "heblu",
    "kirin": "kirin",
    # deterrent
    "dod": "dod",
    "dodSII": "dodsii",
    "dodSIII": "dodsiii",
    "dodSIV": "dodsiv",
    "dodSIVH": "dodsivh",
    "dodT": "dodt",
    "leem": "leem",
    "leemB": "leemb",
    "leemSII": "leemsii",
    "leemSIII": "leemsiii",
    "leemSIV": "leemsiv",
    "nak": "nak",
    "rof": "rof",
    "tonro": "tonro",
    "unvo": "unvo",
    "venkrol": "venkrol",
    "venkrolSII": "venkrolsii",
    "venkrolSIII": "venkrolsiii",
    "venkrolSIV": "venkrolsiv",
    "venkrolSV": "venkrolsv",
    # feral
    "ferBear": "ferbear",
    "ferCow": "fercow",
    "ferEnderman": "ferenderman",
    "ferHorse": "ferhorse",
    "ferHuman": "ferhuman",
    "ferPig": "ferpig",
    "ferSheep": "fersheep",
    "ferVillager": "fervillager",
    "ferWolf": "ferwolf",
    # focused
    "banoFocused": "banov",
    "shycoFocused": "shycov",
    # hijacked
    "hiBlaze": "hiblaze",
    "hiGolem": "higolem",
    "hiSkeleton": "hiskeleton",
    # inborn
    "ata": "ata",
    "buthol": "buthol",
    "gothol": "gothol",
    "kol": "kol",
    "lesh": "lesh",
    "lodo": "lodo",
    "mor": "vermin",
    "mudo": "mudo",
    "nuuh": "nuuh",
    "rathol": "rathol",
    "viin": "vermina",
    # infected - body
    "dorpa": "dorpa",
    "infBear": "infbear",
    "infCow": "cow",
    "infDragonE": "infdragone",
    "infEnderman": "infenderman",
    "infHorse": "infhorse",
    "infHuman": "human",
    "infPig": "pig",
    "infPlayer": "infplayer",
    "infSheep": "sheep",
    "infSquid": "squid",
    "infVillager": "villager",
    "infWolf": "wolf",
    # infected - heads
    "infCowHead": "cowh",
    "infDragonEHead": "infdragone",
    "infEndermanHead": "infenderman",
    "infHorseHead": "infhorse",
    "infHumanHead": "humanh",
    "infPigHead": "pigh",
    "infPlayerHead": "infplayer",
    "infSheepHead": "sheeph",
    "infVillagerHead": "villagerh",
    "infWolfHead": "wolfh",
    # infected - special
    "speBear": "spebear",
    "speCow": "specow",
    "speEnderman": "speenderman",
    "speHuman": "spehuman",
    "speSheep": "spesheep",
    "speVillager": "spevillager",
    # misc
    "biomassPod": "biomasspod",
    "biomassVenkrol": "biomassvenkrol",
    "bombHost": "bombh",
    "bombJinjo": "bombj",
    "bombOmboo": "bombo",
    "gore": "gore",
    "meteor": "sky_flash",
    "nULL": "test",
    "nade": "nade",
    "orbScary": "orbscary",
    "orbVoid": "orbvoid",
    "tendrilAnged": "tendrilanged",
    "tendrilBano": "tendrilbano",
    "tendrilCanra": "tendrilcanra",
    "tendrilDragonELW": "tendrildragonelw",
    "tendrilDragonERW": "tendrildragonerw",
    "tendrilEsor": "tendrilesor",
    "tendrilNogla": "tendrilnogla",
    "tendrilShyco": "tendrilshyco",
    # primitive
    "bano": "bano",
    "canra": "canra",
    "emana": "emana",
    "gim": "gim",
    "hull": "hull",
    "iki": "ikia",
    "lum": "lum",
    "nogla": "nogla",
    "ranrac": "ranrac",
    "shyco": "shyco",
    "wymo": "wymo",
    "zaa": "zaa",
    # projectile
    "dropPod": "ancientpod",
    "projectileHomming": "gnat",
    # pure
    "alafha": "alafha",
    "anged": "anged",
    "elvia": "elvia",
    "esor": "esor",
    "flam": "flam",
    "flog": "flog",
    "ganro": "ganro",
    "jinjo": "jinjo",
    "lencia": "lencia",
    "omboo": "omboo",
    "orch": "orch",
    "pheon": "pheon",
    "rond": "test",
    "tenn": "testb",
    "vesta": "vesta",
}

# Additional texture directories to search (projectile textures, etc.)
EXTRA_TEX_DIRS = {
    "projectile": "projectile",
}


def find_texture(texture_dir: str, entity_name: str) -> str:
    """
    Find the texture PNG for a given entity name using the comprehensive mapping.
    Falls back to heuristics if not in the map.
    Returns the path if found, None otherwise.
    """
    if not texture_dir or not os.path.isdir(texture_dir):
        return None

    # 1. Check the explicit mapping first
    tex_name = TEXTURE_NAME_MAP.get(entity_name)
    if tex_name:
        # Check in main monster directory
        candidate = os.path.join(texture_dir, f"{tex_name}.png")
        if os.path.isfile(candidate):
            return candidate

        # Check in subdirectories (projectile, layer, etc.)
        parent_dir = os.path.dirname(texture_dir)
        for sub in EXTRA_TEX_DIRS.values():
            sub_candidate = os.path.join(parent_dir, sub, f"{tex_name}.png")
            if os.path.isfile(sub_candidate):
                return sub_candidate

    # 2. Fallback heuristic: try lowercase exact match
    lower_name = entity_name.lower()
    candidates = [
        f"{lower_name}.png",
        f"{lower_name}a.png",
        f"{lower_name}h.png",
        f"{lower_name}v.png",
        f"{lower_name}b.png",
    ]

    for candidate in candidates:
        full_path = os.path.join(texture_dir, candidate)
        if os.path.isfile(full_path):
            return full_path

    # 3. Fallback: partial prefix match
    for f in os.listdir(texture_dir):
        if f.endswith(".png"):
            base = f[:-4].lower()
            if base == lower_name or base.startswith(lower_name):
                return os.path.join(texture_dir, f)

    return None


def convert_model(java_path: str, output_dir: str, category: str, output_name: str,
                  texture_path: str = None, namespace: str = "srparasites") -> dict:
    """
    Convert a single model Java file to .bbmodel format.

    Returns a dict with:
        - success: bool
        - output_path: str (if success)
        - error: str (if not success)
        - stats: dict (bones, cubes, texture_size)
    """
    try:
        # Read Java source
        with open(java_path, 'r', encoding='utf-8') as f:
            source = f.read()

        # Step 1: Convert to geo.json using ModelConverter
        from model_converter import ModelConverter
        converter = ModelConverter()
        identifier = f"model.{output_name}"
        result = converter.convert(source, identifier)

        geo_json = result['geo_json']
        bone_mapping = result.get('bone_mapping', {})
        bones = geo_json['model']['bones']
        total_cubes = sum(len(b.get('cubes', [])) for b in bones)
        tex_w = geo_json['model']['texture_width']
        tex_h = geo_json['model']['texture_height']

        # Step 2: Generate .bbmodel
        from bbmodel_generator import BBModelGenerator
        bbgen = BBModelGenerator()

        bbmodel = bbgen.generate(
            geo_json,
            anim_json=None,  # No animation conversion in batch mode
            texture_path=texture_path,
            texture_name=output_name,
            namespace=namespace,
        )

        # Step 3: Save .bbmodel
        cat_dir = os.path.join(output_dir, category)
        os.makedirs(cat_dir, exist_ok=True)
        out_path = os.path.join(cat_dir, f"{output_name}.bbmodel")
        bbgen.save(bbmodel, out_path)

        return {
            'success': True,
            'output_path': out_path,
            'stats': {
                'bones': len(bones),
                'cubes': total_cubes,
                'texture_size': f"{tex_w}x{tex_h}",
            }
        }

    except Exception as e:
        return {
            'success': False,
            'error': f"{type(e).__name__}: {str(e)}",
            'traceback': traceback.format_exc(),
        }


def main():
    parser = argparse.ArgumentParser(
        description="Batch convert ALL SRParasites creature models to .bbmodel"
    )
    parser.add_argument(
        "--source", required=True,
        help="Path to the source repo's src/ directory"
    )
    parser.add_argument(
        "--output", required=True,
        help="Output directory for converted .bbmodel files"
    )
    parser.add_argument(
        "--textures",
        help="Path to the textures directory (entity/monster/)"
    )
    parser.add_argument(
        "--namespace", default="srparasites",
        help="Resource namespace (default: srparasites)"
    )
    parser.add_argument(
        "--skip-errors", action="store_true",
        help="Continue on conversion errors instead of stopping"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("  MinecraftModelMigrator-Pro - BATCH CONVERTER")
    print("  MC 1.12.2 → .bbmodel (Blockbench Bedrock)")
    print("=" * 70)
    print()

    # Discover model files
    print("[1/3] Discovering model files...")
    models = discover_model_files(args.source)
    print(f"      Found {len(models)} model files")

    # Group by category for display
    categories = {}
    for _, cat, name in models:
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(name)

    print()
    for cat in sorted(categories.keys()):
        print(f"  {cat}: {len(categories[cat])} models - {', '.join(sorted(categories[cat])[:5])}{'...' if len(categories[cat]) > 5 else ''}")

    # Convert all models
    print(f"\n[2/3] Converting {len(models)} models...")
    print("-" * 70)

    results = {'success': [], 'failed': []}

    for i, (java_path, category, output_name) in enumerate(models, 1):
        # Find texture
        tex_path = None
        if args.textures:
            tex_path = find_texture(args.textures, output_name)

        print(f"  [{i:3d}/{len(models)}] {category}/{output_name}...", end=" ", flush=True)

        result = convert_model(
            java_path, args.output, category, output_name,
            texture_path=tex_path,
            namespace=args.namespace,
        )

        if result['success']:
            stats = result['stats']
            print(f"OK ({stats['bones']} bones, {stats['cubes']} cubes, {stats['texture_size']})")
            results['success'].append((category, output_name, stats))
        else:
            print(f"FAILED: {result['error']}")
            results['failed'].append((category, output_name, result.get('error', 'Unknown error')))
            if not args.skip_errors:
                if 'traceback' in result:
                    print(f"\n{result['traceback']}")
                print(f"\nStopping due to error. Use --skip-errors to continue.")
                break

    # Summary
    print()
    print("=" * 70)
    print(f"  BATCH CONVERSION SUMMARY")
    print("=" * 70)
    print(f"  Total models:   {len(models)}")
    print(f"  Successful:     {len(results['success'])}")
    print(f"  Failed:         {len(results['failed'])}")
    print()

    if results['failed']:
        print("  Failed models:")
        for cat, name, err in results['failed']:
            print(f"    - {cat}/{name}: {err}")
        print()

    # Total stats
    total_bones = sum(s['bones'] for _, _, s in results['success'])
    total_cubes = sum(s['cubes'] for _, _, s in results['success'])
    print(f"  Total bones converted: {total_bones}")
    print(f"  Total cubes converted: {total_cubes}")

    # Output directory listing
    print(f"\n  Output directory: {args.output}")
    for cat in sorted(categories.keys()):
        cat_dir = os.path.join(args.output, cat)
        if os.path.isdir(cat_dir):
            files = [f for f in os.listdir(cat_dir) if f.endswith('.bbmodel')]
            print(f"    {cat}/: {len(files)} files")

    print()
    return len(results['failed']) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
