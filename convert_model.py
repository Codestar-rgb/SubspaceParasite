#!/usr/bin/env python3
"""Single-model converter using the current v6.9.7 pipeline.
Usage: python3 convert_model.py <category> <name>
"""
import json, os, sys, traceback

CONVERTER_DIR = "/tmp/my-project/subspace-work/SubspaceParasite"
if CONVERTER_DIR not in sys.path:
    sys.path.insert(0, CONVERTER_DIR)

from frontend.geckolib_parser import parse_geo_json, parse_animation_json
from backend.bbmodel_exporter import BBModelExporter
from engine.carry_forward import apply_carry_forward_all
from engine.idle_walk_merger import merge_idle_into_walk
from engine.walk_enhancer import enhance_walk_animations
from engine.frequency_snapper import snap_animation_frequencies
from engine.fft_validator import validate_animation_frequencies
from engine.harmonic_decomposer import decompose_harmonics, harmonics_to_molang, fit_quality
from engine.runtime_sampler import RuntimeSampler
from engine.pixel_validator import print_pixel_report
from engine.layered_loop import group_bones_by_frequency, compute_layer_length
from engine.catmullrom_baker import bake_all_animations
from engine.keyframe_simplifier import simplify_animations_v3 as simplify_animations
from core.types import AnimationIR
from engine.java_analyzer import analyze_model
from engine.mve_data_loader import get_mve_animations_for_model, has_mve_data
import config

sys.path.insert(0, os.path.join(CONVERTER_DIR, "batch"))
from mdo_srp import _apply_namespace_and_loop_semantics, _detect_stub_animations

def _fix_fly_mainbody(bbmodel, model_name):
    """Fix fly mainbody position using Java source formula.
    
    Java: mainbody.field_82908_p (offsetY) = sin(ageInTicks*0.2)*0.72
    The upstream animation.json has irregular position data.
    Replace with clean sine wave matching the reference file.
    """
    import math, uuid as uuid_mod
    for anim in bbmodel.get('animations', []):
        if not anim['name'].endswith('.fly') or 'fly_vomit' in anim['name']:
            continue
        if model_name != 'heblu':
            continue
        for aname, adat in anim.get('animators', {}).items():
            if adat.get('name') == 'mainbody':
                length = anim['length']
                # Generate clean sine wave position
                # Reference: 7 kf at t=0, 0.785, 1.537, 2.356, 3.192, 3.927, 4.712
                # But our length is 3.27s, so adapt
                n_samples = 8
                pos_kfs = []
                for i in range(n_samples):
                    t = i * length / (n_samples - 1)
                    age_in_ticks = t * 20.0
                    # Java: field_82908_p = sin(ageInTicks*0.2)*0.72
                    # But reference has phase shift: y=-0.72 at t=0
                    # So use -cos(ageInTicks*0.2)*0.72 (phase = -pi/2)
                    y_val = -math.cos(age_in_ticks * 0.2) * 0.72
                    pos_kfs.append({
                        'channel': 'position',
                        'data_points': [{'x': 0.0, 'y': round(y_val, 4), 'z': 0.0}],
                        'uuid': str(uuid_mod.uuid4()),
                        'time': round(t, 4),
                        'color': -1,
                        'interpolation': 'catmullrom',
                    })
                # Keep rotation keyframes, replace position
                existing = [k for k in adat.get('keyframes', []) if k.get('channel') != 'position']
                adat['keyframes'] = existing + pos_kfs
                adat['keyframes'].sort(key=lambda k: k['time'])
                break
    print(f"  fixed fly mainbody position")


