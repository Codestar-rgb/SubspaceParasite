#!/usr/bin/env python3
"""
Re-convert ALL non-derived, non-primitive MROLF-TGNBF models from Java source
using the upgraded v10 converter.

Pipeline per model:
  1. Read Java source from Qom-Inseac
  2. Convert with ModelConverter → geo.json
  3. Extract animations with AnimationExtractor (max_bones=150, catch errors gracefully)
  4. Generate bbmodel with BBModelGenerator (including texture_path)
  5. Save to MROLF-TGNBF/{category}/{name}.bbmodel

Categories to convert (all except 'derived' and 'primitive'):
  inborn, adapted, focused, crude, deterrent, feral, hijacked,
  infected, pure, ancient, awakened, abomination, misc, projectile
"""

import gc
import json
import os
import sys
import time
import traceback

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
CONVERTER_DIR = os.path.dirname(os.path.abspath(__file__))
if CONVERTER_DIR not in sys.path:
    sys.path.insert(0, CONVERTER_DIR)

PROJECT_ROOT = os.path.abspath(os.path.join(CONVERTER_DIR, ".."))
SOURCE_BASE = os.path.join(
    PROJECT_ROOT,
    "Qom-Inseac", "src", "main", "java",
    "com", "subspaceparasite", "client", "model", "entity",
)
OUTPUT_BASE = os.path.join(PROJECT_ROOT, "MROLF-TGNBF")

TEXTURE_DIRS = [
    os.path.join(PROJECT_ROOT, "jar_extract", "assets", "srparasites", "textures", "entity", "monster"),
    os.path.join(
        PROJECT_ROOT, "Qom-Inseac", "src", "main", "resources",
        "assets", "subspaceparasite", "textures", "entity", "monster",
    ),
]

# Categories to skip (already done)
SKIP_CATEGORIES = {"derived", "primitive"}

# ---------------------------------------------------------------------------
# CATEGORY_MAP  (directory name → output category)
# Copied from batch_convert.py
# ---------------------------------------------------------------------------
CATEGORY_MAP = {
    "inborn": "inborn",
    "primitive": "primitive",
    "adapted": "adapted",
    "focused": "focused",
    "crude": "crude",
    "deterrent": "deterrent",
    "nexus": "deterrent",
    "derived": "derived",
    "infected": "infected",
    "head": "infected",
    "special": "infected",
    "feral": "feral",
    "hijacked": "hijacked",
    "abomination": "abomination",
    "pure": "pure",
    "preeminent": "pure",
    "ancient": "ancient",
    "awakened": "awakened",
    "misc": "misc",
    "projectile": "projectile",
}

# ---------------------------------------------------------------------------
# TEXTURE_NAME_MAP  (output_name → texture PNG name without .png)
# Copied from batch_convert.py
# ---------------------------------------------------------------------------
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

# Files to skip (base classes, not actual models)
SKIP_FILES = {"ModelSP.java", "ModelEffect.java", "SPModelArmorBase.java", "SPModelBiped.java"}


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_model_files(source_dir: str) -> list:
    """
    Discover all Model*.java files, returning
    [(java_path, category, output_name), ...]
    """
    models = []
    if not os.path.isdir(source_dir):
        print(f"ERROR: Source directory not found: {source_dir}")
        sys.exit(1)

    for root, dirs, files in os.walk(source_dir):
        for fname in sorted(files):
            if not fname.startswith("Model") or not fname.endswith(".java"):
                continue
            if fname in SKIP_FILES:
                continue

            java_path = os.path.join(root, fname)

            # Determine category from directory structure
            rel_path = os.path.relpath(root, source_dir)
            parts = rel_path.split(os.sep)

            category = "misc"  # default
            for part in reversed(parts):
                if part == ".":
                    continue
                if part in CATEGORY_MAP:
                    category = CATEGORY_MAP[part]
                    break

            # For files directly in entity/ root
            if len(parts) == 1 and parts[0] == ".":
                if "Projectile" in fname:
                    category = "misc"
                else:
                    category = "misc"

            # Derive output name from Java class name
            class_name = fname.replace(".java", "")
            if class_name.startswith("Model"):
                output_name = class_name[5:]
                output_name = output_name[0].lower() + output_name[1:]
            else:
                output_name = class_name[0].lower() + class_name[1:]

            models.append((java_path, category, output_name))

    return models


