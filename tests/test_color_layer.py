"""The colour layer: which layers count, and how their colour is changed.

Photoshop templates tint a wallpaper in two ways and users call both "the Solid
Color layer":

* a Solid Color **fill layer** (PhotoCraft kind ``Fill``) - ``layer.fill.solidColor.set``;
* a normal layer carrying a **Color Overlay** layer style - ``layer.layerStyle.colorOverlay``.

The second one is what the wizard failed to offer, and its layer is usually inside a
group - so these tests also pin the group walk (PhotoCraft nests layers under
``children``, not ``layers``).
"""
from __future__ import annotations

import sys

import pytest

from easywalp import wizard as wiz
from easywalp.pipeline import _flatten_layers
from easywalp.presets import (
    COLOR_OVERLAY_KIND,
    MODE_COLOR_OVERLAY,
    MODE_FILL,
    LayerRef,
    Preset,
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="the fake engine shim is a POSIX #!/bin/sh script"
)

from fake_engine import write_fake_engine  # noqa: E402


DOC = {
    "width": 2000,
    "height": 1500,
    "layers": [
        {"id": 12, "name": "Desktop Screen", "kind": "Smart Object"},
        {"id": 3, "name": "BG Color", "kind": "Fill"},
        {
            "id": 25,
            "name": "Tint group",
            "kind": "Group",
            "children": [
                {
                    "id": 21,
                    "name": "BG Overlay",
                    "kind": "Pixel",
                    "effects": {"enabled": True, "items": [{"kind": "colorOverlay", "enabled": True}]},
                },
                {"id": 22, "name": "Plain pixel", "kind": "Pixel"},
            ],
        },
        {"id": 8, "name": "Code label", "kind": "Type"},
    ],
}


def test_all_layers_walks_into_groups():
    ids = [c.id for c in wiz.all_layers(DOC)]
    assert 21 in ids and 22 in ids, "nested layers must be candidates"
    nested = next(c for c in wiz.all_layers(DOC) if c.id == 21)
    assert nested.path == "Tint group"
    assert nested.label.startswith("[Color Overlay] Tint group / BG Overlay")

    # top-level view stays what it always was (doc.exportLayers numbers those)
    assert [c.id for c in wiz.top_level_layers(DOC)] == [12, 3, 25, 8]


def test_only_the_two_colour_flavours_are_offered():
    wants = {c.id for c in wiz.all_layers(DOC) if c.is_color_layer}
    assert wants == {3, 21}, "a Color Fill layer and a Color Overlay layer, nothing else"
    plain = next(c for c in wiz.all_layers(DOC) if c.id == 22)
    assert plain.is_color_layer is False
    fill = next(c for c in wiz.all_layers(DOC) if c.id == 3)
    assert fill.label.startswith("[Fill] BG Color")


def test_flat_layer_map_walks_children():
    """The pipeline's id -> layer map has to see nested layers (it did not)."""
    flat = _flatten_layers(DOC)
    assert set(flat) == {12, 3, 25, 21, 22, 8}
    assert flat[21]["kind"] == "Pixel"
    assert COLOR_OVERLAY_KIND in flat[21]["effects"]
    assert flat[22]["effects"] == ()


def test_preset_remembers_which_flavour_it_was_set_up_with(data_dir):
    preset = Preset(id="modes", name="Modes")
    preset.dir.mkdir(parents=True, exist_ok=True)
    preset.solid_color_fill = LayerRef(id=21, name="BG Overlay", kind="Pixel", mode=MODE_COLOR_OVERLAY)
    preset.save()
    assert preset.solid_color_fill.uses_color_overlay is True
    assert Preset.load("modes").solid_color_fill.mode == MODE_COLOR_OVERLAY

    # a preset from before this existed, and a plain fill mapping
    for mode, expected in (("", False), (MODE_FILL, False)):
        preset.solid_color_fill = LayerRef(id=3, name="BG Color", kind="Fill", mode=mode)
        preset.save()
        assert preset.solid_color_fill.uses_color_overlay is expected
        assert Preset.load("modes").solid_color_fill.uses_color_overlay is expected


def test_wizard_core_maps_a_color_overlay_layer(tmp_path, data_dir, monkeypatch):
    """End of the chain: the wizard's own analysis + mapping for such a PSD."""
    from easywalp.photocraft import PhotoCraftBinary
    from easywalp.presets import import_psd_as_preset

    shim = write_fake_engine(tmp_path / "engine")
    monkeypatch.setenv("FAKE_STATE_DIR", str(tmp_path))
    psd = tmp_path / "template.psd"
    psd.write_bytes(b"8BPS" + b"\x00" * 64)

    binary = PhotoCraftBinary(str(shim))
    info = wiz.inspect_psd(binary, psd)
    candidates = wiz.all_layers(info)
    colour = [c for c in candidates if c.is_color_layer]
    assert {c.id for c in colour} == {3, 21}

    overlay = next(c for c in colour if c.kind != "Fill")
    preset = import_psd_as_preset(psd, "from fake engine", "0.0.0")
    preset.solid_color_fill = LayerRef(overlay.id, overlay.name, overlay.kind, MODE_COLOR_OVERLAY)
    preset.save()
    assert Preset.load(preset.id).solid_color_fill.uses_color_overlay is True
