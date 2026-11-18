from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import shutil
import struct
import subprocess
import sys
import time
import threading
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Any

from step206_contract import (
    CURRENT_SOURCE_MANIFEST_NAME,
    MANIFEST_NAME,
    PACKAGE_GENERATION,
    PART_COUNT,
    PRODUCT_VERSION,
    RELEASE_ID,
    RELEASE_NAME,
    RELEASE_STEP,
    REQUIRED_PYTHON,
    REQUIRED_PYTHON_TEXT,
    active_record,
    active_record_path,
    app_directory,
    app_home,
    atomic_write_json,
    managed_release_root,
    releases_directory,
    stable_diagnose_path,
    stable_launcher_path,
    stable_repair_path,
    stable_restart_path,
    stable_safe_mode_path,
    stable_stop_path,
    stable_uninstall_path,
    user_data_directory,
    utc_now,
)

SOURCE_ROOT_DEFAULT = Path(__file__).resolve().parents[1]
APP_HOME = app_home()
USER_DATA = user_data_directory()
TARGET_ROOT = managed_release_root()
LOCK = USER_DATA / "runtime" / f"install-step{RELEASE_STEP}.lock"
REPORT = USER_DATA / "reports" / f"step{RELEASE_STEP}-install.json"
LOG = USER_DATA / "runtime_logs" / f"step{RELEASE_STEP}-install-{datetime.now():%Y%m%d-%H%M%S}.log"
COPY_EXCLUDED_NAMES = {
    ".venv",
    ".venv.step196-backup",
    ".venv.step206-backup",
    ".venv.step220-backup",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git",
    ".hotfix_backups",
    "UserData",
    "runtime_logs",
    "work",
}
BUNDLED_USER_DATA_SEED_NAMES = {
    "databases",
    "data",
    "proof_gates_v10",
    "step183",
    "step184",
    "step185",
    "step186",
    "step187",
    "step188",
    "step189",
    "step190",
    "step192",
    "step193",
    "connect",
    "research_planning",
    "workspace",
    "cache",
    "engine-platform",
    "engine_platform_v196",
}
SEED_MANIFEST_RELATIVE = Path("release/USER_DATA_SEED_MANIFEST_SHA256.json")


def check_python_runtime() -> None:
    if sys.version_info < (3, 11) or struct.calcsize("P") * 8 != 64:
        current = ".".join(str(part) for part in sys.version_info[:3])
        raise RuntimeError(
            f"BioIntel AI requires CPython 3.11+ x64. "
            f"Installer is using Python {current} ({struct.calcsize('P')*8}-bit). Please use 64-bit Python 3.11 or newer."
        )


def write(message: str = "") -> None:
    print(message, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8", errors="replace") as handle:
        handle.write(message + "\n")


def ensure_application_directories() -> None:
    for path in (
        APP_HOME,
        app_directory(),
        releases_directory(),
        USER_DATA,
        USER_DATA / "data",
        USER_DATA / "reports",
        USER_DATA / "workspace",
        USER_DATA / "exports",
        USER_DATA / "projects",
        USER_DATA / "runtime_logs",
        USER_DATA / "runtime",
        USER_DATA / "backups",
        APP_HOME / "Temp",
        APP_HOME / "Tools",
        APP_HOME / "ReferenceAssets",
        APP_HOME / "Downloads",
    ):
        path.mkdir(parents=True, exist_ok=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def seed_bundled_user_data(source_root: Path) -> dict[str, Any]:
    """Verify and copy signed demo/assurance seeds without overwriting user files."""

    source_base = source_root / "UserData"
    manifest_path = source_root / SEED_MANIFEST_RELATIVE
    if not source_base.is_dir():
        return {"state": "no-bundled-user-data", "copied": 0, "preserved": 0, "roots": []}
    if not manifest_path.is_file():
        raise RuntimeError(f"Bundled UserData seed manifest is missing: {SEED_MANIFEST_RELATIVE}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Bundled UserData seed manifest is invalid: {exc}") from exc
    rows = payload.get("files", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("Bundled UserData seed manifest contains no files.")

    verified: list[tuple[Path, Path, str]] = []
    seeded_roots: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("Bundled UserData seed manifest contains an invalid row.")
        rel_text = str(row.get("path", "")).replace("\\", "/")
        rel = Path(rel_text)
        if rel.is_absolute() or ".." in rel.parts or len(rel.parts) < 3 or rel.parts[0].casefold() != "userdata":
            raise RuntimeError(f"Unsafe bundled UserData seed path: {rel_text!r}")
        root_name = rel.parts[1]
        if root_name not in BUNDLED_USER_DATA_SEED_NAMES:
            raise RuntimeError(f"Unapproved bundled UserData seed root: {root_name}")
        source = source_root / rel
        expected_size = int(row.get("size_bytes", -1))
        expected_hash = str(row.get("sha256", ""))
        if not source.is_file() or source.stat().st_size != expected_size:
            raise RuntimeError(f"Bundled UserData seed size mismatch: {rel_text}")
        if not expected_hash or _sha256_file(source) != expected_hash:
            raise RuntimeError(f"Bundled UserData seed SHA-256 mismatch: {rel_text}")
        target = USER_DATA / Path(*rel.parts[1:])
        verified.append((source, target, root_name))
        seeded_roots.add(root_name)

    copied = 0
    preserved = 0
    for source, target, _root_name in verified:
        if source.name.endswith(("-wal", "-shm", ".pyc", ".pyo")):
            continue
        if target.exists():
            preserved += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".step220-seed.tmp")
        shutil.copy2(source, temporary)
        os.replace(temporary, target)
        copied += 1
    return {
        "state": "seeded" if copied else "already-present",
        "verified": len(verified),
        "copied": copied,
        "preserved": preserved,
        "roots": sorted(seeded_roots),
        "manifest": str(manifest_path),
    }


def _env(root: Path) -> dict[str, str]:
    short = APP_HOME / "Temp"
    cache_root = USER_DATA / "cache"
    for path in (short, short / "runtime", cache_root / "numba", cache_root / "matplotlib"):
        path.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "BIOINTEL_USER_DATA_DIR": str(USER_DATA),
            "BIOINTEL_SHORT_TEMP": str(short),
            "BIOINTEL_RUNTIME_TEMP": str(short / "runtime"),
            "TEMP": str(short),
            "TMP": str(short),
            "NUMBA_CACHE_DIR": str(cache_root / "numba"),
            "MPLCONFIGDIR": str(cache_root / "matplotlib"),
            "PYTHONPATH": str(root / "src"),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PIP_NO_INPUT": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_CACHE_DIR": "1",
        }
    )
    return env


