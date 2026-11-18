from pathlib import Path
import json
import pandas as pd
from biointel.platform_completion_v186 import ASSURANCE_DIMENSIONS,TARGET_MODULES,TARGET_PROFILES,step186_rating_matrix,validate_step186_module
ROOT=Path(__file__).resolve().parents[1]
def test_step186_exactly_18_platform_modules():
    assert len(TARGET_MODULES)==18 and len(TARGET_PROFILES)==18 and all(p.before_demo_rating==9.0 for p in TARGET_PROFILES.values())
def test_step186_all_modules_10_of_10():
    assert {k:validate_step186_module(ROOT,k).blockers for k in TARGET_MODULES if not validate_step186_module(ROOT,k).qualified_10_of_10}=={}
def test_step186_dimensions_complete():
    assert len(ASSURANCE_DIMENSIONS)==15
    for k in TARGET_MODULES:
        m=json.loads((ROOT/'UserData/step186/platform_completion'/k/'assurance_manifest.json').read_text())
        assert tuple(x['dimension'] for x in m['dimensions'])==ASSURANCE_DIMENSIONS and all(x['passed'] for x in m['dimensions'])
def test_step186_ratings_and_boundaries():
    f=step186_rating_matrix(ROOT);assert len(f)==18 and f.qualified_10_of_10.all() and (f.after_platform_completion_rating==10).all() and (f.improvement_points==1).all() and not f.real_external_rating_changed.any() and not f.controlled_release_eligible.any()
def test_step186_pages_have_hooks():
    missing=[]
    for k,p in TARGET_PROFILES.items():
        if f'_render_step186_platform_completion("{k}"' not in (ROOT/p.page).read_text(encoding='utf-8'):missing.append(k)
    assert missing==[]
def test_step186_artifacts_and_performance():
    for k in TARGET_MODULES:
        d=ROOT/'UserData/step186/platform_completion'/k;perf=pd.read_csv(d/'performance_benchmark.csv');neg=pd.read_csv(d/'negative_cases.csv')
        assert set(perf.records)=={500,5000,20000} and (perf.status=='pass').all() and len(neg)>=12 and neg.passed.all()
def test_step186_full_portfolio_is_80_of_80_at_10():
    f=pd.read_csv(ROOT/'STEP186_80_MODULE_FINAL_DEMO_RATINGS.csv');assert len(f)==80 and (f.step186_final_demo_rating==10).all() and int(f.step186_upgraded.sum())==18
