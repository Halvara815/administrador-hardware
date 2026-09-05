"""Proveedores de telemetría térmica e interfaz abstracta desacoplada."""

from __future__ import annotations

import csv
import io
import math
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from hardware_admin.domain.models import (
    ConfidenceLevel,
    HealthStatus,
    Measurement,
    ThermalReading,
)
from hardware_admin.infrastructure.commands import (
    SafeCommandRunner,
    find_trusted_nvidia_smi,
)
from hardware_admin.infrastructure.powershell import (
    PowerShellQuery,
    SafePowerShellRunner,
    parse_json_rows,
)


def _now() -> datetime:
    return datetime.now(UTC)


def kelvin_decikelvin_to_celsius(raw_value: Any) -> float | None:
    """Convierte décimas de Kelvin (dK) de ACPI a Celsius: C = (dK - 2732) / 10.0."""
    if raw_value is None:
        return None
    try:
        val = float(raw_value)
    except (ValueError, TypeError):
        return None

    if math.isnan(val) or math.isinf(val):
        return None

    # En ACPI, la especificación define CurrentTemperature estrictamente en décimas de Kelvin.
    # Por tanto, C = (dK - 2732.0) / 10.0.
    celsius = (val - 2732.0) / 10.0

    # Rango físicamente creíble para hardware de computación (-50 °C a 150 °C)
    if not (-50.0 <= celsius <= 150.0):
        return None

    return round(celsius, 1)


class ThermalSensorProvider(ABC):
    """Contrato base para cualquier proveedor de telemetría térmica."""

    @abstractmethod
    def is_available(self) -> bool:
        """Indica si el proveedor está soportado y presente en el equipo actual."""
        ...

    @abstractmethod
    def read_temperatures(self) -> Sequence[ThermalReading]:
        """Obtiene lecturas instantáneas seguras sin bloquear ni generar falsas alertas."""
        ...


class NullThermalProvider(ThermalSensorProvider):
    """Proveedor nulo canónico: declara explícitamente telemetría no soportada."""

    def is_available(self) -> bool:
        return False

    def read_temperatures(self) -> Sequence[ThermalReading]:
        return [
            ThermalReading(
                source_name="Sin proveedor térmico activo",
                target_hardware="GLOBAL",
                temperature_celsius=None,
                unit="°C",
                collected_at=_now(),
                duration_seconds=0.0,
                confidence=ConfidenceLevel.LOW,
                status=HealthStatus.NOT_SUPPORTED,
                is_supported=False,
                detail="Telemetría térmica desactivada o hardware sin sensores accesibles",
                is_throttling=None,
            )
        ]


