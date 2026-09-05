# ADR-003: Evaluación y Selección de Proveedores de Sensores Térmicos (Fase F3)

**Fecha**: 2026-09-05  
**Estado**: F3 EN IMPLEMENTACIÓN  
**Contexto**: Hoja de Ruta Comercial - Fase F3 (`docs/COMMERCIAL_ROADMAP.md`).

---

## 1. Contexto y Objetivos

El objetivo de la Fase F3 es incorporar capacidades de telemetría térmica y de rendimiento físico:
- Temperaturas de CPU, GPU y Almacenamiento.
- Frecuencias reales y detección explicable de sobrecalentamiento / thermal throttling documentado.
- Ventiladores y voltajes únicamente cuando el hardware los exponga con certeza documental y técnica.

### Restricciones Arquitectónicas Innegociables
1. **100% Local y Sin Base de Datos**: Sin SQLite ni bases de datos externas.
2. **Sin Elevación Automática Silenciosa ni Instalación de Drivers Inseguros**: Cualquier driver de kernel de terceros no firmado o con firmas revocadas (vulnerabilidades BYOVD) está vetado. No se permite LibreHardwareMonitor, OpenHardwareMonitor ni pythonnet.
3. **Sin Telemetría, Cuentas ni Red Externa**.
4. **Degradación Segura**: Un sensor no reportado por el fabricante debe declararse explícitamente como `NOT_SUPPORTED` / No disponible, nunca falsear temperatura como 0 °C ni inferir salud artificial.
5. **No inferir thermal throttling de CurrentClockSpeed vs MaxClockSpeed**: Esa comparación de clocks no constituye evidencia de estrangulamiento térmico (la frecuencia varía por estados P/C de ahorro energético y cargas mononúcleo/multinúcleo). El throttling solo se marca si el proveedor reporta una señal explícita y documentada (p. ej. banderas `clocks_throttle_reasons` de NVIDIA).
6. **No asumir soporte no verificado**: DXGI y WMI AMD no exponen temperatura de forma estándar y verificable sin APIs propietarias/drivers específicos; por tanto, sin fuente oficial se declaran `NOT_SUPPORTED`.

---

## 2. Fuentes Oficiales Directas y Evaluación Técnica

Se evaluaron tres fuentes principales disponibles en el ecosistema Windows con base en documentación oficial:

