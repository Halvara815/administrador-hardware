"""Recolector especializado para adaptadores gráficos (GPU) y monitores."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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


class GpuCollector:
    """Recolector de GPU y monitores con límites WMI explícitos y manejo de estados."""

    component = ComponentKind.MONITOR_GPU

    def __init__(self, runner: SafePowerShellRunner) -> None:
        self.runner = runner

    def collect(self) -> ComponentResult:
        result = self.runner.run(PowerShellQuery.VIDEO_CONTROLLERS)
        if result.exit_code != 0:
            error_msg = result.error or "La consulta no devolvió información"
            return ComponentResult(
                component=self.component,
                name="Monitor y GPU",
                facts={"Resultado": "No disponible", "Detalle": error_msg},
                summary="No disponible",
                status=HealthStatus.ERROR,
                possible_problem="No fue posible consultar el subsistema gráfico de Windows",
                evidence=(
                    EvidenceRecord(
                        "PowerShell",
                        "Win32_VideoController / Win32_DesktopMonitor",
                        error_msg,
                        datetime.now(UTC),
                        False,
                    ),
                ),
            )

        rows = parse_json_rows(result)
        gpu_rows = [row for row in rows if row.get("Tipo") == "GPU"]
        monitor_rows = [row for row in rows if row.get("Tipo") == "Monitor"]

        normalized_gpus: list[dict[str, Any]] = []
        has_critical = False
        has_unknown = False
        problems_desc: list[str] = []

        for gpu in gpu_rows:
            name = str(gpu.get("Nombre") or "GPU no identificada")
            raw_status = str(gpu.get("Estado") or "Unknown").strip()
            processor = str(gpu.get("Procesador") or name)
            driver = str(gpu.get("Driver") or "No disponible")
            resolution = str(gpu.get("Resolucion") or "No disponible")
            pnp_id = str(gpu.get("PNPDeviceID") or "No disponible")
            ram = gpu.get("Memoria")

            status_upper = raw_status.upper()
            if status_upper == "UNKNOWN":
                has_unknown = True
                problems_desc.append(
                    f"{name}: estado «Unknown» reportado por Windows. Requiere investigación de controlador; no prueba daño físico."
                )
            elif status_upper not in {"OK", "0"}:
                has_critical = True
                problems_desc.append(f"{name}: estado de fallo reportado ({raw_status}).")

            normalized_gpus.append(
                {
                    "Nombre": name,
                    "Procesador": processor,
                    "Estado original": raw_status,
                    "Controlador": driver,
                    "Resolución activa": resolution,
                    "Memoria reportada (WMI)": format_bytes(float(ram)) if ram is not None else "No disponible",
                    "ID de hardware": pnp_id,
                }
            )

        # Monitores
        normalized_monitors: list[dict[str, Any]] = []
        for mon in monitor_rows:
            name = str(mon.get("Nombre") or "Monitor")
            m_status = str(mon.get("Estado") or "OK")
            normalized_monitors.append(
                {
                    "Nombre": name,
                    "Estado": m_status,
                    "ID de hardware": mon.get("PNPDeviceID") or "No disponible",
                }
            )

        if has_critical:
            status = HealthStatus.CRITICAL
            problem = "; ".join(problems_desc)
        elif has_unknown:
            status = HealthStatus.WARNING
            problem = "; ".join(problems_desc)
        else:
            status = HealthStatus.NORMAL
            problem = None

        facts: dict[str, Any] = {
            "Dispositivos gráficos": rows,
            "Adaptadores de vídeo (GPU)": normalized_gpus,
            "Pantallas / Monitores": normalized_monitors,
            "Límites técnicos VRAM": (
                "La memoria informada por WMI es referencial del subsistema de vídeo "
                "y no se garantiza como VRAM dedicada exacta."
            ),
        }

        summary = f"{len(gpu_rows)} GPU · {len(monitor_rows)} monitor(es)"
        if status is HealthStatus.NORMAL:
            summary += " · Estado OK"

        evidence = (
            EvidenceRecord(
                "PowerShell",
                "Win32_VideoController / Win32_DesktopMonitor",
                result.output or "[]",
                datetime.now(UTC),
                True,
            ),
        )

        return ComponentResult(
            self.component,
            "Monitor y GPU",
            facts,
            summary=summary,
            status=status,
            possible_problem=problem,
            evidence=evidence,
        )
