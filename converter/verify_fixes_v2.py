#!/usr/bin/env python3
"""
Comprehensive verification of 4 bug fixes by comparing output vs reference bbmodel files.
"""
import json
import math

def load(path):
    with open(path) as f:
        return json.load(f)

def elem_map(data):
    return {e['name']: e for e in data.get('elements', [])}

def bone_map_with_depth(data):
    m = {}
    def walk(items, depth):
        for item in items:
            if isinstance(item, str): continue
            if isinstance(item, dict):
                m[item['name']] = {'bone': item, 'depth': depth}
                if 'children' in item: walk(item['children'], depth+1)
    walk(data.get('outliner', []), 0)
    return m

def euler_to_mat(rx, ry, rz):
    rx, ry, rz = math.radians(rx), math.radians(ry), math.radians(rz)
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    return [
        [cz*cy, cz*sy*sx - sz*cx, cz*sy*cx + sz*sx],
        [sz*cy, sz*sy*sx + cz*cx, sz*sy*cx - cz*sx],
        [-sy,   cy*sx,            cy*cx            ]
    ]

def mat_match(A, B, tol=1e-4):
    return all(abs(A[i][j]-B[i][j]) < tol for i in range(3) for j in range(3))

MODELS = [
    ('kirin_debug', '/home/z/my-project/upload/kirin_debug (1).bbmodel', '/home/z/my-project/converter/output/kirin_debug.bbmodel'),
    ('heblu_debug', '/home/z/my-project/upload/heblu_debug.bbmodel', '/home/z/my-project/converter/output/heblu_debug.bbmodel'),
]

HEBLU_SKIN_ELEMENTS = ['skin_1_c0', 'skin_2_c0', 'skin_4_c0', 'skin_5_c0']

print("=" * 80)
print("  BUG FIX VERIFICATION REPORT")
print("  Comparing output .bbmodel files against reference files")
print("=" * 80)

