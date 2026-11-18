from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from .catalog import BioinformaticsPeakModule
from .contracts import contract_for
from .scientific import AnalysisBundle


def _num(series: pd.Series | Any, fill: float | None = None) -> pd.Series:
    if isinstance(series, pd.Series):
        out = pd.to_numeric(series, errors="coerce")
    else:
        out = pd.Series(series, dtype="float64")
    return out.fillna(fill) if fill is not None else out


def _rank01(series: pd.Series) -> pd.Series:
    values = _num(series)
    if values.notna().sum() == 0:
        return pd.Series(np.zeros(len(values)), index=values.index)
    return values.rank(pct=True).fillna(0.0)


def _entropy(series: pd.Series) -> float:
    values = _num(series, 0).clip(lower=0).to_numpy(float)
    total = float(values.sum())
    if total <= 0:
        return 0.0
    p = values[values > 0] / total
    return float(-(p * np.log(p)).sum())


def _safe_corr(a: pd.Series, b: pd.Series) -> float:
    aa = _num(a)
    bb = _num(b)
    valid = aa.notna() & bb.notna()
    if valid.sum() < 3 or aa[valid].std(ddof=0) == 0 or bb[valid].std(ddof=0) == 0:
        return float("nan")
    return float(aa[valid].corr(bb[valid]))


def _hwe_p(genotype: pd.Series) -> float:
    g = _num(genotype).round().dropna().astype(int)
    g = g[g.isin([0, 1, 2])]
    n = len(g)
    if n < 5:
        return float("nan")
    obs = np.array([(g == 0).sum(), (g == 1).sum(), (g == 2).sum()], dtype=float)
    p = (2 * obs[2] + obs[1]) / (2 * n)
    q = 1 - p
    exp = np.array([q * q * n, 2 * p * q * n, p * p * n])
    valid = exp > 0
    if not valid.all():
        return float("nan")
    return float(stats.chisquare(obs, exp).pvalue)


def parameter_defaults(module_key: str) -> dict[str, Any]:
    return {spec.key: spec.default for spec in contract_for(module_key).parameters}


def normalise_parameters(module_key: str, parameters: dict[str, Any] | None) -> dict[str, Any]:
    defaults = parameter_defaults(module_key)
    for key, value in (parameters or {}).items():
        if key in defaults:
            defaults[key] = value
    return defaults


