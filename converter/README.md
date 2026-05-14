# MinecraftModelMigrator-Pro

Converts Minecraft 1.12.2 entity models (ModelBase/ModelRenderer) to GeckoLib 1.20.1 format (.geo.json + .animation.json).

## Overview

This tool automates the migration of Java-based Minecraft entity models from the 1.12.2 modding era (using `ModelBase` and `ModelRenderer`) to the modern GeckoLib 1.20.1 format used by Forge mods. It handles the complete coordinate system transformation (Y-down RH → Y-up LH), preserves bone hierarchies, computes UV coordinates, and converts animations.

**Reference Model**: Kirin entity from SRParasites 1.10.4

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              MinecraftModelMigrator-Pro              │
│            MC 1.12.2 → GeckoLib 1.20.1              │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────┐       ┌───────────────────┐       │
│  │  Parser       │       │   CoreMath         │       │
│  │  Plugin       │──────▶│   M_model           │       │
│  │  ┌──────────┐│       │   diag(1, -1, -1)  │       │
│  │  │ Java     ││       └────────┬───────────┘       │
│  │  │ ASM      ││                │                    │
│  │  └──────────┘│       ┌────────▼───────────┐       │
│  └──────────────┘       │  ModelConverter     │       │
│                         │  ├─ Pivot flip      │       │
│  ┌──────────────┐       │  ├─ Rotation Xform │       │
│  │  Template     │◀──────│  ├─ Cube origin    │       │
│  │  Engine       │       │  ├─ UV calculation  │       │
│  │  (Jinja2)    │       │  └─ Inflate handle  │       │
│  └──────────────┘       └────────┬───────────┘       │
│                         ┌────────▼───────────┐       │
│                         │ AnimConverter       │       │
│                         │  ├─ Class A-1 (time)│       │
│                         │  ├─ Class A-2 (state)│      │
│                         │  └─ Class B (move) │       │
│                         └────────┬───────────┘       │
│                         ┌────────▼───────────┐       │
│                         │   Verifier          │       │
│                         │   ├─ Vertex compare │       │
│                         │   ├─ UV bounds      │       │
│                         │   ├─ Hierarchy check│       │
│                         │   ├─ Anim matching  │       │
│                         │   ├─ Inflate verify │       │
│                         │   ├─ Y-offset check │       │
│                         │   └─ Blockbench fmt │       │
│                         └────────────────────┘       │
└─────────────────────────────────────────────────────┘
```

## Module Descriptions

### `core_math.py` — Coordinate System Transformation Library

Mathematical foundation of the conversion. Implements the transformation matrix `M_model = diag(1, -1, -1)` that converts from MC 1.12.2 (Y-down, right-hand) to GeckoLib 1.20.1 (Y-up, left-hand).

Key functions:
- `convert_model_pos(x, y, z)` → `(x, -y, -z)` — Pivot/position conversion
- `convert_model_rot(rx, ry, rz)` → `(rx, -ry, -rz)` — Single-axis rotation conversion
- `convert_model_rotation_order(rx, ry, rz)` — Multi-axis rotation via M_model similarity transform
- `convert_model_cube_origin(ox, oy, oz, w, h, d)` → `(ox, -(oy+h), -(oz+d))` — Cube origin (min corner)
- `convert_model_cube_size(w, h, d)` → `(w, h, d)` — Dimensions preserved

### `model_converter.py` — Model Conversion Engine

Parses 1.12.2 Java source (decompiled, SRG-obfuscated names) and produces GeckoLib .geo.json format.

Features:
- SRG name resolution (`func_78793_a` → `setRotationPoint`, etc.)
- Hybrid parsing: javalang AST + text scanning fallback
- UV calculation using original 1.12.2 formulas
- Dual output: GeckoLib game format + Blockbench preview format
- Jinja2 template-based output generation
- Mirror flag preservation
- Inflate parameter handling

### `animation_converter.py` — Animation Conversion Engine

Converts hardcoded Java animations to GeckoLib .animation.json format.

Animation Classes:
- **Class A-1** (time-driven): `ageInTicks` dependent → numerical sampling → .animation.json
- **Class A-2** (entity-state): State-dependent (e.g., cosmical/shaking) → Java code snippets
- **Class B** (movement-driven): `limbSwing` dependent → Java code snippets

Processing pipeline:
1. Extract intermediate variables and rotation assignments
2. Replace Java math functions with Python equivalents
3. Sample rotation values over time period (2π)
4. Apply coordinate system rotation transform (M_model)
5. Simplify keyframes with Douglas-Peucker algorithm
6. Generate GeckoLib animation JSON

### `verifier.py` — Offline Rendering Verification System

Mathematically verifies conversion accuracy by computing world-space vertex positions for both models and comparing them.

Verification checks:
1. **Vertex comparison** — World-space position matching with Y-offset compensation
2. **UV validation** — Texture bounds checking for all face UVs
3. **Bone hierarchy** — Parent-child relationship preservation
4. **Animation matching** — Animation bone names exist in geo.json
5. **Inflate handling** — Correct symmetric expansion of inflated cubes
6. **Y-offset** — Root bone pivot at [0, 24, 0]
7. **Blockbench format** — Format-specific validation

### `parsers/base_parser.py` — Plugin Architecture

Abstract base classes for extending the converter:
- `BaseModelSourceParser` — For new input formats (.class bytecode, etc.)
- `BaseAnimationSourceParser` — For new animation source formats
- `BaseOutputFormatter` — For new output targets

### `templates/` — Jinja2 Templates

- `geo_model.game.json.j2` — GeckoLib game format template
- `geo_model.blockbench.json.j2` — Blockbench preview format template

## Usage

### Command Line (CLI)

```bash
# Convert a model
python -m converter.cli convert ModelKirin.java -o output/

