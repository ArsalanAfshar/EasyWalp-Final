"""The EasyWalp generation pipeline (GUI-free core).

Steps per run (spec §4):
  1. resize desktop/mobile wallpapers to the target resolution (cover-crop, Lanczos,
     JPG q95 4:4:4 sRGB) - Pillow is used ONLY for this, thumbnails and average color;
  2. average color from the configured source wallpaper;
  3. edit a temp clone of the preset PSD through the PhotoCraft engine:
     replace both smart objects' contents, set the solid fill color, ranged-replace the
     code inside the text layer - then PhotoCraft flattens/exports the preview JPG;
  4. move the preview into the output folder. Nothing else in the PSD is touched.

All PhotoCraft file access stays inside a per-run temp folder (the automation
read/write roots); finished files are moved out by EasyWalp.
"""
from __future__ import annotations

import dataclasses
import logging
import re
import shutil
import time
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageCms

from . import paths, presets as presets_mod
from .config import RESOLUTIONS, GenerateOptions, Resolution, AVG_COLOR_SAMPLE_SIZE
from .photocraft import PhotoCraftBinary, PhotoCraftError, Session
from .presets import LayerRef, Preset

log = logging.getLogger("easywalp.pipeline")

# Progress stages (i18n keys for the GUI; CLI prints them raw).
STAGES = ("prepare", "resizing", "color", "editing", "rendering", "done")

# Name-safe sanitizing for template outputs (defensive; templates are user-editable).
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Aspect tolerance before we refuse to distort a smart object's contents (0.5%).
ASPECT_TOLERANCE = 0.005

_SRGB_PROFILE_BYTES: bytes | None = None


def srgb_profile_bytes() -> bytes:
    """A minimal sRGB ICC profile embedded into exported wallpapers."""
    global _SRGB_PROFILE_BYTES
    if _SRGB_PROFILE_BYTES is None:
        _SRGB_PROFILE_BYTES = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    return _SRGB_PROFILE_BYTES


# --------------------------------------------------------------------- naming
def format_number(number: int) -> str:
    """236 -> '236'; 45 -> '045'; 1234 -> '1234' (above 999 prints as-is)."""
    if number > 999:
        return str(number)
    return f"{number:03d}"


def build_code(code_template: str, *, category: str, number: int) -> str:
    """The full code from its template, e.g. 'MD-{cat}-C{num}' -> 'MD-O-C236'."""
    value = code_template.replace("{CAT}", category.upper()).replace("{cat}", category.lower())
    value = value.replace("{num}", format_number(number)).replace("{code}", "")
    return _UNSAFE.sub("_", value).strip()


def fill_template(template: str, *, category: str, number: int, resolution: Resolution | None = None,
                  code: str | None = None) -> str:
    value = template
    value = value.replace("{code}", code if code is not None else "")
    value = value.replace("{CAT}", category.upper())
    value = value.replace("{cat}", category.lower())
    value = value.replace("{num}", format_number(number))
    if resolution is None:
        # No suffix requested: drop dangling separators around {res} too.
        for sep in ("-{res}", "_{res}", " {res}", "+{res}", ".{res}"):
            value = value.replace(sep, "")
        value = value.replace("{res}", "")
    else:
        value = value.replace("{res}", resolution.suffix)
    return _UNSAFE.sub("_", value).strip()


@dataclasses.dataclass
class CodeInfo:
    """Everything the current run will produce, name-wise."""

    code: str
    folder_name: str
    desktop_file: str
    mobile_file: str
    preview_file: str
    desktop_target: tuple[int, int]
    mobile_target: tuple[int, int]
    resolution_key: str

    @property
    def desktop_stem(self) -> str:
        return Path(self.desktop_file).stem

    @property
    def mobile_stem(self) -> str:
        return Path(self.mobile_file).stem


