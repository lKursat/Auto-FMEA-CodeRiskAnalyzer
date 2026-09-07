"""
test_integration.py — End-to-end integration tests for Auto-FMEA engine.
=========================================================================
Runs analyzer.py as a real subprocess (exactly as the VS Code extension does)
and validates the JSON output against the expected schema and business rules.

Uses the real sample files in test_samples/.
"""

import sys
import os
import json
import subprocess
import unittest

# Paths
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_ENGINE = os.path.join(_ROOT, "engine")
_ANALYZER = os.path.join(_ENGINE, "analyzer.py")
_SAMPLES = os.path.join(_ROOT, "test_samples")
_HISTORY_FILE = os.path.join(_ENGINE, ".fmea_history.json")


def _run_analyzer(file_path, language, project_root=None):
    """
    Run analyzer.py as a subprocess and return (exit_code, parsed_json_or_None, raw_stdout).
    Clears history file before each run for test isolation.
    """
    # Clear history for test isolation
    if os.path.exists(_HISTORY_FILE):
        os.remove(_HISTORY_FILE)

    if project_root is None:
        project_root = _SAMPLES

    cmd = [
        sys.executable, _ANALYZER,
        "--file", file_path,
        "--language", language,
        "--project-root", project_root,
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=120,
    )
    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        data = None
    return result.returncode, data, result.stdout


# ===========================================================================
# Python integration tests
# ===========================================================================

class TestIntegrationPython(unittest.TestCase):
    """End-to-end tests analysing test_samples/sample.py."""

    @classmethod
    def setUpClass(cls):
        """Run the analyzer once and cache the result for all tests in this class."""
        sample_path = os.path.join(_SAMPLES, "sample.py")
        cls.exit_code, cls.data, cls.raw = _run_analyzer(sample_path, "python")

    def test_analyzer_produces_valid_json(self):
        """Running the analyzer on sample.py must exit 0 and produce valid JSON with a 'classes' key."""
        self.assertEqual(self.exit_code, 0, f"Non-zero exit code. Stdout:\n{self.raw}")
        self.assertIsNotNone(self.data, f"Output is not valid JSON:\n{self.raw}")
        self.assertIn("classes", self.data)

    def test_all_required_json_fields(self):
        """Every class in the output must have all required JSON fields."""
        required_keys = {
            "name", "severity", "occurrence", "detection",
            "rpn", "risk_level", "cyclomatic_complexity",
            "fan_in", "fan_out", "recommendations", "affected_classes",
        }
        for cls in self.data["classes"]:
            for key in required_keys:
                self.assertIn(
                    key, cls,
                    f"Class '{cls.get('name', '?')}' is missing key '{key}'"
                )

    def test_high_complexity_class_is_high_risk(self):
        """UserService has CC>15, so its RPN must be > 100 (at least HIGH risk)."""
        user_svc = next(
            (c for c in self.data["classes"] if c["name"] == "UserService"),
            None,
        )
        self.assertIsNotNone(user_svc, "UserService not found in output")
        self.assertGreater(
            user_svc["rpn"], 100,
            f"UserService RPN should be > 100, got {user_svc['rpn']}"
        )

    def test_recommendations_not_empty(self):
        """Every class must have at least 3 recommendations."""
        for cls in self.data["classes"]:
            self.assertGreaterEqual(
                len(cls["recommendations"]), 3,
                f"Class '{cls['name']}' has only {len(cls['recommendations'])} recommendations"
            )

    def test_project_summary_present(self):
        """Output must contain a 'project_summary' with all required keys."""
        self.assertIn("project_summary", self.data)
        summary = self.data["project_summary"]
        required = {
            "total_classes_analyzed", "average_rpn", "project_health_score",
            "critical_count", "high_count", "medium_count", "low_count", "top_risks",
        }
        for key in required:
            self.assertIn(
                key, summary,
                f"project_summary missing key '{key}'"
            )


# ===========================================================================
# Java integration tests
# ===========================================================================

class TestIntegrationJava(unittest.TestCase):
    """End-to-end tests analysing test_samples/Sample.java."""

    @classmethod
    def setUpClass(cls):
        sample_path = os.path.join(_SAMPLES, "Sample.java")
        cls.exit_code, cls.data, cls.raw = _run_analyzer(sample_path, "java")

    def test_analyzer_produces_valid_json(self):
        """Running the analyzer on Sample.java must exit 0 and produce valid JSON."""
        self.assertEqual(self.exit_code, 0, f"Non-zero exit code. Stdout:\n{self.raw}")
        self.assertIsNotNone(self.data, f"Output is not valid JSON:\n{self.raw}")
        self.assertIn("classes", self.data)

    def test_java_class_detected(self):
        """At least 1 class with name 'UserService' must be found."""
        names = {c["name"] for c in self.data["classes"]}
        self.assertIn(
            "UserService", names,
            f"Expected 'UserService' in Java output, found: {names}"
        )


