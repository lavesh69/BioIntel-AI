from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pandas as pd
from packaging.utils import canonicalize_name, parse_wheel_filename

from biointel.engine_audit_v196 import audit_catalog
from biointel.module_features_v208.ingestion import FORMAT_CAPABILITIES
from biointel.native.engines import ENGINE_REGISTRY
from biointel.ui.public_branding import public_engine_key, public_engine_name

from .paths import project_root


PACK_KEYS = {
    "Bioinformatics Engine Pack": "bioinformatics",
    "Discovery Engine Pack": "discovery",
    "Lab Imaging & Proteomics Pack": "lab-imaging-proteomics",
    "AI/GPU Model Pack": "ai-gpu-models",
    "Specialist Extension Pack": "specialist-extensions",
}

ADAPTER_INSTALLS: dict[str, dict[str, Any]] = {
    "h5ad": {"packages": ("anndata", "h5py", "zarr"), "engine": "scanpy"},
    "zarr": {"packages": ("anndata", "zarr"), "engine": "scanpy"},
    "nifti": {"packages": ("nibabel",), "engine": ""},
    "dicom": {"packages": ("pydicom",), "engine": ""},
    "edf_bdf_fif": {"packages": ("mne",), "engine": ""},
    "bam_cram_bcf": {"packages": ("pysam",), "engine": "samtools"},
    "bigwig": {"packages": ("pyBigWig",), "engine": "deeptools"},
    "plink": {"packages": (), "engine": "plink2"},
    "mzml": {"packages": ("pymzml",), "engine": "openms"},
    "fast5": {"packages": ("ont-fast5-api",), "engine": "dorado"},
    "pod5": {"packages": ("pod5",), "engine": "dorado"},
    "ome_tiff": {"packages": ("Pillow",), "engine": "openslide"},
}

PRODUCTION_SERVICES: tuple[dict[str, Any], ...] = (
    {"service": "postgresql", "label": "PostgreSQL Repository", "package": "psycopg", "environment": "BIOINTEL_DATABASE_URL", "purpose": "Concurrent multi-user repository"},
    {"service": "redis", "label": "Distributed Queue / Redis", "package": "redis", "environment": "BIOINTEL_REDIS_URL", "purpose": "Distributed jobs, retries and rate limits"},
    {"service": "object_storage", "label": "S3-compatible Object Storage", "package": "boto3", "environment": "BIOINTEL_OBJECT_STORAGE_ENDPOINT", "purpose": "Large dataset and report objects"},
    {"service": "oidc", "label": "OIDC Enterprise Identity", "package": "authlib", "environment": "BIOINTEL_OIDC_ISSUER", "purpose": "Organization login and account lifecycle"},
    {"service": "observability", "label": "OpenTelemetry Observability", "package": "opentelemetry", "environment": "OTEL_EXPORTER_OTLP_ENDPOINT", "purpose": "Metrics, traces and health evidence"},
    {"service": "crdt", "label": "CRDT Simultaneous Editing", "package": "biointel.engine_platform_v196.crdt", "environment": "BIOINTEL_CRDT_ENABLED", "purpose": "Built-in deterministic conflict-free text merging"},
)


def _release_manifest_path(root: str | Path | None = None) -> Path:
    base = Path(root).resolve() if root else project_root()
    return base / "config" / "engine_platform_v196_release_manifest.json"


def release_manifest(root: str | Path | None = None) -> dict[str, Any]:
    path = _release_manifest_path(root)
    if not path.is_file():
        return {"schema": "biointel.engine-platform.release.v1", "engines": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("engines"), dict):
        raise ValueError("Invalid engine release manifest.")
    return payload


