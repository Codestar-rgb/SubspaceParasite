#!/usr/bin/env python3
"""
AnimationController Generator for SubspaceParasite Minecraft Mod
================================================================
Reads .bbmodel files from MODSRP directory and generates GeckoLib 4.x
AnimationController Java code for each model.

Problem Solved:
  In MC 1.12.2, setRotationAngles() is called every frame unconditionally
  with if/switch conditions embedded in the method body. In GeckoLib 1.20.1,
  animations are triggered by AnimationController based on state queries.
  Without generated controller code, the animations are "dead data" that
  never play. This generator bridges that gap by producing state-machine
  controller code from the animation names present in each .bbmodel file.

State Machine Priority (highest to lowest):
  1. death    -> entity.isDeadOrDying()
  2. special  -> entity.isVomiting() / isShaking() / isCosmic()
  3. attack   -> entity.getTarget() != null
  4. sleeping -> entity.isSleeping()
  5. evolved  -> entity.isEvolved()
  6. fly      -> !entity.onGround()
  7. walk     -> limbSwingAmount > 0.01F (smoothed via 0.4F Lerp)
  8. idle     -> default fallback (always true)

Usage:
  python3 animation_controller_generator.py [input_dir] [output_dir]

  Defaults:
    input_dir  = /home/z/my-project/MODSRP
    output_dir = /home/z/my-project/MODSRP-Code
"""

import json
import os
import re
import sys
from pathlib import Path
from collections import defaultdict, OrderedDict
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Set

# ============================================================================
# Configuration
# ============================================================================
MOD_ID = "srparasites"
PACKAGE_NAME = "com.srparasites.client.model"
ENTITY_PACKAGE = "com.srparasites.entity"
DEFAULT_INPUT_DIR = "/home/z/my-project/MODSRP"
DEFAULT_OUTPUT_DIR = "/home/z/my-project/MODSRP-Code"

# Animation category definitions.
# priority: higher = checked first in the state machine
# looping:  whether the animation should loop (thenLoop) or play once (thenPlay)
# transition: default transition length in ticks for blending
ANIMATION_CATEGORIES = OrderedDict([
    ("death",    {"keywords": ["death", "die"],              "priority": 70, "looping": False, "transition": 5}),
    ("special",  {"keywords": ["vomit", "shaking", "cosmic"],"priority": 60, "looping": True,  "transition": 3}),
    ("attack",   {"keywords": ["attack", "hit", "strike"],   "priority": 50, "looping": False, "transition": 3}),
    ("sleeping", {"keywords": ["sleeping", "sleep"],         "priority": 40, "looping": True,  "transition": 10}),
    ("evolved",  {"keywords": ["evolved", "transform"],      "priority": 30, "looping": True,  "transition": 15}),
    ("fly",      {"keywords": ["fly"],                       "priority": 20, "looping": True,  "transition": 5}),
    ("walk",     {"keywords": ["walk", "run", "move"],       "priority": 10, "looping": True,  "transition": 4}),
    ("idle",     {"keywords": ["idle", "stand"],             "priority": 0,  "looping": True,  "transition": 5}),
])

# State-based animation categories (open/closed, stage)
STATE_CATEGORIES = OrderedDict([
    ("open",   {"keywords": ["open"],   "priority": 10, "looping": True,  "transition": 5}),
    ("closed", {"keywords": ["closed"], "priority": 0,  "looping": True,  "transition": 5}),
    ("stage",  {"keywords": ["stage"],  "priority": 5,  "looping": True,  "transition": 10}),
])


# ============================================================================
# Name Conversion Utilities
# ============================================================================

def to_pascal_case(name: str) -> str:
    """Convert a camelCase or lowercase name to PascalCase for Java class names.

    Preserves all-caps abbreviations (SIVH, AWFL, SII, etc.) as-is since
    these represent evolution stage codes in the SRP mod.

    Examples:
        ata          -> Ata
        ferCow       -> FerCow
        dodSIVH      -> DodSIVH
        infPigHead   -> InfPigHead
        canraAdapted -> CanraAdapted
        oroncoAWFL   -> OroncoAWFL
        leemSIII     -> LeemSIII
    """
    # Split on camelCase boundaries while preserving all-caps groups
    parts = re.findall(r"[A-Z]+(?=[A-Z]|$)|[A-Z]?[a-z]+|[0-9]+", name)
    if not parts:
        return name.capitalize()

    result = []
    for part in parts:
        if part.isupper() and len(part) > 1:
            # All-caps abbreviation (SIVH, AWFL, SII, SIII, SV) -- keep as-is
            result.append(part)
        else:
            result.append(part[0].upper() + part[1:] if len(part) > 1 else part.upper())
    return "".join(result)


def to_entity_class(model_name: str) -> str:
    """Convert a model name to an entity class name.

    Examples:
        ata    -> EntityAta
        ferCow -> EntityFerCow
        dodSIVH -> EntityDodSIVH
    """
    return f"Entity{to_pascal_case(model_name)}"


def to_model_class(model_name: str) -> str:
    """Convert a model name to a model class name.

    Examples:
        ata    -> AtaModel
        ferCow -> FerCowModel
        dodSIVH -> DodSIVHModel
    """
    return f"{to_pascal_case(model_name)}Model"


# ============================================================================
# Animation Categorization
# ============================================================================

