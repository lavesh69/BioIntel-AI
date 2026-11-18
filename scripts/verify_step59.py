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

BIOINFORMATICS_PAGES = (
    "pages/1_Sequence_Analyzer.py",
    "pages/2_Sequence_Comparison.py",
    "pages/16_Batch_Sequence_Analysis.py",
    "pages/56_FASTQ_Genomics_QC.py",
    "pages/57_Variant_Annotation_Workbench.py",
    "pages/59_Transcriptomics_Expression_Lab.py",
    "pages/60_Protein_Annotation_Proteomics.py",
    "pages/61_Structural_Bioinformatics.py",
    "pages/63_Pathway_Network_Analysis.py",
    "pages/66_Omics_Integration_Hub.py",
    "pages/68_Alignment_Phylogeny.py",
    "pages/79_Comparative_Pathogen_Genomics.py",
    "pages/80_Single_Cell_Heterogeneity.py",
    "pages/81_Cancer_Genomics.py",
)

ADVANCED_MODULES = (
    "src/biointel/sequence/advanced.py",
    "src/biointel/genomics/variant_advanced.py",
    "src/biointel/genomics/phylogeny_advanced.py",
    "src/biointel/transcriptomics/advanced.py",
    "src/biointel/proteomics/advanced.py",
    "src/biointel/structural/advanced.py",
    "src/biointel/projects/pathogen_advanced.py",
    "src/biointel/projects/single_cell_advanced.py",
    "src/biointel/projects/cancer_advanced.py",
)

REFERENCE_PACK = "data/reference_packs/bioinformatics_step59"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], root: Path) -> None:
    environment = os.environ.copy()
    if "pytest" in command:
        environment.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
        environment.setdefault("OMP_NUM_THREADS", "1")
        environment.setdefault("OPENBLAS_NUM_THREADS", "1")
        environment.setdefault("MKL_NUM_THREADS", "1")
    subprocess.run(command, cwd=root, check=True, env=environment)


def databases(root: Path) -> list[Path]:
    return sorted(
        path
        for path in (root / "reports").glob("*.sqlite3")
        if path.is_file()
    )


def remove_runtime_residue(root: Path) -> list[str]:
    removed: list[str] = []
    patterns = (
        "*.sqlite3-wal",
        "*.sqlite3-shm",
        "*.db-wal",
        "*.db-shm",
        "*.pyc",
    )
    for pattern in patterns:
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
        with sqlite3.connect(
            f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True
        ) as connection:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
            rows = 0
            tables = [
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
            for table in tables:
                try:
                    rows += int(
                        connection.execute(
                            f'SELECT COUNT(*) FROM "{table}"'
                        ).fetchone()[0]
                    )
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


def verify_reference_pack(root: Path) -> dict[str, Any]:
    pack = root / REFERENCE_PACK
    manifest_path = pack / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    for item in payload.get("files", []):
        path = pack / str(item["path"])
        if not path.is_file():
            failures.append(f"missing:{item['path']}")
            continue
        if path.stat().st_size != int(item["bytes"]):
            failures.append(f"size:{item['path']}")
        if sha256(path) != str(item["sha256"]):
            failures.append(f"sha256:{item['path']}")
    return {
        "pack_id": payload.get("pack_id"),
        "schema_version": payload.get("schema_version"),
        "scope": payload.get("scope"),
        "file_count": len(payload.get("files", [])),
        "failures": failures,
        "passed": not failures and bool(payload.get("files")),
    }


def verify_models(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / "store/model-manifest.json").read_text(encoding="utf-8"))
    mismatches: list[str] = []
    for item in manifest.get("models", []):
        path = root / str(item.get("path", ""))
        if (
            not path.is_file()
            or path.stat().st_size != int(item.get("size_bytes", -1))
            or sha256(path) != str(item.get("sha256", ""))
        ):
            mismatches.append(str(item.get("path", "unknown")))
    return {
        "manifest_count": len(manifest.get("models", [])),
        "mismatches": mismatches,
        "passed": not mismatches and bool(manifest.get("models")),
    }


def focused_tests(root: Path, *, include_ui: bool = False) -> None:
    # Run function and UI rendering tests in separate interpreters. This avoids optional
    # JIT backends retaining process state across Streamlit page tests.
    run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_step59_bioinformatics_excellence.py",
            "-k",
            "not all_bioinformatics_pages_render",
        ],
        root,
    )
    if include_ui:
        for page in BIOINFORMATICS_PAGES:
            selector = Path(page).stem
            run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "tests/test_step59_bioinformatics_excellence.py",
                    "-k",
                    selector,
                ],
                root,
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify BioIntel AI Step 59 bioinformatics excellence release."
    )
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument(
        "--include-ui-tests",
        action="store_true",
        help="Also run all 14 Streamlit page render tests in isolated processes.",
    )
    parser.add_argument(
        "--json-output", default="reports/step59_local_verification.json"
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()

    baseline_databases = databases(root)
    with TemporaryDirectory(prefix="biointel-step59-db-") as temp_directory:
        backup = Path(temp_directory)
        for database in baseline_databases:
            shutil.copy2(database, backup / database.name)
        try:
            run([sys.executable, "-m", "ruff", "check", "."], root)
            run(
                [
                    sys.executable,
                    "-m",
                    "compileall",
                    "-q",
                    "app.py",
                    "pages",
                    "src",
                    "scripts",
                    "platform",
                ],
                root,
            )
            if not args.skip_tests:
                focused_tests(root, include_ui=bool(args.include_ui_tests))
        finally:
            remove_runtime_residue(root)
            for database in baseline_databases:
                saved = backup / database.name
                if saved.is_file():
                    shutil.copy2(saved, database)
            remove_runtime_residue(root)

    db_health, row_count = database_health(root)
    reference_pack = verify_reference_pack(root)
    models = verify_models(root)
    engineering = run_engineering_gates(root)
    secrets = scan_repository_secrets(root)
    capabilities = capabilities_dict()
    missing_pages = [path for path in BIOINFORMATICS_PAGES if not (root / path).is_file()]
    missing_modules = [path for path in ADVANCED_MODULES if not (root / path).is_file()]
    residue = sorted(
        path.relative_to(root).as_posix()
        for pattern in ("*.sqlite3-wal", "*.sqlite3-shm", "*.db-wal", "*.db-shm")
        for path in root.rglob(pattern)
    )

    result = {
        "release": "BioIntel AI Step 59 Bioinformatics Excellence",
        "bioinformatics_page_count": len(BIOINFORMATICS_PAGES),
        "missing_bioinformatics_pages": missing_pages,
        "advanced_module_count": len(ADVANCED_MODULES),
        "missing_advanced_modules": missing_modules,
        "focused_regression": "skipped" if args.skip_tests else "passed",
        "ui_render_regression": (
            "skipped" if args.skip_tests or not args.include_ui_tests else "passed"
        ),
        "ruff": "passed",
        "python_compilation": "passed",
        "database_count": len(db_health),
        "healthy_databases": sum(item["integrity"] == "ok" for item in db_health),
        "database_rows": row_count,
        "foreign_key_violations": sum(
            int(item["foreign_key_violations"]) for item in db_health
        ),
        "model_verification": models,
        "reference_pack": reference_pack,
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
        and result["healthy_databases"] == result["database_count"] == 20
        and result["foreign_key_violations"] == 0
        and bool(models["passed"])
        and bool(reference_pack["passed"])
        and bool(engineering["passed"])
        and bool(secrets["passed"])
        and not residue
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
