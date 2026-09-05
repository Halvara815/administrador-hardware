"""Pruebas unitarias y de integración de la Fase F3 Comercial: Sensores y comportamiento térmico."""

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest import TestCase
from unittest.mock import MagicMock, patch

from hardware_admin.collectors.core import CpuCollector
from hardware_admin.collectors.gpu import GpuCollector
from hardware_admin.diagnostics.engine import RuleBasedDiagnosticEngine
from hardware_admin.diagnostics.thermal import (
    NullThermalProvider,
    NvidiaGpuThermalProvider,
    StorageThermalProvider,
    WmiThermalZoneProvider,
    kelvin_decikelvin_to_celsius,
)
from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    ConfidenceLevel,
    HealthStatus,
    Measurement,
    ThermalReading,
)
from hardware_admin.infrastructure.commands import NativeCommandResult
from hardware_admin.infrastructure.powershell import CommandResult, PowerShellQuery
from hardware_admin.reports.html_report import export_html
from hardware_admin.reports.json_report import build_payload
from hardware_admin.reports.txt_report import render_text


def _now() -> datetime:
    return datetime.now(UTC)


def mock_cmd_result(output: str, query: PowerShellQuery, exit_code: int = 0, error: str = "") -> CommandResult:
    return CommandResult(
        query=query,
        output=output,
        exit_code=exit_code,
        error=error,
    )


class ThermalContractAndConversionTests(TestCase):
    """Pruebas de contratos de dominio y algoritmos de conversión térmica."""

    def test_thermal_reading_contract(self) -> None:
        """ThermalReading modela todos los campos obligatorios tipados sin diccionarios libres."""
        reading = ThermalReading(
            source_name="Sensor 1",
            target_hardware="CPU",
            temperature_celsius=45.5,
            unit="°C",
            collected_at=_now(),
            duration_seconds=0.05,
            confidence=ConfidenceLevel.HIGH,
            status=HealthStatus.NORMAL,
            is_supported=True,
            detail="Lectura correcta",
            is_throttling=False,
            fan_rpm=1500,
            power_watts=45.0,
            clock_mhz=3200.0,
        )
        self.assertEqual(reading.source_name, "Sensor 1")
        self.assertEqual(reading.target_hardware, "CPU")
        self.assertEqual(reading.temperature_celsius, 45.5)
        self.assertEqual(reading.unit, "°C")
        self.assertEqual(reading.confidence, ConfidenceLevel.HIGH)
        self.assertEqual(reading.status, HealthStatus.NORMAL)
        self.assertTrue(reading.is_supported)
        self.assertFalse(reading.is_throttling)
        self.assertEqual(reading.fan_rpm, 1500)
        self.assertEqual(reading.power_watts, 45.0)
        self.assertEqual(reading.clock_mhz, 3200.0)

    def test_kelvin_decikelvin_to_celsius_valid(self) -> None:
        """Conversión canónica de décimas de Kelvin a Celsius (C = (dK - 2732) / 10.0)."""
        # 3082 dK = 35.0 °C
        self.assertEqual(kelvin_decikelvin_to_celsius(3082), 35.0)
        # 2732 dK = 0.0 °C
        self.assertEqual(kelvin_decikelvin_to_celsius(2732), 0.0)
        # 3732 dK = 100.0 °C
        self.assertEqual(kelvin_decikelvin_to_celsius(3732), 100.0)
        # 2982 dK = 25.0 °C
        self.assertEqual(kelvin_decikelvin_to_celsius(2982), 25.0)

    def test_kelvin_decikelvin_to_celsius_invalid_or_impossible(self) -> None:
        """Valores nulos, no numéricos, imposibles, NaN o inf devuelven None."""
        self.assertIsNone(kelvin_decikelvin_to_celsius(None))
        self.assertIsNone(kelvin_decikelvin_to_celsius(""))
        self.assertIsNone(kelvin_decikelvin_to_celsius("invalid"))
        self.assertIsNone(kelvin_decikelvin_to_celsius(float("nan")))
        self.assertIsNone(kelvin_decikelvin_to_celsius(float("inf")))
        # Fuera de rango físico de hardware (-50 °C a 150 °C)
        self.assertIsNone(kelvin_decikelvin_to_celsius(100))  # 100 dK = -263.2 °C (imposible)
        self.assertIsNone(kelvin_decikelvin_to_celsius(9999))  # 9999 dK = 726.7 °C (imposible)


class NullThermalProviderTests(TestCase):
    """Pruebas del proveedor nulo y rollback transparente."""

    def test_null_provider_returns_unsupported(self) -> None:
        provider = NullThermalProvider()
        self.assertFalse(provider.is_available())
        readings = provider.read_temperatures()
        self.assertEqual(len(readings), 1)
        r = readings[0]
        self.assertEqual(r.status, HealthStatus.NOT_SUPPORTED)
        self.assertFalse(r.is_supported)
        self.assertIsNone(r.temperature_celsius)
        self.assertIn("desactivada", r.detail.lower())


