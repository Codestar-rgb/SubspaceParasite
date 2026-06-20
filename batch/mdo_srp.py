#!/usr/bin/env python3
"""
Super Converter — MDO-SRP Batch Converter
==========================================
Converts all model sets from MDO-SRP-SRC into Blockbench .bbmodel files
using the new Super Architecture converter pipeline.

Input (MDO-SRP-SRC/category/name):
  - name.geo.json        (Bedrock geometry)
  - name.animation.json  (GeckoLib animation, optional)
  - name.png             (texture, optional)

Output (MDO-SRP/category/name.bbmodel):
  - name.bbmodel         (Blockbench project file)

Pipeline:
  Frontend (Parse) → Engine (Validate/Transform) → Backend (Export)

Improvements over old batch converter:
  - Quaternion-based rotation handling (no gimbal lock)
  - Explicit carry-forward (distinguishes 0.0 from "no data")
  - Period analysis for seamless loop alignment
  - Unified IR data flow (no raw dicts between stages)
  - Robust per-model/per-bone error recovery
"""

import json
import os
import sys
import time
import traceback

# Ensure the super-converter package is importable
CONVERTER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CONVERTER_DIR not in sys.path:
    sys.path.insert(0, CONVERTER_DIR)

from frontend.geckolib_parser import parse_geo_json, parse_animation_json
from backend.bbmodel_exporter import BBModelExporter
from engine.carry_forward import apply_carry_forward_all
from engine.idle_walk_merger import merge_idle_into_walk
# loop_extender removed in v6.9.2 (was no-op)
from engine.walk_enhancer import enhance_walk_animations
from engine.catmullrom_baker import bake_all_animations
from engine.keyframe_simplifier import simplify_animations
from core.types import AnimationIR
from engine.java_analyzer import analyze_model, ModelMetadata
from engine.java_trig_simulator import simulate_idle
from engine.mve_data_loader import get_mve_animations_for_model, has_mve_data
import config


# ============================================================================
# Configuration (v6.7 — sourced from config.py, env-overridable)
# ============================================================================

INPUT_DIR = config.INPUT_DIR
DECOMPILED_DIR = config.DECOMPILED_DIR
MVE_DATA_DIR = config.MVE_DATA_DIR
OUTPUT_DIR = config.OUTPUT_DIR

# v6.1 — Animation namespace for output animation names.
# Original SRP mod uses GeckoLib convention: animation.srparasites.<name>.<action>
# Source MDO-SRP-SRC data uses animation.<name>.<action> (no namespace).
# We inject the 'srparasites' namespace to match the original mod.
ANIMATION_NAMESPACE = "srparasites"

# v6.1 — Loop mode semantic correction.
# The reverse-engineered source data marks ALL non-`hold_on_last_frame` animations
# as `loop`. But in the original SRP Java code, several animation types are
# TRANSIENT (play once, hold final pose) driven by entity state changes:
#   - attack   (25 anims): driven by getAttackTimer() — a transient counter
#     that decrements; the arm-pose overlay fades in then out. As a standalone
#     bbmodel animation it should play once and HOLD the final attack pose.
#   - death    (12 anims): driven by getParasiteStatus()==10 — entity enters
#     a rigid death pose. Should play once and hold (never loop back to alive).
#   - stage6   ( 4 anims): state-transition to evolution stage 6.
#   - stage25  ( 5 anims): state-transition to evolution stage 25.
#   - evolved  (16 anims): state-transition to evolved form.
# These are remapped from `loop` → `hold` so Blockbench plays them once and
# holds the last frame, matching the original mod's transient semantics.
# Animations NOT in this set (idle, walk, sleeping, open, closed, dormant,
# cosmic, shaking, fly) remain `loop` — they're continuous states.
TRANSIENT_ACTIONS: set = {"attack", "death", "stage6", "stage25", "evolved"}

# v6.1 — Stub animation detection.
# Some source models (e.g. misc/tendrilDragonERW, projectile/dropPod) have
# stub animations: 1 root bone with ≤2 keyframes and all-zero/identical values.
# These are placeholders where the upstream reverse-engineering failed to
# capture the Java setRotationAngles logic. We detect and flag them so users
# know which models need manual attention.
STUB_MAX_BONES = 2
STUB_MAX_KEYFRAMES_PER_BONE = 2
STUB_VALUE_TOLERANCE = 0.001


