"""Pruebas de la geometria de los graficos, sin abrir ninguna ventana."""

from unittest import TestCase

from hardware_admin.ui.charts import format_rate, scale_series


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
