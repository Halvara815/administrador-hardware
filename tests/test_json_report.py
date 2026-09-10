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
from hardware_admin.reports.json_report import (
    SCHEMA_VERSION,
    _redact,
    build_payload,
    export_json,
)


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


    def test_redact_removes_personal_data_and_keeps_markers(self) -> None:
        raw = (
            r"Ruta Windows C:\Users\Alice\app.log y C:/Users/Alice/data, "
            "MAC 3C-52-82-1A-BB-04, IP 192.168.1.77"
        )
        redacted = _redact(raw)

        self.assertNotIn("Alice", redacted)
        self.assertNotIn("3C-52-82-1A-BB-04", redacted)
        self.assertNotIn("192.168.1.77", redacted)
        self.assertIn(r"C:\Users\<usuario>", redacted)
        self.assertIn("C:/Users/<usuario>", redacted)
        self.assertIn("[MAC-redacted]", redacted)
        self.assertIn("[IP-redacted]", redacted)

    def test_payload_preserves_technical_facts_when_include_identity_true(self) -> None:
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
        payload = build_payload(report, include_identity=True)
        adapter = payload["resultados"][0]["datos"]["Adaptadores"][0]

        self.assertEqual(adapter["MAC"], "3C-52-82-1A-BB-04")
        self.assertEqual(adapter["IPv4"], "192.168.1.77")
        self.assertEqual(adapter["Puerta de enlace"], "192.168.1.1")
        self.assertEqual(adapter["Servidores DNS"], "1.1.1.1, 8.8.8.8")
        self.assertEqual(adapter["Máscara de subred"], "255.255.255.0")
        self.assertEqual(payload["resultados"][0]["datos"]["Versión de firmware"], "1.0.0.1")

    def test_payload_redacts_identity_facts_but_preserves_mask_and_firmware_when_include_identity_false(self) -> None:
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
                "Ruta": r"C:\Users\Alice\AppData\Local\log.txt",
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
        payload = build_payload(report, include_identity=False)
        datos = payload["resultados"][0]["datos"]
        adapter = datos["Adaptadores"][0]

        self.assertEqual(adapter["MAC"], "[MAC-redacted]")
        self.assertEqual(adapter["IPv4"], "[IP-redacted]")
        self.assertEqual(adapter["Puerta de enlace"], "[IP-redacted]")
        self.assertEqual(adapter["Servidores DNS"], "[IP-redacted], [IP-redacted]")
        self.assertEqual(adapter["Máscara de subred"], "255.255.255.0")
        self.assertEqual(datos["Versión de firmware"], "1.0.0.1")
        self.assertIn(r"C:\Users\<usuario>", datos["Ruta"])
        self.assertNotIn("Alice", datos["Ruta"])


class JsonExportTests(TestCase):
    def test_json_export_does_not_raise_re_error(self) -> None:
        report = sample_report()
        with TemporaryDirectory() as directory:
            path = export_json(report, f"{directory}/export.json")
            self.assertTrue(path.exists())
            content = path.read_text(encoding="utf-8")
            self.assertIn("CPU", content)

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


class ExportLoggingTests(TestCase):
    """Observabilidad: «resultado y ruta final de exportación, sin el contenido»."""

    def test_json_export_logs_result_and_path(self) -> None:
        with TemporaryDirectory() as directory:
            destino = f"{directory}/reporte.json"
            with self.assertLogs("hardware_admin.reports", "INFO") as registro:
                export_json(sample_report(), destino)

        linea = " ".join(registro.output)
        self.assertIn("report_exported", linea)
        self.assertIn("format=json", linea)
        self.assertIn("reporte.json", linea)

    def test_the_log_records_whether_identity_was_included(self) -> None:
        with (
            TemporaryDirectory() as directory,
            self.assertLogs("hardware_admin.reports", "INFO") as registro,
        ):
            export_json(sample_report(), f"{directory}/r.json", include_identity=False)

        self.assertIn("identity=omitted", " ".join(registro.output))

    def test_the_log_never_carries_the_report_content(self) -> None:
        """Se registra la ruta y el resultado, nunca lo que contiene el reporte."""
        with (
            TemporaryDirectory() as directory,
            self.assertLogs("hardware_admin.reports", "INFO") as registro,
        ):
            export_json(sample_report(), f"{directory}/r.json")

        linea = " ".join(registro.output)
        self.assertNotIn("Carga elevada de CPU", linea)
        self.assertNotIn("se reinicia al jugar", linea)