def _apply_namespace_and_loop_semantics(
    animations: list,
    model_name: str,
) -> tuple:
    """Apply v6.1 fidelity fixes to animation names and loop modes.

    1. NAMESPACE: Rename `animation.<name>.<action>` → `animation.srparasites.<name>.<action>`.
       Original SRP mod uses the `srparasites` GeckoLib namespace.
       Source data lacks it; we inject it to match the mod convention.
       Idempotent: if already namespaced, no change.

    2. LOOP SEMANTICS: Remap transient animations from `loop` → `hold`.
       attack/death/stage6/stage25/evolved are transient in the original Java
       (driven by getAttackTimer / state changes). Source data erroneously
       marks them `loop`; we correct to `hold` (play once, hold last frame).

    Args:
        animations: List of AnimationIR.
        model_name: Model name for logging.

    Returns:
        (corrected_animations, stats_dict) where stats_dict has:
          - namespace_renamed: int
          - loop_corrected: dict[action -> count]
    """
    ns = ANIMATION_NAMESPACE
    renamed = 0
    loop_corrected = {}
    result = []

    for anim in animations:
        # --- Namespace fix ---
        new_name = anim.name
        # Match: animation.<name>.<action>  (no namespace yet)
        # Skip: animation.srparasites.<name>.<action> (already namespaced)
        if anim.name.startswith("animation.") and not anim.name.startswith(f"animation.{ns}."):
            # Insert namespace after 'animation.'
            rest = anim.name[len("animation."):]
            new_name = f"animation.{ns}.{rest}"
            if new_name != anim.name:
                renamed += 1

        # --- Loop semantic fix ---
        new_loop = anim.loop
        # Extract action = last segment of the (original) name
        parts = anim.name.split(".")
        action = parts[-1] if parts else ""
        if action in TRANSIENT_ACTIONS and anim.loop == "loop":
            new_loop = "hold"
            loop_corrected[action] = loop_corrected.get(action, 0) + 1

        if new_name != anim.name or new_loop != anim.loop:
            result.append(AnimationIR(
                name=new_name,
                loop=new_loop,
                length=anim.length,
                bones=anim.bones,
                period=anim.period,
            ))
        else:
            result.append(anim)

    return result, {"namespace_renamed": renamed, "loop_corrected": loop_corrected}


def _detect_stub_animations(
    animations: list,
    model_name: str,
) -> list:
    """Detect stub/placeholder animations (v6.1).

    A stub animation has very few bones (≤ STUB_MAX_BONES) and very few
    keyframes per bone (≤ STUB_MAX_KEYFRAMES_PER_BONE), with all values
    near-zero or identical. These indicate the upstream reverse-engineering
    failed to capture the Java setRotationAngles logic.

    Args:
        animations: List of AnimationIR.
        model_name: Model name for logging.

    Returns:
        List of stub animation names.
    """
    stubs = []
    for anim in animations:
        if len(anim.bones) > STUB_MAX_BONES:
            continue
        if not anim.bones:
            continue
        is_stub = True
        for bone_anim in anim.bones.values():
            if len(bone_anim.keyframes) > STUB_MAX_KEYFRAMES_PER_BONE:
                is_stub = False
                break
            # Check all values are near-zero or identical
            all_vals = []
            for kf in bone_anim.keyframes:
                for ch in ("x", "y", "z"):
                    ax = getattr(kf, ch, None)
                    if ax is not None and ax.explicit:
                        all_vals.append(ax.value)
            if all_vals:
                vmin = min(all_vals)
                vmax = max(all_vals)
                if vmax - vmin > STUB_VALUE_TOLERANCE:
                    is_stub = False
                    break
                if abs(vmax) > STUB_VALUE_TOLERANCE:
                    # All same non-zero value — still a stub (static pose)
                    pass
        if is_stub:
            stubs.append(anim.name)
    return stubs


