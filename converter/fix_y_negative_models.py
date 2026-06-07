#!/usr/bin/env python3
"""
Fix Y<0 (ground embedding) issue in .bbmodel files.

Problem: Some models have elements below Y=0, which causes them to appear
embedded in the ground when rendered in GeckoLib.

Root cause: The original Java models used a coordinate system where the
model was not anchored to Y=0 as the ground plane. After conversion to
Bedrock/GeckoLib format, Y=0 corresponds to the entity's ground level,
so any elements with Y<0 appear underground.

Fix: Shift all elements and groups up by |min_y| so the lowest element
is at Y=0. This preserves relative geometry and animations.

The fix is idempotent: running it twice produces the same result.

Usage:
    python fix_y_negative_models.py [--dry-run] [--base-dir DIR]
"""

import json
import os
import sys
from typing import Tuple, Optional


def get_y_range(elements: list) -> Tuple[float, float]:
    """Get the Y range of all elements."""
    min_y = float('inf')
    max_y = float('-inf')
    for el in elements:
        fy = min(el['from'][1], el['to'][1])
        ty = max(el['from'][1], el['to'][1])
        min_y = min(min_y, fy)
        max_y = max(max_y, ty)
    return min_y, max_y


def find_root_group_uuid(data: dict) -> Optional[str]:
    """Find the root group UUID from the outliner."""
    outliner = data.get('outliner', [])
    for item in outliner:
        if isinstance(item, dict):
            return item.get('uuid')
    return None


def clean_float(v: float) -> float:
    """Clean up floating point values: round and avoid -0.0."""
    v = round(v, 4)
    if v == 0.0:
        return 0.0
    return v


def fix_bbmodel(data: dict, filepath: str = "", dry_run: bool = False) -> tuple:
    """Fix a single .bbmodel file by shifting elements up if any are below Y=0.

    Returns a tuple of (data, was_fixed, info_message).
    """
    elements = data.get('elements', [])
    if not elements:
        return data, False, "No elements"

    min_y, max_y = get_y_range(elements)

    # Check if any elements are below Y=0
    if min_y >= -0.001:  # Allow tiny floating point errors
        return data, False, f"Already OK (Y range: [{min_y:.2f}, {max_y:.2f}])"

    offset_y = abs(min_y)
    offset_y = round(offset_y, 4)  # Avoid floating point accumulation

    # Get root group info for reporting
    groups = data.get('groups', [])
    root_uuid = find_root_group_uuid(data)
    root_group = None
    root_origin_before = None
    root_rotation = None
    for g in groups:
        if g.get('uuid') == root_uuid:
            root_group = g
            root_origin_before = list(g.get('origin', [0, 0, 0]))
            root_rotation = list(g.get('rotation', [0, 0, 0]))
            break

    if dry_run:
        new_min_y = min_y + offset_y
        new_max_y = max_y + offset_y
        root_origin_after = [root_origin_before[0], root_origin_before[1] + offset_y, root_origin_before[2]] if root_origin_before else None
        return data, True, (
            f"WOULD FIX: offset_y={offset_y:.2f}, "
            f"Y [{min_y:.2f}, {max_y:.2f}] -> [{new_min_y:.2f}, {new_max_y:.2f}], "
            f"root_origin {root_origin_before} -> {root_origin_after}, "
            f"root_rot={root_rotation}"
        )

    # Shift all elements up by offset_y
    for el in elements:
        el['from'][1] = clean_float(el['from'][1] + offset_y)
        el['to'][1] = clean_float(el['to'][1] + offset_y)
        if 'origin' in el:
            el['origin'][1] = clean_float(el['origin'][1] + offset_y)

    # Shift all groups' origins up by offset_y
    for g in groups:
        if 'origin' in g:
            g['origin'][1] = clean_float(g['origin'][1] + offset_y)

    # Verify the fix
    new_min_y, new_max_y = get_y_range(elements)
    root_origin_after = None
    if root_group:
        root_origin_after = list(root_group.get('origin', [0, 0, 0]))

    return data, True, (
        f"FIXED: offset_y={offset_y:.2f}, "
        f"Y [{min_y:.2f}, {max_y:.2f}] -> [{new_min_y:.2f}, {new_max_y:.2f}], "
        f"root_origin {root_origin_before} -> {root_origin_after}, "
        f"root_rot={root_rotation}"
    )


def process_directory(base_dir: str, dry_run: bool = False) -> None:
    """Process all .bbmodel files in the directory tree."""
    print("=" * 70)
    print("  Fix Y<0 (Ground Embedding) in .bbmodel Files")
    print(f"  Base directory: {base_dir}")
    print(f"  Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print("=" * 70)
    print()

    # Find all .bbmodel files
    bbmodel_files = []
    for root, dirs, files in os.walk(base_dir):
        for fn in sorted(files):
            if fn.endswith('.bbmodel'):
                fpath = os.path.join(root, fn)
                rel = os.path.relpath(fpath, base_dir)
                bbmodel_files.append((fpath, rel))

    print(f"Found {len(bbmodel_files)} .bbmodel files")
    print()

    fixed_count = 0
    skipped_count = 0
    error_count = 0
    results = []

    for fpath, rel in bbmodel_files:
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            fixed_data, was_fixed, info = fix_bbmodel(data, fpath, dry_run)

            if was_fixed:
                if not dry_run:
                    # Write the fixed file
                    with open(fpath, 'w', encoding='utf-8') as f:
                        json.dump(fixed_data, f, indent=2, ensure_ascii=False)
                fixed_count += 1
                status = "WOULD FIX" if dry_run else "FIXED"
                results.append((rel, True, info))
                print(f"  {status}: {rel} - {info}")
            else:
                skipped_count += 1
                # Don't print skipped files (too many)

        except Exception as e:
            error_count += 1
            results.append((rel, False, f"ERROR: {e}"))
            print(f"  ERROR: {rel} - {e}")

    # Summary
    print()
    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  Total files:     {len(bbmodel_files)}")
    print(f"  Fixed:           {fixed_count}")
    print(f"  Already OK:      {skipped_count}")
    print(f"  Errors:          {error_count}")

    if results:
        # Categorize fixed models by directory
        by_category = {}
        for rel, was_fixed, info in results:
            if was_fixed:
                cat = os.path.dirname(rel)
                by_category.setdefault(cat, []).append((rel, info))

        if by_category:
            print()
            print("  Fixed models by category:")
            for cat in sorted(by_category):
                items = by_category[cat]
                print(f"    {cat}/ ({len(items)} models)")
                for rel, info in items:
                    name = os.path.basename(rel)
                    print(f"      {name}: {info}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Fix Y<0 (ground embedding) in .bbmodel files"
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Show what would be fixed without modifying files'
    )
    parser.add_argument(
        '--base-dir', type=str,
        default='/home/z/my-project/MROLF-TGNBF',
        help='Base directory containing .bbmodel files'
    )
    args = parser.parse_args()

    if not os.path.isdir(args.base_dir):
        print(f"Error: Directory not found: {args.base_dir}")
        sys.exit(1)

    process_directory(args.base_dir, args.dry_run)


if __name__ == "__main__":
    main()
