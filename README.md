# SubspaceParasite

MDO-SRP Super Converter — GeckoLib → Blockbench `.bbmodel` conversion pipeline for the SRParasites (Scape and Run Parasites) mod.

## Directory Structure

```
SubspaceParasite/
├── batch/              # Batch conversion scripts
│   └── mdo_srp.py      # MDO-SRP batch converter entry point
├── frontend/           # Input parsers
│   ├── geckolib_parser.py  # GeckoLib geo.json + animation.json parser
│   └── axis_tracker.py     # Per-axis explicit/default tracking
├── engine/             # Animation processing pipeline
│   ├── carry_forward.py    # Interpolation-aware carry-forward
│   ├── loop_extender.py    # Multi-cycle loop extension
│   ├── catmullrom_baker.py # CatmullRom → linear baking
│   ├── idle_walk_merger.py # Idle+walk animation merging
│   ├── walk_enhancer.py    # Synthetic walk leg rotation
│   └── ...                 # Additional pipeline stages
├── backend/            # Output exporters
│   └── bbmodel_exporter.py # .bbmodel format exporter
├── core/               # Core libraries
│   ├── types.py            # Unified IR type definitions
│   ├── math_utils.py       # UUID, rounding, LCM, autocorrelation
│   ├── quaternion.py       # Full quaternion math + SLERP
│   └── coords.py           # MC 1.12.2 → GeckoLib transforms
├── config.py           # Configuration constants
├── run.py              # CLI runner
├── models/             # Converted .bbmodel files (168 models)
│   ├── abomination/    # Abomination composites
│   ├── adapted/        # Adapted primitive variants
│   ├── ancient/        # Ancient parasitic entities
│   ├── awakened/       # Awakened variants
│   ├── crude/          # Crude parasitic forms
│   ├── derived/        # Derived evolved forms
│   ├── deterrent/      # Deterrent-stage entities
│   ├── feral/          # Feral infected variants
│   ├── focused/        # Focused combat variants
│   ├── hijacked/       # Hijacked host bodies
│   ├── inborn/         # Innate parasitic entities
│   ├── infected/       # Infected host creatures
│   ├── misc/           # Miscellaneous entities
│   ├── primitive/      # Base primitive forms
│   ├── projectile/     # Projectile entities
│   └── pure/           # Pure evolved forms
└── REPORT.md           # Detailed technical report
```

## Converter Pipeline (v4.0)

The super converter uses a **multi-stage animation pipeline**:

```
Parse → CarryForward → LoopExtend → CatmullRomBake → IdleWalkMerge → WalkEnhance → Export
```

### Key Features

- **Interpolation-Aware Carry-Forward**: Fills missing axes at merged time points using CatmullRom interpolation from each axis's own time series (not simple step-function carry-forward)
- **Loop Extension**: Short loop animations are extended to 3–8x cycles to reduce CatmullRom boundary distortion frequency
- **CatmullRom Baking**: All CatmullRom curves are baked into dense linear keyframes (20fps) to eliminate Blockbench's CatmullRom loop boundary bug
- **Idle-Walk Merging**: Merges idle animation data (arm/tentacle sway) into walk animations to simulate GeckoLib's animation layering
- **Walk Enhancement**: Adds synthetic leg rotation to walk animations that are overlay-only (the original mod relies on Java-side programmatic leg rotation)
- **Quaternion Rotation Handling**: Proper shortest-path rotation normalization without gimbal lock
- **UV Normalization**: Correct handling of negative `uv_size` values in source data
- **Duplicate Bone Merging**: Handles source models with duplicate bone entries

### Usage

```bash
# Single model conversion
python3 run.py single --geo model.geo.json --anim model.animation.json --tex model.png --output model.bbmodel

# Batch conversion (MDO-SRP)
python3 batch/mdo_srp.py
```

## Model Format

All models are in **Blockbench .bbmodel** format (Bedrock model format), compatible with Blockbench 4.x+.

Each file contains:
- Model geometry (bones, cubes, UV mapping)
- Animations (keyframe-based with linear interpolation after CatmullRom baking)
- Embedded texture (base64 PNG)

## Source Data

Source models from: [Qom-Inseac (SRParasites)](https://github.com/Codestar-rgb/Qom-Inseac)

## Version

Super Converter v4.0 — Walk Animation Completeness Release
