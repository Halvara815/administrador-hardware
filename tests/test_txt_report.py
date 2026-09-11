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
from hardware_admin.reports.txt_report import export_txt, render_text


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
        dynamic_name = "Adaptador Wi-Fi S/N: SN-8899 IP 192.168.1.77"
        net_result = ComponentResult(
            component=ComponentKind.NETWORK,
            name=dynamic_name,
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
                "Versión de firmware": "2.1.0",
            },
            summary="1 conectado",
            status=HealthStatus.NORMAL,
        )
        report = DiagnosticReport(
            started_at=datetime(2026, 9, 5, 10, 0, tzinfo=UTC),
            completed_at=datetime(2026, 9, 5, 10, 1, tzinfo=UTC),
            results=(net_result,),
            conclusion="Conexión establecida para 192.168.1.77.",
        )
        text = render_text(report, include_identity=True)
        self.assertNotIn("(omitido)", text)
        self.assertIn(dynamic_name, text)
        self.assertIn("192.168.1.77", text)
        self.assertIn("SN-8899", text)

    def test_text_report_privacy_policy_with_include_identity_false(self) -> None:
        dynamic_name = r"Adaptador Wi-Fi S/N: SN-8899 MAC 3C-52-82-1A-BB-04 en C:\Users\Alice\Net"
        failed_name = r"Fallo PCI en C:\Users\Alice\pci IP 192.168.1.200"
        net_result = ComponentResult(
            component=ComponentKind.NETWORK,
            name=dynamic_name,
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
                "Versión de firmware": "2.1.0",
            },
            summary="1 conectado en C:\\Users\\Alice\\Net",
            status=HealthStatus.NORMAL,
            possible_problem="Error en IP 10.0.0.1",
        )
        err_result = ComponentResult(
            component=ComponentKind.PCI,
            name=failed_name,
            facts={"Resultado": "Fallo"},
            summary="Error PCI",
            status=HealthStatus.ERROR,
            possible_problem="Denegado en C:\\Users\\Alice",
        )
        report = DiagnosticReport(
            started_at=datetime(2026, 9, 5, 10, 0, tzinfo=UTC),
            completed_at=datetime(2026, 9, 5, 10, 1, tzinfo=UTC),
            results=(net_result, err_result),
            conclusion="Conexión establecida en C:\\Users\\Alice y 192.168.1.50.",
            symptom="Fallo en equipo con MAC AA-BB-CC-DD-EE-FF",
            limitations=("Log inaccesible en C:\\Users\\Alice",),
        )
        text = render_text(report, include_identity=False)

        # Confirmar presencia de marcas de anonimización
        self.assertIn("(omitido)", text)
        self.assertIn("[IP-redacted]", text)
        self.assertIn("[MAC-redacted]", text)
        self.assertIn("[serial-redacted]", text)
        self.assertIn(r"C:\Users\<usuario>", text)

        # Ningún dato identificador ni de nombre de componente debe filtrarse en el texto renderizado
        self.assertNotIn("Alice", text)
        self.assertNotIn("SN-8899", text)
        self.assertNotIn("3C-52-82-1A-BB-04", text)
        self.assertNotIn("AA-BB-CC-DD-EE-FF", text)
        self.assertNotIn("192.168.1.77", text)
        self.assertNotIn("192.168.1.50", text)
        self.assertNotIn("192.168.1.200", text)
        self.assertNotIn("10.0.0.1", text)

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
