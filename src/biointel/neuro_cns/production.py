from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    import numpy as np
except ImportError:
    np = None

try:
    import pandas as pd
except ImportError:
    pd = None

from biointel.neuro_cns.catalog import MODULES
from biointel.neuro_cns.completion import specialist_engine_inventory
from biointel.neuro_cns.data import project_root
from biointel.neuro_cns.hardening import stable_fingerprint
from biointel.neuro_cns.reporting import bundle_json, bundle_markdown, bundle_pdf


PRODUCTION_FEATURES: tuple[tuple[int, str, str], ...] = (
    (1, "Official Data Pack Manager", "official_data_pack_manager"),
    (2, "Specialist Engine Installation & Qualification", "specialist_engine_installation_qualification"),
    (3, "External Benchmark Qualification Center", "external_benchmark_qualification_center"),
    (4, "One-Click Demo Showcase", "one_click_demo_showcase"),
    (5, "Signed Update & Rollback Center", "signed_update_rollback_center"),
    (6, "Enterprise Security & Role Access", "enterprise_security_role_access"),
    (7, "Multi-Reviewer Scientific Sign-off", "multi_reviewer_scientific_signoff"),
    (8, "Background Compute & Performance Qualification", "background_compute_performance"),
    (9, "Crash Diagnostics & Recovery Center", "crash_diagnostics_recovery"),
    (10, "Controlled Release & Publication Export", "controlled_release_publication_export"),
)


