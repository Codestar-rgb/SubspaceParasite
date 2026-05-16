#!/usr/bin/env python3
"""
MinecraftModelMigrator-Pro - Heblu (Draconite) Entity Runner
=============================================================
Converts the Heblu/Draconite entity from SRParasites mod (MC 1.12.2) to GeckoLib 1.20.1 format.

Heblu entity specs:
  - Texture: 1024x512 (RGBA)
  - 383 ModelRenderer fields (massive model with wings, hair, mouth, legs, tail)
  - Class A-1: Time-driven animations (ageInTicks dependent)
  - Class A-2: Movement-driven animations (limbSwing - leg walking)
  - Class B:   State-dependent (cosmical/shaking states)
"""

import os
import sys
import json
import shutil
import argparse

# Add converter directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model_converter import ModelConverter
from animation_converter import AnimationConverter
from render_effect_parser import RenderEffectParser
from easing_fitter import EasingFitter
from swing_analyzer import SwingAnalyzer
from animation_layer_separator import AnimationLayerSeparator
from keyframe_event_marker import KeyframeEventMarker
from dynamic_visibility_detector import DynamicVisibilityDetector


def main():
    parser = argparse.ArgumentParser(
        description="MinecraftModelMigrator-Pro - Heblu (Draconite) Converter"
    )
    parser.add_argument(
        "--mode",
        choices=["game", "blockbench", "both"],
        default="game",
        help="Output mode"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run vertex verification after conversion"
    )
    args = parser.parse_args()
    output_mode = args.mode

    print("=" * 70)
    print("  MinecraftModelMigrator-Pro")
    print("  MC 1.12.2 → GeckoLib 1.20.1 - Heblu (Draconite) Entity")
    print(f"  Output mode: {output_mode}")
    print("=" * 70)
    print()

    # ========================================================================
    # Step 1: Read the decompiled Java source
    # ========================================================================
    model_java_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "decompiled", "com", "dhanantry", "scapeandrunparasites",
        "client", "model", "entity", "derived", "ModelHeblu.java"
    )

    print(f"[1/10] Reading ModelHeblu.java...")
    with open(model_java_path, 'r') as f:
        model_java = f.read()
    print(f"      Source: {len(model_java)} chars, {model_java.count(chr(10))} lines")

    # ========================================================================
    # Step 2: Convert model to .geo.json
    # ========================================================================
    print("\n[2/10] Converting model to .geo.json...")
    converter = ModelConverter()
    result = converter.convert(model_java, "model.heblu")

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
        geo_json_path = os.path.join(output_dir, "heblu.geo.json")
        print(f"\n[3/10] Saving game-format .geo.json to {geo_json_path}...")
        geo_json_str = json.dumps(geo_json, indent=2, ensure_ascii=False)
        with open(geo_json_path, 'w') as f:
            f.write(geo_json_str)
        print(f"      File size: {len(geo_json_str):,} bytes")
    else:
        print("\n[3/10] Skipping game-format output")

    # ========================================================================
    # Step 4: Save Blockbench preview format
    # ========================================================================
    if output_mode in ("blockbench", "both"):
        bb_geo_json_path = os.path.join(output_dir, "heblu_bb.geo.json")
        print(f"\n[4/10] Saving Blockbench preview format...")
        bb_geo_str = converter.to_blockbench_geo_json_string(result)
        with open(bb_geo_json_path, 'w') as f:
            f.write(bb_geo_str)
        print(f"      File size: {len(bb_geo_str):,} bytes")
    else:
        print("\n[4/10] Skipping Blockbench format")

    # ========================================================================
    # Step 5: Save bone mapping
    # ========================================================================
    mapping_path = os.path.join(output_dir, "heblu_bone_mapping.json")
    print(f"\n[5/10] Saving bone mapping...")
    converter.save_bone_mapping(result, mapping_path)
    print(f"      Mapped bones: {len(bone_mapping)}")

    # ========================================================================
    # Step 6: Convert animations
    # ========================================================================
    print(f"\n[6/10] Converting animations...")
    anim_converter = AnimationConverter(bone_mapping)
    anim_result = anim_converter.convert_set_rotation_angles(
        model_java,
        animation_name="idle",
        sample_count=120,
        dp_threshold=0.01
    )

    anim_json = anim_result.get('animation_json')
    if anim_json:
        # Set loop to "loop" for idle
        for anim_name in anim_json.get('animations', {}):
            anim_json['animations'][anim_name]['loop'] = 'loop'

        anim_json_path = os.path.join(output_dir, "heblu.animation.json")
        anim_json_str = json.dumps(anim_json, indent=2, ensure_ascii=False)
        with open(anim_json_path, 'w') as f:
            f.write(anim_json_str)
        print(f"      Animation saved: {anim_json_path}")
        for anim_name, anim_data in anim_json.get('animations', {}).items():
            print(f"        {anim_name}: length={anim_data.get('animation_length', 0)}s, "
                  f"bones={len(anim_data.get('bones', {}))}")
    else:
        print("      No time-driven animation generated")

    java_anim_code = anim_result.get('java_code')
    if java_anim_code:
        java_anim_path = os.path.join(output_dir, "heblu_code_animation.java")
        with open(java_anim_path, 'w') as f:
            f.write(java_anim_code)
        print(f"      Movement-driven animation saved: {java_anim_path}")

    anim_class = anim_result.get('anim_class', 'none')
    print(f"      Animation class: {anim_class}")

    if anim_result.get('warnings'):
        print(f"      Warnings: {len(anim_result['warnings'])}")
        for w in anim_result['warnings'][:5]:
            print(f"        - {w}")

    # ========================================================================
    # Step 7: Apply easing fitting
    # ========================================================================
    print(f"\n[7/10] Applying easing fitting...")
    easing_fitter_obj = EasingFitter()
    if anim_json:
        try:
            animation_bones = {}
            for anim_name, anim_data in anim_json.get('animations', {}).items():
                for bone_name, bone_data in anim_data.get('bones', {}).items():
                    rotation = bone_data.get('rotation', {})
                    time_keyframes = {}
                    for axis, axis_data in rotation.items():
                        if isinstance(axis_data, dict):
                            for time_str, value in axis_data.items():
                                numeric_val = value
                                if isinstance(value, dict):
                                    vec = value.get('vector', value.get('value'))
                                    if isinstance(vec, (int, float)):
                                        numeric_val = vec
                                    elif isinstance(vec, list) and vec:
                                        numeric_val = vec[0]
                                    else:
                                        continue
                                if not isinstance(numeric_val, (int, float)):
                                    continue
                                time_key = round(float(time_str), 6)
                                if time_key not in time_keyframes:
                                    time_keyframes[time_key] = {'time': time_key}
                                time_keyframes[time_key][axis] = numeric_val

                    if time_keyframes:
                        keyframes = sorted(time_keyframes.values(), key=lambda k: k['time'])
                        animation_bones[bone_name] = keyframes

            if animation_bones:
                fitting_results = easing_fitter_obj.fit_animation(animation_bones)
                eased_count = sum(
                    1
                    for bone_result in fitting_results.values()
                    for axis_result in bone_result.values()
                    for seg in axis_result.segments
                    if seg.easing_type != "linear"
                )
                easing_types = list(set(
                    seg.easing_type
                    for bone_result in fitting_results.values()
                    for axis_result in bone_result.values()
                    for seg in axis_result.segments
                    if seg.easing_type != "linear"
                ))

                anim_json = easing_fitter_obj.apply_easing_to_animation_json(
                    anim_json, animation_bones
                )
                anim_json_path = os.path.join(output_dir, "heblu.animation.json")
                anim_json_str = json.dumps(anim_json, indent=2, ensure_ascii=False)
                with open(anim_json_path, 'w') as f:
                    f.write(anim_json_str)
                print(f"      Easing applied: {eased_count} segments, types: {', '.join(easing_types) or 'all linear'}")
            else:
                print("      No animation bone data for easing")
        except Exception as e:
            print(f"      Easing fitting error: {e}")
    else:
        print("      No animation data for easing")

    # ========================================================================
    # Step 8: Copy texture
    # ========================================================================
    print(f"\n[8/10] Copying texture...")
    src_texture = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "jar_extract", "assets", "srparasites",
        "textures", "entity", "monster", "heblu.png"
    )
    dst_texture = os.path.join(output_dir, "heblu.png")
    if os.path.exists(src_texture):
        shutil.copy2(src_texture, dst_texture)
        print(f"      Texture copied: {dst_texture}")
    else:
        print(f"      WARNING: Texture not found at {src_texture}")

    # ========================================================================
    # Step 9: Parse render effects
    # ========================================================================
    print(f"\n[9/10] Parsing render effects...")
    render_effect_parser = RenderEffectParser(bone_mapping)
    render_effects = render_effect_parser.parse(model_java, model_java)
    print(f"      Emissive: {render_effects.emissive.detected}")
    print(f"      Translucency: {render_effects.translucency.detected}")
    print(f"      Conditional visibility: {len(render_effects.conditional_visibility)}")

    # ========================================================================
    # Step 10: Generate Java model class
    # ========================================================================
    print(f"\n[10/10] Generating GeckoLib Java model class...")
    _generate_geckolib_java(output_dir, bone_mapping, render_effects)

    # ========================================================================
    # Validation
    # ========================================================================
    print(f"\n[VALIDATE] Validating output files...")
    _validate_output(output_dir, geo_json, anim_json)

    # ========================================================================
    # Summary
    # ========================================================================
    print("\n" + "=" * 70)
    print("  CONVERSION COMPLETE - Heblu (Draconite)")
    print("=" * 70)
    print(f"\n  Output files:")
    for f in sorted(os.listdir(output_dir)):
        if f.startswith("heblu"):
            fpath = os.path.join(output_dir, f)
            size = os.path.getsize(fpath)
            marker = ""
            if f == "heblu.geo.json":
                marker = " [GeckoLib Game]"
            elif f == "heblu.animation.json":
                marker = " [Animation]"
            elif f == "heblu.png":
                marker = " [Texture]"
            elif f == "heblu_bb.geo.json":
                marker = " [Blockbench Preview]"
            print(f"    {f} ({size:,} bytes){marker}")

    print(f"\n  Model Statistics:")
    print(f"    Total bones: {len(bones)}")
    print(f"    Total cubes: {total_cubes}")
    print(f"    Texture: {geo_json['model']['texture_width']}x{geo_json['model']['texture_height']}")

    print(f"\n  GeckoLib Resource Locations:")
    print(f"    Model: srparasites:geo/entity/heblu.geo.json")
    print(f"    Texture: srparasites:textures/entity/monster/heblu.png")
    print(f"    Animation: srparasites:animations/entity/heblu.animation.json")

    return result


