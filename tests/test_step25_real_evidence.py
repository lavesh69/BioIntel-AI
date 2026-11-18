from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from biointel.data.curation import curate_activity_dataset, normalize_activity_value
from biointel.data.evidence_registry import (
    evidence_readiness,
    list_evidence_links,
    record_review,
    seed_standard_licenses,
)
from biointel.data.real_evidence import import_curated_evidence
from biointel.integrations.bindingdb import parse_activity_cell
from biointel.training.leakage_audit import audit_train_test_leakage
from biointel.training.release_gate import evaluate_release_gate
from biointel.ui.navigation import PAGE_CATALOG


def evidence_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"canonical_smiles":"CCO","protein_sequence":"MKTIIALSYIFCLVFADYKDDDDK","standard_value":10,"standard_units":"nM","standard_relation":"<","activity_type":"IC50","assay_id":"A1","publication_id":"PMID:1","confidence_score":9,"replicate_count":3},
        {"canonical_smiles":"CCN","protein_sequence":"GAVLIPFYWSTCMNQDEKRH","standard_value":100000,"standard_units":"nM","standard_relation":">","activity_type":"IC50","assay_id":"A2","publication_id":"PMID:2","confidence_score":8,"replicate_count":2},
    ])

def test_censored_activity_direction_and_state() -> None:
    lower = normalize_activity_value(10, "nM", "<")
    upper = normalize_activity_value(100000, "nM", ">")
    assert lower.p_activity_lower_bound is not None and lower.p_activity_upper_bound is None
    assert upper.p_activity_upper_bound is not None and upper.p_activity_lower_bound is None
    curated, errors, summary = curate_activity_dataset(evidence_frame())
    assert errors.empty
    assert set(curated["activity_state"]) == {"active", "inactive"}
    assert summary.censored_measurements == 2

def test_evidence_import_review_and_readiness(tmp_path: Path) -> None:
    evidence_db=tmp_path/"evidence.sqlite3"
    dataset_db=tmp_path/"datasets.sqlite3"
    seed_standard_licenses(evidence_db)
    result=import_curated_evidence(
        evidence_frame(), provider="generic", source_release="test",
        registry_path=evidence_db, dataset_registry_path=dataset_db,
        output_directory=tmp_path/"real",
    )
    pending=evidence_readiness(evidence_db,result.dataset_sha256)
    assert pending["license_coverage"]==1.0
    assert pending["review_coverage"]==0.0
    for item in list_evidence_links(evidence_db,dataset_sha256=result.dataset_sha256):
        record_review(evidence_db,dataset_sha256=result.dataset_sha256,evidence_key=item["evidence_key"],decision="accepted",reviewer="test")
    ready=evidence_readiness(evidence_db,result.dataset_sha256)
    assert ready["release_ready"] is True
    assert ready["review_coverage"]==1.0

def test_release_gate_requires_evidence_and_hash_binding() -> None:
    metadata=SimpleNamespace(synthetic_demo=False,task_type="classification",dataset_sha256="abc")
    external={"valid_rows":200,"input_rows":200,"metrics":{"roc_auc":.82,"balanced_accuracy":.73},"drift":{"status":"low"}}
    split={"group_overlap":False}
    blocked=evaluate_release_gate(metadata=metadata,external_validation=external,split_summary=split)
    assert blocked.passed is False
    passed=evaluate_release_gate(
        metadata=metadata,external_validation=external,split_summary=split,
        evidence_manifest={"dataset_sha256":"abc","license_coverage":1.0,"review_coverage":1.0,"mean_quality":.75,"source_count":1,"publication_coverage":1.0},
    )
    assert passed.passed is True

def test_leakage_audit_detects_and_clears_overlap() -> None:
    train=pd.DataFrame({"canonical_smiles":["CCO"],"protein_sequence":["AAAAACCCCC"]})
    bad=pd.DataFrame({"canonical_smiles":["CCO"],"protein_sequence":["AAAAACCCCC"]})
    good=pd.DataFrame({"canonical_smiles":["c1ccccc1"],"protein_sequence":["MMMMMNNNNN"]})
    assert audit_train_test_leakage(train,bad).passed is False
    assert audit_train_test_leakage(train,good).passed is True

def test_bindingdb_value_parser() -> None:
    assert parse_activity_cell("< 12.5") == ("<",12.5)
    assert parse_activity_cell(">=1,000") == (">=",1000.0)
    assert parse_activity_cell("not measured") is None

def test_step25_navigation() -> None:
    assert len(PAGE_CATALOG)>=71
    keys={page.key for page in PAGE_CATALOG}
    assert {"real_evidence_studio","benchmark_leakage_lab","evidence_review_queue"} <= keys
