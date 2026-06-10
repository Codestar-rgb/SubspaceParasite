#!/usr/bin/env python3
"""
Compare rotation values between reference and output .bbmodel files.
Extract bone rotations from the outliner hierarchy, compare bone-by-bone,
and test various hypotheses for the conversion formula.
"""

import json
import numpy as np
from scipy.spatial.transform import Rotation


def extract_bones_from_outliner(node, parent_path=""):
    """Recursively extract bone names and their rotation values from the outliner."""
    bones = {}
    path = f"{parent_path}/{node.get('name', '?')}" if parent_path else node.get('name', 'root')
    
    # Only process nodes that are actual bones (dict with 'name'), not element UUIDs (strings)
    if isinstance(node, dict) and 'name' in node:
        rot = node.get('rotation', [0.0, 0.0, 0.0])
        origin = node.get('origin', [0.0, 0.0, 0.0])
        bones[path] = {
            'name': node['name'],
            'rotation': list(rot),
            'origin': list(origin),
        }
        
        # Process children
        for child in node.get('children', []):
            if isinstance(child, dict):
                child_bones = extract_bones_from_outliner(child, path)
                bones.update(child_bones)
            # String children are element UUID references, skip them
    
    return bones


def load_bones(filepath):
    """Load a .bbmodel file and extract all bones from its outliner."""
    with open(filepath) as f:
        data = json.load(f)
    
    all_bones = {}
    for node in data.get('outliner', []):
        bones = extract_bones_from_outliner(node)
        all_bones.update(bones)
    
    return all_bones


def rotation_matrix_from_euler_xyz_deg(rx, ry, rz):
    """Build rotation matrix from XYZ Euler angles (degrees)."""
    return Rotation.from_euler('XYZ', [rx, ry, rz], degrees=True).as_matrix()


def euler_xyz_deg_from_rotation_matrix(R):
    """Extract XYZ Euler angles (degrees) from a rotation matrix."""
    return Rotation.from_matrix(R).as_euler('XYZ', degrees=True)


def angles_close(a, b, tol=0.01):
    """Check if two angle lists are close (handling -0.0 vs 0.0)."""
    return all(abs(x - y) < tol for x, y in zip(a, b))


def apply_sign_flip(rotation, signs):
    """Apply sign flip to Euler angles. signs = [sx, sy, sz] where each is +1 or -1."""
    return [rotation[0] * signs[0], rotation[1] * signs[1], rotation[2] * signs[2]]


def apply_matrix_transform(rotation_out, D):
    """
    Apply diagonal similarity transform: D * R_out * D
    where D = diag(d1, d2, d3) and R_out is the rotation matrix of the output.
    Then decompose back to Euler angles.
    """
    R_out = rotation_matrix_from_euler_xyz_deg(*rotation_out)
    D_mat = np.diag(D)
    R_transformed = D_mat @ R_out @ D_mat
    return list(euler_xyz_deg_from_rotation_matrix(R_transformed))


def test_hypothesis_on_pair(ref_rot, out_rot, hyp_name, hyp_func):
    """Test a hypothesis function on a single ref/output pair. Returns (matches, transformed)."""
    transformed = hyp_func(out_rot)
    # Need to handle angle wrapping - normalize both to [-180, 180]
    transformed_norm = [(a + 180) % 360 - 180 for a in transformed]
    ref_norm = [(a + 180) % 360 - 180 for a in ref_rot]
    matches = angles_close(transformed_norm, ref_norm, tol=0.5)
    return matches, transformed_norm


def normalize_angle(a):
    """Normalize angle to [-180, 180]."""
    return (a + 180) % 360 - 180


