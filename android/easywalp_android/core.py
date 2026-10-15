"""UI-free service layer for the Android app.

Everything here could equally well run behind the Windows GUI: it wires the very
same ``easywalp`` core (presets, wizard helpers, pipeline) to Android's storage
layout. Keeping it free of Kivy means the whole Android flow is unit-testable
against a fake engine, exactly like the desktop pipeline.
"""
from __future__ import annotations

import dataclasses
import logging
import shutil
import time
from collections.abc import Callable
from pathlib import Path

from easywalp import __version__, paths, settings as settings_mod
from easywalp.config import RESOLUTIONS, GenerateOptions
from easywalp.photocraft import PhotoCraftBinary, PhotoCraftError, Session
from easywalp.pipeline import (
    CodeInfo,
    GenerateResult,
    Pipeline,
    PipelineError,
    _flatten_layers,
    check_overwrite,
    plan_names,
)
from easywalp.presets import (
    LayerRef,
    Preset,
    PresetError,
    SmartObjectInfo,
    TextCodeInfo,
    bundled_fonts_for,
    export_preset,
    import_psd_as_preset,
    import_preset,
    new_preset_id,
    split_code_text,
)
from easywalp.presets import detect_code_span as _detect_code_span
from easywalp.wizard import (
    LayerCandidate,
    font_warnings_from,
    inspect_psd,
    shrink_thumbnail,
    top_level_layers,
)

log = logging.getLogger("easywalp.android.core")

#: layer kinds PhotoCraft reports, mapped to what the wizard asks for
ROLE_DESKTOP = "desktop"
ROLE_MOBILE = "mobile"
ROLE_FILL = "fill"
ROLE_TEXT = "text"
ROLES = (ROLE_DESKTOP, ROLE_MOBILE, ROLE_FILL, ROLE_TEXT)


class CoreError(RuntimeError):
    """A readable problem for the UI layer."""


@dataclasses.dataclass
class Analysis:
    """What the wizard learned from a PSD."""

    psd: Path
    layers: list[LayerCandidate]
    suggestions: dict[str, LayerRef | None]
    code_text: str
    code_span: tuple[int, int] | None
    fonts: list[str]
    font_warnings: list[str]
    contents: dict[str, tuple[int, int]]
    thumbnails: dict[int, Path] = dataclasses.field(default_factory=dict)
    warnings: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class GenerateRequest:
    preset: Preset
    desktop: Path
    mobile: Path
    category: str = "O"
    number: int = 1
    resolution_key: str | None = None
    add_resolution_suffix: bool | None = None


