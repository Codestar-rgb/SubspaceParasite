# MDO-SRP Conversion Report

## Overview

This directory contains 168 Blockbench `.bbmodel` files converted from the SRParasites Geckolib model set using the **MDO-SRP (Multi-Dimensional Object - Symbol Resolution Pipeline)** super converter.

## Pipeline Architecture

```
Parse → Validate → SymbolCompile → PeriodLock → SymbolEvaluate → LoopAlign → RotNormalize → Export
```

### Key Pipeline Stages

| Stage | Function |
|-------|----------|
| **Parse** | Parse GeckoLib geo.json + animation.json into unified IR |
| **Validate** | Clean NaN/Inf, normalize rotations, deduplicate keyframes |
| **SymbolCompile** | Build per-axis AST expressions with correct interpolation selection |
| **PeriodLock** | LCM-based period detection for seamless loop alignment |
| **SymbolEvaluate** | Evaluate AST at merged time points with overshoot clamping |
| **LoopAlign** | Ensure loop animations match at boundaries |
| **RotNormalize** | Quaternion shortest-path + equivalent rotation simplification |

## Bug Fixes (v2.1)

### Critical Fix 1: Duplicate Bone Name Handling

**Problem**: 8 source models (venkrol series, tonro, unvo) contained duplicate bone entries with the same name but different rotations. This caused:
- Two groups with the same UUID in the .bbmodel output
- The outliner referencing only one group (typically the wrong one)
- Models appearing inverted or incorrectly oriented

**Fix**: The parser now deduplicates bone entries by name, merging cubes and using the last entry's rotation (which is typically the correct final rotation).

**Affected models**: `deterrent/venkrol`, `deterrent/venkrolSII`, `deterrent/venkrolSIII`, `deterrent/venkrolsii`, `deterrent/venkrolsiii`, `deterrent/tonro`, `deterrent/unvo`, `derived/venkrolSIV`

### Critical Fix 2: Y Offset Accounting for Root Rotation

**Problem**: Models with non-trivial root bone rotations (X or Z components) were positioned incorrectly — either floating above the ground or sinking into it. The Y offset was computed from un-rotated cube positions, but after the root rotation is applied during rendering, the visual bottom of the model shifts.

**Fix**: The Y offset computation now applies the root bone's rotation to all cube corners before finding the minimum Y, ensuring the visual bottom of the rotated model aligns with Y=0 (ground plane).

**Affected models**: All models with root bone X/Z rotation (venkrol series, tonro, unvo)

### Critical Fix 3: Equivalent Rotation Simplification

**Problem**: Some models had root bone rotations like `[-180, -180, 180]` which is mathematically equivalent to identity (no rotation). Blockbench could have rendering or interpolation issues with these complex representations.

**Fix**: The exporter now detects and simplifies rotations that are equivalent to simpler forms:
- `[-180, -180, 180]` → `[0, 0, 0]` (identity)
- Rotations equivalent to simple 180° Y rotation are simplified accordingly

**Affected models**: `derived/venkrolSIV` and potentially others

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

### Coordinate System
- Source: GeckoLib Bedrock format (Y-up, left-hand)
- Output: Blockbench .bbmodel (Y-up, left-hand)
- Root bone -180° Y rotation is preserved (standard GeckoLib convention for model facing direction)
- Models with tilted root bones (e.g., venkrol at -54.78° X) are positioned so the visual bottom sits at Y=0

### Animation Processing
- CatmullRom interpolation with overshoot clamping (margin = max(5°, 15% of range))
- Snap-heavy rotation channels auto-detected and downgraded to linear
- Sub-frame insertion at 20 FPS for smooth playback
- LCM-based period locking for consistent loop periods

### Texture Handling
- Textures are embedded as base64 in the .bbmodel files
- PNG dimensions override declared dimensions when mismatched (ground truth)
- Some models have texture dimension mismatches in the source data (auto-corrected)

## Conversion Statistics

- **Total models**: 168
- **Conversion success**: 168/168 (100%)
- **Models with animations**: 168
- **Models with textures**: 168
- **Total animations**: 310
- **Total keyframes**: 1,352,304
- **Total animated bones**: 5,641

## Source Data

Source models from: [Qom-Inseac (SRParasites)](https://github.com/Codestar-rgb/Qom-Inseac)

## Converter Version

Super Converter v2.1 (AST Symbol Compiler Architecture)
