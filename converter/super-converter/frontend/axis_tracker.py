#!/usr/bin/env python3
"""
Super Architecture — Axis Tracking Helper
===========================================

Helper module for tracking which axes are explicitly present at each time
point during GeckoLib animation parsing.

This is the KEY improvement over the old AnimEngineV2 parser: we can now
distinguish "the source data has x=0.0 at t=1.0" from "the source data
has no x value at t=1.0".  The old parser would set both to 0.0, causing
the transform stage's carry-forward to incorrectly hold x at its previous
value when it should be 0.0.

Usage:
    from frontend.axis_tracker import AxisPresence, merge_per_axis_data
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GeckoLib value parsing
# ---------------------------------------------------------------------------

def parse_geckolib_value(value) -> Tuple[float, str]:
    """Parse a single GeckoLib value into (float_value, easing_name).

    GeckoLib values can be:
        - A plain number: 0.0  ->  (0.0, "linear")
        - A string (Molang): "query.anim_time * 5"  ->  raises ValueError
        - A dict: {"vector": 1.0, "easing": "easeOutSine"}  ->  (1.0, "easeOutSine")

    Args:
        value: The raw GeckoLib value.

    Returns:
        Tuple of (float_value, easing_name).

    Raises:
        ValueError: If the value is a Molang string (caller should handle).
        TypeError: If the value type is unrecognized.
    """
    if isinstance(value, (int, float)):
        return (float(value), "linear")

    if isinstance(value, str):
        # Molang expression -- caller should handle
        raise ValueError(f"Molang expression: {value}")

    if isinstance(value, dict):
        vec = float(value.get("vector", 0.0))
        easing = value.get("easing", "linear")
        return (vec, easing)

    raise TypeError(f"Unrecognized GeckoLib value type: {type(value).__name__}")


# ---------------------------------------------------------------------------
# AxisPresence — per-time-point axis tracking
# ---------------------------------------------------------------------------

@dataclass
class AxisPresence:
    """Track which axes are present at each time point during parsing.

    This dataclass records, for a single time point in an animation channel,
    which axes actually had data in the source JSON.  This enables the
    transform stage to distinguish between:

      - An axis explicitly set to 0.0 by the source data (x_present=True,
        x_value=0.0) -- the transform stage should NOT apply carry-forward.
      - An axis that has no data at this time point (x_present=False,
        x_value=0.0) -- the transform stage SHOULD apply carry-forward.

    Attributes:
        time: Time in seconds from animation start.
        x_present: True if the X axis had data at this time in the source.
        y_present: True if the Y axis had data at this time in the source.
        z_present: True if the Z axis had data at this time in the source.
        x_value: X-axis numeric value (0.0 if not present).
        y_value: Y-axis numeric value (0.0 if not present).
        z_value: Z-axis numeric value (0.0 if not present).
        x_easing: Easing function for X axis ("linear" if not present).
        y_easing: Easing function for Y axis ("linear" if not present).
        z_easing: Easing function for Z axis ("linear" if not present).
        x_molang: Molang expression for X axis (empty string if not Molang).
        y_molang: Molang expression for Y axis (empty string if not Molang).
        z_molang: Molang expression for Z axis (empty string if not Molang).
    """

    time: float
    x_present: bool = False
    y_present: bool = False
    z_present: bool = False
    x_value: float = 0.0
    y_value: float = 0.0
    z_value: float = 0.0
    x_easing: str = "linear"
    y_easing: str = "linear"
    z_easing: str = "linear"
    x_molang: str = ""
    y_molang: str = ""
    z_molang: str = ""

    def any_present(self) -> bool:
        """Return True if at least one axis was present in the source data."""
        return self.x_present or self.y_present or self.z_present

    def present_axes(self) -> List[str]:
        """Return the list of axis names that were present in the source data."""
        result: List[str] = []
        if self.x_present:
            result.append("x")
        if self.y_present:
            result.append("y")
        if self.z_present:
            result.append("z")
        return result

    def has_molang(self) -> bool:
        """Return True if any axis uses a Molang expression."""
        return bool(self.x_molang) or bool(self.y_molang) or bool(self.z_molang)

    def best_easing(self) -> str:
        """Return the first non-linear easing across all present axes.

        This is a heuristic for choosing a single easing for a keyframe
        when the source provides per-axis easing.  In practice, most
        source data uses the same easing for all axes at a given time
        point, but when they differ we pick the first non-linear one.
        """
        if self.x_present and self.x_easing != "linear":
            return self.x_easing
        if self.y_present and self.y_easing != "linear":
            return self.y_easing
        if self.z_present and self.z_easing != "linear":
            return self.z_easing
        return "linear"


# ---------------------------------------------------------------------------
# Per-axis data types
# ---------------------------------------------------------------------------

@dataclass
class _AxisEntry:
    """Internal: parsed data for one axis at one time point.

    Tracks both numeric values and Molang expressions.
    """

    value: float = 0.0
    easing: str = "linear"
    is_molang: bool = False
    molang: str = ""


def _parse_axis_data(
    axis_data,
    axis_name: str,
    bone_name: str,
    channel: str,
    model_name: str,
) -> Dict[float, _AxisEntry]:
    """Parse one axis's time series from the source JSON.

    The axis data can be:
      - None: no data for this axis.
      - A number (int/float): constant value at t=0.0.
      - A string: global Molang expression (applies at all times).
      - A dict with time keys: {"0.0": value, "1.0": value, ...}

    Args:
        axis_data: Raw axis data from the source JSON.
        axis_name: "x", "y", or "z".
        bone_name: Bone name for logging.
        channel: Channel name for logging.
        model_name: Model name for logging.

    Returns:
        Dict mapping time -> _AxisEntry.  For global Molang expressions,
        returns {0.0: _AxisEntry(is_molang=True, molang=...)}.
        For plain numbers, returns {0.0: _AxisEntry(value=N)}.
    """
    if axis_data is None:
        return {}

    # Plain number: constant value at t=0.0
    if isinstance(axis_data, (int, float)):
        return {0.0: _AxisEntry(value=float(axis_data))}

    # Global Molang: axis value is a string (not a time-series dict)
    if isinstance(axis_data, str):
        return {0.0: _AxisEntry(is_molang=True, molang=axis_data)}

    # Time-series dict: {"0.0": value, "1.0": value, ...}
    if not isinstance(axis_data, dict):
        logger.debug(
            "[%s] Unexpected axis data type for %s.%s.%s: %s",
            model_name, bone_name, channel, axis_name, type(axis_data).__name__,
        )
        return {}

    entries: Dict[float, _AxisEntry] = {}

    for time_str, value in axis_data.items():
        try:
            t = float(time_str)
        except (ValueError, TypeError):
            logger.warning(
                "[%s] Invalid time '%s' in %s.%s.%s, skipping",
                model_name, time_str, bone_name, channel, axis_name,
            )
            continue

        try:
            val, easing = parse_geckolib_value(value)
            entries[t] = _AxisEntry(value=val, easing=easing)
        except ValueError:
            # Molang expression at a specific time point
            molang_str = str(value)
            entries[t] = _AxisEntry(is_molang=True, molang=molang_str)
        except TypeError as e:
            logger.warning(
                "[%s] Unrecognized value in %s.%s.%s at t=%s: %s",
                model_name, bone_name, channel, axis_name, time_str, e,
            )
            continue

    return entries


# ---------------------------------------------------------------------------
# Main merge function
# ---------------------------------------------------------------------------

def merge_per_axis_data(
    axis_data: Dict[str, dict],
    channel: str,
    bone_name: str = "",
    model_name: str = "",
) -> List[AxisPresence]:
    """Merge per-axis time series into unified time points with explicit tracking.

    For each unique time point across all axes, create an AxisPresence that
    records which axes actually had data at that time.  This is the KEY
    improvement over the old parser: we can now distinguish "the source data
    has x=0.0 at t=1.0" from "the source data has no x value at t=1.0".
    The old parser would set both to 0.0, causing the transform stage's
    carry-forward to incorrectly hold x at its previous value when it
    should be 0.0.

    Args:
        axis_data: Dict mapping axis_name ("x", "y", "z") to the raw
                   per-axis time series dict from the source JSON.
                   Each axis's data can be:
                     - None: no data
                     - A string: global Molang expression
                     - A dict with time_str keys mapping to values
        channel: Channel name ("rotation", "position", "scale").
        bone_name: Bone name for logging context.
        model_name: Model name for logging context.

    Returns:
        List of AxisPresence instances, sorted by time.  Each instance
        records which axes were explicitly present at that time point.
    """
    # Step 1: Parse each axis's data into time -> _AxisEntry maps
    parsed: Dict[str, Dict[float, _AxisEntry]] = {}
    for axis_name in ("x", "y", "z"):
        raw = axis_data.get(axis_name)
        if raw is not None:
            parsed[axis_name] = _parse_axis_data(
                raw, axis_name, bone_name, channel, model_name
            )
        else:
            parsed[axis_name] = {}

    # Step 2: Collect all unique time points across all axes
    all_times: set = set()
    for axis_entries in parsed.values():
        all_times.update(axis_entries.keys())

    if not all_times:
        return []

    # Step 3: Build AxisPresence for each time point
    result: List[AxisPresence] = []

    for t in sorted(all_times):
        ap = AxisPresence(time=t)

        x_entry = parsed["x"].get(t)
        y_entry = parsed["y"].get(t)
        z_entry = parsed["z"].get(t)

        if x_entry is not None:
            ap.x_present = True
            if x_entry.is_molang:
                ap.x_molang = x_entry.molang
            else:
                ap.x_value = x_entry.value
                ap.x_easing = x_entry.easing

        if y_entry is not None:
            ap.y_present = True
            if y_entry.is_molang:
                ap.y_molang = y_entry.molang
            else:
                ap.y_value = y_entry.value
                ap.y_easing = y_entry.easing

        if z_entry is not None:
            ap.z_present = True
            if z_entry.is_molang:
                ap.z_molang = z_entry.molang
            else:
                ap.z_value = z_entry.value
                ap.z_easing = z_entry.easing

        result.append(ap)

    return result
