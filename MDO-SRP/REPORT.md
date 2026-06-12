# MDO-SRP Converted Models Report

## Overview

This directory contains **168 Blockbench (.bbmodel) files** converted from SRParasites GeckoLib models using the Super Converter pipeline.

## Source

- **Input**: `srparasites_geckolib_models_v13.zip` — GeckoLib format (geo.json + animation.json + PNG)
- **Output**: Blockbench .bbmodel format (bedrock, per-face UV)
- **Converter**: Super Converter — AST Symbol Compiler Architecture

## Conversion Pipeline

```
Parse (geo.json/animation.json) → AxisTransform → Export (.bbmodel)
```

### Key Transformations

1. **Axis Reflection**: X coordinates of all bone pivots are negated to account for the MC 1.12.2 → Bedrock coordinate convention difference. Bone rotations are transformed as (rx, ry, rz) → (-rx, -ry, rz).

2. **180° Y Rotation Baking**: For bones with ±180° Y rotation, the rotation is baked into cube positions by negating both X and Z of the relative cube position, ensuring correct visual placement.

3. **No Y Offset**: Models use original source Y coordinates without ground-plane adjustment, preserving the author's intended positioning.

4. **Animation Passthrough**: Animation keyframes are preserved directly from the source data with AxisValue tracking for explicit vs. default axis values. No sub-frame interpolation or resampling is applied.

5. **UV Face Preservation**: UV data is passed through without face swaps, as the axis transforms handle the coordinate system difference.

## Statistics

| Metric | Value |
|--------|-------|
| Total models | 168 |
| Successful conversions | 168 |
| Failed conversions | 0 |
| Models with animations | 168 |
| Models with textures | 168 |
| Total animations | 310 |
| Total keyframes | 115,315 |
| Total animated bones | 5,641 |
| Total output size | ~107 MB |

## Categories

| Category | Count |
|----------|-------|
| abomination | 2 |
| adapted | 12 |
| ancient | 3 |
| awakened | 2 |
| crude | 11 |
| derived | 3 |
| deterrent | 33 |
| feral | 9 |
| focused | 2 |
| hijacked | 3 |
| inborn | 11 |
| infected | 29 |
| misc | 20 |
| primitive | 12 |
| projectile | 1 |
| pure | 15 |

## Model Format

Each .bbmodel file contains:

- **Geometry**: All cubes with absolute world-space from/to coordinates and per-face UV mapping
- **Bone Hierarchy**: Outliner tree with bone groups, absolute pivots (origin), and static rotations
- **Animations**: Keyframe data with rotation/position/scale channels per bone
- **Textures**: Embedded as base64 PNG data URIs

### Compatibility

- **Blockbench**: Open directly in Blockbench 4.x+ (Bedrock format)
- **Bedrock Edition**: Export from Blockbench to Bedrock geometry + animation files
- **GeckoLib**: Can be re-exported to GeckoLib format via Blockbench plugins

## Notes

- Some models have texture dimension mismatches (declared vs actual PNG size). The converter uses the actual PNG dimensions as ground truth.
- Models with duplicate bone entries (e.g., venkrol) have been merged — cubes combined, last rotation used.
- Animation keyframes use "linear" interpolation mode, matching the source data's per-segment interpolation.

## Changelog

### v2 (2025-03-05) — Axis Transform Fix

**Root Cause Fix**: The previous converter had three fundamental issues:

1. **Incorrect Y Offset**: Applied a computed Y offset to place models at Y=0, but the source models already use correct absolute Y coordinates. This caused models to "float" (悬空) above or sink below the ground plane. **Fix**: Removed Y offset computation entirely; models now use original source coordinates.

2. **Missing X-Axis Reflection**: The source models use a coordinate convention where the root bone has a -180° Y rotation, mirroring the model. Without negating X coordinates of bone pivots, models appeared "inverted" (本末倒置). **Fix**: Applied YZ-plane reflection (negate X of all bone pivots, negate X and Y of all rotations).

3. **Excessive Keyframe Density**: The engine pipeline was inserting sub-frames at 20fps intervals, inflating file sizes by 10-20x. The reference models only contain keyframes at the original source time points. **Fix**: Bypassed the engine pipeline; parsed animations are passed directly to the exporter.
