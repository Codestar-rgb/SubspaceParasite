"""Base parser abstract classes for the plugin architecture."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseModelSourceParser(ABC):
    """Abstract base class for model source parsers.
    
    Parsers extract bone hierarchy, cube geometry, UV data, and texture
    information from different source formats (decompiled Java, .class files, etc.).
    """

    @abstractmethod
    def parse(self, source: str, **kwargs) -> Dict[str, Any]:
        """Parse a model source and return extracted model data.
        
        Args:
            source: The model source (Java source code, class file path, etc.)
            **kwargs: Additional parser-specific arguments
            
        Returns:
            Dict containing:
              - 'bones': Dict of var_name -> BoneData
              - 'texture_width': int
              - 'texture_height': int
              - 'bone_mapping': Dict of var_name -> bone_name
              - 'warnings': List of warning messages
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Return the parser name."""
        pass

    @abstractmethod
    def get_supported_extensions(self) -> list:
        """Return list of supported file extensions (e.g., ['.java', '.class'])."""
        pass


class BaseAnimationSourceParser(ABC):
    """Abstract base class for animation source parsers."""

    @abstractmethod
    def parse(self, source: str, bone_mapping: Dict[str, str], **kwargs) -> Dict[str, Any]:
        """Parse animation source and return animation data.
        
        Args:
            source: The animation source code
            bone_mapping: Mapping of bone variable names to bone IDs
            **kwargs: Additional parser-specific arguments
            
        Returns:
            Dict containing:
              - 'animation_json': GeckoLib animation structure (or None)
              - 'java_code': Java code snippet (or None)
              - 'anim_class': 'A-1', 'A-2', 'mixed', or 'none'
              - 'warnings': List of warning messages
        """
        pass


class BaseOutputFormatter(ABC):
    """Abstract base class for output formatters."""

    @abstractmethod
    def format_model(self, model_data: Dict[str, Any], **kwargs) -> str:
        """Format model data into the output string.
        
        Args:
            model_data: The model data structure
            **kwargs: Additional formatter-specific arguments
            
        Returns:
            Formatted string (JSON, Java, etc.)
        """
        pass

    @abstractmethod
    def get_format_name(self) -> str:
        """Return the format name (e.g., 'geckoLib_game', 'blockbench')."""
        pass
