from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.database.core import managed_connect
from biointel.intelligence.data_intelligence import all_database_health
from biointel.step123.optimization import runtime_audit
from biointel.utils.atomic_io import atomic_write_json


def main() -> int:
    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    add("Version", version == "13.2.0", f"VERSION={version}")

    required = [
        "src/biointel/step123/optimization.py",
        "scripts/step123_optimize_workspace.py",
        "OPTIMIZE_STEP123_WINDOWS.bat",
        "RUN_APP_SMOOTH_WINDOWS.bat",
        "scripts/run_biointel_step97.py",
    ]
    missing = [item for item in required if not (ROOT / item).is_file()]
    add("Required optimization files", not missing, f"missing={missing}")

    direct_sqlite = []
    for base in (ROOT / "src", ROOT / "pages"):
        for path in base.rglob("*.py"):
            if path == ROOT / "src" / "biointel" / "database" / "core.py":
                continue
            if "sqlite3.connect(" in path.read_text(encoding="utf-8", errors="replace"):
                direct_sqlite.append(path.relative_to(ROOT).as_posix())
    add("Managed SQLite lifecycle", not direct_sqlite, f"direct_connections={len(direct_sqlite)}")

    with tempfile.TemporaryDirectory(prefix="biointel-step123-") as temporary:
        database = Path(temporary) / "lifecycle.sqlite3"
        connection = managed_connect(database)
        with connection as active:
            active.execute("CREATE TABLE sample(value INTEGER)")
            active.execute("INSERT INTO sample VALUES (1)")
        closed = False
        try:
            connection.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            closed = True
        add("SQLite handles close after context", closed, "managed connection closed")

    compile_targets = [ROOT / "app.py", *sorted((ROOT / "src").rglob("*.py")), *sorted((ROOT / "pages").rglob("*.py"))]
    compile_failures: list[str] = []
    for path in compile_targets:
        try:
            compile(path.read_bytes(), str(path), "exec", dont_inherit=True)
        except Exception as exc:
            compile_failures.append(f"{path.relative_to(ROOT).as_posix()}: {exc}")
    add(
        "Python compilation",
        not compile_failures,
        f"files={len(compile_targets)} failures={len(compile_failures)}",
    )

    health = all_database_health(ROOT)
    add(
        "Database fleet",
        int(health["database_count"]) > 0
        and int(health["healthy_count"]) == int(health["database_count"]),
        f"healthy={health['healthy_count']}/{health['database_count']} rows={health['total_rows']}",
    )

    audit = runtime_audit(ROOT)
    add(
        "Runtime audit",
        audit.database_count == audit.healthy_databases and audit.database_count > 0,
        f"health_ms={audit.database_health_ms} cache_dirs={audit.cache_directories}",
    )

    launcher = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_biointel_step97.py"), "--self-check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    add("Windows launcher self-check", launcher.returncode == 0, launcher.stdout.strip()[-500:])

    report = {
        "schema": "biointel.step123.verification.v1",
        "release": version,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "checks": checks,
        "passed_checks": sum(bool(item["passed"]) for item in checks),
        "total_checks": len(checks),
        "passed": all(bool(item["passed"]) for item in checks),
        "runtime_audit": audit.__dict__,
        "database_health": {
            "count": health["database_count"],
            "healthy": health["healthy_count"],
            "rows": health["total_rows"],
        },
    }
    output = ROOT / "reports" / "step123_verification.json"
    atomic_write_json(output, report)
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