# ---------------------------------------------------------------------------
# Texture finding
# ---------------------------------------------------------------------------

def find_texture(entity_name: str) -> str | None:
    """
    Find the texture PNG for a given entity name.
    Searches both texture directories using TEXTURE_NAME_MAP + fallback.
    """
    tex_name = TEXTURE_NAME_MAP.get(entity_name)

    for tex_dir in TEXTURE_DIRS:
        if not tex_dir or not os.path.isdir(tex_dir):
            continue

        # 1. Explicit mapping
        if tex_name:
            candidate = os.path.join(tex_dir, f"{tex_name}.png")
            if os.path.isfile(candidate):
                return candidate

        # 2. Fallback: lowercase exact match
        lower_name = entity_name.lower()
        for suffix in ("", "a", "h", "v", "b"):
            candidate = os.path.join(tex_dir, f"{lower_name}{suffix}.png")
            if os.path.isfile(candidate):
                return candidate

        # 3. Fallback: partial prefix match
        try:
            for f in os.listdir(tex_dir):
                if f.endswith(".png"):
                    base = f[:-4].lower()
                    if base == lower_name or base.startswith(lower_name):
                        return os.path.join(tex_dir, f)
        except OSError:
            pass

    return None


# ---------------------------------------------------------------------------
# Single model conversion
# ---------------------------------------------------------------------------

