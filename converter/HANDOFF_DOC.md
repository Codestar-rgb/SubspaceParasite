# MinecraftModelMigrator-Pro — Handoff Documentation

> **Document Purpose**: This file captures critical debugging experience, coordinate system mathematics,
> and .bbmodel format rules discovered across multiple development sessions. It is intended for any
> developer taking over this project to avoid repeating the same painful debugging cycles.

---

## 1. Project Overview

**MinecraftModelMigrator-Pro** is a converter that migrates Minecraft 1.12.2 entity models to
GeckoLib 1.20.1 format.

### Conversion Pipeline

```
MC 1.12.2 Java ModelBase + ModelRenderer
    │
    ├─► .geo.json        (GeckoLib geometry definition)
    ├─► .animation.json  (GeckoLib animation keyframes)
    └─► .bbmodel         (Blockbench project file for visual editing)
```

### Key Entities
- **Heblu**: Flying parasite entity with mirrored wing bones and multi-axis rotations
- **Kirin**: Quadruped parasite entity with cyclic animations

---

## 2. Critical Bug Fixes (THE MOST IMPORTANT SECTION)

> These bugs were discovered and fixed through extensive debugging. Each one represents hours of
> investigation. Re-introducing any of these would be catastrophic.

### Bug #1: Y-Axis Offset -24.0

- **Problem**: In .bbmodel output, all non-root bone pivots were shifted 24 pixels downward. The
  model appeared "sunken" below the ground.
- **Root Cause**: In MC 1.12.2, the model origin is at Y=24 (top of hitbox). The geo.json root
  bone pivot is `[0, 24, 0]` which already includes this offset. When computing absolute pivots
  for .bbmodel, we accumulate relative pivots from root — but root's pivot already has +24 in Y.
  Non-root bones DON'T have this +24 in their accumulated pivots, causing a missing +24 offset.
- **Fix**: In `BBModelGenerator._compute_absolute_pivots()`, add `Y_OFFSET=24.0` to all NON-ROOT
  bone pivots. Root bone already has it, so adding to root would double-count.
- **Code Location**: `bbmodel_generator.py`, line ~293-301
- **Verification**: Compare root bone pivot and first child pivot. If child Y is 24 less than
  expected, this bug is present.

### Bug #2: North↔South UV Face Swap

- **Problem**: When opening the converted .bbmodel in Blockbench, the north and south face textures
  were swapped. The front of cubes showed the back texture and vice versa.
- **Root Cause**: The coordinate conversion from MC 1.12.2 (RH, Z into screen) to GeckoLib (LH,
  Z out of screen) involves flipping the Z axis via `M_model = diag(1, -1, -1)`. This Z-flip
  reverses the "north" (+Z in geo.json) and "south" (-Z in geo.json) face directions. The UV
  calculation in model_converter.py uses the original 1.12.2 convention, but the face naming in
  .bbmodel uses the post-flip convention. Therefore, what geo.json calls "north" (which was
  originally the -Z face in 1.12.2) should be mapped to "south" in .bbmodel.
- **Fix**: In `BBModelGenerator._convert_faces()`, swap north↔south UVs using a `FACE_SWAP`
  mapping dict.
- **Code Location**: `bbmodel_generator.py`, line ~400-411
- **Verification**: Open .bbmodel in Blockbench, check if front face textures match the texture
  atlas layout.

### Bug #3: Bone Rotation Conversion (Extrinsic XYZ vs Intrinsic xyz)

- **Problem**: Multi-axis bone rotations (especially wing bones in Heblu) were wrong — wings
  appeared twisted or folded incorrectly.
- **Root Cause Analysis** (THIS WAS THE HARDEST BUG — took 3 iterations):
  - **First attempt**: Assumed .bbmodel uses intrinsic xyz Euler angles (`R = Rx·Ry·Rz`),
    converted from geo.json's extrinsic XYZ (`R = Rz·Ry·Rx`) using scipy
    `Rotation.from_euler('XYZ', angles).as_euler('xyz')`. This was WRONG.
  - **Second attempt**: Tried sign-flip `(-rx, -ry, rz)` for .bbmodel based on a different
    convention reading. Also WRONG.
  - **Final fix**: After extensive comparison with a known-working reference .bbmodel file,
    discovered that .bbmodel ALSO uses extrinsic XYZ convention, just like geo.json. The rotation
    values should be passed through directly WITHOUT any conversion between Euler conventions.
  - **Key insight**: The geo.json rotation `(rx, -ry, -rz)` from `convert_model_rot()` IS already
    in extrinsic XYZ. Blockbench's .bbmodel format stores these same extrinsic XYZ values. No
    scipy rotation conversion needed — just pass through the values.
- **Fix**: `_convert_rotation_to_bbmodel()` now simply returns `[rx, ry, rz]` directly.
- **Code Location**: `bbmodel_generator.py`, line ~99-115
- **CRITICAL NOTE**: The geo.json stores rotations in degrees after
  `convert_model_rot(rx, ry, rz) = (rx, -ry, -rz)` from radians, then `rad_to_deg()`. The
  .bbmodel uses these SAME degree values. Do NOT convert between Euler angle conventions.

### Bug #4: Mirror Stacking (Double-Mirror)