def _common_qc(data: pd.DataFrame, module: BioinformaticsPeakModule, params: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    missing = int(data.isna().sum().sum())
    duplicates = int(data.duplicated().sum()) if not data.empty else 0
    rows.extend([
        {"check": "Input records", "status": "Pass" if len(data) else "Block", "value": int(len(data)), "detail": "Records available for analysis"},
        {"check": "Required schema", "status": "Pass" if all(c in data.columns for c in module.required_columns) else "Block", "value": sum(c not in data.columns for c in module.required_columns), "detail": "Required fields present"},
        {"check": "Missing values", "status": "Review" if missing else "Pass", "value": missing, "detail": "Missing values remain visible and are not silently discarded"},
        {"check": "Duplicate records", "status": "Review" if duplicates else "Pass", "value": duplicates, "detail": "Duplicate records remain visible for review"},
        {"check": "Reference context", "status": "Pass" if params.get("genome_build") and params.get("organism") else "Review", "value": 0, "detail": f"{params.get('organism', 'Unspecified')} · {params.get('genome_build', 'Unspecified')}"},
    ])
    return rows


def _gwas_extras(data: pd.DataFrame, bundle: AnalysisBundle, p: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]], dict[str, Any]]:
    frame = data.copy()
    frame["genotype"] = _num(frame.get("genotype"))
    variant_qc = frame.groupby(["variant", "chrom", "position"], dropna=False).agg(
        samples=("sample", "nunique"), call_rate=("genotype", lambda x: float(x.notna().mean())), mean_dosage=("genotype", "mean"),
    ).reset_index()
    variant_qc["maf"] = (variant_qc["mean_dosage"] / 2).clip(0, 1)
    variant_qc["maf"] = np.minimum(variant_qc["maf"], 1 - variant_qc["maf"])
    hwe = frame.groupby("variant")["genotype"].apply(_hwe_p)
    variant_qc["hwe_p"] = variant_qc["variant"].map(hwe)
    variant_qc["pass_call_rate"] = variant_qc["call_rate"] >= float(p["min_call_rate"])
    variant_qc["pass_maf"] = variant_qc["maf"] >= float(p["min_maf"])
    variant_qc["pass_hwe"] = variant_qc["hwe_p"].isna() | (variant_qc["hwe_p"] >= float(p["hwe_threshold"]))

    sample_qc = frame.groupby("sample", as_index=False).agg(
        call_rate=("genotype", lambda x: float(x.notna().mean())), mean_dosage=("genotype", "mean"), phenotype=("phenotype", "first")
    )
    sample_qc["heterozygosity_proxy"] = frame.assign(het=frame["genotype"].round().eq(1)).groupby("sample")["het"].mean().reindex(sample_qc["sample"]).to_numpy()
    sample_qc["heterozygosity_z"] = (sample_qc["heterozygosity_proxy"] - sample_qc["heterozygosity_proxy"].mean()) / sample_qc["heterozygosity_proxy"].std(ddof=0).replace(0, np.nan) if isinstance(sample_qc["heterozygosity_proxy"].std(ddof=0), pd.Series) else 0
    if np.isscalar(sample_qc["heterozygosity_z"]):
        sd = float(sample_qc["heterozygosity_proxy"].std(ddof=0))
        sample_qc["heterozygosity_z"] = 0.0 if not np.isfinite(sd) or sd == 0 else (sample_qc["heterozygosity_proxy"] - sample_qc["heterozygosity_proxy"].mean()) / sd

    geno = frame.pivot_table(index="sample", columns="variant", values="genotype", aggfunc="first")
    related_rows: list[dict[str, Any]] = []
    if 2 <= len(geno) <= 500:
        corr = geno.T.corr(min_periods=max(3, int(geno.shape[1] * 0.2)))
        for i, a in enumerate(corr.index):
            for b in corr.index[i + 1:]:
                value = corr.loc[a, b]
                if pd.notna(value) and abs(float(value)) >= 0.80:
                    related_rows.append({"sample_a": a, "sample_b": b, "dosage_correlation": float(value), "review": True})
    relatedness = pd.DataFrame(related_rows, columns=["sample_a", "sample_b", "dosage_correlation", "review"])

    association = bundle.result.copy()
    association["region_bin"] = association["chrom"].astype(str) + ":" + (pd.to_numeric(association["position"], errors="coerce") // 1_000_000).fillna(-1).astype(int).astype(str) + "Mb"
    regional = association.groupby(["chrom", "region_bin"], as_index=False).agg(top_signal=("minus_log10_p", "max"), variants=("variant", "count"), lead_variant=("variant", "first"))
    credible = association.nlargest(min(50, len(association)), "priority_score").copy()
    if not credible.empty:
        weights = np.exp(credible["minus_log10_p"].fillna(0) - credible["minus_log10_p"].fillna(0).max())
        credible["posterior_proxy"] = weights / weights.sum() if weights.sum() else 0.0
        credible["cumulative_posterior"] = credible["posterior_proxy"].cumsum()
        credible["credible_95"] = credible["cumulative_posterior"] <= 0.95

    prs = bundle.extras.get("prs_scores", pd.DataFrame()).copy()
    calibration = pd.DataFrame()
    if not prs.empty and "phenotype" in prs.columns:
        prs["prs_decile"] = pd.qcut(pd.to_numeric(prs["prs_score"], errors="coerce").rank(method="first"), q=min(10, len(prs)), labels=False, duplicates="drop")
        calibration = prs.groupby("prs_decile", as_index=False).agg(mean_prs=("prs_score", "mean"), observed_rate=("phenotype", "mean"), samples=("sample", "nunique"))

    qc = [
        {"check": "Variant call rate", "status": "Pass" if variant_qc["pass_call_rate"].mean() >= 0.95 else "Review", "value": int((~variant_qc["pass_call_rate"]).sum()), "detail": f"Threshold {p['min_call_rate']}"},
        {"check": "Minor allele frequency", "status": "Pass" if variant_qc["pass_maf"].mean() >= 0.95 else "Review", "value": int((~variant_qc["pass_maf"]).sum()), "detail": f"Threshold {p['min_maf']}"},
        {"check": "Hardy-Weinberg", "status": "Pass" if variant_qc["pass_hwe"].mean() >= 0.95 else "Review", "value": int((~variant_qc["pass_hwe"]).sum()), "detail": f"Screening threshold {p['hwe_threshold']}"},
        {"check": "Relatedness proxy", "status": "Review" if len(relatedness) else "Pass", "value": len(relatedness), "detail": "High dosage-correlation sample pairs"},
    ]
    metrics = {"qc_failed_variants": int((~(variant_qc["pass_call_rate"] & variant_qc["pass_maf"] & variant_qc["pass_hwe"])).sum()), "related_pairs": len(relatedness), "credible_set_candidates": int(credible.get("credible_95", pd.Series(dtype=bool)).sum())}
    return {"sample_qc": sample_qc, "variant_qc": variant_qc, "relatedness": relatedness, "regional_summary": regional, "fine_mapping_proxy": credible, "prs_calibration": calibration}, qc, metrics


def _epigenomics_extras(data: pd.DataFrame, bundle: AnalysisBundle, p: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]], dict[str, Any]]:
    frame = data.copy()
    frame["signal"] = _num(frame.get("signal"), 0)
    frame["width_bp"] = (_num(frame.get("end"), 0) - _num(frame.get("start"), 0)).abs()
    sample_qc = frame.groupby(["sample", "condition"], as_index=False).agg(regions=("region", "nunique"), total_signal=("signal", "sum"), median_signal=("signal", "median"), median_width=("width_bp", "median"))
    balance = sample_qc.groupby("condition", as_index=False).agg(samples=("sample", "nunique"), median_regions=("regions", "median"), median_signal=("total_signal", "median"))
    region_annot = bundle.result.copy()
    region_annot["regulatory_class"] = np.select([
        region_annot.get("gene", pd.Series("Unknown", index=region_annot.index)).astype(str).ne("Unknown") & (pd.to_numeric(region_annot.get("start"), errors="coerce") % 3 == 0),
        region_annot.get("gene", pd.Series("Unknown", index=region_annot.index)).astype(str).ne("Unknown"),
    ], ["Promoter-proximal", "Candidate enhancer"], default="Distal/intergenic")
    motif_enrichment = region_annot.groupby("motif", as_index=False).agg(regions=("region", "count"), significant=("q_value", lambda x: int((pd.to_numeric(x, errors="coerce") <= 0.05).sum())), mean_effect=("log2_fold_change", "mean"), mean_priority=("priority_score", "mean"))
    motif_enrichment["enrichment_proxy"] = motif_enrichment["significant"] / motif_enrichment["regions"].replace(0, np.nan)
    genome_bins = frame.assign(bin=(pd.to_numeric(frame["start"], errors="coerce") // 1_000_000).fillna(-1).astype(int)).groupby(["chrom", "bin", "condition"], as_index=False).agg(mean_signal=("signal", "mean"), regions=("region", "nunique"))
    rna_concordance = region_annot[[c for c in ["region", "gene", "log2_fold_change", "methylation", "priority_score"] if c in region_annot.columns]].copy()
    if "methylation" in rna_concordance.columns:
        rna_concordance["regulatory_concordance"] = np.sign(rna_concordance["log2_fold_change"].fillna(0)) * (1 - rna_concordance["methylation"].fillna(0.5))
    qc = [
        {"check": "Replicates per condition", "status": "Pass" if (balance["samples"] >= int(p["min_replicates"])).all() else "Block", "value": int((balance["samples"] < int(p["min_replicates"])).sum()), "detail": f"Minimum {p['min_replicates']}"},
        {"check": "Region signal", "status": "Pass" if (sample_qc["median_signal"] >= float(p["min_signal"])).mean() >= 0.8 else "Review", "value": int((sample_qc["median_signal"] < float(p["min_signal"])).sum()), "detail": f"Median signal threshold {p['min_signal']}"},
        {"check": "Coordinate validity", "status": "Pass" if (frame["width_bp"] > 0).all() else "Block", "value": int((frame["width_bp"] <= 0).sum()), "detail": "End must be greater than start"},
    ]
    metrics = {"conditions": int(frame["condition"].nunique()), "low_signal_samples": int((sample_qc["median_signal"] < float(p["min_signal"])).sum()), "promoter_regions": int((region_annot["regulatory_class"] == "Promoter-proximal").sum())}
    return {"sample_qc": sample_qc, "condition_balance": balance, "region_annotations": region_annot, "motif_enrichment": motif_enrichment, "genome_bins": genome_bins, "rna_concordance_deep": rna_concordance}, qc, metrics


def _pgx_extras(data: pd.DataFrame, bundle: AnalysisBundle, p: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]], dict[str, Any]]:
    result = bundle.result.copy()
    coverage_col = next((c for c in ["coverage", "depth", "locus_coverage"] if c in result.columns), None)
    if coverage_col:
        result["coverage_value"] = _num(result[coverage_col], 0)
    else:
        result["coverage_value"] = 30.0
    result["coverage_pass"] = result["coverage_value"] >= float(p["min_coverage"])
    diplotype = bundle.extras.get("phenotypes", pd.DataFrame()).copy()
    if not diplotype.empty:
        diplotype["diplotype_confidence"] = np.clip(pd.to_numeric(diplotype.get("max_evidence"), errors="coerce").fillna(0.2) * np.where(pd.to_numeric(diplotype.get("copy_number"), errors="coerce").fillna(2).eq(2), 1.0, 0.8), 0, 1)
        diplotype["review_required"] = diplotype["diplotype_confidence"] < 0.75
    medication = result.groupby(["sample", "drug"], as_index=False).agg(genes=("gene", "nunique"), variants=("variant", "nunique"), max_priority=("priority_score", "max"), evidence_levels=("evidence_level", lambda x: " | ".join(sorted(set(map(str, x))))), coverage_pass=("coverage_pass", "all"))
    medication["impact_state"] = np.select([medication["max_priority"] >= 0.85, medication["max_priority"] >= 0.60], ["High-priority review", "Moderate-priority review"], default="Evidence limited")
    reanalysis = result.groupby(["gene", "drug"], as_index=False).agg(records=("variant", "count"), guideline_sources=("guideline_source", lambda x: len(set(map(str, x)))) if "guideline_source" in result.columns else ("variant", "count"), max_priority=("priority_score", "max"))
    reanalysis["reanalysis_trigger"] = (reanalysis["guideline_sources"] > 1) | (reanalysis["max_priority"] < 0.6)
    qc = [
        {"check": "Locus coverage", "status": "Pass" if result["coverage_pass"].mean() >= 0.95 else "Review", "value": int((~result["coverage_pass"]).sum()), "detail": f"Minimum coverage {p['min_coverage']}"},
        {"check": "Evidence conflicts", "status": "Review" if int(bundle.summary.get("metrics", {}).get("conflicts", 0)) else "Pass", "value": int(bundle.summary.get("metrics", {}).get("conflicts", 0)), "detail": "Conflicting evidence levels per sample/drug"},
        {"check": "Clinical boundary", "status": "Research use", "value": 0, "detail": "No prescribing recommendation is generated"},
    ]
    metrics = {"coverage_failures": int((~result["coverage_pass"]).sum()), "medication_reviews": int((medication["impact_state"] != "Evidence limited").sum()), "reanalysis_triggers": int(reanalysis["reanalysis_trigger"].sum())}
    return {"locus_coverage": result[[c for c in ["sample", "gene", "variant", "coverage_value", "coverage_pass"] if c in result.columns]], "diplotype_confidence": diplotype, "medication_impact": medication, "reanalysis_queue": reanalysis}, qc, metrics


