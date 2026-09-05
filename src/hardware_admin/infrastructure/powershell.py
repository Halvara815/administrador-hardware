"""Ejecución segura de un catálogo cerrado de consultas PowerShell."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class PowerShellQuery(StrEnum):
    SYSTEM_INFO = "system_info"
    CPU_INFO = "cpu_info"
    USB_PRESENT = "usb_present"
    PCI_PRESENT = "pci_present"
    DRIVERS = "drivers"
    PROBLEM_DEVICES = "problem_devices"
    VIDEO_CONTROLLERS = "video_controllers"
    DISKS = "disks"
    PHYSICAL_DISKS = "physical_disks"
    VOLUMES = "volumes"
    USB_STORAGE = "usb_storage"
    NETWORK_ADAPTERS = "network_adapters"
    NETWORK_CONFIGURATION = "network_configuration"


@dataclass(frozen=True, slots=True)
class CommandResult:
    query: PowerShellQuery
    output: str
    exit_code: int
    timed_out: bool = False
    error: str = ""


_QUERY_SCRIPTS: dict[PowerShellQuery, str] = {
    PowerShellQuery.SYSTEM_INFO: """
        $os = Get-CimInstance Win32_OperatingSystem
        $pc = Get-CimInstance Win32_ComputerSystem
        $data = @([PSCustomObject]@{
            Fabricante=$pc.Manufacturer; Modelo=$pc.Model;
            SistemaOperativo=$os.Caption; Version=$os.Version;
            Arquitectura=$os.OSArchitecture; Usuario=$pc.UserName
        })
    """,
    PowerShellQuery.CPU_INFO: """
        $data = @(Get-CimInstance Win32_Processor |
            Select-Object Name,Manufacturer,NumberOfCores,NumberOfLogicalProcessors,
                MaxClockSpeed,SocketDesignation)
    """,
    PowerShellQuery.USB_PRESENT: """
        $data = @(Get-PnpDevice -PresentOnly |
            Where-Object {$_.InstanceId -like 'USB*'} |
            Select-Object -First 100 Status,Class,FriendlyName,InstanceId,Problem)
    """,
    PowerShellQuery.PCI_PRESENT: """
        $data = @(Get-PnpDevice -PresentOnly |
            Where-Object {$_.InstanceId -like 'PCI*'} |
            Select-Object -First 100 Status,Class,FriendlyName,InstanceId,Problem)
    """,
    PowerShellQuery.DRIVERS: """
        $data = @(Get-CimInstance Win32_PnPSignedDriver |
            Where-Object {$_.DeviceName} |
            Select-Object -First 150 `
                @{Name='Nombre';Expression={$_.DeviceName}},
                @{Name='Tipo';Expression={$_.DeviceClass}},
                @{Name='Estado';Expression={if ($_.IsSigned) {'Firmado'} else {'No firmado'}}},
                DriverVersion,DriverDate,Manufacturer,IsSigned,DeviceID,HardWareID)
    """,
    PowerShellQuery.PROBLEM_DEVICES: """
        $data = @(Get-PnpDevice -PresentOnly |
            Where-Object {$_.Status -ne 'OK'} |
            Select-Object -First 100 Status,Class,FriendlyName,InstanceId,Problem)
    """,
    PowerShellQuery.VIDEO_CONTROLLERS: """
        $gpu = @(Get-CimInstance Win32_VideoController | ForEach-Object {
            [PSCustomObject]@{Tipo='GPU'; Nombre=$_.Name; Estado=$_.Status;
                Procesador=$_.VideoProcessor;
                Memoria=$_.AdapterRAM; Resolucion=("{0}x{1}" -f $_.CurrentHorizontalResolution,
                $_.CurrentVerticalResolution); Driver=$_.DriverVersion;
                PNPDeviceID=$_.PNPDeviceID}
        })
        $monitor = @(Get-CimInstance Win32_DesktopMonitor | ForEach-Object {
            [PSCustomObject]@{Tipo='Monitor'; Nombre=$_.Name; Estado=$_.Status;
                Procesador=$null;
                Memoria=$null; Resolucion=$null; Driver=$null;
                PNPDeviceID=$_.PNPDeviceID}
        })
        $data = @($gpu) + @($monitor)
    """,
    PowerShellQuery.DISKS: """
        $data = @(Get-Disk | Select-Object `
            @{Name='Unidad';Expression={$_.Number}},
            @{Name='Dispositivo';Expression={$_.FriendlyName}},
            @{Name='Tipo de bus';Expression={$_.BusType}},
            @{Name='Estado';Expression={$_.OperationalStatus}},
            @{Name='Salud';Expression={$_.HealthStatus}},
            @{Name='Capacidad';Expression={$_.Size}},PartitionStyle)
    """,
    PowerShellQuery.PHYSICAL_DISKS: """
        $data = @(Get-PhysicalDisk | Select-Object `
            DeviceId,FriendlyName,MediaType,BusType,OperationalStatus,HealthStatus,Size)
    """,
    PowerShellQuery.VOLUMES: """
        $data = @(Get-Volume | Select-Object `
            DriveLetter,FileSystemLabel,FileSystem,DriveType,HealthStatus,OperationalStatus,Size,SizeRemaining)
    """,
    PowerShellQuery.USB_STORAGE: """
        $data = @(Get-Disk | Where-Object {$_.BusType -eq 'USB'} | ForEach-Object {
            $numero = $_.Number
            $letras = @(Get-Partition -DiskNumber $numero -ErrorAction SilentlyContinue |
                Where-Object {$_.DriveLetter} | ForEach-Object {[string]$_.DriveLetter})
            [PSCustomObject]@{
                Numero=$numero;
                Dispositivo=$_.FriendlyName;
                Salud=$_.HealthStatus;
                Estado=$_.OperationalStatus;
                EstiloParticion=$_.PartitionStyle;
                Volumenes=($letras -join ',');
            }
        })
    """,
    PowerShellQuery.NETWORK_ADAPTERS: """
        $data = @(Get-NetAdapter | Select-Object Name,InterfaceDescription,
            Status,MacAddress,LinkSpeed)
    """,
    PowerShellQuery.NETWORK_CONFIGURATION: """
        $data = @(Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object {$_.IPEnabled} | ForEach-Object {
            [PSCustomObject]@{
                Descripcion=$_.Description;
                MAC=$_.MACAddress;
                IPv4=@($_.IPAddress | Where-Object {$_ -like '*.*'}) -join ', ';
                IPv6=@($_.IPAddress | Where-Object {$_ -like '*:*'}) -join ', ';
                Gateway=@($_.DefaultIPGateway) -join ', ';
                DNS=@($_.DNSServerSearchOrder) -join ', ';
                DHCPEnabled=$_.DHCPEnabled;
            }
        })
    """,
}


class SafePowerShellRunner:
    """Ejecuta sólo consultas enumeradas, sin aceptar fragmentos del usuario."""

    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self.timeout_seconds = timeout_seconds

    def run(self, query: PowerShellQuery) -> CommandResult:
        script = _QUERY_SCRIPTS[query]
        complete_script = (
            "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new();"
            "$ErrorActionPreference='Stop';"
            f"{script};"
            "ConvertTo-Json -InputObject $data -Compress -Depth 5"
        )
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            completed = subprocess.run(
                [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    complete_script,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
                creationflags=creation_flags,
            )
        except subprocess.TimeoutExpired as exc:
            partial = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else ""
            return CommandResult(query, partial or "", -1, timed_out=True, error="Tiempo agotado")
        except OSError as exc:
            return CommandResult(query, "", -1, error=str(exc))

        return CommandResult(
            query=query,
            output=completed.stdout.strip(),
            exit_code=completed.returncode,
            error=completed.stderr.strip(),
        )


def parse_json_rows(result: CommandResult) -> list[dict[str, Any]]:
    """Normaliza una respuesta JSON como una lista de diccionarios."""
    if result.exit_code != 0 or not result.output:
        return []
    parsed = json.loads(result.output)
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return [row for row in parsed if isinstance(row, dict)]
    return []


def powershell_available() -> bool:
    """Informa si las consultas específicas de Windows son aplicables."""
    return sys.platform == "win32"
