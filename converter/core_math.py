#!/usr/bin/env python3
"""
CoreMath - Coordinate System Transformation Library
====================================================

Converts coordinates/rotations/sizes from Minecraft 1.12.2 (right-hand, Z into screen)
to Minecraft 1.20.1 / GeckoLib (left-hand, Z out of screen).

Coordinate system transformation:
  - 1.12.2: Right-hand coordinate system (X right, Y up, Z into screen)
  - 1.20.1: Left-hand coordinate system (X right, Y up, Z out of screen)

The transformation matrix M = diag(1, 1, -1) converts from RH to LH.
"""

import math
import warnings
import numpy as np

# ============================================================================
# Coordinate System Basis Vector Transformation Matrix
# ============================================================================
# M = diag(1, 1, -1)
# This matrix converts a point from right-hand to left-hand coordinate system
# by negating the Z component while keeping X and Y unchanged.
#
# Derivation:
#   In a right-hand system, the basis vectors are:
#     e_x = (1, 0, 0), e_y = (0, 1, 0), e_z = (0, 0, 1) with Z into screen
#   In a left-hand system, the basis vectors are:
#     e_x' = (1, 0, 0), e_y' = (0, 1, 0), e_z' = (0, 0, -1) with Z out of screen
#   The transformation M maps e_x -> e_x', e_y -> e_y', e_z -> -e_z'
#   Hence M = diag(1, 1, -1)

M = np.diag([1.0, 1.0, -1.0])
M_INV = np.diag([1.0, 1.0, -1.0])  # M is its own inverse: M^-1 = M


def convert_pos(x: float, y: float, z: float) -> tuple:
    """
    Convert a position vector from 1.12.2 (RH) to 1.20.1 (LH).

    New position = (x, y, -z)

    Derivation:
        Let P be a point in the right-hand system with coordinates (x, y, z).
        The position vector P_RH = x*e_x + y*e_y + z*e_z.
        In the left-hand system, the same physical point has coordinates (x, y, -z)
        because the Z basis vector is flipped:
        P_LH = x*e_x' + y*e_y' + (-z)*e_z'
        Therefore: P_LH = M * P_RH = (x, y, -z)

    LaTeX:
        \\mathbf{p}_{LH} = M \\cdot \\mathbf{p}_{RH} = \\begin{pmatrix} 1 & 0 & 0 \\\\ 0 & 1 & 0 \\\\ 0 & 0 & -1 \\end{pmatrix} \\begin{pmatrix} x \\\\ y \\\\ z \\end{pmatrix} = \\begin{pmatrix} x \\\\ y \\\\ -z \\end{pmatrix}

    Numerical example:
        convert_pos(1.0, 2.0, 3.0) = (1.0, 2.0, -3.0)
    """
    return (x, y, -z)


