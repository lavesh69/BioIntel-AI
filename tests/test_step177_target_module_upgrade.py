from pathlib import Path
from biointel.target_modules_v177 import TARGET_MODULES,TARGET_PROFILES,qualification_matrix,required_engines,required_references
ROOT=Path(__file__).resolve().parents[1]
def test_step177_exact_21_modules():assert len(TARGET_MODULES)==21 and len(set(TARGET_MODULES))==21
def test_step177_complete_contracts():
    for k,p in TARGET_PROFILES.items():
        assert k==p.module_key and len(p.workflow)>=5 and len(p.quality_gates)>=6 and len(p.required_outputs)>=5 and p.boundary
        assert len(p.model_assets)>=2 and len(p.cohort_assets)>=2 and (ROOT/p.page).is_file() and not required_engines(k).empty and not required_references(k).empty
def test_step177_pages_hooked():
    for k,p in TARGET_PROFILES.items():
        t=(ROOT/p.page).read_text(encoding='utf-8-sig');assert 'render_step177_module_upgrade' in t and k in t
def test_step177_internal_10_fail_closed():
    m=qualification_matrix(ROOT);assert len(m)==21 and m.internal_upgrade_rating.eq(10).all();assert m.workflow_contract_complete.all() and m.quality_gate_contract_complete.all() and m.output_contract_complete.all();assert m.engine_plan_complete.all() and m.reference_plan_complete.all() and m.model_plan_complete.all() and m.cohort_plan_complete.all();incomplete=m[(m.engine_qualification_fraction<1)|(m.reference_qualification_fraction<1)|(m.model_qualification_fraction<1)|(m.cohort_qualification_fraction<1)|(m.external_evidence_fraction<1)];assert not incomplete.controlled_release_eligible.any() and incomplete.decision.eq('research-only-fail-closed').all()
def test_step177_classic_flow_preserved():assert (ROOT/'INSTALL_WINDOWS.bat').is_file() and (ROOT/'RUN_BOTH_WINDOWS.bat').is_file()
