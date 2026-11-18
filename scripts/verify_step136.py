from __future__ import annotations

import ast
import contextlib
import hashlib
import json
import os
import sqlite3
import struct
import sys
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.engineering.quality_gates import run_engineering_gates
from biointel.native.formats import NATIVE_FORMATS
from biointel.nextgen.biomedical_expansion import NEW_BIOMEDICAL_KEYS, analyse, demo_frame
from biointel.nextgen.catalog import MODULE_BY_KEY
from biointel.nextgen.module_scientific_v135 import build_module_scientific_artifacts
from biointel.nextgen.native_execution_v136 import (
    PROFILES,
    execute_native_pipeline_job,
    stage_for_background,
    validate_profiles,
)

LOCKED = {
    "pages/6_DTI_Predictor.py": "84b3ecec1356b7239a057459210af4cd130c57c08dd9449b7239d1fe5954e0cc",
    "pages/74_DTI_Validation_Evidence_Center.py": "a700a8a21649b49cf0e3a1521d2afad45039b83b767c2fe730b93fee7d4f7f11",
    "pages/109_Lab_Instrument_Import_Center.py": "22b5aba5bfea37bb1ef330ed7cca3773467463f883189602d96a0151311c8f70",
    "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "eadaef1a283a5fa11ce6b243aa561508ba9ceba9f6fdcc207f4853ccf7d86905",
    "pages/157_Instrument_Integration_Hub_2.py": "cf3a5f94756def0007dbff31184ec276d90b03fc6d6e1ca792c87189e5ab7d6d",
}

NEW_FORMAT_KEYS = {
    "wsi",
    "bedmethyl",
    "genbank",
    "sdf",
    "model_asset",
    "safety_xml",
    "parquet",
    "jsonl",
    "yaml",
    "hdf5",
    "bcf",
    "graph_binary",
}


def add(checks: list[dict[str, object]], name: str, passed: bool, detail: object) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def syntax_health() -> dict[str, Any]:
    failures: list[str] = []
    count = 0
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in {".venv", "venv", "site-packages"} for part in path.parts):
            continue
        count += 1
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            failures.append(f"{path.relative_to(ROOT)}: {type(exc).__name__}: {exc}")
    return {"passed": not failures, "files": count, "failures": failures}


def database_health() -> dict[str, Any]:
    paths = sorted(
        {
            path
            for pattern in ("*.db", "*.sqlite", "*.sqlite3")
            for path in ROOT.rglob(pattern)
            if ".venv" not in path.parts and "UserData" not in path.parts
        }
    )
    failures: list[str] = []
    rows = 0
    foreign_keys = 0
    hashes: dict[str, str] = {}
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        hashes[relative] = sha256(path)
        try:
            connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro&immutable=1", uri=True)
            try:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    failures.append(f"{relative}: {integrity}")
                foreign_keys += len(connection.execute("PRAGMA foreign_key_check").fetchall())
                tables = [
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    )
                ]
                for table in tables:
                    with contextlib.suppress(sqlite3.DatabaseError):
                        rows += int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            finally:
                connection.close()
        except Exception as exc:
            failures.append(f"{relative}: {type(exc).__name__}: {exc}")
    return {
        "passed": not failures and foreign_keys == 0,
        "databases": len(paths),
        "rows": rows,
        "foreign_key_issues": foreign_keys,
        "hashes": hashes,
        "failures": failures,
    }


def baseline_database_hashes() -> dict[str, str]:
    manifest_path = ROOT / "reports" / "step135_package_manifest.json"
    if not manifest_path.is_file():
        return {}
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    hashes: dict[str, str] = {}
    for item in payload.get("files", []):
        path = str(item.get("path", ""))
        if Path(path).suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
            hashes[path] = str(item.get("sha256", ""))
    return hashes


