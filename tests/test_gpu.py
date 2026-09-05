"""Pruebas unitarias para GpuCollector, límites de WMI y estados."""

from unittest import TestCase
from unittest.mock import MagicMock

from hardware_admin.collectors.gpu import GpuCollector
from hardware_admin.domain.models import ComponentKind, HealthStatus
from hardware_admin.infrastructure.powershell import CommandResult, PowerShellQuery


def mock_ps_result(output: str) -> CommandResult:
    return CommandResult(
        query=PowerShellQuery.VIDEO_CONTROLLERS,
        output=output,
        exit_code=0,
    )


class GpuCollectorTests(TestCase):
    def setUp(self) -> None:
        self.runner = MagicMock()
        self.collector = GpuCollector(self.runner)

    def test_gpu_collector_normal_and_wmi_limits_note(self) -> None:
        gpu_json = (
            '['
            '{"Tipo": "GPU", "Nombre": "NVIDIA GeForce RTX 3060", "Estado": "OK", '
            '"Procesador": "GA106", "Memoria": 4293918720, "Resolucion": "1920x1080", '
            '"Driver": "31.0.15.2849", "PNPDeviceID": "PCI\\\\VEN_10DE&DEV_2503\\\\01"},'
            '{"Tipo": "Monitor", "Nombre": "Dell U2415", "Estado": "OK", "PNPDeviceID": "MONITOR\\\\DELA0B5\\\\01"}'
            ']'
        )
        self.runner.run.return_value = mock_ps_result(gpu_json)

        result = self.collector.collect()
        self.assertEqual(result.component, ComponentKind.MONITOR_GPU)
        self.assertEqual(result.status, HealthStatus.NORMAL)
        self.assertIn("1 GPU · 1 monitor(es)", result.summary)
        # Verificar que se incluye la nota de límites VRAM de WMI
        self.assertIn("Límites técnicos VRAM", result.facts)
        self.assertIn("WMI", result.facts["Límites técnicos VRAM"])

    def test_gpu_unknown_status_warns_without_condemning_hardware(self) -> None:
        gpu_json = (
            '['
            '{"Tipo": "GPU", "Nombre": "Tarjeta gráfica básica", "Estado": "Unknown", '
            '"Procesador": "VGA", "Memoria": null, "Resolucion": "1024x768", '
            '"Driver": "10.0.19041", "PNPDeviceID": "PCI\\\\VEN_0000\\\\00"}'
            ']'
        )
        self.runner.run.return_value = mock_ps_result(gpu_json)

        result = self.collector.collect()
        self.assertEqual(result.status, HealthStatus.WARNING)
        self.assertIn("Unknown", result.possible_problem or "")
        self.assertIn("no prueba daño físico", result.possible_problem or "")

