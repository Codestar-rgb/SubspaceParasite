#!/usr/bin/env python3
"""
HebluAnimationGenerator - Comprehensive Animation Converter for Heblu (Draconite)
================================================================================
Parses the original MC 1.12.2 Java animation code from ModelHeblu.java and
generates high-quality GeckoLib .animation.json files for each entity state.

Animation States:
  1. idle      - parasiteStatus=0, not flying (subtle body, wing, neck, tail, hair sway)
  2. attack    - parasiteStatus=1/2, not flying (faster walking, more intense sway)
  3. fly       - getFlyingState=true (large wing flapping, hovering, different legs)
  4. vomit     - vomit>0, not flying (head/neck articulated fire-breath animation)
  5. fly_vomit - vomit>0, flying (neck override during flight)
  6. shaking   - shakingC>0, not clone (subtle body vibration)
  7. cosmic    - getCloneC=true, shakingC=0 (body shaking oscillation)
  8. cosmic_shaking - getCloneC=true, shakingC>0 (fast dampened shaking)

Key Conversions:
  - M_MODEL = diag(1, -1, -1): rx stays, ry → -ry, rz → -rz for rotation
  - Position: ox stays, oy → -oy, oz → -oz
  - Radians to degrees for animation output
  - Time in seconds (20 ticks per second in MC)

Quality Improvements over v1:
  - Period-aware duration for seamless loop matching
  - Higher sampling rate (60 fps) for smooth motion
  - Lower DP epsilon for preserving subtle motion detail
  - Start/end value matching for perfect loop continuity
  - Additional animation states (cosmic, fly_vomit)
  - Proper handling of MC variable reassignment (last value wins)
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
# MC Animation Helper Functions (from ModelSRP.java)
# ============================================================================

def swing_x_8(speed: float, degree: float, invert: int,
              offset: float, weight: float,
              limb_swing: float, limb_swing_amount: float) -> float:
    """swingX(bone, speed, degree, invert, offset, weight, limbSwing, limbSwingAmount)
    bone.rx = invert * limbSwingAmount * degree * cos(limbSwing * speed + offset) + weight * limbSwingAmount
    """
    return (invert * limb_swing_amount * degree *
            math.cos(limb_swing * speed + offset) +
            weight * limb_swing_amount)


def swing_z_8(speed: float, degree: float, invert: int,
              offset: float, weight: float,
              limb_swing: float, limb_swing_amount: float) -> float:
    """swingZ(bone, speed, degree, invert, offset, weight, limbSwing, limbSwingAmount)
    bone.rz = invert * limbSwingAmount * degree * cos(limbSwing * speed + offset) + weight * limbSwingAmount
    """
    return (invert * limb_swing_amount * degree *
            math.cos(limb_swing * speed + offset) +
            weight * limb_swing_amount)


def move_y(speed: float, invert: int,
           limb_swing: float, limb_swing_amount: float,
           distance: float) -> float:
    """moveY(bone, speed, invert, f, f1, distance)
    bone.oy = invert * cos(f * speed) * f1 * distance
    where f=limbSwing, f1=limbSwingAmount
    """
    return invert * math.cos(limb_swing * speed) * limb_swing_amount * distance


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
                       epsilon: float = 0.05) -> List[Tuple[float, float]]:
    """Simplify a list of (time, value) pairs using Douglas-Peucker."""
    if len(time_value_pairs) <= 2:
        return time_value_pairs
    result = _dp_simplify(time_value_pairs, epsilon)
    return result


# ============================================================================
# M_MODEL Coordinate Conversion
# ============================================================================

def convert_rotation(rx: float, ry: float, rz: float) -> Tuple[float, float, float]:
    """Apply M_MODEL = diag(1, -1, -1) to rotation angles.
    rx stays, ry → -ry, rz → -rz
    """
    return (rx, -ry, -rz)


def convert_position(ox: float, oy: float, oz: float) -> Tuple[float, float, float]:
    """Apply M_MODEL = diag(1, -1, -1) to position offsets.
    ox stays, oy → -oy, oz → -oz
    """
    return (ox, -oy, -oz)


def rad_to_deg(val: float) -> float:
    """Convert radians to degrees."""
    return val * RAD_TO_DEG


# ============================================================================
# Period Analysis for Smooth Looping
# ============================================================================

def analyze_dominant_periods(eval_func, test_duration: float = 30.0,
                             sample_rate: float = 60.0) -> float:
    """Analyze the dominant oscillation periods and find the best loop duration.
    
    For smooth looping, we want a duration where all major oscillation components
    approximately return to their starting values. We sample a reference bone
    and find the shortest duration > 2s where the values closely match the start.
    """
    n_samples = int(test_duration * sample_rate)
    dt = test_duration / n_samples
    
    # Sample all bone values over time
    start_values = eval_func(0.0)
    if not start_values:
        return 8.0
    
    # Collect all channel values for reference bones
    ref_data = {}
    for bone_name, channels in start_values.items():
        for channel, value in channels.items():
            key = f"{bone_name}.{channel}"
            ref_data[key] = [(0.0, value)]
    
    # Sample over time
    for i in range(1, n_samples + 1):
        t = i * dt
        bone_values = eval_func(t)
        for bone_name, channels in bone_values.items():
            for channel, value in channels.items():
                key = f"{bone_name}.{channel}"
                if key in ref_data:
                    ref_data[key].append((t, value))
    
    # Find the best loop point by checking when ALL channels closely match start
    best_duration = test_duration
    best_error = float('inf')
    
    for i in range(int(2.0 * sample_rate), n_samples + 1):  # Start from 2 seconds
        t = i * dt
        total_error = 0.0
        count = 0
        for key, samples in ref_data.items():
            start_val = samples[0][1]
            # Find the sample closest to time t
            for j in range(len(samples) - 1, -1, -1):
                if samples[j][0] <= t:
                    current_val = samples[j][1]
                    break
            else:
                current_val = start_val
            
            total_error += abs(current_val - start_val)
            count += 1
        
        avg_error = total_error / max(count, 1)
        
        # Prefer shorter durations with low error
        if avg_error < 0.002:  # Very close match threshold
            if t < best_duration:
                best_duration = t
                best_error = avg_error
                break  # Take the first good match
    
    return round(best_duration, 4)


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
                # If the difference is small but non-zero, snap the last to match first
                # Use 1.0 degree threshold for rotation channels (hair oscillations can be ~10° off)
                # and 0.1 for position channels (position offsets are much smaller)
                threshold = 1.0 if channel.startswith('r') else 0.1
                if abs(first_val - last_val) < threshold:
                    keyframes[-1] = (keyframes[-1][0], first_val)
    return sampled_data


# ============================================================================
# Animation State Evaluators
# ============================================================================

def eval_idle(t_seconds: float, limb_swing_amount: float = 0.5) -> Dict[str, Dict[str, float]]:
    """Evaluate animation for parasiteStatus=0 (idle/walking, not flying).
    
    Returns dict of bone_name -> {rx, ry, rz, ox, oy, oz} in MC 1.12.2 space.
    
    IMPORTANT: The Java source (line 2276) wraps the walking animation in
    if (!getStillAni()), meaning when the entity is standing still, legs and
    mainbody bob are NOT animated. We include the walking variant here.
    See eval_idle_still for the standing-still variant.
    """
    # Convert time to MC parameters
    age_in_ticks = t_seconds * TICKS_PER_SECOND
    limb_swing = limb_swing_amount * age_in_ticks  # walking entity

    GS = 0.9
    GD = 0.3

    bones = {}

    # === Transition resets: explicitly zero bones that are non-zero in fly state ===
    # mainbody.rx = 0 (Java line 2096 reset; fly sets rx=-0.8)
    # mainbody.ox = 0, mainbody.oz = 0 (Java lines 2499-2500)
    bones['mainbody'] = {'rx': 0.0, 'ox': 0.0, 'oz': 0.0}

    # === Walking leg animation (swingX with 8 params) ===
    bones['jointBBLL'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, 1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointBBRL'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, -1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointBBLL_2'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, 1, 1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointBBRL_2'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, -1, 1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointBLL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, -1, 1.0, -0.0, limb_swing, limb_swing_amount)}
    bones['jointBRL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, 1, 1.0, -0.0, limb_swing, limb_swing_amount)}
    bones['jointBLL_2'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, 1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointBRL_2'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, -1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointFLL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, 1, 1.0, -0.4, limb_swing, limb_swing_amount)}
    bones['jointFL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, -1, 1.0, -0.4, limb_swing, limb_swing_amount)}
    bones['jointFLL_1'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, 1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointFRL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, -1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointFFLL'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, -1, 1.0, -0.1, limb_swing, limb_swing_amount)}
    bones['jointFFRL'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, 1, 1.0, -0.1, limb_swing, limb_swing_amount)}
    bones['jointFFLL_1'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, -1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointFFRL_1'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, 1, -1.0, 0.0, limb_swing, limb_swing_amount)}

    # moveY on mainbody
    bones['mainbody']['oy'] = move_y(0.6*GS, 1, limb_swing, limb_swing_amount, 0.18)

    # === Wing subtle motion (ageInTicks-driven) ===
    # f1 = cos(ageInTicks * 0.1) * 0.3  ← overwritten by next line (Java line 2297→2298)
    f1_wing = math.cos(age_in_ticks * 0.09) * 0.08
    # Transition resets: wing joints have rx/ry from flight, must zero them
    bones['jointLW1'] = {'rx': 0.0, 'ry': 0.0, 'rz': -0.1 + f1_wing}
    bones['jointLW1_1'] = {'rz': 0.0}  # Reset: flight sets rz via swingZ
    bones['jointLW2'] = {'rz': f1_wing}
    bones['jointRW1'] = {'rx': 0.0, 'ry': 0.0, 'rz': 0.1 + f1_wing}
    bones['jointRW1_1'] = {'rz': 0.0}  # Reset: flight sets rz via swingZ
    bones['jointRW2'] = {'rz': f1_wing}

    # === Neck/tentacle sway (ageInTicks-driven) ===
    # Last assignments (idle mode):
    f1_neck = math.cos(age_in_ticks * 0.0751) * 0.06
    f2_neck = math.cos(age_in_ticks * 0.0872) * 0.0411
    f3_neck = math.cos(age_in_ticks * 0.09669) * 0.075

    bones['jointN1'] = {'rx': -f1_neck, 'ry': f2_neck, 'rz': -f3_neck}
    bones['jointN2'] = {'rx': f1_neck, 'ry': f2_neck, 'rz': f3_neck}
    bones['jointN3'] = {'rx': -f1_neck, 'ry': -f2_neck, 'rz': f3_neck}
    bones['jointN4'] = {'rx': -f1_neck, 'ry': f2_neck, 'rz': -f3_neck}
    bones['jointN5'] = {'rx': f1_neck, 'ry': -f2_neck, 'rz': -f3_neck}

    # === Tail sway ===
    f1_tail = math.cos(age_in_ticks * 0.091) * 0.1
    for name in ['jointT1', 'jointT_1', 'jointT_3', 'jointT_5', 'jointT_7', 'jointT_9', 'jointT_11']:
        bones[name] = {'ry': f1_tail}

    # === Hair joints (common for all non-flying states) ===
    _add_hair_animations(bones, age_in_ticks)

    # === Mouth joints (common for all non-flying states) ===
    _add_mouth_animations(bones, age_in_ticks)

    return bones


def eval_attack(t_seconds: float, limb_swing_amount: float = 0.5) -> Dict[str, Dict[str, float]]:
    """Evaluate animation for parasiteStatus=1/2 (aggressive, not flying)."""
    age_in_ticks = t_seconds * TICKS_PER_SECOND
    limb_swing = limb_swing_amount * age_in_ticks

    GS = 1.0
    GD = 0.25

    bones = {}

    # === Walking leg animation (faster/different proportions) ===
    bones['jointBBLL'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, 1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointBBRL'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, -1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointBBLL_2'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, 1, 1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointBBRL_2'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, -1, 1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointBLL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, -1, 1.0, -0.0, limb_swing, limb_swing_amount)}
    bones['jointBRL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, 1, 1.0, -0.0, limb_swing, limb_swing_amount)}
    bones['jointBLL_2'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, 1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointBRL_2'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, -1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointFLL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, 1, 1.0, -0.4, limb_swing, limb_swing_amount)}
    bones['jointFL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, -1, 1.0, -0.4, limb_swing, limb_swing_amount)}
    bones['jointFLL_1'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, 1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointFRL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, -1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointFFLL'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, -1, 1.0, -0.1, limb_swing, limb_swing_amount)}
    bones['jointFFRL'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, 1, 1.0, -0.1, limb_swing, limb_swing_amount)}
    bones['jointFFLL_1'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, -1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointFFRL_1'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, 1, -1.0, 0.0, limb_swing, limb_swing_amount)}

    # Transition resets + moveY on mainbody
    bones['mainbody'] = {'rx': 0.0, 'ox': 0.0, 'oz': 0.0}
    bones['mainbody']['oy'] = move_y(0.6*GS, 1, limb_swing, limb_swing_amount, 0.2)

    # === Wing motion ===
    f1_wing = math.cos(age_in_ticks * 0.09) * 0.08
    # Transition resets: wing joints have rx/ry from flight
    bones['jointLW1'] = {'rx': 0.0, 'ry': 0.0, 'rz': -0.1 + f1_wing}
    bones['jointLW1_1'] = {'rz': 0.0}  # Reset: flight sets rz via swingZ
    bones['jointLW2'] = {'rz': f1_wing}
    bones['jointRW1'] = {'rx': 0.0, 'ry': 0.0, 'rz': 0.1 + f1_wing}
    bones['jointRW1_1'] = {'rz': 0.0}  # Reset: flight sets rz via swingZ
    bones['jointRW2'] = {'rz': f1_wing}

    # === Neck/tentacle - MORE INTENSE (larger amplitudes) ===
    f1_neck = math.cos(age_in_ticks * 0.0751) * 0.2106
    f2_neck = math.cos(age_in_ticks * 0.0872) * 0.107411
    f3_neck = math.cos(age_in_ticks * 0.09669) * 0.15075

    bones['jointN1'] = {'rx': -f1_neck, 'ry': f2_neck, 'rz': -f3_neck}
    bones['jointN2'] = {'rx': f1_neck, 'ry': f2_neck, 'rz': f3_neck}
    bones['jointN3'] = {'rx': -f1_neck, 'ry': -f2_neck, 'rz': f3_neck}
    bones['jointN4'] = {'rx': -f1_neck, 'ry': f2_neck, 'rz': -f3_neck}
    bones['jointN5'] = {'rx': f1_neck, 'ry': -f2_neck, 'rz': -f3_neck}

    # === Tail sway (faster in attack mode) ===
    f1_tail = math.cos(age_in_ticks * 0.191) * 0.2
    for name in ['jointT1', 'jointT_1', 'jointT_3', 'jointT_5', 'jointT_7', 'jointT_9', 'jointT_11']:
        bones[name] = {'ry': f1_tail}

    # === Hair joints (same as idle) ===
    _add_hair_animations(bones, age_in_ticks)

    # === Mouth joints (same as idle) ===
    _add_mouth_animations(bones, age_in_ticks)

    return bones


def eval_fly(t_seconds: float) -> Dict[str, Dict[str, float]]:
    """Evaluate animation for getFlyingState=true (flying)."""
    age_in_ticks = t_seconds * TICKS_PER_SECOND
    # In flight: limbSwing = getaaa() which increments by 0.08f per tick
    # limbSwingAmount = 0.5f
    limb_swing = 0.08 * age_in_ticks  # getaaa() equivalent
    limb_swing_amount = 0.5
    speed = 2.5

    bones = {}

    # === Body hovering ===
    bones['mainbody'] = {'rx': -0.8, 'ox': 0.0, 'oz': 0.0}  # mainbody.rx = -0.8 (tilted forward)

    # Hover oscillation: mainbody.oy = cos(ageInTicks * 0.2) * 0.72
    f12_hover = math.cos(age_in_ticks * 0.2) * 0.72
    bones['mainbody']['oy'] = f12_hover

    # === Wing flapping (large swingZ) ===
    # Left wing: rx=0.5, ry=0.5 (Java lines 2106-2107), rz stays 0 from initial reset
    bones['jointLW1'] = {'rx': 0.5, 'ry': 0.5, 'rz': 0.0}
    bones['jointLW1_1'] = {'rz': swing_z_8(speed, 2.0, 1, -2.0, 0.8, limb_swing, limb_swing_amount)}
    bones['jointLW2'] = {'rz': swing_z_8(speed, 1.9, 1, 2.5, -1.0, limb_swing, limb_swing_amount)}

    # Right wing: rx=0.5, ry=-0.5 (Java lines 2110-2111), rz stays 0 from initial reset
    bones['jointRW1'] = {'rx': 0.5, 'ry': -0.5, 'rz': 0.0}
    bones['jointRW1_1'] = {'rz': swing_z_8(speed, 2.0, -1, -2.0, -0.8, limb_swing, limb_swing_amount)}
    bones['jointRW2'] = {'rz': swing_z_8(speed, 1.9, -1, 2.5, 1.0, limb_swing, limb_swing_amount)}

    # === Legs in flight position ===
    f12_legs = math.cos(age_in_ticks * 0.18) * 0.12

    bones['jointBBLL'] = {'rx': 0.8 + f12_legs}
    bones['jointBBRL'] = {'rx': 0.75 + -1.0 * f12_legs}
    bones['jointBLL'] = {'rx': 0.6 + -1.0 * f12_legs}
    bones['jointBRL'] = {'rx': 0.65 + f12_legs}

    # Leg sub-joints: explicitly reset to 0 for clean transitions from walk state
    # (Java lines ~2039-2044: jointFFLL_1.rx=0, jointFFRL_1.rx=0, jointFLL_1.rx=0, jointFL.rx=0)
    bones['jointBBLL_2'] = {'rx': 0.0}  # Reset from walk swingX
    bones['jointBBRL_2'] = {'rx': 0.0}  # Reset from walk swingX
    bones['jointBLL_2'] = {'rx': 0.0}   # Reset from walk swingX
    bones['jointBRL_2'] = {'rx': 0.0}   # Reset from walk swingX
    bones['jointFL'] = {'rx': 0.0}       # Reset from walk swingX
    bones['jointFLL_1'] = {'rx': 0.0}    # Reset from walk swingX
    bones['jointFFLL_1'] = {'rx': 0.0}   # Reset from walk swingX
    bones['jointFFRL_1'] = {'rx': 0.0}   # Reset from walk swingX

    f12_front = math.cos(age_in_ticks * 0.17) * 0.1
    bones['jointFLL'] = {'rx': 0.5 + f12_front}
    bones['jointFRL'] = {'rx': 0.555 + f12_front}
    bones['jointFFLL'] = {'rx': 0.5 + f12_front}
    bones['jointFFRL'] = {'rx': 0.51 + f12_front}

    # === Neck in flight ===
    f12_neck = math.cos(age_in_ticks * 0.0751) * 0.0512106
    f22_neck = math.cos(age_in_ticks * 0.0872) * 0.06107411
    f32_neck = math.cos(age_in_ticks * 0.09669) * 0.0515075

    bones['jointN1'] = {'rx': 0.4 + f12_neck, 'ry': f22_neck, 'rz': f32_neck}
    bones['jointN2'] = {'rx': 0.4 + f12_neck, 'ry': f22_neck, 'rz': f32_neck}
    bones['jointN3'] = {'rx': 0.3 + f12_neck, 'ry': f22_neck, 'rz': f32_neck}
    bones['jointN4'] = {'rx': 0.3 + f12_neck, 'ry': f22_neck, 'rz': f32_neck}
    bones['jointN5'] = {'rx': 0.3 + f12_neck, 'ry': f22_neck, 'rz': f32_neck}

    # === Tail in flight ===
    f12_tail = math.cos(age_in_ticks * 0.14) * 0.4
    for name in ['jointT1', 'jointT_1', 'jointT_3', 'jointT_5', 'jointT_7', 'jointT_9', 'jointT_11']:
        bones[name] = {'ry': f12_tail}

    # === Hair joints in flight ===
    _add_hair_animations_flight(bones, age_in_ticks)

    # === Mouth joints in flight ===
    _add_mouth_animations_flight(bones, age_in_ticks)

    return bones


def eval_vomit(t_seconds: float, raining: bool = False, flying: bool = False) -> Dict[str, Dict[str, float]]:
    """Evaluate vomit/fire-breath animation (vomit > 0).
    This overrides the neck positions from whatever base state is active.
    For standalone preview, we include the neck animation plus minimal body.
    """
    age_in_ticks = t_seconds * TICKS_PER_SECOND

    bones = {}

    if flying:
        # Flight + vomit: same as fly but with different neck angles
        # From lines 2231-2270 of ModelHeblu.java
        bones['mainbody'] = {'rx': -0.8, 'ox': 0.0, 'oz': 0.0}
        f12_hover = math.cos(age_in_ticks * 0.2) * 0.72
        bones['mainbody']['oy'] = f12_hover

        # Flight wing/leg animations
        limb_swing = 0.08 * age_in_ticks
        limb_swing_amount = 0.5
        speed = 2.5
        bones['jointLW1'] = {'rx': 0.5, 'ry': 0.5, 'rz': 0.0}
        bones['jointLW1_1'] = {'rz': swing_z_8(speed, 2.0, 1, -2.0, 0.8, limb_swing, limb_swing_amount)}
        bones['jointLW2'] = {'rz': swing_z_8(speed, 1.9, 1, 2.5, -1.0, limb_swing, limb_swing_amount)}
        bones['jointRW1'] = {'rx': 0.5, 'ry': -0.5, 'rz': 0.0}
        bones['jointRW1_1'] = {'rz': swing_z_8(speed, 2.0, -1, -2.0, -0.8, limb_swing, limb_swing_amount)}
        bones['jointRW2'] = {'rz': swing_z_8(speed, 1.9, -1, 2.5, 1.0, limb_swing, limb_swing_amount)}

        f12_legs = math.cos(age_in_ticks * 0.18) * 0.12
        bones['jointBBLL'] = {'rx': 0.8 + f12_legs}
        bones['jointBBRL'] = {'rx': 0.75 + -1.0 * f12_legs}
        bones['jointBLL'] = {'rx': 0.6 + -1.0 * f12_legs}
        bones['jointBRL'] = {'rx': 0.65 + f12_legs}

        # Leg sub-joints: explicitly reset to 0 for clean transitions from walk state
        bones['jointBBLL_2'] = {'rx': 0.0}  # Reset from walk swingX
        bones['jointBBRL_2'] = {'rx': 0.0}  # Reset from walk swingX
        bones['jointBLL_2'] = {'rx': 0.0}   # Reset from walk swingX
        bones['jointBRL_2'] = {'rx': 0.0}   # Reset from walk swingX
        bones['jointFL'] = {'rx': 0.0}       # Reset from walk swingX
        bones['jointFLL_1'] = {'rx': 0.0}    # Reset from walk swingX
        bones['jointFFLL_1'] = {'rx': 0.0}   # Reset from walk swingX
        bones['jointFFRL_1'] = {'rx': 0.0}   # Reset from walk swingX

        f12_front = math.cos(age_in_ticks * 0.17) * 0.1
        bones['jointFLL'] = {'rx': 0.5 + f12_front}
        bones['jointFRL'] = {'rx': 0.555 + f12_front}
        bones['jointFFLL'] = {'rx': 0.5 + f12_front}
        bones['jointFFRL'] = {'rx': 0.51 + f12_front}

        # Flight hair/mouth
        _add_hair_animations_flight(bones, age_in_ticks)
        _add_mouth_animations_flight(bones, age_in_ticks)

        # Flight tail
        f12_tail = math.cos(age_in_ticks * 0.14) * 0.4
        for name in ['jointT1', 'jointT_1', 'jointT_3', 'jointT_5', 'jointT_7', 'jointT_9', 'jointT_11']:
            bones[name] = {'ry': f12_tail}

    if raining:
        f1 = math.cos(age_in_ticks * 0.0751) * 0.02106
        f2 = math.cos(age_in_ticks * 0.0872) * 0.0107411
        f3 = math.cos(age_in_ticks * 0.09669) * 0.015075

        if flying:
            # Flight vomit + raining (from line 2232-2250)
            bones['jointN1'] = {'rx': -0.3 + -f1, 'ry': f2, 'rz': -f3}
            bones['jointN2'] = {'rx': -0.1 + f1, 'ry': f2, 'rz': f3}
            bones['jointN3'] = {'rx': -0.1 + -f1, 'ry': -f2, 'rz': f3}
            bones['jointN4'] = {'rx': -f1, 'ry': f2, 'rz': -f3}
            bones['jointN5'] = {'rx': f1, 'ry': -f2, 'rz': -f3}
        else:
            # Non-flight vomit+raining (from line 2391-2409)
            bones['jointN1'] = {'rx': -0.5 + -f1, 'ry': f2, 'rz': -f3}
            bones['jointN2'] = {'rx': -0.4 + f1, 'ry': f2, 'rz': f3}
            bones['jointN3'] = {'rx': -0.4 + -f1, 'ry': -f2, 'rz': f3}
            bones['jointN4'] = {'rx': -f1, 'ry': f2, 'rz': -f3}
            bones['jointN5'] = {'rx': f1, 'ry': -f2, 'rz': -f3}
    else:
        f1 = math.cos(age_in_ticks * 0.061) * 0.035
        f2 = math.cos(age_in_ticks * 0.082) * 0.02511
        f3 = math.cos(age_in_ticks * 0.079) * 0.04575

        # Non-flight vomit, not raining (from line 2410-2428)
        bones['jointN1'] = {'rx': -f1, 'ry': f2, 'rz': -f3}
        bones['jointN2'] = {'rx': f1, 'ry': f2, 'rz': f3}
        bones['jointN3'] = {'rx': -f1, 'ry': -f2, 'rz': f3}
        bones['jointN4'] = {'rx': -f1, 'ry': f2, 'rz': -f3}
        bones['jointN5'] = {'rx': f1, 'ry': -f2, 'rz': -f3}

    if not flying:
        # Also include the common hair/mouth animations for a complete look
        _add_hair_animations(bones, age_in_ticks)
        _add_mouth_animations(bones, age_in_ticks)

        # Include full idle walking animation (all 16 leg joints)
        limb_swing = 0.5 * age_in_ticks
        limb_swing_amount = 0.5
        GS = 0.9
        GD = 0.3
        bones['jointBBLL'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, 1, -1.0, 0.0, limb_swing, limb_swing_amount)}
        bones['jointBBRL'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, -1, -1.0, 0.0, limb_swing, limb_swing_amount)}
        bones['jointBBLL_2'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, 1, 1.0, 0.0, limb_swing, limb_swing_amount)}
        bones['jointBBRL_2'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, -1, 1.0, 0.0, limb_swing, limb_swing_amount)}
        bones['jointBLL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, -1, 1.0, -0.0, limb_swing, limb_swing_amount)}
        bones['jointBRL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, 1, 1.0, -0.0, limb_swing, limb_swing_amount)}
        bones['jointBLL_2'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, 1, -1.0, 0.0, limb_swing, limb_swing_amount)}
        bones['jointBRL_2'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, -1, -1.0, 0.0, limb_swing, limb_swing_amount)}
        bones['jointFLL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, 1, 1.0, -0.4, limb_swing, limb_swing_amount)}
        bones['jointFL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, -1, 1.0, -0.4, limb_swing, limb_swing_amount)}
        bones['jointFLL_1'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, 1, -1.0, 0.0, limb_swing, limb_swing_amount)}
        bones['jointFRL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, -1, -1.0, 0.0, limb_swing, limb_swing_amount)}
        bones['jointFFLL'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, -1, 1.0, -0.1, limb_swing, limb_swing_amount)}
        bones['jointFFRL'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, 1, 1.0, -0.1, limb_swing, limb_swing_amount)}
        bones['jointFFLL_1'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, -1, -1.0, 0.0, limb_swing, limb_swing_amount)}
        bones['jointFFRL_1'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, 1, -1.0, 0.0, limb_swing, limb_swing_amount)}

        # Wing subtle motion
        f1_wing = math.cos(age_in_ticks * 0.09) * 0.08
        # Transition resets: wing joints have rx/ry from flight
        bones['jointLW1'] = {'rx': 0.0, 'ry': 0.0, 'rz': -0.1 + f1_wing}
        bones['jointLW1_1'] = {'rz': 0.0}
        bones['jointLW2'] = {'rz': f1_wing}
        bones['jointRW1'] = {'rx': 0.0, 'ry': 0.0, 'rz': 0.1 + f1_wing}
        bones['jointRW1_1'] = {'rz': 0.0}
        bones['jointRW2'] = {'rz': f1_wing}

        # Tail sway
        f1_tail = math.cos(age_in_ticks * 0.091) * 0.1
        for name in ['jointT1', 'jointT_1', 'jointT_3', 'jointT_5', 'jointT_7', 'jointT_9', 'jointT_11']:
            bones[name] = {'ry': f1_tail}

        # Body bob
        bones.setdefault('mainbody', {})['rx'] = 0.0
        bones.setdefault('mainbody', {})['ox'] = 0.0
        bones.setdefault('mainbody', {})['oz'] = 0.0
        bones.setdefault('mainbody', {})['oy'] = move_y(0.6*GS, 1, limb_swing, limb_swing_amount, 0.18)

    return bones


def eval_shaking(t_seconds: float) -> Dict[str, Dict[str, float]]:
    """Evaluate shaking state (shakingC > 0, not clone).
    
    From lines 2499-2506 of ModelHeblu.java:
      mainbody.offsetX = cos(ageInTicks * 2.95) * 0.08912576
      mainbody.offsetZ = cos(ageInTicks * 2.95) * 0.08912575
    
    This is a subtle body vibration that occurs when the entity is shaking
    but NOT in cosmic/clone state.
    """
    age_in_ticks = t_seconds * TICKS_PER_SECOND
    
    bones = {}
    
    # From Java: field_82906_o (=offsetX) = cos(ageInTicks * 2.95) * 0.08912576
    #            field_82907_q (=offsetZ) = cos(ageInTicks * 2.95) * 0.08912575
    ox = math.cos(age_in_ticks * 2.95) * 0.08912576
    oz = math.cos(age_in_ticks * 2.95) * 0.08912575
    
    bones['mainbody'] = {'rx': 0.0, 'ox': ox, 'oz': oz}
    
    # Also include idle animations as a base (shaking entities still move)
    limb_swing = 0.5 * age_in_ticks
    limb_swing_amount = 0.5
    GS = 0.9
    GD = 0.3
    
    # Full walking animation (all 16 leg joints)
    bones['jointBBLL'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, 1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointBBRL'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, -1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointBBLL_2'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, 1, 1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointBBRL_2'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, -1, 1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointBLL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, -1, 1.0, -0.0, limb_swing, limb_swing_amount)}
    bones['jointBRL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, 1, 1.0, -0.0, limb_swing, limb_swing_amount)}
    bones['jointBLL_2'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, 1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointBRL_2'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, -1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointFLL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, 1, 1.0, -0.4, limb_swing, limb_swing_amount)}
    bones['jointFL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, -1, 1.0, -0.4, limb_swing, limb_swing_amount)}
    bones['jointFLL_1'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, 1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointFRL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, -1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointFFLL'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, -1, 1.0, -0.1, limb_swing, limb_swing_amount)}
    bones['jointFFRL'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, 1, 1.0, -0.1, limb_swing, limb_swing_amount)}
    bones['jointFFLL_1'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, -1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointFFRL_1'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, 1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    
    # Body bob
    bones['mainbody']['oy'] = move_y(0.6*GS, 1, limb_swing, limb_swing_amount, 0.18)
    
    # Wing subtle motion
    f1_wing = math.cos(age_in_ticks * 0.09) * 0.08
    bones['jointLW1'] = {'rx': 0.0, 'ry': 0.0, 'rz': -0.1 + f1_wing}
    bones['jointLW1_1'] = {'rz': 0.0}
    bones['jointLW2'] = {'rz': f1_wing}
    bones['jointRW1'] = {'rx': 0.0, 'ry': 0.0, 'rz': 0.1 + f1_wing}
    bones['jointRW1_1'] = {'rz': 0.0}
    bones['jointRW2'] = {'rz': f1_wing}
    
    # Neck sway
    f1_neck = math.cos(age_in_ticks * 0.0751) * 0.06
    f2_neck = math.cos(age_in_ticks * 0.0872) * 0.0411
    f3_neck = math.cos(age_in_ticks * 0.09669) * 0.075
    bones['jointN1'] = {'rx': -f1_neck, 'ry': f2_neck, 'rz': -f3_neck}
    bones['jointN2'] = {'rx': f1_neck, 'ry': f2_neck, 'rz': f3_neck}
    bones['jointN3'] = {'rx': -f1_neck, 'ry': -f2_neck, 'rz': f3_neck}
    bones['jointN4'] = {'rx': -f1_neck, 'ry': f2_neck, 'rz': -f3_neck}
    bones['jointN5'] = {'rx': f1_neck, 'ry': -f2_neck, 'rz': -f3_neck}
    
    # Tail sway
    f1_tail = math.cos(age_in_ticks * 0.091) * 0.1
    for name in ['jointT1', 'jointT_1', 'jointT_3', 'jointT_5', 'jointT_7', 'jointT_9', 'jointT_11']:
        bones[name] = {'ry': f1_tail}
    
    # Hair
    _add_hair_animations(bones, age_in_ticks)
    
    # Mouth
    _add_mouth_animations(bones, age_in_ticks)
    
    return bones


def eval_cosmic(t_seconds: float, shaking: bool = False) -> Dict[str, Dict[str, float]]:
    """Evaluate cosmic/clone body shaking animation.
    
    From lines 2507-2520 and 2528-2546 of ModelHeblu.java.
    This is used by both getCloneC() and EntityPCosmical.
    
    When shakingC > 0: amp=2.0, dis=0.3 (faster oscillation, dampened amplitude)
    Normal: amp=1.0, dis=1.0 (full amplitude)
    
    IMPORTANT: The cosmic offset code (lines 2507-2520) runs AFTER the regular
    ground animation (legs/wing/neck/tail/hair/mouth), meaning the cosmic entity
    still walks/sways. The only difference is the mainbody ox/oz override.
    """
    age_in_ticks = t_seconds * TICKS_PER_SECOND
    
    bones = {}
    
    if shaking:
        amp = 2.0
        dis = 0.3
    else:
        amp = 1.0
        dis = 1.0
    
    # From Java source (lines 2517-2519):
    #   f2 = -cos(ageInTicks * 2.6 * amp) * 0.55 * dis
    #   mainbody.field_82906_o (=offsetX) = -cos(ageInTicks * 2.27 * amp) * 0.59 * dis
    #   mainbody.field_82907_q (=offsetZ) = f2
    ox = -1.0 * math.cos(age_in_ticks * 2.27 * amp) * 0.59 * dis
    oz = -1.0 * math.cos(age_in_ticks * 2.6 * amp) * 0.55 * dis
    
    bones['mainbody'] = {'rx': 0.0, 'ox': ox, 'oz': oz}
    
    # Also include idle animations as a base (cosmic entities still walk/sway)
    # NOTE: Java source uses the entity's actual limbSwingAmount, not a fixed value.
    # Using 0.5 (same as idle) rather than the previous incorrect 0.3.
    limb_swing = 0.5 * age_in_ticks
    limb_swing_amount = 0.5
    
    # Full walking animation (all 16 leg joints)
    GS = 0.9
    GD = 0.3
    bones['jointBBLL'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, 1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointBBRL'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, -1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointBBLL_2'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, 1, 1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointBBRL_2'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, -1, 1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointBLL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, -1, 1.0, -0.0, limb_swing, limb_swing_amount)}
    bones['jointBRL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, 1, 1.0, -0.0, limb_swing, limb_swing_amount)}
    bones['jointBLL_2'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, 1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointBRL_2'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, -1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointFLL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, 1, 1.0, -0.4, limb_swing, limb_swing_amount)}
    bones['jointFL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, -1, 1.0, -0.4, limb_swing, limb_swing_amount)}
    bones['jointFLL_1'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, 1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointFRL'] = {'rx': swing_x_8(0.3*GS, 1.5*GD, -1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointFFLL'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, -1, 1.0, -0.1, limb_swing, limb_swing_amount)}
    bones['jointFFRL'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, 1, 1.0, -0.1, limb_swing, limb_swing_amount)}
    bones['jointFFLL_1'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, -1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    bones['jointFFRL_1'] = {'rx': swing_x_8(0.3*GS, 1.1*GD, 1, -1.0, 0.0, limb_swing, limb_swing_amount)}
    
    # Body bob
    bones['mainbody']['oy'] = move_y(0.6*GS, 1, limb_swing, limb_swing_amount, 0.18)
    
    # Wing subtle motion
    f1_wing = math.cos(age_in_ticks * 0.09) * 0.08
    bones['jointLW1'] = {'rx': 0.0, 'ry': 0.0, 'rz': -0.1 + f1_wing}
    bones['jointLW1_1'] = {'rz': 0.0}
    bones['jointLW2'] = {'rz': f1_wing}
    bones['jointRW1'] = {'rx': 0.0, 'ry': 0.0, 'rz': 0.1 + f1_wing}
    bones['jointRW1_1'] = {'rz': 0.0}
    bones['jointRW2'] = {'rz': f1_wing}
    
    # Neck sway
    f1_neck = math.cos(age_in_ticks * 0.0751) * 0.06
    f2_neck = math.cos(age_in_ticks * 0.0872) * 0.0411
    f3_neck = math.cos(age_in_ticks * 0.09669) * 0.075
    bones['jointN1'] = {'rx': -f1_neck, 'ry': f2_neck, 'rz': -f3_neck}
    bones['jointN2'] = {'rx': f1_neck, 'ry': f2_neck, 'rz': f3_neck}
    bones['jointN3'] = {'rx': -f1_neck, 'ry': -f2_neck, 'rz': f3_neck}
    bones['jointN4'] = {'rx': -f1_neck, 'ry': f2_neck, 'rz': -f3_neck}
    bones['jointN5'] = {'rx': f1_neck, 'ry': -f2_neck, 'rz': -f3_neck}
    
    # Tail sway
    f1_tail = math.cos(age_in_ticks * 0.091) * 0.1
    for name in ['jointT1', 'jointT_1', 'jointT_3', 'jointT_5', 'jointT_7', 'jointT_9', 'jointT_11']:
        bones[name] = {'ry': f1_tail}
    
    # Hair
    _add_hair_animations(bones, age_in_ticks)
    
    # Mouth
    _add_mouth_animations(bones, age_in_ticks)
    
    return bones


# ============================================================================
# Shared Animation Component Functions
# ============================================================================

def _add_hair_animations(bones: Dict, age_in_ticks: float):
    """Add hair joint animations (common for all non-flying states).
    From lines 2431-2476 of ModelHeblu.java.

    IMPORTANT: The initial reset section (lines 2092-2095) sets rz=0 for
    hjointD_1, hjointF_1, hjointB_1, hjointH_1. These are NOT reassigned in
    non-flight hair animations, so we must explicitly reset them to 0 for
    clean transitions from flight state where they have nonzero rz.
    """
    f1 = math.cos(age_in_ticks * 0.123) * 0.25
    f2 = math.cos(age_in_ticks * 0.233) * 0.21
    f3 = math.cos(age_in_ticks * 0.1435) * 0.29
    f4 = math.cos(age_in_ticks * 0.2) * 0.24

    # hjointC group
    bones.setdefault('hjointC_1', {})['ry'] = f1
    bones.setdefault('hjointC_3', {})['ry'] = -f2
    bones.setdefault('hjointC_5', {})['ry'] = f1
    bones.setdefault('hjointC_7', {})['ry'] = -f3
    bones.setdefault('hjointC_8', {})['ry'] = -f4

    # hjointG group
    bones.setdefault('hjointG_1', {})['ry'] = -f4
    bones.setdefault('hjointG_3', {})['ry'] = -f3
    bones.setdefault('hjointG_5', {})['ry'] = -f1
    bones.setdefault('hjointG_7', {})['ry'] = -f4
    bones.setdefault('hjointG_8', {})['ry'] = f2

    # hjointD group
    # hjointD_1: ry = f2 (Java line 2445), rz = 0 (reset at line 2092, not reassigned)
    bones.setdefault('hjointD_1', {})['rz'] = 0.0  # Must reset for flight→ground transition
    bones.setdefault('hjointD_1', {})['ry'] = f2
    bones.setdefault('hjointD_3', {})['ry'] = -f4
    bones.setdefault('hjointD_5', {})['ry'] = f1
    bones.setdefault('hjointD_7', {})['ry'] = f3
    bones.setdefault('hjointD_9', {})['ry'] = f1
    bones.setdefault('hjointD_10', {})['ry'] = -f3
    bones.setdefault('hjointD_11', {})['ry'] = -f4

    # hjointF group
    # hjointF_1: ry = -f1 (Java line 2452), rz = 0 (reset at line 2093, not reassigned)
    bones.setdefault('hjointF_1', {})['rz'] = 0.0  # Must reset for flight→ground transition
    bones.setdefault('hjointF_1', {})['ry'] = -f1
    bones.setdefault('hjointF_3', {})['ry'] = -f3
    bones.setdefault('hjointF_5', {})['ry'] = -f4
    bones.setdefault('hjointF_7', {})['ry'] = f2
    bones.setdefault('hjointF_9', {})['ry'] = -f2
    bones.setdefault('hjointF_10', {})['ry'] = -f4
    bones.setdefault('hjointF_11', {})['ry'] = f3

    # hjointB group
    # hjointB_1: ry = -f3 (Java line 2459), rz = 0 (reset at line 2094, not reassigned)
    bones.setdefault('hjointB_1', {})['rz'] = 0.0  # Must reset for flight→ground transition
    bones.setdefault('hjointB_1', {})['ry'] = -f3
    bones.setdefault('hjointB_3', {})['ry'] = f4
    bones.setdefault('hjointB_5', {})['ry'] = -f2
    bones.setdefault('hjointB_7', {})['ry'] = f1
    bones.setdefault('hjointB_8', {})['ry'] = -f4

    # hjointH group
    # hjointH_1: ry = -f4 (Java line 2464), rz = 0 (reset at line 2095, not reassigned)
    bones.setdefault('hjointH_1', {})['rz'] = 0.0  # Must reset for flight→ground transition
    bones.setdefault('hjointH_1', {})['ry'] = -f4
    bones.setdefault('hjointH_3', {})['ry'] = f3
    bones.setdefault('hjointH_5', {})['ry'] = -f3
    bones.setdefault('hjointH_7', {})['ry'] = -f2
    bones.setdefault('hjointH_8', {})['ry'] = -f1

    # hjointA group
    # hjointA_1: ry = -f1 (Java line 2469), rz = 0 (must reset from flight rz=-0.8)
    bones.setdefault('hjointA_1', {})['rz'] = 0.0  # Must reset for flight→ground transition
    bones.setdefault('hjointA_1', {})['ry'] = -f1
    bones.setdefault('hjointA_3', {})['ry'] = -f2
    bones.setdefault('hjointA_5', {})['ry'] = f4
    bones.setdefault('hjointA_6', {})['ry'] = f1

    # hjointE group
    # hjointE_1: ry = f3 (Java line 2474), rz = 0 (must reset from flight rz=0.8)
    bones.setdefault('hjointE_1', {})['rz'] = 0.0  # Must reset for flight→ground transition
    bones.setdefault('hjointE_1', {})['ry'] = f3
    bones.setdefault('hjointE_3', {})['ry'] = f2
    bones.setdefault('hjointE_5', {})['ry'] = f4
    bones.setdefault('hjointE_6', {})['ry'] = -f3


def _add_hair_animations_flight(bones: Dict, age_in_ticks: float):
    """Add hair joint animations for flight state.
    From lines 2157-2208 of ModelHeblu.java.
    """
    f12 = math.cos(age_in_ticks * 0.123) * 0.25
    f22 = math.cos(age_in_ticks * 0.233) * 0.21
    f32 = math.cos(age_in_ticks * 0.1435) * 0.29
    f4 = math.cos(age_in_ticks * 0.2) * 0.24

    # hjointC group (flight)
    bones.setdefault('hjointC_1', {})['ry'] = 0.7 + f12
    bones.setdefault('hjointC_3', {})['ry'] = -0.7 + -f22
    bones.setdefault('hjointC_5', {})['ry'] = -0.7 + f12
    bones.setdefault('hjointC_7', {})['ry'] = -0.5 + -f32
    bones.setdefault('hjointC_8', {})['ry'] = -0.5 + -f4

    # hjointG group (flight)
    bones.setdefault('hjointG_1', {})['ry'] = 0.7 + -f4
    bones.setdefault('hjointG_3', {})['ry'] = -0.7 + -f32
    bones.setdefault('hjointG_5', {})['ry'] = -0.7 + -f12
    bones.setdefault('hjointG_7', {})['ry'] = -0.5 + f4
    bones.setdefault('hjointG_8', {})['ry'] = -0.5 + f22

    # hjointD group (flight) - includes rz for some
    bones.setdefault('hjointD_1', {})['rz'] = 0.7
    bones.setdefault('hjointD_1', {})['ry'] = 0.8 + f22
    bones.setdefault('hjointD_3', {})['ry'] = 0.4 + -f4
    bones.setdefault('hjointD_5', {})['ry'] = 0.5 + f12
    bones.setdefault('hjointD_7', {})['ry'] = -0.5 + f32
    bones.setdefault('hjointD_9', {})['ry'] = -0.5 + f12
    bones.setdefault('hjointD_10', {})['ry'] = -0.5 + -f32
    bones.setdefault('hjointD_11', {})['ry'] = -0.5 + -f4

    # hjointF group (flight)
    bones.setdefault('hjointF_1', {})['rz'] = -0.5
    bones.setdefault('hjointF_1', {})['ry'] = 0.7 + -f12
    bones.setdefault('hjointF_3', {})['ry'] = 0.7 + -f32
    bones.setdefault('hjointF_5', {})['ry'] = 0.7 + -f4
    bones.setdefault('hjointF_7', {})['ry'] = -0.5 + f22
    bones.setdefault('hjointF_9', {})['ry'] = -0.5 + -f22
    bones.setdefault('hjointF_10', {})['ry'] = -0.5 + -f4
    bones.setdefault('hjointF_11', {})['ry'] = -0.5 + f32

    # hjointB group (flight)
    bones.setdefault('hjointB_1', {})['rz'] = 0.8
    bones.setdefault('hjointB_1', {})['ry'] = -0.4 + -f32
    bones.setdefault('hjointB_3', {})['ry'] = 0.4 + f4
    bones.setdefault('hjointB_5', {})['ry'] = 0.7 + -f22
    bones.setdefault('hjointB_7', {})['ry'] = 0.5 + f12
    bones.setdefault('hjointB_8', {})['ry'] = 0.5 + -f4

    # hjointH group (flight)
    bones.setdefault('hjointH_1', {})['rz'] = -0.8
    bones.setdefault('hjointH_1', {})['ry'] = -0.4 + -f4
    bones.setdefault('hjointH_3', {})['ry'] = 0.4 + f32
    bones.setdefault('hjointH_5', {})['ry'] = 0.7 + -f32
    bones.setdefault('hjointH_7', {})['ry'] = 0.5 + -f22
    bones.setdefault('hjointH_8', {})['ry'] = 0.5 + -f12

    # hjointA group (flight)
    bones.setdefault('hjointA_1', {})['rz'] = -0.8
    bones.setdefault('hjointA_1', {})['ry'] = 0.2 + -f12
    bones.setdefault('hjointA_3', {})['ry'] = -0.4 + -f22
    bones.setdefault('hjointA_5', {})['ry'] = 0.7 + f4
    bones.setdefault('hjointA_6', {})['ry'] = 0.5 + f12

    # hjointE group (flight)
    bones.setdefault('hjointE_1', {})['rz'] = 0.8
    bones.setdefault('hjointE_1', {})['ry'] = 0.2 + f32
    bones.setdefault('hjointE_3', {})['ry'] = 0.4 + f22
    bones.setdefault('hjointE_5', {})['ry'] = 0.7 + f4
    bones.setdefault('hjointE_6', {})['ry'] = 0.5 + -f32


def _add_mouth_animations(bones: Dict, age_in_ticks: float):
    """Add mouth joint animations (common for all non-flying states).
    From lines 2477-2498 of ModelHeblu.java.
    Note: Multiple reassignments - LAST value wins.
    """
    f1 = math.cos(age_in_ticks * 0.123) * 0.25
    f2 = math.cos(age_in_ticks * 0.233) * 0.21
    f3 = math.cos(age_in_ticks * 0.1435) * 0.29
    f4 = math.cos(age_in_ticks * 0.2) * 0.24

    # jointMD: ry=-f1, rx=f4 (last: -f3 then f4 → f4)
    bones.setdefault('jointMD', {})['ry'] = -f1
    bones.setdefault('jointMD', {})['rx'] = f4

    # jointMU: ry=f4, rx=f1 (last: -f2 then f1 → f1)
    bones.setdefault('jointMU', {})['ry'] = f4
    bones.setdefault('jointMU', {})['rx'] = f1

    # jointLM: rx=-f4 (last: f2 → -f3 → -f4)
    bones.setdefault('jointLM', {})['rx'] = -f4

    # jointRM: rx=-f1 (last: f2 → f3 → -f1)
    bones.setdefault('jointRM', {})['rx'] = -f1

    # jointUM: ry=f2, rx=-f4 (last: -f3 → -f4)
    bones.setdefault('jointUM', {})['ry'] = f2
    bones.setdefault('jointUM', {})['rx'] = -f4

    # jointDM: ry=f2, rx=-f1 (last: f3 → -f1)
    bones.setdefault('jointDM', {})['ry'] = f2
    bones.setdefault('jointDM', {})['rx'] = -f1


def _add_mouth_animations_flight(bones: Dict, age_in_ticks: float):
    """Add mouth joint animations for flight state.
    From lines 2209-2230 of ModelHeblu.java.
    """
    f12 = math.cos(age_in_ticks * 0.123) * 0.25
    f22 = math.cos(age_in_ticks * 0.233) * 0.21
    f32 = math.cos(age_in_ticks * 0.1435) * 0.29
    f4 = math.cos(age_in_ticks * 0.2) * 0.24

    # Same pattern as non-flight but using flight variable names
    bones.setdefault('jointMD', {})['ry'] = -f12
    bones.setdefault('jointMD', {})['rx'] = f4

    bones.setdefault('jointMU', {})['ry'] = f4
    bones.setdefault('jointMU', {})['rx'] = f12

    bones.setdefault('jointLM', {})['rx'] = -f4

    bones.setdefault('jointRM', {})['rx'] = -f12

    bones.setdefault('jointUM', {})['ry'] = f22
    bones.setdefault('jointUM', {})['rx'] = -f4

    bones.setdefault('jointDM', {})['ry'] = f22
    bones.setdefault('jointDM', {})['rx'] = -f12


# ============================================================================
# Animation Sampling and Keyframe Generation
# ============================================================================

def sample_animation(eval_func, duration: float, samples_per_second: float = 60.0,
                     dp_epsilon: float = 0.15) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
    """Sample an animation function over time and simplify with Douglas-Peucker.
    
    Returns: {bone_name: {channel: [(time, value), ...]}}
    
    Quality parameters:
    - samples_per_second: 60 for smooth motion (was 30)
    - dp_epsilon: 0.15 degrees for preserving subtle detail (was 0.3)
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
                    converted_points.append((t, val))  # rx stays
                elif channel == 'ry':
                    converted_points.append((t, -val))  # ry → -ry
                elif channel == 'rz':
                    converted_points.append((t, -val))  # rz → -rz
                elif channel == 'ox':
                    converted_points.append((t, val))   # ox stays
                elif channel == 'oy':
                    converted_points.append((t, -val))  # oy → -oy
                elif channel == 'oz':
                    converted_points.append((t, -val))  # oz → -oz
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
    return channel[-1]  # 'rx' -> 'x', 'ry' -> 'y', 'rz' -> 'z', etc.


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


