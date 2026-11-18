from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import io
import json
import math
import re
import shutil
import subprocess
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

try:
    from scipy import stats
except ImportError:
    stats = None

from biointel.neuro_cns.catalog import MODULES
from biointel.neuro_cns.hardening import stable_fingerprint
from biointel.neuro_cns.reporting import build_result_bundle, bundle_json, bundle_markdown, bundle_pdf


COMPLETION_FEATURES: tuple[tuple[int, str, str], ...] = (
    (1, "Scientific Resource Binding Studio", "scientific_resource_binding_studio"),
    (2, "Specialist Engine Qualification Center", "specialist_engine_qualification_center"),
    (3, "Privacy & De-identification Guard", "privacy_deidentification_guard"),
    (4, "Study Design & Power Planner", "study_design_power_planner"),
    (5, "Data Leakage & Cohort Split Auditor", "data_leakage_split_auditor"),
    (6, "Dataset Drift & Monitoring Center", "dataset_drift_monitor"),
    (7, "Multi-Site Reproducibility Analyzer", "multisite_reproducibility_analyzer"),
    (8, "Professional PDF Scientific Report", "professional_pdf_scientific_report"),
    (9, "Release Evidence Pack Builder", "release_evidence_pack_builder"),
)


@dataclass(frozen=True)
class ResourceBinding:
    resource_id: str
    provider: str
    release_version: str
    kind: str
    licence_status: str
    commercial_use_status: str
    schema_version: str
    validation_status: str
    file_name: str
    size_bytes: int
    sha256: str
    registered_at_utc: str
    release_eligible: bool
    notes: str = ""


_RESOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,79}$")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def profile_resource_bytes(data: bytes, *, file_name: str) -> dict[str, Any]:
    """Return a fail-closed local resource profile without contacting providers."""
    if not data:
        raise ValueError("Resource file is empty.")
    if len(data) > 2 * 1024 * 1024 * 1024:
        raise ValueError("Resource file exceeds the 2 GB binding limit.")
    suffix = Path(file_name).suffix.lower()
    profile: dict[str, Any] = {
        "file_name": Path(file_name).name,
        "suffix": suffix,
        "size_bytes": len(data),
        "sha256": _sha256_bytes(data),
        "format_status": "binary-unprofiled",
        "rows": None,
        "columns": None,
        "column_names": [],
    }
    if suffix in {".csv", ".tsv", ".txt"}:
        separator = "\t" if suffix in {".tsv", ".txt"} else ","
        try:
            frame = pd.read_csv(io.BytesIO(data), sep=separator, nrows=5_000)
        except Exception as exc:
            raise ValueError(f"Tabular resource could not be parsed: {exc}") from exc
        profile.update(
            {
                "format_status": "tabular-parsed",
                "rows_profiled": int(len(frame)),
                "columns": int(len(frame.columns)),
                "column_names": [str(column) for column in frame.columns[:200]],
                "duplicate_columns": bool(frame.columns.duplicated().any()),
                "missing_fraction_profiled": float(frame.isna().mean().mean()) if frame.size else 0.0,
            }
        )
    elif suffix == ".json":
        try:
            payload = json.loads(data.decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"JSON resource could not be parsed: {exc}") from exc
        profile.update(
            {
                "format_status": "json-parsed",
                "json_type": type(payload).__name__,
                "top_level_keys": sorted(map(str, payload.keys()))[:200] if isinstance(payload, dict) else [],
                "rows": len(payload) if isinstance(payload, list) else None,
            }
        )
    elif suffix in {".fasta", ".fa", ".faa"}:
        text = data.decode("utf-8", errors="replace")
        records = sum(1 for line in text.splitlines() if line.startswith(">"))
        profile.update({"format_status": "fasta-profiled", "records": records})
    elif suffix in {".vcf", ".vcf.gz"}:
        text = data[: min(len(data), 5_000_000)].decode("utf-8", errors="replace")
        variants = sum(1 for line in text.splitlines() if line and not line.startswith("#"))
        profile.update({"format_status": "vcf-profiled", "variant_rows_profiled": variants})
    return profile


