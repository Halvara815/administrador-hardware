"""Pruebas unitarias de la Fase F2 Comercial: almacenamiento profundo, batería, firmware y memoria."""

from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

from hardware_admin.collectors.core import MemoryCollector, SystemCollector
from hardware_admin.collectors.storage import StorageCollector
from hardware_admin.domain.models import ComponentKind, ConfidenceLevel, HealthStatus
from hardware_admin.infrastructure.commands import SafeCommandRunner, generate_battery_report
from hardware_admin.infrastructure.powershell import CommandResult, PowerShellQuery


def mock_cmd_result(output: str, query: PowerShellQuery, exit_code: int = 0, error: str = "") -> CommandResult:
    return CommandResult(
        query=query,
        output=output,
        exit_code=exit_code,
        error=error,
    )


class CommercialF2StorageTests(TestCase):
    """Pruebas de salud profunda de almacenamiento y contadores SMART/Reliability."""

    def setUp(self) -> None:
        self.runner = MagicMock()
        self.collector = StorageCollector(self.runner)

    @patch("psutil.disk_partitions")
    @patch("psutil.disk_usage")
    def test_storage_deep_reliability_counters_healthy(
        self, mock_usage: MagicMock, mock_partitions: MagicMock
    ) -> None:
        """Un disco saludable con contadores SMART/Reliability genera mediciones cuantitativas y confianza alta."""
        mock_part = MagicMock()
        mock_part.mountpoint = "C:\\"
        mock_part.fstype = "NTFS"
        mock_partitions.return_value = [mock_part]

        usage_mock = MagicMock()
        usage_mock.total = 512 * 1024**3
        usage_mock.free = 300 * 1024**3
        usage_mock.used = 212 * 1024**3
        usage_mock.percent = 41.4
        mock_usage.return_value = usage_mock

        phys_json = '[{"DeviceId":"0","FriendlyName":"Samsung 980 PRO 500GB","MediaType":"SSD","BusType":"NVMe","HealthStatus":"Healthy","Size":500107862016}]'
        vol_json = '[{"DriveLetter":"C","FileSystem":"NTFS","HealthStatus":"Healthy","Size":500000000000,"SizeRemaining":300000000000}]'
        disks_json = '[{"Unidad":0,"Dispositivo":"Samsung 980 PRO 500GB","Tipo de bus":"NVMe","Estado":"Online","Salud":"Healthy","Capacidad":500107862016}]'
        rel_json = '[{"DeviceId":"0","FriendlyName":"Samsung 980 PRO 500GB","MediaType":"SSD","BusType":"NVMe","OperationalStatus":"OK","HealthStatus":"Healthy","Temperature":38,"Wear":5,"ReadErrorsTotal":0,"WriteErrorsTotal":0,"PowerOnHours":1240}]'

        def run_side_effect(query: PowerShellQuery) -> CommandResult:
            if query == PowerShellQuery.PHYSICAL_DISKS:
                return mock_cmd_result(phys_json, query)
            if query == PowerShellQuery.VOLUMES:
                return mock_cmd_result(vol_json, query)
            if query == PowerShellQuery.STORAGE_RELIABILITY:
                return mock_cmd_result(rel_json, query)
            return mock_cmd_result(disks_json, query)

        self.runner.run.side_effect = run_side_effect

        result = self.collector.collect()
        self.assertEqual(result.component, ComponentKind.DISK)
        self.assertEqual(result.status, HealthStatus.NORMAL)
        self.assertEqual(result.confidence, ConfidenceLevel.HIGH)

        # Verificar extracción de mediciones cuantitativas
        measurement_names = {m.name for m in result.measurements}
        self.assertIn("Temperatura (Samsung 980 PRO 500GB)", measurement_names)
        self.assertIn("Desgaste (Samsung 980 PRO 500GB)", measurement_names)
        self.assertIn("Horas encendido (Samsung 980 PRO 500GB)", measurement_names)
        self.assertIn("Uso C:\\", measurement_names)

        # Verificar datos de disco físico
        disks = result.facts.get("Discos físicos", [])
        self.assertEqual(len(disks), 1)
        self.assertEqual(disks[0]["Temperatura"], "38 °C")
        self.assertEqual(disks[0]["Desgaste"], "5%")
        self.assertEqual(disks[0]["Horas de encendido"], "1240 h")

    @patch("psutil.disk_partitions")
    @patch("psutil.disk_usage")
    def test_isolated_read_errors_do_not_falsely_flag_healthy_disk(
        self, mock_usage: MagicMock, mock_partitions: MagicMock
    ) -> None:
        """Regla canónica: Nunca deducir disco dañado por un contador acumulado aislado si la salud es Healthy."""
        mock_partitions.return_value = []
        phys_json = '[{"DeviceId":"0","FriendlyName":"Crucial MX500","MediaType":"SSD","BusType":"SATA","HealthStatus":"Healthy","Size":500107862016}]'
        # Contador acumulado de errores de lectura antiguos pero HealthStatus reporta Healthy
        rel_json = '[{"DeviceId":"0","FriendlyName":"Crucial MX500","MediaType":"SSD","BusType":"SATA","OperationalStatus":"OK","HealthStatus":"Healthy","Temperature":32,"Wear":12,"ReadErrorsTotal":3,"WriteErrorsTotal":0,"PowerOnHours":8500}]'

        def run_side_effect(query: PowerShellQuery) -> CommandResult:
            if query == PowerShellQuery.PHYSICAL_DISKS:
                return mock_cmd_result(phys_json, query)
            if query == PowerShellQuery.STORAGE_RELIABILITY:
                return mock_cmd_result(rel_json, query)
            return mock_cmd_result("[]", query)

        self.runner.run.side_effect = run_side_effect

        result = self.collector.collect()
        self.assertEqual(result.status, HealthStatus.NORMAL)
        self.assertIsNone(result.possible_problem)
        self.assertEqual(result.confidence, ConfidenceLevel.HIGH)

    @patch("psutil.disk_partitions")
    @patch("psutil.disk_usage")
    def test_storage_reliability_permission_denied_graceful_fallback(
        self, mock_usage: MagicMock, mock_partitions: MagicMock
    ) -> None:
        """Si falta elevación de administrador, Get-StorageReliabilityCounter se degrada sin generar alerta de fallo."""
        mock_partitions.return_value = []
        phys_json = '[{"DeviceId":"0","FriendlyName":"WD Blue 1TB","MediaType":"HDD","BusType":"SATA","HealthStatus":"Healthy","Size":1000000000000}]'

        def run_side_effect(query: PowerShellQuery) -> CommandResult:
            if query == PowerShellQuery.PHYSICAL_DISKS:
                return mock_cmd_result(phys_json, query)
            if query == PowerShellQuery.STORAGE_RELIABILITY:
                return mock_cmd_result("", query, exit_code=1, error="Access is denied. (Exception from HRESULT: 0x80070005)")
            return mock_cmd_result("[]", query)

        self.runner.run.side_effect = run_side_effect

        result = self.collector.collect()
        self.assertEqual(result.status, HealthStatus.NORMAL)
        self.assertEqual(result.confidence, ConfidenceLevel.MEDIUM)
        self.assertIn("No disponible por permisos", result.facts.get("Fiabilidad física (SMART)", ""))

    @patch("psutil.disk_partitions")
    @patch("psutil.disk_usage")
    def test_storage_missing_health_status_not_substituted_with_healthy(
        self, mock_usage: MagicMock, mock_partitions: MagicMock
    ) -> None:
        """Regla canónica: HealthStatus ausente nunca debe reemplazarse por 'Healthy'."""
        mock_partitions.return_value = []
        phys_json = '[{"DeviceId":"0","FriendlyName":"Generic NVMe Drive","MediaType":"SSD","BusType":"NVMe","HealthStatus":null,"Size":256060514304}]'

        def run_side_effect(query: PowerShellQuery) -> CommandResult:
            if query == PowerShellQuery.PHYSICAL_DISKS:
                return mock_cmd_result(phys_json, query)
            if query == PowerShellQuery.STORAGE_RELIABILITY:
                return mock_cmd_result("[]", query)
            return mock_cmd_result("[]", query)

        self.runner.run.side_effect = run_side_effect

        result = self.collector.collect()
        self.assertEqual(result.status, HealthStatus.NORMAL)
        self.assertEqual(result.confidence, ConfidenceLevel.LOW)
        disks = result.facts.get("Discos físicos", [])
        self.assertEqual(len(disks), 1)
        self.assertEqual(disks[0]["Salud"], "No disponible")

    @patch("psutil.disk_partitions")
    @patch("psutil.disk_usage")
    def test_storage_incompatible_controller_or_unexposed_smart(
        self, mock_usage: MagicMock, mock_partitions: MagicMock
    ) -> None:
        """Si el controlador o bus no expone SMART, se degrada a no soportado sin marcar disco roto."""
        mock_partitions.return_value = []
        phys_json = '[{"DeviceId":"0","FriendlyName":"RAID Virtual Disk","MediaType":"Unspecified","BusType":"RAID","HealthStatus":"Healthy","Size":1000000000000}]'
        # Get-StorageReliabilityCounter reporta NotSupported o ReliabilityError
        rel_json = '[{"DeviceId":"0","ReliabilityError":"The command is not supported by the storage subsystem."}]'

        def run_side_effect(query: PowerShellQuery) -> CommandResult:
            if query == PowerShellQuery.PHYSICAL_DISKS:
                return mock_cmd_result(phys_json, query)
            if query == PowerShellQuery.STORAGE_RELIABILITY:
                return mock_cmd_result(rel_json, query)
            return mock_cmd_result("[]", query)

        self.runner.run.side_effect = run_side_effect

        result = self.collector.collect()
        self.assertEqual(result.status, HealthStatus.NORMAL)
        self.assertEqual(result.confidence, ConfidenceLevel.MEDIUM)
        disks = result.facts.get("Discos físicos", [])
        self.assertEqual(len(disks), 1)
        self.assertEqual(disks[0]["Fiabilidad SMART"], "No soportado por el controlador/unidad")


