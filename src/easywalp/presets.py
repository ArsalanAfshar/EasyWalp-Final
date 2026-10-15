"""Presets: one cloned PSD template + the layer mapping and naming settings.

A preset lives at ``%APPDATA%/EasyWalp/presets/<preset-id>/`` with
``template.psd`` (the private clone; never modified in place - runs work on a
temp copy) and ``preset.json`` (mapping + settings + schema version).

``.easywalp`` share files are zips containing preset.json + template.psd and an
optional fonts/ folder (font redistribution is off by default and warned about).
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import re
import shutil
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .config import GenerateOptions

log = logging.getLogger("easywalp.presets")

SCHEMA_VERSION = 1
PRESET_FILE = "preset.json"
TEMPLATE_FILE = "template.psd"
FONTS_DIR_IN_PACKAGE = "fonts"


class PresetError(RuntimeError):
    """Readable preset problem (validation, IO, schema)."""


@dataclass
class LayerRef:
    """A mapped layer, stored by id AND name AND kind so every run re-validates."""

    id: int
    name: str
    kind: str  # PhotoCraft kind_name(): "Smart Object" | "Fill" | "Type" | ...

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "kind": self.kind}

    @classmethod
    def from_dict(cls, data: dict) -> "LayerRef":
        return cls(id=int(data["id"]), name=str(data["name"]), kind=str(data["kind"]))


@dataclass
class TextCodeInfo:
    """Where the code sits inside the text layer's current text.

    ``prefix``/``suffix`` are the frozen parts around the code; a run replaces
    exactly the region between them (ranged `type.edit`, styles preserved).
    """

    prefix: str = "Code:"
    suffix: str = ""
    sample: str = "Code:MD-O-C236"  # the text as read when the preset was made

    def to_dict(self) -> dict:
        return {"prefix": self.prefix, "suffix": self.suffix, "sample": self.sample}

    @classmethod
    def from_dict(cls, data: dict | None) -> "TextCodeInfo":
        data = data or {}
        return cls(
            prefix=str(data.get("prefix", "")),
            suffix=str(data.get("suffix", "")),
            sample=str(data.get("sample", "")),
        )


@dataclass
class SmartObjectInfo:
    """Stored contents size of a smart object (replacement images must match)."""

    width: int = 0
    height: int = 0
    contents_file_name: str = ""

    def to_dict(self) -> dict:
        return {"width": self.width, "height": self.height, "contentsFileName": self.contents_file_name}

    @classmethod
    def from_dict(cls, data: dict | None) -> "SmartObjectInfo":
        data = data or {}
        return cls(
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            contents_file_name=str(data.get("contentsFileName", "")),
        )


@dataclass
class Preset:
    id: str
    name: str
    created: str = ""
    app_version: str = ""
    schema_version: int = SCHEMA_VERSION

    desktop_smart_object: LayerRef | None = None
    mobile_smart_object: LayerRef | None = None
    solid_color_fill: LayerRef | None = None
    text_layer: LayerRef | None = None
    text_code: TextCodeInfo = field(default_factory=TextCodeInfo)

    desktop_contents: SmartObjectInfo = field(default_factory=SmartObjectInfo)
    mobile_contents: SmartObjectInfo = field(default_factory=SmartObjectInfo)

    fonts: list[str] = field(default_factory=list)  # families the text layer needs
    options: GenerateOptions = field(default_factory=GenerateOptions)

    # ---------------------------------------------------------------- paths
    @property
    def dir(self) -> Path:
        return paths.presets_dir() / self.id

    @property
    def template_path(self) -> Path:
        return self.dir / TEMPLATE_FILE

    @property
    def json_path(self) -> Path:
        return self.dir / PRESET_FILE

    # ------------------------------------------------------------------ IO
    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": self.schema_version,
            "id": self.id,
            "name": self.name,
            "created": self.created or _now(),
            "appVersion": self.app_version,
            "layers": {
                "desktopSmartObject": self.desktop_smart_object.to_dict() if self.desktop_smart_object else None,
                "mobileSmartObject": self.mobile_smart_object.to_dict() if self.mobile_smart_object else None,
                "solidColorFill": self.solid_color_fill.to_dict() if self.solid_color_fill else None,
                "textLayer": self.text_layer.to_dict() if self.text_layer else None,
            },
            "textCode": self.text_code.to_dict(),
            "contents": {
                "desktopSmartObject": self.desktop_contents.to_dict(),
                "mobileSmartObject": self.mobile_contents.to_dict(),
            },
            "fonts": self.fonts,
            "options": self.options.to_dict(),
        }
        self.json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, preset_id: str) -> "Preset":
        p = cls(id=preset_id, name=preset_id)
        if not p.json_path.exists():
            raise PresetError(f"preset '{preset_id}' has no {PRESET_FILE}")
        try:
            data = json.loads(p.json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise PresetError(f"preset '{preset_id}' is corrupted ({e})") from e
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "Preset":
        version = int(data.get("schemaVersion", 0))
        if version > SCHEMA_VERSION:
            raise PresetError(
                f"this preset was made by a newer EasyWalp (schema {version}); please update the app"
            )
        if version < 1:
            raise PresetError("preset file has no schema version; it may not be an .easywalp export")
        layers = data.get("layers", {})

        def ref(key: str) -> LayerRef | None:
            raw = layers.get(key)
            return LayerRef.from_dict(raw) if raw else None

        contents = data.get("contents", {})
        return cls(
            id=str(data.get("id", uuid.uuid4().hex[:8])),
            name=str(data.get("name", "Unnamed preset")),
            created=str(data.get("created", "")),
            app_version=str(data.get("appVersion", "")),
            schema_version=version,
            desktop_smart_object=ref("desktopSmartObject"),
            mobile_smart_object=ref("mobileSmartObject"),
            solid_color_fill=ref("solidColorFill"),
            text_layer=ref("textLayer"),
            text_code=TextCodeInfo.from_dict(data.get("textCode")),
            desktop_contents=SmartObjectInfo.from_dict(contents.get("desktopSmartObject")),
            mobile_contents=SmartObjectInfo.from_dict(contents.get("mobileSmartObject")),
            fonts=[str(f) for f in data.get("fonts", [])],
            options=GenerateOptions.from_dict(data.get("options")),
        )

    # -------------------------------------------------------------- actions
    def clone_template_to(self, dest: Path) -> None:
        """Copy the stored PSD clone for a run - the stored clone is never touched."""
        if not self.template_path.exists():
            raise PresetError(f"the preset's PSD template is missing: {self.template_path}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.template_path, dest)

    def rename(self, new_name: str) -> None:
        self.name = new_name.strip() or self.name
        self.save()

    def delete(self) -> None:
        if self.dir.exists():
            shutil.rmtree(self.dir, ignore_errors=True)

    # -------------------------------------------------------------- listing
    @staticmethod
    def list_ids() -> list[str]:
        root = paths.presets_dir()
        if not root.exists():
            return []
        out = []
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / PRESET_FILE).exists():
                out.append(child.name)
        return out

    @staticmethod
    def load_all() -> list["Preset"]:
        presets = []
        for pid in Preset.list_ids():
            try:
                presets.append(Preset.load(pid))
            except PresetError as e:
                log.warning("skipping preset: %s", e)
        presets.sort(key=lambda p: p.name.lower())
        return presets


def new_preset_id() -> str:
    return uuid.uuid4().hex[:10]


def import_psd_as_preset(source_psd: Path, name: str, app_version: str) -> Preset:
    """Clone a user PSD into EasyWalp storage and return the (unsaved-mapping) preset."""
    if not source_psd.exists():
        raise PresetError(f"PSD not found: {source_psd}")
    preset = Preset(
        id=new_preset_id(),
        name=name.strip() or source_psd.stem,
        created=_now(),
        app_version=app_version,
    )
    preset.dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_psd, preset.template_path)
    preset.save()
    return preset


# ------------------------------------------------------------------ sharing
def export_preset(preset: Preset, dest_file: Path, include_fonts: bool = False) -> None:
    """Write `<name>.easywalp` (a zip with preset.json + template.psd [+ fonts/])."""
    if not preset.template_path.exists():
        raise PresetError("the preset has no PSD template to export")
    dest_file = dest_file.with_suffix(".easywalp")
    with zipfile.ZipFile(dest_file, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(preset.json_path, PRESET_FILE)
        zf.write(preset.template_path, TEMPLATE_FILE)
        if include_fonts:
            fonts = _system_font_files(preset.fonts)
            if fonts:
                for family, path in fonts:
                    zf.write(path, f"{FONTS_DIR_IN_PACKAGE}/{Path(path).name}")
    log.info("exported preset '%s' -> %s (fonts=%s)", preset.name, dest_file, include_fonts)


def import_preset(package_file: Path, app_version: str) -> Preset:
    """Install a `.easywalp` package as a new preset; returns the loaded preset."""
    if not package_file.exists():
        raise PresetError(f"file not found: {package_file}")
    try:
        with zipfile.ZipFile(package_file) as zf:
            names = zf.namelist()
            if PRESET_FILE not in names:
                raise PresetError("this file is not an EasyWalp preset (preset.json missing)")
            data = json.loads(zf.read(PRESET_FILE).decode("utf-8"))
            preset = Preset.from_dict(data)
            # A fresh local id avoids clobbering an existing preset with the same id.
            preset.id = new_preset_id()
            if preset.created:
                preset.created = preset.created  # keep provenance
            preset.app_version = app_version
            if TEMPLATE_FILE not in names:
                raise PresetError("the preset package has no template.psd")
            preset.dir.mkdir(parents=True, exist_ok=True)
            with zf.open(TEMPLATE_FILE) as src, open(preset.template_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            fonts = [n for n in names if n.startswith(FONTS_DIR_IN_PACKAGE + "/")]
            if fonts:
                font_dir = preset.dir / FONTS_DIR_IN_PACKAGE
                font_dir.mkdir(exist_ok=True)
                for n in fonts:
                    target = preset.dir / n
                    with zf.open(n) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
            preset.save()
    except zipfile.BadZipFile as e:
        raise PresetError("this file is not a valid .easywalp package (not a zip)") from e
    log.info("imported preset '%s' from %s", preset.name, package_file)
    return preset


def bundled_fonts_for(preset: Preset) -> list[Path]:
    """Font files shipped inside an imported preset package, if any."""
    d = preset.dir / FONTS_DIR_IN_PACKAGE
    if not d.exists():
        return []
    return sorted(p for p in d.iterdir() if p.suffix.lower() in {".ttf", ".otf"})


def _system_font_files(families: list[str]) -> list[tuple[str, str]]:
    """Best-effort lookup of installed font files for the given family names (Windows-first)."""
    found: list[tuple[str, str]] = []
    search_dirs: list[Path] = []
    if sys_platform() == "win32":
        win = Path(os_environ().get("WINDIR", r"C:\Windows"))
        search_dirs += [win / "Fonts", os_environ().get("LOCALAPPDATA", "") and Path(os_environ()["LOCALAPPDATA"]) / "Microsoft" / "Windows" / "Fonts"]
    else:
        search_dirs += [Path("/usr/share/fonts"), Path.home() / ".local/share/fonts"]
    wanted = [f.lower() for f in families]
    for d in search_dirs:
        if not d or not d.exists():
            continue
        for f in d.rglob("*"):
            if f.suffix.lower() not in {".ttf", ".otf"}:
                continue
            stem = f.stem.lower()
            for w in wanted:
                if w.replace(" ", "") in stem.replace(" ", "").replace("-", ""):
                    found.append((w, str(f)))
                    break
    return found


# Match a code like MD-O-C236 inside arbitrary text (default template shape).
CODE_PATTERN = re.compile(r"\bMD-[A-Z]-C\d{1,}\b")


def detect_code_span(text: str) -> tuple[int, int] | None:
    """Character span [start, end) of the first code-looking substring, else None."""
    m = CODE_PATTERN.search(text)
    if not m:
        return None
    return (m.start(), m.end())


def split_code_text(text: str, span: tuple[int, int]) -> TextCodeInfo:
    """Build the frozen prefix/suffix around a chosen code span."""
    return TextCodeInfo(prefix=text[: span[0]], suffix=text[span[1] :], sample=text)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# tiny indirections so tests can monkeypatch platform bits cleanly
def sys_platform() -> str:
    import sys

    return sys.platform


def os_environ() -> dict:
    import os

    return os.environ
