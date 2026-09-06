"""Pruebas exhaustivas para la Fase F4 Comercial: Red y Eventos Críticos de Windows."""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock

from hardware_admin.collectors.core import NetworkCollector, SystemCollector
from hardware_admin.collectors.drivers import DriverCollector, normalize_device_id
from hardware_admin.diagnostics.recommendations import build_recommendations
from hardware_admin.diagnostics.windows_events import (
    DEFAULT_EVENT_WINDOW_DAYS,
    EVENT_WINDOW_DAYS,
    WindowsEventsProvider,
    sanitize_event_message,
)
from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    DiagnosticReport,
    HealthStatus,
    Measurement,
)
from hardware_admin.infrastructure.commands import (
    NativeCommandResult,
    parse_ping_latency_and_loss,
    parse_wlan_signal,
)
from hardware_admin.infrastructure.powershell import (
    CommandResult,
    PowerShellQuery,
)
from hardware_admin.reports.html_report import export_html
from hardware_admin.reports.json_report import build_payload
from hardware_admin.reports.txt_report import render_text
from hardware_admin.services.connectivity_service import ConnectivityService


def _now() -> datetime:
    return datetime.now(UTC)


def mock_cmd_result(
    output: str, query: PowerShellQuery, exit_code: int = 0, error: str = ""
) -> CommandResult:
    return CommandResult(
        query=query,
        output=output,
        exit_code=exit_code,
        error=error,
    )


def mock_native_result(output: str, exit_code: int = 0, error: str = "") -> NativeCommandResult:
    return NativeCommandResult(
        command=("test.exe",),
        output=output,
        exit_code=exit_code,
        error=error,
    )


