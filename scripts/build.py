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


def verify_assets(distribution: Path, label: str) -> None:
    """Abre cada recurso grafico del paquete y comprueba que es una imagen valida.

    Un usuario recibio FileNotFoundError desde PIL.Image.open al abrir el
    ejecutable: el recurso no habia llegado al paquete y ninguna puerta lo
    detectaba. Comprobar solo la existencia tampoco bastaria, porque un archivo
    truncado existe y falla igual al abrirlo.
    """
    from PIL import Image, UnidentifiedImageError

    required = ("app-icon.png", "app-icon.ico")
    for name in required:
        path = distribution / "_internal" / "assets" / name
        if not path.exists():
            raise FileNotFoundError(f"Falta recurso grafico en {label}: {path}")
        try:
            with Image.open(path) as image:
                image.verify()
        except (OSError, UnidentifiedImageError) as exc:
            raise RuntimeError(f"Recurso grafico ilegible en {label}: {path} ({exc})") from exc
    print(f"> Verificación de recursos gráficos en {label}: {', '.join(required)} legibles.")


def main() -> None:
    if not VENV_PYTHON.exists():
        run([sys.executable, "-m", "venv", str(VENV_DIR)])

    python = str(VENV_PYTHON)
    run([python, "-m", "pip", "install", "-r", "requirements.lock"])
    run([python, "-m", "pip", "install", "--no-deps", "-e", "."])
    run([python, "scripts/prepare_icon.py"])

    # 1. Verificar explícitamente la disponibilidad nativa de Tcl/Tk sin copiar recursos como workaround
    check_tk_code = (
        "import sys, tkinter\n"
        "try:\n"
        "    root = tkinter.Tk()\n"
        "    root.destroy()\n"
        "    print('Verificación nativa de Tcl/Tk en el entorno: PASS')\n"
        "except Exception as err:\n"
        "    print(f'ERROR CRÍTICO: Tcl/Tk no funciona en el entorno {sys.executable}: {err}', file=sys.stderr)\n"
        "    sys.exit(1)\n"
    )
    run([python, "-c", check_tk_code])

    run([python, "-m", "pytest", "--capture=sys", "-q"])
    run([str(VENV_DIR / "Scripts" / "ruff.exe"), "check", "."])
    # Sin argumentos usa los paquetes del pyproject, que es la puerta real.
    run([str(VENV_DIR / "Scripts" / "mypy.exe")])

    # Verificar que ningún proceso residual de AdministradorDeHardware esté bloqueando archivos
    check_process_code = (
        "import psutil, sys\n"
        "blocking = [p.info for p in psutil.process_iter(['name', 'pid']) if p.info['name'] and 'AdministradorDeHardware' in p.info['name']]\n"
        "if blocking:\n"
        "    pids = ', '.join(str(b['pid']) for b in blocking)\n"
        "    print(f'ERROR: El proceso AdministradorDeHardware está en ejecución (PID: {pids}). Por favor ciérrelo manualmente antes de continuar el build.', file=sys.stderr)\n"
        "    sys.exit(1)\n"
    )
    run([python, "-c", check_process_code])

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

    # Verificar que el paquete compilado contenga init.tcl y tk.tcl en _internal
    tcl_init = distribution / "_internal" / "_tcl_data" / "init.tcl"
    tk_init = distribution / "_internal" / "_tk_data" / "tk.tcl"
    if not tcl_init.exists():
        raise FileNotFoundError(f"Falta archivo crítico Tcl en la distribución: {tcl_init}")
    if not tk_init.exists():
        raise FileNotFoundError(f"Falta archivo crítico Tk en la distribución: {tk_init}")
    print("> Verificación de recursos Tcl/Tk en paquete dist: init.tcl y tk.tcl presentes.")

    # Los recursos graficos se abren de verdad, no solo se comprueba que existan:
    # un archivo truncado existe y aun asi revienta la cabecera en el arranque.
    verify_assets(distribution, "dist")

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

    # 2. Puertas obligatorias de smoke test post-empaquetado:
    # a) Smoke test directo sobre el ejecutable en dist
    print("\n> Ejecutando smoke test sobre ejecutable en dist...")
    run([str(executable), "--smoke-test"])

    # b) Extracción limpia del paquete ZIP y smoke test sobre el ejecutable descomprimido
    print("\n> Ejecutando smoke test sobre el ejecutable extraído del ZIP de release...")
    temp_smoke_dir = PROJECT_ROOT / "scratch" / "build_zip_smoke"
    if temp_smoke_dir.exists():
        shutil.rmtree(temp_smoke_dir)
    temp_smoke_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.unpack_archive(archive_path, temp_smoke_dir)
        unzipped_dist = temp_smoke_dir / distribution.name
        extracted_exe = unzipped_dist / executable.name
        if not extracted_exe.exists():
            raise FileNotFoundError(f"El ejecutable no existe dentro del paquete ZIP: {extracted_exe}")

        extracted_tcl_init = unzipped_dist / "_internal" / "_tcl_data" / "init.tcl"
        extracted_tk_init = unzipped_dist / "_internal" / "_tk_data" / "tk.tcl"
        if not extracted_tcl_init.exists():
            raise FileNotFoundError(f"Falta archivo crítico Tcl en el ZIP extraído: {extracted_tcl_init}")
        if not extracted_tk_init.exists():
            raise FileNotFoundError(f"Falta archivo crítico Tk en el ZIP extraído: {extracted_tk_init}")
        print("> Verificación de recursos Tcl/Tk en paquete ZIP extraído: init.tcl y tk.tcl presentes.")

        verify_assets(unzipped_dist, "ZIP extraído")

        run([str(extracted_exe), "--smoke-test"])
    finally:
        shutil.rmtree(temp_smoke_dir, ignore_errors=True)

    print(f"\nEjecutable creado : {executable}")
    print(f"Paquete de entrega: {archive_path}")
    print(f"SHA-256           : {checksum}")
    print(f"Huella escrita en : {checksum_file}")
    print("\nComprobacion pendiente en un equipo limpio sin Python instalado:")
    print("  descomprimir el ZIP, ejecutar el EXE y recorrer los 14 apartados.")


if __name__ == "__main__":
    main()