RESOURCE_PLAN: tuple[dict[str, Any], ...] = (
    {"resource_id": "bbb_reference", "provider_label": "BBB permeability reference", "modules": [1, 7, 12], "formats": ["csv", "tsv"], "minimum_fields": ["compound_id", "smiles", "bbb_label"], "licence_gate": True},
    {"resource_id": "cns_target_registry", "provider_label": "Protein/ontology CNS target registry", "modules": [2, 3, 6, 8, 11, 13, 18], "formats": ["csv", "json"], "minimum_fields": ["target_id", "gene", "category", "evidence"], "licence_gate": True},
    {"resource_id": "protein_domain_models", "provider_label": "Protein domain and family models", "modules": [4, 5], "formats": ["hmm", "tsv"], "minimum_fields": ["model_id", "family", "version"], "licence_gate": True},
    {"resource_id": "disease_target_evidence", "provider_label": "Neurological disease-target evidence", "modules": [6, 11, 17, 22, 23], "formats": ["csv", "json"], "minimum_fields": ["disease", "target_id", "evidence_type", "confidence"], "licence_gate": True},
    {"resource_id": "side_effect_evidence", "provider_label": "Drug-target-side-effect evidence", "modules": [8, 10, 14, 16], "formats": ["csv", "tsv"], "minimum_fields": ["drug_id", "target_id", "effect", "evidence"], "licence_gate": True},
    {"resource_id": "aggregation_benchmark", "provider_label": "Protein aggregation benchmark", "modules": [9], "formats": ["fasta", "csv"], "minimum_fields": ["sequence_id", "label"], "licence_gate": True},
    {"resource_id": "model_organism_orthologs", "provider_label": "Ortholog and phenotype reference", "modules": [13, 17], "formats": ["csv", "json"], "minimum_fields": ["human_target", "organism", "ortholog", "phenotype"], "licence_gate": True},
    {"resource_id": "adme_transporter_reference", "provider_label": "ADME/transporter benchmark", "modules": [14, 15, 16], "formats": ["csv", "sdf"], "minimum_fields": ["compound_id", "endpoint", "value", "unit"], "licence_gate": True},
    {"resource_id": "variant_annotation_reference", "provider_label": "Variant annotation and frequency reference", "modules": [17], "formats": ["vcf", "tsv"], "minimum_fields": ["chrom", "pos", "ref", "alt"], "licence_gate": True},
    {"resource_id": "brain_expression_atlas", "provider_label": "Bulk/single-cell/spatial brain expression atlas", "modules": [18, 19, 23], "formats": ["h5ad", "csv", "tsv"], "minimum_fields": ["gene", "region", "cell_type", "expression"], "licence_gate": True},
    {"resource_id": "neurophysiology_benchmark", "provider_label": "EEG/MEG benchmark recordings", "modules": [20], "formats": ["edf", "bdf", "fif", "csv"], "minimum_fields": ["recording_id", "sampling_rate"], "licence_gate": True},
    {"resource_id": "neuroimaging_benchmark", "provider_label": "Neuroimaging benchmark and atlas", "modules": [21, 23], "formats": ["nii", "nii.gz", "dcm", "csv"], "minimum_fields": ["scan_id", "modality"], "licence_gate": True},
    {"resource_id": "clinical_trial_evidence", "provider_label": "Current clinical trial evidence", "modules": [22], "formats": ["csv", "json"], "minimum_fields": ["trial_id", "phase", "status", "indication"], "licence_gate": True},
    {"resource_id": "precision_cohort_reference", "provider_label": "De-identified external cohort", "modules": [19, 21, 23], "formats": ["csv", "parquet"], "minimum_fields": ["subject_id", "site"], "licence_gate": True},
    {"resource_id": "neurovascular_cohort", "provider_label": "De-identified neurovascular cohort", "modules": [24], "formats": ["csv", "parquet"], "minimum_fields": ["subject_id", "age", "systolic_bp", "diastolic_bp"], "licence_gate": True},
    {"resource_id": "sleep_circadian_benchmark", "provider_label": "Actigraphy/circadian benchmark", "modules": [25], "formats": ["csv", "edf"], "minimum_fields": ["timestamp", "activity"], "licence_gate": True},
    {"resource_id": "fluid_biomarker_reference", "provider_label": "Qualified CSF/blood biomarker cohort", "modules": [26], "formats": ["csv", "parquet"], "minimum_fields": ["subject_id", "group", "biomarker"], "licence_gate": True},
    {"resource_id": "digital_neurology_reference", "provider_label": "Wearable/digital neurology benchmark", "modules": [27, 30], "formats": ["csv", "parquet"], "minimum_fields": ["subject_id", "timestamp"], "licence_gate": True},
    {"resource_id": "neuroimmune_reference", "provider_label": "Neuroimmune cell-state/pathway evidence", "modules": [28], "formats": ["csv", "h5ad"], "minimum_fields": ["cell_type", "condition", "feature"], "licence_gate": True},
    {"resource_id": "longitudinal_cognition_reference", "provider_label": "Longitudinal cognitive cohort", "modules": [29, 33], "formats": ["csv", "parquet"], "minimum_fields": ["subject_id", "time", "score"], "licence_gate": True},
    {"resource_id": "cns_medication_reference", "provider_label": "CNS medication/interaction evidence", "modules": [31], "formats": ["csv", "json"], "minimum_fields": ["medication", "target_or_class", "evidence"], "licence_gate": True},
    {"resource_id": "connectome_resilience_benchmark", "provider_label": "Connectome resilience benchmark", "modules": [32], "formats": ["csv", "npy", "graphml"], "minimum_fields": ["region", "connectivity"], "licence_gate": True},
    {"resource_id": "neuro_oncology_molecular_reference", "provider_label": "Neuro-oncology molecular/imaging research reference", "modules": [34, 40], "formats": ["csv", "vcf", "nii", "ome.tiff"], "minimum_fields": ["subject_id", "molecular_group", "source_version"], "licence_gate": True},
    {"resource_id": "epilepsy_event_diary_reference", "provider_label": "De-identified epilepsy event/diary research benchmark", "modules": [35], "formats": ["csv", "edf", "bdf", "fif"], "minimum_fields": ["subject_id", "timestamp", "event_type"], "licence_gate": True},
    {"resource_id": "movement_sensor_reference", "provider_label": "Movement-disorder wearable sensor benchmark", "modules": [36], "formats": ["csv", "parquet"], "minimum_fields": ["subject_id", "timestamp", "axis_or_magnitude"], "licence_gate": True},
    {"resource_id": "autonomic_hrv_reference", "provider_label": "Autonomic neurophysiology/HRV research benchmark", "modules": [37], "formats": ["csv", "edf"], "minimum_fields": ["subject_id", "timestamp", "rr_interval_ms"], "licence_gate": True},
    {"resource_id": "speech_language_reference", "provider_label": "De-identified speech, voice and language research benchmark", "modules": [38], "formats": ["csv", "wav", "json"], "minimum_fields": ["subject_id", "feature", "value"], "licence_gate": True},
    {"resource_id": "multimodal_neurodegeneration_reference", "provider_label": "Longitudinal multimodal neurodegeneration cohort", "modules": [39], "formats": ["csv", "parquet", "nii", "vcf"], "minimum_fields": ["subject_id", "time", "modality"], "licence_gate": True},
    {"resource_id": "neurocritical_care_reference", "provider_label": "De-identified neurocritical-care trend research benchmark", "modules": [41], "formats": ["csv", "parquet"], "minimum_fields": ["subject_id", "timestamp", "measurement"], "licence_gate": True},
)


