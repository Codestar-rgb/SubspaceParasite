#!/usr/bin/env python3
"""
CoreMath - Coordinate System Transformation Library
====================================================

Converts coordinates/rotations/sizes from Minecraft 1.12.2 (right-hand, Z into screen)
to Minecraft 1.20.1 / GeckoLib (left-hand, Z out of screen).

This module provides TWO transformation tiers:

1. **Pure RH→LH transformation** (M = diag(1, 1, -1))
   Converts between right-hand and left-hand coordinate systems where both use Y-up.
   This is the fundamental coordinate system transformation.

   Functions: convert_pos, convert_rot, convert_size, convert_rotation_order

2. **Full model transformation** (M_model = diag(1, -1, -1))
   Converts the complete Minecraft model coordinate system, accounting for both the
   RH→LH flip AND the Y-down→Y-up origin shift between MC 1.12.2 ModelRenderer
   and GeckoLib 1.20.1 geo.json format.

   Functions: convert_model_pos, convert_model_rot, convert_model_rotation_order,
              convert_model_cube_origin, convert_model_cube_size

Coordinate system comparison:
  - MC 1.12.2 ModelRenderer: Right-hand, Y-DOWN (origin at top of entity hitbox, y=0 at top)
  - GeckoLib 1.20.1 geo.json: Left-hand, Y-UP (origin at entity feet, y=0 at feet)

The pure RH→LH matrix M = diag(1, 1, -1) only flips Z.
The full model matrix M_model = diag(1, -1, -1) flips BOTH Y and Z.
"""

import math
import warnings
import numpy as np


# ============================================================================
# Pure RH→LH Transformation Matrix (M = diag(1, 1, -1))
# ============================================================================
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


# ============================================================================
# Full Model Transformation Matrix (M_model = diag(1, -1, -1))
# ============================================================================
# This matrix handles the COMPLETE coordinate conversion for Minecraft models,
# including both the RH→LH Z-flip AND the Y-down→Y-up Y-flip.
#
# Derivation:
#   MC 1.12.2 ModelRenderer uses Y-DOWN:
#     - Origin at the TOP of the entity hitbox
#     - Y increases downward (toward feet)
#     - Z points into the screen (right-hand system)
#     - Basis: e_x = (1,0,0), e_y = (0,1,0)_down, e_z = (0,0,1)_into_screen
#
#   GeckoLib 1.20.1 geo.json uses Y-UP:
#     - Origin at the entity FEET
#     - Y increases upward
#     - Z points out of the screen (left-hand system)
#     - Basis: e_x' = (1,0,0), e_y' = (0,1,0)_up, e_z' = (0,0,-1)_out_of_screen
#
#   The Y axis direction reversal combined with the Z axis direction reversal
#   (RH→LH) gives the transformation matrix:
#     M_model = diag(1, -1, -1)
#
#   Note: M_model is also its own inverse since M_model^2 = I.
#
# LaTeX:
#   M_{model} = \\begin{pmatrix} 1 & 0 & 0 \\\\ 0 & -1 & 0 \\\\ 0 & 0 & -1 \\end{pmatrix}
#   M_{model}^{-1} = M_{model}  \\quad (M_{model}^2 = I)
#
# Decomposition of M_model:
#   M_model = diag(1,-1,-1) = diag(1,-1,1) * diag(1,1,-1) = M_y * M
#   where M_y = diag(1,-1,1) is the Y-negation matrix and M = diag(1,1,-1)
#   is the pure RH→LH matrix. These two operations commute since they are both
#   diagonal matrices.

M_MODEL = np.diag([1.0, -1.0, -1.0])
M_MODEL_INV = np.diag([1.0, -1.0, -1.0])  # M_MODEL is its own inverse


# ============================================================================
# Pure RH→LH Transformation Functions (M = diag(1, 1, -1))
# ============================================================================

