from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_biointel_step97.py"


def _load_runtime_module():
    spec = importlib.util.spec_from_file_location("step196_cross_release_handover", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _state(root: Path, *, ui: int = 0, api: int = 0, worker: int = 0) -> dict[str, object]:
    return {
        "schema": "biointel.runtime-state.v3",
        "app_root": str(root),
        "ui_pid": ui,
        "api_pid": api,
        "worker_pid": worker,
        "ui_url": "http://127.0.0.1:8501",
        "api_url": "http://127.0.0.1:8000/openapi.json",
    }


def test_verified_old_release_is_handed_off_without_changing_user_data(tmp_path: Path) -> None:
    module = _load_runtime_module()
    old_root = tmp_path / "old-v14"
    new_root = tmp_path / "new-v15"
    old_root.mkdir()
    new_root.mkdir()
    runtime = tmp_path / "UserData" / "runtime_logs"
    runtime.mkdir(parents=True)
    state_path = runtime / "biointel-running.json"
    state_path.write_text(json.dumps(_state(old_root, ui=101, api=102)), encoding="utf-8")
    alive = {101, 102}
    commands = {
        101: f'"{old_root}/.venv/Scripts/python.exe" -m streamlit run app.py',
        102: f'"{old_root}/.venv/Scripts/python.exe" -m uvicorn biointel.api.main:app',
    }
    terminated: list[int] = []

    result = module._reconcile_existing_runtime_state(
        root=new_root,
        state_path=state_path,
        state=_state(old_root, ui=101, api=102),
        runtime_dir=runtime,
        pid_alive=lambda pid: pid in alive,
        command_line_for_pid=lambda pid: commands[pid],
        terminate_pid=lambda pid: (terminated.append(pid), alive.discard(pid), True)[2],
        url_ready=lambda _url: False,
    )

    assert result["outcome"] == "handed-off-verified-release"
    assert terminated == [101, 102]
    assert not state_path.exists()
    audit = json.loads((runtime / "biointel-runtime-reconciliation-latest.json").read_text(encoding="utf-8"))
    assert audit["project_data_changed"] is False
    assert audit["verified_roles"] == ["api", "ui"]


def test_unverified_or_reused_pid_is_never_terminated_or_allowed_to_block(tmp_path: Path) -> None:
    module = _load_runtime_module()
    old_root = tmp_path / "old-v14"
    new_root = tmp_path / "new-v15"
    old_root.mkdir()
    new_root.mkdir()
    runtime = tmp_path / "UserData" / "runtime_logs"
    runtime.mkdir(parents=True)
    state_path = runtime / "biointel-running.json"
    state_path.write_text(json.dumps(_state(old_root, ui=301)), encoding="utf-8")
    terminated: list[int] = []

    result = module._reconcile_existing_runtime_state(
        root=new_root,
        state_path=state_path,
        state=_state(old_root, ui=301),
        runtime_dir=runtime,
        pid_alive=lambda pid: pid == 301,
        command_line_for_pid=lambda _pid: "C:/Unrelated/python.exe -m unrelated_server",
        terminate_pid=lambda pid: terminated.append(pid) or False,
        url_ready=lambda _url: False,
    )

    assert result["outcome"] == "discarded-stale-or-unverified-runtime-record"
    assert terminated == []
    assert not state_path.exists()


def test_healthy_current_release_is_reused_instead_of_restarted(tmp_path: Path) -> None:
    module = _load_runtime_module()
    root = tmp_path / "current-v15"
    root.mkdir()
    runtime = tmp_path / "UserData" / "runtime_logs"
    runtime.mkdir(parents=True)
    state_path = runtime / "biointel-running.json"
    current = _state(root, ui=401, api=402)
    state_path.write_text(json.dumps(current), encoding="utf-8")

    result = module._reconcile_existing_runtime_state(
        root=root,
        state_path=state_path,
        state=current,
        runtime_dir=runtime,
        pid_alive=lambda pid: pid in {401, 402},
        command_line_for_pid=lambda _pid: "",
        terminate_pid=lambda _pid: False,
        url_ready=lambda _url: True,
    )

    assert result["outcome"] == "already-running"
    assert state_path.exists()


def test_handover_requires_exact_biointel_role_and_recorded_root() -> None:
    module = _load_runtime_module()
    root = "C:/BioIntel/V14"
    assert module._matches_recorded_biointel_process(
        "ui", '"C:/BioIntel/V14/.venv/Scripts/python.exe" -m streamlit run app.py', root
    )
    assert module._matches_recorded_biointel_process(
        "api", '"C:/BioIntel/V14/.venv/Scripts/python.exe" -m uvicorn biointel.api.main:app', root
    )
    assert not module._matches_recorded_biointel_process(
        "ui", '"C:/Other/.venv/Scripts/python.exe" -m streamlit run app.py', root
    )
    assert not module._matches_recorded_biointel_process(
        "api", '"C:/BioIntel/V14/.venv/Scripts/python.exe" -m uvicorn another.app:app', root
    )
