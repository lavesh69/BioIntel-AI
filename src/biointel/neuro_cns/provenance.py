from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import pandas as pd
except ImportError:
    pd = None

from biointel.neuro_cns.data import project_root


STEP_VERSION = "202"
RELEASE_LABEL = "Neuro Production Readiness, Robust Installation & Demo Qualification"


RESOURCE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {"resource_id": "target_registry", "provider": "BioIntel bundled reference snapshot", "file": "target_registry_v1.json", "kind": "target/disease/expression", "licence_status": "demo-reference-only", "validation_status": "schema-checked", "release_eligible": False},
    {"resource_id": "side_effect_map", "provider": "BioIntel bundled demonstration map", "file": "side_effect_map_v1.json", "kind": "target-side-effect associations", "licence_status": "demo-reference-only", "validation_status": "schema-checked", "release_eligible": False},
    {"resource_id": "bbb_reference", "provider": "User-approved B3DB-style binding", "file": None, "kind": "BBB benchmark", "licence_status": "not-bound", "validation_status": "adapter-ready", "release_eligible": False},
    {"resource_id": "protein_domains", "provider": "User-approved Pfam/InterPro binding", "file": None, "kind": "protein domains", "licence_status": "not-bound", "validation_status": "adapter-ready", "release_eligible": False},
    {"resource_id": "gpcr_reference", "provider": "User-approved GPCR reference binding", "file": None, "kind": "GPCR families", "licence_status": "not-bound", "validation_status": "adapter-ready", "release_eligible": False},
    {"resource_id": "variant_evidence", "provider": "User-approved ClinVar/gnomAD/VEP binding", "file": None, "kind": "variant evidence", "licence_status": "not-bound", "validation_status": "adapter-ready", "release_eligible": False},
    {"resource_id": "brain_expression", "provider": "User-approved brain atlas binding", "file": None, "kind": "regional/cell-type expression", "licence_status": "not-bound", "validation_status": "adapter-ready", "release_eligible": False},
    {"resource_id": "model_organisms", "provider": "User-approved MGI/RGD/ZFIN/Ensembl binding", "file": None, "kind": "orthology/phenotype", "licence_status": "not-bound", "validation_status": "adapter-ready", "release_eligible": False},
    {"resource_id": "clinical_trials", "provider": "User-approved current trial source", "file": None, "kind": "clinical evidence", "licence_status": "not-bound", "validation_status": "upload-supported", "release_eligible": False},
    {"resource_id": "neuroimaging_adapters", "provider": "Optional NiBabel/pydicom/SimpleITK engines", "file": None, "kind": "specialist imaging", "licence_status": "optional-dependency", "validation_status": "environment-qualification-required", "release_eligible": False},
    {"resource_id": "neural_signal_adapters", "provider": "Optional MNE-compatible engines", "file": None, "kind": "EDF/BDF/FIF signal processing", "licence_status": "optional-dependency", "validation_status": "environment-qualification-required", "release_eligible": False},
    {"resource_id": "aggregation_method", "provider": "User-approved aggregation engine", "file": None, "kind": "protein aggregation methodology", "licence_status": "not-bound", "validation_status": "method-qualification-required", "release_eligible": False},
    {"resource_id": "side_effect_reference", "provider": "User-approved labelled side-effect resource", "file": None, "kind": "clinical side-effect evidence", "licence_status": "not-bound", "validation_status": "data-qualification-required", "release_eligible": False},
    {"resource_id": "blood_csf_method", "provider": "User-approved blood-CSF/PBPK methodology", "file": None, "kind": "blood-CSF transport", "licence_status": "not-bound", "validation_status": "feasibility-required", "release_eligible": False},
    {"resource_id": "adme_models", "provider": "User-approved CNS ADME model panel", "file": None, "kind": "transporters/CYP/clearance", "licence_status": "not-bound", "validation_status": "model-qualification-required", "release_eligible": False},
    {"resource_id": "pk_validation", "provider": "User-approved brain PK/PBPK validation set", "file": None, "kind": "brain exposure and occupancy", "licence_status": "not-bound", "validation_status": "external-validation-required", "release_eligible": False},
    {"resource_id": "omics_external_validation", "provider": "User-approved independent omics cohort", "file": None, "kind": "biomarker external validation", "licence_status": "not-bound", "validation_status": "external-cohort-required", "release_eligible": False},
    {"resource_id": "precision_external_cohort", "provider": "User-approved longitudinal precision-neurology cohort", "file": None, "kind": "patient stratification validation", "licence_status": "not-bound", "validation_status": "independent-cohort-required", "release_eligible": False},
    {"resource_id": "step200_feature_registry", "provider": "BioIntel Step200 bundled feature registry", "file": "step200_max_potential_feature_registry.json", "kind": "software capability manifest", "licence_status": "bundled", "validation_status": "schema-checked", "release_eligible": True},
    {"resource_id": "step201_feature_registry", "provider": "BioIntel Step201 bundled completion registry", "file": "step201_completion_feature_registry.json", "kind": "software capability manifest", "licence_status": "bundled", "validation_status": "schema-checked", "release_eligible": True},
    {"resource_id": "step202_feature_registry", "provider": "BioIntel Step202 bundled production registry", "file": "step202_production_feature_registry.json", "kind": "software capability manifest", "licence_status": "bundled", "validation_status": "schema-checked", "release_eligible": True},
    {"resource_id": "step202_demo_pack", "provider": "BioIntel Step202 synthetic demonstration pack", "file": "demo_packs/step202/manifest.json", "kind": "synthetic demo datasets", "licence_status": "bundled-demo-only", "validation_status": "hash-verified", "release_eligible": False},
)


