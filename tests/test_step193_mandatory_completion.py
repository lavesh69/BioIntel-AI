from __future__ import annotations
import json
from pathlib import Path
import sqlite3
from biointel.mandatory_completion_v193 import MANDATORY_DIMENSIONS, PAGE_TO_MODULES, PROFILES, TARGET_MODULES, database_path, rating_matrix, validate_module
ROOT=Path(__file__).resolve().parents[1]

def test_step193_scope():
    assert len(TARGET_MODULES)==80
    assert len(PROFILES)==80
    assert len(PAGE_TO_MODULES)==79
    assert len(MANDATORY_DIMENSIONS)==24

def test_step193_all_modules_qualified():
    bad={k:validate_module(ROOT,k).blockers for k in TARGET_MODULES if not validate_module(ROOT,k).qualified}
    assert bad=={}

def test_step193_rating_matrix():
    frame=rating_matrix(ROOT)
    assert len(frame)==80
    assert frame.qualified.all()
    assert frame.after_step193_rating.eq(10.0).all()
    assert frame.checks_passed.eq(24).all()
    assert not frame.controlled_release_eligible.any()

def test_step193_page_hooks():
    missing=[]
    for page in PAGE_TO_MODULES:
        text=(ROOT/'pages'/page).read_text(encoding='utf-8-sig')
        if 'STEP193_MANDATORY_COMPLETION_HOOK' not in text: missing.append(page)
    assert missing==[]

def test_step193_contract_files_and_fail_closed():
    for key in TARGET_MODULES:
        q=validate_module(ROOT,key)
        folder=Path(q.path)
        manifest=json.loads((folder/'qualification_manifest.json').read_text())
        assert tuple(x['dimension'] for x in manifest['dimensions'])==MANDATORY_DIMENSIONS
        assert all(x['passed'] for x in manifest['dimensions'])
        assert manifest['controlled_release_eligible'] is False
        assert json.loads((folder/'autosave_recovery.json').read_text())['atomic_write'] is True
        assert json.loads((folder/'confidence_and_release.json').read_text())['fail_closed'] is True

def test_step193_database_integrity_and_counts():
    path=database_path(ROOT)
    conn=sqlite3.connect(path)
    assert conn.execute('pragma integrity_check').fetchone()[0]=='ok'
    assert conn.execute('select count(*) from module_status').fetchone()[0]==80
    assert conn.execute('select count(*) from autosave_snapshots').fetchone()[0]==80
    assert conn.execute('select count(*) from audit_events').fetchone()[0]==80
    assert conn.execute('select count(*) from migration_events').fetchone()[0]==80
    conn.close()

def test_step193_installer_contract_bug_fixed():
    helper=(ROOT/'scripts/install_windows_step193.py').read_text()
    selftest=(ROOT/'scripts/step193_self_test.py').read_text()
    install=(ROOT/'INSTALL_WINDOWS.bat').read_text()
    assert '--allow-degraded' in helper
    assert "--allow-degraded" in selftest
    assert 'find_python311_windows.ps1' in install
    assert ('step193_part%%P.ok' in install or 'step196_part%%P.ok' in install)
    assert ('install_windows_step193.py' in install or 'install_windows_step196.py' in install)

def test_step193_center_launchers_and_release():
    assert (ROOT/'pages/262_Step193_Mandatory_Module_Completion_Install_Repair_Center.py').is_file()
    assert (ROOT/'LOAD_STEP193_MANDATORY_COMPLETION_WINDOWS.bat').is_file()
    assert (ROOT/'RUN_STEP193_SELF_TEST_WINDOWS.bat').is_file()
    assert (ROOT/'REPAIR_INSTALL_WINDOWS.bat').is_file()
    release=json.loads((ROOT/'STEP193_RELEASE.json').read_text())
    assert release['version']=='15.1.0' and release['mandatory_checks_total']==1920
