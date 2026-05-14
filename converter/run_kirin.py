#!/usr/bin/env python3
"""
MinecraftModelMigrator-Pro - Main Runner
=========================================
Converts the Kirin entity from SRParasites mod (MC 1.12.2) to GeckoLib 1.20.1 format.

Supports:
  --blockbench   Also generate Blockbench preview format
  --mode MODE    Output mode: "game" (default), "blockbench", or "both"
  --verify       Run vertex verification after conversion
"""

import os
import sys
import json
import shutil
import argparse

# Add converter directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model_converter import ModelConverter
from animation_converter import KirinAnimationConverter


def main():
    parser = argparse.ArgumentParser(
        description="MinecraftModelMigrator-Pro - MC 1.12.2 → GeckoLib 1.20.1 Converter"
    )
    parser.add_argument(
        "--blockbench",
        action="store_true",
        help="Also generate Blockbench preview format. Equivalent to --mode both"
    )
    parser.add_argument(
        "--mode",
        choices=["game", "blockbench", "both"],
        default="both",
        help="Output mode: 'game' (kirin.geo.json only), "
             "'blockbench' (kirin_bb.geo.json only), "
             "'both' (generate both formats)"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run vertex verification after conversion"
    )
    args = parser.parse_args()

    # --blockbench flag is shorthand for --mode both
    output_mode = args.mode
    if args.blockbench and output_mode == "game":
        output_mode = "both"

    print("=" * 70)
    print("  MinecraftModelMigrator-Pro")
    print("  MC 1.12.2 → GeckoLib 1.20.1 Converter - Kirin Entity")
    print(f"  Output mode: {output_mode}")
    print("=" * 70)
    print()

    # ========================================================================
    # Step 1: Read the decompiled Java source
    # ========================================================================
    model_java_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "decompiled", "com", "dhanantry", "scapeandrunparasites",
        "client", "model", "entity", "derived", "ModelKirin.java"
    )

    print(f"[1/7] Reading ModelKirin.java...")
    with open(model_java_path, 'r') as f:
        model_java = f.read()
    print(f"      Source: {len(model_java)} chars, {model_java.count(chr(10))} lines")

    # ========================================================================
    # Step 2: Convert model to .geo.json
    # ========================================================================
    print("\n[2/7] Converting model to .geo.json...")
    converter = ModelConverter()
    result = converter.convert(model_java, "model.kirin")

    geo_json = result['geo_json']
    bone_mapping = result['bone_mapping']

    bones = geo_json['model']['bones']
    total_cubes = sum(len(b.get('cubes', [])) for b in bones)
    print(f"      Bones converted: {len(bones)}")
    print(f"      Total cubes: {total_cubes}")
    print(f"      Texture size: {geo_json['model']['texture_width']}x{geo_json['model']['texture_height']}")
    if result['warnings']:
        print(f"      Warnings: {len(result['warnings'])}")
        for w in result['warnings'][:5]:
            print(f"        - {w}")

    # ========================================================================
    # Step 3: Save game-format .geo.json
    # ========================================================================
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)

    if output_mode in ("game", "both"):
        geo_json_path = os.path.join(output_dir, "kirin.geo.json")
        print(f"\n[3/7] Saving game-format .geo.json to {geo_json_path}...")
        geo_json_str = json.dumps(geo_json, indent=2, ensure_ascii=False)
        with open(geo_json_path, 'w') as f:
            f.write(geo_json_str)
        print(f"      File size: {len(geo_json_str):,} bytes")
    else:
        print("\n[3/7] Skipping game-format output (mode={output_mode})")

    # ========================================================================
    # Step 4: Save Blockbench preview format .geo.json
    # ========================================================================
    if output_mode in ("blockbench", "both"):
        bb_geo_json_path = os.path.join(output_dir, "kirin_bb.geo.json")
        print(f"\n[4/7] Saving Blockbench preview format to {bb_geo_json_path}...")
        bb_geo_str = converter.to_blockbench_geo_json_string(result)
        with open(bb_geo_json_path, 'w') as f:
            f.write(bb_geo_str)
        print(f"      File size: {len(bb_geo_str):,} bytes")

        # Verify: check bone count in BB format
        bb_data = json.loads(bb_geo_str)
        bb_bone_count = len(bb_data["minecraft:geometry"][0]["bones"])
        print(f"      BB format bone count: {bb_bone_count}")
    else:
        print("\n[4/7] Skipping Blockbench format output (mode={output_mode})")

    # ========================================================================
    # Step 5: Save bone mapping
    # ========================================================================
    mapping_path = os.path.join(output_dir, "kirin_bone_mapping.json")
    print(f"\n[5/7] Saving bone mapping to {mapping_path}...")
    converter.save_bone_mapping(result, mapping_path)
    print(f"      Mapped bones: {len(bone_mapping)}")

    # ========================================================================
    # Step 6: Convert animations
    # ========================================================================
    print(f"\n[6/7] Converting animations...")
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
    # Step 7: Copy texture
    # ========================================================================
    print(f"\n[7/7] Copying texture...")
    src_texture = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "jar_extract", "assets", "srparasites",
        "textures", "entity", "monster", "kirin.png"
    )
    dst_texture = os.path.join(output_dir, "kirin.png")
    shutil.copy2(src_texture, dst_texture)
    print(f"      Texture copied: {dst_texture}")

    # ========================================================================
    # Optional: Run verification
    # ========================================================================
    if args.verify:
        print(f"\n[VERIFY] Running vertex verification...")
        from verifier import ModelVerifier
        verifier = ModelVerifier(tolerance=0.1)
        # Build bone data dict for verification
        bone_data = {'bones': {}}
        for var_name, bone in converter.bones.items():
            bone_data['bones'][var_name] = {
                'pivot_x': bone.pivot_x,
                'pivot_y': bone.pivot_y,
                'pivot_z': bone.pivot_z,
                'rotate_x': bone.rotate_x,
                'rotate_y': bone.rotate_y,
                'rotate_z': bone.rotate_z,
                'boxes': [{'offset_x': b.offset_x, 'offset_y': b.offset_y,
                           'offset_z': b.offset_z, 'width': b.width,
                           'height': b.height, 'depth': b.depth} for b in bone.boxes],
                'parent': bone.parent
            }
        report = verifier.verify(bone_data, geo_json)
        print(f"      Similarity: {report['similarity_score']*100:.2f}%")
        print(f"      Verified: {'PASS' if report['verified'] else 'FAIL'}")

    # ========================================================================
    # Summary
    # ========================================================================
    print("\n" + "=" * 70)
    print("  CONVERSION COMPLETE")
    print("=" * 70)
    print(f"\n  Output mode: {output_mode}")
    print(f"\n  Output files:")
    for f in sorted(os.listdir(output_dir)):
        fpath = os.path.join(output_dir, f)
        size = os.path.getsize(fpath)
        marker = ""
        if f == "kirin_bb.geo.json":
            marker = " [Blockbench Preview]"
        elif f == "kirin.geo.json":
            marker = " [GeckoLib Game]"
        print(f"    📄 {f} ({size:,} bytes){marker}")

    print(f"\n  Model Statistics:")
    print(f"    Total bones: {len(bones)}")
    print(f"    Total cubes: {total_cubes}")
    print(f"    Texture: {geo_json['model']['texture_width']}x{geo_json['model']['texture_height']}")

    # Generate GeckoLib resource location info
    print(f"\n  GeckoLib Resource Locations:")
    print(f"    Model: srparasites:geo/entity/kirin.geo.json")
    print(f"    Texture: srparasites:textures/entity/monster/kirin.png")
    print(f"    Animation: srparasites:animations/entity/kirin.animation.json")

    if output_mode in ("blockbench", "both"):
        print(f"\n  Blockbench Preview:")
        print(f"    File: kirin_bb.geo.json")
        print(f"    Drag this file into Blockbench with GeckoLib plugin")
        print(f"    Then assign kirin.png as texture for UV verification")

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
