from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from typing import Any

from step206_contract import (
    CURRENT_SOURCE_MANIFEST_NAME,
    MANIFEST_NAME,
    PACKAGE_GENERATION,
    PART_COUNT,
    PRODUCT_VERSION,
    RELEASE_NAME,
    RELEASE_STEP,
    REQUIRED_PYTHON,
    REQUIRED_PYTHON_TEXT,
    app_home,
    managed_release_root,
    user_data_directory,
    utc_now,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_report(root: Path, requested: str | None, payload: dict[str, Any]) -> Path | None:
    candidates = [Path(requested)] if requested else [
        user_data_directory() / "reports" / f"step{RELEASE_STEP}-release-gate.json",
        root / "reports" / f"step{RELEASE_STEP}-release-gate-runtime.json",
    ]
    for candidate in candidates:
        path = candidate if candidate.is_absolute() else root / candidate
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".tmp")
            temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, path)
            return path
        except OSError:
            continue
    return None


def _source_manifest_rows(root: Path) -> tuple[Path, list[dict[str, Any]]]:
    candidates = (
        (root / CURRENT_SOURCE_MANIFEST_NAME, "entries"),
        (root / CURRENT_SOURCE_MANIFEST_NAME, "files"),
        (root / MANIFEST_NAME, "entries"),
        (root / MANIFEST_NAME, "files"),
    )
    failures: list[str] = []
    for path, row_key in candidates:
        if not path.is_file():
            failures.append(f"{path.name}: missing")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            rows = payload.get(row_key, [])
            if not isinstance(rows, list) or not rows:
                continue
            return path, rows
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            failures.append(f"{path.name}: {type(exc).__name__}: {exc}")
    raise ValueError("; ".join(failures))


