"""Ventana principal del Administrador de Hardware."""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk
from PIL import Image

from hardware_admin.collectors.core import format_bytes
from hardware_admin.diagnostics.rules import CPU_RULE, DISK_RULE
from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    DiagnosticReport,
    HealthStatus,
)
from hardware_admin.infrastructure.commands import generate_battery_report
from hardware_admin.reports.html_report import export_html
from hardware_admin.reports.json_report import export_json
from hardware_admin.reports.txt_report import export_txt
from hardware_admin.resources import resource_path
from hardware_admin.services.monitoring_service import (
    MonitoringService,
    PsutilRateSampler,
    Sample,
)
from hardware_admin.services.scan_service import ScanService
from hardware_admin.ui import icons, theme
from hardware_admin.ui.charts import (
    Bar,
    BarListChart,
    GaugeChart,
    SeriesSpec,
    TimeSeriesChart,
    format_rate,
)

STATUS_LABELS = {
    HealthStatus.UNKNOWN: "Sin analizar",
    HealthStatus.NORMAL: "Normal",
    HealthStatus.WARNING: "Advertencia",
    HealthStatus.CRITICAL: "Problema",
    HealthStatus.ERROR: "Error de consulta",
    HealthStatus.NOT_SUPPORTED: "No soportado",
    HealthStatus.CANCELLED: "Cancelado",
}

STATUS_COLORS = theme.STATUS_COLORS

#: Salto de línea usado al componer las vistas de texto.
NL = chr(10)

@dataclass(frozen=True, slots=True)
class NavEntry:
    """Una entrada del menú: o abre un componente, o ejecuta una acción.

    Las dos son excluyentes. Conectividad, Recomendaciones, Generar reporte,
    Exportar y Salir no corresponden a ningún `ComponentKind`, y con un simple
    `None` no se distinguiría una acción de otra.
    """

    icon: str
    label: str
    component: ComponentKind | None = None
    action: str | None = None


#: Los 15 apartados del enunciado más Salir, en el orden pedido.
NAV_ITEMS: tuple[NavEntry, ...] = (
    NavEntry("system", "1. Diagnóstico general", ComponentKind.SYSTEM),
    NavEntry("cpu", "2. CPU", ComponentKind.CPU),
    NavEntry("memory", "3. RAM", ComponentKind.MEMORY),
    NavEntry("pci", "4. PCI / PCIe", ComponentKind.PCI),
    NavEntry("network", "5. Red", ComponentKind.NETWORK),
    NavEntry("usb", "6. USB", ComponentKind.USB),
    NavEntry("disk", "7. Almacenamiento", ComponentKind.DISK),
    NavEntry("monitor_gpu", "8. GPU / vídeo", ComponentKind.MONITOR_GPU),
    NavEntry("driver", "9. Controladores", ComponentKind.DRIVER),
    NavEntry("problem_device", "10. Dispositivos con problemas", ComponentKind.PROBLEM_DEVICE),
    NavEntry("check", "11. Conectividad", action="connectivity"),
    NavEntry("io", "12. Monitorización", ComponentKind.IO),
    NavEntry("info", "13. Recomendaciones", action="recommendations"),
    NavEntry("report", "14. Generar reporte", action="report"),
    NavEntry("save", "15. Exportar diagnóstico", action="export"),
    NavEntry("exit", "0. Salir", action="exit"),
)

#: Nombre corto de cada sección, usado en el botón de análisis independiente.
SECTION_NAMES: dict[ComponentKind, str] = {
    ComponentKind.SYSTEM: "sistema",
    ComponentKind.CPU: "CPU",
    ComponentKind.MEMORY: "RAM",
    ComponentKind.DISK: "almacenamiento",
    ComponentKind.NETWORK: "red",
    ComponentKind.USB: "USB",
    ComponentKind.PCI: "PCI",
    ComponentKind.DRIVER: "controladores",
    ComponentKind.PROBLEM_DEVICE: "dispositivos",
    ComponentKind.MONITOR_GPU: "GPU y vídeo",
    ComponentKind.IO: "monitorización",
}

COMPONENT_ORDER: tuple[ComponentKind, ...] = tuple(
    entry.component for entry in NAV_ITEMS if entry.component is not None
)

ICON_NAMES: dict[ComponentKind, str] = {
    entry.component: entry.icon for entry in NAV_ITEMS if entry.component is not None
}

#: Título, peso y ancho mínimo de cada columna de la matriz de diagnóstico.
MATRIX_COLUMNS: tuple[tuple[str, int, int], ...] = (
    ("Componente", 26, 150),
    ("Evidencia", 25, 140),
    ("Estado", 18, 105),
    ("Posible problema", 31, 150),
)


#: Series de cada grafico de monitorizacion, en orden de dibujo.
MONITORING_DISK_SPECS: tuple[SeriesSpec, ...] = (
    SeriesSpec("Lectura", theme.ACCENT_TEXT),
    SeriesSpec("Escritura", theme.YELLOW),
)
MONITORING_NET_SPECS: tuple[SeriesSpec, ...] = (
    SeriesSpec("Envío", theme.GREEN),
    SeriesSpec("Recepción", "#56D4DD"),
)


#: Tamaño con el que abre la ventana cuando la pantalla lo permite.
PREFERRED_SIZE = (1580, 900)
#: Tamaño mínimo deseable; se recorta si la pantalla no da para tanto.
MINIMUM_SIZE = (1180, 720)
#: Margen reservado para la barra de tareas y el marco de la ventana.
SCREEN_MARGIN = (0, 80)