def main():
    # File paths
    ref_kirin = "/home/z/my-project/upload/kirin_debug (1).bbmodel"
    ref_heblu = "/home/z/my-project/upload/heblu_debug.bbmodel"
    out_kirin = "/home/z/my-project/converter/output/kirin_debug.bbmodel"
    out_heblu = "/home/z/my-project/converter/output/heblu_debug.bbmodel"
    
    # Load all bones
    print("=" * 120)
    print("LOADING BONES FROM OUTLINER")
    print("=" * 120)
    
    ref_kirin_bones = load_bones(ref_kirin)
    ref_heblu_bones = load_bones(ref_heblu)
    out_kirin_bones = load_bones(out_kirin)
    out_heblu_bones = load_bones(out_heblu)
    
    print(f"Kirin reference bones: {len(ref_kirin_bones)}")
    print(f"Kirin output bones:    {len(out_kirin_bones)}")
    print(f"Heblu reference bones: {len(ref_heblu_bones)}")
    print(f"Heblu output bones:    {len(out_heblu_bones)}")
    
    # Define hypotheses
    hypotheses = {
        "H0: identity (no transform)": lambda r: r,
        "H1: [-rx, -ry, rz]": lambda r: apply_sign_flip(r, [-1, -1, 1]),
        "H2: [rx, -ry, -rz]": lambda r: apply_sign_flip(r, [1, -1, -1]),
        "H3: [-rx, ry, -rz]": lambda r: apply_sign_flip(r, [-1, 1, -1]),
        "H4: [-rx, -ry, -rz]": lambda r: apply_sign_flip(r, [-1, -1, -1]),
        "H5: [-rx, ry, rz]": lambda r: apply_sign_flip(r, [-1, 1, 1]),
        "H6: [rx, -ry, rz]": lambda r: apply_sign_flip(r, [1, -1, 1]),
        "H7: [rx, ry, -rz]": lambda r: apply_sign_flip(r, [1, 1, -1]),
        "M1: D*M*D D=diag(-1,-1,1)": lambda r: apply_matrix_transform(r, [-1, -1, 1]),
        "M2: D*M*D D=diag(1,-1,-1)": lambda r: apply_matrix_transform(r, [1, -1, -1]),
        "M3: D*M*D D=diag(-1,1,-1)": lambda r: apply_matrix_transform(r, [-1, 1, -1]),
        "M4: D*M*D D=diag(-1,-1,-1)": lambda r: apply_matrix_transform(r, [-1, -1, -1]),
        "M5: D*M*D D=diag(-1,1,1)": lambda r: apply_matrix_transform(r, [-1, 1, 1]),
        "M6: D*M*D D=diag(1,-1,1)": lambda r: apply_matrix_transform(r, [1, -1, 1]),
        "M7: D*M*D D=diag(1,1,-1)": lambda r: apply_matrix_transform(r, [1, 1, -1]),
        "M8: D*M*D^-1 D=diag(-1,-1,1)": lambda r: apply_matrix_transform_inv(r, [-1, -1, 1]),
        "M9: D*M*D^-1 D=diag(1,-1,-1)": lambda r: apply_matrix_transform_inv(r, [1, -1, -1]),
        "M10: D*M*D^-1 D=diag(-1,1,-1)": lambda r: apply_matrix_transform_inv(r, [-1, 1, -1]),
    }
    
    # Process each model pair
    for model_name, ref_bones, out_bones in [
        ("KIRIN", ref_kirin_bones, out_kirin_bones),
        ("HEBLU", ref_heblu_bones, out_heblu_bones),
    ]:
        print("\n")
        print("=" * 120)
        print(f"  MODEL: {model_name}")
        print("=" * 120)
        
        # Match bones by name (strip path, use just the bone name)
        # We'll match by the last part of the path (the bone name itself)
        ref_by_name = {}
        for path, data in ref_bones.items():
            name = data['name']
            ref_by_name[name] = (path, data)
        
        out_by_name = {}
        for path, data in out_bones.items():
            name = data['name']
            out_by_name[name] = (path, data)
        
        common_names = sorted(set(ref_by_name.keys()) & set(out_by_name.keys()))
        only_ref = set(ref_by_name.keys()) - set(out_by_name.keys())
        only_out = set(out_by_name.keys()) - set(ref_by_name.keys())
        
        print(f"\nBones in common: {len(common_names)}")
        if only_ref:
            print(f"Bones only in reference: {only_ref}")
        if only_out:
            print(f"Bones only in output: {only_out}")
        
        # Find bones with different rotations
        diff_bones = []
        same_bones = []
        for name in common_names:
            ref_rot = ref_by_name[name][1]['rotation']
            out_rot = out_by_name[name][1]['rotation']
            ref_norm = [normalize_angle(a) for a in ref_rot]
            out_norm = [normalize_angle(a) for a in out_rot]
            
            if not angles_close(ref_norm, out_norm, tol=0.01):
                diff_bones.append((name, ref_rot, out_rot))
            else:
                same_bones.append(name)
        
        print(f"\nBones with SAME rotation: {len(same_bones)}")
        print(f"Bones with DIFFERENT rotation: {len(diff_bones)}")
        
        # Print ALL bones with their rotations
        print(f"\n{'Bone Name':<30} {'Output Rotation':<30} {'Reference Rotation':<30} {'Same?':<8}")
        print("-" * 100)
        for name in common_names:
            ref_rot = ref_by_name[name][1]['rotation']
            out_rot = out_by_name[name][1]['rotation']
            ref_norm = [normalize_angle(a) for a in ref_rot]
            out_norm = [normalize_angle(a) for a in out_rot]
            is_same = angles_close(ref_norm, out_norm, tol=0.01)
            print(f"{name:<30} [{out_rot[0]:>8.2f}, {out_rot[1]:>8.2f}, {out_rot[2]:>8.2f}]  "
                  f"[{ref_rot[0]:>8.2f}, {ref_rot[1]:>8.2f}, {ref_rot[2]:>8.2f}]  "
                  f"{'SAME' if is_same else 'DIFF':<8}")
        
        # Now test hypotheses on bones with different rotations
        print(f"\n{'='*120}")
        print("HYPOTHESIS TESTING ON BONES WITH DIFFERENT ROTATIONS")
        print(f"{'='*120}")
        
        # Track hypothesis match counts
        hyp_match_counts = {h: 0 for h in hypotheses}
        hyp_total = len(diff_bones)
        
        for name, ref_rot, out_rot in diff_bones:
            print(f"\n--- Bone: {name} ---")
            print(f"  Output:    [{out_rot[0]:>10.4f}, {out_rot[1]:>10.4f}, {out_rot[2]:>10.4f}]")
            print(f"  Reference: [{ref_rot[0]:>10.4f}, {ref_rot[1]:>10.4f}, {ref_rot[2]:>10.4f}]")
            
            # Compute the difference
            diff = [normalize_angle(ref_rot[i] - out_rot[i]) for i in range(3)]
            print(f"  Diff(ref-out): [{diff[0]:>10.4f}, {diff[1]:>10.4f}, {diff[2]:>10.4f}]")
            
            matching_hyps = []
            for hyp_name, hyp_func in hypotheses.items():
                try:
                    matches, transformed = test_hypothesis_on_pair(ref_rot, out_rot, hyp_name, hyp_func)
                    if matches:
                        hyp_match_counts[hyp_name] += 1
                        matching_hyps.append(hyp_name)
                except Exception as e:
                    pass
            
            if matching_hyps:
                print(f"  MATCHING HYPOTHESES: {matching_hyps}")
            else:
                print(f"  NO MATCHING HYPOTHESES")
        
        # Summary of hypothesis matches
        print(f"\n{'='*120}")
        print("HYPOTHESIS MATCH SUMMARY")
        print(f"{'='*120}")
        print(f"Total bones with different rotations: {hyp_total}")
        for hyp_name, count in sorted(hyp_match_counts.items(), key=lambda x: -x[1]):
            print(f"  {hyp_name:<45} : {count}/{hyp_total} bones match ({100*count/max(hyp_total,1):.1f}%)")
    
    # Now let's do a deep analysis for bones that DON'T match simple hypotheses
    print("\n\n" + "=" * 120)
    print("DEEP ANALYSIS: Looking for pattern in non-matching bones")
    print("=" * 120)
    
    for model_name, ref_bones, out_bones in [
        ("KIRIN", ref_kirin_bones, out_kirin_bones),
        ("HEBLU", ref_heblu_bones, out_heblu_bones),
    ]:
        ref_by_name = {}
        for path, data in ref_bones.items():
            name = data['name']
            ref_by_name[name] = (path, data)
        
        out_by_name = {}
        for path, data in out_bones.items():
            name = data['name']
            out_by_name[name] = (path, data)
        
        common_names = sorted(set(ref_by_name.keys()) & set(out_by_name.keys()))
        
        # Check if the rotation matrix of output, when transformed, equals ref rotation matrix
        print(f"\n--- {model_name}: Matrix-level comparison ---")
        print(f"{'Bone':<25} {'ref_rot':>35} {'out_rot':>35} {'R_ref ≈ D*R_out*D?':>20}")
        print("-" * 120)
        
        for name in common_names:
            ref_rot = ref_by_name[name][1]['rotation']
            out_rot = out_by_name[name][1]['rotation']
            ref_norm = [normalize_angle(a) for a in ref_rot]
            out_norm = [normalize_angle(a) for a in out_rot]
            
            if angles_close(ref_norm, out_norm, tol=0.01):
                continue
            
            R_ref = rotation_matrix_from_euler_xyz_deg(*ref_rot)
            R_out = rotation_matrix_from_euler_xyz_deg(*out_rot)
            
            # Test all D*M*D transforms
            best_match = None
            best_D = None
            for D in [
                [-1, -1, 1], [1, -1, -1], [-1, 1, -1],
                [-1, 1, 1], [1, -1, 1], [1, 1, -1],
                [-1, -1, -1], [1, 1, 1]
            ]:
                D_mat = np.diag(D)
                R_transformed = D_mat @ R_out @ D_mat
                if np.allclose(R_transformed, R_ref, atol=1e-6):
                    best_match = f"D*M*D D={D}"
                    best_D = D
                    break
            
            if best_match is None:
                # Try D*M*D^-1 transforms
                for D in [
                    [-1, -1, 1], [1, -1, -1], [-1, 1, -1],
                    [-1, 1, 1], [1, -1, 1], [1, 1, -1],
                    [-1, -1, -1], [1, 1, 1]
                ]:
                    D_mat = np.diag(D)
                    D_inv = np.linalg.inv(D_mat)
                    R_transformed = D_mat @ R_out @ D_inv
                    if np.allclose(R_transformed, R_ref, atol=1e-6):
                        best_match = f"D*M*D^-1 D={D}"
                        best_D = D
                        break
            
            if best_match is None:
                # Try M*D
                for D in [
                    [-1, -1, 1], [1, -1, -1], [-1, 1, -1],
                    [-1, 1, 1], [1, -1, 1], [1, 1, -1],
                    [-1, -1, -1], [1, 1, 1]
                ]:
                    D_mat = np.diag(D)
                    R_transformed = R_out @ D_mat
                    if np.allclose(R_transformed, R_ref, atol=1e-6):
                        best_match = f"M*D D={D}"
                        break
            
            if best_match is None:
                # Try D*M
                for D in [
                    [-1, -1, 1], [1, -1, -1], [-1, 1, -1],
                    [-1, 1, 1], [1, -1, 1], [1, 1, -1],
                    [-1, -1, -1], [1, 1, 1]
                ]:
                    D_mat = np.diag(D)
                    R_transformed = D_mat @ R_out
                    if np.allclose(R_transformed, R_ref, atol=1e-6):
                        best_match = f"D*M D={D}"
                        break
            
            if best_match is None:
                best_match = "NONE FOUND"
            
            print(f"{name:<25} [{ref_rot[0]:>8.2f},{ref_rot[1]:>8.2f},{ref_rot[2]:>8.2f}]  "
                  f"[{out_rot[0]:>8.2f},{out_rot[1]:>8.2f},{out_rot[2]:>8.2f}]  "
                  f"{best_match:>20}")
    
    # Final analysis: for each pair, show the actual rotation matrices to find the pattern
    print("\n\n" + "=" * 120)
    print("RAW ROTATION MATRIX COMPARISON (first 5 differing bones per model)")
    print("=" * 120)
    
    for model_name, ref_bones, out_bones in [
        ("KIRIN", ref_kirin_bones, out_kirin_bones),
        ("HEBLU", ref_heblu_bones, out_heblu_bones),
    ]:
        ref_by_name = {}
        for path, data in ref_bones.items():
            name = data['name']
            ref_by_name[name] = (path, data)
        
        out_by_name = {}
        for path, data in out_bones.items():
            name = data['name']
            out_by_name[name] = (path, data)
        
        common_names = sorted(set(ref_by_name.keys()) & set(out_by_name.keys()))
        
        count = 0
        for name in common_names:
            ref_rot = ref_by_name[name][1]['rotation']
            out_rot = out_by_name[name][1]['rotation']
            ref_norm = [normalize_angle(a) for a in ref_rot]
            out_norm = [normalize_angle(a) for a in out_rot]
            
            if angles_close(ref_norm, out_norm, tol=0.01):
                continue
            
            count += 1
            if count > 5:
                break
            
            print(f"\n--- {model_name} bone: {name} ---")
            print(f"  Output Euler:    [{out_rot[0]:.4f}, {out_rot[1]:.4f}, {out_rot[2]:.4f}]")
            print(f"  Reference Euler: [{ref_rot[0]:.4f}, {ref_rot[1]:.4f}, {ref_rot[2]:.4f}]")
            
            R_out = rotation_matrix_from_euler_xyz_deg(*out_rot)
            R_ref = rotation_matrix_from_euler_xyz_deg(*ref_rot)
            
            print(f"  R_out matrix:")
            for row in R_out:
                print(f"    [{row[0]:>10.6f}, {row[1]:>10.6f}, {row[2]:>10.6f}]")
            print(f"  R_ref matrix:")
            for row in R_ref:
                print(f"    [{row[0]:>10.6f}, {row[1]:>10.6f}, {row[2]:>10.6f}]")
            
            # Show the relationship
            print(f"  R_ref * R_out^T (should be identity if same):")
            rel = R_ref @ R_out.T
            for row in rel:
                print(f"    [{row[0]:>10.6f}, {row[1]:>10.6f}, {row[2]:>10.6f}]")
            
            # Check: is R_ref = flip_x * R_out * flip_x where flip_x = diag(-1,1,1)?
            # Actually let's check various flips
            for D in [[-1,1,1], [1,-1,1], [1,1,-1], [-1,-1,1], [-1,1,-1], [1,-1,-1], [-1,-1,-1]]:
                D_mat = np.diag([float(d) for d in D])
                for transform_name, R_test in [
                    (f"D*R_out*D, D={D}", D_mat @ R_out @ D_mat),
                    (f"D*R_out*D^-1, D={D}", D_mat @ R_out @ np.linalg.inv(D_mat)),
                    (f"D*R_out, D={D}", D_mat @ R_out),
                    (f"R_out*D, D={D}", R_out @ D_mat),
                ]:
                    if np.allclose(R_test, R_ref, atol=1e-6):
                        print(f"  *** EXACT MATRIX MATCH: {transform_name} ***")

    # Let's also check: maybe the conversion is simply negating all angles for non-zero bones
    # Or maybe ref = -out for each axis
    print("\n\n" + "=" * 120)
    print("SIMPLE NUMERICAL RELATIONSHIP ANALYSIS")
    print("=" * 120)
    
    for model_name, ref_bones, out_bones in [
        ("KIRIN", ref_kirin_bones, out_kirin_bones),
        ("HEBLU", ref_heblu_bones, out_heblu_bones),
    ]:
        ref_by_name = {}
        for path, data in ref_bones.items():
            name = data['name']
            ref_by_name[name] = (path, data)
        
        out_by_name = {}
        for path, data in out_bones.items():
            name = data['name']
            out_by_name[name] = (path, data)
        
        common_names = sorted(set(ref_by_name.keys()) & set(out_by_name.keys()))
        
        print(f"\n--- {model_name} ---")
        print(f"{'Bone':<25} {'out_x':>8} {'out_y':>8} {'out_z':>8}  "
              f"{'ref_x':>8} {'ref_y':>8} {'ref_z':>8}  "
              f"{'rx/ox':>8} {'ry/oy':>8} {'rz/oz':>8}  "
              f"{'ref+out_x':>9} {'ref+out_y':>9} {'ref+out_z':>9}")
        print("-" * 140)
        
        for name in common_names:
            ref_rot = ref_by_name[name][1]['rotation']
            out_rot = out_by_name[name][1]['rotation']
            ref_norm = [normalize_angle(a) for a in ref_rot]
            out_norm = [normalize_angle(a) for a in out_rot]
            
            if angles_close(ref_norm, out_norm, tol=0.01):
                continue
            
            # Compute ratios and sums
            ratios = []
            for i in range(3):
                if abs(out_norm[i]) > 0.01:
                    ratios.append(f"{ref_norm[i]/out_norm[i]:>8.3f}")
                else:
                    ratios.append(f"{'N/A':>8}")
            
            sums = [normalize_angle(ref_norm[i] + out_norm[i]) for i in range(3)]
            
            print(f"{name:<25} {out_norm[0]:>8.2f} {out_norm[1]:>8.2f} {out_norm[2]:>8.2f}  "
                  f"{ref_norm[0]:>8.2f} {ref_norm[1]:>8.2f} {ref_norm[2]:>8.2f}  "
                  f"{ratios[0]:>8} {ratios[1]:>8} {ratios[2]:>8}  "
                  f"{sums[0]:>9.2f} {sums[1]:>9.2f} {sums[2]:>9.2f}")


def apply_matrix_transform_inv(rotation_out, D):
    """
    Apply D * R_out * D^-1 transform.
    """
    R_out = rotation_matrix_from_euler_xyz_deg(*rotation_out)
    D_mat = np.diag([float(d) for d in D])
    D_inv = np.linalg.inv(D_mat)
    R_transformed = D_mat @ R_out @ D_inv
    return list(euler_xyz_deg_from_rotation_matrix(R_transformed))


if __name__ == "__main__":
    main()
