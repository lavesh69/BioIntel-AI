from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig", errors="replace")

def test_step205_release_identity_is_consistent() -> None:
    release = json.loads(text("STEP205_RELEASE.json"))
    assert text("VERSION").strip() == release["version"] == "15.5.0"
    assert release["step"] == 205
    assert release["part_count"] == 4
    assert release["package_generation"] == "V18.0"
    assert release["python_runtime"] == "CPython 3.11.9 x64"

def test_step205_two_file_windows_workflow() -> None:
    install, run = text("INSTALL_WINDOWS.bat"), text("RUN_BOTH_WINDOWS.bat")
    assert "for %%P in (1 2 3 4)" in install
    assert "step205_part%%P.ok" in install and "step205_part%%P.ok" in run
    assert "step205_release_gate.py" in install
    assert "verify_step205_windows_install_run.py" in install
    assert "INSTALLATION VERIFICATION FAILED" in install

def test_exact_python_3119_and_path_safety_are_retained() -> None:
    for path in ("INSTALL_WINDOWS.bat", "RUN_BOTH_WINDOWS.bat", "scripts/find_python311_windows.ps1", "scripts/install_windows_step196.py", "scripts/run_biointel_step196.py", "scripts/run_biointel_step97.py"):
        assert "(3,11,9)" in text(path).replace(" ", "")
    assert 'pushd "%~dp0"' in text("INSTALL_WINDOWS.bat")
    assert 'pushd "%~dp0"' in text("RUN_BOTH_WINDOWS.bat")

def test_optional_services_remain_non_blocking() -> None:
    installer = text("scripts/install_windows_step196.py").split("def main()", 1)[1]
    assert "launch_optional_free_web_ai_setup(py)" not in installer
    assert "launch_scientific_runtime_setup(py)" not in installer

def test_excluded_module_pages_remain_present() -> None:
    for path in ("pages/6_DTI_Predictor.py", "pages/74_DTI_Validation_Evidence_Center.py", "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py", "pages/109_Lab_Instrument_Import_Center.py", "pages/157_Instrument_Integration_Hub_2.py"):
        assert (ROOT / path).is_file()