def _directory_size_from_manifest(root: Path) -> int:
    try:
        _path, rows = _source_manifest_rows(root)
        return sum(int(row.get("size_bytes", 0) or 0) for row in rows if isinstance(row, dict))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output")
    parser.add_argument("--deep-hashes", action="store_true")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--allow-builder-python", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    required = [
        "app.py",
        "INSTALL_WINDOWS.bat",
        "RUN_BOTH_WINDOWS.bat",
        "STOP_BIOINTEL_WINDOWS.bat",
        "RESTART_BIOINTEL_WINDOWS.bat",
        "REPAIR_WINDOWS.bat",
        "DIAGNOSE_WINDOWS.bat",
        "SAFE_MODE_WINDOWS.bat",
        "UNINSTALL_BIOINTEL_WINDOWS.bat",
        "RUN_ULTIMATE_ACCEPTANCE_WINDOWS.bat",
        "VERSION",
        RELEASE_NAME,
        MANIFEST_NAME,
        CURRENT_SOURCE_MANIFEST_NAME,
        "requirements.lock",
        "scripts/bootstrap.py",
        "scripts/step206_contract.py",
        "scripts/install_windows_step206.py",
        "scripts/run_biointel_step206.py",
        "scripts/runtime_supervisor_step206.py",
        "scripts/runtime_control_step206.py",
        "scripts/windows_smoke_test_step206.py",
        "scripts/streamlit_startup_check_step206.py",
        "scripts/verify_windows_runtime_compatibility_step206.py",
        "scripts/step206_support_bundle.py",
        "scripts/diagnose_windows_step206.py",
        "scripts/uninstall_windows_step206.py",
        "scripts/ultimate_acceptance_step206.py",
        "scripts/export_ultimate_registries.py",
        "src/biointel/product_registry.py",
        "scripts/find_python311_windows.ps1",
        "scripts/install_python311_user.ps1",
        "wheelhouse/windows-cp311-x64/WHEELHOUSE_METADATA.json",
    ]
    missing = [item for item in required if not (root / item).is_file()]
    add("critical files", not missing, missing or "complete")

    missing_markers = [
        f"step{RELEASE_STEP}_part{part}.ok"
        for part in range(1, PART_COUNT + 1)
        if not (root / ".release_parts" / f"step{RELEASE_STEP}_part{part}.ok").is_file()
    ]
    add(f"four-part Step{RELEASE_STEP} extraction", not missing_markers, missing_markers or "4/4 present")

    try:
        version = (root / "VERSION").read_text(encoding="utf-8-sig").strip()
        release = json.loads((root / RELEASE_NAME).read_text(encoding="utf-8-sig"))
        with (root / "pyproject.toml").open("rb") as handle:
            project_version = str(tomllib.load(handle).get("project", {}).get("version", "")).strip()
        release_ok = (
            version == PRODUCT_VERSION
            and project_version == PRODUCT_VERSION
            and str(release.get("version", "")).strip() == PRODUCT_VERSION
            and int(release.get("step", 0) or 0) == RELEASE_STEP
            and int(release.get("part_count", 0) or 0) == PART_COUNT
            and str(release.get("package_generation", "")).strip() == PACKAGE_GENERATION
            and str(release.get("python_runtime", "")).strip() == REQUIRED_PYTHON_TEXT
        )
        add("active release identity", release_ok, {"VERSION": version, "pyproject": project_version, "release": release})
    except Exception as exc:  # report malformed release metadata calmly
        add("active release identity", False, f"{type(exc).__name__}: {exc}")

    runtime_ok = struct.calcsize("P") * 8 == 64 and (
        args.allow_builder_python or sys.version_info >= (3, 11)
    )
    add(
        "Python runtime",
        runtime_ok,
        {
            "current": sys.version.split()[0],
            "bits": struct.calcsize("P") * 8,
            "required": REQUIRED_PYTHON_TEXT,
            "builder_override": bool(args.allow_builder_python),
        },
    )

    managed = managed_release_root()
    add(
        "managed application path",
        len(str(managed)) <= 120,
        {"path": str(managed), "length": len(str(managed)), "maximum": 120},
    )

    try:
        app_home().mkdir(parents=True, exist_ok=True)
        probe = app_home() / f".step{RELEASE_STEP}-write-probe.tmp"
        probe.write_text("ok", encoding="utf-8")
        writable = probe.read_text(encoding="utf-8") == "ok"
        detail: Any = str(app_home())
    except OSError as exc:
        writable, detail = False, str(exc)
    finally:
        try:
            probe.unlink(missing_ok=True)
        except (OSError, UnboundLocalError):
            pass
    add("managed application directory writable", writable, detail)

    try:
        source_bytes = _directory_size_from_manifest(root)
        required_bytes = max(2 * 1024**3, source_bytes + 500 * 1024**2)
        free_bytes = shutil.disk_usage(app_home()).free
        add(
            "managed-install free disk",
            free_bytes >= required_bytes,
            {
                "available_gb": round(free_bytes / 1024**3, 2),
                "required_gb": round(required_bytes / 1024**3, 2),
                "manifest_source_gb": round(source_bytes / 1024**3, 2),
            },
        )
    except OSError as exc:
        add("managed-install free disk", False, str(exc))

    source_readable = root.is_dir() and all((root / item).exists() for item in ("app.py", "scripts", "src"))
    add("extracted source readable", source_readable, str(root))

    if os.name == "nt":
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        add("Windows PowerShell", bool(powershell), powershell or "not found")
    else:
        add("Windows PowerShell", True, "deferred to native Windows installation")

    if not args.quick:
        try:
            manifest_path, rows = _source_manifest_rows(root)
            current_manifest = manifest_path == root / CURRENT_SOURCE_MANIFEST_NAME
            bad: list[str] = []
            jobs: list[tuple[str, Path, str]] = []
            for row in rows:
                if not isinstance(row, dict):
                    bad.append("<invalid-manifest-row>")
                    continue
                rel = str(row.get("path", ""))
                rel_path = PurePosixPath(rel)
                if not rel or rel_path.is_absolute() or ".." in rel_path.parts:
                    bad.append(rel or "<empty-manifest-path>")
                    continue
                target = root / rel
                expected_size = int(row.get("size_bytes", -1))
                expected_hash = str(row.get("sha256", ""))
                # Only the legacy manifest tracked mutable runtime databases.
                # Ignore mutable runtime databases, jobs log, and temp files during deep hash checks
                if rel.endswith((".sqlite", ".sqlite3", ".sqlite3-journal", ".db", ".log", ".jsonl", ".tmp")) or rel.startswith("reports/"):
                    if target.is_file():
                        continue

                if not target.is_file() or target.stat().st_size != expected_size:
                    bad.append(rel)
                elif args.deep_hashes:
                    jobs.append((rel, target, expected_hash))
            if jobs:
                workers = min(16, max(4, os.cpu_count() or 4))
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    hashes = executor.map(lambda job: sha256_file(job[1]), jobs)
                    for job, actual in zip(jobs, hashes, strict=True):
                        if actual != job[2]:
                            bad.append(job[0])
            add(
                f"Step{RELEASE_STEP} SHA-256 source manifest",
                not bad and len(rows) > 10000,
                {
                    "manifest": manifest_path.relative_to(root).as_posix(),
                    "tracked_files": len(rows),
                    "deep_hashes": bool(args.deep_hashes),
                    "bad_count": len(bad),
                    "bad_files": bad[:25],
                },
            )
        except Exception as exc:
            add(f"Step{RELEASE_STEP} SHA-256 source manifest", False, f"{type(exc).__name__}: {exc}")

        wheelhouse = root / "wheelhouse" / "windows-cp311-x64"
        wheels = list(wheelhouse.glob("*.whl")) if wheelhouse.is_dir() else []
        prefixes = (
            "streamlit-",
            "pandas-",
            "numpy-",
            "scipy-",
            "scikit_learn-",
            "rdkit-",
            "biopython-",
        )
        names = [path.name.lower() for path in wheels]
        absent = [prefix for prefix in prefixes if not any(name.startswith(prefix) for name in names)]
        setuptools_compat = "setuptools-80.9.0-py3-none-any.whl" in names and not any(
            name.startswith("setuptools-83.") for name in names
        )
        add(
            "offline wheelhouse",
            bool(wheels) and not absent and setuptools_compat,
            {
                "wheel_count": len(wheels),
                "missing": absent,
                "setuptools_pkg_resources_compatibility": setuptools_compat,
            },
        )

    passed = all(row["passed"] for row in checks)
    payload = {
        "schema": f"biointel.step{RELEASE_STEP}.release-gate.v1",
        "generated_at_utc": utc_now(),
        "root": str(root),
        "managed_root": str(managed),
        "passed": passed,
        "checks": checks,
        "recovery": [
            f"Extract all four matching Step{RELEASE_STEP} ZIP parts into one new folder, or run EXTRACT_AND_INSTALL_STEP220_WINDOWS.bat beside the ZIPs.",
            "Run INSTALL_WINDOWS.bat; it installs to a stable LocalAppData application folder.",
            "If Python is absent, allow the signed Python 3.11 installer or install a compatible 3.11.x x64 build manually and retry.",
        ],
    }
    written = _write_report(root, args.output, payload)
    if written:
        payload["report_path"] = str(written)
    print(json.dumps(payload, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
