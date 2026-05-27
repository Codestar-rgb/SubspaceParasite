#!/usr/bin/env python3
"""
BBModel to Geo.json Converter
==============================
Converts Blockbench .bbmodel files back to Bedrock geo.json format
and extracts embedded texture PNGs, producing files ready for
GeckoLib mod development.

Output per model:
  <category>/<modelName>.geo.json   - Bedrock geometry definition
  <category>/<modelName>.png        - Texture file

Coordinate System Conversion (bbmodel -> geo.json):
  - bbmodel: ABSOLUTE world-space pivots and element positions
  - geo.json: RELATIVE (parent-local) pivots, bone-local cube origins
  - Root pivot: [0, 24, 0]
  - Direct children of root: relative = abs - parent_abs - [0, 24, 0]
  - Deeper descendants: relative = abs - parent_abs
  - Cube origin = from_pos - bone_abs_pivot

Rotation: intrinsic xyz -> extrinsic XYZ via scipy
Root 180Y: subtracted before rotation conversion
UV: [u1,v1,u2,v2] -> {uv:[u,v], uv_size:[w,h]}
N/S and W/E swaps preserved (already correct for LH/Bedrock)
"""

import base64
import json
import os
import sys
import traceback
from typing import Dict, List, Optional

from scipy.spatial.transform import Rotation

Y_OFFSET = 24.0


class BBModelToGeo:
    """Converts .bbmodel files back to Bedrock geo.json format with texture extraction."""

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

            # Build bone info from groups
            bone_map = {g['uuid']: g for g in groups}

            # Parse outliner for parent-child relationships
            parent_map = {}
            self._parse_outliner(outliner, None, bone_map, parent_map)

            # Map element uuids to bones
            elem_to_bone = {}
            self._map_elems_recursive(outliner, None, elem_to_bone)

            # Build geo.json bones
            geo_bones = self._build_geo_bones(
                groups, elements, bone_map, parent_map, elem_to_bone
            )

            # Assemble geo.json
            geo_json = {
                "format_version": "1.12.0",
                "minecraft:geometry": [{
                    "description": {
                        "identifier": f"geometry.{short_name}",
                        "texture_width": tw,
                        "texture_height": th,
                        "visible_bounds_width": 2,
                        "visible_bounds_height": 3,
                        "visible_bounds_offset": [0, 1.5, 0]
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

    def _parse_outliner(self, outliner, parent_uuid, bone_map, parent_map):
        """Recursively parse outliner tree to build parent-child relationships."""
        for entry in outliner:
            if isinstance(entry, dict):
                uid = entry.get('uuid')
                if uid and uid in bone_map and parent_uuid is not None:
                    parent_map[uid] = parent_uuid
                self._parse_outliner(
                    entry.get('children', []), uid, bone_map, parent_map
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

    def _build_geo_bones(self, groups, elements, bone_map, parent_map, elem_to_bone):
        """Build geo.json bones array from bbmodel data."""
        # Absolute pivot lookup
        abs_piv = {g['uuid']: g.get('origin', [0, 24, 0]) for g in groups}
        # UUID to name lookup
        uid2name = {g['uuid']: g['name'] for g in groups}

        # Elements by bone
        elems_by_bone: Dict[str, list] = {}
        for elem in elements:
            bu = elem_to_bone.get(elem.get('uuid'))
            if bu:
                elems_by_bone.setdefault(bu, []).append(elem)

        # Identify root bone and its direct children
        root_uid = next((g['uuid'] for g in groups if g['name'] == 'root'), None)
        root_children = {
            g['uuid'] for g in groups if parent_map.get(g['uuid']) == root_uid
        }

        geo_bones = []
        for g in groups:
            bone_name = g['name']
            bone_uid = g['uuid']
            abs_pivot = abs_piv.get(bone_uid, [0, 24, 0])

            # Compute relative pivot
            parent_uid = parent_map.get(bone_uid)
            if parent_uid is None:
                # Top-level bone (root or orphan)
                relative_pivot = list(abs_pivot)
            else:
                parent_abs = abs_piv.get(parent_uid, [0, 24, 0])
                relative_pivot = [abs_pivot[i] - parent_abs[i] for i in range(3)]
                # Direct children of root need Y_OFFSET subtraction
                if bone_uid in root_children:
                    relative_pivot[1] -= Y_OFFSET

            bone_entry = {
                "name": bone_name,
                "pivot": [round(relative_pivot[0], 4),
                          round(relative_pivot[1], 4),
                          round(relative_pivot[2], 4)]
            }

            # Parent reference
            if parent_uid is not None and parent_uid in uid2name:
                bone_entry["parent"] = uid2name[parent_uid]

            # Rotation conversion
            bb_rot = list(g.get('rotation', [0, 0, 0]))
            if any(abs(v) > 1e-10 for v in bb_rot):
                # Remove the 180° Y rotation that was added to root
                if bone_name == 'root':
                    bb_rot[1] -= 180.0
                geo_rot = self._convert_rotation_to_geo(bb_rot)
                if any(abs(v) > 1e-10 for v in geo_rot):
                    bone_entry["rotation"] = [round(v, 4) for v in geo_rot]

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

    def _convert_rotation_to_geo(self, bbmodel_rotation):
        """Convert rotation from bbmodel intrinsic xyz to geo.json extrinsic XYZ."""
        if not bbmodel_rotation or all(abs(v) < 1e-10 for v in bbmodel_rotation):
            return [0.0, 0.0, 0.0]
        r = Rotation.from_euler("xyz", bbmodel_rotation, degrees=True)
        result = r.as_euler("XYZ", degrees=True)
        return [round(float(v), 6) for v in result]

    def _convert_element_to_cube(self, element, bone_abs_pivot):
        """Convert a bbmodel element to a geo.json cube."""
        from_pos = element.get('from', [0, 0, 0])
        to_pos = element.get('to', [0, 0, 0])
        inflate = element.get('inflate', 0.0)
        mirror = element.get('mirror_uv', False)

        # Bone-local origin
        origin = [round(from_pos[i] - bone_abs_pivot[i], 4) for i in range(3)]
        # Size
        size = [round(to_pos[i] - from_pos[i], 4) for i in range(3)]

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
        """Convert bbmodel face UV to geo.json format: [u1,v1,u2,v2] -> {uv, uv_size}."""
        geo_faces = {}
        for face_name in ["north", "east", "south", "west", "up", "down"]:
            face = faces.get(face_name)
            if face is not None and face.get('texture', -1) >= 0:
                uv = face.get('uv', [0, 0, 0, 0])
                u1, v1, u2, v2 = uv[0], uv[1], uv[2], uv[3]
                geo_faces[face_name] = {
                    "uv": [round(u1, 4), round(v1, 4)],
                    "uv_size": [round(u2 - u1, 4), round(v2 - v1, 4)]
                }
        return geo_faces


def batch_convert(input_dir: str, output_dir: str) -> bool:
    """Batch convert all .bbmodel files in input_dir to geo.json + PNG."""
    print("=" * 70)
    print("  BBModel -> Geo.json + Texture Converter")
    print("  For GeckoLib Mod Development")
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
        description="Convert .bbmodel files to geo.json + PNG for mod development"
    )
    parser.add_argument("--input", required=True, help="Input directory with .bbmodel files")
    parser.add_argument("--output", required=True, help="Output directory for geo.json + PNG")
    args = parser.parse_args()

    success = batch_convert(args.input, args.output)
    sys.exit(0 if success else 1)
