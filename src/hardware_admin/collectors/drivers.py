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


def normalize_device_id(raw_id: str | None) -> str:
    """Normaliza un identificador de hardware (DeviceID/InstanceId/PNPDeviceID)."""
    if not raw_id:
        return ""
    return str(raw_id).strip().upper().replace("/", "\\")


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

        # Correlación estricta y exclusiva por identificadores normalizados
        # Prohibido correlacionar por FriendlyName, nombre comercial o coincidencia parcial de texto.
        prob_result = self.runner.run(PowerShellQuery.PROBLEM_DEVICES)
        prob_rows = parse_json_rows(prob_result) if prob_result.exit_code == 0 else []

        problem_by_id: dict[str, dict[str, Any]] = {}
        for p in prob_rows:
            inst_id = normalize_device_id(p.get("InstanceId"))
            if inst_id:
                problem_by_id[inst_id] = p

        correlated_problems: list[dict[str, Any]] = []
        for d in rows:
            raw_dev_id = d.get("DeviceID") or d.get("HardWareID")
            norm_id = normalize_device_id(raw_dev_id)
            if not norm_id or norm_id not in problem_by_id:
                continue

            p_dev = problem_by_id[norm_id]
            p_code = p_dev.get("Problem")
            p_status = str(p_dev.get("Status") or "").strip().upper()
            is_signed = d.get("IsSigned")

            # Solo sugerir revisión si hay código de error PnP > 0, driver no firmado o dispositivo deshabilitado con fallo.
            # Una fecha antigua por sí sola NUNCA recomienda actualizar ni marca problema.
            has_pnp_error = p_code is not None and isinstance(p_code, int) and p_code > 0
            is_unhealthy = p_status != "OK" and p_status != ""
            if has_pnp_error or is_unhealthy or (is_signed is False):
                correlated_problems.append(
                    {
                        "DeviceName": d.get("Nombre") or d.get("DeviceName") or "Dispositivo",
                        "DeviceID": norm_id,
                        "DriverVersion": d.get("DriverVersion") or "No disponible",
                        "DriverDate": d.get("DriverDate") or "No disponible",
                        "ProblemCode": p_code,
                        "PnpStatus": p_status,
                        "IsSigned": is_signed,
                    }
                )

        status = HealthStatus.WARNING if (unsigned or correlated_problems) else HealthStatus.NORMAL

        facts: dict[str, Any] = {
            "Controladores": rows,
            "Consultados": len(rows),
            "No firmados": len(unsigned),
            "Dispositivos con fallo PnP": correlated_problems,
        }

        problem_parts: list[str] = []
        if unsigned:
            problem_parts.append(
                f"{len(unsigned)} controlador(es) no firmado(s) detectado(s)."
            )
        if correlated_problems:
            problem_parts.append(
                f"{len(correlated_problems)} controlador(es) correlacionado(s) con dispositivo con código de error PnP activo."
            )

        problem = " ".join(problem_parts) if problem_parts else None

        evidence_items = [
            EvidenceRecord(
                "PowerShell",
                "Win32_PnPSignedDriver",
                result.output or "[]",
                datetime.now(UTC),
                True,
            )
        ]
        if prob_result.output:
            evidence_items.append(
                EvidenceRecord(
                    "PowerShell",
                    "Get-PnpDevice (ProblemDevices)",
                    prob_result.output,
                    datetime.now(UTC),
                    True,
                )
            )

        return ComponentResult(
            self.component,
            "Controladores",
            facts,
            summary=f"{len(rows)} controladores"
            + (f" · {len(correlated_problems)} con fallo PnP" if correlated_problems else ""),
            status=status,
            possible_problem=problem,
            evidence=tuple(evidence_items),
        )

