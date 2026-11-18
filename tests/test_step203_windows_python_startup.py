from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def text(name): return (ROOT/name).read_text(encoding='utf-8-sig',errors='replace')
def test_step203_direct_path_and_auto_repair():
    s=text('INSTALL_WINDOWS.bat')
    assert 'LOCALAPPDATA' in s and 'Python311\\python.exe' in s
    assert 'INSTALL_PYTHON311_WINDOWS.bat' in s
    assert 'scripts\\find_python311_windows.ps1' in s
    assert 'sys.version_info[:2]==(3,11)' in s.replace(' ', '')
    assert '3.11.9' not in s
    assert 'step220_part%%P.ok' in s and 'STEP220_RELEASE.json' in s
def test_step203_no_temp_download_and_signature_check():
    s=text('scripts/install_python311_user.ps1')
    assert 'BioIntelAI\\Downloads' in s
    assert '%TEMP%' not in s.upper()
    assert 'Get-AuthenticodeSignature' in s
    assert 'Python Software Foundation' in s
def test_step203_locator_handles_normal_user_install_and_spaces():
    s=text('scripts/find_python311_windows.ps1')
    assert '$env:LOCALAPPDATA\\Programs\\Python\\Python311\\python.exe' in s
    assert 'where.exe python' in s
    assert 'PythonCore' in s
def test_step203_one_click_entrypoints_exist():
    for name in ('FIX_PYTHON_STARTUP_WINDOWS.bat','START_HERE_STEP203_WINDOWS.bat','REPAIR_STEP203_WINDOWS.bat','VERIFY_STEP203_WINDOWS.bat'):
        assert (ROOT/name).is_file()
