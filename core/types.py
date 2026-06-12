#!/usr/bin/env python3
"""
Super Architecture — Unified IR Type Definitions
=================================================

This module defines the Intermediate Representation (IR) data types that form
the backbone of the entire converter. Every module reads and writes these types,
ensuring a clean data flow with no raw dicts.

Key design decisions:
  - AxisValue tracks whether a value was explicitly set or is a carry-forward
    default, solving the "explicitly 0.0 vs missing data" ambiguity.
  - Frozen dataclasses for immutable IR nodes prevent accidental mutation.
  - All angles in degrees at the IR level; radians only used internally in
    quaternion.py.

Coordinate system context:
  MC 1.12.2 ModelRenderer: Right-hand, Y-DOWN (origin at top of hitbox)
  GeckoLib 1.20.1 geo.json: Left-hand, Y-UP (origin at feet)
  Blockbench .bbmodel:      Left-hand, Y-UP (same as GeckoLib)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Canonical axis names
AXES: Tuple[str, ...] = ("x", "y", "z")

# Animation channel names
CHANNELS: Tuple[str, ...] = ("rotation", "position", "scale")

# Default interpolation mode per channel
# GeckoLib Bedrock format 1.8.0 uses LINEAR interpolation by default.
# CatmullRom is only used when the source data explicitly specifies
# non-linear easing (e.g., "easeOutSine"). Using catmullrom as default
# for rotation causes severe overshoot artifacts in walk animations
# (short cycles with rapid direction changes).
DEFAULT_INTERPOLATION: Dict[str, str] = {
    "rotation": "linear",
    "position": "linear",
    "scale": "linear",
}

# Valid loop modes for GeckoLib / Blockbench
VALID_LOOP_MODES: frozenset = frozenset({"once", "hold_on_last_frame", "loop"})

# Rotation normalization range in degrees
ROTATION_MIN: float = -360.0
ROTATION_MAX: float = 360.0

# UUID length for bbmodel objects (16 hex chars = 64 bits)
UUID_LENGTH: int = 16


# ---------------------------------------------------------------------------
# AxisValue — tracks explicit vs. carry-forward
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AxisValue:
    """A single axis value that tracks whether it was explicitly set or defaulted.

    This solves the critical "explicitly 0.0 vs missing data" problem:
      - explicit=True means the source data provided this value (even if 0.0).
      - explicit=False means this axis was not present in the source and was
        filled in via carry-forward from the previous keyframe or default 0.0.

    The carry-forward logic in transform.py uses `explicit` to decide whether
    to replace a missing axis value with the previous keyframe's value.
    """

    value: float
    explicit: bool

    @staticmethod
    def explicit_val(v: float) -> AxisValue:
        """Create an AxisValue that was explicitly provided in source data."""
        return AxisValue(value=v, explicit=True)

    @staticmethod
    def default_val(v: float = 0.0) -> AxisValue:
        """Create an AxisValue that is a carry-forward default."""
        return AxisValue(value=v, explicit=False)

    def __repr__(self) -> str:
        tag = "E" if self.explicit else "D"
        return f"AxisValue({self.value}, {tag})"


# ---------------------------------------------------------------------------
# KeyframeData — the fundamental animation unit in the IR
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KeyframeData:
    """A single keyframe for one channel of one bone at a specific time.

    This is the fundamental unit of animation data in the IR.  Each axis
    tracks whether it was explicitly set or is a carry-forward default.

    Attributes:
        time: Time in seconds from animation start.
        channel: "rotation", "position", or "scale".
        x: X-axis value with explicit/default tracking.
        y: Y-axis value with explicit/default tracking.
        z: Z-axis value with explicit/default tracking.
        easing: Easing function name (e.g. "linear", "easeOutSine").
        interpolation: "linear" or "catmullrom".
        is_molang: True if any axis uses a Molang expression.
        molang_x: Molang expression for X axis (empty string if not Molang).
        molang_y: Molang expression for Y axis (empty string if not Molang).
        molang_z: Molang expression for Z axis (empty string if not Molang).
    """

    time: float
    channel: str
    x: AxisValue
    y: AxisValue
    z: AxisValue
    easing: str = "linear"
    interpolation: str = "linear"
    is_molang: bool = False
    molang_x: str = ""
    molang_y: str = ""
    molang_z: str = ""

    def has_explicit_axis(self) -> bool:
        """Return True if at least one axis was explicitly set."""
        return self.x.explicit or self.y.explicit or self.z.explicit

    def explicit_axes(self) -> List[str]:
        """Return the list of axis names that were explicitly set."""
        result: List[str] = []
        if self.x.explicit:
            result.append("x")
        if self.y.explicit:
            result.append("y")
        if self.z.explicit:
            result.append("z")
        return result


# ---------------------------------------------------------------------------
# Animation IR types
# ---------------------------------------------------------------------------

@dataclass
class BoneAnimationIR:
    """All keyframes for one bone across all channels.

    Attributes:
        bone_name: Name of the bone (must match a bone in ModelIR).
        keyframes: List of KeyframeData instances, typically sorted by
                   time then channel.
    """

    bone_name: str
    keyframes: List[KeyframeData] = field(default_factory=list)


@dataclass
class AnimationIR:
    """One animation (e.g. "animation.kirin.idle") in the IR.

    Attributes:
        name: Animation identifier string.
        loop: Loop mode — "once", "hold_on_last_frame", or "loop".
        length: Animation length in seconds.
        bones: Dict mapping bone_name -> BoneAnimationIR.
        period: Detected period for seamless looping (None = not yet analyzed).
    """

    name: str
    loop: str = "once"
    length: float = 0.0
    bones: Dict[str, BoneAnimationIR] = field(default_factory=dict)
    period: Optional[float] = None


# ---------------------------------------------------------------------------
# Model IR types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CubeIR:
    """A single cube element in the model IR.

    Attributes:
        origin: Cube origin (minimum corner) relative to bone pivot,
                as (x, y, z) in the target coordinate system.
        size: Cube dimensions (width, height, depth).
        uv: Per-face UV mapping: face_name -> {uv: [u,v], uv_size: [w,h]}.
            Face names: "north", "south", "east", "west", "up", "down".
        inflate: Inflation value (expands/contracts the cube).
        mirror: Whether the cube's texture is mirrored.
    """

    origin: Tuple[float, float, float]
    size: Tuple[float, float, float]
    uv: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    inflate: float = 0.0
    mirror: bool = False


@dataclass(frozen=True)
class BoneIR:
    """A bone in the model IR.

    Attributes:
        name: Bone name (unique within the model).
        parent: Parent bone name (None for root bones).
        pivot: Pivot point relative to parent bone, as (x, y, z).
        rotation: Static rotation in degrees, as (rx, ry, rz).
        cubes: List of CubeIR instances attached to this bone.
        binding: Bedrock binding expression (empty string if none).
    """

    name: str
    parent: Optional[str]
    pivot: Tuple[float, float, float]
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    cubes: List[CubeIR] = field(default_factory=list)
    binding: str = ""


@dataclass(frozen=True)
class ModelIR:
    """The complete model in the IR.

    Attributes:
        identifier: GeckoLib model identifier (e.g. "geometry.kirin").
        texture_width: Texture atlas width in pixels.
        texture_height: Texture atlas height in pixels.
        bones: Ordered list of BoneIR instances (parent before child).
    """

    identifier: str
    texture_width: int
    texture_height: int
    bones: List[BoneIR] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Conversion result
# ---------------------------------------------------------------------------

@dataclass
class ConversionResult:
    """Result of a full model conversion.

    Attributes:
        model: The converted model in IR format.
        animations: List of converted animations in IR format.
        warnings: List of warning messages encountered during conversion.
        stats: Dict with conversion statistics (e.g. keyframe counts,
               carry-forward fixes, etc.).
    """

    model: ModelIR
    animations: List[AnimationIR] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
