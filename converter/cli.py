#!/usr/bin/env python3
"""
MinecraftModelMigrator-Pro - CLI Entry Point
=============================================
Command-line interface for model conversion, verification, and info.

Subcommands:
  convert  - Convert .java or .class input to .geo.json + .animation.json
  verify   - Run verification suite on a .geo.json file
  info     - Show converter version and capabilities
"""

import argparse
import json
import os
import sys

# Ensure converter directory is in path
CONVERTER_DIR = os.path.dirname(os.path.abspath(__file__))
if CONVERTER_DIR not in sys.path:
    sys.path.insert(0, CONVERTER_DIR)

# Also add parent directory for imports
PARENT_DIR = os.path.dirname(CONVERTER_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)


VERSION = "1.0.0"
NAME = "minecraft-model-migrator"


def cmd_convert(args):
    """Handle the 'convert' subcommand."""
    input_path = args.input
    output_dir = args.output
    identifier = args.identifier
    run_verify = args.verify

    if not os.path.exists(input_path):
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    # Read input
    print(f"Reading input: {input_path}")
    with open(input_path, 'r', encoding='utf-8') as f:
        source = f.read()

    # Import converter
    from model_converter import ModelConverter

    converter = ModelConverter()
    result = converter.convert(source, identifier)

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Determine base name from input file
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    if base_name.startswith('Model'):
        base_name = base_name[5:]  # Remove 'Model' prefix
    base_name = base_name[0].lower() + base_name[1:] if base_name else 'model'

    # Save geo.json (game format)
    geo_path = os.path.join(output_dir, f"{base_name}.geo.json")
    geo_str = converter.to_geo_json_string(result)
    with open(geo_path, 'w', encoding='utf-8') as f:
        f.write(geo_str)
    print(f"  Saved: {geo_path} ({len(geo_str):,} bytes)")

    # Save Blockbench format
    bb_path = os.path.join(output_dir, f"{base_name}_bb.geo.json")
    bb_str = converter.to_blockbench_geo_json_string(result)
    with open(bb_path, 'w', encoding='utf-8') as f:
        f.write(bb_str)
    print(f"  Saved: {bb_path} ({len(bb_str):,} bytes)")

    # Save bone mapping
    mapping_path = os.path.join(output_dir, f"{base_name}_bone_mapping.json")
    with open(mapping_path, 'w', encoding='utf-8') as f:
        json.dump(result['bone_mapping'], f, indent=2, ensure_ascii=False)
    print(f"  Saved: {mapping_path}")

    # Try animation conversion
    try:
        from animation_converter import KirinAnimationConverter
        anim_converter = KirinAnimationConverter(result['bone_mapping'])
        anim_result = anim_converter.convert_kirin_idle(source)

        if anim_result.get('animation_json'):
            anim_path = os.path.join(output_dir, f"{base_name}.animation.json")
            anim_str = json.dumps(anim_result['animation_json'], indent=2, ensure_ascii=False)
            with open(anim_path, 'w', encoding='utf-8') as f:
                f.write(anim_str)
            print(f"  Saved: {anim_path} ({len(anim_str):,} bytes)")
            print(f"  Animation class: {anim_result.get('anim_class', 'N/A')}")
        else:
            print("  No animation generated")
    except Exception as e:
        print(f"  Animation conversion skipped: {e}")

    # Show warnings
    if result.get('warnings'):
        print(f"\n  Warnings ({len(result['warnings'])}):")
        for w in result['warnings'][:10]:
            print(f"    - {w}")

    # Model stats
    bones = result['geo_json']['model']['bones']
    total_cubes = sum(len(b.get('cubes', [])) for b in bones)
    print(f"\n  Model: {len(bones)} bones, {total_cubes} cubes")
    print(f"  Texture: {result['geo_json']['model']['texture_width']}x{result['geo_json']['model']['texture_height']}")

    # Optional verification
    if run_verify:
        print(f"\n  Running verification...")
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

        report = verifier.verify(bone_data, result['geo_json'])
        print(f"    Similarity: {report['similarity_score']*100:.2f}%")
        print(f"    Verified: {'PASS' if report['verified'] else 'FAIL'}")
        print(f"    Max error: {report['max_error']:.6f}")
        print(f"    Avg error: {report['avg_error']:.6f}")

    print("\n  Conversion complete!")


