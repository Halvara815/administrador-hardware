"""Contratos de datos compartidos por recolectores, diagnóstico e interfaz."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class HealthStatus(StrEnum):
    UNKNOWN = "unknown"
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    ERROR = "error"
    NOT_SUPPORTED = "not_supported"
    CANCELLED = "cancelled"


class ConfidenceLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ComponentKind(StrEnum):
    SYSTEM = "system"
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    NETWORK = "network"
    USB = "usb"
    PCI = "pci"
    DRIVER = "driver"
    PROBLEM_DEVICE = "problem_device"
    MONITOR_GPU = "monitor_gpu"
    IO = "io"


@dataclass(frozen=True, slots=True)
class Measurement:
    """Medición cuantitativa técnica con unidad física y rangos esperados."""

    name: str
    value: float | int
    unit: str
    expected_range: tuple[float, float] | None = None
    duration_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    source: str
    query: str
    output: str
    collected_at: datetime
    succeeded: bool = True


@dataclass(frozen=True, slots=True)
class ThermalReading:
    """Lectura de telemetría térmica tipada con trazabilidad completa."""

    source_name: str
    target_hardware: str
    temperature_celsius: float | None
    unit: str
    collected_at: datetime
    duration_seconds: float | None
    confidence: ConfidenceLevel
    status: HealthStatus
    is_supported: bool
    detail: str
    is_throttling: bool | None = None
    fan_percent: int | None = None
    fan_rpm: int | None = None
    power_watts: float | None = None
    clock_mhz: float | None = None
    measurements: tuple[Measurement, ...] = ()


@dataclass(frozen=True, slots=True)
class WindowsCriticalEvent:
    """Registro tipado de un evento crítico del sistema Windows (Fase F4)."""

    timestamp: str
    event_id: int
    level: str
    provider: str
    message: str
    category: str
    is_kernel_power_41: bool = False


class ConnectivityStage(StrEnum):
    ADAPTER = "adapter"
    LOCAL_IP = "local_ip"
    GATEWAY = "gateway"
    EXTERNAL_IP = "external_ip"
    DNS = "dns"


@dataclass(frozen=True, slots=True)
class ConnectivityCheckResult:
    stage: ConnectivityStage
    target: str
    succeeded: bool
    details: str = ""


@dataclass(frozen=True, slots=True)
class ComponentResult:
    component: ComponentKind
    name: str
    facts: dict[str, Any]
    summary: str = "Sin datos"
    status: HealthStatus = HealthStatus.UNKNOWN
    possible_problem: str | None = None
    evidence: tuple[EvidenceRecord, ...] = field(default_factory=tuple)
    confidence: ConfidenceLevel = ConfidenceLevel.LOW
    measurements: tuple[Measurement, ...] = field(default_factory=tuple)
    is_supported: bool = True


@dataclass(frozen=True, slots=True)
class Recommendation:
    """Procedimiento correctivo propuesto, nunca ejecutado por la aplicación.

    `modifies_system` distingue comprobar de alterar: separa «revisar el
    Administrador de dispositivos» de «ejecutar ipconfig /release». La
    aplicación describe el procedimiento y lo deja en manos del usuario;
    no ejecuta release/renew, limpieza de DNS ni cambios de controladores.
    """

    component: ComponentKind
    title: str
    cause: str
    steps: tuple[str, ...]
    rationale: str
    verification: str
    modifies_system: bool = False


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    started_at: datetime
    completed_at: datetime
    results: tuple[ComponentResult, ...]
    conclusion: str
    limitations: tuple[str, ...] = field(default_factory=tuple)
    #: Contexto opcional aportado por el usuario. El síntoma se trata como dato,
    #: nunca como instrucción; obliga a proponer diagnóstico adicional si todo
    #: el análisis básico figura sin anomalías (caso C5 del enunciado).
    symptom: str | None = None
    #: Dispositivo que el usuario espera detectar; ausencia no se confunde
    #: con salud física ni se usa para condenar un bus completo.
    expected_device: str | None = None
    #: Procedimientos propuestos, ordenados por gravedad. Vacío cuando no hay
    #: anomalías ni síntoma: no se inventan recomendaciones sin motivo.
    recommendations: tuple[Recommendation, ...] = field(default_factory=tuple)
    #: Fichas locales de ampliación generadas a partir de inventario y contexto
    #: voluntario de la sesión. Se mantiene opcional para conservar la
    #: compatibilidad de los reportes y motores anteriores.
    upgrade_advice: dict[str, Any] = field(default_factory=dict)

    @property
    def has_problems(self) -> bool:
        """Indica si existe al menos una advertencia o problema confirmado.

        Un `ERROR` de consulta no equivale a `CRITICAL`: la falta de evidencia
        nunca se interpreta aquí como hardware dañado (se expone en limitaciones).
        """
        return any(
            result.status in {HealthStatus.WARNING, HealthStatus.CRITICAL}
            for result in self.results
        )
