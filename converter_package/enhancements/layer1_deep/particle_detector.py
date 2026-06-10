#!/usr/bin/env python3
"""
ParticleDetector - Particle Mounting Point Detection
=====================================================
Detects world.spawnParticle calls and bone position calculations in the
original MC 1.12.2 Java source code. Outputs particle keyframe
placeholders in the animation JSON and a particle_hints.json file for
manual configuration.

Detection patterns:
  - world.spawnParticle / worldObj.spawnParticle calls
  - Particle parameter extraction (x, y, z, dx, dy, dz, particle type)
  - Bone position-based particle origins (posX/posY/posZ + offsets)
  - Entity state-dependent particle spawning (isOnFire, attackPhase, etc.)
  - Random particle distribution patterns

Output:
  - particle_keyframes: GeckoLib particle_effects keyframe placeholders
  - particle_hints: JSON-serializable particle mounting point specifications
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import re


@dataclass
class ParticleMountPoint:
    """A detected particle mounting point."""
    name: str
    """Unique identifier for this particle mount."""
    particle_type: str
    """MC particle type name (e.g. 'FLAME', 'SMOKE', 'PORTAL')."""
    bone_name: str
    """GeckoLib bone name where the particle originates (empty = root)."""
    offset: List[float]
    """Local offset from the bone pivot [x, y, z]."""
    spread: List[float]
    """Spread/delta values [dx, dy, dz]."""
    speed: float
    """Particle speed."""
    count: int
    """Number of particles per spawn call."""
    trigger_condition: str
    """Condition for spawning (e.g. 'always', 'isOnFire', 'attackPhase==1')."""
    source_line: str
    """Original Java code line (for reference)."""
    animation_time: Optional[float]
    """Time in seconds for keyframe placement (None = continuous)."""


@dataclass
class ParticleHint:
    """Simplified particle hint for JSON output."""
    name: str
    particle_type: str
    bone_name: str
    offset: List[float]
    trigger_condition: str
    geckolib_effect: str
    """GeckoLib particle effect string for .animation.json."""


@dataclass
class ParticleDetectionResult:
    """Result of particle mounting point detection."""
    mount_points: List[ParticleMountPoint]
    """Detected particle mounting points."""
    particle_hints: List[ParticleHint]
    """Simplified hints for JSON output."""
    particle_keyframes: List[dict]
    """GeckoLib particle_effects keyframe placeholders for animation JSON."""
    warnings: List[str]
    """Non-fatal warnings."""
    has_particles: bool
    """Whether any particle spawning was detected."""


class ParticleDetector:
    """
    Detects particle mounting points from MC 1.12.2 Java source code
    and generates GeckoLib-compatible particle effect specifications.
    """

    # Pattern: world.spawnParticle calls
    SPAWN_PARTICLE_PATTERN = re.compile(
        r'(\w+)\.spawnParticle\s*\(\s*'
        r'(?:EnumParticleTypes\.)?(\w+)\s*,'
        r'\s*([0-9.fF\+\-\*\/\(\)\s]+?)\s*,'
        r'\s*([0-9.fF\+\-\*\/\(\)\s]+?)\s*,'
        r'\s*([0-9.fF\+\-\*\/\(\)\s]+?)\s*,'
        r'\s*([0-9.fF\+\-\*\/\(\)\s]+?)\s*,'
        r'\s*([0-9.fF\+\-\*\/\(\)\s]+?)\s*,'
        r'\s*([0-9.fF\+\-\*\/\(\)\s]+?)\s*'
        r'(?:,\s*(\d+)\s*)?'  # optional count parameter
        r'(?:,\s*([0-9.fF\+\-\*\s]+)\s*)?'  # optional speed
        r'(?:,\s*([^\)]*?)\s*)?\)'  # optional additional args
    )

    # Pattern: Simplified spawnParticle (fewer args)
    SPAWN_PARTICLE_SIMPLE = re.compile(
        r'(\w+)\.(?:spawnParticle|addParticle|sendParticle)\s*\(\s*'
        r'"?(\w+)"?\s*,'
        r'\s*([0-9.fF\+\-\*\/\(\)entity\s]+?)\s*,'
        r'\s*([0-9.fF\+\-\*\/\(\)entity\s]+?)\s*,'
        r'\s*([0-9.fF\+\-\*\/\(\)entity\s]+?)\s*'
    )

    # Pattern: Entity position + offset calculations
    POSITION_OFFSET_PATTERN = re.compile(
        r'(?:entity\.)?(?:posX|field_70165_t)\s*([+\-])\s*([0-9.fF]+)'
        r'|(?:entity\.)?(?:posY|field_70163_u)\s*([+\-])\s*([0-9.fF]+)'
        r'|(?:entity\.)?(?:posZ|field_70161_v)\s*([+\-])\s*([0-9.fF]+)'
    )

    # Pattern: Entity state conditions near particle calls
    STATE_CONDITION_PATTERN = re.compile(
        r'if\s*\(\s*(?:entity\.)?(\w+)\s*(?:==|!=|>|<|>=|<=)\s*([^\)]+)\)'
        r'|if\s*\(\s*(?:entity\.)?(isOnFire|isAttacking|isMoving|isAlive)\s*\)',
        re.MULTILINE
    )

    # Common particle type mappings (1.12.2 → 1.20.1)
    PARTICLE_TYPE_MAP = {
        'FLAME': 'minecraft:flame',
        'SMOKE_NORMAL': 'minecraft:smoke',
        'SMOKE_LARGE': 'minecraft:large_smoke',
        'PORTAL': 'minecraft:portal',
        'REDSTONE': 'minecraft:dust',
        'SPELL': 'minecraft:effect',
        'MOB_SPELL': 'minecraft:entity_effect',
        'DRIP_LAVA': 'minecraft:dripping_lava',
        'DRIP_WATER': 'minecraft:dripping_water',
        'ENCHANTMENT_TABLE': 'minecraft:enchant',
        'HEART': 'minecraft:heart',
        'VILLAGER_HAPPY': 'minecraft:happy_villager',
        'TOWN_AURA': 'minecraft:town_aura',
        'CLOUD': 'minecraft:cloud',
        'SNOWBALL': 'minecraft:snowflake',
        'EXPLOSION_NORMAL': 'minecraft:poof',
        'EXPLOSION_LARGE': 'minecraft:explosion',
        'CRIT': 'minecraft:crit',
        'MAGIC_CRIT': 'minecraft:magic_crit',
    }

    # Bone name patterns for particle origin inference
    BONE_PARTICLE_PATTERNS = {
        'head': ['head', 'skull', 'face', 'mouth'],
        'body': ['body', 'torso', 'chest', 'core'],
        'feet': ['foot', 'feet', 'leg', 'hoof'],
        'tail': ['tail', 'appendage'],
        'wing': ['wing', 'fin'],
        'hand': ['hand', 'arm', 'claw'],
    }

    def __init__(self, bone_mapping: Dict[str, str]):
        """
        Args:
            bone_mapping: Mapping from Java variable names to GeckoLib bone names.
        """
        self.bone_mapping = bone_mapping
        # Reverse mapping: bone_name → java_var
        self.bone_to_java = {v: k for k, v in bone_mapping.items()}

    def detect(self, renderer_java: str, model_java: str = "",
               entity_java: str = "") -> ParticleDetectionResult:
        """
        Detect particle mounting points in Java source code.

        Args:
            renderer_java: Source code of the Renderer class.
            model_java: Source code of the Model class (optional).
            entity_java: Source code of the Entity class (optional, for state conditions).

        Returns:
            ParticleDetectionResult with mount points, hints, and keyframes.
        """
        mount_points: List[ParticleMountPoint] = []
        particle_hints: List[ParticleHint] = []
        particle_keyframes: List[dict] = []
        warnings: List[str] = []

        combined_source = "\n".join([renderer_java, model_java, entity_java])

        # --- Detect spawnParticle calls ---
        spawn_matches = self.SPAWN_PARTICLE_PATTERN.findall(combined_source)
        if not spawn_matches:
            # Try simplified pattern
            spawn_matches_simple = self.SPAWN_PARTICLE_SIMPLE.findall(combined_source)
            for sm in spawn_matches_simple:
                mount_points.append(self._parse_simple_particle(sm, len(mount_points)))
        else:
            for sm in spawn_matches:
                mount_points.append(self._parse_full_particle(sm, len(mount_points)))

        # --- Detect position offsets ---
        position_offsets = self.POSITION_OFFSET_PATTERN.findall(combined_source)

        # --- Detect state conditions ---
        state_conditions = self.STATE_CONDITION_PATTERN.findall(combined_source)

        # --- Generate hints and keyframes ---
        for mp in mount_points:
            # Generate GeckoLib effect string
            geckolib_effect = self.PARTICLE_TYPE_MAP.get(
                mp.particle_type, f"srparasites:{mp.particle_type.lower()}"
            )

            hint = ParticleHint(
                name=mp.name,
                particle_type=mp.particle_type,
                bone_name=mp.bone_name,
                offset=mp.offset,
                trigger_condition=mp.trigger_condition,
                geckolib_effect=geckolib_effect
            )
            particle_hints.append(hint)

            # Generate keyframe placeholder
            if mp.animation_time is not None:
                particle_keyframes.append({
                    'time': mp.animation_time,
                    'effect': geckolib_effect,
                    'locator': mp.bone_name if mp.bone_name else 'root',
                    'type': 'particle'
                })

        # --- Infer bone associations for particles without bones ---
        for mp in mount_points:
            if not mp.bone_name:
                mp.bone_name = self._infer_bone_from_offset(mp.offset)

        # --- Apply state conditions ---
        if state_conditions and mount_points:
            for mp in mount_points:
                if mp.trigger_condition == 'always':
                    # Try to associate with a nearby condition
                    for cond in state_conditions:
                        cond_name = cond[0] if cond[0] else cond[2] if len(cond) > 2 else ""
                        if cond_name:
                            mp.trigger_condition = f"entity.{cond_name}"
                            break

        has_particles = len(mount_points) > 0

        if has_particles and not particle_keyframes:
            # Generate continuous particle keyframe at t=0
            for mp in mount_points[:5]:  # Limit to first 5
                geckolib_effect = self.PARTICLE_TYPE_MAP.get(
                    mp.particle_type, f"srparasites:{mp.particle_type.lower()}"
                )
                particle_keyframes.append({
                    'time': 0.0,
                    'effect': geckolib_effect,
                    'locator': mp.bone_name if mp.bone_name else 'root',
                    'type': 'particle'
                })

        return ParticleDetectionResult(
            mount_points=mount_points,
            particle_hints=particle_hints,
            particle_keyframes=particle_keyframes,
            warnings=warnings,
            has_particles=has_particles
        )

    def _parse_full_particle(self, match, index: int) -> ParticleMountPoint:
        """Parse a full spawnParticle match tuple."""
        world_var = match[0] if match[0] else "world"
        particle_type = match[1] if match[1] else "UNKNOWN"
        x_str = match[2].strip() if len(match) > 2 else "0"
        y_str = match[3].strip() if len(match) > 3 else "0"
        z_str = match[4].strip() if len(match) > 4 else "0"
        dx_str = match[5].strip() if len(match) > 5 else "0"
        dy_str = match[6].strip() if len(match) > 6 else "0"
        dz_str = match[7].strip() if len(match) > 7 else "0"
        count_str = match[8] if len(match) > 8 and match[8] else "1"
        speed_str = match[9] if len(match) > 9 and match[9] else "0"

        # Parse numeric values, defaulting to 0
        offset = [
            self._safe_float(x_str, 0.0),
            self._safe_float(y_str, 0.0),
            self._safe_float(z_str, 0.0)
        ]
        spread = [
            self._safe_float(dx_str, 0.0),
            self._safe_float(dy_str, 0.0),
            self._safe_float(dz_str, 0.0)
        ]

        return ParticleMountPoint(
            name=f"particle_{index}",
            particle_type=particle_type,
            bone_name="",
            offset=offset,
            spread=spread,
            speed=self._safe_float(speed_str, 0.0),
            count=int(self._safe_float(count_str, 1)),
            trigger_condition="always",
            source_line=f"spawnParticle({particle_type}, ...)",
            animation_time=None
        )

    def _parse_simple_particle(self, match, index: int) -> ParticleMountPoint:
        """Parse a simplified spawnParticle match tuple."""
        particle_type = match[1] if len(match) > 1 and match[1] else "UNKNOWN"
        x_str = match[2].strip() if len(match) > 2 else "0"
        y_str = match[3].strip() if len(match) > 3 else "0"
        z_str = match[4].strip() if len(match) > 4 else "0"

        return ParticleMountPoint(
            name=f"particle_{index}",
            particle_type=particle_type,
            bone_name="",
            offset=[
                self._safe_float(x_str, 0.0),
                self._safe_float(y_str, 0.0),
                self._safe_float(z_str, 0.0)
            ],
            spread=[0.0, 0.0, 0.0],
            speed=0.0,
            count=1,
            trigger_condition="always",
            source_line=f"spawnParticle({particle_type}, ...)",
            animation_time=None
        )

    def _infer_bone_from_offset(self, offset: List[float]) -> str:
        """Infer which bone a particle originates from based on its offset."""
        if not offset or len(offset) < 3:
            return ""

        # Check against known bone positions in the mapping
        # Heuristic: Y offset > 1.5 blocks → head area, Y < 0 → feet area, etc.
        _, y, _ = offset[0], offset[1], offset[2]

        # Try to match with bone names
        for bone_name in self.bone_mapping.values():
            lower_name = bone_name.lower()
            for category, keywords in self.BONE_PARTICLE_PATTERNS.items():
                if any(kw in lower_name for kw in keywords):
                    if category == 'head' and y > 1.5:
                        return bone_name
                    elif category == 'feet' and y < 0.5:
                        return bone_name

        return ""

    @staticmethod
    def _safe_float(s: str, default: float) -> float:
        """Safely parse a float from a string that may contain Java expressions."""
        s = s.strip().rstrip('fF')
        try:
            return float(s)
        except ValueError:
            return default

    def to_particle_hints_json(self, result: ParticleDetectionResult) -> dict:
        """
        Convert particle detection result to a particle_hints.json-compatible dict.

        Args:
            result: The ParticleDetectionResult to serialize.

        Returns:
            Dict suitable for JSON serialization as particle_hints.json.
        """
        return {
            'particle_mount_points': [
                {
                    'name': hint.name,
                    'particle_type': hint.particle_type,
                    'geckolib_effect': hint.geckolib_effect,
                    'bone_name': hint.bone_name,
                    'offset': hint.offset,
                    'trigger_condition': hint.trigger_condition,
                }
                for hint in result.particle_hints
            ],
            'keyframe_count': len(result.particle_keyframes),
            'warnings': result.warnings
        }
