"""Motor determinista que transforma evidencia en una conclusión explicable."""

from collections.abc import Sequence
from datetime import UTC, datetime

from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    DiagnosticReport,
    HealthStatus,
)


class RuleBasedDiagnosticEngine:
    def build_report(
        self,
        results: Sequence[ComponentResult],
        symptom: str | None = None,
        expected_device: str | None = None,
    ) -> DiagnosticReport:
        now = datetime.now(UTC)
        evidence_dates = [
            evidence.collected_at for result in results for evidence in result.evidence
        ]
        started = min(evidence_dates, default=now)
        failures = [result for result in results if result.status is HealthStatus.ERROR]
        alerts = [
            result
            for result in results
            if result.status in {HealthStatus.WARNING, HealthStatus.CRITICAL}
        ]

        conclusion_parts: list[str] = []
        by_kind = {result.component: result for result in results}
        memory = by_kind.get(ComponentKind.MEMORY)
        cpu = by_kind.get(ComponentKind.CPU)
        memory_alert = memory and memory.status in {
            HealthStatus.WARNING,
            HealthStatus.CRITICAL,
        }
        cpu_alert = cpu and cpu.status in {HealthStatus.WARNING, HealthStatus.CRITICAL}
        if memory_alert and cpu_alert and memory and cpu:
            conclusion_parts.append(
                "La causa más probable de lentitud es la saturación de recursos: "
                f"CPU ({cpu.summary.lower()}) y memoria RAM ({memory.summary.lower()})."
            )
        elif memory_alert and memory:
            conclusion_parts.append(
                f"La causa más probable de lentitud es la memoria RAM ({memory.summary.lower()})."
            )
        elif cpu_alert and cpu:
            conclusion_parts.append(
                f"La causa más probable de lentitud es la carga de CPU ({cpu.summary.lower()})."
            )

        other_alerts = [
            result
            for result in alerts
            if result.component not in {ComponentKind.CPU, ComponentKind.MEMORY}
        ]
        if other_alerts:
            descriptions = "; ".join(
                f"{result.name}: {result.possible_problem or result.summary}"
                for result in other_alerts
            )
            conclusion_parts.append(f"También se detectó: {descriptions}.")
        if alerts and not conclusion_parts:
            conclusion_parts.append(
                "Se detectaron advertencias que requieren revisión según la matriz."
            )
        if not alerts:
            conclusion_parts.append(
                "No se observan anomalías en los indicadores consultados."
            )
        if failures:
            conclusion_parts.append(
                "Algunas comprobaciones no pudieron completarse y no deben interpretarse como sanas."
            )
        if symptom and not alerts and not failures:
            conclusion_parts.append(
                "Como el síntoma persiste sin anomalías básicas, se requiere "
                "diagnóstico adicional de temperatura, fuente de alimentación, GPU, "
                "controladores, eventos del sistema, memoria RAM y el resto del hardware."
            )
        if expected_device and not alerts:
            conclusion_parts.append(
                f"El dispositivo esperado («{expected_device}») no se usó para "
                "condenar ningún bus: su ausencia requiere confirmación por ID."
            )

        limitations = tuple(
            f"{result.name}: {result.possible_problem or 'consulta no disponible'}"
            for result in failures
        )
        return DiagnosticReport(
            started_at=started,
            completed_at=now,
            results=tuple(results),
            conclusion=" ".join(conclusion_parts),
            limitations=limitations,
            symptom=symptom,
            expected_device=expected_device,
        )
