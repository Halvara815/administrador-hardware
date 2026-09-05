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