def fit_window(
    screen_width: int,
    screen_height: int,
    scaling: float = 1.0,
    preferred: tuple[int, int] = PREFERRED_SIZE,
    minimum: tuple[int, int] = MINIMUM_SIZE,
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Ajusta el tamaño de la ventana a la pantalla y al escalado del sistema.

    Devuelve la geometría inicial y el tamaño mínimo, ambos en unidades
    lógicas de Tk. Con escalado al 125 % o 150 % un mínimo fijo de 1180x720
    ocuparía 1475x900 o 1770x1080 píxeles físicos, imposible en la pantalla
    de 1366x768 que fija el requisito: el usuario no podría encoger la ventana
    hasta que cupiera. Por eso el mínimo también se recorta.
    """
    factor = max(scaling, 0.1)
    usable_width = max(screen_width - SCREEN_MARGIN[0], 320)
    usable_height = max(screen_height - SCREEN_MARGIN[1], 240)
    max_logical = (int(usable_width / factor), int(usable_height / factor))

    geometry = (min(preferred[0], max_logical[0]), min(preferred[1], max_logical[1]))
    smallest = (min(minimum[0], geometry[0]), min(minimum[1], geometry[1]))
    return geometry, smallest


def series_for(
    samples: Sequence[Sample],
) -> tuple[list[float], list[float], list[float], list[float]]:
    """Separa las muestras en las cuatro series que dibujan los graficos."""
    return (
        [item.disk_read_bps for item in samples],
        [item.disk_write_bps for item in samples],
        [item.net_sent_bps for item in samples],
        [item.net_recv_bps for item in samples],
    )


def _status_color(status: HealthStatus) -> str:
    return STATUS_COLORS.get(status, theme.MUTED)


def _number_list(facts: dict[str, Any], key: str) -> list[float]:
    """Lee una serie numerica. Un dato ausente o con otra forma no es un hallazgo."""
    raw = facts.get(key)
    if not isinstance(raw, list):
        return []
    return [float(item) for item in raw if isinstance(item, int | float)]


def _dict_list(facts: dict[str, Any], key: str) -> list[dict[str, Any]]:
    raw = facts.get(key)
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def core_bars(facts: dict[str, Any]) -> list[Bar]:
    """Una barra por nucleo logico, coloreada con la regla oficial de CPU."""
    return [
        Bar(
            label=f"Núcleo {index}",
            ratio=value / 100.0,
            value=f"{value:.1f}%",
            color=_status_color(CPU_RULE.classify(value)),
        )
        for index, value in enumerate(_number_list(facts, "_nucleos"), start=1)
    ]


def volume_bars(facts: dict[str, Any]) -> list[Bar]:
    """Una barra por unidad montada, con la fraccion ocupada y la regla de disco."""
    bars: list[Bar] = []
    for item in _dict_list(facts, "_volumenes"):
        used = float(item.get("usado", 0.0))
        free = float(item.get("libre", 0.0))
        total = used + free
        percent = float(item.get("porcentaje", 0.0))
        bars.append(
            Bar(
                label=str(item.get("unidad", "?")),
                ratio=used / total if total > 0 else 0.0,
                value=f"{format_bytes(used)} de {format_bytes(total)}",
                color=_status_color(DISK_RULE.classify(percent)),
            )
        )
    return bars


def adapter_bars(facts: dict[str, Any]) -> list[Bar]:
    """Velocidad de enlace por adaptador, en proporcion al mas rapido."""
    items = _dict_list(facts, "_adaptadores")
    fastest = max((float(item.get("mbps", 0.0)) for item in items), default=0.0)
    bars: list[Bar] = []
    for item in items:
        mbps = float(item.get("mbps", 0.0))
        connected = bool(item.get("conectado"))
        bars.append(
            Bar(
                label=str(item.get("nombre", "?")),
                ratio=mbps / fastest if fastest > 0 else 0.0,
                value=f"{mbps:.0f} Mbps" if mbps else "No disponible",
                color=theme.ACCENT_TEXT if connected else theme.MUTED,
            )
        )
    return bars


def _format_value(value: Any, indent: str = "") -> str:
    if isinstance(value, list):
        if not value:
            return "Sin elementos"
        lines: list[str] = []
        for index, item in enumerate(value, start=1):
            if isinstance(item, dict):
                compact = " | ".join(
                    f"{key}: {val if val not in (None, '') else 'No disponible'}"
                    for key, val in item.items()
                )
                lines.append(f"{indent}{index}. {compact}")
            else:
                lines.append(f"{indent}{index}. {item}")
        return "\n".join(lines)
    if isinstance(value, dict):
        return "\n".join(f"{indent}{key}: {val}" for key, val in value.items())
    return str(value)


def _console_tag(line: str) -> str | None:
    if line.startswith("> "):
        return "prompt"
    if line.startswith("! "):
        return "error"
    if line.startswith(" "):
        return None
    stripped = line.strip()
    if not stripped:
        return None
    if stripped == stripped.upper() or stripped.endswith(":"):
        return "key"
    return None


def _configure_console_tags(console: Any) -> None:
    console.tag_config("prompt", foreground=theme.CONSOLE_PROMPT)
    console.tag_config("key", foreground=theme.CONSOLE_KEY)
    console.tag_config("error", foreground=theme.CONSOLE_ERROR)


def _fill_console(console: Any, text: str) -> None:
    """Escribe la evidencia en un cuadro de solo lectura, coloreada por tipo de linea."""
    console.configure(state="normal")
    console.delete("1.0", "end")
    clipped = text[:60_000]
    console.insert("1.0", clipped)
    for number, line in enumerate(clipped.splitlines()[:2500], start=1):
        tag = _console_tag(line)
        if tag is not None:
            console.tag_add(tag, f"{number}.0", f"{number}.end")
    console.configure(state="disabled")


def _configure_matrix_columns(frame: Any) -> None:
    for index, (_, weight, minsize) in enumerate(MATRIX_COLUMNS):
        frame.grid_columnconfigure(index, weight=weight, minsize=minsize)


class IconCache:
    """Crea los `CTkImage` una sola vez por combinación de icono, tamaño y color."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, int, str], ctk.CTkImage] = {}

    def get(self, name: str, size: int, color: str) -> ctk.CTkImage:
        key = (name, size, color)
        cached = self._cache.get(key)
        if cached is None:
            drawn = icons.render(name, size, color)
            cached = ctk.CTkImage(light_image=drawn, dark_image=drawn, size=(size, size))
            self._cache[key] = cached
        return cached


class StatusCard(ctk.CTkFrame):
    """Tarjeta de resumen de la fila superior."""

    def __init__(self, master: Any, title: str, icon: ctk.CTkImage, icon_background: str) -> None:
        super().__init__(
            master,
            fg_color=theme.SURFACE_ALT,
            border_color=theme.BORDER,
            border_width=1,
            corner_radius=10,
        )
        self.grid_columnconfigure(1, weight=1)

        icon_box = ctk.CTkFrame(
            self, width=54, height=54, fg_color=icon_background, corner_radius=10
        )
        icon_box.grid(row=0, column=0, rowspan=2, padx=(16, 14), pady=(16, 0))
        icon_box.grid_propagate(False)
        ctk.CTkLabel(icon_box, text="", image=icon).place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            self,
            text=title,
            font=ctk.CTkFont(size=15),
            text_color=theme.TEXT,
            anchor="w",
        ).grid(row=0, column=1, sticky="sw", padx=(0, 14), pady=(17, 0))
        self.value_label = ctk.CTkLabel(
            self,
            text="--",
            font=ctk.CTkFont(size=27, weight="bold"),
            text_color=theme.TEXT,
            anchor="w",
        )
        self.value_label.grid(row=1, column=1, sticky="nw", padx=(0, 14))
        self.status_label = ctk.CTkLabel(
            self,
            text="● Sin analizar",
            font=ctk.CTkFont(size=12),
            text_color=theme.MUTED,
            anchor="w",
        )
        self.status_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=17, pady=(6, 14))

    def update_result(self, value: str, status: HealthStatus, label: str | None = None) -> None:
        self.value_label.configure(text=value)
        self.status_label.configure(
            text=f"● {label or STATUS_LABELS[status]}", text_color=STATUS_COLORS[status]
        )


class MatrixRow(ctk.CTkFrame):
    """Una fila de la matriz de diagnóstico."""

    def __init__(
        self,
        master: Any,
        component: ComponentKind,
        name: str,
        icon: ctk.CTkImage,
        striped: bool,
        on_click: Callable[[ComponentKind], None],
    ) -> None:
        self.base_color = theme.ROW_ALT if striped else theme.ROW
        super().__init__(master, fg_color=self.base_color, corner_radius=6, height=44)
        self.component = component
        self.on_click = on_click
        self.selected = False
        self.grid_propagate(False)
        _configure_matrix_columns(self)

        cells: list[ctk.CTkLabel] = []
        contents: tuple[tuple[str, ctk.CTkImage | None], ...] = (
            (f"   {name}", icon),
            ("—", None),
            ("● Sin analizar", None),
            ("—", None),
        )
        for index, (text, image) in enumerate(contents):
            label = ctk.CTkLabel(
                self,
                text=text,
                image=image,
                compound="left",
                anchor="w",
                justify="left",
                width=1,
                font=ctk.CTkFont(size=12),
                text_color=theme.MUTED if index == 2 else theme.TEXT,
            )
            label.grid(row=0, column=index, sticky="ew", padx=(14 if index == 0 else 10, 8))
            cells.append(label)
        self.cells = cells

        for widget in (self, *cells):
            widget.bind("<Button-1>", self._clicked)
            widget.bind("<Enter>", self._entered)
            widget.bind("<Leave>", self._left)

    def _clicked(self, _event: Any) -> None:
        self.on_click(self.component)

    def _entered(self, _event: Any) -> None:
        if not self.selected:
            self.configure(fg_color=theme.SURFACE_HOVER)

    def _left(self, _event: Any) -> None:
        if not self.selected:
            self.configure(fg_color=self.base_color)

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self.configure(fg_color=theme.ACCENT if selected else self.base_color)

    def update_result(self, result: ComponentResult) -> None:
        self.cells[1].configure(text=result.summary)
        self.cells[2].configure(
            text=f"● {STATUS_LABELS[result.status]}", text_color=STATUS_COLORS[result.status]
        )
        self.cells[3].configure(text=result.possible_problem or "—")


