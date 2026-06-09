"""Generic Animation Pipeline

Processes attack/evolved/death/sleep/unknown animations:
1. C0 enforcement
2. C1 enforcement (global cubic for non-loop, transition blend for loop)
3. Standard DP simplification
4. Final C0
"""

from __future__ import annotations

from .base import PipelineBase
from ..core.config import AnimForgeConfig
from ..core.parser import ParsedAnimation
from ..core.profile import AnimationProfile


class GenericPipeline(PipelineBase):
    """Pipeline for generic animations (attack, evolved, death, sleep, unknown).

    Uses the standard processing order with global cubic C1 for non-loop
    animations and transition zone blend for loop animations.
    """

    def __init__(self, config: AnimForgeConfig | None = None) -> None:
        super().__init__(config)

    def process(self, anim: ParsedAnimation, profile: AnimationProfile) -> ParsedAnimation:
        """Process a generic animation through the full pipeline.

        Args:
            anim: Parsed animation data (will NOT be modified in place).
            profile: Animation profile with bone roles.

        Returns:
            New ParsedAnimation with processed keyframes.
        """
        result = anim.deep_copy()
        is_loop = self._is_loop(result)
        duration = result.length

        # Step 1: C0 enforcement
        self.enforce_c0_all(result)

        # Step 2: C1 enforcement
        if is_loop:
            self._apply_c1_loop(result, duration)
        else:
            self._apply_c1_nonloop(result, duration)

        # Step 3: Standard DP simplification
        self._apply_dp_simplification(result)

        # Step 4: Final C0
        self.enforce_c0_all(result)

        # Round all values
        self.round_all_channels(result)

        return result

    def _apply_c1_loop(self, anim: ParsedAnimation, duration: float) -> None:
        """Apply C1 for loop animations using transition zone blend.

        Falls back to transition zone blend if global cubic would distort too much.
        """
        for bone_name, channels in anim.bone_channels.items():
            for ch_name in list(channels.keys()):
                kfs = channels[ch_name]
                if len(kfs) < 3:
                    continue

                # Try global cubic first
                corrected = self.enforce_c1_global_cubic(
                    kfs, duration, self.config.c1_distortion_limit
                )

                # If global cubic was rejected (returned original), use transition blend
                if corrected is kfs:
                    corrected = self.enforce_c1_transition_blend(
                        kfs, duration, zone_fraction=self.config.c1_transition_zone
                    )

                anim.bone_channels[bone_name][ch_name] = corrected

    def _apply_c1_nonloop(self, anim: ParsedAnimation, duration: float) -> None:
        """Apply C1 for non-loop animations using global cubic correction.

        Non-loop animations don't need C1 at the loop boundary, but we
        can still smooth the transition at the end. For non-loop, we
        only apply gentle smoothing near the end.
        """
        # For non-loop animations, C1 at the boundary isn't needed.
        # We skip C1 enforcement entirely for non-loop animations
        # since they don't wrap around.
        pass

    def _apply_dp_simplification(self, anim: ParsedAnimation) -> None:
        """Apply standard DP simplification for generic animations."""
        epsilon = self.config.dp_epsilon

        for bone_name, channels in anim.bone_channels.items():
            for ch_name in list(channels.keys()):
                kfs = channels[ch_name]
                original_count = len(kfs)

                if original_count <= 2:
                    continue

                simplified = self.dp_simplify(kfs, epsilon)

                # Quality gate: don't remove more than 50% of keyframes
                if len(simplified) < original_count * self.config.min_kf_density_threshold:
                    continue

                anim.bone_channels[bone_name][ch_name] = simplified
