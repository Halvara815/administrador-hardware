"""Pruebas del servicio de monitorizacion: buffer acotado, arranque y parada."""

import time
from datetime import UTC, datetime
from unittest import TestCase
from unittest.mock import MagicMock, patch

from hardware_admin.services.monitoring_service import (
    MonitoringService,
    PsutilRateSampler,
    Sample,
)


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
