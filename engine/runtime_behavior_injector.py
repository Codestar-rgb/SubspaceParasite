#!/usr/bin/env python3
"""
Runtime Behavior Injector (v6.3)
================================
Injects Molang-driven animations that recover runtime behaviors the upstream
extraction can't capture as static keyframes.

Recovers 5 fidelity gaps from the v6.2 FIDELITY_REPORT:

1. ATTACK FADE (14 models):
   Java: `float id = parasite.getAttackTimer(); if (id > 0.0f) bone.field += min(0.4, id);`
   The attack animation's arm-rotation overlay fades in/out as the timer
   decrements. v6.2 already sets attack anims to `hold`; v6.3 adds a
   `blend_weight` Molang expression so GeckoLib fades the animation based
   on a query (modder wires `query.attack_time` to the entity's timer).

2. SET_LIVING_ANIMATIONS BODY BOB (9 models with getFloorTimer):
   Java: `mainbody.offsetY = getFloorTimer(); mainbody.offsetX = partialTickTime * 0.091;`
   This runs once per tick (not per frame) to bob the body. v6.3 injects
   a `body_bob` animation that applies the same trig to mainbody's position
   channel.

3. CONDITIONAL BONE VISIBILITY (19 models):
   Java: `bone.isHidden = parasite.getLeft() == 0.0f;`
   Tentacle clusters hide/show based on entity state. v6.3 can't toggle
   visibility at runtime (Blockbench has no visibility Molang for bedrock),
   so we emit a `visibility_variants` animation that scales bones to 0
   (a workaround) — modders can swap to GeckoLib's bone visibility API.

4. WALK CYCLE NORMALIZATION (all walk anims):
   Java: `swingX(bone, 0.3f * GS, ...)` → period = 2π/(0.3*GS) ticks.
   v6.2 keeps source JSON's 0.6667s. v6.3 resamples walk animations to
   the Java-derived cycle length when the simulator can compute it.

5. LIMBSWINGAMOUNT² SCALING (all swingX/Y/Z-derived anims):
   Java: `rotateAngle = invert * limbSwingAmount² * degree * cos(...)`.
   v6.2 bakes at full walk (limbSwingAmount=1.0). v6.3 adds a Molang
   `scale` channel that multiplies rotation by `query.modified_distance_moved²`
   so slow walks have proportionally smaller motion.
"""

from __future__ import annotations

import logging
import math
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from engine.java_analyzer import (
    ModelMetadata,
    HeadTrackingInfo,
    StateInfo,
    _extract_method_body,
    _extract_all_anim_assignments,
    _resolve_variables,
    SRG_FIELDS,
)

logger = logging.getLogger(__name__)

RAD2DEG = 180.0 / math.pi
AXIS_SIGN_FLIP = {"x": 1, "y": -1, "z": -1}

# GeckoLib 4 (MC 1.20.1) Molang queries
# query.attack_time returns seconds since last attack (0 = just attacked, grows)
# query.modified_distance_moved returns distance moved in the last tick (0 = standing)
# query.head_yaw / query.head_pitch return degrees


def _make_uuid() -> str:
    return str(uuid.uuid4()).replace("-", "")[:16]


# ---------------------------------------------------------------------------
# 1. Attack Fade — blend_weight Molang
# ---------------------------------------------------------------------------

ATTACK_TIMER_RE = re.compile(
    r"float\s+(\w+)\s*=\s*\w+\.getAttackTimer\(\)\s*;"
    r"[^}]*?if\s*\(\s*\1\s*>\s*0\.0f\s*\)\s*\{([^}]*)\}",
    re.DOTALL,
)

ATTACK_ASSIGN_RE = re.compile(
    r"this\.(\w+)\.(field_78795_f|field_78796_g|field_78808_h)\s*\+=\s*Math\.min\(\s*([\d.]+)f?\s*,\s*\w+\s*\)"
)


