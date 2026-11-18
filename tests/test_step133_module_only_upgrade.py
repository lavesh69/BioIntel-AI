from __future__ import annotations

from pathlib import Path

import pandas as pd

from biointel.nextgen.biomedical_expansion import NEW_BIOMEDICAL_KEYS, analyse, demo_frame
from biointel.nextgen.catalog import MODULE_BY_KEY
from biointel.nextgen.module_upgrade_v133 import (
    MODULE_ONLY_KEYS,
    PROFILES,
    build_module_upgrade_artifacts,
)

ROOT = Path(__file__).resolve().parents[1]


def test_module_only_scope_covers_exactly_fifteen_new_modules() -> None:
    assert MODULE_ONLY_KEYS == NEW_BIOMEDICAL_KEYS
    assert len(MODULE_ONLY_KEYS) == 15
    assert set(PROFILES) == set(MODULE_ONLY_KEYS)


def test_all_modules_produce_advanced_tables_and_visuals() -> None:
    for key in sorted(MODULE_ONLY_KEYS):
        module = MODULE_BY_KEY[key]
        data = demo_frame(module, 120)
        result, _summary, secondary, extras = analyse(data, module, 0.7)
        artifacts = build_module_upgrade_artifacts(key, data, result, secondary, extras)
        assert artifacts["summary"].get("safe_error") is None, key
        assert artifacts["summary"]["advanced_tables"] >= 1, key
        assert artifacts["summary"]["advanced_visuals"] >= 1, key


def test_empty_and_malformed_inputs_fail_safely() -> None:
    for key in sorted(MODULE_ONLY_KEYS):
        artifacts = build_module_upgrade_artifacts(key, pd.DataFrame(), pd.DataFrame(), None, {})
        assert isinstance(artifacts["summary"], dict)
        assert isinstance(artifacts["tables"], dict)
        assert isinstance(artifacts["figures"], dict)


def test_renderer_adds_module_upgrade_without_new_central_page() -> None:
    source = (ROOT / "src/biointel/nextgen/renderer.py").read_text(encoding="utf-8")
    assert "Module upgrade" in source
    assert "render_module_upgrade_panel" in source
    page_names = {path.name for path in (ROOT / "pages").glob("*.py")}
    assert not any("Step133" in name or "Module_Upgrade_Center" in name for name in page_names)


def test_version_is_preserved_for_module_only_patch() -> None:
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "13.2.0"
