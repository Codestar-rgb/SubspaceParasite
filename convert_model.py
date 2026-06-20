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
from engine.catmullrom_baker import bake_all_animations
from engine.keyframe_simplifier import simplify_animations_v3 as simplify_animations
from core.types import AnimationIR
from engine.java_analyzer import analyze_model
from engine.mve_data_loader import get_mve_animations_for_model, has_mve_data
import config

sys.path.insert(0, os.path.join(CONVERTER_DIR, "batch"))
from mdo_srp import _apply_namespace_and_loop_semantics, _detect_stub_animations

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
