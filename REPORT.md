# MDO-SRP Super Converter — Technical Report

## Overview

The MDO-SRP Super Converter transforms GeckoLib animation format (`.geo.json` + `.animation.json`) into Blockbench `.bbmodel` format for the Subspace Parasite mod.

## Architecture

```
Frontend (Parse) → Engine (Validate/Transform) → Backend (Export)
```

### Pipeline Stages (6-stage AST Symbol Compiler)
1. **Parse** — GeckoLib geo.json + animation.json → Unified IR
2. **Validate** — NaN/Infinity cleanup, rotation clamping, dedup
3. **SymbolCompile** — Per-axis AST expressions (Constant/Linear/CatmullRom/Hold)
4. **PeriodLock** — LCM-based period detection for seamless loops
5. **LoopAlign** — First/last keyframe match for loop animations
6. **SymbolEvaluate** — Evaluate AST at merged time points

### Batch Converter Flow
The batch converter bypasses the engine pipeline to preserve source keyframe timing faithfully. Parsed animations pass directly to the exporter.

## v3 Fixes (This Release)

### Fix 1: Animation Rotation Axis Transform (CRITICAL)
**Problem**: Model static rotations were transformed `(-rx, -ry, rz)` but animation rotation values were NOT transformed. This caused animated rotations to apply in the wrong direction in Blockbench.

**Root Cause**: The axis reflection transform was only applied to the model parsing (`_apply_axis_transforms`), not to animation data.

**Fix**: Added `_apply_animation_axis_transforms()` in `geckolib_parser.py`:
- Rotation: `(rx, ry, rz) → (-rx, -ry, rz)` — mirrors rotation direction with the model
- Position: `(px, py, pz) → (-px, py, pz)` — mirrors position with the model
- Scale: no transform (multiplicative, unaffected by mirror)
- Molang expressions: NOT transformed (runtime-evaluated strings)

**Mathematical Proof**: 
```
total_rot = static_rot + anim_offset
After transform: (-static_rx, -static_ry, static_rz) + anim_offset_transformed
= (-total_rx, -total_ry, total_rz)
Therefore: anim_offset_transformed = (-anim_rx, -anim_ry, anim_rz)
```

### Fix 2: Interpolation Mode (CRITICAL)
**Problem**: All keyframes were exported with `"interpolation": "linear"`, ignoring the IR's interpolation field. Rotation animations appeared jerky and robotic instead of smooth.

**Root Cause**: `bbmodel_exporter.py` line 868 hardcoded `"interpolation": "linear"`.

**Fix**: Changed to `"interpolation": kf.interpolation`. The parser now correctly sets:
- Rotation → `catmullrom` (default, smooth curves)
- Position → `linear` (direct interpolation)
- Scale → `linear` (direct interpolation)
- Non-linear easing → `catmullrom`

**Impact**: 102,273 rotation keyframes now use `catmullrom` instead of `linear`.

### Fix 3: Loop Mode Mapping
**Problem**: GeckoLib `hold_on_last_frame` was passed through verbatim instead of being converted to Blockbench's `hold`.

**Fix**: Added mapping in `_serialize_single_animation()`:
```python
if bb_loop == "hold_on_last_frame":
    bb_loop = "hold"
```

### Fix 4: Deterrent Directory Deduplication
**Problem**: The `deterrent/` directory contained 13 pairs of case-variant models (e.g., `dodSII` vs `dodsii`). The uppercase versions are LOD/simplified variants with 2-3x fewer keyframes.

**Fix**: Added deduplication in `batch/mdo_srp.py` that prefers lowercase (full-detail) versions:
- Same geometry (identical bones, cubes, UVs)
- Lowercase: 2-3.6x more keyframes (smoother animation)
- 13 uppercase variants eliminated from output

## Conversion Statistics

| Metric | Value |
|--------|-------|
| Total models | 155 |
| Failed | 0 |
| Total animations | 295 |
| Total keyframes | 106,708 |
| Rotation catmullrom | 102,273 |
| Position linear | 4,435 |
| Loop: hold | 1 |
| Loop: hold_on_last_frame | 0 (corrected) |
| Output size | 95.4 MB |

## Known Limitations

1. **Composite animations** (e.g., `fly_vomit`, `cosmic_shaking` in reference) do not exist in source GeckoLib data and cannot be generated
2. **Animation name namespace** differs from reference (`animation.kirin.idle` vs `animation.srparasites.kirin.idle`) — follows source data naming
3. **Animation length** matches source exactly; reference files have time-stretched animations from a different pipeline
4. **Engine pipeline** is bypassed in batch mode; `run.py --single` still uses the full pipeline for advanced features (period detection, loop alignment, rotation normalization)

## File Structure

```
super-converter/
├── batch/mdo_srp.py              # Batch converter entry point
├── frontend/
│   ├── geckolib_parser.py         # GeckoLib geo + animation parser
│   └── axis_tracker.py            # Per-axis explicit/default tracking
├── engine/                        # AST Symbol Compiler pipeline (6 stages)
│   ├── pipeline.py                # Pipeline orchestrator
│   ├── symbol_compiler.py         # Build per-segment AST expressions
│   ├── symbol_evaluator.py        # Evaluate AST with overshoot clamping
│   ├── symbol_table.py            # SymbolTable, ExprNode, Segment types
│   ├── period_locker.py           # LCM period detection
│   ├── loop_aligner.py            # Loop boundary alignment
│   ├── rotation_normalizer.py     # Quaternion shortest-path
│   └── validator.py               # NaN/Infinity/dedup cleanup
├── backend/
│   └── bbmodel_exporter.py        # Export to .bbmodel format
├── core/
│   ├── types.py                   # Unified IR type definitions
│   ├── math_utils.py              # UUID, rounding, LCM, autocorrelation
│   ├── quaternion.py              # Full quaternion math + SLERP
│   └── coords.py                  # MC 1.12.2 → GeckoLib transforms
└── run.py                         # CLI runner
```
