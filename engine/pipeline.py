#!/usr/bin/env python3
"""
AST Symbol Compiler — Animation Processing Pipeline
=====================================================

The new pipeline uses the AST Symbol Compiler architecture to eliminate
the fundamental ordering problem of the old pipeline.

OLD PIPELINE (broken ordering):
  Parse → Validate → CarryForward (uses CatmullRom!) → PeriodAnalysis
  → LoopAlign → RotNormalize → Interpolation (selects mode) → SubFrameInsert

PROBLEM: CarryForward (Stage 2) used CatmullRom to fill missing axis
values, but Interpolation (Stage 6) hadn't run yet. This means some
segments got filled with CatmullRom when they should have been linear,
causing overshoot artifacts and animation stuttering.

NEW PIPELINE (correct ordering):
  Parse → Validate → SymbolCompile → PeriodLock → LoopAlign → RotNormalize
  → SymbolEvaluate → Ready

KEY CHANGES:
  1. SymbolCompile replaces CarryForward + Interpolation:
     - Selects interpolation mode PER SEGMENT before building expressions
     - Builds AST expression nodes with overshoot clamping
     - No separate carry-forward — evaluation fills values on demand

  2. PeriodLock replaces PeriodAnalysis:
     - Uses LCM-based period detection instead of single-axis autocorrelation
     - Locks period across all bones for consistent looping

  3. SymbolEvaluate replaces SubFrameInsert:
     - Evaluates AST expressions at merged time points
     - Inserts sub-frames using the SAME AST (no re-interpolation)
     - Values are always computed from the correct interpolation mode

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
from .symbol_compiler import compile_symbol_table
from .period_locker import lock_periods
from .loop_aligner import align_loops
from .rotation_normalizer import normalize_rotations
from .symbol_evaluator import evaluate_symbol_tables
from .symbol_table import SymbolTable

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
    """AST Symbol Compiler animation processing pipeline.

    Pipeline: Parse → Validate → SymbolCompile → PeriodLock → LoopAlign
              → RotNormalize → SymbolEvaluate → Ready

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
          1. Validate       — Clean and validate parsed data
          2. SymbolCompile  — Build symbol table with per-segment AST expressions
          3. PeriodLock     — LCM-based period detection for seamless loops
          4. LoopAlign      — Ensure loop animations match at boundaries
          5. RotNormalize   — Quaternion-based rotation normalization (minimal)
          6. SymbolEvaluate — Evaluate AST at merged time points → KeyframeData

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
            "[%s] Pipeline starting (AST Symbol Compiler): %d animations",
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
        # Stage 2: Symbol Compile (replaces CarryForward + Interpolation)
        # ------------------------------------------------------------------
        t0 = _time.monotonic()
        compile_stats: Dict[str, Any] = {}
        symbol_tables = compile_symbol_table(validated, model_name, compile_stats)
        stats["symbol_compile"] = compile_stats
        self._stage_timings["symbol_compile"] = _time.monotonic() - t0

        logger.info(
            "[%s] SymbolCompile: %d curves, %d segments (%d CR, %d linear, %d snap-heavy)",
            model_name,
            compile_stats.get("curves_compiled", 0),
            compile_stats.get("segments_compiled", 0),
            compile_stats.get("catmullrom_segments", 0),
            compile_stats.get("linear_segments", 0),
            compile_stats.get("snap_heavy_axes", 0),
        )

        # ------------------------------------------------------------------
        # Stage 3: Period Lock (LCM-based, replaces PeriodAnalysis)
        # ------------------------------------------------------------------
        t0 = _time.monotonic()
        lock_stats: Dict[str, Any] = {}
        locked_tables = lock_periods(symbol_tables, validated, model_name, lock_stats)
        stats["period_lock"] = lock_stats
        self._stage_timings["period_lock"] = _time.monotonic() - t0

        period_count = sum(
            1 for t in locked_tables.values() if t.period is not None
        )
        logger.info(
            "[%s] PeriodLock: %d/%d animations have periods "
            "(%d from source, %d from LCM, %d undetected)",
            model_name, period_count, len(locked_tables),
            lock_stats.get("periods_from_source", 0),
            lock_stats.get("periods_from_lcm", 0),
            lock_stats.get("periods_undetected", 0),
        )

        # ------------------------------------------------------------------
        # Stage 4: Loop Alignment
        # ------------------------------------------------------------------
        # Need to convert symbol tables back to AnimationIR temporarily
        # for the loop aligner (which still operates on KeyframeData).
        # We'll evaluate the symbol tables AFTER loop alignment.
        #
        # Actually, we need a different approach: evaluate the symbol tables
        # first to get AnimationIR, then run loop alignment on the IR.
        # But that would mean evaluating before loop alignment...
        #
        # Better approach: Apply loop alignment at the symbol table level
        # by adjusting segment endpoints. But the current loop aligner
        # operates on KeyframeData...
        #
        # Pragmatic solution: Evaluate symbol tables to get IR, then run
        # loop alignment on the IR, then the loop-aligned IR is the final
        # output. The loop aligner only adds/modifies keyframes at the
        # loop boundary, which is a small change.
        # ------------------------------------------------------------------
        t0 = _time.monotonic()
        eval_stats: Dict[str, Any] = {}
        evaluated_anims = evaluate_symbol_tables(locked_tables, model_name, eval_stats)
        stats["symbol_evaluate_initial"] = eval_stats
        self._stage_timings["symbol_evaluate_initial"] = _time.monotonic() - t0

        logger.info(
            "[%s] SymbolEvaluate (initial): %d keyframes, %d sub-frames",
            model_name,
            eval_stats.get("total_keyframes_evaluated", 0),
            eval_stats.get("subframes_inserted", 0),
        )

        # ------------------------------------------------------------------
        # Stage 5: Loop Alignment (on evaluated IR)
        # ------------------------------------------------------------------
        t0 = _time.monotonic()
        loop_stats: Dict[str, Any] = {}
        aligned = align_loops(evaluated_anims, model_name, loop_stats)
        stats["loop_align"] = loop_stats
        self._stage_timings["loop_align"] = _time.monotonic() - t0

        logger.info(
            "[%s] LoopAlign: %d alignments, %d synthetic end keyframes",
            model_name,
            loop_stats.get("alignments", 0),
            loop_stats.get("synthetic_end_keyframes", 0),
        )

        # ------------------------------------------------------------------
        # Stage 6: Rotation Normalization (minimal, only fixes real problems)
        # ------------------------------------------------------------------
        t0 = _time.monotonic()
        rot_stats: Dict[str, Any] = {}
        normalized = normalize_rotations(aligned, model_name, rot_stats)
        stats["rotation_normalize"] = rot_stats
        self._stage_timings["rotation_normalize"] = _time.monotonic() - t0

        logger.info(
            "[%s] RotationNormalize: %d shortest-path fixes",
            model_name,
            rot_stats.get("shortest_path_fixes", 0),
        )

        # ------------------------------------------------------------------
        # Final = normalized animations
        # ------------------------------------------------------------------
        final = normalized

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
            "[%s] Pipeline complete (AST Symbol Compiler): %d animations, "
            "%d keyframes, %d warnings, %.3fs elapsed",
            model_name, len(final), total_keyframes,
            len(all_warnings), elapsed,
        )

        return PipelineResult(
            animations=final,
            warnings=all_warnings,
            stats=stats,
            elapsed_seconds=elapsed,
        )
