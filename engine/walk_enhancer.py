#!/usr/bin/env python3
"""
Super Architecture — Walk Animation Enhancer  (v6.0 — Axis-Aware Edition)
==========================================================================

Enhance subtle walk animations by adding synthetic walking leg rotation
that accurately mimics the original SRP mod's programmatic animation.

PROBLEM (v6.0 refined understanding):
  The original SRP mod uses vanilla Minecraft ModelBase with PROGRAMMATIC
  animation driven by MathHelper.cos(limbSwing * speed) * degree. This is
  NOT keyframe animation — it's a continuous mathematical function driven
  by the entity's actual movement speed.

  The Java code uses two main methods in ModelSRP:
    swingX(part, speed, degree, invert, limbSwing, limbSwingAmount):
      part.rotateX = invert * limbSwingAmount * degree * cos(limbSwing * speed) * limbSwingAmount

    swingX(part, speed, degree, invert, offset, weight, limbSwing, limbSwingAmount):
      part.rotateX = invert * limbSwingAmount * degree * cos(limbSwing * speed + offset)
                     + weight * limbSwingAmount

    swingY(part, speed, degree, invert, limbSwing, limbSwingAmount):
      part.rotateY = invert * limbSwingAmount * degree * cos(limbSwing * speed) * limbSwingAmount

    moveY(part, speed, invert, f, f1, distance):
      part.posY = invert * cos(f * speed) * f1 * distance

  The bone naming convention in SRP models:
    jointFLLX → Front Left Leg, X-suffix = rotates around Y-axis (swingY, main forward/back swing)
    jointFLLY → Front Left Leg, Y-suffix = rotates around X-axis (swingX, secondary flex/sway)
    jointFLL1/2/3 → Front Left Leg sub-segments (swingX)
    (Same pattern for FRL, MLL, MRL, BLL, BRL, FLA, FRA)

  The GeckoLib .animation.json source captures only a small overlay portion
  of the walk animation. The main programmatic rotation (14-23° amplitude)
  is completely lost in conversion.

  PREVIOUS WALK ENHANCER BUGS:
  1. Leg bone patterns only matched numbered sub-segments (jointFLL1, etc.)
     but NOT the main rotation joints (jointFLLX, jointFLLY)
  2. Enhancement threshold used ALL bone rotation ranges (including hair/tentacle
     from idle_walk_merger), so hair sway (18-22°) caused the enhancer to
     think the walk already had sufficient rotation and skip enhancement
  3. Synthetic walk only added X-axis rotation, but the original uses both
     X-axis (swingX) and Y-axis (swingY) depending on the bone

SOLUTION (v6.0):
  1. Classify leg bones with axis awareness: each bone knows which axis
     it primarily rotates around (X-suffix → Y rotation, Y-suffix → X rotation)
  2. Compute enhancement threshold based ONLY on leg bone rotation ranges
  3. Generate axis-correct synthetic walk:
     - X-suffix bones: add Y-axis cos() rotation (main leg swing)
     - Y-suffix bones: add X-axis cos() rotation (leg flex/sway)
     - Numbered sub-segments: add X-axis cos() rotation
  4. Phase alternation: Front-Left/Back-Right in phase A,
     Front-Right/Back-Left in phase B (standard quadruped gait)
  5. Middle legs get OPPOSITE phase to front legs (insect-like gait)
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
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

# Maximum rotation range (degrees) below which LEG BONES in a walk animation
# are considered "overlay-only" and need enhancement.
# Only leg bone rotation is considered — hair/tentacle/body sway from idle
# merger is excluded from this calculation.
#
# v6.1 (fidelity tuning): lowered 10.0 → 5.0. Decompiled Java analysis
# (ModelBano.setRotationAngles) shows the main leg swing uses
#   swingY(jointFLLX, 0.8, 1.0, ...) → rotateAngleY = limbSwingAmount² * 1.0 * cos(limbSwing*0.8)
# which at full walk yields ~57° peak amplitude. The reverse-engineered JSON
# only captures ~22° (the overlay portion). With threshold=10°, Bano's walk
# (22° leg range) was NOT enhanced. Lowering to 5° ensures under-amplified
# walks get the synthetic boost they need.
ENHANCE_THRESHOLD: float = 5.0

# Target total rotation amplitude for enhanced leg bones (degrees).
# Original SRP models use 14-23° for main leg joints (swingY) and
# 5-12° for secondary joints (swingX with offset/weight variants).
#
# v6.1 (fidelity tuning): raised 20.0 → 30.0 for primary, 10.0 → 15.0 for
# secondary. Decompiled analysis shows Java's `degree` parameter ranges
# 1.0-1.4 rad (57°-80°) for main swingY joints. The JSON overlay typically
# contributes 5-10°, so the synthetic portion needs to target ~30° total
# to reach the Java ground-truth amplitude (overlay 10° + synthetic 20° = 30°
# is still below Java's 57°, but avoids overshooting for models where the
# JSON overlay is already substantial).
TARGET_PRIMARY_AMPLITUDE: float = 30.0   # For main swing (Y-axis on X-suffix bones)
TARGET_SECONDARY_AMPLITUDE: float = 15.0  # For flex/sway (X-axis on Y-suffix bones)

# Number of keyframes per walk cycle for the synthetic rotation.
SYNTHETIC_KF_PER_CYCLE: int = 16

# Minimum amplitude to add (degrees).
MIN_SYNTHETIC_AMPLITUDE: float = 3.0

# Walk cycle speed parameter (mimics limbSwing * speed from original).
# This controls how many full cycles fit in the animation length.
# Original uses speed=0.3 for most legs (0.2*1.5 where GS=1.5).
WALK_CYCLE_SPEED: float = 0.3


# ---------------------------------------------------------------------------
# Leg bone classification
# ---------------------------------------------------------------------------

# Leg bone classification: (regex_pattern, phase_group, primary_axis)
#   phase_group: "A" or "B" (alternating leg phase)
#   primary_axis: "y" for X-suffix bones (swingY = Y rotation),
#                 "x" for Y-suffix/numbered bones (swingX = X rotation)
#
# Naming convention from original SRP Java code:
#   jointFLLX = Front Left Leg X-joint → swingY → rotates around Y axis
#   jointFLLY = Front Left Leg Y-joint → swingX → rotates around X axis
#   jointFLL1/2/3 = Front Left Leg sub-segments → swingX → rotates around X axis

LEG_BONE_PATTERNS: List[Tuple[str, str, str]] = [
    # === Front legs - X-suffix (main swing, Y-axis rotation) ===
    (r'^jointfllx(_\d+)?$', 'A', 'y'),      # Front Left Leg X-joint
    (r'^jointfrlx(_\d+)?$', 'B', 'y'),      # Front Right Leg X-joint
    (r'^jointflax(_\d+)?$', 'A', 'y'),      # Front Left Arm X-joint
    (r'^jointfrax(_\d+)?$', 'B', 'y'),      # Front Right Arm X-joint

    # === Front legs - Y-suffix (flex/sway, X-axis rotation) ===
    (r'^jointflly(_\d+)?$', 'A', 'x'),      # Front Left Leg Y-joint
    (r'^jointfrly(_\d+)?$', 'B', 'x'),      # Front Right Leg Y-joint
    (r'^jointflay(_\d+)?$', 'A', 'x'),      # Front Left Arm Y-joint
    (r'^jointfray(_\d+)?$', 'B', 'x'),      # Front Right Arm Y-joint

    # === Front legs - numbered sub-segments (swingX, X-axis rotation) ===
    (r'^jointfll\d+$', 'A', 'x'),           # Front Left Leg sub-segments
    (r'^jointfrl\d+$', 'B', 'x'),           # Front Right Leg sub-segments
    (r'^jointfla\d+$', 'A', 'x'),           # Front Left Arm sub-segments
    (r'^jointfra\d+$', 'B', 'x'),           # Front Right Arm sub-segments
    (r'^jointfl\d+$', 'A', 'x'),            # Front Left variant
    (r'^jointfr\d+$', 'B', 'x'),            # Front Right variant

    # === Middle legs - X-suffix (main swing, Y-axis rotation) ===
    (r'^jointmllx(_\d+)?$', 'B', 'y'),     # Mid Left Leg X-joint (opposite phase to front)
    (r'^jointmrlx(_\d+)?$', 'A', 'y'),     # Mid Right Leg X-joint (same phase as front-left)

    # === Middle legs - Y-suffix (flex/sway, X-axis rotation) ===
    (r'^jointmlly(_\d+)?$', 'B', 'x'),     # Mid Left Leg Y-joint
    (r'^jointmrly(_\d+)?$', 'A', 'x'),     # Mid Right Leg Y-joint

    # === Middle legs - numbered sub-segments ===
    (r'^jointmll\d+$', 'B', 'x'),          # Mid Left Leg sub-segments
    (r'^jointmrl\d+$', 'A', 'x'),          # Mid Right Leg sub-segments
    (r'^jointml\d+$', 'B', 'x'),           # Mid Left variant
    (r'^jointmr\d+$', 'A', 'x'),           # Mid Right variant

    # === Back legs - X-suffix (main swing, Y-axis rotation) ===
    (r'^jointbllx(_\d+)?$', 'B', 'y'),     # Back Left Leg X-joint (opposite to front-left)
    (r'^jointbrlx(_\d+)?$', 'A', 'y'),     # Back Right Leg X-joint (same as front-left)

    # === Back legs - Y-suffix (flex/sway, X-axis rotation) ===
    (r'^jointblly(_\d+)?$', 'B', 'x'),     # Back Left Leg Y-joint
    (r'^jointbrly(_\d+)?$', 'A', 'x'),     # Back Right Leg Y-joint

    # === Back legs - numbered sub-segments ===
    (r'^jointbll\d+$', 'B', 'x'),          # Back Left Leg sub-segments
    (r'^jointbrl\d+$', 'A', 'x'),          # Back Right Leg sub-segments
    (r'^jointbl\d+$', 'B', 'x'),           # Back Left variant
    (r'^jointbr\d+$', 'A', 'x'),           # Back Right variant

    # === Generic left/right leg joints ===
    (r'^jointll\d*$', 'A', 'x'),           # Left Leg
    (r'^jointrl\d*$', 'B', 'x'),           # Right Leg
    (r'^jointl[a-z]\d*$', 'A', 'x'),       # Left Arm/Leg variant
    (r'^jointr[a-z]\d*$', 'B', 'x'),       # Right Arm/Leg variant

    # === Other naming conventions ===
    (r'^lfrontleg_joint$', 'A', 'y'),      # Left Front Leg joint
    (r'^rfrontleg_joint$', 'B', 'y'),      # Right Front Leg joint
    (r'^lbackleg_joint$', 'B', 'y'),       # Left Back Leg joint
    (r'^rbackleg_joint$', 'A', 'y'),       # Right Back Leg joint
    (r'^lfjoint_\d*$', 'A', 'x'),          # Left Front joint
    (r'^rfjoint_\d*$', 'B', 'x'),          # Right Front joint
    (r'^lbjoint_\d*$', 'B', 'x'),          # Left Back joint
    (r'^rbjoint_\d*$', 'A', 'x'),          # Right Back joint
    (r'^lfrontleg\d*$', 'A', 'x'),         # Left Front Leg
    (r'^rfrontleg\d*$', 'B', 'x'),         # Right Front Leg
    (r'^lbackleg\d*$', 'B', 'x'),          # Left Back Leg
    (r'^rbackleg\d*$', 'A', 'x'),          # Right Back Leg

    # === Special: frontleg (single bone, no left/right) ===
    (r'^frontleg$', 'A', 'x'),

    # === Standard left/right legs ===
    (r'^leftleg$', 'A', 'x'),
    (r'^rightleg$', 'B', 'x'),

    # === Tentacle joints (treat as legs for walking) ===
    (r'^taclejointfl\d*$', 'A', 'x'),
    (r'^taclejointfr\d*$', 'B', 'x'),
    (r'^taclejointl\d*$', 'A', 'x'),
    (r'^taclejointr\d*$', 'B', 'x'),
]


@dataclass
class LegBoneInfo:
    """Classification info for a leg bone."""
    bone_name: str
    phase_group: str    # "A" or "B"
    primary_axis: str   # "x" or "y" — which rotation axis this bone primarily uses

    @property
    def is_primary_joint(self) -> bool:
        """True if this is a primary rotation joint (X-suffix = swingY)."""
        return self.primary_axis == 'y'


def _classify_leg_bone(bone_name: str) -> Optional[LegBoneInfo]:
    """Classify a bone as a leg bone with axis information.

    Args:
        bone_name: Bone name (case-insensitive matching).

    Returns:
        LegBoneInfo with phase group and primary axis, or None if not a leg bone.
    """
    lower = bone_name.lower()

    for pattern, phase, axis in LEG_BONE_PATTERNS:
        if re.match(pattern, lower):
            return LegBoneInfo(
                bone_name=bone_name,
                phase_group=phase,
                primary_axis=axis,
            )

    # Additional heuristic: if the bone name contains "leg"
    if 'leg' in lower:
        if 'left' in lower or 'lfront' in lower or 'lback' in lower:
            return LegBoneInfo(bone_name, 'A', 'x')
        elif 'right' in lower or 'rfront' in lower or 'rback' in lower:
            return LegBoneInfo(bone_name, 'B', 'x')
        elif lower.startswith('l') or 'lleg' in lower:
            return LegBoneInfo(bone_name, 'A', 'x')
        elif lower.startswith('r') or 'rleg' in lower:
            return LegBoneInfo(bone_name, 'B', 'x')

    return None


# ---------------------------------------------------------------------------
# Walk animation analysis
# ---------------------------------------------------------------------------

def _compute_leg_rotation_range(anim: AnimationIR) -> float:
    """Compute the maximum rotation range across LEG BONES ONLY in a walk animation.

    This excludes hair/tentacle/body bones that may have large rotation from
    the idle_walk_merger. Only leg bones are considered to accurately assess
    whether the walk animation needs enhancement.

    Args:
        anim: The walk AnimationIR.

    Returns:
        Maximum rotation range in degrees (leg bones only).
    """
    max_range = 0.0

    for bone_name, bone_anim in anim.bones.items():
        # Only consider leg bones
        leg_info = _classify_leg_bone(bone_name)
        if leg_info is None:
            continue

        rot_kfs = [kf for kf in bone_anim.keyframes if kf.channel == "rotation"]
        if not rot_kfs:
            continue

        for axis in AXES:
            vals = [getattr(kf, axis).value for kf in rot_kfs if getattr(kf, axis).explicit]
            if vals:
                rng = max(vals) - min(vals)
                max_range = max(max_range, rng)

    return max_range


def _get_existing_rotation_for_axis(
    bone_anim: BoneAnimationIR, axis: str
) -> Tuple[float, float]:
    """Get the center value and range of existing rotation on a specific axis.

    Args:
        bone_anim: The bone's animation data.
        axis: Which axis to check ("x", "y", or "z").

    Returns:
        (center, range) tuple. (0, 0) if no rotation data.
    """
    rot_kfs = [kf for kf in bone_anim.keyframes if kf.channel == "rotation"]
    if not rot_kfs:
        return (0.0, 0.0)

    vals = [getattr(kf, axis).value for kf in rot_kfs if getattr(kf, axis).explicit]
    if not vals:
        return (0.0, 0.0)

    min_val = min(vals)
    max_val = max(vals)
    center = (min_val + max_val) / 2.0
    range_val = max_val - min_val

    return (center, range_val)


# ---------------------------------------------------------------------------
# Synthetic walk generation
# ---------------------------------------------------------------------------

def _generate_synthetic_walk_keyframes(
    anim_length: float,
    phase_group: str,
    amplitude: float,
    existing_center: float,
    primary_axis: str,
    num_kf: int = SYNTHETIC_KF_PER_CYCLE,
) -> List[Tuple[float, Dict[str, float]]]:
    """Generate synthetic walk rotation keyframes with axis awareness.

    Produces a sinusoidal walk cycle where:
    - Phase group A: sin(2pi * t / period)
    - Phase group B: sin(2pi * t / period + pi) = -sin(2pi * t / period)

    The rotation is applied on the bone's PRIMARY AXIS:
    - X-suffix bones (primary_axis='y'): Y-axis rotation (main leg swing)
    - Y-suffix/numbered bones (primary_axis='x'): X-axis rotation (leg flex)

    The synthetic values are CENTERED around the existing rotation center,
    so they ADD to the existing animation without displacing it.

    Args:
        anim_length: Animation length in seconds.
        phase_group: "A" or "B" (determines phase offset).
        amplitude: Peak amplitude in degrees.
        existing_center: The center of the existing animation values.
        primary_axis: Which rotation axis this bone primarily uses.
        num_kf: Number of keyframes to generate.

    Returns:
        List of (time, {axis: value}) tuples.
    """
    if amplitude < MIN_SYNTHETIC_AMPLITUDE:
        return []

    result = []
    phase_offset = 0.0 if phase_group == 'A' else math.pi

    for i in range(num_kf + 1):
        t = i * anim_length / num_kf
        # Sinusoidal walk cycle
        angle = 2.0 * math.pi * t / anim_length + phase_offset
        synthetic_value = amplitude * math.sin(angle)
        # Add to existing center
        total_value = existing_center + synthetic_value

        # Build axis values — only set the primary axis
        axis_vals = {"x": 0.0, "y": 0.0, "z": 0.0}
        axis_vals[primary_axis] = total_value

        result.append((t, axis_vals))

    return result


def _merge_synthetic_with_existing(
    bone_anim: BoneAnimationIR,
    synthetic_kfs: List[Tuple[float, Dict[str, float]]],
    primary_axis: str,
    anim_length: float,
) -> List[KeyframeData]:
    """Merge synthetic walk keyframes with existing animation data.

    For each synthetic keyframe time point:
    1. Look up the existing rotation value at that time (interpolated)
    2. Calculate the synthetic offset (synthetic_value - existing_center)
    3. Add the synthetic offset to the existing value on the primary axis
    4. Keep existing values on non-primary axes (interpolated from existing)
    5. Preserve existing position and scale keyframes

    Args:
        bone_anim: The bone's existing animation data.
        synthetic_kfs: List of (time, {axis: value}) tuples.
        primary_axis: Which axis is the primary rotation axis.
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

    # Get existing center for the primary axis
    existing_center, _ = _get_existing_rotation_for_axis(bone_anim, primary_axis)

    # Build time->value lookups for all rotation axes (for interpolation)
    def _get_interp_value(t: float, axis: str) -> float:
        """Get interpolated rotation value at time t for a given axis."""
        if not existing_rot:
            return 0.0

        # Get explicit values for this axis
        times_vals = [(kf.time, getattr(kf, axis).value) for kf in existing_rot
                      if getattr(kf, axis).explicit]

        if not times_vals:
            # Use all values (including non-explicit/carry-forward)
            times_vals = [(kf.time, getattr(kf, axis).value) for kf in existing_rot]

        if not times_vals:
            return 0.0

        times_vals.sort(key=lambda x: x[0])

        if t <= times_vals[0][0]:
            return times_vals[0][1]
        if t >= times_vals[-1][0]:
            return times_vals[-1][1]

        # Linear interpolation
        for i in range(len(times_vals) - 1):
            t0, v0 = times_vals[i]
            t1, v1 = times_vals[i + 1]
            if t0 <= t <= t1:
                dt = t1 - t0
                if dt < 1e-12:
                    return v0
                s = (t - t0) / dt
                return v0 + s * (v1 - v0)

        return times_vals[-1][1]

    # Create merged rotation keyframes
    merged_rot: List[KeyframeData] = []

    for t, synth_axis_vals in synthetic_kfs:
        # Compute synthetic offset for the primary axis
        synth_primary = synth_axis_vals[primary_axis]
        synthetic_offset = synth_primary - existing_center

        # Get existing values at this time for all axes
        existing_x = _get_interp_value(t, "x")
        existing_y = _get_interp_value(t, "y")
        existing_z = _get_interp_value(t, "z")

        # Add synthetic offset to the primary axis
        final_vals = {"x": existing_x, "y": existing_y, "z": existing_z}
        final_vals[primary_axis] = final_vals[primary_axis] + synthetic_offset

        kf = KeyframeData(
            time=t,
            channel="rotation",
            x=AxisValue.explicit_val(final_vals["x"]),
            y=AxisValue.explicit_val(final_vals["y"]),
            z=AxisValue.explicit_val(final_vals["z"]),
            easing="linear",
            interpolation="linear",  # Already baked — use linear
        )
        merged_rot.append(kf)

    # Combine: new rotation + existing position + existing scale
    result = merged_rot + existing_pos + existing_scale
    result.sort(key=lambda kf: (kf.time, kf.channel))

    return result


