#!/usr/bin/env python3
"""
BBModelGenerator - Blockbench .bbmodel Project File Generator
==============================================================
Generates a Blockbench .bbmodel project file from the converter's output
(geo.json + animation.json + texture PNG). The resulting .bbmodel file can
be opened directly in Blockbench via drag-and-drop.

Format Reference:
  .bbmodel is a JSON file (NOT a zip) containing model geometry, textures,
  and animations in a single document. Key differences from .geo.json:

  - UV format:  {uv: [u1, v1, u2, v2], texture: idx}  (vs geo.json's {uv:[u,v], uv_size:[w,h]})
  - Outliner:   Hierarchical bone tree with UUID references to elements
  - Elements:   Cubes with "from"/"to" (min/max corners) and "origin" (pivot)
  - Textures:   Embedded as base64 data URIs
  - Animations: Keyframes grouped per bone with channel/data_points structure

CRITICAL: Coordinate System for .bbmodel
=========================================
  .bbmodel uses ABSOLUTE world-space coordinates for element positions and
  bone pivots (origin). This is different from geo.json which uses
  bone-local (relative to parent) coordinates.

  Element from/to: ABSOLUTE world position (bone-local origin + absolute pivot)
  Element origin:  ABSOLUTE pivot of the bone (rotation center)
  Group origin:    ABSOLUTE pivot of the bone

  Absolute Pivot Computation:
    - Root: abs_pivot = root.pivot = [0, 24, 0]
    - Direct children of root: abs_pivot = root.pivot + child.pivot + [0, 24, 0]
      (The +24 Y offset corrects for the Y_OFFSET subtraction in our geo.json
       relative pivots caused by _make_pivots_relative() in model_converter.py)
    - Deeper descendants: abs_pivot = parent_abs_pivot + child.pivot

  RH->LH Coordinate Corrections (applied in this generator):
    1. North<->South UV Face Swap: The M_model = diag(1,-1,-1) Z-flip maps
       north_RH -> south_LH and south_RH -> north_LH, so UV data assigned to
       'north' in RH must be moved to 'south' in LH, and vice versa.
       West/East and Up/Down face UVs are NOT swapped.
    2. Geometric X-Mirror for mirrored cubes: When mirror=true, MC 1.12.2
       applies scale(-1,1,1) which mirrors both geometry and UV around the
       bone pivot (X=0 in bone-local space). The geometric mirror (negating
       from/to X coordinates relative to absolute pivot) must be applied in
       addition to setting mirror_uv=true.
    3. West<->East UV Swap for mirrored cubes: After the geometric X-mirror,
       the face at -X (west) was originally at +X (east) and vice versa,
       so the UV data assigned to 'west' and 'east' must be swapped.

  Rotation Conversion:
    Per HANDOFF_DOC Bug #3: .bbmodel uses the SAME extrinsic XYZ convention
    as geo.json. No intrinsic/extrinsic conversion is needed — rotation values
    are passed through directly. The previous scipy Rotation.from_euler conversion
    was WRONG and caused multi-axis rotation errors (especially Heblu wings).

    The geo.json stores rotations in degrees after convert_model_rot(rx, ry, rz)
    = (rx, -ry, -rz) from radians, then rad_to_deg(). The .bbmodel uses these
    SAME degree values. Do NOT convert between Euler angle conventions.
"""

import base64
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

# NOTE: scipy.spatial.transform.Rotation was REMOVED.
# Per HANDOFF_DOC Bug #3, .bbmodel uses the SAME extrinsic XYZ convention as
# geo.json. Rotation values should be passed through directly without
# any intrinsic/extrinsic conversion. The old scipy conversion was WRONG.
# from scipy.spatial.transform import Rotation


# Face direction mapping order used in bbmodel
FACE_NAMES = ["north", "east", "south", "west", "up", "down"]

# Y offset correction for absolute pivots.
# In our geo.json, _make_pivots_relative() subtracts root.pivot=[0,entity_height,0] from
# direct children of root, but the resulting relative pivot is entity_height units too low
# in Y because convert_model_pos() already negates Y without adding the offset.
# We correct this by adding entity_height to Y for root's direct children when computing
# absolute pivots for .bbmodel output.
# NOTE: This now reads the actual entity height from the geo.json root bone pivot,
# rather than hardcoding 24.0. This fixes "Model Floating" for non-standard entities.
Y_OFFSET_DEFAULT = 24.0


