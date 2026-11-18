from pathlib import Path
import json
import pandas as pd
from biointel.major_module_standard_v188 import (
    COMPULSORY_DIMENSIONS, PAGE_TO_MODULES, PROFILES, STANDARD_TABS, TARGET_MODULES,
    step188_rating_matrix, validate_module,
)
ROOT=Path(__file__).resolve().parents[1]

def test_step188_exact_scope():
    assert len(TARGET_MODULES)==80 and len(PROFILES)==80 and len(PAGE_TO_MODULES)==79
    assert len(STANDARD_TABS)==12 and len(COMPULSORY_DIMENSIONS)==20

def test_step188_all_modules_10_of_10():
    bad={k:validate_module(ROOT,k).blockers for k in TARGET_MODULES if not validate_module(ROOT,k).qualified_10_of_10}
    assert bad=={}

def test_step188_dimensions_and_tabs_complete():
    for key in TARGET_MODULES:
        r=validate_module(ROOT,key)
        d=Path(r.path)
        q=json.loads((d/'qualification_manifest.json').read_text())
        t=json.loads((d/'tab_contract.json').read_text())
        assert tuple(x['dimension'] for x in q['dimensions'])==COMPULSORY_DIMENSIONS
        assert all(x['passed'] for x in q['dimensions'])
        assert tuple(t['tabs'])==STANDARD_TABS

def test_step188_page_hooks_present():
    missing=[]
    for file_name in PAGE_TO_MODULES:
        source=(ROOT/'pages'/file_name).read_text(encoding='utf-8')
        if 'STEP188_MAJOR_MODULE_STANDARD_HOOK' not in source:missing.append(file_name)
    assert missing==[]

def test_step188_artifacts_and_execution_contracts():
    for key in TARGET_MODULES:
        d=Path(validate_module(ROOT,key).path)
        negative=pd.read_csv(d/'negative_security_cases.csv')
        performance=pd.read_csv(d/'performance_benchmark.csv')
        repeatability=pd.read_csv(d/'repeatability.csv')
        visuals=pd.read_csv(d/'visual_catalog.csv')
        assert len(negative)>=14 and negative.passed.all()
        assert set(performance.records)=={250,2500,10000} and performance.status.eq('pass').all()
        assert len(repeatability)==3 and repeatability.passed.all() and repeatability.output_sha256.nunique()==1
        assert len(visuals)>=6 and visuals.available.all()

def test_step188_rating_matrix_complete():
    frame=step188_rating_matrix(ROOT)
    assert len(frame)==80 and frame.qualified_10_of_10.all()
    assert frame.after_step188_rating.eq(10).all()
    assert frame.dimensions_passed.eq(20).all() and frame.tabs_passed.eq(12).all()
    assert not frame.controlled_release_eligible.any()

def test_step188_central_page_and_windows_launcher():
    assert (ROOT/'pages/258_Step188_Universal_Major_Module_Standard_Center.py').is_file()
    assert (ROOT/'LOAD_STEP188_MAJOR_MODULE_STANDARD_WINDOWS.bat').is_file()
