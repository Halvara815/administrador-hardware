"""Captura controlada de la ventana para revisión visual local."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import ImageGrab

from hardware_admin.app_factory import build_scan_service
from hardware_admin.domain.models import ComponentKind
from hardware_admin.ui.main_window import HardwareAdminApp


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=1580)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--output", type=Path, default=Path("docs/ui-live.png"))
    args = parser.parse_args()

    app = HardwareAdminApp(build_scan_service())
    app.geometry(f"{args.width}x{args.height}+20+20")
    app.attributes("-topmost", True)
    app.after(400, app.start_scan)

    attempts = 0

    def wait_for_scan() -> None:
        nonlocal attempts
        attempts += 1
        if app.report is None and attempts < 240:
            app.after(250, wait_for_scan)
            return
        app.select_component(ComponentKind.MEMORY)
        # CustomTkinter repinta sus lienzos en varios ciclos: capturar antes de
        # que terminen produce etiquetas a medio dibujar.
        app.update()
        app.after(700, grab)

    def grab() -> None:
        app.update()
        app.update_idletasks()
        left = app.winfo_rootx()
        top = app.winfo_rooty()
        right = left + app.winfo_width()
        bottom = top + app.winfo_height()
        destination = args.output
        ImageGrab.grab(bbox=(left, top, right, bottom)).save(destination)
        print(destination.resolve())
        app.destroy()

    app.after(700, wait_for_scan)
    app.mainloop()


if __name__ == "__main__":
    main()
