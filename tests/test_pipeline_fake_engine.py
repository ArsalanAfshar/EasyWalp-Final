"""Full Pipeline.generate() against a FAKE engine speaking the real serve protocol.

Verifies EasyWalp's own logic end to end (no Qt, no real PhotoCraft):
  - command order and params sent to the engine (layer ids, replacement sizes,
    solid color, ranged type.edit with only the code replaced),
  - output names/folders and the exact wallpaper JPG sizes (2K and 4K),
  - warnings for upscale/portrait sources.
The fake engine records everything it receives into calls.json in its work root.
"""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest
from PIL import Image

from easywalp.config import GenerateOptions
from easywalp.photocraft import Session
from easywalp.pipeline import Pipeline
from easywalp.presets import LayerRef, Preset, TextCodeInfo

FAKE_ENGINE = r"""
import json, sys, os, struct, zlib

work = os.getcwd()
state_path = os.path.join(os.environ.get("FAKE_STATE_DIR", work), "calls.json")
state = {"calls": [], "text": "Code:MD-O-C236"}
if os.path.exists(state_path):
    state = json.load(open(state_path))


def save_state():
    json.dump(state, open(state_path, "w"))


def png_bytes(size, color=(10, 60, 90)):
    w, h = size
    def chunk(typ, data):
        c = typ + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", 0xFFFFFFFF & zlib.crc32(c))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(color) * w for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    rid, method, params = req["id"], req.get("method"), req.get("params", {}) or {}
    ok, result = True, {}
    if method == "doc.open":
        pass
    elif method == "doc.inspect":
        result = {"width": 2000, "height": 1500, "layers": [
            {"id": 12, "name": "Desktop Screen", "kind": "Smart Object"},
            {"id": 15, "name": "Phone Screen", "kind": "Smart Object"},
            {"id": 3, "name": "BG Color", "kind": "Fill"},
            {"id": 8, "name": "Code label", "kind": "Type"},
        ]}
    elif method == "engine.execute":
        cmd = params.get("command")
        p = params.get("params", {})
        if cmd == "type.info":
            result = {"text": state["text"], "font": "Vazirmatn", "sizePt": 48}
        elif cmd == "type.edit":
            rep = p["replace"]
            t = state["text"]
            state["text"] = t[: rep["start"]] + rep["text"] + t[rep["end"]:]
        elif cmd == "layer.smartObjects.replaceContents":
            from PIL import Image

            with Image.open(p["path"]) as im:
                result = {"replaced": p["layer"], "size": [im.width, im.height]}
        state["calls"].append({"cmd": cmd, "params": p,
                               **({"size": result.get("size")} if "size" in result else {})})
    elif method == "doc.save":
        out = params["path"]
        with open(out, "wb") as f:
            f.write(png_bytes((2000, 1500)))
        result = {"path": out, "warnings": []}
        state["calls"].append({"cmd": "doc.save", "params": {"quality": params.get("quality")}})
    else:
        ok = False
        result = {"error": "unknown " + str(method)}
    save_state()
    reply = {"id": rid, "ok": ok}
    if ok:
        reply["result"] = result
    else:
        reply["error"] = result.get("error", "fake failure")
    sys.stdout.write(json.dumps(reply) + "\n")
    sys.stdout.flush()
"""



def _shim(tmp_path: Path) -> Path:
    if sys.platform == "win32":
        pytest.skip("posix-only fake engine shim")
    script = tmp_path / "fake_engine.py"
    script.write_text(FAKE_ENGINE, encoding="utf-8")
    shim = tmp_path / "photocraft-cli-fake"
    shim.write_text(f"#!/bin/sh\nexport FAKE_STATE=${{FAKE_STATE_DIR:-$PWD}}/calls.json\nexec {sys.executable} {script} \"$@\"\n", encoding="utf-8")
    shim.chmod(0o755)
    return shim


class FakeBinary:
    def __init__(self, path: Path):
        self.path = path

    def version(self) -> str:
        return "fake-1.0"


