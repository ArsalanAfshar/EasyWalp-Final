"""The engine sandbox: which directories a session may read and write.

PhotoCraft's automation server holds one read root and one write root per session
(``automation::workspace``): ``doc.open``/``doc.place`` accept only paths inside the
read root and ``doc.save``/``doc.exportLayers`` only write inside the write root.
Relative request paths are resolved beneath the root; an absolute path is accepted
only when it lies under it, otherwise the engine answers

    automation path rejected: absolute paths must be inside the automation root: <path>

EasyWalp used to root the wizard's sessions at a *scratch subfolder* of the preset
folder and then ask the engine to open the preset's ``template.psd`` (one level up,
in %APPDATA%) - the whole wizard reached step 4 with no smart-object sizes recorded
and then failed with "does not record the desktop smart object's contents size".

The fake engine enforces the same policy (tests/fake_engine.py), so these tests are
about the sandbox, not about the code paths happening to be lucky.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from easywalp import wizard as wiz
from easywalp.photocraft import PhotoCraftError, Session
from easywalp.presets import LayerRef

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="the fake engine shim is a POSIX #!/bin/sh script"
)

from fake_engine import FakeBinary, write_fake_engine  # noqa: E402


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    shim = write_fake_engine(tmp_path / "engine")
    monkeypatch.setenv("FAKE_STATE_DIR", str(tmp_path))
    return FakeBinary(shim)


def _template(tmp_path: Path) -> Path:
    """A PSD living in its own folder, the way a preset stores one."""
    preset_dir = tmp_path / "AppData" / "EasyWalp" / "presets" / "abc123"
    preset_dir.mkdir(parents=True, exist_ok=True)
    psd = preset_dir / "template.psd"
    psd.write_bytes(b"8BPS" + b"\x00" * 32)
    return psd


def test_the_engine_rejects_a_file_outside_the_session_root(engine, tmp_path):
    """The behaviour that was missing from every test before: it must be enforced."""
    psd = _template(tmp_path)
    scratch = psd.parent / "probe"  # a SUBfolder: the PSD is not inside it
    scratch.mkdir()
    with Session(engine, work_root=scratch) as session:
        session.start()
        with pytest.raises(PhotoCraftError) as err:
            session.open(psd)
    assert "automation path rejected" in str(err.value)
    assert "template.psd" in str(err.value)

    # ... and the same session with an explicit read root can open it
    with Session(engine, work_root=scratch, read_root=psd.parent) as session:
        session.start()
        session.open(psd)
        assert session.inspect()["layers"]


def test_smart_object_contents_reads_the_preset_psd_from_its_own_folder(engine, tmp_path):
    """The exact call the wizard makes when it probes the contents sizes."""
    psd = _template(tmp_path)
    ref = LayerRef(id=12, name="Desktop Screen", kind="Smart Object")
    work_dir = psd.parent / "probe"
    width, height, exported = wiz.smart_object_contents(engine, psd, ref, work_dir)
    assert (width, height) == (1600, 900)
    assert exported == work_dir / "so-12.png"
    assert exported.exists()


def test_layer_thumbnails_read_the_preset_psd_from_its_own_folder(engine, tmp_path):
    psd = _template(tmp_path)
    thumbs = wiz.export_layer_thumbnails(engine, psd, psd.parent / "thumbs")
    assert thumbs, "no thumbnail was exported"
    assert all(p.exists() for p in thumbs.values())


def test_text_layer_info_reads_the_preset_psd(engine, tmp_path):
    """This one always rooted at `psd.parent`, and must keep working."""
    psd = _template(tmp_path)
    ref = LayerRef(id=8, name="Code label", kind="Type")
    info = wiz.text_layer_info(engine, psd, ref)
    assert info["text"] == "Code:MD-O-C236"


def test_the_pipeline_sessions_are_self_contained(engine, tmp_path, data_dir, sample_images, monkeypatch):
    """Generating must not depend on anything outside its own scratch folder.

    The pipeline clones the template into a work dir and does every engine call
    there, so its read root stays the default (the work dir). If that ever stops
    being true, the strict fake engine fails this test.
    """
    from unittest import mock

    import easywalp.paths
    from easywalp.config import GenerateOptions
    from easywalp.pipeline import Pipeline
    from easywalp.presets import Preset, TextCodeInfo

    psd = _template(tmp_path)
    preset = Preset(id="roots", name="Roots")
    preset.dir.mkdir(parents=True, exist_ok=True)
    preset.template_path.write_bytes(psd.read_bytes())
    preset.desktop_smart_object = LayerRef(id=12, name="Desktop Screen", kind="Smart Object")
    preset.mobile_smart_object = LayerRef(id=15, name="Phone Screen", kind="Smart Object")
    preset.solid_color_fill = LayerRef(id=3, name="BG Color", kind="Fill")
    preset.text_layer = LayerRef(id=8, name="Code label", kind="Type")
    preset.text_code = TextCodeInfo()
    preset.desktop_contents.width, preset.desktop_contents.height = 1600, 900
    preset.mobile_contents.width, preset.mobile_contents.height = 900, 1600
    preset.options = GenerateOptions()
    preset.save()

    desktop, mobile = sample_images
    with mock.patch.object(easywalp.paths, "temp_dir", return_value=tmp_path / "scratch"):
        result = Pipeline(engine).generate(preset, desktop, mobile, "O", 1, data_dir / "out")
    assert result.preview_jpg.exists()
    assert result.out_dir == data_dir / "out" / "MD-O-C001"
