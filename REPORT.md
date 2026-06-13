# MDO-SRP Super Converter — Technical Report v4.0

## Overview

The MDO-SRP Super Converter transforms GeckoLib animation format (`.geo.json` + `.animation.json`) into Blockbench `.bbmodel` format for the SRParasites (Scape and Run Parasites) mod.

This document covers the complete conversion pipeline architecture, all known issues discovered during development, and the fixes applied in each version.

## Architecture

```
Frontend (Parse) → Engine (Transform) → Backend (Export)
```

### Pipeline Stages (v4.0)

```
Parse → CarryForward → LoopExtend → CatmullRomBake → IdleWalkMerge → WalkEnhance → Export
```

1. **Parse** — GeckoLib `.geo.json` + `.animation.json` → Unified IR (`AnimationIR`)
2. **CarryForward** — Interpolation-aware fill for missing axes at merged time points
3. **LoopExtend** — Multi-cycle extension for short loop animations
4. **CatmullRomBake** — Bake CatmullRom curves into dense linear keyframes
5. **IdleWalkMerge** — Merge idle animation data into walk animations
6. **WalkEnhance** — Add synthetic leg rotation to subtle walk animations
7. **Export** — Output `.bbmodel` format with embedded textures

### Batch Converter Flow

The batch converter (`batch/mdo_srp.py`) runs the full pipeline for all 168 models from MDO-SRP source data.

---

## Version History & Fixes

### v4.0 — Walk Animation Completeness (Current)

#### Fix 1: CatmullRom Loop Boundary Flash (CRITICAL)

**Problem**: When using CatmullRom interpolation in looping animations, Blockbench does NOT enable `animation_loop_wrapping`. The last keyframe is not properly interpolated with the first keyframe of the loop. This causes a visible tangent discontinuity — the animation briefly "pops" or "flashes to origin" at each cycle boundary.

**Root Cause**: The Bedrock `.bbmodel` format does not support CatmullRom loop wrapping. Blockbench uses the second-to-last keyframe as the "before_plus" control point for the first segment, and the second keyframe as the "after_plus" for the last segment. This creates severe tangent distortion with chord-length parameterization.

**Fix**: Two-stage approach:
1. **Loop Extension** (`loop_extender.py`): Extend short loop animations to multiple cycles (3x–8x). This reduces the frequency of loop boundary hits and places the actual boundary far from dense keyframe regions. For example, a 0.67s walk cycle becomes 2.0s (3x), making the CatmullRom wrapping distortion negligible.
2. **CatmullRom Baking** (`catmullrom_baker.py`): Bake all CatmullRom curves into dense linear keyframes at 20fps sampling rate. Linear interpolation has no tangent/control point dependencies, eliminating the wrapping problem entirely. This follows the same approach as the Blockbench Bakery plugin.

**Reference**: The heblu-SubSRP.bbmodel reference file uses the same multi-cycle extension strategy:
- idle: 2.3271s → 6.9813s (3x)
- attack: 2.0944s → 8.3776s (4x)
- fly: 3.1416s → 4.7124s (1.5x)

#### Fix 2: Interpolation-Aware Carry-Forward (CRITICAL)

**Problem**: The previous carry-forward used "last explicit value" for missing axes at merged time points. This created **step functions** where GeckoLib expects smooth interpolation.

**Example of the problem**:
```
Source rotation: {
  x: {0.0: 0, 1.0: 30, 2.0: 0},
  y: {0.0: 0, 0.5: 15, 1.5: -15, 2.0: 0}
}
After merge, keyframes needed at t=0.0, 0.5, 1.0, 1.5, 2.0.

OLD (broken): at t=0.5, x has no data → carry-forward x=0 from t=0.0
  → Creates a STEP from 0→0→30 instead of smooth 0→15→30

NEW (correct): at t=0.5, x has no data → INTERPOLATE x=15 from x's own curve
  → Smooth: 0→15→30, matching GeckoLib's per-axis interpolation
```

**Root Cause**: GeckoLib renders each axis independently with its own interpolation. When we merge keyframes into unified time points, we must simulate the same interpolation that GeckoLib would use.

