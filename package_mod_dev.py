#!/usr/bin/env python3
"""
package_mod_dev.py — Package converted GeckoLib output into mod-development-ready format.

Takes the already-converted output files from /home/z/my-project/db/output/ and creates
a proper GeckoLib mod resource structure with Java code generation, animation name mapping,
and multi-part entity detection.

Output ZIP: /home/z/my-project/db/MinecraftModelMigrator-Pro-GeckoLib.zip
Also replaces: /home/z/my-project/MROLF-TGNBF/MROLF-TGNBF.tar.gz (as .zip)
"""

import json
import os
import re
import shutil
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ─── Configuration ───────────────────────────────────────────────────────────

OUTPUT_DIR = Path("/home/z/my-project/db/output")
BUILD_DIR = Path("/home/z/my-project/db/geckolib_mod_dev")
ZIP_PATH = Path("/home/z/my-project/db/MinecraftModelMigrator-Pro-GeckoLib.zip")
OLD_ARCHIVE = Path("/home/z/my-project/MROLF-TGNBF/MROLF-TGNBF.tar.gz")

MOD_ID = "srp"
MOD_PACKAGE = "com.srp"

CATEGORIES = [
    "abomination", "adapted", "ancient", "awakened", "crude", "derived",
    "deterrent", "feral", "focused", "hijacked", "inborn", "infected",
    "misc", "primitive", "projectile", "pure"
]

# Category → Entity base class mapping
CATEGORY_ENTITY_TYPE = {
    "abomination": "Monster",
    "adapted": "Monster",
    "ancient": "Monster",
    "awakened": "Monster",
    "crude": "Monster",
    "derived": "Monster",
    "deterrent": "Monster",
    "feral": "Monster",
    "focused": "Monster",
    "hijacked": "Monster",
    "inborn": "Monster",
    "infected": "Monster",
    "misc": "Entity",
    "primitive": "Monster",
    "projectile": "Entity",
    "pure": "Monster",
}

# Full class paths for entity base types
ENTITY_BASE_CLASSES = {
    "Monster": "net.minecraft.world.entity.monster.Monster",
    "Entity": "net.minecraft.world.entity.Entity",
}

# For Entity base type, we use PathfinderMob as a more useful default
# (raw Entity doesn't have the constructor signature we need)
ENTITY_SUPER_IMPORTS = {
    "Monster": ("net.minecraft.world.entity.monster.Monster", "Monster"),
    "Entity": ("net.minecraft.world.entity.PathfinderMob", "PathfinderMob"),
}

# Known multi-part entity groups: category → { base_name: [model_names] }
# These are models that share a common prefix and represent parts of the same entity
MULTIPART_KNOWN = {
    "abomination": {
        "abo": ["aboBodies", "aboHead"],
    },
    "infected": {
        "infCow": ["infCow", "infCowHead"],
        "infDragonE": ["infDragonE", "infDragonEHead"],
        "infEnderman": ["infEnderman", "infEndermanHead"],
        "infHorse": ["infHorse", "infHorseHead"],
        "infHuman": ["infHuman", "infHumanHead"],
        "infPig": ["infPig", "infPigHead"],
        "infPlayer": ["infPlayer", "infPlayerHead"],
        "infSheep": ["infSheep", "infSheepHead"],
        "infVillager": ["infVillager", "infVillagerHead"],
        "infWolf": ["infWolf", "infWolfHead"],
    },
    "deterrent": {
        "dod": ["dod", "dodSII", "dodSIII", "dodSIV", "dodSIVH", "dodT"],
        "leem": ["leem", "leemB", "leemSII", "leemSIII", "leemSIV"],
        "venkrol": ["venkrol", "venkrolSII", "venkrolSIII", "venkrolSIV", "venkrolSV"],
    },
    "awakened": {
        "oroncoAW": ["oroncoAW", "oroncoAWFL"],
    },
    "ancient": {
        "oronco": ["oronco", "oroncoTen"],
    },
}


# ─── Utility Functions ───────────────────────────────────────────────────────

def to_pascal_case(name: str) -> str:
    """Convert a snake_case or camelCase name to PascalCase."""
    # Handle already PascalCase-ish names (e.g., "aboHead" → "AboHead")
    # First, split on common delimiters
    parts = re.split(r'[_\-\s]+', name)
    result = []
    for part in parts:
        if not part:
            continue
        # Split on camelCase boundaries: lowercase followed by uppercase
        sub_parts = re.findall(r'[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z][a-z]|\Z)', part)
        if sub_parts:
            result.extend(s.capitalize() for s in sub_parts)
        else:
            result.append(part.capitalize())
    return "".join(result)