class WmiThermalZoneProviderTests(TestCase):
    """Pruebas de consulta segura a WMI MSAcpi_ThermalZoneTemperature."""

    def setUp(self) -> None:
        self.runner = MagicMock()
        self.provider = WmiThermalZoneProvider(self.runner)

    def test_wmi_thermal_zone_healthy(self) -> None:
        """Zonas térmicas con 3082 dK (35.0 °C) generan estado NORMAL y confianza HIGH."""
        wmi_json = '[{"InstanceName":"ACPI\\\\ThermalZone\\\\TZ01_0","CurrentTemperature":3082,"CriticalTripPoint":3732}]'
        self.runner.run.return_value = mock_cmd_result(wmi_json, PowerShellQuery.THERMAL_ZONE)

        readings = self.provider.read_temperatures()
        self.assertEqual(len(readings), 1)
        r = readings[0]
        self.assertEqual(r.status, HealthStatus.NORMAL)
        self.assertEqual(r.temperature_celsius, 35.0)
        self.assertEqual(r.confidence, ConfidenceLevel.HIGH)
        self.assertTrue(r.is_supported)
        self.assertEqual(len(r.measurements), 1)
        self.assertEqual(r.measurements[0].value, 35.0)

    def test_wmi_thermal_zone_warning_and_critical(self) -> None:
        """Zonas térmicas a 82 °C dan WARNING; a 96 °C dan CRITICAL."""
        # 82 °C -> 2732 + 820 = 3552 dK
        wmi_json_warn = '[{"InstanceName":"TZ01","CurrentTemperature":3552}]'
        self.runner.run.return_value = mock_cmd_result(wmi_json_warn, PowerShellQuery.THERMAL_ZONE)
        r_warn = self.provider.read_temperatures()[0]
        self.assertEqual(r_warn.status, HealthStatus.WARNING)
        self.assertEqual(r_warn.temperature_celsius, 82.0)

        # 96 °C -> 2732 + 960 = 3692 dK
        wmi_json_crit = '[{"InstanceName":"TZ01","CurrentTemperature":3692}]'
        self.runner.run.return_value = mock_cmd_result(wmi_json_crit, PowerShellQuery.THERMAL_ZONE)
        r_crit = self.provider.read_temperatures()[0]
        self.assertEqual(r_crit.status, HealthStatus.CRITICAL)
        self.assertEqual(r_crit.temperature_celsius, 96.0)

    def test_wmi_thermal_zone_permission_denied(self) -> None:
        """Error de acceso denegado (0x80041003) degrada a ERROR con nota clara de permisos."""
        self.runner.run.return_value = mock_cmd_result(
            "",
            PowerShellQuery.THERMAL_ZONE,
            exit_code=1,
            error="Acceso denegado (HRESULT 0x80041003)",
        )
        readings = self.provider.read_temperatures()
        self.assertEqual(len(readings), 1)
        r = readings[0]
        self.assertEqual(r.status, HealthStatus.ERROR)
        self.assertIsNone(r.temperature_celsius)
        self.assertIn("permiso", r.detail.lower())

    def test_wmi_thermal_zone_timeout(self) -> None:
        """Timeout de consulta WMI degrada a ERROR sin colapsar."""
        self.runner.run.return_value = CommandResult(
            query=PowerShellQuery.THERMAL_ZONE,
            output="",
            exit_code=-1,
            timed_out=True,
            error="Timeout",
        )
        readings = self.provider.read_temperatures()
        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0].status, HealthStatus.ERROR)
        self.assertIn("agotado", readings[0].detail.lower())

    def test_wmi_thermal_zone_empty_or_unsupported(self) -> None:
        """Si la placa no expone zonas térmicas ACPI se reporta NOT_SUPPORTED."""
        self.runner.run.return_value = mock_cmd_result("[]", PowerShellQuery.THERMAL_ZONE)
        readings = self.provider.read_temperatures()
        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0].status, HealthStatus.NOT_SUPPORTED)
        self.assertFalse(readings[0].is_supported)


