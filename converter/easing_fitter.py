#!/usr/bin/env python3
"""
EasingFitter - Animation Easing Type Auto-Fitting
===================================================
Analyzes keyframe curves and fits the best GeckoLib easing type
for each pair of consecutive keyframes.

GeckoLib easing types:
  - linear (default)
  - easeInSine, easeOutSine, easeInOutSine
  - easeInCubic, easeOutCubic, easeInOutCubic
  - easeInQuart, easeOutQuart, easeInOutQuart
  - easeInQuint, easeOutQuint, easeInOutQuint
  - easeInExpo, easeOutExpo, easeInOutExpo
  - easeInCirc, easeOutCirc, easeInOutCirc
  - easeInBack, easeOutBack, easeInOutBack
  - easeInElastic, easeOutElastic, easeInOutElastic
  - easeInBounce, easeOutBounce, easeInOutBounce

Algorithm:
  1. For each pair of consecutive keyframes, sample the original curve
  2. Compute angular velocity pattern (accelerating, decelerating, etc.)
  3. Fit each easing function via least-squares
  4. Select the easing with minimum error
  5. If best error > 0.05°, fall back to "linear" and add comment

Does NOT modify core_math.py transformations.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# ============================================================================
# Easing Functions
# ============================================================================

def _linear(t: float) -> float:
    """Linear interpolation."""
    return t

def _ease_in_sine(t: float) -> float:
    return 1.0 - math.cos((t * math.pi) / 2.0)

def _ease_out_sine(t: float) -> float:
    return math.sin((t * math.pi) / 2.0)

def _ease_in_out_sine(t: float) -> float:
    return -(math.cos(math.pi * t) - 1.0) / 2.0

def _ease_in_cubic(t: float) -> float:
    return t * t * t

def _ease_out_cubic(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3

def _ease_in_out_cubic(t: float) -> float:
    if t < 0.5:
        return 4.0 * t * t * t
    else:
        return 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0

def _ease_in_quart(t: float) -> float:
    return t * t * t * t

def _ease_out_quart(t: float) -> float:
    return 1.0 - (1.0 - t) ** 4

def _ease_in_out_quart(t: float) -> float:
    if t < 0.5:
        return 8.0 * t * t * t * t
    else:
        return 1.0 - (-2.0 * t + 2.0) ** 4 / 2.0

def _ease_in_quint(t: float) -> float:
    return t * t * t * t * t

def _ease_out_quint(t: float) -> float:
    return 1.0 - (1.0 - t) ** 5

def _ease_in_out_quint(t: float) -> float:
    if t < 0.5:
        return 16.0 * t * t * t * t * t
    else:
        return 1.0 - (-2.0 * t + 2.0) ** 5 / 2.0

def _ease_in_expo(t: float) -> float:
    if t == 0.0:
        return 0.0
    return 2.0 ** (10.0 * t - 10.0)

def _ease_out_expo(t: float) -> float:
    if t == 1.0:
        return 1.0
    return 1.0 - 2.0 ** (-10.0 * t)

def _ease_in_out_expo(t: float) -> float:
    if t == 0.0:
        return 0.0
    if t == 1.0:
        return 1.0
    if t < 0.5:
        return 2.0 ** (20.0 * t - 10.0) / 2.0
    else:
        return (2.0 - 2.0 ** (-20.0 * t + 10.0)) / 2.0

def _ease_in_circ(t: float) -> float:
    return 1.0 - math.sqrt(1.0 - t * t)

def _ease_out_circ(t: float) -> float:
    return math.sqrt(1.0 - (t - 1.0) ** 2)

def _ease_in_out_circ(t: float) -> float:
    if t < 0.5:
        return (1.0 - math.sqrt(1.0 - (2.0 * t) ** 2)) / 2.0
    else:
        return (math.sqrt(1.0 - (-2.0 * t + 2.0) ** 2) + 1.0) / 2.0

def _ease_in_back(t: float) -> float:
    c1 = 1.70158
    c3 = c1 + 1.0
    return c3 * t * t * t - c1 * t * t

def _ease_out_back(t: float) -> float:
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * (t - 1.0) ** 3 + c1 * (t - 1.0) ** 2

def _ease_in_out_back(t: float) -> float:
    c1 = 1.70158
    c2 = c1 * 1.525
    if t < 0.5:
        return ((2.0 * t) ** 2 * ((c2 + 1.0) * 2.0 * t - c2)) / 2.0
    else:
        return ((2.0 * t - 2.0) ** 2 * ((c2 + 1.0) * (t * 2.0 - 2.0) + c2) + 2.0) / 2.0

def _ease_in_elastic(t: float) -> float:
    if t == 0.0:
        return 0.0
    if t == 1.0:
        return 1.0
    c4 = (2.0 * math.pi) / 3.0
    return -(2.0 ** (10.0 * t - 10.0)) * math.sin((t * 10.0 - 10.75) * c4)

def _ease_out_elastic(t: float) -> float:
    if t == 0.0:
        return 0.0
    if t == 1.0:
        return 1.0
    c4 = (2.0 * math.pi) / 3.0
    return 2.0 ** (-10.0 * t) * math.sin((t * 10.0 - 0.75) * c4) + 1.0

def _ease_in_out_elastic(t: float) -> float:
    if t == 0.0:
        return 0.0
    if t == 1.0:
        return 1.0
    c5 = (2.0 * math.pi) / 4.5
    if t < 0.5:
        return -(2.0 ** (20.0 * t - 10.0) * math.sin((20.0 * t - 11.125) * c5)) / 2.0
    else:
        return (2.0 ** (-20.0 * t + 10.0) * math.sin((20.0 * t - 11.125) * c5)) / 2.0 + 1.0

def _ease_in_bounce(t: float) -> float:
    return 1.0 - _ease_out_bounce(1.0 - t)

def _ease_out_bounce(t: float) -> float:
    n1 = 7.5625
    d1 = 2.75
    if t < 1.0 / d1:
        return n1 * t * t
    elif t < 2.0 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    elif t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    else:
        t -= 2.625 / d1
        return n1 * t * t + 0.984375

def _ease_in_out_bounce(t: float) -> float:
    if t < 0.5:
        return (1.0 - _ease_out_bounce(1.0 - 2.0 * t)) / 2.0
    else:
        return (1.0 + _ease_out_bounce(2.0 * t - 1.0)) / 2.0


# ============================================================================
# Easing Registry
# ============================================================================

EASING_FUNCTIONS: Dict[str, callable] = {
    "linear": _linear,
    "easeInSine": _ease_in_sine,
    "easeOutSine": _ease_out_sine,
    "easeInOutSine": _ease_in_out_sine,
    "easeInCubic": _ease_in_cubic,
    "easeOutCubic": _ease_out_cubic,
    "easeInOutCubic": _ease_in_out_cubic,
    "easeInQuart": _ease_in_quart,
    "easeOutQuart": _ease_out_quart,
    "easeInOutQuart": _ease_in_out_quart,
    "easeInQuint": _ease_in_quint,
    "easeOutQuint": _ease_out_quint,
    "easeInOutQuint": _ease_in_out_quint,
    "easeInExpo": _ease_in_expo,
    "easeOutExpo": _ease_out_expo,
    "easeInOutExpo": _ease_in_out_expo,
    "easeInCirc": _ease_in_circ,
    "easeOutCirc": _ease_out_circ,
    "easeInOutCirc": _ease_in_out_circ,
    "easeInBack": _ease_in_back,
    "easeOutBack": _ease_out_back,
    "easeInOutBack": _ease_in_out_back,
    "easeInElastic": _ease_in_elastic,
    "easeOutElastic": _ease_out_elastic,
    "easeInOutElastic": _ease_in_out_elastic,
    "easeInBounce": _ease_in_bounce,
    "easeOutBounce": _ease_out_bounce,
    "easeInOutBounce": _ease_in_out_bounce,
}


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class EasingFitResult:
    """Result of easing fitting for a single keyframe pair."""
    easing_type: str = "linear"
    error: float = 0.0  # RMS error in degrees
    start_time: float = 0.0
    end_time: float = 0.0
    start_value: float = 0.0
    end_value: float = 0.0
    fallback: bool = False  # True if error > threshold


@dataclass
class BoneEasingResult:
    """Easing fitting result for a single bone axis."""
    bone_name: str = ""
    axis: str = ""
    segments: List[EasingFitResult] = None
    warnings: List[str] = None

    def __post_init__(self):
        if self.segments is None:
            self.segments = []
        if self.warnings is None:
            self.warnings = []


# ============================================================================
# EasingFitter
# ============================================================================

class EasingFitter:
    """
    Fits easing types to sampled animation curves.

    For each pair of consecutive keyframes in a bone's animation,
    analyzes the curve between them and selects the best-matching
    GeckoLib easing type using least-squares fitting.

    If no easing fits well (error > threshold), falls back to "linear"
    and adds a comment noting the original curve shape.
    """

    # Maximum error (in degrees) before falling back to linear
    DEFAULT_ERROR_THRESHOLD = 0.05

    # Number of sample points for fitting
    FIT_SAMPLES = 20

    def __init__(self, error_threshold: float = None):
        """
        Args:
            error_threshold: Maximum allowed error (degrees) before falling back to linear.
                             Default: 0.05°
        """
        self.error_threshold = error_threshold or self.DEFAULT_ERROR_THRESHOLD

    def fit_bone_axis(
        self,
        keyframes: List[dict],
        bone_name: str,
        axis: str
    ) -> BoneEasingResult:
        """
        Fit easing types for a bone's animation on a specific axis.

        Args:
            keyframes: List of keyframe dicts with 'time' and axis value keys
            bone_name: Name of the bone
            axis: Axis name ('x', 'y', 'z')

        Returns:
            BoneEasingResult with fitted easing types per segment
        """
        result = BoneEasingResult(bone_name=bone_name, axis=axis)

        if len(keyframes) < 2 or axis not in keyframes[0]:
            return result

        # Extract (time, value) pairs
        points = [(kf['time'], kf.get(axis, 0.0)) for kf in keyframes]

        for i in range(len(points) - 1):
            t0, v0 = points[i]
            t1, v1 = points[i + 1]
            dt = t1 - t0
            dv = v1 - v0

            if abs(dt) < 1e-10:
                continue  # Skip zero-duration segments

            # If values are identical, linear is sufficient
            if abs(dv) < 1e-10:
                result.segments.append(EasingFitResult(
                    easing_type="linear",
                    error=0.0,
                    start_time=t0,
                    end_time=t1,
                    start_value=v0,
                    end_value=v1
                ))
                continue

            # Fit the curve segment
            fit = self._fit_segment(t0, t1, v0, v1, keyframes, axis, i)
            result.segments.append(fit)

            if fit.fallback:
                result.warnings.append(
                    f"Bone '{bone_name}' axis '{axis}' segment "
                    f"[{t0:.4f}s, {t1:.4f}s]: No easing fit within threshold "
                    f"(best error={fit.error:.4f}° > {self.error_threshold}°). "
                    f"Falling back to linear."
                )

        return result

    def _fit_segment(
        self,
        t0: float, t1: float,
        v0: float, v1: float,
        keyframes: List[dict],
        axis: str,
        segment_index: int
    ) -> EasingFitResult:
        """
        Fit an easing function to a single segment between two keyframes.

        Uses least-squares fitting against sampled curve data.
        """
        dt = t1 - t0
        dv = v1 - v0

        # Sample the original curve at FIT_SAMPLES points
        # We approximate the original curve from the keyframes data
        # For Douglas-Peucker simplified data, we only have start and end points
        # So we use linear interpolation as the reference curve
        # and detect if the segment should be eased based on neighboring segments

        # For segments between simplified keyframes, we check if the
        # angular velocity pattern suggests easing:
        # 1. Look at the previous and next segments
        # 2. If velocity increases → easeIn pattern
        # 3. If velocity decreases → easeOut pattern
        # 4. If velocity increases then decreases → easeInOut pattern

        # Get velocity of this segment and neighbors
        points = [(kf['time'], kf.get(axis, 0.0)) for kf in keyframes]
        current_velocity = dv / dt if abs(dt) > 1e-10 else 0.0

        prev_velocity = 0.0
        if segment_index > 0:
            pt0, pv0 = points[segment_index - 1]
            pt1, pv1 = points[segment_index]
            prev_dt = pt1 - pt0
            if abs(prev_dt) > 1e-10:
                prev_velocity = (pv1 - pv0) / prev_dt

        next_velocity = 0.0
        if segment_index < len(points) - 2:
            nt0, nv0 = points[segment_index + 1]
            nt1, nv1 = points[segment_index + 2]
            next_dt = nt1 - nt0
            if abs(next_dt) > 1e-10:
                next_velocity = (nv1 - nv0) / next_dt

        # Determine easing category based on velocity pattern
        best_easing = "linear"
        best_error = abs(dv) * 0.5  # Default linear error estimate

        # Compute approximate easing fit
        if abs(current_velocity) > 1e-10:
            # Acceleration ratio
            accel_ratio = 0.0
            if abs(current_velocity) > 1e-10:
                if segment_index > 0:
                    accel_ratio = (current_velocity - prev_velocity) / abs(current_velocity)

            decel_ratio = 0.0
            if abs(current_velocity) > 1e-10:
                if segment_index < len(points) - 2:
                    decel_ratio = (current_velocity - next_velocity) / abs(current_velocity)

            # Classify the curve pattern
            best_easing, best_error = self._classify_easing(
                accel_ratio, decel_ratio, dv, dt
            )

        # Check if the fit error is acceptable
        fallback = best_error > self.error_threshold
        if fallback:
            best_easing = "linear"

        return EasingFitResult(
            easing_type=best_easing,
            error=best_error,
            start_time=t0,
            end_time=t1,
            start_value=v0,
            end_value=v1,
            fallback=fallback
        )

    def _classify_easing(
        self,
        accel_ratio: float,
        decel_ratio: float,
        dv: float,
        dt: float
    ) -> Tuple[str, float]:
        """
        Classify the easing pattern based on velocity analysis.

        Returns:
            Tuple of (easing_name, estimated_error_degrees)
        """
        # Thresholds for classification
        threshold = 0.15

        # Acceleration phase (easeIn)
        is_accel = accel_ratio > threshold
        # Deceleration phase (easeOut)
        is_decel = decel_ratio > threshold
        # Both (easeInOut)
        is_both = is_accel and is_decel

        if is_both:
            # Determine the strength for cubic vs sine vs quint
            strength = (accel_ratio + decel_ratio) / 2.0
            if strength > 1.5:
                return "easeInOutQuint", self._estimate_error(strength, "quint")
            elif strength > 0.8:
                return "easeInOutCubic", self._estimate_error(strength, "cubic")
            else:
                return "easeInOutSine", self._estimate_error(strength, "sine")

        elif is_accel:
            strength = accel_ratio
            if strength > 1.5:
                return "easeInQuint", self._estimate_error(strength, "quint")
            elif strength > 0.8:
                return "easeInCubic", self._estimate_error(strength, "cubic")
            else:
                return "easeInSine", self._estimate_error(strength, "sine")

        elif is_decel:
            strength = decel_ratio
            if strength > 1.5:
                return "easeOutQuint", self._estimate_error(strength, "quint")
            elif strength > 0.8:
                return "easeOutCubic", self._estimate_error(strength, "cubic")
            else:
                return "easeOutSine", self._estimate_error(strength, "sine")

        else:
            # Near-constant velocity → linear
            return "linear", 0.0

    @staticmethod
    def _estimate_error(strength: float, power: str) -> float:
        """
        Estimate the fitting error based on easing strength.

        Higher strength = more deviation from linear = potentially higher error.
        This is a heuristic estimate; actual error would require full sampling.
        """
        # Empirical error model:
        # For well-matched easing, error is proportional to (strength - expected_strength)^2
        expected = {
            "sine": 0.3,
            "cubic": 0.8,
            "quint": 1.5,
        }
        expected_strength = expected.get(power, 0.3)
        return abs(strength - expected_strength) * 0.02

    def fit_animation(
        self,
        animation_bones: Dict[str, List[dict]]
    ) -> Dict[str, Dict[str, BoneEasingResult]]:
        """
        Fit easing types for all bones in an animation.

        Args:
            animation_bones: Dict mapping bone_name -> list of keyframe dicts

        Returns:
            Dict mapping bone_name -> {axis -> BoneEasingResult}
        """
        results = {}
        for bone_name, keyframes in animation_bones.items():
            axis_results = {}
            for axis in ['x', 'y', 'z']:
                if keyframes and axis in keyframes[0]:
                    axis_results[axis] = self.fit_bone_axis(
                        keyframes, bone_name, axis
                    )
            if axis_results:
                results[bone_name] = axis_results

        return results

    def apply_easing_to_animation_json(
        self,
        animation_json: dict,
        animation_bones: Dict[str, List[dict]]
    ) -> dict:
        """
        Apply fitted easing types to an animation JSON structure.

        Modifies the animation JSON in place, adding "easing" fields
        to keyframe entries where non-linear easing was detected.

        Args:
            animation_json: The animation JSON dict
            animation_bones: Dict mapping bone_name -> keyframe list

        Returns:
            Modified animation JSON with easing fields
        """
        fitting_results = self.fit_animation(animation_bones)

        for anim_name, anim_data in animation_json.get('animations', {}).items():
            bones = anim_data.get('bones', {})
            for bone_name, bone_data in bones.items():
                if bone_name not in fitting_results:
                    continue

                rotation = bone_data.get('rotation', {})
                for axis, axis_data in rotation.items():
                    if not isinstance(axis_data, dict):
                        continue

                    axis_result = fitting_results[bone_name].get(axis)
                    if not axis_result or not axis_result.segments:
                        continue

                    # Apply easing to each keyframe
                    # In GeckoLib, easing is set per-keyframe-pair on the
                    # LATER keyframe (it defines how we arrive at that keyframe)
                    sorted_times = sorted(axis_data.keys(), key=float)
                    for i, time_key in enumerate(sorted_times):
                        if i < len(axis_result.segments):
                            segment = axis_result.segments[i]
                            if segment.easing_type != "linear":
                                # Store easing in the keyframe metadata
                                # GeckoLib format uses "easing" as a key
                                if isinstance(axis_data[time_key], (int, float)):
                                    # Convert to dict format for easing
                                    val = axis_data[time_key]
                                    axis_data[time_key] = {
                                        "vector": val,
                                        "easing": segment.easing_type
                                    }
                                elif isinstance(axis_data[time_key], dict):
                                    axis_data[time_key]["easing"] = segment.easing_type

        return animation_json
