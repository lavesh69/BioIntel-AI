from __future__ import annotations

import hashlib
import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from .catalog import NextGenModule

NEW_BIOMEDICAL_KEYS: frozenset[str] = frozenset({
    "digital_pathology_foundation",
    "long_read_epigenome",
    "single_cell_long_read_isoforms",
    "biomedical_foundation_model_hub",
    "amr_surveillance",
    "spatial_medicine_tme",
    "gene_therapy_vector",
    "cell_therapy_cart",
    "federated_biomedical_ai",
    "clinical_biomarker_survival",
    "protein_ligand_codesign",
    "pangenome_population_medicine",
    "pharmacovigilance_intelligence",
    "synthetic_cohort_trial",
    "autonomous_lab_planner",
})


def _rng(key: str) -> np.random.Generator:
    seed = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16)
    return np.random.default_rng(seed)


def _numeric(series: pd.Series, fill: float | None = None) -> pd.Series:
    out = pd.to_numeric(series, errors="coerce")
    return out.fillna(fill) if fill is not None else out


def _minmax(series: pd.Series, *, higher_is_better: bool = True) -> pd.Series:
    values = _numeric(series)
    low, high = values.min(), values.max()
    if pd.isna(low) or pd.isna(high) or high == low:
        scaled = pd.Series(0.5, index=values.index, dtype=float)
    else:
        scaled = (values - low) / (high - low)
    return scaled if higher_is_better else 1.0 - scaled


def _welch(a: pd.Series, b: pd.Series) -> float:
    aa = _numeric(a).dropna().to_numpy(float)
    bb = _numeric(b).dropna().to_numpy(float)
    if len(aa) < 2 or len(bb) < 2:
        return float("nan")
    return float(stats.ttest_ind(aa, bb, equal_var=False, nan_policy="omit").pvalue)


