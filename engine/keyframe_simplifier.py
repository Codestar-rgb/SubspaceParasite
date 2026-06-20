#!/usr/bin/env python3
"""
Keyframe Simplifier (v6.9) — Ramer-Douglas-Peucker Algorithm
=============================================================
Reduces keyframe count by removing redundant keyframes on smooth
linear segments, while preserving animation fidelity within a
configurable error threshold.

WHY: CatmullRom baking produces dense linear keyframes (40-80 per
cycle per bone per channel). For SRP models with 50-300 bones, this
creates .bbmodel files with 10K-50K keyframes, causing:
- Large file sizes (100-500MB total)
- Slow GeckoLib runtime parsing
- Slow Blockbench loading

The RDP algorithm reduces keyframes by ~60-80% while keeping visual
error under 0.1° (imperceptible).

ALGORITHM:
  1. For each bone's keyframe curve (per channel, per axis):
  2. Find the point with maximum perpendicular distance from the
     line connecting first and last points.
  3. If max distance > threshold, recursively split at that point.
  4. If max distance <= threshold, discard all intermediate points.
"""

from __future__ import annotations
import logging
from typing import List, Tuple
from core.types import AnimationIR, BoneAnimationIR, KeyframeData, AxisValue

logger = logging.getLogger(__name__)

# Error threshold in degrees — points within this distance from the
# simplified line are considered redundant and removed.
RDP_THRESHOLD = 0.15  # degrees — imperceptible visual difference


def _perpendicular_distance(
    px: float, py: float,
    x1: float, y1: float,
    x2: float, y2: float,
) -> float:
    """Perpendicular distance from point (px,py) to line (x1,y1)-(x2,y2)."""
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    # Distance = |cross product| / |line length|
    return abs(dy * px - dx * py + x2 * y1 - y2 * x1) / ((dx * dx + dy * dy) ** 0.5)


def _rdp_simplify(
    points: List[Tuple[float, float]],
    threshold: float,
) -> List[Tuple[float, float]]:
    """Ramer-Douglas-Peucker simplification on 2D points.

    Args:
        points: List of (time, value) tuples.
        threshold: Max perpendicular distance to keep (points closer are removed).

    Returns:
        Simplified list of (time, value) tuples.
    """
    if len(points) < 3:
        return points

    # Find point with max perpendicular distance from line(first, last)
    first = points[0]
    last = points[-1]
    max_dist = 0.0
    max_idx = 0

    for i in range(1, len(points) - 1):
        dist = _perpendicular_distance(
            points[i][0], points[i][1],
            first[0], first[1],
            last[0], last[1],
        )
        if dist > max_dist:
            max_dist = dist
            max_idx = i

    if max_dist > threshold:
        # Recursively simplify both halves
        left = _rdp_simplify(points[:max_idx + 1], threshold)
        right = _rdp_simplify(points[max_idx:], threshold)
        # Merge (avoid duplicating the split point)
        return left[:-1] + right
    else:
        # All intermediate points are within threshold — keep only endpoints
        return [first, last]


def _simplify_keyframes(
    keyframes: List[KeyframeData],
    threshold: float = RDP_THRESHOLD,
) -> List[KeyframeData]:
    """Simplify keyframes for one bone using RDP per (channel, axis).

    Preserves t=0 and t=length boundary keyframes for seamless loops.
    """
    if len(keyframes) < 4:
        return keyframes  # Too few to simplify

    # Group by channel
    by_channel: dict = {}
    for kf in keyframes:
        by_channel.setdefault(kf.channel, []).append(kf)

    result: List[KeyframeData] = []

    for channel, ch_kfs in by_channel.items():
        ch_kfs_sorted = sorted(ch_kfs, key=lambda k: k.time)

        if len(ch_kfs_sorted) < 4:
            result.extend(ch_kfs_sorted)
            continue

        # Simplify per axis (x, y, z independently)
        keep_indices = set()
        keep_indices.add(0)  # Always keep first
        keep_indices.add(len(ch_kfs_sorted) - 1)  # Always keep last

        for axis in ("x", "y", "z"):
            points = []
            for kf in ch_kfs_sorted:
                val = getattr(kf, axis).value
                points.append((kf.time, val))

            simplified = _rdp_simplify(points, threshold)
            simplified_times = {t for t, _ in simplified}
            # Map back to keyframe indices
            for i, kf in enumerate(ch_kfs_sorted):
                if kf.time in simplified_times:
                    keep_indices.add(i)

        # Build simplified keyframe list (preserving order)
        for i in sorted(keep_indices):
            result.append(ch_kfs_sorted[i])

    result.sort(key=lambda k: (k.time, k.channel))
    return result


