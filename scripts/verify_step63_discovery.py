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
from biointel.engineering.isolated_tests import run_test_files_isolated
from biointel.engineering.repository_audit import scan_repository_secrets
from biointel.quality.model_audit import audit_model_directory
from biointel.ui.navigation import PAGE_BY_KEY

DISCOVERY_FILES = (
    "src/biointel/discovery/workflow.py",
    "src/biointel/discovery/registry.py",
    "src/biointel/discovery/target_intelligence.py",
    "src/biointel/discovery/preparation.py",
    "src/biointel/discovery/admet_plugins.py",
    "src/biointel/discovery/docking.py",
    "src/biointel/discovery/lead_optimization.py",
    "src/biointel/chemistry/standardization.py",
    "src/biointel/chemistry/chemical_space.py",
    "src/biointel/chemistry/admet.py",
    "src/biointel/integrations/chembl_dataset.py",
    "src/biointel/structural/pockets.py",
    "src/biointel/api/main.py",
    "src/biointel/api/schemas.py",
    "src/biointel/jobs/worker.py",
    "pages/6_DTI_Predictor.py",
    "pages/13_ChEMBL_Dataset_Builder.py",
    "pages/61_Structural_Bioinformatics.py",
    "pages/62_ADMET_Drug_Discovery.py",
    "pages/88_Discovery_Command_Center.py",
    "tests/test_step63_discovery_excellence.py",
)

FOCUSED_TESTS = (
    "tests/test_step63_discovery_excellence.py",
    "tests/test_step61_discovery_excellence.py",
    "tests/test_smiles_and_descriptors.py",
    "tests/test_step22_internet_common_names.py",
    "tests/test_step29_biotech_bioinformatics.py",
)

COVERAGE_MODULES = (
    "biointel.discovery.workflow",
    "biointel.discovery.registry",
    "biointel.discovery.target_intelligence",
    "biointel.discovery.preparation",
    "biointel.discovery.admet_plugins",
    "biointel.discovery.docking",
    "biointel.chemistry.chemical_space",
    "biointel.structural.pockets",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str], *, timeout: int = 600) -> dict[str, object]:
    started = time.perf_counter()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SRC)
    with tempfile.TemporaryFile(mode="w+") as stdout_file, tempfile.TemporaryFile(mode="w+") as stderr_file:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=stdout_file,
            stderr=stderr_file,
            start_new_session=True,
        )
        timed_out = False
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            returncode = process.wait()
        finally:
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
        "passed": returncode == 0 and not timed_out,
        "timed_out": timed_out,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "stdout_tail": stdout[-6000:],
        "stderr_tail": stderr[-6000:],
    }


def database_health() -> dict[str, object]:
    paths = sorted({*ROOT.rglob("*.sqlite3"), *ROOT.rglob("*.sqlite"), *ROOT.rglob("*.db")})
    rows: list[dict[str, object]] = []
    for path in paths:
        try:
            with sqlite3.connect(path) as connection:
                integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
                foreign_keys = len(connection.execute("PRAGMA foreign_key_check").fetchall())
                tables = [
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    ).fetchall()
                ]
                record_count = 0
                for table in tables:
                    escaped = str(table).replace('"', '""')
                    record_count += int(connection.execute(f'SELECT COUNT(*) FROM "{escaped}"').fetchone()[0])
            rows.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "integrity": integrity,
                    "foreign_key_violations": foreign_keys,
                    "table_count": len(tables),
                    "row_count": record_count,
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "integrity": "error",
                    "foreign_key_violations": -1,
                    "error": str(exc),
                }
            )
    return {
        "database_count": len(rows),
        "healthy_databases": sum(row.get("integrity") == "ok" for row in rows),
        "foreign_key_violations": sum(max(0, int(row.get("foreign_key_violations", 0))) for row in rows),
        "row_count": sum(int(row.get("row_count", 0)) for row in rows),
        "databases": rows,
    }


def parse_marker(payload: str, marker: str) -> dict[str, object]:
    for line in reversed(payload.splitlines()):
        if line.startswith(marker):
            return json.loads(line[len(marker) :])
    raise ValueError(f"Missing marker: {marker}")


