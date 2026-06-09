#!/usr/bin/env python3
"""
Full Re-conversion Script - Re-convert ALL models with v10 improvements
========================================================================
Re-converts ALL model categories from Java source with the v10 converter
improvements (quintic smoothstep loop continuity, improved interpolation
selection, overshoot protection) and embeds textures.
"""

import argparse
import json
import os
import sys
import traceback
import gc

# Add converter directory to path
CONVERTER_DIR = os.path.dirname(os.path.abspath(__file__))
if CONVERTER_DIR not in sys.path:
    sys.path.insert(0, CONVERTER_DIR)

BASE_DIR = os.path.join(CONVERTER_DIR, "..")
MROLF_DIR = os.path.join(BASE_DIR, "MROLF-TGNBF")
SOURCE_DIR = os.path.join(BASE_DIR, "Qom-Inseac", "src")
JAVA_BASE = os.path.join(SOURCE_DIR, "main", "java", "com", "subspaceparasite", "client", "model", "entity")
TEXTURE_DIR = os.path.join(BASE_DIR, "jar_extract", "assets", "srparasites", "textures", "entity", "monster")
QOM_TEX_DIR = os.path.join(SOURCE_DIR, "main", "resources", "assets", "subspaceparasite", "textures", "entity", "monster")
QOM_PROJ_TEX_DIR = os.path.join(SOURCE_DIR, "main", "resources", "assets", "subspaceparasite", "textures", "entity", "projectile")
PROJ_TEX_DIR = os.path.join(BASE_DIR, "jar_extract", "assets", "srparasites", "textures", "entity", "projectile")

SKIP_FILES = {"ModelSP.java", "ModelEffect.java", "SPModelArmorBase.java", "SPModelBiped.java"}

# Map directory names to output category names
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

# Comprehensive texture name mapping
TEXTURE_NAME_MAP = {
    "aboBodies": "abobodies", "aboHead": "abohead",
    "banoAdapted": "banoa", "canraAdapted": "canraa", "emanaAdapted": "emanaa",
    "gimAdapted": "gima", "hullAdapted": "hull", "ikiAdapted": "ikia",
    "lumAdapted": "luma", "noglaAdapted": "noglaa", "ranracAdapted": "ranraca",
    "shycoAdapted": "shycoa", "wymoAdapted": "wymoa", "zaaAdapted": "zaaa",
    "oronco": "oronco", "oroncoTen": "oroncoten1", "terla": "terla",
    "oroncoAW": "oronco", "oroncoAWFL": "oronco",
    "cruxA": "cruxa", "cruxB": "cruxb", "done": "done", "heed": "heed",
    "host": "host", "hostII": "hostii", "inhooM": "inhoom", "inhooS": "inhoos",
    "leer": "leer", "mes": "mes", "quac": "quac",
    "heblu": "heblu", "kirin": "kirin",
    "dod": "dod", "dodSII": "dodsii", "dodSIII": "dodsiii", "dodSIV": "dodsiv",
    "dodSIVH": "dodsivh", "dodT": "dodt",
    "leem": "leem", "leemB": "leemb", "leemSII": "leemsii", "leemSIII": "leemsiii",
    "leemSIV": "leemsiv", "nak": "nak", "rof": "rof", "tonro": "tonro", "unvo": "unvo",
    "venkrol": "venkrol", "venkrolSII": "venkrolsii", "venkrolSIII": "venkrolsiii",
    "venkrolSIV": "venkrolsiv", "venkrolSV": "venkrolsv",
    "ferBear": "ferbear", "ferCow": "fercow", "ferEnderman": "ferenderman",
    "ferHorse": "ferhorse", "ferHuman": "ferhuman", "ferPig": "ferpig",
    "ferSheep": "fersheep", "ferVillager": "fervillager", "ferWolf": "ferwolf",
    "banoFocused": "banov", "shycoFocused": "shycov",
    "hiBlaze": "hiblaze", "hiGolem": "higolem", "hiSkeleton": "hiskeleton",
    "ata": "ata", "buthol": "buthol", "gothol": "gothol", "kol": "kol",
    "lesh": "lesh", "lodo": "lodo", "mor": "vermin", "mudo": "mudo",
    "nuuh": "nuuh", "rathol": "rathol", "viin": "vermina",
    "dorpa": "dorpa", "infBear": "infbear", "infCow": "cow",
    "infDragonE": "infdragone", "infEnderman": "infenderman",
    "infHorse": "infhorse", "infHuman": "human", "infPig": "pig",
    "infPlayer": "infplayer", "infSheep": "sheep", "infSquid": "squid",
    "infVillager": "villager", "infWolf": "wolf",
    "infCowHead": "cowh", "infDragonEHead": "infdragone",
    "infEndermanHead": "infenderman", "infHorseHead": "infhorse",
    "infHumanHead": "humanh", "infPigHead": "pigh",
    "infPlayerHead": "infplayer", "infSheepHead": "sheeph",
    "infVillagerHead": "villagerh", "infWolfHead": "wolfh",
    "speBear": "spebear", "speCow": "specow", "speEnderman": "speenderman",
    "speHuman": "spehuman", "speSheep": "spesheep", "speVillager": "spevillager",
    "biomassPod": "biomasspod", "biomassVenkrol": "biomassvenkrol",
    "bombHost": "bombh", "bombJinjo": "bombj", "bombOmboo": "bombo",
    "gore": "gore", "meteor": "sky_flash", "nULL": "test", "nade": "nade",
    "orbScary": "orbscary", "orbVoid": "orbvoid",
    "tendrilAnged": "tendrilanged", "tendrilBano": "tendrilbano",
    "tendrilCanra": "tendrilcanra", "tendrilDragonELW": "tendrildragonelw",
    "tendrilDragonERW": "tendrildragonerw", "tendrilEsor": "tendrilesor",
    "tendrilNogla": "tendrilnogla", "tendrilShyco": "tendrilshyco",
    "bano": "bano", "canra": "canra", "emana": "emana", "gim": "gim",
    "hull": "hull", "iki": "ikia", "lum": "lum", "nogla": "nogla",
    "ranrac": "ranrac", "shyco": "shyco", "wymo": "wymo", "zaa": "zaa",
    "dropPod": "ancientpod", "projectileHomming": "gnat",
    "alafha": "alafha", "anged": "anged", "elvia": "elvia", "esor": "esor",
    "flam": "flam", "flog": "flog", "ganro": "ganro", "jinjo": "jinjo",
    "lencia": "lencia", "omboo": "omboo", "orch": "orch", "pheon": "pheon",
    "rond": "test", "tenn": "testb", "vesta": "vesta",
}


