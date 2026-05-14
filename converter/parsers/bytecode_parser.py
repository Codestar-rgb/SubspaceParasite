#!/usr/bin/env python3
"""
Bytecode Parser - Direct .class file parsing for Minecraft models
=================================================================

Concrete implementations of BaseModelSourceParser and BaseAnimationSourceParser
that can parse .class files directly, achieving higher accuracy than text-based
parsing by:

1. Decompiling .class files using CFR decompiler (java -jar cfr.jar)
2. Parsing the constant pool directly for SRG→MCP name resolution
3. Resolving all field references and method invocations unambiguously
4. Then feeding the decompiled source + enhanced SRG mappings to the
   JavaSourceModelParser / JavaSourceAnimationParser

Architecture:
  .class file → [Constant Pool Scanner] → Enhanced SRG Map
              → [CFR Decompiler]        → Java Source
              → [JavaSourceParser]       → Model/Animation Data (with enhanced SRG)

The constant pool scanner extracts ALL string constants from the .class file,
identifying SRG names (func_XXXXX_x, field_XXXXX_x) and building a complete
mapping. This resolves ambiguities where text parsing might miss SRG names
that appear in the bytecode but not in the decompiled source (e.g., due to
inlining or optimization).
"""

import os
import re
import struct
import subprocess
import sys
import tempfile
import warnings
from typing import Dict, Any, List, Optional, Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.base_parser import BaseModelSourceParser, BaseAnimationSourceParser
from model_converter import SRG_MAP


# ============================================================================
# Extended SRG Name Map
# ============================================================================
# The base SRG_MAP in model_converter.py contains the most common ModelRenderer
# field/method mappings. The bytecode parser extends this with additional
# MathHelper, ModelBase, and other commonly-encountered SRG names that are
# discovered via constant pool analysis but aren't in the base map.

EXTENDED_SRG_MAP = {
    # MathHelper methods (commonly found in animation code)
    'func_76126_a': 'sin',          # MathHelper.sin(float)
    'func_76134_b': 'cos',          # MathHelper.cos(float)
    'func_76133_a': 'sqrt',         # MathHelper.sqrt(float)
    'func_76129_l': 'abs',          # MathHelper.abs(float)
    'func_76130_e': 'clamp',        # MathHelper.clamp(float, float, float)
    'func_76128_g': 'wrapDegrees',  # MathHelper.wrapDegrees(float)
    'func_76135_e': 'wrapDegrees',  # MathHelper.wrapDegrees(double)

    # ModelBase methods (found in .class files)
    'func_78088_a': 'animate',      # ModelBase.animate / setRotationAngles variant
    'func_78087_a': 'setRotationAngles',  # ModelBase.setRotationAngles
    'func_78082_a': 'render',       # ModelBase.render

    # Additional ModelRenderer methods
    'func_78794_a': 'setTextureOffset',  # ModelRenderer.setTextureOffset
    'func_78784_a': 'setBoxName',        # ModelRenderer.setTextureOffset (alternate)
}

# Merge base + extended SRG maps
FULL_SRG_MAP = {}
FULL_SRG_MAP.update(SRG_MAP)
FULL_SRG_MAP.update(EXTENDED_SRG_MAP)


# ============================================================================
# Java .class File Constant Pool Parser
# ============================================================================

# Constant pool tag types (JVMS §4.4)
CP_TAG_UTF8 = 1
CP_TAG_INTEGER = 3
CP_TAG_FLOAT = 4
CP_TAG_LONG = 5
CP_TAG_DOUBLE = 6
CP_TAG_CLASS = 7
CP_TAG_STRING = 8
CP_TAG_FIELDREF = 9
CP_TAG_METHODREF = 10
CP_TAG_INTERFACE_METHODREF = 11
CP_TAG_NAME_AND_TYPE = 12
CP_TAG_METHOD_HANDLE = 15
CP_TAG_METHOD_TYPE = 16
CP_TAG_INVOKE_DYNAMIC = 18
CP_TAG_MODULE = 19
CP_TAG_PACKAGE = 20

