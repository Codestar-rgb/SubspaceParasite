"""Animation and Bone Profile Dataclasses

Profiles describe the characteristics of an animation and its bones,
used to guide pipeline selection and processing parameters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Tuple


class AnimCategory(Enum):
    """Animation category for pipeline routing."""
    WALK = "walk"
    IDLE = "idle"
    ATTACK = "attack"
    DEATH = "death"
    SLEEP = "sleep"
    EVOLVED = "evolved"
    UNKNOWN = "unknown"


class BoneRole(Enum):
    """Functional role of a bone within an animation."""
    LEG = "leg"
    ARM = "arm"
    BODY = "body"
    HEAD = "head"
    UNSPECIFIED = "unspecified"


@dataclass
class BoneProfile:
    """Profile for a single bone within an animation.

    Attributes:
        name: Bone identifier.
        role: Functional role (leg, arm, body, head, unspecified).
        has_rotation: Whether this bone has rotation channel data.
        has_position: Whether this bone has position channel data.
        rotation_kf_count: Number of rotation keyframes.
        position_kf_count: Number of position keyframes.
        rotation_amplitude: Peak-to-peak range of rotation (max - min per axis, then max of those).
        position_amplitude: Peak-to-peak range of position.
        is_left_side: Whether this bone appears to be on the left side.
        is_right_side: Whether this bone appears to be on the right side.
        paired_bone: Name of the paired bone on the opposite side (if any).
        phase_offset: Estimated phase offset relative to a reference bone (for walk analysis).
    """
    name: str = ""
    role: BoneRole = BoneRole.UNSPECIFIED
    has_rotation: bool = False
    has_position: bool = False
    rotation_kf_count: int = 0
    position_kf_count: int = 0
    rotation_amplitude: float = 0.0
    position_amplitude: float = 0.0
    is_left_side: bool = False
    is_right_side: bool = False
    paired_bone: str = ""
    phase_offset: float = 0.0


@dataclass
class AnimationProfile:
    """Complete profile of an animation for pipeline routing and processing.

    Attributes:
        name: Full animation identifier, e.g. "animation.ferHuman.walk"
        category: Detected animation category.
        loop: Loop mode from source data.
        length: Duration in seconds.
        bones: Per-bone profiles.
        total_keyframes: Total KF count across all bones/channels.
        bone_count: Number of animated bones.
        is_periodic: Whether the animation shows periodic behavior.
        estimated_period: Estimated period in seconds (if periodic).
        content_hash: Hash of keyframe data for deduplication.
        is_half_cycle: Whether the source only covers half a gait cycle.
        walk_phase: Phase relationship between leg bones (for walk).
        max_rotation_amplitude: Maximum rotation amplitude across all bones.
        interpolation: Dominant interpolation type across keyframes.
    """
    name: str = ""
    category: AnimCategory = AnimCategory.UNKNOWN
    loop: str = "once"
    length: float = 0.0
    bones: Dict[str, BoneProfile] = field(default_factory=dict)
    total_keyframes: int = 0
    bone_count: int = 0
    is_periodic: bool = False
    estimated_period: float = 0.0
    content_hash: str = ""
    is_half_cycle: bool = False
    walk_phase: Dict[str, float] = field(default_factory=dict)
    max_rotation_amplitude: float = 0.0
    interpolation: str = "catmullrom"

    @property
    def leg_bones(self) -> List[str]:
        """Names of bones classified as legs."""
        return [name for name, bp in self.bones.items() if bp.role == BoneRole.LEG]

    @property
    def arm_bones(self) -> List[str]:
        """Names of bones classified as arms."""
        return [name for name, bp in self.bones.items() if bp.role == BoneRole.ARM]

    @property
    def body_bones(self) -> List[str]:
        """Names of bones classified as body."""
        return [name for name, bp in self.bones.items() if bp.role == BoneRole.BODY]

    @property
    def head_bones(self) -> List[str]:
        """Names of bones classified as head."""
        return [name for name, bp in self.bones.items() if bp.role == BoneRole.HEAD]

    @property
    def is_loop(self) -> bool:
        """Whether this animation should loop."""
        return self.loop == "loop"
