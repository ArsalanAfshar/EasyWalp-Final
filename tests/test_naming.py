"""Naming rules (spec section 3) - the acceptance checklist's first item."""
from __future__ import annotations

import pytest

from easywalp.config import FilenameTemplates, GenerateOptions
from easywalp.pipeline import (
    build_code,
    check_overwrite,
    fill_template,
    format_number,
    output_folder,
    plan_names,
)


def test_format_number():
    assert format_number(236) == "236"
    assert format_number(45) == "045"
    assert format_number(7) == "007"
    assert format_number(999) == "999"
    assert format_number(1000) == "1000"
    assert format_number(12345) == "12345"


def test_default_naming():
    opts = GenerateOptions()
    info = plan_names(opts, "O", 236, "2k")
    assert info.code == "MD-O-C236"
    assert info.folder_name == "MD-O-C236"
    assert info.desktop_file == "D-O-C236.jpg"
    assert info.mobile_file == "M-O-C236.jpg"
    assert info.preview_file == "MD-O-C236-preview.jpg"


def test_anime_category():
    info = plan_names(GenerateOptions(), "A", 12, "2k")
    assert info.code == "MD-A-C012"


def test_resolution_suffix_option():
    on = GenerateOptions(add_resolution_suffix=True)
    info = plan_names(on, "O", 236, "4k")
    assert info.folder_name == "MD-O-C236-4K"
    assert info.desktop_file == "D-O-C236-4K.jpg"
    assert info.mobile_file == "M-O-C236-4K.jpg"
    # the code itself never carries the resolution
    assert info.code == "MD-O-C236"

    info2 = plan_names(on, "O", 236, "2k")
    assert info2.desktop_file == "D-O-C236-2K.jpg"
    assert info2.folder_name == "MD-O-C236-2K"


def test_targets_per_resolution():
    assert plan_names(GenerateOptions(), "O", 1, "2k").desktop_target == (2560, 1440)
    assert plan_names(GenerateOptions(), "O", 1, "2k").mobile_target == (1440, 2560)
    assert plan_names(GenerateOptions(), "O", 1, "4k").desktop_target == (4096, 2304)
    assert plan_names(GenerateOptions(), "O", 1, "4k").mobile_target == (2304, 4096)


def test_custom_templates():
    opts = GenerateOptions(templates=FilenameTemplates(
        code="WP-{CAT}{num}",
        folder="{code}",
        desktop="desk-{code}-{res}",
        mobile="mob-{code}-{res}",
        preview="{code}-mock",
    ))
    info = plan_names(opts, "A", 77, "4k")
    assert info.code == "WP-A077"
    assert info.folder_name == "WP-A077"
    # suffix defaults OFF: the {res} placeholder collapses cleanly
    assert info.desktop_file == "desk-WP-A077.jpg"
    assert info.mobile_file == "mob-WP-A077.jpg"
    opts.add_resolution_suffix = True
    info = plan_names(opts, "A", 77, "4k")
    assert info.desktop_file == "desk-WP-A077-4K.jpg"
    assert info.mobile_file == "mob-WP-A077-4K.jpg"


def test_invalid_inputs():
    with pytest.raises(Exception):
        plan_names(GenerateOptions(), "", 5, "2k")
    with pytest.raises(Exception):
        plan_names(GenerateOptions(), "O", -1, "2k")
    with pytest.raises(Exception):
        plan_names(GenerateOptions(), "O", 5, "8k")


def test_overwrite_detection(tmp_path):
    opts = GenerateOptions()
    info = plan_names(opts, "O", 236, "2k")
    assert check_overwrite(tmp_path, info) is None
    output_folder(tmp_path, info).mkdir(parents=True)
    assert check_overwrite(tmp_path, info) == tmp_path / "MD-O-C236"
