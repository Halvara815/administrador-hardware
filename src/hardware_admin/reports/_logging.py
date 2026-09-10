"""Registro común de las exportaciones.

Anota el resultado y la ruta, nunca el contenido del reporte: los registros
técnicos sirven para diagnosticar la aplicación, no para conservar datos del
equipo analizado.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

LOGGER = logging.getLogger("hardware_admin.reports")


def _safe_export_name(path: Path) -> str:
    """Registra un nombre seguro y un hash si la ruta contenía un usuario local."""
    safe_name = path.name
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]
    if "Users" in str(path) or "users" in str(path):
        return f"{safe_name}#{digest}"
    return safe_name


def log_export(path: Path, report_format: str, include_identity: bool = True) -> None:
    """Deja constancia de una exportación completada."""
    LOGGER.info(
        "report_exported format=%s identity=%s path=%s bytes=%d",
        report_format,
        "included" if include_identity else "omitted",
        _safe_export_name(path),
        path.stat().st_size if path.exists() else 0,
    )
