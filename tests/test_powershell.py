import json
from subprocess import CompletedProcess, TimeoutExpired
from unittest import TestCase
from unittest.mock import patch

from hardware_admin.infrastructure.powershell import (
    _QUERY_SCRIPTS,
    MAX_OUTPUT_CHARS,
    CommandResult,
    MalformedQueryOutput,
    PowerShellQuery,
    SafePowerShellRunner,
    UnknownQuery,
    parse_json_rows,
)


class PowerShellTests(TestCase):
    def test_parser_normalizes_one_object_and_a_list(self) -> None:
        one = CommandResult(PowerShellQuery.CPU_INFO, '{"Name":"CPU"}', 0)
        many = CommandResult(PowerShellQuery.USB_PRESENT, '[{"Status":"OK"}]', 0)

        self.assertEqual(parse_json_rows(one), [{"Name": "CPU"}])
        self.assertEqual(parse_json_rows(many), [{"Status": "OK"}])

    @patch("hardware_admin.infrastructure.powershell.subprocess.run")
    def test_runner_uses_an_argument_list_and_no_shell(self, run_mock: object) -> None:
        typed_mock = run_mock
        typed_mock.return_value = CompletedProcess([], 0, "[]", "")  # type: ignore[attr-defined]

        result = SafePowerShellRunner(timeout_seconds=3).run(PowerShellQuery.USB_PRESENT)

        self.assertEqual(result.exit_code, 0)
        call = typed_mock.call_args  # type: ignore[attr-defined]
        command = call.args[0]
        self.assertIsInstance(command, list)
        self.assertNotIn("shell", call.kwargs)
        self.assertEqual(call.kwargs["timeout"], 3)
        self.assertIn("ConvertTo-Json", command[-1])
        json.loads(result.output)


class MalformedOutputTests(TestCase):
    """Una salida corrupta no puede disfrazarse de inventario vacio.

    En la fase 3 una lista vacia paso a significar algo concreto —el caso
    «USB ausente»—, asi que devolver [] ante un JSON invalido confundiria un
    fallo de lectura con la ausencia real de dispositivos.
    """

    def test_truncated_output_is_rejected_with_a_legible_detail(self) -> None:
        result = CommandResult(PowerShellQuery.USB_PRESENT, '[{"a":1},{"b":', 0)

        with self.assertRaises(MalformedQueryOutput) as caught:
            parse_json_rows(result)

        detalle = str(caught.exception)
        self.assertIn("usb_present", detalle)
        self.assertIn("JSON", detalle)

    def test_a_warning_line_before_the_json_is_rejected(self) -> None:
        """PowerShell puede anteponer texto; eso no es un inventario."""
        result = CommandResult(
            PowerShellQuery.USB_PRESENT, "ADVERTENCIA: acceso denegado", 0
        )

        with self.assertRaises(MalformedQueryOutput):
            parse_json_rows(result)

    def test_an_oversized_output_is_refused_before_parsing(self) -> None:
        """Limite de tamano: no se intenta interpretar una salida desmedida."""
        huge = "[" + ",".join(['{"a":1}'] * 200_000) + "]"
        self.assertGreater(len(huge), MAX_OUTPUT_CHARS)
        result = CommandResult(PowerShellQuery.USB_PRESENT, huge, 0)

        with self.assertRaises(MalformedQueryOutput) as caught:
            parse_json_rows(result)

        self.assertIn("tamaño", str(caught.exception))

    def test_a_json_scalar_is_not_a_row_list(self) -> None:
        """Un numero o una cadena son JSON valido pero no un inventario."""
        result = CommandResult(PowerShellQuery.USB_PRESENT, "42", 0)

        with self.assertRaises(MalformedQueryOutput):
            parse_json_rows(result)

    def test_an_empty_output_is_still_an_empty_inventory_not_an_error(self) -> None:
        """Sin salida no hay corrupcion: es ausencia de filas, y eso es valido."""
        self.assertEqual(parse_json_rows(CommandResult(PowerShellQuery.USB_PRESENT, "", 0)), [])
        self.assertEqual(parse_json_rows(CommandResult(PowerShellQuery.USB_PRESENT, "[]", 0)), [])

    def test_a_failed_query_returns_no_rows_without_raising(self) -> None:
        """Si la consulta ya fallo, el codigo de salida manda; no hay que parsear."""
        result = CommandResult(PowerShellQuery.USB_PRESENT, "basura", 1, error="denegado")

        self.assertEqual(parse_json_rows(result), [])


