"""BBModel Animation Parser

Extracts animation data from Blockbench .bbmodel files, organizing keyframes
by bone and channel type. Handles the double-keyframe glitch and groups
keyframes into the canonical format used throughout AnimForge.
"""

from __future__ import annotations

import json
import copy
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..core.config import AnimForgeConfig

# Type alias: keyframes stored as list of (time, (x, y, z)) tuples
Keyframes = List[Tuple[float, Tuple[float, float, float]]]
# Per-bone, per-channel keyframe data
BoneChannels = Dict[str, Dict[str, Keyframes]]  # bone_name -> {"rotation"|"position" -> keyframes


class ParsedAnimation:
    """A single parsed animation with its metadata and keyframe data.

    Attributes:
        name: Animation identifier, e.g. "animation.ferHuman.walk"
        loop: Loop mode string from source ("loop", "once", "hold", etc.)
        length: Animation duration in seconds
        override: Whether this animation overrides previous ones
        animators: Raw animator data from the source
        bone_channels: Organized keyframes: bone_name -> channel -> [(time, (x,y,z))]
    """

    def __init__(
        self,
        name: str,
        loop: str,
        length: float,
        override: bool,
        animators: Dict[str, Any],
        bone_channels: BoneChannels,
    ) -> None:
        self.name = name
        self.loop = loop
        self.length = length
        self.override = override
        self.animators = animators
        self.bone_channels = bone_channels

    @property
    def bone_names(self) -> List[str]:
        """List of bone names that have animation data."""
        return list(self.bone_channels.keys())

    @property
    def total_keyframes(self) -> int:
        """Total number of keyframes across all bones and channels."""
        count = 0
        for channels in self.bone_channels.values():
            for kfs in channels.values():
                count += len(kfs)
        return count

    def get_channel(self, bone: str, channel: str) -> Keyframes:
        """Get keyframes for a specific bone and channel."""
        return self.bone_channels.get(bone, {}).get(channel, [])

    def deep_copy(self) -> ParsedAnimation:
        """Create a deep copy of this parsed animation."""
        return ParsedAnimation(
            name=self.name,
            loop=self.loop,
            length=self.length,
            override=self.override,
            animators=copy.deepcopy(self.animators),
            bone_channels=copy.deepcopy(self.bone_channels),
        )


class BBModelParser:
    """Parses .bbmodel files and extracts animation data.

    Handles:
    - Multiple animations per file
    - Rotation and position channels per bone
    - Double-keyframe glitch (identical consecutive timestamps)
    - Various interpolation modes
    - Missing/empty channels
    """

    def __init__(self, config: AnimForgeConfig | None = None) -> None:
        self.config = config or AnimForgeConfig()

    def parse_file(self, path: str | Path) -> List[ParsedAnimation]:
        """Parse a .bbmodel file and return all animations.

        Args:
            path: Path to the .bbmodel file.

        Returns:
            List of ParsedAnimation objects.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            json.JSONDecodeError: If the file isn't valid JSON.
            ValueError: If no animations are found.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"BBModel file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return self.parse_data(data)

    def parse_data(self, data: Dict[str, Any]) -> List[ParsedAnimation]:
        """Parse BBModel JSON data and return all animations.

        Args:
            data: Parsed JSON data from a .bbmodel file.

        Returns:
            List of ParsedAnimation objects.
        """
        raw_animations = data.get("animations", [])
        if not raw_animations:
            return []

        parsed: List[ParsedAnimation] = []
        for raw_anim in raw_animations:
            anim = self._parse_animation(raw_anim)
            if anim is not None:
                parsed.append(anim)

        return parsed

    def _parse_animation(self, raw: Dict[str, Any]) -> ParsedAnimation | None:
        """Parse a single animation entry from the .bbmodel data."""
        name = raw.get("name", "animation.unknown")
        loop = raw.get("loop", "once")
        length = float(raw.get("length", 0.0))
        override = raw.get("override", False)
        animators = raw.get("animators", {})

        if not animators:
            # Animation with no animators is still valid (empty animation)
            return ParsedAnimation(
                name=name,
                loop=loop,
                length=length,
                override=override,
                animators=animators,
                bone_channels={},
            )

        bone_channels: BoneChannels = {}
        for bone_name, animator_data in animators.items():
            if not isinstance(animator_data, dict):
                continue

            animator_type = animator_data.get("type", "bone")
            if animator_type != "bone":
                # Skip effect/text animators
                continue

            keyframes = animator_data.get("keyframes", [])
            if not keyframes:
                continue

            channels = self._parse_keyframes(keyframes)
            if channels:
                bone_channels[bone_name] = channels

        return ParsedAnimation(
            name=name,
            loop=loop,
            length=length,
            override=override,
            animators=animators,
            bone_channels=bone_channels,
        )

    def _parse_keyframes(
        self, keyframes: List[Dict[str, Any]]
    ) -> Dict[str, Keyframes]:
        """Parse keyframes grouped by channel type.

        Handles the double-keyframe glitch where two keyframes share the same
        timestamp and data. Only the first is kept.

        Returns:
            Dict mapping channel name ("rotation", "position") to keyframe list.
        """
        raw_rotation: List[Tuple[float, Tuple[float, float, float]]] = []
        raw_position: List[Tuple[float, Tuple[float, float, float]]] = []

        for kf in keyframes:
            channel = kf.get("channel", "")
            time = float(kf.get("time", 0.0))
            data_points = kf.get("data_points", [])

            if not data_points:
                continue

            # Use first data point (multi-point KFs are rare and GeckoLib doesn't use them)
            dp = data_points[0]
            x = self._parse_float(dp.get("x", 0))
            y = self._parse_float(dp.get("y", 0))
            z = self._parse_float(dp.get("z", 0))

            values = (x, y, z)

            # Skip if all values are zero and channel hasn't started (reduces noise)
            if channel == "rotation":
                raw_rotation.append((time, values))
            elif channel == "position":
                raw_position.append((time, values))

        # Sort by time and remove double-keyframe glitches
        channels: Dict[str, Keyframes] = {}
        if raw_rotation:
            raw_rotation.sort(key=lambda kf: kf[0])
            channels["rotation"] = self._remove_double_keyframes(raw_rotation)
        if raw_position:
            raw_position.sort(key=lambda kf: kf[0])
            channels["position"] = self._remove_double_keyframes(raw_position)

        return channels

    @staticmethod
    def _remove_double_keyframes(
        keyframes: Keyframes,
    ) -> Keyframes:
        """Remove duplicate keyframes at the same timestamp.

        The double-keyframe glitch in Blockbench exports can produce two
        identical (or near-identical) keyframes at the same time. We keep
        only the first occurrence at each timestamp.
        """
        if len(keyframes) <= 1:
            return keyframes

        result: Keyframes = [keyframes[0]]
        for i in range(1, len(keyframes)):
            t_prev = result[-1][0]
            t_curr = keyframes[i][0]
            # If timestamps are effectively identical, skip the duplicate
            if abs(t_curr - t_prev) < 1e-6:
                continue
            result.append(keyframes[i])

        return result

    @staticmethod
    def _parse_float(value: Any) -> float:
        """Safely parse a float value, handling string representations."""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return 0.0
        return 0.0
