from __future__ import annotations

import json
from pathlib import Path

from biointel.operations.runtime_control import inspect_local_runtime, stop_local_runtime


ROOT = Path(__file__).resolve().parents[1]


def test_v16_five_part_windows_contract_is_consistent() -> None:
    installer = (ROOT / "INSTALL_WINDOWS.bat").read_text(encoding="utf-8")
    runner = (ROOT / "RUN_BOTH_WINDOWS.bat").read_text(encoding="utf-8")
    package = (ROOT / "scripts" / "step196_package.py").read_text(encoding="utf-8")
    release = json.loads((ROOT / "STEP196_RELEASE.json").read_text(encoding="utf-8"))

    assert release["package_revision"] == "V16-5PART"
    assert release["part_count"] == 5
    assert release["p0_p1_upgrade"]["scope"]["priority_modules"] == 62
    assert "for %%P in (1 2 3 4 5)" in installer
    assert "for %%P in (1 2 3 4 5)" in runner
    assert "CPython 3.11.x x64" in installer
    assert "biointel-icon-256.png" in (ROOT / "pages" / "25_Command_Center.py").read_text(encoding="utf-8")
    assert "PART_COUNT = 5" in package
    assert "range(PART_COUNT)" in package
    assert "range(5)" not in package
    assert '"AUTO_INSTALL_AND_RUN_WINDOWS.bat"' in package
    assert '"START_STEP91_AUTO_INSTALL_WINDOWS.bat"' in package


def test_v16_runtime_handover_contract_replaces_cross_release_blocking() -> None:
    launcher = (ROOT / "scripts" / "run_biointel_step97.py").read_text(encoding="utf-8")
    assert "_reconcile_existing_runtime_state" in launcher
    assert "handed-off-verified-release" in launcher
    assert "_matches_recorded_biointel_process" in launcher
    assert "A different extracted BioIntel release is already running" not in launcher


def test_current_runtime_entrypoints_use_friendly_non_traceback_failures() -> None:
    launcher = (ROOT / "scripts" / "run_biointel_step196.py").read_text(encoding="utf-8")
    supervisor = (ROOT / "scripts" / "run_biointel_step97.py").read_text(encoding="utf-8")
    assert "CPython 3.11.x x64" in launcher
    assert "step196_runtime_preflight.py" in supervisor
    assert "traceback.print_exc()" not in launcher
    assert "traceback.print_exc()" not in supervisor


def test_runtime_control_tolerates_corrupt_pid_values_and_refuses_other_release(tmp_path: Path) -> None:
    current_root = tmp_path / "current-release"
    other_root = tmp_path / "other-release"
    current_root.mkdir()
    other_root.mkdir()
    runtime = tmp_path / "UserData" / "runtime_logs"
    runtime.mkdir(parents=True)
    state_path = runtime / "biointel-running.json"
    state_path.write_text(
        json.dumps(
            {
                "app_root": str(other_root),
                "ui_pid": "not-a-pid",
                "api_pid": None,
                "worker_pid": -4,
            }
        ),
        encoding="utf-8",
    )

    inspected = inspect_local_runtime(current_root, tmp_path / "UserData")
    assert [row["pid"] for row in inspected["processes"]] == [0, 0, 0]
    stopped = stop_local_runtime(current_root, tmp_path / "UserData")
    assert stopped["state"] == "refused-different-release"
    assert state_path.exists()


def test_navigation_history_and_catalogue_controls_are_present() -> None:
    theme = (ROOT / "src" / "biointel" / "ui" / "theme.py").read_text(encoding="utf-8")
    catalogue = (ROOT / "pages" / "171_Module_Catalogue_Search.py").read_text(encoding="utf-8")
    assert "_track_navigation_history" in theme
    assert "_navigate_history" in theme
    assert "Visit history" in theme
    assert "svg_icon_html" in catalogue
