from unittest import TestCase
from unittest.mock import patch

from hardware_admin.collectors.core import (
    CpuCollector,
    MemoryCollector,
    SystemCollector,
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

    @patch("psutil.virtual_memory")
    @patch("psutil.swap_memory")
    def test_memory_exposes_firmware_maximum_and_theoretical_margin(self, mock_swap, mock_vm) -> None:
        """El máximo SMBIOS se muestra sin confundirlo con una compatibilidad de módulo."""
        vm = type("Memory", (), {"total": 16 * 1024**3, "available": 8 * 1024**3, "used": 8 * 1024**3, "percent": 50.0})()
        mock_vm.return_value = vm
        mock_swap.return_value = type("Swap", (), {"used": 0})()

        class MemoryRunner:
            def run(self, query: PowerShellQuery) -> CommandResult:
                if query is PowerShellQuery.PHYSICAL_MEMORY_MODULES:
                    return CommandResult(
                        query,
                        '[{"DeviceLocator":"DIMM 0","Capacity":17179869184}]',
                        0,
                    )
                if query is PowerShellQuery.PHYSICAL_MEMORY_ARRAY:
                    return CommandResult(query, '[{"MaxCapacityEx":67108864,"MemoryDevices":2}]', 0)
                return CommandResult(query, "[]", 0)

        result = MemoryCollector(MemoryRunner()).collect()

        self.assertEqual(result.facts["Máximo RAM reportado por firmware"], "64.0 GB")
        self.assertEqual(result.facts["Margen teórico de ampliación RAM"], "48.0 GB")
        self.assertEqual(result.facts["Ranuras RAM reportadas por firmware"], 2)

    def test_system_slots_collector_handles_rows_and_empty(self) -> None:
        """SystemCollector estructura las ranuras Win32_SystemSlot o degrada limpiamente."""
        class SlotsRunner:
            def __init__(self, output: str) -> None:
                self.output = output

            def run(self, query: PowerShellQuery) -> CommandResult:
                if query is PowerShellQuery.SYSTEM_SLOTS:
                    return CommandResult(query, self.output, 0)
                return CommandResult(query, "[]", 0)

        # Caso con filas de ranura
        rows_json = '[{"SlotDesignation":"M.2 Slot 1","CurrentUsage":3,"Status":"OK","MaxDataWidth":4,"Description":"M.2 PCIe"}]'
        res_with_slots = SystemCollector(SlotsRunner(rows_json)).collect()
        slots_val = res_with_slots.facts["Ranuras del sistema (Win32_SystemSlot)"]
        self.assertIsInstance(slots_val, list)
        self.assertEqual(len(slots_val), 1)
        self.assertEqual(slots_val[0]["Ranura"], "M.2 Slot 1")

        # Caso vacío: degrada a mensaje honesto
        res_empty = SystemCollector(SlotsRunner("[]")).collect()
        self.assertEqual(
            res_empty.facts["Ranuras del sistema (Win32_SystemSlot)"],
            "No reportadas por el firmware o incompletas en este equipo",
        )

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
