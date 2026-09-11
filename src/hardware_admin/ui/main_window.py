"""Ventana principal del Administrador de Hardware."""

from __future__ import annotations

import json
import os
import socket
import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk
import psutil
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
from hardware_admin.services.upgrade_advisor import (
    UpgradePreferences,
    build_upgrade_advice,
    format_upgrade_advice,
)
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

INITIAL_CONCLUSION_TEXT = "Analice una sección o el equipo completo para recopilar evidencia."

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
    NavEntry("save", "14. Exportar diagnóstico", action="export"),
    NavEntry("advanced", "0. Avanzado", action="advanced"),
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


def thermal_dashboard_rows(
    results: dict[ComponentKind, ComponentResult],
) -> list[dict[str, str]]:
    """Normaliza las lecturas F3 para su panel visible, sin inventar sensores.

    La telemetría puede llegar desde distintos recolectores. Esta función conserva
    el origen y el límite de cada fuente para que una zona ACPI no se presente
    como temperatura confirmada de CPU.
    """
    sources = (
        (ComponentKind.SYSTEM, "Sensores térmicos del equipo", "Sistema"),
        (ComponentKind.CPU, "Telemetría térmica CPU", "CPU"),
        (ComponentKind.MONITOR_GPU, "Telemetría térmica GPU", "GPU"),
        (ComponentKind.DISK, "Telemetría térmica de almacenamiento", "Almacenamiento"),
    )
    rows: list[dict[str, str]] = []
    for component, fact_key, area in sources:
        result = results.get(component)
        if result is None:
            continue
        value = result.facts.get(fact_key)
        if isinstance(value, str):
            rows.append(
                {
                    "area": area,
                    "source": "Sin lectura disponible",
                    "temperature": "—",
                    "status": "No soportado",
                    "detail": value,
                }
            )
            continue
        for item in _dict_list(result.facts, fact_key):
            source = str(
                item.get("Origen")
                or item.get("Sensor")
                or item.get("Dispositivo")
                or item.get("Unidad")
                or "Sensor"
            )
            rows.append(
                {
                    "area": area,
                    "source": source,
                    "temperature": str(item.get("Temperatura") or "No disponible"),
                    "status": str(item.get("Estado") or "No determinado"),
                    "detail": str(item.get("Detalle") or "Sin detalle adicional"),
                }
            )
    return rows


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


_DETAIL_LABELS = {
    "DeviceID": "Id. de dispositivo",
    "HardWareID": "Id. de hardware",
    "DriverDate": "Fecha del controlador",
    "DriverVersion": "Versión",
    "IsSigned": "Firma",
    "Manufacturer": "Fabricante",
    "Nombre": "Nombre",
}

_DRIVER_CATEGORY_LABELS = {
    "NET": "Red y conectividad",
    "SYSTEM": "Sistema y firmware",
    "PROCESSOR": "Procesador",
    "DISPLAY": "Gráficos y vídeo",
    "MEDIA": "Audio y vídeo",
    "AUDIOENDPOINT": "Audio",
    "AUDIOSWENDPOINT": "Audio",
    "HIDCLASS": "Entrada y dispositivos HID",
    "USB": "USB",
    "SCSIADAPTER": "Almacenamiento",
    "DISKDRIVE": "Almacenamiento",
    "IDE": "Almacenamiento",
    "CDROM": "Almacenamiento",
    "PRINTER": "Impresión",
    "PRINTQUEUE": "Impresión",
    "SECURITYDEVICES": "Seguridad",
    "SOFTWAREDEVICE": "Dispositivos de software",
}

_DRIVER_CATEGORY_COLORS = {
    "Red y conectividad": theme.COMPONENT_COLORS[ComponentKind.NETWORK],
    "Sistema y firmware": theme.COMPONENT_COLORS[ComponentKind.SYSTEM],
    "Procesador": theme.COMPONENT_COLORS[ComponentKind.CPU],
    "Gráficos y vídeo": theme.COMPONENT_COLORS[ComponentKind.MONITOR_GPU],
    "Audio y vídeo": "#E879F9",
    "Audio": "#E879F9",
    "Entrada y dispositivos HID": theme.COMPONENT_COLORS[ComponentKind.USB],
    "USB": theme.COMPONENT_COLORS[ComponentKind.USB],
    "Almacenamiento": theme.COMPONENT_COLORS[ComponentKind.DISK],
    "Impresión": theme.YELLOW,
    "Seguridad": theme.GREEN,
    "Dispositivos de software": theme.ACCENT_TEXT,
}

_DRIVER_FACT_ORDER = (
    "Consultados",
    "No firmados",
    "Dispositivos con fallo PnP",
    "Actualizaciones disponibles",
    "Actualizaciones",
    "Controladores",
)


def _display_value(value: Any) -> str:
    if value in (None, ""):
        return "No disponible"
    if isinstance(value, bool):
        return "Sí" if value else "No"
    return str(value)


def _record_title(record: dict[str, Any]) -> tuple[str, str]:
    for key in ("Nombre", "Dispositivo", "Adaptador", "Unidad", "Título", "Titulo", "Id"):
        value = record.get(key)
        if value not in (None, ""):
            return key, _display_value(value)
    return "", "Registro"


def _driver_category(record: dict[str, Any]) -> str:
    raw_type = _display_value(record.get("Tipo")).upper()
    return _DRIVER_CATEGORY_LABELS.get(raw_type, f"Otros · {raw_type}")


def _format_record(record: dict[str, Any], indent: str, hidden_keys: set[str] | None = None) -> list[str]:
    title_key, title = _record_title(record)
    hidden = hidden_keys or set()
    lines = [f"{indent}• {title}"]
    for key, value in record.items():
        if key == title_key or key in hidden:
            continue
        label = _DETAIL_LABELS.get(key, key)
        display_value = (
            "Firmado" if value else "No firmado"
        ) if key == "IsSigned" else _display_value(value)
        lines.append(f"{indent}  {label}: {display_value}")
    return lines


def _record_groups(
    records: list[dict[str, Any]],
    component: ComponentKind | None,
    fact_name: str,
) -> list[tuple[str | None, list[dict[str, Any]], set[str]]]:
    if component is ComponentKind.DRIVER and fact_name == "Controladores":
        grouped: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            grouped.setdefault(_driver_category(record), []).append(record)
        return [
            (
                category,
                sorted(grouped[category], key=lambda item: _record_title(item)[1].casefold()),
                {"Tipo"},
            )
            for category in sorted(grouped, key=str.casefold)
        ]

    group_key = next(
        (
            key
            for key in ("Categoría", "Categoria", "Tipo", "Clase", "Bus", "Tipo de medio")
            if any(record.get(key) not in (None, "") for record in records)
        ),
        None,
    )
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        group = _display_value(record.get(group_key)) if group_key else "Registros"
        groups.setdefault(group, []).append(record)

    return [
        (
            group if group_key else None,
            sorted(groups[group], key=lambda item: _record_title(item)[1].casefold()),
            {group_key} if group_key else set(),
        )
        for group in sorted(groups, key=str.casefold)
    ]


def _format_records(
    records: list[dict[str, Any]],
    indent: str,
    component: ComponentKind | None,
    fact_name: str,
) -> str:
    groups = _record_groups(records, component, fact_name)

    generic_lines: list[str] = []
    for group, group_records, hidden_keys in groups:
        if group:
            generic_lines.append(f"{indent}{group} ({len(group_records)})")
        for record in group_records:
            generic_lines.extend(
                _format_record(
                    record,
                    f"{indent}  " if group else indent,
                    hidden_keys,
                )
            )
    return "\n".join(generic_lines)


@dataclass(frozen=True, slots=True)
class EvidenceCard:
    title: str
    body: str
    color: str
    collapsible: bool = False


def _evidence_card_color(component: ComponentKind, category: str | None = None) -> str:
    if category:
        return _DRIVER_CATEGORY_COLORS.get(category, theme.ACCENT_TEXT)
    return theme.COMPONENT_COLORS.get(component, theme.ACCENT_TEXT)


