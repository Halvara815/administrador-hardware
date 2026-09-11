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
                "Versión de firmware": "2.4.0-build1",
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
        self.assertEqual(datos["Versión de firmware"], "2.4.0-build1")
        self.assertIn(r"C:\Users\<usuario>", datos["Ruta"])
        self.assertNotIn("Alice", datos["Ruta"])

    def test_contract_network_masks_and_versions_sanitization_rules(self) -> None:
        """Prueba de contrato específica:

        - 'driver_version: 10.0.19041.1' -> conservar.
        - 'firmware: 192.168.1.1' -> redactar.
        - 'version: 1.0.0.1' -> redactar.
        - 'Versión del gateway: 192.168.1.1' -> redactar.
        - 'Máscara: 255.255.255.0' -> conservar.
        - 'Subnet mask: 255.255.0.0' -> conservar.
        - 'Máscara del gateway: 192.168.1.1' -> redactar.
        """
        net_result = ComponentResult(
            component=ComponentKind.NETWORK,
            name="Red",
            facts={
                "driver_version": "10.0.19041.1",
                "firmware": "192.168.1.1",
                "version": "1.0.0.1",
                "Versión del gateway": "192.168.1.1",
                "Máscara": "255.255.255.0",
                "Subnet mask": "255.255.0.0",
                "Máscara del gateway": "192.168.1.1",
                "invalid_mask_host": "10.0.0.1",
                "mask_with_host_ip": "172.16.0.5",
                "bios_version": "2.20.0",
                "Versión de firmware": "2.4.0-build1",
            },
            summary="Prueba de máscaras y versiones",
            status=HealthStatus.NORMAL,
        )
        report = DiagnosticReport(
            started_at=datetime(2026, 9, 5, 10, 0, tzinfo=UTC),
            completed_at=datetime(2026, 9, 5, 10, 1, tzinfo=UTC),
            results=(net_result,),
            conclusion="Validación de contrato.",
        )
        payload = build_payload(report, include_identity=False)
        datos = payload["resultados"][0]["datos"]

        # 1. Versiones reales permitidas que no son IPv4 válidas se conservan
        self.assertEqual(datos["driver_version"], "10.0.19041.1")
        self.assertEqual(datos["bios_version"], "2.20.0")
        self.assertEqual(datos["Versión de firmware"], "2.4.0-build1")

        # 2. Una cadena que sea una IPv4 válida se redacta SIEMPRE, incluso en claves de versión
        self.assertEqual(datos["firmware"], "[IP-redacted]")
        self.assertEqual(datos["version"], "[IP-redacted]")
        self.assertEqual(datos["Versión del gateway"], "[IP-redacted]")

        # 3. Máscaras de red matemáticamente válidas se conservan
        self.assertEqual(datos["Máscara"], "255.255.255.0")
        self.assertEqual(datos["Subnet mask"], "255.255.0.0")

        # 4. Claves que contienen 'máscara' / 'mask' pero contienen IPs no válidas como máscara se redactan
        self.assertEqual(datos["Máscara del gateway"], "[IP-redacted]")
        self.assertEqual(datos["invalid_mask_host"], "[IP-redacted]")
        self.assertEqual(datos["mask_with_host_ip"], "[IP-redacted]")

    def test_anonymous_export_sanitizes_all_contract_fields_and_omits_evidence(self) -> None:
        """Verifica que include_identity=False sanitiza todos los campos y omite salida de evidencia."""
        result = ComponentResult(
            component=ComponentKind.DISK,
            name="Disco C:",
            facts={
                "Modelo": "Samsung SSD 980 S/N: ABC12345",
                "Versión del gateway": "192.168.1.1",  # No debe salvarse por pseudo-versión
                "firmware_version": "2.1.0",
                "Máscara": "255.255.0.0",
            },
            summary="Espacio bajo en C:\\Users\\Alice\\AppData",
            status=HealthStatus.WARNING,
            possible_problem="Fallo en host 192.168.1.50 con MAC 00:1A:2B:3C:4D:5E",
            evidence=(
                EvidenceRecord(
                    source="PowerShell",
                    query="Get-PhysicalDisk",
                    output="Disk SerialNumber: SN-998877 at C:\\Users\\Alice",
                    collected_at=datetime(2026, 9, 5, 10, 0, tzinfo=UTC),
                    succeeded=True,
                ),
            ),
        )
        report = DiagnosticReport(
            started_at=datetime(2026, 9, 5, 10, 0, tzinfo=UTC),
            completed_at=datetime(2026, 9, 5, 10, 1, tzinfo=UTC),
            results=(result,),
            conclusion="Alerta en equipo con IP 10.0.0.5 en C:\\Users\\Alice",
            limitations=("No se pudo leer C:\\Users\\Alice\\secret.log",),
            symptom="Problema con usuario en C:\\Users\\Alice",
            expected_device="Dispositivo MAC 11-22-33-44-55-66",
            recommendations=(
                Recommendation(
                    component=ComponentKind.DISK,
                    title="Limpiar carpeta de C:\\Users\\Alice",
                    cause="Lleno por 192.168.1.99",
                    steps=("Borrar C:\\Users\\Alice\\temp", "Comprobar 192.168.1.100"),
                    rationale="Afecta a C:\\Users\\Alice en 192.168.1.101",
                    verification="Verificar IP 192.168.1.102",
                ),
            ),
        )

        payload = build_payload(report, include_identity=False)

        # 1. Metadatos
        self.assertEqual(payload["equipo"], "(omitido)")
        self.assertEqual(payload["usuario"], "(omitido)")

        # 2. Contexto
        self.assertNotIn("Alice", payload["contexto"]["sintoma"])
        self.assertIn(r"C:\Users\<usuario>", payload["contexto"]["sintoma"])
        self.assertNotIn("11-22-33-44-55-66", payload["contexto"]["dispositivo_esperado"])
        self.assertIn("[MAC-redacted]", payload["contexto"]["dispositivo_esperado"])

        # 3. Resultados & Evidencia
        res = payload["resultados"][0]
        self.assertNotIn("Alice", res["resumen"])
        self.assertIn(r"C:\Users\<usuario>", res["resumen"])
        self.assertNotIn("192.168.1.50", res["posible_problema"])
        self.assertNotIn("00:1A:2B:3C:4D:5E", res["posible_problema"])
        self.assertIn("[IP-redacted]", res["posible_problema"])
        self.assertIn("[MAC-redacted]", res["posible_problema"])

        # Evidencia: salida obligatoriamente "(omitido)"
        ev = res["evidencia"][0]
        self.assertEqual(ev["salida"], "(omitido)")
        self.assertEqual(ev["fuente"], "PowerShell")
        self.assertEqual(ev["consulta"], "Get-PhysicalDisk")
        self.assertTrue(ev["exito"])

        # Datos
        datos = res["datos"]
        self.assertNotIn("ABC12345", datos["Modelo"])
        self.assertIn("[serial-redacted]", datos["Modelo"])
        self.assertEqual(datos["Versión del gateway"], "[IP-redacted]")
        self.assertEqual(datos["firmware_version"], "2.1.0")
        self.assertEqual(datos["Máscara"], "255.255.0.0")

        # 4. Recomendaciones
        rec = payload["recomendaciones"][0]
        self.assertNotIn("Alice", rec["titulo"])
        self.assertIn(r"C:\Users\<usuario>", rec["titulo"])
        self.assertNotIn("192.168.1.99", rec["causa"])
        self.assertNotIn("Alice", rec["pasos"][0])
        self.assertNotIn("192.168.1.100", rec["pasos"][1])
        self.assertNotIn("Alice", rec["fundamento"])
        self.assertNotIn("192.168.1.101", rec["fundamento"])
        self.assertNotIn("192.168.1.102", rec["comprobacion_posterior"])

        # 5. Conclusión y limitaciones
        self.assertNotIn("Alice", payload["conclusion"])
        self.assertNotIn("10.0.0.5", payload["conclusion"])
        self.assertIn("[IP-redacted]", payload["conclusion"])
        self.assertNotIn("Alice", payload["limitaciones"][0])
        self.assertIn(r"C:\Users\<usuario>", payload["limitaciones"][0])

    def test_regression_raw_evidence_or_unsanitized_fields_fail(self) -> None:
        """Regresión: si la evidencia cruda o campos de texto se filtran sin sanitizar, la prueba falla."""
        result = ComponentResult(
            component=ComponentKind.SYSTEM,
            name="Sistema",
            facts={"Ruta": r"C:\Users\SecretUser\doc.txt"},
            summary="Ruta activa: C:\\Users\\SecretUser\\AppData",
            status=HealthStatus.NORMAL,
            evidence=(
                EvidenceRecord(
                    source="WMI",
                    query="Win32_UserAccount",
                    output="Name: SecretUser, SID: S-1-5-21-...",
                    collected_at=datetime.now(UTC),
                ),
            ),
        )
        report = DiagnosticReport(
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            results=(result,),
            conclusion="Reporte generado para C:\\Users\\SecretUser",
        )
        payload = build_payload(report, include_identity=False)
        json_str = json.dumps(payload)

        self.assertNotIn("SecretUser", json_str)
        self.assertNotIn("SID: S-1-5-21-...", json_str)

    def test_component_result_name_sanitization_in_resultados_and_errores(self) -> None:
        """Verifica que el nombre dinámico del componente se sanitiza en modo anónimo y se conserva con identidad."""
        dynamic_name = (
            r"Disco S/N: WD-998877 MAC 00-11-22-33-44-55 IP 192.168.1.15 en C:\Users\veget\data"
        )
        ok_result = ComponentResult(
            component=ComponentKind.DISK,
            name=dynamic_name,
            facts={"Estado": "OK"},
            summary="Disco operativo",
            status=HealthStatus.NORMAL,
        )
        err_result = ComponentResult(
            component=ComponentKind.NETWORK,
            name=dynamic_name,
            facts={"Estado": "Fallo"},
            summary="Error de adaptador",
            status=HealthStatus.ERROR,
            possible_problem="Consulta fallida en 192.168.1.15",
        )
        report = DiagnosticReport(
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            results=(ok_result, err_result),
            conclusion="Diagnóstico con nombres dinámicos.",
        )

        # 1. Modo con identidad: conserva el nombre original íntegro
        payload_private = build_payload(report, include_identity=True)
        self.assertEqual(payload_private["resultados"][0]["nombre"], dynamic_name)
        self.assertEqual(payload_private["resultados"][1]["nombre"], dynamic_name)
        self.assertEqual(payload_private["errores_de_consulta"][0]["nombre"], dynamic_name)

        # 2. Modo anónimo: sanitiza nombre en resultados y errores_de_consulta
        payload_anon = build_payload(report, include_identity=False)
        for res in payload_anon["resultados"]:
            self.assertNotIn("WD-998877", res["nombre"])
            self.assertNotIn("00-11-22-33-44-55", res["nombre"])
            self.assertNotIn("192.168.1.15", res["nombre"])
            self.assertNotIn("veget", res["nombre"])
            self.assertIn("[serial-redacted]", res["nombre"])
            self.assertIn("[MAC-redacted]", res["nombre"])
            self.assertIn("[IP-redacted]", res["nombre"])
            self.assertIn(r"C:\Users\<usuario>", res["nombre"])

        err_item = payload_anon["errores_de_consulta"][0]
        self.assertNotIn("WD-998877", err_item["nombre"])
        self.assertNotIn("00-11-22-33-44-55", err_item["nombre"])
        self.assertNotIn("192.168.1.15", err_item["nombre"])
        self.assertNotIn("veget", err_item["nombre"])
        self.assertIn("[serial-redacted]", err_item["nombre"])
        self.assertIn("[MAC-redacted]", err_item["nombre"])
        self.assertIn("[IP-redacted]", err_item["nombre"])
        self.assertIn(r"C:\Users\<usuario>", err_item["nombre"])


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
