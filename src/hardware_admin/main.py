"""Punto de entrada de la aplicación de escritorio."""

import argparse
import json
import sys
from pathlib import Path

from hardware_admin.app_factory import build_scan_service
from hardware_admin.infrastructure.logging_setup import configure_logging
from hardware_admin.reports.html_report import export_html


def _headless_scan(export_path: Path | None = None) -> None:
    report = build_scan_service().scan()
    if export_path is not None:
        export_html(report, export_path)
    summary = {
        "completed_at": report.completed_at.isoformat(),
        "conclusion": report.conclusion,
        "limitations": report.limitations,
        "results": [
            {
                "component": result.component.value,
                "name": result.name,
                "summary": result.summary,
                "status": result.status.value,
                "possible_problem": result.possible_problem,
            }
            for result in report.results
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Administrador de Hardware")
    parser.add_argument(
        "--headless-scan", action="store_true", help="Ejecuta el diagnóstico sin abrir la UI"
    )
    parser.add_argument(
        "--smoke-test", action="store_true", help="Construye y destruye la ventana para validarla"
    )
    parser.add_argument(
        "--export-report",
        type=Path,
        metavar="ARCHIVO",
        help="Exporta el diagnóstico headless a un reporte HTML",
    )
    args = parser.parse_args()
    if args.headless_scan:
        _headless_scan(args.export_report)
        return

    if args.smoke_test:
        # Antes de construir nada: un recurso ausente o corrupto revienta la
        # cabecera con FileNotFoundError y el usuario ve un traceback en vez de
        # la ventana. Comprobarlo aquí convierte ese fallo en un error claro.
        from hardware_admin.resources import verify_ui_assets

        problems = verify_ui_assets()
        if problems:
            print("ERROR: recursos gráficos no utilizables:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            sys.exit(1)
        print("Verificación de recursos gráficos: PASS")

    from hardware_admin.ui.main_window import HardwareAdminApp

    app = HardwareAdminApp(build_scan_service())
    if args.smoke_test:
        app.update_idletasks()
        app.open_thermal_dashboard()
        app.update_idletasks()
        if app.thermal_window is not None:
            app.thermal_window.destroy()
        app.update_idletasks()
        app.open_windows_events()
        app.update_idletasks()
        if app.windows_events_window is not None:
            app.windows_events_window.destroy()
        app.update_idletasks()
        print(app.export_debug_state())
        app.destroy()
        sys.exit(0)
    app.mainloop()


if __name__ == "__main__":
    main()