class MatrixTable(ctk.CTkFrame):
    """Tabla de diagnóstico con icono por componente y estado coloreado."""

    def __init__(self, master: Any, on_select: Callable[[ComponentKind], None]) -> None:
        super().__init__(
            master,
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
            border_width=1,
            corner_radius=10,
        )
        self.on_select = on_select
        self.rows: dict[ComponentKind, MatrixRow] = {}
        self.selected: ComponentKind | None = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color=theme.SURFACE_ALT, corner_radius=8)
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        _configure_matrix_columns(header)
        for index, (title, _, _) in enumerate(MATRIX_COLUMNS):
            ctk.CTkLabel(
                header,
                text=title,
                anchor="w",
                width=1,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=theme.TEXT,
            ).grid(row=0, column=index, sticky="ew", padx=(14 if index == 0 else 10, 8), pady=10)

        self.body = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=theme.BORDER,
            scrollbar_button_hover_color=theme.ACCENT,
        )
        self.body.grid(row=1, column=0, sticky="nsew", padx=(6, 2), pady=(0, 10))
        self.body.grid_columnconfigure(0, weight=1)

    def add_row(self, component: ComponentKind, name: str, icon: ctk.CTkImage) -> None:
        row = MatrixRow(self.body, component, name, icon, len(self.rows) % 2 == 1, self.on_select)
        row.grid(row=len(self.rows), column=0, sticky="ew", pady=1)
        self.rows[component] = row

    def select(self, component: ComponentKind) -> None:
        self.selected = component
        for kind, row in self.rows.items():
            row.set_selected(kind is component)

    def update_result(self, result: ComponentResult) -> None:
        row = self.rows.get(result.component)
        if row is not None:
            row.update_result(result)


class EvidenceWindow(ctk.CTkToplevel):
    """Evidencia tecnica a pantalla completa, para leer salidas largas sin recortes."""

    def __init__(self, master: Any, heading: str, body: str, expand_icon: ctk.CTkImage) -> None:
        super().__init__(master, fg_color=theme.BACKGROUND)
        self.title("Evidencia técnica")
        self.geometry("1280x820")
        self.minsize(640, 400)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 10))
        bar.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            bar,
            text="  EVIDENCIA TÉCNICA",
            image=expand_icon,
            compound="left",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=theme.ACCENT_TEXT,
        ).grid(row=0, column=0, sticky="w")
        self.heading = ctk.CTkLabel(
            bar,
            text=heading,
            font=ctk.CTkFont(size=12),
            text_color=theme.MUTED,
            anchor="w",
            width=1,
        )
        self.heading.grid(row=0, column=1, sticky="ew", padx=16)
        ctk.CTkButton(
            bar,
            text="Copiar",
            width=104,
            height=32,
            corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color=theme.SURFACE_HOVER,
            hover_color=theme.ACCENT,
            command=self.copy_evidence,
        ).grid(row=0, column=2, sticky="e", padx=(0, 8))
        ctk.CTkButton(
            bar,
            text="Cerrar  (Esc)",
            width=118,
            height=32,
            corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.SURFACE_HOVER,
            border_width=1,
            border_color=theme.BORDER,
            command=self.destroy,
        ).grid(row=0, column=3, sticky="e")

        self.console = ctk.CTkTextbox(
            self,
            fg_color=theme.TERMINAL,
            border_color=theme.BORDER,
            border_width=1,
            corner_radius=10,
            text_color=theme.CONSOLE_TEXT,
            font=ctk.CTkFont(family="Consolas", size=13),
            wrap="none",
        )
        self.console.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        _configure_console_tags(self.console)
        _fill_console(self.console, body)

        self.bind("<Escape>", lambda _event: self.destroy())
        self.transient(master)
        # `zoomed` llena la pantalla conservando los botones de ventana; el modo
        # fullscreen puro los oculta y deja al usuario sin salida visible.
        self.after(10, lambda: self.state("zoomed"))
        self.after(20, self.focus)

    def update_content(self, heading: str, body: str) -> None:
        self.heading.configure(text=heading)
        _fill_console(self.console, body)

    def copy_evidence(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.console.get("1.0", "end-1c"))