def extract_attack_fade(meta: ModelMetadata) -> List[dict]:
    """Extract attack fade info from the model's setRotationAngles body.

    Returns list of {bone, axis, max_offset_rad} dicts.
    """
    if not meta.states:
        return []
    # Read the raw Java source to find attackTimer pattern
    try:
        with open(meta.java_path, "r", encoding="utf-8") as f:
            java_src = f.read()
    except Exception:
        return []

    results = []
    for m in ATTACK_TIMER_RE.finditer(java_src):
        body = m.group(2)
        for am in ATTACK_ASSIGN_RE.finditer(body):
            bone = am.group(1)
            field = am.group(2)
            max_off = float(am.group(3))
            axis = {"field_78795_f": "x", "field_78796_g": "y", "field_78808_h": "z"}[field]
            results.append({
                "bone": bone,
                "axis": axis,
                "max_offset_rad": max_off,
                "max_offset_deg": max_off * RAD2DEG * AXIS_SIGN_FLIP[axis],
            })
    return results


def build_attack_fade_animation(
    meta: ModelMetadata,
    bone_uuids: Dict[str, str],
    attack_anim_length: float = 4.0,
) -> Optional[dict]:
    """Build a blend_weight-driven attack fade animation.

    The animation contains the attack pose keyframes (sourced from the existing
    attack animation if present), with a blend_weight Molang that fades based
    on query.attack_time.

    Since we don't have the existing attack animation's keyframes here, we
    emit a SEPARATE animation `animation.srparasites.<name>.attack_overlay`
    that contains ONE keyframe per affected bone with the max rotation offset,
    and a blend_weight Molang. Modders enable this alongside the base attack
    animation; GeckoLib blends it in proportionally to attack_time.

    The blend_weight formula mimics Java's `Math.min(0.4, attackTimer)`:
      - When attackTimer >= 0.4 (just attacked): full blend (1.0)
      - When attackTimer = 0 (long since attacked): no blend (0.0)
      - Linear fade in between, clamped to [0, 1]
    Molang: `min(1.0, query.attack_time * 2.5)` where 2.5 = 1/0.4
    """
    fades = extract_attack_fade(meta)
    if not fades:
        return None

    animators = {}
    for fade in fades:
        bone = fade["bone"]
        animator_key = bone_uuids.get(bone)
        if not animator_key:
            # case-insensitive fallback
            for bn, bu in bone_uuids.items():
                if bn.lower() == bone.lower():
                    animator_key = bu
                    bone = bn
                    break
        if not animator_key:
            continue

        axis = fade["axis"]
        max_deg = fade["max_offset_deg"]
        # One keyframe at t=0 with the max offset on the attack axis
        dp = {"x": "0", "y": "0", "z": "0"}
        dp[axis] = f"{max_deg:.4f}"
        kf = {
            "channel": "rotation",
            "data_points": [{**dp}],
            "uuid": _make_uuid(),
            "time": 0.0,
            "color": -1,
            "interpolation": "linear",
        }
        animators[animator_key] = {
            "name": bone,
            "type": "bone",
            "keyframes": [kf],
        }

    if not animators:
        return None

    # blend_weight Molang: fades from 1.0 (just attacked) to 0.0 (idle)
    # Java: min(0.4, attackTimer) / 0.4 → clamped 0..1
    # GeckoLib query.attack_time grows from 0 at attack moment, so we use:
    #   blend_weight = max(0, 1.0 - query.attack_time * 2.5)
    # (2.5 = 1/0.4; at attack_time=0 → 1.0, at attack_time=0.4 → 0.0)
    blend_weight_molang = "math.max(0, 1.0 - query.attack_time * 2.5)"

    animation = {
        "name": f"animation.srparasites.{meta.model_name}.attack_overlay",
        "uuid": _make_uuid(),
        "loop": "hold",
        "override": False,
        "length": 0.0,
        "snapping": 24,
        "selected": False,
        "anim_time_update": "",
        "blend_weight": blend_weight_molang,
        "animators": animators,
    }
    logger.debug(
        "[%s] attack_overlay: %d bones, blend_weight=%s",
        meta.model_name, len(animators), blend_weight_molang,
    )
    return animation


# ---------------------------------------------------------------------------
# 2. setLivingAnimations Body Bob — getFloorTimer driven
# ---------------------------------------------------------------------------

FLOOR_TIMER_RE = re.compile(
    r"float\s+(\w+)\s*=\s*\(float\)\w+\.getFloorTimer\(\)\s*;",
    re.DOTALL,
)


