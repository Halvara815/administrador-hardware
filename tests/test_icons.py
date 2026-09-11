from unittest import TestCase

from hardware_admin.domain.models import ComponentKind
from hardware_admin.ui import icons
from hardware_admin.ui.main_window import ICON_NAMES, NAV_ITEMS, SECTION_NAMES


class IconTests(TestCase):
    def test_every_navigation_entry_has_a_drawable_icon(self) -> None:
        available = set(icons.available_icons())

        missing = [entry.icon for entry in NAV_ITEMS if entry.icon not in available]

        self.assertEqual(missing, [])

    def test_every_component_has_a_short_section_name(self) -> None:
        self.assertEqual(set(SECTION_NAMES), set(ComponentKind))
        self.assertEqual(set(ICON_NAMES), set(ComponentKind))

    def test_the_icons_used_outside_the_menu_are_drawable(self) -> None:
        extras = {"check", "collapse", "copy", "expand", "info", "lock", "refresh", "save"}

        self.assertLessEqual(extras, set(icons.available_icons()))

    def test_render_returns_a_transparent_square_of_the_requested_size(self) -> None:
        image = icons.render("cpu", 24, "#4A9EFF")

        self.assertEqual(image.size, (24, 24))
        self.assertEqual(image.mode, "RGBA")
        self.assertGreater(image.getchannel("A").getextrema()[1], 0)

    def test_an_unknown_icon_is_reported_instead_of_drawn_blank(self) -> None:
        with self.assertRaises(KeyError):
            icons.render("no-existe", 16, "#FFFFFF")

    def test_painters_mapping_contract(self) -> None:
        self.assertIs(icons._PAINTERS["pci"], icons._paint_pci)
        self.assertIs(icons._PAINTERS["card"], icons._paint_note)
        self.assertIsNot(icons._PAINTERS["pci"], icons._PAINTERS["card"])