def module_science_smoke() -> dict[str, Any]:
    failures: list[str] = []
    tables = 0
    figures = 0
    modules: list[dict[str, Any]] = []
    for key in sorted(NEW_BIOMEDICAL_KEYS):
        try:
            module = MODULE_BY_KEY[key]
            data = demo_frame(module, 160)
            result, _summary, secondary, extras = analyse(data, module, 0.7)
            artifacts = build_module_scientific_artifacts(key, data, result, secondary, extras)
            summary = artifacts["summary"]
            if summary.get("safe_error"):
                failures.append(f"{key}: {summary['safe_error']}")
            table_count = len(artifacts["tables"])
            figure_count = len(artifacts["figures"])
            if table_count < 2 or figure_count < 3:
                failures.append(f"{key}: expected >=2 tables and >=3 figures, got {table_count}/{figure_count}")
            for name, figure in artifacts["figures"].items():
                payload = figure.to_json()
                if not payload or '"data"' not in payload:
                    failures.append(f"{key}/{name}: invalid figure serialisation")
            tables += table_count
            figures += figure_count
            modules.append({"module": key, "tables": table_count, "figures": figure_count})
        except Exception as exc:
            failures.append(f"{key}: {type(exc).__name__}: {exc}")
    return {
        "passed": not failures and len(modules) == 15 and tables >= 39 and figures >= 49,
        "module_count": len(modules),
        "scientific_tables": tables,
        "specialist_figures": figures,
        "modules": modules,
        "failures": failures,
    }


def _write_csv(path: Path, kind: str) -> None:
    frames = {
        "spatial": pd.DataFrame(
            {
                "patient_id": ["P1", "P1"],
                "region": ["core", "margin"],
                "cell_type": ["tumour", "immune"],
                "x": [1, 2],
                "y": [1, 2],
                "expression": [2.0, 3.0],
            }
        ),
        "federated": pd.DataFrame(
            {
                "site": ["A", "B"],
                "round": [1, 1],
                "samples": [100, 120],
                "metric": [0.80, 0.79],
                "privacy_epsilon": [2.0, 2.0],
            }
        ),
        "clinical": pd.DataFrame(
            {
                "patient_id": ["P1", "P2", "P3", "P4"],
                "biomarker": [1.2, 3.1, 2.5, 4.2],
                "time": [5, 7, 6, 8],
                "event": [1, 0, 1, 0],
                "site": ["A", "A", "B", "B"],
            }
        ),
        "pharmacovigilance": pd.DataFrame(
            {
                "report_id": ["R1", "R2"],
                "drug": ["D1", "D1"],
                "event": ["E1", "E2"],
                "serious": [True, False],
                "outcome": ["recovered", "unknown"],
            }
        ),
        "trial": pd.DataFrame(
            {
                "patient_id": ["P1", "P2", "P3", "P4"],
                "arm": ["A", "B", "A", "B"],
                "site": ["S1", "S1", "S2", "S2"],
                "outcome": [1, 0, 1, 1],
                "time": [1, 2, 3, 4],
                "event": [1, 0, 1, 1],
            }
        ),
        "lab": pd.DataFrame(
            {
                "experiment_id": ["E1", "E2"],
                "factor": ["dose", "time"],
                "level": ["low", "high"],
                "control": [True, False],
                "replicates": [3, 3],
                "cost": [20, 30],
            }
        ),
    }
    frames[kind].to_csv(path, index=False)


