"""Recolectores concretos de las once áreas diagnósticas."""

from __future__ import annotations

import platform
import socket
import time
from datetime import UTC, datetime
from typing import Any

import psutil

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


def _now() -> datetime:
    return datetime.now(UTC)


def _evidence(source: str, query: str, output: str, succeeded: bool = True) -> EvidenceRecord:
    return EvidenceRecord(source, query, output[:40_000], _now(), succeeded)


def _status_for_percent(percent: float, warning: float, critical: float) -> HealthStatus:
    if percent >= critical:
        return HealthStatus.CRITICAL
    if percent >= warning:
        return HealthStatus.WARNING
    return HealthStatus.NORMAL


def _ps_failure(name: str, component: ComponentKind, query: str, error: str) -> ComponentResult:
    message = error or "La consulta no devolvió información"
    return ComponentResult(
        component=component,
        name=name,
        facts={"Resultado": "No disponible", "Detalle": message},
        summary="No disponible",
        status=HealthStatus.ERROR,
        possible_problem="No fue posible consultar el sistema",
        evidence=(_evidence("PowerShell", query, message, False),),
    )


class SystemCollector:
    component = ComponentKind.SYSTEM

    def __init__(self, runner: SafePowerShellRunner) -> None:
        self.runner = runner

    def collect(self) -> ComponentResult:
        uname = platform.uname()
        boot_time = datetime.fromtimestamp(psutil.boot_time(), UTC)
        uptime = datetime.now(UTC) - boot_time
        facts: dict[str, Any] = {
            "Nombre del equipo": socket.gethostname(),
            "Sistema": f"{uname.system} {uname.release}",
            "Sistema operativo": f"{uname.system} {uname.release}",
            "Versión": uname.version,
            "Arquitectura": platform.machine(),
            "Tiempo encendido": str(uptime).split(".")[0],
        }
        result = self.runner.run(PowerShellQuery.SYSTEM_INFO)
        rows = parse_json_rows(result)
        if rows:
            row = rows[0]
            facts.update(
                {
                    "Fabricante": row.get("Fabricante") or "No disponible",
                    "Modelo": row.get("Modelo") or "No disponible",
                    "Sistema operativo": row.get("SistemaOperativo") or facts["Sistema"],
                }
            )
        output = "\n".join(f"{key}: {value}" for key, value in facts.items())
        evidence = [_evidence("Python/platform", "platform.uname()", output)]
        if result.output or result.error:
            evidence.append(
                _evidence(
                    "PowerShell",
                    "Get-CimInstance Win32_OperatingSystem / Win32_ComputerSystem",
                    result.output or result.error,
                    result.exit_code == 0,
                )
            )
        return ComponentResult(
            self.component,
            "Información del sistema",
            facts,
            summary=f"{facts['Sistema operativo']}",
            status=HealthStatus.NORMAL,
            evidence=tuple(evidence),
        )


class CpuCollector:
    component = ComponentKind.CPU

    def __init__(self, runner: SafePowerShellRunner) -> None:
        self.runner = runner

    def collect(self) -> ComponentResult:
        usage = psutil.cpu_percent(interval=1.0)
        frequency = psutil.cpu_freq()
        result = self.runner.run(PowerShellQuery.CPU_INFO)
        rows = parse_json_rows(result)
        model = platform.processor() or "Procesador no identificado"
        if rows and rows[0].get("Name"):
            model = str(rows[0]["Name"]).strip()
        facts = {
            "Modelo": model,
            "Núcleos físicos": psutil.cpu_count(logical=False) or "No disponible",
            "Procesadores lógicos": psutil.cpu_count(logical=True) or "No disponible",
            "Frecuencia actual": (
                f"{frequency.current / 1000:.2f} GHz" if frequency else "No disponible"
            ),
            "Uso": f"{usage:.1f}%",
        }
        status = _status_for_percent(usage, 85, 95)
        problem = "Carga elevada del procesador" if status is not HealthStatus.NORMAL else None
        output = f"psutil.cpu_percent(interval=1)\n{usage:.1f}\n\n" + (
            result.output or result.error
        )
        return ComponentResult(
            self.component,
            "CPU",
            facts,
            summary=f"{usage:.0f}% de uso",
            status=status,
            possible_problem=problem,
            evidence=(_evidence("psutil + PowerShell", "CPU", output, result.exit_code == 0),),
        )


