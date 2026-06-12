#!/usr/bin/env python3
"""
Super Architecture — Quaternion Math Engine
=============================================

Quaternion-based rotation representation that eliminates gimbal lock problems
in Euler angle decomposition.  This module provides:

  - Quaternion class with full arithmetic support
  - Euler angle conversion (XYZ and ZYX conventions)
  - Axis-angle conversion
  - SLERP interpolation
  - Coordinate system rotation conversion via quaternion conjugation
  - Euler shortest-path resolution for animation keyframes

Euler angle conventions used in this module:
  - from_euler_xyz: builds R = Rz * Ry * Rx  (extrinsic XYZ = intrinsic ZYX)
  - from_euler_zyx: builds R = Rx * Ry * Rz  (extrinsic ZYX = intrinsic XYZ)
  - to_euler_xyz:   decomposes into Rz * Ry * Rx angles
  - to_euler_zyx:   decomposes into Rx * Ry * Rz angles

M_model similarity transform:
  M_model = diag(1, -1, -1) is a proper rotation (det = +1), equivalent to
  a 180-degree rotation about the X axis.  The similarity transform
  R' = M_model * R * M_model^{-1} is expressed as quaternion conjugation:
  Q' = Q_mirror * Q * Q_mirror^{-1}, where Q_mirror = (0, 1, 0, 0) encodes
  the 180-degree X rotation.
"""

from __future__ import annotations

import math
from typing import Tuple

import numpy as np