def _sv_extras(data: pd.DataFrame, bundle: AnalysisBundle, p: dict[str, Any], *, circular: bool = False) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]], dict[str, Any]]:
    result = bundle.result.copy()
    result["start_num"] = _num(result.get("start"), 0)
    result["end_num"] = _num(result.get("end"), 0)
    result["support_num"] = _num(result.get("support"), 0)
    result["af_num"] = _num(result.get("allele_fraction"), 0.5)
    result["consensus_bin"] = (result["start_num"] // max(1, int(p.get("merge_distance", 1000)))).astype(int)
    consensus = result.groupby(["sample", "chrom", "event_type", "consensus_bin"], as_index=False).agg(events=("event_id", "nunique"), callers=("caller", "nunique") if "caller" in result.columns else ("event_id", "nunique"), start=("start_num", "min"), end=("end_num", "max"), support=("support_num", "sum"), max_priority=("priority_score", "max"))
    consensus["consensus_level"] = np.select([consensus["callers"] >= 3, consensus["callers"] >= 2], ["Strong multi-caller", "Multi-caller"], default="Single caller")
    mosaic = result.loc[result["af_num"].between(0.01, float(p.get("mosaic_vaf_max", 0.35)))].copy()
    repeat = result.loc[result["event_type"].astype(str).str.contains("STR|repeat", case=False, regex=True, na=False)].copy()
    breakpoints = result.groupby(["chrom", "consensus_bin"], as_index=False).agg(events=("event_id", "count"), samples=("sample", "nunique"), support=("support_num", "sum"), max_priority=("priority_score", "max"))
    recurrence = result.groupby(["event_type", "gene"], as_index=False).agg(samples=("sample", "nunique"), events=("event_id", "count"), max_priority=("priority_score", "max")) if "gene" in result.columns else pd.DataFrame()
    if circular:
        cn = _num(result.get("copy_number"), 0)
        result["amplified"] = cn >= float(p.get("min_copy_number", 4.0))
        topology = result.groupby(["sample", "chrom"], as_index=False).agg(events=("event_id", "count"), amplified=("amplified", "sum"), breakpoint_support=("support_num", "sum"), mean_priority=("priority_score", "mean"))
    else:
        topology = pd.DataFrame()
    qc = [
        {"check": "Read support", "status": "Pass" if (result["support_num"] >= int(p["min_support"])).mean() >= 0.9 else "Review", "value": int((result["support_num"] < int(p["min_support"])).sum()), "detail": f"Minimum support {p['min_support']}"},
        {"check": "Coordinate validity", "status": "Pass" if (result["end_num"] >= result["start_num"]).all() else "Block", "value": int((result["end_num"] < result["start_num"]).sum()), "detail": "End must not precede start"},
        {"check": "Multi-caller consensus", "status": "Pass" if (consensus["callers"] >= 2).any() else "Review", "value": int((consensus["callers"] < 2).sum()), "detail": "Single-caller events require raw-read review"},
    ]
    metrics = {"consensus_clusters": len(consensus), "mosaic_candidates": len(mosaic), "repeat_candidates": len(repeat), "recurrent_gene_events": int((recurrence.get("samples", pd.Series(dtype=float)) >= 2).sum()) if not recurrence.empty else 0}
    return {"consensus_events": consensus, "mosaic_candidates": mosaic, "repeat_candidates": repeat, "breakpoint_clusters": breakpoints, "sample_recurrence": recurrence, "topology_summary": topology}, qc, metrics


def _splicing_extras(data: pd.DataFrame, bundle: AnalysisBundle, p: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]], dict[str, Any]]:
    result = bundle.result.copy()
    group_counts = data.groupby("group")["sample"].nunique().rename("samples").reset_index()
    result["support_pass"] = _num(result.get("junction_support"), 0) >= int(p["min_junction_support"])
    result["effect_pass"] = _num(result.get("delta_psi"), 0).abs() >= float(p["min_delta_psi"])
    result["isoform_switch"] = result["support_pass"] & result["effect_pass"] & (pd.to_numeric(result.get("q_value"), errors="coerce").fillna(1) <= 0.10)
    gene_stats = result.groupby("gene", as_index=False).agg(events=("event", "count"), mean_psi=("mean_psi", "mean"), max_delta_psi=("delta_psi", lambda x: float(pd.to_numeric(x, errors="coerce").abs().max())), max_priority=("priority_score", "max"))
    sd = float(gene_stats["mean_psi"].std(ddof=0))
    gene_stats["outlier_z"] = 0.0 if not np.isfinite(sd) or sd == 0 else (gene_stats["mean_psi"] - gene_stats["mean_psi"].mean()) / sd
    outliers = gene_stats.loc[gene_stats["outlier_z"].abs() >= 2].copy()
    fusion = result.loc[result["event"].astype(str).str.contains("fusion", case=False, na=False)].copy()
    result["nmd_proxy"] = result["event"].astype(str).str.contains("exon_skip|intron_retention|alt_", case=False, regex=True, na=False) & (_num(result.get("delta_psi"), 0).abs() >= 0.2)
    qc = [
        {"check": "Group sample counts", "status": "Pass" if (group_counts["samples"] >= int(p["min_group_samples"])).all() else "Block", "value": int((group_counts["samples"] < int(p["min_group_samples"])).sum()), "detail": f"Minimum {p['min_group_samples']} samples per group"},
        {"check": "Junction support", "status": "Pass" if result["support_pass"].mean() >= 0.8 else "Review", "value": int((~result["support_pass"]).sum()), "detail": f"Minimum {p['min_junction_support']}"},
        {"check": "PSI range", "status": "Pass" if _num(data["psi"]).between(0, 1).all() else "Block", "value": int((~_num(data["psi"]).between(0, 1)).sum()), "detail": "PSI must be between 0 and 1"},
    ]
    metrics = {"isoform_switches": int(result["isoform_switch"].sum()), "aberrant_gene_outliers": len(outliers), "nmd_proxy_events": int(result["nmd_proxy"].sum()), "fusion_candidates": len(fusion)}
    return {"group_qc": group_counts, "isoform_switches": result.loc[result["isoform_switch"]], "aberrant_splicing": outliers, "fusion_review": fusion, "nmd_proxy": result.loc[result["nmd_proxy"]], "gene_outlier_scores": gene_stats}, qc, metrics


