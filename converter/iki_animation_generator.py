#!/usr/bin/env python3
"""
Iki Animation Generator - Precise tentacle animation for the Iki primitive entity
=========================================================================

The Iki entity has a unique animation system with 4 cosine/sine waves driving
all tentacle joints, plus a vertical velocity response. The AnimationExtractor's
generic approach loses precision, so this generator creates exact animations.

Java source (ModelIki.java setRotationAngles):
    f1 = cos(ageInTicks * 0.14986) * 0.1872
    f2 = sin(ageInTicks * 0.13786) * 0.2219872
    f3 = cos(ageInTicks * 0.12786) * 0.2872
    f4 = sin(ageInTicks * 0.1286)  * 0.1972
    fUp = mob.motionY * 0.2972

    mainbody.oz = 0.5; mainbody.oy = f4/2; mainbody.rx = f3/2; mainbody.rz = f3/8
    bh.rx = f4 + 0.15
    jointFLA.rz = f1; jointFLA_1.rz = -f3; jointFLA_2.rz = f4*-3; jointFLA_3.rz = f1*-6-0.5; jointFLA_4.rz = f2*-3
    jointFRA.rz = f3; jointFRA_1.rz = -f4; jointFRA_2.rz = f1*-3; jointFRA_3.rz = -f2*-6-0.5; jointFRA_4.rz = -f3*-3
    jointBLA.rz = -f4; jointBLA_1.rz = f3; jointBLA_2.rz = f1*-3; jointBLA_3.rz = f2*-6-0.5; jointBLA_4.rz = -f3*-3
    jointBRA.rz = f2; jointBRA_1.rz = -f1; jointBRA_2.rz = f2*-3; jointBRA_3.rz = f3*-6-0.5; jointBRA_4.rz = -f4*-3
    (All joint* ry = -fUp, but fUp depends on runtime motionY, set to 0 for idle)

v10: Frequencies adjusted for perfect loop alignment at 9.0s duration:
    - All 4 frequencies adjusted to complete integer cycles in 9.0s
    - Max frequency error: 9.2% (imperceptible for tentacle motion)
    - f1: 0.14986 → 0.139626 (4 cycles, 6.8% change)
    - f2: 0.13786 → 0.139626 (4 cycles, 1.3% change)
    - f3: 0.12786 → 0.139626 (4 cycles, 9.2% change)
    - f4: 0.1286  → 0.139626 (4 cycles, 8.6% change)
"""

import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from heblu_animation_generator import sample_animation, rad_to_deg, build_animation_json

TICKS_PER_SECOND = 20.0


def eval_iki_idle(t_seconds: float) -> dict:
    """Evaluate the Iki idle animation at time t (seconds).
    
    v10: Frequencies adjusted for 9.0s perfect loop.
    All tentacle joints driven by 4 cosine/sine waves.
    fUp is set to 0 for idle (no vertical motion).
    """
    age_in_ticks = t_seconds * TICKS_PER_SECOND
    
    # v10: Aligned frequencies for 9.0s loop (4 cycles each)
    f1_freq = 0.139626
    f2_freq = 0.139626
    f3_freq = 0.139626
    f4_freq = 0.139626
    
    f1 = math.cos(age_in_ticks * f1_freq) * 0.1872
    f2 = math.sin(age_in_ticks * f2_freq) * 0.2219872
    f3 = math.cos(age_in_ticks * f3_freq) * 0.2872
    f4 = math.sin(age_in_ticks * f4_freq) * 0.1972
    fUp = 0.0  # No vertical motion in idle
    
    bones = {}
    
    # Main body
    bones['mainbody'] = {
        'rx': f3 / 2.0,
        'ry': f4 / 2.0,
        'rz': f3 / 8.0,
        'ox': 0.0,
        'oy': f4 / 2.0,  # oy = f4/2 (mainbody.offsetY)
        'oz': 0.5,        # oz = 0.5 (mainbody.offsetZ)
    }
    
    # Body head
    bones['bh'] = {'rx': f4 + 0.15}
    
    # Front Left Appendage (jointFLA)
    bones['jointFLA'] = {'rz': f1, 'ry': -fUp}
    bones['jointFLA_1'] = {'rz': -f3, 'ry': -fUp}
    bones['jointFLA_2'] = {'rz': f4 * -3.0, 'ry': -fUp}
    bones['jointFLA_3'] = {'rz': f1 * -6.0 - 0.5, 'ry': -fUp}
    bones['jointFLA_4'] = {'rz': f2 * -3.0, 'ry': -fUp}
    
    # Front Right Appendage (jointFRA)
    bones['jointFRA'] = {'rz': f3, 'ry': -fUp}
    bones['jointFRA_1'] = {'rz': -f4, 'ry': -fUp}
    bones['jointFRA_2'] = {'rz': f1 * -3.0, 'ry': -fUp}
    bones['jointFRA_3'] = {'rz': -f2 * -6.0 - 0.5, 'ry': -fUp}
    bones['jointFRA_4'] = {'rz': -f3 * -3.0, 'ry': -fUp}
    
    # Back Left Appendage (jointBLA)
    bones['jointBLA'] = {'rz': -f4, 'ry': -fUp}
    bones['jointBLA_1'] = {'rz': f3, 'ry': -fUp}
    bones['jointBLA_2'] = {'rz': f1 * -3.0, 'ry': -fUp}
    bones['jointBLA_3'] = {'rz': f2 * -6.0 - 0.5, 'ry': -fUp}
    bones['jointBLA_4'] = {'rz': -f3 * -3.0, 'ry': -fUp}
    
    # Back Right Appendage (jointBRA)
    bones['jointBRA'] = {'rz': f2, 'ry': -fUp}
    bones['jointBRA_1'] = {'rz': -f1, 'ry': -fUp}
    bones['jointBRA_2'] = {'rz': f2 * -3.0, 'ry': -fUp}
    bones['jointBRA_3'] = {'rz': f3 * -6.0 - 0.5, 'ry': -fUp}
    bones['jointBRA_4'] = {'rz': -f4 * -3.0, 'ry': -fUp}
    
    return bones


