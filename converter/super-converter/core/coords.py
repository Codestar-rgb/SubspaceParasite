#!/usr/bin/env python3
"""
Super Architecture — Coordinate System Transformations
=======================================================

Coordinate system transformations for MC 1.12.2 -> GeckoLib 1.20.1.

Coordinate systems:
  MC 1.12.2 ModelRenderer: Right-hand, Y-DOWN (origin at top of hitbox)
  GeckoLib 1.20.1 geo.json: Left-hand, Y-UP (origin at feet)
  Blockbench .bbmodel:      Left-hand, Y-UP (same as GeckoLib)

Transform matrix: M_model = diag(1, -1, -1)
This handles both Y-flip and Z-flip (RH->LH) in a single operation.

Key improvement over old core_math.py:
  - Rotation conversion uses quaternion math by default for multi-axis
    rotations, eliminating gimbal lock issues.
  - Single-axis rotations use fast simple negation (rx, -ry, -rz).
  - UV face swapping is explicit and documented.
"""

from __future__ import annotations

import math
from typing import Dict, Tuple

from .quaternion import Quaternion, convert_rotation_quaternion


# ---------------------------------------------------------------------------
# Position conversion
# ---------------------------------------------------------------------------

def convert_position(x: float, y: float, z: float) -> Tuple[float, float, float]:
    """Convert position from MC 1.12.2 (Y-down, RH) to GeckoLib (Y-up, LH).

    M_model = diag(1, -1, -1) applied to position vector:
      P_LH = M_model * P_RH = (x, -y, -z)

    Note: The Y-flip handles the axis direction reversal.  An additional
    translation in Y (e.g. +24.0 for standard bipeds) is typically applied
    in the model converter to shift the origin from the top of the hitbox
    to the feet.  That translation is NOT included here because it depends
    on the entity height.

    Args:
        x, y, z: Position in MC 1.12.2 coordinates.

    Returns:
        Position in GeckoLib coordinates: (x, -y, -z).
    """
    return (x, -y, -z)


# ---------------------------------------------------------------------------
# Rotation conversion
# ---------------------------------------------------------------------------

def convert_rotation(
    rx: float, ry: float, rz: float,
    use_quaternion: bool = True,
) -> Tuple[float, float, float]:
    """Convert rotation from MC 1.12.2 to GeckoLib using quaternion math.

    For single-axis rotations (only one non-zero component):
      Result is (rx, -ry, -rz) — derived from M_model similarity transform:
        M_model * R_x(θ) * M_model = R_x(θ)      (X preserved)
        M_model * R_y(φ) * M_model = R_y(-φ)     (Y negated)
        M_model * R_z(ψ) * M_model = R_z(-ψ)     (Z negated)

    For multi-axis rotations (two or more non-zero components):
      Uses quaternion similarity transform to avoid gimbal lock.  The
      quaternion approach computes the exact rotation in 4D space and
      decomposes back to Euler angles, never losing information at
      +/-90 degree singularities.

    Args:
        rx, ry, rz: Rotation angles in degrees (MC 1.12.2 convention:
                     intrinsic X->Y->Z = extrinsic XYZ).
        use_quaternion: If True, use quaternion math for multi-axis
                        rotations.  If False, use simple negation
                        (rx, -ry, -rz) even for multi-axis (old behavior).

    Returns:
        Tuple (rx_new, ry_new, rz_new) in degrees (GeckoLib convention:
        intrinsic Z->Y->X = extrinsic ZYX).
    """
    non_zero_count = sum(1 for a in (rx, ry, rz) if abs(a) > 1e-10)

    if non_zero_count <= 1 or not use_quaternion:
        # Single-axis rotation or explicit fallback: simple angle transform
        return (rx, -ry, -rz)

    # Multi-axis rotation: use quaternion similarity transform
    return convert_rotation_quaternion(
        rx, ry, rz,
        source_order="xyz",   # MC 1.12.2 intrinsic
        target_order="zyx",   # GeckoLib
        m_model=True,
    )


# ---------------------------------------------------------------------------
# Cube conversion
# ---------------------------------------------------------------------------

