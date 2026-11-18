from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from biointel.nextgen.biomedical_expansion import NEW_BIOMEDICAL_KEYS
from biointel.nextgen.catalog import MODULE_BY_KEY, NEXTGEN_MODULES
from biointel.nextgen.scientific import analyse, demo_frame, normalise
from biointel.scientific_depth import profile_for
from biointel.ui.navigation import PAGE_CATALOG

ROOT = Path(__file__).resolve().parents[1]


def test_step128_catalog_has_all_fifteen_modules() -> None:
    assert len(NEW_BIOMEDICAL_KEYS) == 15
    assert NEW_BIOMEDICAL_KEYS.issubset(MODULE_BY_KEY)
    page_numbers = {MODULE_BY_KEY[key].page_number for key in NEW_BIOMEDICAL_KEYS}
    assert page_numbers == set(range(173, 188))
    assert len({module.key for module in NEXTGEN_MODULES}) == len(NEXTGEN_MODULES)


def test_step128_pages_and_navigation_are_registered() -> None:
    nav = {page.key: page for page in PAGE_CATALOG}
    for key in NEW_BIOMEDICAL_KEYS:
        module = MODULE_BY_KEY[key]
        assert key in nav
        path = ROOT / nav[key].path
        assert path.exists(), path
        assert str(module.page_number) in path.name
    assert "next_generation_biomedical_hub" in nav
    assert (ROOT / nav["next_generation_biomedical_hub"].path).exists()


def test_step128_demo_analysis_and_depth_profiles() -> None:
    for key in sorted(NEW_BIOMEDICAL_KEYS):
        module = MODULE_BY_KEY[key]
        frame = demo_frame(module, 120)
        assert not frame.empty, key
        assert set(module.required_columns).issubset(frame.columns), key
        normalised = normalise(frame, module)
        result, summary, secondary, extras = analyse(normalised, module, 0.7)
        assert not result.empty, key
        assert summary["module"] == key
        assert summary["result_records"] == len(result)
        assert "scientific_boundary" in summary
        assert profile_for(key) is not None, key
        assert isinstance(extras, dict)
        assert secondary is None or isinstance(secondary, pd.DataFrame)


def test_step128_module_aware_aliases_preserve_species_patient_and_phenotype() -> None:
    amr = MODULE_BY_KEY["amr_surveillance"]
    frame = normalise(demo_frame(amr, 80), amr)
    assert frame["species"].notna().all()
    assert frame["phenotype"].isin(["Resistant", "Susceptible"]).all()

    biomarker = MODULE_BY_KEY["clinical_biomarker_survival"]
    cohort = normalise(demo_frame(biomarker, 120), biomarker)
    assert cohort["patient"].notna().all()
    assert cohort["patient"].astype(str).str.startswith("CBM-").all()


def test_step128_starter_kits_and_release_config() -> None:
    manifest_path = ROOT / "data/module_starter_kits/step128_next_generation/manifest.json"
    payload = json.loads(manifest_path.read_text())
    assert len(payload["modules"]) == 15
    for item in payload["modules"]:
        path = ROOT / item["starter_file"]
        assert path.exists(), path
        assert path.stat().st_size > 0

    release = json.loads((ROOT / "STEP128_RELEASE.json").read_text())
    assert release["version"] == "13.2.0"
    assert release["new_modules"] == 15
    assert (ROOT / "VERSION").read_text().strip() == "13.2.0"
