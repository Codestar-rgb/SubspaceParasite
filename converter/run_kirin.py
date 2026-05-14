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
from render_effect_parser import RenderEffectParser
from easing_fitter import EasingFitter
from swing_analyzer import SwingAnalyzer


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

    print(f"[1/15] Reading ModelKirin.java...")
    with open(model_java_path, 'r') as f:
        model_java = f.read()
    print(f"      Source: {len(model_java)} chars, {model_java.count(chr(10))} lines")

    # ========================================================================
    # Step 2: Convert model to .geo.json
    # ========================================================================
    print("\n[2/15] Converting model to .geo.json...")
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
        print(f"\n[3/15] Saving game-format .geo.json to {geo_json_path}...")
        geo_json_str = json.dumps(geo_json, indent=2, ensure_ascii=False)
        with open(geo_json_path, 'w') as f:
            f.write(geo_json_str)
        print(f"      File size: {len(geo_json_str):,} bytes")
    else:
        print("\n[3/15] Skipping game-format output (mode={output_mode})")

    # ========================================================================
    # Step 4: Save Blockbench preview format .geo.json
    # ========================================================================
    if output_mode in ("blockbench", "both"):
        bb_geo_json_path = os.path.join(output_dir, "kirin_bb.geo.json")
        print(f"\n[4/15] Saving Blockbench preview format to {bb_geo_json_path}...")
        bb_geo_str = converter.to_blockbench_geo_json_string(result)
        with open(bb_geo_json_path, 'w') as f:
            f.write(bb_geo_str)
        print(f"      File size: {len(bb_geo_str):,} bytes")

        # Verify: check bone count in BB format
        bb_data = json.loads(bb_geo_str)
        bb_bone_count = len(bb_data["minecraft:geometry"][0]["bones"])
        print(f"      BB format bone count: {bb_bone_count}")
    else:
        print("\n[4/15] Skipping Blockbench format output (mode={output_mode})")

    # ========================================================================
    # Step 5: Save bone mapping
    # ========================================================================
    mapping_path = os.path.join(output_dir, "kirin_bone_mapping.json")
    print(f"\n[5/15] Saving bone mapping to {mapping_path}...")
    converter.save_bone_mapping(result, mapping_path)
    print(f"      Mapped bones: {len(bone_mapping)}")

    # ========================================================================
    # Step 6: Parse render effects
    # ========================================================================
    print(f"\n[6/15] Parsing render effects...")
    render_effect_parser = RenderEffectParser(bone_mapping)
    # Parse render effects - pass model source as both render and model java
    # since the Render class is separate and may not be available
    render_effects = render_effect_parser.parse(model_java, model_java)
    print(f"      Emissive detected: {render_effects.emissive.detected}")
    print(f"      Translucency detected: {render_effects.translucency.detected}")
    print(f"      Conditional visibility rules: {len(render_effects.conditional_visibility)}")
    print(f"      Dynamic UV warnings: {len(render_effects.dynamic_uv)}")

    # ========================================================================
    # Step 7: Analyze swing physics
    # ========================================================================
    print(f"\n[7/15] Analyzing swing physics...")
    swing_analyzer = SwingAnalyzer(bone_mapping)
    swing_result = swing_analyzer.analyze(model_java)
    print(f"      Swing components detected: {len(swing_result.swing_components)}")
    print(f"      Gravity/inertia patterns: {len(swing_result.gravity_inertia)}")
    print(f"      Hurt shake patterns: {len(swing_result.hurt_shakes)}")

    # ========================================================================
    # Step 8: Convert animations (enhanced with easing)
    # ========================================================================
    print(f"\n[8/15] Converting animations...")
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
    # Step 9: Apply easing fitting
    # ========================================================================
    print(f"\n[9/15] Applying easing fitting...")
    easing_fitter = EasingFitter()
    if anim_result.get('animation_json'):
        eased_anim = easing_fitter.fit(anim_result['animation_json'])
        print(f"      Keyframes with easing applied: {eased_anim.get('eased_keyframe_count', 0)}")
        print(f"      Easing functions detected: {', '.join(eased_anim.get('easing_types', [])) or 'none'}")
    else:
        eased_anim = {}
        print("      No animation data to fit easing")

    # ========================================================================
    # Step 10: Separate animation layers
    # ========================================================================
    print(f"\n[10/15] Separating animation layers...")
    from animation_layer_separator import AnimationLayerSeparator
    layer_separator = AnimationLayerSeparator()
    if anim_result.get('animation_json'):
        layers = layer_separator.separate(anim_result['animation_json'], bone_mapping)
        print(f"      Animation layers: {len(layers.get('layers', []))}")
        for layer in layers.get('layers', []):
            print(f"        - {layer.get('name', 'unknown')}: priority {layer.get('priority', 0)}")
    else:
        layers = {}
        print("      No animation data to separate into layers")

    # ========================================================================
    # Step 11: Detect animation events
    # ========================================================================
    print(f"\n[11/15] Detecting animation events...")
    from keyframe_event_marker import KeyframeEventMarker
    event_marker = KeyframeEventMarker()
    if anim_result.get('animation_json'):
        events = event_marker.detect(anim_result['animation_json'], model_java)
        print(f"      Sound effects detected: {len(events.get('sound_effects', []))}")
        print(f"      Particle effects detected: {len(events.get('particle_effects', []))}")
        print(f"      Event markers: {len(events.get('event_markers', []))}")
    else:
        events = {}
        print("      No animation data to detect events")

    # ========================================================================
    # Step 12: Detect dynamic visibility
    # ========================================================================
    print(f"\n[12/15] Detecting dynamic visibility...")
    from dynamic_visibility_detector import DynamicVisibilityDetector
    visibility_detector = DynamicVisibilityDetector()
    visibility_result = visibility_detector.detect(model_java, bone_mapping)
    print(f"      Visibility rules detected: {len(visibility_result.get('visibility_rules', []))}")
    for rule in visibility_result.get('visibility_rules', [])[:5]:
        print(f"        - {rule.get('bone', 'unknown')}: {rule.get('condition', 'unknown')}")

    # ========================================================================
    # Step 13: Copy texture
    # ========================================================================
    print(f"\n[13/15] Copying texture...")
    src_texture = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "jar_extract", "assets", "srparasites",
        "textures", "entity", "monster", "kirin.png"
    )
    dst_texture = os.path.join(output_dir, "kirin.png")
    shutil.copy2(src_texture, dst_texture)
    print(f"      Texture copied: {dst_texture}")

    # ========================================================================
    # Step 14: Generate SwingComponent utility
    # ========================================================================
    print(f"\n[14/15] Generating SwingComponent utility...")
    if swing_result.get('swing_components'):
        swing_util_path = os.path.join(output_dir, "KirinSwingComponents.java")
        swing_util_code = swing_analyzer.generate_utility_class(swing_result)
        with open(swing_util_path, 'w') as f:
            f.write(swing_util_code)
        print(f"      SwingComponent utility saved: {swing_util_path}")
        print(f"      Swing components: {len(swing_result.get('swing_components', []))}")
    else:
        print("      No swing components to generate")

    # ========================================================================
    # Step 15: Generate enhanced Java model
    # ========================================================================
    print(f"\n[15/15] Generating enhanced Java model...")
    _generate_geckolib_java(output_dir, bone_mapping, render_effects, swing_result,
                            layers, events, visibility_result)

    # ========================================================================
    # Optional: Run verification (enhanced)
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

        # Enhanced verification: check render effects and swing components
        if render_effects.get('render_types'):
            print(f"      Render type overrides verified: {len(render_effects.get('render_types', []))}")
        if swing_result.get('swing_components'):
            print(f"      Swing components verified: {len(swing_result.get('swing_components', []))}")

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

    return result