class BBModelGenerator:
    """
    Generates a .bbmodel project dict from converter output.

    Usage:
        gen = BBModelGenerator()
        bbmodel = gen.generate(geo_json, anim_json, texture_path="kirin.png")
        gen.save(bbmodel, "kirin.bbmodel")
    """

    def __init__(self):
        pass

    # ========================================================================
    # UUID Generation
    # ========================================================================

    @staticmethod
    def _uuid() -> str:
        """Generate a short unique ID string (8 hex chars) for bbmodel objects."""
        return uuid.uuid4().hex[:8]

    # ========================================================================
    # Absolute Pivot Computation
    # ========================================================================

    def _compute_absolute_pivots(self, bones: list) -> Dict[str, list]:
        """
        Compute absolute pivots for all bones using FK chain.

        In GeckoLib geo.json, each bone's pivot is RELATIVE to its parent's pivot.
        The absolute world-space position of a child bone requires applying
        the parent's rotation to the child's relative offset:
          child_abs = parent_abs + R_parent * child_pivot_relative

        This is the same FK chain computation used in model_converter.py's
        _compute_absolute_pivots(), adapted for the geo.json bone format.

        The geo.json rotation order for each bone is: R = Rz(rz) * Ry(ry) * Rx(rx)
        (extrinsic Z→Y→X, matching MC 1.12.2 ModelRenderer rendering order).

        No y_offset hack is needed — the geo.json pivots are already correct
        relative positions after model_converter's _make_pivots_relative().

        Returns:
            Dict mapping bone_name -> [abs_x, abs_y, abs_z]
        """
        import numpy as np
        from core_math import _rx, _ry, _rz

        bone_map: Dict[str, dict] = {b["name"]: b for b in bones}
        abs_pivots: Dict[str, list] = {}

        # Root pivot — extract entity height dynamically
        root_bone = bone_map.get("root")
        if root_bone:
            root_pivot = [float(v) for v in root_bone.get("pivot", [0, 24, 0])]
        else:
            root_pivot = [0.0, 24.0, 0.0]
        abs_pivots["root"] = root_pivot

        # Build parent -> children mapping for efficient traversal
        children_map: Dict[str, list] = {}
        for bone in bones:
            parent = bone.get("parent")
            if parent is not None:
                if parent not in children_map:
                    children_map[parent] = []
                children_map[parent].append(bone["name"])

        def _bone_rotation_matrix(bone: dict) -> np.ndarray:
            """Get rotation matrix from a bone's rotation data."""
            rot = bone.get("rotation", [0.0, 0.0, 0.0])
            rx = math.radians(float(rot[0]))
            ry = math.radians(float(rot[1]))
            rz = math.radians(float(rot[2]))
            return _rz(rz) @ _ry(ry) @ _rx(rx)

        # Iteratively compute absolute pivots using FK chain
        # child_abs = parent_abs + R_parent * child_pivot_relative
        def compute_abs_iterative(start_bone: str, parent_abs: list, parent_rot_matrix: np.ndarray):
            stack = [(start_bone, parent_abs, parent_rot_matrix)]
            visited = set()

            while stack:
                bone_name, p_abs, p_rot = stack.pop()

                # Break circular references
                if bone_name in abs_pivots or bone_name in visited:
                    continue
                visited.add(bone_name)

                bone = bone_map[bone_name]
                pivot = np.array([float(v) for v in bone.get("pivot", [0, 0, 0])])

                # FK chain: child_abs = parent_abs + R_parent * child_pivot_relative
                rotated_offset = p_rot @ pivot
                abs_pivot = [p_abs[i] + rotated_offset[i] for i in range(3)]

                abs_pivots[bone_name] = abs_pivot

                # Compute this bone's rotation matrix for its children
                bone_rot = _bone_rotation_matrix(bone)

                # Push children onto stack
                for child_name in children_map.get(bone_name, []):
                    stack.append((child_name, abs_pivot, bone_rot))

        # Start from root — root has no rotation applied to its own pivot
        root_rot = np.eye(3)  # Identity — root pivot is already absolute
        if root_bone:
            root_rot = _bone_rotation_matrix(root_bone)

        for child_name in children_map.get("root", []):
            compute_abs_iterative(child_name, root_pivot, root_rot)

        # Handle top-level bones that aren't "root" and don't have a parent
        for bone in bones:
            if bone["name"] not in abs_pivots and bone.get("parent") is None and bone["name"] != "root":
                pivot = [float(v) for v in bone.get("pivot", [0, 0, 0])]
                abs_pivots[bone["name"]] = pivot

        # Handle bones that still don't have absolute pivots (orphaned due to broken cycles)
        for bone in bones:
            if bone["name"] not in abs_pivots:
                pivot = [float(v) for v in bone.get("pivot", [0, 0, 0])]
                parent = bone.get("parent")
                if parent and parent in abs_pivots:
                    # Fallback: simple addition (no rotation — best effort for broken cycles)
                    parent_abs = abs_pivots[parent]
                    abs_pivots[bone["name"]] = [parent_abs[i] + pivot[i] for i in range(3)]
                else:
                    abs_pivots[bone["name"]] = [root_pivot[i] + pivot[i] for i in range(3)]

        return abs_pivots

    # ========================================================================
    # Rotation Conversion
    # ========================================================================

    def _convert_rotation_to_bbmodel(self, rotation_deg: list) -> list:
        """
        Convert rotation from geo.json to .bbmodel format.

        Per HANDOFF_DOC Bug #3: .bbmodel uses the SAME extrinsic XYZ convention
        as geo.json. No intrinsic/extrinsic conversion is needed.

        Previous versions used scipy Rotation.from_euler('XYZ', ...).as_euler('xyz', ...)
        which was WRONG. After extensive comparison with known-working reference
        .bbmodel files, we confirmed that both formats use extrinsic XYZ angles.

        The rotation values from geo.json are passed through directly.
        We only round to avoid floating point noise.

        Args:
            rotation_deg: [rx, ry, rz] in degrees from geo.json (extrinsic XYZ)

        Returns:
            [rx, ry, rz] in degrees for .bbmodel (same convention)
        """
        if not rotation_deg or all(abs(v) < 1e-10 for v in rotation_deg):
            return [0.0, 0.0, 0.0]

        # Direct passthrough — no scipy conversion needed.
        # Both geo.json and .bbmodel use extrinsic XYZ Euler angles.
        return [round(float(v), 6) for v in rotation_deg]

    # ========================================================================
    # Main Generation
    # ========================================================================

    def generate(
        self,
        geo_json: dict,
        anim_json: dict = None,
        texture_path: str = None,
        texture_name: str = "kirin",
        namespace: str = "srparasites",
    ) -> dict:
        """
        Generate a .bbmodel project dict from converter output.

        Args:
            geo_json: The .geo.json structure from ModelConverter.convert()
                      Expected format: {"format_version": ..., "model": {"identifier": ..., "bones": [...]}}
            anim_json: Optional animation JSON structure.
                       Expected format: {"format_version": ..., "animations": {"anim.name": {"loop": ..., "bones": {...}}}}
            texture_path: Path to the texture PNG file (will be embedded as base64)
            texture_name: Name for the texture entry
            namespace: Resource namespace for texture metadata

        Returns:
            Dict representing the .bbmodel structure, ready for json.dumps()
        """
        model = geo_json.get("model", geo_json)
        model_identifier = model.get("identifier", "model.unknown")
        # Extract short name from identifier like "model.kirin" -> "kirin"
        short_name = model_identifier.split(".")[-1] if "." in model_identifier else model_identifier

        tex_width = model.get("texture_width", 64)
        tex_height = model.get("texture_height", 32)
        bones = model.get("bones", [])

        now = int(time.time())

        # ------------------------------------------------------------------
        # Phase 1: Compute absolute pivots for all bones
        # ------------------------------------------------------------------
        abs_pivots = self._compute_absolute_pivots(bones)

        # ------------------------------------------------------------------
        # Phase 2: Assign UUIDs to all bones and cubes
        # ------------------------------------------------------------------
        bone_uuids: Dict[str, str] = {}  # bone_name -> uuid
        element_uuids: Dict[Tuple[str, int], str] = {}  # (bone_name, cube_idx) -> uuid

        for bone in bones:
            bone_name = bone["name"]
            bone_uuids[bone_name] = self._uuid()
            for cube_idx in range(len(bone.get("cubes", []))):
                element_uuids[(bone_name, cube_idx)] = self._uuid()

        # NOTE: root_offset virtual bone is NO LONGER created.
        # The 180° Y rotation was a RH→LH compensation hack that caused
        # incorrect model positioning. Both .bbmodel and geo.json use the
        # same Y-up LH coordinate system, so no rotation compensation is needed.

        # ------------------------------------------------------------------
        # Phase 3: Build elements (cubes) list
        # ------------------------------------------------------------------
        # Elements use ABSOLUTE world-space coordinates:
        #   - Element from/to: cube origin+abs_pivot and origin+size+abs_pivot
        #   - Element origin:  bone's absolute pivot (rotation center)
        elements = self._build_elements(bones, element_uuids, abs_pivots)

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
            texture_path, texture_name, namespace, tex_width, tex_height
        )

        # ------------------------------------------------------------------
        # Phase 6: Build animations
        # ------------------------------------------------------------------
        animations = self._build_animations(anim_json) if anim_json else []

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
            "geometry_name": model_identifier,
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
            "animations": animations,
        }

        return bbmodel

    # ========================================================================
    # Elements (Cubes) Builder
    # ========================================================================

    def _build_elements(
        self,
        bones: list,
        element_uuids: Dict[Tuple[str, int], str],
        abs_pivots: Dict[str, list],
    ) -> list:
        """
        Build the flat elements list from all bones' cubes.

        In geo.json, each cube has:
          - origin: [x, y, z]  (minimum corner, relative to bone's pivot)
          - size: [w, h, d]

        In .bbmodel, each element has:
          - from: [x, y, z]  (minimum corner in ABSOLUTE world space)
          - to: [x+w, y+h, z+d]  (maximum corner in ABSOLUTE world space)
          - origin: [abs_x, abs_y, abs_z]  (bone's absolute pivot = rotation center)

        The conversion from bone-local to absolute:
          abs_from[i] = bone_local_origin[i] + abs_pivot[i]
          abs_to[i] = bone_local_origin[i] + bone_size[i] + abs_pivot[i]
        """
        elements = []
        color_cycle = 0

        for bone in bones:
            bone_name = bone["name"]
            abs_pivot = abs_pivots.get(bone_name, [0.0, 0.0, 0.0])

            for cube_idx, cube in enumerate(bone.get("cubes", [])):
                elem_uuid = element_uuids[(bone_name, cube_idx)]
                origin = cube.get("origin", [0.0, 0.0, 0.0])
                size = cube.get("size", [1.0, 1.0, 1.0])
                inflate = cube.get("inflate", 0.0)
                mirror = cube.get("mirror", False)

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

                # Element origin = bone's absolute pivot (rotation center)
                bb_origin = [float(abs_pivot[0]), float(abs_pivot[1]), float(abs_pivot[2])]

                # Build faces with UV conversion
                faces = self._convert_faces(cube.get("uv", {}))

                # For mirrored cubes, swap West<->East UV faces.
                # After geometric X-mirror, the face at -X (west) was originally at +X (east),
                # so it needs the east UV. Similarly, the face at +X (east) needs the west UV.
                if mirror:
                    west_uv = faces.get("west")
                    east_uv = faces.get("east")
                    if west_uv is not None and east_uv is not None:
                        faces["west"] = east_uv
                        faces["east"] = west_uv

                element = {
                    "name": f"{bone_name}_c{cube_idx}",
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

    def _convert_faces(self, uv_data: dict) -> dict:
        """
        Convert face UV data from geo.json format to .bbmodel format.

        geo.json:  { "north": { "uv": [u, v], "uv_size": [w, h] }, ... }
        bbmodel:   { "north": { "uv": [u, v, u+w, v+h], "texture": 0 }, ... }

        For faces that don't have UV data in the geo.json, we still include
        them with texture: -1 (no texture assigned).
        """
        faces = {}

        for face_name in FACE_NAMES:
            face_uv = uv_data.get(face_name)

            if face_uv is not None:
                u = float(face_uv["uv"][0])
                v = float(face_uv["uv"][1])
                w = float(face_uv["uv_size"][0])
                h = float(face_uv["uv_size"][1])

                faces[face_name] = {
                    "uv": [u, v, u + w, v + h],
                    "texture": 0,
                }
            else:
                # Face without UV data - assign no texture
                faces[face_name] = {
                    "uv": [0.0, 0.0, 0.0, 0.0],
                    "texture": -1,
                }

        # North<->South UV Face Swap (RH->LH Z-flip correction)
        # When converting from MC 1.12.2 (RH, Y-down) to .bbmodel (LH, Y-up),
        # the M_model = diag(1, -1, -1) conversion Z-flips the physical faces:
        #   north_RH [0,0,-1] -> M_model*[0,0,-1] = [0,0,+1] = south_LH
        #   south_RH [0,0,+1] -> M_model*[0,0,+1] = [0,0,-1] = north_LH
        # Therefore the UV that was assigned to 'north' in RH must go to 'south'
        # in LH, and vice versa. West/East and Up/Down do NOT swap.
        north_uv = faces.get("north")
        south_uv = faces.get("south")
        if north_uv is not None and south_uv is not None:
            faces["north"] = south_uv
            faces["south"] = north_uv

        return faces

    # ========================================================================
    # Groups and Outliner Builder
    # ========================================================================

    def _build_groups_and_outliner(
        self,
        bones: list,
        bone_uuids: Dict[str, str],
        element_uuids: Dict[Tuple[str, int], str],
        abs_pivots: Dict[str, list],
    ) -> Tuple[list, list]:
        """
        Build both the groups flat array and the outliner tree structure.

        The groups flat array contains all bone groups with full metadata:
          - name, uuid, origin (absolute pivot), rotation (converted), etc.

        The outliner tree contains groups with only uuid, isOpen, and children:
          - children can be element UUID strings or nested group objects
        """
        # Build lookup: bone_name -> bone data
        bone_map: Dict[str, dict] = {}
        for bone in bones:
            bone_map[bone["name"]] = bone

        # Build parent -> children mapping
        children_map: Dict[str, list] = {}  # parent_name -> [child_bone_name, ...]
        root_bones: list = []  # Bones with no parent (truly top-level)

        for bone in bones:
            bone_name = bone["name"]
            parent_name = bone.get("parent")

            if parent_name is None:
                root_bones.append(bone_name)
            else:
                if parent_name not in children_map:
                    children_map[parent_name] = []
                children_map[parent_name].append(bone_name)

        # Build groups flat array (all bones with full metadata)
        groups = []
        for bone in bones:
            bone_name = bone["name"]
            bone_uid = bone_uuids[bone_name]
            rotation = bone.get("rotation", [0.0, 0.0, 0.0])
            abs_pivot = abs_pivots.get(bone_name, [0.0, 0.0, 0.0])

            # Convert rotation — no scipy needed (see HANDOFF_DOC Bug #3)
            bb_rotation = self._convert_rotation_to_bbmodel(rotation)

            # NOTE: The 180° Y rotation for RH→LH flip is now on the
            # root_offset virtual bone, NOT on root. This keeps animations
            # targeting "root" clean — they don't get the 180° base added.

            group = {
                "name": bone_name,
                "uuid": bone_uid,
                "export": True,
                "locked": False,
                "scope": 0,
                "selected": False,
                "_static": {"properties": {}, "temp_data": {}},
                "origin": [float(abs_pivot[0]), float(abs_pivot[1]), float(abs_pivot[2])],
                "rotation": bb_rotation,
                "bedrock_binding": "",
                "color": 0,
                "children": [],  # Empty in groups flat array; actual children in outliner
                "reset": False,
                "shade": True,
                "mirror_uv": False,
                "visibility": True,
                "autouv": 0,
                "isOpen": False,
                "primary_selected": False,
            }
            groups.append(group)

        # NOTE: root_offset virtual group is NO LONGER created.
        # The 180° Y rotation was incorrect — both .bbmodel and geo.json use
        # the same Y-up LH coordinate system.

        # Build outliner tree (iterative to avoid recursion depth issues)
        # Cycle-safe: tracks visited bones to prevent infinite loops
        def build_outliner_tree(start_bone: str) -> dict:
            """Build outliner tree iteratively from start_bone."""
            visited = set()
            # We use a two-pass approach:
            # 1. Build entries for all bones (bottom-up where possible)
            # 2. Assemble the tree structure
            entries = {}

            # BFS to collect all bones reachable from start_bone
            queue = [start_bone]
            bone_order = []
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
                children = []

                # Add element UUIDs (cubes belonging to this bone)
                for cube_idx in range(len(bone_map[bn].get("cubes", []))):
                    elem_uuid = element_uuids[(bn, cube_idx)]
                    children.append(elem_uuid)

                # Add child bone group entries (already built)
                for child_name in children_map.get(bn, []):
                    if child_name in entries:
                        children.append(entries[child_name])

                entry = {
                    "uuid": bone_uid,
                    "isOpen": False,
                }

                if children:
                    entry["children"] = children

                entries[bn] = entry

            return entries[start_bone]

        # Build the outliner starting from root-level bones
        outliner = []

        if "root" in bone_map:
            root_outliner_entry = build_outliner_tree("root")
            # Root is the top-level bone — no root_offset wrapper needed.
            # The 180° Y rotation was a RH→LH hack that's no longer used.
            outliner.append(root_outliner_entry)
        else:
            # No explicit root bone - add top-level bones directly
            for bone_name in root_bones:
                outliner.append(build_outliner_tree(bone_name))

        return groups, outliner

    # ========================================================================
    # Textures Builder
    # ========================================================================

    def _build_textures(
        self,
        texture_path: str,
        texture_name: str,
        namespace: str,
        tex_width: int,
        tex_height: int,
    ) -> Tuple[list, int, int]:
        """
        Build the textures list. If a texture path is provided, the PNG is
        embedded as a base64 data URI.

        PNG Pixel Verification:
            When a texture PNG is provided, we use PIL/Pillow (if available) to
            read its actual pixel dimensions. If the PNG dimensions differ from
            the declared texture_width/texture_height, a warning is logged and
            the PNG's actual dimensions are used as the ground truth (since the
            PNG is the authoritative source). This prevents UV misalignment
            caused by incorrect texture dimension extraction from Java source
            (e.g., unusual SRG field names).

            If PIL is not available, verification is skipped gracefully.

        Returns:
            Tuple of (textures_list, verified_tex_width, verified_tex_height)
        """
        textures = []

        source = ""
        png_width, png_height = None, None
        if texture_path and os.path.isfile(texture_path):
            with open(texture_path, "rb") as f:
                raw = f.read()
            b64 = base64.b64encode(raw).decode("ascii")
            source = f"data:image/png;base64,{b64}"

            # PNG pixel verification: read actual dimensions from the PNG file
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
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Texture dimension mismatch: declared {tex_width}x{tex_height}, "
                    f"PNG actual {png_width}x{png_height}. "
                    f"Overriding with PNG dimensions (ground truth)."
                )
                tex_width = png_width
                tex_height = png_height

        tex_entry = {
            "name": texture_name,
            "folder": "entity/monster",
            "namespace": namespace,
            "source": source,
            "mode": "bitmap",
            "saved": True,
            "uuid": self._uuid(),
            "width": tex_width,
            "height": tex_height,
            "uv_width": tex_width,
            "uv_height": tex_height,
        }

        textures.append(tex_entry)
        return textures, tex_width, tex_height

    # ========================================================================
    # Animations Builder
    # ========================================================================

    def _build_animations(self, anim_json: dict) -> list:
        """
        Convert from the converter's animation JSON format to bbmodel animation format.

        Input (converter animation.json):
        {
          "format_version": "1.8.0",
          "animations": {
            "animation.model.idle": {
              "loop": "loop",
              "animation_length": 6.2832,
              "bones": {
                "boneName": {
                  "rotation": {
                    "x": {
                      "0.0000": value_or_{"vector": val, "easing": name},
                      ...
                    }
                  }
                }
              }
            }
          }
        }

        Output (bbmodel animations):
        [
          {
            "name": "animation.model.idle",
            "uuid": "...",
            "loop": "loop",
            "override": false,
            "length": 6.2832,
            "snapping": 24,
            "selected": false,
            "anim_time_update": "",
            "blend_weight": "",
            "animators": {
              "boneName": {
                "name": "boneName",
                "type": "bone",
                "keyframes": [
                  {
                    "channel": "rotation",
                    "data_points": [{"x": ..., "y": ..., "z": ..., "easing": "linear"}],
                    "uuid": "...",
                    "time": 0.0,
                    "color": -1,
                    "interpolation": "linear"
                  }
                ]
              }
            }
          }
        ]
        """
        animations_list = []

        anims = anim_json.get("animations", {})

        for anim_name, anim_data in anims.items():
            loop_mode = anim_data.get("loop", "once")
            anim_length = anim_data.get("animation_length", 0.0)
            bones_data = anim_data.get("bones", {})

            animators = {}

            for bone_name, bone_anim in bones_data.items():
                keyframes = []

                # Process rotation channel
                rotation_data = bone_anim.get("rotation", {})
                rot_keyframes = self._process_channel(rotation_data, "rotation")
                keyframes.extend(rot_keyframes)

                # Process position channel (if present)
                position_data = bone_anim.get("position", {})
                pos_keyframes = self._process_channel(position_data, "position")
                keyframes.extend(pos_keyframes)

                # Process scale channel (if present)
                scale_data = bone_anim.get("scale", {})
                scale_keyframes = self._process_channel(scale_data, "scale")
                keyframes.extend(scale_keyframes)

                if keyframes:
                    # Sort keyframes by time
                    keyframes.sort(key=lambda kf: kf["time"])
                    animators[bone_name] = {
                        "name": bone_name,
                        "type": "bone",
                        "keyframes": keyframes,
                    }

            animation = {
                "name": anim_name,
                "uuid": self._uuid(),
                "loop": loop_mode,
                "override": False,
                "length": float(anim_length),
                "snapping": 24,
                "selected": False,
                "anim_time_update": "",
                "blend_weight": "",
                "animators": animators,
            }

            animations_list.append(animation)

        return animations_list

    def _process_channel(self, channel_data: dict, channel_name: str) -> list:
        """
        Process a single channel (rotation/position/scale) from the animation data.

        The channel data is per-axis:
        {
          "x": { "time_str": value_or_object, ... },
          "y": { "time_str": value_or_object, ... },
          "z": { "time_str": value_or_object, ... }
        }

        Where value_or_object is either:
          - A plain number (no easing, defaults to linear)
          - An object: {"vector": number, "easing": "easeOutSine"}

        We need to merge per-axis keyframes into unified keyframes at each
        unique time point.

        IMPORTANT: When merging per-axis keyframes, axes that don't have a value
        at a given time point must "hold" their previous value (carry-forward),
        NOT default to 0.0. Defaulting to 0.0 causes animation twitching because
        it creates zero-snaps where an axis suddenly drops to 0 when only another
        axis changes.
        """
        if not channel_data:
            return []

        # Collect all time points across all axes
        time_points = {}  # time_float -> {axis: (value, easing)}

        for axis, keyframes in channel_data.items():
            if axis not in ("x", "y", "z"):
                continue

            for time_str, value in keyframes.items():
                t = float(time_str)

                if t not in time_points:
                    time_points[t] = {}

                if isinstance(value, dict):
                    val = float(value.get("vector", 0.0))
                    easing = value.get("easing", "linear")
                else:
                    val = float(value)
                    easing = "linear"

                time_points[t][axis] = (val, easing)

        # Build keyframes from merged time points with carry-forward for
        # axes that don't change at each time point.
        keyframes = []
        last_values = {"x": 0.0, "y": 0.0, "z": 0.0}

        for t in sorted(time_points.keys()):
            axis_data = time_points[t]

            # Determine the dominant easing (use first non-linear easing found)
            easing = "linear"
            for axis in ("x", "y", "z"):
                if axis in axis_data:
                    _, axis_easing = axis_data[axis]
                    if axis_easing != "linear":
                        easing = axis_easing
                        break

            # Carry-forward: use last known value for axes not present at this time
            # This prevents zero-snaps that cause twitching
            x_val = axis_data.get("x", (last_values["x"], "linear"))[0]
            y_val = axis_data.get("y", (last_values["y"], "linear"))[0]
            z_val = axis_data.get("z", (last_values["z"], "linear"))[0]

            # Update last known values for carry-forward
            last_values["x"] = x_val
            last_values["y"] = y_val
            last_values["z"] = z_val

            data_point = {"x": x_val, "y": y_val, "z": z_val, "easing": easing}

            # Use catmullrom interpolation for non-linear easing (smoother in Blockbench)
            interpolation = "catmullrom" if easing != "linear" else "linear"

            keyframe = {
                "channel": channel_name,
                "data_points": [data_point],
                "uuid": self._uuid(),
                "time": t,
                "color": -1,
                "interpolation": interpolation,
            }

            keyframes.append(keyframe)

        return keyframes

    # ========================================================================
    # Save Method
    # ========================================================================

    def save(self, bbmodel: dict, filepath: str) -> None:
        """
        Save the .bbmodel dict to a JSON file.

        Args:
            bbmodel: The .bbmodel structure dict from generate()
            filepath: Output file path (should end in .bbmodel)
        """
        # Ensure the parent directory exists
        parent_dir = os.path.dirname(filepath)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(bbmodel, f, indent=2, ensure_ascii=False)