def find_texture(entity_name: str) -> str:
    """Find the texture PNG for a given entity name."""
    tex_name = TEXTURE_NAME_MAP.get(entity_name)
    search_dirs = [TEXTURE_DIR, PROJ_TEX_DIR, QOM_TEX_DIR, QOM_PROJ_TEX_DIR]
    
    if tex_name:
        for search_dir in search_dirs:
            if not search_dir or not os.path.isdir(search_dir):
                continue
            candidate = os.path.join(search_dir, f"{tex_name}.png")
            if os.path.isfile(candidate):
                return candidate
            # Case-insensitive match
            for f in os.listdir(search_dir):
                if f.lower() == f"{tex_name.lower()}.png":
                    return os.path.join(search_dir, f)
    
    # Fallback: try direct name
    lower_name = entity_name.lower()
    for search_dir in search_dirs:
        if not search_dir or not os.path.isdir(search_dir):
            continue
        for suffix in ["", "a", "h", "v", "b"]:
            candidate = os.path.join(search_dir, f"{lower_name}{suffix}.png")
            if os.path.isfile(candidate):
                return candidate
    
    return None


def discover_all_models():
    """Discover all Model*.java files organized by category."""
    models = []
    for root, dirs, files in os.walk(JAVA_BASE):
        for fname in sorted(files):
            if not fname.startswith("Model") or not fname.endswith(".java"):
                continue
            if fname in SKIP_FILES:
                continue
            
            java_path = os.path.join(root, fname)
            
            # Determine category from directory
            rel_path = os.path.relpath(root, JAVA_BASE)
            parts = rel_path.split(os.sep)
            category = "misc"
            for part in reversed(parts):
                if part == ".":
                    continue
                if part in CATEGORY_MAP:
                    category = CATEGORY_MAP[part]
                    break
            
            # Derive entity name from class name
            class_name = fname.replace(".java", "")
            if class_name.startswith("Model"):
                entity_name = class_name[5:]
                entity_name = entity_name[0].lower() + entity_name[1:]
            else:
                entity_name = class_name[0].lower() + class_name[1:]
            
            models.append((java_path, category, entity_name))
    
    return models