def _add_combined_animations(bbmodel, model_name, anim_path):
    """Add combined animations based on Java source state logic.

    v6.9.13: Creates separate animations for different entity states:
    - kirin: idle_shaking (idle + mainbody trembling from shakingC>0)
    - heblu: fly_vomit (fly + vomit head shaking from vomit>0)
    """
    import copy, math, uuid as uuid_mod

    anims = bbmodel.get('animations', [])
    anim_names = {a['name'] for a in anims}

    # Detect model-specific combined animations
    if model_name == 'kirin':
        # Add idle_shaking = idle + mainbody trembling
        idle = next((a for a in anims if a['name'].endswith('.idle')), None)
        if idle and f'{idle["name"]}_shaking' not in anim_names:
            shaking = copy.deepcopy(idle)
            shaking['name'] = f'{idle["name"]}_shaking'
            shaking['uuid'] = str(uuid_mod.uuid4())
            # Add mainbody trembling (2.95 rad/tick, 5.1° amplitude)
            for aname, adat in shaking['animators'].items():
                if adat.get('name') == 'mainbody':
                    length = shaking['length']
                    n_samples = 40
                    dt = length / (n_samples - 1)
                    trembling_kfs = []
                    for i in range(n_samples):
                        t = i * dt
                        age_in_ticks = t * 20.0
                        x_val = math.degrees(math.sin(age_in_ticks * 2.95) * 0.0891)
                        y_val = math.degrees(math.sin(age_in_ticks * 2.95) * 0.0891)
                        trembling_kfs.append({
                            'channel': 'rotation',
                            'data_points': [{'x': round(x_val, 4), 'y': round(y_val, 4), 'z': 0.0}],
                            'uuid': str(uuid_mod.uuid4()),
                            'time': round(t, 4),
                            'color': -1,
                            'interpolation': 'catmullrom',
                        })
                    adat['keyframes'] = trembling_kfs
                    break
            anims.append(shaking)
            print(f"  added idle_shaking")

    elif model_name == 'heblu':
        # Add fly_vomit = fly + vomit (jointN1-N5 head shaking)
        fly = next((a for a in anims if a['name'].endswith('.fly')), None)
        if fly and f'{fly["name"]}_vomit' not in anim_names:
            # Load upstream vomit data
            try:
                with open(anim_path, 'r', encoding='utf-8') as f:
                    up_data = json.load(f)
                vomit_up = up_data.get('animations', {}).get(f'animation.{model_name}.vomit', {})
                vomit_bones = vomit_up.get('bones', {})

                fly_vomit = copy.deepcopy(fly)
                fly_vomit['name'] = f'{fly["name"]}_vomit'
                fly_vomit['uuid'] = str(uuid_mod.uuid4())

                for aname, adat in fly_vomit['animators'].items():
                    bone_name = adat.get('name', '')
                    if bone_name in vomit_bones:
                        vomit_data = vomit_bones[bone_name]
                        if isinstance(vomit_data, dict) and 'rotation' in vomit_data:
                            rot = vomit_data['rotation']
                            if isinstance(rot, dict):
                                all_times = set()
                                for ax in ['x','y','z']:
                                    if ax in rot:
                                        all_times.update(float(t) for t in rot[ax].keys())
                                all_times = sorted(all_times)
                                new_kfs = []
                                for t in all_times:
                                    x_val = rot.get('x', {}).get(f'{t:.4f}', rot.get('x', {}).get(f'{t:.1f}', 0.0))
                                    y_val = rot.get('y', {}).get(f'{t:.4f}', rot.get('y', {}).get(f'{t:.1f}', 0.0))
                                    z_val = rot.get('z', {}).get(f'{t:.4f}', rot.get('z', {}).get(f'{t:.1f}', 0.0))
                                    new_kfs.append({
                                        'channel': 'rotation',
                                        'data_points': [{'x': float(x_val), 'y': float(y_val), 'z': float(z_val)}],
                                        'uuid': str(uuid_mod.uuid4()),
                                        'time': round(t, 4),
                                        'color': -1,
                                        'interpolation': 'catmullrom',
                                    })
                                if new_kfs:
                                    existing = [k for k in adat.get('keyframes', []) if k.get('channel') != 'rotation']
                                    adat['keyframes'] = existing + new_kfs
                                    adat['keyframes'].sort(key=lambda k: k['time'])
                anims.append(fly_vomit)
                print(f"  added fly_vomit")
            except (FileNotFoundError, KeyError):
                pass


