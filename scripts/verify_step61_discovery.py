from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from biointel import __version__
from biointel.api.main import app
from biointel.chemistry.admet import profile_admet
from biointel.ui.navigation import PAGE_BY_KEY

DISCOVERY_FILES = (
    "src/biointel/chemistry/standardization.py",
    "src/biointel/chemistry/medicinal_chemistry.py",
    "src/biointel/chemistry/similarity_search.py",
    "src/biointel/chemistry/admet.py",
    "src/biointel/discovery/__init__.py",
    "src/biointel/discovery/workflow.py",
    "pages/3_Drug_SMILES_Analyzer.py",
    "pages/4_DTI_Feature_Builder.py",
    "pages/6_DTI_Predictor.py",
    "pages/13_ChEMBL_Dataset_Builder.py",
    "pages/61_Structural_Bioinformatics.py",
    "pages/62_ADMET_Drug_Discovery.py",
    "pages/63_Pathway_Network_Analysis.py",
    "pages/88_Discovery_Command_Center.py",
    "tests/test_step61_discovery_excellence.py",
)

FOCUSED_TESTS = (
    "tests/test_step61_discovery_excellence.py",
    "tests/test_smiles_and_descriptors.py",
    "tests/test_step29_biotech_bioinformatics.py",
    "tests/test_step22_internet_common_names.py",
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
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "passed": completed.returncode == 0,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def database_health() -> dict[str, object]:
    paths = sorted(
        {
            *ROOT.rglob("*.sqlite3"),
            *ROOT.rglob("*.db"),
        }
    )
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
                    escaped = table.replace('"', '""')
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


def streamlit_checks() -> dict[str, object]:
    pages = (
        "pages/3_Drug_SMILES_Analyzer.py",
        "pages/62_ADMET_Drug_Discovery.py",
        "pages/88_Discovery_Command_Center.py",
    )
    results: list[dict[str, object]] = []
    for page in pages:
        app_test = AppTest.from_file(str(ROOT / page), default_timeout=60).run()
        results.append(
            {
                "page": page,
                "passed": not app_test.exception,
                "exceptions": [item.message for item in app_test.exception],
            }
        )

    admet = AppTest.from_file(str(ROOT / pages[1]), default_timeout=60).run()
    admet.text_input[0].set_value("CC(=O)[O-].[Na+]")
    next(button for button in admet.button if button.label == "Standardize and profile molecule").click()
    admet.run()
    results.append(
        {
            "page": pages[1],
            "scenario": "salt standardization interaction",
            "passed": not admet.exception,
            "exceptions": [item.message for item in admet.exception],
        }
    )

    command = AppTest.from_file(str(ROOT / pages[2]), default_timeout=60).run()
    next(button for button in command.button if button.label == "Score target evidence").click()
    command.run()
    next(button for button in command.button if button.label == "Standardize, triage and add candidate").click()
    command.run()
    results.append(
        {
            "page": pages[2],
            "scenario": "target score and compound project interaction",
            "passed": not command.exception,
            "exceptions": [item.message for item in command.exception],
        }
    )
    return {
        "scenario_count": len(results),
        "passed_scenarios": sum(bool(item["passed"]) for item in results),
        "scenarios": results,
    }


def api_checks() -> dict[str, object]:
    client = TestClient(app)
    cases = [
        ("aspirin", "CC(=O)OC1=CC=CC=C1C(=O)O", 200),
        ("sodium acetate", "CC(=O)[O-].[Na+]", 200),
        ("invalid", "C1(CC", 422),
    ]
    results: list[dict[str, object]] = []
    for name, smiles, expected in cases:
        response = client.post("/bioinformatics/admet/profile", json={"smiles": smiles})
        payload = response.json()
        results.append(
            {
                "name": name,
                "status_code": response.status_code,
                "expected_status": expected,
                "passed": response.status_code == expected,
                "standardized_smiles": payload.get("standardized_smiles"),
                "developability_score": payload.get("developability_score"),
                "endpoint_count": len(payload.get("endpoint_summary", [])),
            }
        )
    return {
        "case_count": len(results),
        "passed_cases": sum(bool(item["passed"]) for item in results),
        "cases": results,
    }


def benchmark() -> dict[str, object]:
    import pandas as pd

    frame = pd.read_csv(ROOT / "data/coverage/molecule_analysis_library_1000.csv").head(100)
    started = time.perf_counter()
    failures = 0
    for smiles in frame["canonical_smiles"]:
        try:
            profile_admet(str(smiles))
        except Exception:
            failures += 1
    elapsed = time.perf_counter() - started
    return {
        "molecule_count": len(frame),
        "failures": failures,
        "elapsed_seconds": round(elapsed, 3),
        "molecules_per_second": round(len(frame) / elapsed, 2) if elapsed else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify BioIntel AI Step 61 Discovery Excellence.")
    parser.add_argument("--output", default="reports/step61_discovery_qualification.json")
    args = parser.parse_args()

    ruff = run([sys.executable, "-m", "ruff", "check", "."])
    compilation = run(
        [sys.executable, "-m", "compileall", "-q", "app.py", "pages", "src", "scripts", "platform"]
    )
    tests = run([sys.executable, "-m", "pytest", "-q", *FOCUSED_TESTS], timeout=600)
    ui = streamlit_checks()
    api = api_checks()
    databases = database_health()
    performance = benchmark()

    discovery_keys = {
        "discovery_command_center",
        "drug_analyzer",
        "chembl_builder",
        "dti_features",
        "dti_predictor",
        "structural_bioinformatics",
        "admet_discovery",
        "pathway_network",
    }
    navigation = {
        key: {
            "category": PAGE_BY_KEY[key].category,
            "path": PAGE_BY_KEY[key].path,
            "file_exists": (ROOT / PAGE_BY_KEY[key].path).is_file(),
        }
        for key in sorted(discovery_keys)
    }
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    version_consistent = version == __version__ == "6.1.0"
    files = {
        relative: {
            "exists": (ROOT / relative).is_file(),
            "sha256": sha256(ROOT / relative) if (ROOT / relative).is_file() else None,
        }
        for relative in DISCOVERY_FILES
    }

    passed = (
        bool(ruff["passed"])
        and bool(compilation["passed"])
        and bool(tests["passed"])
        and ui["passed_scenarios"] == ui["scenario_count"]
        and api["passed_cases"] == api["case_count"]
        and databases["healthy_databases"] == databases["database_count"]
        and databases["foreign_key_violations"] == 0
        and performance["failures"] == 0
        and all(item["category"] == "Discovery" and item["file_exists"] for item in navigation.values())
        and all(item["exists"] for item in files.values())
        and version_consistent
    )
    report = {
        "schema": "biointel.step61.discovery-qualification.v1",
        "release": "BioIntel AI Step 61 Discovery Excellence",
        "version": version,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "passed": passed,
        "version_consistent": version_consistent,
        "ruff": ruff,
        "python_compilation": compilation,
        "focused_tests": tests,
        "streamlit": ui,
        "api": api,
        "databases": databases,
        "performance": performance,
        "navigation": navigation,
        "discovery_files": files,
        "scientific_boundary": {
            "validated_admet_endpoint_models_installed": False,
            "fake_endpoint_probabilities_generated": False,
            "external_requirements": [
                "Qualified endpoint-specific ADMET models",
                "Validated docking protocol and pose review",
                "Independent activity/selectivity assays",
                "Prospective wet-lab validation",
                "Patent and freedom-to-operate review",
            ],
        },
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
