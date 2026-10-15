"""The Inno Setup files are checked here because nothing else can check them.

ISCC only runs on Windows and only in CI, and every mistake in these two files
shows up as a failed release run half an hour in - which is exactly what happened
twice: a relative icon path resolved from the wrong folder, and a message key
with dots in it (Inno reads `Something.Other` as a language-qualified name and
refuses to compile a language file).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WINDOWS = REPO / "packaging" / "windows"
ISS = WINDOWS / "easywalp.iss"
ISL = WINDOWS / "Farsi.isl"


def _sections(path: Path) -> dict[str, dict[str, str]]:
    """Parse an .iss/.isl file into {section: {key: value}} (comments dropped)."""
    out: dict[str, dict[str, str]] = {}
    section = ""
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        header = re.match(r"^\[(.+)]$", line)
        if header:
            section = header.group(1).lower()
            out.setdefault(section, {})
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            out.setdefault(section, {})[key.strip()] = value.strip()
    return out


def test_farsi_messages_are_inno_message_names():
    """A key with a dot (or anything but a plain name) aborts the compile."""
    messages = _sections(ISL).get("messages", {})
    assert messages, "Farsi.isl has no [Messages] section"
    for key in messages:
        assert re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", key), (
            f"{key!r} is not a plain Inno message name - a '.' makes ISCC report "
            "'A language name may not be specified in a messages file'"
        )
        assert not messages[key].startswith("&"), f"{key} should use & for its accelerator"


def test_language_options_and_rtl_are_kept():
    lang = _sections(ISL).get("langoptions", {})
    assert lang.get("LanguageID") == "$0429", "the Persian language ID is what turns on RTL"
    assert lang.get("LanguageName")


def test_iss_relative_paths_exist():
    """Inno resolves relative paths from the .iss folder, not from the repo root."""
    setup = _sections(ISS).get("setup", {})
    icon = setup.get("SetupIconFile")
    assert icon, "no SetupIconFile in easywalp.iss"
    assert (WINDOWS / icon.replace("\\", "/")).resolve().is_file(), (
        f"SetupIconFile={icon} does not resolve from {WINDOWS}"
    )


def test_iss_languages_reference_the_bundled_files():
    languages = _sections(ISS).get("languages", {})
    names = {v.get("Name", "").strip('"') for v in _as_rows(ISS)}
    assert {"english", "farsi"} <= names, f"languages declared: {names}"
    farsi = next(r for r in _as_rows(ISS) if r.get("Name", "").strip('"') == "farsi")
    files = [f.strip().strip('"') for f in farsi["MessagesFile"].split(",")]
    assert "compiler:Default.isl" in files, "Farsi chains on top of Default.isl for untranslated text"
    for name in files:
        if not name.startswith("compiler:"):
            assert (WINDOWS / name).is_file(), f"{name} is not next to easywalp.iss"
    assert languages is not None


def _as_rows(path: Path) -> list[dict[str, str]]:
    """Rows of the [Languages] section (parameter: value; ... per line)."""
    rows: list[dict[str, str]] = []
    inside = False
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line.startswith("["):
            inside = line.lower() == "[languages]"
            continue
        if not inside or not line or line.startswith(";"):
            continue
        row: dict[str, str] = {}
        for part in line.split(";"):
            if ":" in part:
                key, value = part.split(":", 1)
                row[key.strip()] = value.strip()
        if row:
            rows.append(row)
    return rows