class NetworkParsingAndProbesTests(TestCase):
    """Pruebas para parsing de ping, Wi-Fi y comprobación escalonada de red."""

    def test_parse_ping_latency_and_loss_english(self) -> None:
        raw = """
Pinging 8.8.8.8 with 32 bytes of data:
Reply from 8.8.8.8: bytes=32 time=14ms TTL=117
Reply from 8.8.8.8: bytes=32 time=15ms TTL=117

Ping statistics for 8.8.8.8:
    Packets: Sent = 2, Received = 2, Lost = 0 (0% loss),
Approximate round trip times in milli-seconds:
    Minimum = 14ms, Maximum = 15ms, Average = 14ms
"""
        lat, loss = parse_ping_latency_and_loss(raw)
        self.assertEqual(lat, 14.0)
        self.assertEqual(loss, 0.0)

    def test_parse_ping_latency_and_loss_spanish(self) -> None:
        raw = """
Haciendo ping a 192.168.1.1 con 32 bytes de datos:
Respuesta desde 192.168.1.1: bytes=32 tiempo=2ms TTL=64
Respuesta desde 192.168.1.1: bytes=32 tiempo=1ms TTL=64

Estadísticas de ping para 192.168.1.1:
    Paquetes: enviados = 2, recibidos = 2, perdidos = 0
    (0% perdidos),
Tiempos aproximados de ida y vuelta en milisegundos:
    Mínimo = 1ms, Máximo = 2ms, Media = 1ms
"""
        lat, loss = parse_ping_latency_and_loss(raw)
        self.assertEqual(lat, 1.0)
        self.assertEqual(loss, 0.0)

    def test_parse_ping_latency_and_loss_single_line_fallback(self) -> None:
        raw = "Respuesta desde 10.0.0.1: bytes=32 tiempo=28ms TTL=54"
        lat, loss = parse_ping_latency_and_loss(raw)
        self.assertEqual(lat, 28.0)
        self.assertIsNone(loss)

    def test_parse_ping_latency_and_loss_100_percent_loss(self) -> None:
        raw = """
Haciendo ping a 8.8.8.8 con 32 bytes de datos:
Tiempo de espera agotado para esta solicitud.
Tiempo de espera agotado para esta solicitud.

Estadísticas de ping para 8.8.8.8:
    Paquetes: enviados = 2, recibidos = 0, perdidos = 2
    (100% perdidos),
"""
        lat, loss = parse_ping_latency_and_loss(raw)
        self.assertIsNone(lat)
        self.assertEqual(loss, 100.0)

    def test_parse_wlan_signal_connected(self) -> None:
        raw = """
There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Intel(R) Wi-Fi 6 AX201 160MHz
    GUID                   : 7a8b9c0d-1e2f-3a4b-5c6d-7e8f9a0b1c2d
    Physical address       : 00:11:22:33:44:55
    Interface type         : Primary
    State                  : connected
    SSID                   : Office_5G
    BSSID                  : aa:bb:cc:dd:ee:ff
    Network type           : Infrastructure
    Radio type             : 802.11ax
    Authentication         : WPA2-Personal
    Cipher                 : CCMP
    Connection mode        : Auto Connect
    Channel                : 36
    Receive rate (Mbps)    : 866
    Transmit rate (Mbps)   : 866
    Signal                 : 92%
    Profile                : Office_5G

    Hosted network status  : Not available
"""
        ok, signal, detail = parse_wlan_signal(raw)
        self.assertTrue(ok)
        self.assertEqual(signal, 92)
        self.assertIn("92%", detail)

    def test_parse_wlan_signal_service_not_running_returns_not_supported(self) -> None:
        raw = "The Wireless AutoConfig Service (wlansvc) is not running."
        ok, signal, detail = parse_wlan_signal(raw)
        self.assertFalse(ok)
        self.assertIsNone(signal)
        self.assertIn("NOT_SUPPORTED", detail)

    def test_parse_wlan_signal_empty_output_returns_not_supported(self) -> None:
        ok, signal, detail = parse_wlan_signal("")
        self.assertFalse(ok)
        self.assertIsNone(signal)
        self.assertIn("NOT_SUPPORTED", detail)

    def test_connectivity_service_skip_external_healthy_local_network(self) -> None:
        mock_runner = MagicMock()
        mock_runner.ping.return_value = mock_native_result(
            "Respuesta desde 192.168.1.1: bytes=32 tiempo=1ms TTL=64\nMedia = 1ms\n(0% perdidos)",
            exit_code=0,
        )
        service = ConnectivityService(runner=mock_runner)

        report = service.check(
            adapter_connected=True,
            local_ip="192.168.1.50",
            gateway="192.168.1.1",
            skip_external=True,
        )
        self.assertEqual(report.status, HealthStatus.NORMAL)
        self.assertIsNone(report.problem_title)
        self.assertEqual(report.gateway_latency_ms, 1.0)
        self.assertEqual(report.gateway_packet_loss, 0.0)
        self.assertIsNone(report.external_latency_ms)
        # External tests must not have been executed
        self.assertEqual(mock_runner.ping.call_count, 1)
        mock_runner.nslookup.assert_not_called()

    def test_connectivity_service_icmp_blocked_detected_with_dns_ok(self) -> None:
        mock_runner = MagicMock()
        # Gateway responde
        # External target 8.8.8.8 falla (ICMP filtrado)
        mock_runner.ping.side_effect = [
            mock_native_result("Respuesta desde 192.168.1.1: bytes=32 tiempo=1ms TTL=64\nMedia = 1ms\n(0% perdidos)", exit_code=0),
            mock_native_result("Tiempo de espera agotado.\n(100% perdidos)", exit_code=1),
        ]
        # DNS resuelve correctamente
        mock_runner.nslookup.return_value = mock_native_result(
            "Name: google.com\nAddresses: 142.250.190.46\n", exit_code=0
        )
        service = ConnectivityService(runner=mock_runner)

        report = service.check(
            adapter_connected=True,
            local_ip="192.168.1.50",
            gateway="192.168.1.1",
            skip_external=False,
        )
        self.assertEqual(report.status, HealthStatus.NORMAL)
        self.assertTrue(report.is_icmp_blocked)
        self.assertIsNone(report.problem_title)
        # External stage must be marked succeeded with ICMP blocked notice
        ext_stage = next(s for s in report.stages if s.stage.value == "external_ip")
        self.assertTrue(ext_stage.succeeded)
        self.assertIn("ICMP posiblemente filtrado", ext_stage.details)

    def test_network_collector_interface_statistics_and_measurements(self) -> None:
        mock_ps_runner = MagicMock()
        mock_ps_runner.run.return_value = mock_cmd_result(
            '[{"MAC":"00:11:22:33:44:55","Gateway":"192.168.1.1","DNS":"8.8.8.8","IPv4":"192.168.1.50","IPv6":"No disponible"}]',
            PowerShellQuery.NETWORK_CONFIGURATION,
        )
        mock_cmd_runner = MagicMock()
        mock_cmd_runner.wlan_show_interfaces.return_value = mock_native_result(
            "Name : Wi-Fi\nState : connected\nSSID : TestWiFi\nSignal : 85%",
            exit_code=0,
        )
        mock_cmd_runner.ping.return_value = mock_native_result(
            "Respuesta desde 192.168.1.1: bytes=32 tiempo=2ms TTL=64\nMedia = 2ms\n(0% perdidos)",
            exit_code=0,
        )
        mock_cmd_runner.nslookup.return_value = mock_native_result(
            "Name: google.com\nAddresses: 142.250.190.46\n", exit_code=0
        )

        conn_service = ConnectivityService(runner=mock_cmd_runner)
        collector = NetworkCollector(
            runner=mock_ps_runner,
            connectivity_service=conn_service,
            cmd_runner=mock_cmd_runner,
        )

        result = collector.collect()
        self.assertEqual(result.component, ComponentKind.NETWORK)
        self.assertEqual(result.status, HealthStatus.NORMAL)
        self.assertIn("Wi-Fi", result.facts)
        self.assertIn("Estadísticas de red", result.facts)
        # Verificar que se crearon mediciones
        m_names = {m.name: m.value for m in result.measurements}
        self.assertIn("Señal Wi-Fi", m_names)
        self.assertEqual(m_names["Señal Wi-Fi"], 85)


