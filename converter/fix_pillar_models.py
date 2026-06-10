#!/usr/bin/env python3
"""
Fix pillar/claw models that have elements below Y=0.

For models: venkrol, venkrolSII, venkrolSIII, unvo, tonro

Fix approach (per user instruction):
1. Set root group X rotation to 180° (flips the model upright)
2. Center the model
3. Adjust height to normal values

The 180° X rotation at the root pivot point flips the model vertically.
Since these models were designed to "hang down" (all elements at Y<0),
the flip makes them "stand up" with elements above the pivot.

The UV mapping does NOT need to change because:
- In Bedrock, bone rotation is a 3D transformation
- The faces stay on the same sides of the cubes
- The UV coordinates map to the texture atlas per-face
- When the bone rotates, the faces rotate together with their UVs
"""

import json
import os
import sys
from pathlib import Path

# Models that need fixing
MODELS_TO_FIX = {
    'deterrent': ['venkrol', 'venkrolSII', 'venkrolSIII', 'unvo', 'tonro'],
}

SOURCE_DIR = Path('/home/z/my-project/MROLF-TGNBF')


def find_root_group(outliner):
    """Find the top-level root group in the outliner."""
    for item in outliner:
        if isinstance(item, dict):
            name = item.get('name', '').lower()
            if name == 'root':
                return item
    # If no group named 'root', return the first group
    for item in outliner:
        if isinstance(item, dict):
            return item
    return None


def compute_model_y_bounds(elements):
    """Compute the Y bounds of all elements."""
    min_y = float('inf')
    max_y = float('-inf')
    for elem in elements:
        from_y = elem.get('from', [0, 0, 0])[1]
        to_y = elem.get('to', [0, 0, 0])[1]
        min_y = min(min_y, from_y, to_y)
        max_y = max(max_y, from_y, to_y)
    return min_y, max_y


