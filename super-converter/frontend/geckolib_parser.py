#!/usr/bin/env python3
"""
Super Architecture — GeckoLib Parser
======================================

Parse GeckoLib geo.json and animation.json files into the IR types defined
in core/types.py.

This module has two main functions:

  parse_geo_json(geo_data) -> ModelIR
      Parse a Bedrock geo.json into ModelIR.  Handles both the Bedrock
      format and the internal format.  Converts absolute pivots/origins
      to relative and applies Y offset for correct ground placement.

  parse_animation_json(anim_data, model_name) -> Dict[str, AnimationIR]
      Parse a GeckoLib animation.json into AnimationIR objects.  Uses
      AxisValue to track which axes are explicitly set vs defaulted,
      enabling correct carry-forward in the transform stage.

Key improvement over old AnimEngineV2 parser:
  The old parser couldn't distinguish "value = 0.0" from "no data at this
  time point".  The new parser uses AxisValue(explicit=True/False) to make
  this distinction clear, enabling correct carry-forward.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from core.types import (
    AXES,
    CHANNELS,
    DEFAULT_INTERPOLATION,
    VALID_LOOP_MODES,
    AnimationIR,
    AxisValue,
    BoneAnimationIR,
    BoneIR,
    CubeIR,
    KeyframeData,
    ModelIR,
)
from frontend.axis_tracker import AxisPresence, merge_per_axis_data

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Geo JSON parsing
# ---------------------------------------------------------------------------

def _compute_y_offset(bones: List[dict], abs_pivots: Dict[str, List[float]]) -> float:
    """Compute the Y offset needed to position the model so its bottom is at Y=0.

    In the .bbmodel format, Y=0 is the ground plane.  Models should be
    positioned so the lowest point of their geometry is at approximately Y=0.
    If the model extends below Y=0, it "sinks into the ground."
    If the model floats above Y=0, it appears to hover.

    This function examines all cube positions in the source geo.json (which
    uses absolute coordinates) and computes the minimum Y value.  The Y offset
    is -min_y, which shifts the entire model up (or down) so the bottom
    aligns with the ground plane.

    Args:
        bones: List of bone dicts from geo.json (with original absolute coords).
        abs_pivots: Dict mapping bone_name -> [x, y, z] absolute pivots.

    Returns:
        Y offset to add to root bone pivot Y (positive = shift up).
    """
    min_y = float('inf')

    for bone in bones:
        bone_name = bone.get('name', '')
        abs_pivot = abs_pivots.get(bone_name, [0.0, 0.0, 0.0])

        for cube in bone.get('cubes', []):
            try:
                # Cube origin is ABSOLUTE in the source geo.json
                origin = cube.get('origin', [0.0, 0.0, 0.0])
                size = cube.get('size', [0.0, 0.0, 0.0])

                # Validate that origin and size are list-like with numeric values
                oy = float(origin[1])
                sy = float(size[1])

                # Minimum Y of this cube (origin might not be the min corner)
                cube_min_y = min(oy, oy + sy)
                min_y = min(min_y, cube_min_y)
            except (IndexError, TypeError, ValueError):
                # Skip malformed cubes
                continue

    if min_y == float('inf') or abs(min_y) < 0.01:
        # No cubes found, or already at Y=0
        return 0.0

    # Shift model so bottom is at Y=0
    # If min_y < 0, y_offset > 0 (shift up to fix sinking)
    # If min_y > 0, y_offset < 0 (shift down to fix floating)
    return -min_y


def _parse_cube(cube_data: dict, abs_pivot: List[float]) -> Optional[CubeIR]:
    """Parse a single cube dict from geo.json into a CubeIR.

    Converts the cube origin from absolute to relative (relative to the
    bone's absolute pivot).  The size, UV, inflate, and mirror fields
    are passed through with appropriate type conversion.

    Args:
        cube_data: Raw cube dict from geo.json.
        abs_pivot: The bone's absolute pivot [x, y, z].

    Returns:
        CubeIR instance, or None if the cube data is invalid.
    """
    try:
        abs_origin = cube_data.get('origin', [0.0, 0.0, 0.0])
        size = cube_data.get('size', [0.0, 0.0, 0.0])

        # Convert absolute cube origin to relative (relative to bone pivot)
        # cube_rel = cube_abs - bone_abs_pivot
        rel_origin = (
            abs_origin[0] - abs_pivot[0],
            abs_origin[1] - abs_pivot[1],
            abs_origin[2] - abs_pivot[2],
        )

        # Size as tuple
        size_tuple = (float(size[0]), float(size[1]), float(size[2]))

        # Per-face UV mapping
        uv_data = cube_data.get('uv', {})
        uv: Dict[str, Dict[str, Any]] = {}
        if isinstance(uv_data, dict):
            # Per-face UV format: {"north": {"uv": [u,v], "uv_size": [w,h]}, ...}
            for face_name in ("north", "south", "east", "west", "up", "down"):
                face_data = uv_data.get(face_name)
                if isinstance(face_data, dict):
                    uv[face_name] = {
                        "uv": face_data.get("uv", [0.0, 0.0]),
                        "uv_size": face_data.get("uv_size", [0.0, 0.0]),
                    }

        inflate = float(cube_data.get('inflate', 0.0))
        mirror = bool(cube_data.get('mirror', False))

        return CubeIR(
            origin=rel_origin,
            size=size_tuple,
            uv=uv,
            inflate=inflate,
            mirror=mirror,
        )
    except (IndexError, TypeError, ValueError) as e:
        logger.warning("Failed to parse cube: %s", e)
        return None


def _parse_bone(
    bone_data: dict,
    abs_pivots: Dict[str, List[float]],
    parent_abs_pivot: Optional[List[float]],
    y_offset: float,
    is_root: bool,
) -> Optional[BoneIR]:
    """Parse a single bone dict from geo.json into a BoneIR.

    Converts the bone pivot from absolute to relative (relative to parent's
    absolute pivot for child bones).  Root bones keep their pivot with the
    Y offset applied.

    Args:
        bone_data: Raw bone dict from geo.json.
        abs_pivots: Dict mapping bone_name -> [x, y, z] absolute pivots
                    (original, before any conversion).
        parent_abs_pivot: Parent bone's absolute pivot, or None for root.
        y_offset: Y offset for ground placement (applied to root bones).
        is_root: True if this bone has no parent.

    Returns:
        BoneIR instance, or None if the bone data is invalid.
    """
    try:
        name = bone_data.get('name', '')
        if not name:
            logger.warning("Bone without name, skipping")
            return None

        parent = bone_data.get('parent')

        # Get the bone's original absolute pivot
        abs_pivot = abs_pivots.get(name, [0.0, 0.0, 0.0])

        # Convert pivot to relative
        if is_root:
            # Root bone: keep pivot but apply Y offset
            rel_pivot = (
                abs_pivot[0],
                abs_pivot[1] + y_offset,
                abs_pivot[2],
            )
        else:
            # Child bone: relative to parent
            if parent_abs_pivot is not None:
                rel_pivot = (
                    abs_pivot[0] - parent_abs_pivot[0],
                    abs_pivot[1] - parent_abs_pivot[1],
                    abs_pivot[2] - parent_abs_pivot[2],
                )
            else:
                # No parent pivot available, keep as-is
                rel_pivot = (abs_pivot[0], abs_pivot[1], abs_pivot[2])

        # Static rotation (some bones have a default rotation)
        rot = bone_data.get('rotation', [0.0, 0.0, 0.0])
        try:
            rotation = (
                float(rot[0]) if len(rot) > 0 else 0.0,
                float(rot[1]) if len(rot) > 1 else 0.0,
                float(rot[2]) if len(rot) > 2 else 0.0,
            )
        except (IndexError, TypeError, ValueError):
            rotation = (0.0, 0.0, 0.0)

        # Parse cubes using the bone's absolute pivot
        cubes: List[CubeIR] = []
        for cube_data in bone_data.get('cubes', []):
            cube_ir = _parse_cube(cube_data, abs_pivot)
            if cube_ir is not None:
                cubes.append(cube_ir)

        # Binding expression (rare, but some models use it)
        binding = bone_data.get('binding', '')

        return BoneIR(
            name=name,
            parent=parent,
            pivot=rel_pivot,
            rotation=rotation,
            cubes=cubes,
            binding=binding if isinstance(binding, str) else '',
        )
    except (IndexError, TypeError, ValueError) as e:
        logger.warning("Failed to parse bone '%s': %s", bone_data.get('name', '?'), e)
        return None


def parse_geo_json(geo_data: dict) -> ModelIR:
    """Parse a Bedrock geo.json into ModelIR.

    Handles both Bedrock format:
    {
        "format_version": "1.12.0",
        "minecraft:geometry": [{
            "description": { "identifier": "geometry.name", ... },
            "bones": [...]
        }]
    }

    And our internal format:
    {
        "model": {
            "identifier": "model.name",
            "texture_width": 256,
            "texture_height": 256,
            "bones": [...]
        }
    }

    CRITICAL: The source geo.json files from SRParasites use ABSOLUTE bone pivots
    and ABSOLUTE cube origins. We convert them to RELATIVE (relative to parent
    for pivots, relative to bone pivot for cube origins) during parsing.

    We also compute and apply Y offset to position the model correctly at Y=0.

    Args:
        geo_data: The raw geo.json dict.

    Returns:
        ModelIR instance with all bones and cubes in relative coordinates.
    """
    # Detect format and extract bones + metadata
    geom_list = geo_data.get('minecraft:geometry', [])

    if geom_list:
        # Bedrock format
        geom = geom_list[0]
        desc = geom.get('description', {})
        identifier = desc.get('identifier', 'model.unknown')
        if identifier.startswith('geometry.'):
            identifier = identifier[len('geometry.'):]
        texture_width = int(desc.get('texture_width', 64))
        texture_height = int(desc.get('texture_height', 32))
        bones_raw = geom.get('bones', [])
    elif 'model' in geo_data:
        # Internal format
        model = geo_data['model']
        identifier = model.get('identifier', 'model.unknown')
        texture_width = int(model.get('texture_width', 64))
        texture_height = int(model.get('texture_height', 32))
        bones_raw = model.get('bones', [])
    else:
        # Unknown format — try to extract what we can
        logger.warning("Unrecognized geo.json format, attempting best-effort parse")
        identifier = geo_data.get('identifier', 'model.unknown')
        texture_width = int(geo_data.get('texture_width', 64))
        texture_height = int(geo_data.get('texture_height', 32))
        bones_raw = geo_data.get('bones', [])

    if not bones_raw:
        return ModelIR(
            identifier=identifier,
            texture_width=texture_width,
            texture_height=texture_height,
            bones=[],
        )

    # ------------------------------------------------------------------
    # Step 1: Save all original absolute pivots BEFORE any conversion
    # ------------------------------------------------------------------
    abs_pivots: Dict[str, List[float]] = {}
    for bone in bones_raw:
        bone_name = bone.get('name', '')
        if bone_name:
            try:
                pivot = bone.get('pivot', [0.0, 0.0, 0.0])
                abs_pivots[bone_name] = [float(pivot[0]), float(pivot[1]), float(pivot[2])]
            except (IndexError, TypeError, ValueError):
                abs_pivots[bone_name] = [0.0, 0.0, 0.0]

    # Build bone map for parent lookup
    bone_map: Dict[str, dict] = {}
    for bone in bones_raw:
        bone_name = bone.get('name', '')
        if bone_name:
            bone_map[bone_name] = bone

    # ------------------------------------------------------------------
    # Step 2: Compute Y offset (while cube origins are still absolute)
    # ------------------------------------------------------------------
    y_offset = _compute_y_offset(bones_raw, abs_pivots)

    # ------------------------------------------------------------------
    # Step 3: Parse each bone into BoneIR (converting to relative coords)
    # ------------------------------------------------------------------
    bones_ir: List[BoneIR] = []
    for bone_data in bones_raw:
        bone_name = bone_data.get('name', '')
        if not bone_name:
            continue

        parent_name = bone_data.get('parent')
        is_root = parent_name is None
        parent_abs_pivot = abs_pivots.get(parent_name) if parent_name else None

        bone_ir = _parse_bone(
            bone_data, abs_pivots, parent_abs_pivot, y_offset, is_root
        )
        if bone_ir is not None:
            bones_ir.append(bone_ir)

    return ModelIR(
        identifier=identifier,
        texture_width=texture_width,
        texture_height=texture_height,
        bones=bones_ir,
    )


# ---------------------------------------------------------------------------
# Animation JSON parsing
# ---------------------------------------------------------------------------

def _axis_value_from_presence(
    ap: AxisPresence, axis: str
) -> AxisValue:
    """Create an AxisValue from an AxisPresence for a specific axis.

    If the axis was present in the source data, creates an explicit AxisValue.
    If not, creates a default AxisValue (for carry-forward in transform stage).

    Args:
        ap: The AxisPresence record for this time point.
        axis: "x", "y", or "z".

    Returns:
        AxisValue with explicit=True if source had data for this axis,
        AxisValue with explicit=False if source had no data.
    """
    if axis == "x":
        if ap.x_present:
            return AxisValue.explicit_val(ap.x_value)
        else:
            return AxisValue.default_val(0.0)
    elif axis == "y":
        if ap.y_present:
            return AxisValue.explicit_val(ap.y_value)
        else:
            return AxisValue.default_val(0.0)
    elif axis == "z":
        if ap.z_present:
            return AxisValue.explicit_val(ap.z_value)
        else:
            return AxisValue.default_val(0.0)
    else:
        return AxisValue.default_val(0.0)


def _build_keyframe_from_presence(
    ap: AxisPresence,
    channel: str,
) -> KeyframeData:
    """Build a KeyframeData from an AxisPresence record.

    This is where the explicit/default distinction is captured in the IR.
    Each axis gets an AxisValue that records whether it was explicitly present
    in the source data or is a default placeholder for carry-forward.

    Args:
        ap: The AxisPresence record for this time point.
        channel: "rotation", "position", or "scale".

    Returns:
        KeyframeData with AxisValue entries for each axis.
    """
    # Determine if any axis uses Molang at this time point
    is_molang = ap.has_molang()

    # Get per-axis AxisValues with explicit/default tracking
    x_av = _axis_value_from_presence(ap, "x")
    y_av = _axis_value_from_presence(ap, "y")
    z_av = _axis_value_from_presence(ap, "z")

    # Determine best easing from present axes
    best_easing = ap.best_easing()

    # Select interpolation based on channel and easing
    if best_easing != "linear":
        interpolation = "catmullrom"
    else:
        interpolation = DEFAULT_INTERPOLATION.get(channel, "linear")

    return KeyframeData(
        time=ap.time,
        channel=channel,
        x=x_av,
        y=y_av,
        z=z_av,
        easing=best_easing,
        interpolation=interpolation,
        is_molang=is_molang,
        molang_x=ap.x_molang,
        molang_y=ap.y_molang,
        molang_z=ap.z_molang,
    )


def _parse_channel(
    channel_data: dict,
    channel: str,
    bone_name: str,
    model_name: str,
) -> List[KeyframeData]:
    """Parse one channel (rotation/position/scale) of one bone.

    The channel data is per-axis:
        {
          "x": { "time_str": value_or_object, ... },
          "y": { "time_str": value_or_object, ... },
          "z": { "time_str": value_or_object, ... }
        }

    Where value_or_object is either:
        - A plain number
        - A string (Molang expression)
        - An object: {"vector": number, "easing": "easeOutSine"}

    We merge per-axis keyframes into unified keyframes at each unique time
    point, using AxisValue to track which axes were explicitly present vs
    defaulted.

    Args:
        channel_data: Per-axis time series dict (axis_name -> data).
        channel: "rotation", "position", or "scale".
        bone_name: Name of the bone (for logging).
        model_name: Model name (for logging).

    Returns:
        List of KeyframeData at each unique time point, sorted by time.
    """
    if not channel_data:
        return []

    # Detect global Molang axes (string values at the top level).
    # In GeckoLib: "y": "query.anim_time * 10" means y uses this Molang
    # expression for ALL time points, not just t=0.
    global_molang: Dict[str, str] = {}
    for axis in AXES:
        axis_val = channel_data.get(axis)
        if isinstance(axis_val, str):
            global_molang[axis] = axis_val

    # Build axis_data dict for the merge function
    axis_input: Dict[str, Any] = {}
    for axis in AXES:
        axis_val = channel_data.get(axis)
        if axis_val is not None:
            axis_input[axis] = axis_val

    if not axis_input:
        return []

    # Merge per-axis data into unified time points with explicit tracking
    presences = merge_per_axis_data(axis_input, channel, bone_name, model_name)

    if not presences:
        return []

    # Propagate global Molang to all time points.
    # A global Molang applies at every time point, so if an axis uses a
    # global Molang but a specific time point doesn't have data for it
    # (because only other axes had data at that time), we fill it in.
    if global_molang:
        for ap in presences:
            for axis_name, molang_expr in global_molang.items():
                if axis_name == "x" and not ap.x_present:
                    ap.x_present = True
                    ap.x_molang = molang_expr
                elif axis_name == "y" and not ap.y_present:
                    ap.y_present = True
                    ap.y_molang = molang_expr
                elif axis_name == "z" and not ap.z_present:
                    ap.z_present = True
                    ap.z_molang = molang_expr

    # Build KeyframeData from each AxisPresence
    keyframes: List[KeyframeData] = []
    for ap in presences:
        kf = _build_keyframe_from_presence(ap, channel)
        keyframes.append(kf)

    return keyframes


def _parse_bone_animation(
    bone_name: str,
    bone_anim: dict,
    model_name: str,
) -> BoneAnimationIR:
    """Parse one bone's animation data across all channels.

    Args:
        bone_name: Name of the bone.
        bone_anim: Dict with "rotation", "position", "scale" keys.
        model_name: Model name for logging.

    Returns:
        BoneAnimationIR with all keyframes (not yet sorted or transformed).
    """
    keyframes: List[KeyframeData] = []

    for channel in CHANNELS:
        channel_data = bone_anim.get(channel, {})
        if not channel_data:
            continue

        try:
            channel_keyframes = _parse_channel(
                channel_data, channel, bone_name, model_name
            )
            keyframes.extend(channel_keyframes)
        except Exception as e:
            logger.warning(
                "[%s] Failed to parse channel '%s' for bone '%s': %s",
                model_name, channel, bone_name, e,
            )
            continue

    # Sort by time, then channel for deterministic ordering
    keyframes.sort(key=lambda kf: (kf.time, kf.channel))

    return BoneAnimationIR(bone_name=bone_name, keyframes=keyframes)


def _parse_single_animation(
    anim_name: str,
    anim_data: dict,
    model_name: str,
) -> AnimationIR:
    """Parse one animation entry from the JSON.

    Args:
        anim_name: Animation identifier (e.g. "animation.kirin.idle").
        anim_data: The animation's dict with loop, animation_length, bones, etc.
        model_name: Model name for logging.

    Returns:
        AnimationIR instance.
    """
    # Loop mode
    loop_mode = anim_data.get("loop", "once")
    if isinstance(loop_mode, bool):
        # Some old GeckoLib versions use true/false instead of string
        loop_mode = "loop" if loop_mode else "once"
    if loop_mode not in VALID_LOOP_MODES:
        logger.debug(
            "[%s] Unknown loop mode '%s' in '%s', defaulting to 'once'",
            model_name, loop_mode, anim_name,
        )
        loop_mode = "once"

    # Animation length
    anim_length = 0.0
    raw_length = anim_data.get("animation_length")
    if raw_length is not None:
        try:
            anim_length = float(raw_length)
        except (ValueError, TypeError):
            logger.warning(
                "[%s] Invalid animation_length '%s' in '%s', defaulting to 0.0",
                model_name, raw_length, anim_name,
            )

    # Parse bones
    bones_data = anim_data.get("bones", {})
    bones: Dict[str, BoneAnimationIR] = {}

    for bone_name, bone_anim in bones_data.items():
        try:
            bone_anim_ir = _parse_bone_animation(bone_name, bone_anim, model_name)
            if bone_anim_ir.keyframes:
                bones[bone_name] = bone_anim_ir
        except Exception as e:
            logger.warning(
                "[%s] Failed to parse bone '%s' in '%s': %s",
                model_name, bone_name, anim_name, e,
            )
            continue

    return AnimationIR(
        name=anim_name,
        loop=loop_mode,
        length=anim_length,
        bones=bones,
    )


def parse_animation_json(
    anim_data: dict,
    model_name: str = "",
) -> Dict[str, AnimationIR]:
    """Parse a GeckoLib animation.json into AnimationIR objects.

    Key improvement: Track which axes are EXPLICITLY set vs defaulted.
    The old AnimEngineV2 parser couldn't distinguish "value = 0.0" from
    "no data at this time point".  The new parser uses AxisValue(explicit=True/False)
    to make this distinction clear, enabling correct carry-forward.

    GeckoLib animation.json format:
    {
        "format_version": "1.8.0",
        "animations": {
            "animation.model.idle": {
                "loop": "loop",
                "animation_length": 6.2832,
                "bones": {
                    "boneName": {
                        "rotation": {
                            "x": {"0.0": 0.0, "1.0": 30.0, ...},
                            "y": "query.anim_time * 5",  // Molang
                            "z": {"0.0": {"vector": 0.0, "easing": "easeOutSine"}, ...}
                        },
                        "position": {...},
                        "scale": {...}
                    }
                }
            }
        }
    }

    Per-axis values can be:
    - A number: 0.0
    - A string (Molang): "query.anim_time * 5"
    - A dict with time keys: {"0.0": value, "1.0": value, ...}
    - A dict with vector+easing: {"vector": 1.0, "easing": "easeOutSine"}

    Args:
        anim_data: The raw animation.json dict.
        model_name: Optional model name for logging context.

    Returns:
        Dict mapping animation_name -> AnimationIR.
    """
    result: Dict[str, AnimationIR] = {}
    animations = anim_data.get("animations", {})

    for anim_name, anim_entry in animations.items():
        try:
            parsed = _parse_single_animation(anim_name, anim_entry, model_name)
            result[anim_name] = parsed
        except Exception as e:
            logger.warning(
                "[%s] Failed to parse animation '%s': %s",
                model_name, anim_name, e,
            )
            continue

    return result