class WindowsCriticalEventsTests(TestCase):
    """Pruebas para sanitización y proveedor de eventos críticos de Windows."""

    def test_sanitize_event_message_redactions_and_length(self) -> None:
        raw = (
            "Error en C:\\Windows\\System32\\drivers\\faulty.sys reportado por usuario "
            "C:\\Users\\JohnDoe\\AppData\\Local\\Temp\\run.exe con IP 192.168.1.100 "
            "y dirección MAC 00-14-22-01-23-45 en equipo Serial: SN-987654321."
        )
        sanitized = sanitize_event_message(raw, max_chars=500)
        self.assertNotIn("JohnDoe", sanitized)
        self.assertNotIn("192.168.1.100", sanitized)
        self.assertNotIn("00-14-22-01-23-45", sanitized)
        self.assertNotIn("SN-987654321", sanitized)
        self.assertIn("<ip_redactada>", sanitized)
        self.assertIn("<mac_redactada>", sanitized)
        self.assertIn("<serial_redactado>", sanitized)

        # Truncamiento de caracteres
        long_raw = "A" * 600
        truncated = sanitize_event_message(long_raw, max_chars=500)
        self.assertLessEqual(len(truncated), 500)
        self.assertTrue(truncated.endswith("..."))

    def test_sanitize_event_message_redacts_ipv6_addresses(self) -> None:
        raw = (
            "Conexión bloqueada hacia 2001:0db8:85a3:0000:0000:8a2e:0370:7334 "
            "y link-local fe80::1ff:fe23:4567:890a y loopback ::1 y comprimida 2001:db8::1 "
            "a las 14:30:15 en interfaz con MAC 00:11:22:33:44:55."
        )
        sanitized = sanitize_event_message(raw)
        self.assertNotIn("2001:0db8", sanitized)
        self.assertNotIn("fe80::", sanitized)
        self.assertNotIn("2001:db8", sanitized)
        self.assertNotIn("00:11:22:33:44:55", sanitized)
        self.assertIn("<ip_redactada>", sanitized)
        self.assertIn("<mac_redactada>", sanitized)
        # El timestamp debe preservarse
        self.assertIn("14:30:15", sanitized)

    def test_permission_denied_returns_not_supported_never_empty_or_normal(self) -> None:
        mock_runner = MagicMock()
        mock_runner.run.return_value = mock_cmd_result(
            "",
            PowerShellQuery.CRITICAL_EVENTS,
            exit_code=1,
            error="Get-WinEvent: Access is denied. UnauthorizedAccessException.",
        )
        provider = WindowsEventsProvider(runner=mock_runner)
        _events, status, problem, success = provider.get_recent_events(window_days=7)

        self.assertFalse(success)
        self.assertEqual(status, HealthStatus.NOT_SUPPORTED)
        self.assertIsNotNone(problem)
        self.assertIn("Permisos insuficientes", problem or "")
        self.assertIn("no certifica salud física", problem or "")

    def test_query_failure_returns_error(self) -> None:
        mock_runner = MagicMock()
        mock_runner.run.return_value = mock_cmd_result(
            "",
            PowerShellQuery.CRITICAL_EVENTS,
            exit_code=1,
            error="ERROR_GET_WINEVENT: The RPC server is unavailable.",
        )
        provider = WindowsEventsProvider(runner=mock_runner)
        _events, status, problem, success = provider.get_recent_events(window_days=7)

        self.assertFalse(success)
        self.assertEqual(status, HealthStatus.ERROR)
        self.assertIn("The RPC server is unavailable", problem or "")

    def test_empty_log_returns_normal_with_disclaimer(self) -> None:
        mock_runner = MagicMock()
        mock_runner.run.return_value = mock_cmd_result("[]", PowerShellQuery.CRITICAL_EVENTS, exit_code=0)
        provider = WindowsEventsProvider(runner=mock_runner)
        events, status, problem, success = provider.get_recent_events(window_days=7)

        self.assertTrue(success)
        self.assertEqual(status, HealthStatus.NORMAL)
        self.assertEqual(len(events), 0)
        self.assertIn("la ausencia de eventos no certifica salud física", problem or "")

    def test_whea_error_elevates_to_critical(self) -> None:
        mock_runner = MagicMock()
        whea_json = (
            '[{"Id":18,"Timestamp":"2026-09-01T10:00:00Z","Nivel":"Crítico",'
            '"Proveedor":"Microsoft-Windows-WHEA-Logger","Mensaje":"A fatal hardware error has occurred. Component: Processor Core."}]'
        )
        mock_runner.run.return_value = mock_cmd_result(whea_json, PowerShellQuery.CRITICAL_EVENTS, exit_code=0)
        provider = WindowsEventsProvider(runner=mock_runner)
        events, status, problem, success = provider.get_recent_events(window_days=7)

        self.assertTrue(success)
        self.assertEqual(status, HealthStatus.CRITICAL)
        self.assertIn("WHEA", problem or "")
        self.assertEqual(events[0].category, "WHEA")

    def test_isolated_kernel_power_41_never_elevates_to_critical(self) -> None:
        mock_runner = MagicMock()
        kp41_json = (
            '[{"Id":41,"Timestamp":"2026-09-02T15:30:00Z","Nivel":"Crítico",'
            '"Proveedor":"Microsoft-Windows-Kernel-Power","Mensaje":"The system has rebooted without cleanly shutting down first."}]'
        )
        mock_runner.run.return_value = mock_cmd_result(kp41_json, PowerShellQuery.CRITICAL_EVENTS, exit_code=0)
        provider = WindowsEventsProvider(runner=mock_runner)
        events, status, _problem, success = provider.get_recent_events(window_days=7)

        self.assertTrue(success)
        # Regla canónica: KP41 aislado jamás es CRITICAL
        self.assertEqual(status, HealthStatus.WARNING)
        self.assertIn("reinicio inesperado detectado, causa no determinada", events[0].message)
        self.assertEqual(events[0].category, "REINICIO_INESPERADO")
        self.assertTrue(events[0].is_kernel_power_41)

    def test_kernel_power_with_id_other_than_41_not_treated_as_unexpected_reboot(self) -> None:
        mock_runner = MagicMock()
        kp_other_json = (
            '[{"Id":42,"Timestamp":"2026-09-02T15:30:00Z","Nivel":"Información",'
            '"Proveedor":"Microsoft-Windows-Kernel-Power","Mensaje":"The system is entering sleep."}]'
        )
        mock_runner.run.return_value = mock_cmd_result(kp_other_json, PowerShellQuery.CRITICAL_EVENTS, exit_code=0)
        provider = WindowsEventsProvider(runner=mock_runner)
        events, _status, _problem, success = provider.get_recent_events(window_days=7)

        self.assertTrue(success)
        self.assertEqual(len(events), 1)
        self.assertFalse(events[0].is_kernel_power_41)
        self.assertEqual(events[0].category, "KERNEL_POWER")
        self.assertEqual(events[0].event_id, 42)
        self.assertNotIn("reinicio inesperado", events[0].message)
        self.assertIn("The system is entering sleep", events[0].message)

    def test_window_days_is_fixed_to_7_and_rejects_other_values(self) -> None:
        mock_runner = MagicMock()
        mock_runner.run.return_value = mock_cmd_result("[]", PowerShellQuery.CRITICAL_EVENTS, exit_code=0)
        provider = WindowsEventsProvider(runner=mock_runner)
        self.assertEqual(EVENT_WINDOW_DAYS, 7)
        self.assertEqual(DEFAULT_EVENT_WINDOW_DAYS, 7)

        # 7 días es aceptado
        _events, status, _problem, success = provider.get_recent_events(window_days=7)
        self.assertTrue(success)
        self.assertEqual(status, HealthStatus.NORMAL)

        # Cualquier otro valor es rechazado explícitamente con ValueError
        with self.assertRaises(ValueError):
            provider.get_recent_events(window_days=1)
        with self.assertRaises(ValueError):
            provider.get_recent_events(window_days=30)
        with self.assertRaises(ValueError):
            provider.get_recent_events(window_days=14)

    def test_query_failure_sanitizes_error_messages(self) -> None:
        mock_runner = MagicMock()
        mock_runner.run.return_value = mock_cmd_result(
            "",
            PowerShellQuery.CRITICAL_EVENTS,
            exit_code=1,
            error="ERROR en C:\\Users\\Administrator\\secret.ps1 hacia 192.168.1.50 con fe80::1",
        )
        provider = WindowsEventsProvider(runner=mock_runner)
        _events, status, problem, success = provider.get_recent_events(window_days=7)

        self.assertFalse(success)
        self.assertEqual(status, HealthStatus.ERROR)
        self.assertIsNotNone(problem)
        self.assertNotIn("Administrator", problem or "")
        self.assertNotIn("192.168.1.50", problem or "")
        self.assertNotIn("fe80::1", problem or "")
        self.assertIn("<usuario>", problem or "")
        self.assertIn("<ip_redactada>", problem or "")

    def test_malformed_json_output_returns_error_gracefully(self) -> None:
        mock_runner = MagicMock()
        mock_runner.run.return_value = mock_cmd_result(
            "ESTO NO ES UN JSON VALIDO {{{{",
            PowerShellQuery.CRITICAL_EVENTS,
            exit_code=0,
        )
        provider = WindowsEventsProvider(runner=mock_runner)
        events, status, problem, success = provider.get_recent_events(window_days=7)

        self.assertFalse(success)
        self.assertEqual(status, HealthStatus.ERROR)
        self.assertEqual(events, [])
        self.assertIn("Salida inválida", problem or "")

    def test_system_collector_integrates_events_properly(self) -> None:
        mock_runner = MagicMock()
        sys_json = '[{"Fabricante":"Dell","Modelo":"XPS","SistemaOperativo":"Windows 11"}]'
        firm_json = '[{"BiosVendor":"Dell","BiosVersion":"1.0","BiosDate":"2023-01-01"}]'
        ev_json = (
            '[{"Id":41,"Timestamp":"2026-09-03T12:00:00Z","Nivel":"Crítico",'
            '"Proveedor":"Microsoft-Windows-Kernel-Power","Mensaje":"Reboot without clean shutdown"}]'
        )

        def side_effect(q: PowerShellQuery) -> CommandResult:
            if q == PowerShellQuery.SYSTEM_INFO:
                return mock_cmd_result(sys_json, q)
            if q == PowerShellQuery.FIRMWARE_INFO:
                return mock_cmd_result(firm_json, q)
            if q == PowerShellQuery.CRITICAL_EVENTS:
                return mock_cmd_result(ev_json, q)
            return mock_cmd_result("[]", q)

        mock_runner.run.side_effect = side_effect
        collector = SystemCollector(runner=mock_runner)
        result = collector.collect()

        self.assertEqual(result.component, ComponentKind.SYSTEM)
        self.assertEqual(result.status, HealthStatus.WARNING)
        self.assertEqual(result.facts.get("Ventana de eventos"), "7 días")
        self.assertIn("La ausencia de eventos no certifica salud física", result.facts.get("Límite de evidencia", ""))
        self.assertEqual(result.facts.get("Eventos críticos recientes (7 días)"), 1)
        self.assertIn("Advertencia de energía", result.facts)


