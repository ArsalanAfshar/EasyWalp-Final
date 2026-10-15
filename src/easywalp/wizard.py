"""Setup-wizard machinery: inspect a PSD via PhotoCraft, map layers, probe smart
objects and text, and dry-run the pipeline on generated sample images.

All engine work goes through easywalp.photocraft (headless CLI); Pillow is used
only for reading exported thumbnails/contents sizes and making sample images.
"""
from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from . import presets as presets_mod
from .photocraft import PhotoCraftBinary, PhotoCraftError, Session
from .pipeline import _collect_warnings, _flatten_layers  # shared engine helpers
from .presets import LayerRef, Preset, detect_code_span, split_code_text

log = logging.getLogger("easywalp.wizard")


@dataclass
class LayerCandidate:
    """One top-level layer as shown in the wizard's mapping lists."""

    id: int
    name: str
    kind: str  # PhotoCraft kind_name(): Pixel/Group/Adjustment/Fill/Type/Shape/Smart Object
    visible: bool
    thumbnail: Path | None = None

    @property
    def label(self) -> str:
        vis = "" if self.visible else "  (hidden)"
        return f"[{self.kind}] {self.name}{vis}"


def inspect_psd(binary: PhotoCraftBinary, psd: Path) -> dict:
    """Open + inspect via `photocraft-cli info --compact` (font warnings included)."""
    from .photocraft import info as pc_info

    return pc_info(binary.path, psd)


def top_level_layers(doc: dict) -> list[LayerCandidate]:
    out: list[LayerCandidate] = []
    for item in doc.get("layers", []) or []:
        try:
            lid = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        out.append(
            LayerCandidate(
                id=lid,
                name=str(item.get("name", "")),
                kind=str(item.get("kind", "")),
                visible=bool(item.get("visible", True)),
            )
        )
    return out


def export_layer_thumbnails(binary: PhotoCraftBinary, psd: Path, dest_dir: Path) -> dict[int, Path]:
    """Render a small PNG per top-level layer with `doc.exportLayers` (serve).

    Returns layer id -> thumbnail path, matched by the `{index:04}` infix which
    PhotoCraft writes in the same top-to-bottom order as `doc.inspect`.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    with Session(binary, work_root=dest_dir) as session:
        session.start()
        session.open(psd)
        session.call("doc.exportLayers", {"dir": ".", "format": "png", "visibleOnly": False})
    files = sorted(dest_dir.glob("*.png"))
    pattern = re.compile(r"_(\d{4})_")
    by_index: dict[int, Path] = {}
    for f in files:
        m = pattern.search(f.name)
        if m:
            by_index[int(m.group(1))] = f
    doc = inspect_psd(binary, psd)
    layers = top_level_layers(doc)
    # PhotoCraft numbers files top-to-bottom (index 0 = top layer), skipping
    # adjustment layers - the same order as `top_level_layers` minus adjustments.
    result: dict[int, Path] = {}
    i = 0
    for layer in layers:
        if layer.kind == "Adjustment":
            continue
        thumb = by_index.get(i)
        if thumb is not None:
            result[layer.id] = thumb
        i += 1
    return result


def shrink_thumbnail(src: Path, dest: Path, max_side: int = 220) -> Path:
    im = Image.open(src)
    im.load()
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    im.convert("RGBA").save(dest, format="PNG")
    return dest


def smart_object_contents(
    binary: PhotoCraftBinary, psd: Path, layer_ref: LayerRef, work_dir: Path
) -> tuple[int, int, Path]:
    """Export a smart object's stored contents and return (width, height, file)."""
    work_dir.mkdir(parents=True, exist_ok=True)
    out = work_dir / f"so-{layer_ref.id}.png"
    with Session(binary, work_root=work_dir) as session:
        session.start()
        session.open(psd)
        layers = _flatten_layers(session.inspect())
        from .pipeline import _resolve_layer

        engine_id = _resolve_layer(layers, layer_ref, layer_ref.name, [])
        session.execute("layer.smartObjects.exportContents", {"layer": engine_id, "path": str(out.name)})
    if not out.exists():
        raise PhotoCraftError(f"could not export the contents of smart object '{layer_ref.name}'")
    with Image.open(out) as im:
        size = im.size
    return size[0], size[1], out


