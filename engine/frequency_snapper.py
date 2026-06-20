#!/usr/bin/env python3
"""
Frequency Snapper (v6.9.8)
==========================

Fixes non-seamless loop animations by snapping bone frequencies to integer
cycles at the animation length.

PROBLEM:
  When bones have incommensurate frequencies (irrational ratios), no single
  animation length makes all complete integer cycles. The loop boundary has
  a velocity discontinuity — the motion reverses direction to match the
  first frame, causing visible "stutter" or "pause".

  Even with v6.9.5's forced first=last (which eliminates position discontinuity),
  the VELOCITY is discontinuous: the catmullrom spline must reverse direction
  at the boundary, creating a momentary "freeze" or "stutter".

SOLUTION:
  1. For each bone axis, detect if motion is sinusoidal (single frequency)
  2. Fit: value = DC + A * sin(2*pi*f*t + phi)
  3. Find optimal animation length L that minimizes max frequency change
     when snapping each f to N complete cycles (N = round(L * f))
  4. Snap each frequency: f_snapped = N / L
  5. Regenerate keyframes with snapped frequency

  Max frequency change is typically <15% — imperceptible for organic motion.
  Result: 0° seam AND 0 velocity jump = truly seamless loop.

USAGE:
  Called in the batch converter after MVE/upstream loading, before baking.
  Only applies to loop animations with sinusoidal bone motion.
"""

from __future__ import annotations
import math
import logging
import numpy as np
from typing import List, Tuple, Optional
from core.types import AnimationIR, BoneAnimationIR, KeyframeData, AxisValue

logger = logging.getLogger(__name__)

# Minimum amplitude to consider a bone "animated" (degrees)
MIN_AMPLITUDE = 0.5
# R² threshold for sinusoidal fit quality
SINUSOIDAL_R2_THRESHOLD = 0.85
# Maximum allowed frequency change (fraction)
MAX_FREQ_CHANGE = 0.20
# Length search range (seconds)
MIN_LENGTH = 1.0
MAX_LENGTH = 12.0
# Length search step (seconds)
LENGTH_STEP = 0.05


def _fit_sine(times: np.ndarray, values: np.ndarray) -> Optional[Tuple[float, float, float, float, float]]:
    """Fit values = DC + A * sin(2*pi*f*t + phi) via FFT + refinement.

    Returns (frequency_hz, amplitude, phase, dc_offset, r_squared) or None.
    frequency_hz is cycles per second.
    """
    n = len(values)
    if n < 4:
        return None

    dc = float(np.mean(values))
    ac = values - dc

    amp = float(np.max(np.abs(ac)))
    if amp < MIN_AMPLITUDE:
        return None

    # FFT to find dominant frequency
    dt = float((times[-1] - times[0]) / (n - 1)) if n > 1 else 1.0
    if dt <= 0:
        return None

    fft = np.fft.rfft(ac)
    freqs = np.fft.rfftfreq(n, d=dt)
    mags = np.abs(fft)

    if len(mags) <= 1:
        return None

    # Skip DC (index 0), find peak
    peak_idx = np.argmax(mags[1:]) + 1
    freq_hz = float(freqs[peak_idx])

    if freq_hz <= 0:
        return None

    # Refine: least squares fit for A*sin(2*pi*f*t + phi) = a*sin(wt) + b*cos(wt)
    w = 2 * math.pi * freq_hz
    sin_wt = np.sin(w * times)
    cos_wt = np.cos(w * times)

    # Design matrix [sin, cos, 1]
    design = np.column_stack([sin_wt, cos_wt, np.ones(n)])
    try:
        coeffs, residuals, _, _ = np.linalg.lstsq(design, values, rcond=None)
    except np.linalg.LinAlgError:
        return None

    a_coeff, b_coeff, dc_fit = coeffs
    amplitude = math.sqrt(a_coeff ** 2 + b_coeff ** 2)
    phase = math.atan2(b_coeff, a_coeff)  # phi such that A*sin(wt + phi)

    if amplitude < MIN_AMPLITUDE:
        return None

    # Compute R²
    predicted = dc_fit + a_coeff * sin_wt + b_coeff * cos_wt
    ss_res = float(np.sum((values - predicted) ** 2))
    ss_tot = float(np.sum((values - dc) ** 2))
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    return (freq_hz, amplitude, phase, dc_fit, r_squared)


def _snap_frequency(freq_hz: float, length: float) -> Tuple[int, float, float]:
    """Snap frequency to complete integer cycles in given length.

    Returns (N, snapped_freq_hz, change_fraction).
    """
    cycles = freq_hz * length
    n = max(1, round(cycles))
    snapped = n / length
    change = abs(snapped - freq_hz) / freq_hz if freq_hz > 0 else 0
    return (n, snapped, change)


