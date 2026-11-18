from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.bioinformatics_capabilities import capabilities_dict
from biointel.engineering.quality_gates import run_engineering_gates
from biointel.engineering.repository_audit import scan_repository_secrets

LAB_PAGES = (
    "pages/58_Primer_CRISPR_Codon_Studio.py",
    "pages/64_Wet_Lab_Biotechnology.py",
    "pages/65_Microbiology_Metagenomics.py",
    "pages/82_Metagenomics_Pipeline.py",
)
LAB_MODULES = (
    "src/biointel/biotech/lab_schema.py",
    "src/biointel/biotech/assays_advanced.py",
    "src/biointel/biotech/experimental_design.py",
    "src/biointel/genomics/design_advanced.py",
    "src/biointel/genomics/codon_advanced.py",
    "src/biointel/microbiology/metagenomics.py",
    "src/biointel/projects/metagenomics_advanced.py",
    "src/biointel/projects/metagenomics_raw_reads.py",
    "src/biointel/projects/single_cell_advanced.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], root: Path) -> None:
    environment = os.environ.copy()
    environment.setdefault("PYTHONPATH", "src")
    environment.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    environment.setdefault("OMP_NUM_THREADS", "1")
    environment.setdefault("OPENBLAS_NUM_THREADS", "1")
    environment.setdefault("MKL_NUM_THREADS", "1")
    subprocess.run(command, cwd=root, check=True, env=environment)


def databases(root: Path) -> list[Path]:
    return sorted(path for path in (root / "reports").glob("*.sqlite3") if path.is_file())


def remove_runtime_residue(root: Path) -> list[str]:
    removed: list[str] = []
    for pattern in ("*.sqlite3-wal", "*.sqlite3-shm", "*.db-wal", "*.db-shm", "*.pyc"):
        for path in root.rglob(pattern):
            removed.append(path.relative_to(root).as_posix())
            path.unlink(missing_ok=True)
    for directory_name in ("__pycache__", ".pytest_cache", ".ruff_cache"):
        for directory in sorted(root.rglob(directory_name), reverse=True):
            if directory.is_dir():
                shutil.rmtree(directory, ignore_errors=True)
    return sorted(set(removed))


def database_health(root: Path) -> tuple[list[dict[str, Any]], int]:
    output: list[dict[str, Any]] = []
    total_rows = 0
    for database in databases(root):
        with sqlite3.connect(f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True) as connection:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
            tables = [
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
            rows = 0
            for table in tables:
                try:
                    rows += int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                except sqlite3.Error:
                    continue
        total_rows += rows
        output.append(
            {
                "path": database.relative_to(root).as_posix(),
                "integrity": integrity,
                "foreign_key_violations": len(foreign_keys),
                "table_count": len(tables),
                "row_count": rows,
            }
        )
    return output, total_rows


def verify_models(root: Path) -> dict[str, Any]:
    payload = json.loads((root / "store/model-manifest.json").read_text(encoding="utf-8"))
    mismatches = []
    for item in payload.get("models", []):
        path = root / str(item.get("path", ""))
        if (
            not path.is_file()
            or path.stat().st_size != int(item.get("size_bytes", -1))
            or sha256(path) != str(item.get("sha256", ""))
        ):
            mismatches.append(str(item.get("path", "unknown")))
    return {
        "manifest_count": len(payload.get("models", [])),
        "mismatches": mismatches,
        "passed": not mismatches and bool(payload.get("models")),
    }


def verify_template_pack(root: Path) -> dict[str, Any]:
    directory = root / "data/lab_templates"
    payload = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    for item in payload.get("files", []):
        path = directory / str(item["path"])
        if not path.is_file():
            failures.append(f"missing:{item['path']}")
        elif path.stat().st_size != int(item["bytes"]):
            failures.append(f"size:{item['path']}")
        elif sha256(path) != str(item["sha256"]):
            failures.append(f"sha256:{item['path']}")
    archive = directory / "LAB_ANALYTICS_TEMPLATE_PACK.zip"
    return {
        "pack_id": payload.get("pack_id"),
        "file_count": len(payload.get("files", [])),
        "archive_bytes": archive.stat().st_size if archive.is_file() else 0,
        "archive_sha256": sha256(archive) if archive.is_file() else None,
        "failures": failures,
        "passed": not failures and archive.is_file() and bool(payload.get("files")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify BioIntel AI Step 60 Lab Analytics Excellence release.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--json-output", default="reports/step60_local_verification.json")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    baseline_databases = databases(root)
    with TemporaryDirectory(prefix="biointel-step60-db-") as temp_directory:
        backup = Path(temp_directory)
        for database in baseline_databases:
            shutil.copy2(database, backup / database.name)
        try:
            run([sys.executable, "-m", "ruff", "check", "."], root)
            run([sys.executable, "-m", "compileall", "-q", "app.py", "pages", "src", "scripts", "platform"], root)
            if not args.skip_tests:
                run([sys.executable, "-m", "pytest", "-q", "tests/test_step60_lab_analytics_excellence.py"], root)
        finally:
            remove_runtime_residue(root)
            for database in baseline_databases:
                saved = backup / database.name
                if saved.is_file():
                    shutil.copy2(saved, database)
            remove_runtime_residue(root)

    db_health, row_count = database_health(root)
    models = verify_models(root)
    templates = verify_template_pack(root)
    engineering = run_engineering_gates(root)
    secrets = scan_repository_secrets(root)
    capabilities = capabilities_dict()
    missing_pages = [path for path in LAB_PAGES if not (root / path).is_file()]
    missing_modules = [path for path in LAB_MODULES if not (root / path).is_file()]
    residue = sorted(
        path.relative_to(root).as_posix()
        for pattern in ("*.sqlite3-wal", "*.sqlite3-shm", "*.db-wal", "*.db-shm")
        for path in root.rglob(pattern)
    )
    result = {
        "release": "BioIntel AI Step 60 Lab Analytics Excellence",
        "lab_page_count": len(LAB_PAGES),
        "missing_lab_pages": missing_pages,
        "advanced_module_count": len(LAB_MODULES),
        "missing_advanced_modules": missing_modules,
        "focused_regression": "skipped" if args.skip_tests else "passed",
        "ruff": "passed",
        "python_compilation": "passed",
        "database_count": len(db_health),
        "healthy_databases": sum(item["integrity"] == "ok" for item in db_health),
        "database_rows": row_count,
        "foreign_key_violations": sum(int(item["foreign_key_violations"]) for item in db_health),
        "model_verification": models,
        "lab_template_pack": templates,
        "capability_catalog_count": len(capabilities),
        "capabilities_detected": sum(bool(item["available"]) for item in capabilities),
        "engineering_gates": engineering,
        "secret_scan": secrets,
        "sqlite_runtime_residue": residue,
        "databases": db_health,
    }
    output = root / args.json_output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    passed = (
        not missing_pages
        and not missing_modules
        and result["database_count"] >= 20
        and result["healthy_databases"] == result["database_count"]
        and result["foreign_key_violations"] == 0
        and bool(models["passed"])
        and bool(templates["passed"])
        and bool(engineering["passed"])
        and bool(secrets["passed"])
        and not residue
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
