"""Proveedor y clasificador de eventos críticos recientes de Windows (Fase F4).

Consulta exclusivamente mediante la allowlist de PowerShellQuery.CRITICAL_EVENTS
con ventana cerrada de 7 días y sanitización estricta de privacidad.
"""

from __future__ import annotations

import ipaddress
import logging
import re

from hardware_admin.domain.models import HealthStatus, WindowsCriticalEvent
from hardware_admin.infrastructure.powershell import (
    MalformedQueryOutput,
    PowerShellQuery,
    SafePowerShellRunner,
    parse_json_rows,
)

LOGGER = logging.getLogger(__name__)

#: Ventana temporal canónica de evaluación de eventos (fija de 7 días).
EVENT_WINDOW_DAYS: int = 7
DEFAULT_EVENT_WINDOW_DAYS: int = EVENT_WINDOW_DAYS

#: Patrones para redactar datos confidenciales y personales en los mensajes de eventos.
_PATH_REGEX = re.compile(r"[a-zA-Z]:\\[^ \t\r\n\"';<>|]+", re.IGNORECASE)
_USER_REGEX = re.compile(
    r"(?:Users|Usuarios)\\[A-Za-z0-9_\-\.]+|\b[A-Za-z0-9_\-\.]+\\[A-Za-z0-9_\-\.]+",
    re.IGNORECASE,
)
_IPV4_REGEX = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_MAC_REGEX = re.compile(r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}")
_SERIAL_REGEX = re.compile(
    r"(?:S/N|Serial(?:Number)?|Serie)\s*[:=]\s*[A-Za-z0-9\-]+", re.IGNORECASE
)
_IPV6_CANDIDATE_REGEX = re.compile(
    r"\b(?:[0-9a-fA-F]{1,4}:|:)(?:[0-9a-fA-F]{0,4}:){1,7}[0-9a-fA-F]{0,4}\b|::1\b"
)


def sanitize_event_message(raw_msg: str | None, max_chars: int = 500) -> str:
    """Sanea mensajes de eventos eliminando datos personales, rutas, IP (IPv4 e IPv6) y seriales.

    Trunca la salida a un máximo de `max_chars` caracteres conservando el resumen útil.
    """
    if not raw_msg:
        return ""

    text = str(raw_msg).strip()
    # Redactar rutas y directorios de usuario
    text = _USER_REGEX.sub("<usuario>", text)
    text = _PATH_REGEX.sub("<ruta_redactada>", text)
    text = _IPV4_REGEX.sub("<ip_redactada>", text)
    text = _MAC_REGEX.sub("<mac_redactada>", text)
    text = _SERIAL_REGEX.sub("<serial_redactado>", text)

    def _replace_ipv6(m: re.Match[str]) -> str:
        tok = m.group(0).strip(".,;:()[]\"'")
        if tok and tok != ":":
            try:
                ipaddress.IPv6Address(tok)
                return "<ip_redactada>"
            except ValueError:
                pass
        return m.group(0)

    text = _IPV6_CANDIDATE_REGEX.sub(_replace_ipv6, text)

    # Eliminar saltos de línea redundantes
    text = " ".join(text.split())

    if len(text) > max_chars:
        text = text[: max_chars - 3].rstrip() + "..."
    return text


