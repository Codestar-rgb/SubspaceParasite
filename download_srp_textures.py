#!/usr/bin/env python3
"""
Download SRP variant textures from GitHub repository.
Repo: https://github.com/Codestar-rgb/Qom-Inseac
"""

import json
import os
import subprocess
import sys
import time

BASE_RAW_URL = "https://raw.githubusercontent.com/Codestar-rgb/Qom-Inseac/main"
TEXTURE_BASE_PATH = "src/main/resources/assets/subspaceparasite/textures/entity"
OUTPUT_BASE = "/home/z/my-project/MROLF-TGNBF/bedrock/textures"
JSON_OUTPUT = "/home/z/my-project/MROLF-TGNBF/texture_variants.json"

# Category mapping for each model
MODEL_CATEGORIES = {
    # Abomination
    "abobodies": "abomination",
    "abohead": "abomination",
    # Primitive
    "bano": "primitive",
    "canra": "primitive",
    "emana": "primitive",
    "gim": "primitive",
    "hull": "primitive",
    "iki": "primitive",
    "lum": "primitive",
    "nogla": "primitive",
    "ranrac": "primitive",
    "shyco": "primitive",
    "wymo": "primitive",
    "zaa": "primitive",
    # Adapted
    "banoAdapted": "adapted",
    "canraAdapted": "adapted",
    "emanaAdapted": "adapted",
    "gimAdapted": "adapted",
    "hullAdapted": "adapted",
    "ikiAdapted": "adapted",
    "lumAdapted": "adapted",
    "noglaAdapted": "adapted",
    "ranracAdapted": "adapted",
    "shycoAdapted": "adapted",
    "wymoAdapted": "adapted",
    "zaaAdapted": "adapted",
    # Focused
    "banoFocused": "focused",
    "shycoFocused": "focused",
    # Derived
    "heblu": "derived",
    "kirin": "derived",
    "venkrolsiv": "derived",
    # Pure
    "alafha": "pure",
    "anged": "pure",
    "esor": "pure",
    "flam": "pure",
    "flog": "pure",
    "ganro": "pure",
    "jinjo": "pure",
    "omboo": "pure",
    "orch": "pure",
    "pheon": "pure",
    "vesta": "pure",
    "elvia": "pure",
    "lencia": "pure",
    "tenn": "pure",
    "rond": "pure",
    # Infected
    "dorpa": "infected",
    # Inborn
    "nuuh": "inborn",
    "mudo": "inborn",
    # Misc
    "orbscary": "misc",
    "orbvoid": "misc",
    "bombhost": "misc",
    "bombjinjo": "misc",
    "bombomboo": "misc",
    # Deterrent
    "venkrol": "deterrent",
    "venkrolsii": "deterrent",
    "venkrolsiii": "deterrent",
    "venkrolsv": "deterrent",
}

# Model name -> list of variant texture filenames (without .png)
VARIANT_TEXTURES = {
    "heblu": ["heblumc"],
    "venkrolsiv": ["venkrolsiv_glow"],
    "venkrolsii": ["venkrolsii_glow"],
    "venkrolsiii": ["venkrolsiii_glow"],
    "venkrol": ["venkrol_glow"],
    "bano": ["banoh", "banoa", "banoab", "banoah", "banoav", "banov"],
    "canra": ["canrah", "canraa", "canraab", "canraah", "canraav", "canrab", "canrav"],
    "emana": ["emanah", "emanaa", "emanaah"],
    "gim": ["gima"],
    "hull": ["hullh", "hull_old", "hullh_old", "hulla_old", "hullah_old"],
    "iki": ["ikia"],
    "lum": ["lumh", "luma"],
    "nogla": ["noglah", "noglaa", "noglaab", "noglaah", "noglaav", "noglab", "noglasp1", "noglav"],
    "ranrac": ["ranrach", "ranraca", "ranracab", "ranracah", "ranracav", "ranracb", "ranracv"],
    "shyco": ["shycoh", "shycoa", "shycoaabyss", "shycoab", "shycoah", "shycoalovecraft", "shycoatyrant", "shycoav", "shycob", "shycov"],
    "wymo": ["wymoa"],
    "zaa": ["zaaa"],
    "alafha": ["alafhah"],
    "anged": ["angedh"],
    "esor": ["esorh"],
    "flog": ["flogb", "flogh", "flogv"],
    "ganro": ["ganroh"],
    "omboo": ["ombooh"],
    "orch": ["orchh", "orchsp1"],
    "pheon": ["pheonsp1"],
    "vesta": ["vesta1", "vestare"],
    "dorpa": ["dorpa2"],
    "nuuh": ["nuuhb", "nuuhv"],
    "mudo": ["mudob", "mudov"],
    "orbscary": ["orbscary_armor"],
    "orbvoid": ["orbvoid_armor"],
    "bombhost": ["bombh"],
    "bombjinjo": ["bombj"],
    "bombomboo": ["bombo"],
}

# Layer textures (overlay textures) - these go in a "layer" subfolder
LAYER_TEXTURES = {
    "cosmichasking": {"category": "layer", "model": "heblu", "desc": "cosmic variant overlay"},
    "messnow": {"category": "layer", "model": None, "desc": "snow overlay"},
    "vestasnow": {"category": "layer", "model": "vesta", "desc": "vesta snow overlay"},
}


