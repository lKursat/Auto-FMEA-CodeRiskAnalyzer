"""
test_recommender.py — Unit tests for the recommendation generator.
===================================================================
Tests that specific metric conditions produce the correct
recommendation tags and content. Covers Python, Java, and C#
language-specific test path suggestions.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from recommender import generate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_info(**kwargs):
    """Build a minimal class_info dict with defaults, overridden by kwargs."""
    info = {
        "name": "TestClass",
        "cyclomatic_complexity": 5,
        "fan_in": 0,
        "fan_out": 0,
        "severity": 3,
        "detection": 9,
        "rpn": 27,
        "affected_classes": [],
        "methods": ["run", "process"],
        "test_file_found": False,
        "duplicate": False,
        "duplicate_locations": [],
    }
    info.update(kwargs)
    return info


def _recs_text(recs):
    """Join all recommendations into a single string for easier searching."""
    return "\n".join(recs)


# ===========================================================================
# Python recommendation tests
# ===========================================================================

class TestRecommenderPython(unittest.TestCase):
    """Test recommendation generation for Python-style classes."""

    def test_high_cc_recommendation(self):
        """CC=19 → recommendation must contain the tag '[CC-19]'."""
        info = _base_info(cyclomatic_complexity=19)
        recs = generate(info, file_path="/project/service.py", language="python")
        self.assertTrue(
            any("[CC-19]" in r for r in recs),
            f"Expected [CC-19] tag in recommendations, got: {recs}"
        )

    def test_no_test_recommendation(self):
        """test_file_found=False → recommendation must contain '[NO-TEST]'."""
        info = _base_info(test_file_found=False, detection=9)
        recs = generate(info, file_path="/project/module.py", language="python")
        self.assertTrue(
            any("[NO-TEST]" in r for r in recs),
            f"Expected [NO-TEST] tag in recommendations, got: {recs}"
        )

    def test_no_test_suggests_correct_path(self):
        """Python class 'UserService' → suggested path ends with 'test_user_service.py'."""
        info = _base_info(name="UserService", test_file_found=False, detection=9)
        recs = generate(info, file_path="/project/src/user_service.py", language="python")
        no_test_recs = [r for r in recs if "[NO-TEST]" in r]
        self.assertTrue(len(no_test_recs) > 0, "Expected a [NO-TEST] recommendation")
        self.assertTrue(
            "test_user_service.py" in no_test_recs[0],
            f"Expected 'test_user_service.py' in path, got: {no_test_recs[0]}"
        )

    def test_high_fanin_recommendation(self):
        """fan_in=4 with 4 affected classes → recommendation contains '[IMPACT]' and all names."""
        info = _base_info(
            fan_in=4,
            affected_classes=["Alpha", "Beta", "Gamma", "Delta"],
        )
        recs = generate(info, file_path="/project/core.py", language="python")
        impact_recs = [r for r in recs if "[IMPACT]" in r]
        self.assertTrue(len(impact_recs) > 0, "Expected an [IMPACT] recommendation")
        text = impact_recs[0]
        for name in ["Alpha", "Beta", "Gamma", "Delta"]:
            self.assertIn(name, text, f"Expected '{name}' in [IMPACT] text")

    def test_duplicate_recommendation(self):
        """duplicate=True → recommendation must contain '[DUPLICATE-CLASS]'."""
        info = _base_info(
            duplicate=True,
            duplicate_locations=[
                {"file": "/project/a.py", "line": 5},
                {"file": "/project/b.py", "line": 10},
            ],
        )
        recs = generate(info, file_path="/project/a.py", language="python")
        self.assertTrue(
            any("[DUPLICATE-CLASS]" in r for r in recs),
            f"Expected [DUPLICATE-CLASS] tag, got: {recs}"
        )

    def test_critical_rpn_recommendation(self):
        """rpn=432 → recommendation must contain '[CRITICAL-RPN-432]'."""
        info = _base_info(rpn=432, severity=8, detection=9, cyclomatic_complexity=3)
        recs = generate(info, file_path="/project/core.py", language="python")
        self.assertTrue(
            any("[CRITICAL-RPN-432]" in r for r in recs),
            f"Expected [CRITICAL-RPN-432] tag, got: {recs}"
        )

    def test_minimum_three_recommendations(self):
        """Any valid input must produce at least 3 recommendations."""
        info = _base_info(
            cyclomatic_complexity=2,
            fan_in=0,
            fan_out=0,
            severity=1,
            rpn=6,
            test_file_found=True,
            detection=5,
        )
        recs = generate(info, file_path="/project/tiny.py", language="python")
        self.assertGreaterEqual(
            len(recs), 3,
            f"Expected at least 3 recommendations, got {len(recs)}: {recs}"
        )

    def test_no_duplicate_no_warning(self):
        """duplicate=False → '[DUPLICATE-CLASS]' must NOT appear in any recommendation."""
        info = _base_info(duplicate=False, duplicate_locations=[])
        recs = generate(info, file_path="/project/clean.py", language="python")
        combined = _recs_text(recs)
        self.assertNotIn(
            "[DUPLICATE-CLASS]", combined,
            f"[DUPLICATE-CLASS] appeared unexpectedly: {recs}"
        )


# ===========================================================================
# Java recommendation tests
# ===========================================================================

class TestRecommenderJava(unittest.TestCase):
    """Test Java-specific recommendation details."""

    def test_no_test_suggests_java_path(self):
        """Java class 'OrderService' → suggested test path ends with 'OrderServiceTest.java'."""
        info = _base_info(name="OrderService", test_file_found=False, detection=9)
        recs = generate(info, file_path="/project/src/OrderService.java", language="java")
        no_test_recs = [r for r in recs if "[NO-TEST]" in r]
        self.assertTrue(len(no_test_recs) > 0, "Expected a [NO-TEST] recommendation")
        self.assertTrue(
            "OrderServiceTest.java" in no_test_recs[0],
            f"Expected 'OrderServiceTest.java' in path, got: {no_test_recs[0]}"
        )

    def test_high_cc_java(self):
        """CC=15 → recommendation must contain '[CC-15]'."""
        info = _base_info(cyclomatic_complexity=15)
        recs = generate(info, file_path="/project/Service.java", language="java")
        self.assertTrue(
            any("[CC-15]" in r for r in recs),
            f"Expected [CC-15] tag, got: {recs}"
        )


# ===========================================================================
# C# recommendation tests
# ===========================================================================

class TestRecommenderCSharp(unittest.TestCase):
    """Test C#-specific recommendation details."""

    def test_no_test_suggests_csharp_path(self):
        """C# class 'PaymentProcessor' → suggested test path ends with 'PaymentProcessorTests.cs'."""
        info = _base_info(name="PaymentProcessor", test_file_found=False, detection=9)
        recs = generate(info, file_path="/project/src/PaymentProcessor.cs", language="csharp")
        no_test_recs = [r for r in recs if "[NO-TEST]" in r]
        self.assertTrue(len(no_test_recs) > 0, "Expected a [NO-TEST] recommendation")
        self.assertTrue(
            "PaymentProcessorTests.cs" in no_test_recs[0],
            f"Expected 'PaymentProcessorTests.cs' in path, got: {no_test_recs[0]}"
        )

    def test_high_cc_csharp(self):
        """CC=12 → recommendation must contain '[CC-12]'."""
        info = _base_info(cyclomatic_complexity=12)
        recs = generate(info, file_path="/project/Service.cs", language="csharp")
        self.assertTrue(
            any("[CC-12]" in r for r in recs),
            f"Expected [CC-12] tag, got: {recs}"
        )


if __name__ == "__main__":
    unittest.main()
