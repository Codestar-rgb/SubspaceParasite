"""Parsers package - bytecode and text-based model source parsers.

Provides a plugin architecture for parsing Minecraft 1.12.2 entity model
and animation data from different source formats.

Available parsers:
  - JavaSourceModelParser: Parses decompiled .java source code
  - JavaSourceAnimationParser: Parses animation code from .java source
  - BytecodeModelParser: Parses .class files directly via CFR decompilation
  - BytecodeAnimationParser: Parses .class animation files

Registry:
  - ParserRegistry: Auto-detects correct parser based on file extension

Quick usage:
    from parsers import ParserRegistry

    registry = ParserRegistry()

    # Auto-detect and parse a .class file
    model_data = registry.parse_model('/path/to/ModelKirin.class')

    # Auto-detect and parse a .java file
    with open('/path/to/ModelKirin.java') as f:
        model_data = registry.parse_model(f.read(), source_format='java')

    # Parse animation data
    anim_data = registry.parse_animation(
        '/path/to/ModelKirin.class',
        bone_mapping=model_data['bone_mapping']
    )
"""

import os
from typing import Dict, Any, Optional

from parsers.base_parser import BaseModelSourceParser, BaseAnimationSourceParser, BaseOutputFormatter
from parsers.java_source_parser import JavaSourceModelParser, JavaSourceAnimationParser
from parsers.bytecode_parser import (
    BytecodeModelParser,
    BytecodeAnimationParser,
    ClassFileParser,
    decompile_class_file,
    analyze_constant_pool,
)


# ============================================================================
# Parser Registry
# ============================================================================