def main():
    print("=" * 70)
    print("  MinecraftModelMigrator-Pro - FULL RE-CONVERSION v10")
    print("  Re-converting ALL models with v10 animation improvements")
    print("=" * 70)
    print()
    
    # Discover all model files
    print("[1/3] Discovering model files...")
    models = discover_all_models()
    
    # Group by category
    categories = {}
    for _, cat, name in models:
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(name)
    
    print(f"      Found {len(models)} model files")
    for cat in sorted(categories.keys()):
        print(f"        {cat}: {len(categories[cat])} models")
    
    # Convert all models
    print(f"\n[2/3] Converting {len(models)} models with v10 improvements...")
    print("-" * 70)
    
    from model_converter import ModelConverter
    from bbmodel_generator import BBModelGenerator
    from animation_extractor import AnimationExtractor
    
    results = {'success': [], 'failed': []}
    
    for i, (java_path, category, entity_name) in enumerate(models, 1):
        # Skip derived - handled by specialized generators (heblu/kirin)
        if category == "derived":
            continue
        
        tex_path = find_texture(entity_name)
        
        print(f"  [{i:3d}/{len(models)}] {category}/{entity_name}...", end=" ", flush=True)
        
        try:
            with open(java_path, 'r') as f:
                source = f.read()
            
            # Convert to geo.json
            converter = ModelConverter()
            result = converter.convert(source, f'model.{entity_name}')
            geo_json = result['geo_json']
            bone_mapping = result.get('bone_mapping', {})
            
            # Extract animations
            anim_json = None
            try:
                anim_extractor = AnimationExtractor(bone_mapping)
                anim_json = anim_extractor.extract(source, entity_name, max_bones=150)
            except Exception as e:
                print(f"[ANIM WARN: {e}]", end=" ", flush=True)
            
            # Generate bbmodel
            bbgen = BBModelGenerator()
            bbmodel = bbgen.generate(
                geo_json,
                anim_json=anim_json,
                texture_path=tex_path,
                texture_name=entity_name,
                namespace='srparasites',
            )
            
            # Save
            cat_dir = os.path.join(MROLF_DIR, category)
            os.makedirs(cat_dir, exist_ok=True)
            out_path = os.path.join(cat_dir, f"{entity_name}.bbmodel")
            bbgen.save(bbmodel, out_path)
            
            bones = geo_json['model']['bones']
            total_cubes = sum(len(b.get('cubes', [])) for b in bones)
            anims = bbmodel.get('animations', [])
            size = os.path.getsize(out_path)
            
            print(f"OK ({len(bones)} bones, {total_cubes} cubes, {len(anims)} anims, {size/1024:.0f}KB)")
            results['success'].append((category, entity_name, len(bones), total_cubes, len(anims), size))
            
        except Exception as e:
            print(f"FAILED: {e}")
            results['failed'].append((category, entity_name, str(e)))
        
        # Garbage collection every 10 models
        if i % 10 == 0:
            gc.collect()
    
    # Summary
    print()
    print("=" * 70)
    print(f"  FULL RE-CONVERSION SUMMARY (v10)")
    print("=" * 70)
    print(f"  Total models:   {len(models) - len([m for m in models if m[1] == 'derived'])}")
    print(f"  Successful:     {len(results['success'])}")
    print(f"  Failed:         {len(results['failed'])}")
    
    if results['failed']:
        print("\n  Failed models:")
        for cat, name, err in results['failed']:
            print(f"    - {cat}/{name}: {err[:80]}")
    
    total_size = sum(r[5] for r in results['success'])
    total_anims = sum(r[4] for r in results['success'])
    print(f"\n  Total animations: {total_anims}")
    print(f"  Total file size:  {total_size/1024/1024:.1f} MB")
    
    # Category breakdown
    print("\n  By category:")
    cat_stats = {}
    for cat, name, bones, cubes, anims, size in results['success']:
        if cat not in cat_stats:
            cat_stats[cat] = {'count': 0, 'anims': 0, 'size': 0}
        cat_stats[cat]['count'] += 1
        cat_stats[cat]['anims'] += anims
        cat_stats[cat]['size'] += size
    
    for cat in sorted(cat_stats.keys()):
        s = cat_stats[cat]
        print(f"    {cat:15s}: {s['count']:3d} models, {s['anims']:3d} anims, {s['size']/1024/1024:.1f} MB")
    
    print()


if __name__ == "__main__":
    main()