# ============================================================================
# Convenience Function
# ============================================================================

def generate_bbmodel(
    geo_json_path: str,
    anim_json_path: str = None,
    texture_path: str = None,
    output_path: str = None,
    texture_name: str = "kirin",
    namespace: str = "srparasites",
) -> dict:
    """
    Convenience function to generate and optionally save a .bbmodel file.

    Args:
        geo_json_path: Path to the .geo.json file
        anim_json_path: Optional path to the .animation.json file
        texture_path: Optional path to the texture PNG file
        output_path: Optional output path for the .bbmodel file
        texture_name: Name for the texture entry
        namespace: Resource namespace

    Returns:
        The .bbmodel dict
    """
    # Load geo.json
    with open(geo_json_path, "r", encoding="utf-8") as f:
        geo_json = json.load(f)

    # Load animation.json (optional)
    anim_json = None
    if anim_json_path and os.path.isfile(anim_json_path):
        with open(anim_json_path, "r", encoding="utf-8") as f:
            anim_json = json.load(f)

    # Generate .bbmodel
    generator = BBModelGenerator()
    bbmodel = generator.generate(
        geo_json,
        anim_json=anim_json,
        texture_path=texture_path,
        texture_name=texture_name,
        namespace=namespace,
    )

    # Save if output path provided
    if output_path:
        generator.save(bbmodel, output_path)

    return bbmodel


