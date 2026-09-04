import json
from subprocess import CompletedProcess
from unittest import TestCase
from unittest.mock import patch

from hardware_admin.infrastructure.powershell import (
    CommandResult,
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