# ---------------------------------------------------------------------------
# Main enhancement function
# ---------------------------------------------------------------------------

def enhance_walk_animation(
    anim: AnimationIR,
    model_name: str = "",
) -> AnimationIR:
    """Enhance a walk animation by adding synthetic leg rotation.

    Only enhances animations that:
      - Have "walk" in their name
      - Have max LEG rotation range < ENHANCE_THRESHOLD
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

    # Check LEG rotation range (not all-bone range!)
    leg_max_range = _compute_leg_rotation_range(anim)

    if leg_max_range >= ENHANCE_THRESHOLD:
        logger.debug(
            "[%s] Walk '%s' has sufficient leg range %.1f° — no enhancement needed",
            model_name, anim.name, leg_max_range,
        )
        return anim

    # Identify leg bones and their classification
    leg_bones: Dict[str, LegBoneInfo] = {}
    for bone_name in anim.bones:
        leg_info = _classify_leg_bone(bone_name)
        if leg_info is not None:
            leg_bones[bone_name] = leg_info

    if not leg_bones:
        logger.debug(
            "[%s] Walk '%s' has small range %.1f° but no identifiable leg bones — skipping",
            model_name, anim.name, leg_max_range,
        )
        return anim

    # Compute synthetic amplitude for each leg bone
    enhanced_bones: Dict[str, BoneAnimationIR] = {}
    enhanced_count = 0

    for bone_name, bone_anim in anim.bones.items():
        if bone_name in leg_bones:
            leg_info = leg_bones[bone_name]
            primary_axis = leg_info.primary_axis

            # Get existing rotation info for the primary axis
            existing_center, existing_range = _get_existing_rotation_for_axis(
                bone_anim, primary_axis
            )

            # Calculate synthetic amplitude
            # Primary joints (X-suffix, swingY) get larger amplitude
            # Secondary joints (Y-suffix/numbered, swingX) get smaller amplitude
            if leg_info.is_primary_joint:
                target_amplitude = TARGET_PRIMARY_AMPLITUDE
            else:
                target_amplitude = TARGET_SECONDARY_AMPLITUDE

            synthetic_amplitude = max(0, target_amplitude - existing_range) / 2.0

            if synthetic_amplitude < MIN_SYNTHETIC_AMPLITUDE:
                # Already enough range, just keep existing
                enhanced_bones[bone_name] = bone_anim
                continue

            # Generate axis-aware synthetic keyframes
            synthetic_kfs = _generate_synthetic_walk_keyframes(
                anim_length=anim.length,
                phase_group=leg_info.phase_group,
                amplitude=synthetic_amplitude,
                existing_center=existing_center,
                primary_axis=primary_axis,
            )

            if not synthetic_kfs:
                enhanced_bones[bone_name] = bone_anim
                continue

            # Merge synthetic keyframes with existing animation
            new_keyframes = _merge_synthetic_with_existing(
                bone_anim, synthetic_kfs, primary_axis, anim.length
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
            "[%s] WalkEnhancer v6.1: enhanced '%s' (leg_range=%.1f°, %d leg bones enhanced, target=%.0f°/%.0f°)",
            model_name, anim.name, leg_max_range, enhanced_count,
            TARGET_PRIMARY_AMPLITUDE, TARGET_SECONDARY_AMPLITUDE,
        )

    return AnimationIR(
        name=anim.name,
        loop=anim.loop,
        length=anim.length,
        bones=enhanced_bones,
        period=anim.period,
    )


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
            "[%s] WalkEnhancer v6.1: enhanced %d/%d walk animations",
            model_name, enhanced_count, len(animations),
        )

    return result
