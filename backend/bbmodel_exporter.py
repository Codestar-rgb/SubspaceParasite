#!/usr/bin/env python3
"""
Super Architecture — BBModel Exporter
======================================

Export ModelIR and AnimationIR to the Blockbench .bbmodel format.

The .bbmodel format is a JSON file containing model geometry, textures,
and animations in a single document. Key structural differences from
geo.json:

  - UV format:  {uv: [u1, v1, u2, v2], texture: idx}
                (vs geo.json's {uv:[u,v], uv_size:[w,h]})
  - Outliner:   Hierarchical bone tree with UUID references to elements
  - Elements:   Cubes with "from"/"to" (min/max corners) and "origin" (pivot)
  - Textures:   Embedded as base64 data URIs
  - Animations: Keyframes grouped per bone with channel/data_points structure

CRITICAL: Coordinate System for .bbmodel
=========================================
  .bbmodel uses ABSOLUTE world-space coordinates for element positions and
  bone pivots (origin). This is different from the IR which stores
  bone-local (relative to parent) coordinates.

  Element from/to: ABSOLUTE world position (bone-local origin + absolute pivot)
  Element origin:  ABSOLUTE pivot of the bone (rotation center)
  Group origin:    ABSOLUTE pivot of the bone

  Absolute Pivot Computation:
    - Root: abs_pivot = root.pivot (no Y offset applied)
    - Children: abs_pivot = parent_abs_pivot + child.pivot (simple addition)

  The simple addition (no FK rotation) is correct because:
    1. The source geo.json pivots are positional differences
    2. .bbmodel FROM/TO coordinates are in pre-rotation world space
    3. Blockbench applies rotations during rendering (no double-rotation)

  Axis transforms (applied in the parser, not the exporter):
    - All X coordinates are negated: (x, y, z) → (-x, y, z)
    - Rotation X and Y are negated: (rx, ry, rz) → (-rx, -ry, rz)
    - No Y offset is applied — models use original coordinates
    - No UV face swaps are needed after the axis transforms
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time as _time
from typing import Any, Dict, List, Optional, Tuple

from core.types import (
    AXES,
    CHANNELS,
    AnimationIR,
    AxisValue,
    BoneAnimationIR,
    BoneIR,
    CubeIR,
    KeyframeData,
    ModelIR,
)
from core.math_utils import (
    generate_uuid,
    round_for_bbmodel,
)

logger = logging.getLogger(__name__)


# Face direction mapping order used in bbmodel
FACE_NAMES: Tuple[str, ...] = ("north", "east", "south", "west", "up", "down")


class BBModelExporter:
    """Export ModelIR and AnimationIR to .bbmodel format.

    Usage:
        exporter = BBModelExporter()
        bbmodel = exporter.export(model_ir, animations=[...], texture_path="model.png")
        exporter.save(bbmodel, "output.bbmodel")
    """

    # ========================================================================
    # Public API
    # ========================================================================

    def export(
        self,
        model: ModelIR,
        animations: Optional[List[AnimationIR]] = None,
        texture_path: Optional[str] = None,
        texture_name: str = "model",
        namespace: str = "srparasites",
        model_metadata=None,
    ) -> dict:
        """Generate a .bbmodel project dict from ModelIR and AnimationIR.

        Args:
            model: The ModelIR instance from the frontend parser.
            animations: Optional list of AnimationIR instances from the
                        engine pipeline.  If None or empty, the output
                        will have an empty animations list.
            texture_path: Path to a texture PNG file to embed as base64.
                          If None, the texture entry will have an empty
                          source string (no embedded image).
            texture_name: Name for the texture entry in the .bbmodel.
            namespace: Resource namespace for texture metadata.
            model_metadata: Optional ModelMetadata (v6.2) for head tracking
                            injection. If provided and has head_tracking,
                            a Molang-driven head_track animation is appended.

        Returns:
            Dict representing the .bbmodel structure, ready for
            json.dumps() or self.save().
        """
        bones = model.bones

        # Extract short name from identifier like "geometry.kirin" -> "kirin"
        identifier = model.identifier
        short_name = identifier.split(".")[-1] if "." in identifier else identifier
        geometry_name = f"geometry.{short_name}"

        now = int(_time.time())

        # ------------------------------------------------------------------
        # Phase 1: Compute absolute world-space pivots for all bones
        # ------------------------------------------------------------------
        abs_pivots = self._compute_absolute_pivots(bones)

        # ------------------------------------------------------------------
        # Phase 2: Assign UUIDs to all bones and cubes
        # ------------------------------------------------------------------
        bone_uuids: Dict[str, str] = {}
        element_uuids: Dict[Tuple[str, int], str] = {}

        for bone_idx, bone in enumerate(bones):
            # Use name + index to ensure uniqueness even if bone names
            # were not properly deduplicated upstream
            if bone.name in bone_uuids:
                bone_uuids[bone.name] = generate_uuid()  # Regenerate for collision
            else:
                bone_uuids[bone.name] = generate_uuid()
            for cube_idx in range(len(bone.cubes)):
                element_uuids[(bone.name, cube_idx)] = generate_uuid()

        # ------------------------------------------------------------------
        # Phase 3: Build elements (cubes) list
        # ------------------------------------------------------------------
        elements = self._build_elements(bones, abs_pivots, element_uuids)

        # ------------------------------------------------------------------
        # Phase 4: Build groups (flat array) and outliner (tree)
        # ------------------------------------------------------------------
        groups, outliner = self._build_groups_and_outliner(
            bones, bone_uuids, element_uuids, abs_pivots
        )

        # ------------------------------------------------------------------
        # Phase 5: Build textures list (may override tex dimensions from PNG)
        # ------------------------------------------------------------------
        textures, tex_width, tex_height = self._build_textures(
            texture_path, texture_name, namespace,
            model.texture_width, model.texture_height,
        )

        # ------------------------------------------------------------------
        # Phase 6: Serialize animations (with bone UUID mapping)
        # ------------------------------------------------------------------
        serialized_anims = self._serialize_animations(animations or [], bone_uuids)

        # ------------------------------------------------------------------
        # Phase 6b (v6.2): Inject head tracking animation (Molang)
        # ------------------------------------------------------------------
        if model_metadata is not None and model_metadata.head_tracking:
            try:
                from engine.head_tracking_injector import build_head_track_animation
                head_track = build_head_track_animation(model_metadata, bone_uuids)
                if head_track:
                    serialized_anims.append(head_track)
            except Exception as e:
                logger.warning("head_track injection failed: %s", e)

        # ------------------------------------------------------------------
        # Phase 6c (v6.3): Inject runtime behavior animations (Molang)
        #   - attack_overlay (blend_weight fade)
        #   - body_bob (floor-timer driven)
        #   - visibility (isHidden scale-to-0 workaround)
        #   - walk blend_weight (limbSwingAmount² scaling)
        # ------------------------------------------------------------------
        if model_metadata is not None:
            try:
                from engine.runtime_behavior_injector import inject_all_runtime_behaviors
                serialized_anims, rb_stats = inject_all_runtime_behaviors(
                    serialized_anims, model_metadata, bone_uuids
                )
                if any(rb_stats.values()):
                    logger.debug("runtime_behaviors: %s", rb_stats)
            except Exception as e:
                logger.warning("runtime_behavior injection failed: %s", e)

        # ------------------------------------------------------------------
        # Assemble the final .bbmodel structure
        # ------------------------------------------------------------------
        bbmodel = {
            "meta": {
                "format_version": "5.0",
                "model_format": "bedrock",
                "model_identifier": short_name,
                "creation_time": now,
                "modification_time": now,
                "box_uv": False,
                "face_size": [1, 1],
            },
            "name": short_name,
            "geometry_name": geometry_name,
            "model_identifier": short_name,
            "visible_box": [80, -50, 5],
            "variable_placeholders": "",
            "variable_placeholder_buttons": [],
            "resolution": {
                "width": tex_width,
                "height": tex_height,
            },
            "elements": elements,
            "groups": groups,
            "outliner": outliner,
            "textures": textures,
            "animations": serialized_anims,
        }

        return bbmodel

    def save(self, bbmodel: dict, filepath: str) -> None:
        """Save the .bbmodel dict to a JSON file.

        Args:
            bbmodel: The .bbmodel structure dict from export().
            filepath: Output file path (should end in .bbmodel).
        """
        parent_dir = os.path.dirname(filepath)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(bbmodel, f, indent=2, ensure_ascii=False)

    # ========================================================================
    # Absolute Pivot Computation
    # ========================================================================

    def _compute_absolute_pivots(
        self, bones: List[BoneIR]
    ) -> Dict[str, List[float]]:
        """Compute absolute world-space pivots for all bones.

        Uses simple positional addition (no FK rotation):
          child_abs = parent_abs + child_pivot_relative

        This is correct because:
          1. The source geo.json pivots are positional differences
          2. .bbmodel FROM/TO coordinates are in pre-rotation world space
          3. Blockbench applies rotations during rendering

        Args:
            bones: List of BoneIR instances (parent before child).

        Returns:
            Dict mapping bone_name -> [abs_x, abs_y, abs_z].
        """
        # Build bone name -> BoneIR lookup
        bone_map: Dict[str, BoneIR] = {b.name: b for b in bones}

        # Build parent -> children mapping
        children_map: Dict[str, List[str]] = {}
        for bone in bones:
            if bone.parent is not None:
                if bone.parent not in children_map:
                    children_map[bone.parent] = []
                children_map[bone.parent].append(bone.name)

        abs_pivots: Dict[str, List[float]] = {}

        # Iterative computation using stack
        def compute_abs_iterative(start_bone: str, parent_abs: List[float]) -> None:
            stack = [(start_bone, parent_abs)]
            visited: set = set()

            while stack:
                bone_name, p_abs = stack.pop()

                if bone_name in abs_pivots or bone_name in visited:
                    continue
                visited.add(bone_name)

                bone = bone_map[bone_name]
                pivot = list(bone.pivot)

                # Simple addition: child_abs = parent_abs + child_pivot_relative
                abs_pivot = [p_abs[i] + pivot[i] for i in range(3)]
                abs_pivots[bone_name] = abs_pivot

                # Push children onto stack
                for child_name in children_map.get(bone_name, []):
                    stack.append((child_name, abs_pivot))

        # Find root bone(s) — bones without a parent
        root_bones = [b for b in bones if b.parent is None]

        for root_bone in root_bones:
            root_abs = list(root_bone.pivot)
            abs_pivots[root_bone.name] = root_abs

            for child_name in children_map.get(root_bone.name, []):
                compute_abs_iterative(child_name, root_abs)

        # Handle bones that still don't have absolute pivots
        # (orphaned due to broken cycles or missing parent references)
        fallback_root = [0.0, 24.0, 0.0]
        for bone_name in abs_pivots:
            if "root" in bone_name.lower():
                fallback_root = abs_pivots[bone_name]
                break

        for bone in bones:
            if bone.name not in abs_pivots:
                pivot = list(bone.pivot)
                if bone.parent and bone.parent in abs_pivots:
                    parent_abs = abs_pivots[bone.parent]
                    abs_pivots[bone.name] = [
                        parent_abs[i] + pivot[i] for i in range(3)
                    ]
                else:
                    abs_pivots[bone.name] = [
                        fallback_root[i] + pivot[i] for i in range(3)
                    ]

        return abs_pivots

    # ========================================================================
    # Elements (Cubes) Builder
    # ========================================================================

    def _build_elements(
        self,
        bones: List[BoneIR],
        abs_pivots: Dict[str, List[float]],
        element_uuids: Dict[Tuple[str, int], str],
    ) -> list:
        """Build the flat elements list from all bones' cubes.

        Each element has:
          - from/to: ABSOLUTE world-space min/max corners
            from[i] = cube_origin[i] + abs_pivot[i]
            to[i] = cube_origin[i] + cube_size[i] + abs_pivot[i]
          - origin: bone's absolute pivot (rotation center)
          - faces: UV data with N↔S swap from
            coords.convert_uv_face_north_south()
          - For mirrored cubes: geometric X-mirror + W↔E UV swap

        Args:
            bones: List of BoneIR instances.
            abs_pivots: Dict mapping bone_name -> [abs_x, abs_y, abs_z].
            element_uuids: Dict mapping (bone_name, cube_idx) -> uuid.

        Returns:
            List of element dicts in .bbmodel format.
        """
        elements = []
        color_cycle = 0

        for bone in bones:
            abs_pivot = abs_pivots.get(bone.name, [0.0, 0.0, 0.0])

            for cube_idx, cube in enumerate(bone.cubes):
                elem_uuid = element_uuids[(bone.name, cube_idx)]
                origin = cube.origin
                size = cube.size
                inflate = cube.inflate
                mirror = cube.mirror

                # Convert from bone-local to ABSOLUTE world space
                from_pos = [
                    float(origin[0]) + abs_pivot[0],
                    float(origin[1]) + abs_pivot[1],
                    float(origin[2]) + abs_pivot[2],
                ]
                to_pos = [
                    float(origin[0]) + float(size[0]) + abs_pivot[0],
                    float(origin[1]) + float(size[1]) + abs_pivot[1],
                    float(origin[2]) + float(size[2]) + abs_pivot[2],
                ]

                # Geometric X-mirror for mirrored cubes.
                # Mirror around the bone's absolute pivot X coordinate.
                # Original: [ox+px, ox+w+px] -> Mirrored: [2*px-(ox+w+px), 2*px-(ox+px)]
                #         = [px-ox-w, px-ox]
                if mirror:
                    px = abs_pivot[0]
                    from_x_mirrored = 2 * px - (float(origin[0]) + float(size[0]) + px)
                    to_x_mirrored = 2 * px - (float(origin[0]) + px)
                    from_pos[0] = from_x_mirrored
                    to_pos[0] = to_x_mirrored
                    # Ensure from[0] <= to[0] (required by .bbmodel format)
                    if from_pos[0] > to_pos[0]:
                        from_pos[0], to_pos[0] = to_pos[0], from_pos[0]

                # v6.9.10: Bake PURE single-axis 180-degree rotations into cube positions.
                # Only apply when the rotation is exactly one axis = ±180 and others = 0.
                # This matches the reference converter behavior:
                #   skin_1 [0,0,180] -> bake Y mirror, zero Z rotation
                #   skin_2 [0,-180,0] -> bake Z mirror, zero Y rotation
                # Combined rotations like [-180,0,180] are preserved (not baked).
                bone_rot = bone.rotation
                try:
                    rx = float(bone_rot[0]) if len(bone_rot) > 0 else 0.0
                    ry = float(bone_rot[1]) if len(bone_rot) > 1 else 0.0
                    rz = float(bone_rot[2]) if len(bone_rot) > 2 else 0.0
                except (TypeError, IndexError):
                    rx = ry = rz = 0.0

                def _is_180(a):
                    return abs(abs(a) - 180.0) < 0.5
                def _is_zero(a):
                    return abs(a) < 0.5

                # Pure single-axis 180: exactly one axis is ±180, others are 0
                pure_x180 = _is_180(rx) and _is_zero(ry) and _is_zero(rz)
                pure_y180 = _is_180(ry) and _is_zero(rx) and _is_zero(rz)
                pure_z180 = _is_180(rz) and _is_zero(rx) and _is_zero(ry)

                if pure_y180 or pure_z180 or pure_x180:
                    px, py, pz = float(abs_pivot[0]), float(abs_pivot[1]), float(abs_pivot[2])
                    if pure_y180:
                        # Y=180: mirror Z around pivot Z (X already mirrored by parser)
                        from_pos[2] = 2 * pz - from_pos[2]
                        to_pos[2] = 2 * pz - to_pos[2]
                        if from_pos[2] > to_pos[2]:
                            from_pos[2], to_pos[2] = to_pos[2], from_pos[2]
                    elif pure_z180:
                        # Z=180: mirrors X and Y. Parser negated X, but for Z=180
                        # bones the X mirror should be around the pivot (not just
                        # negate). Mirror X around pivot X to get correct position.
                        from_pos[0] = 2 * px - from_pos[0]
                        to_pos[0] = 2 * px - to_pos[0]
                        if from_pos[0] > to_pos[0]:
                            from_pos[0], to_pos[0] = to_pos[0], from_pos[0]
                    elif pure_x180:
                        # X=180: mirror Y and Z around pivots (X already mirrored by parser)
                        from_pos[1] = 2 * py - from_pos[1]
                        to_pos[1] = 2 * py - to_pos[1]
                        if from_pos[1] > to_pos[1]:
                            from_pos[1], to_pos[1] = to_pos[1], from_pos[1]
                        from_pos[2] = 2 * pz - from_pos[2]
                        to_pos[2] = 2 * pz - to_pos[2]
                        if from_pos[2] > to_pos[2]:
                            from_pos[2], to_pos[2] = to_pos[2], from_pos[2]

                # Element origin = bone's absolute pivot (rotation center)
                bb_origin = [float(abs_pivot[0]), float(abs_pivot[1]), float(abs_pivot[2])]

                # Build faces with UV conversion (includes 180-deg east/west swap)
                faces = self._convert_faces(cube.uv, mirror=mirror, bone_rotation=bone.rotation)

                element = {
                    "name": f"{bone.name}_c{cube_idx}",
                    "box_uv": False,
                    "render_order": "default",
                    "locked": False,
                    "export": True,
                    "scope": 0,
                    "allow_mirror_modeling": True,
                    "from": from_pos,
                    "to": to_pos,
                    "autouv": 0,
                    "color": color_cycle % 8,
                    "inflate": float(inflate),
                    "mirror_uv": mirror,
                    "rotation": [0.0, 0.0, 0.0],
                    "origin": bb_origin,
                    "uv_offset": [0, 0],
                    "faces": faces,
                    "type": "cube",
                    "uuid": elem_uuid,
                }

                elements.append(element)
                color_cycle += 1

        return elements

    def _convert_faces(
        self, uv_data: Dict[str, Any], mirror: bool = False,
        bone_rotation: tuple = (0.0, 0.0, 0.0),
    ) -> dict:
        """Convert face UV data from geo.json to .bbmodel format.

        geo.json:  { "north": { "uv": [u, v], "uv_size": [w, h] }, ... }
        bbmodel:   { "north": { "uv": [u1, v1, u2, v2], "texture": 0 }, ... }

        CRITICAL: UV Coordinate Normalization
        ======================================
        The source geo.json often has NEGATIVE uv_size values (especially on
        up/down faces), which means the texture is flipped. For example:
          uv=[29, 10], uv_size=[-19, -10]

        Naively computing [u, v, u+w, v+h] gives [29, 10, 10, 0] which has
        u1 > u2 and v1 > v2. The .bbmodel format requires UV coordinates as
        a proper rectangle [u1, v1, u2, v2] where u1 ≤ u2 and v1 ≤ v2.

        The fix: normalize UV coordinates by taking min/max of both corners.
        This produces the correct UV rectangle regardless of uv_size sign:
          [29, 10, -19, -10] → normalized: [10, 0, 29, 10]

        No UV face swaps (N↔S, E↔W) are applied. With the axis transform
        fix (keeping ±180° rotations instead of baking them), Blockbench
        handles face orientation correctly during rendering.

        For faces without UV data: set texture to -1, uv to [0,0,0,0].

        Args:
            uv_data: Dict mapping face_name -> {uv: [u,v], uv_size: [w,h]}.
            mirror: Whether the cube has the mirror flag set.

        Returns:
            Dict mapping face_name -> {uv: [u1,v1,u2,v2], texture: int}.
        """
        # Convert format from geo.json to .bbmodel with UV normalization
        faces: Dict[str, dict] = {}

        for face_name in FACE_NAMES:
            face_uv = uv_data.get(face_name)

            if face_uv is not None and isinstance(face_uv, dict):
                u = float(face_uv.get("uv", [0.0, 0.0])[0])
                v = float(face_uv.get("uv", [0.0, 0.0])[1])
                w = float(face_uv.get("uv_size", [0.0, 0.0])[0])
                h = float(face_uv.get("uv_size", [0.0, 0.0])[1])

                # Normalize UV coordinates: ensure u1 ≤ u2 and v1 ≤ v2
                # This handles negative uv_size values (texture flipping)
                u1, u2 = (u, u + w) if w >= 0 else (u + w, u)
                v1, v2 = (v, v + h) if h >= 0 else (v + h, v)

                faces[face_name] = {
                    "uv": [u1, v1, u2, v2],
                    "texture": 0,
                }
            else:
                # Face without UV data — assign no texture
                faces[face_name] = {
                    "uv": [0.0, 0.0, 0.0, 0.0],
                    "texture": -1,
                }

        # v6.9.8: Face UV swap for 180-degree bone rotations.
        # When a bone has 180-degree rotation around Z, the east/west faces
        # swap physically. Blockbench does NOT automatically swap the UV
        # mapping, so we must swap it manually.
        # Z=180: east<->west, up<->down
        # Y=180: east<->west, north<->south
        # X=180: north<->south, up<->down
        try:
            rx = float(bone_rotation[0]) if len(bone_rotation) > 0 else 0.0
            ry = float(bone_rotation[1]) if len(bone_rotation) > 1 else 0.0
            rz = float(bone_rotation[2]) if len(bone_rotation) > 2 else 0.0
        except (TypeError, IndexError):
            rx = ry = rz = 0.0

        def _is_180(angle):
            return abs(abs(angle) - 180.0) < 0.5
        def _is_zero(angle):
            return abs(angle) < 0.5

        # v6.9.10: Swap east/west UVs ONLY for pure single-axis 180 rotations.
        # Combined rotations like [180,0,-90] or [-180,0,180] do NOT need swap
        # (verified against heblu-SubSRP reference: only skin_1/2/4/5 need swap).
        pure_x180 = _is_180(rx) and _is_zero(ry) and _is_zero(rz)
        pure_y180 = _is_180(ry) and _is_zero(rx) and _is_zero(rz)
        pure_z180 = _is_180(rz) and _is_zero(rx) and _is_zero(ry)
        swap_ew = pure_x180 or pure_y180 or pure_z180

        if swap_ew and "east" in faces and "west" in faces:
            faces["east"], faces["west"] = faces["west"], faces["east"]

        return faces

    # ========================================================================
    # Groups and Outliner Builder
    # ========================================================================

    def _build_groups_and_outliner(
        self,
        bones: List[BoneIR],
        bone_uuids: Dict[str, str],
        element_uuids: Dict[Tuple[str, int], str],
        abs_pivots: Dict[str, List[float]],
    ) -> Tuple[list, list]:
        """Build groups flat array and outliner tree structure.

        Groups: flat list of bone group dicts with name, uuid, origin,
                rotation, etc.

        Outliner: hierarchical tree with uuid, isOpen, children (element
                  UUIDs + nested groups).

        The root bone is the top-level entry in the outliner. No
        root_offset virtual bone is used — the old 180° Y rotation
        hack was incorrect and has been removed.

        Args:
            bones: List of BoneIR instances.
            bone_uuids: Dict mapping bone_name -> uuid.
            element_uuids: Dict mapping (bone_name, cube_idx) -> uuid.
            abs_pivots: Dict mapping bone_name -> [abs_x, abs_y, abs_z].

        Returns:
            Tuple of (groups_list, outliner_tree).
        """
        # Build bone name -> BoneIR lookup
        bone_map: Dict[str, BoneIR] = {b.name: b for b in bones}

        # Build parent -> children mapping
        children_map: Dict[str, List[str]] = {}
        root_bones: List[str] = []

        for bone in bones:
            if bone.parent is None:
                root_bones.append(bone.name)
            else:
                if bone.parent not in children_map:
                    children_map[bone.parent] = []
                children_map[bone.parent].append(bone.name)

        # Build groups flat array (all bones with full metadata)
        groups = []
        for bone in bones:
            bone_uid = bone_uuids[bone.name]
            abs_pivot = abs_pivots.get(bone.name, [0.0, 0.0, 0.0])

            # Rotation — preserve all rotations, except pure single-axis 180
            # which was baked into cube positions (v6.9.10).
            # Only zero if the bone has cubes (baking only applies to bones with cubes).
            rot = bone.rotation
            rx, ry, rz = float(rot[0]), float(rot[1]), float(rot[2])
            if bone.cubes:  # Only zero if bone has cubes that were baked
                def _is_180(a):
                    return abs(abs(a) - 180.0) < 0.5
                def _is_zero(a):
                    return abs(a) < 0.5
                if _is_180(rx) and _is_zero(ry) and _is_zero(rz):
                    rx = 0.0
                if _is_180(ry) and _is_zero(rx) and _is_zero(rz):
                    ry = 0.0
                if _is_180(rz) and _is_zero(rx) and _is_zero(ry):
                    rz = 0.0

            bb_rotation = [
                round_for_bbmodel(rx),
                round_for_bbmodel(ry),
                round_for_bbmodel(rz),
            ]
            # Snap near-zero values to exact zero
            for i in range(3):
                if abs(bb_rotation[i]) < 1e-10:
                    bb_rotation[i] = 0.0

            group = {
                "name": bone.name,
                "uuid": bone_uid,
                "export": True,
                "locked": False,
                "scope": 0,
                "selected": False,
                "_static": {"properties": {}, "temp_data": {}},
                "origin": [
                    float(abs_pivot[0]),
                    float(abs_pivot[1]),
                    float(abs_pivot[2]),
                ],
                "rotation": bb_rotation,
                "bedrock_binding": bone.binding if bone.binding else "",
                "color": 0,
                "children": [],
                "reset": False,
                "shade": True,
                "mirror_uv": False,
                "visibility": True,
                "autouv": 0,
                "isOpen": False,
                "primary_selected": False,
            }
            groups.append(group)

        # Build outliner tree (iterative, cycle-safe)
        def build_outliner_tree(start_bone: str) -> dict:
            """Build outliner tree iteratively from start_bone."""
            visited: set = set()
            entries: Dict[str, dict] = {}

            # BFS to collect all bones reachable from start_bone
            queue = [start_bone]
            bone_order: List[str] = []
            while queue:
                bn = queue.pop(0)
                if bn in visited:
                    continue
                visited.add(bn)
                bone_order.append(bn)
                for child_name in children_map.get(bn, []):
                    if child_name not in visited:
                        queue.append(child_name)

            # Build entries in reverse order (children before parents)
            for bn in reversed(bone_order):
                bone_uid = bone_uuids[bn]
                children: list = []

                # Add element UUIDs (cubes belonging to this bone)
                bone_obj = bone_map.get(bn)
                if bone_obj:
                    for cube_idx in range(len(bone_obj.cubes)):
                        elem_uuid = element_uuids[(bn, cube_idx)]
                        children.append(elem_uuid)

                # Add child bone group entries (already built)
                for child_name in children_map.get(bn, []):
                    if child_name in entries:
                        children.append(entries[child_name])

                entry: Dict[str, Any] = {
                    "uuid": bone_uid,
                    "isOpen": False,
                }

                if children:
                    entry["children"] = children

                entries[bn] = entry

            return entries[start_bone]

        # Build the outliner starting from root-level bones
        outliner: list = []

        # If there's a bone named "root", it's the single top-level entry
        if "root" in bone_map:
            outliner.append(build_outliner_tree("root"))
        else:
            # No explicit root bone — add top-level bones directly
            for bone_name in root_bones:
                outliner.append(build_outliner_tree(bone_name))

        return groups, outliner

    # ========================================================================
    # Textures Builder
    # ========================================================================

    def _build_textures(
        self,
        texture_path: Optional[str],
        texture_name: str,
        namespace: str,
        tex_width: int,
        tex_height: int,
    ) -> Tuple[list, int, int]:
        """Build textures list with optional base64-embedded PNG.

        Uses PIL to verify PNG dimensions against declared dimensions.
        If mismatch, overrides with PNG actual dimensions (ground truth).

        If texture_path is None or the file doesn't exist, the texture
        entry will have an empty source string (no embedded image).

        Args:
            texture_path: Path to the texture PNG file, or None.
            texture_name: Name for the texture entry.
            namespace: Resource namespace for texture metadata.
            tex_width: Declared texture width in pixels.
            tex_height: Declared texture height in pixels.

        Returns:
            Tuple of (textures_list, verified_tex_width, verified_tex_height).
        """
        source = ""
        png_width: Optional[int] = None
        png_height: Optional[int] = None

        if texture_path and os.path.isfile(texture_path):
            # Read PNG and embed as base64 data URI
            with open(texture_path, "rb") as f:
                raw = f.read()
            b64 = base64.b64encode(raw).decode("ascii")
            source = f"data:image/png;base64,{b64}"

            # PNG pixel verification: read actual dimensions
            try:
                from PIL import Image
                with Image.open(texture_path) as img:
                    png_width, png_height = img.size
            except ImportError:
                # PIL not available — skip verification gracefully
                pass
            except Exception:
                # Could not read image — skip verification gracefully
                pass

        # If PNG verification succeeded, check for dimension mismatch
        if png_width is not None and png_height is not None:
            if png_width != tex_width or png_height != tex_height:
                logger.warning(
                    "Texture dimension mismatch: declared %dx%d, "
                    "PNG actual %dx%d. Overriding with PNG dimensions "
                    "(ground truth). UV coordinates will be rescaled.",
                    tex_width, tex_height, png_width, png_height,
                )
                # v6.9.2: Calculate UV scale factor for rescaling
                # When declared dimensions differ from PNG actual,
                # UV coordinates in geo.json were calculated based on declared
                # dimensions. We need to rescale them to match actual PNG.
                scale_x = png_width / tex_width if tex_width > 0 else 1.0
                scale_y = png_height / tex_height if tex_height > 0 else 1.0
                # Store scale factors for element UV rescaling
                # (Applied in _build_elements when processing UV faces)
                self._uv_scale_x = scale_x
                self._uv_scale_y = scale_y
                tex_width = png_width
                tex_height = png_height

        tex_entry = {
            "name": texture_name,
            "folder": "entity/monster",
            "namespace": namespace,
            "source": source,
            "mode": "bitmap",
            "saved": True,
            "uuid": generate_uuid(),
            "width": tex_width,
            "height": tex_height,
            "uv_width": tex_width,
            "uv_height": tex_height,
        }

        return [tex_entry], tex_width, tex_height

    # ========================================================================
    # Animation Serialization
    # ========================================================================

    def _serialize_animations(
        self, animations: List[AnimationIR], bone_uuids: Dict[str, str]
    ) -> list:
        """Convert AnimationIR list to bbmodel animation format.

        Uses the bone UUID as the animator key so Blockbench can correctly
        link animations to bones.

        Args:
            animations: List of AnimationIR instances.
            bone_uuids: Dict mapping bone_name -> UUID (from model export).

        Returns:
            List of animation dicts in .bbmodel format.
        """
        result: list = []

        for anim in animations:
            anim_dict = self._serialize_single_animation(anim, bone_uuids)
            if anim_dict is not None:
                result.append(anim_dict)

        return result

    def _serialize_single_animation(
        self, anim: AnimationIR, bone_uuids: Dict[str, str]
    ) -> Optional[dict]:
        """Serialize a single AnimationIR to bbmodel animation dict.

        Uses the bone's group UUID as the animator key, matching the
        reference .bbmodel format.

        Args:
            anim: AnimationIR instance.
            bone_uuids: Dict mapping bone_name -> UUID.

        Returns:
            Dict in .bbmodel animation format, or None if no keyframes.
        """
        if not anim.bones:
            return None

        animators: Dict[str, dict] = {}

        for bone_name, bone_anim in anim.bones.items():
            keyframes = self._serialize_bone_keyframes(bone_anim)
            if keyframes:
                # Use the bone's group UUID as the animator key
                animator_key = bone_uuids.get(bone_name, bone_name)
                animators[animator_key] = {
                    "name": bone_name,
                    "type": "bone",
                    "keyframes": keyframes,
                }

        if not animators:
            return None

        # v6.9.5: Seamless loop strategy depends on interpolation.
        # - catmullrom: ALWAYS force last=first. The catmullrom spline smooths
        #   the internal transition (no visible jump between second-to-last and
        #   last), and first=last makes the wrapping segment zero-length,
        #   eliminating Blockbench's catmullrom loop wrapping tangent bug.
        # - linear: Conditional force (v6.9.4) -- only when natural seam <5 deg.
        #   For large seams, forcing creates a visible internal jump (linear
        #   has no smoothing), so keep natural values and accept boundary snap.
        if anim.loop == "loop" and anim.length > 0:
            for animator_key, animator in animators.items():
                kfs = animator.get("keyframes", [])
                if len(kfs) < 2:
                    continue
                by_channel = {}
                for kf in kfs:
                    ch = kf.get("channel", "")
                    by_channel.setdefault(ch, []).append(kf)
                for ch, ch_kfs in by_channel.items():
                    if len(ch_kfs) < 2:
                        continue
                    first = ch_kfs[0]
                    last = ch_kfs[-1]
                    # Check interpolation of this channel
                    uses_catmullrom = ch_kfs[0].get("interpolation") == "catmullrom"
                    if uses_catmullrom:
                        # Always force seamless for catmullrom (smooths internally)
                        last["data_points"] = [
                            dict(dp) for dp in first.get("data_points", [])
                        ]
                    else:
                        # Linear: only force if natural seam < 5 deg
                        natural_seam_ok = True
                        for ax in ("x", "y", "z"):
                            try:
                                fv = float(first["data_points"][0].get(ax, 0))
                                lv = float(last["data_points"][0].get(ax, 0))
                                if abs(fv - lv) > 5.0:
                                    natural_seam_ok = False
                                    break
                            except (ValueError, TypeError):
                                pass
                        if natural_seam_ok:
                            last["data_points"] = [
                                dict(dp) for dp in first.get("data_points", [])
                            ]
        # Compute animation length if not set
        anim_length = anim.length
        if anim_length <= 0:
            # Find max keyframe time across all bones
            max_time = 0.0
            for bone_anim in anim.bones.values():
                for kf in bone_anim.keyframes:
                    if kf.time > max_time:
                        max_time = kf.time
            anim_length = round_for_bbmodel(max_time)

        # Map GeckoLib loop modes to Blockbench loop modes
        # GeckoLib: "once", "hold_on_last_frame", "loop"
        # Blockbench: "once", "hold", "loop"
        bb_loop = anim.loop
        if bb_loop == "hold_on_last_frame":
            bb_loop = "hold"

        return {
            "name": anim.name,
            "uuid": generate_uuid(),
            "loop": bb_loop,
            "override": False,
            "length": round_for_bbmodel(anim_length),
            "snapping": 24,
            "selected": False,
            "anim_time_update": "",
            "blend_weight": "",
            "animators": animators,
        }

    def _serialize_bone_keyframes(
        self, bone_anim: BoneAnimationIR
    ) -> list:
        """Serialize all keyframes for a bone animation with carry-forward.

        Each KeyframeData becomes one bbmodel keyframe dict. The keyframes
        are sorted by time then channel for deterministic output.

        CARRY-FORWARD FIX:
        When a bone has data on multiple axes with different time points
        (e.g., rotation.y at t=0.5 but no rotation.z at that time),
        the non-explicit axes should carry forward the value from the
        PREVIOUS keyframe that had an explicit value for that axis,
        rather than defaulting to 0.0.

        Without carry-forward, a bone with y=5, z=10 at t=0 and y=8 at t=0.5
        would output (y=8, z=0) at t=0.5, causing z to snap from 10 to 0
        and creating a visible twitch/jump.

        Args:
            bone_anim: BoneAnimationIR instance with keyframes.

        Returns:
            List of keyframe dicts in .bbmodel format.
        """
        result: list = []

        # Sort keyframes by time, then channel
        sorted_kfs = sorted(
            bone_anim.keyframes,
            key=lambda kf: (kf.time, kf.channel),
        )

        # Apply carry-forward per (channel, axis) before serialization.
        # Track the last explicit value for each (channel, axis) pair.
        last_explicit: Dict[Tuple[str, str], float] = {}  # (channel, axis) -> value

        for kf in sorted_kfs:
            # Apply carry-forward to non-explicit axes
            carried_kf = self._apply_carry_forward(kf, last_explicit)
            kf_dict = self._serialize_keyframe(carried_kf)
            if kf_dict is not None:
                result.append(kf_dict)

        return result

    @staticmethod
    def _apply_carry_forward(
        kf: KeyframeData,
        last_explicit: Dict[Tuple[str, str], float],
    ) -> KeyframeData:
        """Apply carry-forward to non-explicit axis values.

        For each axis in the keyframe's channel, if the axis is not explicit
        (i.e., the source data didn't provide a value at this time point),
        use the last explicit value from a previous keyframe instead of 0.0.

        This prevents "twitching" when bones animate on multiple axes with
        different keyframe timing.

        Args:
            kf: The keyframe to apply carry-forward to.
            last_explicit: Dict mapping (channel, axis) -> last explicit value.
                           Updated in-place with any explicit values found.

        Returns:
            New KeyframeData with carry-forward applied.
        """
        key = kf.channel
        new_axes = {}

        for axis in AXES:
            axis_val: AxisValue = getattr(kf, axis)
            axis_key = (key, axis)

            if axis_val.explicit:
                # Update the last explicit value tracker
                last_explicit[axis_key] = axis_val.value
                new_axes[axis] = axis_val
            else:
                # Non-explicit: carry forward from last explicit value
                if axis_key in last_explicit:
                    carried_value = last_explicit[axis_key]
                    new_axes[axis] = AxisValue(value=carried_value, explicit=False)
                else:
                    # No previous explicit value — use default 0.0
                    new_axes[axis] = axis_val

        return KeyframeData(
            time=kf.time,
            channel=kf.channel,
            x=new_axes["x"],
            y=new_axes["y"],
            z=new_axes["z"],
            easing=kf.easing,
            interpolation=kf.interpolation,
            is_molang=kf.is_molang,
            molang_x=kf.molang_x,
            molang_y=kf.molang_y,
            molang_z=kf.molang_z,
        )

    def _serialize_keyframe(self, kf: KeyframeData) -> Optional[dict]:
        """Serialize a single KeyframeData to bbmodel keyframe dict.

        Only outputs keyframes that have at least one explicitly set axis.
        For channels where the source only had data on some axes, the
        non-explicit axes are filled with 0.0.

        For Molang keyframes, axes with Molang expressions are serialized
        as string values instead of numbers.

        Args:
            kf: KeyframeData instance.

        Returns:
            Dict in .bbmodel keyframe format, or None if the keyframe
            has no explicit data.
        """
        if not kf.has_explicit_axis():
            return None

        # Build data_points
        data_point: Dict[str, Any] = {}

        # NOTE: Do NOT add 'easing' to data_points — Blockbench .bbmodel format
        # only expects x/y/z in data_points. The 'easing' field belongs on the
        # keyframe itself (already set via 'interpolation' field). Adding 'easing'
        # to data_points can cause Blockbench to fail to render animations.
        # (Previous versions added data_point["easing"] = "linear" which broke playback.)

        for axis in AXES:
            molang_attr = f"molang_{axis}"
            molang_expr = getattr(kf, molang_attr, "")
            axis_val: AxisValue = getattr(kf, axis)

            if molang_expr:
                # Molang expression — use string value
                data_point[axis] = molang_expr
            else:
                # Numerical value — round for output
                data_point[axis] = round_for_bbmodel(axis_val.value)

        # v6.9.5: Rotation channels use catmullrom interpolation for smooth
        # sine-wave-driven motion. Linear interpolation between sparse (~60)
        # keyframes creates polygon corners at each keyframe -- perceived as
        # "mechanical" or "stepped" motion. Catmullrom draws smooth curves
        # through the keyframe points, matching the original sine wave shape.
        # Position/scale keep their original interpolation (usually linear).
        if kf.channel == "rotation":
            out_interp = "catmullrom"
        else:
            out_interp = kf.interpolation

        return {
            "channel": kf.channel,
            "data_points": [data_point],
            "uuid": generate_uuid(),
            "time": round_for_bbmodel(kf.time),
            "color": -1,
            "interpolation": out_interp,
        }