class Quaternion:
    """Quaternion for rotation representation.  Eliminates gimbal lock.

    Convention: q = w + x*i + y*j + z*k, where w is the scalar part.
    Unit quaternions represent rotations in 3D space.

    The Quaternion class is immutable-ish (no __setattr__ override, but
    all operations return new instances).
    """

    __slots__ = ("w", "x", "y", "z")

    def __init__(self, w: float = 1.0, x: float = 0.0,
                 y: float = 0.0, z: float = 0.0) -> None:
        self.w = w
        self.x = x
        self.y = y
        self.z = z

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_euler_xyz(cls, rx: float, ry: float, rz: float,
                       degrees: bool = False) -> Quaternion:
        """Create quaternion from Euler angles in XYZ (extrinsic) order.

        Builds R = Rz(rz) * Ry(ry) * Rx(rx), which is the extrinsic
        equivalent of intrinsic ZYX rotation.  This is the Minecraft 1.12.2
        convention where rotations are applied X first, Y second, Z third.

        Args:
            rx: Rotation about X axis.
            ry: Rotation about Y axis.
            rz: Rotation about Z axis.
            degrees: If True, inputs are in degrees; otherwise radians.

        Returns:
            Unit quaternion representing the combined rotation.
        """
        if degrees:
            rx = math.radians(rx)
            ry = math.radians(ry)
            rz = math.radians(rz)

        # R = Rz(rz) * Ry(ry) * Rx(rx)
        # Quaternion multiplication: q = qz * qy * qx
        qx = Quaternion(math.cos(rx / 2), math.sin(rx / 2), 0.0, 0.0)
        qy = Quaternion(math.cos(ry / 2), 0.0, math.sin(ry / 2), 0.0)
        qz = Quaternion(math.cos(rz / 2), 0.0, 0.0, math.sin(rz / 2))

        return qz * qy * qx

    @classmethod
    def from_euler_zyx(cls, rx: float, ry: float, rz: float,
                       degrees: bool = False) -> Quaternion:
        """Create quaternion from Euler angles in ZYX (extrinsic) order.

        Builds R = Rx(rx) * Ry(ry) * Rz(rz), which is the extrinsic
        equivalent of intrinsic XYZ rotation.  This is the GeckoLib /
        Blockbench convention where rotations are applied Z first, Y second,
        X third.

        Args:
            rx: Rotation about X axis.
            ry: Rotation about Y axis.
            rz: Rotation about Z axis.
            degrees: If True, inputs are in degrees; otherwise radians.

        Returns:
            Unit quaternion representing the combined rotation.
        """
        if degrees:
            rx = math.radians(rx)
            ry = math.radians(ry)
            rz = math.radians(rz)

        # R = Rx(rx) * Ry(ry) * Rz(rz)
        # Quaternion multiplication: q = qx * qy * qz
        qx = Quaternion(math.cos(rx / 2), math.sin(rx / 2), 0.0, 0.0)
        qy = Quaternion(math.cos(ry / 2), 0.0, math.sin(ry / 2), 0.0)
        qz = Quaternion(math.cos(rz / 2), 0.0, 0.0, math.sin(rz / 2))

        return qx * qy * qz

    @classmethod
    def from_axis_angle(cls, axis: Tuple[float, float, float],
                        angle: float) -> Quaternion:
        """Create quaternion from axis-angle representation.

        Args:
            axis: Rotation axis (will be normalized internally).
            angle: Rotation angle in radians.

        Returns:
            Unit quaternion representing the rotation.

        Raises:
            ValueError: If axis is the zero vector.
        """
        ax, ay, az = axis
        length = math.sqrt(ax * ax + ay * ay + az * az)
        if length < 1e-15:
            raise ValueError("Axis must be a non-zero vector")

        ax /= length
        ay /= length
        az /= length

        half = angle / 2.0
        s = math.sin(half)
        return Quaternion(math.cos(half), ax * s, ay * s, az * s)

    @classmethod
    def identity(cls) -> Quaternion:
        """Return the identity quaternion (no rotation)."""
        return Quaternion(1.0, 0.0, 0.0, 0.0)

    # ------------------------------------------------------------------
    # Decomposition
    # ------------------------------------------------------------------

    def to_euler_xyz(self, degrees: bool = False) -> Tuple[float, float, float]:
        """Decompose into XYZ (extrinsic) Euler angles.

        Decomposes the rotation as R = Rz * Ry * Rx, returning (rx, ry, rz).
        This matches from_euler_xyz which builds the same convention.

        For R = Rz(c) * Ry(b) * Rx(a) the rotation matrix has:
          R[2,0] = -sin(b)
          R[2,1] = cos(b) * sin(a)
          R[2,2] = cos(b) * cos(a)
          R[1,0] = sin(c) * cos(b)
          R[0,0] = cos(c) * cos(b)

        Decomposition:
          b = asin(-R[2,0])
          a = atan2(R[2,1], R[2,2])
          c = atan2(R[1,0], R[0,0])

        Handles gimbal lock gracefully by setting rx=0 when |R[2,0]| ≈ 1.

        Args:
            degrees: If True, return angles in degrees; otherwise radians.

        Returns:
            Tuple (rx, ry, rz) — Euler angles.
        """
        R = self.to_rotation_matrix()

        r20 = _clamp(R[2, 0], -1.0, 1.0)

        if abs(r20) < 1.0 - 1e-10:
            # No gimbal lock
            ry = math.asin(-r20)
            rx = math.atan2(R[2, 1], R[2, 2])
            rz = math.atan2(R[1, 0], R[0, 0])
        else:
            # Gimbal lock: ry = +/-90 degrees
            rx = 0.0
            sign = 1.0 if r20 < 0 else -1.0  # r20 < 0 -> ry = +pi/2
            ry = sign * math.pi / 2.0
            # At gimbal lock, only (a-c) or (a+c) is determined.
            # Set rx = 0 and solve for rz using R[0,1] and R[1,1].
            rz = math.atan2(-R[0, 1], R[1, 1])

        if degrees:
            return (math.degrees(rx), math.degrees(ry), math.degrees(rz))
        return (rx, ry, rz)

    def to_euler_zyx(self, degrees: bool = False) -> Tuple[float, float, float]:
        """Decompose into ZYX (extrinsic) Euler angles.

        Decomposes the rotation as R = Rx * Ry * Rz, returning (rx, ry, rz).
        This matches from_euler_zyx which builds the same convention.
        This is the GeckoLib/Blockbench convention.

        For R = Rx(a) * Ry(b) * Rz(c) the rotation matrix has:
          R[0,2] = sin(b)
          R[1,2] = -sin(a) * cos(b)
          R[2,2] = cos(a) * cos(b)
          R[0,1] = -cos(b) * sin(c)
          R[0,0] = cos(b) * cos(c)

        Decomposition:
          b = asin(R[0,2])
          a = atan2(-R[1,2], R[2,2])
          c = atan2(-R[0,1], R[0,0])

        Handles gimbal lock gracefully by setting rx=0 when |R[0,2]| ≈ 1.

        Args:
            degrees: If True, return angles in degrees; otherwise radians.

        Returns:
            Tuple (rx, ry, rz) — Euler angles.
        """
        R = self.to_rotation_matrix()

        r02 = _clamp(R[0, 2], -1.0, 1.0)

        if abs(r02) < 1.0 - 1e-10:
            # No gimbal lock
            ry = math.asin(r02)
            rx = math.atan2(-R[1, 2], R[2, 2])
            rz = math.atan2(-R[0, 1], R[0, 0])
        else:
            # Gimbal lock: ry = +/-90 degrees
            rx = 0.0
            sign = 1.0 if r02 > 0 else -1.0  # r02 > 0 -> ry = +pi/2
            ry = sign * math.pi / 2.0
            # At gimbal lock, only (c-a) or (c+a) is determined.
            # Set rx = 0 and solve for rz using R[1,0] and R[1,1].
            rz = math.atan2(R[1, 0], R[1, 1])

        if degrees:
            return (math.degrees(rx), math.degrees(ry), math.degrees(rz))
        return (rx, ry, rz)

    def to_rotation_matrix(self) -> np.ndarray:
        """Convert quaternion to a 3x3 rotation matrix.

        Returns:
            3x3 numpy array representing the rotation matrix.
        """
        q = self.normalize()
        w, x, y, z = q.w, q.x, q.y, q.z

        return np.array([
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - w * z),     2.0 * (x * z + w * y)],
            [2.0 * (x * y + w * z),        1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - w * x)],
            [2.0 * (x * z - w * y),        2.0 * (y * z + w * x),     1.0 - 2.0 * (x * x + y * y)],
        ])

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def conjugate(self) -> Quaternion:
        """Return the conjugate of this quaternion: (w, -x, -y, -z).

        For unit quaternions, the conjugate equals the inverse.
        """
        return Quaternion(self.w, -self.x, -self.y, -self.z)

    def inverse(self) -> Quaternion:
        """Return the inverse of this quaternion.

        For unit quaternions, this equals the conjugate.
        For non-unit quaternions, computes q* / |q|².
        """
        norm_sq = self.w * self.w + self.x * self.x + self.y * self.y + self.z * self.z
        if norm_sq < 1e-30:
            raise ValueError("Cannot invert a zero-norm quaternion")
        inv_norm_sq = 1.0 / norm_sq
        return Quaternion(
            self.w * inv_norm_sq,
            -self.x * inv_norm_sq,
            -self.y * inv_norm_sq,
            -self.z * inv_norm_sq,
        )

    def normalize(self) -> Quaternion:
        """Return a normalized (unit) copy of this quaternion."""
        norm = math.sqrt(
            self.w * self.w + self.x * self.x + self.y * self.y + self.z * self.z
        )
        if norm < 1e-30:
            return Quaternion(1.0, 0.0, 0.0, 0.0)
        inv = 1.0 / norm
        return Quaternion(self.w * inv, self.x * inv, self.y * inv, self.z * inv)

    def norm(self) -> float:
        """Return the norm (magnitude) of this quaternion."""
        return math.sqrt(
            self.w * self.w + self.x * self.x + self.y * self.y + self.z * self.z
        )

    # ------------------------------------------------------------------
    # Multiplication
    # ------------------------------------------------------------------

    def __mul__(self, other: Quaternion) -> Quaternion:
        """Hamilton product of two quaternions.

        The product q1 * q2 represents the rotation q2 followed by q1.
        This matches the convention where R = R1 * R2 means "apply R2 first".
        """
        if not isinstance(other, Quaternion):
            return NotImplemented

        w1, x1, y1, z1 = self.w, self.x, self.y, self.z
        w2, x2, y2, z2 = other.w, other.x, other.y, other.z

        return Quaternion(
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        )

    # ------------------------------------------------------------------
    # SLERP
    # ------------------------------------------------------------------

    @staticmethod
    def slerp(q1: Quaternion, q2: Quaternion, t: float) -> Quaternion:
        """Spherical linear interpolation between two quaternions.

        Args:
            q1: Start quaternion (t=0).
            q2: End quaternion (t=1).
            t: Interpolation parameter in [0, 1].

        Returns:
            Interpolated quaternion.

        Note:
            Always takes the shortest path on the quaternion hypersphere
            by negating q2 if the dot product with q1 is negative.
        """
        q1 = q1.normalize()
        q2 = q2.normalize()

        # Compute dot product
        dot = q1.w * q2.w + q1.x * q2.x + q1.y * q2.y + q1.z * q2.z

        # Take shortest path: if dot < 0, negate q2
        if dot < 0.0:
            q2 = Quaternion(-q2.w, -q2.x, -q2.y, -q2.z)
            dot = -dot

        # Clamp for numerical stability
        dot = _clamp(dot, -1.0, 1.0)

        # If quaternions are very close, use linear interpolation to avoid
        # division by near-zero in the slerp formula
        if dot > 0.9995:
            # Linear interpolation
            result = Quaternion(
                q1.w + t * (q2.w - q1.w),
                q1.x + t * (q2.x - q1.x),
                q1.y + t * (q2.y - q1.y),
                q1.z + t * (q2.z - q1.z),
            )
            return result.normalize()

        # Standard slerp
        theta_0 = math.acos(dot)
        theta = theta_0 * t
        sin_theta = math.sin(theta)
        sin_theta_0 = math.sin(theta_0)

        s1 = math.cos(theta) - dot * sin_theta / sin_theta_0
        s2 = sin_theta / sin_theta_0

        return Quaternion(
            s1 * q1.w + s2 * q2.w,
            s1 * q1.x + s2 * q2.x,
            s1 * q1.y + s2 * q2.y,
            s1 * q1.z + s2 * q2.z,
        ).normalize()

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"Quaternion(w={self.w:.6f}, x={self.x:.6f}, y={self.y:.6f}, z={self.z:.6f})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Quaternion):
            return NotImplemented
        return (abs(self.w - other.w) < 1e-10 and abs(self.x - other.x) < 1e-10
                and abs(self.y - other.y) < 1e-10 and abs(self.z - other.z) < 1e-10)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to [lo, hi]."""
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Coordinate system rotation conversion
# ---------------------------------------------------------------------------

def convert_rotation_quaternion(
    rx: float, ry: float, rz: float,
    source_order: str = "xyz",
    target_order: str = "zyx",
    m_model: bool = True,
) -> Tuple[float, float, float]:
    """Convert rotation between coordinate systems using quaternion math.

    This eliminates the gimbal lock problem in the old Euler-angle-based
    convert_model_rotation_order() from core_math.py.

    Algorithm:
      1. Build source rotation as quaternion from source Euler convention.
      2. If m_model=True, apply M_model similarity transform via quaternion
         conjugation: Q' = Q_mirror * Q * Q_mirror^{-1}.
         M_model = diag(1, -1, -1) is a proper rotation (det=+1), equivalent
         to a 180-degree rotation about X.  The mirror quaternion is:
         Q_mirror = Quaternion(cos(pi/2), sin(pi/2), 0, 0) = (0, 1, 0, 0).
      3. Decompose Q' into target Euler angles.

    Args:
        rx: X rotation in degrees.
        ry: Y rotation in degrees.
        rz: Z rotation in degrees.
        source_order: "xyz" for MC 1.12.2 intrinsic (extrinsic XYZ),
                      "zyx" for GeckoLib intrinsic (extrinsic ZYX).
        target_order: "xyz" or "zyx" for the output convention.
        m_model: If True, apply the M_model = diag(1,-1,-1) similarity
                 transform for MC 1.12.2 -> GeckoLib conversion.

    Returns:
        Tuple (rx_new, ry_new, rz_new) in degrees for the target convention.
    """
    # Step 1: Build source quaternion
    if source_order == "xyz":
        q = Quaternion.from_euler_xyz(rx, ry, rz, degrees=True)
    elif source_order == "zyx":
        q = Quaternion.from_euler_zyx(rx, ry, rz, degrees=True)
    else:
        raise ValueError(f"Unknown source_order: {source_order!r}")

    # Step 2: Apply M_model similarity transform if requested
    if m_model:
        # M_model = diag(1, -1, -1) is a 180-degree rotation about X axis.
        # Q_mirror encodes this: R_x(pi) -> Q = (cos(pi/2), sin(pi/2), 0, 0)
        q_mirror = Quaternion(0.0, 1.0, 0.0, 0.0)
        # Similarity transform: Q' = Q_mirror * Q * Q_mirror^{-1}
        # For a unit quaternion, inverse = conjugate
        q = q_mirror * q * q_mirror.conjugate()

    # Step 3: Decompose into target Euler angles
    if target_order == "xyz":
        result = q.to_euler_xyz(degrees=True)
    elif target_order == "zyx":
        result = q.to_euler_zyx(degrees=True)
    else:
        raise ValueError(f"Unknown target_order: {target_order!r}")

    return result


def euler_shortest_path(
    rx1: float, ry1: float, rz1: float,
    rx2: float, ry2: float, rz2: float,
) -> Tuple[float, float, float]:
    """Find the closest Euler representation of the second rotation to the first.

    Given two sets of Euler angles representing the same rotation (or similar
    rotations), find the equivalent representation of the second that is
    closest to the first.  This avoids 360-degree jumps in animation keyframes
    that cause incorrect interpolation.

    For example, if keyframe1 has ry=10 and keyframe2 has ry=370, this function
    would return ry=10 for keyframe2 (since 370 = 10 + 360).

    Algorithm:
      1. Convert both to quaternions.
      2. Ensure both quaternions are on the same hemisphere (dot product > 0).
      3. If they represent the same rotation, decompose the first quaternion
         using the second's angles as a reference to find the shortest path.
      4. Adjust each Euler angle by adding/subtracting 360 to minimize the
         absolute difference from the reference.

    Args:
        rx1, ry1, rz1: Reference Euler angles in degrees.
        rx2, ry2, rz2: Target Euler angles in degrees to adjust.

    Returns:
        Tuple (rx2_adj, ry2_adj, rz2_adj) — adjusted angles closest to
        (rx1, ry1, rz1).
    """
    # Strategy: adjust each angle independently by adding/subtracting
    # multiples of 360 to minimize the difference from the reference.
    # This is the standard approach for animation keyframe shortest-path.

    def _adjust_angle(ref: float, val: float) -> float:
        """Adjust val to be within 180 degrees of ref."""
        diff = val - ref
        # Normalize diff to [-360, 360]
        diff = diff % 720.0
        if diff > 360.0:
            diff -= 720.0
        if diff < -360.0:
            diff += 720.0

        # If the difference is more than 180, there's a shorter path
        # going the other way around
        if diff > 180.0:
            diff -= 360.0
        elif diff < -180.0:
            diff += 360.0

        return ref + diff

    rx_adj = _adjust_angle(rx1, rx2)
    ry_adj = _adjust_angle(ry1, ry2)
    rz_adj = _adjust_angle(rz1, rz2)

    return (rx_adj, ry_adj, rz_adj)


def quaternion_conjugate_rotate(
    q: Quaternion,
    q_mirror: Quaternion,
) -> Quaternion:
    """Apply a similarity transform via quaternion conjugation.

    Computes: q_mirror * q * q_mirror^{-1}

    This is equivalent to the matrix similarity transform
    R' = M * R * M^{-1}, but using quaternion algebra which avoids
    gimbal lock entirely.

    Args:
        q: The rotation quaternion to transform.
        q_mirror: The quaternion encoding the coordinate system transform.

    Returns:
        The transformed quaternion.
    """
    return q_mirror * q * q_mirror.conjugate()
