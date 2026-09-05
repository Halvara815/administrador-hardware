import json
from subprocess import CompletedProcess
from unittest import TestCase
from unittest.mock import patch

from hardware_admin.infrastructure.powershell import (
    MAX_OUTPUT_CHARS,
    CommandResult,
    MalformedQueryOutput,
    PowerShellQuery,
    SafePowerShellRunner,
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
