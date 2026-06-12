#!/usr/bin/env python3
"""
AnimEngineV2 — Animation Conversion Engine
============================================
Pipeline-based animation converter for GeckoLib → bbmodel format.

Architecture:
    Parse → Validate → Transform → Serialize

Usage:
    from anim_engine import AnimEngineV2

    engine = AnimEngineV2()
    result = engine.convert(anim_json, model_name="kirin")

    # result.animations  — list of bbmodel-format animation dicts
    # result.warnings    — list of warning strings
    # result.stats       — dict with conversion statistics

Integration with BBModelGenerator:
    from anim_engine import AnimEngineV2

    engine = AnimEngineV2()
    result = engine.convert(anim_json, model_name=short_name)
    bbmodel["animations"] = result.animations
"""

from .engine import AnimEngineV2
from .types import (
    AnimKeyframe,
    AnimationData,
    BoneAnimation,
    ConversionResult,
)

__all__ = [
    "AnimEngineV2",
    "AnimKeyframe",
    "AnimationData",
    "BoneAnimation",
    "ConversionResult",
]
