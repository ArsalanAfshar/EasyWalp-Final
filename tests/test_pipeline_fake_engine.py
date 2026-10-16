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
from pathlib import Path

import pytest
from PIL import Image

from easywalp.config import GenerateOptions
from easywalp.photocraft import Session
from easywalp.pipeline import Pipeline
from easywalp.presets import LayerRef, Preset, TextCodeInfo

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="the fake engine shim is a POSIX #!/bin/sh script"
)

# The fake engine lives in tests/fake_engine.py (shared with the Android tests).
from fake_engine import FakeBinary, write_fake_engine  # noqa: E402


def _shim(tmp_path: Path) -> Path:
    return write_fake_engine(tmp_path, name="photocraft-cli-fake")


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


# --------------------------------------------- the two flavours of a colour layer
def test_color_overlay_layer_is_coloured_through_its_layer_style(tmp_path, data_dir, sample_images):
    """A normal layer + Color Overlay must be as good as a Color Fill layer.

    Photoshop templates tint the wallpaper either with a Solid Color *fill layer* or
    with a normal layer carrying a **Color Overlay** layer style. The preset records
    which one it was mapped to, and the pipeline has to send the matching command -
    `layer.fill.solidColor.set` does nothing on a layer that has no fill.
    """
    from unittest import mock

    import easywalp.paths
    import os

    shim = _shim(tmp_path)
    os.environ["FAKE_STATE_DIR"] = str(tmp_path)
    desktop, mobile = sample_images
    preset = _preset(data_dir)
    # "BG Overlay" is a Pixel layer with a colorOverlay effect, inside a group (id 21).
    preset.solid_color_fill = LayerRef(id=21, name="BG Overlay", kind="Pixel", mode="colorOverlay")
    preset.save()
    with mock.patch.object(easywalp.paths, "temp_dir", return_value=tmp_path / "tmpdata3"):
        pipeline = Pipeline(FakeBinary(shim))
        result = pipeline.generate(preset, desktop, mobile, "O", 236, data_dir / "out-overlay")

    calls = json.loads((tmp_path / "calls.json").read_text())["calls"]
    kinds = [c["cmd"] for c in calls]
    assert "layer.layerStyle.colorOverlay" in kinds
    assert "layer.fill.solidColor.set" not in kinds, "a Color Overlay layer has no fill to set"
    colour_call = calls[kinds.index("layer.layerStyle.colorOverlay")]
    assert colour_call["params"] == {"layer": 21, "color": "#1e5a96"}
    assert result.preview_jpg.exists()


def test_a_colour_layer_inside_a_group_is_found(tmp_path, data_dir, sample_images):
    """Nested layers must resolve: PhotoCraft lists them under `children`."""
    from unittest import mock

    import easywalp.paths
    import os

    shim = _shim(tmp_path)
    os.environ["FAKE_STATE_DIR"] = str(tmp_path)
    desktop, mobile = sample_images
    preset = _preset(data_dir)
    # Ids shift when the PSD is re-saved, and the nested layer now lives at another
    # id - the name+kind match (plus the group walk) has to find it anyway.
    preset.solid_color_fill = LayerRef(id=999, name="BG Overlay", kind="Pixel", mode="colorOverlay")
    with mock.patch.object(easywalp.paths, "temp_dir", return_value=tmp_path / "tmpdata4"):
        pipeline = Pipeline(FakeBinary(shim))
        result = pipeline.generate(preset, desktop, mobile, "O", 12, data_dir / "out-nested")

    calls = json.loads((tmp_path / "calls.json").read_text())["calls"]
    overlays = [c for c in calls if c["cmd"] == "layer.layerStyle.colorOverlay"]
    assert overlays, "the nested Color Overlay layer was not found"
    assert overlays[-1]["params"]["layer"] == 21
    assert any("moved from id 999" in w for w in result.warnings)


