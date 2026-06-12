#!/usr/bin/env python3
"""
AnimEngineV2 — Shared Utility Functions
========================================
Pure helper functions used across the pipeline stages.
No side effects, no I/O — easy to unit test.
"""

from __future__ import annotations

import math
import uuid
from typing import Optional

from .types import ROTATION_MAX, ROTATION_MIN, UUID_LENGTH


def generate_uuid() -> str:
    """Generate a UUID string for bbmodel objects.

    Uses 16 hex characters (64 bits) to reduce collision risk compared
    to the previous 8-character UUIDs. With 168 models × ~100 elements
    each = ~17K objects, 8 hex chars (4 billion space) has a ~0.03%
    birthday-paradox collision probability; 16 hex chars (1.8e19 space)
    reduces this to negligible.
    """
    return uuid.uuid4().hex[:UUID_LENGTH]


def normalize_rotation(value: float) -> float:
    """Normalize a rotation value to [-360, 360] range.

    Values like 720° and 0° produce the same visual rotation but
    different interpolation results. Normalizing ensures consistent
    spline behavior at loop boundaries.

    Examples:
        >>> normalize_rotation(720.0)
        0.0
        >>> normalize_rotation(-450.0)
        -90.0
        >>> normalize_rotation(45.0)
        45.0
    """
    if value == 0.0:
        return 0.0

    # Use modular arithmetic: value mod 720, shifted to [-360, 360]
    result = value % 720.0
    if result > 360.0:
        result -= 720.0
    elif result < -360.0:
        result += 720.0

    # Clamp to exact range
    result = max(ROTATION_MIN, min(ROTATION_MAX, result))

    # Snap near-zero values to zero
    if abs(result) < 1e-10:
        return 0.0

    return result


def is_valid_number(value: float) -> bool:
    """Check if a value is a valid finite number (not NaN or Infinity).

    Args:
        value: The number to check.

    Returns:
        True if the value is finite and not NaN.
    """
    return math.isfinite(value)


def values_match(a: float, b: float, tolerance: float = 1e-6) -> bool:
    """Check if two float values are approximately equal.

    Args:
        a: First value.
        b: Second value.
        tolerance: Maximum allowed difference.

    Returns:
        True if |a - b| <= tolerance.
    """
    return abs(a - b) <= tolerance


def round_for_bbmodel(value: float) -> float:
    """Round a float value for bbmodel output.

    Rounds to 6 decimal places to avoid floating point noise
    while preserving sufficient precision for smooth animations.

    Args:
        value: The float to round.

    Returns:
        Rounded float.
    """
    return round(value, 6)


def select_interpolation(channel: str, easing: str) -> str:
    """Select the interpolation mode for a keyframe.

    Rules:
        - If easing is non-linear, use catmullrom (Blockbench needs it for easing).
        - Rotation channel defaults to catmullrom (smooth curves match cos/sin sources).
        - Position and scale default to linear (crisp, predictable movements).

    Args:
        channel: "rotation", "position", or "scale".
        easing: The easing function name.

    Returns:
        "catmullrom" or "linear".
    """
    from .types import DEFAULT_INTERPOLATION, VALID_EASINGS

    # Non-linear easing always requires catmullrom
    if easing != "linear":
        return "catmullrom"

    # Channel-specific defaults
    return DEFAULT_INTERPOLATION.get(channel, "linear")


def parse_geckolib_value(value) -> tuple:
    """Parse a GeckoLib value into (float_value, easing_name).

    GeckoLib values can be:
        - A plain number: 0.0  →  (0.0, "linear")
        - A string (Molang): "query.anim_time * 5"  →  raises ValueError
        - A dict: {"vector": 1.0, "easing": "easeOutSine"}  →  (1.0, "easeOutSine")

    Args:
        value: The raw GeckoLib value.

    Returns:
        Tuple of (float_value, easing_name).

    Raises:
        ValueError: If the value is a Molang string (caller should handle separately).
        TypeError: If the value type is unrecognized.
    """
    if isinstance(value, (int, float)):
        return (float(value), "linear")

    if isinstance(value, str):
        # Molang expression — caller should handle
        raise ValueError(f"Molang expression: {value}")

    if isinstance(value, dict):
        vec = float(value.get("vector", 0.0))
        easing = value.get("easing", "linear")
        return (vec, easing)

    raise TypeError(f"Unrecognized GeckoLib value type: {type(value).__name__}")
