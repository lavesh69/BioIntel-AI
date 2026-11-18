from __future__ import annotations

import importlib.util
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from biointel.tools.runtime import resolve_tool

from .specs import get_spec


@dataclass(frozen=True)
class StageAssessment:
    key: str
    label: str
    mode: str
    status: str
    readiness: float
    tools: str
    missing_tools: str
    references: str
    validation_gate: str
    purpose: str


@dataclass(frozen=True)
class ModuleAssessment:
    module_key: str
    title: str
    domain: str
    tier: str
    tier_label: str
    execution_readiness: float
    tools_available: int
    tools_required: int
    packages_available: int
    packages_required: int
    stages: tuple[StageAssessment, ...]
    blockers: tuple[str, ...]
    release_ready: bool
    evidence_boundary: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["stages"] = [asdict(stage) for stage in self.stages]
        return payload

    def stage_frame(self) -> pd.DataFrame:
        return pd.DataFrame([asdict(stage) for stage in self.stages])


@dataclass(frozen=True)
class StatisticalAudit:
    rows: int
    columns: int
    missing_cells: int
    missing_fraction: float
    duplicate_rows: int
    numeric_columns: int
    groups: int
    minimum_group_size: int | None
    replicate_units: int | None
    constant_numeric_columns: tuple[str, ...]
    extreme_outlier_cells: int
    status: str
    blockers: tuple[str, ...]
    recommendations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_FORMAT_SUPPORT: dict[str, tuple[str, str]] = {
    ".fasta": ("native", "streaming sequence parser"),
    ".fa": ("native", "streaming sequence parser"),
    ".fna": ("native", "streaming sequence parser"),
    ".faa": ("native", "streaming sequence parser"),
    ".fastq": ("native", "bounded FASTQ parser"),
    ".fq": ("native", "bounded FASTQ parser"),
    ".vcf": ("native", "VCF parser and optional pysam"),
    ".bcf": ("adapter", "pysam/bcftools required"),
    ".bam": ("adapter", "pysam/samtools required"),
    ".cram": ("adapter", "pysam/samtools and reference required"),
    ".gff": ("native", "feature table parser"),
    ".gff3": ("native", "feature table parser"),
    ".gtf": ("native", "feature table parser"),
    ".bed": ("native", "interval parser"),
    ".gfa": ("native", "bounded graph parser"),
    ".pdb": ("native", "coordinate parser"),
    ".cif": ("native", "mmCIF parser"),
    ".mmcif": ("native", "mmCIF parser"),
    ".h5ad": ("adapter", "anndata/scanpy backed mode"),
    ".zarr": ("adapter", "anndata/zarr backed mode"),
    ".mtx": ("native", "sparse matrix parser"),
    ".fcs": ("adapter", "flow-cytometry parser"),
    ".mzml": ("adapter", "OpenMS/pyteomics-compatible workflow"),
    ".mzxml": ("adapter", "OpenMS/pyteomics-compatible workflow"),
    ".rdml": ("native", "RDML XML parser"),
    ".sdf": ("native", "RDKit molecule parser"),
    ".mol": ("native", "RDKit molecule parser"),
    ".mol2": ("adapter", "Open Babel/RDKit conversion"),
    ".csv": ("native", "streaming tabular parser"),
    ".tsv": ("native", "streaming tabular parser"),
    ".xlsx": ("native", "bounded workbook parser"),
    ".parquet": ("adapter", "PyArrow/DuckDB-compatible workflow"),
}


def _package_available(name: str) -> bool:
    aliases = {"sklearn": "sklearn", "rdkit": "rdkit", "statsmodels": "statsmodels"}
    try:
        return importlib.util.find_spec(aliases.get(name, name)) is not None
    except (ImportError, ValueError):
        return False


