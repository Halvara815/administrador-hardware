from unittest import TestCase

from hardware_admin.domain.models import ComponentKind
from hardware_admin.ui.main_window import NAV_ITEMS


class UiContractTests(TestCase):
    def test_navigation_contains_the_twelve_assignment_options(self) -> None:
        labels = [label for _, label, _ in NAV_ITEMS]
        components = [component for _, _, component in NAV_ITEMS if component is not None]

        self.assertEqual(len(labels), 12)
        self.assertEqual(set(components), set(ComponentKind))
        self.assertEqual(labels[0], "1. Información del sistema")
        self.assertEqual(labels[-1], "12. Generar reporte")