def to_snake_case(name: str) -> str:
    """Convert a name to snake_case."""
    # Insert underscore before uppercase letters
    s = re.sub(r'([A-Z])', r'_\1', name)
    return s.lower().strip('_')


def flatten_resource_name(category: str, model_name: str) -> str:
    """Create a flattened resource name with category prefix: category_modelName"""
    return f"{category}_{model_name}"


# ─── Scanner: Read Output Directory ─────────────────────────────────────────

def scan_output_directory(output_dir: Path) -> Dict:
    """
    Scan the output directory and build a model registry.
    
    Returns:
        {
            category: {
                model_name: {
                    'geo': Path or None,
                    'animation': Path or None,
                    'texture': Path or None,
                    'animation_names': [str, ...],
                }
            }
        }
    """
    registry = {}
    
    for category in CATEGORIES:
        cat_dir = output_dir / category
        if not cat_dir.exists():
            print(f"  WARNING: Category directory missing: {cat_dir}")
            continue
        
        registry[category] = {}
        
        # Collect all model names from geo files
        geo_files = sorted(cat_dir.glob("*.geo.json"))
        for geo_path in geo_files:
            model_name = geo_path.stem.replace(".geo", "")
            registry[category][model_name] = {
                'geo': geo_path,
                'animation': None,
                'texture': None,
                'animation_names': [],
            }
        
        # Match animation files
        for anim_path in sorted(cat_dir.glob("*.animation.json")):
            model_name = anim_path.stem.replace(".animation", "")
            if model_name in registry[category]:
                registry[category][model_name]['animation'] = anim_path
                # Extract animation names
                try:
                    with open(anim_path, 'r') as f:
                        anim_data = json.load(f)
                    anim_names = list(anim_data.get("animations", {}).keys())
                    registry[category][model_name]['animation_names'] = anim_names
                except (json.JSONDecodeError, IOError) as e:
                    print(f"  WARNING: Failed to read animation names from {anim_path}: {e}")
        
        # Match texture files
        for tex_path in sorted(cat_dir.glob("*.png")):
            model_name = tex_path.stem
            if model_name in registry[category]:
                registry[category][model_name]['texture'] = tex_path
            else:
                # Texture without matching geo — might be a separate part
                # Register it as a model without geo (unlikely but handle gracefully)
                print(f"  NOTE: Texture without geo: {tex_path}")
    
    return registry


# ─── Multi-part Entity Detection ─────────────────────────────────────────────

def detect_multipart_entities(registry: Dict) -> Dict[str, Dict]:
    """
    Detect multi-part entities by grouping models that share a base name prefix.
    Uses both known mappings and automatic prefix detection.
    
    Returns:
        {
            category: {
                base_name: {
                    'models': [model_name, ...],
                    'class_name': PascalCaseClassName,
                }
            }
        }
    """
    multipart = {}
    
    for category, models in registry.items():
        if not models:
            continue
        
        model_names = sorted(models.keys())
        used_models = set()
        cat_multipart = {}
        
        # First, apply known multi-part groupings
        if category in MULTIPART_KNOWN:
            for base_name, parts in MULTIPART_KNOWN[category].items():
                existing_parts = [p for p in parts if p in models]
                if len(existing_parts) > 1:
                    cat_multipart[base_name] = {
                        'models': existing_parts,
                        'class_name': to_pascal_case(base_name),
                    }
                    used_models.update(existing_parts)
        
        # Then, auto-detect multi-part entities from remaining models
        # Group by common prefix (minimum 3 chars, at least 2 models sharing it)
        remaining = [m for m in model_names if m not in used_models]
        prefix_groups = defaultdict(list)
        
        for name in remaining:
            # Try progressively shorter prefixes
            for prefix_len in range(min(len(name), 10), 2, -1):
                prefix = name[:prefix_len]
                # Only consider if prefix ends at a word boundary
                # (next char is uppercase or we're at the end)
                if prefix_len < len(name) and name[prefix_len].isupper():
                    prefix_groups[prefix].append(name)
                    break
            else:
                # No clear boundary found, use first 3+ chars as prefix
                if len(name) >= 3:
                    prefix_groups[name[:3]].append(name)
        
        # Filter to groups with 2+ models
        for prefix, group in prefix_groups.items():
            if len(group) >= 2:
                # Verify all models in group actually exist
                existing = [m for m in group if m in models and m not in used_models]
                if len(existing) >= 2:
                    cat_multipart[prefix] = {
                        'models': existing,
                        'class_name': to_pascal_case(prefix),
                    }
                    used_models.update(existing)
        
        if cat_multipart:
            multipart[category] = cat_multipart
    
    return multipart


