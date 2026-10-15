"""End-to-end pipeline test against a REAL photocraft-cli binary.

Skipped unless a binary is found (env EASYWALP_ENGINE, the engines folder, or
`scripts/fetch_engine.py` having run). Builds a synthetic mockup PSD *with
PhotoCraft itself*, maps a preset programmatically, runs the full pipeline and
checks the acceptance list:
  - exact 2K/4K wallpaper sizes,
  - preview at the PSD's own size in both modes,
  - the mockup code text unchanged by the resolution choice,
  - preset export/import + a second run on the imported preset.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from easywalp.photocraft import PhotoCraftBinary, Session
from easywalp.pipeline import Pipeline
from easywalp.presets import LayerRef, Preset, detect_code_span, export_preset, import_preset, split_code_text

CODE_TEXT = "Code:MD-O-C236"


def _find_binary() -> Path | None:
    env = os.getenv("EASYWALP_ENGINE")
    if env and Path(env).exists():
        return Path(env)
    try:
        return PhotoCraftBinary(None).path
    except Exception:
        return None


BINARY = _find_binary()

if BINARY is None:
    pytest.skip("no photocraft-cli binary found (set EASYWALP_ENGINE)", allow_module_level=True)


def _sample(w: int, h: int, top, bottom, label: str) -> Image.Image:
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        t = y / max(1, h - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = color
    d = ImageDraw.Draw(im)
    d.rectangle([0, h - 40, w, h], fill=(255, 255, 255))
    return im


def _build_template_psd(binary: PhotoCraftBinary, work: Path) -> Path:
    """A 2000x1500 mockup: two smart objects, a solid fill, a code text layer."""
    work.mkdir(parents=True, exist_ok=True)
    d_img = _sample(1600, 900, (36, 98, 158), (10, 22, 40), "DESKTOP")
    m_img = _sample(900, 1600, (158, 98, 36), (40, 18, 8), "MOBILE")
    d_img.save(work / "sample-desktop.png")
    m_img.save(work / "sample-mobile.png")
    with Session(binary, work_root=work) as s:
        s.start()
        s.call("doc.new", {"width": 2000, "height": 1500, "background": "#0b1524"})
        s.call("doc.place", {"path": "sample-desktop.png", "asSmartObject": True})
        s.call("doc.place", {"path": "sample-mobile.png", "asSmartObject": True})
        s.execute("layer.newFillLayer.solidColor", {"color": "#203040", "name": "BG Color"})
        s.execute("type.create", {"text": CODE_TEXT, "size": 72, "color": "#ffffff", "name": "Code label"})
        s.call("doc.save", {"path": "template.psd"})
    return work / "template.psd"


@pytest.fixture(scope="module")
def template_psd(tmp_path_factory):
    return _build_template_psd(PhotoCraftBinary(BINARY), tmp_path_factory.mktemp("engine") / "build")


def _layers_by_kind(binary_path, psd: Path) -> dict[str, list]:
    from easywalp import wizard as wiz

    info = wiz.inspect_psd(PhotoCraftBinary(binary_path), psd)
    out: dict[str, list] = {}
    for l in wiz.top_level_layers(info):
        out.setdefault(l.kind, []).append(l)
    return out


@pytest.fixture()
def mapped_preset(data_dir, template_psd):
    from easywalp import wizard as wiz

    binary = PhotoCraftBinary(BINARY)
    by_kind = _layers_by_kind(BINARY, template_psd)
    so = by_kind["Smart Object"]
    fill = by_kind["Fill"][0]
    text = by_kind["Type"][0]

    preset = Preset(id="engine-test", name="Engine test")
    preset.dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template_psd, preset.template_path)
    # doc.place stacks newest on top; desktop was placed first -> mobile is layer[0]? Keep it robust:
    def so_ref(cand):
        w, h, _f = wiz.smart_object_contents(binary, preset.template_path, LayerRef(id=cand.id, name=cand.name, kind="Smart Object"), preset.dir / "probe")
        return LayerRef(id=cand.id, name=cand.name, kind="Smart Object"), (w, h)

    cands = [(c, ) for c in so]
    sizes = {}
    refs = {}
    for cand in so:
        ref, (w, h) = so_ref(cand)
        sizes[cand.id] = (w, h)
        refs[cand.id] = ref
    landscape = [i for i, (w, h) in sizes.items() if w > h]
    portrait = [i for i, (w, h) in sizes.items() if h > w]
    assert landscape and portrait, f"expected one landscape and one portrait smart object, got {sizes}"
    preset.desktop_smart_object = refs[landscape[0]]
    preset.mobile_smart_object = refs[portrait[0]]
    preset.desktop_contents.width, preset.desktop_contents.height = sizes[landscape[0]]
    preset.mobile_contents.width, preset.mobile_contents.height = sizes[portrait[0]]
    preset.solid_color_fill = LayerRef(id=fill.id, name=fill.name, kind="Fill")
    preset.text_layer = LayerRef(id=text.id, name=text.name, kind="Type")
    tinfo = wiz.text_layer_info(binary, preset.template_path, preset.text_layer)
    full = str(tinfo.get("text", ""))
    span = detect_code_span(full)
    assert span, f"no code in text layer: {full!r}"
    preset.text_code = split_code_text(full, span)
    preset.save()
    return preset


def _run(preset, data_dir, sample_images, res_key):
    desktop, mobile = sample_images
    pipeline = Pipeline(PhotoCraftBinary(BINARY))
    return pipeline.generate(preset, desktop, mobile, "O", 236, data_dir / f"out-{res_key}",
                             options_override={"resolution_key": res_key})


def test_pipeline_2k_and_4k(data_dir, mapped_preset, sample_images):
    r2 = _run(mapped_preset, data_dir, sample_images, "2k")
    r4 = _run(mapped_preset, data_dir, sample_images, "4k")

    with Image.open(r2.desktop_jpg) as im:
        assert im.size == (2560, 1440)
    with Image.open(r2.mobile_jpg) as im:
        assert im.size == (1440, 2560)
    with Image.open(r4.desktop_jpg) as im:
        assert im.size == (4096, 2304)
    with Image.open(r4.mobile_jpg) as im:
        assert im.size == (2304, 4096)

    # both previews are the PSD's own size, identical pixels in both modes
    with Image.open(r2.preview_jpg) as a, Image.open(r4.preview_jpg) as b:
        assert a.size == b.size == (2000, 1500)
        from PIL import ImageChops

        diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox()
        assert diff is None, "2K and 4K previews must be pixel-identical"

    assert r2.code.code == "MD-O-C236" == r4.code.code


def test_suffix_option_changes_names_not_code(data_dir, mapped_preset, sample_images):
    mapped_preset.options.add_resolution_suffix = True
    mapped_preset.save()
    r = _run(mapped_preset, data_dir, sample_images, "4k")
    assert r.desktop_jpg.name == "D-O-C236-4K.jpg"
    assert r.mobile_jpg.name == "M-O-C236-4K.jpg"
    assert r.out_dir.name == "MD-O-C236-4K"
    with Image.open(r.preview_jpg) as im:
        assert im.size == (2000, 1500)


def test_preset_shares_between_data_dirs(data_dir, tmp_path, mapped_preset, sample_images):
    package = tmp_path / "share.easywalp"
    export_preset(mapped_preset, package)
    other = tmp_path / "colleague-data"
    other.mkdir()
    os.environ["EASYWALP_DATA_DIR"] = str(other)
    try:
        installed = import_preset(package, "0.0.0-test")
        r = _run(installed, other, sample_images, "2k")
        assert r.desktop_jpg.exists() and r.preview_jpg.exists()
        with Image.open(r.preview_jpg) as im:
            assert im.size == (2000, 1500)
    finally:
        os.environ["EASYWALP_DATA_DIR"] = str(data_dir)


def test_overwrite_prompt_data_present(data_dir, mapped_preset, sample_images):
    r1 = _run(mapped_preset, data_dir, sample_images, "2k")
    from easywalp.pipeline import check_overwrite

    assert check_overwrite(data_dir / "out-2k", r1.code) is not None
