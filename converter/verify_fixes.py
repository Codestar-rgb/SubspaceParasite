#!/usr/bin/env python3
"""
Verify bug fixes by comparing output bbmodel files against reference files.
Checks: Y-offset, North↔South UV swap, Rotation conversion, mirror_uv
"""

import json
import math
import sys
from collections import defaultdict

def load_bbmodel(path):
    with open(path, 'r') as f:
        return json.load(f)

def build_element_map(data):
    """Build a dict mapping element name -> element dict."""
    m = {}
    for elem in data.get('elements', []):
        m[elem['name']] = elem
    return m

def build_bone_map(data):
    """Build a dict mapping bone name -> bone dict, recursively.
    Outliner children can be strings (element UUIDs) or dicts (bones)."""
    m = {}
    def walk(items):
        for item in items:
            if isinstance(item, str):
                continue  # element UUID reference
            if isinstance(item, dict):
                m[item['name']] = item
                if 'children' in item:
                    walk(item['children'])
    walk(data.get('outliner', []))
    return m

def euler_to_rotation_matrix(rx, ry, rz, deg=True):
    """Convert Euler angles (in degrees) to a 3x3 rotation matrix.
    Uses ZYX order (Tait-Bryan): Rz * Ry * Rx
    This matches Bedrock/Blockbench convention.
    """
    if deg:
        rx = math.radians(rx)
        ry = math.radians(ry)
        rz = math.radians(rz)
    
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    
    # Rz * Ry * Rx
    R = [
        [cz*cy, cz*sy*sx - sz*cx, cz*sy*cx + sz*sx],
        [sz*cy, sz*sy*sx + cz*cx, sz*sy*cx - cz*sx],
        [-sy,   cy*sx,            cy*cx            ]
    ]
    return R

def matrices_equal(A, B, tol=1e-4):
    """Check if two 3x3 matrices are equal within tolerance."""
    for i in range(3):
        for j in range(3):
            if abs(A[i][j] - B[i][j]) > tol:
                return False
    return True

def format_matrix(M):
    lines = []
    for row in M:
        lines.append("  [" + ", ".join(f"{v:8.4f}" for v in row) + "]")
    return "\n".join(lines)