def _find_optimal_length(
    bone_fits: List[Tuple[str, str, float, float, float, float]],
    original_length: float,
) -> float:
    """Find optimal animation length minimizing max frequency change.

    bone_fits: list of (bone_name, axis, freq_hz, amplitude, phase, dc)
    """
    if not bone_fits:
        return original_length

    # Search around original length, also try wider range
    search_min = max(MIN_LENGTH, original_length * 0.5)
    search_max = min(MAX_LENGTH, original_length * 2.0)

    best_length = original_length
    best_max_change = float("inf")

    candidates = np.arange(search_min, search_max, LENGTH_STEP)
    for L in candidates:
        max_change = 0
        for _, _, freq_hz, _, _, _ in bone_fits:
            _, _, change = _snap_frequency(freq_hz, L)
            max_change = max(max_change, change)
        if max_change < best_max_change:
            best_max_change = max_change
            best_length = float(L)

    # If best change is too large, keep original length
    if best_max_change > MAX_FREQ_CHANGE:
        return original_length

    return best_length


def _regenerate_keyframes(
    bone_anim: BoneAnimationIR,
    bone_fits: dict,
    length: float,
    n_samples: int = 40,
) -> BoneAnimationIR:
    """Regenerate keyframes for a bone using snapped frequencies.

    bone_fits: dict mapping axis -> (freq_hz, amplitude, phase, dc, r_squared)
    """
    dt = length / (n_samples - 1) if n_samples > 1 else 0
    new_kfs = []

    # Group fits by channel (all rotation axes share the same time points)
    rot_fits = {}
    for axis in ("x", "y", "z"):
        if axis in bone_fits:
            rot_fits[axis] = bone_fits[axis]

    if not rot_fits:
        return bone_anim  # No sinusoidal axes, keep original

    # Get original keyframes for non-sinusoidal channels
    orig_by_channel = {}
    for kf in bone_anim.keyframes:
        ch = kf.channel
        if ch not in orig_by_channel:
            orig_by_channel[ch] = []
        orig_by_channel[ch].append(kf)

    new_keyframes = []

    # Regenerate rotation channel
    if rot_fits:
        for i in range(n_samples):
            t = i * dt
            x_val = 0.0
            y_val = 0.0
            z_val = 0.0
            for axis, (freq_hz, amp, phase, dc, r2) in rot_fits.items():
                # Snap frequency
                n_cycles, snapped_freq, _ = _snap_frequency(freq_hz, length)
                val = dc + amp * math.sin(2 * math.pi * snapped_freq * t + phase)
                if axis == "x":
                    x_val = val
                elif axis == "y":
                    y_val = val
                else:
                    z_val = val
            new_keyframes.append(KeyframeData(
                time=round(t, 6),
                channel="rotation",
                x=AxisValue.explicit_val(x_val),
                y=AxisValue.explicit_val(y_val),
                z=AxisValue.explicit_val(z_val),
                easing="linear",
                interpolation="catmullrom",
            ))

    # Keep non-rotation channels from original
    for ch, kfs in orig_by_channel.items():
        if ch != "rotation":
            new_keyframes.extend(kfs)

    new_keyframes.sort(key=lambda k: (k.time, k.channel))
    return BoneAnimationIR(bone_name=bone_anim.bone_name, keyframes=new_keyframes)


