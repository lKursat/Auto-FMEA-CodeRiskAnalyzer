"""
recommender.py — Actionable Recommendation Generator
======================================================
Generates specific, metric-driven recommendations for each class.
Always produces at least 3 recommendations.
Includes duplicate class warnings and impact analysis recommendations.
"""

import os
from typing import Any, Dict, List


def _suggest_test_path(class_name: str, file_path: str, language: str, project_root: str = "") -> str:
    """Suggest the canonical test file path for a given class (relative to project root)."""
    if language == "python":
        parts = os.path.normpath(file_path).replace("\\", "/").split("/")
        snake = _to_snake(class_name)
        for i, part in enumerate(parts):
            if part in ("src", "lib", "app"):
                parts[i] = "tests"
                parts[-1] = f"test_{snake}.py"
                full_path = "/".join(parts)
                return _make_relative(full_path, project_root)
        parent = os.path.dirname(file_path).replace("\\", "/")
        full_path = f"{parent}/tests/test_{snake}.py"
    elif language == "java":
        parent = os.path.dirname(file_path).replace("\\", "/")
        full_path = f"{parent}/{class_name}Test.java"
    elif language == "csharp":
        parent = os.path.dirname(file_path).replace("\\", "/")
        full_path = f"{parent}/{class_name}Tests.cs"
    else:
        full_path = f"tests/{class_name}Test"
    return _make_relative(full_path, project_root)


def _make_relative(full_path: str, project_root: str) -> str:
    """Convert an absolute path to a relative path from project_root."""
    if not project_root:
        return full_path
    try:
        return os.path.relpath(full_path, project_root).replace("\\", "/")
    except ValueError:
        return full_path


def _to_snake(name: str) -> str:
    import re
    s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def generate(
    class_info: Dict[str, Any],
    file_path: str = "",
    language: str = "python",
    project_root: str = "",
) -> List[str]:
    """
    Generate specific, actionable recommendations for a class.

    Always returns at least 3 items. Recommendations reference actual
    class names, metric values, and concrete file paths.
    """
    name = class_info.get("name", "UnknownClass")
    cc = class_info.get("cyclomatic_complexity", 1)
    fan_in = class_info.get("fan_in", 0)
    fan_out = class_info.get("fan_out", 0)
    severity = class_info.get("severity", 1)
    detection = class_info.get("detection", 9)
    rpn = class_info.get("rpn", 0)
    affected = class_info.get("affected_classes", [])
    methods = class_info.get("methods", [])
    test_found = class_info.get("test_file_found", False)
    is_duplicate = class_info.get("duplicate", False)
    duplicate_locations = class_info.get("duplicate_locations", [])

    recs: List[str] = []

    is_test_class = class_info.get("is_test_class", False)
    if is_test_class:
        recs.append("[TEST-CLASS] This is a test class.")

    if is_duplicate and duplicate_locations:
        n = len(duplicate_locations)
        loc_strs = []
        for loc in duplicate_locations:
            fname = os.path.basename(loc.get("file", "unknown"))
            line = loc.get("line", "?")
            loc_strs.append(f"{fname} line {line}")
        locs_text = ", ".join(loc_strs)
        recs.append(
            f"[DUPLICATE-CLASS] WARNING: Class '{name}' is defined {n} times "
            f"in this project ({locs_text}). This causes ambiguity and "
            f"maintenance risk. Rename or consolidate duplicate definitions "
            f"immediately."
        )

    if fan_in > 0 and affected:
        affected_str = ", ".join(affected[:10])
        recs.append(
            f"[IMPACT] {fan_in} classes depend on '{name}': {affected_str}. "
            f"Any interface change or defect here will directly break these "
            f"dependents. Review all callers before modifying public methods."
        )

    if cc > 10:
        branch_count = max(1, cc - 1)
        method_suggestion = ""
        if methods:
            method_suggestion = (
                f" Consider extracting {min(branch_count, 3)} logical branches "
                f"from methods such as {', '.join(methods[:3])} into separate helper methods."
            )
        recs.append(
            f"[CC-{cc}] '{name}' has a cyclomatic complexity of {cc}, which exceeds "
            f"the recommended threshold of 10. Refactor into smaller, single-responsibility "
            f"methods.{method_suggestion}"
        )

    if fan_in > 5:
        affected_str = (
            ", ".join(affected[:5]) + (" and more" if len(affected) > 5 else "")
            if affected else f"{fan_in} other classes"
        )
        recs.append(
            f"[FAN-IN-{fan_in}] '{name}' is depended upon by {fan_in} other classes "
            f"({affected_str}). Any defect or interface change here has a high blast radius. "
            f"Add comprehensive unit tests before modifying any public methods."
        )

    if detection == 9 and not is_test_class:
        test_path = _suggest_test_path(name, file_path, language, project_root)
        method_list = ""
        if methods:
            public_methods = [m for m in methods if not m.startswith("_")][:4]
            if public_methods:
                method_list = (
                    f" Ensure it covers at least: {', '.join(public_methods)}()."
                )
        recs.append(
            f"[NO-TEST] No test coverage detected for '{name}'. "
            f"Create a test file at '{test_path}'.{method_list}"
        )

    if severity >= 8 and affected:
        affected_str = ", ".join(affected[:6])
        recs.append(
            f"[SEVERITY-{severity}] Changes to '{name}' directly impact: {affected_str}. "
            f"Review all callers before committing changes. "
            f"Document the public API contract of '{name}' to prevent silent breakage."
        )

    if fan_out > 5:
        recs.append(
            f"[FAN-OUT-{fan_out}] '{name}' depends on {fan_out} other modules. "
            f"This high coupling makes it fragile. Apply Dependency Inversion: "
            f"inject dependencies through the constructor rather than creating them internally."
        )

    if rpn >= 200:
        recs.append(
            f"[CRITICAL-RPN-{rpn}] '{name}' has a CRITICAL Risk Priority Number of {rpn}. "
            f"This class should be treated as a top-priority refactoring target. "
            f"Schedule a dedicated code review session before the next release."
        )

    if 5 < cc <= 10 and len(recs) < 3:
        recs.append(
            f"[CC-{cc}] '{name}' has a cyclomatic complexity of {cc}. "
            f"While still manageable, consider adding inline documentation "
            f"for each conditional branch to aid future maintainers."
        )

    if len(recs) < 3:
        generic = [
            (
                f"[BEST-PRACTICE] Add a class-level docstring to '{name}' describing "
                f"its single responsibility, public API, and any important invariants."
            ),
            (
                f"[BEST-PRACTICE] Review '{name}' for adherence to the Single "
                f"Responsibility Principle. A class should have only one reason to change."
            ),
            (
                f"[BEST-PRACTICE] Ensure all public methods of '{name}' have "
                f"parameter validation and raise meaningful exceptions on invalid input."
            ),
            (
                f"[BEST-PRACTICE] Consider adding an integration test that exercises "
                f"'{name}' end-to-end through its primary use case."
            ),
        ]
        for rec in generic:
            if len(recs) >= 3:
                break
            if rec not in recs:
                recs.append(rec)

    return recs
