from __future__ import annotations

import json

import pandas as pd

from biointel.bioinformatics import (
    MODULE_PROFILES,
    RecommendationStore,
    build_recommendation_workspace,
    export_evidence_csv,
    export_recommendation_csv,
    export_recommendation_html,
    export_recommendation_json,
    export_recommendation_pdf,
    export_reproducibility_manifest,
    normalize_recommendation_module,
)


def test_recommendation_workspace_calculates_scores_without_invented_references() -> None:
    results = pd.DataFrame(
        {
            "gene": ["CXCL10", "ISG15", "ACTB"],
            "fdr_bh": [0.001, 0.02, 0.8],
            "log2_fold_change": [2.4, 1.2, 0.1],
        }
    )
    metadata = pd.DataFrame({"sample": ["S1", "S2", "S3", "S4"], "group": ["A", "A", "B", "B"]})
    record = build_recommendation_workspace(
        "transcriptomics",
        {
            "expression_matrix": results,
            "sample_metadata": metadata,
            "experimental_groups": {"reference": "A", "comparison": "B"},
            "evidence": [
                {"evidence_type": "Literature", "source": "PubMed imported collection", "finding": "User-supplied CXCL10 disease evidence", "strength": "Moderate", "status": "Available"},
                {"evidence_type": "Independent cohort validation", "source": "GEO external dataset", "finding": "Directionally consistent replication", "strength": "Moderate", "status": "Available"},
                {"evidence_type": "Orthogonal validation", "source": "qPCR", "finding": "Validation planned", "strength": "Moderate", "status": "Planned"},
            ],
        },
        project_id="P1",
        parameters={"research_objective": "prioritize inflammatory markers"},
        software_version="test-version",
    )
    assert record["module"] == "differential_expression"
    assert record["confidence_score"] is not None and record["confidence_score"] >= 80
    assert record["evidence_grade"].startswith(("Grade A", "Grade B"))
    assert "references are never invented" in json.dumps(record["confidence_components"])
    assert record["reproducibility"]["software_version"] == "test-version"
    assert {"Overview", "Evidence"}.isdisjoint(record.keys())


def test_low_quality_input_caps_confidence_and_priority() -> None:
    record = build_recommendation_workspace(
        "fastq",
        {
            "summary": {
                "reads_profiled": 4,
                "mean_quality": 10.0,
                "adapter_read_fraction": 0.25,
                "duplicate_read_fraction": 0.85,
            }
        },
        project_id="P2",
    )
    assert record["confidence_score"] <= 49
    assert record["priority_score"] <= 54
    assert record["evidence_grade"].startswith("Grade U")
    assert any(row["status"] == "Fail" for row in record["quality_checks"])


def test_recommendation_store_status_and_exports(tmp_path) -> None:
    record = build_recommendation_workspace(
        "variant",
        {"variant_file": pd.DataFrame({"chrom": ["1", "1"], "position": [10, 20], "qual": [50, 60]}), "reference_genome": "GRCh38", "annotation_database_version": "demo"},
        project_id="P3",
    )
    store = RecommendationStore(tmp_path / "recommendations.sqlite3")
    saved_id = store.save(record)
    assert saved_id == record["recommendation_id"]
    loaded = store.get(saved_id)
    assert loaded is not None and loaded["module"] == "variant_prioritization"
    updated = store.update_status(saved_id, "Under Review", actor="tester", note="needs review")
    assert updated["status"] == "Under Review"
    history = store.history_frame(project_id="P3", module="variant")
    assert len(history) == 1
    assert export_recommendation_json(updated).startswith(b"{")
    assert b"recommendation_id" in export_recommendation_csv([updated])
    assert b"Current analysis" in export_evidence_csv(updated)
    assert export_recommendation_html(updated).startswith(b"<!doctype html>")
    assert export_recommendation_pdf(updated).startswith(b"%PDF-1.4")
    assert b"analysis_payload_sha256" in export_reproducibility_manifest(updated)


def test_recommendation_catalog_covers_requested_module_families() -> None:
    assert len(MODULE_PROFILES) >= 19
    assert normalize_recommendation_module("fastq") == "sequencing_quality"
    assert normalize_recommendation_module("transcriptomics") == "differential_expression"
    assert normalize_recommendation_module("metagenomics") == "microbiome"
    assert normalize_recommendation_module("unknown") == "generic_bioinformatics"
