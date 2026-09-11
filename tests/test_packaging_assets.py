"""Regresion de empaquetado: los recursos graficos deben poder abrirse.

Un usuario abrio el ejecutable y recibio FileNotFoundError desde PIL.Image.open
al construir la cabecera, buscando un recurso bajo `_internal/assets`. El smoke
test no lo detecto porque nadie comprobaba los recursos de forma explicita.
"""

from pathlib import Path
from unittest import TestCase

from hardware_admin.resources import REQUIRED_UI_ASSETS, resource_path, verify_ui_assets


class RequiredAssetsTests(TestCase):
    def test_the_ui_declares_the_assets_it_opens(self) -> None:
        """Lo que la interfaz abre y lo que se declara deben coincidir.

        Si alguien anade un Image.open nuevo sin declararlo aqui, el
        empaquetado puede olvidarlo y el fallo solo aparece en manos del
        usuario.
        """
        fuente = Path("src/hardware_admin/ui/main_window.py").read_text(encoding="utf-8")
        declarados = {parts[-1] for parts in REQUIRED_UI_ASSETS}

        for nombre in declarados:
            self.assertIn(nombre, fuente, f"{nombre} se declara pero la UI no lo usa")

    def test_every_required_asset_opens_as_a_valid_image(self) -> None:
        """No basta con que exista: debe poder abrirse y validarse."""
        self.assertEqual(verify_ui_assets(), [])

    def test_a_missing_asset_is_reported_instead_of_raising(self) -> None:
        """El informe debe describir el problema, no reventar al comprobarlo."""
        from hardware_admin import resources

        original = resources.REQUIRED_UI_ASSETS
        resources.REQUIRED_UI_ASSETS = (("assets", "no-existe.png"),)
        try:
            problemas = verify_ui_assets()
        finally:
            resources.REQUIRED_UI_ASSETS = original

        self.assertEqual(len(problemas), 1)
        self.assertIn("no existe", problemas[0])

    def test_a_corrupt_asset_is_detected_not_just_its_presence(self) -> None:
        """Un archivo truncado existe y aun asi revienta al abrirlo."""
        import tempfile

        from hardware_admin import resources

        with tempfile.TemporaryDirectory() as carpeta:
            roto = Path(carpeta) / "roto.png"
            roto.write_bytes(b"esto no es un PNG")
            original_assets = resources.REQUIRED_UI_ASSETS
            original_path = resources.resource_path
            resources.REQUIRED_UI_ASSETS = (("roto.png",),)
            resources.resource_path = lambda *parts: roto  # type: ignore[assignment]
            try:
                problemas = resources.verify_ui_assets()
            finally:
                resources.REQUIRED_UI_ASSETS = original_assets
                resources.resource_path = original_path  # type: ignore[assignment]

        self.assertEqual(len(problemas), 1)
        self.assertIn("no se pudo abrir", problemas[0])

    def test_resource_path_points_inside_the_bundle_when_frozen(self) -> None:
        """Empaquetado, los recursos viven en _MEIPASS; en desarrollo, en el repo."""
        import sys

        original = getattr(sys, "_MEIPASS", None)
        sys._MEIPASS = r"C:\bundle"  # type: ignore[attr-defined]
        try:
            ruta = resource_path("assets", "app-icon.png")
        finally:
            if original is None:
                del sys._MEIPASS  # type: ignore[attr-defined]
            else:
                sys._MEIPASS = original  # type: ignore[attr-defined]

        self.assertEqual(ruta, Path(r"C:\bundle") / "assets" / "app-icon.png")
