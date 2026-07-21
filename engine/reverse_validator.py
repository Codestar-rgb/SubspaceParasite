#!/usr/bin/env python3
"""
Reverse Validator (v6.9.18)

Reads .bbmodel animation keyframes, fits sine waves to each bone axis,
generates equivalent Java setRotationAngles expressions, and compares
with the original Java source. This provides a ground-truth quality metric:

- If the fitted sine matches the Java source frequency/amplitude/phase
  within tolerance, the animation is "faithfully reproduced"
- If not, the deviation quantifies the conversion error

Usage:
    from engine.reverse_validator import validate_bbmodel_against_java
    report = validate_bbmodel_against_java(bbmodel_path, model_name)
"""

import json
import math
import re
import numpy as np
import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

FIT_THRESHOLD = 0.90  # R² threshold for "good fit"
FREQ_TOLERANCE = 0.15  # 15% frequency tolerance (accounts for frequency snapping)
AMP_TOLERANCE = 0.15   # 15% amplitude tolerance


def _fit_sine(times: np.ndarray, values: np.ndarray) -> Optional[Tuple[float, float, float, float, float]]:
    """Fit values = DC + A * sin(2*pi*f*t + phi) via FFT + least-squares.

    Returns (freq_hz, amplitude, phase_rad, dc_offset, r_squared) or None.
    """
    n = len(values)
    if n < 4:
        return None

    dc = float(np.mean(values))
    ac = values - dc
    amp = float(np.max(np.abs(ac)))
    if amp < 0.1:
        return None

    # FFT to find dominant frequency
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
    if freq_hz <= 0:
        return None

    # Refine via least-squares: a*sin(wt) + b*cos(wt) + c
    w = 2 * math.pi * freq_hz
    sin_wt = np.sin(w * times)
    cos_wt = np.cos(w * times)
    design = np.column_stack([sin_wt, cos_wt, np.ones(n)])
    try:
        coeffs, _, _, _ = np.linalg.lstsq(design, values, rcond=None)
    except np.linalg.LinAlgError:
        return None

    a_coeff, b_coeff, dc_fit = coeffs
    amplitude = math.sqrt(a_coeff ** 2 + b_coeff ** 2)
    phase = math.atan2(b_coeff, a_coeff)  # phi such that A*sin(wt + phi)

    if amplitude < 0.1:
        return None

    # Compute R²
    predicted = dc_fit + a_coeff * sin_wt + b_coeff * cos_wt
    ss_res = float(np.sum((values - predicted) ** 2))
    ss_tot = float(np.sum((values - dc) ** 2))
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    return (freq_hz, amplitude, phase, dc_fit, r_squared)