def _native_fixtures(directory: Path) -> dict[str, Path]:
    from PIL import Image

    files: dict[str, Path] = {}
    slide = directory / "slide.png"
    Image.new("RGB", (4, 4), (150, 40, 70)).save(slide)
    files["digital_pathology_foundation"] = slide

    methylation = directory / "methylation.bedmethyl"
    methylation.write_text("chr1\t10\t11\tm1\t0\t+\t10\t11\t0\t30\t80\n", encoding="utf-8")
    files["long_read_epigenome"] = methylation

    annotation = directory / "isoforms.gtf"
    annotation.write_text(
        'chr1\tsrc\ttranscript\t1\t100\t.\t+\t.\tgene_id "G1"; transcript_id "T1";\n',
        encoding="utf-8",
    )
    files["single_cell_long_read_isoforms"] = annotation

    checkpoint = directory / "model.safetensors"
    header = b"{}"
    checkpoint.write_bytes(struct.pack("<Q", len(header)) + header)
    files["biomedical_foundation_model_hub"] = checkpoint

    isolate = directory / "isolate.fasta"
    isolate.write_text(">isolate1\nACGTACGTACGT\n", encoding="utf-8")
    files["amr_surveillance"] = isolate

    spatial = directory / "spatial.csv"
    _write_csv(spatial, "spatial")
    files["spatial_medicine_tme"] = spatial

    vector = directory / "vector.gbk"
    vector.write_text(
        "LOCUS       VEC1 12 bp DNA circular\n"
        "DEFINITION  tiny vector.\n"
        "FEATURES             Location/Qualifiers\n"
        "     CDS             1..12\n"
        "ORIGIN\n"
        "        1 acgtacgtacgt\n"
        "//\n",
        encoding="utf-8",
    )
    files["gene_therapy_vector"] = vector

    cart = directory / "cart.fasta"
    cart.write_text(">CAR1\nMKTIIALSYIFCLVFAD\n", encoding="utf-8")
    files["cell_therapy_cart"] = cart

    for key, kind in (
        ("federated_biomedical_ai", "federated"),
        ("clinical_biomarker_survival", "clinical"),
        ("pharmacovigilance_intelligence", "pharmacovigilance"),
        ("synthetic_cohort_trial", "trial"),
        ("autonomous_lab_planner", "lab"),
    ):
        path = directory / f"{key}.csv"
        _write_csv(path, kind)
        files[key] = path

    structure = directory / "complex.pdb"
    structure.write_text(
        "HEADER    TEST\n"
        "ATOM      1  N   GLY A   1      11.104  13.207   2.000  1.00 20.00           N\n"
        "END\n",
        encoding="utf-8",
    )
    files["protein_ligand_codesign"] = structure

    graph = directory / "population.gfa"
    graph.write_text(
        "H\tVN:Z:1.0\nS\t1\tACGT\nS\t2\tTGCA\nL\t1\t+\t2\t+\t0M\nP\tPOP1\t1+,2+\t*\n",
        encoding="utf-8",
    )
    files["pangenome_population_medicine"] = graph
    return files


def native_pipeline_smoke() -> dict[str, Any]:
    failures: list[str] = []
    modules: list[dict[str, Any]] = []
    old_user_root = os.environ.get("BIOINTEL_USER_DATA_DIR")
    try:
        with tempfile.TemporaryDirectory(prefix="biointel-step136-verify-") as temporary:
            temporary_root = Path(temporary)
            project_root = temporary_root / "project"
            user_root = temporary_root / "userdata"
            project_root.mkdir()
            user_root.mkdir()
            os.environ["BIOINTEL_USER_DATA_DIR"] = str(user_root)
            fixtures = _native_fixtures(temporary_root)
            for index, key in enumerate(sorted(NEW_BIOMEDICAL_KEYS), start=1):
                try:
                    staged = stage_for_background(project_root, fixtures[key], key)
                    result = execute_native_pipeline_job(
                        project_root,
                        {
                            "module_key": key,
                            "path": staged["path"],
                            "source_sha256": staged["sha256"],
                            "max_records": 2_000,
                        },
                        job_id=f"verify-{index:02d}",
                    )
                    manifest = Path(result["manifest_path"])
                    loaded = int(result["native_parse"].get("records_loaded", 0))
                    if not manifest.is_file() or loaded < 1:
                        failures.append(f"{key}: missing manifest or empty native parse")
                    modules.append(
                        {
                            "module": key,
                            "format": result["source"]["detected_format"],
                            "records_loaded": loaded,
                            "analysis_state": result["module_analysis"].get("state"),
                            "manifest_sha256": sha256(manifest) if manifest.is_file() else "",
                        }
                    )
                except Exception as exc:
                    failures.append(f"{key}: {type(exc).__name__}: {exc}")
    finally:
        if old_user_root is None:
            os.environ.pop("BIOINTEL_USER_DATA_DIR", None)
        else:
            os.environ["BIOINTEL_USER_DATA_DIR"] = old_user_root
    return {
        "passed": not failures and len(modules) == 15,
        "module_count": len(modules),
        "modules": modules,
        "failures": failures,
    }


