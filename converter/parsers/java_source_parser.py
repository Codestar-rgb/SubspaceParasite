#!/usr/bin/env python3
"""
Java Source Parser - Text/AST-based model and animation parsing
================================================================

Concrete implementations of BaseModelSourceParser and BaseAnimationSourceParser
that wrap the existing ModelConverter and AnimationConverter text-based parsing
logic for .java source files.

These parsers handle decompiled Minecraft 1.12.2 ModelBase Java source code
with SRG (obfuscated) method/field names, extracting bone hierarchy, cube
geometry, UV data, and animation information.
"""

import sys
import os
import warnings
from typing import Dict, Any, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.base_parser import BaseModelSourceParser, BaseAnimationSourceParser
from model_converter import ModelConverter, BoneData, BoxData, SRG_MAP
from animation_converter import AnimationConverter


class JavaSourceModelParser(BaseModelSourceParser):
    """Parser for decompiled Java source files containing ModelBase definitions.
    
    Wraps the existing ModelConverter._parse_text() logic to extract bone
    hierarchy, cube geometry, UV data, and texture information from Java
    source code that may contain SRG-obfuscated method and field names.
    
    Supported patterns:
      - ModelRenderer field declarations
      - ModelRenderer constructors with texture offsets
      - setRotationPoint (func_78793_a) calls
      - addBox (func_78790_a) calls
      - addChild (func_78792_a) calls
      - setRotateAngle calls
      - Direct rotation field assignments (field_78795_f/g/h)
      - Mirror assignments
      - Texture dimension assignments (field_78090_t, field_78089_u)
    """

    def __init__(self):
        """Initialize the Java source model parser."""
        self._srg_map = SRG_MAP.copy()

    def parse(self, source: str, **kwargs) -> Dict[str, Any]:
        """Parse a Java source string and return extracted model data.
        
        Args:
            source: Java source code string containing a ModelBase class definition
            **kwargs: Additional arguments:
                - srg_map (dict): Optional additional SRG→MCP mappings to merge
                
        Returns:
            Dict containing:
              - 'bones': Dict of var_name -> BoneData (with parsed pivot, rotation, boxes, etc.)
              - 'texture_width': int (default 64)
              - 'texture_height': int (default 32)
              - 'bone_mapping': Dict of var_name -> bone_name
              - 'warnings': List of warning messages
        """
        # Merge optional additional SRG mappings
        extra_srg = kwargs.get('srg_map', {})
        if extra_srg:
            self._srg_map.update(extra_srg)

        # Create a fresh ModelConverter instance and run the text-based parser
        converter = ModelConverter()
        
        try:
            converter.parse_java_source(source)
        except Exception as e:
            warnings.warn(f"Java source parsing failed: {e}")
            return {
                'bones': {},
                'texture_width': 64,
                'texture_height': 32,
                'bone_mapping': {},
                'warnings': [f"Parse error: {e}"]
            }

        # Convert BoneData objects to serializable dicts
        bones_dict = {}
        for var_name, bone in converter.bones.items():
            bones_dict[var_name] = self._bone_to_dict(bone)

        return {
            'bones': bones_dict,
            'texture_width': converter.texture_width,
            'texture_height': converter.texture_height,
            'bone_mapping': dict(converter.bone_mapping),
            'warnings': list(converter.warnings)
        }

    def get_name(self) -> str:
        """Return the parser name."""
        return "java_source"

    def get_supported_extensions(self) -> list:
        """Return list of supported file extensions."""
        return ['.java', '.jav']

    @staticmethod
    def _bone_to_dict(bone: BoneData) -> Dict[str, Any]:
        """Convert a BoneData dataclass to a serializable dictionary.
        
        Args:
            bone: BoneData instance from ModelConverter
            
        Returns:
            Dict with all bone properties including boxes as nested dicts
        """
        boxes = []
        for box in bone.boxes:
            boxes.append({
                'offset_x': box.offset_x,
                'offset_y': box.offset_y,
                'offset_z': box.offset_z,
                'width': box.width,
                'height': box.height,
                'depth': box.depth,
                'inflate': box.inflate,
                'texture_offset_u': box.texture_offset_u,
                'texture_offset_v': box.texture_offset_v,
                'mirror': box.mirror,
            })

        return {
            'name': bone.name,
            'java_var_name': bone.java_var_name,
            'pivot_x': bone.pivot_x,
            'pivot_y': bone.pivot_y,
            'pivot_z': bone.pivot_z,
            'rotate_x': bone.rotate_x,
            'rotate_y': bone.rotate_y,
            'rotate_z': bone.rotate_z,
            'boxes': boxes,
            'children': list(bone.children),
            'parent': bone.parent,
            'mirror': bone.mirror,
        }