def build_resource_binding(
    data: bytes,
    *,
    file_name: str,
    resource_id: str,
    provider: str,
    release_version: str,
    kind: str,
    licence_status: str,
    commercial_use_status: str,
    schema_version: str,
    validation_status: str,
    notes: str = "",
) -> dict[str, Any]:
    resource_id = str(resource_id).strip().lower()
    if not _RESOURCE_ID_RE.fullmatch(resource_id):
        raise ValueError("resource_id must use 2-80 lowercase letters, numbers, dots, underscores or hyphens.")
    required = {
        "provider": provider,
        "release_version": release_version,
        "kind": kind,
        "licence_status": licence_status,
        "commercial_use_status": commercial_use_status,
        "schema_version": schema_version,
        "validation_status": validation_status,
    }
    missing = [key for key, value in required.items() if not str(value or "").strip()]
    if missing:
        raise ValueError(f"Missing binding metadata: {', '.join(missing)}")
    profile = profile_resource_bytes(data, file_name=file_name)
    release_eligible = (
        str(licence_status).lower() in {"approved", "verified", "bundled-approved"}
        and str(commercial_use_status).lower() in {"allowed", "not-applicable", "approved"}
        and str(validation_status).lower() in {"qualified", "externally-validated", "schema-and-content-qualified"}
    )
    binding = ResourceBinding(
        resource_id=resource_id,
        provider=str(provider).strip(),
        release_version=str(release_version).strip(),
        kind=str(kind).strip(),
        licence_status=str(licence_status).strip(),
        commercial_use_status=str(commercial_use_status).strip(),
        schema_version=str(schema_version).strip(),
        validation_status=str(validation_status).strip(),
        file_name=Path(file_name).name,
        size_bytes=len(data),
        sha256=profile["sha256"],
        registered_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        release_eligible=release_eligible,
        notes=str(notes or "").strip(),
    )
    return {
        "binding": asdict(binding),
        "profile": profile,
        "binding_fingerprint_sha256": stable_fingerprint(asdict(binding)),
        "scientific_boundary": "A successful local binding verifies file identity and declared metadata; it does not independently verify provider claims, licence rights or biological validity.",
    }


def persist_resource_binding(
    binding_result: Mapping[str, Any],
    data: bytes,
    *,
    registry_directory: str | Path,
) -> dict[str, str]:
    binding = dict(binding_result.get("binding") or {})
    if not binding.get("resource_id") or not binding.get("sha256"):
        raise ValueError("A valid binding_result is required.")
    if _sha256_bytes(data) != binding["sha256"]:
        raise ValueError("Resource bytes do not match the binding SHA-256.")
    directory = Path(registry_directory)
    assets = directory / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(binding["file_name"]))[:140]
    asset_path = assets / f"{binding['resource_id']}__{safe_name}"
    asset_path.write_bytes(data)
    registry_path = directory / "resource_bindings.json"
    payload = {"schema": "biointel.neuro-cns.resource-bindings.v1", "bindings": []}
    if registry_path.exists():
        try:
            payload = json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {"schema": "biointel.neuro-cns.resource-bindings.v1", "bindings": []}
    rows = [row for row in payload.get("bindings", []) if row.get("resource_id") != binding["resource_id"]]
    binding["local_asset_path"] = str(asset_path)
    rows.append(binding)
    payload["bindings"] = sorted(rows, key=lambda row: str(row.get("resource_id")))
    temporary = registry_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(registry_path)
    return {"registry_path": str(registry_path), "asset_path": str(asset_path)}


