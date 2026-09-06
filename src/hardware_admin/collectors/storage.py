"""Recolector especializado de almacenamiento físico y volúmenes lógicos."""

from __future__ import annotations

from typing import Any

import psutil

from hardware_admin.diagnostics.rules import DISK_RULE
from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    ConfidenceLevel,
    EvidenceRecord,
    HealthStatus,
    Measurement,
)
from hardware_admin.infrastructure.powershell import (
    PowerShellQuery,
    SafePowerShellRunner,
    parse_json_rows,
)


def format_bytes(value: float | None) -> str:
    if value is None:
        return "No disponible"
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(amount) < 1024 or unit == "PB":
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} PB"


class StorageCollector:
    """Recolecta información de volúmenes montados, discos físicos (SSD/HDD) y salud."""

    component = ComponentKind.DISK

    def __init__(
        self,
        runner: SafePowerShellRunner,
        thermal_provider: Any | None = None,
    ) -> None:
        self.runner = runner
        self.thermal_provider = thermal_provider

    def collect(self) -> ComponentResult:
        volumes: list[dict[str, Any]] = []
        seen: set[str] = set()
        for partition in psutil.disk_partitions(all=False):
            if partition.mountpoint in seen:
                continue
            seen.add(partition.mountpoint)
            try:
                usage = psutil.disk_usage(partition.mountpoint)
            except (OSError, PermissionError):
                continue
            volumes.append(
                {
                    "Unidad": partition.mountpoint,
                    "Sistema": partition.fstype or "No disponible",
                    "Capacidad": format_bytes(usage.total),
                    "Disponible": format_bytes(usage.free),
                    "Uso": f"{usage.percent:.1f}%",
                    "UsoNum": usage.percent,
                    "UsadoBytes": float(usage.used),
                    "LibreBytes": float(usage.free),
                }
            )

        # Consultas de almacenamiento en Windows
        disks_result = self.runner.run(PowerShellQuery.DISKS)
        phys_result = self.runner.run(PowerShellQuery.PHYSICAL_DISKS)
        vol_result = self.runner.run(PowerShellQuery.VOLUMES)
        usb_result = self.runner.run(PowerShellQuery.USB_STORAGE)
        rel_result = self.runner.run(PowerShellQuery.STORAGE_RELIABILITY)

        disks = parse_json_rows(disks_result)
        physical_disks = parse_json_rows(phys_result)
        powershell_volumes = parse_json_rows(vol_result)
        usb_storage_rows = parse_json_rows(usb_result)
        rel_rows = parse_json_rows(rel_result)

        # Análisis de soporte y permisos de contadores avanzados (SMART / Reliability)
        rel_by_id = {str(r.get("DeviceId")): r for r in rel_rows if r.get("DeviceId") is not None}
        rel_by_name = {str(r.get("FriendlyName")): r for r in rel_rows if r.get("FriendlyName")}
        has_deep_metrics = False

        reliability_notes: str | None = None
        if rel_result.timed_out:
            reliability_notes = "Tiempo agotado al consultar contadores SMART"
        elif rel_result.exit_code != 0 and not rel_rows:
            err_lower = (rel_result.error or "").lower()
            if any(term in err_lower for term in ("access", "permission", "acceso", "privilegio", "denied")):
                reliability_notes = "No disponible por permisos (requiere elevación de administrador)"
            else:
                reliability_notes = f"Error de consulta SMART: {rel_result.error or 'Fallo desconocido'}"
        elif not rel_rows:
            reliability_notes = "No soportado por el controlador o bus de almacenamiento"

        # Normalización de discos físicos y detección de medios (SSD vs HDD)
        norm_physical: list[dict[str, Any]] = []
        measurements: list[Measurement] = []
        ssd_count = 0
        hdd_count = 0
        unhealthy_disks: list[str] = []
        unconfirmed_disks: list[str] = []
        confirmed_healthy_disks = 0

        target_disks = physical_disks if physical_disks else disks
        for item in target_disks:
            media = str(item.get("MediaType") or item.get("TipoMedio") or "No especificado")
            bus = str(item.get("BusType") or item.get("Tipo de bus") or "No disponible")
            name = str(item.get("FriendlyName") or item.get("Dispositivo") or item.get("Nombre") or "Disco")
            
            raw_health = item.get("HealthStatus") or item.get("Salud")
            if raw_health is None or str(raw_health).strip() in ("", "None", "null"):
                health = "No disponible"
            else:
                health = str(raw_health).strip()

            raw_size = item.get("Size") or item.get("Capacidad") or item.get("Tamano")

            if "SSD" in media.upper():
                ssd_count += 1
            elif "HDD" in media.upper():
                hdd_count += 1

            # Clasificación explícita de salud reportada por Windows/controlador
            if health.upper() in {"WARNING", "UNHEALTHY", "DEGRADED", "CRITICAL"}:
                unhealthy_disks.append(f"{name} ({health})")
            elif health.upper() in {"HEALTHY", "OK", "0"}:
                confirmed_healthy_disks += 1
            else:
                unconfirmed_disks.append(name)

            disk_entry: dict[str, Any] = {
                "Dispositivo": name,
                "Tipo de medio": media,
                "Bus": bus,
                "Salud": health,
                "Capacidad": format_bytes(float(raw_size)) if raw_size is not None else "No disponible",
            }

            # Extracción segura de contadores de confiabilidad (SMART / Wear / Temp)
            rel_info = rel_by_id.get(str(item.get("DeviceId"))) or rel_by_name.get(name)
            rel_err = str(rel_info.get("ReliabilityError") or "").strip() if rel_info else ""
            
            if rel_info:
                temp = rel_info.get("Temperature")
                wear = rel_info.get("Wear")
                poh = rel_info.get("PowerOnHours")
                read_err = rel_info.get("ReadErrorsTotal")
                write_err = rel_info.get("WriteErrorsTotal")

                if temp is not None:
                    has_deep_metrics = True
                    disk_entry["Temperatura"] = f"{temp} °C"
                    measurements.append(
                        Measurement(f"Temperatura ({name})", int(temp), "°C", (0.0, 70.0))
                    )
                if wear is not None:
                    has_deep_metrics = True
                    disk_entry["Desgaste"] = f"{wear}%"
                    measurements.append(
                        Measurement(f"Desgaste ({name})", int(wear), "%", (0.0, 80.0))
                    )
                if poh is not None:
                    has_deep_metrics = True
                    disk_entry["Horas de encendido"] = f"{poh} h"
                    measurements.append(
                        Measurement(f"Horas encendido ({name})", int(poh), "h")
                    )
                if read_err is not None:
                    has_deep_metrics = True
                    disk_entry["Errores lectura"] = int(read_err)
                if write_err is not None:
                    has_deep_metrics = True
                    disk_entry["Errores escritura"] = int(write_err)

                if rel_err:
                    err_l = rel_err.lower()
                    if any(t in err_l for t in ("access", "permission", "acceso", "privilegio", "denied")):
                        disk_entry["Fiabilidad SMART"] = "No disponible por permisos (requiere elevación)"
                    elif any(t in err_l for t in ("not supported", "no admitido", "no soportado")):
                        disk_entry["Fiabilidad SMART"] = "No soportado por el controlador/unidad"
                    else:
                        disk_entry["Fiabilidad SMART"] = f"Error: {rel_err}"
                elif temp is not None or wear is not None or poh is not None:
                    disk_entry["Fiabilidad SMART"] = "Disponible"
                else:
                    disk_entry["Fiabilidad SMART"] = "No soportado por el controlador/unidad"
            else:
                disk_entry["Fiabilidad SMART"] = reliability_notes or "No soportado por el controlador/unidad"

            norm_physical.append(disk_entry)

        # Caso «USB OK sin volumen»: la asociacion disco-particion la resuelve Windows
        # (Get-Disk -> Get-Partition), nunca la coincidencia de nombres. Un medio sano
        # que no expone letra de unidad es un problema de deteccion o configuracion del
        # periferico, no una prueba de dano fisico ni un motivo para condenar el bus.
        # Exigir que la fila declare el campo: si Windows no lo informa el dato esta
        # ausente, y un dato ausente no es un hallazgo.
        usb_without_volume = [
            row
            for row in usb_storage_rows
            if "Volumenes" in row
            and not str(row.get("Volumenes") or "").strip()
            and str(row.get("Salud") or "Healthy").upper() in {"HEALTHY", "OK"}
        ]

        max_usage = max((float(item["UsoNum"]) for item in volumes), default=0.0)
        status = DISK_RULE.classify(max_usage)

        problem: str | None = None
        if unhealthy_disks:
            status = HealthStatus.CRITICAL
            problem = f"Alerta de salud física en disco(s): {', '.join(unhealthy_disks)}"
        elif status is HealthStatus.CRITICAL:
            problem = f"Espacio crítico insuficiente en disco (máximo {max_usage:.1f}% ocupado)"
        elif status is HealthStatus.WARNING:
            problem = f"Poco espacio disponible en disco (máximo {max_usage:.1f}% ocupado)"

        usb_case: str | None = None
        if usb_without_volume and status is HealthStatus.NORMAL:
            nombres = ", ".join(
                str(row.get("Dispositivo") or f"Disco USB {row.get('Numero')}")
                for row in usb_without_volume
            )
            status = HealthStatus.WARNING
            usb_case = "USB-SIN-VOLUMEN"
            problem = (
                f"Medio USB presente y sano sin volumen accesible ({nombres}). "
                "Revisar la deteccion o la configuracion del periferico: asignar letra, "
                "comprobar el formato o probar en otro puerto. El bus USB no queda condenado."
            )

        # Añadir mediciones cuantitativas de uso por cada volumen
        for v in volumes:
            measurements.append(
                Measurement(
                    name=f"Uso {v['Unidad']}",
                    value=round(float(v["UsoNum"]), 1),
                    unit="%",
                    expected_range=(0.0, 90.0),
                )
            )

        internal = {"UsoNum", "UsadoBytes", "LibreBytes"}
        clean_volumes = [
            {k: v for k, v in item.items() if k not in internal} for item in volumes
        ]
        facts: dict[str, Any] = {
            "Unidades": clean_volumes,
            "Discos físicos": norm_physical if norm_physical else disks,
            "Resumen tecnológico": f"{ssd_count} SSD, {hdd_count} HDD" if (ssd_count or hdd_count) else "Discos detectados",
        }
        if reliability_notes:
            facts["Fiabilidad física (SMART)"] = reliability_notes
        if powershell_volumes:
            facts["Volúmenes detectados"] = len(powershell_volumes)
        if usb_storage_rows:
            facts["Almacenamiento USB"] = [
                {
                    "Dispositivo": row.get("Dispositivo") or f"Disco USB {row.get('Numero')}",
                    "Salud": row.get("Salud") or "No disponible",
                    "Estilo de partición": row.get("EstiloParticion") or "No disponible",
                    "Volúmenes": str(row.get("Volumenes") or "").strip() or "Sin volumen",
                }
                for row in usb_storage_rows
            ]
        if usb_case:
            facts["Caso"] = usb_case

        # Telemetría térmica de almacenamiento (Fase F3)
        if self.thermal_provider is not None:
            try:
                thermal_readings = self.thermal_provider.read_temperatures()
                storage_readings = [r for r in thermal_readings if r.target_hardware == "STORAGE"]
                if storage_readings:
                    facts["Telemetría térmica de almacenamiento"] = [
                        {
                            "Unidad": r.source_name,
                            "Temperatura": f"{r.temperature_celsius} °C" if r.temperature_celsius is not None else "No disponible",
                            "Estado": r.status.value,
                            "Fuente": r.source_name,
                            "Confianza": r.confidence.value,
                            "Detalle": r.detail,
                            "Soportado": "Sí" if r.is_supported else "No",
                        }
                        for r in storage_readings
                    ]
                    for r in storage_readings:
                        measurements.extend(r.measurements)
            except (OSError, ValueError, RuntimeError, TypeError, KeyError) as exc:
                facts["Telemetría térmica de almacenamiento"] = f"Error al consultar telemetría: {exc}"

        # Serie para el grafico de barras apiladas por unidad.
        facts["_volumenes"] = [
            {
                "unidad": str(item["Unidad"]),
                "usado": float(item["UsadoBytes"]),
                "libre": float(item["LibreBytes"]),
                "porcentaje": float(item["UsoNum"]),
            }
            for item in volumes
        ]

        volume_text = "\n".join(
            f"{v['Unidad']} | {v['Sistema']} | {v['Capacidad']} | Uso {v['Uso']}"
            for v in clean_volumes
        )
        output = (
            f"psutil.disk_partitions() / disk_usage()\n{volume_text}\n\n"
            f"Get-PhysicalDisk:\n{phys_result.output}\n\n"
            f"Get-Disk:\n{disks_result.output}\n\n"
            f"Get-StorageReliabilityCounter:\n{rel_result.output or rel_result.error}"
        )

        from datetime import UTC, datetime
        evidence_records = [
            EvidenceRecord(
                "psutil + PowerShell (Get-PhysicalDisk / Get-Volume / Get-StorageReliabilityCounter)",
                "Almacenamiento y salud de discos",
                output[:40_000],
                datetime.now(UTC),
                disks_result.exit_code == 0,
            )
        ]

        if has_deep_metrics and confirmed_healthy_disks > 0:
            confidence = ConfidenceLevel.HIGH
        elif confirmed_healthy_disks > 0 or norm_physical:
            confidence = ConfidenceLevel.MEDIUM if confirmed_healthy_disks > 0 else ConfidenceLevel.LOW
        else:
            confidence = ConfidenceLevel.LOW

        if unconfirmed_disks and confirmed_healthy_disks == 0:
            facts["Salud física de discos"] = "No expuesta por el controlador"

        summary = f"Máximo {max_usage:.0f}% ocupado"
        if ssd_count > 0:
            summary += f" · {ssd_count} SSD"
        if hdd_count > 0:
            summary += f" · {hdd_count} HDD"

        return ComponentResult(
            self.component,
            "Almacenamiento",
            facts,
            summary=summary,
            status=status,
            possible_problem=problem,
            evidence=tuple(evidence_records),
            confidence=confidence,
            measurements=tuple(measurements),
            is_supported=True,
        )

