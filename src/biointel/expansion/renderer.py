from __future__ import annotations

import hashlib
import io
import json
import math
from dataclasses import asdict
from datetime import date, timedelta
from statistics import NormalDist
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from biointel.expansion.catalog import MODULE_BY_KEY, ExpansionModule
from biointel.expansion.advanced_analysis import enrich_analysis
from biointel.expansion.io_formats import read_scientific_upload, supported_extensions_for_module
from biointel.expansion.tool_adapters import serialisable_requirements, tool_status



# Shared workbench defaults to upload mode and preserves the Step 105 contract:
# ["Upload scientific data file", "Deterministic demonstration data"]
# Maximum 1 GB per file; files above 100 MB use protected staging.

def _seed(key: str) -> int:
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16)


def _rng(module: ExpansionModule) -> np.random.Generator:
    return np.random.default_rng(_seed(module.key))


def _read_table(upload: Any, module_key: str | None = None) -> pd.DataFrame:
    if module_key is None:
        # Backwards-compatible generic table import.
        raw = upload.getvalue()
        name = str(upload.name).lower()
        if name.endswith(".json"):
            payload = json.loads(raw.decode("utf-8"))
            if isinstance(payload, dict):
                payload = payload.get("records", payload.get("data", payload))
            return pd.DataFrame(payload)
        if name.endswith((".xlsx", ".xls")):
            return pd.read_excel(io.BytesIO(raw))
        text = raw.decode("utf-8-sig", errors="replace")
        separator = "\t" if name.endswith((".tsv", ".txt")) else ","
        try:
            return pd.read_csv(io.StringIO(text), sep=separator)
        except Exception:
            return pd.read_csv(io.StringIO(text), sep=None, engine="python")
    return read_scientific_upload(upload, module_key)