ENGINE_INSTALL_PLAN: tuple[dict[str, Any], ...] = (
    {"engine": "HMMER", "install_kind": "external executable", "module_support": [4, 5], "windows_strategy": "WSL or verified native build", "automatic_install": False},
    {"engine": "InterProScan", "install_kind": "external executable + reference data", "module_support": [4, 5], "windows_strategy": "WSL/container recommended", "automatic_install": False},
    {"engine": "MNE-Python", "install_kind": "Python package", "module_support": [20], "windows_strategy": "offline wheel or approved online install", "automatic_install": True},
    {"engine": "NiBabel", "install_kind": "Python package", "module_support": [21], "windows_strategy": "offline wheel or approved online install", "automatic_install": True},
    {"engine": "pydicom", "install_kind": "Python package", "module_support": [21], "windows_strategy": "offline wheel or approved online install", "automatic_install": True},
    {"engine": "SimpleITK", "install_kind": "Python package", "module_support": [21], "windows_strategy": "qualified wheel", "automatic_install": True},
    {"engine": "Ensembl VEP", "install_kind": "external executable + cache", "module_support": [17], "windows_strategy": "WSL/container recommended", "automatic_install": False},
    {"engine": "bcftools", "install_kind": "external executable", "module_support": [17], "windows_strategy": "WSL or verified native build", "automatic_install": False},
    {"engine": "PLINK 2", "install_kind": "external executable", "module_support": [17, 23], "windows_strategy": "verified native executable", "automatic_install": False},
    {"engine": "ANTs/FSL/FreeSurfer", "install_kind": "specialist imaging suite", "module_support": [21], "windows_strategy": "WSL/container; licence and hardware review", "automatic_install": False},
)


ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "viewer": ("view_results", "download_demo"),
    "researcher": ("view_results", "run_modules", "save_project", "download_demo", "export_research_report"),
    "reviewer": ("view_results", "run_modules", "save_project", "download_demo", "export_research_report", "review_results", "request_changes"),
    "release_manager": ("view_results", "review_results", "request_changes", "approve_release", "export_release_pack", "bind_resources"),
    "administrator": ("view_results", "run_modules", "save_project", "download_demo", "export_research_report", "review_results", "request_changes", "approve_release", "export_release_pack", "bind_resources", "manage_users", "manage_updates", "manage_engines"),
}


@dataclass(frozen=True)
class ReviewRecord:
    reviewer: str
    role: str
    decision: str
    module_keys: tuple[str, ...]
    comments: str
    evidence_fingerprint_sha256: str
    reviewed_at_utc: str


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def demo_pack_directory(root: Path | None = None) -> Path:
    return (root or project_root()) / "data" / "neuro_cns" / "demo_packs" / "step202"


def verify_demo_pack(root: Path | None = None) -> dict[str, Any]:
    directory = demo_pack_directory(root)
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        return {"passed": False, "directory": str(directory), "files": pd.DataFrame(), "errors": ["manifest.json is missing"], "dataset_count": 0, "scientific_boundary": "All Step202 demo records are synthetic or illustrative and must never be treated as patient, clinical, or externally validated evidence."}
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for entry in payload.get("files", []):
        relative = str(entry.get("path", ""))
        path = directory / relative
        exists = path.is_file()
        size = path.stat().st_size if exists else -1
        actual_hash = _hash_file(path) if exists else ""
        passed = exists and size == int(entry.get("size_bytes", -2)) and actual_hash == str(entry.get("sha256", ""))
        if not passed:
            errors.append(relative or "<invalid manifest row>")
        rows.append({"path": relative, "exists": exists, "size_bytes": size, "sha256": actual_hash, "passed": passed, "purpose": entry.get("purpose", "")})
    return {
        "passed": not errors and bool(rows),
        "directory": str(directory),
        "manifest_schema": payload.get("schema"),
        "dataset_count": len(rows),
        "files": pd.DataFrame(rows),
        "errors": errors,
        "scientific_boundary": "All Step202 demo records are synthetic or illustrative and must never be treated as patient, clinical, or externally validated evidence.",
    }


