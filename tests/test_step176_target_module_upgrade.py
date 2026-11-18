from __future__ import annotations

from pathlib import Path

from biointel.target_modules_v176 import TARGET_MODULES, TARGET_PROFILES, qualification_matrix, required_engines, required_references

ROOT = Path(__file__).resolve().parents[1]


def test_step176_covers_exactly_17_target_modules() -> None:
    assert len(TARGET_MODULES) == 17
    assert len(set(TARGET_MODULES)) == 17


def test_step176_contracts_are_complete() -> None:
    for key, profile in TARGET_PROFILES.items():
        assert key == profile.module_key
        assert len(profile.workflow) >= 5
        assert len(profile.quality_gates) >= 5
        assert len(profile.required_outputs) >= 5
        assert profile.boundary
        assert (ROOT / profile.page).is_file()
        assert not required_engines(key).empty
        assert not required_references(key).empty


def test_step176_pages_have_fail_closed_upgrade_hook() -> None:
    for key, profile in TARGET_PROFILES.items():
        text = (ROOT / profile.page).read_text(encoding="utf-8-sig")
        assert "render_target_module_upgrade" in text
        assert repr(key) in text or f'"{key}"' in text


def test_step176_internal_upgrade_is_10_without_fake_external_completion() -> None:
    matrix = qualification_matrix(ROOT)
    assert len(matrix) == 17
    assert matrix["internal_upgrade_rating"].eq(10.0).all()
    assert matrix["workflow_contract_complete"].all()
    assert matrix["quality_gate_contract_complete"].all()
    assert matrix["output_contract_complete"].all()
    # External evidence is not inferred merely because the code layer is complete.
    incomplete = matrix[(matrix["engine_discovery_fraction"] < 1.0) | (matrix["reference_qualification_fraction"] < 1.0)]
    assert not incomplete["controlled_release_eligible"].any()
    assert incomplete["decision"].eq("research-only-fail-closed").all()
