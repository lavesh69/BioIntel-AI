from pathlib import Path
from biointel.target_modules_v178 import TARGET_MODULES,TARGET_PROFILES,qualification_matrix,required_engines,required_references
ROOT=Path(__file__).resolve().parents[1]
def test_step178_exact_19_modules():assert len(TARGET_MODULES)==19 and len(set(TARGET_MODULES))==19
def test_step178_complete_contracts():
    for key,p in TARGET_PROFILES.items():
        assert key==p.module_key and len(p.workflow)>=6 and len(p.quality_gates)>=8 and len(p.acceptance_criteria)>=6 and len(p.required_outputs)>=6 and len(p.risk_controls)>=5 and len(p.monitoring_metrics)>=4 and p.boundary
        assert len(p.model_assets)>=2 and len(p.cohort_assets)>=2 and len(p.governance_assets)>=3 and (ROOT/p.page).is_file() and not required_engines(key).empty and not required_references(key).empty
def test_step178_pages_hooked():
    for key,p in TARGET_PROFILES.items():
        text=(ROOT/p.page).read_text(encoding='utf-8-sig');assert 'render_step178_module_upgrade' in text and key in text
def test_step178_internal_10_fail_closed():
    frame=qualification_matrix(ROOT);assert len(frame)==19 and frame.internal_after_rating.eq(10).all();assert frame.rating_improvement.gt(0).all()
    for c in ['workflow_contract_complete','quality_gate_contract_complete','acceptance_contract_complete','output_contract_complete','risk_contract_complete','monitoring_contract_complete','engine_plan_complete','reference_plan_complete','model_plan_complete','cohort_plan_complete','governance_plan_complete']:assert frame[c].all()
    incomplete=frame[(frame.engine_qualification_fraction<1)|(frame.reference_qualification_fraction<1)|(frame.model_qualification_fraction<1)|(frame.cohort_qualification_fraction<1)|(frame.governance_qualification_fraction<1)|(frame.external_evidence_fraction<1)]
    assert not incomplete.controlled_release_eligible.any() and incomplete.decision.eq('research-only-fail-closed').all()
def test_step178_classic_flow_preserved():assert (ROOT/'INSTALL_WINDOWS.bat').is_file() and (ROOT/'RUN_BOTH_WINDOWS.bat').is_file()
def test_step178_asset_index_built():assert (ROOT/'data/step178/asset_index.json').is_file()