def convert_rot(rx: float, ry: float, rz: float, is_degrees: bool = False) -> tuple:
    """
    Convert rotation angles from 1.12.2 (RH) to 1.20.1 (LH).

    New rotation = (-rx, ry, -rz) when only single-axis rotation is present.

    Derivation (via rotation matrix similarity transform):
        Let R be a rotation matrix in the right-hand system.
        The equivalent rotation in the left-hand system is:
            R' = M * R * M^{-1}

        Since M = diag(1, 1, -1) and M^{-1} = diag(1, 1, -1):

        For rotation about X-axis by angle θ:
            R_x(θ) = [[1, 0, 0], [0, cos θ, -sin θ], [0, sin θ, cos θ]]
            R_x'(θ) = M * R_x(θ) * M = [[1, 0, 0], [0, cos θ, sin θ], [0, -sin θ, cos θ]]
                     = R_x(-θ)
            ⟹ X rotation angle negated: -rx

        For rotation about Y-axis by angle φ:
            R_y(φ) = [[cos φ, 0, sin φ], [0, 1, 0], [-sin φ, 0, cos φ]]
            R_y'(φ) = M * R_y(φ) * M = [[cos φ, 0, -sin φ], [0, 1, 0], [sin φ, 0, cos φ]]
                     = R_y(φ)  (unchanged!)
            ⟹ Y rotation angle unchanged: ry

        For rotation about Z-axis by angle ψ:
            R_z(ψ) = [[cos ψ, -sin ψ, 0], [sin ψ, cos ψ, 0], [0, 0, 1]]
            R_z'(ψ) = M * R_z(ψ) * M = [[cos ψ, sin ψ, 0], [-sin ψ, cos ψ, 0], [0, 0, 1]]
                     = R_z(-ψ)
            ⟹ Z rotation angle negated: -rz

    LaTeX:
        R' = M \\cdot R \\cdot M^{-1} \\implies (\\theta_x', \\theta_y', \\theta_z') = (-\\theta_x, \\theta_y, -\\theta_z)

    Numerical example:
        convert_rot(0.5, 0.3, 0.1) = (-0.5, 0.3, -0.1)

    WARNING: If more than one rotation component is non-zero, the simple angle
    negation may not be accurate due to rotation order differences. In that case,
    use convert_rotation_order() instead.
    """
    # Check for multi-axis rotation
    non_zero_count = sum(1 for a in [rx, ry, rz] if abs(a) > 1e-10)
    if non_zero_count > 1:
        warnings.warn(
            f"Multi-axis rotation detected: ({rx}, {ry}, {rz}). "
            f"Simple angle negation may be inaccurate due to rotation order differences. "
            f"Consider using convert_rotation_order() for accurate conversion.",
            stacklevel=2
        )

    if is_degrees:
        return (-rx, ry, -rz)
    else:
        return (-rx, ry, -rz)


def convert_size(w: float, h: float, d: float) -> tuple:
    """
    Convert box dimensions from 1.12.2 (RH) to 1.20.1 (LH).

    Returns (w, h, d) - depth is PRESERVED, not negated.

    Mathematical proof via interval mapping:
        In 1.12.2 (RH), a box with origin (bx, by, bz) and size (w, h, d)
        occupies the Z interval [bz, bz - d] (depth extends in -Z direction).

        After coordinate system conversion (Z -> -Z), the Z coordinates become:
          -bz -> -bz  (was bz)
          -(bz - d) = -bz + d  (was bz - d)

        So the new Z interval is [-bz, -bz + d].
        This interval extends from -bz in the +Z direction with length d.

        Therefore, the depth d is preserved:
          New depth = (-bz + d) - (-bz) = d

        The box in the new system has origin (-bx, by, -bz) and size (w, h, d).

    LaTeX:
        \\text{1.12.2 Z-interval: } [z_0, z_0 - d]
        \\text{After } z \\to -z: [-z_0, -(z_0 - d)] = [-z_0, -z_0 + d]
        \\text{New depth} = (-z_0 + d) - (-z_0) = d

    Numerical example:
        convert_size(4, 8, 6) = (4, 8, 6)
        (Depth 6 stays 6, not -6)
    """
    # Ensure depth is non-negative
    if d < 0:
        warnings.warn(
            f"Negative depth d={d} passed to convert_size. "
            f"This should be handled by the ModelConverter by adjusting the origin.",
            stacklevel=2
        )
        d = abs(d)
    return (w, h, d)


