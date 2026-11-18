from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
import struct
import subprocess
import time
import sys
import traceback
import warnings
from pathlib import Path
from typing import Any

from step206_contract import RELEASE_STEP, REQUIRED_PYTHON, REQUIRED_PYTHON_TEXT, user_data_directory, utc_now

SETUPTOOLS_COMPAT_VERSION = "80.9.0"
IMPORT_TIMEOUT_SECONDS = 45
REQUIRED_IMPORTS = (
    "numpy",
    "pandas",
    "scipy",
    "sklearn",
    "streamlit",
    "fastapi",
    "Bio",
    "rdkit",
    "reportlab",
    "pypdf",
    "nibabel",
    "pydicom",
    "mne",
    "pymzml",
    "ont_fast5_api",
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _import_environment() -> dict[str, str]:
    user_data = user_data_directory()
    cache_root = user_data / "cache"
    runtime_temp = user_data.parent / "Temp" / "runtime-verify"
    for path in (cache_root / "numba", cache_root / "matplotlib", runtime_temp):
        path.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "BIOINTEL_USER_DATA_DIR": str(user_data),
            "NUMBA_CACHE_DIR": str(cache_root / "numba"),
            "MPLCONFIGDIR": str(cache_root / "matplotlib"),
            "TEMP": str(runtime_temp),
            "TMP": str(runtime_temp),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return env


def _probe_import(module_name: str) -> dict[str, Any]:
    started = time.monotonic()
    command = [
        sys.executable,
        "-c",
        (
            "import importlib,sys;"
            "module=importlib.import_module(sys.argv[1]);"
            "print(getattr(module,'__version__','imported'))"
        ),
        module_name,
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_import_environment(),
            timeout=IMPORT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "seconds": round(time.monotonic() - started, 3),
            "error": f"timed out after {IMPORT_TIMEOUT_SECONDS} seconds",
        }
    detail = (completed.stdout or completed.stderr or "imported").strip()[-1000:]
    return {
        "passed": completed.returncode == 0,
        "seconds": round(time.monotonic() - started, 3),
        "returncode": completed.returncode,
        "detail": detail,
    }


def verify(root: Path, *, strict_python: bool) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    bits = struct.calcsize("P") * 8
    python_ok = sys.version_info[:2] == REQUIRED_PYTHON and bits == 64
    add(
        "Python runtime",
        python_ok or not strict_python,
        {
            "current": sys.version.split()[0],
            "bits": bits,
            "required": REQUIRED_PYTHON_TEXT,
            "strict": strict_python,
        },
    )

    try:
        setuptools_version = importlib.metadata.version("setuptools")
    except importlib.metadata.PackageNotFoundError:
        setuptools_version = "missing"
    add(
        "setuptools runtime compatibility pin",
        setuptools_version == SETUPTOOLS_COMPAT_VERSION,
        {
            "installed": setuptools_version,
            "required": SETUPTOOLS_COMPAT_VERSION,
            "reason": "ont-fast5-api 4.1.3 imports pkg_resources at runtime",
        },
    )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            warnings.simplefilter("ignore", UserWarning)
            importlib.import_module("pkg_resources")
        add("pkg_resources compatibility module", True, "imported")
    except Exception as exc:
        add("pkg_resources compatibility module", False, f"{type(exc).__name__}: {exc}")

    import_failures: dict[str, str] = {}
    import_probes: dict[str, dict[str, Any]] = {}
    for module_name in REQUIRED_IMPORTS:
        probe = _probe_import(module_name)
        import_probes[module_name] = probe
        if not probe.get("passed"):
            import_failures[module_name] = str(probe.get("error") or probe.get("detail") or "import failed")
    add(
        "complete scientific imports",
        not import_failures,
        {
            "import_count": len(REQUIRED_IMPORTS),
            "failures": import_failures,
            "probes": import_probes,
        },
    )

    plugin_detail: Any = "not checked because ont_fast5_api import failed"
    plugin_ok = "ont_fast5_api" not in import_failures
    if plugin_ok:
        try:
            from ont_fast5_api.compression_settings import register_plugin

            plugin_path = Path(register_plugin())
            plugin_ok = plugin_path.is_dir()
            plugin_detail = {"path": str(plugin_path), "exists": plugin_path.exists(), "is_dir": plugin_path.is_dir()}
        except Exception as exc:
            plugin_ok = False
            plugin_detail = f"{type(exc).__name__}: {exc}"
    add("FAST5 VBZ plugin registration", plugin_ok, plugin_detail)

    passed = all(row["passed"] for row in checks)
    return {
        "schema": f"biointel.step{RELEASE_STEP}.windows-runtime-compatibility.v1",
        "generated_at": utc_now(),
        "root": str(root),
        "python": sys.executable,
        "passed": passed,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Verify the complete Step{RELEASE_STEP} Windows runtime import contract.")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output")
    parser.add_argument("--strict-python", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    try:
        payload = verify(root, strict_python=args.strict_python)
    except Exception as exc:
        payload = {
            "schema": f"biointel.step{RELEASE_STEP}.windows-runtime-compatibility.v1",
            "generated_at": utc_now(),
            "root": str(root),
            "python": sys.executable,
            "passed": False,
            "fatal_error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }

    output = Path(args.output) if args.output else user_data_directory() / "reports" / f"step{RELEASE_STEP}-windows-runtime-compatibility.json"
    if not output.is_absolute():
        output = root / output
    try:
        _write_json(output, payload)
        payload["report_path"] = str(output)
    except OSError as exc:
        payload["report_write_error"] = str(exc)

    print(json.dumps(payload, indent=2))
    return 0 if payload.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