def cmd_verify(args):
    """Handle the 'verify' subcommand."""
    geo_path = args.geo_json
    anim_path = args.animation
    bb_path = args.blockbench
    tolerance = args.tolerance

    if not os.path.exists(geo_path):
        print(f"Error: File not found: {geo_path}")
        sys.exit(1)

    # Load geo.json
    with open(geo_path, 'r', encoding='utf-8') as f:
        geo_json = json.load(f)

    # Load optional animation.json
    animation_json = None
    if anim_path and os.path.exists(anim_path):
        with open(anim_path, 'r', encoding='utf-8') as f:
            animation_json = json.load(f)

    # Load optional Blockbench format
    blockbench_json = None
    if bb_path and os.path.exists(bb_path):
        with open(bb_path, 'r', encoding='utf-8') as f:
            blockbench_json = json.load(f)

    from verifier import ModelVerifier

    verifier = ModelVerifier(tolerance=tolerance)

    # Run individual checks that don't need bone_data
    print("Running verification checks...\n")

    # UV validation
    uv_result = verifier.validate_uv_coordinates(geo_json)
    print(f"  UV Validation:        {'PASS' if uv_result['passed'] else 'FAIL'}")
    print(f"    Total faces: {uv_result['total_faces']}")
    print(f"    Valid faces: {uv_result['valid_faces']}")
    print(f"    Violations:  {uv_result['violation_count']}")

    # Y-offset validation
    yoff_result = verifier.validate_y_offset(geo_json)
    print(f"\n  Y-Offset Validation:  {'PASS' if yoff_result['passed'] else 'FAIL'}")
    if yoff_result.get('root_details'):
        rd = yoff_result['root_details']
        if 'pivot' in rd:
            print(f"    Root pivot: {rd['pivot']}")

    # Inflate validation
    inflate_result = verifier.validate_inflate_handling(geo_json)
    print(f"\n  Inflate Validation:   {'PASS' if inflate_result['passed'] else 'FAIL'}")
    print(f"    Cubes with inflate: {inflate_result['cubes_with_inflate']}")
    print(f"    Issues:             {inflate_result['issue_count']}")

    # Animation bone matching
    if animation_json:
        anim_result = verifier.validate_animation_bone_names(animation_json, geo_json)
        print(f"\n  Animation Matching:   {'PASS' if anim_result['passed'] else 'FAIL'}")
        print(f"    Anim bones:  {anim_result['total_anim_bones']}")
        print(f"    Matched:     {anim_result['matched_bones']}")
        print(f"    Missing:     {anim_result['missing_bones']}")
        if anim_result['missing_bone_names']:
            for name in anim_result['missing_bone_names']:
                print(f"      - {name}")
    else:
        print(f"\n  Animation Matching:   Skipped (no animation.json)")

    # Blockbench format validation
    if blockbench_json:
        bb_result = verifier.verify_blockbench_format(blockbench_json)
        print(f"\n  Blockbench Format:    {'PASS' if bb_result['passed'] else 'FAIL'}")
        print(f"    Issues: {bb_result['issue_count']}")
    else:
        print(f"\n  Blockbench Format:    Skipped (no blockbench .geo.json)")

    print(f"\n  Note: Vertex comparison requires original 1.12.2 bone data.")
    print(f"  Use 'convert --verify' for full verification with vertex comparison.")


def cmd_info(args):
    """Handle the 'info' subcommand."""
    print(f"{NAME} v{VERSION}")
    print()
    print("Capabilities:")
    print(f"  Input formats:    .java (decompiled source), .class (via ASM parser)")
    print(f"  Output formats:   .geo.json (GeckoLib game), _bb.geo.json (Blockbench)")
    print(f"  Animation:        .animation.json (Class A-1), Java code (Class A-2, B)")
    print()
    print("Verification checks:")
    print(f"  - Vertex comparison (world-space, M_model transform)")
    print(f"  - UV coordinate bounds validation")
    print(f"  - Bone hierarchy preservation")
    print(f"  - Animation bone name matching")
    print(f"  - Inflate handling verification")
    print(f"  - Y-offset validation (root bone [0, 24, 0])")
    print(f"  - Blockbench format validation")
    print()
    print("Coordinate system:")
    print(f"  Transform:  M_model = diag(1, -1, -1)")
    print(f"  Position:   (x, y, z) → (x, -y, -z) + Y+24 offset")
    print(f"  Rotation:   (rx, ry, rz) → (rx, -ry, -rz) degrees")
    print()
    print("Modules:")
    print(f"  core_math.py           - Coordinate transformation library")
    print(f"  model_converter.py     - Model conversion engine")
    print(f"  animation_converter.py - Animation conversion engine")
    print(f"  verifier.py            - Offline rendering verification")
    print(f"  parsers/base_parser.py - Plugin architecture (ABC)")
    print(f"  templates/             - Jinja2 output templates")
    print(f"  cli.py                 - Command-line interface")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog=NAME,
        description="MinecraftModelMigrator-Pro — MC 1.12.2 → GeckoLib 1.20.1 Model Converter"
    )
    parser.add_argument(
        '--version', action='version', version=f'{NAME} v{VERSION}'
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # --- convert subcommand ---
    convert_parser = subparsers.add_parser(
        'convert',
        help='Convert .java or .class input to .geo.json + .animation.json',
        description='Convert a Minecraft 1.12.2 ModelBase Java source to GeckoLib 1.20.1 format'
    )
    convert_parser.add_argument(
        'input',
        help='Input file path (.java or .class)'
    )
    convert_parser.add_argument(
        '-o', '--output',
        default='output',
        help='Output directory (default: output)'
    )
    convert_parser.add_argument(
        '-i', '--identifier',
        default='model.converted',
        help='GeckoLib model identifier (default: model.converted)'
    )
    convert_parser.add_argument(
        '--verify',
        action='store_true',
        help='Run verification after conversion'
    )
    convert_parser.set_defaults(func=cmd_convert)

    # --- verify subcommand ---
    verify_parser = subparsers.add_parser(
        'verify',
        help='Verify a .geo.json file',
        description='Run the verification suite on a converted .geo.json file'
    )
    verify_parser.add_argument(
        'geo_json',
        help='Path to .geo.json file to verify'
    )
    verify_parser.add_argument(
        '-a', '--animation',
        help='Path to .animation.json for bone name matching'
    )
    verify_parser.add_argument(
        '-b', '--blockbench',
        help='Path to Blockbench _bb.geo.json for format validation'
    )
    verify_parser.add_argument(
        '-t', '--tolerance',
        type=float,
        default=0.1,
        help='Vertex comparison tolerance (default: 0.1)'
    )
    verify_parser.set_defaults(func=cmd_verify)

    # --- info subcommand ---
    info_parser = subparsers.add_parser(
        'info',
        help='Show converter version and capabilities',
        description='Display version, capabilities, and module information'
    )
    info_parser.set_defaults(func=cmd_info)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
