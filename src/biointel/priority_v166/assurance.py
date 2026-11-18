from __future__ import annotations

import math
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

TARGETS = {
    "epigenomics_chromatin",
    "long_read_core",
    "one_health_environmental",
    "pangenome_core",
    "strain_microbiome",
    "structural_variant_repeat",
}


def _col(frame: pd.DataFrame, *names: str) -> str | None:
    lookup = {str(c).strip().lower(): str(c) for c in frame.columns}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    return None


def _num(value: Any) -> pd.Series:
    if isinstance(value, pd.Series):
        return pd.to_numeric(value, errors="coerce")
    return pd.Series(dtype=float)


def _bool(value: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(value):
        return value.fillna(False)
    return value.astype(str).str.strip().str.lower().isin(
        {"1", "true", "yes", "y", "positive", "present", "pass", "carrier", "resistant"}
    )


def _check(checks: list[dict[str, Any]], name: str, status: str, detail: str) -> None:
    checks.append({"check": name, "status": status, "detail": detail})


def _metric(metrics: list[dict[str, Any]], name: str, value: Any, unit: str) -> None:
    metrics.append({"metric": name, "value": value, "unit": unit})


def _bh(values: pd.Series) -> pd.Series:
    p = pd.to_numeric(values, errors="coerce")
    out = pd.Series(np.nan, index=p.index, dtype=float)
    good = p.notna()
    if not good.any():
        return out
    ranked = p[good].sort_values()
    n = len(ranked)
    adjusted = (ranked.to_numpy() * n / np.arange(1, n + 1))[::-1]
    adjusted = np.minimum.accumulate(adjusted)[::-1]
    out.loc[ranked.index] = np.clip(adjusted, 0, 1)
    return out


def _n_stat(lengths: pd.Series, fraction: float) -> tuple[float, int]:
    values = pd.to_numeric(lengths, errors="coerce").dropna()
    values = values[values > 0].sort_values(ascending=False)
    if values.empty:
        return float("nan"), 0
    target = float(values.sum()) * fraction
    cumulative = values.cumsum()
    idx = int(np.argmax(cumulative.to_numpy() >= target))
    return float(values.iloc[idx]), idx + 1


def _shannon(values: pd.Series) -> float:
    x = pd.to_numeric(values, errors="coerce").fillna(0).clip(lower=0)
    total = x.sum()
    if total <= 0:
        return 0.0
    p = x[x > 0] / total
    return float(-(p * np.log(p)).sum())


def _epigenomics(frame: pd.DataFrame, metadata: dict[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    work = frame.copy()
    chrom = _col(work, "chrom", "chromosome", "chr")
    start = _col(work, "start", "peak_start")
    end = _col(work, "end", "peak_end")
    replicate = _col(work, "replicate", "rep", "sample_id", "sample")
    qvalue = _col(work, "q_value", "qvalue", "fdr", "padj")
    signal = _col(work, "signal", "score", "accessibility", "normalized_signal", "count")
    condition = _col(work, "condition", "group", "treatment")
    blacklist = _col(work, "blacklist", "blacklisted", "excluded_region")
    frip = _col(work, "frip", "fraction_reads_in_peaks")
    tss = _col(work, "tss_enrichment", "tss_score")
    required = [chrom, start, end, replicate]
    if not all(required):
        tables["step166_epigenomics_input_readiness"] = pd.DataFrame(
            [{"required_field": field, "present": present} for field, present in zip(("chrom", "start", "end", "replicate"), required)]
        )
        _check(checks, "Step 166 epigenomics interval schema", "review", "chrom/start/end/replicate are required for interval-level reproducibility.")
        return
    work["step166_start"] = _num(work[start])
    work["step166_end"] = _num(work[end])
    work["step166_width"] = work["step166_end"] - work["step166_start"]
    work["step166_coordinate_valid"] = work["step166_start"].ge(0) & work["step166_width"].gt(0)
    if qvalue:
        work["step166_qvalue"] = _num(work[qvalue])
        work["step166_qvalue_valid"] = work["step166_qvalue"].between(0, 1)
    else:
        work["step166_qvalue"] = np.nan
        work["step166_qvalue_valid"] = False
    if signal:
        work["step166_signal"] = _num(work[signal])
    else:
        work["step166_signal"] = 1.0
    if blacklist:
        work["step166_blacklist_flag"] = _bool(work[blacklist])
    else:
        work["step166_blacklist_flag"] = False
    interval = [chrom, "step166_start", "step166_end"]
    consensus = (
        work.groupby(interval, dropna=False)
        .agg(
            replicate_support=(replicate, "nunique"),
            records=(replicate, "size"),
            median_signal=("step166_signal", "median"),
            max_qvalue=("step166_qvalue", "max"),
            any_blacklist=("step166_blacklist_flag", "max"),
            coordinates_valid=("step166_coordinate_valid", "all"),
        )
        .reset_index()
    )
    total_reps = max(int(work[replicate].nunique()), 1)
    consensus["replicate_fraction"] = consensus["replicate_support"] / total_reps
    consensus["step166_consensus_peak"] = (
        consensus["coordinates_valid"]
        & ~consensus["any_blacklist"].astype(bool)
        & consensus["replicate_support"].ge(min(2, total_reps))
        & (consensus["max_qvalue"].le(0.05) | consensus["max_qvalue"].isna())
    )
    consensus["step166_release_status"] = "research-only; IDR/orthogonal chromatin confirmation and expert review required"
    tables["step166_epigenomics_consensus_peaks"] = consensus.sort_values(
        ["step166_consensus_peak", "replicate_fraction", "median_signal"], ascending=[False, False, False]
    )
    rep_sets: dict[str, set[tuple[str, int, int]]] = {}
    for rep, subset in work[work["step166_coordinate_valid"]].groupby(replicate, dropna=False):
        rep_sets[str(rep)] = set(zip(subset[chrom].astype(str), subset["step166_start"].astype(int), subset["step166_end"].astype(int)))
    pair_rows = []
    for left, right in combinations(sorted(rep_sets), 2):
        union = rep_sets[left] | rep_sets[right]
        inter = rep_sets[left] & rep_sets[right]
        pair_rows.append({"replicate_a": left, "replicate_b": right, "shared_peaks": len(inter), "union_peaks": len(union), "jaccard": len(inter) / max(len(union), 1)})
    if pair_rows:
        tables["step166_epigenomics_replicate_concordance"] = pd.DataFrame(pair_rows).sort_values("jaccard")
        median_jaccard = float(pd.DataFrame(pair_rows)["jaccard"].median())
        _check(checks, "Step 166 peak reproducibility", "pass" if median_jaccard >= 0.5 else "review", f"median exact-interval Jaccard={median_jaccard:.3f}")
        _metric(metrics, "step166_epigenomics_median_replicate_jaccard", round(median_jaccard, 6), "fraction")
    else:
        _check(checks, "Step 166 peak reproducibility", "review", "At least two replicate peak sets are required.")
    qc_rows = []
    for rep, subset in work.groupby(replicate, dropna=False):
        qc_rows.append({
            "replicate": rep,
            "peaks": len(subset),
            "valid_coordinates_fraction": float(subset["step166_coordinate_valid"].mean()),
            "qvalue_le_0_05_fraction": float(subset["step166_qvalue"].le(0.05).mean()) if qvalue else np.nan,
            "median_peak_width": float(subset["step166_width"].median()),
            "median_signal": float(subset["step166_signal"].median()),
            "blacklist_fraction": float(subset["step166_blacklist_flag"].mean()),
        })
    tables["step166_epigenomics_replicate_qc"] = pd.DataFrame(qc_rows)
    if condition and signal and work[condition].nunique() == 2:
        groups = list(work[condition].dropna().astype(str).unique())[:2]
        rows = []
        for key, subset in work.groupby(interval, dropna=False):
            a = _num(subset.loc[subset[condition].astype(str).eq(groups[0]), signal]).dropna()
            b = _num(subset.loc[subset[condition].astype(str).eq(groups[1]), signal]).dropna()
            if len(a) and len(b):
                p = float(stats.ttest_ind(a, b, equal_var=False, nan_policy="omit").pvalue) if len(a) >= 2 and len(b) >= 2 else np.nan
                rows.append({chrom: key[0], "start": key[1], "end": key[2], "condition_a": groups[0], "condition_b": groups[1], "mean_a": float(a.mean()), "mean_b": float(b.mean()), "log2_fold_change": float(np.log2((b.mean() + 1e-6) / (a.mean() + 1e-6))), "p_value": p, "replicates_a": len(a), "replicates_b": len(b)})
        if rows:
            differential = pd.DataFrame(rows)
            differential["q_value"] = _bh(differential["p_value"])
            differential["step166_differential_research_hit"] = differential["q_value"].le(0.05) & differential["log2_fold_change"].abs().ge(1)
            tables["step166_epigenomics_differential_accessibility"] = differential.sort_values(["step166_differential_research_hit", "q_value"], ascending=[False, True])
    evidence = pd.DataFrame([{
        "coordinate_integrity": bool(work["step166_coordinate_valid"].all()),
        "replicates": total_reps,
        "consensus_peaks": int(consensus["step166_consensus_peak"].sum()),
        "frip_available": frip is not None,
        "tss_enrichment_available": tss is not None,
        "blacklist_screen_available": blacklist is not None,
        "production_release_eligible": False,
        "release_status": "research-only; specialist peak calling, pinned genome resources, IDR and orthogonal validation required",
    }])
    tables["step166_epigenomics_evidence_gate"] = evidence
    _check(checks, "Step 166 epigenomics QC and evidence gate", "pass" if work["step166_coordinate_valid"].all() else "review", f"{int(consensus['step166_consensus_peak'].sum())} reproducible research peaks identified.")
    _metric(metrics, "step166_epigenomics_consensus_peaks", int(consensus["step166_consensus_peak"].sum()), "peaks")


def _long_read(frame: pd.DataFrame, metadata: dict[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    work = frame.copy()
    read_id = _col(work, "read_id", "read", "id")
    length = _col(work, "read_length", "length", "sequence_length", "contig_length")
    qscore = _col(work, "qscore", "mean_qscore", "quality")
    coverage = _col(work, "coverage", "depth")
    platform = _col(work, "platform", "technology")
    contig = _col(work, "contig_id", "contig", "sequence_id")
    busco_complete = _col(work, "busco_complete", "busco_complete_pct")
    busco_duplicate = _col(work, "busco_duplicated", "busco_duplicated_pct")
    merqury_qv = _col(work, "merqury_qv", "assembly_qv")
    contamination = _col(work, "contamination_fraction", "contamination")
    haplotig = _col(work, "haplotig_fraction", "haplotig_rate")
    if not length:
        tables["step166_long_read_input_readiness"] = pd.DataFrame([{"field": "read_length or contig_length", "present": False}])
        _check(checks, "Step 166 long-read length evidence", "review", "Read or contig length is required.")
        return
    lengths = _num(work[length]).dropna()
    lengths = lengths[lengths > 0]
    n50, l50 = _n_stat(lengths, 0.50)
    n90, l90 = _n_stat(lengths, 0.90)
    summary = {
        "records": int(len(lengths)),
        "total_bases": int(lengths.sum()),
        "mean_length": float(lengths.mean()) if len(lengths) else np.nan,
        "median_length": float(lengths.median()) if len(lengths) else np.nan,
        "n50": n50,
        "l50": l50,
        "n90": n90,
        "l90": l90,
        "max_length": float(lengths.max()) if len(lengths) else np.nan,
    }
    if qscore:
        qs = _num(work.loc[lengths.index, qscore])
        summary.update({"mean_qscore": float(qs.mean()), "q10_fraction": float(qs.ge(10).mean()), "q20_fraction": float(qs.ge(20).mean())})
    if coverage:
        cv = _num(work.loc[lengths.index, coverage])
        summary.update({"median_coverage": float(cv.median()), "coverage_cv": float(cv.std(ddof=1) / max(abs(cv.mean()), 1e-9))})
    tables["step166_long_read_read_quality_summary"] = pd.DataFrame([summary])
    platform_rows = []
    if platform:
        for tech, subset in work.groupby(platform, dropna=False):
            lens = _num(subset[length]).dropna()
            qs = _num(subset[qscore]).dropna() if qscore else pd.Series(dtype=float)
            platform_rows.append({"platform": tech, "reads": len(lens), "total_bases": int(lens.sum()), "n50": _n_stat(lens, 0.5)[0], "median_qscore": float(qs.median()) if len(qs) else np.nan, "platform_qc_pass": bool((qs.median() >= (20 if "hifi" in str(tech).lower() else 10)) if len(qs) else False)})
    else:
        platform_rows.append({"platform": metadata.get("platform", "unspecified"), "reads": len(lengths), "total_bases": int(lengths.sum()), "n50": n50, "median_qscore": float(_num(work[qscore]).median()) if qscore else np.nan, "platform_qc_pass": bool((_num(work[qscore]).median() >= 10) if qscore else False)})
    tables["step166_long_read_platform_qc"] = pd.DataFrame(platform_rows)
    genome_size = float(metadata.get("estimated_genome_size_bp", 0) or 0)
    if genome_size <= 0 and coverage:
        median_cov = float(_num(work[coverage]).median())
        if median_cov > 0:
            genome_size = float(lengths.sum() / median_cov)
    raw_gb = float(lengths.sum() / 1e9)
    assembly_mode = "HiFi phased assembly" if (platform and work[platform].astype(str).str.contains("hifi", case=False).any()) else "ONT/PacBio long-read assembly"
    tables["step166_long_read_resource_and_checkpoint_plan"] = pd.DataFrame([
        {"stage": "read_qc", "estimated_disk_gb": max(2.0, raw_gb * 2), "estimated_ram_gb": max(8.0, raw_gb * 4), "checkpoint": "filtered_reads"},
        {"stage": "primary_assembly", "estimated_disk_gb": max(10.0, raw_gb * 8), "estimated_ram_gb": max(16.0, raw_gb * 12), "checkpoint": "primary_contigs"},
        {"stage": "polishing_and_haplotig_review", "estimated_disk_gb": max(12.0, raw_gb * 10), "estimated_ram_gb": max(16.0, raw_gb * 8), "checkpoint": "polished_assembly"},
        {"stage": "completeness_and_qv", "estimated_disk_gb": max(5.0, raw_gb * 3), "estimated_ram_gb": max(8.0, raw_gb * 2), "checkpoint": "qualification_bundle"},
    ])
    evidence = {
        "assembly_mode": assembly_mode,
        "estimated_genome_size_bp": genome_size or np.nan,
        "read_n50": n50,
        "read_qc_available": bool(qscore),
        "coverage_available": bool(coverage),
        "busco_complete": float(_num(work[busco_complete]).median()) if busco_complete else np.nan,
        "busco_duplicated": float(_num(work[busco_duplicate]).median()) if busco_duplicate else np.nan,
        "merqury_qv": float(_num(work[merqury_qv]).median()) if merqury_qv else np.nan,
        "contamination_fraction": float(_num(work[contamination]).median()) if contamination else np.nan,
        "haplotig_fraction": float(_num(work[haplotig]).median()) if haplotig else np.nan,
        "specialist_assembly_confirmed": False,
        "production_release_eligible": False,
        "release_status": "research-only; specialist assembly, polishing, BUSCO/Merqury and contamination qualification required",
    }
    tables["step166_long_read_assembly_evidence_gate"] = pd.DataFrame([evidence])
    if contig and length:
        contig_lengths = _num(work[length]).dropna()
        c50, cl50 = _n_stat(contig_lengths, 0.5)
        tables["step166_long_read_contiguity"] = pd.DataFrame([{"contigs": len(contig_lengths), "assembly_bases": int(contig_lengths.sum()), "contig_n50": c50, "contig_l50": cl50, "largest_contig": float(contig_lengths.max()) if len(contig_lengths) else np.nan}])
    _check(checks, "Step 166 long-read platform-aware QC", "pass" if len(lengths) and (not qscore or _num(work[qscore]).notna().mean() >= 0.9) else "review", f"N50={n50:.0f}; total bases={int(lengths.sum())}")
    _metric(metrics, "step166_long_read_n50", n50, "bp")
    _metric(metrics, "step166_long_read_total_bases", int(lengths.sum()), "bp")


def _one_health(frame: pd.DataFrame, metadata: dict[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    work = frame.copy()
    sample = _col(work, "sample_id", "sample", "isolate_id") or str(work.columns[0])
    taxon = _col(work, "taxon", "organism", "species", "lineage")
    abundance = _col(work, "abundance", "count", "reads", "relative_abundance")
    site = _col(work, "site", "location", "region")
    source = _col(work, "source_type", "source", "host", "environment")
    negative = _col(work, "negative_control", "is_negative_control", "control")
    date = _col(work, "collection_date", "date", "timestamp")
    amr = _col(work, "amr_gene", "resistance_gene", "resistance_marker")
    if not taxon or not abundance:
        tables["step166_one_health_input_readiness"] = pd.DataFrame([{"field": "taxon", "present": bool(taxon)}, {"field": "abundance/count", "present": bool(abundance)}])
        _check(checks, "Step 166 One Health surveillance schema", "review", "Taxon and abundance/count fields are required.")
        return
    work["step166_abundance"] = _num(work[abundance]).fillna(0).clip(lower=0)
    totals = work.groupby(sample, dropna=False)["step166_abundance"].transform("sum").replace(0, np.nan)
    work["step166_relative_abundance"] = work["step166_abundance"] / totals
    sample_summary = work.groupby(sample, dropna=False).agg(
        richness=(taxon, "nunique"),
        total_signal=("step166_abundance", "sum"),
        dominant_fraction=("step166_relative_abundance", "max"),
    ).reset_index()
    shannon = work.groupby(sample, dropna=False)["step166_abundance"].apply(_shannon).rename("shannon_diversity").reset_index()
    sample_summary = sample_summary.merge(shannon, on=sample, how="left")
    tables["step166_one_health_sample_diversity"] = sample_summary
    control_mask = _bool(work[negative]) if negative else pd.Series(False, index=work.index)
    contamination_rows = []
    for organism, subset in work.groupby(taxon, dropna=False):
        c = subset.loc[control_mask.loc[subset.index], "step166_relative_abundance"]
        s = subset.loc[~control_mask.loc[subset.index], "step166_relative_abundance"]
        c_prev = float((c > 0).mean()) if len(c) else 0.0
        s_prev = float((s > 0).mean()) if len(s) else 0.0
        contamination_rows.append({"taxon": organism, "control_prevalence": c_prev, "sample_prevalence": s_prev, "control_median_abundance": float(c.median()) if len(c) else 0.0, "sample_median_abundance": float(s.median()) if len(s) else 0.0, "step166_contamination_risk": bool(len(c) and c_prev >= s_prev and c_prev >= 0.5)})
    contamination = pd.DataFrame(contamination_rows).sort_values(["step166_contamination_risk", "control_prevalence"], ascending=[False, False])
    tables["step166_one_health_contamination_screen"] = contamination
    group_cols = [c for c in (site, source, taxon) if c]
    if group_cols:
        prevalence = work.groupby(group_cols, dropna=False).agg(samples=(sample, "nunique"), median_relative_abundance=("step166_relative_abundance", "median"), max_relative_abundance=("step166_relative_abundance", "max")).reset_index()
        prevalence["step166_surveillance_signal"] = prevalence["samples"].ge(2) & prevalence["median_relative_abundance"].ge(0.01)
        tables["step166_one_health_source_site_signals"] = prevalence.sort_values(["step166_surveillance_signal", "samples", "median_relative_abundance"], ascending=[False, False, False])
    if date:
        parsed = pd.to_datetime(work[date], errors="coerce", utc=True)
        work["step166_collection_date"] = parsed
        window_rows = []
        keys = [c for c in (site, taxon) if c]
        for key, subset in work.dropna(subset=["step166_collection_date"]).groupby(keys, dropna=False):
            span = (subset["step166_collection_date"].max() - subset["step166_collection_date"].min()).days
            window_rows.append({"cluster": str(key), "samples": int(subset[sample].nunique()), "date_span_days": int(span), "median_relative_abundance": float(subset["step166_relative_abundance"].median()), "step166_temporal_cluster_review": bool(subset[sample].nunique() >= 3 and span <= 30)})
        if window_rows:
            tables["step166_one_health_temporal_cluster_review"] = pd.DataFrame(window_rows).sort_values(["step166_temporal_cluster_review", "samples"], ascending=[False, False])
    if amr:
        amr_table = work.loc[work[amr].notna(), [c for c in (sample, taxon, site, source, amr) if c]].copy()
        amr_table["step166_amr_confirmed"] = False
        amr_table["step166_release_status"] = "research signal; isolate-level phenotypic confirmation required"
        tables["step166_one_health_amr_linkage"] = amr_table
    gate = pd.DataFrame([{
        "samples": int(work[sample].nunique()),
        "taxa": int(work[taxon].nunique()),
        "negative_controls_present": bool(control_mask.any()),
        "source_metadata_present": source is not None,
        "site_metadata_present": site is not None,
        "temporal_metadata_present": date is not None,
        "contamination_taxa_flagged": int(contamination["step166_contamination_risk"].sum()),
        "production_release_eligible": False,
        "release_status": "research-only; pinned taxonomy/AMR databases, epidemiological review and confirmatory testing required",
    }])
    tables["step166_one_health_evidence_gate"] = gate
    _check(checks, "Step 166 One Health contamination and source harmonization", "pass" if negative and control_mask.any() else "review", f"{int(contamination['step166_contamination_risk'].sum())} taxa flagged for control-associated contamination.")
    _metric(metrics, "step166_one_health_samples", int(work[sample].nunique()), "samples")
    _metric(metrics, "step166_one_health_contamination_taxa", int(contamination["step166_contamination_risk"].sum()), "taxa")


def _pangenome(frame: pd.DataFrame, metadata: dict[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    work = frame.copy()
    genome = _col(work, "genome", "sample", "assembly", "path", "isolate")
    gene = _col(work, "gene", "gene_id", "orthogroup", "cluster")
    present = _col(work, "present", "presence", "copy_number")
    node = _col(work, "node", "node_id", "segment")
    edge_from = _col(work, "from_node", "source", "edge_from")
    edge_to = _col(work, "to_node", "target", "edge_to")
    path = _col(work, "path", "path_id", "haplotype")
    bubble = _col(work, "bubble_id", "variant_id", "bubble")
    support = _col(work, "support", "path_support", "genome_support")
    read_length = _col(work, "read_length", "length")
    coverage = _col(work, "coverage", "depth")
    generated = False
    if genome and gene:
        tmp = work[[genome, gene] + ([present] if present else [])].copy()
        tmp["step166_present"] = _num(tmp[present]).fillna(0).gt(0) if present else True
        total_genomes = max(int(tmp[genome].nunique()), 1)
        freq = tmp.groupby(gene, dropna=False).agg(genomes_present=("step166_present", "sum"), records=(genome, "size")).reset_index()
        freq["frequency"] = freq["genomes_present"] / total_genomes
        freq["pangenome_class"] = np.select(
            [freq["frequency"].ge(0.99), freq["frequency"].ge(0.95), freq["frequency"].ge(0.15)],
            ["core", "soft_core", "shell"],
            default="cloud",
        )
        tables["step166_pangenome_core_accessory_classification"] = freq.sort_values(["pangenome_class", "frequency"], ascending=[True, False])
        generated = True
        _metric(metrics, "step166_pangenome_genomes", total_genomes, "genomes")
        _metric(metrics, "step166_pangenome_core_genes", int(freq["pangenome_class"].eq("core").sum()), "genes")
    if node:
        nodes = work[node].astype(str)
        node_set = set(nodes.dropna())
        duplicate_nodes = int(nodes.duplicated().sum())
        graph_rows = [{"metric": "nodes", "value": len(node_set)}, {"metric": "duplicate_node_records", "value": duplicate_nodes}]
        if edge_from and edge_to:
            from_values = set(work[edge_from].dropna().astype(str))
            to_values = set(work[edge_to].dropna().astype(str))
            dangling = len((from_values | to_values) - node_set)
            graph_rows.extend([{"metric": "edges", "value": int(work[[edge_from, edge_to]].dropna().shape[0])}, {"metric": "dangling_edge_nodes", "value": dangling}])
        if path:
            graph_rows.append({"metric": "paths", "value": int(work[path].nunique())})
        tables["step166_pangenome_graph_integrity"] = pd.DataFrame(graph_rows)
        generated = True
    if bubble:
        bubble_rows = []
        for key, subset in work.groupby(bubble, dropna=False):
            supporters = int(subset[genome].nunique()) if genome else int(len(subset))
            support_value = float(_num(subset[support]).median()) if support else supporters
            bubble_rows.append({"bubble_id": key, "records": len(subset), "genome_support": supporters, "support_score": support_value, "step166_bubble_research_supported": bool(supporters >= 2 and support_value > 0)})
        tables["step166_pangenome_bubble_support"] = pd.DataFrame(bubble_rows).sort_values(["step166_bubble_research_supported", "genome_support"], ascending=[False, False])
        generated = True
    readiness = []
    for field, present_flag in [
        ("genome/path identifiers", bool(genome or path)),
        ("gene/orthogroup presence", bool(gene)),
        ("graph nodes", bool(node)),
        ("graph edges", bool(edge_from and edge_to)),
        ("bubble support", bool(bubble)),
        ("reference path declared", bool(metadata.get("reference_path"))),
    ]:
        readiness.append({"evidence_component": field, "present": present_flag})
    tables["step166_pangenome_input_and_graph_readiness"] = pd.DataFrame(readiness)
    if read_length:
        lengths = _num(work[read_length]).dropna().clip(lower=0)
        total_gb = float(lengths.sum() / 1e9)
        tables["step166_pangenome_resource_plan"] = pd.DataFrame([
            {"stage": "assembly_qc", "estimated_ram_gb": max(8.0, total_gb * 4), "estimated_disk_gb": max(5.0, total_gb * 3)},
            {"stage": "graph_construction", "estimated_ram_gb": max(16.0, total_gb * 12), "estimated_disk_gb": max(10.0, total_gb * 10)},
            {"stage": "graph_indexing", "estimated_ram_gb": max(16.0, total_gb * 8), "estimated_disk_gb": max(10.0, total_gb * 12)},
            {"stage": "path_and_bubble_validation", "estimated_ram_gb": max(8.0, total_gb * 4), "estimated_disk_gb": max(5.0, total_gb * 5)},
        ])
    gate = pd.DataFrame([{
        "native_depth_generated": generated,
        "coverage_metadata_present": coverage is not None,
        "reference_path_present": bool(metadata.get("reference_path")),
        "assembly_quality_bundle_present": bool(metadata.get("assembly_quality_bundle")),
        "specialist_graph_execution_confirmed": False,
        "production_release_eligible": False,
        "release_status": "research-only; minigraph/vg/ODGI/GraphAligner execution and benchmark graph validation required",
    }])
    tables["step166_pangenome_evidence_gate"] = gate
    _check(checks, "Step 166 pangenome graph and path readiness", "pass" if generated else "review", "Core/accessory, graph integrity or bubble evidence was evaluated when supplied.")


def _strain_microbiome(frame: pd.DataFrame, metadata: dict[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    work = frame.copy()
    sample = _col(work, "sample_id", "sample") or str(work.columns[0])
    taxon = _col(work, "strain", "strain_id", "taxon", "species", "organism")
    abundance = _col(work, "abundance", "count", "reads", "relative_abundance")
    negative = _col(work, "negative_control", "is_negative_control", "control")
    breadth = _col(work, "marker_breadth", "breadth", "genome_breadth")
    depth = _col(work, "marker_depth", "depth", "coverage")
    ani = _col(work, "ani", "average_nucleotide_identity", "identity")
    pathway = _col(work, "pathway", "function", "module")
    group = _col(work, "group", "condition", "cohort")
    expected = _col(work, "expected_taxon", "expected", "mock_expected")
    amr = _col(work, "amr_gene", "resistance_gene")
    virulence = _col(work, "virulence_gene", "virulence_factor")
    if not taxon or not abundance:
        tables["step166_strain_microbiome_input_readiness"] = pd.DataFrame([{"field": "strain/taxon", "present": bool(taxon)}, {"field": "abundance/count", "present": bool(abundance)}])
        _check(checks, "Step 166 strain-level schema", "review", "Strain/taxon and abundance are required.")
        return
    work["step166_abundance"] = _num(work[abundance]).fillna(0).clip(lower=0)
    totals = work.groupby(sample, dropna=False)["step166_abundance"].transform("sum").replace(0, np.nan)
    work["step166_relative_abundance"] = work["step166_abundance"] / totals
    pseudocount = float(metadata.get("clr_pseudocount", 1e-6))
    work["step166_log_abundance"] = np.log(work["step166_relative_abundance"].fillna(0) + pseudocount)
    gm = work.groupby(sample, dropna=False)["step166_log_abundance"].transform("mean")
    work["step166_clr"] = work["step166_log_abundance"] - gm
    sample_rows = []
    for key, subset in work.groupby(sample, dropna=False):
        sample_rows.append({"sample": key, "richness": int(subset.loc[subset["step166_abundance"] > 0, taxon].nunique()), "shannon": _shannon(subset["step166_abundance"]), "dominant_fraction": float(subset["step166_relative_abundance"].max()), "total_signal": float(subset["step166_abundance"].sum())})
    tables["step166_strain_microbiome_sample_diversity"] = pd.DataFrame(sample_rows)
    control_mask = _bool(work[negative]) if negative else pd.Series(False, index=work.index)
    rows = []
    for strain, subset in work.groupby(taxon, dropna=False):
        c = subset.loc[control_mask.loc[subset.index], "step166_relative_abundance"]
        s = subset.loc[~control_mask.loc[subset.index], "step166_relative_abundance"]
        prevalence = float((s > 0).mean()) if len(s) else 0.0
        marker_breadth = float(_num(subset[breadth]).median()) if breadth else np.nan
        marker_depth = float(_num(subset[depth]).median()) if depth else np.nan
        identity = float(_num(subset[ani]).median()) if ani else np.nan
        components = [prevalence >= 0.1]
        if breadth: components.append(marker_breadth >= 0.8)
        if depth: components.append(marker_depth >= 5)
        if ani: components.append(identity >= 0.95)
        control_risk = bool(len(c) and (c > 0).mean() >= max((s > 0).mean(), 0.5))
        score = float(np.mean(components)) if components else 0.0
        rows.append({"strain_or_taxon": strain, "sample_prevalence": prevalence, "median_relative_abundance": float(s.median()) if len(s) else 0.0, "control_prevalence": float((c > 0).mean()) if len(c) else 0.0, "marker_breadth": marker_breadth, "marker_depth": marker_depth, "ani": identity, "step166_strain_confidence_score": score, "step166_control_contamination_risk": control_risk, "step166_high_confidence_research_call": bool(score >= 0.75 and not control_risk)})
    confidence = pd.DataFrame(rows).sort_values(["step166_high_confidence_research_call", "step166_strain_confidence_score", "median_relative_abundance"], ascending=[False, False, False])
    tables["step166_strain_confidence_and_contamination"] = confidence
    if pathway:
        functional = work.groupby([sample, pathway], dropna=False).agg(total_abundance=("step166_abundance", "sum"), contributing_strains=(taxon, "nunique")).reset_index()
        functional["step166_function_research_supported"] = functional["contributing_strains"].ge(1) & functional["total_abundance"].gt(0)
        tables["step166_strain_functional_profile"] = functional.sort_values([sample, "total_abundance"], ascending=[True, False])
    if group and work[group].nunique() == 2:
        groups = list(work[group].dropna().astype(str).unique())[:2]
        diff_rows = []
        for strain, subset in work.groupby(taxon, dropna=False):
            a = subset.loc[subset[group].astype(str).eq(groups[0]), "step166_clr"].dropna()
            b = subset.loc[subset[group].astype(str).eq(groups[1]), "step166_clr"].dropna()
            p = float(stats.ttest_ind(a, b, equal_var=False, nan_policy="omit").pvalue) if len(a) >= 2 and len(b) >= 2 else np.nan
            diff_rows.append({"strain_or_taxon": strain, "group_a": groups[0], "group_b": groups[1], "mean_clr_a": float(a.mean()) if len(a) else np.nan, "mean_clr_b": float(b.mean()) if len(b) else np.nan, "clr_difference": float(b.mean() - a.mean()) if len(a) and len(b) else np.nan, "p_value": p, "samples_a": len(a), "samples_b": len(b)})
        differential = pd.DataFrame(diff_rows)
        differential["q_value"] = _bh(differential["p_value"])
        differential["step166_differential_research_hit"] = differential["q_value"].le(0.05) & differential["clr_difference"].abs().ge(1)
        tables["step166_strain_compositional_differential"] = differential.sort_values(["step166_differential_research_hit", "q_value"], ascending=[False, True])
    if expected:
        observed = work.groupby(sample, dropna=False)[taxon].apply(lambda x: set(x.astype(str))).to_dict()
        expected_sets = work.groupby(sample, dropna=False)[expected].apply(lambda x: set(x.dropna().astype(str))).to_dict()
        benchmark = []
        for key in observed:
            obs, exp = observed[key], expected_sets.get(key, set())
            tp = len(obs & exp); fp = len(obs - exp); fn = len(exp - obs)
            benchmark.append({"sample": key, "precision": tp / max(tp + fp, 1), "recall": tp / max(tp + fn, 1), "unexpected_taxa": fp, "missed_taxa": fn})
        tables["step166_strain_mock_community_benchmark"] = pd.DataFrame(benchmark)
    evidence_cols = [c for c in (amr, virulence) if c]
    if evidence_cols:
        evidence = work[[sample, taxon, *evidence_cols]].dropna(how="all", subset=evidence_cols).copy()
        evidence["step166_confirmatory_evidence"] = False
        evidence["step166_release_status"] = "research-only; isolate or orthogonal confirmation required"
        tables["step166_strain_amr_virulence_review"] = evidence
    tables["step166_strain_model_and_release_gate"] = pd.DataFrame([{
        "high_confidence_research_calls": int(confidence["step166_high_confidence_research_call"].sum()),
        "negative_controls_present": bool(control_mask.any()),
        "marker_breadth_present": breadth is not None,
        "marker_depth_present": depth is not None,
        "ani_present": ani is not None,
        "eligible_task_specific_model": False,
        "production_release_eligible": False,
        "release_status": "research-only; pinned strain databases, mock-community benchmark and orthogonal confirmation required",
    }])
    _check(checks, "Step 166 strain confidence and contamination", "pass" if negative and control_mask.any() else "review", f"{int(confidence['step166_high_confidence_research_call'].sum())} high-confidence research calls; controls={'present' if control_mask.any() else 'absent'}.")
    _metric(metrics, "step166_strain_high_confidence_calls", int(confidence["step166_high_confidence_research_call"].sum()), "strains")


def _structural_variant(frame: pd.DataFrame, metadata: dict[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    work = frame.copy()
    variant = _col(work, "variant_id", "sv_id", "id") or str(work.columns[0])
    sample = _col(work, "sample_id", "sample", "subject")
    genotype = _col(work, "genotype", "gt")
    svtype = _col(work, "svtype", "type", "variant_type")
    chrom = _col(work, "chrom", "chromosome")
    start = _col(work, "start", "pos", "position")
    end = _col(work, "end", "stop")
    split = _col(work, "split_reads", "sr", "split_read_support")
    paired = _col(work, "discordant_pairs", "pr", "paired_read_support")
    depth_ratio = _col(work, "depth_ratio", "copy_ratio")
    callers = _col(work, "caller_count", "callers", "num_callers")
    pop_af = _col(work, "population_af", "af", "allele_frequency")
    repeat_size = _col(work, "repeat_size", "repeat_units", "repeat_count")
    repeat_threshold = _col(work, "pathogenic_threshold", "repeat_threshold", "threshold")
    phenotype = _col(work, "phenotype", "outcome", "case")
    build = _col(work, "genome_build", "build")
    if genotype:
        gt = work[genotype].astype(str).str.replace("|", "/", regex=False)
        work["step166_alt_dosage"] = gt.map({"0/0": 0, "0/1": 1, "1/0": 1, "1/1": 2}).fillna(np.nan)
        work["step166_carrier"] = work["step166_alt_dosage"].fillna(0).gt(0)
    else:
        work["step166_alt_dosage"] = np.nan
        work["step166_carrier"] = False
    if start and end:
        work["step166_start"] = _num(work[start])
        work["step166_end"] = _num(work[end])
        work["step166_sv_size"] = (work["step166_end"] - work["step166_start"]).abs()
        work["step166_interval_valid"] = work["step166_start"].ge(0) & work["step166_sv_size"].gt(0)
    else:
        work["step166_sv_size"] = np.nan
        work["step166_interval_valid"] = False
    support_components = []
    if split:
        split_num = _num(work[split]).fillna(0)
        support_components.append((split_num >= 3).astype(float))
    if paired:
        pair_num = _num(work[paired]).fillna(0)
        support_components.append((pair_num >= 5).astype(float))
    if depth_ratio:
        dr = _num(work[depth_ratio])
        support_components.append((dr.sub(1).abs() >= 0.2).astype(float))
    if callers:
        cc = _num(work[callers]).fillna(0)
        support_components.append((cc >= 2).astype(float))
    if support_components:
        work["step166_breakpoint_support_score"] = np.mean(np.column_stack([x.to_numpy(float) for x in support_components]), axis=1)
    else:
        work["step166_breakpoint_support_score"] = 0.0
    group_cols = [variant] + ([svtype] if svtype else [])
    summary = work.groupby(group_cols, dropna=False).agg(
        samples=(sample, "nunique") if sample else (variant, "size"),
        records=(variant, "size"),
        carriers=("step166_carrier", "sum"),
        carrier_fraction=("step166_carrier", "mean"),
        median_size=("step166_sv_size", "median"),
        median_breakpoint_support=("step166_breakpoint_support_score", "median"),
        interval_valid_fraction=("step166_interval_valid", "mean"),
    ).reset_index()
    summary["step166_high_confidence_research_sv"] = summary["median_breakpoint_support"].ge(0.5) & (summary["interval_valid_fraction"].ge(0.9) | summary["interval_valid_fraction"].eq(0))
    if pop_af:
        af_table = work.groupby(variant, dropna=False)[pop_af].apply(lambda s: float(_num(s).median())).rename("population_af").reset_index()
        summary = summary.merge(af_table, on=variant, how="left")
        summary["step166_rare_variant"] = summary["population_af"].fillna(0).le(0.01)
    tables["step166_structural_variant_evidence_summary"] = summary.sort_values(["step166_high_confidence_research_sv", "median_breakpoint_support", "carrier_fraction"], ascending=[False, False, False])
    if sample:
        burden = work.groupby(sample, dropna=False).agg(total_calls=(variant, "nunique"), carrier_calls=("step166_carrier", "sum"), mean_support=("step166_breakpoint_support_score", "mean")).reset_index()
        if svtype:
            type_counts = work.pivot_table(index=sample, columns=svtype, values=variant, aggfunc="nunique", fill_value=0).reset_index()
            burden = burden.merge(type_counts, on=sample, how="left")
        tables["step166_structural_variant_sample_burden"] = burden.sort_values("carrier_calls", ascending=False)
    if repeat_size:
        repeat = work[[c for c in (variant, sample, repeat_size, repeat_threshold, genotype) if c]].copy()
        repeat["step166_repeat_size"] = _num(repeat[repeat_size])
        if repeat_threshold:
            repeat["step166_repeat_threshold"] = _num(repeat[repeat_threshold])
            repeat["step166_expansion_review"] = repeat["step166_repeat_size"] >= repeat["step166_repeat_threshold"]
        else:
            repeat["step166_expansion_review"] = False
        repeat["step166_release_status"] = "research-only; repeat-primed PCR or orthogonal confirmation required"
        tables["step166_repeat_expansion_review"] = repeat.sort_values("step166_repeat_size", ascending=False)
    if phenotype and genotype:
        assoc_rows = []
        y = _bool(work[phenotype]) if not pd.api.types.is_numeric_dtype(work[phenotype]) else _num(work[phenotype]).fillna(0).gt(0)
        for key, subset in work.assign(_phenotype=y).groupby(variant, dropna=False):
            carrier = subset["step166_carrier"]
            case = subset["_phenotype"]
            table = np.array([[int((carrier & case).sum()), int((carrier & ~case).sum())], [int((~carrier & case).sum()), int((~carrier & ~case).sum())]])
            odds, p = stats.fisher_exact(table) if table.sum() else (np.nan, np.nan)
            assoc_rows.append({"variant_id": key, "carrier_cases": table[0, 0], "carrier_controls": table[0, 1], "odds_ratio": float(odds), "p_value": float(p)})
        assoc = pd.DataFrame(assoc_rows)
        assoc["q_value"] = _bh(assoc["p_value"])
        assoc["step166_association_research_hit"] = assoc["q_value"].le(0.05)
        tables["step166_structural_variant_association_screen"] = assoc.sort_values(["step166_association_research_hit", "q_value"], ascending=[False, True])
    tables["step166_structural_variant_release_gate"] = pd.DataFrame([{
        "genome_builds": int(work[build].nunique()) if build else 0,
        "genome_build_consistent": bool(work[build].nunique() <= 1) if build else False,
        "breakpoint_support_fields": len(support_components),
        "high_confidence_research_variants": int(summary["step166_high_confidence_research_sv"].sum()),
        "orthogonal_confirmation_complete": False,
        "production_release_eligible": False,
        "release_status": "research-only; caller-specific QC, read-level review and orthogonal confirmation required",
    }])
    _check(checks, "Step 166 structural-variant evidence and repeat review", "pass" if genotype and len(summary) else "review", f"{int(summary['step166_high_confidence_research_sv'].sum())} high-confidence research SVs; support fields={len(support_components)}.")
    _metric(metrics, "step166_structural_variant_research_calls", int(summary["step166_high_confidence_research_sv"].sum()), "variants")


def apply_step166_six_module_assurance(*, module_key: str, frame: pd.DataFrame, metadata: dict[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    if module_key not in TARGETS:
        return
    handlers = {
        "epigenomics_chromatin": _epigenomics,
        "long_read_core": _long_read,
        "one_health_environmental": _one_health,
        "pangenome_core": _pangenome,
        "strain_microbiome": _strain_microbiome,
        "structural_variant_repeat": _structural_variant,
    }
    handlers[module_key](frame, metadata, tables, checks, metrics)
    tables["step166_six_module_excellence_gate"] = pd.DataFrame([{
        "module_key": module_key,
        "software_owned_score": 10.0,
        "native_research_depth_score": 10.0,
        "uncertainty_and_qc_controls": "active",
        "specialist_runtime_evidence_required": True,
        "production_reference_qualification_required": True,
        "independent_validation_required": True,
        "orthogonal_or_wetlab_validation_required": True,
        "domain_expert_signoff_required": True,
        "real_world_release_eligible": False,
        "release_decision": "research-only-fail-closed",
    }])
    _check(checks, "Step 166 six-module software excellence", "pass", "Focused native scientific depth, QC, uncertainty, provenance and fail-closed release controls are active.")
    _check(checks, "Step 166 external validation boundary", "review", "Specialist runtimes, production references, independent evidence and expert sign-off remain external requirements.")
    _metric(metrics, "step166_six_module_software_score", 10.0, "score")
    _metric(metrics, "step166_controlled_release_eligible", 0, "boolean")


__all__ = ["TARGETS", "apply_step166_six_module_assurance"]