def evidence_cards(component: ComponentKind, facts: dict[str, Any]) -> list[EvidenceCard]:
    """Convierte facts en tarjetas visuales, manteniendo todo el detalle disponible."""
    cards: list[EvidenceCard] = []
    scalars: list[str] = []
    for key, value in facts.items():
        if str(key).startswith("_"):
            continue
        if isinstance(value, (list, dict)):
            continue
        scalars.append(f"{key}: {_display_value(value)}")
    if scalars:
        cards.append(EvidenceCard("Resumen", "\n".join(scalars), _evidence_card_color(component)))

    for key, value in facts.items():
        if str(key).startswith("_"):
            continue
        if (
            component is ComponentKind.DRIVER
            and key == "Controladores desactualizados"
            and facts.get("Actualizaciones") == value
        ):
            continue
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            for category, records, hidden_keys in _record_groups(value, component, str(key)):
                title = f"{key} · {category} ({len(records)})" if category else f"{key} ({len(records)})"
                body = "\n".join(
                    line
                    for record in records
                    for line in _format_record(record, "", hidden_keys)
                )
                cards.append(
                    EvidenceCard(
                        title,
                        body,
                        _evidence_card_color(component, category),
                        collapsible=True,
                    )
                )
            continue
        if isinstance(value, (list, dict)):
            title = f"{key} ({len(value)})" if isinstance(value, list) else str(key)
            cards.append(
                EvidenceCard(
                    title,
                    _format_value(value, "", component=component, fact_name=str(key)),
                    _evidence_card_color(component),
                    collapsible=True,
                )
            )
    return cards


_ADVISOR_CARD_SPECS: tuple[tuple[str, str, str], ...] = (
    ("ram", "RAM", theme.COMPONENT_COLORS[ComponentKind.MEMORY]),
    ("ssd", "SSD", theme.COMPONENT_COLORS[ComponentKind.DISK]),
    ("gpu", "GPU · FUENTE Y ESPACIO", theme.COMPONENT_COLORS[ComponentKind.MONITOR_GPU]),
    ("priorización", "QUÉ ACTUALIZAR PRIMERO", theme.YELLOW),
)


def upgrade_advisor_cards(
    advice: dict[str, Any],
    recommendations: Sequence[Any] = (),
) -> list[EvidenceCard]:
    """Convierte las fichas del asesor en tarjetas compactas y desplegables."""

    cards: list[EvidenceCard] = []
    if recommendations:
        body_lines: list[str] = []
        for item in recommendations:
            body_lines.extend(
                [
                    str(getattr(item, "title", "Recomendación")),
                    f"Causa: {getattr(item, 'cause', 'No disponible')}",
                    f"Comprobación: {getattr(item, 'verification', 'No disponible')}",
                    "",
                ]
            )
        cards.append(
            EvidenceCard(
                f"RECOMENDACIONES DEL DIAGNÓSTICO ({len(recommendations)})",
                "\n".join(body_lines).strip(),
                theme.YELLOW,
                True,
            )
        )

    origin = str(advice.get("origen") or "Sin datos de asesor para esta sesión.")
    limits = advice.get("limitaciones")
    summary_lines = [origin]
    if isinstance(limits, list):
        summary_lines.extend(f"• {item}" for item in limits)
    cards.append(EvidenceCard("RESUMEN DEL ASESOR", "\n".join(summary_lines), theme.ACCENT_TEXT))

    for key, title, color in _ADVISOR_CARD_SPECS:
        section = advice.get(key)
        if not isinstance(section, dict):
            continue
        status = str(section.get("estado") or "PENDIENTE DE VERIFICACIÓN")
        body = [f"Estado: {status}", "", str(section.get("conclusion") or "Sin conclusión.")]
        facts = section.get("hechos")
        if isinstance(facts, list) and facts:
            body.extend(["", "HECHOS DE ESTA SESIÓN"])
            body.extend(f"• {item}" for item in facts)
        capacity = section.get("capacidad_objetivo")
        if capacity and capacity != "No indicada":
            body.extend(["", f"CAPACIDAD OBJETIVO: {capacity}"])
        actions = section.get("acciones")
        if isinstance(actions, list) and actions:
            body.extend(["", "ORDEN PROPUESTO"])
            for action in actions:
                if isinstance(action, dict):
                    body.append(f"{action.get('orden', '?')}. {action.get('área', 'Área')}")
                    body.append(f"   {action.get('acción', '')}")
                    body.append(f"   {action.get('fundamento', '')}")
        pending = section.get("comprobaciones_pendientes")
        if isinstance(pending, list) and pending:
            body.extend(["", "PENDIENTE"])
            body.extend(f"• {item}" for item in pending)
        alternative = section.get("alternativa_sin_compra")
        if alternative:
            body.extend(["", f"SIN COMPRA: {alternative}"])
        cards.append(EvidenceCard(f"ASESOR · {title} · {status}", "\n".join(body), color, True))
    return cards


def _format_value(
    value: Any,
    indent: str = "",
    *,
    component: ComponentKind | None = None,
    fact_name: str = "",
) -> str:
    if isinstance(value, list):
        if not value:
            return "Sin elementos"
        if all(isinstance(item, dict) for item in value):
            return _format_records(value, indent, component, fact_name)
        return "\n".join(f"{indent}• {_display_value(item)}" for item in value)
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            lines.append(f"{indent}{_DETAIL_LABELS.get(str(key), str(key))}:")
            lines.append(_format_value(item, f"{indent}  ", component=component, fact_name=str(key)))
        return "\n".join(lines)
    return _display_value(value)


def format_normalized_facts(component: ComponentKind, facts: dict[str, Any]) -> str:
    """Presenta datos estructurados por secciones sin alterar la evidencia cruda."""
    keys = [key for key in facts if not str(key).startswith("_")]
    if component is ComponentKind.DRIVER:
        ordered = [key for key in _DRIVER_FACT_ORDER if key in facts]
        ordered.extend(key for key in keys if key not in ordered)
        keys = ordered

    lines = ["DATOS NORMALIZADOS", "-------------------"]
    for key in keys:
        # Ambas claves contienen la misma lista de Windows Update; mostrar una sola evita duplicar ruido.
        if (
            component is ComponentKind.DRIVER
            and key == "Controladores desactualizados"
            and facts.get("Actualizaciones") == facts[key]
        ):
            continue
        lines.append(f"{key}:")
        lines.append(_format_value(facts[key], "  ", component=component, fact_name=str(key)))
        lines.append("")
    return "\n".join(lines).rstrip()


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
        self.icon_box = icon_box
        self.icon_pulse_on = False
        self._pulse_after_id: str | None = None
        ctk.CTkLabel(icon_box, text="", image=icon).place(relx=0.5, rely=0.5, anchor="center")
        self._pulse_after_id = self.after(900, self._pulse_icon)

        ctk.CTkLabel(
            self,
            text=title,
            font=ctk.CTkFont(family=theme.FONT_FAMILY, size=15),
            text_color=theme.TEXT,
            anchor="w",
        ).grid(row=0, column=1, sticky="sw", padx=(0, 14), pady=(17, 0))
        self.value_label = ctk.CTkLabel(
            self,
            text="--",
            font=ctk.CTkFont(family=theme.DATA_FONT_FAMILY, size=32, weight="bold"),
            text_color=theme.TEXT,
            anchor="w",
        )
        self.value_label.grid(row=1, column=1, sticky="nw", padx=(0, 14))
        self.status_label = ctk.CTkLabel(
            self,
            text="● Sin analizar",
            font=ctk.CTkFont(family=theme.FONT_FAMILY, size=12),
            text_color=theme.MUTED,
            anchor="w",
        )
        self.status_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=17, pady=(6, 14))

    def update_result(self, value: str, status: HealthStatus, label: str | None = None) -> None:
        self.value_label.configure(text=value)
        self.status_label.configure(
            text=f"● {label or STATUS_LABELS[status]}", text_color=STATUS_COLORS[status]
        )

    def reset(self) -> None:
        """Restaura el estado previo a cualquier análisis."""
        self.value_label.configure(text="--")
        self.status_label.configure(text="● Sin analizar", text_color=theme.MUTED)

    def _cancel_pulse(self) -> None:
        if self._pulse_after_id is not None:
            try:
                self.after_cancel(self._pulse_after_id)
            except (tk.TclError, AttributeError):
                pass
            self._pulse_after_id = None

    def destroy(self) -> None:
        self._cancel_pulse()
        super().destroy()

    def _pulse_icon(self) -> None:
        """Pulso visual ligero que mantiene viva la fila sin mover su geometría."""
        self._pulse_after_id = None
        try:
            if not self.winfo_exists() or not self.icon_box.winfo_exists():
                return
            self.icon_pulse_on = not self.icon_pulse_on
            self.icon_box.configure(
                border_width=1 if self.icon_pulse_on else 0,
                border_color=theme.ACCENT_TEXT,
            )
            self._pulse_after_id = self.after(1800 if self.icon_pulse_on else 1200, self._pulse_icon)
        except (tk.TclError, AttributeError):
            self._pulse_after_id = None


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

    def reset(self) -> None:
        """Elimina el resultado de una sesión sin alterar la fila seleccionada."""
        self.cells[1].configure(text="—")
        self.cells[2].configure(text="● Sin analizar", text_color=theme.MUTED)
        self.cells[3].configure(text="—")


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

    def reset(self) -> None:
        """Restaura todas las filas al estado inicial de diagnóstico."""
        for row in self.rows.values():
            row.reset()


