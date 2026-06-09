"""Pipeline Router

Routes animations to the appropriate pipeline based on category:
Walk > Idle > Generic (fallback)
"""

from __future__ import annotations

from typing import Dict, Type

from .base import PipelineBase
from .walk import WalkPipeline
from .idle import IdlePipeline
from .generic import GenericPipeline
from ..core.config import AnimForgeConfig
from ..core.parser import ParsedAnimation
from ..core.profile import AnimationProfile, AnimCategory


class PipelineRouter:
    """Routes animations to the appropriate processing pipeline.

    Priority: Walk > Idle > Generic (fallback)

    The router uses the AnimationProfile's category to select the pipeline,
    but also considers the animation's characteristics for edge cases.
    """

    def __init__(self, config: AnimForgeConfig | None = None) -> None:
        self.config = config or AnimForgeConfig()
        self._pipelines: Dict[AnimCategory, PipelineBase] = {
            AnimCategory.WALK: WalkPipeline(self.config),
            AnimCategory.IDLE: IdlePipeline(self.config),
            AnimCategory.ATTACK: GenericPipeline(self.config),
            AnimCategory.DEATH: GenericPipeline(self.config),
            AnimCategory.SLEEP: GenericPipeline(self.config),
            AnimCategory.EVOLVED: GenericPipeline(self.config),
            AnimCategory.UNKNOWN: GenericPipeline(self.config),
        }

    def route(
        self, anim: ParsedAnimation, profile: AnimationProfile
    ) -> ParsedAnimation:
        """Route an animation to the appropriate pipeline and process it.

        Args:
            anim: Parsed animation to process.
            profile: Animation profile with category and bone roles.

        Returns:
            Processed ParsedAnimation.
        """
        category = profile.category
        pipeline = self._pipelines.get(category, self._pipelines[AnimCategory.UNKNOWN])
        return pipeline.process(anim, profile)

    def get_pipeline(self, category: AnimCategory) -> PipelineBase:
        """Get the pipeline instance for a given category."""
        return self._pipelines.get(category, self._pipelines[AnimCategory.UNKNOWN])
