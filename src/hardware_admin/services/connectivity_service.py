"""Servicio de verificación escalonada de conectividad de red y diagnóstico determinista."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from hardware_admin.domain.models import (
    ConnectivityCheckResult,
    ConnectivityStage,
    HealthStatus,
    Measurement,
)
from hardware_admin.infrastructure.commands import (
    SafeCommandRunner,
    parse_ping_latency_and_loss,
)

LOGGER = logging.getLogger(__name__)


def is_apipa(ip_address: str | None) -> bool:
    """Detecta si una dirección IP pertenece al rango APIPA (169.254.0.0/16)."""
    if not ip_address:
        return False
    clean = ip_address.strip()
    return clean.startswith("169.254.")


@dataclass(slots=True)
class ConnectivityReport:
    """Resultado estructurado de la prueba escalonada de conectividad."""

    stages: tuple[ConnectivityCheckResult, ...]
    status: HealthStatus
    problem_title: str | None
    recommendations: tuple[str, ...]
    is_icmp_blocked: bool = False
    gateway_latency_ms: float | None = None
    gateway_packet_loss: float | None = None
    external_latency_ms: float | None = None
    external_packet_loss: float | None = None
    measurements: tuple[Measurement, ...] = ()


#: Presupuesto total de las pruebas de red. Cada intento tiene además su
#: propio límite; esta constante acota la suma, para que una cadena de
#: intentos lentos no se coma el escaneo entero.
DEFAULT_NETWORK_BUDGET_SECONDS = 30.0


class ConnectivityService:
    """Ejecuta pruebas escalonadas de red: Adaptador -> IP -> Gateway -> IP Externa -> DNS."""

    def __init__(self, runner: SafeCommandRunner | None = None) -> None:
        self.runner = runner or SafeCommandRunner()

    @staticmethod
    def _build_report(
        stages: list[ConnectivityCheckResult],
    ) -> ConnectivityReport:
        """Reporte de una comprobación interrumpida por falta de presupuesto.

        El estado es ADVERTENCIA, no NORMAL: no se llegó a comprobar la salida
        a Internet, y una prueba omitida no demuestra que la red funcione.
        """
        return ConnectivityReport(
            stages=tuple(stages),
            status=HealthStatus.WARNING,
            problem_title="Comprobación de red incompleta: se agotó el presupuesto de tiempo",
            recommendations=(
                "Repetir el análisis de la sección Red cuando el equipo esté menos cargado.",
                "Comprobar manualmente la salida a Internet antes de descartar un problema.",
            ),
            is_icmp_blocked=False,
        )

    def check(
        self,
        adapter_connected: bool,
        local_ip: str | None,
        gateway: str | None,
        external_target: str = "8.8.8.8",
        dns_domain: str = "google.com",
        budget_seconds: float = DEFAULT_NETWORK_BUDGET_SECONDS,
        skip_external: bool = False,
    ) -> ConnectivityReport:
        """Realiza la comprobación escalonada completa con timeouts acotados.

        Además del límite por intento, respeta un presupuesto total. Si se
        agota, las etapas restantes se declaran omitidas: una prueba que no se
        ejecutó no puede leerse como conectividad correcta.
        """
        started = time.monotonic()

        def budget_left() -> bool:
            return (time.monotonic() - started) < budget_seconds

        def skipped(stage: ConnectivityStage, target: str) -> ConnectivityCheckResult:
            return ConnectivityCheckResult(
                stage=stage,
                target=target,
                succeeded=False,
                details=(
                    f"Prueba omitida: se agotó el presupuesto total de red "
                    f"({budget_seconds:.0f} s). Resultado no concluyente."
                ),
            )

        stages: list[ConnectivityCheckResult] = []
        measurements: list[Measurement] = []

        # 1. Escalón: Adaptador físico/lógico
        if not adapter_connected:
            stages.append(
                ConnectivityCheckResult(
                    stage=ConnectivityStage.ADAPTER,
                    target="Interfaz de red",
                    succeeded=False,
                    details="No se detectó un adaptador de red activo o conectado.",
                )
            )
            return ConnectivityReport(
                stages=tuple(stages),
                status=HealthStatus.WARNING,
                problem_title="No se detectó un adaptador de red activo",
                recommendations=(
                    "Verificar que el cable de red Ethernet esté bien conectado o que la red Wi-Fi esté habilitada.",
                    "Revisar en el Administrador de dispositivos si el controlador del adaptador de red presenta advertencias.",
                ),
            )

        stages.append(
            ConnectivityCheckResult(
                stage=ConnectivityStage.ADAPTER,
                target="Interfaz de red",
                succeeded=True,
                details="Adaptador de red conectado y activo.",
            )
        )

        # 2. Escalón: IP Local / Detección APIPA
        ip_clean = (local_ip or "").strip()
        first_ip = ip_clean.split(",")[0].strip() if ip_clean else ""
        has_valid_ip = bool(first_ip and first_ip != "Sin IPv4" and not is_apipa(first_ip))
        has_apipa = is_apipa(first_ip)

        if has_apipa:
            stages.append(
                ConnectivityCheckResult(
                    stage=ConnectivityStage.LOCAL_IP,
                    target=first_ip,
                    succeeded=False,
                    details=f"Dirección de enlace local APIPA detectada ({first_ip}). El equipo no obtuvo IP de un servidor DHCP.",
                )
            )
        elif not has_valid_ip:
            stages.append(
                ConnectivityCheckResult(
                    stage=ConnectivityStage.LOCAL_IP,
                    target="IPv4",
                    succeeded=False,
                    details="El adaptador no tiene asignada una dirección IPv4 válida.",
                )
            )
        else:
            stages.append(
                ConnectivityCheckResult(
                    stage=ConnectivityStage.LOCAL_IP,
                    target=first_ip,
                    succeeded=True,
                    details=f"Dirección IPv4 configurada: {first_ip}",
                )
            )

        # Si es APIPA o no hay IP, no tiene sentido probar gateway ni externos
        if has_apipa:
            stages.extend(
                [
                    ConnectivityCheckResult(
                        stage=ConnectivityStage.GATEWAY,
                        target=gateway or "No asignada",
                        succeeded=False,
                        details="Puerta de enlace ausente o inaccesible por falta de concesión DHCP.",
                    ),
                    ConnectivityCheckResult(
                        stage=ConnectivityStage.EXTERNAL_IP,
                        target=external_target,
                        succeeded=False,
                        details="Prueba omitida: sin direccionamiento IP de red válido.",
                    ),
                    ConnectivityCheckResult(
                        stage=ConnectivityStage.DNS,
                        target=dns_domain,
                        succeeded=False,
                        details="Prueba omitida: sin conectividad IP.",
                    ),
                ]
            )
            return ConnectivityReport(
                stages=tuple(stages),
                status=HealthStatus.CRITICAL,
                problem_title="Dirección APIPA (169.254.x.x) sin concesión DHCP ni acceso a red local",
                recommendations=(
                    "Comprobar el estado del enrutador o conmutador local y verificar si el servicio DHCP está activo.",
                    "Verificar si el cable de red o la contraseña Wi-Fi son correctos.",
                    "Sugerencia de comprobación manual en consola de comandos (cmd) como Administrador:",
                    "  1. ipconfig /all (revisar si DHCP está habilitado)",
                    "  2. ipconfig /release",
                    "  3. ipconfig /renew",
                ),
            )

        if not has_valid_ip:
            return ConnectivityReport(
                stages=tuple(stages),
                status=HealthStatus.WARNING,
                problem_title="Adaptador sin dirección IP asignada",
                recommendations=(
                    "Verificar configuración IP y máscara de subred en las propiedades del adaptador.",
                    "Reiniciar el adaptador de red desde la configuración de Windows.",
                ),
            )

        # 3. Escalón: Puerta de enlace (Gateway)
        gateway_clean = (gateway or "").strip()
        first_gw = gateway_clean.split(",")[0].strip() if gateway_clean else ""
        gw_ok = False
        gw_lat: float | None = None
        gw_loss: float | None = None

        if first_gw and first_gw != "No disponible":
            ping_gw = self.runner.ping(first_gw, count=2, timeout_ms=2000, overall_timeout=3.0)
            gw_ok = ping_gw.exit_code == 0
            gw_lat, gw_loss = parse_ping_latency_and_loss(ping_gw.output)
            if gw_ok and gw_loss is None:
                gw_loss = 0.0

            if gw_lat is not None:
                measurements.append(
                    Measurement(
                        name="Latencia Gateway",
                        value=gw_lat,
                        unit="ms",
                        expected_range=(0.0, 100.0),
                    )
                )
            if gw_loss is not None:
                measurements.append(
                    Measurement(
                        name="Pérdida Gateway",
                        value=gw_loss,
                        unit="%",
                        expected_range=(0.0, 0.0),
                    )
                )

            gw_details = (
                f"Puerta de enlace ({first_gw}) responde al diagnóstico"
                + (f" (latencia: {gw_lat:.1f} ms, pérdida: {gw_loss:.0f}%)." if gw_lat is not None else ".")
                if gw_ok
                else f"La puerta de enlace ({first_gw}) no respondió a la comprobación."
            )
            stages.append(
                ConnectivityCheckResult(
                    stage=ConnectivityStage.GATEWAY,
                    target=first_gw,
                    succeeded=gw_ok,
                    details=gw_details,
                )
            )
        else:
            stages.append(
                ConnectivityCheckResult(
                    stage=ConnectivityStage.GATEWAY,
                    target="Puerta de enlace",
                    succeeded=False,
                    details="No hay puerta de enlace predeterminada configurada.",
                )
            )

        # Si se solicita omitir pruebas externas, no degradar una red local sana
        if skip_external:
            stages.append(
                ConnectivityCheckResult(
                    stage=ConnectivityStage.EXTERNAL_IP,
                    target=external_target,
                    succeeded=True,
                    details="Prueba externa omitida por configuración del usuario (skip_external).",
                )
            )
            stages.append(
                ConnectivityCheckResult(
                    stage=ConnectivityStage.DNS,
                    target=dns_domain,
                    succeeded=True,
                    details="Prueba DNS externa omitida por configuración del usuario (skip_external).",
                )
            )
            local_status = HealthStatus.NORMAL if gw_ok else HealthStatus.WARNING
            local_title = None if gw_ok else "Sin comunicación con la puerta de enlace local"
            local_recs = () if gw_ok else ("Verificar conexión física o Wi-Fi con el enrutador local.",)
            return ConnectivityReport(
                stages=tuple(stages),
                status=local_status,
                problem_title=local_title,
                recommendations=local_recs,
                is_icmp_blocked=False,
                gateway_latency_ms=gw_lat,
                gateway_packet_loss=gw_loss,
                measurements=tuple(measurements),
            )

        # 4. Escalón: IP Externa de referencia (8.8.8.8)
        if not budget_left():
            stages.append(skipped(ConnectivityStage.EXTERNAL_IP, external_target))
            stages.append(skipped(ConnectivityStage.DNS, dns_domain))
            return self._build_report(stages)

        ping_ext = self.runner.ping(external_target, count=2, timeout_ms=2500, overall_timeout=4.0)
        ext_ok = ping_ext.exit_code == 0
        ext_lat, ext_loss = parse_ping_latency_and_loss(ping_ext.output)
        if ext_ok and ext_loss is None:
            ext_loss = 0.0

        if ext_lat is not None:
            measurements.append(
                Measurement(
                    name="Latencia Externa",
                    value=ext_lat,
                    unit="ms",
                    expected_range=(0.0, 150.0),
                )
            )
        if ext_loss is not None:
            measurements.append(
                Measurement(
                    name="Pérdida Externa",
                    value=ext_loss,
                    unit="%",
                    expected_range=(0.0, 0.0),
                )
            )

        ext_details = (
            f"Respuesta correcta desde IP externa ({external_target})"
            + (f" (latencia: {ext_lat:.1f} ms, pérdida: {ext_loss:.0f}%)." if ext_lat is not None else ".")
            if ext_ok
            else f"Sin respuesta de IP externa ({external_target})."
        )
        stages.append(
            ConnectivityCheckResult(
                stage=ConnectivityStage.EXTERNAL_IP,
                target=external_target,
                succeeded=ext_ok,
                details=ext_details,
            )
        )

        # 5. Escalón: Resolución DNS determinista (google.com)
        if not budget_left():
            stages.append(skipped(ConnectivityStage.DNS, dns_domain))
            return self._build_report(stages)

        ns_res = self.runner.nslookup(dns_domain, timeout=4.0)
        dns_ok = self._is_dns_resolved(ns_res.output, ns_res.exit_code)
        stages.append(
            ConnectivityCheckResult(
                stage=ConnectivityStage.DNS,
                target=dns_domain,
                succeeded=dns_ok,
                details=(
                    f"Resolución de nombres correcta para «{dns_domain}»."
                    if dns_ok
                    else f"Fallo al resolver nombre de dominio «{dns_domain}»."
                ),
            )
        )

        # Análisis de conclusiones y casos especiales
        icmp_blocked = False
        if not ext_ok and dns_ok:
            icmp_blocked = True
            stages[3] = ConnectivityCheckResult(
                stage=ConnectivityStage.EXTERNAL_IP,
                target=external_target,
                succeeded=True,
                details=f"IP externa ({external_target}) no responde al ping (ICMP posiblemente filtrado o bloqueado por cortafuegos), pero la resolución DNS y navegación funcionan. Evidencia limitada de ICMP.",
            )

        recs_list: list[str] = []
        if (gw_loss is not None and gw_loss > 0) or (ext_loss is not None and ext_loss > 0):
            recs_list.append("Se detectó pérdida de paquetes en la red. Verificar posibles interferencias Wi-Fi o saturación.")

        if not gw_ok and not ext_ok and not dns_ok:
            return ConnectivityReport(
                stages=tuple(stages),
                status=HealthStatus.CRITICAL,
                problem_title="Sin comunicación con la puerta de enlace ni salida a Internet",
                recommendations=(
                    "Comprobar el cable Ethernet o la señal Wi-Fi hasta el enrutador local.",
                    "Reiniciar el módem/enrutador de la red.",
                    "Revisar si la dirección IP y máscara corresponden a la misma subred del enrutador.",
                ),
                is_icmp_blocked=icmp_blocked,
                gateway_latency_ms=gw_lat,
                gateway_packet_loss=gw_loss,
                external_latency_ms=ext_lat,
                external_packet_loss=ext_loss,
                measurements=tuple(measurements),
            )

        if (ext_ok or icmp_blocked) and not dns_ok:
            # Caso fallo DNS exclusivo
            return ConnectivityReport(
                stages=tuple(stages),
                status=HealthStatus.WARNING,
                problem_title="Conectividad IP operativa pero fallo de resolución DNS",
                recommendations=(
                    "Verificar los servidores DNS asignados en las propiedades del adaptador de red.",
                    "Probar asignación de servidores DNS públicos (p. ej. 1.1.1.1 o 8.8.8.8).",
                    "Comprobar si el servicio del sistema 'Cliente DNS' está en ejecución.",
                    "Sugerencia manual en cmd: ipconfig /flushdns",
                ),
                is_icmp_blocked=icmp_blocked,
                gateway_latency_ms=gw_lat,
                gateway_packet_loss=gw_loss,
                external_latency_ms=ext_lat,
                external_packet_loss=ext_loss,
                measurements=tuple(measurements),
            )

        if not ext_ok and not dns_ok and gw_ok:
            return ConnectivityReport(
                stages=tuple(stages),
                status=HealthStatus.WARNING,
                problem_title="Conexión local establecida pero sin salida a Internet",
                recommendations=(
                    "La red local responde pero no hay salida hacia el proveedor de Internet (WAN).",
                    "Verificar luces indicadoras de Internet/DSL/Fibra en el enrutador principal.",
                ),
                is_icmp_blocked=icmp_blocked,
                gateway_latency_ms=gw_lat,
                gateway_packet_loss=gw_loss,
                external_latency_ms=ext_lat,
                external_packet_loss=ext_loss,
                measurements=tuple(measurements),
            )

        final_status = HealthStatus.NORMAL
        if (not icmp_blocked and ext_loss is not None and ext_loss >= 50) or (
            gw_loss is not None and gw_loss >= 50
        ):
            final_status = HealthStatus.WARNING

        return ConnectivityReport(
            stages=tuple(stages),
            status=final_status,
            problem_title=None if final_status == HealthStatus.NORMAL else "Pérdida significativa de paquetes detectada",
            recommendations=tuple(recs_list),
            is_icmp_blocked=icmp_blocked,
            gateway_latency_ms=gw_lat,
            gateway_packet_loss=gw_loss,
            external_latency_ms=ext_lat,
            external_packet_loss=ext_loss,
            measurements=tuple(measurements),
        )

    @staticmethod
    def _is_dns_resolved(output: str, exit_code: int) -> bool:
        if exit_code != 0:
            return False
        if not output:
            return False
        lower = output.lower()
        if "non-existent" in lower or "can't find" in lower or "timed out" in lower:
            return False
        # Si nslookup arroja 'Address:' o 'Addresses:' para el nombre buscado
        return "address" in lower or "addresses" in lower
