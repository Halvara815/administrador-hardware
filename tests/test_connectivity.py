"""Pruebas unitarias de conectividad escalonada y casos de red (APIPA / DNS)."""

import time
from unittest import TestCase
from unittest.mock import MagicMock

from hardware_admin.domain.models import ConnectivityStage, HealthStatus
from hardware_admin.infrastructure.commands import NativeCommandResult
from hardware_admin.services.connectivity_service import (
    DEFAULT_NETWORK_BUDGET_SECONDS,
    ConnectivityService,
    is_apipa,
)


def mock_command_result(
    output: str, exit_code: int = 0, error: str = ""
) -> NativeCommandResult:
    return NativeCommandResult(
        command=("mock.exe",),
        output=output,
        exit_code=exit_code,
        error=error,
    )


class ConnectivityServiceTests(TestCase):
    def setUp(self) -> None:
        self.mock_runner = MagicMock()
        self.service = ConnectivityService(runner=self.mock_runner)

    def test_is_apipa_detection(self) -> None:
        self.assertTrue(is_apipa("169.254.1.1"))
        self.assertTrue(is_apipa("169.254.255.254"))
        self.assertFalse(is_apipa("192.168.1.1"))
        self.assertFalse(is_apipa("10.0.0.1"))
        self.assertFalse(is_apipa(None))
        self.assertFalse(is_apipa(""))

    def test_adapter_disconnected_returns_warning(self) -> None:
        report = self.service.check(adapter_connected=False, local_ip=None, gateway=None)
        self.assertEqual(report.status, HealthStatus.WARNING)
        self.assertEqual(len(report.stages), 1)
        self.assertEqual(report.stages[0].stage, ConnectivityStage.ADAPTER)
        self.assertFalse(report.stages[0].succeeded)
        self.assertIn("No se detectó un adaptador", report.problem_title or "")

    def test_case_c1_apipa_returns_critical_with_dhcp_recommendations(self) -> None:
        # Caso C1: IP 169.254.x.x, sin gateway, ping falla
        report = self.service.check(
            adapter_connected=True,
            local_ip="169.254.45.10",
            gateway=None,
        )
        self.assertEqual(report.status, HealthStatus.CRITICAL)
        self.assertIn("APIPA", report.problem_title or "")
        self.assertIn("DHCP", report.problem_title or "")
        # Verificar recomendaciones explícitas de renovación IP
        rec_text = " ".join(report.recommendations)
        self.assertIn("ipconfig /release", rec_text)
        self.assertIn("ipconfig /renew", rec_text)
        self.assertIn("DHCP", rec_text)

    def test_case_dns_failure_when_external_ip_ok_but_dns_fails(self) -> None:
        # Gateway responde
        self.mock_runner.ping.side_effect = [
            mock_command_result("Respuesta desde 192.168.1.1: bytes=32 tiempo=1ms TTL=64", exit_code=0),
            mock_command_result("Respuesta desde 8.8.8.8: bytes=32 tiempo=12ms TTL=117", exit_code=0),
        ]
        # nslookup falla
        self.mock_runner.nslookup.return_value = mock_command_result(
            "*** Servidor no puede encontrar google.com: Non-existent domain",
            exit_code=1,
            error="Non-existent domain",
        )

        report = self.service.check(
            adapter_connected=True,
            local_ip="192.168.1.50",
            gateway="192.168.1.1",
        )
        self.assertEqual(report.status, HealthStatus.WARNING)
        self.assertIn("fallo de resolución DNS", report.problem_title or "")
        rec_text = " ".join(report.recommendations)
        self.assertIn("DNS", rec_text)
        self.assertIn("ipconfig /flushdns", rec_text)

    def test_icmp_blocked_handling_when_ping_fails_but_dns_resolves(self) -> None:
        # Gateway responde
        # Ping a 8.8.8.8 falla (ICMP filtrado por firewall)
        self.mock_runner.ping.side_effect = [
            mock_command_result("Respuesta desde 192.168.1.1", exit_code=0),
            mock_command_result("Tiempo de espera agotado", exit_code=1),
        ]
        # Pero DNS resuelve correctamente
        self.mock_runner.nslookup.return_value = mock_command_result(
            "Nombre: google.com\nAddresses: 142.250.190.46\n",
            exit_code=0,
        )

        report = self.service.check(
            adapter_connected=True,
            local_ip="192.168.1.50",
            gateway="192.168.1.1",
        )
        self.assertEqual(report.status, HealthStatus.NORMAL)
        self.assertTrue(report.is_icmp_blocked)
        self.assertIsNone(report.problem_title)

    def test_full_successful_connectivity(self) -> None:
        self.mock_runner.ping.side_effect = [
            mock_command_result("Respuesta desde 192.168.0.1", exit_code=0),
            mock_command_result("Respuesta desde 8.8.8.8", exit_code=0),
        ]
        self.mock_runner.nslookup.return_value = mock_command_result(
            "Name: google.com\nAddresses: 142.250.190.46\n",
            exit_code=0,
        )

        report = self.service.check(
            adapter_connected=True,
            local_ip="192.168.0.15",
            gateway="192.168.0.1",
        )
        self.assertEqual(report.status, HealthStatus.NORMAL)
        self.assertIsNone(report.problem_title)
        self.assertEqual(len(report.stages), 5)
        for stage in report.stages:
            self.assertTrue(stage.succeeded)