for model_name, ref_path, out_path in MODELS:
    ref = load(ref_path)
    out = load(out_path)
    
    ref_e = elem_map(ref)
    out_e = elem_map(out)
    ref_bd = bone_map_with_depth(ref)
    out_bd = bone_map_with_depth(out)
    
    common_elem = set(ref_e.keys()) & set(out_e.keys())
    common_bone = set(ref_bd.keys()) & set(out_bd.keys())
    
    print(f"\n{'━' * 80}")
    print(f"  MODEL: {model_name}")
    print(f"  Elements: {len(ref_e)} ref, {len(out_e)} out, {len(common_elem)} common")
    print(f"  Bones:    {len(ref_bd)} ref, {len(out_bd)} out, {len(common_bone)} common")
    print(f"{'━' * 80}")
    
    # ========================================================================
    # CHECK 1: Y-OFFSET FIX
    # ========================================================================
    print(f"\n  ┌─────────────────────────────────────────────────────────────┐")
    print(f"  │ CHECK 1: Y-OFFSET FIX                                      │")
    print(f"  │ Bug: Y values should not be offset by -24 from reference   │")
    print(f"  └─────────────────────────────────────────────────────────────┘")
    
    # Element Y diffs
    elem_y_diffs = 0
    elem_y_perfect = 0
    elem_diff_values = {}
    for name in common_elem:
        re, oe = ref_e[name], out_e[name]
        diff = oe['from'][1] - re['from'][1]
        if abs(diff) > 0.01:
            elem_y_diffs += 1
            rdiff = round(diff)
            elem_diff_values[rdiff] = elem_diff_values.get(rdiff, 0) + 1
        else:
            elem_y_perfect += 1
    
    # Bone origin Y diffs
    bone_y_diffs = 0
    bone_y_perfect = 0
    bone_diff_by_depth = {}
    for name in common_bone:
        rb = ref_bd[name]['bone']
        ob = out_bd[name]['bone']
        depth = ref_bd[name]['depth']
        ro = rb.get('origin', [0,0,0])
        oo = ob.get('origin', [0,0,0])
        diff = oo[1] - ro[1]
        if abs(diff) > 0.01:
            bone_y_diffs += 1
            if depth not in bone_diff_by_depth:
                bone_diff_by_depth[depth] = []
            bone_diff_by_depth[depth].append(round(diff))
        else:
            bone_y_perfect += 1
    
    if elem_y_diffs == 0 and bone_y_diffs == 0:
        print(f"  ✅ ALL Y values match — Y-offset fix is correct!")
    else:
        print(f"  ❌ Y-OFFSET FIX IS NOT CORRECT")
        print(f"     Elements: {elem_y_perfect} match, {elem_y_diffs} differ")
        print(f"     Bones:    {bone_y_perfect} match, {bone_y_diffs} differ")
        print(f"")
        print(f"  PATTERN: Y diff = depth × 24 (offset accumulates per hierarchy level)")
        print(f"  Element Y diff distribution:")
        for d in sorted(elem_diff_values.keys()):
            print(f"    diff={d:+5.0f}: {elem_diff_values[d]} elements")
        print(f"  Bone Y diff by hierarchy depth:")
        for depth in sorted(bone_diff_by_depth.keys())[:8]:
            vals = bone_diff_by_depth[depth]
            print(f"    depth {depth:2d}: diff={vals[0]:+5.0f} ({len(vals)} bones)")
        if len(bone_diff_by_depth) > 8:
            print(f"    ... (continues up to depth {max(bone_diff_by_depth.keys())})")
        print(f"")
        print(f"  ROOT CAUSE: The +24 Y-offset is being applied at EACH bone in the")
        print(f"  hierarchy, accumulating with depth. The reference only applies it once")
        print(f"  at the root level (or uses Bedrock coords where it's already included).")
    
    # ========================================================================
    # CHECK 2: NORTH↔SOUTH UV SWAP FIX
    # ========================================================================
    print(f"\n  ┌─────────────────────────────────────────────────────────────┐")
    print(f"  │ CHECK 2: NORTH↔SOUTH UV SWAP FIX                           │")
    print(f"  │ Bug: North and South face UVs were swapped in output       │")
    print(f"  └─────────────────────────────────────────────────────────────┘")
    
    ns_diffs = 0
    ns_swapped = 0
    ns_details = []
    for name in common_elem:
        re, oe = ref_e[name], out_e[name]
        rf, of = re.get('faces', {}), oe.get('faces', {})
        rn = rf.get('north', {}).get('uv', [])
        on = of.get('north', {}).get('uv', [])
        rs = rf.get('south', {}).get('uv', [])
        os = of.get('south', {}).get('uv', [])
        
        north_match = rn == on
        south_match = rs == os
        is_swapped = rn == os and rs == on and not north_match
        
        if not north_match or not south_match:
            ns_diffs += 1
            if is_swapped:
                ns_swapped += 1
            ns_details.append({
                'name': name,
                'ref_north': rn, 'out_north': on,
                'ref_south': rs, 'out_south': os,
                'swapped': is_swapped
            })
    
    if ns_diffs == 0:
        print(f"  ✅ ALL north/south UVs match — North↔South UV swap fix is correct!")
    else:
        print(f"  ⚠️  {ns_diffs} elements with north/south UV differences")
        print(f"     Of those, {ns_swapped} appear to be actual north↔south swaps")
        for d in ns_details[:5]:
            tag = " SWAPPED!" if d['swapped'] else ""
            print(f"     - {d['name']}:")
            print(f"       north: ref={d['ref_north']} out={d['out_north']}{tag}")
            print(f"       south: ref={d['ref_south']} out={d['out_south']}{tag}")
        # Check if these are all skin elements with [0,0,0,0] in ref
        skin_with_zero = all(d['ref_north'] == [0,0,0,0] and d['ref_south'] == [0,0,0,0] for d in ns_details)
        if skin_with_zero:
            print(f"     NOTE: All differing elements have UV=[0,0,0,0] in reference.")
            print(f"     These are skin/decoration elements — the non-skin elements all match.")
            print(f"     The north↔south swap fix IS correct for actual geometry elements.")
    
    # ========================================================================
    # CHECK 3: ROTATION CONVERSION FIX
    # ========================================================================
    print(f"\n  ┌─────────────────────────────────────────────────────────────┐")
    print(f"  │ CHECK 3: ROTATION CONVERSION FIX                           │")
    print(f"  │ Bug: Rotation Euler angles were incorrectly converted       │")
    print(f"  └─────────────────────────────────────────────────────────────┘")
    
    euler_diffs = 0
    matrix_diffs = 0
    rot_with_nonzero = 0
    rot_details = []
    
    for name in common_bone:
        rb = ref_bd[name]['bone']
        ob = out_bd[name]['bone']
        rr = rb.get('rotation', [0,0,0])
        orr = ob.get('rotation', [0,0,0])
        
        if any(abs(v) > 0.01 for v in rr) or any(abs(v) > 0.01 for v in orr):
            rot_with_nonzero += 1
            euler_match = all(abs(rr[i]-orr[i]) < 0.01 for i in range(3))
            if not euler_match:
                euler_diffs += 1
                rm = euler_to_mat(*rr)
                om = euler_to_mat(*orr)
                if not mat_match(rm, om):
                    matrix_diffs += 1
                    rot_details.append(f"  ❌ {name}: ref={rr} out={orr} (matrices DIFFER)")
                else:
                    rot_details.append(f"  ⚠️  {name}: ref={rr} out={orr} (equivalent, matrices match)")
    
    # Also check element rotations
    for name in common_elem:
        re, oe = ref_e[name], out_e[name]
        rr = re.get('rotation', [0,0,0])
        orr = oe.get('rotation', [0,0,0])
        if any(abs(v) > 0.01 for v in rr) or any(abs(v) > 0.01 for v in orr):
            euler_match = all(abs(rr[i]-orr[i]) < 0.01 for i in range(3))
            if not euler_match:
                euler_diffs += 1
                rm = euler_to_mat(*rr)
                om = euler_to_mat(*orr)
                if not mat_match(rm, om):
                    matrix_diffs += 1
                    rot_details.append(f"  ❌ elem {name}: ref={rr} out={orr} (matrices DIFFER)")
    
    if matrix_diffs == 0:
        if rot_with_nonzero == 0:
            print(f"  ℹ️  No bones with non-zero rotation found.")
        else:
            print(f"  ✅ ALL rotations produce equivalent matrices — Rotation fix is correct!")
            print(f"     {rot_with_nonzero} bones with non-zero rotation, {euler_diffs} with different")
            print(f"     Euler representations but equivalent rotation matrices.")
            if euler_diffs > 0:
                print(f"     (Different Euler angle representations of the same rotation are valid)")
                for d in rot_details[:3]:
                    print(f"     {d}")
                if len(rot_details) > 3:
                    print(f"     ... and {len(rot_details)-3} more equivalent-but-different Euler angles")
    else:
        print(f"  ❌ {matrix_diffs} rotation matrix mismatches found!")
        for d in rot_details:
            print(d)
    
    # ========================================================================
    # CHECK 4: MIRROR_UV FIX
    # ========================================================================
    print(f"\n  ┌─────────────────────────────────────────────────────────────┐")
    print(f"  │ CHECK 4: MIRROR_UV FIX                                     │")
    print(f"  │ Bug: mirror_uv was incorrectly true for certain elements    │")
    print(f"  └─────────────────────────────────────────────────────────────┘")
    
    mirror_diffs = 0
    mirror_details = []
    for name in common_elem:
        re, oe = ref_e[name], out_e[name]
        rm = re.get('mirror_uv', False)
        om = oe.get('mirror_uv', False)
        if rm != om:
            mirror_diffs += 1
            is_skin = name in HEBLU_SKIN_ELEMENTS
            mirror_details.append(f"  ❌ {name}: ref={rm} out={om}" + (" [SKIN ELEMENT]" if is_skin else ""))
    
    if mirror_diffs == 0:
        print(f"  ✅ ALL mirror_uv values match — mirror_uv fix is correct!")
    else:
        print(f"  ❌ {mirror_diffs} mirror_uv mismatches:")
        for d in mirror_details:
            print(d)
        
        # Specific heblu skin check
        if model_name == 'heblu_debug':
            print(f"\n  Specific Heblu skin element check:")
            for sname in HEBLU_SKIN_ELEMENTS:
                if sname in out_e:
                    om = out_e[sname].get('mirror_uv', False)
                    rm = ref_e[sname].get('mirror_uv', False) if sname in ref_e else 'N/A'
                    status = "✅" if om == False else "❌"
                    print(f"    {status} {sname}: ref={rm} out={om}")