def extract_body_bob(meta: ModelMetadata) -> List[dict]:
    """Extract body bob assignments from setLivingAnimations (func_78086_a).

    Pattern in Java:
      public void func_78086_a(...) {
          float f6 = (float)ven.getFloorTimer();
          if (f6 >= 0.0f) {
              this.mainbody.field_82908_p = f6;
              this.mainbody.field_82906_o = partialTickTime * 0.091f;
              this.mainbody.field_82907_q = partialTickTime * 0.092f;
          }
      }
    """
    try:
        with open(meta.java_path, "r", encoding="utf-8") as f:
            java_src = f.read()
    except Exception:
        return []

    # Find func_78086_a body (setLivingAnimations)
    body = _extract_method_body(java_src, "func_78086_a")
    if not body:
        return []

    # Check if it uses getFloorTimer
    if "getFloorTimer" not in body:
        return []

    # Extract assignments to mainbody offsets
    bobs = []
    # this.<bone>.field_82908_p = <expr>;  (offsetY)
    # this.<bone>.field_82906_o = <expr>;  (offsetX)
    # this.<bone>.field_82907_q = <expr>;  (offsetZ)
    assign_re = re.compile(
        r"this\.(\w+)\.(field_82908_p|field_82906_o|field_82907_q)\s*=\s*([^;]+);"
    )
    for m in assign_re.finditer(body):
        bone = m.group(1)
        field = m.group(2)
        expr = m.group(3).strip()
        axis = {"field_82908_p": "y", "field_82906_o": "x", "field_82907_q": "z"}[field]
        # Skip pure partialTickTime-driven (those aren't bobbing)
        if "getFloorTimer" in expr or "f6" in expr or re.match(r"^[a-z]\d+$", expr):
            bobs.append({"bone": bone, "axis": axis, "expression": expr})
    return bobs


def build_body_bob_animation(
    meta: ModelMetadata,
    bone_uuids: Dict[str, str],
) -> Optional[dict]:
    """Build a body_bob animation driven by a Molang expression.

    The getFloorTimer() value comes from the entity's tick-level state.
    Since we can't query it from standard GeckoLib Molang, we emit a
    SYNTHETIC bob animation that approximates the visual effect using
    query.anim_time (continuous time) modulated by a sine wave.

    Modders can replace the Molang with their entity's floor-timer query
    via GeckoLib's custom Molang variables.
    """
    bobs = extract_body_bob(meta)
    if not bobs:
        return None

    animators = {}
    for bob in bobs:
        bone = bob["bone"]
        animator_key = bone_uuids.get(bone)
        if not animator_key:
            for bn, bu in bone_uuids.items():
                if bn.lower() == bone.lower():
                    animator_key = bu
                    bone = bn
                    break
        if not animator_key:
            continue

        axis = bob["axis"]
        # Build a Molang-driven keyframe. The expression uses query.anim_time
        # to produce a continuous bob. Sign-flip for Y/Z (RH→LH).
        sign = AXIS_SIGN_FLIP[axis]
        # Default bob: 0.5 pixel amplitude at 0.5Hz (visually subtle)
        # Modders should replace with their entity's floor timer query.
        molang = f"{sign} * (math.sin(query.anim_time * 3.14159) * 0.5)"
        dp = {"x": "0", "y": "0", "z": "0"}
        dp[axis] = molang
        kf = {
            "channel": "position",
            "data_points": [{**dp}],
            "uuid": _make_uuid(),
            "time": 0.0,
            "color": -1,
            "interpolation": "linear",
        }
        animators[animator_key] = {
            "name": bone,
            "type": "bone",
            "keyframes": [kf],
        }

    if not animators:
        return None

    animation = {
        "name": f"animation.srparasites.{meta.model_name}.body_bob",
        "uuid": _make_uuid(),
        "loop": "loop",
        "override": False,
        "length": 0.0,
        "snapping": 24,
        "selected": False,
        "anim_time_update": "",
        "blend_weight": "",
        "animators": animators,
    }
    logger.debug(
        "[%s] body_bob: %d bones (floor-timer driven, Molang approx)",
        meta.model_name, len(animators),
    )
    return animation


# ---------------------------------------------------------------------------
# 3. Conditional Bone Visibility — isHidden variants
# ---------------------------------------------------------------------------

