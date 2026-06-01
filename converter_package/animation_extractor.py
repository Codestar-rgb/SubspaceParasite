#!/usr/bin/env python3
"""
AnimationExtractor - High-Precision Animation Extraction Engine
================================================================
Extracts animations from MC 1.12.2 Java model source code and converts
them to GeckoLib 1.20.1 animation format with correct naming, state
classification, and numerical sampling.

Supports:
  - State machine parsing (getParasiteStatus, getOpen, getFlyingState, etc.)
  - swingX/Y/Z helper expansion to mathematical expressions
  - moveY helper expansion to position offset expressions
  - Direct rotation/position/visibility assignments
  - Compound assignments (+=)
  - Intermediate variable resolution
  - Numerical sampling with Douglas-Peucker simplification
  - Proper animation naming for mod development
  - Loop continuity enforcement

Output format: GeckoLib .animation.json structure
  {
    "format_version": "1.8.0",
    "animations": {
      "animation.modelName.idle": { ... },
      "animation.modelName.walk": { ... },
      ...
    }
  }
"""

import json
import math
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Set


# ============================================================================
# Field Name Mappings (SRG → descriptive)
# ============================================================================

ROTATION_FIELDS = {
    'field_78795_f': 'x',   # rotateAngleX
    'field_78796_g': 'y',   # rotateAngleY
    'field_78808_h': 'z',   # rotateAngleZ
}

POSITION_FIELDS = {
    'field_82906_o': 'x',   # offsetX
    'field_82907_q': 'z',   # offsetZ
    'field_82908_p': 'y',   # offsetY
}

VISIBILITY_FIELD = 'field_78807_k'  # showModel


# ============================================================================
# State Name Mapping
# ============================================================================

STATUS_NAMES = {
    0: 'idle',
    1: 'evolved',
    2: 'attack',
    3: 'death',
    4: 'stage4',
    5: 'stage5',
    6: 'stage6',
    7: 'stage7',
    8: 'stage8',
    9: 'stage9',
    10: 'sleeping',
    11: 'stage11',
    15: 'dormant',
}


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class BoneAssignment:
    """A single bone rotation/position/visibility assignment."""
    bone_var: str
    channel: str           # 'rotation', 'position', 'visibility'
    axis: str              # 'x', 'y', 'z' for rotation/position; '' for visibility
    expression: str        # The Java expression
    is_compound: bool = False  # True for += assignments


@dataclass
class AnimationState:
    """Represents a single animation state extracted from Java source."""
    name: str                     # Animation name suffix (e.g., 'idle', 'walk')
    condition_desc: str           # Human-readable condition description
    bone_assignments: List[BoneAssignment] = field(default_factory=list)
    vars_def: Dict[str, str] = field(default_factory=dict)
    is_walk: bool = False
    is_idle: bool = False


# ============================================================================
# AnimationExtractor
# ============================================================================

