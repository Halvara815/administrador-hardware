from datetime import UTC, datetime
from unittest import TestCase

from hardware_admin.domain.models import ComponentKind
from hardware_admin.services.monitoring_service import Sample
from hardware_admin.ui.main_window import (
    MONITORING_DISK_SPECS,
    MONITORING_NET_SPECS,
    NAV_ITEMS,
    series_for,
)


class UiContractTests(TestCase):
    def test_navigation_contains_the_twelve_assignment_options(self) -> None:
        labels = [label for _, label, _ in NAV_ITEMS]
        components = [component for _, _, component in NAV_ITEMS if component is not None]

        self.assertEqual(len(labels), 12)
        self.assertEqual(set(components), set(ComponentKind))
        self.assertEqual(labels[0], "1. Información del sistema")
        self.assertEqual(labels[-1], "12. Generar reporte")


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