### Alternativa A: Proveedor Nativo Windows (WMI / CIM / ThermalZone)
- **Fuentes Oficiales**:
  - Microsoft Docs: Class `MSAcpi_ThermalZoneTemperature` en namespace `root\wmi` ([MSDN ACPI Thermal Zones](https://learn.microsoft.com/en-us/windows-hardware/drivers/bringup/acpi-thermal-management)).
  - Unidad oficial: décimas de Kelvin (`CurrentTemperature` en dK). Fórmula canónica de conversión: `Celsius = (dK - 2732) / 10.0`.
- **Licencia**: Nativa del sistema operativo Windows (sin dependencias adicionales).
- **Mantenimiento y Firma**: Oficial de Microsoft, núcleo de Windows.
- **Comportamiento en Hardware Real**:
  - En laptops y equipos con driver ACPI expuesto a nivel de usuario, devuelve lecturas válidas.
  - En placas base desktop o configuraciones con permisos restringidos, devuelve `HRESULT 0x80041003` (Access Denied / Permiso denegado) o colección vacía.
  - Se maneja con degradación segura: si la consulta devuelve permiso denegado o no hay instancias, se reporta `HealthStatus.ERROR` (con detalle de permisos) o `HealthStatus.NOT_SUPPORTED`, jamás fingiendo salud o temperatura cero.

### Alternativa B: LibreHardwareMonitorLib / OpenHardwareMonitor (Kernel Driver DLL)
- **Fuentes**: Biblioteca .NET / C# invocable vía Python (`pythonnet`) o sidecar local.
- **Licencia**: Mozilla Public License 2.0 (MPL 2.0) / GPLv3.
- **Riesgos**: Requiere driver de kernel sin certificación WHQL comercial vigente en anillo 0 (`WinRing0.sys`), elevación obligatoria de privilegios y riesgo de bloqueo por HVCI/VBS en Windows 11. **Descartada por violación de directrices de seguridad.**

### Alternativa C: Interfaces Especializadas por Subsistema (Híbrido Nativo / CLI Vendor Oficial)
- **Fuentes Oficiales Directas**:
  - **Almacenamiento**: Cmdlet oficial de Windows Storage Management `Get-StorageReliabilityCounter` ([Microsoft Learn: Storage Cmdlets](https://learn.microsoft.com/en-us/powershell/module/storage/get-storagereliabilitycounter)). Expone propiedad `Temperature` en grados Celsius enteros. Reutiliza la recolección segura de F2 sin duplicar llamadas.
  - **GPU NVIDIA**: Herramienta oficial `nvidia-smi.exe` provista por el controlador firmado por NVIDIA ([NVIDIA Management Library / nvidia-smi Documentation](https://developer.nvidia.com/nvidia-system-management-interface)).
    - Binario validado en rutas confiables fijas: `%SystemRoot%\System32\nvidia-smi.exe` o `%ProgramFiles%\NVIDIA Corporation\NVSMI\nvidia-smi.exe` (nunca PATH arbitrario).
    - Parámetros oficiales de allowlist cerrada: `--query-gpu=index,name,temperature.gpu,utilization.gpu,fan.speed,power.draw,clocks.current.graphics,clocks_throttle_reasons.hw_thermal_slowdown,clocks_throttle_reasons.sw_thermal_slowdown --format=csv,noheader,nounits`.
    - Detección de thermal throttling basada exclusivamente en campos explícitos de hardware/software thermal slowdown de NVIDIA.
  - **GPU AMD / Intel**: No existe un equivalente nativo CLI sin instalar software adicional de terceros o drivers propietarios no estándar. Se reporta limpiamente como `NOT_SUPPORTED`.
  - **CPU**: Se consulta `MSAcpi_ThermalZoneTemperature` con conversión dK -> °C y `psutil.cpu_freq()`. Si el fabricante no expone zonas térmicas ACPI legibles por el usuario, se declara `NOT_SUPPORTED` sin inferir valores ficticios.
- **Licencia**: Cero dependencias adicionales. Sin drivers de terceros.

---

## 3. Matriz Comparativa

| Criterio | Alt A: Nativo WMI ThermalZone | Alt B: LibreHardwareMonitorLib | Alt C: Híbrido Especializado (Aprobada) |
|---|---|---|---|
| **Dependencias externas** | Cero (solo Python stdlib / CIM) | Requiere DLL C#, pythonnet o sidecar | Cero adicionales (CIM + CLI oficial vendor) |
| **Riesgo de seguridad / BYOVD** | Ninguno | Alto (driver de kernel de terceros) | Ninguno |
| **Requiere elevación obligatoria** | No (degrada a NOT_SUPPORTED/PERM) | Sí (el driver falla sin admin) | No (lee lo expuesto por drivers oficiales) |
| **Soporte Intel / AMD CPU** | Dependiente de ACPI OEM | Universal | Telemetría ACPI cuando esté disponible |
| **Soporte GPU NVIDIA** | Muy limitado | Completo | Excelente y oficial (nvidia-smi) |
| **Soporte GPU AMD / Intel** | No disponible | Completo | Limpiamente `NOT_SUPPORTED` |
| **Temperatura Almacenamiento** | N/A | Soportado | Totalmente cubierto con Get-StorageReliability |
| **Detección Throttling** | No soportada | Estimada | Banderas oficiales documentadas (NVIDIA) |

---

## 4. Diseño de la Interfaz Interna Desacoplada

Para garantizar el principio de arquitectura limpia y desacoplamiento, la telemetría térmica se implementa mediante contratos de dominio tipados y una interfaz reemplazable:

```python
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from hardware_admin.domain.models import ConfidenceLevel, HealthStatus, Measurement

@dataclass(frozen=True, slots=True)
class ThermalReading:
    source_name: str
    target_hardware: str          # CPU, GPU, STORAGE, CHIPSET
    temperature_celsius: float | None
    unit: str
    collected_at: datetime
    duration_seconds: float | None
    confidence: ConfidenceLevel
    status: HealthStatus
    is_supported: bool
    detail: str
    is_throttling: bool | None = None
    fan_rpm: int | None = None
    power_watts: float | None = None
    clock_mhz: float | None = None
    measurements: tuple[Measurement, ...] = ()

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
```

### Proveedores implementados:
1. `NullThermalProvider`: fallback canónico que devuelve cobertura explícita no soportada.
2. `WmiThermalZoneProvider`: consulta ACPI con parseo seguro de dK a Celsius y degradación por permisos.
3. `StorageThermalProvider`: reutiliza la evidencia F2 de `Get-StorageReliabilityCounter`.
4. `NvidiaGpuThermalProvider`: consulta oficial estricta a `nvidia-smi` en rutas del sistema protegidas.

---

## 5. Decisión y Reglas de Rollback

- **Decisión**: Se implementa la **Alternativa C (Híbrido Especializado)** con interfaz `ThermalSensorProvider`.
- **Procedimiento de Rollback**: Para deshabilitar la telemetría térmica o volver a la línea base previa, basta con instanciar `NullThermalProvider` en `ScanService` y en los recolectores de diagnóstico, devolviendo de inmediato `NOT_SUPPORTED` sin ejecutar consultas WMI térmicas ni `nvidia-smi`.
- **Fase F4**: Permanece **ESTRICTAMENTE NO INICIADA**.
