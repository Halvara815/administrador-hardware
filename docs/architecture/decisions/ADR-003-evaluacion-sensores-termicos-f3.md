# ADR-003: Evaluación y Selección de Proveedores de Sensores Térmicos (Fase F3)

**Fecha**: 2026-09-05  
**Estado**: PROPUESTO / investigación documentada  
**Implementación F3**: NO INICIADA  
**Contexto**: Hoja de Ruta Comercial - Fase F3 (`docs/COMMERCIAL_ROADMAP.md`).

---

## 1. Contexto y Objetivos

El objetivo de la Fase F3 es incorporar capacidades de telemetría térmica y de rendimiento físico:
- Temperaturas de CPU, GPU y Almacenamiento.
- Frecuencias reales y detección determinista de sobrecalentamiento / thermal throttling.
- Ventiladores y voltajes cuando el hardware los exponga con certeza.

### Restricciones Arquitectónicas Innegociables
1. **100% Local y Sin Base de Datos**: Sin SQLite ni bases de datos externas.
2. **Sin Elevación Automática Silenciosa ni Instalación de Drivers Inseguros**: Cualquier driver de kernel de terceros no firmado o con firmas revocadas (vulnerabilidades BYOVD) está vetado.
3. **Sin Telemetría, Cuentas ni Red Externa**.
4. **Degradación Segura**: Un sensor no reportado por el fabricante debe declararse explícitamente como `NOT_SUPPORTED` / No disponible, nunca falsear temperatura como 0 °C ni inferir salud artificial.

---

## 2. Evaluación Comparativa de Alternativas Técnicas

Se evaluaron tres fuentes principales disponibles en el ecosistema Windows:

### Alternativa A: Proveedor Nativo Windows (WMI / CIM / ThermalZone / Perfmon)
- **Fuentes**:
  - `root\wmi:MSAcpi_ThermalZoneTemperature`
  - Contadores de rendimiento `\Thermal Zone Information(*)\Temperature`
  - Consultas PowerShell/CIM `Get-CimInstance Win32_PerfFormattedData_Counters_ThermalZoneInformation`
- **Licencia**: Nativa del sistema operativo Windows (sin dependencias adicionales).
- **Mantenimiento**: Oficial de Microsoft.
- **Firma / Seguridad**: Componentes del núcleo de Windows firmados por Microsoft. No requiere drivers de terceros.
- **Compatibilidad**:
  - **Ventajas**: Funciona de forma estándar en laptops modernas que implementan ACPI Thermal Zones.
  - **Limitaciones**: Muchas placas base de sobremesa (desktop OEM o personalizadas) no exponen temperaturas por núcleo vía ACPI WMI, requiriendo a menudo permisos de Administrador o devolviendo valores fijos/antiguos si el fabricante no implementó la interfaz ACPI estándar.

### Alternativa B: LibreHardwareMonitorLib / OpenHardwareMonitor (Kernel Driver DLL)
- **Fuentes**: Biblioteca .NET / C# invocable vía Python (`pythonnet`) o sidecar local.
- **Licencia**: Mozilla Public License 2.0 (MPL 2.0) / GPLv3.
- **Mantenimiento**: Proyecto activo en GitHub (LibreHardwareMonitor).
- **Firma / Seguridad**:
  - Requiere cargar un driver de kernel (`WinRing0.sys` / `LibreHardwareMonitor.sys`) para acceder a MSRs de CPU y SMBus.
  - Los drivers de kernel para lectura de anillos requieren privilegios elevados de Administrador obligatorios.
  - El uso de drivers de lectura de MSR no firmados con certificados comerciales EV vigentes puede ser bloqueado por Windows 11 (VBS / Hypervisor-protected Code Integrity - HVCI / Vulnerable Driver Blocklist).
- **Compatibilidad**: Excelente para CPUs Intel/AMD y GPU múltiples, pero introduce una dependencia binaria pesada y riesgo de seguridad por elevación.

