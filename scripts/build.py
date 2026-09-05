"""Construcción reproducible del ejecutable sin cambiar políticas de Windows."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = PROJECT_ROOT / ".venv"
VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"

#: Documentos que acompañan al ejecutable en el paquete de entrega.
#: LEEME.txt es el manual renombrado; el resto viaja con su nombre.
DISTRIBUTION_DOCS: tuple[tuple[str, str], ...] = (
    ("MANUAL_USUARIO.txt", "LEEME.txt"),
    ("CHANGELOG.md", "CHANGELOG.md"),
    ("THIRD_PARTY_NOTICES.txt", "THIRD_PARTY_NOTICES.txt"),
)


def sha256_of(path: Path) -> str:
    """Huella del paquete, para comprobar que llega íntegro a su destino."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
    # Sin argumentos usa los paquetes del pyproject, que es la puerta real.
    run([str(VENV_DIR / "Scripts" / "mypy.exe")])
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
    for source_name, target_name in DISTRIBUTION_DOCS:
        source = PROJECT_ROOT / source_name
        if not source.exists():
            raise FileNotFoundError(f"Falta el documento de entrega: {source}")
        shutil.copy2(source, distribution / target_name)
    release_directory = PROJECT_ROOT / "release"
    release_directory.mkdir(exist_ok=True)
    archive_base = release_directory / "AdministradorDeHardware-v0.1.0-windows-x64"
    archive = shutil.make_archive(
        str(archive_base),
        "zip",
        root_dir=distribution.parent,
        base_dir=distribution.name,
    )
    archive_path = Path(archive)
    checksum = sha256_of(archive_path)
    checksum_file = archive_path.with_suffix(archive_path.suffix + ".sha256")
    checksum_file.write_text(f"{checksum}  {archive_path.name}\n", encoding="utf-8")

    print(f"\nEjecutable creado : {executable}")
    print(f"Paquete de entrega: {archive_path}")
    print(f"SHA-256           : {checksum}")
    print(f"Huella escrita en : {checksum_file}")
    print("\nComprobacion pendiente en un equipo limpio sin Python instalado:")
    print("  descomprimir el ZIP, ejecutar el EXE y recorrer los 15 apartados.")


if __name__ == "__main__":
    main()
