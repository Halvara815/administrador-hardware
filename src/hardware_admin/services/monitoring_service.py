"""Muestreo periodico acotado de E/S con arranque y parada explicitos."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import psutil

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