# ─── Java Code Generation ───────────────────────────────────────────────────

def generate_geo_model_class(model_name: str, category: str, has_animation: bool) -> str:
    """Generate a GeckoLib GeoModel subclass."""
    class_name = to_pascal_case(model_name) + "Model"
    entity_class = to_pascal_case(model_name) + "Entity"
    flat_name = flatten_resource_name(category, model_name)
    
    geo_resource = f"{MOD_ID}:geo/{flat_name}.geo.json"
    tex_resource = f"{MOD_ID}:textures/entity/{flat_name}.png"
    anim_resource = f"{MOD_ID}:animations/{flat_name}.animation.json"
    
    lines = [
        f"package {MOD_PACKAGE}.client.model;",
        "",
        f"import {MOD_PACKAGE}.entity.{entity_class};",
        "import software.bernie.geckolib.model.GeoModel;",
        "import net.minecraft.resources.ResourceLocation;",
        "",
        f"public class {class_name} extends GeoModel<{entity_class}> {{",
        "",
        f"    private static final ResourceLocation MODEL = new ResourceLocation(\"{MOD_ID}\", \"geo/{flat_name}.geo.json\");",
        f"    private static final ResourceLocation TEXTURE = new ResourceLocation(\"{MOD_ID}\", \"textures/entity/{flat_name}.png\");",
    ]
    
    if has_animation:
        lines.append(f"    private static final ResourceLocation ANIMATION = new ResourceLocation(\"{MOD_ID}\", \"animations/{flat_name}.animation.json\");")
    
    lines.extend([
        "",
        f"    @Override",
        f"    public ResourceLocation getModelResource({entity_class} animatable) {{",
        f"        return MODEL;",
        f"    }}",
        "",
        f"    @Override",
        f"    public ResourceLocation getTextureResource({entity_class} animatable) {{",
        f"        return TEXTURE;",
        f"    }}",
    ])
    
    if has_animation:
        lines.extend([
            "",
            f"    @Override",
            f"    public ResourceLocation getAnimationResource({entity_class} animatable) {{",
            f"        return ANIMATION;",
            f"    }}",
        ])
    else:
        lines.extend([
            "",
            f"    @Override",
            f"    public ResourceLocation getAnimationResource({entity_class} animatable) {{",
            f"        return null; // No animation file",
            f"    }}",
        ])
    
    lines.extend([
        "}",
        "",
    ])
    
    return "\n".join(lines)


def generate_renderer_class(model_name: str, category: str) -> str:
    """Generate a GeckoLib GeoEntityRenderer subclass."""
    class_name = to_pascal_case(model_name) + "Renderer"
    model_class = to_pascal_case(model_name) + "Model"
    entity_class = to_pascal_case(model_name) + "Entity"
    
    lines = [
        f"package {MOD_PACKAGE}.client.renderer;",
        "",
        f"import {MOD_PACKAGE}.client.model.{model_class};",
        f"import {MOD_PACKAGE}.entity.{entity_class};",
        "import software.bernie.geckolib.renderer.GeoEntityRenderer;",
        "import net.minecraft.client.renderer.entity.EntityRendererProvider;",
        "",
        f"public class {class_name} extends GeoEntityRenderer<{entity_class}> {{",
        "",
        f"    public {class_name}(EntityRendererProvider.Context renderManager) {{",
        f"        super(renderManager, new {model_class}());",
        f"    }}",
        "}",
        "",
    ]
    
    return "\n".join(lines)


def generate_entity_class(model_name: str, category: str) -> str:
    """Generate an Entity class stub."""
    class_name = to_pascal_case(model_name) + "Entity"
    entity_type = CATEGORY_ENTITY_TYPE.get(category, "Monster")
    super_import, super_class = ENTITY_SUPER_IMPORTS.get(entity_type, ENTITY_SUPER_IMPORTS["Monster"])
    
    lines = [
        f"package {MOD_PACKAGE}.entity;",
        "",
        f"import {super_import};",
        "import net.minecraft.world.entity.EntityType;",
        "import net.minecraft.world.level.Level;",
        "",
        f"public class {class_name} extends {super_class} {{",
        "",
        f"    public {class_name}(EntityType<? extends {super_class}> type, Level level) {{",
        f"        super(type, level);",
        f"    }}",
        "}",
        "",
    ]
    
    return "\n".join(lines)


