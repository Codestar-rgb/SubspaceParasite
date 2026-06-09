"""Animation Differentiator

Creates distinct variants for identical source animations based on their
category. This is applied after dedup detection but BEFORE pipeline processing.

Variants:
- Attack: Speed up 1.3x, increase arm swing amplitude 30%, add body lunge
- Evolved: Slow down 1.2x, add body tremor, add head sway, add breathing pulse
- Idle: Keep unchanged as baseline
- Walk: Keep unchanged (walk processing handles its own differentiation)
- Death/Sleep/Unknown: Keep unchanged
"""

from __future__ import annotations

import copy
import math
from typing import Dict, List, Optional, Set, Tuple

from ..core.config import AnimForgeConfig
from ..core.parser import ParsedAnimation, Keyframes, BoneChannels
from ..core.profile import AnimationProfile, AnimCategory, BoneRole


class AnimationDifferentiator:
    """Creates distinct variants for identical cross-category animations.

    When multiple animations share the same source data but belong to
    different categories, this differentiator applies category-specific
    modifications to make them visually distinct in-game.
    """

    def __init__(self, config: AnimForgeConfig | None = None) -> None:
        self.config = config or AnimForgeConfig()

    def differentiate(
        self,
        anim: ParsedAnimation,
        profile: AnimationProfile,
    ) -> ParsedAnimation:
        """Apply category-specific differentiation to an animation.

        Creates a deep copy and modifies keyframe values based on category.

        Args:
            anim: Original parsed animation (NOT modified).
            profile: Animation profile with category.

        Returns:
            New ParsedAnimation with differentiated data.
        """
        category = profile.category

        if category == AnimCategory.ATTACK:
            return self._differentiate_attack(anim, profile)
        elif category == AnimCategory.EVOLVED:
            return self._differentiate_evolved(anim, profile)
        elif category == AnimCategory.IDLE:
            # Idle is the baseline - no changes
            return anim.deep_copy()
        elif category == AnimCategory.WALK:
            # Walk handles its own processing
            return anim.deep_copy()
        else:
            # Death/Sleep/Unknown: no differentiation
            return anim.deep_copy()

    def _differentiate_attack(
        self, anim: ParsedAnimation, profile: AnimationProfile
    ) -> ParsedAnimation:
        """Create attack variant: speed up 1.3x, bigger arm swing, body lunge.

        Modifications:
        1. Speed: compress timeline by attack_speed_mult (1.3x faster)
        2. Arm amplitude: scale arm rotation by attack_arm_amplitude_mult (1.3x)
        3. Body lunge: add forward X rotation pulse to body bones
        """
        result = anim.deep_copy()
        speed_mult = self.config.attack_speed_mult
        amp_mult = self.config.attack_arm_amplitude_mult
        lunge_deg = self.config.attack_body_lunge_degrees
        duration = result.length

        # 1. Speed up: compress timeline
        if duration > 0 and speed_mult != 1.0:
            new_duration = duration / speed_mult
            for bone_name in result.bone_channels:
                for ch_name in result.bone_channels[bone_name]:
                    kfs = result.bone_channels[bone_name][ch_name]
                    result.bone_channels[bone_name][ch_name] = [
                        (self.config.round_time(t / speed_mult), vals)
                        for t, vals in kfs
                    ]
            result.length = self.config.round_time(new_duration)

        # 2. Increase arm swing amplitude
        arm_bones = profile.arm_bones
        for bone_name in arm_bones:
            if bone_name not in result.bone_channels:
                continue
            for ch_name in result.bone_channels[bone_name]:
                kfs = result.bone_channels[bone_name][ch_name]
                result.bone_channels[bone_name][ch_name] = [
                    (t, tuple(v * amp_mult for v in vals))
                    for t, vals in kfs
                ]

        # 3. Add body lunge: X rotation pulse peaking at 30% of duration
        body_bones = profile.body_bones
        new_duration = result.length
        for bone_name in body_bones:
            if bone_name not in result.bone_channels:
                continue
            if "rotation" not in result.bone_channels[bone_name]:
                # Add a rotation channel with just the lunge
                result.bone_channels[bone_name]["rotation"] = self._create_lunge_keyframes(
                    new_duration, lunge_deg
                )
            else:
                # Add lunge to existing rotation channel
                kfs = result.bone_channels[bone_name]["rotation"]
                result.bone_channels[bone_name]["rotation"] = self._add_lunge(
                    kfs, new_duration, lunge_deg
                )

        return result

    def _differentiate_evolved(
        self, anim: ParsedAnimation, profile: AnimationProfile
    ) -> ParsedAnimation:
        """Create evolved variant: slow down, body tremor, head sway, breathing pulse.

        Modifications:
        1. Speed: stretch timeline by 1/evolved_speed_mult (1.2x slower)
        2. Body tremor: high-frequency small-amplitude X rotation oscillation
        3. Head sway: sinusoidal Y rotation oscillation
        4. Breathing pulse: subtle Y position oscillation on body bones
        """
        result = anim.deep_copy()
        speed_mult = self.config.evolved_speed_mult
        tremor_amp = self.config.evolved_body_tremor_amplitude
        sway_amp = self.config.evolved_head_sway_amplitude
        breath_amp = self.config.evolved_breathing_pulse_amplitude
        duration = result.length

        # 1. Slow down: stretch timeline
        if duration > 0 and speed_mult != 1.0:
            for bone_name in result.bone_channels:
                for ch_name in result.bone_channels[bone_name]:
                    kfs = result.bone_channels[bone_name][ch_name]
                    result.bone_channels[bone_name][ch_name] = [
                        (self.config.round_time(t / speed_mult), vals)
                        for t, vals in kfs
                    ]
            result.length = self.config.round_time(duration / speed_mult)

        new_duration = result.length

        # 2. Body tremor: add high-frequency oscillation to body bones
        body_bones = profile.body_bones
        tremor_freq = 12.0  # Hz - fast tremor
        for bone_name in body_bones:
            if bone_name not in result.bone_channels:
                continue
            if "rotation" in result.bone_channels[bone_name]:
                kfs = result.bone_channels[bone_name]["rotation"]
                result.bone_channels[bone_name]["rotation"] = self._add_oscillation(
                    kfs, new_duration, tremor_freq, tremor_amp, axis=0
                )

        # 3. Head sway: sinusoidal Y rotation oscillation
        head_bones = profile.head_bones
        sway_freq = 2.0  # Hz - slow sway
        for bone_name in head_bones:
            if bone_name not in result.bone_channels:
                continue
            if "rotation" in result.bone_channels[bone_name]:
                kfs = result.bone_channels[bone_name]["rotation"]
                result.bone_channels[bone_name]["rotation"] = self._add_oscillation(
                    kfs, new_duration, sway_freq, sway_amp, axis=1
                )

        # 4. Breathing pulse: subtle Y position oscillation on body
        breath_freq = 1.5  # Hz - breathing rate
        for bone_name in body_bones:
            if bone_name not in result.bone_channels:
                continue
            if "position" in result.bone_channels[bone_name]:
                kfs = result.bone_channels[bone_name]["position"]
                result.bone_channels[bone_name]["position"] = self._add_oscillation(
                    kfs, new_duration, breath_freq, breath_amp, axis=1
                )

        return result

    # ── Helper Methods ────────────────────────────────────────────────────

    def _create_lunge_keyframes(
        self, duration: float, lunge_degrees: float
    ) -> Keyframes:
        """Create a simple lunge rotation channel with a pulse peaking at 30%."""
        peak_time = duration * 0.3
        return [
            (0.0, (0.0, 0.0, 0.0)),
            (self.config.round_time(peak_time), (lunge_degrees, 0.0, 0.0)),
            (self.config.round_time(duration), (0.0, 0.0, 0.0)),
        ]

    def _add_lunge(
        self, keyframes: Keyframes, duration: float, lunge_degrees: float
    ) -> Keyframes:
        """Add a lunge pulse to existing rotation keyframes."""
        peak_time = duration * 0.3
        # Create lunge envelope: ramps up then back down
        result: Keyframes = []
        for t, vals in keyframes:
            # Compute lunge contribution at this time
            if t <= peak_time:
                # Ramp up
                frac = t / peak_time if peak_time > 0 else 1.0
                lunge = lunge_degrees * frac
            else:
                # Ramp down
                frac = (t - peak_time) / (duration - peak_time) if duration > peak_time else 0.0
                lunge = lunge_degrees * (1.0 - frac)

            new_vals = (vals[0] + lunge, vals[1], vals[2])
            result.append((t, new_vals))

        return result

    def _add_oscillation(
        self,
        keyframes: Keyframes,
        duration: float,
        frequency: float,
        amplitude: float,
        axis: int = 0,
    ) -> Keyframes:
        """Add a sinusoidal oscillation to a specific axis of keyframe values."""
        result: Keyframes = []
        for t, vals in keyframes:
            if duration > 0:
                phase = 2.0 * math.pi * frequency * t / duration * duration
            else:
                phase = 0.0
            # Simpler: use t directly with frequency
            oscillation = amplitude * math.sin(2.0 * math.pi * frequency * t)

            new_vals = list(vals)
            new_vals[axis] = new_vals[axis] + oscillation
            result.append((t, tuple(new_vals)))

        return result
