"""Animation Profiler

Analyzes parsed animation data to generate profiles that guide pipeline
selection, parameter tuning, and deduplication.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Dict, List, Optional, Tuple

from .config import AnimForgeConfig
from .parser import ParsedAnimation, Keyframes
from .profile import AnimCategory, BoneRole, BoneProfile, AnimationProfile


class AnimationProfiler:
    """Generates AnimationProfile from ParsedAnimation data.

    Performs:
    - Category classification from animation name
    - Bone role detection (leg, arm, body, head)
    - Periodicity detection via autocorrelation
    - Walk-specific analysis (phase, half-cycle)
    - Content hash for deduplication
    """

    def __init__(self, config: AnimForgeConfig | None = None) -> None:
        self.config = config or AnimForgeConfig()

    def profile(self, anim: ParsedAnimation) -> AnimationProfile:
        """Generate a complete profile for the given animation.

        Args:
            anim: Parsed animation data.

        Returns:
            AnimationProfile with all detected characteristics.
        """
        profile = AnimationProfile(
            name=anim.name,
            loop=anim.loop,
            length=anim.length,
            total_keyframes=anim.total_keyframes,
            bone_count=len(anim.bone_channels),
        )

        # 1. Classify category
        profile.category = self._classify_category(anim.name, anim.length)

        # 2. Profile each bone
        profile.bones = self._profile_bones(anim)
        profile.max_rotation_amplitude = max(
            (bp.rotation_amplitude for bp in profile.bones.values()), default=0.0
        )

        # 3. Detect periodicity
        is_periodic, period = self._detect_periodicity(anim)
        profile.is_periodic = is_periodic
        profile.estimated_period = period

        # 4. Walk-specific analysis
        if profile.category == AnimCategory.WALK:
            profile.walk_phase = self._detect_walk_phase(anim, profile)
            profile.is_half_cycle = self._detect_half_cycle(anim, profile)

        # 5. Content hash for dedup
        profile.content_hash = self._compute_content_hash(anim)

        # 6. Detect dominant interpolation
        profile.interpolation = self._detect_interpolation(anim)

        return profile

    def _classify_category(self, name: str, length: float) -> AnimCategory:
        """Classify animation category from its name.

        Priority order: walk > attack > evolved > death > sleep > idle > unknown
        """
        name_lower = name.lower()

        # Walk patterns
        walk_keywords = ["walk", "run", "sprint", "strafe", "move", "gait"]
        for kw in walk_keywords:
            if kw in name_lower:
                if length <= self.config.walk_max_duration:
                    return AnimCategory.WALK

        # Attack patterns
        attack_keywords = ["attack", "hit", "strike", "slash", "punch", "kick", "shoot"]
        for kw in attack_keywords:
            if kw in name_lower:
                return AnimCategory.ATTACK

        # Evolved patterns
        evolved_keywords = ["evolve", "evolved", "evolution", "transform", "transforming"]
        for kw in evolved_keywords:
            if kw in name_lower:
                return AnimCategory.EVOLVED

        # Death patterns
        death_keywords = ["death", "die", "dead", "faint", "defeat", "ko"]
        for kw in death_keywords:
            if kw in name_lower:
                return AnimCategory.DEATH

        # Sleep patterns
        sleep_keywords = ["sleep", "rest", "slumber", "doze", "nap"]
        for kw in sleep_keywords:
            if kw in name_lower:
                return AnimCategory.SLEEP

        # Idle patterns (lower priority than walk)
        idle_keywords = ["idle", "stand", "breath", "ambient", "wait"]
        for kw in idle_keywords:
            if kw in name_lower:
                return AnimCategory.IDLE

        return AnimCategory.UNKNOWN

    def _profile_bones(self, anim: ParsedAnimation) -> Dict[str, BoneProfile]:
        """Create a BoneProfile for each animated bone."""
        profiles: Dict[str, BoneProfile] = {}

        for bone_name, channels in anim.bone_channels.items():
            bp = BoneProfile(name=bone_name)
            bp.role = self._detect_bone_role(bone_name)
            bp.is_left_side = self._is_left_side(bone_name)
            bp.is_right_side = self._is_right_side(bone_name)

            if "rotation" in channels:
                bp.has_rotation = True
                bp.rotation_kf_count = len(channels["rotation"])
                bp.rotation_amplitude = self._compute_amplitude(channels["rotation"])

            if "position" in channels:
                bp.has_position = True
                bp.position_kf_count = len(channels["position"])
                bp.position_amplitude = self._compute_amplitude(channels["position"])

            profiles[bone_name] = bp

        # Pair left/right bones
        self._pair_bones(profiles)

        return profiles

    def _detect_bone_role(self, name: str) -> BoneRole:
        """Detect the functional role of a bone from its name."""
        name_lower = name.lower()

        for pattern in self.config.leg_patterns:
            if pattern.lower() in name_lower:
                return BoneRole.LEG

        for pattern in self.config.arm_patterns:
            if pattern.lower() in name_lower:
                return BoneRole.ARM

        for pattern in self.config.head_patterns:
            if pattern.lower() in name_lower:
                return BoneRole.HEAD

        for pattern in self.config.body_patterns:
            if pattern.lower() in name_lower:
                return BoneRole.BODY

        return BoneRole.UNSPECIFIED

    @staticmethod
    def _is_left_side(name: str) -> bool:
        """Check if bone name suggests left side."""
        name_lower = name.lower()
        left_markers = ["left", "l", "ll", "lft"]
        parts = name_lower.replace("_", " ").replace(".", " ").split()
        return any(p in left_markers for p in parts) or name_lower.endswith("l")

    @staticmethod
    def _is_right_side(name: str) -> bool:
        """Check if bone name suggests right side."""
        name_lower = name.lower()
        right_markers = ["right", "r", "rr", "rgt"]
        parts = name_lower.replace("_", " ").replace(".", " ").split()
        return any(p in right_markers for p in parts) or name_lower.endswith("r")

    @staticmethod
    def _pair_bones(profiles: Dict[str, BoneProfile]) -> None:
        """Find and link left/right bone pairs."""
        names = list(profiles.keys())
        for i, name_a in enumerate(names):
            for name_b in names[i + 1:]:
                if profiles[name_a].paired_bone:
                    break
                if AnimationProfiler._are_paired(name_a, name_b):
                    profiles[name_a].paired_bone = name_b
                    profiles[name_b].paired_bone = name_a

    @staticmethod
    def _are_paired(name_a: str, name_b: str) -> bool:
        """Check if two bone names are left/right pairs."""
        a_lower = name_a.lower()
        b_lower = name_b.lower()

        # Try common substitutions
        pairs = [
            ("left", "right"), ("l", "r"), ("ll", "rr"), ("lft", "rgt"),
        ]
        for left_token, right_token in pairs:
            a_with_r = a_lower.replace(left_token, right_token)
            if a_with_r == b_lower:
                return True
            b_with_l = b_lower.replace(right_token, left_token)
            if b_with_l == a_lower:
                return True

        # Try single-character suffix (e.g., jointL / jointR)
        if len(a_lower) > 1 and len(b_lower) > 1:
            if a_lower[:-1] == b_lower[:-1]:
                suffix_a = a_lower[-1]
                suffix_b = b_lower[-1]
                if (suffix_a, suffix_b) in [("l", "r"), ("r", "l")]:
                    return True

        return False

    @staticmethod
    def _compute_amplitude(keyframes: Keyframes) -> float:
        """Compute peak-to-peak amplitude across all axes of keyframe data."""
        if not keyframes:
            return 0.0

        xs = [kf[1][0] for kf in keyframes]
        ys = [kf[1][1] for kf in keyframes]
        zs = [kf[1][2] for kf in keyframes]

        amp_x = max(xs) - min(xs) if xs else 0.0
        amp_y = max(ys) - min(ys) if ys else 0.0
        amp_z = max(zs) - min(zs) if zs else 0.0

        return max(amp_x, amp_y, amp_z)

    def _detect_periodicity(self, anim: ParsedAnimation) -> Tuple[bool, float]:
        """Detect if the animation is periodic using autocorrelation.

        Returns:
            (is_periodic, estimated_period)
        """
        # Use the highest-amplitude rotation channel for detection
        best_channel: Keyframes = []
        best_amp = 0.0

        for bone_name, channels in anim.bone_channels.items():
            for ch_name, kfs in channels.items():
                if ch_name != "rotation" or len(kfs) < 4:
                    continue
                amp = self._compute_amplitude(kfs)
                if amp > best_amp:
                    best_amp = amp
                    best_channel = kfs

        if len(best_channel) < 4 or best_amp < 1.0:
            return False, 0.0

        # Resample to uniform grid for autocorrelation
        duration = anim.length
        if duration <= 0:
            return False, 0.0

        n_samples = 64
        samples = self._resample_channel(best_channel, duration, n_samples)

        # Compute normalized autocorrelation
        autocorr = self._autocorrelation(samples)

        # Find peaks in autocorrelation
        peaks = self._find_peaks(autocorr)

        if len(peaks) >= self.config.autocorr_min_peaks:
            # Estimate period from first significant peak
            first_peak = peaks[0]
            period = (first_peak / n_samples) * duration
            return True, round(period, 4)

        return False, 0.0

    @staticmethod
    def _resample_channel(
        keyframes: Keyframes, duration: float, n_samples: int
    ) -> List[float]:
        """Resample a keyframe channel to a uniform time grid using linear interpolation.

        Uses the X component (primary rotation axis) of the keyframe values.
        """
        if not keyframes or duration <= 0:
            return [0.0] * n_samples

        times = [kf[0] for kf in keyframes]
        values = [kf[1][0] for kf in keyframes]  # Use X axis

        samples: List[float] = []
        for i in range(n_samples):
            t = (i / (n_samples - 1)) * duration
            # Linear interpolation
            if t <= times[0]:
                samples.append(values[0])
            elif t >= times[-1]:
                samples.append(values[-1])
            else:
                for j in range(len(times) - 1):
                    if times[j] <= t <= times[j + 1]:
                        frac = (t - times[j]) / (times[j + 1] - times[j]) if times[j + 1] != times[j] else 0.0
                        v = values[j] + frac * (values[j + 1] - values[j])
                        samples.append(v)
                        break
                else:
                    samples.append(values[-1])

        return samples

    @staticmethod
    def _autocorrelation(samples: List[float]) -> List[float]:
        """Compute normalized autocorrelation of a signal."""
        n = len(samples)
        mean = sum(samples) / n
        centered = [s - mean for s in samples]

        # Compute variance
        variance = sum(s * s for s in centered)
        if variance < 1e-10:
            return [0.0] * n

        result: List[float] = []
        for lag in range(n):
            corr = 0.0
            count = 0
            for i in range(n - lag):
                corr += centered[i] * centered[i + lag]
                count += 1
            if count > 0:
                result.append(corr / variance)
            else:
                result.append(0.0)

        return result

    def _find_peaks(self, autocorr: List[float]) -> List[int]:
        """Find peaks in autocorrelation function above threshold."""
        threshold = self.config.autocorr_threshold
        peaks: List[int] = []

        # Skip lag 0 (always 1.0) and very small lags
        min_lag = max(2, len(autocorr) // 20)

        for i in range(min_lag, len(autocorr) - 1):
            if autocorr[i] > threshold:
                # Check if this is a local maximum
                if autocorr[i] >= autocorr[i - 1] and autocorr[i] >= autocorr[i + 1]:
                    peaks.append(i)

        return peaks

    def _detect_walk_phase(
        self, anim: ParsedAnimation, profile: AnimationProfile
    ) -> Dict[str, float]:
        """Detect phase offsets between leg bones for walk analysis.

        Returns:
            Dict mapping bone name to phase offset (0.0 to 1.0).
        """
        leg_bones = profile.leg_bones
        if len(leg_bones) < 2:
            return {bone: 0.0 for bone in leg_bones}

        # Use the first leg bone as reference
        ref_bone = leg_bones[0]
        ref_kfs = anim.get_channel(ref_bone, "rotation")
        if len(ref_kfs) < 3:
            return {bone: 0.0 for bone in leg_bones}

        phases: Dict[str, float] = {ref_bone: 0.0}
        duration = anim.length if anim.length > 0 else 1.0

        for bone_name in leg_bones[1:]:
            bone_kfs = anim.get_channel(bone_name, "rotation")
            if len(bone_kfs) < 3:
                phases[bone_name] = 0.0
                continue

            # Cross-correlate to find phase offset
            offset = self._cross_correlate_phase(ref_kfs, bone_kfs, duration)
            phases[bone_name] = offset

        return phases

    def _cross_correlate_phase(
        self, ref_kfs: Keyframes, target_kfs: Keyframes, duration: float
    ) -> float:
        """Estimate phase offset between two channels using cross-correlation."""
        n_samples = 64
        ref_samples = self._resample_channel(ref_kfs, duration, n_samples)
        tgt_samples = self._resample_channel(target_kfs, duration, n_samples)

        # Normalize
        ref_mean = sum(ref_samples) / len(ref_samples)
        tgt_mean = sum(tgt_samples) / len(tgt_samples)
        ref_centered = [s - ref_mean for s in ref_samples]
        tgt_centered = [s - tgt_mean for s in tgt_samples]

        ref_energy = sum(s * s for s in ref_centered)
        tgt_energy = sum(s * s for s in tgt_centered)

        if ref_energy < 1e-10 or tgt_energy < 1e-10:
            return 0.0

        best_corr = -1.0
        best_lag = 0

        for lag in range(n_samples):
            corr = 0.0
            count = 0
            for i in range(n_samples):
                j = (i + lag) % n_samples
                corr += ref_centered[i] * tgt_centered[j]
                count += 1
            if count > 0:
                norm_corr = corr / math.sqrt(ref_energy * tgt_energy)
                if norm_corr > best_corr:
                    best_corr = norm_corr
                    best_lag = lag

        # Convert lag to phase (0.0 to 1.0)
        return best_lag / n_samples

    def _detect_half_cycle(
        self, anim: ParsedAnimation, profile: AnimationProfile
    ) -> bool:
        """Detect if the animation only contains half a gait cycle.

        Checks if the first half and second half of a walk animation are
        mirror images of each other (which would indicate a full cycle is
        present). If they're NOT mirrors and the duration is short,
        it's likely only half a cycle.
        """
        if not profile.is_periodic:
            # If not periodic, check if start matches end
            leg_bones = profile.leg_bones
            if not leg_bones:
                return False

            ref_bone = leg_bones[0]
            ref_kfs = anim.get_channel(ref_bone, "rotation")
            if len(ref_kfs) < 2:
                return False

            # If start ≈ end, it's a complete cycle
            start_val = ref_kfs[0][1]
            end_val = ref_kfs[-1][1]
            diff = max(abs(start_val[i] - end_val[i]) for i in range(3))
            if diff < self.config.c0_threshold * 10:  # Looser than C0
                return False  # Complete cycle

            # Short duration with mismatched start/end suggests half cycle
            return anim.length < 0.5

        # For periodic animations, check half-cycle similarity
        duration = anim.length
        leg_bones = profile.leg_bones
        if not leg_bones:
            return False

        ref_bone = leg_bones[0]
        ref_kfs = anim.get_channel(ref_bone, "rotation")
        if len(ref_kfs) < 6:
            return False

        # Compare first half and second half
        half_duration = duration / 2.0
        first_half = [kf for kf in ref_kfs if kf[0] <= half_duration]
        second_half = [kf for kf in ref_kfs if kf[0] > half_duration]

        if not first_half or not second_half:
            return False

        # Resample both halves and compare
        n = 32
        first_samples = self._resample_channel(first_half, half_duration, n)
        # Shift second half times to start from 0
        shifted_second = [(kf[0] - half_duration, kf[1]) for kf in second_half]
        second_samples = self._resample_channel(shifted_second, half_duration, n)

        # Compute similarity
        similarity = self._compute_similarity(first_samples, second_samples)
        return similarity < self.config.half_cycle_similarity

    @staticmethod
    def _compute_similarity(a: List[float], b: List[float]) -> float:
        """Compute normalized similarity between two signals (1.0 = identical)."""
        if len(a) != len(b) or not a:
            return 0.0

        n = len(a)
        mean_a = sum(a) / n
        mean_b = sum(b) / n

        num = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
        den_a = sum((a[i] - mean_a) ** 2 for i in range(n))
        den_b = sum((b[i] - mean_b) ** 2 for i in range(n))

        if den_a < 1e-10 or den_b < 1e-10:
            return 1.0 if mean_a == mean_b else 0.0

        corr = num / math.sqrt(den_a * den_b)
        # Convert correlation [-1, 1] to similarity [0, 1]
        return (corr + 1.0) / 2.0

    def _compute_content_hash(self, anim: ParsedAnimation) -> str:
        """Compute a content-based hash for deduplication.

        Uses rounded keyframe data to detect byte-identical animations.
        """
        precision = self.config.dedup_hash_precision
        parts: List[str] = []

        # Include bone names, channels, and keyframe data
        for bone_name in sorted(anim.bone_channels.keys()):
            channels = anim.bone_channels[bone_name]
            for ch_name in sorted(channels.keys()):
                kfs = channels[ch_name]
                for t, (x, y, z) in kfs:
                    parts.append(f"{bone_name}:{ch_name}:{round(t, precision)}:{round(x, precision)}:{round(y, precision)}:{round(z, precision)}")

        content = "|".join(parts)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def _detect_interpolation(self, anim: ParsedAnimation) -> str:
        """Detect the dominant interpolation type from keyframes."""
        interp_counts: Dict[str, int] = {}

        for animator_data in anim.animators.values():
            if not isinstance(animator_data, dict):
                continue
            for kf in animator_data.get("keyframes", []):
                interp = kf.get("interpolation", "linear")
                interp_counts[interp] = interp_counts.get(interp, 0) + 1

        if not interp_counts:
            return "linear"

        return max(interp_counts, key=interp_counts.get)  # type: ignore[arg-type]