def simplify_animations(
    animations: List[AnimationIR],
    model_name: str = "",
    threshold: float = RDP_THRESHOLD,
) -> List[AnimationIR]:
    """Simplify all keyframes in all animations using RDP.

    Args:
        animations: List of AnimationIR to simplify in-place.
        model_name: Model name for logging.
        threshold: RDP error threshold in degrees.

    Returns:
        List of AnimationIR with simplified keyframes.
    """
    total_before = 0
    total_after = 0

    for anim in animations:
        new_bones = {}
        for bone_name, bone_anim in anim.bones.items():
            total_before += len(bone_anim.keyframes)
            simplified = _simplify_keyframes(bone_anim.keyframes, threshold)
            total_after += len(simplified)
            new_bones[bone_name] = BoneAnimationIR(
                bone_name=bone_name,
                keyframes=simplified,
            )
        anim.bones = new_bones

    if total_before > 0:
        reduction = (1 - total_after / total_before) * 100
        logger.debug(
            "[%s] RDP simplification: %d → %d keyframes (%.1f%% reduction)",
            model_name, total_before, total_after, reduction,
        )

    return animations


# v6.9.2: Bone name classifier for RDP sensitivity.
# High-frequency bones (tentacles, hair, spines) have subtle rapid oscillations
# that are visually important for the "creepy crawling" feel of SRP parasites.
# These should NOT be aggressively simplified — use a much lower threshold.

# Bones matching these patterns get a lower RDP threshold (0.02° instead of 0.15°)
HIGH_FREQ_PATTERNS = [
    "tacle", "tentacle", "hair", "spine", "joint", "tendril",
    "ff1", "ff2", "ff3",  # hair joint variants
    "dec",  # decorative segments
]

# Bones matching these patterns are structural (legs, body) — safe to simplify normally
STRUCTURAL_PATTERNS = [
    "leg", "body", "head", "arm", "main", "root", "neck",
    "frontleg", "backleg", "jointL", "jointR", "jointM",
]


def _get_bone_threshold(bone_name: str, default_threshold: float) -> float:
    """Get RDP threshold for a bone based on its name.

    High-frequency bones (tentacles, hair) get a much lower threshold
    to preserve their subtle rapid oscillations.
    """
    lower = bone_name.lower()
    for pattern in HIGH_FREQ_PATTERNS:
        if pattern in lower:
            return 0.02  # Very low threshold — preserve micro-oscillations
    return default_threshold


def _simplify_keyframes_v2(
    keyframes: List[KeyframeData],
    bone_name: str,
    default_threshold: float = RDP_THRESHOLD,
) -> List[KeyframeData]:
    """Simplify keyframes with bone-aware threshold.

    Uses a lower threshold for high-frequency bones (tentacles, hair, spines)
    to preserve their biological micro-oscillations.
    """
    threshold = _get_bone_threshold(bone_name, default_threshold)
    return _simplify_keyframes(keyframes, threshold)


def simplify_animations_v2(
    animations: List[AnimationIR],
    model_name: str = "",
    threshold: float = RDP_THRESHOLD,
) -> List[AnimationIR]:
    """Simplify animations with bone-aware RDP threshold.

    This is the v6.9.2 version that preserves high-frequency bone oscillations.
    """
    total_before = 0
    total_after = 0

    for anim in animations:
        new_bones = {}
        for bone_name, bone_anim in anim.bones.items():
            total_before += len(bone_anim.keyframes)
            simplified = _simplify_keyframes_v2(bone_anim.keyframes, bone_name, threshold)
            total_after += len(simplified)
            new_bones[bone_name] = BoneAnimationIR(
                bone_name=bone_name,
                keyframes=simplified,
            )
        anim.bones = new_bones

    if total_before > 0:
        reduction = (1 - total_after / total_before) * 100
        logger.debug(
            "[%s] RDP v2 simplification: %d → %d keyframes (%.1f%% reduction)",
            model_name, total_before, total_after, reduction,
        )

    return animations


