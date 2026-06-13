#!/usr/bin/env python3
"""
BBModel Walk Animation Post-Processor
======================================

Directly fixes walk animations in existing .bbmodel files by adding
synthetic leg rotation that mimics the original SRP mod's programmatic
animation.

BACKGROUND:
  The original SRP mod uses vanilla Minecraft ModelBase with programmatic
  animation driven by MathHelper.cos(limbSwing * speed) * degree. The
  converter pipeline only captured the GeckoLib overlay portion, missing
  the main programmatic walk rotation (14-23° amplitude).

  The previous walk_enhancer in the converter pipeline had bugs:
  1. Leg bone patterns missed X/Y-suffix main rotation joints
  2. Enhancement threshold included hair/tentacle bones from idle merger
  3. Synthetic walk only used X-axis rotation

  This post-processor fixes these issues directly in the .bbmodel files
  without needing to re-run the full converter pipeline.

USAGE:
  python3 fix_walk_animations.py <bbmodel_file_or_directory>

  For a single file:  python3 fix_walk_animations.py orch.bbmodel
  For a directory:    python3 fix_walk_animations.py /path/to/models/
"""

import json
import math
import os
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Maximum rotation range (degrees) below which LEG BONES need enhancement.
ENHANCE_THRESHOLD: float = 10.0

# Target amplitudes for synthetic walk rotation (degrees).
# Primary joints (X-suffix, main leg swing around Y-axis) get larger amplitude.
# Secondary joints (Y-suffix/numbered, leg flex around X-axis) get smaller.
TARGET_PRIMARY_AMPLITUDE: float = 20.0
TARGET_SECONDARY_AMPLITUDE: float = 10.0

# Number of keyframes per walk cycle for synthetic rotation.
SYNTHETIC_KF_PER_CYCLE: int = 16

# Minimum amplitude to add (degrees).
MIN_SYNTHETIC_AMPLITUDE: float = 3.0


# ---------------------------------------------------------------------------
# Leg bone classification
# ---------------------------------------------------------------------------