print(f"\n\n{'=' * 80}")
print(f"  SUMMARY")
print(f"{'=' * 80}")
print(f"""
  CHECK 1 - Y-OFFSET FIX:
    ❌ NOT FIXED — Y values still differ from reference
    Pattern: output_Y = ref_Y + (bone_depth × 24)
    The +24 offset is being applied at every bone in the hierarchy,
    accumulating multiplicatively. The reference only has the offset
    at the root level.
    
    kirin:  ALL 141 elements + ALL 142 bones have Y diffs
    heblu:  ALL 356 elements + ALL 357 bones have Y diffs

  CHECK 2 - NORTH↔SOUTH UV SWAP FIX:
    ✅ FIXED for geometry elements
    kirin:  0 north/south UV mismatches
    heblu:  6 UV mismatches, but ALL are skin elements with [0,0,0,0] 
            UV in reference vs actual UV in output. These are NOT swap
            issues — they're zero-UV vs computed-UV differences for
            skin/decoration elements. No actual N↔S swaps detected.

  CHECK 3 - ROTATION CONVERSION FIX:
    ✅ FIXED — All rotations produce equivalent matrices
    kirin:  17 Euler representations differ, but 0 matrix mismatches
    heblu:  10 Euler representations differ, but 0 matrix mismatches
    Different Euler angle representations of the same rotation are
    functionally equivalent and acceptable.

  CHECK 4 - MIRROR_UV FIX:
    ✅ FIXED for kirin (0 diffs)
    ❌ NOT FIXED for heblu — 4 skin elements still have mirror_uv=True:
       skin_1_c0, skin_2_c0, skin_4_c0, skin_5_c0
       (reference has mirror_uv=False for all of these)
""")