# ============================================================================
# CLI Entry Point
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate .bbmodel from converter output")
    parser.add_argument("geo_json", help="Path to the .geo.json file")
    parser.add_argument("--anim", help="Path to the .animation.json file", default=None)
    parser.add_argument("--texture", help="Path to the texture PNG file", default=None)
    parser.add_argument("--output", "-o", help="Output .bbmodel file path", default=None)
    parser.add_argument("--texture-name", help="Texture name", default="kirin")
    parser.add_argument("--namespace", help="Resource namespace", default="srparasites")

    args = parser.parse_args()

    # Derive output path if not provided
    if not args.output:
        base = os.path.splitext(args.geo_json)[0]
        args.output = base + ".bbmodel"

    # Auto-detect texture if not provided
    if not args.texture:
        base = os.path.splitext(args.geo_json)[0]
        for ext in [".png", ".png.png"]:
            candidate = base + ".png"
            if os.path.isfile(candidate):
                args.texture = candidate
                break

    # Auto-detect animation if not provided
    if not args.anim:
        base = os.path.splitext(args.geo_json)[0]
        candidate = base + ".animation.json"
        if os.path.isfile(candidate):
            args.anim = candidate

    bbmodel = generate_bbmodel(
        args.geo_json,
        anim_json_path=args.anim,
        texture_path=args.texture,
        output_path=args.output,
        texture_name=args.texture_name,
        namespace=args.namespace,
    )

    print(f"Generated {args.output}")
    print(f"  Elements:  {len(bbmodel.get('elements', []))}")
    print(f"  Groups:    {len(bbmodel.get('groups', []))}")
    print(f"  Outliner:  {len(bbmodel.get('outliner', []))} root entries")
    print(f"  Textures:  {len(bbmodel.get('textures', []))}")
    print(f"  Animations: {len(bbmodel.get('animations', []))}")
