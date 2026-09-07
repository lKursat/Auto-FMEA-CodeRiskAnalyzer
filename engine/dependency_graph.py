"""
dependency_graph.py — Cross-File Dependency Analysis
=====================================================
Builds a project-wide reverse dependency map for a given language.

For each class in the project, determines:
  - fan_out: how many other classes/modules THIS class imports or references
  - fan_in:  how many other classes/modules depend on THIS class (impact radius)
  - affected_classes: list of class names that depend on this class

Also performs:
  - Duplicate class detection (same class name in multiple files)
  - Test file detection

The analysis is purely static and reference-based. It scans all source files
of the specified language within the project root.

Fan-in counts BOTH cross-file AND intra-file (same-file) references.
When multiple classes coexist in the same file, references between them
are detected by isolating each class's source region and checking for
usage patterns of other class names within it.
"""

import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

_ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)

from parsers import python_parser, java_parser, csharp_parser


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

_EXTENSIONS = {
    "python": ".py",
    "java":   ".java",
    "csharp": ".cs",
}

_SKIP_DIRS = {
    "__pycache__", ".git", ".github", "node_modules",
    "out", "bin", "obj", ".venv", "venv", "env",
    ".tox", "dist", "build", ".mypy_cache",
}


def _discover_files(project_root: str, language: str) -> List[str]:
    """
    Walk the project root and return all source files for the given language.
    Skips hidden directories, __pycache__, .git, node_modules, out, bin, obj.
    """
    ext = _EXTENSIONS.get(language, "")
    found: List[str] = []
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [
            d for d in dirs
            if d not in _SKIP_DIRS and not d.startswith(".")
        ]
        for fname in files:
            if fname.endswith(ext):
                found.append(os.path.join(root, fname))
    return found


# ---------------------------------------------------------------------------
# Language-specific reference pattern builders
# ---------------------------------------------------------------------------

def _build_python_ref_patterns(class_name: str) -> List[re.Pattern]:
    """Build regex patterns that detect references to class_name in Python."""
    return [
        re.compile(r'\bimport\s+' + re.escape(class_name) + r'\b'),
        re.compile(r'\bfrom\s+\S+\s+import\s+[^#\n]*\b' + re.escape(class_name) + r'\b'),
        re.compile(re.escape(class_name) + r'\s*\('),          # instantiation
        re.compile(r':\s*' + re.escape(class_name) + r'\b'),   # type hint
        re.compile(r'->\s*' + re.escape(class_name) + r'\b'),  # return type hint
    ]


def _build_java_ref_patterns(class_name: str) -> List[re.Pattern]:
    """Build regex patterns that detect references to class_name in Java."""
    return [
        re.compile(r'import\s+[\w.]*' + re.escape(class_name) + r'\s*;'),
        re.compile(re.escape(class_name) + r'\s+\w'),             # variable declaration
        re.compile(r'new\s+' + re.escape(class_name) + r'\s*\('), # instantiation
        re.compile(r'extends\s+' + re.escape(class_name) + r'\b'),
        re.compile(r'implements\s+[^{]*\b' + re.escape(class_name) + r'\b'),
    ]


def _build_csharp_ref_patterns(class_name: str) -> List[re.Pattern]:
    """Build regex patterns that detect references to class_name in C#."""
    return [
        re.compile(r'using\s+[\w.]*' + re.escape(class_name) + r'\b'),
        re.compile(r'new\s+' + re.escape(class_name) + r'\s*[\(<]'),  # instantiation
        re.compile(r':\s*' + re.escape(class_name) + r'\b'),          # inheritance
        re.compile(re.escape(class_name) + r'\s+\w'),                 # variable declaration
        re.compile(r'<' + re.escape(class_name) + r'>'),              # generic type arg
    ]


_REF_PATTERN_BUILDERS = {
    "python": _build_python_ref_patterns,
    "java":   _build_java_ref_patterns,
    "csharp": _build_csharp_ref_patterns,
}


def _class_defines_pattern(class_name: str, language: str) -> re.Pattern:
    """Pattern that matches the class DEFINITION line (to exclude it from ref matching)."""
    if language == "python":
        return re.compile(r'^\s*class\s+' + re.escape(class_name) + r'\b', re.MULTILINE)
    elif language == "java":
        return re.compile(r'\bclass\s+' + re.escape(class_name) + r'\b', re.MULTILINE)
    elif language == "csharp":
        return re.compile(r'\bclass\s+' + re.escape(class_name) + r'\b', re.MULTILINE)
    return re.compile(re.escape(class_name))


# ---------------------------------------------------------------------------
# Helpers for intra-file class body extraction
# ---------------------------------------------------------------------------

