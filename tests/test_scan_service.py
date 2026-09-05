from unittest import TestCase

from hardware_admin.diagnostics.engine import RuleBasedDiagnosticEngine
from hardware_admin.domain.models import ComponentKind, ComponentResult, HealthStatus
from hardware_admin.services.scan_service import ScanService


class GoodCollector:
    component = ComponentKind.CPU

    def collect(self) -> ComponentResult:
        return ComponentResult(
            component=self.component,
            name="CPU",
            facts={"Uso": "10%"},
            summary="10% de uso",
            status=HealthStatus.NORMAL,
        )


class BrokenCollector:
    component = ComponentKind.USB

    def collect(self) -> ComponentResult:
        raise RuntimeError("consulta simulada fallida")


class ScanServiceTests(TestCase):
    def test_a_broken_collector_does_not_discard_successful_results(self) -> None:
        progress: list[tuple[int, int, str]] = []
        service = ScanService(
            collectors=(GoodCollector(), BrokenCollector()),
            diagnostic_engine=RuleBasedDiagnosticEngine(),
        )

        report = service.scan(lambda current, total, name: progress.append((current, total, name)))

        self.assertEqual(len(report.results), 2)
        self.assertEqual(report.results[0].status, HealthStatus.NORMAL)
        self.assertEqual(report.results[1].status, HealthStatus.ERROR)
        self.assertEqual(progress[-1][:2], (2, 2))

    def test_only_restricts_the_scan_to_the_requested_components(self) -> None:
        progress: list[tuple[int, int, str]] = []
        service = ScanService(
            collectors=(GoodCollector(), BrokenCollector()),
            diagnostic_engine=RuleBasedDiagnosticEngine(),
        )

        report = service.scan(
            lambda current, total, name: progress.append((current, total, name)),
            only=frozenset({ComponentKind.CPU}),
        )

        self.assertEqual([result.component for result in report.results], [ComponentKind.CPU])
        self.assertEqual(progress, [(1, 1, "CPU")])

    def test_scanning_an_unknown_component_yields_an_empty_report(self) -> None:
        service = ScanService(
            collectors=(GoodCollector(),),
            diagnostic_engine=RuleBasedDiagnosticEngine(),
        )

        report = service.scan(only=frozenset({ComponentKind.DISK}))

        self.assertEqual(report.results, ())

    def test_symptom_is_kept_in_the_final_report(self) -> None:
        service = ScanService(
            collectors=(GoodCollector(),),
            diagnostic_engine=RuleBasedDiagnosticEngine(),
        )

        report = service.scan(symptom="se reinicia al jugar", expected_device="SSD")

        self.assertEqual(report.symptom, "se reinicia al jugar")
        self.assertEqual(report.expected_device, "SSD")
        self.assertIn("diagnóstico adicional", report.conclusion)