class Core:
    """Presets, analysis and generation - no UI, no threads."""

    def __init__(self) -> None:
        self.settings = settings_mod.load()

    # ------------------------------------------------------------------ engine
    def engine(self) -> PhotoCraftBinary:
        try:
            return PhotoCraftBinary(self.settings.photocraft_path or None)
        except PhotoCraftError as e:
            raise CoreError(str(e)) from e

    def engine_status(self) -> tuple[bool, str]:
        try:
            binary = self.engine()
        except CoreError as e:
            return False, str(e)
        return True, f"{binary.path} ({binary.version()})"

    # ----------------------------------------------------------------- presets
    def presets(self) -> list[Preset]:
        return Preset.load_all()

    def preset(self, preset_id: str) -> Preset:
        return Preset.load(preset_id)

    def delete_preset(self, preset: Preset) -> None:
        preset.delete()

    def import_file(self, package: Path) -> Preset:
        """Install a ``.easywalp`` package (picked from Downloads, Telegram, …)."""
        return import_preset(package, __version__)

    def export_file(self, preset: Preset, dest_dir: Path, include_fonts: bool = False) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / f"{_safe_name(preset.name)}.easywalp"
        export_preset(preset, target, include_fonts=include_fonts)
        return target

    # --------------------------------------------------------------- analysis
    def analyze(self, psd: Path, work_dir: Path) -> Analysis:
        """Map a PSD with a single engine session: layers, smart-object sizes, code text."""
        binary = self.engine()
        doc = inspect_psd(binary, psd)
        layers = top_level_layers(doc)
        if not layers:
            raise CoreError("this PSD has no layers PhotoCraft could read")
        suggestions = _suggest_roles(layers, doc)
        contents: dict[str, tuple[int, int]] = {}
        code_text = ""
        code_span = None
        warnings = [str(w) for w in (doc.get("warnings") or [])]

        work_dir.mkdir(parents=True, exist_ok=True)
        with Session(binary, work_root=work_dir) as session:
            session.start()
            session.open(psd)
            flat = _flatten_layers(session.inspect())
            for role in (ROLE_DESKTOP, ROLE_MOBILE):
                ref = suggestions.get(role)
                if ref is None:
                    continue
                lid = _engine_id(flat, ref)
                if lid is None:
                    continue
                out_name = f"so-{role}.png"
                try:
                    session.execute("layer.smartObjects.exportContents", {"layer": lid, "path": out_name})
                except PhotoCraftError as e:
                    warnings.append(str(e))
                    continue
                exported = work_dir / out_name
                if exported.exists():
                    from PIL import Image

                    with Image.open(exported) as im:
                        contents[role] = im.size
            text_ref = suggestions.get(ROLE_TEXT)
            if text_ref is not None:
                lid = _engine_id(flat, text_ref)
                if lid is not None:
                    try:
                        info = session.execute("type.info", {"layer": lid}) or {}
                    except PhotoCraftError as e:
                        warnings.append(str(e))
                        info = {}
                    code_text = str(info.get("text", ""))
                    code_span = _detect_code_span(code_text)

        fonts = _font_families(doc)
        suggestions, contents = _fix_orientation(suggestions, contents)
        return Analysis(
            psd=psd,
            layers=layers,
            suggestions=suggestions,
            code_text=code_text,
            code_span=code_span,
            fonts=fonts,
            font_warnings=font_warnings_from(doc),
            contents=contents,
            warnings=warnings,
        )

    def layer_thumbnails(self, psd: Path, work_dir: Path) -> dict[int, Path]:
        """Small PNG per top-level layer (best effort - never fatal)."""
        from easywalp.wizard import export_layer_thumbnails

        binary = self.engine()
        thumbs = export_layer_thumbnails(binary, psd, work_dir / "thumbs")
        out: dict[int, Path] = {}
        for layer_id, src in thumbs.items():
            try:
                out[layer_id] = shrink_thumbnail(src, work_dir / "thumbs" / f"small-{layer_id}.png")
            except Exception as e:  # noqa: BLE001 - a missing thumbnail is cosmetic
                log.debug("thumbnail %s failed: %s", layer_id, e)
        return out

    def build_preset(
        self,
        analysis: Analysis,
        *,
        name: str,
        mapping: dict[str, LayerRef | None],
        text_code: TextCodeInfo | None = None,
        options: GenerateOptions | None = None,
    ) -> Preset:
        """Create + save a preset from an analysis and the user's mapping."""
        for role, label in (
            (ROLE_DESKTOP, "desktop Smart Object"),
            (ROLE_MOBILE, "mobile Smart Object"),
            (ROLE_FILL, "solid color fill"),
            (ROLE_TEXT, "text layer"),
        ):
            if mapping.get(role) is None:
                raise CoreError(f"the preset needs a {label} layer")
        preset = Preset(
            id=new_preset_id(),
            name=name.strip() or analysis.psd.stem,
            app_version=__version__,
        )
        preset.dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(analysis.psd, preset.template_path)
        preset.desktop_smart_object = mapping[ROLE_DESKTOP]
        preset.mobile_smart_object = mapping[ROLE_MOBILE]
        preset.solid_color_fill = mapping[ROLE_FILL]
        preset.text_layer = mapping[ROLE_TEXT]
        preset.text_code = text_code or _text_code_for(analysis)
        preset.desktop_contents = _contents_for(analysis, ROLE_DESKTOP)
        preset.mobile_contents = _contents_for(analysis, ROLE_MOBILE)
        preset.fonts = analysis.fonts
        preset.options = options or GenerateOptions()
        for font in bundled_fonts_for(preset):
            log.info("preset ships font %s", font.name)
        preset.save()
        return preset

    def update_options(self, preset: Preset, **changes) -> Preset:
        for key, value in changes.items():
            if value is not None and hasattr(preset.options, key):
                setattr(preset.options, key, value)
        preset.save()
        return preset

    # --------------------------------------------------------------- dry run
    def dry_run(self, preset: Preset, out_dir: Path) -> tuple[Path, list[str]]:
        """Render the preview with generated sample wallpapers (wizard step 4)."""
        from easywalp.wizard import dry_run

        try:
            return dry_run(self.engine(), preset, out_dir)
        except (PipelineError, PresetError, PhotoCraftError) as e:
            raise CoreError(str(e)) from e

    # -------------------------------------------------------------- generate
    def plan(self, request: GenerateRequest) -> CodeInfo:
        options = request.preset.options
        try:
            return plan_names(
                options,
                request.category,
                request.number,
                request.resolution_key or options.resolution_key,
            )
        except PipelineError as e:
            raise CoreError(str(e)) from e

    def output_base(self) -> Path:
        base = self.settings.output_base.strip()
        root = Path(base) if base else fallback_output_dir()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def existing_folder(self, request: GenerateRequest) -> Path | None:
        info = self.plan(request)
        return check_overwrite(self.output_base(), info)

    def generate(
        self,
        request: GenerateRequest,
        progress: Callable[[str, float], None] | None = None,
        *,
        overwrite: bool = True,
    ) -> GenerateResult:
        """Run the full pipeline. Blocking - call it from a worker thread."""
        binary = self.engine()
        info = self.plan(request)
        out_base = self.output_base()
        conflict = check_overwrite(out_base, info)
        if conflict and not overwrite:
            raise CoreError(f"{conflict.name} already exists")
        override: dict = {}
        if request.resolution_key:
            override["resolution_key"] = request.resolution_key
        if request.add_resolution_suffix is not None:
            override["add_resolution_suffix"] = request.add_resolution_suffix
        pipeline = Pipeline(binary)
        try:
            result = pipeline.generate(
                request.preset,
                request.desktop,
                request.mobile,
                request.category,
                request.number,
                out_base,
                progress=progress or (lambda _stage, _frac: None),
                options_override=override,
            )
        except (PipelineError, PresetError, PhotoCraftError) as e:
            raise CoreError(str(e)) from e
        self.settings.output_base = str(out_base)
        self.settings.last_category = request.category
        self.settings.last_resolution = request.resolution_key or request.preset.options.resolution_key
        self.settings.last_number = request.number
        self.settings.last_preset_id = request.preset.id
        settings_mod.save(self.settings)
        return result

    # ------------------------------------------------------------- settings
    def save_settings(self) -> None:
        settings_mod.save(self.settings)

    def set_language(self, lang: str) -> None:
        self.settings.language = lang
        self.save_settings()

    def set_theme(self, theme: str) -> None:
        self.settings.theme = theme
        self.save_settings()

    def storage_summary(self) -> str:
        """Human-readable storage report for the Settings screen."""
        try:
            engine_ok, engine_text = self.engine_status()
        except Exception as e:  # noqa: BLE001
            engine_ok, engine_text = False, str(e)
        lines = [
            f"data: {paths.data_dir()}",
            f"out:  {self.output_base()}",
            f"fonts: {paths.fonts_dir()}",
            f"engine: {engine_text if engine_ok else 'not found - ' + engine_text}",
        ]
        return "\n".join(lines)


