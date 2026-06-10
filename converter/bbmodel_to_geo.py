#!/usr/bin/env python3
"""
BBModel to Geo.json Converter (GeckoLib/Bedrock Format)
========================================================
Converts Blockbench .bbmodel files to Bedrock geo.json format
compatible with GeckoLib for Minecraft 1.20.1 Forge mod development,
and extracts embedded texture PNGs.

Output per model:
  <category>/<modelName>.geo.json   - Bedrock/GeckoLib geometry definition
  <category>/<modelName>.png        - Texture file

Coordinate System (bbmodel -> geo.json):
  Both .bbmodel and geo.json use the SAME Y-up left-hand coordinate system.
  No coordinate transformation is needed — positions and rotations pass
  through directly.

  The key conversions are:
  1. ABSOLUTE → RELATIVE pivots:
     - Root bone: pivot = group origin (absolute in entity space)
     - Child bones: pivot = child_origin - parent_origin (relative to parent)
  2. ABSOLUTE → RELATIVE cube origins:
     - Cube origin = element_from - bone_origin (relative to bone's pivot)
  3. Root 180° Y rotation is REMOVED:
     - The 180° Y rotation on root was a RH→LH compensation hack from the
       Java→bbmodel conversion pipeline. It's not needed in geo.json because
       both formats use the same Y-up LH coordinate system.
  4. Virtual root_offset bone is SKIPPED:
     - It was only used in .bbmodel to separate the 180° rotation from
       animations targeting "root".

Rotation:
  - Pass through directly — no conversion needed (same coordinate system)

UV Conversion:
  - Side faces (N/E/S/W): uv=[u1,v1], uv_size=[u2-u1, v2-v1]
  - Up/Down faces: uv=[u2,v2], uv_size=[-(u2-u1), -(v2-v1)]
"""

import base64
import json
import math
import os
import sys
import traceback
from typing import Dict, List, Optional, Tuple


