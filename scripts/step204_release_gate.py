from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PRODUCT_VERSION = "15.4.0"
RELEASE_STEP = 204
PART_COUNT = 4
REQUIRED_PYTHON = (3, 11, 9)
MANIFEST_NAME = "STEP204_SOURCE_MANIFEST_SHA256.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_report(root: Path, requested: str | None, payload: dict[str, Any]) -> Path | None:
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    candidates = [Path(requested)] if requested else [
        local / "BioIntelAI" / "UserData" / "reports" / "step204-release-gate.json",
        root / "reports" / "step204-release-gate-runtime.json",
    ]
    for candidate in candidates:
        path = candidate if candidate.is_absolute() else root / candidate
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            return path
        except OSError:
            continue
    return None


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
        "app.py", "INSTALL_WINDOWS.bat", "RUN_BOTH_WINDOWS.bat", "VERSION",
        "STEP204_RELEASE.json", MANIFEST_NAME, "requirements.lock",
        "scripts/bootstrap.py", "scripts/install_windows_step196.py",
        "scripts/run_biointel_step196.py", "scripts/run_biointel_step196_runtime.py",
        "scripts/run_biointel_step97.py", "scripts/step204_release_gate.py",
        "scripts/find_python311_windows.ps1", "scripts/install_python311_user.ps1",
        "wheelhouse/windows-cp311-x64/WHEELHOUSE_METADATA.json",
    ]
    missing = [item for item in required if not (root / item).is_file()]
    add("critical files", not missing, missing or "complete")

    missing_markers = [
        f"step{RELEASE_STEP}_part{part}.ok" for part in range(1, PART_COUNT + 1)
        if not (root / ".release_parts" / f"step{RELEASE_STEP}_part{part}.ok").is_file()
    ]
    add("four-part Step204 extraction", not missing_markers, missing_markers or "4/4 present")

    # Legacy internal validators remain compatibility-safe; these markers are
    # package metadata, not a claim that Step204 has five physical ZIP parts.
    compatibility_missing = [
        f"step{step}_part{part}.ok"
        for step in (196, 200, 201, 202, 203)
        for part in range(1, 6)
        if not (root / ".release_parts" / f"step{step}_part{part}.ok").is_file()
    ]
    add("legacy validator compatibility markers", not compatibility_missing, compatibility_missing or "25/25 present")

    try:
        version = (root / "VERSION").read_text(encoding="utf-8-sig").strip()
        release = json.loads((root / "STEP204_RELEASE.json").read_text(encoding="utf-8-sig"))
        release_ok = (
            version == PRODUCT_VERSION
            and str(release.get("version", "")).strip() == PRODUCT_VERSION
            and int(release.get("step", 0) or 0) == RELEASE_STEP
            and int(release.get("part_count", 0) or 0) == PART_COUNT
            and str(release.get("python_runtime", "")).strip() == "CPython 3.11.9 x64"
        )
        add("active release identity", release_ok, {"VERSION": version, "release": release})
    except Exception as exc:
        add("active release identity", False, f"{type(exc).__name__}: {exc}")

    runtime_ok = struct.calcsize("P") * 8 == 64 and (
        args.allow_builder_python or sys.version_info[:3] == REQUIRED_PYTHON
    )
    add("Python runtime", runtime_ok, {
        "current": sys.version.split()[0], "bits": struct.calcsize("P") * 8,
        "required": "CPython 3.11.9 x64", "builder_override": bool(args.allow_builder_python),
    })

    path_length = len(str(root))
    add("path length", path_length <= 180, {"length": path_length, "maximum": 180})
    try:
        free_gb = shutil.disk_usage(root).free / 1024**3
        add("free disk", free_gb >= 1.0, {"available_gb": round(free_gb, 2), "minimum_gb": 1.0})
    except OSError as exc:
        add("free disk", False, str(exc))

    probe = root / ".step204-write-probe.tmp"
    try:
        probe.write_text("ok", encoding="utf-8")
        writable = probe.read_text(encoding="utf-8") == "ok"
        detail: Any = "writable"
    except OSError as exc:
        writable, detail = False, str(exc)
    finally:
        probe.unlink(missing_ok=True)
    add("installation folder writable", writable, detail)

    if not args.quick:
        try:
            manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8-sig"))
            rows = manifest.get("entries", [])
            if not isinstance(rows, list):
                raise ValueError("manifest entries must be a list")
            bad: list[str] = []
            jobs: list[tuple[str, Path, str]] = []
            for row in rows:
                rel = str(row.get("path", ""))
                target = root / rel
                expected_size = int(row.get("size_bytes", -1))
                expected_hash = str(row.get("sha256", ""))
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
            add("Step204 SHA-256 source manifest", not bad and len(rows) > 23000, {
                "tracked_files": len(rows), "deep_hashes": bool(args.deep_hashes),
                "bad_count": len(bad), "bad_files": bad[:25],
            })
        except Exception as exc:
            add("Step204 SHA-256 source manifest", False, f"{type(exc).__name__}: {exc}")

        wheelhouse = root / "wheelhouse" / "windows-cp311-x64"
        wheels = list(wheelhouse.glob("*.whl")) if wheelhouse.is_dir() else []
        prefixes = ("streamlit-", "pandas-", "numpy-", "scipy-", "scikit_learn-", "rdkit-", "biopython-")
        names = [path.name.lower() for path in wheels]
        absent = [prefix for prefix in prefixes if not any(name.startswith(prefix) for name in names)]
        add("offline wheelhouse", bool(wheels) and not absent, {"wheel_count": len(wheels), "missing": absent})

    passed = all(row["passed"] for row in checks)
    payload = {
        "schema": "biointel.step204.release-gate.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "root": str(root), "passed": passed, "checks": checks,
        "recovery": [
            "Extract all four matching Step204 ZIP parts into one new empty folder.",
            "Install 64-bit CPython 3.11.9 exactly, then run INSTALL_WINDOWS.bat again.",
            "Keep the folder writable and avoid moving it after installation.",
        ],
    }
    written = _write_report(root, args.output, payload)
    if written:
        payload["report_path"] = str(written)
    print(json.dumps(payload, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