def batch_convert_mdo_srp(
    input_dir: str = INPUT_DIR,
    output_dir: str = OUTPUT_DIR,
) -> dict:
    """Run the MDO-SRP batch conversion using the Super Architecture converter.

    Args:
        input_dir: Directory containing source geo.json + animation.json + PNG files.
        output_dir: Directory for output .bbmodel files.

    Returns:
        Dict with conversion statistics.
    """
    print("=" * 70)
    print("  Super Converter — MDO-SRP Batch Conversion")
    print("  Pipeline: Parse → AxisTransform → Export")
    print("=" * 70)
    print()

    if not os.path.isdir(input_dir):
        print(f"ERROR: Input directory not found: {input_dir}")
        sys.exit(1)

    # Initialize exporter
    exporter = BBModelExporter()
    print("  [OK] Loaded BBModel Exporter")
    print()

    # Find all .geo.json files
    geo_files = []
    for root, dirs, files in os.walk(input_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fname in sorted(files):
            if fname.endswith('.geo.json'):
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, input_dir)
                geo_files.append(rel_path)

    geo_files.sort()

    # Deduplicate case-variant models (e.g., dodSII vs dodsii)
    # When both uppercase and lowercase versions exist with the same
    # lowercased name, prefer the LOWERCASE version (full-detail animation).
    # The uppercase versions are LOD/simplified variants with fewer keyframes.
    seen_lower: Dict[str, str] = {}  # lowercased_rel_path -> actual rel_path
    deduped_geo_files = []
    skipped_duplicates = 0
    for rel_path in geo_files:
        lower_path = rel_path.lower()
        if lower_path in seen_lower:
            existing = seen_lower[lower_path]
            # If existing is already lowercase and current is mixed-case, skip current
            if existing == lower_path and rel_path != lower_path:
                skipped_duplicates += 1
                print(f"  [DEDUP] Skipping uppercase variant: {rel_path} (keeping {existing})")
                continue
            # If current is lowercase and existing is mixed-case, replace
            elif rel_path == lower_path and existing != lower_path:
                print(f"  [DEDUP] Replacing: {existing} → {rel_path} (lowercase preferred)")
                seen_lower[lower_path] = rel_path
                deduped_geo_files = [rel_path if p == existing else p for p in deduped_geo_files]
                continue
            else:
                # Both same case or both different — keep both
                seen_lower[lower_path] = rel_path
                deduped_geo_files.append(rel_path)
        else:
            seen_lower[lower_path] = rel_path
            deduped_geo_files.append(rel_path)

    if skipped_duplicates > 0:
        print(f"  Deduplicated {skipped_duplicates} case-variant models (kept lowercase/full-detail versions)")
    geo_files = deduped_geo_files
    print(f"  Found {len(geo_files)} models in {input_dir}")
    print(f"  Output: {output_dir}")
    print()

    # Clean output directory
    import shutil
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Statistics
    stats = {
        'total': len(geo_files),
        'ok': 0,
        'fail': 0,
        'has_anim': 0,
        'has_tex': 0,
        'errors': [],          # fatal errors (model skipped)
        'warnings': [],        # non-fatal warnings (model converted with issues)
        'categories': {},
        'engine_stats': {
            'total_keyframes': 0,
            'total_bones': 0,
            'total_animations': 0,
            'carry_forward_applied': 0,
            'loop_alignments': 0,
            'rotations_normalized': 0,
            'periods_detected': 0,
            'warnings': 0,
        },
    }

    start_time = time.time()

    for i, rel_path in enumerate(geo_files, 1):
        category = os.path.dirname(rel_path)
        name = os.path.basename(rel_path).replace('.geo.json', '')
        src_dir = os.path.join(input_dir, category) if category else input_dir
        out_dir = os.path.join(output_dir, category) if category else output_dir

        os.makedirs(out_dir, exist_ok=True)

        # Track categories
        if category not in stats['categories']:
            stats['categories'][category] = {'total': 0, 'ok': 0, 'fail': 0}
        stats['categories'][category]['total'] += 1

        print(f"  [{i:3d}/{stats['total']}] {category}/{name}...", end=" ", flush=True)
        status_parts = []

        try:
            # ---- Step 1: Parse geo.json ----
            geo_path = os.path.join(src_dir, f"{name}.geo.json")
            with open(geo_path, 'r', encoding='utf-8') as f:
                geo_data = json.load(f)

            model_ir = parse_geo_json(geo_data)
            status_parts.append(f"bones={len(model_ir.bones)}")

            # ---- Step 2: Parse animation.json (optional) ----
            # v6.4: MERGE MVE-captured data WITH upstream JSON (not replace).
            # Upstream JSON has named animations (walk/attack/sleeping/stage25)
            # that MVE may not capture. MVE adds per-state-per-variant animations
            # (idle/walk for each state) with ground-truth trig.
            # Merge logic: start with MVE, then add upstream anims that don't
            # conflict by name (upstream walk/attack/sleeping kept if MVE
            # doesn't have same-named anim).
            animations_ir = []
            used_mve = False
            mve_raw = None
            mve_anim_names = set()
            if has_mve_data(name, MVE_DATA_DIR):
                mve_anims, mve_raw = get_mve_animations_for_model(name, MVE_DATA_DIR)
                if mve_anims:
                    animations_ir = mve_anims
                    used_mve = True
                    mve_anim_names = {a.name for a in mve_anims}
                    stats['has_anim'] += 1
                    status_parts.append(f"mve={len(animations_ir)}")

            # Load upstream JSON and MERGE (add anims not already in MVE)
            upstream_count = 0
            anim_path = os.path.join(src_dir, f"{name}.animation.json")
            if os.path.exists(anim_path):
                try:
                    with open(anim_path, 'r', encoding="utf-8") as f:
                        anim_data = json.load(f)
                    anim_dict = parse_animation_json(anim_data, model_name=name)
                    upstream_anims = list(anim_dict.values())
                    # Apply namespace fix to upstream anims before merging
                    upstream_anims, _ = _apply_namespace_and_loop_semantics(upstream_anims, name)
                    # Normalize upstream anim names to use the correct model name casing
                    # (upstream JSON uses lowercase like 'fervillager', but the model
                    # name is CamelCase like 'ferVillager'). This prevents duplicate
                    # anims that differ only in case.
                    name_lower = name.lower()
                    for ua in upstream_anims:
                        # Replace lowercase model name with actual model name in anim name
                        # e.g. animation.srparasites.fervillager.walk → animation.srparasites.ferVillager.walk
                        if f".{name_lower}." in ua.name:
                            ua.name = ua.name.replace(f".{name_lower}.", f".{name}.")
                        elif ua.name.endswith(f".{name_lower}"):
                            ua.name = ua.name[:-(len(name_lower))] + name
                    # Case-insensitive dedup: skip upstream anims that match an MVE anim
                    # (ignoring case differences in the model name portion)
                    mve_anim_names_lower = {n.lower() for n in mve_anim_names}
                    for ua in upstream_anims:
                        if ua.name.lower() not in mve_anim_names_lower:
                            animations_ir.append(ua)
                            mve_anim_names.add(ua.name)
                            mve_anim_names_lower.add(ua.name.lower())
                            upstream_count += 1
                    if not used_mve:
                        stats['has_anim'] += 1
                    if upstream_count > 0:
                        status_parts.append(f"upstream={upstream_count}")
                except Exception as e:
                    if not used_mve:
                        status_parts.append(f"anim_err({e})")
            elif not used_mve:
                status_parts.append("no_anim")

            # ---- Step 2b (v6.1): Namespace + loop-semantic fixes ----
            # Inject 'srparasites' namespace into animation names to match
            # the original SRP mod's GeckoLib convention.
            # Remap transient animations (attack/death/stage*/evolved) from
            # `loop` → `hold` to match the original Java transient semantics.
            if animations_ir:
                animations_ir, fixup_stats = _apply_namespace_and_loop_semantics(
                    animations_ir, name
                )
                nr = fixup_stats["namespace_renamed"]
                lc = fixup_stats["loop_corrected"]
                if nr > 0:
                    status_parts.append(f"ns_fix({nr})")
                if lc:
                    lc_str = ",".join(f"{a}:{c}" for a, c in sorted(lc.items()))
                    status_parts.append(f"loop_fix({lc_str})")

            # ---- Step 2c (v6.1): Stub animation detection ----
            # Flag placeholder animations (few bones, few keyframes, all-zero)
            # so users know which models need manual attention.
            is_stub_model = False
            if animations_ir:
                stubs = _detect_stub_animations(animations_ir, name)
                if stubs:
                    is_stub_model = True
                    status_parts.append(f"STUB({len(stubs)})")
                    if 'stubs' not in stats:
                        stats['stubs'] = []
                    for s in stubs:
                        stats['stubs'].append(f"{category}/{name}: {s}")

            # ---- Step 2d (v6.2): Java trig analysis + stub recovery ----
            # Analyze the decompiled Java ModelX.class to extract:
            #   - Head tracking (netHeadYaw/headPitch → Molang)
            #   - State machine (getParasiteStatus branches)
            #   - Direct trig assignments (for stub recovery)
            # For stub models, simulate the Java trig to generate real keyframes.
            model_meta = None
            if os.path.isdir(DECOMPILED_DIR):
                try:
                    model_meta = analyze_model(name, DECOMPILED_DIR)
                except Exception as e:
                    status_parts.append(f"java_err({e})")
                    stats['warnings'].append(f"{category}/{name}: Java analysis failed: {e}")

                if model_meta:
                    # Stub recovery: if the upstream extraction produced a stub,
                    # replace it with a simulated idle from the Java trig.
                    if is_stub_model and model_meta.has_stub_friendly_trig:
                        simulated = simulate_idle(model_meta, sample_count=40)
                        if simulated and simulated.bones:
                            # Remove stub animations and use the simulated one
                            animations_ir = [simulated]
                            status_parts.append(
                                f"sim_recovery({len(simulated.bones)}b,{sum(len(b.keyframes) for b in simulated.bones.values())}kf)"
                            )
                            stats['stub_recovered'] = stats.get('stub_recovered', 0) + 1

                    # Report Java analysis findings
                    if model_meta.head_tracking:
                        status_parts.append(f"head(✓)")
                    if len(model_meta.states) > 1:
                        status_parts.append(f"states({len(model_meta.states)})")

                    # v6.3 — Runtime behavior detection (reported after export)
                    try:
                        from engine.runtime_behavior_injector import (
                            extract_attack_fade, extract_body_bob, extract_visibility_variants
                        )
                        fades = extract_attack_fade(model_meta)
                        bobs = extract_body_bob(model_meta)
                        vis = extract_visibility_variants(model_meta)
                        if fades:
                            status_parts.append(f"atk_fade({len(fades)})")
                        if bobs:
                            status_parts.append(f"bob({len(bobs)})")
                        if vis:
                            status_parts.append(f"vis({len(vis)})")
                    except Exception:
                        pass

            # ---- Step 3: Interpolation-aware carry-forward ----
            # GeckoLib animates each axis independently with its own time series.
            # When merging per-axis keyframes into unified time points, axes that
            # don't have data at a given time need to be FILLED IN via interpolation
            # from their own curve — NOT by carrying forward the last explicit value
            # (which creates step-function artifacts / HOLD-then-SNAP patterns).
            #
            # The engine carry_forward module uses CatmullRom for rotation channels
            # and linear for position/scale, matching GeckoLib's runtime behavior.
            # This is the CRITICAL fix for walk animation flickering/jumping.
            #
            # We do NOT use the full engine pipeline (which inserts sub-frames),
            # just the carry-forward step to fill missing axis values correctly.

            if animations_ir:
                cf_stats = {}
                anim_dict = {a.name: a for a in animations_ir}
                cf_result = apply_carry_forward_all(anim_dict, name, cf_stats)
                animations_ir = list(cf_result.values())

                # Log carry-forward stats
                axes_filled = cf_stats.get('axes_filled', 0)
                axes_interpolated = cf_stats.get('axes_interpolated', 0)
                if axes_filled > 0 or axes_interpolated > 0:
                    status_parts.append(f"cf({axes_interpolated}i,{axes_filled}f)")

            # ---- Step 3b: Idle-walk merger ----
            # The SRP mod uses GeckoLib animation LAYERING: idle (arm/tentacle/
            # hair/tail sway) always plays, and walk (leg rotation + body bob)
            # overlays on top when moving. In Blockbench .bbmodel format, there's
            # no layering — animations are standalone. This merger step merges
            # idle animation data INTO walk animations so the converted walk
            # includes arm sway and other idle-driven motion that makes it look
            # complete rather than "slight foot lifts".
            #
            # Must run AFTER carry-forward (so axis range heuristic works) and
            # BEFORE walk_enhancer (so walk_enhancer sees the merged animation).

            if animations_ir:
                animations_ir = merge_idle_into_walk(animations_ir, name)
                idle_merged = sum(1 for a in animations_ir
                                  if 'walk' in a.name.lower()
                                  and len(a.bones) > 0)
                if idle_merged > 0:
                    status_parts.append(f"idle_merge({idle_merged})")

            # ---- Step 3c: Walk animation enhancement ----
            # Many SRP walk animations are "overlay-only" with very small rotation
            # ranges (<5°). The main walking motion comes from the Java entity
            # code that programmatically rotates leg bones. When converted to
            # Blockbench, this programmatic rotation is lost, leaving only the
            # subtle overlay. The walk enhancer generates synthetic walk cycles
            # for leg bones and adds them to the existing animation values.

            if animations_ir:
                animations_ir = enhance_walk_animations(animations_ir, name)
                walk_enhanced = sum(1 for a in animations_ir if 'walk' in a.name.lower())
                if walk_enhanced > 0:
                    status_parts.append(f"walk_enh({walk_enhanced})")

            # ---- Step 3d: Loop animation (removed v6.9.2) ----
            # loop_extender was a no-op since v6.1, removed in v6.9.2.

            # ---- Step 3e: Bake CatmullRom to linear keyframes ----
            # Blockbench issue #1965: CatmullRom interpolation in looping
            # animations has a known tangent discontinuity at the loop
            # boundary. The Bedrock format does NOT enable animation_loop_wrapping,
            # causing wrong control points at the boundary.
            # Fix: Bake CatmullRom curves into dense linear keyframes.
            # This eliminates the CatmullRom wrapping problem entirely because
            # linear interpolation has no tangent/control point dependencies.

            if animations_ir:
                animations_ir = bake_all_animations(animations_ir, name)
                # v6.9: RDP keyframe simplification (reduces 60-80% keyframes)
                animations_ir = simplify_animations(animations_ir, name)
                simplified_kf = sum(len(ba.keyframes) for a in animations_ir for ba in a.bones.values())
                if simplified_kf > 0:
                    status_parts.append(f"rdp({simplified_kf})")
                # Count baked keyframes
                total_kf = sum(len(ba.keyframes) for a in animations_ir for ba in a.bones.values())
                if total_kf > 0:
                    cr_kf = sum(1 for a in animations_ir for ba in a.bones.values()
                                for kf in ba.keyframes if kf.interpolation == "catmullrom")
                    lin_kf = total_kf - cr_kf
                    if cr_kf > 0:
                        status_parts.append(f"bake({cr_kf}cr→{lin_kf}lin)")
                    else:
                        status_parts.append(f"all_lin({lin_kf})")

            # Count keyframes for stats
            if animations_ir:
                kf_count = sum(len(ba.keyframes) for a in animations_ir for ba in a.bones.values())
                stats['engine_stats']['total_keyframes'] += kf_count
                stats['engine_stats']['total_bones'] += sum(len(a.bones) for a in animations_ir)
                stats['engine_stats']['total_animations'] += len(animations_ir)
                if kf_count > 0:
                    status_parts.append(f"kf={kf_count}")

            # ---- Step 4: Find texture PNG (optional) ----
            tex_path = os.path.join(src_dir, f"{name}.png")
            if os.path.exists(tex_path):
                stats['has_tex'] += 1
                status_parts.append("tex=YES")
            else:
                tex_path = None
                status_parts.append("tex=NO")

            # ---- Step 5: Export to .bbmodel ----
            bbmodel = exporter.export(
                model_ir,
                animations=animations_ir,
                texture_path=tex_path,
                texture_name=name,
                namespace='srparasites',
                model_metadata=model_meta,
            )

            # Save
            out_path = os.path.join(out_dir, f"{name}.bbmodel")
            exporter.save(bbmodel, out_path)

            stats['ok'] += 1
            stats['categories'][category]['ok'] += 1

            elements = bbmodel.get('elements', [])
            animations = bbmodel.get('animations', [])
            file_size = os.path.getsize(out_path)
            status_parts.append(f"bbmodel({len(elements)}e, {len(animations)}a, {file_size/1024:.0f}KB)")

        except Exception as e:
            stats['fail'] += 1
            stats['categories'][category]['fail'] += 1
            status_parts.append(f"ERROR: {e}")
            stats['errors'].append(f"{category}/{name}: {traceback.format_exc()}")

        print(" | ".join(status_parts))

        # Periodic GC
        if i % 20 == 0:
            import gc
            gc.collect()

    elapsed = time.time() - start_time

    # Summary
    print()
    print("=" * 70)
    print("  SUPER CONVERTER — BATCH CONVERSION SUMMARY")
    print("=" * 70)
    print(f"  Total models:           {stats['total']}")
    print(f"  Converted OK:           {stats['ok']}")
    print(f"  Failed:                 {stats['fail']}")
    print(f"  With animations:        {stats['has_anim']}")
    print(f"  With textures:          {stats['has_tex']}")
    print()

    es = stats['engine_stats']
    if es['total_animations'] > 0:
        print(f"  --- Animation Engine (Super Architecture) ---")
        print(f"  Total animations:       {es['total_animations']}")
        print(f"  Total keyframes:        {es['total_keyframes']}")
        print(f"  Total animated bones:   {es['total_bones']}")
        print(f"  Carry-forward fixes:    {es['carry_forward_applied']}")
        print(f"  Loop alignments:        {es['loop_alignments']}")
        print(f"  Rotations normalized:   {es['rotations_normalized']}")
        print(f"  Periods detected:       {es['periods_detected']}")
        print(f"  Conversion warnings:    {es['warnings']}")
        print()

    print(f"  --- By Category ---")
    for cat in sorted(stats['categories'].keys()):
        cs = stats['categories'][cat]
        print(f"  {cat}: {cs['ok']}/{cs['total']} OK")
    print()
    print(f"  Output: {output_dir}")
    print(f"  Elapsed: {elapsed:.1f}s")

    if stats['errors']:
        print(f"\n  Errors ({len(stats['errors'])}):")
        for e in stats['errors'][:10]:
            first_line = e.split('\n')[0]
            print(f"    X {first_line}")
        if len(stats['errors']) > 10:
            print(f"    ... and {len(stats['errors']) - 10} more")

    # v6.8 — Warnings report (non-fatal issues)
    if stats.get('warnings'):
        print(f"\n  Warnings ({len(stats['warnings'])}):")
        for w in stats['warnings'][:10]:
            print(f"    ! {w}")
        if len(stats['warnings']) > 10:
            print(f"    ... and {len(stats['warnings']) - 10} more")

    # v6.1 — Stub animation report
    stubs = stats.get('stubs', [])
    if stubs:
        print(f"\n  --- Stub Animations ({len(stubs)}) ---")
        print(f"  These are placeholder animations (few bones, few keyframes,")
        print(f"  all-zero/identical values). The upstream reverse-engineering")
        print(f"  failed to capture the Java setRotationAngles logic for these.")
        print(f"  They need manual animation work in Blockbench:")
        for s in stubs[:20]:
            print(f"    ! {s}")
        if len(stubs) > 20:
            print(f"    ... and {len(stubs) - 20} more")

    print()
    print("=" * 70)
    print("  DONE — Super Converter v6.1 batch conversion complete!")
    print(f"  Output: {output_dir}")
    print("=" * 70)

    return stats


if __name__ == "__main__":
    result = batch_convert_mdo_srp()
    sys.exit(0 if result['fail'] == 0 else 1)
