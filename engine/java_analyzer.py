#!/usr/bin/env python3
"""
Java Animation Analyzer (v6.2)
==============================
Parses CFR-decompiled SRP `ModelX.java` files to extract per-model animation
metadata that the upstream Qom-Inseac reverse-engineering missed:

  1. **Head tracking** — `this.<bone>.field_78796_g = netHeadYaw * COEFF`
     and `this.<bone>.field_78795_f = headPitch * COEFF`. Present in 145/154
     models. The upstream extraction drops this entirely because netHeadYaw
     is a runtime variable that can't be baked into static keyframes.

  2. **State machine** — `byte i = parasite.getParasiteStatus(); if (i == N) {…}`
     branches. Identifies all animation states (e.g. Esor has 7 states, but
     only 5 made it into the JSON).

  3. **setLivingAnimations body bob** — `func_78088_a` overrides that set
     ModelRenderer rotations driven by `getFloorTimer()` / `ageInTicks`.

  4. **Walk speed** — `swingX/Y(bone, SPEED, …)` helper calls. The SPEED
     parameter determines the true Java walk cycle (2π/SPEED ticks).

  5. **Conditional bone visibility** — `field_78807_k` (isHidden) assignments
     gated by `getLeft()/getRight()` or state.

  6. **Direct trig assignments** — `this.bone.field_X = <trig expr>;` (not
     via swingX/Y helpers). Elvia uses this pattern; the upstream extraction
     produces a stub because it only looks for swingX/Y calls.

The metadata is used by:
  - `engine/head_tracking_injector.py` — adds Molang-driven head_track anim
  - `engine/java_trig_simulator.py` — generates idle keyframes for stub models
  - `engine/body_bob_injector.py` — injects setLivingAnimations body bob
  - `batch/mdo_srp.py` — decides when to augment/replace upstream JSON data
"""

from __future__ import annotations

import os
import re
import json
import math
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# SRG field name → human-readable (1.12.2 MCP mappings)
SRG_FIELDS: Dict[str, str] = {
    "field_78795_f": "rotateAngleX",   # X rotation (pitch)
    "field_78796_g": "rotateAngleY",   # Y rotation (yaw)
    "field_78808_h": "rotateAngleZ",   # Z rotation (roll)
    "field_82906_o": "offsetX",        # X position
    "field_82908_p": "offsetY",        # Y position
    "field_82907_q": "offsetZ",        # Z position
    "field_78807_k": "isHidden",       # visibility flag
}

# MathHelper SRG names → math functions
# 1.12.2 has multiple SRG mappings for the same function (static vs instance)
MATHHELPER: Dict[str, str] = {
    "func_76126_a": "sin",   # MathHelper.sin
    "func_76134_d": "cos",   # MathHelper.cos (static)
    "func_76134_b": "cos",   # MathHelper.cos (instance/alt mapping)
    "func_76133_a": "sqrt",  # MathHelper.sqrt
    "func_76132_a": "abs",   # MathHelper.abs
    "func_76130_b": "clamp", # MathHelper.clamp
    "func_76131_a": "floor", # MathHelper.floor
}

# Method signatures (SRG names in 1.12.2)
SET_ROTATION_ANGLES = "func_78087_a"   # setRotationAngles
SET_LIVING_ANIMATIONS = "func_78088_a"  # setLivingAnimations


@dataclass
class HeadTrackingInfo:
    """Head tracking metadata for one model."""
    bone_name: str           # e.g. "jointH", "jointhead", "joint_head"
    yaw_coeff: float         # coefficient for netHeadYaw (e.g. 0.016 or -0.016)
    pitch_coeff: float       # coefficient for headPitch (e.g. 0.016)
    yaw_axis: str            # "y" (rotateAngleY)
    pitch_axis: str          # "x" (rotateAngleX)


@dataclass
class StateInfo:
    """One state branch in the state machine."""
    state_value: int         # e.g. 0, 1, 77
    body: str                # raw Java code for this state's branch


@dataclass
class TrigAssignment:
    """A direct trig assignment: this.bone.field = expr; (or +=, -=, *=, /=)"""
    bone: str
    field: str               # SRG field name
    axis: str                # resolved axis: "rotateAngleX/Y/Z" or "offsetX/Y/Z"
    expression: str          # Java expression (e.g. "0.2f * MathHelper.sin(ageInTicks * 0.08f) * 0.73f")
    line: int
    op: str = "="            # assignment operator: "=", "+=", "-=", "*=", "/="