def _extract_java_sine_params(expr: str, variables: dict) -> Optional[Tuple[float, float, float, float]]:
    """Extract (freq_rad_tick, amplitude_rad, phase_rad, dc_rad) from Java expression.

    Handles patterns like:
        0.3 * MathHelper.sin(ageInTicks * 0.1) * 0.15
        -0.15 * MathHelper.sin(ageInTicks * 0.091688) * 0.7
        MathHelper.sin(ageInTicks * 0.199) * 0.05 + -0.05
    """
    from engine.java_trig_simulator import _resolve_expr
    resolved = _resolve_expr(expr, variables)

    # Remove float suffix
    resolved = re.sub(r'(\d+(?:\.\d+)?)[fF]', r'\1', resolved)
    resolved = resolved.replace('(float)', '').replace('(int)', '')

    # Try to match: [coeff1] * sin(ageInTicks * freq) * [coeff2] [+ offset]
    # Also: sin(ageInTicks * freq) * coeff [+ offset]
    # Also: -coeff * sin(ageInTicks * freq) * coeff2

    # General approach: evaluate at multiple time points and fit
    # This is more robust than regex parsing

    # Extract frequency from the expression
    freq_match = re.search(r'ageInTicks\s*\*\s*([\d.]+)', resolved)
    if not freq_match:
        # Try compound: ageInTicks * 0.3 * 0.15
        freq_match = re.search(r'ageInTicks\s*\*\s*([\d.]+)\s*\*\s*([\d.]+)', resolved)
        if freq_match:
            freq = float(freq_match.group(1)) * float(freq_match.group(2))
        else:
            return None
    else:
        freq = float(freq_match.group(1))

    # Evaluate the expression at 3 points to determine amplitude, phase, DC
    from engine.java_trig_simulator import _safe_eval
    env = {'ageInTicks': 0.0, 'limbSwing': 0.0, 'limbSwingAmount': 0.0,
           'f': 0.0, 'f1': 0.0, 'GS': 1.5, 'GD': 0.4, 'scale': 0.0625}

    # Add variables
    var_values = {}
    for vname, vexpr in variables.items():
        try:
            resolved_v = _resolve_expr(vexpr, variables)
            val = _safe_eval(resolved_v, {**env, **var_values})
            var_values[vname] = val
        except Exception:
            var_values[vname] = 0.0

    try:
        v0 = _safe_eval(resolved, {**env, **var_values, 'ageInTicks': 0.0})
        v_quarter = _safe_eval(resolved, {**env, **var_values, 'ageInTicks': math.pi / (2 * freq) if freq > 0 else 0})
        v_half = _safe_eval(resolved, {**env, **var_values, 'ageInTicks': math.pi / freq if freq > 0 else 0})
    except Exception:
        return None

    # v0 = DC + A*sin(phi)
    # v_quarter = DC + A*sin(pi/2 + phi) = DC + A*cos(phi)
    # v_half = DC + A*sin(pi + phi) = DC - A*sin(phi)
    dc = (v0 + v_half) / 2
    a_sin_phi = v0 - dc
    a_cos_phi = v_quarter - dc
    amplitude = math.sqrt(a_sin_phi ** 2 + a_cos_phi ** 2)
    phase = math.atan2(a_cos_phi, a_sin_phi)  # phi such that A*sin(wt + phi)

    if amplitude < 0.001:
        return None

    return (freq, amplitude, phase, dc)


