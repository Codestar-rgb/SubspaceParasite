"""Idle Animation Pipeline

Processes idle/ambient animations with gentle handling:
1. C0 enforcement
2. Gentle C1 (transition zone blend, wider zone 30%)
3. Conservative DP simplification
4. Final C0
"""

from __future__ import annotations

from .base import PipelineBase
from ..core.config import AnimForgeConfig
from ..core.parser import ParsedAnimation
from ..core.profile import AnimationProfile


class IdlePipeline(PipelineBase):
    """Pipeline for idle/ambient animations with gentle processing.

    Idle animations typically have subtle motion and don't need aggressive
    simplification. A wider transition zone (30%) is used for C1 to ensure
    smooth looping without disturbing the subtle idle motion.
    """

    def __init__(self, config: AnimForgeConfig | None = None) -> None:
        super().__init__(config)

    def process(self, anim: ParsedAnimation, profile: AnimationProfile) -> ParsedAnimation:
        """Process an idle animation through the full pipeline.

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

        # Step 2: Gentle C1 with wider transition zone (30%)
        if is_loop:
            self._apply_c1_idle(result, duration)

        # Step 3: Conservative DP simplification
        self._apply_dp_simplification_idle(result)

        # Step 4: Final C0
        self.enforce_c0_all(result)

        # Round all values
        self.round_all_channels(result)

        return result

    def _apply_c1_idle(self, anim: ParsedAnimation, duration: float) -> None:
        """Apply C1 with wider transition zone for idle animations."""
        zone_fraction = self.config.c1_transition_zone * 2.0  # 30% (2x the base 15%)

        for bone_name, channels in anim.bone_channels.items():
            for ch_name in list(channels.keys()):
                kfs = channels[ch_name]
                if len(kfs) < 3:
                    continue

                corrected = self.enforce_c1_transition_blend(
                    kfs, duration, zone_fraction=zone_fraction
                )
                anim.bone_channels[bone_name][ch_name] = corrected

    def _apply_dp_simplification_idle(self, anim: ParsedAnimation) -> None:
        """Apply conservative DP simplification for idle animations.

        Uses the standard epsilon but with a looser quality gate (60% density).
        """
        epsilon = self.config.dp_epsilon

        for bone_name, channels in anim.bone_channels.items():
            for ch_name in list(channels.keys()):
                kfs = channels[ch_name]
                original_count = len(kfs)

                if original_count <= 3:
                    continue  # Don't simplify very short idle channels

                simplified = self.dp_simplify(kfs, epsilon)

                # Quality gate: don't remove more than 40% of keyframes
                if len(simplified) < original_count * 0.6:
                    continue

                anim.bone_channels[bone_name][ch_name] = simplified
