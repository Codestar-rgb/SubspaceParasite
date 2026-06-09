#!/usr/bin/env python3
"""
KirinAnimationGenerator - Comprehensive Animation Converter for Kirin
=====================================================================
Parses the original MC 1.12.2 Java animation code from ModelKirin.java and
generates high-quality GeckoLib .animation.json files for each entity state.

Animation States (from func_78087_a / setRotationAngles):
  1. idle           - Default state: 3 cosine waves driving 36 leg joints + head + mandibles
  2. shaking        - shakingC() > 0: adds subtle mainbody position shake (ox, oz)
  3. cosmic         - getCloneC() == true, shakingC() == 0: intense mainbody position shake
  4. cosmic_shaking - getCloneC() == true, shakingC() > 0: fast but dampened shake

Key Conversions:
  - M_MODEL = diag(1, -1, -1): rx stays, ry → -ry, rz → -rz for rotation
  - Position: ox stays, oy → -oy, oz → -oz
  - Radians to degrees for animation output
  - Time in seconds (20 ticks per second in MC)

Kirin-Specific Notes:
  - Uses 3 cosine waves (f11, f22, f33) for idle leg animation
  - f11 is REASSIGNED at line 873 for jointLM/jointRM (different frequency/amplitude)
  - f22 is REASSIGNED at line 874 for jointH (different frequency/amplitude)
  - No limbSwing-driven walking animation — all joints are ageInTicks-driven
  - Shaking/cosmic states only add mainbody position offsets on top of idle
"""

import json
import math
import os
import sys
from typing import Dict, List, Optional, Tuple

# ============================================================================
# Constants
# ============================================================================
TICKS_PER_SECOND = 20.0
RAD_TO_DEG = 180.0 / math.pi


# ============================================================================
# Douglas-Peucker Line Simplification
# ============================================================================

def _dp_simplify(points: List[Tuple[float, float]], epsilon: float) -> List[Tuple[float, float]]:
    """Douglas-Peucker simplification for (time, value) keyframe pairs."""
    if len(points) <= 2:
        return points

    start, end = points[0], points[-1]
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    line_len_sq = dx * dx + dy * dy

    max_dist = 0.0
    max_idx = 0
    for i in range(1, len(points) - 1):
        if line_len_sq < 1e-12:
            dist = math.hypot(points[i][0] - start[0], points[i][1] - start[1])
        else:
            t = ((points[i][0] - start[0]) * dx + (points[i][1] - start[1]) * dy) / line_len_sq
            t = max(0.0, min(1.0, t))
            proj_x = start[0] + t * dx
            proj_y = start[1] + t * dy
            dist = math.hypot(points[i][0] - proj_x, points[i][1] - proj_y)

        if dist > max_dist:
            max_dist = dist
            max_idx = i

    if max_dist > epsilon:
        left = _dp_simplify(points[:max_idx + 1], epsilon)
        right = _dp_simplify(points[max_idx:], epsilon)
        return left[:-1] + right
    else:
        return [points[0], points[-1]]


def simplify_keyframes(time_value_pairs: List[Tuple[float, float]],
                       epsilon: float = 0.15) -> List[Tuple[float, float]]:
    """Simplify a list of (time, value) pairs using Douglas-Peucker."""
    if len(time_value_pairs) <= 2:
        return time_value_pairs
    result = _dp_simplify(time_value_pairs, epsilon)
    return result


def rad_to_deg(val: float) -> float:
    """Convert radians to degrees."""
    return val * RAD_TO_DEG


# ============================================================================
# Loop Continuity Enforcement
# ============================================================================

def enforce_loop_continuity(sampled_data: Dict, duration: float) -> Dict:
    """Ensure the first and last keyframes match for seamless looping.

    For loop animations, the value at t=0 and t=duration should be identical.
    We adjust the last keyframe to match the first.
    """
    for bone_name, channels in sampled_data.items():
        for channel, keyframes in channels.items():
            if len(keyframes) >= 2:
                first_val = keyframes[0][1]
                last_val = keyframes[-1][1]
                # Use 1.0 degree threshold for rotation channels
                # and 0.1 for position channels (position offsets are much smaller)
                threshold = 1.0 if channel.startswith('r') else 0.1
                if abs(first_val - last_val) < threshold:
                    keyframes[-1] = (keyframes[-1][0], first_val)
    return sampled_data


