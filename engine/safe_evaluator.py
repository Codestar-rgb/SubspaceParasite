#!/usr/bin/env python3
"""
Safe Expression Evaluator (v6.8)
================================
A secure AST-based evaluator for Java trig expressions, replacing the
unsafe `eval()` in java_trig_simulator.py.

WHY THIS EXISTS:
  The previous implementation used `eval(py_expr, safe_globals, dict(env))`
  with `__builtins__: {}`. While this blocks most builtins, `eval` on
  arbitrary strings is inherently risky — a crafted expression could
  potentially escape via attribute access on allowed objects (e.g.
  `().__class__.__bases__[0].__subclasses__()`).

  This module parses the expression into a Python AST and walks it,
  rejecting any node type that isn't explicitly allowed. Only:
    - Numbers (int, float)
    - Names (variable lookup from env)
    - Binary ops (+, -, *, /, %, **)
    - Unary ops (-, +)
    - Function calls (only to whitelisted math functions)
    - Parenthesized expressions

  This is provably safe: no attribute access, no subscripting, no
  comprehensions, no lambda, no imports — just arithmetic + math calls.

USAGE:
  from engine.safe_evaluator import safe_eval
  result = safe_eval("0.2 * __sin(ageInTicks * 0.08) * 0.73", {"ageInTicks": 1.5})
"""

from __future__ import annotations

import ast
import math
import re
from typing import Dict, Any


# Whitelisted functions that can be called in expressions.
# These map function names (after Java→Python translation) to callables.
SAFE_FUNCTIONS: Dict[str, Any] = {
    "__sin": math.sin,
    "__cos": math.cos,
    "__sqrt": math.sqrt,
    "__abs": abs,
    "__clamp": lambda v, lo, hi: max(lo, min(hi, v)),
    "__floor": math.floor,
    # Also allow bare math function names (in case translation is partial)
    "sin": math.sin,
    "cos": math.cos,
    "sqrt": math.sqrt,
    "abs": abs,
    "floor": math.floor,
    "min": min,
    "max": max,
    "pow": pow,
}

# Whitelisted binary operators
_SAFE_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b if b != 0 else 0.0,
    ast.Mod: lambda a, b: a % b if b != 0 else 0.0,
    ast.Pow: lambda a, b: a ** b,
}

# Whitelisted unary operators
_SAFE_UNARYOPS = {
    ast.UAdd: lambda a: +a,
    ast.USub: lambda a: -a,
}


class SafeEvalError(Exception):
    """Raised when an expression contains a disallowed AST node."""
    pass


