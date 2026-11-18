from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from biointel.neuro_cns import __version__
from biointel.neuro_cns.chemistry import bbb_permeability
from biointel.neuro_cns.demos import DEMO_SMILES
from biointel.neuro_cns.hardening import numeric_frame_health, safe_execute, stable_fingerprint, validate_payload
from biointel.neuro_cns.jobs import execute_neuro_job_payload
from biointel.neuro_cns.max_potential import (
    MAX_POTENTIAL_FEATURES,
    applicability_domain_inspector,
    batch_pipeline_orchestrator,
    benchmark_validation_center,
    contradiction_resolution_board,
    evidence_knowledge_graph,
    failure_recovery_center,
    maximum_potential_release_dashboard,
    resource_qualification_manager,
    uncertainty_sensitivity_lab,
)
from biointel.neuro_cns.provenance import STEP_VERSION, resource_registry_rows
from biointel.neuro_cns.reporting import build_result_bundle, bundle_html, bundle_markdown


def test_step200_registry_and_version() -> None:
    assert __version__ == "208.0"
    assert STEP_VERSION == "202"
    assert len(MAX_POTENTIAL_FEATURES) == 9
    assert len({row[2] for row in MAX_POTENTIAL_FEATURES}) == 9


def test_safe_execute_completes_with_metrics() -> None:
    envelope = safe_execute("demo", lambda: {"ok": True}, inputs={"x": 1})
    assert envelope.status == "completed"
    assert envelope.result == {"ok": True}
    assert envelope.elapsed_ms >= 0
    assert envelope.peak_memory_mb >= 0
    assert len(envelope.input_fingerprint_sha256) == 64


def test_safe_execute_isolates_input_error() -> None:
    envelope = safe_execute("demo", lambda: (_ for _ in ()).throw(ValueError("bad unit")), inputs={"unit": "banana"})
    assert envelope.status == "failed"
    assert envelope.error is not None
    assert envelope.error.recovery_code == "INPUT_VALIDATION"
    assert envelope.result is None


def test_stable_fingerprint_is_order_independent() -> None:
    assert stable_fingerprint({"a": 1, "b": 2}) == stable_fingerprint({"b": 2, "a": 1})


def test_payload_validation_and_frame_health() -> None:
    frame = pd.DataFrame({"a": [1.0, 2.0, np.nan], "b": [1.0, 1.0, 1.0]})
    assert validate_payload(frame) == ()
    health = numeric_frame_health(frame)
    assert health["missing_cells"] == 1
    assert "b" in health["constant_numeric_columns"]
    assert health["quality_grade"] == "review"


def test_evidence_graph_uses_explicit_results_only() -> None:
    results = {
        "bbb_permeability": bbb_permeability(DEMO_SMILES["Caffeine"], "caffeine"),
        "cns_disease_targets": pd.DataFrame([{"target_id": "DRD2", "disease": "Parkinson disease", "confidence": "high"}]),
    }
    graph = evidence_knowledge_graph(results)
    assert graph["node_count"] >= 3
    assert graph["edge_count"] >= 2
    assert set(graph["edges"]["module_key"]) <= set(results)


def _benchmark_frame() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    labels = np.tile([0, 1], 60)
    scores = np.clip(labels * 0.65 + rng.normal(0.18, 0.12, len(labels)), 0, 1)
    return pd.DataFrame({"label": labels, "score": scores, "site": np.where(np.arange(len(labels)) % 2, "B", "A")})


def test_benchmark_validation_center_metrics_and_subgroups() -> None:
    output = benchmark_validation_center(_benchmark_frame(), label_column="label", score_column="score", group_column="site", bootstrap_iterations=25)
    assert output["n"] == 120
    assert "roc_auc" in set(output["metrics"]["metric"])
    assert len(output["calibration"]) > 0
    assert set(output["subgroup_performance"]["group"]) == {"A", "B"}


def test_benchmark_validation_rejects_single_class() -> None:
    frame = pd.DataFrame({"label": [1] * 12, "score": np.linspace(0.1, 0.9, 12)})
    with pytest.raises(ValueError):
        benchmark_validation_center(frame, label_column="label", score_column="score", bootstrap_iterations=5)