@dataclass
class BodyBobInfo:
    """Body bob from setLivingAnimations."""
    bone: str
    axis: str                # "rotateAngleX/Y/Z" or "offsetX/Y/Z"
    expression: str          # trig expression


@dataclass
class ModelMetadata:
    """All extracted metadata for one SRP model."""
    model_name: str          # e.g. "elvia"
    class_name: str          # e.g. "ModelElvia"
    java_path: str           # path to decompiled .java
    head_tracking: Optional[HeadTrackingInfo] = None
    states: List[StateInfo] = field(default_factory=list)
    body_bobs: List[BodyBobInfo] = field(default_factory=list)
    walk_speeds: Dict[str, float] = field(default_factory=dict)  # bone -> speed
    has_stub_friendly_trig: bool = False  # direct field assignments (not swingX/Y)
    total_trig_assignments: int = 0
    uses_swing_helpers: bool = False


def find_java_file(model_name: str, decompiled_root: str) -> Optional[str]:
    """Find the decompiled .java file for a model.

    The decompiled structure is: decompiled/all/<category>_Model<Name>/.../Model<Name>.java
    The Java class name preserves CamelCase (e.g. ModelLeemB, ModelVenkrolSV),
    while the MDO-SRP-SRC model name is lowercased (e.g. "leemb", "venkrolsv").
    We do case-insensitive suffix matching to handle this discrepancy.
    """
    if not model_name:
        return None
    target_lower = model_name.lower()
    for root, dirs, files in os.walk(decompiled_root):
        for f in files:
            if not f.endswith(".java"):
                continue
            if not f.startswith("Model"):
                continue
            # Extract the class suffix after "Model" (e.g. "LeemB" from "ModelLeemB")
            suffix = f[len("Model"):-len(".java")]
            if suffix.lower() == target_lower:
                return os.path.join(root, f)
    return None


def _extract_method_body(java_src: str, method_sig_name: str) -> Optional[str]:
    """Extract the body of a method by its SRG name (e.g. func_78087_a).

    Handles brace matching to find the method's closing brace.
    """
    # Find the method declaration
    pattern = rf"public\s+void\s+{re.escape(method_sig_name)}\s*\([^)]*\)\s*\{{"
    m = re.search(pattern, java_src)
    if not m:
        return None
    start = m.end()
    depth = 1
    i = start
    while i < len(java_src) and depth > 0:
        c = java_src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    if depth != 0:
        return None
    return java_src[start : i - 1]


def _extract_head_tracking(set_rotation_body: str) -> Optional[HeadTrackingInfo]:
    """Extract head tracking info from setRotationAngles body.

    Pattern: this.<bone>.field_78796_g = netHeadYaw * <coeff>f;
             this.<bone>.field_78795_f = headPitch * <coeff>f;
    """
    yaw_bone = None
    yaw_coeff = None
    pitch_bone = None
    pitch_coeff = None

    # Yaw: this.<bone>.field_78796_g = netHeadYaw * <expr>
    # Matches both `netHeadYaw * 0.016f` and `netHeadYaw * ((float)Math.PI / 180)`
    yaw_pat = re.compile(
        r"this\.(\w+)\.field_78796_g\s*=\s*netHeadYaw\s*\*\s*([^;]+);"
    )
    for m in yaw_pat.finditer(set_rotation_body):
        yaw_bone = m.group(1)
        coeff_expr = m.group(2).strip()
        # Try to evaluate the coefficient
        if "Math.PI" in coeff_expr or "PI" in coeff_expr:
            # PI/180 = 0.01745, handle the common pattern
            yaw_coeff = math.pi / 180.0
        else:
            # Try parsing as float (e.g. "0.016f", "-0.016f")
            try:
                yaw_coeff = float(coeff_expr.replace("f", ""))
            except ValueError:
                yaw_coeff = 0.016  # default
        break  # take first

    # Pitch: this.<bone>.field_78795_f = headPitch * <expr>
    pitch_pat = re.compile(
        r"this\.(\w+)\.field_78795_f\s*=\s*headPitch\s*\*\s*([^;]+);"
    )
    for m in pitch_pat.finditer(set_rotation_body):
        pitch_bone = m.group(1)
        coeff_expr = m.group(2).strip()
        if "Math.PI" in coeff_expr or "PI" in coeff_expr:
            pitch_coeff = math.pi / 180.0
        else:
            try:
                pitch_coeff = float(coeff_expr.replace("f", ""))
            except ValueError:
                pitch_coeff = 0.016
        break

    if yaw_bone or pitch_bone:
        return HeadTrackingInfo(
            bone_name=(yaw_bone or pitch_bone),
            yaw_coeff=(yaw_coeff or 0.0),
            pitch_coeff=(pitch_coeff or 0.0),
            yaw_axis="y",
            pitch_axis="x",
        )
    return None