def cancel_after_jobs(widget: Any, jobs: list[str]) -> int:
    """Cancela los `after` que programó este widget y vacía la lista.

    Tk no descarta los callbacks programados cuando se destruye su widget: al
    vencer intentan ejecutarse contra un objeto inexistente y Tcl emite un error
    de «after script». El proceso acaba con código 0 igualmente, así que el
    fallo pasa inadvertido.

    Se cancelan únicamente los identificadores propios. Cancelar la lista
    completa del intérprete (`after info`) alcanzaría también a los callbacks de
    otras ventanas vivas y de CustomTkinter, y rompe más de lo que arregla.

    Devuelve cuántos se cancelaron, para poder comprobarlo en las pruebas.
    """
    cancelled = 0
    for job in jobs:
        try:
            widget.after_cancel(job)
            cancelled += 1
        except tk.TclError:
            # Ya vencido o cancelado: no hay nada que deshacer.
            continue
    jobs.clear()
    return cancelled


class CollapsibleEvidenceCard(ctk.CTkFrame):
    """Tarjeta de evidencia que reserva el detalle para cuando se solicita."""

    def __init__(self, master: Any, card: EvidenceCard) -> None:
        super().__init__(
            master,
            fg_color=theme.SURFACE,
            border_color=card.color,
            border_width=1,
            corner_radius=10,
        )
        self.card = card
        self.expanded = not card.collapsible
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(8, 4))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text=card.title.upper(),
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=card.color,
        ).grid(row=0, column=0, sticky="ew")

        self.toggle_button: ctk.CTkButton | None = None
        if card.collapsible:
            self.toggle_button = ctk.CTkButton(
                header,
                text="⌄" if self.expanded else ">",
                width=28,
                height=26,
                corner_radius=6,
                fg_color="transparent",
                hover_color=theme.SURFACE_HOVER,
                text_color=card.color,
                font=ctk.CTkFont(size=16, weight="bold"),
                command=self.toggle,
            )
            self.toggle_button.grid(row=0, column=1, sticky="e", padx=(8, 0))

        self.detail = ctk.CTkLabel(
            self,
            text=card.body,
            anchor="nw",
            justify="left",
            wraplength=620,
            font=ctk.CTkFont(family=theme.DATA_FONT_FAMILY, size=12),
            text_color=theme.TEXT,
        )
        self.detail.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 12))
        if not self.expanded:
            self.detail.grid_remove()

    def toggle(self) -> None:
        """Muestra u oculta el detalle sin modificar la evidencia disponible."""
        if not self.card.collapsible:
            return
        self.expanded = not self.expanded
        if self.expanded:
            self.detail.grid()
        else:
            self.detail.grid_remove()
        if self.toggle_button is not None:
            self.toggle_button.configure(text="⌄" if self.expanded else ">")


class EvidenceWindow(ctk.CTkToplevel):
    """Evidencia técnica con vista organizada y texto completo copiable."""

    def __init__(
        self,
        master: Any,
        heading: str,
        body: str,
        expand_icon: ctk.CTkImage,
        result: ComponentResult | None = None,
    ) -> None:
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
            text="  E V I D E N C I A   T É C N I C A",
            image=expand_icon,
            compound="left",
            font=ctk.CTkFont(family=theme.FONT_FAMILY, size=13, weight="bold"),
            text_color=theme.ACCENT_TEXT,
        ).grid(row=0, column=0, sticky="w")
        self.heading = ctk.CTkLabel(
            bar,
            text=heading,
            font=ctk.CTkFont(family=theme.FONT_FAMILY, size=12),
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

        self.body = body
        self.views = ctk.CTkTabview(
            self,
            fg_color=theme.SURFACE,
            segmented_button_fg_color=theme.SURFACE_ALT,
            segmented_button_selected_color=theme.ACCENT,
            segmented_button_selected_hover_color=theme.ACCENT_HOVER,
            segmented_button_unselected_color=theme.SURFACE_ALT,
            segmented_button_unselected_hover_color=theme.SURFACE_HOVER,
            text_color=theme.TEXT,
        )
        self.views.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.views.add("Vista organizada")
        self.views.add("Evidencia completa")

        self.organized = ctk.CTkScrollableFrame(
            self.views.tab("Vista organizada"),
            fg_color="transparent",
            scrollbar_button_color=theme.BORDER,
            scrollbar_button_hover_color=theme.ACCENT,
        )
        self.organized.pack(fill="both", expand=True, padx=2, pady=2)
        self.organized.grid_columnconfigure(0, weight=1, uniform="evidence_cards")
        self.organized.grid_columnconfigure(1, weight=1, uniform="evidence_cards")

        self.console = ctk.CTkTextbox(
            self.views.tab("Evidencia completa"),
            fg_color=theme.TERMINAL,
            border_color=theme.BORDER,
            border_width=1,
            corner_radius=10,
            text_color=theme.CONSOLE_TEXT,
            font=ctk.CTkFont(family="Consolas", size=13),
            wrap="none",
        )
        self.console.pack(fill="both", expand=True, padx=2, pady=2)
        _configure_console_tags(self.console)
        _fill_console(self.console, body)
        self._render_organized(result)
        self.views.set("Vista organizada" if result is not None else "Evidencia completa")

        self.bind("<Escape>", lambda _event: self.destroy())
        self.transient(master)
        # `zoomed` llena la pantalla conservando los botones de ventana; el modo
        # fullscreen puro los oculta y deja al usuario sin salida visible.
        self._after_jobs: list[str] = [
            self.after(10, lambda: self.state("zoomed")),
            self.after(20, self.focus),
        ]

    def destroy(self) -> None:
        """Cancela lo propio antes de desaparecer.

        Esta ventana programa `state('zoomed')` a 10 ms y `focus` a 20 ms; si se
        cierra antes —como hace el smoke test— vencerían sobre un widget muerto.
        """
        cancel_after_jobs(self, self._after_jobs)
        super().destroy()

    def _render_organized(self, result: ComponentResult | None) -> None:
        for child in self.organized.winfo_children():
            child.destroy()
        if result is None:
            ctk.CTkLabel(
                self.organized,
                text="Sin datos estructurados para esta evidencia.",
                text_color=theme.MUTED,
                font=ctk.CTkFont(size=13),
            ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=16)
            return

        cards = evidence_cards(result.component, result.facts)
        if not cards:
            ctk.CTkLabel(
                self.organized,
                text="El componente no devolvió datos normalizados.",
                text_color=theme.MUTED,
                font=ctk.CTkFont(size=13),
            ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=16)
            return

        # Cada columna tiene su propia pila. Una cuadrícula de tarjetas comparte
        # la altura de cada fila y hacía que abrir una tarjeta estirase la vecina.
        columns: list[ctk.CTkFrame] = []
        for column_index in range(2):
            column = ctk.CTkFrame(self.organized, fg_color="transparent")
            column.grid(row=0, column=column_index, sticky="new", padx=0, pady=0)
            column.grid_columnconfigure(0, weight=1)
            columns.append(column)

        for index, card in enumerate(cards):
            CollapsibleEvidenceCard(columns[index % 2], card).pack(
                fill="x",
                padx=8,
                pady=8,
            )

    def update_content(
        self,
        heading: str,
        body: str,
        result: ComponentResult | None = None,
    ) -> None:
        self.heading.configure(text=heading)
        self.body = body
        _fill_console(self.console, body)
        self._render_organized(result)

    def copy_evidence(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.body)


class ThermalDashboardWindow(ctk.CTkToplevel):
    """Vista legible de los sensores de F3, separada de la evidencia cruda."""

    def __init__(self, master: Any, rows: Sequence[dict[str, str]]) -> None:
        super().__init__(master, fg_color=theme.BACKGROUND)
        self.title("Temperaturas y sensores")
        self.geometry("820x600")
        self.minsize(580, 380)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.withdraw)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(20, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="TEMPERATURAS Y SENSORES",
            font=ctk.CTkFont(size=19, weight="bold"),
            text_color=theme.TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="Lecturas del último análisis; no se inventan valores no expuestos por el hardware.",
            font=ctk.CTkFont(size=12),
            text_color=theme.MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        ctk.CTkButton(
            header,
            text="Cerrar",
            command=self.withdraw,
            width=96,
            height=32,
            corner_radius=8,
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.SURFACE_HOVER,
            border_width=1,
            border_color=theme.BORDER,
        ).grid(row=0, column=1, rowspan=2, sticky="e")

        self.body = ctk.CTkScrollableFrame(
            self,
            fg_color=theme.SURFACE,
            border_width=1,
            border_color=theme.BORDER,
            corner_radius=10,
        )
        self.body.grid(row=1, column=0, sticky="nsew", padx=22, pady=(0, 22))
        self.body.grid_columnconfigure(0, weight=1)
        self.update_rows(rows)

    def update_rows(self, rows: Sequence[dict[str, str]]) -> None:
        for child in self.body.winfo_children():
            child.destroy()
        if not rows:
            ctk.CTkLabel(
                self.body,
                text=(
                    "Aún no hay lecturas térmicas. Use «ANALIZAR EQUIPO».\n\n"
                    "Si después del análisis aparece «No soportado», el fabricante o Windows "
                    "no expone ese sensor de forma fiable."
                ),
                justify="left",
                anchor="w",
                font=ctk.CTkFont(size=13),
                text_color=theme.MUTED,
            ).grid(row=0, column=0, sticky="ew", padx=18, pady=18)
            return
        for index, row in enumerate(rows):
            status = row["status"].lower()
            color = theme.GREEN if status == HealthStatus.NORMAL.value else (
                theme.YELLOW if status == HealthStatus.WARNING.value else (
                    theme.RED if status in {HealthStatus.CRITICAL.value, HealthStatus.ERROR.value} else theme.MUTED
                )
            )
            card = ctk.CTkFrame(
                self.body,
                fg_color=theme.SURFACE_ALT,
                corner_radius=8,
                border_width=1,
                border_color=theme.BORDER_SOFT,
            )
            card.grid(row=index, column=0, sticky="ew", padx=8, pady=5)
            card.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                card,
                text=row["temperature"],
                font=ctk.CTkFont(size=23, weight="bold"),
                text_color=color,
                width=116,
            ).grid(row=0, column=0, rowspan=2, padx=(14, 10), pady=12)
            ctk.CTkLabel(
                card,
                text=f"{row['area']} · {row['source']}",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=theme.TEXT,
                anchor="w",
            ).grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=(12, 2))
            ctk.CTkLabel(
                card,
                text=f"{STATUS_LABELS.get(HealthStatus(status), row['status']) if status in HealthStatus._value2member_map_ else row['status']} · {row['detail']}",
                font=ctk.CTkFont(size=11),
                text_color=theme.MUTED,
                justify="left",
                anchor="w",
                wraplength=570,
            ).grid(row=1, column=1, sticky="ew", padx=(0, 14), pady=(2, 12))


