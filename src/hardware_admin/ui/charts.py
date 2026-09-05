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
