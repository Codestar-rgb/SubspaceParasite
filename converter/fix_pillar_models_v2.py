#!/usr/bin/env python3
"""
Fix pillar/claw models that have elements below Y=0.

Fix approach:
1. Change root group X rotation to 180° in the 'groups' array (primary data source)
2. Adjust root pivot Y so the model sits at ground level after flip
3. Also update the 'outliner' tree for consistency

The 'groups' array in .bbmodel is what bbmodel_to_geo.py reads for bone properties.
The 'outliner' tree defines hierarchy but can also override some properties.
"""

import json
import os
import sys
from pathlib import Path

MODELS_TO_FIX = {
    'deterrent': ['venkrol', 'venkrolSII', 'venkrolSIII', 'unvo', 'tonro'],
}

SOURCE_DIR = Path('/home/z/my-project/MROLF-TGNBF')
OUTPUT_DIR = Path('/home/z/my-project/MROLF-TGNBF-OUTPUT')


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
    groups = data.get('groups', [])
    outliner = data.get('outliner', [])
    
    # Compute original Y bounds
    orig_min_y, orig_max_y = compute_model_y_bounds(elements)
    print(f"Original Y bounds: [{orig_min_y:.1f}, {orig_max_y:.1f}]")
    
    # Find the root group in the groups array (first group named "root")
    root_group = None
    root_idx = None
    for i, g in enumerate(groups):
        if g.get('name', '').lower() == 'root':
            root_group = g
            root_idx = i
            break
    
    if root_group is None:
        print("ERROR: Could not find root group in groups array!")
        return False
    
    orig_rotation = root_group.get('rotation', [0, 0, 0])
    orig_origin = root_group.get('origin', [0, 0, 0])
    print(f"Original root rotation (groups): {orig_rotation}")
    print(f"Original root origin (groups): {orig_origin}")
    
    # Step 1: Set root X rotation to 180° (keep Y and Z as-is)
    new_rotation = [180.0, orig_rotation[1], orig_rotation[2]]
    root_group['rotation'] = new_rotation
    print(f"New root rotation: {new_rotation}")
    
    # Step 2: Adjust root pivot Y
    # After flipping 180° around X at the pivot, elements above the pivot
    # go below and vice versa. The bottom of the flipped model will be at:
    # 2*pivot_y - orig_max_y (the element closest to the pivot ends up at the bottom)
    # We want this to be >= 0, so: pivot_y >= orig_max_y / 2
    pivot_y = orig_origin[1]
    flipped_bottom = 2 * pivot_y - orig_max_y
    print(f"Flipped model bottom (no pivot change): Y={flipped_bottom:.1f}")
    
    # Move pivot so bottom of flipped model is at Y=0
    # 2*new_pivot_y - orig_max_y = 0 → new_pivot_y = orig_max_y / 2
    new_pivot_y = orig_max_y / 2.0
    new_origin = [orig_origin[0], new_pivot_y, orig_origin[2]]
    root_group['origin'] = new_origin
    print(f"New root origin: {new_origin}")
    
    # Verify
    final_bottom = 2 * new_pivot_y - orig_max_y
    final_top = 2 * new_pivot_y - orig_min_y
    print(f"Final flipped model Y range: [{final_bottom:.1f}, {final_top:.1f}]")
    
    # Step 3: Also handle duplicate root UUID entries
    # Some models have a second "root" entry with different rotation (tilted variant)
    # This second entry needs to be renamed to avoid UUID collision
    root_uuid = root_group.get('uuid')
    duplicate_roots = []
    for i, g in enumerate(groups):
        if i != root_idx and g.get('uuid') == root_uuid:
            duplicate_roots.append((i, g))
    
    if duplicate_roots:
        print(f"\nFound {len(duplicate_roots)} duplicate UUID entries for root")
        for idx, g in duplicate_roots:
            old_name = g.get('name', 'unnamed')
            old_rot = g.get('rotation', [0, 0, 0])
            # Rename to "rootarm" with new UUID
            g['name'] = 'rootarm'
            g['uuid'] = g['uuid'][:7] + 'aaaaaaa'  # Simple unique suffix
            print(f"  Renamed group {idx}: '{old_name}' → 'rootarm', rot={old_rot}")
    
    # Step 4: Update the outliner tree for consistency
    def update_outliner_group(items):
        for item in items:
            if isinstance(item, dict):
                if item.get('uuid') == root_uuid:
                    item['rotation'] = new_rotation
                    item['origin'] = new_origin
                update_outliner_group(item.get('children', []))
    
    update_outliner_group(outliner)
    print(f"Updated outliner tree for consistency")
    
    # Save the fixed file
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✓ Fixed and saved: {filepath}")
    return True


def main():
    print("=" * 60)
    print("Pillar/Claw Model Y<0 Fix Script v2")
    print("Fixes groups array (primary data source for geo converter)")
    print("=" * 60)
    
    fixed_count = 0
    failed_count = 0
    
    for category, models in MODELS_TO_FIX.items():
        for model_name in models:
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
