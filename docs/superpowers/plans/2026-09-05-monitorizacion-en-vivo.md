# Monitorización en vivo y gráfico de E/S — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir muestreo periódico acotado de E/S con parada explícita y dibujarlo como dos gráficos de series de tiempo en el apartado de E/S.

**Architecture:** Un `MonitoringService` posee la serie en un `deque` acotado y la alimenta desde un hilo demonio; la UI pide instantáneas con `after()` y dibuja sobre `tkinter.Canvas`. El muestreador se inyecta, de modo que las pruebas son deterministas y no duermen.

**Tech Stack:** Python 3.11+, psutil, customtkinter, tkinter.Canvas, unittest. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-09-05-monitorizacion-en-vivo-design.md`

## Global Constraints

- El intérprete del proyecto es `.venv\Scripts\python.exe`. El `python` del PATH es 3.14 y **no** tiene pytest.
- Gates que deben quedar en verde: `.venv\Scripts\python.exe -m pytest -q`, `-m ruff check .`, `-m mypy`.
- mypy corre en modo `strict`: toda función lleva anotaciones completas.
- ruff: `line-length = 100`, con `E402` e `I` (orden de imports) activadas. Los imports van al encabezado del módulo.
- No se añaden dependencias: nada de matplotlib ni numpy.
- No se alteran contratos de `domain`, ni recolectores, ni reglas de `diagnostics`. `IoCollector` no se toca.
- No se modifica `NAV_ITEMS` (eso es la rebanada 4D).
- Textos de interfaz en español; identificadores y nombres de prueba en inglés, como el resto del proyecto.
- Sólo el hilo principal toca widgets.

---

### Task 1: Serie acotada y control de arranque/parada

**Files:**
- Create: `src/hardware_admin/services/monitoring_service.py`
- Test: `tests/test_monitoring_service.py`

**Interfaces:**
- Consumes: nada.
- Produces: `Sample` (dataclass congelada con `collected_at: datetime`, `disk_read_bps: float`, `disk_write_bps: float`, `net_sent_bps: float`, `net_recv_bps: float`), `Sampler = Callable[[], Sample | None]`, y `MonitoringService(sampler: Sampler, interval_seconds: float = 1.0, capacity: int = 300)` con `start() -> None`, `stop() -> None`, `snapshot() -> tuple[Sample, ...]`, `clear() -> None`, `is_running: bool` y `_collect_once() -> None`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_monitoring_service.py`:

```python
"""Pruebas del servicio de monitorizacion: buffer acotado, arranque y parada."""

import time
from datetime import UTC, datetime
from unittest import TestCase

from hardware_admin.services.monitoring_service import MonitoringService, Sample


def sample_at(second: int, read: float = 1.0) -> Sample:
    return Sample(
        collected_at=datetime(2026, 9, 5, 12, 0, second, tzinfo=UTC),
        disk_read_bps=read,
        disk_write_bps=2.0,
        net_sent_bps=3.0,
        net_recv_bps=4.0,
    )


class MonitoringServiceTests(TestCase):
    def test_buffer_keeps_only_the_most_recent_samples(self) -> None:
        """El buffer se corta en `capacity` y descarta lo mas antiguo."""
        service = MonitoringService(sampler=lambda: None, capacity=3)
        for index in range(5):
            service._samples.append(sample_at(index))

        snapshot = service.snapshot()
        self.assertEqual(len(snapshot), 3)
        self.assertEqual(snapshot[0].collected_at.second, 2)
        self.assertEqual(snapshot[-1].collected_at.second, 4)

    def test_collect_once_appends_the_sample_it_receives(self) -> None:
        service = MonitoringService(sampler=lambda: sample_at(7))
        service._collect_once()

        self.assertEqual(len(service.snapshot()), 1)
        self.assertEqual(service.snapshot()[0].collected_at.second, 7)

    def test_a_sampler_returning_none_adds_nothing(self) -> None:
        """La primera lectura no tiene con que comparar: no hay tasa que publicar."""
        service = MonitoringService(sampler=lambda: None)
        service._collect_once()

        self.assertEqual(service.snapshot(), ())

    def test_snapshot_is_an_immutable_copy(self) -> None:
        service = MonitoringService(sampler=lambda: sample_at(1))
        service._collect_once()
        snapshot = service.snapshot()
        service._collect_once()

        self.assertIsInstance(snapshot, tuple)
        self.assertEqual(len(snapshot), 1)

    def test_clear_empties_the_buffer(self) -> None:
        service = MonitoringService(sampler=lambda: sample_at(1))
        service._collect_once()
        service.clear()

        self.assertEqual(service.snapshot(), ())

    def test_start_and_stop_are_idempotent(self) -> None:
        service = MonitoringService(sampler=lambda: None, interval_seconds=0.01)
        service.start()
        service.start()
        self.assertTrue(service.is_running)

        service.stop()
        service.stop()
        self.assertFalse(service.is_running)

    def test_stop_halts_sampling(self) -> None:
        """Tras stop() no entra ninguna muestra mas."""
        service = MonitoringService(sampler=lambda: sample_at(1), interval_seconds=0.01)
        service.start()
        time.sleep(0.1)
        service.stop()
        captured = len(service.snapshot())

        time.sleep(0.1)
        self.assertEqual(len(service.snapshot()), captured)
        self.assertGreater(captured, 0)
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `.venv\Scripts\python.exe -m pytest tests/test_monitoring_service.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'hardware_admin.services.monitoring_service'`

- [ ] **Step 3: Implementación mínima**

Crear `src/hardware_admin/services/monitoring_service.py`:

```python
"""Muestreo periodico acotado de E/S con arranque y parada explicitos."""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Sample:
    """Una medicion instantanea de tasas de E/S, en bytes por segundo."""

    collected_at: datetime
    disk_read_bps: float
    disk_write_bps: float
    net_sent_bps: float
    net_recv_bps: float