**Fix** (`carry_forward.py`): For each axis, store its own time series from the source. At each merged time point, interpolate missing values using CatmullRom from the axis's own curve. All interpolated values are marked `explicit=True` because they represent the correct animated value GeckoLib would compute.

#### Fix 3: Walk Animation Completeness (CRITICAL)

**Problem**: In the SRP mod, many creatures' walk animations have very small rotation ranges (<5°). This is because the original mod uses GeckoLib animations as **overlay effects** — the main walking motion comes from Java entity code that programmatically rotates leg bones based on movement speed. The GeckoLib animation only adds subtle body sway and slight leg adjustments on top.

When converted to Blockbench `.bbmodel` format, the programmatic rotation is lost, leaving only the subtle overlay — which looks like "slight foot lifts" or "barely visible movement".

**Analysis of 71 walk animations**:
- 44 have max rotation < 5° (overlay-only, need enhancement)
- 8 have max rotation 5–15° (partial, might need enhancement)
- 19 have max rotation >= 15° (self-contained, no enhancement needed)

**Fix** — Two complementary modules:

1. **Idle-Walk Merger** (`idle_walk_merger.py`): Merge idle animation data INTO walk animations to simulate GeckoLib's animation layering. In SRP, idle provides arm/tentacle/hair/tail sway (always playing), while walk adds leg rotation + body bob on top. In Blockbench format (no layering), converted walks are missing the arm/body sway. The merger adds:
   - Bones only in idle → add full animation from idle, sampled at walk timeline
   - Bones in both → walk takes priority for meaningful channels, idle fills constant/zero channels
   - Timeline alignment: sample idle cyclically when walk is longer (t % idle_length)

2. **Walk Enhancer** (`walk_enhancer.py`): For walk animations with small rotation ranges, generate synthetic walking leg rotation and ADD it to existing animation values:
   - Standard sinusoidal pattern for leg rotation around X axis
   - Alternates front-left/back-right (in phase) vs front-right/back-left (opposite phase)
   - Amplitude complements existing animation (target ~25° total range)
   - Preserves original subtle body sway and position effects
   - Leg bone classification via regex patterns (e.g., `jointfll` → Phase A, `jointfrl` → Phase B)

---

### v3.0 — UV & Rotation Fixes

#### Fix 1: UP/DOWN Face UV Coordinate Inversion (CRITICAL)

**Problem**: All models' up/down face textures were displayed reversed ("本末倒置").

**Root Cause**: Source `.geo.json` uses negative `uv_size` values for texture flipping (e.g., `uv=[29, 10], uv_size=[-19, -10]`). The converter computed `[u, v, u+w, v+h]` = `[29, 10, 10, 0]`, but bbmodel requires `u1 ≤ u2, v1 ≤ v2` in `[u1, v1, u2, v2]`.

**Fix**: UV coordinate normalization in `_convert_faces()`:
```python
u1, u2 = (u, u + w) if w >= 0 else (u + w, u)
v1, v2 = (v, v + h) if h >= 0 else (v + h, v)
```

#### Fix 2: Animation Rotation Axis Transform (CRITICAL)

**Problem**: Model static rotations were transformed `(-rx, -ry, rz)` but animation rotation values were NOT transformed. Animated rotations applied in the wrong direction.

**Mathematical Proof**:
```
total_rot = static_rot + anim_offset
After transform: (-static_rx, -static_ry, static_rz) + anim_offset_transformed
= (-total_rx, -total_ry, total_rz)
Therefore: anim_offset_transformed = (-anim_rx, -anim_ry, anim_rz)
```

**Fix**: Added axis transform for animation data:
- Rotation: `(rx, ry, rz) → (-rx, -ry, rz)` — mirrors rotation with the model
- Position: `(px, py, pz) → (-px, py, pz)` — mirrors position with the model
- Scale: no transform (multiplicative, unaffected by mirror)
- Molang expressions: NOT transformed (runtime-evaluated strings)

#### Fix 3: Interpolation Mode (CRITICAL)

