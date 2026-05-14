#!/usr/bin/env python3
"""
SwingAnalyzer - Swing Physics, Gravity/Inertia, and Hurt Shake Analysis
=========================================================================
Analyzes animation patterns for physical simulation detection and migration.

Features:
  10. Tail/ear swing physics encapsulation (sin-based oscillation detection)
  11. Gravity/inertia simulation preservation (state-dependent drag/sag)
  12. Collision/hurt shake extraction (hurtTime conditional rotations)

All detection is best-effort. Failures produce warnings, never exceptions.
Preserves original mathematics exactly — only refactors for readability.
"""

import re
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class SwingComponent:
    """A detected sinusoidal swing component."""
    bone_var: str
    axis: str  # 'x', 'y', 'z'
    amplitude: float = 0.0
    frequency: float = 0.0
    phase_offset: float = 0.0
    weight: float = 0.0  # Additional weight/offset term
    invert: int = 1  # -1 or 1
    expression: str = ""  # Original expression
    is_chain: bool = False  # Part of a bone chain
    parent_bone: Optional[str] = None  # Parent in chain


@dataclass
class GravityInertiaInfo:
    """Detected gravity/inertia simulation pattern."""
    bone_var: str
    axis: str
    state_variable: str  # Instance variable name storing previous frame state
    expression: str  # Full expression
    is_recursive: bool = False  # Depends on previous frame value
    detected: bool = False


@dataclass
class HurtShakeInfo:
    """Detected hurt/collision shake pattern."""
    bone_var: str
    axis: str
    condition: str  # e.g., "entity.hurtTime > 0"
    rotation_expression: str  # Additional rotation during hurt
    amplitude: float = 0.0
    frequency: float = 0.0
    priority: int = 10  # Higher than base animations
    transition_length: float = 0.0  # Blend time


@dataclass
class SwingAnalysisResult:
    """Complete result from swing/physics analysis."""
    swing_components: List[SwingComponent] = field(default_factory=list)
    gravity_inertia: List[GravityInertiaInfo] = field(default_factory=list)
    hurt_shakes: List[HurtShakeInfo] = field(default_factory=list)
    swing_utility_code: str = ""  # Generated SwingComponent utility class
    hurt_controller_code: str = ""  # Generated hurt controller code
    warnings: List[str] = field(default_factory=list)


# ============================================================================
# SwingAnalyzer
# ============================================================================

