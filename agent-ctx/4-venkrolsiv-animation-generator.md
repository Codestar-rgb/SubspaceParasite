# VenkrolSIV Animation Generator Task

## Task Summary
Created `/home/z/my-project/converter/venkrolSIV_animation_generator.py` - a Python animation generator that converts MC 1.12.2 Java animation code to GeckoLib 1.20.1 animation format for the venkrolSIV entity.

## Key Design Decisions

1. **Import-based sharing**: Instead of duplicating shared functions (DP simplification, M_MODEL conversion, loop continuity, boundary enrichment, etc.), the generator imports them from `heblu_animation_generator.py`. This ensures consistency and reduces code duplication.

2. **Quality parameters**: Uses the same quality settings as heblu:
   - 120 fps sampling rate
   - dp_epsilon=0.03 for Douglas-Peucker simplification
   - 10% boundary fraction for loop enrichment
   - Pipeline: sample → enrich → enforce_loop_continuity → build

3. **Animation states**: Two states implemented:
   - `idle` (parasiteStatus >= 0): Body sway + dorsal/middle tentacle joints + tentacle tips
   - `dormant` (parasiteStatus == 3): Same structure but ~25x smaller amplitudes, no tentacle tips

4. **BBModel injection**: Instead of regenerating the entire .bbmodel from geo.json, the generator reads the existing .bbmodel and replaces only the animations section. This preserves the model structure including the [180, 180, 180] root bone rotation.

5. **Output paths**:
   - Source bbmodel: `MROLF-TGNBF/deterrent/venkrolSIV.bbmodel`
   - Output bbmodel: `MROLF-TGNBF/derived/venkrolSIV.bbmodel`
   - Animation JSON: `db/venkrolSIV.animation.json`

## Verification Results

- Idle animation: 69 bones, 1541 keyframes, duration 6.3s
- Dormant animation: 37 bones, 706 keyframes, duration 6.25s
- Total keyframes in bbmodel: 2247
- Loop continuity verified: first and last keyframes match perfectly
- Model structure preserved: 204 elements, 205 groups, 1 texture
- Root bone rotation [180, 180, 180] correctly preserved