def run(
    command: list[str],
    *,
    cwd: Path,
    check: bool = True,
    timeout: int | None = None,
) -> int:
    write("RUN: " + subprocess.list2cmdline(command))
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_env(cwd),
    )
    assert process.stdout is not None
    messages: queue.Queue[str | None] = queue.Queue()

    def reader() -> None:
        try:
            for line in process.stdout:
                messages.put(line)
        finally:
            messages.put(None)

    thread = threading.Thread(target=reader, name="step206-installer-output", daemon=True)
    thread.start()
    started = time.monotonic()
    stream_finished = False
    while True:
        if timeout is not None and time.monotonic() - started > timeout:
            process.kill()
            process.wait()
            raise RuntimeError(
                f"Command timed out after {timeout} seconds: {subprocess.list2cmdline(command)}"
            )
        try:
            item = messages.get(timeout=0.2)
        except queue.Empty:
            item = ""
        if item is None:
            stream_finished = True
        elif item:
            write(item.rstrip())
        if process.poll() is not None and stream_finished:
            break
    thread.join(timeout=1)
    code = int(process.returncode or 0)
    if check and code:
        raise RuntimeError(f"Command failed ({code}): {subprocess.list2cmdline(command)}")
    return code


class InterprocessFileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: BinaryIO | None = None
        self.token = uuid.uuid4().hex

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0, os.SEEK_END)
        if self.handle.tell() == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            raise RuntimeError("Another BioIntel installation or repair is already active.") from exc
        self.handle.seek(0)
        self.handle.truncate(0)
        self.handle.write(
            json.dumps({"pid": os.getpid(), "token": self.token, "release": RELEASE_ID}).encode("utf-8")
        )
        self.handle.flush()

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self.handle.close()
        self.handle = None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8", errors="replace"))
            if payload.get("token") == self.token:
                self.path.unlink(missing_ok=True)
        except (OSError, json.JSONDecodeError, AttributeError):
            pass


@contextmanager
def install_lock():
    lock = InterprocessFileLock(LOCK)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def _validate_source_root(source_root: Path) -> None:
    required = (
        "app.py",
        "INSTALL_WINDOWS.bat",
        "RUN_BOTH_WINDOWS.bat",
        "STOP_BIOINTEL_WINDOWS.bat",
        "RESTART_BIOINTEL_WINDOWS.bat",
        "REPAIR_WINDOWS.bat",
        "DIAGNOSE_WINDOWS.bat",
        "SAFE_MODE_WINDOWS.bat",
        "UNINSTALL_BIOINTEL_WINDOWS.bat",
        RELEASE_NAME,
        MANIFEST_NAME,
        CURRENT_SOURCE_MANIFEST_NAME,
        SEED_MANIFEST_RELATIVE.as_posix(),
        "scripts/step206_release_gate.py",
        "scripts/install_windows_step206.py",
        "scripts/runtime_supervisor_step206.py",
        "scripts/streamlit_startup_check_step206.py",
        "scripts/verify_step206_windows_install_run.py",
        "scripts/verify_windows_runtime_compatibility_step206.py",
        "scripts/step206_support_bundle.py",
        "scripts/diagnose_windows_step206.py",
        "scripts/uninstall_windows_step206.py",
        "wheelhouse/windows-cp311-x64/WHEELHOUSE_METADATA.json",
    )
    missing = [item for item in required if not (source_root / item).is_file()]
    if missing:
        raise RuntimeError(f"Incomplete Step{RELEASE_STEP} extraction. Missing: " + ", ".join(missing))
    missing_parts = [
        part
        for part in range(1, PART_COUNT + 1)
        if not (source_root / ".release_parts" / f"step{RELEASE_STEP}_part{part}.ok").is_file()
    ]
    if missing_parts:
        raise RuntimeError(
            f"Step{RELEASE_STEP} ZIP parts missing: " + ", ".join(str(part) for part in missing_parts) + ". Extract all four parts together."
        )


