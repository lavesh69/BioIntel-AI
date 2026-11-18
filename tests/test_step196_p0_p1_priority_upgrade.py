from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re

from biointel.proof_gates_v10.catalog import (
    EXECUTION_KEY_ALIASES,
    GATE_ORDER,
    P0_MODULE_KEYS,
    P1_MODULE_KEYS,
    PRIORITY_MODULES,
    canonical_execution_key,
)
from biointel.proof_gates_v10.functional import (
    execution_portfolio_rows,
    module_execution_contract,
    prepare_functional_workspaces,
    run_execution_preflight,
)
from biointel.proof_gates_v10.registry import PriorityEvidenceRegistry


ROOT = Path(__file__).resolve().parents[1]


def test_priority_portfolio_has_the_required_25_p0_and_37_p1_modules() -> None:
    assert len(P0_MODULE_KEYS) == 25
    assert len(P1_MODULE_KEYS) == 37
    assert len(PRIORITY_MODULES) == 62
    assert not (set(P0_MODULE_KEYS) & set(P1_MODULE_KEYS))


def test_all_priority_modules_have_one_embedded_evidence_workbench() -> None:
    hooks: dict[str, list[Path]] = {}
    pattern = re.compile(
        r"_render_step196_p0_p1_priority_workbench\(ROOT, ['\"](?P<key>[a-z0-9_]+)['\"], expanded=False\)"
    )
    for page in (ROOT / "pages").glob("*.py"):
        for match in pattern.finditer(page.read_text(encoding="utf-8")):
            hooks.setdefault(match.group("key"), []).append(page)
    assert set(hooks) == set(PRIORITY_MODULES)
    assert all(len(paths) == 1 for paths in hooks.values())

    for name in (
        "242_Final_All_Module_10of10_Command_Center.py",
        "243_Phase_1_to_9_Real_World_Qualification_Execution.py",
    ):
        source = (ROOT / "pages" / name).read_text(encoding="utf-8")
        assert "render_priority_upgrade_center" in source
        assert "P0/P1 priority upgrades" in source


def test_local_evidence_staging_is_hashed_audited_and_never_auto_releases(tmp_path: Path) -> None:
    registry = PriorityEvidenceRegistry(tmp_path)
    module_key = "protein_language_design"
    for gate in GATE_ORDER:
        record = registry.stage_stream(
            module_key,
            gate,
            BytesIO(f"authentic artifact for {gate}".encode("utf-8")),
            original_name=f"{gate}.txt",
            source_reference="protocol-42",
            reviewer="responsible-reviewer",
            evidence_class="authentic",
            review_status="review-ready",
        )
        assert len(record["sha256"]) == 64
        assert (tmp_path / "UserData" / "proof_gates_v10" / record["stored_relative_path"]).exists()
        assert record["qualification_effect"] == "none"

    manifest = registry.write_gate_manifest(
        module_key,
        GATE_ORDER[0],
        reviewer="responsible-reviewer",
        source_reference="protocol-42",
    )
    assert len(manifest["sha256"]) == 64

    result = registry.verify_module(module_key)
    assert result["candidate_for_manual_review"] is True
    assert result["controlled_release"] == "not-automated"
    assert result["rating_promotion"] == "not-automated"
    assert registry.status()["audit_chain_valid"] is True


def test_demo_or_synthetic_evidence_never_satisfies_a_gate(tmp_path: Path) -> None:
    registry = PriorityEvidenceRegistry(tmp_path)
    registry.stage_stream(
        "protein_language_design",
        GATE_ORDER[0],
        BytesIO(b"synthetic demo"),
        original_name="demo.txt",
        source_reference="demo-record",
        reviewer="reviewer",
        evidence_class="synthetic",
        review_status="review-ready",
    )
    result = registry.verify_module("protein_language_design")
    first_gate = result["gates"][0]
    assert first_gate["candidate_count"] == 0
    assert first_gate["rejected_evidence_count"] == 1
    assert first_gate["state"] == "blocked"
    assert result["candidate_for_manual_review"] is False


def test_priority_execution_aliases_preserve_page_identity_and_canonical_runtime_identity() -> None:
    assert EXECUTION_KEY_ALIASES == {
        "model_registry_ml_lifecycle": "model_registry_v2",
        "multiomics_biomarker_discovery": "multiomics_biomarker_core",
        "causal_inference_perturbation": "causal_perturbation",
        "clinical_pharma_validation": "clinical_pharma_core",
        "autonomous_laboratory_planner": "autonomous_lab_planner",
        "pharmacovigilance": "pharmacovigilance_intelligence",
        "synthetic_biology_circuit": "synthetic_biology_core",
    }
    for key in PRIORITY_MODULES:
        assert canonical_execution_key(key) == EXECUTION_KEY_ALIASES.get(key, key)


def test_all_priority_modules_have_one_functional_execution_route() -> None:
    contracts = [module_execution_contract(ROOT, key) for key in PRIORITY_MODULES]
    assert len(contracts) == 62
    assert all(contract["page_exists"] for contract in contracts)
    assert all(contract["priority_hook_bound"] for contract in contracts)
    assert {contract["adapter"] for contract in contracts} == {
        "native_pipeline",
        "nextgen_workbench",
        "expansion_workbench",
        "dedicated_workbench",
    }
    assert sum(contract["adapter"] == "native_pipeline" for contract in contracts) == 15
    assert all(contract["controlled_release_approved"] is False for contract in contracts)
    assert all(contract["rating_promotion"] == "not-automated" for contract in contracts)


def test_functional_workspace_input_and_preflight_are_hashed_audited_and_fail_closed(tmp_path: Path) -> None:
    registry = PriorityEvidenceRegistry(tmp_path)
    module_key = "phenotypic_screening"
    written = prepare_functional_workspaces(ROOT, module_key, registry=registry)
    workspace = tmp_path / "UserData" / "proof_gates_v10" / "functional_workspaces" / module_key
    assert workspace.is_dir()
    assert (workspace / "execution_contract.json").is_file()
    assert (workspace / "input" / "README.md").is_file()
    assert written

    staged = registry.stage_execution_input(
        module_key,
        BytesIO(b"authorised local input"),
        original_name="study_input.csv",
        source_reference="protocol-43",
        notes="genuine user-supplied source",
        expected_size_bytes=len(b"authorised local input"),
    )
    assert len(staged["sha256"]) == 64
    assert (tmp_path / "UserData" / "proof_gates_v10" / staged["stored_relative_path"]).is_file()
    assert staged["qualification_effect"] == "none"

    preflight = run_execution_preflight(ROOT, module_key, registry=registry)
    assert preflight["status"] == "ready-for-local-execution-input-staged"
    assert preflight["record"]["qualification_effect"] == "none"
    assert (tmp_path / "UserData" / "proof_gates_v10" / preflight["record"]["stored_relative_path"]).is_file()
    assert registry.status()["execution_input_count"] == 1
    assert registry.status()["execution_record_count"] >= 2
    assert registry.audit_chain_valid() is True

    portfolio = execution_portfolio_rows(ROOT, registry)
    row = next(item for item in portfolio if item["Module key"] == module_key)
    assert row["Staged inputs"] == 1
    assert row["Controlled release"] == "Not automated"
