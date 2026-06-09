"""Quality Reporter

Computes C0/C1 continuity errors and an overall health score for
processed animations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..core.config import AnimForgeConfig
from ..core.parser import ParsedAnimation, Keyframes
from ..core.profile import AnimationProfile, BoneRole, AnimCategory


@dataclass
class ChannelQuality:
    """Quality metrics for a single bone channel.

    Attributes:
        bone: Bone name.
        channel: Channel name (rotation/position).
        original_kf_count: Keyframe count before processing.
        processed_kf_count: Keyframe count after processing.
        kf_density_ratio: processed_kf_count / original_kf_count.
        original_amplitude: Amplitude before processing.
        processed_amplitude: Amplitude after processing.
        amplitude_fidelity: processed_amplitude / original_amplitude.
        c0_error: C0 continuity error (max component diff between first and last KF).
        c1_error: C1 continuity error (velocity mismatch at loop boundary).
    """
    bone: str = ""
    channel: str = ""
    original_kf_count: int = 0
    processed_kf_count: int = 0
    kf_density_ratio: float = 1.0
    original_amplitude: float = 0.0
    processed_amplitude: float = 0.0
    amplitude_fidelity: float = 1.0
    c0_error: float = 0.0
    c1_error: float = 0.0


@dataclass
class QualityReport:
    """Complete quality report for a processed animation.

    Attributes:
        animation_name: Name of the animation.
        category: Animation category.
        channels: Per-channel quality metrics.
        overall_health: Overall health score (0.0 to 1.0).
        worst_c0_error: Worst C0 error across all channels.
        worst_c1_error: Worst C1 error across all channels.
        avg_density_ratio: Average keyframe density ratio.
        avg_amplitude_fidelity: Average amplitude fidelity.
    """
    animation_name: str = ""
    category: AnimCategory = AnimCategory.UNKNOWN
    channels: List[ChannelQuality] = field(default_factory=list)
    overall_health: float = 1.0
    worst_c0_error: float = 0.0
    worst_c1_error: float = 0.0
    avg_density_ratio: float = 1.0
    avg_amplitude_fidelity: float = 1.0


class QualityReporter:
    """Computes quality metrics for processed animations.

    Generates a QualityReport with per-channel and overall metrics,
    including C0/C1 continuity errors and an overall health score.
    """

    def __init__(self, config: AnimForgeConfig | None = None) -> None:
        self.config = config or AnimForgeConfig()

    def report(
        self,
        original: ParsedAnimation,
        processed: ParsedAnimation,
        profile: AnimationProfile,
    ) -> QualityReport:
        """Generate a quality report comparing processed to original.

        Args:
            original: Pre-processing animation data.
            processed: Post-processing animation data.
            profile: Animation profile.

        Returns:
            QualityReport with detailed metrics.
        """
        rpt = QualityReport(
            animation_name=processed.name,
            category=profile.category,
        )

        # Compute per-channel metrics
        for bone_name in original.bone_channels:
            for ch_name in original.bone_channels[bone_name]:
                ch_quality = self._assess_channel(
                    bone_name,
                    ch_name,
                    original,
                    processed,
                    profile,
                )
                rpt.channels.append(ch_quality)

        # Compute aggregate metrics
        if rpt.channels:
            density_ratios = [ch.kf_density_ratio for ch in rpt.channels if ch.original_kf_count > 0]
            amp_fidelities = [ch.amplitude_fidelity for ch in rpt.channels if ch.original_amplitude > 0]
            c0_errors = [ch.c0_error for ch in rpt.channels]
            c1_errors = [ch.c1_error for ch in rpt.channels if profile.is_loop]

            rpt.avg_density_ratio = sum(density_ratios) / len(density_ratios) if density_ratios else 1.0
            rpt.avg_amplitude_fidelity = sum(amp_fidelities) / len(amp_fidelities) if amp_fidelities else 1.0
            rpt.worst_c0_error = max(c0_errors) if c0_errors else 0.0
            rpt.worst_c1_error = max(c1_errors) if c1_errors else 0.0

        # Compute overall health score
        rpt.overall_health = self._compute_health_score(rpt)

        return rpt

    def _assess_channel(
        self,
        bone_name: str,
        ch_name: str,
        original: ParsedAnimation,
        processed: ParsedAnimation,
        profile: AnimationProfile,
    ) -> ChannelQuality:
        """Assess quality metrics for a single bone channel."""
        ch = ChannelQuality(bone=bone_name, channel=ch_name)

        orig_kfs = original.bone_channels[bone_name][ch_name]
        proc_kfs = processed.bone_channels.get(bone_name, {}).get(ch_name, [])

        ch.original_kf_count = len(orig_kfs)
        ch.processed_kf_count = len(proc_kfs)

        # Keyframe density
        if ch.original_kf_count > 0:
            ch.kf_density_ratio = ch.processed_kf_count / ch.original_kf_count

        # Amplitude
        ch.original_amplitude = self._compute_amplitude(orig_kfs)
        ch.processed_amplitude = self._compute_amplitude(proc_kfs)
        if ch.original_amplitude > 1e-6:
            ch.amplitude_fidelity = ch.processed_amplitude / ch.original_amplitude

        # C0 error
        if profile.is_loop and len(proc_kfs) >= 2:
            start = proc_kfs[0][1]
            end = proc_kfs[-1][1]
            ch.c0_error = max(abs(start[i] - end[i]) for i in range(3))

        # C1 error (for loop animations)
        if profile.is_loop and len(proc_kfs) >= 3:
            ch.c1_error = self._compute_c1_error(proc_kfs, processed.length)

        return ch

    @staticmethod
    def _compute_amplitude(keyframes: Keyframes) -> float:
        """Compute peak-to-peak amplitude."""
        if not keyframes:
            return 0.0
        xs = [kf[1][0] for kf in keyframes]
        ys = [kf[1][1] for kf in keyframes]
        zs = [kf[1][2] for kf in keyframes]
        return max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))

    @staticmethod
    def _compute_c1_error(keyframes: Keyframes, duration: float) -> float:
        """Compute C1 velocity mismatch at loop boundary."""
        if len(keyframes) < 3 or duration <= 0:
            return 0.0

        # Velocity at end (backward difference)
        dt_end = keyframes[-1][0] - keyframes[-2][0]
        if dt_end < 1e-10:
            vel_end = (0.0, 0.0, 0.0)
        else:
            vel_end = tuple(
                (keyframes[-1][1][i] - keyframes[-2][1][i]) / dt_end
                for i in range(3)
            )

        # Velocity at start (forward difference)
        dt_start = keyframes[1][0] - keyframes[0][0]
        if dt_start < 1e-10:
            vel_start = (0.0, 0.0, 0.0)
        else:
            vel_start = tuple(
                (keyframes[1][1][i] - keyframes[0][1][i]) / dt_start
                for i in range(3)
            )

        # Maximum component-wise velocity mismatch
        return max(abs(vel_end[i] - vel_start[i]) for i in range(3))

    def _compute_health_score(self, report: QualityReport) -> float:
        """Compute overall health score (0.0 to 1.0).

        Factors:
        - C0 continuity (most important for loops)
        - Keyframe density preservation
        - Amplitude fidelity
        - C1 continuity (for loops)
        """
        score = 1.0

        # C0 penalty
        c0_threshold = self.config.c0_threshold * 10  # Allow 10x for scoring
        if report.worst_c0_error > c0_threshold:
            c0_penalty = min(0.3, (report.worst_c0_error - c0_threshold) / 10.0)
            score -= c0_penalty

        # Density penalty
        if report.avg_density_ratio < self.config.min_kf_density_threshold:
            density_penalty = (self.config.min_kf_density_threshold - report.avg_density_ratio) * 0.3
            score -= density_penalty

        # Amplitude penalty
        if report.avg_amplitude_fidelity < self.config.amplitude_fidelity_threshold:
            amp_penalty = (self.config.amplitude_fidelity_threshold - report.avg_amplitude_fidelity) * 0.3
            score -= amp_penalty

        # C1 penalty (for loops)
        if report.worst_c1_error > 50.0:  # 50 deg/s is quite noticeable
            c1_penalty = min(0.2, (report.worst_c1_error - 50.0) / 100.0)
            score -= c1_penalty

        return max(0.0, min(1.0, score))
