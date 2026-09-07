"""
analyzer.py — Auto-FMEA Analysis Engine CLI Entry Point
=========================================================
Usage:
    python analyzer.py --file <path> --language <python|java|csharp> --project-root <path>

Outputs a single JSON object to stdout. On any error, outputs:
    {"error": "<message>", "file": "<path>"}

Exit codes:
    0 — success (valid JSON on stdout)
    1 — error (error JSON on stdout)
"""

import argparse
import json
import os
import sys
import traceback
import datetime

_ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)

from parsers import python_parser, java_parser, csharp_parser
from dependency_graph import build_dependency_map, find_test_file, find_duplicates
from risk_calculator import compute_all_metrics
from recommender import generate as generate_recommendations


# ---------------------------------------------------------------------------
# Language dispatch
# ---------------------------------------------------------------------------

_PARSERS = {
    "python": python_parser.parse,
    "java":   java_parser.parse,
    "csharp": csharp_parser.parse,
}

_LANGUAGE_ALIASES = {
    ".py":   "python",
    ".java": "java",
    ".cs":   "csharp",
}


def _detect_language(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    return _LANGUAGE_ALIASES.get(ext, "python")


# ---------------------------------------------------------------------------
# Project-wide history (stored in a JSON sidecar next to analyzer.py)
# ---------------------------------------------------------------------------

_HISTORY_FILE = os.path.join(_ENGINE_DIR, ".fmea_history.json")


def _load_history() -> dict:
    if os.path.exists(_HISTORY_FILE):
        try:
            with open(_HISTORY_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, dict) and "history" in data:
                    return data
        except Exception:
            pass
    return {"history": []}


def _save_history(history: dict) -> None:
    try:
        with open(_HISTORY_FILE, "w", encoding="utf-8") as fh:
            json.dump(history, fh, indent=2)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Test class detection
# ---------------------------------------------------------------------------

def _is_test_class(class_name: str, file_path: str) -> bool:
    """Return True if the class is a test class based on filename or class name."""
    basename = os.path.basename(file_path).lower()
    if basename.startswith("test_"):
        return True
    # Check for Test, Tests, or TestCase in class name (case-sensitive)
    if "Test" in class_name:
        return True
    return False


# ---------------------------------------------------------------------------
# Core analysis pipeline
# ---------------------------------------------------------------------------

def analyze(file_path: str, language: str, project_root: str) -> dict:
    """
    Run the full analysis pipeline for one file.

    Returns a dict matching the Auto-FMEA JSON schema.
    """
    abs_file = os.path.abspath(file_path)
    abs_root = os.path.abspath(project_root)

    parse_fn = _PARSERS.get(language)
    if parse_fn is None:
        raise ValueError(f"Unsupported language: {language}")

    classes = parse_fn(abs_file)
    if not classes:
        return {
            "file": file_path,
            "language": language,
            "classes": [],
            "project_summary": _empty_summary(),
        }

    for cls in classes:
        if _is_test_class(cls["name"], abs_file):
            cls["is_test_class"] = True
            # Report CC as method count instead of raw CC, capped at 50
            cls["cyclomatic_complexity"] = min(50, len(cls.get("methods", [])))
        else:
            cls["is_test_class"] = False

    try:
        duplicates = find_duplicates(abs_root, language)
    except Exception:
        duplicates = {}

    for cls in classes:
        name = cls["name"]
        if name in duplicates and len(duplicates[name]) >= 2:
            cls["duplicate"] = True
            cls["duplicate_locations"] = duplicates[name]
        else:
            cls["duplicate"] = False
            cls["duplicate_locations"] = []

    for cls in classes:
        if cls.get("duplicate"):
            name = cls["name"]
            max_cc = cls["cyclomatic_complexity"]
            for loc in duplicates.get(name, []):
                loc_file = loc.get("file", "")
                if loc_file and os.path.exists(loc_file):
                    try:
                        other_classes = _PARSERS[language](loc_file)
                        for other in other_classes:
                            if other["name"] == name:
                                max_cc = max(max_cc, other.get("cyclomatic_complexity", 1))
                    except Exception:
                        pass
            cls["cyclomatic_complexity"] = max_cc

    class_names = [c["name"] for c in classes]
    try:
        dep_map = build_dependency_map(
            abs_root, language,
            primary_classes=class_names,
            primary_file=abs_file,
        )
    except Exception:
        dep_map = {}

    for cls in classes:
        if cls.get("is_test_class", False):
            # Test classes are their own test — set detection=3
            cls["test_file_found"] = True
            cls["coverage_known"] = True
        else:
            try:
                found, coverage = find_test_file(cls["name"], abs_root, language)
            except Exception:
                found, coverage = False, False
            cls["test_file_found"] = found
            cls["coverage_known"] = coverage

    for cls in classes:
        name = cls["name"]
        if name in dep_map:
            cls["fan_in"] = dep_map[name]["fan_in"]
            cls["fan_out"] = dep_map[name]["fan_out"]
            cls["affected_classes"] = dep_map[name]["affected_classes"]

    for cls in classes:
        updated = compute_all_metrics(cls, file_path=abs_file, project_root=abs_root)
        cls.update(updated)

    for cls in classes:
        cls["recommendations"] = generate_recommendations(cls, abs_file, language, project_root=abs_root)

    now_str = datetime.datetime.utcnow().isoformat() + "Z"
    try:
        rel_file = os.path.relpath(abs_file, abs_root).replace("\\", "/")
    except ValueError:
        rel_file = file_path

    history_entry = {
        "timestamp": now_str,
        "file": rel_file,
        "classes": [
            {
                "name": cls["name"],
                "rpn": cls["rpn"],
                "severity": cls["severity"],
                "occurrence": cls["occurrence"],
                "detection": cls["detection"],
                "risk_level": cls["risk_level"],
            }
            for cls in classes
        ],
    }

    history_data = _load_history()
    history_data["history"].append(history_entry)
    per_file = {}
    for entry in history_data["history"]:
        f = entry.get("file", "")
        if f not in per_file:
            per_file[f] = []
        per_file[f].append(entry)
    pruned = []
    for f, entries in per_file.items():
        pruned.extend(entries[-20:])
    pruned.sort(key=lambda e: e.get("timestamp", ""))
    history_data["history"] = pruned
    _save_history(history_data)

    all_class_entries = {}
    for entry in history_data["history"]:
        for c in entry.get("classes", []):
            key = entry.get("file", "") + "::" + c.get("name", "")
            all_class_entries[key] = {
                "name": c.get("name", ""),
                "file": entry.get("file", ""),
                "severity": c.get("severity", 0),
                "occurrence": c.get("occurrence", 0),
                "detection": c.get("detection", 0),
                "rpn": c.get("rpn", 0),
                "risk_level": c.get("risk_level", "LOW"),
                "last_analyzed": entry.get("timestamp", ""),
            }

    all_entries = list(all_class_entries.values())
    project_summary = _compute_project_summary(all_entries)

    # Extract last 10 history entries for this file (for trend chart)
    file_history = [e for e in history_data["history"] if e.get("file") == rel_file][-10:]

    output_classes = []
    for cls in classes:
        out = {
            "name":                  cls["name"],
            "line_start":            cls.get("line_start", 0),
            "line_end":              cls.get("line_end", 0),
            "cyclomatic_complexity": cls.get("cyclomatic_complexity", 1),
            "fan_in":                cls.get("fan_in", 0),
            "fan_out":               cls.get("fan_out", 0),
            "affected_classes":      cls.get("affected_classes", []),
            "test_file_found":       cls.get("test_file_found", False),
            "severity":              cls["severity"],
            "occurrence":            cls["occurrence"],
            "detection":             cls["detection"],
            "rpn":                   cls["rpn"],
            "risk_level":            cls["risk_level"],
            "recommendations":       cls["recommendations"],
            "last_analyzed":         now_str,
            "git_churn":             cls.get("git_churn", 0),
            "churn_bonus":           cls.get("churn_bonus", 0),
            "git_available":         cls.get("git_available", False),
        }
        if cls.get("duplicate", False):
            out["duplicate"] = True
        output_classes.append(out)

    return {
        "file":            file_path,
        "language":        language,
        "classes":         output_classes,
        "project_summary": project_summary,
        "history":         file_history,
    }


def _empty_summary() -> dict:
    return {
        "total_classes_analyzed": 0,
        "average_rpn": 0,
        "project_health_score": 100,
        "critical_count": 0,
        "high_count": 0,
        "medium_count": 0,
        "low_count": 0,
        "top_risks": [],
        "all_classes": [],
    }


def _compute_project_summary(entries: list) -> dict:
    """Compute aggregate statistics from all historical analysis entries.
    
    Health score formula:
      base = 100 - (average_rpn / 10)
      -10 per CRITICAL class
      - 5 per HIGH class
      - 8 per duplicate class
      clamped to [0, 100]
    """
    if not entries:
        return _empty_summary()

    rpns = [e["rpn"] for e in entries]
    avg_rpn = sum(rpns) / len(rpns)

    critical = sum(1 for e in entries if e["risk_level"] == "CRITICAL")
    high     = sum(1 for e in entries if e["risk_level"] == "HIGH")
    medium   = sum(1 for e in entries if e["risk_level"] == "MEDIUM")
    low      = sum(1 for e in entries if e["risk_level"] == "LOW")
    dup_count = sum(1 for e in entries if e.get("duplicate", False))

    health = 100 - (avg_rpn / 10)
    health -= critical * 10
    health -= high * 5
    health -= dup_count * 8
    health = max(0, min(100, round(health)))

    sorted_entries = sorted(entries, key=lambda e: e["rpn"], reverse=True)
    top_risks = [e["name"] for e in sorted_entries[:5]]

    all_classes = [
        {
            "name":        e.get("name", ""),
            "file":        e.get("file", ""),
            "severity":    e.get("severity", 0),
            "occurrence":  e.get("occurrence", 0),
            "detection":   e.get("detection", 0),
            "rpn":         e.get("rpn", 0),
            "risk_level":  e.get("risk_level", "LOW"),
            "last_analyzed": e.get("last_analyzed", ""),
        }
        for e in sorted_entries
    ]

    return {
        "total_classes_analyzed": len(entries),
        "average_rpn":            round(avg_rpn, 1),
        "project_health_score":   health,
        "critical_count":         critical,
        "high_count":             high,
        "medium_count":           medium,
        "low_count":              low,
        "top_risks":              top_risks,
        "all_classes":            all_classes,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Auto-FMEA: Static analysis and risk calculation engine."
    )
    parser.add_argument("--file",         required=True, help="Path to the source file to analyse.")
    parser.add_argument("--language",     required=True,
                        choices=["python", "java", "csharp"],
                        help="Programming language of the source file.")
    parser.add_argument("--project-root", required=True, dest="project_root",
                        help="Root directory of the project for dependency scanning.")
    args = parser.parse_args()

    try:
        result = analyze(args.file, args.language, args.project_root)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0)
    except Exception as exc:
        error_output = {
            "error":    str(exc),
            "file":     args.file,
            "language": args.language,
            "traceback": traceback.format_exc(),
        }
        print(json.dumps(error_output, indent=2, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
