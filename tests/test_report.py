from datetime import UTC, datetime
from tempfile import TemporaryDirectory
from unittest import TestCase

from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    DiagnosticReport,
    EvidenceRecord,
    HealthStatus,
    Recommendation,
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


class RecommendationSectionTests(TestCase):
    def _report_with(self, *recommendations: Recommendation) -> str:
        report = DiagnosticReport(
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            results=(
                ComponentResult(
                    component=ComponentKind.CPU,
                    name="CPU",
                    facts={"Uso": "98.0%"},
                    summary="98% de uso",
                    status=HealthStatus.CRITICAL,
                    evidence=(EvidenceRecord("psutil", "cpu", "salida", datetime.now(UTC)),),
                ),
            ),
            conclusion="Carga elevada.",
            recommendations=recommendations,
        )
        with TemporaryDirectory() as directory:
            return export_html(report, f"{directory}/reporte.html").read_text(encoding="utf-8")

    def test_the_report_lists_steps_cause_rationale_and_verification(self) -> None:
        html_text = self._report_with(
            Recommendation(
                component=ComponentKind.CPU,
                title="Revisar la carga del procesador",
                cause="El uso de CPU está en 98%.",
                steps=("Abrir el Administrador de tareas.", "Ordenar por CPU."),
                rationale="Una carga sostenida degrada la respuesta.",
                verification="Repetir el análisis.",
            )
        )

        self.assertIn("Revisar la carga del procesador", html_text)
        self.assertIn("Abrir el Administrador de tareas.", html_text)
        self.assertIn("Ordenar por CPU.", html_text)
        self.assertIn("Una carga sostenida degrada la respuesta.", html_text)
        self.assertIn("Repetir el análisis.", html_text)

    def test_procedures_that_alter_the_machine_are_marked_in_the_report(self) -> None:
        """El lector debe ver qué va a cambiar antes de escribir el comando."""
        html_text = self._report_with(
            Recommendation(
                component=ComponentKind.NETWORK,
                title="Recuperar la concesión DHCP",
                cause="Dirección APIPA.",
                steps=("Ejecutar «ipconfig /renew».",),
                rationale="No respondió ningún DHCP.",
                verification="Comprobar que obtiene IP.",
                modifies_system=True,
            )
        )

        self.assertIn("Modifica el sistema", html_text)

    def test_a_report_without_recommendations_omits_the_section(self) -> None:
        self.assertNotIn("Recomendaciones", self._report_with())

    def test_recommendation_content_is_escaped(self) -> None:
        """El contenido se escapa: nada de HTML crudo en el reporte."""
        html_text = self._report_with(
            Recommendation(
                component=ComponentKind.CPU,
                title="<script>alert(1)</script>",
                cause="causa",
                steps=("paso",),
                rationale="fundamento",
                verification="comprobación",
            )
        )

        self.assertNotIn("<script>alert(1)</script>", html_text)
        self.assertIn("&lt;script&gt;", html_text)
