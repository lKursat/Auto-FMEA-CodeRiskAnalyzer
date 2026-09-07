"""
python_parser.py — Python Source Code Parser
==============================================
Uses the built-in `ast` module to extract class and function information
from Python source files. Uses `radon` for cyclomatic complexity.

Returns a list of ClassInfo dicts compatible with the Auto-FMEA JSON schema.
"""

import ast
import os
import sys
from typing import Any, Dict, List, Optional

# Attempt to import radon; fall back to AST-based CC if unavailable.
try:
    from radon.complexity import cc_visit
    RADON_AVAILABLE = True
except ImportError:
    RADON_AVAILABLE = False


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

def _make_class_info(
    name: str,
    line_start: int,
    line_end: int,
    methods: List[str],
    imports: List[str],
    cyclomatic_complexity: int,
    has_public_api: bool,
    is_core_module: bool,
) -> Dict[str, Any]:
    """Return a class info dict with all fields needed by downstream modules."""
    return {
        "name": name,
        "line_start": line_start,
        "line_end": line_end,
        "methods": methods,
        "imports": imports,
        "cyclomatic_complexity": cyclomatic_complexity,
        "has_public_api": has_public_api,
        "is_core_module": is_core_module,
        "fan_in": 0,
        "fan_out": 0,
        "affected_classes": [],
        "test_file_found": False,
        "severity": 0,
        "occurrence": 0,
        "detection": 0,
        "rpn": 0,
        "risk_level": "LOW",
        "recommendations": [],
    }


# ---------------------------------------------------------------------------
# Cyclomatic complexity helpers
# ---------------------------------------------------------------------------

def _radon_cc_for_class(source: str, class_name: str, method_names: List[str]) -> int:
    """
    Compute total cyclomatic complexity for a class using radon.
    Sums CC of all methods belonging to the class.
    """
    if not RADON_AVAILABLE:
        return _ast_cc_fallback(source, class_name)
    try:
        blocks = cc_visit(source)
        total_cc = 0
        for block in blocks:
            # block.letter: 'M' = method, 'F' = function, 'C' = class
            if block.letter in ("M", "F") and block.name in method_names:
                total_cc += block.complexity
        # If class has methods but radon found none, default to 1
        return max(1, total_cc) if method_names else 1
    except SyntaxError:
        return 1


def _ast_cc_fallback(source: str, class_name: str) -> int:
    """
    Estimate cyclomatic complexity using AST branch counting.
    Counts: if, elif, for, while, except, with, and, or, assert, comprehensions.
    """
    BRANCH_NODES = (
        ast.If, ast.For, ast.While, ast.ExceptHandler,
        ast.With, ast.BoolOp, ast.Assert,
        ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
    )
    try:
        tree = ast.parse(source)
        # Find the class node
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                count = 1  # Base complexity
                for child in ast.walk(node):
                    if isinstance(child, BRANCH_NODES):
                        count += 1
                return count
        return 1
    except SyntaxError:
        return 1


# ---------------------------------------------------------------------------
# Import extraction
# ---------------------------------------------------------------------------

def _extract_imports(tree: ast.Module) -> List[str]:
    """Return a flat list of module names imported at the module level."""
    imports: List[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module.split(".")[0])
    return list(set(imports))


# ---------------------------------------------------------------------------
# Core class name detection helpers
# ---------------------------------------------------------------------------

_CORE_KEYWORDS = {"core", "service", "services", "model", "models", "base", "manager"}


def _is_core_module(file_path: str) -> bool:
    """Return True if the file path contains a 'core' module keyword."""
    parts = os.path.normpath(file_path).replace("\\", "/").lower().split("/")
    for part in parts:
        stem = os.path.splitext(part)[0]
        if stem in _CORE_KEYWORDS:
            return True
    return False


# ---------------------------------------------------------------------------
# Main parse function
# ---------------------------------------------------------------------------

def parse(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse a Python source file and return a list of ClassInfo dicts.

    Each dict represents one class. Module-level functions that are not
    inside any class are grouped into a synthetic '__module__' entry only
    if there are no class definitions in the file.

    Parameters
    ----------
    file_path : str
        Absolute or relative path to the .py file.

    Returns
    -------
    list of dict
        Each dict conforms to the ClassInfo schema.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            source = fh.read()
    except OSError as exc:
        raise RuntimeError(f"Cannot read {file_path}: {exc}") from exc

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as exc:
        raise RuntimeError(f"Syntax error in {file_path}: {exc}") from exc

    global_imports = _extract_imports(tree)
    core_mod = _is_core_module(file_path)
    results: List[Dict[str, Any]] = []

    class_nodes = [n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef)]

    for cls_node in class_nodes:
        method_nodes = [
            n for n in ast.iter_child_nodes(cls_node)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        method_names = [m.name for m in method_nodes]

        has_public_api = any(
            not m.startswith("_") for m in method_names
        )

        all_lines = [cls_node.lineno]
        for child in ast.walk(cls_node):
            if hasattr(child, "lineno"):
                all_lines.append(child.lineno)  # type: ignore[arg-type]
        line_end = max(all_lines)

        cc = _radon_cc_for_class(source, cls_node.name, method_names)

        # Fan-out: number of imported modules referenced inside this class
        # (approximation: count distinct import names used in class body)
        class_source_lines = source.splitlines()[cls_node.lineno - 1 : line_end]
        class_source_fragment = "\n".join(class_source_lines)
        fan_out_approx = sum(
            1 for imp in global_imports if imp in class_source_fragment
        )

        info = _make_class_info(
            name=cls_node.name,
            line_start=cls_node.lineno,
            line_end=line_end,
            methods=method_names,
            imports=global_imports,
            cyclomatic_complexity=cc,
            has_public_api=has_public_api,
            is_core_module=core_mod,
        )
        info["fan_out"] = fan_out_approx
        results.append(info)

    # If no classes found, treat module-level functions as one pseudo-class
    if not class_nodes:
        func_nodes = [
            n for n in ast.iter_child_nodes(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        if func_nodes:
            method_names = [f.name for f in func_nodes]
            has_public_api = any(not m.startswith("_") for m in method_names)
            line_start = func_nodes[0].lineno
            all_lines = []
            for fn in func_nodes:
                for child in ast.walk(fn):
                    if hasattr(child, "lineno"):
                        all_lines.append(child.lineno)  # type: ignore[arg-type]
            line_end = max(all_lines) if all_lines else func_nodes[-1].lineno

            module_name = os.path.splitext(os.path.basename(file_path))[0]
            module_name = module_name.replace("_", " ").title().replace(" ", "")

            if RADON_AVAILABLE:
                try:
                    blocks = cc_visit(source)
                    cc = max(1, sum(b.complexity for b in blocks if b.letter == "F"))
                except SyntaxError:
                    cc = 1
            else:
                cc = _ast_cc_fallback(source, "")

            info = _make_class_info(
                name=module_name + "Module",
                line_start=line_start,
                line_end=line_end,
                methods=method_names,
                imports=global_imports,
                cyclomatic_complexity=cc,
                has_public_api=has_public_api,
                is_core_module=core_mod,
            )
            results.append(info)

    return results
