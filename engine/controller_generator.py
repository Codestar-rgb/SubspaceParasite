#!/usr/bin/env python3
"""
GeckoLib Animation Controller Generator (v6.9)
================================================
Generates a basic animation_controllers.json skeleton for GeckoLib 4
(1.20.1) that defines state transitions with blend transitions.

This file should be placed alongside the .bbmodel files in the mod's
 GeckoLib resource directory:
  assets/<modid>/animations/<entity>_animation_controllers.json

The controller defines:
  - idle → walk (based on query.modified_distance_moved)
  - walk → idle (when stopped)
  - idle/walk → attack (based on query.attack_time)
  - attack → idle (after attack finishes)
  - any → death (based on custom variable)
  - state-specific animations (stage1_idle, stage2_walk, etc.)

Mod developers need to:
  1. Set custom Molang variables (variable.parasite_stage, variable.attack_time)
  2. Adjust transition thresholds as needed
  3. Add additional states for evolution stages
"""

import json
import os
from typing import List, Dict, Any


def generate_controller(model_name: str, animations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate a GeckoLib animation controller for one model.

    Args:
        model_name: Model name (e.g. "bano")
        animations: List of animation dicts from .bbmodel (with 'name' field)

    Returns:
        Dict representing the animation_controllers.json structure
    """
    anim_names = [a.get("name", "") for a in animations]

    # Detect available animations
    has_walk = any("walk" in n and "stage" not in n for n in anim_names)
    has_idle = any("idle" in n and "stage" not in n for n in anim_names)
    has_attack = any("attack" in n for n in anim_names)
    has_death = any("death" in n for n in anim_names)
    has_sleep = any("sleep" in n for n in anim_names)

    # Build controller states
    states = {}

    # Default state: idle or first available
    default_anim = f"animation.srparasites.{model_name}.idle" if has_idle else anim_names[0] if anim_names else ""
    states["default"] = {
        "animations": [default_anim],
        "transitions": []
    }

    if has_walk:
        states["default"]["transitions"].append({
            "walk": "query.modified_distance_moved > 0.1"
        })
        states["walk"] = {
            "animations": [f"animation.srparasites.{model_name}.walk"],
            "blend_transition": 0.1,
            "transitions": [
                {"default": "query.modified_distance_moved < 0.1"}
            ]
        }

    if has_attack:
        states["default"]["transitions"].append({
            "attack": "query.attack_time > 0.0"
        })
        if has_walk:
            states["walk"]["transitions"].append({
                "attack": "query.attack_time > 0.0"
            })
        states["attack"] = {
            "animations": [f"animation.srparasites.{model_name}.attack"],
            "blend_transition": 0.05,
            "transitions": [
                {"default": "query.attack_time > 0.5"}
            ]
        }

    if has_sleep:
        states["default"]["transitions"].append({
            "sleeping": "variable.is_sleeping"
        })
        states["sleeping"] = {
            "animations": [f"animation.srparasites.{model_name}.sleeping"],
            "blend_transition": 0.3,
            "transitions": [
                {"default": "!variable.is_sleeping"}
            ]
        }

    if has_death:
        for state_name in list(states.keys()):
            if state_name != "death":
                states[state_name]["transitions"].append({
                    "death": "variable.is_dead"
                })
        states["death"] = {
            "animations": [f"animation.srparasites.{model_name}.death_idle"] if any("death_idle" in n for n in anim_names) else [f"animation.srparasites.{model_name}.death"],
            "blend_transition": 0.2,
        }

    controller = {
        "format_version": "1.10.0",
        "animation_controllers": {
            f"controller.animation.{model_name}": {
                "initial_state": "default",
                "states": states
            }
        }
    }
    return controller


def generate_for_model(model_name: str, bbmodel_path: str, output_dir: str) -> str:
    """Generate controller JSON for a model and save to output_dir.

    Returns the output file path, or empty string if failed.
    """
    try:
        with open(bbmodel_path, 'r') as f:
            m = json.load(f)
        animations = m.get("animations", [])
        controller = generate_controller(model_name, animations)

        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, f"{model_name}_controllers.json")
        with open(out_path, 'w') as f:
            json.dump(controller, f, indent=2)
        return out_path
    except Exception as e:
        return ""
