#!/usr/bin/env python3
"""
KeyframeEventMarker - Keyframe Event Detection & Migration
============================================================
Detects animation events from MC 1.12.2 Java source code and marks
them as GeckoLib keyframe events in the animation JSON.

GeckoLib supports the following keyframe event types:
  - SoundKeyframe: Triggers a sound at a specific time
  - ParticleKeyframe: Spawns a particle effect at a specific time
  - CustomInstructionKeyframe: Executes custom logic at a specific time

In MC 1.12.2, these are typically implemented as:
  - playSound() calls inside setRotationAngles with timing conditions
  - spawnParticle() calls at specific animation phases
  - Conditional attack box activation at specific frames

Detection is best-effort. Failures produce warnings, never exceptions.
Does NOT modify core_math.py or existing converter modules.
"""

import re
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class KeyframeEvent:
    """A detected keyframe event."""
    time: float = 0.0  # Time in seconds
    event_type: str = ""  # "sound", "particle", "custom_instruction"
    name: str = ""  # Event identifier
    data: str = ""  # Additional data (sound name, particle type, etc.)
    bone_name: str = ""  # Associated bone (if any)
    source_expression: str = ""  # Original Java expression that triggered detection


@dataclass
class EventDetectionResult:
    """Complete result from keyframe event detection."""
    events: List[KeyframeEvent] = field(default_factory=list)
    sound_effects: List[Dict] = field(default_factory=list)
    particle_effects: List[Dict] = field(default_factory=list)
    event_markers: List[Dict] = field(default_factory=list)
    geckolib_events_json: Dict = field(default_factory=dict)  # GeckoLib format events
    warnings: List[str] = field(default_factory=list)


# ============================================================================
# KeyframeEventMarker
# ============================================================================

