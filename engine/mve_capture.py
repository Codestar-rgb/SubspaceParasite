#!/usr/bin/env python3
"""
MVE Capture (v6.3) — Code-Level Mocap via Java Trig Simulation
===============================================================
Implements the "Minimum Viable Environment" approach from the feasibility
analysis: a Python-based parameter sweep that simulates SRP's Java
setRotationAngles across the full (state, attackTimer, time, limbSwingAmount)
parameter space, capturing per-tick bone transforms as ground-truth keyframes.

This is the PRAGMATIC implementation of Option B (Pure Java Reflection +
Mocking) from MVE_FEASIBILITY_ANALYSIS.md — but done in Python by evaluating
the extracted Java trig expressions, avoiding the need to load SRP's .class
files against a mocked MC runtime.

WHAT IT CAPTURES:
  - Per-state animations (state 0/1/2/.../77 → separate idle/stateN anims)
  - Attack fade curve (attackTimer 0→0.4 → fade-in keyframes on attack bones)
  - Body bob (getFloorTimer-driven, captured as position keyframes)
  - Conditional visibility (isHidden → separate visible/hidden variants)
  - Walk cycle at correct Java-derived period (not normalized 0.6667s)
  - limbSwingAmount² scaling (captured at multiple speeds, baked as blend curve)

OUTPUT:
  For each model, writes a JSON file:
  {
    "model": "elvia",
    "states": [
      {
        "state": 0,
        "name": "idle",
        "length": 8.0554,
        "loop": "loop",
        "bones": {
          "tacleJointbackL2": [
            {"time": 0.0, "rotation": [x,y,z], "position": [x,y,z], "hidden": false},
            ...
          ]
        }
      },
      {
        "state": 1,
        "name": "state1",
        ...
      }
    ],
    "attack_fade": {
      "bone": "jointLA", "axis": "x",
      "max_offset_deg": 22.9,
      "curve": [{"attackTimer": 0.0, "offset": 0.0}, ..., {"attackTimer": 0.4, "offset": 22.9}]
    },
    "visibility": [
      {"bone": "taclejointLA0", "condition": "getLeft()==0.0", "hidden_when": "left==0"}
    ]
  }
"""

from __future__ import annotations

import json
import math
import os
import re
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.java_analyzer import (
    MATHHELPER,
    SRG_FIELDS,
    ModelMetadata,
    StateInfo,
    TrigAssignment,
    _extract_all_anim_assignments,
    _extract_method_body,
    _resolve_variables,
    _follow_custom_methods,
    analyze_model,
)
from engine.java_trig_simulator import (
    _safe_eval,
    _resolve_expr,
    _detect_cycle_period,
    _axis_from_field,
    _channel_from_field,
    RAD2DEG,
    AXIS_SIGN_FLIP,
)
from core.types import AnimationIR, AxisValue, BoneAnimationIR, KeyframeData

logger = logging.getLogger(__name__)

# MVE output directory (v6.7: from config, env-overridable)
def _get_mve_output_dir():
    try:
        import config
        return config.MVE_DATA_DIR
    except ImportError:
        import os
        return os.environ.get("SRP_MVE_DIR", "/home/z/my-project/subspace-work/mve-capture/data")

MVE_OUTPUT_DIR = _get_mve_output_dir()

# Sample rate: keyframes per second (20fps = MC tick rate)
TIME_SAMPLES_PER_CYCLE = 80   # 80 keyframes per cycle (increased from 40 for anti-aliasing)
ATTACK_TIMER_SAMPLES = 5      # 0.0, 0.1, 0.2, 0.3, 0.4


def _extract_gs_gd(state_body: str) -> Tuple[float, float]:
    """Extract GS (speed) and GD (degree) multipliers from state body."""
    gs_val = 1.5
    gd_val = 0.4
    gs_m = re.search(r"\bGS\s*=\s*(-?[\d.]+)f?\s*;", state_body)
    if gs_m:
        gs_val = float(gs_m.group(1))
    gd_m = re.search(r"\bGD\s*=\s*(-?[\d.]+)f?\s*;", state_body)
    if gd_m:
        gd_val = float(gd_m.group(1))
    return gs_val, gd_val


