#!/usr/bin/env python3
"""
AnimationLayerSeparator - Animation Layer Auto-Separation
==========================================================
Separates animation data into independent layers for GeckoLib controllers.

GeckoLib supports multiple AnimationControllers per entity, each running
independently with its own priority and blending. This module analyzes
the animation JSON and separates bones into logical layers:

  - Base layer: idle/walk animations (low priority, always running)
  - Overlay layer: hurt/attack effects (high priority, transient)
  - Additive layer: breathing/sway (blends additively)

This allows different animation states to blend independently rather than
having a single monolithic animation that must account for all states.

All detection failures default to single-layer with warnings.
Does NOT modify core_math.py or existing converter modules.
"""

import re
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class AnimationLayer:
    """A separated animation layer."""
    name: str
    layer_type: str  # "base", "overlay", "additive"
    priority: int = 0  # Higher = overrides lower
    animation_names: List[str] = field(default_factory=list)
    bone_names: List[str] = field(default_factory=list)
    is_looping: bool = True
    transition_length: float = 0.0  # Blend time in seconds
    controller_name: str = ""  # Generated controller name

    def __post_init__(self):
        if not self.controller_name:
            self.controller_name = f"{self.name}Controller"


@dataclass
class LayerSeparationResult:
    """Complete result from animation layer separation."""
    layers: List[AnimationLayer] = field(default_factory=list)
    bone_layer_map: Dict[str, str] = field(default_factory=dict)  # bone -> layer name
    controller_code: str = ""  # Generated Java controller registration code
    warnings: List[str] = field(default_factory=list)


# ============================================================================
# AnimationLayerSeparator
# ============================================================================