class StorageThermalProviderTests(TestCase):
    """Pruebas de reutilización de temperatura SMART / Reliability de F2."""

    def test_storage_thermal_healthy(self) -> None:
        rows = [
            {"FriendlyName": "NVMe Drive 1", "Temperature": 42},
            {"FriendlyName": "SATA SSD 2", "Temperature": 33},
        ]
        provider = StorageThermalProvider(rows)
        self.assertTrue(provider.is_available())
        readings = provider.read_temperatures()
        self.assertEqual(len(readings), 2)
        self.assertEqual(readings[0].temperature_celsius, 42.0)
        self.assertEqual(readings[0].status, HealthStatus.NORMAL)
        self.assertEqual(readings[1].temperature_celsius, 33.0)

    def test_storage_thermal_warning_and_critical(self) -> None:
        rows = [
            {"FriendlyName": "Hot SSD", "Temperature": 58},  # >= 55 -> WARNING
            {"FriendlyName": "Boiling SSD", "Temperature": 72},  # >= 70 -> CRITICAL
        ]
        provider = StorageThermalProvider(rows)
        readings = provider.read_temperatures()
        self.assertEqual(readings[0].status, HealthStatus.WARNING)
        self.assertEqual(readings[1].status, HealthStatus.CRITICAL)

    def test_storage_thermal_no_temp_sensor(self) -> None:
        rows = [
            {"FriendlyName": "Drive Without Temp", "Temperature": None},
        ]
        provider = StorageThermalProvider(rows)
        readings = provider.read_temperatures()
        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0].status, HealthStatus.NOT_SUPPORTED)
        self.assertIsNone(readings[0].temperature_celsius)


class NvidiaGpuThermalProviderTests(TestCase):
    """Pruebas de consulta y parseo estricto a nvidia-smi."""

    def setUp(self) -> None:
        self.runner = MagicMock()
        self.provider = NvidiaGpuThermalProvider(
            runner=self.runner,
            custom_binary_path=r"C:\Windows\System32\nvidia-smi.exe",
        )

    def test_nvidia_smi_valid_healthy(self) -> None:
        """Parseo de CSV de 9 columnas con temperatura normal y sin throttling."""
        csv_out = "0, NVIDIA GeForce GTX 1050 Ti, 35, 15, 40, [N/A], 607, Not Active, Not Active\n"
        self.runner.nvidia_smi_query.return_value = NativeCommandResult(
            command=("nvidia-smi.exe",),
            output=csv_out,
            exit_code=0,
        )

        readings = self.provider.read_temperatures()
        self.assertEqual(len(readings), 1)
        r = readings[0]
        self.assertEqual(r.temperature_celsius, 35.0)
        self.assertEqual(r.fan_rpm, 40)
        self.assertIsNone(r.power_watts)  # [N/A] parseado a None
        self.assertEqual(r.clock_mhz, 607.0)
        self.assertFalse(r.is_throttling)
        self.assertEqual(r.status, HealthStatus.NORMAL)
        self.assertEqual(r.confidence, ConfidenceLevel.HIGH)

    def test_nvidia_smi_throttling_triggers_critical(self) -> None:
        """Banderas explícitas de hw_thermal_slowdown o sw_thermal_slowdown activan CRITICAL."""
        csv_out = "0, NVIDIA RTX 3080, 84, 99, 100, 320.5, 1400, Active, Not Active\n"
        self.runner.nvidia_smi_query.return_value = NativeCommandResult(
            command=("nvidia-smi.exe",),
            output=csv_out,
            exit_code=0,
        )
        readings = self.provider.read_temperatures()
        self.assertEqual(len(readings), 1)
        r = readings[0]
        self.assertTrue(r.is_throttling)
        self.assertEqual(r.status, HealthStatus.CRITICAL)
        self.assertIn("Throttling ACTIVO", r.detail)
        self.assertEqual(r.power_watts, 320.5)

    def test_nvidia_smi_binary_missing(self) -> None:
        """Si nvidia-smi no existe en ruta de confianza devuelve NOT_SUPPORTED."""
        provider = NvidiaGpuThermalProvider(runner=self.runner, custom_binary_path="")
        self.assertFalse(provider.is_available())
        readings = provider.read_temperatures()
        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0].status, HealthStatus.NOT_SUPPORTED)

    def test_nvidia_smi_timeout_or_error(self) -> None:
        """Fallo de timeout en nvidia-smi produce ERROR."""
        self.runner.nvidia_smi_query.return_value = NativeCommandResult(
            command=("nvidia-smi.exe",),
            output="",
            exit_code=-1,
            timed_out=True,
            error="Timeout",
        )
        readings = self.provider.read_temperatures()
        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0].status, HealthStatus.ERROR)

    def test_nvidia_smi_malformed_csv(self) -> None:
        """Salida malformada o incompleta se maneja sin lanzar excepción no capturada."""
        self.runner.nvidia_smi_query.return_value = NativeCommandResult(
            command=("nvidia-smi.exe",),
            output="Incomplete line, only, two cols",
            exit_code=0,
        )
        readings = self.provider.read_temperatures()
        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0].status, HealthStatus.NOT_SUPPORTED)