class WindowsEventsWindow(ctk.CTkToplevel):
    """Vista legible de eventos críticos de Windows (F4) con ventana de 7 días y descargo de responsabilidad."""

    def __init__(self, master: Any, events: Sequence[dict[str, Any]]) -> None:
        super().__init__(master, fg_color=theme.BACKGROUND)
        self.title("Eventos críticos de Windows")
        self.geometry("860x620")
        self.minsize(600, 420)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.withdraw)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(20, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="EVENTOS CRÍTICOS DE WINDOWS",
            font=ctk.CTkFont(size=19, weight="bold"),
            text_color=theme.TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="Ventana temporal: últimos 7 días · La ausencia de eventos no certifica salud física.",
            font=ctk.CTkFont(size=12),
            text_color=theme.MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        ctk.CTkButton(
            header,
            text="Cerrar",
            command=self.withdraw,
            width=96,
            height=32,
            corner_radius=8,
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.SURFACE_HOVER,
            border_width=1,
            border_color=theme.BORDER,
        ).grid(row=0, column=1, rowspan=2, sticky="e")

        self.body = ctk.CTkScrollableFrame(
            self,
            fg_color=theme.SURFACE,
            border_width=1,
            border_color=theme.BORDER,
            corner_radius=10,
        )
        self.body.grid(row=1, column=0, sticky="nsew", padx=22, pady=(0, 22))
        self.body.grid_columnconfigure(0, weight=1)
        self.update_events(events)

    def update_events(self, events: Sequence[dict[str, Any]]) -> None:
        for child in self.body.winfo_children():
            child.destroy()
        if not events:
            ctk.CTkLabel(
                self.body,
                text=(
                    "Sin eventos críticos registrados en los últimos 7 días.\n\n"
                    "Aviso de cobertura: La ausencia de eventos en el registro del sistema "
                    "no certifica por sí sola la salud física ni eléctrica de los componentes."
                ),
                justify="left",
                anchor="w",
                font=ctk.CTkFont(size=13),
                text_color=theme.MUTED,
            ).grid(row=0, column=0, sticky="ew", padx=18, pady=18)
            return

        for index, ev in enumerate(events):
            cat = str(ev.get("Categoría") or "OTRO").upper()
            is_kp41 = ev.get("Id") == 41 or cat == "REINICIO_INESPERADO"
            is_whea = cat == "WHEA"
            badge_color = (
                theme.RED
                if is_whea
                else (theme.YELLOW if is_kp41 else theme.TEXT)
            )

            card = ctk.CTkFrame(
                self.body,
                fg_color=theme.SURFACE_ALT,
                corner_radius=8,
                border_width=1,
                border_color=theme.BORDER_SOFT,
            )
            card.grid(row=index, column=0, sticky="ew", padx=8, pady=5)
            card.grid_columnconfigure(1, weight=1)

            ev_id = ev.get("Id", 0)
            ctk.CTkLabel(
                card,
                text=f"ID {ev_id}\n{cat}",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=badge_color,
                width=110,
            ).grid(row=0, column=0, rowspan=2, padx=(12, 10), pady=10)

            ts = str(ev.get("Timestamp") or "")
            if "T" in ts:
                ts = ts.replace("T", " ").split(".")[0]
            prov = str(ev.get("Proveedor") or "Desconocido")
            ctk.CTkLabel(
                card,
                text=f"{prov} · {ts}",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=theme.TEXT,
                anchor="w",
            ).grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=(10, 2))

            msg = str(ev.get("Mensaje") or "")
            if is_kp41:
                msg = f"{msg} (Aviso: no determina la causa raíz física del reinicio)"

            ctk.CTkLabel(
                card,
                text=msg,
                font=ctk.CTkFont(size=11),
                text_color=theme.MUTED,
                justify="left",
                anchor="w",
                wraplength=640,
            ).grid(row=1, column=1, sticky="ew", padx=(0, 14), pady=(0, 10))


