"""Regresion: los graficos deben dibujarse bien la primera vez que se muestran.

Estas pruebas necesitan una ventana real porque el fallo que cubren solo
aparece con el ciclo de disposicion de Tk: al mostrar un panel por primera vez,
`winfo_width()` devuelve 1 hasta que Tk lo coloca, y el dibujo hecho con ese
ancho quedaba congelado en un pixel.
"""

from unittest import TestCase, skipUnless

from hardware_admin.ui.charts import Bar, BarListChart, SeriesSpec, TimeSeriesChart


def _tk_available() -> bool:
    import tkinter

    # Sin sesión gráfica, Tk falla al abrir el display; se omiten estas pruebas.
    try:
        root = tkinter.Tk()
        root.destroy()
    except tkinter.TclError:
        return False
    return True


TK = _tk_available()


@skipUnless(TK, "Requiere una sesión gráfica para crear ventanas Tk")
class BarChartRenderTests(TestCase):
    def setUp(self) -> None:
        import customtkinter as ctk

        self.root = ctk.CTk()
        self.root.geometry("900x600")
        self.chart = BarListChart(self.root, "OCUPACIÓN")
        self.chart.pack(fill="both", expand=True)

    def tearDown(self) -> None:
        self.root.destroy()

    def _bars(self) -> list[Bar]:
        return [
            Bar("C:\\", 0.5, "media", "#3FB950"),
            Bar("D:\\", 1.0, "llena", "#F85149"),
        ]

    def test_bars_drawn_before_layout_are_redrawn_at_the_real_width(self) -> None:
        """El caso del informe: se dibuja antes de que Tk conozca el ancho."""
        self.chart.update_bars(self._bars())
        # Sin haber pasado por el ciclo de disposicion, el ancho aun es 1.
        self.root.update_idletasks()
        self.root.update()

        anchos = [
            self.chart.canvas.coords(item)[2] - self.chart.canvas.coords(item)[0]
            for item in self.chart.canvas.find_all()
            if self.chart.canvas.type(item) == "rectangle"
        ]
        self.assertTrue(anchos, "no se dibujó ninguna barra")
        self.assertGreater(
            max(anchos), 100, "las barras siguen midiendo un hilo: no se redibujaron"
        )

    def test_a_resize_rescales_the_bars(self) -> None:
        """Al cambiar el tamaño de la ventana las barras deben reescalarse."""
        self.chart.update_bars(self._bars())
        self.root.update_idletasks()
        self.root.update()
        antes = max(
            self.chart.canvas.coords(item)[2]
            for item in self.chart.canvas.find_all()
            if self.chart.canvas.type(item) == "rectangle"
        )

        self.root.geometry("1400x600")
        self.root.update_idletasks()
        self.root.update()
        despues = max(
            self.chart.canvas.coords(item)[2]
            for item in self.chart.canvas.find_all()
            if self.chart.canvas.type(item) == "rectangle"
        )

        self.assertGreater(despues, antes)

    def test_an_empty_list_keeps_the_placeholder_after_layout(self) -> None:
        self.chart.update_bars([])
        self.root.update_idletasks()
        self.root.update()

        textos = [
            self.chart.canvas.itemcget(item, "text")
            for item in self.chart.canvas.find_all()
            if self.chart.canvas.type(item) == "text"
        ]
        self.assertIn("Sin datos disponibles", textos)


@skipUnless(TK, "Requiere una sesión gráfica para crear ventanas Tk")
class TimeSeriesRenderTests(TestCase):
    def setUp(self) -> None:
        import customtkinter as ctk

        self.root = ctk.CTk()
        self.root.geometry("900x600")
        self.chart = TimeSeriesChart(
            self.root, "DISCO", (SeriesSpec("Lectura", "#4A9EFF"),)
        )
        self.chart.pack(fill="both", expand=True)

    def tearDown(self) -> None:
        self.root.destroy()

    def test_the_line_spans_the_real_width_after_layout(self) -> None:
        self.chart.update_series(([1.0, 5.0, 3.0, 8.0],), "pico 8 B/s")
        self.root.update_idletasks()
        self.root.update()

        lineas = [
            self.chart.canvas.coords(item)
            for item in self.chart.canvas.find_all()
            if self.chart.canvas.type(item) == "line"
        ]
        self.assertTrue(lineas, "no se dibujó ninguna serie")
        self.assertGreater(max(coord[-2] for coord in lineas), 100)


@skipUnless(TK, "Requiere una sesión gráfica para crear ventanas Tk")
class ActionSectionTests(TestCase):
    """Regresion: los apartados que no son componentes deben responder al clic.

    Conectividad, Recomendaciones, Generar reporte, Exportar y Salir no
    corresponden a ningun ComponentKind. Al pulsarlos no se iluminaba ningun
    boton y el area principal seguia mostrando la matriz, asi que parecia que
    el clic no hacia nada.
    """

    def setUp(self) -> None:
        from hardware_admin.app_factory import build_scan_service
        from hardware_admin.ui.main_window import HardwareAdminApp

        self.app = HardwareAdminApp(build_scan_service())
        self.app.update_idletasks()
        self.app.update()

    def tearDown(self) -> None:
        self.app.monitoring_service.stop()
        self.app.destroy()

    def test_an_action_section_highlights_its_own_button(self) -> None:
        from hardware_admin.ui import theme

        self.app.run_action("connectivity")
        self.app.update()

        activo = self.app.nav_buttons["connectivity"]
        self.assertEqual(activo.cget("fg_color"), theme.ACCENT)

    def test_choosing_an_action_clears_the_previous_highlight(self) -> None:
        from hardware_admin.domain.models import ComponentKind
        from hardware_admin.ui import theme

        self.app.select_component(ComponentKind.CPU)
        self.app.update()
        self.app.run_action("recommendations")
        self.app.update()

        self.assertEqual(
            self.app.nav_buttons[ComponentKind.CPU.value].cget("fg_color"),
            theme.SURFACE_ALT,
        )

    def test_an_action_replaces_the_matrix_with_its_own_view(self) -> None:
        """El cambio debe verse en el area principal, no solo en el titulo."""
        self.app.run_action("connectivity")
        self.app.update()

        self.assertTrue(self.app.action_view.winfo_ismapped())
        self.assertFalse(self.app.workspace.winfo_ismapped())

    def test_returning_to_a_component_restores_the_matrix(self) -> None:
        from hardware_admin.domain.models import ComponentKind

        self.app.run_action("connectivity")
        self.app.update()
        self.app.select_component(ComponentKind.CPU)
        self.app.update()

        self.assertTrue(self.app.workspace.winfo_ismapped())
        self.assertFalse(self.app.action_view.winfo_ismapped())
