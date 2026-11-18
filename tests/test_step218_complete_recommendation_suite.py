from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd

from biointel.bioinformatics import (
    MODULE_FEATURES,
    NOTEBOOK_ENTRY_TYPES,
    RecommendationStore,
    analyze_module,
    build_multi_model_consensus,
    build_recommendation_workspace,
    build_what_if_analysis,
    export_evidence_package,
    export_recommendation_docx,
    export_recommendation_pdf,
    export_recommendation_xlsx,
)


def _analysis_table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "entity": ["A", "B", "C"],
            "gene": ["G1", "G2", "G3"],
            "feature": ["F1", "F2", "F3"],
            "score": [0.9, 0.7, 0.2],
            "effect_size": [1.8, 1.2, 0.1],
            "fdr": [0.001, 0.02, 0.8],
            "sample": ["S1", "S2", "S3"],
            "group": ["A", "A", "B"],
        }
    )


def test_all_requested_module_engines_are_implemented() -> None:
    assert len(MODULE_FEATURES) >= 19
    for module, features in MODULE_FEATURES.items():
        result = analyze_module(module, {"analysis_table": _analysis_table()}, {"research_objective": "test"})
        assert result["module"] == module
        assert result["implementation_coverage_percent"] == 100.0
        assert len(result["feature_coverage"]) == len(features)
        assert all(row["implementation_status"] == "Implemented" for row in result["feature_coverage"])
        assert result["rule_version"]


def test_module_specific_calculations_and_scientific_boundaries() -> None:
    result = analyze_module(
        "sequencing_quality",
        {"summary": {"reads_profiled": 1000, "mean_quality": 24, "adapter_read_fraction": 0.1, "duplicate_read_fraction": 0.25}},
        {"minimum_phred": 20},
    )
    metrics = {row["metric"]: row["value"] for row in result["metrics"]}
    assert metrics["Expected retained reads"] < 1000
    assert any(row["feature"] == "Recommended trimming parameters" for row in result["recommendations"])
    hypothesis = analyze_module("hypothesis_generation", {}, {})
    assert hypothesis["scientific_boundary"]
    assert any(row["evaluation_status"] == "Needs additional input" for row in hypothesis["feature_coverage"])


def test_consensus_and_what_if_expose_disagreement_and_stability() -> None:
    consensus = build_multi_model_consensus(
        {
            "model_predictions": [
                {"model": "A", "prediction": "Supports", "confidence": 0.8},
                {"model": "B", "prediction": "Does not support", "confidence": 0.7},
            ]
        }
    )
    assert consensus["consensus"] == "Mixed"
    assert "disagree" in consensus["disagreement"].lower()
    module_result = analyze_module("statistical_analysis", {"analysis_table": _analysis_table()}, {})
    scenarios = build_what_if_analysis(module_result, {})
    assert len(scenarios) == 3
    assert all("rank_set_stability" in row for row in scenarios)


def test_workspace_persistence_notebook_validation_registry_and_versions(tmp_path: Path) -> None:
    record = build_recommendation_workspace(
        "biomarker",
        {
            "analysis_table": pd.DataFrame({"feature": ["A", "B"], "auc": [0.82, 0.71], "stability": [0.8, 0.6]}),
            "nested_cv": True,
            "external_auc": 0.75,
        },
        project_id="PRO",
        parameters={"research_objective": "rank markers"},
        software_version="test",
    )
    assert record["module_analysis"]["implementation_coverage_percent"] == 100
    assert "multi_model_consensus" in record
    assert "what_if_analysis" in record
    assert "cost_feasibility" in record
    store = RecommendationStore(tmp_path / "recommendations.sqlite3")
    store.save(record)
    store.save(record)
    assert len(store.versions(record["recommendation_id"])) == 2
    entry = store.add_notebook_entry(record["recommendation_id"], NOTEBOOK_ENTRY_TYPES[0], "Review", "Decision notes", actor="tester", assigned_to="lead")
    assert entry.startswith("note-")
    assert store.notebook(record["recommendation_id"])[0]["assigned_to"] == "lead"
    attachment = store.save_attachment(record["recommendation_id"], "evidence.txt", b"evidence", "text/plain", actor="tester")
    assert store.attachment_content(attachment)[2] == b"evidence"
    store.save_validation_result(record["recommendation_id"], "Technical validation", "Passed", "Reproduced", acceptance_criteria="Same hash", actor="tester")
    assert store.validations(record["recommendation_id"])[0]["status"] == "Passed"
    store.register_provenance(record["recommendation_id"], "database", "ClinVar", "test-release", actor="tester")
    assert store.provenance(record["recommendation_id"])[0]["name"] == "ClinVar"
    store.cache_set("key", {"value": 1})
    assert store.cache_get("key") == {"value": 1}
    assert store.events(record["recommendation_id"])


def test_professional_exports_and_evidence_package(tmp_path: Path) -> None:
    record = build_recommendation_workspace(
        "fastq",
        {"summary": {"reads_profiled": 100, "mean_quality": 31, "adapter_read_fraction": 0.01, "duplicate_read_fraction": 0.1}},
        project_id="EXPORT",
        parameters={"research_objective": "QC"},
        software_version="test",
    )
    docx = export_recommendation_docx(record)
    xlsx = export_recommendation_xlsx(record)
    pdf = export_recommendation_pdf(record)
    package = export_evidence_package(record)
    assert docx.startswith(b"PK")
    assert xlsx.startswith(b"PK")
    assert pdf.startswith(b"%PDF")
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert any(name.endswith(".docx") for name in names)
        assert any(name.endswith(".xlsx") for name in names)
        assert any(name.endswith("_scientific.pdf") for name in names)
        assert any(name.endswith("_audit.json") for name in names)
        assert "package_manifest.json" in names

