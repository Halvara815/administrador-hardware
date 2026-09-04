from unittest import TestCase

from hardware_admin.domain.models import ComponentKind
from hardware_admin.ui import icons
from hardware_admin.ui.main_window import ICON_NAMES, NAV_ITEMS, SECTION_NAMES


class IconTests(TestCase):
    def test_every_navigation_entry_has_a_drawable_icon(self) -> None:
        available = set(icons.available_icons())

        missing = [name for name, _, _ in NAV_ITEMS if name not in available]

        self.assertEqual(missing, [])

    def test_every_component_has_a_short_section_name(self) -> None:
        self.assertEqual(set(SECTION_NAMES), set(ComponentKind))
        self.assertEqual(set(ICON_NAMES), set(ComponentKind))

    def test_render_returns_a_transparent_square_of_the_requested_size(self) -> None:
        image = icons.render("cpu", 24, "#4A9EFF")

        self.assertEqual(image.size, (24, 24))
        self.assertEqual(image.mode, "RGBA")
        self.assertGreater(image.getchannel("A").getextrema()[1], 0)

    def test_an_unknown_icon_is_reported_instead_of_drawn_blank(self) -> None:
        with self.assertRaises(KeyError):
            icons.render("no-existe", 16, "#FFFFFF")
