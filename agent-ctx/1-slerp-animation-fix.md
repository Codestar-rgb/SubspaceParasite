# Task 1: Fix head/neck animation stuttering with SLERP resampling

## Summary
Replaced the naive per-keyframe Euler angle conversion in `_convert_animation_rotations()` with quaternion-based SLERP resampling to fix head/neck animation stuttering for multi-axis rotations.

## Changes Made
- **File**: `/home/z/my-project/converter/bbmodel_generator.py`
  - Replaced `_convert_animation_rotations()` (lines 232-257) with new quaternion-based SLERP resampling implementation
  - Added `_convert_rotation_keyframes_simple()` helper method for single-keyframe/short channels
  - `_convert_rotation_to_bbmodel()` left unchanged (used for static bone rotations)

## Verification
- Re-ran heblu converter: `cd /home/z/my-project/converter && python3 run_heblu.py`
- All 8 animation states generated successfully
- Neck bone keyframe counts increased (idle: 21→140, fly: 24→189, vomit: 38→310)
- Output files synced to db/ and public/converted/
- Lint clean, dev server running
