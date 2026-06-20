#!/usr/bin/env python3
"""v6.9.7: Regenerate leer MVE data with optimal length + frequency snapping.

ROOT CAUSE of "too long / not seamless / acceleration":
- 6 idle frequencies (0.066-0.096 rad/tick) are INCOMMENSURATE (irrational
  ratios). No single animation length makes all bones complete integer cycles.
- 13.115s was chosen to "minimize max seam" but still had 9.52° max seam
  → visible discontinuity at loop boundary ("不衔接")
- 13.115s is also too long for an idle animation ("过长")
- jointM1/M2 at state1 freq (0.196/0.149, 8 cycles in 13s) look "accelerated"
  relative to idle bones (2-4 cycles in 13s)

FIX: Length = 9.60s + frequency snapping
- For each f-variable, snap frequency so it completes exactly N integer
  cycles in 9.60s (N chosen to minimize frequency change)
- Result: 0° seam (all integer cycles), 14.2% max freq change
- N values preserve layered motion: idle f1/f2/f6 → 3 cycles, f3/f4/f5 → 2
  cycles, state1 f1 → 6, f2 → 5
"""
import json, re, math, os, shutil

JAVA_PATH = "/tmp/my-project/subspace-work/decompiled/all/crude_ModelLeer/com/dhanantry/scapeandrunparasites/client/model/entity/crude/ModelLeer.java"
MVE_PATH = "/tmp/my-project/subspace-work/mve-capture/data/leer.mve.json"

# Target animation length (seconds) — optimal for frequency snapping
TARGET_LENGTH = 9.60

# Original Java frequencies: (freq_rad_per_tick, amplitude_rad, phase_rad)
IDLE_F = {
    'f1': (0.086, 0.14, 0.0),
    'f2': (0.087, 0.16, 8.0),
    'f3': (0.076, 0.13, 4.0),
    'f4': (0.07,  0.111, 8.0),
    'f5': (0.066, 0.12, 4.0),
    'f6': (0.096, 0.15, 4.0),
}
STATE1_F = {
    'f1': (0.196, 0.175, 0.0),
    'f2': (0.14896, 0.145, 0.0),
}

FIELD_AXIS = {
    'field_78795_f': 'x',
    'field_78796_g': 'y',
    'field_78808_h': 'z',
}

def snap_frequency(freq, target_length):
    """Snap frequency so it completes exactly N integer cycles in target_length.
    Returns (N, snapped_freq) that minimizes |snapped_freq - freq|.
    """
    period = 2 * math.pi / (freq * 20)  # seconds
    best_n, best_change = 1, 999.0
    for n in range(1, 30):
        snapped = n * 2 * math.pi / (target_length * 20)
        change = abs(snapped - freq) / freq
        if change < best_change:
            best_change = change
            best_n = n
    snapped_freq = best_n * 2 * math.pi / (target_length * 20)
    return best_n, snapped_freq

def parse_java_assignments(java_text):
    """Extract bone assignments from setRotationAngles.
    Returns list of (bone, axis, f_var, sign, segment).
    """
    m = re.search(r'public void func_78087_a\([^)]*\)\s*\{', java_text)
    if not m:
        raise RuntimeError("func_78087_a not found")
    start = m.end()
    depth = 1
    i = start
    while i < len(java_text) and depth > 0:
        if java_text[i] == '{': depth += 1
        elif java_text[i] == '}': depth -= 1
        i += 1
    body = java_text[start:i-1]

    state1_marker = re.search(r'^\s*f1\s*=\s*MathHelper', body, re.MULTILINE)
    state1_start = state1_marker.start() if state1_marker else len(body)

    assignments = []
    pat = re.compile(r'this\.(\w+)\.(field_78795_f|field_78796_g|field_78808_h)\s*=\s*(-?)(f[1-6])\s*;')
    for m in pat.finditer(body):
        bone = m.group(1)
        field = m.group(2)
        sign_str = m.group(3)
        fvar = m.group(4)
        axis = FIELD_AXIS[field]
        sign = -1.0 if sign_str == '-' else 1.0
        segment = 'state1' if m.start() >= state1_start else 'idle'
        assignments.append((bone, axis, fvar, sign, segment))
    return assignments

