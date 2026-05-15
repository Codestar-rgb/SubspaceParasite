#!/usr/bin/env python3
"""
DynamicVisibilityDetector - Dynamic Bone Visibility Detection
==============================================================
Detects dynamic bone visibility patterns from MC 1.12.2 Java source
and generates corresponding GeckoLib bone.setHidden() code.

In MC 1.12.2, bone visibility is controlled by:
  - ModelRenderer.showModel = false (direct hide)
  - Conditional render() calls (only render if condition)
  - isChild() → baby scaling (pseudo-hide with scale)
  - isInvisible() → hide all parts
  - Custom entity state flags

In GeckoLib 1.20.1, these map to:
  - GeoBone.setHidden(true/false) for direct visibility
  - GeoBone.setScaleX/Y/Z(0.5f) for baby scaling
  - Conditional visibility in codeAnimations method

Detection is best-effort. Failures produce warnings, never exceptions.
Does NOT modify core_math.py or existing converter modules.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class VisibilityRule:
    """A detected visibility rule for a bone."""
    bone_var: str  # Java variable name
    bone_name: str  # GeckoLib bone ID
    condition: str  # Condition expression
    condition_type: str  # "invisible", "child", "hurt", "state", "custom"
    action: str = "hidden"  # "hidden", "scale", "visible"
    scale_value: Optional[float] = None
    inverted: bool = False  # True = show when condition, False = hide when condition
    source_expression: str = ""


@dataclass
class VisibilityDetectionResult:
    """Complete result from dynamic visibility detection."""
    visibility_rules: List[VisibilityRule] = field(default_factory=list)
    visibility_code: str = ""  # Generated Java code for codeAnimations
    hidden_bone_names: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ============================================================================
# DynamicVisibilityDetector
# ============================================================================

class DynamicVisibilityDetector:
    """
    Detects dynamic bone visibility patterns from Java source.

    Patterns detected:
      1. showModel = false → bone.setHidden(true)
      2. if (entity.isInvisible()) → conditional hide
      3. if (entity.isChild()) → baby scaling
      4. if (entity.hurtTime > 0) → hurt visibility
      5. Custom entity state flags → conditional visibility
      6. Pseudo-hide (scale to 0) → bone.setScaleX/Y/Z(0)

    All detection is best-effort with warnings on failure.
    """

    # SRG name mappings for showModel field
    SHOW_MODEL_SRG = {
        'field_78809_i': 'showModel',
        'field_78094_n': 'showModel',
    }

    def __init__(self, bone_mapping: Dict[str, str] = None):
        """
        Args:
            bone_mapping: Dict mapping 1.12.2 java var names to GeckoLib bone IDs
        """
        self.bone_mapping = bone_mapping or {}
        self._warnings: List[str] = []

    def detect(self, java_source: str, bone_mapping: Dict[str, str] = None) -> VisibilityDetectionResult:
        """
        Detect dynamic visibility patterns from Java source.

        Args:
            java_source: The Java source code (Model or Render class)
            bone_mapping: Optional bone mapping (overrides constructor mapping)

        Returns:
            VisibilityDetectionResult with all detected rules and generated code
        """
        if bone_mapping:
            self.bone_mapping = bone_mapping

        result = VisibilityDetectionResult()

        # 1. Detect showModel = false assignments
        self._detect_show_model_hides(java_source, result)

        # 2. Detect isInvisible conditions
        self._detect_invisible_conditions(java_source, result)

        # 3. Detect isChild conditions (baby scaling)
        self._detect_child_conditions(java_source, result)

        # 4. Detect hurtTime conditions
        self._detect_hurt_conditions(java_source, result)

        # 5. Detect custom state conditions
        self._detect_custom_state_conditions(java_source, result)

        # 6. Detect pseudo-hide (setRotationAngle + offset hiding)
        self._detect_pseudo_hide(java_source, result)

        # Generate visibility code
        result.visibility_code = self._generate_visibility_code(result.visibility_rules)

        # Build hidden bone names list
        result.hidden_bone_names = list(set(
            r.bone_name for r in result.visibility_rules
            if r.action == "hidden"
        ))

        result.warnings = self._warnings
        return result

    def _detect_show_model_hides(self, source: str, result: VisibilityDetectionResult) -> None:
        """Detect showModel = false assignments."""
        # Pattern: this.bone.showModel = false
        pattern = re.compile(
            r'this\.(\w+)\.(?:showModel|field_78809_i)\s*=\s*(true|false)\s*;'
        )
        for match in pattern.finditer(source):
            bone_var = match.group(1)
            show_value = match.group(2) == 'true'
            bone_name = self.bone_mapping.get(bone_var, bone_var)

            result.visibility_rules.append(VisibilityRule(
                bone_var=bone_var,
                bone_name=bone_name,
                condition="always",
                condition_type="custom",
                action="hidden" if not show_value else "visible",
                source_expression=match.group(0)
            ))

    def _detect_invisible_conditions(self, source: str, result: VisibilityDetectionResult) -> None:
        """Detect isInvisible() conditional visibility."""
        pattern = re.compile(
            r'if\s*\(\s*(!?)\s*(?:entity\.)?isInvisible\s*\(\s*\)\s*\)\s*\{([^}]+)\}',
            re.DOTALL
        )
        for match in pattern.finditer(source):
            negation = match.group(1) == '!'
            body = match.group(2)

            # Find bone references in the conditional block
            bone_refs = re.findall(
                r'this\.(\w+)\.(?:func_78785_a|field_78795_f|field_78796_g|showModel|field_78809_i)',
                body
            )
            for bone_var in bone_refs:
                bone_name = self.bone_mapping.get(bone_var, bone_var)
                result.visibility_rules.append(VisibilityRule(
                    bone_var=bone_var,
                    bone_name=bone_name,
                    condition="entity.isInvisible()",
                    condition_type="invisible",
                    action="hidden",
                    inverted=negation,
                    source_expression=match.group(0)
                ))

    def _detect_child_conditions(self, source: str, result: VisibilityDetectionResult) -> None:
        """Detect isChild() conditional scaling."""
        pattern = re.compile(
            r'if\s*\(\s*(?:entity\.)?isChild\s*\(\s*\)\s*\)\s*\{([^}]+)\}',
            re.DOTALL
        )
        for match in pattern.finditer(source):
            body = match.group(1)

            # Look for scale modifications
            scale_value = 0.5  # Default baby scale
            scale_match = re.search(r'(?:GlStateManager\.scale|GL11\.glScalef)\s*\(\s*([\d.fF\-]+)', body)
            if scale_match:
                try:
                    scale_value = float(scale_match.group(1).rstrip('fF'))
                except ValueError:
                    pass

            bone_refs = re.findall(r'this\.(\w+)\.(?:func_78785_a|field_78795_f)', body)
            for bone_var in bone_refs:
                bone_name = self.bone_mapping.get(bone_var, bone_var)
                result.visibility_rules.append(VisibilityRule(
                    bone_var=bone_var,
                    bone_name=bone_name,
                    condition="entity.isChild()",
                    condition_type="child",
                    action="scale",
                    scale_value=scale_value,
                    source_expression=match.group(0)
                ))

    def _detect_hurt_conditions(self, source: str, result: VisibilityDetectionResult) -> None:
        """Detect hurtTime conditional visibility."""
        pattern = re.compile(
            r'if\s*\(\s*(?:entity\.)?hurtTime\s*>\s*0\s*\)\s*\{([^}]+)\}',
            re.DOTALL
        )
        for match in pattern.finditer(source):
            body = match.group(1)

            # Check for color modification (red flash) rather than hide
            has_color_change = bool(re.search(r'GlStateManager\.color', body))

            bone_refs = re.findall(
                r'this\.(\w+)\.(?:field_78795_f|field_78796_g|field_78808_h|func_78785_a)',
                body
            )
            for bone_var in bone_refs:
                bone_name = self.bone_mapping.get(bone_var, bone_var)
                result.visibility_rules.append(VisibilityRule(
                    bone_var=bone_var,
                    bone_name=bone_name,
                    condition="entity.hurtTime > 0",
                    condition_type="hurt",
                    action="hidden",  # In GeckoLib, hurt shake is handled by controllers
                    source_expression=match.group(0)
                ))

    def _detect_custom_state_conditions(self, source: str, result: VisibilityDetectionResult) -> None:
        """Detect custom entity state conditional visibility."""
        # Pattern: if (entity.someFlag) { this.bone.render(); } or similar
        pattern = re.compile(
            r'if\s*\(\s*(\w+)\s*\)\s*\{\s*this\.(\w+)\.(?:func_78785_a|render)\s*\('
        )
        for match in pattern.finditer(source):
            condition_var = match.group(1)
            bone_var = match.group(2)

            # Skip already-handled conditions
            if condition_var in ('isInvisible', 'isChild', 'hurtTime'):
                continue

            bone_name = self.bone_mapping.get(bone_var, bone_var)
            result.visibility_rules.append(VisibilityRule(
                bone_var=bone_var,
                bone_name=bone_name,
                condition=f"entity.{condition_var}",
                condition_type="custom",
                action="hidden",
                inverted=False,
                source_expression=match.group(0)
            ))

    def _detect_pseudo_hide(self, source: str, result: VisibilityDetectionResult) -> None:
        """Detect pseudo-hide patterns (scale to 0 or extreme rotation)."""
        # Pattern: bone.showModel = false OR bone field not rendered
        # Also detect: extreme rotation to hide (rotateAngleX = PI/2 etc.)
        extreme_rot_pattern = re.compile(
            r'this\.(\w+)\.(?:field_78795_f|field_78796_g|field_78808_h)\s*=\s*'
            r'(?:\(float\)\s*)?(?:Math\.PI|3\.14159)'
        )
        for match in extreme_rot_pattern.finditer(source):
            bone_var = match.group(1)
            bone_name = self.bone_mapping.get(bone_var, bone_var)

            # Check if this bone already has a visibility rule
            existing = [r for r in result.visibility_rules if r.bone_var == bone_var]
            if existing:
                continue

            result.visibility_rules.append(VisibilityRule(
                bone_var=bone_var,
                bone_name=bone_name,
                condition="always",
                condition_type="custom",
                action="hidden",
                source_expression=match.group(0)
            ))

    def _generate_visibility_code(self, rules: List[VisibilityRule]) -> str:
        """
        Generate Java code for conditional visibility in codeAnimations.

        Returns:
            Java code string for bone visibility control
        """
        if not rules:
            return ""

        lines = []
        lines.append("// Auto-generated by MinecraftModelMigrator-Pro")
        lines.append("// Dynamic Bone Visibility - Generated from original render conditions")
        lines.append("// Place this code in your GeoModel's codeAnimations method")
        lines.append("")

        for rule in rules:
            if rule.condition_type == "invisible":
                if rule.inverted:
                    lines.append(f'// Show bone "{rule.bone_name}" when entity is NOT invisible')
                    lines.append(f'GeoBone {rule.bone_var}Bone = this.getAnimationProcessor().getBone("{rule.bone_name}");')
                    lines.append(f'if ({rule.bone_var}Bone != null) {{')
                    lines.append(f'    {rule.bone_var}Bone.setHidden(entity.isInvisible()); // inverted: hide when invisible')
                    lines.append(f'}}')
                else:
                    lines.append(f'// Hide bone "{rule.bone_name}" when entity is invisible')
                    lines.append(f'GeoBone {rule.bone_var}Bone = this.getAnimationProcessor().getBone("{rule.bone_name}");')
                    lines.append(f'if ({rule.bone_var}Bone != null) {{')
                    lines.append(f'    {rule.bone_var}Bone.setHidden(entity.isInvisible());')
                    lines.append(f'}}')

            elif rule.condition_type == "child":
                lines.append(f'// Baby scaling for bone "{rule.bone_name}"')
                lines.append(f'GeoBone {rule.bone_var}Bone = this.getAnimationProcessor().getBone("{rule.bone_name}");')
                lines.append(f'if ({rule.bone_var}Bone != null && entity.isChild()) {{')
                if rule.scale_value:
                    lines.append(f'    {rule.bone_var}Bone.setScaleX({rule.scale_value}f);')
                    lines.append(f'    {rule.bone_var}Bone.setScaleY({rule.scale_value}f);')
                    lines.append(f'    {rule.bone_var}Bone.setScaleZ({rule.scale_value}f);')
                else:
                    lines.append(f'    {rule.bone_var}Bone.setScaleX(0.5f);')
                    lines.append(f'    {rule.bone_var}Bone.setScaleY(0.5f);')
                    lines.append(f'    {rule.bone_var}Bone.setScaleZ(0.5f);')
                lines.append(f'}}')

            elif rule.condition_type == "hurt":
                lines.append(f'// Hurt effect for bone "{rule.bone_name}" - handled by hurt controller')
                lines.append(f'// See SwingAnalyzer hurt controller output')

            elif rule.condition_type == "custom":
                if rule.action == "visible":
                    lines.append(f'// Always show bone "{rule.bone_name}"')
                    lines.append(f'GeoBone {rule.bone_var}Bone = this.getAnimationProcessor().getBone("{rule.bone_name}");')
                    lines.append(f'if ({rule.bone_var}Bone != null) {{')
                    lines.append(f'    {rule.bone_var}Bone.setHidden(false);')
                    lines.append(f'}}')
                elif rule.action == "hidden":
                    lines.append(f'// Always hide bone "{rule.bone_name}" (showModel=false in original)')
                    lines.append(f'GeoBone {rule.bone_var}Bone = this.getAnimationProcessor().getBone("{rule.bone_name}");')
                    lines.append(f'if ({rule.bone_var}Bone != null) {{')
                    lines.append(f'    {rule.bone_var}Bone.setHidden(true);')
                    lines.append(f'}}')

            lines.append("")

        return '\n'.join(lines)
