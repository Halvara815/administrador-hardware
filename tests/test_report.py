from datetime import UTC, datetime
from tempfile import TemporaryDirectory
from unittest import TestCase

from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    DiagnosticReport,
    EvidenceRecord,
    HealthStatus,
)
from hardware_admin.reports.html_report import export_html


class HtmlReportTests(TestCase):
    def test_report_contains_matrix_conclusion_and_escaped_evidence(self) -> None:
        now = datetime.now(UTC)
        report = DiagnosticReport(
            started_at=now,
            completed_at=now,
            results=(
                ComponentResult(
                    component=ComponentKind.USB,
                    name="USB",
                    facts={"Estado": "Error"},
                    summary="Código 43",
                    status=HealthStatus.CRITICAL,
                    possible_problem="Driver/configuración",
                    evidence=(EvidenceRecord("test", "query", "<script>", now),),
                ),
            ),
            conclusion="Se detectó un problema USB.",
        )

        with TemporaryDirectory() as directory:
            path = export_html(report, f"{directory}/reporte.html")
            content = path.read_text(encoding="utf-8")

        self.assertIn("Matriz de diagnóstico", content)
        self.assertIn("Se detectó un problema USB.", content)
        self.assertIn("&lt;script&gt;", content)
        self.assertNotIn("<script>", content)

    def test_report_includes_user_symptom_and_expected_device(self) -> None:
        now = datetime.now(UTC)
        report = DiagnosticReport(
            started_at=now,
            completed_at=now,
            results=(),
            conclusion="Sin anomalías en los indicadores consultados.",
            symptom="se reinicia al jugar",
            expected_device="SSD M.2",
        )

        with TemporaryDirectory() as directory:
            path = export_html(report, f"{directory}/reporte.html")
            content = path.read_text(encoding="utf-8")

        self.assertIn("Contexto del usuario", content)
        self.assertIn("se reinicia al jugar", content)
        self.assertIn("SSD M.2", content)

    def test_report_omits_context_section_when_empty(self) -> None:
        now = datetime.now(UTC)
        report = DiagnosticReport(
            started_at=now,
            completed_at=now,
            results=(),
            conclusion="Sin datos.",
        )

        with TemporaryDirectory() as directory:
            path = export_html(report, f"{directory}/reporte.html")
            content = path.read_text(encoding="utf-8")

        self.assertNotIn("Contexto del usuario", content)


class MachineReadableFactsTests(TestCase):
    def test_underscored_keys_are_series_for_charts_not_report_text(self) -> None:
        """Las claves con _ son datos para graficar: no deben salir en el reporte."""
        result = ComponentResult(
            component=ComponentKind.CPU,
            name="CPU",
            facts={"Uso": "42.0%", "_uso": 42.0, "_nucleos": [10.0, 74.0]},
            summary="42% de uso",
            status=HealthStatus.NORMAL,
            evidence=(EvidenceRecord("psutil", "cpu", "salida", datetime.now(UTC)),),
        )
        report = DiagnosticReport(
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            results=(result,),
            conclusion="Sin anomalías en los indicadores consultados.",
        )

        with TemporaryDirectory() as directory:
            path = export_html(report, f"{directory}/reporte.html")
            html_text = path.read_text(encoding="utf-8")

        self.assertIn("Uso", html_text)
        self.assertIn("42.0%", html_text)
        self.assertNotIn("_uso", html_text)
        self.assertNotIn("_nucleos", html_text)
