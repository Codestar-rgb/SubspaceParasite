#!/usr/bin/env python3
"""
Walk Animation Post-Processor with Structural Bone Analysis
============================================================
Post-processes generated .animation.json files to produce high-quality
walk and run animations using STRUCTURAL analysis of the .geo.json
bone hierarchy (pivot positions, not name patterns).

Key Features:
  - Structural bone classification (body, legs, head, arms)
  - Sinusoidal walk keyframe generation with correct L/R phasing
  - Subtle body bob at 2x walk frequency
  - Subtle body X-rotation sway at walk frequency
  - Head counter-sway to body
  - Arm swing opposite to legs on same side
  - Run animation generation from walk parameters
  - catmullrom lerp_mode for smooth interpolation
  - Perfect loop continuity (first keyframe = last keyframe)
  - 20-24 keyframes per channel for smooth catmullrom
  - Edge cases: no legs, single leg, many legs, very small models

Integration:
  Called from batch_convert_all.py after the v18 animation converter
  writes the .animation.json file.

  from walk_animation_postprocessor import WalkAnimationPostProcessor
  walk_pp = WalkAnimationPostProcessor()
  walk_pp.process_animation(anim_output_path, geo_path)
"""

import json
import math
import os
from typing import Dict, List, Optional, Tuple, Any


class BoneInfo:
    """Structural information about a bone extracted from geo.json."""
    __slots__ = ('name', 'pivot', 'parent', 'num_cubes', 'cube_bounds',
                 'children', 'pivot_x', 'pivot_y', 'pivot_z',
                 'depth', 'structural_children', 'direct_cubes')

    def __init__(self, name: str, pivot: list, parent: Optional[str],
                 num_cubes: int, cube_bounds: list):
        self.name = name
        self.pivot = pivot
        self.parent = parent
        self.num_cubes = num_cubes
        self.cube_bounds = cube_bounds  # list of (min_y, max_y, min_x, max_x) per cube
        self.children: List[str] = []
        self.pivot_x = pivot[0] if pivot else 0.0
        self.pivot_y = pivot[1] if pivot else 0.0
        self.pivot_z = pivot[2] if pivot else 0.0
        self.depth = 0  # Distance from root (computed later)
        self.structural_children = 0  # Children that themselves have children
        self.direct_cubes = num_cubes  # Only this bone's own cubes (not descendants)


class BoneClassification:
    """Classification of bones into structural roles."""
    def __init__(self):
        self.body_core: Optional[str] = None       # Main body bone
        self.legs_left: List[str] = []              # Left leg bones
        self.legs_right: List[str] = []             # Right leg bones
        self.legs_unpaired: List[str] = []          # Legs with no L/R pair
        self.head_bones: List[str] = []             # Head bones (above body)
        self.arm_left: List[str] = []               # Left arm/wing bones
        self.arm_right: List[str] = []              # Right arm/wing bones
        self.body_pivot_y: float = 0.0              # Reference Y for body core