class DriverCorrelationAndRulesTests(TestCase):
    """Pruebas de correlación estricta de controladores por DeviceID normalizado."""

    def test_normalize_device_id(self) -> None:
        self.assertEqual(
            normalize_device_id("pci/ven_10de&dev_2484/subsys_146710de/rev_a1"),
            "PCI\\VEN_10DE&DEV_2484\\SUBSYS_146710DE\\REV_A1",
        )
        self.assertEqual(normalize_device_id(""), "")
        self.assertEqual(normalize_device_id(None), "")

    def test_correlation_by_device_id_only_and_forbidden_by_friendly_name(self) -> None:
        mock_runner = MagicMock()
        # Dos dispositivos con el MISMO FriendlyName pero DIFERENTE DeviceID
        drivers_json = json.dumps(
            [
                {
                    "Nombre": "Realtek PCIe GbE Family Controller",
                    "DeviceID": "PCI\\VEN_10EC&DEV_8168&SUBSYS_012310EC&REV_15",
                    "IsSigned": True,
                    "DriverDate": "2023-01-01",
                    "DriverVersion": "10.60.0.0",
                }
            ]
        )
        # Problem device tiene el mismo nombre pero OTRO ID de dispositivo (p. ej. USB)
        problem_devices_json = json.dumps(
            [
                {
                    "FriendlyName": "Realtek PCIe GbE Family Controller",
                    "InstanceId": "USB\\VID_0BDA&PID_8153\\000001",
                    "Problem": 28,
                    "Status": "Error",
                }
            ]
        )

        def side_effect(q: PowerShellQuery) -> CommandResult:
            if q == PowerShellQuery.DRIVERS:
                return mock_cmd_result(drivers_json, q)
            if q == PowerShellQuery.PROBLEM_DEVICES:
                return mock_cmd_result(problem_devices_json, q)
            return mock_cmd_result("[]", q)

        mock_runner.run.side_effect = side_effect
        collector = DriverCollector(runner=mock_runner)
        result = collector.collect()

        # Prohibido correlacionar por FriendlyName: no deben correlacionarse
        self.assertEqual(len(result.facts.get("Dispositivos con fallo PnP", [])), 0)
        self.assertEqual(result.status, HealthStatus.NORMAL)

    def test_correlation_succeeds_when_device_ids_match_with_problem_code(self) -> None:
        mock_runner = MagicMock()
        dev_id = "PCI\\VEN_10DE&DEV_2484&SUBSYS_146710DE&REV_A1"
        drivers_json = json.dumps(
            [
                {
                    "Nombre": "NVIDIA GeForce RTX 3070",
                    "DeviceID": dev_id,
                    "IsSigned": True,
                    "DriverDate": "2023-05-10",
                    "DriverVersion": "31.0.15.3623",
                }
            ]
        )
        problem_devices_json = json.dumps(
            [
                {
                    "FriendlyName": "NVIDIA GeForce RTX 3070",
                    "InstanceId": dev_id.lower().replace("\\", "/"),
                    "Problem": 43,
                    "Status": "Error",
                }
            ]
        )

        def side_effect(q: PowerShellQuery) -> CommandResult:
            if q == PowerShellQuery.DRIVERS:
                return mock_cmd_result(drivers_json, q)
            if q == PowerShellQuery.PROBLEM_DEVICES:
                return mock_cmd_result(problem_devices_json, q)
            return mock_cmd_result("[]", q)

        mock_runner.run.side_effect = side_effect
        collector = DriverCollector(runner=mock_runner)
        result = collector.collect()

        self.assertEqual(result.status, HealthStatus.WARNING)
        correlated = result.facts.get("Dispositivos con fallo PnP", [])
        self.assertEqual(len(correlated), 1)
        self.assertEqual(correlated[0]["ProblemCode"], 43)

    def test_old_driver_date_alone_never_recommends_update(self) -> None:
        mock_runner = MagicMock()
        drivers_json = json.dumps(
            [
                {
                    "Nombre": "Standard Keyboard",
                    "DeviceID": "ACPI\\PNP0303\\4&1234567&0",
                    "IsSigned": True,
                    "DriverDate": "2006-06-21",  # Fecha antigua de Windows estándar
                    "DriverVersion": "10.0.19041.1",
                }
            ]
        )

        def side_effect(q: PowerShellQuery) -> CommandResult:
            if q == PowerShellQuery.DRIVERS:
                return mock_cmd_result(drivers_json, q)
            if q == PowerShellQuery.PROBLEM_DEVICES:
                return mock_cmd_result("[]", q)
            return mock_cmd_result("[]", q)

        mock_runner.run.side_effect = side_effect
        collector = DriverCollector(runner=mock_runner)
        result = collector.collect()

        self.assertEqual(result.status, HealthStatus.NORMAL)
        recs = build_recommendations([result])
        # Ninguna recomendación de actualización por fecha
        self.assertEqual(len(recs), 0)


