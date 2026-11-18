from __future__ import annotations

import json
from pathlib import Path

from biointel.expansion.catalog import EXPANSION_MODULES
from biointel.expansion.renderer import _analyse, _demo_frame, _normalise
from biointel.ui.navigation import PAGE_BY_KEY

ROOT = Path(__file__).resolve().parents[1]


def test_step102_version_and_release_metadata_are_synchronised():
    assert (ROOT / "VERSION").read_text().strip() == "13.2.0"
    assert 'version = "13.2.0"' in (ROOT / "pyproject.toml").read_text()
    assert json.loads((ROOT / "STEP102_RELEASE.json").read_text())["new_module_count"] == 21


def test_all_twenty_one_expansion_modules_are_registered_and_packaged():
    assert len(EXPANSION_MODULES) == 21
    for module in EXPANSION_MODULES:
        page = PAGE_BY_KEY[module.key]
        assert page.path.startswith("pages/")
        assert (ROOT / page.path).is_file(), page.path
    assert (ROOT / "pages/133_Scientific_Expansion_Hub.py").is_file()


def test_every_expansion_demo_dataset_executes():
    for module in EXPANSION_MODULES:
        data = _normalise(_demo_frame(module, 96), module)
        result, summary, _ = _analyse(data, module, 0.70)
        assert not data.empty, module.key
        assert not result.empty, module.key
        assert summary["input_records"] == len(data)
        assert summary["result_records"] == len(result)


def test_navigation_contains_new_research_categories():
    navigation = (ROOT / "src/biointel/ui/navigation.py").read_text()
    assert '"Clinical Research"' in navigation
    assert '"Research Planning"' in navigation
    assert '"scientific_expansion_hub"' in navigation
