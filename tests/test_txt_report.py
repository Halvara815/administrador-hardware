"""Pruebas del reporte de texto plano."""

from tempfile import TemporaryDirectory
from unittest import TestCase

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

    def test_the_file_is_written_as_utf8(self) -> None:
        """Los acentos deben sobrevivir al guardado."""
        with TemporaryDirectory() as directory:
            path = export_txt(sample_report(), f"{directory}/reporte.txt")
            content = path.read_text(encoding="utf-8")

        self.assertIn("CONCLUSIÓN", content)
        self.assertIn("Carga elevada de CPU.", content)
