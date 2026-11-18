from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig", errors="replace")


def test_step204_release_identity_is_consistent() -> None:
    release = json.loads(text("STEP204_RELEASE.json"))
    assert text("VERSION").strip() == release["version"] == "15.4.0"
    assert release["step"] == 204
    assert release["part_count"] == 4
    assert release["package_generation"] == "V17.1"
    assert release["python_runtime"] == "CPython 3.11.9 x64"


def test_step204_two_file_windows_workflow() -> None:
    install = text("INSTALL_WINDOWS.bat")
    run = text("RUN_BOTH_WINDOWS.bat")
    assert "for %%P in (1 2 3 4)" in install
    assert "step204_part%%P.ok" in install
    assert "step204_part%%P.ok" in run
    assert "step204_release_gate.py" in install
    assert "verify_step204_windows_install_run.py" in install
    assert "INSTALLATION VERIFICATION FAILED" in install


def test_exact_python_3119_is_enforced_end_to_end() -> None:
    files = (
        "INSTALL_WINDOWS.bat",
        "RUN_BOTH_WINDOWS.bat",
        "scripts/find_python311_windows.ps1",
        "scripts/install_python311_user.ps1",
        "scripts/install_windows_step196.py",
        "scripts/run_biointel_step196.py",
        "scripts/run_biointel_step97.py",
    )
    for path in files:
        assert "(3,11,9)" in text(path).replace(" ", "")


def test_optional_services_do_not_block_core_install_or_run() -> None:
    installer = text("scripts/install_windows_step196.py")
    launcher = text("scripts/run_biointel_step196.py")
    main_block = installer.split("def main()", 1)[1]
    assert "launch_optional_free_web_ai_setup(py)" not in main_block
    assert "launch_scientific_runtime_setup(py)" not in main_block
    assert "setup_free_web_ai_windows.py" not in launcher


def test_path_and_shortcut_hardening_present() -> None:
    install = text("INSTALL_WINDOWS.bat")
    run = text("RUN_BOTH_WINDOWS.bat")
    helper = text("scripts/install_windows_step196.py")
    assert 'pushd "%~dp0"' in install
    assert 'pushd "%~dp0"' in run
    assert '"%PYTHON_EXE%"' in install
    assert '"%PY%"' in run
    assert "_remove_stale_biointel_shortcuts" in helper
    assert "BioIntel AI*.lnk" in helper
    assert "RUN_BOTH_WINDOWS.bat" in helper


def test_excluded_module_pages_remain_present() -> None:
    for path in (
        "pages/6_DTI_Predictor.py",
        "pages/74_DTI_Validation_Evidence_Center.py",
        "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py",
        "pages/109_Lab_Instrument_Import_Center.py",
        "pages/157_Instrument_Integration_Hub_2.py",
    ):
        assert (ROOT / path).is_file()