LEG_BONE_PATTERNS: List[Tuple[str, str, str]] = [
    # (regex_pattern, phase_group, primary_axis)
    # phase_group: "A" or "B" (alternating leg phase)
    # primary_axis: "y" for X-suffix (swingY = Y rotation),
    #               "x" for Y-suffix/numbered (swingX = X rotation)

    # Front legs - X-suffix (main swing, Y-axis rotation)
    (r'^jointfllx(_\d+)?$', 'A', 'y'),
    (r'^jointfrlx(_\d+)?$', 'B', 'y'),
    (r'^jointflax(_\d+)?$', 'A', 'y'),
    (r'^jointfrax(_\d+)?$', 'B', 'y'),

    # Front legs - Y-suffix (flex/sway, X-axis rotation)
    (r'^jointflly(_\d+)?$', 'A', 'x'),
    (r'^jointfrly(_\d+)?$', 'B', 'x'),
    (r'^jointflay(_\d+)?$', 'A', 'x'),
    (r'^jointfray(_\d+)?$', 'B', 'x'),

    # Front legs - numbered sub-segments (swingX, X-axis rotation)
    (r'^jointfll\d+$', 'A', 'x'),
    (r'^jointfrl\d+$', 'B', 'x'),
    (r'^jointfla\d+$', 'A', 'x'),
    (r'^jointfra\d+$', 'B', 'x'),
    (r'^jointfl\d+$', 'A', 'x'),
    (r'^jointfr\d+$', 'B', 'x'),

    # Middle legs - X-suffix
    (r'^jointmllx(_\d+)?$', 'B', 'y'),
    (r'^jointmrlx(_\d+)?$', 'A', 'y'),

    # Middle legs - Y-suffix
    (r'^jointmlly(_\d+)?$', 'B', 'x'),
    (r'^jointmrly(_\d+)?$', 'A', 'x'),

    # Middle legs - numbered sub-segments
    (r'^jointmll\d+$', 'B', 'x'),
    (r'^jointmrl\d+$', 'A', 'x'),
    (r'^jointml\d+$', 'B', 'x'),
    (r'^jointmr\d+$', 'A', 'x'),

    # Back legs - X-suffix
    (r'^jointbllx(_\d+)?$', 'B', 'y'),
    (r'^jointbrlx(_\d+)?$', 'A', 'y'),

    # Back legs - Y-suffix
    (r'^jointblly(_\d+)?$', 'B', 'x'),
    (r'^jointbrly(_\d+)?$', 'A', 'x'),

    # Back legs - numbered sub-segments
    (r'^jointbll\d+$', 'B', 'x'),
    (r'^jointbrl\d+$', 'A', 'x'),
    (r'^jointbl\d+$', 'B', 'x'),
    (r'^jointbr\d+$', 'A', 'x'),

    # Generic left/right leg joints
    (r'^jointll\d*$', 'A', 'x'),
    (r'^jointrl\d*$', 'B', 'x'),
    (r'^jointl[a-z]\d*$', 'A', 'x'),
    (r'^jointr[a-z]\d*$', 'B', 'x'),

    # Other naming conventions
    (r'^lfrontleg_joint$', 'A', 'y'),
    (r'^rfrontleg_joint$', 'B', 'y'),
    (r'^lbackleg_joint$', 'B', 'y'),
    (r'^rbackleg_joint$', 'A', 'y'),
    (r'^lfjoint_\d*$', 'A', 'x'),
    (r'^rfjoint_\d*$', 'B', 'x'),
    (r'^lbjoint_\d*$', 'B', 'x'),
    (r'^rbjoint_\d*$', 'A', 'x'),
    (r'^lfrontleg\d*$', 'A', 'x'),
    (r'^rfrontleg\d*$', 'B', 'x'),
    (r'^lbackleg\d*$', 'B', 'x'),
    (r'^rbackleg\d*$', 'A', 'x'),

    # Single frontleg (no left/right)
    (r'^frontleg$', 'A', 'x'),

    # Standard left/right legs
    (r'^leftleg$', 'A', 'x'),
    (r'^rightleg$', 'B', 'x'),

    # Tentacle joints
    (r'^taclejointfl\d*$', 'A', 'x'),
    (r'^taclejointfr\d*$', 'B', 'x'),
    (r'^taclejointl\d*$', 'A', 'x'),
    (r'^taclejointr\d*$', 'B', 'x'),
]


@dataclass
class LegBoneInfo:
    """Classification info for a leg bone."""
    bone_name: str
    phase_group: str
    primary_axis: str

    @property
    def is_primary_joint(self) -> bool:
        """True if this is a primary rotation joint (X-suffix = swingY)."""
        return self.primary_axis == 'y'


def classify_leg_bone(bone_name: str) -> Optional[LegBoneInfo]:
    """Classify a bone as a leg bone with axis information."""
    lower = bone_name.lower()
    for pattern, phase, axis in LEG_BONE_PATTERNS:
        if re.match(pattern, lower):
            return LegBoneInfo(bone_name=bone_name, phase_group=phase, primary_axis=axis)

    # Heuristic fallback
    if 'leg' in lower:
        if any(k in lower for k in ['left', 'lfront', 'lback']):
            return LegBoneInfo(bone_name, 'A', 'x')
        elif any(k in lower for k in ['right', 'rfront', 'rback']):
            return LegBoneInfo(bone_name, 'B', 'x')

    return None


# ---------------------------------------------------------------------------
# BBModel walk animation analysis and fixing
# ---------------------------------------------------------------------------

def _get_kf_axis_value(kf: dict, axis: str) -> float:
    """Get the value of a specific axis from a keyframe's data_points."""
    dp = kf.get('data_points', [{}])
    if dp:
        return dp[0].get(axis, 0.0)
    return 0.0


def _set_kf_axis_value(kf: dict, axis: str, value: float):
    """Set the value of a specific axis in a keyframe's data_points."""
    dp = kf.get('data_points', [{}])
    if dp:
        dp[0][axis] = round(value, 4)


