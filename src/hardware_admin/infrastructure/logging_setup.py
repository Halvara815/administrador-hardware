"""Logging local y acotado para fallos de la propia aplicación."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.cwd())) / "AdministradorHardware"
    log_directory = base / "logs"
    log_path = log_directory / "app.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    try:
        log_directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_path,
            maxBytes=256_000,
            backupCount=2,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        if not any(
            isinstance(existing, RotatingFileHandler) and Path(existing.baseFilename) == log_path
            for existing in root.handlers
        ):
            root.addHandler(handler)
    except (OSError, PermissionError):
        # Degradar de forma segura a NullHandler sin impedir el arranque ni filtrar datos sensibles
        if not any(isinstance(existing, logging.NullHandler) for existing in root.handlers):
            root.addHandler(logging.NullHandler())

    return log_path
