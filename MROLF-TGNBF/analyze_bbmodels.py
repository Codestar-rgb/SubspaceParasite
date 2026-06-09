#!/usr/bin/env python3
"""
Analyze all .bbmodel files in MROLF-TGNBF directory.
Find the most complex models by animation count, keyframe count, bone count.
Detailed analysis of ferHuman.bbmodel walk animation.
"""

import json
import os
from pathlib import Path
from collections import defaultdict

BASE_DIR = "/home/z/my-project/MROLF-TGNBF"

def count_bones(elements):
    """Count bones (elements with type 'cube' or 'locator' that are used as bones in animations)."""
    # In BBModel, bones are the groups/outlines entries, but elements are the actual cubes.
    # For counting "bones" in animation context, we need to check what animators reference.
    # For a standalone count from elements, we count unique element names.
    return len(elements) if elements else 0

def count_animations_keyframes(animations):
    """Count total keyframes across all animations, and per-animation details.
    
    BBModel format: each animator has a flat 'keyframes' list where each keyframe
    has a 'channel' field (position/rotation/scale).
    """
    total_kf = 0
    anim_details = []
    if not animations:
        return total_kf, anim_details
    
    for anim in animations:
        anim_kf = 0
        anim_bone_channels = 0
        bone_kf_counts = {}
        
        animators = anim.get("animators", {})
        if animators:
            for bone_name, bone_data in animators.items():
                bone_kf = 0
                keyframes = bone_data.get("keyframes", [])
                # Count channels used by this bone
                channels_used = set()
                for kf in keyframes:
                    ch = kf.get("channel", "")
                    channels_used.add(ch)
                bone_kf = len(keyframes)
                anim_bone_channels += len(channels_used)
                bone_kf_counts[bone_name] = bone_kf
                anim_kf += bone_kf
        
        total_kf += anim_kf
        anim_details.append({
            "name": anim.get("name", "unnamed"),
            "length": anim.get("length", 0),
            "loop": anim.get("loop", "once"),
            "total_keyframes": anim_kf,
            "bone_channels": anim_bone_channels,
            "bone_kf_counts": bone_kf_counts,
            "animators_raw": animators
        })
    
    return total_kf, anim_details

def get_bone_channel_count(animations):
    """Count total unique bone channels across all animations.
    BBModel format: channels are in each keyframe's 'channel' field.
    """
    channels = set()
    if not animations:
        return 0
    for anim in animations:
        animators = anim.get("animators", {})
        for bone_name, bone_data in animators.items():
            keyframes = bone_data.get("keyframes", [])
            for kf in keyframes:
                ch = kf.get("channel", "")
                channels.add(f"{bone_name}.{ch}")
    return len(channels)

def scan_all_bbmodels():
    """Scan all .bbmodel files and collect complexity metrics."""
    results = []
    
    for root, dirs, files in os.walk(BASE_DIR):
        # Skip bedrock directory (exported format, not source)
        if "/bedrock/" in root or "/bedrock/textures/" in root:
            continue
        for fname in files:
            if not fname.endswith(".bbmodel"):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, Exception) as e:
                print(f"  [ERROR] Failed to parse {fpath}: {e}")
                continue
            
            elements = data.get("elements", [])
            animations = data.get("animations", [])
            
            num_bones = count_bones(elements)
            num_anims = len(animations) if animations else 0
            total_kf, anim_details = count_animations_keyframes(animations)
            num_bone_channels = get_bone_channel_count(animations)
            
            complexity = total_kf * num_anims  # rough metric
            
            rel_path = os.path.relpath(fpath, BASE_DIR)
            results.append({
                "path": rel_path,
                "animations": num_anims,
                "total_keyframes": total_kf,
                "bones": num_bones,
                "bone_channels": num_bone_channels,
                "complexity": complexity,
                "anim_details": anim_details,
                "full_path": fpath
            })
    
    return results

