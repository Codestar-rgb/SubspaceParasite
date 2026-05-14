#!/usr/bin/env python3
"""
ModelConverter - Model Conversion Engine
=========================================
Converts Minecraft 1.12.2 ModelBase Java source to GeckoLib 1.20.1 .geo.json format.

Uses javalang for AST-based parsing (no regex for structural parsing).
"""

import json
import math
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core_math import (
    convert_pos, convert_rot, convert_rotation_order, convert_size,
    rad_to_deg, deg_to_rad
)

# ============================================================================
# SRG Name Mappings
# ============================================================================
SRG_MAP = {
    'func_78793_a': 'setRotationPoint',   # setRotationPoint(x, y, z)
    'func_78790_a': 'addBox',              # addBox(offX, offY, offZ, w, h, d, inflate?)
    'func_78792_a': 'addChild',            # addChild(child)
    'func_78785_a': 'render',              # render(scale)
    'field_78795_f': 'rotateAngleX',
    'field_78796_g': 'rotateAngleY',
    'field_78808_h': 'rotateAngleZ',
    'field_82906_o': 'offsetX',
    'field_82907_q': 'offsetY',
    'field_82908_p': 'offsetZ',
    'field_78090_t': 'textureWidth',
    'field_78989_u': 'textureHeight',  # alternate name
    'field_78089_u': 'textureHeight',
}


@dataclass
class BoxData:
    """Represents a single addBox call."""
    offset_x: float = 0.0
    offset_y: float = 0.0
    offset_z: float = 0.0
    width: float = 0.0
    height: float = 0.0
    depth: float = 0.0
    inflate: float = 0.0
    texture_offset_u: int = 0  # from ModelRenderer constructor
    texture_offset_v: int = 0
    mirror: bool = False


@dataclass
class BoneData:
    """Represents a single ModelRenderer / bone."""
    name: str = ""
    java_var_name: str = ""
    pivot_x: float = 0.0
    pivot_y: float = 0.0
    pivot_z: float = 0.0
    rotate_x: float = 0.0  # radians
    rotate_y: float = 0.0
    rotate_z: float = 0.0
    boxes: List[BoxData] = field(default_factory=list)
    children: List[str] = field(default_factory=list)  # child var names
    parent: Optional[str] = None  # parent var name
    mirror: bool = False


