#!/usr/bin/env python3
"""
Re-convert all MROLF-TGNBF bbmodel files with v10 animation quality improvements
and embed missing textures.

This script:
1. Re-converts primitive models from Java source with v10 converter
2. Embeds textures into ALL bbmodel files that are missing them
3. Uses the Qom-Inseac source repo and jar_extract for texture files
"""

import base64
import json
import os
import sys
import traceback

# Add converter directory to path
CONVERTER_DIR = os.path.dirname(os.path.abspath(__file__))
if CONVERTER_DIR not in sys.path:
    sys.path.insert(0, CONVERTER_DIR)

BASE_DIR = os.path.join(CONVERTER_DIR, "..")
MROLF_DIR = os.path.join(BASE_DIR, "MROLF-TGNBF")
SOURCE_DIR = os.path.join(BASE_DIR, "Qom-Inseac", "src")
TEXTURE_DIR = os.path.join(BASE_DIR, "jar_extract", "assets", "srparasites", "textures", "entity", "monster")
PROJECTILE_TEX_DIR = os.path.join(BASE_DIR, "jar_extract", "assets", "srparasites", "textures", "entity", "projectile")
LAYER_TEX_DIR = os.path.join(BASE_DIR, "jar_extract", "assets", "srparasites", "textures", "entity", "layer")

# Also check Qom-Inseac textures
QOM_TEX_DIR = os.path.join(SOURCE_DIR, "main", "resources", "assets", "subspaceparasite", "textures", "entity", "monster")
QOM_PROJ_TEX_DIR = os.path.join(SOURCE_DIR, "main", "resources", "assets", "subspaceparasite", "textures", "entity", "projectile")

# Java source base path
JAVA_BASE = os.path.join(SOURCE_DIR, "main", "java", "com", "subspaceparasite", "client", "model", "entity")


def find_texture(entity_name: str) -> str:
    """Find the texture PNG for a given entity name."""
    from batch_convert import TEXTURE_NAME_MAP, find_texture as batch_find_texture
    
    # Try jar_extract textures first (these are the actual mod textures)
    tex_name = TEXTURE_NAME_MAP.get(entity_name)
    
    search_dirs = [TEXTURE_DIR, PROJECTILE_TEX_DIR, LAYER_TEX_DIR, QOM_TEX_DIR, QOM_PROJ_TEX_DIR]
    
    if tex_name:
        for search_dir in search_dirs:
            if not search_dir or not os.path.isdir(search_dir):
                continue
            # Exact match
            candidate = os.path.join(search_dir, f"{tex_name}.png")
            if os.path.isfile(candidate):
                return candidate
            # Case-insensitive match
            if os.path.isdir(search_dir):
                for f in os.listdir(search_dir):
                    if f.lower() == f"{tex_name.lower()}.png":
                        return os.path.join(search_dir, f)
    
    # Try direct name match in all directories
    lower_name = entity_name.lower()
    for search_dir in search_dirs:
        if not search_dir or not os.path.isdir(search_dir):
            continue
        candidates = [
            f"{lower_name}.png",
            f"{lower_name}a.png",
            f"{lower_name}h.png",
            f"{lower_name}v.png",
        ]
        for candidate in candidates:
            full_path = os.path.join(search_dir, candidate)
            if os.path.isfile(full_path):
                return full_path
    
    # Try bedrock PNGs as fallback
    # Walk MROLF-TGNBF/bedrock/ for matching PNGs
    bedrock_dir = os.path.join(MROLF_DIR, "bedrock")
    if os.path.isdir(bedrock_dir):
        for root, dirs, files in os.walk(bedrock_dir):
            for f in files:
                if f.lower() == f"{lower_name}.png":
                    return os.path.join(root, f)
    
    return None


