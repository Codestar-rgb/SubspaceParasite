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

MVE_OUTPUT_DIR = "/home/z/my-project/subspace-work/mve-capture/data"


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


def mve_to_animations(mve_data: dict) -> List[AnimationIR]:
    """Convert MVE-captured states to AnimationIR objects.

    Each captured state becomes one AnimationIR with:
      - name: animation.srparasites.<model>.<action>
      - loop: "loop" for continuous states
      - length: cycle length in seconds
      - bones: dict of bone_name → BoneAnimationIR with keyframes

    Keyframes are created for BOTH rotation and position channels (whichever
    have non-zero values in the captured data).
    """
    model_name = mve_data.get("model", "unknown")
    animations = []

    for state in mve_data.get("states", []):
        anim_name = state["name"]
        length = state["length"]
        bones: Dict[str, BoneAnimationIR] = {}

        for bone_name, curve in state["bones"].items():
            keyframes: List[KeyframeData] = []

            # Group by time; each time point may produce rotation + position kfs
            for sample in curve:
                t = sample["time"]
                rot = sample["rotation"]  # [x, y, z] in degrees
                pos = sample["position"]  # [x, y, z] in pixels

                # Rotation keyframe (if any non-zero)
                if any(abs(v) > 1e-6 for v in rot):
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

                # Position keyframe (if any non-zero)
                if any(abs(v) > 1e-6 for v in pos):
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
            animations.append(anim)

    logger.info(
        "[%s] MVE loaded: %d animations, %d total bones",
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
