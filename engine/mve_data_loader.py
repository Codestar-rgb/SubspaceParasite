#!/usr/bin/env python3
"""
MVE Data Loader (v6.3)
=======================
Loads MVE-captured animation data and converts it to AnimationIR objects
for the converter pipeline.

The MVE data is PREFERRED over:
  - Upstream GeckoLib JSON (which is missing states, attack fade, etc.)
  - Java trig simulator stub recovery (which only generates state 0 idle)

When MVE data is available for a model, this loader produces:
  - One AnimationIR per captured state (idle, state1, state2, ...)
  - The attack fade is handled by runtime_behavior_injector (Molnet)
  - Visibility variants are handled by runtime_behavior_injector

The loader converts captured bone transforms (rotation degrees, position
pixels) into KeyframeData objects with explicit AxisValues.
"""

from __future__ import annotations

import json
import os
import logging
from typing import Any, Dict, List, Optional, Tuple

from core.types import (
    AnimationIR,
    AxisValue,
    BoneAnimationIR,
    KeyframeData,
)

logger = logging.getLogger(__name__)


def _get_mve_output_dir():
    try:
        import config
        return config.MVE_DATA_DIR
    except ImportError:
        import os
        return os.environ.get("SRP_MVE_DIR", "/home/z/my-project/subspace-work/mve-capture/data")

MVE_OUTPUT_DIR = _get_mve_output_dir()


def has_mve_data(model_name: str, mve_dir: str = MVE_OUTPUT_DIR) -> bool:
    """Check if MVE capture data exists for a model."""
    return os.path.isfile(os.path.join(mve_dir, f"{model_name}.mve.json"))