def fix_model(filepath, category, model_name):
    """Fix a single .bbmodel model file."""
    print(f"\n{'='*60}")
    print(f"Fixing: {category}/{model_name}")
    print(f"{'='*60}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    elements = data.get('elements', [])
    outliner = data.get('outliner', [])
    
    # Compute original Y bounds
    orig_min_y, orig_max_y = compute_model_y_bounds(elements)
    print(f"Original Y bounds: [{orig_min_y:.1f}, {orig_max_y:.1f}]")
    print(f"Y span: {orig_max_y - orig_min_y:.1f}")
    
    # Find root group
    root_group = find_root_group(outliner)
    if root_group is None:
        print("ERROR: Could not find root group!")
        return False
    
    orig_rotation = root_group.get('rotation', [0, 0, 0])
    orig_origin = root_group.get('origin', [0, 0, 0])
    print(f"Original root rotation: {orig_rotation}")
    print(f"Original root origin: {orig_origin}")
    
    # Step 1: Set root X rotation to 180°
    # Keep Y rotation as-is (180° for these models)
    # Keep Z rotation as-is (0° for these models)
    new_rotation = [180.0, orig_rotation[1], orig_rotation[2]]
    root_group['rotation'] = new_rotation
    print(f"New root rotation: {new_rotation}")
    
    # Step 2 & 3: Adjust root pivot Y so the model sits at a proper height
    # 
    # When rotating 180° around X at the pivot point:
    # - Elements at Y_rel (relative to pivot) become at -Y_rel
    # - If all elements were below the pivot (Y_rel < 0), they'll be above (Y_rel > 0)
    #
    # The pivot is at orig_origin[1] (e.g., -0.9 for venkrol)
    # Elements range from orig_min_y to orig_max_y (e.g., -36.3 to -0.8 for venkrol)
    # Relative to pivot: [orig_min_y - pivot_y, orig_max_y - pivot_y]
    # After flip: [-(orig_max_y - pivot_y), -(orig_min_y - pivot_y)]
    # In world space: [pivot_y - (orig_max_y - pivot_y), pivot_y - (orig_min_y - pivot_y)]
    #               = [2*pivot_y - orig_max_y, 2*pivot_y - orig_min_y]
    
    pivot_y = orig_origin[1]
    
    # After flip, the model's world Y range will be:
    flipped_min_y = 2 * pivot_y - orig_max_y  # was near pivot, now near pivot (bottom)
    flipped_max_y = 2 * pivot_y - orig_min_y  # was far below, now far above (top)
    
    print(f"After X180 flip (no pivot change): Y range [{flipped_min_y:.1f}, {flipped_max_y:.1f}]")
    
    # We want the bottom of the flipped model to be at Y = 0 (or slightly above)
    # Current bottom: flipped_min_y = 2*pivot_y - orig_max_y
    # We want: new_pivot_y such that 2*new_pivot_y - orig_max_y = 0
    # new_pivot_y = orig_max_y / 2
    
    # Actually, we want the bottom at Y=0 with a small margin
    margin = 0.0  # No margin, bottom at exactly Y=0
    new_pivot_y = (orig_max_y + margin) / 2.0 + margin / 2.0
    
    # Hmm, let me recalculate. We want:
    # 2*new_pivot_y - orig_max_y = 0  (bottom of flipped model at Y=0)
    # new_pivot_y = orig_max_y / 2
    
    new_pivot_y = orig_max_y / 2.0
    
    # But wait, we need to account for the fact that we're changing the pivot Y.
    # The element positions in the .bbmodel file are ABSOLUTE, not relative to the pivot.
    # The pivot just defines the rotation center.
    # So when we change the pivot Y, the elements stay at the same positions,
    # but the rotation center moves. This means the relative positions change,
    # and the flip effect changes.
    
    # Let me reconsider. The elements have absolute positions in the .bbmodel file.
    # The pivot (origin) defines where the rotation is applied.
    # When we rotate 180° around X at the pivot, elements at position (x, y, z) become:
    # (x, 2*pivot_y - y, 2*pivot_z - z)  [for 180° X rotation at pivot]
    
    # Wait no, that's for 180° X rotation. Let me recalculate for [180, 180, 0]:
    # This is more complex. The rotation is applied as Euler angles.
    # But for the purpose of height calculation, the Y flip is the key factor.
    
    # For just the Y component of the rotation (180° X):
    # y_new = 2*pivot_y - y_old
    
    # For the full rotation [180, 180, 0]:
    # We need the combined transformation matrix
    # But for height calculation, the Y component after rotation is what matters.
    
    # Actually, the easiest approach: I want the flipped model bottom to be at Y≈0.
    # The current model bottom (min Y) is at orig_min_y.
    # After 180° X rotation at pivot, it becomes 2*pivot_y - orig_min_y (this is the TOP).
    # The current model top (max Y) is at orig_max_y.
    # After 180° X rotation at pivot, it becomes 2*pivot_y - orig_max_y (this is the BOTTOM).
    
    # So the bottom of the flipped model = 2*pivot_y - orig_max_y
    # We want this to be 0: 2*pivot_y - orig_max_y = 0 → pivot_y = orig_max_y / 2
    
    # But wait, we're also adjusting the pivot_y. If we change pivot_y, the elements
    # don't move in the file, but the rotation center changes. So the flipped bottom
    # becomes 2*new_pivot_y - orig_max_y.
    
    # We want 2*new_pivot_y - orig_max_y >= 0
    # new_pivot_y >= orig_max_y / 2
    
    # For venkrol: orig_max_y = -0.8, so new_pivot_y >= -0.4
    # This would put the pivot at Y=-0.4, which is still below ground.
    
    # Actually, for Minecraft Bedrock models, the entity position is typically at Y=0
    # (ground level). The root pivot defines where the entity's position maps to on the model.
    # If the root pivot is at Y=0, the entity stands on the ground.
    # If the root pivot is at Y=24, the entity's feet are 24 units below the position.
    
    # For consistency, let me set the pivot so the bottom of the model is at Y=0.
    # new_pivot_y = orig_max_y / 2
    
    # For venkrol: new_pivot_y = -0.8 / 2 = -0.4 → bottom at Y=0, top at Y=35.5
    # For unvo: orig_max_y = -0.9, new_pivot_y = -0.45 → bottom at Y=0, top at Y=42.5
    # For tonro: orig_max_y = -0.9, new_pivot_y = -0.45 → bottom at Y=0, top at Y=42.5
    
    # Hmm, but the pivot at Y=-0.4 or Y=-0.45 is slightly below ground.
    # For a cleaner look, let me move the pivot up slightly so it's at Y=0 or above.
    
    # Let me use a different approach: set the pivot so the model stands properly.
    # The model height after flip = orig_max_y - orig_min_y (same as before, just flipped)
    # We want the bottom at Y=0, so:
    # bottom = 2*new_pivot_y - orig_max_y = 0
    # new_pivot_y = orig_max_y / 2
    
    new_pivot_y = orig_max_y / 2.0
    
    new_origin = [orig_origin[0], new_pivot_y, orig_origin[2]]
    root_group['origin'] = new_origin
    print(f"New root origin: {new_origin}")
    
    # Verify the flipped model Y range
    final_bottom = 2 * new_pivot_y - orig_max_y
    final_top = 2 * new_pivot_y - orig_min_y
    print(f"Final flipped model Y range: [{final_bottom:.1f}, {final_top:.1f}]")
    
    # Save the fixed file
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✓ Fixed and saved: {filepath}")
    return True


def main():
    print("=" * 60)
    print("Pillar/Claw Model Y<0 Fix Script")
    print("=" * 60)
    
    fixed_count = 0
    failed_count = 0
    
    for category, models in MODELS_TO_FIX.items():
        for model_name in models:
            # Try both camelCase and lowercase filenames
            filepath = SOURCE_DIR / category / f"{model_name}.bbmodel"
            if not filepath.exists():
                filepath = SOURCE_DIR / category / f"{model_name.lower()}.bbmodel"
            
            if not filepath.exists():
                print(f"WARNING: File not found for {category}/{model_name}")
                failed_count += 1
                continue
            
            try:
                if fix_model(filepath, category, model_name):
                    fixed_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                print(f"ERROR fixing {category}/{model_name}: {e}")
                import traceback
                traceback.print_exc()
                failed_count += 1
    
    print(f"\n{'='*60}")
    print(f"Fix Summary: {fixed_count} fixed, {failed_count} failed")
    print(f"{'='*60}")
    
    return 0 if failed_count == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