# ============================================================================
# Animation State Evaluators
# ============================================================================

def _add_idle_leg_animations(bones: Dict, age_in_ticks: float):
    """Add the 36 leg joint animations using 3 cosine waves.

    From ModelKirin.java lines 837-872:
      f11 = cos(ageInTicks * 0.130998) * 0.107215
      f22 = cos(ageInTicks * 0.0819112) * 0.1206261
      f33 = cos(ageInTicks * 0.0627955) * 0.09067262

    SRG field mapping:
      field_78795_f = rotateAngleX (rx)
      field_78796_g = rotateAngleY (ry)
      field_78808_h = rotateAngleZ (rz)
    """
    f11 = math.cos(age_in_ticks * 0.130998) * 0.107215
    f22 = math.cos(age_in_ticks * 0.0819112) * 0.1206261
    f33 = math.cos(age_in_ticks * 0.0627955) * 0.09067262

    # Upper Right Arm (URA) group
    bones['jointURAX'] = {'rx': -f11}          # line 837: jointURAX.rx = -f11
    bones['jointURAY'] = {'ry': f22}           # line 838: jointURAY.ry = f22
    bones['jointURA1'] = {'ry': -f33}          # line 839: jointURA1.ry = -f33
    bones['jointURA2'] = {'rz': -f11}          # line 840: jointURA2.rz = -f11
    bones['jointURA3'] = {'ry': f22}           # line 841: jointURA3.ry = f22
    bones['jointURA4'] = {'rz': -f22}          # line 842: jointURA4.rz = -f22

    # Upper Left Arm (ULA) group
    bones['jointULAX'] = {'rx': f11}           # line 843: jointULAX.rx = f11
    bones['jointULAY'] = {'ry': f33}           # line 844: jointULAY.ry = f33
    bones['jointULA1'] = {'ry': -f11}          # line 845: jointULA1.ry = -f11
    bones['jointULA2'] = {'rz': f11}           # line 846: jointULA2.rz = f11
    bones['jointULA3'] = {'ry': -f22}          # line 847: jointULA3.ry = -f22
    bones['jointULA4'] = {'rz': f33}           # line 848: jointULA4.rz = f33

    # Mid Right Arm (MRA) group
    bones['jointMRAX'] = {'rx': f11}           # line 849: jointMRAX.rx = f11
    bones['jointMRAY'] = {'ry': f33}           # line 850: jointMRAY.ry = f33
    bones['jointMRA1'] = {'ry': -f22}          # line 851: jointMRA1.ry = -f22
    bones['jointMRA2'] = {'rz': f22}           # line 852: jointMRA2.rz = f22
    bones['jointMRA3'] = {'ry': -f11}          # line 853: jointMRA3.ry = -f11
    bones['jointMRA4'] = {'rz': -f22}          # line 854: jointMRA4.rz = -f22

    # Mid Left Arm (MLA) group
    bones['jointMLAX'] = {'rx': -f33}          # line 855: jointMLAX.rx = -f33
    bones['jointMLAY'] = {'ry': f33}           # line 856: jointMLAY.ry = f33
    bones['jointMLA1'] = {'ry': -f22}          # line 857: jointMLA1.ry = -f22
    bones['jointMLA2'] = {'rz': -f11}          # line 858: jointMLA2.rz = -f11
    bones['jointMLA3'] = {'ry': f22}           # line 859: jointMLA3.ry = f22
    bones['jointMLA4'] = {'rz': -f11}          # line 860: jointMLA4.rz = -f11

    # Down Right Arm (DRA) group
    bones['jointDRAX'] = {'rx': f11}           # line 861: jointDRAX.rx = f11
    bones['jointDRAY'] = {'ry': -f22}          # line 862: jointDRAY.ry = -f22
    bones['jointDRA1'] = {'ry': -f22}          # line 863: jointDRA1.ry = -f22
    bones['jointDRA2'] = {'rz': -f22}          # line 864: jointDRA2.rz = -f22
    bones['jointDRA3'] = {'ry': f22}           # line 865: jointDRA3.ry = f22
    bones['jointDRA4'] = {'rz': f22}           # line 866: jointDRA4.rz = f22

    # Down Left Arm (DLA) group
    bones['jointDLAX'] = {'rx': -f11}          # line 867: jointDLAX.rx = -f11
    bones['jointDLAY'] = {'ry': -f22}          # line 868: jointDLAY.ry = -f22
    bones['jointDLA1'] = {'ry': f22}           # line 869: jointDLA1.ry = f22
    bones['jointDLA2'] = {'rz': f22}           # line 870: jointDLA2.rz = f22
    bones['jointDLA3'] = {'ry': -f22}          # line 871: jointDLA3.ry = -f22
    bones['jointDLA4'] = {'rz': f22}           # line 872: jointDLA4.rz = f22


