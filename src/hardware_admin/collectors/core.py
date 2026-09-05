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
        measurements: list[Measurement] = [
            Measurement(
                name="Tiempo encendido",
                value=round(uptime.total_seconds() / 3600.0, 1),
                unit="h",
            )
        ]

        # 1. Consulta base del sistema operativo y fabricante
        result = self.runner.run(PowerShellQuery.SYSTEM_INFO)
        rows = parse_json_rows(result)
        has_system_info = False
        if rows:
            row = rows[0]
            has_system_info = True
            facts.update(
                {
                    "Fabricante": row.get("Fabricante") or "No disponible",
                    "Modelo": row.get("Modelo") or "No disponible",
                    "Sistema operativo": row.get("SistemaOperativo") or facts["Sistema"],
                }
            )

        # 2. Firmware, Placa base, TPM y Secure Boot
        firm_result = self.runner.run(PowerShellQuery.FIRMWARE_INFO)
        firm_rows = parse_json_rows(firm_result)
        has_firmware_info = False
        if firm_rows:
            f_row = firm_rows[0]
            has_firmware_info = True
            board_man = str(f_row.get("BoardManufacturer") or "").strip()
            board_prod = str(f_row.get("BoardProduct") or "").strip()
            board_ver = str(f_row.get("BoardVersion") or "").strip()
            board_text = f"{board_man} {board_prod}".strip()
            if board_ver and board_ver.lower() not in {"no disponible", "none", "null"}:
                board_text += f" (v{board_ver})"
            if board_text:
                facts["Placa base"] = board_text

            bios_vendor = str(f_row.get("BiosVendor") or "").strip()
            bios_ver = str(f_row.get("BiosVersion") or "").strip()
            bios_date = str(f_row.get("BiosDate") or "").strip()
            if bios_date.startswith("/Date(") and bios_date.endswith(")/"):
                try:
                    ts_ms = int(bios_date[6:-2])
                    dt = datetime.fromtimestamp(ts_ms / 1000.0, UTC)
                    bios_date = dt.strftime("%Y-%m-%d")
                except (ValueError, TypeError, OSError):
                    pass
            bios_text = f"{bios_vendor} {bios_ver}".strip()
            if bios_date and bios_date.lower() not in {"no disponible", "none"}:
                bios_text += f" ({bios_date.split('T')[0] if 'T' in bios_date else bios_date})"
            if bios_text:
                facts["BIOS / UEFI"] = bios_text

            tpm_present = bool(f_row.get("TpmPresent"))
            tpm_ready = bool(f_row.get("TpmReady"))
            tpm_enabled = bool(f_row.get("TpmEnabled"))
            if tpm_present:
                status_parts = []
                if tpm_enabled:
                    status_parts.append("Habilitado")
                if tpm_ready:
                    status_parts.append("Listo")
                facts["Módulo TPM"] = f"Presente ({', '.join(status_parts) if status_parts else 'Detectado'})"
            else:
                facts["Módulo TPM"] = "No detectado o no disponible"

            sb_val = f_row.get("SecureBoot")
            if isinstance(sb_val, bool):
                facts["Arranque seguro (Secure Boot)"] = "Habilitado" if sb_val else "Deshabilitado"
            else:
                facts["Arranque seguro (Secure Boot)"] = "No disponible o no soportado por el firmware"

        # 3. Batería y Administración de Energía
        batt_result = self.runner.run(PowerShellQuery.BATTERY_INFO)
        batt_rows = parse_json_rows(batt_result)
        if batt_rows:
            b_data = batt_rows[0]
            tiene_bateria = bool(b_data.get("TieneBateria"))
            plan = str(b_data.get("PlanEnergia") or "Equilibrado")
            facts["Plan de energía"] = plan

            baterias = b_data.get("Baterias") or []
            if tiene_bateria and isinstance(baterias, list) and baterias:
                b0 = baterias[0] if isinstance(baterias[0], dict) else {}
                charge = b0.get("EstimatedChargeRemaining")
                design_cap = b0.get("DesignCapacity")
                full_cap = b0.get("FullChargeCapacity")
                status_code = b0.get("BatteryStatus")

                st_desc = "En uso"
                if status_code == 2:
                    st_desc = "Cargando"
                elif status_code == 3:
                    st_desc = "Batería totalmente cargada"

                facts["Batería"] = f"{charge}% ({st_desc})" if charge is not None else "Presente"

                # Ciclos de carga y estado del cargador según reporte real ACPI
                ciclos = b0.get("CycleCount")
                facts["Ciclos de batería"] = (
                    str(ciclos)
                    if ciclos is not None and str(ciclos) not in ("0", "None", "")
                    else "No disponibles o no reportados por el controlador ACPI"
                )

                if status_code in (2, 6, 7, 8, 9):
                    charger_status = "Conectado a la corriente (Cargador activo)"
                elif status_code == 3:
                    charger_status = "Conectado a la corriente (Carga completa)"
                elif status_code == 1:
                    charger_status = "Desconectado (Operando con batería)"
                else:
                    charger_status = "No disponible o no reportado por el controlador ACPI"
                facts["Estado del cargador"] = charger_status

                if charge is not None:
                    try:
                        charge_val = float(charge)
                        measurements.append(
                            Measurement(
                                name="Carga de batería",
                                value=round(charge_val, 1),
                                unit="%",
                                expected_range=(10.0, 100.0),
                            )
                        )
                    except (ValueError, TypeError):
                        pass

                # Desgaste físico de batería
                if design_cap and full_cap:
                    try:
                        d_val = float(design_cap)
                        f_val = float(full_cap)
                        if d_val > 0:
                            wear_pct = max(0.0, min(100.0, (1.0 - (f_val / d_val)) * 100.0))
                            facts["Desgaste de batería"] = f"{wear_pct:.1f}%"
                            measurements.append(
                                Measurement(
                                    name="Desgaste de batería",
                                    value=round(wear_pct, 1),
                                    unit="%",
                                    expected_range=(0.0, 40.0),
                                )
                            )
                    except (ValueError, TypeError):
                        pass
                else:
                    facts["Desgaste de batería"] = "No reportado por el firmware SMBIOS"
            else:
                facts["Batería"] = "No aplica (Equipo de sobremesa sin batería)"
                facts["Ciclos de batería"] = "No aplica"
                facts["Estado del cargador"] = "No aplica"
        else:
            facts["Batería"] = "No disponible"
            facts["Plan de energía"] = "No disponible"
            facts["Ciclos de batería"] = "No disponible"
            facts["Estado del cargador"] = "No disponible"

        # 4. Inventario de periféricos extendidos (PnP)
        periph_result = self.runner.run(PowerShellQuery.PERIPHERALS_EXTENDED)
        periph_rows = parse_json_rows(periph_result)
        if periph_rows:
            bt_devs = [r for r in periph_rows if str(r.get("Class", "")).lower() == "bluetooth"]
            audio_devs = [r for r in periph_rows if str(r.get("Class", "")).lower() in ("media", "audioendpoint")]
            cam_devs = [r for r in periph_rows if str(r.get("Class", "")).lower() in ("camera", "image")]
            input_devs = [r for r in periph_rows if str(r.get("Class", "")).lower() in ("keyboard", "mouse")]

            facts["Bluetooth"] = f"{len(bt_devs)} dispositivo(s) detectado(s)" if bt_devs else "No detectado o no disponible"
            facts["Cámara web"] = f"{len(cam_devs)} dispositivo(s) detectado(s)" if cam_devs else "No detectada o no disponible"
            facts["Audio y multimedia"] = f"{len(audio_devs)} dispositivo(s) detectado(s)" if audio_devs else "No disponible"
            facts["Dispositivos de entrada"] = f"{len(input_devs)} detectado(s) (teclado/ratón)" if input_devs else "No disponible"

            # Identificar fallos aislados en periféricos sin condenar el bus completo
            failing_periphs = [
                str(r.get("FriendlyName") or r.get("InstanceId") or "Dispositivo")
                for r in periph_rows
                if str(r.get("Status", "OK")).upper() != "OK"
            ]
            if failing_periphs:
                facts["Anomalías en periféricos"] = (
                    f"Problema localizado en periférico(s): {', '.join(failing_periphs)}. "
                    "El controlador anfitrión y el resto del sistema operan con normalidad."
                )
        else:
            facts["Bluetooth"] = "No disponible o no consultable"
            facts["Cámara web"] = "No disponible o no consultable"

        output = "\n".join(f"{key}: {value}" for key, value in facts.items())
        evidence = [_evidence("Python/platform", "platform.uname()", output)]
        if result.output or result.error:
            evidence.append(
                _evidence(
                    "PowerShell (System)",
                    "Get-CimInstance Win32_OperatingSystem / Win32_ComputerSystem",
                    result.output or result.error,
                    result.exit_code == 0,
                )
            )
        if firm_result.output or firm_result.error:
            evidence.append(
                _evidence(
                    "PowerShell (Firmware)",
                    "Get-CimInstance Win32_BIOS / Win32_BaseBoard / Get-Tpm / Confirm-SecureBootUEFI",
                    firm_result.output or firm_result.error,
                    firm_result.exit_code == 0,
                )
            )
        if batt_result.output or batt_result.error:
            evidence.append(
                _evidence(
                    "PowerShell (Battery)",
                    "Get-CimInstance Win32_Battery / Win32_PowerPlan",
                    batt_result.output or batt_result.error,
                    batt_result.exit_code == 0,
                )
            )

        if has_system_info and has_firmware_info:
            confidence = ConfidenceLevel.HIGH
        elif has_system_info:
            confidence = ConfidenceLevel.MEDIUM
        else:
            confidence = ConfidenceLevel.LOW

        return ComponentResult(
            self.component,
            "Información del sistema",
            facts,
            summary=f"{facts['Sistema operativo']}",
            status=HealthStatus.NORMAL,
            evidence=tuple(evidence),
            confidence=confidence,
            measurements=tuple(measurements),
            is_supported=True,
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


_SMBIOS_MEMORY_TYPES: dict[int, str] = {
    20: "DDR",
    21: "DDR2",
    22: "DDR2 FB-DIMM",
    24: "DDR3",
    26: "DDR4",
    27: "LPDDR",
    28: "LPDDR2",
    29: "LPDDR3",
    30: "LPDDR4",
    31: "Dispositivo no volátil lógico",
    32: "HBM",
    33: "HBM2",
    34: "DDR5",
    35: "LPDDR5",
}

_FORM_FACTORS: dict[int, str] = {
    8: "DIMM",
    12: "SODIMM",
    13: "SRIMM",
    14: "SMD",
    15: "SIMM",
    16: "PIM",
    17: "RIMM",
    18: "SO-DIMM",
}


def _decode_memory_type(smbios_type: Any, mem_type: Any) -> str:
    """Decodifica el tipo de memoria según el estándar DMTF SMBIOS sin inventar generaciones."""
    for val in (smbios_type, mem_type):
        if val is not None:
            try:
                numeric = int(val)
                if numeric in _SMBIOS_MEMORY_TYPES:
                    return _SMBIOS_MEMORY_TYPES[numeric]
            except (ValueError, TypeError):
                continue
    return "No especificado por SMBIOS"


def _decode_form_factor(ff: Any) -> str:
    if ff is not None:
        try:
            numeric = int(ff)
            if numeric in _FORM_FACTORS:
                return _FORM_FACTORS[numeric]
        except (ValueError, TypeError):
            pass
    return "No especificado"


class MemoryCollector:
    component = ComponentKind.MEMORY

    def __init__(self, runner: SafePowerShellRunner | None = None) -> None:
        self.runner = runner or SafePowerShellRunner()

    def collect(self) -> ComponentResult:
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        facts: dict[str, Any] = {
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
        measurements: list[Measurement] = [
            Measurement("Capacidad total RAM", round(memory.total / (1024**3), 2), "GB"),
            Measurement("Uso de memoria", round(memory.percent, 1), "%", (0.0, 85.0)),
        ]

        # Consulta de módulos físicos de memoria (SMBIOS Win32_PhysicalMemory)
        phys_result = self.runner.run(PowerShellQuery.PHYSICAL_MEMORY_MODULES)
        raw_modules = parse_json_rows(phys_result)
        has_modules = False

        if raw_modules:
            has_modules = True
            modules_list: list[dict[str, Any]] = []
            speeds: list[int] = []
            for mod in raw_modules:
                cap_val = mod.get("Capacity")
                speed_val = mod.get("ConfiguredClockSpeed") or mod.get("Speed")
                slot_id = str(mod.get("DeviceLocator") or mod.get("BankLabel") or "Ranura").strip()
                cap_str = format_bytes(float(cap_val)) if cap_val is not None else "No disponible"
                speed_str = f"{speed_val} MHz" if speed_val is not None else "No disponible"
                mfg_str = str(mod.get("Manufacturer") or "No disponible").strip()
                part_str = str(mod.get("PartNumber") or "No disponible").strip()
                type_str = _decode_memory_type(mod.get("SMBIOSMemoryType"), mod.get("MemoryType"))
                ff_str = _decode_form_factor(mod.get("FormFactor"))

                if speed_val is not None:
                    try:
                        speeds.append(int(speed_val))
                    except (ValueError, TypeError):
                        pass

                modules_list.append(
                    {
                        "Ranura": slot_id,
                        "Capacidad": cap_str,
                        "Tipo / Generación": type_str,
                        "Factor de forma": ff_str,
                        "Velocidad": speed_str,
                        "Fabricante": mfg_str,
                        "Parte": part_str,
                    }
                )

            facts["Módulos físicos"] = modules_list
            facts["Ranuras ocupadas"] = len(modules_list)
            facts["Límite de ampliación"] = (
                "Pendiente de validación de compatibilidad con placa base (Asesor E2)"
            )
            if speeds:
                avg_speed = int(sum(speeds) / len(speeds))
                measurements.append(Measurement("Velocidad configurada RAM", avg_speed, "MHz"))
        else:
            facts["Módulos físicos"] = "No reportados por el firmware SMBIOS"
            facts["Límite de ampliación"] = "No determinado sin inventario SMBIOS (Asesor E2)"

        status = MEMORY_RULE.classify(memory.percent)
        problem = "Poca memoria disponible" if status is not HealthStatus.NORMAL else None
        output = (
            "psutil.virtual_memory()\n"
            f"total={memory.total}, available={memory.available}, "
            f"used={memory.used}, percent={memory.percent}\n\n"
            f"Get-CimInstance Win32_PhysicalMemory:\n{phys_result.output or phys_result.error}"
        )

        evidence = [
            _evidence("psutil", "psutil.virtual_memory()", output, True),
        ]
        if phys_result.output or phys_result.error:
            evidence.append(
                _evidence(
                    "PowerShell (SMBIOS)",
                    "Get-CimInstance Win32_PhysicalMemory",
                    phys_result.output or phys_result.error,
                    phys_result.exit_code == 0,
                )
            )

        confidence = ConfidenceLevel.HIGH if has_modules else ConfidenceLevel.MEDIUM

        return ComponentResult(
            self.component,
            "Memoria RAM",
            facts,
            summary=f"{memory.percent:.0f}% de uso",
            status=status,
            possible_problem=problem,
            evidence=tuple(evidence),
            confidence=confidence,
            measurements=tuple(measurements),
            is_supported=True,
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
        MemoryCollector(runner),
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
