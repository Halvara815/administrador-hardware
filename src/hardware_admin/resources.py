"""Resolución de recursos tanto en desarrollo como dentro de PyInstaller."""

from __future__ import annotations

import sys
from pathlib import Path

#: Recursos gráficos que la interfaz abre al construirse. Si falta uno, la
#: ventana principal aborta con FileNotFoundError antes de mostrarse, así que
#: se comprueban explícitamente en el arranque de verificación.
REQUIRED_UI_ASSETS: tuple[tuple[str, ...], ...] = (
    ("assets", "app-icon.png"),
    ("assets", "app-icon.ico"),
)


def resource_path(*parts: str) -> Path:
    bundled_root = getattr(sys, "_MEIPASS", None)
    base = Path(bundled_root) if bundled_root else Path(__file__).resolve().parents[2]
    return base.joinpath(*parts)


def verify_ui_assets() -> list[str]:
    """Comprueba que cada recurso obligatorio existe y es una imagen legible.

    `Path.exists()` no basta: un archivo truncado por un empaquetado a medias
    existe y aun así revienta al abrirlo. Por eso se abre con Pillow y se
    valida su contenido, que es exactamente lo que hace la interfaz al
    construir la cabecera.

    Devuelve la lista de problemas encontrados; vacía significa que todos los
    recursos son utilizables.
    """
    from PIL import Image, UnidentifiedImageError

    problems: list[str] = []
    for parts in REQUIRED_UI_ASSETS:
        path = resource_path(*parts)
        if not path.exists():
            problems.append(f"{'/'.join(parts)}: no existe en {path}")
            continue
        try:
            with Image.open(path) as image:
                # verify() detecta contenido corrupto sin decodificar entera.
                image.verify()
        except (OSError, UnidentifiedImageError) as exc:
            problems.append(f"{'/'.join(parts)}: no se pudo abrir ({exc}) en {path}")
    return problems
