"""Paleta centralizada inspirada en la maqueta aprobada."""

from hardware_admin.domain.models import ComponentKind, HealthStatus

BACKGROUND = "#0A1523"
SURFACE = "#0D1C2C"
SURFACE_ALT = "#122436"
SURFACE_HOVER = "#17324B"
ROW = "#0E1E2E"
ROW_ALT = "#111F30"
BORDER = "#1E3549"
BORDER_SOFT = "#182C3F"
ACCENT = "#1F6FEB"
ACCENT_HOVER = "#1A5FCC"
ACCENT_TEXT = "#4A9EFF"
TEXT = "#E8F0F8"
MUTED = "#8FA5BA"
ICON = "#A8C0D8"
GREEN = "#3FB950"
YELLOW = "#E3B341"
RED = "#F85149"
TERMINAL = "#050C13"

CONSOLE_TEXT = "#C9D8E8"
CONSOLE_PROMPT = "#56D4DD"
CONSOLE_KEY = "#7F9CB8"
CONSOLE_ERROR = "#F85149"

#: Fondo, borde y color de texto de la píldora de estado global de la cabecera.
PILL_STYLES: dict[str, tuple[str, str, str]] = {
    "idle": ("#101E2E", "#26405A", MUTED),
    "busy": ("#2A2413", "#6B551A", YELLOW),
    "ok": ("#0E2A18", "#2D7D3A", GREEN),
    "warn": ("#2A2413", "#6B551A", YELLOW),
    "error": ("#2C1416", "#7D2D30", RED),
}

#: Color de acento de cada componente, usado en iconos, tarjetas y matriz.
COMPONENT_COLORS: dict[ComponentKind, str] = {
    ComponentKind.SYSTEM: "#4A9EFF",
    ComponentKind.CPU: "#4A9EFF",
    ComponentKind.MEMORY: "#3FB950",
    ComponentKind.DISK: "#A371F7",
    ComponentKind.NETWORK: "#4A9EFF",
    ComponentKind.USB: "#56D4DD",
    ComponentKind.PCI: "#56D4DD",
    ComponentKind.DRIVER: "#A8C0D8",
    ComponentKind.PROBLEM_DEVICE: "#E3B341",
    ComponentKind.MONITOR_GPU: "#4A9EFF",
    ComponentKind.IO: "#3FB950",
}

#: Fondo del recuadro de icono de las tarjetas de resumen.
CARD_ICON_BACKGROUNDS: dict[ComponentKind, str] = {
    ComponentKind.CPU: "#14304F",
    ComponentKind.MEMORY: "#173D22",
    ComponentKind.DISK: "#33235C",
    ComponentKind.NETWORK: "#14304F",
}

STATUS_COLORS: dict[HealthStatus, str] = {
    HealthStatus.UNKNOWN: MUTED,
    HealthStatus.NORMAL: GREEN,
    HealthStatus.WARNING: YELLOW,
    HealthStatus.CRITICAL: RED,
    HealthStatus.ERROR: RED,
}
