"""Pruebas del generador de recomendaciones estructuradas."""

from datetime import UTC, datetime
from unittest import TestCase

from hardware_admin.diagnostics.recommendations import build_recommendations
from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    EvidenceRecord,
    HealthStatus,
)


def result_for(
    component: ComponentKind,
    status: HealthStatus,
    summary: str = "resumen",
    problem: str | None = None,
    facts: dict[str, object] | None = None,
) -> ComponentResult:
    return ComponentResult(
        component=component,
        name=component.value,
        facts=facts or {},
        summary=summary,
        status=status,
        possible_problem=problem,
        evidence=(EvidenceRecord("test", "query", "salida", datetime.now(UTC)),),
    )


class RecommendationShapeTests(TestCase):
    def test_a_clean_machine_without_symptom_gets_no_recommendations(self) -> None:
        """Sin anomalias y sin sintoma no hay nada que proponer."""
        results = (
            result_for(ComponentKind.CPU, HealthStatus.NORMAL),
            result_for(ComponentKind.MEMORY, HealthStatus.NORMAL),
        )

        self.assertEqual(build_recommendations(results), ())

    def test_every_recommendation_carries_the_five_required_fields(self) -> None:
        """El plan exige causa, pasos, fundamento y comprobacion posterior."""
        results = (
            result_for(ComponentKind.CPU, HealthStatus.CRITICAL, "98% de uso"),
            result_for(ComponentKind.MEMORY, HealthStatus.WARNING, "88% de uso"),
            result_for(ComponentKind.DISK, HealthStatus.CRITICAL, "96% ocupado"),
        )

        recommendations = build_recommendations(results)
        self.assertGreaterEqual(len(recommendations), 3)
        for item in recommendations:
            self.assertTrue(item.title)
            self.assertTrue(item.cause)
            self.assertTrue(item.steps, f"{item.title}: sin pasos")
            self.assertTrue(item.rationale)
            self.assertTrue(item.verification, f"{item.title}: sin comprobacion")
            self.assertIsInstance(item.modifies_system, bool)


class RecommendationCaseTests(TestCase):
    def test_high_cpu_suggests_reviewing_processes(self) -> None:
        results = (result_for(ComponentKind.CPU, HealthStatus.CRITICAL, "98% de uso"),)

        item = build_recommendations(results)[0]
        self.assertEqual(item.component, ComponentKind.CPU)
        self.assertIn("proceso", " ".join(item.steps).lower())
        self.assertFalse(item.modifies_system)

    def test_full_disk_suggests_freeing_space(self) -> None:
        results = (result_for(ComponentKind.DISK, HealthStatus.CRITICAL, "96% ocupado"),)

        item = build_recommendations(results)[0]
        self.assertIn("espacio", (item.title + " ".join(item.steps)).lower())

    def test_apipa_case_c1_proposes_dhcp_commands_marked_as_altering(self) -> None:
        """ipconfig /release y /renew cambian el equipo: la app los propone, no los ejecuta."""
        results = (
            result_for(
                ComponentKind.NETWORK,
                HealthStatus.CRITICAL,
                "APIPA",
                "Dirección APIPA (169.254.x.x) sin DHCP",
                {"Caso": "C1"},
            ),
        )

        item = build_recommendations(results)[0]
        steps = " ".join(item.steps)
        self.assertIn("ipconfig /renew", steps)
        self.assertTrue(item.modifies_system)

    def test_dns_failure_proposes_flushdns_marked_as_altering(self) -> None:
        results = (
            result_for(
                ComponentKind.NETWORK,
                HealthStatus.WARNING,
                "DNS",
                "Fallo de resolución DNS",
                {"Caso": "DNS"},
            ),
        )

        item = build_recommendations(results)[0]
        self.assertIn("flushdns", " ".join(item.steps))
        self.assertTrue(item.modifies_system)

    def test_pci_case_c2_targets_the_adapter_without_condemning_the_bus(self) -> None:
        results = (
            result_for(ComponentKind.PCI, HealthStatus.CRITICAL, "NIC", None, {"Caso": "C2"}),
        )

        item = build_recommendations(results)[0]
        self.assertEqual(item.component, ComponentKind.PCI)
        self.assertIn("PCIe", item.title + item.cause + " ".join(item.steps))

    def test_usb_case_c3_targets_the_peripheral_not_the_host_bus(self) -> None:
        results = (
            result_for(ComponentKind.USB, HealthStatus.CRITICAL, "USB", None, {"Caso": "C3"}),
        )

        item = build_recommendations(results)[0]
        text = (item.title + item.cause + item.rationale).lower()
        self.assertIn("periférico", text)
        self.assertIn("bus", text)

    def test_usb_without_volume_suggests_assigning_a_letter(self) -> None:
        results = (
            result_for(
                ComponentKind.DISK,
                HealthStatus.WARNING,
                "USB sin volumen",
                "Medio USB presente y sano sin volumen accesible",
                {"Caso": "USB-SIN-VOLUMEN"},
            ),
        )

        item = build_recommendations(results)[0]
        self.assertIn("letra", " ".join(item.steps).lower())

    def test_persistent_symptom_without_anomalies_proposes_deeper_diagnosis(self) -> None:
        """Caso C5: todo OK pero el sintoma sigue. Hay que proponer algo."""
        results = (
            result_for(ComponentKind.CPU, HealthStatus.NORMAL),
            result_for(ComponentKind.MONITOR_GPU, HealthStatus.NORMAL),
        )

        recommendations = build_recommendations(results, symptom="se reinicia al jugar")
        self.assertEqual(len(recommendations), 1)
        text = " ".join(recommendations[0].steps).lower()
        self.assertIn("temperatura", text)

    def test_a_failed_query_produces_its_own_recommendation(self) -> None:
        """Un dato ausente no es hardware sano: hay que repetir la consulta."""
        results = (
            result_for(ComponentKind.PCI, HealthStatus.ERROR, "No disponible", "Permiso denegado"),
        )

        recommendations = build_recommendations(results)
        self.assertEqual(len(recommendations), 1)
        self.assertIn("permiso", " ".join(recommendations[0].steps).lower())


class RecommendationOrderAndSafetyTests(TestCase):
    def test_critical_findings_come_before_warnings(self) -> None:
        results = (
            result_for(ComponentKind.MEMORY, HealthStatus.WARNING, "88% de uso"),
            result_for(ComponentKind.CPU, HealthStatus.CRITICAL, "98% de uso"),
        )

        recommendations = build_recommendations(results)
        self.assertEqual(recommendations[0].component, ComponentKind.CPU)

    def test_the_symptom_is_data_and_never_reaches_a_command(self) -> None:
        """El sintoma se trata como dato: no se interpola en ningun procedimiento."""
        malicious = "lento & del /f /q C:\\Windows"
        results = (result_for(ComponentKind.CPU, HealthStatus.NORMAL),)

        recommendations = build_recommendations(results, symptom=malicious)
        for item in recommendations:
            joined = item.title + item.cause + item.rationale + " ".join(item.steps)
            self.assertNotIn("del /f", joined)
            self.assertNotIn("&", joined)