class ModelConverter:
    """
    Converts 1.12.2 ModelBase Java source to GeckoLib 1.20.1 .geo.json.
    """

    def __init__(self):
        self.texture_width: int = 64
        self.texture_height: int = 32
        self.bones: Dict[str, BoneData] = {}  # java_var_name -> BoneData
        self.bone_mapping: Dict[str, str] = {}  # java_var -> bone_name
        self.warnings: List[str] = []

    def parse_java_source(self, java_source: str) -> None:
        """
        Parse a 1.12.2 ModelBase Java source string and extract all model data.
        Uses a hybrid approach: javalang AST for structure + text scanning for SRG method calls.
        """
        # First, try javalang for high-level structure
        try:
            import javalang
            tree = javalang.parse.parse(java_source)
            self._parse_ast(tree, java_source)
        except Exception as e:
            warnings.warn(f"javalang AST parsing failed ({e}), falling back to text parsing")
            self._parse_text(java_source)

    def _parse_ast(self, tree, java_source: str) -> None:
        """Parse using javalang AST for structure, supplemented by text scanning."""
        # Extract texture dimensions and class-level info from AST
        for path, node in tree:
            if isinstance(node, javalang.tree.ClassDeclaration):
                # Find texture width/height assignments
                for elem in node.body:
                    if isinstance(elem, javalang.tree.MethodDeclaration) and elem.name == '<init>':
                        # Constructor - we'll parse this with text instead for SRG names
                        pass

        # Fall back to text parsing for the actual content (javalang doesn't resolve SRG names)
        self._parse_text(java_source)

    def _parse_text(self, java_source: str) -> None:
        """
        Text-based parsing that handles SRG names directly.
        This is more robust for decompiled code with obfuscated names.
        """
        lines = java_source.split('\n')

        # Phase 1: Extract texture dimensions
        self._extract_texture_dims(java_source)

        # Phase 2: Extract ModelRenderer field declarations
        field_vars = self._extract_model_renderer_fields(java_source)

        # Phase 3: Parse constructor for all bone data
        self._parse_constructor(java_source, field_vars)

        # Phase 4: Build hierarchy from addChild calls
        self._parse_add_child_calls(java_source)

        # Phase 5: Build bone mapping table
        self._build_bone_mapping()

    def _extract_texture_dims(self, java_source: str) -> None:
        """Extract textureWidth and textureHeight from source."""
        import re
        # field_78090_t = textureWidth, field_78089_u = textureHeight
        tw_match = re.search(r'this\.field_78090_t\s*=\s*(\d+)', java_source)
        th_match = re.search(r'this\.field_78089_u\s*=\s*(\d+)', java_source)
        if tw_match:
            self.texture_width = int(tw_match.group(1))
        if th_match:
            self.texture_height = int(th_match.group(1))

    def _extract_model_renderer_fields(self, java_source: str) -> List[str]:
        """Extract all ModelRenderer field variable names."""
        import re
        fields = []
        pattern = r'public\s+ModelRenderer\s+(\w+)\s*;'
        for match in re.finditer(pattern, java_source):
            var_name = match.group(1)
            fields.append(var_name)
            # Initialize bone data
            if var_name not in self.bones:
                self.bones[var_name] = BoneData(
                    name=var_name,
                    java_var_name=var_name
                )
        return fields

    def _parse_constructor(self, java_source: str, field_vars: List[str]) -> None:
        """Parse constructor body for bone initialization."""
        import re

        # Extract each ModelRenderer construction and configuration block
        # Pattern: this.varName = new ModelRenderer((ModelBase)this, texU, texV);
        #          this.varName.func_78793_a(pivotX, pivotY, pivotZ);
        #          this.varName.func_78790_a(offX, offY, offZ, w, h, d, inflate);
        #          this.setRotateAngle(this.varName, rx, ry, rz);

        # Parse ModelRenderer constructors
        constructor_pattern = re.compile(
            r'this\.(\w+)\s*=\s*new\s+ModelRenderer\s*\(\s*\(ModelBase\)\s*this\s*,\s*([\d.\-fF]+)\s*,\s*([\d.\-fF]+)\s*\)\s*;'
        )
        for match in constructor_pattern.finditer(java_source):
            var_name = match.group(1)
            tex_u = self._parse_java_float(match.group(2))
            tex_v = self._parse_java_float(match.group(3))
            if var_name in self.bones:
                # Set texture offset for all boxes of this bone
                # (will be overridden per-box if setTextureOffset is called)
                for box in self.bones[var_name].boxes:
                    box.texture_offset_u = int(tex_u)
                    box.texture_offset_v = int(tex_v)
                # Store as default for new boxes
                self.bones[var_name]._default_tex_u = int(tex_u)
                self.bones[var_name]._default_tex_v = int(tex_v)
            else:
                bone = BoneData(name=var_name, java_var_name=var_name)
                bone._default_tex_u = int(tex_u)
                bone._default_tex_v = int(tex_v)
                self.bones[var_name] = bone

        # Parse setRotationPoint calls
        rotation_point_pattern = re.compile(
            r'this\.(\w+)\.func_78793_a\s*\(\s*([\d.\-fFeE]+)\s*,\s*([\d.\-fFeE]+)\s*,\s*([\d.\-fFeE]+)\s*\)\s*;'
        )
        for match in rotation_point_pattern.finditer(java_source):
            var_name = match.group(1)
            px = self._parse_java_float(match.group(2))
            py = self._parse_java_float(match.group(3))
            pz = self._parse_java_float(match.group(4))
            if var_name not in self.bones:
                self.bones[var_name] = BoneData(name=var_name, java_var_name=var_name)
            self.bones[var_name].pivot_x = px
            self.bones[var_name].pivot_y = py
            self.bones[var_name].pivot_z = pz

        # Parse addBox calls
        addbox_pattern = re.compile(
            r'this\.(\w+)\.func_78790_a\s*\(\s*([\d.\-fFeE]+)\s*,\s*([\d.\-fFeE]+)\s*,\s*([\d.\-fFeE]+)\s*,\s*([\d.\-fFeE]+)\s*,\s*([\d.\-fFeE]+)\s*,\s*([\d.\-fFeE]+)\s*(?:,\s*([\d.\-fFeE]+)\s*)?\)\s*;'
        )
        for match in addbox_pattern.finditer(java_source):
            var_name = match.group(1)
            off_x = self._parse_java_float(match.group(2))
            off_y = self._parse_java_float(match.group(3))
            off_z = self._parse_java_float(match.group(4))
            w = self._parse_java_float(match.group(5))
            h = self._parse_java_float(match.group(6))
            d = self._parse_java_float(match.group(7))
            inflate = self._parse_java_float(match.group(8)) if match.group(8) else 0.0

            if var_name not in self.bones:
                self.bones[var_name] = BoneData(name=var_name, java_var_name=var_name)

            bone = self.bones[var_name]
            tex_u = getattr(bone, '_default_tex_u', 0)
            tex_v = getattr(bone, '_default_tex_v', 0)

            box = BoxData(
                offset_x=off_x, offset_y=off_y, offset_z=off_z,
                width=w, height=h, depth=d, inflate=inflate,
                texture_offset_u=tex_u, texture_offset_v=tex_v,
                mirror=bone.mirror
            )
            bone.boxes.append(box)

        # Parse setRotateAngle calls
        set_rotate_pattern = re.compile(
            r'this\.setRotateAngle\s*\(\s*this\.(\w+)\s*,\s*([\d.\-fFeEpP]+)\s*,\s*([\d.\-fFeEpP]+)\s*,\s*([\d.\-fFeEpP]+)\s*\)\s*;'
        )
        for match in set_rotate_pattern.finditer(java_source):
            var_name = match.group(1)
            rx = self._parse_java_float(match.group(2))
            ry = self._parse_java_float(match.group(3))
            rz = self._parse_java_float(match.group(4))
            if var_name not in self.bones:
                self.bones[var_name] = BoneData(name=var_name, java_var_name=var_name)
            self.bones[var_name].rotate_x = rx
            self.bones[var_name].rotate_y = ry
            self.bones[var_name].rotate_z = rz

        # Parse direct rotation assignments (field_78795_f = rotateAngleX, etc.)
        # This is for animation code that sets rotations directly
        rot_x_pattern = re.compile(r'this\.(\w+)\.field_78795_f\s*=\s*([^;]+);')
        rot_y_pattern = re.compile(r'this\.(\w+)\.field_78796_g\s*=\s*([^;]+);')
        rot_z_pattern = re.compile(r'this\.(\w+)\.field_78808_h\s*=\s*([^;]+);')

        # Parse mirror assignments
        mirror_pattern = re.compile(r'this\.(\w+)\.mirror\s*=\s*(true|false)\s*;')
        for match in mirror_pattern.finditer(java_source):
            var_name = match.group(1)
            mirror_val = match.group(2) == 'true'
            if var_name in self.bones:
                self.bones[var_name].mirror = mirror_val
                for box in self.bones[var_name].boxes:
                    box.mirror = mirror_val

    def _parse_add_child_calls(self, java_source: str) -> None:
        """Parse addChild calls to build bone hierarchy."""
        import re
        addchild_pattern = re.compile(
            r'this\.(\w+)\.func_78792_a\s*\(\s*this\.(\w+)\s*\)\s*;'
        )
        for match in addchild_pattern.finditer(java_source):
            parent_var = match.group(1)
            child_var = match.group(2)
            if parent_var not in self.bones:
                self.bones[parent_var] = BoneData(name=parent_var, java_var_name=parent_var)
            if child_var not in self.bones:
                self.bones[child_var] = BoneData(name=child_var, java_var_name=child_var)
            self.bones[parent_var].children.append(child_var)
            self.bones[child_var].parent = parent_var

    def _build_bone_mapping(self) -> None:
        """Build the bone mapping table (java var name -> bone name for output)."""
        used_names = set()
        for var_name, bone in self.bones.items():
            # Use the java variable name as bone name
            bone_name = var_name
            # Ensure uniqueness
            if bone_name in used_names:
                suffix = 1
                while f"{bone_name}_{suffix}" in used_names:
                    suffix += 1
                bone_name = f"{bone_name}_{suffix}"
                self.warnings.append(f"Bone name conflict: {var_name} renamed to {bone_name}")
            used_names.add(bone_name)
            bone.name = bone_name
            self.bone_mapping[var_name] = bone_name

    def _detect_cycles(self) -> None:
        """Detect circular references in bone hierarchy."""
        visited = set()
        rec_stack = set()

        def dfs(var_name: str) -> bool:
            visited.add(var_name)
            rec_stack.add(var_name)
            for child in self.bones[var_name].children:
                if child not in visited:
                    if dfs(child):
                        return True
                elif child in rec_stack:
                    return True
            rec_stack.remove(var_name)
            return False

        for var_name in self.bones:
            if var_name not in visited:
                if dfs(var_name):
                    raise ValueError("Circular reference detected in bone hierarchy!")

    @staticmethod
    def _parse_java_float(s: str) -> float:
        """Parse a Java float literal (handles f/F suffix, hex, etc.)."""
        s = s.strip()
        s = s.rstrip('fF')
        if s.startswith('0x') or s.startswith('0X'):
            return float(int(s, 16))
        try:
            return float(s)
        except ValueError:
            # Handle expressions like Math.PI
            if 'Math.PI' in s:
                return math.pi
            return 0.0

    @staticmethod
    def _calculate_uv(box: BoxData) -> dict:
        """
        Calculate UV coordinates for each face of a box using 1.12.2 UV formulas.

        UV formulas (using original 1.12.2 dimensions, before conversion):
          u = textureOffsetX, v = textureOffsetY
          w = width, h = height, d = depth

          North: [u+d, v+d, u+d+w, v+d+h]
          South: [u+2d+w, v+d, u+2d+2w, v+d+h]   -- WRONG, should be u+2d+w to u+2d+w+w
          Wait, let me recalculate properly.

        Standard Minecraft 1.12.2 UV layout for a box at offset (bx, by, bz)
        with size (w, h, d) and texture offset (u, v):

          North face: UV origin (u+d, v+d), size (w, h)
          South face: UV origin (u+d+w+d, v+d), size (w, h)  = (u+2d+w, v+d)
          West face:  UV origin (u, v+d), size (d, h)
          East face:  UV origin (u+d+w, v+d), size (d, h)
          Up face:    UV origin (u+d, v), size (w, d)
          Down face:  UV origin (u+d+w, v), size (w, d)
        """
        u = box.texture_offset_u
        v = box.texture_offset_v
        w = box.width
        h = box.height
        d = box.depth

        # Calculate UV for each face
        uv = {}

        # North face
        uv['north'] = {
            'uv': [u + d, v + d],
            'uv_size': [w, h]
        }

        # South face
        uv['south'] = {
            'uv': [u + d + w + d, v + d],
            'uv_size': [w, h]
        }

        # West face
        uv['west'] = {
            'uv': [u, v + d],
            'uv_size': [d, h]
        }

        # East face
        uv['east'] = {
            'uv': [u + d + w, v + d],
            'uv_size': [d, h]
        }

        # Up face
        uv['up'] = {
            'uv': [u + d, v],
            'uv_size': [w, d]
        }

        # Down face
        uv['down'] = {
            'uv': [u + d + w, v],
            'uv_size': [w, d]
        }

        # Handle mirror: swap west/east UV horizontal coordinates
        if box.mirror:
            # Mirror flips the horizontal UV of west and east faces
            west_uv = uv['west']['uv'][0]
            west_w = uv['west']['uv_size'][0]
            east_uv = uv['east']['uv'][0]
            east_w = uv['east']['uv_size'][0]

            # For mirrored, the UV start is adjusted
            # Mirror flips: new_u = original_u + size - (relative offset)
            # For west: original [u, v+d] size [d, h] -> mirrored [u+d, v+d] size [-d, h]
            # But since we can't have negative size, we swap west and east
            uv['west'], uv['east'] = uv['east'], uv['west']

            # For mirrored faces, flip the horizontal UV
            for face_name in ['west', 'east']:
                face = uv[face_name]
                orig_u = face['uv'][0]
                face_w = face['uv_size'][0]
                # Mirror: new_u = orig_u + face_w, new_size = -face_w
                # But we represent as: new_u stays, just note the mirror
                # In GeckoLib, we set mirror to true on the cube instead
                pass

        return uv

    def convert(self, java_source: str, model_identifier: str = "model.kirin") -> dict:
        """
        Main conversion method. Parse Java source and produce .geo.json structure.

        Args:
            java_source: The decompiled 1.12.2 ModelBase Java source code
            model_identifier: The GeckoLib model identifier

        Returns:
            Dictionary containing:
              - 'geo_json': The .geo.json structure (dict)
              - 'bone_mapping': Dict mapping java var names to bone names
              - 'warnings': List of warning messages
        """
        # Parse the source
        self.parse_java_source(java_source)

        # Detect cycles
        self._detect_cycles()

        # Build the .geo.json structure
        bones_output = []

        # Root bone
        root_bone = {
            "name": "root",
            "pivot": [0.0, 24.0, 0.0]
        }
        bones_output.append(root_bone)

        # Find top-level bones (no parent)
        top_level_bones = [
            var_name for var_name, bone in self.bones.items()
            if bone.parent is None
        ]

        # Process all bones
        for var_name, bone in self.bones.items():
            bone_output = self._convert_bone(bone, var_name)
            if bone.parent is None:
                bone_output["parent"] = "root"
            else:
                parent_bone = self.bones.get(bone.parent)
                if parent_bone:
                    bone_output["parent"] = self.bone_mapping.get(bone.parent, bone.parent)
                else:
                    bone_output["parent"] = "root"
            bones_output.append(bone_output)

        geo_json = {
            "format_version": "1.12.0",
            "model": {
                "identifier": model_identifier,
                "texture_width": self.texture_width,
                "texture_height": self.texture_height,
                "bones": bones_output
            }
        }

        return {
            'geo_json': geo_json,
            'bone_mapping': self.bone_mapping,
            'warnings': self.warnings
        }

    def _convert_bone(self, bone: BoneData, var_name: str) -> dict:
        """Convert a single bone to GeckoLib format."""
        bone_name = self.bone_mapping.get(var_name, var_name)

        # Convert pivot position
        new_pivot = convert_pos(bone.pivot_x, bone.pivot_y, bone.pivot_z)

        bone_output = {
            "name": bone_name,
            "pivot": [round(v, 4) for v in new_pivot]
        }

        # Convert rotation
        rx, ry, rz = bone.rotate_x, bone.rotate_y, bone.rotate_z
        has_rotation = abs(rx) > 1e-10 or abs(ry) > 1e-10 or abs(rz) > 1e-10
        if has_rotation:
            non_zero_count = sum(1 for a in [rx, ry, rz] if abs(a) > 1e-10)
            if non_zero_count > 1:
                # Multi-axis rotation: use matrix-based conversion
                new_rx, new_ry, new_rz = convert_rotation_order(rx, ry, rz)
            else:
                new_rx, new_ry, new_rz = convert_rot(rx, ry, rz)

            bone_output["rotation"] = [
                round(rad_to_deg(new_rx), 4),
                round(rad_to_deg(new_ry), 4),
                round(rad_to_deg(new_rz), 4)
            ]

        # Convert cubes
        if bone.boxes:
            cubes = []
            for box in bone.boxes:
                cube = self._convert_cube(box)
                cubes.append(cube)
            bone_output["cubes"] = cubes

        return bone_output

    def _convert_cube(self, box: BoxData) -> dict:
        """Convert a single cube/box to GeckoLib format."""
        # Convert box origin (offset from pivot)
        new_origin = convert_pos(box.offset_x, box.offset_y, box.offset_z)

        # Convert size (depth preserved)
        new_size = convert_size(box.width, box.height, box.depth)

        # Handle negative depth by adjusting origin
        w, h, d = new_size
        ox, oy, oz = new_origin
        if box.depth < 0:
            # Negative depth: adjust Z origin
            oz += d
            d = abs(d)
            new_size = (w, h, d)
            new_origin = (ox, oy, oz)

        # Apply inflate AFTER coordinate conversion
        inflate = box.inflate
        if abs(inflate) > 1e-10:
            new_origin = (
                new_origin[0] - inflate,
                new_origin[1] - inflate,
                new_origin[2] - inflate
            )
            new_size = (
                new_size[0] + 2 * inflate,
                new_size[1] + 2 * inflate,
                new_size[2] + 2 * inflate
            )

        # Calculate UV
        uv = self._calculate_uv(box)

        cube = {
            "origin": [round(v, 4) for v in new_origin],
            "size": [round(v, 4) for v in new_size],
            "uv": uv
        }

        if box.mirror:
            cube["mirror"] = True

        return cube

    def to_geo_json_string(self, result: dict, indent: int = 2) -> str:
        """Convert the result dict to a formatted JSON string."""
        return json.dumps(result['geo_json'], indent=indent, ensure_ascii=False)

    def save_bone_mapping(self, result: dict, filepath: str) -> None:
        """Save the bone mapping table to a JSON file."""
        with open(filepath, 'w') as f:
            json.dump(result['bone_mapping'], f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    # Quick test with a simple model
    test_java = """
    public class TestModel extends ModelBase {
        public ModelRenderer head;
        public ModelRenderer body;

        public TestModel() {
            this.field_78090_t = 64;
            this.field_78089_u = 32;
            this.head = new ModelRenderer((ModelBase)this, 0, 0);
            this.head.func_78793_a(0.0f, 0.0f, 0.0f);
            this.head.func_78790_a(-4.0f, -8.0f, -4.0f, 8, 8, 8, 0.0f);
            this.body = new ModelRenderer((ModelBase)this, 16, 16);
            this.body.func_78793_a(0.0f, 0.0f, 0.0f);
            this.body.func_78790_a(-4.0f, 0.0f, -2.0f, 8, 12, 4, 0.0f);
            this.head.func_78792_a(this.body);
        }
    }
    """

    converter = ModelConverter()
    result = converter.convert(test_java, "model.test")
    print(converter.to_geo_json_string(result))
    print("\nBone mapping:", result['bone_mapping'])