class CommercialF2SystemAndBatteryTests(TestCase):
    """Pruebas para información del sistema, firmware, TPM, Secure Boot y batería."""

    def setUp(self) -> None:
        self.runner = MagicMock()
        self.collector = SystemCollector(self.runner)

    def test_laptop_with_healthy_battery_and_firmware(self) -> None:
        """Una laptop con batería y firmware completo reporta métricas y estado normales."""
        sys_json = '[{"Fabricante":"Dell Inc.","Modelo":"XPS 15 9520","SistemaOperativo":"Microsoft Windows 11 Pro"}]'
        firm_json = '[{"BiosVendor":"Dell Inc.","BiosVersion":"1.12.0","BiosDate":"2023-08-15","BoardManufacturer":"Dell Inc.","BoardProduct":"0HNKD","BoardVersion":"A00","TpmPresent":true,"TpmReady":true,"TpmEnabled":true,"SecureBoot":true}]'
        batt_json = '[{"TieneBateria":true,"PlanEnergia":"Equilibrado","Baterias":[{"DeviceID":"Dell Battery","EstimatedChargeRemaining":85,"BatteryStatus":1,"DesignCapacity":86000,"FullChargeCapacity":81700}]}]'

        def run_side_effect(query: PowerShellQuery) -> CommandResult:
            if query == PowerShellQuery.SYSTEM_INFO:
                return mock_cmd_result(sys_json, query)
            if query == PowerShellQuery.FIRMWARE_INFO:
                return mock_cmd_result(firm_json, query)
            if query == PowerShellQuery.BATTERY_INFO:
                return mock_cmd_result(batt_json, query)
            return mock_cmd_result("[]", query)

        self.runner.run.side_effect = run_side_effect

        result = self.collector.collect()
        self.assertEqual(result.component, ComponentKind.SYSTEM)
        self.assertEqual(result.status, HealthStatus.NORMAL)
        self.assertEqual(result.confidence, ConfidenceLevel.HIGH)

        self.assertIn("85%", result.facts.get("Batería", ""))
        self.assertEqual(result.facts.get("Plan de energía"), "Equilibrado")
        self.assertIn("Dell Inc.", result.facts.get("Placa base", ""))
        self.assertIn("1.12.0", result.facts.get("BIOS / UEFI", ""))
        self.assertIn("Habilitado", result.facts.get("Módulo TPM", ""))
        self.assertEqual(result.facts.get("Arranque seguro (Secure Boot)"), "Habilitado")

        # Comprobar mediciones
        m_names = {m.name: m.value for m in result.measurements}
        self.assertIn("Carga de batería", m_names)
        self.assertEqual(m_names["Carga de batería"], 85.0)
        self.assertIn("Desgaste de batería", m_names)
        self.assertEqual(m_names["Desgaste de batería"], 5.0)

    def test_laptop_with_empty_smbios_battery_capacity_does_not_deduce_bad_battery(self) -> None:
        """Regla canónica: Si los campos SMBIOS de capacidad están ausentes, no inventar batería mala."""
        sys_json = '[{"Fabricante":"Lenovo","Modelo":"ThinkPad T14","SistemaOperativo":"Microsoft Windows 11 Pro"}]'
        firm_json = '[{"BiosVendor":"LENOVO","BiosVersion":"N2DET32W","BiosDate":"2023-01-10","BoardManufacturer":"LENOVO","BoardProduct":"20UD000BUS","BoardVersion":"SDK0J40697","TpmPresent":true,"TpmReady":true,"TpmEnabled":true,"SecureBoot":true}]'
        # SMBIOS no expone DesignCapacity ni FullChargeCapacity (común en algunas baterías OEM genéricas)
        batt_json = '[{"TieneBateria":true,"PlanEnergia":"Alto rendimiento","Baterias":[{"DeviceID":"Battery 1","EstimatedChargeRemaining":90,"BatteryStatus":1,"DesignCapacity":null,"FullChargeCapacity":null}]}]'

        def run_side_effect(query: PowerShellQuery) -> CommandResult:
            if query == PowerShellQuery.SYSTEM_INFO:
                return mock_cmd_result(sys_json, query)
            if query == PowerShellQuery.FIRMWARE_INFO:
                return mock_cmd_result(firm_json, query)
            if query == PowerShellQuery.BATTERY_INFO:
                return mock_cmd_result(batt_json, query)
            return mock_cmd_result("[]", query)

        self.runner.run.side_effect = run_side_effect

        result = self.collector.collect()
        self.assertEqual(result.status, HealthStatus.NORMAL)
        self.assertEqual(
            result.facts.get("Desgaste de batería"),
            "No reportado por el firmware SMBIOS",
        )

    def test_desktop_pc_without_battery_reports_clean_not_applicable(self) -> None:
        """En equipos de sobremesa sin batería, se reporta No aplica de forma limpia sin alertas."""
        sys_json = '[{"Fabricante":"ASUSTeK COMPUTER INC.","Modelo":"System Product Name","SistemaOperativo":"Microsoft Windows 11 Pro"}]'
        firm_json = '[{"BiosVendor":"American Megatrends Inc.","BiosVersion":"2801","BiosDate":"2023-05-10","BoardManufacturer":"ASUSTeK COMPUTER INC.","BoardProduct":"ROG STRIX B550-F GAMING","BoardVersion":"Rev 1.xx","TpmPresent":true,"TpmReady":true,"TpmEnabled":true,"SecureBoot":true}]'
        batt_json = '[{"TieneBateria":false,"PlanEnergia":"Equilibrado","Baterias":[]}]'

        def run_side_effect(query: PowerShellQuery) -> CommandResult:
            if query == PowerShellQuery.SYSTEM_INFO:
                return mock_cmd_result(sys_json, query)
            if query == PowerShellQuery.FIRMWARE_INFO:
                return mock_cmd_result(firm_json, query)
            if query == PowerShellQuery.BATTERY_INFO:
                return mock_cmd_result(batt_json, query)
            return mock_cmd_result("[]", query)

        self.runner.run.side_effect = run_side_effect

        result = self.collector.collect()
        self.assertEqual(result.status, HealthStatus.NORMAL)
        self.assertEqual(result.facts.get("Batería"), "No aplica (Equipo de sobremesa sin batería)")

    def test_peripherals_isolated_failure_does_not_condemn_subsystem(self) -> None:
        """Un fallo aislado en un periférico (ej. cámara con error de driver) no condena todo el subsistema ni el bus."""
        sys_json = '[{"Fabricante":"Dell Inc.","Modelo":"XPS 15","SistemaOperativo":"Microsoft Windows 11 Pro"}]'
        firm_json = '[{"BiosVendor":"Dell","BiosVersion":"1.0","BiosDate":"2023-01-01","BoardManufacturer":"Dell","BoardProduct":"0HNKD","BoardVersion":"A00","TpmPresent":true,"TpmReady":true,"TpmEnabled":true,"SecureBoot":true}]'
        batt_json = '[{"TieneBateria":false,"PlanEnergia":"Equilibrado","Baterias":[]}]'
        periph_json = (
            '['
            '{"Class":"Bluetooth","FriendlyName":"Intel Wireless Bluetooth","Status":"OK"},'
            '{"Class":"Camera","FriendlyName":"Integrated Webcam","Status":"Error"},'
            '{"Class":"Media","FriendlyName":"Realtek High Definition Audio","Status":"OK"}'
            ']'
        )

        def run_side_effect(query: PowerShellQuery) -> CommandResult:
            if query == PowerShellQuery.SYSTEM_INFO:
                return mock_cmd_result(sys_json, query)
            if query == PowerShellQuery.FIRMWARE_INFO:
                return mock_cmd_result(firm_json, query)
            if query == PowerShellQuery.BATTERY_INFO:
                return mock_cmd_result(batt_json, query)
            if query == PowerShellQuery.PERIPHERALS_EXTENDED:
                return mock_cmd_result(periph_json, query)
            return mock_cmd_result("[]", query)

        self.runner.run.side_effect = run_side_effect

        result = self.collector.collect()
        self.assertEqual(result.status, HealthStatus.NORMAL)
        self.assertIn("1 dispositivo(s) detectado(s)", result.facts.get("Bluetooth", ""))
        self.assertIn("1 dispositivo(s) detectado(s)", result.facts.get("Cámara web", ""))
        self.assertIn("Integrated Webcam", result.facts.get("Anomalías en periféricos", ""))
        self.assertIn("operan con normalidad", result.facts.get("Anomalías en periféricos", ""))