class JavaSourceAnimationParser(BaseAnimationSourceParser):
    """Parser for decompiled Java source files containing animation code.
    
    Wraps the existing AnimationConverter and KirinAnimationConverter logic
    to extract animation data from setRotationAngles (func_78087_a) methods
    in decompiled 1.12.2 model classes.
    
    Supports two animation classes:
      - Class A-1: Time-driven animations (ageInTicks dependent) → .animation.json
      - Class A-2: Movement-driven animations (limbSwing dependent) → Java code snippets
    """

    def __init__(self):
        """Initialize the Java source animation parser."""
        self._srg_map = SRG_MAP.copy()

    def parse(self, source: str, bone_mapping: Dict[str, str], **kwargs) -> Dict[str, Any]:
        """Parse animation source code and return animation data.
        
        Args:
            source: Java source code containing setRotationAngles method
            bone_mapping: Mapping of bone variable names to bone IDs
            **kwargs: Additional arguments:
                - animation_name (str): Name for the animation (default "idle")
                - sample_count (int): Number of samples for time-driven (default 120)
                - dp_threshold (float): Douglas-Peucker threshold in degrees (default 0.01)
                - time_scale (float): Time scale factor (default 1.0)
                - use_kirin_parser (bool): Use KirinAnimationConverter (default False)
                
        Returns:
            Dict containing:
              - 'animation_json': GeckoLib animation structure (or None)
              - 'java_code': Java code snippet (or None)
              - 'anim_class': 'A-1', 'A-2', 'mixed', or 'none'
              - 'warnings': List of warning messages
        """
        animation_name = kwargs.get('animation_name', 'idle')
        sample_count = kwargs.get('sample_count', 120)
        dp_threshold = kwargs.get('dp_threshold', 0.01)
        time_scale = kwargs.get('time_scale', 1.0)
        use_kirin_parser = kwargs.get('use_kirin_parser', False)

        if use_kirin_parser:
            from animation_converter import KirinAnimationConverter
            converter = KirinAnimationConverter(bone_mapping)
            try:
                result = converter.convert_kirin_idle(
                    source,
                    sample_count=sample_count,
                    dp_threshold=dp_threshold
                )
            except Exception as e:
                warnings.warn(f"Kirin animation parsing failed: {e}")
                return {
                    'animation_json': None,
                    'java_code': None,
                    'anim_class': 'none',
                    'warnings': [f"Parse error: {e}"]
                }
        else:
            converter = AnimationConverter(bone_mapping)
            try:
                result = converter.convert_set_rotation_angles(
                    source,
                    animation_name=animation_name,
                    sample_count=sample_count,
                    dp_threshold=dp_threshold,
                    time_scale=time_scale
                )
            except Exception as e:
                warnings.warn(f"Animation parsing failed: {e}")
                return {
                    'animation_json': None,
                    'java_code': None,
                    'anim_class': 'none',
                    'warnings': [f"Parse error: {e}"]
                }

        return {
            'animation_json': result.get('animation_json'),
            'java_code': result.get('java_code'),
            'anim_class': result.get('anim_class', 'none'),
            'warnings': list(result.get('warnings', []))
        }

    def get_name(self) -> str:
        """Return the parser name."""
        return "java_source_animation"

    def get_supported_extensions(self) -> list:
        """Return list of supported file extensions."""
        return ['.java', '.jav']


# Module-level convenience function
def parse_java_model(java_source: str, **kwargs) -> Dict[str, Any]:
    """Convenience function to parse a Java model source.
    
    Args:
        java_source: Java source code string
        **kwargs: Additional parser arguments
        
    Returns:
        Model data dict as returned by JavaSourceModelParser.parse()
    """
    parser = JavaSourceModelParser()
    return parser.parse(java_source, **kwargs)


def parse_java_animation(java_source: str, bone_mapping: Dict[str, str], **kwargs) -> Dict[str, Any]:
    """Convenience function to parse a Java animation source.
    
    Args:
        java_source: Java source code string
        bone_mapping: Mapping of bone variable names to bone IDs
        **kwargs: Additional parser arguments
        
    Returns:
        Animation data dict as returned by JavaSourceAnimationParser.parse()
    """
    parser = JavaSourceAnimationParser()
    return parser.parse(java_source, bone_mapping, **kwargs)
