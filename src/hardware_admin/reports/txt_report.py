"""Exportación en texto plano, legible sin navegador ni herramientas.

Comparte el mismo contenido que el JSON, incluida la posibilidad de omitir
equipo y usuario al compartir la copia.
"""

from __future__ import annotations

from pathlib import Path

from hardware_admin.domain.models import DiagnosticReport
from hardware_admin.reports._logging import log_export
from hardware_admin.reports.json_report import build_payload
from hardware_admin.services.upgrade_advisor import format_upgrade_advice

_ESTADOS = {
    "unknown": "Sin analizar",
    "normal": "Normal",
    "warning": "Advertencia",
    "critical": "Problema",
    "error": "Error de consulta",
    "not_supported": "No soportado",
    "cancelled": "Cancelado",
}


def render_text(report: DiagnosticReport, include_identity: bool = True) -> str:
    """Compone el reporte como texto plano a partir del mismo documento del JSON."""
    payload = build_payload(report, include_identity)
    lines: list[str] = [
        "REPORTE DE DIAGNÓSTICO DE HARDWARE",
        "==================================",
        "",
        f"Versión de la aplicación : {payload['app_version']}",
        f"Esquema del reporte      : {payload['schema_version']}",
        f"Generado                 : {payload['generated_at']}",
        f"Equipo                   : {payload['equipo']}",
        f"Usuario                  : {payload['usuario']}",
        f"Sistema operativo        : {payload['sistema_operativo']}",
        (
            f"Análisis                 : {payload['analisis']['inicio']} → "
            f"{payload['analisis']['fin']}"
        ),
        "",
    ]

    contexto = payload["contexto"]
    if contexto["sintoma"] or contexto["dispositivo_esperado"]:
        lines.extend(["CONTEXTO APORTADO POR EL USUARIO", "-" * 32])
        if contexto["sintoma"]:
            lines.append(f"  Síntoma observado    : {contexto['sintoma']}")
        if contexto["dispositivo_esperado"]:
            lines.append(f"  Dispositivo esperado : {contexto['dispositivo_esperado']}")
        lines.append("")

    lines.extend(["MATRIZ DE DIAGNÓSTICO", "-" * 21])
    for item in payload["resultados"]:
        estado = _ESTADOS.get(item["estado"], item["estado"])
        lines.append(f"  {item['nombre']:<30} {estado:<18} {item['resumen']}")
        if item["posible_problema"]:
            lines.append(f"      posible problema: {item['posible_problema']}")
    lines.append("")

    lines.extend(["CONCLUSIÓN", "-" * 10, f"  {payload['conclusion']}", ""])

    if payload["recomendaciones"]:
        lines.extend(["RECOMENDACIONES", "-" * 15])
        for number, item in enumerate(payload["recomendaciones"], start=1):
            lines.append(f"  {number}. {item['titulo']}  [{item['componente']}]")
            lines.append(f"     Causa: {item['causa']}")
            lines.append("     Pasos:")
            lines.extend(
                f"       {index}. {step}" for index, step in enumerate(item["pasos"], start=1)
            )
            lines.append(f"     Fundamento: {item['fundamento']}")
            lines.append(f"     Comprobación posterior: {item['comprobacion_posterior']}")
            lines.append(
                "     ! MODIFICA EL SISTEMA: la aplicación no ejecuta este "
                "procedimiento; lo aplica usted."
                if item["modifica_el_sistema"]
                else "     Sólo consulta: no altera el equipo."
            )
            lines.append("")

    advisor = payload.get("asesor_de_ampliaciones")
    if isinstance(advisor, dict) and advisor:
        lines.extend([format_upgrade_advice(advisor), ""])

    if payload["errores_de_consulta"]:
        lines.extend(["CONSULTAS QUE NO SE COMPLETARON", "-" * 30])
        lines.extend(
            f"  - {item['nombre']}: {item['detalle']}" for item in payload["errores_de_consulta"]
        )
        lines.append("")

    if payload["limitaciones"]:
        lines.extend(["LIMITACIONES", "-" * 12])
        lines.extend(f"  - {item}" for item in payload["limitaciones"])
        lines.append("")

    cobertura = payload["cobertura"]
    lines.extend(
        [
            "COBERTURA",
            "-" * 9,
            f"  Componentes consultados : {cobertura['componentes_consultados']}",
            f"  Consultas fallidas      : {cobertura['consultas_fallidas']}",
            f"  Componentes con anomalía: {cobertura['componentes_con_anomalia']}",
            f"  Nota: {cobertura['nota']}",
            "",
            "Este reporte describe los indicadores consultados en el momento del",
            "análisis. La ausencia de anomalías no equivale a hardware sin fallas.",
        ]
    )
    return "\n".join(lines)


def export_txt(
    report: DiagnosticReport,
    destination: str | Path,
    include_identity: bool = True,
) -> Path:
    """Guarda el diagnóstico como texto plano en UTF-8."""
    path = Path(destination)
    path.write_text(render_text(report, include_identity), encoding="utf-8")
    log_export(path, "txt", include_identity)
    return path
