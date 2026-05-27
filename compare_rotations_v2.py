#!/usr/bin/env python3
"""
Targeted analysis: Test if the difference between reference and output rotations
is due to a different Euler angle convention (order of rotations).

Key observation from initial analysis:
- Reference rotations for dec/hair bones have rz≈0 but output has non-zero rz
- This strongly suggests a different Euler angle decomposition order
"""

import json
import numpy as np
from scipy.spatial.transform import Rotation


def extract_bones_from_outliner(node, parent_path=""):
    bones = {}
    path = f"{parent_path}/{node.get('name', '?')}" if parent_path else node.get('name', 'root')
    if isinstance(node, dict) and 'name' in node:
        rot = node.get('rotation', [0.0, 0.0, 0.0])
        origin = node.get('origin', [0.0, 0.0, 0.0])
        bones[node['name']] = {
            'rotation': list(rot),
            'origin': list(origin),
        }
        for child in node.get('children', []):
            if isinstance(child, dict):
                bones.update(extract_bones_from_outliner(child, path))
    return bones


def load_bones(filepath):
    with open(filepath) as f:
        data = json.load(f)
    all_bones = {}
    for node in data.get('outliner', []):
        all_bones.update(extract_bones_from_outliner(node))
    return all_bones


def normalize_angle(a):
    return (a + 180) % 360 - 180


def angles_close(a, b, tol=0.5):
    return all(abs(normalize_angle(x - y)) < tol for x, y in zip(a, b))


# All 6 possible Euler angle orders
EULER_ORDERS = ['XYZ', 'XZY', 'YXZ', 'YZX', 'ZXY', 'ZYX']
# Both intrinsic (lower) and extrinsic (upper) conventions
ALL_ORDERS = EULER_ORDERS + [e.lower() for e in EULER_ORDERS]


