"""Orquestación del análisis completo del equipo."""

import logging
import time
from collections.abc import Callable, Container
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime

from hardware_admin.collectors.base import HardwareCollector
from hardware_admin.diagnostics.engine import RuleBasedDiagnosticEngine
from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    DiagnosticReport,
    EvidenceRecord,
    HealthStatus,
)

ProgressCallback = Callable[[int, int, str], None]
LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ScanService:
    collectors: tuple[HardwareCollector, ...]
    diagnostic_engine: RuleBasedDiagnosticEngine

    def scan(
        self,
        on_progress: ProgressCallback | None = None,
        only: Container[ComponentKind] | None = None,
    ) -> DiagnosticReport:
        """Ejecuta recolectores y entrega un reporte normalizado.

        Con `only` se analiza un subconjunto de componentes en lugar del equipo
        completo; el reporte resultante sólo contiene esos resultados.
        """
        selected = tuple(
            collector
            for collector in self.collectors
            if only is None or collector.component in only
        )
        total = len(selected)
        if total == 0:
            return self.diagnostic_engine.build_report(())

        ordered_results: dict[int, ComponentResult] = {}
        workers = min(4, total)
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="collector") as executor:
            futures: dict[Future[ComponentResult], int] = {
                executor.submit(self._collect_safely, collector): index
                for index, collector in enumerate(selected)
            }
            for completed_count, future in enumerate(as_completed(futures), start=1):
                index = futures[future]
                result = future.result()
                ordered_results[index] = result
                if on_progress:
                    on_progress(completed_count, total, result.name)

        results = tuple(ordered_results[index] for index in range(total))
        return self.diagnostic_engine.build_report(results)

    @staticmethod
    def _collect_safely(collector: HardwareCollector) -> ComponentResult:
        started = time.monotonic()
        try:
            result = collector.collect()
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            result = ComponentResult(
                component=collector.component,
                name=collector.component.value,
                facts={"Resultado": "Consulta fallida", "Detalle": message},
                summary="Error de consulta",
                status=HealthStatus.ERROR,
                possible_problem="No fue posible obtener información",
                evidence=(
                    EvidenceRecord(
                        source="Aplicación",
                        query="collector.collect()",
                        output=message,
                        collected_at=datetime.now(UTC),
                        succeeded=False,
                    ),
                ),
            )
            LOGGER.exception("collector_failed component=%s", collector.component.value)
        LOGGER.info(
            "collector_completed component=%s status=%s duration_ms=%d",
            result.component.value,
            result.status.value,
            int((time.monotonic() - started) * 1000),
        )
        return result