# --------------------------------------------------------------------- helpers
def fallback_output_dir() -> Path:
    """Default output root on Android: inside the app sandbox, exported on demand."""
    from easywalp import paths

    if paths.is_android():
        return paths.data_dir() / "out"
    return Path.home() / "EasyWalp"


def _suggest_roles(layers: list[LayerCandidate], doc: dict) -> dict[str, LayerRef | None]:
    """Best-guess mapping from layer names/kinds - the user can change every pick."""
    smart = [c for c in layers if c.kind == "Smart Object"]
    fills = [c for c in layers if c.kind == "Fill"]
    texts = [c for c in layers if c.kind == "Type"]

    def ref(candidate: LayerCandidate | None) -> LayerRef | None:
        return LayerRef(candidate.id, candidate.name, candidate.kind) if candidate else None

    desktop, mobile = (smart[0], smart[1]) if len(smart) > 1 else (smart[0] if smart else None, None)
    for candidate in smart:
        low = candidate.name.lower()
        # Device words win over the generic "screen" so "Phone Screen" is not taken
        # for the desktop screen (the aspect check below is the safety net).
        if any(word in low for word in ("mobile", "phone", "iphone", "android", "device")):
            mobile = candidate
        elif any(word in low for word in ("desktop", "monitor", "imac", "laptop", "macbook", "pc")):
            desktop = candidate
    if len(smart) > 1 and desktop is mobile:
        mobile = next(c for c in smart if c is not desktop)
    return {
        ROLE_DESKTOP: ref(desktop),
        ROLE_MOBILE: ref(mobile),
        ROLE_FILL: ref(fills[0] if fills else None),
        ROLE_TEXT: ref(texts[0] if texts else None),
    }


