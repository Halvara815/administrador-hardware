"""Ejecución segura de un catálogo cerrado de consultas PowerShell."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from concurrent.futures import Future
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
    STORAGE_RELIABILITY = "storage_reliability"
    BATTERY_INFO = "battery_info"
    FIRMWARE_INFO = "firmware_info"
    PHYSICAL_MEMORY_MODULES = "physical_memory_modules"
    PERIPHERALS_EXTENDED = "peripherals_extended"
    THERMAL_ZONE = "thermal_zone"
    CRITICAL_EVENTS = "critical_events"


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
    PowerShellQuery.STORAGE_RELIABILITY: """
        $data = @(Get-PhysicalDisk -ErrorAction SilentlyContinue | ForEach-Object {
            $disk = $_
            $rel = $null
            $err = $null
            try {
                $rel = Get-StorageReliabilityCounter -PhysicalDisk $disk -ErrorAction Stop
            } catch {
                $err = $_.Exception.Message
            }
            [PSCustomObject]@{
                DeviceId = $disk.DeviceId;
                FriendlyName = $disk.FriendlyName;
                MediaType = $disk.MediaType;
                BusType = $disk.BusType;
                OperationalStatus = $disk.OperationalStatus;
                HealthStatus = $disk.HealthStatus;
                Temperature = if ($rel) { $rel.Temperature } else { $null };
                Wear = if ($rel) { $rel.Wear } else { $null };
                ReadErrorsTotal = if ($rel) { $rel.ReadErrorsTotal } else { $null };
                WriteErrorsTotal = if ($rel) { $rel.WriteErrorsTotal } else { $null };
                PowerOnHours = if ($rel) { $rel.PowerOnHours } else { $null };
                ReliabilityError = $err
            }
        })
    """,
    PowerShellQuery.BATTERY_INFO: """
        $batt = @(Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue | Select-Object `
            Name,DeviceID,EstimatedChargeRemaining,BatteryStatus,DesignCapacity,FullChargeCapacity,EstimatedRunTime,CycleCount)
        $plan = Get-CimInstance -Namespace root\\cimv2\\power -ClassName Win32_PowerPlan -Filter "IsActive = True" -ErrorAction SilentlyContinue
        $data = @([PSCustomObject]@{
            Baterias = $batt;
            TieneBateria = ($batt.Count -gt 0);
            PlanEnergia = if ($plan) { $plan.ElementName } else { "Equilibrado" }
        })
    """,
    PowerShellQuery.FIRMWARE_INFO: """
        $bios = Get-CimInstance Win32_BIOS -ErrorAction SilentlyContinue
        $board = Get-CimInstance Win32_BaseBoard -ErrorAction SilentlyContinue
        $tpm = Get-Tpm -ErrorAction SilentlyContinue
        $sb = $null
        try {
            $sb = Confirm-SecureBootUEFI -ErrorAction SilentlyContinue
        } catch {
            $sb = $null
        }
        $data = @([PSCustomObject]@{
            BiosVendor = if ($bios) { $bios.Manufacturer } else { "No disponible" };
            BiosVersion = if ($bios) { $bios.SMBIOSBIOSVersion } else { "No disponible" };
            BiosDate = if ($bios) { $bios.ReleaseDate } else { "No disponible" };
            BoardManufacturer = if ($board) { $board.Manufacturer } else { "No disponible" };
            BoardProduct = if ($board) { $board.Product } else { "No disponible" };
            BoardVersion = if ($board) { $board.Version } else { "No disponible" };
            TpmPresent = if ($tpm) { [bool]$tpm.TpmPresent } else { $false };
            TpmReady = if ($tpm) { [bool]$tpm.TpmReady } else { $false };
            TpmEnabled = if ($tpm) { [bool]$tpm.TpmEnabled } else { $false };
            SecureBoot = if ($sb -ne $null) { [bool]$sb } else { "No disponible" }
        })
    """,
    PowerShellQuery.PHYSICAL_MEMORY_MODULES: """
        $data = @(Get-CimInstance Win32_PhysicalMemory -ErrorAction SilentlyContinue | Select-Object `
            BankLabel,DeviceLocator,Capacity,Speed,ConfiguredClockSpeed,Manufacturer,PartNumber,FormFactor,MemoryType,SMBIOSMemoryType)
    """,
    PowerShellQuery.PERIPHERALS_EXTENDED: """
        $classes = @('Bluetooth', 'Media', 'Camera', 'Image', 'Keyboard', 'Mouse')
        $data = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
            Where-Object { $classes -contains $_.Class } |
            Select-Object -First 100 Status,Class,FriendlyName,InstanceId,Problem)
    """,
    PowerShellQuery.THERMAL_ZONE: """
        $data = @(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue |
            Select-Object InstanceName, CurrentTemperature, CriticalTripPoint, ThermalStamp)
    """,
    PowerShellQuery.CRITICAL_EVENTS: """
        try {
            $startTime = (Get-Date).AddDays(-7)
            $filter = @{
                LogName = 'System'
                StartTime = $startTime
                Level = @(1, 2)
            }
            $rawEvents = Get-WinEvent -FilterHashtable $filter -MaxEvents 50 -ErrorAction Stop
            $events = $rawEvents | Where-Object {
                $_.ProviderName -match 'WHEA|disk|Ntfs|storahci|storport|Kernel-Power|BugCheck|volmgr|EventLog'
            } | Select-Object -First 30 @{Name='Timestamp';Expression={$_.TimeCreated.ToString('o')}},
                @{Name='Id';Expression={$_.Id}},
                @{Name='Nivel';Expression={$_.LevelDisplayName}},
                @{Name='Proveedor';Expression={$_.ProviderName}},
                @{Name='Mensaje';Expression={($_.Message -split "`r?`n")[0].Trim()}}
            $data = @($events)
        } catch {
            $msg = $_.Exception.Message
            if ($msg -match 'No events were found|No se encontraron eventos') {
                $data = @()
            } else {
                Write-Error "ERROR_GET_WINEVENT: $msg"
                exit 1
            }
        }
    """,
}


#: Techo de la salida que se acepta interpretar. Una respuesta mayor indica que
#: algo no salió como se esperaba y no compensa intentar parsearla.
MAX_OUTPUT_CHARS = 1_000_000


class UnknownQuery(KeyError):
    """Se pidió ejecutar algo que no pertenece al catálogo cerrado.

    El rechazo ocurre antes de invocar el intérprete: ninguna cadena externa
    llega nunca a componerse como comando.
    """


class MalformedQueryOutput(ValueError):
    """La consulta terminó bien pero su salida no es un inventario legible.

    Se distingue de una lista vacía a propósito: vacío significa «sin filas»,
    y esto significa «no se pudo leer». Confundirlos haría pasar un fallo de
    lectura por ausencia de dispositivos.
    """


class SafePowerShellRunner:
    """Ejecuta sólo consultas enumeradas, sin aceptar fragmentos del usuario."""

    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self.timeout_seconds = timeout_seconds
        self._cache: dict[PowerShellQuery, CommandResult] = {}
        self._inflight: dict[PowerShellQuery, Future[CommandResult]] = {}
        self._lock = threading.Lock()

    def clear_cache(self) -> None:
        """Limpia la caché de resultados de consultas."""
        with self._lock:
            self._cache.clear()

    def reset_session(self) -> None:
        """Limpia la caché de consultas para una nueva sesión de escaneo."""
        self.clear_cache()

    def run(self, query: PowerShellQuery, use_cache: bool = True) -> CommandResult:
        # Comprobación explícita antes de tocar el intérprete: el catálogo es la
        # única fuente de comandos, y un fallo de búsqueda no debe parecer un
        # accidente del diccionario.
        script = _QUERY_SCRIPTS.get(query) if isinstance(query, PowerShellQuery) else None
        if script is None:
            raise UnknownQuery(
                f"La consulta {query!r} no pertenece al catálogo cerrado y no se ejecuta."
            )

        if not use_cache:
            return self._execute_query(query, script)

        with self._lock:
            if query in self._cache:
                return self._cache[query]
            if query in self._inflight:
                future = self._inflight[query]
                is_leader = False
            else:
                future = Future()
                self._inflight[query] = future
                is_leader = True

        if not is_leader:
            return future.result()

        try:
            res = self._execute_query(query, script)
        except BaseException as exc:
            with self._lock:
                self._inflight.pop(query, None)
                future.set_exception(exc)
            raise
        else:
            with self._lock:
                self._cache[query] = res
                self._inflight.pop(query, None)
                future.set_result(res)
            return res

    def _execute_query(self, query: PowerShellQuery, script: str) -> CommandResult:
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
    """Normaliza una respuesta JSON como una lista de diccionarios.

    Una salida corrupta levanta `MalformedQueryOutput` en lugar de devolver una
    lista vacía. La distinción importa: una lista vacía significa «la consulta
    se completó y no hay filas» —el caso «USB ausente» depende de eso—, así que
    un fallo de lectura no puede disfrazarse de inventario vacío.

    Una salida ausente con código de salida correcto sí es un inventario vacío
    legítimo: no hubo corrupción, simplemente no hay filas.
    """
    if result.exit_code != 0 or not result.output:
        return []

    if len(result.output) > MAX_OUTPUT_CHARS:
        # No se intenta interpretar una salida desmedida: el coste de parsearla
        # no compensa, y su tamaño ya indica que algo no salió como se esperaba.
        raise MalformedQueryOutput(
            f"La consulta «{result.query.value}» devolvió {len(result.output)} caracteres, "
            f"por encima del límite de tamaño de {MAX_OUTPUT_CHARS}."
        )

    try:
        parsed = json.loads(result.output)
    except json.JSONDecodeError as exc:
        raise MalformedQueryOutput(
            f"La consulta «{result.query.value}» no devolvió JSON válido "
            f"({exc.msg} en la posición {exc.pos}). "
            f"Inicio de la salida: {result.output[:120]!r}"
        ) from exc

    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return [row for row in parsed if isinstance(row, dict)]
    raise MalformedQueryOutput(
        f"La consulta «{result.query.value}» devolvió JSON válido pero no un "
        f"objeto ni una lista de filas, sino {type(parsed).__name__}."
    )


def powershell_available() -> bool:
    """Informa si las consultas específicas de Windows son aplicables."""
    return sys.platform == "win32"
