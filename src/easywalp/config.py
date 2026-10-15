"""Central EasyWalp configuration tables.

Add a new resolution by adding one entry to RESOLUTIONS - nothing else is
hardcoded: resizing, naming and UI read this single table.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Resolution:
    key: str                      # "2k" / "4k" - used on the CLI and in settings
    label: str                    # UI label
    desktop: tuple[int, int]      # (width, height)
    mobile: tuple[int, int]

    @property
    def suffix(self) -> str:
        return self.key.upper()


RESOLUTIONS: dict[str, Resolution] = {
    "2k": Resolution("2k", "2K", desktop=(2560, 1440), mobile=(1440, 2560)),
    "4k": Resolution("4k", "4K", desktop=(4096, 2304), mobile=(2304, 4096)),
}

DEFAULT_RESOLUTION_KEY = "2k"

CATEGORIES: dict[str, str] = {
    "O": "Other",
    "A": "Anime",
}

DEFAULT_JPEG_QUALITY = 95

# Average-color downscale target for the mean-RGB computation (per the spec: ~256 px).
AVG_COLOR_SAMPLE_SIZE = 256


@dataclass
class FilenameTemplates:
    """Configurable naming templates. Placeholders: {cat} {CAT} {num} {res} {code}."""

    code: str = "MD-{CAT}-C{num}"
    folder: str = "MD-{CAT}-C{num}"
    desktop: str = "D-{CAT}-C{num}"
    mobile: str = "M-{CAT}-C{num}"
    preview: str = "MD-{CAT}-C{num}-preview"

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "folder": self.folder,
            "desktop": self.desktop,
            "mobile": self.mobile,
            "preview": self.preview,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "FilenameTemplates":
        base = cls()
        if not data:
            return base
        return cls(
            code=str(data.get("code", base.code)),
            folder=str(data.get("folder", base.folder)),
            desktop=str(data.get("desktop", base.desktop)),
            mobile=str(data.get("mobile", base.mobile)),
            preview=str(data.get("preview", base.preview)),
        )


@dataclass
class GenerateOptions:
    """Options the user can flip on the main screen or preset editor."""

    resolution_key: str = DEFAULT_RESOLUTION_KEY
    add_resolution_suffix: bool = False
    color_source: str = "desktop"          # "desktop" | "mobile" | "manual"
    manual_color: str | None = None        # "#rrggbb" when color_source == "manual"
    jpeg_quality: int = DEFAULT_JPEG_QUALITY
    templates: FilenameTemplates = field(default_factory=FilenameTemplates)

    def to_dict(self) -> dict:
        return {
            "resolution": self.resolution_key,
            "addResolutionSuffix": self.add_resolution_suffix,
            "colorSource": self.color_source,
            "manualColor": self.manual_color,
            "jpegQuality": self.jpeg_quality,
            "templates": self.templates.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "GenerateOptions":
        data = data or {}
        return cls(
            resolution_key=str(data.get("resolution", DEFAULT_RESOLUTION_KEY)),
            add_resolution_suffix=bool(data.get("addResolutionSuffix", False)),
            color_source=str(data.get("colorSource", "desktop")),
            manual_color=data.get("manualColor"),
            jpeg_quality=int(data.get("jpegQuality", DEFAULT_JPEG_QUALITY)),
            templates=FilenameTemplates.from_dict(data.get("templates")),
        )