def convert_model(category, name, out_dir=None):
    INPUT_DIR = config.INPUT_DIR
    DECOMPILED_DIR = config.DECOMPILED_DIR
    MVE_DATA_DIR = config.MVE_DATA_DIR
    src_dir = os.path.join(INPUT_DIR, category)
    if out_dir is None:
        out_dir = f"/home/z/my-project/GFL/{category}"
    os.makedirs(out_dir, exist_ok=True)

    print(f"=== Converting {category}/{name} ===")
    # Step 1: Parse geo_json
    geo_path = os.path.join(src_dir, f"{name}.geo.json")
    with open(geo_path, 'r', encoding='utf-8') as f:
        geo_data = json.load(f)
    model_ir = parse_geo_json(geo_data)
    print(f"  bones={len(model_ir.bones)}")

    # Step 2: Parse/merge animations (MVE + upstream)
    # v6.9.11: Only use MVE idle. Skip MVE walk/death_idle when upstream has anims.
    animations_ir = []
    mve_anim_names = set()
    if has_mve_data(name, MVE_DATA_DIR):
        mve_anims, mve_raw = get_mve_animations_for_model(name, MVE_DATA_DIR)
        if mve_anims:
            # Filter: keep only MVE idle, skip walk/death_idle (lower quality than upstream)
            mve_anims = [a for a in mve_anims if 'idle' in a.name.lower() and 'death' not in a.name.lower()]
            if mve_anims:
                animations_ir = mve_anims
                mve_anim_names = {a.name for a in mve_anims}
                print(f"  mve(idle only)={len(animations_ir)}")

    anim_path = os.path.join(src_dir, f"{name}.animation.json")
    if os.path.exists(anim_path):
        with open(anim_path, 'r', encoding="utf-8") as f:
            anim_data = json.load(f)
        anim_dict = parse_animation_json(anim_data, model_name=name)
        upstream_anims = list(anim_dict.values())
        upstream_anims, _ = _apply_namespace_and_loop_semantics(upstream_anims, name)
        name_lower = name.lower()
        for ua in upstream_anims:
            if f".{name_lower}." in ua.name:
                ua.name = ua.name.replace(f".{name_lower}.", f".{name}.")
            elif ua.name.endswith(f".{name_lower}"):
                ua.name = ua.name[:-(len(name_lower))] + name
        mve_anim_names_lower = {n.lower() for n in mve_anim_names}
        upstream_count = 0
        for ua in upstream_anims:
            if ua.name.lower() not in mve_anim_names_lower:
                animations_ir.append(ua)
                upstream_count += 1
        if upstream_count > 0:
            print(f"  upstream={upstream_count}")

    if animations_ir:
        animations_ir, _ = _apply_namespace_and_loop_semantics(animations_ir, name)
    if animations_ir:
        stubs = _detect_stub_animations(animations_ir, name)
        if stubs:
            print(f"  STUB({len(stubs)})")

    # Step 2d: Java trig analysis
    model_meta = None
    if os.path.isdir(DECOMPILED_DIR):
        try:
            model_meta = analyze_model(name, DECOMPILED_DIR)
            if model_meta and model_meta.head_tracking:
                print("  head(✓)")
        except Exception as e:
            print(f"  java_err({e})")

    # Step 3: Carry-forward
    if animations_ir:
        cf_stats = {}
        anim_dict = {a.name: a for a in animations_ir}
        cf_result = apply_carry_forward_all(anim_dict, name, cf_stats)
        animations_ir = list(cf_result.values())

    # Step 3b: Idle-walk merger
    if animations_ir:
        animations_ir = merge_idle_into_walk(animations_ir, name)

    # Step 3c: Walk enhancer
    if animations_ir:
        animations_ir = enhance_walk_animations(animations_ir, name)

    # Step 3c2: Frequency snapping (v6.9.8)
    if animations_ir:
        animations_ir = snap_animation_frequencies(animations_ir, name)

    # Step 3e2: FFT validation (v6.9.17)
    if animations_ir:
        issues = validate_animation_frequencies(animations_ir, name)
        if issues:
            print(f"  FFT validation: {len(issues)} frequency deviations detected")

    # Step 3e: Filter out stub/empty animations (v6.9.11)
    # Remove: length <= 0, <5 kf, or <3 animators (stubs like visibility)
    if animations_ir:
        filtered = []
        for a in animations_ir:
            total_kf = sum(len(ba.keyframes) for ba in a.bones.values())
            n_bones = len(a.bones)
            if a.length > 0 and total_kf >= 5 and n_bones >= 3:
                filtered.append(a)
            else:
                print(f"  skip stub: {a.name} (len={a.length}, kf={total_kf}, bones={n_bones})")
        animations_ir = filtered

    # Step 3f: Bake + simplify
    if animations_ir:
        animations_ir = bake_all_animations(animations_ir, name)
        animations_ir = simplify_animations(animations_ir, name)
        total_kf = sum(len(ba.keyframes) for a in animations_ir for ba in a.bones.values())
        print(f"  after bake+rdp: {total_kf} keyframes")

    # Step 4: Texture
    tex_path = os.path.join(src_dir, f"{name}.png")
    if not os.path.exists(tex_path):
        tex_path = None

    # Step 5: Export
    exporter = BBModelExporter()
    bbmodel = exporter.export(
        model_ir,
        animations=animations_ir,
        texture_path=tex_path,
        texture_name=name,
        namespace='srparasites',
        model_metadata=model_meta,
    )

    # v6.9.11: Remove stub/visibility animations from final output
    if 'animations' in bbmodel:
        bbmodel['animations'] = [a for a in bbmodel['animations']
            if a.get('length', 0) > 0 and len(a.get('animators', {})) >= 5]

    # v6.9.15: Fix fly mainbody position (clean sine from Java source)
    _fix_fly_mainbody(bbmodel, name)

    # v6.9.13: Add combined animations
    _add_combined_animations(bbmodel, name, anim_path)

    # v6.9.13: Force seamless loop for combined animations (fly_vomit, idle_shaking)
    for anim in bbmodel.get('animations', []):
        if anim.get('loop') == 'loop' and anim.get('length', 0) > 0:
            for aname, adat in anim.get('animators', {}).items():
                kfs = adat.get('keyframes', [])
                if len(kfs) < 2:
                    continue
                by_channel = {}
                for kf in kfs:
                    ch = kf.get('channel', '')
                    by_channel.setdefault(ch, []).append(kf)
                for ch, ch_kfs in by_channel.items():
                    if len(ch_kfs) < 2:
                        continue
                    first = ch_kfs[0]
                    last = ch_kfs[-1]
                    # Force last = first for seamless loop
                    last['data_points'] = [dict(dp) for dp in first.get('data_points', [])]

    out_path = os.path.join(out_dir, f"{name}.bbmodel")
    exporter.save(bbmodel, out_path)
    print(f"  SAVED: {out_path}")

    # Summary
    with open(out_path) as f:
        d = json.load(f)
    for anim in d.get('animations', []):
        animators = anim.get('animators', {})
        total_kf = sum(len(a.get('keyframes',[])) for a in animators.values())
        interps = set()
        seam_ok = 0
        for aname, adat in animators.items():
            kf = adat.get('keyframes', [])
            interps.update(k.get('interpolation') for k in kf)
            rot = [k for k in kf if k['channel'] == 'rotation']
            if rot:
                f_dp = rot[0]['data_points'][0]
                l_dp = rot[-1]['data_points'][0]
                if all(abs(f_dp.get(ax,0) - l_dp.get(ax,0)) < 0.01 for ax in ('x','y','z')):
                    seam_ok += 1
        print(f"  Anim: {anim['name']} len={anim['length']}s loop={anim['loop']} "
              f"animators={len(animators)} kf={total_kf} interps={interps} seamless={seam_ok}/{len(animators)}")
    return out_path

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 convert_model.py <category> <name>")
        sys.exit(1)
    convert_model(sys.argv[1], sys.argv[2])
