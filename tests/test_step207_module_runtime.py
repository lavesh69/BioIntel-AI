from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from biointel.module_runtime_v207.core import (
    PROTECTED_PAGE_PATHS,
    ModuleQualityProfile,
    audit_tabular_dataset,
    build_diagnostic_bundle,
    profile_module_source,
)
from biointel.module_runtime_v207.portfolio import (
    bioinformatics_cohort_readiness,
    count_matrix_quality,
    demo_frame,
    discovery_assay_readiness,
    lab_assay_quality,
    pareto_rank_candidates,
)


ROOT = Path(__file__).resolve().parents[1]


def test_protected_pages_are_explicitly_excluded() -> None:
    assert "pages/6_DTI_Predictor.py" in PROTECTED_PAGE_PATHS
    assert "pages/74_DTI_Validation_Evidence_Center.py" in PROTECTED_PAGE_PATHS
    assert "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py" in PROTECTED_PAGE_PATHS
    assert "pages/109_Lab_Instrument_Import_Center.py" in PROTECTED_PAGE_PATHS
    assert "pages/157_Instrument_Integration_Hub_2.py" in PROTECTED_PAGE_PATHS


def test_source_profile_is_deterministic_and_root_safe() -> None:
    profile = profile_module_source(
        ROOT,
        page_key="bioinformatics_upgrade_center",
        title="Bioinformatics Feature Upgrade Center",
        category="Bioinformatics",
        page_path="pages/167_Bioinformatics_Feature_Upgrade_Center.py",
    )
    again = profile_module_source(
        ROOT,
        page_key="bioinformatics_upgrade_center",
        title="Bioinformatics Feature Upgrade Center",
        category="Bioinformatics",
        page_path="pages/167_Bioinformatics_Feature_Upgrade_Center.py",
    )
    assert profile.source_sha256 == again.source_sha256
    assert profile.source_size_bytes > 0
    assert 0 <= profile.quality_score <= 10
    with pytest.raises(ValueError):
        profile_module_source(ROOT, page_key="x", title="x", category="Bioinformatics", page_path="../outside.py")


@pytest.mark.parametrize(
    ("category", "frame"),
    [
        ("Bioinformatics", demo_frame("bioinformatics_metadata")),
        ("Discovery", demo_frame("discovery_assay")),
        ("Lab Analytics", demo_frame("lab_assay")),
        (
            "Neuro/CNS",
            pd.DataFrame(
                {
                    "subject_id": ["N1", "N1", "N2", "N2"],
                    "time_months": [0, 6, 0, 6],
                    "group": ["case", "case", "control", "control"],
                    "site": ["A", "A", "B", "B"],
                    "score": [8.0, 7.0, 10.0, 10.5],
                }
            ),
        ),
    ],
)
def test_category_data_audit_returns_bounded_score(category: str, frame: pd.DataFrame) -> None:
    result = audit_tabular_dataset(frame, category)
    assert result["category"] == category
    assert 0 <= result["summary"]["readiness_score_internal"] <= 10
    assert result["summary"]["rows"] == len(frame)
    assert "clinical" in result["scientific_boundary"].lower()


def test_diagnostic_bundle_excludes_uploaded_rows_and_redacts_secrets() -> None:
    profile = ModuleQualityProfile(
        page_key="example",
        title="Example",
        category="Bioinformatics",
        page_path="pages/example.py",
        source_sha256="a" * 64,
        source_size_bytes=100,
        has_upload=True,
        has_upload_preflight=True,
        has_scientific_boundary=True,
        has_visual_output=True,
        has_download_export=True,
        has_workflow_status=True,
        has_background_execution=True,
        source_import_count=3,
        quality_score=10.0,
        findings=(),
    )
    audit = audit_tabular_dataset(pd.DataFrame({"sample_id": ["S1", "S2"], "value": [1.0, 2.0]}), "Bioinformatics")
    payload = build_diagnostic_bundle(
        profile,
        release="15.7.0",
        upload_profiles=[{"filename": "cohort.csv", "api_key": "do-not-ship", "sha256": "b" * 64}],
        data_audit=audit,
    )
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert sorted(archive.namelist()) == ["data_readiness_summary.json", "module_diagnostic_manifest.json"]
        manifest_text = archive.read("module_diagnostic_manifest.json").decode("utf-8")
        manifest = json.loads(manifest_text)
    assert "do-not-ship" not in manifest_text
    assert manifest["upload_profiles"][0]["api_key"] == "[REDACTED]"
    assert "S1" not in manifest_text
    assert "S2" not in manifest_text


def test_bioinformatics_portfolio_workflows() -> None:
    cohort = bioinformatics_cohort_readiness(demo_frame("bioinformatics_metadata"))
    assert cohort["summary"]["blocking_checks"] == 0
    assert cohort["summary"]["samples"] == 24
    matrix = count_matrix_quality(demo_frame("count_matrix"))
    assert matrix["summary"]["features"] == 80
    assert matrix["summary"]["samples"] == 12
    assert matrix["summary"]["negative_values"] == 0


def test_discovery_portfolio_workflows() -> None:
    assay = discovery_assay_readiness(demo_frame("discovery_assay"))
    assert assay["summary"]["compounds"] == 18
    assert assay["summary"]["invalid_values"] == 0
    ranking = pareto_rank_candidates(
        demo_frame("pareto"),
        maximize=["potency", "selectivity"],
        minimize=["clearance", "toxicity_proxy"],
    )
    assert ranking["summary"]["ranked"] == 30
    assert ranking["summary"]["pareto_front"] >= 1
    assert ranking["ranking"]["internal_rank"].tolist() == list(range(1, 31))


def test_lab_portfolio_workflow() -> None:
    result = lab_assay_quality(demo_frame("lab_assay"))
    assert result["summary"]["rows"] == 72
    assert result["summary"]["replicate_groups"] == 24
    assert result["summary"]["batches"] == 2
    assert pd.notna(result["summary"]["z_prime"])


def test_invalid_portfolio_inputs_fail_calmly() -> None:
    with pytest.raises(ValueError, match="empty"):
        bioinformatics_cohort_readiness(pd.DataFrame())
    with pytest.raises(ValueError, match="Compound and activity"):
        discovery_assay_readiness(pd.DataFrame({"foo": [1], "bar": [2]}))
    with pytest.raises(ValueError, match="objective"):
        pareto_rank_candidates(pd.DataFrame({"id": ["A", "B"], "x": [1, 2]}))
    with pytest.raises(ValueError, match="measurement"):
        lab_assay_quality(pd.DataFrame({"sample_id": ["S1"]}))


def test_all_target_nonprotected_pages_use_shared_theme_runtime_layer() -> None:
    from biointel.ui.navigation import PAGE_CATALOG

    targets = [
        page
        for page in PAGE_CATALOG
        if page.category in {"Bioinformatics", "Discovery", "Lab Analytics", "Neuro/CNS"}
        and page.path not in PROTECTED_PAGE_PATHS
    ]
    assert targets
    assert len({page.path for page in targets}) == len(targets)
    missing = []
    for page in targets:
        source = (ROOT / page.path).read_text(encoding="utf-8", errors="replace")
        if "apply_theme()" not in source:
            missing.append(page.path)
    assert not missing


def test_protected_module_hash_manifest_is_unchanged() -> None:
    import hashlib

    payload = json.loads((ROOT / "PROTECTED_MODULE_HASHES_STEP205.json").read_text(encoding="utf-8"))
    entries = payload["entries"]
    assert len(entries) == 17
    for entry in entries:
        path = ROOT / entry["path"]
        assert path.is_file(), entry["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], entry["path"]