def assess_module(module_key: str, *, available_references: Iterable[str] = ()) -> ModuleAssessment:
    spec = get_spec(module_key)
    reference_set = {item.strip().lower() for item in available_references if item.strip()}
    tool_names = tuple(dict.fromkeys(tool for stage in spec.stages for tool in stage.tools))
    tool_status = {name: resolve_tool(name) for name in tool_names}
    package_status = {name: _package_available(name) for name in spec.python_packages}
    stages: list[StageAssessment] = []
    weighted_ready = 0.0
    weighted_total = 0.0
    blockers: list[str] = []
    for stage in spec.stages:
        if stage.mode == "built-in":
            status, readiness, weight = "Available", 1.0, 1.0
        elif stage.mode == "adapter":
            required = list(stage.tools)
            missing = [name for name in required if not tool_status.get(name, resolve_tool(name)).available]
            reference_missing = [name for name in stage.references if name.lower() not in reference_set]
            if required and not missing:
                status = "Executable adapter"
                readiness = 1.0 if not reference_missing else 0.75
            elif required and len(missing) < len(required):
                status, readiness = "Partially configured", 0.5
            elif not required and not reference_missing:
                status, readiness = "Adapter ready", 0.75
            else:
                status, readiness = "Blocked", 0.15
            weight = 1.25
            if missing:
                blockers.append(f"{stage.label}: missing {', '.join(missing)}")
            if reference_missing:
                blockers.append(f"{stage.label}: configure {', '.join(reference_missing)}")
        else:
            status, readiness, weight = "External validation required", 0.0, 0.0
        weighted_ready += readiness * weight
        weighted_total += weight
        missing_tools = [name for name in stage.tools if not tool_status.get(name, resolve_tool(name)).available]
        stages.append(StageAssessment(
            stage.key, stage.label, stage.mode, status, readiness,
            ", ".join(stage.tools) or "Built-in",
            ", ".join(missing_tools),
            ", ".join(stage.references), stage.validation_gate, stage.purpose,
        ))
    for name, available in package_status.items():
        if not available:
            blockers.append(f"Optional Python package missing: {name}")
    readiness = weighted_ready / max(weighted_total, 1.0)
    adapter_stages = [stage for stage in stages if stage.mode == "adapter"]
    blocked_adapters = [stage for stage in adapter_stages if stage.status == "Blocked"]
    if adapter_stages and not blocked_adapters and all(stage.readiness >= 0.75 for stage in adapter_stages):
        tier, label = "A", "Tier A · executable pipeline configured"
    elif adapter_stages:
        tier, label = "B", "Tier B · adapter-ready with external requirements"
    else:
        tier, label = "C", "Tier C · built-in/heuristic workflow"
    release_ready = False  # external-validation stages cannot be auto-certified
    blockers.extend(spec.release_blockers)
    return ModuleAssessment(
        module_key=module_key,
        title=spec.title,
        domain=spec.domain,
        tier=tier,
        tier_label=label,
        execution_readiness=readiness,
        tools_available=sum(item.available for item in tool_status.values()),
        tools_required=len(tool_status),
        packages_available=sum(package_status.values()),
        packages_required=len(package_status),
        stages=tuple(stages),
        blockers=tuple(dict.fromkeys(blockers)),
        release_ready=release_ready,
        evidence_boundary=spec.evidence_boundary,
    )


def format_support(filename: str) -> dict[str, str]:
    lowered = filename.lower()
    if lowered.endswith((".fastq.gz", ".fq.gz", ".vcf.gz")):
        suffix = ".fastq" if lowered.endswith((".fastq.gz", ".fq.gz")) else ".vcf"
    else:
        suffix = Path(lowered).suffix
    mode, detail = _FORMAT_SUPPORT.get(suffix, ("staged", "universal inspector and module-specific adapter required"))
    return {"filename": filename, "extension": suffix or "none", "mode": mode, "detail": detail}


def bh_fdr(p_values: Sequence[float]) -> np.ndarray:
    values = np.asarray(p_values, dtype=float)
    if values.size == 0:
        return values
    if np.any(~np.isfinite(values)) or np.any((values < 0) | (values > 1)):
        raise ValueError("p-values must be finite and between 0 and 1")
    order = np.argsort(values)
    ranked = values[order]
    adjusted = ranked * len(values) / np.arange(1, len(values) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    output = np.empty_like(adjusted)
    output[order] = np.minimum(adjusted, 1.0)
    return output


def hedges_g(group_a: Sequence[float], group_b: Sequence[float]) -> float:
    a = np.asarray(group_a, dtype=float)
    b = np.asarray(group_b, dtype=float)
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    pooled_denom = len(a) + len(b) - 2
    pooled = math.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / pooled_denom)
    if pooled == 0:
        return 0.0
    d = (a.mean() - b.mean()) / pooled
    correction = 1 - (3 / (4 * (len(a) + len(b)) - 9))
    return float(d * correction)


