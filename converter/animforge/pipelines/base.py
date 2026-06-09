"""Pipeline Base - Common Utilities for Animation Processing

Provides:
- Catmull-Rom interpolation (with loop wrapping)
- C0 continuity enforcement (snap last KF to first)
- C1 continuity enforcement (global cubic + transition zone blend)
- Douglas-Peucker simplification (iterative, with protected times)
- Minimum keyframe guarantee
"""

from __future__ import annotations

import math
import copy
from typing import Callable, Dict, List, Optional, Set, Tuple

from ..core.config import AnimForgeConfig
from ..core.parser import ParsedAnimation, Keyframes, BoneChannels
from ..core.profile import AnimationProfile, BoneRole


class PipelineBase:
    """Base class for animation processing pipelines.

    Provides shared utilities for interpolation, continuity enforcement,
    and simplification. Subclasses implement specific processing orders.
    """

    def __init__(self, config: AnimForgeConfig | None = None) -> None:
        self.config = config or AnimForgeConfig()

    # ── Catmull-Rom Interpolation ─────────────────────────────────────────

    @staticmethod
    def catmull_rom_point(
        p0: Tuple[float, ...],
        p1: Tuple[float, ...],
        p2: Tuple[float, ...],
        p3: Tuple[float, ...],
        t: float,
    ) -> Tuple[float, ...]:
        """Evaluate Catmull-Rom spline at parameter t ∈ [0, 1].

        Interpolates between p1 and p2 using tangent estimates from p0 and p3.
        Supports arbitrary tuple dimensions (3D for rotation/position).
        """
        t2 = t * t
        t3 = t2 * t

        result = []
        for i in range(len(p1)):
            v0, v1, v2, v3 = p0[i], p1[i], p2[i], p3[i]
            # Catmull-Rom coefficients
            a = -0.5 * v0 + 1.5 * v1 - 1.5 * v2 + 0.5 * v3
            b = v0 - 2.5 * v1 + 2.0 * v2 - 0.5 * v3
            c = -0.5 * v0 + 0.5 * v2
            d = v1
            result.append(a * t3 + b * t2 + c * t + d)

        return tuple(result)

    def catmull_rom_interpolate(
        self,
        keyframes: Keyframes,
        t: float,
        loop: bool = False,
        duration: float = 0.0,
    ) -> Tuple[float, float, float]:
        """Interpolate a value at time t using Catmull-Rom spline.

        Args:
            keyframes: Sorted keyframe list [(time, (x,y,z)), ...].
            t: Target time.
            loop: Whether the animation loops (affects boundary tangents).
            duration: Total animation duration (needed for loop wrapping).

        Returns:
            Interpolated (x, y, z) tuple.
        """
        if not keyframes:
            return (0.0, 0.0, 0.0)

        if len(keyframes) == 1:
            return keyframes[0][1]

        # Clamp t to keyframe range
        if t <= keyframes[0][0]:
            return keyframes[0][1]
        if t >= keyframes[-1][0]:
            return keyframes[-1][1]

        # Find the segment containing t
        seg_idx = 0
        for i in range(len(keyframes) - 1):
            if keyframes[i][0] <= t <= keyframes[i + 1][0]:
                seg_idx = i
                break

        # Get the 4 control points for Catmull-Rom
        p1_time, p1_val = keyframes[seg_idx]
        p2_time, p2_val = keyframes[seg_idx + 1]

        # Previous point (p0)
        if seg_idx > 0:
            _, p0_val = keyframes[seg_idx - 1]
        elif loop and duration > 0:
            # Wrap: use last keyframe as p0
            _, p0_val = keyframes[-1]
        else:
            p0_val = p1_val  # Clamp

        # Next point (p3)
        if seg_idx + 2 < len(keyframes):
            _, p3_val = keyframes[seg_idx + 2]
        elif loop and duration > 0:
            # Wrap: use first keyframe as p3
            _, p3_val = keyframes[0]
        else:
            p3_val = p2_val  # Clamp

        # Compute local parameter
        seg_duration = p2_time - p1_time
        if seg_duration < 1e-10:
            local_t = 0.0
        else:
            local_t = (t - p1_time) / seg_duration

        result = self.catmull_rom_point(p0_val, p1_val, p2_val, p3_val, local_t)
        return (result[0], result[1], result[2])

    def catmull_rom_upsample(
        self,
        keyframes: Keyframes,
        target_count: int,
        loop: bool = False,
        duration: float = 0.0,
        protected_times: Optional[Set[float]] = None,
    ) -> Keyframes:
        """Upsample a keyframe channel to have at least target_count keyframes.

        Inserts new keyframes between existing ones using Catmull-Rom
        interpolation. Existing keyframes at protected times are always preserved.

        Args:
            keyframes: Original keyframe list.
            target_count: Desired minimum number of keyframes.
            loop: Whether animation loops.
            duration: Animation duration.
            protected_times: Times of keyframes that must be preserved exactly.

        Returns:
            New keyframe list with at least target_count entries.
        """
        if len(keyframes) >= target_count or len(keyframes) < 2:
            return list(keyframes)

        if protected_times is None:
            protected_times = set()

        duration = duration if duration > 0 else keyframes[-1][0]

        # Generate uniform target times
        existing_times = set(kf[0] for kf in keyframes)
        all_times: List[float] = sorted(
            set(
                [kf[0] for kf in keyframes]
                + [self.config.round_time(i * duration / (target_count - 1)) for i in range(target_count)]
            )
        )

        # Remove duplicates too close to existing times
        filtered_times: List[float] = []
        for t in all_times:
            if t in existing_times or t in protected_times:
                filtered_times.append(t)
                continue
            # Check if too close to an existing time
            too_close = any(abs(t - et) < duration / (target_count * 4) for et in existing_times)
            if not too_close:
                filtered_times.append(t)

        # Build result: existing KFs preserved, new ones interpolated
        result: Keyframes = []
        existing_map = {kf[0]: kf[1] for kf in keyframes}

        for t in filtered_times:
            if t in existing_map:
                result.append((t, existing_map[t]))
            else:
                val = self.catmull_rom_interpolate(keyframes, t, loop, duration)
                result.append((t, val))

        result.sort(key=lambda kf: kf[0])
        return result

    # ── C0 Continuity ─────────────────────────────────────────────────────

    def enforce_c0(
        self,
        keyframes: Keyframes,
        loop: bool = False,
    ) -> Keyframes:
        """Enforce C0 continuity for loop animations.

        Snaps the last keyframe's values to match the first keyframe.
        For non-loop animations, this is a no-op.
        """
        if not loop or len(keyframes) < 2:
            return keyframes

        result = list(keyframes)
        first_val = result[0][1]

        # Snap last keyframe to first keyframe values
        last_time = result[-1][0]
        result[-1] = (last_time, first_val)

        return result

    def enforce_c0_all(
        self,
        anim: ParsedAnimation,
    ) -> None:
        """Enforce C0 on all channels of a loop animation in-place."""
        if not self._is_loop(anim):
            return

        for bone_name, channels in anim.bone_channels.items():
            for ch_name, kfs in channels.items():
                anim.bone_channels[bone_name][ch_name] = self.enforce_c0(
                    kfs, loop=True
                )

    # ── C1 Continuity ─────────────────────────────────────────────────────

    def enforce_c1_global_cubic(
        self,
        keyframes: Keyframes,
        duration: float,
        distortion_limit: float = 0.5,
    ) -> Keyframes:
        """Enforce C1 continuity using global cubic correction.

        Computes a cubic correction function that makes the velocity at the
        loop boundary continuous. Falls back to no correction if the
        distortion exceeds the limit.

        Args:
            keyframes: Keyframe list (assumed C0 already enforced).
            duration: Animation duration.
            distortion_limit: Max allowed RMS distortion from correction.

        Returns:
            Corrected keyframe list.
        """
        if len(keyframes) < 3 or duration <= 0:
            return keyframes

        # Estimate velocity at end and start
        # Velocity at end: backward difference from last two KFs
        vel_end = self._estimate_velocity_backward(keyframes, len(keyframes) - 1)
        # Velocity at start: forward difference from first two KFs
        vel_start = self._estimate_velocity_forward(keyframes, 0)

        # Velocity mismatch
        vel_diff = tuple(vel_end[i] - vel_start[i] for i in range(3))

        # If already C1, no correction needed
        mismatch_mag = math.sqrt(sum(v * v for v in vel_diff))
        if mismatch_mag < self.config.c0_threshold:
            return keyframes

        # Compute global cubic correction
        # f(t) = vel_diff * (t/d)^2 * (3 - 2*t/d)  (Hermite smoothstep)
        corrected: Keyframes = []
        total_distortion_sq = 0.0

        for time, values in keyframes:
            t_norm = time / duration
            # Smoothstep blend factor
            blend = t_norm * t_norm * (3.0 - 2.0 * t_norm)

            new_vals = tuple(
                values[i] + vel_diff[i] * blend for i in range(3)
            )

            distortion_sq = sum(
                (new_vals[i] - values[i]) ** 2 for i in range(3)
            )
            total_distortion_sq += distortion_sq

            corrected.append((time, new_vals))

        # Check distortion
        rms_distortion = math.sqrt(total_distortion_sq / len(corrected))
        if rms_distortion > distortion_limit:
            # Global cubic would distort too much; return original
            # (Caller should fall back to transition zone blend)
            return keyframes

        return corrected

    def enforce_c1_transition_blend(
        self,
        keyframes: Keyframes,
        duration: float,
        zone_fraction: float = 0.15,
    ) -> Keyframes:
        """Enforce C1 using transition zone blending.

        Blends the velocity at the loop boundary within a transition zone
        at the end of the animation. This is gentler than global cubic
        correction and preserves the shape of the main animation.

        Args:
            keyframes: Keyframe list (assumed C0 already enforced).
            duration: Animation duration.
            zone_fraction: Fraction of duration for the transition zone.

        Returns:
            Corrected keyframe list.
        """
        if len(keyframes) < 3 or duration <= 0:
            return keyframes

        vel_end = self._estimate_velocity_backward(keyframes, len(keyframes) - 1)
        vel_start = self._estimate_velocity_forward(keyframes, 0)

        vel_diff = tuple(vel_end[i] - vel_start[i] for i in range(3))

        mismatch_mag = math.sqrt(sum(v * v for v in vel_diff))
        if mismatch_mag < self.config.c0_threshold:
            return keyframes

        zone_start = duration * (1.0 - zone_fraction)
        corrected: Keyframes = []

        for time, values in keyframes:
            if time < zone_start:
                # Before transition zone: no change
                corrected.append((time, values))
            else:
                # In transition zone: gradually blend toward C1
                t_zone = (time - zone_start) / (duration - zone_start) if duration > zone_start else 1.0
                t_zone = max(0.0, min(1.0, t_zone))

                # Smooth blend from 0 to 1 within the zone
                blend = t_zone * t_zone * (3.0 - 2.0 * t_zone)  # smoothstep

                # Apply velocity correction
                correction = tuple(
                    vel_diff[i] * blend for i in range(3)
                )
                new_vals = tuple(
                    values[i] - correction[i] for i in range(3)
                )
                corrected.append((time, new_vals))

        # Re-enforce C0 to ensure last = first
        corrected = self.enforce_c0(corrected, loop=True)

        return corrected

    @staticmethod
    def _estimate_velocity_forward(keyframes: Keyframes, idx: int) -> Tuple[float, float, float]:
        """Estimate velocity at keyframe idx using forward difference."""
        if idx >= len(keyframes) - 1:
            return (0.0, 0.0, 0.0)

        dt = keyframes[idx + 1][0] - keyframes[idx][0]
        if dt < 1e-10:
            return (0.0, 0.0, 0.0)

        v1 = keyframes[idx][1]
        v2 = keyframes[idx + 1][1]
        return tuple((v2[i] - v1[i]) / dt for i in range(3))

    @staticmethod
    def _estimate_velocity_backward(keyframes: Keyframes, idx: int) -> Tuple[float, float, float]:
        """Estimate velocity at keyframe idx using backward difference."""
        if idx <= 0 or idx >= len(keyframes):
            return (0.0, 0.0, 0.0)

        dt = keyframes[idx][0] - keyframes[idx - 1][0]
        if dt < 1e-10:
            return (0.0, 0.0, 0.0)

        v1 = keyframes[idx - 1][1]
        v2 = keyframes[idx][1]
        return tuple((v2[i] - v1[i]) / dt for i in range(3))

    # ── Douglas-Peucker Simplification ─────────────────────────────────────

    def dp_simplify(
        self,
        keyframes: Keyframes,
        epsilon: float,
        protected_times: Optional[Set[float]] = None,
    ) -> Keyframes:
        """Simplify keyframes using iterative Douglas-Peucker algorithm.

        Protected keyframes (at specified times, plus first and last) are
        never removed.

        Args:
            keyframes: Keyframe list to simplify.
            epsilon: Maximum allowed deviation (in degrees for rotation).
            protected_times: Set of times whose keyframes must not be removed.

        Returns:
            Simplified keyframe list.
        """
        if len(keyframes) <= 2:
            return list(keyframes)

        if protected_times is None:
            protected_times = set()

        # Always protect first and last keyframes
        if self.config.dp_protected_first_last:
            protected_times = protected_times | {keyframes[0][0], keyframes[-1][0]}

        # Build list of (time, values, is_protected)
        items = [
            (kf[0], kf[1], kf[0] in protected_times)
            for kf in keyframes
        ]

        # Mark indices of protected items
        protected_indices = set()
        for i, item in enumerate(items):
            if item[2]:
                protected_indices.add(i)

        # Iterative DP: keep removing the point with smallest deviation
        # until all remaining have deviation > epsilon
        result_indices = list(range(len(items)))

        while len(result_indices) > 2:
            # Find the point with the smallest max deviation from the line
            # connecting its neighbors
            min_deviation = float("inf")
            min_idx = -1

            for i in range(1, len(result_indices) - 1):
                abs_idx = result_indices[i]

                # Skip protected keyframes
                if abs_idx in protected_indices:
                    continue

                # Compute deviation from line between neighbors
                prev_abs = result_indices[i - 1]
                next_abs = result_indices[i + 1]

                deviation = self._point_line_deviation(
                    items[prev_abs][1],  # line start value
                    items[next_abs][1],  # line end value
                    items[abs_idx][1],   # point value
                    items[prev_abs][0],  # line start time
                    items[next_abs][0],  # line end time
                    items[abs_idx][0],   # point time
                )

                if deviation < min_deviation:
                    min_deviation = deviation
                    min_idx = i

            # If the smallest deviation is above epsilon, stop
            if min_deviation >= epsilon or min_idx == -1:
                break

            # Remove the point with smallest deviation
            result_indices.pop(min_idx)

        return [(items[i][0], items[i][1]) for i in result_indices]

    @staticmethod
    def _point_line_deviation(
        line_start: Tuple[float, ...],
        line_end: Tuple[float, ...],
        point: Tuple[float, ...],
        t_start: float,
        t_end: float,
        t_point: float,
    ) -> float:
        """Compute the maximum deviation of a point from a line segment.

        Uses the perpendicular distance from the point to the line in each
        dimension, returning the maximum.
        """
        if abs(t_end - t_start) < 1e-10:
            # Degenerate: line start and end at same time
            return max(abs(point[i] - line_start[i]) for i in range(len(point)))

        # Parameter along the line
        t_param = (t_point - t_start) / (t_end - t_start)
        t_param = max(0.0, min(1.0, t_param))

        # Interpolated point on the line
        interp = tuple(
            line_start[i] + t_param * (line_end[i] - line_start[i])
            for i in range(len(point))
        )

        # Maximum deviation across dimensions
        return max(abs(point[i] - interp[i]) for i in range(len(point)))

    def dp_simplify_channel(
        self,
        keyframes: Keyframes,
        epsilon: float,
        is_walk_leg: bool = False,
        duration: float = 0.0,
        protected_times: List[float] | None = None,
    ) -> Keyframes:
        """Simplify a channel with walk-leg-specific protections.

        For walk leg bones, uses tighter epsilon and protects local extrema.
        Additional protected_times can be provided to prevent removal of
        specific keyframe times.
        """
        if is_walk_leg:
            epsilon *= self.config.dp_walk_leg_epsilon_mult

        # Collect protected times
        protected: Set[float] = set()

        # Add any caller-provided protected times
        if protected_times:
            protected.update(protected_times)

        # For walk legs, protect extrema (local min/max in any axis)
        if is_walk_leg and len(keyframes) > 2:
            protected.update(self._find_extrema_times(keyframes))

        # Always protect first and last
        if keyframes:
            protected.add(keyframes[0][0])
            protected.add(keyframes[-1][0])

        return self.dp_simplify(keyframes, epsilon, protected)

    @staticmethod
    def _find_extrema_times(keyframes: Keyframes) -> Set[float]:
        """Find times of local extrema in any axis."""
        extrema: Set[float] = set()
        n = len(keyframes)
        if n < 3:
            return extrema

        for axis in range(3):
            for i in range(1, n - 1):
                prev_val = keyframes[i - 1][1][axis]
                curr_val = keyframes[i][1][axis]
                next_val = keyframes[i + 1][1][axis]

                # Local maximum
                if curr_val >= prev_val and curr_val >= next_val:
                    extrema.add(keyframes[i][0])
                # Local minimum
                elif curr_val <= prev_val and curr_val <= next_val:
                    extrema.add(keyframes[i][0])

        return extrema

    # ── Minimum Keyframe Guarantee ────────────────────────────────────────

    def ensure_min_keyframes(
        self,
        keyframes: Keyframes,
        min_count: int,
        loop: bool = False,
        duration: float = 0.0,
    ) -> Keyframes:
        """Ensure a channel has at least min_count keyframes.

        If below the minimum, upsamples using Catmull-Rom interpolation.
        Existing keyframes are always preserved.
        """
        if len(keyframes) >= min_count:
            return keyframes

        if len(keyframes) < 2:
            # Can't meaningfully upsample with < 2 KFs
            return keyframes

        duration = duration if duration > 0 else keyframes[-1][0]

        return self.catmull_rom_upsample(
            keyframes,
            target_count=min_count,
            loop=loop,
            duration=duration,
        )

    # ── Utility Methods ───────────────────────────────────────────────────

    @staticmethod
    def _is_loop(anim: ParsedAnimation) -> bool:
        """Check if an animation is configured to loop."""
        return anim.loop == "loop"

    def round_keyframes(self, keyframes: Keyframes) -> Keyframes:
        """Round all time and value entries to configured precision."""
        return [
            (
                self.config.round_time(t),
                tuple(self.config.round_value(v) for v in vals),
            )
            for t, vals in keyframes
        ]

    def round_all_channels(self, anim: ParsedAnimation) -> None:
        """Round all channel data in-place."""
        for bone_name in anim.bone_channels:
            for ch_name in anim.bone_channels[bone_name]:
                anim.bone_channels[bone_name][ch_name] = self.round_keyframes(
                    anim.bone_channels[bone_name][ch_name]
                )

    @staticmethod
    def compute_amplitude(keyframes: Keyframes) -> float:
        """Compute peak-to-peak amplitude of keyframe data."""
        if not keyframes:
            return 0.0
        xs = [kf[1][0] for kf in keyframes]
        ys = [kf[1][1] for kf in keyframes]
        zs = [kf[1][2] for kf in keyframes]
        return max(
            max(xs) - min(xs),
            max(ys) - min(ys),
            max(zs) - min(zs),
        )

    @staticmethod
    def mirror_keyframes(
        keyframes: Keyframes,
        duration: float,
        mirror_fn: Optional[Callable[[Tuple[float, float, float]], Tuple[float, float, float]]] = None,
    ) -> Keyframes:
        """Mirror keyframes: create a half-cycle mirror for walk animations.

        Takes the first half of the cycle and creates a mirrored version
        for the second half. The mirror function transforms bone values
        (e.g., negating X/Z for opposite-side legs).

        Args:
            keyframes: Original keyframes (assumed first half of cycle).
            duration: Full cycle duration.
            mirror_fn: Function to transform values for the mirrored half.

        Returns:
            Complete cycle keyframes.
        """
        if not keyframes or duration <= 0:
            return keyframes

        half_duration = duration / 2.0

        # First half: keep as-is (but shift so it starts at t=0)
        first_half: Keyframes = []
        for t, vals in keyframes:
            if t <= half_duration:
                first_half.append((t, vals))

        if not first_half:
            return keyframes

        # Create mirrored second half
        if mirror_fn is None:
            # Default mirror: negate X and Z (typical for left/right leg swap)
            def default_mirror(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
                return (-v[0], v[1], -v[2])
            mirror_fn = default_mirror

        second_half: Keyframes = []
        for t, vals in first_half:
            # Map time to second half
            new_t = t + half_duration
            if new_t <= duration:
                new_vals = mirror_fn(vals)
                second_half.append((new_t, new_vals))

        # Combine
        result = first_half + second_half
        result.sort(key=lambda kf: kf[0])

        # Remove any duplicate at the boundary
        cleaned: Keyframes = [result[0]]
        for i in range(1, len(result)):
            if abs(result[i][0] - cleaned[-1][0]) > 1e-6:
                cleaned.append(result[i])

        return cleaned
