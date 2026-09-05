"""Pruebas unitarias para PnpDeviceCollector y validación de los casos C2 y C3."""

from unittest import TestCase
from unittest.mock import MagicMock

from hardware_admin.collectors.pnp import PnpDeviceCollector
from hardware_admin.domain.models import ComponentKind, HealthStatus
from hardware_admin.infrastructure.powershell import CommandResult, PowerShellQuery


def mock_ps_result(output: str, query: PowerShellQuery) -> CommandResult:
    return CommandResult(
        query=query,
        output=output,
        exit_code=0,
    )


class PnpCollectorTests(TestCase):
    def setUp(self) -> None:
        self.runner = MagicMock()

    def test_usb_case_c3_peripheral_error_without_condemning_host_bus(self) -> None:
        # Caso C3: Controlador USB en OK, pero dispositivo USB con error Código 43
        usb_devices = (
            '['
            '{"FriendlyName": "Controlador de host USB 3.0 eXtensible", "Class": "USB", "Status": "OK", "InstanceId": "PCI\\\\VEN_8086&DEV_A36D\\\\ROOT_HUB30", "Problem": null},'
            '{"FriendlyName": "Memoria USB SanDisk Cruzer", "Class": "DiskDrive", "Status": "Error", "InstanceId": "USB\\\\VID_0781&PID_5581\\\\AA01", "Problem": 43}'
            ']'
        )
        self.runner.run.return_value = mock_ps_result(usb_devices, PowerShellQuery.USB_PRESENT)

        collector = PnpDeviceCollector(
            self.runner,
            ComponentKind.USB,
            "USB",
            PowerShellQuery.USB_PRESENT,
        )

        result = collector.collect()
        self.assertEqual(result.component, ComponentKind.USB)
        self.assertEqual(result.status, HealthStatus.CRITICAL)
        self.assertEqual(result.facts.get("Caso"), "C3")
        # Debe aislar la falla en el periférico y certificar que el host no está degradado
        self.assertIn("Memoria USB SanDisk Cruzer", result.possible_problem or "")
        self.assertIn("controlador anfitrión USB funciona correctamente", result.possible_problem or "")
        self.assertIn("no está degradado", result.possible_problem or "")

    def test_pci_case_c2_nic_error_localized(self) -> None:
        # Caso C2: NIC PCIe con error de controlador
        pci_devices = (
            '['
            '{"FriendlyName": "Intel(R) PCI Express Root Port", "Class": "System", "Status": "OK", "InstanceId": "PCI\\\\VEN_8086&DEV_A338\\\\0", "Problem": null},'
            '{"FriendlyName": "Realtek PCIe GbE Family Controller (NIC)", "Class": "Net", "Status": "Error", "InstanceId": "PCI\\\\VEN_10EC&DEV_8168\\\\NIC01", "Problem": 10}'
            ']'
        )
        self.runner.run.return_value = mock_ps_result(pci_devices, PowerShellQuery.PCI_PRESENT)

        collector = PnpDeviceCollector(
            self.runner,
            ComponentKind.PCI,
            "PCI / PCIe",
            PowerShellQuery.PCI_PRESENT,
        )

        result = collector.collect()
        self.assertEqual(result.component, ComponentKind.PCI)
        self.assertEqual(result.status, HealthStatus.CRITICAL)
        self.assertEqual(result.facts.get("Caso"), "C2")
        self.assertIn("adaptador de red PCIe", result.possible_problem or "")
        self.assertIn("Realtek PCIe GbE Family Controller", result.possible_problem or "")
        self.assertIn("inserción física", result.possible_problem or "")

    def test_usb_absent_list_does_not_prove_the_device_never_existed(self) -> None:
        """Caso «USB ausente» del plan: una lista vacia no demuestra ausencia fisica.
        No confundir el PASS de una consulta con salud ni con inexistencia."""
        self.runner.run.return_value = mock_ps_result("[]", PowerShellQuery.USB_PRESENT)

        collector = PnpDeviceCollector(
            self.runner,
            ComponentKind.USB,
            "USB",
            PowerShellQuery.USB_PRESENT,
        )
        result = collector.collect()

        self.assertEqual(result.status, HealthStatus.NORMAL)
        self.assertEqual(result.facts.get("Caso"), "USB-AUSENTE")
        cobertura = str(result.facts.get("Limitación de cobertura", ""))
        self.assertIn("no demuestra", cobertura)
        self.assertIn("ID", cobertura)
