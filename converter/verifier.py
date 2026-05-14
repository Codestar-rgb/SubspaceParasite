#!/usr/bin/env python3
"""
ModelVerifier - Offline Rendering Verification System
======================================================
Mathematically verifies model conversion accuracy by computing world-space
vertex positions for both the original 1.12.2 model and the converted
1.20.1 model, then comparing them.

No actual OpenGL rendering required - works in headless environments.
Uses numpy for efficient matrix operations.
"""

import math
import numpy as np
from typing import Dict, List, Tuple, Optional


class ModelVerifier:
    """
    Verifies model conversion accuracy by comparing world-space vertex positions
    between the original 1.12.2 model and the converted 1.20.1 model.
    """

    def __init__(self, tolerance: float = 0.01):
        """
        Args:
            tolerance: Maximum allowed vertex position difference (in pixels/units)
        """
        self.tolerance = tolerance

    def verify(self, bone_data_1122: dict, geo_json_1201: dict) -> dict:
        """
        Main verification method. Compares the original and converted models.

        Args:
            bone_data_1122: Original bone data dict with 'bones' key (var_name -> BoneData-like dict)
            geo_json_1201: Converted .geo.json structure

        Returns:
            Verification report dict
        """
        # Compute world vertices for both models
        verts_1122 = self.compute_world_vertices_1122(bone_data_1122)
        verts_1201 = self.compute_world_vertices_1201(geo_json_1201)

        # Compare
        comparison = self.compare_vertices(verts_1122, verts_1201, self.tolerance)

        return comparison

    def compute_world_vertices_1122(self, bone_data: dict) -> Dict[str, np.ndarray]:
        """
        Compute world-space vertex positions for all cubes in the 1.12.2 model.

        In MC 1.12.2 (Y-down, RH):
          - Bone hierarchy: parent transform * child transform
          - Pivot at setRotationPoint position
          - Rotation applied at pivot
          - Cube at addBox offset from pivot

        Returns:
            Dict mapping bone_name -> Nx3 array of world-space vertices (8 per cube)
        """
        bones = bone_data.get('bones', {})
        result = {}

        # Build world transforms for each bone
        world_transforms = {}
        self._compute_world_transforms_1122(bones, world_transforms, None, np.eye(4))

        # Compute cube vertices
        for var_name, bone in bones.items():
            if not bone.get('boxes'):
                continue

            transform = world_transforms.get(var_name)
            if transform is None:
                continue

            all_verts = []
            for box in bone['boxes']:
                # 8 corner vertices of the cube in local space
                ox, oy, oz = box['offset_x'], box['offset_y'], box['offset_z']
                w, h, d = box['width'], box['height'], box['depth']

                corners = [
                    [ox, oy, oz, 1],
                    [ox + w, oy, oz, 1],
                    [ox, oy + h, oz, 1],
                    [ox + w, oy + h, oz, 1],
                    [ox, oy, oz + d, 1],
                    [ox + w, oy, oz + d, 1],
                    [ox, oy + h, oz + d, 1],
                    [ox + w, oy + h, oz + d, 1],
                ]

                for corner in corners:
                    world_vert = transform @ np.array(corner)
                    all_verts.append(world_vert[:3])

            if all_verts:
                result[var_name] = np.array(all_verts)

        return result

    def _compute_world_transforms_1122(self, bones: dict, transforms: dict,
                                        parent_var: Optional[str], parent_transform: np.ndarray) -> None:
        """Recursively compute world transforms for the 1.12.2 bone hierarchy."""
        for var_name, bone in bones.items():
            if bone.get('parent') != parent_var:
                continue

            # Build local transform: translate to pivot, rotate, translate back
            px, py, pz = bone['pivot_x'], bone['pivot_y'], bone['pivot_z']
            rx, ry, rz = bone['rotate_x'], bone['rotate_y'], bone['rotate_z']

            # Local transform = T(pivot) * R * T(-pivot) ... but in MC, the pivot
            # is the rotation point, and cubes are offset from it.
            # So the transform is: T(pivot) * R
            local = self._make_transform_1122(px, py, pz, rx, ry, rz)
            world = parent_transform @ local
            transforms[var_name] = world

            # Recurse into children
            self._compute_world_transforms_1122(bones, transforms, var_name, world)

    @staticmethod
    def _make_transform_1122(px: float, py: float, pz: float,
                              rx: float, ry: float, rz: float) -> np.ndarray:
        """Create a 4x4 transform matrix for MC 1.12.2 (Y-down, RH)."""
        # Translation to pivot
        T = np.eye(4)
        T[0, 3] = px
        T[1, 3] = py
        T[2, 3] = pz

        # Rotation: R = Rz(rz) * Ry(ry) * Rx(rx)
        cx, sx = math.cos(rx), math.sin(rx)
        cy, sy = math.cos(ry), math.sin(ry)
        cz, sz = math.cos(rz), math.sin(rz)

        Rx = np.eye(4)
        Rx[1, 1] = cx; Rx[1, 2] = -sx
        Rx[2, 1] = sx; Rx[2, 2] = cx

        Ry = np.eye(4)
        Ry[0, 0] = cy; Ry[0, 2] = sy
        Ry[2, 0] = -sy; Ry[2, 2] = cy

        Rz = np.eye(4)
        Rz[0, 0] = cz; Rz[0, 1] = -sz
        Rz[1, 0] = sz; Rz[1, 1] = cz

        R = Rz @ Ry @ Rx

        return T @ R

    def compute_world_vertices_1201(self, geo_json: dict) -> Dict[str, np.ndarray]:
        """
        Compute world-space vertex positions for all cubes in the converted 1.20.1 model.

        In GeckoLib 1.20.1 (Y-up, LH):
          - Root bone at (0, 24, 0)
          - Bone hierarchy: parent transform * child transform
          - Pivot in converted coordinates
          - Rotation in converted coordinates (degrees)

        Returns:
            Dict mapping bone_name -> Nx3 array of world-space vertices (8 per cube)
        """
        model = geo_json.get('model', geo_json.get('minecraft:geometry', [{}])[0])
        bones_list = model.get('bones', [])

        # Build bone lookup
        bone_lookup = {b['name']: b for b in bones_list}

        # Compute world transforms
        world_transforms = {}
        self._compute_world_transforms_1201(bone_lookup, world_transforms, 'root', np.eye(4))

        # Compute cube vertices
        result = {}
        for bone in bones_list:
            name = bone['name']
            cubes = bone.get('cubes', [])
            if not cubes:
                continue

            transform = world_transforms.get(name)
            if transform is None:
                continue

            all_verts = []
            for cube in cubes:
                origin = cube['origin']
                size = cube['size']

                ox, oy, oz = origin[0], origin[1], origin[2]
                w, h, d = size[0], size[1], size[2]

                corners = [
                    [ox, oy, oz, 1],
                    [ox + w, oy, oz, 1],
                    [ox, oy + h, oz, 1],
                    [ox + w, oy + h, oz, 1],
                    [ox, oy, oz + d, 1],
                    [ox + w, oy, oz + d, 1],
                    [ox, oy + h, oz + d, 1],
                    [ox + w, oy + h, oz + d, 1],
                ]

                for corner in corners:
                    world_vert = transform @ np.array(corner)
                    all_verts.append(world_vert[:3])

            if all_verts:
                result[name] = np.array(all_verts)

        return result

    def _compute_world_transforms_1201(self, bone_lookup: dict, transforms: dict,
                                        parent_name: str, parent_transform: np.ndarray) -> None:
        """Recursively compute world transforms for the 1.20.1 bone hierarchy."""
        for name, bone in bone_lookup.items():
            if bone.get('parent') != parent_name:
                continue

            pivot = bone.get('pivot', [0, 0, 0])
            rotation = bone.get('rotation', [0, 0, 0])

            # Convert degrees to radians
            rx = math.radians(rotation[0])
            ry = math.radians(rotation[1])
            rz = math.radians(rotation[2])

            local = self._make_transform_1201(pivot[0], pivot[1], pivot[2], rx, ry, rz)
            world = parent_transform @ local
            transforms[name] = world

            self._compute_world_transforms_1201(bone_lookup, transforms, name, world)

    @staticmethod
    def _make_transform_1201(px: float, py: float, pz: float,
                              rx: float, ry: float, rz: float) -> np.ndarray:
        """Create a 4x4 transform matrix for GeckoLib 1.20.1 (Y-up, LH)."""
        T = np.eye(4)
        T[0, 3] = px
        T[1, 3] = py
        T[2, 3] = pz

        # Rotation: R = Rx(rx) * Ry(ry) * Rz(rz) (GeckoLib ZYX order)
        cx, sx = math.cos(rx), math.sin(rx)
        cy, sy = math.cos(ry), math.sin(ry)
        cz, sz = math.cos(rz), math.sin(rz)

        Rx = np.eye(4)
        Rx[1, 1] = cx; Rx[1, 2] = -sx
        Rx[2, 1] = sx; Rx[2, 2] = cx

        Ry = np.eye(4)
        Ry[0, 0] = cy; Ry[0, 2] = sy
        Ry[2, 0] = -sy; Ry[2, 2] = cy

        Rz = np.eye(4)
        Rz[0, 0] = cz; Rz[0, 1] = -sz
        Rz[1, 0] = sz; Rz[1, 1] = cz

        R = Rx @ Ry @ Rz

        return T @ R

    def compare_vertices(self, verts_1122: Dict[str, np.ndarray],
                          verts_1201: Dict[str, np.ndarray],
                          tolerance: float) -> dict:
        """
        Compare world-space vertex sets from both models.

        The 1.12.2 model uses Y-down RH coordinates.
        The 1.20.1 model uses Y-up LH coordinates.
        We convert both to a common coordinate system for comparison.

        Args:
            verts_1122: Dict of bone_name -> vertices in 1.12.2 Y-down RH space
            verts_1201: Dict of bone_name -> vertices in 1.20.1 Y-up LH space
            tolerance: Maximum allowed distance between matching vertices

        Returns:
            Verification report dict
        """
        # M_model = diag(1, -1, -1) converts 1.12.2 -> 1.20.1
        M = np.diag([1.0, -1.0, -1.0])

        total_verts = 0
        matching_verts = 0
        total_error = 0.0
        max_error = 0.0
        details = []

        # Match bones by name
        bone_mapping_1122_to_1201 = {}
        for name_1122 in verts_1122:
            # Try direct match or clean name match
            if name_1122 in verts_1201:
                bone_mapping_1122_to_1201[name_1122] = name_1122

        for name_1122, name_1201 in bone_mapping_1122_to_1201.items():
            v1122 = verts_1122[name_1122]
            v1201 = verts_1201[name_1201]

            # Convert 1.12.2 vertices to 1.20.1 space
            v1122_converted = (M @ v1122.T).T

            if len(v1122_converted) != len(v1201):
                # Different number of cubes - try per-vertex matching
                pass

            n_verts = min(len(v1122_converted), len(v1201))
            bone_total_error = 0.0
            bone_max_error = 0.0
            bone_matching = 0

            for i in range(n_verts):
                diff = np.linalg.norm(v1122_converted[i] - v1201[i])
                total_verts += 1
                bone_total_error += diff
                total_error += diff

                if diff > max_error:
                    max_error = diff
                if diff > bone_max_error:
                    bone_max_error = diff

                if diff <= tolerance:
                    matching_verts += 1
                    bone_matching += 1

            avg_error = bone_total_error / max(n_verts, 1)
            details.append({
                'bone_1122': name_1122,
                'bone_1201': name_1201,
                'vertex_count': n_verts,
                'matching_vertices': bone_matching,
                'max_error': round(bone_max_error, 6),
                'avg_error': round(avg_error, 6)
            })

        similarity_score = matching_verts / max(total_verts, 1)

        return {
            'verified': similarity_score >= 0.99,
            'similarity_score': round(similarity_score, 6),
            'total_vertices': total_verts,
            'matching_vertices': matching_verts,
            'avg_error': round(total_error / max(total_verts, 1), 6),
            'max_error': round(max_error, 6),
            'tolerance': tolerance,
            'bones_compared': len(details),
            'details': details
        }


if __name__ == "__main__":
    print("ModelVerifier module loaded successfully.")
    print("Usage: Instantiate ModelVerifier and call verify() with bone data and geo.json")