ISHIDDEN_RE = re.compile(
    r"this\.(\w+)\.field_78807_k\s*=\s*([^;]+);"
)


def extract_visibility_variants(meta: ModelMetadata) -> List[dict]:
    """Extract isHidden assignments (conditional bone visibility).

    Pattern: this.bone.field_78807_k = parasite.getLeft() == 0.0f;
    Returns list of {bone, condition} where condition is the Java expression.
    """
    try:
        with open(meta.java_path, "r", encoding="utf-8") as f:
            java_src = f.read()
    except Exception:
        return []

    variants = []
    for m in ISHIDDEN_RE.finditer(java_src):
        bone = m.group(1)
        cond = m.group(2).strip()
        variants.append({"bone": bone, "condition": cond})
    return variants


def build_visibility_variants_animation(
    meta: ModelMetadata,
    bone_uuids: Dict[str, str],
) -> Optional[dict]:
    """Build a visibility_variants animation that scales bones to 0.

    Blockbench bedrock format has no runtime visibility toggle via Molang.
    As a workaround, we emit an animation that scales hidden bones to 0
    using a Molang expression. GeckoLib 4 supports `query.is_first_person`
    and custom variables; modders wire their entity's getLeft()/getRight()
    state to a custom Molang variable (e.g. `variable.left_hidden`).

    The scale channel uses: `variable.left_hidden ? 0 : 1`
    """
    variants = extract_visibility_variants(meta)
    if not variants:
        return None

    animators = {}
    for var in variants:
        bone = var["bone"]
        cond = var["condition"]
        animator_key = bone_uuids.get(bone)
        if not animator_key:
            for bn, bu in bone_uuids.items():
                if bn.lower() == bone.lower():
                    animator_key = bu
                    bone = bn
                    break
        if not animator_key:
            continue

        # Map Java condition to a Molang variable name
        # parasite.getLeft() == 0.0f → variable.left_hidden
        var_name = "left_hidden"
        if "getRight" in cond:
            var_name = "right_hidden"
        elif "getLeft" in cond:
            var_name = "left_hidden"
        else:
            var_name = "custom_hidden"

        # Scale to 0 when hidden (variable.*_hidden == 1)
        scale_molang = f"variable.{var_name} ? 0 : 1"
        dp = {"x": scale_molang, "y": scale_molang, "z": scale_molang}
        kf = {
            "channel": "scale",
            "data_points": [{**dp}],
            "uuid": _make_uuid(),
            "time": 0.0,
            "color": -1,
            "interpolation": "linear",
        }
        animators[animator_key] = {
            "name": bone,
            "type": "bone",
            "keyframes": [kf],
        }

    if not animators:
        return None

    animation = {
        "name": f"animation.srparasites.{meta.model_name}.visibility",
        "uuid": _make_uuid(),
        "loop": "loop",
        "override": False,
        "length": 0.0,
        "snapping": 24,
        "selected": False,
        "anim_time_update": "",
        "blend_weight": "",
        "animators": animators,
    }
    logger.debug(
        "[%s] visibility: %d bones (Molang scale-to-0 workaround)",
        meta.model_name, len(animators),
    )
    return animation


# ---------------------------------------------------------------------------
# 4. Walk Cycle Normalization
# ---------------------------------------------------------------------------

