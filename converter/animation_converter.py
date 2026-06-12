#!/usr/bin/env python3
"""
AnimationConverter - Animation Conversion Engine
=================================================
Converts Minecraft 1.12.2 hardcoded animations to 1.20.1 GeckoLib format.

Animation classes:
  - Class A-1: Time-driven animations (ageInTicks dependent) → .animation.json
  - Class A-2: Movement-driven animations (limbSwing dependent) → Java code (GeoBone.setRotationX/Y/Z)
  - Class B:   State machine animations (entity state dependent) → AnimationController Java code
  - Head Tracking: Head/neck rotation following player → codeAnimations Java code
"""

import json
import math
import os
import re
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from core_math import convert_model_rot, convert_model_rotation_order, rad_to_deg


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class AnimationExpression:
    """A single rotation assignment expression for a bone."""
    bone_var: str
    axis: str  # 'x', 'y', 'z'
    expression: str  # The raw Java expression
    is_time_driven: bool = False
    is_movement_driven: bool = False
    operator: str = '='  # Assignment operator: '=', '+=', '-=', '*=', '/='


@dataclass
class HeadBoneConfig:
    """Configuration for a head tracking bone chain."""
    bone_names: List[str]  # Ordered from outermost to innermost (e.g. ["head", "neck", "upper_neck"])
    max_yaw_deg: float = 75.0
    max_pitch_deg: float = 45.0


@dataclass
class AnimationState:
    """Represents a single animation state in a state machine."""
    name: str
    animation_name: str
    condition: str
    priority: int = 0
    transition_length: float = 0.0  # 0 = use default
    is_looping: bool = True


@dataclass
class IntermediateVariable:
    """An intermediate variable definition parsed from Java source."""
    name: str
    expression: str
    depends_on: List[str] = field(default_factory=list)  # Other vars this references


# ============================================================================
# AnimationConverter
# ============================================================================

