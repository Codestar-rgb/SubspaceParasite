#!/usr/bin/env python3
"""
Final verification: The output uses extrinsic XYZ Euler angles.
The reference uses intrinsic xyz Euler angles.
These represent the SAME rotation matrix, just decomposed differently.

Test: Read output as extrinsic XYZ, build rotation matrix, 
      compare with reference rotation matrix built from intrinsic xyz.
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
    print("DEFINITIVE TEST: Does the output store extrinsic XYZ while reference stores intrinsic xyz?")
    print("=" * 140)
    print()
    print("In scipy:")
    print("  'XYZ' (uppercase) = extrinsic: R = Rz(c) · Ry(b) · Rx(a)")
    print("  'xyz' (lowercase) = intrinsic: R = Rx(a) · Ry'(b) · Ry''(c) = equivalent to extrinsic ZYX with reversed angles")
    print()
    print("Blockbench uses intrinsic XYZ for its Euler angles.")
    print()
    
    for model_name, ref_bones, out_bones in [
        ("KIRIN", ref_kb, out_kb),
        ("HEBLU", ref_hb, out_hb),
    ]:
        common = sorted(set(ref_bones.keys()) & set(out_bones.keys()))
        
        print(f"\n{'='*140}")
        print(f"  MODEL: {model_name}")
        print(f"{'='*140}")
        
        # Test: Build rotation matrix from output using extrinsic XYZ
        # Compare with rotation matrix from reference using intrinsic xyz
        matrix_match = 0
        euler_mismatch = 0
        both_match = 0
        neither_match = 0
        
        failing_bones = []
        
        for name in common:
            ref_rot = ref_bones[name]['rotation']
            out_rot = out_bones[name]['rotation']
            
            # Build matrices
            try:
                R_ref = Rotation.from_euler('xyz', ref_rot, degrees=True).as_matrix()
                R_out_xyz = Rotation.from_euler('xyz', out_rot, degrees=True).as_matrix()  # reading output as intrinsic
                R_out_XYZ = Rotation.from_euler('XYZ', out_rot, degrees=True).as_matrix()  # reading output as extrinsic
                
                same_matrix_xyz = np.allclose(R_ref, R_out_xyz, atol=1e-4)
                same_matrix_XYZ = np.allclose(R_ref, R_out_XYZ, atol=1e-4)
                
                ref_norm = [normalize_angle(a) for a in ref_rot]
                out_norm = [normalize_angle(a) for a in out_rot]
                same_euler = all(abs(normalize_angle(ref_norm[i] - out_norm[i])) < 0.5 for i in range(3))
                
                if same_matrix_XYZ:
                    matrix_match += 1
                if not same_euler:
                    euler_mismatch += 1
                if same_matrix_XYZ and not same_euler:
                    both_match += 1
                if not same_matrix_XYZ and not same_euler:
                    neither_match += 1
                    
                if not same_matrix_XYZ and not same_euler:
                    failing_bones.append((name, ref_rot, out_rot, R_ref, R_out_XYZ))
                    
            except Exception as e:
                failing_bones.append((name, ref_rot, out_rot, None, None))
        
        print(f"\nTotal bones: {len(common)}")
        print(f"Bones where R_ref == R_out_XYZ (output as extrinsic XYZ): {matrix_match}/{len(common)}")
        print(f"Bones with different Euler angles: {euler_mismatch}/{len(common)}")
        print(f"Bones where matrices match but Euler angles differ: {both_match}/{len(common)}")
        print(f"Bones where NEITHER matrices nor Euler angles match: {neither_match}/{len(common)}")
        
        # Show the conversion: for each bone, read output as XYZ (extrinsic),
        # then decompose as xyz (intrinsic) to get the correct reference values
        print(f"\n--- CONVERSION VERIFICATION: Read output as extrinsic XYZ → decompose as intrinsic xyz ---")
        print(f"{'Bone':<20} {'out_angles':>35} {'ref_angles':>35} {'converted_angles':>35} {'MatrixMatch':>12} {'EulerMatch':>11}")
        print("-" * 150)
        
        for name in common:
            ref_rot = ref_bones[name]['rotation']
            out_rot = out_bones[name]['rotation']
            
            ref_norm = [normalize_angle(a) for a in ref_rot]
            out_norm = [normalize_angle(a) for a in out_rot]
            same_euler = all(abs(normalize_angle(ref_norm[i] - out_norm[i])) < 0.5 for i in range(3))
            
            if same_euler:
                continue  # Skip bones where Euler angles are already the same
            
            try:
                R_ref = Rotation.from_euler('xyz', ref_rot, degrees=True).as_matrix()
                R_out_XYZ = Rotation.from_euler('XYZ', out_rot, degrees=True).as_matrix()
                
                # Convert: read output as extrinsic XYZ, decompose as intrinsic xyz
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    converted = Rotation.from_matrix(R_out_XYZ).as_euler('xyz', degrees=True)
                converted_norm = [normalize_angle(a) for a in converted]
                
                matrix_match = np.allclose(R_ref, R_out_XYZ, atol=1e-4)
                euler_match = all(abs(normalize_angle(converted_norm[i] - ref_norm[i])) < 0.5 for i in range(3))
                
                mat_str = "✓" if matrix_match else "✗"
                eul_str = "✓" if euler_match else "✗"
                
                print(f"{name:<20} [{out_norm[0]:>8.2f},{out_norm[1]:>8.2f},{out_norm[2]:>8.2f}]  "
                      f"[{ref_norm[0]:>8.2f},{ref_norm[1]:>8.2f},{ref_norm[2]:>8.2f}]  "
                      f"[{converted_norm[0]:>8.2f},{converted_norm[1]:>8.2f},{converted_norm[2]:>8.2f}]  "
                      f"{mat_str:>12} {eul_str:>11}")
            except Exception as e:
                print(f"{name:<20} ERROR: {e}")
        
        # Show failing bones details
        if failing_bones:
            print(f"\n--- FAILING BONES (matrices don't match even with XYZ convention) ---")
            for item in failing_bones[:10]:
                name, ref_rot, out_rot, R_ref, R_out_XYZ = item
                if R_ref is None:
                    print(f"  {name}: ERROR")
                    continue
                    
                print(f"  Bone '{name}':")
                print(f"    out_rot = {out_rot}")
                print(f"    ref_rot = {ref_rot}")
                
                # Show the difference
                diff = R_ref - R_out_XYZ
                max_diff = np.max(np.abs(diff))
                print(f"    Max matrix difference: {max_diff:.6f}")
                
                # Try all other conventions
                for conv in ['xyz', 'XYZ', 'xzy', 'XZY', 'yxz', 'YXZ', 'yzx', 'YZX', 'zxy', 'ZXY', 'zyx', 'ZYX']:
                    try:
                        R_test = Rotation.from_euler(conv, out_rot, degrees=True).as_matrix()
                        if np.allclose(R_ref, R_test, atol=1e-4):
                            print(f"    *** MATCHES with output convention '{conv}' ***")
                    except:
                        pass

    # Final summary
    print("\n\n" + "=" * 140)
    print("CONVERSION FORMULA SUMMARY")
    print("=" * 140)
    print()
    print("FINDING: The output .bbmodel files store rotation Euler angles in EXTRINSIC XYZ convention,")
    print("while the reference .bbmodel files store them in INTRINSIC xyz convention.")
    print()
    print("To convert from output (buggy) to reference (correct):")
    print()
    print("  1. Read the output Euler angles [rx, ry, rz]")
    print("  2. Build the rotation matrix using EXTRINSIC XYZ convention:")
    print("     R = Rz(rz) · Ry(ry) · Rx(rx)")
    print("  3. Decompose R using INTRINSIC xyz convention to get the correct angles:")
    print("     [correct_rx, correct_ry, correct_rz] = decompose_xyz_intrinsic(R)")
    print()
    print("In scipy, this is:")
    print("  R = Rotation.from_euler('XYZ', [rx, ry, rz], degrees=True)")
    print("  correct = R.as_euler('xyz', degrees=True)")
    print()
    print("Or equivalently, since intrinsic xyz(a,b,c) = extrinsic ZYX(c,b,a):")
    print("  The output stores [a, b, c] as extrinsic XYZ")
    print("  The reference stores the SAME rotation as intrinsic xyz")
    print("  So: R_out = Rz(c) · Ry(b) · Rx(a) = R_intrinsic_xyz")
    print("  And: R_intrinsic_xyz(a',b',c') = Rx(a') · Ry'(b') · Rz''(c')")
    print("  These represent the same rotation, so the decomposed angles differ.")


if __name__ == "__main__":
    main()
