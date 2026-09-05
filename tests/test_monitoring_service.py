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
