"""Clasificación central y comprobable de mediciones en estados de salud.

La rúbrica docente indica umbrales enteros (CPU 0–70, 71–89 y 90–100; RAM
<70, >=70 y <90, >=90). Este módulo los traduce a reglas continuas sin huecos
para que valores decimales (p. ej. 70.5 %) clasifiquen de forma determinista.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from hardware_admin.domain.models import HealthStatus


class MetricKind(StrEnum):
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"


@dataclass(frozen=True, slots=True)
class ThresholdRule:
    """Regla de clasificación por porcentaje con límites decimales.

    `warning_strict` controla el borde inferior de la advertencia:
    - CPU (NORMAL <=70): la advertencia empieza estrictamente después de 70.
    - RAM (<70 NORMAL): el propio 70 ya es advertencia.
    El límite superior nunca tiene huecos: el valor en el borde se eleva.
    """

    metric: MetricKind
    warning: float
    critical: float
    warning_strict: bool = False

    def classify(self, percent: float | None) -> HealthStatus:
        if percent is None:
            return HealthStatus.UNKNOWN
        if percent >= self.critical:
            return HealthStatus.CRITICAL
        warning_started = (
            percent > self.warning if self.warning_strict else percent >= self.warning
        )
        if warning_started:
            return HealthStatus.WARNING
        return HealthStatus.NORMAL


# CPU: NORMAL <=70; ADVERTENCIA >70 y <90; CRÍTICO >=90. La regla continua >70
# cubre los decimales sin huecos (interpretación documentada en el informe).
CPU_RULE = ThresholdRule(MetricKind.CPU, warning=70.0, critical=90.0, warning_strict=True)
# RAM: NORMAL <70; ADVERTENCIA >=70 y <90; CRÍTICO >=90.
MEMORY_RULE = ThresholdRule(MetricKind.MEMORY, warning=70.0, critical=90.0)
# Disco: política del proyecto conservada provisionalmente en 85/95; cualquier
# valor >=95, incluido el 96 % del enunciado, resulta CRÍTICO.
DISK_RULE = ThresholdRule(MetricKind.DISK, warning=85.0, critical=95.0)

RULES: dict[MetricKind, ThresholdRule] = {
    MetricKind.CPU: CPU_RULE,
    MetricKind.MEMORY: MEMORY_RULE,
    MetricKind.DISK: DISK_RULE,
}


def classify_percent(kind: MetricKind, percent: float | None) -> HealthStatus:
    """Clasifica una medición según la regla oficial de la métrica."""
    return RULES[kind].classify(percent)