class ParserRegistry:
    """Registry for model and animation source parsers.
    
    Manages parser registration and provides auto-detection of the correct
    parser based on file extension. Supports both model and animation parsers.
    
    Usage:
        registry = ParserRegistry()
        
        # Auto-detect parser and parse a file
        model_data = registry.parse_model('/path/to/ModelKirin.class')
        
        # Explicitly specify parser type
        model_data = registry.parse_model(source, parser_name='java_source')
        
        # Register a custom parser
        registry.register_model_parser(MyCustomModelParser())
    """

    def __init__(self):
        """Initialize the registry with default parsers."""
        self._model_parsers: dict = {}   # name -> parser instance
        self._animation_parsers: dict = {}  # name -> parser instance
        self._extension_model_map: dict = {}   # extension -> parser name
        self._extension_animation_map: dict = {}  # extension -> parser name

        # Register default parsers
        self._register_defaults()

    def _register_defaults(self):
        """Register the built-in default parsers."""
        # Model parsers
        java_model = JavaSourceModelParser()
        self.register_model_parser(java_model)

        bytecode_model = BytecodeModelParser()
        self.register_model_parser(bytecode_model)

        # Animation parsers
        java_anim = JavaSourceAnimationParser()
        self.register_animation_parser(java_anim)

        bytecode_anim = BytecodeAnimationParser()
        self.register_animation_parser(bytecode_anim)

    # ------------------------------------------------------------------
    # Registration Methods
    # ------------------------------------------------------------------

    def register_model_parser(self, parser: BaseModelSourceParser) -> None:
        """Register a model source parser.
        
        Args:
            parser: An instance of a BaseModelSourceParser subclass
            
        Raises:
            TypeError: If parser is not a BaseModelSourceParser instance
            ValueError: If a parser with the same name is already registered
        """
        if not isinstance(parser, BaseModelSourceParser):
            raise TypeError(
                f"Model parser must be a BaseModelSourceParser instance, "
                f"got {type(parser).__name__}"
            )

        name = parser.get_name()
        if name in self._model_parsers:
            raise ValueError(
                f"Model parser '{name}' is already registered. "
                f"Use unregister_model_parser() first if you want to replace it."
            )

        self._model_parsers[name] = parser

        # Map file extensions to this parser
        for ext in parser.get_supported_extensions():
            # First registered parser wins for each extension
            if ext not in self._extension_model_map:
                self._extension_model_map[ext] = name

    def register_animation_parser(self, parser: BaseAnimationSourceParser) -> None:
        """Register an animation source parser.
        
        Args:
            parser: An instance of a BaseAnimationSourceParser subclass
            
        Raises:
            TypeError: If parser is not a BaseAnimationSourceParser instance
            ValueError: If a parser with the same name is already registered
        """
        if not isinstance(parser, BaseAnimationSourceParser):
            raise TypeError(
                f"Animation parser must be a BaseAnimationSourceParser instance, "
                f"got {type(parser).__name__}"
            )

        name = parser.get_name()
        if name in self._animation_parsers:
            raise ValueError(
                f"Animation parser '{name}' is already registered. "
                f"Use unregister_animation_parser() first if you want to replace it."
            )

        self._animation_parsers[name] = parser

        # Map file extensions to this parser
        for ext in parser.get_supported_extensions():
            if ext not in self._extension_animation_map:
                self._extension_animation_map[ext] = name

    def unregister_model_parser(self, name: str) -> None:
        """Unregister a model parser by name.
        
        Args:
            name: The parser name to unregister
        """
        if name in self._model_parsers:
            parser = self._model_parsers.pop(name)
            # Remove extension mappings
            for ext in parser.get_supported_extensions():
                if self._extension_model_map.get(ext) == name:
                    del self._extension_model_map[ext]

    def unregister_animation_parser(self, name: str) -> None:
        """Unregister an animation parser by name.
        
        Args:
            name: The parser name to unregister
        """
        if name in self._animation_parsers:
            parser = self._animation_parsers.pop(name)
            for ext in parser.get_supported_extensions():
                if self._extension_animation_map.get(ext) == name:
                    del self._extension_animation_map[ext]

    # ------------------------------------------------------------------
    # Query Methods
    # ------------------------------------------------------------------

    def get_model_parser(self, name: str) -> BaseModelSourceParser:
        """Get a registered model parser by name.
        
        Args:
            name: Parser name
            
        Returns:
            The parser instance
            
        Raises:
            KeyError: If no parser with that name is registered
        """
        if name not in self._model_parsers:
            raise KeyError(
                f"No model parser registered with name '{name}'. "
                f"Available: {list(self._model_parsers.keys())}"
            )
        return self._model_parsers[name]

    def get_animation_parser(self, name: str) -> BaseAnimationSourceParser:
        """Get a registered animation parser by name.
        
        Args:
            name: Parser name
            
        Returns:
            The parser instance
            
        Raises:
            KeyError: If no parser with that name is registered
        """
        if name not in self._animation_parsers:
            raise KeyError(
                f"No animation parser registered with name '{name}'. "
                f"Available: {list(self._animation_parsers.keys())}"
            )
        return self._animation_parsers[name]

    def list_model_parsers(self) -> list:
        """List all registered model parser names."""
        return list(self._model_parsers.keys())

    def list_animation_parsers(self) -> list:
        """List all registered animation parser names."""
        return list(self._animation_parsers.keys())

    def detect_model_parser(self, source: str) -> BaseModelSourceParser:
        """Auto-detect the appropriate model parser based on source.
        
        Detection strategy:
          1. If source is a file path that exists, check the extension
          2. If source looks like a file path but doesn't exist, check extension
          3. Otherwise, default to java_source parser (treat as Java source text)
          
        Args:
            source: File path or Java source text
            
        Returns:
            The appropriate model parser instance
            
        Raises:
            ValueError: If no suitable parser is found
        """
        # Try to detect from file extension
        ext = self._detect_extension(source)

        if ext and ext in self._extension_model_map:
            parser_name = self._extension_model_map[ext]
            return self._model_parsers[parser_name]

        # Default: treat as Java source text
        if 'java_source' in self._model_parsers:
            return self._model_parsers['java_source']

        raise ValueError(
            f"Could not auto-detect parser for source. "
            f"Available extensions: {list(self._extension_model_map.keys())}"
        )

    def detect_animation_parser(self, source: str) -> BaseAnimationSourceParser:
        """Auto-detect the appropriate animation parser based on source.
        
        Same detection strategy as detect_model_parser().
        
        Args:
            source: File path or Java source text
            
        Returns:
            The appropriate animation parser instance
            
        Raises:
            ValueError: If no suitable parser is found
        """
        ext = self._detect_extension(source)

        if ext and ext in self._extension_animation_map:
            parser_name = self._extension_animation_map[ext]
            return self._animation_parsers[parser_name]

        # Default: treat as Java source text
        if 'java_source_animation' in self._animation_parsers:
            return self._animation_parsers['java_source_animation']

        raise ValueError(
            f"Could not auto-detect parser for source. "
            f"Available extensions: {list(self._extension_animation_map.keys())}"
        )

    # ------------------------------------------------------------------
    # Parsing Methods (High-Level API)
    # ------------------------------------------------------------------

    def parse_model(self, source: str, parser_name: str = None, **kwargs) -> Dict[str, Any]:
        """Parse a model source and return extracted model data.
        
        Auto-detects the appropriate parser unless parser_name is specified.
        
        Args:
            source: File path or Java source text
            parser_name: Optional explicit parser name to use
            **kwargs: Additional parser-specific arguments
            
        Returns:
            Dict containing:
              - 'bones': Dict of var_name -> bone data
              - 'texture_width': int
              - 'texture_height': int
              - 'bone_mapping': Dict of var_name -> bone_name
              - 'warnings': List of warning messages
        """
        if parser_name:
            parser = self.get_model_parser(parser_name)
        else:
            parser = self.detect_model_parser(source)

        return parser.parse(source, **kwargs)

    def parse_animation(self, source: str, bone_mapping: Dict[str, str],
                        parser_name: str = None, **kwargs) -> Dict[str, Any]:
        """Parse an animation source and return animation data.
        
        Auto-detects the appropriate parser unless parser_name is specified.
        
        Args:
            source: File path or Java source text
            bone_mapping: Mapping of bone variable names to bone IDs
            parser_name: Optional explicit parser name to use
            **kwargs: Additional parser-specific arguments
            
        Returns:
            Dict containing:
              - 'animation_json': GeckoLib animation structure (or None)
              - 'java_code': Java code snippet (or None)
              - 'anim_class': 'A-1', 'A-2', 'mixed', or 'none'
              - 'warnings': List of warning messages
        """
        if parser_name:
            parser = self.get_animation_parser(parser_name)
        else:
            parser = self.detect_animation_parser(source)

        return parser.parse(source, bone_mapping, **kwargs)

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_extension(source: str) -> str:
        """Detect file extension from a source string.
        
        Args:
            source: File path or source text
            
        Returns:
            File extension with dot (e.g., '.class', '.java') or empty string
        """
        # If source contains newlines or is very long without being a path,
        # it's likely source text, not a file path
        if '\n' in source or '\r' in source:
            return ''

        # Check if it looks like a file path
        # Must contain at least one path character and a dot extension
        potential_ext = os.path.splitext(source)[1].lower()
        if potential_ext and len(potential_ext) <= 10:
            return potential_ext

        return ''


# ============================================================================
# Module-Level Exports
# ============================================================================

# Base classes
__all__ = [
    # Base classes
    'BaseModelSourceParser',
    'BaseAnimationSourceParser',
    'BaseOutputFormatter',
    # Java source parsers
    'JavaSourceModelParser',
    'JavaSourceAnimationParser',
    # Bytecode parsers
    'BytecodeModelParser',
    'BytecodeAnimationParser',
    'ClassFileParser',
    'decompile_class_file',
    'analyze_constant_pool',
    # Registry
    'ParserRegistry',
]


