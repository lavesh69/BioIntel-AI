from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image
from scipy import ndimage, stats

from .catalog import MODULE_BY_KEY, NextGenModule
from .biomedical_expansion import NEW_BIOMEDICAL_KEYS, analyse as analyse_biomedical, demo_frame as demo_biomedical_frame

def _seed(key: str) -> int:
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16)


def _rng(key: str) -> np.random.Generator:
    return np.random.default_rng(_seed(key))


def bh_adjust(values: pd.Series) -> pd.Series:
    p = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    result = np.full(len(p), np.nan, dtype=float)
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


def _numeric(series: pd.Series, fill: float | None = None) -> pd.Series:
    out = pd.to_numeric(series, errors="coerce")
    return out.fillna(fill) if fill is not None else out


def _safe_welch(a: pd.Series, b: pd.Series) -> float:
    aa = _numeric(a).dropna().to_numpy(dtype=float)
    bb = _numeric(b).dropna().to_numpy(dtype=float)
    if len(aa) < 2 or len(bb) < 2:
        return float("nan")
    return float(stats.ttest_ind(aa, bb, equal_var=False, nan_policy="omit").pvalue)


def _cohen_d(a: pd.Series, b: pd.Series) -> float:
    aa = _numeric(a).dropna().to_numpy(dtype=float)
    bb = _numeric(b).dropna().to_numpy(dtype=float)
    if len(aa) < 2 or len(bb) < 2:
        return float("nan")
    pooled = math.sqrt(((len(aa) - 1) * np.var(aa, ddof=1) + (len(bb) - 1) * np.var(bb, ddof=1)) / max(len(aa) + len(bb) - 2, 1))
    return float((np.mean(bb) - np.mean(aa)) / pooled) if pooled > 0 else 0.0


from .scientific_io import read_upload


