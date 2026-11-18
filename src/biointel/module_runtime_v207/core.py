from __future__ import annotations

import hashlib
import io
import json
import math
import re
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

TARGET_CATEGORIES = frozenset({"Bioinformatics", "Discovery", "Lab Analytics", "Neuro/CNS"})
PROTECTED_PAGE_PATHS = frozenset(
    {
        "pages/6_DTI_Predictor.py",
        "pages/74_DTI_Validation_Evidence_Center.py",
        "pages/109_Lab_Instrument_Import_Center.py",
        "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py",
        "pages/157_Instrument_Integration_Hub_2.py",
    }
)
_SECRET_KEY = re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization|cookie|bearer)")
_DIRECT_IDENTIFIER = re.compile(
    r"(?i)^(name|full_name|patient_name|email|phone|mobile|address|street|aadhaar|aadhar|passport|mrn|medical_record|dob|date_of_birth)$"
)


@dataclass(frozen=True)
class ModuleQualityProfile:
    page_key: str
    title: str
    category: str
    page_path: str
    source_sha256: str
    source_size_bytes: int
    has_upload: bool
    has_upload_preflight: bool
    has_scientific_boundary: bool
    has_visual_output: bool
    has_download_export: bool
    has_workflow_status: bool
    has_background_execution: bool
    source_import_count: int
    quality_score: float
    findings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def profile_module_source(
    project_root: str | Path,
    *,
    page_key: str,
    title: str,
    category: str,
    page_path: str,
) -> ModuleQualityProfile:
    root = Path(project_root).resolve()
    path = (root / page_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("Page path escapes the project root.") from exc
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    has_upload = "file_uploader(" in text
    has_preflight = (
        "render_upload_preflight(" in text
        or "render_upload_collection_preflight(" in text
        or "profile_streamlit_upload(" in text
    )
    has_boundary = (
        "scientific_boundary_banner(" in text
        or "scientific_boundary" in text
        or "research-only" in text.lower()
        or "research only" in text.lower()
    )
    has_visual = any(
        marker in text
        for marker in (
            "plotly_chart(",
            "px.",
            "go.Figure",
            "st.image(",
            "render_peak_visual_suite",
            "canvas",
        )
    )
    has_export = any(
        marker in text
        for marker in (
            "download_button(",
            "build_summary_pdf",
            "export_",
            "report",
        )
    )
    has_status = any(
        marker in text
        for marker in (
            "workflow_status(",
            "st.status(",
            "st.spinner(",
            "safe_execute(",
        )
    )
    has_background = any(
        marker in text
        for marker in (
            "LocalJobQueue",
            "submit_job",
            "background",
            "stage_large_streamlit_upload",
        )
    )
    import_count = sum(
        1
        for line in text.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    )
    findings: list[str] = []
    passed = 0
    checks = 6
    if not has_upload or has_preflight:
        passed += 1
    else:
        findings.append("Upload control exists without an explicit preflight marker.")
    if has_boundary:
        passed += 1
    else:
        findings.append("Scientific-use boundary is not explicit in the page source.")
    if has_visual:
        passed += 1
    else:
        findings.append("No calculated scientific visual marker was detected.")
    if has_export:
        passed += 1
    else:
        findings.append("No result export/report marker was detected.")
    if has_status:
        passed += 1
    else:
        findings.append("Long-running work has no explicit progress/safe-execution marker.")
    if has_background or not has_upload:
        passed += 1
    elif has_upload:
        findings.append("Large work may need background execution or staged ingestion.")
    score = round(10.0 * passed / checks, 2)
    return ModuleQualityProfile(
        page_key=str(page_key),
        title=str(title),
        category=str(category),
        page_path=str(page_path),
        source_sha256=_sha256_bytes(raw),
        source_size_bytes=len(raw),
        has_upload=has_upload,
        has_upload_preflight=has_preflight,
        has_scientific_boundary=has_boundary,
        has_visual_output=has_visual,
        has_download_export=has_export,
        has_workflow_status=has_status,
        has_background_execution=has_background,
        source_import_count=import_count,
        quality_score=score,
        findings=tuple(findings),
    )


def _safe_numeric(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.select_dtypes(include=[np.number]).copy()
    for column in output.columns:
        output[column] = pd.to_numeric(output[column], errors="coerce")
    return output


def _iqr_outlier_fraction(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < 8:
        return 0.0
    q1, q3 = values.quantile([0.25, 0.75])
    iqr = float(q3 - q1)
    if not math.isfinite(iqr) or iqr <= 0:
        return 0.0
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return float(((values < lower) | (values > upper)).mean())


def _cramers_v(left: pd.Series, right: pd.Series) -> float | None:
    table = pd.crosstab(left.astype(str), right.astype(str))
    if table.empty or min(table.shape) < 2:
        return None
    observed = table.to_numpy(dtype=float)
    total = observed.sum()
    if total <= 0:
        return None
    expected = np.outer(observed.sum(axis=1), observed.sum(axis=0)) / total
    mask = expected > 0
    chi2 = float(np.sum(((observed - expected) ** 2)[mask] / expected[mask]))
    phi2 = chi2 / total
    rows, cols = observed.shape
    correction = ((cols - 1) * (rows - 1)) / max(total - 1, 1)
    phi2_corrected = max(0.0, phi2 - correction)
    rows_corrected = rows - ((rows - 1) ** 2) / max(total - 1, 1)
    cols_corrected = cols - ((cols - 1) ** 2) / max(total - 1, 1)
    denominator = max(min(cols_corrected - 1, rows_corrected - 1), 1e-12)
    return float(min(1.0, math.sqrt(phi2_corrected / denominator)))


def _detect_column(columns: Iterable[str], names: Iterable[str]) -> str | None:
    normalized = {re.sub(r"[^a-z0-9]+", "_", str(column).lower()).strip("_"): str(column) for column in columns}
    for name in names:
        key = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        if key in normalized:
            return normalized[key]
    return None


def _base_dataset_audit(frame: pd.DataFrame) -> dict[str, Any]:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Dataset must be a pandas DataFrame.")
    if frame.empty:
        raise ValueError("Dataset is empty.")
    if frame.shape[1] == 0:
        raise ValueError("Dataset has no columns.")
    memory_bytes = int(frame.memory_usage(index=True, deep=True).sum())
    missing = pd.DataFrame(
        {
            "column": frame.columns.astype(str),
            "missing_count": [int(frame[column].isna().sum()) for column in frame.columns],
            "missing_fraction": [float(frame[column].isna().mean()) for column in frame.columns],
            "dtype": [str(frame[column].dtype) for column in frame.columns],
            "unique_values": [int(frame[column].nunique(dropna=True)) for column in frame.columns],
        }
    ).sort_values(["missing_fraction", "column"], ascending=[False, True])
    numeric = _safe_numeric(frame)
    numeric_quality = pd.DataFrame(
        [
            {
                "column": column,
                "finite_fraction": float(np.isfinite(numeric[column].to_numpy(dtype=float, na_value=np.nan)).mean()),
                "outlier_fraction_iqr": _iqr_outlier_fraction(numeric[column]),
                "mean": float(numeric[column].mean()) if numeric[column].notna().any() else np.nan,
                "standard_deviation": float(numeric[column].std(ddof=1)) if numeric[column].notna().sum() > 1 else np.nan,
                "minimum": float(numeric[column].min()) if numeric[column].notna().any() else np.nan,
                "maximum": float(numeric[column].max()) if numeric[column].notna().any() else np.nan,
            }
            for column in numeric.columns
        ]
    )
    constant_columns = [str(column) for column in frame.columns if frame[column].nunique(dropna=True) <= 1]
    duplicate_rows = int(frame.duplicated().sum())
    direct_identifiers = [str(column) for column in frame.columns if _DIRECT_IDENTIFIER.match(str(column).strip())]
    return {
        "rows": int(frame.shape[0]),
        "columns": int(frame.shape[1]),
        "memory_bytes": memory_bytes,
        "memory_mb": round(memory_bytes / (1024**2), 3),
        "duplicate_rows": duplicate_rows,
        "duplicate_fraction": float(duplicate_rows / max(len(frame), 1)),
        "constant_columns": constant_columns,
        "direct_identifier_columns": direct_identifiers,
        "missingness": missing.reset_index(drop=True),
        "numeric_quality": numeric_quality.reset_index(drop=True),
    }


def _bioinformatics_checks(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    sample_col = _detect_column(frame.columns, ("sample_id", "sample", "subject_id", "cell_id", "barcode"))
    batch_col = _detect_column(frame.columns, ("batch", "batch_id", "site", "center", "centre", "run"))
    group_col = _detect_column(frame.columns, ("group", "condition", "phenotype", "case_control", "label"))
    chrom_col = _detect_column(frame.columns, ("chrom", "chromosome", "chr"))
    pos_col = _detect_column(frame.columns, ("position", "pos", "start"))
    count_like = [
        column
        for column in frame.select_dtypes(include=[np.number]).columns
        if re.search(r"(?i)(count|read|umi|abundance|depth|coverage)", str(column))
    ]
    if sample_col:
        duplicate_samples = int(frame[sample_col].astype(str).duplicated().sum())
        rows.append({"check": "sample_identifier_uniqueness", "status": "pass" if duplicate_samples == 0 else "review", "value": duplicate_samples, "detail": sample_col})
        if duplicate_samples:
            warnings.append(f"{duplicate_samples} duplicate sample identifiers were detected in {sample_col}.")
    if chrom_col and pos_col:
        invalid_pos = int((pd.to_numeric(frame[pos_col], errors="coerce") <= 0).fillna(True).sum())
        rows.append({"check": "genomic_coordinates", "status": "pass" if invalid_pos == 0 else "fail", "value": invalid_pos, "detail": f"{chrom_col}/{pos_col}"})
        if invalid_pos:
            warnings.append("Genomic coordinates contain missing or non-positive positions.")
    if count_like:
        negative = int((frame[count_like].apply(pd.to_numeric, errors="coerce") < 0).sum().sum())
        rows.append({"check": "nonnegative_count_features", "status": "pass" if negative == 0 else "fail", "value": negative, "detail": ", ".join(map(str, count_like[:8]))})
        if negative:
            warnings.append("Count-like bioinformatics features contain negative values.")
    if batch_col and group_col:
        association = _cramers_v(frame[batch_col].fillna("[missing]"), frame[group_col].fillna("[missing]"))
        if association is not None:
            status = "review" if association >= 0.7 else "pass"
            rows.append({"check": "batch_group_confounding", "status": status, "value": round(association, 4), "detail": f"Cramer's V: {batch_col} vs {group_col}"})
            if association >= 0.7:
                warnings.append("Batch/site and biological group are strongly associated; validation may be confounded.")
    numeric = frame.select_dtypes(include=[np.number])
    if not numeric.empty:
        zero_fraction = float((numeric.fillna(0) == 0).to_numpy().mean())
        rows.append({"check": "numeric_matrix_sparsity", "status": "review" if zero_fraction > 0.95 else "pass", "value": round(zero_fraction, 4), "detail": "Overall zero fraction"})
    return pd.DataFrame(rows), warnings


def _discovery_checks(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    id_col = _detect_column(frame.columns, ("compound_id", "molecule_id", "ligand_id", "id"))
    smiles_col = _detect_column(frame.columns, ("smiles", "canonical_smiles", "structure"))
    activity_col = _detect_column(frame.columns, ("activity", "activity_value", "ic50", "ec50", "ki", "kd", "pactivity"))
    unit_col = _detect_column(frame.columns, ("unit", "activity_unit", "units"))
    if id_col:
        duplicates = int(frame[id_col].astype(str).duplicated().sum())
        rows.append({"check": "compound_identifier_uniqueness", "status": "review" if duplicates else "pass", "value": duplicates, "detail": id_col})
    if smiles_col:
        blank = int(frame[smiles_col].astype(str).str.strip().isin({"", "nan", "none"}).sum())
        duplicate_structures = int(frame[smiles_col].astype(str).duplicated().sum())
        rows.extend(
            [
                {"check": "structure_presence", "status": "fail" if blank else "pass", "value": blank, "detail": smiles_col},
                {"check": "duplicate_structure_rows", "status": "review" if duplicate_structures else "pass", "value": duplicate_structures, "detail": smiles_col},
            ]
        )
        if blank:
            warnings.append("Blank molecular structures were detected.")
    if activity_col:
        numeric = pd.to_numeric(frame[activity_col], errors="coerce")
        invalid = int(numeric.isna().sum())
        rows.append({"check": "numeric_activity", "status": "fail" if invalid else "pass", "value": invalid, "detail": activity_col})
    if unit_col:
        units = sorted({str(value).strip() for value in frame[unit_col].dropna().unique() if str(value).strip()})
        rows.append({"check": "activity_unit_consistency", "status": "review" if len(units) > 1 else "pass", "value": len(units), "detail": ", ".join(units[:8])})
        if len(units) > 1:
            warnings.append("Multiple activity units were detected; normalize before ranking compounds.")
    if id_col and activity_col:
        replicate_counts = frame.groupby(id_col, dropna=False)[activity_col].size()
        rows.append({"check": "replicate_measurements", "status": "pass", "value": int((replicate_counts > 1).sum()), "detail": "Compounds with repeated measurements"})
    return pd.DataFrame(rows), warnings


def _lab_checks(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    sample_col = _detect_column(frame.columns, ("sample_id", "sample", "well_id", "specimen_id"))
    batch_col = _detect_column(frame.columns, ("batch", "batch_id", "plate", "plate_id", "run_id"))
    control_col = _detect_column(frame.columns, ("control", "control_type", "sample_type", "role"))
    value_col = _detect_column(frame.columns, ("value", "signal", "response", "concentration", "ct", "cq"))
    replicate_col = _detect_column(frame.columns, ("replicate", "replicate_id", "technical_replicate"))
    if sample_col:
        rows.append({"check": "sample_identifier_presence", "status": "pass", "value": int(frame[sample_col].notna().sum()), "detail": sample_col})
    if control_col:
        values = frame[control_col].astype(str).str.lower()
        control_count = int(values.str.contains("control|blank|calibrator|standard", regex=True, na=False).sum())
        rows.append({"check": "control_coverage", "status": "review" if control_count == 0 else "pass", "value": control_count, "detail": control_col})
        if control_count == 0:
            warnings.append("No rows were recognisable as controls, blanks, calibrators or standards.")
    if batch_col:
        batch_sizes = frame.groupby(batch_col, dropna=False).size()
        rows.append({"check": "batch_balance", "status": "review" if batch_sizes.min() < 2 else "pass", "value": int(batch_sizes.size), "detail": f"min={int(batch_sizes.min())}, max={int(batch_sizes.max())}"})
    if value_col:
        values = pd.to_numeric(frame[value_col], errors="coerce")
        invalid = int(values.isna().sum())
        rows.append({"check": "numeric_measurement", "status": "fail" if invalid else "pass", "value": invalid, "detail": value_col})
        if sample_col and (replicate_col or frame[sample_col].duplicated().any()):
            grouped = frame.assign(_value=values).groupby(sample_col, dropna=False)["_value"]
            cv = grouped.agg(lambda x: float(x.std(ddof=1) / abs(x.mean())) if x.notna().sum() > 1 and abs(x.mean()) > 1e-12 else np.nan)
            high_cv = int((cv > 0.20).sum())
            rows.append({"check": "replicate_precision_cv_gt_20pct", "status": "review" if high_cv else "pass", "value": high_cv, "detail": sample_col})
            if high_cv:
                warnings.append(f"{high_cv} sample groups have replicate CV above 20%.")
    return pd.DataFrame(rows), warnings


def _neuro_checks(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    subject_col = _detect_column(frame.columns, ("subject_id", "participant_id", "patient_id", "sample_id"))
    time_col = _detect_column(frame.columns, ("time", "timepoint", "time_months", "visit", "timestamp"))
    group_col = _detect_column(frame.columns, ("group", "condition", "diagnosis", "phenotype"))
    site_col = _detect_column(frame.columns, ("site", "center", "centre", "scanner", "batch"))
    if subject_col:
        blank = int(frame[subject_col].isna().sum())
        rows.append({"check": "subject_identifier_completeness", "status": "fail" if blank else "pass", "value": blank, "detail": subject_col})
    if subject_col and time_col:
        order_violations = 0
        converted = pd.to_datetime(frame[time_col], errors="coerce")
        if converted.notna().mean() < 0.5:
            converted = pd.to_numeric(frame[time_col], errors="coerce")
        temp = frame.assign(_time=converted)
        for _, group in temp.groupby(subject_col, dropna=False):
            values = group["_time"].dropna().to_numpy()
            if len(values) > 1 and np.any(values[1:] < values[:-1]):
                order_violations += 1
        rows.append({"check": "longitudinal_time_order", "status": "review" if order_violations else "pass", "value": order_violations, "detail": time_col})
    if group_col and site_col:
        association = _cramers_v(frame[group_col].fillna("[missing]"), frame[site_col].fillna("[missing]"))
        if association is not None:
            rows.append({"check": "site_group_confounding", "status": "review" if association >= 0.7 else "pass", "value": round(association, 4), "detail": f"Cramer's V: {site_col} vs {group_col}"})
            if association >= 0.7:
                warnings.append("Site/scanner and neurological group are strongly associated.")
    direct = [str(column) for column in frame.columns if _DIRECT_IDENTIFIER.match(str(column).strip())]
    rows.append({"check": "direct_identifier_scan", "status": "fail" if direct else "pass", "value": len(direct), "detail": ", ".join(direct)})
    if direct:
        warnings.append("Potential direct identifiers are present; de-identify before research analysis or export.")
    return pd.DataFrame(rows), warnings


def audit_tabular_dataset(frame: pd.DataFrame, category: str) -> dict[str, Any]:
    """Run deterministic, local-first readiness checks without fabricating scientific conclusions."""

    base = _base_dataset_audit(frame)
    normalized = str(category)
    if normalized == "Bioinformatics":
        category_checks, warnings = _bioinformatics_checks(frame)
    elif normalized == "Discovery":
        category_checks, warnings = _discovery_checks(frame)
    elif normalized == "Lab Analytics":
        category_checks, warnings = _lab_checks(frame)
    elif normalized == "Neuro/CNS":
        category_checks, warnings = _neuro_checks(frame)
    else:
        category_checks, warnings = pd.DataFrame(), []

    if base["duplicate_rows"]:
        warnings.append(f"{base['duplicate_rows']} completely duplicated rows were detected.")
    if base["constant_columns"]:
        warnings.append("Constant columns: " + ", ".join(base["constant_columns"][:12]))
    if base["direct_identifier_columns"]:
        warnings.append("Potential direct identifier columns: " + ", ".join(base["direct_identifier_columns"]))
    severe_missing = base["missingness"].loc[base["missingness"]["missing_fraction"] >= 0.50, "column"].astype(str).tolist()
    if severe_missing:
        warnings.append("Columns at least 50% missing: " + ", ".join(severe_missing[:12]))

    status_counts = (
        category_checks["status"].value_counts().to_dict()
        if isinstance(category_checks, pd.DataFrame) and not category_checks.empty and "status" in category_checks
        else {}
    )
    blocking = int(status_counts.get("fail", 0))
    reviews = int(status_counts.get("review", 0))
    completeness = float(1.0 - base["missingness"]["missing_fraction"].mean())
    readiness_score = max(
        0.0,
        min(
            10.0,
            10.0 * completeness
            - min(3.0, blocking * 1.5)
            - min(2.0, reviews * 0.35)
            - min(1.0, base["duplicate_fraction"] * 10.0),
        ),
    )
    return {
        "schema": "biointel.module_data_readiness.v207",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "category": normalized,
        "summary": {
            "rows": base["rows"],
            "columns": base["columns"],
            "memory_mb": base["memory_mb"],
            "duplicate_rows": base["duplicate_rows"],
            "constant_columns": len(base["constant_columns"]),
            "potential_direct_identifiers": len(base["direct_identifier_columns"]),
            "blocking_checks": blocking,
            "review_checks": reviews,
            "data_completeness": round(completeness, 4),
            "readiness_score_internal": round(readiness_score, 2),
        },
        "missingness": base["missingness"],
        "numeric_quality": base["numeric_quality"],
        "category_checks": category_checks,
        "warnings": sorted(dict.fromkeys(warnings)),
        "scientific_boundary": (
            "This is an internal software/data-readiness audit. It does not establish clinical, wet-lab, regulatory or external scientific validity."
        ),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return value.head(500).replace({np.nan: None}).to_dict(orient="records")
    if isinstance(value, pd.Series):
        return value.head(500).replace({np.nan: None}).tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _SECRET_KEY.search(str(key)) else _json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in list(value)[:500]]
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def build_diagnostic_bundle(
    profile: ModuleQualityProfile,
    *,
    release: str,
    runtime_errors: Iterable[Mapping[str, Any]] = (),
    upload_profiles: Iterable[Mapping[str, Any]] = (),
    data_audit: Mapping[str, Any] | None = None,
) -> bytes:
    """Create a sanitized support/provenance ZIP without source data or uploaded rows."""

    manifest = {
        "schema": "biointel.module_diagnostics.v207",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "release": str(release),
        "module": profile.to_dict(),
        "upload_profiles": [_json_safe(item) for item in list(upload_profiles)[:50]],
        "runtime_errors": [
            {
                "error_id": str(item.get("error_id", "")),
                "timestamp_utc": str(item.get("timestamp_utc", "")),
                "context": str(item.get("context", "")),
                "exception_type": str(item.get("exception_type", "")),
                "message": str(item.get("message", ""))[:500],
            }
            for item in list(runtime_errors)[:50]
        ],
        "data_audit_summary": _json_safe(data_audit.get("summary", {})) if data_audit else None,
        "scientific_boundary": "Diagnostics contain metadata only; uploaded scientific rows and project files are excluded.",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("module_diagnostic_manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        if data_audit:
            audit_export = {
                "schema": data_audit.get("schema"),
                "generated_at_utc": data_audit.get("generated_at_utc"),
                "category": data_audit.get("category"),
                "summary": _json_safe(data_audit.get("summary", {})),
                "warnings": _json_safe(data_audit.get("warnings", [])),
                "scientific_boundary": data_audit.get("scientific_boundary"),
            }
            archive.writestr("data_readiness_summary.json", json.dumps(audit_export, indent=2, ensure_ascii=False))
    return buffer.getvalue()
