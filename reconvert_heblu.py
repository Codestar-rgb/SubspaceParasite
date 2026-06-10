#!/usr/bin/env python3
"""
Re-convert Heblu bbmodel with improved animation quality v3
===========================================================
Fixes:
  - Consistent linear interpolation (no more catmullrom/linear mixing = no twitching)
  - All 8 animation states (added fly_vomit, cosmic_shaking)
  - Higher sampling rates (90-480 fps) for smoother motion
  - Tighter DP epsilon (0.03-0.04) for better keyframe precision
  - Loop continuity enforcement on all loop animations
  - No duplicate animation files
  - Keyframe deduplication to prevent same-time conflicts
"""

import json
import os
import sys

# Add converter directory to path
CONVERTER_DIR = os.path.dirname(os.path.abspath(__file__))
if CONVERTER_DIR not in sys.path:
    sys.path.insert(0, CONVERTER_DIR)

# Also add parent converter dir
PARENT_CONVERTER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "converter")
if PARENT_CONVERTER not in sys.path:
    sys.path.insert(0, PARENT_CONVERTER)


def main():
    print("=" * 70)
    print("  Heblu BBModel Re-Converter v3")
    print("  Improved Animation Quality: Precision, Smoothness, No Twitching")
    print("=" * 70)
    print()

    # Paths
    project_root = os.path.dirname(os.path.abspath(__file__))
    bbmodel_path = os.path.join(project_root, "MROLF-TGNBF", "derived", "heblu.bbmodel")
    java_source_path = os.path.join(
        project_root, "decompiled", "com", "dhanantry", "scapeandrunparasites",
        "client", "model", "entity", "derived", "ModelHeblu.java"
    )
    texture_path = os.path.join(
        project_root, "jar_extract", "assets", "srparasites",
        "textures", "entity", "monster", "heblu.png"
    )

    # ========================================================================
    # Step 1: Load existing bbmodel for geo data
    # ========================================================================
    print("[1/4] Loading existing heblu.bbmodel geometry...")
    with open(bbmodel_path, 'r') as f:
        existing_bbmodel = json.load(f)

    # Extract geo data from the bbmodel (elements, groups, outliner, textures)
    print(f"  Elements: {len(existing_bbmodel.get('elements', []))}")
    print(f"  Groups: {len(existing_bbmodel.get('groups', []))}")
    print(f"  Existing animations: {len(existing_bbmodel.get('animations', []))}")
    for a in existing_bbmodel.get('animations', []):
        print(f"    - {a['name']} (length={a.get('length',0)})")

    # ========================================================================
    # Step 2: Generate improved animations using heblu_animation_generator
    # ========================================================================
    print("\n[2/4] Generating improved animations (v3 quality)...")

    from heblu_animation_generator import generate_all_animations
    anim_json = generate_all_animations()

    anim_count = len(anim_json.get('animations', {}))
    print(f"\n  Total animations generated: {anim_count}")
    for anim_name, anim_data in anim_json.get('animations', {}).items():
        bone_count = len(anim_data.get('bones', {}))
        length = anim_data.get('animation_length', 0)
        loop = anim_data.get('loop', '?')
        print(f"    - {anim_name}: {bone_count} bones, {length}s, loop={loop}")

    # ========================================================================
    # Step 3: Re-generate bbmodel with improved animations
    # ========================================================================
    print("\n[3/4] Regenerating bbmodel with improved animations...")

    # Use the existing bbmodel's geo data but replace animations
    # We need to use the bbmodel_generator to properly convert anim_json to bbmodel format
    from bbmodel_generator import BBModelGenerator

    # Load the Java source for full conversion (geo + anim)
    # But we already have the bbmodel geometry, so we just need to replace animations
    # Use the generator's _build_animations method directly

    gen = BBModelGenerator()
    bb_animations = gen._build_animations(anim_json)

    print(f"  BBModel animations: {len(bb_animations)}")
    for a in bb_animations:
        animator_count = len(a.get('animators', {}))
        total_kf = sum(len(at.get('keyframes', [])) for at in a.get('animators', {}).values())
        interp_types = set()
        for at in a.get('animators', {}).values():
            for kf in at.get('keyframes', []):
                interp_types.add(kf.get('interpolation', '?'))
        print(f"    - {a['name']}: {animator_count} bones, {total_kf} keyframes, interp={interp_types}")

    # Replace animations in the existing bbmodel
    existing_bbmodel['animations'] = bb_animations

    # Also update modification time
    import time
    existing_bbmodel['meta']['modification_time'] = int(time.time())

    # ========================================================================
    # Step 4: Save the improved bbmodel
    # ========================================================================
    print(f"\n[4/4] Saving improved bbmodel to {bbmodel_path}...")

    # Backup the old file first
    backup_path = bbmodel_path + ".v2.bak"
    if not os.path.exists(backup_path):
        import shutil
        shutil.copy2(bbmodel_path, backup_path)
        print(f"  Backup saved: {backup_path}")

    gen.save(existing_bbmodel, bbmodel_path)

    file_size = os.path.getsize(bbmodel_path)
    print(f"  Saved: {bbmodel_path} ({file_size:,} bytes)")

    # ========================================================================
    # Verification
    # ========================================================================
    print("\n" + "=" * 70)
    print("  VERIFICATION")
    print("=" * 70)

    with open(bbmodel_path, 'r') as f:
        verify = json.load(f)

    # Check animations
    anims = verify.get('animations', [])
    print(f"  Animation count: {len(anims)}")
    expected_names = {
        "animation.model.idle",
        "animation.model.attack",
        "animation.model.fly",
        "animation.model.vomit",
        "animation.model.fly_vomit",
        "animation.model.shaking",
        "animation.model.cosmic",
        "animation.model.cosmic_shaking",
    }
    actual_names = {a['name'] for a in anims}
    missing = expected_names - actual_names
    extra = actual_names - expected_names

    if missing:
        print(f"  WARNING: Missing animations: {missing}")
    if extra:
        print(f"  WARNING: Extra animations: {extra}")
    if not missing and not extra:
        print(f"  ✓ All 8 expected animations present, no duplicates or extras")

    # Check interpolation consistency
    all_linear = True
    for a in anims:
        for at in a.get('animators', {}).values():
            for kf in at.get('keyframes', []):
                if kf.get('interpolation') != 'linear':
                    all_linear = False
                    print(f"  WARNING: Non-linear interpolation found in {a['name']}")
                    break
            if not all_linear:
                break
    if all_linear:
        print(f"  ✓ All keyframes use consistent 'linear' interpolation")

    # Check for duplicate time points
    dup_found = False
    for a in anims:
        for at in a.get('animators', {}).values():
            kfs = at.get('keyframes', [])
            seen_times = {}
            for kf in kfs:
                key = (round(kf['time'], 6), kf['channel'])
                if key in seen_times:
                    dup_found = True
                    print(f"  WARNING: Duplicate time point in {a['name']}: t={kf['time']}, ch={kf['channel']}")
                seen_times[key] = True
    if not dup_found:
        print(f"  ✓ No duplicate time points found")

    # Check loop continuity
    for a in anims:
        if a.get('loop') == 'loop':
            for at in a.get('animators', {}).values():
                kfs = at.get('keyframes', [])
                if len(kfs) >= 2:
                    # Group by channel and check first/last match
                    channels = {}
                    for kf in kfs:
                        ch = kf['channel']
                        if ch not in channels:
                            channels[ch] = []
                        channels[ch].append(kf)
                    for ch, ch_kfs in channels.items():
                        first_dp = ch_kfs[0]['data_points'][0]
                        last_dp = ch_kfs[-1]['data_points'][0]
                        for axis in ('x', 'y', 'z'):
                            diff = abs(first_dp.get(axis, 0.0) - last_dp.get(axis, 0.0))
                            if diff > 0.5:
                                print(f"  NOTE: {a['name']} {ch} {axis} loop gap: {diff:.4f}")

    print("\n  Done! The improved heblu.bbmodel is ready.")


if __name__ == "__main__":
    main()