def _immune_extras(data: pd.DataFrame, bundle: AnalysisBundle, p: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]], dict[str, Any]]:
    frame = data.copy()
    frame["count"] = _num(frame.get("count"), 0).clip(lower=0)
    chain_qc = frame.groupby(["sample", "chain"], as_index=False).agg(clonotypes=("clonotype", "nunique"), reads=("count", "sum"), cdr3_complete=("cdr3", lambda x: float(x.notna().mean())))
    public = frame.groupby("clonotype", as_index=False).agg(samples=("sample", "nunique"), total_count=("count", "sum"), chains=("chain", "nunique"), cdr3=("cdr3", "first"))
    public["public_clone"] = public["samples"] >= int(p["public_clone_min_samples"])
    clonality = frame.groupby("sample", as_index=False).agg(total_reads=("count", "sum"), clonotypes=("clonotype", "nunique"), shannon=("count", _entropy), max_clone=("count", "max"))
    clonality["clonality"] = clonality["max_clone"] / clonality["total_reads"].replace(0, np.nan)
    rarefaction_rows: list[dict[str, Any]] = []
    for sample, group in frame.groupby("sample"):
        counts = group.sort_values("count", ascending=False)["count"].to_numpy(float)
        total = counts.sum()
        for fraction in (0.1, 0.25, 0.5, 0.75, 1.0):
            target = total * fraction
            cumulative = np.cumsum(counts)
            detected = int(np.searchsorted(cumulative, target, side="left") + 1) if total > 0 else 0
            rarefaction_rows.append({"sample": sample, "sampling_fraction": fraction, "detected_clonotypes": detected})
    rarefaction = pd.DataFrame(rarefaction_rows)
    low_support = frame.loc[frame["count"] < int(p["min_clone_count"])].copy()
    qc = [
        {"check": "Clonotype support", "status": "Pass" if len(low_support) / max(1, len(frame)) <= 0.2 else "Review", "value": len(low_support), "detail": f"Minimum count {p['min_clone_count']}"},
        {"check": "CDR3 completeness", "status": "Pass" if chain_qc["cdr3_complete"].mean() >= 0.95 else "Review", "value": int((chain_qc["cdr3_complete"] < 0.95).sum()), "detail": "Sample-chain groups below 95% completeness"},
        {"check": "Sample depth balance", "status": "Pass" if clonality["total_reads"].min() >= 0.1 * clonality["total_reads"].median() else "Review", "value": int((clonality["total_reads"] < 0.1 * clonality["total_reads"].median()).sum()), "detail": "Very low-depth samples"},
    ]
    metrics = {"public_clonotypes": int(public["public_clone"].sum()), "low_support_clones": len(low_support), "median_clonality": float(clonality["clonality"].median())}
    return {"chain_qc": chain_qc, "public_clonotypes": public.loc[public["public_clone"]], "clonality": clonality, "rarefaction": rarefaction, "low_support_clones": low_support}, qc, metrics