def _add_head_mandible_animations(bones: Dict, age_in_ticks: float):
    """Add head and mandible animations using REASSIGNED f11 and f22.

    From ModelKirin.java lines 873-876:
      f11 = cos(ageInTicks * 0.1730998) * 0.1307215    (REASSIGNED)
      jointH.rx = f22 = cos(ageInTicks * 0.09819112) * 0.1720626  (f22 REASSIGNED via compound)
      jointLM.ry = f11  (new value)
      jointRM.ry = -f11 (new value)

    Note: jointH.rx uses the NEW f22 value (0.09819112, 0.1720626),
          NOT the old one (0.0819112, 0.1206261).
    """
    # Reassigned f11 for mandibles
    f11_new = math.cos(age_in_ticks * 0.1730998) * 0.1307215

    # Reassigned f22 for head (compound assignment)
    f22_new = math.cos(age_in_ticks * 0.09819112) * 0.1720626

    bones['jointH'] = {'rx': f22_new}           # line 874: jointH.rx = f22 = ...
    bones['jointLM'] = {'ry': f11_new}          # line 875: jointLM.ry = f11
    bones['jointRM'] = {'ry': -f11_new}         # line 876: jointRM.ry = -f11


def eval_idle(t_seconds: float) -> Dict[str, Dict[str, float]]:
    """Evaluate animation for default idle state.

    All 36 leg joints driven by 3 cosine waves (f11, f22, f33).
    Head and mandibles driven by REASSIGNED f11 and f22.
    No mainbody position offset.

    Returns dict of bone_name -> {rx, ry, rz, ox, oy, oz} in MC 1.12.2 space.
    """
    age_in_ticks = t_seconds * TICKS_PER_SECOND

    bones = {}

    # 36 leg joint animations
    _add_idle_leg_animations(bones, age_in_ticks)

    # Head and mandible animations (using reassigned f11/f22)
    _add_head_mandible_animations(bones, age_in_ticks)

    # mainbody: no position offset in idle (ox/oy/oz = 0, initialized at top of method)
    # We still include it with zero offsets so the bone appears in the animation
    # for consistency with other states
    bones['mainbody'] = {}

    return bones


def eval_shaking(t_seconds: float) -> Dict[str, Dict[str, float]]:
    """Evaluate animation for shaking state (shakingC() > 0).

    From ModelKirin.java lines 877-883:
      mainbody.ox = cos(ageInTicks * 2.95) * 0.08912576
      mainbody.oz = cos(ageInTicks * 2.95) * 0.08912575

    This is layered ON TOP of the idle animation (legs still animate).
    """
    age_in_ticks = t_seconds * TICKS_PER_SECOND

    bones = {}

    # Same idle leg animations
    _add_idle_leg_animations(bones, age_in_ticks)

    # Same head/mandible animations
    _add_head_mandible_animations(bones, age_in_ticks)

    # Shaking position offsets
    ox = math.cos(age_in_ticks * 2.95) * 0.08912576
    oz = math.cos(age_in_ticks * 2.95) * 0.08912575
    bones['mainbody'] = {'ox': ox, 'oz': oz}

    return bones


def eval_cosmic(t_seconds: float) -> Dict[str, Dict[str, float]]:
    """Evaluate animation for cosmic state (getCloneC() == true, shakingC() == 0).

    From ModelKirin.java lines 884-898:
      amp = 1.0, dis = 1.0
      mainbody.ox = -cos(ageInTicks * 2.27 * amp) * 0.59 * dis
      mainbody.oz = -cos(ageInTicks * 2.6 * amp) * 0.55 * dis

    This OVERRIDES the shaking state (checked after shaking in code flow).
    Leg animations still run from the idle base.
    """
    age_in_ticks = t_seconds * TICKS_PER_SECOND

    bones = {}

    # Same idle leg animations
    _add_idle_leg_animations(bones, age_in_ticks)

    # Same head/mandible animations
    _add_head_mandible_animations(bones, age_in_ticks)

    # Cosmic position offsets (amp=1.0, dis=1.0)
    amp = 1.0
    dis = 1.0
    ox = -1.0 * math.cos(age_in_ticks * 2.27 * amp) * 0.59 * dis
    oz = -1.0 * math.cos(age_in_ticks * 2.6 * amp) * 0.55 * dis
    bones['mainbody'] = {'ox': ox, 'oz': oz}

    return bones