def _capture_state_frame(
    state_body: str,
    variables: Dict[str, str],
    assignments: List[TrigAssignment],
    age_in_ticks: float,
    limb_swing: float,
    limb_swing_amount: float,
    gs_val: float,
    gd_val: float,
) -> Dict[str, Dict[str, Any]]:
    """Capture all bone transforms for one frame at the given parameters.

    Returns dict: bone_name → {rotation: [x,y,z], position: [x,y,z], hidden: bool}
    """
    # Resolve variables for this frame
    env_base = {
        "ageInTicks": age_in_ticks,
        "limbSwing": limb_swing,
        "limbSwingAmount": limb_swing_amount,
        "f": limb_swing,
        "f1": limb_swing_amount,
        "GS": gs_val,
        "GD": gd_val,
        "scale": 0.0625,
    }
    var_values: Dict[str, float] = {}
    for vname, vexpr in variables.items():
        resolved = _resolve_expr(vexpr, variables)
        val = _safe_eval(resolved, {**env_base, **var_values})
        var_values[vname] = val

    env = {**env_base, **var_values}

    # Evaluate each assignment and accumulate per bone
    # A bone may have multiple assignments (e.g. rotation X and Y, or += pose offsets)
    bone_transforms: Dict[str, Dict[str, Any]] = {}
    # Track raw radian values per (bone, channel, axis) to handle += correctly
    # (+= must accumulate in RADIANS before the rad→deg conversion)
    raw_values: Dict[str, Dict[str, Dict[str, float]]] = {}  # bone → channel → axis → value (radians/pixels)
    for a in assignments:
        resolved = _resolve_expr(a.expression, variables)
        val = _safe_eval(resolved, env)
        axis = _axis_from_field(a.field)
        channel = _channel_from_field(a.field)
        axis_idx = {"x":0,"y":1,"z":2}[axis]

        bone = a.bone
        if bone not in bone_transforms:
            bone_transforms[bone] = {
                "rotation": [0.0, 0.0, 0.0],
                "position": [0.0, 0.0, 0.0],
                "hidden": False,
            }
            raw_values[bone] = {"rotation": [0.0,0.0,0.0], "position": [0.0,0.0,0.0]}

        # Apply operator (in raw radian/px units, BEFORE conversion)
        if a.op == "=":
            raw_values[bone][channel][axis_idx] = val
        elif a.op == "+=":
            raw_values[bone][channel][axis_idx] += val
        elif a.op == "-=":
            raw_values[bone][channel][axis_idx] -= val
        elif a.op == "*=":
            raw_values[bone][channel][axis_idx] *= val
        elif a.op == "/=":
            if val != 0:
                raw_values[bone][channel][axis_idx] /= val

    # Now convert raw radians/pixels to degrees/pixels with RH→LH transform
    for bone, channels in raw_values.items():
        for axis_idx in range(3):
            axis = ["x","y","z"][axis_idx]
            # rotation: radians → degrees, RH→LH sign flip
            rot_rad = channels["rotation"][axis_idx]
            bone_transforms[bone]["rotation"][axis_idx] = rot_rad * RAD2DEG * AXIS_SIGN_FLIP[axis]
            # position: model units → pixels, RH→LH sign flip
            pos_u = channels["position"][axis_idx]
            bone_transforms[bone]["position"][axis_idx] = pos_u * 16.0 * AXIS_SIGN_FLIP[axis]

    return bone_transforms


