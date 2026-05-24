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
  .bbmodel is Blockbench's INTERNAL format. It is the direct serialization of
  Blockbench's in-memory scene graph. Blockbench does NOT apply any coordinate
  conversion when reading/writing .bbmodel files.

  This is different from .geo.json import/export, where Blockbench applies
  X-flip to cube positions (parseCube/compileCube) and negates X/Y rotation
  (parseBone/compileBone).

  Therefore, when generating .bbmodel DIRECTLY from geo.json data:

    DO NOT apply X-flip to element positions (from/to).
    DO NOT apply X-flip to bone pivots (origin).
    DO apply X/Y rotation negation: [-rx, -ry, rz]
      (Blockbench internally uses different rotation sign conventions)

  RH→LH Coordinate Corrections (applied in this generator):
    1. North↔South UV Face Swap: The M_model = diag(1,-1,-1) Z-flip maps
       north_RH → south_LH and south_RH → north_LH, so UV data assigned to
       'north' in RH must be moved to 'south' in LH, and vice versa.
       West/East and Up/Down face UVs are NOT swapped.
    2. Geometric X-Mirror for mirrored cubes: When mirror=true, MC 1.12.2
       applies scale(-1,1,1) which mirrors both geometry and UV around the
       bone pivot (X=0 in bone-local space). The geometric mirror (negating
       from/to X coordinates) must be applied in addition to setting
       mirror_uv=true, otherwise mirrored cubes overlap with non-mirrored
       cubes causing a "stacking" visual disorder.
    3. West↔East UV Swap for mirrored cubes: After the geometric X-mirror,
       the face at -X (west) was originally at +X (east) and vice versa,
       so the UV data assigned to 'west' and 'east' must be swapped.
       This swap is in addition to the geometric X-mirror and mirror_uv;
       together the three produce the correct result:
         a) Geometric X-mirror → correct cube position
         b) West↔East UV swap → correct face-UV assignment
         c) mirror_uv=true → correct per-face UV orientation (horizontal mirror)

  Bone pivots (origin) in .bbmodel are RELATIVE to the parent bone, matching
  the geo.json convention. Blockbench adds child mesh to parent mesh in Three.js,
  so the child's position (origin) is automatically relative to the parent.
