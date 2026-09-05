from datetime import UTC, datetime
from unittest import TestCase

from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    DiagnosticReport,
    EvidenceRecord,
    HealthStatus,
)


class ComponentResultTests(TestCase):
    def test_problem_result_keeps_its_evidence(self) -> None:
        evidence = EvidenceRecord(
            source="PowerShell",
            query="Get-PnpDevice -PresentOnly",
            output="USB Mass Storage Device | Error | Código 43",
            collected_at=datetime.now(UTC),
        )

        result = ComponentResult(
            component=ComponentKind.USB,
            name="USB Mass Storage Device",
            facts={"problem_code": 43},
            status=HealthStatus.CRITICAL,
            possible_problem="Driver o configuración",
            evidence=(evidence,),
        )

        self.assertIs(result.status, HealthStatus.CRITICAL)
        self.assertEqual(result.evidence, (evidence,))
        self.assertEqual(result.facts["problem_code"], 43)


class DiagnosticReportTests(TestCase):
    def test_context_fields_are_optional(self) -> None:
        now = datetime.now(UTC)
        report = DiagnosticReport(
            started_at=now,
            completed_at=now,
            results=(),
            conclusion="Sin datos.",
        )

        self.assertIsNone(report.symptom)
        self.assertIsNone(report.expected_device)
        self.assertFalse(report.has_problems)

    def test_context_fields_round_trip(self) -> None:
        now = datetime.now(UTC)
        report = DiagnosticReport(
            started_at=now,
            completed_at=now,
            results=(),
            conclusion="Sin anomalías.",
            symptom="el equipo se reinicia al jugar",
            expected_device="SSD M.2",
        )

        self.assertEqual(report.symptom, "el equipo se reinicia al jugar")
        self.assertEqual(report.expected_device, "SSD M.2")
