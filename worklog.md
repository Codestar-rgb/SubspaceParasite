# Work Log: Walk Animation Converter v18 — Critical Regression Fix

**Date:** 2025-03-04
**File:** `converter/bbmodel_animation_converter_v18.py`
**Root Cause:** Walk keyframe normalization (Step 11f-v19) produced evenly-spaced keyframes, but the JSON builder's DP simplification ran AFTER normalization and re-introduced uneven spacing, causing stuttering/flashing/frame drops.

## Fixes Applied

### Fix 1: Skip DP Simplification for Already-Normalized Walk Keyframes
- Added `already_normalized: bool = False` parameter to `build()` method (line ~5977)
- Added `already_normalized: bool = False` parameter to `_build_bone_entry()` method (line ~6038)
- In `_build_bone_entry()`, when `is_walk_anim=True and already_normalized=True`, skip DP simplification entirely and use keyframes as-is (`simplified = list(keyframes)`)
- Propagated `already_normalized` from `build()` → `_build_bone_entry()`

### Fix 2: Skip `_enforce_keyframe_velocity()` for Already-Normalized Walks
- Modified the velocity enforcement condition in `_build_bone_entry()`:
  - Old: `if loop_mode == "loop" and len(simplified) >= 3 and duration > 0:`
  - New: `if (loop_mode == "loop" and len(simplified) >= 3 and duration > 0 and not (is_walk_anim and already_normalized)):`
- Rationale: Normalization already ensures proper C0 continuity and velocity matching; re-enforcing would add extra keyframes that break even spacing.

### Fix 3: Reduce Normalization Threshold
- Changed ratio threshold in `_normalize_walk_keyframes()` from `4.0` to `2.0`
- Even a ratio of 2.0–4.0 can cause visible stuttering with catmullrom interpolation
- Line ~9955: `if ratio < 2.0 and min_sp >= 0.02:`

### Fix 4: Ensure Catmullrom Interpolation for Walk Animations
- Modified `kf_dict` construction in `_build_bone_entry()` for walk animations
- Walk animations now output keyframes in catmullrom format:
  ```json
  "0.0000": {"post": -7.49, "lerp_mode": "catmullrom"}
  ```
- Non-walk animations continue using the simple format: `"0.0000": -7.49`

### Fix 5: Walk Animation Minimum Keyframe Density
- Changed `walk_min_output_keyframes` default from `12` to `16` in `ConverterConfig`
- Ensures at least 16 keyframes per channel for smooth playback at 25 FPS over a typical 0.667s walk cycle

### Step 11f-v19: Pass already_normalized=True
- Updated the `build()` call after walk keyframe normalization (line ~7626) to pass `already_normalized=True`
- This ensures the normalized keyframes bypass DP simplification and velocity enforcement

### Batch Config Update
- Updated `batch_convert_all.py` line 266: `walk_min_output_keyframes=16`

## Verification
- Both `bbmodel_animation_converter_v18.py` and `batch_convert_all.py` pass Python import checks with no syntax errors.

## Files Modified
1. `/home/z/my-project/converter/bbmodel_animation_converter_v18.py` — All 5 fixes + Step 11f-v19 update
2. `/home/z/my-project/converter/batch_convert_all.py` — `walk_min_output_keyframes=16`

## Files NOT Modified (as instructed)
- `bbmodel_to_geo.py`
- `core_math.py`

---
Task ID: 2
Agent: Main Agent
Task: Fix walk animation converter v18 - comprehensive v20 upgrade

Work Log:
- Identified ROOT CAUSE: Walk normalization (Step 11f-v19) produced evenly-spaced keyframes, but JSON builder's DP simplification ran AFTER normalization and re-introduced uneven spacing
- Fixed by adding `already_normalized` parameter to `build()` and `_build_bone_entry()` methods - skips DP simplification when True
- Fixed `_enforce_keyframe_velocity()` skip for already-normalized walks
- Reduced normalization threshold ratio from 4.0 to 2.0 in `_normalize_walk_keyframes()`
- Added catmullrom interpolation output format for walk keyframes
- Changed `walk_min_output_keyframes` from 12 to 16 for smoother playback
- Fixed CRITICAL BUG: Catmullrom dict values ({"post": val, "lerp_mode": "catmullrom"}) were not being handled by static/empty animation detection, causing walk animations to be incorrectly purged as "truly static" or "truly empty"
- Added `_numeric_val()` static method to handle both plain number and dict keyframe values
- Fixed all 8+ instances of `isinstance(val, (int, float))` checks throughout the converter to use `_numeric_val()`
- Re-batch converted all 154 models with 0 errors
- Verified walk animation quality: 73 walk animations, ratio=1.00 (perfect even spacing), C0=0 (perfect loop), 97.3% catmullrom interpolation

Stage Summary:
- Walk animation spacing ratio: 1.00 (was 2.0-9.2)
- Walk animation C0 errors: 0/73
- Catmullrom interpolation: 97.3% of walk channels
- All 154 models converted successfully with 0 errors
- Frontend updated to v20
