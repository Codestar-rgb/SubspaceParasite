"""AnimForge v19 Configuration

Centralized configuration with sensible defaults for Minecraft 1.20.1 / GeckoLib
animation conversion. All parameters are grouped by subsystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Tuple


@dataclass
class AnimForgeConfig:
    """Master configuration for AnimForge v19 converter.

    Attributes:
        rounding_time: Decimal places for time values.
        rounding_value: Decimal places for rotation/position values.
        c0_threshold: Max absolute difference to consider values matching for C0 continuity.
        c1_transition_zone: Fraction of duration used for transition zone blend (0.0-1.0).
        c1_distortion_limit: Max allowed RMS distortion from global cubic C1 correction.
        dp_epsilon: Base Douglas-Peucker simplification epsilon (degrees for rotation).
        dp_walk_leg_epsilon_mult: Multiplier on dp_epsilon for walk leg bones (should be <1).
        dp_protected_first_last: Whether to always protect first and last keyframes.
        min_kf_walk_leg: Minimum keyframes per channel for walk leg bones.
        min_kf_default: Minimum keyframes per channel for non-walk bones.
        min_kf_density_threshold: Below this fraction of original KF count, quality gate fails.
        amplitude_fidelity_threshold: Below this fraction of original amplitude, quality gate fails.
        upsample_target: Target keyframe count for catmull-rom upsampling of sparse channels.
        autocorr_min_peaks: Minimum autocorrelation peaks for periodicity detection.
        autocorr_threshold: Minimum normalized autocorrelation value to count as a peak.
        half_cycle_similarity: Threshold for considering two halves of a cycle as mirror images.
        dedup_hash_precision: Decimal places used when computing content hash.
        walk_max_duration: Animations longer than this are not classified as walk.
        idle_max_amplitude: Animations with max bone rotation below this are likely idle.
        model_name: Override model name for output animation identifiers.
        coordinate_rotation: Transform for rotation: negate X and Y components.
        coordinate_position: Transform for position: negate X component.
    """

    # ── Rounding ──────────────────────────────────────────────────────────
    rounding_time: int = 4
    rounding_value: int = 4

    # ── Continuity ────────────────────────────────────────────────────────
    c0_threshold: float = 0.01
    c1_transition_zone: float = 0.15  # 15% of duration for walk, 30% for idle
    c1_distortion_limit: float = 0.5  # max RMS distortion from global cubic

    # ── Simplification ────────────────────────────────────────────────────
    dp_epsilon: float = 0.5  # degrees
    dp_walk_leg_epsilon_mult: float = 0.2  # 5x tighter for walk legs
    dp_protected_first_last: bool = True

    # ── Minimum keyframes ─────────────────────────────────────────────────
    min_kf_walk_leg: int = 8
    min_kf_default: int = 2
    min_kf_density_threshold: float = 0.5  # 50% of original KF count

    # ── Quality ───────────────────────────────────────────────────────────
    amplitude_fidelity_threshold: float = 0.70  # 70% of original amplitude

    # ── Upsampling ────────────────────────────────────────────────────────
    upsample_target: int = 8

    # ── Periodicity detection ─────────────────────────────────────────────
    autocorr_min_peaks: int = 2
    autocorr_threshold: float = 0.6
    half_cycle_similarity: float = 0.85

    # ── Deduplication ─────────────────────────────────────────────────────
    dedup_hash_precision: int = 2

    # ── Classification thresholds ─────────────────────────────────────────
    walk_max_duration: float = 3.0
    idle_max_amplitude: float = 15.0  # degrees

    # ── Model ─────────────────────────────────────────────────────────────
    model_name: str = ""

    # ── Coordinate transforms (applied only at serialization) ─────────────
    coordinate_rotation: Tuple[bool, bool, bool] = (True, True, False)
    # (negate_x, negate_y, negate_z) → (-rx, -ry, rz)
    coordinate_position: Tuple[bool, bool, bool] = (True, False, False)
    # (negate_x, negate_y, negate_z) → (-px, py, pz)

    # ── Differentiator ────────────────────────────────────────────────────
    attack_speed_mult: float = 1.3
    attack_arm_amplitude_mult: float = 1.3
    attack_body_lunge_degrees: float = 8.0

    evolved_speed_mult: float = 0.8333  # 1/1.2 → slower
    evolved_body_tremor_amplitude: float = 2.0
    evolved_head_sway_amplitude: float = 4.0
    evolved_breathing_pulse_amplitude: float = 1.5

    # ── Bone name patterns ────────────────────────────────────────────────
    # These must cover all MROLF-TGNBF naming conventions
    leg_patterns: Tuple[str, ...] = (
        # English names
        "leg", "foot", "thigh", "shin", "knee", "ankle",
        "leftleg", "rightleg", "frontleg", "backleg",
        "Lfrontleg", "Rfrontleg", "Lbackleg", "Rbackleg",
        # MROLF biped: jointLL/jointRL (leg left/right)
        "jointLL", "jointRL", "jointLL1", "jointRL1",
        "jointLL2", "jointRL2", "jointLL3", "jointRL3",
        "jointLL0",
        # MROLF quadruped: jointFL/jointFR (front), jointBL/jointBR (back)
        "jointFL", "jointFR", "jointBL", "jointBR",
        "jointFLL", "jointFRL", "jointBLL", "jointBRL",
        "jointFLL1", "jointFRL1", "jointBLL1", "jointBRL1",
        "jointFLL2", "jointFRL2", "jointBLL2", "jointBRL2",
        "jointFLL3", "jointFRL3", "jointBLL3", "jointBRL3",
        "jointFLL4", "jointFRL4", "jointBLL4", "jointBRL4",
        # MROLF hexapod: jointML/jointMR (middle)
        "jointML", "jointMR", "jointMLL", "jointMRL",
        "jointMLL1", "jointMRL1", "jointMLL2", "jointMRL2",
        "jointMLL3", "jointMRL3",
        # MROLF extended: jointFFL/jointFFR (far front), jointBBL/jointBBR (far back)
        "jointFFL", "jointFFR", "jointBBL", "jointBBR",
        # MROLF X/Y variants (rotation axis indicators)
        "jointFLX", "jointFRX", "jointBLX", "jointBRX",
        "jointFLY", "jointFRY", "jointBLY", "jointBRY",
        "jointFLLX", "jointFRLX", "jointBLLX", "jointBRLX",
        "jointFLLY", "jointFRLY", "jointBLLY", "jointBRLY",
        "jointMLLX", "jointMRLX", "jointMLLY", "jointMRLY",
        "jointFFLLX", "jointFFRLX", "jointBBLLX", "jointBBRLX",
        "jointFFLLY", "jointFFRLY", "jointBBLLY", "jointBBRLY",
        "jointLLX", "jointRLX", "jointLLY", "jointRLY",
        # Tentacle/appendage legs
        "taclejointL", "taclejointR",
    )
    arm_patterns: Tuple[str, ...] = (
        "arm", "hand", "elbow", "wrist", "shoulder",
        # MROLF biped: jointLA/jointRA (arm left/right)
        "jointLA", "jointRA", "jointLA1", "jointRA1",
        "jointLA2", "jointRA2", "jointLA3", "jointRA3",
        "jointLA4", "jointRA4", "jointLAC", "jointRAC",
        "jointLAX", "jointRAX", "jointLAY", "jointRAY",
        "jointFLA", "jointFRA",
    )
    body_patterns: Tuple[str, ...] = (
        "body", "torso", "spine", "chest", "pelvis", "waist",
        "mainbody", "jointM",
    )
    head_patterns: Tuple[str, ...] = (
        "head", "neck", "jaw", "mouth", "snout",
        "jointh", "jointH",
    )

    def round_time(self, t: float) -> float:
        """Round a time value to the configured precision."""
        return round(t, self.rounding_time)

    def round_value(self, v: float) -> float:
        """Round a rotation/position value to the configured precision."""
        return round(v, self.rounding_value)