class WalkAnimationPostProcessor:
    """
    Post-processes walk animations using structural bone analysis.

    Usage:
        pp = WalkAnimationPostProcessor()
        pp.process_animation(anim_path, geo_path)
    """

    # Walk animation parameters
    WALK_LEG_AMPLITUDE_DEG = 30.0        # Degrees of leg X-rotation swing
    WALK_BOB_AMPLITUDE_PX = 0.2          # v22: Reduced from 1.2 — was excessive bounce
    WALK_SWAY_AMPLITUDE_DEG = 0.3        # v22: Reduced from 2.5 — was extreme waddling
    WALK_HEAD_COUNTER_SWAY_DEG = 0.5     # v22: Reduced from 1.5 — proportional to body sway
    WALK_ARM_AMPLITUDE_DEG = 25.0        # Degrees of arm X-rotation swing
    WALK_NUM_KEYFRAMES = 24              # Keyframes per channel for smooth catmullrom

    # Run animation parameters (derived from walk)
    RUN_SPEED_RATIO = 0.6                # Run duration = walk_duration * 0.6
    RUN_AMPLITUDE_BOOST = 1.4            # Run leg amplitude = walk * 1.4
    RUN_BODY_LEAN_DEG = 7.0              # Forward body lean in degrees
    RUN_BOB_AMPLITUDE_BOOST = 1.5        # Run bob = walk bob * 1.5
    RUN_BOB_AMPLITUDE_PX = 0.4           # v22: Reduced from 1.8 — was excessive bouncing

    # Small model threshold
    SMALL_MODEL_HEIGHT_PX = 16.0         # Below this, scale amplitudes down
    MIN_AMPLITUDE_SCALE = 0.3            # Minimum amplitude scaling factor

    def __init__(self):
        pass

    # ========================================================================
    # Public API
    # ========================================================================

    def process_animation(self, anim_path: str, geo_path: str) -> bool:
        """
        Post-process a .animation.json file to enhance walk/run animations.

        Args:
            anim_path: Path to the .animation.json file
            geo_path: Path to the corresponding .geo.json file

        Returns:
            True if any modifications were made, False otherwise
        """
        if not os.path.isfile(anim_path) or not os.path.isfile(geo_path):
            return False

        # Load both files
        try:
            with open(geo_path, 'r') as f:
                geo = json.load(f)
            with open(anim_path, 'r') as f:
                anim = json.load(f)
        except (json.JSONDecodeError, IOError):
            return False

        # Extract bone structure from geo.json
        bone_info = self._extract_bone_structure(geo)
        if not bone_info:
            return False

        # Classify bones structurally
        classification = self._classify_bones(bone_info)

        # Compute model scale factor for amplitude adjustment
        model_height = self._compute_model_height(geo)
        amplitude_scale = self._compute_amplitude_scale(model_height)

        # Process walk animations
        modified = False
        animations = anim.get("animations", {})

        walk_anim_data = None  # Store walk params for run generation

        for anim_name in list(animations.keys()):
            anim_data = animations[anim_name]
            anim_lower = anim_name.lower()

            is_walk = 'walk' in anim_lower
            is_run = 'run' in anim_lower

            if not (is_walk or is_run):
                continue

            loop_mode = anim_data.get("loop", "once")
            if loop_mode != "loop":
                continue

            duration = anim_data.get("animation_length", 0.0)
            if duration < 0.1:
                continue

            # Check if we have identifiable legs
            has_legs = bool(classification.legs_left or classification.legs_right
                            or classification.legs_unpaired)

            if not has_legs:
                # No legs detected - still apply body sway improvement
                # to the existing animation if it has a body core
                if classification.body_core and is_walk:
                    # Enhance existing walk: add body bob/sway to the
                    # body core bone without replacing other bone data
                    existing_bones = anim_data.get("bones", {})
                    body_name = classification.body_core
                    if body_name not in existing_bones:
                        # Add body sway/bob to the walk animation
                        sway_x = self._generate_sinusoidal_channel(
                            duration, num_kfs, sway_amp, phase_offset=0.0
                        )
                        bob_y = self._generate_cosine_channel(
                            duration, num_kfs, bob_amp, frequency_multiplier=2.0
                        )
                        existing_bones[body_name] = {
                            "rotation": {"x": sway_x, "y": {}, "z": {}},
                            "position": {"x": {}, "y": bob_y, "z": {}}
                        }
                        anim_data["bones"] = existing_bones
                        modified = True
                continue

            # Generate walk keyframes
            is_run_anim = is_run
            new_bones = self._generate_walk_keyframes(
                classification, duration, amplitude_scale, is_run_anim, bone_info
            )

            if not new_bones:
                continue

            # Replace bone data in animation
            anim_data["bones"] = new_bones
            anim_data["lerp_mode"] = "catmullrom"
            modified = True

            # Store walk params for run generation
            if is_walk:
                walk_anim_data = {
                    'duration': duration,
                    'name': anim_name,
                    'amplitude_scale': amplitude_scale,
                }

        # Generate run animation from walk if walk exists but run doesn't
        if walk_anim_data and not any('run' in n.lower() for n in animations):
            run_anim = self._generate_run_from_walk(
                classification, walk_anim_data, animations, bone_info
            )
            if run_anim:
                # Find the walk animation name and create run variant
                walk_name = walk_anim_data['name']
                run_name = walk_name.replace('walk', 'run')
                if run_name == walk_name:
                    run_name = walk_name + '.run'
                animations[run_name] = run_anim
                modified = True

        # Add lerp_mode to ALL loop animations (not just walk/run)
        # This is always beneficial regardless of whether walk was modified
        lerp_modified = False
        for anim_name, anim_data in animations.items():
            if anim_data.get("loop") == "loop":
                if "lerp_mode" not in anim_data:
                    anim_data["lerp_mode"] = "catmullrom"
                    lerp_modified = True

        # Also ensure walk/run animations that were NOT modified by the
        # postprocessor still get catmullrom interpolation (smoother than linear)
        for anim_name, anim_data in animations.items():
            anim_lower = anim_name.lower()
            if ('walk' in anim_lower or 'run' in anim_lower):
                if anim_data.get("loop") == "loop":
                    anim_data["lerp_mode"] = "catmullrom"
                    if "lerp_mode" not in anim_data:
                        lerp_modified = True

        if modified or lerp_modified:
            with open(anim_path, 'w') as f:
                json.dump(anim, f, indent=2, ensure_ascii=False)

        return modified

    # ========================================================================
    # Bone Structure Extraction
    # ========================================================================

    def _extract_bone_structure(self, geo: dict) -> Dict[str, BoneInfo]:
        """Extract bone structural information from geo.json."""
        geometries = geo.get("minecraft:geometry", [])
        if not geometries:
            return {}

        model = geometries[0]
        bones = model.get("bones", [])

        bone_info: Dict[str, BoneInfo] = {}

        for bone in bones:
            name = bone["name"]
            pivot = [float(v) for v in bone.get("pivot", [0, 0, 0])]
            parent = bone.get("parent")
            cubes = bone.get("cubes", [])

            # Compute cube bounds for each cube
            cube_bounds = []
            for cube in cubes:
                origin = cube.get("origin", [0, 0, 0])
                size = cube.get("size", [0, 0, 0])
                min_y = origin[1]
                max_y = origin[1] + size[1]
                min_x = origin[0]
                max_x = origin[0] + size[0]
                cube_bounds.append((min_y, max_y, min_x, max_x))

            info = BoneInfo(name, pivot, parent, len(cubes), cube_bounds)
            bone_info[name] = info

        # Build children lists
        for name, info in bone_info.items():
            if info.parent and info.parent in bone_info:
                bone_info[info.parent].children.append(name)

        # Compute depth (distance from root) and structural children
        root_bones_list = [name for name, info in bone_info.items()
                          if info.parent is None]
        for root_name in root_bones_list:
            bone_info[root_name].depth = 0

        # BFS to set depth
        queue = list(root_bones_list)
        while queue:
            name = queue.pop(0)
            info = bone_info[name]
            for child in info.children:
                if child in bone_info:
                    bone_info[child].depth = info.depth + 1
                    queue.append(child)

        # Compute structural children (children that themselves have children)
        for name, info in bone_info.items():
            info.structural_children = sum(
                1 for c in info.children
                if c in bone_info and bone_info[c].children
            )

        return bone_info

    # ========================================================================
    # Structural Bone Classification
    # ========================================================================

    def _classify_bones(self, bone_info: Dict[str, BoneInfo]) -> BoneClassification:
        """
        Classify bones into structural roles based on pivot positions
        and hierarchy, NOT name patterns.

        Algorithm:
        1. Find the body core: bone with most cubes and highest pivot
           that isn't the root
        2. Find legs: children of body core with lower pivot Y
        3. Find head: children of body core with higher pivot Y
        4. Find arms: children of body core at same height but offset in X
        5. Detect L/R pairs by X-pivot symmetry
        """
        cls = BoneClassification()

        if not bone_info:
            return cls

        # Step 1: Find the body core bone
        # Criteria: non-root bone that is a structural hub (has children)
        # We use a multi-factor scoring that weights structural role,
        # not just raw cube count. This prevents decorative sub-elements
        # from inflating the score (e.g., leg_3 with 7 decor children
        # should not beat mainbody with 5 structural children).
        best_body = None
        best_score = -1

        root_bones = [name for name, info in bone_info.items()
                      if info.parent is None]

        for name, info in bone_info.items():
            # Skip the "root" bone specifically (it's a container, not body)
            if name.lower() == 'root':
                continue

            # Body core should be a HUB - it must have at least 1 child
            if not info.children:
                continue

            # Count only direct cubes (not descendant cubes) to avoid
            # decorative children inflating the score
            direct_cubes = info.num_cubes

            # Count structural children (children that themselves have children)
            # These are the important ones - legs, head, arms attach here
            structural_ch = info.structural_children

            # Depth penalty: deeply nested bones are less likely to be body core
            depth_penalty = max(0, info.depth - 2) * 100

            # Y-position bonus: prefer bones in the middle of the model
            # (not too high like head, not too low like feet)
            all_y = [bi.pivot_y for bi in bone_info.values() if bi.children]
            if all_y:
                y_median = sorted(all_y)[len(all_y) // 2]
                y_closeness = max(0, 1.0 - abs(info.pivot_y - y_median) / max(y_median, 1.0))
            else:
                y_closeness = 0.5

            # Multi-factor score:
            # - Structural children weighted heavily (they are the key indicator)
            # - Direct cubes as a secondary indicator
            # - Depth penalty prevents deeply nested bones from winning
            # - Y-position bonus for central bones
            score = (structural_ch * 500
                     + direct_cubes * 50
                     + y_closeness * 200
                     - depth_penalty)

            if score > best_score:
                best_score = score
                best_body = name

        if best_body is None:
            # Fallback: use the first bone with the most cubes
            # that also has at least 2 children
            for name, info in bone_info.items():
                if name.lower() == 'root':
                    continue
                if len(info.children) >= 2 and info.num_cubes > best_score:
                    best_score = info.num_cubes
                    best_body = name

        if best_body is None:
            # Second fallback: any bone with children
            for name, info in bone_info.items():
                if name.lower() == 'root':
                    continue
                if info.children and info.num_cubes >= best_score:
                    best_score = info.num_cubes
                    best_body = name

        if best_body is None:
            return cls

        cls.body_core = best_body
        cls.body_pivot_y = bone_info[best_body].pivot_y

        # Step 2: Find leg, head, and arm candidates among children of body core
        body_children = bone_info[best_body].children

        # Also check grandchildren if body has few direct children
        all_descendants = []
        queue = list(body_children)
        visited = set()
        while queue:
            child = queue.pop(0)
            if child in visited or child not in bone_info:
                continue
            visited.add(child)
            all_descendants.append(child)
            for grandchild in bone_info[child].children:
                if grandchild not in visited:
                    queue.append(grandchild)

        # Classify by pivot Y relative to body core
        leg_candidates = []
        head_candidates = []
        arm_candidates = []

        body_y = cls.body_pivot_y
        body_x = bone_info[best_body].pivot_x

        # Compute model height for proportional leg detection threshold
        # A tiny model's legs are closer to body than a large model's
        all_pivots_y = [bi.pivot_y for bi in bone_info.values()]
        model_y_range = max(all_pivots_y) - min(all_pivots_y) if all_pivots_y else 24.0
        # Leg threshold: legs should be at least 5% of model height below body
        leg_dy_threshold = max(0.5, model_y_range * 0.05)

        for child_name in all_descendants:
            if child_name not in bone_info:
                continue

            child_info = bone_info[child_name]
            dy = child_info.pivot_y - body_y
            dx = abs(child_info.pivot_x - body_x)

            # Only consider direct children and first-level grandchildren
            # for leg/arm/head classification
            is_direct_child = child_name in body_children

            if is_direct_child:
                if dy < -leg_dy_threshold:
                    # Below body = leg candidate
                    leg_candidates.append(child_name)
                elif dy > 2.0:
                    # Above body = head candidate
                    head_candidates.append(child_name)
                elif dx > 2.0:
                    # Same height, offset to side = arm candidate
                    arm_candidates.append(child_name)

        # If no direct children are legs, also check grandchildren
        if not leg_candidates:
            for child_name in all_descendants:
                if child_name not in bone_info:
                    continue
                child_info = bone_info[child_name]
                dy = child_info.pivot_y - body_y
                dx = abs(child_info.pivot_x - body_x)

                if dy < -leg_dy_threshold:
                    if child_name not in leg_candidates:
                        leg_candidates.append(child_name)
                elif dy > 2.0:
                    # BUG FIX: Check head_candidates AND arm_candidates
                    # to prevent dual classification
                    if child_name not in head_candidates and child_name not in arm_candidates:
                        head_candidates.append(child_name)
                elif dx > 2.0:
                    # BUG FIX: Check head_candidates AND arm_candidates
                    # to prevent a bone from being in both lists
                    if child_name not in head_candidates and child_name not in arm_candidates:
                        arm_candidates.append(child_name)

        # Step 3: Detect L/R pairs among legs by X-pivot symmetry
        left_legs, right_legs, unpaired = self._detect_lr_pairs(
            leg_candidates, bone_info
        )

        cls.legs_left = left_legs
        cls.legs_right = right_legs
        cls.legs_unpaired = unpaired

        # Step 4: Detect L/R pairs for arms
        left_arms, right_arms, _ = self._detect_lr_pairs(
            arm_candidates, bone_info
        )
        cls.arm_left = left_arms
        cls.arm_right = right_arms

        # Step 5: Classify head bones
        cls.head_bones = head_candidates

        # Step 6: Fallback - if structural analysis found no legs,
        # try name-based detection as a last resort
        if not cls.legs_left and not cls.legs_right and not cls.legs_unpaired:
            cls = self._name_based_leg_fallback(cls, bone_info, best_body)

        # Step 7: Hip-based reclassification - if a bone named "hip" or
        # "pelvis" exists as a child of body core, its children are likely
        # legs even if they're structurally above the body (e.g., ferHuman
        # where mainbody pivot is very low and hip is above it)
        if not cls.legs_left and not cls.legs_right and not cls.legs_unpaired:
            cls = self._hip_based_leg_detection(cls, bone_info, best_body)

        return cls

    def _name_based_leg_fallback(
        self,
        cls: BoneClassification,
        bone_info: Dict[str, BoneInfo],
        body_core: str,
    ) -> BoneClassification:
        """
        Fallback: detect legs by name patterns when structural analysis fails.
        This handles models where legs have unusual pivot positions or
        hierarchy that the structural classifier misses.
        """
        # Common leg name patterns (lowercase)
        leg_patterns = [
            'leg', 'foot', 'feet', 'limb', 'paw', 'hoof', 'tarsus',
            'femur', 'tibia', 'shin', 'thigh', 'frontleg', 'backleg',
            'foreleg', 'hindleg', 'frontarm', 'backarm',
        ]
        # Common L/R leg naming conventions in MC mods
        # (checked against the actual bone names in our model set)
        # IMPORTANT: Be specific to avoid matching arm bones (LA/RA)
        lr_leg_patterns = [
            # *LL/*RL (Left Leg / Right Leg) - most common MC convention
            (r'jointll\b', 'left'), (r'jointrl\b', 'right'),
            (r'll\b', 'left'), (r'rl\b', 'right'),
            # *LF/*RF (Left Front / Right Front) - quadrupeds
            (r'lf\b', 'left'), (r'rf\b', 'right'),
            # *LB/*RB (Left Back / Right Back) - quadrupeds
            (r'lb\b', 'left'), (r'rb\b', 'right'),
            # Full words: left/right in name
            (r'leftleg', 'left'), (r'rightleg', 'right'),
            (r'jointleft\b', 'left'), (r'jointright\b', 'right'),
            (r'leftfoot', 'left'), (r'rightfoot', 'right'),
        ]

        leg_candidates = []

        for name, info in bone_info.items():
            name_lower = name.lower()
            # Skip body core and root
            if name == body_core or name_lower == 'root':
                continue
            # Skip if already classified as head or arm
            if name in cls.head_bones or name in cls.arm_left or name in cls.arm_right:
                continue

            # Check if name matches leg patterns
            is_leg = any(p in name_lower for p in leg_patterns)

            # Exclude arm bones explicitly
            arm_patterns = ['arm', 'hand', 'wing', 'claw', 'grab', 'tentacle', 'tacle']
            is_arm = any(p in name_lower for p in arm_patterns)
            if is_arm:
                is_leg = False

            # Also check for L/R leg naming patterns
            if not is_leg and not is_arm:
                import re
                for pattern, side in lr_leg_patterns:
                    if re.search(pattern, name_lower):
                        is_leg = True
                        break

            # A bone is a leg candidate if it matches name patterns
            # OR if it's a descendant of a "hip"/"pelvis" bone
            if not is_leg:
                # Check if parent is named hip/pelvis
                if info.parent:
                    parent_lower = info.parent.lower()
                    if any(p in parent_lower for p in ['hip', 'pelvis', 'legs', 'lowerbody']):
                        is_leg = True

            if is_leg:
                leg_candidates.append(name)

        if not leg_candidates:
            return cls

        # Classify as left/right/unpaired
        left_legs, right_legs, unpaired = self._detect_lr_pairs(
            leg_candidates, bone_info
        )

        cls.legs_left = left_legs
        cls.legs_right = right_legs
        cls.legs_unpaired = unpaired

        return cls

    def _hip_based_leg_detection(
        self,
        cls: BoneClassification,
        bone_info: Dict[str, BoneInfo],
        body_core: str,
    ) -> BoneClassification:
        """
        Detect legs by finding a "hip"/"pelvis" bone and treating its
        children as legs. This handles models like ferHuman where the
        body core has a very low pivot and everything is above it.
        """
        hip_names = ['hip', 'pelvis', 'hips', 'lowerbody', 'waist']

        # Find hip bone among body core's descendants
        hip_bone = None
        for name, info in bone_info.items():
            if name.lower() in hip_names:
                # Verify it's a descendant of body core
                if self._is_descendant_of(name, body_core, bone_info):
                    hip_bone = name
                    break

        if hip_bone is None or hip_bone not in bone_info:
            return cls

        hip_info = bone_info[hip_bone]
        leg_candidates = []

        for child_name in hip_info.children:
            if child_name not in bone_info:
                continue
            child_info = bone_info[child_name]
            # Skip if it's clearly an arm (has "arm" in name)
            child_lower = child_name.lower()
            arm_patterns = ['arm', 'hand', 'wing']
            is_arm = any(p in child_lower for p in arm_patterns)
            if is_arm:
                continue
            leg_candidates.append(child_name)

        if not leg_candidates:
            return cls

        left_legs, right_legs, unpaired = self._detect_lr_pairs(
            leg_candidates, bone_info
        )

        cls.legs_left = left_legs
        cls.legs_right = right_legs
        cls.legs_unpaired = unpaired

        # Remove these legs from head_bones if they were incorrectly
        # classified there
        all_legs = set(left_legs + right_legs + unpaired)
        cls.head_bones = [h for h in cls.head_bones if h not in all_legs]

        return cls

    def _is_descendant_of(
        self,
        bone_name: str,
        ancestor_name: str,
        bone_info: Dict[str, BoneInfo],
    ) -> bool:
        """Check if bone_name is a descendant of ancestor_name."""
        current = bone_name
        visited = set()
        while current and current in bone_info and current not in visited:
            if current == ancestor_name:
                return True
            visited.add(current)
            current = bone_info[current].parent
        return False

    def _detect_lr_pairs(
        self,
        candidates: List[str],
        bone_info: Dict[str, BoneInfo]
    ) -> Tuple[List[str], List[str], List[str]]:
        """
        Detect left/right pairs among candidate bones using X-pivot symmetry.

        In geo.json coordinates (after X-mirroring):
          - Negative X = LEFT side of model
          - Positive X = RIGHT side of model

        (Note: geo.json has X mirrored from bbmodel, so geo negative X
        corresponds to the model's left side facing +Z)
        """
        if not candidates:
            return [], [], []

        left = []
        right = []
        unpaired = []

        # Single candidate: treat as unpaired (will get symmetrical walk)
        if len(candidates) == 1:
            unpaired.append(candidates[0])
            return left, right, unpaired

        # Compute adaptive X threshold based on candidate X positions
        x_values = [bone_info[n].pivot_x for n in candidates if n in bone_info]
        if x_values:
            x_range = max(x_values) - min(x_values)
            # Threshold: 10% of the X range, minimum 0.5
            x_threshold = max(0.5, x_range * 0.10)
        else:
            x_threshold = 1.0

        # Classify by X pivot position
        # Sort by X to find pairs
        x_groups: Dict[str, List[str]] = {'neg': [], 'zero': [], 'pos': []}

        for name in candidates:
            if name not in bone_info:
                continue
            px = bone_info[name].pivot_x
            if px < -x_threshold:
                x_groups['neg'].append(name)
            elif px > x_threshold:
                x_groups['pos'].append(name)
            else:
                x_groups['zero'].append(name)

        # Negative X = left side, Positive X = right side
        left = x_groups['neg']
        right = x_groups['pos']
        unpaired = x_groups['zero']

        # If all bones have X near zero (centered model), try to pair
        # by sorting by X and splitting
        if not left and not right and len(candidates) >= 2:
            sorted_candidates = sorted(
                candidates,
                key=lambda n: bone_info[n].pivot_x if n in bone_info else 0
            )
            mid = len(sorted_candidates) // 2
            left = sorted_candidates[:mid]
            right = sorted_candidates[mid:]
            unpaired = []

        # Spider-like: many legs (4+), distribute with alternating phase
        # Already handled by having left/right lists

        return left, right, unpaired

    def _get_leg_chain(
        self,
        top_leg_bone: str,
        bone_info: Dict[str, BoneInfo],
    ) -> List[str]:
        """
        Get the full chain of bones from a top-level leg bone down to the leaf.

        For example, for ferWolf's front left leg:
          JD → jointFLL → leg → jointFLL1 → leg_1 → jointFLL2 → leg_2 → leg_3

        Returns the chain as a list of bone names, or empty list if not found.
        Only follows the FIRST child at each level (the structural child),
        ignoring decorative sub-bones.
        """
        if top_leg_bone not in bone_info:
            return []

        chain = [top_leg_bone]
        current = top_leg_bone
        visited = {top_leg_bone}
        max_depth = 6  # Prevent infinite chains

        for _ in range(max_depth):
            info = bone_info.get(current)
            if not info or not info.children:
                break

            # Find the "structural" child: the one with the most cubes
            # or the one that continues the chain (has children of its own)
            best_child = None
            best_score = -1

            for child_name in info.children:
                if child_name in visited:
                    continue
                if child_name not in bone_info:
                    continue

                child_info = bone_info[child_name]

                # Prefer children that:
                # 1. Have children themselves (continuation of chain)
                # 2. Have cubes (not just a decoration bone)
                # 3. Have a leg-like name
                score = 0
                if child_info.children:
                    score += 100
                if child_info.num_cubes > 0:
                    score += 50

                child_lower = child_name.lower()
                leg_names = ('leg', 'joint', 'foot', 'shin', 'knee', 'thigh')
                if any(n in child_lower for n in leg_names):
                    score += 30

                # Avoid decoration bones (names like "dec", "pop", "spike")
                deco_names = ('dec', 'pop', 'spike', 'horn', 'eye', 'tooth', 'jaw', 'tusk')
                if any(n in child_lower for n in deco_names):
                    score -= 200

                if score > best_score:
                    best_score = score
                    best_child = child_name

            if best_child is None or best_score < 0:
                break

            visited.add(best_child)
            chain.append(best_child)
            current = best_child

        return chain

    # ========================================================================
    # Model Scale Computation
    # ========================================================================

    def _compute_model_height(self, geo: dict) -> float:
        """Compute model height from geo.json cube bounds."""
        geometries = geo.get("minecraft:geometry", [])
        if not geometries:
            return 32.0

        model = geometries[0]
        bones = model.get("bones", [])

        min_y = float('inf')
        max_y = float('-inf')

        for bone in bones:
            for cube in bone.get("cubes", []):
                origin = cube.get("origin", [0, 0, 0])
                size = cube.get("size", [0, 0, 0])
                min_y = min(min_y, origin[1])
                max_y = max(max_y, origin[1] + size[1])

        if min_y == float('inf'):
            return 32.0

        return max_y - min_y

    def _compute_amplitude_scale(self, model_height: float) -> float:
        """Compute amplitude scaling factor for small models."""
        if model_height >= self.SMALL_MODEL_HEIGHT_PX:
            return 1.0

        # Scale down proportionally for small models
        scale = model_height / self.SMALL_MODEL_HEIGHT_PX
        return max(self.MIN_AMPLITUDE_SCALE, scale)

    # ========================================================================
    # Walk Keyframe Generation
    # ========================================================================

    def _generate_walk_keyframes(
        self,
        classification: BoneClassification,
        duration: float,
        amplitude_scale: float,
        is_run: bool = False,
        bone_info: Dict[str, BoneInfo] = None,
    ) -> Optional[dict]:
        """
        Generate walk/run animation keyframes for all classified bones.

        Returns a bones dict suitable for .animation.json format:
        {
          "bone_name": {
            "rotation": { "x": { "0.0": val, ... }, "y": {}, "z": {} },
            "position": { "x": {}, "y": { "0.0": val, ... }, "z": {} }
          },
          ...
        }
        """
        bones_dict = {}

        num_kfs = self.WALK_NUM_KEYFRAMES
        leg_amp = self.WALK_LEG_AMPLITUDE_DEG * amplitude_scale
        bob_amp = self.WALK_BOB_AMPLITUDE_PX * amplitude_scale
        sway_amp = self.WALK_SWAY_AMPLITUDE_DEG * amplitude_scale
        head_sway = self.WALK_HEAD_COUNTER_SWAY_DEG * amplitude_scale
        arm_amp = self.WALK_ARM_AMPLITUDE_DEG * amplitude_scale

        # For spider-like models with many legs, use alternating phase offsets
        all_legs_left = list(classification.legs_left)
        all_legs_right = list(classification.legs_right)
        all_legs_unpaired = list(classification.legs_unpaired)

        # Scale body sway by number of legs: more legs = less sway
        # (6+ leg creatures like spiders have more stable base)
        total_leg_count = len(all_legs_left) + len(all_legs_right) + len(all_legs_unpaired)
        if total_leg_count > 4:
            # Reduce sway for many-legged creatures
            sway_multiplier = max(0.3, 1.0 - (total_leg_count - 4) * 0.1)
            sway_amp *= sway_multiplier
            bob_amp *= max(0.5, sway_multiplier)
        elif total_leg_count == 2:
            # Biped: more body sway
            sway_amp *= 1.3
            bob_amp *= 1.2

        # Adjust for run animation
        if is_run:
            leg_amp *= self.RUN_AMPLITUDE_BOOST
            bob_amp = self.RUN_BOB_AMPLITUDE_PX * amplitude_scale
            sway_amp *= 1.2  # Slightly more sway when running

        # --- Generate leg keyframes with full chain animation ---
        # v22: Now animates the entire leg chain (upper leg → knee → foot),
        # not just the top-level joint. This creates natural knee bending
        # instead of rigid "paddle walking".
        all_legs_with_phase = []
        for leg_name in all_legs_left:
            all_legs_with_phase.append((leg_name, 0.0))
        for idx, leg_name in enumerate(all_legs_right):
            extra_phase = 0.0
            if len(all_legs_right) > 2 and idx % 2 == 1:
                extra_phase = math.pi
            all_legs_with_phase.append((leg_name, math.pi + extra_phase))
        for idx, leg_name in enumerate(all_legs_unpaired):
            phase = (2.0 * math.pi * idx / max(len(all_legs_unpaired), 1))
            all_legs_with_phase.append((leg_name, phase))

        for leg_name, phase in all_legs_with_phase:
            # Get the full chain of bones from this leg to the leaf
            chain = self._get_leg_chain(leg_name, bone_info)
            if not chain:
                # Fallback: just animate the top-level leg
                rot_x = self._generate_sinusoidal_channel(
                    duration, num_kfs, leg_amp, phase_offset=phase
                )
                bones_dict[leg_name] = {
                    "rotation": {"x": rot_x, "y": {}, "z": {}}
                }
                continue

            # Generate animation for each bone in the chain
            for chain_idx, chain_bone in enumerate(chain):
                if chain_bone in bones_dict:
                    continue  # Don't overwrite existing data

                if chain_idx == 0:
                    # Top of chain (hip joint): full forward/backward swing
                    rot_x = self._generate_sinusoidal_channel(
                        duration, num_kfs, leg_amp, phase_offset=phase
                    )
                elif chain_idx == 1:
                    # Second bone (upper leg/knee): opposite phase swing
                    # creating natural knee bending (knee bends when leg swings forward)
                    knee_amp = leg_amp * 0.6  # Knees don't swing as wide
                    rot_x = self._generate_sinusoidal_channel(
                        duration, num_kfs, knee_amp, phase_offset=phase + math.pi * 0.5
                    )
                elif chain_idx == 2:
                    # Third bone (lower leg/shin): same direction as top,
                    # but offset and reduced (continues the knee bend)
                    shin_amp = leg_amp * 0.3
                    rot_x = self._generate_sinusoidal_channel(
                        duration, num_kfs, shin_amp, phase_offset=phase + math.pi
                    )
                else:
                    # Deeper bones (foot, toes): very subtle motion
                    foot_amp = leg_amp * 0.15
                    rot_x = self._generate_sinusoidal_channel(
                        duration, num_kfs, foot_amp, phase_offset=phase
                    )

                bones_dict[chain_bone] = {
                    "rotation": {"x": rot_x, "y": {}, "z": {}}
                }

        # --- Generate body core keyframes ---
        if classification.body_core:
            body_name = classification.body_core

            # Body X-rotation sway at walk frequency
            sway_x = self._generate_sinusoidal_channel(
                duration, num_kfs, sway_amp, phase_offset=0.0
            )

            # Body Y-position bob at 2x walk frequency (cosine)
            bob_y = self._generate_cosine_channel(
                duration, num_kfs, bob_amp, frequency_multiplier=2.0
            )

            # Add forward lean for run
            lean_x = {}
            if is_run:
                lean_deg = self.RUN_BODY_LEAN_DEG
                # Constant lean throughout, with subtle variation
                for i in range(num_kfs + 1):
                    t = (i / num_kfs) * duration
                    if i == num_kfs:
                        t = duration
                    t_str = f"{t:.4f}"
                    # Slight variation: lean +/- 0.5 deg
                    variation = 0.5 * math.sin(2.0 * math.pi * t / duration)
                    lean_x[t_str] = round(lean_deg + variation, 4)

            # Merge sway and lean into rotation X channel
            rot_x = self._merge_rotation_channels(sway_x, lean_x)

            bones_dict[body_name] = {
                "rotation": {"x": rot_x, "y": {}, "z": {}},
                "position": {"x": {}, "y": bob_y, "z": {}}
            }

        # --- Generate head keyframes ---
        for head_name in classification.head_bones:
            # Counter-sway to body (opposite phase, smaller amplitude)
            rot_x = self._generate_sinusoidal_channel(
                duration, num_kfs, head_sway, phase_offset=math.pi
            )
            bones_dict[head_name] = {
                "rotation": {"x": rot_x, "y": {}, "z": {}}
            }

        # --- Generate arm keyframes ---
        # IMPORTANT: Arms must not overwrite existing bone entries
        # (e.g., a bone classified as both head AND arm should keep
        # its head counter-sway, not get arm swing)
        for arm_name in classification.arm_left:
            # Left arm swings opposite to left leg (pi phase offset)
            rot_x = self._generate_sinusoidal_channel(
                duration, num_kfs, arm_amp, phase_offset=math.pi
            )
            if arm_name in bones_dict:
                # Don't overwrite - this bone already has a role
                # (likely head counter-sway, which takes priority)
                pass
            else:
                bones_dict[arm_name] = {
                    "rotation": {"x": rot_x, "y": {}, "z": {}}
                }

        for arm_name in classification.arm_right:
            # Right arm swings with right leg (0 phase offset)
            rot_x = self._generate_sinusoidal_channel(
                duration, num_kfs, arm_amp, phase_offset=0.0
            )
            if arm_name in bones_dict:
                # Don't overwrite - this bone already has a role
                pass
            else:
                bones_dict[arm_name] = {
                    "rotation": {"x": rot_x, "y": {}, "z": {}}
                }

        return bones_dict if bones_dict else None

    def _generate_sinusoidal_channel(
        self,
        duration: float,
        num_keyframes: int,
        amplitude: float,
        phase_offset: float = 0.0,
    ) -> dict:
        """
        Generate sinusoidal keyframes for a single axis channel.

        Returns: {"0.0000": value, "0.0xxx": value, ...}

        The function generates amplitude * sin(2*pi*t/duration + phase_offset).
        This starts at zero-crossing (when phase_offset=0), ensuring
        perfect loop continuity since sin(0) = sin(2*pi) = 0.
        """
        channel = {}

        for i in range(num_keyframes + 1):
            t = (i / num_keyframes) * duration
            if i == num_keyframes:
                t = duration

            phase = 2.0 * math.pi * t / duration + phase_offset
            val = amplitude * math.sin(phase)

            t_str = f"{t:.4f}"
            channel[t_str] = round(val, 4)

        # Ensure loop continuity: last value should equal first
        first_t = f"{0.0:.4f}"
        last_t = f"{duration:.4f}"
        if first_t in channel and last_t in channel:
            # Force last = first for perfect loop
            channel[last_t] = channel[first_t]

        return channel

    def _generate_cosine_channel(
        self,
        duration: float,
        num_keyframes: int,
        amplitude: float,
        frequency_multiplier: float = 2.0,
    ) -> dict:
        """
        Generate cosine keyframes for a single axis channel.

        Used for body bob which oscillates at 2x walk frequency.
        Uses cosine so the body starts at maximum (standing position)
        and dips down at each foot strike.

        Returns: {"0.0000": value, "0.0xxx": value, ...}
        """
        channel = {}

        for i in range(num_keyframes + 1):
            t = (i / num_keyframes) * duration
            if i == num_keyframes:
                t = duration

            phase = frequency_multiplier * 2.0 * math.pi * t / duration
            val = -amplitude * (1.0 - math.cos(phase)) / 2.0  # Negative = downward bob

            t_str = f"{t:.4f}"
            channel[t_str] = round(val, 4)

        # Ensure loop continuity
        first_t = f"{0.0:.4f}"
        last_t = f"{duration:.4f}"
        if first_t in channel and last_t in channel:
            channel[last_t] = channel[first_t]

        return channel

    def _merge_rotation_channels(self, *channels: dict) -> dict:
        """
        Merge multiple rotation channels by summing values at matching time points.

        If time points don't align exactly, the merged channel uses the union
        of all time points with interpolated values.
        """
        if not channels:
            return {}

        if len(channels) == 1:
            return channels[0]

        # Collect all time points
        all_times = set()
        for ch in channels:
            all_times.update(ch.keys())

        # Sort time points
        sorted_times = sorted(all_times, key=lambda t: float(t))

        # For each time point, sum values from all channels
        merged = {}
        for t_str in sorted_times:
            total = 0.0
            for ch in channels:
                if t_str in ch:
                    total += ch[t_str]
                else:
                    # Interpolate: find nearest surrounding keys
                    total += self._interpolate_channel(ch, float(t_str))
            merged[t_str] = round(total, 4)

        return merged

    def _interpolate_channel(self, channel: dict, t: float) -> float:
        """Linearly interpolate a channel value at time t."""
        if not channel:
            return 0.0

        times = sorted(channel.keys(), key=lambda k: float(k))

        # Before first keyframe
        if t <= float(times[0]):
            return channel[times[0]]

        # After last keyframe
        if t >= float(times[-1]):
            return channel[times[-1]]

        # Find surrounding keys
        for i in range(len(times) - 1):
            t0 = float(times[i])
            t1 = float(times[i + 1])
            if t0 <= t <= t1:
                alpha = (t - t0) / (t1 - t0) if t1 != t0 else 0.0
                v0 = channel[times[i]]
                v1 = channel[times[i + 1]]
                return v0 + alpha * (v1 - v0)

        return 0.0

    # ========================================================================
    # Run Animation Generation
    # ========================================================================

    def _generate_run_from_walk(
        self,
        classification: BoneClassification,
        walk_anim_data: dict,
        existing_animations: dict,
        bone_info: Dict[str, BoneInfo] = None,
    ) -> Optional[dict]:
        """
        Generate a run animation from walk parameters.

        Run characteristics vs walk:
        - Duration = walk_duration * 0.6
        - Leg amplitude = walk_amplitude * 1.4
        - Body lean forward = 7 degrees
        - Body bob amplitude = walk_bob * 1.5
        """
        walk_duration = walk_anim_data['duration']
        amplitude_scale = walk_anim_data['amplitude_scale']

        run_duration = round(walk_duration * self.RUN_SPEED_RATIO, 4)

        # Generate run keyframes
        run_bones = self._generate_walk_keyframes(
            classification, run_duration, amplitude_scale, is_run=True, bone_info=bone_info
        )

        if not run_bones:
            return None

        # Build run animation entry
        run_anim = {
            "loop": "loop",
            "animation_length": run_duration,
            "bones": run_bones,
            "lerp_mode": "catmullrom",
        }

        return run_anim
