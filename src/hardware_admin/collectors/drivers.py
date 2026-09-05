"""Recolector especializado para controladores (drivers) del sistema."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    EvidenceRecord,
    HealthStatus,
)
from hardware_admin.infrastructure.powershell import (
    PowerShellQuery,
    SafePowerShellRunner,
    parse_json_rows,
)


class DriverCollector:
    """Recolector de controladores firmados y catálogo del sistema."""

    component = ComponentKind.DRIVER

    def __init__(self, runner: SafePowerShellRunner) -> None:
        self.runner = runner

    def collect(self) -> ComponentResult:
        result = self.runner.run(PowerShellQuery.DRIVERS)
        if result.exit_code != 0:
            error_msg = result.error or "La consulta no devolvió información"
            return ComponentResult(
                component=self.component,
                name="Controladores",
                facts={"Resultado": "No disponible", "Detalle": error_msg},
                summary="No disponible",
                status=HealthStatus.ERROR,
                possible_problem="No fue posible consultar los controladores de Windows",
                evidence=(
                    EvidenceRecord(
                        "PowerShell",
                        "Win32_PnPSignedDriver",
                        error_msg,
                        datetime.now(UTC),
                        False,
                    ),
                ),
            )

        rows = parse_json_rows(result)
        unsigned = [row for row in rows if row.get("IsSigned") is False]
        status = HealthStatus.WARNING if unsigned else HealthStatus.NORMAL

        facts: dict[str, Any] = {
            "Controladores": rows,
            "Consultados": len(rows),
            "No firmados": len(unsigned),
        }

        problem = (
            f"{len(unsigned)} controlador(es) no firmado(s) detectado(s). Podrían causar inestabilidad o rechazo de firma en 64 bits."
            if unsigned
            else None
        )

        return ComponentResult(
            self.component,
            "Controladores",
            facts,
            summary=f"{len(rows)} controladores",
            status=status,
            possible_problem=problem,
            evidence=(
                EvidenceRecord(
                    "PowerShell",
                    "Win32_PnPSignedDriver",
                    result.output or "[]",
                    datetime.now(UTC),
                    True,
                ),
            ),
        )