def convert_pos(x: float, y: float, z: float) -> tuple:
    """
    Convert a position vector from 1.12.2 (RH) to 1.20.1 (LH).

    Pure RH→LH transformation: New position = (x, y, -z)

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

    Pure RH→LH transformation: New rotation = (-rx, ry, -rz) when only
    single-axis rotation is present.

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

    Pure RH→LH transformation: Returns (w, h, d) - depth is PRESERVED, not negated.

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
    then apply pure RH→LH coordinate system transformation (M = diag(1,1,-1)).

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
          If r02 ≠ ±1:
            β = asin(r02)
            α = atan2(-r12, r22)
            γ = atan2(-r01, r00)
          Else (gimbal lock):
            α = 0
            γ = atan2(r10, r11)
            β = r02 * π/2

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
    # Minecraft 1.12.2 applies rotations as:
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


# ============================================================================
# Full Model Transformation Functions (M_model = diag(1, -1, -1))
# ============================================================================
#
# These functions handle the COMPLETE Minecraft model coordinate conversion,
# accounting for:
#   1. Y-down → Y-up (Y-flip): MC 1.12.2 ModelRenderer uses Y-down with origin
#      at the top of the entity hitbox. GeckoLib 1.20.1 uses Y-up with origin
#      at entity feet.
#   2. RH → LH (Z-flip): MC 1.12.2 is right-hand (Z into screen), GeckoLib
#      1.20.1 is left-hand (Z out of screen).
#
# The combined transformation matrix is M_model = diag(1, -1, -1).
#
# WHY M_model DIFFERS FROM M:
#   The pure RH→LH matrix M = diag(1,1,-1) only handles the handedness change.
#   In MC 1.12.2, the ModelRenderer coordinate system is right-hand with Y
#   pointing DOWN. When we convert to GeckoLib's Y-UP left-hand system, we must
#   also flip Y. This is NOT simply an origin translation — it is a genuine
#   axis direction reversal that affects rotation angles via the similarity
#   transform R' = M_model * R * M_model^{-1}.
#
#   The Y-flip arises because:
#     - In MC 1.12.2 ModelRenderer: setRotationPoint(x, y, z) has y increasing
#       downward (0 at top of hitbox, positive toward feet)
#     - In GeckoLib geo.json: "pivot": [x, y, z] has y increasing upward
#       (0 at feet, positive toward head)
#     - This is a fundamental axis reversal, not just a translation
#
# LaTeX (derivation of M_model):
#   \\text{MC 1.12.2 basis (Y-down, RH): } \\hat{x}, -\\hat{y}, \\hat{z}
#   \\text{GeckoLib basis (Y-up, LH): } \\hat{x}, \\hat{y}, -\\hat{z}
#   \\text{Mapping: } \\hat{x} \\to \\hat{x}, \\hat{y}_{down} \\to -\\hat{y}_{up},
#   \\hat{z} \\to -\\hat{z}
#   M_{model} = \\text{diag}(1, -1, -1)
# ============================================================================


def convert_model_pos(x: float, y: float, z: float) -> tuple:
    """
    Convert a position from MC 1.12.2 ModelRenderer (Y-down, RH) to
    GeckoLib 1.20.1 geo.json (Y-up, LH) using M_model = diag(1, -1, -1).

    Result: (x, -y, -z)

    Derivation:
        In MC 1.12.2 ModelRenderer, the coordinate system is:
          - X: right
          - Y: DOWN (0 at top of hitbox, positive toward feet)
          - Z: into screen (right-hand)

        In GeckoLib 1.20.1, the coordinate system is:
          - X: right
          - Y: UP (0 at feet, positive toward head)
          - Z: out of screen (left-hand)

        Applying M_model = diag(1, -1, -1):
          P_LH = M_model * P_RH = (x, -y, -z)

        Note: The Y-flip handles the axis direction reversal. In a full
        conversion pipeline, an ADDITIONAL translation of +24.0 in Y is
        typically applied to shift the origin from the top of the hitbox
        (y=0 in 1.12.2) to the feet (y=0 in GeckoLib). This translation
        is handled by the ModelConverter, not by this function, because it
        depends on the entity height (24.0 for standard bipeds).

    LaTeX:
        \\mathbf{p}_{GeckoLib} = M_{model} \\cdot \\mathbf{p}_{MC1.12.2}
        = \\begin{pmatrix} 1 & 0 & 0 \\\\ 0 & -1 & 0 \\\\ 0 & 0 & -1 \\end{pmatrix}
          \\begin{pmatrix} x \\\\ y \\\\ z \\end{pmatrix}
        = \\begin{pmatrix} x \\\\ -y \\\\ -z \\end{pmatrix}

    Numerical example:
        convert_model_pos(5.0, 12.0, 3.0) = (5.0, -12.0, -3.0)
        A pivot at (5, 12, 3) in Y-down maps to (5, -12, -3) in Y-up
        (before the +24 Y translation for origin shift)
    """
    return (x, -y, -z)


def convert_model_rot(rx: float, ry: float, rz: float, is_degrees: bool = False) -> tuple:
    """
    Convert rotation angles from MC 1.12.2 (Y-down, RH) to GeckoLib 1.20.1
    (Y-up, LH) using M_model = diag(1, -1, -1).

    Result: (rx, -ry, -rz) for single-axis rotations.

    Derivation (via rotation matrix similarity transform):
        Let R be a rotation matrix in the MC 1.12.2 system.
        The equivalent rotation in GeckoLib is:
            R' = M_model * R * M_model^{-1}

        Since M_model = diag(1, -1, -1) and M_model^{-1} = diag(1, -1, -1):

        For rotation about X-axis by angle θ:
            R_x(θ) = [[1, 0, 0], [0, cos θ, -sin θ], [0, sin θ, cos θ]]

            M_model * R_x(θ):
              Row 0: [1, 0, 0]
              Row 1: [0, -cos θ, sin θ]
              Row 2: [0, -sin θ, -cos θ]

            (M_model * R_x(θ)) * M_model:
              Row 0: [1, 0, 0]
              Row 1: [0, cos θ, -sin θ]
              Row 2: [0, sin θ, cos θ]
              = R_x(θ)

            ⟹ X rotation angle UNCHANGED: rx
            (X axis is not flipped by M_model, so rotations about X are preserved)

        For rotation about Y-axis by angle φ:
            R_y(φ) = [[cos φ, 0, sin φ], [0, 1, 0], [-sin φ, 0, cos φ]]

            M_model * R_y(φ):
              Row 0: [cos φ, 0, sin φ]
              Row 1: [0, -1, 0]
              Row 2: [sin φ, 0, -cos φ]

            (M_model * R_y(φ)) * M_model:
              Row 0: [cos φ, 0, -sin φ]
              Row 1: [0, 1, 0]
              Row 2: [sin φ, 0, cos φ]
              = R_y(-φ)

            ⟹ Y rotation angle NEGATED: -ry
            (Y axis is flipped, so rotations about Y reverse direction)

        For rotation about Z-axis by angle ψ:
            R_z(ψ) = [[cos ψ, -sin ψ, 0], [sin ψ, cos ψ, 0], [0, 0, 1]]

            M_model * R_z(ψ):
              Row 0: [cos ψ, -sin ψ, 0]
              Row 1: [-sin ψ, -cos ψ, 0]
              Row 2: [0, 0, -1]

            (M_model * R_z(ψ)) * M_model:
              Row 0: [cos ψ, sin ψ, 0]
              Row 1: [-sin ψ, cos ψ, 0]
              Row 2: [0, 0, 1]
              = R_z(-ψ)

            ⟹ Z rotation angle NEGATED: -rz
            (Z axis is flipped, so rotations about Z reverse direction)

    LaTeX:
        R' = M_{model} \\cdot R \\cdot M_{model}^{-1}
        \\implies (\\theta_x', \\theta_y', \\theta_z') = (\\theta_x, -\\theta_y, -\\theta_z)

    Numerical example:
        convert_model_rot(0.5, 0.3, 0.1) = (0.5, -0.3, -0.1)

    WARNING: If more than one rotation component is non-zero, the simple angle
    transformation may not be accurate due to rotation order differences. In that
    case, use convert_model_rotation_order() instead.
    """
    # Check for multi-axis rotation
    non_zero_count = sum(1 for a in [rx, ry, rz] if abs(a) > 1e-10)
    if non_zero_count > 1:
        warnings.warn(
            f"Multi-axis rotation detected: ({rx}, {ry}, {rz}). "
            f"Simple angle transformation may be inaccurate due to rotation order differences. "
            f"Consider using convert_model_rotation_order() for accurate conversion.",
            stacklevel=2
        )

    return (rx, -ry, -rz)


def convert_model_rotation_order(rx: float, ry: float, rz: float) -> tuple:
    """
    Convert rotation from MC 1.12.2 X→Y→Z order to GeckoLib Z→Y→X order,
    then apply the full model coordinate transformation (M_model = diag(1,-1,-1)).

    This handles both the rotation order change AND the Y-down→Y-up + RH→LH
    coordinate system transformation in a single mathematically consistent step.

    Algorithm (based on Graphics Gems IV matrix-to-Euler decomposition):
        1. Construct the 1.12.2 rotation matrix R = R_z(rz) * R_y(ry) * R_x(rx)
           (This is the extrinsic equivalent of intrinsic X→Y→Z)
        2. Apply model coordinate system transform:
           R' = M_model * R * M_model^{-1}
           where M_model = diag(1, -1, -1)
        3. Decompose R' into Z→Y→X Euler angles (GeckoLib order):
           R' = R_x(α) * R_y(β) * R_z(γ)
        4. Return (α, β, γ)

    WHY THIS DIFFERS FROM convert_rotation_order:
        The pure RH→LH function convert_rotation_order uses M = diag(1,1,-1),
        which only flips Z. This function uses M_model = diag(1,-1,-1), which
        flips both Y and Z. The Y-flip causes the Y rotation component to be
        negated (instead of preserved), and the X rotation component to be
        preserved (instead of negated).

    Comparison of similarity transforms:
        M = diag(1,1,-1):     X-rot → -θ,  Y-rot → +φ,  Z-rot → -ψ
        M_model = diag(1,-1,-1): X-rot → +θ,  Y-rot → -φ,  Z-rot → -ψ

    The difference arises because M_model flips the Y axis, which changes how
    the Y rotation matrix transforms under the similarity transform:
        M * R_y(φ) * M     = R_y(φ)     (Y preserved under pure Z-flip)
        M_model * R_y(φ) * M_model = R_y(-φ) (Y negated under Y+Z flip)

    The decomposition formulas (Graphics Gems IV) are identical to
    convert_rotation_order — only the similarity transform matrix differs.

    LaTeX:
        R_{1.12.2} = R_z(\\psi) \\cdot R_y(\\varphi) \\cdot R_x(\\theta)
        R' = M_{model} \\cdot R_{1.12.2} \\cdot M_{model}^{-1}
        R' = R_x(\\alpha) \\cdot R_y(\\beta) \\cdot R_z(\\gamma)

    Numerical example:
        For rx=0.5, ry=0.3, rz=0.1 (radians):
        R_1122 = Rz(0.1) * Ry(0.3) * Rx(0.5)
        R' = M_model * R_1122 * M_model
        Decompose R' into ZYX -> (alpha, beta, gamma)

    Returns:
        Tuple of (rx_new, ry_new, rz_new) in radians for GeckoLib Z→Y→X order
    """
    # Step 1: Construct 1.12.2 rotation matrix
    R_1122 = _rz(rz) @ _ry(ry) @ _rx(rx)

    # Step 2: Apply model coordinate system transform
    R_prime = M_MODEL @ R_1122 @ M_MODEL_INV

    # Step 3: Decompose R' into Z→Y→X Euler angles (GeckoLib order)
    # Same decomposition as convert_rotation_order — Graphics Gems IV
    # For R = Rx(α) * Ry(β) * Rz(γ):
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


def convert_model_cube_origin(ox: float, oy: float, oz: float,
                               w: float, h: float, d: float) -> tuple:
    """
    Convert a cube's origin from MC 1.12.2 ModelRenderer (Y-down, RH) to
    GeckoLib 1.20.1 geo.json (Y-up, LH) using M_model = diag(1, -1, -1).

    Result: (ox, -(oy + h), -(oz + d)) — the MINIMUM corner in Y-up space.

    Derivation:
        In MC 1.12.2 ModelRenderer, addBox(ox, oy, oz, w, h, d) defines a box
        spanning:
          X: [ox, ox + w]
          Y: [oy, oy + h]  (Y-down, so oy+h is further down)
          Z: [oz, oz + d]  (Z into screen in RH)

        After applying M_model = diag(1, -1, -1), each axis is transformed:
          X: [ox, ox + w]        → [ox, ox + w]       (unchanged)
          Y: [-oy, -(oy + h)]    → [-(oy + h), -oy]   (reversed: min corner is -(oy+h))
          Z: [-oz, -(oz + d)]    → [-(oz + d), -oz]   (reversed: min corner is -(oz+d))

        In GeckoLib/Bedrock geo.json format, the cube origin is the MINIMUM
        corner of the axis-aligned bounding box. Therefore:
          New origin = (ox, -(oy + h), -(oz + d))

        Size is preserved: (w, h, d)

    LaTeX:
        \\text{MC 1.12.2 box: } [o_x, o_x+w] \\times [o_y, o_y+h] \\times [o_z, o_z+d]
        \\text{After } M_{model}: [o_x, o_x+w] \\times [-(o_y+h), -o_y] \\times [-(o_z+d), -o_z]
        \\text{New origin (min corner)} = (o_x, -(o_y+h), -(o_z+d))

    WHY Y IS ALSO FLIPPED (unlike convert_size which only flips Z):
        The pure RH→LH function only needs to handle the Z-flip. But the full
        model transformation also flips Y. In MC 1.12.2, the box extends from
        oy DOWNWARD by h units. After Y-flip, this becomes extending from
        -(oy+h) UPWARD by h units. The minimum Y corner shifts from -(oy+h)
        because the Y direction is reversed.

    Numerical example:
        convert_model_cube_origin(-4.0, -8.0, -4.0, 8, 8, 8)
        = (-4.0, -(-8.0 + 8), -(-4.0 + 8))
        = (-4.0, 0.0, -4.0)
        A head box at offset (-4, -8, -4) with size (8,8,8) in Y-down
        maps to origin (-4, 0, -4) in Y-up space.

    Args:
        ox: Cube offset X (addBox first parameter)
        oy: Cube offset Y (addBox second parameter)
        oz: Cube offset Z (addBox third parameter)
        w:  Cube width  (addBox fourth parameter)
        h:  Cube height (addBox fifth parameter)
        d:  Cube depth  (addBox sixth parameter)

    Returns:
        Tuple (new_ox, new_oy, new_oz) — the minimum corner in GeckoLib Y-up space
    """
    new_ox = ox
    new_oy = -(oy + h)
    new_oz = -(oz + d)
    return (new_ox, new_oy, new_oz)


def convert_model_cube_size(w: float, h: float, d: float) -> tuple:
    """
    Convert cube dimensions from MC 1.12.2 to GeckoLib 1.20.1.

    Result: (w, h, d) — all dimensions are PRESERVED.

    Derivation:
        Under the linear transformation M_model = diag(1, -1, -1), axis-aligned
        box dimensions are preserved because the negation only reverses the
        direction of extension, not the magnitude.

        For each axis:
          X: extends from ox by +w → size w (no flip, preserved)
          Y: extends from -(oy+h) by +h → size h (Y-flip reverses direction,
             but the height magnitude is preserved)
          Z: extends from -(oz+d) by +d → size d (Z-flip reverses direction,
             but the depth magnitude is preserved)

        More formally, if an interval [a, a+s] is mapped by -x to [-a-s, -a],
        the new interval still has length s.

    LaTeX:
        \\text{Original interval: } [a, a+s], \\quad s > 0
        \\text{After negation: } [-a-s, -a]
        \\text{New length} = -a - (-a-s) = s \\quad \\checkmark

    Numerical example:
        convert_model_cube_size(8, 8, 8) = (8, 8, 8)
        convert_model_cube_size(4, 12, 4) = (4, 12, 4)
    """
    # Ensure all dimensions are non-negative
    if w < 0:
        warnings.warn(
            f"Negative width w={w} passed to convert_model_cube_size. "
            f"Taking absolute value.", stacklevel=2
        )
        w = abs(w)
    if h < 0:
        warnings.warn(
            f"Negative height h={h} passed to convert_model_cube_size. "
            f"Taking absolute value.", stacklevel=2
        )
        h = abs(h)
    if d < 0:
        warnings.warn(
            f"Negative depth d={d} passed to convert_model_cube_size. "
            f"Taking absolute value.", stacklevel=2
        )
        d = abs(d)
    return (w, h, d)


# ============================================================================
# Utility Functions
# ============================================================================

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

    # ========================================================================
    # Part 1: Pure RH→LH Transformation Tests (M = diag(1,1,-1))
    # ========================================================================

    # Test 1: Position conversion
    print("--- Test 1: Position Conversion (RH→LH) ---")
    result = convert_pos(1.0, 2.0, 3.0)
    expected = (1.0, 2.0, -3.0)
    print(f"convert_pos(1, 2, 3) = {result}, expected = {expected}")
    assert result == expected, "Position conversion failed!"
    print("PASS\n")

    # Test 2: Size conversion (depth preserved)
    print("--- Test 2: Size Conversion (RH→LH) ---")
    result = convert_size(4, 8, 6)
    expected = (4, 8, 6)
    print(f"convert_size(4, 8, 6) = {result}, expected = {expected}")
    assert result == expected, "Size conversion failed!"
    print("PASS\n")

    # Test 3: Single-axis rotation
    print("--- Test 3: Single-axis Rotation (RH→LH) ---")
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
    print("--- Test 4: Rotation Order Conversion (RH→LH) ---")
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
    print("--- Test 5: Multi-axis vs Simple (RH→LH) ---")
    rx, ry, rz = 0.3, 0.5, 0.7
    simple = convert_rot(rx, ry, rz)
    ordered = convert_rotation_order(rx, ry, rz)
    print(f"Simple negation: ({simple[0]:.6f}, {simple[1]:.6f}, {simple[2]:.6f})")
    print(f"Matrix reorder:  ({ordered[0]:.6f}, {ordered[1]:.6f}, {ordered[2]:.6f})")
    print(f"Difference shows why rotation order matters for multi-axis rotations")
    print()

    # ========================================================================
    # Part 2: Full Model Transformation Tests (M_model = diag(1,-1,-1))
    # ========================================================================

    print("=" * 60)
    print("Part 2: Full Model Transformation Tests")
    print("=" * 60 + "\n")

    # Test 6: Model position conversion
    print("--- Test 6: Model Position Conversion (M_model) ---")
    result = convert_model_pos(5.0, 12.0, 3.0)
    expected = (5.0, -12.0, -3.0)
    print(f"convert_model_pos(5, 12, 3) = {result}, expected = {expected}")
    assert result == expected, "Model position conversion failed!"
    # Zero test
    result = convert_model_pos(0.0, 0.0, 0.0)
    expected = (0.0, 0.0, 0.0)
    print(f"convert_model_pos(0, 0, 0) = {result}, expected = {expected}")
    assert result == expected, "Model position zero test failed!"
    # Negative values
    result = convert_model_pos(-4.0, -8.0, -4.0)
    expected = (-4.0, 8.0, 4.0)
    print(f"convert_model_pos(-4, -8, -4) = {result}, expected = {expected}")
    assert result == expected, "Model position negative test failed!"
    print("PASS\n")

    # Test 7: Model single-axis rotation conversion
    print("--- Test 7: Model Single-axis Rotation (M_model) ---")
    # X rotation: should be UNCHANGED (not negated like in RH→LH)
    result = convert_model_rot(0.5, 0.0, 0.0)
    expected = (0.5, 0.0, 0.0)
    print(f"convert_model_rot(0.5, 0, 0) = {result}, expected = {expected}")
    assert abs(result[0] - expected[0]) < 1e-10, "Model X rotation conversion failed!"
    # Y rotation: should be NEGATED (not preserved like in RH→LH)
    result = convert_model_rot(0.0, 0.3, 0.0)
    expected = (0.0, -0.3, 0.0)
    print(f"convert_model_rot(0, 0.3, 0) = {result}, expected = {expected}")
    assert abs(result[1] - expected[1]) < 1e-10, "Model Y rotation conversion failed!"
    # Z rotation: should be NEGATED (same as RH→LH)
    result = convert_model_rot(0.0, 0.0, 0.1)
    expected = (0.0, 0.0, -0.1)
    print(f"convert_model_rot(0, 0, 0.1) = {result}, expected = {expected}")
    assert abs(result[2] - expected[2]) < 1e-10, "Model Z rotation conversion failed!"
    # Multi-axis
    result = convert_model_rot(0.5, 0.3, 0.1)
    expected = (0.5, -0.3, -0.1)
    print(f"convert_model_rot(0.5, 0.3, 0.1) = {result}, expected = {expected}")
    assert abs(result[0] - expected[0]) < 1e-10, "Model combined X rotation failed!"
    assert abs(result[1] - expected[1]) < 1e-10, "Model combined Y rotation failed!"
    assert abs(result[2] - expected[2]) < 1e-10, "Model combined Z rotation failed!"
    print("PASS\n")

    # Test 8: Model rotation order conversion (single-axis consistency)
    print("--- Test 8: Model Rotation Order - Single Axis (M_model) ---")
    # Single X rotation: should match simple conversion
    alpha, beta, gamma = convert_model_rotation_order(0.5, 0.0, 0.0)
    print(f"convert_model_rotation_order(0.5, 0, 0) = ({alpha:.6f}, {beta:.6f}, {gamma:.6f})")
    print(f"Expected X (preserved): {0.5:.6f}")
    assert abs(alpha - 0.5) < 1e-6, f"Model rotation order X failed! got {alpha}"

    # Single Y rotation: should be negated
    alpha, beta, gamma = convert_model_rotation_order(0.0, 0.3, 0.0)
    print(f"convert_model_rotation_order(0, 0.3, 0) = ({alpha:.6f}, {beta:.6f}, {gamma:.6f})")
    print(f"Expected Y (negated): {-0.3:.6f}")
    assert abs(beta - (-0.3)) < 1e-6, f"Model rotation order Y failed! got {beta}"

    # Single Z rotation: should be negated
    alpha, beta, gamma = convert_model_rotation_order(0.0, 0.0, 0.1)
    print(f"convert_model_rotation_order(0, 0, 0.1) = ({alpha:.6f}, {beta:.6f}, {gamma:.6f})")
    print(f"Expected Z (negated): {-0.1:.6f}")
    assert abs(gamma - (-0.1)) < 1e-6, f"Model rotation order Z failed! got {gamma}"
    print("PASS\n")

    # Test 9: Model rotation order conversion (multi-axis matrix verification)
    print("--- Test 9: Model Rotation Order - Multi Axis (M_model) ---")
    rx_t, ry_t, rz_t = 0.3, 0.5, 0.7
    alpha, beta, gamma = convert_model_rotation_order(rx_t, ry_t, rz_t)
    print(f"convert_model_rotation_order({rx_t}, {ry_t}, {rz_t}) = "
          f"({alpha:.6f}, {beta:.6f}, {gamma:.6f})")

    # Verify by reconstructing: R_x(α) * R_y(β) * R_z(γ) should equal M_model * R_1122 * M_model
    R_check = _rx(alpha) @ _ry(beta) @ _rz(gamma)
    R_original = M_MODEL @ (_rz(rz_t) @ _ry(ry_t) @ _rx(rx_t)) @ M_MODEL_INV
    max_diff = np.max(np.abs(R_check - R_original))
    print(f"Max matrix difference: {max_diff:.2e}")
    assert max_diff < 1e-10, "Model rotation order conversion verification failed!"
    print("PASS\n")

    # Test 10: Model rotation order vs simple rotation (show difference)
    print("--- Test 10: Model Multi-axis Simple vs Matrix ---")
    rx_t, ry_t, rz_t = 0.3, 0.5, 0.7
    simple = convert_model_rot(rx_t, ry_t, rz_t)
    ordered = convert_model_rotation_order(rx_t, ry_t, rz_t)
    print(f"Simple transform: ({simple[0]:.6f}, {simple[1]:.6f}, {simple[2]:.6f})")
    print(f"Matrix reorder:   ({ordered[0]:.6f}, {ordered[1]:.6f}, {ordered[2]:.6f})")
    diff = [abs(s - o) for s, o in zip(simple, ordered)]
    print(f"Absolute diff:    ({diff[0]:.6f}, {diff[1]:.6f}, {diff[2]:.6f})")
    print(f"(Non-zero diff confirms rotation order matters for multi-axis)")
    print()

    # Test 11: Model cube origin conversion
    print("--- Test 11: Model Cube Origin Conversion (M_model) ---")
    # Standard head box: addBox(-4, -8, -4, 8, 8, 8) in Y-down
    result = convert_model_cube_origin(-4.0, -8.0, -4.0, 8, 8, 8)
    expected = (-4.0, -(-8.0 + 8), -(-4.0 + 8))  # (-4, 0, -4)
    print(f"convert_model_cube_origin(-4, -8, -4, 8, 8, 8) = {result}")
    print(f"Expected = {expected}")
    assert abs(result[0] - expected[0]) < 1e-10, "Cube origin X failed!"
    assert abs(result[1] - expected[1]) < 1e-10, "Cube origin Y failed!"
    assert abs(result[2] - expected[2]) < 1e-10, "Cube origin Z failed!"
    print("PASS")

    # Body box: addBox(-4, 0, -2, 8, 12, 4) in Y-down
    result = convert_model_cube_origin(-4.0, 0.0, -2.0, 8, 12, 4)
    expected = (-4.0, -(0.0 + 12), -(-2.0 + 4))  # (-4, -12, -2)
    print(f"convert_model_cube_origin(-4, 0, -2, 8, 12, 4) = {result}")
    print(f"Expected = {expected}")
    assert abs(result[0] - expected[0]) < 1e-10, "Body cube origin X failed!"
    assert abs(result[1] - expected[1]) < 1e-10, "Body cube origin Y failed!"
    assert abs(result[2] - expected[2]) < 1e-10, "Body cube origin Z failed!"
    print("PASS")

    # All-positive offset box
    result = convert_model_cube_origin(0.0, 0.0, 0.0, 4, 4, 4)
    expected = (0.0, -4.0, -4.0)
    print(f"convert_model_cube_origin(0, 0, 0, 4, 4, 4) = {result}")
    print(f"Expected = {expected}")
    assert abs(result[0] - expected[0]) < 1e-10, "Zero-offset cube origin X failed!"
    assert abs(result[1] - expected[1]) < 1e-10, "Zero-offset cube origin Y failed!"
    assert abs(result[2] - expected[2]) < 1e-10, "Zero-offset cube origin Z failed!"
    print("PASS\n")

    # Test 12: Model cube size conversion
    print("--- Test 12: Model Cube Size Conversion (M_model) ---")
    result = convert_model_cube_size(8, 8, 8)
    expected = (8, 8, 8)
    print(f"convert_model_cube_size(8, 8, 8) = {result}, expected = {expected}")
    assert result == expected, "Model cube size conversion failed!"

    result = convert_model_cube_size(4, 12, 4)
    expected = (4, 12, 4)
    print(f"convert_model_cube_size(4, 12, 4) = {result}, expected = {expected}")
    assert result == expected, "Model cube size conversion failed!"
    print("PASS\n")

    # Test 13: Comparison of RH→LH vs Model transformations
    print("--- Test 13: RH→LH vs Model Transformation Comparison ---")
    test_pos = (5.0, 12.0, 3.0)
    rh_lh = convert_pos(*test_pos)
    model = convert_model_pos(*test_pos)
    print(f"Position {test_pos}:")
    print(f"  RH→LH:  {rh_lh}  (only Z flipped)")
    print(f"  Model:  {model}  (Y and Z flipped)")
    print()

    test_rot = (0.5, 0.3, 0.1)
    rh_lh_rot = convert_rot(*test_rot)
    model_rot = convert_model_rot(*test_rot)
    print(f"Rotation {test_rot}:")
    print(f"  RH→LH:  {rh_lh_rot}  (-rx, +ry, -rz)")
    print(f"  Model:  {model_rot}  (+rx, -ry, -rz)")
    print()

    # Test 14: Verify M_model properties
    print("--- Test 14: Matrix Property Verification ---")
    # M_model should be its own inverse
    identity_check = M_MODEL @ M_MODEL_INV
    print(f"M_model * M_model_inv = \n{identity_check}")
    assert np.allclose(identity_check, np.eye(3)), "M_model is not its own inverse!"
    print("M_model is its own inverse: PASS")

    # M_model^2 should be identity
    m_sq = M_MODEL @ M_MODEL
    print(f"M_model^2 = \n{m_sq}")
    assert np.allclose(m_sq, np.eye(3)), "M_model^2 ≠ I!"
    print("M_model^2 = I: PASS")

    # det(M_model) should be 1 (proper rotation + reflection)
    det = np.linalg.det(M_MODEL)
    print(f"det(M_model) = {det}")
    assert abs(det - 1.0) < 1e-10, "det(M_model) ≠ 1!"
    print("det(M_model) = 1: PASS\n")

    # Test 15: Gimbal lock test for model rotation order
    print("--- Test 15: Model Rotation Order - Gimbal Lock ---")
    # Construct a rotation that results in gimbal lock (β = ±90°)
    # When ry = π/2 and combined with other rotations, we get gimbal lock
    alpha_gl, beta_gl, gamma_gl = convert_model_rotation_order(0.3, math.pi / 2, 0.0)
    print(f"Near gimbal lock: convert_model_rotation_order(0.3, π/2, 0)")
    print(f"  Result: ({alpha_gl:.6f}, {beta_gl:.6f}, {gamma_gl:.6f})")

    # Verify by reconstruction
    R_check = _rx(alpha_gl) @ _ry(beta_gl) @ _rz(gamma_gl)
    R_original = M_MODEL @ (_rz(0.0) @ _ry(math.pi / 2) @ _rx(0.3)) @ M_MODEL_INV
    max_diff = np.max(np.abs(R_check - R_original))
    print(f"  Max matrix difference: {max_diff:.2e}")
    assert max_diff < 1e-6, "Gimbal lock reconstruction failed!"
    print("PASS\n")

    # Test 16: Identity rotation test
    print("--- Test 16: Identity Rotation ---")
    alpha, beta, gamma = convert_model_rotation_order(0.0, 0.0, 0.0)
    print(f"convert_model_rotation_order(0, 0, 0) = ({alpha:.6f}, {beta:.6f}, {gamma:.6f})")
    assert abs(alpha) < 1e-10 and abs(beta) < 1e-10 and abs(gamma) < 1e-10, \
        "Identity rotation failed!"
    print("PASS\n")

    # Test 17: Round-trip verification for model rotation
    print("--- Test 17: Model Rotation Round-trip ---")
    # If we apply the model transform and then the inverse, we should get back the original
    test_angles = [(0.5, 0.0, 0.0), (0.0, 0.3, 0.0), (0.0, 0.0, 0.1), (0.3, 0.5, 0.7)]
    for rx_t, ry_t, rz_t in test_angles:
        # Forward: MC 1.12.2 → GeckoLib
        alpha, beta, gamma = convert_model_rotation_order(rx_t, ry_t, rz_t)
        # The resulting angles should produce a matrix equal to M_MODEL * R_1122 * M_MODEL
        R_geckolib = _rx(alpha) @ _ry(beta) @ _rz(gamma)
        R_mc1122 = _rz(rz_t) @ _ry(ry_t) @ _rx(rx_t)
        R_expected = M_MODEL @ R_mc1122 @ M_MODEL_INV
        max_diff = np.max(np.abs(R_geckolib - R_expected))
        print(f"  ({rx_t}, {ry_t}, {rz_t}) → ({alpha:.4f}, {beta:.4f}, {gamma:.4f}), "
              f"diff = {max_diff:.2e}")
        assert max_diff < 1e-10, f"Round-trip failed for ({rx_t}, {ry_t}, {rz_t})!"
    print("PASS\n")

    print("=== All CoreMath Tests Passed ===")
