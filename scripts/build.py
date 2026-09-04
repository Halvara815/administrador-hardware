"""Construcción reproducible del ejecutable sin cambiar políticas de Windows."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = PROJECT_ROOT / ".venv"
VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"


def run(command: list[str]) -> None:
    printable = " ".join(command)
    print(f"\n> {printable}")
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def main() -> None:
    if not VENV_PYTHON.exists():
        run([sys.executable, "-m", "venv", str(VENV_DIR)])

    python = str(VENV_PYTHON)
    run([python, "-m", "pip", "install", "-r", "requirements.lock"])
    run([python, "-m", "pip", "install", "--no-deps", "-e", "."])
    run([python, "scripts/prepare_icon.py"])
    run([python, "-m", "pytest", "-q"])
    run([str(VENV_DIR / "Scripts" / "ruff.exe"), "check", "."])
    run([str(VENV_DIR / "Scripts" / "mypy.exe"), "src"])
    run(
        [
            python,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(PROJECT_ROOT / "packaging" / "AdministradorDeHardware.spec"),
        ]
    )
    executable = PROJECT_ROOT / "dist" / "AdministradorDeHardware" / "AdministradorDeHardware.exe"
    if not executable.exists():
        raise FileNotFoundError(f"PyInstaller no creó {executable}")
    distribution = executable.parent
    shutil.copy2(PROJECT_ROOT / "MANUAL_USUARIO.txt", distribution / "LEEME.txt")
    release_directory = PROJECT_ROOT / "release"
    release_directory.mkdir(exist_ok=True)
    archive_base = release_directory / "AdministradorDeHardware-v0.1.0-windows-x64"
    archive = shutil.make_archive(
        str(archive_base),
        "zip",
        root_dir=distribution.parent,
        base_dir=distribution.name,
    )
    print(f"\nEjecutable creado: {executable}")
    print(f"Paquete de entrega: {archive}")


if __name__ == "__main__":
    main()