class KeyframeEventMarker:
    """
    Detects animation events from Java source and marks them in animation JSON.

    Detection patterns:
      1. Sound effects: world.playSound() or entity.playSound() calls
      2. Particle effects: world.spawnParticle() or WorldServer.spawnParticle()
      3. Attack frames: attackKey/attackTime conditional logic
      4. Custom instructions: conditional setRotationAngle changes at specific times

    All detection is best-effort with warnings on failure.
    """

    # Sound event patterns
    SOUND_PATTERNS = [
        re.compile(r'world\.playSound\s*\(', re.IGNORECASE),
        re.compile(r'entity\.playSound\s*\(', re.IGNORECASE),
        re.compile(r'((?:\w+)\.)?func_184133_a\s*\(', re.IGNORECASE),  # playSound SRG
        re.compile(r'((?:\w+)\.)?playSound\s*\(\s*[^,]+,\s*[^,]+,\s*(\w+SoundEvents\.\w+)', re.IGNORECASE),
    ]

    # Particle event patterns
    PARTICLE_PATTERNS = [
        re.compile(r'world\.spawnParticle\s*\(', re.IGNORECASE),
        re.compile(r'((?:\w+)\.)?func_175688_a\s*\(', re.IGNORECASE),  # spawnParticle SRG
        re.compile(r'ServerParticle', re.IGNORECASE),
        re.compile(r'EnumParticleTypes\.\w+', re.IGNORECASE),
    ]

    # Attack frame patterns
    ATTACK_PATTERNS = [
        re.compile(r'attackTime\s*>\s*0', re.IGNORECASE),
        re.compile(r'attackTime\s*==\s*0', re.IGNORECASE),
        re.compile(r'isAttacking\s*\(\s*\)', re.IGNORECASE),
        re.compile(r'attackPhase', re.IGNORECASE),
    ]

    def __init__(self, bone_mapping: Dict[str, str] = None):
        """
        Args:
            bone_mapping: Dict mapping 1.12.2 java var names to GeckoLib bone IDs
        """
        self.bone_mapping = bone_mapping or {}
        self._warnings: List[str] = []

    def detect(self, animation_json: dict, java_source: str = "") -> EventDetectionResult:
        """
        Detect keyframe events from Java source and animation data.

        Args:
            animation_json: The .animation.json structure (for timing reference)
            java_source: The Java source code (Model or Render class)

        Returns:
            EventDetectionResult with all detected events and GeckoLib format
        """
        result = EventDetectionResult()

        if not java_source:
            result.warnings.append("No Java source provided for event detection")
            return result

        # Get animation length for timing reference
        anim_length = self._get_animation_length(animation_json)

        # 1. Detect sound events
        sound_events = self._detect_sound_events(java_source, anim_length)
        result.sound_effects = [
            {"name": e.name, "time": e.time, "sound": e.data, "bone": e.bone_name}
            for e in sound_events
        ]

        # 2. Detect particle events
        particle_events = self._detect_particle_events(java_source, anim_length)
        result.particle_effects = [
            {"name": e.name, "time": e.time, "particle": e.data, "bone": e.bone_name}
            for e in particle_events
        ]

        # 3. Detect attack frame events
        attack_events = self._detect_attack_events(java_source, anim_length)

        # Combine all events
        all_events = sound_events + particle_events + attack_events
        all_events.sort(key=lambda e: e.time)

        result.events = all_events
        result.event_markers = [
            {"time": e.time, "type": e.event_type, "name": e.name,
             "data": e.data, "bone": e.bone_name}
            for e in all_events
        ]

        # Generate GeckoLib format events
        result.geckolib_events_json = self._generate_geckolib_events(all_events, animation_json)

        result.warnings = self._warnings
        return result

    def _get_animation_length(self, animation_json: dict) -> float:
        """Extract animation length from animation JSON."""
        if not animation_json:
            return 6.2832  # Default 2π
        animations = animation_json.get('animations', {})
        for anim_name, anim_data in animations.items():
            return anim_data.get('animation_length', 6.2832)
        return 6.2832

    def _detect_sound_events(self, source: str, anim_length: float) -> List[KeyframeEvent]:
        """
        Detect sound effect triggers from Java source.

        Looks for playSound() calls, especially those inside animation methods
        that are conditional on timing variables.
        """
        events = []
        seen_positions = set()  # Track match positions to avoid duplicates

        # Find playSound calls
        for pattern in self.SOUND_PATTERNS:
            for match in pattern.finditer(source):
                # Deduplicate: same match position from overlapping patterns
                if match.start() in seen_positions:
                    continue
                seen_positions.add(match.start())

                # Extract context around the call
                start = max(0, match.start() - 300)
                context = source[start:match.start()]

                # Try to determine timing from context
                time = self._extract_timing_from_context(context, anim_length)

                # Try to extract sound event name
                sound_name = self._extract_sound_name(source[match.start():match.start() + 200])

                # Try to find associated bone
                bone_name = self._extract_bone_from_context(context)

                event = KeyframeEvent(
                    time=time,
                    event_type="sound",
                    name=f"sound_{len(events)}",
                    data=sound_name or "minecraft:entity.generic.ambient",
                    bone_name=bone_name,
                    source_expression=match.group(0)
                )
                events.append(event)

        return events

    def _detect_particle_events(self, source: str, anim_length: float) -> List[KeyframeEvent]:
        """
        Detect particle effect triggers from Java source.

        Looks for spawnParticle() calls.
        """
        events = []
        seen_positions = set()  # Track match positions to avoid duplicates

        for pattern in self.PARTICLE_PATTERNS:
            for match in pattern.finditer(source):
                # Deduplicate: same match position from overlapping patterns
                if match.start() in seen_positions:
                    continue
                seen_positions.add(match.start())

                start = max(0, match.start() - 300)
                context = source[start:match.start()]

                time = self._extract_timing_from_context(context, anim_length)

                # Extract particle type
                particle_type = "generic"
                particle_match = re.search(r'EnumParticleTypes\.(\w+)', source[match.start():match.start() + 200])
                if particle_match:
                    particle_type = particle_match.group(1)

                bone_name = self._extract_bone_from_context(context)

                event = KeyframeEvent(
                    time=time,
                    event_type="particle",
                    name=f"particle_{len(events)}",
                    data=particle_type,
                    bone_name=bone_name,
                    source_expression=match.group(0)
                )
                events.append(event)

        return events

    def _detect_attack_events(self, source: str, anim_length: float) -> List[KeyframeEvent]:
        """
        Detect attack frame events from Java source.

        Looks for attackTime/attackPhase conditional logic that defines
        when an entity's attack hitbox is active.
        """
        events = []
        seen_positions = set()  # Track match positions to avoid duplicates

        for pattern in self.ATTACK_PATTERNS:
            for match in pattern.finditer(source):
                # Deduplicate: same match position from overlapping patterns
                if match.start() in seen_positions:
                    continue
                seen_positions.add(match.start())

                start = max(0, match.start() - 200)
                context = source[start:match.start() + 100]

                # Attack events typically occur at specific animation phases
                # Common timing: first 1/3 of walk cycle or at specific tick counts
                time = 0.0  # Default to start

                # Try to extract timing
                if 'attackTime > 0' in context:
                    # Active during hurt frames
                    time = anim_length * 0.1  # Early in animation
                elif 'attackPhase' in context:
                    # Phase-based attack
                    phase_match = re.search(r'attackPhase\s*==\s*(\d+)', context)
                    if phase_match:
                        phase = int(phase_match.group(1))
                        time = anim_length * (phase / 3.0)

                event = KeyframeEvent(
                    time=time,
                    event_type="custom_instruction",
                    name="attack_frame",
                    data="attack_hitbox_active",
                    bone_name="",
                    source_expression=match.group(0)
                )
                events.append(event)

        return events

    def _extract_timing_from_context(self, context: str, anim_length: float) -> float:
        """
        Try to determine event timing from surrounding code context.

        Looks for ageInTicks-based timing conditions or tick count checks.
        """
        # Pattern: if (ageInTicks % N == 0) → time = period / N
        modulo_pattern = re.search(r'ageInTicks\s*%\s*(\d+)\s*==\s*0', context)
        if modulo_pattern:
            period = int(modulo_pattern.group(1))
            return (period / 20.0) % anim_length  # Ticks to seconds

        # Pattern: hurtTime > 0 → time = 0 (hurt start)
        if 'hurtTime > 0' in context:
            return 0.0

        # Pattern: specific tick count
        tick_pattern = re.search(r'tickCount\s*==\s*(\d+)', context)
        if tick_pattern:
            return int(tick_pattern.group(1)) / 20.0

        # Default: start of animation
        return 0.0

    def _extract_sound_name(self, text: str) -> str:
        """Try to extract a sound event name from playSound call context."""
        # Pattern: SoundEvents.ENTITY_XXX
        sound_match = re.search(r'SoundEvents\.(\w+)', text)
        if sound_match:
            return f"minecraft:{sound_match.group(1).lower().replace('_', '.')}"
        return ""

    def _extract_bone_from_context(self, context: str) -> str:
        """Try to extract a bone name from surrounding context."""
        # Look for bone variable references
        bone_refs = re.findall(r'this\.(\w+)\.(?:field_78795_f|field_78796_g|field_78808_h|rotateAngle[XYZ])', context)
        if bone_refs:
            return self.bone_mapping.get(bone_refs[-1], bone_refs[-1])
        return ""

    def _generate_geckolib_events(self, events: List[KeyframeEvent],
                                   animation_json: dict) -> Dict:
        """
        Generate GeckoLib format keyframe events structure.

        GeckoLib .animation.json can include sound_keyframes and
        particle_keyframes arrays in animation data.
        """
        result = {}

        if not events:
            return result

        # Group events by animation name
        animations = animation_json.get('animations', {})
        anim_name = list(animations.keys())[0] if animations else "animation.model.idle"

        sound_keyframes = []
        particle_keyframes = []
        custom_keyframes = []

        for event in events:
            if event.event_type == "sound":
                sound_keyframes.append({
                    "time": round(event.time, 4),
                    "effect": event.data
                })
            elif event.event_type == "particle":
                particle_keyframes.append({
                    "time": round(event.time, 4),
                    "effect": event.data,
                    "locator": event.bone_name or "root"
                })
            elif event.event_type == "custom_instruction":
                custom_keyframes.append({
                    "time": round(event.time, 4),
                    "instruction": event.data
                })

        if sound_keyframes or particle_keyframes or custom_keyframes:
            result[anim_name] = {}
            if sound_keyframes:
                result[anim_name]["sound_effects"] = sound_keyframes
            if particle_keyframes:
                result[anim_name]["particle_effects"] = particle_keyframes
            if custom_keyframes:
                # Aggregate events at the same time into lists
                timeline = {}
                for e in custom_keyframes:
                    time_key = str(round(e["time"], 4))
                    if time_key not in timeline:
                        timeline[time_key] = []
                    timeline[time_key].append(e["instruction"])
                result[anim_name]["timeline"] = timeline

        return result
