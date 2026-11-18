from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel import __version__
from biointel.ui.navigation import PAGE_BY_KEY

LAB_FILES = (
    "src/biointel/biotech/assays.py",
    "src/biointel/biotech/assays_advanced.py",
    "src/biointel/biotech/experimental_design.py",
    "src/biointel/biotech/lab_schema.py",
    "src/biointel/biotech/lab_import.py",
    "src/biointel/biotech/lab_reporting.py",
    "src/biointel/biotech/lab_registry.py",
    "src/biointel/projects/metagenomics_raw_reads.py",
    "src/biointel/api/main.py",
    "src/biointel/api/schemas.py",
    "src/biointel/ui/navigation.py",
    "pages/64_Wet_Lab_Biotechnology.py",
    "pages/82_Metagenomics_Pipeline.py",
    "pages/89_Lab_Analytics_Command_Center.py",
    "tests/test_step62_lab_analytics_excellence.py",
    "tests/test_step62_lab_analytics_coverage.py",
)

FOCUSED_TESTS = (
    "tests/test_step60_lab_analytics_excellence.py",
    "tests/test_step62_lab_analytics_excellence.py",
    "tests/test_step62_lab_analytics_coverage.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str], *, timeout: int = 600) -> dict[str, object]:
    started = time.perf_counter()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    # File-backed capture avoids inherited PIPE handles from test/UI worker
    # processes keeping the verifier alive after the direct child exits.
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stdout_file, tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stderr_file:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=stdout_file,
            stderr=stderr_file,
            start_new_session=True,
        )
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise
        finally:
            # Third-party UI/scientific libraries can leave helper workers in
            # the child's process group. Terminate only that isolated group.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read()
        stderr = stderr_file.read()
    return {
        "command": command,
        "returncode": returncode,
        "passed": returncode == 0,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-4000:],
    }


def database_health() -> dict[str, object]:
    paths = sorted({*ROOT.rglob("*.sqlite3"), *ROOT.rglob("*.db")})
    rows: list[dict[str, object]] = []
    for path in paths:
        try:
            with sqlite3.connect(path) as connection:
                integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
                foreign_keys = len(connection.execute("PRAGMA foreign_key_check").fetchall())
                tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
                record_count = 0
                for table in tables:
                    escaped = table.replace('"', '""')
                    record_count += int(connection.execute(f'SELECT COUNT(*) FROM "{escaped}"').fetchone()[0])
            rows.append({"path": path.relative_to(ROOT).as_posix(), "integrity": integrity, "foreign_key_violations": foreign_keys, "table_count": len(tables), "row_count": record_count})
        except Exception as exc:
            rows.append({"path": path.relative_to(ROOT).as_posix(), "integrity": "error", "foreign_key_violations": -1, "error": str(exc)})
    return {
        "database_count": len(rows),
        "healthy_databases": sum(row.get("integrity") == "ok" for row in rows),
        "foreign_key_violations": sum(max(0, int(row.get("foreign_key_violations", 0))) for row in rows),
        "row_count": sum(int(row.get("row_count", 0)) for row in rows),
        "databases": rows,
    }


def _parse_json_marker(payload: str, marker: str) -> dict[str, object]:
    for line in reversed(payload.splitlines()):
        if line.startswith(marker):
            return json.loads(line[len(marker):])
    raise ValueError(f"Missing {marker!r} marker in subprocess output")


