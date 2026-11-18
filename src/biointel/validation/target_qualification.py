from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Iterable

from biointel.database.core import managed_connect


@dataclass(frozen=True)
class QualificationCheck:
    key: str
    passed: bool
    detail: str
    category: str
    blocking: bool = True


@dataclass(frozen=True)
class TargetQualificationReport:
    schema: str
    generated_at_utc: str
    root: str
    platform: dict[str, Any]
    checks: tuple[QualificationCheck, ...]
    passed: bool
    blocking_failures: int
    advisories: int

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["checks"] = [asdict(item) for item in self.checks]
        return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_path_with_spaces(workspace: Path) -> QualificationCheck:
    target = workspace / "BioIntel Step 157 Path With Spaces" / "nested" / "probe.txt"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("biointel-path-safe\n", encoding="utf-8")
        passed = target.read_text(encoding="utf-8") == "biointel-path-safe\n"
        return QualificationCheck("path_with_spaces", passed, str(target), "filesystem")
    except Exception as exc:
        return QualificationCheck("path_with_spaces", False, f"{type(exc).__name__}: {exc}", "filesystem")


def _check_long_path(workspace: Path) -> QualificationCheck:
    parts = ["biointel_long_path_segment_0123456789"] * 7
    target = workspace.joinpath(*parts, "probe.txt")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"ok")
        return QualificationCheck("long_path_write", target.read_bytes() == b"ok", f"length={len(str(target))}", "filesystem", blocking=False)
    except Exception as exc:
        return QualificationCheck("long_path_write", False, f"{type(exc).__name__}: {exc}", "filesystem", blocking=False)


