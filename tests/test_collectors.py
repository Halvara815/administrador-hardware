from unittest import TestCase

from hardware_admin.collectors.core import (
    CpuCollector,
    MemoryCollector,
    build_default_collectors,
    format_bytes,
)
from hardware_admin.domain.models import ComponentKind, ComponentResult
from hardware_admin.infrastructure.powershell import CommandResult, PowerShellQuery
from hardware_admin.ui.main_window import _format_value


class _FakeRunner:
    """Runner que responde una lista vacia: aisla la prueba de Windows."""

    def run(self, query: PowerShellQuery) -> CommandResult:
        return CommandResult(query=query, output="[]", exit_code=0)


class CollectorCompositionTests(TestCase):
    def test_all_diagnostic_areas_are_composed_once(self) -> None:
        components = [collector.component for collector in build_default_collectors()]

        self.assertEqual(len(components), 11)
        self.assertEqual(set(components), set(ComponentKind))

    def test_byte_formatter_uses_human_readable_units(self) -> None:
        self.assertEqual(format_bytes(1024), "1.0 KB")
        self.assertEqual(format_bytes(None), "No disponible")


def _details_text(result: ComponentResult) -> str:
    """Texto de la ficha tal y como lo compone la ventana principal."""
    parts: list[str] = []
    for key, value in result.facts.items():
        if str(key).startswith("_"):
            continue
        parts.append(f"{key}:")
        parts.append(_format_value(value, "  "))
    return "\n".join(parts)


class NumericSeriesTests(TestCase):
    """Los graficos necesitan numeros; la matriz y el reporte siguen leyendo texto."""

    def test_cpu_publishes_totals_and_per_core_without_touching_the_text(self) -> None:
        result = CpuCollector(_FakeRunner()).collect()

        self.assertIsInstance(result.facts["_uso"], float)
        nucleos = result.facts["_nucleos"]
        self.assertIsInstance(nucleos, list)
        self.assertGreater(len(nucleos), 0)
        for value in nucleos:
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 100.0)
        # El texto que consumen la matriz y el reporte no cambia de forma.
        self.assertTrue(str(result.facts["Uso"]).endswith("%"))

    def test_memory_publishes_bytes_alongside_the_formatted_text(self) -> None:
        result = MemoryCollector().collect()

        memoria = result.facts["_memoria"]
        self.assertEqual(
            set(memoria), {"usada", "disponible", "total"}
        )
        self.assertGreater(memoria["total"], 0)
        self.assertLessEqual(memoria["usada"], memoria["total"])
        self.assertTrue(str(result.facts["Porcentaje de uso"]).endswith("%"))

    def test_chart_series_never_reach_the_details_panel(self) -> None:
        """Las claves de grafico no son texto: la ficha no debe mostrarlas.

        Los conteos de nucleos si son numericos y si deben verse, asi que la
        regla no es "todo numero lleva guion bajo", sino que lo llevan las
        series que existen unicamente para dibujar.
        """
        result = CpuCollector(_FakeRunner()).collect()
        rendered = _details_text(result)

        self.assertIn("Procesadores lógicos", rendered)
        for key in result.facts:
            if str(key).startswith("_"):
                self.assertNotIn(str(key), rendered)
