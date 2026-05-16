#!/usr/bin/env python3
"""
OverlayDetector - Multi-layer Texture / Overlay Detection & Conversion
======================================================================
Detects LayerRenderer patterns, additional render() calls, color settings,
hurtTime-based overlays, and other multi-pass rendering in the original
MC 1.12.2 Java code. Outputs GeckoLib-compatible overlay specifications
with codeAnimations color settings and merge-hint annotations.

Detection patterns:
  - LayerRenderer subclasses (e.g. LayerHeldItem, LayerArmorBase)
  - Extra render() method calls in the main renderer
  - GlStateManager color changes (color4f, color3f)
  - hurtTime > 0 conditionals that tint the model red
  - Multiple texture binds per frame (ResourceLocation changes)
  - RenderType switches (eyes, translucent, solid)

Output:
  - overlay_layers: list of OverlayLayer specifications
  - color_settings: codeAnimations-compatible color keyframes
  - merge_hints: annotations suggesting texture merge strategies
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import re


@dataclass
class OverlayLayer:
    """A detected overlay rendering layer."""
    name: str
    """Human-readable name for the overlay (e.g. 'hurt_overlay', 'glow_layer')."""
    layer_type: str
    """Type: 'hurt_tint', 'emissive', 'translucent', 'held_item', 'armor', 'custom'."""
    trigger_condition: str
    """Java expression that triggers this layer (e.g. 'hurtTime > 0')."""
    color_rgba: Optional[Tuple[float, float, float, float]]
    """RGBA color tint applied during overlay (0.0-1.0 each). None if no color."""
    texture_path: Optional[str]
    """Alternative texture used by this layer, if any."""
    render_pass: int
    """Render pass order (0=base, 1=first overlay, etc.)."""
    bone_names: List[str]
    """Bones affected by this overlay (empty = all bones)."""
    code_anim_snippet: str
    """Generated codeAnimations snippet for this overlay."""


@dataclass
class MergeHint:
    """Suggestion for merging textures or adjusting the model."""
    hint_type: str
    """'merge_texture', 'split_geo', 'use_rendertype', 'code_animation'."""
    description: str
    """Human-readable description of the merge action."""
    priority: str
    """'required', 'recommended', 'optional'."""
    affected_bones: List[str]
    """Bones this hint applies to."""


@dataclass
class OverlayDetectionResult:
    """Result of overlay detection analysis."""
    overlay_layers: List[OverlayLayer]
    """Detected overlay layers."""
    color_settings: List[dict]
    """Color keyframe settings for codeAnimations."""
    merge_hints: List[MergeHint]
    """Texture merge suggestions."""
    warnings: List[str]
    """Non-fatal warnings during detection."""
    has_overlay: bool
    """Whether any overlay was detected."""


class OverlayDetector:
    """
    Detects multi-layer texture/overlay rendering patterns in MC 1.12.2
    Java source code and converts them to GeckoLib 1.20.1 specifications.
    """

    # Pattern: LayerRenderer class names
    LAYER_CLASS_PATTERN = re.compile(
        r'class\s+\w+Layer\s+extends\s+LayerRenderer'
        r'|class\s+\w+Layer\s+extends\s+\w+Layer'
    )

    # Pattern: hurtTime conditional
    HURT_TIME_PATTERN = re.compile(
        r'if\s*\(\s*(?:entity\.)?hurtTime\s*>\s*0\s*\)'
        r'|if\s*\(\s*(?:entity\.)?hurtTime\s*!=\s*0\s*\)'
    )

    # Pattern: GlStateManager color calls
    COLOR_PATTERN = re.compile(
        r'GlStateManager\.color[34]f\s*\(\s*([0-9.fF]+)\s*,\s*([0-9.fF]+)\s*,\s*([0-9.fF]+)'
        r'(?:\s*,\s*([0-9.fF]+))?\s*\)'
    )

    # Pattern: ResourceLocation binding
    TEXTURE_BIND_PATTERN = re.compile(
        r'(?:this\.)?bindTexture\s*\(\s*new\s+ResourceLocation\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)\s*\)'
        r'|(?:this\.)?bindTexture\s*\(\s*([A-Z_]+)\s*\)'
    )

    # Pattern: RenderType / render pass detection
    RENDER_TYPE_PATTERN = re.compile(
        r'RenderType\.(eyes|entityTranslucent|entitySolid|entityCutout|entityCutoutNoCull|entityTranslucentEmissive)'
    )

    # Pattern: Additional render calls (super.render or doRender with different params)
    EXTRA_RENDER_PATTERN = re.compile(
        r'super\.render\s*\(\s*[^)]+\)\s*;.*?//\s*overlay'
        r'|this\.\w+Renderer\.render\s*\(',
        re.DOTALL
    )

    # Pattern: Entity state flags that affect rendering
    STATE_FLAG_PATTERN = re.compile(
        r'if\s*\(\s*(?:entity\.)?(\w+)\s*\)',
        re.MULTILINE
    )

    def __init__(self, bone_mapping: Dict[str, str]):
        """
        Args:
            bone_mapping: Mapping from Java variable names to GeckoLib bone names.
        """
        self.bone_mapping = bone_mapping

    def detect(self, renderer_java: str, model_java: str = "") -> OverlayDetectionResult:
        """
        Detect overlay rendering layers in the Java source code.

        Args:
            renderer_java: Source code of the Renderer class.
            model_java: Source code of the Model class (optional, for cross-reference).

        Returns:
            OverlayDetectionResult with detected layers, color settings, and merge hints.
        """
        overlay_layers: List[OverlayLayer] = []
        color_settings: List[dict] = []
        merge_hints: List[MergeHint] = []
        warnings: List[str] = []
        render_pass = 1  # Start at 1 (0 is base model)

        # --- Detect LayerRenderer subclasses ---
        layer_classes = self.LAYER_CLASS_PATTERN.findall(renderer_java)
        for i, layer_match in enumerate(layer_classes):
            layer_name = f"layer_{i}"
            layer_type = "custom"
            if "HeldItem" in layer_match or "held" in layer_match.lower():
                layer_type = "held_item"
            elif "Armor" in layer_match or "armor" in layer_match.lower():
                layer_type = "armor"

            overlay_layers.append(OverlayLayer(
                name=layer_name,
                layer_type=layer_type,
                trigger_condition="true",  # LayerRenderers always render
                color_rgba=None,
                texture_path=None,
                render_pass=render_pass,
                bone_names=[],
                code_anim_snippet=f"// Layer: {layer_name} ({layer_type}) - see Java LayerRenderer"
            ))
            render_pass += 1

            merge_hints.append(MergeHint(
                hint_type="code_animation",
                description=f"LayerRenderer '{layer_match}' detected. "
                            f"In GeckoLib 1.20.1, implement as a separate GeoRenderer layer "
                            f"or use codeAnimations for dynamic effects.",
                priority="recommended",
                affected_bones=[]
            ))

        # --- Detect hurtTime-based overlays ---
        hurt_matches = self.HURT_TIME_PATTERN.findall(renderer_java + model_java)
        if hurt_matches:
            # Find accompanying color settings in hurtTime blocks
            hurt_color = (1.0, 0.3, 0.3, 1.0)  # Default hurt tint (red)

            # Search for color4f calls near hurtTime checks
            color_matches = self.COLOR_PATTERN.findall(renderer_java)
            for cm in color_matches:
                try:
                    r = float(cm[0].rstrip('fF'))
                    g = float(cm[1].rstrip('fF'))
                    b = float(cm[2].rstrip('fF'))
                    a = float(cm[3].rstrip('fF')) if cm[3] else 1.0
                    # If red channel is dominant and others are low, it's likely a hurt tint
                    if r > 0.5 and g < 0.5 and b < 0.5:
                        hurt_color = (r, g, b, a)
                        break
                except ValueError:
                    continue

            overlay_layers.append(OverlayLayer(
                name="hurt_overlay",
                layer_type="hurt_tint",
                trigger_condition="entity.hurtTime > 0",
                color_rgba=hurt_color,
                texture_path=None,
                render_pass=render_pass,
                bone_names=[],
                code_anim_snippet=self._generate_hurt_overlay_code(hurt_color)
            ))
            render_pass += 1

            color_settings.append({
                'overlay': 'hurt_overlay',
                'trigger': 'hurtTime > 0',
                'rgba': list(hurt_color),
                'type': 'hurt_tint'
            })

            merge_hints.append(MergeHint(
                hint_type="code_animation",
                description="Hurt overlay detected (red tint when hurtTime > 0). "
                            "Implement via codeAnimations: setRGBABones() or custom RenderType.",
                priority="recommended",
                affected_bones=[]
            ))

        # --- Detect color changes ---
        color_matches = self.COLOR_PATTERN.findall(renderer_java + model_java)
        detected_colors: List[Tuple[float, float, float, float]] = []
        for cm in color_matches:
            try:
                r = float(cm[0].rstrip('fF'))
                g = float(cm[1].rstrip('fF'))
                b = float(cm[2].rstrip('fF'))
                a = float(cm[3].rstrip('fF')) if cm[3] else 1.0
                detected_colors.append((r, g, b, a))
            except ValueError:
                continue

        # Filter out the hurt color (already handled)
        for color in detected_colors:
            if color == (1.0, 0.3, 0.3, 1.0) or (color[0] > 0.5 and color[1] < 0.5 and color[2] < 0.5):
                continue  # Skip hurt colors (already handled)
            if abs(color[0] - 1.0) < 0.01 and abs(color[1] - 1.0) < 0.01 and abs(color[2] - 1.0) < 0.01:
                continue  # Skip identity color (1,1,1,1) = no tint

            overlay_layers.append(OverlayLayer(
                name=f"color_tint_{len(overlay_layers)}",
                layer_type="custom",
                trigger_condition="true",
                color_rgba=color,
                texture_path=None,
                render_pass=render_pass,
                bone_names=[],
                code_anim_snippet=self._generate_color_tint_code(color)
            ))
            render_pass += 1

            color_settings.append({
                'overlay': f"color_tint_{len(color_settings)}",
                'rgba': list(color),
                'type': 'static_tint'
            })

            warnings.append(
                f"Detected non-standard color tint RGBA=({color[0]:.2f},{color[1]:.2f},"
                f"{color[2]:.2f},{color[3]:.2f}). Verify if this is intentional."
            )

        # --- Detect multiple texture binds ---
        texture_binds = self.TEXTURE_BIND_PATTERN.findall(renderer_java)
        seen_textures: set = set()
        for tb in texture_binds:
            if isinstance(tb, tuple) and len(tb) >= 2:
                namespace = tb[0] if tb[0] else "minecraft"
                path = tb[1] if tb[1] else tb[2] if len(tb) > 2 else ""
                texture_key = f"{namespace}:{path}"
                if texture_key not in seen_textures:
                    seen_textures.add(texture_key)
                    if len(seen_textures) > 1:
                        overlay_layers.append(OverlayLayer(
                            name=f"alt_texture_{len(overlay_layers)}",
                            layer_type="custom",
                            trigger_condition="true",
                            color_rgba=None,
                            texture_path=texture_key,
                            render_pass=render_pass,
                            bone_names=[],
                            code_anim_snippet=f"// Alternative texture: {texture_key}"
                        ))
                        render_pass += 1

                        merge_hints.append(MergeHint(
                            hint_type="merge_texture",
                            description=f"Multiple textures detected: {texture_key}. "
                                        f"Consider merging textures into a single atlas or "
                                        f"using GeckoLib's multi-render-layer approach.",
                            priority="recommended",
                            affected_bones=[]
                        ))

        # --- Detect RenderType switches ---
        render_type_matches = self.RENDER_TYPE_PATTERN.findall(renderer_java)
        for rt in render_type_matches:
            if rt == "eyes":
                overlay_layers.append(OverlayLayer(
                    name="emissive_overlay",
                    layer_type="emissive",
                    trigger_condition="true",
                    color_rgba=None,
                    texture_path=None,
                    render_pass=render_pass,
                    bone_names=[],
                    code_anim_snippet="// Emissive overlay: override getRenderType() → RenderType.eyes(texture)"
                ))
                render_pass += 1

                merge_hints.append(MergeHint(
                    hint_type="use_rendertype",
                    description="Emissive (eyes) RenderType detected. "
                                "Override getRenderType() in your GeoModel to return RenderType.eyes(texture) "
                                "for glowing eye/emissive bone rendering.",
                    priority="required",
                    affected_bones=[]
                ))

            elif rt == "entityTranslucent" or rt == "entityTranslucentEmissive":
                overlay_layers.append(OverlayLayer(
                    name="translucent_overlay",
                    layer_type="translucent",
                    trigger_condition="true",
                    color_rgba=None,
                    texture_path=None,
                    render_pass=render_pass,
                    bone_names=[],
                    code_anim_snippet="// Translucent overlay: override getRenderType() → RenderType.entityTranslucent(texture)"
                ))
                render_pass += 1

        # --- Detect entity state flags that affect visibility ---
        state_flags = self.STATE_FLAG_PATTERN.findall(renderer_java)
        entity_state_flags = set()
        known_flags = {'isAttacking', 'isMoving', 'isChild', 'isInvisible', 'isAlive',
                       'isDeadOrDying', 'isOnFire', 'isSprinting', 'isShiftKeyDown'}
        for flag in state_flags:
            if flag in known_flags:
                entity_state_flags.add(flag)

        if entity_state_flags:
            merge_hints.append(MergeHint(
                hint_type="code_animation",
                description=f"Entity state flags detected: {', '.join(entity_state_flags)}. "
                            f"Use codeAnimations to conditionally show/hide bones based on entity state.",
                priority="recommended",
                affected_bones=[]
            ))

        has_overlay = len(overlay_layers) > 0

        return OverlayDetectionResult(
            overlay_layers=overlay_layers,
            color_settings=color_settings,
            merge_hints=merge_hints,
            warnings=warnings,
            has_overlay=has_overlay
        )

    def _generate_hurt_overlay_code(self, color: Tuple[float, float, float, float]) -> str:
        """Generate codeAnimations snippet for hurt overlay."""
        r, g, b, a = color
        return (
            f"// Hurt overlay - red tint when hurtTime > 0\n"
            f"// In codeAnimations():\n"
            f"if (entity.hurtTime > 0) {{\n"
            f"    for (GeoBone bone : getAllBones()) {{\n"
            f"        bone.setRGBA({r}f, {g}f, {b}f, {a}f);\n"
            f"    }}\n"
            f"}} else {{\n"
            f"    for (GeoBone bone : getAllBones()) {{\n"
            f"        bone.setRGBA(1f, 1f, 1f, 1f);\n"
            f"    }}\n"
            f"}}"
        )

    def _generate_color_tint_code(self, color: Tuple[float, float, float, float]) -> str:
        """Generate codeAnimations snippet for static color tint."""
        r, g, b, a = color
        return (
            f"// Static color tint RGBA=({r:.2f}, {g:.2f}, {b:.2f}, {a:.2f})\n"
            f"// In codeAnimations():\n"
            f"for (GeoBone bone : getAllBones()) {{\n"
            f"    bone.setRGBA({r}f, {g}f, {b}f, {a}f);\n"
            f"}}"
        )
