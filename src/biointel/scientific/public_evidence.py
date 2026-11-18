from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _control(key: str, label: str, passed: bool, evidence: str, boundary: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "passed": bool(passed),
        "evidence": evidence,
        "boundary": boundary,
    }


def public_external_evidence_readiness(root: str | Path) -> dict[str, Any]:
    """Score observable bundled public evidence without inflating product validation."""

    base = Path(root).resolve()
    pack = base / "data" / "real_scientific_pack"
    external = base / "data" / "external_scientific_evidence"
    catalog = json.loads((pack / "catalog.json").read_text(encoding="utf-8"))
    datasets = list(catalog.get("datasets", []))
    providers = {str(item.get("provider", "")).strip() for item in datasets if item.get("provider")}
    scopes = {str(item.get("scope", "")).strip() for item in datasets if item.get("scope")}
    modules = {
        str(module)
        for item in datasets
        for module in item.get("modules", [])
        if str(module).strip()
    }
    official_urls = [
        str(item.get("source_url"))
        for item in datasets
        if urlparse(str(item.get("source_url", ""))).scheme == "https"
        and urlparse(str(item.get("source_url", ""))).hostname
    ]
    file_entries = [meta for item in datasets for meta in item.get("file_metadata", [])]
    verified_files = 0
    verified_bytes = 0
    integrity_failures: list[str] = []
    for item in file_entries:
        path = base / str(item.get("path", ""))
        expected_size = int(item.get("size_bytes", -1))
        expected_sha = str(item.get("sha256", ""))
        if path.is_file() and path.stat().st_size == expected_size and _sha256(path) == expected_sha:
            verified_files += 1
            verified_bytes += expected_size
        else:
            integrity_failures.append(str(item.get("path", "")))
    multisite = [
        item
        for item in datasets
        if any(
            token in str(item.get("scope", "")).lower()
            for token in ("multisite", "multilaboratory")
        )
    ]
    identifiers = pd.read_csv(pack / "manifests" / "verified_public_reference_catalog.csv")
    stable_identifiers = int(identifiers["stable_id"].astype(str).nunique())
    entity_types = int(identifiers["record_type"].astype(str).nunique())
    benchmark = json.loads((external / "uci_wdbc_benchmark_report.json").read_text())
    benchmark_model = base / "models" / "legacy" / "public_wdbc_reproducible_benchmark.joblib"
    holdout_path = external / "uci_wdbc_untouched_holdout.csv"
    predictions_path = external / "uci_wdbc_holdout_predictions.csv"
    benchmark_ok = (
        benchmark_model.is_file()
        and holdout_path.is_file()
        and predictions_path.is_file()
        and _sha256(benchmark_model) == benchmark.get("model_sha256")
        and _sha256(pack / "cancer" / "uci_wdbc_real.csv") == benchmark.get("dataset_sha256")
        and int(benchmark.get("holdout_rows", 0)) == len(pd.read_csv(holdout_path))
        and len(pd.read_csv(predictions_path)) == int(benchmark.get("holdout_rows", 0))
        and float(benchmark.get("metrics", {}).get("holdout_roc_auc", 0.0)) >= 0.90
        and float(benchmark.get("metrics", {}).get("holdout_balanced_accuracy", 0.0)) >= 0.90
        and benchmark.get("clinical_use") is False
    )
    manifest = json.loads((external / "evidence_bundle_manifest.json").read_text())
    artifacts = list(manifest.get("artifacts", []))
    manifest_verified = 0
    for item in artifacts:
        path = base / str(item.get("path", ""))
        if (
            path.is_file()
            and path.stat().st_size == int(item.get("size_bytes", -1))
            and _sha256(path) == str(item.get("sha256", ""))
        ):
            manifest_verified += 1
    licence_count = sum(bool(str(item.get("licence", "")).strip()) for item in datasets)
    boundary_text = " ".join(
        [
            str(catalog.get("boundary", "")),
            str(manifest.get("claim_boundary", "")),
            str(benchmark.get("scope", "")),
            " ".join(str(item) for item in benchmark.get("limitations", [])),
        ]
    ).lower()
    boundary_ok = (
        "not" in boundary_text
        and "clinical" in boundary_text
        and "regulatory" in boundary_text
        and benchmark.get("clinical_use") is False
    )
    controls = [
        _control("catalog_schema", "Versioned real-scientific-data catalog", catalog.get("dataset_count") == len(datasets) and len(datasets) >= 14, f"{len(datasets)} parsed dataset entries.", "Inventory does not prove clinical efficacy."),
        _control("provider_diversity", "Independent public-provider diversity", len(providers) >= 10, f"{len(providers)} provider groups.", "Provider diversity is not a BioIntel validation study."),
        _control("scientific_modality_diversity", "Cross-modality scientific coverage", len(scopes) >= 10 and len(modules) >= 30, f"{len(scopes)} scopes mapped to {len(modules)} modules.", "Breadth does not guarantee equal cohort depth."),
        _control("official_source_urls", "Official HTTPS source traceability", len(official_urls) >= len(datasets) - 1, f"{len(official_urls)}/{len(datasets)} HTTPS sources.", "URLs are provenance metadata."),
        _control("licence_attribution", "Licence and attribution coverage", licence_count == len(datasets), f"{licence_count}/{len(datasets)} licensed/attributed.", "Commercial terms still require legal review."),
        _control("artifact_integrity", "Checksum-bound artifact integrity", verified_files == len(file_entries) and not integrity_failures, f"{verified_files}/{len(file_entries)} files verified ({verified_bytes:,} bytes).", "Integrity validates bytes, not every interpretation."),
        _control("multisite_reproducibility", "Retrospective multisite and multilaboratory evidence", len(multisite) >= 3, f"{len(multisite)} multisite/multilaboratory records.", "Retrospective evidence is not a prospective BioIntel study."),
        _control("stable_identifier_coverage", "Stable identifier and provider mapping", stable_identifiers >= 50 and entity_types >= 3, f"{stable_identifiers} identifiers across {entity_types} entity types.", "Identifiers support traceability, not outcomes."),
        _control("reproducible_public_benchmark", "Reproducible real-data benchmark", benchmark_ok, f"{benchmark.get('holdout_rows', 0)} holdout rows; ROC-AUC {benchmark.get('metrics', {}).get('holdout_roc_auc', 0.0):.3f}; balanced accuracy {benchmark.get('metrics', {}).get('holdout_balanced_accuracy', 0.0):.3f}.", "Software benchmark only; not patient-care validation."),
        _control("bundle_manifest", "Machine-verifiable evidence bundle manifest", manifest_verified == len(artifacts) and len(artifacts) >= 16, f"{manifest_verified}/{len(artifacts)} artifacts verified.", "Manifest integrity does not replace peer review."),
        _control("claim_boundary", "Scientific claim-boundary enforcement", boundary_ok, "Public evidence is explicitly separated from product-specific validation.", "Only independent BioIntel-specific evidence can raise product-validation scores."),
    ]
    passed = sum(bool(item["passed"]) for item in controls)
    return {
        "schema": "biointel.public-external-evidence-readiness.v1",
        "score": round(10.0 * passed / len(controls), 1),
        "passed": passed,
        "total": len(controls),
        "complete": passed == len(controls),
        "controls": controls,
        "failed_controls": [item["label"] for item in controls if not item["passed"]],
        "summary": {
            "dataset_entries": len(datasets),
            "providers": len(providers),
            "evidence_scopes": len(scopes),
            "module_mappings": len(modules),
            "verified_files": verified_files,
            "verified_bytes": verified_bytes,
            "retrospective_reproducibility_studies": len(multisite),
            "stable_identifiers": stable_identifiers,
            "benchmark_holdout_rows": int(benchmark.get("holdout_rows", 0)),
        },
        "boundary": "10/10 means the bundled public reference pack is diverse, attributed, checksum-bound and reproducible; it does not mean BioIntel completed independent prospective clinical/pharma validation or regulatory authorization.",
    }