def test_applicability_domain_flags_extreme_query() -> None:
    rng = np.random.default_rng(1)
    ref = pd.DataFrame(rng.normal(size=(100, 4)), columns=list("abcd"))
    qry = pd.DataFrame([[0, 0, 0, 0], [20, 20, 20, 20]], columns=list("abcd"))
    output = applicability_domain_inspector(ref, qry)
    assert bool(output["assessment"].iloc[0]["inside_applicability_domain"])
    assert not bool(output["assessment"].iloc[1]["inside_applicability_domain"])


def test_uncertainty_lab_is_deterministic_and_ranks_influence() -> None:
    evaluator = lambda concentration, kd: 100 * concentration / (concentration + kd)
    params = {"concentration": 20.0, "kd": 5.0}
    uncertainty = {
        "concentration": {"distribution": "lognormal", "cv": 0.2, "minimum": 0},
        "kd": {"distribution": "lognormal", "cv": 0.1, "minimum": 0.001},
    }
    a = uncertainty_sensitivity_lab(evaluator, params, uncertainty, iterations=80, seed=7)
    b = uncertainty_sensitivity_lab(evaluator, params, uncertainty, iterations=80, seed=7)
    assert a["output_summary"] == b["output_summary"]
    assert len(a["sensitivity"]) == 2
    assert a["output_summary"]["ci95_high"] >= a["output_summary"]["ci95_low"]


def test_resource_qualification_covers_all_modules() -> None:
    output = resource_qualification_manager()
    assert len(output["modules"]) == 41
    assert output["blocked_modules"] >= 1
    assert "step200_feature_registry" in {row["resource_id"] for row in resource_registry_rows()}


def test_contradiction_resolver_preserves_review() -> None:
    output = contradiction_resolution_board({"cns_side_effects": {"coverage": {"coverage_fraction": 0.1}}})
    assert output["open_count"] >= 1
    assert "LOW_SIDE_EFFECT_COVERAGE" in set(output["board"]["rule"])
    assert set(output["board"]["review_status"]) == {"open"}


def test_batch_orchestrator_continues_after_isolated_error() -> None:
    tasks = [
        {"task_id": "ok", "module_key": "bbb_permeability", "compound_rows": [{"compound_id": "c", "smiles": DEMO_SMILES["Caffeine"]}]},
        {"task_id": "bad", "module_key": "unsupported", "table_records": []},
    ]
    output = batch_pipeline_orchestrator(tasks, executor=execute_neuro_job_payload, continue_on_error=True)
    assert output["executed"] == 2
    assert output["completed"] == 1
    assert output["failed"] == 1
    assert {row["status"] for row in output["tasks"]} == {"completed", "failed"}


def test_failure_recovery_center_classifies_errors() -> None:
    output = failure_recovery_center([
        {"module_key": "x", "error_type": "ValueError", "message": "missing column", "recovery_code": "SCHEMA_MISMATCH"},
        {"module_key": "y", "error_type": "MemoryError", "message": "memory", "recovery_code": "RESOURCE_EXHAUSTION"},
    ])
    assert output["error_count"] == 2
    assert output["retry_safe_count"] == 2
    assert set(output["errors"]["category"]) == {"data_schema", "performance"}


def test_release_dashboard_separates_software_and_science() -> None:
    output = maximum_potential_release_dashboard({"bbb_permeability": bbb_permeability(DEMO_SMILES["Caffeine"])}, test_status={"passed": 10, "failed": 0})
    assert len(output["module_dashboard"]) == 41
    assert output["average_software_readiness"] > output["average_scientific_readiness"]
    assert output["controlled_release_eligible"] is False


def test_reporting_includes_execution_and_isolated_errors() -> None:
    results = {"bbb_permeability": bbb_permeability(DEMO_SMILES["Caffeine"])}
    bundle = build_result_bundle(results, execution_history=[{"status": "completed"}], error_records=[{"message": "isolated"}])
    assert len(bundle["execution_history"]) == 1
    assert len(bundle["error_records"]) == 1
    assert "Recorded executions: 1" in bundle_markdown(results, execution_history=[{"status": "completed"}])
    assert "Execution reliability" in bundle_html(results, error_records=[{"message": "isolated"}])


def test_feature_registry_json_is_valid() -> None:
    from biointel.neuro_cns.data import project_root

    path = project_root() / "data" / "neuro_cns" / "step200_max_potential_feature_registry.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["step"] == 200
    assert payload["step200_control_systems"] == 9
    assert payload["advanced_systems_total"] == 18
