"""Servicio de verificación escalonada de conectividad de red y diagnóstico determinista."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from hardware_admin.domain.models import (
    ConnectivityCheckResult,
    ConnectivityStage,
    HealthStatus,
)
from hardware_admin.infrastructure.commands import SafeCommandRunner

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


class ConnectivityService:
    """Ejecuta pruebas escalonadas de red: Adaptador -> IP -> Gateway -> IP Externa -> DNS."""

    def __init__(self, runner: SafeCommandRunner | None = None) -> None:
        self.runner = runner or SafeCommandRunner()

    def check(
        self,
        adapter_connected: bool,
        local_ip: str | None,
        gateway: str | None,
        external_target: str = "8.8.8.8",
        dns_domain: str = "google.com",
    ) -> ConnectivityReport:
        """Realiza la comprobación escalonada completa con timeouts acotados."""
        stages: list[ConnectivityCheckResult] = []

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
        if first_gw and first_gw != "No disponible":
            ping_gw = self.runner.ping(first_gw, count=1, timeout_ms=2500, overall_timeout=3.0)
            gw_ok = ping_gw.exit_code == 0
            stages.append(
                ConnectivityCheckResult(
                    stage=ConnectivityStage.GATEWAY,
                    target=first_gw,
                    succeeded=gw_ok,
                    details=(
                        f"Puerta de enlace ({first_gw}) responde al diagnóstico."
                        if gw_ok
                        else f"La puerta de enlace ({first_gw}) no respondió a la comprobación."
                    ),
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

        # 4. Escalón: IP Externa de referencia (8.8.8.8)
        ping_ext = self.runner.ping(external_target, count=1, timeout_ms=3000, overall_timeout=4.0)
        ext_ok = ping_ext.exit_code == 0
        stages.append(
            ConnectivityCheckResult(
                stage=ConnectivityStage.EXTERNAL_IP,
                target=external_target,
                succeeded=ext_ok,
                details=(
                    f"Respuesta correcta desde IP externa de referencia ({external_target})."
                    if ext_ok
                    else f"Sin respuesta de IP externa ({external_target})."
                ),
            )
        )

        # 5. Escalón: Resolución DNS determinista (google.com)
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
                details=f"IP externa ({external_target}) no responde al ping (ICMP posiblemente filtrado), pero la navegación y el tráfico DNS funcionan.",
            )

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
            )

        if ext_ok and not dns_ok:
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
            )

        if not ext_ok and not dns_ok:
            return ConnectivityReport(
                stages=tuple(stages),
                status=HealthStatus.WARNING,
                problem_title="Conexión local establecida pero sin salida a Internet",
                recommendations=(
                    "La red local responde pero no hay salida hacia el proveedor de Internet (WAN).",
                    "Verificar luces indicadoras de Internet/DSL/Fibra en el enrutador principal.",
                ),
                is_icmp_blocked=icmp_blocked,
            )

        return ConnectivityReport(
            stages=tuple(stages),
            status=HealthStatus.NORMAL,
            problem_title=None,
            recommendations=(),
            is_icmp_blocked=icmp_blocked,
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