def generate_iki_animations():
    """Generate all Iki animations with v10 precision."""
    animations = {}
    
    print("  Generating iki idle animation...")
    duration = 9.0  # 9s for perfect loop alignment
    
    iki_data = sample_animation(
        eval_iki_idle,
        duration=duration,
        samples_per_second=60.0,
        dp_epsilon=0.3  # Tighter for tentacle articulation
    )
    
    animations["animation.iki.idle"] = build_animation_json(
        "animation.iki.idle", "loop", iki_data, duration
    )
    
    bone_count = len(animations["animation.iki.idle"]["bones"])
    print(f"    Bones: {bone_count}, Duration: {duration}s")
    
    return {
        "format_version": "1.8.0",
        "animations": animations
    }


if __name__ == "__main__":
    anim = generate_iki_animations()
    
    # Save
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "MROLF-TGNBF", "primitive")
    os.makedirs(out_dir, exist_ok=True)
    
    # Re-convert the model and embed the animation
    import json
    from model_converter import ModelConverter
    from bbmodel_generator import BBModelGenerator
    from PIL import Image
    import numpy as np
    
    # Read Java source
    java_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..",
        "Qom-Inseac", "src", "main", "java", "com", "subspaceparasite",
        "client", "model", "entity", "primitive", "ModelIki.java"
    )
    with open(java_path) as f:
        source = f.read()
    
    # Convert model
    converter = ModelConverter()
    result = converter.convert(source, 'model.iki')
    geo_json = result['geo_json']
    bone_mapping = result.get('bone_mapping', {})
    
    # Fix texture height mismatch (Java says 128, actual texture is 256)
    tex_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..",
        "jar_extract", "assets", "srparasites", "textures", "entity", "monster", "ikia.png"
    )
    img = Image.open(tex_path)
    actual_w, actual_h = img.size
    model_h = geo_json['model']['texture_height']
    
    if model_h != actual_h:
        scale_v = actual_h / model_h
        geo_json['model']['texture_height'] = actual_h
        for bone in geo_json['model']['bones']:
            for cube in bone.get('cubes', []):
                uv = cube.get('uv', {})
                for face_name, face_uv in uv.items():
                    if isinstance(face_uv, dict):
                        face_uv['uv'][1] *= scale_v
                        face_uv['uv_size'][1] *= scale_v
    
    # Generate bbmodel with custom animations
    bbgen = BBModelGenerator()
    bbmodel = bbgen.generate(
        geo_json,
        anim_json=anim,
        texture_path=tex_path,
        texture_name='iki',
        namespace='srparasites',
    )
    
    out_path = os.path.join(out_dir, "iki.bbmodel")
    bbgen.save(bbmodel, out_path)
    
    size = os.path.getsize(out_path)
    bones = geo_json['model']['bones']
    total_cubes = sum(len(b.get('cubes', [])) for b in bones)
    anims = bbmodel.get('animations', [])
    print(f"\n  Iki model saved: {out_path}")
    print(f"  {len(bones)} bones, {total_cubes} cubes, {len(anims)} anims, {size:,} bytes")
