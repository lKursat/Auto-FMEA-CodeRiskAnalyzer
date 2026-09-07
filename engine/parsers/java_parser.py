"""
java_parser.py — Java Source Code Parser
==========================================
Uses the `javalang` library to parse Java source files and extract class
information: class name, methods, imports, and an estimated cyclomatic
complexity based on control-flow statement counting.

Returns a list of ClassInfo dicts compatible with the Auto-FMEA JSON schema.
"""

import os
import re
from typing import Any, Dict, List

try:
    import javalang
    JAVALANG_AVAILABLE = True
except ImportError:
    JAVALANG_AVAILABLE = False


# ---------------------------------------------------------------------------
# Core keyword detection
# ---------------------------------------------------------------------------

_CORE_KEYWORDS = {"core", "service", "services", "model", "models", "base", "manager"}


def _is_core_module(file_path: str) -> bool:
    """Return True if any directory component is a core keyword."""
    parts = os.path.normpath(file_path).replace("\\", "/").lower().split("/")
    for part in parts:
        stem = os.path.splitext(part)[0]
        if stem in _CORE_KEYWORDS:
            return True
    return False


# ---------------------------------------------------------------------------
# Cyclomatic complexity estimation
# ---------------------------------------------------------------------------

# Branch-inducing Java keywords (McCabe branch counting)
_BRANCH_PATTERN = re.compile(
    r'\b(if|else\s+if|for|while|do|case|catch|&&|\|\|)\b'
)


def _estimate_cc_from_source(class_body: str) -> int:
    """
    Estimate cyclomatic complexity by counting branch keywords.
    CC = 1 + number_of_branches
    """
    branches = len(_BRANCH_PATTERN.findall(class_body))
    return max(1, 1 + branches)


# ---------------------------------------------------------------------------
# Fallback regex parser (when javalang is unavailable)
# ---------------------------------------------------------------------------

_CLASS_PATTERN = re.compile(
    r'(?:public\s+|protected\s+|private\s+|abstract\s+|final\s+)*'
    r'class\s+(\w+)',
    re.MULTILINE,
)
_METHOD_PATTERN = re.compile(
    r'(?:public|protected|private|static|final|abstract|synchronized)'
    r'(?:\s+(?:public|protected|private|static|final|abstract|synchronized))*'
    r'\s+\w[\w<>\[\],\s]*\s+(\w+)\s*\(',
    re.MULTILINE,
)
_IMPORT_PATTERN = re.compile(r'import\s+([\w.]+)\s*;', re.MULTILINE)


def _parse_with_regex(source: str, file_path: str) -> List[Dict[str, Any]]:
    """Fallback parser using regex when javalang is unavailable."""
    imports = [m.split(".")[-2] if "." in m else m
               for m in _IMPORT_PATTERN.findall(source)]
    imports = list(set(imports))
    core_mod = _is_core_module(file_path)
    results: List[Dict[str, Any]] = []

    for class_match in _CLASS_PATTERN.finditer(source):
        class_name = class_match.group(1)
        start_pos = class_match.start()
        line_start = source[:start_pos].count("\n") + 1

        brace_start = source.find("{", start_pos)
        if brace_start == -1:
            continue
        depth = 0
        body_end = brace_start
        for i, ch in enumerate(source[brace_start:], start=brace_start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    body_end = i
                    break

        class_body = source[brace_start:body_end]
        line_end = source[:body_end].count("\n") + 1

        methods = list(set(_METHOD_PATTERN.findall(class_body)))
        has_public_api = bool(re.search(r'\bpublic\b', class_body))
        cc = _estimate_cc_from_source(class_body)

        fan_out = sum(1 for imp in imports if imp in class_body)

        results.append({
            "name": class_name,
            "line_start": line_start,
            "line_end": line_end,
            "methods": methods,
            "imports": imports,
            "cyclomatic_complexity": cc,
            "has_public_api": has_public_api,
            "is_core_module": core_mod,
            "fan_in": 0,
            "fan_out": fan_out,
            "affected_classes": [],
            "test_file_found": False,
            "severity": 0,
            "occurrence": 0,
            "detection": 0,
            "rpn": 0,
            "risk_level": "LOW",
            "recommendations": [],
        })

    return results


# ---------------------------------------------------------------------------
# javalang-based parser
# ---------------------------------------------------------------------------

def _get_line_of_position(source: str, position: int) -> int:
    """Convert a character position to a 1-indexed line number."""
    return source[:position].count("\n") + 1


def _parse_with_javalang(source: str, file_path: str) -> List[Dict[str, Any]]:
    """Parse Java source using the javalang library."""
    try:
        tree = javalang.parse.parse(source)
    except (javalang.parser.JavaSyntaxError, Exception) as exc:
        raise RuntimeError(f"javalang parse error in {file_path}: {exc}") from exc

    imports = []
    for imp in tree.imports:
        parts = imp.path.split(".")
        if len(parts) >= 2:
            imports.append(parts[-2])
        else:
            imports.append(parts[-1])
    imports = list(set(imports))

    core_mod = _is_core_module(file_path)
    results: List[Dict[str, Any]] = []
    source_lines = source.splitlines()

    for _, class_decl in tree.filter(javalang.tree.ClassDeclaration):
        class_name = class_decl.name

        line_start = class_decl.position.line if class_decl.position else 1

        # Collect method names
        methods: List[str] = []
        for method in class_decl.methods:
            methods.append(method.name)

        # Detect public API: any public method
        has_public_api = any(
            "public" in (m.modifiers or set()) for m in class_decl.methods
        )

        depth = 0
        line_end = line_start
        for idx in range(line_start - 1, len(source_lines)):
            for ch in source_lines[idx]:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        line_end = idx + 1
                        break
            if depth == 0 and line_end > line_start:
                break

        class_body = "\n".join(source_lines[line_start - 1: line_end])
        cc = _estimate_cc_from_source(class_body)

        fan_out = sum(1 for imp in imports if imp in class_body)

        results.append({
            "name": class_name,
            "line_start": line_start,
            "line_end": line_end,
            "methods": methods,
            "imports": imports,
            "cyclomatic_complexity": cc,
            "has_public_api": has_public_api,
            "is_core_module": core_mod,
            "fan_in": 0,
            "fan_out": fan_out,
            "affected_classes": [],
            "test_file_found": False,
            "severity": 0,
            "occurrence": 0,
            "detection": 0,
            "rpn": 0,
            "risk_level": "LOW",
            "recommendations": [],
        })

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse a Java source file and return a list of ClassInfo dicts.

    Falls back to regex-based parsing if javalang is unavailable.

    Parameters
    ----------
    file_path : str
        Absolute or relative path to the .java file.

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

    if JAVALANG_AVAILABLE:
        return _parse_with_javalang(source, file_path)
    else:
        return _parse_with_regex(source, file_path)
