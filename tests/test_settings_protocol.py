"""Settings persistence and the PhotoCraft JSON-lines protocol helpers."""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

from easywalp import settings as settings_mod
from easywalp.photocraft_protocol import PhotoCraftError, frame, parse_reply
from easywalp.photocraft import Session


def test_settings_roundtrip(data_dir):
    s = settings_mod.load()
    assert s.language == "en" and s.theme == "system"
    s.language = "fa"
    s.theme = "dark"
    s.output_base = r"D:\Out"
    s.last_number = 236
    settings_mod.save(s)
    again = settings_mod.load()
    assert again.language == "fa"
    assert again.theme == "dark"
    assert again.output_base == r"D:\Out"
    assert again.last_number == 236


def test_settings_survives_corruption(data_dir):
    f = settings_mod.load()
    f.output_base = "X"
    settings_mod.save(f)
    settings_file = settings_mod.paths.settings_file()
    settings_file.write_text("{broken json", encoding="utf-8")
    s = settings_mod.load()
    assert s.language == "en"  # defaults, no crash


def test_protocol_frame_and_reply():
    assert json.loads(frame(7, "doc.inspect")) == {"id": 7, "method": "doc.inspect", "params": {}}
    assert parse_reply('{"id": 7, "ok": true, "result": {"width": 100}}') == {"width": 100}
    with pytest.raises(PhotoCraftError, match="boom"):
        parse_reply('{"id": 7, "ok": false, "error": "boom"}')
    with pytest.raises(PhotoCraftError):
        parse_reply("not json")


FAKE_ENGINE = textwrap.dedent(
    """
    import json, sys
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        method = req.get("method")
        if method == "doc.open":
            result = {"warnings": []}
        elif method == "doc.inspect":
            result = {"width": 2000, "height": 1500, "layers": [{"id": 1, "name": "A", "kind": "Pixel"}]}
        elif method == "engine.execute":
            result = {"echo": req["params"]}
        elif method == "doc.save":
            result = {"path": req["params"]["path"]}
        else:
            sys.stdout.write(json.dumps({"id": req["id"], "ok": False, "error": f"unknown {method}"}) + "\\n")
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps({"id": req["id"], "ok": True, "result": result}) + "\\n")
        sys.stdout.flush()
    """
)


def _fake_engine_shim(tmp_path: Path) -> Path:
    """A real executable that speaks the serve protocol (posix only)."""
    if sys.platform == "win32":
        pytest.skip("posix-only fake engine shim")
    script = tmp_path / "fake_engine.py"
    script.write_text(FAKE_ENGINE, encoding="utf-8")
    shim = tmp_path / "photocraft-cli-fake"
    shim.write_text(f"#!/bin/sh\nexec {sys.executable} {script} \"$@\"\n", encoding="utf-8")
    shim.chmod(0o755)
    return shim


class FakeBinary:
    def __init__(self, path):
        self.path = path

    def version(self):
        return "fake"


def test_session_json_lines(tmp_path):
    shim = _fake_engine_shim(tmp_path)
    session = Session(FakeBinary(shim), work_root=tmp_path)
    session.start()
    try:
        opened = session.open(tmp_path / "x.psd")
        assert opened == {"warnings": []}
        doc = session.inspect()
        assert doc["width"] == 2000
        echo = session.execute("layer.fill.solidColor.set", {"layer": 1, "color": "#0a3a4f"})
        assert echo["echo"]["params"]["color"] == "#0a3a4f"
        with pytest.raises(PhotoCraftError, match="unknown"):
            session.call("nope.method", {})
    finally:
        session.close()
