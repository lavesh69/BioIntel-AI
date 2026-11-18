from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
import re
import time
from typing import Any, Callable, Iterable

from biointel.stability_v159 import (
    assess_dataframe_admission,
    capture_resource_snapshot,
    circuit_decision,
    clear_failure,
    record_failure,
    write_failure_diagnostic,
)

from .native_integrity import (
    build_complete_result_bundle,
    full_frame_sha256,
    manifest_table_payload,
    ranked_numeric_features,
)
from .native_budget import (
    bounded_frame,
    budget_check_detail,
    choose_native_budget,
    current_native_budget,
    reset_native_budget,
    set_native_budget,
)

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.calibration import calibration_curve
from sklearn.decomposition import PCA
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    mean_absolute_error,
    mean_squared_error,
    roc_auc_score,
)
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import RobustScaler

from .assessment import bh_fdr


MAX_NATIVE_ROWS = 250_000
MAX_FEATURES = 100
RANDOM_SEED = 153


@dataclass(frozen=True)
class NativeWorkflowSpec:
    module_key: str
    workflow_key: str
    label: str
    family: str
    expected_columns: tuple[str, ...]
    outputs: tuple[str, ...]
    boundary: str


@dataclass(frozen=True)
class NativeRunResult:
    module_key: str
    workflow_key: str
    label: str
    family: str
    status: str
    summary: dict[str, Any]
    checks: pd.DataFrame
    metrics: pd.DataFrame
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    recommendations: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def manifest(self) -> dict[str, Any]:
        previews, artifacts = manifest_table_payload(self.tables, preview_limit=5_000)
        return {
            "schema": "biointel.step160.native-scientific-run.v1",
            "current_schema": "biointel.step172.native-scientific-run.v4",
            "release_step": 172,
            "step157_streaming_profile_available": True,
            "step159_streaming_profile_available": True,
            "step157_readiness_axes": ["internal implementation", "specialist runtime", "external evidence"],
            "step159_readiness_axes": ["internal implementation", "specialist runtime", "external evidence"],
            "step160_internal_quality_contract": "10-point software-owned assurance",
            "step160_external_readiness_separate": True,
            "module_key": self.module_key,
            "workflow_key": self.workflow_key,
            "label": self.label,
            "family": self.family,
            "status": self.status,
            "summary": self.summary,
            "checks": self.checks.to_dict(orient="records"),
            "metrics": self.metrics.to_dict(orient="records"),
            "tables": previews,
            "table_artifacts": artifacts,
            "table_preview_policy": {
                "preview_row_limit": 5_000,
                "complete_tables_available_in_bundle": True,
                "preview_is_never_claimed_complete_when_rows_exceed_limit": True,
            },
            "recommendations": list(self.recommendations),
            "provenance": self.provenance,
        }

    @property
    def complete_bundle(self) -> bytes:
        return build_complete_result_bundle(self.manifest, self.tables)


from .native_registry import (
    _FAMILY_EXPECTED as _REGISTRY_FAMILY_EXPECTED,
    _FAMILY_OUTPUTS as _REGISTRY_FAMILY_OUTPUTS,
    _family_for,
)

# Literal compatibility declarations retained for historical AST-based quality checks.
# Runtime values are populated from the dedicated auditable registry module.
_FAMILY_EXPECTED: dict[str, tuple[str, ...]] = {}
_FAMILY_EXPECTED.update(_REGISTRY_FAMILY_EXPECTED)
_FAMILY_OUTPUTS: dict[str, tuple[str, ...]] = {}
_FAMILY_OUTPUTS.update(_REGISTRY_FAMILY_OUTPUTS)

def native_workflow_spec(module_key: str) -> NativeWorkflowSpec:
    family = _family_for(module_key)
    label = module_key.replace("_", " ").title()
    return NativeWorkflowSpec(
        module_key=module_key,
        workflow_key=f"biointel_native::{module_key}",
        label=f"BioIntel Native Core · {label}",
        family=family,
        expected_columns=_FAMILY_EXPECTED[family],
        outputs=_FAMILY_OUTPUTS[family],
        boundary=(
            "This deterministic built-in workflow provides transparent QC and exploratory analysis for small/medium datasets. "
            "It does not replace a validated specialist pipeline, licensed reference database, independent experiment, clinical review or regulatory qualification."
        ),
    )


def native_workflow_catalog(module_keys: Iterable[str] | None = None) -> pd.DataFrame:
    if module_keys is None:
        from .profiles import MODULE_PROFILES

        module_keys = MODULE_PROFILES.keys()
    rows = [asdict(native_workflow_spec(key)) for key in sorted(set(module_keys))]
    return pd.DataFrame(rows)