def categorize_animation(anim_name: str) -> Tuple[str, dict]:
    """Categorize an animation name into a category.

    Args:
        anim_name: Full animation name (e.g., "animation.ata.idle")

    Returns:
        Tuple of (category_name, category_info dict)
        category_name is one of the defined categories or 'unknown'
    """
    # Extract the state identifier (last segment after the final dot)
    parts = anim_name.split(".")
    state_name = parts[-1].lower()

    # Check standard categories first (higher priority ones first)
    for cat_name, cat_info in ANIMATION_CATEGORIES.items():
        for keyword in cat_info["keywords"]:
            if keyword in state_name:
                return cat_name, cat_info

    # Check state-based categories
    for cat_name, cat_info in STATE_CATEGORIES.items():
        for keyword in cat_info["keywords"]:
            if keyword in state_name:
                return cat_name, cat_info

    return "unknown", {"priority": -1, "looping": True, "transition": 5}


def categorize_all_animations(animation_names: List[str]) -> Dict[str, List[str]]:
    """Categorize all animation names from a model.

    Returns:
        Dict mapping category_name -> [animation_names] sorted by name
    """
    categories = defaultdict(list)
    for anim_name in animation_names:
        cat_name, _ = categorize_animation(anim_name)
        categories[cat_name].append(anim_name)
    # Sort animation names within each category for deterministic output
    return {k: sorted(v) for k, v in sorted(categories.items())}


def get_animation_complexity(categorized: Dict[str, List[str]]) -> str:
    """Determine the complexity level of a model's animation setup.

    Returns one of:
        'simple'    - only idle animation
        'basic'     - idle + walk only
        'standard'  - up to 3 animation categories
        'complex'   - 4+ animation categories (full state machine)
        'state'     - open/closed only (no idle/walk)
    """
    cats = set(categorized.keys())

    # State-based models (host, hostII) that only have open/closed
    if cats <= {"open", "closed"} and "idle" not in cats and "walk" not in cats:
        return "state"

    if len(cats) == 1 and "idle" in cats:
        return "simple"

    if len(cats) == 2 and "idle" in cats and "walk" in cats:
        return "basic"

    if len(cats) <= 3:
        return "standard"

    return "complex"


# ============================================================================
# Java Condition Generation
# ============================================================================

def generate_state_condition(category: str, entity_var: str, anim_name: str) -> str:
    """Generate the Java boolean condition for an animation state.

    Args:
        category: Animation category name
        entity_var: Variable name for the entity reference
        anim_name: Full animation name (for special cases like stage6, vomit)

    Returns:
        Java boolean expression string
    """
    conditions = {
        "death":    f"{entity_var}.isDeadOrDying()",
        "attack":   f"{entity_var}.getTarget() != null",
        "sleeping": f"{entity_var}.isSleeping()",
        "evolved":  f"{entity_var}.isEvolved()",
        "fly":      f"!{entity_var}.onGround()",
        "walk":     "this.limbSwingAmount > 0.01F",
        "idle":     "true",
        "open":     f"{entity_var}.isOpen()",
        "closed":   f"!{entity_var}.isOpen()",
    }

    # Handle categories that need per-animation customization
    if category == "special":
        return _generate_special_condition(entity_var, anim_name)
    if category == "stage":
        return _generate_stage_condition(entity_var, anim_name)

    return conditions.get(category, "true")


def _generate_special_condition(entity_var: str, anim_name: str) -> str:
    """Generate condition for special animations (vomit, shaking, cosmic)."""
    state_name = anim_name.split(".")[-1].lower()
    if "vomit" in state_name:
        return f"{entity_var}.isVomiting()"
    if "shaking" in state_name:
        return f"{entity_var}.isShaking()"
    if "cosmic" in state_name:
        return f"{entity_var}.isCosmic()"
    return f"{entity_var}.isSpecialState()"


def _generate_stage_condition(entity_var: str, anim_name: str) -> str:
    """Generate condition for stage animations (stage6, stage25, etc.)."""
    state_name = anim_name.split(".")[-1].lower()
    match = re.search(r"stage(\d+)", state_name)
    if match:
        stage_num = match.group(1)
        return f"{entity_var}.getStage() == {stage_num}"
    return f"{entity_var}.getStage() > 0"


def generate_raw_animation_call(anim_name: str, looping: bool) -> str:
    """Generate the RawAnimation Java code for an animation.

    GeckoLib 4.x API:
      - thenLoop(name)  for looping animations (idle, walk, fly, etc.)
      - thenPlay(name)  for one-shot animations (attack, death, etc.)
    """
    if looping:
        return f'RawAnimation.begin().thenLoop("{anim_name}")'
    else:
        return f'RawAnimation.begin().thenPlay("{anim_name}")'


# ============================================================================
# Java Model Class Generation
# ============================================================================

