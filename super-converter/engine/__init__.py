#!/usr/bin/env python3
"""
Super Architecture — Engine Package
=====================================

The engine package implements the animation processing pipeline that transforms
parsed AnimationIR data into clean, loop-aligned, rotation-normalized data
ready for serialization to .bbmodel format.

Pipeline stages (in order):
  1. Validate      — Clean and validate parsed data
  2. CarryForward  — Fill missing axes using interpolation-based fill
  3. PeriodAnalysis — Detect animation periods for seamless loops
  4. LoopAlign     — Ensure loop animations match at boundaries
  5. RotationNormalize — Quaternion-based rotation normalization (minimal)
  6. Interpolation — Select adaptive interpolation modes per segment
  7. SubFrameInsert — Insert intermediate keyframes for smooth playback

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