def _validate_output(output_dir, geo_json, anim_json):
    """Quick validation of output files."""
    errors = []

    # Validate geo.json
    if geo_json:
        if geo_json.get('format_version') != '1.12.0':
            errors.append(f"geo.json format_version should be 1.12.0, got {geo_json.get('format_version')}")
        if not geo_json.get('model', {}).get('bones'):
            errors.append("geo.json has no bones")

        # UV bounds check
        tex_w = geo_json['model'].get('texture_width', 0)
        tex_h = geo_json['model'].get('texture_height', 0)
        uv_oob = 0
        all_bone_names = set()
        for bone in geo_json['model']['bones']:
            all_bone_names.add(bone.get('name', ''))
            for cube in bone.get('cubes', []):
                for face, uv_data in cube.get('uv', {}).items():
                    u, v = uv_data.get('uv', [0, 0])
                    us, vs = uv_data.get('uv_size', [0, 0])
                    if u + us > tex_w or v + vs > tex_h or u < 0 or v < 0:
                        uv_oob += 1
        if uv_oob > 0:
            errors.append(f"{uv_oob} UV out-of-bounds violations")
        else:
            print(f"      UV bounds: OK (within {tex_w}x{tex_h})")

        # Parent check
        for bone in geo_json['model']['bones']:
            parent = bone.get('parent')
            if parent and parent not in all_bone_names:
                errors.append(f"Bone {bone.get('name', '')}: parent '{parent}' not found")

        print(f"      Bones: {len(geo_json['model']['bones'])}")
        print(f"      Format: {geo_json.get('format_version')}")

    # Validate anim.json
    if anim_json:
        if anim_json.get('format_version') != '1.8.0':
            errors.append(f"anim.json format_version should be 1.8.0, got {anim_json.get('format_version')}")
        for anim_name, anim_data in anim_json.get('animations', {}).items():
            anim_bones = anim_data.get('bones', {})
            print(f"      Animation '{anim_name}': {len(anim_bones)} bones, "
                  f"length={anim_data.get('animation_length', 0)}s")
            # Check animation bones exist in geo.json
            for bone_name in anim_bones:
                if geo_json and bone_name not in all_bone_names:
                    errors.append(f"Animation bone '{bone_name}' not in geo.json")

    if errors:
        print(f"      ERRORS: {len(errors)}")
        for e in errors[:10]:
            print(f"        - {e}")
    else:
        print("      ALL VALID ✓")


