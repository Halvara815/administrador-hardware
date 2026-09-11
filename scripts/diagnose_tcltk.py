"""Diagnóstico de solo lectura del entorno Tcl/Tk.

No modifica nada: no copia recursos, no define variables de entorno y no
escribe fuera de la salida estándar. Está pensado para ejecutarse antes de
`build.py`, de `pytest` y del `--smoke-test`, y para conservar su salida como
evidencia del entorno en que se obtuvieron los resultados.

Uso:
    .venv\\Scripts\\python.exe scripts\\diagnose_tcltk.py

Código de salida 0 si `tkinter.Tk()` funciona; 1 en caso contrario.

El fallo «Can't find a usable init.tcl» no significa que el archivo falte:
significa que Tcl lo encontró y no pudo usarlo. Conviene leer la causa concreta
que acompaña al mensaje:

- «couldn't read file ...: No error» con el archivo presente y legible indica
  que los descriptores estándar del proceso están redirigidos a nivel de
  sistema operativo. Tcl los necesita al inicializar un intérprete. Es lo que
  provoca la captura por defecto de pytest (`--capture=fd`); por eso el
  proyecto fija `--capture=sys` en pyproject.toml.
- Una discrepancia de versión entre la DLL cargada y los archivos de librería
  produce el mismo encabezado. Por eso este informe lista las DLL candidatas en
  el orden de búsqueda de Windows y la versión que exige `init.tcl`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

CANDIDATE_DLLS = ("tcl86t.dll", "tk86t.dll")


def _section(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def _interpreter_report() -> None:
    _section("Intérprete")
    print(f"sys.executable   : {sys.executable}")
    print(f"sys.prefix       : {sys.prefix}")
    print(f"sys.base_prefix  : {sys.base_prefix}")
    print(f"version          : {sys.version.split()[0]}")
    print(f"frozen (PyInstaller): {getattr(sys, 'frozen', False)}")
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        print(f"_MEIPASS         : {meipass}")


def _environment_report() -> None:
    _section("Variables de entorno Tcl/Tk")
    for name in ("TCL_LIBRARY", "TK_LIBRARY", "TCLLIBPATH"):
        print(f"{name:<16} : {os.environ.get(name, '(no definida)')}")
    print("Ninguna debería estar definida: usarlas como parche oculta el problema real.")


def _library_files_report() -> None:
    _section("Archivos de librería Tcl/Tk")
    roots = [Path(sys.base_prefix) / "tcl"]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))
    for root in roots:
        print(f"raíz: {root}  existe={root.exists()}")
        if not root.exists():
            continue
        for relative in ("tcl8.6/init.tcl", "tk8.6/tk.tcl", "_tcl_data/init.tcl", "_tk_data/tk.tcl"):
            candidate = root / relative
            if candidate.exists():
                declared = _declared_version(candidate)
                suffix = f"  package require -exact -> {declared}" if declared else ""
                print(f"   OK    {relative}{suffix}")


def _declared_version(init_tcl: Path) -> str | None:
    """Versión exacta que `init.tcl` exige de la DLL de Tcl.

    Si no coincide con la DLL cargada, Tcl declara el archivo inservible.
    """
    try:
        for line in init_tcl.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped.startswith("package require -exact Tcl"):
                return stripped.split()[-1]
    except OSError:
        return None
    return None


def _dll_resolution_report() -> None:
    """Lista las DLL de Tcl/Tk visibles en el orden de búsqueda de Windows.

    La primera de la lista es la que se cargaría, y si su versión no es la de
    los archivos de librería, `init.tcl` se declara inservible.
    """
    _section("Resolución de DLL Tcl/Tk (orden de búsqueda de Windows)")
    search_dirs: list[Path] = [
        Path(sys.executable).parent,
        Path(sys.base_prefix) / "DLLs",
    ]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        search_dirs.insert(0, Path(meipass))
    search_dirs += [Path(item) for item in os.environ.get("PATH", "").split(os.pathsep) if item]

    for dll_name in CANDIDATE_DLLS:
        print(f"{dll_name}:")
        found = 0
        seen: set[str] = set()
        for directory in search_dirs:
            try:
                candidate = directory / dll_name
                key = str(candidate).lower()
                if key in seen or not candidate.is_file():
                    continue
            except OSError:
                continue
            seen.add(key)
            found += 1
            marker = "  <-- se cargaría esta" if found == 1 else ""
            size = candidate.stat().st_size
            print(f"   {found}. {candidate}  ({size:,} bytes){marker}")
        if found == 0:
            print("   ninguna encontrada en las rutas de búsqueda")
        elif found > 1:
            print(f"   AVISO: {found} copias distintas visibles. Si la primera no")
            print("   corresponde a este Python, Tcl rechazará init.tcl por versión.")


def _tk_report() -> int:
    _section("Prueba de tkinter.Tk()")
    try:
        import tkinter
    except ImportError as exc:
        print(f"FALLO al importar tkinter: {type(exc).__name__}: {exc}")
        return 1

    try:
        import _tkinter
    except ImportError:
        print("_tkinter no disponible: la extensión nativa no está instalada.")
    else:
        print(f"_tkinter compilado contra Tcl {_tkinter.TCL_VERSION} / Tk {_tkinter.TK_VERSION}")

    try:
        root = tkinter.Tk()
    except tkinter.TclError as exc:
        print(f"FALLO: {type(exc).__name__}: {exc}")
        print()
        print("«usable» es la palabra clave: si el mensaje dice que no encuentra")
        print("un init.tcl *usable*, el archivo existe pero su versión no case con")
        print("la DLL cargada. Revise arriba qué DLL se cargaría primero.")
        return 1

    try:
        print(f"info library     : {root.tk.eval('info library')}")
        print(f"info patchlevel  : {root.tk.eval('info patchlevel')}")
        print(f"tk windowingsystem: {root.tk.eval('tk windowingsystem')}")
    finally:
        root.destroy()
    print("RESULTADO: TCL_TK_PASS")
    return 0


def main() -> int:
    print("=" * 72)
    print("Diagnóstico Tcl/Tk (solo lectura)")
    print("=" * 72)
    _interpreter_report()
    _environment_report()
    _library_files_report()
    _dll_resolution_report()
    return _tk_report()


if __name__ == "__main__":
    sys.exit(main())