def analyze_ferhuman(ferhuman_path):
    """Deep analysis of ferHuman.bbmodel."""
    with open(ferhuman_path, "r") as f:
        data = json.load(f)
    
    animations = data.get("animations", [])
    elements = data.get("elements", [])
    
    print("=" * 80)
    print("ferHuman.bbmodel — DETAILED ANIMATION ANALYSIS")
    print("=" * 80)
    print(f"Total elements: {len(elements)}")
    print(f"Total animations: {len(animations)}")
    print()
    
    # Print summary of each animation
    print("-" * 80)
    print("ANIMATION SUMMARY")
    print("-" * 80)
    for anim in animations:
        name = anim.get("name", "unnamed")
        length = anim.get("length", 0)
        loop = anim.get("loop", "once")
        animators = anim.get("animators", {})
        
        total_kf = 0
        bone_counts = {}
        bone_channel_counts = {}
        for bone_name, bone_data in animators.items():
            keyframes = bone_data.get("keyframes", [])
            ch_counts = {}
            for kf in keyframes:
                ch = kf.get("channel", "unknown")
                ch_counts[ch] = ch_counts.get(ch, 0) + 1
            bone_counts[bone_name] = len(keyframes)
            bone_channel_counts[bone_name] = ch_counts
            total_kf += len(keyframes)
        
        print(f"\n  Animation: \"{name}\"")
        print(f"    Length: {length}  |  Loop: {loop}  |  Total keyframes: {total_kf}")
        print(f"    Bones animated: {len(bone_counts)}")
        for bone_name in sorted(bone_counts.keys(), key=lambda x: -bone_counts[x]):
            ch_str = ", ".join(f"{ch}:{cnt}" for ch, cnt in sorted(bone_channel_counts[bone_name].items()))
            print(f"      {bone_name}: {bone_counts[bone_name]} keyframes ({ch_str})")
    
    # Find the walk animation
    walk_anim = None
    for anim in animations:
        if "walk" in anim.get("name", "").lower():
            walk_anim = anim
            break
    
    if walk_anim:
        print("\n" + "=" * 80)
        print(f"WALK ANIMATION DEEP DIVE: \"{walk_anim.get('name')}\"")
        print("=" * 80)
        print(f"  Length: {walk_anim.get('length', 0)}")
        print(f"  Loop: {walk_anim.get('loop', 'once')}")
        print(f"  Override: {walk_anim.get('override', False)}")
        print(f"  Animators (bones): {len(walk_anim.get('animators', {}))}")
        
        animators = walk_anim.get("animators", {})
        for bone_name, bone_data in sorted(animators.items()):
            keyframes = bone_data.get("keyframes", [])
            print(f"\n  ── Bone: \"{bone_name}\" ──")
            if not keyframes:
                print("    (no keyframes)")
                continue
            # Group keyframes by channel
            channels = {}
            for kf in keyframes:
                ch = kf.get("channel", "unknown")
                if ch not in channels:
                    channels[ch] = []
                channels[ch].append(kf)
            
            for ch_name in ["position", "rotation", "scale"]:
                if ch_name not in channels:
                    continue
                kf_list = channels[ch_name]
                kf_list.sort(key=lambda k: k.get("time", 0))
                print(f"    Channel: {ch_name} ({len(kf_list)} keyframes, interpolation: {kf_list[0].get('interpolation', 'linear')})")
                for kf in kf_list:
                    time = kf.get("time", "?")
                    interpolation = kf.get("interpolation", "")
                    data_points = kf.get("data_points", [])
                    if data_points:
                        for dp_idx, dp in enumerate(data_points):
                            x = dp.get("x", dp.get("value", "?"))
                            y = dp.get("y", "?")
                            z = dp.get("z", "?")
                            easing = dp.get("easing", "")
                            if dp_idx == 0:
                                print(f"      t={time:>8.4f}  x={x:>10}  y={y:>10}  z={z:>10}  interp={interpolation}  easing={easing}")
                            else:
                                print(f"               (blend)    x={x:>10}  y={y:>10}  z={z:>10}  easing={easing}")
                    else:
                        print(f"      t={time:>8}  (no data_points)")
    
    # Check for duplicate animations
    print("\n" + "=" * 80)
    print("DUPLICATE ANIMATION CHECK")
    print("=" * 80)
    
    # Build a signature for each animation: sorted list of (bone, channel, time, data)
    anim_sigs = {}
    for anim in animations:
        name = anim.get("name", "unnamed")
        sig_parts = []
        animators = anim.get("animators", {})
        for bone_name in sorted(animators.keys()):
            bone_data = animators[bone_name]
            keyframes = bone_data.get("keyframes", [])
            for kf in keyframes:
                ch = kf.get("channel", "")
                time = kf.get("time", 0)
                dp = kf.get("data_points", [])
                dp_str = json.dumps(dp, sort_keys=True)
                sig_parts.append((bone_name, ch, time, dp_str))
        sig = tuple(sig_parts)
        if sig not in anim_sigs:
            anim_sigs[sig] = []
        anim_sigs[sig].append(name)
    
    duplicates_found = False
    for sig, names in anim_sigs.items():
        if len(names) > 1:
            duplicates_found = True
            print(f"\n  DUPLICATE FOUND! These animations have identical data:")
            for n in names:
                print(f"    - \"{n}\"")
    
    if not duplicates_found:
        print("  No duplicate animations found (all animations have unique bone channel/keyframe data).")
    
    # Additional: check for near-duplicate patterns (same bones, same channel structure, similar keyframe times)
    print("\n" + "=" * 80)
    print("STRUCTURAL SIMILARITY CHECK (same bone+channel set)")
    print("=" * 80)
    
    anim_structures = {}
    for anim in animations:
        name = anim.get("name", "unnamed")
        structure = set()
        animators = anim.get("animators", {})
        for bone_name in sorted(animators.keys()):
            bone_data = animators[bone_name]
            keyframes = bone_data.get("keyframes", [])
            # Count per channel
            ch_counts = {}
            for kf in keyframes:
                ch = kf.get("channel", "unknown")
                ch_counts[ch] = ch_counts.get(ch, 0) + 1
            for ch, kf_count in ch_counts.items():
                structure.add((bone_name, ch, kf_count))
        struct_key = frozenset(structure)
        if struct_key not in anim_structures:
            anim_structures[struct_key] = []
        anim_structures[struct_key].append(name)
    
    for struct, names in anim_structures.items():
        if len(names) > 1:
            print(f"\n  Structurally similar animations (same bones + channels + keyframe counts):")
            for n in names:
                print(f"    - \"{n}\"")
            # Show the common structure
            for bone, ch, kf_count in sorted(struct):
                print(f"      {bone}.{ch}: {kf_count} keyframes")