class BBModelToGeo:
    """Converts .bbmodel files to Bedrock/GeckoLib geo.json format with texture extraction."""

    # Virtual bones to skip during conversion
    VIRTUAL_BONES = {'root_offset'}

    def convert_bbmodel(self, bbmodel_path: str, output_dir: str) -> dict:
        try:
            with open(bbmodel_path, 'r', encoding='utf-8') as f:
                bb = json.load(f)

            short_name = bb.get('model_identifier', bb.get('name', 'unknown'))
            res = bb.get('resolution', {})
            tw, th = res.get('width', 256), res.get('height', 256)

            groups = bb.get('groups', [])
            elements = bb.get('elements', [])
            outliner = bb.get('outliner', [])

            # Build bone info from groups (skip virtual bones)
            bone_map = {g['uuid']: g for g in groups if g.get('name') not in self.VIRTUAL_BONES}

            # Parse outliner for parent-child relationships
            parent_map = {}
            self._parse_outliner(outliner, None, bone_map, parent_map)

            # Map element uuids to bones
            elem_to_bone = {}
            self._map_elems_recursive(outliner, None, elem_to_bone)

            # Build absolute pivot lookup from group origins
            abs_pivots = {}
            for g in groups:
                if g.get('name') not in self.VIRTUAL_BONES:
                    origin = g.get('origin', [0, 24, 0])
                    abs_pivots[g['uuid']] = [float(v) for v in origin]

            # Build geo.json bones
            geo_bones = self._build_geo_bones(
                groups, elements, bone_map, parent_map, elem_to_bone, abs_pivots
            )

            # Compute visible bounds from model data
            vbw, vbh, vbo = self._compute_visible_bounds(groups, elements)

            # Assemble geo.json
            geo_json = {
                "format_version": "1.12.0",
                "minecraft:geometry": [{
                    "description": {
                        "identifier": f"geometry.model.{short_name}",
                        "texture_width": tw,
                        "texture_height": th,
                        "visible_bounds_width": vbw,
                        "visible_bounds_height": vbh,
                        "visible_bounds_offset": vbo
                    },
                    "bones": geo_bones
                }]
            }

            # Save geo.json
            os.makedirs(output_dir, exist_ok=True)
            geo_path = os.path.join(output_dir, f"{short_name}.geo.json")
            with open(geo_path, 'w', encoding='utf-8') as f:
                json.dump(geo_json, f, indent=2, ensure_ascii=False)

            # Extract texture PNG
            texture_path = None
            for tx in bb.get('textures', []):
                src = tx.get('source', '')
                if src.startswith('data:image/png;base64,'):
                    b64_data = src[len('data:image/png;base64,'):]
                    png_data = base64.b64decode(b64_data)
                    texture_path = os.path.join(output_dir, f"{short_name}.png")
                    with open(texture_path, 'wb') as f:
                        f.write(png_data)
                    break

            total_bones = len(geo_bones)
            total_cubes = sum(len(b.get('cubes', [])) for b in geo_bones)

            return {
                'success': True,
                'geo_path': geo_path,
                'texture_path': texture_path,
                'stats': {
                    'bones': total_bones,
                    'cubes': total_cubes,
                    'texture_size': f"{tw}x{th}",
                    'has_texture': texture_path is not None,
                }
            }

        except Exception as e:
            return {
                'success': False,
                'error': f"{type(e).__name__}: {e}",
                'traceback': traceback.format_exc(),
            }

    def _compute_visible_bounds(self, groups, elements):
        """Compute visible_bounds_width, height, offset from model data.

        Uses generous defaults matching Blockbench's export convention.
        visible_bounds_width is in 1/16th block units (pixels), divided by 16
        to get block units, with generous padding for animations.
        """
        if not elements:
            return 2, 3, [0, 1.5, 0]

        # Find bounding box of all elements
        min_x = min(e.get('from', [0,0,0])[0] for e in elements)
        min_y = min(e.get('from', [0,0,0])[1] for e in elements)
        max_x = max(e.get('to', [0,0,0])[0] for e in elements)
        max_y = max(e.get('to', [0,0,0])[1] for e in elements)
        max_z = max(e.get('to', [0,0,0])[2] for e in elements)
        min_z = min(e.get('from', [0,0,0])[2] for e in elements)

        # Width = max extent in X or Z
        width_x = abs(max_x - min_x)
        width_z = abs(max_z - min_z)
        total_width = max(width_x, width_z)

        # Height
        total_height = abs(max_y - min_y)

        # Use generous bounds matching Blockbench convention
        # visible_bounds are in block units, add 50% margin for animations
        vbw = max(2, math.ceil(total_width * 1.5 / 16))
        vbh = max(3, math.ceil(total_height * 1.2 / 16))

        # Offset: center vertically around model midpoint
        center_y = (min_y + max_y) / 2.0
        vbo_y = round(center_y / 16, 1)

        return vbw, vbh, [0, max(1, vbo_y), 0]

    def _parse_outliner(self, outliner, parent_uuid, bone_map, parent_map):
        """Recursively parse outliner tree to build parent-child relationships.
        
        Skips virtual bones (root_offset) — children of virtual bones are
        reparented to the virtual bone's parent.
        """
        for entry in outliner:
            if isinstance(entry, dict):
                uid = entry.get('uuid')
                if uid and uid in bone_map:
                    # This is a real bone — set parent if we have one
                    if parent_uuid is not None and parent_uuid in bone_map:
                        parent_map[uid] = parent_uuid
                    # Recurse with this bone as parent
                    self._parse_outliner(
                        entry.get('children', []), uid, bone_map, parent_map
                    )
                elif uid and uid not in bone_map:
                    # This is a virtual bone — skip it, but process its children
                    # with the current parent_uuid (reparent children to virtual bone's parent)
                    self._parse_outliner(
                        entry.get('children', []), parent_uuid, bone_map, parent_map
                    )
                else:
                    self._parse_outliner(
                        entry.get('children', []), parent_uuid, bone_map, parent_map
                    )

    def _map_elems_recursive(self, items, bone_uid, elem_to_bone):
        """Map element UUIDs to their parent bone UUIDs from the outliner."""
        for item in items:
            if isinstance(item, str) and bone_uid:
                elem_to_bone[item] = bone_uid
            elif isinstance(item, dict):
                self._map_elems_recursive(
                    item.get('children', []), item.get('uuid'), elem_to_bone
                )

    def _build_geo_bones(self, groups, elements, bone_map, parent_map, elem_to_bone, abs_pivots):
        """Build geo.json bones array from bbmodel data.

        Key principles:
        1. Both .bbmodel and geo.json use Y-up left-hand coordinate system
        2. No coordinate transformation needed — pass through directly
        3. Pivots are RELATIVE to parent (not absolute)
        4. Cube origins are RELATIVE to bone's pivot (not absolute)
        5. Root bone's 180° Y rotation is REMOVED (was a RH→LH hack)
        6. Virtual bones (root_offset) are skipped
        """
        # UUID to name lookup
        uid2name = {g['uuid']: g['name'] for g in groups if g.get('name') not in self.VIRTUAL_BONES}

        # Elements by bone
        elems_by_bone: Dict[str, list] = {}
        for elem in elements:
            bu = elem_to_bone.get(elem.get('uuid'))
            if bu and bu in bone_map:
                elems_by_bone.setdefault(bu, []).append(elem)

        geo_bones = []
        for g in groups:
            bone_name = g.get('name', '')
            
            # Skip virtual bones
            if bone_name in self.VIRTUAL_BONES:
                continue
                
            bone_uid = g['uuid']
            abs_pivot = abs_pivots.get(bone_uid, [0.0, 24.0, 0.0])

            # Compute relative pivot
            parent_uid = parent_map.get(bone_uid)
            if parent_uid is not None and parent_uid in abs_pivots:
                parent_abs = abs_pivots[parent_uid]
                geo_pivot = [
                    round(abs_pivot[0] - parent_abs[0], 4),
                    round(abs_pivot[1] - parent_abs[1], 4),
                    round(abs_pivot[2] - parent_abs[2], 4),
                ]
            else:
                # Root bone or top-level bone — pivot is absolute
                geo_pivot = [
                    round(abs_pivot[0], 4) if abs(abs_pivot[0]) > 1e-10 else 0.0,
                    round(abs_pivot[1], 4) if abs(abs_pivot[1]) > 1e-10 else 0.0,
                    round(abs_pivot[2], 4) if abs(abs_pivot[2]) > 1e-10 else 0.0,
                ]

            # Clean up -0.0 → 0.0
            geo_pivot = [v if abs(v) > 1e-10 else 0.0 for v in geo_pivot]

            bone_entry = {
                "name": bone_name,
                "pivot": geo_pivot
            }

            # Parent reference
            if parent_uid is not None and parent_uid in uid2name:
                bone_entry["parent"] = uid2name[parent_uid]

            # Rotation: pass through directly (same coordinate system)
            # EXCEPTION: remove root's 180° Y rotation (RH→LH hack)
            bb_rot = list(g.get('rotation', [0, 0, 0]))
            if bone_name == 'root':
                # Remove 180° Y rotation — it was a coordinate system hack
                # that doesn't belong in geo.json
                bb_rot[1] = 0.0
                # Also remove 180° X and Z if present (some models have [180, -180, 180])
                # These are also RH→LH artifacts
                if abs(bb_rot[0]) > 179 and abs(bb_rot[0]) < 181:
                    bb_rot[0] = 0.0
                if abs(bb_rot[2]) > 179 and abs(bb_rot[2]) < 181:
                    bb_rot[2] = 0.0

            # Clean up rotation
            bb_rot = [v if abs(v) > 1e-10 else 0.0 for v in bb_rot]
            if any(abs(v) > 1e-10 for v in bb_rot):
                bone_entry["rotation"] = [round(v, 5) for v in bb_rot]

            # Process cubes
            bone_elems = elems_by_bone.get(bone_uid, [])
            if bone_elems:
                cubes = []
                for elem in bone_elems:
                    cube = self._convert_element_to_cube(elem, abs_pivot)
                    if cube:
                        cubes.append(cube)
                if cubes:
                    bone_entry["cubes"] = cubes

            # Mirror flag
            if bone_elems and any(e.get('mirror_uv', False) for e in bone_elems):
                bone_entry["mirror"] = True

            geo_bones.append(bone_entry)

        return geo_bones

    def _convert_element_to_cube(self, element, bone_abs_pivot):
        """Convert a bbmodel element to a geo.json cube.

        Key transformations:
        - Cube origin is RELATIVE to bone's pivot: [from_x - pivot_x, from_y - pivot_y, from_z - pivot_z]
        - Size: [to_x - from_x, to_y - from_y, to_z - from_z] (unchanged)
        - No coordinate mirroring — both formats use Y-up LH system
        """
        from_pos = element.get('from', [0, 0, 0])
        to_pos = element.get('to', [0, 0, 0])
        inflate = element.get('inflate', 0.0)
        mirror = element.get('mirror_uv', False)

        # Cube origin relative to bone's pivot (both in Y-up LH absolute space)
        origin = [
            round(float(from_pos[0]) - bone_abs_pivot[0], 4),
            round(float(from_pos[1]) - bone_abs_pivot[1], 4),
            round(float(from_pos[2]) - bone_abs_pivot[2], 4),
        ]
        # Size is unchanged
        size = [
            round(float(to_pos[0]) - float(from_pos[0]), 4),
            round(float(to_pos[1]) - float(from_pos[1]), 4),
            round(float(to_pos[2]) - float(from_pos[2]), 4),
        ]

        cube = {"origin": origin, "size": size}

        if inflate != 0.0:
            cube["inflate"] = round(float(inflate), 4)

        if mirror:
            cube["mirror"] = True

        # Convert UV faces
        faces = element.get('faces', {})
        uv_data = self._convert_faces_to_geo(faces)
        if uv_data:
            cube["uv"] = uv_data

        return cube

    def _convert_faces_to_geo(self, faces):
        """Convert bbmodel face UV to geo.json format.

        Side faces (N/E/S/W): uv=[u1,v1], uv_size=[u2-u1, v2-v1]
        Up/Down faces: uv=[u2,v2], uv_size=[-(u2-u1), -(v2-v1)]

        The up/down convention with negative uv_size is the standard
        Bedrock/GeckoLib format for horizontal faces.

        No face name swapping is needed — both .bbmodel and geo.json use
        the same Y-up LH coordinate system.
        """
        geo_faces = {}
        for face_name in ["north", "east", "south", "west", "up", "down"]:
            face = faces.get(face_name)
            if face is not None and face.get('texture', -1) >= 0:
                uv = face.get('uv', [0, 0, 0, 0])
                u1, v1, u2, v2 = uv[0], uv[1], uv[2], uv[3]

                if face_name in ("up", "down"):
                    # Up/down faces: use [u2, v2] as origin with negative sizes
                    geo_faces[face_name] = {
                        "uv": [round(u2, 4), round(v2, 4)],
                        "uv_size": [round(-(u2 - u1), 4), round(-(v2 - v1), 4)]
                    }
                else:
                    # Side faces: use [u1, v1] as origin with positive sizes
                    geo_faces[face_name] = {
                        "uv": [round(u1, 4), round(v1, 4)],
                        "uv_size": [round(u2 - u1, 4), round(v2 - v1, 4)]
                    }
        return geo_faces