class UpgradeAdvisorDialog(ctk.CTkToplevel):
    """Formulario local para las verificaciones que Windows no puede observar."""

    _ENTRY_FIELDS: tuple[tuple[str, str, str], ...] = (
        ("Objetivo de uso", "goal", "Ej.: edición de vídeo a 1080p"),
        ("Presupuesto total", "budget", "Ej.: 250"),
        ("Moneda", "currency", "Ej.: HNL o USD"),
        ("SSD: modelo/capacidad objetivo", "ssd_target", "Ej.: SSD 1 TB"),
        ("SSD: capacidad objetivo", "ssd_target_capacity", "Ej.: 2 TB"),
        ("SSD: protocolo objetivo", "ssd_target_protocol", "Ej.: NVMe"),
        ("SSD: formato objetivo", "ssd_target_form_factor", "Ej.: M.2 2280"),
        ("SSD: bahía/ranura libre", "ssd_available_bays_or_slots", "Ej.: M.2_2 libre"),
        ("GPU objetivo (modelo/SKU)", "gpu_target", "Ej.: modelo exacto, no sólo familia"),
        ("GPU: fuente mínima requerida (W)", "gpu_required_psu_watts", "Ej.: 550"),
        ("GPU: conectores requeridos", "gpu_required_connectors", "Ej.: 1 × 8-pin"),
        ("GPU: longitud (mm)", "gpu_length_mm", "Ej.: 300"),
        ("Fuente instalada (W)", "gpu_current_psu_watts", "Ej.: 650"),
        ("Conectores PCIe disponibles", "gpu_current_connectors", "Ej.: 2 × 8-pin"),
        ("Espacio útil del gabinete (mm)", "gpu_clearance_mm", "Ej.: 320"),
        ("GPU: ranura/restricción documentada", "gpu_pcie_slot_note", "Ej.: PCIe x16 disponible"),
        ("GPU: manual/especificación", "gpu_manual_reference", "Modelo y enlace o código de manual"),
    )

    def __init__(
        self,
        master: Any,
        preferences: UpgradePreferences,
        on_save: Callable[[UpgradePreferences], None],
    ) -> None:
        super().__init__(master, fg_color=theme.BACKGROUND)
        self.title("Configurar asesor de ampliaciones")
        self.geometry("780x720")
        self.minsize(600, 460)
        self._on_save = on_save
        self._entries: dict[str, Any] = {}
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="DATOS PARA EL ASESOR DE AMPLIACIONES",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=theme.TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text=(
                "Todo queda sólo en esta sesión. Windows no conoce ranuras libres, fuente ni espacio: "
                "anote datos del manual o de una comprobación física."
            ),
            font=ctk.CTkFont(size=11),
            text_color=theme.MUTED,
            justify="left",
            wraplength=650,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        body = ctk.CTkScrollableFrame(
            self,
            fg_color=theme.SURFACE,
            border_width=1,
            border_color=theme.BORDER,
            corner_radius=10,
        )
        body.grid(row=1, column=0, sticky="nsew", padx=22, pady=(0, 12))
        body.grid_columnconfigure(1, weight=1)
        for row, (label, key, placeholder) in enumerate(self._ENTRY_FIELDS):
            ctk.CTkLabel(
                body,
                text=label,
                text_color=theme.TEXT,
                font=ctk.CTkFont(size=12),
                anchor="w",
            ).grid(row=row, column=0, sticky="w", padx=(14, 10), pady=5)
            entry = ctk.CTkEntry(body, placeholder_text=placeholder, height=30)
            entry.grid(row=row, column=1, sticky="ew", padx=(0, 14), pady=5)
            entry.insert(0, str(getattr(preferences, key)))
            self._entries[key] = entry

        option_row = len(self._ENTRY_FIELDS)
        self._equipment_var = ctk.StringVar(value=preferences.equipment_form)
        self._ram_soldered_var = ctk.StringVar(value=preferences.ram_soldered)
        self._ssd_mode_var = ctk.StringVar(value=preferences.ssd_mode)
        self._option(body, option_row, "Tipo de equipo", self._equipment_var, ("No indicado", "Sobremesa", "Portátil"))
        self._option(body, option_row + 1, "RAM soldada", self._ram_soldered_var, ("No indicado", "No", "Sí"))
        self._option(body, option_row + 2, "Plan SSD", self._ssd_mode_var, ("Añadir", "Reemplazar"))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 18))
        footer.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            footer,
            text="Cancelar",
            command=self.destroy,
            width=112,
            height=34,
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.SURFACE_HOVER,
            border_width=1,
            border_color=theme.BORDER,
        ).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(
            footer,
            text="Actualizar asesor",
            command=self._save,
            width=150,
            height=34,
            fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER,
        ).grid(row=0, column=2)

    @staticmethod
    def _option(
        master: Any,
        row: int,
        label: str,
        variable: Any,
        values: tuple[str, ...],
    ) -> None:
        ctk.CTkLabel(
            master,
            text=label,
            text_color=theme.TEXT,
            font=ctk.CTkFont(size=12),
            anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=(14, 10), pady=5)
        ctk.CTkOptionMenu(master, values=list(values), variable=variable, height=30).grid(
            row=row, column=1, sticky="ew", padx=(0, 14), pady=5
        )

    def _save(self) -> None:
        values = {key: str(entry.get()).strip() for key, entry in self._entries.items()}
        values.update(
            {
                "equipment_form": self._equipment_var.get(),
                "ram_soldered": self._ram_soldered_var.get(),
                "ssd_mode": self._ssd_mode_var.get(),
            }
        )
        self._on_save(UpgradePreferences(**values))
        self.destroy()


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
        self.worker_poll_job: str | None = None
        self.advanced_refresh_job: str | None = None
        self.report: DiagnosticReport | None = None
        self.upgrade_preferences = UpgradePreferences()
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
        self.thermal_window: ThermalDashboardWindow | None = None
        self.windows_events_window: WindowsEventsWindow | None = None
        self.icons = IconCache()
        self.nav_font = ctk.CTkFont(family=theme.FONT_FAMILY, size=13)
        self.nav_font_selected = ctk.CTkFont(family=theme.FONT_FAMILY, size=13, weight="bold")

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
            font=ctk.CTkFont(family=theme.FONT_FAMILY, size=25, weight="bold"),
            text_color=theme.TEXT,
        ).grid(row=0, column=1, sticky="sw", pady=(20, 0))
        ctk.CTkLabel(
            header,
            text="DIAGNÓSTICO Y ESTADO DEL EQUIPO",
            font=ctk.CTkFont(family=theme.FONT_FAMILY, size=14, weight="bold"),
            text_color=theme.MUTED,
        ).grid(row=1, column=1, sticky="nw", pady=(2, 0))

        self.status_pill = ctk.CTkFrame(header, corner_radius=8, border_width=1)
        self.status_pill.grid(row=0, column=2, padx=(12, 26), pady=(22, 0), sticky="e")
        self.status_icon = ctk.CTkLabel(self.status_pill, text="")
        self.status_icon.grid(row=0, column=0, padx=(13, 8), pady=8)
        self.global_status = ctk.CTkLabel(
            self.status_pill,
            text="Sin analizar",
            font=ctk.CTkFont(family=theme.FONT_FAMILY, size=13, weight="bold"),
        )
        self.global_status.grid(row=0, column=1, padx=(0, 15), pady=8)
        self._set_global_status("idle", "Sin analizar")

        self.last_scan_label = ctk.CTkLabel(
            header,
            text="Último análisis: —",
            text_color=theme.MUTED,
            font=ctk.CTkFont(family=theme.FONT_FAMILY, size=11),
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
            text="O P C I O N E S",
            font=ctk.CTkFont(family=theme.FONT_FAMILY, size=12),
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
            border_width=1,
            border_color=theme.ACCENT_TEXT,
        )
        self.scan_button.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 16))
        self.scan_button.bind("<Enter>", self._primary_button_enter)
        self.scan_button.bind("<Leave>", self._primary_button_leave)
        self.reset_diagnostic_button = ctk.CTkButton(
            sidebar,
            text="LIMPIAR DIAGNÓSTICO",
            image=self.icons.get("refresh", 16, theme.ACCENT_TEXT),
            compound="left",
            command=self.reset_diagnostic,
            height=38,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="transparent",
            hover_color=theme.SURFACE_HOVER,
            border_width=1,
            border_color=theme.BORDER,
            text_color=theme.ACCENT_TEXT,
        )
        self.reset_diagnostic_button.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 16))

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
            font=ctk.CTkFont(family=theme.FONT_FAMILY, size=19, weight="bold"),
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

        self.thermal_dashboard_button = ctk.CTkButton(
            title_row,
            text="Temperaturas y sensores",
            command=self.open_thermal_dashboard,
            height=34,
            width=190,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.SURFACE_HOVER,
            border_width=1,
            border_color=theme.BORDER,
            text_color=theme.ACCENT_TEXT,
        )
        self.thermal_dashboard_button.grid(row=0, column=3, sticky="e", padx=(0, 10))

        self.windows_events_button = ctk.CTkButton(
            title_row,
            text="Eventos de Windows",
            command=self.open_windows_events,
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
        self.windows_events_button.grid(row=0, column=4, sticky="e", padx=(0, 10))

        self.section_button = ctk.CTkButton(
            title_row,
            text="Analizar sistema",
            image=self.icons.get("refresh", 16, theme.ACCENT_TEXT),
            compound="left",
            command=self.scan_selected_component,
            height=34,
            width=208,
            corner_radius=10,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.SURFACE_HOVER,
            border_width=1,
            border_color=theme.BORDER,
            text_color=theme.ACCENT_TEXT,
        )
        self.section_button.grid(row=0, column=5, sticky="e")
        self.section_button.bind("<Enter>", self._primary_button_enter)
        self.section_button.bind("<Leave>", self._primary_button_leave)

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

        self.battery_card = StatusCard(
            cards_frame,
            "Batería",
            self.icons.get("card", 26, theme.BATTERY_COLOR),
            theme.BATTERY_ICON_BACKGROUND,
        )
        self.battery_card.grid(row=0, column=4, sticky="nsew", padx=(7, 0))

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
        panel.grid_rowconfigure(1, weight=1)
        self.action_view = panel

        self.advisor_controls = ctk.CTkFrame(panel, fg_color="transparent")
        self.advisor_controls.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 0))
        self.advisor_controls.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self.advisor_controls,
            text="Los datos declarados se conservan sólo hasta cerrar o limpiar el diagnóstico.",
            text_color=theme.MUTED,
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=0, sticky="w")
        self.advisor_configure_button = ctk.CTkButton(
            self.advisor_controls,
            text="Configurar datos",
            command=self.open_upgrade_advisor_config,
            width=130,
            height=30,
            corner_radius=8,
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.SURFACE_HOVER,
            border_width=1,
            border_color=theme.BORDER,
            text_color=theme.ACCENT_TEXT,
        )
        self.advisor_configure_button.grid(row=0, column=1, padx=(8, 0))
        self.advisor_controls.grid_remove()

        # Cabecera de «Exportar diagnóstico»: la vista previa se lee antes de guardar.
        self.export_controls = ctk.CTkFrame(panel, fg_color="transparent")
        self.export_controls.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 0))
        self.export_controls.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self.export_controls,
            text="Vista previa del diagnóstico. Nada se guarda hasta pulsar «Exportar».",
            text_color=theme.MUTED,
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=0, sticky="w")
        self.export_confirm_button = ctk.CTkButton(
            self.export_controls,
            text="Exportar",
            image=self.icons.get("save", 16, theme.ACCENT_TEXT),
            compound="left",
            command=self.export_report,
            width=130,
            height=30,
            corner_radius=8,
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.SURFACE_HOVER,
            border_width=1,
            border_color=theme.BORDER,
            text_color=theme.ACCENT_TEXT,
        )
        self.export_confirm_button.grid(row=0, column=1, padx=(8, 0))
        self.export_controls.grid_remove()

        self.action_text = ctk.CTkTextbox(
            panel,
            fg_color=theme.TERMINAL,
            text_color=theme.CONSOLE_TEXT,
            font=ctk.CTkFont(family="Consolas", size=12),
            corner_radius=8,
            wrap="none",
        )
        self.action_text.grid(row=1, column=0, sticky="nsew", padx=14, pady=14)
        self.action_text.configure(state="disabled")

        self.advisor_cards_view = ctk.CTkScrollableFrame(
            panel,
            fg_color="transparent",
            corner_radius=0,
        )
        self.advisor_cards_view.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 8))
        self.advisor_cards_view.grid_columnconfigure(0, weight=1, uniform="advisor-columns")
        self.advisor_cards_view.grid_columnconfigure(1, weight=1, uniform="advisor-columns")
        self.advisor_cards_view.grid_remove()
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

    def _cancel_advanced_refresh(self) -> None:
        if self.advanced_refresh_job is not None:
            self.after_cancel(self.advanced_refresh_job)
            self.advanced_refresh_job = None

    def _on_close(self) -> None:
        """Detiene el muestreo antes de cerrar para no dejar el hilo colgado."""
        self.monitoring_service.stop()
        self._cancel_advanced_refresh()
        self.destroy()

    def destroy(self) -> None:
        """Cierra cancelando el refresco de monitorización y el sondeo del worker.

        Ambos se reprograman solos con `after`, así que sin cancelarlos vencería
        al menos uno después de que la ventana deje de existir.
        """
        propios = [job for job in (self.monitoring_job, self.worker_poll_job) if job]
        cancel_after_jobs(self, propios)
        self.monitoring_job = None
        self.worker_poll_job = None
        super().destroy()

    def _build_diagnostic_column(self, master: Any) -> None:
        left = ctk.CTkFrame(master, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            left,
            text="MATRIZ DE DIAGNÓSTICO",
            font=ctk.CTkFont(family=theme.FONT_FAMILY, size=15, weight="bold"),
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
            font=ctk.CTkFont(family=theme.FONT_FAMILY, size=13, weight="bold"),
            text_color=theme.ACCENT_TEXT,
        ).grid(row=0, column=1, sticky="sw", pady=(16, 4))
        self.conclusion_label = ctk.CTkLabel(
            conclusion,
            text=INITIAL_CONCLUSION_TEXT,
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
            fg_color="transparent",
            hover_color=theme.SURFACE_HOVER,
            border_width=1,
            border_color=theme.BORDER,
            text_color=theme.ACCENT_TEXT,
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
            fg_color="transparent",
            hover_color=theme.SURFACE_HOVER,
            border_width=1,
            border_color=theme.BORDER,
            text_color=theme.ACCENT_TEXT,
            command=self.copy_evidence,
        ).grid(row=0, column=3, sticky="e")
        self.driver_update_link = ctk.CTkLabel(
            header,
            text="Actualizar en Windows Update",
            text_color=theme.ACCENT_TEXT,
            font=ctk.CTkFont(size=11, underline=True),
        )
        self.driver_update_link.grid(row=1, column=3, sticky="e", pady=(4, 0))
        self.driver_update_link.bind("<Button-1>", lambda _event: self.open_windows_update())
        self.driver_update_link.grid_remove()

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
        elif action == "export":
            self.show_export_preview()
        elif action == "advanced":
            self.show_advanced()

    def _show_action_view(self, action: str, title: str, body: str) -> None:
        """Presenta un apartado que no es un componente."""
        self._cancel_advanced_refresh()
        self._highlight_nav(action)
        self.section_title.configure(text=title)
        self.monitoring_panel.grid_remove()
        for panel in self.section_panels.values():
            panel.grid_remove()
        self.workspace.grid_remove()
        self.action_view.grid()
        self.advisor_controls.grid_remove()
        self.export_controls.grid_remove()
        self.advisor_cards_view.grid_remove()
        self.action_text.grid()
        self.action_text.configure(state="normal")
        self.action_text.delete("1.0", "end")
        self.action_text.insert("1.0", body)
        self.action_text.configure(state="disabled")

    def _render_upgrade_advisor_cards(self, recommendations: Sequence[Any]) -> None:
        """Apila cada columna de forma independiente, igual que la evidencia de controladores."""
        for child in self.advisor_cards_view.winfo_children():
            child.destroy()
        advice = self.report.upgrade_advice if self.report else {}
        columns: list[ctk.CTkFrame] = []
        for index in range(2):
            column = ctk.CTkFrame(self.advisor_cards_view, fg_color="transparent")
            column.grid(row=0, column=index, sticky="new")
            column.grid_columnconfigure(0, weight=1)
            columns.append(column)
        for index, card in enumerate(upgrade_advisor_cards(advice, recommendations)):
            CollapsibleEvidenceCard(columns[index % 2], card).pack(fill="x", padx=8, pady=8)

    @staticmethod
    def _format_battery_eta(seconds: float | None) -> str:
        if seconds is None or seconds <= 0:
            return "Autonomía desconocida"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        if hours > 0:
            return f"~{hours} h {minutes} min"
        return f"~{minutes} min"

    def _read_battery_summary(self) -> tuple[str, str, str, HealthStatus]:
        try:
            battery = psutil.sensors_battery()
        except (AttributeError, OSError, RuntimeError):
            return "No aplica", "No aplica", "Sin sensor de batería en este equipo.", HealthStatus.UNKNOWN
        if battery is None:
            return "No aplica", "Sin batería", "No aplica", HealthStatus.UNKNOWN

        percent = max(0, int(battery.percent))
        if battery.power_plugged:
            status_text = "Cargando" if percent < 100 else "Conectada"
            eta = "Conectada" if percent >= 100 else self._format_battery_eta(battery.secsleft)
        else:
            status_text = "Descargando" if percent < 100 else "En espera"
            eta = self._format_battery_eta(battery.secsleft)

        if percent <= 10:
            health_status = HealthStatus.CRITICAL
        elif percent <= 20:
            health_status = HealthStatus.WARNING
        else:
            health_status = HealthStatus.NORMAL
        return f"{percent}%", status_text, eta if eta else "Autonomía desconocida", health_status

    def show_advanced(self) -> None:
        self._cancel_advanced_refresh()
        battery_percent, state, eta, health_status = self._read_battery_summary()
        lines = [
            "AVANZADO",
            "========",
            "",
            f"Batería: {battery_percent}",
            f"Estado: {state}",
            f"Autonomía estimada: {eta}",
            f"Estado de salud: {STATUS_LABELS[health_status]}",
            "",
            (
                "Diagnóstico de batería en tiempo real: el valor se actualiza cada 10 segundos "
                "mientras esta vista esté abierta."
            ),
            "",
            "Funciones del modo avanzado:",
            "- Ver el estado inmediato de la batería.",
            "- Generar un reporte HTML de batería al elegir una ruta de destino.",
            "- Mantener cierres ordenados sin cancelar tareas globales del resto de la app.",
        ]
        self._show_action_view("advanced", "AVANZADO", "\n".join(lines))
        self.advanced_refresh_job = self.after(10000, self._refresh_advanced_view)

    def _refresh_advanced_view(self) -> None:
        if self.active_nav_key != "advanced":
            self._cancel_advanced_refresh()
            return
        battery_percent, state, eta, _ = self._read_battery_summary()
        text = "\n".join(
            [
                "AVANZADO",
                "========",
                "",
                f"Batería: {battery_percent}",
                f"Estado: {state}",
                f"Autonomía estimada: {eta}",
                "",
                "Actualización en tiempo real activa.",
            ]
        )
        self.action_text.configure(state="normal")
        self.action_text.delete("1.0", "end")
        self.action_text.insert("1.0", text)
        self.action_text.configure(state="disabled")
        self.advanced_refresh_job = self.after(10000, self._refresh_advanced_view)

    def show_export_preview(self) -> None:
        """Vista previa del diagnóstico antes de exportar. No guarda nada por sí sola."""
        report = self.report
        if report is None:
            self._show_action_view(
                "export",
                "EXPORTAR DIAGNÓSTICO",
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
        if report.upgrade_advice:
            lines.extend(["", format_upgrade_advice(report.upgrade_advice)])

        lines.extend(
            [
                "",
                "Pulse «Exportar» para guardar este diagnóstico en disco."
            ]
        )
        self._show_action_view("export", "EXPORTAR DIAGNÓSTICO", NL.join(lines))
        self.export_controls.grid()

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
        """Procedimientos del diagnóstico y asesores locales de ampliación."""
        recommendations = self.report.recommendations if self.report else ()
        if self.report is None:
            self._show_action_view(
                "recommendations",
                "RECOMENDACIONES",
                "Aún no hay diagnóstico.\n\nEjecute «Analizar equipo» para que el asesor "
                "de RAM, SSD, GPU y prioridad use el inventario local de esta sesión.",
            )
            return

        lines = ["RECOMENDACIONES", "===============", ""]
        if recommendations:
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
        else:
            lines.extend(
                [
                    "No se detectaron recomendaciones correctivas en esta sesión.",
                    "Esto no certifica que el hardware esté libre de fallas.",
                    "",
                ]
            )
        lines.extend([format_upgrade_advice(self.report.upgrade_advice), ""])
        self._show_action_view("recommendations", "RECOMENDACIONES", "\n".join(lines))
        self.advisor_controls.grid()
        self.action_text.grid_remove()
        self._render_upgrade_advisor_cards(recommendations)
        self.advisor_cards_view.grid()

    def open_upgrade_advisor_config(self) -> None:
        """Pide la evidencia física/documental que Windows no puede medir."""
        if self.report is None:
            return
        window = UpgradeAdvisorDialog(self, self.upgrade_preferences, self._save_upgrade_preferences)
        self._present_child_window(window)

    def _save_upgrade_preferences(self, preferences: UpgradePreferences) -> None:
        self.upgrade_preferences = preferences
        self._refresh_upgrade_advice()
        self.show_recommendations()

    def _refresh_upgrade_advice(self) -> None:
        """Actualiza sólo las fichas de sesión; no dispara consultas ni acciones externas."""
        if self.report is None:
            return
        advice = build_upgrade_advice(self.report.results, self.upgrade_preferences)
        self.report = replace(self.report, upgrade_advice=advice)

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
            self.windows_events_button.grid()
        else:
            self.battery_report_button.grid_remove()
            self.windows_events_button.grid_remove()

        # Un unico hueco en la fila 3: el panel en vivo en E/S, y el de
        # graficos del apartado en CPU, RAM, discos y red.
        if component is ComponentKind.IO:
            self.monitoring_panel.grid()
            self._draw_monitoring()
        else:
            self.monitoring_panel.grid_remove()
        self._sync_driver_update_link()
        for kind, panel in self.section_panels.items():
            if kind is component:
                panel.grid()
                self._draw_section_charts(kind)
            else:
                panel.grid_remove()
        self._show_selected_evidence()

    def _primary_button_enter(self, event: Any) -> None:
        button = event.widget
        button.configure(border_width=2, border_color=theme.ACCENT_TEXT)

    def _primary_button_leave(self, event: Any) -> None:
        button = event.widget
        border_color = theme.ACCENT_TEXT if button is self.scan_button else theme.BORDER
        button.configure(border_width=1, border_color=border_color)

    def _animate_refresh_icon(self, frame: int = 0) -> None:
        """Gira brevemente los iconos de análisis al comenzar una comprobación."""
        buttons = (
            (self.scan_button, 20, "#FFFFFF"),
            (self.section_button, 16, theme.ACCENT_TEXT),
        )
        images: list[ctk.CTkImage] = []
        angle = frame * 45
        for button, size, color in buttons:
            image = icons.render("refresh", size, color).rotate(
                angle, resample=Image.Resampling.BICUBIC
            )
            ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))
            images.append(ctk_image)
            button.configure(image=ctk_image)
        self._refresh_animation_images = images
        if frame < 8:
            self.after(45, lambda: self._animate_refresh_icon(frame + 1))
        else:
            self.scan_button.configure(image=self.icons.get("refresh", 20, "#FFFFFF"))
            self.section_button.configure(image=self.icons.get("refresh", 16, theme.ACCENT_TEXT))

    def start_scan(self, only: ComponentKind | None = None) -> None:
        """Analiza el equipo completo, o sólo `only` si se indica un componente."""
        if self.scan_running:
            return
        self.scan_running = True
        self.scan_scope = only
        self._animate_refresh_icon()
        self.scan_button.configure(text="ANALIZANDO...", state="disabled")
        self.section_button.configure(state="disabled")
        self.reset_diagnostic_button.configure(state="disabled")
        self.symptom_entry.configure(state="disabled")
        self._set_global_status("busy", "Analizando")
        self.progress_label.configure(text="Iniciando comprobaciones...")
        worker = threading.Thread(
            target=self._run_scan, args=(only,), name="hardware-scan", daemon=True
        )
        worker.start()
        self.worker_poll_job = self.after(40, self._poll_worker_events)

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
            self.worker_poll_job = self.after(40, self._poll_worker_events)

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
        self._refresh_upgrade_advice()
        # Refrescar el panel visible: sin esto los graficos seguirian mostrando
        # el analisis anterior hasta que el usuario cambiara de apartado.
        self._draw_section_charts(self.selected_component)
        self.scan_running = False
        self.scan_button.configure(text="ANALIZAR EQUIPO", state="normal")
        self.section_button.configure(state="normal")
        self.reset_diagnostic_button.configure(state="normal")
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
        self._refresh_thermal_dashboard()
        self._refresh_windows_events()
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
        self.reset_diagnostic_button.configure(state="normal")
        self.symptom_entry.configure(state="normal")
        self._set_global_status("error", "Error")
        self.progress_label.configure(text="El análisis no pudo completarse")
        messagebox.showerror("Error de análisis", f"No fue posible completar el análisis:\n{error}")

    def reset_diagnostic(self) -> None:
        """Descarta sólo la sesión actual para comenzar un diagnóstico nuevo.

        No borra reportes ya exportados ni las muestras de monitorización: ambas
        son recursos distintos del diagnóstico de componentes.
        """
        if self.scan_running:
            return
        self.report = None
        self.upgrade_preferences = UpgradePreferences()
        self.results_by_kind.clear()
        self.scan_scope = None
        self.symptom_var.set("")
        self.matrix.reset()
        for card in self.cards.values():
            card.reset()
        self.battery_card.reset()
        for component in self.section_panels:
            self._draw_section_charts(component)
        self._set_global_status("idle", "Sin analizar")
        self.last_scan_label.configure(text="Último análisis: —")
        self.progress_label.configure(text="Diagnóstico restablecido")
        self.conclusion_label.configure(text=INITIAL_CONCLUSION_TEXT)
        self._refresh_thermal_dashboard()
        self._refresh_windows_events()
        self._show_selected_evidence()

    def _update_cards(self) -> None:
        for kind, card in self.cards.items():
            result = self.results_by_kind.get(kind)
            if result is None:
                continue
            label = None
            if kind is ComponentKind.NETWORK and result.status is HealthStatus.NORMAL:
                label = "Conectada"
            card.update_result(self._card_value(result), result.status, label)

        battery_percent, battery_state, eta, battery_health = self._read_battery_summary()
        self.battery_card.update_result(
            battery_percent,
            battery_health,
            f"{battery_state} · {eta}",
        )

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

    def open_thermal_dashboard(self) -> None:
        """Abre una ventana hija con las lecturas F3 del último análisis."""
        rows = thermal_dashboard_rows(self.results_by_kind)
        window = self.thermal_window
        if window is not None and window.winfo_exists():
            window.update_rows(rows)
            self._present_child_window(window)
            return
        self.thermal_window = ThermalDashboardWindow(self, rows)
        self._present_child_window(self.thermal_window)

    def _present_child_window(self, window: ctk.CTkToplevel) -> None:
        """Muestra una ventana hija delante de su aplicación sin hacerla modal."""
        window.deiconify()
        window.transient(self)
        window.lift()
        window.focus_force()
        # En Windows, `lift` durante el primer mapeo puede perderse frente a la
        # ventana principal. Elevarla brevemente fuerza el orden correcto y al
        # soltarlo conserva el comportamiento normal de una ventana hija.
        window.attributes("-topmost", True)
        window.update_idletasks()
        window.attributes("-topmost", False)

    def _refresh_thermal_dashboard(self) -> None:
        rows = thermal_dashboard_rows(self.results_by_kind)
        suffix = f" · {len(rows)} lectura(s)" if rows else ""
        self.thermal_dashboard_button.configure(text=f"Temperaturas y sensores{suffix}")
        window = self.thermal_window
        if window is not None and window.winfo_exists():
            window.update_rows(rows)

    def open_windows_events(self) -> None:
        """Abre una ventana hija con los eventos críticos de Windows (Fase F4)."""
        events = self._get_windows_events()
        window = self.windows_events_window
        if window is not None and window.winfo_exists():
            window.update_events(events)
            self._present_child_window(window)
            return
        self.windows_events_window = WindowsEventsWindow(self, events)
        self._present_child_window(self.windows_events_window)

    def _get_windows_events(self) -> list[dict[str, Any]]:
        sys_res = self.results_by_kind.get(ComponentKind.SYSTEM)
        if sys_res and sys_res.facts:
            raw_evs = sys_res.facts.get("Eventos de Windows (7 días)")
            if isinstance(raw_evs, list):
                return raw_evs
        return []

    def _refresh_windows_events(self) -> None:
        events = self._get_windows_events()
        suffix = f" · {len(events)}" if events else ""
        self.windows_events_button.configure(text=f"Eventos de Windows{suffix}")
        window = self.windows_events_window
        if window is not None and window.winfo_exists():
            window.update_events(events)

    def _show_selected_evidence(self) -> None:
        result = self.results_by_kind.get(self.selected_component)
        name = SECTION_NAMES[self.selected_component]
        if result is None:
            self._sync_driver_update_link()
            self.console_context.configure(text=f"Sin analizar · {name}")
            self.console_indicator.configure(text_color=theme.MUTED)
            self._set_console(
                f"> {self.selected_component.value}\n"
                f"Sin evidencia. Use «Analizar {name}» o ANALIZAR EQUIPO."
            )
            self._sync_evidence_window()
            return

        self.console_context.configure(text=f"Componente: {result.name}")
        self._sync_driver_update_link()
        self.console_indicator.configure(text_color=STATUS_COLORS[result.status])
        lines = [
            f"COMPONENTE: {result.name}",
            f"ESTADO: {STATUS_LABELS[result.status]}",
            f"RESUMEN: {result.summary}",
            "",
            format_normalized_facts(result.component, result.facts),
        ]
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

    def _sync_driver_update_link(self) -> None:
        result = self.results_by_kind.get(ComponentKind.DRIVER)
        updates = result.facts.get("Actualizaciones", []) if result else []
        if self.selected_component is ComponentKind.DRIVER and updates:
            self.driver_update_link.grid()
        else:
            self.driver_update_link.grid_remove()

    def open_windows_update(self) -> None:
        """Abre el enlace oficial para actualizar el controlador seleccionado."""
        update_uri = "ms-settings:windowsupdate"
        try:
            startfile = getattr(os, "startfile", None)
            if callable(startfile):
                startfile(update_uri)
            elif not webbrowser.open(update_uri):
                raise OSError("Windows no pudo abrir Windows Update")
        except OSError as exc:
            messagebox.showerror(
                "Windows Update",
                f"No fue posible abrir Windows Update:\n{exc}",
                parent=self,
            )

    def _set_console(self, text: str) -> None:
        _fill_console(self.console, text)

    def open_evidence_window(self) -> None:
        """Abre la evidencia del componente seleccionado a pantalla completa."""
        heading = self.console_context.cget("text")
        body = self.console.get("1.0", "end-1c")
        result = self.results_by_kind.get(self.selected_component)
        window = self.evidence_window
        if window is not None and window.winfo_exists():
            window.update_content(heading, body, result)
            window.deiconify()
            window.lift()
            window.focus()
            return
        self.evidence_window = EvidenceWindow(
            self,
            heading,
            body,
            self.icons.get("expand", 17, theme.ACCENT_TEXT),
            result,
        )

    def _sync_evidence_window(self) -> None:
        window = self.evidence_window
        if window is not None and window.winfo_exists():
            window.update_content(
                self.console_context.cget("text"),
                self.console.get("1.0", "end-1c"),
                self.results_by_kind.get(self.selected_component),
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

        self.battery_report_button.configure(state="disabled")
        self.progress_label.configure(text="Generando reporte de batería...")

        def _worker() -> None:
            try:
                res = generate_battery_report(target_path)
            except Exception as exc:  # noqa: BLE001
                err_text = str(exc)
                self.after(0, lambda msg=err_text: self._on_battery_report_failed(msg))
                return
            self.after(0, lambda: self._on_battery_report_completed(target_path, res))

        threading.Thread(target=_worker, name="battery-report-worker", daemon=True).start()

    def _on_battery_report_completed(self, target_path: Path, result: Any) -> None:
        self.battery_report_button.configure(state="normal")
        if result.exit_code == 0:
            self.progress_label.configure(text=f"Reporte de batería: {target_path.name}")
            messagebox.showinfo(
                "Reporte de batería generado",
                f"El reporte de batería se guardó con éxito en:\n{target_path}",
                parent=self,
            )
        else:
            err_msg = str(getattr(result, "error", "")).strip() or f"Código de salida: {result.exit_code}"
            self.progress_label.configure(text="")
            messagebox.showerror(
                "Error al generar reporte",
                f"No se pudo generar el reporte de batería.\n\nDetalle: {err_msg}",
                parent=self,
            )

    def _on_battery_report_failed(self, error_message: str) -> None:
        self.battery_report_button.configure(state="normal")
        self.progress_label.configure(text="")
        messagebox.showerror(
            "Error al generar reporte",
            f"Ocurrió un error inesperado al generar el reporte de batería:\n\n{error_message}",
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
