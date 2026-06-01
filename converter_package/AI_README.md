# MinecraftModelMigrator-Pro — AI Usage Guide

> **Document Purpose**: This is the comprehensive guide for any AI or developer taking over this project.
> It contains everything needed to use the converter at the current conversion quality level,
> including critical bug fix history, coordinate mathematics, format rules, and the full pipeline API.

---

## Overview

This is a **Minecraft 1.12.2 → GeckoLib 1.20.1** model+animation converter. It takes decompiled Java
ModelBase source code and produces `.geo.json`, `.animation.json`, and `.bbmodel` files.

### Conversion Pipeline

```
MC 1.12.2 Java ModelBase + ModelRenderer
    |
    +---> .geo.json        (GeckoLib geometry definition)
    +---> .animation.json  (GeckoLib animation keyframes)
    +---> .bbmodel         (Blockbench project file for visual editing)
    +---> .java            (Java controller/utility code for complex animations)
```

### Key Entity Examples
- **Heblu**: Flying parasite entity with mirrored wing bones and multi-axis rotations
- **Kirin**: Quadruped parasite entity with cyclic animations

---

## Quick Start - Conversion Pipeline

### Step 1: Parse Java source → geo.json

```python
from model_converter import ModelConverter

converter = ModelConverter()
result = converter.convert(java_source_string, "model.entityName")
geo_json = result['geo_json']
bone_mapping = result['bone_mapping']
```

The `bone_mapping` is critical for Step 2 — it maps Java variable names to GeckoLib bone names.

### Step 2: Extract animations → animation.json

```python
from animation_extractor import AnimationExtractor

extractor = AnimationExtractor(bone_mapping)
anim_json = extractor.extract(java_source_string, "entityName", max_bones=150)
```

### Step 3: Apply easing (optional but recommended)

```python
from easing_fitter import EasingFitter

fitter = EasingFitter()
# First prepare keyframe data, then:
anim_json = fitter.apply_easing_to_animation_json(anim_json, animation_bones_data)
```

### Step 4: Generate .bbmodel (Blockbench project file)

```python
from bbmodel_generator import BBModelGenerator

bbgen = BBModelGenerator()
bbmodel = bbgen.generate(
    geo_json,
    anim_json=anim_json,
    texture_path="path/to/texture.png",
    texture_name="entityName",
    namespace="srparasites",
)
bbgen.save(bbmodel, "output/entityName.bbmodel")
```

### Step 5: .bbmodel → geo.json + PNG (if needed)

```python
from bbmodel_to_geo import BBModelToGeo, batch_convert

converter = BBModelToGeo()
result = converter.convert_bbmodel("input.bbmodel", "output_dir/")
```

### Full Example: Entity Conversion Pipeline

See `run_heblu.py` and `run_kirin.py` for complete end-to-end examples. These demonstrate:
- Loading Java source files
- Running the full conversion pipeline
- Verification steps
- Output file writing

---

## Batch Conversion

```bash
python batch_convert.py --source /path/to/src --output /path/to/output --textures /path/to/textures
```

The `batch_convert.py` contains a comprehensive `TEXTURE_NAME_MAP` that maps entity class names to
their texture file names.

---

## CLI Usage

```bash
python cli.py convert ModelKirin.java -o output/ --identifier model.kirin
python cli.py convert ModelHeblu.java -o output/ --identifier model.heblu --verify
```

---

## CRITICAL Rules

### 1. core_math.py MUST NOT be modified

It contains the mathematically proven coordinate transformations. These were derived from the
similarity transform `M_model = diag(1, -1, -1)` and verified against reference models.