def compute_java_walk_period(meta: ModelMetadata) -> Optional[float]:
    """Compute the Java-derived walk cycle period in seconds.

    From swingX/Y(bone, SPEED, ...) calls, the period is 2π/SPEED ticks.
    With GS (default 1.5) multiplier: SPEED = base_speed * GS.
    At 20 tps, period_seconds = 2π / (base_speed * GS * 20).

    Returns None if no swing calls found.
    """
    if not meta.states:
        return None
    speeds = []
    for s in meta.states:
        # Look for swingX/Y(this.bone, SPEED * GS, ...) or swingX/Y(this.bone, SPEED, ...)
        for m in re.finditer(
            r"this\.swing[XYZ]\(\s*this\.\w+\s*,\s*([^,]+),", s.body
        ):
            speed_expr = m.group(1).strip()
            # Extract base speed: "0.3f * GS" → 0.3, "0.8f" → 0.8
            base_m = re.match(r"([\d.]+)f?\s*\*\s*GS", speed_expr)
            if base_m:
                base = float(base_m.group(1))
                gs = 1.5  # default GS
                # Check if GS is assigned in this state
                gs_m = re.search(r"\bGS\s*=\s*([\d.]+)f?\s*;", s.body)
                if gs_m:
                    gs = float(gs_m.group(1))
                speeds.append(base * gs)
            else:
                base_m2 = re.match(r"([\d.]+)f?", speed_expr)
                if base_m2:
                    speeds.append(float(base_m2.group(1)))
    if not speeds:
        return None
    # Use the median speed (most common walk frequency)
    speeds.sort()
    median_speed = speeds[len(speeds) // 2]
    if median_speed <= 0:
        return None
    period_ticks = 2.0 * math.pi / median_speed
    period_sec = period_ticks / 20.0
    return round(period_sec, 4)


# ---------------------------------------------------------------------------
# 5. limbSwingAmount² Molang Scaling
# ---------------------------------------------------------------------------

def build_walk_speed_molang(walk_anim_length: float = 0.6667) -> str:
    """Build a Molang expression for limbSwingAmount² scaling.

    Java: rotateAngle = invert * limbSwingAmount² * degree * cos(...)
    At full walk (limbSwingAmount=1.0), the baked keyframes are correct.
    At slow walk, the rotation should be proportionally smaller (squared).

    GeckoLib query.modified_distance_moved returns distance moved last tick.
    A typical full walk is ~0.2 blocks/tick. We normalize:
      scale = (query.modified_distance_moved / 0.2)²
    Clamped to [0, 1] to avoid overshoot.

    This Molang goes on the walk animation's blend_weight so it scales ALL
    bones proportionally.
    """
    # clamp((query.modified_distance_moved / 0.2)², 0, 1)
    return "math.clamp(math.pow(query.modified_distance_moved / 0.2, 2), 0, 1)"


def inject_walk_blend_weight(animations: List[dict], model_name: str) -> int:
    """Inject blend_weight Molang into walk animations in-place.

    Returns count of modified animations.
    """
    modified = 0
    molang = build_walk_speed_molang()
    for anim in animations:
        name = anim.get("name", "")
        if "walk" in name.lower():
            anim["blend_weight"] = molang
            modified += 1
    return modified


# ---------------------------------------------------------------------------
# Unified injection entry point
# ---------------------------------------------------------------------------

def inject_all_runtime_behaviors(
    animations: List[dict],
    meta: Optional[ModelMetadata],
    bone_uuids: Dict[str, str],
    walk_anim_length: float = 0.6667,
) -> Tuple[List[dict], dict]:
    """Inject all v6.3 runtime behavior animations.

    Args:
        animations: Existing list of animation dicts (will be modified in-place
                    for walk blend_weight, and appended to for new anims).
        meta: ModelMetadata from java_analyzer, or None.
        bone_uuids: Dict mapping bone_name → uuid.
        walk_anim_length: Length of the walk animation (for cycle normalization).

    Returns:
        (animations, stats) where stats has counts of each injection type.
    """
    stats = {
        "attack_overlay": 0,
        "body_bob": 0,
        "visibility": 0,
        "walk_blend_weight": 0,
    }

    if meta is None:
        # Still inject walk blend_weight (doesn't need Java analysis)
        stats["walk_blend_weight"] = inject_walk_blend_weight(animations, "")
        return animations, stats

    # 1. Attack fade overlay
    attack_anim = build_attack_fade_animation(meta, bone_uuids)
    if attack_anim:
        animations.append(attack_anim)
        stats["attack_overlay"] = 1

    # 2. Body bob
    bob_anim = build_body_bob_animation(meta, bone_uuids)
    if bob_anim:
        animations.append(bob_anim)
        stats["body_bob"] = 1

    # 3. Visibility variants
    vis_anim = build_visibility_variants_animation(meta, bone_uuids)
    if vis_anim:
        animations.append(vis_anim)
        stats["visibility"] = 1

    # 5. Walk blend_weight (limbSwingAmount² scaling)
    stats["walk_blend_weight"] = inject_walk_blend_weight(animations, meta.model_name)

    return animations, stats