def load_mve_data(model_name: str, mve_dir: str = MVE_OUTPUT_DIR) -> Optional[dict]:
    """Load MVE capture data for a model."""
    path = os.path.join(mve_dir, f"{model_name}.mve.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("[%s] Failed to load MVE data: %s", model_name, e)
        return None


def _animation_signature(anim: AnimationIR) -> str:
    """Compute a NUMERIC signature for an animation to detect visual duplicates.

    Uses rounded value statistics (min/max/mean per bone per axis) rounded to
    the nearest degree, so animations that differ only in sub-degree precision
    are detected as duplicates.
    """
    parts = []
    for bone_name in sorted(anim.bones.keys()):
        ba = anim.bones[bone_name]
        rot_vals = {"x": [], "y": [], "z": []}
        pos_vals = {"x": [], "y": [], "z": []}
        for kf in ba.keyframes:
            if kf.channel == "rotation":
                rot_vals["x"].append(kf.x.value)
                rot_vals["y"].append(kf.y.value)
                rot_vals["z"].append(kf.z.value)
            elif kf.channel == "position":
                pos_vals["x"].append(kf.x.value)
                pos_vals["y"].append(kf.y.value)
                pos_vals["z"].append(kf.z.value)
        bone_sig = bone_name
        for ch_name, vals in (("rot", rot_vals), ("pos", pos_vals)):
            for axis in ("x", "y", "z"):
                v = vals[axis]
                if v:
                    # Round to nearest degree to suppress sub-degree noise
                    vmin = round(min(v))
                    vmax = round(max(v))
                    vmean = round(sum(v) / len(v))
                    bone_sig += f"|{ch_name}{axis}:{vmin},{vmax},{vmean}"
        parts.append(bone_sig)
    return "|".join(parts)


def _animations_visually_similar(a1: AnimationIR, a2: AnimationIR, threshold: float = 2.0) -> bool:
    """Check if two animations are visually similar (differences below threshold).

    Compares bone sets and value ranges. Returns True if:
      - Same bone set
      - For each bone, max absolute difference in (min, max, mean) per axis
        is below `threshold` degrees/pixels
    """
    if set(a1.bones.keys()) != set(a2.bones.keys()):
        return False
    for bone_name in a1.bones:
        b1 = a1.bones[bone_name]
        b2 = a2.bones[bone_name]
        for ch in ("rotation", "position"):
            kfs1 = [kf for kf in b1.keyframes if kf.channel == ch]
            kfs2 = [kf for kf in b2.keyframes if kf.channel == ch]
            if bool(kfs1) != bool(kfs2):
                return False
            if not kfs1:
                continue
            for axis in ("x", "y", "z"):
                vals1 = [getattr(kf, axis).value for kf in kfs1]
                vals2 = [getattr(kf, axis).value for kf in kfs2]
                # Compare statistics
                stats1 = (min(vals1), max(vals1), sum(vals1)/len(vals1))
                stats2 = (min(vals2), max(vals2), sum(vals2)/len(vals2))
                for s1, s2 in zip(stats1, stats2):
                    if abs(s1 - s2) > threshold:
                        return False
    return True


def mve_to_animations(mve_data: dict) -> List[AnimationIR]:
    """Convert MVE-captured states to AnimationIR objects, deduplicating identical states.

    Each captured state becomes one AnimationIR with:
      - name: animation.srparasites.<model>.<action>
      - loop: "loop" for continuous states
      - length: cycle length in seconds
      - bones: dict of bone_name → BoneAnimationIR with keyframes

    Keyframes are created for BOTH rotation and position channels (whichever
    have non-zero values in the captured data, PLUS t=0/t=length boundary
    keyframes which are always kept for seamless looping).

    IDENTICAL STATE DEDUPLICATION:
      If two states produce byte-identical animations (e.g. stage1_idle and
      stage2_idle have the same else-branch code), only the FIRST is kept.
      This avoids cluttering the .bbmodel with duplicate animations.
    """
    model_name = mve_data.get("model", "unknown")
    animations = []

    for state in mve_data.get("states", []):
        anim_name = state["name"]
        length = state["length"]
        bones: Dict[str, BoneAnimationIR] = {}

        for bone_name, curve in state["bones"].items():
            keyframes: List[KeyframeData] = []
            # Always preserve t=0 and t=length keyframes for seamless looping
            anim_length = state["length"]
            boundary_times = {0.0, anim_length}

            for sample in curve:
                t = sample["time"]
                rot = sample["rotation"]  # [x, y, z] in degrees
                pos = sample["position"]  # [x, y, z] in pixels
                is_boundary = any(abs(t - bt) < 1e-4 for bt in boundary_times)

                # Rotation keyframe: keep if non-zero OR boundary (t=0/t=length)
                if any(abs(v) > 1e-6 for v in rot) or is_boundary:
                    kf = KeyframeData(
                        time=t,
                        channel="rotation",
                        x=AxisValue.explicit_val(rot[0]),
                        y=AxisValue.explicit_val(rot[1]),
                        z=AxisValue.explicit_val(rot[2]),
                        easing="linear",
                        interpolation="linear",
                    )
                    keyframes.append(kf)

                # Position keyframe: keep if non-zero OR boundary
                if any(abs(v) > 1e-6 for v in pos) or is_boundary:
                    kf = KeyframeData(
                        time=t,
                        channel="position",
                        x=AxisValue.explicit_val(pos[0]),
                        y=AxisValue.explicit_val(pos[1]),
                        z=AxisValue.explicit_val(pos[2]),
                        easing="linear",
                        interpolation="linear",
                    )
                    keyframes.append(kf)

            if keyframes:
                bones[bone_name] = BoneAnimationIR(bone_name=bone_name, keyframes=keyframes)

        if bones:
            anim = AnimationIR(
                name=anim_name,
                loop=state.get("loop", "loop"),
                length=length,
                bones=bones,
            )
            # Dedup: skip if a visually similar animation was already added.
            # "Visually similar" = same bone set + value ranges within 2 degrees.
            # This catches stage1_idle/stage2_idle which differ only in sub-degree
            # trig frequency but look identical to the eye.
            is_duplicate = False
            # Dedup threshold from config (env-overridable)
            try:
                import config
                dedup_threshold = config.DEDUP_THRESHOLD
            except ImportError:
                dedup_threshold = 2.0
            for existing in animations:
                if _animations_visually_similar(anim, existing, threshold=dedup_threshold):
                    logger.debug(
                        "[%s] Skipping visually-similar state anim '%s' (≈ '%s')",
                        model_name, anim_name, existing.name,
                    )
                    is_duplicate = True
                    break
            if is_duplicate:
                continue
            animations.append(anim)

    logger.debug(
        "[%s] MVE loaded: %d animations (after dedup), %d total bones",
        model_name, len(animations),
        sum(len(a.bones) for a in animations),
    )
    return animations


def get_mve_animations_for_model(
    model_name: str,
    mve_dir: str = MVE_OUTPUT_DIR,
) -> Tuple[Optional[List[AnimationIR]], Optional[dict]]:
    """Load MVE data and convert to AnimationIR list.

    Returns:
        (animations, mve_raw_data) or (None, None) if no MVE data.
        The mve_raw_data is kept for runtime_behavior_injector to use
        (attack_fade, visibility info).
    """
    mve_data = load_mve_data(model_name, mve_dir)
    if not mve_data:
        return None, None
    animations = mve_to_animations(mve_data)
    if not animations:
        return None, None
    return animations, mve_data
