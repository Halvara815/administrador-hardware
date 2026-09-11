"""Contratos de los asesores locales de ampliación."""

from datetime import UTC, datetime
from unittest import TestCase

from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    EvidenceRecord,
    HealthStatus,
)
from hardware_admin.services.upgrade_advisor import (
    CONTRADICTORY,
    DECLARED_INCOMPATIBLE,
    PENDING,
    UpgradePreferences,
    build_upgrade_advice,
)


def result(
    component: ComponentKind,
    facts: dict[str, object],
    status: HealthStatus = HealthStatus.NORMAL,
) -> ComponentResult:
    return ComponentResult(
        component=component,
        name=component.value,
        facts=facts,
        status=status,
        evidence=(EvidenceRecord("fixture", "query", "output", datetime.now(UTC)),),
    )


MEMORY = result(
    ComponentKind.MEMORY,
    {
        "_memoria": {"total": 8 * 1024**3},
        "Módulos físicos": [
            {"Ranura": "DIMM 0", "Capacidad": "8.0 GB", "Tipo / Generación": "DDR4"}
        ],
    },
)
STORAGE = result(
    ComponentKind.DISK,
    {
        "Discos físicos": [
            {"Dispositivo": "Unidad actual", "Tipo de medio": "SSD", "Bus": "NVMe", "Capacidad": "512 GB"}
        ],
        "_volumenes": [{"unidad": "C:\\", "porcentaje": 92.0}],
    },
)
GPU = result(
    ComponentKind.MONITOR_GPU,
    {"Adaptadores de vídeo (GPU)": [{"Nombre": "GPU actual"}]},
)


