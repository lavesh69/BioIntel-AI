from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "install_windows_step196.py"


def load_installer_module():
    spec = importlib.util.spec_from_file_location("step196_installer_lock_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configure_paths(module, tmp_path: Path) -> Path:
    lock = tmp_path / "runtime" / "install-step196.lock"
    module.LOCK = lock
    module.LOG = tmp_path / "runtime_logs" / "install.log"
    return lock


def test_recent_lock_from_dead_process_is_removed(tmp_path: Path) -> None:
    module = load_installer_module()
    lock = configure_paths(module, tmp_path)
    lock.parent.mkdir(parents=True)
    lock.write_text(
        json.dumps({"pid": 999_999_999, "created_epoch": time.time()}),
        encoding="utf-8",
    )

    with module.install_lock():
        payload = json.loads(lock.read_text(encoding="utf-8"))
        assert payload["pid"] == os.getpid()
        assert payload["schema"] == "biointel.step196.install-lock.v3"
        assert payload["token"]

    assert not lock.exists()


def test_live_process_lock_is_not_removed(tmp_path: Path) -> None:
    module = load_installer_module()
    lock = configure_paths(module, tmp_path)
    script = """
import importlib.util
import sys
import time
from pathlib import Path
source, lock_path = map(Path, sys.argv[1:3])
spec = importlib.util.spec_from_file_location('step196_child_lock', source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.LOCK = lock_path
module.LOG = lock_path.parent / 'child-install.log'
with module.install_lock():
    print('LOCKED', flush=True)
    time.sleep(15)
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", script, str(SCRIPT), str(lock)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "LOCKED"
        with pytest.raises(RuntimeError, match="genuinely active"):
            with module.install_lock():
                pass
        assert lock.exists()
    finally:
        proc.terminate()
        proc.communicate(timeout=10)


def test_old_invalid_lock_is_self_healed(tmp_path: Path) -> None:
    module = load_installer_module()
    lock = configure_paths(module, tmp_path)
    lock.parent.mkdir(parents=True)
    lock.write_text("partial-json", encoding="utf-8")
    old = time.time() - 60
    os.utime(lock, (old, old))

    with module.install_lock():
        payload = json.loads(lock.read_text(encoding="utf-8"))
        assert payload["token"]

    assert not lock.exists()


def test_lock_release_does_not_delete_replacement(tmp_path: Path) -> None:
    module = load_installer_module()
    lock = configure_paths(module, tmp_path)

    with module.install_lock():
        lock.write_text(
            json.dumps({"pid": os.getpid(), "created_epoch": time.time(), "token": "replacement"}),
            encoding="utf-8",
        )

    assert lock.exists()
    assert json.loads(lock.read_text(encoding="utf-8"))["token"] == "replacement"
