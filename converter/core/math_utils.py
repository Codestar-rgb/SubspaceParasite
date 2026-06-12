#!/usr/bin/env python3
"""
Super Architecture — General Math Utilities
=============================================

Pure helper functions used across the converter modules.  No side effects,
no I/O — easy to unit test.

Key functions:
  - rad_to_deg / deg_to_rad: angle unit conversion
  - normalize_rotation: clamp rotation to [-360, 360] degrees
  - is_valid_number: NaN/Infinity check
  - values_match: approximate float equality
  - round_for_bbmodel: 6-decimal-place rounding for output
  - generate_uuid: 16-hex-char UUIDs for bbmodel objects
  - lcm: least common multiple for period analysis
  - compute_animation_period: autocorrelation-based period detection
"""

from __future__ import annotations

import math
import uuid
from typing import List, Optional

from .types import ROTATION_MAX, ROTATION_MIN, UUID_LENGTH


# ---------------------------------------------------------------------------
# Angle conversions
# ---------------------------------------------------------------------------

def rad_to_deg(rad: float) -> float:
    """Convert radians to degrees.

    Args:
        rad: Angle in radians.

    Returns:
        Angle in degrees.
    """
    return rad * 180.0 / math.pi


def deg_to_rad(deg: float) -> float:
    """Convert degrees to radians.

    Args:
        deg: Angle in degrees.

    Returns:
        Angle in radians.
    """
    return deg * math.pi / 180.0


# ---------------------------------------------------------------------------
# Rotation utilities
# ---------------------------------------------------------------------------

def normalize_rotation(value: float) -> float:
    """Normalize a rotation value to [-360, 360] degrees.

    Values like 720 degrees and 0 degrees produce the same visual rotation
    but different interpolation results.  Normalizing ensures consistent
    spline behavior at loop boundaries.

    Examples:
        >>> normalize_rotation(720.0)
        0.0
        >>> normalize_rotation(-450.0)
        -90.0
        >>> normalize_rotation(45.0)
        45.0

    Args:
        value: Rotation angle in degrees.

    Returns:
        Normalized angle in [-360, 360] degrees.
    """
    if value == 0.0:
        return 0.0

    # Normalize to (-360, 360] using fmod, which preserves the sign of
    # the dividend.  This correctly handles negative values:
    #   fmod(-450, 360) = -90  (not 270 like Python's % operator)
    result = math.fmod(value, 360.0)

    # Clamp to exact range
    result = max(ROTATION_MIN, min(ROTATION_MAX, result))

    # Snap near-zero values to zero
    if abs(result) < 1e-10:
        return 0.0

    return result