def generate_multipart_entity_class(base_name: str, category: str, part_model_names: List[str]) -> str:
    """Generate an Entity class for a multi-part entity with references to multiple geo models."""
    class_name = to_pascal_case(base_name) + "Entity"
    entity_type = CATEGORY_ENTITY_TYPE.get(category, "Monster")
    super_import, super_class = ENTITY_SUPER_IMPORTS.get(entity_type, ENTITY_SUPER_IMPORTS["Monster"])
    
    lines = [
        f"package {MOD_PACKAGE}.entity;",
        "",
        f"import {super_import};",
        "import net.minecraft.world.entity.EntityType;",
        "import net.minecraft.world.level.Level;",
        "",
        f"public class {class_name} extends {super_class} {{",
        "",
    ]
    
    # Add references to each part's model resources
    for part_name in part_model_names:
        flat_name = flatten_resource_name(category, part_name)
        part_field = to_snake_case(part_name).upper()
        lines.extend([
            f"    // Part: {part_name}",
            f"    public static final String {part_field}_GEO = \"{MOD_ID}:geo/{flat_name}.geo.json\";",
            f"    public static final String {part_field}_TEXTURE = \"{MOD_ID}:textures/entity/{flat_name}.png\";",
        ])
    
    lines.extend([
        "",
        f"    public {class_name}(EntityType<? extends {super_class}> type, Level level) {{",
        f"        super(type, level);",
        f"    }}",
        "}",
        "",
    ])
    
    return "\n".join(lines)


def generate_multipart_geo_model_class(base_name: str, category: str, parts: List[Dict]) -> str:
    """Generate a GeoModel class for a multi-part entity (uses the primary/first part's model)."""
    class_name = to_pascal_case(base_name) + "Model"
    entity_class = to_pascal_case(base_name) + "Entity"
    
    # Use first part as primary
    primary = parts[0]
    flat_name = flatten_resource_name(category, primary)
    has_animation = any(p.get('has_animation', False) for p in parts)
    
    lines = [
        f"package {MOD_PACKAGE}.client.model;",
        "",
        f"import {MOD_PACKAGE}.entity.{entity_class};",
        "import software.bernie.geckolib.model.GeoModel;",
        "import net.minecraft.resources.ResourceLocation;",
        "",
        f"public class {class_name} extends GeoModel<{entity_class}> {{",
        "",
        f"    // Multi-part entity — primary model: {primary}",
        f"    private static final ResourceLocation MODEL = new ResourceLocation(\"{MOD_ID}\", \"geo/{flat_name}.geo.json\");",
        f"    private static final ResourceLocation TEXTURE = new ResourceLocation(\"{MOD_ID}\", \"textures/entity/{flat_name}.png\");",
    ]
    
    if has_animation:
        anim_flat = flatten_resource_name(category, primary)
        lines.append(f"    private static final ResourceLocation ANIMATION = new ResourceLocation(\"{MOD_ID}\", \"animations/{anim_flat}.animation.json\");")
    
    lines.extend([
        "",
        f"    @Override",
        f"    public ResourceLocation getModelResource({entity_class} animatable) {{",
        f"        return MODEL;",
        f"    }}",
        "",
        f"    @Override",
        f"    public ResourceLocation getTextureResource({entity_class} animatable) {{",
        f"        return TEXTURE;",
        f"    }}",
    ])
    
    if has_animation:
        lines.extend([
            "",
            f"    @Override",
            f"    public ResourceLocation getAnimationResource({entity_class} animatable) {{",
            f"        return ANIMATION;",
            f"    }}",
        ])
    else:
        lines.extend([
            "",
            f"    @Override",
            f"    public ResourceLocation getAnimationResource({entity_class} animatable) {{",
            f"        return null;",
            f"    }}",
        ])
    
    lines.extend([
        "}",
        "",
    ])
    
    return "\n".join(lines)