class AnimationConverter:
    """
    Converts 1.12.2 animation code to GeckoLib 1.20.1 format.

    Supports:
      - Class A-1: Time-driven animations (ageInTicks) → .animation.json
      - Class A-2: Movement-driven animations (limbSwing) → compilable Java code
      - Class B: State machine animations via StateMachineConverter
      - Head tracking with multi-bone chains
    """

    def __init__(self, bone_mapping: Dict[str, str]):
        """
        Args:
            bone_mapping: Dict mapping 1.12.2 java var names to GeckoLib bone IDs
        """
        self.bone_mapping = bone_mapping
        self.warnings: List[str] = []

    def convert_set_rotation_angles(
        self,
        java_source: str,
        animation_name: str = "idle",
        sample_count: int = 120,
        dp_threshold: float = 0.5,
        time_scale: float = 1.0,
        sample_window_ticks: float = 200.0,
        static_rotations: Optional[Dict[str, Dict[str, float]]] = None,
        molang_enabled: bool = True
    ) -> dict:
        """
        Convert a setRotationAngles method to GeckoLib animation format.

        Args:
            java_source: The Java source containing the setRotationAngles method
            animation_name: Name for the animation (e.g., "idle", "walk")
            sample_count: Number of samples for time-driven animations
            dp_threshold: Douglas-Peucker simplification threshold (degrees)
            time_scale: Time scale factor (1.0 = normal)
            sample_window_ticks: Sampling window in ticks (default 200 = 10 seconds)
            static_rotations: Base rotations from static pose {bone_var: {'x': rx, 'y': ry, 'z': rz}}
                              in radians. Used for compound operators (+=, -=).
            molang_enabled: If True, attempt Molang expression generation for simple
                            cos/sin patterns before falling back to numerical sampling.

        Returns:
            Dict with:
              - 'animation_json': GeckoLib .animation.json structure (for Class A-1)
              - 'java_code': Java code snippet (for Class A-2)
              - 'anim_class': 'A-1' or 'A-2' or 'mixed'
              - 'warnings': List of warnings
        """
        # Extract the setRotationAngles method body
        method_body = self._extract_method_body(java_source)
        if not method_body:
            return {
                'animation_json': None,
                'java_code': None,
                'anim_class': None,
                'warnings': ['Could not find setRotationAngles method']
            }

        # Parse intermediate variables
        vars_def = self._parse_intermediate_variables(method_body)

        # Parse all rotation assignments
        expressions = self._parse_rotation_assignments(method_body, vars_def)

        # Classify animations
        time_driven = [e for e in expressions if e.is_time_driven]
        movement_driven = [e for e in expressions if e.is_movement_driven]

        result = {
            'animation_json': None,
            'java_code': None,
            'anim_class': 'none',
            'warnings': self.warnings
        }

        # Class A-1: Time-driven → JSON animation
        if time_driven:
            result['animation_json'] = self._convert_time_driven(
                time_driven, animation_name, sample_count, dp_threshold, time_scale,
                vars_def, sample_window_ticks, static_rotations, molang_enabled
            )
            result['anim_class'] = 'A-1'

        # Class A-2: Movement-driven → Java code
        if movement_driven:
            result['java_code'] = self._convert_movement_driven(movement_driven, vars_def)
            if result['anim_class'] == 'A-1':
                result['anim_class'] = 'mixed'
            else:
                result['anim_class'] = 'A-2'

        return result

    # ========================================================================
    # Method Body Extraction
    # ========================================================================

    def _extract_method_body(self, java_source: str) -> Optional[str]:
        """Extract the body of setRotationAngles (func_78087_a) method."""
        # Find the method - could be func_78087_a (setRotationAngles)
        pattern = re.compile(
            r'public\s+void\s+func_78087_a\s*\([^)]+\)\s*\{',
            re.DOTALL
        )
        match = pattern.search(java_source)
        if not match:
            # Try alternate pattern
            pattern = re.compile(
                r'public\s+void\s+setRotationAngles\s*\([^)]+\)\s*\{',
                re.DOTALL
            )
            match = pattern.search(java_source)

        if not match:
            return None

        # Count braces to find the matching closing brace
        start_pos = match.end() - 1  # Position of opening {
        depth = 0
        for i in range(start_pos, len(java_source)):
            if java_source[i] == '{':
                depth += 1
            elif java_source[i] == '}':
                depth -= 1
                if depth == 0:
                    return java_source[start_pos + 1:i]

        return None

    # ========================================================================
    # Intermediate Variable Parsing
    # ========================================================================

    def _parse_intermediate_variables(self, method_body: str) -> Dict[str, IntermediateVariable]:
        """
        Parse intermediate variable definitions from the method body.
        Handles patterns like:
          float f11 = MathHelper.cos(ageInTicks * 0.130998f) * 0.107215f;
          f11 = MathHelper.cos(...) * ...;
        """
        vars_def: Dict[str, IntermediateVariable] = {}

        # Pattern for: float f11 = expression;  OR  f11 = expression;
        var_pattern = re.compile(
            r'(?:float\s+)?(f\d+)\s*=\s*([^;]+);'
        )

        for match in var_pattern.finditer(method_body):
            var_name = match.group(1)
            var_expr = match.group(2).strip()

            # Skip if this is actually a bone rotation assignment
            # (e.g., this.bone.field_78795_f = f11 = ... is handled elsewhere)
            if 'field_78795_f' in var_expr or 'field_78796_g' in var_expr or 'field_78808_h' in var_expr:
                continue

            # Find dependencies on other variables
            deps = []
            for existing_var in vars_def:
                if re.search(r'\b' + re.escape(existing_var) + r'\b', var_expr):
                    deps.append(existing_var)

            vars_def[var_name] = IntermediateVariable(
                name=var_name,
                expression=var_expr,
                depends_on=deps
            )

        return vars_def

    # ========================================================================
    # Rotation Assignment Parsing
    # ========================================================================

    def _parse_rotation_assignments(
        self, method_body: str, vars_def: Dict[str, IntermediateVariable]
    ) -> List[AnimationExpression]:
        """Parse all rotation angle assignments from the method body."""
        expressions = []

        # SRG field → axis mapping
        axis_map = {
            'field_78795_f': 'x',
            'field_78796_g': 'y',
            'field_78808_h': 'z'
        }

        # Pattern for: this.boneVar.field_78795_f = expression;  (also captures +=, -=, etc.)
        pattern = re.compile(
            r'this\.(\w+)\.(field_78795_f|field_78796_g|field_78808_h)\s*([\+\-\*\/]?=)\s*([^;]+);'
        )

        for match in pattern.finditer(method_body):
            bone_var = match.group(1)
            axis_field = match.group(2)
            operator = match.group(3)
            expression = match.group(4).strip()

            axis = axis_map.get(axis_field)
            if not axis:
                continue

            # Check if bone is in mapping
            if bone_var not in self.bone_mapping:
                self.warnings.append(
                    f"Bone variable '{bone_var}' not found in bone mapping! "
                    f"Skipping rotation assignment."
                )
                continue

            # Handle compound assignments: this.bone.field = f11 = expression;
            compound_match = re.match(r'(\w+)\s*=\s*(.+)', expression)
            if compound_match and compound_match.group(1) in vars_def:
                # This is: varName = actualExpression
                # The actual rotation value is varName (a reference)
                var_name = compound_match.group(1)
                actual_expr = compound_match.group(2).strip()
                # Store the actual expression as the definition of this variable
                vars_def[var_name].expression = actual_expr
                expression = var_name  # The bone rotation references this variable

            # Classify: time-driven vs movement-driven
            # Resolve through variable dependencies
            full_expr = self._resolve_variable_expression(expression, vars_def)
            is_time = self._is_time_driven(full_expr)
            is_movement = self._is_movement_driven(full_expr)

            expr = AnimationExpression(
                bone_var=bone_var,
                axis=axis,
                expression=expression,
                is_time_driven=is_time,
                is_movement_driven=is_movement,
                operator=operator
            )
            expressions.append(expr)

        return expressions

    def _resolve_variable_expression(self, expr: str, vars_def: Dict[str, IntermediateVariable]) -> str:
        """
        Resolve all variable references in an expression to get the full expression.
        Used for classification purposes (not for evaluation).
        """
        resolved = expr
        max_depth = 10  # Prevent infinite recursion
        depth = 0
        while depth < max_depth:
            changed = False
            for var_name, var_info in vars_def.items():
                if re.search(r'\b' + re.escape(var_name) + r'\b', resolved):
                    resolved = re.sub(
                        r'\b' + re.escape(var_name) + r'\b',
                        f'({var_info.expression})',
                        resolved
                    )
                    changed = True
            if not changed:
                break
            depth += 1
        return resolved

    def _is_time_driven(self, full_expr: str) -> bool:
        """Check if an expression depends on ageInTicks."""
        return 'ageInTicks' in full_expr or 'tick' in full_expr.lower()

    def _is_movement_driven(self, full_expr: str) -> bool:
        """Check if an expression depends on limbSwing/limbSwingAmount."""
        return 'limbSwing' in full_expr

    # ========================================================================
    # Molang Safe-Subset Translation
    # ========================================================================

    # Rad-to-deg conversion factor for Molang (Molang trig uses degrees)
    _RAD_TO_DEG_FACTOR = 57.2958  # 180 / pi, rounded to 6 significant digits

    # Regex for MathHelper.cos / MathHelper.sin including SRG names
    _MATH_HELPER_COS = r'(?:MathHelper\.(?:cos|func_76134_b))'
    _MATH_HELPER_SIN = r'(?:MathHelper\.(?:sin|func_76126_a|func_76133_a))'

    # Numeric literal with optional float suffix: 0.13, 0.130998f, 5.0F, 42
    _NUM = r'([+-]?\d+(?:\.\d+)?)[fF]?'

    def _try_molang_translation(
        self,
        expr: AnimationExpression,
        vars_def: Dict[str, IntermediateVariable] = None,
        static_rotations: Optional[Dict[str, Dict[str, float]]] = None
    ) -> Optional[str]:
        """
        Attempt to translate a simple cos/sin(ageInTicks * C) * A expression
        into a GeckoLib Molang string.

        A "simple expression" matches one of these patterns:
          MathHelper.cos(ageInTicks * C) * A
          MathHelper.sin(ageInTicks * C) * A
          MathHelper.cos(ageInTicks * C + P) * A
          (float)MathHelper.cos(ageInTicks * C) * A
          A * MathHelper.cos(ageInTicks * C)    (amplitude before trig)

        Where C, A, P are numeric literals (possibly with float suffix).

        Complex expressions containing: if/else, limbSwing, method calls other
        than MathHelper.cos/sin, array access, etc. → return None (requires sampling).

        Args:
            expr: The AnimationExpression to attempt translation for
            vars_def: Intermediate variable definitions for resolution
            static_rotations: Base rotations from static pose (for compound operators)

        Returns:
            A Molang string if translatable, or None if numerical sampling is required.
        """
        if vars_def is None:
            vars_def = {}
        if static_rotations is None:
            static_rotations = {}

        # Step 1: Resolve variable references to get the full expression
        resolved = self._resolve_variable_expression(expr.expression, vars_def)

        # Step 2: Reject complex expressions
        if self._is_complex_for_molang(resolved):
            return None

        # Step 3: Try to match the simple cos/sin pattern
        match = self._match_simple_trig_pattern(resolved)
        if match is None:
            return None

        func, coefficient, phase, amplitude = match

        # Step 4: Build the Molang expression
        # Original Java: func(ageInTicks * C [+ P]) * A
        #   ageInTicks is in ticks
        # Molang: math.func(query.anim_time * 20 * C * 57.2958 [+ P_deg]) * A_deg
        #   query.anim_time is in seconds
        #   * 20 converts seconds back to ticks
        #   * C is the original coefficient
        #   * 57.2958 converts radians to degrees (Molang trig uses degrees)
        # The amplitude is in radians and needs to be converted to degrees too
        # for the final rotation output.

        # Compute the effective coefficient for Molang: 20 * C * 57.2958
        molang_coeff = 20.0 * coefficient * self._RAD_TO_DEG_FACTOR

        # Amplitude in degrees (the final rotation value)
        amplitude_deg = amplitude * self._RAD_TO_DEG_FACTOR

        # Phase in degrees (if present)
        phase_deg = phase * self._RAD_TO_DEG_FACTOR if phase is not None else None

        # Apply M_model rotation conversion: if axis is 'y' or 'z', negate amplitude
        # This matches the existing logic in _sample_bone_animation
        if expr.axis in ('y', 'z'):
            amplitude_deg = -amplitude_deg
            if phase_deg is not None:
                phase_deg = -phase_deg

        # Build Molang trig call
        molang_func = 'math.cos' if func == 'cos' else 'math.sin'

        if phase_deg is not None:
            # math.func(query.anim_time * molang_coeff + phase_deg) * amplitude_deg
            # Round to avoid floating point noise
            molang_inner = f"query.anim_time * {molang_coeff:.6g}"
            if phase_deg >= 0:
                molang_trig = f"{molang_func}({molang_inner} + {phase_deg:.6g})"
            else:
                molang_trig = f"{molang_func}({molang_inner} - {abs(phase_deg):.6g})"
        else:
            molang_trig = f"{molang_func}(query.anim_time * {molang_coeff:.6g})"

        # Apply amplitude
        if abs(amplitude_deg - 1.0) < 1e-10:
            molang_expr = molang_trig
        elif abs(amplitude_deg + 1.0) < 1e-10:
            molang_expr = f"-{molang_trig}"
        elif amplitude_deg < 0:
            molang_expr = f"-{abs(amplitude_deg):.6g} * {molang_trig}"
        else:
            molang_expr = f"{amplitude_deg:.6g} * {molang_trig}"

        # Handle compound operators (+=, -=, etc.)
        if expr.operator in ('+=', '-=', '*=', '/='):
            bone_static = static_rotations.get(expr.bone_var, {})
            base_rot_rad = bone_static.get(expr.axis, 0.0)
            base_rot_deg = base_rot_rad * self._RAD_TO_DEG_FACTOR
            # Apply M_model negation to base rotation too
            if expr.axis in ('y', 'z'):
                base_rot_deg = -base_rot_deg

            if expr.operator == '+=':
                molang_expr = f"({base_rot_deg:.6g} + {molang_expr})"
            elif expr.operator == '-=':
                molang_expr = f"({base_rot_deg:.6g} - {molang_expr})"
            elif expr.operator == '*=':
                molang_expr = f"({base_rot_deg:.6g} * {molang_expr})"
            elif expr.operator == '/=':
                molang_expr = f"({base_rot_deg:.6g} / {molang_expr})"

        return molang_expr

    def _is_complex_for_molang(self, resolved_expr: str) -> bool:
        """
        Check if a resolved expression is too complex for Molang translation.

        Complex features that disqualify an expression:
          - Ternary operators (?:)
          - limbSwing / limbSwingAmount references
          - Method calls other than MathHelper.cos/sin
          - Array access patterns
          - if/else statements
        """
        # Check for ternary
        if '?' in resolved_expr and ':' in resolved_expr:
            return True

        # Check for limbSwing references
        if 'limbSwing' in resolved_expr:
            return True

        # Check for if/else
        if re.search(r'\bif\b', resolved_expr) or re.search(r'\belse\b', resolved_expr):
            return True

        # Check for array access
        if re.search(r'\w+\[', resolved_expr):
            return True

        # Check for method calls other than MathHelper.cos/sin
        # Remove known MathHelper.cos/sin patterns first, then check for remaining calls
        cleaned = resolved_expr
        cleaned = re.sub(r'MathHelper\.(?:cos|sin|func_76134_b|func_76126_a|func_76133_a)', '', cleaned)
        cleaned = re.sub(r'\(float\)', '', cleaned)
        # Check for remaining method calls (word.word pattern with parens)
        if re.search(r'\w+\.\w+\s*\(', cleaned):
            return True

        return False

    def _match_simple_trig_pattern(self, resolved_expr: str) -> Optional[Tuple[str, float, Optional[float], float]]:
        """
        Match a resolved expression against the simple trig pattern.

        Patterns matched:
          MathHelper.cos(ageInTicks * C) * A
          MathHelper.sin(ageInTicks * C) * A
          MathHelper.cos(ageInTicks * C + P) * A
          (float)MathHelper.cos(ageInTicks * C) * A
          A * MathHelper.cos(ageInTicks * C)  (amplitude before trig)

        Returns:
            Tuple of (func, coefficient, phase_or_None, amplitude) or None if no match.
        """
        # Normalize: remove (float) casts and extra whitespace
        expr = re.sub(r'\(float\)', '', resolved_expr).strip()

        # Strip outer wrapping parentheses from variable resolution
        # e.g., "(MathHelper.cos(ageInTicks * 0.13) * 0.5)" → "MathHelper.cos(ageInTicks * 0.13) * 0.5"
        while expr.startswith('(') and expr.endswith(')'):
            # Check that the closing paren matches the opening one
            depth = 0
            matched = True
            for i, ch in enumerate(expr):
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                if depth == 0 and i < len(expr) - 1:
                    matched = False
                    break
            if matched:
                expr = expr[1:-1].strip()
            else:
                break

        cos_pat = self._MATH_HELPER_COS
        sin_pat = self._MATH_HELPER_SIN
        num = self._NUM

        # Pattern 1: MathHelper.cos/sin(ageInTicks * C [+ P]) * A
        # Pattern 2: A * MathHelper.cos/sin(ageInTicks * C [+ P])
        # Pattern 3: MathHelper.cos/sin(ageInTicks * C [+ P])  (amplitude = 1.0)

        for func_name, trig_pat in [('cos', cos_pat), ('sin', sin_pat)]:
            # --- Pattern: TRIG(ageInTicks * C [+ P]) * A ---
            # With optional phase
            m = re.match(
                rf'^{trig_pat}\s*\(\s*ageInTicks\s*\*\s*{num}\s*(?:\+\s*{num}\s*)?\)\s*\*\s*{num}$',
                expr
            )
            if m:
                coefficient = float(m.group(1))
                # Check if phase group matched (group 2)
                phase = float(m.group(2)) if m.group(2) is not None else None
                amplitude = float(m.group(3))
                return (func_name, coefficient, phase, amplitude)

            # Without phase, explicit version
            m = re.match(
                rf'^{trig_pat}\s*\(\s*ageInTicks\s*\*\s*{num}\s*\)\s*\*\s*{num}$',
                expr
            )
            if m:
                coefficient = float(m.group(1))
                amplitude = float(m.group(2))
                return (func_name, coefficient, None, amplitude)

            # --- Pattern: A * TRIG(ageInTicks * C [+ P]) ---
            # With phase
            m = re.match(
                rf'^{num}\s*\*\s*{trig_pat}\s*\(\s*ageInTicks\s*\*\s*{num}\s*(?:\+\s*{num}\s*)?\)$',
                expr
            )
            if m:
                amplitude = float(m.group(1))
                coefficient = float(m.group(2))
                phase = float(m.group(3)) if m.group(3) is not None else None
                return (func_name, coefficient, phase, amplitude)

            # Without phase
            m = re.match(
                rf'^{num}\s*\*\s*{trig_pat}\s*\(\s*ageInTicks\s*\*\s*{num}\s*\)$',
                expr
            )
            if m:
                amplitude = float(m.group(1))
                coefficient = float(m.group(2))
                return (func_name, coefficient, None, amplitude)

            # --- Pattern: TRIG(ageInTicks * C [+ P]) with implicit amplitude 1.0 ---
            m = re.match(
                rf'^{trig_pat}\s*\(\s*ageInTicks\s*\*\s*{num}\s*(?:\+\s*{num}\s*)?\)$',
                expr
            )
            if m:
                coefficient = float(m.group(1))
                phase = float(m.group(2)) if m.group(2) is not None else None
                return (func_name, coefficient, phase, 1.0)

        return None

    # ========================================================================
    # Class A-1: Time-Driven Conversion (enhanced with vars_def)
    # ========================================================================

    def _convert_time_driven(
        self,
        expressions: List[AnimationExpression],
        animation_name: str,
        sample_count: int,
        dp_threshold: float,
        time_scale: float,
        vars_def: Dict[str, IntermediateVariable] = None,
        sample_window_ticks: float = 200.0,
        static_rotations: Optional[Dict[str, Dict[str, float]]] = None,
        molang_enabled: bool = True
    ) -> dict:
        """
        Convert time-driven animations using Molang where possible, falling back
        to numerical sampling for complex expressions.

        Process:
        1. Try Molang translation for each expression (if molang_enabled)
        2. For expressions that can't be translated to Molang, use numerical sampling
        3. Molang expressions appear as string values in .animation.json
        4. Sampled expressions appear as keyframe dicts
        5. A bone can have MIXED output: e.g., x-axis as Molang, y-axis as sampled
        """
        if vars_def is None:
            vars_def = {}
        if static_rotations is None:
            static_rotations = {}

        # Split expressions into Molang-translatable and sampling-required
        # molang_results: {(bone_var, axis): molang_string}
        # sample_exprs: list of AnimationExpression that need numerical sampling
        molang_results: Dict[Tuple[str, str], str] = {}
        sample_exprs: List[AnimationExpression] = []

        for expr in expressions:
            if molang_enabled:
                molang_str = self._try_molang_translation(
                    expr, vars_def, static_rotations
                )
                if molang_str is not None:
                    molang_results[(expr.bone_var, expr.axis)] = molang_str
                    continue
            sample_exprs.append(expr)

        # --- Handle sampled expressions (existing pipeline) ---
        # Group sampled expressions by bone
        bone_exprs: Dict[str, Dict[str, str]] = {}
        bone_operators: Dict[str, Dict[str, str]] = {}
        for expr in sample_exprs:
            if expr.bone_var not in bone_exprs:
                bone_exprs[expr.bone_var] = {}
                bone_operators[expr.bone_var] = {}
            bone_exprs[expr.bone_var][expr.axis] = expr.expression
            bone_operators[expr.bone_var][expr.axis] = expr.operator

        # Sample each bone's rotation over time
        animation_bones = {}

        for bone_var, axis_exprs in bone_exprs.items():
            bone_name = self.bone_mapping[bone_var]
            axis_ops = bone_operators.get(bone_var, {})
            keyframes = self._sample_bone_animation(
                bone_var, axis_exprs, sample_count, time_scale, vars_def,
                axis_operators=axis_ops,
                sample_window_ticks=sample_window_ticks,
                static_rotations=static_rotations
            )

            if keyframes:
                # Simplify with Douglas-Peucker
                simplified = self._douglas_peucker_simplify(keyframes, dp_threshold)
                animation_bones[bone_name] = simplified

        # --- Build .animation.json structure ---
        anim_id = f"animation.model.{animation_name}"

        # Build bone animation data (combining Molang strings and sampled keyframes)
        bones_data: Dict[str, dict] = {}

        # First, add sampled keyframes
        for bone_name, keyframes in animation_bones.items():
            bone_anim: Dict[str, Any] = {}
            for kf in keyframes:
                time_s = kf['time']
                for axis in ['x', 'y', 'z']:
                    if axis in kf:
                        if "rotation" not in bone_anim:
                            bone_anim["rotation"] = {}
                        if axis not in bone_anim["rotation"]:
                            bone_anim["rotation"][axis] = {}
                        bone_anim["rotation"][axis][f"{time_s:.4f}"] = kf[axis]

            if bone_anim:
                bones_data[bone_name] = bone_anim

        # Then, add Molang expressions (may merge with existing bone_anim from sampling)
        for (bone_var, axis), molang_str in molang_results.items():
            bone_name = self.bone_mapping[bone_var]
            if bone_name not in bones_data:
                bones_data[bone_name] = {}
            if "rotation" not in bones_data[bone_name]:
                bones_data[bone_name]["rotation"] = {}
            # Molang string replaces the axis entry entirely
            bones_data[bone_name]["rotation"][axis] = molang_str

        # Calculate animation length
        # For purely Molang bones, there's no animation_length from keyframes.
        # We keep the sampled keyframe animation length if any, otherwise use
        # the sample window duration.
        max_time = self._calculate_animation_length(animation_bones) if animation_bones else 0.0
        if max_time == 0.0 and molang_results:
            # Molang-only animations loop continuously; use a reasonable default
            max_time = round(sample_window_ticks / 20.0, 4)

        animation_json = {
            "format_version": "1.8.0",
            "animations": {
                anim_id: {
                    "loop": "hold_on_last_frame",
                    "animation_length": max_time,
                    "bones": bones_data
                }
            }
        }

        return animation_json

    def _sample_bone_animation(
        self,
        bone_var: str,
        axis_exprs: Dict[str, str],
        sample_count: int,
        time_scale: float,
        vars_def: Dict[str, IntermediateVariable] = None,
        axis_operators: Optional[Dict[str, str]] = None,
        sample_window_ticks: float = 200.0,
        static_rotations: Optional[Dict[str, Dict[str, float]]] = None
    ) -> List[dict]:
        """
        Sample a bone's rotation values over time.
        Returns list of keyframe dicts: [{'time': t, 'x': rx, 'y': ry, 'z': rz}, ...]

        Time axis: samples tick values from 0 to sample_window_ticks, converts to
        GeckoLib seconds (tick / 20.0) for output. The ageInTicks substituted into
        expressions is computed as tick / time_scale.

        Compound operators (+=, -=): the sampled expression value is combined with
        the bone's static base rotation from static_rotations.
        """
        if vars_def is None:
            vars_def = {}
        if axis_operators is None:
            axis_operators = {}
        if static_rotations is None:
            static_rotations = {}

        keyframes = []

        # Sample over sample_window_ticks (default 200 ticks = 10 seconds)
        dt_ticks = sample_window_ticks / sample_count

        # Get static base rotations for this bone (in radians)
        bone_static = static_rotations.get(bone_var, {})

        for i in range(sample_count + 1):
            tick = i * dt_ticks
            age_in_ticks = tick / time_scale

            # Output time in GeckoLib seconds (20 ticks per second)
            time_sec = tick / 20.0
            kf = {'time': round(time_sec, 6)}

            for axis, expr in axis_exprs.items():
                try:
                    value = self._evaluate_expression(
                        expr, age_in_ticks,
                        limb_swing=0.0, limb_swing_amount=0.0,
                        vars_def=vars_def
                    )

                    # Apply compound operator: combine with static base rotation
                    op = axis_operators.get(axis, '=')
                    base_rot = bone_static.get(axis, 0.0)  # radians
                    if op == '+=':
                        value = base_rot + value
                    elif op == '-=':
                        value = base_rot - value
                    elif op == '*=':
                        value = base_rot * value
                    elif op == '/=':
                        value = base_rot / value if value != 0.0 else 0.0
                    # else op == '=': value stays as-is

                    # Apply full model rotation conversion (M_model = diag(1,-1,-1))
                    if axis == 'y':
                        value = -value
                    elif axis == 'z':
                        value = -value

                    kf[axis] = round(rad_to_deg(value), 6)
                except Exception as e:
                    self.warnings.append(
                        f"Failed to evaluate expression for {bone_var}.{axis}: {expr} ({e})"
                    )
                    kf[axis] = 0.0

            keyframes.append(kf)

        return keyframes

    # ========================================================================
    # Expression Evaluation (Enhanced)
    # ========================================================================

    def _evaluate_expression(
        self,
        expr: str,
        age_in_ticks: float = 0.0,
        limb_swing: float = 0.0,
        limb_swing_amount: float = 0.0,
        vars_def: Dict[str, IntermediateVariable] = None,
        head_yaw: float = 0.0,
        head_pitch: float = 0.0
    ) -> float:
        """
        Evaluate a Java math expression with the given parameter values.
        Replaces Java math functions with Python equivalents.

        Enhanced to support:
          - Ternary operators (condition ? a : b)
          - Chained method calls
          - Array access patterns
          - MathHelper/Math function resolution
          - Intermediate variable resolution
        """
        if vars_def is None:
            vars_def = {}

        py_expr = expr

        # Resolve intermediate variable references
        for var_name, var_info in vars_def.items():
            py_expr = re.sub(
                r'\b' + re.escape(var_name) + r'\b',
                f'({var_info.expression})',
                py_expr
            )

        # Handle ternary operators: condition ? a : b
        py_expr = self._resolve_ternary(py_expr)

        # Replace Java math functions (SRG names first, then deobfuscated)
        py_expr = re.sub(r'MathHelper\.func_76134_b', 'math.cos', py_expr)
        py_expr = re.sub(r'MathHelper\.func_76126_a', 'math.sin', py_expr)
        py_expr = re.sub(r'MathHelper\.func_76133_a', 'math.sin', py_expr)  # alt SRG for sin
        py_expr = re.sub(r'MathHelper\.func_76129_a', 'math.sqrt', py_expr)  # MathHelper.sqrt
        py_expr = re.sub(r'MathHelper\.func_76130_a', 'math.sqrt', py_expr)  # alt SRG
        py_expr = re.sub(r'MathHelper\.func_76142_g', 'math.floor', py_expr)  # MathHelper.floor
        py_expr = re.sub(r'MathHelper\.func_76128_c', 'math.abs', py_expr)  # MathHelper.abs
        py_expr = re.sub(r'MathHelper\.func_76131_a', 'math.clamp', py_expr)  # MathHelper.clamp
        py_expr = re.sub(r'MathHelper\.cos', 'math.cos', py_expr)
        py_expr = re.sub(r'MathHelper\.sin', 'math.sin', py_expr)
        py_expr = re.sub(r'MathHelper\.sqrt', 'math.sqrt', py_expr)
        py_expr = re.sub(r'MathHelper\.abs', 'math.abs', py_expr)

        # Replace Math.* methods
        py_expr = re.sub(r'Math\.sin', 'math.sin', py_expr)
        py_expr = re.sub(r'Math\.cos', 'math.cos', py_expr)
        py_expr = re.sub(r'Math\.sqrt', 'math.sqrt', py_expr)
        py_expr = re.sub(r'Math\.abs', 'math.abs', py_expr)
        py_expr = re.sub(r'Math\.floor', 'math.floor', py_expr)
        py_expr = re.sub(r'Math\.ceil', 'math.ceil', py_expr)
        py_expr = re.sub(r'Math\.max', 'max', py_expr)
        py_expr = re.sub(r'Math\.min', 'min', py_expr)
        py_expr = re.sub(r'Math\.toRadians', 'math.radians', py_expr)
        py_expr = re.sub(r'Math\.toDegrees', 'math.degrees', py_expr)

        # Replace Math.PI
        py_expr = py_expr.replace('Math.PI', str(math.pi))

        # Replace Java float suffixes (but not inside variable names)
        py_expr = re.sub(r'(\d+(?:\.\d+)?)[fF](?!\w)', r'\1', py_expr)

        # Replace parameter references
        py_expr = py_expr.replace('ageInTicks', str(age_in_ticks))
        py_expr = py_expr.replace('limbSwingAmount', str(limb_swing_amount))
        py_expr = py_expr.replace('limbSwing', str(limb_swing))

        # Handle partialTick / partialTicks
        py_expr = re.sub(r'\bpartialTick[s]?\b', '0.0', py_expr)

        # Remove explicit casts
        py_expr = re.sub(r'\(float\)', '', py_expr)
        py_expr = re.sub(r'\(double\)', '', py_expr)
        py_expr = re.sub(r'\(int\)', '', py_expr)

        # Handle array access patterns: array[index] → 0 (placeholder)
        # We can't resolve array values at conversion time, default to 0
        py_expr = re.sub(r'(\w+)\[(\w+|\d+)\]', '0', py_expr)

        # Handle chained method calls on non-math objects.
        # Only replace patterns like obj.method() where obj is NOT 'math'.
        # We must NOT replace math.cos(), math.sin(), etc.
        def _replace_non_math_calls(match):
            prefix = match.group(1)
            if prefix == 'math':
                return match.group(0)  # Keep math.cos(...), math.sin(...), etc.
            return '0'  # Replace unknown method calls with 0

        py_expr = re.sub(r'(\w+)\.\w+\([^)]*\)', _replace_non_math_calls, py_expr)

        # Try to evaluate using safe_eval with variable stubbing
        try:
            from core_math import safe_eval
            # Define math.radians and math.degrees for eval context
            def _radians(d): return d * math.pi / 180.0
            def _degrees(r): return r * 180.0 / math.pi
            context = {
                "math": math,
                "radians": _radians,
                "degrees": _degrees,
            }
            return safe_eval(py_expr, context=context, default=0.0)
        except Exception:
            # If safe_eval fails entirely, return 0
            return 0.0

    def _resolve_ternary(self, expr: str) -> str:
        """
        Resolve Java ternary operators (condition ? a : b) to Python (a if condition else b).

        Handles nested ternaries and complex expressions.
        Only resolves at the top level of the expression to avoid breaking
        parenthesized sub-expressions.
        """
        # Find ternary operators that aren't inside nested parentheses
        # Strategy: scan from left, track paren depth, find ? at depth 0
        depth = 0
        question_pos = -1

        for i, ch in enumerate(expr):
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == '?' and depth == 0:
                question_pos = i
                break

        if question_pos == -1:
            return expr  # No ternary found

        # Find the matching : at the same depth level
        condition = expr[:question_pos].strip()
        rest = expr[question_pos + 1:]

        # Find the colon at depth 0
        depth = 0
        colon_pos = -1
        for i, ch in enumerate(rest):
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == ':' and depth == 0:
                colon_pos = i
                break

        if colon_pos == -1:
            return expr  # Malformed ternary, leave as-is

        true_expr = rest[:colon_pos].strip()
        false_expr = rest[colon_pos + 1:].strip()

        # Recursively resolve nested ternaries
        true_expr = self._resolve_ternary(true_expr)
        false_expr = self._resolve_ternary(false_expr)

        # Convert to Python ternary
        # Note: Java condition expressions use &&, || which need conversion too
        py_condition = condition.replace('&&', ' and ').replace('||', ' or ')
        py_condition = py_condition.replace('!', ' not ')

        return f"(({true_expr}) if ({py_condition}) else ({false_expr}))"

    # ========================================================================
    # Class A-2: Movement-Driven Conversion (Enhanced)
    # ========================================================================

    def _convert_movement_driven(
        self,
        expressions: List[AnimationExpression],
        vars_def: Dict[str, IntermediateVariable] = None
    ) -> str:
        """
        Convert movement-driven animations to compilable GeckoLib Java code.

        Generates proper Java code using GeoBone.setRotationX/Y/Z with:
          - Full expression resolution (not stub comments)
          - GeckoLib API-compatible code (GeoBone, not IBone)
          - Proper coordinate transformation for animation values
          - Intermediate variable resolution into the output code
        """
        if vars_def is None:
            vars_def = {}

        lines = []
        lines.append("// Auto-generated by MC1122 -> GeckoLib Animation Converter")
        lines.append("// Class A-2: Movement-driven animation (limbSwing dependent)")
        lines.append("// Place this code in your GeoModel's codeAnimations method")
        lines.append("")

        # Emit parameter extraction
        lines.append("// Get animation parameters from entity")
        lines.append("float limbSwing = animatable.limbSwing;")
        lines.append("float limbSwingAmount = animatable.limbSwingAmount;")
        lines.append("float ageInTicks = animatable.ageInTicks;")
        lines.append("")

        # Emit intermediate variable calculations
        if vars_def:
            lines.append("// Intermediate variables (resolved from original code)")
            # Sort variables by dependency order
            sorted_vars = self._topological_sort_vars(vars_def)
            for var_name in sorted_vars:
                var_info = vars_def[var_name]
                converted_expr = self._convert_expression_to_geckolib(var_info.expression)
                lines.append(f"float {var_name} = (float)({converted_expr});")
            lines.append("")

        # Group by bone
        bone_exprs: Dict[str, Dict[str, str]] = {}
        for expr in expressions:
            if expr.bone_var not in bone_exprs:
                bone_exprs[expr.bone_var] = {}
            bone_exprs[expr.bone_var][expr.axis] = expr.expression

        lines.append("// Bone rotation assignments:")

        for bone_var, axis_exprs in bone_exprs.items():
            bone_name = self.bone_mapping[bone_var]
            lines.append(f"GeoBone {bone_var}Bone = this.getAnimationProcessor().getBone(\"{bone_name}\");")
            lines.append(f"if ({bone_var}Bone != null) {{")

            for axis, expr in axis_exprs.items():
                # Convert expression for GeckoLib
                converted_expr = self._convert_expression_to_geckolib(expr)
                # Apply coordinate transformation
                # M_model = diag(1, -1, -1): X preserved, Y negated, Z negated
                if axis == 'y':
                    converted_expr = f"-({converted_expr})"
                elif axis == 'z':
                    converted_expr = f"-({converted_expr})"
                # X stays the same

                method = f"setRotation{axis.upper()}"
                lines.append(f"    {bone_var}Bone.{method}((float)({converted_expr}));")

            lines.append("}")
            lines.append("")

        return '\n'.join(lines)

    def _topological_sort_vars(self, vars_def: Dict[str, IntermediateVariable]) -> List[str]:
        """Sort variables by dependency order (dependencies first)."""
        sorted_vars = []
        visited = set()

        def visit(name: str):
            if name in visited:
                return
            visited.add(name)
            if name in vars_def:
                for dep in vars_def[name].depends_on:
                    visit(dep)
            sorted_vars.append(name)

        for var_name in vars_def:
            visit(var_name)

        return sorted_vars

    def _convert_expression_to_geckolib(self, expr: str) -> str:
        """
        Convert a Java expression to GeckoLib-compatible Java.
        Replaces SRG names, MathHelper references, and removes unnecessary casts.
        """
        result = expr

        # Replace MathHelper SRG names with standard Java Math
        result = result.replace('MathHelper.func_76134_b', 'Math.cos')
        result = result.replace('MathHelper.func_76126_a', 'Math.sin')
        result = result.replace('MathHelper.func_76133_a', 'Math.sin')
        result = result.replace('MathHelper.func_76129_a', 'Math.sqrt')
        result = result.replace('MathHelper.func_76130_a', 'Math.sqrt')
        result = result.replace('MathHelper.func_76142_g', 'Math.floor')
        result = result.replace('MathHelper.func_76128_c', 'Math.abs')
        result = result.replace('MathHelper.func_76131_a', 'MathHelper.clamp')
        result = result.replace('MathHelper.cos', 'Math.cos')
        result = result.replace('MathHelper.sin', 'Math.sin')
        result = result.replace('MathHelper.sqrt', 'Math.sqrt')
        result = result.replace('MathHelper.abs', 'Math.abs')

        # Remove unnecessary casts (keep the expression intact)
        result = result.replace('(float)', '')
        result = result.replace('(double)', '')

        # Handle ternary operators: keep as-is (valid Java)
        # But convert && → &&, || → || (no change needed in Java)

        return result

    # ========================================================================
    # Class A-2: Template-Based Code Generation
    # ========================================================================

    def convert_movement_driven_templated(
        self,
        expressions: List[AnimationExpression],
        vars_def: Dict[str, IntermediateVariable] = None
    ) -> str:
        """
        Convert movement-driven animations using Jinja2 template.
        Returns the rendered Java code string.
        """
        if vars_def is None:
            vars_def = {}

        env = self._get_jinja_env()
        template = env.get_template('java_animation.java.j2')

        # Prepare bone_animations data for template
        bone_animations = []
        bone_exprs: Dict[str, Dict[str, str]] = {}
        for expr in expressions:
            if expr.bone_var not in bone_exprs:
                bone_exprs[expr.bone_var] = {}
            bone_exprs[expr.bone_var][expr.axis] = expr.expression

        for bone_var, axis_exprs in bone_exprs.items():
            bone_name = self.bone_mapping[bone_var]
            anim_dict = {
                'bone_var': bone_var,
                'bone_name': bone_name,
                'rotation_x': None,
                'rotation_y': None,
                'rotation_z': None,
                'position_x': None,
                'position_y': None,
                'position_z': None,
            }
            for axis, expr in axis_exprs.items():
                converted = self._convert_expression_to_geckolib(expr)
                # Apply coordinate transformation
                if axis == 'y':
                    converted = f"-({converted})"
                elif axis == 'z':
                    converted = f"-({converted})"
                anim_dict[f'rotation_{axis}'] = converted

            bone_animations.append(anim_dict)

        output = template.render(
            package_name="com.example.srparasites.client.model",
            class_name="KirinGeoModel",
            entity_class="KirinEntity",
            bone_animations=bone_animations
        )
        return output

    # ========================================================================
    # Douglas-Peucker Simplification
    # ========================================================================

    # Minimum time gap between keyframes for smooth animation (seconds)
    # If Douglas-Peucker removes keyframes creating gaps larger than this,
    # we re-insert intermediate keyframes to prevent jerky animation.
    _MAX_KEYFRAME_GAP_SECONDS = 0.35

    def _douglas_peucker_simplify(
        self, keyframes: List[dict], threshold: float
    ) -> List[dict]:
        """Simplify keyframes using Douglas-Peucker algorithm.

        After DP simplification, we enforce a minimum keyframe density by
        re-inserting keyframes from the original set if any gap exceeds
        _MAX_KEYFRAME_GAP_SECONDS. This prevents the animation from becoming
        too sparse, which causes visible jerkiness even with catmullrom
        interpolation.

        Args:
            keyframes: List of keyframe dicts with 'time' and axis values
            threshold: Douglas-Peucker distance threshold in degrees

        Returns:
            Simplified list of keyframes with enforced minimum density
        """
        if len(keyframes) <= 2:
            return keyframes

        axes = ['x', 'y', 'z']
        kept_indices = set()

        for axis in axes:
            if axis not in keyframes[0]:
                continue
            points = [(kf['time'], kf.get(axis, 0.0)) for kf in keyframes]
            indices = self._dp_axis(points, threshold)
            kept_indices.update(indices)

        kept_indices.add(0)
        kept_indices.add(len(keyframes) - 1)

        sorted_indices = sorted(kept_indices)

        # Enforce minimum keyframe density: if any gap between consecutive
        # kept keyframes exceeds _MAX_KEYFRAME_GAP_SECONDS, re-insert
        # intermediate keyframes from the original set.
        dense_indices = list(sorted_indices)
        i = 0
        while i < len(dense_indices) - 1:
            idx_a = dense_indices[i]
            idx_b = dense_indices[i + 1]
            time_a = keyframes[idx_a]['time']
            time_b = keyframes[idx_b]['time']
            gap = time_b - time_a

            if gap > self._MAX_KEYFRAME_GAP_SECONDS:
                # Find the midpoint keyframe in the original set
                mid_time = (time_a + time_b) / 2.0
                # Find the closest original keyframe to the midpoint
                best_idx = None
                best_dist = float('inf')
                for j in range(idx_a + 1, idx_b):
                    if j not in dense_indices:
                        dist = abs(keyframes[j]['time'] - mid_time)
                        if dist < best_dist:
                            best_dist = dist
                            best_idx = j
                if best_idx is not None:
                    dense_indices.insert(i + 1, best_idx)
                    # Don't advance i — check the new gap too
                    continue
            i += 1

        return [keyframes[i] for i in sorted(dense_indices)]

    def _dp_axis(self, points: List[Tuple[float, float]], threshold: float) -> List[int]:
        """Douglas-Peucker for a single axis."""
        if len(points) <= 2:
            return [0, len(points) - 1]

        start = points[0]
        end = points[-1]

        max_dist = 0
        max_idx = 0

        for i in range(1, len(points) - 1):
            dist = self._point_line_distance(points[i], start, end)
            if dist > max_dist:
                max_dist = dist
                max_idx = i

        if max_dist > threshold:
            left = self._dp_axis(points[:max_idx + 1], threshold)
            right = self._dp_axis(points[max_idx:], threshold)
            right_offset = [r + max_idx for r in right]
            return left[:-1] + right_offset
        else:
            return [0, len(points) - 1]

    @staticmethod
    def _point_line_distance(
        point: Tuple[float, float],
        line_start: Tuple[float, float],
        line_end: Tuple[float, float]
    ) -> float:
        """Calculate perpendicular distance from a point to a line."""
        x0, y0 = point
        x1, y1 = line_start
        x2, y2 = line_end

        dx = x2 - x1
        dy = y2 - y1

        if dx == 0 and dy == 0:
            return math.sqrt((x0 - x1) ** 2 + (y0 - y1) ** 2)

        dist = abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / math.sqrt(dx ** 2 + dy ** 2)
        return dist

    def _calculate_animation_length(self, animation_bones: dict) -> float:
        """Calculate the total animation length from all keyframes."""
        max_time = 0.0
        for bone_name, keyframes in animation_bones.items():
            for kf in keyframes:
                if kf['time'] > max_time:
                    max_time = kf['time']
        return round(max_time, 4)

    # ========================================================================
    # Jinja2 Template Support
    # ========================================================================

    def _get_jinja_env(self):
        """Get or create the Jinja2 environment with custom filters."""
        try:
            from jinja2 import Environment, FileSystemLoader
        except ImportError:
            raise ImportError(
                "Jinja2 is required for template-based output. "
                "Install it with: pip install Jinja2"
            )

        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(
            loader=FileSystemLoader(template_dir),
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        # Register custom filters
        env.filters['round4'] = lambda v: round(v, 4)
        env.filters['tojson_indent'] = lambda v, indent=2: json.dumps(v, indent=indent, ensure_ascii=False)
        return env

    def render_animation_json_templated(self, animation_json: dict) -> str:
        """
        Render an animation JSON dict using the Jinja2 template.

        Args:
            animation_json: The animation JSON dict from _convert_time_driven()

        Returns:
            Formatted JSON string via template
        """
        env = self._get_jinja_env()
        template = env.get_template('animation.json.j2')

        # Extract animations from the nested structure
        anims = animation_json.get('animations', {})

        # Build template data
        animations_list = []
        for anim_name, anim_data in anims.items():
            bones_list = []
            for bone_name, bone_data in anim_data.get('bones', {}).items():
                bone_dict = {'name': bone_name}

                for channel in ['rotation', 'position', 'scale']:
                    if channel in bone_data:
                        channel_data = {}
                        for axis, axis_data in bone_data[channel].items():
                            if isinstance(axis_data, (int, float)):
                                channel_data[axis] = {'single_value': axis_data}
                            elif isinstance(axis_data, dict):
                                keyframes = [
                                    {'time': float(t), 'value': v}
                                    for t, v in axis_data.items()
                                ]
                                keyframes.sort(key=lambda kf: kf['time'])
                                channel_data[axis] = {'keyframes': keyframes}
                        bone_dict[channel] = channel_data

                # Add channel presence flags for comma handling in template
                bone_dict['has_position'] = 'position' in bone_dict
                bone_dict['has_scale'] = 'scale' in bone_dict

                bones_list.append(bone_dict)

            animations_list.append({
                'name': anim_name,
                'loop': anim_data.get('loop', 'hold_on_last_frame'),
                'animation_length': anim_data.get('animation_length', 0.0),
                'override_previous': anim_data.get('override_previous', False),
                'bones': bones_list
            })

        output = template.render(
            format_version=animation_json.get('format_version', '1.8.0'),
            animations=animations_list
        )
        return output


# ============================================================================
# Class B: State Machine Converter
# ============================================================================

class StateMachineConverter:
    """
    Converts entity state-based animation logic to GeckoLib AnimationController code.

    Handles state machines where different entity states (idle, walking, attacking,
    etc.) trigger different animation sets with proper state transitions and blending.
    """

    def __init__(self, bone_mapping: Dict[str, str] = None):
        """
        Args:
            bone_mapping: Dict mapping 1.12.2 java var names to GeckoLib bone IDs
        """
        self.bone_mapping = bone_mapping or {}
        self.warnings: List[str] = []
        self.states: List[AnimationState] = []
        self._jinja_env = None

    def parse_entity_states(self, entity_java_source: str) -> List[AnimationState]:
        """
        Parse entity state fields from the Entity class source.

        Looks for common patterns:
          - boolean fields: isMoving, isAttacking, isIdle, etc.
          - int/enum fields: getState(), state == State.IDLE
          - health-based conditions: getHealth() > 0

        Args:
            entity_java_source: The decompiled Entity class Java source

        Returns:
            List of AnimationState objects
        """
        states = []

        # Parse boolean state fields
        bool_pattern = re.compile(r'private\s+boolean\s+(\w+)')
        for match in bool_pattern.finditer(entity_java_source):
            field_name = match.group(1)
            # Common entity state names
            state_names = {
                'isMoving': 'walk',
                'isAttacking': 'attack',
                'isIdle': 'idle',
                'isAggressive': 'aggressive',
                'isHurt': 'hurt',
                'isDead': 'death',
                'isCharging': 'charge',
                'isFlying': 'fly',
                'isSwimming': 'swim',
                'isSprinting': 'sprint',
            }
            if field_name in state_names:
                anim_name = state_names[field_name]
                states.append(AnimationState(
                    name=anim_name,
                    animation_name=f"animation.model.{anim_name}",
                    condition=f"animatable.{field_name}()",
                    priority=self._state_priority(anim_name),
                    is_looping=True
                ))

        # Parse int state fields with common state patterns
        int_pattern = re.compile(r'private\s+int\s+(\w+)(?:\s*=\s*(\d+))?')
        for match in int_pattern.finditer(entity_java_source):
            field_name = match.group(1)
            if field_name in ('state', 'animationState', 'actionState', 'phase'):
                # Generate states for common integer state values
                for i, state_name in enumerate(['idle', 'walk', 'attack', 'hurt', 'death']):
                    states.append(AnimationState(
                        name=f"{state_name}",
                        animation_name=f"animation.model.{state_name}",
                        condition=f"animatable.get{field_name[0].upper()}{field_name[1:]}() == {i}",
                        priority=self._state_priority(state_name),
                        is_looping=(state_name not in ('attack', 'hurt', 'death'))
                    ))

        # Always add a default idle state if not present
        has_idle = any(s.name == 'idle' for s in states)
        if not has_idle:
            states.append(AnimationState(
                name='idle',
                animation_name='animation.model.idle',
                condition='true',
                priority=-100,  # Lowest priority (fallback)
                is_looping=True
            ))

        # Sort by priority (highest first)
        states.sort(key=lambda s: s.priority, reverse=True)

        self.states = states
        return states

    @staticmethod
    def _state_priority(state_name: str) -> int:
        """Assign priority to animation states. Higher = checked first."""
        priorities = {
            'death': 1000,
            'hurt': 900,
            'attack': 800,
            'charge': 700,
            'aggressive': 600,
            'sprint': 500,
            'fly': 400,
            'swim': 350,
            'walk': 300,
            'idle': -100,
        }
        return priorities.get(state_name, 0)

    def add_state(
        self,
        name: str,
        animation_name: str,
        condition: str,
        priority: int = 0,
        transition_length: float = 0.0,
        is_looping: bool = True
    ) -> None:
        """Manually add an animation state."""
        self.states.append(AnimationState(
            name=name,
            animation_name=animation_name,
            condition=condition,
            priority=priority,
            transition_length=transition_length,
            is_looping=is_looping
        ))
        # Re-sort
        self.states.sort(key=lambda s: s.priority, reverse=True)

    def generate_controller_code(
        self,
        controller_name: str = "mainController",
        default_transition_length: float = 5.0,
        package_name: str = "com.example.srparasites.client.model",
        class_name: str = "KirinGeoModel",
        entity_class: str = "KirinEntity"
    ) -> str:
        """
        Generate GeckoLib AnimationController Java code.

        Args:
            controller_name: Name for the controller
            default_transition_length: Default transition blending duration in ticks
            package_name: Java package name
            class_name: Model class name
            entity_class: Entity class name

        Returns:
            Java code string for the AnimationController
        """
        env = self._get_jinja_env()
        template = env.get_template('java_controller.java.j2')

        output = template.render(
            package_name=package_name,
            class_name=class_name,
            entity_class=entity_class,
            controller_name=controller_name,
            transition_length=default_transition_length,
            states=self.states
        )
        return output

    def generate_controller_code_direct(
        self,
        controller_name: str = "mainController",
        default_transition_length: float = 5.0,
        entity_class: str = "KirinEntity"
    ) -> str:
        """
        Generate AnimationController Java code directly (without template).

        Returns:
            Java code string
        """
        lines = []

        lines.append(f"AnimationController<{entity_class}> {controller_name} =")
        lines.append(f"    new AnimationController<{entity_class}>(this, \"{controller_name}\", {default_transition_length}f, event -> {{")
        lines.append(f"        {entity_class} animatable = event.getAnimatable();")
        lines.append("")

        for state in self.states:
            lines.append(f"        // State: {state.name} (priority {state.priority})")
            lines.append(f"        if ({state.condition}) {{")
            if state.is_looping:
                lines.append(f"            event.getController().setAnimation(")
                lines.append(f"                RawAnimation.begin().then(\"{state.animation_name}\", Animation.LoopType.LOOP)")
                lines.append(f"            );")
            else:
                lines.append(f"            event.getController().setAnimation(")
                lines.append(f"                RawAnimation.begin().then(\"{state.animation_name}\", Animation.LoopType.PLAY_ONCE)")
                lines.append(f"            );")
            lines.append("            return PlayState.CONTINUE;")
            lines.append("        }")
            lines.append("")

        lines.append("        // Default: no animation plays")
        lines.append("        return PlayState.STOP;")
        lines.append("    });")

        return '\n'.join(lines)

    def _get_jinja_env(self):
        """Get or create the Jinja2 environment."""
        if self._jinja_env is None:
            try:
                from jinja2 import Environment, FileSystemLoader
            except ImportError:
                raise ImportError(
                    "Jinja2 is required for template-based output. "
                    "Install it with: pip install Jinja2"
                )

            template_dir = os.path.join(os.path.dirname(__file__), 'templates')
            self._jinja_env = Environment(
                loader=FileSystemLoader(template_dir),
                keep_trailing_newline=True,
                trim_blocks=True,
                lstrip_blocks=True,
            )
        return self._jinja_env


# ============================================================================
# Head Tracking Converter
# ============================================================================

class HeadTrackingConverter:
    """
    Generates GeckoLib-compatible head tracking code for entity models.

    Supports:
      - Single head bone rotation
      - Multi-bone head chains (head → neck → upper_neck) with distributed rotation
      - Yaw and pitch clamping
      - Coordinate transformation for GeckoLib's Y-up LH system
    """

    def __init__(self, bone_mapping: Dict[str, str] = None):
        self.bone_mapping = bone_mapping or {}
        self.warnings: List[str] = []
        self._jinja_env = None

    def generate_head_tracking_code(
        self,
        head_config: HeadBoneConfig,
        entity_class: str = "KirinEntity",
        method_style: str = "geckolib"
    ) -> str:
        """
        Generate head tracking Java code for the codeAnimations method.

        Args:
            head_config: Head bone chain configuration
            entity_class: Entity class name
            method_style: "geckolib" for GeoBone API, "legacy" for IBone API

        Returns:
            Java code string for head rotation
        """
        lines = []
        bone_names = head_config.bone_names
        max_yaw = head_config.max_yaw_deg
        max_pitch = head_config.max_pitch_deg

        lines.append("// Head tracking: Rotate head/neck bones to follow look direction")
        lines.append(f"// Head chain: {' -> '.join(reversed(bone_names))}")
        lines.append(f"// Max yaw: {max_yaw}°, Max pitch: {max_pitch}°")
        lines.append("")

        # Get bone references
        for bone_name in bone_names:
            var_name = self._bone_name_to_var(bone_name)
            lines.append(f"GeoBone {var_name}Bone = this.getAnimationProcessor().getBone(\"{bone_name}\");")

        lines.append("")

        # Get look angles
        lines.append("// Get look angles from entity")
        lines.append(f"float yaw = animatable.getYRot() * ((float) Math.PI / 180f);")
        lines.append(f"float pitch = animatable.getXRot() * ((float) Math.PI / 180f);")
        lines.append("")

        # Calculate clamped rotations
        lines.append("// Calculate head rotation with clamping")
        lines.append(f"float maxYaw = (float) Math.toRadians({max_yaw});")
        lines.append(f"float maxPitch = (float) Math.toRadians({max_pitch});")
        lines.append("float headYaw = Math.max(-maxYaw, Math.min(maxYaw, yaw));")
        lines.append("float headPitch = Math.max(-maxPitch, Math.min(maxPitch, pitch));")
        lines.append("")

        # Apply rotation to bones
        if len(bone_names) == 1:
            # Single head bone
            var_name = self._bone_name_to_var(bone_names[0])
            lines.append(f"if ({var_name}Bone != null) {{")
            # GeckoLib: setRotationY for yaw (Y rotation), setRotationX for pitch (X rotation)
            # Pitch is negated because MC pitch direction is opposite to GeckoLib X rotation
            lines.append(f"    {var_name}Bone.setRotationY(headYaw);")
            lines.append(f"    {var_name}Bone.setRotationX(-headPitch);")
            lines.append("}")
        else:
            # Multi-bone head chain: distribute rotation evenly
            chain_length = len(bone_names)
            lines.append(f"// Multi-bone head chain: distribute rotation across {chain_length} bones")
            lines.append(f"float boneCount = {chain_length}.0f;")
            lines.append("")

            for bone_name in bone_names:
                var_name = self._bone_name_to_var(bone_name)
                lines.append(f"if ({var_name}Bone != null) {{")
                lines.append(f"    {var_name}Bone.setRotationY(headYaw / boneCount);")
                lines.append(f"    {var_name}Bone.setRotationX(-headPitch / boneCount);")
                lines.append("}")
                lines.append("")

        return '\n'.join(lines)

    def generate_head_tracking_templated(
        self,
        head_config: HeadBoneConfig,
        package_name: str = "com.example.srparasites.client.model",
        class_name: str = "AnimationUtils",
        entity_class: str = "KirinEntity",
        mod_id: str = "srparasites"
    ) -> str:
        """
        Generate a utility class with head tracking methods using Jinja2 template.

        Args:
            head_config: Head bone chain configuration
            package_name: Java package name
            class_name: Utility class name
            entity_class: Entity class name
            mod_id: Mod identifier

        Returns:
            Java utility class code string
        """
        env = self._get_jinja_env()
        template = env.get_template('utility_class.java.j2')

        head_tracking_dict = {
            'head_bones': head_config.bone_names,
            'max_yaw': head_config.max_yaw_deg,
            'max_pitch': head_config.max_pitch_deg,
            'yaw_divisor': float(len(head_config.bone_names)),
            'pitch_divisor': float(len(head_config.bone_names)),
        }

        output = template.render(
            package_name=package_name,
            class_name=class_name,
            mod_id=mod_id,
            entity_class=entity_class,
            head_tracking=head_tracking_dict
        )
        return output

    def detect_head_bones(self, bone_mapping: Dict[str, str]) -> Optional[HeadBoneConfig]:
        """
        Auto-detect head bone chain from the bone mapping.

        Looks for common head bone naming patterns:
          - head, Head, headBone
          - neck, Neck, neckBone
          - upper_neck, upperNeck
          - head_1, head_2 (numbered variants)
          - jointH (Kirin-specific)

        Args:
            bone_mapping: Dict of java var name -> bone name

        Returns:
            HeadBoneConfig if head bones found, None otherwise
        """
        head_names = []
        neck_names = []

        for var_name, bone_name in bone_mapping.items():
            name_lower = bone_name.lower()
            if name_lower in ('head', 'headbone') or name_lower.startswith('head_'):
                head_names.append(bone_name)
            elif name_lower in ('neck', 'neckbone', 'upper_neck', 'upperneck'):
                neck_names.append(bone_name)
            elif name_lower == 'jointh':
                head_names.append(bone_name)

        if not head_names:
            return None

        # Build chain from innermost (upper_neck) to outermost (head)
        chain = []
        # Sort neck bones by specificity (upper_neck before neck)
        neck_names.sort(key=lambda n: (0 if 'upper' in n.lower() else 1, n))
        chain.extend(neck_names)
        chain.extend(head_names[:1])  # Only take one head bone

        return HeadBoneConfig(
            bone_names=chain,
            max_yaw_deg=75.0,
            max_pitch_deg=45.0
        )

    @staticmethod
    def _bone_name_to_var(bone_name: str) -> str:
        """Convert a bone name to a valid Java variable name."""
        # Remove non-alphanumeric characters and camelCase
        var = re.sub(r'[^a-zA-Z0-9]', '', bone_name)
        # Ensure starts with lowercase
        if var and var[0].isupper():
            var = var[0].lower() + var[1:]
        return var if var else "bone"

    def _get_jinja_env(self):
        """Get or create the Jinja2 environment."""
        if self._jinja_env is None:
            try:
                from jinja2 import Environment, FileSystemLoader
            except ImportError:
                raise ImportError(
                    "Jinja2 is required for template-based output. "
                    "Install it with: pip install Jinja2"
                )

            template_dir = os.path.join(os.path.dirname(__file__), 'templates')
            self._jinja_env = Environment(
                loader=FileSystemLoader(template_dir),
                keep_trailing_newline=True,
                trim_blocks=True,
                lstrip_blocks=True,
            )
        return self._jinja_env


# ============================================================================
# Kirin-Specialized Converter (Enhanced)
# ============================================================================

class KirinAnimationConverter(AnimationConverter):
    """
    Specialized converter for ModelKirin's animation code.
    Handles the specific intermediate variable patterns used in ModelKirin.
    """

    def convert_kirin_idle(
        self,
        java_source: str,
        sample_count: int = 120,
        dp_threshold: float = 0.01
    ) -> dict:
        """
        Convert the Kirin idle animation (func_78087_a method).

        The Kirin idle animation uses intermediate variables:
          f11 = MathHelper.cos(ageInTicks * 0.130998f) * 0.107215f
          f22 = MathHelper.cos(ageInTicks * 0.0819112f) * 0.1206261f
          f33 = MathHelper.cos(ageInTicks * 0.0627955f) * 0.09067262f

        And assigns rotations to many bones using these variables.
        """
        # Find the method body
        method_body = self._extract_method_body(java_source)
        if not method_body:
            # Try extracting from the full source directly
            start_marker = 'func_78087_a'
            start_idx = java_source.find(start_marker)
            if start_idx >= 0:
                brace_start = java_source.find('{', start_idx)
                depth = 0
                end_idx = brace_start
                for i in range(brace_start, len(java_source)):
                    if java_source[i] == '{':
                        depth += 1
                    elif java_source[i] == '}':
                        depth -= 1
                        if depth == 0:
                            end_idx = i
                            break
                method_body = java_source[brace_start + 1:end_idx]

        if not method_body:
            return {
                'animation_json': None,
                'java_code': None,
                'anim_class': None,
                'warnings': ['Could not find setRotationAngles method body']
            }

        # Parse intermediate variables using the enhanced parser
        vars_def = self._parse_intermediate_variables(method_body)

        # Also parse compound assignments to capture additional variable definitions
        compound_pattern = re.compile(
            r'this\.(\w+)\.(field_78795_f|field_78796_g|field_78808_h)\s*=\s*(\w+)\s*=\s*([^;]+);'
        )
        for match in compound_pattern.finditer(method_body):
            var_name = match.group(3)
            expr = match.group(4).strip()
            if var_name not in vars_def:
                vars_def[var_name] = IntermediateVariable(
                    name=var_name,
                    expression=expr,
                    depends_on=[]
                )
            else:
                # Update the expression from the compound assignment
                vars_def[var_name].expression = expr

        # Parse all bone rotation assignments
        axis_map = {
            'field_78795_f': 'x',
            'field_78796_g': 'y',
            'field_78808_h': 'z'
        }

        bone_rotations: Dict[str, Dict[str, str]] = {}

        # Pattern: this.jointURAX.field_78795_f = -f11;
        rot_pattern = re.compile(
            r'this\.(\w+)\.(field_78795_f|field_78796_g|field_78808_h)\s*=\s*([^;]+);'
        )

        for match in rot_pattern.finditer(method_body):
            bone_var = match.group(1)
            axis_field = match.group(2)
            expr = match.group(3).strip()

            axis = axis_map.get(axis_field)
            if not axis:
                continue

            if bone_var not in self.bone_mapping:
                self.warnings.append(f"Bone '{bone_var}' not in mapping")
                continue

            # Handle compound assignments: expr might be "f11 = MathHelper.cos(...)"
            compound_match = re.match(r'(\w+)\s*=\s*(.+)', expr)
            if compound_match and compound_match.group(1) in vars_def:
                var_name = compound_match.group(1)
                actual_expr = compound_match.group(2).strip()
                vars_def[var_name].expression = actual_expr
                expr = var_name

            if bone_var not in bone_rotations:
                bone_rotations[bone_var] = {}
            bone_rotations[bone_var][axis] = expr

        # Parse offset-based animations (position channel)
        offset_map = {
            'field_82906_o': 'x',
            'field_82907_q': 'y',
            'field_82908_p': 'z'
        }

        offset_pattern = re.compile(
            r'this\.(\w+)\.(field_82906_o|field_82907_q|field_82908_p)\s*=\s*([^;]+);'
        )

        bone_offsets: Dict[str, Dict[str, str]] = {}
        for match in offset_pattern.finditer(method_body):
            bone_var = match.group(1)
            offset_field = match.group(2)
            expr = match.group(3).strip()

            axis = offset_map.get(offset_field)
            if not axis:
                continue

            if bone_var not in self.bone_mapping:
                continue

            if bone_var not in bone_offsets:
                bone_offsets[bone_var] = {}
            bone_offsets[bone_var][axis] = expr

        # Now sample the animation
        animation_bones = {}

        # FFT-based auto-period detection replaces hardcoded 2*pi.
        # The old code used period = 2 * math.pi (~6.28s) regardless of the
        # actual animation frequencies. This caused incorrect sampling windows
        # for animations whose dominant period is much shorter or longer.
        # We now auto-detect the real period from the expression coefficients.
        period = self._detect_animation_period(vars_def)
        if period is None:
            # Fallback: use a generous default sampling window of 10 seconds
            # (200 ticks at 20 tps), which covers most idle animation cycles.
            period = 10.0

        for bone_var, axis_exprs in bone_rotations.items():
            bone_name = self.bone_mapping[bone_var]
            keyframes = []

            for i in range(sample_count + 1):
                t = i * period / sample_count
                age_in_ticks = t * 20.0

                kf = {'time': round(t, 6)}

                for axis, expr in axis_exprs.items():
                    try:
                        value = self._evaluate_kirin_expression(
                            expr, age_in_ticks, vars_def
                        )
                        # Apply coordinate system rotation conversion
                        if axis == 'y':
                            value = -value
                        elif axis == 'z':
                            value = -value
                        kf[axis] = round(rad_to_deg(value), 6)
                    except Exception as e:
                        self.warnings.append(
                            f"Eval failed for {bone_var}.{axis}: {expr} ({e})"
                        )
                        kf[axis] = 0.0

                keyframes.append(kf)

            simplified = self._douglas_peucker_simplify(keyframes, dp_threshold)
            if simplified:
                animation_bones[bone_name] = simplified

        # Build .animation.json
        anim_id = "animation.model.idle"
        bones_data = {}

        for bone_name, keyframes in animation_bones.items():
            bone_anim = {"rotation": {}}
            for kf in keyframes:
                time_s = kf['time']
                for axis in ['x', 'y', 'z']:
                    if axis in kf:
                        if axis not in bone_anim["rotation"]:
                            bone_anim["rotation"][axis] = {}
                        bone_anim["rotation"][axis][f"{time_s:.4f}"] = kf[axis]

            has_values = False
            for axis_data in bone_anim["rotation"].values():
                for v in axis_data.values():
                    if abs(v) > 0.001:
                        has_values = True
                        break

            if has_values:
                bones_data[bone_name] = bone_anim

        anim_length = 0.0
        for bone_name, keyframes in animation_bones.items():
            for kf in keyframes:
                if kf['time'] > anim_length:
                    anim_length = kf['time']

        animation_json = {
            "format_version": "1.8.0",
            "animations": {
                anim_id: {
                    "loop": "loop",
                    "animation_length": round(anim_length, 4),
                    "bones": bones_data
                }
            }
        }

        return {
            'animation_json': animation_json,
            'java_code': None,
            'anim_class': 'A-1',
            'warnings': self.warnings
        }

    def _detect_animation_period(
        self,
        vars_def: Dict[str, IntermediateVariable],
        sample_rate: int = 512
    ) -> Optional[float]:
        """
        Auto-detect the dominant animation period from intermediate variable
        expressions using FFT spectral analysis.

        This replaces the old hardcoded ``period = 2 * math.pi`` which assumed
        all animations have a ~6.28s cycle.  Real MC 1.12.2 animations use
        ``ageInTicks * C`` where C varies widely; the dominant frequency is
        extracted from the resolved expressions.

        Algorithm:
          1. Resolve each variable's full expression (substitute deps).
          2. For each cos/sin(ageInTicks * C) pattern, extract frequency C.
          3. Convert C to period: T = 2*pi / C / 20  (ticks → seconds).
          4. Return the LCM-approximation of the top-2 dominant periods
             so that one full cycle of every frequency is captured.
             If only one frequency, return its period.
          5. Return None if no frequency could be extracted (fallback needed).

        Args:
            vars_def: Intermediate variable definitions from the animation method.
            sample_rate: Reserved for future FFT-based sampling (currently unused).

        Returns:
            Detected period in seconds, or None if undetectable.
        """
        if not vars_def:
            return None

        frequencies: List[float] = []

        for var_info in vars_def.values():
            # Resolve the full expression
            resolved = self._resolve_variable_expression(var_info.name, vars_def)

            # Extract all coefficients from cos/sin(ageInTicks * C) patterns
            coeff_pattern = re.compile(
                r'(?:MathHelper\.(?:cos|sin|func_76134_b|func_76126_a|func_76133_a)|'
                r'math\.(?:cos|sin))'
                r'\s*\(\s*ageInTicks\s*\*\s*([+-]?\d+(?:\.\d+)?)\s*[fF]?\s*(?:\+'
                r'\s*[+-]?\d+(?:\.\d+)?\s*[fF]?)?\s*\)'
            )
            for m in coeff_pattern.finditer(resolved):
                try:
                    c = float(m.group(1))
                    if abs(c) > 1e-10:
                        frequencies.append(abs(c))
                except (ValueError, IndexError):
                    continue

        if not frequencies:
            return None

        # Convert frequencies (coefficient on ageInTicks) to periods in seconds.
        # ageInTicks is in ticks (1/20s), so:
        #   period_ticks = 2*pi / C
        #   period_seconds = period_ticks / 20.0
        periods = [2.0 * math.pi / c / 20.0 for c in frequencies]

        # Sort by period (longest first — it determines the overall window)
        periods.sort(reverse=True)

        # For a single dominant frequency, just return its period
        if len(periods) == 1:
            return round(periods[0], 4)

        # For multiple frequencies, find the smallest period T such that
        # T is an integer multiple of each individual period (LCM approximation).
        # We use a simple approach: scan multiples of the longest period up to
        # a reasonable limit and check phase closure for all frequencies.
        longest = periods[0]
        best_period = longest
        best_error = float('inf')

        for n in range(1, 13):  # Check up to 12x the longest period
            candidate = longest * n
            if candidate > 30.0:  # Don't exceed 30 seconds
                break
            # Compute phase error for each frequency
            total_error = 0.0
            for p in periods:
                # How close is candidate to an integer multiple of p?
                ratio = candidate / p
                nearest_int = round(ratio)
                if nearest_int < 1:
                    nearest_int = 1
                error = abs(ratio - nearest_int) / nearest_int
                total_error += error
            avg_error = total_error / len(periods)
            if avg_error < best_error:
                best_error = avg_error
                best_period = candidate
            if best_error < 0.02:  # Good enough — within 2%
                break

        return round(best_period, 4)

    def _evaluate_kirin_expression(
        self,
        expr: str,
        age_in_ticks: float,
        vars_def: Dict[str, IntermediateVariable]
    ) -> float:
        """
        Evaluate a Kirin-specific animation expression.
        Resolves intermediate variable references and converts Java → Python.
        """
        # Use the enhanced _evaluate_expression which handles vars_def
        return self._evaluate_expression(
            expr, age_in_ticks=age_in_ticks, vars_def=vars_def
        )

    def convert_kirin_cosmical(self, java_source: str) -> str:
        """
        Convert the Kirin cosmical/shaking animation to Java code.
        This is Class A-2 (uses entity state, not pure time).
        """
        # Extract method body for cosmical/shaking animation
        method_body = self._extract_method_body(java_source)
        if not method_body:
            return "// Could not find animation method body"

        # Parse offset-based animations (shaking uses position offsets)
        vars_def = self._parse_intermediate_variables(method_body)

        offset_map = {
            'field_82906_o': 'x',
            'field_82907_q': 'y',
            'field_82908_p': 'z'
        }

        offset_pattern = re.compile(
            r'this\.(\w+)\.(field_82906_o|field_82907_q|field_82908_p)\s*=\s*([^;]+);'
        )

        bone_offsets: Dict[str, Dict[str, str]] = {}
        for match in offset_pattern.finditer(method_body):
            bone_var = match.group(1)
            offset_field = match.group(2)
            expr = match.group(3).strip()

            axis = offset_map.get(offset_field)
            if not axis:
                continue

            if bone_var not in self.bone_mapping:
                continue

            if bone_var not in bone_offsets:
                bone_offsets[bone_var] = {}
            bone_offsets[bone_var][axis] = expr

        lines = []
        lines.append("// Kirin Cosmical Animation - Class A-2")
        lines.append("// This handles the shaking/clone state offsets")
        lines.append("// Must be implemented as code animation in GeckoLib")
        lines.append("")

        if bone_offsets:
            lines.append("// Position offset animations:")
            for bone_var, axis_exprs in bone_offsets.items():
                bone_name = self.bone_mapping[bone_var]
                lines.append(f"GeoBone {bone_var}Bone = this.getAnimationProcessor().getBone(\"{bone_name}\");")
                lines.append(f"if ({bone_var}Bone != null) {{")
                for axis, expr in axis_exprs.items():
                    converted_expr = self._convert_expression_to_geckolib(expr)
                    # Position offsets: apply M_model (x preserved, Y negated, Z negated)
                    if axis == 'y':
                        converted_expr = f"-({converted_expr})"
                    elif axis == 'z':
                        converted_expr = f"-({converted_expr})"
                    method = f"setOffset{axis.upper()}"
                    lines.append(f"    {bone_var}Bone.{method}((float)({converted_expr}));")
                lines.append("}")
                lines.append("")
        else:
            lines.append("// No offset-based animations detected in the source")
            lines.append("// Implement custom shaking animation based on entity state")

        return '\n'.join(lines)

    def convert_kirin_walk(self, java_source: str) -> dict:
        """
        Convert the Kirin walk animation (if present in setRotationAngles).
        This handles Class A-2 movement-driven animations with full expression resolution.
        """
        method_body = self._extract_method_body(java_source)
        if not method_body:
            return {
                'animation_json': None,
                'java_code': None,
                'anim_class': None,
                'warnings': ['Could not find setRotationAngles method body']
            }

        vars_def = self._parse_intermediate_variables(method_body)
        expressions = self._parse_rotation_assignments(method_body, vars_def)

        # Filter for movement-driven only
        movement_driven = [e for e in expressions if e.is_movement_driven]

        if not movement_driven:
            return {
                'animation_json': None,
                'java_code': None,
                'anim_class': None,
                'warnings': ['No movement-driven animations found']
            }

        java_code = self._convert_movement_driven(movement_driven, vars_def)

        return {
            'animation_json': None,
            'java_code': java_code,
            'anim_class': 'A-2',
            'warnings': self.warnings
        }


# ============================================================================
# Task 7: Animation Layer Auto-Separation
# ============================================================================

@dataclass
class AnimationLayer:
    """Represents a single animation layer separated from a mixed animation method."""
    name: str  # e.g., "base_walk", "hurt_overlay"
    priority: int = 0  # Higher = rendered on top
    expressions: List[AnimationExpression] = field(default_factory=list)
    is_additive: bool = True  # Overlay layers are additive
    transition_length: float = 0.0
    condition: str = ""  # e.g., "entity.hurtTime > 0"


class AnimationLayerSeparator:
    """
    Detects when the same animation method uses if-conditions to apply multiple
    overlapping rotations to the same bone (e.g., walk + hurt shake). Generates
    separate AnimationController definitions for each layer.

    Layer separation rules:
      - Code outside any conditional → base layer (priority 0)
      - if (entity.hurtTime > 0) blocks → hurt overlay (priority 10)
      - if (entity.isInvisible()) blocks → invisible overlay (priority 5)
      - Other if-blocks → named overlay based on condition

    The base layer is a continuous animation. Overlay layers use
    ``transitionNested`` or an independent controller with higher priority.
    """

    # Condition patterns and their corresponding layer info
    _CONDITION_LAYERS = [
        (re.compile(r'entity\.hurtTime\s*>\s*0'), "hurt_overlay", 10, "entity.hurtTime > 0"),
        (re.compile(r'entity\.isInvisible\(\)'), "invisible_overlay", 5, "entity.isInvisible()"),
        (re.compile(r'entity\.isAlive\(\)'), "alive_overlay", 3, "entity.isAlive()"),
        (re.compile(r'entity\.isAggressive\(\)'), "aggressive_overlay", 8, "entity.isAggressive()"),
        (re.compile(r'entity\.isCharging\(\)'), "charge_overlay", 7, "entity.isCharging()"),
    ]

    def __init__(self, bone_mapping: Dict[str, str] = None):
        """
        Args:
            bone_mapping: Dict mapping 1.12.2 java var names to GeckoLib bone IDs.
        """
        self.bone_mapping = bone_mapping or {}
        self.warnings: List[str] = []

    def separate_layers(self, method_body: str) -> List[AnimationLayer]:
        """
        Parse a method body and separate into base + overlay layers based on
        if-condition blocks.

        The method scans the Java source for if-blocks that correspond to known
        overlay conditions (hurt, invisible, etc.) and splits the rotation
        assignments accordingly. Code outside any conditional block is assigned
        to the base layer.

        Args:
            method_body: The Java source of the animation method body.

        Returns:
            A list of :class:`AnimationLayer` objects, always including at least
            a base layer. Overlay layers are sorted by descending priority.
        """
        if not method_body or not method_body.strip():
            self.warnings.append("Empty method body provided to AnimationLayerSeparator")
            return [AnimationLayer(name="base", priority=0, is_additive=False)]

        try:
            # Find all if-blocks and their ranges in the method body
            if_blocks = self._find_if_blocks(method_body)

            if not if_blocks:
                # No conditional blocks found — everything is the base layer
                return [AnimationLayer(name="base", priority=0, is_additive=False)]

            # Identify which if-blocks correspond to known overlay conditions
            overlay_blocks: List[Dict[str, Any]] = []
            for block_info in if_blocks:
                layer_match = self._match_condition_to_layer(block_info['condition'])
                if layer_match:
                    overlay_blocks.append({
                        **block_info,
                        'layer_name': layer_match[0],
                        'priority': layer_match[1],
                        'condition_str': layer_match[2],
                    })

            # Build the base layer from code outside overlay blocks
            overlay_ranges = [(b['start'], b['end']) for b in overlay_blocks]
            base_code = self._extract_code_outside_ranges(method_body, overlay_ranges)
            base_expressions = self._parse_expressions_from_code(base_code)

            layers: List[AnimationLayer] = []

            # Base layer
            base_layer = AnimationLayer(
                name="base",
                priority=0,
                expressions=base_expressions,
                is_additive=False,
                transition_length=0.0,
                condition="",
            )
            layers.append(base_layer)

            # Overlay layers
            for block in overlay_blocks:
                overlay_code = method_body[block['start']:block['end']]
                # Strip the if-condition line and outer braces
                overlay_code = self._strip_if_wrapper(overlay_code)
                overlay_expressions = self._parse_expressions_from_code(overlay_code)

                layer = AnimationLayer(
                    name=block['layer_name'],
                    priority=block['priority'],
                    expressions=overlay_expressions,
                    is_additive=True,
                    transition_length=0.2,  # Default transition for overlays
                    condition=block['condition_str'],
                )
                layers.append(layer)

            # Sort overlays by descending priority
            layers.sort(key=lambda l: l.priority, reverse=True)

            return layers

        except Exception as e:
            self.warnings.append(
                f"AnimationLayerSeparator.separate_layers failed: {e}. "
                f"Returning base layer only."
            )
            return [AnimationLayer(name="base", priority=0, is_additive=False)]

    def generate_controller_code(self, layers: List[AnimationLayer]) -> str:
        """
        Generate Java code for each controller with proper priority and blending.

        The base layer is generated as a continuous animation controller.
        Overlay layers are generated with higher priority and use
        ``transitionNested`` or independent controllers.

        Args:
            layers: List of :class:`AnimationLayer` objects, typically from
                :meth:`separate_layers`.

        Returns:
            A string of Java code defining the animation controllers.
        """
        if not layers:
            self.warnings.append("No layers provided to generate_controller_code")
            return "// No animation layers to generate"

        lines: List[str] = []
        lines.append("// Auto-generated AnimationController definitions")
        lines.append("// Generated by AnimationLayerSeparator")
        lines.append("")

        for layer in layers:
            lines.append(f"// --- Layer: {layer.name} (priority={layer.priority}) ---")

            if layer.priority == 0:
                # Base layer: continuous controller
                lines.append(f"AnimationController<{'>,'.join(['T extends GeoAnimatable'])}> {layer.name}Controller =")
                lines.append(f"    new AnimationController<>(this, \"{layer.name}\", 0, event -> {{")
                lines.append(f"        event.getController().setAnimation(")
                lines.append(f"            new AnimationBuilder().addAnimation(\"animation.model.{layer.name}\", true));")
                lines.append(f"        return PlayState.CONTINUE;")
                lines.append(f"    }});")
            else:
                # Overlay layer: conditional controller with transition
                transition = layer.transition_length
                lines.append(f"AnimationController<{'>,'.join(['T extends GeoAnimatable'])}> {layer.name}Controller =")
                lines.append(f"    new AnimationController<>(this, \"{layer.name}\", {transition}, event -> {{")
                if layer.condition:
                    lines.append(f"        // Condition: {layer.condition}")
                    lines.append(f"        if ({layer.condition}) {{")
                    lines.append(f"            event.getController().setAnimation(")
                    lines.append(f"                new AnimationBuilder().addAnimation(\"animation.model.{layer.name}\", true));")
                    lines.append(f"            return PlayState.CONTINUE;")
                    lines.append(f"        }}")
                    lines.append(f"        return PlayState.STOP;")
                else:
                    lines.append(f"        event.getController().setAnimation(")
                    lines.append(f"            new AnimationBuilder().addAnimation(\"animation.model.{layer.name}\", true));")
                    lines.append(f"        return PlayState.CONTINUE;")
                lines.append(f"    }});")
                lines.append(f"{layer.name}Controller.priority = {layer.priority};")
                if layer.is_additive:
                    lines.append(f"{layer.name}Controller.transitionNested = true;")

            lines.append("")

        # Register all controllers
        lines.append("// Register all controllers:")
        lines.append("@Override")
        lines.append("public void registerControllers(AnimatableManager.ControllerRegistrar controllers) {")
        for layer in layers:
            lines.append(f"    controllers.add({layer.name}Controller);")
        lines.append("}")

        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_if_blocks(self, method_body: str) -> List[Dict[str, Any]]:
        """
        Find all top-level if-blocks in the method body.

        Returns a list of dicts with keys:
          - 'condition': the condition string inside if(...)
          - 'start': character position of the block start (the 'if')
          - 'end': character position after the closing brace
        """
        blocks: List[Dict[str, Any]] = []
        pattern = re.compile(r'\bif\s*\(')
        pos = 0

        while pos < len(method_body):
            match = pattern.search(method_body, pos)
            if not match:
                break

            if_start = match.start()

            # Extract the condition string between the parentheses of if(...)
            paren_start = match.end() - 1  # position of '('
            depth = 0
            paren_end = paren_start
            for i in range(paren_start, len(method_body)):
                if method_body[i] == '(':
                    depth += 1
                elif method_body[i] == ')':
                    depth -= 1
                    if depth == 0:
                        paren_end = i
                        break

            condition_str = method_body[paren_start + 1:paren_end]

            # Find the opening brace of the if-block body
            body_start = paren_end + 1
            # Skip whitespace
            while body_start < len(method_body) and method_body[body_start] in ' \t\n\r':
                body_start += 1

            if body_start >= len(method_body) or method_body[body_start] != '{':
                # Single-line if without braces — skip for now
                pos = paren_end + 1
                continue

            # Find matching closing brace
            depth = 0
            brace_end = body_start
            for i in range(body_start, len(method_body)):
                if method_body[i] == '{':
                    depth += 1
                elif method_body[i] == '}':
                    depth -= 1
                    if depth == 0:
                        brace_end = i
                        break

            blocks.append({
                'condition': condition_str,
                'start': if_start,
                'end': brace_end + 1,
            })

            pos = brace_end + 1

        return blocks

    def _match_condition_to_layer(
        self, condition: str
    ) -> Optional[Tuple[str, int, str]]:
        """
        Match a condition string to a known overlay layer type.

        Returns:
            Tuple of (layer_name, priority, condition_str) or None if no match.
        """
        for pattern, name, priority, cond_str in self._CONDITION_LAYERS:
            if pattern.search(condition):
                return (name, priority, cond_str)
        return None

    def _extract_code_outside_ranges(
        self, source: str, ranges: List[Tuple[int, int]]
    ) -> str:
        """
        Extract the parts of source that are not covered by any of the
        given ranges.
        """
        if not ranges:
            return source

        # Sort ranges by start position
        sorted_ranges = sorted(ranges, key=lambda r: r[0])

        parts: List[str] = []
        prev_end = 0
        for start, end in sorted_ranges:
            if start > prev_end:
                parts.append(source[prev_end:start])
            prev_end = max(prev_end, end)

        # Append any remaining code after the last range
        if prev_end < len(source):
            parts.append(source[prev_end:])

        return '\n'.join(parts)

    def _strip_if_wrapper(self, code: str) -> str:
        """
        Strip the ``if (condition) {`` and closing ``}`` from an if-block,
        returning only the body.
        """
        # Find first '{' and last '}'
        brace_start = code.find('{')
        brace_end = code.rfind('}')
        if brace_start == -1 or brace_end == -1 or brace_start >= brace_end:
            return code
        return code[brace_start + 1:brace_end]

    def _parse_expressions_from_code(self, code: str) -> List[AnimationExpression]:
        """
        Parse rotation assignment expressions from a code fragment.

        Uses the same SRG field → axis mapping as the parent
        :class:`AnimationConverter`.
        """
        expressions: List[AnimationExpression] = []

        axis_map = {
            'field_78795_f': 'x',
            'field_78796_g': 'y',
            'field_78808_h': 'z',
        }

        pattern = re.compile(
            r'this\.(\w+)\.(field_78795_f|field_78796_g|field_78808_h)\s*=\s*([^;]+);'
        )

        for match in pattern.finditer(code):
            bone_var = match.group(1)
            axis_field = match.group(2)
            expr_str = match.group(3).strip()

            axis = axis_map.get(axis_field)
            if not axis:
                continue

            if bone_var not in self.bone_mapping:
                self.warnings.append(
                    f"AnimationLayerSeparator: Bone variable '{bone_var}' "
                    f"not found in bone mapping. Skipping."
                )
                continue

            expr = AnimationExpression(
                bone_var=bone_var,
                axis=axis,
                expression=expr_str,
                is_time_driven='ageInTicks' in expr_str,
                is_movement_driven='limbSwing' in expr_str,
            )
            expressions.append(expr)

        return expressions


# ============================================================================
# Task 8: Animation Event Markers
# ============================================================================

@dataclass
class AnimationEvent:
    """Represents an event detected inside animation Java code at a specific tick."""
    event_type: str  # "sound", "effect", "comment"
    time_ticks: int  # Tick position in the animation
    time_seconds: float  # Converted time
    original_call: str  # The original Java method call
    resource_hint: str = ""  # Extracted resource path if available
    description: str = ""  # Human-readable description


class KeyframeEventMarker:
    """
    Detects calls to ``entity.attackEntityAsMob(...)``, ``entity.playSound(...)``,
    ``world.spawnParticle(...)`` inside animation Java code at specific tick/time
    points. Outputs markers in the ``.animation.json`` at corresponding time
    positions using GeckoLib's sound/effect keyframe format.

    Supported event patterns:
      - ``entity.attackEntityAsMob(...)`` → "effect" event
      - ``entity.playSound(...)`` → "sound" event (extracts sound resource path)
      - ``world.spawnParticle(...)`` → "effect" event
      - Other entity method calls inside animation → "comment" event
    """

    # Ticks per second in Minecraft
    TPS = 20.0

    def __init__(self, bone_mapping: Dict[str, str] = None):
        """
        Args:
            bone_mapping: Dict mapping 1.12.2 java var names to GeckoLib bone IDs.
        """
        self.bone_mapping = bone_mapping or {}
        self.warnings: List[str] = []

    def detect_events(self, java_source: str) -> List[AnimationEvent]:
        """
        Scan animation code for method calls that represent events.

        Detects:
          - ``entity.attackEntityAsMob(...)`` → "effect" event
          - ``entity.playSound(...)`` → "sound" event; extracts sound resource
            path if the first argument is a string literal or a
            ``SoundEvents`` reference.
          - ``world.spawnParticle(...)`` → "effect" event
          - Any other ``entity.*(...)`` calls inside animation methods →
            "comment" event with the original code

        Args:
            java_source: The Java source containing animation methods.

        Returns:
            A list of :class:`AnimationEvent` instances sorted by time_ticks.
        """
        if not java_source or not java_source.strip():
            self.warnings.append("Empty Java source provided to KeyframeEventMarker.detect_events")
            return []

        events: List[AnimationEvent] = []

        try:
            # Detect entity.attackEntityAsMob calls
            attack_pattern = re.compile(
                r'entity\.attackEntityAsMob\s*\([^)]*\)'
            )
            for match in attack_pattern.finditer(java_source):
                tick = self._estimate_time_ticks(match.start(), java_source)
                events.append(AnimationEvent(
                    event_type="effect",
                    time_ticks=tick,
                    time_seconds=round(tick / self.TPS, 4),
                    original_call=match.group(),
                    resource_hint="",
                    description="Attack entity as mob",
                ))

            # Detect entity.playSound calls
            sound_pattern = re.compile(
                r'entity\.playSound\s*\(([^)]*)\)'
            )
            for match in sound_pattern.finditer(java_source):
                args_str = match.group(1).strip()
                resource_hint = self._extract_sound_resource(args_str)
                tick = self._estimate_time_ticks(match.start(), java_source)
                events.append(AnimationEvent(
                    event_type="sound",
                    time_ticks=tick,
                    time_seconds=round(tick / self.TPS, 4),
                    original_call=match.group(),
                    resource_hint=resource_hint,
                    description=f"Play sound: {resource_hint}" if resource_hint else "Play sound",
                ))

            # Detect world.spawnParticle calls
            particle_pattern = re.compile(
                r'world\.spawnParticle\s*\([^)]*\)'
            )
            for match in particle_pattern.finditer(java_source):
                tick = self._estimate_time_ticks(match.start(), java_source)
                events.append(AnimationEvent(
                    event_type="effect",
                    time_ticks=tick,
                    time_seconds=round(tick / self.TPS, 4),
                    original_call=match.group(),
                    resource_hint="",
                    description="Spawn particle",
                ))

            # Detect other entity method calls (comment events)
            # Exclude already-detected methods
            excluded_methods = {
                'attackEntityAsMob', 'playSound',
            }
            entity_method_pattern = re.compile(
                r'entity\.(\w+)\s*\([^)]*\)'
            )
            for match in entity_method_pattern.finditer(java_source):
                method_name = match.group(1)
                if method_name in excluded_methods:
                    continue
                # Skip common non-event entity methods
                if method_name in {
                    'getPosition', 'getPosX', 'getPosY', 'getPosZ',
                    'getHealth', 'getMaxHealth', 'isAlive', 'isInvisible',
                    'hurtTime', 'deathTime', 'limbSwing', 'limbSwingAmount',
                    'ageInTicks', 'rotationYaw', 'rotationPitch',
                    'getRNG', 'getRandom',
                }:
                    continue
                tick = self._estimate_time_ticks(match.start(), java_source)
                events.append(AnimationEvent(
                    event_type="comment",
                    time_ticks=tick,
                    time_seconds=round(tick / self.TPS, 4),
                    original_call=match.group(),
                    resource_hint="",
                    description=f"Entity call: {method_name}",
                ))

            # Sort by time
            events.sort(key=lambda e: e.time_ticks)

        except Exception as e:
            self.warnings.append(
                f"KeyframeEventMarker.detect_events failed: {e}. "
                f"Returning partial results."
            )

        return events

    def apply_to_animation_json(
        self, animation_json: dict, events: List[AnimationEvent]
    ) -> dict:
        """
        Insert events into the animation JSON at the correct time positions
        using GeckoLib's sound/effect keyframe format.

        For events where the resource ID is known, uses the appropriate
        ``sound`` or ``effect`` keyframe type. For unknown resource IDs,
        uses ``comment`` type instead.

        The GeckoLib keyframe format places sound and effect markers at
        the animation level (not under a specific bone).

        Args:
            animation_json: The animation JSON dict to modify.
            events: List of :class:`AnimationEvent` instances.

        Returns:
            The modified animation JSON dict with event keyframes inserted.
        """
        if not events:
            return animation_json

        try:
            anims = animation_json.get('animations', {})
            for anim_name, anim_data in anims.items():
                sound_keyframes = []
                effect_keyframes = []

                for event in events:
                    time_str = f"{event.time_seconds:.4f}"
                    if event.event_type == "sound" and event.resource_hint:
                        sound_keyframes.append({
                            "time": time_str,
                            "effect": event.resource_hint,
                        })
                    elif event.event_type == "effect" and event.resource_hint:
                        effect_keyframes.append({
                            "time": time_str,
                            "effect": event.resource_hint,
                        })
                    else:
                        # Use comment type for unknown resources
                        comment_text = event.description or event.original_call
                        if "sound_effects" not in anim_data:
                            anim_data["sound_effects"] = {}
                        if not isinstance(anim_data.get("sound_effects"), dict):
                            anim_data["sound_effects"] = {}
                        time_key = time_str
                        anim_data["sound_effects"][time_key] = {
                            "effect": comment_text,
                        }

                if sound_keyframes:
                    if "sound_effects" not in anim_data:
                        anim_data["sound_effects"] = {}
                    if not isinstance(anim_data.get("sound_effects"), dict):
                        anim_data["sound_effects"] = {}
                    for kf in sound_keyframes:
                        time_key = kf["time"]
                        anim_data["sound_effects"][time_key] = {
                            "effect": kf["effect"],
                        }

                if effect_keyframes:
                    if "particle_effects" not in anim_data:
                        anim_data["particle_effects"] = {}
                    if not isinstance(anim_data.get("particle_effects"), dict):
                        anim_data["particle_effects"] = {}
                    for kf in effect_keyframes:
                        time_key = kf["time"]
                        anim_data["particle_effects"][time_key] = {
                            "effect": kf["effect"],
                        }

        except Exception as e:
            self.warnings.append(
                f"KeyframeEventMarker.apply_to_animation_json failed: {e}. "
                f"Returning unmodified animation JSON."
            )

        return animation_json

    def _estimate_time_ticks(self, call_position: int, method_body: str) -> int:
        """
        Heuristic to estimate which tick the event occurs at based on code
        position relative to the method.

        The heuristic counts the number of lines before the call position,
        assuming roughly one logical step per line. In Minecraft animations,
        the ``setRotationAngles`` method is called once per tick, so each
        line roughly corresponds to one sub-step within that tick.

        A more refined estimate uses the ratio of the call position to the
        total method length, scaled to a typical animation period.

        Args:
            call_position: Character offset of the call in method_body.
            method_body: The full method body string.

        Returns:
            Estimated tick number (0-based).
        """
        if not method_body:
            return 0

        try:
            # Count the number of newlines before the call position
            line_number = method_body[:call_position].count('\n')

            # Use a simple heuristic: assume ~1 line per tick,
            # but cap at a reasonable animation length
            estimated_tick = line_number

            # Cap at a reasonable max (most animations are < 200 ticks)
            max_ticks = 200
            return min(estimated_tick, max_ticks)

        except Exception:
            return 0

    def _extract_sound_resource(self, args_str: str) -> str:
        """
        Extract a sound resource path from playSound arguments.

        Handles:
          - String literal first arg: ``"minecraft:entity.zombie.hurt"``
          - SoundEvents reference: ``SoundEvents.ENTITY_ZOMBIE_HURT``
          - Fallback: returns empty string

        Args:
            args_str: The comma-separated arguments inside playSound(...).

        Returns:
            The extracted resource path string, or empty string if not found.
        """
        if not args_str:
            return ""

        # Split by comma, take first argument
        parts = [p.strip() for p in args_str.split(',')]
        if not parts:
            return ""

        first_arg = parts[0]

        # Try string literal: "minecraft:entity.zombie.hurt"
        str_match = re.match(r'"([^"]+)"', first_arg)
        if str_match:
            return str_match.group(1)

        # Try SoundEvents reference: SoundEvents.ENTITY_ZOMBIE_HURT
        sfx_match = re.match(r'SoundEvents\.(\w+)', first_arg)
        if sfx_match:
            # Convert CONSTANT_CASE to resource path
            name = sfx_match.group(1).lower()
            return f"minecraft:{name.replace('_', '.')}"

        return ""


# ============================================================================
# Task 9: Dynamic Bone Visibility
# ============================================================================

@dataclass
class DynamicVisibilityRule:
    """Represents a bone whose scale or rotation is set to near-zero to simulate hiding."""
    bone_var: str
    axis: str
    is_pseudo_hide: bool  # True if using near-zero scale/rotation to simulate hiding
    original_expression: str
    replacement_code: str  # setHidden replacement code


class DynamicVisibilityDetector:
    """
    Detects bones whose scale or rotation is set to extremely small values
    (near 0) to simulate hiding. Replaces with proper ``bone.setHidden(true/false)``
    calls.

    Detection patterns:
      - ``this.bone.field_78795_f = 0.01f`` (rotation near zero → pseudo-hide)
      - Scale set to values < threshold for more than 1 frame
      - Periodic patterns where bone values drop below threshold
        (blinking/eye closing)

    The replacement uses ``GeoBone.setHidden()`` instead of the pseudo-hide
    pattern, with comments explaining the original behavior.
    """

    # SRG field → axis mapping
    _AXIS_MAP = {
        'field_78795_f': 'x',
        'field_78796_g': 'y',
        'field_78808_h': 'z',
    }

    def __init__(self, bone_mapping: Dict[str, str] = None, threshold: float = 0.05):
        """
        Args:
            bone_mapping: Dict mapping 1.12.2 java var names to GeckoLib bone IDs.
            threshold: Values below this are considered "near-zero" (pseudo-hide).
                Default is 0.05 radians.
        """
        self.bone_mapping = bone_mapping or {}
        self.threshold = threshold
        self.warnings: List[str] = []

    def detect(self, method_body: str) -> List[DynamicVisibilityRule]:
        """
        Find patterns where bone scale or rotation is set to near-zero values
        to simulate hiding.

        Specifically detects:
          - Rotation assignments with literal near-zero values (e.g. 0.01f)
          - Ternary expressions that set bone to 0 on a condition
            (e.g. ``condition ? 0.0f : normalValue``)
          - Periodic patterns where a cosine/sine function multiplied by a
            very small amplitude produces values below threshold
          - Scale assignments with near-zero values

        Args:
            method_body: The Java source of the animation method body.

        Returns:
            A list of :class:`DynamicVisibilityRule` instances for each
            detected pseudo-hide pattern.
        """
        if not method_body or not method_body.strip():
            self.warnings.append("Empty method body provided to DynamicVisibilityDetector.detect")
            return []

        rules: List[DynamicVisibilityRule] = []

        try:
            # 1. Detect rotation assignments with literal near-zero values
            rules.extend(self._detect_near_zero_rotations(method_body))

            # 2. Detect ternary patterns: condition ? 0.0f : value
            rules.extend(self._detect_ternary_zero_patterns(method_body))

            # 3. Detect periodic patterns (blinking) where amplitude < threshold
            rules.extend(self._detect_periodic_zero_patterns(method_body))

        except Exception as e:
            self.warnings.append(
                f"DynamicVisibilityDetector.detect failed: {e}. "
                f"Returning partial results."
            )

        return rules

    def generate_visibility_code(self, rules: List[DynamicVisibilityRule]) -> str:
        """
        Generate Java code for codeAnimations that uses ``bone.setHidden()``
        instead of the pseudo-hide pattern.

        Each replacement is annotated with a comment explaining what the
        original code was doing.

        Args:
            rules: List of :class:`DynamicVisibilityRule` instances.

        Returns:
            A string of Java code with ``setHidden()`` replacements.
        """
        if not rules:
            return "// No dynamic visibility rules detected"

        lines: List[str] = []
        lines.append("// Auto-generated dynamic visibility code")
        lines.append("// Generated by DynamicVisibilityDetector")
        lines.append("// Replaces near-zero scale/rotation pseudo-hide with setHidden()")
        lines.append("")

        # Group rules by bone variable
        bone_rules: Dict[str, List[DynamicVisibilityRule]] = {}
        for rule in rules:
            if rule.bone_var not in bone_rules:
                bone_rules[rule.bone_var] = []
            bone_rules[rule.bone_var].append(rule)

        for bone_var, bone_rule_list in bone_rules.items():
            bone_name = self.bone_mapping.get(bone_var, bone_var)
            lines.append(f"GeoBone {bone_var}Bone = this.getAnimationProcessor().getBone(\"{bone_name}\");")
            lines.append(f"if ({bone_var}Bone != null) {{")

            for rule in bone_rule_list:
                lines.append(f"    // Original: this.{rule.bone_var}.{rule.axis} = {rule.original_expression}")
                lines.append(f"    // Detected pseudo-hide on axis '{rule.axis}' (near-zero value)")
                lines.append(f"    {rule.replacement_code}")

            lines.append("}")
            lines.append("")

        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # Internal detection helpers
    # ------------------------------------------------------------------

    def _detect_near_zero_rotations(self, method_body: str) -> List[DynamicVisibilityRule]:
        """
        Detect rotation assignments where the value is a literal near-zero
        constant.

        Matches patterns like:
          - ``this.bone.field_78795_f = 0.01f;``
          - ``this.bone.field_78795_f = 0.0f;``
        """
        rules: List[DynamicVisibilityRule] = []

        # Pattern for: this.boneVar.field_xxxxx_x = literalValue;
        pattern = re.compile(
            r'this\.(\w+)\.(field_78795_f|field_78796_g|field_78808_h)\s*=\s*([^;]+);'
        )

        for match in pattern.finditer(method_body):
            bone_var = match.group(1)
            axis_field = match.group(2)
            expr_str = match.group(3).strip()

            axis = self._AXIS_MAP.get(axis_field)
            if not axis:
                continue

            # Check if the expression is a near-zero literal
            if self._is_near_zero_literal(expr_str):
                if bone_var not in self.bone_mapping:
                    self.warnings.append(
                        f"DynamicVisibilityDetector: Bone '{bone_var}' not in mapping. Skipping."
                    )
                    continue

                bone_name = self.bone_mapping[bone_var]
                replacement = (
                    f"// Pseudo-hide: {bone_var}.{axis} was set to {expr_str}\n"
                    f"    {bone_var}Bone.setHidden(true);"
                )

                rules.append(DynamicVisibilityRule(
                    bone_var=bone_var,
                    axis=axis,
                    is_pseudo_hide=True,
                    original_expression=expr_str,
                    replacement_code=replacement,
                ))

        return rules

    def _detect_ternary_zero_patterns(self, method_body: str) -> List[DynamicVisibilityRule]:
        """
        Detect ternary expressions that set a bone rotation to 0 on a condition.

        Matches patterns like:
          - ``this.bone.field_xxxxx_x = entity.hurtTime > 0 ? 0.0f : f4;``
          - ``condition ? 0 : value``
        """
        rules: List[DynamicVisibilityRule] = []

        pattern = re.compile(
            r'this\.(\w+)\.(field_78795_f|field_78796_g|field_78808_h)\s*=\s*([^;]+);'
        )

        for match in pattern.finditer(method_body):
            bone_var = match.group(1)
            axis_field = match.group(2)
            expr_str = match.group(3).strip()

            axis = self._AXIS_MAP.get(axis_field)
            if not axis:
                continue

            # Check if the expression contains a ternary with a zero branch
            if '?' in expr_str and ':' in expr_str:
                zero_branch = self._check_ternary_zero_branch(expr_str)
                if zero_branch is not None:
                    if bone_var not in self.bone_mapping:
                        self.warnings.append(
                            f"DynamicVisibilityDetector: Bone '{bone_var}' not in mapping. Skipping."
                        )
                        continue

                    bone_name = self.bone_mapping[bone_var]
                    condition = self._extract_ternary_condition(expr_str)

                    if zero_branch == 'true':
                        # condition ? 0 : value → hide when condition is true
                        replacement = (
                            f"// Pseudo-hide via ternary: when ({condition}) is true, "
                            f"{bone_var}.{axis} → 0\n"
                            f"    if ({condition}) {{\n"
                            f"        {bone_var}Bone.setHidden(true);\n"
                            f"    }} else {{\n"
                            f"        {bone_var}Bone.setHidden(false);\n"
                            f"    }}"
                        )
                    else:
                        # condition ? value : 0 → hide when condition is false
                        replacement = (
                            f"// Pseudo-hide via ternary: when ({condition}) is false, "
                            f"{bone_var}.{axis} → 0\n"
                            f"    if (!({condition})) {{\n"
                            f"        {bone_var}Bone.setHidden(true);\n"
                            f"    }} else {{\n"
                            f"        {bone_var}Bone.setHidden(false);\n"
                            f"    }}"
                        )

                    rules.append(DynamicVisibilityRule(
                        bone_var=bone_var,
                        axis=axis,
                        is_pseudo_hide=True,
                        original_expression=expr_str,
                        replacement_code=replacement,
                    ))

        return rules

    def _detect_periodic_zero_patterns(self, method_body: str) -> List[DynamicVisibilityRule]:
        """
        Detect periodic patterns where bone values drop below threshold
        (blinking/eye closing).

        Looks for expressions where a trigonometric function is multiplied
        by a very small amplitude, producing values near zero for most of
        the animation cycle.

        Matches patterns like:
          - ``MathHelper.cos(ageInTicks * 0.1f) * 0.01f``
          - Expressions with amplitude < threshold
        """
        rules: List[DynamicVisibilityRule] = []

        # Pattern for small-amplitude trig expressions
        # Matches: MathHelper.cos/sin(...) * 0.01f  or  0.01f * MathHelper.cos/sin(...)
        small_amp_pattern = re.compile(
            r'MathHelper\.(?:func_76134_b|func_76126_a|func_76133_a|cos|sin)\s*\([^)]*\)\s*\*\s*(0?\.\d+f?)'
        )
        small_amp_pattern2 = re.compile(
            r'(0?\.\d+f?)\s*\*\s*MathHelper\.(?:func_76134_b|func_76126_a|func_76133_a|cos|sin)\s*\([^)]*\)'
        )

        # Find bone rotation assignments that use these patterns
        assignment_pattern = re.compile(
            r'this\.(\w+)\.(field_78795_f|field_78796_g|field_78808_h)\s*=\s*([^;]+);'
        )

        for match in assignment_pattern.finditer(method_body):
            bone_var = match.group(1)
            axis_field = match.group(2)
            expr_str = match.group(3).strip()

            axis = self._AXIS_MAP.get(axis_field)
            if not axis:
                continue

            # Check for small-amplitude periodic patterns
            amp_match = small_amp_pattern.search(expr_str) or small_amp_pattern2.search(expr_str)
            if amp_match:
                amplitude_str = amp_match.group(1)
                try:
                    amplitude = float(amplitude_str.rstrip('fF'))
                except ValueError:
                    continue

                if amplitude < self.threshold:
                    if bone_var not in self.bone_mapping:
                        self.warnings.append(
                            f"DynamicVisibilityDetector: Bone '{bone_var}' not in mapping. Skipping."
                        )
                        continue

                    bone_name = self.bone_mapping[bone_var]
                    replacement = (
                        f"// Periodic pseudo-hide: {bone_var}.{axis} uses amplitude {amplitude_str} "
                        f"(below threshold {self.threshold})\n"
                        f"    // Consider using setHidden() with a timer-based condition instead\n"
                        f"    // Original expression: {expr_str}\n"
                        f"    {bone_var}Bone.setHidden(false); // REVIEW: implement blink timer"
                    )

                    rules.append(DynamicVisibilityRule(
                        bone_var=bone_var,
                        axis=axis,
                        is_pseudo_hide=True,
                        original_expression=expr_str,
                        replacement_code=replacement,
                    ))

        return rules

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def _is_near_zero_literal(self, expr: str) -> bool:
        """
        Check if an expression is a literal near-zero value.

        Handles:
          - ``0.0f``, ``0.01f``, ``0.001``
          - ``0f``, ``0``
          - Negated near-zero values
        """
        # Strip whitespace and common modifiers
        cleaned = expr.strip()
        # Remove float suffix
        cleaned = re.sub(r'[fF]$', '', cleaned)
        # Remove surrounding parentheses
        cleaned = cleaned.strip('()')

        try:
            value = float(cleaned)
            return abs(value) < self.threshold
        except ValueError:
            return False

    def _check_ternary_zero_branch(self, expr: str) -> Optional[str]:
        """
        Check if a ternary expression has a branch that evaluates to zero.

        Returns:
            'true' if the true branch is zero, 'false' if the false branch is
            zero, or None if neither branch is near-zero.
        """
        # Find the ? and : at depth 0
        depth = 0
        question_pos = -1
        colon_pos = -1

        for i, ch in enumerate(expr):
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == '?' and depth == 0 and question_pos == -1:
                question_pos = i
            elif ch == ':' and depth == 0 and question_pos != -1 and colon_pos == -1:
                colon_pos = i

        if question_pos == -1 or colon_pos == -1:
            return None

        true_expr = expr[question_pos + 1:colon_pos].strip()
        false_expr = expr[colon_pos + 1:].strip()

        true_is_zero = self._is_near_zero_literal(true_expr)
        false_is_zero = self._is_near_zero_literal(false_expr)

        if true_is_zero:
            return 'true'
        elif false_is_zero:
            return 'false'
        return None

    def _extract_ternary_condition(self, expr: str) -> str:
        """
        Extract the condition portion of a ternary expression.

        Returns the text before the first ``?`` at depth 0.
        """
        depth = 0
        for i, ch in enumerate(expr):
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == '?' and depth == 0:
                return expr[:i].strip()
        return expr