class MemoryCollector:
    component = ComponentKind.MEMORY

    def collect(self) -> ComponentResult:
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        facts = {
            "Total": format_bytes(memory.total),
            "Disponible": format_bytes(memory.available),
            "En uso": format_bytes(memory.used),
            "Porcentaje de uso": f"{memory.percent:.1f}%",
            "Memoria virtual usada": format_bytes(swap.used),
        }
        status = _status_for_percent(memory.percent, 80, 95)
        problem = "Poca memoria disponible" if status is not HealthStatus.NORMAL else None
        output = (
            "psutil.virtual_memory()\n"
            f"total={memory.total}, available={memory.available}, "
            f"used={memory.used}, percent={memory.percent}"
        )
        return ComponentResult(
            self.component,
            "Memoria RAM",
            facts,
            summary=f"{memory.percent:.0f}% de uso",
            status=status,
            possible_problem=problem,
            evidence=(_evidence("psutil", "psutil.virtual_memory()", output),),
        )


class DiskCollector:
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
        result = self.runner.run(PowerShellQuery.DISKS)
        disks = parse_json_rows(result)
        max_usage = max((float(item["UsoNum"]) for item in volumes), default=0.0)
        status = _status_for_percent(max_usage, 85, 95)
        problem = "Poco espacio disponible" if status is not HealthStatus.NORMAL else None
        clean_volumes = [{k: v for k, v in item.items() if k != "UsoNum"} for item in volumes]
        facts = {"Unidades": clean_volumes, "Discos físicos": disks}
        volume_text = "\n".join(
            f"{v['Unidad']} | {v['Sistema']} | {v['Capacidad']} | Uso {v['Uso']}"
            for v in clean_volumes
        )
        output = f"psutil.disk_partitions() / disk_usage()\n{volume_text}\n\n{result.output}"
        return ComponentResult(
            self.component,
            "Almacenamiento",
            facts,
            summary=f"Máximo {max_usage:.0f}% ocupado",
            status=status,
            possible_problem=problem,
            evidence=(_evidence("psutil + PowerShell", "Discos y volúmenes", output),),
        )


class NetworkCollector:
    component = ComponentKind.NETWORK

    def collect(self) -> ComponentResult:
        addresses = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        adapters: list[dict[str, Any]] = []
        for name, values in addresses.items():
            ipv4 = [item.address for item in values if item.family == socket.AF_INET]
            mac = [
                item.address
                for item in values
                if getattr(psutil, "AF_LINK", object()) == item.family
            ]
            stat = stats.get(name)
            if not ipv4 and not mac:
                continue
            adapters.append(
                {
                    "Adaptador": name,
                    "MAC": mac[0] if mac else "No disponible",
                    "IPv4": ", ".join(ipv4) if ipv4 else "Sin IPv4",
                    "Estado": "Conectado" if stat and stat.isup else "Desconectado",
                    "Velocidad": f"{stat.speed} Mbps" if stat and stat.speed else "No disponible",
                }
            )
        connected = sum(1 for item in adapters if item["Estado"] == "Conectado")
        status = HealthStatus.NORMAL if connected else HealthStatus.WARNING
        problem = None if connected else "No se detectó un adaptador de red activo"
        output = "\n".join(
            f"{a['Adaptador']} | {a['MAC']} | {a['IPv4']} | {a['Estado']} | {a['Velocidad']}"
            for a in adapters
        )
        return ComponentResult(
            self.component,
            "Red",
            {"Adaptadores": adapters},
            summary=f"{connected} conectado(s)",
            status=status,
            possible_problem=problem,
            evidence=(_evidence("psutil", "psutil.net_if_addrs() / net_if_stats()", output),),
        )


class PnpCollector:
    def __init__(
        self,
        runner: SafePowerShellRunner,
        component: ComponentKind,
        name: str,
        query: PowerShellQuery,
    ) -> None:
        self.runner = runner
        self.component = component
        self.name = name
        self.query = query

    def collect(self) -> ComponentResult:
        result = self.runner.run(self.query)
        if result.exit_code != 0:
            return _ps_failure(self.name, self.component, self.query.value, result.error)
        rows = parse_json_rows(result)
        problems = [row for row in rows if str(row.get("Status", "OK")).upper() != "OK"]
        if self.component is ComponentKind.PROBLEM_DEVICE:
            problems = rows
        status = HealthStatus.CRITICAL if problems else HealthStatus.NORMAL
        problem = f"{len(problems)} dispositivo(s) con error" if problems else None
        summary = (
            f"{len(problems)} errores detectados"
            if self.component is ComponentKind.PROBLEM_DEVICE
            else f"{len(rows)} disp. · {len(problems)} errores"
        )
        normalized_rows = [
            {
                "Dispositivo": row.get("FriendlyName") or row.get("InstanceId") or "Sin nombre",
                "Clase": row.get("Class") or "No disponible",
                "Estado": row.get("Status") or "No disponible",
                "ID": row.get("InstanceId") or "No disponible",
                "Código": row.get("Problem") if row.get("Problem") is not None else "—",
            }
            for row in rows
        ]
        return ComponentResult(
            self.component,
            self.name,
            {
                "Dispositivos": normalized_rows,
                "Total": len(rows),
                "Con problemas": len(problems),
            },
            summary=summary,
            status=status,
            possible_problem=problem,
            evidence=(_evidence("PowerShell", self.query.value, result.output or "[]", True),),
        )


