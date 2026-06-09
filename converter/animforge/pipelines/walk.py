"""Walk Animation Pipeline

Processes walk animations with these steps IN ORDER:
1. Validate walk has leg bones
2. Half-cycle mirroring (if source only has half a gait cycle)
3. Catmull-Rom upsampling for sparse leg channels (<8 KF per channel)
4. C0 enforcement
5. Gentle C1 enforcement (transition zone blend, NOT global cubic)
6. Quality-gated DP simplification (very conservative: 5x tighter epsilon for legs)
7. Min keyframe guarantee (walk legs must have >=8 KF per channel)
8. Final C0 guarantee

CRITICAL: Do NOT extend a walk cycle that is already complete (start≈end values).
Only extend if duration < 0.5s AND start/end values don't match.
"""

from __future__ import annotations

import copy
import math
from typing import Dict, List, Optional, Set, Tuple

from .base import PipelineBase
from ..core.config import AnimForgeConfig
from ..core.parser import ParsedAnimation, Keyframes
from ..core.profile import AnimationProfile, BoneRole, AnimCategory


class WalkPipeline(PipelineBase):
    """Pipeline for walk/run animations with gait-cycle-aware processing.

    Key principle: walk animations are sacred. They must never be truncated
    or over-simplified. Leg bones get extra protection throughout.
    """

    def __init__(self, config: AnimForgeConfig | None = None) -> None:
        super().__init__(config)

    def process(self, anim: ParsedAnimation, profile: AnimationProfile) -> ParsedAnimation:
        """Process a walk animation through the full pipeline.

        Args:
            anim: Parsed animation data (will NOT be modified in place).
            profile: Animation profile with bone roles and walk metadata.

        Returns:
            New ParsedAnimation with processed keyframes.
        """
        result = anim.deep_copy()
        is_loop = self._is_loop(result)
        duration = result.length

        # Step 1: Validate walk has leg bones
        leg_bones = profile.leg_bones
        if not leg_bones:
            # No leg bones found; process as generic
            return self._process_as_generic(result, profile)

        # Step 2: Half-cycle mirroring (ONLY if incomplete cycle)
        if profile.is_half_cycle:
            self._apply_half_cycle_mirroring(result, profile)

        # Step 3: Catmull-Rom upsampling for sparse leg channels
        self._upsample_sparse_legs(result, profile)

        # Step 4: C0 enforcement
        self.enforce_c0_all(result)

        # Step 5: Gentle C1 enforcement (transition zone blend only)
        self._apply_c1_walk(result, profile)

        # Step 6: Quality-gated DP simplification (very conservative for legs)
        self._apply_dp_simplification_walk(result, profile)

        # Step 7: Min keyframe guarantee for walk legs
        self._ensure_min_kf_walk(result, profile)

        # Step 8: Final C0 guarantee
        self.enforce_c0_all(result)

        # Round all values
        self.round_all_channels(result)

        return result

    def _process_as_generic(self, anim: ParsedAnimation, profile: AnimationProfile) -> ParsedAnimation:
        """Fallback: process without walk-specific logic when no legs found."""
        from .generic import GenericPipeline
        generic = GenericPipeline(self.config)
        return generic.process(anim, profile)

    def _apply_half_cycle_mirroring(
        self, anim: ParsedAnimation, profile: AnimationProfile
    ) -> None:
        """Apply half-cycle mirroring for incomplete walk cycles.

        CRITICAL: Only mirrors if the animation is actually incomplete.
        A complete cycle (where start ≈ end) is never extended.
        """
        duration = anim.length
        if duration <= 0:
            return

        # Double-check: is this really a half cycle?
        # If first and last keyframes of any leg bone match, it's complete
        for bone_name in profile.leg_bones:
            kfs = anim.get_channel(bone_name, "rotation")
            if len(kfs) >= 2:
                start_val = kfs[0][1]
                end_val = kfs[-1][1]
                diff = max(abs(start_val[i] - end_val[i]) for i in range(3))
                if diff < self.config.c0_threshold * 10:
                    # This bone has a complete cycle, don't mirror
                    return

        # Also check duration - don't mirror long animations
        if duration >= 0.5:
            return

        # Apply mirroring for each bone
        for bone_name, channels in anim.bone_channels.items():
            bone_profile = profile.bones.get(bone_name)
            is_leg = bone_profile and bone_profile.role == BoneRole.LEG

            for ch_name in list(channels.keys()):
                kfs = channels[ch_name]
                if len(kfs) < 2:
                    continue

                # Create a mirrored second half
                double_duration = duration * 2.0
                mirror_fn = self._get_walk_mirror_fn(bone_name, bone_profile, ch_name)

                mirrored = self.mirror_keyframes(
                    kfs,
                    double_duration,
                    mirror_fn=mirror_fn,
                )

                anim.bone_channels[bone_name][ch_name] = mirrored

        # Update length
        anim.length = duration * 2.0

    @staticmethod
    def _get_walk_mirror_fn(
        bone_name: str,
        bone_profile: Optional[Any],
        channel: str,
    ) -> Optional[callable]:
        """Get the mirror function for a bone during half-cycle mirroring.

        For legs: mirror X and Z (invert swing direction)
        For arms: mirror X and Z
        For body: mirror X only
        For head: mirror X only
        """
        if bone_profile is None:
            return None

        role = bone_profile.role

        if role in (BoneRole.LEG, BoneRole.ARM):
            def mirror_limb(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
                return (-v[0], v[1], -v[2])
            return mirror_limb
        elif role in (BoneRole.BODY, BoneRole.HEAD):
            def mirror_body(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
                return (-v[0], v[1], v[2])
            return mirror_body

        return None

    def _upsample_sparse_legs(
        self, anim: ParsedAnimation, profile: AnimationProfile
    ) -> None:
        """Upsample sparse leg channels to at least the target count."""
        is_loop = self._is_loop(anim)
        duration = anim.length

        for bone_name in profile.leg_bones:
            if bone_name not in anim.bone_channels:
                continue

            for ch_name in list(anim.bone_channels[bone_name].keys()):
                kfs = anim.bone_channels[bone_name][ch_name]
                if len(kfs) < self.config.upsample_target:
                    upsampled = self.catmull_rom_upsample(
                        kfs,
                        target_count=self.config.upsample_target,
                        loop=is_loop,
                        duration=duration,
                    )
                    anim.bone_channels[bone_name][ch_name] = upsampled

    def _apply_c1_walk(
        self, anim: ParsedAnimation, profile: AnimationProfile
    ) -> None:
        """Apply gentle C1 enforcement for walk animations.

        Uses transition zone blend (NOT global cubic) to preserve walk shape.
        The transition zone is narrower for walk (15% by default).
        """
        is_loop = self._is_loop(anim)
        if not is_loop:
            return

        duration = anim.length
        zone_fraction = self.config.c1_transition_zone  # 15% for walk

        for bone_name, channels in anim.bone_channels.items():
            for ch_name in list(channels.keys()):
                kfs = channels[ch_name]
                if len(kfs) < 3:
                    continue

                corrected = self.enforce_c1_transition_blend(
                    kfs, duration, zone_fraction=zone_fraction
                )
                anim.bone_channels[bone_name][ch_name] = corrected

    def _apply_dp_simplification_walk(
        self, anim: ParsedAnimation, profile: AnimationProfile
    ) -> None:
        """Apply quality-gated DP simplification for walk animations.

        CRITICAL: Walk animations are sacred. We use VERY conservative
        simplification to preserve body bob, arm swing, and subtle motion.

        Strategy:
        - Walk leg bones: Use 10x tighter epsilon (0.05° instead of 0.5°)
        - Walk arm/body/head bones: Use 10x tighter epsilon
        - Always protect first/last keyframes AND local extrema
        - If simplification would drop amplitude below 70%, revert
        - If simplification would drop KF count below 80%, revert
        - For very small channels (<3 KFs), don't simplify at all
        """
        leg_bone_names = set(profile.leg_bones)
        base_epsilon = self.config.dp_epsilon
        # Walk uses 10x tighter epsilon for ALL bones
        walk_epsilon = base_epsilon * 0.1  # 0.05 degrees

        for bone_name, channels in anim.bone_channels.items():
            for ch_name in list(channels.keys()):
                kfs = channels[ch_name]
                original_count = len(kfs)

                # Don't simplify very sparse channels
                if original_count <= 3:
                    continue

                # Compute original amplitude
                orig_amp = self.compute_amplitude(kfs)

                # For very small amplitude channels, use even tighter epsilon
                if orig_amp < 1.0:
                    channel_epsilon = walk_epsilon * 0.1  # Ultra-tight for subtle motion
                else:
                    channel_epsilon = walk_epsilon

                # Find extrema times to protect
                extrema_times = self._find_extrema_times(kfs)

                simplified = self.dp_simplify_channel(
                    kfs,
                    epsilon=channel_epsilon,
                    is_walk_leg=True,  # Always protect like a walk leg
                    duration=anim.length,
                    protected_times=extrema_times,
                )

                # Quality gates
                # Gate 1: KF count must stay above 80% of original
                if len(simplified) < original_count * 0.8:
                    continue

                # Gate 2: Amplitude must be preserved above 70%
                simp_amp = self.compute_amplitude(simplified)
                if orig_amp > 0.01 and simp_amp / orig_amp < self.config.amplitude_fidelity_threshold:
                    continue

                anim.bone_channels[bone_name][ch_name] = simplified

    def _ensure_min_kf_walk(
        self, anim: ParsedAnimation, profile: AnimationProfile
    ) -> None:
        """Ensure walk leg bones have minimum required keyframes."""
        is_loop = self._is_loop(anim)
        duration = anim.length

        for bone_name in profile.leg_bones:
            if bone_name not in anim.bone_channels:
                continue

            for ch_name in list(anim.bone_channels[bone_name].keys()):
                kfs = anim.bone_channels[bone_name][ch_name]
                if len(kfs) < self.config.min_kf_walk_leg:
                    upsampled = self.ensure_min_keyframes(
                        kfs,
                        min_count=self.config.min_kf_walk_leg,
                        loop=is_loop,
                        duration=duration,
                    )
                    anim.bone_channels[bone_name][ch_name] = upsampled

    @staticmethod
    def _find_extrema_times(kfs: Keyframes) -> List[float]:
        """Find times of local extrema in keyframe data.

        For each axis, finds keyframes where the value is a local maximum
        or minimum. These are the most important keyframes to preserve.
        """
        if len(kfs) < 3:
            return []

        extrema = set()

        # Check each axis independently
        for axis in range(len(kfs[0][1])):
            for i in range(1, len(kfs) - 1):
                prev_v = kfs[i - 1][1][axis]
                curr_v = kfs[i][1][axis]
                next_v = kfs[i + 1][1][axis]

                # Local maximum or minimum
                if (curr_v > prev_v and curr_v > next_v) or \
                   (curr_v < prev_v and curr_v < next_v):
                    extrema.add(round(kfs[i][0], 4))

        return sorted(extrema)


# Type alias for the mirror function type hint
from typing import Any