class UpgradeAdvisorSafetyTests(TestCase):
    def test_ram_never_infers_a_maximum_or_free_slot_from_windows_inventory(self) -> None:
        advice = build_upgrade_advice((MEMORY,))

        ram = advice["ram"]
        self.assertEqual(ram["estado"], PENDING)
        self.assertIn("manual", " ".join(ram["comprobaciones_pendientes"]).lower())
        self.assertIn("ranuras", " ".join(ram["comprobaciones_pendientes"]).lower())

    def test_ram_rejects_a_documented_limit_below_the_detected_inventory(self) -> None:
        advice = build_upgrade_advice(
            (
                MEMORY,
            ),
            UpgradePreferences(
                ram_manual_reference="Manual OEM",
                ram_verified_max_gb="4",
                ram_total_slots="2",
                ram_soldered="No",
            ),
        )

        self.assertEqual(advice["ram"]["estado"], CONTRADICTORY)

    def test_ssd_does_not_infer_nvme_compatibility_from_an_m2_label_or_current_disk(self) -> None:
        advice = build_upgrade_advice(
            (STORAGE,),
            UpgradePreferences(
                ssd_target="SSD nuevo",
                ssd_target_capacity="2 TB",
                ssd_target_protocol="NVMe",
                ssd_target_form_factor="M.2 2280",
            ),
        )

        self.assertEqual(advice["ssd"]["estado"], PENDING)
        pending = " ".join(advice["ssd"]["comprobaciones_pendientes"]).lower()
        self.assertIn("manual", pending)
        self.assertIn("ranura", pending)

    def test_ssd_marks_a_declared_protocol_mismatch_without_claiming_a_purchase(self) -> None:
        advice = build_upgrade_advice(
            (STORAGE,),
            UpgradePreferences(
                ssd_target="SSD nuevo",
                ssd_target_capacity="2 TB",
                ssd_target_protocol="NVMe",
                ssd_target_form_factor="M.2 2280",
                ssd_supported_protocols="SATA",
                ssd_supported_form_factors="M.2 2280",
                ssd_available_bays_or_slots="M.2_2 libre",
                ssd_manual_reference="Manual OEM",
            ),
        )

        self.assertEqual(advice["ssd"]["estado"], DECLARED_INCOMPATIBLE)
        self.assertEqual(advice["ssd"]["capacidad_objetivo"], "2 TB")

    def test_gpu_laptop_is_pending_even_when_windows_detects_an_adapter(self) -> None:
        advice = build_upgrade_advice(
            (GPU,),
            UpgradePreferences(equipment_form="Portátil", gpu_target="GPU objetivo"),
        )

        self.assertEqual(advice["gpu"]["estado"], PENDING)
        self.assertIn("portátil", advice["gpu"]["conclusion"].lower())

    def test_gpu_declared_short_on_power_space_or_connector_is_not_compatible(self) -> None:
        advice = build_upgrade_advice(
            (GPU,),
            UpgradePreferences(
                equipment_form="Sobremesa",
                gpu_target="GPU objetivo",
                gpu_required_psu_watts="650",
                gpu_required_connectors="8-pin",
                gpu_length_mm="320",
                gpu_current_psu_watts="550",
                gpu_current_connectors="6-pin",
                gpu_clearance_mm="300",
                gpu_pcie_slot_note="PCIe x16 documentada",
                gpu_manual_reference="Manual y ficha técnica",
            ),
        )

        self.assertEqual(advice["gpu"]["estado"], DECLARED_INCOMPATIBLE)

    def test_priority_starts_with_no_purchase_and_requires_goal_and_budget(self) -> None:
        advice = build_upgrade_advice((MEMORY, STORAGE, GPU))

        priority = advice["priorización"]
        self.assertEqual(priority["estado"], PENDING)
        self.assertEqual(priority["acciones"][0]["área"], "Sin compra")
        self.assertIn("objetivo", " ".join(priority["comprobaciones_pendientes"]).lower())

    def test_empty_preferences_has_at_most_1_ram_pending_and_at_most_4_ssd_pending(self) -> None:
        memory_full = result(
            ComponentKind.MEMORY,
            {
                "_memoria": {"total": 16 * 1024**3},
                "Módulos físicos": [
                    {"Ranura": "DIMM 0", "Capacidad": "16.0 GB", "Tipo / Generación": "DDR4", "Factor de forma": "DIMM"}
                ],
                "Ranuras RAM reportadas por firmware": 2,
                "_ampliacion_ram": {
                    "maximo_firmware_bytes": 64 * 1024**3,
                    "margen_teorico_bytes": 48 * 1024**3,
                },
            },
        )
        system_full = result(
            ComponentKind.SYSTEM,
            {
                "Fabricante": "Dell Inc.",
                "Modelo": "OptiPlex 7090",
                "Placa base": "0XYZ12",
                "BIOS / UEFI": "1.14.0",
                "Ranuras del sistema (Win32_SystemSlot)": [
                    {"Ranura": "M.2 Slot 1", "Uso actual": "Disponible", "Estado": "OK"}
                ],
            },
        )
        advice = build_upgrade_advice((system_full, memory_full, STORAGE, GPU), UpgradePreferences())

        # RAM tiene a lo sumo 1 pendiente (la verificación de memoria soldada)
        self.assertLessEqual(len(advice["ram"]["comprobaciones_pendientes"]), 1)
        # SSD tiene a lo sumo 4 pendientes (modelo, capacidad, protocolo, formato objetivo)
        self.assertLessEqual(len(advice["ssd"]["comprobaciones_pendientes"]), 4)

    def test_ram_complete_inventory_slots_and_max_not_pending(self) -> None:
        memory_with_fw = result(
            ComponentKind.MEMORY,
            {
                "_memoria": {"total": 8 * 1024**3},
                "Módulos físicos": [
                    {"Ranura": "DIMM 0", "Capacidad": "8.0 GB", "Tipo / Generación": "DDR4"}
                ],
                "Ranuras RAM reportadas por firmware": 2,
                "_ampliacion_ram": {
                    "maximo_firmware_bytes": 32 * 1024**3,
                    "margen_teorico_bytes": 24 * 1024**3,
                },
            },
        )
        advice = build_upgrade_advice((memory_with_fw,))
        pending = " ".join(advice["ram"]["comprobaciones_pendientes"]).lower()
        self.assertNotIn("número total de ranuras", pending)
        self.assertNotIn("capacidad máxima de ram", pending)

    def test_ram_without_slots_fact_stays_pending_with_reason(self) -> None:
        advice = build_upgrade_advice((MEMORY,))
        self.assertEqual(advice["ram"]["estado"], PENDING)
        pending = " ".join(advice["ram"]["comprobaciones_pendientes"]).lower()
        self.assertIn("número total de ranuras de memoria no reportado por firmware ni declarado", pending)

    def test_ssd_nvme_present_does_not_request_supported_protocols(self) -> None:
        advice = build_upgrade_advice((STORAGE,))
        pending = " ".join(advice["ssd"]["comprobaciones_pendientes"]).lower()
        self.assertNotIn("protocolos admitidos por la ranura", pending)

    def test_system_slots_empty_keeps_bay_pending_without_asserting_free_slot(self) -> None:
        system_no_slots = result(
            ComponentKind.SYSTEM,
            {
                "Fabricante": "HP",
                "Modelo": "ProBook",
                "Ranuras del sistema (Win32_SystemSlot)": "No reportadas por el firmware o incompletas en este equipo",
            },
        )
        advice = build_upgrade_advice(
            (system_no_slots, STORAGE),
            UpgradePreferences(
                ssd_target="SSD 1 TB",
                ssd_target_capacity="1 TB",
                ssd_target_protocol="NVMe",
                ssd_target_form_factor="M.2 2280",
            ),
        )
        self.assertEqual(advice["ssd"]["estado"], PENDING)
        pending = " ".join(advice["ssd"]["comprobaciones_pendientes"]).lower()
        self.assertIn("ranura libre verificada", pending)

    def test_declared_contradicts_inventory_sets_contradictory(self) -> None:
        advice_slots = build_upgrade_advice(
            (MEMORY,),
            UpgradePreferences(ram_total_slots="0"),
        )
        # Con 1 módulo ocupado y 0 ranuras declaradas -> contradictorio
        self.assertEqual(advice_slots["ram"]["estado"], CONTRADICTORY)