ENGINE_SPECS: tuple[dict[str, Any], ...] = (
    {"engine": "HMMER", "executables": ["hmmsearch", "hmmscan"], "packages": [], "supports": "Ion channel/GPCR domain classification"},
    {"engine": "InterProScan", "executables": ["interproscan", "interproscan.sh"], "packages": [], "supports": "Protein domain evidence"},
    {"engine": "MNE-Python", "executables": [], "packages": ["mne"], "supports": "EDF/BDF/FIF neurophysiology"},
    {"engine": "NiBabel", "executables": [], "packages": ["nibabel"], "supports": "NIfTI imaging"},
    {"engine": "pydicom", "executables": [], "packages": ["pydicom"], "supports": "DICOM imaging"},
    {"engine": "SimpleITK", "executables": [], "packages": ["SimpleITK"], "supports": "Registration and image processing"},
    {"engine": "Ensembl VEP", "executables": ["vep"], "packages": [], "supports": "Variant annotation"},
    {"engine": "bcftools", "executables": ["bcftools"], "packages": [], "supports": "VCF normalization/query"},
    {"engine": "PLINK 2", "executables": ["plink2", "plink"], "packages": [], "supports": "Cohort genetics/QC"},
    {"engine": "FreeSurfer", "executables": ["recon-all"], "packages": [], "supports": "Cortical reconstruction"},
    {"engine": "FSL", "executables": ["fslmaths"], "packages": [], "supports": "Neuroimaging preprocessing"},
    {"engine": "ANTs", "executables": ["antsRegistration"], "packages": [], "supports": "Image registration"},
)


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _executable_version(path: str) -> str | None:
    for args in ([path, "--version"], [path, "-version"], [path, "-v"]):
        try:
            completed = subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)
        except Exception:
            continue
        text = (completed.stdout or completed.stderr or "").strip().splitlines()
        if text:
            return text[0][:240]
    return None


def specialist_engine_inventory(*, run_version_checks: bool = False) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for spec in ENGINE_SPECS:
        package_hits = []
        for package in spec["packages"]:
            version = _package_version(package)
            if version or importlib.util.find_spec(package) is not None:
                package_hits.append({"name": package, "version": version or "installed-version-unknown"})
        executable_hits = []
        for executable in spec["executables"]:
            path = shutil.which(executable)
            if path:
                executable_hits.append({"name": executable, "path": path, "version": _executable_version(path) if run_version_checks else None})
        installed = bool(package_hits or executable_hits)
        rows.append(
            {
                "engine": spec["engine"],
                "supports": spec["supports"],
                "installed": installed,
                "package_hits": package_hits,
                "executable_hits": executable_hits,
                "qualification_status": "installed-unqualified" if installed else "missing",
                "release_eligible": False,
            }
        )
    frame = pd.DataFrame(rows)
    return {
        "engines": frame,
        "installed_count": int(frame["installed"].sum()),
        "missing_count": int((~frame["installed"]).sum()),
        "scientific_boundary": "Detection is not qualification. Each installed engine still needs version locking, licensed references, golden/adverse fixtures and target-Windows verification.",
    }


_DIRECT_IDENTIFIER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("phone", re.compile(r"(?<!\d)(?:\+?\d[\d .()-]{7,}\d)(?!\d)")),
    ("ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("date", re.compile(r"\b(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}\b")),
    ("long_numeric_id", re.compile(r"\b\d{8,18}\b")),
)
_SENSITIVE_COLUMN_HINTS = {
    "name", "first_name", "last_name", "patient_name", "email", "phone", "mobile", "address",
    "street", "city", "postal", "zip", "dob", "birth_date", "date_of_birth", "mrn", "medical_record",
    "aadhaar", "passport", "pan", "ssn", "patient_id", "subject_name",
}