def _multiome_extras(data: pd.DataFrame, bundle: AnalysisBundle, p: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]], dict[str, Any]]:
    frame = data.copy()
    frame["value"] = _num(frame.get("value"), 0)
    cell_qc = frame.groupby(["cell", "sample", "batch"], as_index=False).agg(features=("feature", "nunique"), modalities=("modality", "nunique"), total_signal=("value", "sum"), cluster=("cluster", "first"))
    cell_qc["low_features"] = cell_qc["features"] < int(p["min_features"])
    cell_qc["doublet_proxy"] = (cell_qc["features"] > cell_qc["features"].quantile(0.99)) & (cell_qc["total_signal"] > cell_qc["total_signal"].quantile(0.99))
    modality_depth = frame.groupby(["cell", "modality"], as_index=False).agg(features=("feature", "nunique"), total_signal=("value", "sum"))
    modality_pivot = modality_depth.pivot_table(index="cell", columns="modality", values="total_signal", fill_value=0)
    if modality_pivot.shape[1] >= 2:
        cols = list(modality_pivot.columns[:2])
        denom = modality_pivot[cols].max(axis=1).replace(0, np.nan)
        agreement = 1 - (modality_pivot[cols[0]] - modality_pivot[cols[1]]).abs() / denom
        agreement = agreement.clip(0, 1)
        modality_agreement = agreement.rename("modality_agreement").reset_index()
    else:
        modality_agreement = pd.DataFrame({"cell": modality_pivot.index, "modality_agreement": 0.0})
    marker = frame.groupby(["cluster", "modality", "feature"], as_index=False).agg(mean_value=("value", "mean"), cells=("cell", "nunique"))
    marker["marker_score"] = _rank01(marker["mean_value"]) * _rank01(marker["cells"])
    batch = cell_qc.groupby(["batch", "cluster"], as_index=False).agg(cells=("cell", "nunique"))
    batch["batch_fraction"] = batch["cells"] / batch.groupby("batch")["cells"].transform("sum").replace(0, np.nan)
    qc = [
        {"check": "Feature depth", "status": "Pass" if cell_qc["low_features"].mean() <= 0.2 else "Review", "value": int(cell_qc["low_features"].sum()), "detail": f"Minimum features {p['min_features']}"},
        {"check": "Modality completeness", "status": "Pass" if (cell_qc["modalities"] >= 2).mean() >= 0.8 else "Review", "value": int((cell_qc["modalities"] < 2).sum()), "detail": "Cells lacking paired modalities"},
        {"check": "Doublet proxy", "status": "Review" if cell_qc["doublet_proxy"].any() else "Pass", "value": int(cell_qc["doublet_proxy"].sum()), "detail": "Extreme feature and signal cells"},
    ]
    metrics = {"low_feature_cells": int(cell_qc["low_features"].sum()), "doublet_proxy_cells": int(cell_qc["doublet_proxy"].sum()), "median_modality_agreement": float(modality_agreement["modality_agreement"].median()) if not modality_agreement.empty else 0.0}
    return {"cell_qc": cell_qc, "modality_depth": modality_depth, "modality_agreement_deep": modality_agreement, "multimodal_markers": marker.nlargest(min(250, len(marker)), "marker_score"), "batch_composition": batch}, qc, metrics


def _proteogenomics_extras(data: pd.DataFrame, bundle: AnalysisBundle, p: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]], dict[str, Any]]:
    result = bundle.result.copy()
    result["peptide_length"] = result.get("peptide", pd.Series("", index=result.index)).astype(str).str.len()
    result["expression_pass"] = _num(result.get("expression"), 0) >= float(p["min_expression"])
    result["normal_tissue_pass"] = _num(result.get("normal_tissue_risk"), 1) <= float(p["max_normal_tissue_risk"])
    result["panel_eligible"] = result["expression_pass"] & result["normal_tissue_pass"] & result["peptide_length"].between(8, 30)
    panel = result.loc[result["panel_eligible"]].nlargest(int(p["panel_size"]), "priority_score").copy()
    shared = result.groupby(["peptide", "hla"], as_index=False).agg(samples=("sample", "nunique"), variants=("variant", "nunique"), max_priority=("priority_score", "max"), mean_expression=("expression", "mean") if "expression" in result.columns else ("priority_score", "mean"))
    shared["shared_candidate"] = shared["samples"] >= 2
    evidence = result.assign(evidence_tier=np.select([
        result["panel_eligible"] & (_num(result.get("ms_support"), 0) > 0),
        result["panel_eligible"],
    ], ["RNA+MS supported", "RNA supported"], default="Computational candidate")).groupby("evidence_tier", as_index=False).agg(candidates=("peptide", "count"), mean_priority=("priority_score", "mean"))
    qc = [
        {"check": "Peptide length", "status": "Pass" if result["peptide_length"].between(8, 30).mean() >= 0.95 else "Review", "value": int((~result["peptide_length"].between(8, 30)).sum()), "detail": "Expected review range 8–30 amino acids"},
        {"check": "Expression support", "status": "Pass" if result["expression_pass"].mean() >= 0.5 else "Review", "value": int((~result["expression_pass"]).sum()), "detail": f"Minimum {p['min_expression']}"},
        {"check": "Normal-tissue risk", "status": "Pass" if result["normal_tissue_pass"].mean() >= 0.8 else "Review", "value": int((~result["normal_tissue_pass"]).sum()), "detail": f"Maximum {p['max_normal_tissue_risk']}"},
    ]
    metrics = {"panel_candidates": len(panel), "shared_candidates": int(shared["shared_candidate"].sum()), "normal_tissue_failures": int((~result["normal_tissue_pass"]).sum())}
    return {"candidate_panel_deep": panel, "shared_candidates": shared.loc[shared["shared_candidate"]], "evidence_tiers": evidence, "peptide_qc": result[[c for c in ["sample", "variant", "peptide", "hla", "peptide_length", "expression_pass", "normal_tissue_pass", "panel_eligible"] if c in result.columns]]}, qc, metrics