def main():
    print("=" * 80)
    print("BBMODEL COMPLEXITY ANALYSIS — MROLF-TGNBF")
    print("=" * 80)
    print()
    
    results = scan_all_bbmodels()
    
    # Sort by complexity
    results.sort(key=lambda x: x["complexity"], reverse=True)
    
    print("TOP 10 MOST COMPLEX .bbmodel FILES")
    print("(Complexity = total_keyframes × animation_count)")
    print("-" * 80)
    print(f"{'Rank':<5} {'File':<40} {'Anims':<7} {'Keyframes':<11} {'Bones':<7} {'Channels':<9} {'Complexity':<12}")
    print("-" * 80)
    
    for i, r in enumerate(results[:10], 1):
        print(f"{i:<5} {r['path']:<40} {r['animations']:<7} {r['total_keyframes']:<11} {r['bones']:<7} {r['bone_channels']:<9} {r['complexity']:<12}")
    
    print()
    print("TOP 5 BY TOTAL KEYFRAMES (absolute)")
    print("-" * 80)
    by_kf = sorted(results, key=lambda x: x["total_keyframes"], reverse=True)
    print(f"{'Rank':<5} {'File':<40} {'Anims':<7} {'Keyframes':<11} {'Bones':<7} {'Channels':<9}")
    print("-" * 80)
    for i, r in enumerate(by_kf[:5], 1):
        print(f"{i:<5} {r['path']:<40} {r['animations']:<7} {r['total_keyframes']:<11} {r['bones']:<7} {r['bone_channels']:<9}")
    
    print()
    print("TOP 5 BY ANIMATION COUNT")
    print("-" * 80)
    by_anims = sorted(results, key=lambda x: x["animations"], reverse=True)
    print(f"{'Rank':<5} {'File':<40} {'Anims':<7} {'Keyframes':<11} {'Bones':<7}")
    print("-" * 80)
    for i, r in enumerate(by_anims[:5], 1):
        print(f"{i:<5} {r['path']:<40} {r['animations']:<7} {r['total_keyframes']:<11} {r['bones']:<7}")
    
    print()
    print("MODELS WITH 0 ANIMATIONS")
    print("-" * 80)
    no_anim = [r for r in results if r["animations"] == 0]
    for r in no_anim:
        print(f"  {r['path']} ({r['bones']} bones)")
    print(f"  Total: {len(no_anim)} files with no animations")
    
    # Now analyze ferHuman specifically
    ferhuman_path = os.path.join(BASE_DIR, "feral", "ferHuman.bbmodel")
    if os.path.exists(ferhuman_path):
        analyze_ferhuman(ferhuman_path)
    else:
        print(f"\nferHuman.bbmodel not found at {ferhuman_path}")
    
    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