**Problem**: All keyframes were exported with `"interpolation": "linear"`, ignoring the IR's interpolation field. Rotation animations appeared jerky and robotic.

**Fix**: Changed hardcoded `"linear"` to use `kf.interpolation`. The parser now correctly sets:
- Rotation → `catmullrom` (default, smooth curves)
- Position → `linear` (direct interpolation)
- Scale → `linear` (direct interpolation)

**Impact**: 102,273 rotation keyframes now use `catmullrom` instead of `linear`.

#### Fix 4: Loop Mode Mapping

**Problem**: GeckoLib `hold_on_last_frame` was passed through verbatim instead of being converted to Blockbench's `hold`.

**Fix**: Added mapping: `hold_on_last_frame` → `hold`

#### Fix 5: Rotation Baking Removal

**Problem**: Static bone rotations were "baked" into cube positions, causing models to appear upside-down or floating.

**Fix**: Removed rotation baking. Static rotations are now preserved as bone rotation properties in the `.bbmodel` output.

---

### v2.1 — Initial Batch Conversion

- AST Symbol Compiler pipeline (6 stages)
- 168 models converted from GeckoLib format
- Deterrent directory deduplication (13 uppercase LOD variants eliminated)
- Quaternion rotation handling with shortest-path normalization

---

## Conversion Statistics (v4.0)

| Metric | Value |
|--------|-------|
| Total models | 168 |
| Failed | 0 |
| Total animations | 295+ |
| Walk animations enhanced | 44 |
| Walk animations merged with idle | ~71 |
| CatmullRom baked to linear | All loop animations |
| Loop extensions applied | All loops < 3.0s |

## Known Limitations

1. **Composite animations** (e.g., `fly_vomit`, `cosmic_shaking` in reference) do not exist in source GeckoLib data and cannot be generated
2. **Animation name namespace** differs from reference (`animation.kirin.idle` vs `animation.srparasites.kirin.idle`) — follows source data naming
3. **Animation length** matches source exactly for non-extended animations; loop-extended animations are multiples of the source length
4. **Walk enhancement** uses heuristic leg bone classification — some exotic bone names may not be detected
5. **Idle-walk merging** depends on both idle and walk animations being present in the source data

## File Structure

```
super-converter/
├── batch/
│   └── mdo_srp.py              # Batch converter entry point
├── frontend/
│   ├── geckolib_parser.py       # GeckoLib geo + animation parser
│   └── axis_tracker.py          # Per-axis explicit/default tracking
├── engine/
│   ├── carry_forward.py         # Interpolation-aware carry-forward
│   ├── loop_extender.py         # Multi-cycle loop extension
│   ├── catmullrom_baker.py      # CatmullRom → linear baking
│   ├── idle_walk_merger.py      # Idle+walk animation merging
│   ├── walk_enhancer.py         # Synthetic walk leg rotation
│   ├── interpolation.py         # Interpolation utilities
│   ├── loop_aligner.py          # Loop boundary alignment
│   ├── period_analyzer.py       # Animation period detection
│   ├── period_locker.py         # LCM period locking
│   ├── pipeline.py              # Pipeline orchestrator
│   ├── rotation_normalizer.py   # Quaternion shortest-path
│   ├── subframe_inserter.py     # Sub-frame key insertion
│   ├── symbol_compiler.py       # Per-segment AST expressions
│   ├── symbol_evaluator.py      # AST evaluation with clamping
│   ├── symbol_table.py          # SymbolTable, ExprNode, Segment
│   └── validator.py             # NaN/Infinity/dedup cleanup
├── backend/
│   └── bbmodel_exporter.py      # Export to .bbmodel format
├── core/
│   ├── types.py                 # Unified IR type definitions
│   ├── math_utils.py            # UUID, rounding, LCM, autocorrelation
│   ├── quaternion.py            # Full quaternion math + SLERP
│   └── coords.py                # MC 1.12.2 → GeckoLib transforms
├── config.py                    # Configuration constants
├── run.py                       # CLI runner
└── REPORT.md                    # This file
```
