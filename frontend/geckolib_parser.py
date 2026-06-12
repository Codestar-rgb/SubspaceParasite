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

def _get_root_rotation(bones: List[dict], abs_pivots: Dict[str, List[float]]) -> Tuple[float, float, float]:
    """Get the root bone's static rotation from the source data.

    For models with duplicate root bone entries (e.g., venkrol), we use the
    LAST entry's rotation, which typically contains the correct final rotation.

    Args:
        bones: List of bone dicts from geo.json.
        abs_pivots: Dict mapping bone_name -> [x, y, z] absolute pivots.

    Returns:
        Root bone rotation as (rx, ry, rz) in degrees, or (0, 0, 0).
    """
    root_rot = [0.0, 0.0, 0.0]
    for bone in bones:
        if bone.get('parent') is None:
            rot = bone.get('rotation')
            if rot is not None:
                try:
                    root_rot = [float(rot[0]) if len(rot) > 0 else 0.0,
                                float(rot[1]) if len(rot) > 1 else 0.0,
                                float(rot[2]) if len(rot) > 2 else 0.0]
                except (IndexError, TypeError, ValueError):
                    pass
    return tuple(root_rot)


def _apply_rotation_to_point(
    point: Tuple[float, float, float],
    pivot: Tuple[float, float, float],
    rotation: Tuple[float, float, float],
) -> Tuple[float, float, float]:
    """Apply a rotation to a point around a pivot.

    Uses the ZYX (GeckoLib/Blockbench) rotation convention:
    R = Rz(rz) * Ry(ry) * Rx(rx)

    Args:
        point: The point to rotate (x, y, z).
        pivot: The pivot point to rotate around (px, py, pz).
        rotation: Rotation angles in degrees (rx, ry, rz).

    Returns:
        Rotated point (x, y, z).
    """
    from core.quaternion import Quaternion

    if not rotation or all(abs(r) < 1e-10 for r in rotation):
        return point

    # Translate to pivot-relative
    px, py, pz = point[0] - pivot[0], point[1] - pivot[1], point[2] - pivot[2]

    # Build rotation quaternion (ZYX convention = GeckoLib/Blockbench)
    q = Quaternion.from_euler_xyz(rotation[0], rotation[1], rotation[2], degrees=True)

    # Apply rotation
    rx, ry, rz = q.rotate_vector(px, py, pz)

    # Translate back
    return (rx + pivot[0], ry + pivot[1], rz + pivot[2])