def batch_convert(input_dir: str, output_dir: str) -> bool:
    """Batch convert all .bbmodel files in input_dir to geo.json + PNG."""
    print("=" * 70)
    print("  BBModel -> Geo.json + Texture Converter")
    print("  GeckoLib Format for MC 1.20.1 Forge Mod Development")
    print("=" * 70)
    print()

    # Find all .bbmodel files
    bbmodel_files = []
    for root, dirs, files in os.walk(input_dir):
        for fname in sorted(files):
            if fname.endswith('.bbmodel'):
                rel_path = os.path.relpath(
                    os.path.join(root, fname), input_dir
                )
                bbmodel_files.append(rel_path)

    print(f"Found {len(bbmodel_files)} .bbmodel files")
    print()

    converter = BBModelToGeo()
    ok_results = []
    fail_results = []

    for i, rel_path in enumerate(bbmodel_files, 1):
        bbmodel_path = os.path.join(input_dir, rel_path)
        category = os.path.dirname(rel_path)
        out_dir = os.path.join(output_dir, category) if category else output_dir
        name = os.path.basename(rel_path).replace('.bbmodel', '')

        print(f"  [{i:3d}/{len(bbmodel_files)}] {category}/{name}...",
              end=" ", flush=True)

        result = converter.convert_bbmodel(bbmodel_path, out_dir)

        if result['success']:
            s = result['stats']
            tex_mark = "tex=YES" if s['has_texture'] else "tex=NO"
            print(f"OK ({s['bones']}b, {s['cubes']}c, {s['texture_size']}, {tex_mark})")
            ok_results.append((category, name, s))
        else:
            print(f"FAILED: {result['error']}")
            fail_results.append((category, name, result.get('error', '?')))

    # Summary
    print()
    print("=" * 70)
    print("  CONVERSION SUMMARY")
    print("=" * 70)
    print(f"  Total:       {len(bbmodel_files)}")
    print(f"  Successful:  {len(ok_results)}")
    print(f"  Failed:      {len(fail_results)}")

    with_tex = sum(1 for _, _, s in ok_results if s.get('has_texture'))
    print(f"  With textures: {with_tex}")

    if fail_results:
        print("\n  Failed models:")
        for cat, name, err in fail_results:
            print(f"    - {cat}/{name}: {err}")

    total_bones = sum(s['bones'] for _, _, s in ok_results)
    total_cubes = sum(s['cubes'] for _, _, s in ok_results)
    print(f"\n  Total bones: {total_bones}")
    print(f"  Total cubes: {total_cubes}")
    print(f"  Output: {output_dir}")

    return len(fail_results) == 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert .bbmodel files to geo.json + PNG for GeckoLib mod development"
    )
    parser.add_argument("--input", required=True, help="Input directory with .bbmodel files")
    parser.add_argument("--output", required=True, help="Output directory for geo.json + PNG")
    args = parser.parse_args()

    success = batch_convert(args.input, args.output)
    sys.exit(0 if success else 1)
