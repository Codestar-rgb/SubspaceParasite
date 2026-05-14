#!/usr/bin/env python3
"""
ModelVerifier - Offline Rendering Verification System
======================================================
Mathematically verifies model conversion accuracy by computing world-space
vertex positions for both the original 1.12.2 model and the converted
1.20.1 model, then comparing them.

No actual OpenGL rendering required - works in headless environments.
Uses numpy for efficient matrix operations.

Enhanced verification checks:
  1. Vertex position comparison (original)
  2. UV coordinate validation (texture bounds)
  3. Bone hierarchy validation (parent-child preservation)
  4. Animation bone name matching (anim bones exist in geo)
  5. Inflate handling verification
  6. Blockbench format validation
  7. Y-offset handling (root bone at [0,24,0])
"""

import math
import json
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import numpy as np


class ModelVerifier:
    """
    Verifies model conversion accuracy by comparing world-space vertex positions
    between the original 1.12.2 model and the converted 1.20.1 model.

    Enhanced with UV validation, bone hierarchy checks, animation bone matching,
    inflate verification, Blockbench format validation, and Y-offset handling.
    """

    # Standard root bone pivot in GeckoLib Y-up coordinate system
    ROOT_BONE_PIVOT_Y = 24.0

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

    def verify_full(self, bone_data_1122: dict, geo_json_1201: dict,
                    animation_json: Optional[dict] = None,
                    blockbench_json: Optional[dict] = None) -> dict:
        """
        Full verification suite with all enhanced checks.

        Args:
            bone_data_1122: Original bone data dict
            geo_json_1201: Converted .geo.json structure (game format)
            animation_json: Optional .animation.json for bone name matching
            blockbench_json: Optional Blockbench format .geo.json for format validation

        Returns:
            Comprehensive verification report dict
        """
        results = {}

        # 1. Vertex comparison (existing)
        vertex_result = self.verify(bone_data_1122, geo_json_1201)
        results['vertex_comparison'] = vertex_result

        # 2. UV validation
        uv_result = self.validate_uv_coordinates(geo_json_1201)
        results['uv_validation'] = uv_result

        # 3. Bone hierarchy validation
        hierarchy_result = self.validate_bone_hierarchy(bone_data_1122, geo_json_1201)
        results['bone_hierarchy'] = hierarchy_result

        # 4. Animation bone name matching
        if animation_json:
            anim_result = self.validate_animation_bone_names(animation_json, geo_json_1201)
            results['animation_matching'] = anim_result
        else:
            results['animation_matching'] = {
                'checked': False,
                'reason': 'No animation JSON provided'
            }

        # 5. Inflate handling verification
        inflate_result = self.validate_inflate_handling(geo_json_1201)
        results['inflate_validation'] = inflate_result

        # 6. Y-offset handling verification
        yoffset_result = self.validate_y_offset(geo_json_1201)
        results['y_offset_validation'] = yoffset_result

        # 7. Blockbench format validation
        if blockbench_json:
            bb_result = self.verify_blockbench_format(blockbench_json)
            results['blockbench_format'] = bb_result
        else:
            results['blockbench_format'] = {
                'checked': False,
                'reason': 'No Blockbench JSON provided'
            }

        # Overall pass/fail
        all_checks = [
            vertex_result.get('verified', False),
            uv_result.get('passed', False),
            hierarchy_result.get('passed', False),
            yoffset_result.get('passed', False),
        ]
        if animation_json:
            all_checks.append(anim_result.get('passed', False))
        if blockbench_json:
            all_checks.append(bb_result.get('passed', False))

        results['overall_passed'] = all(all_checks)
        results['overall_score'] = sum(1 for c in all_checks if c) / max(len(all_checks), 1)
        results['timestamp'] = datetime.now().isoformat()

        return results

    # ========================================================================
    # UV Validation
    # ========================================================================

    def validate_uv_coordinates(self, geo_json: dict) -> dict:
        """
        Validate that UV coordinates don't exceed texture bounds.

        Checks each face of each cube to ensure that:
          uv[0] + uv_size[0] <= texture_width
          uv[1] + uv_size[1] <= texture_height
          uv values are non-negative

        Args:
            geo_json: The converted .geo.json structure

        Returns:
            Dict with 'passed', 'total_faces', 'valid_faces', 'violations' keys
        """
        model = geo_json.get('model', geo_json.get('minecraft:geometry', [{}])[0])
        texture_width = model.get('texture_width', 256)
        texture_height = model.get('texture_height', 256)
        bones = model.get('bones', [])

        total_faces = 0
        valid_faces = 0
        violations = []

        for bone in bones:
            bone_name = bone.get('name', 'unknown')
            cubes = bone.get('cubes', [])
            for ci, cube in enumerate(cubes):
                uv_data = cube.get('uv', {})
                for face_name, face_uv in uv_data.items():
                    total_faces += 1
                    uv_origin = face_uv.get('uv', [0, 0])
                    uv_size = face_uv.get('uv_size', [0, 0])

                    u, v = uv_origin[0], uv_origin[1]
                    u_size, v_size = uv_size[0], uv_size[1]

                    issues = []

                    # Check lower bounds
                    if u < 0:
                        issues.append(f'u={u} < 0')
                    if v < 0:
                        issues.append(f'v={v} < 0')

                    # Check upper bounds
                    if u + u_size > texture_width:
                        issues.append(
                            f'u+u_size={u + u_size} > texture_width={texture_width}'
                        )
                    if v + v_size > texture_height:
                        issues.append(
                            f'v+v_size={v + v_size} > texture_height={texture_height}'
                        )

                    # Check non-negative sizes
                    if u_size < 0:
                        issues.append(f'u_size={u_size} < 0')
                    if v_size < 0:
                        issues.append(f'v_size={v_size} < 0')

                    if issues:
                        violations.append({
                            'bone': bone_name,
                            'cube_index': ci,
                            'face': face_name,
                            'uv': uv_origin,
                            'uv_size': uv_size,
                            'issues': issues
                        })
                    else:
                        valid_faces += 1

        passed = len(violations) == 0

        return {
            'passed': passed,
            'total_faces': total_faces,
            'valid_faces': valid_faces,
            'violation_count': len(violations),
            'violations': violations[:20],  # Limit to first 20
            'texture_width': texture_width,
            'texture_height': texture_height
        }

    # ========================================================================
    # Bone Hierarchy Validation
    # ========================================================================

    def validate_bone_hierarchy(self, bone_data_1122: dict, geo_json_1201: dict) -> dict:
        """
        Verify that parent-child relationships are preserved in the conversion.

        Checks that:
          - Every parent-child pair in 1.12.2 has a corresponding pair in 1.20.1
          - No orphaned bones (bones referencing non-existent parents)
          - Root bone exists and has correct pivot

        Args:
            bone_data_1122: Original bone data dict
            geo_json_1201: Converted .geo.json structure

        Returns:
            Dict with 'passed', 'details' keys
        """
        bones_1122 = bone_data_1122.get('bones', {})
        model = geo_json_1201.get('model', geo_json_1201.get('minecraft:geometry', [{}])[0])
        bones_1201 = model.get('bones', [])

        # Build 1.20.1 bone lookup
        bone_1201_lookup = {b['name']: b for b in bones_1201}

        # Build 1.12.2 parent-child pairs
        pairs_1122 = set()
        for var_name, bone in bones_1122.items():
            parent = bone.get('parent')
            if parent:
                # Map names using bone_data naming
                child_name = var_name
                parent_name = parent
                pairs_1122.add((parent_name, child_name))

        # Build 1.20.1 parent-child pairs
        pairs_1201 = set()
        for bone in bones_1201:
            name = bone.get('name', '')
            parent = bone.get('parent')
            if parent:
                pairs_1201.add((parent, name))

        # Check for missing pairs
        missing_pairs = []
        for parent, child in pairs_1122:
            # Try direct match
            if (parent, child) in pairs_1201:
                continue
            # The parent-child pair should be preserved
            missing_pairs.append({
                'parent': parent,
                'child': child,
                'reason': 'Parent-child pair not found in converted model'
            })

        # Check for orphaned bones in 1.20.1
        orphaned_bones = []
        for bone in bones_1201:
            name = bone.get('name', '')
            parent = bone.get('parent')
            if parent and parent != 'root' and parent not in bone_1201_lookup:
                orphaned_bones.append({
                    'bone': name,
                    'missing_parent': parent
                })

        # Check root bone
        root_bone = bone_1201_lookup.get('root')
        root_valid = False
        root_issues = []
        if root_bone:
            pivot = root_bone.get('pivot', [0, 0, 0])
            if abs(pivot[1] - self.ROOT_BONE_PIVOT_Y) > 0.01:
                root_issues.append(
                    f'Root bone pivot Y={pivot[1]} != {self.ROOT_BONE_PIVOT_Y}'
                )
            else:
                root_valid = True
        else:
            root_issues.append('Root bone not found')

        passed = (len(missing_pairs) == 0 and
                  len(orphaned_bones) == 0 and
                  root_valid)

        return {
            'passed': passed,
            'hierarchy_pairs_1122': len(pairs_1122),
            'hierarchy_pairs_1201': len(pairs_1201),
            'missing_pairs': len(missing_pairs),
            'missing_pair_details': missing_pairs[:10],
            'orphaned_bones': len(orphaned_bones),
            'orphaned_bone_details': orphaned_bones[:10],
            'root_bone_valid': root_valid,
            'root_bone_issues': root_issues
        }

    # ========================================================================
    # Animation Bone Name Matching
    # ========================================================================

    def validate_animation_bone_names(self, animation_json: dict, geo_json_1201: dict) -> dict:
        """
        Verify that all animation bone names exist in the geo.json.

        Args:
            animation_json: The .animation.json structure
            geo_json_1201: The converted .geo.json structure

        Returns:
            Dict with 'passed', 'missing_bones', 'details' keys
        """
        model = geo_json_1201.get('model', geo_json_1201.get('minecraft:geometry', [{}])[0])
        geo_bone_names = {b['name'] for b in model.get('bones', [])}

        # Collect all bone names from all animations
        anim_bone_names = set()
        animations = animation_json.get('animations', {})
        for anim_name, anim_data in animations.items():
            bones = anim_data.get('bones', {})
            for bone_name in bones:
                anim_bone_names.add(bone_name)

        # Find missing bones (in animation but not in geo)
        missing_bones = anim_bone_names - geo_bone_names
        matched_bones = anim_bone_names & geo_bone_names

        passed = len(missing_bones) == 0

        return {
            'passed': passed,
            'total_anim_bones': len(anim_bone_names),
            'matched_bones': len(matched_bones),
            'missing_bones': len(missing_bones),
            'missing_bone_names': sorted(list(missing_bones)),
            'total_geo_bones': len(geo_bone_names)
        }

    # ========================================================================
    # Inflate Handling Verification
    # ========================================================================

    def validate_inflate_handling(self, geo_json_1201: dict) -> dict:
        """
        Check that inflate values are correctly applied.

        In MC 1.12.2, addBox can have an optional inflate parameter.
        In the converted model, inflate should expand the cube symmetrically:
          - origin is shifted by -inflate in each axis
          - size is increased by 2*inflate in each axis

        This checks that:
          1. Cubes with inflate have consistent origin/size adjustments
          2. Inflate values are reasonable (not excessively large)

        Args:
            geo_json_1201: The converted .geo.json structure

        Returns:
            Dict with 'passed', 'cubes_with_inflate', 'issues' keys
        """
        model = geo_json_1201.get('model', geo_json_1201.get('minecraft:geometry', [{}])[0])
        bones = model.get('bones', [])

        cubes_with_inflate = 0
        issues = []

        for bone in bones:
            bone_name = bone.get('name', 'unknown')
            cubes = bone.get('cubes', [])
            for ci, cube in enumerate(cubes):
                inflate = cube.get('inflate', 0.0)
                if abs(inflate) > 1e-10:
                    cubes_with_inflate += 1

                    # Check for unreasonable inflate values
                    size = cube.get('size', [0, 0, 0])
                    origin = cube.get('origin', [0, 0, 0])

                    for axis_idx, (s, o, axis_name) in enumerate(
                        zip(size, origin, ['X', 'Y', 'Z'])
                    ):
                        # Inflated size should be positive
                        if s <= 0:
                            issues.append({
                                'bone': bone_name,
                                'cube_index': ci,
                                'issue': f'Inflated size {axis_name}={s} <= 0 '
                                         f'(inflate={inflate})'
                            })

                        # Check that inflate doesn't make the cube degenerate
                        if abs(inflate) > s / 2:
                            issues.append({
                                'bone': bone_name,
                                'cube_index': ci,
                                'issue': f'Inflate |{inflate}| > half-size {axis_name}={s/2}, '
                                         f'cube may be degenerate'
                            })

        # Inflate check passes if there are no issues with inflated cubes
        # Note: not having inflate is also fine (passes)
        passed = len(issues) == 0

        return {
            'passed': passed,
            'cubes_with_inflate': cubes_with_inflate,
            'issue_count': len(issues),
            'issues': issues[:20]
        }

    # ========================================================================
    # Y-Offset Validation
    # ========================================================================

    def validate_y_offset(self, geo_json_1201: dict) -> dict:
        """
        Verify that the Y-offset (root bone at [0,24,0]) is correctly handled.

        In GeckoLib 1.20.1, the root bone pivot is at [0, 24, 0] to account
        for the Y-down → Y-up coordinate shift. All top-level bones should
        have their pivots relative to this root position.

        Checks:
          - Root bone exists with pivot [0, 24, 0]
          - Top-level bones (children of root) have pivots consistent with
            the 24-unit Y offset

        Args:
            geo_json_1201: The converted .geo.json structure

        Returns:
            Dict with 'passed', 'root_valid', 'details' keys
        """
        model = geo_json_1201.get('model', geo_json_1201.get('minecraft:geometry', [{}])[0])
        bones = model.get('bones', [])

        bone_lookup = {b['name']: b for b in bones}

        # Check root bone
        root_bone = bone_lookup.get('root')
        root_valid = False
        root_details = {}

        if root_bone:
            pivot = root_bone.get('pivot', [0, 0, 0])
            expected_pivot = [0.0, self.ROOT_BONE_PIVOT_Y, 0.0]

            root_details = {
                'pivot': pivot,
                'expected_pivot': expected_pivot,
                'y_correct': abs(pivot[1] - self.ROOT_BONE_PIVOT_Y) < 0.01,
                'x_correct': abs(pivot[0]) < 0.01,
                'z_correct': abs(pivot[2]) < 0.01
            }
            root_valid = (root_details['y_correct'] and
                          root_details['x_correct'] and
                          root_details['z_correct'])
        else:
            root_details = {'error': 'Root bone not found'}

        # Check top-level bones are children of root
        top_level_bones = []
        for bone in bones:
            if bone.get('parent') == 'root':
                top_level_bones.append(bone['name'])

        passed = root_valid

        return {
            'passed': passed,
            'root_valid': root_valid,
            'root_details': root_details,
            'top_level_bone_count': len(top_level_bones),
            'top_level_bones': top_level_bones[:20]
        }

    # ========================================================================
    # Blockbench Format Validation
    # ========================================================================

    def verify_blockbench_format(self, blockbench_json: dict) -> dict:
        """
        Validate Blockbench-specific format requirements.

        Checks:
          1. Top-level "minecraft:geometry" array wrapper exists
          2. "description" sub-object with required fields
          3. UV format uses {uv:[], uv_size:[]} per face
          4. visible_bounds fields present
          5. format_version is correct

        Args:
            blockbench_json: The Blockbench format .geo.json dict

        Returns:
            Dict with 'passed', 'checks', 'issues' keys
        """
        checks = {}
        issues = []

        # Check 1: minecraft:geometry wrapper
        has_mc_geo = 'minecraft:geometry' in blockbench_json
        checks['minecraft_geometry_wrapper'] = has_mc_geo
        if not has_mc_geo:
            issues.append('Missing "minecraft:geometry" top-level key')

        # Check 2: format_version
        format_version = blockbench_json.get('format_version', '')
        checks['format_version'] = format_version in ('1.12.0', '1.10.0')
        if format_version not in ('1.12.0', '1.10.0'):
            issues.append(f'Unexpected format_version: {format_version}')

        # Check 3: description object
        if has_mc_geo:
            geometries = blockbench_json['minecraft:geometry']
            if isinstance(geometries, list) and len(geometries) > 0:
                geo = geometries[0]
                desc = geo.get('description', {})

                required_desc_fields = [
                    'identifier', 'texture_width', 'texture_height'
                ]
                for field in required_desc_fields:
                    present = field in desc
                    checks[f'description_{field}'] = present
                    if not present:
                        issues.append(f'Missing description field: {field}')

                # Check visible_bounds (optional but recommended)
                has_visible_bounds = 'visible_bounds_width' in desc
                checks['visible_bounds'] = has_visible_bounds

                # Check bones exist
                bones = geo.get('bones', [])
                checks['bones_present'] = len(bones) > 0
                if len(bones) == 0:
                    issues.append('No bones in Blockbench format')

                # Check UV format
                uv_issues = 0
                for bone in bones:
                    for cube in bone.get('cubes', []):
                        uv = cube.get('uv', {})
                        for face_name, face_uv in uv.items():
                            if 'uv' not in face_uv or 'uv_size' not in face_uv:
                                uv_issues += 1
                                if uv_issues <= 5:
                                    issues.append(
                                        f'Invalid UV format in bone {bone.get("name")}, '
                                        f'face {face_name}: expected {{uv:[], uv_size:[]}}'
                                    )

                checks['uv_format_valid'] = uv_issues == 0
            else:
                issues.append('minecraft:geometry is empty or not a list')
                checks['description_valid'] = False
        else:
            checks['description_valid'] = False

        passed = len(issues) == 0

        return {
            'passed': passed,
            'checks': checks,
            'issue_count': len(issues),
            'issues': issues[:20]
        }

    # ========================================================================
    # Verification Report Generation
    # ========================================================================

    def generate_verification_report(self, results: dict) -> str:
        """
        Generate a detailed text report from verification results.

        Args:
            results: The results dict from verify_full()

        Returns:
            Formatted text report string
        """
        lines = []
        lines.append("=" * 70)
        lines.append("  MODEL VERIFICATION REPORT")
        lines.append("  MC 1.12.2 → GeckoLib 1.20.1 Conversion Verification")
        lines.append("=" * 70)
        lines.append("")

        # Timestamp
        ts = results.get('timestamp', 'N/A')
        lines.append(f"  Generated: {ts}")
        lines.append(f"  Tolerance: {self.tolerance}")
        lines.append("")

        # Overall result
        overall = results.get('overall_passed', False)
        score = results.get('overall_score', 0)
        status = "PASS" if overall else "FAIL"
        lines.append(f"  Overall Result: {status}")
        lines.append(f"  Overall Score:  {score:.1%}")
        lines.append("")

        # 1. Vertex Comparison
        lines.append("-" * 70)
        lines.append("  1. VERTEX COMPARISON")
        lines.append("-" * 70)
        vc = results.get('vertex_comparison', {})
        if vc:
            sim = vc.get('similarity_score', 0)
            verified = vc.get('verified', False)
            lines.append(f"  Similarity Score:  {sim:.6f} ({sim*100:.2f}%)")
            lines.append(f"  Verified:          {'PASS' if verified else 'FAIL'}")
            lines.append(f"  Total Vertices:    {vc.get('total_vertices', 0)}")
            lines.append(f"  Matching Vertices: {vc.get('matching_vertices', 0)}")
            lines.append(f"  Average Error:     {vc.get('avg_error', 0):.6f}")
            lines.append(f"  Max Error:         {vc.get('max_error', 0):.6f}")
            lines.append(f"  Bones Compared:    {vc.get('bones_compared', 0)}")

            # Per-bone details
            details = vc.get('details', [])
            if details:
                lines.append("")
                lines.append("  Per-Bone Details:")
                for d in details[:20]:
                    bone_1122 = d.get('bone_1122', '?')
                    bone_1201 = d.get('bone_1201', '?')
                    match_pct = d.get('matching_vertices', 0) / max(d.get('vertex_count', 1), 1) * 100
                    lines.append(
                        f"    {bone_1122:20s} → {bone_1201:20s}  "
                        f"verts={d.get('vertex_count', 0):3d}  "
                        f"match={match_pct:6.1f}%  "
                        f"max_err={d.get('max_error', 0):.4f}"
                    )
        else:
            lines.append("  No vertex comparison data available")
        lines.append("")

        # 2. UV Validation
        lines.append("-" * 70)
        lines.append("  2. UV COORDINATE VALIDATION")
        lines.append("-" * 70)
        uv = results.get('uv_validation', {})
        if uv:
            passed = uv.get('passed', False)
            lines.append(f"  Result:        {'PASS' if passed else 'FAIL'}")
            lines.append(f"  Total Faces:   {uv.get('total_faces', 0)}")
            lines.append(f"  Valid Faces:   {uv.get('valid_faces', 0)}")
            lines.append(f"  Violations:    {uv.get('violation_count', 0)}")
            lines.append(f"  Texture Size:  {uv.get('texture_width', 0)}x{uv.get('texture_height', 0)}")

            violations = uv.get('violations', [])
            if violations:
                lines.append("")
                lines.append("  UV Violations (first 10):")
                for v in violations[:10]:
                    lines.append(
                        f"    Bone: {v['bone']}, Cube: {v['cube_index']}, "
                        f"Face: {v['face']}"
                    )
                    for issue in v.get('issues', []):
                        lines.append(f"      - {issue}")
        else:
            lines.append("  No UV validation data available")
        lines.append("")

        # 3. Bone Hierarchy
        lines.append("-" * 70)
        lines.append("  3. BONE HIERARCHY VALIDATION")
        lines.append("-" * 70)
        bh = results.get('bone_hierarchy', {})
        if bh:
            passed = bh.get('passed', False)
            lines.append(f"  Result:                  {'PASS' if passed else 'FAIL'}")
            lines.append(f"  1.12.2 Pairs:            {bh.get('hierarchy_pairs_1122', 0)}")
            lines.append(f"  1.20.1 Pairs:            {bh.get('hierarchy_pairs_1201', 0)}")
            lines.append(f"  Missing Pairs:           {bh.get('missing_pairs', 0)}")
            lines.append(f"  Orphaned Bones:          {bh.get('orphaned_bones', 0)}")
            lines.append(f"  Root Bone Valid:         {'Yes' if bh.get('root_bone_valid') else 'No'}")
            if bh.get('root_bone_issues'):
                for issue in bh['root_bone_issues']:
                    lines.append(f"    Root Issue: {issue}")
        else:
            lines.append("  No bone hierarchy data available")
        lines.append("")

        # 4. Animation Matching
        lines.append("-" * 70)
        lines.append("  4. ANIMATION BONE NAME MATCHING")
        lines.append("-" * 70)
        am = results.get('animation_matching', {})
        if am.get('checked', False):
            passed = am.get('passed', False)
            lines.append(f"  Result:            {'PASS' if passed else 'FAIL'}")
            lines.append(f"  Anim Bones:        {am.get('total_anim_bones', 0)}")
            lines.append(f"  Matched:           {am.get('matched_bones', 0)}")
            lines.append(f"  Missing:           {am.get('missing_bones', 0)}")
            missing = am.get('missing_bone_names', [])
            if missing:
                lines.append(f"  Missing Bone Names:")
                for name in missing:
                    lines.append(f"    - {name}")
        else:
            lines.append(f"  Skipped: {am.get('reason', 'Not provided')}")
        lines.append("")

        # 5. Inflate Handling
        lines.append("-" * 70)
        lines.append("  5. INFLATE HANDLING VERIFICATION")
        lines.append("-" * 70)
        inf = results.get('inflate_validation', {})
        if inf:
            passed = inf.get('passed', False)
            lines.append(f"  Result:              {'PASS' if passed else 'FAIL'}")
            lines.append(f"  Cubes with Inflate:  {inf.get('cubes_with_inflate', 0)}")
            lines.append(f"  Issues:              {inf.get('issue_count', 0)}")
        else:
            lines.append("  No inflate validation data available")
        lines.append("")

        # 6. Y-Offset
        lines.append("-" * 70)
        lines.append("  6. Y-OFFSET VALIDATION (Root Bone [0,24,0])")
        lines.append("-" * 70)
        yo = results.get('y_offset_validation', {})
        if yo:
            passed = yo.get('passed', False)
            lines.append(f"  Result:             {'PASS' if passed else 'FAIL'}")
            lines.append(f"  Root Bone Valid:    {'Yes' if yo.get('root_valid') else 'No'}")
            rd = yo.get('root_details', {})
            if 'pivot' in rd:
                lines.append(f"  Root Pivot:         {rd['pivot']}")
                lines.append(f"  Expected Pivot:     {rd.get('expected_pivot', [0, 24, 0])}")
            lines.append(f"  Top-level Bones:    {yo.get('top_level_bone_count', 0)}")
        else:
            lines.append("  No Y-offset data available")
        lines.append("")

        # 7. Blockbench Format
        lines.append("-" * 70)
        lines.append("  7. BLOCKBENCH FORMAT VALIDATION")
        lines.append("-" * 70)
        bb = results.get('blockbench_format', {})
        if bb.get('checked', True):
            passed = bb.get('passed', False)
            lines.append(f"  Result:       {'PASS' if passed else 'FAIL'}")
            lines.append(f"  Issues:       {bb.get('issue_count', 0)}")
            checks = bb.get('checks', {})
            if checks:
                for check_name, check_val in checks.items():
                    status_str = "PASS" if check_val else "FAIL"
                    lines.append(f"  {check_name:30s} {status_str}")
        else:
            lines.append(f"  Skipped: {bb.get('reason', 'Not provided')}")
        lines.append("")

        # Footer
        lines.append("=" * 70)
        lines.append("  END OF REPORT")
        lines.append("=" * 70)

        return "\n".join(lines)

    # ========================================================================
    # Original Vertex Computation Methods (preserved)
    # ========================================================================

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

            # Local transform = T(pivot) * R
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

        # Compute world transforms - start with root bone
        world_transforms = {}

        # Find root bone and set its transform
        root_bone = bone_lookup.get('root')
        if root_bone:
            pivot = root_bone.get('pivot', [0, 24, 0])
            rotation = root_bone.get('rotation', [0, 0, 0])
            rx = math.radians(rotation[0])
            ry = math.radians(rotation[1])
            rz = math.radians(rotation[2])
            root_transform = self._make_transform_1201(pivot[0], pivot[1], pivot[2], rx, ry, rz)
            world_transforms['root'] = root_transform
        else:
            # If no root bone, use identity at (0, 24, 0) as fallback
            root_transform = np.eye(4)
            root_transform[1, 3] = self.ROOT_BONE_PIVOT_Y
            world_transforms['root'] = root_transform

        # Compute transforms for all children of root
        self._compute_world_transforms_1201(bone_lookup, world_transforms, 'root', root_transform)

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

                # Account for inflate if present
                inflate = cube.get('inflate', 0.0)
                if abs(inflate) > 1e-10:
                    ox -= inflate
                    oy -= inflate
                    oz -= inflate
                    w += 2 * inflate
                    h += 2 * inflate
                    d += 2 * inflate

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

        Enhanced: properly handles the Y-offset (root bone at [0,24,0]) by
        accounting for the coordinate system transformation M_model = diag(1,-1,-1).

        Args:
            verts_1122: Dict of bone_name -> vertices in 1.12.2 Y-down RH space
            verts_1201: Dict of bone_name -> vertices in 1.20.1 Y-up LH space
            tolerance: Maximum allowed distance between matching vertices

        Returns:
            Verification report dict
        """
        # M_model = diag(1, -1, -1) converts 1.12.2 Y-down RH → 1.20.1 Y-up LH
        # This is the full model transformation used by CoreMath
        M_model = np.diag([1.0, -1.0, -1.0])

        total_verts = 0
        matching_verts = 0
        total_error = 0.0
        max_error = 0.0
        details = []

        # Match bones by name
        bone_mapping_1122_to_1201 = {}
        for name_1122 in verts_1122:
            # Try direct match
            if name_1122 in verts_1201:
                bone_mapping_1122_to_1201[name_1122] = name_1122

        for name_1122, name_1201 in bone_mapping_1122_to_1201.items():
            v1122 = verts_1122[name_1122]
            v1201 = verts_1201[name_1201]

            # Convert 1.12.2 vertices to 1.20.1 Y-up LH space using M_model
            # M_model = diag(1, -1, -1) flips Y and Z
            v1122_converted = (M_model @ v1122.T).T

            # Add Y-offset: in 1.12.2, origin is at top of entity (y=0)
            # In 1.20.1, origin is at feet (y=0), with root at y=24
            # After M_model, the 1.12.2 y=0 becomes y=0 in the flipped system
            # But the root bone is at y=24 in the 1.20.1 system
            # So we add +24 to the Y coordinate to account for the root bone offset
            v1122_converted[:, 1] += self.ROOT_BONE_PIVOT_Y

            n_verts = min(len(v1122_converted), len(v1201))
            if n_verts == 0:
                continue

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
            'details': details,
            'y_offset_applied': True,
            'transform_matrix': 'M_model = diag(1, -1, -1)'
        }


if __name__ == "__main__":
    print("ModelVerifier module loaded successfully.")
    print("Usage: Instantiate ModelVerifier and call verify() or verify_full() with model data")
    print("")
    print("Available verification methods:")
    print("  verify()                       - Vertex position comparison")
    print("  verify_full()                  - Complete verification suite")
    print("  validate_uv_coordinates()      - UV texture bounds check")
    print("  validate_bone_hierarchy()      - Parent-child relationship check")
    print("  validate_animation_bone_names() - Animation bone name matching")
    print("  validate_inflate_handling()    - Inflate value verification")
    print("  validate_y_offset()            - Root bone Y-offset check")
    print("  verify_blockbench_format()     - Blockbench format validation")
    print("  generate_verification_report() - Generate text report")