def _rx(angle):
    """Rotation matrix about X-axis."""
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def _ry(angle):
    """Rotation matrix about Y-axis."""
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _rz(angle):
    """Rotation matrix about Z-axis."""
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def convert_rotation_order(rx: float, ry: float, rz: float) -> tuple:
    """
    Convert rotation from 1.12.2 X→Y→Z order to GeckoLib Z→Y→X order,
    then apply coordinate system transformation.

    In 1.12.2, rotations are applied in the order: X → Y → Z (intrinsic/local axes).
    In GeckoLib 1.20.1, rotations are applied in the order: Z → Y → X.

    Algorithm (based on Graphics Gems IV matrix-to-Euler decomposition):
        1. Construct the 1.12.2 rotation matrix R = R_z(rz) * R_y(ry) * R_x(rx)
           (This is the extrinsic equivalent of intrinsic X→Y→Z)
        2. Apply coordinate system transform: R' = M * R * M^{-1}
        3. Decompose R' into Z→Y→X Euler angles (GeckoLib order):
           R' = R_x(α) * R_y(β) * R_z(γ)
        4. Return (α, β, γ)

    The decomposition follows the standard algorithm from Graphics Gems IV:
        Given R = [[r00, r01, r02], [r10, r11, r12], [r20, r21, r22]]
        For Z→Y→X order (R = Rx * Ry * Rz):
          If r20 ≠ ±1:
            β = asin(-r20)
            α = atan2(r10, r00)
            γ = atan2(r21, r22)
          Else (gimbal lock):
            α = 0
            γ = atan2(r01, r02)
            β = -r20 * π/2

    LaTeX:
        R_{1.12.2} = R_z(\\psi) \\cdot R_y(\\varphi) \\cdot R_x(\\theta)
        R' = M \\cdot R_{1.12.2} \\cdot M^{-1}
        R' = R_x(\\alpha) \\cdot R_y(\\beta) \\cdot R_z(\\gamma)

    Numerical example:
        For rx=0.5, ry=0.3, rz=0.1 (radians):
        R_1122 = Rz(0.1) * Ry(0.3) * Rx(0.5)
        R' = M * R_1122 * M
        Decompose R' into ZYX -> (alpha, beta, gamma)

    Returns:
        Tuple of (rx_new, ry_new, rz_new) in radians for GeckoLib Z→Y→X order
    """
    # Step 1: Construct 1.12.2 rotation matrix (extrinsic X→Y→Z = intrinsic Z→Y→X)
    # Actually, Minecraft 1.12.2 applies rotations as:
    # rotateAngleX first, then rotateAngleY, then rotateAngleZ
    # In matrix form, this is: R = Rz(rz) * Ry(ry) * Rx(rx) (column-vector convention)
    R_1122 = _rz(rz) @ _ry(ry) @ _rx(rx)

    # Step 2: Apply coordinate system transform
    R_prime = M @ R_1122 @ M_INV

    # Step 3: Decompose R' into Euler angles using the same convention
    # Both 1.12.2 and GeckoLib use the same rotation application order:
    #   OpenGL calls: rotateZ, rotateY, rotateX → R = Rx * Ry * Rz
    #   This is intrinsic X→Y→Z = extrinsic Z→Y→X
    #
    # For R = Rx(α) * Ry(β) * Rz(γ), the matrix entries are:
    #   R[0,0] = cos(β)*cos(γ)       R[0,1] = -cos(β)*sin(γ)      R[0,2] = sin(β)
    #   R[1,0] = sin(α)*sin(β)*cos(γ) + cos(α)*sin(γ)
    #   R[1,1] = -sin(α)*sin(β)*sin(γ) + cos(α)*cos(γ)
    #   R[1,2] = -sin(α)*cos(β)
    #   R[2,0] = -cos(α)*sin(β)*cos(γ) + sin(α)*sin(γ)
    #   R[2,1] = cos(α)*sin(β)*sin(γ) + sin(α)*cos(γ)
    #   R[2,2] = cos(α)*cos(β)
    #
    # Decomposition formulas (Graphics Gems IV):
    #   β = asin(R[0,2])
    #   α = atan2(-R[1,2], R[2,2])
    #   γ = atan2(-R[0,1], R[0,0])

    r02 = R_prime[0, 2]

    # Clamp to handle floating point errors
    r02 = max(-1.0, min(1.0, r02))

    if abs(r02) < 1.0 - 1e-10:
        # No gimbal lock
        beta = math.asin(r02)  # Y rotation
        alpha = math.atan2(-R_prime[1, 2], R_prime[2, 2])  # X rotation
        gamma = math.atan2(-R_prime[0, 1], R_prime[0, 0])  # Z rotation
    else:
        # Gimbal lock (β = ±90°)
        alpha = 0.0
        sign = 1.0 if r02 > 0 else -1.0
        beta = sign * math.pi / 2
        gamma = math.atan2(R_prime[1, 0], R_prime[1, 1])

    return (alpha, beta, gamma)