def _check_target_permissions_and_disk(source_root: Path) -> None:
    probe = APP_HOME / ".install-write-probe.tmp"
    try:
        probe.write_text("ok", encoding="utf-8")
        if probe.read_text(encoding="utf-8") != "ok":
            raise OSError("write verification failed")
    except OSError as exc:
        raise RuntimeError(f"BioIntel application folder is not writable: {APP_HOME}. Details: {exc}") from exc
    finally:
        probe.unlink(missing_ok=True)

    try:
        source_size = sum(path.stat().st_size for path in source_root.rglob("*") if path.is_file())
    except OSError:
        source_size = 1024**3
    required = max(2 * 1024**3, source_size + 500 * 1024**2)
    free = shutil.disk_usage(APP_HOME).free
    if free < required:
        raise RuntimeError(
            f"Installation drive needs about {required / 1024**3:.1f} GB free; available {free / 1024**3:.1f} GB."
        )


def verify_source_before_copy(source_root: Path) -> None:
    run(
        [
            sys.executable,
            str(source_root / "scripts" / "step206_release_gate.py"),
            "--root",
            str(source_root),
            "--deep-hashes",
            "--output",
            str(USER_DATA / "reports" / f"step{RELEASE_STEP}-source-release-gate.json"),
        ],
        cwd=source_root,
        timeout=900,
    )
    run(
        [sys.executable, str(source_root / "scripts" / "verify_dependency_lock.py"), "--root", str(source_root)],
        cwd=source_root,
        timeout=300,
    )
    run(
        [sys.executable, str(source_root / "scripts" / "verify_windows_wheelhouse.py"), "--root", str(source_root)],
        cwd=source_root,
        timeout=900,
    )


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    ignored = {name for name in names if name in COPY_EXCLUDED_NAMES}
    ignored.update(name for name in names if name.endswith((".pyc", ".pyo", "-wal", "-shm")))
    return ignored


def _copy_source_tree(source_root: Path, staging: Path) -> None:
    """Copy through a short staging root while retaining Windows long-path support."""
    staging.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        robocopy = shutil.which("robocopy.exe") or shutil.which("robocopy")
        if robocopy:
            command = [
                robocopy,
                str(source_root),
                str(staging),
                "/E",
                "/COPY:DAT",
                "/DCOPY:DAT",
                "/R:2",
                "/W:1",
                "/XJ",
                "/NFL",
                "/NDL",
                "/NJH",
                "/NJS",
                "/NP",
                "/XD",
                *sorted(COPY_EXCLUDED_NAMES),
                "/XF",
                "*.pyc",
                "*.pyo",
                "*-wal",
                "*-shm",
            ]
            code = run(command, cwd=source_root, check=False, timeout=3600)
            if code >= 8:
                raise RuntimeError(f"Long-path managed source copy failed with robocopy exit code {code}.")
            return
    shutil.copytree(source_root, staging, ignore=_copy_ignore, copy_function=shutil.copy2)


def _target_source_valid(source_root: Path) -> bool:
    if not TARGET_ROOT.is_dir():
        return False
    manifest_name = (
        CURRENT_SOURCE_MANIFEST_NAME
        if (source_root / CURRENT_SOURCE_MANIFEST_NAME).is_file()
        else MANIFEST_NAME
    )
    source_manifest = source_root / manifest_name
    target_manifest = TARGET_ROOT / manifest_name
    try:
        if not source_manifest.is_file() or not target_manifest.is_file():
            return False
        # A same-version hotfix must replace the managed source instead of
        # reusing a previously verified but stale Step206 installation.
        if source_manifest.read_bytes() != target_manifest.read_bytes():
            return False
    except OSError:
        return False
    command = [
        sys.executable,
        str(TARGET_ROOT / "scripts" / "step206_release_gate.py"),
        "--root",
        str(TARGET_ROOT),
        "--quick",
        "--allow-builder-python",
        "--output",
        str(USER_DATA / "reports" / f"step{RELEASE_STEP}-managed-source-gate.json"),
    ]
    return run(command, cwd=TARGET_ROOT, check=False, timeout=900) == 0


