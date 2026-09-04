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
class EvidenceRecord:
    source: str
    query: str
    output: str
    collected_at: datetime
    succeeded: bool = True


@dataclass(frozen=True, slots=True)
class ComponentResult:
    component: ComponentKind
    name: str
    facts: dict[str, Any]
    summary: str = "Sin datos"
    status: HealthStatus = HealthStatus.UNKNOWN
    possible_problem: str | None = None
    evidence: tuple[EvidenceRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    started_at: datetime
    completed_at: datetime
    results: tuple[ComponentResult, ...]
    conclusion: str
    limitations: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_problems(self) -> bool:
        """Indica si existe al menos una advertencia o problema confirmado."""
        return any(
            result.status in {HealthStatus.WARNING, HealthStatus.CRITICAL}
            for result in self.results
        )
