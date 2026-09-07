"""
test_risk_calculator.py — Unit tests for the FMEA risk calculator.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from risk_calculator import (
    compute_severity, compute_occurrence, compute_detection,
    compute_rpn, classify_risk, compute_all_metrics,
)


class TestSeverity(unittest.TestCase):
    def test_zero_fan_in_no_extras(self):
        self.assertEqual(compute_severity(0, False, False), 1)

    def test_fan_in_5_no_extras(self):
        # base = min(10, 5*2) = 10, no extras => 10
        self.assertEqual(compute_severity(5, False, False), 10)

    def test_public_api_adds_2(self):
        # base = min(10, 1*2)=2, +2=4
        self.assertEqual(compute_severity(1, True, False), 4)

    def test_core_module_adds_1(self):
        # base=2, +1=3
        self.assertEqual(compute_severity(1, False, True), 3)

    def test_all_extras_capped_at_10(self):
        # base=10, +2, +1 → capped at 10
        self.assertEqual(compute_severity(5, True, True), 10)

    def test_minimum_is_1(self):
        self.assertGreaterEqual(compute_severity(0, False, False), 1)

    def test_core_class_name_adds_1(self):
        # fan_in=0 base=0, +2(public) +1(name has Service) = 3
        self.assertEqual(compute_severity(0, True, False, class_name="PaymentService"), 3)

    def test_duplicate_adds_3(self):
        # fan_in=0 base=0, no extras => 1, +3 duplicate = 4
        self.assertEqual(compute_severity(0, False, False, is_duplicate=True), 4)

    def test_duplicate_capped_at_10(self):
        # fan_in=5 base=10, +3 duplicate => still 10
        self.assertEqual(compute_severity(5, True, True, is_duplicate=True), 10)


class TestOccurrence(unittest.TestCase):
    def test_cc_le_5(self):
        self.assertEqual(compute_occurrence(3)[0], 2)

    def test_cc_le_10(self):
        self.assertEqual(compute_occurrence(10)[0], 4)

    def test_cc_le_15(self):
        self.assertEqual(compute_occurrence(13)[0], 6)

    def test_cc_le_20(self):
        self.assertEqual(compute_occurrence(18)[0], 8)

    def test_cc_gt_20(self):
        self.assertEqual(compute_occurrence(25)[0], 10)

    def test_capped_at_10(self):
        self.assertLessEqual(compute_occurrence(100)[0], 10)

    def test_no_file_no_git_bonus(self):
        # No file_path → no git bonus
        self.assertEqual(compute_occurrence(5, None)[0], 2)


class TestDetection(unittest.TestCase):
    def test_no_test_file(self):
        self.assertEqual(compute_detection(False, False), 9)

    def test_test_file_no_coverage(self):
        self.assertEqual(compute_detection(True, False), 5)

    def test_test_file_with_coverage(self):
        self.assertEqual(compute_detection(True, True), 3)


class TestRPN(unittest.TestCase):
    def test_basic_multiplication(self):
        self.assertEqual(compute_rpn(5, 6, 9), 270)

    def test_low_rpn(self):
        self.assertEqual(compute_rpn(1, 2, 3), 6)

    def test_max_rpn(self):
        self.assertEqual(compute_rpn(10, 10, 10), 1000)


class TestClassifyRisk(unittest.TestCase):
    def test_critical(self):
        self.assertEqual(classify_risk(200), "CRITICAL")
        self.assertEqual(classify_risk(500), "CRITICAL")

    def test_high(self):
        self.assertEqual(classify_risk(100), "HIGH")
        self.assertEqual(classify_risk(199), "HIGH")

    def test_medium(self):
        self.assertEqual(classify_risk(50), "MEDIUM")
        self.assertEqual(classify_risk(99), "MEDIUM")

    def test_low(self):
        self.assertEqual(classify_risk(49), "LOW")
        self.assertEqual(classify_risk(0), "LOW")


class TestComputeAllMetrics(unittest.TestCase):
    def _base_info(self, **kwargs):
        info = {
            "name": "TestClass",
            "fan_in": 0, "has_public_api": False, "is_core_module": False,
            "cyclomatic_complexity": 3, "test_file_found": False, "coverage_known": False,
            "duplicate": False,
        }
        info.update(kwargs)
        return info

    def test_all_fields_populated(self):
        result = compute_all_metrics(self._base_info())
        for key in ("severity", "occurrence", "detection", "rpn", "risk_level"):
            self.assertIn(key, result)

    def test_rpn_matches_formula(self):
        result = compute_all_metrics(self._base_info(
            fan_in=3, has_public_api=True, cyclomatic_complexity=12, test_file_found=True,
        ))
        self.assertEqual(result["rpn"], result["severity"] * result["occurrence"] * result["detection"])

    def test_critical_classification(self):
        result = compute_all_metrics(self._base_info(
            fan_in=5, has_public_api=True, is_core_module=True,
            cyclomatic_complexity=22, test_file_found=False,
        ))
        self.assertEqual(result["risk_level"], "CRITICAL")

    def test_low_classification(self):
        result = compute_all_metrics(self._base_info(
            fan_in=0, has_public_api=False, is_core_module=False,
            cyclomatic_complexity=3, test_file_found=True, coverage_known=True,
        ))
        self.assertEqual(result["risk_level"], "LOW")

    def test_duplicate_increases_severity(self):
        no_dup = compute_all_metrics(self._base_info(
            fan_in=1, has_public_api=True, duplicate=False,
        ))
        with_dup = compute_all_metrics(self._base_info(
            fan_in=1, has_public_api=True, duplicate=True,
        ))
        self.assertEqual(with_dup["severity"], min(10, no_dup["severity"] + 3))

    def test_core_name_detection(self):
        """A class named 'UserService' should get is_core_module=True effect even without path flag."""
        result = compute_all_metrics(self._base_info(
            name="UserService", fan_in=0, has_public_api=True, is_core_module=False,
        ))
        # base=0, +2(public), +1(Service in name) = 3
        self.assertEqual(result["severity"], 3)

    def test_bug5_expected_output(self):
        """
        From the user spec: fan_in=2, CC=19, no test, duplicate.
        Expected: severity=7, occurrence=8, detection=9, RPN=504, CRITICAL.
        """
        result = compute_all_metrics(self._base_info(
            name="SomeClass",
            fan_in=2,
            has_public_api=False,
            is_core_module=False,
            cyclomatic_complexity=19,
            test_file_found=False,
            duplicate=True,
        ))
        # base = min(10, 2*2) = 4, +0(no public) +0(no core name) = 4, +3(dup) = 7
        self.assertEqual(result["severity"], 7)
        # CC=19 → band <=20 → 8
        self.assertEqual(result["occurrence"], 8)
        # no test → 9
        self.assertEqual(result["detection"], 9)
        # RPN = 7*8*9 = 504
        self.assertEqual(result["rpn"], 504)
        self.assertEqual(result["risk_level"], "CRITICAL")


if __name__ == "__main__":
    unittest.main()
