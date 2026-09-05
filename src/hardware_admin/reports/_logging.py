"""Registro común de las exportaciones.

Anota el resultado y la ruta, nunca el contenido del reporte: los registros
técnicos sirven para diagnosticar la aplicación, no para conservar datos del
equipo analizado.
"""

from __future__ import annotations

import logging
from pathlib import Path

LOGGER = logging.getLogger("hardware_admin.reports")


def log_export(path: Path, report_format: str, include_identity: bool = True) -> None:
    """Deja constancia de una exportación completada."""
    LOGGER.info(
        "report_exported format=%s identity=%s path=%s bytes=%d",
        report_format,
        "included" if include_identity else "omitted",
        path,
        path.stat().st_size if path.exists() else 0,
    )
