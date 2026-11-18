from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

SUPPORTED_PYTHON = {(3, 11), (3, 12), (3, 13)}
CORE_MODULES = ("numpy", "pandas", "sklearn", "rdkit", "streamlit", "fastapi", "uvicorn")


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".biointel_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _sqlite_features() -> dict[str, bool]:
    connection = sqlite3.connect(":memory:")
    try:
        json1 = connection.execute("SELECT json_valid('{\"a\":1}')").fetchone()[0] == 1
        fts5 = True
        try:
            connection.execute("CREATE VIRTUAL TABLE probe USING fts5(content)")
        except sqlite3.OperationalError:
            fts5 = False
        return {"json1": bool(json1), "fts5": fts5, "foreign_keys": True}
    finally:
        connection.close()


def _lock_valid(root: Path) -> bool:
    lock = root / "requirements.lock"
    digest_file = root / "requirements.lock.sha256"
    if not lock.is_file() or not digest_file.is_file():
        return False
    import hashlib

    observed = hashlib.sha256(lock.read_bytes()).hexdigest()
    expected = digest_file.read_text(encoding="utf-8").strip().split()[0]
    return observed == expected


def check_environment(root: Path = Path(".")) -> dict[str, Any]:
    root = root.resolve()
    modules = {name: importlib.util.find_spec(name) is not None for name in CORE_MODULES}
    required_files = ["app.py", "src", "pages", "requirements.lock", "VERSION", "pyproject.toml"]
    project_files = {name: (root / name).exists() for name in required_files}
    writable = {
        "reports": _writable(root / "reports"),
        "cache": _writable(root / "cache"),
        "models": _writable(root / "models"),
    }
    disk = shutil.disk_usage(root)
    sqlite_features = _sqlite_features()
    core_checks = {
        "python_supported": sys.version_info[:2] in SUPPORTED_PYTHON,
        "project_files": all(project_files.values()),
        "core_dependencies": all(modules.values()),
        "dependency_lock": _lock_valid(root),
        "workspace_writable": all(writable.values()),
        "sqlite_capabilities": all(sqlite_features.values()),
        "disk_space": disk.free >= 1_000_000_000,
    }
    optional = {
        "git": shutil.which("git") is not None,
        "docker": shutil.which("docker") is not None,
        "tesseract": shutil.which("tesseract") is not None,
    }
    return {
        "ready": all(core_checks.values()),
        "python": {
            "version": platform.python_version(),
            "supported": core_checks["python_supported"],
        },
        "platform": platform.platform(),
        "core_checks": core_checks,
        "project_files": project_files,
        "dependencies": modules,
        "writable_paths": writable,
        "sqlite": sqlite_features,
        "disk": {"free_bytes": disk.free, "total_bytes": disk.total},
        "optional_tools": optional,
        "remediation": [
            "Run the platform installer to install locked dependencies."
            for key, passed in core_checks.items()
            if not passed and key in {"core_dependencies", "dependency_lock"}
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="BioIntel AI developer and installation doctor")
    parser.add_argument("--root", default=".")
    parser.add_argument("--human", action="store_true")
    args = parser.parse_args()
    result = check_environment(Path(args.root))
    if args.human:
        print(f"BioIntel developer doctor: {'READY' if result['ready'] else 'REVIEW'}")
        for key, value in result["core_checks"].items():
            print(f"  {'PASS' if value else 'FAIL'}  {key}")
        for key, value in result["optional_tools"].items():
            print(f"  {'YES ' if value else 'NO  '}  optional:{key}")
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