def streamlit_checks() -> dict[str, object]:
    pages = (
        "pages/64_Wet_Lab_Biotechnology.py",
        "pages/82_Metagenomics_Pipeline.py",
        "pages/89_Lab_Analytics_Command_Center.py",
    )
    code = r"""
import json
from pathlib import Path
from streamlit.testing.v1 import AppTest
root = Path.cwd()
pages = [
    "pages/64_Wet_Lab_Biotechnology.py",
    "pages/82_Metagenomics_Pipeline.py",
    "pages/89_Lab_Analytics_Command_Center.py",
]
results = []
for page in pages:
    application = AppTest.from_file(str(root / page), default_timeout=90).run()
    results.append({
        "page": page,
        "passed": not application.exception,
        "exceptions": [item.message for item in application.exception],
    })
report = {
    "scenario_count": len(results),
    "passed_scenarios": sum(bool(item["passed"]) for item in results),
    "scenarios": results,
}
print("__STEP62_UI_JSON__" + json.dumps(report), flush=True)
import os
os._exit(0)
"""
    result = run([sys.executable, "-c", code], timeout=360)
    try:
        parsed = _parse_json_marker(str(result["stdout_tail"]), "__STEP62_UI_JSON__")
    except Exception as exc:
        parsed = {
            "scenario_count": len(pages),
            "passed_scenarios": 0,
            "scenarios": [],
            "error": str(exc),
        }
    parsed["subprocess"] = result
    return parsed


def api_checks() -> dict[str, object]:
    code = r"""
import json
from fastapi.testclient import TestClient
from biointel.api.main import app
client = TestClient(app)
concentrations = [1, 2, 4, 8, 16, 32]
elisa_rows = []
for concentration in concentrations:
    response = 0.1 + 2.0 * concentration / (8 + concentration)
    elisa_rows.extend([
        {"type": "standard", "concentration": concentration, "absorbance": response},
        {"type": "standard", "concentration": concentration, "absorbance": response * 1.001},
    ])
elisa_rows.append({"type": "unknown", "concentration": 0, "absorbance": 1.1})
cases = [
    ("ELISA", "/biotechnology/elisa/quantify", {"rows": elisa_rows, "candidate_models": ["4PL", "log-linear"]}),
    ("Enzyme", "/biotechnology/enzyme/fit", {"rows": [{"substrate": value, "velocity": 10 * value / (0.4 + value)} for value in [0.05, 0.1, 0.25, 0.5, 1, 2, 5]], "model": "auto"}),
    ("Bioprocess", "/biotechnology/bioprocess/analyze", {"rows": [{"batch": "A", "time": t, "biomass": 0.2 + t * 0.2, "substrate": 10 - t, "product": t * 0.3} for t in [0, 1, 2, 3]], "process_mode": "Batch", "batch_column": "batch"}),
    ("Experimental design", "/biotechnology/design/sample-size", {"design_type": "noninferiority", "margin": 0.5, "assumed_standard_deviation": 2.0}),
    ("Plate QC", "/biotechnology/plate/qc", {"rows": [{"well": "A1", "signal": 1.0}, {"well": "A2", "signal": 1.1}, {"well": "H12", "signal": 2.0}], "value_column": "signal", "plate_format": 96}),
]
results = []
for name, endpoint, payload in cases:
    response = client.post(endpoint, json=payload)
    results.append({
        "name": name,
        "endpoint": endpoint,
        "status_code": response.status_code,
        "passed": response.status_code == 200,
        "response_preview": response.text[:500],
    })
report = {
    "case_count": len(results),
    "passed_cases": sum(bool(item["passed"]) for item in results),
    "cases": results,
}
print("__STEP62_API_JSON__" + json.dumps(report), flush=True)
import os
os._exit(0)
"""
    result = run([sys.executable, "-c", code], timeout=240)
    try:
        parsed = _parse_json_marker(str(result["stdout_tail"]), "__STEP62_API_JSON__")
    except Exception as exc:
        parsed = {
            "case_count": 5,
            "passed_cases": 0,
            "cases": [],
            "error": str(exc),
        }
    parsed["subprocess"] = result
    return parsed