### Alternativa C: Interfaces Especializadas por Subsistema (Híbrido Nativo / CLI Vendor)
- **Fuentes**:
  - **Almacenamiento**: `Get-StorageReliabilityCounter` (captura nativa de temperatura NVMe/SSD ya integrada en F2).
  - **GPU NVIDIA**: `nvidia-smi.exe --query-gpu=temperature.gpu,utilization.gpu,power.draw --format=csv,noheader,nounits` (ejecutable nativo provisto oficialmente por el driver firmado por NVIDIA en `%ProgramFiles%\NVIDIA Corporation\NVSMI\nvidia-smi.exe` o `System32`).
  - **GPU AMD**: `Get-CimInstance` sobre proveedores WMI AMD o métricas DXGI.
  - **CPU**: Fallback a WMI ThermalZone + consulta de throttling vía `Win32_Processor` (`CurrentClockSpeed`, `MaxClockSpeed`).
- **Licencia**: Libre de dependencias externas en tiempo de compilación.
- **Mantenimiento**: Mantenido por Microsoft y los fabricantes de GPU (NVIDIA/AMD/Intel).
- **Firma / Seguridad**: Todos los componentes son binarios del SO o instalados oficialmente por el controlador del fabricante con firma WHQL válida.

---

## 3. Matriz Comparativa

| Criterio | Alt A: Nativo WMI ThermalZone | Alt B: LibreHardwareMonitorLib | Alt C: Híbrido Especializado (Recomendada) |
|---|---|---|---|
| **Dependencias externas** | Cero (solo Python stdlib / CIM) | Requiere DLL C#, pythonnet o sidecar | Cero adicionales (CIM + CLI oficial vendor) |
| **Riesgo de seguridad / BYOVD** | Ninguno | Alto (driver de kernel de terceros) | Ninguno |
| **Requiere elevación obligatoria** | No (degrada a NOT_SUPPORTED) | Sí (el driver falla sin admin) | No (lee lo expuesto por drivers de usuario) |
| **Soporte Intel / AMD CPU** | Dependiente de ACPI OEM | Universal | Telemetría básica + throttling ratio |
| **Soporte GPU NVIDIA / AMD** | Muy limitado | Completo | Excelente en NVIDIA (nvidia-smi), fallback WMI |
| **Temperatura Almacenamiento** | N/A | Soportado | Totalmente cubierto con Get-StorageReliability |
| **Facilidad PyInstaller** | Inmediata (sin DLLs C# nativas) | Compleja (gestión de runtime .NET) | Inmediata |

---

## 4. Diseño de la Interfaz Interna Desacoplada

Para garantizar el principio de arquitectura limpia y permitir sustituir o incorporar proveedores sin afectar al motor de diagnóstico ni a los modelos de dominio, se propone la siguiente abstracción interna (sin implementar código aún):

`python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

@dataclass(frozen=True, slots=True)
class ThermalReading:
    source_name: str          # ej. CPU Package, GPU NVIDIA RTX 3070, NVMe SSD
    target_hardware: str      # CPU, GPU, STORAGE
    temperature_celsius: float | None
    is_throttling: bool | None
    fan_rpm: int | None
    power_watts: float | None
    status_note: str          # ej. Normal, NOT_SUPPORTED, Requiere permisos de administrador

class ThermalSensorProvider(ABC):
    "Contrato base para cualquier proveedor de telemetría térmica."

    @abstractmethod
    def is_available(self) -> bool:
        "Indica si el proveedor está soportado y presente en el equipo actual."
        ...

    @abstractmethod
    def read_temperatures(self) -> Sequence[ThermalReading]:
        "Obtiene lecturas instantáneas seguras sin bloquear ni generar falsas alertas."
        ...
`

### Proveedores a implementar en la futura Fase F3:
1. `StorageThermalProvider`: reutiliza los contadores fiables ya endurecidos en F2 (`Get-StorageReliabilityCounter`).
2. `NvidiaGpuThermalProvider`: consulta segura a `nvidia-smi` con allowlist cerrada (`SafeCommandRunner`).
3. `WmiThermalZoneProvider`: consulta estándar a `root\wmi` con degradación a `NOT_SUPPORTED`.
4. `NullThermalProvider`: fallback transparente cuando el equipo no expone sensores térmicos.

---

## 5. Decisión y Pasos Siguientes

- **Decisión**: Se aprueba la **Alternativa C (Híbrido Especializado)** como propuesta de proveedor canónico base, complementado por la interfaz desacoplada `ThermalSensorProvider`.
- **Estado de F3**: PROPUESTO / investigación documentada.
- **Implementación F3**: **NO INICIADA**. No se han instalado dependencias de terceros, no se ha modificado el entorno virtual ni se ha escrito código de recolección térmica funcional en esta etapa.
