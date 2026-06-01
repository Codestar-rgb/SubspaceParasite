#!/usr/bin/env python3
"""
MinecraftModelMigrator-Pro - Main Runner (Layer 1 Enhanced)
============================================================
Converts the Kirin entity from SRParasites mod (MC 1.12.2) to GeckoLib 1.20.1 format.

Layer 1 Enhancement Pipeline:
  Steps 1-5:  Core conversion (model, blockbench, bone mapping)
  Step 6:     Render effect parsing (emissive, translucency, visibility, dynamic UV)
  Step 7:     Swing physics analysis (tail/ear swing, gravity/inertia, hurt shake)
  Step 8:     Animation conversion (Class A-1 time-driven, Class A-2 movement-driven)
  Step 9:     Easing fitting (least-squares to GeckoLib easing types)
  Step 10:    Animation layer separation (base, overlay, additive layers)
  Step 11:    Keyframe event detection (sound, particle, attack events)
  Step 12:    Dynamic visibility detection (showModel, isInvisible, isChild)
  Steps 13-15: Output generation (texture, swing utility, Java model)

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
from animation_layer_separator import AnimationLayerSeparator
from keyframe_event_marker import KeyframeEventMarker
from dynamic_visibility_detector import DynamicVisibilityDetector

# Layer 1 Deep Enhancements
from enhancements.layer1_deep.overlay_detector import OverlayDetector
from enhancements.layer1_deep.firstperson_detector import FirstPersonDetector
from enhancements.layer1_deep.particle_detector import ParticleDetector
from enhancements.layer1_deep.sound_keyframe_filler import SoundKeyframeFiller
from enhancements.layer1_deep.animation_naming_manager import AnimationNamingManager
from enhancements.layer1_deep.animation_reference_validator import AnimationReferenceValidator


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
    parser.add_argument(
        "--animation-naming-config",
        type=str,
        default=None,
        help="Path to custom animation_naming.json config file"
    )
    args = parser.parse_args()

    # --blockbench flag is shorthand for --mode both
    output_mode = args.mode
    if args.blockbench and output_mode == "game":
        output_mode = "both"

    print("=" * 70)
    print("  MinecraftModelMigrator-Pro (Layer 1 Enhanced)")
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
    render_effects = render_effect_parser.parse(model_java, model_java)
    print(f"      Emissive detected: {render_effects.emissive.detected}")
    print(f"      Translucency detected: {render_effects.translucency.detected}")
    print(f"      Conditional visibility rules: {len(render_effects.conditional_visibility)}")
    print(f"      Dynamic UV warnings: {len(render_effects.dynamic_uv)}")
    if render_effects.render_order:
        print(f"      Render order entries: {len(render_effects.render_order)}")

    # ========================================================================
    # Step 7: Analyze swing physics
    # ========================================================================
    print(f"\n[7/15] Analyzing swing physics...")
    swing_analyzer = SwingAnalyzer(bone_mapping)
    swing_result = swing_analyzer.analyze(model_java)
    print(f"      Swing components detected: {len(swing_result.swing_components)}")
    print(f"      Gravity/inertia patterns: {len(swing_result.gravity_inertia)}")
    print(f"      Hurt shake patterns: {len(swing_result.hurt_shakes)}")
    if swing_result.warnings:
        for w in swing_result.warnings[:3]:
            print(f"        Warning: {w}")

    # ========================================================================
    # Step 8: Convert animations (enhanced with easing)
    # ========================================================================
    print(f"\n[8/15] Converting animations...")
    anim_converter = KirinAnimationConverter(bone_mapping)
    anim_result = anim_converter.convert_kirin_idle(model_java)

    anim_json = anim_result.get('animation_json')
    if anim_json:
        anim_json_path = os.path.join(output_dir, "kirin.animation.json")
        anim_json_str = json.dumps(anim_json, indent=2, ensure_ascii=False)
        with open(anim_json_path, 'w') as f:
            f.write(anim_json_str)
        print(f"      Idle animation saved: {anim_json_path}")
        idle_data = anim_json['animations'].get('animation.model.idle', {})
        print(f"      Animation length: {idle_data.get('animation_length', 0)}s")
        bones_with_anim = len(idle_data.get('bones', {}))
        print(f"      Bones with animation: {bones_with_anim}")
    else:
        print("      No animation generated")

    if anim_result.get('java_code'):
        java_anim_path = os.path.join(output_dir, "kirin_code_animation.java")
        with open(java_anim_path, 'w') as f:
            f.write(anim_result['java_code'])
        print(f"      Java code animation saved: {java_anim_path}")

    if anim_result.get('warnings'):
        print(f"      Animation warnings: {len(anim_result['warnings'])}")
        for w in anim_result['warnings'][:5]:
            print(f"        - {w}")

    # ========================================================================
    # Step 9: Apply easing fitting
    # ========================================================================
    print(f"\n[9/15] Applying easing fitting...")
    easing_fitter_obj = EasingFitter()
    easing_result = {}
    if anim_json:
        try:
            # Prepare animation bones data for easing fitting
            # Uses dict for O(1) time-key lookup instead of O(n) list search
            animation_bones = {}
            idle_data = anim_json['animations'].get('animation.model.idle', {})
            for bone_name, bone_data in idle_data.get('bones', {}).items():
                rotation = bone_data.get('rotation', {})
                # Dict: time_key (rounded) -> keyframe dict
                time_keyframes = {}
                for axis, axis_data in rotation.items():
                    if isinstance(axis_data, dict):
                        for time_str, value in axis_data.items():
                            # Extract numeric value from potential dict format
                            numeric_val = value
                            if isinstance(value, dict):
                                vec = value.get('vector', value.get('value'))
                                if isinstance(vec, (int, float)):
                                    numeric_val = vec
                                elif isinstance(vec, list) and vec:
                                    numeric_val = vec[0]
                                else:
                                    continue  # Skip unparseable values
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
                total_segments = sum(
                    len(axis_result.segments)
                    for bone_result in fitting_results.values()
                    for axis_result in bone_result.values()
                )
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

                # Apply easing to the animation JSON (modifies in place)
                anim_json = easing_fitter_obj.apply_easing_to_animation_json(
                    anim_json, animation_bones
                )

                # Re-save the animation JSON with easing applied
                anim_json_path = os.path.join(output_dir, "kirin.animation.json")
                anim_json_str = json.dumps(anim_json, indent=2, ensure_ascii=False)
                with open(anim_json_path, 'w') as f:
                    f.write(anim_json_str)
                print(f"      Animation JSON updated with easing: {anim_json_path}")

                easing_result = {
                    'eased_keyframe_count': eased_count,
                    'easing_types': easing_types,
                    'total_segments': total_segments,
                    'fitting_results': fitting_results
                }
                print(f"      Keyframes with easing applied: {eased_count}")
                print(f"      Easing functions detected: {', '.join(easing_types) or 'none (all linear)'}")
                print(f"      Total segments analyzed: {total_segments}")
            else:
                print("      No animation bone data for easing fitting")
        except Exception as e:
            print(f"      Easing fitting error: {e}")
    else:
        print("      No animation data to fit easing")

    # ========================================================================
    # Step 10: Separate animation layers
    # ========================================================================
    print(f"\n[10/15] Separating animation layers...")
    layer_separator = AnimationLayerSeparator(bone_mapping)
    layers_result = None
    if anim_json:
        layers_result = layer_separator.separate(anim_json, bone_mapping)
        print(f"      Animation layers: {len(layers_result.layers)}")
        for layer in layers_result.layers:
            print(f"        - {layer.name}: type={layer.layer_type}, priority={layer.priority}, bones={len(layer.bone_names)}")
        if layers_result.warnings:
            for w in layers_result.warnings[:3]:
                print(f"        Warning: {w}")
    else:
        print("      No animation data to separate into layers")

    # ========================================================================
    # Step 11: Detect animation events
    # ========================================================================
    print(f"\n[11/15] Detecting animation events...")
    event_marker = KeyframeEventMarker(bone_mapping)
    events_result = None
    if anim_json:
        events_result = event_marker.detect(anim_json, model_java)
        print(f"      Sound effects detected: {len(events_result.sound_effects)}")
        print(f"      Particle effects detected: {len(events_result.particle_effects)}")
        print(f"      Event markers: {len(events_result.event_markers)}")
    else:
        print("      No animation data to detect events")

    # ========================================================================
    # Step 12: Detect dynamic visibility
    # ========================================================================
    print(f"\n[12/15] Detecting dynamic visibility...")
    visibility_detector = DynamicVisibilityDetector(bone_mapping)
    visibility_result = visibility_detector.detect(model_java, bone_mapping)
    print(f"      Visibility rules detected: {len(visibility_result.visibility_rules)}")
    for rule in visibility_result.visibility_rules[:5]:
        print(f"        - {rule.bone_name}: {rule.condition} ({rule.condition_type})")
    if visibility_result.warnings:
        for w in visibility_result.warnings[:3]:
            print(f"        Warning: {w}")

    # ========================================================================
    # Step 13: Overlay detection (Layer 1 Deep Enhancement #1)
    # ========================================================================
    print(f"\n[13/21] Detecting multi-layer texture overlays...")
    overlay_detector = OverlayDetector(bone_mapping)
    overlay_result = overlay_detector.detect(model_java, model_java)
    print(f"      Overlay layers detected: {len(overlay_result.overlay_layers)}")
    print(f"      Has overlay: {overlay_result.has_overlay}")
    for layer in overlay_result.overlay_layers:
        print(f"        - {layer.name}: type={layer.layer_type}, trigger={layer.trigger_condition}")
    if overlay_result.merge_hints:
        print(f"      Merge hints: {len(overlay_result.merge_hints)}")
        for hint in overlay_result.merge_hints[:3]:
            print(f"        - [{hint.priority}] {hint.description[:80]}")

    # ========================================================================
    # Step 14: First-person handheld detection (Layer 1 Deep Enhancement #2)
    # ========================================================================
    print(f"\n[14/21] Detecting first-person handheld transforms...")
    firstperson_detector = FirstPersonDetector(bone_mapping)
    firstperson_result = firstperson_detector.detect(model_java, model_java)
    print(f"      Has held item: {firstperson_result.has_held_item}")
    print(f"      Held item bones: {len(firstperson_result.held_item_bones)}")
    for hb in firstperson_result.held_item_bones:
        print(f"        - {hb.bone_name}: {hb.item_type}")
    if firstperson_result.first_person_hints:
        print(f"      First-person hints: {len(firstperson_result.first_person_hints)}")

    # ========================================================================
    # Step 15: Particle mounting point detection (Layer 1 Deep Enhancement #3)
    # ========================================================================
    print(f"\n[15/21] Detecting particle mounting points...")
    particle_detector = ParticleDetector(bone_mapping)
    particle_result = particle_detector.detect(model_java, model_java)
    print(f"      Particle mount points: {len(particle_result.mount_points)}")
    print(f"      Has particles: {particle_result.has_particles}")
    for mp in particle_result.mount_points[:5]:
        print(f"        - {mp.name}: type={mp.particle_type}, bone={mp.bone_name}")

    # ========================================================================
    # Step 16: Sound keyframe auto-fill (Layer 1 Deep Enhancement #4)
    # ========================================================================
    print(f"\n[16/21] Auto-filling sound keyframes...")
    anim_length = 6.28
    if anim_json:
        for anim_name, anim_data in anim_json.get('animations', {}).items():
            anim_length = anim_data.get('animation_length', 6.28)
            break
    sound_filler = SoundKeyframeFiller(bone_mapping)
    sound_result = sound_filler.detect(model_java, model_java, "", anim_length)
    print(f"      Sound keyframes: {len(sound_result.sound_keyframes)}")
    print(f"      Has sounds: {sound_result.has_sounds}")
    for kf in sound_result.sound_keyframes[:5]:
        print(f"        - t={kf.time:.2f}s: {kf.effect} (from {kf.original_sound})")

    # ========================================================================
    # Step 17: Animation naming management (Layer 1 Deep Enhancement #6)
    # ========================================================================
    print(f"\n[17/21] Managing animation naming...")
    naming_config_path = args.animation_naming_config
    if not naming_config_path:
        default_config = os.path.join(output_dir, "animation_naming.json")
        if os.path.exists(default_config):
            naming_config_path = default_config
    naming_manager = AnimationNamingManager(
        namespace="srparasites",
        entity_name="kirin",
        config_path=naming_config_path
    )
    # Build animation sources from the converted animation
    animation_sources = []
    if anim_json:
        for anim_name, anim_data in anim_json.get('animations', {}).items():
            # Derive action name from the animation name
            action_name = anim_name.split('.')[-1] if '.' in anim_name else anim_name
            is_looping = anim_data.get('loop', 'loop') == 'loop'
            animation_sources.append({
                'method_name': f'setRotationAngles{action_name.capitalize()}',
                'state_condition': '',
                'is_looping': is_looping,
                'animation_class': 'A1',
                'animation_data': anim_data,
            })
    naming_result = naming_manager.manage(
        animation_sources,
        layer_info=[
            {
                'name': layer.name,
                'layer_type': layer.layer_type,
                'priority': layer.priority,
                'bone_names': layer.bone_names,
                'animation_names': getattr(layer, 'animation_names', []),
            }
            for layer in (layers_result.layers if layers_result else [])
        ]
    )
    print(f"      Named animations: {len(naming_result.entries)}")
    print(f"      Naming conflicts: {len(naming_result.conflicts)}")
    for entry in naming_result.entries:
        print(f"        - {entry.animation_name} (from {entry.source_method}, rule={entry.derivation_rule})")
    if naming_result.conflicts:
        for conflict in naming_result.conflicts:
            print(f"        Conflict: {conflict.conflicting_name} → {conflict.resolution}")

    # Update animation JSON with managed names
    if anim_json and naming_result.entries:
        anim_json = naming_manager.update_animation_json_names(anim_json, naming_result)
        # Re-save with updated names
        anim_json_path = os.path.join(output_dir, "kirin.animation.json")
        anim_json_str = json.dumps(anim_json, indent=2, ensure_ascii=False)
        with open(anim_json_path, 'w') as f:
            f.write(anim_json_str)
        print(f"      Animation JSON updated with managed names")

    # Save AnimationNames Java interface
    anim_names_path = os.path.join(output_dir, "AnimationNames.java")
    with open(anim_names_path, 'w') as f:
        f.write(naming_result.java_interface_code)
    print(f"      AnimationNames interface saved: {anim_names_path}")

    # Save animation naming config template
    naming_config_output = os.path.join(output_dir, "animation_naming.json")
    naming_manager.save_config_template(naming_config_output)
    print(f"      Animation naming config saved: {naming_config_output}")

    # ========================================================================
    # Step 18: Animation reference validation (Layer 1 Deep Enhancement #6)
    # ========================================================================
    print(f"\n[18/21] Validating animation references...")
    ref_validator = AnimationReferenceValidator(namespace="srparasites")
    ref_result = ref_validator.validate(
        animation_json=anim_json or {},
        controller_refs=[
            {
                'controller_name': 'kirinController',
                'animation_names': [entry.animation_name for entry in naming_result.entries],
                'priority': 0,
            }
        ],
        naming_constants=[
            {'constant_name': c.constant_name, 'animation_name': c.animation_name}
            for c in naming_result.constants
        ],
        layer_info=[
            {
                'name': layer.name,
                'layer_type': layer.layer_type,
                'priority': layer.priority,
                'animation_names': getattr(layer, 'animation_names', []),
            }
            for layer in (layers_result.layers if layers_result else [])
        ] if layers_result else None
    )
    print(f"      Reference validation: {'PASS' if ref_result.passed else 'FAIL'}")
    print(f"      Total animations: {ref_result.total_animations}")
    print(f"      Missing animations: {len(ref_result.missing_animations)}")
    print(f"      Orphaned animations: {len(ref_result.orphaned_animations)}")
    if ref_result.all_issues:
        for issue in ref_result.all_issues[:5]:
            print(f"        [{issue.severity}] {issue.detail[:80]}")

    # ========================================================================
    # Step 19: Copy texture + save overlay/particle hints
    # ========================================================================
    print(f"\n[19/22] Copying texture and saving hint files...")
    src_texture = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "jar_extract", "assets", "srparasites",
        "textures", "entity", "monster", "kirin.png"
    )
    dst_texture = os.path.join(output_dir, "kirin.png")
    if os.path.exists(src_texture):
        shutil.copy2(src_texture, dst_texture)
        print(f"      Texture copied: {dst_texture}")
    else:
        print(f"      WARNING: Texture not found at {src_texture}")

    # Save particle hints JSON
    if particle_result.has_particles:
        particle_hints_path = os.path.join(output_dir, "kirin_particle_hints.json")
        particle_hints_json = particle_detector.to_particle_hints_json(particle_result)
        with open(particle_hints_path, 'w') as f:
            json.dump(particle_hints_json, f, indent=2, ensure_ascii=False)
        print(f"      Particle hints saved: {particle_hints_path}")

    # Save overlay hints JSON
    if overlay_result.has_overlay:
        overlay_hints_path = os.path.join(output_dir, "kirin_overlay_hints.json")
        overlay_data = {
            'overlay_layers': [
                {
                    'name': layer.name,
                    'layer_type': layer.layer_type,
                    'trigger_condition': layer.trigger_condition,
                    'color_rgba': list(layer.color_rgba) if layer.color_rgba else None,
                    'texture_path': layer.texture_path,
                    'render_pass': layer.render_pass,
                }
                for layer in overlay_result.overlay_layers
            ],
            'color_settings': overlay_result.color_settings,
            'merge_hints': [
                {'hint_type': h.hint_type, 'description': h.description, 'priority': h.priority}
                for h in overlay_result.merge_hints
            ],
        }
        with open(overlay_hints_path, 'w') as f:
            json.dump(overlay_data, f, indent=2, ensure_ascii=False)
        print(f"      Overlay hints saved: {overlay_hints_path}")

    # ========================================================================
    # Step 20: Generate .bbmodel file
    # ========================================================================
    print(f"\n[20/22] Generating .bbmodel file...")
    from bbmodel_generator import BBModelGenerator
    bbmodel_gen = BBModelGenerator()

    # Load animation if available
    bb_anim_data = None
    if anim_json:
        anim_json_path_check = os.path.join(output_dir, "kirin.animation.json")
        if os.path.isfile(anim_json_path_check):
            with open(anim_json_path_check, 'r') as f:
                bb_anim_data = json.load(f)

    # Generate .bbmodel
    bbmodel = bbmodel_gen.generate(
        geo_json,
        anim_json=bb_anim_data,
        texture_path=dst_texture if os.path.exists(dst_texture) else None,
        texture_name="kirin",
        namespace="srparasites",
    )

    bbmodel_path = os.path.join(output_dir, "kirin.bbmodel")
    bbmodel_gen.save(bbmodel, bbmodel_path)
    print(f"      .bbmodel saved: {bbmodel_path}")

    # ========================================================================
    # Step 21: Generate SwingComponent utility + AnimationNames interface
    # ========================================================================
    print(f"\n[21/22] Generating SwingComponent utility...")
    swing_components = swing_result.swing_components if swing_result else []
    if swing_components:
        swing_util_path = os.path.join(output_dir, "KirinSwingComponents.java")
        # Use the internal method which takes component list
        swing_util_code = swing_analyzer._generate_swing_utility(swing_components)
        with open(swing_util_path, 'w') as f:
            f.write(swing_util_code)
        print(f"      SwingComponent utility saved: {swing_util_path}")

        # Also save hurt controller if detected
        hurt_shakes = swing_result.hurt_shakes if swing_result else []
        if hurt_shakes:
            hurt_code = swing_analyzer._generate_hurt_controller(hurt_shakes)
            hurt_path = os.path.join(output_dir, "KirinHurtController.java")
            with open(hurt_path, 'w') as f:
                f.write(hurt_code)
            print(f"      Hurt controller saved: {hurt_path}")
    else:
        print("      No swing components to generate")

    # ========================================================================
    # Step 22: Generate enhanced Java model
    # ========================================================================
    print(f"\n[22/22] Generating enhanced Java model...")
    _generate_geckolib_java(output_dir, bone_mapping, render_effects, swing_result,
                            layers_result, events_result, visibility_result,
                            overlay_result, firstperson_result, naming_result)

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

        # Run enhanced verification
        bb_json = None
        if output_mode in ("blockbench", "both"):
            try:
                with open(bb_geo_json_path, 'r') as f:
                    bb_json = json.load(f)
            except Exception:
                pass

        # Transform render_effects to verifier-expected format
        # The verifier expects conditional_visibility as a dict, not a list
        render_effect_dict = _to_dict_safe(render_effects)
        if 'conditional_visibility' in render_effect_dict and isinstance(render_effect_dict['conditional_visibility'], list):
            # Convert list of ConditionalVisibility dicts to a dict keyed by bone_var
            cv_dict = {}
            for cv in render_effect_dict['conditional_visibility']:
                bone_var = cv.get('bone_var', 'unknown')
                cv_dict[bone_var] = cv
            render_effect_dict['conditional_visibility'] = cv_dict

        # Add hurt_shake_bones for verifier
        if swing_result and swing_result.hurt_shakes:
            render_effect_dict['hurt_shake_bones'] = list(set(
                bone_mapping.get(hs.bone_var, hs.bone_var)
                for hs in swing_result.hurt_shakes
            ))

        full_report = verifier.verify_full(
            bone_data, geo_json,
            animation_json=anim_json,
            blockbench_json=bb_json,
            render_effect_result=render_effect_dict,
            easing_results=easing_result,
            swing_result=_to_dict_safe(swing_result),
            animation_events=_to_dict_safe(events_result) if events_result else None
        )
        print(f"      Full verification score: {full_report.get('overall_score', 0)*100:.1f}%")
        print(f"      Overall passed: {'YES' if full_report.get('overall_passed') else 'NO'}")

    # ========================================================================
    # Summary
    # ========================================================================
    print("\n" + "=" * 70)
    print("  CONVERSION COMPLETE (Layer 1 Enhanced)")
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
        elif f == "kirin.animation.json":
            marker = " [Animation]"
        elif f == "kirin.bbmodel":
            marker = " [Blockbench Model]"
        elif f.endswith(".java"):
            marker = " [Java Code]"
        print(f"    {f} ({size:,} bytes){marker}")

    print(f"\n  Model Statistics:")
    print(f"    Total bones: {len(bones)}")
    print(f"    Total cubes: {total_cubes}")
    print(f"    Texture: {geo_json['model']['texture_width']}x{geo_json['model']['texture_height']}")

    # Enhancement summary
    print(f"\n  Layer 1 Enhancement Results:")
    print(f"    Render Effects: emissive={render_effects.emissive.detected}, translucent={render_effects.translucency.detected}")
    print(f"    Swing Physics: {len(swing_components)} components, {len(swing_result.gravity_inertia)} inertia, {len(swing_result.hurt_shakes)} hurt shakes")
    print(f"    Animation Layers: {len(layers_result.layers) if layers_result else 0}")
    print(f"    Keyframe Events: {len(events_result.event_markers) if events_result else 0}")
    print(f"    Visibility Rules: {len(visibility_result.visibility_rules)}")
    print(f"    Easing: {easing_result.get('eased_keyframe_count', 0)} non-linear segments")

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


def _to_dict_safe(obj):
    """Convert a dataclass or nested dataclass to dict for JSON serialization."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return {k: _to_dict_safe(v) for k, v in obj.items()}
    if hasattr(obj, '__dataclass_fields__'):
        import dataclasses
        result = {}
        for field_name in obj.__dataclass_fields__:
            val = getattr(obj, field_name)
            if hasattr(val, '__dataclass_fields__'):
                result[field_name] = _to_dict_safe(val)
            elif isinstance(val, dict):
                result[field_name] = _to_dict_safe(val)
            elif isinstance(val, list):
                result[field_name] = [_to_dict_safe(item) for item in val]
            else:
                result[field_name] = val
        return result
    if isinstance(obj, list):
        return [_to_dict_safe(item) for item in obj]
    return obj