def generate_multipart_renderer_class(base_name: str, category: str) -> str:
    """Generate a renderer class for a multi-part entity."""
    class_name = to_pascal_case(base_name) + "Renderer"
    model_class = to_pascal_case(base_name) + "Model"
    entity_class = to_pascal_case(base_name) + "Entity"
    
    lines = [
        f"package {MOD_PACKAGE}.client.renderer;",
        "",
        f"import {MOD_PACKAGE}.client.model.{model_class};",
        f"import {MOD_PACKAGE}.entity.{entity_class};",
        "import software.bernie.geckolib.renderer.GeoEntityRenderer;",
        "import net.minecraft.client.renderer.entity.EntityRendererProvider;",
        "",
        f"public class {class_name} extends GeoEntityRenderer<{entity_class}> {{",
        "",
        f"    public {class_name}(EntityRendererProvider.Context renderManager) {{",
        f"        super(renderManager, new {model_class}());",
        f"    }}",
        "}",
        "",
    ]
    
    return "\n".join(lines)


# ─── Resource Mapping Documentation ─────────────────────────────────────────

def generate_resource_mapping_md(
    registry: Dict,
    multipart: Dict,
    animation_names_map: Dict,
) -> str:
    """Generate RESOURCE_MAPPING.md documentation."""
    lines = [
        "# MinecraftModelMigrator-Pro — GeckoLib Resource Mapping",
        "",
        f"**Mod ID**: `{MOD_ID}`",
        f"**Package**: `{MOD_PACKAGE}`",
        f"**Generated by**: package_mod_dev.py",
        "",
        "## Resource Path Convention",
        "",
        "| Resource Type | Path Pattern |",
        "|---|---|",
        f"| Geometry | `assets/{MOD_ID}/geo/<category>_<model>.geo.json` |",
        f"| Animation | `assets/{MOD_ID}/animations/<category>_<model>.animation.json` |",
        f"| Texture | `assets/{MOD_ID}/textures/entity/<category>_<model>.png` |",
        "",
        "## Category → Entity Type Mapping",
        "",
        "| Category | Entity Base Class | Hostile? |",
        "|---|---|---|",
    ]
    
    for cat in CATEGORIES:
        etype = CATEGORY_ENTITY_TYPE.get(cat, "Monster")
        hostile = "Yes" if etype == "Monster" else "No"
        lines.append(f"| {cat} | {etype} | {hostile} |")
    
    lines.extend([
        "",
        "## Models by Category",
        "",
    ])
    
    total_models = 0
    total_anims = 0
    
    for category in CATEGORIES:
        if category not in registry:
            continue
        models = registry[category]
        if not models:
            continue
        
        lines.append(f"### {category}")
        lines.append("")
        lines.append("| Model | Java Entity Class | Geo | Texture | Animation |")
        lines.append("|---|---|---|---|---|")
        
        for model_name in sorted(models.keys()):
            info = models[model_name]
            total_models += 1
            flat = flatten_resource_name(category, model_name)
            entity_class = to_pascal_case(model_name) + "Entity"
            has_anim = "Yes" if info['animation'] else "No"
            if info['animation']:
                total_anims += 1
            lines.append(f"| {model_name} | {entity_class} | `{flat}.geo.json` | `{flat}.png` | {has_anim} |")
        
        lines.append("")
    
    # Multi-part entities section
    if multipart:
        lines.extend([
            "## Multi-Part Entities",
            "",
            "These entities consist of multiple geo models combined into a single entity:",
            "",
            "| Category | Entity | Parts |",
            "|---|---|---|",
        ])
        
        for category, groups in multipart.items():
            for base_name, info in groups.items():
                parts_str = ", ".join(info['models'])
                lines.append(f"| {category} | {info['class_name']}Entity | {parts_str} |")
        
        lines.append("")
    
    lines.extend([
        "## Animation Names Index",
        "",
    ])
    
    for model_key in sorted(animation_names_map.keys()):
        info = animation_names_map[model_key]
        anim_names = info.get('animation_names', [])
        if anim_names:
            lines.append(f"### {model_key}")
            lines.append("")
            for an in anim_names:
                lines.append(f"- `{an}`")
            lines.append("")
    
    lines.extend([
        "## Summary",
        "",
        f"- **Total models**: {total_models}",
        f"- **Total with animations**: {total_anims}",
        f"- **Total animation clips**: {sum(len(v.get('animation_names', [])) for v in animation_names_map.values())}",
        f"- **Multi-part entities**: {sum(len(g) for g in multipart.values())}",
        f"- **Categories**: {len(registry)}",
        "",
    ])
    
    return "\n".join(lines)