def _grn_extras(data: pd.DataFrame, bundle: AnalysisBundle, p: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]], dict[str, Any]]:
    result = bundle.result.copy()
    activity_series = _num(result.get("activity", result.get("mean_activity", pd.Series(0.0, index=result.index))), 0)
    result["edge_confidence"] = _num(result.get("evidence"), 0).clip(0, 1) * _rank01(activity_series.abs())
    result["high_confidence_edge"] = result["edge_confidence"] >= float(p["min_edge_evidence"])
    stats_table = result.groupby("tf", as_index=False).agg(targets=("target", "nunique"), mean_activity=("mean_activity", "mean"), mean_confidence=("edge_confidence", "mean"), high_confidence_edges=("high_confidence_edge", "sum"), expression=("expression", "mean") if "expression" in result.columns else ("priority_score", "mean"))
    stats_table["master_regulator_score"] = _rank01(stats_table["targets"]) * 0.4 + _rank01(stats_table["mean_confidence"]) * 0.4 + _rank01(stats_table["expression"]) * 0.2
    perturb = stats_table.nlargest(min(50, len(stats_table)), "master_regulator_score").copy()
    perturb["predicted_knockdown_effect"] = -perturb["master_regulator_score"] * np.sign(perturb["mean_activity"].replace(0, 1))
    provenance = result[[c for c in ["tf", "target", "condition", "evidence", "motif_score", "edge_confidence", "high_confidence_edge"] if c in result.columns]].copy()
    qc = [
        {"check": "Edge evidence", "status": "Pass" if result["high_confidence_edge"].mean() >= 0.5 else "Review", "value": int((~result["high_confidence_edge"]).sum()), "detail": f"Threshold {p['min_edge_evidence']}"},
        {"check": "Network complexity", "status": "Review" if len(result) > int(p["max_edges"]) else "Pass", "value": max(0, len(result) - int(p["max_edges"])), "detail": "Interactive network is bounded; full table remains exportable"},
        {"check": "TF/target completeness", "status": "Pass" if result[["tf", "target"]].notna().all(axis=1).mean() >= 0.95 else "Review", "value": int(result[["tf", "target"]].isna().any(axis=1).sum()), "detail": "Missing network endpoints"},
    ]
    metrics = {"high_confidence_edges": int(result["high_confidence_edge"].sum()), "master_regulators": int((stats_table["master_regulator_score"] >= 0.7).sum()), "displayed_edges": min(len(result), int(p["max_edges"]))}
    return {"network_statistics": stats_table, "master_regulators": stats_table.nlargest(min(50, len(stats_table)), "master_regulator_score"), "perturbation_simulation": perturb, "edge_provenance": provenance}, qc, metrics


def _federated_extras(data: pd.DataFrame, bundle: AnalysisBundle, p: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]], dict[str, Any]]:
    result = bundle.result.copy()
    result["phenotype_pass"] = _num(result.get("phenotype_similarity"), 0) >= float(p["min_phenotype_similarity"])
    consent = result.groupby(["source", "access_status", "consent_scope"], as_index=False).agg(cases=("case_id", "nunique"), high_matches=("phenotype_pass", "sum"))
    invalid_hpo = result.loc[~result.get("phenotype", pd.Series("", index=result.index)).astype(str).str.len().gt(0)].copy()
    query_plan = result.groupby("source", as_index=False).agg(cases=("case_id", "nunique"), max_match=("priority_score", "max"), access_status=("access_status", "first"), consent_scopes=("consent_scope", lambda x: " | ".join(sorted(set(map(str, x))))))
    query_plan["query_mode"] = p["privacy_mode"]
    query_plan["action"] = np.where(query_plan["access_status"].astype(str).eq("Open metadata"), "Query metadata", "Request/consent review")
    case_summary = result.groupby("case_id", as_index=False).agg(sources=("source", "nunique"), phenotypes=("phenotype", "nunique"), genes=("gene", "nunique"), variants=("variant", "nunique"), max_match=("priority_score", "max"))
    qc = [
        {"check": "Phenotype similarity", "status": "Pass" if result["phenotype_pass"].any() else "Review", "value": int((~result["phenotype_pass"]).sum()), "detail": f"Threshold {p['min_phenotype_similarity']}"},
        {"check": "Consent/access review", "status": "Review" if (~result["access_status"].astype(str).eq("Open metadata")).any() else "Pass", "value": int((~result["access_status"].astype(str).eq("Open metadata")).sum()), "detail": "Controlled/request-required records"},
        {"check": "Phenotype identifiers", "status": "Pass" if invalid_hpo.empty else "Review", "value": len(invalid_hpo), "detail": "Empty phenotype labels"},
    ]
    metrics = {"high_similarity_matches": int(result["phenotype_pass"].sum()), "controlled_records": int((~result["access_status"].astype(str).eq("Open metadata")).sum()), "query_sources": len(query_plan)}
    return {"consent_matrix": consent, "phenopacket_qc": invalid_hpo, "federated_query_plan": query_plan, "case_summary": case_summary}, qc, metrics


def _viral_extras(data: pd.DataFrame, bundle: AnalysisBundle, p: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]], dict[str, Any]]:
    result = bundle.result.copy()
    depth = _num(result.get("depth"), 0)
    result["depth_pass_deep"] = depth >= int(p["min_depth"])
    result["minor_variant_deep"] = _num(result.get("frequency"), 0).between(float(p["minor_variant_min"]), 0.5)
    subject_depth = result.groupby("subject", as_index=False).agg(median_depth=("depth", "median") if "depth" in result.columns else ("frequency", "count"), sites=("position", "nunique"), lineages=("lineage", "nunique"))
    if "depth" in result.columns:
        med = result.groupby("subject")["depth"].transform("median").replace(0, np.nan)
        result["primer_dropout"] = depth < float(p["primer_dropout_threshold"]) * med
    else:
        result["primer_dropout"] = False
    mixed = result.groupby(["subject", "time"], as_index=False).agg(lineages=("lineage", "nunique"), variants=("position", "nunique"), max_frequency=("frequency", "max"))
    mixed["mixed_infection_proxy"] = mixed["lineages"] > 1
    transmission = result.groupby(["subject", "lineage"], as_index=False).agg(variants=("position", "nunique"), mean_frequency=("frequency", "mean"), timepoints=("time", "nunique"))
    antigenic = result.loc[result.get("gene", pd.Series("", index=result.index)).astype(str).str.contains("S|HA|NA|env", case=False, regex=True, na=False)].copy() if "gene" in result.columns else pd.DataFrame()
    qc = [
        {"check": "Depth", "status": "Pass" if result["depth_pass_deep"].mean() >= 0.9 else "Review", "value": int((~result["depth_pass_deep"]).sum()), "detail": f"Minimum depth {p['min_depth']}"},
        {"check": "Primer dropout", "status": "Review" if result["primer_dropout"].any() else "Pass", "value": int(result["primer_dropout"].sum()), "detail": "Sites below subject-relative depth threshold"},
        {"check": "Mixed infection proxy", "status": "Review" if mixed["mixed_infection_proxy"].any() else "Pass", "value": int(mixed["mixed_infection_proxy"].sum()), "detail": "Multiple lineage labels at a subject/timepoint"},
    ]
    metrics = {"minor_variants": int(result["minor_variant_deep"].sum()), "primer_dropout_sites": int(result["primer_dropout"].sum()), "mixed_infection_timepoints": int(mixed["mixed_infection_proxy"].sum()), "antigenic_candidates": len(antigenic)}
    return {"depth_qc": subject_depth, "primer_dropout": result.loc[result["primer_dropout"]], "mixed_infection": mixed, "transmission_summary": transmission, "antigenic_review": antigenic}, qc, metrics


