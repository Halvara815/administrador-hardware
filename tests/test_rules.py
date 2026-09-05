from unittest import TestCase

from hardware_admin.diagnostics.rules import (
    CPU_RULE,
    DISK_RULE,
    MEMORY_RULE,
    MetricKind,
    classify_percent,
)
from hardware_admin.domain.models import HealthStatus


class ThresholdRuleTests(TestCase):
    def test_cpu_boundaries_are_decimal_safe(self) -> None:
        cases = {
            0.0: HealthStatus.NORMAL,
            70.0: HealthStatus.NORMAL,
            70.1: HealthStatus.WARNING,
            89.9: HealthStatus.WARNING,
            90.0: HealthStatus.CRITICAL,
            96.0: HealthStatus.CRITICAL,
            100.0: HealthStatus.CRITICAL,
        }
        for percent, expected in cases.items():
            with self.subTest(percent=percent):
                self.assertIs(classify_percent(MetricKind.CPU, percent), expected)

    def test_memory_boundaries_use_inclusive_warning_threshold(self) -> None:
        cases = {
            0.0: HealthStatus.NORMAL,
            69.9: HealthStatus.NORMAL,
            70.0: HealthStatus.WARNING,
            89.9: HealthStatus.WARNING,
            90.0: HealthStatus.CRITICAL,
            97.5: HealthStatus.CRITICAL,
        }
        for percent, expected in cases.items():
            with self.subTest(percent=percent):
                self.assertIs(classify_percent(MetricKind.MEMORY, percent), expected)

    def test_disk_keeps_project_policy_and_marks_96_percent_critical(self) -> None:
        cases = {
            50.0: HealthStatus.NORMAL,
            84.9: HealthStatus.NORMAL,
            85.0: HealthStatus.WARNING,
            94.9: HealthStatus.WARNING,
            95.0: HealthStatus.CRITICAL,
            96.0: HealthStatus.CRITICAL,
        }
        for percent, expected in cases.items():
            with self.subTest(percent=percent):
                self.assertIs(classify_percent(MetricKind.DISK, percent), expected)

    def test_missing_value_is_unknown_not_normal(self) -> None:
        self.assertIs(CPU_RULE.classify(None), HealthStatus.UNKNOWN)
        self.assertIs(MEMORY_RULE.classify(None), HealthStatus.UNKNOWN)
        self.assertIs(DISK_RULE.classify(None), HealthStatus.UNKNOWN)

    def test_rules_hold_the_documented_thresholds(self) -> None:
        self.assertEqual((CPU_RULE.warning, CPU_RULE.critical), (70.0, 90.0))
        self.assertEqual((MEMORY_RULE.warning, MEMORY_RULE.critical), (70.0, 90.0))
        self.assertEqual((DISK_RULE.warning, DISK_RULE.critical), (85.0, 95.0))
        self.assertTrue(CPU_RULE.warning_strict)
        self.assertFalse(MEMORY_RULE.warning_strict)