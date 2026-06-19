#!/usr/bin/env python3
"""
Java Trig Simulator (v6.2)
==========================
Simulates the SRP Java `setRotationAngles` trig math to generate GeckoLib/
Blockbench keyframes for models where the upstream reverse-engineering failed
(stub animations) or where additional state-specific animations are missing.

WHY THIS EXISTS:
  The upstream Qom-Inseac `.class` → GeckoLib JSON extractor only recognizes
  `swingX/Y/Z(...)` helper calls. Many SRP models (e.g. Elvia with 290 bones)
  use DIRECT field assignments:
      this.tacleJointbackL2.field_78795_f = 0.2f * MathHelper.sin(ageInTicks * 0.08f) * 0.73f;
  The extractor misses these and produces a stub (1 root bone, position=None).
  This simulator parses those direct assignments and bakes them into keyframes.

HOW IT WORKS:
  1. Parse `float varN = <expr>;` declarations in the state body
  2. Resolve variable references (e.g. `age3fN = -1.0f * age3f`)
  3. Parse `this.<bone>.<field> = <expr>;` assignments
  4. For each assignment, determine the natural cycle from the trig frequency
  5. Sample the expression at 20fps over one full cycle → keyframes
  6. Convert ModelRenderer radians → Blockbench degrees (×57.2958)
  7. Apply the RH→LH coordinate transform (Y negated for rotation/position)

SUPPORTED EXPRESSIONS:
  - `MathHelper.func_76126_a(x)` = sin(x)     [SRG name for MathHelper.sin]
  - `MathHelper.func_76134_d(x)` = cos(x)     [SRG name for MathHelper.cos]
  - `<float>f` literal
  - `ageInTicks` variable (substituted with t*20)
  - `limbSwing` / `limbSwingAmount` variables (for walk-state simulations)
  - Variable references (resolved from declarations)
  - Arithmetic: +, -, *, /, unary minus, parentheses
"""

from __future__ import annotations

import math
import re
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.types import (
    AXES,
    AnimationIR,
    AxisValue,
    BoneAnimationIR,
    KeyframeData,
)
from engine.java_analyzer import (
    MATHHELPER,
    SRG_FIELDS,
    ModelMetadata,
    StateInfo,
    TrigAssignment,
    _extract_all_anim_assignments,
    _resolve_variables,
)

logger = logging.getLogger(__name__)


# Sample rate: keyframes per second (20fps = MC tick rate)
SAMPLE_FPS: int = 20

# Radians → degrees
RAD2DEG: float = 180.0 / math.pi

# RH→LH transform: ModelRenderer Y is negated in Blockbench (Y-up vs Y-down)
# Rotation: (rx, -ry, -rz); Position: (px, -py, -pz)
# This matches core/coords.py M_model = diag(1, -1, -1)
AXIS_SIGN_FLIP: Dict[str, int] = {"x": 1, "y": -1, "z": -1}


def _axis_from_field(field: str) -> str:
    """Map SRG field name to single axis letter."""
    mapping = {
        "field_78795_f": "x",  # rotateAngleX
        "field_78796_g": "y",  # rotateAngleY
        "field_78808_h": "z",  # rotateAngleZ
        "field_82906_o": "x",  # offsetX
        "field_82908_p": "y",  # offsetY
        "field_82907_q": "z",  # offsetZ
    }
    return mapping.get(field, "x")


def _channel_from_field(field: str) -> str:
    """Map SRG field name to animation channel ('rotation' or 'position')."""
    if field in ("field_78795_f", "field_78796_g", "field_78808_h"):
        return "rotation"
    if field in ("field_82906_o", "field_82908_p", "field_82907_q"):
        return "position"
    return "rotation"


def _safe_eval(expr: str, env: Dict[str, float]) -> float:
    """Safely evaluate a Java trig expression to a float.

    v6.8: Uses AST-based safe_evaluator instead of eval().
    Translates Java syntax (MathHelper.func_*, float suffixes, casts)
    to Python, then evaluates via a whitelist-restricted AST walker.
    This blocks all attribute access, subscripting, imports, and lambda —
    only arithmetic + whitelisted math functions are allowed.
    """
    from engine.safe_evaluator import safe_eval_java
    return safe_eval_java(expr, env)


def _resolve_expr(expr: str, variables: Dict[str, str], depth: int = 0) -> str:
    """Recursively resolve variable references in an expression.

    e.g. given variables = {"age3fN": "-1.0f * age3f", "age3f": "0.2f * MathHelper.sin(ageInTicks * 0.08f) * 0.73f"},
    resolve("age3fN") → "-1.0f * 0.2f * MathHelper.sin(ageInTicks * 0.08f) * 0.73f"
    """
    if depth > 10:
        return expr
    # Find variable references (identifiers that match declared variables)
    def replace_var(m):
        name = m.group(0)
        if name in variables:
            # Recursively resolve the variable's expression
            inner = _resolve_expr(variables[name], variables, depth + 1)
            return f"({inner})"
        return name

    # Match identifiers that aren't preceded by '.' (so we don't match MathHelper.sin etc.)
    # and aren't function calls
    py_expr = re.sub(r"\b([a-zA-Z_]\w*)\b(?!\s*\()", replace_var, expr)
    return py_expr