def streamlit_checks() -> dict[str, object]:
    pages = [
        "pages/88_Discovery_Command_Center.py",
        "pages/13_ChEMBL_Dataset_Builder.py",
        "pages/61_Structural_Bioinformatics.py",
        "pages/62_ADMET_Drug_Discovery.py",
        "pages/6_DTI_Predictor.py",
    ]
    code = r'''
import json, os
from pathlib import Path
from streamlit.testing.v1 import AppTest
root = Path.cwd()
pages = [
    "pages/88_Discovery_Command_Center.py",
    "pages/13_ChEMBL_Dataset_Builder.py",
    "pages/61_Structural_Bioinformatics.py",
    "pages/62_ADMET_Drug_Discovery.py",
    "pages/6_DTI_Predictor.py",
]
results = []
for page in pages:
    app = AppTest.from_file(str(root / page), default_timeout=90).run(timeout=90)
    item = {"page": page, "passed": not app.exception, "exceptions": [x.message for x in app.exception]}
    if page.endswith("6_DTI_Predictor.py") and not app.exception:
        acknowledgements = [x for x in app.checkbox if "exploratory/demo-only" in x.label]
        buttons = [x for x in app.button if x.label == "Predict interaction"]
        item["exploratory_gate_present"] = bool(acknowledgements)
        item["prediction_disabled_without_acknowledgement"] = bool(buttons and buttons[0].disabled)
        item["passed"] = item["passed"] and item["exploratory_gate_present"] and item["prediction_disabled_without_acknowledgement"]
    results.append(item)
report = {"scenario_count": len(results), "passed_scenarios": sum(bool(x["passed"]) for x in results), "scenarios": results}
print("__STEP63_UI_JSON__" + json.dumps(report), flush=True)
os._exit(0)
'''
    subprocess_result = run([sys.executable, "-c", code], timeout=480)
    try:
        report = parse_marker(str(subprocess_result["stdout_tail"]), "__STEP63_UI_JSON__")
    except Exception as exc:
        report = {"scenario_count": len(pages), "passed_scenarios": 0, "scenarios": [], "error": str(exc)}
    report["subprocess"] = subprocess_result
    return report


def api_checks() -> dict[str, object]:
    code = r'''
import json, os, tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from biointel.api import main as api_main
with tempfile.TemporaryDirectory() as temp:
    api_main.DISCOVERY_DATABASE = Path(temp) / "discovery.sqlite3"
    client = TestClient(api_main.app)
    results = []
    created = client.post("/discovery/projects", json={"project_name": "Qualification", "indication": "test"})
    project_id = created.json().get("project", {}).get("project_id", "")
    results.append({"name": "project", "status_code": created.status_code, "passed": created.status_code == 200 and bool(project_id)})
    compound = client.post(f"/discovery/projects/{project_id}/compounds", json={"compound_id": "ethanol", "smiles": "CCO"})
    results.append({"name": "compound", "status_code": compound.status_code, "passed": compound.status_code == 200})
    ranking = client.post(f"/discovery/projects/{project_id}/rankings", json={"benefit_columns": {"developability_score": 0.7, "qed": 0.3}, "cost_columns": {}})
    results.append({"name": "ranking", "status_code": ranking.status_code, "passed": ranking.status_code == 200})
    bundle = client.get(f"/discovery/projects/{project_id}/bundle")
    results.append({"name": "bundle", "status_code": bundle.status_code, "passed": bundle.status_code == 200 and bundle.headers.get("content-type") == "application/zip"})
    standardize = client.post("/discovery/standardize-batch", json={"rows": [{"compound_id": "a", "smiles": "CC(=O)[O-].[Na+]"}, {"compound_id": "bad", "smiles": "not-smiles"}], "preparation_mode": "physiological_context", "ph": 7.4})
    results.append({"name": "standardize", "status_code": standardize.status_code, "passed": standardize.status_code == 200 and len(standardize.json().get("failures", [])) == 1})
    similarity = client.post("/discovery/similarity", json={"query_smiles": "CCO", "rows": [{"name": "ethanol", "smiles": "CCO"}, {"name": "benzene", "smiles": "c1ccccc1"}], "smiles_column": "smiles", "name_column": "name", "top_n": 2})
    results.append({"name": "similarity", "status_code": similarity.status_code, "passed": similarity.status_code == 200 and len(similarity.json().get("hits", [])) == 2})
    card = {
        "model_id": "herg-qualified", "endpoint": "hERG", "version": "1.0",
        "artifact_sha256": "a" * 64, "training_dataset_sha256": "b" * 64,
        "licence": "documented", "endpoint_definition": "locked binary endpoint", "units": "probability",
        "split_strategies": ["scaffold", "external"], "metrics": {"roc_auc": 0.8},
        "calibration": {"ece": 0.04}, "applicability_domain": {"method": "distance"},
        "independent_validation": {"dataset": "external"}, "intended_use": "screening", "limitations": ["not clinical"]
    }
    qualify = client.post("/discovery/admet-models/qualify", json=card)
    listed = client.get("/discovery/admet-models")
    results.append({"name": "endpoint model", "status_code": qualify.status_code, "passed": qualify.status_code == 200 and qualify.json().get("eligible") is True and listed.json().get("count") == 1})
    docking = client.post("/discovery/docking/qualify", json={"receptor_prepared": True, "ligand_prepared": True, "grid_defined": True, "reference_ligand_available": True, "redocking_rmsd_angstrom": 1.5, "enrichment_factor_1_percent": 5, "pose_review_completed": True, "protocol": {"engine": "qualified external engine"}})
    results.append({"name": "docking gate", "status_code": docking.status_code, "passed": docking.status_code == 200 and docking.json().get("qualified") is True})
    capabilities = client.get("/discovery/capabilities")
    results.append({"name": "capabilities", "status_code": capabilities.status_code, "passed": capabilities.status_code == 200 and capabilities.json().get("persistent_projects") is True})
report = {"case_count": len(results), "passed_cases": sum(bool(x["passed"]) for x in results), "cases": results}
print("__STEP63_API_JSON__" + json.dumps(report), flush=True)
os._exit(0)
'''
    subprocess_result = run([sys.executable, "-c", code], timeout=360)
    try:
        report = parse_marker(str(subprocess_result["stdout_tail"]), "__STEP63_API_JSON__")
    except Exception as exc:
        report = {"case_count": 9, "passed_cases": 0, "cases": [], "error": str(exc)}
    report["subprocess"] = subprocess_result
    return report


