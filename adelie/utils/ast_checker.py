"""
adelie/utils/ast_checker.py

Python AST-based static analysis for the Policy Engine.

Provides structural code checks that are more precise than regex:
  - disallow_calls: Detect forbidden function calls (eval, exec, etc.)
  - disallow_import_star: Detect `from X import *`
  - require_docstrings: Check for missing docstrings on public functions/classes

Uses Python's built-in `ast` module — zero external dependencies.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ASTViolation:
    """A violation found during AST analysis."""
    file: str
    line: int
    message: str
    matched_text: str


def run_ast_check(
    content: str,
    filepath: str,
    check_type: str,
    rule_id: str,
    rule_name: str,
    severity: str,
    message: str,
    autofix_hint: str = "",
    target_calls: list[str] | None = None,
    scope: str = "",
) -> list:
    """
    Run an AST-based check on Python source code.

    Args:
        content: Python source code
        filepath: File path for error reporting
        check_type: "disallow_calls" | "disallow_import_star" | "require_docstrings"
        rule_id: Policy rule ID
        rule_name: Policy rule name
        severity: "block" | "warn" | "info"
        message: Violation message
        autofix_hint: Fix suggestion
        target_calls: For disallow_calls — list of forbidden function names
        scope: For require_docstrings — "public_functions" | "all_functions" | "classes"

    Returns:
        list of PolicyViolation (imported from policy_engine to avoid circular deps)
    """
    from adelie.policy_engine import PolicyViolation

    try:
        tree = ast.parse(content, filename=filepath)
    except SyntaxError:
        # Can't parse — skip AST checks (py_compile will catch syntax errors)
        return []

    violations: list[PolicyViolation] = []

    if check_type == "disallow_calls":
        raw = _check_disallow_calls(tree, target_calls or [], filepath)
    elif check_type == "disallow_import_star":
        raw = _check_disallow_import_star(tree, filepath)
    elif check_type == "require_docstrings":
        raw = _check_require_docstrings(tree, filepath, scope or "public_functions")
    else:
        return []

    for v in raw:
        violations.append(PolicyViolation(
            rule_id=rule_id,
            rule_name=rule_name,
            file=filepath,
            line=v.line,
            severity=severity,
            message=v.message or message,
            matched_text=v.matched_text,
            autofix_hint=autofix_hint,
        ))

    return violations


# ── Check: Disallow Calls ────────────────────────────────────────────────────


def _check_disallow_calls(
    tree: ast.Module,
    target_calls: list[str],
    filepath: str,
) -> list[ASTViolation]:
    """
    Detect forbidden function calls like eval(), exec(), compile().

    Matches both direct calls: eval(...)
    and attribute calls: builtins.eval(...)
    """
    violations: list[ASTViolation] = []
    target_set = set(target_calls)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_call_name(node)
            if func_name in target_set:
                violations.append(ASTViolation(
                    file=filepath,
                    line=node.lineno,
                    message=f"Forbidden call: {func_name}()",
                    matched_text=f"{func_name}()",
                ))

    return violations


def _get_call_name(node: ast.Call) -> str:
    """Extract function name from a Call node."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    elif isinstance(func, ast.Attribute):
        return func.attr
    return ""


# ── Check: Disallow Import Star ──────────────────────────────────────────────


def _check_disallow_import_star(
    tree: ast.Module,
    filepath: str,
) -> list[ASTViolation]:
    """Detect `from X import *` statements."""
    violations: list[ASTViolation] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.names and any(alias.name == "*" for alias in node.names):
                module = node.module or ""
                violations.append(ASTViolation(
                    file=filepath,
                    line=node.lineno,
                    message=f"Wildcard import: from {module} import *",
                    matched_text=f"from {module} import *",
                ))

    return violations


# ── Check: Require Docstrings ────────────────────────────────────────────────


def _check_require_docstrings(
    tree: ast.Module,
    filepath: str,
    scope: str,
) -> list[ASTViolation]:
    """
    Check for missing docstrings.

    Scope:
      "public_functions" — Only functions not starting with _
      "all_functions"    — All function definitions
      "classes"          — Class definitions
    """
    violations: list[ASTViolation] = []

    for node in ast.walk(tree):
        target = False
        name = ""

        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            name = node.name
            if scope == "public_functions" and name.startswith("_"):
                continue
            if scope in ("public_functions", "all_functions"):
                target = True

        elif isinstance(node, ast.ClassDef):
            name = node.name
            if scope == "classes":
                target = True
            # Also check classes for public_functions scope
            if scope == "public_functions" and not name.startswith("_"):
                target = True

        if target and not _has_docstring(node):
            node_type = "class" if isinstance(node, ast.ClassDef) else "function"
            violations.append(ASTViolation(
                file=filepath,
                line=node.lineno,
                message=f"Missing docstring: {node_type} '{name}'",
                matched_text=f"def {name}" if node_type == "function" else f"class {name}",
            ))

    return violations


def _has_docstring(node: ast.AST) -> bool:
    """Check if a function/class node has a docstring."""
    if not hasattr(node, "body") or not node.body:
        return False
    first = node.body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
        return isinstance(first.value.value, str)
    return False