# Convert and verify
python -m converter.cli convert ModelKirin.java -o output/ --verify

# Verify an existing geo.json
python -m converter.cli verify kirin.geo.json

# Show converter info
python -m converter.cli info
```

### Python API

```python
from model_converter import ModelConverter
from verifier import ModelVerifier

# Convert
converter = ModelConverter()
result = converter.convert(java_source, "model.kirin")

# Save outputs
with open("kirin.geo.json", "w") as f:
    f.write(converter.to_geo_json_string(result))

with open("kirin_bb.geo.json", "w") as f:
    f.write(converter.to_blockbench_geo_json_string(result))

# Verify
verifier = ModelVerifier(tolerance=0.1)
report = verifier.verify(bone_data, result['geo_json'])
print(f"Similarity: {report['similarity_score']*100:.2f}%")
```

### Full Verification Suite

```python
verifier = ModelVerifier(tolerance=0.1)
results = verifier.verify_full(
    bone_data_1122=bone_data,
    geo_json_1201=geo_json,
    animation_json=anim_json,
    blockbench_json=bb_json
)
report_text = verifier.generate_verification_report(results)
print(report_text)
```

## Coordinate System

| Property | MC 1.12.2 | GeckoLib 1.20.1 |
|----------|-----------|-----------------|
| Y Axis | Down (0=top) | Up (0=feet) |
| Handedness | Right-hand (Z into screen) | Left-hand (Z out of screen) |
| Origin | Top of hitbox | Entity feet |
| Transform | `M_model = diag(1, -1, -1)` | — |
| Root pivot | — | [0, 24, 0] |

## Output Files

| File | Format | Description |
|------|--------|-------------|
| `kirin.geo.json` | GeckoLib game | Runtime format for GeckoLib 4.x |
| `kirin_bb.geo.json` | Blockbench preview | Visual preview in Blockbench |
| `kirin.animation.json` | GeckoLib animation | Class A-1 idle animation |
| `kirin_bone_mapping.json` | Reference | Java var → bone name mapping |
| `KirinGeoModel.java` | Java template | 1.20.1 GeoModel implementation |

## Dependencies

- Python 3.8+
- numpy — Matrix operations for vertex computation
- jinja2 — Template-based output formatting
- javalang (optional) — Java source AST parsing

## License

Part of the MinecraftModelMigrator-Pro project.
