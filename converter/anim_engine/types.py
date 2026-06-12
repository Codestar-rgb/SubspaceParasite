#!/usr/bin/env python3
"""
AnimEngineV2 — Type Definitions and Constants
===============================================
Dataclasses and type aliases for the animation conversion pipeline.
Every stage of the pipeline uses these types for clear contracts.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AXES = ("x", "y", "z")
CHANNELS = ("rotation", "position", "scale")

# Default interpolation per channel
DEFAULT_INTERPOLATION = {
    "rotation": "catmullrom",
    "position": "linear",
    "scale": "linear",
}

# Easing names recognized by Blockbench
VALID_EASINGS = frozenset({
    "linear",
    "easeInQuad", "easeOutQuad", "easeInOutQuad",
    "easeInCubic", "easeOutCubic", "easeInOutCubic",
    "easeInQuart", "easeOutQuart", "easeInOutQuart",
    "easeInQuint", "easeOutQuint", "easeInOutQuint",
    "easeInSine", "easeOutSine", "easeInOutSine",
    "easeInExpo", "easeOutExpo", "easeInOutExpo",
    "easeInCirc", "easeOutCirc", "easeInOutCirc",
    "easeInBack", "easeOutBack", "easeInOutBack",
    "easeInElastic", "easeOutElastic", "easeInOutElastic",
    "easeInBounce", "easeOutBounce", "easeInOutBounce",
})

# Valid loop modes
VALID_LOOP_MODES = frozenset({"once", "hold_on_last_frame", "loop"})

# Rotation normalization range
ROTATION_MIN = -360.0
ROTATION_MAX = 360.0

# UUID length for bbmodel objects (16 hex chars to reduce collision risk)
UUID_LENGTH = 16


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AnimKeyframe:
    """A single keyframe for one channel of one bone.

    Attributes:
        time: Keyframe time in seconds (>= 0).
        x: X-axis value.
        y: Y-axis value.
        z: Z-axis value.
        easing: Easing function name (e.g. "linear", "easeOutSine").
        interpolation: Interpolation mode for Blockbench ("linear" or "catmullrom").
        channel: Channel name ("rotation", "position", or "scale").
        is_molang: Whether any axis contains a Molang expression string.
        molang_x: Molang expression for X axis (if is_molang).
        molang_y: Molang expression for Y axis (if is_molang).
        molang_z: Molang expression for Z axis (if is_molang).
    """
    time: float
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    easing: str = "linear"
    interpolation: str = "catmullrom"
    channel: str = "rotation"
    is_molang: bool = False
    molang_x: str = ""
    molang_y: str = ""
    molang_z: str = ""


@dataclass
class BoneAnimation:
    """All keyframes for one bone across all channels.

    Attributes:
        bone_name: Name of the bone.
        keyframes: List of AnimKeyframe instances, sorted by time then channel.
    """
    bone_name: str
    keyframes: List[AnimKeyframe] = field(default_factory=list)


@dataclass
class AnimationData:
    """One animation (e.g. "animation.kirin.idle").

    Attributes:
        name: Animation identifier (e.g. "animation.kirin.idle").
        loop: Loop mode ("once", "hold_on_last_frame", "loop").
        length: Animation length in seconds.
        bones: Dict mapping bone_name -> BoneAnimation.
    """
    name: str
    loop: str = "once"
    length: float = 0.0
    bones: Dict[str, BoneAnimation] = field(default_factory=dict)


@dataclass
class ConversionResult:
    """Result of converting an animation.json file.

    Attributes:
        animations: List of bbmodel-format animation dicts (ready for json.dumps).
        warnings: List of warning messages encountered during conversion.
        stats: Dict with conversion statistics.
    """
    animations: List[dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
