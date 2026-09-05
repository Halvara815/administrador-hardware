"""Pruebas unitarias para el recolector de almacenamiento StorageCollector."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

from hardware_admin.collectors.storage import StorageCollector
from hardware_admin.domain.models import ComponentKind, HealthStatus
from hardware_admin.infrastructure.powershell import CommandResult, PowerShellQuery


def mock_ps_result(output: str, query: PowerShellQuery = PowerShellQuery.DISKS) -> CommandResult:
    return CommandResult(
        query=query,
        output=output,
        exit_code=0,
    )


class StorageCollectorTests(TestCase):
    def setUp(self) -> None:
        self.runner = MagicMock()
        self.collector = StorageCollector(self.runner)

    @patch("psutil.disk_partitions")
    @patch("psutil.disk_usage")
    def test_storage_collector_normal(self, mock_usage: MagicMock, mock_partitions: MagicMock) -> None:
        mock_part = MagicMock()
        mock_part.mountpoint = "C:\\"
        mock_part.fstype = "NTFS"
        mock_partitions.return_value = [mock_part]

        usage_mock = MagicMock()
        usage_mock.total = 500 * 1024**3
        usage_mock.free = 250 * 1024**3
        usage_mock.percent = 50.0
        mock_usage.return_value = usage_mock

        # Mock physical disks (SSD NVMe)
        phys_json = '[{"DeviceId":"0","FriendlyName":"NVMe SSD 500GB","MediaType":"SSD","BusType":"NVMe","HealthStatus":"Healthy","Size":500107862016}]'
        vol_json = '[{"DriveLetter":"C","FileSystem":"NTFS","HealthStatus":"Healthy","Size":500000000000,"SizeRemaining":250000000000}]'
        disks_json = '[{"Unidad":0,"Dispositivo":"NVMe SSD 500GB","Tipo de bus":"NVMe","Estado":"Online","Salud":"Healthy","Capacidad":500107862016}]'

        def run_side_effect(query: PowerShellQuery) -> CommandResult:
            if query == PowerShellQuery.PHYSICAL_DISKS:
                return mock_ps_result(phys_json, query)
            if query == PowerShellQuery.VOLUMES:
                return mock_ps_result(vol_json, query)
            return mock_ps_result(disks_json, query)

        self.runner.run.side_effect = run_side_effect

        result = self.collector.collect()
        self.assertEqual(result.component, ComponentKind.DISK)
        self.assertEqual(result.status, HealthStatus.NORMAL)
        self.assertIn("SSD", result.summary)
        self.assertIn("1 SSD", result.facts.get("Resumen tecnológico", ""))

    @patch("psutil.disk_partitions")
    @patch("psutil.disk_usage")
    def test_storage_unhealthy_disk_reports_critical(self, mock_usage: MagicMock, mock_partitions: MagicMock) -> None:
        mock_partitions.return_value = []
        phys_json = '[{"DeviceId":"1","FriendlyName":"Failing HDD","MediaType":"HDD","BusType":"SATA","HealthStatus":"Warning","Size":1000000000000}]'

        def run_side_effect(query: PowerShellQuery) -> CommandResult:
            if query == PowerShellQuery.PHYSICAL_DISKS:
                return mock_ps_result(phys_json, query)
            return mock_ps_result("[]", query)

        self.runner.run.side_effect = run_side_effect

        result = self.collector.collect()
        self.assertEqual(result.status, HealthStatus.CRITICAL)
        self.assertIn("Failing HDD", result.possible_problem or "")
        self.assertIn("salud física", result.possible_problem or "")

    @patch("psutil.disk_partitions")
    @patch("psutil.disk_usage")
    def test_usb_ok_without_volume_is_a_localized_case_not_a_bus_failure(
        self, mock_usage: MagicMock, mock_partitions: MagicMock
    ) -> None:
        """Caso «USB OK sin volumen» del plan: la memoria USB esta presente y sana
        pero Windows no expone volumen. Es deteccion/configuracion del periferico,
        no una condena del bus ni un dano fisico."""
        mock_partitions.return_value = []
        phys_json = "[]"
        # Asociacion reportada por Windows: disco USB sano y sin letra de unidad.
        usb_json = (
            '[{"Numero":2,"Dispositivo":"SanDisk Cruzer","Salud":"Healthy",'
            '"Estado":"Online","EstiloParticion":"RAW","Volumenes":""}]'
        )

        def run_side_effect(query: PowerShellQuery) -> CommandResult:
            if query == PowerShellQuery.USB_STORAGE:
                return mock_ps_result(usb_json, query)
            if query == PowerShellQuery.PHYSICAL_DISKS:
                return mock_ps_result(phys_json, query)
            return mock_ps_result("[]", query)

        self.runner.run.side_effect = run_side_effect

        result = self.collector.collect()
        self.assertEqual(result.status, HealthStatus.WARNING)
        self.assertEqual(result.facts.get("Caso"), "USB-SIN-VOLUMEN")
        problem = result.possible_problem or ""
        self.assertIn("SanDisk Cruzer", problem)
        self.assertIn("sin volumen", problem.lower())
        self.assertNotIn("daño físico", problem)

    @patch("psutil.disk_partitions")
    @patch("psutil.disk_usage")
    def test_usb_storage_with_volume_letter_is_not_flagged(
        self, mock_usage: MagicMock, mock_partitions: MagicMock
    ) -> None:
        """Un USB sano y con letra de unidad no debe generar el caso anterior."""
        mock_partitions.return_value = []
        usb_json = (
            '[{"Numero":2,"Dispositivo":"SanDisk Cruzer","Salud":"Healthy",'
            '"Estado":"Online","EstiloParticion":"MBR","Volumenes":"E"}]'
        )

        def run_side_effect(query: PowerShellQuery) -> CommandResult:
            if query == PowerShellQuery.USB_STORAGE:
                return mock_ps_result(usb_json, query)
            return mock_ps_result("[]", query)

        self.runner.run.side_effect = run_side_effect

        result = self.collector.collect()
        self.assertEqual(result.status, HealthStatus.NORMAL)
        self.assertIsNone(result.facts.get("Caso"))
