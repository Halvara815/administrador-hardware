"""Exportación JSON del diagnóstico, con esquema versionado.

`SCHEMA_VERSION` permite que una herramienta futura lea exportaciones antiguas
o avise de incompatibilidad, sin necesidad de migraciones ni base de datos.

La identidad del equipo y del usuario puede omitirse: el plan exige poder
anonimizar las copias que se comparten.
"""

from __future__ import annotations

import getpass
import json
import platform
import re
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hardware_admin import __version__
from hardware_admin.domain.models import DiagnosticReport, HealthStatus
from hardware_admin.reports._logging import log_export

#: Versión del esquema de exportación. Subir sólo ante cambios incompatibles.
SCHEMA_VERSION = "1.0"

#: Marca que sustituye equipo y usuario cuando se anonimiza la copia.
OMITTED = "(omitido)"


_VERSION_OR_MASK_KEY_REGEX = re.compile(
    r"(?i)(?:m[aá]scara|mask|subred|subnet|versi[oó]n|version|firmware|bios|build|release)"
)


def _is_network_mask(ip: str) -> bool:
    octets = ip.split(".")
    if len(octets) != 4:
        return False
    try:
        nums = [int(o) for o in octets]
    except ValueError:
        return False
    if any(n < 0 or n > 255 for n in nums):
        return False
    val = (nums[0] << 24) | (nums[1] << 16) | (nums[2] << 8) | nums[3]
    if val == 0:
        return True
    inverted = (~val) & 0xFFFFFFFF
    return (inverted & (inverted + 1)) == 0


def _redact_ip_match(match: re.Match[str], field_name: str | None) -> str:
    ip_str = match.group(0)
    if _is_network_mask(ip_str):
        return ip_str
    if field_name and _VERSION_OR_MASK_KEY_REGEX.search(field_name):
        return ip_str
    return "[IP-redacted]"


def _redact(value: str | None, field_name: str | None = None) -> str:
    if value is None:
        return "No disponible"
    text = str(value)
    patterns = [
        (r"(?i)C:\\Users\\[^\\]+", lambda _: r"C:\Users\<usuario>"),
        (r"(?i)\\Users\\[^\\]+", lambda _: r"\Users\<usuario>"),
        (r"(?i)C:/Users/[^/]+", lambda _: "C:/Users/<usuario>"),
        (r"(?i)hostname|computername", lambda _: "[redacted]"),
        (r"(?i)\b[A-Fa-f0-9]{2}(-[A-Fa-f0-9]{2}){5}\b", lambda _: "[MAC-redacted]"),
        (r"(?i)\b(?:\d{1,3}\.){3}\d{1,3}\b", lambda m: _redact_ip_match(m, field_name)),
    ]
    for pattern, repl in patterns:
        text = re.sub(pattern, repl, text)
    return text


def _machine(include_identity: bool = True) -> str:
    try:
        name = socket.gethostname()
        return name if include_identity else _redact(name)
    except OSError:
        return "No disponible"


def _user(include_identity: bool = True) -> str:
    # getpass consulta variables de entorno y el registro de usuarios: puede
    # fallar en sesiones de servicio o sin perfil, y eso no es un error grave.
    try:
        username = getpass.getuser()
        return username if include_identity else _redact(username)
    except (OSError, KeyError, ImportError):
        return "No disponible"


def _public_facts(facts: dict[str, Any], include_identity: bool = True) -> dict[str, Any]:
    """Descarta las series con guion bajo y anonimiza según include_identity."""

    def _process_item(val: Any, key_name: str | None) -> Any:
        if isinstance(val, dict):
            return {
                k: _process_item(v, str(k))
                for k, v in val.items()
                if not str(k).startswith("_")
            }
        elif isinstance(val, list):
            return [_process_item(elem, key_name) for elem in val]
        elif isinstance(val, str) and not include_identity:
            return _redact(val, key_name)
        return val

    return {
        key: _process_item(value, str(key))
        for key, value in facts.items()
        if not str(key).startswith("_")
    }


def build_payload(
    report: DiagnosticReport,
    include_identity: bool = True,
) -> dict[str, Any]:
    """Compone el documento exportable a partir del diagnóstico.

    Separa `resultados` de `errores_de_consulta`: una consulta que no se
    completó deja el componente sin evaluar y no debe leerse como hallazgo de
    hardware. `cobertura` dice cuánto se pudo consultar realmente.
    """
    failures = [item for item in report.results if item.status is HealthStatus.ERROR]
    alerts = [
        item
        for item in report.results
        if item.status in {HealthStatus.WARNING, HealthStatus.CRITICAL}
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "app_version": __version__,
        "generated_at": datetime.now(UTC).isoformat(),
        "equipo": _machine(include_identity=True) if include_identity else OMITTED,
        "usuario": _user(include_identity=True) if include_identity else OMITTED,
        "sistema_operativo": f"{platform.system()} {platform.release()}",
        "analisis": {
            "inicio": report.started_at.isoformat(),
            "fin": report.completed_at.isoformat(),
        },
        "contexto": {
            "sintoma": report.symptom,
            "dispositivo_esperado": report.expected_device,
        },
        "resultados": [
            {
                "componente": item.component.value,
                "nombre": item.name,
                "estado": item.status.value,
                "confianza": item.confidence.value,
                "soportado": item.is_supported,
                "resumen": item.summary,
                "posible_problema": item.possible_problem,
                "mediciones": [
                    {
                        "nombre": m.name,
                        "valor": m.value,
                        "unidad": m.unit,
                        "rango_esperado": list(m.expected_range) if m.expected_range else None,
                        "duracion_segundos": m.duration_seconds,
                    }
                    for m in item.measurements
                ],
                "datos": _public_facts(item.facts, include_identity),
                "evidencia": [
                    {
                        "fuente": record.source,
                        "consulta": record.query,
                        "salida": record.output,
                        "momento": record.collected_at.isoformat(),
                        "exito": record.succeeded,
                    }
                    for record in item.evidence
                ],
            }
            for item in report.results
        ],
        "errores_de_consulta": [
            {
                "componente": item.component.value,
                "nombre": item.name,
                "detalle": item.possible_problem or "La consulta no se completó",
            }
            for item in failures
        ],
        "recomendaciones": [
            {
                "componente": item.component.value,
                "titulo": item.title,
                "causa": item.cause,
                "pasos": list(item.steps),
                "fundamento": item.rationale,
                "comprobacion_posterior": item.verification,
                "modifica_el_sistema": item.modifies_system,
            }
            for item in report.recommendations
        ],
        "conclusion": report.conclusion,
        "cobertura": {
            "componentes_consultados": len(report.results),
            "consultas_fallidas": len(failures),
            "componentes_con_anomalia": len(alerts),
            "componentes_no_soportados": len(
                [
                    r
                    for r in report.results
                    if r.status is HealthStatus.NOT_SUPPORTED or not r.is_supported
                ]
            ),
            "nota": (
                "Una consulta fallida deja el componente sin evaluar; "
                "no equivale a ausencia de problemas."
            ),
        },
        "limitaciones": list(report.limitations),
    }


def export_json(
    report: DiagnosticReport,
    destination: str | Path,
    include_identity: bool = True,
) -> Path:
    """Guarda el diagnóstico como JSON en UTF-8 y devuelve la ruta escrita."""
    path = Path(destination)
    payload = build_payload(report, include_identity)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log_export(path, "json", include_identity)
    return path