class HardwareAdminApp(ctk.CTk):
    def __init__(
        self,
        scan_service: ScanService,
        monitoring_service: MonitoringService | None = None,
    ) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        super().__init__(fg_color=theme.BACKGROUND)
        self.scan_service = scan_service
        self.monitoring_service = monitoring_service or MonitoringService(
            sampler=PsutilRateSampler()
        )
        self.monitoring_job: str | None = None
        self.report: DiagnosticReport | None = None
        self.selected_component = ComponentKind.SYSTEM
        self.scan_running = False
        self.scan_scope: ComponentKind | None = None
        self.symptom_var = ctk.StringVar()
        # Indexados por clave: el valor del componente o el nombre de la acción.
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.active_nav_key = ComponentKind.SYSTEM.value
        self.results_by_kind: dict[ComponentKind, ComponentResult] = {}
        self.cards: dict[ComponentKind, StatusCard] = {}
        self.worker_events: Queue[tuple[str, Any]] = Queue()
        self.evidence_window: EvidenceWindow | None = None
        self.icons = IconCache()
        self.nav_font = ctk.CTkFont(size=13)
        self.nav_font_selected = ctk.CTkFont(size=13, weight="bold")

        self.title("Administrador de Hardware")
        icon_path = resource_path("assets", "app-icon.ico")
        if icon_path.exists():
            self.iconbitmap(default=str(icon_path))
        # La navegación es desplazable, así que la ventana puede encogerse hasta
        # caber en la pantalla objetivo con cualquiera de los escalados soportados.
        geometry, smallest = fit_window(
            self.winfo_screenwidth(),
            self.winfo_screenheight(),
            scaling=ctk.ScalingTracker.get_window_scaling(self),
        )
        self.geometry(f"{geometry[0]}x{geometry[1]}")
        self.minsize(*smallest)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_body()
        self._render_initial_matrix()
        self.select_component(ComponentKind.SYSTEM)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, height=100, corner_radius=0, fg_color=theme.BACKGROUND)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        header.grid_rowconfigure(1, weight=1)
        header.grid_propagate(False)

        logo_box = ctk.CTkFrame(header, width=60, height=60, fg_color="transparent")
        logo_box.grid(row=0, column=0, rowspan=2, padx=(24, 16), pady=(18, 0))
        logo_box.grid_propagate(False)
        logo_path = resource_path("assets", "app-icon.png")
        self.header_icon_image = ctk.CTkImage(
            light_image=Image.open(logo_path),
            dark_image=Image.open(logo_path),
            size=(58, 58),
        )
        ctk.CTkLabel(logo_box, text="", image=self.header_icon_image).place(
            relx=0.5, rely=0.5, anchor="center"
        )

        ctk.CTkLabel(
            header,
            text="ADMINISTRADOR DE HARDWARE",
            font=ctk.CTkFont(size=25, weight="bold"),
            text_color=theme.TEXT,
        ).grid(row=0, column=1, sticky="sw", pady=(20, 0))
        ctk.CTkLabel(
            header,
            text="Diagnóstico y estado del equipo",
            font=ctk.CTkFont(size=14),
            text_color=theme.MUTED,
        ).grid(row=1, column=1, sticky="nw", pady=(2, 0))

        self.status_pill = ctk.CTkFrame(header, corner_radius=8, border_width=1)
        self.status_pill.grid(row=0, column=2, padx=(12, 26), pady=(22, 0), sticky="e")
        self.status_icon = ctk.CTkLabel(self.status_pill, text="")
        self.status_icon.grid(row=0, column=0, padx=(13, 8), pady=8)
        self.global_status = ctk.CTkLabel(
            self.status_pill, text="Sin analizar", font=ctk.CTkFont(size=13, weight="bold")
        )
        self.global_status.grid(row=0, column=1, padx=(0, 15), pady=8)
        self._set_global_status("idle", "Sin analizar")

        self.last_scan_label = ctk.CTkLabel(
            header, text="Último análisis: —", text_color=theme.MUTED, font=ctk.CTkFont(size=11)
        )
        self.last_scan_label.grid(row=1, column=2, padx=(12, 27), pady=(2, 0), sticky="ne")

        separator = ctk.CTkFrame(header, height=1, corner_radius=0, fg_color=theme.BORDER_SOFT)
        separator.grid(row=2, column=0, columnspan=3, sticky="sew")

    def _set_global_status(self, state: str, text: str) -> None:
        background, border, color = theme.PILL_STYLES[state]
        self.status_pill.configure(fg_color=background, border_color=border)
        self.status_icon.configure(image=self.icons.get("check", 17, color), fg_color=background)
        self.global_status.configure(text=text, text_color=color, fg_color=background)

    def _build_body(self) -> None:
        body = ctk.CTkFrame(self, corner_radius=0, fg_color=theme.BACKGROUND)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        self._build_sidebar(body)
        self._build_content(body)

    def _build_sidebar(self, master: Any) -> None:
        sidebar = ctk.CTkFrame(master, width=300, corner_radius=0, fg_color=theme.SURFACE)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_rowconfigure(1, weight=1)
        sidebar.grid_propagate(False)

        ctk.CTkLabel(
            sidebar,
            text="OPCIONES",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=theme.ACCENT_TEXT,
        ).grid(row=0, column=0, sticky="w", padx=22, pady=(18, 10))

        navigation = ctk.CTkScrollableFrame(
            sidebar,
            width=262,
            fg_color="transparent",
            scrollbar_button_color=theme.BORDER,
            scrollbar_button_hover_color=theme.ACCENT,
        )
        navigation.grid(row=1, column=0, sticky="nsew", padx=(12, 6))
        navigation.grid_columnconfigure(0, weight=1)

        for row, entry in enumerate(NAV_ITEMS):
            icon_name, label, component = entry.icon, entry.label, entry.component
            command = (
                partial(self.select_component, component)
                if component is not None
                else partial(self.run_action, entry.action or "")
            )
            button = ctk.CTkButton(
                navigation,
                text=f"   {label}",
                image=self.icons.get(icon_name, 20, theme.ICON),
                compound="left",
                command=command,
                height=46,
                corner_radius=8,
                anchor="w",
                font=self.nav_font,
                fg_color=theme.SURFACE_ALT,
                hover_color=theme.SURFACE_HOVER,
                border_width=0,
                text_color=theme.TEXT,
            )
            button.grid(row=row, column=0, sticky="ew", pady=3)
            self.nav_buttons[component.value if component is not None else entry.action or ""] = (
                button
            )

        symptom_box = ctk.CTkFrame(sidebar, fg_color="transparent")
        symptom_box.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        symptom_box.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            symptom_box,
            text="SÍNTOMA OBSERVADO (OPCIONAL)",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=theme.ACCENT_TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        self.symptom_entry = ctk.CTkEntry(
            symptom_box,
            textvariable=self.symptom_var,
            placeholder_text="p. ej. el equipo se reinicia al jugar",
            height=38,
            corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color=theme.SURFACE_ALT,
            border_color=theme.BORDER,
            text_color=theme.TEXT,
        )
        self.symptom_entry.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        self.scan_button = ctk.CTkButton(
            sidebar,
            text="ANALIZAR EQUIPO",
            image=self.icons.get("refresh", 20, "#FFFFFF"),
            compound="left",
            command=self.start_scan,
            height=58,
            corner_radius=10,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER,
        )
        self.scan_button.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 16))

    def _build_content(self, master: Any) -> None:
        content = ctk.CTkFrame(master, corner_radius=0, fg_color=theme.BACKGROUND)
        content.grid(row=0, column=1, sticky="nsew", padx=28, pady=18)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(2, weight=1)

        title_row = ctk.CTkFrame(content, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        title_row.grid_columnconfigure(1, weight=1)
        self.section_title = ctk.CTkLabel(
            title_row,
            text="DIAGNÓSTICO GENERAL",
            font=ctk.CTkFont(size=19, weight="bold"),
            text_color=theme.TEXT,
        )
        self.section_title.grid(row=0, column=0, sticky="w")
        self.progress_label = ctk.CTkLabel(
            title_row, text="", text_color=theme.MUTED, font=ctk.CTkFont(size=12)
        )
        self.progress_label.grid(row=0, column=1, sticky="e", padx=(12, 14))
        self.battery_report_button = ctk.CTkButton(
            title_row,
            text="Reporte de batería",
            image=self.icons.get("report", 16, theme.ACCENT_TEXT),
            compound="left",
            command=self.request_battery_report,
            height=34,
            width=180,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.SURFACE_HOVER,
            border_width=1,
            border_color=theme.BORDER,
            text_color=theme.ACCENT_TEXT,
        )
        self.battery_report_button.grid(row=0, column=2, sticky="e", padx=(0, 10))

        self.section_button = ctk.CTkButton(
            title_row,
            text="Analizar sistema",
            image=self.icons.get("refresh", 16, theme.ACCENT_TEXT),
            compound="left",
            command=self.scan_selected_component,
            height=34,
            width=208,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.SURFACE_HOVER,
            border_width=1,
            border_color=theme.BORDER,
            text_color=theme.ACCENT_TEXT,
        )
        self.section_button.grid(row=0, column=3, sticky="e")

        cards_frame = ctk.CTkFrame(content, fg_color="transparent")
        cards_frame.grid(row=1, column=0, sticky="ew", pady=(0, 18))
        for column in range(4):
            cards_frame.grid_columnconfigure(column, weight=1, uniform="cards")

        card_specs = (
            (ComponentKind.CPU, "CPU"),
            (ComponentKind.MEMORY, "RAM"),
            (ComponentKind.DISK, "Disco"),
            (ComponentKind.NETWORK, "Red"),
        )
        for column, (kind, title) in enumerate(card_specs):
            card = StatusCard(
                cards_frame,
                title,
                self.icons.get(ICON_NAMES[kind], 26, theme.COMPONENT_COLORS[kind]),
                theme.CARD_ICON_BACKGROUNDS[kind],
            )
            card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 7, 7))
            self.cards[kind] = card

        workspace = ctk.CTkFrame(content, fg_color="transparent")
        self.workspace = workspace
        workspace.grid(row=2, column=0, sticky="nsew")
        workspace.grid_rowconfigure(0, weight=1)
        workspace.grid_columnconfigure(0, weight=3, minsize=480)
        workspace.grid_columnconfigure(1, weight=2, minsize=310)
        self._build_diagnostic_column(workspace)
        self._build_evidence_console(workspace)
        self._build_action_view(content)
        self._build_monitoring_panel(content)
        self._build_section_charts(content)

    def _build_action_view(self, master: Any) -> None:
        """Área principal de los apartados que no son componentes.

        Ocupa el mismo hueco que la matriz y la sustituye, para que al pulsar
        Conectividad o Recomendaciones el cambio se vea en el centro de la
        pantalla y no sólo en el título.
        """
        panel = ctk.CTkFrame(
            master,
            fg_color=theme.SURFACE,
            corner_radius=12,
            border_width=1,
            border_color=theme.BORDER,
        )
        panel.grid(row=2, column=0, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(0, weight=1)
        self.action_view = panel

        self.action_text = ctk.CTkTextbox(
            panel,
            fg_color=theme.TERMINAL,
            text_color=theme.CONSOLE_TEXT,
            font=ctk.CTkFont(family="Consolas", size=12),
            corner_radius=8,
            wrap="none",
        )
        self.action_text.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
        self.action_text.configure(state="disabled")
        panel.grid_remove()

    def _build_monitoring_panel(self, master: Any) -> None:
        """Panel de E/S en vivo: oculto salvo en el apartado de monitorizacion."""
        panel = ctk.CTkFrame(master, fg_color="transparent")
        panel.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        panel.grid_columnconfigure(0, weight=1)
        self.monitoring_panel = panel

        controls = ctk.CTkFrame(panel, fg_color="transparent")
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        controls.grid_columnconfigure(3, weight=1)
        self.monitoring_start_button = ctk.CTkButton(
            controls,
            text="Iniciar",
            command=self.start_monitoring,
            width=110,
            height=32,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER,
        )
        self.monitoring_start_button.grid(row=0, column=0)
        self.monitoring_stop_button = ctk.CTkButton(
            controls,
            text="Detener",
            command=self.stop_monitoring,
            width=110,
            height=32,
            corner_radius=8,
            state="disabled",
            font=ctk.CTkFont(size=12),
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.SURFACE_HOVER,
            border_width=1,
            border_color=theme.BORDER,
            text_color=theme.TEXT,
        )
        self.monitoring_stop_button.grid(row=0, column=1, padx=8)
        self.monitoring_clear_button = ctk.CTkButton(
            controls,
            text="Limpiar",
            command=self.clear_monitoring,
            width=110,
            height=32,
            corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.SURFACE_HOVER,
            border_width=1,
            border_color=theme.BORDER,
            text_color=theme.TEXT,
        )
        self.monitoring_clear_button.grid(row=0, column=2)
        self.monitoring_status = ctk.CTkLabel(
            controls,
            text="Detenido · 0 muestras",
            text_color=theme.MUTED,
            font=ctk.CTkFont(size=11),
        )
        self.monitoring_status.grid(row=0, column=3, sticky="e")

        self.disk_chart = TimeSeriesChart(panel, "DISCO", MONITORING_DISK_SPECS)
        self.disk_chart.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.net_chart = TimeSeriesChart(panel, "RED", MONITORING_NET_SPECS)
        self.net_chart.grid(row=2, column=0, sticky="ew")
        panel.grid_remove()

    def _build_section_charts(self, master: Any) -> None:
        """Un panel de graficos por apartado, en el mismo hueco que la fila 3."""
        self.section_panels: dict[ComponentKind, ctk.CTkFrame] = {}

        cpu_panel = ctk.CTkFrame(master, fg_color="transparent")
        cpu_panel.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        cpu_panel.grid_columnconfigure(1, weight=1)
        self.cpu_gauge = GaugeChart(cpu_panel, "USO TOTAL")
        self.cpu_gauge.grid(row=0, column=0, sticky="nw", padx=(0, 12))
        self.cpu_cores = BarListChart(cpu_panel, "USO POR NÚCLEO LÓGICO")
        self.cpu_cores.grid(row=0, column=1, sticky="new")
        cpu_panel.grid_remove()
        self.section_panels[ComponentKind.CPU] = cpu_panel

        memory_panel = ctk.CTkFrame(master, fg_color="transparent")
        memory_panel.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        memory_panel.grid_columnconfigure(1, weight=1)
        self.memory_gauge = GaugeChart(memory_panel, "USO DE MEMORIA")
        self.memory_gauge.grid(row=0, column=0, sticky="nw", padx=(0, 12))
        self.memory_bars = BarListChart(memory_panel, "ASIGNACIÓN DE CAPACIDAD")
        self.memory_bars.grid(row=0, column=1, sticky="new")
        memory_panel.grid_remove()
        self.section_panels[ComponentKind.MEMORY] = memory_panel

        disk_panel = ctk.CTkFrame(master, fg_color="transparent")
        disk_panel.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        disk_panel.grid_columnconfigure(0, weight=1)
        self.disk_bars = BarListChart(disk_panel, "ESPACIO OCUPADO POR UNIDAD")
        self.disk_bars.grid(row=0, column=0, sticky="ew")
        disk_panel.grid_remove()
        self.section_panels[ComponentKind.DISK] = disk_panel

        network_panel = ctk.CTkFrame(master, fg_color="transparent")
        network_panel.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        network_panel.grid_columnconfigure(0, weight=1)
        self.network_bars = BarListChart(network_panel, "VELOCIDAD DE ENLACE POR ADAPTADOR")
        self.network_bars.grid(row=0, column=0, sticky="ew")
        network_panel.grid_remove()
        self.section_panels[ComponentKind.NETWORK] = network_panel

    def _draw_section_charts(self, component: ComponentKind) -> None:
        """Dibuja el panel del apartado con lo ultimo analizado, si lo hay."""
        result = self.results_by_kind.get(component)
        facts: dict[str, Any] = dict(result.facts) if result else {}
        color = _status_color(result.status) if result else theme.MUTED

        if component is ComponentKind.CPU:
            usage = float(facts.get("_uso", 0.0))
            self.cpu_gauge.update_value(usage, str(facts.get("Modelo", ""))[:38], color)
            self.cpu_cores.update_bars(core_bars(facts))
        elif component is ComponentKind.MEMORY:
            usage = float(facts.get("_uso", 0.0))
            raw_memory = facts.get("_memoria")
            memory: dict[str, Any] = raw_memory if isinstance(raw_memory, dict) else {}
            self.memory_gauge.update_value(usage, str(facts.get("Total", "")), color)
            used = float(memory.get("usada", 0.0))
            available = float(memory.get("disponible", 0.0))
            total = float(memory.get("total", 0.0))
            bars = (
                [
                    Bar("En uso", used / total, format_bytes(used), color),
                    Bar("Disponible", available / total, format_bytes(available), theme.GREEN),
                ]
                if total > 0
                else []
            )
            self.memory_bars.update_bars(bars, format_bytes(total) if total else "")
        elif component is ComponentKind.DISK:
            self.disk_bars.update_bars(volume_bars(facts), str(facts.get("Resumen tecnológico", "")))
        elif component is ComponentKind.NETWORK:
            self.network_bars.update_bars(adapter_bars(facts))

    def start_monitoring(self) -> None:
        self.monitoring_service.start()
        self.monitoring_start_button.configure(state="disabled")
        self.monitoring_stop_button.configure(state="normal")
        self._refresh_monitoring()

    def stop_monitoring(self) -> None:
        self.monitoring_service.stop()
        self.monitoring_start_button.configure(state="normal")
        self.monitoring_stop_button.configure(state="disabled")
        if self.monitoring_job is not None:
            self.after_cancel(self.monitoring_job)
            self.monitoring_job = None
        self._draw_monitoring()

    def clear_monitoring(self) -> None:
        self.monitoring_service.clear()
        self._draw_monitoring()

    def _refresh_monitoring(self) -> None:
        """Redibuja mientras haya muestreo. Solo corre en el hilo principal."""
        self._draw_monitoring()
        if self.monitoring_service.is_running:
            self.monitoring_job = self.after(1000, self._refresh_monitoring)

    def _draw_monitoring(self) -> None:
        samples = self.monitoring_service.snapshot()
        read, write, sent, recv = series_for(samples)
        summary = self.monitoring_service.summary()
        disk_peak = max(summary.disk_read.peak, summary.disk_write.peak)
        net_peak = max(summary.net_sent.peak, summary.net_recv.peak)
        self.disk_chart.update_series((read, write), f"pico {format_rate(disk_peak)}")
        self.net_chart.update_series((sent, recv), f"pico {format_rate(net_peak)}")
        state = "Muestreando" if self.monitoring_service.is_running else "Detenido"
        self.monitoring_status.configure(
            text=f"{state} · {len(samples)}/{self.monitoring_service.capacity} muestras · 1 s"
        )

    def _on_close(self) -> None:
        """Detiene el muestreo antes de cerrar para no dejar el hilo colgado."""
        self.monitoring_service.stop()
        self.destroy()

    def _build_diagnostic_column(self, master: Any) -> None:
        left = ctk.CTkFrame(master, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            left,
            text="MATRIZ DE DIAGNÓSTICO",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=theme.TEXT,
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        self.matrix = MatrixTable(left, self.select_component)
        self.matrix.grid(row=1, column=0, sticky="nsew")

        conclusion = ctk.CTkFrame(
            left,
            fg_color=theme.SURFACE_ALT,
            border_color="#1E4E86",
            border_width=1,
            corner_radius=10,
        )
        conclusion.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        conclusion.grid_columnconfigure(1, weight=1)

        info_box = ctk.CTkFrame(
            conclusion, width=46, height=46, fg_color="#12365F", corner_radius=10
        )
        info_box.grid(row=0, column=0, rowspan=3, padx=(16, 14), pady=16)
        info_box.grid_propagate(False)
        ctk.CTkLabel(info_box, text="", image=self.icons.get("info", 26, theme.ACCENT_TEXT)).place(
            relx=0.5, rely=0.5, anchor="center"
        )

        ctk.CTkLabel(
            conclusion,
            text="CONCLUSIÓN DEL DIAGNÓSTICO",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=theme.ACCENT_TEXT,
        ).grid(row=0, column=1, sticky="sw", pady=(16, 4))
        self.conclusion_label = ctk.CTkLabel(
            conclusion,
            text="Analice una sección o el equipo completo para recopilar evidencia.",
            font=ctk.CTkFont(size=12),
            text_color=theme.TEXT,
            justify="left",
            anchor="nw",
            wraplength=620,
        )
        self.conclusion_label.grid(row=1, column=1, sticky="new")
        ctk.CTkButton(
            conclusion,
            text="Guardar evidencia",
            image=self.icons.get("save", 16, theme.TEXT),
            compound="left",
            command=self.export_report,
            height=32,
            width=190,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=theme.SURFACE_HOVER,
            hover_color=theme.ACCENT,
        ).grid(row=2, column=1, sticky="e", padx=(0, 16), pady=(10, 16))

    def _build_evidence_console(self, master: Any) -> None:
        panel = ctk.CTkFrame(
            master,
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
            border_width=1,
            corner_radius=10,
        )
        panel.grid(row=0, column=1, sticky="nsew")
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 8))
        header.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(
            header,
            text="EVIDENCIA TÉCNICA",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=theme.ACCENT_TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            header,
            text="",
            image=self.icons.get("expand", 15, theme.ACCENT_TEXT),
            width=34,
            height=30,
            corner_radius=8,
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.SURFACE_HOVER,
            border_width=1,
            border_color=theme.BORDER,
            command=self.open_evidence_window,
        ).grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.console_indicator = ctk.CTkLabel(
            header, text="●", font=ctk.CTkFont(size=14), text_color=theme.MUTED
        )
        self.console_indicator.grid(row=0, column=2, sticky="e", padx=(0, 10))
        ctk.CTkButton(
            header,
            text="Copiar",
            image=self.icons.get("copy", 15, theme.TEXT),
            compound="left",
            width=108,
            height=30,
            corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color=theme.SURFACE_HOVER,
            hover_color=theme.ACCENT,
            command=self.copy_evidence,
        ).grid(row=0, column=3, sticky="e")

        self.console = ctk.CTkTextbox(
            panel,
            fg_color=theme.TERMINAL,
            border_color=theme.BORDER,
            border_width=1,
            corner_radius=8,
            text_color=theme.CONSOLE_TEXT,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="none",
        )
        self.console.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        _configure_console_tags(self.console)
        self._set_console(
            "ADMINISTRADOR DE HARDWARE\n"
            "La evidencia de las consultas aparecerá aquí.\n\n"
            "> Estado\nEsperando análisis..."
        )

        footer = ctk.CTkFrame(panel, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 11))
        footer.grid_columnconfigure(0, weight=1)
        self.console_context = ctk.CTkLabel(
            footer,
            text="Componente seleccionado",
            text_color=theme.MUTED,
            font=ctk.CTkFont(size=11),
            anchor="w",
            width=1,
        )
        self.console_context.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            footer,
            text=" Salida de solo lectura",
            image=self.icons.get("lock", 13, theme.MUTED),
            compound="left",
            text_color=theme.MUTED,
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=1, sticky="e")

    def _render_initial_matrix(self) -> None:
        for entry in NAV_ITEMS:
            component = entry.component
            if component is None:
                continue
            self.matrix.add_row(
                component,
                entry.label.split(". ", 1)[-1],
                self.icons.get(entry.icon, 17, theme.COMPONENT_COLORS[component]),
            )

    def run_action(self, action: str) -> None:
        """Ejecuta una entrada del menú que no corresponde a un componente."""
        if action == "connectivity":
            self.show_connectivity()
        elif action == "recommendations":
            self.show_recommendations()
        elif action == "report":
            self.show_report()
        elif action == "export":
            self.export_report()
        elif action == "exit":
            self._on_close()

    def _show_action_view(self, action: str, title: str, body: str) -> None:
        """Presenta un apartado que no es un componente."""
        self._highlight_nav(action)
        self.section_title.configure(text=title)
        self.monitoring_panel.grid_remove()
        for panel in self.section_panels.values():
            panel.grid_remove()
        self.workspace.grid_remove()
        self.action_view.grid()
        self.action_text.configure(state="normal")
        self.action_text.delete("1.0", "end")
        self.action_text.insert("1.0", body)
        self.action_text.configure(state="disabled")

    def show_report(self) -> None:
        """Vista del reporte completo. No guarda nada: eso es «Exportar»."""
        report = self.report
        if report is None:
            self._show_action_view(
                "report",
                "REPORTE DE DIAGNÓSTICO",
                "Todavía no hay diagnóstico." + NL + NL
                + "Ejecute «Analizar equipo» o el análisis de una sección concreta.",
            )
            return

        lines = [
            "REPORTE DE DIAGNÓSTICO",
            "======================",
            "",
            f"Inicio:  {report.started_at.astimezone():%Y-%m-%d %H:%M:%S}",
            f"Fin:     {report.completed_at.astimezone():%Y-%m-%d %H:%M:%S}",
            f"Equipo:  {socket.gethostname()}",
            "",
        ]
        if report.symptom:
            lines.extend([f"Síntoma reportado: {report.symptom}", ""])
        if report.expected_device:
            lines.extend([f"Dispositivo esperado: {report.expected_device}", ""])

        lines.extend(["MATRIZ DE DIAGNÓSTICO", "---------------------"])
        for result in report.results:
            estado = STATUS_LABELS[result.status]
            lines.append(f"  {result.name:<28} {estado:<16} {result.summary}")
            if result.possible_problem:
                lines.append(f"      posible problema: {result.possible_problem}")

        lines.extend(["", "CONCLUSIÓN", "----------", report.conclusion])

        if report.limitations:
            lines.extend(["", "LIMITACIONES", "------------"])
            lines.extend(f"  - {item}" for item in report.limitations)

        if report.recommendations:
            lines.extend(["", "RECOMENDACIONES", "---------------"])
            for number, item in enumerate(report.recommendations, start=1):
                marca = " (modifica el sistema)" if item.modifies_system else ""
                lines.append(f"  {number}. {item.title}{marca}")

        lines.extend(
            [
                "",
                "Use «15. Exportar diagnóstico» para guardar este reporte en disco.",
            ]
        )
        self._show_action_view("report", "REPORTE DE DIAGNÓSTICO", NL.join(lines))

    def show_connectivity(self) -> None:
        """Etapas de conectividad ya medidas por el servicio, sin volver a probar."""
        result = self.results_by_kind.get(ComponentKind.NETWORK)
        if result is None:
            self._show_action_view(
                "connectivity",
                "CONECTIVIDAD",
                "Sin datos de conectividad.\n\n"
                "Ejecute «Analizar equipo» o el análisis de la sección Red para "
                "obtener las pruebas escalonadas de adaptador, IP, puerta de enlace, "
                "acceso externo y resolución DNS.",
            )
            return

        lines = [
            "CONECTIVIDAD",
            "============",
            "",
            f"DIAGNÓSTICO: {result.facts.get('Diagnóstico de red', 'No disponible')}",
            "",
            "PRUEBAS ESCALONADAS",
            "-------------------",
        ]
        stages = result.facts.get("Conectividad")
        if isinstance(stages, list) and stages:
            for stage in stages:
                if not isinstance(stage, dict):
                    continue
                marca = "OK   " if stage.get("Resultado") == "OK" else "FALLO"
                lines.append(f"[{marca}] {stage.get('Etapa', '?')} -> {stage.get('Destino', '?')}")
                lines.append(f"         {stage.get('Detalle', '')}")
        else:
            lines.append("No se registraron etapas de conectividad.")

        recomendaciones = result.facts.get("Recomendaciones")
        if isinstance(recomendaciones, list) and recomendaciones:
            lines.extend(["", "SUGERENCIAS", "-----------"])
            lines.extend(f"  - {item}" for item in recomendaciones)

        lines.extend(
            [
                "",
                "NOTA: un ping sin respuesta puede reflejar ICMP bloqueado; el resultado",
                "no es concluyente sin pruebas complementarias.",
            ]
        )
        self._show_action_view("connectivity", "CONECTIVIDAD", "\n".join(lines))

    def show_recommendations(self) -> None:
        """Todos los procedimientos propuestos, ordenados por gravedad."""
        recommendations = self.report.recommendations if self.report else ()
        if not recommendations:
            self._show_action_view(
                "recommendations",
                "RECOMENDACIONES",
                "No hay recomendaciones.\n\n"
                "No se detectaron anomalías en los indicadores consultados ni se "
                "registró un síntoma. Esto no equivale a afirmar que el hardware "
                "esté libre de fallas: sólo que las comprobaciones realizadas no "
                "encontraron anomalías.",
            )
            return

        lines = ["RECOMENDACIONES", "===============", ""]
        for number, item in enumerate(recommendations, start=1):
            lines.append(f"{number}. {item.title}  [{item.component.value}]")
            lines.append(f"   Causa: {item.cause}")
            lines.append("")
            lines.append("   Pasos:")
            lines.extend(f"     {index}. {step}" for index, step in enumerate(item.steps, 1))
            lines.extend(["", f"   Fundamento: {item.rationale}"])
            lines.append(f"   Comprobación posterior: {item.verification}")
            lines.append(
                "   ! MODIFICA EL SISTEMA: la aplicación no ejecuta este "
                "procedimiento; lo aplica usted."
                if item.modifies_system
                else "   Sólo consulta: no altera el equipo."
            )
            lines.append("")
        self._show_action_view("recommendations", "RECOMENDACIONES", "\n".join(lines))

    def _highlight_nav(self, active_key: str) -> None:
        """Ilumina la entrada activa del menú, sea componente o acción.

        Antes sólo se resaltaban los componentes, así que pulsar Conectividad o
        Recomendaciones no encendía ningún botón y parecía que el clic se había
        ignorado.
        """
        self.active_nav_key = active_key
        for entry in NAV_ITEMS:
            key = entry.component.value if entry.component is not None else entry.action or ""
            button = self.nav_buttons.get(key)
            if button is None:
                continue
            chosen = key == active_key
            button.configure(
                fg_color=theme.ACCENT if chosen else theme.SURFACE_ALT,
                hover_color=theme.ACCENT_HOVER if chosen else theme.SURFACE_HOVER,
                image=self.icons.get(entry.icon, 20, "#FFFFFF" if chosen else theme.ICON),
                font=self.nav_font_selected if chosen else self.nav_font,
            )

    def select_component(self, component: ComponentKind) -> None:
        self.selected_component = component
        self._highlight_nav(component.value)
        self.action_view.grid_remove()
        self.workspace.grid()
        self.matrix.select(component)
        self.section_button.configure(text=f"Analizar {SECTION_NAMES[component]}")
        if component is ComponentKind.SYSTEM:
            self.battery_report_button.grid()
        else:
            self.battery_report_button.grid_remove()

        # Un unico hueco en la fila 3: el panel en vivo en E/S, y el de
        # graficos del apartado en CPU, RAM, discos y red.
        if component is ComponentKind.IO:
            self.monitoring_panel.grid()
            self._draw_monitoring()
        else:
            self.monitoring_panel.grid_remove()
        for kind, panel in self.section_panels.items():
            if kind is component:
                panel.grid()
                self._draw_section_charts(kind)
            else:
                panel.grid_remove()
        self._show_selected_evidence()

    def start_scan(self, only: ComponentKind | None = None) -> None:
        """Analiza el equipo completo, o sólo `only` si se indica un componente."""
        if self.scan_running:
            return
        self.scan_running = True
        self.scan_scope = only
        self.scan_button.configure(text="ANALIZANDO...", state="disabled")
        self.section_button.configure(state="disabled")
        self.symptom_entry.configure(state="disabled")
        self._set_global_status("busy", "Analizando")
        self.progress_label.configure(text="Iniciando comprobaciones...")
        worker = threading.Thread(
            target=self._run_scan, args=(only,), name="hardware-scan", daemon=True
        )
        worker.start()
        self.after(40, self._poll_worker_events)

    def scan_selected_component(self) -> None:
        self.start_scan(self.selected_component)

    def _run_scan(self, only: ComponentKind | None) -> None:
        scope = None if only is None else frozenset({only})
        symptom = self.symptom_var.get().strip() or None
        try:
            report = self.scan_service.scan(
                on_progress=self._publish_progress,
                only=scope,
                symptom=symptom,
            )
        except Exception as exc:  # noqa: BLE001 - frontera del hilo de trabajo.
            self.worker_events.put(("error", exc))
            return
        self.worker_events.put(("finished", report))

    def _publish_progress(self, current: int, total: int, name: str) -> None:
        self.worker_events.put(("progress", (current, total, name)))

    def _poll_worker_events(self) -> None:
        try:
            while True:
                event, payload = self.worker_events.get_nowait()
                if event == "progress":
                    current, total, name = payload
                    self.progress_label.configure(text=f"{current}/{total} · {name}")
                elif event == "finished":
                    self._scan_finished(payload)
                elif event == "error":
                    self._scan_failed(payload)
        except Empty:
            pass
        if self.scan_running or not self.worker_events.empty():
            self.after(40, self._poll_worker_events)

    def _merged_report(self) -> DiagnosticReport:
        """Reporte con todo lo analizado hasta ahora, sea parcial o completo."""
        results = tuple(
            self.results_by_kind[kind] for kind in COMPONENT_ORDER if kind in self.results_by_kind
        )
        symptom = self.symptom_var.get().strip() or None
        return self.scan_service.diagnostic_engine.build_report(results, symptom)

    def _scan_finished(self, report: DiagnosticReport) -> None:
        for result in report.results:
            self.results_by_kind[result.component] = result
            self.matrix.update_result(result)
        self.report = self._merged_report()
        # Refrescar el panel visible: sin esto los graficos seguirian mostrando
        # el analisis anterior hasta que el usuario cambiara de apartado.
        self._draw_section_charts(self.selected_component)
        self.scan_running = False
        self.scan_button.configure(text="ANALIZAR EQUIPO", state="normal")
        self.section_button.configure(state="normal")
        self.symptom_entry.configure(state="normal")

        checks = len(report.results)
        self.progress_label.configure(
            text="1 comprobación completada"
            if checks == 1
            else f"{checks} comprobaciones completadas"
        )
        timestamp = report.completed_at.astimezone().strftime("%H:%M:%S")
        self.last_scan_label.configure(text=f"Último análisis: {timestamp}")
        self._refresh_global_status()

        self.conclusion_label.configure(text=self._conclusion_text(self.report))
        self._update_cards()
        self._show_selected_evidence()

    @staticmethod
    def _conclusion_text(report: DiagnosticReport) -> str:
        """Evita que un análisis parcial se lea como un veredicto sobre todo el equipo."""
        analysed = len(report.results)
        total = len(COMPONENT_ORDER)
        if analysed >= total:
            return report.conclusion
        pending = total - analysed
        return (
            f"{report.conclusion} Este resultado cubre {analysed} de {total} comprobaciones: "
            f"quedan {pending} sin analizar."
        )

    def _refresh_global_status(self) -> None:
        report = self.report
        if report is None:
            self._set_global_status("idle", "Sin analizar")
        elif report.has_problems:
            self._set_global_status("warn", "Revisión necesaria")
        elif report.limitations:
            self._set_global_status("warn", "Análisis parcial")
        elif len(report.results) < len(COMPONENT_ORDER):
            self._set_global_status(
                "ok", f"{len(report.results)} de {len(COMPONENT_ORDER)} analizados"
            )
        else:
            self._set_global_status("ok", "Análisis completado")

    def _scan_failed(self, error: Exception) -> None:
        self.scan_running = False
        self.scan_button.configure(text="ANALIZAR EQUIPO", state="normal")
        self.section_button.configure(state="normal")
        self.symptom_entry.configure(state="normal")
        self._set_global_status("error", "Error")
        self.progress_label.configure(text="El análisis no pudo completarse")
        messagebox.showerror("Error de análisis", f"No fue posible completar el análisis:\n{error}")

    def _update_cards(self) -> None:
        for kind, card in self.cards.items():
            result = self.results_by_kind.get(kind)
            if result is None:
                continue
            label = None
            if kind is ComponentKind.NETWORK and result.status is HealthStatus.NORMAL:
                label = "Conectada"
            card.update_result(self._card_value(result), result.status, label)

    @staticmethod
    def _card_value(result: ComponentResult) -> str:
        if result.component in {ComponentKind.CPU, ComponentKind.MEMORY}:
            return result.summary.split(" ", 1)[0]
        if result.component is ComponentKind.DISK:
            parts = result.summary.split()
            return parts[1] if len(parts) > 1 else result.summary
        if result.component is ComponentKind.NETWORK:
            return HardwareAdminApp._network_value(result)
        return result.summary

    @staticmethod
    def _network_value(result: ComponentResult) -> str:
        adapters = result.facts.get("Adaptadores", [])
        speeds: list[int] = []
        connected = 0
        for adapter in adapters:
            if not isinstance(adapter, dict) or adapter.get("Estado") != "Conectado":
                continue
            connected += 1
            raw = str(adapter.get("Velocidad", ""))
            if raw.endswith(" Mbps"):
                try:
                    speeds.append(int(raw.removesuffix(" Mbps")))
                except ValueError:
                    continue
        if speeds:
            fastest = max(speeds)
            return f"{fastest // 1000} Gbps" if fastest >= 1000 else f"{fastest} Mbps"
        return f"{connected} activa(s)"

    def _show_selected_evidence(self) -> None:
        result = self.results_by_kind.get(self.selected_component)
        name = SECTION_NAMES[self.selected_component]
        if result is None:
            self.console_context.configure(text=f"Sin analizar · {name}")
            self.console_indicator.configure(text_color=theme.MUTED)
            self._set_console(
                f"> {self.selected_component.value}\n"
                f"Sin evidencia. Use «Analizar {name}» o ANALIZAR EQUIPO."
            )
            self._sync_evidence_window()
            return

        self.console_context.configure(text=f"Componente: {result.name}")
        self.console_indicator.configure(text_color=STATUS_COLORS[result.status])
        lines = [
            f"COMPONENTE: {result.name}",
            f"ESTADO: {STATUS_LABELS[result.status]}",
            f"RESUMEN: {result.summary}",
            "",
            "DATOS NORMALIZADOS",
            "-------------------",
        ]
        for key, value in result.facts.items():
            # Series numericas para los graficos: no son texto de la ficha.
            if str(key).startswith("_"):
                continue
            lines.append(f"{key}:")
            lines.append(_format_value(value, "  "))
            lines.append("")
        # Recomendaciones del componente seleccionado, antes de la evidencia cruda.
        applicable = [
            item
            for item in (self.report.recommendations if self.report else ())
            if item.component is result.component
        ]
        for item in applicable:
            lines.extend(["RECOMENDACIÓN", "--------------", item.title, ""])
            lines.append(f"Causa: {item.cause}")
            lines.append("")
            lines.append("Pasos:")
            lines.extend(f"  {number}. {step}" for number, step in enumerate(item.steps, 1))
            lines.extend(["", f"Fundamento: {item.rationale}"])
            lines.append(f"Comprobación posterior: {item.verification}")
            lines.append(
                "! Modifica el sistema: la aplicación no lo ejecuta, lo aplica usted."
                if item.modifies_system
                else "Sólo consulta: no altera el equipo."
            )
            lines.append("")

        lines.extend(["EVIDENCIA CRUDA", "---------------"])
        for evidence in result.evidence:
            marker = ">" if evidence.succeeded else "!"
            lines.extend(
                [
                    f"{marker} [{evidence.source}] {evidence.query}",
                    evidence.output or "Sin salida",
                    "",
                ]
            )
        self._set_console("\n".join(lines))
        self._sync_evidence_window()

    def _set_console(self, text: str) -> None:
        _fill_console(self.console, text)

    def open_evidence_window(self) -> None:
        """Abre la evidencia del componente seleccionado a pantalla completa."""
        heading = self.console_context.cget("text")
        body = self.console.get("1.0", "end-1c")
        window = self.evidence_window
        if window is not None and window.winfo_exists():
            window.update_content(heading, body)
            window.deiconify()
            window.lift()
            window.focus()
            return
        self.evidence_window = EvidenceWindow(
            self, heading, body, self.icons.get("expand", 17, theme.ACCENT_TEXT)
        )

    def _sync_evidence_window(self) -> None:
        window = self.evidence_window
        if window is not None and window.winfo_exists():
            window.update_content(
                self.console_context.cget("text"), self.console.get("1.0", "end-1c")
            )

    def copy_evidence(self) -> None:
        text = self.console.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        self.progress_label.configure(text="Evidencia copiada al portapapeles")

    def _write_report(self, destination: Path, include_identity: bool) -> Path:
        """Escribe el reporte en el formato que indica la extensión elegida."""
        assert self.report is not None
        suffix = destination.suffix.lower()
        if suffix == ".json":
            return export_json(self.report, destination, include_identity)
        if suffix == ".txt":
            return export_txt(self.report, destination, include_identity)
        return export_html(self.report, destination)

    def export_report(self) -> None:
        if self.report is None:
            messagebox.showinfo(
                "Sin diagnóstico", "Primero debe analizar al menos una sección del equipo."
            )
            return
        # El plan exige mostrar qué se incluye antes de guardar y permitir
        # anonimizar la copia que se comparte.
        include_identity = messagebox.askyesno(
            "Datos del equipo",
            "¿Incluir el nombre del equipo y del usuario en el reporte?"
            f"{NL}{NL}Elija «No» para guardar una copia anónima, apta para compartir."
            f"{NL}El resto del contenido es idéntico.",
            parent=self,
        )
        default_name = f"diagnostico-hardware-{datetime.now(UTC):%Y%m%d-%H%M}.html"
        destination = filedialog.asksaveasfilename(
            parent=self,
            title="Guardar reporte de diagnóstico",
            defaultextension=".html",
            initialfile=default_name,
            filetypes=(
                ("Reporte HTML", "*.html"),
                ("Datos JSON", "*.json"),
                ("Texto plano", "*.txt"),
                ("Todos los archivos", "*.*"),
            ),
        )
        if not destination:
            return
        try:
            path = self._write_report(Path(destination), include_identity)
        except OSError as exc:
            messagebox.showerror("No se pudo guardar", str(exc), parent=self)
            return
        self.progress_label.configure(text=f"Reporte guardado: {path.name}")
        messagebox.showinfo("Reporte generado", f"Reporte guardado en:\n{path}", parent=self)

    def request_battery_report(self) -> None:
        """Solicita y genera un reporte HTML detallado de batería vía powercfg."""
        proceed = messagebox.askokcancel(
            "Generar reporte de batería",
            "Esta acción ejecutará la herramienta nativa de Windows (powercfg /batteryreport)\n"
            "para generar un reporte HTML detallado del historial y salud de la batería.\n\n"
            "¿Desea continuar?",
            parent=self,
        )
        if not proceed:
            return

        default_name = f"battery-report-{datetime.now(UTC):%Y%m%d-%H%M}.html"
        destination = filedialog.asksaveasfilename(
            parent=self,
            title="Guardar reporte de batería",
            defaultextension=".html",
            initialfile=default_name,
            filetypes=(
                ("Reporte HTML", "*.html"),
                ("Todos los archivos", "*.*"),
            ),
        )
        if not destination:
            return

        target_path = Path(destination)
        if target_path.exists():
            overwrite = messagebox.askyesno(
                "Confirmar reemplazo",
                f"El archivo {target_path.name} ya existe.\n¿Desea reemplazarlo?",
                parent=self,
            )
            if not overwrite:
                return

        result = generate_battery_report(target_path)
        if result.exit_code == 0:
            self.progress_label.configure(text=f"Reporte de batería: {target_path.name}")
            messagebox.showinfo(
                "Reporte de batería generado",
                f"El reporte de batería se guardó con éxito en:\n{target_path}",
                parent=self,
            )
        else:
            err_msg = result.error.strip() or f"Código de salida: {result.exit_code}"
            messagebox.showerror(
                "Error al generar reporte",
                f"No se pudo generar el reporte de batería.\n\nDetalle: {err_msg}",
                parent=self,
            )

    def export_debug_state(self) -> str:
        """Representación estable usada por el smoke test, sin datos sensibles completos."""
        state = {
            "selected": self.selected_component.value,
            "has_report": self.report is not None,
            "navigation_items": len(NAV_ITEMS),
            "matrix_rows": len(self.matrix.rows),
        }
        return json.dumps(state, ensure_ascii=False, sort_keys=True)
