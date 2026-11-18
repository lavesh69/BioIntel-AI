from pathlib import Path
from biointel.target_modules_v179 import TARGET_MODULES,TARGET_PROFILES,qualification_matrix,required_components,required_references,run_contract_smoke
ROOT=Path(__file__).resolve().parents[1]
def test_step179_exact_18_modules():assert len(TARGET_MODULES)==18 and len(set(TARGET_MODULES))==18
def test_step179_complete_contracts():
    for key,p in TARGET_PROFILES.items():
        assert key==p.module_key and len(p.workflow)>=6 and len(p.reliability_gates)>=8 and len(p.security_gates)>=6 and len(p.acceptance_criteria)>=6 and len(p.required_outputs)>=6 and len(p.risk_controls)>=5 and len(p.monitoring_metrics)>=4 and p.boundary
        assert len(p.validation_fixtures)>=3 and len(p.governance_assets)>=3 and (ROOT/p.page).is_file() and not required_components(key).empty and not required_references(key).empty
def test_step179_pages_hooked():
    for key,p in TARGET_PROFILES.items():
        text=(ROOT/p.page).read_text(encoding='utf-8-sig');assert 'render_step179_module_upgrade' in text and key in text
def test_step179_deterministic_smoke():
    for key in TARGET_MODULES:
        checks=run_contract_smoke(key);assert len(checks)>=11 and all(checks.values())
def test_step179_internal_10_fail_closed():
    frame=qualification_matrix(ROOT);assert len(frame)==18 and frame.internal_after_rating.eq(10).all() and frame.rating_improvement.eq(2.5).all()
    for c in ['workflow_contract_complete','reliability_contract_complete','security_contract_complete','acceptance_contract_complete','output_contract_complete','risk_contract_complete','monitoring_contract_complete','ui_hook_present','component_plan_complete','reference_plan_complete','fixture_plan_complete','governance_plan_complete','deterministic_smoke_passed']:assert frame[c].all()
    incomplete=frame[(frame.component_qualification_fraction<1)|(frame.reference_qualification_fraction<1)|(frame.fixture_qualification_fraction<1)|(frame.governance_qualification_fraction<1)|(frame.external_evidence_fraction<1)]
    assert not incomplete.controlled_release_eligible.any() and incomplete.decision.eq('internal-10of10-external-fail-closed').all()
def test_step179_classic_flow_and_asset_index():
    assert (ROOT/'INSTALL_WINDOWS.bat').is_file() and (ROOT/'RUN_BOTH_WINDOWS.bat').is_file() and (ROOT/'data/step179/asset_index.json').is_file()
