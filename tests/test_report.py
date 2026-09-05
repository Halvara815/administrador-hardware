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
