# MDO-SRP Conversion Report v3.0

## Overview

This directory contains 168 Blockbench `.bbmodel` files converted from the SRParasites Geckolib model set using the **MDO-SRP (Multi-Dimensional Object - Symbol Resolution Pipeline)** super converter.

## Pipeline Architecture

```
Parse → AxisTransform → Export
```

### Key Pipeline Stages

| Stage | Function |
|-------|----------|
| **Parse** | Parse GeckoLib geo.json + animation.json into unified IR |
| **AxisTransform** | Apply coordinate system transforms for correct .bbmodel output |
| **Export** | Serialize to .bbmodel format with embedded textures and animations |

## Bug Fixes (v3.0)

### Critical Fix 1: Cube Position X-Negation

**Problem**: The previous converter used a "delta shift" approach for cube positions — shifting cube origin X by the same delta as the bone pivot X. This produced incorrect relative positions, causing 68/141 elements in kirin to be offset by varying amounts (1.0 to 32.0 units).

**Fix**: Replaced with simple X-negation of both from/to corners for ALL cube positions. This matches the reference converter's behavior exactly: negate both corners, then ensure from <= to.

**Verification**: 141/141 kirin elements and 356/356 heblu elements now match reference files with zero positional error.

### Critical Fix 2: Single-Axis ±180° Rotation Baking

**Problem**: Bones with pure single-axis ±180° rotations (X, Y, or Z) had their rotations applied at render time, but the cube positions were not adjusted. This caused visual errors ("本末倒置" — inverted parts, "悬空" — floating/disconnected parts).

**Fix**: Pure single-axis ±180° rotations are now baked into cube positions and the bone rotation is set to identity:
- **±180° X**: Mirror Y and Z around pivot, then negate X
- **±180° Y**: Mirror Z around pivot only (X handled by axis transform), then negate X
- **±180° Z**: Mirror X and Y around pivot, then negate X

**Affected models**: All models with skin/flat mesh bones (heblu skin_1-5, tendril variants, etc.)

### Critical Fix 3: Removed Quaternion Rotation Simplification

**Problem**: The exporter was using quaternion dot-product checks to simplify equivalent rotations (e.g., [-180, 0, 180] → [0, 180, 0]). While mathematically equivalent, different Euler angle decompositions can cause subtle rendering differences in Blockbench.

**Fix**: Removed quaternion simplification entirely. Original rotation decompositions from the axis transform are preserved exactly.

### Fix 4: Duplicate Bone Name Handling (inherited from v2.1)

8 source models contained duplicate bone entries with the same name but different rotations. The parser deduplicates by name, merging cubes and using the last entry's rotation.

### Fix 5: Animation Pipeline Simplification

The engine pipeline (SymbolCompile → PeriodLock → LoopAlign → SymbolEvaluate) was causing excessive keyframe density by inserting sub-frames at 20 FPS. The reference files only contain keyframes at original source time points. The pipeline is now bypassed, and parsed animations are passed directly to the exporter with AxisValue tracking for explicit vs. default axis data.

## Model Categories

| Category | Count | Description |
|----------|-------|-------------|
| primitive | 12 | Base primitive forms |
| adapted | 12 | Adapted variants of primitives |
| focused | 2 | Focused combat variants |
| pure | 15 | Pure evolved forms |
| crude | 11 | Crude parasitic forms |
| inborn | 11 | Innate parasitic entities |
| infected | 29 | Infected host creatures |
| feral | 9 | Feral infected variants |
| deterrent | 35 | Deterrent-stage entities |
| derived | 3 | Derived evolved forms |
| ancient | 3 | Ancient parasitic entities |
| awakened | 2 | Awakened variants |
| hijacked | 3 | Hijacked host bodies |
| abomination | 2 | Abomination composites |
| misc | 20 | Miscellaneous entities |
| projectile | 1 | Projectile entities |

## Technical Notes

### Coordinate System Transform

The conversion applies the following transforms to convert from GeckoLib source coordinates to .bbmodel coordinates:

1. **Bone pivots**: Negate X → (-x, y, z)
2. **Bone rotations**: Negate X and Y → (-rx, -ry, rz)
3. **Cube positions**: Negate both from_x and to_x corners, then ensure from ≤ to
4. **Single-axis ±180° rotations**: Bake into cube positions (see Fix 2 above)

These transforms handle the coordinate system difference between the MC 1.12.2 Java models (original source) and the Blockbench .bbmodel format.

### Animation Processing

- Parsed animations use AxisValue to track explicit vs. default axis values
- Only keyframes with at least one explicit axis are output
- All channels use "linear" interpolation matching reference format
- Bone UUIDs (not names) are used as animator keys

### Texture Handling

- Textures are embedded as base64 in the .bbmodel files
- PNG dimensions override declared dimensions when mismatched (ground truth)

## Conversion Statistics

- **Total models**: 168
- **Conversion success**: 168/168 (100%)
- **Models with animations**: 168
- **Models with textures**: 168
- **Total animations**: 310
- **Total keyframes**: 115,315
- **Total animated bones**: 5,641

## Verification

Verified against user-provided reference files:
- **kirin.bbmodel**: 141/141 elements match (0 positional error)
- **heblu-SubSRP.bbmodel**: 356/356 elements match (0 positional error)

## Source Data

Source models from: [Qom-Inseac (SRParasites)](https://github.com/Codestar-rgb/Qom-Inseac)

## Converter Version

Super Converter v3.0 (AST Symbol Compiler Architecture with Corrected Axis Transforms)