def generate_model_class(model_name: str, category: str,
                         categorized_anims: Dict[str, List[str]],
                         raw_animations: List[dict]) -> str:
    """Generate the complete Java model class with AnimationController code.

    Args:
        model_name: Model identifier (e.g., "ata", "ferCow")
        category: Category directory name (e.g., "inborn", "feral")
        categorized_anims: Dict mapping category_name -> [animation_names]
        raw_animations: Raw animation data from .bbmodel (for reference)
    """
    pascal_name = to_pascal_case(model_name)
    model_class = to_model_class(model_name)
    entity_class = to_entity_class(model_name)

    complexity = get_animation_complexity(categorized_anims)
    has_walk = "walk" in categorized_anims
    has_stage = "stage" in categorized_anims
    has_state_anim = bool(set(categorized_anims.keys()) & {"open", "closed"})
    has_special = "special" in categorized_anims
    has_fly = "fly" in categorized_anims

    # Determine which imports are needed
    imports = [
        "net.minecraft.resources.ResourceLocation",
        "software.bernie.geckolib.animation.AnimatableManager",
        "software.bernie.geckolib.animation.AnimationController",
        "software.bernie.geckolib.animation.PlayState",
        "software.bernie.geckolib.animation.RawAnimation",
        "software.bernie.geckolib.model.GeoModel",
        f"{ENTITY_PACKAGE}.{entity_class}",
    ]

    # Build code sections
    sections = []

    # ---- Package and imports ----
    sections.append(f"package {PACKAGE_NAME};")
    sections.append("")
    for imp in sorted(imports):
        sections.append(f"import {imp};")
    sections.append("")

    # ---- Class Javadoc ----
    sections.append("/**")
    sections.append(f" * GeckoLib 4.x Model class for {entity_class}.")
    sections.append(f" * Auto-generated by AnimationController Generator.")
    sections.append(f" *")
    sections.append(f" * Category: {category}")
    sections.append(f" * Complexity: {complexity}")
    sections.append(f" * Animations: {', '.join(sorted(categorized_anims.keys()))}")
    sections.append(f" *")

    # Document the active states in priority order
    active_states = []
    all_cats = {**ANIMATION_CATEGORIES, **STATE_CATEGORIES}
    for cat_name in categorized_anims:
        cat_info = all_cats.get(cat_name, {"priority": 0})
        active_states.append((cat_name, cat_info.get("priority", 0)))
    active_states.sort(key=lambda x: x[1], reverse=True)

    sections.append(" * State Machine Priority (highest to lowest):")
    for cat_name, _ in active_states:
        anim_names = categorized_anims[cat_name]
        sections.append(f" *   {cat_name}: {', '.join(anim_names)}")

    sections.append(" *")
    sections.append(" * NOTE: In GeckoLib 4.x for MC 1.20.1, registerControllers()")
    sections.append(" * is typically on the entity class that implements GeoAnimatable.")
    sections.append(" * This generated code can be placed on the model class if your")
    sections.append(" * setup delegates to it, or moved to the entity class where")
    sections.append(" * event.getAnimatable() will directly return the entity instance.")
    sections.append(" */")

    # ---- Class declaration ----
    sections.append(f"public class {model_class} extends GeoModel<{entity_class}> {{")
    sections.append("")

    # ---- Resource location constants ----
    sections.append("    private static final ResourceLocation MODEL =")
    sections.append(f"        new ResourceLocation(\"{MOD_ID}\", \"geo/{model_name}.geo.json\");")
    sections.append("    private static final ResourceLocation TEXTURE =")
    sections.append(f"        new ResourceLocation(\"{MOD_ID}\", \"textures/entity/monster/{model_name}.png\");")
    sections.append("    private static final ResourceLocation ANIMATION =")
    sections.append(f"        new ResourceLocation(\"{MOD_ID}\", \"animations/{model_name}.animation.json\");")
    sections.append("")

    # ---- limbSwingAmount fields (if walk animation exists) ----
    if has_walk:
        sections.append("    // ========================================================================")
        sections.append("    // limbSwingAmount Lerp Simulation")
        sections.append("    // ========================================================================")
        sections.append("    // Replicates MC 1.12.2's exponential decay smoothing for walk detection.")
        sections.append("    // In vanilla MC, the limbSwingAmount is interpolated each frame using:")
        sections.append("    //   limbSwingAmount += (targetAmount - limbSwingAmount) * 0.4F")
        sections.append("    // where targetAmount = horizontalDistance * 4.0F")
        sections.append("    //")
        sections.append("    // The 0.4F factor creates smooth acceleration/deceleration of the")
        sections.append("    // walk cycle, preventing pop-in when entities start/stop moving.")
        sections.append("    // Walk detection uses the smoothed value (> 0.01F) rather than")
        sections.append("    // raw movement to avoid animation flickering at low speeds.")
        sections.append("    //")
        sections.append("    // See SRPLimbSwingHelper.java for a reusable utility version.")
        sections.append("    private float prevLimbSwingAmount = 0.0F;")
        sections.append("    private float limbSwingAmount = 0.0F;")
        sections.append("")

    # ---- Resource override methods ----
    sections.append("    @Override")
    sections.append(f"    public ResourceLocation getModelResource({entity_class} entity) {{")
    sections.append("        return MODEL;")
    sections.append("    }")
    sections.append("")
    sections.append("    @Override")
    sections.append(f"    public ResourceLocation getTextureResource({entity_class} entity) {{")
    sections.append("        return TEXTURE;")
    sections.append("    }")
    sections.append("")
    sections.append("    @Override")
    sections.append(f"    public ResourceLocation getAnimationResource({entity_class} entity) {{")
    sections.append("        return ANIMATION;")
    sections.append("    }")
    sections.append("")

    # ---- registerControllers method ----
    sections.append("    /**")
    sections.append("     * Registers animation controllers with state machine logic.")
    sections.append("     *")
    sections.append("     * In MC 1.12.2, setRotationAngles() was called every frame with")
    sections.append("     * embedded if/switch conditions. In GeckoLib 1.20.1, animations are")
    sections.append("     * triggered by AnimationController based on entity state queries.")
    sections.append("     *")
    sections.append("     * The state machine checks conditions in priority order (highest first)")
    sections.append("     * and plays the first matching animation. This ensures that death always")
    sections.append("     * overrides attack, attack overrides walk, and walk overrides idle.")
    sections.append("     *")
    sections.append("     * Transition times are tuned to match MC 1.12.2 feel:")
    sections.append("     *   - Attack: 3 tick snap transition (responsive combat)")
    sections.append("     *   - Walk/Idle: 4-5 tick smooth blend (natural movement)")
    sections.append("     *   - Evolved: 15 tick slow morph (dramatic transformation)")
    sections.append("     *   - Sleeping: 10 tick gentle transition (peaceful rest)")
    sections.append("     */")
    sections.append("    @Override")
    sections.append("    public void registerControllers(AnimatableManager.ControllerRegistrar controllers) {")

    # Generate the controller body based on complexity
    controller_code = _generate_controller_body(
        model_name, entity_class, categorized_anims,
        complexity, has_walk, has_stage, has_state_anim, has_special
    )
    # Indent the controller body (it's already at 8-space indent)
    sections.append(controller_code)

    sections.append("    }")
    sections.append("}")
    sections.append("")

    return "\n".join(sections)