def _fix_orientation(
    suggestions: dict[str, LayerRef | None], contents: dict[str, tuple[int, int]]
) -> tuple[dict[str, LayerRef | None], dict[str, tuple[int, int]]]:
    """Swap desktop/mobile when the exported contents prove they are reversed.

    A desktop wallpaper smart object is landscape (16:9-ish) and a phone one is
    portrait; when the names were unhelpful this is the only reliable signal. The
    user sees the resulting mapping in the wizard and can still change it.
    """
    desktop = contents.get(ROLE_DESKTOP)
    mobile = contents.get(ROLE_MOBILE)
    if not desktop or not mobile:
        return suggestions, contents
    desktop_landscape = desktop[0] >= desktop[1]
    mobile_portrait = mobile[1] >= mobile[0]
    if desktop_landscape or not mobile_portrait:
        return suggestions, contents
    log.info("swapping the desktop/mobile smart objects: %s vs %s", desktop, mobile)
    swapped_suggestions = dict(suggestions)
    swapped_suggestions[ROLE_DESKTOP], swapped_suggestions[ROLE_MOBILE] = (
        suggestions.get(ROLE_MOBILE),
        suggestions.get(ROLE_DESKTOP),
    )
    swapped_contents = dict(contents)
    swapped_contents[ROLE_DESKTOP], swapped_contents[ROLE_MOBILE] = mobile, desktop
    return swapped_suggestions, swapped_contents


def _engine_id(flat: dict[int, dict], ref: LayerRef) -> int | None:
    hit = flat.get(int(ref.id))
    if hit and hit["name"] == ref.name and hit["kind"] == ref.kind:
        return int(ref.id)
    for lid, meta in flat.items():
        if meta["name"] == ref.name and meta["kind"] == ref.kind:
            return lid
    return None


def _contents_for(analysis: Analysis, role: str) -> SmartObjectInfo:
    size = analysis.contents.get(role)
    if not size:
        return SmartObjectInfo()
    return SmartObjectInfo(width=size[0], height=size[1], contents_file_name="")


def _text_code_for(analysis: Analysis) -> TextCodeInfo:
    text = analysis.code_text or "Code:MD-O-C236"
    span = analysis.code_span or _detect_code_span(text)
    if span is None:
        # No code-looking substring: treat the whole text as the code area.
        return TextCodeInfo(prefix="", suffix="", sample=text)
    return split_code_text(text, span)


def _font_families(doc: dict) -> list[str]:
    """Families the document uses, from the layer metadata PhotoCraft reports."""
    families: set[str] = set()

    def walk(items: list) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            font = item.get("font") or item.get("fontFamily")
            if font:
                families.add(str(font))
            walk(item.get("layers") or [])

    walk(doc.get("layers") or [])
    return sorted(families)


def _safe_name(name: str) -> str:
    keep = [c if (c.isalnum() or c in " -_.") else "_" for c in name.strip()]
    return "".join(keep).strip() or "preset"


def resolution_choices() -> list[tuple[str, str]]:
    return [(key, RESOLUTIONS[key].label) for key in RESOLUTIONS]


def elapsed_text(seconds: float) -> str:
    return f"{seconds:.1f}s"


def now() -> float:  # tiny indirection, handy in tests
    return time.monotonic()
