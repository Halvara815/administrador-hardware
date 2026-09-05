"""Pruebas unitarias de seguridad y ejecución de SafeCommandRunner."""

from subprocess import TimeoutExpired
from unittest import TestCase
from unittest.mock import MagicMock, patch

from hardware_admin.infrastructure.commands import SafeCommandRunner


class SafeCommandRunnerTests(TestCase):
    def setUp(self) -> None:
        self.runner = SafeCommandRunner(default_timeout_seconds=2.0)

    def test_safe_ip_and_host_validation(self) -> None:
        valid_targets = [
            "192.168.0.1",
            "8.8.8.8",
            "10.0.0.1",
            "127.0.0.1",
            "google.com",
            "dns.google",
            "sub.domain-test.org",
            "fe80::1",
        ]
        for target in valid_targets:
            self.assertTrue(
                SafeCommandRunner.is_safe_ip_or_host(target),
                f"Debe ser válido: {target}",
            )

    def test_disallowed_and_injection_strings_are_rejected(self) -> None:
        malicious_targets = [
            "8.8.8.8; dir",
            "127.0.0.1 & calc.exe",
            "google.com | whoami",
            "192.168.1.1 && shutdown",
            "10.0.0.1`whoami`",
            "8.8.8.8\ncalc.exe",
            "192.168.1.1>out.txt",
            "$env:COMPUTERNAME",
            "",
            "   ",
        ]
        for target in malicious_targets:
            self.assertFalse(
                SafeCommandRunner.is_safe_ip_or_host(target),
                f"Debe ser rechazado: {target}",
            )

    def test_ping_rejects_unsafe_target_without_running_subprocess(self) -> None:
        with patch("subprocess.run") as mock_sub:
            result = self.runner.ping("8.8.8.8; dir")
            mock_sub.assert_not_called()
            self.assertEqual(result.exit_code, -1)
            self.assertIn("inválido", result.error)

    def test_nslookup_rejects_unsafe_domain_without_running_subprocess(self) -> None:
        with patch("subprocess.run") as mock_sub:
            result = self.runner.nslookup("google.com | whoami")
            mock_sub.assert_not_called()
            self.assertEqual(result.exit_code, -1)
            self.assertIn("inválido", result.error)

    def test_ping_invokes_subprocess_with_safe_arguments(self) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"Respuesta desde 8.8.8.8: bytes=32 tiempo=15ms TTL=117"
        mock_proc.stderr = b""

        with patch("subprocess.run", return_value=mock_proc) as mock_sub:
            result = self.runner.ping("8.8.8.8", count=1, timeout_ms=2000)
            mock_sub.assert_called_once()
            args, kwargs = mock_sub.call_args
            self.assertEqual(args[0], ["ping.exe", "-n", "1", "-w", "2000", "8.8.8.8"])
            self.assertFalse(kwargs.get("shell", True))
            self.assertEqual(result.exit_code, 0)
            self.assertIn("Respuesta", result.output)

    def test_nslookup_invokes_subprocess_with_safe_arguments(self) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"Non-authoritative answer:\nName: google.com\nAddresses: 142.250.190.46\n"
        mock_proc.stderr = b""

        with patch("subprocess.run", return_value=mock_proc) as mock_sub:
            result = self.runner.nslookup("google.com")
            mock_sub.assert_called_once()
            args, kwargs = mock_sub.call_args
            self.assertEqual(args[0], ["nslookup.exe", "google.com"])
            self.assertFalse(kwargs.get("shell", True))
            self.assertEqual(result.exit_code, 0)
            self.assertIn("142.250.190.46", result.output)



class NativeTimeoutTests(TestCase):
    """Control declarado: proceso colgado con finalizacion controlada."""

    @patch("subprocess.run")
    def test_a_hung_ping_is_reported_as_timed_out(self, run: MagicMock) -> None:
        run.side_effect = TimeoutExpired(cmd="ping.exe", timeout=5.0)

        result = SafeCommandRunner().ping("8.8.8.8")

        self.assertTrue(result.timed_out)
        self.assertEqual(result.exit_code, -1)
        self.assertIn("Tiempo agotado", result.error)

    @patch("subprocess.run")
    def test_a_partial_output_survives_the_timeout(self, run: MagicMock) -> None:
        """Lo recogido antes de agotarse el tiempo no se descarta."""
        run.side_effect = TimeoutExpired(
            cmd="ping.exe", timeout=5.0, output=b"Respuesta desde 8.8.8.8"
        )

        result = SafeCommandRunner().ping("8.8.8.8")

        self.assertTrue(result.timed_out)
        self.assertIn("Respuesta desde", result.output)

    @patch("subprocess.run")
    def test_a_missing_tool_is_reported_without_crashing(self, run: MagicMock) -> None:
        run.side_effect = FileNotFoundError("nslookup.exe no encontrado")

        result = SafeCommandRunner().nslookup("google.com")

        self.assertEqual(result.exit_code, -1)
        self.assertIn("no encontrado", result.error)
