from datetime import UTC, datetime
from unittest import TestCase

from hardware_admin.diagnostics.engine import RuleBasedDiagnosticEngine
from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    EvidenceRecord,
    HealthStatus,
)


def result_for(
    component: ComponentKind,
    status: HealthStatus,
    summary: str,
    problem: str | None = None,
) -> ComponentResult:
    return ComponentResult(
        component=component,
        name="USB" if component is ComponentKind.USB else component.value,
        facts={},
        summary=summary,
        status=status,
        possible_problem=problem,
        evidence=(EvidenceRecord("test", "query", "output", datetime.now(UTC)),),
    )


class DiagnosticEngineTests(TestCase):
    def test_memory_is_explained_as_probable_cause_of_slowness(self) -> None:
        report = RuleBasedDiagnosticEngine().build_report(
            (
                result_for(ComponentKind.CPU, HealthStatus.NORMAL, "25% de uso"),
                result_for(
                    ComponentKind.MEMORY,
                    HealthStatus.WARNING,
                    "88% de uso",
                    "Poca memoria disponible",
                ),
                result_for(
                    ComponentKind.USB,
                    HealthStatus.CRITICAL,
                    "1 dispositivo con problema",
                    "Driver o configuración",
                ),
            )
        )

        self.assertIn("causa más probable", report.conclusion)
        self.assertIn("memoria RAM", report.conclusion)
        self.assertIn("USB", report.conclusion)
        self.assertTrue(report.has_problems)

    def test_cpu_alone_is_explained_as_probable_cause_of_slowness(self) -> None:
        """Caso «CPU individual» del plan: CPU98/RAM52/disco30 -> carga de CPU alta."""
        report = RuleBasedDiagnosticEngine().build_report(
            (
                result_for(ComponentKind.CPU, HealthStatus.CRITICAL, "98% de uso", "Carga elevada"),
                result_for(ComponentKind.MEMORY, HealthStatus.NORMAL, "52% de uso"),
                result_for(ComponentKind.DISK, HealthStatus.NORMAL, "30% ocupado"),
            )
        )

        self.assertTrue(report.has_problems)
        self.assertIn("carga de CPU", report.conclusion)
        self.assertIn("98% de uso", report.conclusion)
        self.assertNotIn("memoria RAM", report.conclusion)

    def test_case_c4_cpu_and_memory_saturated_with_the_rest_normal(self) -> None:
        """Caso C4 del plan: CPU97/RAM91/disco12 y el resto normal."""
        report = RuleBasedDiagnosticEngine().build_report(
            (
                result_for(ComponentKind.CPU, HealthStatus.CRITICAL, "97% de uso", "Carga elevada"),
                result_for(ComponentKind.MEMORY, HealthStatus.CRITICAL, "91% de uso", "Poca memoria"),
                result_for(ComponentKind.DISK, HealthStatus.NORMAL, "12% ocupado"),
                result_for(ComponentKind.USB, HealthStatus.NORMAL, "8 disp. USB conectados"),
            )
        )

        self.assertTrue(report.has_problems)
        self.assertIn("saturación de recursos", report.conclusion)
        self.assertIn("97% de uso", report.conclusion)
        self.assertIn("91% de uso", report.conclusion)
        self.assertNotIn("También se detectó", report.conclusion)

    def test_query_failure_becomes_limitation_not_hardware_problem(self) -> None:
        report = RuleBasedDiagnosticEngine().build_report(
            (
                result_for(
                    ComponentKind.PCI,
                    HealthStatus.ERROR,
                    "Error de consulta",
                    "Permiso insuficiente",
                ),
            )
        )

        self.assertFalse(report.has_problems)
        self.assertEqual(len(report.limitations), 1)
        self.assertIn("no pudieron completarse", report.conclusion)

    def test_final_assignment_scenario_mentions_each_supported_cause(self) -> None:
        report = RuleBasedDiagnosticEngine().build_report(
            (
                result_for(ComponentKind.CPU, HealthStatus.CRITICAL, "95% de uso"),
                result_for(ComponentKind.MEMORY, HealthStatus.WARNING, "92% de uso"),
                result_for(ComponentKind.DISK, HealthStatus.NORMAL, "45% ocupado"),
                result_for(
                    ComponentKind.USB,
                    HealthStatus.CRITICAL,
                    "Código 43",
                    "Driver/configuración",
                ),
                result_for(
                    ComponentKind.MONITOR_GPU,
                    HealthStatus.CRITICAL,
                    "Error de controlador",
                    "Controlador gráfico",
                ),
            )
        )

        self.assertIn("CPU (95% de uso)", report.conclusion)
        self.assertIn("memoria RAM (92% de uso)", report.conclusion)
        self.assertIn("USB", report.conclusion)
        self.assertIn("monitor_gpu", report.conclusion)

    def test_error_is_not_a_hardware_problem_but_critical_is(self) -> None:
        error_report = RuleBasedDiagnosticEngine().build_report(
            (result_for(ComponentKind.PCI, HealthStatus.ERROR, "Error de consulta"),)
        )
        critical_report = RuleBasedDiagnosticEngine().build_report(
            (result_for(ComponentKind.PCI, HealthStatus.CRITICAL, "Código 43"),)
        )

        self.assertFalse(error_report.has_problems)
        self.assertTrue(critical_report.has_problems)

    def test_all_ok_with_persistent_symptom_forces_deeper_diagnosis(self) -> None:
        report = RuleBasedDiagnosticEngine().build_report(
            (
                result_for(ComponentKind.CPU, HealthStatus.NORMAL, "35% de uso"),
                result_for(ComponentKind.MEMORY, HealthStatus.NORMAL, "42% de uso"),
                result_for(ComponentKind.DISK, HealthStatus.NORMAL, "55% ocupado"),
                result_for(ComponentKind.MONITOR_GPU, HealthStatus.NORMAL, "GPU OK"),
            ),
            symptom="el equipo se reinicia al jugar",
        )

        self.assertFalse(report.has_problems)
        self.assertEqual(report.symptom, "el equipo se reinicia al jugar")
        self.assertIn("sin anomalías básicas", report.conclusion)
        self.assertIn("temperatura", report.conclusion)
        self.assertIn("fuente de alimentación", report.conclusion)
        self.assertIn("GPU", report.conclusion)

    def test_symptom_persists_with_failed_query_still_forces_deeper_diagnosis(self) -> None:
        """Un fallo de consulta no equivale a hardware sano: el sintoma persistente
        sigue exigiendo diagnostico adicional en lugar de quedarse sin orientacion."""
        report = RuleBasedDiagnosticEngine().build_report(
            (
                result_for(ComponentKind.CPU, HealthStatus.NORMAL, "20% de uso"),
                result_for(
                    ComponentKind.DISK,
                    HealthStatus.ERROR,
                    "No disponible",
                    "La consulta no devolvio informacion",
                ),
            ),
            symptom="el equipo se reinicia al jugar",
        )

        self.assertFalse(report.has_problems)
        self.assertIn("no deben interpretarse como sanas", report.conclusion)
        self.assertIn("temperatura", report.conclusion)
        self.assertIn("fuente de alimentación", report.conclusion)

    def test_symptom_without_anomalies_uses_precise_wording(self) -> None:
        report = RuleBasedDiagnosticEngine().build_report(
            (result_for(ComponentKind.SYSTEM, HealthStatus.NORMAL, "Sistema OK"),)
        )

        self.assertIn("No se observan anomalías en los indicadores consultados", report.conclusion)
        self.assertNotIn("sin problemas", report.conclusion)

    def test_network_case_c1_apipa_conclusion(self) -> None:
        net_result = ComponentResult(
            component=ComponentKind.NETWORK,
            name="Red",
            facts={"Caso": "C1", "Diagnóstico de red": "Dirección APIPA (169.254.x.x)"},
            summary="APIPA (169.254.x.x) - Sin DHCP",
            status=HealthStatus.CRITICAL,
            possible_problem="Dirección APIPA (169.254.x.x) sin concesión DHCP ni acceso a red local",
            evidence=(),
        )
        report = RuleBasedDiagnosticEngine().build_report((net_result,))
        self.assertTrue(report.has_problems)
        self.assertIn("Caso C1", report.conclusion)
        self.assertIn("APIPA", report.conclusion)
        self.assertIn("DHCP", report.conclusion)
        self.assertIn("ipconfig /release", report.conclusion)

    def test_network_case_dns_failure_conclusion(self) -> None:
        net_result = ComponentResult(
            component=ComponentKind.NETWORK,
            name="Red",
            facts={"Caso": "DNS", "Diagnóstico de red": "Conectividad IP operativa pero fallo de resolución DNS"},
            summary="Fallo de resolución DNS",
            status=HealthStatus.WARNING,
            possible_problem="Conectividad IP operativa pero fallo de resolución DNS",
            evidence=(),
        )
        report = RuleBasedDiagnosticEngine().build_report((net_result,))
        self.assertTrue(report.has_problems)
        self.assertIn("resolución DNS", report.conclusion)
        self.assertIn("ipconfig /flushdns", report.conclusion)

    def test_pci_case_c2_conclusion(self) -> None:
        pci_result = ComponentResult(
            component=ComponentKind.PCI,
            name="PCI / PCIe",
            facts={"Caso": "C2"},
            summary="1 disp. con error",
            status=HealthStatus.CRITICAL,
            possible_problem="Problema localizado en adaptador de red PCIe (Realtek, Código: 10)",
            evidence=(),
        )
        report = RuleBasedDiagnosticEngine().build_report((pci_result,))
        self.assertTrue(report.has_problems)
        self.assertIn("Caso C2", report.conclusion)
        self.assertIn("adaptador de red PCIe", report.conclusion)
        self.assertIn("Administrador de dispositivos", report.conclusion)

    def test_usb_case_c3_conclusion(self) -> None:
        usb_result = ComponentResult(
            component=ComponentKind.USB,
            name="USB",
            facts={"Caso": "C3"},
            summary="1 disp. con error",
            status=HealthStatus.CRITICAL,
            possible_problem="Problema localizado en periférico USB (SanDisk, Código: 43)",
            evidence=(),
        )
        report = RuleBasedDiagnosticEngine().build_report((usb_result,))
        self.assertTrue(report.has_problems)
        self.assertIn("Caso C3", report.conclusion)
        self.assertIn("periférico o memoria USB", report.conclusion)
        self.assertIn("controlador anfitrión USB funciona correctamente", report.conclusion)
        self.assertIn("no está degradado", report.conclusion)

    def test_gpu_ok_with_persistent_symptom_conclusion(self) -> None:
        gpu_result = ComponentResult(
            component=ComponentKind.MONITOR_GPU,
            name="Monitor y GPU",
            facts={},
            summary="1 GPU · Estado OK",
            status=HealthStatus.NORMAL,
            evidence=(),
        )
        report = RuleBasedDiagnosticEngine().build_report((gpu_result,), symptom="el equipo se reinicia al jugar")
        self.assertIn("DirectX", report.conclusion)
        self.assertIn("gráficos por aplicación", report.conclusion)
        self.assertIn("controladores", report.conclusion)


