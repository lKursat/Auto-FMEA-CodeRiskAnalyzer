"""
risk_calculator.py — FMEA Risk Priority Number Calculator
Implements: RPN = Severity x Occurrence x Detection

Severity (1-10):
  base = min(10, fan_in * 2)
  +2 if class has public API methods
  +1 if class name contains Service/Manager/Controller/Repository/Processor/Handler/Engine
  severity = min(10, base)
  If duplicate: severity = min(10, severity + 3)

Occurrence (1-10):
  CC bands + git commit bonus

Detection (1-10):
  Based on test file presence

Risk Level:
  RPN >= 200: CRITICAL
  RPN >= 100: HIGH
  RPN >=  50: MEDIUM
  RPN <   50: LOW
"""

import os
import re
from typing import Optional

_CORE_NAME_KEYWORDS = {
    "service", "manager", "controller", "repository",
    "processor", "handler", "engine",
}


def _git_commits_last_30_days(file_path: str, project_root: str = "") -> tuple:
    """Return (commit_count, git_available) for the file in the last 30 days."""
    try:
        import git  # type: ignore
        search_dir = project_root if project_root else os.path.dirname(os.path.abspath(file_path))
        repo = git.Repo(search_dir, search_parent_directories=True)
        commits = list(repo.iter_commits(paths=os.path.abspath(file_path), after="30.days.ago"))
        return (len(commits), True)
    except Exception:
        return (0, False)


def _is_core_class_name(class_name: str) -> bool:
    """Return True if the class name contains a core keyword like Service, Manager, etc."""
    lower = class_name.lower()
    for keyword in _CORE_NAME_KEYWORDS:
        if keyword in lower:
            return True
    return False


def compute_severity(
    fan_in: int,
    has_public_api: bool,
    is_core_module: bool,
    class_name: str = "",
    is_duplicate: bool = False,
) -> int:
    """
    Severity (1-10):
      base = min(10, fan_in * 2)
      +2 if class has public API methods
      +1 if class name contains Service/Manager/Controller/Repository/Processor/Handler/Engine
      severity = min(10, base)
      If duplicate: severity = min(10, severity + 3)
    """
    base = min(10, fan_in * 2)
    if has_public_api:
        base += 2
    if is_core_module or _is_core_class_name(class_name):
        base += 1
    severity = max(1, min(10, base))

    if is_duplicate:
        severity = min(10, severity + 3)

    return severity


def compute_occurrence(cyclomatic_complexity: int, file_path: Optional[str] = None, project_root: str = "") -> tuple:
    """
    Occurrence (1-10) based on CC bands, plus git commit bonus.
    Returns (occurrence, churn_count, churn_bonus, git_available).
    """
    cc = cyclomatic_complexity
    if cc <= 5:
        base = 2
    elif cc <= 10:
        base = 4
    elif cc <= 15:
        base = 6
    elif cc <= 20:
        base = 8
    else:
        base = 10

    churn_count = 0
    churn_bonus = 0
    git_available = False
    if file_path:
        churn_count, git_available = _git_commits_last_30_days(file_path, project_root)
        if churn_count >= 15:
            churn_bonus = 3
        elif churn_count >= 10:
            churn_bonus = 2
        elif churn_count >= 5:
            churn_bonus = 1

    return (min(10, base + churn_bonus), churn_count, churn_bonus, git_available)


def compute_detection(test_file_found: bool, coverage_known: bool = False) -> int:
    """
    Detection (1-10) — lower = better test coverage.
      Test found & coverage known: 3
      Test found, coverage unknown: 5
      No test file:                 9
    """
    if test_file_found and coverage_known:
        return 3
    elif test_file_found:
        return 5
    else:
        return 9


def compute_rpn(severity: int, occurrence: int, detection: int) -> int:
    return severity * occurrence * detection


def classify_risk(rpn: int) -> str:
    if rpn >= 200:
        return "CRITICAL"
    elif rpn >= 100:
        return "HIGH"
    elif rpn >= 50:
        return "MEDIUM"
    else:
        return "LOW"


def compute_all_metrics(class_info: dict, file_path: Optional[str] = None, project_root: str = "") -> dict:
    """Compute all FMEA metrics and return updated class_info dict."""
    severity = compute_severity(
        fan_in=class_info.get("fan_in", 0),
        has_public_api=class_info.get("has_public_api", False),
        is_core_module=class_info.get("is_core_module", False),
        class_name=class_info.get("name", ""),
        is_duplicate=class_info.get("duplicate", False),
    )
    occurrence, churn_count, churn_bonus, git_available = compute_occurrence(
        cyclomatic_complexity=class_info.get("cyclomatic_complexity", 1),
        file_path=file_path,
        project_root=project_root,
    )
    detection = compute_detection(
        test_file_found=class_info.get("test_file_found", False),
        coverage_known=class_info.get("coverage_known", False),
    )
    rpn = compute_rpn(severity, occurrence, detection)
    risk_level = classify_risk(rpn)

    updated = dict(class_info)
    updated["severity"] = severity
    updated["occurrence"] = occurrence
    updated["detection"] = detection
    updated["rpn"] = rpn
    updated["risk_level"] = risk_level
    updated["git_churn"] = churn_count
    updated["churn_bonus"] = churn_bonus
    updated["git_available"] = git_available
    return updated
