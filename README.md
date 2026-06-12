# SubspaceParasite

MDO-SRP (Multi-Dimensional Object - Symbol Resolution Pipeline) converted models and converter pipeline for the SRParasites mod.

## Directory Structure

```
SubspaceParasite/
├── converter/          # Super Converter pipeline (Python)
│   ├── core/          # Core types, math, quaternion, coordinates
│   ├── frontend/      # GeckoLib geo.json/animation.json parser
│   ├── engine/        # Animation processing pipeline (AST Symbol Compiler)
│   ├── backend/       # .bbmodel exporter
│   ├── batch/         # Batch conversion scripts
│   ├── config.py      # Configuration constants
│   └── run.py         # CLI entry point
├── models/            # Converted .bbmodel files (168 models)
│   ├── abomination/   # Abomination composites
│   ├── adapted/       # Adapted primitive variants
│   ├── ancient/       # Ancient parasitic entities
│   ├── awakened/      # Awakened variants
│   ├── crude/         # Crude parasitic forms
│   ├── derived/       # Derived evolved forms
│   ├── deterrent/     # Deterrent-stage entities
│   ├── feral/         # Feral infected variants
│   ├── focused/       # Focused combat variants
│   ├── hijacked/      # Hijacked host bodies
│   ├── inborn/        # Innate parasitic entities
│   ├── infected/      # Infected host creatures
│   ├── misc/          # Miscellaneous entities
│   ├── primitive/     # Base primitive forms
│   ├── projectile/    # Projectile entities
│   └── pure/          # Pure evolved forms
└── REPORT.md          # Detailed conversion report
```

## Converter Pipeline

The super converter uses the **AST Symbol Compiler** architecture:

```
Parse → Validate → SymbolCompile → PeriodLock → SymbolEvaluate → LoopAlign → RotNormalize → Export
```

### Key Features

- **AST Symbol Compiler**: Selects interpolation mode per-segment BEFORE evaluation, eliminating the chicken-and-egg problem of the old pipeline where carry-forward used wrong interpolation
- **Overshoot Clamping**: CatmullRom expressions are clamped to `[min(v1,v2) - margin, max(v1,v2) + margin]` to prevent extreme overshooting
- **LCM-Based Period Lock**: Uses least common multiple of per-curve periods for consistent loop alignment
- **Quaternion Rotation Handling**: Proper shortest-path rotation normalization without gimbal lock
- **Duplicate Bone Merging**: Handles source models with duplicate bone entries by merging cubes and selecting the correct rotation

### Usage

```bash
# Single model conversion
python3 converter/run.py single --geo model.geo.json --anim model.animation.json --tex model.png --output model.bbmodel

# Batch conversion (MDO-SRP)
python3 converter/batch/mdo_srp.py
```

## Model Format

All models are in **Blockbench .bbmodel** format (v5.0, Bedrock model format), compatible with Blockbench 4.x+.

Each file contains:
- Model geometry (bones, cubes, UV mapping)
- Animations (keyframe-based with CatmullRom/linear interpolation)
- Embedded texture (base64 PNG)

## Source Data

Source models from: [Qom-Inseac (SRParasites)](https://github.com/Codestar-rgb/Qom-Inseac)

## Version

Super Converter v2.1 (AST Symbol Compiler Architecture)