def main():
    ref_kirin = "/home/z/my-project/upload/kirin_debug (1).bbmodel"
    ref_heblu = "/home/z/my-project/upload/heblu_debug.bbmodel"
    out_kirin = "/home/z/my-project/converter/output/kirin_debug.bbmodel"
    out_heblu = "/home/z/my-project/converter/output/heblu_debug.bbmodel"
    
    ref_kb = load_bones(ref_kirin)
    ref_hb = load_bones(ref_heblu)
    out_kb = load_bones(out_kirin)
    out_hb = load_bones(out_heblu)
    
    print("=" * 140)
    print("EULER ANGLE CONVENTION ANALYSIS")
    print("=" * 140)
    print()
    print("Hypothesis: The output file uses a DIFFERENT Euler angle order than the reference.")
    print("The reference uses XYZ (intrinsic). We test if the output uses a different order.")
    print()
    print("Method: For each bone with differing rotation, convert the output Euler angles")
    print("to a rotation matrix using the output's convention, then decompose back using")
    print("the reference's XYZ convention. If the result matches the reference, we found")
    print("the output's convention.")
    print()
    
    for model_name, ref_bones, out_bones in [
        ("KIRIN", ref_kb, out_kb),
        ("HEBLU", ref_hb, out_hb),
    ]:
        common = sorted(set(ref_bones.keys()) & set(out_bones.keys()))
        diff_bones = []
        for name in common:
            ref_rot = ref_bones[name]['rotation']
            out_rot = out_bones[name]['rotation']
            if not angles_close(ref_rot, out_rot, tol=0.5):
                diff_bones.append((name, ref_rot, out_rot))
        
        print(f"\n{'='*140}")
        print(f"  MODEL: {model_name}  ({len(diff_bones)} bones differ)")
        print(f"{'='*140}")
        
        # Test each possible output convention
        # The reference convention is XYZ (intrinsic, uppercase = extrinsic in scipy)
        # In scipy: uppercase = extrinsic, lowercase = intrinsic
        # Blockbench uses intrinsic XYZ, which in scipy is 'xyz'
        
        # Actually let's be careful. Blockbench applies rotations as:
        # R = Rz * Ry * Rx (intrinsic XYZ means X first, then Y around new Y, then Z around new Z)
        # This is equivalent to extrinsic ZYX: R = Rz * Ry * Rx
        # In scipy: 'XYZ' (uppercase) = extrinsic XYZ = Rx * Ry * Rz
        #           'xyz' (lowercase) = intrinsic XYZ = Rz * Ry * Rx
        # Blockbench intrinsic XYZ = scipy 'xyz'
        
        REF_CONVENTION = 'xyz'  # Blockbench intrinsic XYZ
        
        # Test: if output stores angles in convention OUT_CONV, and we read them as OUT_CONV,
        # build the rotation matrix, then decompose as REF_CONVENTION, do we get the reference values?
        
        best_order = None
        best_count = 0
        order_match_counts = {}
        
        for out_conv in ALL_ORDERS:
            match_count = 0
            total_tested = 0
            
            for name, ref_rot, out_rot in diff_bones:
                try:
                    # Build rotation matrix from output angles using the candidate output convention
                    R_out = Rotation.from_euler(out_conv, out_rot, degrees=True).as_matrix()
                    # Decompose back using the reference convention
                    ref_decomposed = Rotation.from_matrix(R_out).as_euler(REF_CONVENTION, degrees=True)
                    ref_decomposed_norm = [normalize_angle(a) for a in ref_decomposed]
                    ref_norm = [normalize_angle(a) for a in ref_rot]
                    
                    if angles_close(ref_decomposed_norm, ref_norm, tol=0.5):
                        match_count += 1
                    total_tested += 1
                except:
                    pass
            
            order_match_counts[out_conv] = (match_count, total_tested)
            if match_count > best_count:
                best_count = match_count
                best_order = out_conv
        
        print(f"\nEuler order match counts (out_conv → ref_conv '{REF_CONVENTION}'):")
        for out_conv in ALL_ORDERS:
            mc, tt = order_match_counts[out_conv]
            pct = 100 * mc / max(tt, 1)
            bar = "█" * mc + "░" * (tt - mc)
            marker = " <<<" if out_conv == best_order else ""
            print(f"  out_conv={out_conv:>5s}: {mc:>3d}/{tt:>3d} match ({pct:>5.1f}%) {bar}{marker}")
        
        # Now test the OTHER direction: maybe the reference uses a different convention
        # and we need to decompose using that convention
        print(f"\n--- Reverse: What if the reference uses different convention? ---")
        ref_order_match = {}
        for ref_conv in ALL_ORDERS:
            match_count = 0
            total_tested = 0
            
            for name, ref_rot, out_rot in diff_bones:
                try:
                    # Build rotation matrix from reference angles using candidate ref convention
                    R_ref = Rotation.from_euler(ref_conv, ref_rot, degrees=True).as_matrix()
                    # Decompose using the output convention (XYZ intrinsic)
                    out_decomposed = Rotation.from_matrix(R_ref).as_euler('xyz', degrees=True)
                    out_decomposed_norm = [normalize_angle(a) for a in out_decomposed]
                    out_norm = [normalize_angle(a) for a in out_rot]
                    
                    if angles_close(out_decomposed_norm, out_norm, tol=0.5):
                        match_count += 1
                    total_tested += 1
                except:
                    pass
            
            ref_order_match[ref_conv] = (match_count, total_tested)
        
        for ref_conv in ALL_ORDERS:
            mc, tt = ref_order_match[ref_conv]
            pct = 100 * mc / max(tt, 1)
            bar = "█" * mc + "░" * (tt - mc)
            print(f"  ref_conv={ref_conv:>5s} → out='xyz': {mc:>3d}/{tt:>3d} match ({pct:>5.1f}%) {bar}")
        
        # Now let's do the most important test: 
        # Build the rotation matrix from OUTPUT angles using BEST output convention
        # and compare with rotation matrix from REFERENCE angles using 'xyz'
        print(f"\n--- Best match detailed verification: out_conv='{best_order}' ---")
        print(f"{'Bone':<20} {'out_rot':>35} {'ref_rot':>35} {'recomposed':>35} {'Match':>6}")
        print("-" * 140)
        
        for name, ref_rot, out_rot in diff_bones[:30]:  # Show first 30
            try:
                R_out = Rotation.from_euler(best_order, out_rot, degrees=True).as_matrix()
                ref_decomposed = Rotation.from_matrix(R_out).as_euler(REF_CONVENTION, degrees=True)
                ref_decomposed_norm = [normalize_angle(a) for a in ref_decomposed]
                ref_norm = [normalize_angle(a) for a in ref_rot]
                
                match = angles_close(ref_decomposed_norm, ref_norm, tol=0.5)
                match_str = "✓" if match else "✗"
                
                print(f"{name:<20} [{out_rot[0]:>8.2f},{out_rot[1]:>8.2f},{out_rot[2]:>8.2f}]  "
                      f"[{ref_rot[0]:>8.2f},{ref_rot[1]:>8.2f},{ref_rot[2]:>8.2f}]  "
                      f"[{ref_decomposed_norm[0]:>8.2f},{ref_decomposed_norm[1]:>8.2f},{ref_decomposed_norm[2]:>8.2f}]  "
                      f"{match_str:>6}")
            except Exception as e:
                print(f"{name:<20} ERROR: {e}")

    # Also test the hypothesis that both use XYZ but with a coordinate system flip
    print("\n\n" + "=" * 140)
    print("COORDINATE SYSTEM FLIP ANALYSIS")
    print("=" * 140)
    print()
    print("Test: Build rotation matrix from output, apply coordinate flip, decompose as xyz")
    
    COORD_FLIPS = {
        "flip_x: diag(-1,1,1)": [-1, 1, 1],
        "flip_y: diag(1,-1,1)": [1, -1, 1],
        "flip_z: diag(1,1,-1)": [1, 1, -1],
        "flip_xz: diag(-1,1,-1)": [-1, 1, -1],
        "flip_xy: diag(-1,-1,1)": [-1, -1, 1],
        "flip_yz: diag(1,-1,-1)": [1, -1, -1],
        "flip_xyz: diag(-1,-1,-1)": [-1, -1, -1],
    }
    
    # For each flip, test: R_ref = D * R_out * D (similarity transform)
    # and also: R_ref = D * R_out and R_ref = R_out * D
    # and also: angles_ref = D * angles_out (simple sign flip)
    
    for model_name, ref_bones, out_bones in [
        ("KIRIN", ref_kb, out_kb),
        ("HEBLU", ref_hb, out_hb),
    ]:
        common = sorted(set(ref_bones.keys()) & set(out_bones.keys()))
        diff_bones = []
        for name in common:
            ref_rot = ref_bones[name]['rotation']
            out_rot = out_bones[name]['rotation']
            if not angles_close(ref_rot, out_rot, tol=0.5):
                diff_bones.append((name, ref_rot, out_rot))
        
        print(f"\n--- {model_name} ---")
        
        for flip_name, flip_diag in COORD_FLIPS.items():
            for transform_type in ["D*R_out*D", "D*R_out", "R_out*D", "sign_flip"]:
                match_count = 0
                for name, ref_rot, out_rot in diff_bones:
                    try:
                        R_out = Rotation.from_euler('xyz', out_rot, degrees=True).as_matrix()
                        R_ref = Rotation.from_euler('xyz', ref_rot, degrees=True).as_matrix()
                        D = np.diag([float(d) for d in flip_diag])
                        
                        if transform_type == "D*R_out*D":
                            R_test = D @ R_out @ D
                        elif transform_type == "D*R_out":
                            R_test = D @ R_out
                        elif transform_type == "R_out*D":
                            R_test = R_out @ D
                        elif transform_type == "sign_flip":
                            # Simple sign flip on angles
                            test_angles = [out_rot[i] * flip_diag[i] for i in range(3)]
                            R_test = Rotation.from_euler('xyz', test_angles, degrees=True).as_matrix()
                        
                        if np.allclose(R_test, R_ref, atol=1e-4):
                            match_count += 1
                    except:
                        pass
                
                if match_count > 0:
                    pct = 100 * match_count / len(diff_bones)
                    print(f"  {flip_name:>30s} {transform_type:>12s}: {match_count:>3d}/{len(diff_bones)} ({pct:>5.1f}%)")

    # Final: test ALL combinations of Euler order + coordinate flip
    print("\n\n" + "=" * 140)
    print("COMBINED: EULER ORDER + COORDINATE FLIP")
    print("=" * 140)
    
    for model_name, ref_bones, out_bones in [
        ("KIRIN", ref_kb, out_kb),
        ("HEBLU", ref_hb, out_hb),
    ]:
        common = sorted(set(ref_bones.keys()) & set(out_bones.keys()))
        diff_bones = []
        for name in common:
            ref_rot = ref_bones[name]['rotation']
            out_rot = out_bones[name]['rotation']
            if not angles_close(ref_rot, out_rot, tol=0.5):
                diff_bones.append((name, ref_rot, out_rot))
        
        print(f"\n--- {model_name} ({len(diff_bones)} differing bones) ---")
        
        results = []
        for out_conv in ALL_ORDERS:
            for flip_name, flip_diag in COORD_FLIPS.items():
                for transform_type in ["D*R_out*D", "sign_flip"]:
                    match_count = 0
                    for name, ref_rot, out_rot in diff_bones:
                        try:
                            R_out = Rotation.from_euler(out_conv, out_rot, degrees=True).as_matrix()
                            R_ref = Rotation.from_euler('xyz', ref_rot, degrees=True).as_matrix()
                            D = np.diag([float(d) for d in flip_diag])
                            
                            if transform_type == "D*R_out*D":
                                R_test = D @ R_out @ D
                            elif transform_type == "sign_flip":
                                test_angles = [out_rot[i] * flip_diag[i] for i in range(3)]
                                R_test = Rotation.from_euler(out_conv, test_angles, degrees=True).as_matrix()
                            
                            if np.allclose(R_test, R_ref, atol=1e-4):
                                match_count += 1
                        except:
                            pass
                    
                    if match_count > 0:
                        pct = 100 * match_count / len(diff_bones)
                        results.append((match_count, pct, out_conv, flip_name, transform_type))
        
        results.sort(key=lambda x: -x[0])
        print(f"  {'Count':>5} {'%':>6} {'OutConv':>6} {'Flip':>25} {'Transform':>15}")
        for count, pct, out_conv, flip, transform in results[:20]:
            print(f"  {count:>5d} {pct:>5.1f}% {out_conv:>6s} {flip:>25s} {transform:>15s}")

    # Final definitive test: verify the rotation matrices are actually the same
    # for bones where the Euler angles differ
    print("\n\n" + "=" * 140)
    print("ARE THE ROTATION MATRICES ACTUALLY THE SAME?")
    print("(Testing if ref and output represent the SAME rotation in different Euler conventions)")
    print("=" * 140)
    
    for model_name, ref_bones, out_bones in [
        ("KIRIN", ref_kb, out_kb),
        ("HEBLU", ref_hb, out_hb),
    ]:
        common = sorted(set(ref_bones.keys()) & set(out_bones.keys()))
        diff_bones = []
        for name in common:
            ref_rot = ref_bones[name]['rotation']
            out_rot = out_bones[name]['rotation']
            if not angles_close(ref_rot, out_rot, tol=0.5):
                diff_bones.append((name, ref_rot, out_rot))
        
        print(f"\n--- {model_name} ---")
        
        same_matrix_count = 0
        for name, ref_rot, out_rot in diff_bones:
            R_ref = Rotation.from_euler('xyz', ref_rot, degrees=True).as_matrix()
            R_out = Rotation.from_euler('xyz', out_rot, degrees=True).as_matrix()
            if np.allclose(R_ref, R_out, atol=1e-4):
                same_matrix_count += 1
        
        print(f"  Bones where R_ref ≈ R_out (same rotation, different Euler angles): "
              f"{same_matrix_count}/{len(diff_bones)}")
        
        # If they're NOT the same matrix, find what transforms R_out to R_ref
        if same_matrix_count < len(diff_bones):
            print(f"\n  Testing what matrix operation converts R_out to R_ref:")
            
            # The relationship R_ref = A * R_out * B for some A, B
            # Let's compute the residual R_ref * R_out^T
            for name, ref_rot, out_rot in diff_bones[:5]:
                R_ref = Rotation.from_euler('xyz', ref_rot, degrees=True).as_matrix()
                R_out = Rotation.from_euler('xyz', out_rot, degrees=True).as_matrix()
                
                # R_ref = X * R_out, so X = R_ref * R_out^T
                X = R_ref @ R_out.T
                print(f"\n  Bone '{name}':")
                print(f"    out_rot = [{out_rot[0]:.4f}, {out_rot[1]:.4f}, {out_rot[2]:.4f}]")
                print(f"    ref_rot = [{ref_rot[0]:.4f}, {ref_rot[1]:.4f}, {ref_rot[2]:.4f}]")
                print(f"    R_ref * R_out^T:")
                for row in X:
                    print(f"      [{row[0]:>10.6f}, {row[1]:>10.6f}, {row[2]:>10.6f}]")
                
                # Check if X is a diagonal matrix
                is_diag = np.allclose(X - np.diag(np.diag(X)), 0, atol=1e-4)
                print(f"    Is diagonal? {is_diag}")
                if is_diag:
                    print(f"    Diagonal values: {np.diag(X)}")


if __name__ == "__main__":
    main()
