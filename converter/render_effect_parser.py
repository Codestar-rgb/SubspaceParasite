#!/usr/bin/env python3
"""
RenderEffectParser - Rendering Effect Detection & Migration
=============================================================
Detects rendering effects from MC 1.12.2 Java source (Render class, Model class)
and generates corresponding GeckoLib 1.20.1 code.

Features:
  1. Emissive/Glow detection (disableLighting, blendFunc ONE)
  2. Translucency detection (enableBlend, SRC_ALPHA/ONE_MINUS_SRC_ALPHA)
  3. Render order extraction (ModelRenderer.render call sequence)
  4. Conditional visibility (isInvisible, isChild, hurtTime)
  5. Dynamic UV/texture offset migration (warning-only)

All detection failures default to original behavior with warnings.
Never interrupts the conversion pipeline.
"""

import re
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class EmissiveInfo:
    """Detected emissive/glow rendering effect."""
    is_global: bool = False
    emissive_bones: List[str] = field(default_factory=list)
    render_type: str = "eyes"  # "eyes" or "entity_translucent_emissive"
    detected: bool = False
    source_pattern: str = ""


@dataclass
class TranslucencyInfo:
    """Detected translucency rendering effect."""
    is_global: bool = False
    translucent_bones: List[str] = field(default_factory=list)
    blend_src: str = ""
    blend_dst: str = ""
    render_type: str = "entityTranslucent"
    detected: bool = False
    source_pattern: str = ""


@dataclass
class RenderOrderEntry:
    """A single entry in the render order."""
    bone_var: str
    order_index: int
    is_translucent_stage: bool = False


@dataclass
class ConditionalVisibility:
    """A conditional visibility rule for a bone."""
    bone_var: str
    condition: str  # Java condition expression
    condition_type: str  # "invisible", "child", "hurt", "custom"
    action: str = "hidden"  # "hidden" or "scale"
    scale_value: Optional[float] = None
    inverted: bool = False  # True = show when condition, False = hide when condition


@dataclass
class DynamicUVInfo:
    """Detected dynamic UV/texture offset modification."""
    bone_var: str
    is_per_frame: bool = False
    expression: str = ""
    detected: bool = False


@dataclass
class RenderEffectResult:
    """Complete result from render effect parsing."""
    emissive: EmissiveInfo = field(default_factory=EmissiveInfo)
    translucency: TranslucencyInfo = field(default_factory=TranslucencyInfo)
    render_order: List[RenderOrderEntry] = field(default_factory=list)
    conditional_visibility: List[ConditionalVisibility] = field(default_factory=list)
    dynamic_uv: List[DynamicUVInfo] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    render_type_code: str = ""  # Generated Java code for getRenderType
    visibility_code: str = ""  # Generated Java code for codeAnimations visibility
    render_order_code: str = ""  # Generated Java code for render ordering


# ============================================================================
# RenderEffectParser
# ============================================================================