def statistical_audit(
    frame: pd.DataFrame,
    *,
    group_column: str | None = None,
    replicate_column: str | None = None,
) -> StatisticalAudit:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    rows, columns = frame.shape
    missing_cells = int(frame.isna().sum().sum())
    missing_fraction = missing_cells / max(rows * columns, 1)
    duplicate_rows = int(frame.duplicated().sum())
    numeric = frame.select_dtypes(include=[np.number])
    constant = tuple(column for column in numeric.columns if numeric[column].dropna().nunique() <= 1)
    outlier_cells = 0
    for column in numeric.columns:
        values = numeric[column].replace([np.inf, -np.inf], np.nan).dropna()
        if len(values) < 4:
            continue
        q1, q3 = values.quantile([0.25, 0.75])
        iqr = q3 - q1
        if iqr > 0:
            outlier_cells += int(((values < q1 - 3 * iqr) | (values > q3 + 3 * iqr)).sum())
    groups = 0
    minimum_group_size = None
    blockers: list[str] = []
    recommendations: list[str] = []
    if group_column:
        if group_column not in frame.columns:
            blockers.append(f"Group column not found: {group_column}")
        else:
            counts = frame[group_column].dropna().astype(str).value_counts()
            groups = int(len(counts))
            minimum_group_size = int(counts.min()) if not counts.empty else 0
            if groups < 2:
                blockers.append("At least two groups are required for comparison")
            if minimum_group_size < 2:
                blockers.append("At least one group has fewer than two observations")
            elif minimum_group_size < 3:
                recommendations.append("Increase biological replication; one group has fewer than three observations")
    replicate_units = None
    if replicate_column:
        if replicate_column not in frame.columns:
            blockers.append(f"Replicate column not found: {replicate_column}")
        else:
            replicate_units = int(frame[replicate_column].dropna().nunique())
            if replicate_units < 2:
                blockers.append("Fewer than two independent replicate units are present")
    if rows == 0:
        blockers.append("Dataset is empty")
    if missing_fraction > 0.25:
        blockers.append("More than 25% of cells are missing")
    elif missing_fraction > 0.05:
        recommendations.append("Review missing-data mechanism and sensitivity")
    if duplicate_rows:
        recommendations.append(f"Review {duplicate_rows} duplicate row(s)")
    if constant:
        recommendations.append("Remove or justify constant numeric columns")
    if outlier_cells:
        recommendations.append("Review extreme outliers using a prespecified policy")
    if not numeric.columns.empty:
        recommendations.append("Report effect sizes and confidence intervals, not p-values alone")
    status = "blocked" if blockers else ("review" if recommendations else "ready")
    return StatisticalAudit(
        rows, columns, missing_cells, missing_fraction, duplicate_rows, len(numeric.columns),
        groups, minimum_group_size, replicate_units, constant, outlier_cells,
        status, tuple(blockers), tuple(dict.fromkeys(recommendations)),
    )


def release_manifest(module_key: str, *, inputs: Mapping[str, Any] | None = None, parameters: Mapping[str, Any] | None = None) -> dict[str, Any]:
    spec = get_spec(module_key)
    assessment = assess_module(module_key)
    return {
        "schema": "biointel.step127.module-release-manifest.v1",
        "module_key": module_key,
        "title": spec.title,
        "domain": spec.domain,
        "execution_tier": assessment.tier,
        "execution_readiness": round(assessment.execution_readiness, 4),
        "inputs": dict(inputs or {}),
        "parameters": dict(parameters or {}),
        "features_added": list(spec.features_added),
        "statistical_requirements": list(spec.statistical_requirements),
        "release_blockers": list(spec.release_blockers),
        "evidence_boundary": spec.evidence_boundary,
        "release_ready": False,
    }