def convert_model(java_path: str, output_dir: str, category: str, output_name: str,
                  texture_path: str = None, namespace: str = "srparasites") -> dict:
    """
    Convert a single model Java file to .bbmodel format.
    Returns dict with 'success', 'output_path'/'error', 'stats'.
    """
    try:
        # Read Java source
        with open(java_path, "r", encoding="utf-8") as f:
            source = f.read()

        # Step 1: Convert to geo.json using ModelConverter
        from model_converter import ModelConverter
        converter = ModelConverter()
        identifier = f"model.{output_name}"
        result = converter.convert(source, identifier)

        geo_json = result["geo_json"]
        bone_mapping = result.get("bone_mapping", {})
        bones = geo_json["model"]["bones"]
        total_cubes = sum(len(b.get("cubes", [])) for b in bones)
        tex_w = geo_json["model"]["texture_width"]
        tex_h = geo_json["model"]["texture_height"]

        # Step 2: Extract animations (graceful error handling)
        anim_json = None
        anim_count = 0
        try:
            from animation_extractor import AnimationExtractor
            anim_extractor = AnimationExtractor(bone_mapping)
            anim_json = anim_extractor.extract(source, output_name, max_bones=150)
            if anim_json and "animations" in anim_json:
                anim_count = len(anim_json["animations"])
        except Exception as e:
            print(f"\n    [ANIM WARN] {output_name}: {type(e).__name__}: {e}")
            anim_json = None

        # Step 3: Generate .bbmodel
        from bbmodel_generator import BBModelGenerator
        bbgen = BBModelGenerator()

        bbmodel = bbgen.generate(
            geo_json,
            anim_json=anim_json,
            texture_path=texture_path,
            texture_name=output_name,
            namespace=namespace,
        )

        # Step 4: Save .bbmodel
        cat_dir = os.path.join(output_dir, category)
        os.makedirs(cat_dir, exist_ok=True)
        out_path = os.path.join(cat_dir, f"{output_name}.bbmodel")
        bbgen.save(bbmodel, out_path)

        stats = {
            "bones": len(bones),
            "cubes": total_cubes,
            "texture_size": f"{tex_w}x{tex_h}",
        }
        if anim_count > 0:
            stats["animations"] = anim_count

        return {
            "success": True,
            "output_path": out_path,
            "stats": stats,
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {str(e)}",
            "traceback": traceback.format_exc(),
        }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("  MROLF-TGNBF v10 Re-converter - Remaining Categories")
    print("  MC 1.12.2 → .bbmodel (Blockbench Bedrock)")
    print("  Skipping: derived, primitive")
    print("=" * 70)
    print()

    # Discover model files
    print("[1/3] Discovering model files...")
    all_models = discover_model_files(SOURCE_BASE)
    print(f"      Found {len(all_models)} total model files")

    # Filter: skip derived and primitive
    models = [(p, c, n) for p, c, n in all_models if c not in SKIP_CATEGORIES]
    skipped = len(all_models) - len(models)
    print(f"      Skipping {skipped} models in: {', '.join(sorted(SKIP_CATEGORIES))}")
    print(f"      Processing {len(models)} models")

    # Group by category for display
    categories = {}
    for _, cat, name in models:
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(name)

    print()
    for cat in sorted(categories.keys()):
        names = sorted(categories[cat])
        preview = ", ".join(names[:5])
        suffix = "..." if len(names) > 5 else ""
        print(f"  {cat}: {len(names)} models - {preview}{suffix}")

    # Convert all models
    print(f"\n[2/3] Converting {len(models)} models...")
    print("-" * 70)

    results = {"success": [], "failed": []}
    start_time = time.time()

    for i, (java_path, category, output_name) in enumerate(models, 1):
        # Find texture
        tex_path = find_texture(output_name)

        print(f"  [{i:3d}/{len(models)}] {category}/{output_name}...", end=" ", flush=True)

        result = convert_model(
            java_path, OUTPUT_BASE, category, output_name,
            texture_path=tex_path,
            namespace="srparasites",
        )

        if result["success"]:
            stats = result["stats"]
            anim_info = f", {stats['animations']} anims" if "animations" in stats else ""
            tex_info = " [TEX]" if tex_path else " [NO-TEX]"
            print(f"OK ({stats['bones']} bones, {stats['cubes']} cubes, {stats['texture_size']}{anim_info}){tex_info}")
            results["success"].append((category, output_name, stats))
        else:
            print(f"FAILED: {result['error']}")
            results["failed"].append((category, output_name, result.get("error", "Unknown error")))

        # Garbage collect every 10 models
        if i % 10 == 0:
            gc.collect()
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(models) - i) / rate if rate > 0 else 0
            print(f"         [gc] {i}/{len(models)} done, {rate:.1f} models/s, ETA {eta:.0f}s")

    elapsed = time.time() - start_time

    # Summary
    print()
    print("=" * 70)
    print(f"  RE-CONVERSION SUMMARY (v10)")
    print("=" * 70)
    print(f"  Total models:   {len(models)}")
    print(f"  Successful:     {len(results['success'])}")
    print(f"  Failed:         {len(results['failed'])}")
    print(f"  Time:           {elapsed:.1f}s")
    print()

    if results["failed"]:
        print("  Failed models:")
        for cat, name, err in results["failed"]:
            print(f"    - {cat}/{name}: {err}")
        print()

    # Total stats
    total_bones = sum(s["bones"] for _, _, s in results["success"])
    total_cubes = sum(s["cubes"] for _, _, s in results["success"])
    total_anims = sum(s.get("animations", 0) for _, _, s in results["success"])
    print(f"  Total bones converted: {total_bones}")
    print(f"  Total cubes converted: {total_cubes}")
    print(f"  Total animations:      {total_anims}")

    # Category breakdown
    print()
    print("  Per-category results:")
    cat_results = {}
    for cat, name, stats in results["success"]:
        if cat not in cat_results:
            cat_results[cat] = {"count": 0, "bones": 0, "cubes": 0, "anims": 0}
        cat_results[cat]["count"] += 1
        cat_results[cat]["bones"] += stats["bones"]
        cat_results[cat]["cubes"] += stats["cubes"]
        cat_results[cat]["anims"] += stats.get("animations", 0)

    for cat in sorted(cat_results.keys()):
        r = cat_results[cat]
        anim_str = f", {r['anims']} anims" if r["anims"] > 0 else ""
        print(f"    {cat:12s}: {r['count']:3d} models, {r['bones']:5d} bones, {r['cubes']:5d} cubes{anim_str}")

    # Output directory listing
    print(f"\n  Output directory: {OUTPUT_BASE}")
    for cat in sorted(categories.keys()):
        cat_dir = os.path.join(OUTPUT_BASE, cat)
        if os.path.isdir(cat_dir):
            files = [f for f in os.listdir(cat_dir) if f.endswith(".bbmodel")]
            print(f"    {cat}/: {len(files)} .bbmodel files")

    print()
    return len(results["failed"]) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