class WmiThermalZoneProvider(ThermalSensorProvider):
    """Consulta segura de zonas térmicas ACPI vía root\\wmi MSAcpi_ThermalZoneTemperature."""

    def __init__(self, runner: SafePowerShellRunner | None = None) -> None:
        self.runner = runner or SafePowerShellRunner()

    def is_available(self) -> bool:
        return True

    def read_temperatures(self) -> Sequence[ThermalReading]:
        start = datetime.now(UTC)
        result = self.runner.run(PowerShellQuery.THERMAL_ZONE)
        elapsed = (datetime.now(UTC) - start).total_seconds()

        if result.timed_out:
            return [
                ThermalReading(
                    source_name="ACPI Thermal Zone",
                    target_hardware="CPU",
                    temperature_celsius=None,
                    unit="°C",
                    collected_at=_now(),
                    duration_seconds=elapsed,
                    confidence=ConfidenceLevel.LOW,
                    status=HealthStatus.ERROR,
                    is_supported=True,
                    detail="Tiempo agotado al consultar WMI MSAcpi_ThermalZoneTemperature",
                )
            ]

        if result.exit_code != 0:
            err_lower = (result.error or "").lower()
            if any(t in err_lower for t in ("denied", "access", "acceso", "0x80041003", "privilegio")):
                return [
                    ThermalReading(
                        source_name="ACPI Thermal Zone",
                        target_hardware="CPU",
                        temperature_celsius=None,
                        unit="°C",
                        collected_at=_now(),
                        duration_seconds=elapsed,
                        confidence=ConfidenceLevel.LOW,
                        status=HealthStatus.ERROR,
                        is_supported=True,
                        detail="Permiso denegado al consultar WMI (requiere elevación)",
                    )
                ]
            return [
                ThermalReading(
                    source_name="ACPI Thermal Zone",
                    target_hardware="CPU",
                    temperature_celsius=None,
                    unit="°C",
                    collected_at=_now(),
                    duration_seconds=elapsed,
                    confidence=ConfidenceLevel.LOW,
                    status=HealthStatus.ERROR,
                    is_supported=True,
                    detail=f"Fallo en consulta WMI: {result.error or 'Error desconocido'}",
                )
            ]

        rows = parse_json_rows(result)
        if not rows:
            return [
                ThermalReading(
                    source_name="ACPI Thermal Zone",
                    target_hardware="CPU",
                    temperature_celsius=None,
                    unit="°C",
                    collected_at=_now(),
                    duration_seconds=elapsed,
                    confidence=ConfidenceLevel.LOW,
                    status=HealthStatus.NOT_SUPPORTED,
                    is_supported=False,
                    detail="No hay zonas térmicas ACPI expuestas por la placa base o el BIOS",
                )
            ]

        readings: list[ThermalReading] = []
        for row in rows:
            name = str(row.get("InstanceName") or "ThermalZone")
            raw_temp = row.get("CurrentTemperature")
            celsius = kelvin_decikelvin_to_celsius(raw_temp)

            if celsius is None:
                readings.append(
                    ThermalReading(
                        source_name=name,
                        target_hardware="CPU",
                        temperature_celsius=None,
                        unit="°C",
                        collected_at=_now(),
                        duration_seconds=elapsed,
                        confidence=ConfidenceLevel.LOW,
                        status=HealthStatus.NOT_SUPPORTED,
                        is_supported=False,
                        detail=f"Valor de temperatura no interpretable: {raw_temp!r}",
                    )
                )
                continue

            # Determinar estado según umbrales ACPI estándar documentados
            status = HealthStatus.NORMAL
            if celsius >= 95.0:
                status = HealthStatus.CRITICAL
            elif celsius >= 80.0:
                status = HealthStatus.WARNING

            meas = (Measurement(f"Temperatura ({name})", celsius, "°C", (0.0, 90.0)),)
            readings.append(
                ThermalReading(
                    source_name=name,
                    target_hardware="CPU",
                    temperature_celsius=celsius,
                    unit="°C",
                    collected_at=_now(),
                    duration_seconds=elapsed,
                    confidence=ConfidenceLevel.HIGH,
                    status=status,
                    is_supported=True,
                    detail=f"Temperatura leída de zona térmica ACPI: {celsius} °C",
                    measurements=meas,
                )
            )

        return readings


class StorageThermalProvider(ThermalSensorProvider):
    """Reutiliza contadores SMART / Reliability ya obtenidos en F2."""

    def __init__(self, raw_reliability_rows: Sequence[dict[str, Any]] | None = None) -> None:
        self.rows = tuple(raw_reliability_rows or ())

    def is_available(self) -> bool:
        return bool(self.rows)

    def read_temperatures(self) -> Sequence[ThermalReading]:
        readings: list[ThermalReading] = []
        if not self.rows:
            return [
                ThermalReading(
                    source_name="Almacenamiento SMART",
                    target_hardware="STORAGE",
                    temperature_celsius=None,
                    unit="°C",
                    collected_at=_now(),
                    duration_seconds=0.0,
                    confidence=ConfidenceLevel.LOW,
                    status=HealthStatus.NOT_SUPPORTED,
                    is_supported=False,
                    detail="No hay métricas de fiabilidad SMART reportadas para las unidades",
                )
            ]

        for item in self.rows:
            name = str(item.get("FriendlyName") or item.get("DeviceId") or "Disco")
            temp = item.get("Temperature")
            if temp is None:
                continue

            try:
                temp_val = float(temp)
                if math.isnan(temp_val) or math.isinf(temp_val) or not (-20.0 <= temp_val <= 120.0):
                    readings.append(
                        ThermalReading(
                            source_name=f"Almacenamiento: {name}",
                            target_hardware="STORAGE",
                            temperature_celsius=None,
                            unit="°C",
                            collected_at=_now(),
                            duration_seconds=0.0,
                            confidence=ConfidenceLevel.LOW,
                            status=HealthStatus.NOT_SUPPORTED,
                            is_supported=False,
                            detail=f"Temperatura de disco fuera de rango creíble: {temp!r}",
                        )
                    )
                    continue

                status = HealthStatus.NORMAL
                if temp_val >= 70.0:
                    status = HealthStatus.CRITICAL
                elif temp_val >= 55.0:
                    status = HealthStatus.WARNING

                meas = (Measurement(f"Temperatura ({name})", int(temp_val), "°C", (0.0, 70.0)),)
                readings.append(
                    ThermalReading(
                        source_name=f"Almacenamiento: {name}",
                        target_hardware="STORAGE",
                        temperature_celsius=temp_val,
                        unit="°C",
                        collected_at=_now(),
                        duration_seconds=0.0,
                        confidence=ConfidenceLevel.HIGH,
                        status=status,
                        is_supported=True,
                        detail=f"Sensor SMART de unidad de almacenamiento: {temp_val:.0f} °C",
                        measurements=meas,
                    )
                )
            except (ValueError, TypeError):
                continue

        if not readings:
            return [
                ThermalReading(
                    source_name="Almacenamiento SMART",
                    target_hardware="STORAGE",
                    temperature_celsius=None,
                    unit="°C",
                    collected_at=_now(),
                    duration_seconds=0.0,
                    confidence=ConfidenceLevel.LOW,
                    status=HealthStatus.NOT_SUPPORTED,
                    is_supported=False,
                    detail="Las unidades de almacenamiento no reportaron sensor de temperatura",
                )
            ]

        return readings