def _extract_class_body(source: str, class_name: str, language: str) -> Optional[str]:
    """
    Extract the source code body of `class_name` from the file source.
    Returns None if the class cannot be found.

    For Python: finds "class ClassName:" and uses indentation to delimit.
    For Java/C#: finds "class ClassName" and uses brace-depth tracking.
    """
    if language == "python":
        pattern = re.compile(
            r'^(\s*)class\s+' + re.escape(class_name) + r'\b[^:]*:\s*\n',
            re.MULTILINE,
        )
        match = pattern.search(source)
        if not match:
            return None
        class_indent = len(match.group(1))
        body_start = match.end()
        lines = source[body_start:].splitlines()
        body_lines: List[str] = []
        for line in lines:
            stripped = line.lstrip()
            if stripped == "" or stripped.startswith("#"):
                body_lines.append(line)
                continue
            indent = len(line) - len(stripped)
            if indent <= class_indent:
                break
            body_lines.append(line)
        return "\n".join(body_lines)
    else:
        # Java / C# — brace-depth tracking
        pattern = re.compile(
            r'\bclass\s+' + re.escape(class_name) + r'\b',
            re.MULTILINE,
        )
        match = pattern.search(source)
        if not match:
            return None
        brace_start = source.find("{", match.end())
        if brace_start == -1:
            return None
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
        return source[brace_start + 1:body_end]


# ---------------------------------------------------------------------------
# Core graph builder
# ---------------------------------------------------------------------------