def load_demo_asset(name: str, root: Path | None = None) -> Any:
    directory = demo_pack_directory(root)
    safe = Path(name).name
    path = directory / safe
    if not path.is_file():
        raise FileNotFoundError(f"Demo asset not found: {safe}")
    lower = safe.lower()
    if lower.endswith(".csv"):
        return pd.read_csv(path)
    if lower.endswith((".tsv", ".txt")):
        return pd.read_csv(path, sep="\t")
    if lower.endswith(".json"):
        return json.loads(path.read_text(encoding="utf-8"))
    if lower.endswith(".npy"):
        return np.load(path, allow_pickle=False)
    return path.read_text(encoding="utf-8", errors="replace")


def demo_pack_zip(root: Path | None = None) -> bytes:
    directory = demo_pack_directory(root)
    status = verify_demo_pack(root)
    if not status["passed"]:
        raise RuntimeError(f"Demo pack verification failed: {status['errors']}")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                archive.write(path, f"BioIntel-Neuro-Step202-Demo/{path.relative_to(directory).as_posix()}")
    return buffer.getvalue()


def official_resource_plan() -> dict[str, Any]:
    frame = pd.DataFrame(RESOURCE_PLAN)
    covered = sorted({module for row in RESOURCE_PLAN for module in row["modules"]})
    return {
        "resources": frame,
        "resource_count": len(frame),
        "covered_modules": covered,
        "all_modules_covered": covered == [module.number for module in MODULES],
        "release_eligible": False,
        "scientific_boundary": "This is a binding plan only. BioIntel does not claim official data are bundled, licensed, current, or validated until the user binds and qualifies them.",
    }


def specialist_engine_installation_plan(*, run_version_checks: bool = False) -> dict[str, Any]:
    inventory = specialist_engine_inventory(run_version_checks=run_version_checks)["engines"]
    plan = pd.DataFrame(ENGINE_INSTALL_PLAN)
    merged = plan.merge(inventory[["engine", "installed", "qualification_status"]], on="engine", how="left")
    merged["installed"] = merged["installed"].where(merged["installed"].notna(), False).astype(bool)
    merged["qualification_status"] = merged["qualification_status"].fillna("not-detected")
    merged["next_action"] = np.where(merged["installed"], "Run golden/adverse fixtures and lock version", np.where(merged["automatic_install"], "Install approved Python package", "Follow governed external-engine installation guide"))
    return {
        "plan": merged,
        "installed_count": int(merged["installed"].sum()),
        "pending_count": int((~merged["installed"]).sum()),
        "automatic_install_candidates": int(merged["automatic_install"].sum()),
        "release_eligible": False,
        "scientific_boundary": "Installation is not qualification. External executables, references, licences, versions, hardware and golden/adverse cases must all pass before release use.",
    }


