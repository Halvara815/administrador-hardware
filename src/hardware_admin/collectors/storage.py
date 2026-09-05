"""Recolector especializado de almacenamiento físico y volúmenes lógicos."""

from __future__ import annotations

from typing import Any

import psutil

from hardware_admin.diagnostics.rules import DISK_RULE
from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    EvidenceRecord,
    HealthStatus,
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

    def __init__(self, runner: SafePowerShellRunner) -> None:
        self.runner = runner

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
                }
            )

        # Consultas de almacenamiento en Windows
        disks_result = self.runner.run(PowerShellQuery.DISKS)
        phys_result = self.runner.run(PowerShellQuery.PHYSICAL_DISKS)
        vol_result = self.runner.run(PowerShellQuery.VOLUMES)

        disks = parse_json_rows(disks_result)
        physical_disks = parse_json_rows(phys_result)
        powershell_volumes = parse_json_rows(vol_result)

        # Normalización de discos físicos y detección de medios (SSD vs HDD)
        norm_physical: list[dict[str, Any]] = []
        ssd_count = 0
        hdd_count = 0
        unhealthy_disks: list[str] = []

        target_disks = physical_disks if physical_disks else disks
        for item in target_disks:
            media = str(item.get("MediaType") or item.get("TipoMedio") or "No especificado")
            bus = str(item.get("BusType") or item.get("Tipo de bus") or "No disponible")
            name = str(item.get("FriendlyName") or item.get("Dispositivo") or item.get("Nombre") or "Disco")
            health = str(item.get("HealthStatus") or item.get("Salud") or "Healthy")
            raw_size = item.get("Size") or item.get("Capacidad") or item.get("Tamano")

            if "SSD" in media.upper():
                ssd_count += 1
            elif "HDD" in media.upper():
                hdd_count += 1

            if health.upper() not in {"HEALTHY", "OK", "0"}:
                unhealthy_disks.append(f"{name} ({health})")

            norm_physical.append(
                {
                    "Dispositivo": name,
                    "Tipo de medio": media,
                    "Bus": bus,
                    "Salud": health,
                    "Capacidad": format_bytes(float(raw_size)) if raw_size is not None else "No disponible",
                }
            )

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

        clean_volumes = [{k: v for k, v in item.items() if k != "UsoNum"} for item in volumes]
        facts: dict[str, Any] = {
            "Unidades": clean_volumes,
            "Discos físicos": norm_physical if norm_physical else disks,
            "Resumen tecnológico": f"{ssd_count} SSD, {hdd_count} HDD" if (ssd_count or hdd_count) else "Discos detectados",
        }
        if powershell_volumes:
            facts["Volúmenes detectados"] = len(powershell_volumes)

        volume_text = "\n".join(
            f"{v['Unidad']} | {v['Sistema']} | {v['Capacidad']} | Uso {v['Uso']}"
            for v in clean_volumes
        )
        output = f"psutil.disk_partitions() / disk_usage()\n{volume_text}\n\nGet-PhysicalDisk:\n{phys_result.output}\n\nGet-Disk:\n{disks_result.output}"

        from datetime import UTC, datetime
        evidence_records = [
            EvidenceRecord(
                "psutil + PowerShell (Get-PhysicalDisk / Get-Volume)",
                "Almacenamiento y salud de discos",
                output[:40_000],
                datetime.now(UTC),
                disks_result.exit_code == 0,
            )
        ]

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
        )