def build_dependency_map(
    project_root: str,
    language: str,
    primary_classes: Optional[List[str]] = None,
    primary_file: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Scan all source files in `project_root` for the given `language` and build
    a dependency map using language-specific reference patterns.

    Fan-in is computed from TWO sources:
      1. Cross-file references: other files that reference this class
      2. Intra-file references: other classes in the SAME file that reference
         this class (detected by isolating each class's body)

    Parameters
    ----------
    project_root : str
        Root directory of the project to scan.
    language : str
        One of 'python', 'java', 'csharp'.
    primary_classes : list of str, optional
        Names of the classes being analysed in the current file.
    primary_file : str, optional
        Absolute path of the file being analysed.

    Returns
    -------
    dict
        {
          class_name: {
            "fan_in": int,
            "fan_out": int,
            "affected_classes": [str, ...],
          },
          ...
        }
    """
    pattern_builder = _REF_PATTERN_BUILDERS.get(language, _build_python_ref_patterns)

    # Step 1: Discover all source files and read their contents
    source_files = _discover_files(project_root, language)
    all_source: Dict[str, str] = {}
    for fpath in source_files:
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                all_source[fpath] = fh.read()
        except OSError:
            continue

    # Step 2: Parse all files to get class names, line ranges, and their defining files
    # Maps: file_path -> list of parsed class dicts
    file_to_parsed: Dict[str, List[Dict[str, Any]]] = {}
    # Maps: file_path -> list of class names defined there
    file_to_classes: Dict[str, List[str]] = {}
    # Maps: class_name -> list of file_paths where it is defined
    class_to_files: Dict[str, List[str]] = {}

    for fpath in source_files:
        if fpath not in all_source:
            continue
        try:
            if language == "python":
                classes = python_parser.parse(fpath)
            elif language == "java":
                classes = java_parser.parse(fpath)
            elif language == "csharp":
                classes = csharp_parser.parse(fpath)
            else:
                classes = []
            file_to_parsed[fpath] = classes
            names = [c["name"] for c in classes]
            file_to_classes[fpath] = names
            for cn in names:
                class_to_files.setdefault(cn, []).append(fpath)
        except Exception:
            file_to_classes[fpath] = []
            file_to_parsed[fpath] = []

    # Collect all known class names
    all_class_names: Set[str] = set()
    for names in file_to_classes.values():
        all_class_names.update(names)

    # Step 3: For each target class, count references from OTHER classes
    targets = primary_classes if primary_classes else list(all_class_names)
    primary_file_norm = os.path.normpath(primary_file) if primary_file else None

    result: Dict[str, Dict[str, Any]] = {}

    for class_name in targets:
        # Skip names that are too short (common false positives like "A", "T")
        if len(class_name) < 3:
            result[class_name] = {"fan_in": 0, "fan_out": 0, "affected_classes": []}
            continue

        # Build reference detection patterns for this class name
        ref_patterns = pattern_builder(class_name)
        defining_files = set(class_to_files.get(class_name, []))
        defining_norms = {os.path.normpath(f) for f in defining_files}

        fan_in = 0
        affected: List[str] = []

        for fpath, src in all_source.items():
            fpath_norm = os.path.normpath(fpath)
            is_same_file = (
                fpath_norm in defining_norms
                or (primary_file_norm and fpath_norm == primary_file_norm)
            )

            if is_same_file:
                other_classes_in_file = [
                    cn for cn in file_to_classes.get(fpath, [])
                    if cn != class_name and len(cn) >= 3
                ]
                seen_others: Set[str] = set()
                for other_cn in other_classes_in_file:
                    if other_cn in seen_others:
                        continue
                    seen_others.add(other_cn)

                    other_body = _extract_class_body(src, other_cn, language)
                    if other_body is None:
                        continue

                    # Check if other_cn's body references class_name
                    found_ref = False
                    for pat in ref_patterns:
                        if pat.search(other_body):
                            found_ref = True
                            break

                    if found_ref:
                        fan_in += 1
                        affected.append(other_cn)
            else:
                found_ref = False
                for pat in ref_patterns:
                    if pat.search(src):
                        found_ref = True
                        break

                if found_ref:
                    fan_in += 1
                    for cn in file_to_classes.get(fpath, []):
                        if cn != class_name:
                            affected.append(cn)

        fan_out = 0
        for def_file in defining_files:
            if def_file in all_source:
                own_body = _extract_class_body(all_source[def_file], class_name, language)
                if own_body is None:
                    own_body = all_source[def_file]
                for other_class in all_class_names:
                    if other_class == class_name or len(other_class) < 3:
                        continue
                    other_patterns = pattern_builder(other_class)
                    for pat in other_patterns:
                        if pat.search(own_body):
                            fan_out += 1
                            break

        result[class_name] = {
            "fan_in": fan_in,
            "fan_out": fan_out,
            "affected_classes": sorted(set(affected)),
        }

    return result


# ---------------------------------------------------------------------------
# Duplicate class detection (project-wide scan)
# ---------------------------------------------------------------------------

def find_duplicates(
    project_root: str,
    language: str,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Scan all source files in the project and find classes with the same name
    defined in more than one location.

    Returns
    -------
    dict
        {
          class_name: [
            {"file": "path/to/a.py", "line": 10},
            {"file": "path/to/b.py", "line": 5},
          ],
          ...
        }
    Only classes that appear 2+ times are included.
    """
    source_files = _discover_files(project_root, language)
    # Map: class_name -> list of {file, line}
    class_locations: Dict[str, List[Dict[str, Any]]] = {}

    for fpath in source_files:
        try:
            if language == "python":
                classes = python_parser.parse(fpath)
            elif language == "java":
                classes = java_parser.parse(fpath)
            elif language == "csharp":
                classes = csharp_parser.parse(fpath)
            else:
                classes = []
            for c in classes:
                entry = {
                    "file": fpath,
                    "line": c.get("line_start", 0),
                }
                class_locations.setdefault(c["name"], []).append(entry)
        except Exception:
            continue

    # Filter: keep only names with 2+ definitions
    duplicates = {
        name: locs
        for name, locs in class_locations.items()
        if len(locs) >= 2
    }
    return duplicates


# ---------------------------------------------------------------------------
# Test file detection
# ---------------------------------------------------------------------------

def find_test_file(
    class_name: str,
    project_root: str,
    language: str,
) -> Tuple[bool, bool]:
    """
    Search the project for a test file that corresponds to `class_name`.

    Naming conventions:
      Python : test_<snake_class>.py  or  tests/test_*.py
      Java   : <ClassName>Test.java   or  <ClassName>Tests.java
      C#     : <ClassName>Tests.cs    or  <ClassName>Test.cs

    Returns
    -------
    (test_file_found, coverage_known)
        test_file_found : bool — True if any matching test file exists
        coverage_known  : bool — True if the file contains references to class_name
    """
    snake = _to_snake_case(class_name)

    if language == "python":
        patterns = [
            f"test_{snake}.py",
            f"test_{class_name.lower()}.py",
            f"{snake}_test.py",
        ]
    elif language == "java":
        patterns = [
            f"{class_name}Test.java",
            f"{class_name}Tests.java",
        ]
    elif language == "csharp":
        patterns = [
            f"{class_name}Tests.cs",
            f"{class_name}Test.cs",
        ]
    else:
        patterns = []

    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
        for fname in files:
            if fname in patterns:
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                        content = fh.read()
                    coverage_known = class_name in content
                    return True, coverage_known
                except OSError:
                    return True, False

    return False, False


def _to_snake_case(name: str) -> str:
    """Convert CamelCase to snake_case."""
    s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