class ClosedCatalogTests(TestCase):
    """Control declarado: «consultas fijas, sin entrada del usuario»."""

    def test_every_catalogued_query_has_a_script(self) -> None:
        """Un miembro sin script seria un hueco silencioso en el catalogo."""
        faltan = [query.value for query in PowerShellQuery if query not in _QUERY_SCRIPTS]

        self.assertEqual(faltan, [])

    @patch("subprocess.run")
    def test_an_arbitrary_string_is_refused_without_running_anything(
        self, run: object
    ) -> None:
        """Lo esencial: se rechaza ANTES de invocar el interprete."""
        with self.assertRaises(UnknownQuery) as caught:
            SafePowerShellRunner().run("Get-Process; Remove-Item C:/")  # type: ignore[arg-type]

        self.assertIn("no pertenece al catálogo", str(caught.exception))
        run.assert_not_called()  # type: ignore[attr-defined]

    @patch("subprocess.run")
    def test_the_command_carries_only_the_catalogued_script(self, run: object) -> None:
        """Nada externo se compone dentro del comando que recibe el interprete.

        Las llaves son sintaxis normal de PowerShell (@{...}), asi que buscarlas
        no prueba nada. Lo que prueba el control es que el guion enviado sea
        exactamente el del catalogo, envuelto en la cabecera fija.
        """
        run.return_value = CompletedProcess(  # type: ignore[attr-defined]
            args=[], returncode=0, stdout="[]", stderr=""
        )

        SafePowerShellRunner().run(PowerShellQuery.CPU_INFO)

        argumentos = run.call_args.args[0]  # type: ignore[attr-defined]
        self.assertIsInstance(argumentos, list)
        self.assertEqual(argumentos[0], "powershell.exe")
        self.assertIn("-NoProfile", argumentos)
        enviado = argumentos[-1]
        self.assertIn(_QUERY_SCRIPTS[PowerShellQuery.CPU_INFO], enviado)
        # Ningun otro guion del catalogo se cuela en la misma invocacion.
        for query, script in _QUERY_SCRIPTS.items():
            if query is not PowerShellQuery.CPU_INFO:
                self.assertNotIn(script, enviado)


class TimeoutTests(TestCase):
    """Control declarado: «proceso colgado → timeout y finalizacion controlada»."""

    @patch("subprocess.run")
    def test_a_hung_query_is_reported_as_timed_out_not_as_a_crash(
        self, run: object
    ) -> None:
        run.side_effect = TimeoutExpired(cmd="powershell.exe", timeout=15.0)  # type: ignore[attr-defined]

        result = SafePowerShellRunner(timeout_seconds=15.0).run(PowerShellQuery.CPU_INFO)

        self.assertTrue(result.timed_out)
        self.assertEqual(result.exit_code, -1)
        self.assertIn("Tiempo agotado", result.error)

    @patch("subprocess.run")
    def test_a_timed_out_query_yields_no_rows_instead_of_raising(
        self, run: object
    ) -> None:
        """Su codigo de salida manda: no se intenta parsear una salida parcial."""
        run.side_effect = TimeoutExpired(cmd="powershell.exe", timeout=15.0)  # type: ignore[attr-defined]

        result = SafePowerShellRunner().run(PowerShellQuery.USB_PRESENT)

        self.assertEqual(parse_json_rows(result), [])
