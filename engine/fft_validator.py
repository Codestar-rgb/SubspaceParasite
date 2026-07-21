"""
FFT Sampling Validator (v6.9.17)

Validates MVE-captured animation data against Java source frequencies.
For each bone axis, performs FFT on the captured keyframes and compares
the dominant frequency with the frequency extracted from the Java source
expression. Reports deviations > 5%.

Usage:
    from engine.fft_validator import validate_animation_frequencies
    issues = validate_animation_frequencies(animations, model_name)
"""

import logging
import math
import re
import numpy as np
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

DEVIATION_THRESHOLD = 0.05  # 5%


def _extract_java_frequency(expr: str, variables: dict) -> Optional[float]:
    """Extract the frequency (rad/tick) from a Java trig expression.

    Looks for ageInTicks * FREQ or limbSwing * FREQ patterns.
    Returns the frequency multiplier (e.g., 0.1 from ageInTicks * 0.1f).
    """
    # Resolve variables first
    from engine.java_trig_simulator import _resolve_expr
    resolved = _resolve_expr(expr, variables)

    # Find ageInTicks * <float> or limbSwing * <float>
    freq_patterns = [
        r'ageInTicks\s*\*\s*([\d.]+)',
        r'limbSwing\s*\*\s*([\d.]+)',
    ]
    for pat in freq_patterns:
        m = re.search(pat, resolved)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass

    # Check for compound: ageInTicks * 0.3f * 0.15f
    m = re.search(r'ageInTicks\s*\*\s*([\d.]+)\s*\*\s*([\d.]+)', resolved)
    if m:
        try:
            return float(m.group(1)) * float(m.group(2))
        except ValueError:
            pass

    return None


def _fft_dominant_frequency(times: np.ndarray, values: np.ndarray) -> Optional[float]:
    """Compute dominant frequency via FFT.

    Returns frequency in rad/tick.
    """
    n = len(values)
    if n < 4:
        return None

    dc = float(np.mean(values))
    ac = values - dc
    amp = float(np.max(np.abs(ac)))
    if amp < 0.01:
        return None

    dt = float((times[-1] - times[0]) / (n - 1)) if n > 1 else 1.0
    if dt <= 0:
        return None

    fft = np.fft.rfft(ac)
    freqs_hz = np.fft.rfftfreq(n, d=dt)
    mags = np.abs(fft)

    if len(mags) <= 1:
        return None

    peak_idx = np.argmax(mags[1:]) + 1
    freq_hz = float(freqs_hz[peak_idx])

    # Convert Hz (cycles/sec) to rad/tick: freq_hz * 2*pi / 20
    return freq_hz * 2 * math.pi / 20.0


def validate_animation_frequencies(animations: list, model_name: str = "") -> List[dict]:
    """Validate MVE-captured frequencies against Java source.

    Args:
        animations: List of AnimationIR objects.
        model_name: Model name for logging.

    Returns:
        List of issue dicts with bone, axis, java_freq, captured_freq, deviation.
    """
    issues = []
    from engine.java_analyzer import analyze_model
    from engine.mve_data_loader import get_mve_animations_for_model, has_mve_data
    import config

    # Load Java source for frequency extraction
    meta = analyze_model(model_name, config.DECOMPILED_DIR) if model_name else None
    if not meta:
        return issues

    # Collect Java frequencies from all states
    java_freqs = {}  # (bone, axis) -> freq
    from engine.java_analyzer import _resolve_variables, _extract_all_anim_assignments, _follow_custom_methods
    import re as re_mod

    for state in meta.states:
        with open(meta.java_path, 'r', encoding='utf-8') as f:
            java_src = f.read()
        inlined = _follow_custom_methods(java_src, state.body)
        variables = _resolve_variables(inlined)
        assignments = _extract_all_anim_assignments(inlined)

        axis_map = {'field_78795_f': 'x', 'field_78796_g': 'y', 'field_78808_h': 'z'}
        for a in assignments:
            ax = axis_map.get(a.field, '')
            if not ax:
                continue
            freq = _extract_java_frequency(a.expression, variables)
            if freq and freq > 0:
                key = (a.bone, ax)
                if key not in java_freqs:
                    java_freqs[key] = freq

    # Check each animation's captured frequencies
    for anim in animations:
        for bname, bone_anim in anim.bones.items():
            rot_kfs = [kf for kf in bone_anim.keyframes if kf.channel == 'rotation']
            if len(rot_kfs) < 8:
                continue

            times = np.array([kf.time for kf in sorted(rot_kfs, key=lambda k: k.time)])
            for ax in ('x', 'y', 'z'):
                vals = np.array([getattr(kf, ax).value for kf in sorted(rot_kfs, key=lambda k: k.time)])
                amp = vals.max() - vals.min()
                if amp < 0.5:
                    continue

                key = (bname, ax)
                if key not in java_freqs:
                    continue

                java_freq = java_freqs[key]
                captured_freq = _fft_dominant_frequency(times, vals)

                if captured_freq and java_freq > 0:
                    deviation = abs(captured_freq - java_freq) / java_freq
                    if deviation > DEVIATION_THRESHOLD:
                        issues.append({
                            'animation': anim.name,
                            'bone': bname,
                            'axis': ax,
                            'java_freq': java_freq,
                            'captured_freq': captured_freq,
                            'deviation': deviation,
                        })
                        logger.warning(
                            "[%s] %s %s.%s: Java freq=%.5f, captured=%.5f, deviation=%.1f%%",
                            model_name, anim.name, bname, ax,
                            java_freq, captured_freq, deviation * 100,
                        )

    if issues:
        logger.warning("[%s] FFT validation found %d frequency deviations", model_name, len(issues))
    else:
        logger.debug("[%s] FFT validation passed (no deviations)", model_name)

    return issues