def _demo_frame(module: ExpansionModule, n: int = 96) -> pd.DataFrame:
    rng = _rng(module)
    k = module.key
    groups = np.array(["Control", "Treatment"])
    conditions = rng.choice(groups, size=n)

    if k == "epigenomics_chromatin":
        regions = [f"chr{1 + i % 6}:{100000 + i * 250}-{100180 + i * 250}" for i in range(24)]
        rows = []
        for sample_idx in range(12):
            condition = "Control" if sample_idx < 6 else "Treatment"
            for region_idx, region in enumerate(regions):
                effect = 1.7 if condition == "Treatment" and region_idx % 5 == 0 else 1.0
                rows.append({
                    "sample": f"ATAC_{sample_idx + 1:02d}", "region": region, "condition": condition,
                    "signal": max(0.05, rng.lognormal(2.2, 0.35) * effect),
                    "gc_content": np.clip(rng.normal(0.48, 0.08), 0.2, 0.8),
                    "methylation": np.clip(rng.normal(0.55 - (0.12 if effect > 1 else 0), 0.12), 0, 1),
                })
        return pd.DataFrame(rows)

    if k == "metabolomics_lipidomics":
        features = [f"M{100 + i:04d}" for i in range(32)]
        rows = []
        for sample_idx in range(16):
            group = "Control" if sample_idx < 8 else "Case"
            for feature_idx, feature in enumerate(features):
                effect = 2.0 if group == "Case" and feature_idx % 7 == 0 else 1.0
                base = rng.lognormal(8.0, 0.5) * effect
                rows.append({"sample": f"MS_{sample_idx + 1:02d}", "feature": feature, "group": group,
                             "intensity": base, "blank_intensity": base * rng.uniform(0.005, 0.08),
                             "annotation_confidence": rng.uniform(0.45, 0.99)})
        return pd.DataFrame(rows)

    if k == "immunoinformatics_vaccine":
        aa = np.array(list("ACDEFGHIKLMNPQRSTVWY"))
        alleles = ["HLA-A*02:01", "HLA-A*24:02", "HLA-B*07:02", "HLA-DRB1*04:01"]
        return pd.DataFrame({
            "peptide": ["".join(rng.choice(aa, size=9 if i % 2 == 0 else 15)) for i in range(n)],
            "allele": rng.choice(alleles, size=n),
            "binding_score": rng.uniform(0.35, 0.99, size=n),
            "immunogenicity": rng.uniform(0.2, 0.98, size=n),
            "conservancy": rng.uniform(0.4, 1.0, size=n),
            "toxicity_risk": rng.uniform(0.0, 0.35, size=n),
        })

    if k == "antibody_biologics":
        return pd.DataFrame({
            "variant": [f"AbV-{i + 1:03d}" for i in range(n)],
            "affinity": rng.lognormal(2.0, 0.45, size=n),
            "stability": rng.uniform(0.45, 0.99, size=n),
            "humanness": rng.uniform(0.55, 0.99, size=n),
            "aggregation_risk": rng.uniform(0.02, 0.55, size=n),
            "liability_count": rng.poisson(1.2, size=n),
        })

    if k == "docking_dynamics":
        ligands = [f"LIG-{i + 1:03d}" for i in range(max(12, n // 3))]
        rows = []
        for ligand in ligands:
            for pose in range(3):
                rows.append({"ligand": ligand, "pose": pose + 1, "docking_score": rng.normal(-8.2, 1.25),
                             "rmsd": abs(rng.normal(2.1, 1.0)), "hbond_occupancy": rng.uniform(0.1, 0.95),
                             "strain_energy": abs(rng.normal(3.0, 1.5))})
        return pd.DataFrame(rows)

    if k == "pharmacogenomics":
        genes = ["CYP2C19", "CYP2D6", "CYP2C9", "SLCO1B1", "TPMT", "DPYD"]
        drugs = ["clopidogrel", "codeine", "warfarin", "simvastatin", "thiopurine", "fluoropyrimidine"]
        phenotypes = ["Normal", "Intermediate", "Poor", "Rapid", "Indeterminate"]
        evidence = ["A", "B", "C", "D"]
        rows = []
        for i in range(n):
            idx = int(rng.integers(0, len(genes)))
            rows.append({"sample": f"PGX-{1 + i // 3:03d}", "gene": genes[idx], "variant": f"{genes[idx]}*{1 + int(rng.integers(1, 18))}",
                         "drug": drugs[idx], "phenotype": rng.choice(phenotypes, p=[0.42, 0.22, 0.14, 0.08, 0.14]),
                         "evidence_level": rng.choice(evidence, p=[0.36, 0.28, 0.22, 0.14])})
        return pd.DataFrame(rows)

    if k == "spatial_omics_pathology":
        spots = int(math.sqrt(n)) ** 2
        side = int(math.sqrt(spots))
        x, y = np.meshgrid(np.arange(side), np.arange(side))
        x = x.ravel(); y = y.ravel()
        region = np.where(x < side / 2, "Tumour-like ROI", "Stroma-like ROI")
        expression = rng.gamma(2.0, 2.0, size=spots) + np.where(region == "Tumour-like ROI", 3.2, 0.0)
        return pd.DataFrame({"spot": [f"SPOT-{i + 1:04d}" for i in range(spots)], "x": x, "y": y,
                             "region": region, "gene": rng.choice(["EPCAM", "COL1A1", "CD3D", "MKI67"], size=spots),
                             "expression": expression})

    if k == "single_cell_trajectory":
        pseudotime = np.sort(rng.uniform(0, 1, size=n))
        cluster = np.where(pseudotime < 0.33, "Progenitor", np.where(pseudotime < 0.7, "Intermediate", "Terminal"))
        return pd.DataFrame({"cell": [f"CELL-{i + 1:04d}" for i in range(n)], "cluster": cluster, "pseudotime": pseudotime,
                             "ligand": rng.choice(["TGFB1", "CXCL12", "IL6", "VEGFA"], size=n),
                             "receptor": rng.choice(["TGFBR1", "CXCR4", "IL6R", "KDR"], size=n),
                             "expression": rng.gamma(2.2, 1.8, size=n) * (0.7 + pseudotime)})

    if k == "bioimage_microscopy":
        return pd.DataFrame({"image_id": rng.choice([f"IMG-{i + 1:03d}" for i in range(12)], size=n),
                             "object_id": [f"OBJ-{i + 1:05d}" for i in range(n)],
                             "condition": conditions, "area": rng.lognormal(4.2, 0.35, size=n) * np.where(conditions == "Treatment", 1.15, 1.0),
                             "intensity": rng.lognormal(5.0, 0.4, size=n) * np.where(conditions == "Treatment", 1.3, 1.0),
                             "circularity": np.clip(rng.normal(0.72, 0.13, size=n), 0.1, 1.0)})

    if k == "biostatistics_design":
        return pd.DataFrame({"design": [f"Scenario {i + 1}" for i in range(12)], "effect_size": np.linspace(0.25, 0.8, 12),
                             "alpha": [0.05] * 12, "power": np.linspace(0.75, 0.95, 12),
                             "groups": rng.choice([2, 3, 4], size=12), "dropout_rate": np.linspace(0.0, 0.25, 12)})

    if k == "clinical_trial_biomarker":
        biomarker = rng.normal(0, 1, size=n)
        arm = rng.choice(["Control", "Treatment"], size=n)
        response_prob = 1 / (1 + np.exp(-(0.5 * biomarker + np.where(arm == "Treatment", 0.55, -0.15))))
        response = rng.binomial(1, response_prob)
        time = rng.exponential(12 / (1 + 0.25 * response_prob), size=n)
        event = rng.binomial(1, 0.68, size=n)
        return pd.DataFrame({"patient": [f"PT-{i + 1:04d}" for i in range(n)], "arm": arm,
                             "biomarker": biomarker, "response": response, "time": time, "event": event})

    if k == "genome_editing_safety":
        dna = np.array(list("ACGT"))
        return pd.DataFrame({"guide": ["".join(rng.choice(dna, size=20)) for _ in range(n)],
                             "on_target": rng.uniform(0.35, 0.98, size=n), "off_target_count": rng.poisson(4.0, size=n),
                             "max_mismatch": rng.integers(1, 6, size=n), "bulge_count": rng.poisson(0.7, size=n),
                             "snp_overlap": rng.binomial(1, 0.12, size=n)})

    if k == "proteogenomics_neoantigen":
        aa = np.array(list("ACDEFGHIKLMNPQRSTVWY"))
        return pd.DataFrame({"peptide": ["".join(rng.choice(aa, size=9)) for _ in range(n)],
                             "variant": [f"VAR-{i + 1:04d}" for i in range(n)], "expression": rng.lognormal(2.2, 0.7, size=n),
                             "spectral_score": rng.uniform(0.1, 0.99, size=n), "hla_binding": rng.uniform(0.15, 0.99, size=n),
                             "clonality": rng.uniform(0.05, 1.0, size=n)})

    if k == "bioprocess_fermentation":
        rows = []
        for batch in ["BATCH-A", "BATCH-B", "BATCH-C", "BATCH-D"]:
            for hour in range(0, 49, 2):
                growth = 1 / (1 + math.exp(-(hour - 20) / 5))
                rows.append({"batch": batch, "time": hour, "ph": 7.0 - 0.8 * growth + rng.normal(0, 0.05),
                             "temperature": 37 + rng.normal(0, 0.25), "dissolved_oxygen": max(3, 85 - 62 * growth + rng.normal(0, 3)),
                             "biomass": max(0, 18 * growth + rng.normal(0, 0.5)),
                             "product": max(0, 6.5 * max(0, growth - 0.25) + rng.normal(0, 0.18))})
        return pd.DataFrame(rows)

    if k == "lims_eln_chain":
        sample_ids = [f"SMP-{i + 1:04d}" for i in range(n)]
        parent = ["" if i < n // 3 else sample_ids[int(rng.integers(0, n // 3))] for i in range(n)]
        return pd.DataFrame({"sample_id": sample_ids, "parent_id": parent,
                             "status": rng.choice(["Received", "Processing", "Stored", "Consumed", "Quarantined"], size=n),
                             "location": rng.choice(["FZ-A/R1/B1", "FZ-A/R2/B3", "LN2/T1/R4", "FR-4C/S2"], size=n),
                             "freeze_thaw": rng.poisson(1.6, size=n), "days_to_expiry": rng.integers(-15, 365, size=n)})

    if k == "causal_perturbation":
        return pd.DataFrame({"exposure": rng.choice(["GeneA activity", "GeneB expression", "Metabolite C", "Pathway D"], size=n),
                             "outcome": rng.choice(["Cell viability", "Inflammation", "Drug response", "Disease score"], size=n),
                             "effect": rng.normal(0.05, 0.28, size=n), "standard_error": rng.uniform(0.04, 0.22, size=n),
                             "p_value": np.clip(rng.beta(0.7, 4.0, size=n), 1e-6, 1), "instrument_strength": rng.uniform(4, 45, size=n)})

    if k == "explainable_ai_assurance":
        truth = rng.binomial(1, 0.48, size=n)
        prediction = np.clip(0.18 + 0.62 * truth + rng.normal(0, 0.22, size=n), 0.01, 0.99)
        return pd.DataFrame({"sample": [f"PRED-{i + 1:04d}" for i in range(n)], "prediction": prediction, "truth": truth,
                             "uncertainty": np.clip(0.5 - abs(prediction - 0.5) + rng.normal(0, 0.07, size=n), 0.01, 0.95),
                             "feature_contribution": rng.normal(0, 0.35, size=n),
                             "subgroup": rng.choice(["Site A", "Site B", "Site C"], size=n)})

    if k == "multiomics_harmonization":
        features = [f"F{i + 1:03d}" for i in range(12)]
        rows = []
        for sample_idx in range(18):
            batch = "Batch-1" if sample_idx < 9 else "Batch-2"
            platform = "RNA" if sample_idx % 2 == 0 else "Protein"
            condition = "Control" if sample_idx < 9 else "Case"
            for feature_idx, feature in enumerate(features):
                batch_shift = 2.4 if batch == "Batch-2" else 0.0
                biological = 1.1 if condition == "Case" and feature_idx % 4 == 0 else 0.0
                rows.append({"sample": f"OM-{sample_idx + 1:03d}", "batch": batch, "platform": platform,
                             "feature": feature, "value": rng.normal(8 + batch_shift + biological, 0.8), "condition": condition})
        return pd.DataFrame(rows)

    if k == "glycomics_glycoproteomics":
        return pd.DataFrame({"glycopeptide": [f"GP-{i + 1:04d}" for i in range(n)],
                             "site": rng.choice(["N45", "N88", "N162", "N297", "O112"], size=n),
                             "glycan": rng.choice(["G0F", "G1F", "G2F", "High mannose", "Sialylated"], size=n),
                             "condition": conditions, "abundance": rng.lognormal(6.2, 0.55, size=n) * np.where(conditions == "Treatment", 1.25, 1.0),
                             "confidence": rng.uniform(0.35, 0.99, size=n)})

    if k == "one_health_environmental":
        start = date.today() - timedelta(days=120)
        return pd.DataFrame({"sample": [f"OH-{i + 1:04d}" for i in range(n)],
                             "date": [(start + timedelta(days=int(rng.integers(0, 121)))).isoformat() for _ in range(n)],
                             "host": rng.choice(["Human", "Livestock", "Wildlife", "Wastewater", "Surface water"], size=n),
                             "location": rng.choice(["North", "South", "East", "West"], size=n),
                             "pathogen": rng.choice(["Influenza A", "Salmonella", "E. coli", "SARS-like virus", "Campylobacter"], size=n),
                             "amr_genes": rng.poisson(1.4, size=n), "read_count": rng.lognormal(8.0, 1.1, size=n).astype(int)})

    if k == "synthetic_data_privacy":
        return pd.DataFrame({"record_id": [f"REC-{i + 1:05d}" for i in range(n)], "age": rng.integers(18, 86, size=n),
                             "category": rng.choice(["F", "M", "Other/Unknown"], size=n, p=[0.48, 0.48, 0.04]),
                             "diagnosis_group": rng.choice(["Group A", "Group B", "Group C", "Group D"], size=n),
                             "measurement": rng.normal(50, 14, size=n), "site": rng.choice(["Site 1", "Site 2", "Site 3"], size=n)})

    return pd.DataFrame(columns=module.columns)


def _normalise(frame: pd.DataFrame, module: ExpansionModule) -> pd.DataFrame:
    data = frame.copy()
    data.columns = [str(column).strip().lower().replace(" ", "_") for column in data.columns]
    expected = list(module.columns)
    missing = [column for column in expected if column not in data.columns]
    if missing:
        raise ValueError("Missing required column(s): " + ", ".join(missing))
    extras = [column for column in data.columns if column not in expected]
    data = data[expected + extras].copy()
    return data


def _safe_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _zscore(series: pd.Series) -> pd.Series:
    values = _safe_numeric(series)
    std = values.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(np.zeros(len(values)), index=values.index)
    return (values - values.mean()) / std


def _minmax(series: pd.Series, *, higher_is_better: bool = True) -> pd.Series:
    values = _safe_numeric(series)
    minimum, maximum = values.min(), values.max()
    if pd.isna(minimum) or pd.isna(maximum) or maximum == minimum:
        scaled = pd.Series(np.full(len(values), 0.5), index=values.index)
    else:
        scaled = (values - minimum) / (maximum - minimum)
    return scaled if higher_is_better else 1 - scaled


def _analyse_base(data: pd.DataFrame, module: ExpansionModule, threshold: float) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame | None]:
    k = module.key
    result = data.copy()
    secondary: pd.DataFrame | None = None

    if k == "epigenomics_chromatin":
        result["signal"] = _safe_numeric(result["signal"])
        pivot = result.pivot_table(index="region", columns="condition", values="signal", aggfunc="mean")
        columns = list(pivot.columns)
        if len(columns) >= 2:
            pivot["log2_fold_change"] = np.log2((pivot[columns[-1]] + 1e-6) / (pivot[columns[0]] + 1e-6))
        else:
            pivot["log2_fold_change"] = 0.0
        quality = result.groupby("region", as_index=True).agg(mean_gc=("gc_content", "mean"), mean_methylation=("methylation", "mean"), replicates=("sample", "nunique"))
        ranked = pivot.join(quality).reset_index()
        ranked["priority_score"] = abs(ranked["log2_fold_change"]) * np.minimum(1.0, ranked["replicates"] / 6)
        result = ranked.sort_values("priority_score", ascending=False)

    elif k == "metabolomics_lipidomics":
        for column in ["intensity", "blank_intensity", "annotation_confidence"]:
            result[column] = _safe_numeric(result[column])
        grouped = result.groupby(["feature", "group"], as_index=False)["intensity"].mean()
        pivot = grouped.pivot(index="feature", columns="group", values="intensity")
        columns = list(pivot.columns)
        pivot["log2_fold_change"] = np.log2((pivot[columns[-1]] + 1) / (pivot[columns[0]] + 1)) if len(columns) >= 2 else 0
        quality = result.groupby("feature").agg(mean_intensity=("intensity", "mean"), blank_ratio=("blank_intensity", lambda x: float(x.mean())), annotation_confidence=("annotation_confidence", "mean"), cv=("intensity", lambda x: float(x.std() / max(x.mean(), 1e-9)))).reset_index()
        quality["blank_ratio"] = quality["blank_ratio"] / quality["mean_intensity"].clip(lower=1e-9)
        result = pivot.reset_index().merge(quality, on="feature")
        result["priority_score"] = abs(result["log2_fold_change"]) * result["annotation_confidence"] * (1 - result["blank_ratio"].clip(0, 1)) * (1 - result["cv"].clip(0, 1))
        result = result.sort_values("priority_score", ascending=False)

    elif k == "immunoinformatics_vaccine":
        for column in ["binding_score", "immunogenicity", "conservancy", "toxicity_risk"]:
            result[column] = _safe_numeric(result[column])
        result["priority_score"] = 0.35 * result["binding_score"] + 0.30 * result["immunogenicity"] + 0.25 * result["conservancy"] + 0.10 * (1 - result["toxicity_risk"].clip(0, 1))
        result["passes_safety_screen"] = result["toxicity_risk"] <= (1 - threshold) * 0.8
        result = result.sort_values(["passes_safety_screen", "priority_score"], ascending=[False, False])
        secondary = result.groupby("allele", as_index=False).agg(candidates=("peptide", "count"), mean_score=("priority_score", "mean"), safe_candidates=("passes_safety_screen", "sum"))

    elif k == "antibody_biologics":
        result["priority_score"] = (0.30 * _minmax(result["affinity"]) + 0.25 * _minmax(result["stability"]) + 0.20 * _minmax(result["humanness"]) + 0.15 * _minmax(result["aggregation_risk"], higher_is_better=False) + 0.10 * _minmax(result["liability_count"], higher_is_better=False))
        result["developability_flag"] = (result["aggregation_risk"].astype(float) > 0.35) | (result["liability_count"].astype(float) >= 3)
        result = result.sort_values(["developability_flag", "priority_score"], ascending=[True, False])

    elif k == "docking_dynamics":
        result["priority_score"] = (0.35 * _minmax(result["docking_score"], higher_is_better=False) + 0.25 * _minmax(result["rmsd"], higher_is_better=False) + 0.25 * _minmax(result["hbond_occupancy"]) + 0.15 * _minmax(result["strain_energy"], higher_is_better=False))
        result = result.sort_values("priority_score", ascending=False)
        secondary = result.groupby("ligand", as_index=False).agg(best_score=("priority_score", "max"), best_docking=("docking_score", "min"), median_rmsd=("rmsd", "median"))

    elif k == "pharmacogenomics":
        evidence_map = {"A": 4, "B": 3, "C": 2, "D": 1}
        phenotype_risk = {"Poor": 3, "Rapid": 3, "Intermediate": 2, "Indeterminate": 2, "Normal": 0}
        result["evidence_score"] = result["evidence_level"].astype(str).str.upper().map(evidence_map).fillna(0)
        result["phenotype_risk"] = result["phenotype"].astype(str).map(phenotype_risk).fillna(1)
        result["review_priority"] = result["evidence_score"] * result["phenotype_risk"]
        result["review_required"] = result["review_priority"] >= max(3, round(threshold * 8))
        result = result.sort_values(["review_required", "review_priority"], ascending=[False, False])
        secondary = result.groupby(["gene", "drug"], as_index=False).agg(records=("sample", "count"), review_required=("review_required", "sum"), strongest_evidence=("evidence_score", "max"))

    elif k == "spatial_omics_pathology":
        result["expression"] = _safe_numeric(result["expression"])
        region_mean = result.groupby("region")["expression"].transform("mean")
        result["regional_enrichment"] = result["expression"] - region_mean
        result["priority_score"] = _minmax(abs(result["regional_enrichment"]))
        result = result.sort_values("priority_score", ascending=False)
        secondary = result.groupby(["region", "gene"], as_index=False).agg(mean_expression=("expression", "mean"), spots=("spot", "count"))

    elif k == "single_cell_trajectory":
        result["communication_score"] = _minmax(result["expression"]) * (0.5 + 0.5 * _minmax(result["pseudotime"]))
        result["state"] = pd.cut(_safe_numeric(result["pseudotime"]), bins=[-np.inf, 0.33, 0.7, np.inf], labels=["Early", "Intermediate", "Late"])
        result = result.sort_values("communication_score", ascending=False)
        secondary = result.groupby(["cluster", "ligand", "receptor"], as_index=False).agg(mean_score=("communication_score", "mean"), cells=("cell", "count"))

    elif k == "bioimage_microscopy":
        result["morphology_score"] = 0.4 * _minmax(result["area"]) + 0.4 * _minmax(result["intensity"]) + 0.2 * _minmax(result["circularity"])
        result["outlier_score"] = abs(_zscore(result["area"])) + abs(_zscore(result["intensity"])) + abs(_zscore(result["circularity"]))
        result["quality_flag"] = result["outlier_score"] > (2.5 + threshold)
        result = result.sort_values("outlier_score", ascending=False)
        secondary = result.groupby("condition", as_index=False).agg(objects=("object_id", "count"), mean_area=("area", "mean"), mean_intensity=("intensity", "mean"), mean_circularity=("circularity", "mean"))

    elif k == "biostatistics_design":
        alpha = _safe_numeric(result["alpha"]).clip(1e-6, 0.2)
        power = _safe_numeric(result["power"]).clip(0.51, 0.999)
        effect = _safe_numeric(result["effect_size"]).abs().clip(lower=1e-4)
        groups = _safe_numeric(result["groups"]).clip(lower=2)
        dropout = _safe_numeric(result["dropout_rate"]).clip(0, 0.8)
        z_alpha = alpha.map(lambda a: NormalDist().inv_cdf(1 - a / 2))
        z_power = power.map(lambda p: NormalDist().inv_cdf(p))
        n_per_group = 2 * ((z_alpha + z_power) / effect) ** 2
        result["n_per_group_raw"] = np.ceil(n_per_group).astype(int)
        result["n_per_group_with_dropout"] = np.ceil(n_per_group / (1 - dropout)).astype(int)
        result["total_sample_size"] = (result["n_per_group_with_dropout"] * groups).astype(int)
        result["feasibility_score"] = _minmax(result["total_sample_size"], higher_is_better=False)
        result = result.sort_values("total_sample_size")

    elif k == "clinical_trial_biomarker":
        result["biomarker_group"] = pd.qcut(_safe_numeric(result["biomarker"]), q=2, labels=["Low", "High"], duplicates="drop")
        secondary = result.groupby(["arm", "biomarker_group"], observed=False, as_index=False).agg(patients=("patient", "count"), response_rate=("response", "mean"), median_time=("time", "median"), event_rate=("event", "mean"))
        result["priority_score"] = _minmax(abs(_zscore(result["biomarker"]))) * (0.5 + 0.5 * _safe_numeric(result["response"]))
        result = result.sort_values("priority_score", ascending=False)

    elif k == "genome_editing_safety":
        result["safety_score"] = 0.45 * _minmax(result["on_target"]) + 0.25 * _minmax(result["off_target_count"], higher_is_better=False) + 0.10 * _minmax(result["max_mismatch"]) + 0.10 * _minmax(result["bulge_count"], higher_is_better=False) + 0.10 * _minmax(result["snp_overlap"], higher_is_better=False)
        result["high_risk"] = (_safe_numeric(result["off_target_count"]) > 6) | (_safe_numeric(result["bulge_count"]) > 1) | (_safe_numeric(result["snp_overlap"]) > 0)
        result = result.sort_values(["high_risk", "safety_score"], ascending=[True, False])

    elif k == "proteogenomics_neoantigen":
        result["priority_score"] = 0.20 * _minmax(result["expression"]) + 0.30 * _minmax(result["spectral_score"]) + 0.30 * _minmax(result["hla_binding"]) + 0.20 * _minmax(result["clonality"])
        result["multi_layer_support"] = ((_safe_numeric(result["spectral_score"]) >= threshold) & (_safe_numeric(result["hla_binding"]) >= threshold) & (_safe_numeric(result["clonality"]) >= threshold * 0.7))
        result = result.sort_values(["multi_layer_support", "priority_score"], ascending=[False, False])

    elif k == "bioprocess_fermentation":
        result["yield"] = _safe_numeric(result["product"]) / _safe_numeric(result["biomass"]).clip(lower=1e-6)
        for column in ["ph", "temperature", "dissolved_oxygen"]:
            result[f"{column}_z"] = _zscore(result[column])
        result["deviation_score"] = abs(result["ph_z"]) + abs(result["temperature_z"]) + abs(result["dissolved_oxygen_z"])
        result["deviation_flag"] = result["deviation_score"] > (3.0 + threshold)
        secondary = result.groupby("batch", as_index=False).agg(max_biomass=("biomass", "max"), max_product=("product", "max"), mean_yield=("yield", "mean"), deviations=("deviation_flag", "sum"))
        result = result.sort_values(["deviation_flag", "deviation_score"], ascending=[False, False])

    elif k == "lims_eln_chain":
        result["freeze_thaw"] = _safe_numeric(result["freeze_thaw"]).fillna(0)
        result["days_to_expiry"] = _safe_numeric(result["days_to_expiry"])
        result["custody_risk"] = (result["status"].astype(str).str.lower() == "quarantined").astype(int) * 3 + (result["freeze_thaw"] >= 3).astype(int) * 2 + (result["days_to_expiry"] <= 30).astype(int) * 2 + (result["location"].astype(str).str.strip() == "").astype(int) * 2
        result["alert"] = result["custody_risk"] >= max(2, round(threshold * 5))
        result = result.sort_values(["alert", "custody_risk"], ascending=[False, False])
        secondary = result.groupby("status", as_index=False).agg(samples=("sample_id", "count"), alerts=("alert", "sum"), median_freeze_thaw=("freeze_thaw", "median"))

    elif k == "causal_perturbation":
        result["z_score"] = _safe_numeric(result["effect"]) / _safe_numeric(result["standard_error"]).clip(lower=1e-9)
        result["precision"] = 1 / (_safe_numeric(result["standard_error"]).clip(lower=1e-9) ** 2)
        result["strength_flag"] = _safe_numeric(result["instrument_strength"]) < 10
        result["priority_score"] = _minmax(abs(result["z_score"])) * _minmax(result["instrument_strength"]) * _minmax(result["p_value"], higher_is_better=False)
        result = result.sort_values(["strength_flag", "priority_score"], ascending=[True, False])

    elif k == "explainable_ai_assurance":
        prediction = _safe_numeric(result["prediction"]).clip(0, 1)
        truth = _safe_numeric(result["truth"]).clip(0, 1)
        result["absolute_error"] = abs(prediction - truth)
        result["predicted_class"] = (prediction >= 0.5).astype(int)
        result["correct"] = result["predicted_class"] == truth.astype(int)
        result["risk_score"] = 0.65 * result["absolute_error"] + 0.35 * _safe_numeric(result["uncertainty"]).clip(0, 1)
        result = result.sort_values("risk_score", ascending=False)
        secondary = result.groupby("subgroup", as_index=False).agg(records=("sample", "count"), accuracy=("correct", "mean"), mean_error=("absolute_error", "mean"), mean_uncertainty=("uncertainty", "mean"))

    elif k == "multiomics_harmonization":
        result["value"] = _safe_numeric(result["value"])
        batch_feature_mean = result.groupby(["feature", "batch"])["value"].transform("mean")
        feature_global_mean = result.groupby("feature")["value"].transform("mean")
        result["harmonized_value"] = result["value"] - batch_feature_mean + feature_global_mean
        result["correction_delta"] = result["harmonized_value"] - result["value"]
        result["large_correction"] = abs(result["correction_delta"]) > (result["value"].std(ddof=0) * (0.5 + threshold))
        secondary = result.groupby(["batch", "platform"], as_index=False).agg(records=("sample", "count"), raw_mean=("value", "mean"), harmonized_mean=("harmonized_value", "mean"), mean_abs_correction=("correction_delta", lambda x: float(abs(x).mean())))
        result = result.sort_values("correction_delta", key=lambda x: abs(x), ascending=False)

    elif k == "glycomics_glycoproteomics":
        result["abundance"] = _safe_numeric(result["abundance"])
        group_means = result.groupby(["glycan", "condition"], as_index=False)["abundance"].mean()
        pivot = group_means.pivot(index="glycan", columns="condition", values="abundance")
        columns = list(pivot.columns)
        pivot["log2_fold_change"] = np.log2((pivot[columns[-1]] + 1) / (pivot[columns[0]] + 1)) if len(columns) >= 2 else 0
        secondary = pivot.reset_index()
        result["priority_score"] = _minmax(result["abundance"]) * _safe_numeric(result["confidence"]).clip(0, 1)
        result = result.sort_values("priority_score", ascending=False)

    elif k == "one_health_environmental":
        result["date"] = pd.to_datetime(result["date"], errors="coerce")
        result["read_count"] = _safe_numeric(result["read_count"]).fillna(0)
        result["amr_genes"] = _safe_numeric(result["amr_genes"]).fillna(0)
        result["surveillance_score"] = _minmax(np.log1p(result["read_count"])) * 0.65 + _minmax(result["amr_genes"]) * 0.35
        result["alert"] = result["surveillance_score"] >= threshold
        secondary = result.groupby(["location", "host", "pathogen"], as_index=False).agg(samples=("sample", "count"), total_reads=("read_count", "sum"), mean_amr=("amr_genes", "mean"), alerts=("alert", "sum"))
        result = result.sort_values(["alert", "surveillance_score"], ascending=[False, False])

    elif k == "synthetic_data_privacy":
        rng = _rng(module)
        result["age"] = _safe_numeric(result["age"])
        result["measurement"] = _safe_numeric(result["measurement"])
        synthetic = result.sample(n=len(result), replace=True, random_state=_seed(module.key)).reset_index(drop=True)
        noise_scale = max(0.25, (1 - threshold) * 5)
        synthetic["age"] = np.clip(np.round(synthetic["age"] + rng.normal(0, noise_scale, len(synthetic))), 0, 110).astype(int)
        synthetic["measurement"] = synthetic["measurement"] + rng.normal(0, noise_scale * 1.5, len(synthetic))
        synthetic["record_id"] = [f"SYN-{i + 1:06d}" for i in range(len(synthetic))]
        quasi = ["age", "category", "site"]
        group_size = synthetic.groupby(quasi)["record_id"].transform("count")
        synthetic["equivalence_class_size"] = group_size
        synthetic["privacy_flag"] = group_size < 3
        result = synthetic.sort_values(["privacy_flag", "equivalence_class_size"], ascending=[False, True])
        secondary = pd.DataFrame({
            "metric": ["source_age_mean", "synthetic_age_mean", "source_measurement_mean", "synthetic_measurement_mean", "unique_quasi_identifier_rate"],
            "value": [float(data["age"].astype(float).mean()), float(synthetic["age"].mean()), float(data["measurement"].astype(float).mean()), float(synthetic["measurement"].mean()), float((group_size == 1).mean())],
        })

    else:
        result["priority_score"] = 0.5

    score_columns = [column for column in result.columns if column.endswith("score") or column in {"priority_score", "review_priority", "safety_score", "surveillance_score"}]
    primary_score = score_columns[0] if score_columns else None
    summary = {
        "module": module.title,
        "input_records": int(len(data)),
        "result_records": int(len(result)),
        "missing_cells": int(data.isna().sum().sum()),
        "duplicate_rows": int(data.duplicated().sum()),
        "threshold": float(threshold),
        "primary_score": primary_score,
        "top_score": float(pd.to_numeric(result[primary_score], errors="coerce").max()) if primary_score else None,
    }
    for flag in [column for column in result.columns if result[column].dtype == bool]:
        summary[f"{flag}_count"] = int(result[flag].sum())
    return result, summary, secondary


def _analyse_detailed(
    data: pd.DataFrame, module: ExpansionModule, threshold: float
) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame | None, dict[str, pd.DataFrame]]:
    result, summary, secondary = _analyse_base(data, module, threshold)
    result, secondary, advanced_metrics, extra_tables = enrich_analysis(
        data, result, secondary, module.key, threshold
    )
    summary.update(advanced_metrics)
    summary["result_records"] = int(len(result))
    score_columns = [
        column for column in result.columns
        if column.endswith("score") or column in {
            "priority_score", "priority_score_advanced", "review_priority",
            "safety_score", "safety_score_advanced", "surveillance_score"
        }
    ]
    if score_columns:
        summary["primary_score"] = score_columns[0]
        summary["top_score"] = float(pd.to_numeric(result[score_columns[0]], errors="coerce").max())
    summary["advanced_table_count"] = len(extra_tables)
    return result, summary, secondary, extra_tables


def _analyse(
    data: pd.DataFrame, module: ExpansionModule, threshold: float
) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame | None]:
    result, summary, secondary, _ = _analyse_detailed(data, module, threshold)
    return result, summary, secondary


def _overview_chart(
    data: pd.DataFrame,
    result: pd.DataFrame,
    module: ExpansionModule,
    secondary: pd.DataFrame | None = None,
    extras: dict[str, pd.DataFrame] | None = None,
) -> None:
    from biointel.ui.scientific_visuals import render_scientific_visual_suite

    render_scientific_visual_suite(
        module.key,
        data=data,
        result=result,
        secondary=secondary,
        extras=extras,
        key=f"exp_visuals_{module.key}",
    )

def render_expansion_module(module_key: str) -> None:
    import streamlit as st

    from biointel.expansion.utilities import render_module_utility
    from biointel.scientific_depth import assess_evidence_readiness, profile_for, render_depth_upgrade_panel
    from biointel.ui.components import smart_dataframe, smart_json
    from biointel.ui.theme import section_title
    from biointel.ui.workbench import (
        apply_analysis_filters,
        compact_module_header,
        render_analysis_controls,
        render_column_mapping,
        render_data_readiness,
        render_export_panel,
        render_results_workbench,
        render_source_selector,
        run_analysis_once,
    )

    module = MODULE_BY_KEY[module_key]
    root = Path(__file__).resolve().parents[3]
    compact_module_header(
        title=module.title,
        summary=module.summary,
        icon=module.icon,
        category=module.category,
        tags=("Scientific import", "Cached analysis", "Auditable export"),
        boundary=module.boundary,
    )

    has_depth = profile_for(module.key) is not None
    labels = ["1 · Prepare & run", "2 · Explore results", "3 · Export"]
    if has_depth:
        labels.append("4 · Scientific depth")
    labels.append("5 · Guide & utilities" if has_depth else "4 · Guide & utilities")
    tabs = st.tabs(labels)
    tab_prepare, tab_results, tab_export = tabs[:3]
    if has_depth:
        tab_depth, tab_guide = tabs[3], tabs[4]
    else:
        tab_depth, tab_guide = None, tabs[3]

    with tab_prepare:
        section_title("Prepare data and run analysis", "▤")
        source = render_source_selector(
            key=f"wb_{module.key}",
            module_key=module.key,
            extensions=supported_extensions_for_module(module.key),
            required_columns=module.columns,
            project_root=root,
            demo_min=48,
            demo_max=240,
            demo_default=96,
            demo_step=24,
        )
        raw = pd.DataFrame(columns=module.columns)
        if source.mode == "demo":
            raw = _demo_frame(module, source.demo_size)
        elif source.upload is not None and not source.is_large_upload:
            try:
                raw = _read_table(source.upload, module.key)
            except Exception as exc:
                st.error(f"Input validation failed: {exc}")
        elif source.is_large_upload:
            st.info("The file is in large-file mode. Stage it locally, then use the Background Job Center for bounded processing.")

        raw = render_column_mapping(raw, module.columns, key=f"wb_{module.key}") if not raw.empty else raw
        try:
            data = _normalise(raw, module) if not raw.empty else raw
        except Exception as exc:
            st.error(f"Schema normalisation failed safely: {exc}")
            data = pd.DataFrame(columns=module.columns)

        readiness = render_data_readiness(data, module.columns, key=f"wb_{module.key}")
        if not data.empty:
            with st.expander("Preview imported records", expanded=True):
                smart_dataframe(data.head(500), height=360, key=f"wb_{module.key}_preview")

        st.markdown("#### Analysis configuration")
        parameters = render_analysis_controls(data, module_key=module.key, key=f"wb_{module.key}")
        filtered_data = apply_analysis_filters(data, parameters)
        if len(filtered_data) != len(data):
            st.caption(f"Advanced filters retain {len(filtered_data):,} of {len(data):,} records.")
        if readiness["missing_required"]:
            st.warning("Map or repair the required fields before relying on the analysis result.")

        run_state = run_analysis_once(
            state_key=f"wb_{module.key}_run_state",
            data=data,
            parameters=parameters,
            analyser=lambda frame, threshold: _analyse_detailed(frame, module, threshold),
        )
        if run_state is not None:
            smart_json(
                run_state.summary,
                title="Current run summary",
                download_name=f"{module.key}_analysis_summary.json",
                key=f"wb_{module.key}_summary",
            )

    with tab_results:
        section_title("Explore current results", "📊")
        render_results_workbench(
            run_state=run_state,
            key=f"wb_{module.key}",
            chart_renderer=lambda result, secondary, extras: _overview_chart(
                apply_analysis_filters(data, run_state.parameters) if run_state is not None else data,
                result,
                module,
                secondary,
                extras,
            ),
            boundary=module.boundary,
        )

    with tab_export:
        section_title("Reproducible result package", "📦")
        manifest = None
        if run_state is not None:
            depth_profile = profile_for(module.key)
            readiness_report = assess_evidence_readiness(
                module.key,
                data,
                required_columns=module.columns,
                profile_references=depth_profile.references if depth_profile else (),
                profile_validations=depth_profile.validations if depth_profile else (),
                source_mode=source.mode,
                run_summary=run_state.summary,
            )
            manifest = {
                "schema": "biointel.scientific_expansion.v4",
                "module": asdict(module),
                "configuration": run_state.parameters,
                "completed_at_utc": run_state.completed_at_utc,
                "summary": run_state.summary,
                "input_profile": {
                    "rows": len(data),
                    "columns": list(data.columns),
                    "missing_cells": int(data.isna().sum().sum()) if not data.empty else 0,
                    "duplicate_rows": int(data.astype(str).duplicated().sum()) if not data.empty else 0,
                },
                "scientific_boundary": module.boundary,
                "workflow": list(module.workflow),
                "optional_external_tools": serialisable_requirements(module.key),
                "scientific_readiness": readiness_report.manifest,
            }
        render_export_panel(
            module_key=module.key,
            run_state=run_state,
            manifest=manifest,
            key=f"wb_{module.key}",
        )

    if tab_depth is not None:
        with tab_depth:
            render_depth_upgrade_panel(
                module.key,
                data,
                key_prefix=f"wb_depth_{module.key}",
                expanded=True,
                source_mode=source.mode,
                run_summary=run_state.summary if run_state is not None else None,
            )

    with tab_guide:
        guide_tab, utility_tab = st.tabs(["Operating guide", "Advanced utilities"])
        with guide_tab:
            section_title("Purpose and operating guide", "📘")
            st.markdown(f"**Purpose:** {module.purpose}")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Accepted inputs**")
                for item in module.accepted_inputs:
                    st.markdown(f"- {item}")
            with c2:
                st.markdown("**Generated outputs**")
                for item in module.outputs:
                    st.markdown(f"- {item}")
            st.markdown("**Recommended workflow**")
            for index, step in enumerate(module.workflow, start=1):
                st.markdown(f"{index}. {step}")
            readiness_tools = tool_status(module.key)
            if not readiness_tools.empty:
                with st.expander("Optional specialist-tool readiness", expanded=False):
                    st.caption("External programs are never silently presented as bundled or executed.")
                    smart_dataframe(readiness_tools, height=260, key=f"wb_{module.key}_tools")
        with utility_tab:
            render_module_utility(module, data, root)

