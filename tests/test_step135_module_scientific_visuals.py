from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from biointel.nextgen.biomedical_expansion import NEW_BIOMEDICAL_KEYS, analyse, demo_frame
from biointel.nextgen.catalog import MODULE_BY_KEY
from biointel.nextgen.module_scientific_v135 import (
    PROFILES,
    build_module_scientific_artifacts,
)

ROOT = Path(__file__).resolve().parents[1]


def _artifacts(key: str):
    module = MODULE_BY_KEY[key]
    data = demo_frame(module, 120)
    result, _summary, secondary, extras = analyse(data, module, 0.7)
    return data, build_module_scientific_artifacts(key, data, result, secondary, extras)


def test_step135_scope_is_exactly_the_fifteen_new_biomedical_modules() -> None:
    assert set(PROFILES) == set(NEW_BIOMEDICAL_KEYS)
    assert len(PROFILES) == 15


def test_every_module_builds_multiple_scientific_tables_and_specialist_viewers() -> None:
    for key in sorted(NEW_BIOMEDICAL_KEYS):
        _data, artifacts = _artifacts(key)
        assert artifacts["summary"].get("safe_error") is None, key
        assert artifacts["summary"]["scientific_tables"] >= 2, key
        assert artifacts["summary"]["specialist_viewers"] >= 3, key
        assert not artifacts["quality"].empty, key


def test_clinical_module_has_cox_ph_calibration_and_risk_outputs() -> None:
    _data, artifacts = _artifacts("clinical_biomarker_survival")
    assert {"cox_model_screen", "proportional_hazards_diagnostic", "horizon_calibration", "patient_risk_screen"}.issubset(artifacts["tables"])
    assert {"cox_forest", "calibration", "patient_risk_waterfall", "km_with_risk"}.issubset(artifacts["figures"])
    assert artifacts["summary"]["events"] >= 8


def test_spatial_module_has_neighbourhood_enrichment_and_layered_view() -> None:
    _data, artifacts = _artifacts("spatial_medicine_tme")
    assert "cell_neighbourhood_enrichment" in artifacts["tables"]
    assert "layered_spatial_map" in artifacts["figures"]
    assert "neighbourhood_enrichment" in artifacts["figures"]


def test_pharmacovigilance_has_shrinkage_and_duplicate_review() -> None:
    data, artifacts = _artifacts("pharmacovigilance_intelligence")
    duplicate = pd.concat([data, data.head(2)], ignore_index=True)
    module = MODULE_BY_KEY["pharmacovigilance_intelligence"]
    result, _summary, secondary, extras = analyse(duplicate, module, 0.7)
    artifacts = build_module_scientific_artifacts(module.key, duplicate, result, secondary, extras)
    assert "shrinkage_signal_review" in artifacts["tables"]
    assert "case_duplicate_and_coding_review" in artifacts["tables"]
    assert artifacts["summary"]["duplicate_cases"] >= 2


def test_dirty_and_empty_inputs_fail_safely() -> None:
    for key in sorted(NEW_BIOMEDICAL_KEYS):
        dirty = pd.DataFrame({"unexpected": [1, float("inf"), None], "duplicate": ["a", "a", "a"]})
        artifacts = build_module_scientific_artifacts(key, dirty, pd.DataFrame(), None, {})
        assert isinstance(artifacts["summary"], dict)
        assert isinstance(artifacts["tables"], dict)
        assert isinstance(artifacts["figures"], dict)
        assert not artifacts["quality"].empty


def test_renderer_integrates_step135_without_adding_a_central_page() -> None:
    renderer = (ROOT / "src/biointel/nextgen/renderer.py").read_text(encoding="utf-8")
    assert "render_module_scientific_v135_panel" in renderer
    page_names = {path.name for path in (ROOT / "pages").glob("*.py")}
    assert not any("Step135" in name or "Module_Scientific_Depth_135" in name for name in page_names)


def test_protected_pages_remain_byte_identical() -> None:
    expected = {
        "pages/6_DTI_Predictor.py": "10767f9c1654df364b2321b743117f9367e24f1d17c6642ace8e378c2fedcf1a",
        "pages/74_DTI_Validation_Evidence_Center.py": "a700a8a21649b49cf0e3a1521d2afad45039b83b767c2fe730b93fee7d4f7f11",
        "pages/109_Lab_Instrument_Import_Center.py": "6b8b24f0549593cbe96e6baabc1929b208772d21f48e92ec4630c6835a91d73f",
        "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "85e7812ef3eb05351a0ae28da1a78dc4428b23fe8e8f04e5b41c250363df996f",
        "pages/157_Instrument_Integration_Hub_2.py": "cf3a5f94756def0007dbff31184ec276d90b03fc6d6e1ca792c87189e5ab7d6d",
    }
    for relative, digest in expected.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest


def test_product_version_is_preserved_for_module_only_patch() -> None:
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "13.2.0"
