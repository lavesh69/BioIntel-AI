from __future__ import annotations

from biointel.runtime_paths import runtime_database_path, runtime_report_path

import importlib
import importlib.util
import platform
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from biointel.chemistry.common_compounds import load_common_compound_directory
from biointel.data.coverage_packs import verify_coverage_integrity
from biointel.data.data_packs import verify_data_pack_integrity
from biointel.data.evidence_registry import registry_summary
from biointel.documents.history import history_summary
from biointel.intelligence.data_intelligence import (
    all_database_health,
)
from biointel.internet.connectivity import internet_configuration
from biointel.internet.download_registry import download_summary
from biointel.internet.network_policy import (
    InternetPolicy,
    NetworkPolicyError,
    validate_public_https_url,
)
from biointel.training.model_artifact import load_model_artifact
from biointel.utils.audit_log import verify_audit_chain


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    status: str
    message: str
    category: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _check(
    name: str,
    category: str,
    operation: Callable[[], str],
) -> DiagnosticCheck:
    try:
        message = operation()
        return DiagnosticCheck(
            name=name,
            status="PASS",
            message=message,
            category=category,
        )
    except Exception as exc:
        return DiagnosticCheck(
            name=name,
            status="FAIL",
            message=str(exc),
            category=category,
        )


def run_diagnostics(
    project_root: str | Path,
    *,
    profile: str = "full",
) -> list[DiagnosticCheck]:
    root = Path(project_root).resolve()
    checks: list[DiagnosticCheck] = []

    def python_check() -> str:
        version = sys.version_info
        if version < (3, 11):
            raise RuntimeError(f"Python 3.11+ required; found {platform.python_version()}.")
        return f"Python {platform.python_version()}"

    checks.append(
        _check(
            "Python version",
            "Runtime",
            python_check,
        )
    )

    if profile not in {"quick", "full"}:
        raise ValueError("Diagnostic profile must be 'quick' or 'full'.")

    for module_name in (
        "streamlit",
        "fastapi",
        "Bio",
        "rdkit",
        "sklearn",
        "pandas",
        "numpy",
        "plotly",
        "reportlab",
        "joblib",
        "pypdf",
        "pdfplumber",
        "docx",
        "openpyxl",
        "xlrd",
        "multipart",
        "pytesseract",
        "pypdfium2",
        "pptx",
        "bs4",
        "yaml",
        "odf",
    ):

        def import_check(
            name: str = module_name,
        ) -> str:
            # Importing RDKit, scikit-learn, PDF stacks and office readers can
            # add several seconds to every Diagnostics-page rerun.  The quick
            # profile therefore performs a zero-side-effect availability check;
            # the explicit full profile still imports every dependency.
            if profile == "quick":
                if importlib.util.find_spec(name) is None:
                    raise RuntimeError(f"{name} is not installed")
                return f"{name} available (deep import deferred)"
            module = importlib.import_module(name)
            version = getattr(module, "__version__", "installed")
            return f"{name} {version}"

        checks.append(
            _check(
                f"Import {module_name}",
                "Dependencies",
                import_check,
            )
        )

    for relative in (
        "models",
        "reports",
        "cache/external",
        "data/internet_downloads",
        "data/document_extractions",
    ):
        directory = root / relative

        def directory_check(
            path: Path = directory,
            label: str = relative,
        ) -> str:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".biointel_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return f"{label} is writable"

        checks.append(
            _check(
                f"Writable {relative}",
                "Storage",
                directory_check,
            )
        )

    models = sorted((root / "models").glob("*.joblib"))
    if not models:
        checks.append(
            DiagnosticCheck(
                name="Trusted model artifacts",
                status="WARN",
                message="No .joblib models are currently available.",
                category="Models",
            )
        )
    elif profile == "quick":
        checks.append(
            DiagnosticCheck(
                name="Trusted model artifacts",
                status="PASS",
                message=(
                    f"{len(models)} local model artifact file(s) available; "
                    "deep compatibility loading runs in the full diagnostic profile."
                ),
                category="Models",
            )
        )
    else:
        for model_path in models:

            def model_check(
                path: Path = model_path,
            ) -> str:
                artifact = load_model_artifact(
                    path,
                    trusted_root=root / "models",
                )
                return (
                    f"{artifact.metadata.task_type}, artifact {artifact.metadata.artifact_version}"
                )

            checks.append(
                _check(
                    f"Load {model_path.name}",
                    "Models",
                    model_check,
                )
            )

    # Interactive portfolio/activity views use the quick profile so they do not
    # load every model or deeply validate multi-thousand-record scientific packs
    # on every rerun. This return must apply whether or not a model is installed;
    # otherwise an empty models directory unexpectedly triggers every full data,
    # chemistry, database and governance check. The explicit full profile retains
    # all deep checks.
    if profile == "quick":
        return checks

    def data_pack_check() -> str:
        result = verify_data_pack_integrity(root)
        if not result["valid"]:
            raise RuntimeError("Data-pack integrity failed: " + "; ".join(result["errors"]))
        return f"{result['checked_files']} file(s), {result['total_rows']} bundled row(s)"

    checks.append(
        _check(
            "Bundled data-pack integrity",
            "Data",
            data_pack_check,
        )
    )

    def coverage_pack_check() -> str:
        result = verify_coverage_integrity(root)
        if not result["valid"]:
            raise RuntimeError("Coverage-pack integrity failed: " + "; ".join(result["errors"]))
        totals = result["totals"]
        return (
            f"{result['checked_files']} file(s), "
            f"{totals.get('sequence_records', 0)} sequences, "
            f"{totals.get('molecules', 0)} molecules"
        )

    checks.append(
        _check(
            "Complete coverage-pack integrity",
            "Data",
            coverage_pack_check,
        )
    )

    def database_fabric_check() -> str:
        result = all_database_health(root)
        if result["healthy_count"] != result["database_count"]:
            raise RuntimeError(
                f"Only {result['healthy_count']}/{result['database_count']} databases are healthy."
            )
        return (
            f"{result['database_count']} databases, "
            f"{result['total_rows']} rows, "
            f"{result['total_indices']} indices"
        )

    checks.append(
        _check(
            "Professional database fabric",
            "Databases",
            database_fabric_check,
        )
    )

    for database_key in (
        "knowledge",
        "analytics",
        "assets",
    ):

        def warehouse_check(
            key: str = database_key,
        ) -> str:
            result = all_database_health(root)["professional_warehouses"][key]
            if not result["healthy"]:
                raise RuntimeError(f"{key} warehouse health failed.")
            database = result["database"]
            return (
                f"{database['row_count']} rows, "
                f"{database['index_count']} indices, "
                f"{database['journal_mode']} journal"
            )

        checks.append(
            _check(
                f"{database_key.title()} warehouse",
                "Databases",
                warehouse_check,
            )
        )

    def evidence_registry_check() -> str:
        result = registry_summary(runtime_database_path(root, "evidence.sqlite3"))
        database = result["database"]
        if database["integrity"] != "ok":
            raise RuntimeError("Evidence registry integrity failed.")
        licences = int(result["counts"]["evidence_licenses"])
        if licences < 5:
            raise RuntimeError(
                f"Expected at least five standard licence records; found {licences}."
            )
        return f"{licences} licence profiles, {result['counts']['dataset_evidence_links']} evidence links"

    checks.append(_check("Step 25 evidence registry", "Evidence", evidence_registry_check))

    def document_history_check() -> str:
        result = history_summary(runtime_database_path(root, "document_history.sqlite3"))
        database = result["database"]
        if database["integrity"] != "ok":
            raise RuntimeError("Document extraction history integrity failed.")
        return (
            f"{result['total_runs']} runs, {result['output_count']} outputs, "
            f"{result.get('indexed_content_records', 0)} indexed content records, "
            f"{result.get('scientific_entities', 0)} entities"
        )

    checks.append(
        _check(
            "Step 27 document knowledge history",
            "Documents",
            document_history_check,
        )
    )

    def common_compound_directory_check() -> str:
        directory = load_common_compound_directory(root)
        if len(directory) != 5000:
            raise RuntimeError(f"Expected 5,000 compound-name records; found {len(directory)}.")
        if int(directory["canonical_smiles"].nunique()) != 5000:
            raise RuntimeError("The compound-name directory contains duplicate structures.")
        curated = int((directory["name_type"] == "curated_common_name").sum())
        return f"5,000 names, 5,000 structures, {curated} curated common names"

    checks.append(
        _check(
            "Compound-name directory",
            "Chemistry",
            common_compound_directory_check,
        )
    )

    def internet_policy_check() -> str:
        configuration = internet_configuration()
        policy = configuration["policy"]
        if not policy["enabled"]:
            raise RuntimeError("Outbound internet access is disabled.")
        if not configuration["outbound_only"]:
            raise RuntimeError("Internet policy must remain outbound-only.")
        try:
            validate_public_https_url(
                "https://files.rcsb.org/download/4HHB.cif",
                policy=InternetPolicy(resolve_dns=False),
                resolve_dns=False,
            )
        except NetworkPolicyError as exc:
            raise RuntimeError(str(exc)) from exc
        return (
            f"HTTPS only, {policy['max_download_bytes'] // (1024 * 1024)} MB limit, "
            f"{policy['retries']} retries"
        )

    checks.append(
        _check(
            "Outbound internet security policy",
            "Internet",
            internet_policy_check,
        )
    )

    def download_registry_check() -> str:
        result = download_summary(runtime_database_path(root, "internet_downloads.sqlite3"))
        database = result["database"]
        if database["integrity"] != "ok":
            raise RuntimeError("Internet download registry integrity failed.")
        return (
            f"{result['downloads']} downloads, "
            f"{database['index_count']} indices, "
            f"{database['journal_mode']} journal"
        )

    checks.append(
        _check(
            "Internet download registry",
            "Internet",
            download_registry_check,
        )
    )

    def audit_check() -> str:
        result = verify_audit_chain(runtime_report_path(root, "audit.jsonl"))
        if not result["valid"]:
            raise RuntimeError("Audit chain verification failed: " + "; ".join(result["errors"]))
        return (
            f"{result['chained_events']} chained event(s), "
            f"{result['legacy_events']} legacy event(s)"
        )

    checks.append(
        _check(
            "Audit chain integrity",
            "Governance",
            audit_check,
        )
    )

    required_files = (
        "app.py",
        "requirements.txt",
        "RUN_APP_WINDOWS.bat",
        "RUN_API_WINDOWS.bat",
        "START_BIOINTEL_NO_LOGIN_WINDOWS.bat",
        "IMPORT_REAL_EVIDENCE_WINDOWS.bat",
        "VERIFY_STEP25_WINDOWS.bat",
        "EXTRACT_DOCUMENT_WINDOWS.bat",
        "VERIFY_STEP26_WINDOWS.bat",
    )
    for relative in required_files:
        path = root / relative
        checks.append(
            DiagnosticCheck(
                name=f"Required file: {relative}",
                status="PASS" if path.is_file() else "FAIL",
                message=("Present" if path.is_file() else "Missing from project folder"),
                category="Project files",
            )
        )

    return checks


def diagnostic_summary(
    checks: list[DiagnosticCheck],
) -> dict[str, int | str]:
    counts = {
        "PASS": sum(check.status == "PASS" for check in checks),
        "WARN": sum(check.status == "WARN" for check in checks),
        "FAIL": sum(check.status == "FAIL" for check in checks),
    }
    overall = "FAIL" if counts["FAIL"] else "WARN" if counts["WARN"] else "PASS"
    return {
        **counts,
        "total": len(checks),
        "overall": overall,
    }
