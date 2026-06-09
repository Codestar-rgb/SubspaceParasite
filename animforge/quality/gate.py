"""Quality Gate

Validates that processing didn't degrade animation quality beyond acceptable
thresholds. Checks:
- Keyframe density must not drop below 50%
- Walk leg bones must have >= min_kf keyframes
- Amplitude fidelity must not drop below 70%
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..core.config import AnimForgeConfig
from ..core.parser import ParsedAnimation
from ..core.profile import AnimationProfile, BoneRole, AnimCategory
from .report import QualityReporter, QualityReport


@dataclass
class GateResult:
    """Result of quality gate validation.

    Attributes:
        passed: Whether the animation passed all quality checks.
        failures: List of (check_name, description) for failed checks.
        warnings: List of (check_name, description) for marginal results.
        report: Detailed quality report.
    """
    passed: bool = True
    failures: List[Tuple[str, str]] = field(default_factory=list)
    warnings: List[Tuple[str, str]] = field(default_factory=list)
    report: Optional[QualityReport] = None


class QualityGate:
    """Validates that processing didn't degrade animation quality.

    Each check produces either a pass, warning, or failure. The overall
    result is a failure if any check fails.
    """

    def __init__(self, config: AnimForgeConfig | None = None) -> None:
        self.config = config or AnimForgeConfig()
        self.reporter = QualityReporter(self.config)

    def validate(
        self,
        original: ParsedAnimation,
        processed: ParsedAnimation,
        profile: AnimationProfile,
    ) -> GateResult:
        """Validate processed animation against original.

        Args:
            original: The pre-processing animation data.
            processed: The post-processing animation data.
            profile: Animation profile with bone roles.

        Returns:
            GateResult with pass/fail status and details.
        """
        result = GateResult()

        # Generate quality report
        result.report = self.reporter.report(original, processed, profile)

        # Check 1: Keyframe density
        self._check_kf_density(original, processed, profile, result)

        # Check 2: Walk leg minimum keyframes
        if profile.category == AnimCategory.WALK:
            self._check_walk_leg_min_kf(processed, profile, result)

        # Check 3: Amplitude fidelity
        self._check_amplitude_fidelity(original, processed, profile, result)

        # Check 4: C0 continuity (for loop animations)
        if profile.is_loop:
            self._check_c0_continuity(processed, profile, result)

        return result

    def _check_kf_density(
        self,
        original: ParsedAnimation,
        processed: ParsedAnimation,
        profile: AnimationProfile,
        result: GateResult,
    ) -> None:
        """Check that keyframe density hasn't dropped below threshold."""
        for bone_name in original.bone_channels:
            if bone_name not in processed.bone_channels:
                result.failures.append((
                    "kf_density",
                    f"Bone '{bone_name}' missing in processed animation"
                ))
                result.passed = False
                continue

            for ch_name in original.bone_channels[bone_name]:
                orig_count = len(original.bone_channels[bone_name][ch_name])
                proc_kfs = processed.bone_channels[bone_name].get(ch_name, [])
                proc_count = len(proc_kfs)

                if orig_count == 0:
                    continue

                ratio = proc_count / orig_count
                threshold = self.config.min_kf_density_threshold

                if ratio < threshold:
                    result.failures.append((
                        "kf_density",
                        f"Bone '{bone_name}' channel '{ch_name}': "
                        f"KF density {ratio:.1%} below threshold {threshold:.1%} "
                        f"({proc_count}/{orig_count})"
                    ))
                    result.passed = False
                elif ratio < threshold * 1.2:
                    result.warnings.append((
                        "kf_density",
                        f"Bone '{bone_name}' channel '{ch_name}': "
                        f"KF density {ratio:.1%} near threshold "
                        f"({proc_count}/{orig_count})"
                    ))

    def _check_walk_leg_min_kf(
        self,
        processed: ParsedAnimation,
        profile: AnimationProfile,
        result: GateResult,
    ) -> None:
        """Check that walk leg bones have minimum required keyframes."""
        min_kf = self.config.min_kf_walk_leg

        for bone_name in profile.leg_bones:
            if bone_name not in processed.bone_channels:
                continue

            for ch_name in processed.bone_channels[bone_name]:
                count = len(processed.bone_channels[bone_name][ch_name])
                if count < min_kf:
                    result.failures.append((
                        "walk_leg_min_kf",
                        f"Walk leg '{bone_name}' channel '{ch_name}': "
                        f"{count} keyframes below minimum {min_kf}"
                    ))
                    result.passed = False

    def _check_amplitude_fidelity(
        self,
        original: ParsedAnimation,
        processed: ParsedAnimation,
        profile: AnimationProfile,
        result: GateResult,
    ) -> None:
        """Check that amplitude hasn't been reduced below threshold."""
        threshold = self.config.amplitude_fidelity_threshold

        for bone_name in original.bone_channels:
            if bone_name not in processed.bone_channels:
                continue

            for ch_name in original.bone_channels[bone_name]:
                orig_kfs = original.bone_channels[bone_name][ch_name]
                proc_kfs = processed.bone_channels[bone_name].get(ch_name, [])

                orig_amp = self._compute_amplitude(orig_kfs)
                proc_amp = self._compute_amplitude(proc_kfs)

                if orig_amp < 1e-6:
                    continue  # Negligible original amplitude

                ratio = proc_amp / orig_amp
                if ratio < threshold:
                    result.failures.append((
                        "amplitude_fidelity",
                        f"Bone '{bone_name}' channel '{ch_name}': "
                        f"Amplitude fidelity {ratio:.1%} below threshold {threshold:.1%} "
                        f"({proc_amp:.2f}/{orig_amp:.2f})"
                    ))
                    result.passed = False

    def _check_c0_continuity(
        self,
        processed: ParsedAnimation,
        profile: AnimationProfile,
        result: GateResult,
    ) -> None:
        """Check C0 continuity for loop animations."""
        threshold = self.config.c0_threshold

        for bone_name, channels in processed.bone_channels.items():
            for ch_name, kfs in channels.items():
                if len(kfs) < 2:
                    continue

                start_val = kfs[0][1]
                end_val = kfs[-1][1]
                max_diff = max(abs(start_val[i] - end_val[i]) for i in range(3))

                if max_diff > threshold * 10:  # Allow 10x the strict C0 threshold
                    result.warnings.append((
                        "c0_continuity",
                        f"Bone '{bone_name}' channel '{ch_name}': "
                        f"C0 error {max_diff:.4f} exceeds threshold {threshold * 10:.4f}"
                    ))

    @staticmethod
    def _compute_amplitude(keyframes) -> float:
        """Compute peak-to-peak amplitude of keyframe data."""
        if not keyframes:
            return 0.0
        xs = [kf[1][0] for kf in keyframes]
        ys = [kf[1][1] for kf in keyframes]
        zs = [kf[1][2] for kf in keyframes]
        return max(
            max(xs) - min(xs),
            max(ys) - min(ys),
            max(zs) - min(zs),
        )