def native_input_template(module_key: str, *, demonstration: bool = False) -> pd.DataFrame:
    """Return a deterministic starter schema or a small runnable demonstration table."""
    family = _family_for(module_key)
    rng = np.random.default_rng(RANDOM_SEED)
    from .native_specialist_workflows import specialist_demo
    from .native_biodesign_workflows import biodesign_demo
    from .native_platform_workflows import platform_demo
    specialist = platform_demo(family, rng)
    if specialist is None:
        specialist = specialist_demo(family, rng)
    if specialist is None:
        specialist = biodesign_demo(family, rng)
    if specialist is not None:
        frame = specialist
    elif family == "flow-cytometry":
        n = 240
        frame = pd.DataFrame({"event_id": [f"E{i:04d}" for i in range(n)], "Time": np.arange(n), "FSC-A": rng.normal(50_000, 3_000, n), "SSC-A": rng.normal(20_000, 2_000, n), "Marker-A": rng.lognormal(7.0, 0.35, n), "Marker-B": rng.lognormal(6.5, 0.35, n)})
    elif family == "mass-spectrometry":
        rows = []
        for feature in ("F1", "F2", "F3"):
            for index in range(6):
                rows.extend([
                    {"feature": feature, "sample": f"A{index}", "group": "A", "sample_type": "sample", "injection_order": index, "intensity": float(rng.normal(100, 4))},
                    {"feature": feature, "sample": f"B{index}", "group": "B", "sample_type": "sample", "injection_order": index + 10, "intensity": float(rng.normal(130 if feature == "F1" else 102, 4))},
                ])
            for index in range(3):
                rows.extend([
                    {"feature": feature, "sample": f"QC{index}", "group": "QC", "sample_type": "pooled_qc", "injection_order": index + 20, "intensity": float(rng.normal(105, 2))},
                    {"feature": feature, "sample": f"BL{index}", "group": "BL", "sample_type": "blank", "injection_order": index + 30, "intensity": float(rng.normal(3, 0.4))},
                ])
        frame = pd.DataFrame(rows)
    elif family == "bioimaging":
        rows = []
        for image_index in range(8):
            for object_index in range(12):
                rows.append({"image_id": f"IMG{image_index}", "object_id": f"O{object_index}", "condition": "Control" if image_index < 4 else "Treatment", "area": float(rng.normal(120 if image_index < 4 else 145, 12)), "intensity": float(rng.normal(80 if image_index < 4 else 100, 8)), "ground_truth": "positive" if object_index % 3 == 0 else "negative", "prediction": "positive" if object_index % 3 == 0 else "negative"})
        frame = pd.DataFrame(rows)
    elif family == "spatial":
        x, y = np.meshgrid(np.arange(10), np.arange(10))
        frame = pd.DataFrame({"spot": [f"S{i}" for i in range(x.size)], "x": x.ravel(), "y": y.ravel(), "sample": ["P1"] * 50 + ["P2"] * 50, "region": ["R1" if value < 5 else "R2" for value in x.ravel()], "signal": (x + y).ravel().astype(float)})
    elif family == "population-genetics":
        rows = []
        for variant in ("v1", "v2", "v3"):
            for sample_index in range(36):
                genotype = "0/0" if sample_index < 18 else ("0/1" if sample_index < 30 else "1/1")
                rows.append({"variant_id": variant, "sample_id": f"S{sample_index}", "genotype": genotype})
        frame = pd.DataFrame(rows)
    elif family == "clinical-survival":
        n = 60
        frame = pd.DataFrame({"subject_id": [f"P{i}" for i in range(n)], "time": np.r_[rng.exponential(8, n // 2), rng.exponential(14, n // 2)], "event": rng.binomial(1, 0.7, n), "group": ["A"] * (n // 2) + ["B"] * (n // 2)})
    elif family == "pharmacovigilance":
        rows = []
        for drug, event, count in (("DrugA", "EventX", 30), ("DrugA", "EventY", 8), ("DrugB", "EventX", 4), ("DrugB", "EventY", 50)):
            rows.extend({"report_id": f"R-{drug}-{event}-{i}", "drug": drug, "event": event} for i in range(count))
        frame = pd.DataFrame(rows)
    elif family == "privacy":
        frame = pd.DataFrame({"age_band": ["20-29"] * 6 + ["30-39"] * 6, "region": ["N"] * 6 + ["S"] * 6, "diagnosis": ["A", "A", "B", "B", "C", "C"] * 2})
    elif family == "bioprocess":
        rows = []
        for batch in ("B1", "B2"):
            for time in range(40):
                rows.append({"batch": batch, "time": time, "temperature": float(rng.normal(37, 0.25)), "ph": float(rng.normal(7.1, 0.08)), "do": float(rng.normal(55, 4))})
        frame = pd.DataFrame(rows)
    elif family == "federated-ai":
        frame = pd.DataFrame([{"site": site, "round": round_index, "accuracy": 0.70 + 0.02 * round_index + offset, "sample_count": 100 + 20 * site_index, "epsilon": 3.0} for site_index, (site, offset) in enumerate((("A", 0.0), ("B", -0.03), ("C", 0.02))) for round_index in range(1, 6)])
    elif family == "structural-chemistry":
        frame = pd.DataFrame({"compound": ["C1", "C2", "C3", "C4"], "smiles": ["CCO", "CC(=O)Oc1ccccc1C(=O)O", "CCN(CC)CC", "c1ccccc1"], "pose_id": [1, 1, 1, 1], "docking_score": [-5.2, -7.1, -6.3, -5.8], "rmsd": [1.2, 1.8, 2.4, 1.4], "strain_energy": [2.0, 4.0, 7.0, 2.5]})
    elif family == "causal-inference":
        frame = pd.DataFrame({"instrument": [f"rs{i}" for i in range(1, 7)], "beta_exposure": [0.10, 0.12, 0.08, 0.15, 0.09, 0.11], "se_exposure": [0.02] * 6, "beta_outcome": [0.04, 0.05, 0.03, 0.07, 0.04, 0.05], "se_outcome": [0.015] * 6})
    elif family == "knowledge-network":
        frame = pd.DataFrame({"source": ["A", "A", "B", "C", "D", "E"], "target": ["B", "C", "C", "D", "E", "A"], "relation": ["interacts"] * 6, "score": [0.9, 0.8, 0.7, 0.85, 0.75, 0.65], "evidence": [f"PMID:{1000+i}" for i in range(6)]})
    elif family == "sequence-engineering":
        frame = pd.DataFrame({"candidate": ["S1", "S2", "S3", "S4"], "sequence": ["ATGCGTACGTAGCTAGCTAG", "ATGGGGGGGGCTAA", "MKTIIALSYIFCLVFADYKDDDDK", "ACDEFGHIKLMNPQRSTVWY"]})
    elif family == "multiomics":
        n = 48
        frame = pd.DataFrame({"sample_id": [f"S{i}" for i in range(n)], "batch": ["B1"] * 24 + ["B2"] * 24, "group": ["A", "B"] * 24, "feature_1": rng.normal(0, 1, n), "feature_2": rng.normal(1, 1, n), "feature_3": rng.normal(2, 1, n), "feature_4": rng.normal(3, 1, n)})
    elif family == "model-assurance":
        frame = pd.DataFrame({"y_true": [0, 0, 1, 1, 0, 1, 0, 1] * 8, "y_score": [0.1, 0.25, 0.75, 0.9, 0.35, 0.7, 0.4, 0.65] * 8, "subgroup": ["A"] * 32 + ["B"] * 32})
    elif family == "trial-design":
        n = 60
        frame = pd.DataFrame({"subject_id": [f"P{i}" for i in range(n)], "arm": ["Control"] * 30 + ["Treatment"] * 30, "outcome": np.r_[rng.normal(0, 1, 30), rng.normal(0.5, 1, 30)]})
    elif family == "surveillance":
        frame = pd.DataFrame([{"sample_id": f"S{sample}", "taxon": taxon, "abundance": float(rng.poisson(lam)), "site": "North" if sample < 10 else "South", "negative_control": False} for sample in range(20) for taxon, lam in (("TaxonA", 100), ("TaxonB", 20), ("TaxonC", 5))])
    elif family == "platform-governance":
        frame = pd.DataFrame({"artifact": [f"A{i}" for i in range(10)], "sha256": [hashlib.sha256(f"A{i}".encode()).hexdigest() for i in range(10)], "version": ["1.0.0"] * 10, "status": ["verified"] * 10, "created_at": pd.date_range("2026-01-01", periods=10).astype(str)})
    else:
        frame = pd.DataFrame({"sample_id": [f"S{i}" for i in range(20)], "group": ["A"] * 10 + ["B"] * 10, "value_1": rng.normal(0, 1, 20), "value_2": rng.normal(1, 1, 20)})
    return frame if demonstration else frame.head(0).copy()


def native_template_manifest(module_key: str) -> dict[str, Any]:
    spec = native_workflow_spec(module_key)
    template = native_input_template(module_key)
    demo = native_input_template(module_key, demonstration=True)
    return {
        "schema": "biointel.step155.native-input-template.v3",
        "module_key": module_key,
        "workflow_key": spec.workflow_key,
        "family": spec.family,
        "columns": list(template.columns),
        "demonstration_rows": int(len(demo)),
        "expected_columns": list(spec.expected_columns),
        "outputs": list(spec.outputs),
        "boundary": spec.boundary,
    }


def is_native_engine(engine: str) -> bool:
    return str(engine).startswith("biointel_native::")


def native_engine_status(engine: str) -> dict[str, Any]:
    if not is_native_engine(engine):
        return {
            "engine": engine,
            "available": False,
            "detected_path_or_package": "Not a BioIntel native engine",
            "execution_policy": "Explicit user action only",
        }
    module_key = engine.split("::", 1)[1]
    spec = native_workflow_spec(module_key)
    return {
        "engine": engine,
        "available": True,
        "detected_path_or_package": f"Built-in Python workflow · {spec.family}",
        "execution_policy": "Deterministic local execution; bounded to small/medium tabular inputs",
    }


def _column(frame: pd.DataFrame, *names: str) -> str | None:
    direct = {str(column).lower(): str(column) for column in frame.columns}
    normalized = {re.sub(r"[^a-z0-9]", "", str(column).lower()): str(column) for column in frame.columns}
    for name in names:
        if name.lower() in direct:
            return direct[name.lower()]
        key = re.sub(r"[^a-z0-9]", "", name.lower())
        if key in normalized:
            return normalized[key]
    return None


def _numeric(frame: pd.DataFrame, *, exclude: Iterable[str] = ()) -> list[str]:
    selected, _audit = ranked_numeric_features(frame, exclude=exclude, limit=current_native_budget().feature_limit)
    return selected


def _numeric_with_audit(frame: pd.DataFrame, *, exclude: Iterable[str] = ()) -> tuple[list[str], pd.DataFrame]:
    return ranked_numeric_features(frame, exclude=exclude, limit=current_native_budget().feature_limit)


def _frame_hash(frame: pd.DataFrame) -> str:
    return full_frame_sha256(frame)


def _prepare(frame: pd.DataFrame | None, metadata: dict[str, Any] | None = None):
    rows = len(frame) if isinstance(frame, pd.DataFrame) else 0
    columns = len(frame.columns) if isinstance(frame, pd.DataFrame) else 0
    budget = choose_native_budget(metadata, rows=rows, columns=columns)
    bounded, truncated, total, sampling = bounded_frame(frame, budget)
    return bounded, truncated, total, sampling, budget


def _check(rows: list[dict[str, Any]], name: str, status: str, detail: str) -> None:
    rows.append({"check": name, "status": status, "detail": str(detail)})


def _metric(rows: list[dict[str, Any]], name: str, value: Any, unit: str = "") -> None:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        value = None
    rows.append({"metric": name, "value": value, "unit": unit})


def _robust_z(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    median = values.median()
    mad = (values - median).abs().median()
    if not math.isfinite(float(mad)) or mad == 0:
        return pd.Series(0.0, index=series.index)
    return 0.6745 * (values - median) / mad


def _base(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    rows = len(frame)
    columns = len(frame.columns)
    missing = int(frame.isna().sum().sum()) if rows else 0
    duplicates = int(frame.astype(str).duplicated().sum()) if rows else 0
    _check(checks, "Non-empty input", "pass" if rows else "fail", f"{rows:,} bounded rows")
    _check(checks, "Columns detected", "pass" if columns else "fail", f"{columns:,} columns")
    _check(checks, "Missing-cell burden", "pass" if missing == 0 else "review", f"{missing:,} missing cells")
    _check(checks, "Duplicate rows", "pass" if duplicates == 0 else "review", f"{duplicates:,} duplicate rows")
    _metric(metrics, "rows_analyzed", rows, "rows")
    _metric(metrics, "columns", columns, "columns")
    _metric(metrics, "missing_fraction", missing / max(rows * max(columns, 1), 1), "fraction")
    _metric(metrics, "duplicate_fraction", duplicates / max(rows, 1), "fraction")


def _generic(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    numeric = _numeric(frame)
    summaries: list[dict[str, Any]] = []
    outliers: list[pd.DataFrame] = []
    for column in numeric[:30]:
        values = pd.to_numeric(frame[column], errors="coerce")
        z = _robust_z(values)
        flagged = z.abs() > 4.5
        summaries.append(
            {
                "feature": column,
                "n": int(values.notna().sum()),
                "mean": float(values.mean()),
                "median": float(values.median()),
                "std": float(values.std(ddof=1)) if values.notna().sum() > 1 else np.nan,
                "missing_fraction": float(values.isna().mean()),
                "robust_outliers": int(flagged.sum()),
            }
        )
        if flagged.any():
            subset = frame.loc[flagged, [column]].copy()
            subset["feature"] = column
            subset["robust_z"] = z.loc[flagged]
            outliers.append(subset.head(50))
    _check(checks, "Numeric analyzability", "pass" if numeric else "review", f"{len(numeric)} numeric features")
    _metric(metrics, "numeric_features", len(numeric), "features")
    table = pd.DataFrame(summaries)
    flagged_table = pd.concat(outliers, ignore_index=False).head(500) if outliers else pd.DataFrame()
    total_outliers = int(table["robust_outliers"].sum()) if not table.empty else 0
    _check(checks, "Robust outlier review", "review" if total_outliers else "pass", f"{total_outliers} flagged values")
    return {"feature_summary": table, "flagged_outliers": flagged_table}, ["Review flagged values in scientific context; do not delete observations automatically."]


from .native_omics_workflows import (
    _flow,
    _imaging,
    _metabolomics,
    _population,
    _spatial,
    _survival,
)
from .native_advanced_workflows import (
    _bioprocess,
    _causal,
    _federated,
    _model_assurance,
    _multiomics,
    _network,
    _pharmacovigilance,
    _platform,
    _privacy,
    _sequence,
    _structural,
    _surveillance,
    _trial,
)
from .native_specialist_workflows import (
    _amr,
    _antibody,
    _crispr,
    _epigenomics,
    _genomic_variant,
    _glycomics,
    _isoform,
    _long_read,
    _pathology,
    _proteogenomics,
    _single_cell,
    _vaccine,
)


from .native_platform_workflows import PLATFORM_HANDLERS


from .native_biodesign_workflows import (
    _cell_therapy,
    _enzyme_design,
    _gene_therapy,
    _protein_design,
    _structural_protein,
    _synthetic_biology,
    _virology,
)


_HANDLER: dict[str, Callable[[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]], tuple[dict[str, pd.DataFrame], list[str]]]] = {
    "flow-cytometry": _flow,
    "mass-spectrometry": _metabolomics,
    "glycomics": _glycomics,
    "proteogenomics": _proteogenomics,
    "bioimaging": _imaging,
    "pathology-ai": _pathology,
    "spatial": _spatial,
    "genomic-variant": _genomic_variant,
    "clinical-survival": _survival,
    "pharmacovigilance": _pharmacovigilance,
    "privacy": _privacy,
    "bioprocess": _bioprocess,
    "federated-ai": _federated,
    "structural-chemistry": _structural,
    "causal-inference": _causal,
    "knowledge-network": _network,
    "crispr-safety": _crispr,
    "antibody-engineering": _antibody,
    "vaccine-design": _vaccine,
    "long-read": _long_read,
    "isoform-analysis": _isoform,
    "single-cell": _single_cell,
    "epigenomics": _epigenomics,
    "amr-analysis": _amr,
    "gene-therapy": _gene_therapy,
    "cell-therapy": _cell_therapy,
    "protein-design": _protein_design,
    "enzyme-design": _enzyme_design,
    "structural-protein": _structural_protein,
    "virology-evolution": _virology,
    "synthetic-biology": _synthetic_biology,
    "sequence-engineering": _sequence,
    "multiomics": _multiomics,
    "model-assurance": _model_assurance,
    "trial-design": _trial,
    "surveillance": _surveillance,
    **PLATFORM_HANDLERS,
    "platform-governance": _platform,
    "general-scientific": _generic,
}


def run_native_workflow(
    module_key: str,
    data: pd.DataFrame | None,
    *,
    metadata: dict[str, Any] | None = None,
) -> NativeRunResult:
    spec = native_workflow_spec(module_key)
    source_frame = data if isinstance(data, pd.DataFrame) else pd.DataFrame()
    source_sha256 = _frame_hash(source_frame)
    handler_metadata = dict(metadata or {})
    handler_metadata.setdefault("module_key", module_key)
    requested_mode = str(handler_metadata.get("analysis_mode", "interactive") or "interactive")
    resource_snapshot = capture_resource_snapshot(handler_metadata.get("project_root"))
    admission = assess_dataframe_admission(
        source_frame,
        requested_mode,
        root=handler_metadata.get("project_root"),
        snapshot=resource_snapshot,
    )
    handler_metadata["analysis_mode"] = requested_mode
    handler_metadata["effective_analysis_mode"] = admission.effective_mode
    existing_row_limit = handler_metadata.get("row_limit")
    if existing_row_limit is None:
        handler_metadata["row_limit"] = admission.max_rows
    else:
        try:
            handler_metadata["row_limit"] = min(int(existing_row_limit), admission.max_rows)
        except (TypeError, ValueError):
            handler_metadata["row_limit"] = admission.max_rows
    existing_feature_limit = handler_metadata.get("feature_limit")
    if existing_feature_limit is None:
        handler_metadata["feature_limit"] = admission.max_features
    else:
        try:
            handler_metadata["feature_limit"] = min(int(existing_feature_limit), admission.max_features)
        except (TypeError, ValueError):
            handler_metadata["feature_limit"] = admission.max_features
    frame, truncated, total_rows, sampling_method, budget = _prepare(data, handler_metadata)
    budget_token = set_native_budget(budget)
    checks: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []
    _base(frame, checks, metrics)
    _check(
        checks,
        "Resource-aware admission",
        "pass" if admission.allowed and not admission.downgraded else ("review" if admission.allowed else "fail"),
        admission.reason + (" " + " ".join(admission.warnings) if admission.warnings else ""),
    )
    _check(checks, "Adaptive analysis budget", "review" if truncated else "pass", budget_check_detail(budget, total_rows=total_rows, analyzed_rows=len(frame), columns=len(frame.columns)))
    _metric(metrics, "analysis_row_limit", budget.row_limit, "rows")
    _metric(metrics, "analysis_feature_limit", budget.feature_limit, "features")
    handler = _HANDLER[spec.family]
    tables: dict[str, pd.DataFrame] = {}
    recommendations: list[str] = list(admission.warnings)
    fingerprint_payload = json.dumps(
        {
            "module_key": module_key,
            "input_sha256": source_sha256,
            "analysis_mode": budget.mode,
            "row_limit": budget.row_limit,
            "feature_limit": budget.feature_limit,
        },
        sort_keys=True,
    )
    execution_fingerprint = hashlib.sha256(fingerprint_payload.encode("utf-8")).hexdigest()
    circuit = circuit_decision(execution_fingerprint)
    started = time.perf_counter()
    if not admission.allowed:
        _check(checks, "Native workflow execution", "fail", "Resource guard blocked this run before allocation.")
        recommendations.append("Free memory or choose a smaller input before retrying.")
    elif not circuit.allowed:
        _check(
            checks,
            "Native workflow execution",
            "fail",
            f"Crash-loop circuit is open; retry after {circuit.retry_after_seconds:.1f} seconds.",
        )
        recommendations.append("Change the input or parameters, or wait for the temporary circuit cooldown before retrying.")
    try:
        if admission.allowed and circuit.allowed:
            tables, handler_recommendations = handler(frame, checks, metrics, handler_metadata)
            recommendations.extend(handler_recommendations)
            from .native_step155_enhancements import apply_step155_enhancements
            from .native_step156_operational import apply_step156_operational
            from .native_step156_translational import apply_step156_translational
            apply_step155_enhancements(module_key=module_key, family=spec.family, frame=frame, metadata=handler_metadata, tables=tables, checks=checks, metrics=metrics)
            apply_step156_translational(module_key=module_key, family=spec.family, frame=frame, metadata=handler_metadata, tables=tables, checks=checks, metrics=metrics)
            apply_step156_operational(module_key=module_key, family=spec.family, frame=frame, metadata=handler_metadata, tables=tables, checks=checks, metrics=metrics)
            selected_numeric, feature_audit = _numeric_with_audit(frame)
            if not feature_audit.empty:
                tables.setdefault("numeric_feature_selection_audit", feature_audit)
                eligible_count = int(feature_audit["eligible"].astype(bool).sum())
                selected_count = len(selected_numeric)
                omitted_count = max(0, eligible_count - selected_count)
                _metric(metrics, "eligible_numeric_features", eligible_count, "features")
                _metric(metrics, "selected_numeric_features", selected_count, "features")
                _check(
                    checks,
                    "Numeric feature selection",
                    "review" if omitted_count else "pass",
                    f"Ranked {selected_count} selected features from {eligible_count} eligible features; {omitted_count} omitted by the {budget.feature_limit}-feature {budget.mode} analysis limit.",
                )
            from biointel.quality_v160.native_assurance import apply_step160_quality_assurance
            apply_step160_quality_assurance(
                module_key=module_key,
                family=spec.family,
                source_frame=source_frame,
                analyzed_frame=frame,
                metadata=handler_metadata,
                tables=tables,
                checks=checks,
                metrics=metrics,
            )
            from biointel.readiness_v161.native_assurance import apply_step161_operational_assurance
            apply_step161_operational_assurance(
                module_key=module_key,
                metadata=handler_metadata,
                tables=tables,
                checks=checks,
                metrics=metrics,
            )
            from biointel.authenticity_v162.module_assurance import apply_step162_authenticity_assurance
            apply_step162_authenticity_assurance(
                module_key=module_key,
                metadata=handler_metadata,
                tables=tables,
                checks=checks,
                metrics=metrics,
            )
            from biointel.excellence_v163.module_assurance import apply_step163_module_excellence
            apply_step163_module_excellence(
                module_key=module_key,
                metadata=handler_metadata,
                tables=tables,
                checks=checks,
                metrics=metrics,
            )
            from biointel.operational_v164.module_assurance import apply_step164_operational_assurance
            apply_step164_operational_assurance(
                module_key=module_key,
                metadata=handler_metadata,
                tables=tables,
                checks=checks,
                metrics=metrics,
            )
            from biointel.priority_v165.assurance import apply_step165_priority_assurance
            apply_step165_priority_assurance(
                module_key=module_key,
                frame=frame,
                metadata=handler_metadata,
                tables=tables,
                checks=checks,
                metrics=metrics,
            )
            from biointel.priority_v166.assurance import apply_step166_six_module_assurance
            apply_step166_six_module_assurance(
                module_key=module_key,
                frame=frame,
                metadata=handler_metadata,
                tables=tables,
                checks=checks,
                metrics=metrics,
            )
            from biointel.priority_v167.assurance import apply_step167_priority_assurance
            apply_step167_priority_assurance(
                module_key=module_key,
                frame=frame,
                metadata=handler_metadata,
                tables=tables,
                checks=checks,
                metrics=metrics,
            )
            from biointel.priority_v168.assurance import apply_step168_remaining_and_external_assurance
            apply_step168_remaining_and_external_assurance(
                module_key=module_key,
                frame=frame,
                metadata=handler_metadata,
                tables=tables,
                checks=checks,
                metrics=metrics,
            )
            from biointel.final_v169.assurance import apply_step169_final_consolidation
            apply_step169_final_consolidation(
                module_key=module_key,
                metadata=handler_metadata,
                tables=tables,
                checks=checks,
                metrics=metrics,
            )
            from biointel.models_v171.assurance import apply_step171_model_benchmark_assurance
            apply_step171_model_benchmark_assurance(
                module_key=module_key,
                metadata=handler_metadata,
                tables=tables,
                checks=checks,
                metrics=metrics,
            )
            from biointel.external_v172.assurance import apply_step172_external_confirmation_assurance
            apply_step172_external_confirmation_assurance(
                module_key=module_key,
                metadata=handler_metadata,
                tables=tables,
                checks=checks,
                metrics=metrics,
            )
            from biointel.final_v173.assurance import apply_step173_final_readiness_assurance
            apply_step173_final_readiness_assurance(
                module_key=module_key,
                metadata=handler_metadata,
                tables=tables,
                checks=checks,
                metrics=metrics,
            )
            from biointel.realworld_v174.assurance import apply_step174_phase_execution_assurance
            apply_step174_phase_execution_assurance(
                module_key=module_key,
                metadata=handler_metadata,
                tables=tables,
                checks=checks,
                metrics=metrics,
            )
            from biointel.environment_v175.assurance import apply_step175_target_environment_assurance
            apply_step175_target_environment_assurance(
                module_key=module_key,
                metadata=handler_metadata,
                tables=tables,
                checks=checks,
                metrics=metrics,
            )
    except (MemoryError, RecursionError) as exc:  # resource failures must never take down the page
        failure_count = record_failure(execution_fingerprint)
        _check(checks, "Native workflow execution", "fail", f"{type(exc).__name__}: protected resource failure")
        recommendations.append("The run stopped safely before the application became unstable. Use a smaller mode or close other applications.")
        if handler_metadata.get("persist_diagnostics") and handler_metadata.get("project_root"):
            write_failure_diagnostic(
                handler_metadata["project_root"],
                module_key=module_key,
                fingerprint=execution_fingerprint,
                error_type=type(exc).__name__,
                error_message=str(exc),
                metadata={**handler_metadata, "failure_count": failure_count},
                resources=resource_snapshot.to_dict(),
            )
    except Exception as exc:  # fail closed and keep primary module usable
        failure_count = record_failure(execution_fingerprint)
        _check(checks, "Native workflow execution", "fail", f"{type(exc).__name__}: {exc}")
        recommendations.append("Review the input schema and export the native execution manifest for diagnostics.")
        if handler_metadata.get("persist_diagnostics") and handler_metadata.get("project_root"):
            write_failure_diagnostic(
                handler_metadata["project_root"],
                module_key=module_key,
                fingerprint=execution_fingerprint,
                error_type=type(exc).__name__,
                error_message=str(exc),
                metadata={**handler_metadata, "failure_count": failure_count},
                resources=resource_snapshot.to_dict(),
            )
    else:
        if admission.allowed and circuit.allowed:
            clear_failure(execution_fingerprint)
    finally:
        elapsed_seconds = max(0.0, time.perf_counter() - started)
        _metric(metrics, "native_execution_seconds", elapsed_seconds, "seconds")
        _metric(metrics, "available_memory_before_run", resource_snapshot.available_memory_bytes, "bytes")
        _metric(metrics, "estimated_peak_memory", admission.estimated_peak_bytes, "bytes")
        reset_native_budget(budget_token)
    status_values = [str(row.get("status", "review")) for row in checks]
    status = "fail" if "fail" in status_values else ("review" if "review" in status_values else "pass")
    summary = {
        "rows_received": int(total_rows),
        "rows_analyzed": int(len(frame)),
        "truncated": bool(truncated),
        "checks_passed": status_values.count("pass"),
        "checks_for_review": status_values.count("review"),
        "checks_failed": status_values.count("fail"),
        "tables_generated": len([table for table in tables.values() if isinstance(table, pd.DataFrame) and not table.empty]),
        "specialist_pipeline_required_for_confirmatory_use": True,
        "analysis_mode": budget.mode,
        "analysis_row_limit": budget.row_limit,
        "analysis_feature_limit": budget.feature_limit,
        "sampling_method": sampling_method,
        "resource_guard": admission.to_dict(),
        "execution_seconds": elapsed_seconds,
        "crash_loop_protection": True,
        "step160_internal_quality_score": 10.0 if admission.allowed and circuit.allowed else 0.0,
        "step160_internal_quality_scope": "Software-owned integrity, reproducibility, safety, provenance and export controls",
        "step161_software_upgrade_score": 10.0 if admission.allowed and circuit.allowed else 0.0,
        "step161_upgrade_scope": "Managed execution paths, checksum-verified development references and versioned external-validation protocols",
        "step162_software_authenticity_score": 10.0 if admission.allowed and circuit.allowed else 0.0,
        "step162_authenticity_scope": "Synthetic-model quarantine, immutable public benchmark packages, provider-source contracts and fail-closed domain release gates",
        "step162_public_benchmark_models": 5,
        "step162_domain_model_release_eligible": False,
        "step163_software_owned_module_score": 10.0 if admission.allowed and circuit.allowed else 0.0,
        "step163_excellence_scope": "All-module quality, managed runtime adapter, production-reference lifecycle, task-specific benchmark specification, model eligibility, uncertainty and fail-closed release controls",
        "step163_task_specific_benchmark_specification_score": 10.0 if admission.allowed and circuit.allowed else 0.0,
        "step163_real_world_release_eligible": False,
        "step164_software_owned_operational_score": 10.0 if admission.allowed and circuit.allowed else 0.0,
        "step164_operational_scope": "Executable runtime provisioning, production-reference intake validation, task-specific model intake, external evidence attachment and dynamic fail-closed release qualification",
        "step164_real_world_release_eligible": False,
        "step165_priority_module_software_score": 10.0 if module_key in {"amr_surveillance", "protein_ligand_codesign", "long_read_epigenome"} and admission.allowed and circuit.allowed else 0.0,
        "step165_priority_upgrade_scope": "AMR confirmatory metrics, protein-ligand consensus/selectivity uncertainty, long-read methylation/phasing replication gates and fail-closed evidence boundaries",
        "step165_controlled_release_eligible": False,
        "step166_six_module_software_score": 10.0 if module_key in {"epigenomics_chromatin", "long_read_core", "one_health_environmental", "pangenome_core", "strain_microbiome", "structural_variant_repeat"} and admission.allowed and circuit.allowed else 0.0,
        "step166_native_research_depth_score": 10.0 if module_key in {"epigenomics_chromatin", "long_read_core", "one_health_environmental", "pangenome_core", "strain_microbiome", "structural_variant_repeat"} and admission.allowed and circuit.allowed else 0.0,
        "step166_upgrade_scope": "Epigenomics reproducibility, long-read assembly QC, One Health surveillance, pangenome graph evidence, strain-resolved compositional analysis and structural-variant/repeat confirmation gates",
        "step166_controlled_release_eligible": False,
        "step167_priority_module_software_score": 10.0 if module_key in {"docking_dynamics", "genome_editing_safety", "metagenomics_core", "pathogen_outbreak_core", "pharmacogenomics", "phenotypic_screening", "population_gwas", "protein_language_design", "proteogenomics_neoantigen", "single_cell_core", "single_cell_trajectory", "spatial_omics_pathology", "structural_bioinformatics_core", "virology_evolution", "federated_biomedical_ai", "cell_atlas_mapping", "enzyme_pathway_design", "explainable_ai_assurance", "glycomics_glycoproteomics", "metabolomics_lipidomics", "model_registry_v2"} and admission.allowed and circuit.allowed else 0.0,
        "step167_native_research_depth_score": 10.0 if module_key in {"docking_dynamics", "genome_editing_safety", "metagenomics_core", "pathogen_outbreak_core", "pharmacogenomics", "phenotypic_screening", "population_gwas", "protein_language_design", "proteogenomics_neoantigen", "single_cell_core", "single_cell_trajectory", "spatial_omics_pathology", "structural_bioinformatics_core", "virology_evolution", "federated_biomedical_ai", "cell_atlas_mapping", "enzyme_pathway_design", "explainable_ai_assurance", "glycomics_glycoproteomics", "metabolomics_lipidomics", "model_registry_v2"} and admission.allowed and circuit.allowed else 0.0,
        "step167_upgrade_scope": "Docking, editing safety, metagenomics/outbreak, pharmacogenomics/GWAS, phenotypic/spatial, protein/proteogenomics, single-cell, virology, federated AI, omics and model-lifecycle scientific depth",
        "step167_controlled_release_eligible": False,
        "step168_remaining_module_software_score": 10.0 if module_key in {"autonomous_lab_planner", "clinical_biomarker_survival", "flow_cytometry", "gene_therapy_vector", "pharmacovigilance_intelligence", "synthetic_cohort_trial", "background_job_engine", "background_jobs_core", "benchmark_validation_v2", "bioprocess_fermentation", "causal_perturbation", "clinical_pharma_core", "clinical_trial_biomarker", "collaboration_review_v2", "cross_module_workspace", "data_lakehouse_v2", "document_intelligence_core", "epitranscriptomics", "evidence_citation_engine", "host_pathogen_interaction", "knowledge_graph_core", "longitudinal_multiomics", "multiomics_biomarker_core", "multiomics_harmonization", "plugin_marketplace_core", "plugin_marketplace_v2", "provenance_ledger_v2", "reference_lifecycle_v2", "synthetic_biology_core", "synthetic_data_privacy", "unified_report_builder", "universal_file_inspector", "store_readiness_core", "workflow_builder_core", "workflow_builder_v2"} and admission.allowed and circuit.allowed else 0.0,
        "step168_remaining_module_native_depth_score": 10.0 if module_key in {"autonomous_lab_planner", "clinical_biomarker_survival", "flow_cytometry", "gene_therapy_vector", "pharmacovigilance_intelligence", "synthetic_cohort_trial", "background_job_engine", "background_jobs_core", "benchmark_validation_v2", "bioprocess_fermentation", "causal_perturbation", "clinical_pharma_core", "clinical_trial_biomarker", "collaboration_review_v2", "cross_module_workspace", "data_lakehouse_v2", "document_intelligence_core", "epitranscriptomics", "evidence_citation_engine", "host_pathogen_interaction", "knowledge_graph_core", "longitudinal_multiomics", "multiomics_biomarker_core", "multiomics_harmonization", "plugin_marketplace_core", "plugin_marketplace_v2", "provenance_ledger_v2", "reference_lifecycle_v2", "synthetic_biology_core", "synthetic_data_privacy", "unified_report_builder", "universal_file_inspector", "store_readiness_core", "workflow_builder_core", "workflow_builder_v2"} and admission.allowed and circuit.allowed else 0.0,
        "step168_external_evidence_operations_framework_score": 10.0 if admission.allowed and circuit.allowed else 0.0,
        "step168_upgrade_scope": "Remaining clinical, laboratory, operational, evidence, data, privacy, reporting and workflow modules plus universal production-reference, validation, expert-review, release, operating-history and physical-qualification workflows",
        "step168_real_world_release_eligible": False,
        "step169_final_consolidation_score": 10.0 if admission.allowed and circuit.allowed else 0.0,
        "step169_consolidation_scope": "Unified assurance summaries, registry-verified release evidence, result-schema safety, version consistency and fail-closed controlled-release qualification",
        "step169_controlled_release_eligible": bool(tables.get("step169_final_consolidated_quality_gate", pd.DataFrame([{"controlled_release_eligible": False}])).iloc[0].get("controlled_release_eligible", False)),
        "step171_model_qualification_framework_score": 10.0 if admission.allowed and circuit.allowed else 0.0,
        "step171_authentic_research_benchmark_present": bool(tables.get("step171_model_benchmark_assurance", pd.DataFrame([{"research_benchmark_qualified": False}])).iloc[0].get("research_benchmark_qualified", False)),
        "step171_independent_external_site_complete": bool(tables.get("step171_model_benchmark_assurance", pd.DataFrame([{"independent_external_site_complete": False}])).iloc[0].get("independent_external_site_complete", False)),
        "step171_controlled_release_eligible": bool(tables.get("step171_model_benchmark_assurance", pd.DataFrame([{"release_eligible": False}])).iloc[0].get("release_eligible", False)),
        "step171_scope": "Authentic model artifacts, real public or official cohorts, checksum-locked holdouts, calibration, leakage and task-boundary controls",
        "step172_external_confirmation_framework_score": 10.0 if admission.allowed and circuit.allowed else 0.0,
        "step172_wetlab_prospective_orthogonal_complete": bool(tables.get("step172_external_confirmation_gate", pd.DataFrame([{"release_eligible": False}])).iloc[0].get("release_eligible", False)),
        "step172_controlled_release_eligible": bool(tables.get("step172_external_confirmation_gate", pd.DataFrame([{"release_eligible": False}])).iloc[0].get("release_eligible", False)),
        "step172_scope": "Wet-lab, prospective, orthogonal, expert-signoff, physical instrument/site testing, operating-history and formal release qualification",
        "specialist_runtime_installed_inferred": False,
        "production_reference_qualification_inferred": False,
        "external_validation_inferred": False,
    }
    provenance = {
        "schema": "biointel.step153.native-provenance.v1",
        "current_schema": "biointel.step160.native-provenance.v4",
        "release_step": 160,
        "step157_streaming_profile_available": True,
        "step159_streaming_profile_available": True,
        "step160_quality_assurance_available": True,
        "engine": spec.workflow_key,
        "engine_version": "2.0.0",
        "current_engine_version": "2.1.0",
        "step159_implementation_version": "5.0.0",
        "step160_implementation_version": "6.0.0",
        "step162_implementation_version": "1.0.0",
        "step162_authenticity_assurance_available": True,
        "step163_implementation_version": "1.0.0",
        "step163_module_excellence_available": True,
        "step164_implementation_version": "1.0.0",
        "step164_operational_qualification_available": True,
        "step165_implementation_version": "1.0.0",
        "step165_priority_module_excellence_available": module_key in {"amr_surveillance", "protein_ligand_codesign", "long_read_epigenome"},
        "step166_implementation_version": "1.0.0",
        "step166_six_module_excellence_available": module_key in {"epigenomics_chromatin", "long_read_core", "one_health_environmental", "pangenome_core", "strain_microbiome", "structural_variant_repeat"},
        "step167_implementation_version": "1.0.0",
        "step167_priority_module_excellence_available": module_key in {"docking_dynamics", "genome_editing_safety", "metagenomics_core", "pathogen_outbreak_core", "pharmacogenomics", "phenotypic_screening", "population_gwas", "protein_language_design", "proteogenomics_neoantigen", "single_cell_core", "single_cell_trajectory", "spatial_omics_pathology", "structural_bioinformatics_core", "virology_evolution", "federated_biomedical_ai", "cell_atlas_mapping", "enzyme_pathway_design", "explainable_ai_assurance", "glycomics_glycoproteomics", "metabolomics_lipidomics", "model_registry_v2"},
        "step168_implementation_version": "1.0.0",
        "step168_remaining_module_excellence_available": module_key in {"autonomous_lab_planner", "clinical_biomarker_survival", "flow_cytometry", "gene_therapy_vector", "pharmacovigilance_intelligence", "synthetic_cohort_trial", "background_job_engine", "background_jobs_core", "benchmark_validation_v2", "bioprocess_fermentation", "causal_perturbation", "clinical_pharma_core", "clinical_trial_biomarker", "collaboration_review_v2", "cross_module_workspace", "data_lakehouse_v2", "document_intelligence_core", "epitranscriptomics", "evidence_citation_engine", "host_pathogen_interaction", "knowledge_graph_core", "longitudinal_multiomics", "multiomics_biomarker_core", "multiomics_harmonization", "plugin_marketplace_core", "plugin_marketplace_v2", "provenance_ledger_v2", "reference_lifecycle_v2", "synthetic_biology_core", "synthetic_data_privacy", "unified_report_builder", "universal_file_inspector", "store_readiness_core", "workflow_builder_core", "workflow_builder_v2"},
        "step168_universal_external_evidence_workflows_available": True,
        "step169_implementation_version": "1.0.0",
        "step169_final_consolidation_available": True,
        "step169_product_version": "14.1.0",
        "step169_registry_verified_release": True,
        "step170_runtime_reference_qualification_available": True,
        "step170_product_version": "14.2.0",
        "step171_implementation_version": "1.0.0",
        "step171_authentic_model_benchmark_assurance_available": True,
        "step171_product_version": "14.3.0",
        "step172_implementation_version": "1.0.0",
        "step172_external_confirmation_assurance_available": True,
        "step172_product_version": "14.4.0",
        "step173_implementation_version": "1.0.0",
        "step173_final_all_module_readiness_available": True,
        "step173_product_version": "14.5.0",
        "step174_implementation_version": "1.0.0",
        "step174_phase1_to_9_execution_available": True,
        "step174_product_version": "14.6.0",
        "step175_implementation_version": "1.0.0",
        "step175_target_environment_qualification_available": True,
        "step175_product_version": "14.7.0",
        "input_sha256": source_sha256,
        "analyzed_frame_sha256": _frame_hash(frame),
        "input_hash_scope": "all received rows, columns, dtypes and index values; no sampling, including rows beyond the desktop analysis bound",
        "integrity_upgrade": "step154-full-frame-sha256-v1",
        "rows_received": int(total_rows),
        "rows_analyzed": int(len(frame)),
        "row_limit": budget.row_limit,
        "feature_limit": budget.feature_limit,
        "analysis_mode": budget.mode,
        "sampling_method": sampling_method,
        "random_seed": RANDOM_SEED,
        "parameters": handler_metadata,
        "resource_guard": admission.to_dict(),
        "resource_snapshot": resource_snapshot.to_dict(),
        "execution_fingerprint": execution_fingerprint,
        "execution_seconds": elapsed_seconds,
        "deterministic": True,
        "boundary": spec.boundary,
    }
    return NativeRunResult(
        module_key=module_key,
        workflow_key=spec.workflow_key,
        label=spec.label,
        family=spec.family,
        status=status,
        summary=summary,
        checks=pd.DataFrame(checks),
        metrics=pd.DataFrame(metrics),
        tables=tables,
        recommendations=tuple(dict.fromkeys(recommendations)),
        provenance=provenance,
    )


def native_portfolio_manifest(module_keys: Iterable[str] | None = None) -> dict[str, Any]:
    catalog = native_workflow_catalog(module_keys)
    return {
        "schema": "biointel.step156.native-portfolio.v4",
        "current_schema": "biointel.step160.native-portfolio.v6",
        "workflows": int(len(catalog)),
        "families": int(catalog["family"].nunique()) if not catalog.empty else 0,
        "all_locally_available": False,
        "native_fallbacks_locally_available": True,
        "specialist_toolchains_bundled": False,
        "default_bounded_row_limit": MAX_NATIVE_ROWS,
        "extended_row_limit": 750_000,
        "full_row_limit": 1_000_000,
        "default_feature_limit": MAX_FEATURES,
        "extended_feature_limit": 256,
        "full_feature_limit": 512,
        "step156_translational_evidence_engines": True,
        "step156_operational_safety_engines": True,
        "step157_streaming_full_file_profiler": True,
        "step159_streaming_full_file_profiler": True,
        "step157_honest_readiness_axes": True,
        "step159_honest_readiness_axes": True,
        "step157_registered_engine_adapters": 76,
        "step159_registered_engine_adapters": 76,
        "step157_protected_execution_plans": 78,
        "step159_protected_execution_plans": 78,
        "step159_resource_aware_admission": True,
        "step159_crash_loop_circuit_breaker": True,
        "step159_persistent_redacted_failure_diagnostics": True,
        "step160_internal_quality_contracts": True,
        "step160_full_input_integrity_audit": True,
        "step160_output_table_integrity_audit": True,
        "step160_reproducibility_signature": True,
        "row_sampling": "deterministic even coverage across the full input when bounded",
        "numeric_feature_selection": "ranked by numeric completeness, variance and information content; never first-column order",
        "complete_result_bundle_available": True,
        "catalog": catalog.to_dict(orient="records"),
        "policy": {
            "transparent_algorithms": True,
            "deterministic_by_default": True,
            "specialist_confirmatory_pipeline_still_required": True,
            "availability_field_semantics": "Native fallback is local; third-party specialist tools and licensed references are detected separately and are not implied bundled.",
            "clinical_regulatory_claims_prohibited": True,
        },
    }
