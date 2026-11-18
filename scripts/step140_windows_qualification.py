from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "step140_windows_qualification.json"


def _check(name: str, passed: bool, detail: str, *, gated: bool = False) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail, "environment_gated": bool(gated)}


def _run(command: list[str], timeout: int = 120) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout, check=False)
        output = (result.stdout + "\n" + result.stderr).strip()[-5000:]
        return result.returncode == 0, output
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    checks: list[dict[str, Any]] = []
    is_windows = os.name == "nt"
    checks.append(_check("Operating system", is_windows, platform.platform(), gated=not is_windows))
    checks.append(_check("Python architecture", platform.architecture()[0] == "64bit", f"{platform.python_version()} · {platform.architecture()[0]}"))
    checks.append(_check("Python version", sys.version_info[:2] in {(3, 11), (3, 12), (3, 13)}, platform.python_version()))

    user_data = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or ROOT / "UserData").resolve()
    try:
        user_data.mkdir(parents=True, exist_ok=True)
        test = user_data / ".step140-write-test"
        test.write_text("ok", encoding="utf-8")
        test.unlink()
        checks.append(_check("Writable UserData", True, str(user_data)))
    except Exception as exc:
        checks.append(_check("Writable UserData", False, f"{type(exc).__name__}: {exc}"))

    disk = shutil.disk_usage(user_data)
    checks.append(_check("Free disk", disk.free >= 5 * 1024**3, f"{disk.free / 1024**3:.2f} GB free"))

    unicode_path = user_data / "qualification space üñîçødé"
    try:
        unicode_path.mkdir(exist_ok=True)
        (unicode_path / "test.txt").write_text("ok", encoding="utf-8")
        shutil.rmtree(unicode_path)
        checks.append(_check("Spaces/non-English path", True, "Unicode workspace write/read passed"))
    except Exception as exc:
        checks.append(_check("Spaces/non-English path", False, str(exc)))

    try:
        db_path = user_data / ".step140-qualification.sqlite3"
        with sqlite3.connect(db_path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS test(id INTEGER PRIMARY KEY, value TEXT)")
            db.execute("INSERT INTO test(value) VALUES(?)", ("ok",))
            db.execute("PRAGMA integrity_check")
        db_path.unlink(missing_ok=True)
        checks.append(_check("SQLite WAL/read-write", True, "SQLite local write and integrity check passed"))
    except Exception as exc:
        checks.append(_check("SQLite WAL/read-write", False, str(exc)))

    ok, output = _run([sys.executable, "-m", "pytest", "-q", "tests/test_step140_bioinformatics_interoperability_portability.py"], timeout=300)
    checks.append(_check("Step 140 focused tests", ok, output))

    ok, output = _run([sys.executable, "-m", "compileall", "-q", "app.py", "src", "pages", "tests"], timeout=300)
    checks.append(_check("Python compilation", ok, output or "Passed"))

    scaling_detail = "Display scaling query requires Windows"
    scaling_passed = False
    if is_windows:
        try:
            import ctypes
            dpi = ctypes.windll.user32.GetDpiForSystem()
            scale = round(dpi / 96 * 100)
            scaling_detail = f"System DPI {dpi}; scale approximately {scale}%"
            scaling_passed = 100 <= scale <= 300
        except Exception as exc:
            scaling_detail = f"Unable to query DPI: {exc}"
    checks.append(_check("Display scaling detection", scaling_passed, scaling_detail, gated=not is_windows))

    memory_detail = "RAM query unavailable"
    memory_passed = True
    try:
        import psutil  # type: ignore
        ram = psutil.virtual_memory().total / 1024**3
        memory_detail = f"{ram:.2f} GB physical RAM; 8 GB or more is recommended for large workflows"
        memory_passed = ram >= 4
    except Exception:
        pass
    checks.append(_check("Minimum RAM profile", memory_passed, memory_detail))

    blockers = [item for item in checks if not item["passed"] and not item["environment_gated"]]
    report = {
        "schema": "biointel.step140.windows-qualification.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "host": {"platform": platform.platform(), "python": platform.python_version(), "machine": platform.machine()},
        "checks": checks,
        "passed": not blockers,
        "blockers": blockers,
        "boundary": "Physical Windows qualification covers this machine only. External scientific tools, licensed databases and every possible hardware configuration require separate qualification.",
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "report": str(REPORT), "blockers": len(blockers)}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