def text_layer_info(binary: PhotoCraftBinary, psd: Path, layer_ref: LayerRef) -> dict:
    """Current text + font family of the text layer: {"text", "font", "sizePt"}."""
    with Session(binary, work_root=psd.parent) as session:
        session.start()
        session.open(psd)
        layers = _flatten_layers(session.inspect())
        from .pipeline import _resolve_layer

        engine_id = _resolve_layer(layers, layer_ref, layer_ref.name, [])
        return session.execute("type.info", {"layer": engine_id}) or {}


def font_warnings_from(doc_info: dict) -> list[str]:
    """'font X is not installed' notices reported by `info` (missing-font behaviour)."""
    out = []
    for w in doc_info.get("warnings", []) or []:
        text = str(w)
        if "font" in text.lower():
            out.append(text)
    return out


def installed_font_families() -> set[str]:
    """Families visible to the OS (Windows registry first, then font dirs)."""
    fams: set[str] = set()
    try:
        if sys_platform() == "win32":
            import winreg

            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    key = winreg.OpenKey(root, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts")
                    i = 0
                    while True:
                        try:
                            name, _val, _typ = winreg.EnumValue(key, i)
                        except OSError:
                            break
                        fams.add(_family_from_font_entry(str(name)))
                        i += 1
                except OSError:
                    continue
        else:
            for d in (Path("/usr/share/fonts"), Path.home() / ".local/share/fonts", Path.home() / ".fonts"):
                if d.exists():
                    fams.add("*")  # presence-only heuristic on non-Windows dev machines
    except Exception as e:  # pragma: no cover - defensive
        log.debug("font enumeration failed: %s", e)
    return fams


def _family_from_font_entry(entry: str) -> str:
    """'Vazirmatn Bold (TrueType)' -> 'Vazirmatn'."""
    name = entry.split(" (")[0]
    for style in (
        " Bold", " Light", " Medium", " SemiBold", " ExtraBold", " Black", " Thin",
        " Regular", " Italic", " Oblique", " Heavy", " Condensed",
    ):
        if name.endswith(style):
            name = name[: -len(style)]
    return name.strip()


def sys_platform() -> str:
    import sys

    return sys.platform


# ------------------------------------------------------------------ dry run
def make_sample_images(dest_dir: Path, desktop_wh: tuple[int, int], mobile_wh: tuple[int, int]) -> tuple[Path, Path]:
    """Deterministic gradient sample wallpapers for the wizard's test render."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    d_path = dest_dir / "sample-desktop.png"
    m_path = dest_dir / "sample-mobile.png"
    _gradient(d_path, *desktop_wh, top=(38, 98, 157), bottom=(12, 24, 44), marker="DESKTOP")
    _gradient(m_path, *mobile_wh, top=(157, 98, 38), bottom=(44, 20, 12), marker="MOBILE")
    return d_path, m_path


def _gradient(path: Path, w: int, h: int, top: tuple, bottom: tuple, marker: str) -> None:
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    draw = ImageDraw.Draw(im)
    bar = max(8, h // 90)
    draw.rectangle([0, h - bar * 3, w, h - bar * 2], fill=(255, 255, 255))
    im.save(path, format="PNG")


def dry_run(
    binary: PhotoCraftBinary,
    preset: Preset,
    out_dir: Path,
    sample_desktop: Path | None = None,
    sample_mobile: Path | None = None,
) -> tuple[Path, list[str]]:
    """Render one preview with sample images through the real pipeline.

    Uses the preset's smart-object contents sizes so the test matches 2K/4K runs.
    Returns (preview_jpg_path, warnings)."""
    from .pipeline import Pipeline  # local import avoids a cycle at module load

    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "dryrun"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    d_size = (preset.desktop_contents.width or 2560, preset.desktop_contents.height or 1440)
    m_size = (preset.mobile_contents.width or 1440, preset.mobile_contents.height or 2560)
    d_path = sample_desktop or make_sample_images(work, d_size, m_size)[0]
    m_path = sample_mobile or make_sample_images(work, d_size, m_size)[1]
    pipeline = Pipeline(binary)
    result = pipeline.generate(
        preset,
        d_path,
        m_path,
        category="O",
        number=236,
        out_base=work,
        progress=lambda stage, frac: None,
    )
    return result.preview_jpg, result.warnings


__all__ = [
    "LayerCandidate",
    "inspect_psd",
    "top_level_layers",
    "export_layer_thumbnails",
    "shrink_thumbnail",
    "smart_object_contents",
    "text_layer_info",
    "font_warnings_from",
    "installed_font_families",
    "make_sample_images",
    "dry_run",
    "detect_code_span",
    "split_code_text",
    "PhotoCraftError",
    "presets_mod",
]
