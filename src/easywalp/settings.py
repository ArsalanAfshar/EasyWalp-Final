"""Persisted app settings (%APPDATA%/EasyWalp/settings.json)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from . import paths

log = logging.getLogger("easywalp.settings")


@dataclass
class Settings:
    language: str = "en"                 # "en" | "fa"
    theme: str = "system"                # "dark" | "light" | "system"
    output_base: str = ""                # last output folder
    last_preset_id: str = ""
    last_category: str = "O"
    last_resolution: str = "2k"
    last_number: int = 1
    persian_digits: bool = False         # display only; codes/filenames always Latin digits
    photocraft_path: str = ""            # explicit engine binary override
    window_geometry: list[int] = field(default_factory=list)  # [x, y, w, h]
    recent_folders: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "theme": self.theme,
            "outputBase": self.output_base,
            "lastPresetId": self.last_preset_id,
            "lastCategory": self.last_category,
            "lastResolution": self.last_resolution,
            "lastNumber": self.last_number,
            "persianDigits": self.persian_digits,
            "engines": {"photocraftPath": self.photocraft_path},
            "windowGeometry": self.window_geometry,
            "recentFolders": self.recent_folders,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        data = data or {}
        engines = data.get("engines", {}) or {}
        return cls(
            language=str(data.get("language", "en")),
            theme=str(data.get("theme", "system")),
            output_base=str(data.get("outputBase", "")),
            last_preset_id=str(data.get("lastPresetId", "")),
            last_category=str(data.get("lastCategory", "O")),
            last_resolution=str(data.get("lastResolution", "2k")),
            last_number=int(data.get("lastNumber", 1)),
            persian_digits=bool(data.get("persianDigits", False)),
            photocraft_path=str(engines.get("photocraftPath", "")),
            window_geometry=[int(v) for v in (data.get("windowGeometry") or [])][:4],
            recent_folders=[str(f) for f in (data.get("recentFolders") or [])][:10],
        )


def load() -> Settings:
    f = paths.settings_file()
    if not f.exists():
        return Settings()
    try:
        return Settings.from_dict(json.loads(f.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        log.warning("settings file unreadable (%s); using defaults", e)
        return Settings()


def save(settings: Settings) -> None:
    f = paths.settings_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(settings.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def remember_output_folder(settings: Settings, folder: str) -> None:
    settings.output_base = folder
    if folder and folder not in settings.recent_folders:
        settings.recent_folders.insert(0, folder)
        del settings.recent_folders[10:]