def plan_names(options: GenerateOptions, category: str, number: int, resolution_key: str) -> CodeInfo:
    """Compute code + all file/folder names for a run (no IO)."""
    if not category:
        raise PipelineError("category must be 'O' or 'A'")
    if number < 0:
        raise PipelineError("the wallpaper number cannot be negative")
    resolution = RESOLUTIONS.get(resolution_key)
    if resolution is None:
        raise PipelineError(f"unknown resolution '{resolution_key}' (known: {', '.join(RESOLUTIONS)})")
    opts = options
    code = build_code(opts.templates.code, category=category, number=number)
    folder = fill_template(opts.templates.folder, category=category, number=number, code=code)
    suffix_res = resolution if opts.add_resolution_suffix else None
    desktop = fill_template(opts.templates.desktop, category=category, number=number, resolution=suffix_res, code=code)
    mobile = fill_template(opts.templates.mobile, category=category, number=number, resolution=suffix_res, code=code)
    preview = fill_template(opts.templates.preview, category=category, number=number, resolution=suffix_res, code=code)

    if opts.add_resolution_suffix:
        if "{res}" not in opts.templates.folder:
            folder = f"{folder}-{resolution.suffix}"

    def add_res_before_ext(filename: str, template: str) -> str:
        if "{res}" in template:
            return filename
        stem, dot, ext = filename.rpartition(".")
        return f"{stem}-{resolution.suffix}.{ext}" if dot else f"{filename}-{resolution.suffix}"

    if opts.add_resolution_suffix:
        desktop = add_res_before_ext(desktop, opts.templates.desktop)
        mobile = add_res_before_ext(mobile, opts.templates.mobile)
        preview = add_res_before_ext(preview, opts.templates.preview)

    if not desktop.lower().endswith(".jpg"):
        desktop += ".jpg"
    if not mobile.lower().endswith(".jpg"):
        mobile += ".jpg"
    if not preview.lower().endswith(".jpg"):
        preview += ".jpg"
    return CodeInfo(
        code=code,
        folder_name=folder,
        desktop_file=desktop,
        mobile_file=mobile,
        preview_file=preview,
        desktop_target=resolution.desktop,
        mobile_target=resolution.mobile,
        resolution_key=resolution.key,
    )


def output_folder(out_base: Path, info: CodeInfo) -> Path:
    return Path(out_base) / info.folder_name


def check_overwrite(out_base: Path, info: CodeInfo) -> Path | None:
    """The folder that already exists and would be overwritten, or None."""
    target = output_folder(out_base, info)
    return target if target.exists() else None


# ------------------------------------------------------------------- resizing
def cover_resize(im: Image.Image, width: int, height: int) -> Image.Image:
    """Scale to fill (width, height) and center-crop. Never stretches or letterboxes."""
    src_w, src_h = im.size
    scale = max(width / src_w, height / src_h)
    new_w = max(1, round(src_w * scale))
    new_h = max(1, round(src_h * scale))
    resized = im.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    return resized.crop((left, top, left + width, top + height))


