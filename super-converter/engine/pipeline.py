#!/usr/bin/env python3
"""
Super Architecture — Animation Processing Pipeline
====================================================

The main pipeline orchestrator.  Replaces the old AnimEngineV2 with a
cleaner, more correct architecture.

Pipeline: Parse → Validate → CarryForward → PeriodAnalysis →
          LoopAlign → RotationNormalize → Interpolation → Ready

Each stage:
  - Receives data from the previous stage
  - Produces new data (never mutates input)
  - Validates its input and output
  - Logs issues at appropriate granularity
  - Can fail gracefully (bad data skipped, not fatal)

Usage:
    pipeline = AnimationPipeline()
    result = pipeline.process(animations, model_name="kirin")
    processed_animations = result.animations
"""

from __future__ import annotations

import logging
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.types import AnimationIR, BoneAnimationIR

from .validator import validate_animations, ValidationResult
from .carry_forward import apply_carry_forward_all
from .period_analyzer import analyze_periods
from .loop_aligner import align_loops
from .rotation_normalizer import normalize_rotations
from .interpolation import select_interpolation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline result types
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    """Result of running the full animation processing pipeline.

    Attributes:
        animations: Processed animations, ready for serialization.
        warnings: List of warning messages from all pipeline stages.
        stats: Dict with statistics from each pipeline stage.
        elapsed_seconds: Total pipeline execution time.
    """

    animations: Dict[str, AnimationIR] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    elapsed_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Pipeline implementation
# ---------------------------------------------------------------------------

