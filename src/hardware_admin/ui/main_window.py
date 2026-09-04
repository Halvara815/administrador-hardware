"""Ventana principal del Administrador de Hardware."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk
from PIL import Image

from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    DiagnosticReport,
    HealthStatus,
)
from hardware_admin.reports.html_report import export_html
from hardware_admin.resources import resource_path
from hardware_admin.services.scan_service import ScanService
from hardware_admin.ui import icons, theme

STATUS_LABELS = {
    HealthStatus.UNKNOWN: "Sin analizar",
    HealthStatus.NORMAL: "Normal",
    HealthStatus.WARNING: "Advertencia",
    HealthStatus.CRITICAL: "Problema",
    HealthStatus.ERROR: "Error de consulta",
}

STATUS_COLORS = theme.STATUS_COLORS

NAV_ITEMS: tuple[tuple[str, str, ComponentKind | None], ...] = (
    ("system", "1. Información del sistema", ComponentKind.SYSTEM),
    ("cpu", "2. CPU", ComponentKind.CPU),
    ("memory", "3. Memoria", ComponentKind.MEMORY),
    ("disk", "4. Discos", ComponentKind.DISK),
    ("network", "5. Red", ComponentKind.NETWORK),
    ("usb", "6. USB", ComponentKind.USB),
    ("pci", "7. PCI / PCIe", ComponentKind.PCI),
    ("driver", "8. Controladores", ComponentKind.DRIVER),
    ("problem_device", "9. Dispositivos con problemas", ComponentKind.PROBLEM_DEVICE),
    ("monitor_gpu", "10. Monitor y GPU", ComponentKind.MONITOR_GPU),
    ("io", "11. Monitorizar E/S", ComponentKind.IO),
    ("report", "12. Generar reporte", None),
)

#: Nombre corto de cada sección, usado en el botón de análisis independiente.
SECTION_NAMES: dict[ComponentKind, str] = {
    ComponentKind.SYSTEM: "sistema",
    ComponentKind.CPU: "CPU",
    ComponentKind.MEMORY: "memoria",
    ComponentKind.DISK: "discos",
    ComponentKind.NETWORK: "red",
    ComponentKind.USB: "USB",
    ComponentKind.PCI: "PCI",
    ComponentKind.DRIVER: "controladores",
    ComponentKind.PROBLEM_DEVICE: "dispositivos",
    ComponentKind.MONITOR_GPU: "monitor y GPU",
    ComponentKind.IO: "E/S",
}

COMPONENT_ORDER: tuple[ComponentKind, ...] = tuple(
    component for _, _, component in NAV_ITEMS if component is not None
)

ICON_NAMES: dict[ComponentKind, str] = {
    component: icon for icon, _, component in NAV_ITEMS if component is not None
}

#: Título, peso y ancho mínimo de cada columna de la matriz de diagnóstico.
MATRIX_COLUMNS: tuple[tuple[str, int, int], ...] = (
    ("Componente", 26, 150),
    ("Evidencia", 25, 140),
    ("Estado", 18, 105),
    ("Posible problema", 31, 150),
)


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


class HardwareAdminApp(ctk.CTk):
    def __init__(self, scan_service: ScanService) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        super().__init__(fg_color=theme.BACKGROUND)
        self.scan_service = scan_service
        self.report: DiagnosticReport | None = None
        self.selected_component = ComponentKind.SYSTEM
        self.scan_running = False
        self.scan_scope: ComponentKind | None = None
        self.nav_buttons: dict[ComponentKind, ctk.CTkButton] = {}
        self.results_by_kind: dict[ComponentKind, ComponentResult] = {}
        self.cards: dict[ComponentKind, StatusCard] = {}
        self.worker_events: Queue[tuple[str, Any]] = Queue()
        self.icons = IconCache()
        self.nav_font = ctk.CTkFont(size=13)
        self.nav_font_selected = ctk.CTkFont(size=13, weight="bold")

        self.title("Administrador de Hardware")
        icon_path = resource_path("assets", "app-icon.ico")
        if icon_path.exists():
            self.iconbitmap(default=str(icon_path))
        self.geometry("1580x900")
        self.minsize(1180, 720)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_body()
        self._render_initial_matrix()
        self.select_component(ComponentKind.SYSTEM)

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

        for row, (icon_name, label, component) in enumerate(NAV_ITEMS):
            command = (
                self.export_report
                if component is None
                else partial(self.select_component, component)
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
            if component is not None:
                self.nav_buttons[component] = button

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
        self.scan_button.grid(row=2, column=0, sticky="ew", padx=16, pady=16)

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
        self.section_button.grid(row=0, column=2, sticky="e")

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
        workspace.grid(row=2, column=0, sticky="nsew")
        workspace.grid_rowconfigure(0, weight=1)
        workspace.grid_columnconfigure(0, weight=3, minsize=480)
        workspace.grid_columnconfigure(1, weight=2, minsize=310)
        self._build_diagnostic_column(workspace)
        self._build_evidence_console(workspace)

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
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            header,
            text="EVIDENCIA TÉCNICA",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=theme.ACCENT_TEXT,
        ).grid(row=0, column=0, sticky="w")
        self.console_indicator = ctk.CTkLabel(
            header, text="●", font=ctk.CTkFont(size=14), text_color=theme.MUTED
        )
        self.console_indicator.grid(row=0, column=1, sticky="e", padx=(0, 12))
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
        ).grid(row=0, column=2, sticky="e")

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
        self.console.tag_config("prompt", foreground=theme.CONSOLE_PROMPT)
        self.console.tag_config("key", foreground=theme.CONSOLE_KEY)
        self.console.tag_config("error", foreground=theme.CONSOLE_ERROR)
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
        for icon_name, label, component in NAV_ITEMS:
            if component is None:
                continue
            self.matrix.add_row(
                component,
                label.split(". ", 1)[-1],
                self.icons.get(icon_name, 17, theme.COMPONENT_COLORS[component]),
            )

    def select_component(self, component: ComponentKind) -> None:
        self.selected_component = component
        for kind, button in self.nav_buttons.items():
            chosen = kind is component
            button.configure(
                fg_color=theme.ACCENT if chosen else theme.SURFACE_ALT,
                hover_color=theme.ACCENT_HOVER if chosen else theme.SURFACE_HOVER,
                image=self.icons.get(ICON_NAMES[kind], 20, "#FFFFFF" if chosen else theme.ICON),
                font=self.nav_font_selected if chosen else self.nav_font,
            )
        self.matrix.select(component)
        self.section_button.configure(text=f"Analizar {SECTION_NAMES[component]}")
        self._show_selected_evidence()

    def start_scan(self, only: ComponentKind | None = None) -> None:
        """Analiza el equipo completo, o sólo `only` si se indica un componente."""
        if self.scan_running:
            return
        self.scan_running = True
        self.scan_scope = only
        self.scan_button.configure(text="ANALIZANDO...", state="disabled")
        self.section_button.configure(state="disabled")
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
        try:
            report = self.scan_service.scan(on_progress=self._publish_progress, only=scope)
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
        return self.scan_service.diagnostic_engine.build_report(results)

    def _scan_finished(self, report: DiagnosticReport) -> None:
        for result in report.results:
            self.results_by_kind[result.component] = result
            self.matrix.update_result(result)
        self.report = self._merged_report()
        self.scan_running = False
        self.scan_button.configure(text="ANALIZAR EQUIPO", state="normal")
        self.section_button.configure(state="normal")

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
            lines.append(f"{key}:")
            lines.append(_format_value(value, "  "))
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

    @staticmethod
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

    def _set_console(self, text: str) -> None:
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        clipped = text[:60_000]
        self.console.insert("1.0", clipped)
        for number, line in enumerate(clipped.splitlines()[:2500], start=1):
            tag = self._console_tag(line)
            if tag is not None:
                self.console.tag_add(tag, f"{number}.0", f"{number}.end")
        self.console.configure(state="disabled")

    def copy_evidence(self) -> None:
        text = self.console.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        self.progress_label.configure(text="Evidencia copiada al portapapeles")

    def export_report(self) -> None:
        if self.report is None:
            messagebox.showinfo(
                "Sin diagnóstico", "Primero debe analizar al menos una sección del equipo."
            )
            return
        default_name = f"diagnostico-hardware-{datetime.now(UTC):%Y%m%d-%H%M}.html"
        destination = filedialog.asksaveasfilename(
            parent=self,
            title="Guardar reporte de diagnóstico",
            defaultextension=".html",
            initialfile=default_name,
            filetypes=(("Reporte HTML", "*.html"), ("Todos los archivos", "*.*")),
        )
        if not destination:
            return
        try:
            path = export_html(self.report, Path(destination))
        except OSError as exc:
            messagebox.showerror("No se pudo guardar", str(exc), parent=self)
            return
        self.progress_label.configure(text=f"Reporte guardado: {path.name}")
        messagebox.showinfo("Reporte generado", f"Reporte guardado en:\n{path}", parent=self)

    def export_debug_state(self) -> str:
        """Representación estable usada por el smoke test, sin datos sensibles completos."""
        state = {
            "selected": self.selected_component.value,
            "has_report": self.report is not None,
            "navigation_items": len(NAV_ITEMS),
            "matrix_rows": len(self.matrix.rows),
        }
        return json.dumps(state, ensure_ascii=False, sort_keys=True)