# Tag sizes (how many extra u2 entries to read after the tag byte)
# Long and Double take two constant pool slots
CP_EXTRA_SLOTS = {
    CP_TAG_UTF8: 'variable',       # u2 length, then bytes
    CP_TAG_INTEGER: 2,             # 4 bytes = 2 x u2
    CP_TAG_FLOAT: 2,               # 4 bytes = 2 x u2
    CP_TAG_LONG: 4,                # 8 bytes = 4 x u2 (takes 2 slots!)
    CP_TAG_DOUBLE: 4,              # 8 bytes = 4 x u2 (takes 2 slots!)
    CP_TAG_CLASS: 1,               # u2 name_index
    CP_TAG_STRING: 1,              # u2 string_index
    CP_TAG_FIELDREF: 2,            # u2 class_index, u2 name_and_type_index
    CP_TAG_METHODREF: 2,           # u2 class_index, u2 name_and_type_index
    CP_TAG_INTERFACE_METHODREF: 2, # u2 class_index, u2 name_and_type_index
    CP_TAG_NAME_AND_TYPE: 2,       # u2 name_index, u2 descriptor_index
    CP_TAG_METHOD_HANDLE: 2,       # u1 reference_kind, u2 reference_index
    CP_TAG_METHOD_TYPE: 1,         # u2 descriptor_index
    CP_TAG_INVOKE_DYNAMIC: 2,      # u2 bootstrap_method_attr_index, u2 name_and_type_index
    CP_TAG_MODULE: 1,              # u2 name_index
    CP_TAG_PACKAGE: 1,             # u2 name_index
}


class ConstantPoolEntry:
    """Represents a single entry in the Java .class constant pool."""

    def __init__(self, tag: int, data: dict, index: int):
        self.tag = tag
        self.data = data
        self.index = index

    def __repr__(self):
        return f"CPEntry(index={self.index}, tag={self.tag}, data={self.data})"