def _extract_states(set_rotation_body: str) -> List[StateInfo]:
    """Extract state branches from the state machine.

    Pattern: byte <var> = parasite.getParasiteStatus();
             if (<var> == N) { ... } else if (<var> == M) { ... } ...

    Variable declarations BEFORE the state branches (e.g. `float f1 = ...`)
    are prepended to each state's body so the simulator can resolve them.
    """
    # Find the status variable
    status_m = re.search(r"byte\s+(\w+)\s*=\s*\w+\.getParasiteStatus\(\)", set_rotation_body)
    if not status_m:
        # No state machine — single implicit state 0
        return [StateInfo(state_value=0, body=set_rotation_body)]

    var_name = status_m.group(1)
    # Capture everything BEFORE the first state branch as "pre-state" code.
    # This includes: variable declarations (float f1 = MathHelper.cos(...)) AND
    # unconditional assignments (this.bone.field = f1) that run regardless of state.
    # The first if(state==N) branch marks the start of state-specific code.
    first_branch_m = None
    branch_pat = re.compile(
        rf"(?:else\s+)?if\s*\(\s*{re.escape(var_name)}\s*==\s*(\d+)\s*\)\s*\{{"
    )
    first_branch_m = branch_pat.search(set_rotation_body, status_m.end())
    if first_branch_m:
        pre_branch = set_rotation_body[: first_branch_m.start()]
    else:
        pre_branch = set_rotation_body[: status_m.start()]

    states: List[StateInfo] = []

    matches = list(branch_pat.finditer(set_rotation_body))
    if not matches:
        return [StateInfo(state_value=0, body=set_rotation_body)]

    for i, m in enumerate(matches):
        state_val = int(m.group(1))
        body_start = m.end()
        # Find matching closing brace
        depth = 1
        j = body_start
        while j < len(set_rotation_body) and depth > 0:
            c = set_rotation_body[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            j += 1
        state_body = set_rotation_body[body_start : j - 1]
        # Prepend pre-state code (variable declarations + unconditional assignments)
        # so the simulator can resolve variables and capture state-independent anims
        full_body = pre_branch + "\n" + state_body
        states.append(StateInfo(state_value=state_val, body=full_body))

    return states


_VAR_DECL_RE = re.compile(
    r"float\s+(\w+)\s*=\s*([^;]+);"
)
# Also match reassignments to pre-declared float variables: f1 = <expr>;
# (no `float` prefix; variable was declared earlier as `float f1;`)
_VAR_REASSIGN_RE = re.compile(
    r"(?<![\w.])\b([a-z]\w*)\s*=\s*([^;={]+(?:\([^)]*\)[^;={]*)*);"
)
_ASSIGN_RE = re.compile(
    r"this\.(\w+)\.(field_\w+)\s*([+\-*/]?)=\s*([^;]+);"
)


def _resolve_variables(state_body: str) -> Dict[str, str]:
    """Extract variable declarations and reassignments.

    Matches both:
      - `float varN = <expr>;` (declaration with type)
      - `varN = <expr>;` (reassignment of pre-declared variable)
    Excludes `this.bone.field = ...` (handled separately) and
    `if/while` condition assignments.
    """
    variables: Dict[str, str] = {}
    # First pass: declarations with `float` prefix
    for m in _VAR_DECL_RE.finditer(state_body):
        var_name = m.group(1)
        expr = m.group(2).strip()
        variables[var_name] = expr
    # Second pass: reassignments without `float` prefix (e.g. `f1 = MathHelper.cos(...)`; )
    # Skip lines that are clearly not variable reassignments:
    #   - this.x.field = ... (bone field assignments, handled by _ASSIGN_RE)
    #   - if/while conditions
    #   - comparison operators (==, <=, >=, !=)
    for m in _VAR_REASSIGN_RE.finditer(state_body):
        var_name = m.group(1)
        expr = m.group(2).strip()
        # Skip if it's a this.bone.field assignment (var_name would be like "this")
        if var_name in ("this", "if", "while", "for", "else", "return", "true", "false", "null"):
            continue
        # Skip if expr contains comparison operators (it's a condition, not an assignment)
        if any(op in expr for op in ("==", "!=", "<=", ">=", "&&", "||")):
            continue
        # Skip if expr is just a literal number (likely a state setter, not trig)
        if re.match(r"^-?[\d.]+f?$", expr):
            continue
        variables[var_name] = expr
    return variables


def _extract_trig_assignments(state_body: str) -> List[TrigAssignment]:
    """Extract direct trig assignments: this.bone.field_X = <expr>; (or +=, -=, etc.)"""
    assignments: List[TrigAssignment] = []
    variables = _resolve_variables(state_body)

    for m in _ASSIGN_RE.finditer(state_body):
        bone = m.group(1)
        field = m.group(2)
        op_char = m.group(3)  # "", "+", "-", "*", "/"
        op = (op_char + "=") if op_char else "="
        expr = m.group(4).strip()
        line = state_body[: m.start()].count("\n") + 1

        if field not in SRG_FIELDS:
            continue

        # Skip head-tracking assignments (handled separately)
        if "netHeadYaw" in expr or "headPitch" in expr:
            continue
        # Skip isHidden assignments (handled separately)
        if field == "field_78807_k":
            continue
        # Skip pure constant assignments (no trig/variable) ONLY for plain "="
        # (For +=/-= with constants like += -1.7f, we MUST keep them as pose offsets)
        if op == "=" and not re.search(r"MathHelper|sin|cos|\bage\d", expr) and not any(
            v in expr for v in variables if re.match(r"age\w+", v)
        ):
            # Check if it references a variable that itself contains trig
            tokens = re.findall(r"\b([a-zA-Z_]\w*)\b", expr)
            if not any(t in variables for t in tokens):
                continue

        assignments.append(TrigAssignment(
            bone=bone,
            field=field,
            axis=SRG_FIELDS[field],
            expression=expr,
            line=line,
            op=op,
        ))

    return assignments


def _extract_body_bobs(set_living_body: str) -> List[BodyBobInfo]:
    """Extract body bob assignments from setLivingAnimations body."""
    bobs: List[BodyBobInfo] = []
    if not set_living_body:
        return bobs
    for m in _ASSIGN_RE.finditer(set_living_body):
        bone = m.group(1)
        field = m.group(2)
        expr = m.group(3).strip()
        if field not in SRG_FIELDS:
            continue
        if field == "field_78807_k":
            continue
        # Only interested in trig-driven assignments
        if "MathHelper" in expr or "sin" in expr or "cos" in expr:
            bobs.append(BodyBobInfo(
                bone=bone,
                axis=SRG_FIELDS[field],
                expression=expr,
            ))
    return bobs


def _extract_walk_speeds(set_rotation_body: str) -> Dict[str, float]:
    """Extract walk speeds from swingX/Y/Z helper calls.

    Pattern: swingX(this.bone, SPEED, DEGREE, ...) or swingY(...) etc.
    The base ModelSRP defines these helpers; subclasses call them.
    """
    speeds: Dict[str, float] = {}
    swing_pat = re.compile(
        r"this\.swing[XYZ]\(\s*this\.(\w+)\s*,\s*([^,]+),"
    )
    for m in swing_pat.finditer(set_rotation_body):
        bone = m.group(1)
        speed_expr = m.group(2).strip()
        speed_expr_clean = speed_expr.replace("f", "").replace("GS", "1.5")
        try:
            speed = float(eval(speed_expr_clean, {"__builtins__": {}}, {}))
            speeds[bone] = speed
        except Exception:
            pass
    return speeds


# Regex for swingX/Y/Z and moveY helper calls.
# swingX has 3 overloads:
#   swingX(mr, speed, degree, invert, limbSwing, limbSwingAmount)              — 6 args
#   swingX(mr, speed, degree, invert, offset, weight, limbSwing, limbSwingAmount) — 8 args
#   swingX(pref, mr, speed, degree, invert, limbSwing, limbSwingAmount)        — 7 args (pref first)
# moveY(mr, speed, invert, f, f1, distance) — 6 args
# We capture the full call string and parse args in the simulator.
_SWING_CALL_RE = re.compile(
    r"this\.(swing[XYZ])\(([^)]+)\);"
)
_MOVEY_CALL_RE = re.compile(
    r"this\.(moveY)\(([^)]+)\);"
)


def _extract_swing_calls(state_body: str) -> List[TrigAssignment]:
    """Extract swingX/Y/Z and moveY helper calls as TrigAssignment objects.

    Each swing call is converted to a TrigAssignment with the bone, field, and
    a synthetic expression that the simulator can evaluate.

    swingX/Y/Z → rotation assignment (rotateAngleX/Y/Z)
    moveY → position assignment (offsetY)
    """
    assignments: List[TrigAssignment] = []

    for m in _SWING_CALL_RE.finditer(state_body):
        helper = m.group(1)  # swingX, swingY, or swingZ
        args_str = m.group(2)
        line = state_body[: m.start()].count("\n") + 1

        # Parse args (split by comma, respecting that GS/GD may be multiplied)
        args = _split_args(args_str)
        if len(args) < 6:
            continue

        # Determine which overload and extract params
        # Overload 1: swingX(mr, speed, degree, invert, limbSwing, limbSwingAmount) — 6 args
        # Overload 2: swingX(mr, speed, degree, invert, offset, weight, limbSwing, limbSwingAmount) — 8 args
        # Overload 3: swingX(pref, mr, speed, degree, invert, limbSwing, limbSwingAmount) — 7 args (pref first)
        bone = None
        speed = None
        degree = None
        invert = None
        offset = "0"
        weight = "0"
        has_pref = False

        if len(args) == 6:
            # Overload 1: mr, speed, degree, invert, limbSwing, limbSwingAmount
            bone = _clean_bone_arg(args[0])
            speed = args[1]
            degree = args[2]
            invert = args[3]
        elif len(args) == 8:
            # Overload 2: mr, speed, degree, invert, offset, weight, limbSwing, limbSwingAmount
            bone = _clean_bone_arg(args[0])
            speed = args[1]
            degree = args[2]
            invert = args[3]
            offset = args[4]
            weight = args[5]
        elif len(args) == 7:
            # Overload 3: pref, mr, speed, degree, invert, limbSwing, limbSwingAmount
            bone = _clean_bone_arg(args[1])
            speed = args[2]
            degree = args[3]
            invert = args[4]
            has_pref = True
            pref = args[0]
        else:
            continue

        if not bone:
            continue

        # Map helper to field
        field_map = {"swingX": "field_78795_f", "swingY": "field_78796_g", "swingZ": "field_78808_h"}
        field = field_map[helper]

        # Build synthetic expression for the simulator.
        # ModelSRP.swingX: mr.rotateAngleX = invert * limbSwingAmount * degree * cos(limbSwing * speed + offset) + weight * limbSwingAmount
        # Note: the real helper multiplies by limbSwingAmount TWICE (quadratic scaling).
        # For idle (limbSwingAmount=0): result = 0 (no walk motion)
        # For walk (limbSwingAmount=1): result = invert * degree * cos(limbSwing*speed+offset) + weight
        if has_pref:
            expr = f"{pref} + {invert} * limbSwingAmount * limbSwingAmount * {degree} * MathHelper.func_76134_d(limbSwing * {speed})"
        elif offset != "0" or weight != "0":
            expr = f"{invert} * limbSwingAmount * limbSwingAmount * {degree} * MathHelper.func_76134_d(limbSwing * {speed} + {offset}) + {weight} * limbSwingAmount"
        else:
            expr = f"{invert} * limbSwingAmount * limbSwingAmount * {degree} * MathHelper.func_76134_d(limbSwing * {speed})"

        assignments.append(TrigAssignment(
            bone=bone,
            field=field,
            axis=SRG_FIELDS[field],
            expression=expr,
            line=line,
        ))

    # moveY calls → offsetY (position channel)
    for m in _MOVEY_CALL_RE.finditer(state_body):
        args_str = m.group(2)
        args = _split_args(args_str)
        if len(args) < 6:
            continue
        bone = _clean_bone_arg(args[0])
        speed = args[1]
        invert = args[2]
        # args[3]=f=limbSwing, args[4]=f1=limbSwingAmount, args[5]=distance
        distance = args[5]
        if not bone:
            continue
        # moveY: mr.offsetY = invert * cos(f * speed) * f1 * distance
        # f = limbSwing, f1 = limbSwingAmount. For idle (lsa=0): result = 0.
        expr = f"{invert} * MathHelper.func_76134_d(limbSwing * {speed}) * limbSwingAmount * {distance}"
        assignments.append(TrigAssignment(
            bone=bone,
            field="field_82908_p",  # offsetY
            axis="offsetY",
            expression=expr,
            line=state_body[: m.start()].count("\n") + 1,
        ))

    return assignments


def _split_args(args_str: str) -> List[str]:
    """Split a Java argument list by commas, respecting parentheses."""
    args = []
    depth = 0
    current = ""
    for c in args_str:
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        if c == "," and depth == 0:
            args.append(current.strip())
            current = ""
        else:
            current += c
    if current.strip():
        args.append(current.strip())
    return args


def _clean_bone_arg(arg: str) -> Optional[str]:
    """Extract bone name from 'this.boneName' argument."""
    arg = arg.strip()
    if arg.startswith("this."):
        return arg[5:]
    return None


def _extract_all_anim_assignments(state_body: str) -> List[TrigAssignment]:
    """Extract ALL animation assignments: direct field assignments + swing/moveY calls.

    This is the unified extractor used by the simulator.
    """
    direct = _extract_trig_assignments(state_body)
    swing = _extract_swing_calls(state_body)
    return direct + swing


def _follow_custom_methods(java_src: str, state_body: str) -> str:
    """Follow custom animation method calls like normalAni(...).

    If the state body calls a custom method (e.g. this.normalAni(...)),
    inline that method's body so the simulator can see its swing/trig calls.
    """
    # Find calls like: this.<methodname>(...);
    # Common custom methods: normalAni, underground, stateAni, etc.
    method_calls = re.findall(r"this\.(\w+)\(([^)]*)\)\s*;", state_body)
    result = state_body
    for method_name, call_args in method_calls:
        if method_name in ("swingX", "swingY", "swingZ", "moveY", "setRotateAngle",
                           "underground", "renderC", "setRotationAnglesCosmical"):
            continue  # skip known helpers
        # Find the method definition
        method_body = _extract_method_body(java_src, method_name)
        if method_body and ("swing" in method_body or "MathHelper" in method_body or "field_78" in method_body):
            # Inline the method body (simplified — doesn't handle return values)
            result += "\n        // --- inlined from " + method_name + " ---\n" + method_body
    return result


def analyze_model(model_name: str, decompiled_root: str) -> Optional[ModelMetadata]:
    """Analyze one model's decompiled Java source.

    Args:
        model_name: lowercase model name (e.g. "elvia")
        decompiled_root: path to decompiled/all/ directory

    Returns:
        ModelMetadata, or None if the .java file can't be found.
    """
    java_path = find_java_file(model_name, decompiled_root)
    if not java_path:
        logger.debug("[%s] No decompiled .java found", model_name)
        return None

    with open(java_path, "r", encoding="utf-8") as f:
        java_src = f.read()

    class_name = os.path.basename(java_path).replace(".java", "")
    meta = ModelMetadata(
        model_name=model_name,
        class_name=class_name,
        java_path=java_path,
    )

    # Extract setRotationAngles body
    sra_body = _extract_method_body(java_src, SET_ROTATION_ANGLES)
    if sra_body:
        # Head tracking
        meta.head_tracking = _extract_head_tracking(sra_body)
        # State machine
        meta.states = _extract_states(sra_body)
        # Walk speeds
        meta.walk_speeds = _extract_walk_speeds(sra_body)
        # Check for swing helper usage
        meta.uses_swing_helpers = bool(re.search(r"this\.swing[XYZ]\(", sra_body))
        # Count ALL animation assignments (direct + swing/moveY) across all states,
        # following custom method calls like normalAni(...)
        total = 0
        for s in meta.states:
            # Follow custom method calls to inline their bodies
            inlined_body = _follow_custom_methods(java_src, s.body)
            s.body = inlined_body  # update with inlined content
            total += len(_extract_all_anim_assignments(inlined_body))
        meta.total_trig_assignments = total
        meta.has_stub_friendly_trig = total > 3  # significant animation data

    # v6.7: Also analyze setLivingAnimations (func_78088_a AND func_78086_a) for animation data.
    # Some SRP models (orbScary, orbVoid, nade, quac) put ALL animation in
    # setLivingAnimations, leaving setRotationAngles empty. Without this,
    # these models appear as unrecoverable stubs.
    # func_78088_a: setLivingAnimations(Entity, float, float, float, float, float, float)
    # func_78086_a: setLivingAnimations(EntityLivingBase, float, float, float) — older override
    for sla_method in [SET_LIVING_ANIMATIONS, "func_78086_a"]:
        sla_body = _extract_method_body(java_src, sla_method)
        if not sla_body:
            continue
        if sla_method == SET_LIVING_ANIMATIONS:
            meta.body_bobs = _extract_body_bobs(sla_body)
        # If setRotationAngles had too few REAL assignments (<=3), treat as
        # effectively empty and try setLivingAnimations as the animation source.
        # This catches models where setRotationAngles only has variable declarations
        # but the actual bone assignments are in setLivingAnimations.
        if meta.total_trig_assignments <= 3:
            sla_states = _extract_states(sla_body)
            if sla_states:
                # Replace states entirely with sla states (sra had no real anims)
                meta.states = sla_states
            else:
                meta.states = [StateInfo(state_value=0, body=sla_body)]

            total = 0
            for s in meta.states:
                inlined_body = _follow_custom_methods(java_src, s.body)
                s.body = inlined_body
                total += len(_extract_all_anim_assignments(inlined_body))
            # Only update if sla actually has more assignments (avoid regressing)
            if total > meta.total_trig_assignments:
                meta.total_trig_assignments = total
                meta.has_stub_friendly_trig = total >= 2  # lower threshold for sla fallback
            if not meta.head_tracking:
                meta.head_tracking = _extract_head_tracking(sla_body)

    return meta


def analyze_all_models(
    model_names: List[str],
    decompiled_root: str,
) -> Dict[str, ModelMetadata]:
    """Analyze a list of models.

    Returns dict mapping model_name -> ModelMetadata (only for models found).
    """
    results: Dict[str, ModelMetadata] = {}
    for name in model_names:
        meta = analyze_model(name, decompiled_root)
        if meta:
            results[name] = meta
    return results


def metadata_to_dict(meta: ModelMetadata) -> dict:
    """Serialize ModelMetadata to a JSON-compatible dict."""
    return {
        "model_name": meta.model_name,
        "class_name": meta.class_name,
        "java_path": meta.java_path,
        "head_tracking": {
            "bone_name": meta.head_tracking.bone_name,
            "yaw_coeff": meta.head_tracking.yaw_coeff,
            "pitch_coeff": meta.head_tracking.pitch_coeff,
            "yaw_axis": meta.head_tracking.yaw_axis,
            "pitch_axis": meta.head_tracking.pitch_axis,
        } if meta.head_tracking else None,
        "states": [
            {"state_value": s.state_value, "body_preview": s.body[:200]}
            for s in meta.states
        ],
        "state_count": len(meta.states),
        "body_bobs": [
            {"bone": b.bone, "axis": b.axis, "expression": b.expression}
            for b in meta.body_bobs
        ],
        "walk_speeds": meta.walk_speeds,
        "uses_swing_helpers": meta.uses_swing_helpers,
        "total_trig_assignments": meta.total_trig_assignments,
        "has_stub_friendly_trig": meta.has_stub_friendly_trig,
    }


if __name__ == "__main__":
    # Self-test: analyze elvia and print metadata
    import sys
    import os
    try:
        import config
        SW = str(config.WORK_ROOT)
    except ImportError:
        SW = os.environ.get("SRP_WORK_ROOT", "/home/z/my-project/subspace-work")
    name = sys.argv[1] if len(sys.argv) > 1 else "elvia"
    meta = analyze_model(name, f"{SW}/decompiled/all")
    if meta:
        print(json.dumps(metadata_to_dict(meta), indent=2, ensure_ascii=False))
    else:
        print(f"Model {name} not found")
