#!/usr/bin/env python3
"""
AST Symbol Compiler — Engine Package
=======================================

The engine package implements the animation processing pipeline that transforms
parsed AnimationIR data into clean, loop-aligned, rotation-normalized data
ready for serialization to .bbmodel format.

NEW Pipeline (AST Symbol Compiler architecture):
  1. Validate       — Clean and validate parsed data
  2. SymbolCompile  — Build symbol table with per-segment AST expressions
  3. PeriodLock     — LCM-based period detection for seamless loops
  4. SymbolEvaluate — Evaluate AST at merged time points → KeyframeData
  5. LoopAlign      — Ensure loop animations match at boundaries
  6. RotationNormalize — Quaternion-based rotation normalization (minimal)

KEY IMPROVEMENTS over the old pipeline:
  - No separate carry-forward step (evaluation fills values on demand)
  - Interpolation selected BEFORE evaluation (fixes chicken-and-egg problem)
  - CatmullRom overshoot clamping built into AST expressions
  - LCM-based period locking for consistent looping across all bones

Usage:
    from engine import AnimationPipeline, PipelineResult
    pipeline = AnimationPipeline()
    result = pipeline.process(animations, model_name="kirin")
    processed = result.animations
"""

from .pipeline import AnimationPipeline, PipelineResult

__all__ = [
    "AnimationPipeline",
    "PipelineResult",
]