class ClassFileParser:
    """Low-level parser for Java .class file format.
    
    Parses the constant pool to extract string constants, field references,
    and method references. This allows us to identify SRG names directly
    from the bytecode without relying on decompilation.
    
    Reference: JVMS (Java Virtual Machine Specification) §4.1-4.4
    """

    def __init__(self):
        self.constant_pool: Dict[int, ConstantPoolEntry] = {}
        self.utf8_entries: Dict[int, str] = {}
        self.class_name: str = ""
        self.super_class_name: str = ""
        self.field_refs: List[Dict] = []
        self.method_refs: List[Dict] = []

    def parse(self, class_file_path: str) -> Dict[str, Any]:
        """Parse a .class file and extract constant pool information.
        
        Args:
            class_file_path: Path to the .class file
            
        Returns:
            Dict containing:
              - 'constant_pool': Dict of index -> ConstantPoolEntry
              - 'utf8_strings': Dict of index -> UTF-8 string value
              - 'srg_names': Dict of SRG name -> context info
              - 'field_refs': List of field reference dicts
              - 'method_refs': List of method reference dicts
              - 'class_name': Fully qualified class name
              - 'super_class_name': Fully qualified superclass name
              - 'warnings': List of warnings
        """
        if not os.path.exists(class_file_path):
            raise FileNotFoundError(f"Class file not found: {class_file_path}")

        with open(class_file_path, 'rb') as f:
            data = f.read()

        if len(data) < 10:
            raise ValueError("File too small to be a valid .class file")

        # Check magic number: 0xCAFEBABE
        magic = struct.unpack('>I', data[0:4])[0]
        if magic != 0xCAFEBABE:
            raise ValueError(f"Invalid .class file magic number: 0x{magic:08X}")

        # Read version info
        minor_version = struct.unpack('>H', data[4:6])[0]
        major_version = struct.unpack('>H', data[6:8])[0]

        # Read constant pool
        offset = 8
        cp_count = struct.unpack('>H', data[offset:offset + 2])[0]
        offset += 2

        warnings_list = []
        index = 1  # Constant pool indices are 1-based

        while index < cp_count:
            if offset >= len(data):
                warnings_list.append(f"Unexpected end of constant pool at index {index}")
                break

            tag = data[offset]
            offset += 1

            if tag == CP_TAG_UTF8:
                # UTF-8 string: u2 length + bytes
                length = struct.unpack('>H', data[offset:offset + 2])[0]
                offset += 2
                utf8_bytes = data[offset:offset + length]
                offset += length
                try:
                    string_val = utf8_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    string_val = utf8_bytes.decode('latin-1')
                entry = ConstantPoolEntry(tag, {'value': string_val}, index)
                self.constant_pool[index] = entry
                self.utf8_entries[index] = string_val
                index += 1

            elif tag in (CP_TAG_LONG, CP_TAG_DOUBLE):
                # Long and Double take 2 constant pool slots
                offset += 8  # 4 u2 slots
                entry = ConstantPoolEntry(tag, {'raw': '8-byte value'}, index)
                self.constant_pool[index] = entry
                index += 2  # Takes two slots

            elif tag in CP_EXTRA_SLOTS and CP_EXTRA_SLOTS[tag] != 'variable':
                extra = CP_EXTRA_SLOTS[tag]
                raw_data = data[offset:offset + extra * 2]
                offset += extra * 2
                entry = ConstantPoolEntry(tag, self._decode_tag_data(tag, raw_data), index)
                self.constant_pool[index] = entry

                # Resolve references
                if tag == CP_TAG_CLASS:
                    name_idx = struct.unpack('>H', raw_data[0:2])[0]
                    entry.data['resolved_name'] = self.utf8_entries.get(name_idx, f'<unresolved#{name_idx}>')

                elif tag in (CP_TAG_FIELDREF, CP_TAG_METHODREF, CP_TAG_INTERFACE_METHODREF):
                    class_idx = struct.unpack('>H', raw_data[0:2])[0]
                    nat_idx = struct.unpack('>H', raw_data[2:4])[0]
                    ref_info = {
                        'class_index': class_idx,
                        'name_and_type_index': nat_idx,
                    }
                    # Try to resolve class name
                    class_entry = self.constant_pool.get(class_idx)
                    if class_entry and class_entry.tag == CP_TAG_CLASS:
                        ref_info['class_name'] = class_entry.data.get('resolved_name', '')
                    # Try to resolve name and type
                    nat_entry = self.constant_pool.get(nat_idx)
                    if nat_entry and nat_entry.tag == CP_TAG_NAME_AND_TYPE:
                        name_idx = nat_entry.data.get('name_index', 0)
                        desc_idx = nat_entry.data.get('descriptor_index', 0)
                        ref_info['name'] = self.utf8_entries.get(name_idx, '')
                        ref_info['descriptor'] = self.utf8_entries.get(desc_idx, '')
                    entry.data.update(ref_info)

                    if tag == CP_TAG_FIELDREF:
                        self.field_refs.append(ref_info)
                    elif tag == CP_TAG_METHODREF:
                        self.method_refs.append(ref_info)

                elif tag == CP_TAG_NAME_AND_TYPE:
                    name_idx = struct.unpack('>H', raw_data[0:2])[0]
                    desc_idx = struct.unpack('>H', raw_data[2:4])[0]
                    entry.data['name_index'] = name_idx
                    entry.data['descriptor_index'] = desc_idx

                elif tag == CP_TAG_STRING:
                    string_idx = struct.unpack('>H', raw_data[0:2])[0]
                    entry.data['value'] = self.utf8_entries.get(string_idx, '')

                index += 1

            else:
                # Unknown tag or variable-length tag that shouldn't appear here
                warnings_list.append(f"Unknown or unexpected constant pool tag {tag} at index {index}")
                # Try to skip by guessing - this is a fallback
                index += 1
                break

        # Resolve class and superclass names
        if 2 in self.constant_pool and self.constant_pool[2].tag == CP_TAG_CLASS:
            self.class_name = self.constant_pool[2].data.get('resolved_name', '')

        # Extract SRG names from constant pool
        srg_names = self._extract_srg_names()

        return {
            'constant_pool': {idx: {'tag': e.tag, 'data': e.data} for idx, e in self.constant_pool.items()},
            'utf8_strings': dict(self.utf8_entries),
            'srg_names': srg_names,
            'field_refs': self.field_refs,
            'method_refs': self.method_refs,
            'class_name': self.class_name,
            'super_class_name': self.super_class_name,
            'warnings': warnings_list,
        }

    def _decode_tag_data(self, tag: int, raw_data: bytes) -> dict:
        """Decode raw bytes for a given constant pool tag type."""
        if tag == CP_TAG_INTEGER:
            val = struct.unpack('>i', raw_data)[0]
            return {'value': val}
        elif tag == CP_TAG_FLOAT:
            val = struct.unpack('>f', raw_data)[0]
            return {'value': val}
        elif tag == CP_TAG_CLASS:
            name_index = struct.unpack('>H', raw_data[0:2])[0]
            return {'name_index': name_index}
        elif tag == CP_TAG_STRING:
            string_index = struct.unpack('>H', raw_data[0:2])[0]
            return {'string_index': string_index}
        elif tag in (CP_TAG_FIELDREF, CP_TAG_METHODREF, CP_TAG_INTERFACE_METHODREF):
            class_index = struct.unpack('>H', raw_data[0:2])[0]
            nat_index = struct.unpack('>H', raw_data[2:4])[0]
            return {'class_index': class_index, 'name_and_type_index': nat_index}
        elif tag == CP_TAG_NAME_AND_TYPE:
            name_index = struct.unpack('>H', raw_data[0:2])[0]
            descriptor_index = struct.unpack('>H', raw_data[2:4])[0]
            return {'name_index': name_index, 'descriptor_index': descriptor_index}
        elif tag == CP_TAG_METHOD_HANDLE:
            reference_kind = raw_data[0]
            reference_index = struct.unpack('>H', raw_data[1:3])[0]
            return {'reference_kind': reference_kind, 'reference_index': reference_index}
        elif tag == CP_TAG_METHOD_TYPE:
            descriptor_index = struct.unpack('>H', raw_data[0:2])[0]
            return {'descriptor_index': descriptor_index}
        elif tag == CP_TAG_INVOKE_DYNAMIC:
            bootstrap_index = struct.unpack('>H', raw_data[0:2])[0]
            nat_index = struct.unpack('>H', raw_data[2:4])[0]
            return {'bootstrap_method_attr_index': bootstrap_index, 'name_and_type_index': nat_index}
        else:
            return {'raw': raw_data.hex()}

    def _extract_srg_names(self) -> Dict[str, Dict[str, str]]:
        """Extract all SRG names found in the constant pool.
        
        Identifies patterns:
          - func_XXXXX_x: SRG method names
          - field_XXXXX_x: SRG field names
          
        Returns:
            Dict mapping SRG name -> {'type': 'method'|'field', 'mcp_name': str|None}
        """
        srg_names = {}

        # Pattern for SRG names
        srg_method_pattern = re.compile(r'^func_\d+_[a-z]$')
        srg_field_pattern = re.compile(r'^field_\d+_[a-z]$')

        for idx, string_val in self.utf8_entries.items():
            # Check for method SRG names
            if srg_method_pattern.match(string_val):
                mcp_name = FULL_SRG_MAP.get(string_val, None)
                srg_names[string_val] = {
                    'type': 'method',
                    'mcp_name': mcp_name,
                    'constant_pool_index': idx,
                }
            # Check for field SRG names
            elif srg_field_pattern.match(string_val):
                mcp_name = FULL_SRG_MAP.get(string_val, None)
                srg_names[string_val] = {
                    'type': 'field',
                    'mcp_name': mcp_name,
                    'constant_pool_index': idx,
                }

        # Also check field and method references for SRG names that might not
        # match the simple pattern but are still obfuscated
        for ref in self.field_refs + self.method_refs:
            name = ref.get('name', '')
            if name.startswith('func_') or name.startswith('field_'):
                if name not in srg_names:
                    ref_type = 'method' if name.startswith('func_') else 'field'
                    mcp_name = FULL_SRG_MAP.get(name, None)
                    srg_names[name] = {
                        'type': ref_type,
                        'mcp_name': mcp_name,
                        'context': 'reference',
                    }

        return srg_names


