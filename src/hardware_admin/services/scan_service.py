"""Orquestación del análisis completo del equipo."""

import logging
import time
import uuid
from collections.abc import Callable, Container, Sequence
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

#: Límite total del escaneo básico. Al excederlo se entregan resultados
#: parciales en lugar de esperar indefinidamente.
DEFAULT_BUDGET_SECONDS = 60.0


@dataclass(slots=True)
class ScanService:
    collectors: tuple[HardwareCollector, ...]
    diagnostic_engine: RuleBasedDiagnosticEngine

    @staticmethod
    def _prepare_session(collectors: Sequence[HardwareCollector]) -> None:
        """Prepara e inicializa de forma determinista una nueva sesión de escaneo.

        Limpia las instancias compartidas de SafePowerShellRunner y reinicia
        los proveedores con captura por escaneo (ThermalSnapshotProvider)
        asociados a los recolectores seleccionados, garantizando que los resultados
        obsoletos no persistan entre llamadas consecutivas a scan().
        """
        seen_runners: set[int] = set()
        seen_thermal_providers: set[int] = set()

        for collector in collectors:
            # 1. Limpieza de SafePowerShellRunner compartido (exactamente una vez por instancia)
            runner = getattr(collector, "runner", None)
            if runner is not None and id(runner) not in seen_runners:
                seen_runners.add(id(runner))
                try:
                    if hasattr(runner, "reset_session") and callable(runner.reset_session):
                        runner.reset_session()
                    elif hasattr(runner, "clear_cache") and callable(runner.clear_cache):
                        runner.clear_cache()
                except (OSError, RuntimeError, ValueError, AttributeError, TypeError) as exc:  # pragma: no cover
                    LOGGER.warning("Error al reiniciar SafePowerShellRunner: %s", exc)

            # 2. Reinicio de ThermalSnapshotProvider compartido (exactamente una vez por instancia)
            thermal_provider = getattr(collector, "thermal_provider", None)
            if thermal_provider is not None and id(thermal_provider) not in seen_thermal_providers:
                seen_thermal_providers.add(id(thermal_provider))
                try:
                    if hasattr(thermal_provider, "reset_session") and callable(thermal_provider.reset_session):
                        thermal_provider.reset_session()
                    elif hasattr(thermal_provider, "reset") and callable(thermal_provider.reset):
                        thermal_provider.reset()
                except (OSError, RuntimeError, ValueError, AttributeError, TypeError) as exc:  # pragma: no cover
                    LOGGER.warning("Error al reiniciar proveedor térmico: %s", exc)

            # 3. Recolectores personalizados que implementen reset_session
            if hasattr(collector, "reset_session") and callable(collector.reset_session):
                try:
                    collector.reset_session()
                except (OSError, RuntimeError, ValueError, AttributeError, TypeError) as exc:  # pragma: no cover
                    LOGGER.warning("Error al reiniciar recolector %s: %s", collector, exc)

    def scan(
        self,
        on_progress: ProgressCallback | None = None,
        only: Container[ComponentKind] | None = None,
        symptom: str | None = None,
        expected_device: str | None = None,
        budget_seconds: float = DEFAULT_BUDGET_SECONDS,
    ) -> DiagnosticReport:
        """Ejecuta recolectores y entrega un reporte normalizado.

        Con `only` se analiza un subconjunto de componentes en lugar del equipo
        completo; el reporte resultante sólo contiene esos resultados. El síntoma
        y el dispositivo esperado son contexto opcional del usuario y se tratan
        como datos, nunca como instrucciones.
        """
        selected = tuple(
            collector
            for collector in self.collectors
            if only is None or collector.component in only
        )
        self._prepare_session(selected)
        total = len(selected)
        if total == 0:
            return self.diagnostic_engine.build_report(
                (), symptom, expected_device
            )

        session = uuid.uuid4().hex[:8]
        started = time.monotonic()
        ordered_results: dict[int, ComponentResult] = {}
        workers = min(4, total)
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="collector") as executor:
            futures: dict[Future[ComponentResult], int] = {
                executor.submit(self._collect_safely, collector, session): index
                for index, collector in enumerate(selected)
            }
            try:
                for completed_count, future in enumerate(
                    as_completed(futures, timeout=budget_seconds), start=1
                ):
                    index = futures[future]
                    result = future.result()
                    ordered_results[index] = result
                    if on_progress:
                        on_progress(completed_count, total, result.name)
            except TimeoutError:
                # Se agotó el presupuesto: se cancela lo que no arrancó y se
                # entrega lo obtenido. Lo que quedó fuera se declara como no
                # consultado, nunca como sano.
                for future in futures:
                    future.cancel()
                LOGGER.warning(
                    "scan_budget_exceeded session=%s budget_s=%.1f completed=%d of=%d",
                    session,
                    budget_seconds,
                    len(ordered_results),
                    total,
                )

        results = tuple(
            ordered_results.get(index) or self._not_collected(selected[index], budget_seconds)
            for index in range(total)
        )
        LOGGER.info(
            "scan_completed session=%s components=%d skipped=%d duration_ms=%d",
            session,
            total,
            total - len(ordered_results),
            int((time.monotonic() - started) * 1000),
        )
        return self.diagnostic_engine.build_report(results, symptom, expected_device)

    @staticmethod
    def _not_collected(
        collector: HardwareCollector, budget_seconds: float
    ) -> ComponentResult:
        """Componente que no llegó a consultarse dentro del presupuesto.

        Se marca como error de consulta, no como desconocido: así aparece en
        las limitaciones del reporte. Una prueba omitida no equivale a
        hardware sano.
        """
        detalle = (
            f"No se consultó: se agotó el límite de escaneo de {budget_seconds:.0f} s."
        )
        return ComponentResult(
            component=collector.component,
            name=collector.component.value,
            facts={"Resultado": "No consultado", "Detalle": detalle},
            summary="No consultado",
            status=HealthStatus.ERROR,
            possible_problem=f"Sin evaluar: se alcanzó el límite total de escaneo "
            f"({budget_seconds:.0f} s)",
            evidence=(
                EvidenceRecord(
                    source="Aplicación",
                    query="presupuesto de escaneo",
                    output=detalle,
                    collected_at=datetime.now(UTC),
                    succeeded=False,
                ),
            ),
        )

    @staticmethod
    def _collect_safely(collector: HardwareCollector, session: str = "-") -> ComponentResult:
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
            "collector_completed session=%s component=%s status=%s duration_ms=%d",
            session,
            result.component.value,
            result.status.value,
            int((time.monotonic() - started) * 1000),
        )
        return result