class ThermalVerticalSliceIntegrationTests(TestCase):
    """Integración vertical: Recolector -> Motor -> Recomendaciones -> Reportes."""

    def test_cpu_collector_with_thermal_provider(self) -> None:
        ps_runner = MagicMock()
        ps_runner.run.return_value = mock_cmd_result(
            '[{"Name":"Intel Core i7-10700K"}]',
            PowerShellQuery.CPU_INFO,
        )

        mock_thermal = MagicMock()
        mock_thermal.read_temperatures.return_value = [
            ThermalReading(
                source_name="TZ01",
                target_hardware="CPU",
                temperature_celsius=48.0,
                unit="°C",
                collected_at=_now(),
                duration_seconds=0.01,
                confidence=ConfidenceLevel.HIGH,
                status=HealthStatus.NORMAL,
                is_supported=True,
                detail="Temperatura ACPI: 48.0 °C",
                measurements=(Measurement("Temperatura (TZ01)", 48.0, "°C"),),
            )
        ]

        def mock_cpu_percent(interval: float | None = None, percpu: bool = False) -> Any:
            return [15.0, 15.0] if percpu else 15.0

        with patch("psutil.cpu_percent", side_effect=mock_cpu_percent), patch("psutil.cpu_count", return_value=8), patch("psutil.cpu_freq", return_value=None):
            collector = CpuCollector(ps_runner, thermal_provider=mock_thermal)
            res = collector.collect()

        self.assertEqual(res.status, HealthStatus.NORMAL)
        self.assertIn("Telemetría térmica CPU", res.facts)
        meas_names = [m.name for m in res.measurements]
        self.assertIn("Temperatura (TZ01)", meas_names)

    def test_gpu_collector_with_thermal_provider(self) -> None:
        ps_runner = MagicMock()
        ps_runner.run.return_value = mock_cmd_result(
            '[{"Tipo":"GPU","Nombre":"NVIDIA GeForce GTX 1050 Ti","Estado":"OK"}]',
            PowerShellQuery.VIDEO_CONTROLLERS,
        )

        mock_thermal = MagicMock()
        mock_thermal.read_temperatures.return_value = [
            ThermalReading(
                source_name="GPU 0: NVIDIA GeForce GTX 1050 Ti",
                target_hardware="GPU",
                temperature_celsius=84.0,
                unit="°C",
                collected_at=_now(),
                duration_seconds=0.02,
                confidence=ConfidenceLevel.HIGH,
                status=HealthStatus.WARNING,
                is_supported=True,
                detail="Telemetría GPU NVIDIA oficial: 84 °C",
                measurements=(Measurement("Temperatura GPU (1050 Ti)", 84.0, "°C"),),
            )
        ]

        collector = GpuCollector(ps_runner, thermal_provider=mock_thermal)
        res = collector.collect()

        self.assertEqual(res.status, HealthStatus.WARNING)
        self.assertIn("Telemetría térmica GPU", res.facts)
        self.assertIn("Temperatura elevada en GPU", str(res.possible_problem) or "")

    def test_reports_serialization_with_thermal_data(self) -> None:
        """Reportes JSON, HTML y TXT exportan mediciones térmicas sin romper compatibilidad."""
        mock_evidence = MagicMock()
        mock_evidence.source = "NVIDIA SMI"
        mock_evidence.query = "nvidia-smi"
        mock_evidence.output = "35 C"
        mock_evidence.collected_at = _now()
        mock_evidence.succeeded = True

        res = ComponentResult(
            component=ComponentKind.MONITOR_GPU,
            name="Monitor y GPU",
            facts={
                "Telemetría térmica GPU": [
                    {"Dispositivo": "GTX 1050 Ti", "Temperatura": "35 °C", "Estado": "normal"}
                ]
            },
            summary="1 GPU · Estado OK",
            status=HealthStatus.NORMAL,
            evidence=(mock_evidence,),
            measurements=(
                Measurement("Temperatura GPU", 35.0, "°C", (0.0, 85.0)),
            ),
        )

        engine = RuleBasedDiagnosticEngine()
        report = engine.build_report([res])

        # JSON
        payload = build_payload(report)
        self.assertIn("resultados", payload)
        gpu_json = payload["resultados"][0]
        self.assertEqual(gpu_json["mediciones"][0]["nombre"], "Temperatura GPU")
        self.assertEqual(gpu_json["mediciones"][0]["valor"], 35.0)

        # TXT
        text = render_text(report)
        self.assertIn("Monitor y GPU", text)
        self.assertIn("Normal", text)

        # HTML
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "report.html"
            export_html(report, out_file)
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("Monitor y GPU", content)
            self.assertIn("Telemetría térmica GPU", content)