def eval_cosmic_shaking(t_seconds: float) -> Dict[str, Dict[str, float]]:
    """Evaluate animation for cosmic + shaking state (getCloneC() == true, shakingC() > 0).

    From ModelKirin.java lines 884-898:
      amp = 2.0, dis = 0.3
      mainbody.ox = -cos(ageInTicks * 2.27 * amp) * 0.59 * dis
      mainbody.oz = -cos(ageInTicks * 2.6 * amp) * 0.55 * dis

    Fast oscillation (2x frequency) but dampened (0.3x amplitude).
    Leg animations still run from the idle base.
    """
    age_in_ticks = t_seconds * TICKS_PER_SECOND

    bones = {}

    # Same idle leg animations
    _add_idle_leg_animations(bones, age_in_ticks)

    # Same head/mandible animations
    _add_head_mandible_animations(bones, age_in_ticks)

    # Cosmic position offsets with shaking parameters (amp=2.0, dis=0.3)
    amp = 2.0
    dis = 0.3
    ox = -1.0 * math.cos(age_in_ticks * 2.27 * amp) * 0.59 * dis
    oz = -1.0 * math.cos(age_in_ticks * 2.6 * amp) * 0.55 * dis
    bones['mainbody'] = {'ox': ox, 'oz': oz}

    return bones


# ============================================================================
# Animation Sampling and Keyframe Generation
# ============================================================================

def sample_animation(eval_func, duration: float, samples_per_second: float = 60.0,
                     dp_epsilon: float = 0.15) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
    """Sample an animation function over time and simplify with Douglas-Peucker.

    Returns: {bone_name: {channel: [(time, value), ...]}}

    Quality parameters:
    - samples_per_second: 60 for smooth motion
    - dp_epsilon: 0.15 degrees for preserving subtle detail
    """
    n_samples = max(int(duration * samples_per_second), 120)
    dt = duration / n_samples

    # Collect raw samples
    raw_channels: Dict[str, Dict[str, List[Tuple[float, float]]]] = {}

    for i in range(n_samples + 1):
        t = i * dt
        bone_values = eval_func(t)

        for bone_name, channels in bone_values.items():
            if bone_name not in raw_channels:
                raw_channels[bone_name] = {}
            for channel, value in channels.items():
                if channel not in raw_channels[bone_name]:
                    raw_channels[bone_name][channel] = []
                raw_channels[bone_name][channel].append((t, value))

    # Apply M_MODEL conversion and Douglas-Peucker simplification
    result: Dict[str, Dict[str, List[Tuple[float, float]]]] = {}

    for bone_name, channels in raw_channels.items():
        result[bone_name] = {}
        for channel, points in channels.items():
            # Apply M_MODEL conversion
            converted_points = []
            for t, val in points:
                if channel == 'rx':
                    converted_points.append((t, val))    # rx stays
                elif channel == 'ry':
                    converted_points.append((t, -val))   # ry → -ry
                elif channel == 'rz':
                    converted_points.append((t, -val))   # rz → -rz
                elif channel == 'ox':
                    converted_points.append((t, val))    # ox stays
                elif channel == 'oy':
                    converted_points.append((t, -val))   # oy → -oy
                elif channel == 'oz':
                    converted_points.append((t, -val))   # oz → -oz
                else:
                    converted_points.append((t, val))

            # Convert rotation from radians to degrees
            if channel in ('rx', 'ry', 'rz'):
                converted_points = [(t, rad_to_deg(v)) for t, v in converted_points]

            # Simplify with Douglas-Peucker
            simplified = simplify_keyframes(converted_points, epsilon=dp_epsilon)
            result[bone_name][channel] = simplified

    return result


# ============================================================================
# GeckoLib Animation JSON Generation
# ============================================================================

def _channel_to_axis(channel: str) -> str:
    """Convert internal channel name to GeckoLib axis name.
    rx -> x, ry -> y, rz -> z, ox -> x, oy -> y, oz -> z
    """
    return channel[-1]