def compare_files(ref_path, out_path, model_name):
    """Compare a reference and output bbmodel file."""
    print(f"\n{'='*80}")
    print(f"  MODEL: {model_name}")
    print(f"{'='*80}")
    print(f"  Reference: {ref_path}")
    print(f"  Output:    {out_path}")
    print(f"{'='*80}")
    
    ref = load_bbmodel(ref_path)
    out = load_bbmodel(out_path)
    
    ref_elems = build_element_map(ref)
    out_elems = build_element_map(out)
    
    ref_bones = build_bone_map(ref)
    out_bones = build_bone_map(out)
    
    all_issues = 0
    
    # =========================================================================
    # CHECK 1: Y-OFFSET FIX
    # =========================================================================
    print(f"\n{'─'*80}")
    print("  CHECK 1: Y-OFFSET FIX")
    print(f"{'─'*80}")
    print("  Bug: Y values were off by -24.0 (Bedrock → Blockbench offset missing)")
    print("  Expected: Output Y values should match reference Y values exactly.\n")
    
    y_issues = 0
    y_details = []
    
    # Check element from/to/origin Y values
    common_elem_names = sorted(set(ref_elems.keys()) & set(out_elems.keys()))
    
    for name in common_elem_names:
        re = ref_elems[name]
        oe = out_elems[name]
        
        # Check from[1]
        ref_from_y = re['from'][1]
        out_from_y = oe['from'][1]
        diff_from = out_from_y - ref_from_y
        
        # Check to[1]
        ref_to_y = re['to'][1]
        out_to_y = oe['to'][1]
        diff_to = out_to_y - ref_to_y
        
        # Check origin[1]
        ref_origin_y = re['origin'][1]
        out_origin_y = oe['origin'][1]
        diff_origin = out_origin_y - ref_origin_y
        
        if abs(diff_from) > 0.01 or abs(diff_to) > 0.01 or abs(diff_origin) > 0.01:
            y_issues += 1
            y_details.append(f"  ❌ Element '{name}':")
            y_details.append(f"     from[1]: ref={ref_from_y:.2f} out={out_from_y:.2f} diff={diff_from:.2f}")
            y_details.append(f"     to[1]:   ref={ref_to_y:.2f} out={out_to_y:.2f} diff={diff_to:.2f}")
            y_details.append(f"     origin[1]: ref={ref_origin_y:.2f} out={out_origin_y:.2f} diff={diff_origin:.2f}")
    
    # Check bone origin Y values
    common_bone_names = sorted(set(ref_bones.keys()) & set(out_bones.keys()))
    for name in common_bone_names:
        rb = ref_bones[name]
        ob = out_bones[name]
        
        ref_origin_y = rb.get('origin', [0,0,0])[1]
        out_origin_y = ob.get('origin', [0,0,0])[1]
        diff = out_origin_y - ref_origin_y
        
        if abs(diff) > 0.01:
            y_issues += 1
            y_details.append(f"  ❌ Bone '{name}': origin[1] ref={ref_origin_y:.2f} out={out_origin_y:.2f} diff={diff:.2f}")
    
    if y_issues == 0:
        print("  ✅ ALL Y values match between reference and output — Y-offset fix is correct!")
    else:
        print(f"  ❌ {y_issues} elements/bones with Y differences found:")
        for d in y_details:
            print(d)
    
    all_issues += y_issues
    
    # =========================================================================
    # CHECK 2: NORTH↔SOUTH UV SWAP FIX
    # =========================================================================
    print(f"\n{'─'*80}")
    print("  CHECK 2: NORTH↔SOUTH UV SWAP FIX")
    print(f"{'─'*80}")
    print("  Bug: North and South face UVs were swapped in output")
    print("  Expected: North UV and South UV in output should match reference.\n")
    
    uv_issues = 0
    uv_details = []
    
    for name in common_elem_names:
        re = ref_elems[name]
        oe = out_elems[name]
        
        ref_faces = re.get('faces', {})
        out_faces = oe.get('faces', {})
        
        # Check north UV
        if 'north' in ref_faces and 'north' in out_faces:
            ref_north = ref_faces['north'].get('uv', [])
            out_north = out_faces['north'].get('uv', [])
            if ref_north != out_north:
                uv_issues += 1
                uv_details.append(f"  ❌ Element '{name}': north UV mismatch")
                uv_details.append(f"     ref={ref_north}  out={out_north}")
        
        # Check south UV
        if 'south' in ref_faces and 'south' in out_faces:
            ref_south = ref_faces['south'].get('uv', [])
            out_south = out_faces['south'].get('uv', [])
            if ref_south != out_south:
                uv_issues += 1
                uv_details.append(f"  ❌ Element '{name}': south UV mismatch")
                uv_details.append(f"     ref={ref_south}  out={out_south}")
    
    if uv_issues == 0:
        print("  ✅ ALL north and south UVs match — North↔South UV swap fix is correct!")
    else:
        print(f"  ❌ {uv_issues} north/south UV mismatches found:")
        for d in uv_details:
            print(d)
    
    all_issues += uv_issues
    
    # =========================================================================
    # CHECK 3: ROTATION CONVERSION FIX
    # =========================================================================
    print(f"\n{'─'*80}")
    print("  CHECK 3: ROTATION CONVERSION FIX")
    print(f"{'─'*80}")
    print("  Bug: Rotation conversion from source format was incorrect")
    print("  Expected: Rotation matrices from Euler angles should be equivalent.\n")
    
    rot_issues = 0
    rot_details = []
    
    # Check bone rotations
    bones_with_rotation = []
    for name in common_bone_names:
        rb = ref_bones[name]
        ob = out_bones[name]
        
        ref_rot = rb.get('rotation', [0,0,0])
        out_rot = ob.get('rotation', [0,0,0])
        
        # Only check bones with non-zero rotation in either
        ref_nonzero = any(abs(v) > 0.01 for v in ref_rot)
        out_nonzero = any(abs(v) > 0.01 for v in out_rot)
        
        if ref_nonzero or out_nonzero:
            bones_with_rotation.append((name, ref_rot, out_rot))
    
    print(f"  Found {len(bones_with_rotation)} bones with non-zero rotation.\n")
    
    for name, ref_rot, out_rot in bones_with_rotation:
        ref_mat = euler_to_rotation_matrix(*ref_rot)
        out_mat = euler_to_rotation_matrix(*out_rot)
        
        # Check if Euler angles match directly
        euler_match = all(abs(ref_rot[i] - out_rot[i]) < 0.01 for i in range(3))
        
        # Check if rotation matrices match
        mat_match = matrices_equal(ref_mat, out_mat)
        
        is_single_axis = sum(1 for v in ref_rot if abs(v) > 0.01) == 1
        
        if not euler_match:
            if not mat_match:
                rot_issues += 1
                rot_details.append(f"  ❌ Bone '{name}' (multi-axis):")
                rot_details.append(f"     Ref rotation:  {ref_rot}")
                rot_details.append(f"     Out rotation:  {out_rot}")
                rot_details.append(f"     Ref matrix:\n{format_matrix(ref_mat)}")
                rot_details.append(f"     Out matrix:\n{format_matrix(out_mat)}")
            else:
                # Matrices match but Euler angles differ — could be equivalent but different representation
                rot_details.append(f"  ⚠️  Bone '{name}': Euler angles differ but matrices are equivalent")
                rot_details.append(f"     Ref rotation: {ref_rot}")
                rot_details.append(f"     Out rotation: {out_rot}")
    
    # Also check element rotations
    for name in common_elem_names:
        re = ref_elems[name]
        oe = out_elems[name]
        
        ref_rot = re.get('rotation', [0,0,0])
        out_rot = oe.get('rotation', [0,0,0])
        
        ref_nonzero = any(abs(v) > 0.01 for v in ref_rot)
        out_nonzero = any(abs(v) > 0.01 for v in out_rot)
        
        if ref_nonzero or out_nonzero:
            euler_match = all(abs(ref_rot[i] - out_rot[i]) < 0.01 for i in range(3))
            ref_mat = euler_to_rotation_matrix(*ref_rot)
            out_mat = euler_to_rotation_matrix(*out_rot)
            mat_match = matrices_equal(ref_mat, out_mat)
            
            if not euler_match:
                if not mat_match:
                    rot_issues += 1
                    rot_details.append(f"  ❌ Element '{name}':")
                    rot_details.append(f"     Ref rotation:  {ref_rot}")
                    rot_details.append(f"     Out rotation:  {out_rot}")
    
    if rot_issues == 0:
        if bones_with_rotation:
            print("  ✅ ALL rotations match — Rotation conversion fix is correct!")
        else:
            print("  ℹ️  No bones with non-zero rotation found in this model.")
    else:
        print(f"  ❌ {rot_issues} rotation mismatches found:")
        for d in rot_details:
            print(d)
    
    all_issues += rot_issues
    
    # =========================================================================
    # CHECK 4: MIRROR_UV FIX
    # =========================================================================
    print(f"\n{'─'*80}")
    print("  CHECK 4: MIRROR_UV FIX")
    print(f"{'─'*80}")
    print("  Bug: mirror_uv was incorrectly set to true for certain skin elements")
    print("  Expected: mirror_uv should be false (matching reference).\n")
    
    mirror_issues = 0
    mirror_details = []
    
    # Check the Heblu skin elements specifically
    heblu_skin_elements = ['skin_1_c0', 'skin_2_c0', 'skin_4_c0', 'skin_5_c0']
    
    # Also do a general check for all elements
    for name in common_elem_names:
        re = ref_elems[name]
        oe = out_elems[name]
        
        ref_mirror = re.get('mirror_uv', False)
        out_mirror = oe.get('mirror_uv', False)
        
        if ref_mirror != out_mirror:
            mirror_issues += 1
            is_skin = name in heblu_skin_elements
            marker = " [SKIN ELEMENT]" if is_skin else ""
            mirror_details.append(f"  ❌ Element '{name}'{marker}: ref mirror_uv={ref_mirror}, out mirror_uv={out_mirror}")
    
    # Check specifically for Heblu skin elements even if they don't appear in common names
    for sname in heblu_skin_elements:
        if sname in out_elems:
            oe = out_elems[sname]
            out_mirror = oe.get('mirror_uv', False)
            if out_mirror:
                if sname not in ref_elems or sname not in common_elem_names:
                    mirror_issues += 1
                    mirror_details.append(f"  ❌ Skin element '{sname}': mirror_uv={out_mirror} (should be false)")
    
    if mirror_issues == 0:
        print("  ✅ ALL mirror_uv values match — mirror_uv fix is correct!")
    else:
        print(f"  ❌ {mirror_issues} mirror_uv mismatches found:")
        for d in mirror_details:
            print(d)
    
    all_issues += mirror_issues
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    print(f"\n{'='*80}")
    if all_issues == 0:
        print(f"  ✅ ALL CHECKS PASSED FOR {model_name.upper()} — All 4 bug fixes verified!")
    else:
        print(f"  ❌ {all_issues} total issues found for {model_name.upper()}")
    print(f"{'='*80}")
    
    return all_issues