class NvidiaGpuThermalProvider(ThermalSensorProvider):
    """Consulta oficial a nvidia-smi exclusivamente desde rutas confiables del sistema."""

    def __init__(
        self,
        runner: SafeCommandRunner | None = None,
        custom_binary_path: str | None = None,
    ) -> None:
        self.runner = runner or SafeCommandRunner()
        if custom_binary_path is not None:
            self.binary_path = custom_binary_path if custom_binary_path else None
        else:
            self.binary_path = find_trusted_nvidia_smi()

    def is_available(self) -> bool:
        return self.binary_path is not None

    def read_temperatures(self) -> Sequence[ThermalReading]:
        if not self.binary_path:
            return [
                ThermalReading(
                    source_name="NVIDIA GPU",
                    target_hardware="GPU",
                    temperature_celsius=None,
                    unit="°C",
                    collected_at=_now(),
                    duration_seconds=0.0,
                    confidence=ConfidenceLevel.LOW,
                    status=HealthStatus.NOT_SUPPORTED,
                    is_supported=False,
                    detail="Herramienta nvidia-smi no encontrada en rutas confiables del sistema",
                )
            ]

        start = datetime.now(UTC)
        result = self.runner.nvidia_smi_query(self.binary_path, timeout=5.0)
        elapsed = (datetime.now(UTC) - start).total_seconds()

        if result.timed_out:
            return [
                ThermalReading(
                    source_name="NVIDIA GPU",
                    target_hardware="GPU",
                    temperature_celsius=None,
                    unit="°C",
                    collected_at=_now(),
                    duration_seconds=elapsed,
                    confidence=ConfidenceLevel.LOW,
                    status=HealthStatus.ERROR,
                    is_supported=True,
                    detail="Tiempo agotado al consultar telemetría con nvidia-smi",
                )
            ]

        if result.exit_code != 0 or not result.output.strip():
            return [
                ThermalReading(
                    source_name="NVIDIA GPU",
                    target_hardware="GPU",
                    temperature_celsius=None,
                    unit="°C",
                    collected_at=_now(),
                    duration_seconds=elapsed,
                    confidence=ConfidenceLevel.LOW,
                    status=HealthStatus.ERROR,
                    is_supported=True,
                    detail=f"nvidia-smi devolvió error ({result.exit_code}): {result.error or 'Sin salida'}",
                )
            ]

        readings: list[ThermalReading] = []
        try:
            reader = csv.reader(io.StringIO(result.output.strip()))
            for row in reader:
                clean_cols = [col.strip() for col in row]
                # Esperamos 9 columnas:
                # index, name, temp, util, fan, power, clock, hw_throttle, sw_throttle
                if len(clean_cols) < 9:
                    continue

                idx, name, raw_temp, _raw_util, raw_fan, raw_power, raw_clock, hw_th, sw_th = (
                    clean_cols[:9]
                )

                # Parseo de temperatura
                temp_celsius: float | None = None
                if raw_temp not in ("[N/A]", "N/A", "", "null", "None"):
                    try:
                        parsed = float(raw_temp)
                        if 0.0 < parsed <= 120.0:
                            temp_celsius = parsed
                    except (ValueError, TypeError):
                        pass

                # Parseo de ventilador
                fan_rpm: int | None = None
                if raw_fan not in ("[N/A]", "N/A", "", "null", "None"):
                    try:
                        fan_rpm = int(float(raw_fan))
                    except (ValueError, TypeError):
                        pass

                # Parseo de potencia
                power_w: float | None = None
                if raw_power not in ("[N/A]", "N/A", "", "null", "None"):
                    try:
                        power_w = float(raw_power)
                    except (ValueError, TypeError):
                        pass

                # Parseo de reloj
                clock_mhz: float | None = None
                if raw_clock not in ("[N/A]", "N/A", "", "null", "None"):
                    try:
                        clock_mhz = float(raw_clock)
                    except (ValueError, TypeError):
                        pass

                # Parseo de throttling térmico documentado explícito
                # En nvidia-smi devuelve "Active" o "Not Active"
                is_throttling = None
                if hw_th in ("Active", "1") or sw_th in ("Active", "1"):
                    is_throttling = True
                elif hw_th == "Not Active" and sw_th == "Not Active":
                    is_throttling = False

                meas_list: list[Measurement] = []
                if temp_celsius is not None:
                    meas_list.append(
                        Measurement(f"Temperatura GPU ({name})", temp_celsius, "°C", (0.0, 85.0))
                    )
                if fan_rpm is not None:
                    meas_list.append(
                        Measurement(f"Ventilador GPU ({name})", fan_rpm, "%", (0.0, 100.0))
                    )
                if power_w is not None:
                    meas_list.append(
                        Measurement(f"Potencia GPU ({name})", round(power_w, 1), "W")
                    )
                if clock_mhz is not None:
                    meas_list.append(
                        Measurement(f"Frecuencia GPU ({name})", round(clock_mhz, 0), "MHz")
                    )

                if temp_celsius is None:
                    readings.append(
                        ThermalReading(
                            source_name=f"GPU {idx}: {name}",
                            target_hardware="GPU",
                            temperature_celsius=None,
                            unit="°C",
                            collected_at=_now(),
                            duration_seconds=elapsed,
                            confidence=ConfidenceLevel.LOW,
                            status=HealthStatus.NOT_SUPPORTED,
                            is_supported=False,
                            detail="nvidia-smi no reportó temperatura válida para este dispositivo",
                            is_throttling=is_throttling,
                            fan_rpm=fan_rpm,
                            power_watts=power_w,
                            clock_mhz=clock_mhz,
                            measurements=tuple(meas_list),
                        )
                    )
                    continue

                # Severidad conservadora documentada
                status = HealthStatus.NORMAL
                if temp_celsius >= 90.0 or is_throttling is True:
                    status = HealthStatus.CRITICAL
                elif temp_celsius >= 80.0:
                    status = HealthStatus.WARNING

                throttle_text = " (Thermal Throttling ACTIVO)" if is_throttling else ""
                readings.append(
                    ThermalReading(
                        source_name=f"GPU {idx}: {name}",
                        target_hardware="GPU",
                        temperature_celsius=temp_celsius,
                        unit="°C",
                        collected_at=_now(),
                        duration_seconds=elapsed,
                        confidence=ConfidenceLevel.HIGH,
                        status=status,
                        is_supported=True,
                        detail=f"Telemetría GPU NVIDIA oficial: {temp_celsius:.0f} °C{throttle_text}",
                        is_throttling=is_throttling,
                        fan_rpm=fan_rpm,
                        power_watts=power_w,
                        clock_mhz=clock_mhz,
                        measurements=tuple(meas_list),
                    )
                )
        except (csv.Error, ValueError, TypeError, KeyError) as exc:
            return [
                ThermalReading(
                    source_name="NVIDIA GPU",
                    target_hardware="GPU",
                    temperature_celsius=None,
                    unit="°C",
                    collected_at=_now(),
                    duration_seconds=elapsed,
                    confidence=ConfidenceLevel.LOW,
                    status=HealthStatus.ERROR,
                    is_supported=True,
                    detail=f"Error al procesar salida de nvidia-smi: {exc}",
                )
            ]

        if not readings:
            return [
                ThermalReading(
                    source_name="NVIDIA GPU",
                    target_hardware="GPU",
                    temperature_celsius=None,
                    unit="°C",
                    collected_at=_now(),
                    duration_seconds=elapsed,
                    confidence=ConfidenceLevel.LOW,
                    status=HealthStatus.NOT_SUPPORTED,
                    is_supported=False,
                    detail="No se encontraron dispositivos GPU en la respuesta de nvidia-smi",
                )
            ]

        return readings


class CompositeThermalProvider(ThermalSensorProvider):
    """Orquesta múltiples proveedores ordenados sin duplicar ni bloquear."""

    def __init__(self, providers: Sequence[ThermalSensorProvider]) -> None:
        self.providers = tuple(providers)

    def is_available(self) -> bool:
        return any(p.is_available() for p in self.providers)

    def read_temperatures(self) -> Sequence[ThermalReading]:
        all_readings: list[ThermalReading] = []
        for provider in self.providers:
            try:
                readings = provider.read_temperatures()
                all_readings.extend(readings)
            except (OSError, ValueError, RuntimeError, TypeError, KeyError) as exc:
                all_readings.append(
                    ThermalReading(
                        source_name=provider.__class__.__name__,
                        target_hardware="UNKNOWN",
                        temperature_celsius=None,
                        unit="°C",
                        collected_at=_now(),
                        duration_seconds=0.0,
                        confidence=ConfidenceLevel.LOW,
                        status=HealthStatus.ERROR,
                        is_supported=True,
                        detail=f"Error no controlado en proveedor térmico: {exc}",
                    )
                )
        return all_readings
