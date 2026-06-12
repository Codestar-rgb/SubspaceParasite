#!/usr/bin/env python3
"""
AnimEngineV2 — Main Engine Orchestrator
=========================================
Orchestrates the full Parse → Validate → Transform → Serialize pipeline.

Usage:
    from anim_engine import AnimEngineV2

    engine = AnimEngineV2()
    result = engine.convert(anim_json, model_name="kirin")

    # result.animations  — list of bbmodel-format animation dicts
    # result.warnings    — list of warning strings
    # result.stats       — dict with conversion statistics

The engine can be used standalone or integrated into BBModelGenerator.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .types import AnimationData, ConversionResult
from .parser import parse_animations
from .validator import validate_animations
from .transform import transform_animations
from .serializer import serialize_animations

logger = logging.getLogger(__name__)


class AnimEngineV2:
    """Animation conversion engine with pipeline architecture.

    Pipeline: Parse → Validate → Transform → Serialize

    Each stage:
        - Receives data from the previous stage
        - Produces new data (never mutates input)
        - Validates its input and output
        - Logs issues at appropriate granularity
        - Can fail gracefully (bad bones/animations are skipped, not fatal)

    Usage:
        engine = AnimEngineV2()
        result = engine.convert(anim_json, model_name="kirin")
        bbmodel_animations = result.animations

    Integration with BBModelGenerator:
        engine = AnimEngineV2()
        result = engine.convert(anim_json, model_name=short_name)
        bbmodel["animations"] = result.animations
    """

    def __init__(self, log_level: int = logging.WARNING) -> None:
        """Initialize the engine.

        Args:
            log_level: Logging level for the engine's logger.
                       Set to logging.DEBUG for detailed diagnostics.
        """
        self._log_level = log_level
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._logger.setLevel(log_level)

    def convert(
        self,
        anim_json: dict,
        model_name: str = "",
        is_loop_default: bool = True,
    ) -> ConversionResult:
        """Convert a GeckoLib animation.json to bbmodel animation format.

        Args:
            anim_json: The raw animation.json dict with "animations" key.
                       Expected format:
                       {
                         "format_version": "1.8.0",
                         "animations": {
                           "animation.model.idle": {
                             "loop": "loop",
                             "animation_length": 6.2832,
                             "bones": { ... }
                           }
                         }
                       }
            model_name: Model name for logging context.
            is_loop_default: If True, animations without an explicit loop
                             mode default to "loop" instead of "once".
                             Most SRParasites animations are looping.

        Returns:
            ConversionResult with:
                - animations: List of bbmodel-format animation dicts
                - warnings: List of warning strings
                - stats: Dict with detailed conversion statistics
        """
        all_warnings: List[str] = []
        all_stats: dict = {
            "model_name": model_name,
            "pipeline_stages": {},
        }

        # If no animation data, return empty result
        if not anim_json or not anim_json.get("animations"):
            return ConversionResult(
                animations=[],
                warnings=[],
                stats={"model_name": model_name, "total_animations": 0},
            )

        # Apply default loop mode if needed
        if is_loop_default:
            anim_json = _apply_default_loop(anim_json)

        # ---- Stage 1: Parse ----
        try:
            parsed = parse_animations(anim_json, model_name)
            all_stats["pipeline_stages"]["parse"] = {
                "animations_parsed": len(parsed),
                "total_bones": sum(len(a.bones) for a in parsed.values()),
                "total_keyframes": sum(
                    len(b.keyframes)
                    for a in parsed.values()
                    for b in a.bones.values()
                ),
            }
        except Exception as e:
            all_warnings.append(f"[{model_name}] Parse stage failed: {e}")
            return ConversionResult(animations=[], warnings=all_warnings, stats=all_stats)

        # ---- Stage 2: Validate ----
        try:
            validation = validate_animations(parsed, model_name)
            all_warnings.extend(validation.warnings)
            all_stats["pipeline_stages"]["validate"] = validation.stats
        except Exception as e:
            all_warnings.append(f"[{model_name}] Validation stage failed: {e}")
            # Use parsed data as fallback
            validation = None
            validated_animations = parsed
        else:
            validated_animations = validation.animations

        # ---- Stage 3: Transform ----
        try:
            transformation = transform_animations(validated_animations, model_name)
            all_warnings.extend(transformation.warnings)
            all_stats["pipeline_stages"]["transform"] = transformation.stats
        except Exception as e:
            all_warnings.append(f"[{model_name}] Transform stage failed: {e}")
            transformation = None
            transformed_animations = validated_animations
        else:
            transformed_animations = transformation.animations

        # ---- Stage 4: Serialize ----
        try:
            serialization = serialize_animations(transformed_animations, model_name)
            all_warnings.extend(serialization.warnings)
            all_stats["pipeline_stages"]["serialize"] = serialization.stats
        except Exception as e:
            all_warnings.append(f"[{model_name}] Serialize stage failed: {e}")
            return ConversionResult(animations=[], warnings=all_warnings, stats=all_stats)

        # Compute summary stats
        all_stats["total_animations"] = len(serialization.animations)
        all_stats["total_keyframes"] = serialization.stats["total_keyframes"]
        all_stats["total_bones"] = serialization.stats["total_bones"]
        all_stats["molang_keyframes"] = serialization.stats["molang_keyframes"]

        # Log warnings count
        if all_warnings:
            self._logger.info(
                "[%s] Conversion completed with %d warnings",
                model_name, len(all_warnings),
            )
        else:
            self._logger.debug("[%s] Conversion completed, no warnings", model_name)

        return ConversionResult(
            animations=serialization.animations,
            warnings=all_warnings,
            stats=all_stats,
        )


def _apply_default_loop(anim_json: dict) -> dict:
    """Apply default loop mode to animations that don't specify one.

    Many GeckoLib animations don't specify a loop mode but are intended
    to loop. This function ensures they default to "loop" instead of "once".

    This creates a shallow copy of the animations dict to avoid mutating
    the input.

    Args:
        anim_json: Raw animation.json dict.

    Returns:
        New dict with default loop modes applied.
    """
    import copy
    result = copy.copy(anim_json)
    animations = result.get("animations", {})

    new_animations = {}
    for anim_name, anim_data in animations.items():
        new_data = copy.copy(anim_data)
        if "loop" not in new_data:
            new_data["loop"] = "loop"
        new_animations[anim_name] = new_data

    result["animations"] = new_animations
    return result
