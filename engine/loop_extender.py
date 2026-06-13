#!/usr/bin/env python3
"""
Super Architecture — Loop Animation Handler (No-Op)
=====================================================

PRESERVES the original animation_length from GeckoLib source data.

PREVIOUS APPROACH (REMOVED):
  The previous implementation extended short loop animations to multiple
  cycles (3x–8x) to reduce CatmullRom loop boundary distortion frequency.
  
  This caused a critical speed mismatch: the original GeckoLib
  animation_length (e.g., 0.6667s for walk) is the TRUE loop cycle
  duration. Extending it to 5.3336s (8x) made animations play 8x slower
  in Blockbench, since Blockbench plays the full animation length before
  looping back to t=0.

WHY NO EXTENSION IS NEEDED:
  The CatmullRom baking step (catmullrom_baker.py) converts all CatmullRom
  curves to dense linear keyframes at 50fps. Linear interpolation has NO
  tangent/control point dependencies, so there is no CatmullRom boundary
  distortion. Combined with the source data guaranteeing first-frame ==
  last-frame values for loop animations, seamless looping is achieved
  without any multi-cycle extension.

ANIMATION SPEED:
  GeckoLib uses animation_length as the loop cycle period. The Java entity
  code does NOT apply a separate speed multiplier for these animations.
  Therefore, preserving the original animation_length gives the correct
  playback speed in Blockbench.

  Example:
    Source: animation.ferbear.walk animation_length=0.6667s
    Output: bbmodel animation length=0.6667s (one walk cycle per 0.67s)
    Previous (wrong): length=5.3336s (8x slower!)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.types import (
    AnimationIR,
    BoneAnimationIR,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Apply to all animations — no-op pass-through
# ---------------------------------------------------------------------------

def extend_loop_animations(
    animations: List[AnimationIR],
    model_name: str = "",
) -> List[AnimationIR]:
    """Pass through animations without extension.

    The original animation_length is preserved from the GeckoLib source.
    CatmullRom baking handles loop boundary distortion.
    First/last frame value consistency is guaranteed by source data.

    Args:
        animations: List of AnimationIR instances.
        model_name: Model name for logging.

    Returns:
        The same list of AnimationIR (unchanged).
    """
    # No-op: return animations as-is
    # The original animation_length from GeckoLib source is the correct
    # loop cycle duration and should be preserved exactly.
    logger.debug(
        "[%s] LoopExtender: no-op (preserving original animation lengths)",
        model_name,
    )
    return animations


def extend_animation(anim: AnimationIR) -> AnimationIR:
    """Pass through a single animation without extension.

    Args:
        anim: The AnimationIR to process.

    Returns:
        The same AnimationIR (unchanged).
    """
    return anim