def _annotation_extras(data: pd.DataFrame, bundle: AnalysisBundle, p: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]], dict[str, Any]]:
    result = bundle.result.copy()
    result["length_pass"] = _num(result.get("length_bp"), 0) >= int(p["min_feature_length"])
    result["completeness_pass"] = _num(result.get("completeness"), 0) >= float(p["min_completeness"])
    overlap_rows: list[dict[str, Any]] = []
    for (genome, chrom), group in result.sort_values("start").groupby(["genome", "chrom"], dropna=False):
        previous_end = -1
        previous_id = None
        for _, row in group.iterrows():
            start = float(row.get("start", 0)); end = float(row.get("end", 0))
            if start < previous_end:
                overlap_rows.append({"genome": genome, "chrom": chrom, "feature_a": previous_id, "feature_b": row.get("feature_id"), "overlap_bp": max(0, previous_end - start)})
            if end > previous_end:
                previous_end = end; previous_id = row.get("feature_id")
    overlaps = pd.DataFrame(overlap_rows, columns=["genome", "chrom", "feature_a", "feature_b", "overlap_bp"])
    orphan = result.loc[result.get("ortholog_group", pd.Series("Unassigned", index=result.index)).astype(str).isin(["Unassigned", "", "nan"])].copy()
    version = result.groupby("genome", as_index=False).agg(features=("feature_id", "nunique"), mean_completeness=("completeness", "mean"), evidence_types=("evidence", "nunique"), short_features=("length_pass", lambda x: int((~x).sum())), incomplete=("completeness_pass", lambda x: int((~x).sum())))
    qc = [
        {"check": "Feature length", "status": "Pass" if result["length_pass"].mean() >= 0.95 else "Review", "value": int((~result["length_pass"]).sum()), "detail": f"Minimum {p['min_feature_length']} bp"},
        {"check": "Completeness", "status": "Pass" if result["completeness_pass"].mean() >= 0.8 else "Review", "value": int((~result["completeness_pass"]).sum()), "detail": f"Minimum {p['min_completeness']}"},
        {"check": "Coordinate overlaps", "status": "Review" if len(overlaps) else "Pass", "value": len(overlaps), "detail": "Potential overlapping annotation conflicts"},
    ]
    metrics = {"overlap_conflicts": len(overlaps), "orphan_features": len(orphan), "short_features": int((~result["length_pass"]).sum()), "incomplete_features": int((~result["completeness_pass"]).sum())}
    return {"annotation_conflicts": overlaps, "orphan_features": orphan, "version_consistency": version, "feature_qc_deep": result[[c for c in ["genome", "feature_id", "chrom", "start", "end", "length_bp", "length_pass", "completeness", "completeness_pass", "evidence"] if c in result.columns]]}, qc, metrics


def _edna_extras(data: pd.DataFrame, bundle: AnalysisBundle, p: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]], dict[str, Any]]:
    result = bundle.result.copy()
    result["reference_pass"] = _num(result.get("reference_confidence"), 0) >= float(p["min_reference_confidence"])
    result["detection_deep"] = _num(result.get("adjusted_reads"), _num(result.get("reads"), 0)) >= int(p["min_reads"])
    controls = result.groupby("control_type", as_index=False).agg(samples=("sample", "nunique"), reads=("reads", "sum") if "reads" in result.columns else ("adjusted_reads", "sum"), detections=("detection_deep", "sum"))
    replicate = result.groupby(["site", "date", "species"], as_index=False).agg(samples=("sample", "nunique"), detections=("detection_deep", "sum"), mean_reads=("adjusted_reads", "mean") if "adjusted_reads" in result.columns else ("reads", "mean"), mean_confidence=("reference_confidence", "mean"))
    replicate["replicate_concordance"] = replicate["detections"] / replicate["samples"].replace(0, np.nan)
    ambiguity = result.loc[~result["reference_pass"]].copy()
    watch_col = next((c for c in ["watch_status", "invasive", "rare_species"] if c in result.columns), None)
    alerts = result.loc[result["detection_deep"] & result["reference_pass"]].copy()
    if watch_col:
        alerts = alerts.loc[alerts[watch_col].astype(str).str.contains("yes|true|invasive|rare|watch", case=False, regex=True, na=False)]
    else:
        alerts = alerts.nlargest(min(25, len(alerts)), "priority_score")
    qc = [
        {"check": "Reference confidence", "status": "Pass" if result["reference_pass"].mean() >= 0.9 else "Review", "value": int((~result["reference_pass"]).sum()), "detail": f"Minimum {p['min_reference_confidence']}"},
        {"check": "Negative controls", "status": "Review" if controls.loc[controls["control_type"].astype(str).str.contains("negative", case=False, na=False), "detections"].sum() > 0 else "Pass", "value": int(controls.loc[controls["control_type"].astype(str).str.contains("negative", case=False, na=False), "detections"].sum()), "detail": "Detections in negative controls"},
        {"check": "Replicate concordance", "status": "Pass" if replicate["replicate_concordance"].median() >= 0.5 else "Review", "value": int((replicate["replicate_concordance"] < 0.5).sum()), "detail": "Site/date/species groups below 50% concordance"},
    ]
    metrics = {"high_confidence_detections": int((result["detection_deep"] & result["reference_pass"]).sum()), "ambiguous_taxa": len(ambiguity), "surveillance_alerts": len(alerts)}
    return {"control_qc": controls, "replicate_concordance": replicate, "taxonomic_ambiguity": ambiguity, "surveillance_alerts": alerts}, qc, metrics


