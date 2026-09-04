from unittest import TestCase

from hardware_admin.collectors.core import build_default_collectors, format_bytes
from hardware_admin.domain.models import ComponentKind


class CollectorCompositionTests(TestCase):
    def test_all_diagnostic_areas_are_composed_once(self) -> None:
        components = [collector.component for collector in build_default_collectors()]

        self.assertEqual(len(components), 11)
        self.assertEqual(set(components), set(ComponentKind))

    def test_byte_formatter_uses_human_readable_units(self) -> None:
        self.assertEqual(format_bytes(1024), "1.0 KB")
        self.assertEqual(format_bytes(None), "No disponible")