def runtime_residue() -> dict[str, Any]:
    residue: list[str] = []
    for path in ROOT.rglob("*"):
        if path.is_dir() and path.name in {"__pycache__", ".pytest_cache"}:
            residue.append(path.relative_to(ROOT).as_posix())
        elif path.is_file() and (
            path.suffix in {".pyc", ".pyo"}
            or path.name.endswith(("-wal", "-shm"))
            or path.name.endswith(".partial")
        ):
            residue.append(path.relative_to(ROOT).as_posix())
    return {"passed": not residue, "count": len(residue), "paths": residue[:100]}


def main() -> int:
    checks: list[dict[str, object]] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    add(checks, "Product version preserved", version == "13.2.0", version)

    profiles = validate_profiles()
    add(checks, "Fifteen native pipeline profiles", profiles["valid"], profiles)
    add(checks, "Native format registry", NEW_FORMAT_KEYS.issubset(NATIVE_FORMATS), sorted(NEW_FORMAT_KEYS))

    native_smoke = native_pipeline_smoke()
    add(checks, "Native raw-data pipeline smoke", native_smoke["passed"], native_smoke)

    science_smoke = module_science_smoke()
    add(checks, "Scientific depth and specialist viewers preserved", science_smoke["passed"], science_smoke)

    syntax = syntax_health()
    add(checks, "Python syntax", syntax["passed"], syntax)

    engineering = run_engineering_gates(ROOT)
    add(checks, "Engineering quality gates", engineering["passed"], engineering)

    database = database_health()
    add(checks, "Database integrity", database["passed"], {key: value for key, value in database.items() if key != "hashes"})
    baseline = baseline_database_hashes()
    changed = sorted(
        path
        for path, digest in baseline.items()
        if path not in database["hashes"] or database["hashes"][path] != digest
    )
    added = sorted(set(database["hashes"]) - set(baseline))
    add(
        checks,
        "Step 135 database baseline preserved",
        bool(baseline) and not changed and not added and len(database["hashes"]) == 36,
        {"baseline_databases": len(baseline), "current_databases": len(database["hashes"]), "changed": changed, "added": added},
    )

    locked_failures = [
        relative
        for relative, expected in LOCKED.items()
        if not (ROOT / relative).is_file() or sha256(ROOT / relative) != expected
    ]
    add(checks, "Protected pages", not locked_failures, locked_failures or "5/5 byte-identical")

    renderer = (ROOT / "src/biointel/nextgen/renderer.py").read_text(encoding="utf-8")
    worker = (ROOT / "src/biointel/jobs/worker.py").read_text(encoding="utf-8")
    page_names = {path.name for path in (ROOT / "pages").glob("*.py")}
    integration = {
        "renderer_hook": "render_native_execution_v136_panel" in renderer,
        "native_tab": "Native pipeline" in renderer,
        "worker_handler": '"nextgen_native_pipeline": self._nextgen_native_pipeline' in worker,
        "new_central_pages": sorted(name for name in page_names if "Step136" in name or "Native_Raw_Data_136" in name),
    }
    add(
        checks,
        "Module-only native execution integration",
        integration["renderer_hook"] and integration["native_tab"] and integration["worker_handler"] and not integration["new_central_pages"],
        integration,
    )

    required = [
        ROOT / "STEP136_RELEASE.json",
        ROOT / "config" / "step136_native_raw_execution.json",
        ROOT / "config" / "step136_reference_bindings.json",
        ROOT / "STEP136_NATIVE_RAW_DATA_REAL_ENGINE_EXECUTION_REPORT.md",
        ROOT / "VERIFY_STEP136_WINDOWS.bat",
    ]
    missing = [path.relative_to(ROOT).as_posix() for path in required if not path.is_file()]
    add(checks, "Release artifacts", not missing, missing or "Complete")

    residue = runtime_residue()
    add(checks, "Runtime residue", residue["passed"], residue)

    payload = {
        "schema": "biointel.step136-native-raw-execution-verification.v1",
        "step": 136,
        "version": version,
        "scope": "native-raw-data-real-engine-readiness-background-pipelines",
        "checks": checks,
        "passed": all(bool(item["passed"]) for item in checks),
    }
    output = ROOT / "reports" / "step136_native_raw_execution_verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