#: Devuelve None cuando todavia no puede calcularse una tasa.
Sampler = Callable[[], "Sample | None"]


class MonitoringService:
    """Mantiene una serie acotada de muestras alimentada por un hilo demonio.

    El servicio es dueño de la serie: la interfaz pide instantaneas y nunca
    escribe en el buffer. El muestreador se inyecta para poder probar el
    servicio sin depender del hardware ni dormir entre muestras.
    """

    def __init__(
        self,
        sampler: Sampler,
        interval_seconds: float = 1.0,
        capacity: int = 300,
    ) -> None:
        self.sampler = sampler
        self.interval_seconds = interval_seconds
        self.capacity = capacity
        self._samples: deque[Sample] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Arranca el muestreo. Llamarlo dos veces no crea un segundo hilo."""
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="monitoring", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Detiene el muestreo y espera al hilo. Es seguro llamarlo de mas."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(self.interval_seconds * 2, 1.0))
        self._thread = None

    def snapshot(self) -> tuple[Sample, ...]:
        """Copia inmutable de la serie, la muestra mas reciente al final."""
        with self._lock:
            return tuple(self._samples)

    def clear(self) -> None:
        with self._lock:
            self._samples.clear()

    def _loop(self) -> None:
        # wait() devuelve True cuando piden parar, asi que la parada es
        # inmediata en vez de esperar a que acabe el intervalo en curso.
        while not self._stop_event.wait(self.interval_seconds):
            self._collect_once()

    def _collect_once(self) -> None:
        sample = self.sampler()
        if sample is None:
            return
        with self._lock:
            self._samples.append(sample)
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

Run: `.venv\Scripts\python.exe -m pytest tests/test_monitoring_service.py -v`
Expected: PASS, 7 pruebas

- [ ] **Step 5: Gates y commit**

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy
git add tests/test_monitoring_service.py src/hardware_admin/services/monitoring_service.py
git commit -m "feat(monitorizacion): serie acotada con arranque y parada explicitos"
```

---

### Task 2: Muestreador real sobre psutil, sin pico falso de arranque

**Files:**
- Modify: `src/hardware_admin/services/monitoring_service.py`
- Test: `tests/test_monitoring_service.py`

**Interfaces:**
- Consumes: `Sample` de la Task 1.
- Produces: `PsutilRateSampler(clock: Callable[[], float] = time.monotonic)`, invocable como `__call__() -> Sample | None`; devuelve `None` en la primera llamada.

- [ ] **Step 1: Escribir las pruebas que fallan**

Añadir al final de `tests/test_monitoring_service.py`:

```python
from unittest.mock import MagicMock, patch

from hardware_admin.services.monitoring_service import PsutilRateSampler


def io_counters(read: int, write: int) -> MagicMock:
    counters = MagicMock()
    counters.read_bytes = read
    counters.write_bytes = write
    return counters


def net_counters(sent: int, recv: int) -> MagicMock:
    counters = MagicMock()
    counters.bytes_sent = sent
    counters.bytes_recv = recv
    return counters


class PsutilRateSamplerTests(TestCase):
    @patch("psutil.net_io_counters")
    @patch("psutil.disk_io_counters")
    def test_first_reading_yields_no_sample(self, disk: MagicMock, net: MagicMock) -> None:
        """Sin lectura previa no hay tasa: publicarla seria un pico falso."""
        disk.return_value = io_counters(1000, 2000)
        net.return_value = net_counters(3000, 4000)
        sampler = PsutilRateSampler(clock=lambda: 100.0)

        self.assertIsNone(sampler())

    @patch("psutil.net_io_counters")
    @patch("psutil.disk_io_counters")
    def test_second_reading_divides_the_delta_by_the_elapsed_time(
        self, disk: MagicMock, net: MagicMock
    ) -> None:
        times = iter([100.0, 102.0])
        sampler = PsutilRateSampler(clock=lambda: next(times))

        disk.return_value = io_counters(1000, 2000)
        net.return_value = net_counters(3000, 4000)
        self.assertIsNone(sampler())

        disk.return_value = io_counters(1200, 2400)
        net.return_value = net_counters(3600, 4800)
        sample = sampler()

        assert sample is not None
        self.assertAlmostEqual(sample.disk_read_bps, 100.0)
        self.assertAlmostEqual(sample.disk_write_bps, 200.0)
        self.assertAlmostEqual(sample.net_sent_bps, 300.0)
        self.assertAlmostEqual(sample.net_recv_bps, 400.0)
        self.assertEqual(sample.collected_at.tzinfo, UTC)

    @patch("psutil.net_io_counters")
    @patch("psutil.disk_io_counters")
    def test_absent_disk_counters_are_reported_as_zero_not_as_a_crash(
        self, disk: MagicMock, net: MagicMock
    ) -> None:
        """psutil devuelve None en algunos equipos: es dato ausente, no un fallo."""
        times = iter([100.0, 101.0])
        sampler = PsutilRateSampler(clock=lambda: next(times))
        disk.return_value = None
        net.return_value = net_counters(3000, 4000)
        self.assertIsNone(sampler())

        net.return_value = net_counters(3100, 4100)
        sample = sampler()

        assert sample is not None
        self.assertEqual(sample.disk_read_bps, 0.0)
        self.assertAlmostEqual(sample.net_sent_bps, 100.0)

    @patch("psutil.net_io_counters")
    @patch("psutil.disk_io_counters")
    def test_a_counter_going_backwards_is_reported_as_zero(
        self, disk: MagicMock, net: MagicMock
    ) -> None:
        """Un contador que retrocede no puede dar una tasa negativa."""
        times = iter([100.0, 101.0])
        sampler = PsutilRateSampler(clock=lambda: next(times))
        disk.return_value = io_counters(5000, 5000)
        net.return_value = net_counters(5000, 5000)
        self.assertIsNone(sampler())

        disk.return_value = io_counters(10, 20)
        net.return_value = net_counters(30, 40)
        sample = sampler()

        assert sample is not None
        self.assertEqual(sample.disk_read_bps, 0.0)
        self.assertEqual(sample.net_recv_bps, 0.0)
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `.venv\Scripts\python.exe -m pytest tests/test_monitoring_service.py -k Psutil -v`
Expected: FAIL con `ImportError: cannot import name 'PsutilRateSampler'`

- [ ] **Step 3: Implementación mínima**

Añadir al encabezado de `monitoring_service.py`, respetando el orden de imports que exige ruff:

```python
import time
from datetime import UTC, datetime

import psutil
```

(La línea existente `from datetime import datetime` se sustituye por `from datetime import UTC, datetime`.)

Añadir al final del módulo:

```python
class PsutilRateSampler:
    """Convierte contadores acumulados de psutil en tasas por segundo.

    Guarda la lectura anterior porque una tasa necesita dos puntos. La
    primera llamada devuelve None en vez de inventar un pico de arranque.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._previous: tuple[float, float, float, float] | None = None
        self._previous_at: float = 0.0

    def __call__(self) -> Sample | None:
        disk = psutil.disk_io_counters()
        net = psutil.net_io_counters()
        current = (
            float(disk.read_bytes) if disk else 0.0,
            float(disk.write_bytes) if disk else 0.0,
            float(net.bytes_sent) if net else 0.0,
            float(net.bytes_recv) if net else 0.0,
        )
        now = self.clock()

        previous = self._previous
        previous_at = self._previous_at
        self._previous = current
        self._previous_at = now
        if previous is None:
            return None

        elapsed = max(now - previous_at, 1e-6)
        # Un contador que retrocede (reinicio o vuelco) se reporta como cero
        # en lugar de como una tasa negativa imposible.
        rates = [max(new - old, 0.0) / elapsed for new, old in zip(current, previous)]
        return Sample(
            collected_at=datetime.now(UTC),
            disk_read_bps=rates[0],
            disk_write_bps=rates[1],
            net_sent_bps=rates[2],
            net_recv_bps=rates[3],
        )
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