def privacy_scan_frame(frame: pd.DataFrame, *, sample_cells: int = 50_000) -> dict[str, Any]:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame.")
    rows: list[dict[str, Any]] = []
    lower_map = {str(column).strip().lower(): str(column) for column in frame.columns}
    for hint in sorted(_SENSITIVE_COLUMN_HINTS):
        if hint in lower_map:
            rows.append({"finding_type": "sensitive_column_name", "column": lower_map[hint], "count": int(frame[lower_map[hint]].notna().sum()), "severity": "high"})
    checked = 0
    for column in frame.columns:
        series = frame[column].dropna().astype(str)
        for value in series.head(max(1, sample_cells // max(1, len(frame.columns)))):
            checked += 1
            for finding_type, pattern in _DIRECT_IDENTIFIER_PATTERNS:
                if pattern.search(value):
                    rows.append({"finding_type": finding_type, "column": str(column), "count": 1, "severity": "high" if finding_type in {"email", "phone", "long_numeric_id"} else "medium"})
    findings = pd.DataFrame(rows)
    if not findings.empty:
        findings = findings.groupby(["finding_type", "column", "severity"], as_index=False)["count"].sum().sort_values(["severity", "count"], ascending=[True, False])
    else:
        findings = pd.DataFrame(columns=["finding_type", "column", "severity", "count"])
    high = int((findings["severity"] == "high").sum()) if not findings.empty else 0
    return {
        "findings": findings,
        "cells_sampled": checked,
        "high_finding_groups": high,
        "export_block_recommended": high > 0,
        "scientific_boundary": "Automated PHI/PII scanning reduces accidental disclosure risk but cannot prove de-identification or regulatory compliance.",
    }


def deidentify_frame(
    frame: pd.DataFrame,
    *,
    drop_columns: Sequence[str] | None = None,
    hash_columns: Sequence[str] | None = None,
    salt: str = "biointel-neuro-local",
    date_columns: Sequence[str] | None = None,
    date_shift_days: int = 0,
) -> pd.DataFrame:
    result = frame.copy()
    for column in drop_columns or []:
        if column in result:
            result = result.drop(columns=[column])
    for column in hash_columns or []:
        if column in result:
            result[column] = result[column].map(lambda value: hashlib.sha256(f"{salt}|{value}".encode("utf-8")).hexdigest()[:24] if pd.notna(value) else value)
    for column in date_columns or []:
        if column in result:
            parsed = pd.to_datetime(result[column], errors="coerce")
            result[column] = parsed + pd.to_timedelta(int(date_shift_days), unit="D")
    return result


def study_design_power_planner(
    *,
    design: str,
    effect_size: float,
    alpha: float = 0.05,
    power: float = 0.80,
    allocation_ratio: float = 1.0,
    dropout_fraction: float = 0.10,
    baseline_rate: float | None = None,
) -> dict[str, Any]:
    if not (0 < alpha < 1) or not (0 < power < 1):
        raise ValueError("alpha and power must be between 0 and 1.")
    if effect_size <= 0 or allocation_ratio <= 0 or not (0 <= dropout_fraction < 0.8):
        raise ValueError("effect_size/allocation_ratio must be positive and dropout_fraction must be below 0.8.")
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_power = stats.norm.ppf(power)
    design_key = str(design).strip().lower()
    if design_key in {"two_group_continuous", "continuous", "t_test"}:
        n_control = ((1 + 1 / allocation_ratio) * (z_alpha + z_power) ** 2) / (effect_size**2)
    elif design_key in {"paired_continuous", "paired"}:
        n_control = ((z_alpha + z_power) / effect_size) ** 2
        allocation_ratio = 1.0
    elif design_key in {"binary", "two_group_binary"}:
        if baseline_rate is None or not (0 < baseline_rate < 1):
            raise ValueError("baseline_rate between 0 and 1 is required for binary designs.")
        target_rate = min(max(baseline_rate + effect_size, 1e-6), 1 - 1e-6)
        pooled = (baseline_rate + target_rate) / 2
        numerator = (z_alpha * math.sqrt(2 * pooled * (1 - pooled)) + z_power * math.sqrt(baseline_rate * (1 - baseline_rate) + target_rate * (1 - target_rate))) ** 2
        n_control = numerator / ((target_rate - baseline_rate) ** 2)
    else:
        raise ValueError("Unsupported design. Use two_group_continuous, paired_continuous or binary.")
    n_control = int(math.ceil(n_control / (1 - dropout_fraction)))
    n_treatment = int(math.ceil(n_control * allocation_ratio))
    return {
        "design": design_key,
        "effect_size": effect_size,
        "alpha": alpha,
        "power": power,
        "dropout_fraction": dropout_fraction,
        "control_n": n_control,
        "treatment_n": n_treatment,
        "total_n": n_control + n_treatment if design_key != "paired_continuous" else n_control,
        "allocation_ratio": allocation_ratio,
        "scientific_boundary": "Analytic sample-size planning assumes the selected statistical model and effect-size definition are appropriate; protocol-specific simulation and statistician review remain required.",
    }


def leakage_split_audit(
    frame: pd.DataFrame,
    *,
    outcome_column: str,
    split_column: str | None = None,
    subject_id_column: str | None = None,
    group_columns: Sequence[str] | None = None,
    correlation_threshold: float = 0.98,
) -> dict[str, Any]:
    if outcome_column not in frame:
        raise ValueError("outcome_column does not exist.")
    findings: list[dict[str, Any]] = []
    if subject_id_column and subject_id_column in frame:
        duplicates = int(frame[subject_id_column].duplicated(keep=False).sum())
        if duplicates:
            findings.append({"rule": "DUPLICATE_SUBJECT_IDS", "severity": "high", "count": duplicates, "message": "Duplicate subject identifiers can leak repeated individuals across evaluation."})
        if split_column and split_column in frame:
            overlap = frame.groupby(subject_id_column)[split_column].nunique(dropna=True)
            crossing = int((overlap > 1).sum())
            if crossing:
                findings.append({"rule": "SUBJECT_SPLIT_OVERLAP", "severity": "critical", "count": crossing, "message": "Subjects appear in more than one data split."})
    if split_column and split_column in frame:
        split_counts = frame[split_column].value_counts(dropna=False)
        if len(split_counts) < 2:
            findings.append({"rule": "SINGLE_SPLIT", "severity": "critical", "count": int(len(frame)), "message": "Only one split is present; independent evaluation is unavailable."})
        for group_column in group_columns or []:
            if group_column in frame:
                crossing = frame.groupby(group_column)[split_column].nunique(dropna=True)
                count = int((crossing > 1).sum())
                if count:
                    findings.append({"rule": "GROUP_SPLIT_OVERLAP", "severity": "high", "count": count, "message": f"{group_column} groups cross split boundaries."})
    outcome = frame[outcome_column]
    numeric_outcome = pd.to_numeric(outcome, errors="coerce")
    if numeric_outcome.notna().sum() >= 10:
        numeric = frame.select_dtypes(include=[np.number]).drop(columns=[outcome_column], errors="ignore")
        correlations = numeric.apply(lambda series: abs(series.corr(numeric_outcome)))
        for feature, value in correlations.dropna().items():
            if value >= correlation_threshold:
                findings.append({"rule": "NEAR_PERFECT_OUTCOME_CORRELATION", "severity": "high", "count": 1, "feature": str(feature), "value": float(value), "message": "Feature is almost perfectly correlated with outcome and should be reviewed for target leakage."})
    outcome_token = outcome_column.lower()
    for column in frame.columns:
        token = str(column).lower()
        if column != outcome_column and (outcome_token in token or token in {"label", "target", "outcome_copy", "response_copy"}):
            findings.append({"rule": "OUTCOME_LIKE_COLUMN_NAME", "severity": "medium", "count": 1, "feature": str(column), "message": "Column name resembles the outcome and may encode downstream information."})
    findings_frame = pd.DataFrame(findings)
    critical = int((findings_frame.get("severity", pd.Series(dtype=str)) == "critical").sum()) if not findings_frame.empty else 0
    high = int((findings_frame.get("severity", pd.Series(dtype=str)) == "high").sum()) if not findings_frame.empty else 0
    return {
        "findings": findings_frame,
        "critical_findings": critical,
        "high_findings": high,
        "release_blocked": critical > 0,
        "scientific_boundary": "Automated leakage checks identify common failure modes but cannot replace protocol review, temporal reasoning and independent replication.",
    }


def _psi(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    quantiles = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
    if len(quantiles) < 3:
        return 0.0
    quantiles[0] = -np.inf
    quantiles[-1] = np.inf
    ref_counts = np.histogram(reference, bins=quantiles)[0].astype(float)
    cur_counts = np.histogram(current, bins=quantiles)[0].astype(float)
    ref_prop = np.clip(ref_counts / max(ref_counts.sum(), 1), 1e-6, None)
    cur_prop = np.clip(cur_counts / max(cur_counts.sum(), 1), 1e-6, None)
    return float(np.sum((cur_prop - ref_prop) * np.log(cur_prop / ref_prop)))


def dataset_drift_monitor(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    *,
    features: Sequence[str] | None = None,
    psi_warning: float = 0.10,
    psi_critical: float = 0.25,
) -> dict[str, Any]:
    selected = list(features or sorted(set(reference.columns) & set(current.columns)))
    rows: list[dict[str, Any]] = []
    for feature in selected:
        ref_num = pd.to_numeric(reference[feature], errors="coerce").dropna().to_numpy(float)
        cur_num = pd.to_numeric(current[feature], errors="coerce").dropna().to_numpy(float)
        if len(ref_num) >= 10 and len(cur_num) >= 10:
            ks = stats.ks_2samp(ref_num, cur_num)
            psi = _psi(ref_num, cur_num)
            severity = "critical" if psi >= psi_critical else "warning" if psi >= psi_warning else "stable"
            rows.append({"feature": feature, "type": "numeric", "reference_n": len(ref_num), "current_n": len(cur_num), "psi": psi, "ks_statistic": float(ks.statistic), "ks_pvalue": float(ks.pvalue), "mean_shift_sd": float((np.mean(cur_num) - np.mean(ref_num)) / (np.std(ref_num, ddof=1) or 1.0)), "severity": severity})
            continue
        ref_cat = reference[feature].astype(str).fillna("<NA>")
        cur_cat = current[feature].astype(str).fillna("<NA>")
        levels = sorted(set(ref_cat.unique()) | set(cur_cat.unique()))
        ref_prop = ref_cat.value_counts(normalize=True).reindex(levels, fill_value=0.0)
        cur_prop = cur_cat.value_counts(normalize=True).reindex(levels, fill_value=0.0)
        tvd = float(0.5 * np.abs(ref_prop - cur_prop).sum())
        severity = "critical" if tvd >= 0.30 else "warning" if tvd >= 0.15 else "stable"
        rows.append({"feature": feature, "type": "categorical", "reference_n": len(ref_cat), "current_n": len(cur_cat), "total_variation_distance": tvd, "new_levels": sorted(set(cur_cat.unique()) - set(ref_cat.unique()))[:50], "severity": severity})
    drift = pd.DataFrame(rows)
    return {
        "drift": drift,
        "critical_features": int((drift["severity"] == "critical").sum()) if not drift.empty else 0,
        "warning_features": int((drift["severity"] == "warning").sum()) if not drift.empty else 0,
        "monitoring_status": "action-required" if not drift.empty and (drift["severity"] == "critical").any() else "review" if not drift.empty and (drift["severity"] == "warning").any() else "stable",
        "scientific_boundary": "Distribution drift indicates changed inputs, not necessarily degraded biological or clinical performance. Outcome-linked monitoring remains required.",
    }


def multisite_reproducibility_analyzer(
    frame: pd.DataFrame,
    *,
    site_column: str,
    estimate_column: str,
    standard_error_column: str,
) -> dict[str, Any]:
    for column in (site_column, estimate_column, standard_error_column):
        if column not in frame:
            raise ValueError(f"Required column missing: {column}")
    work = frame[[site_column, estimate_column, standard_error_column]].copy()
    work[estimate_column] = pd.to_numeric(work[estimate_column], errors="coerce")
    work[standard_error_column] = pd.to_numeric(work[standard_error_column], errors="coerce")
    work = work.dropna()
    work = work[work[standard_error_column] > 0]
    if len(work) < 2:
        raise ValueError("At least two sites with positive standard errors are required.")
    y = work[estimate_column].to_numpy(float)
    se = work[standard_error_column].to_numpy(float)
    w = 1 / (se**2)
    fixed = float(np.sum(w * y) / np.sum(w))
    q = float(np.sum(w * (y - fixed) ** 2))
    df = len(y) - 1
    c = float(np.sum(w) - np.sum(w**2) / np.sum(w))
    tau2 = max(0.0, (q - df) / c) if c > 0 else 0.0
    wr = 1 / (se**2 + tau2)
    random_effect = float(np.sum(wr * y) / np.sum(wr))
    random_se = float(math.sqrt(1 / np.sum(wr)))
    i2 = max(0.0, (q - df) / q * 100) if q > 0 else 0.0
    work = work.rename(columns={site_column: "site", estimate_column: "estimate", standard_error_column: "standard_error"})
    work["ci95_low"] = work["estimate"] - 1.96 * work["standard_error"]
    work["ci95_high"] = work["estimate"] + 1.96 * work["standard_error"]
    return {
        "site_results": work,
        "site_count": int(len(work)),
        "fixed_effect": fixed,
        "random_effect": random_effect,
        "random_effect_ci95": [random_effect - 1.96 * random_se, random_effect + 1.96 * random_se],
        "tau_squared": tau2,
        "cochran_q": q,
        "i_squared_percent": i2,
        "heterogeneity_grade": "high" if i2 >= 75 else "moderate" if i2 >= 40 else "low",
        "scientific_boundary": "Meta-analytic reproducibility summaries require compatible estimands, independent sites and transparent inclusion criteria.",
    }


def professional_pdf_report(results: dict[str, Any], **metadata: Any) -> bytes:
    return bundle_pdf(results, **metadata)


def release_evidence_pack(
    results: dict[str, Any],
    *,
    project_name: str | None = None,
    analyst: str | None = None,
    notes: str | None = None,
    execution_history: list[dict[str, Any]] | None = None,
    error_records: list[dict[str, Any]] | None = None,
    resource_bindings: Iterable[Mapping[str, Any]] | None = None,
    engine_inventory: Mapping[str, Any] | None = None,
    privacy_findings: Mapping[str, Any] | None = None,
) -> bytes:
    metadata = {
        "project_name": project_name,
        "analyst": analyst,
        "notes": notes,
        "execution_history": execution_history or [],
        "error_records": error_records or [],
    }
    bundle = build_result_bundle(results, **metadata)
    files: dict[str, bytes] = {
        "report/neuro_report.json": bundle_json(results, **metadata).encode("utf-8"),
        "report/neuro_report.md": bundle_markdown(results, **metadata).encode("utf-8"),
        "report/neuro_report.pdf": bundle_pdf(results, **metadata),
        "evidence/resource_bindings.json": json.dumps(list(resource_bindings or []), indent=2, sort_keys=True, default=str).encode("utf-8"),
        "evidence/engine_inventory.json": json.dumps(engine_inventory or {}, indent=2, sort_keys=True, default=str).encode("utf-8"),
        "evidence/privacy_findings.json": json.dumps(privacy_findings or {}, indent=2, sort_keys=True, default=str).encode("utf-8"),
        "evidence/result_bundle_fingerprint.txt": stable_fingerprint(bundle).encode("utf-8"),
    }
    manifest_rows = []
    for path, content in sorted(files.items()):
        manifest_rows.append({"path": path, "size_bytes": len(content), "sha256": _sha256_bytes(content)})
    manifest = {
        "schema": "biointel.neuro-cns.release-evidence-pack.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "project_name": project_name,
        "base_modules": len(MODULES),
        "controlled_release_eligible": False,
        "files": manifest_rows,
        "scientific_boundary": "The evidence pack is an integrity-preserving review bundle, not a regulatory signature or clinical release authorization.",
    }
    files["MANIFEST.json"] = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, content in sorted(files.items()):
            archive.writestr(path, content)
    return buffer.getvalue()