def build_animation_json(anim_name: str, loop_mode: str,
                         sampled_data: Dict[str, Dict[str, List[Tuple[float, float]]]],
                         duration: float) -> dict:
    """Build a single GeckoLib animation entry from sampled data.

    Output uses GeckoLib axis names: "x", "y", "z" (not "rx", "ry", "rz").
    """
    bones_dict = {}

    for bone_name, channels in sampled_data.items():
        # Separate rotation and position channels
        rot_axes = {_channel_to_axis(k): v for k, v in channels.items()
                   if k in ('rx', 'ry', 'rz') and (len(v) > 1 or (len(v) == 1 and abs(v[0][1]) > 0.001))}
        pos_axes = {_channel_to_axis(k): v for k, v in channels.items()
                   if k in ('ox', 'oy', 'oz') and (len(v) > 1 or (len(v) == 1 and abs(v[0][1]) > 0.001))}

        # Build channel data dicts
        rot_channels = {}
        for axis, keyframes in rot_axes.items():
            if len(keyframes) <= 1:
                if len(keyframes) == 1 and abs(keyframes[0][1]) > 0.001:
                    rot_channels[axis] = {f"{t:.4f}": round(v, 6) for t, v in keyframes}
            else:
                rot_channels[axis] = {f"{t:.4f}": round(v, 6) for t, v in keyframes}

        pos_channels = {}
        for axis, keyframes in pos_axes.items():
            if len(keyframes) <= 1:
                if len(keyframes) == 1 and abs(keyframes[0][1]) > 0.001:
                    pos_channels[axis] = {f"{t:.4f}": round(v, 6) for t, v in keyframes}
            else:
                pos_channels[axis] = {f"{t:.4f}": round(v, 6) for t, v in keyframes}

        bone_entry = {}
        if rot_channels:
            bone_entry["rotation"] = rot_channels
        if pos_channels:
            bone_entry["position"] = pos_channels

        if bone_entry:
            bones_dict[bone_name] = bone_entry

    return {
        "loop": loop_mode,
        "animation_length": round(duration, 4),
        "bones": bones_dict
    }


# ============================================================================
# Period Analysis for Duration Alignment
# ============================================================================

def compute_periods() -> Dict[str, float]:
    """Compute the oscillation periods (in seconds) for all cosine waves in Kirin.

    Returns dict of wave_name -> period_in_seconds.

    Angular frequencies (rad/s) = frequency_coefficient * TICKS_PER_SECOND
    Period = 2π / angular_frequency
    """
    periods = {}

    # Initial 3 waves for legs
    periods['f11'] = 2 * math.pi / (0.130998 * TICKS_PER_SECOND)    # ~2.399s
    periods['f22'] = 2 * math.pi / (0.0819112 * TICKS_PER_SECOND)   # ~3.834s
    periods['f33'] = 2 * math.pi / (0.0627955 * TICKS_PER_SECOND)   # ~5.003s

    # Reassigned waves for head/mandibles
    periods['f11_new'] = 2 * math.pi / (0.1730998 * TICKS_PER_SECOND)  # ~1.815s
    periods['f22_new'] = 2 * math.pi / (0.09819112 * TICKS_PER_SECOND) # ~3.200s

    # Shaking/cosmic waves
    periods['shake'] = 2 * math.pi / (2.95 * TICKS_PER_SECOND)       # ~0.107s
    periods['cosmic_ox'] = 2 * math.pi / (2.27 * TICKS_PER_SECOND)   # ~0.138s
    periods['cosmic_oz'] = 2 * math.pi / (2.6 * TICKS_PER_SECOND)    # ~0.121s

    return periods


def find_best_loop_duration(periods_dict: Dict[str, float],
                            min_duration: float = 5.0,
                            max_duration: float = 60.0) -> float:
    """Find the best loop duration where all wave phases approximately realign.

    For Kirin's idle, the 5 different frequencies are incommensurate,
    so we search for a duration where the total phase error is minimized.
    """
    best_duration = min_duration
    best_error = float('inf')

    # Test durations from min to max in 0.1s steps
    for dur_10 in range(int(min_duration * 10), int(max_duration * 10) + 1):
        duration = dur_10 / 10.0
        total_error = 0.0
        for name, period in periods_dict.items():
            # How far from an integer number of cycles?
            n_cycles = duration / period
            fractional = n_cycles - int(n_cycles)
            # Phase error: how far from start phase
            phase_error = min(fractional, 1.0 - fractional)
            total_error += phase_error

        if total_error < best_error:
            best_error = total_error
            best_duration = duration

    return best_duration