def _apply_axis_transforms(
    bones: List[dict],
    abs_pivots: Dict[str, List[float]],
) -> None:
    """Apply axis reflection transforms for correct .bbmodel output.

    The source geo.json models from SRParasites were originally MC 1.12.2 Java
    models converted to GeckoLib format. These models use a convention where the
    root bone has a -180° Y rotation, which effectively mirrors the model.

    To produce correct .bbmodel output that matches the reference converter:
      - Negate X of all bone pivots: (x, y, z) → (-x, y, z)
      - Negate X and Y of all bone rotations: (rx, ry, rz) → (-rx, -ry, rz)
      - Negate both from_x and to_x corners of ALL cube positions
      - Keep ALL rotations (including ±180°) — do NOT bake them into geometry.
        Blockbench handles rotation during rendering, so baking is unnecessary
        and causes UV face orientation issues (east/west swap, up/down flip).

    Previously, pure ±180° single-axis rotations were "baked" into cube positions
    and the bone rotation was zeroed. This caused three critical bugs:
      1. Root bone 180° Y rotation was zeroed → model faces wrong direction
      2. Child bone 180° rotations were baked but UV face swaps were missing
         → textures appear inverted ("本末倒置")
      3. Baked geometry + missing UV swaps → parts appear disconnected ("悬空")

    The fix: keep all rotations as-is after the axis transform. Blockbench
    applies rotations during rendering, correctly orienting all faces.

    Args:
        bones: List of bone dicts from geo.json (modified in-place).
        abs_pivots: Dict mapping bone_name -> [x, y, z] absolute pivots
                    (modified in-place).
    """
    # Transform absolute pivots: negate X
    for bone_name in abs_pivots:
        p = abs_pivots[bone_name]
        abs_pivots[bone_name] = [-p[0], p[1], p[2]]

    # Transform bone data
    for bone in bones:
        # Transform rotation: (rx, ry, rz) → (-rx, -ry, rz)
        # Applied uniformly to ALL bones, including ±180° rotations.
        rot = bone.get('rotation')
        if rot is not None:
            try:
                bone['rotation'] = [
                    -float(rot[0]) if len(rot) > 0 else 0.0,
                    -float(rot[1]) if len(rot) > 1 else 0.0,
                    float(rot[2]) if len(rot) > 2 else 0.0,
                ]
            except (IndexError, TypeError, ValueError):
                pass

        # Transform cube origins: negate X only
        for cube in bone.get('cubes', []):
            origin = cube.get('origin')
            size = cube.get('size')
            if origin is not None and size is not None:
                try:
                    ox, oy, oz = float(origin[0]), float(origin[1]), float(origin[2])
                    sx, sy, sz = float(size[0]), float(size[1]), float(size[2])

                    # Compute absolute from/to corners
                    from_x, from_y, from_z = ox, oy, oz
                    to_x, to_y, to_z = ox + sx, oy + sy, oz + sz

                    # Negate X of both corners (applied to ALL bones)
                    from_x, to_x = -from_x, -to_x

                    # Ensure from <= to (required by .bbmodel)
                    if from_x > to_x:
                        from_x, to_x = to_x, from_x
                    if from_y > to_y:
                        from_y, to_y = to_y, from_y
                    if from_z > to_z:
                        from_z, to_z = to_z, from_z

                    cube['origin'] = [from_x, from_y, from_z]
                    # Size is recomputed from the corners
                    cube['size'] = [to_x - from_x, to_y - from_y, to_z - from_z]
                except (IndexError, TypeError, ValueError):
                    pass


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
    absolute pivot for child bones).  Root bones keep their pivot directly
    (no Y offset — the model uses original coordinates from the source).

    Args:
        bone_data: Raw bone dict from geo.json.
        abs_pivots: Dict mapping bone_name -> [x, y, z] absolute pivots
                    (after axis transforms).
        parent_abs_pivot: Parent bone's absolute pivot, or None for root.
        y_offset: Unused (kept for API compatibility, always 0.0).
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

        # Get the bone's absolute pivot (already axis-transformed)
        abs_pivot = abs_pivots.get(name, [0.0, 0.0, 0.0])

        # Convert pivot to relative
        if is_root:
            # Root bone: keep pivot directly (no Y offset)
            rel_pivot = (abs_pivot[0], abs_pivot[1], abs_pivot[2])
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
    # Step 1: Deduplicate bones by name (CRITICAL FIX)
    # ------------------------------------------------------------------
    # Some source models (e.g., venkrol) have DUPLICATE bone entries with
    # the same name but different rotations. This was causing:
    #   - Two groups with the same name and UUID in the .bbmodel output
    #   - The outliner referencing only one of them
    #   - The wrong rotation being applied
    # We merge duplicate entries: combine cubes and use the LAST entry's
    # rotation (which is typically the correct one).
    deduped_bones: Dict[str, dict] = {}
    for bone in bones_raw:
        bone_name = bone.get('name', '')
        if not bone_name:
            continue
        if bone_name in deduped_bones:
            # Merge: combine cubes, keep the LAST rotation (more specific)
            existing = deduped_bones[bone_name]
            # Combine cubes
            existing_cubes = existing.get('cubes', [])
            new_cubes = bone.get('cubes', [])
            if new_cubes:
                existing['cubes'] = existing_cubes + new_cubes
            # Use the new entry's rotation if it's more specific
            new_rot = bone.get('rotation')
            if new_rot is not None:
                existing['rotation'] = new_rot
            logger.debug(
                "Merged duplicate bone '%s': %d + %d cubes",
                bone_name, len(existing_cubes), len(new_cubes),
            )
        else:
            deduped_bones[bone_name] = dict(bone)  # shallow copy

    bones_deduped = list(deduped_bones.values())

    # ------------------------------------------------------------------
    # Step 2: Save all original absolute pivots BEFORE any conversion
    # ------------------------------------------------------------------
    abs_pivots: Dict[str, List[float]] = {}
    for bone in bones_deduped:
        bone_name = bone.get('name', '')
        if bone_name:
            try:
                pivot = bone.get('pivot', [0.0, 0.0, 0.0])
                abs_pivots[bone_name] = [float(pivot[0]), float(pivot[1]), float(pivot[2])]
            except (IndexError, TypeError, ValueError):
                abs_pivots[bone_name] = [0.0, 0.0, 0.0]

    # Build bone map for parent lookup
    bone_map: Dict[str, dict] = {b.get('name', ''): b for b in bones_deduped}

    # ------------------------------------------------------------------
    # Step 3: Apply axis reflection transforms (CRITICAL FIX)
    # ------------------------------------------------------------------
    # The source geo.json models from SRParasites were originally MC 1.12.2
    # Java models. They use a coordinate convention where X needs to be
    # negated and rotation X/Y need to be negated for correct Blockbench
    # rendering. No Y offset is applied — models use original coordinates.
    _apply_axis_transforms(bones_deduped, abs_pivots)

    # ------------------------------------------------------------------
    # Step 4: Parse each bone into BoneIR (converting to relative coords)
    # ------------------------------------------------------------------
    bones_ir: List[BoneIR] = []
    for bone_data in bones_deduped:
        bone_name = bone_data.get('name', '')
        if not bone_name:
            continue

        parent_name = bone_data.get('parent')
        is_root = parent_name is None
        parent_abs_pivot = abs_pivots.get(parent_name) if parent_name else None

        bone_ir = _parse_bone(
            bone_data, abs_pivots, parent_abs_pivot, 0.0, is_root
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


def _apply_animation_axis_transforms(anim_ir: AnimationIR) -> AnimationIR:
    """Apply axis reflection transforms to animation data.

    The model's static bone rotations were transformed as (rx, ry, rz) → (-rx, -ry, rz)
    and positions as (x, y, z) → (-x, y, z). Animation values represent OFFSETS from
    the static pose. For the animation to produce correct visual results in the
    transformed coordinate system, the same axis transforms must be applied:

      - Rotation: (rx, ry, rz) → (-rx, -ry, rz)
        Reasoning: total_rot = static_rot + anim_offset. After transform:
        (-static_rx, -static_ry, static_rz) + anim_offset_transformed
        = (-total_rx, -total_ry, total_rz), so anim_offset_transformed = (-anim_rx, -anim_ry, anim_rz)

      - Position: (px, py, pz) → (-px, py, pz)
        Reasoning: same mirror transform as model positions (negate X)

      - Scale: no transform needed (multiplicative, unaffected by mirror)

    Molang expressions are NOT transformed — they are runtime-evaluated strings
    that Blockbench/GeckoLib interprets as-is.

    Args:
        anim_ir: The parsed AnimationIR (untransformed).

    Returns:
        New AnimationIR with axis-transformed animation values.
    """
    transformed_bones: Dict[str, BoneAnimationIR] = {}

    for bone_name, bone_anim in anim_ir.bones.items():
        transformed_kfs: List[KeyframeData] = []

        for kf in bone_anim.keyframes:
            # Determine transform per channel
            if kf.channel == "rotation":
                # Rotation: (rx, ry, rz) → (-rx, -ry, rz)
                # Only transform explicit numeric values, not Molang
                x_val = -kf.x.value if (kf.x.explicit and not kf.molang_x) else kf.x.value
                y_val = -kf.y.value if (kf.y.explicit and not kf.molang_y) else kf.y.value
                z_val = kf.z.value  # Z unchanged

                new_x = AxisValue(value=x_val, explicit=kf.x.explicit)
                new_y = AxisValue(value=y_val, explicit=kf.y.explicit)
                new_z = AxisValue(value=z_val, explicit=kf.z.explicit)

            elif kf.channel == "position":
                # Position: (px, py, pz) → (-px, py, pz)
                # Only transform explicit numeric values, not Molang
                x_val = -kf.x.value if (kf.x.explicit and not kf.molang_x) else kf.x.value
                y_val = kf.y.value  # Y unchanged
                z_val = kf.z.value  # Z unchanged

                new_x = AxisValue(value=x_val, explicit=kf.x.explicit)
                new_y = AxisValue(value=y_val, explicit=kf.y.explicit)
                new_z = AxisValue(value=z_val, explicit=kf.z.explicit)

            else:
                # Scale or other: no transform
                new_x = kf.x
                new_y = kf.y
                new_z = kf.z

            transformed_kfs.append(KeyframeData(
                time=kf.time,
                channel=kf.channel,
                x=new_x,
                y=new_y,
                z=new_z,
                easing=kf.easing,
                interpolation=kf.interpolation,
                is_molang=kf.is_molang,
                molang_x=kf.molang_x,
                molang_y=kf.molang_y,
                molang_z=kf.molang_z,
            ))

        transformed_bones[bone_name] = BoneAnimationIR(
            bone_name=bone_name,
            keyframes=transformed_kfs,
        )

    return AnimationIR(
        name=anim_ir.name,
        loop=anim_ir.loop,
        length=anim_ir.length,
        bones=transformed_bones,
        period=anim_ir.period,
    )


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
        AnimationIR instance with axis transforms applied.
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

    anim_ir = AnimationIR(
        name=anim_name,
        loop=loop_mode,
        length=anim_length,
        bones=bones,
    )

    # Apply axis reflection transforms to animation values
    # (rotation: negate X/Y, position: negate X — same as model transforms)
    anim_ir = _apply_animation_axis_transforms(anim_ir)

    return anim_ir


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
