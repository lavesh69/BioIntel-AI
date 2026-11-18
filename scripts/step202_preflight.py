from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PART_COUNT = 4


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output")
    parser.add_argument("--allow-non-cp311", action="store_true", help="Source-builder mode only.")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    required = [
        "app.py", "INSTALL_WINDOWS.bat", "RUN_BOTH_WINDOWS.bat", "scripts/install_windows_step196.py",
        "scripts/run_biointel_step196.py", "scripts/run_biointel_step196_runtime.py", "scripts/step202_preflight.py",
        "scripts/run_step202_neuro_demo.py", "src/biointel/neuro_cns/production.py",
        "src/biointel/neuro_cns/demo_showcase.py", "data/neuro_cns/step202_production_feature_registry.json",
        "data/neuro_cns/demo_packs/step202/manifest.json", "wheelhouse/windows-cp311-x64/WHEELHOUSE_METADATA.json",
    ]
    missing = [item for item in required if not (root / item).is_file()]
    add("critical files", not missing, missing or "complete")

    missing_markers: list[str] = []
    for step in (204,):
        for part in range(1, PART_COUNT + 1):
            if not (root / ".release_parts" / f"step{step}_part{part}.ok").is_file():
                missing_markers.append(f"step{step}_part{part}.ok")
    add("four-part Step205 extraction markers", not missing_markers, missing_markers or "4/4 present")

    runtime_ok = struct.calcsize("P") * 8 == 64 and (args.allow_non_cp311 or sys.version_info[:3] == (3, 11, 9))
    add("Python runtime", runtime_ok, {"version": sys.version.split()[0], "bits": struct.calcsize("P") * 8, "required": "CPython 3.11.9 x64"})

    path_length = len(str(root))
    add("path length", path_length <= 180, {"length": path_length, "maximum": 180, "recommended": r"C:\BioIntelAI"})
    free_gb = shutil.disk_usage(root).free / 1024**3
    add("free disk", free_gb >= 1.0, {"available_gb": round(free_gb, 2), "minimum_gb": 1.0})

    writable_probe = root / ".step202-write-probe.tmp"
    writable = False
    try:
        writable_probe.write_text("ok", encoding="utf-8")
        writable = writable_probe.read_text(encoding="utf-8") == "ok"
    except OSError as exc:
        writable_detail: Any = str(exc)
    else:
        writable_detail = "writable"
    finally:
        writable_probe.unlink(missing_ok=True)
    add("installation folder writable", writable, writable_detail)

    demo_manifest = root / "data" / "neuro_cns" / "demo_packs" / "step202" / "manifest.json"
    demo_errors: list[str] = []
    demo_count = 0
    try:
        payload = json.loads(demo_manifest.read_text(encoding="utf-8"))
        directory = demo_manifest.parent
        for row in payload.get("files", []):
            demo_count += 1
            path = directory / str(row.get("path", ""))
            if not path.is_file() or path.stat().st_size != int(row.get("size_bytes", -1)) or sha256_file(path) != str(row.get("sha256", "")):
                demo_errors.append(str(row.get("path", "<invalid>")))
    except Exception as exc:
        demo_errors.append(f"manifest error: {type(exc).__name__}: {exc}")
    add("Step202 demo pack integrity", not demo_errors and demo_count >= 20, {"files": demo_count, "errors": demo_errors})

    wheelhouse = root / "wheelhouse" / "windows-cp311-x64"
    wheels = list(wheelhouse.glob("*.whl")) if wheelhouse.is_dir() else []
    required_tokens = ("streamlit-", "pandas-", "numpy-", "scipy-", "scikit_learn-", "rdkit-", "biopython-")
    names = [path.name.lower() for path in wheels]
    absent = [token for token in required_tokens if not any(name.startswith(token) for name in names)]
    add("offline wheelhouse", bool(wheels) and not absent, {"wheel_count": len(wheels), "missing_core_prefixes": absent})

    passed = all(item["passed"] for item in checks)
    report = {
        "schema": "biointel.step203.preflight.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "root": str(root),
        "passed": passed,
        "checks": checks,
        "recovery": [
            "Extract all four matching Step205 ZIP files into one new empty folder.",
            r"Use a short writable path such as C:\BioIntelAI.",
            "Run INSTALL_WINDOWS.bat. It detects an exact Python 3.11.9 installation or uses a safe current-user installer outside %TEMP%.",
            "Run INSTALL_WINDOWS.bat again if the environment exists but imports fail.",
        ],
    }
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = root / output
        candidates = [output]
    else:
        local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        candidates = [
            local / "BioIntelAI" / "UserData" / "reports" / "step203-preflight.json",
            root / "reports" / "step203-preflight-runtime.json",
        ]
    written = None
    for output in candidates:
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            written = output
            break
        except OSError:
            continue
    if written is not None:
        report["report_path"] = str(written)
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
