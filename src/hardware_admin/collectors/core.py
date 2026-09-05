"""Recolectores concretos de las once áreas diagnósticas."""

from __future__ import annotations

import platform
import socket
import time
from datetime import UTC, datetime
from typing import Any

import psutil

from hardware_admin.collectors.base import HardwareCollector
from hardware_admin.collectors.drivers import DriverCollector
from hardware_admin.collectors.gpu import GpuCollector
from hardware_admin.collectors.pnp import PnpDeviceCollector
from hardware_admin.collectors.storage import StorageCollector
from hardware_admin.diagnostics.rules import CPU_RULE, MEMORY_RULE
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
from hardware_admin.services.connectivity_service import ConnectivityService


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
        # Cebar el contador por nucleo antes de la medicion global: la lectura
        # posterior cubre exactamente esa misma ventana de un segundo, sin
        # alargar el analisis y sin alterar el valor que clasifica la salud.
        psutil.cpu_percent(interval=None, percpu=True)
        usage = psutil.cpu_percent(interval=1.0)
        per_core = psutil.cpu_percent(interval=None, percpu=True)
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
            # Series para los graficos; los renderizadores omiten las claves con "_".
            "_uso": float(usage),
            "_nucleos": [float(value) for value in per_core],
        }
        status = CPU_RULE.classify(usage)
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
            "_uso": float(memory.percent),
            "_memoria": {
                "usada": float(memory.used),
                "disponible": float(memory.available),
                "total": float(memory.total),
            },
        }
        status = MEMORY_RULE.classify(memory.percent)
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


DiskCollector = StorageCollector


class NetworkCollector:
    component = ComponentKind.NETWORK

    def __init__(
        self,
        runner: SafePowerShellRunner | None = None,
        connectivity_service: ConnectivityService | None = None,
    ) -> None:
        self.runner = runner or SafePowerShellRunner()
        self.connectivity_service = connectivity_service or ConnectivityService()

    def collect(self) -> ComponentResult:
        addresses = psutil.net_if_addrs()
        stats = psutil.net_if_stats()

        ps_result = self.runner.run(PowerShellQuery.NETWORK_CONFIGURATION)
        ps_rows = parse_json_rows(ps_result)
        configs_by_mac = {
            str(r.get("MAC", "")).upper().replace("-", ":"): r
            for r in ps_rows
            if r.get("MAC")
        }

        adapters: list[dict[str, Any]] = []
        for name, values in addresses.items():
            ipv4_list = [item.address for item in values if item.family == socket.AF_INET]
            mac_list = [
                item.address
                for item in values
                if getattr(psutil, "AF_LINK", object()) == item.family
            ]
            stat = stats.get(name)
            if not ipv4_list and not mac_list:
                continue

            mac_str = mac_list[0] if mac_list else ""
            mac_key = mac_str.upper().replace("-", ":")
            conf = configs_by_mac.get(mac_key, {})

            ipv6_val = conf.get("IPv6") or "No disponible"
            gateway_val = conf.get("Gateway") or "No disponible"
            dns_val = conf.get("DNS") or "No disponible"

            adapters.append(
                {
                    "Adaptador": name,
                    "MAC": mac_str or "No disponible",
                    "IPv4": ", ".join(ipv4_list) if ipv4_list else "Sin IPv4",
                    "IPv6": ipv6_val,
                    "Puerta de enlace": gateway_val,
                    "Servidores DNS": dns_val,
                    "Estado": "Conectado" if stat and stat.isup else "Desconectado",
                    "Velocidad": f"{stat.speed} Mbps" if stat and stat.speed else "No disponible",
                }
            )

        connected = sum(1 for item in adapters if item["Estado"] == "Conectado")

        primary_ip: str | None = None
        primary_gw: str | None = None
        for a in adapters:
            if a["Estado"] == "Conectado" and a["IPv4"] != "Sin IPv4":
                primary_ip = a["IPv4"]
                primary_gw = a.get("Puerta de enlace")
                break
        if not primary_ip and connected > 0:
            for a in adapters:
                if a["Estado"] == "Conectado":
                    primary_ip = a["IPv4"] if a["IPv4"] != "Sin IPv4" else None
                    primary_gw = a.get("Puerta de enlace")
                    break

        conn_report = self.connectivity_service.check(
            adapter_connected=connected > 0,
            local_ip=primary_ip,
            gateway=primary_gw,
        )

        stages_fact = [
            {
                "Etapa": s.stage.value,
                "Destino": s.target,
                "Resultado": "OK" if s.succeeded else "Fallo",
                "Detalle": s.details,
            }
            for s in conn_report.stages
        ]

        facts: dict[str, Any] = {
            "Adaptadores": adapters,
            "_adaptadores": [
                {
                    "nombre": item["Adaptador"],
                    "mbps": float(stats[item["Adaptador"]].speed)
                    if stats.get(item["Adaptador"]) and stats[item["Adaptador"]].speed
                    else 0.0,
                    "conectado": item["Estado"] == "Conectado",
                }
                for item in adapters
            ],
            "Conectividad": stages_fact,
            "Diagnóstico de red": conn_report.problem_title
            or "Conectividad normal y acceso a Internet verificado",
        }
        if conn_report.recommendations:
            facts["Recomendaciones"] = list(conn_report.recommendations)

        if conn_report.problem_title and "APIPA" in conn_report.problem_title:
            summary = "APIPA (169.254.x.x) - Sin DHCP"
            facts["Caso"] = "C1"
        elif conn_report.problem_title and "DNS" in conn_report.problem_title:
            summary = "Fallo de resolución DNS"
            facts["Caso"] = "DNS"
        elif not connected:
            summary = "0 adaptadores conectados"
        elif conn_report.status == HealthStatus.NORMAL:
            summary = f"{connected} conectado(s) · Conectividad OK"
        else:
            summary = f"{connected} conectado(s) · {conn_report.problem_title or 'Advertencia'}"

        evidence_items = [
            _evidence(
                "psutil",
                "psutil.net_if_addrs() / net_if_stats()",
                "\n".join(
                    f"{a['Adaptador']} | {a['MAC']} | IPv4: {a['IPv4']} | GW: {a['Puerta de enlace']} | Estado: {a['Estado']}"
                    for a in adapters
                ),
            ),
        ]
        if ps_result.output or ps_result.error:
            evidence_items.append(
                _evidence(
                    "PowerShell",
                    "Get-CimInstance Win32_NetworkAdapterConfiguration",
                    ps_result.output or ps_result.error,
                    ps_result.exit_code == 0,
                )
            )

        connectivity_evidence_text = "\n".join(
            f"[{'OK' if s.succeeded else 'FALLO'}] {s.stage.value.upper()} -> {s.target}: {s.details}"
            for s in conn_report.stages
        )
        evidence_items.append(
            _evidence(
                "ConnectivityService (ping / nslookup)",
                "Pruebas escalonadas de conectividad",
                connectivity_evidence_text,
                conn_report.status == HealthStatus.NORMAL,
            )
        )

        return ComponentResult(
            self.component,
            "Red",
            facts,
            summary=summary,
            status=conn_report.status,
            possible_problem=conn_report.problem_title,
            evidence=tuple(evidence_items),
        )


PnpCollector = PnpDeviceCollector
MonitorGpuCollector = GpuCollector


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


def build_default_collectors() -> tuple[HardwareCollector, ...]:
    runner = SafePowerShellRunner()
    return (
        SystemCollector(runner),
        CpuCollector(runner),
        MemoryCollector(),
        DiskCollector(runner),
        NetworkCollector(runner),
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