def _eval_node(node: ast.AST, env: Dict[str, float]) -> float:
    """Recursively evaluate an AST node.

    Raises SafeEvalError if the node type is not whitelisted.
    """
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, env)

    if isinstance(node, ast.Constant):
        # Python 3.8+: numbers and strings are ast.Constant
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise SafeEvalError(f"Disallowed constant: {node.value!r}")

    if isinstance(node, ast.Num):
        # Python 3.7 compat (deprecated but may appear)
        return float(node.n)

    if isinstance(node, ast.Name):
        # Variable lookup from env
        name = node.id
        if name in env:
            val = env[name]
            return float(val) if not isinstance(val, bool) else (1.0 if val else 0.0)
        if name in ("PI", "Math_PI"):
            return math.pi
        if name == "E":
            return math.e
        if name in ("true", "True"):
            return 1.0
        if name in ("false", "False"):
            return 0.0
        # Unknown variable — return 0 rather than failing (robustness)
        return 0.0

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _SAFE_BINOPS:
            raise SafeEvalError(f"Disallowed binary op: {op_type.__name__}")
        left = _eval_node(node.left, env)
        right = _eval_node(node.right, env)
        return _SAFE_BINOPS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _SAFE_UNARYOPS:
            raise SafeEvalError(f"Disallowed unary op: {op_type.__name__}")
        operand = _eval_node(node.operand, env)
        return _SAFE_UNARYOPS[op_type](operand)

    if isinstance(node, ast.Call):
        # Only allow calls to whitelisted functions
        if not isinstance(node.func, ast.Name):
            raise SafeEvalError("Only direct function calls are allowed")
        func_name = node.func.id
        if func_name not in SAFE_FUNCTIONS:
            raise SafeEvalError(f"Disallowed function: {func_name}")
        # Evaluate all arguments
        args = [_eval_node(arg, env) for arg in node.args]
        # Reject keyword arguments
        if node.keywords:
            raise SafeEvalError("Keyword arguments not allowed")
        try:
            return float(SAFE_FUNCTIONS[func_name](*args))
        except (TypeError, ValueError, OverflowError) as e:
            raise SafeEvalError(f"Function {func_name} error: {e}")

    # Explicitly disallow dangerous node types
    if isinstance(node, (ast.Attribute, ast.Subscript, ast.Index, ast.Slice)):
        raise SafeEvalError(f"Disallowed node (attribute/subscript): {type(node).__name__}")
    if isinstance(node, (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
        raise SafeEvalError(f"Disallowed node (comprehension/lambda): {type(node).__name__}")
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        raise SafeEvalError("Import statements not allowed")
    if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
        raise SafeEvalError("Assignment not allowed (use env for variables)")
    if isinstance(node, ast.IfExp):
        # Ternary — allow but evaluate condition as truthy
        test = _eval_node(node.test, env)
        return _eval_node(node.body if test else node.orelse, env)

    raise SafeEvalError(f"Disallowed AST node: {type(node).__name__}")


def safe_eval(expr: str, env: Dict[str, float]) -> float:
    """Safely evaluate a math expression to a float.

    Uses Python's ast module to parse and walk the expression tree,
    rejecting any node type that isn't explicitly whitelisted.

    Args:
        expr: A Python-syntax math expression (after Java→Python translation).
              e.g. "0.2 * __sin(ageInTicks * 0.08) * 0.73"
        env: Dict mapping variable names to numeric values.

    Returns:
        The evaluated float value, or 0.0 if evaluation fails.
    """
    if not expr or not expr.strip():
        return 0.0
    try:
        tree = ast.parse(expr.strip(), mode="eval")
        return float(_eval_node(tree, env))
    except SafeEvalError:
        return 0.0
    except SyntaxError:
        return 0.0
    except Exception:
        return 0.0


def translate_java_to_python(expr: str) -> str:
    """Translate a Java trig expression to Python syntax.

    This is the same translation previously done inline in _safe_eval,
    now factored out for reuse and testing.
    """
    # Handle chained assignments: "f2 = 0.9f * ..." → take last segment
    if "=" in expr and not any(op in expr for op in ("==", "!=", "<=", ">=", "<", ">")):
        parts = expr.rsplit("=", 1)
        if len(parts) == 2 and parts[0].strip().isidentifier():
            expr = parts[1].strip()

    py_expr = expr
    # Replace MathHelper SRG names with safe function names
    py_expr = py_expr.replace("MathHelper.func_76126_a", "__sin")
    py_expr = py_expr.replace("MathHelper.func_76134_d", "__cos")
    py_expr = py_expr.replace("MathHelper.func_76134_b", "__cos")
    py_expr = py_expr.replace("MathHelper.func_76133_a", "__sqrt")
    py_expr = py_expr.replace("MathHelper.func_76132_a", "__abs")
    py_expr = py_expr.replace("MathHelper.func_76130_b", "__clamp")
    py_expr = py_expr.replace("MathHelper.func_76131_a", "__floor")
    # Remove Java float suffix and casts
    py_expr = re.sub(r"(\d+(?:\.\d+)?)f", r"\1", py_expr)
    py_expr = py_expr.replace("(float)", "").replace("(int)", "")
    py_expr = py_expr.replace("(double)", "")
    # PI / E constants
    py_expr = py_expr.replace("Math.PI", str(math.pi))
    py_expr = py_expr.replace("MathHelper.PI", str(math.pi))
    py_expr = re.sub(r"\bPI\b(?!\w)", str(math.pi), py_expr)
    # Remove 'L' long suffix
    py_expr = re.sub(r"(\d+)L\b", r"\1", py_expr)
    return py_expr


def safe_eval_java(expr: str, env: Dict[str, float]) -> float:
    """Translate a Java expression to Python and safely evaluate it.

    Convenience function combining translate_java_to_python + safe_eval.
    """
    py_expr = translate_java_to_python(expr)
    return safe_eval(py_expr, env)


if __name__ == "__main__":
    # Self-test
    test_cases = [
        ("0.2 * __sin(ageInTicks * 0.08) * 0.73", {"ageInTicks": 1.5}),
        ("1.5 * __cos(limbSwing * 0.42 + 1.0) - 0.8", {"limbSwing": 2.0}),
        ("-1.7f", {}),
        ("0.2f * MathHelper.func_76126_a((float)(ageInTicks * 0.08f)) * 0.73f", {"ageInTicks": 1.5}),
        ("f1", {"f1": 0.5}),
        ("1 + 2 * 3", {}),
        ("__sin(0)", {}),
        ("__cos(3.141592653589793)", {}),
        # Security tests (should all return 0.0)
        ("().__class__", {}),
        ("__import__('os').system('echo bad')", {}),
        ("open('/etc/passwd').read()", {}),
    ]
    for expr, env in test_cases:
        try:
            py = translate_java_to_python(expr)
            result = safe_eval(py, env)
            print(f"  {expr[:50]:50s} -> {result:.6f}")
        except Exception as e:
            print(f"  {expr[:50]:50s} -> ERROR: {e}")