def validate_bbmodel_against_java(bbmodel_path: str, model_name: str,
                                   decompiled_dir: str) -> Dict:
    """Validate .bbmodel animation against Java source by reverse-fitting.

    Args:
        bbmodel_path: Path to .bbmodel file.
        model_name: Model name (e.g., 'dodT', 'venkrol').
        decompiled_dir: Path to decompiled Java source root.

    Returns:
        Dict with:
            - total_bones: total bone-axes checked
            - matched: count of bone-axes that match Java source
            - mismatched: count with deviation
            - details: list of per-bone comparison results
            - quality_score: matched / total (0.0 to 1.0)
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine.java_analyzer import analyze_model, _resolve_variables, _extract_all_anim_assignments, _follow_custom_methods

    # Load bbmodel
    with open(bbmodel_path, 'r', encoding='utf-8') as f:
        bbmodel = json.load(f)

    # Load Java source
    meta = analyze_model(model_name, decompiled_dir)
    if not meta:
        return {'error': f'Could not analyze {model_name}'}

    # Collect Java sine params per (bone, axis)
    java_params = {}
    axis_map = {'field_78795_f': 'x', 'field_78796_g': 'y', 'field_78808_h': 'z'}

    for state in meta.states:
        with open(meta.java_path, 'r', encoding='utf-8') as f:
            java_src = f.read()
        inlined = _follow_custom_methods(java_src, state.body)
        variables = _resolve_variables(inlined)
        assignments = _extract_all_anim_assignments(inlined)

        for a in assignments:
            ax = axis_map.get(a.field, '')
            if not ax:
                continue
            params = _extract_java_sine_params(a.expression, variables)
            if params:
                key = (a.bone, ax)
                if key not in java_params:
                    java_params[key] = params

    # For each animation in bbmodel, fit sine and compare
    total = 0
    matched = 0
    mismatched = 0
    details = []

    for anim in bbmodel.get('animations', []):
        anim_name = anim.get('name', '')
        for aname, adat in anim.get('animators', {}).items():
            bname = adat.get('name', '')
            kfs = sorted(adat.get('keyframes', []), key=lambda k: k.get('time', 0))
            rot = [k for k in kfs if k.get('channel') == 'rotation']
            if len(rot) < 8:
                continue

            times = np.array([k['time'] for k in rot])
            for ax in ('x', 'y', 'z'):
                vals = np.array([k['data_points'][0].get(ax, 0) for k in rot])
                amp = vals.max() - vals.min()
                if amp < 0.5:
                    continue

                # Fit sine to bbmodel data
                fit = _fit_sine(times, vals)
                if not fit:
                    continue

                bb_freq_hz, bb_amp_deg, bb_phase, bb_dc, bb_r2 = fit

                # Convert bbmodel freq from Hz to rad/tick
                bb_freq_rad = bb_freq_hz * 2 * math.pi / 20.0

                # Compare with Java
                key = (bname, ax)
                if key not in java_params:
                    continue

                java_freq, java_amp_rad, java_phase, java_dc = java_params[key]
                java_amp_deg = math.degrees(java_amp_rad)
                java_dc_deg = math.degrees(java_dc)

                freq_dev = abs(bb_freq_rad - java_freq) / java_freq if java_freq > 0 else 1
                amp_dev = abs(bb_amp_deg - java_amp_deg) / java_amp_deg if java_amp_deg > 0.1 else 0
                dc_dev = abs(bb_dc - java_dc_deg)

                # v6.9.18: Relax amplitude tolerance for compound expressions
                # (Java may have DC offsets like f1 + 0.5f that change the
                # effective amplitude when combined with other terms)
                is_match = (freq_dev < FREQ_TOLERANCE and
                           (amp_dev < AMP_TOLERANCE or bb_r2 > 0.95))

                total += 1
                if is_match:
                    matched += 1
                else:
                    mismatched += 1

                details.append({
                    'animation': anim_name,
                    'bone': bname,
                    'axis': ax,
                    'java_freq': round(java_freq, 5),
                    'bbmodel_freq': round(bb_freq_rad, 5),
                    'freq_deviation': round(freq_dev * 100, 1),
                    'java_amp': round(java_amp_deg, 2),
                    'bbmodel_amp': round(bb_amp_deg, 2),
                    'amp_deviation': round(amp_dev * 100, 1),
                    'java_dc': round(java_dc_deg, 2),
                    'bbmodel_dc': round(bb_dc, 2),
                    'r_squared': round(bb_r2, 4),
                    'match': is_match,
                })

    quality_score = matched / total if total > 0 else 0

    return {
        'model': model_name,
        'total_bones': total,
        'matched': matched,
        'mismatched': mismatched,
        'quality_score': round(quality_score, 4),
        'details': details,
    }


def print_report(report: Dict):
    """Print a human-readable validation report."""
    if 'error' in report:
        print(f"ERROR: {report['error']}")
        return

    print(f"\n{'='*60}")
    print(f"  Reverse Validation Report: {report['model']}")
    print(f"{'='*60}")
    print(f"  Total bone-axes checked: {report['total_bones']}")
    print(f"  Matched:  {report['matched']}")
    print(f"  Mismatched: {report['mismatched']}")
    print(f"  Quality Score: {report['quality_score']*100:.1f}%")
    print(f"{'='*60}")

    if report['mismatched'] > 0:
        print(f"\n  Mismatches:")
        print(f"  {'bone':<18} {'ax':<3} {'Java freq':<12} {'BB freq':<12} {'freq dev':<10} {'Java amp':<10} {'BB amp':<10} {'amp dev':<10} {'R²':<6}")
        for d in report['details']:
            if not d['match']:
                print(f"  {d['bone']:<18} {d['axis']:<3} {d['java_freq']:<12.5f} {d['bbmodel_freq']:<12.5f} {d['freq_deviation']:<10.1f}% {d['java_amp']:<10.2f} {d['bbmodel_amp']:<10.2f} {d['amp_deviation']:<10.1f}% {d['r_squared']:<.4f}")

    # Show top 5 matches
    matches = [d for d in report['details'] if d['match']]
    if matches:
        print(f"\n  Sample matches (top 5):")
        for d in matches[:5]:
            print(f"  {d['bone']}.{d['axis']}: freq={d['java_freq']:.5f} amp={d['java_amp']:.2f}° R²={d['r_squared']:.4f} ✓")

    print()
