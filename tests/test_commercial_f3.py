"""Pruebas unitarias y de integración de la Fase F3 Comercial: Sensores y comportamiento térmico."""

import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest import TestCase
from unittest.mock import MagicMock, patch

from hardware_admin.collectors.core import (
    CpuCollector,
    MonitorGpuCollector,
    SystemCollector,
    build_default_collectors,
)
from hardware_admin.collectors.gpu import GpuCollector
from hardware_admin.collectors.storage import StorageCollector
from hardware_admin.diagnostics.engine import RuleBasedDiagnosticEngine
from hardware_admin.diagnostics.thermal import (
    CompositeThermalProvider,
    NullThermalProvider,
    NvidiaGpuThermalProvider,
    StorageThermalProvider,
    ThermalSnapshotProvider,
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
from hardware_admin.infrastructure.commands import (
    NativeCommandResult,
    SafeCommandRunner,
    is_trusted_nvidia_smi_path,
)
from hardware_admin.infrastructure.powershell import (
    CommandResult,
    PowerShellQuery,
    SafePowerShellRunner,
)
from hardware_admin.reports.html_report import export_html
from hardware_admin.reports.json_report import build_payload
from hardware_admin.reports.txt_report import render_text
from hardware_admin.services.scan_service import ScanService


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
        """ThermalReading modela todos los campos obligatorios tipados con fan_percent."""
        reading = ThermalReading(
            source_name="Sensor 1",
            target_hardware="THERMAL_ZONE",
            temperature_celsius=45.5,
            unit="°C",
            collected_at=_now(),
            duration_seconds=0.05,
            confidence=ConfidenceLevel.HIGH,
            status=HealthStatus.NORMAL,
            is_supported=True,
            detail="Zona térmica ACPI; no atribuible de forma confiable a CPU (45.5 °C)",
            is_throttling=False,
            fan_percent=55,
            fan_rpm=None,
            power_watts=45.0,
            clock_mhz=3200.0,
        )
        self.assertEqual(reading.source_name, "Sensor 1")
        self.assertEqual(reading.target_hardware, "THERMAL_ZONE")
        self.assertEqual(reading.temperature_celsius, 45.5)
        self.assertEqual(reading.unit, "°C")
        self.assertEqual(reading.confidence, ConfidenceLevel.HIGH)
        self.assertEqual(reading.status, HealthStatus.NORMAL)
        self.assertTrue(reading.is_supported)
        self.assertFalse(reading.is_throttling)
        self.assertEqual(reading.fan_percent, 55)
        self.assertIsNone(reading.fan_rpm)
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
        """Zonas térmicas con 3082 dK (35.0 °C) generan estado NORMAL, confianza HIGH y target THERMAL_ZONE."""
        wmi_json = '[{"InstanceName":"ACPI\\\\ThermalZone\\\\TZ01_0","CurrentTemperature":3082,"CriticalTripPoint":3732}]'
        self.runner.run.return_value = mock_cmd_result(wmi_json, PowerShellQuery.THERMAL_ZONE)

        readings = self.provider.read_temperatures()
        self.assertEqual(len(readings), 1)
        r = readings[0]
        self.assertEqual(r.target_hardware, "THERMAL_ZONE")
        self.assertEqual(r.status, HealthStatus.NORMAL)
        self.assertEqual(r.temperature_celsius, 35.0)
        self.assertEqual(r.confidence, ConfidenceLevel.HIGH)
        self.assertTrue(r.is_supported)
        self.assertIn("Zona térmica ACPI; no atribuible de forma confiable a CPU", r.detail)
        self.assertEqual(len(r.measurements), 1)
        self.assertEqual(r.measurements[0].value, 35.0)

    def test_wmi_thermal_zone_warning_and_critical(self) -> None:
        """Zonas térmicas a 82 °C dan WARNING; a 96 °C dan CRITICAL pero conservan target THERMAL_ZONE."""
        # 82 °C -> 2732 + 820 = 3552 dK
        wmi_json_warn = '[{"InstanceName":"TZ01","CurrentTemperature":3552}]'
        self.runner.run.return_value = mock_cmd_result(wmi_json_warn, PowerShellQuery.THERMAL_ZONE)
        r_warn = self.provider.read_temperatures()[0]
        self.assertEqual(r_warn.target_hardware, "THERMAL_ZONE")
        self.assertEqual(r_warn.status, HealthStatus.WARNING)
        self.assertEqual(r_warn.temperature_celsius, 82.0)

        # 96 °C -> 2732 + 960 = 3692 dK
        wmi_json_crit = '[{"InstanceName":"TZ01","CurrentTemperature":3692}]'
        self.runner.run.return_value = mock_cmd_result(wmi_json_crit, PowerShellQuery.THERMAL_ZONE)
        r_crit = self.provider.read_temperatures()[0]
        self.assertEqual(r_crit.target_hardware, "THERMAL_ZONE")
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
        self.assertEqual(r.target_hardware, "THERMAL_ZONE")
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
        self.assertEqual(readings[0].target_hardware, "THERMAL_ZONE")
        self.assertEqual(readings[0].status, HealthStatus.ERROR)
        self.assertIn("agotado", readings[0].detail.lower())

    def test_wmi_thermal_zone_empty_or_unsupported(self) -> None:
        """Si la placa no expone zonas térmicas ACPI se reporta NOT_SUPPORTED."""
        self.runner.run.return_value = mock_cmd_result("[]", PowerShellQuery.THERMAL_ZONE)
        readings = self.provider.read_temperatures()
        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0].target_hardware, "THERMAL_ZONE")
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


