"""Pruebas de la geometria de los graficos, sin abrir ninguna ventana."""

from unittest import TestCase

from hardware_admin.ui.charts import (
    GAUGE_SWEEP,
    bar_widths,
    elide_text,
    format_rate,
    gauge_extent,
    scale_series,
)


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


class FormatRateTests(TestCase):
    def test_rates_use_human_readable_units_per_second(self) -> None:
        self.assertEqual(format_rate(0.0), "0.0 B/s")
        self.assertEqual(format_rate(1536.0), "1.5 KB/s")
        self.assertEqual(format_rate(1024.0 * 1024.0), "1.0 MB/s")

    def test_a_negative_rate_is_reported_as_zero(self) -> None:
        """Una tasa negativa no existe: se reporta como cero, no con signo."""
        self.assertEqual(format_rate(-5.0), "0.0 B/s")


class GaugeExtentTests(TestCase):
    def test_zero_percent_draws_no_arc(self) -> None:
        self.assertEqual(gauge_extent(0.0), 0.0)

    def test_full_percent_draws_the_whole_sweep(self) -> None:
        self.assertEqual(gauge_extent(100.0), -GAUGE_SWEEP)

    def test_half_percent_draws_half_the_sweep(self) -> None:
        self.assertAlmostEqual(gauge_extent(50.0), -GAUGE_SWEEP / 2)

    def test_out_of_range_values_stay_inside_the_arc(self) -> None:
        """Un porcentaje imposible no debe desbordar el dibujo."""
        self.assertEqual(gauge_extent(-10.0), 0.0)
        self.assertEqual(gauge_extent(140.0), -GAUGE_SWEEP)


class BarWidthsTests(TestCase):
    def test_no_bars_produce_no_widths(self) -> None:
        self.assertEqual(bar_widths([], 200), [])

    def test_ratios_map_to_proportional_widths(self) -> None:
        self.assertEqual(bar_widths([0.0, 0.5, 1.0], 200), [0.0, 100.0, 200.0])

    def test_ratios_are_clamped_to_the_track(self) -> None:
        """Una proporcion fuera de rango no puede pintar fuera de la barra."""
        self.assertEqual(bar_widths([-0.5, 1.4], 200), [0.0, 200.0])


class ElideTextTests(TestCase):
    """La etiqueta no puede invadir la barra: se recorta con puntos suspensivos."""

    @staticmethod
    def _measure(text: str) -> int:
        """Fuente falsa de 10 px por carácter: hace la prueba determinista."""
        return len(text) * 10

    def test_a_short_label_is_left_untouched(self) -> None:
        self.assertEqual(elide_text("Ethernet", 200, self._measure), "Ethernet")

    def test_a_long_label_is_cut_with_an_ellipsis(self) -> None:
        resultado = elide_text("vEthernet (Default Switch)", 120, self._measure)

        self.assertTrue(resultado.endswith("…"))
        self.assertLessEqual(self._measure(resultado), 120)
        self.assertTrue("vEthernet".startswith(resultado[:5]))

    def test_the_result_never_exceeds_the_available_width(self) -> None:
        for ancho in (30, 60, 120, 250):
            with self.subTest(ancho=ancho):
                resultado = elide_text("Loopback Pseudo-Interface 1", ancho, self._measure)

                self.assertLessEqual(self._measure(resultado), ancho)

    def test_an_impossibly_narrow_column_yields_no_text_instead_of_garbage(self) -> None:
        self.assertEqual(elide_text("Ethernet", 5, self._measure), "")

    def test_an_empty_label_stays_empty(self) -> None:
        self.assertEqual(elide_text("", 100, self._measure), "")