def _generate_controller_body(model_name: str, entity_class: str,
                              categorized_anims: Dict[str, List[str]],
                              complexity: str, has_walk: bool,
                              has_stage: bool, has_state_anim: bool,
                              has_special: bool) -> str:
    """Generate the body of the registerControllers method.

    This is the core state machine generation logic that handles different
    complexity levels appropriately.
    """
    lines = []

    # ========================================================================
    # SIMPLE: Only idle animation
    # ========================================================================
    if complexity == "simple":
        idle_anims = categorized_anims.get("idle", [])
        if idle_anims:
            lines.append("        // Simple idle-only controller")
            lines.append("        // This model has only an idle animation, so we use a")
            lines.append("        // straightforward controller that always loops the idle anim.")
            lines.append("        controllers.add(new AnimationController<>(this, \"idleController\", 5f, event -> {")
            lines.append("            event.getController().setAnimation(")
            lines.append(f"                {generate_raw_animation_call(idle_anims[0], True)}")
            lines.append("            );")
            lines.append("            return PlayState.CONTINUE;")
            lines.append("        }));")
        return "\n".join(lines)

    # ========================================================================
    # STATE: Only open/closed animations (host, hostII)
    # ========================================================================
    if complexity == "state":
        return _generate_state_controller(entity_class, categorized_anims)

    # ========================================================================
    # BASIC / STANDARD / COMPLEX: Full state machine
    # ========================================================================

    # Build the list of state entries sorted by priority (highest first)
    all_states = []
    all_cats = {**ANIMATION_CATEGORIES, **STATE_CATEGORIES}

    for cat_name, anim_names in categorized_anims.items():
        cat_info = all_cats.get(cat_name, {"priority": 0, "looping": True, "transition": 5})
        priority = cat_info.get("priority", 0)
        looping = cat_info.get("looping", True)
        transition = cat_info.get("transition", 5)

        for anim_name in anim_names:
            all_states.append({
                "category": cat_name,
                "anim_name": anim_name,
                "priority": priority,
                "looping": looping,
                "transition": transition,
            })

    # Sort by priority (highest first), then by animation name for determinism
    all_states.sort(key=lambda s: (-s["priority"], s["anim_name"]))

    # Calculate default transition time (match the most important state)
    default_transition = 5
    if has_walk:
        default_transition = 4

    # Generate the main controller header
    priority_order = " > ".join(
        dict.fromkeys(s["category"] for s in all_states)
    )
    lines.append("        // ========================================================================")
    lines.append("        // Main Animation Controller - State Machine")
    lines.append("        // ========================================================================")
    lines.append(f"        // Priority order: {priority_order}")
    lines.append("        // Each state is checked in order; the first matching condition wins.")
    lines.append("        // Idle is always the fallback (condition: true) so the controller")
    lines.append("        // never returns PlayState.STOP for normal entity states.")
    lines.append(f"        controllers.add(new AnimationController<>(this, \"mainController\", {default_transition}f, event -> {{")
    lines.append(f"            {entity_class} entity = event.getAnimatable();")
    lines.append("")

    # ---- limbSwingAmount update (if walk exists) ----
    if has_walk:
        lines.append("            // ------------------------------------------------------------------")
        lines.append("            // limbSwingAmount Lerp Update")
        lines.append("            // ------------------------------------------------------------------")
        lines.append("            // Update the smoothed limbSwingAmount before checking walk state.")
        lines.append("            // This must run every tick regardless of which animation plays,")
        lines.append("            // so the value is always up-to-date when transitioning to walk.")
        lines.append("            float targetAmount = entity.getDeltaMovement().horizontalDistance() * 4.0F;")
        lines.append("            this.prevLimbSwingAmount = this.limbSwingAmount;")
        lines.append("            this.limbSwingAmount += (targetAmount - this.limbSwingAmount) * 0.4F;")
        lines.append("")

    # ---- State checks in priority order ----
    cat_descriptions = {
        "death":    "Death - plays once when entity dies, overrides everything",
        "special":  "Special - entity-specific state (vomit/shaking/cosmic)",
        "attack":   "Attack - plays once when entity has a target",
        "sleeping": "Sleeping - loops when entity is sleeping",
        "evolved":  "Evolved - loops when entity has evolved/transformed",
        "fly":      "Flying - loops when entity is airborne",
        "walk":     "Walking - loops when entity is moving (smoothed detection)",
        "idle":     "Idle - default fallback, always loops",
        "open":     "Open - loops when entity is in open state",
        "closed":   "Closed - loops when entity is in closed state",
        "stage":    "Stage - triggered by entity evolution stage",
    }

    for state in all_states:
        cat = state["category"]
        anim_name = state["anim_name"]
        looping = state["looping"]

        condition = generate_state_condition(cat, "entity", anim_name)
        desc = cat_descriptions.get(cat, f"{cat} animation")

        lines.append(f"            // {desc}")
        lines.append(f"            if ({condition}) {{")
        lines.append(f"                event.getController().setAnimation(")
        lines.append(f"                    {generate_raw_animation_call(anim_name, looping)}")
        lines.append(f"                );")
        lines.append(f"                return PlayState.CONTINUE;")
        lines.append(f"            }}")
        lines.append("")

    # Default fallback
    lines.append("            // No matching state - stop animation")
    lines.append("            return PlayState.STOP;")
    lines.append("        }));")

    # ---- Supplementary controllers ----
    # Stage animations get a separate controller so they can blend
    # with the base animations on a different layer
    if has_stage:
        lines.append("")
        lines.append(_generate_stage_controller(entity_class, categorized_anims))

    return "\n".join(lines)


