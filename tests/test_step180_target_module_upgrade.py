from pathlib import Path

from biointel.target_modules_v180 import (
    TARGET_MODULES,
    TARGET_PROFILES,
    clr_transform,
    compositional_closure,
    kmer_jaccard,
    morans_i,
    pose_rmsd,
    protein_sequence_valid,
    qualification_matrix,
    required_cohorts,
    required_components,
    required_models,
    required_references,
    run_contract_smoke,
    split_is_leakage_free,
    steric_clash_free,
    z_prime,
)

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BASELINES = {
    "phenotypic_screening": 4.36,
    "spatial_omics_pathology": 4.25,
    "protein_language_design": 3.50,
    "protein_ligand_codesign": 3.50,
    "strain_microbiome": 3.50,
}


def test_step180_exact_final_five_modules():
    assert tuple(TARGET_MODULES) == tuple(EXPECTED_BASELINES)
    assert len(TARGET_MODULES) == 5 and len(set(TARGET_MODULES)) == 5


def test_step180_complete_scientific_contracts():
    for key, profile in TARGET_PROFILES.items():
        assert key == profile.module_key
        assert len(profile.workflow) >= 6
        assert len(profile.data_gates) >= 6
        assert len(profile.model_gates) >= 6
        assert len(profile.scientific_gates) >= 7
        assert len(profile.acceptance_criteria) >= 6
        assert len(profile.required_outputs) >= 6
        assert len(profile.risk_controls) >= 6
        assert len(profile.monitoring_metrics) >= 5
        assert len(profile.validation_fixtures) >= 5
        assert len(profile.governance_assets) >= 3
        assert profile.boundary
        assert (ROOT / profile.page).is_file()
        assert not required_components(key).empty
        assert not required_references(key).empty
        assert not required_models(key).empty
        assert not required_cohorts(key).empty


def test_step180_pages_hooked():
    for key, profile in TARGET_PROFILES.items():
        text = (ROOT / profile.page).read_text(encoding="utf-8-sig")
        assert "render_step180_module_upgrade" in text
        assert key in text


def test_step180_module_specific_scientific_math():
    assert z_prime([98, 100, 102, 99], [8, 10, 12, 9]) >= 0.5
    assert split_is_leakage_free({"train": ["A", "B"], "test": ["C"]})
    assert not split_is_leakage_free({"train": ["A", "B"], "test": ["B"]})
    assert -1.5 <= morans_i([1, 1.2, 4, 4.2], [(0, 1), (1, 0), (1, 2), (2, 1), (2, 3), (3, 2)]) <= 1.5
    assert protein_sequence_valid("MKTAYIAKQRQISFVKSHFSRQLEER")
    assert not protein_sequence_valid("MKTAX***")
    assert kmer_jaccard("MKTAYIAKQRQ", "GAVLILKKKGH") < 0.5
    assert pose_rmsd([(0, 0, 0), (1, 0, 0)], [(0.1, 0, 0), (1.1, 0, 0)]) < 0.2
    assert steric_clash_free([(5, 5, 5)], [(0, 0, 0)])
    assert compositional_closure([0.5, 0.3, 0.2])
    assert abs(sum(clr_transform([50, 30, 20]))) < 1e-10


def test_step180_deterministic_scientific_smoke():
    for key in TARGET_MODULES:
        checks = run_contract_smoke(key)
        assert len(checks) >= 17
        assert all(checks.values())


def test_step180_internal_10of10_and_external_fail_closed():
    frame = qualification_matrix(ROOT)
    assert len(frame) == 5
    assert frame.internal_after_rating.eq(10.0).all()
    assert dict(zip(frame.module_key, frame.baseline_rating)) == EXPECTED_BASELINES
    expected_improvements = {key: round(10.0 - value, 2) for key, value in EXPECTED_BASELINES.items()}
    assert dict(zip(frame.module_key, frame.rating_improvement)) == expected_improvements
    contract_columns = [
        "workflow_contract_complete",
        "data_contract_complete",
        "model_contract_complete",
        "scientific_contract_complete",
        "acceptance_contract_complete",
        "output_contract_complete",
        "risk_contract_complete",
        "monitoring_contract_complete",
        "ui_hook_present",
        "component_plan_complete",
        "reference_plan_complete",
        "model_plan_complete",
        "cohort_plan_complete",
        "fixture_plan_complete",
        "governance_plan_complete",
        "deterministic_scientific_smoke_passed",
    ]
    for column in contract_columns:
        assert frame[column].all()
    incomplete = frame[
        (frame.component_qualification_fraction < 1)
        | (frame.reference_qualification_fraction < 1)
        | (frame.model_qualification_fraction < 1)
        | (frame.cohort_qualification_fraction < 1)
        | (frame.fixture_qualification_fraction < 1)
        | (frame.governance_qualification_fraction < 1)
        | (frame.external_evidence_fraction < 1)
    ]
    assert not incomplete.controlled_release_eligible.any()
    assert incomplete.decision.eq("internal-10of10-external-fail-closed").all()


def test_step180_classic_windows_flow_and_asset_index():
    assert (ROOT / "INSTALL_WINDOWS.bat").is_file()
    assert (ROOT / "RUN_BOTH_WINDOWS.bat").is_file()
    assert (ROOT / "BUILD_STEP180_TARGET_MODULE_ASSETS_WINDOWS.bat").is_file()
    assert (ROOT / "VERIFY_STEP180_TARGET_MODULES_WINDOWS.bat").is_file()
    assert (ROOT / "PROVISION_STEP180_TARGET_MODULES_WINDOWS.bat").is_file()
    assert (ROOT / "data/step180/asset_index.json").is_file()
