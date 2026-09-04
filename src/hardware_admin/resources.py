"""Resolución de recursos tanto en desarrollo como dentro de PyInstaller."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_path(*parts: str) -> Path:
    bundled_root = getattr(sys, "_MEIPASS", None)
    base = Path(bundled_root) if bundled_root else Path(__file__).resolve().parents[2]
    return base.joinpath(*parts)