class NvidiaGpuThermalProviderAndSecurityTests(TestCase):
    """Pruebas de consulta, endurecimiento de rutas de confianza y parseo estricto de 9 columnas."""

    def setUp(self) -> None:
        self.runner = MagicMock()
        self.provider = NvidiaGpuThermalProvider(
            runner=self.runner,
            custom_binary_path=r"C:\Windows\System32\nvidia-smi.exe",
        )

    def test_nvidia_smi_valid_healthy_with_fan_percent(self) -> None:
        """Parseo de CSV de 9 columnas exactas; fan.speed se modela como porcentaje (fan_percent)."""
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
        self.assertEqual(r.fan_percent, 40)
        self.assertIsNone(r.fan_rpm)
        self.assertIsNone(r.power_watts)
        self.assertEqual(r.clock_mhz, 607.0)
        self.assertFalse(r.is_throttling)
        self.assertEqual(r.status, HealthStatus.NORMAL)
        self.assertEqual(r.confidence, ConfidenceLevel.HIGH)

        fan_meas = [m for m in r.measurements if "Ventilador" in m.name]
        self.assertEqual(len(fan_meas), 1)
        self.assertEqual(fan_meas[0].unit, "%")
        self.assertEqual(fan_meas[0].value, 40)

    def test_nvidia_smi_strict_9_columns_rejects_fewer_columns(self) -> None:
        """CSV con 8 columnas (faltantes) se rechaza estrictamente."""
        csv_8_cols = "0, GPU, 40, 20, 50, 100, 1200, Not Active\n"
        self.runner.nvidia_smi_query.return_value = NativeCommandResult(
            command=("nvidia-smi.exe",),
            output=csv_8_cols,
            exit_code=0,
        )
        readings = self.provider.read_temperatures()
        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0].status, HealthStatus.NOT_SUPPORTED)

    def test_nvidia_smi_strict_9_columns_rejects_extra_columns(self) -> None:
        """CSV con 10 columnas (de más) se rechaza estrictamente."""
        csv_10_cols = "0, GPU, 40, 20, 50, 100, 1200, Not Active, Not Active, ExtraCol\n"
        self.runner.nvidia_smi_query.return_value = NativeCommandResult(
            command=("nvidia-smi.exe",),
            output=csv_10_cols,
            exit_code=0,
        )
        readings = self.provider.read_temperatures()
        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0].status, HealthStatus.NOT_SUPPORTED)

    def test_safe_command_runner_rejects_untrusted_nvidia_smi_path(self) -> None:
        """SafeCommandRunner rechaza rutas arbitrarias fuera del allowlist sin invocar subprocesos."""
        runner = SafeCommandRunner()
        res = runner.nvidia_smi_query(r"C:\arbitrary\path\nvidia-smi.exe")
        self.assertEqual(res.exit_code, -1)
        self.assertIn("no confiable", res.error)

    def test_safe_command_runner_accepts_trusted_nvidia_smi_path(self) -> None:
        """SafeCommandRunner acepta rutas verificadas en allowlist oficial."""
        self.assertTrue(is_trusted_nvidia_smi_path(r"C:\Windows\System32\nvidia-smi.exe"))
        self.assertTrue(
            is_trusted_nvidia_smi_path(r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe")
        )
        self.assertFalse(is_trusted_nvidia_smi_path(r"C:\Users\test\nvidia-smi.exe"))

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


class ThermalSnapshotAndDeduplicationTests(TestCase):
    """Garantía de cero duplicación de consultas en escaneo completo y consumo de snapshot idéntico."""

    def test_thermal_snapshot_provider_caches_identically(self) -> None:
        mock_sub = MagicMock()
        mock_sub.is_available.return_value = True
        mock_sub.read_temperatures.return_value = [
            ThermalReading(
                source_name="TZ01",
                target_hardware="THERMAL_ZONE",
                temperature_celsius=40.0,
                unit="°C",
                collected_at=_now(),
                duration_seconds=0.01,
                confidence=ConfidenceLevel.HIGH,
                status=HealthStatus.NORMAL,
                is_supported=True,
                detail="Zona térmica ACPI; no atribuible de forma confiable a CPU (40.0 °C)",
            )
        ]

        snapshot_provider = ThermalSnapshotProvider(mock_sub)
        res1 = snapshot_provider.read_temperatures()
        res2 = snapshot_provider.read_temperatures()

        self.assertEqual(mock_sub.read_temperatures.call_count, 1)
        self.assertIs(res1, res2)

    def test_acpi_thermal_zone_does_not_degrade_cpu_status(self) -> None:
        """Una zona térmica ACPI alta (98 °C) NO degrada el estado de CPU a CRITICAL ni WARNING."""
        ps_runner = MagicMock()
        ps_runner.run.return_value = mock_cmd_result(
            '[{"Name":"Intel Core i7"}]',
            PowerShellQuery.CPU_INFO,
        )

        mock_thermal = MagicMock()
        mock_thermal.read_temperatures.return_value = [
            ThermalReading(
                source_name="ACPI Thermal Zone",
                target_hardware="THERMAL_ZONE",
                temperature_celsius=98.0,
                unit="°C",
                collected_at=_now(),
                duration_seconds=0.01,
                confidence=ConfidenceLevel.HIGH,
                status=HealthStatus.CRITICAL,
                is_supported=True,
                detail="Zona térmica ACPI; no atribuible de forma confiable a CPU (98.0 °C)",
            )
        ]

        def mock_cpu(interval: float | None = None, percpu: bool = False) -> Any:
            return [12.0] if percpu else 12.0

        with patch("psutil.cpu_percent", side_effect=mock_cpu), patch("psutil.cpu_count", return_value=8), patch("psutil.cpu_freq", return_value=None):
            collector = CpuCollector(ps_runner, thermal_provider=mock_thermal)
            res = collector.collect()

        self.assertEqual(res.status, HealthStatus.NORMAL)
        self.assertIsNone(res.possible_problem)
        self.assertIn("Zona térmica ACPI; no atribuible de forma confiable a CPU", res.facts.get("Zonas térmicas ACPI", ""))

    def test_single_query_per_provider_during_full_scan(self) -> None:
        """En un escaneo completo, WMI térmico y nvidia-smi se ejecutan como máximo 1 vez."""
        wmi_counter = {"calls": 0}
        nvidia_counter = {"calls": 0}
        storage_rel_counter = {"calls": 0}

        def mock_ps_run(query: PowerShellQuery, use_cache: bool = True) -> CommandResult:
            if query == PowerShellQuery.THERMAL_ZONE:
                wmi_counter["calls"] += 1
                return mock_cmd_result(
                    '[{"InstanceName":"TZ01","CurrentTemperature":3100}]',
                    PowerShellQuery.THERMAL_ZONE,
                )
            if query == PowerShellQuery.STORAGE_RELIABILITY:
                storage_rel_counter["calls"] += 1
                return mock_cmd_result(
                    '[{"FriendlyName":"SSD 1","Temperature":38,"DeviceId":0}]',
                    PowerShellQuery.STORAGE_RELIABILITY,
                )
            if query == PowerShellQuery.VIDEO_CONTROLLERS:
                return mock_cmd_result(
                    '[{"Tipo":"GPU","Nombre":"NVIDIA GPU","Estado":"OK"}]',
                    PowerShellQuery.VIDEO_CONTROLLERS,
                )
            if query == PowerShellQuery.PHYSICAL_DISKS:
                return mock_cmd_result(
                    '[{"DeviceId":0,"FriendlyName":"SSD 1","MediaType":"SSD","BusType":"NVMe","HealthStatus":"Healthy","Size":512000000000}]',
                    PowerShellQuery.PHYSICAL_DISKS,
                )
            if query == PowerShellQuery.DISKS:
                return mock_cmd_result(
                    '[{"Number":0,"FriendlyName":"SSD 1","BusType":"NVMe","HealthStatus":"Healthy","Size":512000000000}]',
                    PowerShellQuery.DISKS,
                )
            if query == PowerShellQuery.VOLUMES:
                return mock_cmd_result(
                    '[{"DriveLetter":"C","FileSystem":"NTFS","Size":500000000000,"SizeRemaining":300000000000,"HealthStatus":"Healthy"}]',
                    PowerShellQuery.VOLUMES,
                )
            if query == PowerShellQuery.USB_STORAGE:
                return mock_cmd_result('[]', PowerShellQuery.USB_STORAGE)
            return mock_cmd_result('[]', query)

        class MockSafePowerShellRunner(SafePowerShellRunner):
            def run(self, query: PowerShellQuery, use_cache: bool = True) -> CommandResult:
                if use_cache and query in self._cache:
                    return self._cache[query]
                res = mock_ps_run(query, use_cache)
                if use_cache:
                    self._cache[query] = res
                return res

        class MockSafeCommandRunner(SafeCommandRunner):
            def nvidia_smi_query(self, binary_path: str, timeout: float = 5.0) -> NativeCommandResult:
                nvidia_counter["calls"] += 1
                return NativeCommandResult(
                    command=("nvidia-smi",),
                    output="0, NVIDIA GPU, 42, 10, 30, 50.0, 1000, Not Active, Not Active\n",
                    exit_code=0,
                )

        runner = MockSafePowerShellRunner()
        cmd_runner = MockSafeCommandRunner()

        wmi_provider = WmiThermalZoneProvider(runner)
        gpu_provider = NvidiaGpuThermalProvider(
            runner=cmd_runner,
            custom_binary_path=r"C:\Windows\System32\nvidia-smi.exe",
        )
        storage_provider = StorageThermalProvider(runner=runner)

        composite = CompositeThermalProvider((wmi_provider, gpu_provider, storage_provider))
        snapshot_provider = ThermalSnapshotProvider(composite)

        collectors = (
            SystemCollector(runner, thermal_provider=snapshot_provider),
            CpuCollector(runner, thermal_provider=snapshot_provider),
            StorageCollector(runner, thermal_provider=snapshot_provider),
            MonitorGpuCollector(runner, thermal_provider=snapshot_provider),
        )

        def mock_scan_cpu(interval: float | None = None, percpu: bool = False) -> Any:
            return [10.0] if percpu else 10.0

        with patch("psutil.cpu_percent", side_effect=mock_scan_cpu), \
             patch("psutil.cpu_count", return_value=8), \
             patch("psutil.cpu_freq", return_value=None), \
             patch("psutil.disk_partitions", return_value=[]), \
             patch("psutil.disk_usage", side_effect=OSError):
            service = ScanService(collectors=collectors, diagnostic_engine=RuleBasedDiagnosticEngine())
            report = service.scan()

        self.assertLessEqual(wmi_counter["calls"], 1)
        self.assertLessEqual(nvidia_counter["calls"], 1)
        self.assertLessEqual(storage_rel_counter["calls"], 1)

        sys_res = next(r for r in report.results if r.component == ComponentKind.SYSTEM)
        self.assertIn("Sensores térmicos del equipo", sys_res.facts)

        storage_res = next(r for r in report.results if r.component == ComponentKind.DISK)
        self.assertIn("Telemetría térmica de almacenamiento", storage_res.facts)

        gpu_res = next(r for r in report.results if r.component == ComponentKind.MONITOR_GPU)
        self.assertIn("Telemetría térmica GPU", gpu_res.facts)

    def test_build_default_collectors_wiring(self) -> None:
        """build_default_collectors cablea los recolectores con ThermalSnapshotProvider por defecto."""
        collectors = build_default_collectors()
        self.assertTrue(any(isinstance(c, StorageCollector) for c in collectors))
        self.assertTrue(any(isinstance(c, SystemCollector) for c in collectors))
        self.assertTrue(any(isinstance(c, CpuCollector) for c in collectors))
        self.assertTrue(any(isinstance(c, MonitorGpuCollector) for c in collectors))

    def test_two_consecutive_scans_reexecute_and_return_fresh_values(self) -> None:
        """Dos ScanService.scan() consecutivos ejecutan las fuentes 1 vez por scan (2 en total) y usan valores actuales."""
        wmi_counter = {"calls": 0}
        nvidia_counter = {"calls": 0}
        storage_rel_counter = {"calls": 0}

        def mock_ps_run(query: PowerShellQuery, use_cache: bool = True) -> CommandResult:
            if query == PowerShellQuery.THERMAL_ZONE:
                wmi_counter["calls"] += 1
                # Primer scan: 3132 dK (40.0 °C); Segundo scan: 3282 dK (55.0 °C)
                temp_dk = 3132 if wmi_counter["calls"] == 1 else 3282
                return mock_cmd_result(
                    f'[{{"InstanceName":"TZ01","CurrentTemperature":{temp_dk}}}]',
                    PowerShellQuery.THERMAL_ZONE,
                )
            if query == PowerShellQuery.STORAGE_RELIABILITY:
                storage_rel_counter["calls"] += 1
                temp_c = 35 if storage_rel_counter["calls"] == 1 else 50
                return mock_cmd_result(
                    f'[{{"FriendlyName":"SSD 1","Temperature":{temp_c},"DeviceId":0}}]',
                    PowerShellQuery.STORAGE_RELIABILITY,
                )
            if query == PowerShellQuery.VIDEO_CONTROLLERS:
                return mock_cmd_result(
                    '[{"Tipo":"GPU","Nombre":"NVIDIA GPU","Estado":"OK"}]',
                    PowerShellQuery.VIDEO_CONTROLLERS,
                )
            if query == PowerShellQuery.PHYSICAL_DISKS:
                return mock_cmd_result(
                    '[{"DeviceId":0,"FriendlyName":"SSD 1","MediaType":"SSD","BusType":"NVMe","HealthStatus":"Healthy","Size":512000000000}]',
                    PowerShellQuery.PHYSICAL_DISKS,
                )
            if query == PowerShellQuery.DISKS:
                return mock_cmd_result(
                    '[{"Number":0,"FriendlyName":"SSD 1","BusType":"NVMe","HealthStatus":"Healthy","Size":512000000000}]',
                    PowerShellQuery.DISKS,
                )
            if query == PowerShellQuery.VOLUMES:
                return mock_cmd_result(
                    '[{"DriveLetter":"C","FileSystem":"NTFS","Size":500000000000,"SizeRemaining":300000000000,"HealthStatus":"Healthy"}]',
                    PowerShellQuery.VOLUMES,
                )
            return mock_cmd_result('[]', query)

        class MockSafePowerShellRunner(SafePowerShellRunner):
            def run(self, query: PowerShellQuery, use_cache: bool = True) -> CommandResult:
                if use_cache and query in self._cache:
                    return self._cache[query]
                res = mock_ps_run(query, use_cache)
                if use_cache:
                    self._cache[query] = res
                return res

        class MockSafeCommandRunner(SafeCommandRunner):
            def nvidia_smi_query(self, binary_path: str, timeout: float = 5.0) -> NativeCommandResult:
                nvidia_counter["calls"] += 1
                temp_gpu = 42 if nvidia_counter["calls"] == 1 else 68
                return NativeCommandResult(
                    command=("nvidia-smi",),
                    output=f"0, NVIDIA GPU, {temp_gpu}, 10, 30, 50.0, 1000, Not Active, Not Active\n",
                    exit_code=0,
                )

        runner = MockSafePowerShellRunner()
        cmd_runner = MockSafeCommandRunner()

        wmi_provider = WmiThermalZoneProvider(runner)
        gpu_provider = NvidiaGpuThermalProvider(
            runner=cmd_runner,
            custom_binary_path=r"C:\Windows\System32\nvidia-smi.exe",
        )
        storage_provider = StorageThermalProvider(runner=runner)

        composite = CompositeThermalProvider((wmi_provider, gpu_provider, storage_provider))
        snapshot_provider = ThermalSnapshotProvider(composite)

        collectors = (
            SystemCollector(runner, thermal_provider=snapshot_provider),
            CpuCollector(runner, thermal_provider=snapshot_provider),
            StorageCollector(runner, thermal_provider=snapshot_provider),
            MonitorGpuCollector(runner, thermal_provider=snapshot_provider),
        )

        def mock_scan_cpu(interval: float | None = None, percpu: bool = False) -> Any:
            return [10.0] if percpu else 10.0

        with patch("psutil.cpu_percent", side_effect=mock_scan_cpu), \
             patch("psutil.cpu_count", return_value=8), \
             patch("psutil.cpu_freq", return_value=None), \
             patch("psutil.disk_partitions", return_value=[]), \
             patch("psutil.disk_usage", side_effect=OSError):
            service = ScanService(collectors=collectors, diagnostic_engine=RuleBasedDiagnosticEngine())

            # PRIMER ESCANEO
            report1 = service.scan()

            self.assertEqual(wmi_counter["calls"], 1)
            self.assertEqual(nvidia_counter["calls"], 1)
            self.assertEqual(storage_rel_counter["calls"], 1)

            sys1 = next(r for r in report1.results if r.component == ComponentKind.SYSTEM)
            sensors1 = {s["Origen"]: s["Temperatura"] for s in sys1.facts["Sensores térmicos del equipo"]}
            self.assertEqual(sensors1["TZ01"], "40.0 °C")
            self.assertEqual(sensors1["GPU 0: NVIDIA GPU"], "42.0 °C")
            self.assertEqual(sensors1["Almacenamiento: SSD 1"], "35.0 °C")

            disk1 = next(r for r in report1.results if r.component == ComponentKind.DISK)
            self.assertEqual(disk1.facts["Telemetría térmica de almacenamiento"][0]["Temperatura"], "35.0 °C")

            gpu1 = next(r for r in report1.results if r.component == ComponentKind.MONITOR_GPU)
            self.assertEqual(gpu1.facts["Telemetría térmica GPU"][0]["Temperatura"], "42.0 °C")

            # SEGUNDO ESCANEO CONSECUTIVO
            report2 = service.scan()

            # Cada fuente se ejecutó exactamente 1 vez adicional (2 en total)
            self.assertEqual(wmi_counter["calls"], 2)
            self.assertEqual(nvidia_counter["calls"], 2)
            self.assertEqual(storage_rel_counter["calls"], 2)

            sys2 = next(r for r in report2.results if r.component == ComponentKind.SYSTEM)
            sensors2 = {s["Origen"]: s["Temperatura"] for s in sys2.facts["Sensores térmicos del equipo"]}
            self.assertEqual(sensors2["TZ01"], "55.0 °C")
            self.assertEqual(sensors2["GPU 0: NVIDIA GPU"], "68.0 °C")
            self.assertEqual(sensors2["Almacenamiento: SSD 1"], "50.0 °C")

            disk2 = next(r for r in report2.results if r.component == ComponentKind.DISK)
            self.assertEqual(disk2.facts["Telemetría térmica de almacenamiento"][0]["Temperatura"], "50.0 °C")

            gpu2 = next(r for r in report2.results if r.component == ComponentKind.MONITOR_GPU)
            self.assertEqual(gpu2.facts["Telemetría térmica GPU"][0]["Temperatura"], "68.0 °C")

    def test_safe_powershell_runner_session_cache_and_reset(self) -> None:
        """SafePowerShellRunner cachea dentro de una sesión y se limpia con reset_session()."""
        call_count = {"calls": 0}

        def mock_subp_run(*args: Any, **kwargs: Any) -> Any:
            call_count["calls"] += 1
            mock_res = MagicMock()
            mock_res.returncode = 0
            mock_res.stdout = '[{"Name":"Test"}]'
            mock_res.stderr = ""
            return mock_res

        runner = SafePowerShellRunner()
        with patch("subprocess.run", side_effect=mock_subp_run):
            # Primera llamada en sesión 1: ejecuta subprocess
            res1 = runner.run(PowerShellQuery.STORAGE_RELIABILITY)
            self.assertEqual(call_count["calls"], 1)
            self.assertEqual(res1.output, '[{"Name":"Test"}]')

            # Segunda llamada en sesión 1: resultado en caché, no ejecuta subprocess
            res2 = runner.run(PowerShellQuery.STORAGE_RELIABILITY)
            self.assertEqual(call_count["calls"], 1)
            self.assertIs(res1, res2)

            # Inicia nueva sesión
            runner.reset_session()

            # Tercera llamada en sesión 2: caché limpia, ejecuta subprocess nuevamente
            res3 = runner.run(PowerShellQuery.STORAGE_RELIABILITY)
            self.assertEqual(call_count["calls"], 2)
            self.assertEqual(res3.output, '[{"Name":"Test"}]')

    def test_scan_service_partial_scan_prepares_session(self) -> None:
        """ScanService.scan() con 'only' reinicia los recolectores seleccionados."""
        runner = SafePowerShellRunner()
        mock_provider = MagicMock()
        mock_provider.read_temperatures.return_value = []
        cpu_collector = CpuCollector(runner, thermal_provider=mock_provider)

        engine = RuleBasedDiagnosticEngine()
        service = ScanService(collectors=(cpu_collector,), diagnostic_engine=engine)

        with patch("psutil.cpu_percent", return_value=5.0), \
             patch("psutil.cpu_count", return_value=4), \
             patch("psutil.cpu_freq", return_value=None), \
             patch.object(runner, "run", return_value=mock_cmd_result('[]', PowerShellQuery.CPU_INFO)):
            report = service.scan(only=[ComponentKind.CPU])

        self.assertEqual(len(report.results), 1)
        self.assertEqual(report.results[0].component, ComponentKind.CPU)

    def test_safe_powershell_runner_concurrent_requests_execute_once(self) -> None:
        """Hilos concurrentes que solicitan la misma consulta esperan y ejecutan una sola vez."""
        barrier = threading.Barrier(3)
        exec_count = {"count": 0}

        class ConcurrentRunner(SafePowerShellRunner):
            def _execute_query(self, query: PowerShellQuery, script: str) -> CommandResult:
                exec_count["count"] += 1
                time.sleep(0.05)
                return mock_cmd_result('[{"Result":"OK"}]', query)

        runner = ConcurrentRunner()
        results: list[CommandResult] = [None] * 3  # type: ignore[list-item]

        def worker(index: int) -> None:
            barrier.wait(timeout=3.0)
            results[index] = runner.run(PowerShellQuery.STORAGE_RELIABILITY)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        self.assertEqual(exec_count["count"], 1)
        self.assertEqual(len(results), 3)
        self.assertIsNotNone(results[0])
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1], results[2])

    def test_deterministic_race_condition_storage_reliability_during_scan(self) -> None:
        """Sincroniza StorageCollector y StorageThermalProvider con una barrera para forzar
        la solicitud concurrente de STORAGE_RELIABILITY dentro de un mismo scan():
        garantiza exactamente 1 ejecución nativa y que ambos reciben el resultado correcto.
        """
        barrier = threading.Barrier(2)
        native_calls = {"calls": 0}

        class ConcurrentTestRunner(SafePowerShellRunner):
            def _execute_query(self, query: PowerShellQuery, script: str) -> CommandResult:
                if query == PowerShellQuery.STORAGE_RELIABILITY:
                    native_calls["calls"] += 1
                    time.sleep(0.05)  # Simular latencia de PowerShell
                    return mock_cmd_result(
                        '[{"FriendlyName":"NVMe Concurrent","Temperature":44,"DeviceId":0}]',
                        PowerShellQuery.STORAGE_RELIABILITY,
                    )
                if query == PowerShellQuery.PHYSICAL_DISKS:
                    return mock_cmd_result(
                        '[{"DeviceId":0,"FriendlyName":"NVMe Concurrent","MediaType":"SSD","BusType":"NVMe","HealthStatus":"Healthy","Size":512000000000}]',
                        PowerShellQuery.PHYSICAL_DISKS,
                    )
                if query == PowerShellQuery.DISKS:
                    return mock_cmd_result(
                        '[{"Number":0,"FriendlyName":"NVMe Concurrent","BusType":"NVMe","HealthStatus":"Healthy","Size":512000000000}]',
                        PowerShellQuery.DISKS,
                    )
                if query == PowerShellQuery.VOLUMES:
                    return mock_cmd_result(
                        '[{"DriveLetter":"C","FileSystem":"NTFS","Size":500000000000,"SizeRemaining":300000000000,"HealthStatus":"Healthy"}]',
                        PowerShellQuery.VOLUMES,
                    )
                return mock_cmd_result('[]', query)

        runner = ConcurrentTestRunner()
        original_run = runner.run

        def synced_run(query: PowerShellQuery, use_cache: bool = True) -> CommandResult:
            if query == PowerShellQuery.STORAGE_RELIABILITY:
                try:
                    barrier.wait(timeout=3.0)
                except threading.BrokenBarrierError:
                    pass
            return original_run(query, use_cache=use_cache)

        runner.run = synced_run  # type: ignore[assignment]

        storage_thermal = StorageThermalProvider(runner=runner)
        storage_collector = StorageCollector(runner)
        system_collector = SystemCollector(runner, thermal_provider=storage_thermal)

        engine = RuleBasedDiagnosticEngine()
        service = ScanService(
            collectors=(storage_collector, system_collector),
            diagnostic_engine=engine,
        )

        with patch("psutil.disk_partitions", return_value=[]), \
             patch("psutil.disk_usage", side_effect=OSError):
            report = service.scan()

        # 1. Verifica exactamente 1 ejecución nativa
        self.assertEqual(native_calls["calls"], 1)

        # 2. Verifica que StorageCollector recibió el resultado de STORAGE_RELIABILITY
        disk_res = next(r for r in report.results if r.component == ComponentKind.DISK)
        self.assertTrue(any("NVMe Concurrent" in str(d) for d in disk_res.facts.get("Discos físicos", [])))

        # 3. Verifica que StorageThermalProvider (en SystemCollector) recibió la telemetría térmica
        sys_res = next(r for r in report.results if r.component == ComponentKind.SYSTEM)
        sensors = sys_res.facts.get("Sensores térmicos del equipo", [])
        self.assertTrue(any("NVMe Concurrent" in s["Origen"] and "44" in s["Temperatura"] for s in sensors))


