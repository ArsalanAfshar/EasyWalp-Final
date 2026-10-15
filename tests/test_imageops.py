"""Resize rules: cover-crop (never stretch/letterbox), JPEG 4:4:4, average color."""
from __future__ import annotations

from PIL import Image, JpegImagePlugin

from easywalp.pipeline import average_color, cover_resize, save_wallpaper_jpg


def test_cover_resize_landscape_to_landscape():
    im = Image.new("RGB", (1920, 1080), (255, 0, 0))
    out = cover_resize(im, 2560, 1440)
    assert out.size == (2560, 1440)  # exact target, no stretch (same aspect)


def test_cover_resize_crops_never_distorts():
    # a wide 4:1 image into a 16:9 frame must crop sides, not squeeze
    im = Image.new("RGB", (400, 100), (0, 255, 0))
    out = cover_resize(im, 160, 90)
    assert out.size == (160, 90)
    # center column keeps its color; a squeezed image would too, so check the
    # geometry instead: 4:1 -> 16:9 crop keeps full height, crops width heavily
    # (scale = max(160/400, 90/100) = 0.9 -> 360x90 -> crop to 160).
    assert out.getpixel((80, 45)) == (0, 255, 0)


def test_cover_resize_tall_to_wide_crops_top_bottom():
    im = Image.new("RGB", (100, 1000), (0, 0, 255))
    out = cover_resize(im, 160, 90)
    assert out.size == (160, 90)
    assert out.getpixel((80, 45)) == (0, 0, 255)


def test_upscale_still_exact():
    im = Image.new("RGB", (100, 60), (9, 9, 9))
    out = cover_resize(im, 2560, 1440)
    assert out.size == (2560, 1440)


def test_jpeg_quality_and_subsampling(tmp_path):
    im = Image.new("RGB", (320, 180), (128, 60, 30))
    dest = tmp_path / "w.jpg"
    save_wallpaper_jpg(im, dest)
    with Image.open(dest) as check:
        assert check.format == "JPEG"
        assert check.size == (320, 180)
        sampling = JpegImagePlugin.get_sampling(check)
        assert sampling == 0, "4:4:4 (subsampling 0) required"


def test_average_color_matches_solid(tmp_path):
    dest = tmp_path / "solid.png"
    Image.new("RGB", (500, 500), (10, 58, 79)).save(dest)
    assert average_color(dest) == "#0a3a4f"


def test_average_color_mixed(tmp_path):
    from PIL import ImageDraw

    dest = tmp_path / "mix.png"
    im = Image.new("RGB", (300, 300))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 149, 299], fill=(200, 100, 50))
    d.rectangle([150, 0, 299, 299], fill=(100, 50, 25))
    im.save(dest)
    r, g, b = (int(average_color(dest)[i:i + 2], 16) for i in (1, 3, 5))
    assert abs(r - 150) <= 1 and abs(g - 75) <= 1 and abs(b - 38) <= 2