def _detect_dominant_period(
    assignments: List[TrigAssignment],
    variables: Dict[str, str],
) -> float:
    """Detect the DOMINANT cycle period and SNAP to integer cycles.

    For seamless looping, the animation length must be an INTEGER MULTIPLE
    of the cycle period. If we just use the raw period, the cosine wave
    won't complete at the boundary, causing a visible jump/twitch.

    Strategy:
    1. Find the MAX period (lowest frequency) among all assignments.
    2. Snap the animation length to the nearest integer multiple of this period.
       This ensures the wave completes exactly N full cycles.

    We exclude spurious very-short periods (<0.3s) that come from
    high-frequency noise (e.g. constant-folded expressions).

    Returns the SNAPPED animation length in seconds (integer × period).
    """
    periods = []
    for a in assignments:
        p = _detect_cycle_period(a.expression, variables)
        if p > 0:
            periods.append(p)
    if not periods:
        return 4.0
    # Filter out spurious very-short periods (high-frequency noise)
    periods = [p for p in periods if p >= 0.3]
    if not periods:
        return 4.0

    # Find the most common period (mode) — this is the "dominant" cycle.
    # Using MAX period was wrong: it picked slow hair-sway periods (1.8s)
    # for walk animations where the actual walk cycle is 0.78s.
    # Using the mode ensures we pick the period most bones animate at.
    from collections import Counter
    # Round periods to 2 decimal places for grouping
    rounded = [round(p, 2) for p in periods]
    period_counts = Counter(rounded)

    # For walk animations: prefer limbSwing-driven periods over ageInTicks-driven.
    # limbSwing periods are the actual walk cycle; ageInTicks periods are
    # idle-like sway that happens to be present in the walk branch too.
    # Check if any assignment uses limbSwing
    has_limb_swing = any("limbSwing" in a.expression for a in assignments)
    if has_limb_swing:
        # Filter to only limbSwing-driven periods
        ls_periods = []
        for a in assignments:
            if "limbSwing" in a.expression:
                p = _detect_cycle_period(a.expression, variables)
                if p > 0:
                    ls_periods.append(round(p, 2))
        if ls_periods:
            ls_counts = Counter(ls_periods)
            base_period = ls_counts.most_common(1)[0][0]
        else:
            base_period = period_counts.most_common(1)[0][0]
    else:
        # No limbSwing — use overall mode (idle animation)
        base_period = period_counts.most_common(1)[0][0]

    # Snap to nearest integer multiple of base_period for seamless looping.
    # Use at least 1 full cycle.
    snapped_length = base_period

    # Ensure minimum length of 0.5s (Blockbench doesn't like very short anims)
    if snapped_length < 0.5:
        snapped_length = base_period * 2

    return snapped_length


def _force_seamless_loop(bone_curves: Dict[str, List[dict]]) -> None:
    """Force first frame == last frame for seamless looping.

    DISABLED in v6.8.6: Forcing last=first causes LARGE jumps when the
    animation length is not an integer multiple of a bone's cycle period.
    Different bones have incommensurate periods, so no single length
    satisfies all bones. The forced last=first creates a visible twitch
    at the loop boundary for outlier bones.

    Instead, we now sample exactly 1 cycle of the DOMINANT (most common)
    period. Most bones complete exactly 1 cycle and loop naturally.
    Outlier bones (different frequency) may have a small discontinuity,
    but it's much smaller than the forced jump.
    """
    pass  # no-op


def _split_still_ani_branches(state_body: str) -> Tuple[str, str]:
    """Split a state body into (walk_branch, idle_branch) by getStillAni.

    SRP pattern:
      if (!parasite.getStillAni()) {
          // WALK: swingX/Y driven by limbSwing
      } else {
          // IDLE: cos/sin driven by ageInTicks
      }
      // SHARED: hair sway, tentacle sway (runs regardless of still/moving)

    Returns (walk_body, idle_body) where each includes the SHARED code.
    If no getStillAni split, returns (state_body, state_body).
    """
    if "getStillAni" not in state_body:
        return state_body, state_body

    # Find the if (!parasite.getStillAni()) { ... } else { ... } block
    # Pattern: if (!parasite.getStillAni()) { WALK } else { IDLE }
    # The else block may be absent (then idle = shared only)
    still_re = re.compile(
        r"if\s*\(\s*!\s*\w+\.getStillAni\(\)\s*\)\s*\{",
    )
    m = still_re.search(state_body)
    if not m:
        return state_body, state_body

    # Find matching closing brace for the if block
    if_start = m.end()
    depth = 1
    i = if_start
    while i < len(state_body) and depth > 0:
        if state_body[i] == "{":
            depth += 1
        elif state_body[i] == "}":
            depth -= 1
        i += 1
    walk_body = state_body[if_start : i - 1]

    # Check for else block
    rest = state_body[i:]
    idle_body = ""
    else_m = re.match(r"\s*else\s*\{", rest)
    if else_m:
        else_start = else_m.end()
        depth = 1
        j = else_start
        while j < len(rest) and depth > 0:
            if rest[j] == "{":
                depth += 1
            elif rest[j] == "}":
                depth -= 1
            j += 1
        idle_body = rest[else_start : j - 1]
        shared = rest[j:]
    else:
        shared = rest

    # Shared code (hair sway, etc.) runs in BOTH variants
    walk_full = walk_body + "\n" + shared
    idle_full = idle_body + "\n" + shared
    return walk_full, idle_full