def _compute_leg_rotation_range(anim: dict) -> float:
    """Compute max rotation range across LEG BONES ONLY in a walk animation."""
    max_range = 0.0
    animators = anim.get('animators', {})

    for aname, adata in animators.items():
        bone_name = adata.get('name', '')
        leg_info = classify_leg_bone(bone_name)
        if leg_info is None:
            continue

        for kf in adata.get('keyframes', []):
            if kf.get('channel') != 'rotation':
                continue
            for axis in ('x', 'y', 'z'):
                # Collect all values for this axis across all keyframes
                pass

    # Need to collect per-axis ranges
    for aname, adata in animators.items():
        bone_name = adata.get('name', '')
        leg_info = classify_leg_bone(bone_name)
        if leg_info is None:
            continue

        rot_kfs = [kf for kf in adata.get('keyframes', []) if kf.get('channel') == 'rotation']
        for axis in ('x', 'y', 'z'):
            vals = [_get_kf_axis_value(kf, axis) for kf in rot_kfs]
            vals = [v for v in vals if v != 0.0]  # exclude zero defaults
            if vals:
                rng = max(vals) - min(vals)
                max_range = max(max_range, rng)

    return max_range


def _get_existing_rotation_center_range(kf_list: list, axis: str) -> Tuple[float, float]:
    """Get the center and range of existing rotation on a specific axis."""
    vals = [_get_kf_axis_value(kf, axis) for kf in kf_list]
    # Filter out pure zeros (likely defaults, not real data)
    non_zero_vals = [v for v in vals if abs(v) > 0.001]
    if not non_zero_vals:
        # Use all vals including zeros
        if not vals:
            return (0.0, 0.0)
        non_zero_vals = vals

    min_val = min(non_zero_vals)
    max_val = max(non_zero_vals)
    center = (min_val + max_val) / 2.0
    range_val = max_val - min_val
    return (center, range_val)


def _interpolate_existing_value(kf_list: list, t: float, axis: str) -> float:
    """Interpolate existing rotation value at time t for a given axis."""
    if not kf_list:
        return 0.0

    # Get time-value pairs
    times_vals = [(kf.get('time', 0), _get_kf_axis_value(kf, axis)) for kf in kf_list]
    times_vals.sort(key=lambda x: x[0])

    if t <= times_vals[0][0]:
        return times_vals[0][1]
    if t >= times_vals[-1][0]:
        return times_vals[-1][1]

    # Linear interpolation
    for i in range(len(times_vals) - 1):
        t0, v0 = times_vals[i]
        t1, v1 = times_vals[i + 1]
        if t0 <= t <= t1:
            dt = t1 - t0
            if dt < 1e-12:
                return v0
            s = (t - t0) / dt
            return v0 + s * (v1 - v0)

    return times_vals[-1][1]


def _generate_uuid() -> str:
    """Generate a simple UUID for bbmodel keyframes."""
    import random
    return format(random.getrandbits(64), '016x')


