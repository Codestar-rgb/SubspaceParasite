#!/usr/bin/env python3
"""
Super Architecture — Walk Animation Enhancer
==============================================

Enhance subtle walk animations by adding synthetic walking leg rotation.

PROBLEM:
  In the SRP (Scape and Run Parasites) mod, many creatures' walk animations
  have very small rotation ranges (<5°). This is because the original mod uses
  GeckoLib animations as OVERLAY effects — the main walking motion comes from
  the Java entity code that programmatically rotates leg bones based on the
  entity's movement speed. The GeckoLib animation only adds subtle body sway
  and slight leg adjustments on top.

  When these animations are converted to Blockbench .bbmodel format, the
  programmatic rotation is lost, leaving only the subtle overlay — which looks
  like "slight foot lifts" or "barely visible movement".

  Analysis of 71 walk animations found:
    - 44 have max rotation < 5° (overlay-only, need enhancement)
    - 8 have max rotation 5-15° (partial, might need enhancement)
    - 19 have max rotation >= 15° (self-contained, no enhancement needed)

SOLUTION:
  For walk animations with small rotation ranges, generate a synthetic walking
  cycle for each leg bone and ADD it to the existing animation values. The
  synthetic walk cycle:

  1. Uses a standard sinusoidal pattern for leg rotation around X axis
  2. Alternates front-left/back-right legs (in phase) vs front-right/back-left
  3. Has an amplitude that complements the existing animation (if existing
     animation has ~2° range, add ~25° synthetic to achieve ~27° total)
  4. Preserves the original animation's subtle body sway and position effects
  5. Ensures perfect loop continuity (first frame = last frame)

ALGORITHM:
  1. Identify walk animations (by name containing "walk")
  2. Calculate max rotation range across all bones
  3. If range < THRESHOLD, mark for enhancement
  4. For each leg bone, determine:
     - Which "phase group" it belongs to (left vs right)
     - The existing rotation center and range
     - The synthetic amplitude needed
  5. Generate synthetic keyframes at regular intervals
  6. Add synthetic values to existing animation values
  7. Ensure loop continuity (first frame value = last frame value)
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from core.types import (
    AXES,
    CHANNELS,
    AnimationIR,
    AxisValue,
    BoneAnimationIR,
    KeyframeData,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Maximum rotation range (degrees) below which a walk animation is considered
# "overlay-only" and needs enhancement.
ENHANCE_THRESHOLD: float = 10.0

# Target total rotation amplitude for enhanced leg bones (degrees).
# A typical Minecraft walk cycle has ±25° to ±35° range.
TARGET_LEG_AMPLITUDE: float = 25.0

# Number of keyframes per walk cycle for the synthetic rotation.
# More keyframes = smoother curve but larger file size.
SYNTHETIC_KF_PER_CYCLE: int = 16

# Minimum amplitude to add (degrees). If the calculated synthetic amplitude
# is less than this, don't bother adding it.
MIN_SYNTHETIC_AMPLITUDE: float = 5.0

# Leg bone name patterns (lowercase).
# Format: (pattern, phase_group)
#   phase_group: "A" = front-left/back-right (in phase)
#                "B" = front-right/back-left (in phase, opposite to A)
LEG_PATTERNS: List[Tuple[str, str]] = [
    # Front legs
    (r'jointfll\d*', 'A'),    # Front Left Leg
    (r'jointfrl\d*', 'B'),    # Front Right Leg
    (r'jointlfront\d*', 'A'), # Left Front
    (r'jointrfront\d*', 'B'), # Right Front
    (r'lfjoint\d*', 'A'),     # Left Front joint
    (r'rfjoint\d*', 'B'),     # Right Front joint
    (r'jointfl\d*', 'A'),     # Front Left
    (r'jointfr\d*', 'B'),     # Front Right
    
    # Back legs
    (r'jointbll\d*', 'B'),    # Back Left Leg (opposite phase to front-left)
    (r'jointbrl\d*', 'A'),    # Back Right Leg (same phase as front-left)
    (r'jointlback\d*', 'B'),  # Left Back
    (r'jointrback\d*', 'A'),  # Right Back
    (r'lbjoint\d*', 'B'),     # Left Back joint
    (r'rbjoint\d*', 'A'),     # Right Back joint
    (r'jointbl\d*', 'B'),     # Back Left
    (r'jointbr\d*', 'A'),     # Back Right
    
    # Middle legs (for multi-leg creatures)
    (r'jointmll\d*', 'A'),    # Middle Left Leg
    (r'jointmrl\d*', 'B'),    # Middle Right Leg
    (r'jointml\d*', 'A'),     # Middle Left
    (r'jointmr\d*', 'B'),     # Middle Right
    
    # Generic left/right leg pairs
    (r'jointll\d*', 'A'),     # Left Leg
    (r'jointrl\d*', 'B'),     # Right Leg
    (r'jointl[a-z]\d*', 'A'), # Left Arm/Leg variant
    (r'jointr[a-z]\d*', 'B'), # Right Arm/Leg variant
    
    # Special: tacle (tentacle) joints
    (r'taclejointl\d*', 'A'),
    (r'taclejointr\d*', 'B'),
    
    # Rfrontleg/Lfrontleg style (bano-like naming)
    (r'rfrontleg\d*', 'B'),
    (r'lfrontleg\d*', 'A'),
    (r'rbackleg\d*', 'A'),
    (r'lbackleg\d*', 'B'),
]


def _classify_leg_bone(bone_name: str) -> Optional[str]:
    """Classify a bone as a leg bone and determine its phase group.
    
    Args:
        bone_name: Bone name (case-insensitive matching).
        
    Returns:
        Phase group "A" or "B", or None if not a leg bone.
    """
    lower = bone_name.lower()
    
    for pattern, phase in LEG_PATTERNS:
        if re.match(pattern, lower):
            return phase
    
    # Additional heuristic: if the bone name contains "leg" or specific patterns
    if 'leg' in lower:
        if 'left' in lower or 'lfront' in lower or 'lback' in lower:
            return 'A'
        elif 'right' in lower or 'rfront' in lower or 'rback' in lower:
            return 'B'
        # Generic left/right detection
        elif lower.startswith('l') or 'lleg' in lower:
            return 'A'
        elif lower.startswith('r') or 'rleg' in lower:
            return 'B'
    
    return None


def _compute_walk_rotation_range(anim: AnimationIR) -> float:
    """Compute the maximum rotation range across all bones in a walk animation.
    
    Args:
        anim: The walk AnimationIR.
        
    Returns:
        Maximum rotation range in degrees.
    """
    max_range = 0.0
    
    for bone_name, bone_anim in anim.bones.items():
        rot_kfs = [kf for kf in bone_anim.keyframes if kf.channel == "rotation"]
        if not rot_kfs:
            continue
        
        for axis in AXES:
            vals = [getattr(kf, axis).value for kf in rot_kfs if getattr(kf, axis).explicit]
            if vals:
                rng = max(vals) - min(vals)
                max_range = max(max_range, rng)
    
    return max_range


def _get_existing_rotation_center(bone_anim: BoneAnimationIR) -> Tuple[float, float]:
    """Get the center value and range of existing X rotation for a bone.
    
    Args:
        bone_anim: The bone's animation data.
        
    Returns:
        (center, range) tuple for X rotation. (0, 0) if no rotation data.
    """
    rot_kfs = [kf for kf in bone_anim.keyframes if kf.channel == "rotation"]
    if not rot_kfs:
        return (0.0, 0.0)
    
    x_vals = [kf.x.value for kf in rot_kfs if kf.x.explicit]
    if not x_vals:
        return (0.0, 0.0)
    
    min_val = min(x_vals)
    max_val = max(x_vals)
    center = (min_val + max_val) / 2.0
    range_val = max_val - min_val
    
    return (center, range_val)


def _generate_synthetic_walk_keyframes(
    anim_length: float,
    phase_group: str,
    amplitude: float,
    existing_center: float,
    num_kf: int = SYNTHETIC_KF_PER_CYCLE,
) -> List[Tuple[float, float]]:
    """Generate synthetic walk rotation keyframes.
    
    Produces a sinusoidal walk cycle where:
    - Phase group A: sin(2π * t / period)
    - Phase group B: sin(2π * t / period + π) = -sin(2π * t / period)
    
    The synthetic values are CENTERED around the existing rotation center,
    so they ADD to the existing animation without displacing it.
    
    Args:
        anim_length: Animation length in seconds.
        phase_group: "A" or "B" (determines phase offset).
        amplitude: Peak amplitude in degrees (±amplitude from center).
        existing_center: The center of the existing animation values.
        num_kf: Number of keyframes to generate.
        
    Returns:
        List of (time, value) tuples.
    """
    if amplitude < MIN_SYNTHETIC_AMPLITUDE:
        return []
    
    result = []
    phase_offset = 0.0 if phase_group == 'A' else math.pi
    
    # Generate keyframes from t=0 to t=anim_length
    # Use the animation length as one full walk cycle
    for i in range(num_kf + 1):
        t = i * anim_length / num_kf
        # Sinusoidal walk cycle
        angle = 2.0 * math.pi * t / anim_length + phase_offset
        synthetic_value = amplitude * math.sin(angle)
        # Add to existing center
        total_value = existing_center + synthetic_value
        result.append((t, total_value))
    
    # Ensure loop continuity: first and last values must match
    # The sin function naturally ensures sin(0) = sin(2π) = 0,
    # so the synthetic component is 0 at both endpoints.
    # This means first = last = existing_center, which is correct for looping.
    
    return result


def enhance_walk_animation(
    anim: AnimationIR,
    model_name: str = "",
) -> AnimationIR:
    """Enhance a walk animation by adding synthetic leg rotation.
    
    Only enhances animations that:
      - Have "walk" in their name
      - Have max rotation range < ENHANCE_THRESHOLD
      - Have identifiable leg bones
    
    For animations that already have large rotation ranges (self-contained
    walks), this function returns the input unchanged.
    
    Args:
        anim: The walk AnimationIR to enhance.
        model_name: Model name for logging.
        
    Returns:
        Enhanced AnimationIR (or original if no enhancement needed).
    """
    # Only enhance walk animations
    if 'walk' not in anim.name.lower():
        return anim
    
    # Check rotation range
    max_range = _compute_walk_rotation_range(anim)
    
    if max_range >= ENHANCE_THRESHOLD:
        logger.debug(
            "[%s] Walk '%s' has sufficient range %.1f° — no enhancement needed",
            model_name, anim.name, max_range,
        )
        return anim
    
    # Identify leg bones and their phase groups
    leg_bones: Dict[str, str] = {}  # bone_name -> phase_group
    for bone_name in anim.bones:
        phase = _classify_leg_bone(bone_name)
        if phase is not None:
            leg_bones[bone_name] = phase
    
    if not leg_bones:
        logger.debug(
            "[%s] Walk '%s' has small range %.1f° but no identifiable leg bones — skipping",
            model_name, anim.name, max_range,
        )
        return anim
    
    # Compute synthetic amplitude for each leg bone
    # The synthetic amplitude should bring the total rotation to TARGET_LEG_AMPLITUDE
    enhanced_bones: Dict[str, BoneAnimationIR] = {}
    enhanced_count = 0
    
    for bone_name, bone_anim in anim.bones.items():
        if bone_name in leg_bones:
            phase_group = leg_bones[bone_name]
            existing_center, existing_range = _get_existing_rotation_center(bone_anim)
            
            # Calculate how much synthetic rotation to add
            # Target: existing_center ± (TARGET_LEG_AMPLITUDE / 2)
            # But we want the existing animation to be PRESERVED as an overlay
            # So the synthetic amplitude should make the TOTAL range ≈ TARGET_LEG_AMPLITUDE
            synthetic_amplitude = max(0, TARGET_LEG_AMPLITUDE - existing_range) / 2.0
            
            if synthetic_amplitude < MIN_SYNTHETIC_AMPLITUDE:
                # Already enough range, just keep existing
                enhanced_bones[bone_name] = bone_anim
                continue
            
            # Generate synthetic keyframes
            synthetic_kfs = _generate_synthetic_walk_keyframes(
                anim_length=anim.length,
                phase_group=phase_group,
                amplitude=synthetic_amplitude,
                existing_center=existing_center,
            )
            
            if not synthetic_kfs:
                enhanced_bones[bone_name] = bone_anim
                continue
            
            # Merge synthetic keyframes with existing animation
            # Strategy: For each synthetic keyframe time point, ADD the synthetic
            # value to the existing interpolated value.
            new_keyframes = _merge_synthetic_with_existing(
                bone_anim, synthetic_kfs, anim.length
            )
            
            enhanced_bones[bone_name] = BoneAnimationIR(
                bone_name=bone_name,
                keyframes=new_keyframes,
            )
            enhanced_count += 1
        else:
            # Non-leg bone — keep unchanged
            enhanced_bones[bone_name] = bone_anim
    
    if enhanced_count > 0:
        logger.info(
            "[%s] WalkEnhancer: enhanced '%s' (range=%.1f°, %d leg bones enhanced)",
            model_name, anim.name, max_range, enhanced_count,
        )
    
    return AnimationIR(
        name=anim.name,
        loop=anim.loop,
        length=anim.length,
        bones=enhanced_bones,
        period=anim.period,
    )


def _merge_synthetic_with_existing(
    bone_anim: BoneAnimationIR,
    synthetic_kfs: List[Tuple[float, float]],
    anim_length: float,
) -> List[KeyframeData]:
    """Merge synthetic walk keyframes with existing animation data.
    
    For each synthetic keyframe time point:
    1. Look up the existing rotation value at that time (interpolated from
       existing keyframes, or the nearest keyframe)
    2. Calculate the synthetic offset (synthetic_value - existing_center)
    3. Add the synthetic offset to the existing value
    4. Create a new KeyframeData with the combined value
    
    This preserves the existing animation's subtle overlay while adding
    the synthetic walk cycle.
    
    Args:
        bone_anim: The bone's existing animation data.
        synthetic_kfs: List of (time, total_synthetic_value) tuples.
        anim_length: Animation length for boundary handling.
        
    Returns:
        New list of KeyframeData with merged values.
    """
    # Extract existing rotation keyframes
    existing_rot = sorted(
        [kf for kf in bone_anim.keyframes if kf.channel == "rotation"],
        key=lambda kf: kf.time,
    )
    existing_pos = [kf for kf in bone_anim.keyframes if kf.channel == "position"]
    existing_scale = [kf for kf in bone_anim.keyframes if kf.channel == "scale"]
    
    # Get the existing center for X rotation (used to compute synthetic offset)
    x_vals = [kf.x.value for kf in existing_rot if kf.x.explicit]
    existing_center = (min(x_vals) + max(x_vals)) / 2.0 if x_vals else 0.0
    
    # Build time->value lookup for existing X rotation (for interpolation)
    existing_times = [kf.time for kf in existing_rot]
    existing_x_vals = [kf.x.value for kf in existing_rot]
    
    def get_existing_x(t: float) -> float:
        """Get the existing X rotation value at time t (linear interpolation)."""
        if not existing_times:
            return 0.0
        if t <= existing_times[0]:
            return existing_x_vals[0]
        if t >= existing_times[-1]:
            return existing_x_vals[-1]
        
        # Binary search for the interval
        lo, hi = 0, len(existing_times) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if existing_times[mid] <= t:
                lo = mid
            else:
                hi = mid
        
        # Linear interpolation
        dt = existing_times[hi] - existing_times[lo]
        if dt < 1e-12:
            return existing_x_vals[lo]
        
        s = (t - existing_times[lo]) / dt
        return existing_x_vals[lo] + s * (existing_x_vals[hi] - existing_x_vals[lo])
    
    # Create merged rotation keyframes
    # Use the synthetic keyframe times as the new keyframe times
    merged_rot: List[KeyframeData] = []
    
    for t, synthetic_total in synthetic_kfs:
        # Get existing value at this time
        existing_val = get_existing_x(t)
        
        # Compute synthetic offset (the part to ADD to existing)
        # synthetic_total = existing_center + amplitude * sin(...)
        # So synthetic_offset = synthetic_total - existing_center
        synthetic_offset = synthetic_total - existing_center
        
        # Combined value = existing + synthetic_offset
        combined_x = existing_val + synthetic_offset
        
        # Get Y and Z values from existing (interpolated)
        existing_y = 0.0
        existing_z = 0.0
        
        # Find nearest existing keyframe for Y/Z
        if existing_rot:
            # Find closest time
            nearest_idx = 0
            min_dt = float('inf')
            for i, kf in enumerate(existing_rot):
                dt = abs(kf.time - t)
                if dt < min_dt:
                    min_dt = dt
                    nearest_idx = i
            
            existing_y = existing_rot[nearest_idx].y.value
            existing_z = existing_rot[nearest_idx].z.value
        
        kf = KeyframeData(
            time=t,
            channel="rotation",
            x=AxisValue.explicit_val(combined_x),
            y=AxisValue.explicit_val(existing_y),
            z=AxisValue.explicit_val(existing_z),
            easing="linear",
            interpolation="catmullrom",  # Will be baked later
        )
        merged_rot.append(kf)
    
    # Also include the original rotation keyframes (for non-X axes that might have data)
    # But only keep rotation keyframes that add unique data points
    # Since synthetic keyframes already cover all time points, we can just use those
    
    # Combine: new rotation + existing position + existing scale
    result = merged_rot + existing_pos + existing_scale
    result.sort(key=lambda kf: (kf.time, kf.channel))
    
    return result


def enhance_walk_animations(
    animations: List[AnimationIR],
    model_name: str = "",
) -> List[AnimationIR]:
    """Enhance all walk animations that need it.
    
    Args:
        animations: List of AnimationIR instances.
        model_name: Model name for logging.
        
    Returns:
        New list of AnimationIR with enhanced walk animations.
    """
    result = []
    enhanced_count = 0
    
    for anim in animations:
        enhanced = enhance_walk_animation(anim, model_name)
        if enhanced is not anim:
            enhanced_count += 1
        result.append(enhanced)
    
    if enhanced_count > 0:
        logger.info(
            "[%s] WalkEnhancer: enhanced %d/%d walk animations",
            model_name, enhanced_count, len(animations),
        )
    
    return result