def _generate_geckolib_java(output_dir: str, bone_mapping: dict,
                          render_effects, swing_result,
                          layers_result, events_result,
                          visibility_result,
                          overlay_result=None,
                          firstperson_result=None,
                          naming_result=None):
    """Generate an enhanced GeckoLib Java class for the Kirin entity.

    Includes optional enhancement code for:
      - Render type override (from render_effect_parser)
      - Visibility code (from render_effect_parser + dynamic_visibility_detector)
      - Swing component instantiations (from swing_analyzer)
      - Hurt controller registration (from swing_analyzer)
      - Animation layer code (from AnimationLayerSeparator)
      - Event markers info (from KeyframeEventMarker)
      - Overlay code (from OverlayDetector)
      - Held item code (from FirstPersonDetector)
      - Animation naming constants (from AnimationNamingManager)
    """
    # Extract data from dataclass objects safely
    swing_components = swing_result.swing_components if swing_result else []
    hurt_shakes = swing_result.hurt_shakes if swing_result else []

    # Build render type override code
    render_type_code = ""
    if render_effects and (render_effects.emissive.detected or render_effects.translucency.detected):
        render_type_code = (
            "\n    /**\n"
            "     * Render type override for custom rendering.\n"
            "     * Generated from render effect analysis.\n"
            "     */\n"
            "    @Override\n"
            "    public RenderType getRenderType(KirinEntity animatable, ResourceLocation texture) {\n"
        )
        if render_effects.emissive.detected and render_effects.emissive.is_global:
            render_type_code += "        return RenderType.eyes(texture);\n"
        elif render_effects.translucency.detected and render_effects.translucency.is_global:
            render_type_code += "        return RenderType.entityTranslucent(texture);\n"
        else:
            render_type_code += "        return super.getRenderType(animatable, texture);\n"
        render_type_code += "    }\n"

    # Build visibility code
    visibility_code = ""
    all_visibility_rules = []
    if render_effects and render_effects.conditional_visibility:
        all_visibility_rules.extend(render_effects.conditional_visibility)
    if visibility_result and visibility_result.visibility_rules:
        all_visibility_rules.extend(visibility_result.visibility_rules)

    if all_visibility_rules:
        visibility_lines = ["\n    // Conditional visibility for bones"]
        for rule in all_visibility_rules:
            bone_name = getattr(rule, 'bone_name', '') or getattr(rule, 'bone_var', '')
            condition = getattr(rule, 'condition', 'true')
            condition_type = getattr(rule, 'condition_type', 'custom')
            visibility_lines.append(
                f"    // Bone: {bone_name} - condition: {condition} (type: {condition_type})"
            )
        visibility_code = "\n".join(visibility_lines) + "\n"

    # Build swing component instantiations
    swing_code = ""
    if swing_components:
        swing_lines = ["\n    // Swing component instantiations"]
        for i, sc in enumerate(swing_components):
            bone_name = getattr(sc, 'bone_var', f'swing_{i}')
            freq = getattr(sc, 'frequency', 1.0)
            amp = getattr(sc, 'amplitude', 1.0)
            axis = getattr(sc, 'axis', 'x')
            inv = getattr(sc, 'invert', 1)
            swing_lines.append(
                f"    private final SwingComponent {bone_name}Swing = "
                f"new SwingComponent({freq}f, {amp}f, {inv}, 0.0f, 0.0f);"
            )
        swing_code = "\n".join(swing_lines) + "\n"

    # Build hurt controller registration
    hurt_code = ""
    if hurt_shakes:
        hurt_lines = ["\n    // Hurt shake detected - see KirinHurtController.java"]
        for shake in hurt_shakes:
            bone_name = getattr(shake, 'bone_var', 'unknown')
            axis = getattr(shake, 'axis', 'x')
            amplitude = getattr(shake, 'amplitude', 0.1)
            hurt_lines.append(
                f"    // Hurt shake: {bone_name}.{axis} amplitude={amplitude}"
            )
        hurt_code = "\n".join(hurt_lines) + "\n"

    # Build animation layer code
    layer_code = ""
    if layers_result and layers_result.layers:
        layer_lines = ["\n    // Animation layer registrations"]
        for layer in layers_result.layers:
            layer_lines.append(
                f"    // Layer: {layer.name} - type: {layer.layer_type}, "
                f"priority: {layer.priority}, bones: {len(layer.bone_names)}"
            )
        layer_code = "\n".join(layer_lines) + "\n"

    # Build event markers info
    event_code = ""
    if events_result and events_result.event_markers:
        event_lines = ["\n    // Keyframe event markers"]
        for em in events_result.event_markers:
            time_val = em.get('time', 0.0) if isinstance(em, dict) else getattr(em, 'time', 0.0)
            etype = em.get('type', 'unknown') if isinstance(em, dict) else getattr(em, 'event_type', 'unknown')
            ename = em.get('name', 'unnamed') if isinstance(em, dict) else getattr(em, 'name', 'unnamed')
            event_lines.append(
                f"    // Event at {time_val:.3f}s: {etype} - {ename}"
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