def validate_benchmark_registry(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    records = []
    valid_modules = {module.key for module in MODULES}
    for index, row in enumerate(rows, 1):
        module_key = str(row.get("module_key", "")).strip()
        positives = int(row.get("positive_cases", 0) or 0)
        negatives = int(row.get("negative_cases", 0) or 0)
        external_sites = int(row.get("external_sites", 0) or 0)
        calibration = bool(row.get("calibration_passed", False))
        leakage = bool(row.get("leakage_audit_passed", False))
        errors = []
        if module_key not in valid_modules:
            errors.append("unknown module_key")
        if positives < 5:
            errors.append("fewer than 5 positive cases")
        if negatives < 5:
            errors.append("fewer than 5 negative cases")
        if external_sites < 1:
            errors.append("no independent external site")
        if not calibration:
            errors.append("calibration not passed")
        if not leakage:
            errors.append("leakage audit not passed")
        qualified = not errors
        records.append({"row": index, "module_key": module_key, "positive_cases": positives, "negative_cases": negatives, "external_sites": external_sites, "calibration_passed": calibration, "leakage_audit_passed": leakage, "qualified": qualified, "gaps": "; ".join(errors)})
    frame = pd.DataFrame(records)
    qualified = int(frame["qualified"].sum()) if not frame.empty else 0
    return {
        "benchmarks": frame,
        "qualified_modules": qualified,
        "submitted_modules": int(frame["module_key"].nunique()) if not frame.empty else 0,
        "coverage_fraction": qualified / float(max(len(MODULES), 1)),
        "controlled_release_eligible": qualified == len(MODULES),
        "scientific_boundary": "This registry checks minimum evidence fields, not the biological validity or independence of submitted benchmark cases.",
    }


def role_access_matrix() -> pd.DataFrame:
    actions = sorted({action for actions in ROLE_PERMISSIONS.values() for action in actions})
    return pd.DataFrame([{"role": role, **{action: action in permissions for action in actions}} for role, permissions in ROLE_PERMISSIONS.items()])


def authorize_action(role: str, action: str) -> dict[str, Any]:
    role_key = str(role).strip().lower()
    action_key = str(action).strip()
    allowed = action_key in ROLE_PERMISSIONS.get(role_key, ())
    return {"role": role_key, "action": action_key, "allowed": allowed, "reason": "permission granted" if allowed else "role does not include this permission"}


def create_review_record(*, reviewer: str, role: str, decision: str, module_keys: Sequence[str], comments: str, evidence: Mapping[str, Any]) -> dict[str, Any]:
    if not str(reviewer).strip():
        raise ValueError("reviewer is required")
    role_key = str(role).strip().lower()
    decision_key = str(decision).strip().lower()
    if role_key not in {"reviewer", "release_manager", "administrator"}:
        raise ValueError("role is not permitted to create scientific review records")
    if decision_key not in {"approve", "reject", "request_changes", "acknowledge_exploratory"}:
        raise ValueError("unsupported review decision")
    valid = {module.key for module in MODULES}
    unknown = sorted(set(module_keys) - valid)
    if unknown:
        raise ValueError(f"unknown module keys: {unknown}")
    record = ReviewRecord(
        reviewer=str(reviewer).strip(),
        role=role_key,
        decision=decision_key,
        module_keys=tuple(sorted(set(module_keys))),
        comments=str(comments or "").strip(),
        evidence_fingerprint_sha256=stable_fingerprint(evidence),
        reviewed_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    return {"record": asdict(record), "record_fingerprint_sha256": stable_fingerprint(asdict(record)), "electronic_signature_status": "local-audit-record-not-cryptographic-signature"}


def compute_qualification_profile(*, rows: int, columns: int, byte_size: int, workload: str, available_ram_gb: float | None = None, cpu_count: int | None = None, gpu_available: bool = False) -> dict[str, Any]:
    rows = max(0, int(rows)); columns = max(0, int(columns)); byte_size = max(0, int(byte_size))
    available_ram_gb = float(available_ram_gb if available_ram_gb is not None else 8.0)
    cpu_count = int(cpu_count if cpu_count is not None else (os.cpu_count() or 2))
    cell_count = rows * columns
    heavy = byte_size >= 20 * 1024 * 1024 or cell_count >= 5_000_000 or workload in {"neuroimaging", "neurophysiology", "multiomics", "variant_annotation"}
    estimated_memory_gb = max(byte_size * 4 / 1024**3, cell_count * 16 / 1024**3, 0.1)
    insufficient = estimated_memory_gb > max(available_ram_gb * 0.65, 0.5)
    mode = "blocked-insufficient-memory" if insufficient else "background" if heavy else "interactive"
    worker_limit = max(1, min(4, cpu_count // 2 or 1))
    if available_ram_gb < 8:
        worker_limit = 1
    return {
        "workload": workload,
        "recommended_mode": mode,
        "estimated_peak_memory_gb": round(estimated_memory_gb, 3),
        "available_ram_gb": available_ram_gb,
        "recommended_worker_limit": worker_limit,
        "gpu_available": bool(gpu_available),
        "streaming_recommended": byte_size >= 100 * 1024 * 1024,
        "checkpointing_recommended": heavy,
        "reason": "estimated memory exceeds safe fraction" if insufficient else "large/specialist workload" if heavy else "within interactive guardrails",
    }


def create_update_snapshot(root: Path, *, include_paths: Sequence[str], label: str = "pre-update") -> bytes:
    root = Path(root).resolve()
    safe_label = re.sub(r"[^A-Za-z0-9._-]+", "_", label)[:80] or "snapshot"
    manifest_rows = []
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for relative in sorted(set(include_paths)):
            path = (root / relative).resolve()
            try:
                path.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"Snapshot path escapes project root: {relative}") from exc
            if not path.is_file():
                continue
            data = path.read_bytes()
            archive.writestr(f"snapshot/{relative.replace(os.sep, '/')}", data)
            manifest_rows.append({"path": relative.replace(os.sep, "/"), "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        manifest = {"schema": "biointel.neuro.step202.snapshot.v1", "label": safe_label, "created_at_utc": datetime.now(UTC).isoformat(timespec="seconds"), "files": manifest_rows}
        archive.writestr("SNAPSHOT_MANIFEST.json", json.dumps(manifest, indent=2, sort_keys=True))
    return buffer.getvalue()


def crash_diagnostics_bundle(root: Path, *, error_message: str = "", log_paths: Sequence[Path] = ()) -> bytes:
    root = Path(root).resolve()
    diagnostics = {
        "schema": "biointel.neuro.step202.diagnostics.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "python": sys.version,
        "python_executable_name": Path(sys.executable).name,
        "project_root_name": root.name,
        "error_message": str(error_message)[:2000],
        "demo_pack": {key: value for key, value in verify_demo_pack(root).items() if key not in {"files"}},
        "engine_inventory": specialist_engine_inventory(run_version_checks=False)["engines"].to_dict(orient="records"),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("diagnostics.json", json.dumps(diagnostics, indent=2, default=str))
        for path in log_paths[:30]:
            path = Path(path)
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")[-200_000:]
            text = re.sub(r"[A-Za-z]:\\Users\\[^\\\s]+", r"C:\\Users\\<redacted>", text, flags=re.I)
            text = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "<redacted-email>", text, flags=re.I)
            archive.writestr(f"logs/{path.name}", text)
    return buffer.getvalue()


def controlled_release_status(*, results: Mapping[str, Any], resource_bindings: Sequence[Mapping[str, Any]] = (), engine_rows: Sequence[Mapping[str, Any]] = (), benchmark_rows: Sequence[Mapping[str, Any]] = (), review_records: Sequence[Mapping[str, Any]] = (), test_failures: int = 0, native_windows_qualified: bool = False) -> dict[str, Any]:
    executed = sorted(set(results) & {module.key for module in MODULES})
    eligible_resources = {str(row.get("resource_id")) for row in resource_bindings if bool(row.get("release_eligible"))}
    qualified_engines = {str(row.get("engine")) for row in engine_rows if str(row.get("qualification_status", "")).lower() in {"qualified", "externally-qualified"}}
    qualified_benchmarks = {str(row.get("module_key")) for row in benchmark_rows if bool(row.get("qualified"))}
    approved_modules: set[str] = set()
    for row in review_records:
        record = row.get("record", row)
        if str(record.get("decision", "")).lower() == "approve":
            approved_modules.update(map(str, record.get("module_keys", [])))
    gates = {
        "software_tests": int(test_failures) == 0,
        "native_windows": bool(native_windows_qualified),
        "resource_bindings": len(eligible_resources) >= 8,
        "specialist_engines": len(qualified_engines) >= 4,
        "external_benchmarks": set(executed) <= qualified_benchmarks if executed else False,
        "scientific_review": set(executed) <= approved_modules if executed else False,
        "results_present": bool(executed),
    }
    eligible = all(gates.values())
    tier = "Controlled Scientific Release" if eligible else "Research Qualified" if gates["software_tests"] and gates["results_present"] and len(qualified_benchmarks) >= max(1, len(executed) // 2) else "Exploratory Research" if results else "Demo"
    return {
        "release_tier": tier,
        "controlled_release_eligible": eligible,
        "gates": gates,
        "executed_modules": executed,
        "eligible_resource_count": len(eligible_resources),
        "qualified_engine_count": len(qualified_engines),
        "qualified_benchmark_count": len(qualified_benchmarks),
        "approved_module_count": len(approved_modules),
        "boundary": "Clinical use remains out of scope even when controlled scientific release gates pass; clinical validation and regulatory qualification are separate.",
    }


def publication_export_pack(results: Mapping[str, Any], *, project_name: str, methods: str = "", limitations: str = "", citations: Sequence[str] = (), release_status: Mapping[str, Any] | None = None) -> bytes:
    status = dict(release_status or controlled_release_status(results=results))
    metadata = {"project_name": project_name, "methods": methods, "limitations": limitations, "citations": list(citations), "release_status": status}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("report/results.json", bundle_json(results, project_name=project_name))
        archive.writestr("report/results.md", bundle_markdown(results, project_name=project_name))
        archive.writestr("report/results.pdf", bundle_pdf(results, project_name=project_name))
        archive.writestr("publication/METHODS.md", f"# Methods\n\n{methods or 'Methods must be completed and reviewed before submission.'}\n")
        archive.writestr("publication/LIMITATIONS.md", f"# Limitations\n\n{limitations or 'Exploratory software outputs; independent validation required.'}\n")
        archive.writestr("publication/CITATIONS.json", json.dumps(list(citations), indent=2))
        archive.writestr("publication/RELEASE_STATUS.json", json.dumps(status, indent=2, default=str))
        archive.writestr("publication/METADATA.json", json.dumps(metadata, indent=2, default=str))
    return buffer.getvalue()