class DriverCollector:
    component = ComponentKind.DRIVER

    def __init__(self, runner: SafePowerShellRunner) -> None:
        self.runner = runner

    def collect(self) -> ComponentResult:
        result = self.runner.run(PowerShellQuery.DRIVERS)
        if result.exit_code != 0:
            return _ps_failure(
                "Controladores", self.component, "Win32_PnPSignedDriver", result.error
            )
        rows = parse_json_rows(result)
        unsigned = [row for row in rows if row.get("IsSigned") is False]
        status = HealthStatus.WARNING if unsigned else HealthStatus.NORMAL
        return ComponentResult(
            self.component,
            "Controladores",
            {"Controladores": rows, "Consultados": len(rows), "No firmados": len(unsigned)},
            summary=f"{len(rows)} controladores",
            status=status,
            possible_problem=(
                f"{len(unsigned)} controlador(es) no firmado(s)" if unsigned else None
            ),
            evidence=(_evidence("PowerShell", "Win32_PnPSignedDriver", result.output),),
        )


class MonitorGpuCollector:
    component = ComponentKind.MONITOR_GPU

    def __init__(self, runner: SafePowerShellRunner) -> None:
        self.runner = runner

    def collect(self) -> ComponentResult:
        result = self.runner.run(PowerShellQuery.VIDEO_CONTROLLERS)
        if result.exit_code != 0:
            return _ps_failure(
                "Monitor y GPU", self.component, "Win32_VideoController", result.error
            )
        rows = parse_json_rows(result)
        gpu_rows = [row for row in rows if row.get("Tipo") == "GPU"]
        monitor_rows = [row for row in rows if row.get("Tipo") == "Monitor"]
        problems = [row for row in rows if str(row.get("Estado", "OK")).upper() != "OK"]
        status = HealthStatus.CRITICAL if problems else HealthStatus.NORMAL
        return ComponentResult(
            self.component,
            "Monitor y GPU",
            {"Dispositivos gráficos": rows},
            summary=f"{len(gpu_rows)} GPU · {len(monitor_rows)} monitor(es)",
            status=status,
            possible_problem="Controlador o dispositivo gráfico" if problems else None,
            evidence=(
                _evidence("PowerShell", "Get-CimInstance Win32_VideoController", result.output),
            ),
        )


class IoCollector:
    component = ComponentKind.IO

    def collect(self) -> ComponentResult:
        disk_before = psutil.disk_io_counters()
        net_before = psutil.net_io_counters()
        started = time.monotonic()
        time.sleep(0.5)
        elapsed = max(time.monotonic() - started, 0.001)
        disk_after = psutil.disk_io_counters()
        net_after = psutil.net_io_counters()

        read_rate = (
            (disk_after.read_bytes - disk_before.read_bytes) / elapsed
            if disk_before and disk_after
            else 0.0
        )
        write_rate = (
            (disk_after.write_bytes - disk_before.write_bytes) / elapsed
            if disk_before and disk_after
            else 0.0
        )
        send_rate = (net_after.bytes_sent - net_before.bytes_sent) / elapsed
        receive_rate = (net_after.bytes_recv - net_before.bytes_recv) / elapsed
        facts = {
            "Lectura de disco": f"{format_bytes(read_rate)}/s",
            "Escritura de disco": f"{format_bytes(write_rate)}/s",
            "Envío de red": f"{format_bytes(send_rate)}/s",
            "Recepción de red": f"{format_bytes(receive_rate)}/s",
            "Intervalo": f"{elapsed:.2f} s",
        }
        output = "\n".join(f"{key}: {value}" for key, value in facts.items())
        return ComponentResult(
            self.component,
            "Monitorización de E/S",
            facts,
            summary=f"Lectura {facts['Lectura de disco']}",
            status=HealthStatus.NORMAL,
            evidence=(_evidence("psutil", "disk_io_counters() / net_io_counters()", output),),
        )


def build_default_collectors() -> tuple[object, ...]:
    runner = SafePowerShellRunner()
    return (
        SystemCollector(runner),
        CpuCollector(runner),
        MemoryCollector(),
        DiskCollector(runner),
        NetworkCollector(),
        PnpCollector(runner, ComponentKind.USB, "USB", PowerShellQuery.USB_PRESENT),
        PnpCollector(runner, ComponentKind.PCI, "PCI / PCIe", PowerShellQuery.PCI_PRESENT),
        DriverCollector(runner),
        PnpCollector(
            runner,
            ComponentKind.PROBLEM_DEVICE,
            "Dispositivos con problemas",
            PowerShellQuery.PROBLEM_DEVICES,
        ),
        MonitorGpuCollector(runner),
        IoCollector(),
    )