# ---------------------------------------------------------------------------
# Number validation
# ---------------------------------------------------------------------------

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
        tolerance: Maximum allowed absolute difference.

    Returns:
        True if |a - b| <= tolerance.
    """
    return abs(a - b) <= tolerance


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def round_for_bbmodel(value: float) -> float:
    """Round a float value for bbmodel output.

    Rounds to 6 decimal places to avoid floating point noise while
    preserving sufficient precision for smooth animations.

    Args:
        value: The float to round.

    Returns:
        Rounded float with at most 6 decimal places.
    """
    return round(value, 6)


# ---------------------------------------------------------------------------
# UUID generation
# ---------------------------------------------------------------------------

def generate_uuid() -> str:
    """Generate a UUID string for bbmodel objects.

    Uses 16 hex characters (64 bits) to reduce collision risk compared
    to 8-character UUIDs.  With 168 models * ~100 elements each = ~17K
    objects, 8 hex chars (4 billion space) has a ~0.03% birthday-paradox
    collision probability; 16 hex chars (1.8e19 space) reduces this to
    negligible.

    Returns:
        16-character lowercase hex string.
    """
    return uuid.uuid4().hex[:UUID_LENGTH]


# ---------------------------------------------------------------------------
# Period analysis
# ---------------------------------------------------------------------------

def lcm(a: float, b: float) -> float:
    """Compute the least common multiple of two positive floats.

    Uses the relationship: lcm(a, b) = |a * b| / gcd(a, b).
    Floats are rounded to the nearest integer for GCD computation to
    handle values like 2.0, 3.0, 4.5 that represent rational periods.

    Args:
        a: First positive value.
        b: Second positive value.

    Returns:
        The least common multiple as a float.

    Raises:
        ValueError: If either value is not positive.
    """
    if a <= 0 or b <= 0:
        raise ValueError(f"lcm requires positive values, got a={a}, b={b}")

    # Round to reasonable precision to handle float imprecision
    a_int = round(a * 10000)
    b_int = round(b * 10000)

    if a_int == 0 or b_int == 0:
        return max(a, b)

    g = math.gcd(a_int, b_int)
    return (a_int * b_int) / (g * 10000.0)


def compute_animation_period(
    keyframe_times: List[float],
    values: List[float],
) -> Optional[float]:
    """Analyze keyframe data to detect the animation period.

    Uses autocorrelation to find the period that makes the animation
    loop seamlessly.  This replaces the old fixed 200-tick sampling
    window.

    Algorithm:
      1. If there are fewer than 4 data points, return None.
      2. Compute the autocorrelation of the value series.
      3. Find the first significant peak after lag 0.
      4. Return the corresponding period in seconds.

    The autocorrelation at lag k measures how similar the signal is to
    itself shifted by k samples.  For a periodic signal with period T,
    the autocorrelation has peaks at multiples of T.

    Args:
        keyframe_times: Sorted list of keyframe times in seconds.
        values: Corresponding list of scalar values (e.g. one axis
                of rotation).

    Returns:
        Detected period in seconds, or None if period cannot be determined.
    """
    n = len(values)
    if n < 4:
        return None

    # Resample to uniform time grid for autocorrelation
    if not keyframe_times:
        return None

    t_min = keyframe_times[0]
    t_max = keyframe_times[-1]
    duration = t_max - t_min

    if duration < 1e-6:
        return None

    # Use ~200 sample points (or fewer if n is very small)
    num_samples = min(200, n * 5)
    if num_samples < 8:
        return None

    dt = duration / (num_samples - 1)
    uniform = [0.0] * num_samples

    # Linear interpolation resampling
    src_idx = 0
    for i in range(num_samples):
        t = t_min + i * dt

        # Advance source index
        while src_idx < n - 1 and keyframe_times[src_idx + 1] < t:
            src_idx += 1

        if src_idx >= n - 1:
            uniform[i] = values[-1]
        else:
            t0 = keyframe_times[src_idx]
            t1 = keyframe_times[src_idx + 1]
            v0 = values[src_idx]
            v1 = values[src_idx + 1]
            span = t1 - t0
            if span < 1e-12:
                uniform[i] = v0
            else:
                frac = (t - t0) / span
                frac = max(0.0, min(1.0, frac))
                uniform[i] = v0 + frac * (v1 - v0)

    # Compute mean and subtract it (zero-mean for autocorrelation)
    mean = sum(uniform) / num_samples
    centered = [v - mean for v in uniform]

    # Compute variance for normalization
    variance = sum(v * v for v in centered)
    if variance < 1e-20:
        # Constant signal — no period
        return None

    # Compute autocorrelation using the direct method (O(n^2) but fine for 200 samples)
    # We check lags from 1 to 2/3 of num_samples. This allows detecting periods
    # up to ~2/3 of the signal duration while still having enough samples for
    # reliable autocorrelation (need at least 1+ period of remaining data).
    max_lag = (2 * num_samples) // 3
    autocorr = [0.0] * (max_lag + 1)
    for lag in range(max_lag + 1):
        ac = 0.0
        count = num_samples - lag
        for i in range(count):
            ac += centered[i] * centered[i + lag]
        autocorr[lag] = ac / variance if variance > 0 else 0.0

    # Find the first significant peak after lag 0
    # A peak is where autocorr[lag] > autocorr[lag-1] and
    # autocorr[lag] > autocorr[lag+1] and autocorr[lag] > threshold
    threshold = 0.3  # Require at least 30% correlation for a valid period

    best_period_lag = None
    best_ac = 0.0

    for lag in range(2, max_lag - 1):
        if (autocorr[lag] > autocorr[lag - 1] and
                autocorr[lag] > autocorr[lag + 1] and
                autocorr[lag] > threshold):
            if best_period_lag is None or autocorr[lag] > best_ac:
                best_period_lag = lag
                best_ac = autocorr[lag]

    if best_period_lag is None:
        return None

    # Convert lag to period in seconds
    period_seconds = best_period_lag * dt

    if period_seconds < 1e-6:
        return None

    # Validate: the period should be at most the duration
    if period_seconds > duration * 1.5:
        return None

    return period_seconds
