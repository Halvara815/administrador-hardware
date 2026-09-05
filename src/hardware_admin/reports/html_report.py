"""Exportación de un diagnóstico autocontenido a HTML."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from hardware_admin import __version__
from hardware_admin.domain.models import DiagnosticReport, HealthStatus

_STATUS_LABELS = {
    HealthStatus.UNKNOWN: "Sin analizar",
    HealthStatus.NORMAL: "Normal",
    HealthStatus.WARNING: "Advertencia",
    HealthStatus.CRITICAL: "Problema",
    HealthStatus.ERROR: "Error de consulta",
}


def _render_value(value: Any) -> str:
    if isinstance(value, list):
        if not value:
            return "Sin elementos"
        rows = []
        for item in value:
            if isinstance(item, dict):
                rows.append(" | ".join(f"{key}: {val}" for key, val in item.items()))
            else:
                rows.append(str(item))
        return "<br>".join(html.escape(row) for row in rows)
    return html.escape(str(value))


def _context_items(report: DiagnosticReport) -> list[str]:
    """Devuelve las líneas de contexto del usuario para el reporte HTML."""
    items: list[str] = []
    if report.symptom:
        items.append(
            f"<li><strong>Síntoma informado:</strong> {html.escape(report.symptom)}</li>"
        )
    if report.expected_device:
        items.append(
            "<li><strong>Dispositivo esperado:</strong> "
            f"{html.escape(report.expected_device)}</li>"
        )
    return items


def export_html(report: DiagnosticReport, destination: str | Path) -> Path:
    path = Path(destination)
    matrix_rows = []
    recommendation_blocks = []
    for item in report.recommendations:
        steps = "".join(f"<li>{html.escape(step)}</li>" for step in item.steps)
        # Advertir de lo que altera el equipo: la aplicacion lo propone,
        # nunca lo ejecuta, y el lector debe saberlo antes de escribirlo.
        badge = (
            "<p><strong>Modifica el sistema.</strong> La aplicación no ejecuta este "
            "procedimiento: descríbalo antes de aplicarlo usted mismo.</p>"
            if item.modifies_system
            else "<p><small>Sólo consulta: no altera el equipo.</small></p>"
        )
        recommendation_blocks.append(
            f"<article><h3>{html.escape(item.title)}</h3>"
            f"<p><strong>Causa:</strong> {html.escape(item.cause)}</p>"
            f"<ol>{steps}</ol>"
            f"<p><strong>Fundamento:</strong> {html.escape(item.rationale)}</p>"
            f"<p><strong>Comprobación posterior:</strong> {html.escape(item.verification)}</p>"
            f"{badge}</article>"
        )
    recommendation_section = (
        f"<section><h2>Recomendaciones</h2>{''.join(recommendation_blocks)}</section>"
        if recommendation_blocks
        else ""
    )

    detail_sections = []
    for result in report.results:
        status = _STATUS_LABELS[result.status]
        matrix_rows.append(
            "<tr>"
            f"<td>{html.escape(result.name)}</td>"
            f"<td>{html.escape(result.summary)}</td>"
            f"<td class='{result.status.value}'>{status}</td>"
            f"<td>{html.escape(result.possible_problem or '—')}</td>"
            "</tr>"
        )
        # Las claves con guion bajo son series numericas para los graficos:
        # datos legibles por maquina, no texto del reporte.
        facts = "".join(
            f"<tr><th>{html.escape(str(key))}</th><td>{_render_value(value)}</td></tr>"
            for key, value in result.facts.items()
            if not str(key).startswith("_")
        )
        evidence = "\n\n".join(
            f"> {item.source}: {item.query}\n{item.output}" for item in result.evidence
        )
        detail_sections.append(
            f"<section><h2>{html.escape(result.name)}</h2>"
            f"<table class='facts'>{facts}</table>"
            f"<details><summary>Evidencia técnica</summary>"
            f"<pre>{html.escape(evidence)}</pre></details></section>"
        )

    limitations = "".join(f"<li>{html.escape(item)}</li>" for item in report.limitations)
    context_items = list(_context_items(report))
    context_section = (
        f"<section><h2>Contexto del usuario</h2><ul>{''.join(context_items)}</ul></section>"
        if context_items
        else ""
    )
    document = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reporte de diagnóstico de hardware</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;background:#f4f7fb;color:#172235;margin:0}}
main{{max-width:1100px;margin:auto;padding:32px}} header,section{{background:white;padding:24px;
border-radius:12px;margin-bottom:20px;box-shadow:0 2px 10px #16223615}}
h1{{margin:0 0 8px;color:#0b5fc6}} table{{border-collapse:collapse;width:100%}}
th,td{{padding:10px;border-bottom:1px solid #dfe7f1;text-align:left;vertical-align:top}}
.normal{{color:#16863b;font-weight:700}} .warning{{color:#a66a00;font-weight:700}}
.critical,.error{{color:#b42318;font-weight:700}} pre{{white-space:pre-wrap;background:#09111c;
color:#d9e6f5;padding:16px;border-radius:8px;max-height:420px;overflow:auto}}
.conclusion{{border-left:5px solid #1478e8}} small{{color:#607086}}
article{{border-left:4px solid #1478e8;padding:4px 0 4px 16px;margin:18px 0}}
article h3{{margin:0 0 8px;color:#0b5fc6}} article ol{{margin:8px 0;padding-left:22px}}
@media print{{body{{background:white}} header,section{{box-shadow:none;border:1px solid #ddd}}}}
</style></head><body><main>
<header><h1>Administrador de Hardware</h1><p>Reporte de diagnóstico · versión {__version__}</p>
<small>Generado: {report.completed_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")}</small></header>
<section><h2>Matriz de diagnóstico</h2><table><thead><tr><th>Componente</th>
<th>Evidencia</th><th>Estado</th><th>Posible problema</th></tr></thead>
<tbody>{"".join(matrix_rows)}</tbody></table></section>
<section class="conclusion"><h2>Conclusión</h2><p>{html.escape(report.conclusion)}</p></section>
{context_section}
{recommendation_section}
{f"<section><h2>Limitaciones</h2><ul>{limitations}</ul></section>" if limitations else ""}
{"".join(detail_sections)}
</main></body></html>"""
    path.write_text(document, encoding="utf-8")
    return path
