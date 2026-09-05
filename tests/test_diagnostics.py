from datetime import UTC, datetime
from unittest import TestCase

from hardware_admin.diagnostics.engine import RuleBasedDiagnosticEngine
from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    EvidenceRecord,
    HealthStatus,
)


def result_for(
    component: ComponentKind,
    status: HealthStatus,
    summary: str,
    problem: str | None = None,
) -> ComponentResult:
    return ComponentResult(
        component=component,
        name="USB" if component is ComponentKind.USB else component.value,
        facts={},
        summary=summary,
        status=status,
        possible_problem=problem,
        evidence=(EvidenceRecord("test", "query", "output", datetime.now(UTC)),),
    )


class DiagnosticEngineTests(TestCase):
    def test_memory_is_explained_as_probable_cause_of_slowness(self) -> None:
        report = RuleBasedDiagnosticEngine().build_report(
            (
                result_for(ComponentKind.CPU, HealthStatus.NORMAL, "25% de uso"),
                result_for(
                    ComponentKind.MEMORY,
                    HealthStatus.WARNING,
                    "88% de uso",
                    "Poca memoria disponible",
                ),
                result_for(
                    ComponentKind.USB,
                    HealthStatus.CRITICAL,
                    "1 dispositivo con problema",
                    "Driver o configuración",
                ),
            )
        )

        self.assertIn("causa más probable", report.conclusion)
        self.assertIn("memoria RAM", report.conclusion)
        self.assertIn("USB", report.conclusion)
        self.assertTrue(report.has_problems)

    def test_query_failure_becomes_limitation_not_hardware_problem(self) -> None:
        report = RuleBasedDiagnosticEngine().build_report(
            (
                result_for(
                    ComponentKind.PCI,
                    HealthStatus.ERROR,
                    "Error de consulta",
                    "Permiso insuficiente",
                ),
            )
        )

        self.assertFalse(report.has_problems)
        self.assertEqual(len(report.limitations), 1)
        self.assertIn("no pudieron completarse", report.conclusion)

    def test_final_assignment_scenario_mentions_each_supported_cause(self) -> None:
        report = RuleBasedDiagnosticEngine().build_report(
            (
                result_for(ComponentKind.CPU, HealthStatus.CRITICAL, "95% de uso"),
                result_for(ComponentKind.MEMORY, HealthStatus.WARNING, "92% de uso"),
                result_for(ComponentKind.DISK, HealthStatus.NORMAL, "45% ocupado"),
                result_for(
                    ComponentKind.USB,
                    HealthStatus.CRITICAL,
                    "Código 43",
                    "Driver/configuración",
                ),
                result_for(
                    ComponentKind.MONITOR_GPU,
                    HealthStatus.CRITICAL,
                    "Error de controlador",
                    "Controlador gráfico",
                ),
            )
        )

        self.assertIn("CPU (95% de uso)", report.conclusion)
        self.assertIn("memoria RAM (92% de uso)", report.conclusion)
        self.assertIn("USB", report.conclusion)
        self.assertIn("monitor_gpu", report.conclusion)

    def test_error_is_not_a_hardware_problem_but_critical_is(self) -> None:
        error_report = RuleBasedDiagnosticEngine().build_report(
            (result_for(ComponentKind.PCI, HealthStatus.ERROR, "Error de consulta"),)
        )
        critical_report = RuleBasedDiagnosticEngine().build_report(
            (result_for(ComponentKind.PCI, HealthStatus.CRITICAL, "Código 43"),)
        )

        self.assertFalse(error_report.has_problems)
        self.assertTrue(critical_report.has_problems)

    def test_all_ok_with_persistent_symptom_forces_deeper_diagnosis(self) -> None:
        report = RuleBasedDiagnosticEngine().build_report(
            (
                result_for(ComponentKind.CPU, HealthStatus.NORMAL, "35% de uso"),
                result_for(ComponentKind.MEMORY, HealthStatus.NORMAL, "42% de uso"),
                result_for(ComponentKind.DISK, HealthStatus.NORMAL, "55% ocupado"),
                result_for(ComponentKind.MONITOR_GPU, HealthStatus.NORMAL, "GPU OK"),
            ),
            symptom="el equipo se reinicia al jugar",
        )

        self.assertFalse(report.has_problems)
        self.assertEqual(report.symptom, "el equipo se reinicia al jugar")
        self.assertIn("sin anomalías básicas", report.conclusion)
        self.assertIn("temperatura", report.conclusion)
        self.assertIn("fuente de alimentación", report.conclusion)
        self.assertIn("GPU", report.conclusion)

    def test_symptom_without_anomalies_uses_precise_wording(self) -> None:
        report = RuleBasedDiagnosticEngine().build_report(
            (result_for(ComponentKind.SYSTEM, HealthStatus.NORMAL, "Sistema OK"),)
        )

        self.assertIn("No se observan anomalías en los indicadores consultados", report.conclusion)
        self.assertNotIn("sin problemas", report.conclusion)
