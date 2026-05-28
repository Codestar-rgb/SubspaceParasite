#!/usr/bin/env python3
"""
Abomination Animation Converter - High-Precision Edition
========================================================
Specialized converter for abomination-class models (ModelAboHead, ModelAboBodies)
that extracts and converts all animations with maximum precision.

Key improvements over the generic extractor:
  1. Handles compound assignments: this.bone.field = f1 = MathHelper.sin(...)
  2. No bone count limit (abominations have 50+ animated bones)
  3. Higher sampling density (240 samples) for smoother curves
  4. Tighter Douglas-Peucker threshold (0.08°) for more keyframe detail
  5. Proper state naming: idle_walk, evolved_walk, attack_walk, tentacles_idle
  6. Full support for GS/GD intermediate variables
  7. Correct handling of (float)(expr) casts in decompiled code
  8. Separate "idle_ambient" animation for the ageInTicks-driven tentacle/body parts
"""

import json
import math
import os
import re
import sys
import traceback
from typing import Dict, List, Optional, Tuple, Any

# Ensure converter directory is in path
CONVERTER_DIR = os.path.dirname(os.path.abspath(__file__))
if CONVERTER_DIR not in sys.path:
    sys.path.insert(0, CONVERTER_DIR)

from model_converter import ModelConverter
from bbmodel_generator import BBModelGenerator


# ============================================================================
# SRG Field Mappings
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

STATUS_NAMES = {
    0: 'idle',
    1: 'evolved',
    2: 'attack',
    3: 'death',
}


# ============================================================================
# Abomination Animation Extractor
# ============================================================================