def _generate_state_controller(entity_class: str,
                               categorized_anims: Dict[str, List[str]]) -> str:
    """Generate a state-based controller for open/closed models (host, hostII)."""
    lines = []
    open_anims = categorized_anims.get("open", [])
    closed_anims = categorized_anims.get("closed", [])

    lines.append("        // ========================================================================")
    lines.append("        // State-based Controller (open/closed)")
    lines.append("        // ========================================================================")
    lines.append("        // Models like host and hostII use open/closed states instead of")
    lines.append("        // idle/walk. The entity's isOpen() method determines which plays.")
    lines.append(f"        controllers.add(new AnimationController<>(this, \"stateController\", 5f, event -> {{")
    lines.append(f"            {entity_class} entity = event.getAnimatable();")
    lines.append("")

    if open_anims:
        lines.append("            // Open state - entity is opened/activated")
        lines.append("            if (entity.isOpen()) {")
        lines.append("                event.getController().setAnimation(")
        lines.append(f"                    {generate_raw_animation_call(open_anims[0], True)}")
        lines.append("                );")
        lines.append("                return PlayState.CONTINUE;")
        lines.append("            }")
        lines.append("")

    if closed_anims:
        lines.append("            // Closed state - entity is closed/dormant (default)")
        lines.append("            event.getController().setAnimation(")
        lines.append(f"                {generate_raw_animation_call(closed_anims[0], True)}")
        lines.append("            );")
        lines.append("            return PlayState.CONTINUE;")
    elif open_anims:
        lines.append("            // No closed animation available - stop when not open")
        lines.append("            return PlayState.STOP;")

    lines.append("        }));")
    return "\n".join(lines)


def _generate_stage_controller(entity_class: str,
                               categorized_anims: Dict[str, List[str]]) -> str:
    """Generate a supplementary stage evolution controller.

    Stage animations (stage6, stage25) run on a separate controller layer
    so they can override or blend with the base idle/walk animations.
    This matches MC 1.12.2 behavior where stage conditions were checked
    alongside the base animation state.
    """
    lines = []
    stage_anims = categorized_anims.get("stage", [])

    if not stage_anims:
        return ""

    lines.append("        // ========================================================================")
    lines.append("        // Stage Evolution Controller")
    lines.append("        // ========================================================================")
    lines.append("        // Different evolution stages trigger different animations.")
    lines.append("        // This runs as a separate controller so it can override the base")
    lines.append("        // animations when a specific stage is active.")
    lines.append("        // In MC 1.12.2, stage checks were embedded in setRotationAngles()")
    lines.append("        // as switch/if conditions alongside the base animation.")
    lines.append(f"        controllers.add(new AnimationController<>(this, \"stageController\", 10f, event -> {{")
    lines.append(f"            {entity_class} entity = event.getAnimatable();")
    lines.append("")

    for anim_name in stage_anims:
        condition = generate_state_condition("stage", "entity", anim_name)
        state_name = anim_name.split(".")[-1]
        lines.append(f"            // Stage: {state_name}")
        lines.append(f"            if ({condition}) {{")
        lines.append(f"                event.getController().setAnimation(")
        lines.append(f"                    {generate_raw_animation_call(anim_name, True)}")
        lines.append(f"                );")
        lines.append(f"                return PlayState.CONTINUE;")
        lines.append(f"            }}")
        lines.append("")

    lines.append("            // No stage active - let main controller handle animation")
    lines.append("            return PlayState.STOP;")
    lines.append("        }));")

    return "\n".join(lines)


# ============================================================================
# SRPLimbSwingHelper Utility Class
# ============================================================================