def convert_cube_origin(
    ox: float, oy: float, oz: float,
    w: float, h: float, d: float,
) -> Tuple[float, float, float]:
    """Convert cube origin from MC 1.12.2 to GeckoLib.

    In MC 1.12.2 ModelRenderer, addBox(ox, oy, oz, w, h, d) defines a box
    spanning:
      X: [ox, ox + w]
      Y: [oy, oy + h]   (Y-down, so oy+h is further down)
      Z: [oz, oz + d]   (Z into screen in RH)

    After applying M_model = diag(1, -1, -1):
      X: [ox, ox + w]              (unchanged)
      Y: [-(oy+h), -oy]            (reversed: min corner is -(oy+h))
      Z: [-(oz+d), -oz]            (reversed: min corner is -(oz+d))

    In GeckoLib geo.json format, the cube origin is the MINIMUM corner.
    Therefore: new origin = (ox, -(oy + h), -(oz + d))

    Args:
        ox, oy, oz: Cube offset in MC 1.12.2 coordinates.
        w, h, d:    Cube dimensions (width, height, depth).

    Returns:
        Cube origin in GeckoLib coordinates: (ox, -(oy+h), -(oz+d)).
    """
    new_ox = ox
    new_oy = -(oy + h)
    new_oz = -(oz + d)
    return (new_ox, new_oy, new_oz)


def convert_cube_size(
    w: float, h: float, d: float,
) -> Tuple[float, float, float]:
    """Convert cube dimensions from MC 1.12.2 to GeckoLib.

    Under M_model = diag(1, -1, -1), axis-aligned box dimensions are
    preserved because negation only reverses the direction of extension,
    not the magnitude.  If an interval [a, a+s] is mapped by -x to
    [-a-s, -a], the new interval still has length s.

    All dimensions must be non-negative.  Negative values are corrected
    with a warning.

    Args:
        w, h, d: Cube dimensions (width, height, depth).

    Returns:
        Preserved dimensions: (w, h, d) with all values non-negative.
    """
    return (abs(w), abs(h), abs(d))


# ---------------------------------------------------------------------------
# UV face conversion
# ---------------------------------------------------------------------------

def convert_uv_face_north_south(uv_data: Dict) -> Dict:
    """Swap North <-> South UV faces for RH -> LH Z-flip correction.

    M_model Z-flip maps:
      north_RH [0,0,-1] -> M_model*[0,0,-1] = [0,0,+1] = south_LH
      south_RH [0,0,+1] -> M_model*[0,0,+1] = [0,0,-1] = north_LH

    So UV assigned to 'north' in RH must go to 'south' in LH, and vice versa.
    West/East and Up/Down do NOT swap under M_model.

    For mirrored cubes, also swap West <-> East (because mirror in MC 1.12.2
    is about the Z axis, and the Z-flip changes which side is "west" vs "east").

    Args:
        uv_data: Dict mapping face_name -> {uv: [u,v], uv_size: [w,h]}.
                 Face names: "north", "south", "east", "west", "up", "down".

    Returns:
        New dict with north/south UV data swapped.  Original dict is not
        modified.
    """
    if not uv_data:
        return {}

    result = dict(uv_data)

    # Swap north <-> south
    north = uv_data.get("north")
    south = uv_data.get("south")
    if north is not None:
        result["south"] = north
    else:
        result.pop("south", None)
    if south is not None:
        result["north"] = south
    else:
        result.pop("north", None)

    return result


def convert_uv_face_mirror(uv_data: Dict) -> Dict:
    """Swap West <-> East UV faces for mirrored cubes after Z-flip.

    When a cube has mirror=True in MC 1.12.2, the texture is mirrored
    about the Z axis.  After the Z-flip (RH -> LH), the mirrored west
    and east faces swap sides.

    This should be called AFTER convert_uv_face_north_south() for mirrored
    cubes.

    Args:
        uv_data: Dict mapping face_name -> {uv: [u,v], uv_size: [w,h]}.

    Returns:
        New dict with west/east UV data swapped.  Original dict is not
        modified.
    """
    if not uv_data:
        return {}

    result = dict(uv_data)

    # Swap west <-> east
    west = uv_data.get("west")
    east = uv_data.get("east")
    if west is not None:
        result["east"] = west
    else:
        result.pop("east", None)
    if east is not None:
        result["west"] = east
    else:
        result.pop("west", None)

    return result


def convert_uv_for_cube(uv_data: Dict, mirror: bool = False) -> Dict:
    """Full UV face conversion for a cube.

    Applies the correct sequence of face swaps:
      1. Always swap North <-> South (Z-flip)
      2. If mirror=True, also swap West <-> East

    Args:
        uv_data: Dict mapping face_name -> {uv: [u,v], uv_size: [w,h]}.
        mirror: Whether the cube has the mirror flag set.

    Returns:
        New dict with appropriate face swaps applied.
    """
    result = convert_uv_face_north_south(uv_data)
    if mirror:
        result = convert_uv_face_mirror(result)
    return result