def install_managed_source(source_root: Path) -> dict[str, Any]:
    if _target_source_valid(source_root):
        write(f"Managed Step{RELEASE_STEP} source already verified: {TARGET_ROOT}")
        return {"state": "reused-verified", "target": str(TARGET_ROOT)}

    staging = releases_directory() / f".{RELEASE_ID}.staging-{uuid.uuid4().hex[:8]}"
    backup = releases_directory() / f".{RELEASE_ID}.invalid-backup-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.rmtree(staging, ignore_errors=True)
    write(f"Copying verified package to stable application folder: {TARGET_ROOT}")
    _copy_source_tree(source_root, staging)
    for runtime_path in (
        staging / ".biointel_step196_installed",
        staging / ".biointel_step206_installed",
        staging / ".biointel_step220_installed",
        staging / "reports" / "step205-release-gate-runtime.json",
        staging / "reports" / "step206-release-gate-runtime.json",
        staging / "reports" / "step220-release-gate-runtime.json",
    ):
        runtime_path.unlink(missing_ok=True)

    run(
        [
            sys.executable,
            str(staging / "scripts" / "step206_release_gate.py"),
            "--root",
            str(staging),
            "--quick",
            "--allow-builder-python",
            "--output",
            str(USER_DATA / "reports" / f"step{RELEASE_STEP}-staging-source-gate.json"),
        ],
        cwd=staging,
        timeout=900,
    )

    if TARGET_ROOT.exists():
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        try:
            TARGET_ROOT.replace(backup)
        except OSError:
            time.sleep(1)
            try:
                TARGET_ROOT.replace(backup)
            except OSError:
                shutil.rmtree(TARGET_ROOT, ignore_errors=True)
    try:
        if staging.exists():
            try:
                staging.replace(TARGET_ROOT)
            except OSError:
                shutil.copytree(staging, TARGET_ROOT, dirs_exist_ok=True, copy_function=shutil.copy2)
    except Exception:
        if backup.exists() and not TARGET_ROOT.exists():
            try:
                backup.replace(TARGET_ROOT)
            except OSError:
                pass
        raise
    else:
        previous_venv = backup / ".venv"
        target_venv = TARGET_ROOT / ".venv"
        if previous_venv.is_dir() and not target_venv.exists():
            write("Preserving the verified managed Python environment across the source update...")
            try:
                previous_venv.replace(target_venv)
            except OSError:
                shutil.copytree(previous_venv, target_venv, copy_function=shutil.copy2)
        shutil.rmtree(backup, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)
    return {"state": "installed", "target": str(TARGET_ROOT)}


def _runtime_compatibility_command(python: Path, output_name: str) -> list[str]:
    return [
        str(python),
        str(TARGET_ROOT / "scripts" / "verify_windows_runtime_compatibility_step206.py"),
        "--root",
        str(TARGET_ROOT),
        "--strict-python",
        "--output",
        str(USER_DATA / "reports" / output_name),
    ]


def _environment_probe(python: Path) -> bool:
    if not python.is_file():
        return False
    if run([str(python), "-m", "pip", "check"], cwd=TARGET_ROOT, check=False, timeout=300):
        return False
    return (
        run(
            _runtime_compatibility_command(python, "step206-windows-runtime-compatibility-probe.json"),
            cwd=TARGET_ROOT,
            check=False,
            timeout=600,
        )
        == 0
    )


def _post_install_tests(python: Path) -> None:
    run([str(python), "-m", "pip", "check"], cwd=TARGET_ROOT, timeout=300)
    run(
        _runtime_compatibility_command(python, "step206-windows-runtime-compatibility.json"),
        cwd=TARGET_ROOT,
        timeout=600,
    )
    run([str(python), str(TARGET_ROOT / "scripts" / "step196_self_test.py")], cwd=TARGET_ROOT, timeout=600)
    run([str(python), str(TARGET_ROOT / "scripts" / "verify_step202_neuro.py")], cwd=TARGET_ROOT, timeout=600)
    run(
        [
            str(python),
            str(TARGET_ROOT / "scripts" / "streamlit_startup_check_step206.py"),
            "--root",
            str(TARGET_ROOT),
            "--output",
            str(USER_DATA / "reports" / "step206-streamlit-startup-check.json"),
        ],
        cwd=TARGET_ROOT,
        timeout=300,
    )
    run(
        [
            str(python),
            str(TARGET_ROOT / "scripts" / "verify_step206_windows_install_run.py"),
            "--root",
            str(TARGET_ROOT),
            "--installed-python",
            str(python),
        ],
        cwd=TARGET_ROOT,
        timeout=600,
    )
    run(
        [str(python), str(TARGET_ROOT / "scripts" / "runtime_supervisor_step206.py"), "--root", str(TARGET_ROOT), "--self-check"],
        cwd=TARGET_ROOT,
        timeout=120,
    )