class AnimationExtractor:
    """
    Extracts animations from MC 1.12.2 Java model source code.
    """

    def __init__(self, bone_mapping: Dict[str, str] = None):
        self.bone_mapping = bone_mapping or {}
        self.warnings: List[str] = []
        self._max_bones = 0

    def extract(self, java_source: str, model_name: str, max_bones: int = 0) -> Optional[dict]:
        """Extract all animations from a Java model source file.
        
        Args:
            java_source: The full Java source code of the model class
            model_name: The model name (used for animation naming)
            max_bones: Maximum number of animated bones to process (0 = no limit).
                      Models with more animated bones will be skipped.
        """
        self.warnings = []
        self._max_bones = max_bones
        
        method_body = self._find_method_body(java_source)
        if not method_body:
            return None
        
        # Check if there are any animation-driving expressions
        if not self._has_animations(method_body):
            return None
        
        # Parse into animation states
        state_blocks = self._parse_all_states(method_body)
        if not state_blocks:
            return None
        
        animation_json = self._build_animation_json(state_blocks, model_name)
        return animation_json

    # ========================================================================
    # Method Body Extraction
    # ========================================================================

    def _find_method_body(self, java_source: str) -> Optional[str]:
        """Find the setRotationAngles (func_78087_a) method body."""
        patterns = [
            r'public\s+void\s+func_78087_a\s*\([^)]+\)\s*\{',
            r'public\s+void\s+setRotationAngles\s*\([^)]+\)\s*\{',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, java_source, re.DOTALL)
            if match:
                start_pos = match.end() - 1
                body = self._extract_brace_block(java_source, start_pos)
                if body:
                    return body
        return None

    def _extract_brace_block(self, source: str, start_pos: int) -> Optional[str]:
        """Extract content between matching braces starting at start_pos."""
        if start_pos >= len(source) or source[start_pos] != '{':
            return None
        depth = 0
        for i in range(start_pos, len(source)):
            if source[i] == '{':
                depth += 1
            elif source[i] == '}':
                depth -= 1
                if depth == 0:
                    return source[start_pos + 1:i]
        return None

    def _has_animations(self, method_body: str) -> bool:
        """Check if the method body contains any animation-driving code."""
        animation_indicators = [
            r'ageInTicks',
            r'limbSwing',
            r'MathHelper\.',
            r'swingX\(',
            r'swingY\(',
            r'swingZ\(',
            r'moveY\(',
            r'field_78795_f\s*=\s*[^;0]+',  # non-zero rotation
            r'field_78796_g\s*=\s*[^;0]+',
            r'field_78808_h\s*=\s*[^;0]+',
        ]
        for pattern in animation_indicators:
            if re.search(pattern, method_body):
                return True
        return False

    # ========================================================================
    # State Parsing - Comprehensive Approach
    # ========================================================================

    def _parse_all_states(self, method_body: str) -> List[AnimationState]:
        """
        Parse all animation states from the method body.
        Handles: getParasiteStatus() if/else, boolean conditions, 
        attack timer blocks, and unconditional code.
        """
        states = []
        
        # 1. Find the status variable (getParasiteStatus)
        status_var = None
        status_match = re.search(r'byte\s+(\w+)\s*=\s*\w+\.getParasiteStatus\(\)', method_body)
        if status_match:
            status_var = status_match.group(1)
        
        # 2. Find boolean variables
        bool_vars = {}
        for match in re.finditer(r'boolean\s+(\w+)\s*=\s*\w+\.(\w+)\(\)', method_body):
            bool_vars[match.group(1)] = match.group(2)
        
        # 3. Find float state variables
        float_vars = {}
        for match in re.finditer(r'float\s+(\w+)\s*=\s*\w+\.(\w+)\(\)', method_body):
            float_vars[match.group(1)] = match.group(2)
        
        # 4. Parse based on the condition type found
        if status_var:
            states = self._parse_status_states(method_body, status_var)
        elif bool_vars:
            states = self._parse_boolean_states(method_body, bool_vars)
        else:
            # Single state or float-var-driven states
            states = self._parse_default_states(method_body, float_vars)
        
        # 5. Look for standalone attack/additive blocks after the main conditions
        attack_states = self._find_attack_blocks(method_body, float_vars)
        for as_ in attack_states:
            # Don't duplicate if already captured
            existing_names = {s.name for s in states}
            if as_.name not in existing_names:
                states.append(as_)
        
        return states

    def _parse_status_states(self, method_body: str, status_var: str) -> List[AnimationState]:
        """Parse states from a getParasiteStatus()-driven if/else chain."""
        states = []
        
        # Find all if/else if blocks containing the status variable
        # Use a robust approach: scan for 'if' keywords at the top level
        # and check if the condition involves the status variable
        
        blocks = self._extract_top_level_if_blocks(method_body)
        
        status_blocks = []
        other_blocks = []
        
        for block_info in blocks:
            condition = block_info['condition']
            if status_var in condition:
                status_blocks.append(block_info)
            else:
                other_blocks.append(block_info)
        
        if not status_blocks:
            # No status-based if blocks - treat as single state
            return self._parse_default_states(method_body, {})
        
        # Parse each status block
        for block_info in status_blocks:
            condition = block_info['condition']
            body = block_info['body']
            is_else = block_info.get('is_else', False)
            
            # Extract status value from condition
            status_values = self._extract_status_values(condition, status_var)
            
            if status_values:
                primary_val = min(status_values)
                state_name = STATUS_NAMES.get(primary_val, f'stage{primary_val}')
            elif is_else:
                state_name = 'other'
            else:
                state_name = 'unknown'
            
            # Check for stillAni sub-condition
            still_ani_match = re.search(
                r'if\s*\(\s*!?\s*\w+\.getStillAni\(\)\s*\)\s*\{', body
            )
            
            if still_ani_match:
                # Split into walk (inside !stillAni) and idle (outside)
                still_brace = still_ani_match.end() - 1
                walk_body = self._extract_brace_block(body, still_brace)
                negate = '!' in still_ani_match.group(0)
                
                if walk_body and negate:
                    # Walk animation (when NOT still)
                    walk_state = AnimationState(
                        name=f'{state_name}_walk',
                        condition_desc=f'status={status_values} && !stillAni',
                    )
                    walk_state.bone_assignments = self._extract_all_assignments(walk_body)
                    walk_state.vars_def = self._parse_intermediate_vars(walk_body)
                    self._classify_state(walk_state)
                    states.append(walk_state)
                
                # Idle animation: code outside the stillAni block
                idle_code = body[:still_ani_match.start()] + body[still_brace + len(walk_body or '') + 2:]
                idle_assignments = self._extract_all_assignments(idle_code)
                idle_vars = self._parse_intermediate_vars(idle_code)
                
                if idle_assignments:
                    idle_state = AnimationState(
                        name=f'{state_name}',
                        condition_desc=f'status={status_values} (idle)',
                    )
                    idle_state.bone_assignments = idle_assignments
                    idle_state.vars_def = idle_vars
                    self._classify_state(idle_state)
                    states.append(idle_state)
            else:
                # No stillAni split - entire block is one state
                state = AnimationState(
                    name=state_name,
                    condition_desc=f'status={status_values}',
                )
                state.bone_assignments = self._extract_all_assignments(body)
                state.vars_def = self._parse_intermediate_vars(body)
                self._classify_state(state)
                states.append(state)
        
        # Handle trailing code (after all if/else blocks)
        # This often contains ambient/idle animations (ageInTicks-driven)
        trailing = self._extract_trailing_code(method_body, blocks)
        if trailing:
            trailing_assignments = self._extract_all_assignments(trailing)
            trailing_vars = self._parse_intermediate_vars(trailing)
            # Filter to only non-zero, non-reset assignments
            non_reset = [a for a in trailing_assignments
                        if not self._is_reset_assignment(a)]
            if non_reset:
                # Check if trailing code has ageInTicks-driven assignments
                has_age_ticks = False
                for a in non_reset:
                    full_expr = self._resolve_vars(a.expression, trailing_vars)
                    if 'ageInTicks' in full_expr:
                        has_age_ticks = True
                        break
                
                if has_age_ticks:
                    # Trailing code contains idle/ambient animations.
                    # Add trailing assignments AND vars to all existing states
                    # so each state gets both walk + ambient animations.
                    for state in states:
                        # Merge trailing intermediate variables
                        for var_name, var_expr in trailing_vars.items():
                            if var_name not in state.vars_def:
                                state.vars_def[var_name] = var_expr
                        
                        existing = {(a.bone_var, a.channel, a.axis) for a in state.bone_assignments}
                        for a in non_reset:
                            if (a.bone_var, a.channel, a.axis) not in existing:
                                state.bone_assignments.append(a)
                        
                        # Re-classify since we added new assignments
                        self._classify_state(state)
                    
                    # Also create a standalone ambient/idle state if trailing has
                    # ageInTicks-driven bones not covered by any existing state
                    trailing_age_bones = set()
                    for a in non_reset:
                        full_expr = self._resolve_vars(a.expression, trailing_vars)
                        if 'ageInTicks' in full_expr:
                            trailing_age_bones.add(a.bone_var)
                    
                    # Check if any existing idle state already covers these bones
                    covered_bones = set()
                    for state in states:
                        if state.is_idle:
                            for a in state.bone_assignments:
                                covered_bones.add(a.bone_var)
                    
                    uncovered = trailing_age_bones - covered_bones
                    if uncovered or not any(s.is_idle for s in states):
                        # Create a separate ambient/idle state
                        ambient_state = AnimationState(
                            name='ambient',
                            condition_desc='always (trailing code)',
                        )
                        ambient_state.bone_assignments = [a for a in non_reset
                            if 'ageInTicks' in self._resolve_vars(a.expression, trailing_vars)]
                        ambient_state.vars_def = trailing_vars.copy()
                        self._classify_state(ambient_state)
                        if ambient_state.is_idle and ambient_state.bone_assignments:
                            states.append(ambient_state)
                else:
                    # No ageInTicks in trailing - just add as common code
                    for state in states:
                        existing = {(a.bone_var, a.channel, a.axis) for a in state.bone_assignments}
                        for a in non_reset:
                            if (a.bone_var, a.channel, a.axis) not in existing:
                                state.bone_assignments.append(a)
        
        return states

    def _parse_boolean_states(self, method_body: str, bool_vars: Dict[str, str]) -> List[AnimationState]:
        """Parse states from boolean variable conditions (getOpen, etc.)."""
        states = []
        
        blocks = self._extract_top_level_if_blocks(method_body)
        
        last_if_condition = None  # Track the previous if condition for else blocks
        
        for block_info in blocks:
            condition = block_info['condition']
            body = block_info['body']
            is_else = block_info.get('is_else', False)
            
            if condition == 'else' and last_if_condition:
                # This is the else block of a previous if
                # Derive name from the inverse of the previous condition
                prev_var = None
                for var_name in bool_vars:
                    if var_name in last_if_condition:
                        prev_var = var_name
                        break
                
                if prev_var:
                    method_name = bool_vars.get(prev_var, prev_var)
                    # Invert the previous condition's naming
                    was_negated = f'!{prev_var}' in last_if_condition or f'! {prev_var}' in last_if_condition
                    if was_negated:
                        # Previous was negated (e.g., !open), else is positive (open)
                        if method_name == 'getOpen':
                            state_name = 'open'
                        else:
                            state_name = method_name.replace('get', '').lower()
                    else:
                        # Previous was positive, else is negated
                        if method_name == 'getOpen':
                            state_name = 'closed'
                        else:
                            state_name = f'not_{method_name.replace("get", "").lower()}'
                else:
                    # Float variable else block - name based on inverse
                    # e.g., if "ft6 > 0" was previous, else means "ft6 <= 0"
                    float_cond_match = re.match(r'(\w+)\s*[><=!]+', last_if_condition)
                    if float_cond_match:
                        state_name = f'not_{float_cond_match.group(1)}'
                    else:
                        state_name = 'else'
                
                last_if_condition = None  # Reset
            else:
                # Determine which boolean variable this condition uses
                matched_var = None
                is_negated = False
                for var_name in bool_vars:
                    if var_name in condition:
                        matched_var = var_name
                        is_negated = f'!{var_name}' in condition or f'! {var_name}' in condition
                        break
                
                if matched_var is None:
                    if 'getStillAni' in condition:
                        continue
                    # For float var conditions (attack timer, digging, etc.)
                    # Try to extract a meaningful name from the condition
                    matched_var = condition.strip()
                    is_negated = False
                    
                    # Clean up float variable condition names
                    # e.g., "ft6 > 0.0f" -> extract var name for better naming
                    float_cond_match = re.match(r'(\w+)\s*[><=!]+', matched_var)
                    if float_cond_match:
                        float_var_name = float_cond_match.group(1)
                        # Try to derive a meaningful name from the variable
                        # Common patterns: ft6=diggingModel, f5=attackTimer
                        float_name_map = {
                            'diggingModel': 'digging',
                            'attackTimer': 'attack',
                            'digging': 'digging',
                        }
                        # Check if we can find the variable's purpose in the source
                        # For now, use a generic but clean name
                        matched_var = float_var_name  # Use just the variable name, not the whole condition
                
                # Determine state name
                method_name = bool_vars.get(matched_var, matched_var)
                if is_negated:
                    if method_name == 'getOpen':
                        state_name = 'closed'
                    else:
                        state_name = f'not_{method_name.replace("get", "").lower()}'
                else:
                    if method_name == 'getOpen':
                        state_name = 'open'
                    else:
                        state_name = method_name.replace('get', '').lower()
                
                last_if_condition = condition
            
            state = AnimationState(
                name=state_name,
                condition_desc=condition.strip(),
            )
            state.bone_assignments = self._extract_all_assignments(body)
            state.vars_def = self._parse_intermediate_vars(body)
            self._classify_state(state)
            states.append(state)
        
        # If no boolean-based blocks found, try the whole method
        if not states:
            return self._parse_default_states(method_body, {})
        
        # Handle trailing code
        trailing = self._extract_trailing_code(method_body, blocks)
        if trailing:
            trailing_assignments = self._extract_all_assignments(trailing)
            trailing_vars = self._parse_intermediate_vars(trailing)
            non_reset = [a for a in trailing_assignments
                        if not self._is_reset_assignment(a)]
            if non_reset:
                # Check if trailing has ageInTicks-driven code
                has_age_ticks = False
                for a in non_reset:
                    full_expr = self._resolve_vars(a.expression, trailing_vars)
                    if 'ageInTicks' in full_expr:
                        has_age_ticks = True
                        break
                
                if has_age_ticks:
                    # Merge trailing vars and assignments into existing states
                    for state in states:
                        for var_name, var_expr in trailing_vars.items():
                            if var_name not in state.vars_def:
                                state.vars_def[var_name] = var_expr
                        existing = {(a.bone_var, a.channel, a.axis) for a in state.bone_assignments}
                        for a in non_reset:
                            if (a.bone_var, a.channel, a.axis) not in existing:
                                state.bone_assignments.append(a)
                        self._classify_state(state)
                    
                    # Also create ambient state if no idle state exists
                    if not any(s.is_idle for s in states):
                        ambient_state = AnimationState(
                            name='ambient',
                            condition_desc='always (trailing code)',
                        )
                        ambient_state.bone_assignments = [a for a in non_reset
                            if 'ageInTicks' in self._resolve_vars(a.expression, trailing_vars)]
                        ambient_state.vars_def = trailing_vars.copy()
                        self._classify_state(ambient_state)
                        if ambient_state.is_idle and ambient_state.bone_assignments:
                            states.append(ambient_state)
                else:
                    for state in states:
                        existing = {(a.bone_var, a.channel, a.axis) for a in state.bone_assignments}
                        for a in non_reset:
                            if (a.bone_var, a.channel, a.axis) not in existing:
                                state.bone_assignments.append(a)
        
        return states

    def _parse_default_states(self, method_body: str, float_vars: Dict) -> List[AnimationState]:
        """Parse states when no status or boolean conditions exist."""
        assignments = self._extract_all_assignments(method_body)
        vars_def = self._parse_intermediate_vars(method_body)
        
        if not assignments:
            return []
        
        state = AnimationState(name='idle', condition_desc='always')
        state.bone_assignments = assignments
        state.vars_def = vars_def
        self._classify_state(state)
        return [state]

    def _find_attack_blocks(self, method_body: str, float_vars: Dict) -> List[AnimationState]:
        """Find standalone attack/additive animation blocks."""
        states = []
        
        for var_name, method_name in float_vars.items():
            # Look for: if (varName > 0.0f) { ... += ... }
            pattern = re.compile(
                r'if\s*\(\s*' + re.escape(var_name) + r'\s*>\s*0\.0f?\s*\)\s*\{'
            )
            match = pattern.search(method_body)
            if match:
                body = self._extract_brace_block(method_body, match.end() - 1)
                if body:
                    # Check if it contains += assignments
                    assignments = self._extract_all_assignments(body)
                    compound_assigns = [a for a in assignments if a.is_compound]
                    
                    if compound_assigns:
                        # Create attack state
                        # For attack animations, the compound assignments are additive
                        # We need the base state + the additive part
                        state = AnimationState(
                            name='attack',
                            condition_desc=f'{var_name} > 0',
                        )
                        state.bone_assignments = compound_assigns
                        state.vars_def = self._parse_intermediate_vars(body)
                        state.is_idle = True  # attack timers are time-driven
                        states.append(state)
        
        return states

    # ========================================================================
    # Top-Level If/Else Block Extraction
    # ========================================================================

    def _extract_top_level_if_blocks(self, code: str) -> List[dict]:
        """
        Extract all top-level if/else if/else blocks from code.
        Returns list of dicts with keys: condition, body, is_else, position.
        """
        blocks = []
        
        # Pre-compute brace depth at each position
        depth_map = [0] * len(code)
        depth = 0
        for i, ch in enumerate(code):
            if ch == '{':
                depth_map[i] = depth
                depth += 1
            elif ch == '}':
                depth -= 1
                depth_map[i] = depth
            else:
                depth_map[i] = depth
        
        # Find all 'if' and 'else' keywords at depth 0
        pos = 0
        code_len = len(code)
        
        while pos < code_len:
            # Find next 'if' or 'else' at depth 0
            next_if = -1
            next_else = -1
            
            search_pos = pos
            while search_pos < code_len:
                idx = code.find('if', search_pos)
                if idx < 0:
                    break
                # Check it's a keyword (not part of another word)
                if (idx == 0 or not code[idx-1].isalnum()) and depth_map[idx] == 0:
                    # Check the char after 'if' is not alphanumeric
                    if idx + 2 >= code_len or not code[idx+2].isalnum():
                        next_if = idx
                        break
                search_pos = idx + 2
            
            search_pos = pos
            while search_pos < code_len:
                idx = code.find('else', search_pos)
                if idx < 0:
                    break
                if (idx == 0 or not code[idx-1].isalnum()) and depth_map[idx] == 0:
                    if idx + 4 >= code_len or not code[idx+4].isalnum():
                        next_else = idx
                        break
                search_pos = idx + 4
            
            # Pick the earliest
            candidates = []
            if next_if >= 0:
                candidates.append(next_if)
            if next_else >= 0:
                candidates.append(next_else)
            
            if not candidates:
                break
            
            earliest = min(candidates)
            remaining = code[earliest:]
            
            # Try to match: else if (condition) {
            else_if_match = re.match(r'else\s+if\s*\(([^)]+)\)\s*\{', remaining)
            if_match = re.match(r'if\s*\(([^)]+)\)\s*\{', remaining)
            else_match = re.match(r'else\s*\{', remaining)
            
            if else_if_match and earliest == next_else:
                condition = else_if_match.group(1).strip()
                brace_start = earliest + else_if_match.end() - 1
                body = self._extract_brace_block(code, brace_start)
                if body:
                    blocks.append({
                        'condition': condition,
                        'body': body,
                        'is_else': True,
                        'position': earliest,
                    })
                    pos = brace_start + len(body) + 2
                else:
                    pos = earliest + 5
            elif if_match and earliest == next_if:
                condition = if_match.group(1).strip()
                brace_start = earliest + if_match.end() - 1
                body = self._extract_brace_block(code, brace_start)
                if body:
                    blocks.append({
                        'condition': condition,
                        'body': body,
                        'is_else': False,
                        'position': earliest,
                    })
                    pos = brace_start + len(body) + 2
                else:
                    pos = earliest + 3
            elif else_match and earliest == next_else:
                brace_start = earliest + else_match.end() - 1
                body = self._extract_brace_block(code, brace_start)
                if body:
                    blocks.append({
                        'condition': 'else',
                        'body': body,
                        'is_else': True,
                        'position': earliest,
                    })
                    pos = brace_start + len(body) + 2
                else:
                    pos = earliest + 5
            else:
                pos = earliest + 2
        
        return blocks

    def _extract_trailing_code(self, method_body: str, blocks: List[dict]) -> Optional[str]:
        """Find code after the last if/else block."""
        if not blocks:
            return None
        
        last_block = blocks[-1]
        # Find where the last block ends in the method body
        last_pos = last_block['position']
        
        # Find the opening brace of the last block
        brace_search = method_body.find('{', last_pos)
        if brace_search == -1:
            return None
        
        body = self._extract_brace_block(method_body, brace_search)
        if body is None:
            return None
        
        end_pos = brace_search + len(body) + 2
        
        # Check for more else/else if blocks
        remaining = method_body[end_pos:].lstrip()
        while remaining.startswith('else'):
            else_brace = remaining.find('{')
            if else_brace == -1:
                break
            else_body = self._extract_brace_block(remaining, else_brace)
            if else_body is None:
                break
            end_pos += else_brace + len(else_body) + 2
            remaining = method_body[end_pos:].lstrip()
        
        # Extract trailing code
        trailing = method_body[end_pos:].strip()
        
        # Filter out non-animation code
        lines = trailing.split('\n')
        anim_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith('this.underground'):
                continue
            if stripped.startswith('super.'):
                continue
            anim_lines.append(line)
        
        return '\n'.join(anim_lines) if anim_lines else None

    # ========================================================================
    # Assignment Extraction
    # ========================================================================

    def _extract_all_assignments(self, code: str) -> List[BoneAssignment]:
        """Extract all bone rotation, position, and visibility assignments from code."""
        assignments = []
        
        # Track which (bone_var, channel, axis) we've already seen from swingX/Y/Z
        # to avoid duplicating when there's also a direct assignment
        swing_assigned = set()
        
        # 1. Expand swingX/Y/Z calls FIRST (they're higher priority)
        swing_assignments = self._expand_swing_calls(code)
        for a in swing_assignments:
            assignments.append(a)
            swing_assigned.add((a.bone_var, a.channel, a.axis))
        
        # 2. Direct rotation assignments: this.bone.field_xxx = expr;
        rot_pattern = re.compile(
            r'this\.(\w+)\.(field_78795_f|field_78796_g|field_78808_h)\s*(\+?=)\s*([^;]+);'
        )
        for match in rot_pattern.finditer(code):
            bone_var = match.group(1)
            field_name = match.group(2)
            op = match.group(3)
            expr = match.group(4).strip()
            
            if bone_var not in self.bone_mapping:
                continue
            
            axis = ROTATION_FIELDS[field_name]
            key = (bone_var, 'rotation', axis)
            
            # Skip if already assigned by swingX/Y/Z (swing overrides direct assignment)
            if key in swing_assigned:
                continue
            
            is_compound = (op == '+=')
            
            # Handle compound: this.bone.field += expr
            # For sampling, we need the full expression (base + additive)
            # But we don't know the base value at this point
            # Store as compound for separate handling
            
            assignments.append(BoneAssignment(
                bone_var=bone_var,
                channel='rotation',
                axis=axis,
                expression=expr,
                is_compound=is_compound,
            ))
        
        # 3. Position offset assignments: this.bone.field_xxx = expr;
        pos_pattern = re.compile(
            r'this\.(\w+)\.(field_82906_o|field_82907_q|field_82908_p)\s*(\+?=)\s*([^;]+);'
        )
        for match in pos_pattern.finditer(code):
            bone_var = match.group(1)
            field_name = match.group(2)
            op = match.group(3)
            expr = match.group(4).strip()
            
            if bone_var not in self.bone_mapping:
                continue
            
            axis = POSITION_FIELDS[field_name]
            is_compound = (op == '+=')
            
            assignments.append(BoneAssignment(
                bone_var=bone_var,
                channel='position',
                axis=axis,
                expression=expr,
                is_compound=is_compound,
            ))
        
        # 4. Visibility assignments
        vis_pattern = re.compile(
            r'this\.(\w+)\.' + re.escape(VISIBILITY_FIELD) + r'\s*=\s*([^;]+);'
        )
        for match in vis_pattern.finditer(code):
            bone_var = match.group(1)
            expr = match.group(2).strip()
            
            if bone_var not in self.bone_mapping:
                continue
            
            assignments.append(BoneAssignment(
                bone_var=bone_var,
                channel='visibility',
                axis='',
                expression=expr,
            ))
        
        # 5. Expand moveY calls
        move_assignments = self._expand_move_y_calls(code)
        assignments.extend(move_assignments)
        
        return assignments

    def _expand_swing_calls(self, code: str) -> List[BoneAssignment]:
        """
        Expand swingX/Y/Z calls to equivalent direct bone rotation assignments.
        
        Overload 1 (6 args): swingX(bone, speed, degree, invert, limbSwing, limbSwingAmount)
          → bone.rotateAngleX = invert * limbSwingAmount * degree * cos(limbSwing * speed) * limbSwingAmount
          
        Overload 2 (8 args): swingX(bone, speed, degree, invert, offset, weight, limbSwing, limbSwingAmount)
          → bone.rotateAngleX = invert * limbSwingAmount * degree * cos(limbSwing * speed + offset) * limbSwingAmount + weight * limbSwingAmount
          
        Overload 3 (7 args): swingX(pref, bone, speed, degree, invert, limbSwing, limbSwingAmount)
          → bone.rotateAngleX = pref + invert * limbSwingAmount * degree * cos(limbSwing * speed) * limbSwingAmount
        """
        assignments = []
        
        for swing_method, axis in [('swingX', 'x'), ('swingY', 'y'), ('swingZ', 'z')]:
            # Find all calls to this.swingX/Y/Z
            # Match: this.swingX(args...)
            call_pattern = re.compile(
                r'this\.' + swing_method + r'\s*\(([^)]+)\)'
            )
            
            for match in call_pattern.finditer(code):
                args_str = match.group(1)
                # Parse arguments carefully - split by comma but respect parentheses
                args = self._parse_method_args(args_str)
                
                if len(args) < 6:
                    continue
                
                # Determine overload by checking first arg
                first_arg = args[0].strip()
                
                if first_arg.startswith('this.'):
                    # First arg is a bone reference → Overload 1 or 2
                    bone_var = first_arg.replace('this.', '').strip()
                    
                    if bone_var not in self.bone_mapping:
                        continue
                    
                    if len(args) == 6:
                        # Overload 1: swingX(bone, speed, degree, invert, limbSwing, limbSwingAmount)
                        speed = args[1].strip()
                        degree = args[2].strip()
                        invert = args[3].strip()
                        limbSwing = args[4].strip()
                        limbSwingAmount = args[5].strip()
                        
                        expr = f'{invert} * {limbSwingAmount} * {degree} * MathHelper.cos({limbSwing} * {speed}) * {limbSwingAmount}'
                        
                    elif len(args) == 8:
                        # Overload 2: swingX(bone, speed, degree, invert, offset, weight, limbSwing, limbSwingAmount)
                        speed = args[1].strip()
                        degree = args[2].strip()
                        invert = args[3].strip()
                        offset = args[4].strip()
                        weight = args[5].strip()
                        limbSwing = args[6].strip()
                        limbSwingAmount = args[7].strip()
                        
                        expr = f'{invert} * {limbSwingAmount} * {degree} * MathHelper.cos({limbSwing} * {speed} + {offset}) * {limbSwingAmount} + {weight} * {limbSwingAmount}'
                    else:
                        continue
                    
                else:
                    # First arg is NOT a bone → Overload 3: swingX(pref, bone, speed, ...)
                    if len(args) == 7:
                        pref = args[0].strip()
                        bone_ref = args[1].strip()
                        
                        if bone_ref.startswith('this.'):
                            bone_var = bone_ref.replace('this.', '').strip()
                        else:
                            continue
                        
                        if bone_var not in self.bone_mapping:
                            continue
                        
                        speed = args[2].strip()
                        degree = args[3].strip()
                        invert = args[4].strip()
                        limbSwing = args[5].strip()
                        limbSwingAmount = args[6].strip()
                        
                        expr = f'{pref} + {invert} * {limbSwingAmount} * {degree} * MathHelper.cos({limbSwing} * {speed}) * {limbSwingAmount}'
                    else:
                        continue
                
                assignments.append(BoneAssignment(
                    bone_var=bone_var,
                    channel='rotation',
                    axis=axis,
                    expression=expr,
                ))
        
        return assignments

    def _expand_move_y_calls(self, code: str) -> List[BoneAssignment]:
        """
        Expand moveY calls to position offset assignments.
        moveY(bone, speed, invert, f, f1, distance)
          → bone.offsetY = invert * cos(f * speed) * f1 * distance
        """
        assignments = []
        
        pattern = re.compile(r'this\.moveY\s*\(([^)]+)\)')
        for match in pattern.finditer(code):
            args_str = match.group(1)
            args = self._parse_method_args(args_str)
            
            if len(args) < 6:
                continue
            
            bone_ref = args[0].strip()
            if bone_ref.startswith('this.'):
                bone_var = bone_ref.replace('this.', '').strip()
            else:
                continue
            
            if bone_var not in self.bone_mapping:
                continue
            
            speed = args[1].strip()
            invert = args[2].strip()
            f = args[3].strip()
            f1 = args[4].strip()
            distance = args[5].strip()
            
            expr = f'{invert} * MathHelper.cos({f} * {speed}) * {f1} * {distance}'
            assignments.append(BoneAssignment(
                bone_var=bone_var,
                channel='position',
                axis='y',
                expression=expr,
            ))
        
        return assignments

    def _parse_method_args(self, args_str: str) -> List[str]:
        """Parse method arguments, handling nested parentheses and casts."""
        args = []
        current = ''
        depth = 0
        
        for ch in args_str:
            if ch == '(' :
                depth += 1
                current += ch
            elif ch == ')':
                depth -= 1
                current += ch
            elif ch == ',' and depth == 0:
                args.append(current.strip())
                current = ''
            else:
                current += ch
        
        if current.strip():
            args.append(current.strip())
        
        return args

    # ========================================================================
    # Intermediate Variable Parsing
    # ========================================================================

    def _parse_intermediate_vars(self, code: str) -> Dict[str, str]:
        """Parse intermediate variable definitions from code.
        
        Handles both declarations (float x = expr;) and re-assignments (x = expr;).
        Re-assignments are common for variables like GS, GD that are set differently
        per animation state (e.g., GS = 2.1f; inside an idle block, GS = 2.7f; inside evolved).
        """
        vars_def = {}
        
        # Pattern 1: Type-prefixed declarations: float/double varName = expr;
        typed_pattern = re.compile(r'(?:float|double)\s+(\w+)\s*=\s*([^;]+);')
        
        # Pattern 2: Re-assignments without type prefix: varName = expr;
        # Must be at start of line or after a semicolon/brace to avoid matching
        # bone.field = expr; or this.bone.field = expr;
        reassign_pattern = re.compile(r'(?:^|[{;}\n])\s*(\w+)\s*=\s*([^;]+);', re.MULTILINE)
        
        # Known intermediate variable name patterns
        known_var_names = {'GS', 'GD', 'j', 'nf2'}
        
        def is_valid_var_name(name):
            """Check if a variable name looks like an intermediate var."""
            if name in known_var_names:
                return True
            if re.match(r'^[fgn]\w*\d+$', name):
                return True
            if re.match(r'^[fg]\d+$', name):
                return True
            # Also accept short all-caps names used as animation params (GS, GD, GF, etc.)
            if re.match(r'^[A-Z]{1,3}$', name) and name not in ('IF', 'FOR', 'NEW', 'INT', 'TRY'):
                return True
            return False
        
        def is_valid_expr(expr_str):
            """Check if an expression is a valid intermediate var value."""
            # Skip if expression contains bone field assignments
            if re.search(r'field_\d+\w', expr_str) and 'this.' in expr_str:
                return False
            # Skip entity method calls
            if expr_str.startswith('parasite.') or expr_str.startswith('entityIn.'):
                return False
            # Skip keywords
            if expr_str.strip() in ('0.0f', '0', '0.0', 'false'):
                # Zero assignments are OK - they're defaults that get overridden
                return True
            return True
        
        # Process type-prefixed declarations
        for match in typed_pattern.finditer(code):
            var_name = match.group(1)
            var_expr = match.group(2).strip()
            
            # Skip keywords
            if var_name in ('this', 'if', 'else', 'for', 'while', 'return', 'byte',
                          'float', 'int', 'boolean', 'double', 'scaleFactor'):
                continue
            
            if is_valid_var_name(var_name) and is_valid_expr(var_expr):
                vars_def[var_name] = var_expr
        
        # Process re-assignments (overwrite previous values if same variable)
        for match in reassign_pattern.finditer(code):
            var_name = match.group(1)
            var_expr = match.group(2).strip()
            
            # Skip keywords and Java keywords
            if var_name in ('this', 'if', 'else', 'for', 'while', 'return', 'byte',
                          'float', 'int', 'boolean', 'double', 'scaleFactor', 'new',
                          'super', 'null', 'true', 'false', 'class', 'void'):
                continue
            
            if is_valid_var_name(var_name) and is_valid_expr(var_expr):
                vars_def[var_name] = var_expr  # Overwrite with latest value
        
        return vars_def

    # ========================================================================
    # State Classification
    # ========================================================================

    def _classify_state(self, state: AnimationState) -> None:
        """Classify a state as walk, idle, or both based on its assignments."""
        has_limb = False
        has_age = False
        
        for assignment in state.bone_assignments:
            full_expr = self._resolve_vars(assignment.expression, state.vars_def)
            if 'limbSwing' in full_expr:
                has_limb = True
            if 'ageInTicks' in full_expr:
                has_age = True
        
        state.is_walk = has_limb
        state.is_idle = has_age

    def _is_reset_assignment(self, a: BoneAssignment) -> bool:
        """Check if an assignment is a reset (sets bone to 0)."""
        expr = a.expression.strip()
        return expr in ('0.0f', '0', '0.0', '0.0F', 'false', 'False')

    # ========================================================================
    # Numerical Sampling
    # ========================================================================

    def _sample_animation(
        self,
        state: AnimationState,
        is_walk: bool = False,
        sample_count: int = 120,
        dp_threshold: float = 0.08,
    ) -> dict:
        """Sample a single animation state numerically."""
        # Check max_bones limit
        unique_bones = set()
        for assignment in state.bone_assignments:
            bone_name = self.bone_mapping.get(assignment.bone_var, assignment.bone_var)
            unique_bones.add(bone_name)
        
        if self._max_bones > 0 and len(unique_bones) > self._max_bones:
            # Too many bones - skip this animation
            return {}
        
        # Group assignments by bone and channel
        bone_channels: Dict[str, Dict[str, Dict[str, str]]] = {}
        
        for assignment in state.bone_assignments:
            bone_name = self.bone_mapping.get(assignment.bone_var, assignment.bone_var)
            
            if bone_name not in bone_channels:
                bone_channels[bone_name] = {}
            if assignment.channel not in bone_channels[bone_name]:
                bone_channels[bone_name][assignment.channel] = {}
            
            # Skip compound assignments for now (they need special handling)
            if assignment.is_compound:
                continue
            
            # Only keep the first assignment per (bone, channel, axis)
            if assignment.axis not in bone_channels[bone_name][assignment.channel]:
                bone_channels[bone_name][assignment.channel][assignment.axis] = assignment.expression
        
        if not bone_channels:
            return {}
        
        # Determine sampling parameters
        if is_walk:
            # Vanilla MC walk cycle: cos(limbSwing * 0.6662)
            # Full cosine period = 2π in limbSwing space.
            # In MC, limbSwing is distance-based, NOT time.
            # At normal walking speed, one full cycle takes ~0.6667s (40 ticks / 20 tps).
            # We sample limbSwing from 0 to 2π over a real-time duration of 0.6667s.
            walk_duration = 0.6667  # seconds - vanilla MC walk cycle duration
            limb_swing_max = 2 * math.pi  # One full cosine cycle in limbSwing space
            limb_swing_amount = 0.35
            age_ratio = 0.0  # No ageInTicks influence in pure walk
        else:
            # For idle/ambient animations, ageInTicks is in TICKS (1/20 second).
            # The _estimate_period returns the period in tick-space.
            # We need to convert to seconds for the animation timeline.
            period_ticks = self._estimate_period(state)
            period_seconds = period_ticks / 20.0  # Convert ticks to seconds
            period_seconds = min(period_seconds, 4.0)  # Cap at 4 seconds for practical use
            period_seconds = max(period_seconds, 0.5)  # Minimum 0.5 seconds
            age_ratio = 0
        
        if is_walk:
            dt = walk_duration / sample_count
        else:
            dt = period_seconds / sample_count
        bones_data = {}
        
        for bone_name, channels in bone_channels.items():
            bone_anim = {}
            
            for channel, axis_exprs in channels.items():
                keyframes = []
                
                for i in range(sample_count + 1):
                    t = i * dt
                    
                    if is_walk:
                        # Map time [0, walk_duration] to limbSwing [0, 2π]
                        # This ensures one full walk cycle plays in 0.6667s
                        limb_swing = limb_swing_max * (t / walk_duration) if walk_duration > 0 else 0.0
                        # Reduced limbSwingAmount for more natural leg swing.
                        # SRP's swingX formula: amplitude = limbSwingAmount^2 * degree
                        # With 0.35: amplitude = 0.1225 * degree (natural-looking)
                        limb_swing_amount = 0.35
                        age_in_ticks = t * age_ratio
                    else:
                        limb_swing = 0.0
                        limb_swing_amount = 0.0
                        # ageInTicks in MC is in TICKS (1/20 second), not seconds.
                        # Convert: ticks = seconds * 20
                        age_in_ticks = t * 20.0
                    
                    kf = {'time': t}
                    
                    for axis, expr in axis_exprs.items():
                        try:
                            value = self._evaluate_expression(
                                expr, age_in_ticks, limb_swing, limb_swing_amount,
                                state.vars_def
                            )
                            
                            # Apply M_MODEL coordinate transform
                            if channel == 'rotation':
                                if axis == 'y':
                                    value = -value
                                elif axis == 'z':
                                    value = -value
                                value = math.degrees(value)
                            elif channel == 'position':
                                if axis == 'y':
                                    value = -value * 16.0
                                elif axis == 'z':
                                    value = -value * 16.0
                                else:
                                    value = value * 16.0
                            
                            kf[axis] = round(value, 4)
                        except Exception:
                            kf[axis] = 0.0
                    
                    keyframes.append(kf)
                
                # Smooth loop enforcement for ALL loop animations
                if keyframes and len(keyframes) > 2:
                    first = keyframes[0]
                    last = keyframes[-1]

                    # Check if last naturally matches first
                    max_diff = 0.0
                    for axis in ['x', 'y', 'z']:
                        if axis in first and axis in last:
                            max_diff = max(max_diff, abs(last[axis] - first[axis]))

                    if max_diff > 0.5:
                        # Significant mismatch - apply Gaussian-weighted crossfade over last 15% of samples
                        crossfade_count = max(3, len(keyframes) * 15 // 100)
                        for j in range(crossfade_count):
                            idx = len(keyframes) - crossfade_count + j
                            if idx < 0 or idx >= len(keyframes):
                                continue
                            # Gaussian-weighted blend: stronger blending toward the end
                            t_norm = (j + 1) / crossfade_count  # 0→1
                            alpha = 1.0 - math.exp(-3.0 * t_norm * t_norm)  # Gaussian curve
                            kf_cur = keyframes[idx]
                            for axis in ['x', 'y', 'z']:
                                if axis in first and axis in kf_cur:
                                    target = first[axis]
                                    current = kf_cur[axis]
                                    kf_cur[axis] = current + (target - current) * alpha
                    else:
                        # Small mismatch - just snap last to first
                        for axis in ['x', 'y', 'z']:
                            if axis in first and axis in last:
                                last[axis] = first[axis]
                
                # Simplify with Douglas-Peucker
                simplified = self._douglas_peucker_simplify(keyframes, dp_threshold)
                
                # Post-DP loop continuity enforcement
                # After DP simplification, first and last keyframes may have drifted.
                # Ensure the last keyframe exactly matches the first for seamless loops.
                if simplified and len(simplified) > 1:
                    first_kf = simplified[0]
                    last_kf = simplified[-1]
                    for axis in ['x', 'y', 'z']:
                        if axis in first_kf and axis in last_kf:
                            # Snap last to first
                            last_kf[axis] = first_kf[axis]
                    # Also ensure the second-to-last keyframe doesn't create a sudden jump
                    if len(simplified) > 2:
                        second_last = simplified[-2]
                        for axis in ['x', 'y', 'z']:
                            if axis in second_last and axis in last_kf:
                                diff = abs(second_last[axis] - last_kf[axis])
                                if diff > abs(first_kf.get(axis, 0) - last_kf.get(axis, 0)) * 3:
                                    # Too big a jump - interpolate
                                    if len(simplified) > 3:
                                        third_last = simplified[-3]
                                        if axis in third_last:
                                            # Linear interpolate
                                            second_last[axis] = third_last[axis] + (last_kf[axis] - third_last[axis]) * 0.7
                
                # Detect easing type based on the expression pattern
                easing = "linear"
                for assignment in state.bone_assignments:
                    bone_name_check = self.bone_mapping.get(assignment.bone_var, assignment.bone_var)
                    if bone_name_check == bone_name and assignment.channel == channel:
                        resolved = self._resolve_vars(assignment.expression, state.vars_def)
                        if 'cos' in resolved or 'sin' in resolved:
                            # Cosine/sine-driven bones use easeInOut for natural motion
                            easing = "easeInOutSine"
                            break

                # Build channel data in GeckoLib format
                channel_data = {}
                for axis in ['x', 'y', 'z']:
                    axis_keyframes = {}
                    for kf in simplified:
                        if axis in kf:
                            axis_keyframes[f"{kf['time']:.4f}"] = kf[axis]
                    if axis_keyframes:
                        # Add easing to keyframes if non-linear
                        if easing != "linear":
                            new_axis_data = {}
                            for time_str, val in axis_keyframes.items():
                                new_axis_data[time_str] = {"vector": val, "easing": easing}
                            channel_data[axis] = new_axis_data
                        else:
                            channel_data[axis] = axis_keyframes
                
                if channel_data:
                    bone_anim[channel] = channel_data
            
            if bone_anim:
                bones_data[bone_name] = bone_anim
        
        return bones_data

    def _estimate_period(self, state: AnimationState) -> float:
        """Estimate the animation period from all expressions.
        
        Finds all frequency components and computes a common period where
        ALL bones complete integer cycles for seamless looping.
        
        IMPORTANT: Returns the period in ageInTicks units (ticks, 1/20 second).
        The caller must convert to seconds: period_seconds = period / 20.0
        """
        frequencies = []
        
        for assignment in state.bone_assignments:
            expr = self._resolve_vars(assignment.expression, state.vars_def)
            # Find all frequency multipliers on ageInTicks
            for freq_match in re.finditer(r'ageInTicks\s*\*\s*\(?\s*([\d.]+)', expr):
                try:
                    freq = float(freq_match.group(1))
                    if 0 < freq < 50:  # Sanity check
                        frequencies.append(freq)
                except ValueError:
                    pass
            # Also check for: (float)ageInTicks * X pattern
            for freq_match in re.finditer(r'ageInTicks\s*\*\s*([\d.]+)', expr):
                try:
                    freq = float(freq_match.group(1))
                    if 0 < freq < 50 and freq not in frequencies:
                        frequencies.append(freq)
                except ValueError:
                    pass
        
        if not frequencies:
            # Default: ~100 ticks = 5 seconds (typical ambient animation)
            return 100.0
        
        # Find the fundamental period: period = 2π / freq (in tick-space)
        # We need a common period T where T * freq_i / (2π) is an integer for all i
        # i.e., T = N * 2π / gcd_of_frequencies
        # Use the LCM approach: find T such that all freq * T / (2π) are integers
        
        # Group similar frequencies (within 1% tolerance)
        unique_freqs = []
        for f in sorted(frequencies):
            is_similar = False
            for uf in unique_freqs:
                if abs(f - uf) / max(uf, 0.001) < 0.01:
                    is_similar = True
                    break
            if not is_similar:
                unique_freqs.append(f)
        
        if len(unique_freqs) == 1:
            period = 2 * math.pi / unique_freqs[0]
        else:
            # Find LCM of periods: LCM(T1, T2, ...) where Ti = 2π/fi
            # LCM of rationals: find the smallest T where T*fi/(2π) is integer for all i
            # Simplified: T = 2π * LCM(numerators) / GCD(denominators)
            
            # Convert frequencies to rational approximations
            from fractions import Fraction
            frac_freqs = [Fraction(f).limit_denominator(1000) for f in unique_freqs]
            
            # Find LCM of periods: T_i = 2π / f_i = 2π * denom_i / numer_i
            # LCM(T_1, T_2, ...) = 2π * LCM(denom_i) / GCD(numer_i)
            denoms = [f.denominator for f in frac_freqs]
            numers = [f.numerator for f in frac_freqs]
            
            from math import gcd
            from functools import reduce
            
            def lcm(a, b):
                return a * b // gcd(a, b)
            
            lcm_denom = reduce(lcm, denoms)
            gcd_numer = reduce(gcd, numers)
            
            period = 2 * math.pi * lcm_denom / gcd_numer
            
            # Cap at reasonable duration (in ticks)
            period = min(period, 200.0)  # 200 ticks = 10 seconds max
        
        # Ensure period is at least 10 ticks (0.5 seconds) for visual quality
        period = max(period, 10.0)
        
        return period

    # ========================================================================
    # Expression Evaluation
    # ========================================================================

    def _evaluate_expression(
        self,
        expr: str,
        age_in_ticks: float = 0.0,
        limb_swing: float = 0.0,
        limb_swing_amount: float = 0.0,
        vars_def: Dict[str, str] = None,
    ) -> float:
        """Evaluate a Java math expression with the given parameter values."""
        if vars_def is None:
            vars_def = {}
        
        py_expr = expr
        
        # Resolve intermediate variable references
        for _ in range(10):
            changed = False
            for var_name, var_expr in vars_def.items():
                if re.search(r'\b' + re.escape(var_name) + r'\b', py_expr):
                    py_expr = re.sub(r'\b' + re.escape(var_name) + r'\b', f'({var_expr})', py_expr)
                    changed = True
            if not changed:
                break
        
        # Handle ternary operators
        py_expr = self._resolve_ternary(py_expr)
        
        # Replace MathHelper methods
        math_replacements = [
            (r'MathHelper\.func_76134_b', 'math.cos'),
            (r'MathHelper\.func_76126_a', 'math.sin'),
            (r'MathHelper\.func_76133_a', 'math.sin'),
            (r'MathHelper\.func_76129_a', 'math.sqrt'),
            (r'MathHelper\.func_76142_g', 'math.floor'),
            (r'MathHelper\.func_76128_c', 'math.abs'),
            (r'MathHelper\.cos', 'math.cos'),
            (r'MathHelper\.sin', 'math.sin'),
            (r'MathHelper\.sqrt', 'math.sqrt'),
            (r'MathHelper\.abs', 'math.abs'),
            (r'Math\.sin', 'math.sin'),
            (r'Math\.cos', 'math.cos'),
            (r'Math\.sqrt', 'math.sqrt'),
            (r'Math\.abs', 'math.abs'),
            (r'Math\.floor', 'math.floor'),
            (r'Math\.ceil', 'math.ceil'),
            (r'Math\.max', 'max'),
            (r'Math\.min', 'min'),
        ]
        
        for pattern, replacement in math_replacements:
            py_expr = re.sub(pattern, replacement, py_expr)
        
        py_expr = py_expr.replace('Math.PI', str(math.pi))
        py_expr = py_expr.replace('PI', str(math.pi))
        
        # Replace Java float suffixes
        py_expr = re.sub(r'(\d+(?:\.\d+)?)[fF](?!\w)', r'\1', py_expr)
        
        # Replace parameter references
        py_expr = py_expr.replace('ageInTicks', str(age_in_ticks))
        py_expr = py_expr.replace('limbSwingAmount', str(limb_swing_amount))
        py_expr = py_expr.replace('limbSwing', str(limb_swing))
        
        # Handle partialTicks
        py_expr = re.sub(r'\bpartialTick[s]?\b', '0.5', py_expr)
        
        # Remove explicit casts
        py_expr = re.sub(r'\(float\)', '', py_expr)
        py_expr = re.sub(r'\(double\)', '', py_expr)
        py_expr = re.sub(r'\(int\)', '', py_expr)
        
        # Entity method defaults
        entity_defaults = [
            (r'\w+\.getBODY\(\)', '1.0'),
            (r'\w+\.getOpen\(\)', '1'),
            (r'\w+\.getBurrowTimer\(\)', '0.0'),
            (r'\w+\.getBurrowed\(\)', '0'),
            (r'\w+\.getAttackTimer\(\)', '0.0'),
            (r'\w+\.getStillAni\(\)', '0'),
            (r'\w+\.getFlyingState\(\)', '0'),
            (r'\w+\.getFloorTimer\(\)', '0.0'),
            (r'\w+\.shakingC\(\)', '0'),
            (r'\w+\.getCloneC\(\)', '0'),
            (r'\w+\.showC\(\)', '1'),
            (r'\w+\.vomit', '0'),
            (r'\w+\.raining', '0'),
            (r'\w+\.getLeft\(\)', '0'),
            (r'\w+\.getRight\(\)', '0'),
            (r'\w+\.getHead\(\)', '0'),
            (r'\w+\.getParasiteStatus\(\)', '0'),
        ]
        
        for pattern, default in entity_defaults:
            py_expr = re.sub(pattern, default, py_expr)
        
        # Handle array access
        py_expr = re.sub(r'(\w+)\[(\w+|\d+)\]', '0', py_expr)
        
        # Handle remaining method calls on non-math objects
        def _replace_non_math_calls(match):
            prefix = match.group(1)
            if prefix == 'math':
                return match.group(0)
            return '0'
        
        py_expr = re.sub(r'(\w+)\.\w+\([^)]*\)', _replace_non_math_calls, py_expr)
        
        # Handle remaining field references
        py_expr = re.sub(r'this\.\w+\.field_\d+\w*', '0', py_expr)
        
        try:
            eval_globals = {
                "math": math,
                "__builtins__": {"max": max, "min": min, "abs": abs},
            }
            result = eval(py_expr, eval_globals)
            return float(result)
        except Exception:
            return 0.0

    def _resolve_ternary(self, expr: str) -> str:
        """Resolve Java ternary operators to Python."""
        depth = 0
        question_pos = -1
        
        for i, ch in enumerate(expr):
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == '?' and depth == 0:
                question_pos = i
                break
        
        if question_pos == -1:
            return expr
        
        condition = expr[:question_pos].strip()
        rest = expr[question_pos + 1:]
        
        depth = 0
        colon_pos = -1
        for i, ch in enumerate(rest):
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == ':' and depth == 0:
                colon_pos = i
                break
        
        if colon_pos == -1:
            return expr
        
        true_expr = rest[:colon_pos].strip()
        false_expr = rest[colon_pos + 1:].strip()
        
        true_expr = self._resolve_ternary(true_expr)
        false_expr = self._resolve_ternary(false_expr)
        
        py_condition = condition.replace('&&', ' and ').replace('||', ' or ')
        py_condition = re.sub(r'!\s*(?!\s*=)', ' not ', py_condition)
        
        return f"(({true_expr}) if ({py_condition}) else ({false_expr}))"

    def _resolve_vars(self, expr: str, vars_def: Dict[str, str]) -> str:
        """Resolve all variable references in an expression."""
        resolved = expr
        for _ in range(10):
            changed = False
            for var_name, var_expr in vars_def.items():
                if re.search(r'\b' + re.escape(var_name) + r'\b', resolved):
                    resolved = re.sub(r'\b' + re.escape(var_name) + r'\b', f'({var_expr})', resolved)
                    changed = True
            if not changed:
                break
        return resolved

    # ========================================================================
    # Douglas-Peucker Simplification
    # ========================================================================

    def _douglas_peucker_simplify(self, keyframes: List[dict], threshold: float) -> List[dict]:
        """Simplify keyframes using Douglas-Peucker algorithm."""
        if len(keyframes) <= 2:
            return keyframes
        
        axes = ['x', 'y', 'z']
        kept_indices = set()
        
        for axis in axes:
            if axis not in keyframes[0]:
                continue
            points = [(kf['time'], kf.get(axis, 0.0)) for kf in keyframes]
            indices = self._dp_axis(points, threshold)
            kept_indices.update(indices)
        
        kept_indices.add(0)
        kept_indices.add(len(keyframes) - 1)
        
        return [keyframes[i] for i in sorted(kept_indices)]

    def _dp_axis(self, points: List[Tuple[float, float]], threshold: float) -> List[int]:
        """Douglas-Peucker for a single axis."""
        if len(points) <= 2:
            return [0, len(points) - 1]
        
        start = points[0]
        end = points[-1]
        
        max_dist = 0
        max_idx = 0
        
        for i in range(1, len(points) - 1):
            dist = self._point_line_distance(points[i], start, end)
            if dist > max_dist:
                max_dist = dist
                max_idx = i
        
        if max_dist > threshold:
            left = self._dp_axis(points[:max_idx + 1], threshold)
            right = self._dp_axis(points[max_idx:], threshold)
            # Offset right indices by max_idx (the start position of the right subarray)
            right_offset = [r + max_idx for r in right]
            return left[:-1] + right_offset
        else:
            return [0, len(points) - 1]

    @staticmethod
    def _point_line_distance(point, line_start, line_end):
        """Calculate perpendicular distance from a point to a line."""
        x0, y0 = point
        x1, y1 = line_start
        x2, y2 = line_end
        
        dx = x2 - x1
        dy = y2 - y1
        
        if dx == 0 and dy == 0:
            return math.sqrt((x0 - x1) ** 2 + (y0 - y1) ** 2)
        
        return abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / math.sqrt(dx ** 2 + dy ** 2)

    # ========================================================================
    # Animation JSON Building
    # ========================================================================

    def _build_animation_json(self, states: List[AnimationState], model_name: str) -> dict:
        """Build the final GeckoLib animation JSON structure.
        
        KEY DESIGN DECISIONS:
        1. All walk animations are MERGED into a single shared "walk" animation.
           In GeckoLib, walk animations are blended with idle animations at runtime,
           so having one unified walk animation avoids duplication and saves memory.
        2. State-specific idle/ambient animations are kept separate (idle, evolved, etc.)
           since they represent different visual states that are activated conditionally.
        3. Animation names follow GeckoLib convention: animation.modelName.stateName
        """
        animations = {}
        
        # Phase 1: Collect all walk bones from all states that have walk components
        # Merge them into a single unified walk animation
        all_walk_assignments = []
        all_walk_vars = {}
        walk_bones_seen = set()  # Track (bone_var, channel, axis) to avoid duplicates
        
        for state in states:
            if not state.is_walk:
                continue
            
            for assignment in state.bone_assignments:
                full_expr = self._resolve_vars(assignment.expression, state.vars_def)
                if 'limbSwing' not in full_expr:
                    continue
                
                key = (assignment.bone_var, assignment.channel, assignment.axis)
                if key not in walk_bones_seen:
                    walk_bones_seen.add(key)
                    all_walk_assignments.append(assignment)
            
            # Merge vars from all walk states
            for var_name, var_expr in state.vars_def.items():
                if var_name not in all_walk_vars:
                    all_walk_vars[var_name] = var_expr
        
        # Create unified walk animation if we have walk bones
        if all_walk_assignments:
            walk_state = AnimationState(
                name='walk',
                condition_desc='unified walk from all states',
            )
            walk_state.bone_assignments = all_walk_assignments
            walk_state.vars_def = all_walk_vars
            walk_state.is_walk = True
            walk_state.is_idle = False
            
            bones_data = self._sample_animation(walk_state, is_walk=True)
            if bones_data:
                animations[f"animation.{model_name}.walk"] = {
                    "loop": "loop",
                    "animation_length": self._calculate_animation_length(bones_data),
                    "bones": bones_data,
                }
        
        # Phase 2: Create state-specific idle/ambient animations
        # Only include ageInTicks-driven bones (NOT limbSwing-driven walk bones)
        for state in states:
            if not state.is_idle:
                continue
            
            # Filter to only non-walk (ageInTicks-only) bones for idle animations
            idle_state = self._filter_idle_bones(state)
            
            if idle_state.bone_assignments:
                # Determine animation name based on state
                base_name = state.name
                # Clean up naming: remove redundant suffixes
                clean_name = base_name
                if clean_name.endswith('_walk'):
                    clean_name = clean_name[:-5]  # Remove _walk suffix
                
                # Map common state names to standard animation names
                anim_name_suffix = clean_name if clean_name else 'idle'
                
                anim_name = f"animation.{model_name}.{anim_name_suffix}"
                bones_data = self._sample_animation(idle_state, is_walk=False)
                if bones_data:
                    # Don't overwrite if already exists (dedup)
                    if anim_name not in animations:
                        animations[anim_name] = {
                            "loop": "loop",
                            "animation_length": self._calculate_animation_length(bones_data),
                            "bones": bones_data,
                        }
                    else:
                        # Merge bones into existing animation (different states may
                        # animate different bones in idle)
                        existing_bones = animations[anim_name].get("bones", {})
                        for bone_name, channels in bones_data.items():
                            if bone_name not in existing_bones:
                                existing_bones[bone_name] = channels
                        # Update animation_length if needed
                        new_length = self._calculate_animation_length(bones_data)
                        if new_length > animations[anim_name].get("animation_length", 0):
                            animations[anim_name]["animation_length"] = new_length
        
        # Phase 3: Handle states that are neither walk nor idle (rare edge cases)
        for state in states:
            if state.is_walk or state.is_idle:
                continue
            
            # This state has neither limbSwing nor ageInTicks - likely a static pose
            # Create it as a simple animation
            bones_data = self._sample_animation(state, is_walk=False)
            if bones_data:
                anim_name = f"animation.{model_name}.{state.name}"
                if anim_name not in animations:
                    animations[anim_name] = {
                        "loop": "loop",
                        "animation_length": self._calculate_animation_length(bones_data),
                        "bones": bones_data,
                    }
        
        if not animations:
            return None
        
        return {
            "format_version": "1.8.0",
            "animations": animations,
        }

    def _filter_walk_bones(self, state: AnimationState) -> AnimationState:
        """Create a new state containing only limbSwing-driven bones."""
        walk_state = AnimationState(
            name=state.name,
            condition_desc=state.condition_desc,
            vars_def=state.vars_def.copy(),
        )
        
        for assignment in state.bone_assignments:
            full_expr = self._resolve_vars(assignment.expression, state.vars_def)
            if 'limbSwing' in full_expr:
                walk_state.bone_assignments.append(assignment)
        
        walk_state.is_walk = True
        walk_state.is_idle = False
        return walk_state

    def _filter_idle_bones(self, state: AnimationState) -> AnimationState:
        """Create a new state containing only ageInTicks-driven bones."""
        idle_state = AnimationState(
            name=state.name,
            condition_desc=state.condition_desc,
            vars_def=state.vars_def.copy(),
        )
        
        for assignment in state.bone_assignments:
            full_expr = self._resolve_vars(assignment.expression, state.vars_def)
            if 'ageInTicks' in full_expr and 'limbSwing' not in full_expr:
                idle_state.bone_assignments.append(assignment)
        
        idle_state.is_walk = False
        idle_state.is_idle = True
        return idle_state

    def _calculate_animation_length(self, bones_data: dict) -> float:
        """Calculate the total animation length from all keyframes."""
        max_time = 0.0
        for bone_name, channels in bones_data.items():
            for channel, axes in channels.items():
                for axis, keyframes in axes.items():
                    for time_str in keyframes.keys():
                        t = float(time_str)
                        if t > max_time:
                            max_time = t
        return round(max_time, 4)

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def _extract_status_values(self, condition: str, status_var: str) -> List[int]:
        """Extract status values from a condition expression."""
        values = []
        for match in re.finditer(re.escape(status_var) + r'\s*(==|>=|<=|>|<|!=)\s*(\d+)', condition):
            op = match.group(1)
            val = int(match.group(2))
            if op == '==':
                values.append(val)
            elif op == '>=':
                values.extend(range(val, val + 5))
            elif op == '<=':
                values.extend(range(max(0, val - 4), val + 1))
            elif op == '>':
                values.extend(range(val + 1, val + 5))
            elif op == '<':
                values.extend(range(0, val))
            elif op == '!=':
                values.extend([v for v in range(5) if v != val])
        return values


# ============================================================================
# Convenience Function
# ============================================================================

def extract_animations(java_source: str, model_name: str, bone_mapping: Dict[str, str] = None) -> Optional[dict]:
    """Convenience function to extract animations from a Java model source."""
    extractor = AnimationExtractor(bone_mapping)
    return extractor.extract(java_source, model_name)
