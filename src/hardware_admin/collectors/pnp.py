"""Recolector especializado para dispositivos PnP (USB, PCI/PCIe y dispositivos con problemas)."""

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


class PnpDeviceCollector:
    """Recolector PnP con diagnóstico localizado y correlación de identificadores de hardware."""

    def __init__(
        self,
        runner: SafePowerShellRunner,
        component: ComponentKind,
        name: str,
        query: PowerShellQuery,
    ) -> None:
        self.runner = runner
        self.component = component
        self.name = name
        self.query = query

    def collect(self) -> ComponentResult:
        result = self.runner.run(self.query)
        if result.exit_code != 0:
            error_msg = result.error or "La consulta no devolvió información"
            return ComponentResult(
                component=self.component,
                name=self.name,
                facts={"Resultado": "No disponible", "Detalle": error_msg},
                summary="No disponible",
                status=HealthStatus.ERROR,
                possible_problem="No fue posible consultar el subsistema PnP de Windows",
                evidence=(
                    EvidenceRecord(
                        "PowerShell",
                        self.query.value,
                        error_msg,
                        datetime.now(UTC),
                        False,
                    ),
                ),
            )

        rows = parse_json_rows(result)

        normalized_rows: list[dict[str, Any]] = []
        problems: list[dict[str, Any]] = []
        host_controllers: list[dict[str, Any]] = []
        peripherals: list[dict[str, Any]] = []

        for row in rows:
            status_val = str(row.get("Status", "OK")).strip()
            instance_id = str(row.get("InstanceId") or "No disponible")
            friendly_name = str(row.get("FriendlyName") or instance_id or "Sin nombre")
            dev_class = str(row.get("Class") or "No disponible")
            problem_code = row.get("Problem")
            is_ok = status_val.upper() == "OK" and (problem_code is None or problem_code == 0)

            device_entry = {
                "Dispositivo": friendly_name,
                "Clase": dev_class,
                "Estado": status_val,
                "ID": instance_id,
                "Código": problem_code if problem_code is not None else "—",
            }
            normalized_rows.append(device_entry)

            if not is_ok or self.component is ComponentKind.PROBLEM_DEVICE:
                problems.append(device_entry)

            # Clasificación de topología para USB
            if self.component is ComponentKind.USB:
                if "ROOT_HUB" in instance_id.upper() or "HOST" in friendly_name.upper():
                    host_controllers.append(device_entry)
                else:
                    peripherals.append(device_entry)

        status = HealthStatus.CRITICAL if problems else HealthStatus.NORMAL
        possible_problem: str | None = None
        case_tag: str | None = None

        # Diagnóstico localizado según componente
        if self.component is ComponentKind.USB:
            if problems:
                # Caso C3: Comprobar si los controladores anfitriones están sanos y la falla es sólo de periférico
                host_problems = [h for h in host_controllers if h in problems]
                peripheral_problems = [p for p in peripherals if p in problems]

                if peripheral_problems and not host_problems:
                    # Caso C3 verificado: Periférico USB con error sin condenar todo el bus
                    first_p = peripheral_problems[0]
                    possible_problem = (
                        f"Problema localizado en periférico USB ({first_p['Dispositivo']}, "
                        f"ID: {first_p['ID']}, Código: {first_p['Código']}). "
                        f"El controlador anfitrión USB funciona correctamente; el bus no está degradado."
                    )
                    case_tag = "C3"
                else:
                    possible_problem = f"{len(problems)} dispositivo(s) USB con problema de configuración o controlador."
            summary = (
                f"{len(rows)} disp. · {len(problems)} con error"
                if problems
                else f"{len(rows)} disp. USB conectados"
            )
            if not rows:
                # Caso «USB ausente»: separar disponibilidad de severidad. Que la
                # consulta no devuelva filas no prueba que el equipo carezca de USB
                # ni que un dispositivo esperado no haya existido nunca.
                case_tag = "USB-AUSENTE"
                summary = "Sin dispositivos USB en la consulta"

        elif self.component is ComponentKind.PCI:
            if problems:
                first_p = problems[0]
                is_nic = any(term in first_p["Clase"].upper() or term in first_p["Dispositivo"].upper() for term in ("NET", "RED", "ETHERNET", "NETWORK", "WIFI", "WIRELESS"))
                if is_nic:
                    case_tag = "C2"
                    possible_problem = (
                        f"Problema localizado en adaptador de red PCIe ({first_p['Dispositivo']}, "
                        f"ID: {first_p['ID']}, Código: {first_p['Código']}). "
                        f"Requiere comprobación de inserción física, estado en Administrador de dispositivos o actualización de controlador."
                    )
                else:
                    possible_problem = (
                        f"Problema localizado en dispositivo PCIe ({first_p['Dispositivo']}, "
                        f"ID: {first_p['ID']}, Código: {first_p['Código']})."
                    )
            summary = (
                f"{len(rows)} disp. · {len(problems)} con error"
                if problems
                else f"{len(rows)} disp. PCI/PCIe activos"
            )

        elif self.component is ComponentKind.PROBLEM_DEVICE:
            summary = f"{len(problems)} errores detectados"
            possible_problem = f"{len(problems)} dispositivo(s) con error en el Administrador de dispositivos" if problems else None

        facts: dict[str, Any] = {
            "Dispositivos": normalized_rows,
            "Total": len(rows),
            "Con problemas": len(problems),
        }
        if case_tag:
            facts["Caso"] = case_tag
        if self.component is ComponentKind.USB and not rows:
            facts["Limitación de cobertura"] = (
                "La consulta no devolvió dispositivos USB. Una lista vacía no demuestra "
                "ausencia física ni que un dispositivo esperado no haya existido: "
                "confirmar por ID de instancia antes de descartar el bus."
            )
        if self.component is ComponentKind.USB and host_controllers:
            facts["Controladores anfitriones"] = len(host_controllers)
            facts["Periféricos conectados"] = len(peripherals)

        evidence = (
            EvidenceRecord(
                "PowerShell",
                self.query.value,
                result.output or "[]",
                datetime.now(UTC),
                True,
            ),
        )

        return ComponentResult(
            self.component,
            self.name,
            facts,
            summary=summary,
            status=status,
            possible_problem=possible_problem,
            evidence=evidence,
        )