def fix_walk_animation(anim: dict) -> Tuple[dict, bool]:
    """Fix a single walk animation by adding synthetic leg rotation.

    Args:
        anim: The animation dict from bbmodel JSON.

    Returns:
        (animation dict, changed_flag) tuple.
    """
    name = anim.get('name', '')
    if 'walk' not in name.lower():
        return anim, False

    anim_length = anim.get('length', 0)
    if anim_length <= 0:
        return anim, False

    animators = anim.get('animators', {})

    # Step 1: Compute leg rotation range
    leg_max_range = _compute_leg_rotation_range(anim)

    if leg_max_range >= ENHANCE_THRESHOLD:
        return anim, False  # Already has sufficient leg rotation

    # Step 2: Identify leg bones and classify them
    leg_bones: Dict[str, LegBoneInfo] = {}
    for aname, adata in animators.items():
        bone_name = adata.get('name', '')
        leg_info = classify_leg_bone(bone_name)
        if leg_info is not None:
            leg_bones[aname] = leg_info

    if not leg_bones:
        return anim, False  # No identifiable leg bones

    # Step 3: Enhance each leg bone
    enhanced_count = 0
    for aname, adata in animators.items():
        bone_name = adata.get('name', '')
        if aname not in leg_bones:
            continue

        leg_info = leg_bones[aname]
        primary_axis = leg_info.primary_axis

        # Get existing rotation keyframes
        kf_list = adata.get('keyframes', [])
        rot_kfs = [kf for kf in kf_list if kf.get('channel') == 'rotation']

        if not rot_kfs:
            continue

        # Get existing center and range for the primary axis
        existing_center, existing_range = _get_existing_rotation_center_range(
            rot_kfs, primary_axis
        )

        # Calculate synthetic amplitude
        if leg_info.is_primary_joint:
            target_amp = TARGET_PRIMARY_AMPLITUDE
        else:
            target_amp = TARGET_SECONDARY_AMPLITUDE

        synthetic_amplitude = max(0, target_amp - existing_range) / 2.0

        if synthetic_amplitude < MIN_SYNTHETIC_AMPLITUDE:
            continue

        # Generate synthetic walk offset function
        phase_offset = 0.0 if leg_info.phase_group == 'A' else math.pi
        anim_length = anim.get('length', 0)

        def synthetic_offset_at(t: float) -> float:
            """Compute the synthetic walk offset at time t for the primary axis."""
            angle = 2.0 * math.pi * t / anim_length + phase_offset
            return synthetic_amplitude * math.sin(angle)

        # MODIFY existing rotation keyframes in-place by adding synthetic offset.
        # This preserves the original keyframe times (density) and the original
        # overlay values, adding the synthetic walk on top.
        for kf in rot_kfs:
            t = kf.get('time', 0)
            offset = synthetic_offset_at(t)

            # Add synthetic offset to the primary axis value
            dp = kf.get('data_points', [{}])
            if dp:
                current_val = dp[0].get(primary_axis, 0.0)
                dp[0][primary_axis] = round(current_val + offset, 4)

        enhanced_count += 1

    if enhanced_count > 0:
        print(f"  WalkEnhancer: enhanced '{name}' (leg_range={leg_max_range:.1f}°, "
              f"{enhanced_count} leg bones enhanced)")

    return anim, enhanced_count > 0


def fix_bbmodel_file(filepath: str, dry_run: bool = False) -> bool:
    """Fix walk animations in a single .bbmodel file.

    Args:
        filepath: Path to the .bbmodel file.
        dry_run: If True, don't write changes.

    Returns:
        True if any changes were made.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ERROR reading {filepath}: {e}")
        return False

    animations = data.get('animations', [])
    if not animations:
        return False

    changed = False
    for i, anim in enumerate(animations):
        name = anim.get('name', '')
        if 'walk' not in name.lower():
            continue

        # Check if this walk animation needs enhancement
        leg_range = _compute_leg_rotation_range(anim)
        if leg_range >= ENHANCE_THRESHOLD:
            continue

        # Fix the walk animation
        fixed, was_changed = fix_walk_animation(anim)
        if was_changed:
            animations[i] = fixed
            changed = True

    if changed and not dry_run:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=None, separators=(',', ':'))

    return changed


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python3 fix_walk_animations.py <bbmodel_file_or_directory>")
        sys.exit(1)

    target = sys.argv[1]
    dry_run = '--dry-run' in sys.argv

    if os.path.isfile(target):
        # Single file
        print(f"Processing: {target}")
        changed = fix_bbmodel_file(target, dry_run=dry_run)
        if changed:
            print(f"  ✓ Changes {'would be ' if dry_run else ''}applied")
        else:
            print(f"  - No changes needed")

    elif os.path.isdir(target):
        # Directory — process all .bbmodel files
        total = 0
        fixed = 0

        for root, dirs, files in os.walk(target):
            dirs.sort()
            for fn in sorted(files):
                if not fn.endswith('.bbmodel'):
                    continue

                filepath = os.path.join(root, fn)
                total += 1
                print(f"[{total}] {os.path.relpath(filepath, target)}...", end=" ")

                try:
                    changed = fix_bbmodel_file(filepath, dry_run=dry_run)
                    if changed:
                        fixed += 1
                        print("✓ Enhanced")
                    else:
                        print("-")
                except Exception as e:
                    print(f"ERROR: {e}")

        print(f"\nProcessed {total} models, enhanced {fixed}")

    else:
        print(f"Error: {target} not found")
        sys.exit(1)


if __name__ == "__main__":
    main()