def main():
    ref_kirin = "/home/z/my-project/upload/kirin_debug (1).bbmodel"
    out_kirin = "/home/z/my-project/converter/output/kirin_debug.bbmodel"
    ref_heblu = "/home/z/my-project/upload/heblu_debug.bbmodel"
    out_heblu = "/home/z/my-project/converter/output/heblu_debug.bbmodel"
    
    issues_kirin = compare_files(ref_kirin, out_kirin, "kirin_debug")
    issues_heblu = compare_files(ref_heblu, out_heblu, "heblu_debug")
    
    print(f"\n\n{'#'*80}")
    print(f"  GRAND SUMMARY")
    print(f"{'#'*80}")
    print(f"  kirin_debug: {issues_kirin} issues")
    print(f"  heblu_debug: {issues_heblu} issues")
    print(f"  TOTAL:       {issues_kirin + issues_heblu} issues")
    print(f"{'#'*80}")
    
    # Additional: Print Y-offset statistics for first few elements to verify the fix
    print(f"\n\n{'='*80}")
    print("  DETAILED Y-OFFSET ANALYSIS (first 10 elements per model)")
    print(f"{'='*80}")
    
    for model_name, ref_path, out_path in [
        ("kirin_debug", ref_kirin, out_kirin),
        ("heblu_debug", ref_heblu, out_heblu)
    ]:
        ref = load_bbmodel(ref_path)
        out = load_bbmodel(out_path)
        ref_elems = build_element_map(ref)
        out_elems = build_element_map(out)
        
        print(f"\n  {model_name}:")
        common = sorted(set(ref_elems.keys()) & set(out_elems.keys()))
        for name in common[:10]:
            re = ref_elems[name]
            oe = out_elems[name]
            
            ref_fy = re['from'][1]
            out_fy = oe['from'][1]
            ref_ty = re['to'][1]
            out_ty = oe['to'][1]
            ref_oy = re['origin'][1]
            out_oy = oe['origin'][1]
            
            diff_f = out_fy - ref_fy
            diff_t = out_ty - ref_ty
            diff_o = out_oy - ref_oy
            
            status = "✅" if (abs(diff_f) < 0.01 and abs(diff_t) < 0.01 and abs(diff_o) < 0.01) else "❌"
            print(f"  {status} {name:20s}  from_y diff={diff_f:+7.2f}  to_y diff={diff_t:+7.2f}  origin_y diff={diff_o:+7.2f}")
    
    # Print rotation statistics for bones with non-zero rotation
    print(f"\n\n{'='*80}")
    print("  DETAILED ROTATION ANALYSIS (all bones with non-zero rotation)")
    print(f"{'='*80}")
    
    for model_name, ref_path, out_path in [
        ("kirin_debug", ref_kirin, out_kirin),
        ("heblu_debug", ref_heblu, out_heblu)
    ]:
        ref = load_bbmodel(ref_path)
        out = load_bbmodel(out_path)
        ref_bones = build_bone_map(ref)
        out_bones = build_bone_map(out)
        
        print(f"\n  {model_name}:")
        common = sorted(set(ref_bones.keys()) & set(out_bones.keys()))
        found_any = False
        for name in common:
            rb = ref_bones[name]
            ob = out_bones[name]
            ref_rot = rb.get('rotation', [0,0,0])
            out_rot = ob.get('rotation', [0,0,0])
            
            if any(abs(v) > 0.01 for v in ref_rot) or any(abs(v) > 0.01 for v in out_rot):
                found_any = True
                match = all(abs(ref_rot[i] - out_rot[i]) < 0.01 for i in range(3))
                status = "✅" if match else "❌"
                print(f"  {status} {name:20s}  ref_rot={ref_rot}  out_rot={out_rot}")
                
                if not match:
                    ref_mat = euler_to_rotation_matrix(*ref_rot)
                    out_mat = euler_to_rotation_matrix(*out_rot)
                    mat_match = matrices_equal(ref_mat, out_mat)
                    print(f"     Matrix match: {mat_match}")
        
        if not found_any:
            print("  (no bones with non-zero rotation)")


if __name__ == '__main__':
    main()