Run: `.venv\Scripts\python.exe -m pytest tests/test_monitoring_service.py -v`
Expected: PASS, 11 pruebas

- [ ] **Step 5: Gates y commit**

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy
git add tests/test_monitoring_service.py src/hardware_admin/services/monitoring_service.py
git commit -m "feat(monitorizacion): muestreador psutil sin pico falso de arranque"
```

---

### Task 3: Resumen con fecha y resistencia a fallos del muestreador

**Files:**
- Modify: `src/hardware_admin/services/monitoring_service.py`
- Test: `tests/test_monitoring_service.py`

**Interfaces:**
- Consumes: `Sample`, `MonitoringService` de la Task 1.
- Produces: `SeriesStats` (dataclass congelada con `peak: float`, `mean: float`), `MonitoringSummary` (dataclass congelada con `sample_count: int`, `started_at: datetime | None`, `ended_at: datetime | None`, `disk_read: SeriesStats`, `disk_write: SeriesStats`, `net_sent: SeriesStats`, `net_recv: SeriesStats`) y `MonitoringService.summary() -> MonitoringSummary`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Añadir estos métodos a la clase `MonitoringServiceTests`:

```python
    def test_summary_reports_peaks_means_and_window(self) -> None:
        service = MonitoringService(sampler=lambda: None)
        for index, read in enumerate((10.0, 30.0, 20.0)):
            service._samples.append(sample_at(index, read=read))

        summary = service.summary()
        self.assertEqual(summary.sample_count, 3)
        self.assertEqual(summary.disk_read.peak, 30.0)
        self.assertAlmostEqual(summary.disk_read.mean, 20.0)
        assert summary.started_at is not None and summary.ended_at is not None
        self.assertEqual(summary.started_at.second, 0)
        self.assertEqual(summary.ended_at.second, 2)

    def test_summary_of_an_empty_series_is_zero_without_dividing_by_zero(self) -> None:
        summary = MonitoringService(sampler=lambda: None).summary()

        self.assertEqual(summary.sample_count, 0)
        self.assertIsNone(summary.started_at)
        self.assertEqual(summary.disk_read.peak, 0.0)
        self.assertEqual(summary.disk_read.mean, 0.0)

    def test_a_failing_sampler_is_logged_without_killing_the_thread(self) -> None:
        """Un fallo de muestreo no debe tumbar la monitorizacion ni la app."""

        def boom() -> Sample | None:
            raise OSError("contador no disponible")

        service = MonitoringService(sampler=boom)
        with self.assertLogs("hardware_admin.services.monitoring_service", "ERROR"):
            service._collect_once()

        self.assertEqual(service.snapshot(), ())
        service._collect_once()
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `.venv\Scripts\python.exe -m pytest tests/test_monitoring_service.py -k "summary or failing_sampler" -v`
Expected: FAIL con `AttributeError: 'MonitoringService' object has no attribute 'summary'`

