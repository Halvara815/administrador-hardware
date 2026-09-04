"""Iconos dibujados con Pillow.

Se dibujan en código en lugar de usar glifos de texto para que la interfaz se
vea igual en cualquier equipo: los símbolos Unicode dependen de qué fuentes
tenga instalado Windows y se degradan a cuadros vacíos con facilidad.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

from PIL import Image, ImageDraw

_SUPERSAMPLE = 4

Point = tuple[float, float]
IconPainter = Callable[[ImageDraw.ImageDraw, float, str, int], None]


def _line(
    draw: ImageDraw.ImageDraw, size: float, points: Sequence[Point], color: str, width: int
) -> None:
    draw.line([(x * size, y * size) for x, y in points], fill=color, width=width, joint="curve")


def _rect(
    draw: ImageDraw.ImageDraw,
    size: float,
    box: tuple[float, float, float, float],
    color: str,
    width: int,
    radius: float = 0.0,
) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(
        (x0 * size, y0 * size, x1 * size, y1 * size),
        radius=radius * size,
        outline=color,
        width=width,
    )


def _ellipse(
    draw: ImageDraw.ImageDraw,
    size: float,
    box: tuple[float, float, float, float],
    color: str,
    width: int,
) -> None:
    x0, y0, x1, y1 = box
    draw.ellipse((x0 * size, y0 * size, x1 * size, y1 * size), outline=color, width=width)


def _dot(draw: ImageDraw.ImageDraw, size: float, center: Point, radius: float, color: str) -> None:
    cx, cy = center
    draw.ellipse(
        (
            (cx - radius) * size,
            (cy - radius) * size,
            (cx + radius) * size,
            (cy + radius) * size,
        ),
        fill=color,
    )


def _paint_monitor(draw: ImageDraw.ImageDraw, size: float, color: str, width: int) -> None:
    _rect(draw, size, (0.08, 0.16, 0.92, 0.68), color, width, 0.08)
    _line(draw, size, ((0.50, 0.68), (0.50, 0.82)), color, width)
    _line(draw, size, ((0.30, 0.86), (0.70, 0.86)), color, width)


def _paint_chip(draw: ImageDraw.ImageDraw, size: float, color: str, width: int) -> None:
    _rect(draw, size, (0.22, 0.22, 0.78, 0.78), color, width, 0.08)
    _rect(draw, size, (0.37, 0.37, 0.63, 0.63), color, width, 0.03)
    pin = round(width * 1.3)
    for offset in (0.36, 0.64):
        _line(draw, size, ((offset, 0.09), (offset, 0.22)), color, pin)
        _line(draw, size, ((offset, 0.78), (offset, 0.91)), color, pin)
        _line(draw, size, ((0.09, offset), (0.22, offset)), color, pin)
        _line(draw, size, ((0.78, offset), (0.91, offset)), color, pin)


def _paint_ram(draw: ImageDraw.ImageDraw, size: float, color: str, width: int) -> None:
    _rect(draw, size, (0.06, 0.28, 0.94, 0.68), color, width, 0.05)
    for offset in (0.22, 0.36, 0.50, 0.64, 0.78):
        _line(draw, size, ((offset, 0.38), (offset, 0.58)), color, width)
    _line(draw, size, ((0.24, 0.68), (0.24, 0.80)), color, width)
    _line(draw, size, ((0.76, 0.68), (0.76, 0.80)), color, width)


def _paint_disk(draw: ImageDraw.ImageDraw, size: float, color: str, width: int) -> None:
    _rect(draw, size, (0.16, 0.12, 0.84, 0.88), color, width, 0.12)
    _ellipse(draw, size, (0.36, 0.42, 0.64, 0.70), color, width)
    _line(draw, size, ((0.36, 0.26), (0.64, 0.26)), color, width)


def _paint_globe(draw: ImageDraw.ImageDraw, size: float, color: str, width: int) -> None:
    _ellipse(draw, size, (0.10, 0.10, 0.90, 0.90), color, width)
    _ellipse(draw, size, (0.36, 0.10, 0.64, 0.90), color, width)
    _line(draw, size, ((0.11, 0.50), (0.89, 0.50)), color, width)
    _line(draw, size, ((0.21, 0.28), (0.79, 0.28)), color, width)
    _line(draw, size, ((0.21, 0.72), (0.79, 0.72)), color, width)


def _paint_usb(draw: ImageDraw.ImageDraw, size: float, color: str, width: int) -> None:
    _rect(draw, size, (0.40, 0.08, 0.60, 0.24), color, width, 0.02)
    _rect(draw, size, (0.28, 0.24, 0.72, 0.92), color, width, 0.08)
    _line(draw, size, ((0.40, 0.44), (0.60, 0.44)), color, width)
    _line(draw, size, ((0.40, 0.60), (0.60, 0.60)), color, width)


def _paint_card(draw: ImageDraw.ImageDraw, size: float, color: str, width: int) -> None:
    _rect(draw, size, (0.08, 0.22, 0.92, 0.68), color, width, 0.06)
    _line(draw, size, ((0.20, 0.36), (0.62, 0.36)), color, width)
    _line(draw, size, ((0.20, 0.52), (0.50, 0.52)), color, width)
    for offset in (0.26, 0.46, 0.66):
        _line(draw, size, ((offset, 0.68), (offset, 0.84)), color, width)


def _paint_gear(draw: ImageDraw.ImageDraw, size: float, color: str, width: int) -> None:
    _ellipse(draw, size, (0.22, 0.22, 0.78, 0.78), color, width)
    _ellipse(draw, size, (0.40, 0.40, 0.60, 0.60), color, width)
    # Dientes cortos y anchos: alargados se leen como un sol en lugar de un engranaje.
    for degrees in range(0, 360, 45):
        angle = math.radians(degrees)
        _line(
            draw,
            size,
            (
                (0.5 + 0.29 * math.cos(angle), 0.5 + 0.29 * math.sin(angle)),
                (0.5 + 0.40 * math.cos(angle), 0.5 + 0.40 * math.sin(angle)),
            ),
            color,
            round(width * 2.0),
        )


def _paint_alert(draw: ImageDraw.ImageDraw, size: float, color: str, width: int) -> None:
    _line(
        draw,
        size,
        ((0.50, 0.10), (0.94, 0.86), (0.06, 0.86), (0.50, 0.10)),
        color,
        width,
    )
    _line(draw, size, ((0.50, 0.38), (0.50, 0.62)), color, round(width * 1.2))
    _dot(draw, size, (0.50, 0.75), 0.065, color)


def _paint_pulse(draw: ImageDraw.ImageDraw, size: float, color: str, width: int) -> None:
    _rect(draw, size, (0.05, 0.14, 0.95, 0.86), color, width, 0.14)
    _line(
        draw,
        size,
        ((0.16, 0.56), (0.32, 0.56), (0.43, 0.24), (0.57, 0.78), (0.67, 0.56), (0.84, 0.56)),
        color,
        width,
    )


def _paint_document(draw: ImageDraw.ImageDraw, size: float, color: str, width: int) -> None:
    _rect(draw, size, (0.22, 0.08, 0.78, 0.92), color, width, 0.07)
    for offset in (0.30, 0.44, 0.58, 0.72):
        _line(draw, size, ((0.34, offset), (0.66, offset)), color, width)


def _paint_copy(draw: ImageDraw.ImageDraw, size: float, color: str, width: int) -> None:
    _rect(draw, size, (0.10, 0.10, 0.62, 0.62), color, width, 0.08)
    _rect(draw, size, (0.38, 0.38, 0.90, 0.90), color, width, 0.08)


def _paint_save(draw: ImageDraw.ImageDraw, size: float, color: str, width: int) -> None:
    _rect(draw, size, (0.10, 0.10, 0.90, 0.90), color, width, 0.08)
    _rect(draw, size, (0.32, 0.10, 0.68, 0.38), color, width)
    _rect(draw, size, (0.26, 0.56, 0.74, 0.90), color, width)


def _paint_check(draw: ImageDraw.ImageDraw, size: float, color: str, width: int) -> None:
    _ellipse(draw, size, (0.08, 0.08, 0.92, 0.92), color, width)
    _line(draw, size, ((0.29, 0.51), (0.44, 0.66), (0.72, 0.34)), color, width)


def _paint_info(draw: ImageDraw.ImageDraw, size: float, color: str, width: int) -> None:
    _ellipse(draw, size, (0.08, 0.08, 0.92, 0.92), color, width)
    _dot(draw, size, (0.50, 0.29), 0.055, color)
    _line(draw, size, ((0.50, 0.44), (0.50, 0.74)), color, width)


def _paint_refresh(draw: ImageDraw.ImageDraw, size: float, color: str, width: int) -> None:
    radius = 0.34
    draw.arc(
        (
            (0.5 - radius) * size,
            (0.5 - radius) * size,
            (0.5 + radius) * size,
            (0.5 + radius) * size,
        ),
        start=25,
        end=330,
        fill=color,
        width=width,
    )
    # Punta de flecha apoyada en el extremo del arco, orientada por su tangente.
    angle = math.radians(330)
    end_x, end_y = 0.5 + radius * math.cos(angle), 0.5 + radius * math.sin(angle)
    tangent_x, tangent_y = -math.sin(angle), math.cos(angle)
    normal_x, normal_y = math.cos(angle), math.sin(angle)
    head = 0.20
    draw.polygon(
        [
            ((end_x + tangent_x * head) * size, (end_y + tangent_y * head) * size),
            ((end_x - normal_x * head * 0.8) * size, (end_y - normal_y * head * 0.8) * size),
            ((end_x + normal_x * head * 0.8) * size, (end_y + normal_y * head * 0.8) * size),
        ],
        fill=color,
    )


def _paint_expand(draw: ImageDraw.ImageDraw, size: float, color: str, width: int) -> None:
    """Cuatro esquinas abiertas hacia fuera: la convención de «ver en grande»."""
    arm = 0.28
    corners = ((0.12, 0.12, 1.0, 1.0), (0.88, 0.12, -1.0, 1.0),
               (0.12, 0.88, 1.0, -1.0), (0.88, 0.88, -1.0, -1.0))
    for x, y, x_way, y_way in corners:
        _line(draw, size, ((x, y + y_way * arm), (x, y), (x + x_way * arm, y)), color, width)


def _paint_collapse(draw: ImageDraw.ImageDraw, size: float, color: str, width: int) -> None:
    arm = 0.28
    corners = ((0.42, 0.42, -1.0, -1.0), (0.58, 0.42, 1.0, -1.0),
               (0.42, 0.58, -1.0, 1.0), (0.58, 0.58, 1.0, 1.0))
    for x, y, x_way, y_way in corners:
        _line(draw, size, ((x, y + y_way * arm), (x, y), (x + x_way * arm, y)), color, width)


def _paint_lock(draw: ImageDraw.ImageDraw, size: float, color: str, width: int) -> None:
    _rect(draw, size, (0.20, 0.44, 0.80, 0.90), color, width, 0.10)
    draw.arc(
        (0.32 * size, 0.12 * size, 0.68 * size, 0.62 * size),
        start=180,
        end=360,
        fill=color,
        width=width,
    )


_PAINTERS: dict[str, IconPainter] = {
    "system": _paint_monitor,
    "cpu": _paint_chip,
    "memory": _paint_ram,
    "disk": _paint_disk,
    "network": _paint_globe,
    "usb": _paint_usb,
    "pci": _paint_card,
    "driver": _paint_gear,
    "problem_device": _paint_alert,
    "monitor_gpu": _paint_monitor,
    "io": _paint_pulse,
    "report": _paint_document,
    "copy": _paint_copy,
    "save": _paint_save,
    "check": _paint_check,
    "info": _paint_info,
    "refresh": _paint_refresh,
    "expand": _paint_expand,
    "collapse": _paint_collapse,
    "lock": _paint_lock,
}


def available_icons() -> tuple[str, ...]:
    """Nombres de icono que `render` sabe dibujar."""
    return tuple(sorted(_PAINTERS))


def render(name: str, size: int, color: str, stroke: float = 0.07) -> Image.Image:
    """Devuelve el icono `name` como imagen RGBA de `size` píxeles de lado."""
    painter = _PAINTERS.get(name)
    if painter is None:
        raise KeyError(f"Icono desconocido: {name}")
    canvas = size * _SUPERSAMPLE
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    painter(ImageDraw.Draw(image), float(canvas), color, max(1, round(stroke * canvas)))
    return image.resize((size, size), Image.Resampling.LANCZOS)
