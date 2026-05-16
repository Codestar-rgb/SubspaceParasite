#!/usr/bin/env python3
"""
SoundKeyframeFiller - Sound Keyframe Auto-Fill
================================================
Automatically fills GeckoLib SoundKeyframe entries by mapping detected
sound events from MC 1.12.2 Java source code to 1.20.1-style sound paths.

Capabilities:
  - Detect playSound / world.playSound calls in Java source
  - Map MC 1.12.2 sound event names to 1.20.1 resource paths
  - Generate GeckoLib SoundKeyframe format entries for animation JSON
  - Handle mod-specific sound paths (srparasites: prefix)
  - Provide timing estimation from code context (attack phase, animation cycle)
  - Fallback for unknown sounds with warning annotations

Output:
  - sound_keyframes: GeckoLib sound_effects keyframe entries
  - sound_mapping: Detected sound event mapping (original → 1.20.1)
  - warnings: Non-fatal warnings for unmapped sounds
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import re


@dataclass
class SoundKeyframe:
    """A GeckoLib sound keyframe entry."""
    time: float
    """Time in seconds within the animation."""
    effect: str
    """GeckoLib sound effect path (e.g. 'minecraft:entity.zombie.hurt')."""
    original_sound: str
    """Original MC 1.12.2 sound event name."""
    volume: float
    """Sound volume (0.0-1.0)."""
    pitch: float
    """Sound pitch multiplier."""
    source: str
    """Sound source category (master, music, hostile, etc.)."""


@dataclass
class SoundMapping:
    """A detected sound event mapping."""
    original: str
    """Original sound event name from 1.12.2 code."""
    mapped: str
    """Mapped 1.20.1-style sound path."""
    is_exact: bool
    """Whether the mapping is exact (True) or heuristic (False)."""
    context: str
    """Code context where the sound was found."""


@dataclass
class SoundFillResult:
    """Result of sound keyframe auto-fill."""
    sound_keyframes: List[SoundKeyframe]
    """Generated GeckoLib sound keyframes."""
    sound_mapping: List[SoundMapping]
    """Detected sound event mappings."""
    warnings: List[str]
    """Non-fatal warnings for unmapped or ambiguous sounds."""
    has_sounds: bool
    """Whether any sound events were detected."""


class SoundKeyframeFiller:
    """
    Automatically fills GeckoLib SoundKeyframe entries from MC 1.12.2
    Java source code by detecting playSound calls and mapping them to
    1.20.1-style sound paths.
    """

    # Pattern: world.playSound calls
    PLAY_SOUND_PATTERN = re.compile(
        r'(?:\w+)\.playSound\s*\(\s*'
        r'(?:null|entity|player|this)\s*,\s*'
        r'(?:entity\.)?(?:posX|field_70165_t)\s*,\s*'
        r'(?:entity\.)?(?:posY|field_70163_u)\s*,\s*'
        r'(?:entity\.)?(?:posZ|field_70161_v)\s*,\s*'
        r'(?:SoundEvents|SoundEvent)\s*\.\s*(\w+)\s*,\s*'
        r'(?:SoundCategory|SoundSource)\s*\.\s*(\w+)\s*,\s*'
        r'([0-9.fF]+)\s*,\s*([0-9.fF]+)'
    )

    # Pattern: playSound with ResourceLocation
    PLAY_SOUND_RESOURCE_PATTERN = re.compile(
        r'(?:\w+)\.playSound\s*\([^,]*,\s*'
        r'new\s+ResourceLocation\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)'
    )

    # Pattern: playSound with string literal
    PLAY_SOUND_STRING_PATTERN = re.compile(
        r'(?:\w+)\.playSound\s*\([^,]*,\s*"([^"]+)"\s*,\s*"([^"]+)"'
    )

    # Pattern: SoundEvents field references
    SOUND_EVENTS_PATTERN = re.compile(
        r'SoundEvents\.\s*(\w+)'
    )

    # Pattern: Entity attack/interaction sound methods
    ENTITY_SOUND_METHODS = re.compile(
        r'(?:getHurtSound|getDeathSound|getAmbientSound|getAttackSound|getStepSound)\s*\(\s*\)'
    )

    # Common MC 1.12.2 → 1.20.1 sound event mappings
    SOUND_MAP: Dict[str, str] = {
        # Generic entity sounds
        'ENTITY_GENERIC_HURT': 'minecraft:entity.generic.hurt',
        'ENTITY_GENERIC_DEATH': 'minecraft:entity.generic.death',
        'ENTITY_GENERIC_EXPLODE': 'minecraft:entity.generic.explode',
        'ENTITY_GENERIC_BURN': 'minecraft:entity.generic.burn',
        'ENTITY_GENERIC_DRINK': 'minecraft:entity.generic.drink',
        'ENTITY_GENERIC_EAT': 'minecraft:entity.generic.eat',
        'ENTITY_GENERIC_BIG_FALL': 'minecraft:entity.generic.big_fall',
        'ENTITY_GENERIC_SMALL_FALL': 'minecraft:entity.generic.small_fall',
        'ENTITY_GENERIC_SPLASH': 'minecraft:entity.generic.splash',
        'ENTITY_GENERIC_SWIM': 'minecraft:entity.generic.swim',

        # Hostile sounds
        'ENTITY_HOSTILE_HURT': 'minecraft:entity.hostile.hurt',
        'ENTITY_HOSTILE_DEATH': 'minecraft:entity.hostile.death',
        'ENTITY_HOSTILE_FALL': 'minecraft:entity.hostile.fall',
        'ENTITY_HOSTILE_SPLASH': 'minecraft:entity.hostile.splash',
        'ENTITY_HOSTILE_SWIM': 'minecraft:entity.hostile.swim',

        # Zombie sounds
        'ENTITY_ZOMBIE_HURT': 'minecraft:entity.zombie.hurt',
        'ENTITY_ZOMBIE_DEATH': 'minecraft:entity.zombie.death',
        'ENTITY_ZOMBIE_AMBIENT': 'minecraft:entity.zombie.ambient',
        'ENTITY_ZOMBIE_ATTACK_IRON_DOOR': 'minecraft:entity.zombie.attack_iron_door',
        'ENTITY_ZOMBIE_BREAK_DOOR_WOOD': 'minecraft:entity.zombie.break_door_wood',
        'ENTITY_ZOMBIE_STEP': 'minecraft:entity.zombie.step',
        'ENTITY_ZOMBIE_INFECT': 'minecraft:entity.zombie.infect',

        # Skeleton sounds
        'ENTITY_SKELETON_HURT': 'minecraft:entity.skeleton.hurt',
        'ENTITY_SKELETON_DEATH': 'minecraft:entity.skeleton.death',
        'ENTITY_SKELETON_AMBIENT': 'minecraft:entity.skeleton.ambient',
        'ENTITY_SKELETON_STEP': 'minecraft:entity.skeleton.step',

        # Blaze sounds
        'ENTITY_BLAZE_HURT': 'minecraft:entity.blaze.hurt',
        'ENTITY_BLAZE_DEATH': 'minecraft:entity.blaze.death',
        'ENTITY_BLAZE_AMBIENT': 'minecraft:entity.blaze.ambient',
        'ENTITY_BLAZE_BURN': 'minecraft:entity.blaze.burn',
        'ENTITY_BLAZE_SHOOT': 'minecraft:entity.blaze.shoot',

        # Enderman sounds
        'ENTITY_ENDERMAN_HURT': 'minecraft:entity.enderman.hurt',
        'ENTITY_ENDERMAN_DEATH': 'minecraft:entity.enderman.death',
        'ENTITY_ENDERMAN_AMBIENT': 'minecraft:entity.enderman.ambient',
        'ENTITY_ENDERMAN_SCREAM': 'minecraft:entity.enderman.scream',
        'ENTITY_ENDERMAN_STARE': 'minecraft:entity.enderman.stare',
        'ENTITY_ENDERMAN_TELEPORT': 'minecraft:entity.enderman.teleport',

        # Fire sounds
        'ITEM_FIRECHARGE_USE': 'minecraft:item.firecharge.use',
        'ENTITY_GHAST_SHOOT': 'minecraft:entity.ghast.shoot',

        # Step sounds
        'BLOCK_STONE_STEP': 'minecraft:block.stone.step',
        'BLOCK_GRASS_STEP': 'minecraft:block.grass.step',
        'BLOCK_GRAVEL_STEP': 'minecraft:block.gravel.step',
        'BLOCK_SAND_STEP': 'minecraft:block.sand.step',
    }

    # Sound source category mapping (1.12.2 → 1.20.1)
    SOURCE_MAP = {
        'MASTER': 'master',
        'MUSIC': 'music',
        'RECORDS': 'music',
        'WEATHER': 'weather',
        'BLOCKS': 'block',
        'HOSTILE': 'hostile',
        'NEUTRAL': 'neutral',
        'PLAYERS': 'player',
        'AMBIENT': 'ambient',
        'VOICE': 'voice',
    }

    def __init__(self, bone_mapping: Dict[str, str], namespace: str = "srparasites"):
        """
        Args:
            bone_mapping: Mapping from Java variable names to GeckoLib bone names.
            namespace: Mod namespace for mod-specific sounds.
        """
        self.bone_mapping = bone_mapping
        self.namespace = namespace

    def detect(self, renderer_java: str, model_java: str = "",
               entity_java: str = "",
               animation_length: float = 6.28) -> SoundFillResult:
        """
        Detect sound events and generate GeckoLib sound keyframes.

        Args:
            renderer_java: Source code of the Renderer class.
            model_java: Source code of the Model class (optional).
            entity_java: Source code of the Entity class (optional).
            animation_length: Animation length in seconds (for timing estimation).

        Returns:
            SoundFillResult with keyframes, mappings, and warnings.
        """
        sound_keyframes: List[SoundKeyframe] = []
        sound_mapping: List[SoundMapping] = []
        warnings: List[str] = []

        combined_source = "\n".join([renderer_java, model_java, entity_java])

        # --- Detect playSound with SoundEvents ---
        play_sound_matches = self.PLAY_SOUND_PATTERN.findall(combined_source)
        for psm in play_sound_matches:
            sound_event_name = psm[0] if psm[0] else "UNKNOWN"
            source_category = psm[1] if len(psm) > 1 else "HOSTILE"
            volume_str = psm[2] if len(psm) > 2 else "1.0f"
            pitch_str = psm[3] if len(psm) > 3 else "1.0f"

            mapped_sound = self.SOUND_MAP.get(sound_event_name, None)
            is_exact = mapped_sound is not None

            if not mapped_sound:
                # Try heuristic mapping
                mapped_sound = self._heuristic_map(sound_event_name)

            if not mapped_sound:
                mapped_sound = f"{self.namespace}:{sound_event_name.lower()}"
                warnings.append(
                    f"Unknown sound event '{sound_event_name}'. Using fallback: {mapped_sound}"
                )

            try:
                volume = float(volume_str.rstrip('fF'))
            except ValueError:
                volume = 1.0
            try:
                pitch = float(pitch_str.rstrip('fF'))
            except ValueError:
                pitch = 1.0

            sound_mapping.append(SoundMapping(
                original=sound_event_name,
                mapped=mapped_sound,
                is_exact=is_exact,
                context=f"playSound(SoundEvents.{sound_event_name})"
            ))

            # Estimate timing (distribute evenly if multiple sounds)
            estimated_time = 0.0
            if len(play_sound_matches) > 1:
                idx = play_sound_matches.index(psm)
                estimated_time = (idx / len(play_sound_matches)) * animation_length

            sound_keyframes.append(SoundKeyframe(
                time=estimated_time,
                effect=mapped_sound,
                original_sound=sound_event_name,
                volume=volume,
                pitch=pitch,
                source=self.SOURCE_MAP.get(source_category, 'hostile')
            ))

        # --- Detect playSound with ResourceLocation ---
        resource_matches = self.PLAY_SOUND_RESOURCE_PATTERN.findall(combined_source)
        for rm in resource_matches:
            namespace = rm[0] if rm[0] else self.namespace
            path = rm[1] if rm[1] else "unknown"
            mapped_sound = f"{namespace}:{path}"

            sound_mapping.append(SoundMapping(
                original=f"{namespace}:{path}",
                mapped=mapped_sound,
                is_exact=True,
                context=f"playSound(ResourceLocation({namespace}, {path}))"
            ))

            sound_keyframes.append(SoundKeyframe(
                time=0.0,
                effect=mapped_sound,
                original_sound=f"{namespace}:{path}",
                volume=1.0,
                pitch=1.0,
                source='hostile'
            ))

        # --- Detect SoundEvents field references (without playSound context) ---
        sound_events_matches = self.SOUND_EVENTS_PATTERN.findall(combined_source)
        for sem in sound_events_matches:
            # Skip if already mapped from playSound
            if any(sm.original == sem for sm in sound_mapping):
                continue

            mapped_sound = self.SOUND_MAP.get(sem, f"{self.namespace}:{sem.lower()}")
            is_exact = sem in self.SOUND_MAP

            sound_mapping.append(SoundMapping(
                original=sem,
                mapped=mapped_sound,
                is_exact=is_exact,
                context=f"SoundEvents.{sem} (reference only, no playSound context)"
            ))

        # --- Detect entity sound method overrides ---
        entity_sound_methods = self.ENTITY_SOUND_METHODS.findall(combined_source)
        for esm in entity_sound_methods:
            method_name = esm.replace('get', '').replace('Sound', '').lower()
            if method_name == 'hurt':
                mapped = f"{self.namespace}:entity.hostile.hurt"
                time = 0.0
            elif method_name == 'death':
                mapped = f"{self.namespace}:entity.hostile.death"
                time = 0.0
            elif method_name == 'ambient':
                mapped = f"{self.namespace}:entity.hostile.ambient"
                time = animation_length * 0.5
            elif method_name == 'attack':
                mapped = f"{self.namespace}:entity.hostile.attack"
                time = animation_length * 0.25
            elif method_name == 'step':
                mapped = f"{self.namespace}:entity.hostile.step"
                time = animation_length * 0.5
            else:
                mapped = f"{self.namespace}:entity.{method_name}"
                time = 0.0

            sound_keyframes.append(SoundKeyframe(
                time=time,
                effect=mapped,
                original_sound=esm,
                volume=1.0,
                pitch=1.0,
                source='hostile'
            ))

        # --- Sort keyframes by time ---
        sound_keyframes.sort(key=lambda kf: kf.time)

        has_sounds = len(sound_keyframes) > 0

        return SoundFillResult(
            sound_keyframes=sound_keyframes,
            sound_mapping=sound_mapping,
            warnings=warnings,
            has_sounds=has_sounds
        )

    def _heuristic_map(self, sound_event_name: str) -> Optional[str]:
        """
        Attempt heuristic mapping of a sound event name to a 1.20.1 path.

        Rules:
          1. ENTITY_* → minecraft:entity.<name>
          2. BLOCK_* → minecraft:block.<name>
          3. ITEM_* → minecraft:item.<name>
          4. Mod-specific patterns → <namespace>:<lowercase_name>
        """
        name = sound_event_name

        if name.startswith("ENTITY_"):
            entity_part = name[7:].lower()
            return f"minecraft:entity.{entity_part}"
        elif name.startswith("BLOCK_"):
            block_part = name[6:].lower()
            return f"minecraft:block.{block_part}"
        elif name.startswith("ITEM_"):
            item_part = name[5:].lower()
            return f"minecraft:item.{item_part}"

        return None

    def to_animation_json_sound_effects(self, result: SoundFillResult) -> List[dict]:
        """
        Convert sound keyframes to GeckoLib animation.json sound_effects format.

        Returns:
            List of dicts suitable for embedding in animation JSON:
            [{"time": 0.5, "effect": "minecraft:entity.zombie.hurt"}, ...]
        """
        return [
            {
                'time': kf.time,
                'effect': kf.effect,
            }
            for kf in result.sound_keyframes
        ]
