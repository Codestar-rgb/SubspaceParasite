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
    Uses scipy.spatial.transform.Rotation to convert from geo.json extrinsic
    XYZ Euler angles to Blockbench intrinsic xyz Euler angles:
      Rotation.from_euler('XYZ', geo_rot, degrees=True).as_euler('xyz', degrees=True)
    This correctly handles multi-axis rotations where simple [-rx, -ry, rz]
    fails (e.g., when Z=-180, X rotation sign must flip).
"""

import base64
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from scipy.spatial.transform import Rotation


# Face direction mapping order used in bbmodel
FACE_NAMES = ["north", "east", "south", "west", "up", "down"]

# Y offset correction for absolute pivots.
# In our geo.json, _make_pivots_relative() subtracts root.pivot=[0,24,0] from
# direct children of root, but the resulting relative pivot is 24 units too low
# in Y because convert_model_pos() already negates Y without adding the Y_OFFSET.
# We correct this by adding 24 to Y for root's direct children when computing
# absolute pivots for .bbmodel output.
Y_OFFSET = 24.0


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
        Compute absolute pivots for all bones, matching the reference .bbmodel
        convention where element from/to and group origins are in absolute
        world space.

        Algorithm:
          - root: abs_pivot = root.pivot (typically [0, 24, 0])
          - Direct children of root: abs_pivot = root.pivot + child.pivot + [0, Y_OFFSET, 0]
            The Y_OFFSET correction compensates for the double-subtraction bug
            in _make_pivots_relative() which subtracts root.pivot=[0,24,0]
            from convert_model_pos() results that already lack the +24 Y offset.
          - Deeper descendants: abs_pivot = parent_abs_pivot + child.pivot

        Circular reference handling:
          Some models have circular parent references (e.g. A→B→C→A) caused by
          decompilation artifacts. We break cycles by treating already-visited
          bones as having no further parent chain.

        Returns:
            Dict mapping bone_name -> [abs_x, abs_y, abs_z]
        """
        bone_map: Dict[str, dict] = {b["name"]: b for b in bones}
        abs_pivots: Dict[str, list] = {}

        # Root pivot
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

        # Iteratively compute absolute pivots (avoids recursion depth issues)
        # Also detects and breaks circular references.
        def compute_abs_iterative(start_bone: str, parent_abs: list, is_root_child: bool = False):
            stack = [(start_bone, parent_abs, is_root_child)]
            visited = set()

            while stack:
                bone_name, p_abs, is_rc = stack.pop()

                # Break circular references
                if bone_name in abs_pivots or bone_name in visited:
                    continue
                visited.add(bone_name)

                bone = bone_map[bone_name]
                pivot = [float(v) for v in bone.get("pivot", [0, 0, 0])]

                abs_pivot = [p_abs[i] + pivot[i] for i in range(3)]

                # For direct children of root, add Y_OFFSET correction
                if is_rc:
                    abs_pivot[1] += Y_OFFSET

                abs_pivots[bone_name] = abs_pivot

                # Push children onto stack
                for child_name in children_map.get(bone_name, []):
                    stack.append((child_name, abs_pivot, False))

        # Process root's children (they get the Y_OFFSET correction)
        for child_name in children_map.get("root", []):
            compute_abs_iterative(child_name, root_pivot, is_root_child=True)

        # Also handle top-level bones that aren't "root" and don't have a parent
        for bone in bones:
            if bone["name"] not in abs_pivots and bone.get("parent") is None and bone["name"] != "root":
                pivot = [float(v) for v in bone.get("pivot", [0, 0, 0])]
                abs_pivots[bone["name"]] = pivot

        # Handle bones that still don't have absolute pivots (orphaned due to broken cycles)
        # These bones have a parent reference that was part of a cycle;
        # use the root pivot as their base
        for bone in bones:
            if bone["name"] not in abs_pivots:
                pivot = [float(v) for v in bone.get("pivot", [0, 0, 0])]
                # Try to use parent's absolute pivot if available
                parent = bone.get("parent")
                if parent and parent in abs_pivots:
                    parent_abs = abs_pivots[parent]
                    abs_pivots[bone["name"]] = [parent_abs[i] + pivot[i] for i in range(3)]
                else:
                    # Fallback: use root pivot as base
                    abs_pivots[bone["name"]] = [root_pivot[i] + pivot[i] for i in range(3)]

        return abs_pivots

    # ========================================================================
    # Rotation Conversion
    # ========================================================================

    def _convert_rotation_to_bbmodel(self, rotation_deg: list) -> list:
        """
        Convert rotation from geo.json (extrinsic XYZ) to .bbmodel (intrinsic xyz)
        using scipy Rotation.

        The geo.json format stores rotations as extrinsic XYZ Euler angles.
        The .bbmodel (Blockbench internal) format uses intrinsic xyz Euler angles.
        scipy's Rotation class handles this conversion correctly, including
        multi-axis rotations where simple sign flipping fails.

        Example failures of simple [-rx, -ry, rz]:
          - geo [44, 0, 0] -> simple gives [-44, 0, 0] but correct is [44, 0, 0]
          - geo [-25, 0, -180] -> simple gives [25, 0, -180] (happens to be correct)
          The Z=-180 case flips the X sign convention, which scipy handles properly.
        """
        if not rotation_deg or all(abs(v) < 1e-10 for v in rotation_deg):
            return [0.0, 0.0, 0.0]

        r = Rotation.from_euler("XYZ", rotation_deg, degrees=True)
        result = r.as_euler("xyz", degrees=True)
        # Round to avoid floating point noise (e.g., 24.999999999996 -> 25.0)
        return [round(float(v), 6) for v in result]

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

        tex_width = model.get("texture_width", 256)
        tex_height = model.get("texture_height", 256)
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
        # Phase 5: Build textures list
        # ------------------------------------------------------------------
        textures = self._build_textures(
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

    def _is_z180_bone(self, bone: dict) -> bool:
        """
        Detect bones with a 180° Z-rotation that should be baked into geometry.

        In MC 1.12.2, some bones (especially wing membranes/skins) have
        rotateAngleZ = -PI (180° Z-rotation). When converted to bbmodel, this
        becomes [0, 0, 180] intrinsic xyz rotation. However, for flat (h≈0)
        membrane elements, a Z-rotation in bbmodel only flips X and Y, not Z.
        The visual effect in MC requires the wing to flip in the Z direction,
        which corresponds to a Y-180° rotation in the bbmodel coordinate system.

        For these bones, we bake the rotation into the element geometry instead
        of storing it as a bone rotation, which produces the correct visual result.

        IMPORTANT: When a bone has BOTH Z-180° rotation AND mirror=True on its
        cubes, the two effects cancel out for flat elements (Z-180° flips X,
        mirror flips X again → net: no X flip). In this case, we do NOT bake
        the Z-180° rotation because it would conflict with the mirror.
        Instead, the mirror+Z-180° combination is handled per-cube in
        _build_elements() by skipping both transformations.
        """
        rotation = bone.get("rotation", [0.0, 0.0, 0.0])
        if rotation is None:
            return False

        # Check if rotation is approximately [0, 0, ±180] (Z-axis 180° rotation)
        rx, ry, rz = [float(v) for v in rotation]
        x_near_zero = abs(rx) < 1.0
        y_near_zero = abs(ry) < 1.0
        z_near_180 = abs(abs(rz) - 180.0) < 1.0

        if not (x_near_zero and y_near_zero and z_near_180):
            return False

        # Only bake if the bone contains flat (h≈0) elements (membranes/skins)
        # that do NOT have mirror=True (mirror+Z-180° cancels out)
        has_non_mirrored_flat = False
        for cube in bone.get("cubes", []):
            size = cube.get("size", [1.0, 1.0, 1.0])
            mirror = cube.get("mirror", False)
            if abs(float(size[1])) < 0.5:  # Flat element (height near 0)
                if not mirror:
                    has_non_mirrored_flat = True

        return has_non_mirrored_flat

    def _bake_z180_rotation(
        self,
        from_pos: list,
        to_pos: list,
        abs_pivot: list,
        faces: dict,
    ) -> Tuple[list, list, dict]:
        """
        Bake a 180° Z-rotation into element geometry.

        For bones with 180° Z-rotation in geo.json (from MC rotateAngleZ = -PI),
        the scipy-converted rotation is [0, 0, 180] in intrinsic xyz. Rather than
        storing this as a bone rotation (which causes rendering issues with flat
        elements), we bake it into the element geometry by applying the Z-180°
        rotation to the from/to coordinates and setting the bone rotation to [0,0,0].

        Z-180° rotation around pivot: (x,y,z) -> (2*px-x, 2*py-y, z)
        For flat elements (h≈0) at constant Y, the Y-flip is invisible.

        Args:
            from_pos: Element from position (absolute)
            to_pos: Element to position (absolute)
            abs_pivot: Bone's absolute pivot
            faces: Element face UV data

        Returns:
            (new_from, new_to, new_faces) with rotation baked in
        """
        px, py, pz = abs_pivot

        # Apply 180° Z-rotation around pivot: (x,y,z) -> (2*px-x, 2*py-y, z)
        new_from = [2*px - from_pos[0], 2*py - from_pos[1], from_pos[2]]
        new_to = [2*px - to_pos[0], 2*py - to_pos[1], to_pos[2]]

        # Ensure from <= to on each axis (required by .bbmodel format)
        for i in range(3):
            if new_from[i] > new_to[i]:
                new_from[i], new_to[i] = new_to[i], new_from[i]

        # Z-180° rotation swaps face visibility:
        # The face that was at +X (east) is now at -X (west) and vice versa
        # The face that was at +Y (up) is now at -Y (down) and vice versa
        # For flat elements at constant Y, the up/down swap is less important
        # but we still need to swap east/west UVs
        west_uv = faces.get("west")
        east_uv = faces.get("east")
        if west_uv is not None and east_uv is not None:
            faces["west"] = east_uv
            faces["east"] = west_uv

        up_uv = faces.get("up")
        down_uv = faces.get("down")
        if up_uv is not None and down_uv is not None:
            faces["up"] = down_uv
            faces["down"] = up_uv

        # Rotate north/south face UVs 180° in UV space (X and Y flipped)
        for face_name in ["north", "south"]:
            if face_name in faces:
                face = faces[face_name]
                uv = face.get("uv")
                if isinstance(uv, list) and len(uv) == 4:
                    face["uv"] = [uv[2], uv[3], uv[0], uv[1]]

        return new_from, new_to, faces

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

        BAKED ROTATION FIX:
          Bones with 180° Z-rotation and flat (h≈0) elements (wing membranes/skins)
          have their rotation baked into the element geometry instead of stored as
          bone rotation. This is because the visual effect of MC's Z-rotation on
          flat elements corresponds to a Y-rotation in the bbmodel coordinate system.
        """
        elements = []
        color_cycle = 0

        # Identify bones whose Z-180° rotation should be baked into geometry
        baked_bones = set()
        # Also track bones where ALL flat cubes have mirror=True (mirror+Z-180° cancels)
        mirror_z180_bones = set()
        for bone in bones:
            if self._is_z180_bone(bone):
                baked_bones.add(bone["name"])
            # Check if this is a Z-180° bone where all flat cubes are mirrored
            rotation = bone.get("rotation", [0.0, 0.0, 0.0])
            if rotation is not None:
                rx, ry, rz = [float(v) for v in rotation]
                if abs(rx) < 1.0 and abs(ry) < 1.0 and abs(abs(rz) - 180.0) < 1.0:
                    flat_cubes = [c for c in bone.get("cubes", [])
                                  if abs(float(c.get("size", [1,1,1])[1])) < 0.5]
                    if flat_cubes and all(c.get("mirror", False) for c in flat_cubes):
                        mirror_z180_bones.add(bone["name"])

        for bone in bones:
            bone_name = bone["name"]
            abs_pivot = abs_pivots.get(bone_name, [0.0, 0.0, 0.0])
            is_baked = bone_name in baked_bones

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

                # Handle mirror + Z-180° combination for flat elements.
                # In MC 1.12.2, mirror flips X and Z-180° also flips X.
                # For flat elements, mirror + Z-180° = no net X flip (they cancel).
                # When both are present, skip BOTH geometric transformations
                # and keep the cube at its original bone-local position.
                # When only mirror is present (no Z-180°), apply mirror normally.
                # When only Z-180° is present (no mirror), bake Z-180°.
                is_z180_baked = is_baked  # bone-level Z-180° detection
                mirror_and_z180 = mirror and is_z180_baked

                if mirror_and_z180:
                    # mirror + Z-180° cancel out for flat elements:
                    # No geometric X-mirror, no Z-180° bake.
                    # The cube stays at its original bone-local position.
                    # mirror_uv stays True for correct UV rendering.
                    pass
                elif mirror:
                    # Mirror only: apply geometric X-mirror around the bone pivot
                    px = abs_pivot[0]
                    from_x_mirrored = 2 * px - (float(origin[0]) + float(size[0]) + px)
                    to_x_mirrored = 2 * px - (float(origin[0]) + px)
                    from_pos[0] = from_x_mirrored
                    to_pos[0] = to_x_mirrored
                    if from_pos[0] > to_pos[0]:
                        from_pos[0], to_pos[0] = to_pos[0], from_pos[0]

                # Element origin = bone's absolute pivot (rotation center)
                bb_origin = [float(abs_pivot[0]), float(abs_pivot[1]), float(abs_pivot[2])]

                # Build faces with UV conversion
                faces = self._convert_faces(cube.get("uv", {}))

                # UV face swaps depend on which geometric transforms were applied
                if mirror_and_z180:
                    # mirror + Z-180°: both applied = neither applied geometrically
                    # UV is un-flipped (double flip cancels out)
                    # No UV swap needed
                    pass
                elif mirror:
                    # Mirror only: swap West<->East UV faces
                    west_uv = faces.get("west")
                    east_uv = faces.get("east")
                    if west_uv is not None and east_uv is not None:
                        faces["west"] = east_uv
                        faces["east"] = west_uv

                # Bake Z-180° rotation into geometry for membrane/skin bones
                # Skip if mirror is also present (already handled above)
                if is_z180_baked and not mirror_and_z180:
                    from_pos, to_pos, faces = self._bake_z180_rotation(
                        from_pos, to_pos, abs_pivot, faces
                    )

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
                    "mirror_uv": mirror and not mirror_and_z180,
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

        # Identify bones with baked Z-180° rotation (set their group rotation to [0,0,0])
        baked_bones = set()
        mirror_z180_bones = set()  # Bones where mirror+Z-180° cancel out
        for bone in bones:
            if self._is_z180_bone(bone):
                baked_bones.add(bone["name"])
            # Check if this is a Z-180° bone where all flat cubes are mirrored
            rotation = bone.get("rotation", [0.0, 0.0, 0.0])
            if rotation is not None:
                rx, ry, rz = [float(v) for v in rotation]
                if abs(rx) < 1.0 and abs(ry) < 1.0 and abs(abs(rz) - 180.0) < 1.0:
                    flat_cubes = [c for c in bone.get("cubes", [])
                                  if abs(float(c.get("size", [1,1,1])[1])) < 0.5]
                    if flat_cubes and all(c.get("mirror", False) for c in flat_cubes):
                        mirror_z180_bones.add(bone["name"])

        # Build groups flat array (all bones with full metadata)
        groups = []
        for bone in bones:
            bone_name = bone["name"]
            bone_uid = bone_uuids[bone_name]
            rotation = bone.get("rotation", [0.0, 0.0, 0.0])
            abs_pivot = abs_pivots.get(bone_name, [0.0, 0.0, 0.0])

            # For bones with baked Z-180° rotation, set group rotation to [0,0,0]
            # Also for bones where mirror+Z-180° cancel, set rotation to [0,0,0]
            if bone_name in baked_bones or bone_name in mirror_z180_bones:
                bb_rotation = [0.0, 0.0, 0.0]
            else:
                # Convert rotation using scipy
                bb_rotation = self._convert_rotation_to_bbmodel(rotation)

            # Root bone: add 180° Y rotation so the model faces the correct direction
            # (RH→LH coordinate flip causes the model to appear reversed)
            if bone_name == "root":
                bb_rotation[1] += 180.0

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
            outliner.append(build_outliner_tree("root"))
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
    ) -> list:
        """
        Build the textures list. If a texture path is provided, the PNG is
        embedded as a base64 data URI.
        """
        textures = []

        source = ""
        if texture_path and os.path.isfile(texture_path):
            with open(texture_path, "rb") as f:
                raw = f.read()
            b64 = base64.b64encode(raw).decode("ascii")
            source = f"data:image/png;base64,{b64}"

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
        return textures

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

        # Track animation names to prevent duplicates
        seen_names = set()

        for anim_name, anim_data in anims.items():
            # Skip duplicate animations
            if anim_name in seen_names:
                continue
            seen_names.add(anim_name)

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
                    # Sort keyframes by time, then by channel for stable ordering
                    keyframes.sort(key=lambda kf: (kf["time"], kf["channel"]))

                    # Enforce loop continuity for loop animations:
                    # Ensure the last keyframe's values match the first for seamless looping
                    if loop_mode == "loop" and len(keyframes) >= 2:
                        keyframes = self._enforce_loop_continuity(keyframes, anim_length)

                    # Remove near-duplicate keyframes at the same time point
                    # (same time AND same channel)
                    keyframes = self._deduplicate_keyframes(keyframes)

                    # Unify interpolation mode per channel to avoid velocity
                    # discontinuities that cause twitching/flickering.
                    # Mixed linear+catmullrom in the same channel creates visible
                    # jumps at the transition points.
                    keyframes = self._unify_interpolation(keyframes)

                    animators[bone_name] = {
                        "name": bone_name,
                        "type": "bone",
                        "keyframes": keyframes,
                    }

            # Skip empty animations (no bones with keyframes)
            if not animators:
                continue

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

    def _enforce_loop_continuity(self, keyframes: list, anim_length: float) -> list:
        """
        Enforce loop continuity by ensuring the last keyframe's values match
        the first keyframe's values for each channel.

        For seamless looping, the value at t=0 and t=animation_length should
        be identical. We FORCE the last keyframe to match the first exactly.
        This is critical because Blockbench/geckolib interpolates between
        the last keyframe and the loop restart, and any mismatch causes
        a visible snap/twitch at the loop point.

        Additionally, we ensure there is always a keyframe at t=0 and
        t=animation_length for each channel, inserting them if missing.
        """
        # Group keyframes by channel
        channels = {}
        for kf in keyframes:
            ch = kf["channel"]
            if ch not in channels:
                channels[ch] = []
            channels[ch].append(kf)

        result = []
        for ch, ch_kfs in channels.items():
            # Sort by time
            ch_kfs.sort(key=lambda k: k["time"])

            if len(ch_kfs) < 2:
                result.extend(ch_kfs)
                continue

            first = ch_kfs[0]
            last = ch_kfs[-1]

            # Ensure first keyframe is at t=0
            if first["time"] > 1e-6:
                # Insert a keyframe at t=0 using the first keyframe's values
                insert_kf = {
                    "channel": ch,
                    "data_points": [dict(first["data_points"][0])],
                    "uuid": self._uuid(),
                    "time": 0.0,
                    "color": -1,
                    "interpolation": first.get("interpolation", "catmullrom"),
                }
                ch_kfs.insert(0, insert_kf)
                first = insert_kf

            # Ensure last keyframe is at t=animation_length
            if anim_length > 0 and abs(last["time"] - anim_length) > 1e-6:
                # Insert a keyframe at t=animation_length matching the first
                insert_kf = {
                    "channel": ch,
                    "data_points": [dict(first["data_points"][0])],
                    "uuid": self._uuid(),
                    "time": anim_length,
                    "color": -1,
                    "interpolation": first.get("interpolation", "catmullrom"),
                }
                ch_kfs.append(insert_kf)
                last = insert_kf

            # FORCE last keyframe to exactly match first for seamless loop
            # This is the most important fix for twitching at loop points
            first_dp = first["data_points"][0]
            last_dp = last["data_points"][0]

            for axis in ("x", "y", "z"):
                last_dp[axis] = first_dp[axis]

            result.extend(ch_kfs)

        return result

    def _unify_interpolation(self, keyframes: list) -> list:
        """
        Unify interpolation mode within each channel to prevent velocity
        discontinuities that cause visual twitching/flickering.

        When a channel has mixed linear and catmullrom keyframes, the
        transition between interpolation modes creates a derivative
        discontinuity (C0 continuous but not C1), which manifests as a
        visible "snap" or "twitch" in the animation.

        Strategy:
          - Channels with 3+ keyframes: use catmullrom for all (smooth curves)
          - Channels with 2 keyframes: use catmullrom (still smooth, no downside)
          - This ensures C1 continuity throughout the animation
        """
        # Group keyframes by channel
        channels = {}
        for kf in keyframes:
            ch = kf["channel"]
            if ch not in channels:
                channels[ch] = []
            channels[ch].append(kf)

        for ch, ch_kfs in channels.items():
            # Determine the best interpolation for this channel
            # Count how many use each mode
            interp_counts = {}
            for kf in ch_kfs:
                interp = kf.get("interpolation", "linear")
                interp_counts[interp] = interp_counts.get(interp, 0) + 1

            # If there's any mixing, unify to catmullrom for smoothness
            if len(interp_counts) > 1:
                for kf in ch_kfs:
                    kf["interpolation"] = "catmullrom"
            elif len(ch_kfs) >= 2 and list(interp_counts.keys())[0] == "linear":
                # Even for uniform linear channels with 2+ keyframes,
                # catmullrom produces smoother results for sampled animations
                for kf in ch_kfs:
                    kf["interpolation"] = "catmullrom"

        return keyframes

    def _deduplicate_keyframes(self, keyframes: list) -> list:
        """
        Remove near-duplicate keyframes at the same time point for the same channel.
        Two keyframes are duplicates if they have the same time AND same channel.
        When duplicates exist, merge them by keeping the one with the most data.
        """
        if len(keyframes) <= 1:
            return keyframes

        seen = {}
        result = []
        for kf in keyframes:
            # Create a key from time (rounded) and channel
            time_key = round(kf["time"], 6)
            channel = kf["channel"]
            dedup_key = (time_key, channel)

            if dedup_key not in seen:
                seen[dedup_key] = kf
                result.append(kf)
            else:
                # Merge: if the existing keyframe has zero values where this one
                # doesn't, update it (carry-forward merge)
                existing = seen[dedup_key]
                existing_dp = existing["data_points"][0]
                new_dp = kf["data_points"][0]
                for axis in ("x", "y", "z"):
                    if abs(existing_dp.get(axis, 0)) < 1e-10 and abs(new_dp.get(axis, 0)) > 1e-10:
                        existing_dp[axis] = new_dp[axis]

        return result

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

        INTERPOLATION CONSISTENCY FIX:
          All keyframes within a channel use the SAME interpolation type to avoid
          velocity discontinuities that cause visual twitching/flickering. We use
          "linear" consistently because the source animations are sampled from
          mathematical functions with dense keyframes, making linear interpolation
          smooth enough while avoiding the derivative discontinuities that occur
          when mixing linear and catmullrom.
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

            keyframe = {
                "channel": channel_name,
                "data_points": [data_point],
                "uuid": self._uuid(),
                "time": t,
                "color": -1,
                "interpolation": "catmullrom",
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
