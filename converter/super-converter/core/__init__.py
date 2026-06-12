#!/usr/bin/env python3
"""
Super Architecture — Core Package
===================================

The core package provides the unified IR types, quaternion math engine,
coordinate system transformations, and math utilities for the
MC 1.12.2 -> GeckoLib 1.20.1 / Blockbench .bbmodel converter.

Module overview:
  - types:       Unified IR data types (AxisValue, KeyframeData, AnimationIR, etc.)
  - quaternion:  Quaternion class with slerp, Euler conversion, M_model transform
  - coords:      Coordinate system transformations (position, rotation, cube, UV)
  - math_utils:  General math utilities (normalize, round, UUID, period detection)

Usage:
    from core import AnimationIR, KeyframeData, AxisValue
    from core import Quaternion, convert_rotation_quaternion
    from core import convert_position, convert_rotation, convert_cube_origin
    from core import normalize_rotation, generate_uuid, compute_animation_period
"""

# ---------------------------------------------------------------------------
# IR types
# ---------------------------------------------------------------------------
from .types import (
    AXES,
    CHANNELS,
    DEFAULT_INTERPOLATION,
    ROTATION_MAX,
    ROTATION_MIN,
    UUID_LENGTH,
    VALID_LOOP_MODES,
    AnimationIR,
    AxisValue,
    BoneAnimationIR,
    ConversionResult,
    CubeIR,
    KeyframeData,
    BoneIR,
    ModelIR,
)

# ---------------------------------------------------------------------------
# Quaternion math
# ---------------------------------------------------------------------------
from .quaternion import (
    Quaternion,
    convert_rotation_quaternion,
    euler_shortest_path,
    quaternion_conjugate_rotate,
)

# ---------------------------------------------------------------------------
# Coordinate transformations
# ---------------------------------------------------------------------------
from .coords import (
    convert_cube_origin,
    convert_cube_size,
    convert_position,
    convert_rotation,
    convert_uv_face_mirror,
    convert_uv_face_north_south,
    convert_uv_for_cube,
)

# ---------------------------------------------------------------------------
# Math utilities
# ---------------------------------------------------------------------------
from .math_utils import (
    compute_animation_period,
    deg_to_rad,
    generate_uuid,
    is_valid_number,
    lcm,
    normalize_rotation,
    rad_to_deg,
    round_for_bbmodel,
    values_match,
)

__all__ = [
    # Types
    "AXES",
    "CHANNELS",
    "DEFAULT_INTERPOLATION",
    "ROTATION_MAX",
    "ROTATION_MIN",
    "UUID_LENGTH",
    "VALID_LOOP_MODES",
    "AnimationIR",
    "AxisValue",
    "BoneAnimationIR",
    "ConversionResult",
    "CubeIR",
    "KeyframeData",
    "BoneIR",
    "ModelIR",
    # Quaternion
    "Quaternion",
    "convert_rotation_quaternion",
    "euler_shortest_path",
    "quaternion_conjugate_rotate",
    # Coords
    "convert_cube_origin",
    "convert_cube_size",
    "convert_position",
    "convert_rotation",
    "convert_uv_face_mirror",
    "convert_uv_face_north_south",
    "convert_uv_for_cube",
    # Math utils
    "compute_animation_period",
    "deg_to_rad",
    "generate_uuid",
    "is_valid_number",
    "lcm",
    "normalize_rotation",
    "rad_to_deg",
    "round_for_bbmodel",
    "values_match",
]
