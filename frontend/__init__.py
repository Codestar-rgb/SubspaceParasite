#!/usr/bin/env python3
"""
Super Architecture — Frontend Parser Package
==============================================

The frontend package parses GeckoLib geo.json and animation.json source
files into the unified IR types defined in core/types.py.

Key improvement over the old AnimEngineV2 parser:
  The old parser couldn't distinguish "value = 0.0" from "no data at this
  time point".  The new parser uses AxisValue(explicit=True/False) to make
  this distinction clear, enabling correct carry-forward in the transform
  stage.

Usage:
    from frontend import parse_geo_json, parse_animation_json

    # Parse a model
    model_ir = parse_geo_json(geo_data)

    # Parse animations
    anims = parse_animation_json(anim_data, model_name="kirin")
"""

from .geckolib_parser import parse_animation_json, parse_geo_json
from .axis_tracker import AxisPresence, merge_per_axis_data

__all__ = [
    "parse_geo_json",
    "parse_animation_json",
    "AxisPresence",
    "merge_per_axis_data",
]