- [ ] **Step 3: Implementación mínima**

Añadir estas dataclases justo después de `Sample`:

```python
@dataclass(frozen=True, slots=True)
class SeriesStats:
    """Pico y media de una de las cuatro series."""

    peak: float
    mean: float


@dataclass(frozen=True, slots=True)
class MonitoringSummary:
    """Resumen con fecha de la serie capturada, listo para exportar en fase 5."""

    sample_count: int
    started_at: datetime | None
    ended_at: datetime | None
    disk_read: SeriesStats
    disk_write: SeriesStats
    net_sent: SeriesStats
    net_recv: SeriesStats
```

Añadir el método `summary()` a `MonitoringService`:

```python
    def summary(self) -> MonitoringSummary:
        """Picos, medias y ventana temporal de lo capturado hasta ahora."""
        samples = self.snapshot()
        if not samples:
            empty = SeriesStats(peak=0.0, mean=0.0)
            return MonitoringSummary(0, None, None, empty, empty, empty, empty)

        def stats(values: tuple[float, ...]) -> SeriesStats:
            return SeriesStats(peak=max(values), mean=sum(values) / len(values))

        return MonitoringSummary(
            sample_count=len(samples),
            started_at=samples[0].collected_at,
            ended_at=samples[-1].collected_at,
            disk_read=stats(tuple(item.disk_read_bps for item in samples)),
            disk_write=stats(tuple(item.disk_write_bps for item in samples)),
            net_sent=stats(tuple(item.net_sent_bps for item in samples)),
            net_recv=stats(tuple(item.net_recv_bps for item in samples)),
        )
```

Sustituir `_collect_once` por la versión que absorbe el fallo:

```python
    def _collect_once(self) -> None:
        try:
            sample = self.sampler()
        except Exception:
            # Un contador que falla es un dato ausente, no un motivo para
            # detener la monitorizacion ni para tumbar la aplicacion.
            LOGGER.exception("monitoring_sampler_failed")
            return
        if sample is None:
            return
        with self._lock:
            self._samples.append(sample)
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

Run: `.venv\Scripts\python.exe -m pytest tests/test_monitoring_service.py -v`
Expected: PASS, 14 pruebas

- [ ] **Step 5: Gates y commit**

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy
git add tests/test_monitoring_service.py src/hardware_admin/services/monitoring_service.py
git commit -m "feat(monitorizacion): resumen con fecha y muestreador a prueba de fallos"
```