| Property | Formula | Notes |
|---|---|---|
| **Position** | `convert_model_pos(x, y, z) = (x, -y, -z)` | Y and Z flip |
| **Rotation** | `convert_model_rot(rx, ry, rz) = (rx, -ry, -rz)` | Derived from similarity transform `R' = M_model * R * M_model^-1` |
| **Cube origin** | `convert_model_cube_origin(ox, oy, oz, w, h, d) = (ox, -(oy+h), -(oz+d))` | Minimum corner in Y-up space |
| **Cube size** | `convert_model_cube_size(w, h, d) = (w, h, d)` | Preserved (dimensions don't change) |

### 2. Coordinate System: M_model = diag(1, -1, -1)

- **MC 1.12.2**: Y-DOWN, Right-Handed (Z into screen)
- **GeckoLib**: Y-UP, Left-Handed (Z out of screen)
- The transformation matrix `M_model = diag(1, -1, -1)` converts between these systems
- All position and rotation conversions follow from this matrix

### 3. .bbmodel Format Rules

These rules were discovered through extensive debugging. Violating any of them will produce
visually incorrect models.

1. **Element from/to**: ABSOLUTE world-space coordinates (NOT bone-local)
2. **Element origin**: ABSOLUTE bone pivot (rotation center in world space)
3. **Bone origin**: ABSOLUTE world-space pivot (NOT relative to parent, despite what some docs say)
4. **Y_OFFSET = 24.0**: Applied to non-root bones only in `_compute_absolute_pivots()`.
   Root bone already has +24 in Y from the geo.json pivot `[0, 24, 0]`; adding to root would
   double-count.
5. **North↔South UV swap**: Required due to Z-axis flip. The coordinate conversion flips Z,
   which reverses the north/south face directions. Use a `FACE_SWAP` mapping dict in
   `BBModelGenerator._convert_faces()`.
6. **Rotation**: Direct pass-through of geo.json extrinsic XYZ angles. NO Euler convention
   conversion needed. Both geo.json and .bbmodel use extrinsic XYZ.
7. **Mirror**: Use `mirror_uv` flag on elements. Do NOT geometrically flip X positions —
   GeckoLib/Blockbench handles the X-axis mirror internally when `mirror=true` is set
   (it applies `GlStateManager.scale(-1, 1, 1)` which flips the cube).

### 4. Animation Conversion Notes

- **Class A-1** (time-driven, `ageInTicks`): Numerical sampling → `.animation.json`
  - Sample the Java animation code at regular intervals (e.g., every tick)
  - Apply Douglas-Peucker simplification for keyframe reduction
  - Period-aware duration for seamless looping
  - Loop continuity enforcement (cosine blend zone)

- **Class A-2** (movement-driven, `limbSwing`): → Java code for `GeoBone.setRotation`
  - Cannot be expressed in .animation.json (depends on runtime movement variable)
  - Generate Java code that implements the rotation in a `GeoModel` subclass

- **Class B** (state machine): → AnimationController Java code
  - Multi-state animations controlled by conditions
  - Generate Java `AnimationController` code with state transitions

- **Easing fitter**: Auto-fit easing types to animation curves for natural motion
- **Douglas-Peucker simplification**: Reduces keyframe count while preserving curve shape
- **Period-aware duration**: Detects animation period for seamless looping
- **Loop continuity enforcement**: Uses cosine blend zone at loop boundaries

### 5. SRG Name Mappings (in model_converter.py)

These are the obfuscated Minecraft method/field names used in 1.12.2 decompiled source:

```
func_78793_a  →  setRotationPoint
func_78790_a  →  addBox
func_78792_a  →  addChild
field_78795_f →  rotateAngleX
field_78796_g →  rotateAngleY
field_78808_h →  rotateAngleZ
field_82906_o →  offsetX
field_82907_q →  offsetY
field_82908_p →  offsetZ
```

---

## Critical Bug Fixes (DO NOT REGRESS)

> These bugs were discovered and fixed through extensive debugging. Each one represents hours of
> investigation. Re-introducing any of these would be catastrophic.

### Bug #1: Y-Axis Offset -24.0

- **Problem**: In .bbmodel output, all non-root bone pivots were shifted 24 pixels downward.
  The model appeared "sunken" below the ground.
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
  - **First attempt**: Assumed .bbmodel uses intrinsic xyz Euler angles (`R = Rx*Ry*Rz`),
    converted from geo.json's extrinsic XYZ (`R = Rz*Ry*Rx`) using scipy
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

## Known Issues (Still Present)

- **skin_c0/skin_3_c0 wing membrane bones**: May need manual position correction. The outermost
  wing parts (`skin_2_c0` on one side, `skin_5_c0` on the other) have incorrect rotation/position.
  They should correctly connect with `skin_1_c0` and `skin_4_c0` respectively. The reference
  .bbmodel file ALSO has this same error — so you cannot use it for validation. The fix must be
  derived mathematically from the geo.json bone hierarchy and pivot data. Likely related to
  multi-axis rotation accumulation through the bone chain. The wing chain is:
  `skin_0_c0 → skin_1_c0 → skin_2_c0` (left) and `skin_3_c0 → skin_4_c0 → skin_5_c0` (right).

- **Neck twitching/flickering**: In some animations, neck twitching/flickering may occur — needs
  higher sampling precision.

- **bbmodel_to_geo.py coordinate transforms**: May produce clumped models at -Y. This is a known
  issue in the reverse conversion pipeline.

- **Beckon Stage 1-3 rotation/position**: Differs from Stage 4 in some entity animations.

- **Kirin Animation Fluency**: Cyclic animations may have discontinuities at the loop point.
  Needs optimization for smooth continuous looping.

---

## File Descriptions

| File | Purpose |
|------|---------|
| `core_math.py` | Coordinate transformation library (DO NOT MODIFY) |
| `model_converter.py` | Java → geo.json conversion engine |
| `bbmodel_generator.py` | geo.json → .bbmodel with textures, UV swaps, Z-180° baking |
| `bbmodel_to_geo.py` | .bbmodel → geo.json + PNG extraction |
| `animation_converter.py` | Generic animation conversion (A-1, A-2, StateMachine) |
| `animation_extractor.py` | High-precision extraction with state machine parsing |
| `easing_fitter.py` | Auto-fit easing types to animation curves |
| `verifier.py` | Full verification suite (vertex, UV, hierarchy, etc.) |
| `cli.py` | CLI entry point |
| `batch_convert.py` | Batch converter with comprehensive TEXTURE_NAME_MAP |
| `render_effect_parser.py` | Parse render effects (glow, transparency) from Java source |
| `swing_analyzer.py` | Swing physics analysis for movement-driven animations |
| `animation_layer_separator.py` | Separate blended animation layers |
| `dynamic_visibility_detector.py` | Detect dynamic visibility conditions in animations |
| `keyframe_event_marker.py` | Detect and mark keyframe events (sound, particle triggers) |
| `heblu_animation_generator.py` | Example: entity-specific animation with MC helper functions |
| `kirin_animation_generator.py` | Example: entity-specific animation generator |
| `run_heblu.py` | Example: full Heblu entity conversion pipeline |
| `run_kirin.py` | Example: full Kirin entity conversion pipeline |
| `setup.py` | Package setup configuration |

### Subdirectories

| Path | Purpose |
|------|---------|
| `parsers/` | Plugin architecture for parsing Java source and bytecode |
| `parsers/base_parser.py` | Abstract base class for parser plugins |
| `parsers/java_source_parser.py` | Java source code parser |
| `parsers/bytecode_parser.py` | Java bytecode parser (for .class files) |
| `enhancements/layer1_deep/` | Layer 1 deep enhancement modules |
| `enhancements/layer1_deep/animation_naming_manager.py` | Animation naming conventions |
| `enhancements/layer1_deep/sound_keyframe_filler.py` | Sound keyframe auto-filling |
| `enhancements/layer1_deep/animation_reference_validator.py` | Animation reference validation |
| `enhancements/layer1_deep/overlay_detector.py` | Overlay texture detection |
| `enhancements/layer1_deep/firstperson_detector.py` | First-person arm detection |
| `enhancements/layer1_deep/particle_detector.py` | Particle effect detection |
| `templates/` | Jinja2 output templates |
| `templates/geo_model.blockbench.json.j2` | Blockbench-format geo.json template |
| `templates/geo_model.game.json.j2` | Game-format geo.json template |
| `templates/java_animation.java.j2` | Java animation class template |
| `templates/java_controller.java.j2` | Java animation controller template |
| `templates/java_model.java.j2` | Java model class template |
| `templates/utility_class.java.j2` | Java utility class template |
| `templates/animation.json.j2` | GeckoLib animation.json template |

---

## Verification System

The `verifier.py` module provides a full verification suite to validate conversion quality:

```python
from verifier import Verifier

verifier = Verifier()
results = verifier.verify(geo_json, original_java_source)
# Check vertex positions, UV mappings, bone hierarchy, cube sizes, etc.
```

Verification checks include:
- **Vertex verification**: Ensure cube vertices match after coordinate transformation
- **UV verification**: Check texture coordinate mappings
- **Hierarchy verification**: Validate bone parent-child relationships
- **Cube size verification**: Ensure dimensions are preserved
- **Pivot verification**: Check bone pivot positions

---

## Entity-Specific Animation Generation

For entities that need custom animation logic beyond the generic extractor, create entity-specific
animation generators. See `heblu_animation_generator.py` for a comprehensive example that includes:

- MC helper function simulation (sin, cos, sqrt, etc.)
- Wing flap animation with proper mirroring
- State machine animation logic
- Walk/fly/idle animation blending

```python
# Example: Heblu animation generator
from heblu_animation_generator import HebluAnimationGenerator

gen = HebluAnimationGenerator(bone_mapping)
anim_json = gen.generate_all_animations()
```

---

## Dependencies

```
numpy>=1.20.0
scipy>=1.7.0
jinja2>=3.0.0
javalang>=0.13.0
```

- **numpy**: Array operations for vertex/UV calculations
- **scipy**: Rotation conversion (used in animation processing; NOT used for bbmodel rotation passthrough)
- **jinja2**: Template rendering for Java and JSON output
- **javalang**: Optional Java AST parsing for better source analysis

---

## Architecture Notes

### Parser Plugin System

The `parsers/` directory implements a plugin architecture:
- `base_parser.py`: Abstract base class defining the parser interface
- `java_source_parser.py`: Parses decompiled `.java` source files
- `bytecode_parser.py`: Parses `.class` bytecode files (for when source is unavailable)

### Enhancement Layers

The `enhancements/` directory contains post-processing enhancement modules:
- **Layer 1 (Deep)**: Structural analysis enhancements
  - Animation naming: Standardizes animation names to GeckoLib conventions
  - Sound keyframe filling: Auto-adds sound events at appropriate keyframes
  - Animation reference validation: Ensures all referenced animations exist
  - Overlay detection: Identifies overlay texture layers
  - First-person detection: Identifies first-person arm geometry
  - Particle detection: Identifies particle effect trigger points

### Template System

Jinja2 templates in `templates/` generate output files:
- **geo.json templates**: Two variants — Blockbench format and game format
- **Java templates**: Generate controller, model, animation, and utility classes for
  animations that cannot be expressed in .animation.json format
- **animation.json template**: GeckoLib animation file format

---

## Usage Patterns

### Pattern 1: Simple Model Conversion (no animation)

```python
from model_converter import ModelConverter
from bbmodel_generator import BBModelGenerator

converter = ModelConverter()
result = converter.convert(java_source, "model.myentity")

bbgen = BBModelGenerator()
bbmodel = bbgen.generate(result['geo_json'], texture_path="myentity.png")
bbgen.save(bbmodel, "output/myentity.bbmodel")
```

### Pattern 2: Full Model + Animation Conversion

```python
from model_converter import ModelConverter
from animation_extractor import AnimationExtractor
from easing_fitter import EasingFitter
from bbmodel_generator import BBModelGenerator

# Convert model
converter = ModelConverter()
result = converter.convert(java_source, "model.myentity")

# Extract and process animations
extractor = AnimationExtractor(result['bone_mapping'])
anim_json = extractor.extract(java_source, "myentity")

# Apply easing
fitter = EasingFitter()
anim_json = fitter.apply_easing_to_animation_json(anim_json, animation_data)

# Generate bbmodel with animations
bbgen = BBModelGenerator()
bbmodel = bbgen.generate(result['geo_json'], anim_json=anim_json,
                         texture_path="myentity.png", texture_name="myentity")
bbgen.save(bbmodel, "output/myentity.bbmodel")
```

### Pattern 3: Reverse Conversion (.bbmodel → geo.json)

```python
from bbmodel_to_geo import BBModelToGeo

converter = BBModelToGeo()
result = converter.convert_bbmodel("input.bbmodel", "output_dir/")
# Produces: output_dir/model.geo.json and output_dir/model.png
```

### Pattern 4: Batch Conversion

```bash
python batch_convert.py \
    --source /path/to/java/sources \
    --output /path/to/output \
    --textures /path/to/texture/atlas
```

---

## Common Pitfalls

1. **Forgetting the Y_OFFSET=24.0**: When computing absolute pivots for .bbmodel, non-root bones
   need +24 in Y. Forgetting this makes the model sink 24 pixels.

2. **Converting rotation between Euler conventions**: Do NOT use scipy to convert between extrinsic
   XYZ and intrinsic xyz for .bbmodel. Both formats use extrinsic XYZ — just pass through.

3. **Double-mirroring mirrored bones**: Set `mirror_uv=true` flag only. Do NOT also geometrically
   flip X coordinates. The flag alone triggers the engine's built-in mirror.

4. **Swapping north/south UVs**: The Z-axis flip means north and south faces swap. If you forget
   this, textures on front/back faces will be swapped in Blockbench.

5. **Using bone-local coordinates in .bbmodel**: Elements in .bbmodel use ABSOLUTE world-space
   coordinates for from/to and origin, not bone-local. This is different from geo.json which uses
   bone-local coordinates.

6. **Forgetting to convert radians to degrees**: The Java source uses radians for rotations.
   `core_math.py` converts the values, but you need to ensure `rad_to_deg()` is applied before
   writing to .bbmodel.

---

## Version History

- **1.0.0**: Initial working conversion with all 4 critical bugs fixed
  - Y_OFFSET=24.0 fix
  - North↔South UV swap fix
  - Rotation passthrough fix (no Euler convention conversion)
  - Mirror flag-only fix (no geometric flip)