class CommercialF2MemoryTests(TestCase):
    """Pruebas para módulos físicos de memoria RAM (Win32_PhysicalMemory)."""

    def setUp(self) -> None:
        self.runner = MagicMock()
        self.collector = MemoryCollector(self.runner)

    @patch("psutil.virtual_memory")
    @patch("psutil.swap_memory")
    def test_memory_physical_modules_populated(
        self, mock_swap: MagicMock, mock_vm: MagicMock
    ) -> None:
        """La detección de módulos físicos por ranura desglosa slots, fabricantes y velocidad configurada."""
        vm = MagicMock()
        vm.total = 16 * 1024**3
        vm.available = 10 * 1024**3
        vm.used = 6 * 1024**3
        vm.percent = 37.5
        mock_vm.return_value = vm

        swap = MagicMock()
        swap.used = 1 * 1024**3
        mock_swap.return_value = swap

        modules_json = (
            '['
            '{"BankLabel":"BANK 0","DeviceLocator":"DIMM 1","Capacity":8589934592,"Speed":3200,"ConfiguredClockSpeed":3200,"Manufacturer":"Kingston","PartNumber":"KHX3200C16D4/8GX"},'
            '{"BankLabel":"BANK 2","DeviceLocator":"DIMM 2","Capacity":8589934592,"Speed":3200,"ConfiguredClockSpeed":3200,"Manufacturer":"Kingston","PartNumber":"KHX3200C16D4/8GX"}'
            ']'
        )

        self.runner.run.return_value = mock_cmd_result(
            modules_json, PowerShellQuery.PHYSICAL_MEMORY_MODULES
        )

        result = self.collector.collect()
        self.assertEqual(result.component, ComponentKind.MEMORY)
        self.assertEqual(result.status, HealthStatus.NORMAL)
        self.assertEqual(result.confidence, ConfidenceLevel.HIGH)

        modules = result.facts.get("Módulos físicos", [])
        self.assertEqual(len(modules), 2)
        self.assertEqual(result.facts.get("Ranuras ocupadas"), 2)
        self.assertEqual(modules[0]["Ranura"], "DIMM 1")
        self.assertEqual(modules[0]["Velocidad"], "3200 MHz")
        self.assertEqual(modules[0]["Fabricante"], "Kingston")

        # Comprobar mediciones de memoria
        m_names = {m.name: m.value for m in result.measurements}
        self.assertIn("Capacidad total RAM", m_names)
        self.assertIn("Velocidad configurada RAM", m_names)
        self.assertEqual(m_names["Velocidad configurada RAM"], 3200)

    @patch("psutil.virtual_memory")
    @patch("psutil.swap_memory")
    def test_memory_empty_smbios_modules_graceful(
        self, mock_swap: MagicMock, mock_vm: MagicMock
    ) -> None:
        """Si SMBIOS no devuelve módulos físicos, se declara la ausencia sin fallar."""
        vm = MagicMock()
        vm.total = 8 * 1024**3
        vm.available = 4 * 1024**3
        vm.used = 4 * 1024**3
        vm.percent = 50.0
        mock_vm.return_value = vm

        swap = MagicMock()
        swap.used = 512 * 1024**2
        mock_swap.return_value = swap

        self.runner.run.return_value = mock_cmd_result("[]", PowerShellQuery.PHYSICAL_MEMORY_MODULES)

        result = self.collector.collect()
        self.assertEqual(result.status, HealthStatus.NORMAL)
        self.assertEqual(result.confidence, ConfidenceLevel.MEDIUM)
        self.assertEqual(result.facts.get("Módulos físicos"), "No reportados por el firmware SMBIOS")

    @patch("psutil.virtual_memory")
    @patch("psutil.swap_memory")
    def test_memory_smbios_type_decoding_and_expansion_limit(
        self, mock_swap: MagicMock, mock_vm: MagicMock
    ) -> None:
        """Verifica la decodificación precisa de SMBIOS (DDR4 vs No especificado) y el límite de ampliación."""
        vm = MagicMock()
        vm.total = 16 * 1024**3
        vm.available = 8 * 1024**3
        vm.used = 8 * 1024**3
        vm.percent = 50.0
        mock_vm.return_value = vm
        mock_swap.return_value = MagicMock(used=0)

        # Módulo 1: SMBIOSMemoryType 26 -> DDR4, FormFactor 9 -> DIMM
        # Módulo 2: SMBIOSMemoryType 999 (desconocido) -> "No especificado por SMBIOS", FormFactor 12 -> SODIMM
        modules_json = (
            '['
            '{"DeviceLocator":"DIMM 0","Capacity":8589934592,"Speed":3200,"ConfiguredClockSpeed":3200,"Manufacturer":"Crucial","SMBIOSMemoryType":26,"FormFactor":8},'
            '{"DeviceLocator":"DIMM 1","Capacity":8589934592,"Speed":3200,"ConfiguredClockSpeed":3200,"Manufacturer":"Crucial","SMBIOSMemoryType":999,"FormFactor":12}'
            ']'
        )
        self.runner.run.return_value = mock_cmd_result(modules_json, PowerShellQuery.PHYSICAL_MEMORY_MODULES)

        result = self.collector.collect()
        modules = result.facts.get("Módulos físicos", [])
        self.assertEqual(len(modules), 2)
        self.assertEqual(modules[0]["Tipo / Generación"], "DDR4")
        self.assertEqual(modules[0]["Factor de forma"], "DIMM")
        self.assertEqual(modules[1]["Tipo / Generación"], "No especificado por SMBIOS")
        self.assertEqual(modules[1]["Factor de forma"], "SODIMM")
        self.assertEqual(
            result.facts.get("Límite de ampliación"),
            "Pendiente de validación de compatibilidad con placa base (Asesor E2)",
        )


class CommercialF2CommandTests(TestCase):
    """Pruebas para la generación segura del reporte powercfg /batteryreport."""

    def test_battery_report_command_valid_path(self) -> None:
        runner = SafeCommandRunner()
        with patch.object(runner, "_execute") as mock_exec:
            mock_exec.return_value = MagicMock(exit_code=0, error="")
            res = generate_battery_report(Path("C:\\temp\\report.html"), runner=runner)
            self.assertIsNotNone(res)
            mock_exec.assert_called_once()
            args = mock_exec.call_args[0][0]
            self.assertEqual(args[0], "powercfg.exe")
            self.assertEqual(args[1], "/batteryreport")
            self.assertEqual(args[2], "/output")

    def test_battery_report_command_rejects_unsafe_path(self) -> None:
        runner = SafeCommandRunner()
        res = runner.battery_report("C:\\temp\\report.html & calc.exe")
        self.assertEqual(res.exit_code, -1)
        self.assertIn("inválida o no segura", res.error)
