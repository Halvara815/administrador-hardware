# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.hooks.tcl_tk import tcltk_info


project_root = Path(SPECPATH).parent

# Verificación de integridad Tcl/Tk del intérprete activo
if tcltk_info.tcl_data_missing or tcltk_info.tk_data_missing:
    raise RuntimeError(
        f"Instalación incompleta de Tcl/Tk en el intérprete: "
        f"tcl_missing={tcltk_info.tcl_data_missing}, tk_missing={tcltk_info.tk_data_missing}"
    )

ctk_datas, ctk_binaries, ctk_hidden = collect_all("customtkinter")

# Imports ocultos requeridos explícitamente para Tkinter y PIL
explicit_hiddenimports = [
    "tkinter",
    "_tkinter",
    "tkinter.constants",
    "tkinter.filedialog",
    "tkinter.font",
    "tkinter.ttk",
    "PIL.ImageTk",
]

hiddenimports = sorted(set(ctk_hidden + explicit_hiddenimports))

# Recursos de datos
datas = list(ctk_datas)
datas += [
    (str(project_root / "assets" / "app-icon.ico"), "assets"),
    (str(project_root / "assets" / "app-icon.png"), "assets"),
]

# Binarios: asegurar que DLLs Tcl/Tk y extensión _tkinter.pyd se incluyan explícitamente
binaries = list(ctk_binaries)
base_prefix = Path(sys.base_prefix)
dlls_dir = base_prefix / "DLLs"
for dll_name in ("tcl86t.dll", "tk86t.dll", "_tkinter.pyd"):
    dll_path = dlls_dir / dll_name
    if not dll_path.exists():
        raise FileNotFoundError(f"Falta binario crítico de Tcl/Tk: {dll_path}")
    binaries.append((str(dll_path), "."))

a = Analysis(
    [str(project_root / "src" / "hardware_admin" / "main.py")],
    pathex=[str(project_root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)

# Conservar exactamente la jerarquía de destino requerida por PyInstaller/Tcl
# sin alterar dest con Path(dest).parent. tcltk_info.data_files contiene tuplas canónicas (dest, src, typecode).
for dest, src, typecode in tcltk_info.data_files:
    entry = (dest, src, typecode)
    if entry not in a.datas:
        a.datas.append(entry)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AdministradorDeHardware",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(project_root / "assets" / "app-icon.ico"),
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AdministradorDeHardware",
)
