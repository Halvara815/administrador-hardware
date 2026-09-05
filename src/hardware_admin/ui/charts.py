"""Widgets de grafico sobre tkinter.Canvas, sin dependencias externas.

La geometria se calcula en funciones puras para poder comprobarla sin abrir
ventana, que es como estan escritas las pruebas de interfaz del proyecto.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import customtkinter as ctk

from hardware_admin.ui import theme


def scale_series(
    values: Sequence[float],
    width: int,
    height: int,
    maximum: float | None = None,
) -> list[tuple[float, float]]:
    """Convierte valores en coordenadas de lienzo.

    El origen es la esquina superior izquierda, como en tkinter.Canvas: el
    valor mayor queda arriba (y=0) y el cero abajo (y=height). El valor mas
    reciente se dibuja a la derecha.
    """
    if not values:
        return []

    top = maximum if maximum is not None else max(values)
    if top <= 0:
        # Serie plana en cero: sin escala util, todo descansa en la base.
        return [(_x_for(index, len(values), width), float(height)) for index in range(len(values))]

    points: list[tuple[float, float]] = []
    for index, value in enumerate(values):
        ratio = min(max(value / top, 0.0), 1.0)
        points.append((_x_for(index, len(values), width), height - ratio * height))
    return points


def _x_for(index: int, count: int, width: int) -> float:
    if count <= 1:
        return float(width)
    return index * (width / (count - 1))


#: Barrido del medidor en grados: arco abierto por abajo, de 225 a -45.
GAUGE_START = 225.0
GAUGE_SWEEP = 270.0


def gauge_extent(percent: float) -> float:
    """Grados que ocupa el arco de un medidor para un porcentaje dado.

    Negativo porque tkinter mide el barrido en sentido antihorario. Un valor
    fuera de 0-100 se recorta: un porcentaje imposible no puede desbordar el
    dibujo.
    """
    ratio = min(max(percent, 0.0), 100.0) / 100.0
    return -GAUGE_SWEEP * ratio


def bar_widths(ratios: Sequence[float], width: int) -> list[float]:
    """Ancho en pixeles de cada barra, recortado al carril disponible."""
    return [min(max(ratio, 0.0), 1.0) * width for ratio in ratios]


def format_rate(bps: float) -> str:
    """Formatea una tasa en unidades legibles por segundo."""
    amount = max(bps, 0.0)
    for unit in ("B", "KB", "MB", "GB"):
        if amount < 1024 or unit == "GB":
            return f"{amount:.1f} {unit}/s"
        amount /= 1024
    return f"{amount:.1f} GB/s"


@dataclass(frozen=True, slots=True)
class SeriesSpec:
    """Nombre y color de una serie dentro de un grafico."""

    label: str
    color: str


class TimeSeriesChart(ctk.CTkFrame):
    """Grafico de lineas con su propio eje autoescalado.

    Cada grafico escala de forma independiente: disco y red difieren en
    ordenes de magnitud y un eje compartido dejaria la red pegada al cero.
    """

    def __init__(
        self,
        master: Any,
        title: str,
        specs: Sequence[SeriesSpec],
        height: int = 120,
    ) -> None:
        super().__init__(
            master,
            fg_color=theme.SURFACE,
            corner_radius=10,
            border_width=1,
            border_color=theme.BORDER,
        )
        self.specs = tuple(specs)
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            header,
            text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=theme.TEXT,
        ).grid(row=0, column=0, sticky="w")
        self.peak_label = ctk.CTkLabel(
            header, text="", font=ctk.CTkFont(size=11), text_color=theme.MUTED
        )
        self.peak_label.grid(row=0, column=1, sticky="e")

        self.canvas = tk.Canvas(
            self, height=height, background=theme.TERMINAL, highlightthickness=0, bd=0
        )
        self.canvas.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))

        legend = ctk.CTkFrame(self, fg_color="transparent")
        legend.grid(row=2, column=0, sticky="w", padx=12, pady=(0, 10))
        for column, spec in enumerate(self.specs):
            ctk.CTkLabel(
                legend,
                text=f"— {spec.label}",
                font=ctk.CTkFont(size=11),
                text_color=spec.color,
            ).grid(row=0, column=column, padx=(0 if column == 0 else 14, 0))

    def update_series(self, series: Sequence[Sequence[float]], peak_label: str) -> None:
        """Redibuja el grafico. Se llama solo desde el hilo principal."""
        self.peak_label.configure(text=peak_label)
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)

        # Escala comun a las series del mismo grafico para que sean comparables.
        top = max((max(values) for values in series if values), default=0.0)
        for spec, values in zip(self.specs, series):
            points = scale_series(values, width, height, maximum=top or None)
            if len(points) < 2:
                continue
            flat: list[float] = []
            for x, y in points:
                flat.extend((x, y))
            self.canvas.create_line(*flat, fill=spec.color, width=2)


class _ChartFrame(ctk.CTkFrame):
    """Marco comun de los graficos: titulo a la izquierda, dato a la derecha."""

    def __init__(self, master: Any, title: str) -> None:
        super().__init__(
            master,
            fg_color=theme.SURFACE,
            corner_radius=10,
            border_width=1,
            border_color=theme.BORDER,
        )
        self.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            header,
            text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=theme.TEXT,
        ).grid(row=0, column=0, sticky="w")
        self.value_label = ctk.CTkLabel(
            header, text="", font=ctk.CTkFont(size=11), text_color=theme.MUTED
        )
        self.value_label.grid(row=0, column=1, sticky="e")


class GaugeChart(_ChartFrame):
    """Medidor circular de un porcentaje unico."""

    def __init__(self, master: Any, title: str, size: int = 150) -> None:
        super().__init__(master, title)
        self.size = size
        self.canvas = tk.Canvas(
            self, width=size, height=size, background=theme.TERMINAL,
            highlightthickness=0, bd=0,
        )
        self.canvas.grid(row=1, column=0, padx=12, pady=(0, 12))

    def update_value(self, percent: float, label: str, color: str) -> None:
        """Redibuja el medidor. Solo desde el hilo principal."""
        self.value_label.configure(text=label)
        self.canvas.delete("all")
        margin, width = 16, 14
        box = (margin, margin, self.size - margin, self.size - margin)
        self.canvas.create_arc(
            *box, start=GAUGE_START, extent=-GAUGE_SWEEP, style="arc",
            outline=theme.BORDER, width=width,
        )
        extent = gauge_extent(percent)
        if extent != 0.0:
            self.canvas.create_arc(
                *box, start=GAUGE_START, extent=extent, style="arc",
                outline=color, width=width,
            )
        self.canvas.create_text(
            self.size / 2, self.size / 2, text=f"{percent:.0f}%",
            fill=theme.TEXT, font=("Segoe UI", 20, "bold"),
        )


@dataclass(frozen=True, slots=True)
class Bar:
    """Una barra: etiqueta, proporcion ocupada (0-1), valor y color."""

    label: str
    ratio: float
    value: str
    color: str


class BarListChart(_ChartFrame):
    """Lista de barras horizontales: nucleos, volumenes o adaptadores."""

    ROW_HEIGHT = 26

    def __init__(self, master: Any, title: str) -> None:
        super().__init__(master, title)
        self.canvas = tk.Canvas(
            self, height=self.ROW_HEIGHT, background=theme.TERMINAL,
            highlightthickness=0, bd=0,
        )
        self.canvas.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))

    def update_bars(self, bars: Sequence[Bar], value_label: str = "") -> None:
        """Redibuja la lista. Una lista vacia deja el grafico en blanco."""
        self.value_label.configure(text=value_label)
        self.canvas.delete("all")
        if not bars:
            self.canvas.configure(height=self.ROW_HEIGHT)
            self.canvas.create_text(
                10, self.ROW_HEIGHT / 2, anchor="w", text="Sin datos disponibles",
                fill=theme.MUTED, font=("Segoe UI", 10),
            )
            return

        self.canvas.configure(height=self.ROW_HEIGHT * len(bars))
        total_width = max(self.canvas.winfo_width(), 1)
        label_width, value_width = 120, 110
        track = max(total_width - label_width - value_width, 1)
        widths = bar_widths([bar.ratio for bar in bars], track)

        for index, (bar, filled) in enumerate(zip(bars, widths)):
            top = index * self.ROW_HEIGHT + 6
            bottom = top + self.ROW_HEIGHT - 14
            self.canvas.create_text(
                0, (top + bottom) / 2, anchor="w", text=bar.label,
                fill=theme.MUTED, font=("Segoe UI", 10),
            )
            self.canvas.create_rectangle(
                label_width, top, label_width + track, bottom,
                fill=theme.SURFACE_ALT, outline="",
            )
            if filled > 0:
                self.canvas.create_rectangle(
                    label_width, top, label_width + filled, bottom,
                    fill=bar.color, outline="",
                )
            self.canvas.create_text(
                total_width, (top + bottom) / 2, anchor="e", text=bar.value,
                fill=theme.TEXT, font=("Segoe UI", 10),
            )