def _detect_cycle_period(expr: str, variables: Dict[str, str]) -> float:
    """Detect the natural cycle period (in seconds) from trig frequencies.

    Looks for `ageInTicks * FREQ` patterns and computes 2π/max(FREQ) ticks,
    converted to seconds at 20tps.

    For walk-state expressions using `limbSwing * FREQ`, the cycle depends on
    movement speed; we default to the JSON walk length (0.6667s).
    """
    resolved = _resolve_expr(expr, variables)
    # Find all frequency multipliers: ageInTicks * <float> OR limbSwing * <float>
    freqs = re.findall(r"(?:ageInTicks|limbSwing)\s*\*\s*([\d.]+)", resolved)
    if not freqs:
        # Also check for (var) * <float> where var resolves to ageInTicks/limbSwing
        freqs = re.findall(r"(?:ageInTicks|limbSwing)\s*\*\s*\(([\d.]+)\)", resolved)
    if not freqs:
        return 4.0  # default 4s cycle for idle
    max_freq = max(float(f) for f in freqs)
    if max_freq <= 0:
        return 4.0
    # Period in ticks = 2π / freq; in seconds = ticks / 20
    period_ticks = 2.0 * math.pi / max_freq
    period_sec = period_ticks / 20.0
    # Use the ACTUAL period (not 2x). Sampling exactly 1 cycle ensures
    # the cosine/sine wave naturally returns to its starting value,
    # providing a seamless loop WITHOUT needing _force_seamless_loop.
    # The previous 2x multiplier caused non-integer cycle counts,
    # leading to visible jumps/twitches at the loop boundary.
    return max(0.3, min(period_sec, 20.0))


