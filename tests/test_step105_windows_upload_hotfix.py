from __future__ import annotations

import os
from pathlib import Path

from biointel.expansion.io_formats import supported_extensions_for_module
from biointel.step101 import background

ROOT = Path(__file__).resolve().parents[1]


def test_upload_transport_is_one_gib() -> None:
    config = (ROOT / ".streamlit/config.toml").read_text(encoding="utf-8")
    assert "maxUploadSize = 1024" in config
    assert "maxMessageSize = 1024" in config


def test_expansion_uploaders_are_active_by_default() -> None:
    text = (ROOT / "src/biointel/expansion/renderer.py").read_text(encoding="utf-8")
    assert '["Upload scientific data file", "Deterministic demonstration data"]' in text
    assert 'disabled=source.startswith("Deterministic")' not in text
    assert "Maximum 1 GB per file" in text


def test_nextgen_uploaders_are_active_by_default() -> None:
    text = (ROOT / "src/biointel/nextgen/renderer.py").read_text(encoding="utf-8")
    assert '["Upload scientific data", "Deterministic demonstration data"]' in text
    assert 'disabled=source.startswith("Deterministic")' not in text
    assert '"cell_atlas_mapping": ["h5ad"]' in text


def test_module_specific_extensions_are_truthful() -> None:
    assert "bed" in supported_extensions_for_module("epigenomics_chromatin")
    assert "mzml" in supported_extensions_for_module("metabolomics_lipidomics")
    assert "pdb" in supported_extensions_for_module("docking_dynamics")
    assert "h5ad" in supported_extensions_for_module("single_cell_trajectory")
    assert "pdb" not in supported_extensions_for_module("biostatistics_design")


def test_pid_liveness_never_uses_posix_probe_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(background.os, "name", "nt")
    monkeypatch.setattr(background, "_windows_pid_alive", lambda pid: pid == 123)
    assert background._pid_alive(123) is True
    assert background._pid_alive(124) is False
    assert background._pid_alive(0) is False


def test_current_process_is_alive_on_host() -> None:
    assert background._pid_alive(os.getpid()) is True


def test_stale_worker_state_is_removed(tmp_path, monkeypatch) -> None:
    service = background.BackgroundJobService(tmp_path)
    service.state_path.write_text('{"pid": 999999, "worker_id": "stale"}', encoding="utf-8")
    monkeypatch.setattr(background, "_pid_alive", lambda pid: False)
    status = service.status()
    assert status.running is False
    assert status.pid == 0
    assert not service.state_path.exists()

def test_worker_launch_closes_parent_log_and_requires_registration(tmp_path, monkeypatch) -> None:
    service = background.BackgroundJobService(tmp_path)
    captured = {}

    class Process:
        pid = 123
        returncode = None

        @staticmethod
        def poll():
            return None

    def launch(*args, **kwargs):
        captured["log"] = kwargs["stdout"]
        return Process()

    monkeypatch.setattr(background.os, "getpid", lambda: 7)
    monkeypatch.setattr(background.time, "time", lambda: 42)
    monkeypatch.setattr(background, "_pid_alive", lambda pid: pid == 123)
    monkeypatch.setattr(background.subprocess, "Popen", launch)
    monkeypatch.setattr(
        service.queue,
        "workers",
        lambda: [{"worker_id": "background-7-42", "status": "online"}],
    )

    status = service.start()

    assert status.running is True
    assert captured["log"].closed is True


def test_worker_bootstrap_registers_before_heavy_scientific_import() -> None:
    source = (ROOT / "scripts" / "background_job_worker.py").read_text(encoding="utf-8")
    assert source.index('status="starting"') < source.index(
        "from biointel.jobs.worker import LocalWorker"
    )
    assert "startup_timeout_seconds: float = 60.0" in (
        ROOT / "src" / "biointel" / "step101" / "background.py"
    ).read_text(encoding="utf-8")