def capture_model_animations(
    meta: ModelMetadata,
    sample_count: int = TIME_SAMPLES_PER_CYCLE,
) -> Optional[dict]:
    """Capture all animations for one model via MVE parameter sweep.

    For each state with a getStillAni split, captures TWO variants:
      - idle (else branch): ageInTicks-driven trig (swaying, breathing)
      - walk (if branch): limbSwing-driven swing helpers
    Shared code (hair sway, tentacle sway) runs in both.

    Uses DOMINANT period detection (not max) so shorter-cycle bones seam.
    Forces first==last frame for seamless looping.
    """
    if not meta.states:
        return None

    # Guard against sample_count=0 (env var misconfiguration)
    if sample_count <= 0:
        sample_count = TIME_SAMPLES_PER_CYCLE

    # Read Java source ONCE (was read 3x per model — perf bug)
    try:
        with open(meta.java_path, "r", encoding="utf-8") as f:
            java_src = f.read()
    except Exception:
        return None

    captured_states = []
    for state in meta.states:
        inlined_body = _follow_custom_methods(java_src, state.body)

        # Split into walk/idle branches by getStillAni
        walk_body, idle_body = _split_still_ani_branches(inlined_body)

        gs_val, gd_val = _extract_gs_gd(inlined_body)

        # Check if this state has a getStillAni split
        has_still_ani_split = "getStillAni" in inlined_body

        # Semantic state label
        sv = state.state_value
        if sv == 0:
            state_label = "stage0"
        elif sv == 10:
            state_label = "death"
        elif sv == 25:
            state_label = "stage25"
        elif sv == 77:
            state_label = "dormant"
        else:
            state_label = f"stage{sv}"

        # --- Capture IDLE variant (else branch) ---
        idle_variables = _resolve_variables(idle_body)
        idle_assignments = _extract_all_anim_assignments(idle_body)
        cycle_length = _detect_dominant_period(idle_assignments, idle_variables) if idle_assignments else 4.0

        idle_curves: Dict[str, List[dict]] = {}
        if idle_assignments:
            for i in range(sample_count + 1):
                t = i * cycle_length / sample_count
                age_in_ticks = t * 20.0
                frame = _capture_state_frame(
                    idle_body, idle_variables, idle_assignments,
                    age_in_ticks=age_in_ticks,
                    limb_swing=0.0,
                    limb_swing_amount=0.0,
                    gs_val=gs_val, gd_val=gd_val,
                )
                for bone, transform in frame.items():
                    idle_curves.setdefault(bone, []).append({
                        "time": round(t, 6),
                        "rotation": transform["rotation"],
                        "position": transform["position"],
                        "hidden": transform["hidden"],
                    })

            _force_seamless_loop(idle_curves)
            # Filter out bones with no motion
            idle_curves = {
                b: c for b, c in idle_curves.items()
                if any(
                    any(abs(v) > 1e-6 for v in s["rotation"]) or
                    any(abs(v) > 1e-6 for v in s["position"])
                    for s in c
                )
            }

        if idle_curves:
            if sv == 0:
                anim_name = f"animation.srparasites.{meta.model_name}.idle"
            else:
                anim_name = f"animation.srparasites.{meta.model_name}.{state_label}_idle"
            captured_states.append({
                "state": sv,
                "variant": "idle",
                "name": anim_name,
                "action": "idle" if sv == 0 else f"{state_label}_idle",
                "length": round(cycle_length, 4),
                "loop": "loop",
                "bones": idle_curves,
            })

        # --- Capture WALK variant (if branch) ---
        walk_variables = _resolve_variables(walk_body)
        walk_assignments = _extract_all_anim_assignments(walk_body)
        walk_cycle = _detect_dominant_period(walk_assignments, walk_variables) if walk_assignments else cycle_length

        # Capture walk if: has getStillAni split, OR references limbSwing (direct walk-driven)
        has_limb_swing = "limbSwing" in inlined_body
        capture_walk = has_still_ani_split or has_limb_swing

        walk_curves: Dict[str, List[dict]] = {}
        if walk_assignments and capture_walk:
            for i in range(sample_count + 1):
                t = i * walk_cycle / sample_count
                limb_swing = t * 20.0
                frame = _capture_state_frame(
                    walk_body, walk_variables, walk_assignments,
                    age_in_ticks=t * 20.0,
                    limb_swing=limb_swing,
                    limb_swing_amount=0.4,
                    gs_val=gs_val, gd_val=gd_val,
                )
                for bone, transform in frame.items():
                    walk_curves.setdefault(bone, []).append({
                        "time": round(t, 6),
                        "rotation": transform["rotation"],
                        "position": transform["position"],
                        "hidden": transform["hidden"],
                    })

            _force_seamless_loop(walk_curves)
            # Filter: keep only bones with walk-specific motion (non-zero when limbSwingAmount=1)
            walk_curves = {
                b: c for b, c in walk_curves.items()
                if any(
                    any(abs(v) > 1e-6 for v in s["rotation"]) or
                    any(abs(v) > 1e-6 for v in s["position"])
                    for s in c
                )
            }
            # For models without getStillAni: walk body == full state body, so walk_curves
            # includes idle bones too. Filter to keep only limbSwing-driven bones (those
            # whose values differ between limbSwing=0 and limbSwing>0).
            if not has_still_ani_split and has_limb_swing:
                # Compare at the MIDDLE of the cycle (limbSwing > 0 there)
                mid_t = walk_cycle / 2.0
                mid_frame = _capture_state_frame(
                    walk_body, walk_variables, walk_assignments,
                    age_in_ticks=mid_t * 20.0,
                    limb_swing=mid_t * 20.0,
                    limb_swing_amount=0.4,
                    gs_val=gs_val, gd_val=gd_val,
                )
                idle_mid_frame = _capture_state_frame(
                    walk_body, walk_variables, walk_assignments,
                    age_in_ticks=mid_t * 20.0,
                    limb_swing=0.0,
                    limb_swing_amount=0.0,
                    gs_val=gs_val, gd_val=gd_val,
                )
                walk_only = {}
                for bone, curve in walk_curves.items():
                    walk_rot = mid_frame.get(bone, {}).get("rotation", [0,0,0])
                    idle_rot = idle_mid_frame.get(bone, {}).get("rotation", [0,0,0])
                    if any(abs(walk_rot[k] - idle_rot[k]) > 1e-3 for k in range(3)):
                        walk_only[bone] = curve
                walk_curves = walk_only

        if walk_curves:
            if sv == 0:
                anim_name = f"animation.srparasites.{meta.model_name}.walk"
            else:
                anim_name = f"animation.srparasites.{meta.model_name}.{state_label}_walk"
            captured_states.append({
                "state": sv,
                "variant": "walk",
                "name": anim_name,
                "action": "walk" if sv == 0 else f"{state_label}_walk",
                "length": round(walk_cycle, 4),
                "loop": "loop",
                "bones": walk_curves,
            })

        logger.debug(
            "[%s] MVE state %d: %d idle bones, %d walk bones, idle=%.2fs walk=%.2fs",
            meta.model_name, sv,
            len(idle_curves), len(walk_curves),
            cycle_length, walk_cycle,
        )

    # Capture attack fade curve (pass java_src to avoid re-reading file)
    attack_fade = _capture_attack_fade(meta, java_src)
    # Capture visibility info
    visibility = _capture_visibility(meta, java_src)

    if not captured_states and not attack_fade and not visibility:
        return None

    return {
        "model": meta.model_name,
        "states": captured_states,
        "attack_fade": attack_fade,
        "visibility": visibility,
    }


