#!/usr/bin/env python3
"""
Super Architecture — Loop Animation Multi-Cycle Extension
==========================================================

Extend short loop animations to multiple cycles to avoid Blockbench
CatmullRom loop boundary distortion.

PROBLEM:
  Blockbench's Bedrock format does NOT enable `animation_loop_wrapping`,
  which means the CatmullRom interpolation at the loop boundary uses
  WRONG control points (second-to-last keyframe as "before_plus" for the
  first segment, second keyframe as "after_plus" for the last segment).
  
  With THREE.SplineCurve chord-length parameterization, this causes
  severe tangent distortion at the loop boundary — the spline briefly
  deviates in the wrong direction, creating a visible "flash to origin"
  or "pop" at each loop cycle.

SOLUTION:
  Extend short loop animations to multiple cycles (3x or more), matching
  the reference SubspaceParasite converter's strategy. This:
  
  1. Reduces loop boundary frequency (e.g., 0.67s → 2.0s per cycle)
  2. Places the actual loop boundary far from dense keyframe regions
  3. Makes CatmullRom wrapping distortion negligible (control points
     from the opposite end of the animation are much closer in time)

REFERENCE:
  The heblu-SubSRP.bbmodel reference converter extends animations:
  - idle: 2.3271s → 6.9813s (3x)
  - attack: 2.0944s → 8.3776s (4x)
  - fly: 3.1416s → 4.7124s (1.5x)

ALGORITHM:
  For each "loop" animation with length <= MIN_LENGTH_FOR_EXTENSION:
    1. Compute the number of cycles needed (at least MIN_CYCLES)
    2. Replicate keyframes for each additional cycle with time offset
    3. Update animation length to cycles * source_length
    4. Avoid duplicate keyframes at cycle boundaries
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.types import (
    AnimationIR,
    AxisValue,
    BoneAnimationIR,
    KeyframeData,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Minimum animation length in seconds. Animations shorter than this
# that are set to "loop" will be extended.
MIN_LENGTH_FOR_EXTENSION: float = 3.0

# Minimum number of cycles for extended animations.
MIN_CYCLES: int = 3

# Maximum number of cycles (safety cap to avoid huge files).
MAX_CYCLES: int = 8

# Target extended length in seconds (we try to get at least this long).
TARGET_EXTENDED_LENGTH: float = 6.0


# ---------------------------------------------------------------------------
# Cycle computation
# ---------------------------------------------------------------------------

def _compute_cycle_count(source_length: float) -> int:
    """Compute how many cycles to extend an animation to.
    
    Args:
        source_length: Original animation length in seconds.
        
    Returns:
        Number of cycles (integer, at least MIN_CYCLES).
    """
    if source_length <= 0:
        return 1
    
    # Compute cycles needed to reach target length
    cycles_for_target = int(TARGET_EXTENDED_LENGTH / source_length) + 1
    
    # Ensure minimum
    cycles = max(cycles_for_target, MIN_CYCLES)
    
    # Cap at maximum
    cycles = min(cycles, MAX_CYCLES)
    
    return cycles


# ---------------------------------------------------------------------------
# Single animation extension
# ---------------------------------------------------------------------------

def extend_animation(anim: AnimationIR) -> AnimationIR:
    """Extend a loop animation to multiple cycles.
    
    Only extends animations that are:
      - Loop mode = "loop"
      - Length <= MIN_LENGTH_FOR_EXTENSION
      
    For other animations, returns the input unchanged.
    
    Args:
        anim: The AnimationIR to extend.
        
    Returns:
        New AnimationIR with extended keyframes (or original if not extended).
    """
    # Only extend loop animations
    if anim.loop != "loop":
        return anim
    
    # Only extend short animations
    source_length = anim.length
    if source_length <= 0:
        return anim
    
    if source_length > MIN_LENGTH_FOR_EXTENSION:
        return anim
    
    # Compute cycle count
    cycles = _compute_cycle_count(source_length)
    
    if cycles <= 1:
        return anim
    
    new_length = source_length * cycles
    
    # Extend each bone's keyframes
    new_bones: Dict[str, BoneAnimationIR] = {}
    
    for bone_name, bone_anim in anim.bones.items():
        new_keyframes = _extend_bone_keyframes(
            bone_anim.keyframes, source_length, cycles
        )
        new_bones[bone_name] = BoneAnimationIR(
            bone_name=bone_name,
            keyframes=new_keyframes,
        )
    
    return AnimationIR(
        name=anim.name,
        loop=anim.loop,
        length=new_length,
        bones=new_bones,
        period=anim.period,
    )


def _extend_bone_keyframes(
    keyframes: List[KeyframeData],
    source_length: float,
    cycles: int,
) -> List[KeyframeData]:
    """Extend keyframes for one bone across multiple cycles.
    
    Cycle 1: original keyframes (t=0 to t=source_length)
    Cycle 2+: keyframes shifted by cycle_offset, excluding t=0 duplicates
    (since the last keyframe of cycle N has the same values as the first
    keyframe of cycle N+1, for seamless looping).
    
    Args:
        keyframes: Original keyframes for one bone.
        source_length: Original animation length in seconds.
        cycles: Number of cycles to extend to.
        
    Returns:
        New list of keyframes covering all cycles.
    """
    if not keyframes or cycles <= 1:
        return list(keyframes)
    
    result: List[KeyframeData] = []
    
    # Sort keyframes by time for consistent processing
    sorted_kfs = sorted(keyframes, key=lambda kf: (kf.time, kf.channel))
    
    for cycle_idx in range(cycles):
        offset = cycle_idx * source_length
        
        for kf in sorted_kfs:
            new_time = kf.time + offset
            
            # For cycles after the first, skip the t=0 keyframe
            # (it's a duplicate of the previous cycle's last keyframe)
            if cycle_idx > 0 and kf.time < 1e-9:
                continue
            
            # Create new keyframe with shifted time
            new_kf = KeyframeData(
                time=new_time,
                channel=kf.channel,
                x=kf.x,
                y=kf.y,
                z=kf.z,
                easing=kf.easing,
                interpolation=kf.interpolation,
                is_molang=kf.is_molang,
                molang_x=kf.molang_x,
                molang_y=kf.molang_y,
                molang_z=kf.molang_z,
            )
            result.append(new_kf)
    
    # Sort by time, then channel
    result.sort(key=lambda kf: (kf.time, kf.channel))
    
    return result


# ---------------------------------------------------------------------------
# Apply to all animations
# ---------------------------------------------------------------------------

def extend_loop_animations(
    animations: List[AnimationIR],
    model_name: str = "",
) -> List[AnimationIR]:
    """Extend all short loop animations to multiple cycles.
    
    Args:
        animations: List of AnimationIR instances.
        model_name: Model name for logging.
        
    Returns:
        New list of AnimationIR with extended animations.
    """
    result: List[AnimationIR] = []
    extended_count = 0
    
    for anim in animations:
        extended = extend_animation(anim)
        if extended is not anim:
            extended_count += 1
            logger.debug(
                "[%s] Extended '%s': %.4fs × %d = %.4fs",
                model_name, anim.name, anim.length,
                round(extended.length / anim.length),
                extended.length,
            )
        result.append(extended)
    
    if extended_count > 0:
        logger.info(
            "[%s] LoopExtender: extended %d/%d animations",
            model_name, extended_count, len(animations),
        )
    
    return result
