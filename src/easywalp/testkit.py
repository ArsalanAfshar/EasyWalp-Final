"""Synthetic test material: sample wallpapers and a mockup PSD built *by the engine*.

Shared by ``scripts/spike/make_test_psd.py`` (desktop spike/CI) and the Android
self-test, so both validate the pipeline against exactly the same fixture. The PSD
is created with PhotoCraft's own commands (``doc.new`` / ``doc.place`` /
``layer.newFillLayer.solidColor`` / ``type.create``), which is why it needs a real
engine binary: no private PSD and no extra PSD-writing dependency is involved.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .photocraft import PhotoCraftBinary, Session

CANVAS = (2000, 1500)
CODE_TEXT = "Code:MD-O-C236"


def gradient(width: int, height: int, top: tuple, bottom: tuple, label: str) -> Image.Image:
    """A vertical gradient with a white bar and a text label (deterministic fixture)."""
    im = Image.new("RGB", (width, height))
    px = im.load()
    for y in range(height):
        t = y / max(1, height - 1)
        px_row = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(width):
            px[x, y] = px_row
    draw = ImageDraw.Draw(im)
    bar = max(8, height // 25)
    draw.rectangle([0, height - bar, width, height], fill=(255, 255, 255))
    draw.text((18, height - bar + 6), label, fill=(0, 0, 0))
    return im


def sample_wallpapers(dest_dir: Path, *, desktop: tuple[int, int] = (1600, 900),
                      mobile: tuple[int, int] = (900, 1600)) -> tuple[Path, Path]:
    """16:9 and 9:16 sample wallpapers (desktop first, mobile second)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    d_path = dest_dir / "sample-desktop.png"
    m_path = dest_dir / "sample-mobile.png"
    gradient(*desktop, (36, 98, 158), (10, 22, 40), "DESKTOP").save(d_path)
    gradient(*mobile, (158, 98, 36), (40, 18, 8), "MOBILE").save(m_path)
    return d_path, m_path


def build_template_psd(
    binary: PhotoCraftBinary,
    dest_dir: Path,
    *,
    canvas: tuple[int, int] = CANVAS,
    code_text: str = CODE_TEXT,
    background: str = "#0b1524",
) -> Path:
    """Create ``template.psd``: two smart objects, a solid fill and the code text.

    Layout: desktop 16:9 smart object, mobile 9:16 smart object, a Solid Color fill
    layer and a Type layer reading ``Code:MD-O-C236`` - i.e. every feature the real
    presets map, so a successful run here means a real PSD will work too.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    desktop_png, mobile_png = sample_wallpapers(dest_dir)
    with Session(binary, work_root=dest_dir) as session:
        session.start()
        session.call("doc.new", {"width": canvas[0], "height": canvas[1], "background": background})
        session.call("doc.place", {"path": desktop_png.name, "asSmartObject": True})
        session.call("doc.place", {"path": mobile_png.name, "asSmartObject": True})
        session.execute("layer.newFillLayer.solidColor", {"color": "#203040", "name": "BG Color"})
        session.execute(
            "type.create",
            {"text": code_text, "size": 72, "color": "#ffffff", "name": "Code label"},
        )
        session.call("doc.save", {"path": "template.psd"})
    return dest_dir / "template.psd"