def rad_to_deg(rad: float) -> float:
    """Convert radians to degrees."""
    return rad * 180.0 / math.pi


def deg_to_rad(deg: float) -> float:
    """Convert degrees to radians."""
    return deg * math.pi / 180.0


# ============================================================================
# Self-test / verification
# ============================================================================
if __name__ == "__main__":
    print("=== CoreMath Verification ===\n")

    # Test 1: Position conversion
    print("--- Test 1: Position Conversion ---")
    result = convert_pos(1.0, 2.0, 3.0)
    expected = (1.0, 2.0, -3.0)
    print(f"convert_pos(1, 2, 3) = {result}, expected = {expected}")
    assert result == expected, "Position conversion failed!"
    print("PASS\n")

    # Test 2: Size conversion (depth preserved)
    print("--- Test 2: Size Conversion ---")
    result = convert_size(4, 8, 6)
    expected = (4, 8, 6)
    print(f"convert_size(4, 8, 6) = {result}, expected = {expected}")
    assert result == expected, "Size conversion failed!"
    print("PASS\n")

    # Test 3: Single-axis rotation
    print("--- Test 3: Single-axis Rotation ---")
    result = convert_rot(0.5, 0.0, 0.0)
    expected = (-0.5, 0.0, 0.0)
    print(f"convert_rot(0.5, 0, 0) = {result}, expected = {expected}")
    assert abs(result[0] - expected[0]) < 1e-10, "X rotation conversion failed!"
    result = convert_rot(0.0, 0.3, 0.0)
    expected = (0.0, 0.3, 0.0)
    print(f"convert_rot(0, 0.3, 0) = {result}, expected = {expected}")
    assert abs(result[1] - expected[1]) < 1e-10, "Y rotation conversion failed!"
    result = convert_rot(0.0, 0.0, 0.1)
    expected = (0.0, 0.0, -0.1)
    print(f"convert_rot(0, 0, 0.1) = {result}, expected = {expected}")
    assert abs(result[2] - expected[2]) < 1e-10, "Z rotation conversion failed!"
    print("PASS\n")

    # Test 4: Rotation order conversion
    print("--- Test 4: Rotation Order Conversion ---")
    # Single-axis: should match simple conversion
    alpha, beta, gamma = convert_rotation_order(0.5, 0.0, 0.0)
    print(f"convert_rotation_order(0.5, 0, 0) = ({alpha:.6f}, {beta:.6f}, {gamma:.6f})")
    print(f"Expected X: {-0.5:.6f}")
    assert abs(alpha - (-0.5)) < 1e-6, "Rotation order X failed!"

    # Multi-axis
    alpha, beta, gamma = convert_rotation_order(0.3, 0.5, 0.7)
    print(f"convert_rotation_order(0.3, 0.5, 0.7) = ({alpha:.6f}, {beta:.6f}, {gamma:.6f})")

    # Verify by reconstructing the matrix
    R_check = _rx(alpha) @ _ry(beta) @ _rz(gamma)
    R_original = M @ (_rz(0.7) @ _ry(0.5) @ _rx(0.3)) @ M_INV
    max_diff = np.max(np.abs(R_check - R_original))
    print(f"Max matrix difference: {max_diff:.2e}")
    assert max_diff < 1e-10, "Rotation order conversion verification failed!"
    print("PASS\n")

    # Test 5: Multi-axis rotation where simple negation differs
    print("--- Test 5: Multi-axis vs Simple ---")
    rx, ry, rz = 0.3, 0.5, 0.7
    simple = convert_rot(rx, ry, rz)
    ordered = convert_rotation_order(rx, ry, rz)
    print(f"Simple negation: ({simple[0]:.6f}, {simple[1]:.6f}, {simple[2]:.6f})")
    print(f"Matrix reorder:  ({ordered[0]:.6f}, {ordered[1]:.6f}, {ordered[2]:.6f})")
    print(f"Difference shows why rotation order matters for multi-axis rotations")
    print()

    print("=== All CoreMath Tests Passed ===")
