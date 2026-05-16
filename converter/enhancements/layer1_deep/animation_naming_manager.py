#!/usr/bin/env python3
"""
AnimationNamingManager - Animation Naming & Multi-Animation Combination Management
===================================================================================
Manages animation naming conventions, conflict resolution, multi-animation
combination, and reference consistency for GeckoLib 1.20.1 output.

Key responsibilities:
  - Derive animation names from Java method names or state conditions
  - Enforce GeckoLib naming convention: animation.<namespace>.<entity>.<action>
  - Resolve naming conflicts with numeric suffixes
  - Support user-configurable naming overrides via animation_naming.json
  - Generate AnimationNames constant interface for Java code
  - Track animation references across controllers for deduplication
  - Coordinate with animation layer separation (layer-prefixed names)

Naming convention:
  animation.<namespace>.<entity>.<action>

  Action name derivation priority:
    1. Explicit method name (e.g. setRotationAnglesIdle → idle)
    2. State machine branch (e.g. isAttacking() → attack)
    3. Fallback: anim_0, anim_1, etc.

  Constraints:
    - All lowercase, underscores for separators
    - No spaces, no camelCase
    - No duplicate names (append _2, _3, etc.)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
import json
import os
import re


@dataclass
class AnimationNameEntry:
    """A single animation name entry with metadata."""
    animation_name: str
    """Full GeckoLib animation name (e.g. 'animation.srparasites.kirin.idle')."""
    action_name: str
    """Short action name (e.g. 'idle')."""
    source_method: str
    """Original Java method or code location where this animation was found."""
    derivation_rule: str
    """How the name was derived: 'explicit', 'state_condition', 'fallback', 'user_config'."""
    layer_prefix: str
    """Layer prefix if applicable (e.g. 'base_', 'overlay_'). Empty if no layer."""
    is_looping: bool
    """Whether this animation loops."""
    reference_count: int
    """Number of controllers that reference this animation."""
    file_name: str
    """Expected animation file name (e.g. 'kirin.animation.json')."""


@dataclass
class AnimationNamesConstant:
    """A Java constant entry for the AnimationNames interface."""
    constant_name: str
    """Java constant name (e.g. 'KIRIN_IDLE')."""
    animation_name: str
    """Full animation name string (e.g. 'animation.srparasites.kirin.idle')."""


@dataclass
class NamingConflictWarning:
    """A naming conflict warning."""
    conflicting_name: str
    """The name that has conflicts."""
    sources: List[str]
    """Source methods/code locations that produce the same name."""
    resolution: str
    """How the conflict was resolved (e.g. 'appended _2')."""


@dataclass
class NamingConfig:
    """User-configurable naming overrides loaded from animation_naming.json."""
    namespace: str
    """Mod namespace (e.g. 'srparasites')."""
    entity_name: str
    """Entity name (e.g. 'kirin')."""
    overrides: Dict[str, str]
    """Manual mapping: original_derived_name → user_preferred_name."""
    layer_prefixes: Dict[str, str]
    """Layer type → prefix mapping (e.g. {'overlay': 'overlay_', 'additive': 'add_'})."""


@dataclass
class NamingResult:
    """Result of animation naming management."""
    entries: List[AnimationNameEntry]
    """All named animation entries."""
    constants: List[AnimationNamesConstant]
    """Java constant interface entries."""
    conflicts: List[NamingConflictWarning]
    """Naming conflict warnings."""
    reference_map: Dict[str, List[str]]
    """Animation name → list of controller names that reference it."""
    animation_file_map: Dict[str, str]
    """Animation name → file name mapping."""
    java_interface_code: str
    """Generated AnimationNames Java interface code."""
    warnings: List[str]
    """Non-fatal warnings."""


class AnimationNamingManager:
    """
    Manages animation naming, conflict resolution, and multi-animation
    combination for GeckoLib 1.20.1 output.
    """

    # Action name extraction from Java method names
    METHOD_NAME_PATTERNS = [
        # setRotationAngles<Name> → <name>
        re.compile(r'setRotationAngles(\w+)', re.IGNORECASE),
        # animate<Name> → <name>
        re.compile(r'animate(\w+)', re.IGNORECASE),
        # set<Name>Angles → <name>
        re.compile(r'set(\w+)Angles', re.IGNORECASE),
        # <name>Animation → <name>
        re.compile(r'(\w+)Animation', re.IGNORECASE),
    ]

    # State condition → action name mappings
    STATE_ACTION_MAP = {
        'isAttacking': 'attack',
        'isMoving': 'walk',
        'isIdle': 'idle',
        'isDead': 'death',
        'isHurt': 'hurt',
        'isOnFire': 'burn',
        'isSprinting': 'sprint',
        'isChild': 'child',
        'isInvisible': 'invisible',
        'isCharging': 'charge',
        'isFlying': 'fly',
        'isSwimming': 'swim',
        'isSleeping': 'sleep',
        'isSitting': 'sit',
        'isAngry': 'angry',
        'isTamed': 'tamed',
        'isAggressive': 'aggressive',
    }

    # Common action names from animation method naming conventions
    COMMON_ACTIONS = {
        'idle', 'walk', 'run', 'attack', 'hurt', 'death', 'fly', 'swim',
        'sit', 'sleep', 'eat', 'drink', 'jump', 'fall', 'land', 'sneak',
        'sprint', 'roar', 'charge', 'shoot', 'cast', 'summon', 'transform',
        'birth', 'grow', 'dig', 'rest', 'alert', 'patrol', 'flee',
    }

    # Default layer prefixes
    DEFAULT_LAYER_PREFIXES = {
        'base': '',
        'overlay': 'overlay_',
        'additive': 'add_',
    }

    def __init__(self, namespace: str = "srparasites", entity_name: str = "",
                 config_path: Optional[str] = None):
        """
        Args:
            namespace: Mod namespace for animation naming.
            entity_name: Entity name for animation naming.
            config_path: Optional path to animation_naming.json config file.
        """
        self.namespace = namespace
        self.entity_name = entity_name
        self.config = self._load_config(config_path, namespace, entity_name)
        self._used_names: Set[str] = set()

    def _load_config(self, config_path: Optional[str], namespace: str,
                     entity_name: str) -> NamingConfig:
        """Load user-configurable naming overrides from animation_naming.json."""
        config = NamingConfig(
            namespace=namespace,
            entity_name=entity_name,
            overrides={},
            layer_prefixes=dict(self.DEFAULT_LAYER_PREFIXES)
        )

        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    data = json.load(f)
                config.namespace = data.get('namespace', namespace)
                config.entity_name = data.get('entity_name', entity_name)
                config.overrides = data.get('overrides', {})
                config.layer_prefixes.update(data.get('layer_prefixes', {}))
            except (json.JSONDecodeError, IOError) as e:
                pass  # Silent fallback

        return config

    def derive_action_name(self, method_name: str, state_condition: str = "") -> Tuple[str, str]:
        """
        Derive an action name from a Java method name or state condition.

        Args:
            method_name: Java method name (e.g. 'setRotationAnglesIdle').
            state_condition: State condition string (e.g. 'isAttacking()').

        Returns:
            Tuple of (action_name, derivation_rule).
        """
        # Priority 0: User config override
        for original, override in self.config.overrides.items():
            if method_name and original in method_name.lower():
                return override, 'user_config'
            if state_condition and original in state_condition.lower():
                return override, 'user_config'

        # Priority 1: Explicit method name extraction
        if method_name:
            for pattern in self.METHOD_NAME_PATTERNS:
                match = pattern.search(method_name)
                if match:
                    raw_action = match.group(1)
                    action = self._normalize_action(raw_action)
                    if action in self.COMMON_ACTIONS:
                        return action, 'explicit'

        # Priority 2: State condition mapping
        if state_condition:
            for state_key, action_val in self.STATE_ACTION_MAP.items():
                if state_key.lower() in state_condition.lower():
                    return action_val, 'state_condition'

        # Priority 3: Fallback
        return 'anim_0', 'fallback'

    def generate_animation_name(self, action_name: str, layer_type: str = "base") -> str:
        """
        Generate a full GeckoLib animation name following the convention:
        animation.<namespace>.<entity>.<layer_prefix><action>

        Args:
            action_name: Short action name (e.g. 'idle').
            layer_type: Animation layer type ('base', 'overlay', 'additive').

        Returns:
            Full animation name string.
        """
        prefix = self.config.layer_prefixes.get(layer_type,
                   self.DEFAULT_LAYER_PREFIXES.get(layer_type, ''))
        return f"animation.{self.config.namespace}.{self.config.entity_name}.{prefix}{action_name}"

    def resolve_conflicts(self, entries: List[AnimationNameEntry]) -> List[NamingConflictWarning]:
        """
        Detect and resolve naming conflicts by appending numeric suffixes.

        Args:
            entries: List of animation name entries to check.

        Returns:
            List of NamingConflictWarning for any conflicts found.
        """
        conflicts: List[NamingConflictWarning] = []
        name_counts: Dict[str, List[str]] = {}

        for entry in entries:
            if entry.animation_name not in name_counts:
                name_counts[entry.animation_name] = []
            name_counts[entry.animation_name].append(entry.source_method)

        for name, sources in name_counts.items():
            if len(sources) > 1:
                # Conflict: append numeric suffixes
                for i, source in enumerate(sources[1:], start=2):
                    # Find the entry and modify its name
                    for entry in entries:
                        if entry.source_method == source and entry.animation_name == name:
                            # Parse the full name to insert suffix
                            parts = name.rsplit('.', 1)
                            new_action = f"{parts[1]}_{i}" if len(parts) > 1 else f"{name}_{i}"
                            new_full_name = f"{parts[0]}.{new_action}" if len(parts) > 1 else new_action

                            conflicts.append(NamingConflictWarning(
                                conflicting_name=name,
                                sources=sources,
                                resolution=f"Renamed to {new_full_name} (appended _{i})"
                            ))

                            entry.animation_name = new_full_name
                            entry.action_name = new_action
                            break

        return conflicts

    def manage(self, animation_sources: List[dict],
               layer_info: Optional[List[dict]] = None) -> NamingResult:
        """
        Main method: manage animation naming for all detected animations.

        Args:
            animation_sources: List of dicts with:
              - 'method_name': str - Java method name
              - 'state_condition': str - State condition (optional)
              - 'is_looping': bool - Whether the animation loops
              - 'animation_class': str - 'A1', 'A2', 'B' (optional)
              - 'animation_data': dict - Animation JSON data (optional)
            layer_info: Optional list of layer dicts from AnimationLayerSeparator.

        Returns:
            NamingResult with all naming entries, constants, and reference map.
        """
        entries: List[AnimationNameEntry] = []
        constants: List[AnimationNamesConstant] = []
        warnings: List[str] = []
        reference_map: Dict[str, List[str]] = {}
        animation_file_map: Dict[str, str] = {}

        fallback_counter = 0
        file_name = f"{self.config.entity_name}.animation.json"

        # Build layer mapping
        layer_map: Dict[str, str] = {}
        if layer_info:
            for layer in layer_info:
                layer_name = layer.get('name', 'base')
                layer_type = layer.get('layer_type', 'base')
                for bone in layer.get('bone_names', []):
                    layer_map[bone] = layer_type

        for source in animation_sources:
            method_name = source.get('method_name', '')
            state_condition = source.get('state_condition', '')
            is_looping = source.get('is_looping', True)
            anim_class = source.get('animation_class', 'A1')
            anim_data = source.get('animation_data')

            # Derive action name
            action_name, derivation_rule = self.derive_action_name(method_name, state_condition)

            # Handle fallback numbering
            if derivation_rule == 'fallback':
                action_name = f"anim_{fallback_counter}"
                fallback_counter += 1

            # Determine layer type
            layer_type = 'base'
            if method_name:
                lower_method = method_name.lower()
                if 'hurt' in lower_method:
                    layer_type = 'overlay'
                elif any(kw in lower_method for kw in ['tail', 'ear', 'mane', 'hair', 'wing']):
                    layer_type = 'additive'

            # Generate full animation name
            full_name = self.generate_animation_name(action_name, layer_type)

            entry = AnimationNameEntry(
                animation_name=full_name,
                action_name=action_name,
                source_method=method_name or state_condition or 'unknown',
                derivation_rule=derivation_rule,
                layer_prefix=self.config.layer_prefixes.get(layer_type,
                              self.DEFAULT_LAYER_PREFIXES.get(layer_type, '')),
                is_looping=is_looping,
                reference_count=0,
                file_name=file_name
            )
            entries.append(entry)

            # Generate Java constant name
            const_name = f"{self.config.entity_name.upper()}_{action_name.upper()}"
            constants.append(AnimationNamesConstant(
                constant_name=const_name,
                animation_name=full_name
            ))

            # Update reference map
            reference_map[full_name] = []
            animation_file_map[full_name] = file_name

        # Resolve conflicts
        conflicts = self.resolve_conflicts(entries)

        # Update constant names after conflict resolution
        for i, entry in enumerate(entries):
            if i < len(constants):
                # Re-derive constant name from final action name
                action_part = entry.action_name.upper()
                constants[i].constant_name = f"{self.config.entity_name.upper()}_{action_part}"
                constants[i].animation_name = entry.animation_name

        # Generate Java interface code
        java_interface = self._generate_animation_names_interface(constants)

        return NamingResult(
            entries=entries,
            constants=constants,
            conflicts=conflicts,
            reference_map=reference_map,
            animation_file_map=animation_file_map,
            java_interface_code=java_interface,
            warnings=warnings
        )

    def update_animation_json_names(self, animation_json: dict,
                                     naming_result: NamingResult) -> dict:
        """
        Update animation JSON to use the managed naming convention.

        Args:
            animation_json: Original animation JSON dict.
            naming_result: Result from manage().

        Returns:
            Updated animation JSON with renamed animations.
        """
        if 'animations' not in animation_json:
            return animation_json

        original_anims = animation_json['animations']
        new_anims = {}

        for original_name, anim_data in original_anims.items():
            # Find the corresponding entry
            new_name = original_name
            for entry in naming_result.entries:
                # Match by order if only one animation, or by action name inference
                if len(naming_result.entries) == 1:
                    new_name = entry.animation_name
                    break
                # Try to match by action keyword
                action = entry.action_name
                if action in original_name.lower():
                    new_name = entry.animation_name
                    break

            new_anims[new_name] = anim_data

        animation_json['animations'] = new_anims
        return animation_json

    def _normalize_action(self, raw_action: str) -> str:
        """
        Normalize a raw action name to lowercase underscore format.

        Examples:
          'Idle' → 'idle'
          'WalkForward' → 'walk_forward'
          'AttackMelee' → 'attack_melee'
        """
        # Insert underscores before uppercase letters
        result = re.sub(r'([A-Z])', r'_\1', raw_action)
        result = result.strip('_').lower()
        # Remove consecutive underscores
        result = re.sub(r'_+', '_', result)
        return result

    def _generate_animation_names_interface(self, constants: List[AnimationNamesConstant]) -> str:
        """Generate the AnimationNames Java interface code."""
        lines = [
            f"// Auto-generated Animation Names constant interface",
            f"// For {self.config.namespace}:{self.config.entity_name}",
            f"package com.example.{self.config.namespace}.client.animation;",
            f"",
            f"/**",
            f" * Centralized animation name constants for {self.config.entity_name} entity.",
            f" * Use these constants in all AnimationController references to ensure",
            f" * consistency and easy refactoring.",
            f" */",
            f"public interface AnimationNames {{",
        ]

        for const in constants:
            lines.append(
                f'    String {const.constant_name} = "{const.animation_name}";'
            )

        lines.append("}")
        return "\n".join(lines)

    def save_config_template(self, output_path: str) -> None:
        """
        Save a template animation_naming.json for user customization.

        Args:
            output_path: Path to save the template file.
        """
        template = {
            "namespace": self.namespace,
            "entity_name": self.entity_name,
            "overrides": {
                "idle": "idle",
                "walk": "walk",
                "attack": "attack",
                "hurt": "hurt",
                "death": "death",
            },
            "layer_prefixes": {
                "base": "",
                "overlay": "overlay_",
                "additive": "add_",
            },
            "_comment": "Override auto-derived action names by mapping original → preferred"
        }

        with open(output_path, 'w') as f:
            json.dump(template, f, indent=2, ensure_ascii=False)
