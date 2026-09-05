from datetime import UTC, datetime
from unittest import TestCase

from hardware_admin.domain.models import ComponentKind
from hardware_admin.services.monitoring_service import Sample
from hardware_admin.ui import theme
from hardware_admin.ui.main_window import (
    MONITORING_DISK_SPECS,
    MONITORING_NET_SPECS,
    NAV_ITEMS,
    adapter_bars,
    core_bars,
    series_for,
    volume_bars,
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


class SectionChartContractTests(TestCase):
    """Conversion de facts a barras: dato ausente no revienta, se dibuja vacio."""

    def test_core_bars_are_built_from_the_numeric_series(self) -> None:
        bars = core_bars({"_nucleos": [10.0, 95.0]})

        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0].label, "Núcleo 1")
        self.assertAlmostEqual(bars[0].ratio, 0.10)
        self.assertEqual(bars[1].value, "95.0%")

    def test_core_bars_colour_by_the_official_thresholds(self) -> None:
        """El color sigue la regla 70/90 de la fase 1, no un criterio nuevo."""
        bars = core_bars({"_nucleos": [10.0, 75.0, 95.0]})

        self.assertEqual(bars[0].color, theme.GREEN)
        self.assertEqual(bars[1].color, theme.YELLOW)
        self.assertEqual(bars[2].color, theme.RED)

    def test_volume_bars_use_the_used_fraction(self) -> None:
        bars = volume_bars(
            {"_volumenes": [{"unidad": "C:\\", "usado": 25.0, "libre": 75.0, "porcentaje": 25.0}]}
        )

        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].label, "C:\\")
        self.assertAlmostEqual(bars[0].ratio, 0.25)

    def test_adapter_bars_scale_against_the_fastest_link(self) -> None:
        bars = adapter_bars(
            {
                "_adaptadores": [
                    {"nombre": "Ethernet", "mbps": 1000.0, "conectado": True},
                    {"nombre": "Wi-Fi", "mbps": 250.0, "conectado": False},
                ]
            }
        )

        self.assertAlmostEqual(bars[0].ratio, 1.0)
        self.assertAlmostEqual(bars[1].ratio, 0.25)
        self.assertEqual(bars[1].color, theme.MUTED)

    def test_missing_series_yield_no_bars_instead_of_raising(self) -> None:
        """Si el recolector fallo no hay serie: se dibuja vacio, no se revienta."""
        self.assertEqual(core_bars({}), [])
        self.assertEqual(volume_bars({}), [])
        self.assertEqual(adapter_bars({}), [])
        self.assertEqual(core_bars({"_nucleos": "no disponible"}), [])