def _blend_loop_boundary(
    bone_anim: BoneAnimationIR,
    length: float,
) -> BoneAnimationIR:
    """Blend the last keyframes toward the first to ensure seamless loop.

    For non-sinusoidal bones where frequency snapping does not apply, this
    creates a smooth velocity transition at the loop boundary.
    """
    kfs = sorted(bone_anim.keyframes, key=lambda k: (k.time, k.channel))
    if len(kfs) < 6:
        return bone_anim

    by_channel = {}
    for kf in kfs:
        by_channel.setdefault(kf.channel, []).append(kf)

    new_kfs = []
    for ch, ch_kfs in by_channel.items():
        ch_kfs = sorted(ch_kfs, key=lambda k: k.time)
        n = len(ch_kfs)
        if n < 6:
            new_kfs.extend(ch_kfs)
            continue

        blend_n = max(3, min(8, n // 7))
        first = ch_kfs[0]
        last = ch_kfs[-1]

        # Compute blend adjustments per axis
        adjustments = {}
        for axis in ("x", "y", "z"):
            first_val = getattr(first, axis).value
            last_val = getattr(last, axis).value
            diff = first_val - last_val
            if abs(diff) < 0.01:
                adjustments[axis] = None
            else:
                adjustments[axis] = []
                for i in range(blend_n):
                    s = (i + 1) / blend_n
                    smooth = s * s * (3 - 2 * s)
                    adjustments[axis].append(diff * smooth)

        # Rebuild keyframes with blended values
        for idx, kf in enumerate(ch_kfs):
            new_x = kf.x.value
            new_y = kf.y.value
            new_z = kf.z.value

            # Apply blend if in the blend window
            if idx >= n - blend_n:
                blend_idx = idx - (n - blend_n)
                for axis, adj in adjustments.items():
                    if adj is None:
                        continue
                    val = adj[blend_idx]
                    if axis == "x":
                        new_x = kf.x.value + val
                    elif axis == "y":
                        new_y = kf.y.value + val
                    elif axis == "z":
                        new_z = kf.z.value + val

            # Force last keyframe = first keyframe
            if idx == n - 1:
                new_x = first.x.value
                new_y = first.y.value
                new_z = first.z.value

            new_kfs.append(KeyframeData(
                time=kf.time,
                channel=kf.channel,
                x=AxisValue.explicit_val(round(new_x, 6)),
                y=AxisValue.explicit_val(round(new_y, 6)),
                z=AxisValue.explicit_val(round(new_z, 6)),
                easing=kf.easing,
                interpolation=kf.interpolation,
                is_molang=kf.is_molang,
                molang_x=kf.molang_x,
                molang_y=kf.molang_y,
                molang_z=kf.molang_z,
            ))

    new_kfs.sort(key=lambda k: (k.time, k.channel))
    return BoneAnimationIR(bone_name=bone_anim.bone_name, keyframes=new_kfs)


def snap_animation_frequencies(animations: list, model_name: str = "") -> list:
    """Snap all loop animations' bone frequencies to integer cycles.

    For each loop animation:
    1. For each bone axis, fit sinusoidal curve
    2. Find optimal length minimizing max frequency change
    3. Snap all frequencies to integer cycles at that length
    4. Regenerate keyframes with snapped frequencies

    Only applies to loop animations. Non-loop (hold/once) are unchanged.
    Only snaps bones with sinusoidal motion (R² > threshold).
    """
    for anim in animations:
        if anim.loop != "loop" or anim.length <= 0:
            continue

        original_length = anim.length
        bone_fits_all = []  # (bone, axis, freq, amp, phase, dc)
        bone_fits_by_bone = {}  # bone_name -> {axis: (freq, amp, phase, dc, r2)}

        for bone_name, bone_anim in anim.bones.items():
            # Collect rotation keyframes per axis
            rot_kfs = [kf for kf in bone_anim.keyframes if kf.channel == "rotation"]
            if len(rot_kfs) < 4:
                continue

            rot_kfs.sort(key=lambda k: k.time)
            times = np.array([kf.time for kf in rot_kfs])

            bone_fits = {}
            for axis in ("x", "y", "z"):
                vals = np.array([getattr(kf, axis).value for kf in rot_kfs])
                fit = _fit_sine(times, vals)
                if fit and fit[4] >= SINUSOIDAL_R2_THRESHOLD:  # r_squared
                    freq_hz, amp, phase, dc, r2 = fit
                    bone_fits[axis] = (freq_hz, amp, phase, dc, r2)
                    bone_fits_all.append((bone_name, axis, freq_hz, amp, phase, dc))

            if bone_fits:
                bone_fits_by_bone[bone_name] = bone_fits

        if not bone_fits_all:
            continue

        # Find optimal length
        optimal_length = _find_optimal_length(bone_fits_all, original_length)

        if abs(optimal_length - original_length) < 0.01:
            # Length unchanged, but still snap frequencies at original length
            optimal_length = original_length

        # Snap and regenerate
        max_change = 0
        for _, _, freq_hz, _, _, _ in bone_fits_all:
            _, _, change = _snap_frequency(freq_hz, optimal_length)
            max_change = max(max_change, change)

        if max_change > MAX_FREQ_CHANGE:
            logger.debug(
                "[%s] %s: max freq change %.1f%% too large, skipping",
                model_name, anim.name, max_change * 100,
            )
            continue

        # Regenerate each bone
        n_snapped = 0
        n_blended = 0
        for bone_name, bone_anim in anim.bones.items():
            if bone_name in bone_fits_by_bone:
                new_bone = _regenerate_keyframes(
                    bone_anim, bone_fits_by_bone[bone_name], optimal_length
                )
                anim.bones[bone_name] = new_bone
                n_snapped += 1
            else:
                anim.bones[bone_name] = _blend_loop_boundary(bone_anim, optimal_length)
                n_blended += 1

        # Update animation length
        anim.length = round(optimal_length, 4)

        logger.debug(
            "[%s] %s: length %.2f->%.2f, %d snapped %d blended (max change %.1f%%)",
            model_name, anim.name, original_length, optimal_length,
            n_snapped, n_blended, max_change * 100,
        )

    return animations