class ThermalVerticalSliceIntegrationTests(TestCase):
    """Integración vertical: Recolector -> Motor -> Recomendaciones -> Reportes."""

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
                fan_percent=65,
                measurements=(Measurement("Temperatura GPU (1050 Ti)", 84.0, "°C"),),
            )
        ]

        collector = GpuCollector(ps_runner, thermal_provider=mock_thermal)
        res = collector.collect()

        self.assertEqual(res.status, HealthStatus.WARNING)
        self.assertIn("Telemetría térmica GPU", res.facts)
        self.assertIn("Temperatura elevada en GPU", str(res.possible_problem) or "")
        telemetry = res.facts["Telemetría térmica GPU"][0]
        self.assertEqual(telemetry["Ventilador"], "65%")

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

    def test_thermal_dashboard_dialog_lifecycle_in_app(self) -> None:
        """Verifica que el botón de dashboard térmico y la ventana hija abren y cierran sin excepción."""
        import tkinter
        try:
            root = tkinter.Tk()
            root.destroy()
        except tkinter.TclError:
            self.skipTest("Requiere una sesión gráfica para crear ventanas Tk")

        from hardware_admin.app_factory import build_scan_service
        from hardware_admin.ui.main_window import HardwareAdminApp, ThermalDashboardWindow

        app = HardwareAdminApp(build_scan_service())
        try:
            app.update_idletasks()
            self.assertTrue(app.thermal_dashboard_button.winfo_exists())
            self.assertIn("Temperaturas y sensores", app.thermal_dashboard_button.cget("text"))

            app.open_thermal_dashboard()
            app.update_idletasks()
            self.assertIsNotNone(app.thermal_window)
            self.assertIsInstance(app.thermal_window, ThermalDashboardWindow)
            self.assertTrue(app.thermal_window.winfo_exists())
            self.assertEqual(app.thermal_window.title(), "Temperaturas y sensores")

            app.thermal_window.destroy()
            app.update_idletasks()
            self.assertFalse(app.thermal_window.winfo_exists())
        finally:
            app.destroy()