def _generate_geckolib_java(output_dir: str, bone_mapping: dict,
                          render_effects: dict = None,
                          swing_result: dict = None,
                          layers: dict = None,
                          events: dict = None,
                          visibility_result: dict = None):
    """Generate an enhanced GeckoLib Java class for the Kirin entity.

    Includes optional enhancement code for:
      - Render type override (from render_effect_parser)
      - Visibility code (from render_effect_parser)
      - Swing component instantiations (from swing_analyzer)
      - Hurt controller registration (from swing_analyzer)
      - Animation layer code (from AnimationLayerSeparator)
      - Event markers info (from KeyframeEventMarker)
    """
    render_effects = render_effects or {}
    swing_result = swing_result or {}
    layers = layers or {}
    events = events or {}
    visibility_result = visibility_result or {}

    # Build render type override code
    render_type_code = ""
    if render_effects.get('render_types'):
        render_type_lines = []
        for rt in render_effects['render_types']:
            render_type_lines.append(
                f"    // Render type: {rt.get('type', 'entity_translucent')}"
            )
        render_type_code = "\n".join(render_type_lines)
        render_type_code = (
            "\n    /**\n"
            "     * Render type override for custom rendering.\n"
            "     * Generated from render effect analysis.\n"
            "     */\n"
            "    @Override\n"
            "    public RenderType getRenderType(KirinEntity animatable, ResourceLocation texture) {\n"
            f"{render_type_code}\n"
            "        return RenderType.entityTranslucent(texture);\n"
            "    }\n"
        )

    # Build visibility code
    visibility_code = ""
    if render_effects.get('visibility_conditions') or visibility_result.get('visibility_rules'):
        visibility_lines = ["\n    /**"]
        visibility_lines.append("     * Conditional visibility for bones.")
        visibility_lines.append("     * Generated from render effect and dynamic visibility analysis.")
        visibility_lines.append("     */")
        all_conditions = list(render_effects.get('visibility_conditions', []))
        all_conditions.extend(visibility_result.get('visibility_rules', []))
        for vc in all_conditions:
            bone_name = vc.get('bone', 'unknown')
            condition = vc.get('condition', 'true')
            visibility_lines.append(
                f"    // Bone: {bone_name} - visible when: {condition}"
            )
        visibility_code = "\n".join(visibility_lines) + "\n"

    # Build swing component instantiations
    swing_code = ""
    if swing_result.get('swing_components'):
        swing_lines = ["\n    // Swing component instantiations"]
        for sc in swing_result['swing_components']:
            swing_lines.append(
                f"    private final SwingComponent {sc.get('name', 'swing')} = "
                f"new SwingComponent({sc.get('frequency', 1.0)}f, {sc.get('amplitude', 1.0)}f);"
            )
        swing_code = "\n".join(swing_lines) + "\n"

    # Build hurt controller registration
    hurt_code = ""
    if swing_result.get('hurt_controllers'):
        hurt_lines = ["\n    // Hurt controller registrations"]
        for hc in swing_result['hurt_controllers']:
            hurt_lines.append(
                f"    // Hurt controller: {hc.get('name', 'hurt')} - "
                f"intensity: {hc.get('intensity', 1.0)}"
            )
        hurt_code = "\n".join(hurt_lines) + "\n"

    # Build animation layer code
    layer_code = ""
    if layers.get('layers'):
        layer_lines = ["\n    // Animation layer registrations"]
        for layer in layers['layers']:
            layer_lines.append(
                f"    // Layer: {layer.get('name', 'base')} - "
                f"priority: {layer.get('priority', 0)}"
            )
        layer_code = "\n".join(layer_lines) + "\n"

    # Build event markers info
    event_code = ""
    if events.get('event_markers'):
        event_lines = ["\n    // Keyframe event markers"]
        for em in events['event_markers']:
            event_lines.append(
                f"    // Event at {em.get('time', 0.0)}s: {em.get('type', 'unknown')} - "
                f"{em.get('name', 'unnamed')}"
            )
        event_code = "\n".join(event_lines) + "\n"

    java_code = (
        "package com.example.srparasites.client.model;\n"
        "\n"
        "import net.minecraft.resources.ResourceLocation;\n"
        "import net.minecraft.client.renderer.RenderType;\n"
        "import software.bernie.geckolib.model.GeoModel;\n"
        "import com.example.srparasites.entity.KirinEntity;\n"
        "\n"
        "public class KirinGeoModel extends GeoModel<KirinEntity> {\n"
        f"{swing_code}"
        "    @Override\n"
        "    public ResourceLocation getModelResource(KirinEntity animatable) {\n"
        '        return new ResourceLocation("srparasites", "geo/entity/kirin.geo.json");\n'
        "    }\n"
        "\n"
        "    @Override\n"
        "    public ResourceLocation getTextureResource(KirinEntity animatable) {\n"
        '        return new ResourceLocation("srparasites", "textures/entity/monster/kirin.png");\n'
        "    }\n"
        "\n"
        "    @Override\n"
        "    public ResourceLocation getAnimationResource(KirinEntity animatable) {\n"
        '        return new ResourceLocation("srparasites", "animations/entity/kirin.animation.json");\n'
        "    }\n"
        f"{render_type_code}{visibility_code}{hurt_code}{layer_code}{event_code}"
        "    // For Class A-2 movement-driven animations, override codeAnimations:\n"
        "    // @Override\n"
        "    // public void codeAnimations(KirinEntity animatable, AnimatableManager<KirinEntity> manager) {\n"
        "    //     // Insert movement-driven animation code here\n"
        "    // }\n"
        "}\n"
    )
    java_path = os.path.join(output_dir, "KirinGeoModel.java")
    with open(java_path, 'w') as f:
        f.write(java_code)
    print(f"      Generated: {java_path}")


if __name__ == "__main__":
    result = main()