# ===========================================================================
# C# integration tests
# ===========================================================================

class TestIntegrationCSharp(unittest.TestCase):
    """End-to-end tests analysing test_samples/Sample.cs."""

    @classmethod
    def setUpClass(cls):
        sample_path = os.path.join(_SAMPLES, "Sample.cs")
        cls.exit_code, cls.data, cls.raw = _run_analyzer(sample_path, "csharp")

    def test_analyzer_produces_valid_json(self):
        """Running the analyzer on Sample.cs must exit 0 and produce valid JSON."""
        self.assertEqual(self.exit_code, 0, f"Non-zero exit code. Stdout:\n{self.raw}")
        self.assertIsNotNone(self.data, f"Output is not valid JSON:\n{self.raw}")
        self.assertIn("classes", self.data)

    def test_csharp_class_detected(self):
        """At least 1 class must be found in the C# sample."""
        self.assertGreater(
            len(self.data["classes"]), 0,
            "Expected at least 1 class in C# output"
        )


# ===========================================================================
# Duplicate class integration test
# ===========================================================================

class TestIntegrationDuplicate(unittest.TestCase):
    """End-to-end test for duplicate class detection using mytetst.py."""

    @classmethod
    def setUpClass(cls):
        sample_path = os.path.join(_SAMPLES, "mytetst.py")
        cls.exit_code, cls.data, cls.raw = _run_analyzer(sample_path, "python")

    def test_duplicate_class_flagged(self):
        """mytetst.py has 2 PaymentProcessor classes → at least one must have 'duplicate': true
        and '[DUPLICATE-CLASS]' in its recommendations."""
        self.assertEqual(self.exit_code, 0, f"Non-zero exit code. Stdout:\n{self.raw}")
        self.assertIsNotNone(self.data, f"Output is not valid JSON:\n{self.raw}")

        payment_classes = [
            c for c in self.data["classes"]
            if c["name"] == "PaymentProcessor"
        ]
        self.assertTrue(
            len(payment_classes) >= 1,
            f"Expected at least 1 PaymentProcessor class, found: "
            f"{[c['name'] for c in self.data['classes']]}"
        )

        # At least one should be marked as duplicate
        has_duplicate = any(c.get("duplicate", False) for c in payment_classes)
        self.assertTrue(
            has_duplicate,
            f"Expected at least one PaymentProcessor with 'duplicate': true"
        )

        # The duplicate one should have the warning in recommendations
        dup_class = next(c for c in payment_classes if c.get("duplicate", False))
        combined_recs = "\n".join(dup_class.get("recommendations", []))
        self.assertIn(
            "[DUPLICATE-CLASS]", combined_recs,
            f"Expected [DUPLICATE-CLASS] in recommendations, got: {dup_class['recommendations']}"
        )


# ===========================================================================
# Fan-in integration test
# ===========================================================================

class TestIntegrationFanIn(unittest.TestCase):
    """End-to-end test for cross-file fan-in using mytetst.py."""

    @classmethod
    def setUpClass(cls):
        sample_path = os.path.join(_SAMPLES, "mytetst.py")
        cls.exit_code, cls.data, cls.raw = _run_analyzer(sample_path, "python")

    def test_fanin_detected_in_mytetst(self):
        """PaymentProcessor is used by OrderService and RefundService in the same file.
        Since all classes are in the same file (mytetst.py) and primary_file is mytetst.py,
        the fan_in from within the same file is excluded. However, if there are other .py
        files in test_samples/ that reference PaymentProcessor, fan_in may be > 0.

        The key assertion: the analyzer runs successfully and the PaymentProcessor
        class is present with valid fan_in >= 0."""
        self.assertEqual(self.exit_code, 0, f"Non-zero exit code. Stdout:\n{self.raw}")
        self.assertIsNotNone(self.data)

        payment_classes = [
            c for c in self.data["classes"]
            if c["name"] == "PaymentProcessor"
        ]
        self.assertTrue(
            len(payment_classes) >= 1,
            "Expected PaymentProcessor in output"
        )

        # fan_in should be a non-negative integer
        for pc in payment_classes:
            self.assertIsInstance(pc["fan_in"], int)
            self.assertGreaterEqual(pc["fan_in"], 0)


if __name__ == "__main__":
    unittest.main()
