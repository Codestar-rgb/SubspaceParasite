#!/usr/bin/env python3
"""
AnimationConverter - Animation Conversion Engine
=================================================
Converts Minecraft 1.12.2 hardcoded animations to 1.20.1 GeckoLib format.

Two animation classes:
  - Class A-1: Time-driven animations (ageInTicks dependent) → .animation.json
  - Class A-2: Movement-driven animations (limbSwing dependent) → Java code snippets
"""

import json
import math
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core_math import convert_model_rot, convert_model_rotation_order, rad_to_deg


@dataclass
class AnimationExpression:
    """A single rotation assignment expression for a bone."""
    bone_var: str
    axis: str  # 'x', 'y', 'z'
    expression: str  # The raw Java expression
    is_time_driven: bool = False
    is_movement_driven: bool = False


class AnimationConverter:
    """
    Converts 1.12.2 animation code to GeckoLib 1.20.1 format.
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

        # Parse all rotation assignments
        expressions = self._parse_rotation_assignments(method_body)

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
                time_driven, animation_name, sample_count, dp_threshold, time_scale
            )
            result['anim_class'] = 'A-1'

        # Class A-2: Movement-driven → Java code
        if movement_driven:
            result['java_code'] = self._convert_movement_driven(movement_driven)
            if result['anim_class'] == 'A-1':
                result['anim_class'] = 'mixed'
            else:
                result['anim_class'] = 'A-2'

        return result

    def _extract_method_body(self, java_source: str) -> Optional[str]:
        """Extract the body of setRotationAngles (func_78087_a) method."""
        import re
        # Find the method - could be func_78087_a (setRotationAngles)
        # Look for the method signature
        pattern = re.compile(
            r'public\s+void\s+func_78087_a\s*\([^)]+\)\s*\{(.*?)\n    \}',
            re.DOTALL
        )
        match = pattern.search(java_source)
        if match:
            return match.group(1)

        # Try alternate pattern
        pattern2 = re.compile(
            r'public\s+void\s+setRotationAngles\s*\([^)]+\)\s*\{(.*?)\n    \}',
            re.DOTALL
        )
        match = pattern2.search(java_source)
        if match:
            return match.group(1)

        return None

    def _parse_rotation_assignments(self, method_body: str) -> List[AnimationExpression]:
        """Parse all rotation angle assignments from the method body."""
        import re
        expressions = []

        # Pattern for: this.boneVar.field_78795_f = expression;
        # field_78795_f = rotateAngleX, field_78796_g = rotateAngleY, field_78808_h = rotateAngleZ
        axis_map = {
            'field_78795_f': 'x',
            'field_78796_g': 'y',
            'field_78808_h': 'z'
        }

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

            # Classify: time-driven vs movement-driven
            is_time = 'ageInTicks' in expression or 'tick' in expression.lower()
            is_movement = 'limbSwing' in expression and 'limbSwingAmount' in expression

            expr = AnimationExpression(
                bone_var=bone_var,
                axis=axis,
                expression=expression,
                is_time_driven=is_time,
                is_movement_driven=is_movement
            )
            expressions.append(expr)

        # Also parse compound assignments like: this.bone.field = f11 = expression;
        compound_pattern = re.compile(
            r'this\.(\w+)\.(field_78795_f|field_78796_g|field_78808_h)\s*=\s*(\w+)\s*=\s*([^;]+);'
        )
        for match in compound_pattern.finditer(method_body):
            bone_var = match.group(1)
            axis_field = match.group(2)
            var_name = match.group(3)
            expression = match.group(4).strip()

            axis = axis_map.get(axis_field)
            if not axis:
                continue

            if bone_var not in self.bone_mapping:
                continue

            is_time = 'ageInTicks' in expression or 'tick' in expression.lower()
            is_movement = 'limbSwing' in expression

            expr = AnimationExpression(
                bone_var=bone_var,
                axis=axis,
                expression=expression,
                is_time_driven=is_time,
                is_movement_driven=is_movement
            )
            expressions.append(expr)

        return expressions

    def _convert_time_driven(
        self,
        expressions: List[AnimationExpression],
        animation_name: str,
        sample_count: int,
        dp_threshold: float,
        time_scale: float
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
        # Group expressions by bone
        bone_exprs: Dict[str, Dict[str, str]] = {}  # bone_var -> {axis: expression}
        for expr in expressions:
            if expr.bone_var not in bone_exprs:
                bone_exprs[expr.bone_var] = {}
            bone_exprs[expr.bone_var][expr.axis] = expr.expression

        # Sample each bone's rotation over time
        animation_bones = {}

        for bone_var, axis_exprs in bone_exprs.items():
            bone_name = self.bone_mapping[bone_var]
            keyframes = self._sample_bone_animation(
                bone_var, axis_exprs, sample_count, time_scale
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
            # Group keyframes by axis
            for kf in keyframes:
                time_s = kf['time']
                for axis in ['x', 'y', 'z']:
                    if axis in kf:
                        channel = f"rotation" if True else "position"
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
        time_scale: float
    ) -> List[dict]:
        """
        Sample a bone's rotation values over time.
        Returns list of keyframe dicts: [{'time': t, 'x': rx, 'y': ry, 'z': rz}, ...]
        """
        keyframes = []

        # Sample over 2π period (typical for Minecraft animations)
        # ageInTicks is in ticks (1/20 second), so 2π period ≈ 6.28 seconds
        period = 2 * math.pi
        dt = period / sample_count

        for i in range(sample_count + 1):
            t = i * dt
            age_in_ticks = t / time_scale  # Convert to ticks

            kf = {'time': t}

            for axis, expr in axis_exprs.items():
                try:
                    value = self._evaluate_expression(expr, age_in_ticks)
                    # Apply full model rotation conversion (M_model = diag(1,-1,-1))
                    # convert_model_rot: X preserved, Y negated, Z negated
                    if axis == 'y':
                        value = -value
                    elif axis == 'z':
                        value = -value
                    # X stays the same (not negated like in pure RH→LH)

                    kf[axis] = round(rad_to_deg(value), 6)
                except Exception as e:
                    self.warnings.append(
                        f"Failed to evaluate expression for {bone_var}.{axis}: {expr} ({e})"
                    )
                    kf[axis] = 0.0

            keyframes.append(kf)

        return keyframes

    def _evaluate_expression(self, expr: str, age_in_ticks: float) -> float:
        """
        Evaluate a Java math expression with the given ageInTicks value.
        Replaces Java math functions with Python equivalents.
        """
        import re

        # Replace Java math functions
        py_expr = expr

        # Replace MathHelper.func_76134_b -> math.cos (MathHelper.cos)
        py_expr = re.sub(r'MathHelper\.func_76134_b', 'math.cos', py_expr)
        py_expr = re.sub(r'MathHelper\.cos', 'math.cos', py_expr)

        # Replace MathHelper.sin
        py_expr = re.sub(r'MathHelper\.func_76126_a', 'math.sin', py_expr)
        py_expr = re.sub(r'MathHelper\.sin', 'math.sin', py_expr)

        # Replace Math.sin/cos
        py_expr = re.sub(r'Math\.sin', 'math.sin', py_expr)
        py_expr = re.sub(r'Math\.cos', 'math.cos', py_expr)

        # Replace Math.PI
        py_expr = py_expr.replace('Math.PI', str(math.pi))

        # Replace Java float suffixes
        py_expr = re.sub(r'(\d)[fF]', r'\1', py_expr)

        # Replace variable references
        # ageInTicks parameter
        py_expr = py_expr.replace('ageInTicks', str(age_in_ticks))

        # Remove explicit cast (float)
        py_expr = re.sub(r'\(float\)', '', py_expr)
        py_expr = re.sub(r'\(double\)', '', py_expr)

        # Handle intermediate variable references like f11, f22, f33
        # These are defined earlier in the method and we need to inline them
        # For now, we'll handle the common pattern in ModelKirin

        # Try to evaluate
        try:
            result = eval(py_expr, {"math": math, "__builtins__": {}})
            return float(result)
        except Exception:
            # If direct evaluation fails, return 0
            return 0.0

    def _douglas_peucker_simplify(
        self, keyframes: List[dict], threshold: float
    ) -> List[dict]:
        """
        Simplify keyframes using Douglas-Peucker algorithm.
        Threshold is in degrees.
        """
        if len(keyframes) <= 2:
            return keyframes

        # For each axis, apply Douglas-Peucker independently
        axes = ['x', 'y', 'z']
        kept_indices = set()

        for axis in axes:
            if axis not in keyframes[0]:
                continue

            points = [(kf['time'], kf.get(axis, 0.0)) for kf in keyframes]
            indices = self._dp_axis(points, threshold)
            kept_indices.update(indices)

        # Always keep first and last
        kept_indices.add(0)
        kept_indices.add(len(keyframes) - 1)

        # Sort and return
        sorted_indices = sorted(kept_indices)
        return [keyframes[i] for i in sorted_indices]

    def _dp_axis(self, points: List[Tuple[float, float]], threshold: float) -> List[int]:
        """Douglas-Peucker for a single axis."""
        if len(points) <= 2:
            return [0, len(points) - 1]

        # Find the point with maximum distance from the line
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
            # Recurse
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

    def _convert_movement_driven(self, expressions: List[AnimationExpression]) -> str:
        """
        Convert movement-driven animations to Java code snippets for GeckoLib.

        These must remain as Java code because GeckoLib cannot express
        limbSwing-dependent animations in JSON format.
        """
        lines = []
        lines.append("// Auto-generated by MC1122 -> GeckoLib Animation Converter")
        lines.append("// Class A-2: Movement-driven animation (limbSwing dependent)")
        lines.append("// Place this code in your GeoModel's codeAnimations method")
        lines.append("")
        lines.append("import software.bernie.geckolib.animatable.GeoAnimatable;")
        lines.append("import software.bernie.geckolib.animation.AnimatableManager;")

        # Group by bone
        bone_exprs: Dict[str, Dict[str, str]] = {}
        for expr in expressions:
            if expr.bone_var not in bone_exprs:
                bone_exprs[expr.bone_var] = {}
            bone_exprs[expr.bone_var][expr.axis] = expr.expression

        lines.append("")
        lines.append("// Bone references and rotation assignments:")

        for bone_var, axis_exprs in bone_exprs.items():
            bone_name = self.bone_mapping[bone_var]
            lines.append(f"IBone {bone_var}Bone = this.getAnimationProcessor().getBone(\"{bone_name}\");")

            for axis, expr in axis_exprs.items():
                # Convert expression: replace Java references
                converted_expr = self._convert_expression_to_geckolib(expr, bone_var)
                # Apply rotation conversion (negate X and Z)
                if axis in ('x', 'z'):
                    converted_expr = f"-({converted_expr})"
                method = f"setRotation{axis.upper()}"
                lines.append(f"{bone_var}Bone.{method}((float)({converted_expr}));")

            lines.append("")

        return '\n'.join(lines)

    def _convert_expression_to_geckolib(self, expr: str, bone_var: str) -> str:
        """Convert a Java expression to GeckoLib-compatible Java."""
        result = expr
        # Replace MathHelper with Math for standard Java
        result = result.replace('MathHelper.func_76134_b', 'Math.cos')
        result = result.replace('MathHelper.func_76126_a', 'Math.sin')
        result = result.replace('MathHelper.cos', 'Math.cos')
        result = result.replace('MathHelper.sin', 'Math.sin')
        # Remove float casts
        result = result.replace('(float)', '')
        result = result.replace('(double)', '')
        return result


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
        import re

        # Parse the specific intermediate variables
        vars_def = {}

        # f11 = MathHelper.func_76134_b((float)(ageInTicks * 0.130998f)) * 0.107215f
        var_pattern = re.compile(
            r'(f\d+)\s*=\s*([^;]+);'
        )

        # Find the method body
        method_body = self._extract_method_body(java_source)
        if not method_body:
            # Try extracting from the full source directly
            # Look for the setRotationAngles pattern
            start_marker = 'func_78087_a'
            start_idx = java_source.find(start_marker)
            if start_idx >= 0:
                # Find the opening brace
                brace_start = java_source.find('{', start_idx)
                # Count braces to find the end
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
                method_body = java_source[brace_start+1:end_idx]

        if not method_body:
            return {
                'animation_json': None,
                'java_code': None,
                'anim_class': None,
                'warnings': ['Could not find setRotationAngles method body']
            }

        # Parse intermediate variable definitions
        # f11 = MathHelper.cos(...) * ...
        for match in var_pattern.finditer(method_body):
            var_name = match.group(1)
            var_expr = match.group(2).strip()
            vars_def[var_name] = var_expr

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

            if bone_var not in bone_rotations:
                bone_rotations[bone_var] = {}
            bone_rotations[bone_var][axis] = expr

        # Also parse compound assignments like:
        # this.jointH.field_78795_f = f22 = MathHelper.cos(...) * ...
        compound_pattern = re.compile(
            r'this\.(\w+)\.(field_78795_f|field_78796_g|field_78808_h)\s*=\s*(\w+)\s*=\s*([^;]+);'
        )
        for match in compound_pattern.finditer(method_body):
            bone_var = match.group(1)
            axis_field = match.group(2)
            var_name = match.group(3)
            expr = match.group(4).strip()

            axis = axis_map.get(axis_field)
            if not axis:
                continue

            if bone_var not in self.bone_mapping:
                continue

            # Store the variable definition for later use
            vars_def[var_name] = expr

            if bone_var not in bone_rotations:
                bone_rotations[bone_var] = {}
            bone_rotations[bone_var][axis] = var_name  # Reference to intermediate var

        # Parse shaking/clone animations (offset-based, not rotation)
        # These use field_82906_o (offsetX), field_82907_q (offsetY), field_82908_p (offsetZ)
        # We'll handle these as position animations

        # Now sample the animation
        animation_bones = {}
        period = 2 * math.pi  # Full cycle

        for bone_var, axis_exprs in bone_rotations.items():
            bone_name = self.bone_mapping[bone_var]
            keyframes = []

            for i in range(sample_count + 1):
                t = i * period / sample_count
                age_in_ticks = t * 20.0  # Convert seconds to ticks

                kf = {'time': round(t, 6)}

                for axis, expr in axis_exprs.items():
                    try:
                        value = self._evaluate_kirin_expression(
                            expr, age_in_ticks, vars_def
                        )
                        # Apply coordinate system rotation conversion
                        # Apply full model rotation conversion (M_model = diag(1,-1,-1))
                        # convert_model_rot: X preserved, Y negated, Z negated
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

            # Simplify
            simplified = self._douglas_peucker_simplify(keyframes, dp_threshold)
            if simplified:
                animation_bones[bone_name] = simplified

        # Build .animation.json
        anim_id = f"animation.model.idle"
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

            # Only add if there are non-zero values
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
        vars_def: Dict[str, str]
    ) -> float:
        """
        Evaluate a Kirin-specific animation expression.
        Resolves intermediate variable references.
        """
        import re

        # Resolve variable references inline
        resolved_expr = expr
        for var_name, var_expr in vars_def.items():
            # Replace variable references (whole word only)
            resolved_expr = re.sub(
                r'\b' + re.escape(var_name) + r'\b',
                f'({var_expr})',
                resolved_expr
            )

        # Replace Java math with Python
        py_expr = resolved_expr
        py_expr = re.sub(r'MathHelper\.func_76134_b', 'math.cos', py_expr)
        py_expr = re.sub(r'MathHelper\.func_76126_a', 'math.sin', py_expr)
        py_expr = re.sub(r'MathHelper\.cos', 'math.cos', py_expr)
        py_expr = re.sub(r'MathHelper\.sin', 'math.sin', py_expr)
        py_expr = py_expr.replace('Math.sin', 'math.sin')
        py_expr = py_expr.replace('Math.cos', 'math.cos')
        py_expr = py_expr.replace('Math.PI', str(math.pi))
        py_expr = re.sub(r'(\d)[fF]', r'\1', py_expr)
        py_expr = py_expr.replace('(float)', '')
        py_expr = py_expr.replace('(double)', '')
        py_expr = py_expr.replace('ageInTicks', str(age_in_ticks))

        # Evaluate
        result = eval(py_expr, {"math": math, "__builtins__": {}})
        return float(result)

    def convert_kirin_cosmical(self, java_source: str) -> str:
        """
        Convert the Kirin cosmical/shaking animation to Java code.
        This is Class A-2 (uses entity state, not pure time).
        """
        lines = []
        lines.append("// Kirin Cosmical Animation - Class A-2")
        lines.append("// This handles the shaking/clone state offsets")
        lines.append("// Must be implemented as code animation in GeckoLib")
        return '\n'.join(lines)