class DiagnosticReportSerializationTests(TestCase):
    """Pruebas de serialización de reportes HTML, JSON y TXT con datos de F4."""

    def test_reports_include_f4_network_and_events_facts(self) -> None:
        net_result = ComponentResult(
            component=ComponentKind.NETWORK,
            name="Red",
            facts={
                "Adaptadores": [{"Adaptador": "Ethernet", "Estado": "Conectado", "IPv4": "192.168.1.10"}],
                "Wi-Fi": {"Estado": "connected", "SSID": "Home5G", "Señal": "80%"},
                "Estadísticas de red": {"Total errores entrada": 0, "Total descartes entrada": 0},
                "Diagnóstico de red": "Conectividad normal y acceso a Internet verificado",
            },
            summary="1 conectado(s) · Conectividad OK",
            status=HealthStatus.NORMAL,
            measurements=(
                Measurement("Latencia Gateway", 1.5, "ms"),
                Measurement("Pérdida Gateway", 0.0, "%"),
                Measurement("Señal Wi-Fi", 80, "%"),
            ),
        )

        sys_result = ComponentResult(
            component=ComponentKind.SYSTEM,
            name="Información del sistema",
            facts={
                "Sistema operativo": "Microsoft Windows 11 Pro",
                "Ventana de eventos": "7 días",
                "Límite de evidencia": "La ausencia de eventos no certifica salud física",
                "Eventos críticos recientes (7 días)": 1,
                "Eventos de Windows (7 días)": [
                    {
                        "Timestamp": "2026-09-04T18:00:00Z",
                        "Id": 41,
                        "Nivel": "Crítico",
                        "Proveedor": "Microsoft-Windows-Kernel-Power",
                        "Categoría": "REINICIO_INESPERADO",
                        "Mensaje": "reinicio inesperado detectado, causa no determinada (Event ID 41)",
                    }
                ],
            },
            summary="Microsoft Windows 11 Pro",
            status=HealthStatus.WARNING,
            possible_problem="1 reinicio(s) inesperado(s) detectado(s) (Event ID 41)",
        )

        report = DiagnosticReport(
            started_at=_now(),
            completed_at=_now(),
            results=(sys_result, net_result),
            conclusion="Diagnóstico completado",
            recommendations=build_recommendations([sys_result, net_result]),
        )

        # 1. JSON Payload
        payload = build_payload(report)
        components = {r["componente"] for r in payload["resultados"]}
        self.assertIn("network", components)
        self.assertIn("system", components)
        json_str = json.dumps(payload, ensure_ascii=False)
        self.assertIn("Latencia Gateway", json_str)
        self.assertIn("Señal Wi-Fi", json_str)
        self.assertIn("REINICIO_INESPERADO", json_str)

        # 2. TXT Report
        txt_str = render_text(report)
        self.assertIn("Monitorear reinicios inesperados (Kernel-Power 41)", txt_str)
        self.assertIn("reinicio inesperado detectado, causa no determinada", txt_str)

        # 3. HTML Export
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp_f:
            tmp_path = Path(tmp_f.name)
        try:
            export_html(report, tmp_path)
            html_str = tmp_path.read_text(encoding="utf-8")
            self.assertIn("Ventana de eventos", html_str)
            self.assertIn("Wi-Fi", html_str)
            self.assertIn("Kernel-Power", html_str)
        finally:
            tmp_path.unlink(missing_ok=True)