"""

import base64
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple


# Face direction mapping order used in bbmodel
FACE_NAMES = ["north", "east", "south", "west", "up", "down"]


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
        # Phase 1: Assign UUIDs to all bones and cubes
        # ------------------------------------------------------------------
        bone_uuids: Dict[str, str] = {}  # bone_name -> uuid
        element_uuids: Dict[Tuple[str, int], str] = {}  # (bone_name, cube_idx) -> uuid

        for bone in bones:
            bone_name = bone["name"]
            bone_uuids[bone_name] = self._uuid()
            for cube_idx in range(len(bone.get("cubes", []))):
                element_uuids[(bone_name, cube_idx)] = self._uuid()

        # ------------------------------------------------------------------
        # Phase 2: Build elements (cubes) list
        # ------------------------------------------------------------------
        # Elements use BONE-LOCAL coordinates directly from geo.json:
        #   - Element from/to: cube origin and origin+size (NO X-flip!)
        #   - Element origin:  [0, 0, 0] (rotation center = bone's own pivot)
        #
        # CRITICAL: Do NOT apply X-flip! .bbmodel is Blockbench's internal
        # format and does NOT go through the .geo.json import path that
        # applies X-flip. Applying X-flip here causes mirrored stacking.
        elements = self._build_elements(bones, element_uuids)

        # ------------------------------------------------------------------
        # Phase 3: Build outliner (bone hierarchy)
        # ------------------------------------------------------------------
        # Bone pivots (origin) are RELATIVE to parent bone, directly from
        # geo.json. No X-flip. The field name in .bbmodel is "origin".
        outliner = self._build_outliner(bones, bone_uuids, element_uuids)

        # ------------------------------------------------------------------
        # Phase 4: Build textures list
        # ------------------------------------------------------------------
        textures = self._build_textures(
            texture_path, texture_name, namespace, tex_width, tex_height
        )

        # ------------------------------------------------------------------
        # Phase 5: Build animations
        # ------------------------------------------------------------------
        animations = self._build_animations(anim_json) if anim_json else []

        # ------------------------------------------------------------------
        # Assemble the final .bbmodel structure
        # ------------------------------------------------------------------
        bbmodel = {
            "meta": {
                "format_version": "4.10",
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
    ) -> list:
        """
        Build the flat elements list from all bones' cubes.

        In geo.json, each cube has:
          - origin: [x, y, z]  (minimum corner, relative to bone's pivot)
          - size: [w, h, d]

        In .bbmodel, each element has:
          - from: [x, y, z]  (minimum corner in BONE-LOCAL space, NO X-flip)
          - to: [x+w, y+h, z+d]  (maximum corner in BONE-LOCAL space, NO X-flip)
          - origin: [0, 0, 0]  (rotation center = bone's own pivot)

        CRITICAL: Do NOT apply X-flip to element positions!
        .bbmodel is Blockbench's internal format. The X-flip only happens
        during .geo.json import (parseCube/compileCube), not during .bbmodel
        read/write. Applying X-flip here causes mirrored/stacked models.
        """
        elements = []

        for bone in bones:
            bone_name = bone["name"]

            for cube_idx, cube in enumerate(bone.get("cubes", [])):
                elem_uuid = element_uuids[(bone_name, cube_idx)]
                origin = cube.get("origin", [0.0, 0.0, 0.0])
                size = cube.get("size", [1.0, 1.0, 1.0])
                inflate = cube.get("inflate", 0.0)
                mirror = cube.get("mirror", False)

                # Direct mapping from geo.json cube coordinates to .bbmodel.
                from_pos = [
                    float(origin[0]),                       # X
                    float(origin[1]),                       # Y: direct
                    float(origin[2]),                       # Z: direct
                ]
                to_pos = [
                    float(origin[0]) + float(size[0]),      # X
                    float(origin[1]) + float(size[1]),      # Y: direct
                    float(origin[2]) + float(size[2]),      # Z: direct
                ]

                # Geometric X-mirror for mirrored cubes.
                # In MC 1.12.2, mirror=true causes scale(-1,1,1) which mirrors
                # the cube's geometry around the bone pivot (X=0 in bone-local
                # space). Without this, mirrored cubes stay at the non-mirrored
                # position and overlap with non-mirrored cubes ("stacking").
                if mirror:
                    # Mirror X around bone pivot (X=0 in bone-local space)
                    # Original: [ox, ox+w] → Mirrored: [-(ox+w), -ox]
                    from_x_mirrored = -float(origin[0]) - float(size[0])
                    to_x_mirrored = -float(origin[0])
                    from_pos[0] = from_x_mirrored
                    to_pos[0] = to_x_mirrored
                    # Ensure from[0] <= to[0] (required by .bbmodel format)
                    if from_pos[0] > to_pos[0]:
                        from_pos[0], to_pos[0] = to_pos[0], from_pos[0]

                # Cube origin = rotation center = [0, 0, 0] in bone-local space
                # (The bone's pivot IS the rotation center; in bone-local coords it's at origin)
                bb_origin = [0.0, 0.0, 0.0]

                # Build faces with UV conversion
                faces = self._convert_faces(cube.get("uv", {}))

                # For mirrored cubes, swap West↔East UV faces.
                # After geometric X-mirror, the face at -X (west) was originally at +X (east),
                # so it needs the east UV. Similarly, the face at +X (east) needs the west UV.
                if mirror:
                    west_uv = faces.get("west")
                    east_uv = faces.get("east")
                    if west_uv is not None and east_uv is not None:
                        faces["west"] = east_uv
                        faces["east"] = west_uv

                element = {
                    "name": f"cube",
                    "uuid": elem_uuid,
                    "type": "cube",
                    "resizable": True,
                    "from": from_pos,
                    "to": to_pos,
                    "autouv": 0,
                    "color": 0,
                    "inflate": float(inflate),
                    "mirror_uv": mirror,
                    "rotation": [0.0, 0.0, 0.0],
                    "origin": bb_origin,
                    "uv_offset": [0, 0],
                    "faces": faces,
                }

                elements.append(element)

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

        # North↔South UV Face Swap (RH→LH Z-flip correction)
        # When converting from MC 1.12.2 (RH, Y-down) to .bbmodel (LH, Y-up),
        # the M_model = diag(1, -1, -1) conversion Z-flips the physical faces:
        #   north_RH [0,0,-1] → M_model*[0,0,-1] = [0,0,+1] = south_LH
        #   south_RH [0,0,+1] → M_model*[0,0,+1] = [0,0,-1] = north_LH
        # Therefore the UV that was assigned to 'north' in RH must go to 'south'
        # in LH, and vice versa. West/East and Up/Down do NOT swap.
        north_uv = faces.get("north")
        south_uv = faces.get("south")
        if north_uv is not None and south_uv is not None:
            faces["north"] = south_uv
            faces["south"] = north_uv

        return faces

    # ========================================================================
    # Outliner (Bone Hierarchy) Builder
    # ========================================================================

    def _build_outliner(
        self,
        bones: list,
        bone_uuids: Dict[str, str],
        element_uuids: Dict[Tuple[str, int], str],
    ) -> list:
        """
        Build the outliner (bone hierarchy) from the flat bone list.

        The outliner is a tree structure where:
          - Leaf entries are element UUID strings (references to elements)
          - Branch entries are bone group objects with name, uuid, origin, rotation, children

        Bone parent relationships from geo.json define the tree structure.

        CRITICAL COORDINATE RULES for .bbmodel bone groups:

        1. The field name is "origin" (NOT "pivot") — this is Blockbench's
           internal field name for bone group pivot points.

        2. The origin values are RELATIVE to the parent bone, matching the
           geo.json convention. Blockbench adds child mesh to parent mesh
           in Three.js, so the child's position (origin) is automatically
           relative to the parent.

        3. NO X-flip on origin values. .bbmodel is Blockbench's internal
           format — X-flip only happens during .geo.json import, not during
           .bbmodel read/write.

        4. Rotation X and Y are negated: [-rx, -ry, rz]. This conversion
           IS needed because Blockbench's internal rotation conventions
           differ from geo.json (different Euler angle sign conventions).
           From Blockbench source (parseBone):
             group.rotation.forEach((br, axis) => { if (axis !== 2) group.rotation[axis] *= -1 })
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
                # No parent - truly top-level
                root_bones.append(bone_name)
            else:
                # Has a parent - add to parent's children list
                if parent_name not in children_map:
                    children_map[parent_name] = []
                children_map[parent_name].append(bone_name)

        # Recursively build the outliner tree
        def build_bone_entry(bone_name: str) -> dict:
            """Build a single bone group entry for the outliner."""
            bone = bone_map[bone_name]
            bone_uid = bone_uuids[bone_name]
            rotation = bone.get("rotation", [0.0, 0.0, 0.0])

            children = []

            # Add element UUIDs (cubes belonging to this bone)
            for cube_idx in range(len(bone.get("cubes", []))):
                elem_uuid = element_uuids[(bone_name, cube_idx)]
                children.append(elem_uuid)

            # Add child bone groups
            for child_name in children_map.get(bone_name, []):
                children.append(build_bone_entry(child_name))

            # Use RELATIVE pivot directly from geo.json, NO X-flip.
            # The geo.json already has relative pivots (thanks to
            # _make_pivots_relative in model_converter.py).
            pivot = bone.get("pivot", [0.0, 0.0, 0.0])
            bb_origin_x = float(pivot[0])   # NO X-flip!
            bb_origin_y = float(pivot[1])    # Direct
            bb_origin_z = float(pivot[2])    # Direct

            # Rotation: negate X and Y for Blockbench internal convention.
            # This IS needed — it's not a position flip but a rotation sign
            # convention difference between geo.json and Blockbench internal.
            bb_rot_x = -float(rotation[0])   # X negated
            bb_rot_y = -float(rotation[1])   # Y negated
            bb_rot_z = float(rotation[2])    # Z preserved

            entry = {
                "name": bone_name,
                "uuid": bone_uid,
                "origin": [bb_origin_x, bb_origin_y, bb_origin_z],  # "origin", NOT "pivot"
                "rotation": [bb_rot_x, bb_rot_y, bb_rot_z],
            }

            if children:
                entry["children"] = children

            return entry

        # Build the outliner starting from root-level bones
        outliner = []

        # If there's a "root" bone, it goes first and contains everything
        if "root" in bone_map:
            outliner.append(build_bone_entry("root"))
        else:
            # No explicit root bone - add top-level bones directly
            for bone_name in root_bones:
                outliner.append(build_bone_entry(bone_name))

        return outliner

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

        # Build keyframes from merged time points
        keyframes = []

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

            x_val = axis_data.get("x", (0.0, "linear"))[0]
            y_val = axis_data.get("y", (0.0, "linear"))[0]
            z_val = axis_data.get("z", (0.0, "linear"))[0]

            data_point = {"x": x_val, "y": y_val, "z": z_val, "easing": easing}

            keyframe = {
                "channel": channel_name,
                "data_points": [data_point],
                "uuid": self._uuid(),
                "time": t,
                "color": -1,
                "interpolation": "linear",
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
    print(f"  Outliner:  {len(bbmodel.get('outliner', []))} root entries")
    print(f"  Textures:  {len(bbmodel.get('textures', []))}")
    print(f"  Animations: {len(bbmodel.get('animations', []))}")
