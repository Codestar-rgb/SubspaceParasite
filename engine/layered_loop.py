"""
Layered Loop Generator (v6.9.17)

Groups bones by their animation frequency and generates separate animation
layers, each with its own optimal loop length. This eliminates the
incommensurate frequency problem that causes velocity discontinuities
at loop boundaries.

Strategy:
- Fast layer (high freq): short loop (~2s)
- Medium layer (mid freq): medium loop (~4s)
- Slow layer (low freq): long loop (~8s)
Each layer completes integer cycles for its bones, ensuring perfect loops.
"""

import logging
import math
import numpy as np
from typing import Dict, List, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


def _detect_bone_frequency(times: np.ndarray, values: np.ndarray) -> float:
    """Detect dominant frequency via zero-crossing analysis.

    Returns frequency in rad/tick, or 0 if no clear frequency.
    """
    if len(values) < 8:
        return 0

    dc = np.mean(values)
    ac = values - dc
    amp = np.max(np.abs(ac))
    if amp < 0.5:
        return 0

    # Zero-crossing analysis
    crossings = []
    for i in range(len(ac) - 1):
        if ac[i] <= 0 and ac[i + 1] > 0:
            t_cross = times[i] + (0 - ac[i]) / (ac[i + 1] - ac[i]) * (times[i + 1] - times[i])
            crossings.append(t_cross)

    if len(crossings) < 2:
        return 0

    period = np.median([crossings[i + 1] - crossings[i] for i in range(len(crossings) - 1)])
    if period <= 0:
        return 0

    return 2 * math.pi / (period * 20)  # rad/tick


def group_bones_by_frequency(anim, model_name: str = "") -> Dict[str, List[str]]:
    """Group bones by their dominant frequency.

    Returns dict: layer_name -> [bone_names]
    Layers: 'fast' (period < 2s), 'medium' (2-5s), 'slow' (> 5s)
    """
    groups = {'fast': [], 'medium': [], 'slow': [], 'static': []}

    for bname, bone_anim in anim.bones.items():
        rot_kfs = sorted([k for k in bone_anim.keyframes if k.channel == 'rotation'],
                         key=lambda k: k.time)
        if len(rot_kfs) < 8:
            groups['static'].append(bname)
            continue

        times = np.array([k.time for k in rot_kfs])
        best_freq = 0
        for ax in ('x', 'y', 'z'):
            vals = np.array([getattr(k, ax).value for k in rot_kfs])
            amp = vals.max() - vals.min()
            if amp < 0.5:
                continue
            freq = _detect_bone_frequency(times, vals)
            if freq > best_freq:
                best_freq = freq
            break

        if best_freq <= 0:
            groups['static'].append(bname)
        else:
            period = 2 * math.pi / (best_freq * 20)  # seconds
            if period < 2.0:
                groups['fast'].append(bname)
            elif period < 5.0:
                groups['medium'].append(bname)
            else:
                groups['slow'].append(bname)

    logger.debug("[%s] %s: fast=%d, medium=%d, slow=%d, static=%d",
                 model_name, anim.name,
                 len(groups['fast']), len(groups['medium']),
                 len(groups['slow']), len(groups['static']))
    return groups


def compute_layer_length(bones: List[str], anim, target_cycles: int = 2) -> float:
    """Compute optimal loop length for a group of bones.

    Finds the length where all bones complete approximately integer cycles.
    """
    best_length = anim.length
    best_error = float('inf')

    for length_ms in range(int(anim.length * 1000 * 0.5), int(anim.length * 1000 * 3), 50):
        length = length_ms / 1000.0
        max_error = 0
        for bname in bones:
            bone = anim.bones.get(bname)
            if not bone:
                continue
            rot_kfs = sorted([k for k in bone.keyframes if k.channel == 'rotation'],
                            key=lambda k: k.time)
            if len(rot_kfs) < 8:
                continue
            times = np.array([k.time for k in rot_kfs])
            for ax in ('x', 'y', 'z'):
                vals = np.array([getattr(k, ax).value for k in rot_kfs])
                amp = vals.max() - vals.min()
                if amp < 0.5:
                    continue
                freq = _detect_bone_frequency(times, vals)
                if freq <= 0:
                    continue
                period = 2 * math.pi / (freq * 20)
                cycles = length / period
                error = abs(cycles - round(cycles))
                max_error = max(max_error, error)
                break

        if max_error < best_error:
            best_error = max_error
            best_length = length

    return best_length
