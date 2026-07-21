"""
FFT Harmonic Decomposer (v6.9.19)

Decomposes bone animation curves into multiple sine harmonics.
SRP tentacle animations often use multi-frequency overlays like:
    bone.x = sin(0.07t) * 0.5 + sin(0.15t) * 0.3

Single-sine fitting only captures the dominant frequency, losing
secondary harmonics. This module:
1. Performs FFT on the animation curve
2. Identifies top-K harmonics by power spectral density
3. Refines each harmonic with Levenberg-Marquardt fitting
4. Outputs either Molang expressions or dense keyframes
"""

import math
import numpy as np
import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MAX_HARMONICS = 5
ENERGY_THRESHOLD = 0.99  # Capture 99% of signal energy


@dataclass
class Harmonic:
    """A single harmonic component."""
    freq_hz: float       # Frequency in Hz (cycles/second)
    freq_rad_tick: float # Frequency in rad/tick
    amplitude: float     # Amplitude in degrees
    phase: float         # Phase in radians
    power: float         # Power (proportional to amplitude²)


def decompose_harmonics(times: np.ndarray, values: np.ndarray,
                        max_harmonics: int = MAX_HARMONICS) -> List[Harmonic]:
    """Decompose a signal into its harmonic components via FFT.

    Args:
        times: Time points (seconds)
        values: Values at each time point (degrees)
        max_harmonics: Maximum number of harmonics to extract

    Returns:
        List of Harmonic objects, sorted by power (descending)
    """
    n = len(values)
    if n < 8:
        return []

    dc = float(np.mean(values))
    ac = values - dc
    total_power = float(np.sum(ac ** 2))
    if total_power < 1e-6:
        return []

    dt = float((times[-1] - times[0]) / (n - 1)) if n > 1 else 1.0
    if dt <= 0:
        return []

    # FFT
    fft = np.fft.rfft(ac)
    freqs_hz = np.fft.rfftfreq(n, d=dt)
    mags = np.abs(fft)

    if len(mags) <= 1:
        return []

    # Power spectral density (normalized)
    power = mags ** 2
    cumulative_energy = 0.0
    total_energy = float(np.sum(power[1:]))  # Skip DC

    if total_energy < 1e-10:
        return []

    # Sort peaks by power (descending), skip DC
    peak_indices = np.argsort(power[1:])[::-1] + 1

    harmonics = []
    accumulated_energy = 0.0

    for idx in peak_indices:
        if len(harmonics) >= max_harmonics:
            break

        freq_hz = float(freqs_hz[idx])
        if freq_hz <= 0:
            continue

        # Amplitude from FFT magnitude (normalized for 2-sided spectrum)
        amplitude = float(2 * mags[idx] / n)
        phase = float(np.angle(fft[idx]))

        # Power
        h_power = float(power[idx] / total_energy)
        accumulated_energy += h_power

        freq_rad_tick = freq_hz * 2 * math.pi / 20.0

        h = Harmonic(
            freq_hz=freq_hz,
            freq_rad_tick=freq_rad_tick,
            amplitude=amplitude,
            phase=phase,
            power=h_power,
        )
        # Refine frequency/phase with least-squares
        h = refine_harmonic(h, times, ac)
        harmonics.append(h)

        if accumulated_energy >= ENERGY_THRESHOLD:
            break

    return harmonics


def reconstruct_from_harmonics(harmonics: List[Harmonic], dc: float,
                                times: np.ndarray) -> np.ndarray:
    """Reconstruct signal from harmonics + DC offset.

    Uses cos convention to match FFT phase: A*cos(2*pi*f*t + phase)
    """
    result = np.full(len(times), dc)
    for h in harmonics:
        result += h.amplitude * np.cos(2 * math.pi * h.freq_hz * times + h.phase)
    return result


def refine_harmonic(harmonic: Harmonic, times: np.ndarray,
                    values: np.ndarray) -> Harmonic:
    """Refine a single harmonic using least-squares fitting.

    FFT gives coarse frequency bins; this refines to sub-bin precision.
    Uses scipy.optimize.least_squares with Levenberg-Marquardt if available,
    otherwise falls back to grid search.
    """
    try:
        from scipy.optimize import least_squares
        def residual(params):
            a, f, p = params
            return a * np.cos(2 * math.pi * f * times + p) - (values - np.mean(values))

        x0 = [harmonic.amplitude, harmonic.freq_hz, harmonic.phase]
        result = least_squares(residual, x0, method='lm', max_nfev=1000)
        return Harmonic(
            freq_hz=float(result.x[1]),
            freq_rad_tick=float(result.x[1]) * 2 * math.pi / 20.0,
            amplitude=float(result.x[0]),
            phase=float(result.x[2]),
            power=harmonic.power,
        )
    except ImportError:
        # Fallback: grid search around FFT frequency
        best_err = float('inf')
        best = harmonic
        for f_offset in np.linspace(-0.01, 0.01, 21):
            f = harmonic.freq_hz + f_offset
            if f <= 0:
                continue
            for p_offset in np.linspace(-0.5, 0.5, 21):
                p = harmonic.phase + p_offset
                pred = harmonic.amplitude * np.cos(2 * math.pi * f * times + p)
                err = np.sum((pred - (values - np.mean(values))) ** 2)
                if err < best_err:
                    best_err = err
                    best = Harmonic(
                        freq_hz=f,
                        freq_rad_tick=f * 2 * math.pi / 20.0,
                        amplitude=harmonic.amplitude,
                        phase=p,
                        power=harmonic.power,
                    )
        return best


def harmonics_to_molang(harmonics: List[Harmonic], dc: float = 0.0) -> str:
    """Convert harmonic decomposition to a Molang expression.

    Produces: dc + A1*sin(2*pi*f1*t + phi1) + A2*sin(...) + ...
    """
    if not harmonics:
        return str(dc)

    parts = []
    if abs(dc) > 0.001:
        parts.append(f"{dc:.6f}")

    for h in harmonics:
        # Convert to ageInTicks-based expression
        # sin(2*pi*f_hz * t + phi) = sin(freq_rad_tick * ageInTicks + phi)
        # where ageInTicks = t * 20
        freq = h.freq_rad_tick
        amp = h.amplitude
        phase = h.phase

        if abs(amp) < 0.001:
            continue

        # Molang: math.cos(query.anim_time * 20 * freq + phase) * amp
        term = f"math.cos(query.anim_time * 20 * {freq:.6f}"
        if abs(phase) > 0.001:
            term += f" + {phase:.6f}"
        term += f") * {amp:.6f}"
        parts.append(term)

    if not parts:
        return "0.0"

    return " + ".join(parts)


def fit_quality(harmonics: List[Harmonic], dc: float,
                times: np.ndarray, values: np.ndarray) -> float:
    """Compute R² of the harmonic reconstruction."""
    if not harmonics:
        return 0.0

    predicted = reconstruct_from_harmonics(harmonics, dc, times)
    ss_res = float(np.sum((values - predicted) ** 2))
    ss_tot = float(np.sum((values - dc) ** 2))
    return 1 - ss_res / ss_tot if ss_tot > 0 else 0
