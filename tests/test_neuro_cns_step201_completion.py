from __future__ import annotations

import io
import json
import zipfile

import numpy as np
import pandas as pd
import pytest
from pypdf import PdfReader

from biointel.neuro_cns import COMPLETION_FEATURES, __version__
from biointel.neuro_cns.chemistry import bbb_permeability
from biointel.neuro_cns.completion import (
    build_resource_binding,
    dataset_drift_monitor,
    deidentify_frame,
    leakage_split_audit,
    multisite_reproducibility_analyzer,
    privacy_scan_frame,
    release_evidence_pack,
    specialist_engine_inventory,
    study_design_power_planner,
)
from biointel.neuro_cns.demos import DEMO_SMILES
from biointel.neuro_cns.provenance import STEP_VERSION, resource_registry_rows
from biointel.neuro_cns.reporting import bundle_pdf


def test_step201_registry_and_version() -> None:
    assert __version__ == "208.0"
    assert STEP_VERSION == "202"
    assert len(COMPLETION_FEATURES) == 9
    assert len({row[2] for row in COMPLETION_FEATURES}) == 9


def test_resource_binding_profiles_csv_and_release_gate() -> None:
    data = b"target,score\nDRD2,0.8\nHTR2A,0.4\n"
    result = build_resource_binding(
        data,
        file_name="targets.csv",
        resource_id="approved_targets",
        provider="Example Provider",
        release_version="2026-07",
        kind="target evidence",
        licence_status="approved",
        commercial_use_status="allowed",
        schema_version="1",
        validation_status="qualified",
    )
    assert result["profile"]["format_status"] == "tabular-parsed"
    assert result["binding"]["release_eligible"] is True
    assert len(result["binding"]["sha256"]) == 64


def test_resource_binding_rejects_bad_identifier() -> None:
    with pytest.raises(ValueError):
        build_resource_binding(
            b"x\n1\n",
            file_name="x.csv",
            resource_id="Bad Resource ID",
            provider="p",
            release_version="1",
            kind="k",
            licence_status="approved",
            commercial_use_status="allowed",
            schema_version="1",
            validation_status="qualified",
        )


def test_engine_inventory_has_expected_specialist_rows() -> None:
    result = specialist_engine_inventory(run_version_checks=False)
    assert len(result["engines"]) >= 10
    assert {"HMMER", "MNE-Python", "NiBabel", "Ensembl VEP"} <= set(result["engines"]["engine"])
    assert result["installed_count"] + result["missing_count"] == len(result["engines"])


def test_privacy_scan_and_deidentification() -> None:
    frame = pd.DataFrame({"patient_id": ["12345678"], "email": ["a@example.org"], "value": [1.2], "visit_date": ["2026-01-01"]})
    scan = privacy_scan_frame(frame)
    assert scan["export_block_recommended"] is True
    clean = deidentify_frame(frame, drop_columns=["email"], hash_columns=["patient_id"], date_columns=["visit_date"], date_shift_days=30)
    assert "email" not in clean
    assert clean.loc[0, "patient_id"] != "12345678"
    assert str(clean.loc[0, "visit_date"]).startswith("2026-01-31")


def test_power_planner_continuous_and_binary() -> None:
    continuous = study_design_power_planner(design="two_group_continuous", effect_size=0.5, power=0.8)
    binary = study_design_power_planner(design="binary", effect_size=0.15, baseline_rate=0.30, power=0.8)
    assert continuous["total_n"] > 100
    assert binary["total_n"] > 0
    assert continuous["control_n"] == continuous["treatment_n"]


def test_leakage_audit_detects_subject_overlap_and_outcome_copy() -> None:
    frame = pd.DataFrame({
        "subject_id": ["S1", "S2", "S1", "S3"],
        "split": ["train", "train", "test", "test"],
        "outcome": [0, 1, 0, 1],
        "outcome_copy": [0, 1, 0, 1],
    })
    result = leakage_split_audit(frame, outcome_column="outcome", split_column="split", subject_id_column="subject_id")
    rules = set(result["findings"]["rule"])
    assert "SUBJECT_SPLIT_OVERLAP" in rules
    assert "OUTCOME_LIKE_COLUMN_NAME" in rules
    assert result["release_blocked"] is True


def test_drift_monitor_detects_numeric_and_categorical_shift() -> None:
    rng = np.random.default_rng(4)
    reference = pd.DataFrame({"x": rng.normal(0, 1, 200), "site": ["A"] * 100 + ["B"] * 100})
    current = pd.DataFrame({"x": rng.normal(2, 1, 200), "site": ["C"] * 200})
    result = dataset_drift_monitor(reference, current)
    assert result["critical_features"] >= 1
    assert set(result["drift"]["type"]) == {"numeric", "categorical"}


def test_multisite_reproducibility_outputs_heterogeneity() -> None:
    frame = pd.DataFrame({"site": ["A", "B", "C"], "estimate": [0.5, 0.3, 0.8], "se": [0.1, 0.12, 0.11]})
    result = multisite_reproducibility_analyzer(frame, site_column="site", estimate_column="estimate", standard_error_column="se")
    assert result["site_count"] == 3
    assert result["i_squared_percent"] >= 0
    assert len(result["random_effect_ci95"]) == 2


def test_pdf_report_is_valid_pdf() -> None:
    results = {"bbb_permeability": bbb_permeability(DEMO_SMILES["Caffeine"])}
    data = bundle_pdf(results, project_name="Unit test")
    assert data.startswith(b"%PDF")
    reader = PdfReader(io.BytesIO(data))
    assert len(reader.pages) >= 2


def test_release_evidence_pack_has_manifest_and_verified_files() -> None:
    results = {"bbb_permeability": bbb_permeability(DEMO_SMILES["Caffeine"])}
    data = release_evidence_pack(results, project_name="Unit test")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
        assert {"MANIFEST.json", "report/neuro_report.json", "report/neuro_report.pdf"} <= names
        manifest = json.loads(archive.read("MANIFEST.json"))
        assert manifest["controlled_release_eligible"] is False
        for row in manifest["files"]:
            assert row["path"] in names


def test_step201_resource_registry_is_present() -> None:
    assert "step201_feature_registry" in {row["resource_id"] for row in resource_registry_rows()}


def test_completion_background_job_executes(tmp_path) -> None:
    from biointel.jobs.local_queue import LocalJobQueue
    from biointel.jobs.worker import LocalWorker
    from biointel.neuro_cns.jobs import submit_neuro_job

    job = submit_neuro_job(
        tmp_path,
        "completion_multisite",
        {
            "table_records": [
                {"site": "A", "estimate": 0.5, "se": 0.1},
                {"site": "B", "estimate": 0.4, "se": 0.12},
            ],
            "parameters": {"site_column": "site", "estimate_column": "estimate", "standard_error_column": "se"},
        },
    )
    worker = LocalWorker(tmp_path, worker_id="step201-neuro-worker")
    run = worker.run_once()
    assert run.status == "completed"
    stored = LocalJobQueue(tmp_path / "reports" / "jobs.sqlite3").get(job.job_id)
    assert stored.result["module_key"] == "completion_multisite"
