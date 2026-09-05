"""Motor determinista que transforma evidencia en una conclusión explicable."""

from collections.abc import Sequence
from datetime import UTC, datetime

from hardware_admin.diagnostics.recommendations import build_recommendations
from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    DiagnosticReport,
    HealthStatus,
)


class RuleBasedDiagnosticEngine:
    def build_report(
        self,
        results: Sequence[ComponentResult],
        symptom: str | None = None,
        expected_device: str | None = None,
    ) -> DiagnosticReport:
        now = datetime.now(UTC)
        evidence_dates = [
            evidence.collected_at for result in results for evidence in result.evidence
        ]
        started = min(evidence_dates, default=now)
        failures = [result for result in results if result.status is HealthStatus.ERROR]
        alerts = [
            result
            for result in results
            if result.status in {HealthStatus.WARNING, HealthStatus.CRITICAL}
        ]

        conclusion_parts: list[str] = []
        by_kind = {result.component: result for result in results}
        memory = by_kind.get(ComponentKind.MEMORY)
        cpu = by_kind.get(ComponentKind.CPU)
        memory_alert = memory and memory.status in {
            HealthStatus.WARNING,
            HealthStatus.CRITICAL,
        }
        cpu_alert = cpu and cpu.status in {HealthStatus.WARNING, HealthStatus.CRITICAL}
        if memory_alert and cpu_alert and memory and cpu:
            conclusion_parts.append(
                "La causa más probable de lentitud es la saturación de recursos: "
                f"CPU ({cpu.summary.lower()}) y memoria RAM ({memory.summary.lower()})."
            )
        elif memory_alert and memory:
            conclusion_parts.append(
                f"La causa más probable de lentitud es la memoria RAM ({memory.summary.lower()})."
            )
        elif cpu_alert and cpu:
            conclusion_parts.append(
                f"La causa más probable de lentitud es la carga de CPU ({cpu.summary.lower()})."
            )

        network = by_kind.get(ComponentKind.NETWORK)
        network_alert = network and network.status in {
            HealthStatus.WARNING,
            HealthStatus.CRITICAL,
        }
        if network_alert and network:
            if "APIPA" in (network.possible_problem or "") or "APIPA" in str(network.facts):
                conclusion_parts.append(
                    "Problema de red detectado (Caso C1): dirección APIPA (169.254.x.x) sin concesión DHCP "
                    "ni puerta de enlace. Se sugiere verificar el router/DHCP y ejecutar manualmente "
                    "'ipconfig /all', 'ipconfig /release' y 'ipconfig /renew'."
                )
            elif "DNS" in (network.possible_problem or "") or "DNS" in str(network.facts.get("Diagnóstico de red", "")):
                conclusion_parts.append(
                    "Problema de red detectado: la conectividad IP externa responde pero falla la resolución DNS. "
                    "Se sugiere verificar los servidores DNS o ejecutar manualmente 'ipconfig /flushdns'."
                )

        pci = by_kind.get(ComponentKind.PCI)
        pci_alert = pci and pci.status in {HealthStatus.WARNING, HealthStatus.CRITICAL}
        pci_c2_handled = False
        if pci_alert and pci and (pci.facts.get("Caso") == "C2" or "adaptador de red PCIe" in (pci.possible_problem or "")):
            conclusion_parts.append(
                "Problema de hardware localizado (Caso C2): anomalía en adaptador de red PCIe. "
                "El resto de dispositivos se reporta normal; se sugiere revisar el código en el "
                "Administrador de dispositivos, comprobar la inserción en la ranura PCIe y actualizar el controlador."
            )
            pci_c2_handled = True

        usb = by_kind.get(ComponentKind.USB)
        usb_alert = usb and usb.status in {HealthStatus.WARNING, HealthStatus.CRITICAL}
        usb_c3_handled = False
        if usb_alert and usb and (usb.facts.get("Caso") == "C3" or "periférico USB" in (usb.possible_problem or "")):
            conclusion_parts.append(
                "Problema de hardware localizado (Caso C3): falla aislada en periférico o memoria USB. "
                "El controlador anfitrión USB funciona correctamente y el bus principal no está degradado; "
                "se sugiere verificar el periférico concreto o su controlador sin condenar el bus."
            )
            usb_c3_handled = True

        handled_components = {ComponentKind.CPU, ComponentKind.MEMORY, ComponentKind.NETWORK}
        if pci_c2_handled:
            handled_components.add(ComponentKind.PCI)
        if usb_c3_handled:
            handled_components.add(ComponentKind.USB)

        other_alerts = [
            result
            for result in alerts
            if result.component not in handled_components
        ]
        if network_alert and network and not any("Problema de red detectado" in p for p in conclusion_parts):
            other_alerts.insert(0, network)

        if other_alerts:
            descriptions = "; ".join(
                f"{result.name}: {result.possible_problem or result.summary}"
                for result in other_alerts
            )
            conclusion_parts.append(f"También se detectó: {descriptions}.")
        if alerts and not conclusion_parts:
            conclusion_parts.append(
                "Se detectaron advertencias que requieren revisión según la matriz."
            )
        if not alerts:
            conclusion_parts.append(
                "No se observan anomalías en los indicadores consultados."
            )
        if failures:
            conclusion_parts.append(
                "Algunas comprobaciones no pudieron completarse y no deben interpretarse como sanas."
            )
        # Un fallo de consulta no equivale a hardware sano: si el sintoma persiste,
        # la orientacion adicional se mantiene aunque alguna comprobacion fallara.
        if symptom and not alerts:
            conclusion_parts.append(
                "Como el síntoma persiste sin anomalías básicas, se requiere "
                "diagnóstico adicional de temperatura, fuente de alimentación, GPU, "
                "controladores, eventos del sistema, memoria RAM y el resto del hardware."
            )
            gpu = by_kind.get(ComponentKind.MONITOR_GPU)
            if gpu and gpu.status is HealthStatus.NORMAL:
                conclusion_parts.append(
                    "Para el subsistema de GPU y gráficos, con estado en OK pero síntomas reportados, "
                    "se recomienda revisar la compatibilidad de DirectX, ajustes gráficos por aplicación, "
                    "instalación limpia de controladores y estabilidad de alimentación PCIe."
                )
        if expected_device and not alerts:
            conclusion_parts.append(
                f"El dispositivo esperado («{expected_device}») no se usó para "
                "condenar ningún bus: su ausencia requiere confirmación por ID."
            )

        unsupported = [
            result
            for result in results
            if result.status is HealthStatus.NOT_SUPPORTED or not result.is_supported
        ]
        if unsupported and not alerts and not failures:
            conclusion_parts.append(
                "Algunas comprobaciones no son soportadas por este hardware o versión de Windows."
            )

        limitations_list = [
            f"{result.name}: {result.possible_problem or 'consulta no disponible'}"
            for result in failures
        ]
        limitations_list.extend(
            f"{result.name}: función no soportada en este entorno"
            for result in unsupported
        )
        limitations = tuple(limitations_list)
        return DiagnosticReport(
            started_at=started,
            completed_at=now,
            results=tuple(results),
            conclusion=" ".join(conclusion_parts),
            limitations=limitations,
            symptom=symptom,
            expected_device=expected_device,
            recommendations=build_recommendations(results, symptom, expected_device),
        )