class EngineRecommendationTests(TestCase):
    def test_the_report_carries_recommendations_for_each_anomaly(self) -> None:
        report = RuleBasedDiagnosticEngine().build_report(
            (
                result_for(ComponentKind.CPU, HealthStatus.CRITICAL, "98% de uso"),
                result_for(ComponentKind.DISK, HealthStatus.NORMAL, "30% ocupado"),
            )
        )

        self.assertEqual(len(report.recommendations), 1)
        self.assertEqual(report.recommendations[0].component, ComponentKind.CPU)

    def test_a_clean_report_carries_no_recommendations(self) -> None:
        report = RuleBasedDiagnosticEngine().build_report(
            (result_for(ComponentKind.CPU, HealthStatus.NORMAL, "20% de uso"),)
        )

        self.assertEqual(report.recommendations, ())

    def test_procedures_that_alter_the_machine_are_flagged(self) -> None:
        """La app propone ipconfig /renew; nunca lo ejecuta."""
        net = ComponentResult(
            component=ComponentKind.NETWORK,
            name="Red",
            facts={"Caso": "C1"},
            summary="APIPA",
            status=HealthStatus.CRITICAL,
            possible_problem="Dirección APIPA (169.254.x.x) sin DHCP",
            evidence=(),
        )
        report = RuleBasedDiagnosticEngine().build_report((net,))

        self.assertTrue(report.recommendations[0].modifies_system)
