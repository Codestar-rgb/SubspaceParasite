#!/usr/bin/env python3
"""
MC1122 to GeckoLib Converter - Main Runner
============================================
Processes the Kirin entity from SRParasites mod.
"""

import os
import sys
import json
import shutil

# Add converter directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model_converter import ModelConverter
from animation_converter import KirinAnimationConverter


def main():
    print("=" * 70)
    print("  MC 1.12.2 → GeckoLib 1.20.1 Converter - Kirin Entity")
    print("=" * 70)
    print()

    # ========================================================================
    # Step 1: Read the decompiled Java source
    # ========================================================================
    model_java_path = "/home/z/my-project/decompiled/com/dhanantry/scapeandrunparasites/client/model/entity/derived/ModelKirin.java"

    print(f"[1/6] Reading ModelKirin.java...")
    with open(model_java_path, 'r') as f:
        model_java = f.read()
    print(f"      Source: {len(model_java)} chars, {model_java.count(chr(10))} lines")

    # ========================================================================
    # Step 2: Convert model to .geo.json
    # ========================================================================
    print("\n[2/6] Converting model to .geo.json...")
    converter = ModelConverter()
    result = converter.convert(model_java, "model.kirin")

    geo_json = result['geo_json']
    bone_mapping = result['bone_mapping']

    print(f"      Bones converted: {len(geo_json['model']['bones'])}")
    print(f"      Texture size: {geo_json['model']['texture_width']}x{geo_json['model']['texture_height']}")
    if result['warnings']:
        print(f"      Warnings: {len(result['warnings'])}")
        for w in result['warnings'][:5]:
            print(f"        - {w}")

    # ========================================================================
    # Step 3: Save .geo.json
    # ========================================================================
    output_dir = "/home/z/my-project/converter/output"
    os.makedirs(output_dir, exist_ok=True)

    geo_json_path = os.path.join(output_dir, "kirin.geo.json")
    print(f"\n[3/6] Saving .geo.json to {geo_json_path}...")
    geo_json_str = json.dumps(geo_json, indent=2, ensure_ascii=False)
    with open(geo_json_path, 'w') as f:
        f.write(geo_json_str)
    print(f"      File size: {len(geo_json_str)} bytes")

    # ========================================================================
    # Step 4: Save bone mapping
    # ========================================================================
    mapping_path = os.path.join(output_dir, "kirin_bone_mapping.json")
    print(f"\n[4/6] Saving bone mapping to {mapping_path}...")
    converter.save_bone_mapping(result, mapping_path)
    print(f"      Mapped bones: {len(bone_mapping)}")

    # Print bone mapping for reference
    print("\n      Bone Mapping Table:")
    print("      " + "-" * 50)
    for java_var, bone_name in sorted(bone_mapping.items()):
        print(f"      {java_var:25s} → {bone_name}")

    # ========================================================================
    # Step 5: Convert animations
    # ========================================================================
    print(f"\n[5/6] Converting animations...")
    anim_converter = KirinAnimationConverter(bone_mapping)
    anim_result = anim_converter.convert_kirin_idle(model_java)

    if anim_result['animation_json']:
        anim_json_path = os.path.join(output_dir, "kirin.animation.json")
        anim_json_str = json.dumps(anim_result['animation_json'], indent=2, ensure_ascii=False)
        with open(anim_json_path, 'w') as f:
            f.write(anim_json_str)
        print(f"      Idle animation saved: {anim_json_path}")
        print(f"      Animation length: {anim_result['animation_json']['animations']['animation.model.idle']['animation_length']}s")
        bones_with_anim = len(anim_result['animation_json']['animations']['animation.model.idle']['bones'])
        print(f"      Bones with animation: {bones_with_anim}")
    else:
        print("      No animation generated")

    if anim_result.get('java_code'):
        java_anim_path = os.path.join(output_dir, "kirin_code_animation.java")
        with open(java_anim_path, 'w') as f:
            f.write(anim_result['java_code'])
        print(f"      Java code animation saved: {java_anim_path}")

    if anim_result['warnings']:
        print(f"      Animation warnings: {len(anim_result['warnings'])}")
        for w in anim_result['warnings'][:5]:
            print(f"        - {w}")

    # ========================================================================
    # Step 6: Copy texture
    # ========================================================================
    print(f"\n[6/6] Copying texture...")
    src_texture = "/home/z/my-project/jar_extract/assets/srparasites/textures/entity/monster/kirin.png"
    dst_texture = os.path.join(output_dir, "kirin.png")
    shutil.copy2(src_texture, dst_texture)
    print(f"      Texture copied: {dst_texture}")

    # ========================================================================
    # Summary
    # ========================================================================
    print("\n" + "=" * 70)
    print("  CONVERSION COMPLETE")
    print("=" * 70)
    print(f"\n  Output files:")
    for f in os.listdir(output_dir):
        fpath = os.path.join(output_dir, f)
        size = os.path.getsize(fpath)
        print(f"    📄 {f} ({size:,} bytes)")

    print(f"\n  Model Statistics:")
    print(f"    Total bones: {len(geo_json['model']['bones'])}")
    total_cubes = sum(
        len(bone.get('cubes', []))
        for bone in geo_json['model']['bones']
    )
    print(f"    Total cubes: {total_cubes}")
    print(f"    Texture: {geo_json['model']['texture_width']}x{geo_json['model']['texture_height']}")

    # Generate GeckoLib resource location info
    print(f"\n  GeckoLib Resource Locations:")
    print(f"    Model: srparasites:geo/entity/kirin.geo.json")
    print(f"    Texture: srparasites:textures/entity/monster/kirin.png")
    print(f"    Animation: srparasites:animations/entity/kirin.animation.json")

    # Generate example Java class for 1.20.1
    _generate_geckolib_java(output_dir, bone_mapping)

    return result


def _generate_geckolib_java(output_dir: str, bone_mapping: dict):
    """Generate a skeleton GeckoLib Java class for the Kirin entity."""
    java_code = '''package com.example.srparasites.client.model;

import net.minecraft.resources.ResourceLocation;
import software.bernie.geckolib.model.GeoModel;
import com.example.srparasites.entity.KirinEntity;

public class KirinGeoModel extends GeoModel<KirinEntity> {

    @Override
    public ResourceLocation getModelResource(KirinEntity animatable) {
        return new ResourceLocation("srparasites", "geo/entity/kirin.geo.json");
    }

    @Override
    public ResourceLocation getTextureResource(KirinEntity animatable) {
        return new ResourceLocation("srparasites", "textures/entity/monster/kirin.png");
    }

    @Override
    public ResourceLocation getAnimationResource(KirinEntity animatable) {
        return new ResourceLocation("srparasites", "animations/entity/kirin.animation.json");
    }

    // For Class A-2 movement-driven animations, override codeAnimations:
    // @Override
    // public void codeAnimations(KirinEntity animatable, AnimatableManager<KirinEntity> manager) {
    //     // Insert movement-driven animation code here
    // }
}
'''
    java_path = os.path.join(output_dir, "KirinGeoModel.java")
    with open(java_path, 'w') as f:
        f.write(java_code)
    print(f"    Generated: {java_path}")


if __name__ == "__main__":
    result = main()
