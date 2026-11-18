from pathlib import Path
import json
import tempfile
import zipfile
import pandas as pd

from biointel.universal_platform_v189 import PAGE_TO_MODULES, PLATFORM_DIMENSIONS, PROFILES, TARGET_MODULES, rating_matrix, validate_module
from biointel.universal_platform_v189.generator import module_folder, shared_db
from biointel.universal_platform_v189.platform import (
    DiagnosticCenter, DurableJobQueue, EngineHub, HandoffManager, ProjectRegistry,
    ProvenanceLedger, ReferenceManager, ReviewWorkflow, connect,
)

ROOT=Path(__file__).resolve().parents[1]

def test_step189_exact_scope_and_dimensions():
    assert len(TARGET_MODULES)==80 and len(PROFILES)==80 and len(PAGE_TO_MODULES)==79
    assert len(PLATFORM_DIMENSIONS)==30

def test_step189_all_modules_10_of_10():
    bad={k:validate_module(ROOT,k).blockers for k in TARGET_MODULES if not validate_module(ROOT,k).qualified_10_of_10}
    assert bad=={}

def test_step189_page_hooks_present():
    missing=[]
    for file_name in PAGE_TO_MODULES:
        source=(ROOT/'pages'/file_name).read_text(encoding='utf-8')
        if 'STEP189_UNIVERSAL_PLATFORM_HOOK' not in source:missing.append(file_name)
    assert missing==[]

def test_step189_platform_database_counts_and_integrity():
    db=shared_db(ROOT)
    with connect(db) as conn:
        assert conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0]==80
        assert conn.execute('SELECT COUNT(*) FROM jobs WHERE status="completed"').fetchone()[0]==80
        assert conn.execute('SELECT COUNT(*) FROM handoffs').fetchone()[0]==80
        assert conn.execute('SELECT COUNT(*) FROM provenance').fetchone()[0]>=240
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'

def test_step189_artifacts_reports_and_controls():
    for key in TARGET_MODULES:
        d=module_folder(ROOT,key)
        assert (d/'portable_project.zip').is_file() and zipfile.is_zipfile(d/'portable_project.zip')
        assert (d/'redacted_support_bundle.zip').is_file() and zipfile.is_zipfile(d/'redacted_support_bundle.zip')
        assert (d/'reports/report.pdf').stat().st_size>100
        assert (d/'reports/report.docx').stat().st_size>100
        assert (d/'reports/report_bundle.zip').is_file() and zipfile.is_zipfile(d/'reports/report_bundle.zip')
        negative=pd.read_csv(d/'negative_security_cases.csv')
        perf=pd.read_csv(d/'performance_benchmark.csv')
        assert len(negative)>=6 and negative.passed.all()
        assert set(perf.records)=={250,2500,10000} and perf.status.eq('pass').all()
        assert json.loads((d/'preflight.json').read_text())['decision']=='READY'
        assert json.loads((d/'provenance_verification.json').read_text())['valid'] is True

def test_step189_service_state_machines_in_temp_database(tmp_path):
    db=tmp_path/'platform.sqlite3'
    registry=ProjectRegistry(db);p=registry.create_project('Test','Test',project_id='P1')
    s=registry.add_sample('P1','S1','human','test',{},sample_id='S1')
    f=tmp_path/'asset.csv';f.write_text('record_id,value\nR1,1\n')
    asset=registry.register_asset('P1',TARGET_MODULES[0],f,'input',sample_id=s)
    q=DurableJobQueue(db);job=q.enqueue('P1',TARGET_MODULES[0],'test',{})
    assert q.claim('worker')['job_id']==job
    q.heartbeat(job,.5,{'stage':'half'});q.transition(job,'completed',progress=1,result={'ok':True})
    assert q.get(job)['status']=='completed'
    ledger=ProvenanceLedger(db);ledger.append('P1',TARGET_MODULES[0],'test',{'asset':asset})
    assert ledger.verify('P1')['valid']
    review=ReviewWorkflow(db);review.transition('P1',TARGET_MODULES[0],'a','analyst','in_review','ok');review.transition('P1',TARGET_MODULES[0],'r','reviewer','approved','ok')
    assert review.current_status('P1',TARGET_MODULES[0])=='approved'
    h=HandoffManager(db).create('P1',TARGET_MODULES[0],TARGET_MODULES[1],[asset],{'schema':'test'})
    assert h.startswith('HOF-')

def test_step189_rating_matrix_and_release_boundary():
    frame=rating_matrix(ROOT)
    assert len(frame)==80 and frame.qualified_10_of_10.all()
    assert frame.after_step189_rating.eq(10).all()
    assert frame.dimensions_passed.eq(30).all()
    assert not frame.controlled_release_eligible.any()

def test_step189_central_page_and_windows_launcher():
    assert (ROOT/'pages/259_Step189_Universal_Production_Platform_Center.py').is_file()
    assert (ROOT/'LOAD_STEP189_UNIVERSAL_PLATFORM_WINDOWS.bat').is_file()