class RenderEffectParser:
    """
    Parses rendering effects from MC 1.12.2 Java source and generates
    corresponding GeckoLib 1.20.1 code.

    Detects:
      - GlStateManager.disableLighting() → emissive rendering
      - GlStateManager.enableBlend() + blendFunc → translucency
      - ModelRenderer.render() call order → render order
      - if (entity.isInvisible/isChild/hurtTime) → conditional visibility
      - setTextureOffset per-frame modifications → dynamic UV warnings

    All detection is best-effort. Failures produce warnings, never exceptions.
    """

    # SRG name mappings for GlStateManager methods
    GLStateManager_SRG = {
        'func_179141_l': 'disableLighting',
        'func_179098_w': 'enableBlend',
        'func_179112_h': 'disableBlend',
        'func_179120_a': 'blendFunc',
        'func_188338_a': 'tryBlendFuncSeparate',
    }

    def __init__(self, bone_mapping: Dict[str, str] = None):
        """
        Args:
            bone_mapping: Dict mapping 1.12.2 java var names to GeckoLib bone IDs
        """
        self.bone_mapping = bone_mapping or {}
        self._warnings: List[str] = []

    def parse(self, render_java: str, model_java: str = "") -> RenderEffectResult:
        """
        Parse rendering effects from Java source(s).

        Args:
            render_java: The Render class Java source
            model_java: The Model class Java source (optional, for additional detection)

        Returns:
            RenderEffectResult with all detected effects and generated code
        """
        result = RenderEffectResult()
        combined_source = render_java + "\n" + model_java

        # 1. Detect emissive/glow
        result.emissive = self._detect_emissive(combined_source)

        # 2. Detect translucency
        result.translucency = self._detect_translucency(combined_source)

        # 3. Extract render order
        result.render_order = self._extract_render_order(combined_source)

        # 4. Detect conditional visibility
        result.conditional_visibility = self._detect_conditional_visibility(combined_source)

        # 5. Detect dynamic UV
        result.dynamic_uv = self._detect_dynamic_uv(combined_source)

        # Generate code
        result.render_type_code = self._generate_render_type_code(result)
        result.visibility_code = self._generate_visibility_code(result)
        result.render_order_code = self._generate_render_order_code(result)

        result.warnings = self._warnings
        return result

    # ========================================================================
    # 1. Emissive/Glow Detection
    # ========================================================================

    def _detect_emissive(self, source: str) -> EmissiveInfo:
        """
        Detect emissive/glow rendering from GlStateManager calls.

        Patterns:
          - GlStateManager.disableLighting() → global or bone-level emissive
          - tryBlendFuncSeparate(SourceFactor.ONE, ...) → additive blending
          - Custom render methods that disable lighting for specific parts

        Returns:
            EmissiveInfo with detection results
        """
        info = EmissiveInfo()

        # Pattern 1: Global disableLighting (before all render calls)
        disable_lighting_pattern = re.compile(
            r'GlStateManager\.func_179141_l\(\)|GlStateManager\.disableLighting\(\)'
        )
        lighting_matches = list(disable_lighting_pattern.finditer(source))

        # Pattern 2: Blend function with ONE (additive/emissive blending)
        blend_one_pattern = re.compile(
            r'GlStateManager\.func_188338_a\(\s*GlStateManager\.SourceFactor\.ONE\s*,'
            r'|GlStateManager\.tryBlendFuncSeparate\(\s*GlStateManager\.SourceFactor\.ONE\s*,'
        )
        blend_one_matches = list(blend_one_pattern.finditer(source))

        if lighting_matches or blend_one_matches:
            info.detected = True

            # Check if the lighting disable is inside a conditional block
            # that references a specific bone (bone-level emissive)
            # vs. global (applied to the whole model)
            for match in lighting_matches:
                # Look at surrounding context for bone references
                start = max(0, match.start() - 200)
                context = source[start:match.start()]

                # Check if this is near a specific bone render call
                bone_refs = re.findall(r'this\.(\w+)\.func_78785_a\s*\(', context)
                if bone_refs:
                    for bone_ref in bone_refs[-1:]:  # Last bone reference before
                        bone_name = self.bone_mapping.get(bone_ref, bone_ref)
                        if bone_name not in info.emissive_bones:
                            info.emissive_bones.append(bone_name)
                else:
                    # No specific bone reference → global emissive
                    info.is_global = True

            if blend_one_matches:
                info.render_type = "eyes"  # Common for mob eyes
                if not info.source_pattern:
                    info.source_pattern = "tryBlendFuncSeparate(SourceFactor.ONE, ...)"

            if lighting_matches and not info.emissive_bones:
                info.is_global = True
                info.source_pattern = "GlStateManager.disableLighting()"
            elif info.emissive_bones:
                info.source_pattern = f"disableLighting for bones: {info.emissive_bones}"

        return info

    # ========================================================================
    # 2. Translucency Detection
    # ========================================================================

    def _detect_translucency(self, source: str) -> TranslucencyInfo:
        """
        Detect translucency rendering from GlStateManager blend calls.

        Patterns:
          - enableBlend() + blendFunc(SRC_ALPHA, ONE_MINUS_SRC_ALPHA)
            → RenderType.entityTranslucent
          - blendFunc(ONE, ONE_MINUS_SRC_COLOR) → additive/custom (note only)
          - enableAlpha() + specific alpha func

        Only detects patterns within model rendering context,
        not GUI or other rendering contexts.

        Returns:
            TranslucencyInfo with detection results
        """
        info = TranslucencyInfo()

        # Pattern: enableBlend
        enable_blend_pattern = re.compile(
            r'GlStateManager\.func_179098_w\(\)|GlStateManager\.enableBlend\(\)'
        )
        enable_blend_matches = list(enable_blend_pattern.finditer(source))

        if not enable_blend_matches:
            return info

        # Pattern: blendFunc with SRC_ALPHA
        src_alpha_pattern = re.compile(
            r'GlStateManager\.func_179120_a\(\s*GlStateManager\.SourceFactor\.SRC_ALPHA\s*,\s*'
            r'GlStateManager\.DestFactor\.ONE_MINUS_SRC_ALPHA\s*\)'
            r'|GlStateManager\.blendFunc\(\s*GlStateManager\.SourceFactor\.SRC_ALPHA\s*,\s*'
            r'GlStateManager\.DestFactor\.ONE_MINUS_SRC_ALPHA\s*\)'
        )
        src_alpha_matches = list(src_alpha_pattern.finditer(source))

        # Pattern: blendFunc with ONE, ONE_MINUS_SRC_COLOR (additive)
        additive_pattern = re.compile(
            r'GlStateManager\.SourceFactor\.ONE\s*,\s*GlStateManager\.DestFactor\.ONE_MINUS_SRC_COLOR'
        )
        additive_matches = list(additive_pattern.finditer(source))

        if src_alpha_matches:
            info.detected = True
            info.blend_src = "SRC_ALPHA"
            info.blend_dst = "ONE_MINUS_SRC_ALPHA"
            info.render_type = "entityTranslucent"

            # Check if it's global or bone-level
            for match in enable_blend_matches:
                start = max(0, match.start() - 200)
                context = source[start:match.start()]
                bone_refs = re.findall(r'this\.(\w+)\.func_78785_a\s*\(', context)
                if bone_refs:
                    for bone_ref in bone_refs[-1:]:
                        bone_name = self.bone_mapping.get(bone_ref, bone_ref)
                        if bone_name not in info.translucent_bones:
                            info.translucent_bones.append(bone_name)
                else:
                    info.is_global = True

            info.source_pattern = f"enableBlend + blendFunc({info.blend_src}, {info.blend_dst})"

        elif additive_matches:
            info.detected = True
            info.blend_src = "ONE"
            info.blend_dst = "ONE_MINUS_SRC_COLOR"
            info.render_type = "custom_additive"
            info.source_pattern = "blendFunc(ONE, ONE_MINUS_SRC_COLOR) [additive/custom]"
            self._warnings.append(
                "Detected additive blending (ONE, ONE_MINUS_SRC_COLOR). "
                "No direct GeckoLib RenderType equivalent. "
                "Generated code will include a comment for manual implementation."
            )

        return info

    # ========================================================================
    # 3. Render Order Extraction
    # ========================================================================

    def _extract_render_order(self, source: str) -> List[RenderOrderEntry]:
        """
        Extract the render call order from the model's render method.

        In 1.12.2, ModelRenderer.render() calls in sequence define draw order.
        In GeckoLib, this maps to bone render stages.

        Patterns:
          - this.boneVar.func_78785_a(scale) → render call
          - super.func_78785_a(scale) → parent render

        Returns:
            List of RenderOrderEntry in original call order
        """
        entries = []

        # Find the render method body
        render_method = self._extract_render_method(source)
        if not render_method:
            return entries

        # Find all render calls
        render_call_pattern = re.compile(
            r'this\.(\w+)\.func_78785_a\s*\([^)]*\)\s*;'
        )

        order = 0
        for match in render_call_pattern.finditer(render_method):
            bone_var = match.group(1)

            # Skip non-bone variables
            if bone_var in ('field_78795_f', 'field_78796_g', 'field_78808_h'):
                continue

            bone_name = self.bone_mapping.get(bone_var, bone_var)
            entries.append(RenderOrderEntry(
                bone_var=bone_var,
                order_index=order,
                is_translucent_stage=False
            ))
            order += 1

        return entries

    def _extract_render_method(self, source: str) -> Optional[str]:
        """Extract the body of the render method."""
        # Try func_78088_a (render) or render method
        pattern = re.compile(
            r'public\s+void\s+(?:func_78088_a|render)\s*\([^)]+\)\s*\{',
            re.DOTALL
        )
        match = pattern.search(source)
        if not match:
            return None

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

    # ========================================================================
    # 4. Conditional Visibility Detection
    # ========================================================================

    def _detect_conditional_visibility(self, source: str) -> List[ConditionalVisibility]:
        """
        Detect conditional visibility patterns in render/animation code.

        Patterns:
          - if (entity.isInvisible()) → hide bone
          - if (entity.isChild()) → scale for baby
          - if (entity.hurtTime > 0) → hurt effect
          - if (entity.isInvisible() && ...) → compound conditions
          - if (someFlag) { this.bone.render(...) } → conditional render

        Returns:
            List of ConditionalVisibility entries
        """
        visibilities = []

        # Pattern: if (entity.isInvisible())
        invisible_pattern = re.compile(
            r'if\s*\(\s*(?:!?)\s*entity\.isInvisible\s*\(\s*\)\s*\)\s*\{([^}]+)\}',
            re.DOTALL
        )
        for match in invisible_pattern.finditer(source):
            body = match.group(1)
            condition_expr = match.group(0)[:match.group(0).index('{')].strip()
            is_negated = '!' in condition_expr and 'isInvisible' in condition_expr

            # Find bone references in the conditional block
            bone_refs = re.findall(r'this\.(\w+)\.(?:func_78785_a|field_78795_f|field_78796_g|field_78808_h)', body)
            for bone_var in bone_refs:
                bone_name = self.bone_mapping.get(bone_var, bone_var)
                visibilities.append(ConditionalVisibility(
                    bone_var=bone_var,
                    condition="entity.isInvisible()",
                    condition_type="invisible",
                    action="hidden",
                    inverted=is_negated  # !isInvisible → show when not invisible
                ))

        # Pattern: if (entity.isChild())
        child_pattern = re.compile(
            r'if\s*\(\s*(?:!?)\s*entity\.isChild\s*\(\s*\)\s*\)\s*\{([^}]+)\}',
            re.DOTALL
        )
        for match in child_pattern.finditer(source):
            body = match.group(1)

            # Look for scale modifications (GL11.glScalef or similar)
            scale_match = re.search(r'GlStateManager\.scale\s*\(\s*([\d.fF]+)\s*,', body)
            scale_value = None
            if scale_match:
                try:
                    scale_value = float(scale_match.group(1).rstrip('fF'))
                except ValueError:
                    pass

            bone_refs = re.findall(r'this\.(\w+)\.(?:func_78785_a|field_78795_f)', body)
            for bone_var in bone_refs:
                bone_name = self.bone_mapping.get(bone_var, bone_var)
                visibilities.append(ConditionalVisibility(
                    bone_var=bone_var,
                    condition="entity.isChild()",
                    condition_type="child",
                    action="scale" if scale_value else "hidden",
                    scale_value=scale_value
                ))

        # Pattern: if (entity.hurtTime > 0)
        hurt_pattern = re.compile(
            r'if\s*\(\s*entity\.hurtTime\s*>\s*0\s*\)\s*\{([^}]+)\}',
            re.DOTALL
        )
        for match in hurt_pattern.finditer(source):
            body = match.group(1)

            # Check for color modifications (red flash)
            has_color_change = bool(re.search(r'GlStateManager\.color\s*\(', body))

            bone_refs = re.findall(r'this\.(\w+)\.(?:func_78785_a|field_78795_f|field_78796_g)', body)
            for bone_var in bone_refs:
                bone_name = self.bone_mapping.get(bone_var, bone_var)
                visibilities.append(ConditionalVisibility(
                    bone_var=bone_var,
                    condition="entity.hurtTime > 0",
                    condition_type="hurt",
                    action="hidden"
                ))

        # Pattern: Generic conditional render (if (flag) { bone.render(); })
        generic_cond_pattern = re.compile(
            r'if\s*\(\s*(\w+)\s*\)\s*\{\s*this\.(\w+)\.func_78785_a\s*\('
        )
        for match in generic_cond_pattern.finditer(source):
            condition = match.group(1)
            bone_var = match.group(2)
            if condition in ('isInvisible', 'isChild', 'hurtTime'):
                continue  # Already handled above
            bone_name = self.bone_mapping.get(bone_var, bone_var)
            visibilities.append(ConditionalVisibility(
                bone_var=bone_var,
                condition=f"entity.{condition}",
                condition_type="custom",
                action="hidden"
            ))

        return visibilities

    # ========================================================================
    # 5. Dynamic UV Detection (Warning-only)
    # ========================================================================

    def _detect_dynamic_uv(self, source: str) -> List[DynamicUVInfo]:
        """
        Detect dynamic UV/texture offset modifications.

        Patterns:
          - setTextureOffset called inside animation methods (not constructor)
          - textureOffsetX/Y modified per frame

        Detection only; generates warnings. Cannot auto-migrate to GeckoLib.

        Returns:
            List of DynamicUVInfo entries
        """
        uv_infos = []

        # Find setRotationAngles method body
        anim_method = self._extract_animation_method(source)
        if not anim_method:
            return uv_infos

        # Pattern: this.bone.setTextureOffset(u, v) inside animation method
        set_tex_pattern = re.compile(
            r'this\.(\w+)\.setTextureOffset\s*\(\s*([^,]+)\s*,\s*([^)]+)\s*\)'
        )
        for match in set_tex_pattern.finditer(anim_method):
            bone_var = match.group(1)
            u_expr = match.group(2).strip()
            v_expr = match.group(3).strip()

            # Check if the expressions are dynamic (contain variables)
            is_dynamic = bool(re.search(r'[a-zA-Z_]\w*', u_expr.replace('Math', '').replace('MathHelper', '')))

            if is_dynamic:
                bone_name = self.bone_mapping.get(bone_var, bone_var)
                uv_infos.append(DynamicUVInfo(
                    bone_var=bone_var,
                    is_per_frame=True,
                    expression=f"setTextureOffset({u_expr}, {v_expr})",
                    detected=True
                ))
                self._warnings.append(
                    f"Detected dynamic UV modification for bone '{bone_name}': "
                    f"setTextureOffset({u_expr}, {v_expr}). "
                    f"Cannot auto-migrate to GeckoLib UV animation. "
                    f"Converting as static UV. Please manually add UV animation if needed."
                )

        # Pattern: this.bone.textureOffsetX = expr
        tex_offset_pattern = re.compile(
            r'this\.(\w+)\.textureOffset[X-Y]\s*=\s*([^;]+);'
        )
        for match in tex_offset_pattern.finditer(anim_method):
            bone_var = match.group(1)
            expr = match.group(2).strip()
            bone_name = self.bone_mapping.get(bone_var, bone_var)
            uv_infos.append(DynamicUVInfo(
                bone_var=bone_var,
                is_per_frame=True,
                expression=expr,
                detected=True
            ))
            self._warnings.append(
                f"Detected dynamic texture offset for bone '{bone_name}': {expr}. "
                f"Cannot auto-migrate. Please manually add UV animation."
            )

        return uv_infos

    def _extract_animation_method(self, source: str) -> Optional[str]:
        """Extract the body of setRotationAngles or animate method."""
        # Try func_78087_a (setRotationAngles)
        for method_name in [r'func_78087_a', r'setRotationAngles', r'setLivingAnimations', r'func_78087_a']:
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

    # ========================================================================
    # Code Generation
    # ========================================================================

    def _generate_render_type_code(self, result: RenderEffectResult) -> str:
        """
        Generate Java code for getRenderType override in GeoModel.

        Returns:
            Java code string for the getRenderType method, or empty string
            if no render type override is needed.
        """
        lines = []

        if result.emissive.detected and result.emissive.is_global:
            lines.append("// Auto-generated: Emissive rendering detected from original code")
            lines.append("// Source: " + result.emissive.source_pattern)
            lines.append("@Override")
            lines.append("public RenderType getRenderType(T animatable, ResourceLocation texture) {")
            lines.append("    return RenderType.eyes(texture);")
            lines.append("}")
        elif result.translucency.detected and result.translucency.is_global:
            lines.append("// Auto-generated: Translucent rendering detected from original code")
            lines.append("// Source: " + result.translucency.source_pattern)
            lines.append("@Override")
            lines.append("public RenderType getRenderType(T animatable, ResourceLocation texture) {")
            lines.append("    return RenderType.entityTranslucent(texture);")
            lines.append("}")
        elif result.emissive.detected and result.emissive.emissive_bones:
            lines.append("// Auto-generated: Partial emissive rendering detected")
            lines.append("// Emissive bones: " + str(result.emissive.emissive_bones))
            lines.append("// NOTE: GeckoLib does not support per-bone emissive in getRenderType.")
            lines.append("// Consider creating an emissive texture (_e.png) for these bones.")
            lines.append("// For codeAnimations, use: bone.setEmissive(true) (if GeckoLib supports)")
            lines.append("@Override")
            lines.append("public RenderType getRenderType(T animatable, ResourceLocation texture) {")
            lines.append("    // TODO: If all bones should be emissive, use RenderType.eyes(texture)")
            lines.append("    // For partial emissive, consider custom RenderType or _e texture")
            lines.append("    return super.getRenderType(animatable, texture);")
            lines.append("}")

        if result.translucency.detected and not result.translucency.is_global:
            lines.append("// NOTE: Translucent rendering detected for specific bones: "
                        + str(result.translucency.translucent_bones))
            lines.append("// Per-bone translucency requires custom RenderType or shader.")

        return '\n'.join(lines)

    def _generate_visibility_code(self, result: RenderEffectResult) -> str:
        """
        Generate Java code for conditional visibility in codeAnimations.

        Returns:
            Java code string for bone visibility control
        """
        if not result.conditional_visibility:
            return ""

        lines = []
        lines.append("// Auto-generated: Conditional visibility from original code")

        for cv in result.conditional_visibility:
            bone_name = self.bone_mapping.get(cv.bone_var, cv.bone_var)

            if cv.condition_type == "invisible":
                if cv.inverted:
                    lines.append(f'// Show bone "{bone_name}" when entity is NOT invisible')
                    lines.append(f'GeoBone {cv.bone_var}Bone = this.getAnimationProcessor().getBone("{bone_name}");')
                    lines.append(f'if ({cv.bone_var}Bone != null) {{')
                    lines.append(f'    {cv.bone_var}Bone.setHidden(!entity.isInvisible()); // inverted logic')
                    lines.append(f'}}')
                else:
                    lines.append(f'// Hide bone "{bone_name}" when entity is invisible')
                    lines.append(f'GeoBone {cv.bone_var}Bone = this.getAnimationProcessor().getBone("{bone_name}");')
                    lines.append(f'if ({cv.bone_var}Bone != null) {{')
                    lines.append(f'    {cv.bone_var}Bone.setHidden(entity.isInvisible());')
                    lines.append(f'}}')

            elif cv.condition_type == "child":
                lines.append(f'// Baby scaling for bone "{bone_name}"')
                lines.append(f'GeoBone {cv.bone_var}Bone = this.getAnimationProcessor().getBone("{bone_name}");')
                lines.append(f'if ({cv.bone_var}Bone != null && entity.isChild()) {{')
                if cv.scale_value:
                    lines.append(f'    {cv.bone_var}Bone.setScaleX({cv.scale_value}f);')
                    lines.append(f'    {cv.bone_var}Bone.setScaleY({cv.scale_value}f);')
                    lines.append(f'    {cv.bone_var}Bone.setScaleZ({cv.scale_value}f);')
                else:
                    lines.append(f'    {cv.bone_var}Bone.setScaleX(0.5f); // default baby scale')
                    lines.append(f'    {cv.bone_var}Bone.setScaleY(0.5f);')
                    lines.append(f'    {cv.bone_var}Bone.setScaleZ(0.5f);')
                lines.append(f'}}')

            elif cv.condition_type == "hurt":
                lines.append(f'// Hurt effect for bone "{bone_name}"')
                lines.append(f'// NOTE: Hurt shake is handled by separate hurt controller')
                lines.append(f'// See animation converter hurt controller generation')

            elif cv.condition_type == "custom":
                lines.append(f'// Custom condition for bone "{bone_name}": {cv.condition}')
                lines.append(f'GeoBone {cv.bone_var}Bone = this.getAnimationProcessor().getBone("{bone_name}");')
                lines.append(f'if ({cv.bone_var}Bone != null) {{')
                lines.append(f'    {cv.bone_var}Bone.setHidden(!({cv.condition})); // adjust logic as needed')
                lines.append(f'}}')

        return '\n'.join(lines)

    def _generate_render_order_code(self, result: RenderEffectResult) -> str:
        """
        Generate Java code for render ordering.

        Returns:
            Java code string for render stage assignment
        """
        if not result.render_order:
            return ""

        lines = []
        lines.append("// Auto-generated: Render order from original code")
        lines.append("// Original render call order:")

        for entry in result.render_order:
            bone_name = self.bone_mapping.get(entry.bone_var, entry.bone_var)
            lines.append(f"//   {entry.order_index}: {bone_name}")

        # Only generate stage assignment for translucent bones
        translucent_bones = []
        if result.translucency.detected:
            translucent_bones = result.translucency.translucent_bones

        if translucent_bones:
            lines.append("// Translucent bones rendered after opaque:")
            for bone_var in translucent_bones:
                bone_name = self.bone_mapping.get(bone_var, bone_var)
                lines.append(f'GeoBone {bone_var}Bone = this.getAnimationProcessor().getBone("{bone_name}");')
                lines.append(f'if ({bone_var}Bone != null) {{')
                lines.append(f'    {bone_var}Bone.setRenderStage(RenderStage.AFTER_TRANSLUCENT);')
                lines.append(f'}}')

        return '\n'.join(lines)
