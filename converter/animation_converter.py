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
        dp_threshold: float = 0.01,
        time_scale: float = 1.0
    ) -> dict:
        """
        Convert a setRotationAngles method to GeckoLib animation format.

        Args:
            java_source: The Java source containing the setRotationAngles method
            animation_name: Name for the animation (e.g., "idle", "walk")
            sample_count: Number of samples for time-driven animations
            dp_threshold: Douglas-Peucker simplification threshold (degrees)
            time_scale: Time scale factor (1.0 = normal)

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
                time_driven, animation_name, sample_count, dp_threshold, time_scale, vars_def
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

        # Pattern for: this.boneVar.field_78795_f = expression;
        pattern = re.compile(
            r'this\.(\w+)\.(field_78795_f|field_78796_g|field_78808_h)\s*=\s*([^;]+);'
        )

        for match in pattern.finditer(method_body):
            bone_var = match.group(1)
            axis_field = match.group(2)
            expression = match.group(3).strip()

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
                is_movement_driven=is_movement
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
    # Class A-1: Time-Driven Conversion (enhanced with vars_def)
    # ========================================================================

    def _convert_time_driven(
        self,
        expressions: List[AnimationExpression],
        animation_name: str,
        sample_count: int,
        dp_threshold: float,
        time_scale: float,
        vars_def: Dict[str, IntermediateVariable] = None
    ) -> dict:
        """
        Convert time-driven animations using numerical sampling.

        Process:
        1. Extract all intermediate variable definitions
        2. Replace Java math with Python equivalents
        3. Sample over time period
        4. Apply Douglas-Peucker simplification
        5. Generate .animation.json structure
        """
        if vars_def is None:
            vars_def = {}

        # Group expressions by bone
        bone_exprs: Dict[str, Dict[str, str]] = {}
        for expr in expressions:
            if expr.bone_var not in bone_exprs:
                bone_exprs[expr.bone_var] = {}
            bone_exprs[expr.bone_var][expr.axis] = expr.expression

        # Sample each bone's rotation over time
        animation_bones = {}

        for bone_var, axis_exprs in bone_exprs.items():
            bone_name = self.bone_mapping[bone_var]
            keyframes = self._sample_bone_animation(
                bone_var, axis_exprs, sample_count, time_scale, vars_def
            )

            if keyframes:
                # Simplify with Douglas-Peucker
                simplified = self._douglas_peucker_simplify(keyframes, dp_threshold)
                animation_bones[bone_name] = simplified

        # Build .animation.json structure
        anim_id = f"animation.model.{animation_name}"

        # Build bone animation data
        bones_data = {}
        for bone_name, keyframes in animation_bones.items():
            bone_anim = {}
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

        animation_json = {
            "format_version": "1.8.0",
            "animations": {
                anim_id: {
                    "loop": "hold_on_last_frame",
                    "animation_length": self._calculate_animation_length(animation_bones),
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
        vars_def: Dict[str, IntermediateVariable] = None
    ) -> List[dict]:
        """
        Sample a bone's rotation values over time.
        Returns list of keyframe dicts: [{'time': t, 'x': rx, 'y': ry, 'z': rz}, ...]
        """
        if vars_def is None:
            vars_def = {}

        keyframes = []

        # Sample over 2π period (typical for Minecraft animations)
        period = 2 * math.pi
        dt = period / sample_count

        for i in range(sample_count + 1):
            t = i * dt
            age_in_ticks = t / time_scale

            kf = {'time': t}

            for axis, expr in axis_exprs.items():
                try:
                    value = self._evaluate_expression(
                        expr, age_in_ticks,
                        limb_swing=0.0, limb_swing_amount=0.0,
                        vars_def=vars_def
                    )
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

        # Try to evaluate
        try:
            # Define math.radians and math.degrees for eval context
            def _radians(d): return d * math.pi / 180.0
            def _degrees(r): return r * 180.0 / math.pi
            eval_globals = {
                "math": math,
                "__builtins__": {
                    "max": max,
                    "min": min,
                    "abs": abs,
                },
            }
            result = eval(py_expr, eval_globals)
            return float(result)
        except Exception:
            # If direct evaluation fails, return 0
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

    def _douglas_peucker_simplify(
        self, keyframes: List[dict], threshold: float
    ) -> List[dict]:
        """Simplify keyframes using Douglas-Peucker algorithm."""
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
        return [keyframes[i] for i in sorted_indices]

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
            return left[:-1] + right
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
        period = 2 * math.pi

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