def download_file(url, dest_path):
    """Download a file using curl. Returns True on success."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    try:
        result = subprocess.run(
            ["curl", "-sS", "-f", "-L", "-o", dest_path, url],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            return True
        else:
            # Clean up empty/failed files
            if os.path.exists(dest_path):
                os.remove(dest_path)
            return False
    except subprocess.TimeoutExpired:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return False
    except Exception as e:
        print(f"  Error downloading {url}: {e}")
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return False


def main():
    success_count = 0
    fail_count = 0
    skipped_count = 0
    total_count = 0

    results = {}
    texture_variants_json = {}

    print("=" * 70)
    print("SRP Variant Texture Downloader")
    print("=" * 70)

    # ------------------------------------------------------------------
    # 1. Download monster variant textures
    # ------------------------------------------------------------------
    print("\n--- Downloading monster variant textures ---\n")

    for model_name, variants in sorted(VARIANT_TEXTURES.items()):
        category = MODEL_CATEGORIES.get(model_name)
        if not category:
            print(f"  WARNING: No category for model '{model_name}', skipping")
            skipped_count += len(variants)
            continue

        texture_variants_json[model_name] = {
            "category": category,
            "base_texture": f"{model_name}.png",
            "variants": []
        }

        for variant in variants:
            total_count += 1
            filename = f"{variant}.png"
            github_path = f"{TEXTURE_BASE_PATH}/monster/{filename}"
            url = f"{BASE_RAW_URL}/{github_path}"
            dest_dir = os.path.join(OUTPUT_BASE, category)
            dest_path = os.path.join(dest_dir, filename)

            print(f"  [{model_name}] Downloading {filename} -> {category}/{filename} ... ", end="")
            ok = download_file(url, dest_path)

            if ok:
                print("OK")
                success_count += 1
                texture_variants_json[model_name]["variants"].append({
                    "name": variant,
                    "filename": filename,
                    "source_path": github_path,
                    "local_path": f"bedrock/textures/{category}/{filename}"
                })
            else:
                print("FAILED")
                fail_count += 1
                texture_variants_json[model_name]["variants"].append({
                    "name": variant,
                    "filename": filename,
                    "source_path": github_path,
                    "local_path": None,
                    "download_failed": True
                })

            # Small delay to be nice to GitHub
            time.sleep(0.1)

    # ------------------------------------------------------------------
    # 2. Download layer textures
    # ------------------------------------------------------------------
    print("\n--- Downloading layer textures ---\n")

    texture_variants_json["_layer_textures"] = []

    for tex_name, info in sorted(LAYER_TEXTURES.items()):
        total_count += 1
        filename = f"{tex_name}.png"
        category = info["category"]
        github_path = f"{TEXTURE_BASE_PATH}/layer/{filename}"
        url = f"{BASE_RAW_URL}/{github_path}"
        dest_dir = os.path.join(OUTPUT_BASE, category)
        dest_path = os.path.join(dest_dir, filename)

        print(f"  Downloading {filename} -> {category}/{filename} ... ", end="")
        ok = download_file(url, dest_path)

        if ok:
            print("OK")
            success_count += 1
            texture_variants_json["_layer_textures"].append({
                "name": tex_name,
                "filename": filename,
                "category": category,
                "model": info["model"],
                "description": info["desc"],
                "source_path": github_path,
                "local_path": f"bedrock/textures/{category}/{filename}"
            })
        else:
            print("FAILED")
            fail_count += 1
            texture_variants_json["_layer_textures"].append({
                "name": tex_name,
                "filename": filename,
                "category": category,
                "model": info["model"],
                "description": info["desc"],
                "source_path": github_path,
                "local_path": None,
                "download_failed": True
            })

        time.sleep(0.1)

    # ------------------------------------------------------------------
    # 3. Also try to download base monster textures (the model's own .png)
    #    for any model that has variants, in case they're missing locally
    # ------------------------------------------------------------------
    print("\n--- Checking base textures for models with variants ---\n")

    for model_name in sorted(VARIANT_TEXTURES.keys()):
        category = MODEL_CATEGORIES.get(model_name)
        if not category:
            continue

        filename = f"{model_name}.png"
        dest_dir = os.path.join(OUTPUT_BASE, category)
        dest_path = os.path.join(dest_dir, filename)

        # Only download if not already present locally
        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            print(f"  [{model_name}] Base texture already exists: {category}/{filename}")
            continue

        total_count += 1
        github_path = f"{TEXTURE_BASE_PATH}/monster/{filename}"
        url = f"{BASE_RAW_URL}/{github_path}"

        print(f"  [{model_name}] Downloading base {filename} -> {category}/{filename} ... ", end="")
        ok = download_file(url, dest_path)

        if ok:
            print("OK")
            success_count += 1
        else:
            print("FAILED (may exist elsewhere)")
            fail_count += 1

        time.sleep(0.1)

    # ------------------------------------------------------------------
    # 4. Save the JSON mapping
    # ------------------------------------------------------------------
    print(f"\n--- Saving texture_variants.json ---\n")

    os.makedirs(os.path.dirname(JSON_OUTPUT), exist_ok=True)
    with open(JSON_OUTPUT, "w") as f:
        json.dump(texture_variants_json, f, indent=2)

    print(f"  Saved to: {JSON_OUTPUT}")

    # ------------------------------------------------------------------
    # 5. Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("DOWNLOAD SUMMARY")
    print("=" * 70)
    print(f"  Total attempted:  {total_count}")
    print(f"  Successful:       {success_count}")
    print(f"  Failed:           {fail_count}")
    print(f"  Skipped:          {skipped_count}")
    print(f"  Success rate:     {success_count/total_count*100:.1f}%" if total_count > 0 else "  N/A")
    print("=" * 70)

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
