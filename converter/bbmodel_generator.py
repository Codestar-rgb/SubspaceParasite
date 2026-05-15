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
        # Phase 1.5: Compute absolute pivots for outliner bone positioning
        # ------------------------------------------------------------------
        # Blockbench .bbmodel uses ABSOLUTE world-space for bone pivots in the
        # outliner. Blockbench internally computes relative positions via:
        #   mesh.position = group.origin - parent.origin
        # Therefore, the pivot stored in .bbmodel must be absolute, so the
        # subtraction yields the correct relative offset.
        abs_pivots = self._compute_absolute_pivots(bones)

        # ------------------------------------------------------------------
        # Phase 2: Build elements (cubes) list
        # ------------------------------------------------------------------
        # Elements use BONE-LOCAL coordinates:
        #   - Element from/to: relative to the bone's own pivot
        #   - Element origin:  [0, 0, 0] (the bone's pivot IS the rotation center)
        #
        # Coordinate X-flip: Blockbench's internal system for bedrock models has
        # the X axis flipped relative to geo.json. Applied to element from/to.
        elements = self._build_elements(bones, element_uuids)

        # ------------------------------------------------------------------
        # Phase 3: Build outliner (bone hierarchy)
        # ------------------------------------------------------------------
        # Bone pivots in ABSOLUTE world-space (with X-flip for Blockbench)
        outliner = self._build_outliner(bones, bone_uuids, element_uuids, abs_pivots)

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
    # Absolute Pivot Computation
    # ========================================================================

    @staticmethod
    def _compute_absolute_pivots(bones: list) -> Dict[str, list]:
        """
        Compute absolute world-space pivots for all bones by walking the hierarchy.

        In geo.json, bone pivots are relative to their parent bone.
        We accumulate them to get each bone's world position.

        Blockbench .bbmodel requires ABSOLUTE pivots because it internally
        computes relative positions via: mesh.position = group.origin - parent.origin

        Returns:
            Dict mapping bone_name -> [abs_x, abs_y, abs_z]
        """
        bone_map: Dict[str, dict] = {b["name"]: b for b in bones}

        children_map: Dict[str, list] = {}
        root_bones: list = []

        for bone in bones:
            bone_name = bone["name"]
            parent_name = bone.get("parent")
            if parent_name is None:
                root_bones.append(bone_name)
            else:
                children_map.setdefault(parent_name, []).append(bone_name)

        abs_pivots: Dict[str, list] = {}

        def _accumulate(bone_name: str, parent_abs: list) -> None:
            bone = bone_map[bone_name]
            rel_pivot = bone.get("pivot", [0.0, 0.0, 0.0])
            abs_piv = [
                parent_abs[0] + float(rel_pivot[0]),
                parent_abs[1] + float(rel_pivot[1]),
                parent_abs[2] + float(rel_pivot[2]),
            ]
            abs_pivots[bone_name] = abs_piv
            for child_name in children_map.get(bone_name, []):
                _accumulate(child_name, abs_piv)

        for bone_name in root_bones:
            bone = bone_map[bone_name]
            pivot = bone.get("pivot", [0.0, 0.0, 0.0])
            abs_piv = [float(pivot[0]), float(pivot[1]), float(pivot[2])]
            abs_pivots[bone_name] = abs_piv
            for child_name in children_map.get(bone_name, []):
                _accumulate(child_name, abs_piv)

        return abs_pivots

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

        In .bbmodel (bedrock format), each element has:
          - from: [x, y, z]  (minimum corner in BONE-LOCAL space)
          - to: [x+w, y+h, z+d]  (maximum corner in BONE-LOCAL space)
          - origin: [0, 0, 0]  (rotation center = bone's own pivot, at origin in bone-local)

        CRITICAL: Blockbench bedrock format uses BONE-LOCAL coordinates for elements.
        The bone's pivot is the rotation center for all its cubes. In bone-local
        space, the pivot is at [0, 0, 0]. The bone's position in the model is
        defined by the outliner's hierarchical pivot/rotation chain.

        Coordinate X-flip: Blockbench's internal system for bedrock models has
        the X axis flipped relative to geo.json:
          - bb_from_x = -(geo_origin_x + size_x)
          - bb_to_x = -geo_origin_x
        This is based on Blockbench source code (bedrock.js parseCube/compileCube).
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

                # Use bone-local coordinates directly from geo.json
                # (cube origin is already relative to bone's pivot)
                # Apply X-flip for Blockbench bedrock format:
                #   bb_from_x = -(origin_x + size_x)
                #   bb_to_x = -origin_x
                from_pos = [
                    -(float(origin[0]) + float(size[0])),  # X flip
                    float(origin[1]),                       # Y same
                    float(origin[2]),                       # Z same
                ]
                to_pos = [
                    -float(origin[0]),                       # X flip
                    float(origin[1]) + float(size[1]),       # Y same
                    float(origin[2]) + float(size[2]),       # Z same
                ]

                # Cube origin = rotation center = [0, 0, 0] in bone-local space
                # (The bone's pivot IS the rotation center; in bone-local coords it's at origin)
                bb_origin = [0.0, 0.0, 0.0]

                # Build faces with UV conversion
                faces = self._convert_faces(cube.get("uv", {}))

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

        return faces

    # ========================================================================
    # Outliner (Bone Hierarchy) Builder
    # ========================================================================

    def _build_outliner(
        self,
        bones: list,
        bone_uuids: Dict[str, str],
        element_uuids: Dict[Tuple[str, int], str],
        abs_pivots: Dict[str, list],
    ) -> list:
        """
        Build the outliner (bone hierarchy) from the flat bone list.

        The outliner is a tree structure where:
          - Leaf entries are element UUID strings (references to elements)
          - Branch entries are bone group objects with name, uuid, pivot, rotation, children

        Bone parent relationships from geo.json define the tree structure.

        CRITICAL: .bbmodel bone pivots must be ABSOLUTE world-space coordinates.
        Blockbench internally computes relative positions via:
          mesh.position = group.origin - parent.origin
        Therefore, the pivot stored in .bbmodel must be absolute, so the
        subtraction yields the correct relative offset.

        Example:
          root pivot [0,24,0], mainbody pivot [0,53,16] (relative in geo.json)
          Absolute mainbody pivot = [0,77,16]
          Blockbench computes: [0,77,16] - [0,24,0] = [0,53,16] ✓
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

            # Use ABSOLUTE pivot with X-flipped for Blockbench coordinate system
            # Blockbench computes relative position via: child.origin - parent.origin
            # So we must provide absolute world-space pivots.
            abs_pivot = abs_pivots.get(bone_name, [0.0, 0.0, 0.0])
            bb_pivot_x = -float(abs_pivot[0])  # X flip
            bb_pivot_y = float(abs_pivot[1])
            bb_pivot_z = float(abs_pivot[2])

            # Rotation also needs X/Y flip for Blockbench
            # From Blockbench source: group.rotation.forEach((br, axis) => { if (axis !== 2) group.rotation[axis] *= -1 })
            bb_rot_x = -float(rotation[0])
            bb_rot_y = -float(rotation[1])
            bb_rot_z = float(rotation[2])

            entry = {
                "name": bone_name,
                "uuid": bone_uid,
                "pivot": [bb_pivot_x, bb_pivot_y, bb_pivot_z],
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
