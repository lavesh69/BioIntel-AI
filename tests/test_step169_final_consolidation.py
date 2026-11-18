from __future__ import annotations

import json
from pathlib import Path

from biointel.final_v169 import (
    AXES,
    ensure_step169_assets,
    final_consolidation_matrix,
    record_operating_metrics,
    record_release_decision,
    register_evidence_artifact,
    verified_release_state,
)
from biointel.scientific_depth import native_input_template, run_native_workflow
from biointel.scientific_depth.profiles import MODULE_PROFILES

ROOT = Path(__file__).resolve().parents[1]


def test_step169_assets_matrix_and_version_consistency():
    written = ensure_step169_assets(ROOT)
    matrix = final_consolidation_matrix(ROOT)
    assert len(written) == 80
    assert len(matrix) == 80
    assert (matrix.internal_software_rating == 10).all()
    assert (matrix.native_research_depth_rating == 10).all()
    current_version = (ROOT / "VERSION").read_text().strip()
    from biointel import __version__
    assert __version__ == current_version
    assert json.loads((ROOT / "platform/desktop/package.json").read_text())["version"] == current_version
    assert json.loads((ROOT / "platform/mobile/package.json").read_text())["version"] == current_version
    assert tuple(int(part) for part in current_version.split(".")) >= (14, 1, 0)
    assert json.loads((ROOT / "STEP169_RELEASE.json").read_text())["version"] == "14.1.0"
    from biointel.ui.navigation import PAGE_BY_KEY
    assert PAGE_BY_KEY["final_consolidation_10of10_center"].path == "pages/238_Final_Consolidation_10of10_Center.py"


def test_step169_all_80_demo_runs_are_consolidated_and_fail_closed():
    for key in sorted(MODULE_PROFILES):
        result = run_native_workflow(key, native_input_template(key, demonstration=True), metadata={"project_root": str(ROOT)})
        gate = result.tables["step169_final_consolidated_quality_gate"].iloc[0]
        assert float(gate.internal_software_score) == 10.0
        assert bool(gate.result_schema_safe)
        assert not bool(gate.controlled_release_eligible)
        assert result.summary["step169_final_consolidation_score"] == 10.0
        assert result.provenance["step169_product_version"] == "14.1.0"


def test_step169_metadata_flags_cannot_unlock_release():
    key = "benchmark_validation_v2"
    metadata = {
        "project_root": str(ROOT),
        "production_references_qualified": True,
        "independent_validation_complete": True,
        "prospective_or_orthogonal_validation_complete": True,
        "domain_expert_signoff_complete": True,
        "formal_release_review_complete": True,
        "real_world_operating_history_complete": True,
        "physical_platform_qualification_complete": True,
    }
    result = run_native_workflow(key, native_input_template(key, demonstration=True), metadata=metadata)
    gate = result.tables["step169_final_consolidated_quality_gate"].iloc[0]
    assert not bool(gate.controlled_release_eligible)
    assert gate.release_status == "research-only-fail-closed"


def test_step169_checksum_tamper_detection_and_verified_unlock(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    ensure_step169_assets(root)
    key = "benchmark_validation_v2"
    evidence_dir = root / "evidence"
    evidence_dir.mkdir()
    for axis in AXES:
        path = evidence_dir / f"{axis}.json"
        path.write_text(json.dumps({"axis": axis, "issuer": "independent-test-fixture"}), encoding="utf-8")
        register_evidence_artifact(root, module_key=key, axis=axis, artifact_path=path, issuer="independent-test-fixture", identifier=f"TEST-{axis}")
    record_operating_metrics(
        root,
        module_key=key,
        completed_runs=100,
        failed_runs=1,
        downtime_minutes=30,
        observed_days=90,
        incident_log_attached=True,
        capa_log_attached=True,
    )
    decision = root / "evidence" / "decision.json"
    decision.write_text(json.dumps({"decision": "controlled-release", "reviewer": "Test Reviewer"}), encoding="utf-8")
    record_release_decision(root, module_key=key, decision="controlled-release", intended_use="test-only", reviewer="Test Reviewer", decision_artifact_path=decision)
    state = verified_release_state(root, key)
    assert state.controlled_release_eligible
    (evidence_dir / "production_reference.json").write_text("tampered", encoding="utf-8")
    state = verified_release_state(root, key)
    assert not state.controlled_release_eligible
    assert state.artifact_integrity_failures == 1
