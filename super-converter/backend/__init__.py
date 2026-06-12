#!/usr/bin/env python3
"""
Super Architecture — Backend Package
======================================

The backend package exports the processed IR data (ModelIR + AnimationIR)
to the Blockbench .bbmodel format, which is a JSON file containing model
geometry, textures, and animations in a single document.

Key differences from the old BBModelGenerator:
  1. Consumes IR types directly (ModelIR, AnimationIR) instead of raw dicts.
  2. Coordinate transforms are centralized using coords.py functions.
  3. UV face swap uses coords.py instead of hardcoded inline logic.
  4. UUID generation uses math_utils.generate_uuid() (16 hex chars).
  5. Cleaner module structure — each concern is a separate method.

Usage:
    from backend import BBModelExporter
    exporter = BBModelExporter()
    bbmodel = exporter.export(model_ir, animations=[...], texture_path="model.png")
    exporter.save(bbmodel, "output.bbmodel")
"""

from .bbmodel_exporter import BBModelExporter

__all__ = [
    "BBModelExporter",
]
