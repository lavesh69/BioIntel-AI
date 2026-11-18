from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from biointel.database.core import managed_connect

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BenchmarkProfile:
    module_key: str
    name: str
    truth_requirements: tuple[str, ...]
    metrics: tuple[str, ...]
    stratifications: tuple[str, ...]
    external_reference: str
    boundary: str


_DEFAULTS = {
    "population_gwas_peak": ("association truth/replication cohort", ("precision", "recall", "f1", "calibration"), ("ancestry", "frequency", "chromosome"), "GIAB-compatible variant truth where applicable"),
    "epigenomics_peak": ("validated peak/region labels", ("precision", "recall", "f1", "correlation"), ("assay", "chromatin_state", "signal_bin"), "ENCODE-style held-out regions"),
    "pharmacogenomics_peak": ("validated diplotype/phenotype calls", ("accuracy", "precision", "recall"), ("gene", "population", "coverage"), "laboratory-confirmed PGx controls"),
    "structural_variant_peak": ("truth SV set", ("precision", "recall", "f1"), ("event_type", "size_bin", "difficult_region"), "GIAB SV benchmark compatibility"),
    "rna_splicing_peak": ("validated splicing events", ("precision", "recall", "f1", "correlation"), ("event_type", "support_bin", "tissue"), "orthogonal RT-PCR/long-read truth"),
    "immune_repertoire": ("known clonotypes/controls", ("accuracy", "diversity_error", "correlation"), ("chain", "depth", "sample"), "AIRR community benchmark controls"),
    "single_cell_multiome": ("held-out labels/modalities", ("accuracy", "ari", "silhouette", "correlation"), ("cell_type", "batch", "modality"), "curated multimodal atlas"),
    "proteogenomics_peak": ("validated peptide-spectrum matches", ("precision", "recall", "f1", "calibration"), ("hla", "expression_bin", "ms_support"), "immunopeptidomics controls"),
    "gene_regulatory_network": ("perturbation-backed edges", ("precision", "recall", "auprc", "stability"), ("tf", "cell_type", "evidence_type"), "held-out perturbation evidence"),
    "federated_genomic_discovery": ("known case matches", ("precision", "recall", "ranking"), ("source", "consent", "phenotype_count"), "curated synthetic federation test pack"),
    "viral_within_host": ("validated variants/lineages", ("precision", "recall", "f1", "frequency_error"), ("frequency_bin", "amplicon", "lineage"), "sequencing control mixtures"),
    "genome_annotation": ("curated annotation", ("precision", "recall", "f1", "busco"), ("feature_type", "evidence", "length_bin"), "curated reference annotation"),
    "circular_dna_instability": ("validated amplicon topology", ("precision", "recall", "topology_accuracy"), ("event_type", "copy_number", "purity"), "orthogonal long-read/FISH evidence"),
    "environmental_edna": ("known community/control truth", ("precision", "recall", "f1", "abundance_error"), ("taxon", "site", "control_type"), "mock community and field controls"),
    "comparative_regulatory_genomics": ("validated orthologous regulatory regions", ("precision", "recall", "correlation"), ("species", "tissue", "constraint_bin"), "cross-species functional evidence"),
}

BENCHMARK_PROFILES = {
    key: BenchmarkProfile(key, f"{key.replace('_', ' ').title()} benchmark", (truth,), tuple(metrics), tuple(strata), external, "Benchmark results measure the supplied truth pack only and are not a substitute for independent external validation.")
    for key, (truth, metrics, strata, external) in _DEFAULTS.items()
}


def _binary_metrics(truth: pd.Series, prediction: pd.Series) -> dict[str, float]:
    y = pd.to_numeric(truth, errors="coerce").fillna(0).astype(int).clip(0, 1)
    pred_numeric = pd.to_numeric(prediction, errors="coerce").fillna(0)
    yhat = (pred_numeric >= 0.5).astype(int)
    tp = int(((y == 1) & (yhat == 1)).sum()); tn = int(((y == 0) & (yhat == 0)).sum())
    fp = int(((y == 0) & (yhat == 1)).sum()); fn = int(((y == 1) & (yhat == 0)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / len(y) if len(y) else 0.0
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1, "accuracy": accuracy}


def run_benchmark(frame: pd.DataFrame, *, truth_column: str, prediction_column: str, module_key: str, subgroup_column: str | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    if truth_column not in frame.columns or prediction_column not in frame.columns:
        raise ValueError("Truth and prediction columns must exist.")
    work = frame[[truth_column, prediction_column] + ([subgroup_column] if subgroup_column and subgroup_column in frame.columns else [])].dropna()
    if work.empty:
        raise ValueError("Benchmark has no complete truth/prediction rows.")
    overall = _binary_metrics(work[truth_column], work[prediction_column])
    rows = [{"stratum": "Overall", "records": len(work), **overall}]
    if subgroup_column and subgroup_column in work.columns:
        for value, group in work.groupby(subgroup_column, dropna=False):
            rows.append({"stratum": str(value), "records": len(group), **_binary_metrics(group[truth_column], group[prediction_column])})
    summary = {"module_key": module_key, "truth_column": truth_column, "prediction_column": prediction_column, "records": len(work), "generated_at_utc": datetime.now(timezone.utc).isoformat(), **overall}
    return pd.DataFrame(rows), summary


class BenchmarkStore:
    def __init__(self, project_root: str | Path):
        self.path = Path(project_root).resolve() / "UserData" / "workspace" / "bioinformatics_peak_v140" / "benchmarks.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with managed_connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS runs (run_id INTEGER PRIMARY KEY AUTOINCREMENT, module_key TEXT NOT NULL, created_at_utc TEXT NOT NULL, profile_json TEXT NOT NULL, summary_json TEXT NOT NULL)")

    def save(self, module_key: str, summary: dict[str, Any]) -> int:
        profile = BENCHMARK_PROFILES[module_key]
        with managed_connect(self.path) as db:
            cur = db.execute("INSERT INTO runs(module_key,created_at_utc,profile_json,summary_json) VALUES(?,?,?,?)", (module_key, datetime.now(timezone.utc).isoformat(), json.dumps(asdict(profile), sort_keys=True), json.dumps(summary, sort_keys=True, default=str)))
            return int(cur.lastrowid)

    def history(self, module_key: str) -> pd.DataFrame:
        with managed_connect(self.path) as db:
            rows = db.execute("SELECT run_id,created_at_utc,summary_json FROM runs WHERE module_key=? ORDER BY run_id DESC LIMIT 200", (module_key,)).fetchall()
        records = []
        for run_id, created, payload in rows:
            summary = json.loads(payload)
            records.append({"run_id": run_id, "created_at_utc": created, **summary})
        return pd.DataFrame(records)


__all__ = ["BenchmarkProfile", "BENCHMARK_PROFILES", "run_benchmark", "BenchmarkStore"]