---

### Task 4: Escalado de series como función pura

**Files:**
- Create: `src/hardware_admin/ui/charts.py`
- Test: `tests/test_charts.py`

**Interfaces:**
- Consumes: nada.
- Produces: `scale_series(values: Sequence[float], width: int, height: int, maximum: float | None = None) -> list[tuple[float, float]]`, con origen arriba-izquierda como en `tkinter.Canvas` y el valor más reciente a la derecha.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_charts.py`:

```python
"""Pruebas de la geometria de los graficos, sin abrir ninguna ventana."""

from unittest import TestCase

from hardware_admin.ui.charts import scale_series


class ScaleSeriesTests(TestCase):
    def test_an_empty_series_produces_no_points(self) -> None:
        self.assertEqual(scale_series([], 100, 50), [])

    def test_a_single_sample_sits_at_the_right_edge(self) -> None:
        """Lo mas reciente va a la derecha, tambien cuando solo hay un punto."""
        points = scale_series([5.0], 100, 50)

        self.assertEqual(len(points), 1)
        self.assertEqual(points[0][0], 100.0)

    def test_values_spread_across_the_full_width(self) -> None:
        points = scale_series([0.0, 5.0, 10.0], 100, 50)

        self.assertEqual([point[0] for point in points], [0.0, 50.0, 100.0])

    def test_the_maximum_reaches_the_top_and_zero_the_bottom(self) -> None:
        points = scale_series([0.0, 10.0], 100, 50)

        self.assertEqual(points[0][1], 50.0)
        self.assertEqual(points[1][1], 0.0)

    def test_an_all_zero_series_rests_on_the_baseline(self) -> None:
        """Todo en cero no puede provocar una division por cero."""
        points = scale_series([0.0, 0.0, 0.0], 100, 50)

        self.assertEqual([point[1] for point in points], [50.0, 50.0, 50.0])

    def test_an_explicit_maximum_is_honoured_and_clamped(self) -> None:
        points = scale_series([5.0, 20.0], 100, 50, maximum=10.0)

        self.assertEqual(points[0][1], 25.0)
        self.assertEqual(points[1][1], 0.0)
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `.venv\Scripts\python.exe -m pytest tests/test_charts.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'hardware_admin.ui.charts'`

- [ ] **Step 3: Implementación mínima**

Crear `src/hardware_admin/ui/charts.py`:

```python
"""Widgets de grafico sobre tkinter.Canvas, sin dependencias externas.

La geometria se calcula en funciones puras para poder comprobarla sin abrir
ventana, que es como estan escritas las pruebas de interfaz del proyecto.
"""

from __future__ import annotations

from collections.abc import Sequence


def scale_series(
    values: Sequence[float],
    width: int,
    height: int,
    maximum: float | None = None,
) -> list[tuple[float, float]]:
    """Convierte valores en coordenadas de lienzo.

    El origen es la esquina superior izquierda, como en tkinter.Canvas: el
    valor mayor queda arriba (y=0) y el cero abajo (y=height). El valor mas
    reciente se dibuja a la derecha.
    """
    if not values:
        return []

    top = maximum if maximum is not None else max(values)
    if top <= 0:
        # Serie plana en cero: sin escala util, todo descansa en la base.
        return [(_x_for(index, len(values), width), float(height)) for index in range(len(values))]

    points: list[tuple[float, float]] = []
    for index, value in enumerate(values):
        ratio = min(max(value / top, 0.0), 1.0)
        points.append((_x_for(index, len(values), width), height - ratio * height))
    return points


def _x_for(index: int, count: int, width: int) -> float:
    if count <= 1:
        return float(width)
    return index * (width / (count - 1))
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

Run: `.venv\Scripts\python.exe -m pytest tests/test_charts.py -v`
Expected: PASS, 6 pruebas

- [ ] **Step 5: Gates y commit**

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy
git add tests/test_charts.py src/hardware_admin/ui/charts.py
git commit -m "feat(ui): escalado de series de tiempo como funcion pura"
```

---

### Task 5: Widget de gráfico de series de tiempo

**Files:**
- Modify: `src/hardware_admin/ui/charts.py`
- Test: `tests/test_charts.py`

**Interfaces:**
- Consumes: `scale_series` de la Task 4.
- Produces: `format_rate(bps: float) -> str`, `SeriesSpec(label: str, color: str)` y `TimeSeriesChart(master: Any, title: str, specs: Sequence[SeriesSpec], height: int = 120)` con `update_series(series: Sequence[Sequence[float]], peak_label: str) -> None`.

- [ ] **Step 1: Escribir la prueba que falla**

Añadir a `tests/test_charts.py`:

```python
from hardware_admin.ui.charts import format_rate


class FormatRateTests(TestCase):
    def test_rates_use_human_readable_units_per_second(self) -> None:
        self.assertEqual(format_rate(0.0), "0.0 B/s")
        self.assertEqual(format_rate(1536.0), "1.5 KB/s")
        self.assertEqual(format_rate(1024.0 * 1024.0), "1.0 MB/s")

    def test_a_negative_rate_is_reported_as_zero(self) -> None:
        """Una tasa negativa no existe: se reporta como cero, no con signo."""
        self.assertEqual(format_rate(-5.0), "0.0 B/s")
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `.venv\Scripts\python.exe -m pytest tests/test_charts.py -k format_rate -v`
Expected: FAIL con `ImportError: cannot import name 'format_rate'`

- [ ] **Step 3: Implementación mínima**

Añadir al encabezado de `charts.py`, respetando el orden que exige ruff:

```python
import tkinter as tk
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import customtkinter as ctk

from hardware_admin.ui import theme
```

Añadir al final del módulo:

```python
def format_rate(bps: float) -> str:
    """Formatea una tasa en unidades legibles por segundo."""
    amount = max(bps, 0.0)
    for unit in ("B", "KB", "MB", "GB"):
        if amount < 1024 or unit == "GB":
            return f"{amount:.1f} {unit}/s"
        amount /= 1024
    return f"{amount:.1f} GB/s"


@dataclass(frozen=True, slots=True)
class SeriesSpec:
    """Nombre y color de una serie dentro de un grafico."""

    label: str
    color: str


class TimeSeriesChart(ctk.CTkFrame):
    """Grafico de lineas con su propio eje autoescalado.

    Cada grafico escala de forma independiente: disco y red difieren en
    ordenes de magnitud y un eje compartido dejaria la red pegada al cero.
    """

    def __init__(
        self,
        master: Any,
        title: str,
        specs: Sequence[SeriesSpec],
        height: int = 120,
    ) -> None:
        super().__init__(
            master,
            fg_color=theme.SURFACE,
            corner_radius=10,
            border_width=1,
            border_color=theme.BORDER,
        )
        self.specs = tuple(specs)
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            header,
            text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=theme.TEXT,
        ).grid(row=0, column=0, sticky="w")
        self.peak_label = ctk.CTkLabel(
            header, text="", font=ctk.CTkFont(size=11), text_color=theme.MUTED
        )
        self.peak_label.grid(row=0, column=1, sticky="e")

        self.canvas = tk.Canvas(
            self, height=height, background=theme.TERMINAL, highlightthickness=0, bd=0
        )
        self.canvas.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))

        legend = ctk.CTkFrame(self, fg_color="transparent")
        legend.grid(row=2, column=0, sticky="w", padx=12, pady=(0, 10))
        for column, spec in enumerate(self.specs):
            ctk.CTkLabel(
                legend,
                text=f"— {spec.label}",
                font=ctk.CTkFont(size=11),
                text_color=spec.color,
            ).grid(row=0, column=column, padx=(0 if column == 0 else 14, 0))

    def update_series(self, series: Sequence[Sequence[float]], peak_label: str) -> None:
        """Redibuja el grafico. Se llama solo desde el hilo principal."""
        self.peak_label.configure(text=peak_label)
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)

        # Escala comun a las series del mismo grafico para que sean comparables.
        top = max((max(values) for values in series if values), default=0.0)
        for spec, values in zip(self.specs, series):
            points = scale_series(values, width, height, maximum=top or None)
            if len(points) < 2:
                continue
            flat: list[float] = []
            for x, y in points:
                flat.extend((x, y))
            self.canvas.create_line(*flat, fill=spec.color, width=2)
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

Run: `.venv\Scripts\python.exe -m pytest tests/test_charts.py -v`
Expected: PASS, 8 pruebas

- [ ] **Step 5: Gates y commit**

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy
git add tests/test_charts.py src/hardware_admin/ui/charts.py
git commit -m "feat(ui): widget de grafico de series de tiempo sobre Canvas"
```

---

### Task 6: Panel de monitorización en el apartado de E/S

**Files:**
- Modify: `src/hardware_admin/ui/main_window.py`
- Test: `tests/test_ui_contract.py`

**Interfaces:**
- Consumes: `MonitoringService`, `PsutilRateSampler`, `Sample` (Tasks 1-3); `SeriesSpec`, `TimeSeriesChart`, `format_rate` (Tasks 4-5).
- Produces: `MONITORING_DISK_SPECS: tuple[SeriesSpec, ...]`, `MONITORING_NET_SPECS: tuple[SeriesSpec, ...]` y `series_for(samples: Sequence[Sample]) -> tuple[list[float], list[float], list[float], list[float]]` en `main_window.py`, en este orden: lectura, escritura, envío, recepción.

- [ ] **Step 1: Escribir la prueba que falla**

Añadir a `tests/test_ui_contract.py`:

```python
from datetime import UTC, datetime

