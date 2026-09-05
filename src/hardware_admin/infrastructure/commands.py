"""Ejecución segura de comandos nativos de Windows mediante argumentos cerrados y validados."""

from __future__ import annotations

import ipaddress
import re
import subprocess
from dataclasses import dataclass

#: Patrón seguro para nombres de host o dominios sin caracteres de inyección.
_SAFE_HOST_REGEX = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$")

#: Caracteres y operadores de shell estrictamente prohibidos en cualquier argumento.
_DISALLOWED_CHARS = set("&|;><`$\r\n\x00")


@dataclass(frozen=True, slots=True)
class NativeCommandResult:
    """Resultado de ejecución de una herramienta nativa de Windows."""

    command: tuple[str, ...]
    output: str
    exit_code: int
    timed_out: bool = False
    error: str = ""


class SafeCommandRunner:
    """Ejecutor de comandos de diagnóstico con catálogo cerrado y shell=False."""

    def __init__(self, default_timeout_seconds: float = 5.0) -> None:
        self.default_timeout_seconds = default_timeout_seconds

    @staticmethod
    def is_safe_ip_or_host(value: str) -> bool:
        """Verifica si una cadena es una IP válida o un nombre de host seguro."""
        if not value or any(ch in _DISALLOWED_CHARS for ch in value):
            return False
        clean = value.strip()
        try:
            ipaddress.ip_address(clean)
            return True
        except ValueError:
            pass
        return bool(_SAFE_HOST_REGEX.match(clean))

    def _execute(self, args: list[str], timeout: float | None = None) -> NativeCommandResult:
        """Ejecuta una lista fija de argumentos con shell=False y sin ventana de consola."""
        # Validación preventiva contra inyección
        for arg in args:
            if any(ch in _DISALLOWED_CHARS for ch in arg):
                return NativeCommandResult(
                    command=tuple(args),
                    output="",
                    exit_code=-1,
                    error=f"Argumento inválido con caracteres no permitidos: {arg!r}",
                )

        timeout_sec = timeout if timeout is not None else self.default_timeout_seconds
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            completed = subprocess.run(
                args,
                capture_output=True,
                timeout=timeout_sec,
                shell=False,
                creationflags=creation_flags,
                check=False,
            )
            stdout = self._decode_output(completed.stdout)
            stderr = self._decode_output(completed.stderr)
            return NativeCommandResult(
                command=tuple(args),
                output=stdout.strip(),
                exit_code=completed.returncode,
                error=stderr.strip(),
            )
        except subprocess.TimeoutExpired as exc:
            partial = self._decode_output(exc.stdout) if exc.stdout else ""
            return NativeCommandResult(
                command=tuple(args),
                output=partial.strip(),
                exit_code=-1,
                timed_out=True,
                error=f"Tiempo agotado ({timeout_sec}s)",
            )
        except OSError as exc:
            return NativeCommandResult(
                command=tuple(args),
                output="",
                exit_code=-1,
                error=str(exc),
            )

    @staticmethod
    def _decode_output(raw_bytes: bytes | None) -> str:
        if not raw_bytes:
            return ""
        for encoding in ("utf-8", "cp850", "cp1252", "latin-1"):
            try:
                return raw_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw_bytes.decode("utf-8", errors="replace")

    def ipconfig_all(self, timeout: float = 10.0) -> NativeCommandResult:
        """Ejecuta cmd.exe /d /c ipconfig /all para obtener configuración detallada."""
        return self._execute(["cmd.exe", "/d", "/c", "ipconfig", "/all"], timeout=timeout)

    def ping(
        self,
        target: str,
        count: int = 1,
        timeout_ms: int = 3000,
        overall_timeout: float = 5.0,
    ) -> NativeCommandResult:
        """Ejecuta ping.exe hacia un destino validado sin operadores de shell."""
        if not self.is_safe_ip_or_host(target):
            return NativeCommandResult(
                command=("ping.exe", target),
                output="",
                exit_code=-1,
                error=f"Destino de ping inválido o no seguro: {target!r}",
            )
        safe_count = max(1, min(4, count))
        safe_timeout_ms = max(500, min(10000, timeout_ms))
        return self._execute(
            ["ping.exe", "-n", str(safe_count), "-w", str(safe_timeout_ms), target.strip()],
            timeout=overall_timeout,
        )

    def nslookup(self, domain: str = "google.com", timeout: float = 5.0) -> NativeCommandResult:
        """Ejecuta nslookup.exe para validar resolución DNS determinista."""
        if not self.is_safe_ip_or_host(domain):
            return NativeCommandResult(
                command=("nslookup.exe", domain),
                output="",
                exit_code=-1,
                error=f"Dominio de consulta inválido o no seguro: {domain!r}",
            )
        return self._execute(["nslookup.exe", domain.strip()], timeout=timeout)

    def arp_a(self, timeout: float = 5.0) -> NativeCommandResult:
        """Ejecuta arp.exe -a para consultar la tabla de resolución local conocida."""
        return self._execute(["arp.exe", "-a"], timeout=timeout)

