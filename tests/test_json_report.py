"""Pruebas del reporte JSON: esquema completo, UTF-8 y opcion de anonimizar."""

import json
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
from hardware_admin.reports.json_report import SCHEMA_VERSION, build_payload, export_json


def sample_report() -> DiagnosticReport:
    ok = ComponentResult(
        component=ComponentKind.CPU,
        name="CPU",
        facts={"Uso": "97.0%", "_uso": 97.0},
        summary="97% de uso",
        status=HealthStatus.CRITICAL,
        possible_problem="Carga elevada del procesador",
        evidence=(EvidenceRecord("psutil", "cpu_percent", "97.0", datetime.now(UTC)),),
    )
    failed = ComponentResult(
        component=ComponentKind.PCI,
        name="PCI / PCIe",
        facts={"Resultado": "No disponible"},
        summary="No disponible",
        status=HealthStatus.ERROR,
        possible_problem="Permiso denegado",
        evidence=(EvidenceRecord("PowerShell", "pci", "denegado", datetime.now(UTC), False),),
    )
    return DiagnosticReport(
        started_at=datetime(2026, 9, 5, 10, 0, tzinfo=UTC),
        completed_at=datetime(2026, 9, 5, 10, 1, tzinfo=UTC),
        results=(ok, failed),
        conclusion="Carga elevada de CPU.",
        limitations=("PCI / PCIe: Permiso denegado",),
        symptom="se reinicia al jugar",
        recommendations=(
            Recommendation(
                component=ComponentKind.CPU,
                title="Revisar la carga del procesador",
                cause="Uso al 97%.",
                steps=("Abrir el Administrador de tareas.",),
                rationale="Una carga sostenida degrada la respuesta.",
                verification="Repetir el análisis.",
            ),
        ),
    )


class JsonSchemaTests(TestCase):
    def test_the_payload_carries_every_field_the_plan_requires(self) -> None:
        payload = build_payload(sample_report())

        for key in (
            "schema_version",
            "app_version",
            "generated_at",
            "equipo",
            "usuario",
            "sistema_operativo",
            "resultados",
            "errores_de_consulta",
            "recomendaciones",
            "conclusion",
            "cobertura",
            "limitaciones",
        ):
            self.assertIn(key, payload, f"falta el campo {key!r} del contrato")

    def test_schema_version_allows_detecting_old_exports(self) -> None:
        self.assertEqual(build_payload(sample_report())["schema_version"], SCHEMA_VERSION)

    def test_query_failures_are_separated_from_hardware_findings(self) -> None:
        """Un ERROR de consulta no es un hallazgo de hardware."""
        payload = build_payload(sample_report())

        errores = payload["errores_de_consulta"]
        self.assertEqual(len(errores), 1)
        self.assertEqual(errores[0]["componente"], "pci")
        estados = [item["estado"] for item in payload["resultados"]]
        self.assertIn("error", estados)

    def test_coverage_reports_what_was_consulted_and_what_failed(self) -> None:
        cobertura = build_payload(sample_report())["cobertura"]

        self.assertEqual(cobertura["componentes_consultados"], 2)
        self.assertEqual(cobertura["consultas_fallidas"], 1)

    def test_recommendations_declare_whether_they_alter_the_machine(self) -> None:
        recomendacion = build_payload(sample_report())["recomendaciones"][0]

        self.assertIn("modifica_el_sistema", recomendacion)
        self.assertFalse(recomendacion["modifica_el_sistema"])
        self.assertEqual(recomendacion["pasos"], ["Abrir el Administrador de tareas."])


class JsonPrivacyTests(TestCase):
    def test_identity_can_be_omitted_for_shared_copies(self) -> None:
        """El plan pide poder omitir equipo y usuario al compartir el reporte."""
        payload = build_payload(sample_report(), include_identity=False)

        self.assertEqual(payload["equipo"], "(omitido)")
        self.assertEqual(payload["usuario"], "(omitido)")

    def test_identity_is_included_by_default(self) -> None:
        payload = build_payload(sample_report())

        self.assertNotEqual(payload["equipo"], "(omitido)")


class JsonExportTests(TestCase):
    def test_the_file_is_written_as_utf8_and_parses_back(self) -> None:
        with TemporaryDirectory() as directory:
            path = export_json(sample_report(), f"{directory}/reporte.json")
            parsed = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(parsed["conclusion"], "Carga elevada de CPU.")
        self.assertEqual(parsed["contexto"]["sintoma"], "se reinicia al jugar")

    def test_chart_series_do_not_bloat_the_export(self) -> None:
        """Las claves con _ son para dibujar; no son datos del reporte."""
        payload = build_payload(sample_report())
        datos = payload["resultados"][0]["datos"]

        self.assertIn("Uso", datos)
        self.assertNotIn("_uso", datos)