def test_preset_saves_and_loads_the_colour_mode(data_dir):
    """Old presets (no mode) keep working and mean the fill-layer behaviour."""
    preset = _preset(data_dir)
    preset.solid_color_fill = LayerRef(id=21, name="BG Overlay", kind="Pixel", mode="colorOverlay")
    preset.save()
    payload = json.loads(preset.json_path.read_text())
    assert payload["layers"]["solidColorFill"]["mode"] == "colorOverlay"
    reloaded = Preset.load(preset.id)
    assert reloaded.solid_color_fill is not None
    assert reloaded.solid_color_fill.uses_color_overlay is True

    # a preset written by an older EasyWalp has no "mode" at all
    payload["layers"]["solidColorFill"].pop("mode")
    payload["layers"]["solidColorFill"]["kind"] = "Fill"
    preset.json_path.write_text(json.dumps(payload))
    old = Preset.load(preset.id)
    assert old.solid_color_fill is not None
    assert old.solid_color_fill.uses_color_overlay is False
    assert old.solid_color_fill.to_dict() == {"id": 21, "name": "BG Overlay", "kind": "Fill"}


def test_a_preset_without_a_recorded_contents_size_is_healed_not_refused(
    tmp_path, data_dir, sample_images
):
    """The "recreate the preset" dead end must not exist any more.

    `0.1.2` and older could save a preset whose smart-object contents size was never
    recorded (the wizard's probe was rejected by the engine sandbox). Generating with
    such a preset used to stop with "the preset does not record the desktop smart
    object's contents size; recreate the preset" - the size is now read from the
    smart object itself, the run continues and the preset is updated, so nothing has
    to be recreated.
    """
    from unittest import mock

    import easywalp.paths
    import os

    shim = _shim(tmp_path)
    os.environ["FAKE_STATE_DIR"] = str(tmp_path)
    desktop, mobile = sample_images
    preset = _preset(data_dir)
    preset.desktop_contents.width, preset.desktop_contents.height = 0, 0
    preset.mobile_contents.width, preset.mobile_contents.height = 0, 0
    preset.save()

    with mock.patch.object(easywalp.paths, "temp_dir", return_value=tmp_path / "tmpdata-heal"):
        result = Pipeline(FakeBinary(shim)).generate(
            preset, desktop, mobile, "O", 12, data_dir / "out-heal"
        )

    assert result.preview_jpg.exists()
    assert (result.out_dir).is_dir()
    assert any("contents size" in w for w in result.warnings)
    # the sizes the fake engine handed back (SO 12 -> 1600x900, SO 15 -> 900x1600)
    assert (preset.desktop_contents.width, preset.desktop_contents.height) == (1600, 900)
    assert (preset.mobile_contents.width, preset.mobile_contents.height) == (900, 1600)
    # ... and they are persisted, so the next run needs no probe
    assert Preset.load(preset.dir).desktop_contents.width == 1600


def test_a_replacement_is_still_refused_when_its_aspect_ratio_is_wrong(
    tmp_path, data_dir, tiny_images
):
    """Healing the size must not disable the distortion guard behind it."""
    from unittest import mock

    import easywalp.paths
    import os

    import pytest as _pytest

    from easywalp.pipeline import PipelineError

    shim = _shim(tmp_path)
    os.environ["FAKE_STATE_DIR"] = str(tmp_path)
    desktop, mobile = tiny_images
    preset = _preset(data_dir)
    # say the desktop contents are square while the 16:9 source is not
    preset.desktop_contents.width, preset.desktop_contents.height = 1000, 1000
    preset.save()
    with mock.patch.object(easywalp.paths, "temp_dir", return_value=tmp_path / "tmpdata-aspect"):
        with _pytest.raises(PipelineError) as err:
            Pipeline(FakeBinary(shim)).generate(preset, desktop, mobile, "O", 13, data_dir / "out-aspect")
    assert "does not match" in str(err.value)