def _simulate_state(
    state_body: str,
    model_name: str,
    state_value: int,
    sample_count: int = 80,
) -> Tuple[AnimationIR, float]:
    """Simulate one state branch to generate an AnimationIR.

    Args:
        state_body: Java code for the state branch.
        model_name: Model name (for animation naming).
        state_value: State integer (e.g. 0, 1, 77).
        sample_count: Number of keyframes to generate per cycle.

    Returns:
        (AnimationIR, cycle_length_seconds)
    """
    variables = _resolve_variables(state_body)
    assignments = _extract_all_anim_assignments(state_body)

    if not assignments:
        logger.debug("[%s] state %d: no trig assignments", model_name, state_value)
        return AnimationIR(
            name=f"animation.simulated.{model_name}.state{state_value}",
            loop="loop",
            length=4.0,
            bones={},
        ), 4.0

    # Extract SRP animation constants GS (speed multiplier) and GD (degree multiplier).
    # These are declared as `float GS; ... GS = <val>f;` and vary by state.
    # We take the first assignment found in the state body.
    gs_val = 1.5
    gd_val = 0.4
    gs_m = re.search(r"\bGS\s*=\s*(-?[\d.]+)f?\s*;", state_body)
    if gs_m:
        gs_val = float(gs_m.group(1))
    gd_m = re.search(r"\bGD\s*=\s*(-?[\d.]+)f?\s*;", state_body)
    if gd_m:
        gd_val = float(gd_m.group(1))

    # Detect cycle period from the assignment with the highest frequency
    max_period = 4.0
    for a in assignments:
        resolved = _resolve_expr(a.expression, variables)
        p = _detect_cycle_period(a.expression, variables)
        if p > max_period:
            max_period = p
    cycle_length = max_period

    # Generate samples
    # ageInTicks = t * 20 (MC runs at 20tps); at t=cycle_length, ageInTicks = cycle_length*20
    # limbSwing for walk states: assume default walk speed → limbSwing = t * 20
    # limbSwingAmount: assume full walk = 1.0
    sample_times = [i * cycle_length / sample_count for i in range(sample_count + 1)]

    # Group assignments by bone
    bone_assignments: Dict[str, List[TrigAssignment]] = {}
    for a in assignments:
        bone_assignments.setdefault(a.bone, []).append(a)

    # Generate keyframes per bone
    bones: Dict[str, BoneAnimationIR] = {}
    for bone_name, assigns in bone_assignments.items():
        keyframes: List[KeyframeData] = []
        for t in sample_times:
            # Build the evaluation environment
            age_in_ticks = t * 20.0
            limb_swing = t * 20.0  # default walk speed
            limb_swing_amount = 1.0  # full walk

            # First resolve variables (they may depend on ageInTicks/limbSwing)
            var_values: Dict[str, float] = {}
            for vname, vexpr in variables.items():
                resolved = _resolve_expr(vexpr, variables)
                env = {
                    "ageInTicks": age_in_ticks,
                    "limbSwing": limb_swing,
                    "limbSwingAmount": limb_swing_amount,
                    "f": limb_swing,
                    "f1": limb_swing_amount,
                    "GS": gs_val,
                    "GD": gd_val,
                    "scale": 0.0625,
                    **var_values,
                }
                val = _safe_eval(resolved, env)
                var_values[vname] = val

            # Now evaluate each assignment for this bone
            axis_values = {"x": AxisValue.default_val(), "y": AxisValue.default_val(), "z": AxisValue.default_val()}
            channel = None
            for a in assigns:
                resolved = _resolve_expr(a.expression, variables)
                env = {
                    "ageInTicks": age_in_ticks,
                    "limbSwing": limb_swing,
                    "limbSwingAmount": limb_swing_amount,
                    "f": limb_swing,
                    "f1": limb_swing_amount,
                    "GS": gs_val,
                    "GD": gd_val,
                    "scale": 0.0625,
                    **var_values,
                }
                val = _safe_eval(resolved, env)
                axis = _axis_from_field(a.field)
                ch = _channel_from_field(a.field)
                if channel is None:
                    channel = ch
                # Convert radians → degrees, apply RH→LH sign flip
                if channel == "rotation":
                    val_deg = val * RAD2DEG * AXIS_SIGN_FLIP[axis]
                else:  # position
                    # ModelRenderer position is in model units (1/16 block); BB uses pixels
                    # Apply sign flip for Y/Z
                    val_deg = val * 16.0 * AXIS_SIGN_FLIP[axis]  # scale up to pixels
                axis_values[axis] = AxisValue.explicit_val(val_deg)

            if channel is None:
                continue

            kf = KeyframeData(
                time=round(t, 6),
                channel=channel,
                x=axis_values["x"],
                y=axis_values["y"],
                z=axis_values["z"],
                easing="linear",
                interpolation="linear",
            )
            keyframes.append(kf)

        if keyframes:
            bones[bone_name] = BoneAnimationIR(bone_name=bone_name, keyframes=keyframes)

    anim_name = f"animation.simulated.{model_name}.state{state_value}"
    if state_value == 0:
        anim_name = f"animation.simulated.{model_name}.idle"

    anim = AnimationIR(
        name=anim_name,
        loop="loop",
        length=round(cycle_length, 4),
        bones=bones,
    )
    logger.debug(
        "[%s] simulated state %d: %d bones, %d keyframes, cycle=%.2fs",
        model_name, state_value, len(bones),
        sum(len(b.keyframes) for b in bones.values()),
        cycle_length,
    )
    return anim, cycle_length


def simulate_idle(
    meta: ModelMetadata,
    sample_count: int = 80,
) -> Optional[AnimationIR]:
    """Generate an idle animation by simulating state 0 of the Java trig.

    Use this for stub models where the upstream extraction failed.

    Args:
        meta: ModelMetadata from java_analyzer.
        sample_count: Keyframes per cycle.

    Returns:
        AnimationIR for the idle animation, or None if no trig found.
    """
    if not meta.states:
        return None
    # Find state 0 (the default idle state)
    state0 = None
    for s in meta.states:
        if s.state_value == 0:
            state0 = s
            break
    if state0 is None:
        state0 = meta.states[0]

    anim, _ = _simulate_state(state0.body, meta.model_name, state0.state_value, sample_count)
    if not anim.bones:
        return None
    # Rename to use srparasites namespace + model name
    anim.name = f"animation.srparasites.{meta.model_name}.idle"
    return anim


def simulate_all_states(
    meta: ModelMetadata,
    sample_count: int = 80,
) -> List[AnimationIR]:
    """Generate animations for ALL states in the state machine.

    Use this to recover state-specific animations that the upstream extraction
    collapsed into fewer animations.

    Args:
        meta: ModelMetadata from java_analyzer.

    Returns:
        List of AnimationIR, one per non-empty state.
    """
    anims: List[AnimationIR] = []
    seen_states = set()
    for s in meta.states:
        if s.state_value in seen_states:
            continue
        seen_states.add(s.state_value)
        anim, _ = _simulate_state(s.body, meta.model_name, s.state_value, sample_count)
        if anim.bones:
            # Name based on state value
            if s.state_value == 0:
                anim.name = f"animation.srparasites.{meta.model_name}.idle"
            else:
                anim.name = f"animation.srparasites.{meta.model_name}.state{s.state_value}"
            anims.append(anim)
    return anims
