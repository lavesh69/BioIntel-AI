from pathlib import Path
import json
import pandas as pd
from biointel.operational_assurance_v185 import ASSURANCE_DIMENSIONS,TARGET_MODULES,TARGET_PROFILES,step185_rating_matrix,validate_step185_module
ROOT=Path(__file__).resolve().parents[1]
def test_step185_has_exactly_19_modules():
    assert len(TARGET_MODULES)==19 and len(TARGET_PROFILES)==19 and len(set(TARGET_MODULES))==19
    assert all(8.0<=p.before_demo_rating<9.0 for p in TARGET_PROFILES.values())
def test_step185_all_modules_are_10_of_10():
    failures={k:validate_step185_module(ROOT,k).blockers for k in TARGET_MODULES if not validate_step185_module(ROOT,k).qualified_10_of_10}
    assert failures=={}
def test_step185_dimensions_complete():
    assert len(ASSURANCE_DIMENSIONS)==12
    for k in TARGET_MODULES:
        m=json.loads((ROOT/"UserData/step185/operational_assurance"/k/"assurance_manifest.json").read_text())
        assert tuple(x["dimension"] for x in m["dimensions"])==ASSURANCE_DIMENSIONS and all(x["passed"] for x in m["dimensions"])
def test_step185_ratings_improve_without_faking_evidence():
    f=step185_rating_matrix(ROOT); assert len(f)==19 and f.qualified_10_of_10.all() and (f.after_operational_assurance_rating==10.0).all() and (f.after_operational_assurance_rating>f.before_demo_rating).all() and not f.real_external_rating_changed.any() and not f.controlled_release_eligible.any()
def test_step185_target_pages_have_hook():
    missing=[]
    for k,p in TARGET_PROFILES.items():
        t=(ROOT/p.page).read_text(encoding="utf-8")
        if f'_render_step185_operational_assurance("{k}"' not in t: missing.append((k,p.page))
    assert missing==[]
def test_step185_operational_artifacts_pass():
    for k in TARGET_MODULES:
        folder=ROOT/"UserData/step185/operational_assurance"/k
        perf=pd.read_csv(folder/"performance_benchmark.csv"); sub=pd.read_csv(folder/"subgroup_validation.csv"); drift=pd.read_csv(folder/"drift_monitoring.csv")
        assert set(perf.records)=={250,2500,10000} and (perf.status=="pass").all() and len(sub)>=1 and not drift.alert.any()
def test_step185_full_portfolio_has_no_8xx_modules():
    f=pd.read_csv(ROOT/"STEP185_80_MODULE_FINAL_DEMO_RATINGS.csv"); assert len(f)==80 and not ((f.step185_final_demo_rating>=8)&(f.step185_final_demo_rating<9)).any()