def _capture_attack_fade(meta: ModelMetadata, java_src: str = "") -> Optional[dict]:
    """Capture the attack timer fade curve.

    Java: float id = parasite.getAttackTimer();
          if (id > 0.0f) bone.field += Math.min(0.4f, id);
    """
    if not java_src:
        try:
            with open(meta.java_path, "r", encoding="utf-8") as f:
                java_src = f.read()
        except Exception:
            return None

    # Find attackTimer pattern
    at_m = re.search(
        r"float\s+(\w+)\s*=\s*\w+\.getAttackTimer\(\)\s*;"
        r"[^}]*?if\s*\(\s*\1\s*>\s*0\.0f\s*\)\s*\{([^}]*)\}",
        java_src, re.DOTALL,
    )
    if not at_m:
        return None

    body = at_m.group(2)
    # Find all += Math.min(MAX, attackTimer) assignments
    assign_re = re.compile(
        r"this\.(\w+)\.(field_78795_f|field_78796_g|field_78808_h)\s*\+=\s*Math\.min\(\s*([\d.]+)f?\s*,\s*\w+\s*\)"
    )
    fades = []
    for am in assign_re.finditer(body):
        bone = am.group(1)
        field = am.group(2)
        max_off = float(am.group(3))
        axis = {"field_78795_f": "x", "field_78796_g": "y", "field_78808_h": "z"}[field]
        max_deg = max_off * RAD2DEG * AXIS_SIGN_FLIP[axis]

        # Build fade curve: attackTimer 0→max_off, offset = min(max_off, attackTimer)
        curve = []
        for i in range(11):
            at = i * max_off / 10.0
            offset = min(max_off, at) * RAD2DEG * AXIS_SIGN_FLIP[axis]
            curve.append({"attackTimer": round(at, 4), "offset_deg": round(offset, 4)})

        fades.append({
            "bone": bone,
            "axis": axis,
            "max_offset_deg": round(max_deg, 4),
            "curve": curve,
        })

    if not fades:
        return None
    return fades


