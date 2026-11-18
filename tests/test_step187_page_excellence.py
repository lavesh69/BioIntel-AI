from pathlib import Path
import json
import pandas as pd
from biointel.page_excellence_v187 import ASSURANCE_DIMENSIONS,DEEP_TARGETS,TARGET_PAGES,TARGET_PROFILES,step187_rating_matrix,validate_step187_page
ROOT=Path(__file__).resolve().parents[1]
def test_step187_exact_target_scope():
    assert len(TARGET_PAGES)==177 and len(TARGET_PROFILES)==177 and len(DEEP_TARGETS)==10
def test_step187_all_pages_10_of_10():
    bad={f:validate_step187_page(ROOT,f).blockers for f in TARGET_PAGES if not validate_step187_page(ROOT,f).qualified_10_of_10};assert bad=={}
def test_step187_dimensions_complete():
    assert len(ASSURANCE_DIMENSIONS)==16
    for f in TARGET_PAGES:
        r=validate_step187_page(ROOT,f);m=json.loads((Path(r.path)/'assurance_manifest.json').read_text());assert tuple(x['dimension'] for x in m['dimensions'])==ASSURANCE_DIMENSIONS and all(x['passed'] for x in m['dimensions'])
def test_step187_pages_have_hooks():
    assert [f for f in TARGET_PAGES if 'STEP187_PAGE_EXCELLENCE_HOOK' not in (ROOT/'pages'/f).read_text(encoding='utf-8')]==[]
def test_step187_artifacts_and_performance():
    for f in TARGET_PAGES:
        d=Path(validate_step187_page(ROOT,f).path);perf=pd.read_csv(d/'performance_benchmark.csv');neg=pd.read_csv(d/'negative_security_cases.csv');rep=pd.read_csv(d/'repeatability.csv')
        assert set(perf.records)=={250,2500,10000} and perf.status.eq('pass').all() and len(neg)>=15 and neg.passed.all() and len(rep)==3 and rep.passed.all()
def test_step187_category_averages_are_10():
    f=step187_rating_matrix(ROOT);assert len(f)==177 and f.qualified_10_of_10.all() and f.after_step187_rating.eq(10).all() and f.groupby('category').after_step187_rating.mean().eq(10).all()
def test_step187_all_256_pages_are_10():
    f=pd.read_csv(ROOT/'STEP187_ALL_256_PAGE_FINAL_RATINGS.csv');assert len(f)==256 and f.step187_final_internal_demo_rating.eq(10).all() and int(f.step187_upgraded.sum())==177
