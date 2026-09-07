"""
csharp_parser.py — C# Source Code Parser
==========================================
Uses regex and a lightweight brace-depth tracker to parse C# source files.
Extracts class names, method signatures, using statements, and estimates
cyclomatic complexity.

No external libraries are required; only the Python standard library is used.

Returns a list of ClassInfo dicts compatible with the Auto-FMEA JSON schema.
"""

import os
import re
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Matches class declarations (handles partial, abstract, sealed, static, etc.)
_CLASS_PATTERN = re.compile(
    r'(?:(?:public|private|protected|internal|abstract|sealed|static|partial)\s+)*'
    r'class\s+(\w+)',
    re.MULTILINE,
)

# Matches method declarations (simplified: captures method name)
_METHOD_PATTERN = re.compile(
    r'(?:(?:public|private|protected|internal|static|virtual|override|abstract'
    r'|async|sealed|new)\s+)+'
    r'(?:[\w<>\[\],\s?]+\s+)?'      # return type
    r'(\w+)\s*\(',                   # method name
    re.MULTILINE,
)

# Matches using directives
_USING_PATTERN = re.compile(r'using\s+([\w.]+)\s*;', re.MULTILINE)

# Branch keywords for CC estimation
_BRANCH_PATTERN = re.compile(
    r'\b(if|else\s+if|for|foreach|while|do|case|catch|\?\?|&&|\|\|)\b'
)

_CORE_KEYWORDS = {"Core", "Service", "Services", "Model", "Models", "Base", "Manager"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_core_module(file_path: str) -> bool:
    """Return True if any path component matches a core keyword."""
    parts = os.path.normpath(file_path).replace("\\", "/").split("/")
    for part in parts:
        stem = os.path.splitext(part)[0]
        if stem in _CORE_KEYWORDS or stem.lower() in {k.lower() for k in _CORE_KEYWORDS}:
            return True
    return False


def _estimate_cc(class_body: str) -> int:
    """Estimate cyclomatic complexity by counting decision points."""
    branches = len(_BRANCH_PATTERN.findall(class_body))
    return max(1, 1 + branches)


def _find_class_body(source: str, class_start_pos: int) -> tuple[int, int, str]:
    """
    Find the opening brace and closing brace for a class starting at
    `class_start_pos`. Returns (line_start, line_end, body_text).
    """
    brace_start = source.find("{", class_start_pos)
    if brace_start == -1:
        line_start = source[:class_start_pos].count("\n") + 1
        return line_start, line_start, ""

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

    body_text = source[brace_start + 1: body_end]
    line_start = source[:class_start_pos].count("\n") + 1
    line_end = source[:body_end].count("\n") + 1
    return line_start, line_end, body_text


def _extract_methods(class_body: str) -> List[str]:
    """Extract method names from a class body string."""
    # Common non-method keywords to exclude
    _KEYWORDS = {
        "if", "while", "for", "foreach", "switch", "catch", "using",
        "return", "new", "typeof", "nameof", "sizeof", "default",
    }
    methods = []
    for match in _METHOD_PATTERN.finditer(class_body):
        name = match.group(1)
        if name not in _KEYWORDS:
            methods.append(name)
    return list(set(methods))


def _extract_usings(source: str) -> List[str]:
    """Extract short namespace names from using directives."""
    usings = []
    for match in _USING_PATTERN.finditer(source):
        ns = match.group(1)
        parts = ns.split(".")
        # Use the last non-empty part
        usings.append(parts[-1] if parts else ns)
    return list(set(usings))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse a C# source file and return a list of ClassInfo dicts.

    Uses regex-based parsing with brace-depth tracking to locate class
    boundaries. Handles nested types by processing only top-level class
    declarations (first depth-0 class opening).

    Parameters
    ----------
    file_path : str
        Absolute or relative path to the .cs file.

    Returns
    -------
    list of dict
        Each dict conforms to the ClassInfo schema.
    """
    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="replace") as fh:
            source = fh.read()
    except OSError as exc:
        raise RuntimeError(f"Cannot read {file_path}: {exc}") from exc

    using_imports = _extract_usings(source)
    core_mod = _is_core_module(file_path)
    results: List[Dict[str, Any]] = []

    # Track already-processed regions to avoid duplicate processing of nested classes
    processed_ranges: List[tuple[int, int]] = []

    for class_match in _CLASS_PATTERN.finditer(source):
        class_name = class_match.group(1)
        class_start = class_match.start()

        inside_processed = any(
            start < class_start < end
            for start, end in processed_ranges
        )
        if inside_processed:
            continue

        line_start, line_end, class_body = _find_class_body(source, class_start)
        if not class_body:
            continue

        brace_pos = source.find("{", class_start)
        processed_ranges.append((brace_pos, source.find("}", brace_pos)))

        methods = _extract_methods(class_body)
        has_public_api = bool(re.search(r'\bpublic\b', class_body))
        cc = _estimate_cc(class_body)

        fan_out = sum(1 for ns in using_imports if ns in class_body)

        results.append({
            "name": class_name,
            "line_start": line_start,
            "line_end": line_end,
            "methods": methods,
            "imports": using_imports,
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