def demo_frame(module: NextGenModule, n: int = 120) -> pd.DataFrame:
    if module.key in NEW_BIOMEDICAL_KEYS:
        return demo_biomedical_frame(module, n)
    rng = _rng(module.key)
    key = module.key
    if key == "population_gwas":
        samples = [f"S{i + 1:04d}" for i in range(max(40, n // 3))]
        variants = [(str(1 + i % 6), 100_000 + i * 10_000, f"rs{10000 + i}") for i in range(40)]
        phenotype_map = {s: rng.binomial(1, 0.45) for s in samples}
        rows = []
        for vi, (chrom, pos, variant) in enumerate(variants):
            maf = rng.uniform(0.05, 0.45)
            for sample in samples:
                pheno = phenotype_map[sample]
                p = np.clip(maf + (0.12 if vi % 13 == 0 and pheno == 1 else 0), 0.01, 0.49)
                gt = rng.binomial(2, p)
                rows.append({"sample": sample, "variant": variant, "chrom": chrom, "position": pos, "genotype": gt, "phenotype": pheno, "age": rng.normal(52, 12), "sex": rng.choice([0, 1])})
        return pd.DataFrame(rows)
    if key == "structural_variant_repeat":
        svtypes = ["DEL", "DUP", "INV", "BND", "STR"]
        rows = []
        for i in range(n):
            start = int(rng.integers(50_000, 80_000_000)); length = int(rng.lognormal(9.5, 1.1))
            rows.append({"sample": f"SVS-{i % 24 + 1:03d}", "sv_id": f"SV-{i + 1:05d}", "chrom": str(rng.integers(1, 23)), "start": start, "end": start + length, "sv_type": rng.choice(svtypes), "support": int(rng.integers(2, 50)), "caller": rng.choice(["caller_a", "caller_b", "caller_c"]), "gene": rng.choice(["GENE1", "GENE2", "GENE3", "INTERGENIC"]), "quality": rng.uniform(10, 99)})
        return pd.DataFrame(rows)
    if key == "longitudinal_multiomics":
        rows = []
        features = [f"F{i + 1:03d}" for i in range(20)]
        for subject_idx in range(24):
            group = "Treatment" if subject_idx >= 12 else "Control"
            for time in [0, 1, 3, 6, 12]:
                if rng.random() < 0.08:
                    continue
                for fi, feature in enumerate(features):
                    slope = 0.18 if group == "Treatment" and fi % 7 == 0 else rng.normal(0, 0.03)
                    rows.append({"subject": f"P{subject_idx + 1:03d}", "time": time, "feature": feature, "omics_layer": rng.choice(["RNA", "Protein", "Metabolite"]), "value": rng.normal(5 + slope * time, 0.5), "group": group})
        return pd.DataFrame(rows)
    if key == "rna_isoform_splicing":
        rows = []
        for sample_idx in range(20):
            group = "Case" if sample_idx >= 10 else "Control"
            for gene_idx in range(12):
                for iso in range(3):
                    switch = 1.8 if group == "Case" and gene_idx % 5 == 0 and iso == 1 else 1.0
                    rows.append({"sample": f"RNA-{sample_idx + 1:03d}", "gene": f"GENE{gene_idx + 1:03d}", "transcript": f"TX{gene_idx + 1:03d}.{iso + 1}", "group": group, "abundance": rng.lognormal(3.0, 0.45) * switch, "junction_support": int(rng.integers(3, 100))})
        return pd.DataFrame(rows)
    if key == "epitranscriptomics":
        rows = []
        sites = [f"chr{1 + i % 4}:{10_000 + i * 123}:A>G" for i in range(30)]
        for sample_idx in range(16):
            condition = "Treatment" if sample_idx >= 8 else "Control"
            for si, site in enumerate(sites):
                shift = 0.2 if condition == "Treatment" and si % 8 == 0 else 0
                rows.append({"sample": f"ER-{sample_idx + 1:02d}", "site": site, "transcript": f"TX{si + 1:03d}", "condition": condition, "coverage": int(rng.integers(10, 250)), "modified_fraction": float(np.clip(rng.beta(2, 8) + shift, 0, 1)), "strand": rng.choice(["+", "-"])})
        return pd.DataFrame(rows)
    if key == "strain_microbiome":
        rows = []
        taxa = ["Bacteroides", "Faecalibacterium", "Escherichia", "Bifidobacterium", "Akkermansia"]
        features = ["pathway_glycolysis", "AMR_beta_lactam", "virulence_adhesion", "SCFA_butyrate"]
        for sample_idx in range(24):
            group = "Case" if sample_idx >= 12 else "Control"
            for taxon in taxa:
                for feature in features:
                    base = rng.gamma(1.5, 2.0)
                    effect = 2.2 if group == "Case" and feature.startswith("AMR") and taxon == "Escherichia" else 1.0
                    rows.append({"sample": f"MB-{sample_idx + 1:03d}", "taxon": taxon, "strain": f"{taxon}_S{rng.integers(1, 5)}", "feature": feature, "abundance": base * effect, "feature_type": "AMR" if feature.startswith("AMR") else "Pathway", "group": group})
        return pd.DataFrame(rows)
    if key == "cell_atlas_mapping":
        labels = ["T cell", "B cell", "Monocyte", "Endothelial", "Fibroblast"]
        return pd.DataFrame({"cell": [f"CELL-{i + 1:05d}" for i in range(n)], "reference_label": rng.choice(labels, n), "similarity": np.clip(rng.normal(0.78, 0.16, n), 0, 1), "marker_agreement": np.clip(rng.normal(0.72, 0.2, n), 0, 1), "batch": rng.choice(["B1", "B2", "B3"], n), "query_cluster": rng.choice([f"C{i}" for i in range(8)], n)})
    if key == "phenotypic_screening":
        rows = []
        compounds = [f"CMP-{i + 1:03d}" for i in range(14)]
        for plate in ["P1", "P2", "P3"]:
            for row in "ABCDEFGH":
                for col in range(1, 13):
                    well = f"{row}{col:02d}"
                    if col == 1:
                        control, compound, dose, response = "negative", "DMSO", 0.0, rng.normal(1.0, 0.06)
                    elif col == 12:
                        control, compound, dose, response = "positive", "KILL", 10.0, rng.normal(0.12, 0.04)
                    else:
                        control, compound = "sample", rng.choice(compounds)
                        dose = float(rng.choice([0.03, 0.1, 0.3, 1.0, 3.0, 10.0]))
                        potency = 10 ** rng.uniform(-1, 1)
                        response = 1 / (1 + dose / potency) + rng.normal(0, 0.05)
                    edge = row in "AH" or col in {1, 12}
                    rows.append({"plate": plate, "well": well, "compound": compound, "dose": dose, "response": float(response + (0.05 if edge and control == "sample" else 0)), "control_type": control, "edge_well": edge})
        return pd.DataFrame(rows)
    if key == "organoid_3d":
        rows = []
        for image_idx in range(8):
            condition = "Treatment" if image_idx >= 4 else "Control"
            for organoid_idx in range(12):
                growth = rng.uniform(0.04, 0.13) * (0.65 if condition == "Treatment" else 1.0)
                base = rng.lognormal(5.0, 0.25)
                for time in [0, 24, 48, 72]:
                    rows.append({"image": f"IMG-{image_idx + 1:03d}", "organoid": f"ORG-{image_idx + 1:03d}-{organoid_idx + 1:02d}", "time": time, "condition": condition, "area": base * (1 + growth * time), "viability": float(np.clip(rng.normal(0.88 if condition == "Control" else 0.68, 0.08), 0, 1)), "circularity": float(np.clip(rng.normal(0.76, 0.12), 0, 1))})
        return pd.DataFrame(rows)
    if key == "protein_language_design":
        aa = np.array(list("ACDEFGHIKLMNPQRSTVWY"))
        rows = []
        for i in range(max(20, n // 4)):
            seq = "".join(rng.choice(aa, size=int(rng.integers(80, 240))))
            rows.append({"sequence_id": f"PROT-{i + 1:03d}", "sequence": seq, "activity_proxy": rng.uniform(0.2, 0.9), "stability_proxy": rng.uniform(0.3, 0.95), "constraint_group": rng.choice(["A", "B"]), "parent_id": "ROOT"})
        return pd.DataFrame(rows)
    if key == "enzyme_pathway_design":
        return pd.DataFrame({"enzyme": [f"E{i % 12 + 1:02d}" for i in range(n)], "variant": [f"V{i + 1:03d}" for i in range(n)], "reaction": [f"R{i % 18 + 1:02d}" for i in range(n)], "activity": rng.lognormal(0.2, 0.45, n), "stability": rng.uniform(0.3, 0.98, n), "flux": rng.lognormal(-0.1, 0.7, n), "cofactor": rng.choice(["NADH", "NADPH", "ATP", "None"], n), "host": rng.choice(["E. coli", "Yeast", "CHO"], n)})
    if key == "host_pathogen_interaction":
        return pd.DataFrame({"host_protein": [f"H{i % 40 + 1:03d}" for i in range(n)], "pathogen_protein": [f"P{i % 35 + 1:03d}" for i in range(n)], "evidence": rng.uniform(0.05, 1, n), "host_effect": rng.normal(0, 1, n), "pathogen_essentiality": rng.uniform(0, 1, n), "druggability": rng.uniform(0, 1, n), "source_count": rng.integers(1, 8, n)})
    if key == "virology_evolution":
        rows = []
        for sample_idx in range(16):
            for pos in range(100, 5100, 100):
                freq = float(np.clip(rng.beta(0.8, 8), 0, 1))
                if sample_idx >= 8 and pos % 900 == 0:
                    freq = float(np.clip(rng.normal(0.7, 0.08), 0, 1))
                rows.append({"sample": f"VIR-{sample_idx + 1:03d}", "position": pos, "ref": rng.choice(list("ACGT")), "alt": rng.choice(list("ACGT")), "frequency": freq, "gene": f"ORF{pos // 900 + 1}", "lineage_marker": pos % 900 == 0})
        return pd.DataFrame(rows)
    if key == "rare_variant_family":
        families = [f"FAM-{i + 1:02d}" for i in range(10)]
        genes = ["GENE_A", "GENE_B", "GENE_C", "GENE_D", "GENE_E"]
        rows = []
        for family in families:
            for variant_idx in range(30):
                gene = rng.choice(genes); variant = f"{gene}:v{variant_idx + 1}"
                af = float(10 ** rng.uniform(-5, -1))
                impact = rng.choice(["HIGH", "MODERATE", "LOW"], p=[0.15, 0.45, 0.4])
                pattern = rng.choice(["de_novo", "recessive", "dominant", "unknown"])
                genotypes = {"father": 0, "mother": 0, "proband": 1}
                if pattern == "recessive": genotypes = {"father": 1, "mother": 1, "proband": 2}
                elif pattern == "dominant": genotypes = {"father": 1, "mother": 0, "proband": 1}
                elif pattern == "unknown": genotypes = {r: int(rng.integers(0, 3)) for r in ["father", "mother", "proband"]}
                for role, gt in genotypes.items():
                    rows.append({"family": family, "sample": f"{family}-{role}", "role": role, "gene": gene, "variant": variant, "genotype": gt, "frequency": af, "impact": impact, "phenotype_match": rng.uniform(0, 1)})
        return pd.DataFrame(rows)
    raise KeyError(key)


ALIASES = {
    "chr": "chrom", "chromosome": "chrom", "pos": "position", "id": "variant",
    "gt": "genotype", "case_control": "phenotype", "value_group": "group",
    "subject_id": "subject", "patient": "subject", "timepoint": "time",
    "isoform": "transcript", "count": "abundance", "reads": "junction_support",
    "mod_fraction": "modified_fraction", "depth": "coverage", "species": "taxon",
    "cell_id": "cell", "label": "reference_label", "confidence": "similarity",
    "object_id": "organoid", "image_id": "image", "seq": "sequence",
    "protein": "enzyme", "svtype": "sv_type", "qual": "quality",
}


def normalise(data: pd.DataFrame, module: NextGenModule) -> pd.DataFrame:
    frame = data.copy()
    frame.columns = [str(column).strip().lower().replace(" ", "_").replace("-", "_") for column in frame.columns]
    frame = frame.rename(columns={key: value for key, value in ALIASES.items() if key in frame.columns and value not in frame.columns and key not in module.required_columns})
    for column in module.required_columns:
        if column not in frame.columns:
            if column in {"sample", "subject", "cell", "image", "family"}:
                frame[column] = [f"record_{i + 1}" for i in range(len(frame))]
            elif column in {"group", "condition", "omics_layer", "feature_type", "control_type", "impact", "sv_type"}:
                frame[column] = "Unknown"
            else:
                frame[column] = np.nan
    if module.key == "population_gwas":
        frame["position"] = _numeric(frame["position"])
        frame["genotype"] = frame["genotype"].map(lambda x: sum(int(t) for t in re.split(r"[/|]", str(x)) if t.isdigit()) if isinstance(x, str) and ("/" in x or "|" in x) else pd.to_numeric(x, errors="coerce"))
        frame["phenotype"] = frame["phenotype"].map({"case": 1, "control": 0, "Case": 1, "Control": 0, True: 1, False: 0}).fillna(pd.to_numeric(frame["phenotype"], errors="coerce"))
    numeric_candidates = {
        "position", "start", "end", "support", "quality", "time", "value", "abundance", "junction_support", "coverage",
        "modified_fraction", "similarity", "marker_agreement", "dose", "response", "area", "viability", "activity_proxy",
        "stability_proxy", "activity", "stability", "flux", "evidence", "host_effect", "pathogen_essentiality", "druggability",
        "frequency", "genotype", "phenotype_match",
    }
    for column in numeric_candidates.intersection(frame.columns):
        frame[column] = _numeric(frame[column])
    if module.key == "enzyme_pathway_design" and "sequence" in frame.columns:
        features = frame["sequence"].fillna("").astype(str).map(_aa_features)
        entropy = features.map(lambda x: x["composition_entropy"])
        hydrophobic = features.map(lambda x: x["hydrophobic_fraction"])
        if frame["activity"].isna().all():
            frame["activity"] = (0.4 + 0.6 * entropy).clip(0, 1)
        if frame["stability"].isna().all():
            frame["stability"] = (1 - (hydrophobic - 0.42).abs()).clip(0, 1)
        if frame["flux"].isna().all():
            frame["flux"] = frame["activity"] * frame["stability"]
        frame["score_source"] = "sequence_composition_proxy"
    return frame


def _hwe_p(genotypes: pd.Series) -> float:
    g = _numeric(genotypes).dropna().round().astype(int)
    g = g[g.isin([0, 1, 2])]
    n = len(g)
    if n < 10:
        return float("nan")
    obs = np.array([(g == 0).sum(), (g == 1).sum(), (g == 2).sum()], dtype=float)
    p = (2 * obs[2] + obs[1]) / (2 * n)
    exp = np.array([(1 - p) ** 2, 2 * p * (1 - p), p ** 2]) * n
    if np.any(exp < 1e-9):
        return float("nan")
    return float(stats.chisquare(obs, exp).pvalue)


def _linear_p(x: pd.Series, y: pd.Series) -> tuple[float, float]:
    table = pd.DataFrame({"x": _numeric(x), "y": _numeric(y)}).dropna()
    if len(table) < 8 or table["x"].nunique() < 2 or table["y"].nunique() < 2:
        return float("nan"), float("nan")
    slope, _, r, p, _ = stats.linregress(table["x"], table["y"])
    return float(slope), float(p)


def _entropy(values: pd.Series) -> float:
    x = _numeric(values).dropna().clip(lower=0)
    if x.empty or x.sum() <= 0:
        return 0.0
    p = x / x.sum()
    return float(-(p[p > 0] * np.log(p[p > 0])).sum())


def _aa_features(sequence: str) -> dict[str, float]:
    seq = re.sub(r"[^ACDEFGHIKLMNPQRSTVWY]", "", str(sequence).upper())
    length = max(len(seq), 1)
    counts = {aa: seq.count(aa) / length for aa in "ACDEFGHIKLMNPQRSTVWY"}
    hydrophobic = sum(counts[a] for a in "AILMFWVY")
    charged = sum(counts[a] for a in "DEKR")
    aromatic = sum(counts[a] for a in "FWY")
    entropy = -sum(value * math.log(value + 1e-12) for value in counts.values() if value > 0) / math.log(20)
    liability = len(re.findall(r"N[GST]|D[GSTP]|[MW]", seq))
    return {"length": len(seq), "hydrophobic_fraction": hydrophobic, "charged_fraction": charged, "aromatic_fraction": aromatic, "composition_entropy": entropy, "liability_motifs": liability, **{f"aa_{aa}": counts[aa] for aa in counts}}


def analyse(data: pd.DataFrame, module: NextGenModule, threshold: float = 0.7) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame | None, dict[str, pd.DataFrame]]:
    if module.key in NEW_BIOMEDICAL_KEYS:
        return analyse_biomedical(data, module, threshold)
    frame = normalise(data, module)
    key = module.key
    extras: dict[str, pd.DataFrame] = {}
    secondary: pd.DataFrame | None = None
    metrics: dict[str, Any] = {}

    if key == "population_gwas":
        rows = []
        for variant, group in frame.groupby("variant", dropna=False):
            genotype = _numeric(group["genotype"])
            phenotype = _numeric(group["phenotype"])
            slope, p_value = _linear_p(genotype, phenotype)
            called = genotype.dropna()
            maf = float(min(called.sum() / max(2 * len(called), 1), 1 - called.sum() / max(2 * len(called), 1))) if len(called) else np.nan
            rows.append({"variant": variant, "chrom": str(group["chrom"].iloc[0]), "position": float(_numeric(group["position"]).median()), "samples": len(group), "call_rate": float(genotype.notna().mean()), "maf": maf, "hwe_p": _hwe_p(genotype), "effect": slope, "p_value": p_value})
        result = pd.DataFrame(rows)
        result["q_value"] = bh_adjust(result["p_value"])
        result["qc_pass"] = (result["call_rate"] >= 0.95) & (result["maf"] >= 0.01) & ((result["hwe_p"].isna()) | (result["hwe_p"] >= 1e-6))
        result["priority_score"] = result["qc_pass"].astype(float) * (1 - result["q_value"].fillna(1)) * result["effect"].abs().clip(0, 1)
        result = result.sort_values(["q_value", "priority_score"], ascending=[True, False])
        valid = result["p_value"].dropna().clip(1e-300, 1)
        lambda_gc = float(np.median(stats.chi2.isf(valid, 1)) / 0.4549364) if len(valid) else np.nan
        metrics.update({"variants_tested": len(result), "qc_pass_variants": int(result["qc_pass"].sum()), "fdr_significant": int((result["q_value"] <= 0.05).sum()), "lambda_gc": lambda_gc})
        secondary = frame.groupby("sample", as_index=False).agg(call_rate=("genotype", lambda x: float(_numeric(x).notna().mean())), phenotype=("phenotype", "first"))
    elif key == "structural_variant_repeat":
        result = frame.copy()
        result["size_bp"] = (_numeric(result["end"]) - _numeric(result["start"])).abs().clip(lower=1)
        result["support_norm"] = _numeric(result["support"]).rank(pct=True).fillna(0)
        quality = _numeric(result.get("quality", pd.Series(np.nan, index=result.index)))
        result["quality_norm"] = quality.rank(pct=True).fillna(0.5)
        result["gene_impact"] = np.where(result.get("gene", "INTERGENIC").astype(str).str.upper().eq("INTERGENIC"), 0.25, 1.0)
        result["priority_score"] = 0.4 * result["support_norm"] + 0.25 * result["quality_norm"] + 0.2 * result["gene_impact"] + 0.15 * np.log10(result["size_bp"] + 1) / max(np.log10(result["size_bp"].max() + 1), 1)
        result["low_confidence"] = (_numeric(result["support"]) < 3) | (quality.notna() & (quality < 20))
        result = result.sort_values(["low_confidence", "priority_score"], ascending=[True, False])
        secondary = result.groupby("sv_type", as_index=False).agg(events=("sv_id", "count"), median_size=("size_bp", "median"), samples=("sample", "nunique"), mean_priority=("priority_score", "mean"))
        metrics.update({"events": len(result), "low_confidence": int(result["low_confidence"].sum()), "samples": int(result["sample"].nunique())})
    elif key == "longitudinal_multiomics":
        slope_rows = []
        for (subject, feature), group in frame.groupby(["subject", "feature"]):
            clean = group[["time", "value"]].dropna().sort_values("time")
            slope = float(np.polyfit(clean["time"], clean["value"], 1)[0]) if len(clean) >= 2 and clean["time"].nunique() >= 2 else np.nan
            slope_rows.append({"subject": subject, "feature": feature, "group": group["group"].iloc[0], "omics_layer": group["omics_layer"].iloc[0], "visits": len(clean), "slope": slope, "baseline": float(clean["value"].iloc[0]) if len(clean) else np.nan, "last_value": float(clean["value"].iloc[-1]) if len(clean) else np.nan})
        slopes = pd.DataFrame(slope_rows)
        groups = slopes["group"].dropna().astype(str).unique().tolist()
        rows = []
        for feature, group in slopes.groupby("feature"):
            row = {"feature": feature, "omics_layer": group["omics_layer"].mode().iat[0] if not group["omics_layer"].mode().empty else "Unknown", "subjects": group["subject"].nunique(), "median_visits": float(group["visits"].median()), "mean_slope": float(group["slope"].mean())}
            if len(groups) >= 2:
                a = group.loc[group["group"].astype(str) == groups[0], "slope"]
                b = group.loc[group["group"].astype(str) == groups[-1], "slope"]
                row.update({"reference_group": groups[0], "comparison_group": groups[-1], "slope_difference": float(_numeric(b).mean() - _numeric(a).mean()), "effect_size": _cohen_d(a, b), "p_value": _safe_welch(a, b)})
            rows.append(row)
        result = pd.DataFrame(rows)
        result["q_value"] = bh_adjust(result.get("p_value", pd.Series(np.nan, index=result.index)))
        result["priority_score"] = result.get("slope_difference", pd.Series(0, index=result.index)).abs().rank(pct=True) * (1 - result["q_value"].fillna(1))
        result = result.sort_values("priority_score", ascending=False)
        secondary = slopes
        extras["subject_slopes"] = slopes
        metrics.update({"features": len(result), "subjects": int(frame["subject"].nunique()), "significant_features": int((result["q_value"] <= 0.05).sum())})
    elif key == "rna_isoform_splicing":
        work = frame.copy()
        work["gene_total"] = work.groupby(["sample", "gene"])["abundance"].transform("sum")
        work["transcript_usage"] = _numeric(work["abundance"]) / work["gene_total"].replace(0, np.nan)
        groups = work["group"].dropna().astype(str).unique().tolist()
        rows = []
        for (gene, transcript), group in work.groupby(["gene", "transcript"]):
            row = {"gene": gene, "transcript": transcript, "samples": group["sample"].nunique(), "mean_usage": float(group["transcript_usage"].mean()), "median_junction_support": float(_numeric(group["junction_support"]).median())}
            if len(groups) >= 2:
                a = group.loc[group["group"].astype(str) == groups[0], "transcript_usage"]
                b = group.loc[group["group"].astype(str) == groups[-1], "transcript_usage"]
                row.update({"reference_group": groups[0], "comparison_group": groups[-1], "delta_usage": float(_numeric(b).mean() - _numeric(a).mean()), "p_value": _safe_welch(a, b)})
            rows.append(row)
        result = pd.DataFrame(rows); result["q_value"] = bh_adjust(result.get("p_value", pd.Series(np.nan, index=result.index)))
        result["supported"] = result["median_junction_support"] >= 5
        result["priority_score"] = result.get("delta_usage", pd.Series(0, index=result.index)).abs() * (1 - result["q_value"].fillna(1)) * result["supported"].astype(float)
        result = result.sort_values("priority_score", ascending=False)
        secondary = work.groupby("gene", as_index=False).agg(transcripts=("transcript", "nunique"), samples=("sample", "nunique"), total_abundance=("abundance", "sum"))
        metrics.update({"isoforms": len(result), "genes": int(result["gene"].nunique()), "fdr_switches": int(((result["q_value"] <= 0.05) & (result.get("delta_usage", 0).abs() >= 0.1)).sum())})
    elif key == "epitranscriptomics":
        groups = frame["condition"].dropna().astype(str).unique().tolist(); rows = []
        for site, group in frame.groupby("site"):
            row = {"site": site, "transcript": group["transcript"].iloc[0], "samples": group["sample"].nunique(), "median_coverage": float(_numeric(group["coverage"]).median()), "mean_modified_fraction": float(_numeric(group["modified_fraction"]).mean()), "replicate_sd": float(_numeric(group["modified_fraction"]).std())}
            if len(groups) >= 2:
                a = group.loc[group["condition"].astype(str) == groups[0], "modified_fraction"]
                b = group.loc[group["condition"].astype(str) == groups[-1], "modified_fraction"]
                row.update({"reference_condition": groups[0], "comparison_condition": groups[-1], "delta_fraction": float(_numeric(b).mean() - _numeric(a).mean()), "p_value": _safe_welch(a, b)})
            rows.append(row)
        result = pd.DataFrame(rows); result["q_value"] = bh_adjust(result.get("p_value", pd.Series(np.nan, index=result.index)))
        result["qc_pass"] = (result["median_coverage"] >= 20) & (result["replicate_sd"].fillna(1) <= 0.25)
        result["priority_score"] = result.get("delta_fraction", pd.Series(0, index=result.index)).abs() * (1 - result["q_value"].fillna(1)) * result["qc_pass"].astype(float)
        result = result.sort_values("priority_score", ascending=False)
        secondary = frame.groupby("transcript", as_index=False).agg(sites=("site", "nunique"), mean_fraction=("modified_fraction", "mean"), median_coverage=("coverage", "median"))
        metrics.update({"sites": len(result), "qc_pass": int(result["qc_pass"].sum()), "fdr_candidates": int((result["q_value"] <= 0.05).sum())})
    elif key == "strain_microbiome":
        work = frame.copy(); work["abundance"] = _numeric(work["abundance"], 0).clip(lower=0)
        work["sample_total"] = work.groupby("sample")["abundance"].transform("sum")
        work["relative_abundance"] = work["abundance"] / work["sample_total"].replace(0, np.nan)
        diversity = work.groupby("sample").apply(lambda g: pd.Series({"shannon": _entropy(g.groupby("taxon")["relative_abundance"].sum()), "taxa": g["taxon"].nunique(), "strains": g["strain"].nunique(), "group": g.get("group", pd.Series(["Unknown"])).iloc[0]}), include_groups=False).reset_index()
        groups = work.get("group", pd.Series(["Unknown"] * len(work))).dropna().astype(str).unique().tolist(); rows = []
        for (feature, feature_type), group in work.groupby(["feature", "feature_type"]):
            sample_values = group.groupby(["sample", "group"], as_index=False)["relative_abundance"].sum() if "group" in group.columns else group.groupby("sample", as_index=False)["relative_abundance"].sum().assign(group="Unknown")
            row = {"feature": feature, "feature_type": feature_type, "prevalence": float((sample_values["relative_abundance"] > 0).mean()), "mean_relative_abundance": float(sample_values["relative_abundance"].mean())}
            if len(groups) >= 2:
                a = sample_values.loc[sample_values["group"].astype(str) == groups[0], "relative_abundance"]
                b = sample_values.loc[sample_values["group"].astype(str) == groups[-1], "relative_abundance"]
                row.update({"log2_fold_change": float(np.log2((_numeric(b).mean() + 1e-9) / (_numeric(a).mean() + 1e-9))), "p_value": _safe_welch(a, b)})
            rows.append(row)
        result = pd.DataFrame(rows); result["q_value"] = bh_adjust(result.get("p_value", pd.Series(np.nan, index=result.index)))
        result["priority_score"] = result.get("log2_fold_change", pd.Series(0, index=result.index)).abs().clip(0, 5) / 5 * (1 - result["q_value"].fillna(1)) * result["prevalence"]
        result = result.sort_values("priority_score", ascending=False); secondary = diversity; extras["sample_diversity"] = diversity
        metrics.update({"samples": int(work["sample"].nunique()), "features": len(result), "amr_features": int(result["feature_type"].astype(str).str.upper().eq("AMR").sum())})
    elif key == "cell_atlas_mapping":
        result = frame.copy(); result["annotation_confidence"] = 0.65 * _numeric(result["similarity"], 0) + 0.35 * _numeric(result["marker_agreement"], 0)
        batch_medians = result.groupby("batch")["annotation_confidence"].transform("median")
        result["batch_shift"] = (result["annotation_confidence"] - batch_medians).abs()
        result["novel_state_flag"] = (result["annotation_confidence"] < threshold) | (result["marker_agreement"] < 0.4)
        result["priority_score"] = result["annotation_confidence"] * (~result["novel_state_flag"]).astype(float)
        result = result.sort_values(["novel_state_flag", "annotation_confidence"], ascending=[False, True])
        secondary = result.groupby("reference_label", as_index=False).agg(cells=("cell", "count"), mean_confidence=("annotation_confidence", "mean"), novel_fraction=("novel_state_flag", "mean"), batches=("batch", "nunique"))
        metrics.update({"cells": len(result), "labels": int(result["reference_label"].nunique()), "novel_or_uncertain": int(result["novel_state_flag"].sum())})
    elif key == "phenotypic_screening":
        work = frame.copy(); work["response"] = _numeric(work["response"]); work["dose"] = _numeric(work["dose"])
        plate_qc = []
        normalised = []
        for plate, group in work.groupby("plate"):
            neg = group.loc[group["control_type"].astype(str).str.lower().eq("negative"), "response"]
            pos = group.loc[group["control_type"].astype(str).str.lower().eq("positive"), "response"]
            neg_mean, pos_mean = float(neg.mean()), float(pos.mean())
            zprime = 1 - 3 * (float(neg.std()) + float(pos.std())) / abs(neg_mean - pos_mean) if len(neg) > 1 and len(pos) > 1 and neg_mean != pos_mean else np.nan
            plate_qc.append({"plate": plate, "negative_mean": neg_mean, "positive_mean": pos_mean, "z_prime": zprime, "wells": len(group)})
            g = group.copy(); g["normalised_response"] = (g["response"] - pos_mean) / max(neg_mean - pos_mean, 1e-9); normalised.append(g)
        work = pd.concat(normalised, ignore_index=True) if normalised else work.assign(normalised_response=np.nan)
        sample = work[work["control_type"].astype(str).str.lower().eq("sample")].copy()
        rows = []
        for compound, group in sample.groupby("compound"):
            dose_summary = group.groupby("dose", as_index=False)["normalised_response"].median().sort_values("dose")
            min_response = float(dose_summary["normalised_response"].min()) if not dose_summary.empty else np.nan
            auc = float(np.trapezoid(dose_summary["normalised_response"], np.log10(dose_summary["dose"].clip(lower=1e-9)))) if len(dose_summary) >= 2 else np.nan
            monotonicity = float(-stats.spearmanr(np.log10(group["dose"].clip(lower=1e-9)), group["normalised_response"], nan_policy="omit").statistic) if group["dose"].nunique() >= 3 else np.nan
            rows.append({"compound": compound, "wells": len(group), "doses": group["dose"].nunique(), "min_response": min_response, "auc_logdose": auc, "dose_response_monotonicity": monotonicity, "replicate_cv": float(group.groupby("dose")["normalised_response"].std().mean())})
        result = pd.DataFrame(rows); result["priority_score"] = (1 - result["min_response"].clip(0, 1)) * result["dose_response_monotonicity"].clip(0, 1).fillna(0) * (1 - result["replicate_cv"].clip(0, 1).fillna(1))
        result = result.sort_values("priority_score", ascending=False); secondary = pd.DataFrame(plate_qc); extras["normalised_wells"] = work
        metrics.update({"compounds": len(result), "plates": int(work["plate"].nunique()), "plates_zprime_ge_0_5": int((secondary["z_prime"] >= 0.5).sum()) if not secondary.empty else 0})
    elif key == "organoid_3d":
        work = frame.copy(); work["time"] = _numeric(work["time"], 0); work["area"] = _numeric(work["area"]); work["viability"] = _numeric(work["viability"])
        rows = []
        for organoid, group in work.groupby("organoid"):
            clean = group.sort_values("time")
            slope = float(np.polyfit(clean["time"], np.log(clean["area"].clip(lower=1)), 1)[0]) if len(clean) >= 2 and clean["time"].nunique() >= 2 else np.nan
            rows.append({"organoid": organoid, "image": group["image"].iloc[0], "condition": group["condition"].iloc[0], "measurements": len(group), "growth_rate_log_area": slope, "final_area": float(clean["area"].iloc[-1]), "mean_viability": float(clean["viability"].mean()), "mean_circularity": float(_numeric(clean.get("circularity", pd.Series(np.nan, index=clean.index))).mean())})
        result = pd.DataFrame(rows); result["qc_flag"] = result["mean_circularity"].notna() & (result["mean_circularity"] < 0.2)
        result["priority_score"] = result["mean_viability"].fillna(0) * result["growth_rate_log_area"].rank(pct=True).fillna(0) * (~result["qc_flag"]).astype(float)
        result = result.sort_values("priority_score", ascending=False)
        secondary = result.groupby("condition", as_index=False).agg(organoids=("organoid", "count"), mean_growth=("growth_rate_log_area", "mean"), mean_viability=("mean_viability", "mean"), median_final_area=("final_area", "median"))
        metrics.update({"organoids": len(result), "conditions": int(result["condition"].nunique()), "qc_flags": int(result["qc_flag"].sum())})
    elif key == "protein_language_design":
        result = frame.copy(); feature_rows = []
        for _, row in result.iterrows():
            features = _aa_features(str(row["sequence"])); feature_rows.append(features)
        features = pd.DataFrame(feature_rows, index=result.index); result = pd.concat([result, features], axis=1)
        result["sequence_quality_score"] = result["composition_entropy"].clip(0, 1) * (1 - (result["hydrophobic_fraction"] - 0.42).abs().clip(0, 0.42) / 0.42) * (1 - result["liability_motifs"].clip(0, 20) / 20)
        result["priority_score"] = 0.35 * _numeric(result.get("activity_proxy", pd.Series(0.5, index=result.index)), 0.5).clip(0, 1) + 0.35 * _numeric(result.get("stability_proxy", pd.Series(0.5, index=result.index)), 0.5).clip(0, 1) + 0.3 * result["sequence_quality_score"].clip(0, 1)
        result["constraint_flag"] = (result["hydrophobic_fraction"] > 0.65) | (result["liability_motifs"] >= 20) | (result["length"] < 20)
        proposals = []
        conservative = {"A": "G", "G": "A", "D": "E", "E": "D", "K": "R", "R": "K", "I": "L", "L": "I", "F": "Y", "Y": "F", "S": "T", "T": "S", "N": "Q", "Q": "N"}
        for _, row in result.sort_values("priority_score", ascending=False).head(20).iterrows():
            seq = str(row["sequence"]); positions = [i for i, aa in enumerate(seq) if aa in conservative]
            if positions:
                pos = positions[_seed(str(row["sequence_id"])) % len(positions)]; mutant = seq[:pos] + conservative[seq[pos]] + seq[pos + 1:]
                proposals.append({"parent_id": row["sequence_id"], "mutation": f"{seq[pos]}{pos + 1}{conservative[seq[pos]]}", "candidate_sequence": mutant, "proposal_type": "conservative_local"})
        extras["mutation_proposals"] = pd.DataFrame(proposals); secondary = result.groupby("constraint_group", as_index=False).agg(sequences=("sequence_id", "count"), mean_quality=("sequence_quality_score", "mean"), mean_priority=("priority_score", "mean"), flagged=("constraint_flag", "sum"))
        result = result.sort_values(["constraint_flag", "priority_score"], ascending=[True, False]); metrics.update({"sequences": len(result), "constraint_flags": int(result["constraint_flag"].sum()), "proposals": len(proposals)})
    elif key == "enzyme_pathway_design":
        result = frame.copy();
        for c in ["activity", "stability", "flux"]: result[c] = _numeric(result[c])
        result["activity_norm"] = result["activity"].rank(pct=True); result["stability_norm"] = result["stability"].rank(pct=True); result["flux_norm"] = result["flux"].rank(pct=True)
        result["priority_score"] = 0.4 * result["activity_norm"] + 0.35 * result["stability_norm"] + 0.25 * result["flux_norm"]
        reaction_summary = result.groupby("reaction", as_index=False).agg(mean_flux=("flux", "mean"), variants=("variant", "nunique"), mean_activity=("activity", "mean"), hosts=("host", "nunique") if "host" in result.columns else ("enzyme", "nunique"))
        reaction_summary["bottleneck_score"] = 1 - reaction_summary["mean_flux"].rank(pct=True)
        extras["pathway_bottlenecks"] = reaction_summary.sort_values("bottleneck_score", ascending=False)
        if "cofactor" in result.columns:
            secondary = result.groupby("cofactor", as_index=False).agg(variants=("variant", "count"), total_flux=("flux", "sum"), mean_priority=("priority_score", "mean"))
        result = result.sort_values("priority_score", ascending=False); metrics.update({"variants": len(result), "reactions": int(result["reaction"].nunique()), "bottlenecks": int((reaction_summary["bottleneck_score"] >= 0.8).sum())})
    elif key == "host_pathogen_interaction":
        result = frame.copy()
        source_norm = _numeric(result.get("source_count", pd.Series(1, index=result.index)), 1).rank(pct=True)
        result["priority_score"] = 0.3 * _numeric(result["evidence"], 0).clip(0, 1) + 0.25 * _numeric(result["pathogen_essentiality"], 0).clip(0, 1) + 0.25 * _numeric(result["druggability"], 0).clip(0, 1) + 0.1 * _numeric(result["host_effect"], 0).abs().rank(pct=True) + 0.1 * source_norm
        result["evidence_gap"] = (_numeric(result["evidence"], 0) < 0.35) | (_numeric(result.get("source_count", pd.Series(1, index=result.index)), 1) < 2)
        result = result.sort_values(["evidence_gap", "priority_score"], ascending=[True, False])
        secondary = result.groupby("pathogen_protein", as_index=False).agg(host_partners=("host_protein", "nunique"), mean_priority=("priority_score", "mean"), max_essentiality=("pathogen_essentiality", "max"), evidence_gaps=("evidence_gap", "sum")).sort_values("mean_priority", ascending=False)
        metrics.update({"interactions": len(result), "host_proteins": int(result["host_protein"].nunique()), "pathogen_proteins": int(result["pathogen_protein"].nunique()), "evidence_gaps": int(result["evidence_gap"].sum())})
    elif key == "virology_evolution":
        result = frame.copy(); result["frequency"] = _numeric(result["frequency"]).clip(0, 1)
        result["minor_variant"] = result["frequency"].between(0.02, 0.5, inclusive="both")
        result["fixed_or_consensus"] = result["frequency"] > 0.5
        result["priority_score"] = result["frequency"] * (1 + result.get("lineage_marker", pd.Series(False, index=result.index)).astype(bool).astype(float)) / 2
        sample_stats = result.groupby("sample", as_index=False).agg(variants=("position", "count"), minor_variants=("minor_variant", "sum"), fixed_variants=("fixed_or_consensus", "sum"), mean_frequency=("frequency", "mean"))
        diversity = result.groupby("sample")["frequency"].apply(_entropy).rename("frequency_entropy").reset_index(); sample_stats = sample_stats.merge(diversity, on="sample", how="left")
        sample_stats["mixed_infection_review"] = (sample_stats["minor_variants"] >= sample_stats["minor_variants"].quantile(0.9)) & (sample_stats["frequency_entropy"] >= sample_stats["frequency_entropy"].quantile(0.75))
        secondary = sample_stats; result = result.sort_values("priority_score", ascending=False)
        metrics.update({"samples": int(result["sample"].nunique()), "variants": len(result), "samples_for_mixed_review": int(sample_stats["mixed_infection_review"].sum())})
    elif key == "rare_variant_family":
        work = frame.copy(); work["frequency"] = _numeric(work["frequency"]); work["genotype"] = _numeric(work["genotype"])
        impact_score = work["impact"].astype(str).str.upper().map({"HIGH": 1.0, "MODERATE": 0.65, "LOW": 0.2}).fillna(0.35)
        work["rarity_score"] = (1 - np.log10(work["frequency"].clip(lower=1e-6)) / np.log10(1e-6)).clip(0, 1)
        work["impact_score"] = impact_score
        rows = []
        for (family, variant), group in work.groupby(["family", "variant"]):
            role_gt = {str(row.get("role", row["sample"])).lower(): row["genotype"] for _, row in group.iterrows()}
            proband = role_gt.get("proband", np.nan); father = role_gt.get("father", np.nan); mother = role_gt.get("mother", np.nan)
            de_novo = proband >= 1 and father == 0 and mother == 0 if np.isfinite(proband) and np.isfinite(father) and np.isfinite(mother) else False
            recessive = proband == 2 and father >= 1 and mother >= 1 if np.isfinite(proband) and np.isfinite(father) and np.isfinite(mother) else False
            dominant = proband >= 1 and ((father >= 1) ^ (mother >= 1)) if np.isfinite(proband) and np.isfinite(father) and np.isfinite(mother) else False
            inheritance = "de_novo" if de_novo else "recessive" if recessive else "dominant" if dominant else "unresolved"
            first = group.iloc[0]
            rows.append({"family": family, "gene": first["gene"], "variant": variant, "members": group["sample"].nunique(), "frequency": float(group["frequency"].min()), "impact": first["impact"], "impact_score": float(group["impact_score"].max()), "phenotype_match": float(_numeric(group.get("phenotype_match", pd.Series(0.5, index=group.index))).max()), "inheritance": inheritance, "inheritance_consistent": inheritance != "unresolved"})
        result = pd.DataFrame(rows); result["rarity_score"] = (1 - (np.log10(result["frequency"].clip(lower=1e-6)) - math.log10(1e-6)) / (math.log10(0.05) - math.log10(1e-6))).clip(0, 1)
        result["priority_score"] = 0.35 * result["rarity_score"] + 0.3 * result["impact_score"] + 0.25 * result["phenotype_match"] + 0.1 * result["inheritance_consistent"].astype(float)
        result["manual_review_required"] = True; result = result.sort_values("priority_score", ascending=False)
        secondary = result.groupby("gene", as_index=False).agg(families=("family", "nunique"), variants=("variant", "nunique"), max_priority=("priority_score", "max"), consistent_inheritance=("inheritance_consistent", "sum")).sort_values("max_priority", ascending=False)
        metrics.update({"families": int(result["family"].nunique()), "candidates": len(result), "inheritance_consistent": int(result["inheritance_consistent"].sum())})
    else:
        raise KeyError(key)

    summary: dict[str, Any] = {
        "schema": "biointel.nextgen.scientific.v1",
        "module": module.key,
        "title": module.title,
        "input_records": len(frame),
        "result_records": len(result),
        "threshold": threshold,
        "missing_cells": int(frame.isna().sum().sum()),
        "duplicate_rows": int(frame.duplicated().sum()),
        "metrics": metrics,
        "advanced_table_count": len(extras),
        "scientific_boundary": module.boundary,
    }
    return result, summary, secondary, extras


def evidence_manifest(module: NextGenModule, data: pd.DataFrame, summary: dict[str, Any], configuration: dict[str, Any]) -> dict[str, Any]:
    stable = data.to_csv(index=False, lineterminator="\n", na_rep="<NA>").encode("utf-8")
    return {
        "schema": "biointel.nextgen.run_manifest.v1",
        "module": asdict(module),
        "input_sha256": hashlib.sha256(stable).hexdigest(),
        "input_profile": {"rows": len(data), "columns": list(map(str, data.columns)), "missing_cells": int(data.isna().sum().sum()), "duplicate_rows": int(data.duplicated().sum())},
        "configuration": configuration,
        "summary": summary,
        "boundary": module.boundary,
    }