class AbominationAnimExtractor:
    """
    High-precision animation extractor specifically for abomination models.
    Handles the full complexity of these models including:
      - getParasiteStatus() state machine with idle/evolved/attack states
      - getStillAni() sub-conditions splitting walk vs idle
      - Compound f1 = MathHelper.sin(...) assignments
      - swingX/Y/Z with 6/8 arg overloads (offset + weight variants)
      - moveY position helpers
      - ageInTicks-driven ambient animations (tentacles, body swaying)
    """

    def __init__(self, bone_mapping: Dict[str, str]):
        self.bone_mapping = bone_mapping
        self.warnings: List[str] = []

    def extract(self, java_source: str, model_name: str) -> Optional[dict]:
        """Extract all animations from an abomination model source file."""
        self.warnings = []

        method_body = self._find_method_body(java_source)
        if not method_body:
            self.warnings.append("No setRotationAngles method found")
            return None

        # Parse into animation states
        states = self._parse_abomination_states(method_body, model_name)
        if not states:
            self.warnings.append("No animation states found")
            return None

        # Build animation JSON with high-precision sampling
        animation_json = self._build_animation_json(states, model_name)
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
        """Extract content between matching braces."""
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

    # ========================================================================
    # Abomination-Specific State Parsing
    # ========================================================================

    def _parse_abomination_states(self, method_body: str, model_name: str) -> List[dict]:
        """
        Parse abomination model animation states.

        Abomination models follow a consistent pattern:
          1. Reset assignments (all bones set to 0)
          2. byte i = parasite.getParasiteStatus();
          3. if (i == 0) { if (!parasite.getStillAni()) { walk code } }
          4. else if (i == 1) { ... }
          5. else if (i == 2) { ... }
          6. Trailing code: ageInTicks-driven ambient animations

        Returns list of state dicts with:
          - name: animation name
          - bone_exprs: {bone_name: {channel: {axis: expression}}}
          - vars_def: {var_name: expression}
          - is_walk: bool
          - loop: "loop" or "hold_on_last_frame"
        """
        states = []

        # Find status variable
        status_match = re.search(r'byte\s+(\w+)\s*=\s*\w+\.getParasiteStatus\(\)', method_body)
        if not status_match:
            self.warnings.append("No getParasiteStatus() found - trying default extraction")
            return self._parse_generic_states(method_body, model_name)

        status_var = status_match.group(1)

        # Extract the status-based if/else chain
        # We need to find: if (i == N) { ... } else if (i == M) { ... } else ...
        # and for each, potentially: if (!parasite.getStillAni()) { walk code }

        blocks = self._extract_status_blocks(method_body, status_var)

        # First pass: collect outer-block variables (GS/GD etc.) from each status block
        # These are defined BEFORE the stillAni check and are needed by walk code
        outer_vars_by_status: Dict[int, Dict[str, str]] = {}

        for block in blocks:
            status_val = block['status_value']
            body = block['body']

            # Check for stillAni sub-condition
            still_match = re.search(
                r'if\s*\(\s*!\s*\w+\.getStillAni\(\)\s*\)\s*\{', body
            )

            if still_match:
                # Variables defined in the outer block (before stillAni) include GS/GD
                outer_body = body[:still_match.start()]
                outer_vars = self._parse_vars(outer_body)
                outer_vars_by_status[status_val] = outer_vars

        # Second pass: parse each status block with inherited outer vars
        walk_state = None  # We merge all walk animations into one

        for block in blocks:
            status_val = block['status_value']
            body = block['body']
            state_name = STATUS_NAMES.get(status_val, f'stage{status_val}')

            # Check for stillAni sub-condition
            still_match = re.search(
                r'if\s*\(\s*!\s*\w+\.getStillAni\(\)\s*\)\s*\{', body
            )

            if still_match:
                # Split into walk and idle parts
                walk_body = self._extract_brace_block(body, still_match.end() - 1)

                if walk_body:
                    # Walk animation (when moving)
                    # CRITICAL: Merge outer block variables (GS/GD) into walk vars
                    # These are set before the stillAni check and used in swing calls
                    walk_vars = self._parse_vars(walk_body)
                    outer_vars = outer_vars_by_status.get(status_val, {})
                    # Outer vars take lower priority - only add if not in walk_vars
                    for var_name, var_expr in outer_vars.items():
                        if var_name not in walk_vars:
                            walk_vars[var_name] = var_expr

                    walk_assigns = self._extract_all_assignments(walk_body, walk_vars)
                    if walk_assigns:
                        # Merge all walk states into a single "walk" animation
                        # Use the first (idle/normal) state's walk as the base
                        if walk_state is None:
                            walk_state = {
                                'name': 'walk',
                                'bone_exprs': walk_assigns,
                                'vars_def': walk_vars,
                                'is_walk': True,
                                'loop': 'loop',
                            }
                        # If we already have a walk state, skip duplicates
                        # (user wants ONE walk animation, not three identical ones)

                # Idle part: code before/after the stillAni block
                idle_body = body[:still_match.start()]
                if walk_body:
                    after_pos = still_match.end() - 1 + len(walk_body) + 1
                    idle_body += body[after_pos:]

                idle_vars = self._parse_vars(idle_body)
                idle_assigns = self._extract_all_assignments(idle_body, idle_vars)
                if idle_assigns:
                    states.append({
                        'name': state_name,
                        'bone_exprs': idle_assigns,
                        'vars_def': idle_vars,
                        'is_walk': False,
                        'loop': 'loop',
                    })
            else:
                # No stillAni split - entire block is one state
                block_vars = self._parse_vars(body)
                block_assigns = self._extract_all_assignments(body, block_vars)
                if block_assigns:
                    has_limb = any(
                        'limbSwing' in self._resolve_vars(expr, block_vars)
                        for bone_data in block_assigns.values()
                        for chan_data in bone_data.values()
                        for expr in chan_data.values()
                    )
                    if has_limb:
                        # Merge into single walk animation
                        if walk_state is None:
                            walk_state = {
                                'name': 'walk',
                                'bone_exprs': block_assigns,
                                'vars_def': block_vars,
                                'is_walk': True,
                                'loop': 'loop',
                            }
                    else:
                        states.append({
                            'name': state_name,
                            'bone_exprs': block_assigns,
                            'vars_def': block_vars,
                            'is_walk': False,
                            'loop': 'loop',
                        })

        # Add the merged walk animation (before other states)
        if walk_state is not None:
            states.insert(0, walk_state)

        # Extract trailing ageInTicks-driven code (ambient animations)
        trailing = self._extract_trailing_code(method_body, status_var, blocks)
        if trailing:
            trailing_vars = self._parse_vars(trailing)
            trailing_assigns = self._extract_all_assignments(trailing, trailing_vars)

            # Filter out reset assignments (value == 0.0)
            non_reset = {}
            for bone_name, channels in trailing_assigns.items():
                for channel, axes in channels.items():
                    for axis, expr in axes.items():
                        resolved = self._resolve_vars(expr, trailing_vars)
                        # Skip if it's just a literal 0
                        try:
                            val = self._quick_eval(resolved, 1.0, 0.0, 0.0, trailing_vars)
                            if abs(val) < 1e-10:
                                continue
                        except Exception:
                            pass
                        if bone_name not in non_reset:
                            non_reset[bone_name] = {}
                        if channel not in non_reset[bone_name]:
                            non_reset[bone_name][channel] = {}
                        non_reset[bone_name][channel][axis] = expr

            if non_reset:
                states.append({
                    'name': 'ambient',
                    'bone_exprs': non_reset,
                    'vars_def': trailing_vars,
                    'is_walk': False,
                    'loop': 'loop',
                })

        return states

    def _parse_generic_states(self, method_body: str, model_name: str) -> List[dict]:
        """Fallback: parse states when no getParasiteStatus is found."""
        vars_def = self._parse_vars(method_body)
        assigns = self._extract_all_assignments(method_body, vars_def)

        if not assigns:
            return []

        return [{
            'name': 'idle',
            'bone_exprs': assigns,
            'vars_def': vars_def,
            'is_walk': False,
            'loop': 'loop',
        }]

    # ========================================================================
    # Status Block Extraction
    # ========================================================================

    def _extract_status_blocks(self, method_body: str, status_var: str) -> List[dict]:
        """Extract all if/else if blocks for the status variable."""
        blocks = []

        # Find the start of the if chain
        # Pattern: if (i == 0) { ... } else if (i == 1) { ... } else if (i == 2 && ...) { ... }

        # Strategy: find the position after the status variable declaration
        status_decl = re.search(
            r'byte\s+' + re.escape(status_var) + r'\s*=\s*\w+\.getParasiteStatus\(\)\s*;',
            method_body
        )
        if not status_decl:
            return blocks

        search_start = status_decl.end()

        # Find all if/else if blocks with status_var in the condition
        pattern = re.compile(
            r'(?:if|else\s+if)\s*\(\s*' + re.escape(status_var) + r'\s*==\s*(\d+)'
        )

        pos = search_start
        while pos < len(method_body):
            match = pattern.search(method_body, pos)
            if not match:
                break

            status_val = int(match.group(1))

            # Find the opening brace of this if block
            brace_pos = method_body.find('{', match.end())
            if brace_pos == -1:
                break

            # Handle compound conditions like "i == 2 && !parasite.getStillAni()"
            # Find the closing parenthesis of the condition
            cond_start = match.start()
            cond_text = method_body[cond_start:brace_pos]

            body = self._extract_brace_block(method_body, brace_pos)
            if body is None:
                break

            blocks.append({
                'status_value': status_val,
                'body': body,
                'condition': cond_text.strip(),
            })

            pos = brace_pos + len(body) + 2

        return blocks

    def _extract_trailing_code(self, method_body: str, status_var: str,
                                blocks: List[dict]) -> Optional[str]:
        """Extract code after the last status if/else block."""
        if not blocks:
            return None

        # Find the end of the last block
        last_cond = blocks[-1].get('condition', '')
        last_pos = method_body.rfind(last_cond)
        if last_pos == -1:
            return None

        brace_pos = method_body.find('{', last_pos)
        if brace_pos == -1:
            return None

        body = self._extract_brace_block(method_body, brace_pos)
        if body is None:
            return None

        end_pos = brace_pos + len(body) + 2

        # Check for else blocks after
        remaining = method_body[end_pos:].lstrip()
        while remaining.startswith('else'):
            else_brace = remaining.find('{')
            if else_brace == -1:
                break
            # Need to find this in the original method_body
            else_pos = method_body.find('else', end_pos)
            if else_pos == -1:
                break
            else_brace_pos = method_body.find('{', else_pos)
            if else_brace_pos == -1:
                break
            else_body = self._extract_brace_block(method_body, else_brace_pos)
            if else_body is None:
                break
            end_pos = else_brace_pos + len(else_body) + 2
            remaining = method_body[end_pos:].lstrip()

        trailing = method_body[end_pos:].strip()

        # Filter out non-animation code
        lines = trailing.split('\n')
        anim_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith('super.'):
                continue
            anim_lines.append(line)

        return '\n'.join(anim_lines) if anim_lines else None

    # ========================================================================
    # Assignment Extraction - Enhanced for Abominations
    # ========================================================================

    def _extract_all_assignments(self, code: str, vars_def: Dict[str, str]) -> Dict[str, Dict[str, Dict[str, str]]]:
        """
        Extract all bone assignments from code.

        Returns: {bone_name: {channel: {axis: expression}}}
        where bone_name is the GeckoLib bone name from bone_mapping.
        """
        result: Dict[str, Dict[str, Dict[str, str]]] = {}
        swing_assigned = set()  # Track (bone_var, channel, axis) from swing calls

        # 1. Expand swingX/Y/Z calls FIRST
        swing_results = self._expand_swing_calls(code)
        for bone_var, channel, axis, expr in swing_results:
            bone_name = self.bone_mapping.get(bone_var, bone_var)
            key = (bone_var, channel, axis)
            swing_assigned.add(key)

            if bone_name not in result:
                result[bone_name] = {}
            if channel not in result[bone_name]:
                result[bone_name][channel] = {}
            result[bone_name][channel][axis] = expr

        # 2. Direct rotation assignments: this.bone.field_xxx = expr;
        # Also handles compound: this.bone.field_xxx = f1 = MathHelper.sin(...)
        rot_pattern = re.compile(
            r'this\.(\w+)\.(field_78795_f|field_78796_g|field_78808_h)\s*=\s*([^;]+);'
        )
        for match in rot_pattern.finditer(code):
            bone_var = match.group(1)
            field_name = match.group(2)
            expr = match.group(3).strip()

            if bone_var not in self.bone_mapping:
                continue

            axis = ROTATION_FIELDS[field_name]
            key = (bone_var, 'rotation', axis)

            # Skip if already covered by swingX/Y/Z
            if key in swing_assigned:
                continue

            # Handle compound: this.bone.field = f1 = MathHelper.sin(...)
            # This means: f1 is assigned AND bone.field = f1
            compound_match = re.match(r'(\w+)\s*=\s*(.+)', expr)
            if compound_match and compound_match.group(1) in vars_def:
                var_name = compound_match.group(1)
                actual_expr = compound_match.group(2).strip()
                # Update vars_def with the actual expression
                vars_def[var_name] = actual_expr
                # The bone rotation references this variable
                expr = var_name

            bone_name = self.bone_mapping[bone_var]

            if bone_name not in result:
                result[bone_name] = {}
            if 'rotation' not in result[bone_name]:
                result[bone_name]['rotation'] = {}
            result[bone_name]['rotation'][axis] = expr

        # 3. Position offset assignments
        pos_pattern = re.compile(
            r'this\.(\w+)\.(field_82906_o|field_82907_q|field_82908_p)\s*=\s*([^;]+);'
        )
        for match in pos_pattern.finditer(code):
            bone_var = match.group(1)
            field_name = match.group(2)
            expr = match.group(3).strip()

            if bone_var not in self.bone_mapping:
                continue

            # Skip reset assignments for trailing code
            if expr.strip() in ('0.0f', '0', '0.0', '0.0F'):
                # But keep non-zero assignments like -0.75f
                continue

            axis = POSITION_FIELDS[field_name]
            bone_name = self.bone_mapping[bone_var]

            if bone_name not in result:
                result[bone_name] = {}
            if 'position' not in result[bone_name]:
                result[bone_name]['position'] = {}
            result[bone_name]['position'][axis] = expr

        # 4. Expand moveY calls
        move_results = self._expand_move_y_calls(code)
        for bone_var, axis, expr in move_results:
            bone_name = self.bone_mapping.get(bone_var, bone_var)

            if bone_name not in result:
                result[bone_name] = {}
            if 'position' not in result[bone_name]:
                result[bone_name]['position'] = {}
            result[bone_name]['position'][axis] = expr

        return result

    # ========================================================================
    # Swing/MoveY Call Expansion
    # ========================================================================

    def _expand_swing_calls(self, code: str) -> List[Tuple[str, str, str, str]]:
        """
        Expand swingX/Y/Z calls to mathematical expressions.

        Returns list of (bone_var, channel, axis, expression) tuples.

        Overload 1 (6 args): swingX(bone, speed, degree, invert, limbSwing, limbSwingAmount)
          → invert * limbSwingAmount * degree * cos(limbSwing * speed) * limbSwingAmount

        Overload 2 (8 args): swingX(bone, speed, degree, invert, offset, weight, limbSwing, limbSwingAmount)
          → invert * limbSwingAmount * degree * cos(limbSwing * speed + offset) * limbSwingAmount + weight * limbSwingAmount
        """
        results = []

        for swing_method, axis in [('swingX', 'x'), ('swingY', 'y'), ('swingZ', 'z')]:
            call_pattern = re.compile(
                r'this\.' + swing_method + r'\s*\(([^)]+)\)'
            )

            for match in call_pattern.finditer(code):
                args_str = match.group(1)
                args = self._parse_method_args(args_str)

                if len(args) < 6:
                    continue

                first_arg = args[0].strip()

                if first_arg.startswith('this.'):
                    bone_var = first_arg.replace('this.', '').strip()

                    if bone_var not in self.bone_mapping:
                        continue

                    if len(args) == 6:
                        # Overload 1
                        speed = args[1].strip()
                        degree = args[2].strip()
                        invert = args[3].strip()
                        limbSwing = args[4].strip()
                        limbSwingAmount = args[5].strip()

                        expr = f'{invert} * {limbSwingAmount} * {degree} * MathHelper.cos({limbSwing} * {speed}) * {limbSwingAmount}'

                    elif len(args) == 8:
                        # Overload 2
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

                results.append((bone_var, 'rotation', axis, expr))

        return results

    def _expand_move_y_calls(self, code: str) -> List[Tuple[str, str, str]]:
        """
        Expand moveY calls to position offset expressions.
        moveY(bone, speed, invert, f, f1, distance)
          → invert * cos(f * speed) * f1 * distance
        """
        results = []

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
            results.append((bone_var, 'y', expr))

        return results

    def _parse_method_args(self, args_str: str) -> List[str]:
        """Parse method arguments, handling nested parentheses and casts."""
        args = []
        current = ''
        depth = 0

        for ch in args_str:
            if ch == '(':
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

    def _parse_vars(self, code: str) -> Dict[str, str]:
        """Parse intermediate variable definitions, including compound f1 = expr patterns."""
        vars_def = {}

        # Pattern 1: float f1 = MathHelper.sin(...) * 0.35f;
        var_pattern = re.compile(r'(?:float|double)\s+(\w+)\s*=\s*([^;]+);')

        for match in var_pattern.finditer(code):
            var_name = match.group(1)
            var_expr = match.group(2).strip()

            # Skip if expression contains bone field assignments
            if 'field_78795_f' in var_expr or 'field_78796_g' in var_expr or 'field_78808_h' in var_expr:
                continue

            # Skip keywords and entity method calls
            if var_name in ('this', 'if', 'else', 'for', 'while', 'return', 'byte',
                          'float', 'int', 'boolean', 'double', 'scaleFactor'):
                continue
            if var_expr.startswith('parasite.') or var_expr.startswith('entityIn.'):
                continue

            # Accept all variable names that look like intermediate vars
            # Be more permissive than the generic extractor
            vars_def[var_name] = var_expr

        # Pattern 1b: Bare variable assignments like GS = 0.65f; GD = 0.75f;
        # These are re-assignments of variables declared earlier (outside the block)
        # Common in abomination models where GS/GD are declared at method scope
        # and assigned different values in each state block.
        bare_var_pattern = re.compile(r'\b([A-Z][A-Z0-9]*)\s*=\s*([^;]+);')
        for match in bare_var_pattern.finditer(code):
            var_name = match.group(1)
            var_expr = match.group(2).strip()

            # Skip if expression contains bone field assignments
            if 'field_78795_f' in var_expr or 'field_78796_g' in var_expr or 'field_78808_h' in var_expr:
                continue

            # Only capture uppercase short variable names (GS, GD, etc.)
            # This avoids capturing bone assignments or other code
            if len(var_name) <= 4 and var_name.isupper():
                vars_def[var_name] = var_expr

        # Also capture f-prefixed bare assignments: f1 = expr;  (without float prefix)
        bare_f_pattern = re.compile(r'\b([fg]\d+)\s*=\s*([^;]+);')
        for match in bare_f_pattern.finditer(code):
            var_name = match.group(1)
            var_expr = match.group(2).strip()

            if 'field_78795_f' in var_expr or 'field_78796_g' in var_expr or 'field_78808_h' in var_expr:
                continue

            vars_def[var_name] = var_expr

        # Pattern 2: Compound assignments in the form this.bone.field = f1 = expr;
        # These set both f1 and the bone rotation
        compound_pattern = re.compile(
            r'this\.\w+\.(?:field_78795_f|field_78796_g|field_78808_h)\s*=\s*(\w+)\s*=\s*([^;]+);'
        )
        for match in compound_pattern.finditer(code):
            var_name = match.group(1)
            actual_expr = match.group(2).strip()
            # Store/update the variable definition
            vars_def[var_name] = actual_expr

        return vars_def

    # ========================================================================
    # Expression Evaluation
    # ========================================================================

    def _resolve_vars(self, expr: str, vars_def: Dict[str, str]) -> str:
        """Resolve all variable references in an expression."""
        resolved = expr
        for _ in range(10):
            changed = False
            for var_name, var_expr in vars_def.items():
                if re.search(r'\b' + re.escape(var_name) + r'\b', resolved):
                    resolved = re.sub(
                        r'\b' + re.escape(var_name) + r'\b',
                        f'({var_expr})',
                        resolved
                    )
                    changed = True
            if not changed:
                break
        return resolved

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
                    py_expr = re.sub(
                        r'\b' + re.escape(var_name) + r'\b',
                        f'({var_expr})',
                        py_expr
                    )
                    changed = True
            if not changed:
                break

        # Handle ternary operators
        py_expr = self._resolve_ternary(py_expr)

        # Replace MathHelper methods (SRG names first, then deobfuscated)
        replacements = [
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

        for pattern, replacement in replacements:
            py_expr = re.sub(pattern, replacement, py_expr)

        py_expr = py_expr.replace('Math.PI', str(math.pi))
        py_expr = py_expr.replace('PI', str(math.pi))

        # Replace Java float suffixes (but not inside variable names)
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
        def _replace_non_math_calls(m):
            prefix = m.group(1)
            if prefix == 'math':
                return m.group(0)
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

    def _quick_eval(self, expr: str, age_in_ticks: float, limb_swing: float,
                    limb_swing_amount: float, vars_def: Dict[str, str]) -> float:
        """Quick evaluation for checking if an expression is non-zero."""
        return self._evaluate_expression(expr, age_in_ticks, limb_swing, limb_swing_amount, vars_def)

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

    # ========================================================================
    # Numerical Sampling - High Precision
    # ========================================================================

    def _sample_animation(
        self,
        state: dict,
        sample_count: int = 240,
        dp_threshold: float = 0.08,
    ) -> dict:
        """
        Sample a single animation state numerically with high precision.

        Key timing corrections:
          - Walk animations: limbSwing is NOT in seconds. In MC 1.12.2, limbSwing
            increments by ~walk_speed*4.0 per tick. We map the period in limbSwing
            space to a target walk cycle duration.
            Vanilla MC walk cycle ≈ 0.6667s (40 ticks at 20 TPS).
            For mod entities with different swing speeds, we scale proportionally.
          - Ambient animations: ageInTicks is in ticks. 1 tick = 0.05s.
            We find the fundamental period that ALL frequency components share,
            ensuring smooth loop by sampling over exact integer multiples of all periods.

        Args:
            state: State dict from _parse_abomination_states
            sample_count: Number of samples (240 for smooth curves)
            dp_threshold: Douglas-Peucker threshold in degrees (0.08° for high precision)
        """
        bone_exprs = state['bone_exprs']
        vars_def = state.get('vars_def', {})
        is_walk = state.get('is_walk', False)

        # --- Timing constants ---
        TICKS_PER_SECOND = 20.0  # MC runs at 20 TPS

        if is_walk:
            # Find the dominant walk speed factor from swing expressions
            walk_speed = self._find_dominant_walk_speed(bone_exprs, vars_def)

            # Period in limbSwing space (one full cosine cycle)
            period_limbSwing = 2 * math.pi / walk_speed

            # Vanilla MC walk cycle = 40 ticks = 2.0s at 20 TPS
            # But the visual cycle (one full leg swing) is 0.6667s because
            # vanilla uses cos(limbSwing * 0.6662) with limbSwing incrementing
            # by ~4.0*distance/tick. At normal walk speed the period is ~40 ticks.
            # For GeckoLib, we target 0.6667s (vanilla standard) as the visual cycle.
            #
            # For SRP entities with different swing speeds, we scale proportionally:
            #   walk_cycle = vanilla_cycle * (vanilla_speed / detected_speed)
            #   where vanilla_speed ≈ 0.6662 (the vanilla cos coefficient)
            VANILLA_WALK_SPEED = 0.6662
            VANILLA_WALK_CYCLE = 0.6667  # seconds

            if walk_speed > 0:
                walk_cycle_seconds = VANILLA_WALK_CYCLE * (VANILLA_WALK_SPEED / walk_speed)
            else:
                walk_cycle_seconds = VANILLA_WALK_CYCLE

            # Clamp to reasonable range
            walk_cycle_seconds = max(0.4, min(walk_cycle_seconds, 2.0))

            # Scaling: limbSwing ranges from 0 to period_limbSwing over walk_cycle_seconds
            limb_swing_scale = period_limbSwing / walk_cycle_seconds

            # ageInTicks during walk: scales proportionally
            age_ratio = TICKS_PER_SECOND

            period_seconds = walk_cycle_seconds
        else:
            # Ambient animation: find the fundamental period that ensures
            # ALL frequency components complete whole cycles
            period_ticks = self._estimate_period_precise(bone_exprs, vars_def)

            # Convert period from ticks to seconds
            period_seconds = period_ticks / TICKS_PER_SECOND
            # Cap at a reasonable ambient duration (max ~5 seconds)
            period_seconds = min(period_seconds, 5.0)

            # Re-derive period_ticks from capped seconds
            period_ticks = period_seconds * TICKS_PER_SECOND

            age_ratio = 0
            limb_swing_scale = 0

        dt = period_seconds / sample_count
        bones_data = {}

        for bone_name, channels in bone_exprs.items():
            bone_anim = {}

            for channel, axis_exprs in channels.items():
                keyframes = []

                for i in range(sample_count + 1):
                    time_s = i * dt  # Time in seconds (for Blockbench keyframe)

                    if is_walk:
                        # Map real time to limbSwing value
                        limb_swing = time_s * limb_swing_scale
                        # Use limbSwingAmount that produces vanilla-like amplitude.
                        # Vanilla MC uses ~1.0 for the base cos coefficient, but
                        # SRP's swingX formula uses limbSwingAmount SQUARED, so:
                        #   amplitude = limbSwingAmount^2 * degree
                        # With 0.5: amplitude = 0.25 * degree (vanilla-like for large entities)
                        # With 0.7: amplitude = 0.49 * degree (too exaggerated)
                        # 0.5 produces ~±20° for typical SRP degree values, matching vanilla.
                        limb_swing_amount = 0.5
                        age_in_ticks = time_s * age_ratio
                    else:
                        # Map real time to ageInTicks value
                        limb_swing = 0.0
                        limb_swing_amount = 0.0
                        age_in_ticks = time_s * TICKS_PER_SECOND  # seconds → ticks

                    kf = {'time': time_s}

                    for axis, expr in axis_exprs.items():
                        try:
                            value = self._evaluate_expression(
                                expr, age_in_ticks, limb_swing, limb_swing_amount,
                                vars_def
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
                # Instead of hard-forcing last = first (which creates a snap),
                # we smoothly crossfade the last N samples toward the first frame's values.
                if keyframes and len(keyframes) > 2:
                    first = keyframes[0]
                    last = keyframes[-1]

                    # Check if last naturally matches first
                    max_diff = 0.0
                    for axis in ['x', 'y', 'z']:
                        if axis in first and axis in last:
                            max_diff = max(max_diff, abs(last[axis] - first[axis]))

                    if max_diff > 0.5:
                        # Significant mismatch - apply smooth crossfade over last 5% of samples
                        crossfade_count = max(2, len(keyframes) // 20)
                        for j in range(crossfade_count):
                            idx = len(keyframes) - crossfade_count + j
                            if idx < 0 or idx >= len(keyframes):
                                continue
                            # Alpha: 0 at start of crossfade, 1 at the last frame
                            alpha = (j + 1) / crossfade_count
                            # Smooth alpha with ease-in (cubic)
                            alpha = alpha * alpha * (3.0 - 2.0 * alpha)  # smoothstep
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
                # Use tighter threshold for walk animations (more detail needed)
                actual_threshold = dp_threshold * 0.5 if is_walk else dp_threshold
                simplified = self._douglas_peucker_simplify(keyframes, actual_threshold)

                # Build channel data
                channel_data = {}
                for axis in ['x', 'y', 'z']:
                    axis_keyframes = {}
                    for kf in simplified:
                        if axis in kf:
                            axis_keyframes[f"{kf['time']:.4f}"] = kf[axis]
                    if axis_keyframes:
                        channel_data[axis] = axis_keyframes

                if channel_data:
                    bone_anim[channel] = channel_data

            if bone_anim:
                bones_data[bone_name] = bone_anim

        return bones_data

    def _estimate_period(self, bone_exprs: dict, vars_def: Dict[str, str]) -> float:
        """Estimate the animation period from the expressions (simple version)."""
        min_freq = float('inf')

        for bone_name, channels in bone_exprs.items():
            for channel, axis_exprs in channels.items():
                for axis, expr in axis_exprs.items():
                    resolved = self._resolve_vars(expr, vars_def)
                    for freq_match in re.finditer(r'ageInTicks\s*\*\s*\(?\s*([\d.]+)', resolved):
                        try:
                            freq = float(freq_match.group(1))
                            if 0 < freq < min_freq:
                                min_freq = freq
                        except ValueError:
                            pass

        if min_freq == float('inf'):
            min_freq = 0.5

        period = 2 * math.pi / min_freq
        return period

    def _estimate_period_precise(self, bone_exprs: dict, vars_def: Dict[str, str]) -> float:
        """
        Estimate the animation period with high precision for smooth looping.

        Instead of just finding the minimum frequency, this method finds ALL
        frequency components and computes the shortest period that is an integer
        multiple of all individual periods. This ensures that ALL bones complete
        whole cycles within the animation length, producing a perfectly smooth loop.

        Strategy:
          1. Extract all frequency factors from ageInTicks * freq patterns
          2. Compute individual periods: T_i = 2π / freq_i
          3. Find the fundamental period T that is close to an integer multiple
             of each T_i (using a tolerance-based approach)
          4. This ensures all sine/cosine components return to their starting values
        """
        # Collect all frequency factors
        all_freqs = []

        for bone_name, channels in bone_exprs.items():
            for channel, axis_exprs in channels.items():
                for axis, expr in axis_exprs.items():
                    resolved = self._resolve_vars(expr, vars_def)
                    for freq_match in re.finditer(r'ageInTicks\s*\*\s*\(?\s*([\d.]+)', resolved):
                        try:
                            freq = float(freq_match.group(1))
                            if freq > 0:
                                all_freqs.append(freq)
                        except ValueError:
                            pass

        if not all_freqs:
            # Default: 2π / 0.5 ≈ 12.57 ticks ≈ 0.63 seconds
            return 2 * math.pi / 0.5

        # Find minimum frequency (determines the longest individual period)
        min_freq = min(all_freqs)
        base_period = 2 * math.pi / min_freq

        # Check if all frequencies are integer multiples of the minimum frequency.
        # If so, the base period is the fundamental period.
        # If not, we need to find a common period.
        #
        # For each frequency f_i, the ratio f_i / min_freq should be close to an integer.
        # If it's not, we need to extend the base period until all ratios become integers.
        #
        # Practical approach: find the fundamental period by checking the greatest
        # common divisor (GCD) of all frequency ratios.

        # Normalize frequencies relative to the minimum
        ratios = [f / min_freq for f in all_freqs]

        # Round ratios to reasonable precision (they should be near-integer
        # or simple fractions for typical animation patterns)
        TOLERANCE = 0.05  # 5% tolerance for ratio rounding

        # Try to find a base frequency that all frequencies are integer multiples of.
        # Start with the minimum frequency and check.
        def _find_fundamental_period(freqs, base_f):
            """Find the shortest period T where all frequencies complete whole cycles."""
            # Try T = base_period, 2*base_period, 3*base_period, ... up to 10x
            for multiplier in range(1, 11):
                candidate_period = base_period * multiplier
                all_integer = True
                for f in freqs:
                    # Number of cycles this frequency completes in candidate_period
                    cycles = f * candidate_period / (2 * math.pi)
                    # Check if close to an integer
                    nearest_int = round(cycles)
                    if abs(cycles - nearest_int) > TOLERANCE:
                        all_integer = False
                        break
                if all_integer:
                    return candidate_period
            # Fallback: use 2x base period for a reasonable approximation
            return base_period * 2

        fundamental_period = _find_fundamental_period(all_freqs, min_freq)

        return fundamental_period

    def _find_dominant_walk_speed(self, bone_exprs: dict, vars_def: Dict[str, str]) -> float:
        """
        Find the dominant walk speed factor from animation expressions.

        Walk animations use patterns like:
          MathHelper.cos(limbSwing * speed) where speed = 0.2 * GS (e.g., 0.42)

        The speed factor may be a compound expression like '0.2 * GS' that needs
        variable resolution and numerical evaluation.

        Strategy: Find "limbSwing * <expr>" inside cos() calls, extract <expr>,
        resolve variables, and evaluate numerically.

        Returns the dominant speed factor (default 0.6667 = vanilla MC walk speed).
        """
        speeds = []

        for bone_name, channels in bone_exprs.items():
            for channel, axis_exprs in channels.items():
                for axis, expr in axis_exprs.items():
                    resolved = self._resolve_vars(expr, vars_def)

                    # Find all occurrences of "limbSwing *" and extract the speed factor
                    pos = 0
                    while True:
                        idx = resolved.find('limbSwing', pos)
                        if idx == -1:
                            break

                        # Check if followed by *
                        after = resolved[idx + len('limbSwing'):].lstrip()
                        if after.startswith('*'):
                            # Extract the expression after the *
                            rest = after[1:].lstrip()
                            # Extract up to a + or - at depth 0
                            speed_expr = self._extract_balanced_factor(rest)
                            if speed_expr:
                                speed = self._eval_speed_expr(speed_expr)
                                if speed and 0 < speed < 10.0:
                                    speeds.append(speed)

                        pos = idx + 1

        if speeds:
            # Use the most common (median) speed as the dominant one
            speeds.sort()
            return speeds[len(speeds) // 2]

        # Fallback: vanilla MC default walk speed
        return 0.6667

    def _extract_balanced_factor(self, expr: str) -> Optional[str]:
        """
        Extract a balanced expression from the start of a string.
        Stops at a + or - at depth 0 (not inside parentheses).
        Returns the extracted substring, or None if empty.
        """
        depth = 0
        end = 0
        for i, ch in enumerate(expr):
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth < 0:
                    break
            elif ch in ('+', '-') and depth == 0 and i > 0:
                # Stop at + or - at depth 0 (but not at start)
                break
            end = i + 1

        result = expr[:end].strip()
        return result if result else None

    def _eval_speed_expr(self, speed_expr: str) -> Optional[float]:
        """Evaluate a speed expression string to a numeric value."""
        try:
            py_expr = speed_expr
            # Remove Java float suffixes
            py_expr = re.sub(r'(\d+(?:\.\d+)?)[fF](?!\w)', r'\1', py_expr)
            # Remove non-numeric function calls
            py_expr = re.sub(r'MathHelper\.\w+', '0', py_expr)
            py_expr = re.sub(r'math\.\w+', '0', py_expr)
            # Evaluate
            speed = float(eval(py_expr, {"__builtins__": {}}, {}))
            return speed
        except Exception:
            return None

    # ========================================================================
    # Douglas-Peucker Simplification
    # ========================================================================

    def _douglas_peucker_simplify(self, keyframes: list, threshold: float) -> list:
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

    def _dp_axis(self, points: list, threshold: float) -> list:
        """Douglas-Peucker for a single axis.

        Returns indices relative to the input points list.
        The recursive calls must offset right-subarray indices by the split position.
        """
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

    def _build_animation_json(self, states: List[dict], model_name: str) -> dict:
        """Build the final GeckoLib animation JSON structure."""
        animations = {}

        for state in states:
            anim_name = f"animation.{model_name}.{state['name']}"

            bones_data = self._sample_animation(state)
            if not bones_data:
                continue

            # Calculate animation length
            max_time = 0.0
            for bone_name, channels in bones_data.items():
                for channel, axis_data in channels.items():
                    for axis, keyframes in axis_data.items():
                        for t_str in keyframes:
                            t = float(t_str)
                            if t > max_time:
                                max_time = t

            animations[anim_name] = {
                "loop": state.get('loop', 'loop'),
                "animation_length": round(max_time, 4),
                "bones": bones_data,
            }

        if not animations:
            return None

        return {
            "format_version": "1.8.0",
            "animations": animations,
        }


# ============================================================================
# Main Conversion Pipeline
# ============================================================================

def find_texture(texture_dir: str, entity_name: str) -> Optional[str]:
    """Find texture file for an entity name."""
    if not texture_dir or not os.path.isdir(texture_dir):
        return None

    TEXTURE_MAP = {
        "aboBodies": "abobodies",
        "aboHead": "abohead",
    }

    tex_name = TEXTURE_MAP.get(entity_name, entity_name.lower())

    # Try direct match
    candidate = os.path.join(texture_dir, f"{tex_name}.png")
    if os.path.isfile(candidate):
        return candidate

    # Try lowercase
    candidate = os.path.join(texture_dir, f"{tex_name.lower()}.png")
    if os.path.isfile(candidate):
        return candidate

    # Fallback: partial match
    for f in os.listdir(texture_dir):
        if f.endswith('.png') and f.lower().startswith(tex_name.lower()):
            return os.path.join(texture_dir, f)

    return None


def convert_abomination_model(
    java_path: str,
    output_dir: str,
    output_name: str,
    texture_path: str = None,
    namespace: str = "srparasites",
) -> dict:
    """
    Convert a single abomination model to .bbmodel with high-precision animations.
    """
    try:
        # Read Java source
        with open(java_path, 'r', encoding='utf-8') as f:
            source = f.read()

        # Step 1: Convert geometry
        converter = ModelConverter()
        identifier = f"model.{output_name}"
        result = converter.convert(source, identifier)

        geo_json = result['geo_json']
        bone_mapping = result.get('bone_mapping', {})
        bones = geo_json['model']['bones']
        total_cubes = sum(len(b.get('cubes', [])) for b in bones)

        # Step 2: Extract animations with high-precision abomination extractor
        anim_json = None
        anim_count = 0
        try:
            extractor = AbominationAnimExtractor(bone_mapping)
            anim_json = extractor.extract(source, output_name)
            if anim_json and 'animations' in anim_json:
                anim_count = len(anim_json['animations'])
                print(f"    Animations extracted: {list(anim_json['animations'].keys())}")
            if extractor.warnings:
                for w in extractor.warnings:
                    print(f"    [ANIM WARN] {w}")
        except Exception as e:
            print(f"    [ANIM ERROR] {e}")
            traceback.print_exc()
            anim_json = None

        # Step 3: Generate .bbmodel
        bbgen = BBModelGenerator()
        bbmodel = bbgen.generate(
            geo_json,
            anim_json=anim_json,
            texture_path=texture_path,
            texture_name=output_name,
            namespace=namespace,
        )

        # Step 4: Save .bbmodel
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, f"{output_name}.bbmodel")
        bbgen.save(bbmodel, out_path)

        return {
            'success': True,
            'output_path': out_path,
            'stats': {
                'bones': len(bones),
                'cubes': total_cubes,
                'animations': anim_count,
            },
        }

    except Exception as e:
        return {
            'success': False,
            'error': f"{type(e).__name__}: {str(e)}",
            'traceback': traceback.format_exc(),
        }


def main():
    """Convert abomination models with high-precision animations."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert abomination models with high-precision animation extraction"
    )
    parser.add_argument(
        "--source", required=True,
        help="Path to the source repo's src/ directory"
    )
    parser.add_argument(
        "--output", required=True,
        help="Output directory for converted .bbmodel files"
    )
    parser.add_argument(
        "--textures",
        help="Path to the textures directory (entity/monster/)"
    )
    parser.add_argument(
        "--namespace", default="srparasites",
        help="Resource namespace (default: srparasites)"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("  Abomination Animation Converter - HIGH PRECISION")
    print("  MC 1.12.2 → .bbmodel with embedded animations")
    print("=" * 70)
    print()

    # Find abomination model files
    model_base = os.path.join(
        args.source, "main", "java", "com", "subspaceparasite",
        "client", "model", "entity", "abomination"
    )

    if not os.path.isdir(model_base):
        print(f"ERROR: Abomination model directory not found: {model_base}")
        sys.exit(1)

    models = []
    for fname in sorted(os.listdir(model_base)):
        if fname.startswith("Model") and fname.endswith(".java"):
            java_path = os.path.join(model_base, fname)
            # Derive output name
            class_name = fname.replace(".java", "")
            output_name = class_name[5:]  # Remove "Model"
            output_name = output_name[0].lower() + output_name[1:]  # Lowercase first letter
            models.append((java_path, output_name))

    print(f"Found {len(models)} abomination models:")
    for _, name in models:
        print(f"  - {name}")
    print()

    # Convert each model
    output_dir = os.path.join(args.output, "abomination")

    for i, (java_path, output_name) in enumerate(models, 1):
        print(f"[{i}/{len(models)}] Converting {output_name}...")

        tex_path = None
        if args.textures:
            tex_path = find_texture(args.textures, output_name)

        result = convert_abomination_model(
            java_path, output_dir, output_name,
            texture_path=tex_path,
            namespace=args.namespace,
        )

        if result['success']:
            stats = result['stats']
            print(f"  ✓ Success: {stats['bones']} bones, {stats['cubes']} cubes, "
                  f"{stats.get('animations', 0)} animations")
            print(f"  Output: {result['output_path']}")
        else:
            print(f"  ✗ Failed: {result['error']}")
            if 'traceback' in result:
                print(result['traceback'])

    print()
    print("=" * 70)
    print("  Abomination conversion complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
