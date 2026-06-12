#!/usr/bin/env python3
"""
Super Converter — CLI Runner
=============================
Main entry point for the Super Architecture animation converter.

Usage:
    # Batch convert MDO-SRP models
    python run.py --batch

    # Convert a single model
    python run.py --single geo.json [--anim animation.json] [--texture model.png] [-o output.bbmodel]

Architecture:
    Frontend (Parse) → Engine (Validate/Transform) → Backend (Export)
    
    Key improvements over old converter:
    - Quaternion-based rotation (no gimbal lock)
    - Explicit carry-forward (distinguishes 0.0 from "no data")
    - Period analysis for seamless loops
    - Unified IR data flow
    - Pipeline-based architecture with per-stage error recovery
"""

import argparse
import json
import os
import sys

# Ensure the super-converter package is importable
CONVERTER_DIR = os.path.dirname(os.path.abspath(__file__))
if CONVERTER_DIR not in sys.path:
    sys.path.insert(0, CONVERTER_DIR)


def cmd_batch(args):
    """Run MDO-SRP batch conversion."""
    from batch.mdo_srp import batch_convert_mdo_srp
    result = batch_convert_mdo_srp(
        input_dir=args.input,
        output_dir=args.output,
    )
    return 0 if result['fail'] == 0 else 1


def cmd_single(args):
    """Convert a single model."""
    from frontend.geckolib_parser import parse_geo_json, parse_animation_json
    from engine.pipeline import AnimationPipeline
    from backend.bbmodel_exporter import BBModelExporter

    # Load geo.json
    with open(args.geo, 'r', encoding='utf-8') as f:
        geo_data = json.load(f)

    # Parse model
    model_ir = parse_geo_json(geo_data)
    print(f"  Parsed model: {model_ir.identifier} ({len(model_ir.bones)} bones)")

    # Parse animation (optional)
    animations_ir = []
    if args.anim and os.path.isfile(args.anim):
        with open(args.anim, 'r', encoding='utf-8') as f:
            anim_data = json.load(f)
        anim_dict = parse_animation_json(anim_data, model_name=model_ir.identifier)
        animations_ir = list(anim_dict.values())
        print(f"  Parsed animations: {len(animations_ir)}")

    # Run animation pipeline
    if animations_ir:
        pipeline = AnimationPipeline()
        from core.types import AnimationIR
        anim_input = {a.name: a for a in animations_ir}
        result = pipeline.process(anim_input, model_name=model_ir.identifier)
        animations_ir = list(result.animations.values())
        print(f"  Pipeline: {len(result.warnings)} warnings")
        if result.warnings:
            for w in result.warnings[:5]:
                print(f"    - {w}")

    # Find texture (optional)
    tex_path = args.texture
    if tex_path and not os.path.isfile(tex_path):
        tex_path = None

    # Export
    exporter = BBModelExporter()
    bbmodel = exporter.export(
        model_ir,
        animations=animations_ir,
        texture_path=tex_path,
        texture_name=os.path.splitext(os.path.basename(args.geo))[0],
    )

    # Determine output path
    output = args.output
    if not output:
        output = os.path.splitext(args.geo)[0] + ".bbmodel"

    exporter.save(bbmodel, output)
    print(f"  Saved: {output}")
    print(f"  Elements: {len(bbmodel.get('elements', []))}")
    print(f"  Animations: {len(bbmodel.get('animations', []))}")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Super Converter — Animation Converter (Super Architecture)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Architecture:
  Frontend (Parse) → Engine (Validate/Transform) → Backend (Export)

Key improvements:
  - Quaternion-based rotation (no gimbal lock)
  - Explicit carry-forward (distinguishes 0.0 from "no data")
  - Period analysis for seamless loops
  - Unified IR data flow
"""
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Batch command
    batch_parser = subparsers.add_parser("batch", help="Batch convert MDO-SRP models")
    batch_parser.add_argument("--input", "-i", default="/home/z/my-project/MDO-SRP-SRC",
                              help="Input directory")
    batch_parser.add_argument("--output", "-o", default="/home/z/my-project/MDO-SRP",
                              help="Output directory")

    # Single command
    single_parser = subparsers.add_parser("single", help="Convert a single model")
    single_parser.add_argument("geo", help="Path to .geo.json file")
    single_parser.add_argument("--anim", "-a", help="Path to .animation.json file")
    single_parser.add_argument("--texture", "-t", help="Path to texture PNG file")
    single_parser.add_argument("--output", "-o", help="Output .bbmodel file path")

    args = parser.parse_args()

    if args.command == "batch":
        sys.exit(cmd_batch(args))
    elif args.command == "single":
        sys.exit(cmd_single(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
