"""
Enhancement modules for MinecraftModelMigrator-Pro.

Layer 1 Deep: Visual & animation fidelity enhancements beyond core conversion.
"""

from .layer1_deep.overlay_detector import OverlayDetector
from .layer1_deep.firstperson_detector import FirstPersonDetector
from .layer1_deep.particle_detector import ParticleDetector
from .layer1_deep.sound_keyframe_filler import SoundKeyframeFiller
from .layer1_deep.animation_naming_manager import AnimationNamingManager
from .layer1_deep.animation_reference_validator import AnimationReferenceValidator

__all__ = [
    'OverlayDetector',
    'FirstPersonDetector',
    'ParticleDetector',
    'SoundKeyframeFiller',
    'AnimationNamingManager',
    'AnimationReferenceValidator',
]