- **Problem**: Mirrored bones (wings) appeared double-mirrored, making them look inside-out.
- **Root Cause**: Initially, the .bbmodel generator applied a geometric X-flip to element
  positions for `mirror=true` bones, AND also set `mirror_uv=true`. This caused the mirror effect
  to be applied twice.
- **Fix**: Switch from geometric X-flip to `mirror=true` flag only. GeckoLib/Blockbench handles
  the X-axis mirror internally when `mirror=true` is set — it applies
  `GlStateManager.scale(-1, 1, 1)` which flips the cube. Setting the flag is sufficient; any
  additional geometric flipping causes double-mirror.
- **Code Location**: `bbmodel_generator.py` `_build_elements()`, line ~376 sets
  `"mirror_uv": bool(mirror)`; `_build_outliner()` does NOT apply any geometric flip.

---

## 3. Coordinate System Mathematics (Must-Know)

The transformation matrix `M_model = diag(1, -1, -1)` converts from MC 1.12.2 (Y-down, RH) to
GeckoLib (Y-up, LH).

| Property | Formula | Notes |
|---|---|---|
| **Position** | `convert_model_pos(x, y, z) = (x, -y, -z)` | Y and Z flip |
| **Rotation** | `convert_model_rot(rx, ry, rz) = (rx, -ry, -rz)` | Derived from similarity transform `R' = M_model · R · M_model⁻¹` |
| **Cube origin** | `convert_model_cube_origin(ox, oy, oz, w, h, d) = (ox, -(oy+h), -(oz+d))` | Minimum corner in Y-up space |
| **Cube size** | `convert_model_cube_size(w, h, d) = (w, h, d)` | Preserved (dimensions don't change) |

**IMPORTANT**: `converter/core_math.py` MUST NOT be modified. It contains the mathematically
proven coordinate transformations.

---

## 4. .bbmodel Format Key Rules

1. **Element from/to**: ABSOLUTE world-space coordinates (NOT bone-local)
2. **Element origin**: ABSOLUTE bone pivot (rotation center in world space)
3. **Bone origin**: ABSOLUTE world-space pivot (NOT relative to parent, despite what some docs say)
4. **Y_OFFSET = 24.0**: Applied to non-root bones only in `_compute_absolute_pivots()`
5. **North↔South UV swap**: Required due to Z-axis flip
6. **Rotation**: Direct pass-through of geo.json extrinsic XYZ angles (NO Euler convention conversion)
7. **Mirror**: Use `mirror_uv` flag on elements, do NOT geometrically flip positions

---

## 5. Known Issues (Still Present)

### Heblu Wing Rotation: skin_2_c0 and skin_5_c0

- The outermost wing parts (`skin_2_c0` on one side, `skin_5_c0` on the other) have incorrect
  rotation/position
- They should correctly connect with `skin_1_c0` and `skin_4_c0` respectively
- **CRITICAL**: The reference .bbmodel file ALSO has this same error — so you cannot use it for
  validation
- The fix must be derived mathematically from the geo.json bone hierarchy and pivot data
- Likely related to multi-axis rotation accumulation through the bone chain
- The wing chain is: `skin_0_c0 → skin_1_c0 → skin_2_c0` (left) and
  `skin_3_c0 → skin_4_c0 → skin_5_c0` (right)

### Kirin Animation Fluency

- Cyclic animations may have discontinuities at the loop point
- Needs optimization for smooth continuous looping

---

## 6. File Structure

```
converter/
├── core_math.py           # Coordinate transformation (DO NOT MODIFY)
├── model_converter.py     # Model conversion engine
├── animation_converter.py # Animation conversion engine
├── bbmodel_generator.py   # .bbmodel project file generator
├── verifier.py            # Verification system
├── cli.py                 # CLI entry point
├── setup.py               # Package setup
├── run_heblu.py           # Heblu entity runner
├── run_kirin.py           # Kirin entity runner
├── easing_fitter.py       # Easing curve fitting
├── swing_analyzer.py      # Swing physics analysis
├── render_effect_parser.py # Render effect parsing
├── animation_layer_separator.py # Animation layer separation
├── keyframe_event_marker.py # Keyframe event detection
├── dynamic_visibility_detector.py # Dynamic visibility
├── parsers/
│   ├── __init__.py
│   ├── base_parser.py     # Plugin architecture (ABC)
│   ├── java_source_parser.py
│   └── bytecode_parser.py
├── enhancements/
│   └── layer1_deep/       # Layer 1 deep enhancement modules
├── templates/             # Jinja2 output templates
└── output/                # Generated output files
    ├── heblu.geo.json
    ├── heblu.animation.json
    ├── heblu_debug.bbmodel
    ├── heblu.png
    ├── kirin.geo.json
    ├── kirin.animation.json
    ├── kirin_debug.bbmodel
    ├── kirin.png
    └── ...
```

---

## 7. Quick Start for New Developers

```bash
# Convert Heblu
cd converter
python run_heblu.py --mode both

# Convert Kirin
python run_kirin.py --mode both --verify

# CLI usage
python cli.py convert ModelKirin.java -o output/ --identifier model.kirin
```

---

## 8. Dependencies

- Python 3.8+
- numpy
- scipy (for rotation conversion — though current code doesn't use it for bbmodel)
- jinja2 (for template output)
- javalang (optional, for AST parsing)