def _comparative_extras(data: pd.DataFrame, bundle: AnalysisBundle, p: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]], dict[str, Any]]:
    result = bundle.result.copy()
    result["conservation_pass"] = _num(result.get("conservation"), 0) >= float(p["min_conservation"])
    support = result.groupby("ortholog_group", as_index=False).agg(species=("species", "nunique"), mean_conservation=("conservation", "mean"), mean_activity=("activity", "mean"), motifs=("motif", "nunique"))
    support["species_pass"] = support["species"] >= int(p["min_species"])
    gain_loss = result.groupby(["ortholog_group", "species"], as_index=False).agg(activity=("activity", "mean"), conservation=("conservation", "mean"))
    gain_loss["state"] = np.select([
        (gain_loss["activity"] > gain_loss["activity"].median()) & (gain_loss["conservation"] >= float(p["min_conservation"])),
        (gain_loss["activity"] > gain_loss["activity"].median()) & (gain_loss["conservation"] < float(p["min_conservation"])),
    ], ["Conserved active", "Lineage gain"], default="Low/inactive")
    tissue = result.groupby(["tissue", "species"], as_index=False).agg(regions=("region", "nunique"), mean_activity=("activity", "mean"), mean_conservation=("conservation", "mean")) if "tissue" in result.columns else pd.DataFrame()
    qc = [
        {"check": "Conservation", "status": "Pass" if result["conservation_pass"].mean() >= 0.7 else "Review", "value": int((~result["conservation_pass"]).sum()), "detail": f"Threshold {p['min_conservation']}"},
        {"check": "Species support", "status": "Pass" if support["species_pass"].mean() >= 0.8 else "Review", "value": int((~support["species_pass"]).sum()), "detail": f"Minimum {p['min_species']} species"},
        {"check": "Tissue matching", "status": "Pass" if not tissue.empty and tissue["tissue"].nunique() >= 1 else "Review", "value": 0 if not tissue.empty else 1, "detail": "Comparable tissue context should be supplied"},
    ]
    metrics = {"lineage_gain_events": int((gain_loss["state"] == "Lineage gain").sum()), "well_supported_orthologs": int(support["species_pass"].sum()), "low_conservation_regions": int((~result["conservation_pass"]).sum())}
    return {"species_support": support, "regulatory_gain_loss": gain_loss, "tissue_matching": tissue, "conservation_qc": result[[c for c in ["species", "region", "ortholog_group", "motif", "conservation", "conservation_pass", "activity", "tissue"] if c in result.columns]]}, qc, metrics


def enhance_bundle(data: pd.DataFrame, module: BioinformaticsPeakModule, bundle: AnalysisBundle, parameters: dict[str, Any] | None = None) -> AnalysisBundle:
    p = normalise_parameters(module.key, parameters)
    extras: dict[str, pd.DataFrame] = {}
    qc: list[dict[str, Any]] = _common_qc(data, module, p)
    metrics: dict[str, Any] = {}

    if module.key == "population_gwas_peak":
        extras, module_qc, metrics = _gwas_extras(data, bundle, p)
    elif module.key == "epigenomics_peak":
        extras, module_qc, metrics = _epigenomics_extras(data, bundle, p)
    elif module.key == "pharmacogenomics_peak":
        extras, module_qc, metrics = _pgx_extras(data, bundle, p)
    elif module.key == "structural_variant_peak":
        extras, module_qc, metrics = _sv_extras(data, bundle, p)
    elif module.key == "rna_splicing_peak":
        extras, module_qc, metrics = _splicing_extras(data, bundle, p)
    elif module.key == "immune_repertoire":
        extras, module_qc, metrics = _immune_extras(data, bundle, p)
    elif module.key == "single_cell_multiome":
        extras, module_qc, metrics = _multiome_extras(data, bundle, p)
    elif module.key == "proteogenomics_peak":
        extras, module_qc, metrics = _proteogenomics_extras(data, bundle, p)
    elif module.key == "gene_regulatory_network":
        extras, module_qc, metrics = _grn_extras(data, bundle, p)
    elif module.key == "federated_genomic_discovery":
        extras, module_qc, metrics = _federated_extras(data, bundle, p)
    elif module.key == "viral_within_host":
        extras, module_qc, metrics = _viral_extras(data, bundle, p)
    elif module.key == "genome_annotation":
        extras, module_qc, metrics = _annotation_extras(data, bundle, p)
    elif module.key == "circular_dna_instability":
        extras, module_qc, metrics = _sv_extras(data, bundle, p, circular=True)
    elif module.key == "environmental_edna":
        extras, module_qc, metrics = _edna_extras(data, bundle, p)
    elif module.key == "comparative_regulatory_genomics":
        extras, module_qc, metrics = _comparative_extras(data, bundle, p)
    else:  # pragma: no cover
        module_qc = []

    contract = contract_for(module.key)
    parameter_manifest = pd.DataFrame([{"parameter": key, "value": json.dumps(value, default=str) if isinstance(value, (dict, list, tuple)) else value} for key, value in p.items()])
    reference_context = pd.DataFrame([
        {"field": "organism", "value": p.get("organism")},
        {"field": "genome_build", "value": p.get("genome_build")},
        {"field": "analysis_profile", "value": p.get("analysis_profile", contract.analysis_profiles[0])},
        {"field": "reference_assets", "value": " | ".join(contract.reference_assets)},
        {"field": "specialist_engines", "value": " | ".join(contract.specialist_engines)},
        {"field": "review_roles", "value": " | ".join(contract.review_roles)},
    ])
    provenance = pd.DataFrame([
        {"field": "schema", "value": "biointel.bioinformatics_peak.v138"},
        {"field": "module", "value": module.key},
        {"field": "generated_at_utc", "value": datetime.now(timezone.utc).isoformat()},
        {"field": "input_rows", "value": len(data)},
        {"field": "input_columns", "value": len(data.columns)},
        {"field": "input_sha256", "value": sha256(data.to_csv(index=False, lineterminator="\n", na_rep="<NA>").encode("utf-8")).hexdigest()},
        {"field": "scientific_boundary", "value": module.boundary},
    ])

    merged_extras = dict(bundle.extras)
    merged_extras.update(extras)
    merged_extras.update({"parameter_manifest": parameter_manifest, "reference_context": reference_context, "provenance": provenance})

    quality = pd.concat([bundle.quality, pd.DataFrame(qc + module_qc)], ignore_index=True)
    quality = quality.drop_duplicates(subset=["check", "detail"], keep="last").reset_index(drop=True)
    summary = dict(bundle.summary)
    summary["schema"] = "biointel.bioinformatics_peak.v138"
    summary["parameters"] = p
    summary["capabilities"] = list(contract.capabilities)
    summary["specialist_engines"] = list(contract.specialist_engines)
    summary["reference_assets"] = list(contract.reference_assets)
    summary["review_roles"] = list(contract.review_roles)
    summary["visual_count"] = 12
    summary["metrics"] = {**dict(summary.get("metrics", {})), **metrics}
    summary["quality_status"] = "Blocked" if quality["status"].astype(str).str.lower().eq("block").any() else ("Review" if quality["status"].astype(str).str.lower().eq("review").any() else "Passed")
    return replace(bundle, summary=summary, extras=merged_extras, quality=quality)