# ============================================================================
# Generate All Animations
# ============================================================================

def generate_all_animations() -> dict:
    """Generate all animation states and return the complete .animation.json."""
    animations = {}

    # Compute period information for duration alignment
    periods = compute_periods()
    idle_periods = {k: v for k, v in periods.items()
                   if k in ('f11', 'f22', 'f33', 'f11_new', 'f22_new')}

    print(f"  Oscillation periods:")
    for name, period in sorted(periods.items()):
        print(f"    {name}: {period:.4f}s")

    # --- IDLE animation ---
    print("\n  Generating idle animation...")
    # Find a good loop duration for the 5 incommensurate frequencies
    # Use period analysis to find a duration where phases approximately align
    idle_duration = find_best_loop_duration(idle_periods, min_duration=5.0, max_duration=60.0)
    print(f"    Best loop duration: {idle_duration:.1f}s")

    idle_data = sample_animation(
        eval_idle,
        duration=idle_duration,
        samples_per_second=60.0,
        dp_epsilon=0.15
    )
    # Enforce loop continuity
    idle_data = enforce_loop_continuity(idle_data, idle_duration)

    animations["animation.srparasites.kirin.idle"] = build_animation_json(
        "animation.srparasites.kirin.idle", "loop", idle_data, idle_duration
    )
    idle_bone_count = len(animations["animation.srparasites.kirin.idle"]["bones"])
    print(f"    Bones: {idle_bone_count}, Duration: {idle_duration}s")

    # --- SHAKING animation ---
    print("  Generating shaking animation...")
    # Shaking frequency: 2.95*20 = 59 rad/s → period = 0.1066s
    # Use integer cycles: 38 cycles × 0.1066s ≈ 4.05s
    shake_period = 2 * math.pi / (2.95 * TICKS_PER_SECOND)
    n_shake_cycles = round(4.0 / shake_period)
    shaking_duration = n_shake_cycles * shake_period
    print(f"    Shake period: {shake_period:.4f}s, using {n_shake_cycles} cycles = {shaking_duration:.4f}s")

    shaking_data = sample_animation(
        eval_shaking,
        duration=shaking_duration,
        samples_per_second=60.0,
        dp_epsilon=0.15
    )
    shaking_data = enforce_loop_continuity(shaking_data, shaking_duration)

    animations["animation.srparasites.kirin.shaking"] = build_animation_json(
        "animation.srparasites.kirin.shaking", "loop", shaking_data, shaking_duration
    )
    shaking_bone_count = len(animations["animation.srparasites.kirin.shaking"]["bones"])
    print(f"    Bones: {shaking_bone_count}, Duration: {shaking_duration:.4f}s")

    # --- COSMIC animation ---
    print("  Generating cosmic animation...")
    # Cosmic has 2 frequencies:
    #   ox: 2.27*20 = 45.4 rad/s → period = 0.1384s
    #   oz: 2.6*20 = 52.0 rad/s → period = 0.1208s
    # Find a common duration for both
    cosmic_ox_period = 2 * math.pi / (2.27 * TICKS_PER_SECOND)
    cosmic_oz_period = 2 * math.pi / (2.6 * TICKS_PER_SECOND)
    # Use ~4s with integer cycles of both frequencies
    # Find best duration that's integer multiples of both periods
    best_cosmic_dur = 4.0
    best_cosmic_error = float('inf')
    for dur_100 in range(300, 601):  # 3.0 to 6.0 in 0.01 steps
        dur = dur_100 / 100.0
        err = 0.0
        for period in [cosmic_ox_period, cosmic_oz_period]:
            n_cycles = dur / period
            frac = n_cycles - int(n_cycles)
            err += min(frac, 1.0 - frac)
        if err < best_cosmic_error:
            best_cosmic_error = err
            best_cosmic_dur = dur
    cosmic_duration = best_cosmic_dur
    print(f"    Cosmic ox period: {cosmic_ox_period:.4f}s, oz period: {cosmic_oz_period:.4f}s")
    print(f"    Using {cosmic_duration:.2f}s (error: {best_cosmic_error:.4f})")

    cosmic_data = sample_animation(
        eval_cosmic,
        duration=cosmic_duration,
        samples_per_second=60.0,
        dp_epsilon=0.15
    )
    cosmic_data = enforce_loop_continuity(cosmic_data, cosmic_duration)

    animations["animation.srparasites.kirin.cosmic"] = build_animation_json(
        "animation.srparasites.kirin.cosmic", "loop", cosmic_data, cosmic_duration
    )
    cosmic_bone_count = len(animations["animation.srparasites.kirin.cosmic"]["bones"])
    print(f"    Bones: {cosmic_bone_count}, Duration: {cosmic_duration:.2f}s")

    # --- COSMIC SHAKING animation ---
    print("  Generating cosmic_shaking animation...")
    # amp=2.0 doubles the frequency:
    #   ox: 2.27*2*20 = 90.8 rad/s → period = 0.0692s
    #   oz: 2.6*2*20 = 104.0 rad/s → period = 0.0604s
    cosmic_shake_ox_period = 2 * math.pi / (2.27 * 2.0 * TICKS_PER_SECOND)
    cosmic_shake_oz_period = 2 * math.pi / (2.6 * 2.0 * TICKS_PER_SECOND)
    # Use ~4s with integer cycles of both frequencies
    best_cs_dur = 4.0
    best_cs_error = float('inf')
    for dur_100 in range(300, 601):  # 3.0 to 6.0 in 0.01 steps
        dur = dur_100 / 100.0
        err = 0.0
        for period in [cosmic_shake_ox_period, cosmic_shake_oz_period]:
            n_cycles = dur / period
            frac = n_cycles - int(n_cycles)
            err += min(frac, 1.0 - frac)
        if err < best_cs_error:
            best_cs_error = err
            best_cs_dur = dur
    cosmic_shaking_duration = best_cs_dur
    print(f"    Cosmic_shake ox period: {cosmic_shake_ox_period:.4f}s, oz period: {cosmic_shake_oz_period:.4f}s")
    print(f"    Using {cosmic_shaking_duration:.2f}s (error: {best_cs_error:.4f})")

    cosmic_shaking_data = sample_animation(
        eval_cosmic_shaking,
        duration=cosmic_shaking_duration,
        samples_per_second=60.0,
        dp_epsilon=0.15
    )
    cosmic_shaking_data = enforce_loop_continuity(cosmic_shaking_data, cosmic_shaking_duration)

    animations["animation.srparasites.kirin.cosmic_shaking"] = build_animation_json(
        "animation.srparasites.kirin.cosmic_shaking", "loop", cosmic_shaking_data, cosmic_shaking_duration
    )
    cosmic_shaking_bone_count = len(animations["animation.srparasites.kirin.cosmic_shaking"]["bones"])
    print(f"    Bones: {cosmic_shaking_bone_count}, Duration: {cosmic_shaking_duration:.2f}s")

    return {
        "format_version": "1.8.0",
        "animations": animations
    }


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    print("=" * 70)
    print("  Kirin Animation Generator")
    print("  MC 1.12.2 → GeckoLib 1.20.1 Animation Conversion")
    print("=" * 70)
    print()

    # Generate all animations
    anim_json = generate_all_animations()

    # Determine output paths
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(project_root, "db", "kirin.animation.json")
    output_path = os.path.join(project_root, "converter", "output", "kirin.animation.json")

    # Save animation JSON
    anim_json_str = json.dumps(anim_json, indent=2, ensure_ascii=False)

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(db_path, 'w', encoding='utf-8') as f:
        f.write(anim_json_str)
    print(f"\n  Saved animation JSON to: {db_path}")

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(anim_json_str)
    print(f"  Saved animation JSON to: {output_path}")

    # Statistics
    total_size = len(anim_json_str)
    print(f"\n  Total file size: {total_size:,} bytes")
    for anim_name, anim_data in anim_json.get('animations', {}).items():
        n_bones = len(anim_data.get('bones', {}))
        total_keyframes = 0
        for bone_data in anim_data.get('bones', {}).values():
            for channel_data in bone_data.values():
                total_keyframes += len(channel_data)
        print(f"    {anim_name}: {n_bones} bones, {total_keyframes} keyframes, "
              f"length={anim_data.get('animation_length', 0)}s, "
              f"loop={anim_data.get('loop', 'unknown')}")

    print("\n" + "=" * 70)
    print("  DONE - Kirin Animation Generator")
    print("=" * 70)

    return anim_json


if __name__ == "__main__":
    main()
