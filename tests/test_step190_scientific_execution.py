from pathlib import Path
import json
import zipfile
import pandas as pd

from biointel.scientific_execution_v190 import EXECUTION_DIMENSIONS, PAGE_TO_MODULES, PROFILES, TARGET_MODULES, rating_matrix, validate_module
from biointel.scientific_execution_v190.execution import make_fixture, native_analysis
from biointel.scientific_execution_v190.generator import connect, module_folder, shared_db

ROOT=Path(__file__).resolve().parents[1]

def test_step190_scope_and_dimensions():
    assert len(TARGET_MODULES)==80 and len(PROFILES)==80 and len(PAGE_TO_MODULES)==79
    assert len(EXECUTION_DIMENSIONS)==40

def test_step190_all_modules_10_of_10():
    bad={k:validate_module(ROOT,k).blockers for k in TARGET_MODULES if not validate_module(ROOT,k).qualified_10_of_10}
    assert bad=={}

def test_step190_page_hooks_present():
    missing=[]
    for file_name in PAGE_TO_MODULES:
        source=(ROOT/'pages'/file_name).read_text(encoding='utf-8')
        if 'STEP190_SCIENTIFIC_EXECUTION_HOOK' not in source: missing.append(file_name)
    assert missing==[]

def test_step190_database_and_artifacts():
    with connect(shared_db(ROOT)) as conn:
        assert conn.execute('SELECT COUNT(*) FROM module_runs').fetchone()[0]==80
        assert conn.execute('SELECT COUNT(*) FROM benchmark_metrics').fetchone()[0]==80*8
        assert conn.execute('SELECT COUNT(*) FROM standard_artifacts').fetchone()[0]>=80
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    for key in TARGET_MODULES:
        d=module_folder(ROOT,key)
        assert zipfile.is_zipfile(d/'step190_execution_bundle.zip')
        assert (d/'native_viewer.html').stat().st_size>500
        assert (d/'viewer_snapshot.svg').stat().st_size>100
        assert pd.read_csv(d/'truth_benchmark_metrics.csv').passed.all()
        assert pd.read_csv(d/'streaming_performance.csv').status.eq('pass').all()
        assert len(pd.read_csv(d/'error_recovery_catalogue.csv'))>=10
        assert json.loads((d/'release_boundary.json').read_text())['controlled_release_eligible'] is False

def test_step190_native_execution_all_categories():
    seen=set()
    for key,profile in PROFILES.items():
        if profile.category in seen: continue
        frame=make_fixture(profile,60)
        output,summary=native_analysis(profile,frame)
        assert len(output)==60 and output.prediction_score.between(0,1).all()
        assert summary['f1']>=0.75 and summary['expected_calibration_error']<=0.15
        seen.add(profile.category)
    assert len(seen)>=10

def test_step190_standard_bridges_and_update_impact():
    for key in TARGET_MODULES:
        d=module_folder(ROOT,key)
        manifest=pd.read_csv(d/'standard_formats/format_bridge_manifest.csv')
        assert len(manifest)>=1
        assert (d/'standard_formats/service_info_compatibility.json').is_file()
        assert (d/'standard_formats/provenance.prov.jsonld').is_file()
        impact=json.loads((d/'update_impact_report.json').read_text())
        assert impact['records']>0 and 0<=impact['changed_decision_rate']<=1

def test_step190_rating_matrix():
    frame=rating_matrix(ROOT)
    assert len(frame)==80 and frame.qualified_10_of_10.all()
    assert frame.after_step190_rating.eq(10).all()
    assert frame.dimensions_passed.eq(40).all()
    assert not frame.controlled_release_eligible.any()

def test_step190_central_page_and_launcher():
    assert (ROOT/'pages/260_Step190_Scientific_Execution_Interoperability_Center.py').is_file()
    assert (ROOT/'LOAD_STEP190_SCIENTIFIC_EXECUTION_WINDOWS.bat').is_file()
