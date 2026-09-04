"""Convierte el recurso maestro en PNG e ICO multirresolución."""

from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE = PROJECT_ROOT / "assets" / "app-icon-source.png"


def main() -> None:
    image = Image.open(SOURCE).convert("RGBA")
    alpha_box = image.getchannel("A").getbbox()
    if alpha_box:
        image = image.crop(alpha_box)
    side = max(image.size)
    padding = max(8, side // 18)
    canvas = Image.new("RGBA", (side + padding * 2, side + padding * 2), (0, 0, 0, 0))
    canvas.alpha_composite(
        image,
        ((canvas.width - image.width) // 2, (canvas.height - image.height) // 2),
    )
    icon = canvas.resize((256, 256), Image.Resampling.LANCZOS)
    icon.save(PROJECT_ROOT / "assets" / "app-icon.png")
    icon.save(
        PROJECT_ROOT / "assets" / "app-icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


if __name__ == "__main__":
    main()
