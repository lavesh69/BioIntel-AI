from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd

from biointel.external_v172 import ALL_MODULES, PROFILES, Step172Registry, build_step172_assets, profile_matrix
from biointel.scientific_depth.native_workflows import run_native_workflow

ROOT = Path(__file__).resolve().parents[1]


def test_profiles_cover_all_80_modules() -> None:
    frame = profile_matrix()
    assert len(ALL_MODULES) == len(PROFILES) == len(frame) == 80
    assert set(frame["software_framework_score"]) == {10.0}
    assert frame["requires_formal_release_review"].all()
    assert frame["requires_expert_signoff"].all()


def test_assets_and_registry_fail_closed() -> None:
    assets = build_step172_assets(ROOT)
    assert len(assets) >= 801
    registry = Step172Registry(ROOT)
    matrix = registry.matrix(refresh=True)
    assert len(matrix) == 80
    assert not matrix["release_eligible"].any()
    assert set(matrix["decision"]) == {"research-only-fail-closed"}
    status = registry.status()
    assert status["database_integrity"] == "ok"
    assert status["foreign_key_violations"] == 0


def test_flags_without_files_never_unlock_release(tmp_path: Path) -> None:
    root = tmp_path / "project"
    shutil.copytree(ROOT / "src", root / "src")
    registry = Step172Registry(root)
    module_key = "flow_cytometry"
    submission = registry.submissions / module_key
    submission.mkdir(parents=True)
    manifest = {
        "module_key": module_key,
        "protocol": {"path": "missing.pdf", "sha256": "0" * 64, "locked_before_execution": True, "acceptance_thresholds_locked": True, "protocol_id": "P1"},
        "sites": [{"independent": True, "qa_approved": True, "qualification_path": "missing.pdf", "qualification_sha256": "0" * 64}],
        "instruments": [{"serial_number": "X", "qualified": True, "iq_path": "x", "iq_sha256": "0" * 64, "oq_path": "x", "oq_sha256": "0" * 64, "pq_path": "x", "pq_sha256": "0" * 64, "calibration_path": "x", "calibration_sha256": "0" * 64}],
        "confirmations": [{"type": "wet_lab", "acceptance_passed": True, "independent": True, "controls_complete": True, "biological_replicates": 3, "technical_replicates": 3, "sample_count": 20, "evidence_path": "x", "evidence_sha256": "0" * 64, "data_manifest_path": "x", "data_manifest_sha256": "0" * 64}],
        "experts": [{"approved": True, "independent": True}],
        "physical_qualification": {"windows_tested": True, "instrument_tested": True, "recovery_tested": True, "large_file_tested": True, "antivirus_tested": True, "network_loss_tested": True, "sleep_resume_tested": True},
        "operating_history": {"runs": 999, "unresolved_critical_incidents": 0, "drift_review_complete": True},
        "release_review": {"decision": "approved", "quorum": 9, "independent_qa_approval": True, "domain_expert_approval": True, "product_owner_approval": True, "risk_acceptance_documented": True, "intended_use": "controlled"},
    }
    path = submission / "confirmation_manifest.json"
    path.write_text(json.dumps(manifest))
    result = registry.import_submission(module_key, path)
    assert result["release_eligible"] is False
    assert result["blockers"]


def test_native_results_include_step172_gate() -> None:
    frame = pd.DataFrame({"sample_id": ["S1", "S2", "S3", "S4"], "value": [1.0, 2.0, 3.0, 4.0]})
    result = run_native_workflow("flow_cytometry", frame, metadata={"project_root": str(ROOT)})
    assert "step172_external_confirmation_gate" in result.tables
    gate = result.tables["step172_external_confirmation_gate"].iloc[0]
    assert gate["software_framework_score"] == 10.0
    assert not bool(gate["release_eligible"])


def test_release_metadata_and_navigation() -> None:
    release = json.loads((ROOT / "STEP172_RELEASE.json").read_text())
    assert release["version"] == "14.4.0"
    assert (ROOT / "pages" / "241_External_Confirmation_Formal_Release.py").exists()
    navigation = (ROOT / "src" / "biointel" / "ui" / "navigation.py").read_text()
    assert "external_confirmation_formal_release" in navigation