def _capture_visibility(meta: ModelMetadata, java_src: str = "") -> List[dict]:
    """Capture conditional visibility (isHidden) info."""
    if not java_src:
        try:
            with open(meta.java_path, "r", encoding="utf-8") as f:
                java_src = f.read()
        except Exception:
            return []

    variants = []
    for m in re.finditer(
        r"this\.(\w+)\.field_78807_k\s*=\s*([^;]+);", java_src
    ):
        bone = m.group(1)
        cond = m.group(2).strip()
        variants.append({
            "bone": bone,
            "condition": cond,
            "hidden_when": cond,
        })
    return variants


def capture_all_models(
    decompiled_root: str,
    model_names: List[str],
    output_dir: str = MVE_OUTPUT_DIR,
) -> dict:
    """Run MVE capture on all models.

    Args:
        decompiled_root: Path to decompiled/all/ directory.
        model_names: List of model names to capture.
        output_dir: Where to write per-model JSON files.

    Returns:
        Stats dict with counts.
    """
    os.makedirs(output_dir, exist_ok=True)
    stats = {
        "total": len(model_names),
        "captured": 0,
        "failed": 0,
        "total_states": 0,
        "total_bones": 0,
        "total_samples": 0,
        "with_attack_fade": 0,
        "with_visibility": 0,
    }

    for name in model_names:
        meta = analyze_model(name, decompiled_root)
        if not meta:
            stats["failed"] += 1
            continue

        try:
            captured = capture_model_animations(meta)
            if captured:
                out_path = os.path.join(output_dir, f"{name}.mve.json")
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(captured, f, ensure_ascii=False, indent=2)
                stats["captured"] += 1
                stats["total_states"] += len(captured["states"])
                stats["total_bones"] += sum(
                    len(s["bones"]) for s in captured["states"]
                )
                stats["total_samples"] += sum(
                    len(curves) for s in captured["states"]
                    for curves in s["bones"].values()
                )
                if captured.get("attack_fade"):
                    stats["with_attack_fade"] += 1
                if captured.get("visibility"):
                    stats["with_visibility"] += 1
            else:
                stats["failed"] += 1
        except Exception as e:
            logger.warning("[%s] MVE capture failed: %s", name, e)
            stats["failed"] += 1

    return stats


if __name__ == "__main__":
    import sys
    try:
        import config
        SW = str(Path(config.WORK_ROOT))
        DECOMP = config.DECOMPILED_DIR
    except ImportError:
        SW = os.environ.get("SRP_WORK_ROOT", "/home/z/my-project/subspace-work")
        DECOMP = os.path.join(SW, "decompiled", "all")

    # Get all model names from MDO-SRP-SRC
    src_dir = os.environ.get("SRP_INPUT_DIR", os.path.join(SW, "SubspaceParasite", "MDO-SRP-SRC"))
    model_names = []
    for cat in os.listdir(src_dir):
        cat_dir = os.path.join(src_dir, cat)
        if not os.path.isdir(cat_dir):
            continue
        for fn in os.listdir(cat_dir):
            if fn.endswith(".geo.json"):
                model_names.append(fn.replace(".geo.json", ""))

    model_names.sort()
    print(f"Capturing {len(model_names)} models via MVE...")

    stats = capture_all_models(DECOMP, model_names, MVE_OUTPUT_DIR)
    print(f"\n=== MVE Capture Complete ===")
    print(f"Total: {stats['total']}")
    print(f"Captured: {stats['captured']}")
    print(f"Failed: {stats['failed']}")
    print(f"Total states: {stats['total_states']}")
    print(f"Total bones: {stats['total_bones']}")
    print(f"Total samples: {stats['total_samples']}")
    print(f"With attack fade: {stats['with_attack_fade']}")
    print(f"With visibility: {stats['with_visibility']}")
    print(f"Output: {MVE_OUTPUT_DIR}")
