# MinecraftModelMigrator-Pro — Technical Documentation

> Comprehensive technical reference for the MC 1.12.2 → GeckoLib 1.20.1 model conversion system.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Coordinate System Transformation](#2-coordinate-system-transformation)
3. [Model Conversion Pipeline](#3-model-conversion-pipeline)
4. [Animation Conversion Pipeline](#4-animation-conversion-pipeline)
5. [Blockbench (.bbmodel) Output](#5-blockbench-bbmodel-output)
6. [Verification System](#6-verification-system)
7. [Enhancement Layer](#7-enhancement-layer)
8. [Conversion Results](#8-conversion-results)
9. [CLI Usage Guide](#9-cli-usage-guide)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Project Overview

### 1.1 Purpose

MinecraftModelMigrator-Pro automates the migration of Java-based Minecraft entity models from the 1.12.2 modding era (`ModelBase` / `ModelRenderer`) to the modern GeckoLib 1.20.1 format (`.geo.json` + `.animation.json`). It handles the complete coordinate system transformation (Y-down RH → Y-up LH), preserves bone hierarchies, computes UV coordinates, converts animations, and generates Blockbench-compatible project files for visual verification.

### 1.2 Scope and Capabilities

| Capability | Description |
|---|---|
| **Model geometry** | Full ModelRenderer → `.geo.json` conversion with pivot, rotation, cubes, UV, mirror, inflate |
| **Animation** | Time-driven (Class A-1) → `.animation.json`; Movement-driven (Class A-2/B) → Java code snippets |
| **Multi-state** | State-aware extraction (idle, fly, evolved_idle) from conditional animation code |
| **Blockbench** | `.bbmodel` project file generation with embedded textures and animations |
| **Verification** | 13-point offline verification suite with vertex comparison |
| **Enhancements** | Overlay detection, particle mounting, sound keyframes, first-person analysis, naming management |

### 1.3 Supported Input Formats and Output Targets

**Input:**
- Decompiled Java source (`.java`) with SRG-obfuscated names
- Optionally: `.class` bytecode via ASM parser plugin

**Output:**

| File | Format | Purpose |
|---|---|---|
| `entity.geo.json` | GeckoLib game format | Runtime model for GeckoLib 4.x |
| `entity_bb.geo.json` | Blockbench Bedrock format | Visual preview in Blockbench |
| `entity.animation.json` | GeckoLib animation | Class A-1 time-driven animations |
| `entity.bbmodel` | Blockbench project | Full project with textures + animations |
| `*_bone_mapping.json` | Reference | Java variable → bone name mapping |
| `*GeoModel.java` | Java template | 1.20.1 GeoModel implementation |
| `*_code_animation.java` | Java code | Class A-2/B movement-driven snippets |

### 1.4 Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                 MinecraftModelMigrator-Pro                          │
│               MC 1.12.2 → GeckoLib 1.20.1                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐       ┌───────────────────┐                      │
│  │  Parser       │       │   CoreMath         │                      │
│  │  Plugin       │──────▶│   M_model           │                      │
│  │  ┌──────────┐│       │   diag(1, -1, -1)  │                      │
│  │  │ Java     ││       └────────┬───────────┘                      │
│  │  │ ASM      ││                │                                    │
│  │  └──────────┘│       ┌────────▼───────────┐                      │
│  └──────────────┘       │  ModelConverter     │                      │
│                         │  ├─ Pivot flip      │                      │
│  ┌──────────────┐       │  ├─ Rotation Xform │                      │
│  │  Template     │◀──────│  ├─ Cube origin    │                      │
│  │  Engine       │       │  ├─ UV calculation  │                      │
│  │  (Jinja2)    │       │  └─ Inflate handle  │                      │
│  └──────────────┘       └────────┬───────────┘                      │
│                         ┌────────▼───────────┐                      │
│                         │ AnimConverter       │                      │
│                         │  ├─ Class A-1 (time)│                      │
│                         │  ├─ Class A-2 (state)│                     │
│                         │  └─ Class B (move) │                      │
│                         └────────┬───────────┘                      │
│                         ┌────────▼───────────┐                      │
│                         │  BBModelGenerator   │                      │
│                         │  ├─ Elements        │                      │
│                         │  ├─ Outliner        │                      │
│                         │  └─ Anim embedding  │                      │
│                         └────────┬───────────┘                      │
│                         ┌────────▼───────────┐                      │
│                         │   Verifier          │                      │
│                         │   ├─ Vertex compare │                      │
│                         │   ├─ UV bounds      │                      │
│                         │   ├─ Hierarchy check│                      │
│                         │   ├─ Anim matching  │                      │
│                         │   ├─ Y-offset check │                      │
│                         │   └─ Normal check   │                      │
│                         └────────────────────┘                      │
│                         ┌────────────────────┐                      │
│                         │  Enhancement Layer  │                      │
│                         │  ├─ OverlayDetector │                      │
│                         │  ├─ FirstPersonDet. │                      │
│                         │  ├─ ParticleDetector│                      │
│                         │  ├─ SoundKeyframe   │                      │
│                         │  ├─ AnimNamingMgr   │                      │
│                         │  └─ AnimRefValidator│                      │
│                         └────────────────────┘                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Coordinate System Transformation

### 2.1 The Transformation Matrix

The core of the conversion is the linear transformation matrix `M_model`:

```
M_model = diag(1, -1, -1) = | 1   0   0 |
                              | 0  -1   0 |
                              | 0   0  -1 |
```

**Key property:** `M_model` is its own inverse (`M_model² = I`), meaning the transformation is an involution.

### 2.2 Why M_model = diag(1, -1, -1)

The matrix arises from the combination of two axis reversals:

| Axis | MC 1.12.2 | GeckoLib 1.20.1 | Transformation |
|---|---|---|---|
| X | Right | Right | Preserved (×1) |
| Y | Down (0=top of hitbox) | Up (0=feet) | Negated (×-1) |
| Z | Into screen (RH) | Out of screen (LH) | Negated (×-1) |

The Y-flip is **not** a simple translation — it is a genuine axis direction reversal that affects rotation angles via the similarity transform. The Z-flip handles the right-hand → left-hand change.

**Decomposition:**
```
M_model = diag(1,-1,-1) = diag(1,-1,1) × diag(1,1,-1) = M_y × M
```
where `M_y = diag(1,-1,1)` is the Y-negation and `M = diag(1,1,-1)` is the pure RH→LH matrix.

### 2.3 Position Conversion

```
P_GeckoLib = M_model × P_MC1.12.2 = (x, -y, -z)
```

**Example:** A pivot at `(5, 12, 3)` in Y-down space maps to `(5, -12, -3)` in Y-up space, before the +24 Y origin shift.

The origin shift (top-of-hitbox → feet) is a **translation** applied separately by the `ModelConverter` via the root bone pivot at `[0, 24, 0]`, because it depends on entity height rather than being a linear transformation.

### 2.4 Rotation Conversion (Single-Axis)

For single-axis rotations, the similarity transform `R' = M_model × R × M_model⁻¹` yields:

| Axis | Original | Transformed | Explanation |
|---|---|---|---|
| X rotation | θ | θ (unchanged) | X axis is not flipped by M_model |
| Y rotation | φ | -φ (negated) | Y axis is flipped, so rotations about Y reverse |
| Z rotation | ψ | -ψ (negated) | Z axis is flipped, so rotations about Z reverse |

**Combined single-axis formula:**
```
(rx, ry, rz) → (rx, -ry, -rz)
```

### 2.5 Multi-Axis Rotation (Similarity Transform)

When more than one rotation component is non-zero, the simple angle negation may be inaccurate due to rotation order differences. The converter uses a matrix-based approach:

**Algorithm:**
1. Construct the 1.12.2 rotation matrix: `R = Rz(rz) × Ry(ry) × Rx(rx)`
2. Apply coordinate system transform: `R' = M_model × R × M_model⁻¹`
3. Decompose `R'` into Z→Y→X Euler angles (GeckoLib order) using Graphics Gems IV formulas:
   - `β = asin(R'[0,2])`
   - `α = atan2(-R'[1,2], R'[2,2])`
   - `γ = atan2(-R'[0,1], R'[0,0])`
4. Return `(α, β, γ)`

**Gimbal lock handling:** When `|R'[0,2]| ≈ 1`, `α = 0` and `γ = atan2(R'[1,0], R'[1,1])`.

### 2.6 Z-Origin Fix for Cube Origins

In MC 1.12.2, `addBox(ox, oy, oz, w, h, d)` creates a box spanning `[ox, ox+w] × [oy, oy+h] × [oz, oz+d]`.

After applying `M_model`:
- X: `[ox, ox+w]` → `[ox, ox+w]` (unchanged)
- Y: `[oy, oy+h]` → `[-(oy+h), -oy]` (min corner is `-(oy+h)`)
- Z: `[oz, oz+d]` → `[-(oz+d), -oz]` (min corner is `-(oz+d)`)

GeckoLib/Bedrock format specifies the cube origin as the **minimum corner**, so:

```
new_origin = (ox, -(oy+h), -(oz+d))
new_size   = (w, h, d)   // preserved under linear transformation
```

**Negative dimensions:** When `h < 0`, the interval becomes `[oy+h, oy]`, and after Y-flip: `[-oy, -(oy+h)]`, giving min corner = `-oy`. When `d < 0`, min corner = `-oz`. The converter handles these cases explicitly.

**Inflate:** Applied after coordinate conversion: `origin -= inflate`, `size += 2×inflate` per axis. Since inflate is uniform, the result is identical regardless of whether it is applied before or after conversion.

---

## 3. Model Conversion Pipeline

### 3.1 Pipeline Overview

```
Java Source → Text Parsing → Bone Extraction → Hierarchy Build →
Pivot Computation → Coordinate Conversion → Relative Pivot Adjustment →
.geo.json Structure → Jinja2 Template → Output Files
```

### 3.2 SRG Name Resolution

Decompiled 1.12.2 code uses SRG (Searge) obfuscated names. The converter maintains a mapping table (`SRG_MAP`) that translates SRG names to their deobfuscated equivalents:

| SRG Name | Deobfuscated | Purpose |
|---|---|---|
| `func_78793_a` | `setRotationPoint` | Set bone pivot |
| `func_78790_a` | `addBox` | Add cube to bone |
| `func_78792_a` | `addChild` | Set bone parent |
| `field_78795_f` | `rotateAngleX` | X rotation field |
| `field_78796_g` | `rotateAngleY` | Y rotation field |
| `field_78808_h` | `rotateAngleZ` | Z rotation field |
| `field_78809_i` | `mirror` | Mirror flag |
| `field_78807_k` | `showModel` | Visibility flag |
| `field_82906_o` | `offsetX` | Position offset X |
| `field_82907_q` | `offsetY` | Position offset Y |
| `field_82908_p` | `offsetZ` | Position offset Z |
| `field_78090_t` | `textureWidth` | Texture width |
| `field_78089_u` | `textureHeight` | Texture height |

The parsing uses regex patterns that match both deobfuscated (`mirror = true`) and SRG (`field_78809_i = true`) forms. This dual-pattern approach was critical for the Heblu entity, where wing skin bones had mirror flags expressed only in SRG form.

### 3.3 Bone Hierarchy Construction

1. **Field extraction:** Regex matches `public ModelRenderer <varName>;` declarations
2. **Constructor parsing:** Extracts `new ModelRenderer(this, texU, texV)`, `setRotationPoint(x,y,z)`, `addBox(...)` calls
3. **Parent assignment:** `addChild` calls establish parent-child relationships
4. **Mirror detection:** Both `.mirror = true/false` and `.field_78809_i = true/false` patterns
5. **Cycle detection:** DFS-based circular reference check prevents infinite loops

### 3.4 Pivot Computation (Absolute → Relative)

In MC 1.12.2, `setRotationPoint` values are:
- **Top-level bones:** Absolute (relative to model origin)
- **Child bones:** Relative to parent's coordinate space

The converter computes absolute pivots by walking the hierarchy (accumulating `setRotationPoint` values), then converts them to the GeckoLib relative-to-parent format:

```
rel_pivot = convert_model_pos(abs_pivot) - convert_model_pos(parent_abs_pivot)
```

For bones with `parent="root"`, the parent pivot is `[0, 24, 0]` (the root bone's pivot in GeckoLib space).

### 3.5 UV Calculation Algorithm

UV coordinates use the original 1.12.2 box dimensions **before** coordinate conversion:

```
u = textureOffsetX,  v = textureOffsetY
w = width,           h = height,         d = depth
```

| Face | UV Origin | UV Size |
|---|---|---|
| North | (u+d, v+d) | (w, h) |
| South | (u+2d+w, v+d) | (w, h) |
| West | (u, v+d) | (d, h) |
| East | (u+d+w, v+d) | (d, h) |
| Up | (u+d, v) | (w, d) |
| Down | (u+d+w, v) | (w, d) |

**Output format:** `{"uv": [u, v], "uv_size": [w, h]}` per face.

**Out-of-bounds handling:** If a face's UV start coordinate is negative (from negative texture offsets), the face is omitted from the UV dict. This causes the `.bbmodel` generator to assign `texture: -1` (no texture) and GeckoLib skips rendering that face.

### 3.6 Mirror Flag Handling

When `mirror=true` is set on a `ModelRenderer`:
- MC 1.12.2 applies `GlStateManager.scale(-1, 1, 1)` which flips the entire cube along X
- GeckoLib's `mirror` property does the same

**Critical rule:** Do NOT swap UV coordinates when `mirror=true`. Setting the mirror flag alone is sufficient — swapping UVs would cause a double-mirror. The standard UV calculation is correct as-is for mirrored cubes.

**SRG mirror parsing:** The converter matches both `.mirror = true` and `.field_78809_i = true` patterns. When a mirror flag is found on a bone, it is propagated to all boxes of that bone.

### 3.7 Inflate Parameter Handling

The optional 7th parameter of `addBox` specifies inflate (symmetric expansion):
- `origin = (ox - inflate, oy - inflate, oz - inflate)`
- `size = (w + 2×inflate, h + 2×inflate, d + 2×inflate)`

Inflate is applied **after** coordinate conversion, which is mathematically equivalent to applying before conversion for uniform inflate values.

### 3.8 Relative vs Absolute Pivot Modes

The converter operates in two stages:

1. **Absolute pivot computation:** Walks hierarchy accumulating `setRotationPoint` values (ignoring parent rotation for simplicity, since `M_model` is linear)
2. **Relative pivot adjustment:** Subtracts parent's converted absolute pivot from each bone's converted absolute pivot

This ensures all pivots in the output are relative to their parent's coordinate system, as required by GeckoLib format.

---

## 4. Animation Conversion Pipeline

### 4.1 Animation Class Taxonomy

| Class | Driver | Output | Example |
|---|---|---|---|
| **A-1** (Time-driven) | `ageInTicks` | `.animation.json` with sampled keyframes | Idle breathing, tail sway |
| **A-2** (State-dependent) | Entity state flags | Java code snippets | Flying, evolved form |
| **B** (Movement-driven) | `limbSwing`, `limbSwingAmount` | Java code snippets (`GeoBone.setRotationX/Y/Z`) | Walking legs |

### 4.2 Expression Extraction and Variable Resolution

The animation converter parses `setRotationAngles` method bodies through these stages:

1. **State body extraction:** For multi-state entities, `extract_state_body()` isolates the code for a specific state (idle, flying, evolved) by finding conditional blocks (`if (parasite.getFlyingState())`, `if (i == 0)`, etc.)

2. **Variable redefinition renaming:** `_rename_redefined_variables()` detects when variables like `f1`, `f2`, `f3` are assigned multiple times and renames subsequent definitions with versioning (`f1_v2`, `f1_v3`, etc.). References are updated to use the latest version.

3. **Helper method expansion:** `_expand_helper_methods()` inlines `swingX`, `swingZ`, `moveY` method calls:
   - `swingX(bone, speed, degree, invert, offset, weight, limbSwing, limbSwingAmount)` → `bone.field_78795_f = invert * limbSwingAmount * degree * Math.cos(limbSwing * speed + offset) + weight * limbSwingAmount`
   - `swingZ(bone, speed, degree, invert, offset, weight, limbSwing, limbSwingAmount)` → Same pattern for `field_78808_h`
   - `moveY(bone, speed, invert, f, f1, distance)` → `bone.field_82908_p = invert * MathHelper.cos(f * speed) * f1 * distance`

4. **Intermediate variable parsing:** Extracts `float f11 = MathHelper.cos(ageInTicks * 0.130998f) * 0.107215f;` style definitions.

5. **Rotation/position assignment parsing:** Matches `this.boneVar.field_78795_f = expression;` patterns.

6. **Classification:** Resolves variable dependencies to determine if an expression is time-driven (depends on `ageInTicks`) or movement-driven (depends on `limbSwing`).

### 4.3 Numerical Sampling Approach

For Class A-1 animations, the converter uses numerical sampling:

| Parameter | Default Value | Purpose |
|---|---|---|
| `sample_count` | 240 | Number of time samples over one full period |
| Period | 2π | One full cycle of the base cosine function |
| Time scale | 1.0 | Scaling factor for animation length |

For each bone axis with a time-driven expression:
1. Substitute `ageInTicks` with sampled time values (0 to 2π, step = 2π/240)
2. Evaluate the Python-translated expression at each time point
3. Apply `M_model` rotation conversion to the resulting rotation values
4. Convert from radians to degrees

### 4.4 Douglas-Peucker Keyframe Simplification

After sampling, the raw keyframe data is simplified using the Douglas-Peucker algorithm:

- **Threshold:** 0.005° (for high-precision entities like Heblu) or 0.01° (default for Kirin)
- **Preserves:** Start and end keyframes always
- **Removes:** Intermediate keyframes that lie within the threshold of a linear interpolation

The result is a compact set of keyframes that faithfully represents the animation curve within the specified tolerance.

### 4.5 Easing Curve Fitting

After DP simplification, the `EasingFitter` analyzes each keyframe pair:

1. **Velocity pattern analysis:** Compares the current segment's velocity with previous and next segments
2. **Classification:** Based on acceleration ratio:
   - Accelerating → `easeIn*` family
   - Decelerating → `easeOut*` family  
   - Both → `easeInOut*` family
3. **Strength selection:** Within each family, selects the power:
   - Low strength (ratio < 0.8) → Sine
   - Medium strength (0.8 - 1.5) → Cubic
   - High strength (> 1.5) → Quint
4. **Error threshold:** If best fit error > 0.05°, falls back to `linear`
5. **Output format:** Keyframes with easing are stored as `{"vector": value, "easing": "easeOutSine"}`

### 4.6 State-Aware Animation Extraction

For entities with multiple animation states (e.g., Heblu with idle, flying, evolved), the converter:

1. **Finds boundary markers:** Locates `if (parasite.getFlyingState())` and `if (i == 0)` blocks
2. **Extracts per-state bodies:** Combines reset code + state-specific branch + shared code (filtered)
3. **Filters shared code:** Removes conditional sub-blocks (vomit, shaking, clone) from the shared section using depth-based filtering
4. **Generates separate animations:** Each state produces an independent `.animation.json` entry

### 4.7 Variable Redefinition Handling

When a variable is assigned multiple times in the same method body:

```
f1 = cos(ageInTicks * 0.1f) * 0.3f;     // keeps f1
f1 = cos(ageInTicks * 0.09f) * 0.08f;    // renamed to f1_v2
this.bone.z = -0.1f + f1;                 // f1 → f1_v2
f1 = cos(ageInTicks * 0.0751f) * 0.06f;  // renamed to f1_v3
this.bone.x = -f1;                        // f1 → f1_v3
```

The `_rename_redefined_variables()` method processes line-by-line, tracking:
- `var_def_count`: Number of times each variable has been defined
- `var_active_name`: The current versioned name for each variable
- References in the same line as a definition use the **previous** value (Java RHS-before-assignment semantics)

### 4.8 Zero-Only Bone Filtering

After animation generation, bones with all-zero keyframe values across all axes and channels are removed:

```
For each bone in each animation:
  For each channel (rotation, position, scale):
    For each axis (x, y, z):
      Check if ALL keyframe values are within 1e-10 of zero
  If all zero: remove the bone from the animation
```

**Results for Heblu:**
- idle: 83 → 64 bones (-19)
- fly: 83 → 63 bones (-20)
- evolved_idle: 83 → 64 bones (-19)

### 4.9 Movement-Driven Animation Output

Class A-2 and B animations cannot be represented in `.animation.json` because they depend on runtime values (`limbSwing`, entity state). Instead, the converter generates Java code snippets:

```java
// Movement-driven animation for bone: rightLeg
GeoBone rightLegBone = this.getAnimationProcessor().getBone("rightLeg");
if (rightLegBone != null) {
    rightLegBone.setRotationX(
        swingComponent.getRotation(limbSwing, limbSwingAmount)
    );
}
```

These snippets are saved to `*_code_animation.java` for manual integration into the GeckoLib `codeAnimations()` method.

---

## 5. Blockbench (.bbmodel) Output

### 5.1 Format Differences from .geo.json

| Property | .geo.json | .bbmodel |
|---|---|---|
| Top-level wrapper | `{"format_version": "1.12.0", "model": {...}}` | `{"meta": {...}, "elements": [...], "outliner": [...]}` |
| UV format | `{"uv": [u,v], "uv_size": [w,h]}` per face | `{"uv": [u1,v1,u2,v2], "texture": 0}` per face |
| Bone pivot field | `"pivot"` | `"origin"` |
| Cube definition | `"origin"` + `"size"` (min corner + dims) | `"from"` + `"to"` (min + max corners) |
| Cube rotation center | Implicit (bone pivot) | Explicit `"origin": [0,0,0]` |
| Texture | Referenced by path | Embedded as base64 data URI |
| Hierarchy | Flat list with `"parent"` field | Nested tree in `"outliner"` |

### 5.2 Bone-Local Element Coordinates

In `.bbmodel`, element `from`/`to` coordinates are in **bone-local space**, directly matching the geo.json cube coordinates. No additional X-flip is applied because `.bbmodel` is Blockbench's internal format (not the `.geo.json` import path).

**Critical rule:** DO NOT apply X-flip to element positions or bone pivots in `.bbmodel`. The X-flip only occurs during `.geo.json` import (Blockbench's `parseCube`/`compileCube` functions).

### 5.3 Relative Bone Pivots

Bone pivots (`origin` field in `.bbmodel`) are **relative to the parent bone**, matching the geo.json convention. The geo.json already has relative pivots (computed by `_make_pivots_relative`), so they are used directly.

### 5.4 Rotation Convention in .bbmodel

Blockbench's internal rotation convention differs from geo.json:
- **geo.json:** `(rx, ry, rz)` in degrees
- **.bbmodel:** `(-rx, -ry, rz)` — X and Y are negated

This conversion IS needed and is applied during outliner generation:
```python
bb_rot_x = -float(rotation[0])  # X negated
bb_rot_y = -float(rotation[1])  # Y negated
bb_rot_z =  float(rotation[2])  # Z preserved
```

### 5.5 Animation Embedding

Animations in `.bbmodel` use a different structure from `.animation.json`:

```
.animation.json:                          .bbmodel:
{                                         [
  "animations": {                           {
    "anim.name": {                            "name": "anim.name",
      "bones": {                              "animators": {
        "bone": {                               "bone": {
          "rotation": {                           "keyframes": [
            "x": {"0.0": val}                       {
          }                                            "channel": "rotation",
        }                                              "data_points": [{"x":..., "y":..., "z":...}],
      }                                                "time": 0.0
    }                                                }]
  }                                            }
}                                          }
                                         ]
```

Easing information is embedded in the `data_points` entries.

### 5.6 Texture Embedding

Textures are embedded as base64 data URIs:
```json
{
  "name": "kirin",
  "source": "data:image/png;base64,<base64_encoded_png>",
  "mode": "bitmap",
  "width": 256,
  "height": 256
}
```

Faces without UV data are assigned `texture: -1` (no texture), causing Blockbench to skip rendering them.

---

## 6. Verification System

### 6.1 Vertex Comparison Algorithm

The verifier computes world-space vertex positions for both the original 1.12.2 model and the converted 1.20.1 model, then compares them:

1. For each bone, compute the bone's world transformation matrix (translation + rotation)
2. For each cube, compute 8 corner vertices in bone-local space
3. Transform vertices to world space using the bone hierarchy
4. Compare vertex positions with configurable tolerance (default: 0.1 pixels)
5. Compute similarity score = matched vertices / total vertices

The Y-offset compensation adjusts for the 24-unit vertical shift between coordinate systems.

### 6.2 UV Bounds Validation

For each face of each cube:
- `uv[0] + uv_size[0] <= texture_width`
- `uv[1] + uv_size[1] <= texture_height`
- `uv[0] >= 0` and `uv[1] >= 0`
- `uv_size[0] >= 0` and `uv_size[1] >= 0`

Violations are reported with bone name, cube index, face name, and specific issue.

### 6.3 Bone Hierarchy Checking

Verifies:
- Every parent-child pair in 1.12.2 has a corresponding pair in 1.20.1
- No orphaned bones (referencing non-existent parents)
- Root bone exists with pivot `[0, 24, 0]`

### 6.4 Animation Bone Matching

Checks that all bone names in the `.animation.json` exist in the `.geo.json` bones list. Missing bones indicate a mapping error; matched bones confirm correct bone naming.

### 6.5 Root Pivot Y-Offset Verification

The root bone must have `pivot: [0, 24, 0]` in GeckoLib space:
- `24.0` = standard entity height (internal units) from feet to top of hitbox
- This offset compensates for the MC 1.12.2 origin being at the top of the entity, while GeckoLib uses the feet as origin

### 6.6 Normal Divergence Analysis

Computes world-space normals for each face of each cube in both models and compares them. Significant divergence (>5°) indicates a rotation conversion error, particularly in multi-axis rotations.

### 6.7 Full Verification Suite (13 Checks)

| # | Check | Input Required |
|---|---|---|
| 1 | Vertex comparison | bone_data + geo_json |
| 2 | UV coordinate validation | geo_json |
| 3 | Bone hierarchy validation | bone_data + geo_json |
| 4 | Animation bone name matching | animation_json + geo_json |
| 5 | Inflate handling verification | geo_json |
| 6 | Y-offset validation | geo_json |
| 7 | Blockbench format validation | blockbench_json |
| 8 | Render effect consistency | render_effect_result + geo_json |
| 9 | Easing fitting consistency | easing_results |
| 10 | Swing component consistency | swing_result + geo_json |
| 11 | Bone visibility consistency | render_effect_result + geo_json + animation_json |
| 12 | Animation event consistency | animation_events + animation_json |
| 13 | Normal divergence analysis | bone_data + geo_json |

---

## 7. Enhancement Layer

### 7.1 Overlay Detection (`OverlayDetector`)

Detects multi-layer rendering patterns in the 1.12.2 Java source:

| Pattern | Detection Method | Output |
|---|---|---|
| LayerRenderer subclasses | Class name regex | `OverlayLayer` with type `held_item` / `armor` / `custom` |
| hurtTime overlays | Conditional regex | `OverlayLayer` with type `hurt_tint`, RGBA color |
| GlStateManager color changes | `color3f`/`color4f` regex | Color keyframe settings |
| Multiple texture binds | `bindTexture` regex | Alternative texture specifications |
| RenderType switches | `RenderType.eyes`/`entityTranslucent` regex | Emissive / translucent overlay layers |

**Output artifacts:**
- `overlay_layers`: List of detected overlay layers with trigger conditions
- `color_settings`: GeckoLib `codeAnimations`-compatible color keyframes
- `merge_hints`: Suggestions for texture merging or code animation implementation

### 7.2 First-Person / Held Item Analysis (`FirstPersonDetector`)

Detects held item rendering and first-person arm transform patterns:

- **ItemRenderer references:** Detects `ItemRenderer`, `RenderItem`, `Minecraft.getItemRenderer()`
- **Held item bones:** Matches bone names against patterns like `right_hand`, `left_arm`, `held_item`
- **ItemTransformVec3f:** Extracts display preset rotation/translation/scale values
- **Equipment slot access:** Detects `getItemBySlot`, `getItemInHand` patterns

**Output:** Display presets for each perspective, held item bone mappings with code animation snippets.

### 7.3 Particle Mounting Point Detection (`ParticleDetector`)

Detects `world.spawnParticle` calls and generates GeckoLib particle effect specifications:

1. **Full spawnParticle parsing:** Extracts particle type, position (x,y,z), spread (dx,dy,dz), count, speed
2. **Particle type mapping:** 1.12.2 `EnumParticleTypes` → 1.20.1 resource paths (e.g., `FLAME` → `minecraft:flame`)
3. **Bone inference:** Associates particles with bones based on Y-offset heuristics (head, body, feet, tail, wing, hand)
4. **State conditions:** Links particles to entity state flags (`isOnFire`, `isAttacking`, etc.)

**Output:** `particle_mount_points`, `particle_hints.json`, GeckoLib `particle_effects` keyframe placeholders.

### 7.4 Sound Keyframe Mapping (`SoundKeyframeFiller`)

Maps 1.12.2 `playSound` calls to GeckoLib `SoundKeyframe` entries:

1. **Sound event detection:** Regex matches `world.playSound(...)`, `SoundEvents.FIELD_NAME`
2. **Name mapping:** 1.12.2 `ENTITY_ZOMBIE_HURT` → 1.20.1 `minecraft:entity.zombie.hurt`
3. **Heuristic mapping:** `ENTITY_*` → `minecraft:entity.<name>`, mod-specific → `<namespace>:<name>`
4. **Timing estimation:** Distributes sounds evenly across animation length if exact timing is unavailable
5. **Entity sound methods:** Detects `getHurtSound()`, `getAmbientSound()` overrides

**Output:** `SoundKeyframe` entries with time, effect path, volume, pitch, source category.

### 7.5 Animation Naming Validation (`AnimationNamingManager`)

Manages animation naming conventions and conflict resolution:

- **Convention:** `animation.<namespace>.<entity>.<action>` (all lowercase, underscores)
- **Derivation priority:** User config → Explicit method name → State condition → Fallback
- **Conflict resolution:** Appends numeric suffixes (`_2`, `_3`) for duplicate names
- **Layer prefixes:** Base (none), overlay (`overlay_`), additive (`add_`)
- **Java interface generation:** Produces `AnimationNames.java` with constant strings

### 7.6 Animation Reference Validation (`AnimationReferenceValidator`)

Validates cross-reference integrity between controllers, animations, and naming constants:

| Check | Severity | Description |
|---|---|---|
| Missing animation | Error | Referenced but not defined in JSON |
| Orphaned animation | Warning | Defined but never referenced by any controller |
| Weight warning | Info/Warning | Unreasonable layer priority values |
| Name mismatch | Error/Warning | Constant name doesn't match JSON animation name |

---

## 8. Conversion Results

### 8.1 Kirin Entity (Sacred Beast)

| Metric | Value |
|---|---|
| **Bones** | 142 (including root) |
| **Cubes** | 141 |
| **Texture** | 256×128 |
| **Animation** | 1 (idle, Class A-1 time-driven) |
| **Verification** | ~98% accuracy confirmed |
| **Output files** | `kirin.geo.json`, `kirin_bb.geo.json`, `kirin.animation.json`, bone mapping, Java model |

### 8.2 Heblu Entity (Draconite / 邪狱龙)

| Metric | Value |
|---|---|
| **Bones** | 357 (including root) |
| **Cubes** | 356 |
| **Texture** | 1024×512 |
| **Animations** | 3 (idle, fly, evolved_idle) |
| **Animated bones (pre-filter)** | 83 per animation |
| **Animated bones (post-filter)** | idle: 64, fly: 63, evolved_idle: 64 |
| **Keyframes** | ~310 per animation |
| **UV violations** | 0 (3 wing membrane faces omitted) |
| **Mirror bones** | 6 (skin, skin_1-5) |

**Animation accuracy verification (spot checks):**
- `jointN1.x = -3.44°` — exact match
- `hjointC_1.y = -14.32°` — exact match
- `jointLW1.z = 1.15°` — exact match

### 8.3 Known Limitations and Edge Cases

| Limitation | Description | Workaround |
|---|---|---|
| **Parent rotation ignored in absolute pivot** | Absolute pivots use simple addition, not rotation-adjusted positions | Validated empirically for SRParasites models |
| **SRG name coverage** | Not all possible SRG names are in the map | Add entries to `SRG_MAP` as needed |
| **Expression evaluation** | Complex Java expressions may fail to evaluate | Manual review of `*_code_animation.java` |
| **Negative texture offsets** | Faces with negative UV are omitted | Intentional — prevents rendering artifacts |
| **Gimbal lock** | Euler angle decomposition at ±90° | Handled with standard gimbal lock formulas |
| **Non-uniform easing** | Velocity-pattern heuristic, not full curve fitting | Falls back to linear when uncertain |
| **State detection heuristics** | Depends on specific code patterns | Manual adjustment for non-standard patterns |

---

## 9. CLI Usage Guide

### 9.1 Commands

```bash
# Convert a model
python -m converter.cli convert ModelKirin.java -o output/ --identifier model.kirin

# Convert with verification
python -m converter.cli convert ModelKirin.java -o output/ --verify

# Verify an existing geo.json
python -m converter.cli verify kirin.geo.json -a kirin.animation.json -b kirin_bb.geo.json

# Show converter info
python -m converter.cli info
```

### 9.2 Convert Command Options

| Option | Default | Description |
|---|---|---|
| `input` | (required) | Input `.java` file path |
| `-o, --output` | `output` | Output directory |
| `-i, --identifier` | `model.converted` | GeckoLib model identifier |
| `--verify` | False | Run verification after conversion |

### 9.3 Verify Command Options

| Option | Default | Description |
|---|---|---|
| `geo_json` | (required) | Path to `.geo.json` file |
| `-a, --animation` | None | Path to `.animation.json` for bone name matching |
| `-b, --blockbench` | None | Path to Blockbench `.geo.json` for format validation |
| `-t, --tolerance` | 0.1 | Vertex comparison tolerance |

### 9.4 Python API Usage

```python
from model_converter import ModelConverter
from animation_converter import AnimationConverter
from bbmodel_generator import BBModelGenerator
from verifier import ModelVerifier
from easing_fitter import EasingFitter

# --- Model Conversion ---
converter = ModelConverter()
result = converter.convert(java_source, "model.kirin")

# Save outputs
with open("kirin.geo.json", "w") as f:
    f.write(converter.to_geo_json_string(result))

with open("kirin_bb.geo.json", "w") as f:
    f.write(converter.to_blockbench_geo_json_string(result))

# --- Animation Conversion ---
anim_converter = AnimationConverter(result['bone_mapping'])
anim_result = anim_converter.convert_set_rotation_angles(
    java_source,
    animation_name="idle",
    sample_count=240,
    dp_threshold=0.005,
    state="idle"
)

# --- Easing Fitting ---
easing_fitter = EasingFitter(error_threshold=0.05)
anim_json = anim_result['animation_json']
anim_json = easing_fitter.apply_easing_to_animation_json(anim_json, animation_bones)

# --- BBModel Generation ---
bbmodel_gen = BBModelGenerator()
bbmodel = bbmodel_gen.generate(
    result['geo_json'],
    anim_json=anim_json,
    texture_path="kirin.png",
    texture_name="kirin"
)
bbmodel_gen.save(bbmodel, "kirin.bbmodel")

# --- Verification ---
verifier = ModelVerifier(tolerance=0.1)
report = verifier.verify(bone_data, result['geo_json'])
print(f"Similarity: {report['similarity_score']*100:.2f}%")

# Full verification suite
full_report = verifier.verify_full(
    bone_data_1122=bone_data,
    geo_json_1201=result['geo_json'],
    animation_json=anim_json,
    blockbench_json=bb_json
)
```

### 9.5 Runner Scripts

For complete end-to-end conversion of specific entities:

```bash
# Kirin entity (Layer 1 Enhanced, 21 steps)
python run_kirin.py --mode both --verify

# Heblu entity (12 steps)
python run_heblu.py --mode game --verify
```

The Kirin runner includes all enhancement layer modules (overlay, first-person, particle, sound, naming). The Heblu runner includes multi-state animation conversion and zero-only bone filtering.

### 9.6 Configuration

**Animation naming config** (`animation_naming.json`):
```json
{
  "namespace": "srparasites",
  "entity_name": "kirin",
  "overrides": {
    "idle": "idle",
    "walk": "walk",
    "attack": "attack"
  },
  "layer_prefixes": {
    "base": "",
    "overlay": "overlay_",
    "additive": "add_"
  }
}
```

---

## 10. Troubleshooting

### 10.1 Common Issues and Solutions

#### Wing/mirrored parts appear incorrectly positioned

**Symptom:** Symmetrical bones (e.g., left/right wings) have identical rotations instead of mirrored ones.

**Cause:** SRG mirror flag (`field_78809_i`) not parsed.

**Solution:** Ensure `mirror_srg_pattern` is active in `_parse_constructor()`. Check that bones with `mirror=true` have the flag in the output `.geo.json`.

#### Animations contain zero-only bones

**Symptom:** Animation JSON has bones with all-zero keyframes, inflating file size.

**Solution:** Run zero-only bone filtering (Step 8 in `run_heblu.py`):
```python
for bone_name, bone_data in list(bones_data.items()):
    # Check if all values across all channels/axes are ~0
    if all_zero:
        del bones_data[bone_name]
```

#### UV out-of-bounds violations

**Symptom:** Verifier reports UV coordinates exceeding texture dimensions.

**Cause:** Negative texture offsets from `ModelRenderer` constructor produce negative UV start values.

**Solution:** Already handled — faces with negative UV start are omitted. Verify no violations remain by running the verifier.

#### Animation bones missing from geo.json

**Symptom:** Animation references bone names that don't exist in the model.

**Cause:** Bone variable name mapping error.

**Solution:** Check `*_bone_mapping.json` for mapping inconsistencies. Ensure all Java variable names are correctly mapped.

#### Multi-axis rotation appears wrong

**Symptom:** Bones with non-zero rotation on multiple axes appear misaligned.

**Cause:** Simple angle negation (`(rx, -ry, -rz)`) is inaccurate for multi-axis rotations.

**Solution:** The converter automatically uses `convert_model_rotation_order()` for multi-axis rotations. Check the warning log for single-axis fallback cases.

#### Variable redefinition causes wrong animation values

**Symptom:** Animation keyframes don't match expected values from manual calculation.

**Cause:** Variables like `f1` redefined multiple times in the method body; later definitions overwrite earlier ones in the dict.

**Solution:** `_rename_redefined_variables()` handles this. Ensure it runs before `_parse_intermediate_variables()` in the pipeline.

### 10.2 Debug Workflow

1. **Enable verification:** Use `--verify` flag with the CLI or runner scripts
2. **Check bone mapping:** Inspect `*_bone_mapping.json` for correct Java var → bone name mappings
3. **UV inspection:** Run `verifier.validate_uv_coordinates()` standalone
4. **Animation spot-check:** Compare specific bone values against manual Java evaluation
5. **Blockbench preview:** Open `.bbmodel` in Blockbench to visually verify geometry and animation
6. **Vertex comparison:** Run `verifier.verify()` with bone_data for exact positional accuracy
7. **Normal divergence:** Run `verifier.check_normals()` for rotation accuracy (threshold: 5°)
8. **Enable Python warnings:** Set `PYTHONWARNINGS=all` to see multi-axis rotation warnings from `core_math.py`

---

*Generated by MinecraftModelMigrator-Pro Technical Writer Agent*
*Last updated: 2026-03-05*