# ─── Main Build Pipeline ────────────────────────────────────────────────────

def build_mod_dev_package():
    """Main function: scan, generate, package."""
    
    print("=" * 70)
    print("MinecraftModelMigrator-Pro — GeckoLib Mod Dev Packaging")
    print("=" * 70)
    
    # Step 1: Scan output directory
    print("\n[1/7] Scanning output directory...")
    registry = scan_output_directory(OUTPUT_DIR)
    
    total_geo = 0
    total_anim = 0
    total_tex = 0
    total_anim_names = 0
    
    for category, models in registry.items():
        for model_name, info in models.items():
            if info['geo']:
                total_geo += 1
            if info['animation']:
                total_anim += 1
            if info['texture']:
                total_tex += 1
            total_anim_names += len(info['animation_names'])
    
    print(f"  Found {total_geo} geo models, {total_anim} animations, {total_tex} textures")
    print(f"  Total animation clips: {total_anim_names}")
    
    # Step 2: Detect multi-part entities
    print("\n[2/7] Detecting multi-part entities...")
    multipart = detect_multipart_entities(registry)
    
    mp_count = sum(len(g) for g in multipart.values())
    print(f"  Found {mp_count} multi-part entity groups")
    for category, groups in multipart.items():
        for base_name, info in groups.items():
            print(f"    {category}/{base_name}: {info['models']}")
    
    # Step 3: Create directory structure
    print("\n[3/7] Creating directory structure...")
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    
    resources_base = BUILD_DIR / "src" / "main" / "resources" / "assets" / MOD_ID
    geo_dir = resources_base / "geo"
    animations_dir = resources_base / "animations"
    textures_dir = resources_base / "textures" / "entity"
    
    java_base = BUILD_DIR / "src" / "main" / "java" / "com" / "srp"
    model_dir = java_base / "client" / "model"
    renderer_dir = java_base / "client" / "renderer"
    entity_dir = java_base / "entity"
    
    for d in [geo_dir, animations_dir, textures_dir, model_dir, renderer_dir, entity_dir]:
        d.mkdir(parents=True, exist_ok=True)
    
    print(f"  Created directory tree at {BUILD_DIR}")
    
    # Step 4: Copy resources and generate Java code
    print("\n[4/7] Copying resources and generating Java code...")
    
    animation_names_map = {}  # model_key → {geo, texture, animation, animation_names}
    generated_classes = set()  # Track generated class names to avoid collisions
    
    # Determine which models are part of multi-part entities
    multipart_model_set = set()  # (category, model_name) tuples
    multipart_primary = {}  # (category, base_name) → primary model_name
    
    for category, groups in multipart.items():
        for base_name, info in groups.items():
            for part_name in info['models']:
                multipart_model_set.add((category, part_name))
            # First model is primary
            multipart_primary[(category, base_name)] = info['models'][0]
    
    # Process each model
    for category in CATEGORIES:
        if category not in registry:
            continue
        models = registry[category]
        
        for model_name in sorted(models.keys()):
            info = models[model_name]
            flat_name = flatten_resource_name(category, model_name)
            
            # Copy geo file
            if info['geo']:
                dest = geo_dir / f"{flat_name}.geo.json"
                shutil.copy2(info['geo'], dest)
            
            # Copy animation file
            if info['animation']:
                dest = animations_dir / f"{flat_name}.animation.json"
                shutil.copy2(info['animation'], dest)
            
            # Copy texture file
            if info['texture']:
                dest = textures_dir / f"{flat_name}.png"
                shutil.copy2(info['texture'], dest)
            
            # Build animation_names_map entry
            model_key = model_name  # Use bare model name as key
            entry = {
                'geo': f"{MOD_ID}:geo/{flat_name}.geo.json",
                'texture': f"{MOD_ID}:textures/entity/{flat_name}.png",
                'category': category,
                'flat_name': flat_name,
            }
            if info['animation']:
                entry['animation'] = f"{MOD_ID}:animations/{flat_name}.animation.json"
            entry['animation_names'] = info['animation_names']
            animation_names_map[model_key] = entry
            
            # Generate Java classes for standalone models
            # (Multi-part entity parts also get individual classes for flexibility)
            has_animation = info['animation'] is not None
            
            # Ensure unique class names by checking for collisions
            class_base = to_pascal_case(model_name)
            model_class_name = class_base + "Model"
            renderer_class_name = class_base + "Renderer"
            entity_class_name = class_base + "Entity"
            
            # Check for collisions (same model name in different categories)
            if model_class_name in generated_classes:
                # Add category prefix to disambiguate
                class_base = to_pascal_case(category) + class_base
                model_class_name = class_base + "Model"
                renderer_class_name = class_base + "Renderer"
                entity_class_name = class_base + "Entity"
            
            generated_classes.add(model_class_name)
            generated_classes.add(renderer_class_name)
            generated_classes.add(entity_class_name)
            
            # Generate GeoModel class
            model_java = generate_geo_model_class(model_name, category, has_animation)
            # Use the potentially disambiguated class name
            if class_base != to_pascal_case(model_name):
                model_java = model_java.replace(
                    f"class {to_pascal_case(model_name)}Model",
                    f"class {model_class_name}"
                )
                model_java = model_java.replace(
                    f"extends GeoModel<{to_pascal_case(model_name)}Entity>",
                    f"extends GeoModel<{entity_class_name}>"
                )
                model_java = model_java.replace(
                    f"import {MOD_PACKAGE}.entity.{to_pascal_case(model_name)}Entity;",
                    f"import {MOD_PACKAGE}.entity.{entity_class_name};"
                )
                model_java = model_java.replace(
                    f"getModelResource({to_pascal_case(model_name)}Entity",
                    f"getModelResource({entity_class_name}"
                )
                model_java = model_java.replace(
                    f"getTextureResource({to_pascal_case(model_name)}Entity",
                    f"getTextureResource({entity_class_name}"
                )
                model_java = model_java.replace(
                    f"getAnimationResource({to_pascal_case(model_name)}Entity",
                    f"getAnimationResource({entity_class_name}"
                )
            
            (model_dir / f"{model_class_name}.java").write_text(model_java)
            
            # Generate Renderer class
            renderer_java = generate_renderer_class(model_name, category)
            if class_base != to_pascal_case(model_name):
                renderer_java = renderer_java.replace(
                    f"class {to_pascal_case(model_name)}Renderer",
                    f"class {renderer_class_name}"
                )
                renderer_java = renderer_java.replace(
                    f"new {to_pascal_case(model_name)}Model()",
                    f"new {model_class_name}()"
                )
                renderer_java = renderer_java.replace(
                    f"GeoEntityRenderer<{to_pascal_case(model_name)}Entity>",
                    f"GeoEntityRenderer<{entity_class_name}>"
                )
                renderer_java = renderer_java.replace(
                    f"import {MOD_PACKAGE}.client.model.{to_pascal_case(model_name)}Model;",
                    f"import {MOD_PACKAGE}.client.model.{model_class_name};"
                )
                renderer_java = renderer_java.replace(
                    f"import {MOD_PACKAGE}.entity.{to_pascal_case(model_name)}Entity;",
                    f"import {MOD_PACKAGE}.entity.{entity_class_name};"
                )
                renderer_java = renderer_java.replace(
                    f"{renderer_class_name}(EntityRendererProvider.Context renderManager)",
                    f"{renderer_class_name}(EntityRendererProvider.Context renderManager)"
                )
            
            (renderer_dir / f"{renderer_class_name}.java").write_text(renderer_java)
            
            # Generate Entity class
            entity_java = generate_entity_class(model_name, category)
            if class_base != to_pascal_case(model_name):
                entity_java = entity_java.replace(
                    f"class {to_pascal_case(model_name)}Entity",
                    f"class {entity_class_name}"
                )
            
            (entity_dir / f"{entity_class_name}.java").write_text(entity_java)
    
    # Generate multi-part entity classes
    print("\n  Generating multi-part entity classes...")
    for category, groups in multipart.items():
        for base_name, info in groups.items():
            class_name = info['class_name'] + "Entity"
            
            # Check if this class name collides with any standalone class
            if class_name in generated_classes:
                class_name = to_pascal_case(category) + class_name
                info['class_name'] = class_name.replace("Entity", "")
            
            generated_classes.add(class_name)
            
            # Build part info
            parts_info = []
            for part_name in info['models']:
                part_data = registry[category].get(part_name, {})
                parts_info.append({
                    'name': part_name,
                    'has_animation': part_data.get('animation') is not None,
                })
            
            # Generate multi-part entity class
            entity_java = generate_multipart_entity_class(
                info['class_name'], category, info['models']
            )
            (entity_dir / f"{class_name}.java").write_text(entity_java)
            
            # Generate multi-part GeoModel class
            model_class_name = info['class_name'] + "Model"
            if model_class_name in generated_classes:
                model_class_name = to_pascal_case(category) + model_class_name
            generated_classes.add(model_class_name)
            
            model_java = generate_multipart_geo_model_class(
                info['class_name'], category, parts_info
            )
            (model_dir / f"{model_class_name}.java").write_text(model_java)
            
            # Generate multi-part renderer class
            renderer_class_name = info['class_name'] + "Renderer"
            if renderer_class_name in generated_classes:
                renderer_class_name = to_pascal_case(category) + renderer_class_name
            generated_classes.add(renderer_class_name)
            
            renderer_java = generate_multipart_renderer_class(
                info['class_name'], category
            )
            (renderer_dir / f"{renderer_class_name}.java").write_text(renderer_java)
    
    print(f"  Generated {len(generated_classes)} Java classes total")
    
    # Step 5: Write animation_names.json
    print("\n[5/7] Writing animation_names.json...")
    anim_names_path = BUILD_DIR / "animation_names.json"
    with open(anim_names_path, 'w') as f:
        json.dump(animation_names_map, f, indent=2, sort_keys=True)
    
    anim_model_count = sum(1 for v in animation_names_map.values() if v.get('animation_names'))
    anim_clip_count = sum(len(v.get('animation_names', [])) for v in animation_names_map.values())
    print(f"  Wrote {anim_model_count} model entries with {anim_clip_count} total animation clips")
    
    # Step 6: Write RESOURCE_MAPPING.md
    print("\n[6/7] Writing RESOURCE_MAPPING.md...")
    mapping_md = generate_resource_mapping_md(registry, multipart, animation_names_map)
    (BUILD_DIR / "RESOURCE_MAPPING.md").write_text(mapping_md)
    print(f"  Written RESOURCE_MAPPING.md ({len(mapping_md)} bytes)")
    
    # Step 7: Package into ZIP
    print("\n[7/7] Packaging into ZIP...")
    
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    
    file_count = 0
    total_bytes = 0
    
    with zipfile.ZipFile(ZIP_PATH, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, dirs, files in os.walk(BUILD_DIR):
            for filename in sorted(files):
                filepath = Path(root) / filename
                arcname = str(filepath.relative_to(BUILD_DIR))
                zf.write(filepath, arcname)
                file_count += 1
                total_bytes += filepath.stat().st_size
    
    zip_size = ZIP_PATH.stat().st_size
    print(f"  Created {ZIP_PATH.name} ({zip_size / 1024:.1f} KB, {file_count} files)")
    
    # Step 8: Replace old archive
    print("\n[BONUS] Replacing old archive...")
    if OLD_ARCHIVE.exists():
        # Replace .tar.gz with .zip
        new_archive = OLD_ARCHIVE.parent / "MROLF-TGNBF.zip"
        if new_archive.exists():
            new_archive.unlink()
        shutil.copy2(ZIP_PATH, new_archive)
        print(f"  Copied to {new_archive}")
        # Optionally remove old .tar.gz
        # OLD_ARCHIVE.unlink()  # Keep for safety
    else:
        print(f"  Old archive not found at {OLD_ARCHIVE}")
    
    # ─── Final Summary ───────────────────────────────────────────────────────
    
    print("\n" + "=" * 70)
    print("BUILD COMPLETE — Summary")
    print("=" * 70)
    print(f"  Geo models:      {total_geo}")
    print(f"  Textures:        {total_tex}")
    print(f"  Animations:      {total_anim} files, {total_anim_names} clips")
    print(f"  Multi-part:      {mp_count} groups")
    print(f"  Java classes:    {len(generated_classes)}")
    print(f"  Resource files:  {file_count}")
    print(f"  ZIP size:        {zip_size / 1024:.1f} KB")
    print(f"  Output:          {ZIP_PATH}")
    print(f"  Build dir:       {BUILD_DIR}")
    print("=" * 70)
    
    return {
        'total_geo': total_geo,
        'total_tex': total_tex,
        'total_anim': total_anim,
        'total_anim_names': total_anim_names,
        'multipart_groups': mp_count,
        'java_classes': len(generated_classes),
        'file_count': file_count,
        'zip_size_kb': zip_size / 1024,
    }


if __name__ == "__main__":
    result = build_mod_dev_package()