class WindowsEventsProvider:
    """Proveedor aislado de lectura y diagnóstico de eventos del sistema Windows."""

    def __init__(self, runner: SafePowerShellRunner | None = None) -> None:
        self.runner = runner or SafePowerShellRunner()

    def get_recent_events(
        self, window_days: int = EVENT_WINDOW_DAYS
    ) -> tuple[list[WindowsCriticalEvent], HealthStatus, str | None, bool]:
        """Consulta eventos críticos de los últimos `window_days` días (fijo: 7 días).

        Devuelve: (eventos_saneados, estado, posible_problema, consulta_exitosa).
        Si la consulta falla por permisos o error, devuelve ERROR o NOT_SUPPORTED,
        NUNCA lista vacía ni estado NORMAL.
        """
        if window_days != EVENT_WINDOW_DAYS:
            raise ValueError(
                f"La ventana de eventos de Windows es fija de {EVENT_WINDOW_DAYS} días; no se permiten otros valores."
            )

        result = self.runner.run(PowerShellQuery.CRITICAL_EVENTS)
        if result.exit_code != 0:
            err_lower = (result.error or "").lower()
            is_perm = (
                "access is denied" in err_lower
                or "acceso denegado" in err_lower
                or "permission" in err_lower
                or "unauthorized" in err_lower
            )
            status = HealthStatus.NOT_SUPPORTED if is_perm else HealthStatus.ERROR
            sanitized_err = sanitize_event_message(result.error.strip() or "Error de consulta")
            error_detail = (
                "Permisos insuficientes para acceder al visor de eventos de Windows (Get-WinEvent); "
                "la consulta no pudo completarse y no certifica salud física"
                if is_perm
                else f"Fallo al consultar eventos críticos de Windows: {sanitized_err}"
            )
            return [], status, error_detail, False

        try:
            rows = parse_json_rows(result)
        except (MalformedQueryOutput, ValueError, TypeError, KeyError) as exc:
            sanitized_err = sanitize_event_message(str(exc))
            return (
                [],
                HealthStatus.ERROR,
                f"Salida inválida al consultar eventos críticos de Windows: {sanitized_err}",
                False,
            )

        if not rows:
            return (
                [],
                HealthStatus.NORMAL,
                (
                    f"Sin eventos críticos registrados en la ventana de {EVENT_WINDOW_DAYS} días; "
                    "la ausencia de eventos no certifica salud física"
                ),
                True,
            )

        events: list[WindowsCriticalEvent] = []
        has_whea = False
        has_storage = False
        has_bsod = False
        only_kp41 = True

        for row in rows:
            event_id = int(row.get("Id") or 0)
            provider = str(row.get("Proveedor") or "Desconocido").strip()
            level = str(row.get("Nivel") or "Error").strip()
            timestamp = str(row.get("Timestamp") or "").strip()
            raw_msg = str(row.get("Mensaje") or "")

            prov_lower = provider.lower()
            is_kernel_power = "kernel-power" in prov_lower
            is_kp41 = event_id == 41 and is_kernel_power

            if is_kp41:
                category = "REINICIO_INESPERADO"
                sanitized_msg = "reinicio inesperado detectado, causa no determinada (Event ID 41)"
            elif is_kernel_power:
                category = "KERNEL_POWER"
                only_kp41 = False
                sanitized_msg = sanitize_event_message(raw_msg)
            elif "whea" in prov_lower:
                category = "WHEA"
                has_whea = True
                only_kp41 = False
                sanitized_msg = sanitize_event_message(raw_msg)
            elif any(k in prov_lower for k in ("disk", "ntfs", "storahci", "storport", "volmgr")):
                category = "DISCO"
                has_storage = True
                only_kp41 = False
                sanitized_msg = sanitize_event_message(raw_msg)
            elif "bugcheck" in prov_lower or event_id == 1001:
                category = "BSOD"
                has_bsod = True
                only_kp41 = False
                sanitized_msg = sanitize_event_message(raw_msg)
            elif any(k in prov_lower for k in ("driver", "controlador")):
                category = "DRIVER"
                only_kp41 = False
                sanitized_msg = sanitize_event_message(raw_msg)
            else:
                category = "OTRO"
                only_kp41 = False
                sanitized_msg = sanitize_event_message(raw_msg)

            events.append(
                WindowsCriticalEvent(
                    timestamp=timestamp,
                    event_id=event_id,
                    level=level,
                    provider=provider,
                    message=sanitized_msg,
                    category=category,
                    is_kernel_power_41=is_kp41,
                )
            )

        # Reglas canónicas de severidad:
        # 1. Kernel-Power 41 aislado jamás puede elevar a CRITICAL
        if only_kp41:
            status = HealthStatus.WARNING
            problem = (
                f"{len(events)} reinicio(s) inesperado(s) detectado(s) (Event ID 41); "
                "causa física no determinada"
            )
        elif has_whea:
            status = HealthStatus.CRITICAL
            problem = (
                f"{len(events)} evento(s) crítico(s) del sistema, incluidos errores WHEA de arquitectura de hardware"
            )
        elif has_storage:
            status = HealthStatus.WARNING
            problem = (
                f"{len(events)} evento(s) crítico(s) del sistema, incluidos errores de almacenamiento o NTFS"
            )
        elif has_bsod:
            status = HealthStatus.WARNING
            problem = (
                f"{len(events)} evento(s) crítico(s) del sistema, incluidos eventos de pantalla azul (BugCheck)"
            )
        else:
            status = HealthStatus.WARNING
            problem = f"{len(events)} evento(s) crítico(s) registrados en el visor de eventos de Windows"

        return events, status, problem, True