class WindowsEventsWindowUITests(TestCase):
    """Pruebas de la ventana gráfica de eventos críticos de Windows (F4)."""

    def test_windows_events_window_lifecycle_and_disclaimer(self) -> None:
        import customtkinter as ctk

        from hardware_admin.ui.main_window import WindowsEventsWindow

        root = ctk.CTk()
        root.withdraw()
        try:
            # 1. Ventana vacía muestra descargo obligatorio
            win = WindowsEventsWindow(root, [])
            win.update_idletasks()
            children = win.body.winfo_children()
            self.assertGreater(len(children), 0)
            text = children[0].cget("text")
            self.assertIn("Sin eventos críticos registrados en los últimos 7 días", text)
            self.assertIn("no certifica por sí sola la salud física", text)

            # 2. Actualizar con eventos
            sample_events = [
                {
                    "Id": 41,
                    "Timestamp": "2026-09-04T12:00:00Z",
                    "Proveedor": "Microsoft-Windows-Kernel-Power",
                    "Categoría": "REINICIO_INESPERADO",
                    "Mensaje": "reinicio inesperado detectado, causa no determinada (Event ID 41)",
                },
                {
                    "Id": 18,
                    "Timestamp": "2026-09-03T10:00:00Z",
                    "Proveedor": "Microsoft-Windows-WHEA-Logger",
                    "Categoría": "WHEA",
                    "Mensaje": "Error crítico WHEA",
                },
            ]
            win.update_events(sample_events)
            win.update_idletasks()
            self.assertEqual(len(win.body.winfo_children()), 2)

            win.destroy()
        finally:
            root.destroy()


class LoggingResilienceTests(TestCase):
    """Pruebas de tolerancia a fallos en la configuración de logging (F4)."""

    def test_configure_logging_handles_permission_error_and_oserror_gracefully(self) -> None:
        from unittest.mock import patch

        from hardware_admin.infrastructure.logging_setup import configure_logging

        # 1. Fallo por PermissionError al crear directorio de logs
        with patch("pathlib.Path.mkdir", side_effect=PermissionError("Acceso denegado a logs")):
            log_path = configure_logging()
            self.assertIsNotNone(log_path)
            self.assertTrue(str(log_path).endswith("app.log"))

        # 2. Fallo por OSError / PermissionError al instanciar RotatingFileHandler
        with patch(
            "hardware_admin.infrastructure.logging_setup.RotatingFileHandler",
            side_effect=PermissionError("app.log bloqueado"),
        ):
            log_path = configure_logging()
            self.assertIsNotNone(log_path)
            self.assertTrue(str(log_path).endswith("app.log"))