def generate_limb_swing_helper() -> str:
    """Generate the SRPLimbSwingHelper.java utility class.

    This provides a reusable implementation of the MC 1.12.2 limbSwingAmount
    exponential decay smoothing, which can be used by entity classes that
    need per-entity limb swing tracking (since model classes are singletons).
    """
    # Build as a list of lines to avoid f-string issues with JavaDoc curly braces
    lines = [
        f"package {PACKAGE_NAME};",
        "",
        "/**",
        " * SRPLimbSwingHelper - Reusable limbSwingAmount Lerp calculation.",
        " * ================================================================",
        " * Replicates MC 1.12.2's exponential decay smoothing for walk detection",
        " * in GeckoLib 1.20.1 animation controllers.",
        " *",
        " * <h3>Background</h3>",
        " * In MC 1.12.2, the limbSwingAmount field was smoothly interpolated",
        " * each frame using exponential decay:",
        " * <pre>",
        " *   limbSwingAmount += (targetAmount - limbSwingAmount) * 0.4F",
        " * </pre>",
        " * where targetAmount = horizontalDistance * 4.0F.",
        " *",
        " * <p>This smoothing prevents animation pop-in when entities start/stop",
        " * walking and provides the characteristic Minecraft movement feel.",
        " * Without it, walk animations would snap on/off instantly, looking jerky.</p>",
        " *",
        " * <h3>Usage in Entity Class</h3>",
        " * <pre>",
        " *   // Store as a field on the entity (per-entity tracking)",
        " *   private final SRPLimbSwingHelper limbSwingHelper = new SRPLimbSwingHelper();",
        " *",
        " *   // In tick() method, update the limb swing",
        " *   public void tick() {",
        " *       super.tick();",
        " *       limbSwingHelper.updateLimbSwing(",
        " *           (float) this.getDeltaMovement().horizontalDistance()",
        " *       );",
        " *   }",
        " *",
        " *   // In AnimationController callback, check walk state",
        " *   if (entity.getLimbSwingHelper().isWalking()) {",
        " *       event.getController().setAnimation(",
        " *           RawAnimation.begin().thenLoop(\"animation.model.walk\")",
        " *       );",
        " *       return PlayState.CONTINUE;",
        " *   }",
        " * </pre>",
        " *",
        " * <h3>Usage in Model Class (singleton caveat)</h3>",
        " * <pre>",
        " *   // For single-entity scenarios, store on the model:",
        " *   private final SRPLimbSwingHelper limbSwingHelper = new SRPLimbSwingHelper();",
        " *",
        " *   // In registerControllers callback:",
        " *   limbSwingHelper.updateLimbSwing(",
        " *       entity.getDeltaMovement().horizontalDistance()",
        " *   );",
        " *   if (limbSwingHelper.isWalking()) { ... }",
        " * </pre>",
        " * <p><b>Note:</b> Model classes are singletons shared across all entities",
        " * of the same type. For multi-entity scenarios, use per-entity tracking",
        " * as shown above.</p>",
        " */",
        "public class SRPLimbSwingHelper {",
        "",
        "    /**",
        "     * The exponential decay factor from MC 1.12.2's limbSwing interpolation.",
        "     * A value of 0.4F means 40% of the difference is applied each tick,",
        "     * creating smooth acceleration/deceleration of the limb swing.",
        "     *",
        "     * <p>Higher values = snappier transitions (less smooth)<br>",
        "     * Lower values = smoother transitions (more sluggish)</p>",
        "     */",
        "    public static final float LERP_FACTOR = 0.4F;",
        "",
        "    /**",
        "     * The movement threshold for walk detection.",
        "     * Values below this are considered stationary.",
        "     * Matches vanilla MC behavior where very slow movement",
        "     * doesn't trigger the walk animation cycle.",
        "     */",
        "    public static final float WALK_THRESHOLD = 0.01F;",
        "",
        "    /**",
        "     * Scaling factor applied to horizontal distance to get",
        "     * the target limbSwingAmount. In vanilla MC, this converts",
        "     * blocks/tick movement speed to animation speed.",
        "     */",
        "    public static final float MOVEMENT_SCALE = 4.0F;",
        "",
        "    // Per-instance state",
        "    private float prevLimbSwingAmount = 0.0F;",
        "    private float limbSwingAmount = 0.0F;",
        "",
        "    /**",
        "     * Update the limbSwingAmount with exponential decay interpolation.",
        "     *",
        "     * @param horizontalDistance The entity's horizontal movement distance",
        "     *                           per tick (from entity.getDeltaMovement().horizontalDistance())",
        "     * @return The smoothed limbSwingAmount value",
        "     */",
        "    public float updateLimbSwing(float horizontalDistance) {",
        "        float targetAmount = horizontalDistance * MOVEMENT_SCALE;",
        "        this.prevLimbSwingAmount = this.limbSwingAmount;",
        "        this.limbSwingAmount += (targetAmount - this.limbSwingAmount) * LERP_FACTOR;",
        "        return this.limbSwingAmount;",
        "    }",
        "",
        "    /**",
        "     * Check if the entity is currently walking based on smoothed limbSwingAmount.",
        "     *",
        "     * @return true if limbSwingAmount exceeds the walk threshold",
        "     */",
        "    public boolean isWalking() {",
        "        return this.limbSwingAmount > WALK_THRESHOLD;",
        "    }",
        "",
        "    /**",
        "     * Get the current smoothed limbSwingAmount.",
        "     *",
        "     * @return Current interpolated value",
        "     */",
        "    public float getLimbSwingAmount() {",
        "        return this.limbSwingAmount;",
        "    }",
        "",
        "    /**",
        "     * Get the previous tick's limbSwingAmount.",
        "     * Useful for detecting state transitions (walk start/stop).",
        "     *",
        "     * @return Previous tick's interpolated value",
        "     */",
        "    public float getPrevLimbSwingAmount() {",
        "        return this.prevLimbSwingAmount;",
        "    }",
        "",
        "    /**",
        "     * Calculate the walk animation speed multiplier based on limbSwingAmount.",
        "     * In MC 1.12.2, walk animation speed was proportional to limbSwingAmount,",
        "     * capped at 1.0F. This provides the same behavior.",
        "     *",
        "     * @return Speed multiplier in range [0.0, 1.0]",
        "     */",
        "    public float getWalkSpeedMultiplier() {",
        "        return Math.min(this.limbSwingAmount, 1.0F);",
        "    }",
        "",
        "    /**",
        "     * Detect if the entity just started walking this tick.",
        "     * Useful for triggering walk-start transition animations.",
        "     *",
        "     * @return true if walking now but was not walking last tick",
        "     */",
        "    public boolean startedWalking() {",
        "        return this.limbSwingAmount > WALK_THRESHOLD",
        "            && this.prevLimbSwingAmount <= WALK_THRESHOLD;",
        "    }",
        "",
        "    /**",
        "     * Detect if the entity just stopped walking this tick.",
        "     * Useful for triggering walk-stop transition animations.",
        "     *",
        "     * @return true if not walking now but was walking last tick",
        "     */",
        "    public boolean stoppedWalking() {",
        "        return this.limbSwingAmount <= WALK_THRESHOLD",
        "            && this.prevLimbSwingAmount > WALK_THRESHOLD;",
        "    }",
        "",
        "    /**",
        "     * Reset the limbSwingAmount state (e.g., when entity is spawned or",
        "     * changes dimension).",
        "     */",
        "    public void reset() {",
        "        this.prevLimbSwingAmount = 0.0F;",
        "        this.limbSwingAmount = 0.0F;",
        "    }",
        "",
        "    /**",
        "     * Static helper: Calculate limbSwingAmount for a single tick without",
        "     * maintaining state. Useful for one-off calculations or when state is",
        "     * stored elsewhere.",
        "     *",
        "     * @param currentAmount The current limbSwingAmount",
        "     * @param horizontalDistance The entity's horizontal movement distance",
        "     * @return The new smoothed limbSwingAmount",
        "     */",
        "    public static float calculateLerp(float currentAmount, float horizontalDistance) {",
        "        float targetAmount = horizontalDistance * MOVEMENT_SCALE;",
        "        return currentAmount + (targetAmount - currentAmount) * LERP_FACTOR;",
        "    }",
        "",
        "    /**",
        "     * Static helper: Check if a limbSwingAmount value indicates walking.",
        "     *",
        "     * @param limbSwingAmount The current smoothed value",
        "     * @return true if the value exceeds the walk threshold",
        "     */",
        "    public static boolean isMoving(float limbSwingAmount) {",
        "        return limbSwingAmount > WALK_THRESHOLD;",
        "    }",
        "}",
        "",
    ]
    return "\n".join(lines)


