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
from biointel.chemistry.medicinal_chemistry import medicinal_chemistry_cache_info
from biointel.chemistry.standardization import standardization_cache_info
from biointel.engineering.isolated_tests import run_test_files_isolated
from biointel.engineering.quality_gates import run_engineering_gates
from biointel.engineering.repository_audit import scan_repository_secrets
from biointel.engineering.runtime_optimizer import optimize_database_fleet
from biointel.ui.navigation import PAGE_BY_KEY
from biointel.utils.runtime_cache import runtime_cache_info


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str], *, timeout: int = 600) -> dict[str, object]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SRC)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.setdefault("OMP_NUM_THREADS", "1")
    environment.setdefault("OPENBLAS_NUM_THREADS", "1")
    environment.setdefault("MKL_NUM_THREADS", "1")
    environment.setdefault("NUMEXPR_NUM_THREADS", "1")
    started = time.perf_counter()
    with tempfile.TemporaryFile(mode="w+") as stdout_file, tempfile.TemporaryFile(
        mode="w+"
    ) as stderr_file:
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
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read()
        stderr = stderr_file.read()
    return {
        "command": command,
        "returncode": int(returncode),
        "passed": returncode == 0 and not timed_out,
        "timed_out": timed_out,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "stdout_tail": stdout[-8000:],
        "stderr_tail": stderr[-8000:],
    }


def parse_marker(payload: str, marker: str) -> dict[str, object]:
    for line in reversed(payload.splitlines()):
        if line.startswith(marker):
            return json.loads(line[len(marker) :])
    raise ValueError(f"Missing marker: {marker}")


def database_health() -> dict[str, object]:
    paths = sorted({*ROOT.rglob("*.sqlite3"), *ROOT.rglob("*.sqlite"), *ROOT.rglob("*.db")})
    rows: list[dict[str, object]] = []
    for path in paths:
        try:
            with sqlite3.connect(path) as connection:
                integrity = str(connection.execute("PRAGMA quick_check").fetchone()[0])
                foreign_keys = len(connection.execute("PRAGMA foreign_key_check").fetchall())
                tables = [
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    ).fetchall()
                ]
                count = 0
                for table in tables:
                    escaped = table.replace('"', '""')
                    count += int(connection.execute(f'SELECT COUNT(*) FROM "{escaped}"').fetchone()[0])
            rows.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "integrity": integrity,
                    "foreign_key_violations": foreign_keys,
                    "table_count": len(tables),
                    "row_count": count,
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
        "healthy_databases": sum(item.get("integrity") == "ok" for item in rows),
        "foreign_key_violations": sum(
            max(0, int(item.get("foreign_key_violations", 0))) for item in rows
        ),
        "row_count": sum(int(item.get("row_count", 0)) for item in rows),
        "databases": rows,
    }


def streamlit_checks() -> dict[str, object]:
    pages = [
        "app.py",
        "pages/6_DTI_Predictor.py",
        "pages/62_ADMET_Drug_Discovery.py",
        "pages/64_Wet_Lab_Biotechnology.py",
        "pages/82_Metagenomics_Pipeline.py",
        "pages/88_Discovery_Command_Center.py",
        "pages/89_Lab_Analytics_Command_Center.py",
    ]
    code = f'''
import json, os
from pathlib import Path
from streamlit.testing.v1 import AppTest
root=Path.cwd()
pages={pages!r}
results=[]
for page in pages:
    app=AppTest.from_file(str(root/page), default_timeout=120).run(timeout=120)
    results.append({{"page":page,"passed":not app.exception,"exceptions":[item.message for item in app.exception]}})
report={{"scenario_count":len(results),"passed_scenarios":sum(bool(x["passed"]) for x in results),"scenarios":results}}
print("__STEP64_UI__"+json.dumps(report), flush=True)
os._exit(0)
'''
    result = run([sys.executable, "-c", code], timeout=900)
    try:
        report = parse_marker(str(result["stdout_tail"]), "__STEP64_UI__")
    except Exception as exc:
        report = {"scenario_count": len(pages), "passed_scenarios": 0, "error": str(exc)}
    report["subprocess"] = result
    return report