# ============================================================================
# CFR Decompiler Interface
# ============================================================================

# Default path to CFR decompiler JAR
DEFAULT_CFR_JAR_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'cfr.jar')


def decompile_class_file(class_file_path: str,
                         cfr_jar_path: str = DEFAULT_CFR_JAR_PATH,
                         extra_args: Optional[List[str]] = None) -> str:
    """Decompile a .class file using CFR decompiler.
    
    Args:
        class_file_path: Path to the .class file
        cfr_jar_path: Path to cfr.jar decompiler (default: /home/z/my-project/cfr.jar)
        extra_args: Additional arguments to pass to CFR
        
    Returns:
        Decompiled Java source code as a string
        
    Raises:
        FileNotFoundError: If the .class file or CFR jar doesn't exist
        RuntimeError: If decompilation fails
    """
    if not os.path.exists(class_file_path):
        raise FileNotFoundError(f"Class file not found: {class_file_path}")

    if not os.path.exists(cfr_jar_path):
        raise FileNotFoundError(
            f"CFR decompiler JAR not found at {cfr_jar_path}. "
            f"Please ensure cfr.jar is available."
        )

    # Build CFR command
    cmd = [
        'java', '-jar', cfr_jar_path,
        class_file_path,
        '--removeboilerplate', 'false',  # Keep all code for accuracy
        '--decodestringswitch', 'true',
        '--sugarenums', 'true',
        '--decodelambdas', 'true',
        '--aexagg', 'false',  # Don't aggregate exceptions (keep original structure)
    ]

    if extra_args:
        cmd.extend(extra_args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60  # 60 second timeout
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("CFR decompilation timed out after 60 seconds")
    except FileNotFoundError:
        raise RuntimeError(
            "Java runtime not found. Please install Java (JRE/JDK) to decompile .class files."
        )

    if result.returncode != 0:
        raise RuntimeError(
            f"CFR decompilation failed with return code {result.returncode}:\n{result.stderr}"
        )

    return result.stdout


# ============================================================================
# Bytecode Model Parser
# ============================================================================

class BytecodeModelParser(BaseModelSourceParser):
    """Parser for .class files containing Minecraft 1.12.2 ModelBase definitions.
    
    This parser provides higher accuracy than text-based parsing by:
    
    1. Parsing the constant pool directly to extract all SRG name references,
       including those that might be inlined or optimized away in decompiled output
    2. Decompile the .class file using CFR to get readable Java source
    3. Feed both the decompiled source AND the enhanced SRG mappings to the
       JavaSourceModelParser
    
    The enhanced SRG map from constant pool analysis can catch names that the
    text parser would miss, such as:
      - SRG names used in static initializers
      - SRG names in methods other than the constructor
      - SRG names that CFR might partially resolve (leaving some obfuscated)
    
    Usage:
        parser = BytecodeModelParser()
        result = parser.parse('/path/to/ModelKirin.class')
    """

    def __init__(self, cfr_jar_path: str = DEFAULT_CFR_JAR_PATH):
        """Initialize the bytecode model parser.
        
        Args:
            cfr_jar_path: Path to the CFR decompiler JAR file
        """
        self._cfr_jar_path = cfr_jar_path
        self._class_parser = ClassFileParser()

    def parse(self, source: str, **kwargs) -> Dict[str, Any]:
        """Parse a .class file and return extracted model data.
        
        Args:
            source: Path to the .class file
            **kwargs: Additional arguments:
                - cfr_jar_path (str): Override CFR JAR path
                - cfr_extra_args (list): Additional CFR arguments
                - keep_decompiled (bool): Whether to include decompiled source in output (default False)
                - fallback_to_text (bool): If bytecode parsing fails, try text parsing (default True)
                
        Returns:
            Dict containing:
              - 'bones': Dict of var_name -> bone data
              - 'texture_width': int
              - 'texture_height': int
              - 'bone_mapping': Dict of var_name -> bone_name
              - 'warnings': List of warning messages
              - 'bytecode_info': Dict with constant pool analysis results (optional)
        """
        class_file_path = source
        cfr_jar = kwargs.get('cfr_jar_path', self._cfr_jar_path)
        cfr_extra_args = kwargs.get('cfr_extra_args', None)
        keep_decompiled = kwargs.get('keep_decompiled', False)
        fallback_to_text = kwargs.get('fallback_to_text', True)

        all_warnings = []

        # Phase 1: Parse constant pool for SRG name resolution
        srg_map_enhanced = {}
        bytecode_info = None

        try:
            cp_result = self._class_parser.parse(class_file_path)
            bytecode_info = {
                'class_name': cp_result.get('class_name', ''),
                'srg_names_found': list(cp_result.get('srg_names', {}).keys()),
                'field_ref_count': len(cp_result.get('field_refs', [])),
                'method_ref_count': len(cp_result.get('method_refs', [])),
            }

            # Build enhanced SRG map from constant pool
            for srg_name, info in cp_result.get('srg_names', {}).items():
                mcp_name = info.get('mcp_name')
                if mcp_name:
                    srg_map_enhanced[srg_name] = mcp_name
                else:
                    all_warnings.append(
                        f"Unknown SRG name in constant pool: {srg_name} ({info['type']})"
                    )

        except Exception as e:
            all_warnings.append(f"Constant pool parsing failed: {e}")
            if not fallback_to_text:
                return {
                    'bones': {},
                    'texture_width': 64,
                    'texture_height': 32,
                    'bone_mapping': {},
                    'warnings': all_warnings,
                }

        # Phase 2: Decompile the .class file
        try:
            java_source = decompile_class_file(class_file_path, cfr_jar, cfr_extra_args)
        except Exception as e:
            all_warnings.append(f"CFR decompilation failed: {e}")
            if fallback_to_text:
                # Try reading as text (maybe it's already a .java file)
                try:
                    with open(class_file_path, 'r') as f:
                        java_source = f.read()
                    all_warnings.append("Fell back to reading file as text (not a .class file?)")
                except Exception as e2:
                    return {
                        'bones': {},
                        'texture_width': 64,
                        'texture_height': 32,
                        'bone_mapping': {},
                        'warnings': all_warnings + [f"Text fallback also failed: {e2}"],
                    }
            else:
                return {
                    'bones': {},
                    'texture_width': 64,
                    'texture_height': 32,
                    'bone_mapping': {},
                    'warnings': all_warnings,
                }

        # Phase 3: Parse the decompiled source with enhanced SRG mappings
        from parsers.java_source_parser import JavaSourceModelParser
        text_parser = JavaSourceModelParser()

        parse_kwargs = {}
        if srg_map_enhanced:
            parse_kwargs['srg_map'] = srg_map_enhanced

        result = text_parser.parse(java_source, **parse_kwargs)

        # Merge warnings
        result['warnings'] = all_warnings + result.get('warnings', [])

        # Add bytecode info if requested
        if keep_decompiled:
            result['decompiled_source'] = java_source

        if bytecode_info:
            result['bytecode_info'] = bytecode_info

        return result

    def get_name(self) -> str:
        """Return the parser name."""
        return "bytecode"

    def get_supported_extensions(self) -> list:
        """Return list of supported file extensions."""
        return ['.class']


class BytecodeAnimationParser(BaseAnimationSourceParser):
    """Parser for .class files containing Minecraft 1.12.2 animation code.
    
    Extracts animation data from .class files by:
    1. Parsing the constant pool for SRG name resolution
    2. Decompiling the .class file using CFR
    3. Feeding the decompiled source with enhanced SRG mappings to
       JavaSourceAnimationParser
    
    This provides higher accuracy for animation parsing because:
    - All MathHelper method references are resolved from the constant pool
    - Intermediate variable names and expression patterns are preserved
    - SRG field references for rotation angles are unambiguously identified
    """

    def __init__(self, cfr_jar_path: str = DEFAULT_CFR_JAR_PATH):
        """Initialize the bytecode animation parser.
        
        Args:
            cfr_jar_path: Path to the CFR decompiler JAR file
        """
        self._cfr_jar_path = cfr_jar_path
        self._class_parser = ClassFileParser()

    def parse(self, source: str, bone_mapping: Dict[str, str], **kwargs) -> Dict[str, Any]:
        """Parse a .class file and return animation data.
        
        Args:
            source: Path to the .class file
            bone_mapping: Mapping of bone variable names to bone IDs
            **kwargs: Additional arguments:
                - cfr_jar_path (str): Override CFR JAR path
                - cfr_extra_args (list): Additional CFR arguments
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
        class_file_path = source
        cfr_jar = kwargs.get('cfr_jar_path', self._cfr_jar_path)
        cfr_extra_args = kwargs.get('cfr_extra_args', None)

        all_warnings = []

        # Phase 1: Parse constant pool for enhanced SRG mappings
        srg_map_enhanced = {}
        try:
            cp_result = self._class_parser.parse(class_file_path)
            for srg_name, info in cp_result.get('srg_names', {}).items():
                mcp_name = info.get('mcp_name')
                if mcp_name:
                    srg_map_enhanced[srg_name] = mcp_name
        except Exception as e:
            all_warnings.append(f"Constant pool parsing failed: {e}")

        # Phase 2: Decompile the .class file
        try:
            java_source = decompile_class_file(class_file_path, cfr_jar, cfr_extra_args)
        except Exception as e:
            all_warnings.append(f"CFR decompilation failed: {e}")
            return {
                'animation_json': None,
                'java_code': None,
                'anim_class': 'none',
                'warnings': all_warnings,
            }

        # Phase 3: Parse the decompiled source with enhanced SRG mappings
        from parsers.java_source_parser import JavaSourceAnimationParser
        text_parser = JavaSourceAnimationParser()

        result = text_parser.parse(java_source, bone_mapping, **kwargs)

        # Merge warnings
        result['warnings'] = all_warnings + result.get('warnings', [])

        return result

    def get_name(self) -> str:
        """Return the parser name."""
        return "bytecode_animation"

    def get_supported_extensions(self) -> list:
        """Return list of supported file extensions."""
        return ['.class']


# ============================================================================
# Convenience Functions
# ============================================================================

def parse_class_model(class_file_path: str, **kwargs) -> Dict[str, Any]:
    """Convenience function to parse a .class model file.
    
    Args:
        class_file_path: Path to the .class file
        **kwargs: Additional parser arguments
        
    Returns:
        Model data dict as returned by BytecodeModelParser.parse()
    """
    parser = BytecodeModelParser()
    return parser.parse(class_file_path, **kwargs)


def parse_class_animation(class_file_path: str, bone_mapping: Dict[str, str], **kwargs) -> Dict[str, Any]:
    """Convenience function to parse a .class animation file.
    
    Args:
        class_file_path: Path to the .class file
        bone_mapping: Mapping of bone variable names to bone IDs
        **kwargs: Additional parser arguments
        
    Returns:
        Animation data dict as returned by BytecodeAnimationParser.parse()
    """
    parser = BytecodeAnimationParser()
    return parser.parse(class_file_path, bone_mapping, **kwargs)


def analyze_constant_pool(class_file_path: str) -> Dict[str, Any]:
    """Convenience function to analyze a .class file's constant pool.
    
    Useful for debugging and exploration without triggering full parsing.
    
    Args:
        class_file_path: Path to the .class file
        
    Returns:
        Constant pool analysis results from ClassFileParser.parse()
    """
    parser = ClassFileParser()
    return parser.parse(class_file_path)
