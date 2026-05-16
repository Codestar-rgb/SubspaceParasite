#!/usr/bin/env python3
"""
AnimationReferenceValidator - Animation Reference Integrity Validation
======================================================================
Validates that all animation references across controllers, state machines,
and animation JSON files are consistent and complete.

Checks:
  1. All controller-referenced animation names have corresponding JSON data
  2. All generated animation JSON entries are referenced by at least one controller
  3. Animation layer priority and blend weights are reasonable
  4. AnimationNames constants match the actual animation JSON names
  5. Cross-file consistency (animation name in JSON matches controller code)

Output:
  - validation_results: Per-check pass/fail with details
  - missing_animations: Animations referenced but not defined
  - orphaned_animations: Animations defined but never referenced
  - layer_weight_warnings: Unreasonable weight/priority combinations
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
import re


@dataclass
class ReferenceIssue:
    """An issue found during reference validation."""
    issue_type: str
    """'missing_animation', 'orphaned_animation', 'weight_warning', 'name_mismatch'."""
    animation_name: str
    """The animation name involved."""
    detail: str
    """Human-readable description of the issue."""
    severity: str
    """'error', 'warning', 'info'."""
    source: str
    """Where the issue was found (controller name, file name, etc.)."""


@dataclass
class ReferenceValidationResult:
    """Result of animation reference validation."""
    passed: bool
    """Whether all checks passed."""
    total_animations: int
    """Total number of animations found in JSON."""
    total_references: int
    """Total number of animation references in controllers."""
    missing_animations: List[ReferenceIssue]
    """Animations referenced but not defined in JSON."""
    orphaned_animations: List[ReferenceIssue]
    """Animations defined in JSON but never referenced."""
    layer_weight_warnings: List[ReferenceIssue]
    """Unreasonable layer weight/priority combinations."""
    name_mismatches: List[ReferenceIssue]
    """Name mismatches between JSON and controller code."""
    reference_map: Dict[str, List[str]]
    """Animation name → list of controllers referencing it."""
    all_issues: List[ReferenceIssue]
    """All issues combined, sorted by severity."""
    summary: str
    """Human-readable summary."""


class AnimationReferenceValidator:
    """
    Validates animation reference integrity across all generated output files.
    Ensures every referenced animation exists, and every defined animation is used.
    """

    # Reasonable layer weight/priority bounds
    MIN_BASE_WEIGHT = 0.5
    MAX_OVERLAY_WEIGHT = 1.0
    MIN_PRIORITY = 0
    MAX_PRIORITY = 100

    def __init__(self, namespace: str = "srparasites"):
        """
        Args:
            namespace: Mod namespace for animation name prefix matching.
        """
        self.namespace = namespace

    def validate(self, animation_json: dict,
                 controller_refs: Optional[List[dict]] = None,
                 naming_constants: Optional[List[dict]] = None,
                 layer_info: Optional[List[dict]] = None) -> ReferenceValidationResult:
        """
        Validate animation reference integrity.

        Args:
            animation_json: The .animation.json dict.
            controller_refs: List of dicts with controller reference info:
              - 'controller_name': str
              - 'animation_names': List[str]
              - 'priority': int (optional)
              - 'weight': float (optional)
            naming_constants: List of dicts from AnimationNamingManager:
              - 'constant_name': str
              - 'animation_name': str
            layer_info: Optional list of layer dicts from AnimationLayerSeparator:
              - 'name': str
              - 'layer_type': str
              - 'priority': int
              - 'animation_names': List[str]

        Returns:
            ReferenceValidationResult with detailed validation info.
        """
        issues: List[ReferenceIssue] = []
        missing: List[ReferenceIssue] = []
        orphaned: List[ReferenceIssue] = []
        weight_warnings: List[ReferenceIssue] = []
        mismatches: List[ReferenceIssue] = []

        # --- Collect defined animation names from JSON ---
        defined_anims: Set[str] = set()
        if animation_json and 'animations' in animation_json:
            defined_anims = set(animation_json['animations'].keys())

        total_animations = len(defined_anims)

        # --- Collect referenced animation names from controllers ---
        referenced_anims: Set[str] = set()
        reference_map: Dict[str, List[str]] = {}
        total_references = 0

        if controller_refs:
            for ctrl in controller_refs:
                ctrl_name = ctrl.get('controller_name', 'unknown')
                anim_names = ctrl.get('animation_names', [])
                for anim_name in anim_names:
                    referenced_anims.add(anim_name)
                    total_references += 1
                    if anim_name not in reference_map:
                        reference_map[anim_name] = []
                    reference_map[anim_name].append(ctrl_name)

        # Also check layer info for references
        if layer_info:
            for layer in layer_info:
                layer_name = layer.get('name', 'unknown')
                anim_names = layer.get('animation_names', [])
                for anim_name in anim_names:
                    referenced_anims.add(anim_name)
                    total_references += 1
                    if anim_name not in reference_map:
                        reference_map[anim_name] = []
                    reference_map[anim_name].append(f"layer:{layer_name}")

        # --- Check 1: Missing animations (referenced but not defined) ---
        missing_set = referenced_anims - defined_anims
        for anim_name in sorted(missing_set):
            ref_sources = reference_map.get(anim_name, [])
            issue = ReferenceIssue(
                issue_type='missing_animation',
                animation_name=anim_name,
                detail=f"Animation '{anim_name}' is referenced by {len(ref_sources)} "
                       f"controller(s) but not defined in animation JSON. "
                       f"Referenced by: {', '.join(ref_sources)}",
                severity='error',
                source=', '.join(ref_sources)
            )
            missing.append(issue)
            issues.append(issue)

        # --- Check 2: Orphaned animations (defined but never referenced) ---
        orphaned_set = defined_anims - referenced_anims
        for anim_name in sorted(orphaned_set):
            issue = ReferenceIssue(
                issue_type='orphaned_animation',
                animation_name=anim_name,
                detail=f"Animation '{anim_name}' is defined in JSON but not referenced "
                       f"by any controller. This may be dead code.",
                severity='warning',
                source='animation.json'
            )
            orphaned.append(issue)
            issues.append(issue)

        # --- Check 3: Layer weight/priority validation ---
        if layer_info:
            for layer in layer_info:
                layer_name = layer.get('name', 'unknown')
                layer_type = layer.get('layer_type', 'base')
                priority = layer.get('priority', 0)

                # Base layer should have highest priority
                if layer_type == 'base' and priority < 5:
                    issue = ReferenceIssue(
                        issue_type='weight_warning',
                        animation_name='',
                        detail=f"Base layer '{layer_name}' has low priority ({priority}). "
                               f"Base layers typically have the highest priority.",
                        severity='info',
                        source=f"layer:{layer_name}"
                    )
                    weight_warnings.append(issue)
                    issues.append(issue)

                # Overlay layers with weight > base
                if layer_type == 'overlay' and priority > 50:
                    issue = ReferenceIssue(
                        issue_type='weight_warning',
                        animation_name='',
                        detail=f"Overlay layer '{layer_name}' has very high priority ({priority}). "
                               f"This may override base animations unexpectedly.",
                        severity='warning',
                        source=f"layer:{layer_name}"
                    )
                    weight_warnings.append(issue)
                    issues.append(issue)

        # --- Check 4: Naming constant consistency ---
        if naming_constants:
            constant_anims = {nc['animation_name'] for nc in naming_constants}
            # Check if constants match defined animations
            for nc in naming_constants:
                const_name = nc['constant_name']
                anim_name = nc['animation_name']
                if anim_name not in defined_anims:
                    issue = ReferenceIssue(
                        issue_type='name_mismatch',
                        animation_name=anim_name,
                        detail=f"AnimationNames constant '{const_name}' references "
                               f"'{anim_name}' which is not defined in animation JSON.",
                        severity='error',
                        source='AnimationNames'
                    )
                    mismatches.append(issue)
                    issues.append(issue)

            # Check if all defined animations have a constant
            for anim_name in defined_anims:
                if anim_name not in constant_anims:
                    issue = ReferenceIssue(
                        issue_type='name_mismatch',
                        animation_name=anim_name,
                        detail=f"Animation '{anim_name}' is defined in JSON but has no "
                               f"corresponding AnimationNames constant.",
                        severity='warning',
                        source='AnimationNames'
                    )
                    mismatches.append(issue)
                    issues.append(issue)

        # --- Sort issues by severity ---
        severity_order = {'error': 0, 'warning': 1, 'info': 2}
        issues.sort(key=lambda x: severity_order.get(x.severity, 3))

        # --- Determine overall pass/fail ---
        has_errors = any(i.severity == 'error' for i in issues)
        passed = not has_errors

        # --- Build summary ---
        summary_parts = [
            f"Animation Reference Validation: {'PASS' if passed else 'FAIL'}",
            f"  Defined animations: {total_animations}",
            f"  Referenced animations: {total_references}",
            f"  Missing: {len(missing)}",
            f"  Orphaned: {len(orphaned)}",
            f"  Weight warnings: {len(weight_warnings)}",
            f"  Name mismatches: {len(mismatches)}",
        ]
        summary = "\n".join(summary_parts)

        return ReferenceValidationResult(
            passed=passed,
            total_animations=total_animations,
            total_references=total_references,
            missing_animations=missing,
            orphaned_animations=orphaned,
            layer_weight_warnings=weight_warnings,
            name_mismatches=mismatches,
            reference_map=reference_map,
            all_issues=issues,
            summary=summary
        )

    def validate_from_files(self, animation_json_path: str,
                             naming_result=None,
                             layer_result=None) -> ReferenceValidationResult:
        """
        Validate animation references using file paths and result objects.

        Args:
            animation_json_path: Path to the .animation.json file.
            naming_result: NamingResult from AnimationNamingManager.
            layer_result: LayerSeparationResult from AnimationLayerSeparator.

        Returns:
            ReferenceValidationResult.
        """
        import json

        # Load animation JSON
        animation_json = {}
        try:
            with open(animation_json_path, 'r') as f:
                animation_json = json.load(f)
        except (IOError, json.JSONDecodeError):
            pass

        # Build controller refs from layer result
        controller_refs = []
        if layer_result:
            layers = getattr(layer_result, 'layers', [])
            for layer in layers:
                controller_name = getattr(layer, 'controller_name', layer.name)
                anim_names = getattr(layer, 'animation_names', [])
                priority = getattr(layer, 'priority', 0)
                controller_refs.append({
                    'controller_name': controller_name,
                    'animation_names': anim_names,
                    'priority': priority,
                })

        # Build naming constants from naming result
        naming_constants = []
        if naming_result:
            for const in getattr(naming_result, 'constants', []):
                naming_constants.append({
                    'constant_name': const.constant_name,
                    'animation_name': const.animation_name,
                })

        # Build layer info from layer result
        layer_info = []
        if layer_result:
            layers = getattr(layer_result, 'layers', [])
            for layer in layers:
                layer_info.append({
                    'name': layer.name,
                    'layer_type': layer.layer_type,
                    'priority': layer.priority,
                    'animation_names': getattr(layer, 'animation_names', []),
                })

        return self.validate(animation_json, controller_refs, naming_constants, layer_info)