def engine_platform_catalog(*, probe_runtime: bool = False, root: str | Path | None = None) -> pd.DataFrame:
    frame = audit_catalog(probe_runtime=probe_runtime).copy()
    frame["upstream_label"] = frame["label"]
    frame["public_engine_key"] = frame["engine"].map(public_engine_key)
    frame["label"] = frame["engine"].map(public_engine_name)
    pins = release_manifest(root).get("engines", {})
    frame["pack_key"] = frame["recommended_pack"].map(PACK_KEYS).fillna("specialist-extensions")
    frame["pinned_version"] = frame["engine"].map(lambda key: str(pins.get(key, {}).get("version", "")))
    frame["release_artifact_sha256"] = frame["engine"].map(lambda key: str(pins.get(key, {}).get("artifact_sha256", "")))
    frame["licence_file_sha256"] = frame["engine"].map(lambda key: str(pins.get(key, {}).get("licence_sha256", "")))
    frame["qualification_status"] = frame["engine"].map(lambda key: str(pins.get(key, {}).get("qualification_status", "unqualified")))
    frame["install_manifest_complete"] = frame.apply(
        lambda row: bool(row["pinned_version"] and row["release_artifact_sha256"] and row["licence_file_sha256"] and row["qualification_status"] == "qualified"),
        axis=1,
    )
    if len(frame) != len(ENGINE_REGISTRY) or frame["engine"].nunique() != len(ENGINE_REGISTRY):
        raise RuntimeError("Engine platform catalog must cover every registered engine exactly once.")
    return frame


def _bundled_windows_packages(root: str | Path | None = None) -> set[str]:
    base = Path(root).resolve() if root else project_root()
    wheelhouse = base / "wheelhouse" / "windows-cp311-x64"
    packages: set[str] = set()
    if not wheelhouse.is_dir():
        return packages
    for wheel in wheelhouse.glob("*.whl"):
        try:
            name, _version, _build, _tags = parse_wheel_filename(wheel.name)
        except ValueError:
            continue
        packages.add(canonicalize_name(name))
    return packages


def adapter_catalog(*, root: str | Path | None = None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    bundled = _bundled_windows_packages(root)
    selected = {item.format_key: item for item in FORMAT_CAPABILITIES if item.format_key in ADAPTER_INSTALLS}
    for key in ADAPTER_INSTALLS:
        capability = selected[key]
        install = ADAPTER_INSTALLS[key]
        dependency = capability.dependency
        dependency_available = bool(dependency and importlib.util.find_spec(dependency) is not None)
        external = capability.mode == "external_tool"
        required_packages = tuple(str(item) for item in install["packages"])
        bundled_packages = [item for item in required_packages if canonicalize_name(item) in bundled]
        missing_bundled_packages = [item for item in required_packages if canonicalize_name(item) not in bundled]
        rows.append(
            {
                "adapter": key,
                "category": capability.category,
                "extensions": ", ".join(capability.extensions),
                "mode": capability.mode,
                "dependency": dependency or "external executable",
                "packages": ", ".join(required_packages),
                "linked_engine": install["engine"],
                "available": dependency_available if not external else False,
                "offline_bundle_available": bool(required_packages) and not missing_bundled_packages,
                "bundled_packages": ", ".join(bundled_packages),
                "missing_bundled_packages": ", ".join(missing_bundled_packages),
                "qualification_required": True,
                "description": capability.description,
            }
        )
    frame = pd.DataFrame(rows).sort_values("adapter").reset_index(drop=True)
    if len(frame) != 12:
        raise RuntimeError(f"Expected 12 advanced adapters, found {len(frame)}.")
    return frame


def production_service_catalog() -> pd.DataFrame:
    rows = []
    for item in PRODUCTION_SERVICES:
        package = str(item["package"])
        rows.append({**item, "package_available": importlib.util.find_spec(package) is not None})
    return pd.DataFrame(rows)


def pack_catalog() -> pd.DataFrame:
    rows = []
    catalog = engine_platform_catalog()
    for label, key in PACK_KEYS.items():
        subset = catalog[catalog["pack_key"] == key]
        rows.append(
            {
                "pack_key": key,
                "label": label,
                "engine_count": int(len(subset)),
                "qualified_engine_count": int(subset["install_manifest_complete"].sum()),
                "p1_count": int((subset["priority_tier"] == "P1-compulsory").sum()),
                "p2_count": int((subset["priority_tier"] == "P2-high-value").sum()),
                "contains_model_weights": bool(subset["model_weights_required"].astype(bool).any()),
                "claim_boundary": "Pack is installable only after every included artifact, licence and smoke test is qualified.",
            }
        )
    return pd.DataFrame(rows)