def save_wallpaper_jpg(im: Image.Image, dest: Path) -> None:
    """JPG quality 95, 4:4:4 (subsampling=0), sRGB."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.convert("RGB").save(
        dest,
        format="JPEG",
        quality=95,
        subsampling=0,
        optimize=True,
        icc_profile=srgb_profile_bytes(),
    )


def resize_wallpaper(src: Path, dest: Path, target: tuple[int, int]) -> Image.Image:
    im = Image.open(src)
    im.load()
    im = cover_resize(im, target[0], target[1])
    save_wallpaper_jpg(im, dest)
    return im


def average_color(src: Path, sample_size: int = AVG_COLOR_SAMPLE_SIZE) -> str:
    """Mean RGB in sRGB of a ~256px downscale, as '#rrggbb'."""
    im = Image.open(src)
    im.load()
    im = im.convert("RGB")
    im.thumbnail((sample_size, sample_size), Image.LANCZOS)
    # Mean over all pixels: downsize to 1x1 with a box-ish filter chain for accuracy.
    small = im.resize((1, 1), Image.BOX if hasattr(Image, "BOX") else Image.LANCZOS)
    r, g, b = small.getpixel((0, 0))[:3]
    return f"#{r:02x}{g:02x}{b:02x}"


# ----------------------------------------------------------------- validation
def validate_sources(desktop_src: Path, mobile_src: Path, info: CodeInfo) -> list[str]:
    """Warnings (not blockers): orientation swaps and upscaling."""
    warnings: list[str] = []
    try:
        dw, dh = Image.open(desktop_src).size
    except Exception as e:  # PIL raises several types
        raise PipelineError(f"cannot read the desktop image: {e}") from e
    try:
        mw, mh = Image.open(mobile_src).size
    except Exception as e:
        raise PipelineError(f"cannot read the mobile image: {e}") from e
    if dh > dw:
        warnings.append("the desktop image is portrait; a desktop wallpaper should be landscape (16:9)")
    if mw > mh:
        warnings.append("the mobile image is landscape; a mobile wallpaper should be portrait (9:16)")
    tw, th = info.desktop_target
    if dw < tw or dh < th:
        warnings.append(
            f"the desktop image ({dw}x{dh}) is smaller than the target {tw}x{th} and will be upscaled"
        )
    tw, th = info.mobile_target
    if mw < tw or mh < th:
        warnings.append(
            f"the mobile image ({mw}x{mh}) is smaller than the target {tw}x{th} and will be upscaled"
        )
    return warnings


# ------------------------------------------------------------------- pipeline
class PipelineError(RuntimeError):
    """A readable, user-actionable pipeline failure."""


ProgressFn = Callable[[str, float], None]


@dataclasses.dataclass
class GenerateResult:
    code: CodeInfo
    out_dir: Path
    desktop_jpg: Path
    mobile_jpg: Path
    preview_jpg: Path
    average_color: str
    warnings: list[str]
    timings: dict[str, float]


class Pipeline:
    """Runs the full generation for one release folder."""

    def __init__(self, binary: PhotoCraftBinary) -> None:
        self.binary = binary

    # ---------------------------------------------------------------- public
    def generate(
        self,
        preset: Preset,
        desktop_src: Path,
        mobile_src: Path,
        category: str,
        number: int,
        out_base: Path,
        progress: ProgressFn | None = None,
        options_override: dict | None = None,
    ) -> GenerateResult:
        t_start = time.monotonic()
        report = progress or (lambda stage, frac: None)
        timings: dict[str, float] = {}
        warnings: list[str] = []

        opts = dataclasses.replace(preset.options)
        if options_override:
            for key, value in options_override.items():
                if hasattr(opts, key) and value is not None:
                    setattr(opts, key, value)

        info = plan_names(opts, category, number, opts.resolution_key)
        out_dir = output_folder(Path(out_base), info)
        report("prepare", 0.02)

        warnings += validate_sources(desktop_src, mobile_src, info)

        # 1. Resize ---------------------------------------------------------
        t0 = time.monotonic()
        run_tmp = paths.temp_dir() / f"run-{int(time.time() * 1000)}"
        (run_tmp).mkdir(parents=True, exist_ok=True)
        desktop_jpg = run_tmp / f"{info.desktop_stem}.jpg"
        mobile_jpg = run_tmp / f"{info.mobile_stem}.jpg"
        resize_wallpaper(Path(desktop_src), desktop_jpg, info.desktop_target)
        report("resizing", 0.15)
        resize_wallpaper(Path(mobile_src), mobile_jpg, info.mobile_target)
        report("resizing", 0.3)
        timings["resize"] = time.monotonic() - t0

        # 2. Average color ---------------------------------------------------
        t0 = time.monotonic()
        if opts.color_source == "manual" and opts.manual_color:
            color = _normalize_hex(opts.manual_color)
        else:
            source = desktop_jpg if opts.color_source != "mobile" else mobile_jpg
            color = average_color(source)
        report("color", 0.4)
        timings["color"] = time.monotonic() - t0
        log.info("average color: %s (source=%s)", color, opts.color_source)

        # 3. PhotoCraft edit + render ---------------------------------------
        t0 = time.monotonic()
        work_dir = run_tmp / "engine"
        work_dir.mkdir()
        psd_clone = work_dir / "template.psd"
        preset.clone_template_to(psd_clone)
        report("editing", 0.45)
        preview_tmp = work_dir / "preview.jpg"
        self._engine_pass(preset, psd_clone, desktop_jpg, mobile_jpg, color, info, preview_tmp, report, warnings)
        timings["photocraft"] = time.monotonic() - t0

        # 4. Publish ----------------------------------------------------------
        t0 = time.monotonic()
        out_dir.mkdir(parents=True, exist_ok=True)
        final_desktop = out_dir / info.desktop_file
        final_mobile = out_dir / info.mobile_file
        final_preview = out_dir / info.preview_file
        shutil.move(str(desktop_jpg), final_desktop)
        shutil.move(str(mobile_jpg), final_mobile)
        shutil.move(str(preview_tmp), final_preview)
        timings["publish"] = time.monotonic() - t0
        timings["total"] = time.monotonic() - t_start
        report("done", 1.0)

        _cleanup(run_tmp)
        return GenerateResult(
            code=info,
            out_dir=out_dir,
            desktop_jpg=final_desktop,
            mobile_jpg=final_mobile,
            preview_jpg=final_preview,
            average_color=color,
            warnings=warnings,
            timings=timings,
        )

    # --------------------------------------------------------------- engine
    def _engine_pass(
        self,
        preset: Preset,
        psd_clone: Path,
        desktop_jpg: Path,
        mobile_jpg: Path,
        color: str,
        info: CodeInfo,
        preview_out: Path,
        report: ProgressFn,
        warnings: list[str],
    ) -> None:
        work_dir = psd_clone.parent
        with Session(self.binary, work_root=work_dir) as session:
            session.start()
            opened = session.open(psd_clone)
            _collect_warnings(opened, warnings)
            doc = session.inspect()
            width, height = int(doc.get("width", 0)), int(doc.get("height", 0))
            if not width or not height:
                raise PipelineError("PhotoCraft could not read the PSD canvas size")

            layers = _flatten_layers(doc)
            desktop_ref = _require_ref(preset.desktop_smart_object, "desktop Smart Object")
            mobile_ref = _require_ref(preset.mobile_smart_object, "mobile Smart Object")
            fill_ref = _require_ref(preset.solid_color_fill, "solid color fill")
            text_ref = _require_ref(preset.text_layer, "text")

            desktop_id = _resolve_layer(layers, desktop_ref, "desktop Smart Object", warnings)
            mobile_id = _resolve_layer(layers, mobile_ref, "mobile Smart Object", warnings)
            fill_id = _resolve_layer(layers, fill_ref, "solid color fill", warnings)
            text_id = _resolve_layer(layers, text_ref, "text", warnings)

            # Replacement files must match each smart object's stored contents size,
            # so the mockup layout is identical for 2K and 4K runs.
            for ref, contents, jpg, label in (
                (desktop_ref, preset.desktop_contents, desktop_jpg, "desktop"),
                (mobile_ref, preset.mobile_contents, mobile_jpg, "mobile"),
            ):
                if contents.width <= 0 or contents.height <= 0:
                    raise PipelineError(
                        f"the preset does not record the {label} smart object's contents size; "
                        "recreate the preset"
                    )
                with Image.open(jpg) as im:
                    src_w, src_h = im.size
                target_aspect = contents.width / contents.height
                src_aspect = src_w / src_h
                if abs(src_aspect - target_aspect) / target_aspect > ASPECT_TOLERANCE:
                    raise PipelineError(
                        f"the {label} wallpaper aspect ({src_w}x{src_h}) does not match the "
                        f"{label} smart object's contents ({contents.width}x{contents.height}); "
                        "refusing to distort - check the preset mapping"
                    )
                replacement = _scaled_copy(jpg, contents.width, contents.height, work_dir / f"{label}-so.jpg")
                result = session.execute(
                    "layer.smartObjects.replaceContents",
                    {"layer": _engine_layer_id(ref.id), "path": str(replacement)},
                )
                _collect_warnings(result, warnings)
            report("editing", 0.6)

            result = session.execute("layer.fill.solidColor.set", {"layer": fill_id, "color": color})
            _collect_warnings(result, warnings)
            report("editing", 0.7)

            text_info = session.execute("type.info", {"layer": text_id})
            current_text = str((text_info or {}).get("text", ""))
            new_start, new_end, code_text = _text_replace_span(preset, current_text, info.code)
            if new_end > new_start or code_text:
                result = session.execute(
                    "type.edit",
                    {"layer": text_id, "replace": {"start": new_start, "end": new_end, "text": code_text}},
                )
                _collect_warnings(result, warnings)
            report("rendering", 0.85)

            saved = session.save(preview_out, quality=max(95, preset.options.jpeg_quality))
            _collect_warnings(saved, warnings)
            if not preview_out.exists():
                raise PipelineError("PhotoCraft did not write the preview file")
            with Image.open(preview_out) as im:
                got = im.size
            if (got[0], got[1]) not in {(width, height), (height, width)}:
                warnings.append(
                    f"the preview size {got[0]}x{got[1]} differs from the PSD canvas {width}x{height}"
                )


# ------------------------------------------------------------------- helpers
def _engine_layer_id(stored: int) -> int:
    """Stored ids are already numeric PhotoCraft layer ids."""
    return int(stored)


def _require_ref(ref: LayerRef | None, label: str) -> LayerRef:
    if ref is None:
        raise PipelineError(f"the preset has no {label} mapping; recreate the preset")
    return ref


def _flatten_layers(doc: dict) -> dict[int, dict]:
    """Map layer id -> {name, kind} for every layer, groups included (recursive)."""
    out: dict[int, dict] = {}

    def walk(items: list) -> None:
        for item in items:
            try:
                lid = int(item.get("id"))
            except (TypeError, ValueError):
                continue
            out[lid] = {"name": str(item.get("name", "")), "kind": str(item.get("kind", ""))}
            children = item.get("layers")
            if isinstance(children, list):
                walk(children)

    walk(doc.get("layers", []) or [])
    return out


def _resolve_layer(layers: dict[int, dict], ref: LayerRef, label: str, warnings: list[str]) -> int:
    """Re-validate the stored mapping against the freshly inspected document.

    1. the stored id must exist and match name+kind;
    2. otherwise a layer with the same name AND kind is used (ids shifted after a
       PSD re-save) with a warning;
    3. otherwise it is a hard error.
    """
    hit = layers.get(int(ref.id))
    if hit and hit["name"] == ref.name and hit["kind"] == ref.kind:
        return int(ref.id)
    for lid, meta in layers.items():
        if meta["name"] == ref.name and meta["kind"] == ref.kind:
            warnings.append(
                f"the {label} layer '{ref.name}' moved from id {ref.id} to {lid}; using the name/kind match"
            )
            return lid
    raise PipelineError(
        f"the {label} layer '{ref.name}' ({ref.kind}, id {ref.id}) was not found in the PSD; "
        "the template may have changed - recreate or re-map the preset"
    )


def _text_replace_span(preset: Preset, current_text: str, new_code: str) -> tuple[int, int, str]:
    """Where the code sits in the CURRENT text; ranged replace only, never replace-all."""
    tc = preset.text_code
    expected = tc.prefix + _stored_code(tc) + tc.suffix
    if current_text == expected:
        start = len(tc.prefix)
        end = len(current_text) - len(tc.suffix)
        return start, end, new_code
    # The PSD text drifted from the stored sample: try the detected code pattern.
    span = presets_mod.detect_code_span(current_text)
    if span is not None:
        warnings = (
            f"the text layer text changed since the preset was made; replacing the detected code "
            f"at characters {span[0]}..{span[1]}"
        )
        log.warning(warnings)
        return span[0], span[1], new_code
    raise PipelineError(
        "the text layer no longer matches the preset's stored text pattern "
        f"(stored sample: '{tc.sample}', current: '{current_text}'); re-map the preset"
    )


def _stored_code(tc) -> str:
    """The code substring of the stored sample: sample minus prefix/suffix."""
    text = tc.sample or ""
    if tc.suffix and text.endswith(tc.suffix):
        text = text[: len(text) - len(tc.suffix)]
    if tc.prefix and text.startswith(tc.prefix):
        text = text[len(tc.prefix):]
    return text


def _scaled_copy(src: Path, width: int, height: int, dest: Path) -> Path:
    im = Image.open(src)
    im.load()
    im = cover_resize(im, width, height)
    im.convert("RGB").save(dest, format="JPEG", quality=95, subsampling=0)
    return dest


def _normalize_hex(value: str) -> str:
    v = value.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", v):
        raise PipelineError(f"'{value}' is not a #rrggbb color")
    return f"#{v.lower()}"


def _collect_warnings(result: dict | None, warnings: list[str]) -> None:
    if not result:
        return
    for w in result.get("warnings", []) or []:
        text = str(w)
        if text not in warnings:
            warnings.append(text)


def _cleanup(run_tmp: Path) -> None:
    shutil.rmtree(run_tmp, ignore_errors=True)
