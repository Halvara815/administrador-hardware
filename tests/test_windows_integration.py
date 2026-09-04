import sys
from unittest import TestCase, skipUnless

from hardware_admin.app_factory import build_scan_service
from hardware_admin.domain.models import ComponentKind, HealthStatus


@skipUnless(sys.platform == "win32", "Las consultas PnP/CIM requieren Windows")
class WindowsIntegrationTests(TestCase):
    def test_real_scan_returns_every_component_with_evidence(self) -> None:
        report = build_scan_service().scan()
        by_kind = {result.component: result for result in report.results}

        self.assertEqual(len(report.results), 11)
        self.assertEqual(set(by_kind), set(ComponentKind))
        for result in report.results:
            self.assertTrue(result.summary)
            self.assertTrue(result.evidence)
            self.assertIsInstance(result.status, HealthStatus)

        expected_fact_keys = {
            ComponentKind.SYSTEM: {"Nombre del equipo", "Sistema operativo", "Arquitectura"},
            ComponentKind.CPU: {"Modelo", "Núcleos físicos", "Uso"},
            ComponentKind.MEMORY: {"Total", "Disponible", "Porcentaje de uso"},
            ComponentKind.DISK: {"Unidades", "Discos físicos"},
            ComponentKind.NETWORK: {"Adaptadores"},
            ComponentKind.USB: {"Dispositivos", "Total", "Con problemas"},
            ComponentKind.PCI: {"Dispositivos", "Total", "Con problemas"},
            ComponentKind.DRIVER: {"Controladores", "Consultados", "No firmados"},
            ComponentKind.PROBLEM_DEVICE: {"Dispositivos", "Total", "Con problemas"},
            ComponentKind.MONITOR_GPU: {"Dispositivos gráficos"},
            ComponentKind.IO: {"Lectura de disco", "Escritura de disco", "Recepción de red"},
        }
        for component, keys in expected_fact_keys.items():
            if by_kind[component].status is not HealthStatus.ERROR:
                self.assertTrue(keys.issubset(by_kind[component].facts))