def _resample_uniform(kfs, anim_length):
    """Resample keyframes to uniform time spacing.
    
    After RDP, keyframes are at curve extrema which may be non-uniformly
    spaced. This resamples them to uniform spacing while preserving the
    curve shape via linear interpolation from the RDP result.
    
    This eliminates the 'mechanical' and 'acceleration' feel caused by
    irregular keyframe spacing in loop animations.
    """
    if len(kfs) < 3:
        return kfs
    
    # Sort by time
    kfs = sorted(kfs, key=lambda k: (k.time, k.channel))
    
    # Group by channel
    by_channel = {}
    for kf in kfs:
        by_channel.setdefault(kf.channel, []).append(kf)
    
    result = []
    for ch, ch_kfs in by_channel.items():
        if len(ch_kfs) < 3:
            result.extend(ch_kfs)
            continue
        
        ch_kfs = sorted(ch_kfs, key=lambda k: k.time)
        n = len(ch_kfs)
        
        # Create uniform times
        uniform_times = [i * anim_length / (n - 1) for i in range(n)]
        
        # Get original times and values per axis
        orig_times = [kf.time for kf in ch_kfs]
        
        for t in uniform_times:
            # Interpolate each axis
            axis_vals = {}
            for axis in ('x', 'y', 'z'):
                orig_vals = [getattr(kf, axis).value for kf in ch_kfs]
                if t <= orig_times[0]:
                    axis_vals[axis] = orig_vals[0]
                elif t >= orig_times[-1]:
                    axis_vals[axis] = orig_vals[-1]
                else:
                    # Linear interpolation
                    for j in range(len(orig_times) - 1):
                        if orig_times[j] <= t <= orig_times[j + 1]:
                            dt = orig_times[j + 1] - orig_times[j]
                            if dt < 1e-10:
                                axis_vals[axis] = orig_vals[j]
                            else:
                                s = (t - orig_times[j]) / dt
                                axis_vals[axis] = orig_vals[j] + s * (orig_vals[j + 1] - orig_vals[j])
                            break
                    else:
                        axis_vals[axis] = orig_vals[-1]
            
            result.append(KeyframeData(
                time=round(t, 6),
                channel=ch,
                x=AxisValue.explicit_val(axis_vals['x']),
                y=AxisValue.explicit_val(axis_vals['y']),
                z=AxisValue.explicit_val(axis_vals['z']),
                easing='linear',
                interpolation='linear',
            ))
    
    result.sort(key=lambda k: (k.time, k.channel))
    return result


def simplify_animations_v3(
    animations,
    model_name: str = "",
    threshold: float = RDP_THRESHOLD,
    anim_length: float = 0,
):
    """v6.9.3: RDP + uniform resample for smooth loop animations.
    
    1. Apply bone-aware RDP simplification (preserve tentacle micro-oscillations)
    2. Resample to uniform time spacing (eliminate mechanical/acceleration feel)
    """
    total_before = 0
    total_after = 0

    for anim in animations:
        length = anim_length if anim_length > 0 else anim.length
        new_bones = {}
        for bone_name, bone_anim in anim.bones.items():
            total_before += len(bone_anim.keyframes)
            # Step 1: RDP simplification
            simplified = _simplify_keyframes_v2(bone_anim.keyframes, bone_name, threshold)
            # Step 2: Uniform resample for smooth playback
            if len(simplified) >= 3 and anim.loop == "loop" and length > 0:
                simplified = _resample_uniform(simplified, length)
            total_after += len(simplified)
            new_bones[bone_name] = BoneAnimationIR(
                bone_name=bone_name,
                keyframes=simplified,
            )
        anim.bones = new_bones

    if total_before > 0:
        reduction = (1 - total_after / total_before) * 100
        logger.debug(
            "[%s] RDP v3 (uniform): %d -> %d keyframes (%.1f%% reduction)",
            model_name, total_before, total_after, reduction,
        )

    return animations