# ============================================================================
# Model Scanner
# ============================================================================

def scan_bbmodel_files(input_dir: str) -> List[Dict]:
    """Scan all .bbmodel files in the input directory tree.

    Returns a list of dicts, each containing:
        - path: full file path
        - filename: bbmodel filename
        - model_id: filename without .bbmodel extension
        - category: category directory name
        - internal_name: model name from inside the bbmodel
        - animations: list of animation name strings
        - animation_count: number of animations
    """
    models = []

    if not os.path.isdir(input_dir):
        print(f"  ERROR: Input directory does not exist: {input_dir}")
        return models

    for category_dir in sorted(os.listdir(input_dir)):
        cat_path = os.path.join(input_dir, category_dir)
        if not os.path.isdir(cat_path):
            continue

        for filename in sorted(os.listdir(cat_path)):
            if not filename.endswith(".bbmodel"):
                continue

            filepath = os.path.join(cat_path, filename)
            model_id = filename[: -len(".bbmodel")]

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)

                animations = data.get("animations", [])
                anim_names = [a.get("name", "") for a in animations if a.get("name")]
                internal_name = data.get("name", model_id)

                models.append(
                    {
                        "path": filepath,
                        "filename": filename,
                        "model_id": model_id,
                        "category": category_dir,
                        "internal_name": internal_name,
                        "animations": anim_names,
                        "animation_count": len(anim_names),
                    }
                )

            except (json.JSONDecodeError, IOError) as e:
                print(f"  WARNING: Failed to read {filepath}: {e}")
                continue

    return models


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point for the AnimationController generator."""
    input_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INPUT_DIR
    output_dir = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUTPUT_DIR

    print("=" * 70)
    print("  AnimationController Generator for SubspaceParasite")
    print("  GeckoLib 4.x Java Code Generation")
    print("=" * 70)
    print(f"\n  Input:  {input_dir}")
    print(f"  Output: {output_dir}")
    print()

    # ---------------------------------------------------------------
    # Step 1: Scan all .bbmodel files
    # ---------------------------------------------------------------
    print("  Step 1: Scanning .bbmodel files...")
    models = scan_bbmodel_files(input_dir)
    print(f"  Found {len(models)} models total")

    models_with_anims = [m for m in models if m["animation_count"] > 0]
    print(f"  Models with animations: {len(models_with_anims)}")

    # ---------------------------------------------------------------
    # Step 2: Categorize all animations
    # ---------------------------------------------------------------
    print("\n  Step 2: Categorizing animations...")
    category_stats = defaultdict(int)
    anim_type_counts = defaultdict(int)

    for model in models_with_anims:
        categorized = categorize_all_animations(model["animations"])
        model["categorized"] = categorized
        model["complexity"] = get_animation_complexity(categorized)

        for cat_name, anim_names in categorized.items():
            category_stats[cat_name] += len(anim_names)

        anim_type_counts[model["complexity"]] += 1

    # Print animation category statistics
    print("\n  Animation Category Statistics:")
    all_cat_names = list(ANIMATION_CATEGORIES.keys()) + list(STATE_CATEGORIES.keys()) + ["unknown"]
    for cat_name in all_cat_names:
        if cat_name in category_stats:
            print(f"    {cat_name:12s}: {category_stats[cat_name]:3d} animations")

    total_anims = sum(category_stats.values())
    print(f"    {'TOTAL':12s}: {total_anims:3d} animations")

    # Print complexity distribution
    print("\n  Model Complexity Distribution:")
    for complexity in ["simple", "basic", "standard", "complex", "state"]:
        if complexity in anim_type_counts:
            print(f"    {complexity:12s}: {anim_type_counts[complexity]:3d} models")

    # ---------------------------------------------------------------
    # Step 3: Generate Java model classes
    # ---------------------------------------------------------------
    print("\n  Step 3: Generating Java model classes...")
    os.makedirs(output_dir, exist_ok=True)

    generated_files = []
    errors = []

    for model in models_with_anims:
        model_id = model["model_id"]
        category = model["category"]
        categorized = model["categorized"]

        try:
            java_code = generate_model_class(
                model_name=model_id,
                category=category,
                categorized_anims=categorized,
                raw_animations=model["animations"],
            )

            # Output path preserving category structure
            out_cat_dir = os.path.join(output_dir, category)
            os.makedirs(out_cat_dir, exist_ok=True)

            model_class = to_model_class(model_id)
            out_path = os.path.join(out_cat_dir, f"{model_class}.java")

            with open(out_path, "w", encoding="utf-8") as f:
                f.write(java_code)

            generated_files.append(
                {
                    "model_id": model_id,
                    "category": category,
                    "class_name": model_class,
                    "entity_class": to_entity_class(model_id),
                    "complexity": model["complexity"],
                    "path": out_path,
                    "animations": model["animations"],
                    "categories": sorted(categorized.keys()),
                }
            )

        except Exception as e:
            errors.append(f"{category}/{model_id}: {e}")
            print(f"    ERROR generating {category}/{model_id}: {e}")

    print(f"  Generated {len(generated_files)} model classes")
    if errors:
        print(f"  Errors: {len(errors)}")
        for err in errors:
            print(f"    - {err}")

    # ---------------------------------------------------------------
    # Step 4: Generate SRPLimbSwingHelper
    # ---------------------------------------------------------------
    print("\n  Step 4: Generating SRPLimbSwingHelper.java...")
    helper_code = generate_limb_swing_helper()
    helper_path = os.path.join(output_dir, "SRPLimbSwingHelper.java")
    with open(helper_path, "w", encoding="utf-8") as f:
        f.write(helper_code)
    print(f"  Saved: {helper_path}")

    # ---------------------------------------------------------------
    # Step 5: Print generated files by category
    # ---------------------------------------------------------------
    print("\n  Generated files by category:")
    by_category = defaultdict(list)
    for gf in generated_files:
        by_category[gf["category"]].append(gf)

    for cat in sorted(by_category.keys()):
        files = by_category[cat]
        print(f"\n  [{cat}] ({len(files)} models):")
        for gf in files:
            anim_str = ", ".join(gf["categories"])
            print(f"    {gf['class_name']:30s}  [{anim_str}]  ({gf['complexity']})")

    # ---------------------------------------------------------------
    # Step 6: Save generation report
    # ---------------------------------------------------------------
    report_path = os.path.join(output_dir, "generation_report.json")
    report = {
        "generator": "animation_controller_generator.py",
        "timestamp": datetime.now().isoformat(),
        "input_dir": input_dir,
        "output_dir": output_dir,
        "total_models_scanned": len(models),
        "models_with_animations": len(models_with_anims),
        "generated_files": len(generated_files),
        "errors": errors,
        "category_stats": dict(category_stats),
        "complexity_stats": dict(anim_type_counts),
        "files": [
            {
                "model_id": gf["model_id"],
                "category": gf["category"],
                "class_name": gf["class_name"],
                "entity_class": gf["entity_class"],
                "complexity": gf["complexity"],
                "animations": gf["animations"],
                "animation_categories": gf["categories"],
            }
            for gf in generated_files
        ],
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n  Report saved to: {report_path}")

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  GENERATION COMPLETE")
    print("=" * 70)
    print(f"\n  Models scanned:     {len(models)}")
    print(f"  Models generated:   {len(generated_files)}")
    print(f"  Total animations:   {total_anims}")
    print(f"  Helper class:       SRPLimbSwingHelper.java")
    if errors:
        print(f"  Errors:             {len(errors)}")
    print()

    return generated_files


if __name__ == "__main__":
    main()