def generate_all_animations() -> dict:
    """Generate all animation states and return the complete .animation.json."""
    animations = {}

    # --- IDLE animation ---
    print("  Generating idle animation...")
    # Walk cycle period = 2π / (0.3*0.9*0.5*20) = 2.327s
    # Use 9 complete walk cycles for seamless walking loop
    idle_duration = 9 * (2 * math.pi / 2.7)  # 20.944s = 9 complete walk cycles
    
    idle_data = sample_animation(
        lambda t: eval_idle(t, limb_swing_amount=0.5),
        duration=idle_duration,
        samples_per_second=60.0,
        dp_epsilon=0.15
    )
    # Enforce loop continuity
    idle_data = enforce_loop_continuity(idle_data, idle_duration)
    
    animations["animation.model.idle"] = build_animation_json(
        "animation.model.idle", "loop", idle_data, idle_duration
    )
    idle_bone_count = len(animations["animation.model.idle"]["bones"])
    print(f"    Bones: {idle_bone_count}, Duration: {idle_duration}s")

    # --- ATTACK animation ---
    print("  Generating attack animation...")
    # Walk cycle period for attack: 2π / (0.3*1.0*0.5*20) = 2.094s
    # Use 10 complete walk cycles for seamless loop
    attack_walk_period = 2 * math.pi / (0.3 * 1.0 * 0.5 * 20)
    attack_duration = 10 * attack_walk_period  # ~20.944s
    
    attack_data = sample_animation(
        lambda t: eval_attack(t, limb_swing_amount=0.5),
        duration=attack_duration,
        samples_per_second=60.0,
        dp_epsilon=0.15
    )
    attack_data = enforce_loop_continuity(attack_data, attack_duration)
    
    animations["animation.model.attack"] = build_animation_json(
        "animation.model.attack", "loop", attack_data, attack_duration
    )
    attack_bone_count = len(animations["animation.model.attack"]["bones"])
    print(f"    Bones: {attack_bone_count}, Duration: {attack_duration}s")

    # --- FLY animation ---
    print("  Generating fly animation...")
    # Flight wing flap period: cos(0.08 * ageInTicks * 2.5)
    # Angular frequency: 0.08 * 20 * 2.5 = 4.0 rad/s → period = π/2 ≈ 1.571s
    # Use 4 complete wing cycles for seamless loop
    fly_wing_period = 2 * math.pi / 4.0
    fly_duration = 4 * fly_wing_period  # 6.283s = 4 complete wing cycles
    
    fly_data = sample_animation(
        eval_fly,
        duration=fly_duration,
        samples_per_second=60.0,
        dp_epsilon=0.12  # Tighter epsilon for wing flap detail
    )
    fly_data = enforce_loop_continuity(fly_data, fly_duration)
    
    animations["animation.model.fly"] = build_animation_json(
        "animation.model.fly", "loop", fly_data, fly_duration
    )
    fly_bone_count = len(animations["animation.model.fly"]["bones"])
    print(f"    Bones: {fly_bone_count}, Duration: {fly_duration}s")

    # --- VOMIT animation (ground) ---
    print("  Generating vomit animation (ground)...")
    vomit_duration = 4.0  # Finite duration, hold_on_last_frame
    
    vomit_data = sample_animation(
        lambda t: eval_vomit(t, raining=False, flying=False),
        duration=vomit_duration,
        samples_per_second=60.0,
        dp_epsilon=0.08  # Very tight epsilon for neck articulation detail
    )
    
    animations["animation.model.vomit"] = build_animation_json(
        "animation.model.vomit", "hold_on_last_frame", vomit_data, vomit_duration
    )
    vomit_bone_count = len(animations["animation.model.vomit"]["bones"])
    print(f"    Bones: {vomit_bone_count}, Duration: {vomit_duration}s")

    # --- FLY VOMIT animation ---
    print("  Generating fly_vomit animation...")
    fly_vomit_duration = 4.0
    
    fly_vomit_data = sample_animation(
        lambda t: eval_vomit(t, raining=False, flying=True),
        duration=fly_vomit_duration,
        samples_per_second=60.0,
        dp_epsilon=0.08
    )
    
    animations["animation.model.fly_vomit"] = build_animation_json(
        "animation.model.fly_vomit", "hold_on_last_frame", fly_vomit_data, fly_vomit_duration
    )
    fly_vomit_bone_count = len(animations["animation.model.fly_vomit"]["bones"])
    print(f"    Bones: {fly_vomit_bone_count}, Duration: {fly_vomit_duration}s")

    # --- SHAKING animation ---
    print("  Generating shaking animation...")
    # Shaking: cos(ageInTicks * 2.95) → angular freq = 2.95 * 20 = 59 rad/s
    # Period = 2π/59 ≈ 0.1066s → ~9.4 cycles per second
    # At 60fps that's only ~6.3 samples/cycle - need higher rate!
    # Use 240 fps for adequate sampling of this fast oscillation
    # Duration: 2 complete shake cycles = 2 * 2π/59 ≈ 0.213s, use 2s for visibility
    shaking_duration = 2.0
    
    shaking_data = sample_animation(
        eval_shaking,
        duration=shaking_duration,
        samples_per_second=240.0,  # High rate for fast oscillation
        dp_epsilon=0.05  # Tighter epsilon to preserve subtle 0.089 amplitude
    )
    shaking_data = enforce_loop_continuity(shaking_data, shaking_duration)
    
    animations["animation.model.shaking"] = build_animation_json(
        "animation.model.shaking", "loop", shaking_data, shaking_duration
    )
    shaking_bone_count = len(animations["animation.model.shaking"]["bones"])
    print(f"    Bones: {shaking_bone_count}, Duration: {shaking_duration}s")

    # --- COSMIC animation ---
    print("  Generating cosmic animation...")
    # Cosmic: cos(ageInTicks * 2.27) → angular freq = 2.27 * 20 = 45.4 rad/s
    # Period ≈ 0.138s → ~7.2 cycles per second
    cosmic_duration = 4.0
    
    cosmic_data = sample_animation(
        lambda t: eval_cosmic(t, shaking=False),
        duration=cosmic_duration,
        samples_per_second=120.0,  # Higher rate for oscillation
        dp_epsilon=0.08
    )
    cosmic_data = enforce_loop_continuity(cosmic_data, cosmic_duration)
    
    animations["animation.model.cosmic"] = build_animation_json(
        "animation.model.cosmic", "loop", cosmic_data, cosmic_duration
    )
    cosmic_bone_count = len(animations["animation.model.cosmic"]["bones"])
    print(f"    Bones: {cosmic_bone_count}, Duration: {cosmic_duration}s")

    # --- COSMIC SHAKING animation ---
    print("  Generating cosmic_shaking animation...")
    # Cosmic shaking: cos(ageInTicks * 2.27 * 2.0) = cos(ageInTicks * 4.54)
    # Angular freq = 4.54 * 20 = 90.8 rad/s → period ≈ 0.069s → ~14.5 cycles/s
    # This is VERY fast - needs 300+ fps for adequate sampling
    cosmic_shaking_duration = 2.0
    
    cosmic_shaking_data = sample_animation(
        lambda t: eval_cosmic(t, shaking=True),
        duration=cosmic_shaking_duration,
        samples_per_second=300.0,  # Very high rate for extremely fast oscillation
        dp_epsilon=0.05  # Tight epsilon to preserve dampened 0.59*0.3=0.177 amplitude
    )
    cosmic_shaking_data = enforce_loop_continuity(cosmic_shaking_data, cosmic_shaking_duration)
    
    animations["animation.model.cosmic_shaking"] = build_animation_json(
        "animation.model.cosmic_shaking", "loop", cosmic_shaking_data, cosmic_shaking_duration
    )
    cosmic_shaking_bone_count = len(animations["animation.model.cosmic_shaking"]["bones"])
    print(f"    Bones: {cosmic_shaking_bone_count}, Duration: {cosmic_shaking_duration}s")

    return {
        "format_version": "1.8.0",
        "animations": animations
    }


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    print("=" * 70)
    print("  Heblu Animation Generator v2")
    print("  MC 1.12.2 → GeckoLib 1.20.1 Animation Conversion")
    print("=" * 70)
    print()

    # Generate all animations
    anim_json = generate_all_animations()

    # Determine output paths
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(project_root, "db", "heblu.animation.json")
    output_path = os.path.join(project_root, "converter", "output", "heblu.animation.json")

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

    # Now regenerate the .bbmodel
    print("\n  Regenerating .bbmodel with new animations...")
    sys.path.insert(0, os.path.join(project_root, 'converter'))
    from bbmodel_generator import BBModelGenerator

    geo_json_path = os.path.join(project_root, 'db', 'heblu.geo.json')
    texture_path = os.path.join(project_root, 'db', 'heblu.png')

    with open(geo_json_path, 'r', encoding='utf-8') as f:
        geo_json = json.load(f)

    gen = BBModelGenerator()
    bbmodel = gen.generate(
        geo_json,
        anim_json=anim_json,
        texture_path=texture_path if os.path.isfile(texture_path) else None,
        texture_name='heblu',
        namespace='srparasites'
    )

    bbmodel_db_path = os.path.join(project_root, 'db', 'heblu_debug.bbmodel')
    bbmodel_out_path = os.path.join(project_root, 'converter', 'output', 'heblu_debug.bbmodel')

    gen.save(bbmodel, bbmodel_db_path)
    gen.save(bbmodel, bbmodel_out_path)

    print(f"  Saved .bbmodel to: {bbmodel_db_path}")
    print(f"  Saved .bbmodel to: {bbmodel_out_path}")
    print(f"  .bbmodel size: {os.path.getsize(bbmodel_db_path):,} bytes")
    print(f"  Elements: {len(bbmodel.get('elements', []))}")
    print(f"  Animations: {len(bbmodel.get('animations', []))}")

    # Also regenerate Kirin bbmodel
    print("\n  Regenerating Kirin .bbmodel...")
    kirin_geo_path = os.path.join(project_root, 'db', 'kirin.geo.json')
    kirin_texture_path = os.path.join(project_root, 'db', 'kirin.png')
    kirin_anim_path = os.path.join(project_root, 'db', 'kirin.animation.json')
    
    if os.path.isfile(kirin_geo_path):
        with open(kirin_geo_path, 'r', encoding='utf-8') as f:
            kirin_geo = json.load(f)
        
        kirin_anim = None
        if os.path.isfile(kirin_anim_path):
            with open(kirin_anim_path, 'r', encoding='utf-8') as f:
                kirin_anim = json.load(f)
        
        kirin_bbmodel = gen.generate(
            kirin_geo,
            anim_json=kirin_anim,
            texture_path=kirin_texture_path if os.path.isfile(kirin_texture_path) else None,
            texture_name='kirin',
            namespace='srparasites'
        )
        
        kirin_bbmodel_db_path = os.path.join(project_root, 'db', 'kirin_debug.bbmodel')
        kirin_bbmodel_out_path = os.path.join(project_root, 'converter', 'output', 'kirin_debug.bbmodel')
        
        gen.save(kirin_bbmodel, kirin_bbmodel_db_path)
        gen.save(kirin_bbmodel, kirin_bbmodel_out_path)
        
        print(f"  Saved Kirin .bbmodel to: {kirin_bbmodel_db_path}")
        print(f"  Kirin .bbmodel size: {os.path.getsize(kirin_bbmodel_db_path):,} bytes")
        print(f"  Kirin Elements: {len(kirin_bbmodel.get('elements', []))}")
        print(f"  Kirin Animations: {len(kirin_bbmodel.get('animations', []))}")

    print("\n" + "=" * 70)
    print("  DONE - Heblu Animation Generator v2")
    print("=" * 70)

    return anim_json


if __name__ == "__main__":
    main()