class SwingAnalyzer:
    """
    Analyzes animation patterns for physics-based movement detection.

    Detects:
      1. Sinusoidal swing patterns (swingX/Y/Z from ModelSRP)
      2. Gravity/inertia patterns (instance variable state tracking)
      3. Hurt/collision shake patterns (hurtTime conditional rotations)

    Generates:
      - SwingComponent utility class for clean swing encapsulation
      - Independent hurt AnimationController
      - Preserved gravity/inertia code with documentation
    """

    def __init__(self, bone_mapping: Dict[str, str] = None):
        """
        Args:
            bone_mapping: Dict mapping 1.12.2 java var names to GeckoLib bone IDs
        """
        self.bone_mapping = bone_mapping or {}
        self._warnings: List[str] = []

    def analyze(self, java_source: str) -> SwingAnalysisResult:
        """
        Analyze Java source for swing/physics patterns.

        Args:
            java_source: The model Java source code (ModelKirin.java)

        Returns:
            SwingAnalysisResult with all detected patterns and generated code
        """
        result = SwingAnalysisResult()

        # Extract method body (setRotationAngles)
        method_body = self._extract_animation_method(java_source)

        # 10. Detect swing components
        result.swing_components = self._detect_swing_patterns(java_source, method_body)

        # 11. Detect gravity/inertia
        result.gravity_inertia = self._detect_gravity_inertia(java_source, method_body)

        # 12. Detect hurt shake
        result.hurt_shakes = self._detect_hurt_shake(java_source, method_body)

        # Build bone chains from swing components
        self._build_bone_chains(result.swing_components)

        # Generate code
        result.swing_utility_code = self._generate_swing_utility(result.swing_components)
        result.hurt_controller_code = self._generate_hurt_controller(result.hurt_shakes)

        result.warnings = self._warnings
        return result

    # ========================================================================
    # 10. Swing Pattern Detection
    # ========================================================================

    def _detect_swing_patterns(
        self,
        java_source: str,
        method_body: Optional[str]
    ) -> List[SwingComponent]:
        """
        Detect sinusoidal swing patterns in animation code.

        Patterns from ModelSRP:
          - swingX(bone, speed, degree, invert, limbSwing, limbSwingAmount)
          - swingY(bone, speed, degree, invert, offset, weight, limbSwing, limbSwingAmount)
          - swingZ(bone, speed, degree, invert, limbSwing, limbSwingAmount)
          - moveY(bone, speed, invert, f, f1, distance)

        Generic patterns:
          - bone.rotateAngleX = MathHelper.sin(ageInTicks * freq) * amplitude
          - bone.rotateAngleX = pref + Math.cos(limbSwing * speed) * limbSwingAmount * degree

        Returns:
            List of SwingComponent instances
        """
        components = []
        source = method_body or java_source

        # Pattern 1: swingX/Y/Z calls from ModelSRP
        swing_call_pattern = re.compile(
            r'this\.swing([XYZ])\s*\(\s*'
            r'this\.(\w+)\s*,\s*'        # bone
            r'([\d.fF\-]+)\s*,\s*'        # speed
            r'([\d.fF\-]+)\s*,\s*'        # degree
            r'([\-\d]+)\s*'               # invert
            r'(?:\s*,\s*([\d.fF\-]+)\s*)?'  # optional offset
            r'(?:\s*,\s*([\d.fF\-]+)\s*)?'  # optional weight
            r'(?:\s*,\s*[\w.]+\s*)'       # limbSwing
            r'(?:\s*,\s*[\w.]+\s*)'       # limbSwingAmount
            r'\s*\)'
        )

        for match in swing_call_pattern.finditer(source):
            axis = match.group(1).lower()
            bone_var = match.group(2)
            try:
                speed = float(match.group(3).rstrip('fF'))
                degree = float(match.group(4).rstrip('fF'))
                invert = int(match.group(5))
            except ValueError:
                continue

            offset = 0.0
            weight = 0.0
            if match.group(6):
                try:
                    offset = float(match.group(6).rstrip('fF'))
                except ValueError:
                    pass
            if match.group(7):
                try:
                    weight = float(match.group(7).rstrip('fF'))
                except ValueError:
                    pass

            components.append(SwingComponent(
                bone_var=bone_var,
                axis=axis,
                amplitude=degree,
                frequency=speed,
                phase_offset=offset,
                weight=weight,
                invert=invert,
                expression=match.group(0)
            ))

        # Pattern 2: swingX/Y/Z with prefix (pref, bone, speed, degree, invert, ...)
        swing_pref_pattern = re.compile(
            r'this\.swing([XYZ])\s*\(\s*'
            r'([\d.fF\-]+)\s*,\s*'        # pref value
            r'this\.(\w+)\s*,\s*'          # bone
            r'([\d.fF\-]+)\s*,\s*'         # speed
            r'([\d.fF\-]+)\s*,\s*'         # degree
            r'([\-\d]+)\s*'                # invert
            r'(?:\s*,\s*[\w.]+\s*)'        # limbSwing
            r'(?:\s*,\s*[\w.]+\s*)'        # limbSwingAmount
            r'\s*\)'
        )

        for match in swing_pref_pattern.finditer(source):
            axis = match.group(1).lower()
            try:
                pref = float(match.group(2).rstrip('fF'))
            except ValueError:
                pref = 0.0
            bone_var = match.group(3)
            try:
                speed = float(match.group(4).rstrip('fF'))
                degree = float(match.group(5).rstrip('fF'))
                invert = int(match.group(6))
            except ValueError:
                continue

            components.append(SwingComponent(
                bone_var=bone_var,
                axis=axis,
                amplitude=degree,
                frequency=speed,
                phase_offset=0.0,
                weight=pref,
                invert=invert,
                expression=match.group(0)
            ))

        # Pattern 3: Direct sin/cos assignments (ageInTicks or limbSwing based)
        direct_swing_pattern = re.compile(
            r'this\.(\w+)\.(?:field_78795_f|field_78796_g|field_78808_h|rotateAngle[XYZ])\s*=\s*'
            r'(-?)'                        # optional negation sign
            r'(?:[\d.fF\-]+\s*\+\s*)?'    # optional prefix
            r'(?:\(float\)\s*)?'
            r'MathHelper\.(?:func_76126_a|func_76134_b|sin|cos)\s*\(\s*'
            r'([\w.]+)\s*\*\s*([\d.fF\-]+)\s*'  # variable * frequency
            r'(?:\+\s*([\d.fF\-]+)\s*)?'  # optional phase offset
            r'\)\s*\*\s*([\d.fF\-]+)'     # amplitude
        )

        for match in direct_swing_pattern.finditer(source):
            bone_var = match.group(1)
            negation = match.group(2)  # '-' if negated, '' otherwise
            variable = match.group(3)
            try:
                frequency = float(match.group(4).rstrip('fF'))
                phase = float(match.group(5).rstrip('fF')) if match.group(5) else 0.0
                amplitude = float(match.group(6).rstrip('fF'))
            except ValueError:
                continue

            # Determine axis from the field assignment
            axis_match = re.search(
                r'\.(field_78795_f|field_78796_g|field_78808_h|rotateAngle([XYZ]))',
                source[match.start():match.start() + 200]
            )
            axis = 'x'
            if axis_match:
                if axis_match.group(2):
                    axis = axis_match.group(2).lower()
                elif axis_match.group(1) == 'field_78795_f':
                    axis = 'x'
                elif axis_match.group(1) == 'field_78796_g':
                    axis = 'y'
                elif axis_match.group(1) == 'field_78808_h':
                    axis = 'z'

            # Negation sign flips the invert value
            invert_val = -1 if negation == '-' else 1

            components.append(SwingComponent(
                bone_var=bone_var,
                axis=axis,
                amplitude=amplitude,
                frequency=frequency,
                phase_offset=phase,
                weight=0.0,
                invert=invert_val,
                expression=match.group(0),
                is_chain=False
            ))

        return components

    def _build_bone_chains(self, components: List[SwingComponent]) -> None:
        """
        Identify bone chains from swing components.

        A bone chain is a sequence of bones where each bone's swing
        depends on or adds to the previous bone's swing.
        E.g., tail1 → tail2 → tail3 where each adds incremental rotation.

        Detection heuristic:
          - Bones with similar frequency and axis
          - Names following a pattern (tail1, tail2, tail3)
          - Bone names with sequential suffixes
        """
        # Group by axis and frequency similarity
        groups: Dict[str, List[SwingComponent]] = {}
        for comp in components:
            key = f"{comp.axis}_{comp.frequency:.3f}"
            if key not in groups:
                groups[key] = []
            groups[key].append(comp)

        # Within each group, check for chain patterns
        for key, group in groups.items():
            if len(group) < 2:
                continue

            # Check for sequential naming patterns
            for i in range(len(group) - 1):
                bone1 = group[i].bone_var
                bone2 = group[i + 1].bone_var

                # Pattern: same prefix with number suffix
                prefix1 = re.match(r'(\D+)(\d+)', bone1)
                prefix2 = re.match(r'(\D+)(\d+)', bone2)

                if prefix1 and prefix2:
                    if prefix1.group(1) == prefix2.group(1):
                        try:
                            num1 = int(prefix1.group(2))
                            num2 = int(prefix2.group(2))
                            if num2 == num1 + 1:
                                group[i + 1].is_chain = True
                                group[i + 1].parent_bone = bone1
                        except ValueError:
                            pass

    # ========================================================================
    # 11. Gravity/Inertia Detection
    # ========================================================================

    def _detect_gravity_inertia(
        self,
        java_source: str,
        method_body: Optional[str]
    ) -> List[GravityInertiaInfo]:
        """
        Detect gravity/inertia simulation patterns.

        Patterns:
          - Instance variables storing previous frame angle:
            this.prevAngle = this.bone.rotateAngleX;
            this.bone.rotateAngleX = this.prevAngle + damping * (target - this.prevAngle);
          - Recursive/drag calculations:
            this.bone.rotateAngleX += (target - this.bone.rotateAngleX) * damping;

        These CANNOT be converted to JSON keyframes and must remain as
        Java code in codeAnimations.

        Returns:
            List of GravityInertiaInfo entries
        """
        infos = []
        source = method_body or java_source

        # Pattern: Previous angle storage
        prev_store_pattern = re.compile(
            r'this\.(\w+)\s*=\s*this\.(\w+)\.(?:field_78795_f|field_78796_g|field_78808_h|rotateAngle[XYZ])\s*;'
        )
        stored_vars = {}
        for match in prev_store_pattern.finditer(source):
            store_var = match.group(1)
            bone_var = match.group(2)
            stored_vars[store_var] = bone_var

        # Pattern: Drag/damping calculation using stored variable
        if stored_vars:
            drag_pattern = re.compile(
                r'this\.(\w+)\.(?:field_78795_f|field_78796_g|field_78808_h)\s*=\s*([^;]+);'
            )
            for match in drag_pattern.finditer(source):
                bone_var = match.group(1)
                expression = match.group(2).strip()

                # Check if expression references a stored variable
                for store_var, store_bone in stored_vars.items():
                    if store_var in expression and store_bone == bone_var:
                        axis = 'x'  # Default
                        if 'field_78796_g' in source[match.start():match.start() + 100]:
                            axis = 'y'
                        elif 'field_78808_h' in source[match.start():match.start() + 100]:
                            axis = 'z'

                        infos.append(GravityInertiaInfo(
                            bone_var=bone_var,
                            axis=axis,
                            state_variable=store_var,
                            expression=expression,
                            is_recursive=True,
                            detected=True
                        ))

        # Pattern: Direct damping (angle += (target - angle) * factor)
        direct_damp_pattern = re.compile(
            r'this\.(\w+)\.(?:field_78795_f|field_78796_g|field_78808_h)\s*\+=\s*\([^)]+\)\s*\*\s*[\d.fF]+'
        )
        for match in direct_damp_pattern.finditer(source):
            bone_var = match.group(1)
            # Check if already detected
            if any(info.bone_var == bone_var for info in infos):
                continue

            axis = 'x'
            if 'field_78796_g' in source[match.start():match.start() + 100]:
                axis = 'y'
            elif 'field_78808_h' in source[match.start():match.start() + 100]:
                axis = 'z'

            infos.append(GravityInertiaInfo(
                bone_var=bone_var,
                axis=axis,
                state_variable="implicit_prev_frame",
                expression=match.group(0),
                is_recursive=True,
                detected=True
            ))

        return infos

    # ========================================================================
    # 12. Hurt Shake Detection
    # ========================================================================

    def _detect_hurt_shake(
        self,
        java_source: str,
        method_body: Optional[str]
    ) -> List[HurtShakeInfo]:
        """
        Detect hurt/collision shake patterns.

        Patterns:
          - if (entity.hurtTime > 0) { bone.rotateAngleX += value; }
          - Conditional rotation applied during hurt state
          - Often combined with random offset for shake effect

        These should be extracted into a separate hurt AnimationController
        with higher priority that blends on top of base animations.

        Returns:
            List of HurtShakeInfo entries
        """
        shakes = []
        source = method_body or java_source

        # Pattern: hurtTime conditional rotation
        hurt_pattern = re.compile(
            r'if\s*\(\s*entity\.hurtTime\s*>\s*0\s*\)\s*\{([^}]+)\}',
            re.DOTALL
        )

        for match in hurt_pattern.finditer(source):
            body = match.group(1)

            # Find rotation assignments inside the hurt block
            rot_pattern = re.compile(
                r'this\.(\w+)\.(field_78795_f|field_78796_g|field_78808_h)\s*'
                r'(\+?=)\s*([^;]+);'
            )

            for rot_match in rot_pattern.finditer(body):
                bone_var = rot_match.group(1)
                field = rot_match.group(2)
                is_additive = rot_match.group(3) == '+='
                expression = rot_match.group(4).strip()

                axis_map = {
                    'field_78795_f': 'x',
                    'field_78796_g': 'y',
                    'field_78808_h': 'z'
                }
                axis = axis_map.get(field, 'x')
                bone_name = self.bone_mapping.get(bone_var, bone_var)

                # Try to extract amplitude from the expression
                amplitude = self._extract_amplitude(expression)

                shakes.append(HurtShakeInfo(
                    bone_var=bone_var,
                    axis=axis,
                    condition="entity.hurtTime > 0",
                    rotation_expression=expression,
                    amplitude=amplitude,
                    frequency=0.0,
                    priority=10,
                    transition_length=0.1  # Quick blend for hurt shake
                ))

        # Pattern: Random hurt shake (entity.rand or Math.random in hurt context)
        rand_hurt_pattern = re.compile(
            r'if\s*\(\s*entity\.hurtTime\s*>\s*0\s*\)[^{]*'
            r'this\.(\w+)\.(?:field_78795_f|field_78796_g|field_78808_h)\s*'
            r'(?:\+?=)\s*[^;]*rand[^;]*;'
        )
        for match in rand_hurt_pattern.finditer(source):
            bone_var = match.group(1)
            # Check if already detected
            if any(s.bone_var == bone_var for s in shakes):
                continue

            bone_name = self.bone_mapping.get(bone_var, bone_var)
            shakes.append(HurtShakeInfo(
                bone_var=bone_var,
                axis='x',
                condition="entity.hurtTime > 0",
                rotation_expression="random_hurt_shake",
                amplitude=0.1,
                frequency=0.0,
                priority=10,
                transition_length=0.1
            ))
            self._warnings.append(
                f"Detected random-based hurt shake for bone '{bone_name}'. "
                f"Random shake cannot be exactly reproduced in GeckoLib JSON. "
                f"Generating approximate shake animation."
            )

        return shakes

    @staticmethod
    def _extract_amplitude(expression: str) -> float:
        """Try to extract a numeric amplitude from an expression."""
        # Simple: look for numeric constants
        nums = re.findall(r'[\d.]+f?', expression)
        for num in nums:
            try:
                return abs(float(num.rstrip('fF')))
            except ValueError:
                continue
        return 0.1  # Default

    # ========================================================================
    # Code Generation
    # ========================================================================

    def _generate_swing_utility(self, components: List[SwingComponent]) -> str:
        """
        Generate the SwingComponent utility class Java code.

        Creates a reusable component class that encapsulates swing parameters,
        making the generated animation code cleaner and more readable.

        Returns:
            Java code string for SwingComponent class
        """
        lines = []
        lines.append("// Auto-generated by MinecraftModelMigrator-Pro")
        lines.append("// SwingComponent utility class for sinusoidal bone animations")
        lines.append("")
        lines.append("package com.example.srparasites.client.animation;")
        lines.append("")
        lines.append("/**")
        lines.append(" * Encapsulates a sinusoidal swing animation for a single bone axis.")
        lines.append(" * Replaces raw Math.cos(limbSwing * speed) * limbSwingAmount * degree")
        lines.append(" * with clean, readable, and adjustable parameters.")
        lines.append(" *")
        lines.append(" * Usage in codeAnimations:")
        lines.append(" *   SwingComponent tailSwing = new SwingComponent(0.6f, 1.0f, -1, 0.0f, 0.0f);")
        lines.append(" *   tailBone.setRotationX(tailSwing.compute(limbSwing, limbSwingAmount));")
        lines.append(" */")
        lines.append("public class SwingComponent {")
        lines.append("    private final float speed;")
        lines.append("    private final float degree;")
        lines.append("    private final int invert;")
        lines.append("    private final float phaseOffset;")
        lines.append("    private final float weight;")
        lines.append("")
        lines.append("    public SwingComponent(float speed, float degree, int invert,")
        lines.append("                          float phaseOffset, float weight) {")
        lines.append("        this.speed = speed;")
        lines.append("        this.degree = degree;")
        lines.append("        this.invert = invert;")
        lines.append("        this.phaseOffset = phaseOffset;")
        lines.append("        this.weight = weight;")
        lines.append("    }")
        lines.append("")
        lines.append("    /**")
        lines.append("     * Compute the swing rotation value.")
        lines.append("     * Equivalent to: (invert * limbSwingAmount * degree)")
        lines.append("     *                * Math.cos(limbSwing * speed + phaseOffset)")
        lines.append("     *                + (weight * limbSwingAmount)")
        lines.append("     */")
        lines.append("    public float compute(float limbSwing, float limbSwingAmount) {")
        lines.append("        if (phaseOffset != 0.0f || weight != 0.0f) {")
        lines.append("            return (float)((invert * limbSwingAmount * degree)")
        lines.append("                * Math.cos(limbSwing * speed + phaseOffset)")
        lines.append("                + (weight * limbSwingAmount));")
        lines.append("        }")
        lines.append("        return (float)((invert * degree)")
        lines.append("            * Math.cos(limbSwing * speed) * limbSwingAmount);")
        lines.append("    }")
        lines.append("")
        lines.append("    /**")
        lines.append("     * Compute with a prefix value (pref + swing).")
        lines.append("     */")
        lines.append("    public float computeWithPrefix(float pref, float limbSwing, float limbSwingAmount) {")
        lines.append("        return pref + compute(limbSwing, limbSwingAmount);")
        lines.append("    }")
        lines.append("}")

        return '\n'.join(lines)

    def _generate_hurt_controller(self, shakes: List[HurtShakeInfo]) -> str:
        """
        Generate a separate hurt AnimationController Java code.

        Creates an independent hurt controller with:
          - High priority (overrides base animations)
          - Short transition time for responsive hurt feedback
          - Proper blending with base walk/idle animations

        Returns:
            Java code string for hurt controller
        """
        if not shakes:
            return ""

        lines = []
        lines.append("// Auto-generated by MinecraftModelMigrator-Pro")
        lines.append("// Hurt Shake AnimationController")
        lines.append("// Extracted from original hurtTime > 0 conditional logic")
        lines.append("")
        lines.append("// Register this controller in your GeoModel's registerControllers():")
        lines.append("//   controllerRegistrar.add(new HurtShakeController());")
        lines.append("")
        lines.append("// === Hurt shake animation code for codeAnimations ===")
        lines.append("// Add the following to your codeAnimations method:")
        lines.append("")
        lines.append("// Check if entity is hurt")
        lines.append("float hurtTime = ((LivingEntity) animatable).hurtTime;")
        lines.append("")

        for shake in shakes:
            bone_name = self.bone_mapping.get(shake.bone_var, shake.bone_var)
            lines.append(f"// Hurt shake for bone: {bone_name} ({shake.axis}-axis)")
            lines.append(f"GeoBone {shake.bone_var}Bone = this.getAnimationProcessor().getBone(\"{bone_name}\");")
            lines.append(f"if ({shake.bone_var}Bone != null && hurtTime > 0) {{")

            # Generate hurt rotation code
            # Apply coordinate transformation for M_model = diag(1, -1, -1)
            expr = shake.rotation_expression
            negate = shake.axis in ('y', 'z')

            if shake.rotation_expression == "random_hurt_shake":
                lines.append(f"    // Random hurt shake (approximated)")
                lines.append(f"    float hurtShake{shake.axis.upper()} = (float)(Math.random() - 0.5) * 0.2f;")
                if negate:
                    lines.append(f"    {shake.bone_var}Bone.setRotation{shake.axis.upper()}" +
                                f"(-hurtShake{shake.axis.upper()});")
                else:
                    lines.append(f"    {shake.bone_var}Bone.setRotation{shake.axis.upper()}" +
                                f"(hurtShake{shake.axis.upper()});")
            else:
                # Replace SRG names
                converted = self._convert_expression(expr)
                if negate:
                    converted = f"-({converted})"
                lines.append(f"    {shake.bone_var}Bone.setRotation{shake.axis.upper()}((float)({converted}));")

            lines.append(f"}}")
            lines.append("")

        return '\n'.join(lines)

    @staticmethod
    def _convert_expression(expr: str) -> str:
        """Convert a Java expression to GeckoLib-compatible Java."""
        result = expr
        result = result.replace('MathHelper.func_76134_b', 'Math.cos')
        result = result.replace('MathHelper.func_76126_a', 'Math.sin')
        result = result.replace('MathHelper.func_76133_a', 'Math.sin')
        result = result.replace('MathHelper.cos', 'Math.cos')
        result = result.replace('MathHelper.sin', 'Math.sin')
        result = result.replace('(float)', '')
        return result

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _extract_animation_method(self, source: str) -> Optional[str]:
        """Extract the body of setRotationAngles or similar animation method."""
        for method_name in [r'func_78087_a', r'setRotationAngles', r'setLivingAnimations']:
            pattern = re.compile(
                rf'public\s+void\s+{method_name}\s*\([^)]+\)\s*\{{',
                re.DOTALL
            )
            match = pattern.search(source)
            if match:
                start_pos = match.end() - 1
                depth = 0
                for i in range(start_pos, len(source)):
                    if source[i] == '{':
                        depth += 1
                    elif source[i] == '}':
                        depth -= 1
                        if depth == 0:
                            return source[start_pos + 1:i]
        return None