def api_checks() -> dict[str, object]:
    code = r'''
import json, os, tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from biointel.api import main as api_main
with tempfile.TemporaryDirectory() as temp:
    api_main.DISCOVERY_DATABASE=Path(temp)/"discovery.sqlite3"
    client=TestClient(api_main.app)
    cases=[]
    def add(name,response,condition=True):
        cases.append({"name":name,"status_code":response.status_code,"passed":response.status_code==200 and bool(condition)})
    health=client.get("/health"); add("health",health,health.json().get("status") in {"ok","healthy"})
    ui=client.get("/ui/catalog"); add("ui catalog",ui,bool(ui.json()))
    project=client.post("/discovery/projects",json={"project_name":"Step64 qualification","indication":"verification"})
    project_id=project.json().get("project",{}).get("project_id",""); add("discovery project",project,bool(project_id))
    compound=client.post(f"/discovery/projects/{project_id}/compounds",json={"compound_id":"ethanol","smiles":"CCO"}); add("compound",compound)
    rank=client.post(f"/discovery/projects/{project_id}/rankings",json={"benefit_columns":{"developability_score":1.0},"cost_columns":{}}); add("ranking",rank)
    admet=client.post("/bioinformatics/admet/profile",json={"smiles":"CCO"}); add("admet",admet,admet.json().get("developability_score") is not None)
    enzyme=client.post("/biotechnology/enzyme/fit",json={"rows":[{"substrate":x,"velocity":10*x/(0.4+x)} for x in [0.05,0.1,0.25,0.5,1,2,5]],"model":"auto"}); add("enzyme",enzyme)
    process=client.post("/biotechnology/bioprocess/analyze",json={"rows":[{"batch":"A","time":t,"biomass":0.2+t*0.2,"substrate":10-t,"product":t*0.3} for t in [0,1,2,3]],"process_mode":"Batch","batch_column":"batch"}); add("bioprocess",process)
    sequence=client.post("/sequence/analyze",json={"sequence":"ATGGCCATTGTAATGGGCCGCTGAAAGGGTGCCCGATAG","sequence_type":"DNA"}); add("sequence",sequence)
report={"case_count":len(cases),"passed_cases":sum(bool(x["passed"]) for x in cases),"cases":cases}
print("__STEP64_API__"+json.dumps(report), flush=True)
os._exit(0)
'''
    result = run([sys.executable, "-c", code], timeout=480)
    try:
        report = parse_marker(str(result["stdout_tail"]), "__STEP64_API__")
    except Exception as exc:
        report = {"case_count": 9, "passed_cases": 0, "error": str(exc)}
    report["subprocess"] = result
    return report


