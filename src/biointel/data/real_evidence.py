from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from biointel.data.curation import curate_activity_dataset, curation_summary_dict
from biointel.data.dataset_registry import register_dataset
from biointel.data.evidence_registry import (
    complete_import_run,
    evidence_readiness,
    link_curated_dataset,
    register_source,
    seed_standard_licenses,
    start_import_run,
)


@dataclass(frozen=True)
class RealEvidenceImportResult:
    dataset_path: str
    error_path: str
    dataset_sha256: str
    source_id: str
    import_run_id: str
    summary: dict[str, Any]
    readiness: dict[str, Any]
    manifest: dict[str, Any]

_PROVIDER_LICENSE = {
    "chembl": "CHEMBL_TERMS",
    "bindingdb": "BINDINGDB_TERMS",
    "pubchem_bioassay": "PUBCHEM_PUBLIC_DATA",
    "uniprot": "UNIPROT_TERMS",
    "local": "LOCAL_USER_SUPPLIED",
    "generic": "LOCAL_USER_SUPPLIED",
}

_VERIFIED_PROVIDER_KEYS = {"chembl", "bindingdb", "pubchem_bioassay", "uniprot"}

def _authenticity_status(provider: str, source_release: str | None, metadata: dict[str, Any] | None) -> tuple[str, bool]:
    provider_key = provider.strip().lower()
    release = (source_release or "").strip().lower()
    if provider_key in _VERIFIED_PROVIDER_KEYS and release not in {"", "demo", "synthetic", "example"}:
        return "provider_reference_pending_review", True
    attested = bool((metadata or {}).get("experimental_attestation"))
    if provider_key in {"local", "generic"} and attested:
        return "user_attested_pending_review", True
    return "user_supplied_unverified", False

def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _provider_license(provider: str) -> str:
    return _PROVIDER_LICENSE.get(provider.strip().lower(), "LOCAL_USER_SUPPLIED")

def import_curated_evidence(
    dataframe: pd.DataFrame,
    *,
    provider: str,
    source_release: str | None,
    registry_path: str | Path,
    dataset_registry_path: str | Path,
    output_directory: str | Path,
    source_homepage: str | None = None,
    source_sha256: str | None = None,
    source_local_path: str | None = None,
    active_threshold: float = 6.0,
    aggregate_duplicates: bool = True,
    metadata: dict[str, Any] | None = None,
    curation_kwargs: dict[str, Any] | None = None,
) -> RealEvidenceImportResult:
    provider_key = provider.strip().lower()
    authenticity_status, real_experimental_data = _authenticity_status(
        provider_key, source_release, metadata
    )
    if not provider_key:
        raise ValueError("provider is required.")
    evidence_db = Path(registry_path).resolve()
    dataset_db = Path(dataset_registry_path).resolve()
    out_dir = Path(output_directory).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    seed_standard_licenses(evidence_db)
    run = start_import_run(
        evidence_db,
        provider=provider_key,
        source_release=source_release,
        source_sha256=source_sha256,
        parameters={
            "active_threshold": active_threshold,
            "aggregate_duplicates": aggregate_duplicates,
            **(metadata or {}),
        },
    )
    try:
        curated, errors, summary = curate_activity_dataset(
            dataframe,
            active_threshold=active_threshold,
            aggregate_duplicates=aggregate_duplicates,
            source_database=provider_key,
            **(curation_kwargs or {}),
        )
        if curated.empty:
            raise ValueError("No valid activity rows remained after curation.")
        license_id = _provider_license(provider_key)
        curated["license_id"] = curated.get("license_id", pd.Series(index=curated.index, dtype=object)).fillna(license_id)
        curated["source_release"] = source_release
        curated["review_status"] = curated.get("review_status", pd.Series(index=curated.index, dtype=object)).fillna("pending")
        summary = replace(
            summary,
            licensed_rows=int(curated["license_id"].notna().sum()),
            review_pending_rows=int((curated["review_status"] == "pending").sum()),
        )
        safe_release = re.sub(r"[^A-Za-z0-9._-]+", "_", source_release or "current")
        dataset_path = out_dir / f"{provider_key}_{safe_release}_curated.csv"
        error_path = out_dir / f"{provider_key}_{safe_release}_rejected.csv"
        curated.to_csv(dataset_path, index=False)
        errors.to_csv(error_path, index=False)
        file_hash = sha256_file(dataset_path)
        dataset_record = register_dataset(
            dataset_db,
            curated,
            dataset_name=f"{provider_key} {source_release or 'current'} real evidence",
            dataset_version=source_release or datetime.now(UTC).strftime("%Y%m%d"),
            task_type="unlabelled",
            source_description=f"Curated experimental activity evidence imported from {provider_key}.",
            activity_type="mixed",
            notes="Step 25 real-evidence import. Review approval is required before scientific release.",
            metadata={
                "file_sha256": file_hash,
                "real_experimental_data": real_experimental_data,
                "synthetic": False,
                "authenticity_status": authenticity_status,
                "release_eligible": False,
                "provider": provider_key,
                "source_release": source_release,
                "curation_summary": curation_summary_dict(summary),
            },
        )
        dataset_hash = dataset_record.dataset_sha256
        source = register_source(
            evidence_db,
            source_name=provider_key,
            source_release=source_release,
            homepage_url=source_homepage,
            license_id=license_id,
            source_sha256=source_sha256 or file_hash,
            local_path=source_local_path or str(dataset_path),
            record_count=len(curated),
            metadata=metadata or {},
        )
        link_curated_dataset(
            evidence_db,
            dataset_sha256=dataset_hash,
            source_id=source.source_id,
            curated=curated,
            default_license_id=license_id,
        )
        readiness = evidence_readiness(evidence_db, dataset_hash)
        manifest = {
            "dataset_sha256": dataset_hash,
            "real_experimental_data": real_experimental_data,
            "synthetic": False,
            "authenticity_status": authenticity_status,
            "release_eligible": False,
            "provider": provider_key,
            "source_release": source_release,
            "source_id": source.source_id,
            "import_run_id": run.run_id,
            "license_id": license_id,
            **readiness,
        }
        complete_import_run(
            evidence_db,
            run.run_id,
            status="completed",
            input_rows=len(dataframe),
            curated_rows=len(curated),
            rejected_rows=len(errors),
            report={"summary": curation_summary_dict(summary), "readiness": readiness, "manifest": manifest},
        )
        return RealEvidenceImportResult(
            str(dataset_path),
            str(error_path),
            dataset_hash,
            source.source_id,
            run.run_id,
            curation_summary_dict(summary),
            readiness,
            manifest,
        )
    except Exception as exc:
        complete_import_run(
            evidence_db,
            run.run_id,
            status="failed",
            input_rows=len(dataframe),
            curated_rows=0,
            rejected_rows=len(dataframe),
            report={"error": str(exc)},
        )
        raise

def result_dict(result: RealEvidenceImportResult) -> dict[str, Any]:
    return asdict(result)