def _check_sqlite(workspace: Path) -> list[QualificationCheck]:
    db = workspace / "sqlite" / "qualification.sqlite3"
    db.parent.mkdir(parents=True, exist_ok=True)
    checks: list[QualificationCheck] = []
    try:
        with managed_connect(db, timeout=30) as connection:
            journal = str(connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript(
                "CREATE TABLE parent(id INTEGER PRIMARY KEY);"
                "CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL REFERENCES parent(id));"
                "INSERT INTO parent(id) VALUES(1);"
                "INSERT INTO child(id,parent_id) VALUES(1,1);"
            )
            connection.commit()
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            fk = connection.execute("PRAGMA foreign_key_check").fetchall()
        checks.append(QualificationCheck("sqlite_wal", journal == "wal", f"journal={journal}", "database"))
        checks.append(QualificationCheck("sqlite_integrity", integrity == "ok", f"integrity={integrity}", "database"))
        checks.append(QualificationCheck("sqlite_foreign_keys", not fk, f"violations={len(fk)}", "database"))
    except Exception as exc:
        checks.append(QualificationCheck("sqlite_runtime", False, f"{type(exc).__name__}: {exc}", "database"))
    return checks


def _check_package_manifest(root: Path) -> list[QualificationCheck]:
    manifest_candidates = sorted((root / "release").glob("step*_package_manifest.json"))
    if not manifest_candidates:
        return [QualificationCheck("package_manifest", False, "No package manifest found", "package")]
    manifest = manifest_candidates[-1]
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        return [QualificationCheck("package_manifest", False, f"{type(exc).__name__}: {exc}", "package")]
    mismatches: list[str] = []
    files = payload.get("files", {})
    for relative, metadata in files.items():
        path = root / relative
        if not path.is_file():
            mismatches.append(f"missing:{relative}")
            continue
        if path.stat().st_size != int(metadata.get("size", -1)):
            mismatches.append(f"size:{relative}")
            continue
        if _sha256(path) != str(metadata.get("sha256", "")):
            mismatches.append(f"sha256:{relative}")
    return [
        QualificationCheck("package_manifest_present", True, manifest.name, "package"),
        QualificationCheck("package_manifest_hashes", not mismatches, json.dumps(mismatches[:50]), "package"),
    ]


def _check_python_import(root: Path) -> QualificationCheck:
    code = (
        "from biointel.scientific_depth import MODULE_PROFILES, native_workflow_catalog;"
        "from biointel.native.engines import ENGINE_REGISTRY, plan_catalog;"
        "assert len(MODULE_PROFILES)==80;"
        "assert len(native_workflow_catalog())==80;"
        "assert len(ENGINE_REGISTRY)>=76;"
        "assert len(plan_catalog())>=78;"
        "print('ok')"
    )
    env = {**os.environ, "PYTHONPATH": str(root / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        detail = (completed.stdout + completed.stderr)[-2000:]
        return QualificationCheck("core_python_import", completed.returncode == 0, detail, "runtime")
    except Exception as exc:
        return QualificationCheck("core_python_import", False, f"{type(exc).__name__}: {exc}", "runtime")


def _app_test(root: Path, page: Path, timeout_seconds: float) -> QualificationCheck:
    relative = page.relative_to(root).as_posix()
    code = (
        "from streamlit.testing.v1 import AppTest;"
        f"app=AppTest.from_file({str(page)!r});"
        f"app.run(timeout={float(timeout_seconds)!r});"
        "errors=list(app.exception);"
        "assert not errors, [str(item.value) for item in errors];"
        "print('ok')"
    )
    env = {**os.environ, "PYTHONPATH": str(root / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=max(10, int(timeout_seconds) + 15),
            check=False,
        )
        detail = (completed.stdout + completed.stderr)[-3000:]
        return QualificationCheck(f"streamlit_app_test:{relative}", completed.returncode == 0, detail, "ui", blocking=False)
    except subprocess.TimeoutExpired:
        return QualificationCheck(f"streamlit_app_test:{relative}", False, "Timed out", "ui", blocking=False)
    except Exception as exc:
        return QualificationCheck(f"streamlit_app_test:{relative}", False, f"{type(exc).__name__}: {exc}", "ui", blocking=False)


def qualify_target(
    root: str | Path,
    *,
    app_test_pages: Iterable[str | Path] = (),
    app_test_timeout_seconds: float = 30.0,
    verify_manifest: bool = True,
) -> TargetQualificationReport:
    root_path = Path(root).expanduser().resolve()
    checks: list[QualificationCheck] = []
    checks.append(QualificationCheck("root_exists", root_path.is_dir(), str(root_path), "package"))
    checks.append(QualificationCheck("python_supported", sys.version_info >= (3, 11), sys.version, "runtime"))
    checks.append(QualificationCheck("disk_free", shutil.disk_usage(root_path).free >= 2 * 1024**3, f"free_bytes={shutil.disk_usage(root_path).free}", "filesystem", blocking=False))
    checks.append(_check_python_import(root_path))

    with tempfile.TemporaryDirectory(prefix="biointel_step157_qualification_") as temporary:
        workspace = Path(temporary)
        checks.append(_check_path_with_spaces(workspace))
        checks.append(_check_long_path(workspace))
        checks.extend(_check_sqlite(workspace))

    if verify_manifest:
        checks.extend(_check_package_manifest(root_path))
    for page_value in app_test_pages:
        page = (root_path / Path(page_value)).resolve()
        if not page.is_file():
            checks.append(QualificationCheck(f"streamlit_app_test:{page_value}", False, "Page missing", "ui", blocking=False))
        else:
            checks.append(_app_test(root_path, page, app_test_timeout_seconds))

    blocking_failures = sum(not item.passed and item.blocking for item in checks)
    advisories = sum(not item.passed and not item.blocking for item in checks)
    return TargetQualificationReport(
        schema="biointel.step157.target-qualification.v1",
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        root=str(root_path),
        platform={
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": sys.version,
            "executable": sys.executable,
        },
        checks=tuple(checks),
        passed=blocking_failures == 0,
        blocking_failures=blocking_failures,
        advisories=advisories,
    )


def save_target_report(report: TargetQualificationReport, destination: str | Path) -> Path:
    path = Path(destination).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


__all__ = ["QualificationCheck", "TargetQualificationReport", "qualify_target", "save_target_report"]
