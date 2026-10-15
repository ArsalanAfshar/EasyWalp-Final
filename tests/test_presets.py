"""Preset persistence, validation and .easywalp sharing."""
from __future__ import annotations

import json
import zipfile

import pytest

from easywalp import __version__
from easywalp.presets import (
    LayerRef,
    Preset,
    PresetError,
    TextCodeInfo,
    detect_code_span,
    export_preset,
    import_preset,
    import_psd_as_preset,
    new_preset_id,
    split_code_text,
)


def _mk_psd(tmp_path):
    psd = tmp_path / "source.psd"
    psd.write_bytes(b"8BPS" + b"\x00" * 64)  # not opened by tests, just stored
    return psd


def _map_layers(preset: Preset) -> None:
    preset.desktop_smart_object = LayerRef(id=12, name="Desktop", kind="Smart Object")
    preset.mobile_smart_object = LayerRef(id=15, name="Mobile", kind="Smart Object")
    preset.solid_color_fill = LayerRef(id=3, name="BG", kind="Fill")
    preset.text_layer = LayerRef(id=8, name="Code", kind="Type")
    preset.text_code = TextCodeInfo(prefix="Code:", suffix="", sample="Code:MD-O-C236")
    preset.desktop_contents.width, preset.desktop_contents.height = 1600, 900
    preset.mobile_contents.width, preset.mobile_contents.height = 900, 1600


def test_roundtrip(data_dir, tmp_path):
    psd = _mk_psd(tmp_path)
    preset = import_psd_as_preset(psd, "My template", __version__)
    _map_layers(preset)
    preset.save()

    loaded = Preset.load(preset.id)
    assert loaded.name == "My template"
    assert loaded.desktop_smart_object == preset.desktop_smart_object
    assert loaded.text_code.prefix == "Code:"
    assert loaded.desktop_contents.width == 1600
    assert (preset.dir / "template.psd").exists()


def test_list_and_rename_and_duplicate(data_dir, tmp_path):
    psd = _mk_psd(tmp_path)
    p1 = import_psd_as_preset(psd, "Alpha", __version__)
    _map_layers(p1)
    p1.save()
    assert [p.name for p in Preset.load_all()] == ["Alpha"]

    p1.rename("Beta")
    assert [p.name for p in Preset.load_all()] == ["Beta"]

    clone = Preset.from_dict(json.loads(p1.json_path.read_text(encoding="utf-8")))
    clone.id = new_preset_id()
    clone.name = "Beta (copy)"
    clone.dir.mkdir(parents=True, exist_ok=True)
    (clone.dir / "template.psd").write_bytes(b"8BPS")
    clone.save()
    assert len(Preset.load_all()) == 2

    clone.delete()
    assert len(Preset.load_all()) == 1


def test_schema_version_rejects_future(data_dir, tmp_path):
    psd = _mk_psd(tmp_path)
    preset = import_psd_as_preset(psd, "Future", __version__)
    data = json.loads(preset.json_path.read_text(encoding="utf-8"))
    data["schemaVersion"] = 99
    preset.json_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PresetError, match="newer EasyWalp"):
        Preset.load(preset.id)


def test_export_import_roundtrip(data_dir, tmp_path):
    src = import_psd_as_preset(_mk_psd(tmp_path), "Share me", __version__)
    _map_layers(src)
    src.save()

    package = tmp_path / "Share me.easywalp"
    export_preset(src, package)
    assert zipfile.is_zipfile(package)

    # import into a DIFFERENT data dir (the colleague's machine)
    other = tmp_path / "other-data"
    other.mkdir()
    import os

    os.environ["EASYWALP_DATA_DIR"] = str(other)
    try:
        installed = import_preset(package, __version__)
        assert installed.id != src.id, "fresh id, no clobbering"
        assert installed.name == "Share me"
        assert installed.desktop_smart_object.id == 12
        assert installed.template_path.exists()
        assert len(Preset.load_all()) == 1
    finally:
        os.environ["EASYWALP_DATA_DIR"] = str(src.dir.parents[1])


def test_import_rejects_non_zip(tmp_path, data_dir):
    bogus = tmp_path / "no.easywalp"
    bogus.write_bytes(b"not a zip")
    with pytest.raises(PresetError):
        import_preset(bogus, __version__)


def test_code_span_detection():
    assert detect_code_span("Code:MD-O-C236") == (5, 14)
    assert detect_code_span("MD-A-C12") == (0, 8)
    assert detect_code_span("no code here") is None
    assert detect_code_span("prefix MD-O-C1000 suffix") == (7, 17)


def test_split_code_text():
    info = split_code_text("Code:MD-O-C236", (5, 14))
    assert info.prefix == "Code:"
    assert info.suffix == ""
    assert info.sample == "Code:MD-O-C236"