class AnimationPipeline:
    """Super Architecture animation processing pipeline.

    Pipeline: Parse → Validate → CarryForward → PeriodAnalysis →
              LoopAlign → RotationNormalize → Interpolation → Ready

    Each stage:
    - Receives data from the previous stage
    - Produces new data (never mutates input)
    - Validates its input and output
    - Logs issues at appropriate granularity
    - Can fail gracefully (bad data skipped, not fatal)

    Usage:
        pipeline = AnimationPipeline()
        result = pipeline.process(animations, model_name="kirin")
        processed_animations = result.animations
    """

    def __init__(self) -> None:
        """Initialize the pipeline with default settings."""
        self._stage_timings: Dict[str, float] = {}

    def process(
        self,
        animations: Dict[str, AnimationIR],
        model_name: str = "",
    ) -> PipelineResult:
        """Run the full pipeline on parsed AnimationIR data.

        Pipeline stages (in order):
          1. Validate      — Clean and validate parsed data
          2. CarryForward  — Fill missing axes using explicit carry-forward
          3. PeriodAnalysis — Detect animation periods for seamless loops
          4. LoopAlign     — Ensure loop animations match at boundaries
          5. RotationNormalize — Quaternion-based rotation normalization
          6. Interpolation — Select adaptive interpolation modes

        Args:
            animations: Dict mapping animation_name -> AnimationIR, as
                        produced by the frontend parser.
            model_name: Optional model name for logging context.

        Returns:
            PipelineResult with processed animations, warnings, and stats.
        """
        start_time = _time.monotonic()
        all_warnings: List[str] = []
        stats: Dict[str, Any] = {}

        if not animations:
            elapsed = _time.monotonic() - start_time
            stats["total_animations"] = 0
            stats["total_keyframes"] = 0
            return PipelineResult(
                animations={},
                warnings=[],
                stats=stats,
                elapsed_seconds=elapsed,
            )

        # Log pipeline start
        logger.info(
            "[%s] Pipeline starting: %d animations",
            model_name, len(animations),
        )

        # ------------------------------------------------------------------
        # Stage 1: Validate
        # ------------------------------------------------------------------
        t0 = _time.monotonic()
        validation_result = validate_animations(animations, model_name)
        validated = validation_result.animations
        all_warnings.extend(validation_result.warnings)
        stats["validation"] = validation_result.stats
        stats["validation"]["removed_animations"] = len(animations) - len(validated)
        self._stage_timings["validate"] = _time.monotonic() - t0

        logger.info(
            "[%s] Validate: %d → %d animations, %d warnings",
            model_name, len(animations), len(validated),
            len(validation_result.warnings),
        )

        # ------------------------------------------------------------------
        # Stage 2: Carry-Forward
        # ------------------------------------------------------------------
        t0 = _time.monotonic()
        carry_stats: Dict[str, Any] = {}
        carried = apply_carry_forward_all(validated, model_name, carry_stats)
        stats["carry_forward"] = carry_stats
        self._stage_timings["carry_forward"] = _time.monotonic() - t0

        logger.info(
            "[%s] CarryForward: %d axes filled",
            model_name, carry_stats.get("axes_filled", 0),
        )

        # ------------------------------------------------------------------
        # Stage 3: Period Analysis
        # ------------------------------------------------------------------
        t0 = _time.monotonic()
        period_analyzed = analyze_periods(carried, model_name)
        self._stage_timings["period_analysis"] = _time.monotonic() - t0

        period_count = sum(
            1 for a in period_analyzed.values() if a.period is not None
        )
        stats["period_analysis"] = {
            "animations_with_period": period_count,
            "total_animations": len(period_analyzed),
        }

        logger.info(
            "[%s] PeriodAnalysis: %d/%d animations have detected periods",
            model_name, period_count, len(period_analyzed),
        )

        # ------------------------------------------------------------------
        # Stage 4: Loop Alignment
        # ------------------------------------------------------------------
        t0 = _time.monotonic()
        loop_stats: Dict[str, Any] = {}
        aligned = align_loops(period_analyzed, model_name, loop_stats)
        stats["loop_align"] = loop_stats
        self._stage_timings["loop_align"] = _time.monotonic() - t0

        logger.info(
            "[%s] LoopAlign: %d alignments, %d synthetic end keyframes",
            model_name,
            loop_stats.get("alignments", 0),
            loop_stats.get("synthetic_end_keyframes", 0),
        )

        # ------------------------------------------------------------------
        # Stage 5: Rotation Normalization
        # ------------------------------------------------------------------
        t0 = _time.monotonic()
        rot_stats: Dict[str, Any] = {}
        normalized = normalize_rotations(aligned, model_name, rot_stats)
        stats["rotation_normalize"] = rot_stats
        self._stage_timings["rotation_normalize"] = _time.monotonic() - t0

        logger.info(
            "[%s] RotationNormalize: %d shortest-path fixes, %d rotations normalized",
            model_name,
            rot_stats.get("shortest_path_fixes", 0),
            rot_stats.get("rotations_normalized", 0),
        )

        # ------------------------------------------------------------------
        # Stage 6: Interpolation Selection
        # ------------------------------------------------------------------
        t0 = _time.monotonic()
        interp_stats: Dict[str, Any] = {}
        final = select_interpolation(normalized, model_name, interp_stats)
        stats["interpolation"] = interp_stats
        self._stage_timings["interpolation"] = _time.monotonic() - t0

        logger.info(
            "[%s] Interpolation: %d catmullrom, %d linear, %d snap-heavy overrides",
            model_name,
            interp_stats.get("catmullrom_count", 0),
            interp_stats.get("linear_count", 0),
            interp_stats.get("snap_heavy_overrides", 0),
        )

        # ------------------------------------------------------------------
        # Compute summary stats
        # ------------------------------------------------------------------
        total_keyframes = 0
        total_bones = 0
        for anim in final.values():
            total_bones += len(anim.bones)
            for bone_anim in anim.bones.values():
                total_keyframes += len(bone_anim.keyframes)

        stats["total_animations"] = len(final)
        stats["total_keyframes"] = total_keyframes
        stats["total_bones"] = total_bones
        stats["stage_timings"] = self._stage_timings
        stats["total_warnings"] = len(all_warnings)

        elapsed = _time.monotonic() - start_time

        logger.info(
            "[%s] Pipeline complete: %d animations, %d keyframes, "
            "%d warnings, %.3fs elapsed",
            model_name, len(final), total_keyframes,
            len(all_warnings), elapsed,
        )

        return PipelineResult(
            animations=final,
            warnings=all_warnings,
            stats=stats,
            elapsed_seconds=elapsed,
        )