from hardware_admin.services.monitoring_service import Sample
from hardware_admin.ui.main_window import (
    MONITORING_DISK_SPECS,
    MONITORING_NET_SPECS,
    series_for,
)


class MonitoringPanelContractTests(TestCase):
    def test_disk_and_network_are_two_charts_of_two_series_each(self) -> None:
        """Escalas separadas: disco y red difieren en ordenes de magnitud."""
        self.assertEqual(len(MONITORING_DISK_SPECS), 2)
        self.assertEqual(len(MONITORING_NET_SPECS), 2)
        labels = [spec.label for spec in MONITORING_DISK_SPECS + MONITORING_NET_SPECS]
        self.assertEqual(labels, ["Lectura", "Escritura", "Envío", "Recepción"])

    def test_series_for_splits_samples_into_four_ordered_series(self) -> None:
        samples = [
            Sample(datetime(2026, 9, 5, 12, 0, index, tzinfo=UTC), 1.0, 2.0, 3.0, 4.0)
            for index in range(3)
        ]

        read, write, sent, recv = series_for(samples)
        self.assertEqual(read, [1.0, 1.0, 1.0])
        self.assertEqual(write, [2.0, 2.0, 2.0])
        self.assertEqual(sent, [3.0, 3.0, 3.0])
        self.assertEqual(recv, [4.0, 4.0, 4.0])

    def test_series_for_an_empty_capture_yields_four_empty_series(self) -> None:
        self.assertEqual(series_for([]), ([], [], [], []))
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ui_contract.py -v`
Expected: FAIL con `ImportError: cannot import name 'MONITORING_DISK_SPECS'`

- [ ] **Step 3: Implementación mínima**

Añadir a los imports del encabezado de `main_window.py` (y `Sequence` a los de `collections.abc` si falta):

```python
from hardware_admin.services.monitoring_service import (
    MonitoringService,
    PsutilRateSampler,
    Sample,
)
from hardware_admin.ui.charts import SeriesSpec, TimeSeriesChart, format_rate
```

Tras `MATRIX_COLUMNS`, añadir:

```python
#: Series de cada grafico de monitorizacion, en orden de dibujo.
MONITORING_DISK_SPECS: tuple[SeriesSpec, ...] = (
    SeriesSpec("Lectura", theme.ACCENT_TEXT),
    SeriesSpec("Escritura", theme.YELLOW),
)
MONITORING_NET_SPECS: tuple[SeriesSpec, ...] = (
    SeriesSpec("Envío", theme.GREEN),
    SeriesSpec("Recepción", "#56D4DD"),
)


def series_for(
    samples: Sequence[Sample],
) -> tuple[list[float], list[float], list[float], list[float]]:
    """Separa las muestras en las cuatro series que dibujan los graficos."""
    return (
        [item.disk_read_bps for item in samples],
        [item.disk_write_bps for item in samples],
        [item.net_sent_bps for item in samples],
        [item.net_recv_bps for item in samples],
    )
```

En `HardwareAdminApp.__init__`, aceptar el servicio (parámetro opcional, para no romper a quien ya construye la app con un solo argumento) y registrar el cierre:

```python
    def __init__(
        self,
        scan_service: ScanService,
        monitoring_service: MonitoringService | None = None,
    ) -> None:
```

Dentro de `__init__`, junto al resto de atributos:

```python
        self.monitoring_service = monitoring_service or MonitoringService(
            sampler=PsutilRateSampler()
        )
        self.monitoring_job: str | None = None
```

Y al final de `__init__`:

```python
        self.protocol("WM_DELETE_WINDOW", self._on_close)
```

Al final de `_build_content`, tras construir `workspace`:

```python
        self._build_monitoring_panel(content)
