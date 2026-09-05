from datetime import UTC, datetime
from unittest import TestCase

from hardware_admin.domain.models import ComponentKind
from hardware_admin.services.monitoring_service import Sample
from hardware_admin.ui import theme
from hardware_admin.ui.main_window import (
    MONITORING_DISK_SPECS,
    MONITORING_NET_SPECS,
    NAV_ITEMS,
    PREFERRED_SIZE,
    SECTION_NAMES,
    adapter_bars,
    core_bars,
    fit_window,
    series_for,
    volume_bars,
)


class UiContractTests(TestCase):
    def test_navigation_contains_the_fifteen_options_and_exit(self) -> None:
        """El enunciado pide 15 apartados mas Salir, en ese orden."""
        labels = [entry.label for entry in NAV_ITEMS]

        self.assertEqual(len(NAV_ITEMS), 16)
        self.assertEqual(labels[0], "1. Diagnóstico general")
        self.assertEqual(labels[10], "11. Conectividad")
        self.assertEqual(labels[11], "12. Monitorización")
        self.assertEqual(labels[12], "13. Recomendaciones")
        self.assertEqual(labels[13], "14. Generar reporte")
        self.assertEqual(labels[14], "15. Exportar diagnóstico")
        self.assertEqual(labels[15], "0. Salir")

    def test_every_component_still_has_its_own_section(self) -> None:
        """Ningun apartado de componente se pierde al reordenar el menu."""
        components = [entry.component for entry in NAV_ITEMS if entry.component is not None]

        self.assertEqual(set(components), set(ComponentKind))
        self.assertEqual(len(components), len(set(components)))

    def test_entries_without_component_declare_an_action(self) -> None:
        """Conectividad, Recomendaciones, Reporte, Exportar y Salir no son componentes."""
        actions = [entry.action for entry in NAV_ITEMS if entry.component is None]

        self.assertEqual(
            actions,
            ["connectivity", "recommendations", "report", "export", "exit"],
        )

    def test_no_entry_declares_both_a_component_and_an_action(self) -> None:
        for entry in NAV_ITEMS:
            self.assertFalse(
                entry.component is not None and entry.action is not None,
                f"{entry.label}: no puede ser componente y acción a la vez",
            )
            self.assertTrue(
                entry.component is not None or entry.action is not None,
                f"{entry.label}: sin destino",
            )

    def test_every_component_has_a_short_section_name(self) -> None:
        for component in ComponentKind:
            self.assertIn(component, SECTION_NAMES)


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


class WindowFitTests(TestCase):
    """Requisito no funcional: 1366x768 con escalado 100 %, 125 % y 150 %."""

    SCREEN = (1366, 768)

    def test_at_100_percent_the_preferred_size_is_capped_to_the_screen(self) -> None:
        geometria, minima = fit_window(*self.SCREEN, scaling=1.0)

        self.assertLessEqual(geometria[0], self.SCREEN[0])
        self.assertLessEqual(geometria[1], self.SCREEN[1])
        self.assertLessEqual(minima[0], geometria[0])
        self.assertLessEqual(minima[1], geometria[1])

    def test_the_window_fits_the_target_screen_at_every_required_scaling(self) -> None:
        """En pixeles fisicos la ventana nunca puede exceder la pantalla."""
        for escalado in (1.0, 1.25, 1.5):
            with self.subTest(escalado=escalado):
                geometria, minima = fit_window(*self.SCREEN, scaling=escalado)

                self.assertLessEqual(geometria[0] * escalado, self.SCREEN[0])
                self.assertLessEqual(geometria[1] * escalado, self.SCREEN[1])
                # Y sobre todo: el usuario debe poder encogerla hasta que quepa.
                self.assertLessEqual(minima[0] * escalado, self.SCREEN[0])
                self.assertLessEqual(minima[1] * escalado, self.SCREEN[1])

    def test_a_large_screen_keeps_the_preferred_size(self) -> None:
        """En una pantalla amplia no se recorta nada."""
        geometria, _ = fit_window(2560, 1440, scaling=1.0)

        self.assertEqual(geometria, PREFERRED_SIZE)

    def test_the_minimum_never_exceeds_the_geometry(self) -> None:
        """Un minimo mayor que la ventana la haria inmanejable."""
        for ancho, alto, escalado in ((1366, 768, 1.5), (1024, 600, 1.0), (3840, 2160, 2.0)):
            with self.subTest(pantalla=(ancho, alto), escalado=escalado):
                geometria, minima = fit_window(ancho, alto, scaling=escalado)

                self.assertLessEqual(minima[0], geometria[0])
                self.assertLessEqual(minima[1], geometria[1])

    def test_an_absurd_screen_still_yields_a_usable_window(self) -> None:
        """Ante datos improbables se devuelve algo manejable, no cero."""
        geometria, minima = fit_window(0, 0, scaling=1.0)

        self.assertGreater(minima[0], 0)
        self.assertGreater(minima[1], 0)
        self.assertLessEqual(minima[0], geometria[0])