def _generate_geckolib_java(output_dir, bone_mapping, render_effects):
    """Generate a GeckoLib Java class for the Heblu entity."""

    render_type_code = ""
    if render_effects and (render_effects.emissive.detected or render_effects.translucency.detected):
        render_type_code = (
            "\n    @Override\n"
            "    public RenderType getRenderType(HebluEntity animatable, ResourceLocation texture) {\n"
        )
        if render_effects.emissive.detected and render_effects.emissive.is_global:
            render_type_code += "        return RenderType.eyes(texture);\n"
        elif render_effects.translucency.detected and render_effects.translucency.is_global:
            render_type_code += "        return RenderType.entityTranslucent(texture);\n"
        else:
            render_type_code += "        return super.getRenderType(animatable, texture);\n"
        render_type_code += "    }\n"

    java_code = (
        "package com.example.srparasites.client.model;\n"
        "\n"
        "import net.minecraft.resources.ResourceLocation;\n"
        "import net.minecraft.client.renderer.RenderType;\n"
        "import software.bernie.geckolib.model.GeoModel;\n"
        "import com.example.srparasites.entity.HebluEntity;\n"
        "\n"
        "public class HebluGeoModel extends GeoModel<HebluEntity> {\n"
        f"{render_type_code}"
        "    @Override\n"
        "    public ResourceLocation getModelResource(HebluEntity animatable) {\n"
        '        return new ResourceLocation("srparasites", "geo/entity/heblu.geo.json");\n'
        "    }\n"
        "\n"
        "    @Override\n"
        "    public ResourceLocation getTextureResource(HebluEntity animatable) {\n"
        '        return new ResourceLocation("srparasites", "textures/entity/monster/heblu.png");\n'
        "    }\n"
        "\n"
        "    @Override\n"
        "    public ResourceLocation getAnimationResource(HebluEntity animatable) {\n"
        '        return new ResourceLocation("srparasites", "animations/entity/heblu.animation.json");\n'
        "    }\n"
        "}\n"
    )
    java_path = os.path.join(output_dir, "HebluGeoModel.java")
    with open(java_path, 'w') as f:
        f.write(java_code)
    print(f"      Generated: {java_path}")


if __name__ == "__main__":
    main()