class NetworkBudgetTests(TestCase):
    """Objetivo operativo: pruebas de red acotadas a 30 s en total."""

    def test_the_declared_budget_is_the_documented_one(self) -> None:
        self.assertEqual(DEFAULT_NETWORK_BUDGET_SECONDS, 30.0)

    def test_a_slow_stage_stops_the_remaining_probes(self) -> None:
        """Agotado el presupuesto no se lanzan más pruebas externas."""
        runner = MagicMock()
        llamadas: list[str] = []

        def ping_lento(target: str, **kwargs: object) -> NativeCommandResult:
            llamadas.append(f"ping:{target}")
            time.sleep(0.35)
            return NativeCommandResult(command=("ping.exe", target), output="", exit_code=0)

        def nslookup(domain: str, **kwargs: object) -> NativeCommandResult:
            llamadas.append(f"nslookup:{domain}")
            return NativeCommandResult(command=("nslookup.exe", domain), output="Address: 1.2.3.4", exit_code=0)

        runner.ping.side_effect = ping_lento
        runner.nslookup.side_effect = nslookup

        report = ConnectivityService(runner).check(
            adapter_connected=True,
            local_ip="192.168.1.50",
            gateway="192.168.1.1",
            budget_seconds=0.4,
        )

        self.assertNotIn("nslookup:google.com", llamadas)
        etapas = {s.stage: s for s in report.stages}
        self.assertIn(ConnectivityStage.DNS, etapas)
        self.assertFalse(etapas[ConnectivityStage.DNS].succeeded)
        self.assertIn("presupuesto", etapas[ConnectivityStage.DNS].details.lower())

    def test_a_skipped_stage_is_not_reported_as_successful(self) -> None:
        """Una prueba omitida no puede leerse como conectividad correcta."""
        runner = MagicMock()

        def ping_lento(target: str, **kwargs: object) -> NativeCommandResult:
            time.sleep(0.35)
            return NativeCommandResult(command=("ping.exe", target), output="", exit_code=0)

        runner.ping.side_effect = ping_lento
        runner.nslookup.return_value = NativeCommandResult(
            command=("nslookup.exe",), output="Address: 1.2.3.4", exit_code=0
        )

        report = ConnectivityService(runner).check(
            adapter_connected=True,
            local_ip="192.168.1.50",
            gateway="192.168.1.1",
            budget_seconds=0.4,
        )

        self.assertIsNot(report.status, HealthStatus.NORMAL)