```

Añadir estos métodos a `HardwareAdminApp`:

```python
    def _build_monitoring_panel(self, master: Any) -> None:
        """Panel de E/S en vivo: oculto salvo en el apartado de monitorizacion."""
        panel = ctk.CTkFrame(master, fg_color="transparent")
        panel.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        panel.grid_columnconfigure(0, weight=1)
        self.monitoring_panel = panel

        controls = ctk.CTkFrame(panel, fg_color="transparent")
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        controls.grid_columnconfigure(3, weight=1)
        self.monitoring_start_button = ctk.CTkButton(
            controls,
            text="Iniciar",
            command=self.start_monitoring,
            width=110,
            height=32,
            corner_radius=8,
            fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER,
        )
        self.monitoring_start_button.grid(row=0, column=0)
        self.monitoring_stop_button = ctk.CTkButton(
            controls,
            text="Detener",
            command=self.stop_monitoring,
            width=110,
            height=32,
            corner_radius=8,
            state="disabled",
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.SURFACE_HOVER,
            border_width=1,
            border_color=theme.BORDER,
            text_color=theme.TEXT,
        )
        self.monitoring_stop_button.grid(row=0, column=1, padx=8)
        self.monitoring_clear_button = ctk.CTkButton(
            controls,
            text="Limpiar",
            command=self.clear_monitoring,
            width=110,
            height=32,
            corner_radius=8,
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.SURFACE_HOVER,
            border_width=1,
            border_color=theme.BORDER,
            text_color=theme.TEXT,
        )
        self.monitoring_clear_button.grid(row=0, column=2)
        self.monitoring_status = ctk.CTkLabel(
            controls,
            text="Detenido · 0 muestras",
            text_color=theme.MUTED,
            font=ctk.CTkFont(size=11),
        )
        self.monitoring_status.grid(row=0, column=3, sticky="e")

        self.disk_chart = TimeSeriesChart(panel, "DISCO", MONITORING_DISK_SPECS)
        self.disk_chart.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.net_chart = TimeSeriesChart(panel, "RED", MONITORING_NET_SPECS)
        self.net_chart.grid(row=2, column=0, sticky="ew")
        panel.grid_remove()

    def start_monitoring(self) -> None:
        self.monitoring_service.start()
        self.monitoring_start_button.configure(state="disabled")
        self.monitoring_stop_button.configure(state="normal")
        self._refresh_monitoring()

    def stop_monitoring(self) -> None:
        self.monitoring_service.stop()
        self.monitoring_start_button.configure(state="normal")
        self.monitoring_stop_button.configure(state="disabled")
        if self.monitoring_job is not None:
            self.after_cancel(self.monitoring_job)
            self.monitoring_job = None
        self._draw_monitoring()

    def clear_monitoring(self) -> None:
        self.monitoring_service.clear()
        self._draw_monitoring()

    def _refresh_monitoring(self) -> None:
        """Redibuja mientras haya muestreo. Solo corre en el hilo principal."""
        self._draw_monitoring()
        if self.monitoring_service.is_running:
            self.monitoring_job = self.after(1000, self._refresh_monitoring)

    def _draw_monitoring(self) -> None:
        samples = self.monitoring_service.snapshot()
        read, write, sent, recv = series_for(samples)
        summary = self.monitoring_service.summary()
        disk_peak = max(summary.disk_read.peak, summary.disk_write.peak)
        net_peak = max(summary.net_sent.peak, summary.net_recv.peak)
        self.disk_chart.update_series((read, write), f"pico {format_rate(disk_peak)}")
        self.net_chart.update_series((sent, recv), f"pico {format_rate(net_peak)}")
        state = "Muestreando" if self.monitoring_service.is_running else "Detenido"
        self.monitoring_status.configure(
            text=f"{state} · {len(samples)}/{self.monitoring_service.capacity} muestras · 1 s"
        )

    def _on_close(self) -> None:
        """Detiene el muestreo antes de cerrar para no dejar el hilo colgado."""
        self.monitoring_service.stop()
        self.destroy()
```

En `select_component`, mostrar u ocultar el panel según el apartado:

```python
        if component is ComponentKind.IO:
            self.monitoring_panel.grid()
        else:
            self.monitoring_panel.grid_remove()
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ui_contract.py -v`
Expected: PASS

- [ ] **Step 5: Comprobar la aplicación de verdad**

Run: `.venv\Scripts\python.exe -m hardware_admin.main`

Verificar a mano: el apartado 11 muestra el panel y los demás no; **Iniciar** dibuja ambas curvas al cabo de unos segundos; **Detener** congela lo capturado; **Limpiar** lo vacía; cerrar la ventana no deja el proceso vivo. Copiar un archivo grande mientras corre para que el gráfico de disco se mueva de verdad.

- [ ] **Step 6: Gates y commit**

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy
git add tests/test_ui_contract.py src/hardware_admin/ui/main_window.py
git commit -m "feat(ui): panel de monitorizacion en vivo con graficos de disco y red"
```

---

### Task 7: Registrar el estado real de la fase 4

**Files:**
- Modify: `BUILD_PLAN.md`

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: nada de código.

- [ ] **Step 1: Actualizar la tabla de fases**

En la fila de la fase 4, dejar constancia de que la rebanada 4A (monitorización y gráfico de E/S) está completa, y de que 4B (gráficos de CPU, RAM, discos y red), 4C (recomendaciones) y 4D (menú de 15 opciones y Salir) siguen pendientes.

No marcar la fase 4 entera como completada: hacerlo repetiría el error que ya se corrigió en las fases 1-3, cuando el documento afirmaba gates en verde que en realidad no se ejecutaban.

- [ ] **Step 2: Commit**

```bash
git add BUILD_PLAN.md
git commit -m "docs: registrar la rebanada 4A completada y lo que sigue pendiente"
```
