from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "step68_runtime_repair_qualification.json"


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def run(command: list[str], *, timeout: int = 360) -> dict[str, object]:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
        return {
            "passed": completed.returncode == 0,
            "returncode": completed.returncode,
            "timed_out": False,
            "stdout": completed.stdout[-5000:],
            "stderr": completed.stderr[-5000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "passed": False,
            "returncode": 124,
            "timed_out": True,
            "stdout": str(exc.stdout or "")[-5000:],
            "stderr": str(exc.stderr or "")[-5000:],
        }


def database_summary() -> dict[str, object]:
    databases = []
    for base in (ROOT / "data", ROOT / "reports"):
        for pattern in ("*.sqlite", "*.sqlite3", "*.db", "*.db3"):
            databases.extend(sorted(base.rglob(pattern)))
    unique = []
    seen: set[Path] = set()
    for path in databases:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    healthy = 0
    rows = 0
    fk_violations = 0
    failures: list[dict[str, str]] = []
    for path in unique:
        try:
            connection = sqlite3.connect(path)
            try:
                integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
                if integrity != "ok":
                    raise RuntimeError(str(integrity))
                fk_violations += len(connection.execute("PRAGMA foreign_key_check").fetchall())
                tables = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
                for (name,) in tables:
                    quoted = str(name).replace('"', '""')
                    rows += int(connection.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0])
                healthy += 1
            finally:
                connection.close()
        except Exception as exc:  # noqa: BLE001
            failures.append({"database": str(path.relative_to(ROOT)), "error": f"{type(exc).__name__}: {exc}"})
    return {
        "database_count": len(unique),
        "healthy": healthy,
        "rows": rows,
        "foreign_key_violations": fk_violations,
        "failures": failures,
        "passed": healthy == len(unique) and fk_violations == 0,
    }


def main() -> int:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    lint = run([sys.executable, "-m", "ruff", "check", "."])
    compile_check = run([sys.executable, "-m", "compileall", "-q", "src", "pages", "scripts", "tests"])
    step68_tests = run([sys.executable, "-m", "pytest", "-q", "tests/test_step68_runtime_error_repairs.py"])
    regressions = load_json("reports/step68_regression_summary.json")
    runtime = load_json("reports/step68_streamlit_runtime_matrix.json")
    api = load_json("reports/step68_api_smoke.json")
    performance = load_json("reports/step68_performance_benchmark.json")
    store = load_json("reports/step68_store_release_verification.json")
    secrets = load_json("reports/step68_secret_scan.json")
    databases = database_summary()

    checks = {
        "version": version,
        "ruff": lint,
        "compilation": compile_check,
        "step68_tests": step68_tests,
        "focused_regressions": regressions,
        "streamlit_runtime": runtime,
        "api_smoke": api,
        "performance": performance,
        "store": {
            "implementation_ready": store.get("implementation_ready"),
            "internal_failures": store.get("internal_failures"),
            "external_actions": store.get("external_actions"),
        },
        "secrets": secrets,
        "databases": databases,
    }
    passed = all(
        [
            version == "6.8.0",
            bool(lint["passed"]),
            bool(compile_check["passed"]),
            bool(step68_tests["passed"]),
            regressions.get("passed") is True,
            regressions.get("tests") == 171,
            runtime.get("passed_scenarios") == runtime.get("scenario_count") == 15,
            api.get("passed_cases") == api.get("case_count") == 9,
            performance.get("balanced_speedup_vs_exhaustive", 0) > 1,
            store.get("internal_failures") == 0,
            secrets.get("passed") is True,
            databases.get("passed") is True,
            databases.get("database_count") == 22,
        ]
    )
    payload = {
        "schema": "biointel.step68.runtime-repair-qualification.v1",
        "passed": passed,
        "checks": checks,
        "historical_full_suite_note": (
            "A single monolithic historical test run can exceed the environment execution cap. "
            "No complete historical-suite pass is claimed. The release is supported by 171 isolated focused/regression tests, "
            "15 representative Streamlit page renders, API checks, lint, compilation, database integrity and package verification."
        ),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