def main() -> int:
    parser = argparse.ArgumentParser(description="Verify BioIntel AI Step 62 Lab Analytics Excellence.")
    parser.add_argument("--output", default="reports/step62_lab_analytics_qualification.json")
    args = parser.parse_args()

    ruff = run([sys.executable, "-m", "ruff", "check", *LAB_FILES])
    compilation = run([sys.executable, "-m", "compileall", "-q", "app.py", "pages", "src", "scripts", "platform"])
    pytest_args = [
        "-q",
        *FOCUSED_TESTS,
        "--cov=biointel.biotech.assays",
        "--cov=biointel.biotech.assays_advanced",
        "--cov=biointel.biotech.experimental_design",
        "--cov=biointel.biotech.lab_schema",
        "--cov=biointel.biotech.lab_import",
        "--cov=biointel.biotech.lab_reporting",
        "--cov=biointel.biotech.lab_registry",
        "--cov-report=json:reports/step62_lab_coverage.json",
        "--cov-report=term",
        "--cov-fail-under=85",
    ]
    pytest_wrapper = (
        "import os, pytest, sys; "
        "code = pytest.main(" + repr(pytest_args) + "); "
        "sys.stdout.flush(); sys.stderr.flush(); os._exit(int(code))"
    )
    tests = run([sys.executable, "-c", pytest_wrapper], timeout=600)
    coverage_path = ROOT / "reports" / "step62_lab_coverage.json"
    coverage = json.loads(coverage_path.read_text(encoding="utf-8")) if coverage_path.is_file() else {}
    ui = streamlit_checks()
    api = api_checks()
    databases = database_health()

    lab_keys = {"primer_crispr_codon", "wetlab_biotechnology", "microbiology_metagenomics", "metagenomics_pipeline", "lab_analytics_command_center"}
    navigation = {key: {"category": PAGE_BY_KEY[key].category, "path": PAGE_BY_KEY[key].path, "file_exists": (ROOT / PAGE_BY_KEY[key].path).is_file()} for key in sorted(lab_keys)}
    templates = sorted((ROOT / "data" / "lab_templates").glob("*"))
    template_state = {path.name: {"exists": path.is_file(), "sha256": sha256(path) if path.is_file() else None} for path in templates}
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    version_consistent = version == __version__ == "6.2.0"
    files = {relative: {"exists": (ROOT / relative).is_file(), "sha256": sha256(ROOT / relative) if (ROOT / relative).is_file() else None} for relative in LAB_FILES}

    passed = (
        bool(ruff["passed"])
        and bool(compilation["passed"])
        and bool(tests["passed"])
        and float(coverage.get("totals", {}).get("percent_covered", 0)) >= 85
        and ui["passed_scenarios"] == ui["scenario_count"]
        and api["passed_cases"] == api["case_count"]
        and databases["healthy_databases"] == databases["database_count"]
        and databases["foreign_key_violations"] == 0
        and all(item["category"] == "Lab Analytics" and item["file_exists"] for item in navigation.values())
        and all(item["exists"] for item in files.values())
        and version_consistent
    )
    report = {
        "schema": "biointel.step62.lab-analytics-qualification.v1",
        "release": "BioIntel AI Step 62 Lab Analytics Excellence",
        "version": version,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "passed": passed,
        "version_consistent": version_consistent,
        "ruff": ruff,
        "python_compilation": compilation,
        "focused_tests": tests,
        "coverage": coverage,
        "streamlit": ui,
        "api": api,
        "databases": databases,
        "navigation": navigation,
        "template_pack": template_state,
        "lab_files": files,
        "scientific_boundary": {
            "research_workbench": True,
            "regulated_laboratory_certification_claimed": False,
            "external_requirements": [
                "Laboratory-specific method validation and acceptance criteria",
                "Instrument qualification and vendor software review",
                "GLP/GMP quality-system validation, electronic signatures and SOP governance",
                "Independent experimental confirmation and accredited laboratory evidence",
                "Validated live historian/LIMS/ELN integrations for production use",
            ],
        },
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "passed": passed,
        "version": version,
        "focused_tests": tests["passed"],
        "coverage_percent": coverage.get("totals", {}).get("percent_covered", 0),
        "streamlit": f"{ui['passed_scenarios']}/{ui['scenario_count']}",
        "api": f"{api['passed_cases']}/{api['case_count']}",
        "databases": f"{databases['healthy_databases']}/{databases['database_count']}",
        "foreign_key_violations": databases["foreign_key_violations"],
        "output": output.relative_to(ROOT).as_posix(),
    }, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    exit_code = main()
    # Some third-party scientific/UI libraries start non-daemon helper threads.
    # Qualification artifacts are fully flushed before forcing deterministic exit.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
