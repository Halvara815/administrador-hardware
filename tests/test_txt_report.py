from datetime import UTC, datetime
from tempfile import TemporaryDirectory
from unittest import TestCase

from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    DiagnosticReport,
    HealthStatus,
)
from hardware_admin.reports.txt_report import export_txt, render_text
from tests.test_json_report import sample_report


class TxtReportTests(TestCase):
    def test_the_text_carries_the_contract_sections(self) -> None:
        text = render_text(sample_report())

        for heading in (
            "REPORTE DE DIAGNÓSTICO",
            "MATRIZ DE DIAGNÓSTICO",
            "CONCLUSIÓN",
            "RECOMENDACIONES",
            "LIMITACIONES",
            "COBERTURA",
        ):
            self.assertIn(heading, text)

    def test_query_failures_are_not_presented_as_healthy(self) -> None:
        text = render_text(sample_report())

        self.assertIn("no equivale a ausencia de problemas", text)

    def test_procedures_that_alter_the_machine_are_marked(self) -> None:
        text = render_text(sample_report())

        self.assertIn("Revisar la carga del procesador", text)
        self.assertIn("Sólo consulta", text)

    def test_identity_can_be_omitted(self) -> None:
        text = render_text(sample_report(), include_identity=False)

        self.assertIn("(omitido)", text)

    def test_text_report_preserves_facts_with_include_identity_true(self) -> None:
        net_result = ComponentResult(
            component=ComponentKind.NETWORK,
            name="Red",
            facts={
                "Adaptadores": [
                    {
                        "Adaptador": "Wi-Fi",
                        "MAC": "3C-52-82-1A-BB-04",
                        "IPv4": "192.168.1.77",
                        "Puerta de enlace": "192.168.1.1",
                        "Servidores DNS": "1.1.1.1, 8.8.8.8",
                        "Máscara de subred": "255.255.255.0",
                    }
                ],
                "Versión de firmware": "1.0.0.1",
            },
            summary="1 conectado",
            status=HealthStatus.NORMAL,
        )
        report = DiagnosticReport(
            started_at=datetime(2026, 9, 5, 10, 0, tzinfo=UTC),
            completed_at=datetime(2026, 9, 5, 10, 1, tzinfo=UTC),
            results=(net_result,),
            conclusion="Conexión establecida.",
        )
        text = render_text(report, include_identity=True)
        self.assertNotIn("(omitido)", text)

    def test_text_report_privacy_policy_with_include_identity_false(self) -> None:
        net_result = ComponentResult(
            component=ComponentKind.NETWORK,
            name="Red",
            facts={
                "Adaptadores": [
                    {
                        "Adaptador": "Wi-Fi",
                        "MAC": "3C-52-82-1A-BB-04",
                        "IPv4": "192.168.1.77",
                        "Puerta de enlace": "192.168.1.1",
                        "Servidores DNS": "1.1.1.1, 8.8.8.8",
                        "Máscara de subred": "255.255.255.0",
                    }
                ],
                "Versión de firmware": "1.0.0.1",
            },
            summary="1 conectado",
            status=HealthStatus.NORMAL,
        )
        report = DiagnosticReport(
            started_at=datetime(2026, 9, 5, 10, 0, tzinfo=UTC),
            completed_at=datetime(2026, 9, 5, 10, 1, tzinfo=UTC),
            results=(net_result,),
            conclusion="Conexión establecida.",
        )
        text = render_text(report, include_identity=False)
        self.assertIn("(omitido)", text)

    def test_txt_export_does_not_raise_re_error(self) -> None:
        report = sample_report()
        with TemporaryDirectory() as directory:
            path = export_txt(report, f"{directory}/export.txt")
            self.assertTrue(path.exists())
            content = path.read_text(encoding="utf-8")
            self.assertIn("REPORTE DE DIAGNÓSTICO", content)

    def test_the_file_is_written_as_utf8(self) -> None:
        """Los acentos deben sobrevivir al guardado."""
        with TemporaryDirectory() as directory:
            path = export_txt(sample_report(), f"{directory}/reporte.txt")
            content = path.read_text(encoding="utf-8")

        self.assertIn("CONCLUSIÓN", content)
        self.assertIn("Carga elevada de CPU.", content)