def benchmark() -> dict[str, object]:
    code = r'''
import json, os, time
import pandas as pd
from pathlib import Path
from biointel.chemistry.admet import profile_admet
from biointel.discovery.preparation import prepare_molecular_states
root = Path.cwd()
frame = pd.read_csv(root / "data/coverage/molecule_analysis_library_1000.csv").head(200)
failures = []
started = time.perf_counter()
for index, smiles in enumerate(frame["canonical_smiles"], start=1):
    try:
        state = prepare_molecular_states(str(smiles), mode="neutral_parent")
        profile_admet(state.standardized_parent_smiles)
    except Exception as exc:
        failures.append({"row": index, "error": str(exc)})
elapsed = time.perf_counter() - started
report = {"molecule_count": len(frame), "successes": len(frame) - len(failures), "failures": failures, "elapsed_seconds": round(elapsed, 3), "molecules_per_second": round(len(frame) / elapsed, 2) if elapsed else None}
print("__STEP63_BENCH_JSON__" + json.dumps(report), flush=True)
os._exit(0)
'''
    subprocess_result = run([sys.executable, "-c", code], timeout=360)
    try:
        report = parse_marker(str(subprocess_result["stdout_tail"]), "__STEP63_BENCH_JSON__")
    except Exception as exc:
        report = {"molecule_count": 200, "successes": 0, "failures": [{"error": str(exc)}]}
    report["subprocess"] = subprocess_result
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify BioIntel AI Step 63 Discovery Excellence.")
    parser.add_argument("--output", default="reports/step63_discovery_qualification.json")
    args = parser.parse_args()

    print("[Step63] Ruff", flush=True)
    ruff = run([sys.executable, "-m", "ruff", "check", "."], timeout=360)
    print("[Step63] Compilation", flush=True)
    compilation = run([sys.executable, "-m", "compileall", "-q", "app.py", "pages", "src", "scripts", "platform"], timeout=360)
    coverage_output = "reports/step63_discovery_core_coverage.json"
    core_pytest_args = ["-q", "tests/test_step63_discovery_excellence.py"]
    for module in COVERAGE_MODULES:
        core_pytest_args.append(f"--cov={module}")
    core_pytest_args.extend([f"--cov-report=json:{coverage_output}", "--cov-report=term", "--cov-fail-under=85"])
    core_wrapper = (
        "import os, pytest, sys; code=pytest.main(" + repr(core_pytest_args) + "); "
        "sys.stdout.flush(); sys.stderr.flush(); os._exit(int(code))"
    )
    print("[Step63] Core tests and coverage", flush=True)
    core_tests = run([sys.executable, "-c", core_wrapper], timeout=300)
    print("[Step63] Legacy regressions", flush=True)
    legacy_tests = run_test_files_isolated(
        ROOT,
        FOCUSED_TESTS[1:],
        timeout_seconds=240,
        max_workers=2,
    )
    coverage_path = ROOT / coverage_output
    coverage = json.loads(coverage_path.read_text(encoding="utf-8")) if coverage_path.is_file() else {}
    print("[Step63] Streamlit", flush=True)
    ui = streamlit_checks()
    print("[Step63] API", flush=True)
    api = api_checks()
    print("[Step63] Databases", flush=True)
    databases = database_health()
    print("[Step63] Benchmark", flush=True)
    performance = benchmark()
    print("[Step63] Model audit", flush=True)
    model_audit = audit_model_directory(ROOT / "models")
    print("[Step63] Secret scan", flush=True)
    secrets = scan_repository_secrets(ROOT)

    discovery_keys = {
        "discovery_command_center", "drug_analyzer", "chembl_builder", "dti_features",
        "dti_predictor", "structural_bioinformatics", "admet_discovery", "pathway_network",
    }
    navigation = {
        key: {"category": PAGE_BY_KEY[key].category, "path": PAGE_BY_KEY[key].path, "file_exists": (ROOT / PAGE_BY_KEY[key].path).is_file()}
        for key in sorted(discovery_keys)
    }
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    version_consistent = version == __version__
    files = {
        relative: {"exists": (ROOT / relative).is_file(), "sha256": sha256(ROOT / relative) if (ROOT / relative).is_file() else None}
        for relative in DISCOVERY_FILES
    }
    coverage_percent = float(coverage.get("totals", {}).get("percent_covered", 0))
    passed = (
        bool(ruff["passed"])
        and bool(compilation["passed"])
        and bool(core_tests["passed"])
        and int(legacy_tests["failed_files"]) == 0
        and coverage_percent >= 85
        and ui["passed_scenarios"] == ui["scenario_count"]
        and api["passed_cases"] == api["case_count"]
        and databases["healthy_databases"] == databases["database_count"]
        and databases["foreign_key_violations"] == 0
        and len(performance.get("failures", [])) == 0
        and all(item["category"] == "Discovery" and item["file_exists"] for item in navigation.values())
        and all(item["exists"] for item in files.values())
        and int(secrets.get("finding_count", 0)) == 0
        and version_consistent
    )
    report = {
        "schema": "biointel.step63.discovery-qualification.v1",
        "release": "BioIntel AI Step 63 Discovery Platform Excellence",
        "version": version,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "passed": passed,
        "version_consistent": version_consistent,
        "ruff": ruff,
        "python_compilation": compilation,
        "core_coverage_tests": core_tests,
        "legacy_regression_tests": legacy_tests,
        "coverage": coverage.get("totals", {}),
        "streamlit": ui,
        "api": api,
        "database_health": databases,
        "performance": performance,
        "model_evidence_boundary": {
            "model_count": model_audit.get("model_count", 0),
            "synthetic_models": model_audit.get("synthetic_models", 0),
            "release_eligible_models": model_audit.get("release_eligible_models", 0),
            "statement": "Synthetic or release-blocked models remain exploratory and cannot be promoted by this qualification.",
        },
        "secret_scan": secrets,
        "navigation": navigation,
        "files": files,
        "external_boundaries": [
            "Independent wet-lab potency, selectivity, ADME and toxicity results",
            "Qualified endpoint model artifacts and independent validation datasets",
            "Validated docking engine/protocol execution and expert pose review",
            "Patent freedom-to-operate legal opinion",
            "Regulatory approval and prospective clinical or laboratory validation",
        ],
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps({"passed": passed, "output": str(output), "coverage_percent": coverage_percent, "core_tests_passed": core_tests["passed"], "legacy_tests_passed": legacy_tests["failed_files"] == 0, "ui": f"{ui['passed_scenarios']}/{ui['scenario_count']}", "api": f"{api['passed_cases']}/{api['case_count']}", "databases": f"{databases['healthy_databases']}/{databases['database_count']}"}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