def main():
    with open(JAVA_PATH, 'r', encoding='utf-8') as f:
        java_text = f.read()
    assignments = parse_java_assignments(java_text)
    print(f"Parsed {len(assignments)} bone assignments from Java source")

    # Compute snapped frequencies for each f-variable
    print(f"\n=== Frequency snapping (target length = {TARGET_LENGTH}s) ===")
    snapped = {}  # (segment, fvar) -> (N, snapped_freq, orig_freq, amp, phase)
    for fvar, (freq, amp, phase) in IDLE_F.items():
        n, sf = snap_frequency(freq, TARGET_LENGTH)
        change = abs(sf - freq) / freq * 100
        print(f"  idle {fvar}: {freq:.5f} -> {sf:.5f} (N={n}, {change:+.1f}%)")
        snapped[('idle', fvar)] = (n, sf, freq, amp, phase)
    for fvar, (freq, amp, phase) in STATE1_F.items():
        n, sf = snap_frequency(freq, TARGET_LENGTH)
        change = abs(sf - freq) / freq * 100
        print(f"  state1 {fvar}: {freq:.5f} -> {sf:.5f} (N={n}, {change:+.1f}%)")
        snapped[('state1', fvar)] = (n, sf, freq, amp, phase)

    # Build per-bone per-axis mapping
    bone_axis_map = {}  # (bone, axis) -> (segment, fvar, sign)
    for bone, axis, fvar, sign, segment in assignments:
        bone_axis_map[(bone, axis)] = (segment, fvar, sign)

    # Load original MVE data (to get bone list and metadata)
    with open(MVE_PATH, 'r', encoding='utf-8') as f:
        mve = json.load(f)
    state = mve['states'][0]
    bones = state['bones']

    # Regenerate with target length and snapped frequencies
    N_SAMPLES = 81  # original sample count
    dt = TARGET_LENGTH / (N_SAMPLES - 1)
    state['length'] = TARGET_LENGTH
    print(f"\nRegenerating: length={TARGET_LENGTH}s, {N_SAMPLES} samples, dt={dt:.6f}")

    for bname, bdat in bones.items():
        kfs = bdat if isinstance(bdat, list) else bdat.get('keyframes', [])
        # Ensure correct number of keyframes
        if len(kfs) != N_SAMPLES:
            # Rebuild keyframe list
            kfs = [{'time': i * dt, 'rotation': [0.0, 0.0, 0.0], 'position': [0.0, 0.0, 0.0], 'hidden': False} for i in range(N_SAMPLES)]
        # For each axis, regenerate if we have a mapping
        for axis in ('x', 'y', 'z'):
            key = (bname, axis)
            if key not in bone_axis_map:
                continue
            segment, fvar, sign = bone_axis_map[key]
            if (segment, fvar) not in snapped:
                continue
            n, sf, orig_freq, amp, phase = snapped[(segment, fvar)]
            for i, kf in enumerate(kfs):
                t = i * dt
                age_in_ticks = t * 20.0
                val_rad = sign * amp * math.sin(age_in_ticks * sf + phase)
                val_deg = math.degrees(val_rad)
                rot = list(kf['rotation'])
                axis_idx = {'x':0,'y':1,'z':2}[axis]
                rot[axis_idx] = val_deg
                kf['rotation'] = rot
                kf['time'] = round(t, 6)
        if isinstance(bdat, list):
            bones[bname] = kfs
        else:
            bdat['keyframes'] = kfs
            bones[bname] = bdat

    # Backup original
    backup = MVE_PATH + '.v697.bak'
    if not os.path.exists(backup):
        shutil.copy2(MVE_PATH, backup)
        print(f"Backup saved: {backup}")

    with open(MVE_PATH, 'w', encoding='utf-8') as f:
        json.dump(mve, f, indent=1)
    print(f"Saved: {MVE_PATH}")

    # Verify: all bones should complete integer cycles
    import numpy as np
    print(f"\n=== Verification ===")
    all_ok = True
    for bname in ['jointA1', 'jointA5', 'jointM1', 'jointM2', 'jointC3', 'jointD2']:
        bdat = bones[bname]
        kfs = bdat if isinstance(bdat, list) else bdat.get('keyframes', [])
        times = np.array([k['time'] for k in kfs])
        for ai, ax in enumerate(['x','y','z']):
            vals = np.array([k['rotation'][ai] for k in kfs])
            amp = vals.max() - vals.min()
            if amp < 1.0: continue
            vals_dc = vals - vals.mean()
            crossings = []
            for i in range(len(vals)-1):
                if vals_dc[i] <= 0 and vals_dc[i+1] > 0:
                    tc = times[i] + (0-vals_dc[i])/(vals_dc[i+1]-vals_dc[i])*(times[i+1]-times[i])
                    crossings.append(tc)
            if len(crossings) >= 2:
                period = np.median([crossings[i+1]-crossings[i] for i in range(len(crossings)-1)])
                cycles = TARGET_LENGTH / period
                seam = abs(vals[-1] - vals[0])
                ok = abs(cycles - round(cycles)) < 0.05 and seam < 0.1
                if not ok: all_ok = False
                print(f"  {bname}.{ax}: amp={amp:.2f}° period={period:.3f}s cycles={cycles:.3f} seam={seam:.3f}° {'✓' if ok else '✗'}")
            break
    print(f"\nAll integer cycles + seamless: {all_ok}")

if __name__ == '__main__':
    main()