def _sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resource_registry_rows() -> list[dict[str, Any]]:
    data_dir = project_root() / "data" / "neuro_cns"
    rows: list[dict[str, Any]] = []
    for definition in RESOURCE_DEFINITIONS:
        row = dict(definition)
        filename = row.get("file")
        path = data_dir / str(filename) if filename else None
        row["installed"] = bool(path and path.exists())
        row["path"] = f"data/neuro_cns/{filename}" if path else None
        row["sha256"] = _sha256(path) if path else None
        row["checked_at_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
        rows.append(row)
    user_registry = Path.home() / ".biointel" / "neuro_cns" / "resources" / "resource_bindings.json"
    if user_registry.exists():
        try:
            payload = json.loads(user_registry.read_text(encoding="utf-8"))
            for binding in payload.get("bindings", []):
                local_path = Path(str(binding.get("local_asset_path") or ""))
                current_sha = _sha256(local_path) if local_path.exists() else None
                integrity_match = bool(current_sha and current_sha == binding.get("sha256"))
                rows.append({
                    "resource_id": binding.get("resource_id"),
                    "provider": binding.get("provider"),
                    "file": binding.get("file_name"),
                    "kind": binding.get("kind"),
                    "licence_status": binding.get("licence_status"),
                    "commercial_use_status": binding.get("commercial_use_status"),
                    "validation_status": binding.get("validation_status"),
                    "release_eligible": bool(binding.get("release_eligible")) and integrity_match,
                    "installed": local_path.exists(),
                    "path": str(local_path) if local_path.exists() else None,
                    "sha256": current_sha or binding.get("sha256"),
                    "declared_sha256": binding.get("sha256"),
                    "integrity_match": integrity_match,
                    "release_version": binding.get("release_version"),
                    "schema_version": binding.get("schema_version"),
                    "checked_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                    "source": "user-local-binding",
                })
        except Exception:
            rows.append({
                "resource_id": "user_resource_bindings",
                "provider": "Local binding registry",
                "kind": "binding registry",
                "licence_status": "unknown",
                "validation_status": "registry-unreadable",
                "release_eligible": False,
                "installed": True,
                "path": str(user_registry),
                "sha256": _sha256(user_registry),
                "checked_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            })
    return rows


def resource_registry_frame() -> pd.DataFrame:
    return pd.DataFrame(resource_registry_rows())


def provenance_block(module_key: str, *, input_fingerprint: str | None = None, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema": "biointel.neuro-cns.provenance.v2",
        "step": STEP_VERSION,
        "release_label": RELEASE_LABEL,
        "module_key": module_key,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "input_fingerprint_sha256": input_fingerprint,
        "parameters": parameters or {},
        "resources": [
            {key: row.get(key) for key in ("resource_id", "provider", "sha256", "validation_status", "release_eligible")}
            for row in resource_registry_rows()
            if row.get("installed")
        ],
        "controlled_release_eligible": False,
    }


def write_resource_manifest(path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "biointel.neuro-cns.resource-registry.v2",
        "step": STEP_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "resources": resource_registry_rows(),
    }
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return destination