def embed_texture_in_bbmodel(bbmodel_path: str, texture_path: str) -> bool:
    """Embed a texture into an existing bbmodel file."""
    try:
        with open(bbmodel_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Read and encode texture
        with open(texture_path, 'rb') as f:
            png_data = f.read()
        
        b64_data = base64.b64encode(png_data).decode('ascii')
        data_uri = f"data:image/png;base64,{b64_data}"
        
        # Update texture entry
        textures = data.get('textures', [])
        if textures:
            textures[0]['source'] = data_uri
        else:
            textures.append({
                'name': os.path.splitext(os.path.basename(texture_path))[0],
                'folder': 'entity/monster',
                'namespace': 'srparasites',
                'source': data_uri,
            })
        
        # Save
        with open(bbmodel_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        
        return True
    except Exception as e:
        print(f"    ERROR embedding texture: {e}")
        return False


def reconvert_from_java(java_path: str, output_path: str, texture_path: str, entity_name: str) -> bool:
    """Re-convert a model from Java source with the v10 converter."""
    try:
        from model_converter import ModelConverter
        from bbmodel_generator import BBModelGenerator
        from animation_extractor import AnimationExtractor
        
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
            print(f"    [ANIM WARN] {entity_name}: {e}")
        
        # Generate bbmodel
        bbgen = BBModelGenerator()
        bbmodel = bbgen.generate(
            geo_json,
            anim_json=anim_json,
            texture_path=texture_path,
            texture_name=entity_name,
            namespace='srparasites',
        )
        
        # Save
        bbgen.save(bbmodel, output_path)
        
        bones = geo_json['model']['bones']
        total_cubes = sum(len(b.get('cubes', [])) for b in bones)
        anims = bbmodel.get('animations', [])
        print(f"    OK: {len(bones)} bones, {total_cubes} cubes, {len(anims)} anims, "
              f"{os.path.getsize(output_path):,} bytes")
        return True
        
    except Exception as e:
        print(f"    FAILED: {e}")
        traceback.print_exc()
        return False


def get_category_from_path(java_path: str) -> str:
    """Determine category from the Java file's directory structure."""
    from batch_convert import CATEGORY_MAP
    rel_path = os.path.relpath(java_path, JAVA_BASE)
    parts = rel_path.split(os.sep)
    
    for part in reversed(parts):
        if part == ".":
            continue
        if part in CATEGORY_MAP:
            return CATEGORY_MAP[part]
    return "misc"


def get_entity_name(java_path: str) -> str:
    """Derive entity name from Java filename."""
    fname = os.path.basename(java_path)
    class_name = fname.replace(".java", "")  # ModelBano
    if class_name.startswith("Model"):
        output_name = class_name[5:]  # Bano
        output_name = output_name[0].lower() + output_name[1:]  # bano
    else:
        output_name = class_name[0].lower() + class_name[1:]
    return output_name


def main():
    skip_files = {"ModelSP.java", "ModelEffect.java", "SPModelArmorBase.java", "SPModelBiped.java"}
    
    print("=" * 70)
    print("  MinecraftModelMigrator-Pro - RE-CONVERT & TEXTURE FIX v10")
    print("  Fixing animation quality + embedding missing textures")
    print("=" * 70)
    print()
    
    # ========================================================================
    # Phase 1: Re-convert primitive models from Java source
    # ========================================================================
    print("[Phase 1] Re-converting primitive models from Java source (v10)...")
    print("-" * 70)
    
    primitive_dir = os.path.join(JAVA_BASE, "primitive")
    if os.path.isdir(primitive_dir):
        java_files = sorted([f for f in os.listdir(primitive_dir) 
                            if f.startswith("Model") and f.endswith(".java") and f not in skip_files])
        
        for fname in java_files:
            entity_name = get_entity_name(fname)
            java_path = os.path.join(primitive_dir, fname)
            output_path = os.path.join(MROLF_DIR, "primitive", f"{entity_name}.bbmodel")
            
            tex_path = find_texture(entity_name)
            
            print(f"  [{entity_name}]", end=" ")
            reconvert_from_java(java_path, output_path, tex_path, entity_name)
    
    # ========================================================================
    # Phase 2: Embed textures into ALL bbmodel files that are missing them
    # ========================================================================
    print(f"\n[Phase 2] Embedding missing textures into bbmodel files...")
    print("-" * 70)
    
    fixed_count = 0
    missing_count = 0
    already_has = 0
    
    # Walk all category directories
    categories = ['primitive', 'inborn', 'adapted', 'focused', 'crude', 'deterrent',
                  'feral', 'hijacked', 'infected', 'pure', 'ancient', 'awakened',
                  'abomination', 'misc', 'projectile']
    # Skip 'derived' - already has textures
    
    for category in categories:
        cat_dir = os.path.join(MROLF_DIR, category)
        if not os.path.isdir(cat_dir):
            continue
        
        bbmodels = sorted([f for f in os.listdir(cat_dir) if f.endswith('.bbmodel')])
        
        for bm in bbmodels:
            entity_name = os.path.splitext(bm)[0]
            bbmodel_path = os.path.join(cat_dir, bm)
            
            # Check if texture is already embedded
            try:
                with open(bbmodel_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                textures = data.get('textures', [])
                has_texture = False
                if textures:
                    src = textures[0].get('source', '')
                    if src and len(src) > 100:
                        has_texture = True
                
                if has_texture:
                    already_has += 1
                    continue
            except:
                pass
            
            # Find and embed texture
            tex_path = find_texture(entity_name)
            
            if tex_path:
                print(f"  Embedding {category}/{entity_name}: {os.path.basename(tex_path)}")
                if embed_texture_in_bbmodel(bbmodel_path, tex_path):
                    fixed_count += 1
                else:
                    missing_count += 1
            else:
                print(f"  MISSING texture: {category}/{entity_name}")
                missing_count += 1
    
    # Also handle derived (they already have textures, just verify)
    derived_dir = os.path.join(MROLF_DIR, "derived")
    if os.path.isdir(derived_dir):
        for bm in os.listdir(derived_dir):
            if bm.endswith('.bbmodel'):
                already_has += 1
    
    print()
    print("=" * 70)
    print(f"  TEXTURE SUMMARY")
    print(f"  Already had texture: {already_has}")
    print(f"  Textures embedded:   {fixed_count}")
    print(f"  Still missing:       {missing_count}")
    print("=" * 70)


if __name__ == "__main__":
    main()