def performance_checks() -> dict[str, object]:
    code = r'''
import json, os, time
import pandas as pd
from biointel.chemistry.standardization import clear_standardization_cache, standardize_molecule, standardization_cache_info
from biointel.chemistry.medicinal_chemistry import clear_medicinal_chemistry_cache, medicinal_chemistry_cache_info, profile_medicinal_chemistry
from biointel.chemistry.chemical_space import similarity_matrix
smiles=["CCO","CCCO","CC(=O)O","c1ccccc1","CCN"]*100
clear_standardization_cache(); clear_medicinal_chemistry_cache()
started=time.perf_counter()
for value in smiles:
    mol,_=standardize_molecule(value)
    profile_medicinal_chemistry(mol)
first=time.perf_counter()-started
started=time.perf_counter()
for value in smiles:
    mol,_=standardize_molecule(value)
    profile_medicinal_chemistry(mol)
second=time.perf_counter()-started
frame=pd.DataFrame({"compound_id":[f"c{i}" for i in range(100)],"standardized_smiles":[smiles[i%len(smiles)] for i in range(100)]})
started=time.perf_counter(); matrix=similarity_matrix(frame); matrix_seconds=time.perf_counter()-started
report={"profiles":len(smiles),"first_pass_seconds":round(first,4),"cached_pass_seconds":round(second,4),"speedup":round(first/max(second,1e-9),2),"standardization_cache":standardization_cache_info(),"medicinal_cache":medicinal_chemistry_cache_info(),"similarity_matrix_shape":list(matrix.shape),"similarity_matrix_seconds":round(matrix_seconds,4)}
print("__STEP64_PERF__"+json.dumps(report), flush=True)
os._exit(0)
'''
    result = run([sys.executable, "-c", code], timeout=360)
    try:
        report = parse_marker(str(result["stdout_tail"]), "__STEP64_PERF__")
    except Exception as exc:
        report = {"error": str(exc)}
    report["subprocess"] = result
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify BioIntel AI Step 64 final optimization.")
    parser.add_argument("--output", default="reports/step64_final_qualification.json")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    print("[Step64] Ruff", flush=True)
    ruff = run([sys.executable, "-m", "ruff", "check", "."], timeout=420)
    print("[Step64] Compilation", flush=True)
    compilation = run(
        [sys.executable, "-m", "compileall", "-q", "app.py", "pages", "src", "scripts", "platform"],
        timeout=420,
    )
    print("[Step64] Engineering gates", flush=True)
    engineering = run_engineering_gates(ROOT)
    print("[Step64] Full isolated test-file suite", flush=True)
    test_files = [path.relative_to(ROOT).as_posix() for path in sorted((ROOT / "tests").glob("test_*.py"))]
    tests = run_test_files_isolated(
        ROOT,
        test_files,
        timeout_seconds=300,
        max_workers=args.workers,
    )
    print("[Step64] Streamlit", flush=True)
    ui = streamlit_checks()
    print("[Step64] API", flush=True)
    api = api_checks()
    print("[Step64] Database optimization", flush=True)
    database_optimization = optimize_database_fleet(ROOT)
    print("[Step64] Database health", flush=True)
    databases = database_health()
    print("[Step64] Performance", flush=True)
    performance = performance_checks()
    print("[Step64] Secret scan", flush=True)
    secrets = scan_repository_secrets(ROOT)

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    version_consistent = version == __version__ == "6.5.0"
    navigation_missing = [
        key for key, page in PAGE_BY_KEY.items() if not (ROOT / page.path).is_file()
    ]
    residue = sorted(
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file()
        and (
            path.suffix in {".pyc", ".pyo"}
            or path.name.endswith(("-wal", "-shm"))
        )
    )
    passed = (
        bool(ruff["passed"])
        and bool(compilation["passed"])
        and bool(engineering["passed"])
        and int(tests["failed_files"]) == 0
        and ui.get("passed_scenarios") == ui.get("scenario_count")
        and api.get("passed_cases") == api.get("case_count")
        and int(database_optimization["failed_databases"]) == 0
        and databases["healthy_databases"] == databases["database_count"]
        and databases["foreign_key_violations"] == 0
        and int(secrets.get("finding_count", 0)) == 0
        and version_consistent
        and not navigation_missing
    )
    report = {
        "schema": "biointel.step64.final-optimization.v1",
        "release": "BioIntel AI Step 64 Final Stabilization and Optimization",
        "version": version,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "passed": passed,
        "version_consistent": version_consistent,
        "ruff": ruff,
        "python_compilation": compilation,
        "engineering_gates": engineering,
        "isolated_test_files": tests,
        "streamlit": ui,
        "api": api,
        "database_optimization": database_optimization,
        "database_health": databases,
        "performance": performance,
        "secret_scan": secrets,
        "navigation_missing": navigation_missing,
        "runtime_residue_before_packaging": residue,
        "runtime_caches": {
            "files": runtime_cache_info(),
            "standardization": standardization_cache_info(),
            "medicinal_chemistry": medicinal_chemistry_cache_info(),
        },
        "key_files": {
            relative: sha256(ROOT / relative)
            for relative in [
                "src/biointel/chemistry/standardization.py",
                "src/biointel/chemistry/chemical_space.py",
                "src/biointel/chemistry/medicinal_chemistry.py",
                "src/biointel/discovery/registry.py",
                "src/biointel/biotech/assays_advanced.py",
                "src/biointel/biotech/assays_quality.py",
                "src/biointel/engineering/isolated_tests.py",
                "src/biointel/engineering/runtime_optimizer.py",
                "scripts/verify_step64_final.py",
                "tests/test_step64_final_optimization.py",
            ]
        },
        "external_boundaries": [
            "Independent wet-lab and prospective validation evidence",
            "Qualified third-party ADMET or docking model artifacts",
            "Regulatory approval, inspection history and accredited-lab certification",
            "Patent freedom-to-operate legal opinion",
        ],
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": passed,
                "output": str(output),
                "test_files": f"{tests['passed_files']}/{tests['file_count']}",
                "ui": f"{ui.get('passed_scenarios', 0)}/{ui.get('scenario_count', 0)}",
                "api": f"{api.get('passed_cases', 0)}/{api.get('case_count', 0)}",
                "databases": f"{databases['healthy_databases']}/{databases['database_count']}",
            },
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
