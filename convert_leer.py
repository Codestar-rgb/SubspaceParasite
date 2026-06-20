#!/usr/bin/env python3
"""Single-model converter for leer (v6.9.5 catmullrom fix)."""
import json
import os
import sys
import traceback

CONVERTER_DIR = "/tmp/my-project/subspace-work/SubspaceParasite"
if CONVERTER_DIR not in sys.path:
    sys.path.insert(0, CONVERTER_DIR)

from frontend.geckolib_parser import parse_geo_json, parse_animation_json
from backend.bbmodel_exporter import BBModelExporter
from engine.carry_forward import apply_carry_forward_all
from engine.idle_walk_merger import merge_idle_into_walk
from engine.walk_enhancer import enhance_walk_animations
from engine.catmullrom_baker import bake_all_animations
from engine.keyframe_simplifier import simplify_animations_v3 as simplify_animations
from core.types import AnimationIR
from engine.java_analyzer import analyze_model
from engine.mve_data_loader import get_mve_animations_for_model, has_mve_data
import config

# Import the namespace/loop fix from batch
sys.path.insert(0, os.path.join(CONVERTER_DIR, "batch"))
from mdo_srp import _apply_namespace_and_loop_semantics, _detect_stub_animations

INPUT_DIR = config.INPUT_DIR
DECOMPILED_DIR = config.DECOMPILED_DIR
MVE_DATA_DIR = config.MVE_DATA_DIR

NAME = "leer"
CATEGORY = "crude"
OUT_DIR = "/home/z/my-project/GFL/crude"
os.makedirs(OUT_DIR, exist_ok=True)

src_dir = os.path.join(INPUT_DIR, CATEGORY)

# Step 1: Parse geo_json
geo_path = os.path.join(src_dir, f"{NAME}.geo.json")
with open(geo_path, 'r', encoding='utf-8') as f:
    geo_data = json.load(f)
model_ir = parse_geo_json(geo_data)
print(f"bones={len(model_ir.bones)}")

# Step 2: Parse/merge animations (MVE + upstream)
animations_ir = []
mve_anim_names = set()
if has_mve_data(NAME, MVE_DATA_DIR):
    mve_anims, mve_raw = get_mve_animations_for_model(NAME, MVE_DATA_DIR)
    if mve_anims:
        animations_ir = mve_anims
        mve_anim_names = {a.name for a in mve_anims}
        print(f"mve={len(animations_ir)}")

anim_path = os.path.join(src_dir, f"{NAME}.animation.json")
if os.path.exists(anim_path):
    with open(anim_path, 'r', encoding="utf-8") as f:
        anim_data = json.load(f)
    anim_dict = parse_animation_json(anim_data, model_name=NAME)
    upstream_anims = list(anim_dict.values())
    upstream_anims, _ = _apply_namespace_and_loop_semantics(upstream_anims, NAME)
    name_lower = NAME.lower()
    for ua in upstream_anims:
        if f".{name_lower}." in ua.name:
            ua.name = ua.name.replace(f".{name_lower}.", f".{NAME}.")
        elif ua.name.endswith(f".{name_lower}"):
            ua.name = ua.name[:-(len(name_lower))] + NAME
    mve_anim_names_lower = {n.lower() for n in mve_anim_names}
    upstream_count = 0
    for ua in upstream_anims:
        if ua.name.lower() not in mve_anim_names_lower:
            animations_ir.append(ua)
            upstream_count += 1
    if upstream_count > 0:
        print(f"upstream={upstream_count}")

# Step 2b: Namespace + loop semantics
if animations_ir:
    animations_ir, _ = _apply_namespace_and_loop_semantics(animations_ir, NAME)

# Step 2c: Stub detection
if animations_ir:
    stubs = _detect_stub_animations(animations_ir, NAME)
    if stubs:
        print(f"STUB({len(stubs)})")

# Step 2d: Java trig analysis
model_meta = None
if os.path.isdir(DECOMPILED_DIR):
    try:
        model_meta = analyze_model(NAME, DECOMPILED_DIR)
        if model_meta and model_meta.head_tracking:
            print("head(✓)")
    except Exception as e:
        print(f"java_err({e})")

# Step 3: Carry-forward
if animations_ir:
    cf_stats = {}
    anim_dict = {a.name: a for a in animations_ir}
    cf_result = apply_carry_forward_all(anim_dict, NAME, cf_stats)
    animations_ir = list(cf_result.values())

# Step 3b: Idle-walk merger
if animations_ir:
    animations_ir = merge_idle_into_walk(animations_ir, NAME)

# Step 3c: Walk enhancer
if animations_ir:
    animations_ir = enhance_walk_animations(animations_ir, NAME)

# Step 3e: Bake + simplify
if animations_ir:
    animations_ir = bake_all_animations(animations_ir, NAME)
    animations_ir = simplify_animations(animations_ir, NAME)
    total_kf = sum(len(ba.keyframes) for a in animations_ir for ba in a.bones.values())
    print(f"after bake+rdp: {total_kf} keyframes")

# Step 4: Texture
tex_path = os.path.join(src_dir, f"{NAME}.png")
if not os.path.exists(tex_path):
    tex_path = None

# Step 5: Export
exporter = BBModelExporter()
bbmodel = exporter.export(
    model_ir,
    animations=animations_ir,
    texture_path=tex_path,
    texture_name=NAME,
    namespace='srparasites',
    model_metadata=model_meta,
)

out_path = os.path.join(OUT_DIR, f"{NAME}.bbmodel")
exporter.save(bbmodel, out_path)
print(f"SAVED: {out_path}")

# Verify
with open(out_path) as f:
    d = json.load(f)
for anim in d.get('animations', []):
    print(f"\nAnim: {anim['name']} len={anim['length']} loop={anim['loop']}")
    for aname, adat in list(anim.get('animators', {}).items())[:3]:
        kf = adat.get('keyframes', [])
        interps = sorted(set([k.get('interpolation') for k in kf]))
        chans = sorted(set([k.get('channel') for k in kf]))
        print(f"  {aname}: {len(kf)} kf, chans={chans}, interps={interps}")
    break
