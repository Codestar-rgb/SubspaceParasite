# Task: AnimForge v19 Animation Converter

## Summary
Created the complete AnimForge v19 component-based animation converter for Minecraft models at `/home/z/my-project/converter/animforge/`. The converter transforms Blockbench .bbmodel animation data to GeckoLib .animation.json format for MC 1.20.1.

## Files Created (3,931 lines total)
- `__init__.py` - Package init with AnimForgeConverter export
- `core/config.py` (119 lines) - AnimForgeConfig with ~25 parameters
- `core/parser.py` (266 lines) - BBModelParser with double-keyframe glitch removal
- `core/profile.py` (124 lines) - AnimCategory, BoneRole, BoneProfile, AnimationProfile
- `core/profiler.py` (550 lines) - AnimationProfiler with autocorrelation, walk phase detection, content hash
- `pipelines/base.py` (686 lines) - PipelineBase with Catmull-Rom, C0, C1, DP simplification
- `pipelines/walk.py` (289 lines) - WalkPipeline with 8-step processing
- `pipelines/idle.py` (97 lines) - IdlePipeline with gentle processing
- `pipelines/generic.py` (116 lines) - GenericPipeline for attack/evolved/death/sleep/unknown
- `pipelines/router.py` (59 lines) - PipelineRouter (Walk > Idle > Generic)
- `stages/dedup.py` (117 lines) - DedupEngine with content-hash grouping
- `stages/differentiator.py` (254 lines) - AnimationDifferentiator for cross-category dupes
- `quality/gate.py` (224 lines) - QualityGate with density/amplitude/C0 checks
- `quality/report.py` (240 lines) - QualityReporter with health score
- `output/geckolib.py` (312 lines) - GeckoLibSerializer with coordinate transforms
- `main.py` (463 lines) - AnimForgeConverter orchestrator + CLI

## Key Design Decisions
1. Coordinate transforms applied ONLY at serialization: rotation (rx,ry,rz)→(-rx,-ry,rz), position (px,py,pz)→(-px,py,pz)
2. Walk pipeline preserves complete cycles - never extends when start≈end
3. C1 uses global cubic with distortion check, fallback to transition zone blend
4. DP simplification protects walk leg extrema and first/last keyframes
5. Differentiator applied AFTER dedup but BEFORE pipeline processing
6. All floats rounded to 4 decimal places for time and values

## Tests Verified
- All imports work correctly
- End-to-end conversion pipeline (walk, idle, attack, evolved, generic)
- Dedup + differentiation of byte-identical cross-category animations
- Coordinate transform correctness for both rotation and position
- Double-keyframe glitch removal
- C0 continuity enforcement for loop animations
- File I/O (read .bbmodel, write .animation.json)
- Edge cases (empty animations, string floats, deep copy isolation, loop mode mapping)