def _initialize_engine_platform(python: Path) -> dict[str, Any]:
    output = USER_DATA / "reports" / "step213-engine-platform-bootstrap.json"
    run(
        [
            str(python),
            str(TARGET_ROOT / "scripts" / "step213_engine_platform_bootstrap.py"),
            "--root",
            str(TARGET_ROOT),
            "--user-data",
            str(USER_DATA),
            "--output",
            str(output),
        ],
        cwd=TARGET_ROOT,
        timeout=300,
    )
    acquisition_output = USER_DATA / "reports" / "step214-engine-acquisition.json"
    acquisition_dir = USER_DATA / "engine_packs" / "v19.6-acquisition"
    run(
        [
            str(python),
            str(TARGET_ROOT / "scripts" / "step214_prepare_engine_acquisition.py"),
            "--root",
            str(TARGET_ROOT),
            "--output",
            str(acquisition_dir),
        ],
        cwd=TARGET_ROOT,
        timeout=300,
    )
    acquisition_manifest = acquisition_dir / "BIOINTEL_ENGINE_ACQUISITION.json"
    acquisition_payload = json.loads(acquisition_manifest.read_text(encoding="utf-8"))
    acquisition_output.write_text(json.dumps(acquisition_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "engine_platform": json.loads(output.read_text(encoding="utf-8")),
        "engine_acquisition": acquisition_payload,
    }


def install_environment(force: bool, *, online: bool = False) -> Path:
    venv = TARGET_ROOT / ".venv"
    python = venv / "Scripts" / "python.exe"
    backup = TARGET_ROOT / ".venv.step206-backup"
    shutil.rmtree(backup, ignore_errors=True)

    if venv.is_dir() and not force and _environment_probe(python):
        try:
            _post_install_tests(python)
            write("Existing managed environment is healthy; dependency reinstall skipped.")
            return python
        except Exception as exc:
            write(f"Existing environment failed full verification and will be rebuilt: {exc}")

    if venv.exists():
        write("Preserving previous environment for rollback...")
        venv.replace(backup)
    try:
        bootstrap_mode = "--online" if online else "--offline"
        run(
            [sys.executable, str(TARGET_ROOT / "scripts" / "bootstrap.py"), bootstrap_mode],
            cwd=TARGET_ROOT,
            timeout=3600,
        )
        if not python.is_file():
            raise RuntimeError("Virtual environment was not created in the managed application folder.")
        _post_install_tests(python)
    except Exception:
        shutil.rmtree(venv, ignore_errors=True)
        if backup.exists():
            write("Environment build failed; restoring the previous verified environment...")
            backup.replace(venv)
        raise
    else:
        shutil.rmtree(backup, ignore_errors=True)
    return python


# Legacy source examples include reports/jobs.sqlite3 and reports/api_security.sqlite3; migration targets UserData/databases.
LEGACY_RUNTIME_DATABASE_NAMES = (
    "jobs.sqlite3",
    "feature_cache.sqlite3",
    "api_security.sqlite3",
    "tenants.sqlite3",
    "biotechnology_project_runs.sqlite3",
)


def _legacy_release_databases(release_root: Path) -> list[Path]:
    reports = release_root / "reports"
    if not reports.is_dir():
        return []
    discovered: dict[str, Path] = {}
    for pattern in ("*.sqlite3", "*.sqlite", "*.db"):
        for path in reports.glob(pattern):
            if path.is_file() and not path.name.endswith(("-wal", "-shm")):
                discovered.setdefault(path.name.casefold(), path)
    for name in LEGACY_RUNTIME_DATABASE_NAMES:
        path = reports / name
        if path.is_file():
            discovered.setdefault(name.casefold(), path)
    return sorted(discovered.values(), key=lambda item: item.name.casefold())


def _backup_databases(previous_root: Path | None = None) -> dict[str, Any]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = USER_DATA / "backups" / f"pre-step206-{stamp}"
    sources: list[tuple[str, Path, Path]] = []
    for path in USER_DATA.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".sqlite", ".sqlite3", ".db"} and "backups" not in path.parts:
            sources.append(("user-data", path, path.relative_to(USER_DATA)))
    if previous_root is not None:
        scope = "active-release" if previous_root.resolve() == TARGET_ROOT.resolve() else "previous-release"
        for path in _legacy_release_databases(previous_root):
            sources.append((scope, path, Path("reports") / path.name))

    copied: list[dict[str, str]] = []
    for scope, source, relative in sources:
        target = destination / scope / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append({"scope": scope, "source": str(source), "backup": target.relative_to(destination).as_posix()})
    if copied:
        (destination / "BACKUP_MANIFEST.json").write_text(
            json.dumps(
                {
                    "schema": "biointel.database-backup.v2",
                    "created_at": utc_now(),
                    "target_release": RELEASE_ID,
                    "files": copied,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return {
        "state": "created" if copied else "no-databases-found",
        "path": str(destination),
        "file_count": len(copied),
    }


def _migrate_previous_runtime_databases(previous_root: Path | None) -> dict[str, Any]:
    if previous_root is None:
        return {"state": "not-required", "migrated": [], "preserved": []}
    destination = USER_DATA / "databases"
    destination.mkdir(parents=True, exist_ok=True)
    migrated: list[str] = []
    preserved: list[str] = []
    for source in _legacy_release_databases(previous_root):
        target = destination / source.name
        if target.exists():
            preserved.append(source.name)
            continue
        temporary = target.with_name(target.name + ".step220-migration.tmp")
        shutil.copy2(source, temporary)
        os.replace(temporary, target)
        migrated.append(source.name)
    return {
        "state": "migrated" if migrated else "no-previous-runtime-databases",
        "previous_root": str(previous_root),
        "destination": str(destination),
        "migrated": migrated,
        "preserved": preserved,
    }


def _stop_active_runtime_before_activation() -> dict[str, Any]:
    record_path = active_record_path()
    try:
        record = json.loads(record_path.read_text(encoding="utf-8-sig")) if record_path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        record = {}
    old_root = Path(str(record.get("application_root", ""))).expanduser() if record.get("application_root") else None
    state_path = USER_DATA / "runtime_logs" / "biointel-running.json"
    if not state_path.is_file():
        return {"state": "not-running", "previous_root": str(old_root) if old_root is not None else ""}
    if old_root is None:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            state = {}
        value = str(state.get("app_root", "")).strip() if isinstance(state, dict) else ""
        old_root = Path(value).expanduser() if value else None
    if old_root is None:
        raise RuntimeError("An existing BioIntel runtime was detected, but its application root could not be verified safely.")
    source = str(TARGET_ROOT / "src")
    fallback_source = str(SOURCE_ROOT_DEFAULT / "src")
    for candidate in (source, fallback_source):
        if candidate not in sys.path and Path(candidate).is_dir():
            sys.path.insert(0, candidate)
    from biointel.operations.runtime_control import stop_local_runtime

    result = stop_local_runtime(old_root, USER_DATA)
    if result.get("state") not in {"stopped", "not-running"}:
        blocking = result.get("blocking_owned_processes", {})
        raise RuntimeError(
            "Existing BioIntel runtime could not be stopped safely before installation activation. "
            f"State={result.get('state')}; verified blocking processes={blocking}."
        )
    result["previous_root"] = str(old_root)
    return result


def _known_folder(kind: str) -> Path:
    fallback = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ("Desktop" if kind == "Desktop" else "AppData/Roaming/Microsoft/Windows/Start Menu/Programs")
    if os.name != "nt":
        return fallback
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"[Environment]::GetFolderPath('{kind}')"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        value = completed.stdout.strip()
        if completed.returncode == 0 and value:
            return Path(value)
    except (OSError, subprocess.SubprocessError):
        pass
    return fallback


def _hidden_start_launcher_path() -> Path:
    return app_directory() / "RUN_BIOINTEL_ACTIVE_HIDDEN.vbs"


def _write_stable_launchers() -> Path:
    app_directory().mkdir(parents=True, exist_ok=True)
    target_run = TARGET_ROOT / "RUN_BOTH_WINDOWS.bat"
    target_stop = TARGET_ROOT / "STOP_BIOINTEL_WINDOWS.bat"
    target_restart = TARGET_ROOT / "RESTART_BIOINTEL_WINDOWS.bat"
    target_repair = TARGET_ROOT / "REPAIR_WINDOWS.bat"
    target_diagnose = TARGET_ROOT / "DIAGNOSE_WINDOWS.bat"
    target_safe_mode = TARGET_ROOT / "SAFE_MODE_WINDOWS.bat"
    target_uninstall = TARGET_ROOT / "UNINSTALL_BIOINTEL_WINDOWS.bat"
    mapping = {
        stable_launcher_path(): (target_run, "/managed"),
        stable_stop_path(): (target_stop, "/managed"),
        stable_restart_path(): (target_restart, "/managed"),
        stable_repair_path(): (target_repair, "/managed"),
        stable_diagnose_path(): (target_diagnose, "/managed"),
        stable_safe_mode_path(): (target_safe_mode, "/managed"),
        stable_uninstall_path(): (target_uninstall, "/managed"),
    }
    for stable, (target, argument) in mapping.items():
        if not target.is_file():
            raise RuntimeError(f"Managed launcher missing: {target.name}")
        stable.write_text(
            "@echo off\r\n"
            "setlocal EnableExtensions DisableDelayedExpansion\r\n"
            f"if not exist \"{target}\" (\r\n"
            "  echo ERROR: Managed BioIntel release is missing. Run INSTALL_WINDOWS.bat again.\r\n"
            "  pause\r\n"
            "  exit /b 1\r\n"
            ")\r\n"
            f"call \"{target}\" {argument} %*\r\n"
            "exit /b %ERRORLEVEL%\r\n",
            encoding="utf-8",
        )
    hidden = _hidden_start_launcher_path()
    hidden.write_text(
        "Option Explicit\r\n"
        "Dim shell\r\n"
        "Set shell = CreateObject(\"WScript.Shell\")\r\n"
        f"shell.Run Chr(34) & \"{stable_launcher_path()}\" & Chr(34), 0, False\r\n",
        encoding="utf-8",
    )
    return hidden


def _remove_managed_shortcuts(folder: Path) -> list[str]:
    if os.name != "nt" or not folder.exists():
        return []
    removed: list[str] = []
    for path in folder.glob("BioIntel AI*.lnk"):
        try:
            path.unlink()
            removed.append(str(path))
        except OSError:
            pass
    return removed


def _create_shortcut(path: Path, target: Path, workdir: Path, description: str, arguments: str = "") -> None:
    if os.name != "nt":
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    icon = TARGET_ROOT / "assets" / "brand" / "biointel-icon-256.ico"
    icon_source = icon if icon.is_file() else target
    env = {
        **os.environ,
        "BIOINTEL_SHORTCUT_PATH": str(path),
        "BIOINTEL_SHORTCUT_TARGET": str(target),
        "BIOINTEL_SHORTCUT_WORKDIR": str(workdir),
        "BIOINTEL_SHORTCUT_ICON": str(icon_source),
        "BIOINTEL_SHORTCUT_DESCRIPTION": description,
        "BIOINTEL_SHORTCUT_ARGUMENTS": arguments,
    }
    command = (
        "$ErrorActionPreference='Stop';"
        "$shell=New-Object -ComObject WScript.Shell;"
        "$link=$shell.CreateShortcut($env:BIOINTEL_SHORTCUT_PATH);"
        "$link.TargetPath=$env:BIOINTEL_SHORTCUT_TARGET;"
        "$link.WorkingDirectory=$env:BIOINTEL_SHORTCUT_WORKDIR;"
        "$link.Description=$env:BIOINTEL_SHORTCUT_DESCRIPTION;"
        "$link.Arguments=$env:BIOINTEL_SHORTCUT_ARGUMENTS;"
        "$link.IconLocation=$env:BIOINTEL_SHORTCUT_ICON;"
        "$link.Save()"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=30,
    )
    if completed.returncode or not path.is_file():
        detail = (completed.stderr or completed.stdout or "unknown shortcut error").strip()
        raise RuntimeError(f"Could not create shortcut {path.name}: {detail[:500]}")


def create_shortcuts_and_active_record() -> dict[str, Any]:
    # Stable launchers are the supported control surface and remain blocking.
    # Explorer shortcuts are optional conveniences: OneDrive policy, endpoint
    # protection, or a locked-down Start Menu must not roll back a verified core install.
    hidden_launcher = _write_stable_launchers()
    desktop = _known_folder("Desktop")
    start_menu = _known_folder("Programs") / "BioIntel AI"
    removed = _remove_managed_shortcuts(desktop) + _remove_managed_shortcuts(start_menu)
    wscript = Path(shutil.which("wscript.exe") or (Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wscript.exe"))
    hidden_arguments = f'"{hidden_launcher}"'
    shortcut_specs = (
        (desktop / "BioIntel AI.lnk", wscript, "Start BioIntel AI", hidden_arguments),
        (start_menu / "BioIntel AI.lnk", wscript, "Start BioIntel AI", hidden_arguments),
        (start_menu / "Stop BioIntel AI.lnk", stable_stop_path(), "Stop BioIntel AI", ""),
        (start_menu / "Restart BioIntel AI.lnk", stable_restart_path(), "Restart BioIntel AI", ""),
        (start_menu / "Repair BioIntel AI.lnk", stable_repair_path(), "Verify and repair BioIntel AI", ""),
        (start_menu / "Diagnose BioIntel AI.lnk", stable_diagnose_path(), "Diagnose BioIntel AI", ""),
        (start_menu / "BioIntel AI Safe Mode.lnk", stable_safe_mode_path(), "Start BioIntel AI in offline safe mode", ""),
        (start_menu / "Uninstall BioIntel AI.lnk", stable_uninstall_path(), "Uninstall BioIntel AI while preserving user data", ""),
    )
    created: list[str] = []
    failures: list[dict[str, str]] = []
    if os.name == "nt":
        for shortcut, target, description, arguments in shortcut_specs:
            try:
                _create_shortcut(shortcut, target, TARGET_ROOT, description, arguments)
                created.append(str(shortcut))
            except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                failures.append({"path": str(shortcut), "error": str(exc)[:500]})
                write(f"WARNING: Optional Explorer shortcut unavailable: {shortcut} ({exc})")

    desktop_shortcut = shortcut_specs[0][0]
    record = active_record(TARGET_ROOT, desktop_shortcut if desktop_shortcut.is_file() else None)
    record["start_menu_shortcut"] = str(shortcut_specs[1][0]) if shortcut_specs[1][0].is_file() else ""
    record["stop_shortcut"] = str(shortcut_specs[2][0]) if shortcut_specs[2][0].is_file() else ""
    record["restart_shortcut"] = str(shortcut_specs[3][0]) if shortcut_specs[3][0].is_file() else ""
    record["repair_shortcut"] = str(shortcut_specs[4][0]) if shortcut_specs[4][0].is_file() else ""
    record["diagnostic_shortcut"] = str(shortcut_specs[5][0]) if shortcut_specs[5][0].is_file() else ""
    record["safe_mode_shortcut"] = str(shortcut_specs[6][0]) if shortcut_specs[6][0].is_file() else ""
    record["uninstall_shortcut"] = str(shortcut_specs[7][0]) if shortcut_specs[7][0].is_file() else ""
    record["shortcut_failures"] = failures
    atomic_write_json(active_record_path(), record)
    return {
        "state": (
            "deferred-non-windows"
            if os.name != "nt"
            else "created"
            if not failures
            else "created-with-optional-shortcut-warnings"
        ),
        "desktop": str(desktop_shortcut) if desktop_shortcut.is_file() else "",
        "start_menu": str(shortcut_specs[1][0]) if shortcut_specs[1][0].is_file() else "",
        "created": created,
        "failures": failures,
        "removed_stale": removed,
        "stable_launcher": str(stable_launcher_path()),
    }

def initialize_professional_databases(python: Path) -> dict[str, Any]:
    """Idempotently initialize and seed writable registries after environment setup."""
    script = TARGET_ROOT / "scripts" / "seed_professional_databases.py"
    if not script.is_file():
        raise RuntimeError("Professional database initialization script is missing.")
    run([str(python), str(script)], cwd=TARGET_ROOT, timeout=900)
    database_dir = USER_DATA / "databases"
    databases = sorted(
        path.name for path in database_dir.glob("*.sqlite3")
        if path.is_file() and not path.name.endswith(("-wal", "-shm"))
    )
    return {
        "state": "initialized",
        "database_directory": str(database_dir),
        "database_count": len(databases),
        "databases": databases,
    }


def run_native_smoke_test(python: Path) -> dict[str, Any]:
    if os.name != "nt":
        return {"state": "deferred-non-windows", "reason": "Native Windows process launch is tested during Windows installation."}
    run(
        [str(python), str(TARGET_ROOT / "scripts" / "windows_smoke_test_step206.py"), "--root", str(TARGET_ROOT)],
        cwd=TARGET_ROOT,
        timeout=600,
    )
    return {"state": "passed"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", default=str(SOURCE_ROOT_DEFAULT))
    parser.add_argument("--force-repair", action="store_true")
    parser.add_argument("--online", action="store_true", help="Use the verified online dependency route instead of the bundled wheelhouse.")
    args = parser.parse_args()
    source_root = Path(args.source_root).resolve()
    status: dict[str, Any] = {
        "schema": f"biointel.step{RELEASE_STEP}.install.v1",
        "started_at": utc_now(),
        "source_root": str(source_root),
        "managed_root": str(TARGET_ROOT),
        "passed": False,
    }
    try:
        check_python_runtime()
        ensure_application_directories()
        with install_lock():
            write(f"BioIntel AI {PRODUCT_VERSION} Step{RELEASE_STEP} managed Windows installation")
            _validate_source_root(source_root)
            _check_target_permissions_and_disk(source_root)
            write("[1/7] Verifying all four ZIP parts, SHA-256 manifest, and offline wheelhouse...")
            verify_source_before_copy(source_root)
            write("[2/7] Stopping any verified older BioIntel runtime safely...")
            status["previous_runtime"] = _stop_active_runtime_before_activation()
            previous_root_text = str(status["previous_runtime"].get("previous_root", "")).strip()
            previous_root = Path(previous_root_text).expanduser() if previous_root_text else None
            write("[3/7] Installing verified source into stable LocalAppData application folder...")
            status["managed_source"] = install_managed_source(source_root)
            write("[4/7] Backing up and migrating existing local SQLite runtime state after clean shutdown...")
            status["database_backup"] = _backup_databases(previous_root)
            status["database_migration"] = _migrate_previous_runtime_databases(previous_root)
            write("Seeding versioned demo and assurance assets into the writable UserData folder...")
            status["bundled_user_data"] = seed_bundled_user_data(source_root)
            write("[5/7] Creating or repairing the isolated Python environment and running post-install checks...")
            python = install_environment(args.force_repair, online=args.online)
            status["dependency_install_mode"] = "online-verified" if args.online else "offline-bundled"
            write("Initializing and repairing writable professional databases and demonstration workspace...")
            status["professional_databases"] = initialize_professional_databases(python)
            write("Initializing the fail-closed V19.6 Engine Control Center (no external downloads)...")
            status["engine_platform"] = _initialize_engine_platform(python)
            write("[6/7] Running native Windows UI/API/worker startup and shutdown smoke test...")
            status["native_smoke_test"] = run_native_smoke_test(python)
            write("[7/7] Refreshing stable launchers, Desktop shortcut, and Start Menu controls...")
            status["shortcuts"] = create_shortcuts_and_active_record()
            (TARGET_ROOT / f".biointel_step{RELEASE_STEP}_installed").write_text(utc_now() + "\n", encoding="utf-8")
            status["core_installation"] = "passed"
            status["optional_services"] = "not-started; offline core remains fully usable"
            status["passed"] = True
            status["message"] = (
                "Managed verified online installation and all available verification gates completed."
                if args.online
                else "Managed offline installation and all available verification gates completed."
            )
            write("INSTALLATION COMPLETE. Use RUN_BOTH_WINDOWS.bat or the BioIntel AI shortcut.")
            return 0
    except Exception as exc:
        status["message"] = str(exc)
        status["traceback"] = traceback.format_exc()
        write("INSTALLATION FAILED: " + str(exc))
        write("No BioIntel project data was deleted. Review the report and run INSTALL_WINDOWS.bat again.")
        return 1
    finally:
        status["finished_at"] = utc_now()
        status["log"] = str(LOG)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(REPORT, status)
        if not status.get("passed"):
            support_root = TARGET_ROOT if (TARGET_ROOT / "scripts" / "step206_support_bundle.py").is_file() else source_root
            support_script = support_root / "scripts" / "step206_support_bundle.py"
            if support_script.is_file():
                try:
                    subprocess.run(
                        [sys.executable, str(support_script), "--root", str(support_root)],
                        cwd=support_root,
                        check=False,
                        timeout=60,
                        env=_env(support_root),
                    )
                except (OSError, subprocess.SubprocessError):
                    pass


if __name__ == "__main__":
    raise SystemExit(main())
