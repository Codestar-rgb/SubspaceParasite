"""GeckoLib Serializer

Transforms and serializes animation data to GeckoLib .animation.json format.

Key responsibilities:
- Apply coordinate transforms (rotation and position) at serialization time ONLY
- Transform rotation values: (rx, ry, rz) → (-rx, -ry, rz)
- Transform position values: (px, py, pz) → (-px, py, pz)
- Serialize to GeckoLib format with time-string keys
- Handle static (single-value) and animated channels
- Preserve animation name format (animation.modelName.animType)
"""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from ..core.config import AnimForgeConfig
from ..core.parser import ParsedAnimation, Keyframes
from ..core.profile import AnimationProfile


class GeckoLibSerializer:
    """Serializes processed animations to GeckoLib .animation.json format.

    The coordinate transform is applied ONLY at serialization time, not during
    processing. This ensures all pipeline operations work in the original
    Blockbench coordinate system.
    """

    FORMAT_VERSION = "1.8.0"

    def __init__(self, config: AnimForgeConfig | None = None) -> None:
        self.config = config or AnimForgeConfig()

    def serialize(
        self,
        animations: List[ParsedAnimation],
        profiles: List[AnimationProfile],
        model_name: str = "",
    ) -> Dict[str, Any]:
        """Serialize multiple animations to GeckoLib format.

        Args:
            animations: List of processed animations.
            profiles: Corresponding animation profiles.
            model_name: Override model name for animation identifiers.

        Returns:
            Dict in GeckoLib .animation.json format.
        """
        result: Dict[str, Any] = OrderedDict()
        result["format_version"] = self.FORMAT_VERSION

        animations_dict: Dict[str, Any] = OrderedDict()

        for anim, profile in zip(animations, profiles):
            anim_name = self._format_animation_name(anim.name, model_name)
            anim_data = self._serialize_animation(anim, profile)
            animations_dict[anim_name] = anim_data

        result["animations"] = animations_dict
        return result

    def serialize_single(
        self,
        anim: ParsedAnimation,
        profile: AnimationProfile,
        model_name: str = "",
    ) -> Dict[str, Any]:
        """Serialize a single animation to GeckoLib format.

        Args:
            anim: Processed animation.
            profile: Animation profile.
            model_name: Override model name.

        Returns:
            Dict in GeckoLib .animation.json format.
        """
        result: Dict[str, Any] = OrderedDict()
        result["format_version"] = self.FORMAT_VERSION

        anim_name = self._format_animation_name(anim.name, model_name)
        result["animations"] = OrderedDict()
        result["animations"][anim_name] = self._serialize_animation(anim, profile)

        return result

    def write(
        self,
        animations: List[ParsedAnimation],
        profiles: List[AnimationProfile],
        output_path: str | Path,
        model_name: str = "",
    ) -> None:
        """Serialize and write animations to a .animation.json file.

        Args:
            animations: List of processed animations.
            profiles: Corresponding animation profiles.
            output_path: Path to the output file.
            model_name: Override model name.
        """
        output_path = Path(output_path)
        data = self.serialize(animations, profiles, model_name)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # ── Internal Serialization ────────────────────────────────────────────

    def _format_animation_name(self, original_name: str, model_name: str) -> str:
        """Format the animation name for GeckoLib output.

        GeckoLib uses the format: animation.{modelName}.{animType}

        If model_name is provided, it replaces the model part of the name.
        """
        if model_name:
            # Extract the animation type from the original name
            parts = original_name.split(".")
            if len(parts) >= 3:
                anim_type = ".".join(parts[2:])
            elif len(parts) == 2:
                anim_type = parts[1]
            else:
                anim_type = original_name

            # Clean model name for GeckoLib (lowercase, no spaces)
            clean_model = re.sub(r'[^a-zA-Z0-9_]', '', model_name.lower())
            return f"animation.{clean_model}.{anim_type}"

        return original_name

    def _serialize_animation(
        self, anim: ParsedAnimation, profile: AnimationProfile
    ) -> Dict[str, Any]:
        """Serialize a single animation to GeckoLib format."""
        result: Dict[str, Any] = OrderedDict()

        # Loop mode
        if anim.loop == "loop":
            result["loop"] = "loop"
        else:
            result["loop"] = "hold_on_last_frame"

        # Animation length
        if anim.length > 0:
            result["animation_length"] = self.config.round_time(anim.length)

        # Bones
        bones: Dict[str, Any] = OrderedDict()
        for bone_name in sorted(anim.bone_channels.keys()):
            channels = anim.bone_channels[bone_name]
            bone_data = self._serialize_bone(bone_name, channels, profile)
            if bone_data:
                bones[bone_name] = bone_data

        if bones:
            result["bones"] = bones

        return result

    def _serialize_bone(
        self,
        bone_name: str,
        channels: Dict[str, Keyframes],
        profile: AnimationProfile,
    ) -> Dict[str, Any]:
        """Serialize a single bone's channels to GeckoLib format."""
        bone_data: Dict[str, Any] = OrderedDict()

        if "rotation" in channels:
            rot_data = self._serialize_channel(
                channels["rotation"], "rotation"
            )
            if rot_data is not None:
                bone_data["rotation"] = rot_data

        if "position" in channels:
            pos_data = self._serialize_channel(
                channels["position"], "position"
            )
            if pos_data is not None:
                bone_data["position"] = pos_data

        return bone_data

    def _serialize_channel(
        self,
        keyframes: Keyframes,
        channel_type: str,
    ) -> Optional[Union[List[float], Dict[str, List[float]]]]:
        """Serialize a keyframe channel to GeckoLib format.

        Applies the coordinate transform based on channel type:
        - rotation: (rx, ry, rz) → (-rx, -ry, rz)
        - position: (px, py, pz) → (-px, py, pz)

        For a single keyframe (static value), returns a list [x, y, z].
        For multiple keyframes, returns a dict with time-string keys.

        Args:
            keyframes: Processed keyframe data.
            channel_type: "rotation" or "position".

        Returns:
            Serialized channel data, or None if empty.
        """
        if not keyframes:
            return None

        # Apply coordinate transform
        transform = self._get_transform(channel_type)
        transformed = self._apply_transform(keyframes, transform)

        # Round values
        rounded = self._round_keyframes(transformed)

        if len(rounded) == 1:
            # Static value (single keyframe)
            return list(rounded[0][1])
        else:
            # Animated: dict with time keys
            result: Dict[str, List[float]] = OrderedDict()
            for time, values in rounded:
                time_key = self._format_time_key(time)
                result[time_key] = list(values)
            return result

    def _get_transform(self, channel_type: str) -> Tuple[bool, bool, bool]:
        """Get the coordinate transform flags for a channel type.

        Returns (negate_x, negate_y, negate_z) tuple.
        """
        if channel_type == "rotation":
            return self.config.coordinate_rotation  # (True, True, False)
        elif channel_type == "position":
            return self.config.coordinate_position  # (True, False, False)
        return (False, False, False)

    @staticmethod
    def _apply_transform(
        keyframes: Keyframes,
        transform: Tuple[bool, bool, bool],
    ) -> Keyframes:
        """Apply coordinate transform to keyframe values.

        Args:
            keyframes: Original keyframes.
            transform: (negate_x, negate_y, negate_z) flags.

        Returns:
            Transformed keyframes.
        """
        negate_x, negate_y, negate_z = transform
        result: Keyframes = []

        for time, (x, y, z) in keyframes:
            new_x = -x if negate_x else x
            new_y = -y if negate_y else y
            new_z = -z if negate_z else z
            result.append((time, (new_x, new_y, new_z)))

        return result

    @staticmethod
    def _clean_zero(v: float) -> float:
        """Convert -0.0 to 0.0 for cleaner output."""
        return 0.0 if v == 0.0 else v

    def _round_keyframes(self, keyframes: Keyframes) -> Keyframes:
        """Round all time and value entries to configured precision."""
        clean = self._clean_zero
        return [
            (
                clean(self.config.round_time(t)),
                (
                    clean(self.config.round_value(v[0])),
                    clean(self.config.round_value(v[1])),
                    clean(self.config.round_value(v[2])),
                ),
            )
            for t, v in keyframes
        ]

    @staticmethod
    def _format_time_key(time: float) -> str:
        """Format a time value as a string key for GeckoLib.

        GeckoLib uses string time keys like "0.0", "0.3333", etc.
        We format to remove trailing zeros but keep at least one decimal.
        """
        # Round to avoid floating point noise
        time = round(time, 4)

        if time == int(time):
            # Integer time: "1.0" not "1"
            return f"{time:.1f}"
        else:
            # Format with up to 4 decimal places, strip trailing zeros
            formatted = f"{time:.4f}".rstrip("0")
            # Ensure at least one decimal place
            if "." not in formatted:
                formatted += ".0"
            return formatted
