#!/usr/bin/env python3
"""
FirstPersonDetector - First-Person Handheld Transform Detection & Conversion
=============================================================================
Detects ItemRenderer-related code, held item display transforms, and
first-person rendering adjustments in the original MC 1.12.2 Java code.
Outputs display preset specifications or annotation comments for manual
adjustment.

Detection patterns:
  - ItemRenderer / RenderItem references
  - Held item transform (ItemTransformVec3f / TRSRTransformation)
  - First-person arm rendering (RenderPlayer arm modifications)
  - Item display overrides (ModelResourceLocation "inventory" variants)
  - Held item bone rotations (specific bone transforms for item holding)

Output:
  - display_presets: dict of display settings per perspective
  - held_item_bones: bones used for item holding
  - first_person_hints: annotation strings for manual adjustment
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import re


@dataclass
class DisplayPreset:
    """A display preset for item rendering (MC model format)."""
    perspective: str
    """Third-person, first-person, gui, ground, head, fixed."""
    rotation: List[float]
    """[rx, ry, rz] rotation in degrees."""
    translation: List[float]
    """[tx, ty, tz] translation."""
    scale: List[float]
    """[sx, sy, sz] scale."""


@dataclass
class HeldItemBone:
    """A bone configured for held item display."""
    bone_name: str
    """GeckoLib bone name."""
    item_type: str
    """'main_hand', 'off_hand', 'both_hands'."""
    transform_code: str
    """Java code snippet for the bone transform."""


@dataclass
class FirstPersonDetectionResult:
    """Result of first-person / held item detection."""
    display_presets: List[DisplayPreset]
    """Display presets for item perspectives."""
    held_item_bones: List[HeldItemBone]
    """Bones used for holding items."""
    first_person_hints: List[str]
    """Annotation strings for manual first-person adjustments."""
    has_held_item: bool
    """Whether held item rendering was detected."""
    warnings: List[str]
    """Non-fatal warnings."""


class FirstPersonDetector:
    """
    Detects first-person handheld transform and held item rendering
    patterns in MC 1.12.2 Java source code.
    """

    # Pattern: ItemRenderer / RenderItem references
    ITEM_RENDERER_PATTERN = re.compile(
        r'ItemRenderer|RenderItem|Minecraft\.getItemRenderer'
        r'|mc\.getItemRenderer'
    )

    # Pattern: Held item bone names (common conventions)
    HELD_ITEM_BONE_PATTERNS = [
        re.compile(r'(?:right|left|main|off)[_]?hand', re.IGNORECASE),
        re.compile(r'(?:right|left|main|off)[_]?arm', re.IGNORECASE),
        re.compile(r'held[_]?item', re.IGNORECASE),
        re.compile(r'item[_]?holder', re.IGNORECASE),
    ]

    # Pattern: ItemTransformVec3f / transform settings
    TRANSFORM_PATTERN = re.compile(
        r'ItemTransformVec3f\s*\(\s*'
        r'(?:new\s+Vector3f\s*\()?([0-9.fF\-]+)\s*,\s*([0-9.fF\-]+)\s*,\s*([0-9.fF\-]+)\)?'
        r'\s*,\s*'
        r'(?:new\s+Vector3f\s*\()?([0-9.fF\-]+)\s*,\s*([0-9.fF\-]+)\s*,\s*([0-9.fF\-]+)\)?'
        r'\s*,\s*'
        r'(?:new\s+Vector3f\s*\()?([0-9.fF\-]+)\s*,\s*([0-9.fF\-]+)\s*,\s*([0-9.fF\-]+)\)?'
    )

    # Pattern: Equipped item detection
    EQUIPPED_PATTERN = re.compile(
        r'getEquipmentSlot|getItemBySlot|getItemStackFromSlot'
        r'|getItemInHand|getHeldItem|getMainHandItem|getOffhandItem'
    )

    # Pattern: First-person arm rendering
    FIRST_PERSON_ARM_PATTERN = re.compile(
        r'renderItemInFirstPerson|renderArmFirstPerson|renderItemIn'
        r'|FirstPersonRenderer|ItemInHandRenderer'
    )

    # Default display presets (MC 1.12.2 defaults)
    DEFAULT_PRESETS = {
        'thirdperson_righthand': DisplayPreset(
            perspective='thirdperson_righthand',
            rotation=[0.0, 0.0, 0.0],
            translation=[0.0, 3.0, 1.0],
            scale=[0.55, 0.55, 0.55]
        ),
        'thirdperson_lefthand': DisplayPreset(
            perspective='thirdperson_lefthand',
            rotation=[0.0, 0.0, 0.0],
            translation=[0.0, 3.0, 1.0],
            scale=[0.55, 0.55, 0.55]
        ),
        'firstperson_righthand': DisplayPreset(
            perspective='firstperson_righthand',
            rotation=[0.0, -90.0, 25.0],
            translation=[1.13, 3.2, 1.13],
            scale=[0.68, 0.68, 0.68]
        ),
        'firstperson_lefthand': DisplayPreset(
            perspective='firstperson_lefthand',
            rotation=[0.0, 90.0, -25.0],
            translation=[1.13, 3.2, 1.13],
            scale=[0.68, 0.68, 0.68]
        ),
    }

    def __init__(self, bone_mapping: Dict[str, str]):
        """
        Args:
            bone_mapping: Mapping from Java variable names to GeckoLib bone names.
        """
        self.bone_mapping = bone_mapping

    def detect(self, renderer_java: str, model_java: str = "") -> FirstPersonDetectionResult:
        """
        Detect first-person handheld transform patterns.

        Args:
            renderer_java: Source code of the Renderer class.
            model_java: Source code of the Model class (optional).

        Returns:
            FirstPersonDetectionResult with display presets, held item bones, and hints.
        """
        display_presets: List[DisplayPreset] = []
        held_item_bones: List[HeldItemBone] = []
        first_person_hints: List[str] = []
        warnings: List[str] = []

        combined_source = renderer_java + "\n" + model_java

        # --- Detect ItemRenderer references ---
        item_renderer_matches = self.ITEM_RENDERER_PATTERN.findall(combined_source)
        if item_renderer_matches:
            first_person_hints.append(
                "ItemRenderer detected in source. In GeckoLib 1.20.1, held items are "
                "automatically handled by the entity's IAncillaryModelHolder or via "
                "BuiltinModelItemRenderer for block items."
            )

        # --- Detect first-person arm rendering ---
        fp_arm_matches = self.FIRST_PERSON_ARM_PATTERN.findall(combined_source)
        if fp_arm_matches:
            first_person_hints.append(
                "First-person arm rendering detected. For GeckoLib entities, use "
                "GeoPlayerRenderer or customize the arm rendering via "
                "RenderPlayerEvent.Pre/Post to integrate with the GeckoLib model."
            )

        # --- Detect equipped item checks ---
        equipped_matches = self.EQUIPPED_PATTERN.findall(combined_source)
        if equipped_matches:
            first_person_hints.append(
                "Equipment slot access detected. In GeckoLib 1.20.1, access equipment "
                "via entity.getItemBySlot(EquipmentSlot.MAINHAND) in codeAnimations "
                "to adjust held-item bone visibility or rotation."
            )

        # --- Detect ItemTransformVec3f settings ---
        transform_matches = self.TRANSFORM_PATTERN.findall(combined_source)
        for tm in transform_matches:
            try:
                rx, ry, rz = float(tm[0].rstrip('fF')), float(tm[1].rstrip('fF')), float(tm[2].rstrip('fF'))
                tx, ty, tz = float(tm[3].rstrip('fF')), float(tm[4].rstrip('fF')), float(tm[5].rstrip('fF'))
                sx, sy, sz = float(tm[6].rstrip('fF')), float(tm[7].rstrip('fF')), float(tm[8].rstrip('fF'))
                display_presets.append(DisplayPreset(
                    perspective="custom",
                    rotation=[rx, ry, rz],
                    translation=[tx, ty, tz],
                    scale=[sx, sy, sz]
                ))
            except (ValueError, IndexError):
                warnings.append("Could not parse ItemTransformVec3f values")

        # --- Detect held item bones from bone mapping ---
        for java_var, bone_name in self.bone_mapping.items():
            for pattern in self.HELD_ITEM_BONE_PATTERNS:
                if pattern.search(bone_name) or pattern.search(java_var):
                    item_type = "main_hand"
                    if "left" in bone_name.lower() or "off" in bone_name.lower():
                        item_type = "off_hand"

                    held_item_bones.append(HeldItemBone(
                        bone_name=bone_name,
                        item_type=item_type,
                        transform_code=self._generate_held_item_code(bone_name, item_type)
                    ))
                    break

        # --- Generate display presets if not found ---
        if not display_presets and held_item_bones:
            # Use default MC presets as starting point
            for preset in self.DEFAULT_PRESETS.values():
                display_presets.append(preset)

            first_person_hints.append(
                "No custom ItemTransformVec3f found. Using default MC display presets. "
                "Adjust rotation/translation/scale in the display settings if the "
                "held item appears incorrectly positioned."
            )

        has_held_item = len(held_item_bones) > 0 or len(item_renderer_matches) > 0

        return FirstPersonDetectionResult(
            display_presets=display_presets,
            held_item_bones=held_item_bones,
            first_person_hints=first_person_hints,
            has_held_item=has_held_item,
            warnings=warnings
        )

    def _generate_held_item_code(self, bone_name: str, item_type: str) -> str:
        """Generate codeAnimations snippet for held item bone."""
        return (
            f"// Held item bone: {bone_name} ({item_type})\n"
            f"// In codeAnimations():\n"
            f"GeoBone {bone_name}Bone = this.getAnimationProcessor().getBone(\"{bone_name}\");\n"
            f"if ({bone_name}Bone != null) {{\n"
            f"    ItemStack mainHand = entity.getItemBySlot(EquipmentSlot.MAINHAND);\n"
            f"    {bone_name}Bone.setHidden(mainHand.isEmpty());\n"
            f"}}"
        )