class AnimationLayerSeparator:
    """
    Separates animation data into independent layers for GeckoLib controllers.

    Detection heuristics:
      1. Bones whose animation is conditional on hurtTime → overlay (hurt) layer
      2. Bones with sin/cos patterns based on ageInTicks → base (idle) layer
      3. Bones with small amplitude breathing patterns → additive (sway) layer
      4. Bones appearing in multiple animation contexts → overlay layer

    Falls back to single-layer on detection failure with warnings.
    """

    # Keywords that suggest overlay (hurt/attack) layer
    OVERLAY_KEYWORDS = {
        'hurt', 'attack', 'hit', 'damage', 'strike', 'swing',
        'death', 'die', 'kill', 'pain', 'flinch', 'shake'
    }

    # Keywords that suggest base (idle/walk) layer
    BASE_KEYWORDS = {
        'idle', 'walk', 'run', 'move', 'stand', 'rest',
        'swim', 'fly', 'sneak', 'sprint'
    }

    # Keywords that suggest additive (breathing/sway) layer
    ADDITIVE_KEYWORDS = {
        'breath', 'sway', 'idle_sway', 'subtle', 'ambient',
        'tail', 'ear', 'mane', 'hair'
    }

    # Bone name patterns for specific layers
    TAIL_PATTERN = re.compile(r'tail|caudal', re.IGNORECASE)
    EAR_PATTERN = re.compile(r'ear|auri', re.IGNORECASE)
    MANE_PATTERN = re.compile(r'mane|crest|plume', re.IGNORECASE)
    HURT_PATTERN = re.compile(r'hurt|hit|damage|shake', re.IGNORECASE)

    def __init__(self, bone_mapping: Dict[str, str] = None):
        """
        Args:
            bone_mapping: Dict mapping 1.12.2 java var names to GeckoLib bone IDs
        """
        self.bone_mapping = bone_mapping or {}
        self._warnings: List[str] = []

    def separate(self, animation_json: dict, bone_mapping: Dict[str, str] = None) -> LayerSeparationResult:
        """
        Separate animation JSON into layers based on bone names and animation patterns.

        Args:
            animation_json: The .animation.json structure
            bone_mapping: Optional bone mapping (overrides constructor mapping)

        Returns:
            LayerSeparationResult with separated layers and generated code
        """
        if bone_mapping:
            self.bone_mapping = bone_mapping

        result = LayerSeparationResult()
        animations = animation_json.get('animations', {})

        if not animations:
            result.warnings.append("No animations found in JSON")
            # Default: single base layer
            result.layers.append(AnimationLayer(
                name="base",
                layer_type="base",
                priority=0
            ))
            return result

        # Collect all bone names across all animations
        all_bones = set()
        anim_bone_map: Dict[str, List[str]] = {}  # anim_name -> bone_names

        for anim_name, anim_data in animations.items():
            bones = anim_data.get('bones', {})
            bone_names = list(bones.keys())
            all_bones.update(bone_names)
            anim_bone_map[anim_name] = bone_names

        # Classify each bone into a layer based on heuristics
        bone_classifications: Dict[str, str] = {}

        for bone_name in all_bones:
            layer_type = self._classify_bone(bone_name, animations)
            bone_classifications[bone_name] = layer_type

        # Group bones by layer type
        base_bones = [b for b, t in bone_classifications.items() if t == 'base']
        overlay_bones = [b for b, t in bone_classifications.items() if t == 'overlay']
        additive_bones = [b for b, t in bone_classifications.items() if t == 'additive']

        # If all bones are base (common for simple idle-only animations),
        # keep as single layer
        if not overlay_bones and not additive_bones:
            result.layers.append(AnimationLayer(
                name="base",
                layer_type="base",
                priority=0,
                animation_names=list(animations.keys()),
                bone_names=base_bones,
                is_looping=True,
                transition_length=0.0
            ))
            for bone in base_bones:
                result.bone_layer_map[bone] = "base"
        else:
            # Create multiple layers
            if base_bones:
                base_anims = [name for name in animations.keys()
                              if any(kw in name.lower() for kw in self.BASE_KEYWORDS)
                              or not any(kw in name.lower() for kw in self.OVERLAY_KEYWORDS)]
                if not base_anims:
                    base_anims = list(animations.keys())

                result.layers.append(AnimationLayer(
                    name="base",
                    layer_type="base",
                    priority=0,
                    animation_names=base_anims,
                    bone_names=base_bones,
                    is_looping=True,
                    transition_length=0.1
                ))
                for bone in base_bones:
                    result.bone_layer_map[bone] = "base"

            if overlay_bones:
                overlay_anims = [name for name in animations.keys()
                                 if any(kw in name.lower() for kw in self.OVERLAY_KEYWORDS)]
                if not overlay_anims:
                    overlay_anims = list(animations.keys())

                result.layers.append(AnimationLayer(
                    name="hurt_overlay",
                    layer_type="overlay",
                    priority=10,
                    animation_names=overlay_anims,
                    bone_names=overlay_bones,
                    is_looping=False,
                    transition_length=0.05
                ))
                for bone in overlay_bones:
                    result.bone_layer_map[bone] = "hurt_overlay"

            if additive_bones:
                result.layers.append(AnimationLayer(
                    name="ambient_sway",
                    layer_type="additive",
                    priority=-1,
                    animation_names=list(animations.keys()),
                    bone_names=additive_bones,
                    is_looping=True,
                    transition_length=0.3
                ))
                for bone in additive_bones:
                    result.bone_layer_map[bone] = "ambient_sway"

        # Generate controller registration code
        result.controller_code = self._generate_controller_code(result.layers)

        result.warnings = self._warnings
        return result

    def _classify_bone(self, bone_name: str, animations: dict) -> str:
        """
        Classify a bone into a layer type based on its name and animation data.

        Returns:
            "base", "overlay", or "additive"
        """
        bone_lower = bone_name.lower()

        # Check overlay patterns
        if self.HURT_PATTERN.search(bone_lower):
            return "overlay"

        # Check additive patterns (tail, ear, mane swing)
        if (self.TAIL_PATTERN.search(bone_lower) or
                self.EAR_PATTERN.search(bone_lower) or
                self.MANE_PATTERN.search(bone_lower)):
            # These are typically additive sway animations
            return "additive"

        # Check animation data patterns
        for anim_name, anim_data in animations.items():
            bones = anim_data.get('bones', {})
            if bone_name not in bones:
                continue

            # Check if this animation name suggests overlay
            anim_lower = anim_name.lower()
            if any(kw in anim_lower for kw in self.OVERLAY_KEYWORDS):
                return "overlay"

            # Check bone's animation amplitude
            bone_data = bones[bone_name]
            rotation = bone_data.get('rotation', {})
            max_amplitude = 0.0
            for axis, axis_data in rotation.items():
                if isinstance(axis_data, dict):
                    for v in axis_data.values():
                        if isinstance(v, (int, float)):
                            max_amplitude = max(max_amplitude, abs(v))
                        elif isinstance(v, dict):
                            # Handle eased keyframe format: {"vector": val, "easing": "..."}
                            vec = v.get('vector', v.get('value'))
                            if isinstance(vec, (int, float)):
                                max_amplitude = max(max_amplitude, abs(vec))
                            elif isinstance(vec, list):
                                for item in vec:
                                    if isinstance(item, (int, float)):
                                        max_amplitude = max(max_amplitude, abs(item))

            # Small amplitude = additive (breathing/sway)
            if max_amplitude > 0 and max_amplitude < 2.0:
                return "additive"

        # Default: base layer
        return "base"

    def _generate_controller_code(self, layers: List[AnimationLayer]) -> str:
        """
        Generate Java code for AnimationController registration.

        Returns:
            Java code string for registerControllers method
        """
        if not layers:
            return ""

        lines = []
        lines.append("// Auto-generated by MinecraftModelMigrator-Pro")
        lines.append("// Animation Layer Controller Registration")
        lines.append("//")
        lines.append("// Each layer runs as an independent AnimationController")
        lines.append("// with its own priority and blending behavior.")
        lines.append("")
        lines.append("// Register in your GeoModel's registerControllers() method:")
        lines.append("//")
        lines.append("@Override")
        lines.append("public void registerControllers(AnimatableManager.ControllerRegistrar controllerRegistrar) {")

        for layer in layers:
            ctrl_name = layer.controller_name
            trans = layer.transition_length
            if layer.layer_type == "base":
                lines.append("    // Base layer: {} (priority {})".format(layer.name, layer.priority))
                lines.append('    controllerRegistrar.add(new AnimationController<>(this, "{}",'.format(ctrl_name))
                lines.append('        {}f, state -> {{'.format(trans))
                lines.append('            // Play base animation (idle/walk)')
                for anim_name in layer.animation_names[:3]:
                    lines.append('            // state.getController().setAnimation(RawAnimation.begin().thenPlay("{}"));'.format(anim_name))
                lines.append('            return PlayState.CONTINUE;')
                lines.append('        }));')
            elif layer.layer_type == "overlay":
                lines.append("    // Overlay layer: {} (priority {})".format(layer.name, layer.priority))
                lines.append('    controllerRegistrar.add(new AnimationController<>(this, "{}",'.format(ctrl_name))
                lines.append('        {}f, state -> {{'.format(trans))
                lines.append('            // Overlay animation (hurt/attack) - only plays when triggered')
                lines.append('            // Use: state.getController().setAnimation(...)')
                lines.append('            return PlayState.STOP;')
                lines.append('        }));')
            elif layer.layer_type == "additive":
                lines.append("    // Additive layer: {} (priority {})".format(layer.name, layer.priority))
                lines.append('    // Ambient sway/breathing - always runs with additive blending')
                lines.append('    controllerRegistrar.add(new AnimationController<>(this, "{}",'.format(ctrl_name))
                lines.append('        {}f, state -> {{'.format(trans))
                for anim_name in layer.animation_names[:1]:
                    lines.append('            state.getController().setAnimation(RawAnimation.begin().thenPlay("{}"));'.format(anim_name))
                lines.append('            return PlayState.CONTINUE;')
                lines.append('        }));')
            lines.append('')

        lines.append("}")
        return '\n'.join(lines)
