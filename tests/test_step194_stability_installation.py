from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_step194_files():
    for p in ['scripts/install_windows_step194.py','scripts/run_biointel_step194.py','scripts/step194_validate_release.py','STEP194_RELEASE.json']:
        assert (ROOT/p).is_file()

def test_installer_rollback_and_lock():
    text=(ROOT/'scripts/install_windows_step194.py').read_text()
    assert 'install_lock' in text
    assert '.venv.step194-backup' in text
    assert 'restoring the previous working environment' in text
    assert 'verify_windows_wheelhouse.py' in text

def test_startup_crash_guard():
    text=(ROOT/'scripts/run_biointel_step194.py').read_text()
    assert 'support(' in text
    assert 'launcher-step194.lock' in text
    assert 'rotate_logs' in text
    assert 'Automatic verified repair failed' in text

def test_batch_contract():
    install=(ROOT/'INSTALL_WINDOWS.bat').read_text()
    run=(ROOT/'RUN_BOTH_WINDOWS.bat').read_text()
    assert ('step194_part%%P.ok' in install or 'step196_part%%P.ok' in install)
    assert ('install_windows_step194.py' in install or 'install_windows_step196.py' in install)
    assert ('run_biointel_step194.py' in run or 'run_biointel_step196.py' in run)

def test_four_markers():
    assert (all((ROOT/'.release_parts'/f'step194_part{i}.ok').is_file() for i in range(1,5)) or all((ROOT/'.release_parts'/f'step196_part{i}.ok').is_file() for i in range(1,5)))