def _preset(data_dir: Path) -> Preset:
    preset = Preset(id="fake-test", name="Fake test")
    preset.dir.mkdir(parents=True, exist_ok=True)
    preset.desktop_smart_object = LayerRef(id=12, name="Desktop Screen", kind="Smart Object")
    preset.mobile_smart_object = LayerRef(id=15, name="Phone Screen", kind="Smart Object")
    preset.solid_color_fill = LayerRef(id=3, name="BG Color", kind="Fill")
    preset.text_layer = LayerRef(id=8, name="Code label", kind="Type")
    preset.text_code = TextCodeInfo(prefix="Code:", suffix="", sample="Code:MD-O-C236")
    preset.desktop_contents.width, preset.desktop_contents.height = 1600, 900
    preset.mobile_contents.width, preset.mobile_contents.height = 900, 1600
    preset.options = GenerateOptions()
    preset.template_path.write_bytes(b"8BPS-fake")
    preset.save()
    return preset


def test_full_pipeline_logic(tmp_path, data_dir, sample_images):
    from unittest import mock

    import easywalp.paths
    import os

    shim = _shim(tmp_path)
    os.environ["FAKE_STATE_DIR"] = str(tmp_path)
    state_path = tmp_path / "calls.json"
    desktop, mobile = sample_images  # 1920x1080, 1080x1920
    out = data_dir / "out"
    with mock.patch.object(easywalp.paths, "temp_dir", return_value=tmp_path / "tmpdata"):
        pipeline = Pipeline(FakeBinary(shim))
        result = pipeline.generate(_preset(data_dir), desktop, mobile, "O", 236, out)

    # names & outputs
    assert result.out_dir == out / "MD-O-C236"
    assert result.desktop_jpg.name == "D-O-C236.jpg"
    assert result.mobile_jpg.name == "M-O-C236.jpg"
    assert result.preview_jpg.name == "MD-O-C236-preview.jpg"
    with Image.open(result.desktop_jpg) as im:
        assert im.size == (2560, 1440)
    with Image.open(result.mobile_jpg) as im:
        assert im.size == (1440, 2560)

    # engine calls: order and parameters
    calls = json.loads(state_path.read_text())["calls"]
    kinds = [c["cmd"] for c in calls]
    assert kinds == [
        "layer.smartObjects.replaceContents",
        "layer.smartObjects.replaceContents",
        "layer.fill.solidColor.set",
        "type.info",
        "type.edit",
        "doc.save",
    ]
    assert calls[-1]["params"]["quality"] == 95
    assert calls[0]["params"]["path"].endswith("desktop-so.jpg")
    assert calls[1]["params"]["path"].endswith("mobile-so.jpg")
    d_call, m_call = calls[0], calls[1]
    assert d_call["params"]["layer"] == 12 and m_call["params"]["layer"] == 15
    assert d_call["size"] == [1600, 900], "desktop replacement must be at the SO contents size"
    assert m_call["size"] == [900, 1600], "mobile replacement must be at the SO contents size"
    assert calls[2]["params"] == {"layer": 3, "color": "#1e5a96"}
    assert calls[4]["params"]["layer"] == 8
    rep = calls[4]["params"]["replace"]
    assert rep == {"start": 5, "end": 14, "text": "MD-O-C236"}

    # the ranged replace kept the prefix intact
    text_after = json.loads(state_path.read_text())["text"]
    assert text_after == "Code:MD-O-C236"


def test_full_pipeline_4k_names_with_suffix(tmp_path, data_dir, tiny_images):
    from unittest import mock

    import easywalp.paths
    import os

    shim = _shim(tmp_path)
    os.environ["FAKE_STATE_DIR"] = str(tmp_path)
    desktop, mobile = tiny_images  # tiny -> upscale warnings expected
    out = data_dir / "out4k"
    opts = GenerateOptions(add_resolution_suffix=True)
    preset = _preset(data_dir)
    preset.options = opts
    with mock.patch.object(easywalp.paths, "temp_dir", return_value=tmp_path / "tmpdata2"):
        pipeline = Pipeline(FakeBinary(shim))
        result = pipeline.generate(preset, desktop, mobile, "A", 7, out,
                                   options_override={"resolution_key": "4k"})

    assert result.out_dir == out / "MD-A-C007-4K"
    assert result.desktop_jpg.name == "D-A-C007-4K.jpg"
    assert result.mobile_jpg.name == "M-A-C007-4K.jpg"
    assert result.code.code == "MD-A-C007"
    # warnings: both images smaller than 4K targets
    assert any("desktop image" in w and "upscaled" in w for w in result.warnings)
    assert any("mobile image" in w and "upscaled" in w for w in result.warnings)