def _bh(values: pd.Series) -> pd.Series:
    p = _numeric(values).to_numpy(float)
    result = np.full(len(p), np.nan)
    valid = np.isfinite(p)
    if not valid.any():
        return pd.Series(result, index=values.index)
    pv = p[valid]
    order = np.argsort(pv)
    ranked = pv[order]
    adjusted = ranked * len(ranked) / np.arange(1, len(ranked) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    restored = np.empty_like(adjusted)
    restored[order] = np.clip(adjusted, 0, 1)
    result[np.where(valid)[0]] = restored
    return pd.Series(result, index=values.index)


def _as_bool(series: pd.Series) -> pd.Series:
    """Parse boolean-like scientific fields without treating non-empty strings as True."""
    truthy = {"1", "true", "yes", "y", "positive", "resistant", "serious", "event"}
    falsy = {"0", "false", "no", "n", "negative", "susceptible", "non-serious", "none"}
    def convert(value: Any) -> bool:
        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return False
        text = str(value).strip().lower()
        if text in truthy:
            return True
        if text in falsy or text == "":
            return False
        try:
            return float(text) != 0.0
        except Exception:
            return False
    return series.map(convert).astype(bool)


def _kaplan_meier(frame: pd.DataFrame, *, group_columns: list[str]) -> pd.DataFrame:
    """Deterministic Kaplan–Meier table for exploratory visualisation."""
    required = {"time", "event", *group_columns}
    if frame.empty or not required.issubset(frame.columns):
        return pd.DataFrame()
    work = frame.copy()
    work["time"] = _numeric(work["time"])
    work["event"] = _numeric(work["event"], 0).clip(0, 1)
    work = work.dropna(subset=["time"])
    rows: list[dict[str, Any]] = []
    for keys, group in work.groupby(group_columns, dropna=False):
        key_tuple = keys if isinstance(keys, tuple) else (keys,)
        group = group.sort_values("time")
        survival = 1.0
        rows.append({**dict(zip(group_columns, key_tuple, strict=False)), "time": 0.0, "survival": 1.0, "at_risk": int(len(group)), "events": 0})
        for time_value in sorted(group["time"].dropna().unique().tolist()):
            at_risk = int((group["time"] >= time_value).sum())
            events = int(((group["time"] == time_value) & (group["event"] > 0)).sum())
            if at_risk > 0 and events > 0:
                survival *= max(0.0, 1.0 - events / at_risk)
            rows.append({**dict(zip(group_columns, key_tuple, strict=False)), "time": float(time_value), "survival": float(survival), "at_risk": at_risk, "events": events})
    return pd.DataFrame(rows)


def _standardized_mean_difference(frame: pd.DataFrame, *, arm_column: str, numeric_columns: list[str]) -> pd.DataFrame:
    if frame.empty or arm_column not in frame.columns:
        return pd.DataFrame()
    arms = [str(value) for value in frame[arm_column].dropna().astype(str).unique().tolist()]
    if len(arms) < 2:
        return pd.DataFrame()
    baseline, comparator = arms[0], arms[-1]
    rows: list[dict[str, Any]] = []
    for column in numeric_columns:
        if column not in frame.columns:
            continue
        a = _numeric(frame.loc[frame[arm_column].astype(str) == baseline, column]).dropna()
        b = _numeric(frame.loc[frame[arm_column].astype(str) == comparator, column]).dropna()
        if len(a) < 2 or len(b) < 2:
            continue
        pooled = math.sqrt(max(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / max(len(a) + len(b) - 2, 1), 0))
        smd = float((b.mean() - a.mean()) / pooled) if pooled > 0 else 0.0
        rows.append({"covariate": column, "baseline_arm": baseline, "comparator_arm": comparator, "smd": smd, "absolute_smd": abs(smd), "balanced": abs(smd) <= 0.1})
    return pd.DataFrame(rows)


def demo_frame(module: NextGenModule, n: int = 120) -> pd.DataFrame:
    rng = _rng(module.key)
    k = module.key

    if k == "digital_pathology_foundation":
        rows: list[dict[str, Any]] = []
        slides = max(8, n // 12)
        for s in range(slides):
            site = ["Site-A", "Site-B", "Site-C"][s % 3]
            scanner = ["Scanner-X", "Scanner-Y"][s % 2]
            slide_shift = 0.10 if s % 4 == 0 else 0.0
            for tile in range(12):
                rows.append({
                    "slide_id": f"SLIDE-{s + 1:03d}",
                    "tile_id": f"TILE-{tile + 1:04d}",
                    "tissue_fraction": float(np.clip(rng.normal(0.76, 0.16), 0, 1)),
                    "embedding_score": float(np.clip(rng.normal(0.78 - slide_shift, 0.10), 0, 1)),
                    "tumour_probability": float(np.clip(rng.beta(2.2 + (s % 2), 3.0), 0, 1)),
                    "scanner": scanner,
                    "site": site,
                })
        return pd.DataFrame(rows)

    if k == "long_read_epigenome":
        rows = []
        regions = [f"chr{1 + i % 4}:{100_000 + i * 8000}-{103_000 + i * 8000}" for i in range(24)]
        for sample_idx in range(12):
            condition = "Case" if sample_idx >= 6 else "Control"
            for region_idx, region in enumerate(regions):
                base = rng.beta(4, 4)
                shift = 0.22 if condition == "Case" and region_idx % 7 == 0 else 0.0
                for hap in ["H1", "H2"]:
                    allele_shift = 0.18 if region_idx % 9 == 0 and hap == "H1" else 0.0
                    rows.append({
                        "sample": f"LRM-{sample_idx + 1:03d}",
                        "chrom": region.split(":")[0],
                        "position": 100_000 + region_idx * 8000,
                        "haplotype": hap,
                        "methylation_fraction": float(np.clip(base + shift + allele_shift + rng.normal(0, 0.04), 0, 1)),
                        "coverage": int(rng.integers(12, 90)),
                        "region": region,
                        "condition": condition,
                    })
        return pd.DataFrame(rows)

    if k == "single_cell_long_read_isoforms":
        rows = []
        clusters = ["T cell", "B cell", "Myeloid", "Stromal"]
        genes = [f"GENE{i + 1:03d}" for i in range(16)]
        cells = max(40, n // 2)
        for cell_idx in range(cells):
            cluster = clusters[cell_idx % len(clusters)]
            for gene_idx, gene in enumerate(genes):
                for iso in range(2):
                    effect = 2.2 if cluster == "Myeloid" and gene_idx % 6 == 0 and iso == 1 else 1.0
                    rows.append({
                        "cell": f"CELL-{cell_idx + 1:05d}",
                        "cluster": cluster,
                        "gene": gene,
                        "transcript": f"{gene}.T{iso + 1}",
                        "umi_count": int(rng.poisson(2.5 * effect)),
                        "full_length": bool(rng.random() > 0.18),
                        "splice_junctions": int(rng.integers(1, 12)),
                    })
        return pd.DataFrame(rows)

    if k == "biomedical_foundation_model_hub":
        modalities = ["DNA", "Protein", "Single-cell", "Pathology", "Molecule"]
        tasks = ["Embedding", "Classification", "Generation", "Retrieval"]
        licences = ["Apache-2.0", "MIT", "Research-only", "Custom"]
        rows = []
        for i in range(max(30, n // 2)):
            params = int(rng.choice([80, 150, 350, 650, 1200, 3000, 7000])) * 1_000_000
            rows.append({
                "model_id": f"BFM-{i + 1:03d}",
                "modality": rng.choice(modalities),
                "task": rng.choice(tasks),
                "parameter_count": params,
                "embedding_dim": int(rng.choice([256, 512, 768, 1024, 1536])),
                "license": rng.choice(licences, p=[0.3, 0.25, 0.25, 0.2]),
                "local_ready": bool(rng.random() > 0.42),
                "benchmark_score": float(np.clip(rng.normal(0.77, 0.11), 0.35, 0.98)),
            })
        return pd.DataFrame(rows)

    if k == "amr_surveillance":
        species = ["E. coli", "K. pneumoniae", "S. aureus", "P. aeruginosa"]
        genes = ["blaCTX-M", "blaKPC", "mecA", "vanA", "qnrS", "aac(6')-Ib"]
        rows = []
        for i in range(max(80, n)):
            gene = rng.choice(genes)
            predicted = float(np.clip(rng.normal(0.76 if gene in {"mecA", "blaKPC", "vanA"} else 0.58, 0.18), 0, 1))
            phenotype = "Resistant" if rng.random() < predicted else "Susceptible"
            rows.append({
                "sample": f"ISO-{i + 1:05d}",
                "species": rng.choice(species),
                "lineage": f"ST{int(rng.integers(1, 500))}",
                "amr_gene": gene,
                "phenotype": phenotype,
                "resistant_probability": predicted,
                "location": rng.choice(["North", "South", "East", "West"]),
                "date": pd.Timestamp("2025-01-01") + pd.to_timedelta(int(rng.integers(0, 540)), unit="D"),
            })
        return pd.DataFrame(rows)

    if k == "spatial_medicine_tme":
        rows = []
        cell_types = ["Tumour", "CD8 T", "Treg", "Macrophage", "Fibroblast", "Endothelial"]
        genes = ["PDCD1", "CD274", "CXCL9", "COL1A1", "MKI67", "CD8A"]
        for patient in range(max(8, n // 15)):
            for spot in range(15):
                x, y = int(rng.integers(0, 100)), int(rng.integers(0, 100))
                region = "Core" if 25 < x < 75 and 25 < y < 75 else "Margin"
                ctype = rng.choice(cell_types)
                rows.append({
                    "patient": f"TME-{patient + 1:03d}",
                    "region": region,
                    "cell_type": ctype,
                    "gene": rng.choice(genes),
                    "expression": float(rng.gamma(2.2, 1.8) * (1.5 if ctype == "Tumour" else 1.0)),
                    "x": x,
                    "y": y,
                })
        return pd.DataFrame(rows)

    if k == "gene_therapy_vector":
        vector_types = ["AAV", "Lentiviral", "Adenoviral", "Non-viral"]
        promoters = ["CAG", "EF1a", "CMV", "Tissue-specific", "Inducible"]
        rows = []
        for i in range(max(50, n // 2)):
            vector = rng.choice(vector_types)
            limit = 4700 if vector == "AAV" else 9000 if vector == "Lentiviral" else 30_000
            cargo = int(rng.integers(900, min(limit + 2500, 12_000)))
            rows.append({
                "construct": f"VEC-{i + 1:04d}",
                "vector_type": vector,
                "cargo_bp": cargo,
                "promoter": rng.choice(promoters),
                "tropism_score": float(rng.uniform(0.25, 0.98)),
                "immunogenicity_risk": float(rng.uniform(0.02, 0.75)),
                "integration_risk": float(rng.uniform(0.01, 0.85 if vector == "Lentiviral" else 0.25)),
            })
        return pd.DataFrame(rows)

    if k == "cell_therapy_cart":
        rows = []
        antigens = ["CD19", "BCMA", "HER2", "EGFRvIII", "GPC3"]
        costim = ["4-1BB", "CD28", "ICOS", "OX40"]
        for i in range(max(50, n // 2)):
            rows.append({
                "construct": f"CAR-{i + 1:04d}",
                "antigen": rng.choice(antigens),
                "scfv_affinity": float(rng.lognormal(1.8, 0.45)),
                "costim_domain": rng.choice(costim),
                "off_tumour_risk": float(rng.uniform(0.02, 0.8)),
                "exhaustion_score": float(rng.uniform(0.05, 0.85)),
                "manufacturability": float(rng.uniform(0.3, 0.98)),
            })
        return pd.DataFrame(rows)

    if k == "federated_biomedical_ai":
        rows = []
        for round_id in range(1, 13):
            for site in ["Hospital-A", "Hospital-B", "Hospital-C", "Hospital-D"]:
                rows.append({
                    "site": site,
                    "round": round_id,
                    "samples": int(rng.integers(120, 1200)),
                    "metric": "AUROC",
                    "metric_value": float(np.clip(0.68 + 0.018 * round_id + rng.normal(0, 0.025), 0.5, 0.98)),
                    "drift_score": float(np.clip(rng.beta(2, 8), 0, 1)),
                    "privacy_epsilon": float(rng.choice([0.5, 1.0, 2.0, 4.0, 8.0])),
                })
        return pd.DataFrame(rows)

    if k == "clinical_biomarker_survival":
        rows = []
        for i in range(max(120, n)):
            marker = float(rng.normal(0, 1))
            arm = rng.choice(["Control", "Treatment"])
            response_prob = 1 / (1 + np.exp(-(0.45 * marker + (0.45 if arm == "Treatment" else -0.15))))
            response = int(rng.binomial(1, response_prob))
            time = float(rng.exponential(16 / (1 + 0.35 * response_prob)))
            rows.append({
                "patient": f"CBM-{i + 1:05d}",
                "arm": arm,
                "biomarker": marker,
                "time": time,
                "event": int(rng.binomial(1, 0.7)),
                "response": response,
                "site": rng.choice(["Site-1", "Site-2", "Site-3"]),
            })
        return pd.DataFrame(rows)

    if k == "protein_ligand_codesign":
        rows = []
        for i in range(max(80, n)):
            rows.append({
                "candidate": f"CO-{i + 1:04d}",
                "protein_variant": f"PV-{int(rng.integers(1, 30)):03d}",
                "ligand": f"LIG-{int(rng.integers(1, 45)):03d}",
                "protein_score": float(rng.uniform(0.2, 0.98)),
                "ligand_score": float(rng.uniform(0.2, 0.98)),
                "interface_score": float(rng.uniform(0.15, 0.99)),
                "selectivity_risk": float(rng.uniform(0.02, 0.85)),
            })
        return pd.DataFrame(rows)

    if k == "pangenome_population_medicine":
        rows = []
        populations = ["AFR", "AMR", "EAS", "EUR", "SAS"]
        for i in range(max(100, n)):
            pop = rng.choice(populations)
            clinical = float(rng.uniform(0, 1))
            rows.append({
                "sample": f"PGM-{i + 1:05d}",
                "population": pop,
                "path": f"PATH-{int(rng.integers(1, 80)):03d}",
                "variant": f"VAR-{int(rng.integers(1, 500)):05d}",
                "allele_frequency": float(rng.beta(1.2, 6.0)),
                "clinical_weight": clinical,
                "reference_bias": float(np.clip(rng.beta(2, 7) + (0.12 if pop == "AFR" else 0), 0, 1)),
            })
        return pd.DataFrame(rows)

    if k == "pharmacovigilance_intelligence":
        drugs = ["Drug-A", "Drug-B", "Drug-C", "Drug-D", "Drug-E"]
        events = ["Rash", "Nausea", "Liver injury", "Arrhythmia", "Neutropenia", "Headache"]
        rows = []
        for i in range(max(220, n * 2)):
            drug = rng.choice(drugs)
            event = rng.choice(events, p=[0.20, 0.22, 0.10, 0.10, 0.12, 0.26])
            if drug == "Drug-C" and rng.random() < 0.28:
                event = "Liver injury"
            rows.append({
                "report_id": f"AE-{i + 1:06d}",
                "drug": drug,
                "event": event,
                "serious": bool(rng.random() < (0.45 if event in {"Liver injury", "Arrhythmia", "Neutropenia"} else 0.12)),
                "outcome": rng.choice(["Recovered", "Recovering", "Not recovered", "Unknown"]),
                "age": int(rng.integers(18, 90)),
                "sex": rng.choice(["F", "M", "Unknown"]),
            })
        return pd.DataFrame(rows)

    if k == "synthetic_cohort_trial":
        rows = []
        for i in range(max(180, n)):
            arm = rng.choice(["Control", "Treatment"])
            baseline = float(np.clip(rng.beta(2.5, 4.5), 0, 1))
            outcome_prob = np.clip(0.25 + 0.35 * baseline - (0.12 if arm == "Treatment" else 0), 0.03, 0.95)
            outcome = int(rng.binomial(1, outcome_prob))
            rows.append({
                "patient": f"SYN-{i + 1:05d}",
                "arm": arm,
                "age": int(rng.integers(18, 85)),
                "baseline_risk": baseline,
                "outcome": outcome,
                "time": float(rng.exponential(15 / (1.2 - outcome_prob))),
                "event": int(rng.binomial(1, 0.65)),
                "site": rng.choice(["Synthetic-S1", "Synthetic-S2", "Synthetic-S3"]),
            })
        return pd.DataFrame(rows)

    if k == "autonomous_lab_planner":
        rows = []
        hypotheses = ["Gene perturbation changes response", "Dose affects viability", "Media composition improves yield", "Combination is synergistic"]
        factors = ["Dose", "Time", "Genotype", "Media", "Temperature"]
        for i in range(max(40, n // 2)):
            reps = int(rng.integers(2, 7))
            rows.append({
                "experiment_id": f"EXP-{i + 1:04d}",
                "hypothesis": rng.choice(hypotheses),
                "factor": rng.choice(factors),
                "level": str(rng.choice(["Low", "Medium", "High", "0.1", "1.0", "10.0"])),
                "control": bool(rng.random() < 0.22),
                "replicates": reps,
                "cost_per_run": float(rng.uniform(15, 850)),
            })
        return pd.DataFrame(rows)

    raise KeyError(k)


def analyse(
    data: pd.DataFrame,
    module: NextGenModule,
    threshold: float = 0.7,
) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame | None, dict[str, pd.DataFrame]]:
    frame = data.copy()
    k = module.key
    secondary: pd.DataFrame | None = None
    extras: dict[str, pd.DataFrame] = {}
    metrics: dict[str, Any] = {}

    if k == "digital_pathology_foundation":
        for c in ["tissue_fraction", "embedding_score", "tumour_probability"]:
            frame[c] = _numeric(frame[c])
        result = frame.groupby(["slide_id", "scanner", "site"], as_index=False).agg(
            tiles=("tile_id", "count"), tissue_fraction=("tissue_fraction", "mean"),
            embedding_score=("embedding_score", "mean"), tumour_burden=("tumour_probability", "mean"),
            high_tumour_tiles=("tumour_probability", lambda s: int((_numeric(s) >= threshold).sum())),
        )
        result["ood_risk"] = 1 - result["embedding_score"].clip(0, 1)
        result["qc_flag"] = (result["tissue_fraction"] < 0.35) | (result["ood_risk"] > 0.45)
        result["priority_score"] = result["tumour_burden"] * (1 - result["ood_risk"]) * (~result["qc_flag"]).astype(float)
        secondary = frame.groupby(["site", "scanner"], as_index=False).agg(slides=("slide_id", "nunique"), mean_embedding=("embedding_score", "mean"), mean_tumour=("tumour_probability", "mean"), mean_tissue=("tissue_fraction", "mean"))
        site_median = secondary["mean_embedding"].median()
        site_mad = float((secondary["mean_embedding"] - site_median).abs().median()) or 1e-9
        secondary["embedding_drift_score"] = ((secondary["mean_embedding"] - site_median).abs() / (1.4826 * site_mad)).clip(0, 10)
        secondary["drift_review"] = secondary["embedding_drift_score"] > 2.5
        extras["tile_level_qc"] = frame.assign(
            low_tissue=frame["tissue_fraction"] < 0.35,
            embedding_ood=(1 - frame["embedding_score"].clip(0, 1)) > 0.45,
            high_tumour=frame["tumour_probability"] >= threshold,
        )
        extras["scanner_site_drift"] = secondary.copy()
        extras["slide_tumour_heatmap"] = frame[["slide_id", "tile_id", "tumour_probability", "tissue_fraction", "embedding_score"]].copy()
        metrics = {"slides": int(result["slide_id"].nunique()), "qc_flags": int(result["qc_flag"].sum()), "sites": int(result["site"].nunique()), "scanner_drift_reviews": int(secondary["drift_review"].sum())}

    elif k == "long_read_epigenome":
        for c in ["methylation_fraction", "coverage"]:
            frame[c] = _numeric(frame[c])
        rows = []
        conditions = frame.get("condition", pd.Series(["Unknown"] * len(frame))).astype(str).unique().tolist()
        for (region, haplotype), group in frame.groupby(["region", "haplotype"]):
            row = {"region": region, "haplotype": haplotype, "samples": group["sample"].nunique(), "mean_methylation": float(group["methylation_fraction"].mean()), "median_coverage": float(group["coverage"].median())}
            if len(conditions) >= 2:
                a = group.loc[group["condition"].astype(str) == conditions[0], "methylation_fraction"]
                b = group.loc[group["condition"].astype(str) == conditions[-1], "methylation_fraction"]
                row.update({"delta_methylation": float(_numeric(b).mean() - _numeric(a).mean()), "p_value": _welch(a, b)})
            rows.append(row)
        result = pd.DataFrame(rows)
        result["q_value"] = _bh(result.get("p_value", pd.Series(np.nan, index=result.index)))
        result["qc_pass"] = (result["median_coverage"] >= 15) & (result["samples"] >= 4)
        result["priority_score"] = result.get("delta_methylation", pd.Series(0, index=result.index)).abs() * (1 - result["q_value"].fillna(1)) * result["qc_pass"].astype(float)
        hap = result.pivot_table(index="region", columns="haplotype", values="mean_methylation", aggfunc="mean").reset_index()
        if {"H1", "H2"}.issubset(hap.columns):
            hap["allelic_imbalance"] = (hap["H1"] - hap["H2"]).abs()
        secondary = hap
        extras["dmr_candidates"] = result.loc[(result["q_value"] <= 0.05) & result["qc_pass"]].copy()
        extras["region_condition_matrix"] = frame.groupby(["region", "condition"], as_index=False).agg(mean_methylation=("methylation_fraction", "mean"), median_coverage=("coverage", "median"), samples=("sample", "nunique"))
        extras["haplotype_imbalance"] = hap.copy()
        metrics = {"regions": int(result["region"].nunique()), "fdr_candidates": int((result["q_value"] <= 0.05).sum()), "qc_pass": int(result["qc_pass"].sum()), "max_allelic_imbalance": float(hap.get("allelic_imbalance", pd.Series([0.0])).max())}

    elif k == "single_cell_long_read_isoforms":
        frame["umi_count"] = _numeric(frame["umi_count"], 0).clip(lower=0)
        frame["splice_junctions"] = _numeric(frame["splice_junctions"], 0).clip(lower=0)
        frame["full_length"] = _as_bool(frame["full_length"])
        total = frame.groupby(["cell", "gene"])["umi_count"].transform("sum").replace(0, np.nan)
        frame["isoform_fraction"] = frame["umi_count"] / total
        result = frame.groupby(["gene", "transcript", "cluster"], as_index=False).agg(cells=("cell", "nunique"), mean_fraction=("isoform_fraction", "mean"), full_length_rate=("full_length", "mean"), median_junctions=("splice_junctions", "median"), total_umis=("umi_count", "sum"))
        result["support_score"] = _minmax(result["cells"]) * result["full_length_rate"].fillna(0) * _minmax(result["median_junctions"])
        result["priority_score"] = result["mean_fraction"].fillna(0) * result["support_score"]
        secondary = result.groupby(["cluster", "gene"], as_index=False).agg(isoforms=("transcript", "nunique"), dominant_fraction=("mean_fraction", "max"), total_umis=("total_umis", "sum"))
        dominant = result.sort_values("mean_fraction", ascending=False).drop_duplicates(["gene", "cluster"]).copy()
        dominant["isoform_switch_candidate"] = dominant.groupby("gene")["transcript"].transform("nunique") > 1
        extras["dominant_isoforms"] = dominant
        extras["isoform_usage_matrix"] = result[["gene", "transcript", "cluster", "mean_fraction", "support_score", "priority_score"]].copy()
        extras["junction_support_qc"] = result[["gene", "transcript", "cluster", "cells", "full_length_rate", "median_junctions", "total_umis"]].copy()
        metrics = {"cells": int(frame["cell"].nunique()), "genes": int(frame["gene"].nunique()), "isoforms": int(frame["transcript"].nunique()), "switch_candidates": int(dominant["isoform_switch_candidate"].sum())}

    elif k == "biomedical_foundation_model_hub":
        frame["parameter_count"] = _numeric(frame["parameter_count"], 0)
        frame["embedding_dim"] = _numeric(frame["embedding_dim"], 0)
        frame["benchmark_score"] = _numeric(frame["benchmark_score"], 0)
        frame["local_ready"] = _as_bool(frame["local_ready"])
        frame["license_review_required"] = ~frame["license"].astype(str).isin(["Apache-2.0", "MIT", "BSD-3-Clause"])
        frame["resource_tier"] = pd.cut(frame["parameter_count"], [-1, 500e6, 2e9, 8e9, np.inf], labels=["Laptop", "Workstation", "High-memory GPU", "Cluster"])
        frame["readiness_score"] = 0.55 * frame["benchmark_score"].clip(0, 1) + 0.25 * frame["local_ready"].astype(bool).astype(float) + 0.20 * (~frame["license_review_required"]).astype(float)
        frame["release_blocked"] = (~frame["local_ready"].astype(bool)) | frame["license_review_required"]
        frame["priority_score"] = frame["readiness_score"] * (~frame["release_blocked"]).astype(float)
        result = frame.sort_values(["release_blocked", "readiness_score"], ascending=[True, False])
        secondary = result.groupby(["modality", "task"], as_index=False).agg(models=("model_id", "count"), local_ready=("local_ready", "sum"), mean_benchmark=("benchmark_score", "mean"), blocked=("release_blocked", "sum"))
        extras["hardware_compatibility"] = result[["model_id", "modality", "task", "parameter_count", "embedding_dim", "resource_tier", "local_ready", "release_blocked"]].copy()
        extras["licence_review_matrix"] = result.groupby(["license", "modality"], as_index=False).agg(models=("model_id", "count"), local_ready=("local_ready", "sum"), mean_benchmark=("benchmark_score", "mean"), licence_reviews=("license_review_required", "sum"))
        extras["modality_task_coverage"] = secondary.copy()
        metrics = {"models": len(result), "local_ready": int(result["local_ready"].sum()), "license_review": int(result["license_review_required"].sum()), "blocked": int(result["release_blocked"].sum())}

    elif k == "amr_surveillance":
        frame["resistant_probability"] = _numeric(frame["resistant_probability"], 0).clip(0, 1)
        frame["predicted_resistant"] = frame["resistant_probability"] >= threshold
        frame["observed_resistant"] = frame["phenotype"].astype(str).str.lower().eq("resistant")
        frame["concordant"] = frame["predicted_resistant"] == frame["observed_resistant"]
        result = frame.groupby(["species", "lineage", "amr_gene", "location"], as_index=False).agg(isolates=("sample", "nunique"), resistance_rate=("observed_resistant", "mean"), mean_probability=("resistant_probability", "mean"), concordance=("concordant", "mean"), first_date=("date", "min"), last_date=("date", "max"))
        result["emergence_score"] = _minmax(result["isolates"]) * result["resistance_rate"].fillna(0) * (0.5 + 0.5 * result["mean_probability"])
        result["review_required"] = (result["concordance"] < 0.75) | (result["emergence_score"] >= threshold)
        result["priority_score"] = result["emergence_score"] * (0.5 + 0.5 * result["review_required"].astype(float))
        secondary = frame.groupby(["location", "species"], as_index=False).agg(isolates=("sample", "nunique"), resistance_rate=("observed_resistant", "mean"), genes=("amr_gene", "nunique"))
        monthly = frame.assign(month=pd.to_datetime(frame["date"], errors="coerce").dt.to_period("M").astype(str)).groupby(["month", "location", "species"], as_index=False).agg(isolates=("sample", "nunique"), resistance_rate=("observed_resistant", "mean"), concordance=("concordant", "mean"))
        confusion = frame.groupby(["phenotype", "predicted_resistant"], as_index=False).agg(isolates=("sample", "nunique"))
        extras["temporal_resistance_trends"] = monthly
        extras["phenotype_genotype_concordance"] = confusion
        extras["gene_species_matrix"] = frame.groupby(["species", "amr_gene"], as_index=False).agg(isolates=("sample", "nunique"), resistance_rate=("observed_resistant", "mean"), concordance=("concordant", "mean"))
        metrics = {"isolates": int(frame["sample"].nunique()), "signals": int(result["review_required"].sum()), "concordance": float(frame["concordant"].mean()), "lineages": int(frame["lineage"].nunique())}

    elif k == "spatial_medicine_tme":
        frame["expression"] = _numeric(frame["expression"], 0)
        cell_type_map = {"CD8 T": "immune", "Treg": "immune", "Macrophage": "immune", "Tumour": "tumour", "Fibroblast": "stroma", "Endothelial": "stroma"}
        frame["compartment"] = frame["cell_type"].map(cell_type_map).fillna("other")
        result = frame.groupby(["patient", "region", "compartment"], as_index=False).agg(spots=("gene", "count"), mean_expression=("expression", "mean"), cell_types=("cell_type", "nunique"))
        total = result.groupby(["patient", "region"])["spots"].transform("sum").replace(0, np.nan)
        result["fraction"] = result["spots"] / total
        pivot = result.pivot_table(index=["patient", "region"], columns="compartment", values="fraction", fill_value=0).reset_index()
        for col in ["immune", "tumour", "stroma"]:
            if col not in pivot.columns:
                pivot[col] = 0.0
        pivot["immune_exclusion_score"] = pivot["tumour"] * (1 - pivot["immune"])
        pivot["priority_score"] = pivot["immune_exclusion_score"] * (0.5 + 0.5 * pivot["stroma"])
        result = pivot.sort_values("priority_score", ascending=False)
        secondary = frame.groupby(["patient", "cell_type"], as_index=False).agg(spots=("gene", "count"), mean_expression=("expression", "mean"))
        extras["spatial_points"] = frame[["patient", "region", "cell_type", "gene", "expression", "x", "y", "compartment"]].copy()
        extras["gene_region_expression"] = frame.groupby(["gene", "region"], as_index=False).agg(mean_expression=("expression", "mean"), spots=("gene", "count"), patients=("patient", "nunique"))
        extras["compartment_composition"] = pivot.copy()
        metrics = {"patients": int(frame["patient"].nunique()), "cell_types": int(frame["cell_type"].nunique()), "regions": int(frame["region"].nunique()), "high_exclusion_regions": int((result["immune_exclusion_score"] >= threshold).sum())}

    elif k == "gene_therapy_vector":
        frame["cargo_bp"] = _numeric(frame["cargo_bp"], 0)
        for c in ["tropism_score", "immunogenicity_risk", "integration_risk"]:
            frame[c] = _numeric(frame[c], 0).clip(0, 1)
        limits = frame["vector_type"].map({"AAV": 4700, "Lentiviral": 9000, "Adenoviral": 30000, "Non-viral": 15000}).fillna(5000)
        frame["packaging_margin_bp"] = limits - frame["cargo_bp"]
        frame["packaging_pass"] = frame["packaging_margin_bp"] >= 0
        frame["safety_score"] = 0.45 * frame["tropism_score"] + 0.30 * (1 - frame["immunogenicity_risk"]) + 0.25 * (1 - frame["integration_risk"])
        frame["release_blocked"] = (~frame["packaging_pass"]) | (frame["immunogenicity_risk"] > 0.65) | (frame["integration_risk"] > 0.65)
        frame["priority_score"] = frame["safety_score"] * frame["packaging_pass"].astype(float) * (~frame["release_blocked"]).astype(float)
        result = frame.sort_values(["release_blocked", "priority_score"], ascending=[True, False])
        secondary = result.groupby("vector_type", as_index=False).agg(constructs=("construct", "count"), packaging_pass=("packaging_pass", "sum"), mean_safety=("safety_score", "mean"), blocked=("release_blocked", "sum"))
        extras["construct_capacity"] = result[["construct", "vector_type", "cargo_bp", "packaging_margin_bp", "packaging_pass", "promoter"]].copy()
        extras["promoter_vector_matrix"] = result.groupby(["vector_type", "promoter"], as_index=False).agg(constructs=("construct", "count"), mean_safety=("safety_score", "mean"), mean_tropism=("tropism_score", "mean"), blocked=("release_blocked", "sum"))
        extras["safety_risk_register"] = result[["construct", "vector_type", "immunogenicity_risk", "integration_risk", "release_blocked", "priority_score"]].copy()
        metrics = {"constructs": len(result), "packaging_failures": int((~result["packaging_pass"]).sum()), "blocked": int(result["release_blocked"].sum()), "promoters": int(result["promoter"].nunique())}

    elif k == "cell_therapy_cart":
        frame["scfv_affinity"] = _numeric(frame["scfv_affinity"], 0)
        for c in ["off_tumour_risk", "exhaustion_score", "manufacturability"]:
            frame[c] = _numeric(frame[c], 0).clip(0, 1)
        affinity_component = _minmax(frame["scfv_affinity"], higher_is_better=False)
        frame["engineering_score"] = 0.30 * affinity_component + 0.30 * frame["manufacturability"] + 0.20 * (1 - frame["off_tumour_risk"]) + 0.20 * (1 - frame["exhaustion_score"])
        frame["safety_review"] = (frame["off_tumour_risk"] > 0.45) | (frame["exhaustion_score"] > 0.65)
        frame["priority_score"] = frame["engineering_score"] * (~frame["safety_review"]).astype(float)
        result = frame.sort_values(["safety_review", "priority_score"], ascending=[True, False])
        secondary = result.groupby(["antigen", "costim_domain"], as_index=False).agg(constructs=("construct", "count"), mean_score=("engineering_score", "mean"), safety_reviews=("safety_review", "sum"), mean_manufacturability=("manufacturability", "mean"))
        extras["construct_score_components"] = result[["construct", "antigen", "costim_domain", "scfv_affinity", "off_tumour_risk", "exhaustion_score", "manufacturability", "engineering_score", "safety_review"]].copy()
        extras["antigen_domain_matrix"] = secondary.copy()
        metrics = {"constructs": len(result), "antigens": int(result["antigen"].nunique()), "safety_reviews": int(result["safety_review"].sum()), "costim_domains": int(result["costim_domain"].nunique())}

    elif k == "federated_biomedical_ai":
        for c in ["round", "samples", "metric_value", "drift_score", "privacy_epsilon"]:
            frame[c] = _numeric(frame[c], 0)
        weighted = frame.assign(weighted=frame["metric_value"] * frame["samples"]).groupby("round", as_index=False).agg(weighted_sum=("weighted", "sum"), samples=("samples", "sum"), mean_drift=("drift_score", "mean"), max_epsilon=("privacy_epsilon", "max"), sites=("site", "nunique"))
        weighted["global_metric"] = weighted["weighted_sum"] / weighted["samples"].replace(0, np.nan)
        weighted["privacy_risk"] = (weighted["max_epsilon"] / max(weighted["max_epsilon"].max(), 1)).clip(0, 1)
        weighted["priority_score"] = weighted["global_metric"] * (1 - weighted["mean_drift"].clip(0, 1)) * (1 - 0.25 * weighted["privacy_risk"])
        result = weighted.sort_values("round")
        secondary = frame.groupby("site", as_index=False).agg(rounds=("round", "nunique"), samples=("samples", "sum"), mean_metric=("metric_value", "mean"), mean_drift=("drift_score", "mean"), epsilon=("privacy_epsilon", "max"))
        secondary["site_outlier"] = (secondary["mean_metric"] - secondary["mean_metric"].median()).abs() > 0.08
        extras["site_round_metrics"] = frame[["site", "round", "samples", "metric", "metric_value", "drift_score", "privacy_epsilon"]].copy()
        extras["privacy_utility_frontier"] = result[["round", "global_metric", "mean_drift", "max_epsilon", "privacy_risk", "priority_score"]].copy()
        extras["site_outlier_review"] = secondary.copy()
        metrics = {"sites": int(frame["site"].nunique()), "rounds": int(frame["round"].nunique()), "site_outliers": int(secondary["site_outlier"].sum()), "max_privacy_epsilon": float(frame["privacy_epsilon"].max())}

    elif k == "clinical_biomarker_survival":
        frame["biomarker"] = _numeric(frame["biomarker"])
        frame["time"] = _numeric(frame["time"])
        frame["event"] = _numeric(frame["event"], 0)
        frame["response"] = _numeric(frame["response"], 0)
        cutoff = float(frame["biomarker"].median())
        frame["biomarker_group"] = np.where(frame["biomarker"] >= cutoff, "High", "Low")
        result = frame.groupby(["arm", "biomarker_group"], as_index=False).agg(patients=("patient", "count"), response_rate=("response", "mean"), median_time=("time", "median"), event_rate=("event", "mean"), sites=("site", "nunique"))
        result["clinical_utility_score"] = result["response_rate"] * (1 - result["event_rate"]) * _minmax(result["median_time"])
        result["priority_score"] = result["clinical_utility_score"]
        secondary = frame.groupby("site", as_index=False).agg(patients=("patient", "count"), response_rate=("response", "mean"), median_biomarker=("biomarker", "median"), event_rate=("event", "mean"))
        km = _kaplan_meier(frame, group_columns=["arm", "biomarker_group"])
        group_rates = frame.groupby(["arm", "biomarker_group"], as_index=False).agg(events=("event", "sum"), person_time=("time", "sum"), patients=("patient", "count"))
        group_rates["event_rate_per_time"] = group_rates["events"] / group_rates["person_time"].replace(0, np.nan)
        extras["kaplan_meier_curves"] = km
        extras["event_rate_summary"] = group_rates
        extras["patient_risk_waterfall"] = frame[["patient", "arm", "biomarker_group", "biomarker", "time", "event", "response", "site"]].sort_values("biomarker").copy()
        metrics = {"patients": int(frame["patient"].nunique()), "sites": int(frame["site"].nunique()), "biomarker_cutoff": cutoff, "events": int(frame["event"].sum())}

    elif k == "protein_ligand_codesign":
        for c in ["protein_score", "ligand_score", "interface_score", "selectivity_risk"]:
            frame[c] = _numeric(frame[c], 0).clip(0, 1)
        frame["joint_score"] = 0.30 * frame["protein_score"] + 0.25 * frame["ligand_score"] + 0.35 * frame["interface_score"] + 0.10 * (1 - frame["selectivity_risk"])
        frame["selectivity_review"] = frame["selectivity_risk"] > 0.5
        frame["pareto_like"] = (frame["protein_score"] >= frame["protein_score"].quantile(0.75)) & (frame["ligand_score"] >= frame["ligand_score"].quantile(0.75)) & (frame["interface_score"] >= frame["interface_score"].quantile(0.75))
        frame["priority_score"] = frame["joint_score"] * (~frame["selectivity_review"]).astype(float)
        result = frame.sort_values(["selectivity_review", "priority_score"], ascending=[True, False])
        secondary = result.groupby("protein_variant", as_index=False).agg(ligands=("ligand", "nunique"), best_score=("joint_score", "max"), pareto_candidates=("pareto_like", "sum"), selectivity_reviews=("selectivity_review", "sum"))
        extras["pareto_candidates"] = result.loc[result["pareto_like"]].copy()
        extras["variant_ligand_matrix"] = result[["protein_variant", "ligand", "joint_score", "interface_score", "selectivity_risk", "priority_score"]].copy()
        extras["score_components"] = result[["candidate", "protein_score", "ligand_score", "interface_score", "selectivity_risk", "joint_score"]].copy()
        metrics = {"candidates": len(result), "pareto_like": int(result["pareto_like"].sum()), "selectivity_reviews": int(result["selectivity_review"].sum()), "protein_variants": int(result["protein_variant"].nunique())}

    elif k == "pangenome_population_medicine":
        for c in ["allele_frequency", "clinical_weight", "reference_bias"]:
            frame[c] = _numeric(frame[c], 0).clip(0, 1)
        result = frame.groupby(["population", "variant", "path"], as_index=False).agg(samples=("sample", "nunique"), allele_frequency=("allele_frequency", "mean"), clinical_weight=("clinical_weight", "mean"), reference_bias=("reference_bias", "mean"))
        global_af = result.groupby("variant")["allele_frequency"].transform("mean")
        result["population_delta"] = (result["allele_frequency"] - global_af).abs()
        result["priority_score"] = result["population_delta"] * result["clinical_weight"] * (1 - result["reference_bias"])
        result["bias_review"] = result["reference_bias"] > 0.4
        secondary = result.groupby("population", as_index=False).agg(variants=("variant", "nunique"), mean_bias=("reference_bias", "mean"), population_specific=("population_delta", lambda s: int((_numeric(s) > 0.1).sum())), mean_clinical_weight=("clinical_weight", "mean"))
        extras["population_allele_matrix"] = result[["population", "variant", "path", "allele_frequency", "population_delta", "clinical_weight", "priority_score"]].copy()
        extras["reference_bias_audit"] = result[["population", "variant", "path", "reference_bias", "bias_review"]].copy()
        metrics = {"populations": int(result["population"].nunique()), "variants": int(result["variant"].nunique()), "bias_reviews": int(result["bias_review"].sum()), "paths": int(result["path"].nunique())}

    elif k == "pharmacovigilance_intelligence":
        frame["serious"] = _as_bool(frame["serious"])
        total_reports = max(len(frame), 1)
        rows = []
        for (drug, event), group in frame.groupby(["drug", "event"]):
            a = len(group)
            b = int((frame["drug"] == drug).sum()) - a
            c = int((frame["event"] == event).sum()) - a
            d = total_reports - a - b - c
            ror = ((a + 0.5) * (d + 0.5)) / ((b + 0.5) * (c + 0.5))
            se = math.sqrt(sum(1 / (x + 0.5) for x in [a, b, c, d]))
            lower = math.exp(math.log(ror) - 1.96 * se)
            prr = ((a + 0.5) / (a + b + 1.0)) / ((c + 0.5) / (c + d + 1.0))
            expected = ((a + b) * (a + c)) / max(total_reports, 1)
            information_component = math.log2((a + 0.5) / (expected + 0.5))
            rows.append({"drug": drug, "event": event, "reports": a, "serious_rate": float(group["serious"].mean()), "reporting_odds_ratio": ror, "ror_lower_95": lower, "proportional_reporting_ratio": prr, "information_component": information_component})
        result = pd.DataFrame(rows)
        result["signal_flag"] = (result["reports"] >= 3) & (result["ror_lower_95"] > 1)
        result["priority_score"] = _minmax(np.log1p(result["reporting_odds_ratio"])) * (0.5 + 0.5 * result["serious_rate"]) * result["signal_flag"].astype(float)
        result = result.sort_values(["signal_flag", "priority_score"], ascending=[False, False])
        secondary = frame.groupby("drug", as_index=False).agg(reports=("report_id", "count"), serious_rate=("serious", "mean"), events=("event", "nunique"))
        extras["drug_event_matrix"] = result[["drug", "event", "reports", "reporting_odds_ratio", "proportional_reporting_ratio", "information_component", "signal_flag"]].copy()
        extras["serious_outcome_summary"] = frame.groupby(["drug", "outcome"], as_index=False).agg(reports=("report_id", "count"), serious_rate=("serious", "mean"), events=("event", "nunique"))
        metrics = {"reports": len(frame), "signals": int(result["signal_flag"].sum()), "drugs": int(frame["drug"].nunique()), "events": int(frame["event"].nunique())}

    elif k == "synthetic_cohort_trial":
        for c in ["age", "baseline_risk", "outcome", "time", "event"]:
            frame[c] = _numeric(frame[c])
        arm = frame.groupby("arm", as_index=False).agg(patients=("patient", "count"), mean_age=("age", "mean"), mean_risk=("baseline_risk", "mean"), outcome_rate=("outcome", "mean"), median_time=("time", "median"), event_rate=("event", "mean"), sites=("site", "nunique"))
        if len(arm) >= 2:
            control = arm.iloc[0]
            treatment = arm.iloc[-1]
            risk_difference = float(treatment["outcome_rate"] - control["outcome_rate"])
        else:
            risk_difference = float("nan")
        arm["balance_score"] = 1 - (arm["mean_risk"] - frame["baseline_risk"].mean()).abs().clip(0, 1)
        arm["priority_score"] = arm["balance_score"] * (1 - arm["outcome_rate"].clip(0, 1))
        result = arm
        secondary = frame.groupby("site", as_index=False).agg(patients=("patient", "count"), mean_risk=("baseline_risk", "mean"), outcome_rate=("outcome", "mean"), arms=("arm", "nunique"))
        km = _kaplan_meier(frame, group_columns=["arm"])
        balance = _standardized_mean_difference(frame, arm_column="arm", numeric_columns=["age", "baseline_risk"])
        extras["kaplan_meier_curves"] = km
        extras["covariate_balance"] = balance
        extras["patient_level_simulation"] = frame[["patient", "arm", "age", "baseline_risk", "outcome", "time", "event", "site"]].copy()
        metrics = {"synthetic_patients": int(frame["patient"].nunique()), "sites": int(frame["site"].nunique()), "simulated_risk_difference": risk_difference, "imbalanced_covariates": int((~balance.get("balanced", pd.Series(dtype=bool))).sum()) if not balance.empty else 0}

    elif k == "autonomous_lab_planner":
        frame["replicates"] = _numeric(frame["replicates"], 0)
        frame["cost_per_run"] = _numeric(frame["cost_per_run"], 0)
        frame["total_cost"] = frame["replicates"] * frame["cost_per_run"]
        frame["control"] = _as_bool(frame["control"])
        frame["control_coverage"] = frame.groupby("hypothesis")["control"].transform("max").astype(bool)
        frame["replicate_score"] = (frame["replicates"] / 4).clip(0, 1)
        frame["design_completeness"] = 0.45 * frame["control_coverage"].astype(float) + 0.35 * frame["replicate_score"] + 0.20 * (frame["factor"].astype(str).str.len() > 0).astype(float)
        frame["review_required"] = (~frame["control_coverage"]) | (frame["replicates"] < 3)
        frame["priority_score"] = frame["design_completeness"] * (~frame["review_required"]).astype(float) * (1 - _minmax(frame["total_cost"]))
        result = frame.sort_values(["review_required", "priority_score"], ascending=[True, False])
        secondary = result.groupby("hypothesis", as_index=False).agg(experiments=("experiment_id", "count"), total_cost=("total_cost", "sum"), controls=("control", "sum"), mean_replicates=("replicates", "mean"), review_required=("review_required", "sum"))
        factor_matrix = result.groupby(["factor", "level"], as_index=False).agg(experiments=("experiment_id", "count"), controls=("control", "sum"), mean_replicates=("replicates", "mean"), total_cost=("total_cost", "sum"), review_required=("review_required", "sum"))
        result["estimated_hours"] = result["replicates"].clip(lower=1) * 1.5
        result["schedule_order"] = np.arange(1, len(result) + 1)
        extras["design_matrix"] = factor_matrix
        extras["resource_schedule"] = result[["schedule_order", "experiment_id", "hypothesis", "factor", "level", "replicates", "estimated_hours", "total_cost", "review_required"]].copy()
        extras["risk_register"] = result.loc[result["review_required"], ["experiment_id", "hypothesis", "control_coverage", "replicates", "total_cost", "review_required"]].copy()
        metrics = {"experiments": len(result), "total_cost": float(result["total_cost"].sum()), "review_required": int(result["review_required"].sum()), "factors": int(result["factor"].nunique())}

    else:
        raise KeyError(k)

    if "priority_score" in result.columns:
        result = result.sort_values("priority_score", ascending=False, na_position="last")
    summary = {
        "schema": "biointel.nextgen.scientific.v1",
        "module": module.key,
        "title": module.title,
        "input_records": int(len(frame)),
        "result_records": int(len(result)),
        "threshold": float(threshold),
        "missing_cells": int(frame.isna().sum().sum()),
        "duplicate_rows": int(frame.duplicated().sum()),
        "metrics": metrics,
        "advanced_table_count": len(extras),
        "scientific_boundary": module.boundary,
    }
    return result, summary, secondary, extras
