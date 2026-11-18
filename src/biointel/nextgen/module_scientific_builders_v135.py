from __future__ import annotations

import itertools
import math
import re
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from scipy import optimize, stats
from scipy.spatial import cKDTree

from .module_scientific_v135 import (
    MAX_BOOTSTRAPS,
    MAX_DEPTH_ROWS,
    MAX_NETWORK_LINKS,
    MAX_PLOT_ROWS,
    MAX_STAT_GROUPS,
    MODULE_ONLY_KEYS,
    PROFILES,
    _auc_binary,
    _bh,
    _bool,
    _clean_for_plot,
    _cox_fit,
    _factorial_design,
    _input_quality,
    _num,
    _pareto_mask,
    _plate_layout,
    _safe_div,
    _stable_rng,
    _weighted_bootstrap_effect,
    _wilson,
)

def build_module_scientific_artifacts(
    module_key: str,
    data: pd.DataFrame,
    result: pd.DataFrame,
    secondary: pd.DataFrame | None = None,
    extras: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    if module_key not in MODULE_ONLY_KEYS:
        return {"summary": {}, "tables": {}, "figures": {}, "quality": pd.DataFrame()}
    source = data.head(MAX_DEPTH_ROWS).copy() if isinstance(data, pd.DataFrame) else pd.DataFrame()
    output = result.head(MAX_DEPTH_ROWS).copy() if isinstance(result, pd.DataFrame) else pd.DataFrame()
    extra = dict(extras or {})
    tables: dict[str, pd.DataFrame] = {}
    figures: dict[str, go.Figure] = {}
    summary: dict[str, Any] = {"input_rows": len(source), "result_rows": len(output), "bounded_input": bool(isinstance(data, pd.DataFrame) and len(source) < len(data))}
    quality = _input_quality(source)
    rng = _stable_rng(module_key, source, output)

    try:
        if module_key == "digital_pathology_foundation":
            tile = source.copy()
            if not tile.empty:
                tile["tumour_probability"] = _num(tile.get("tumour_probability", 0), 0).clip(0, 1)
                tile["embedding_score"] = _num(tile.get("embedding_score", 0), 0).clip(0, 1)
                tile["tissue_fraction"] = _num(tile.get("tissue_fraction", 0), 0).clip(0, 1)
                tile["uncertainty"] = 1 - (2 * (tile["tumour_probability"] - 0.5).abs()).clip(0, 1)
                tile["ood_risk"] = 1 - tile["embedding_score"]
                tile["review_score"] = 0.45 * tile["uncertainty"] + 0.35 * tile["ood_risk"] + 0.20 * (1 - tile["tissue_fraction"])
                tile_number = tile.get("tile_id", pd.Series(np.arange(len(tile)), index=tile.index)).astype(str).str.extract(r"(\d+)")[0]
                tile["tile_number"] = pd.to_numeric(tile_number, errors="coerce").fillna(pd.Series(np.arange(len(tile)), index=tile.index)).astype(int)
                tile["tile_row"] = 0
                tile["tile_col"] = 0
                for _, group in tile.groupby("slide_id", sort=False):
                    width = max(1, int(math.ceil(math.sqrt(len(group)))))
                    tile.loc[group.index, "tile_row"] = np.arange(len(group)) // width
                    tile.loc[group.index, "tile_col"] = np.arange(len(group)) % width
                tables["tile_review_queue"] = tile.sort_values("review_score", ascending=False)
                slide = tile.groupby([c for c in ["slide_id", "site", "scanner"] if c in tile.columns], as_index=False).agg(
                    tiles=("tile_id", "count"), tissue_mean=("tissue_fraction", "mean"), tumour_mean=("tumour_probability", "mean"),
                    tumour_sd=("tumour_probability", "std"), uncertainty_mean=("uncertainty", "mean"), ood_mean=("ood_risk", "mean"), review_max=("review_score", "max")
                )
                slide["tumour_se"] = slide["tumour_sd"].fillna(0) / np.sqrt(slide["tiles"].clip(lower=1))
                slide["tumour_lower_95"] = (slide["tumour_mean"] - 1.96 * slide["tumour_se"]).clip(0, 1)
                slide["tumour_upper_95"] = (slide["tumour_mean"] + 1.96 * slide["tumour_se"]).clip(0, 1)
                tables["slide_composition_confidence"] = slide.sort_values("review_max", ascending=False)
                metrics = slide[["tissue_mean", "tumour_mean", "uncertainty_mean", "ood_mean"]].fillna(0)
                if len(metrics) >= 3:
                    scaled = (metrics - metrics.mean()) / metrics.std(ddof=0).replace(0, 1)
                    u, s, _ = np.linalg.svd(scaled.to_numpy(float), full_matrices=False)
                    slide["domain_pc1"] = u[:, 0] * s[0]
                    slide["domain_pc2"] = u[:, 1] * s[1] if len(s) > 1 else 0
                    tables["scanner_domain_projection"] = slide[[c for c in ["slide_id", "site", "scanner", "domain_pc1", "domain_pc2", "ood_mean"] if c in slide.columns]]
                    figures["scanner_domain_projection"] = px.scatter(slide, x="domain_pc1", y="domain_pc2", color="scanner" if "scanner" in slide else None, symbol="site" if "site" in slide else None, size="ood_mean", hover_name="slide_id", title="Scanner/site domain projection")
                top_slide = str(tile.groupby("slide_id")["review_score"].mean().idxmax()) if "slide_id" in tile else ""
                grid = tile.loc[tile["slide_id"].astype(str) == top_slide] if top_slide else tile.head(100)
                figures["tile_probability_map"] = px.density_heatmap(grid, x="tile_col", y="tile_row", z="tumour_probability", histfunc="avg", color_continuous_scale="RdBu_r", title=f"Tile tumour-probability map · {top_slide}")
                figures["tile_uncertainty_map"] = px.density_heatmap(grid, x="tile_col", y="tile_row", z="review_score", histfunc="avg", color_continuous_scale="Magma", title=f"Tile review/uncertainty map · {top_slide}")
                summary.update({"high_review_tiles": int((tile["review_score"] >= 0.6).sum()), "slides_with_ci": len(slide)})

        elif module_key == "long_read_epigenome":
            work = source.copy()
            required = {"region", "haplotype", "condition", "methylation_fraction", "coverage"}
            if required.issubset(work.columns):
                work["methylation_fraction"] = _num(work["methylation_fraction"])
                work["coverage"] = _num(work["coverage"], 0).clip(lower=0)
                rows: list[dict[str, Any]] = []
                for (region, haplotype), group in list(work.groupby(["region", "haplotype"]))[:MAX_STAT_GROUPS]:
                    effect, lower, upper = _weighted_bootstrap_effect(group, rng)
                    conditions = [str(v) for v in group["condition"].dropna().astype(str).unique().tolist()]
                    if len(conditions) >= 2:
                        a = group.loc[group["condition"].astype(str) == conditions[0], "methylation_fraction"]
                        b = group.loc[group["condition"].astype(str) == conditions[-1], "methylation_fraction"]
                        p_value = float(stats.mannwhitneyu(a.dropna(), b.dropna(), alternative="two-sided").pvalue) if len(a.dropna()) >= 2 and len(b.dropna()) >= 2 else float("nan")
                    else:
                        p_value = float("nan")
                    rows.append({"region": region, "haplotype": haplotype, "samples": int(group.get("sample", pd.Series(group.index)).nunique()), "weighted_delta": effect, "lower_95": lower, "upper_95": upper, "p_value": p_value, "median_coverage": float(group["coverage"].median())})
                dmr = pd.DataFrame(rows)
                if not dmr.empty:
                    dmr["q_value"] = _bh(dmr["p_value"])
                    dmr["confidence_excludes_zero"] = (dmr["lower_95"] > 0) | (dmr["upper_95"] < 0)
                    dmr["dmr_review"] = (dmr["q_value"] <= 0.05) & dmr["confidence_excludes_zero"] & (dmr["median_coverage"] >= 15)
                    tables["coverage_weighted_dmr_confidence"] = dmr.sort_values(["dmr_review", "q_value"], ascending=[False, True])
                    volcano = dmr.copy()
                    volcano["minus_log10_q"] = -np.log10(_num(volcano["q_value"], 1).clip(lower=1e-300))
                    figures["confidence_dmr_volcano"] = px.scatter(volcano, x="weighted_delta", y="minus_log10_q", error_x_minus=(volcano["weighted_delta"] - volcano["lower_95"]).clip(lower=0), error_x=(volcano["upper_95"] - volcano["weighted_delta"]).clip(lower=0), color="dmr_review", size="median_coverage", hover_name="region", title="Coverage-weighted DMR effects with bootstrap uncertainty")
                if {"position", "methylation_fraction", "coverage", "haplotype"}.issubset(work.columns):
                    lollipop = _clean_for_plot(work, 5000)
                    figures["methylation_lollipop"] = px.scatter(lollipop, x="position", y="methylation_fraction", size="coverage", color="haplotype", facet_row="condition" if lollipop["condition"].nunique() <= 4 else None, hover_data=[c for c in ["sample", "region"] if c in lollipop], title="Position-level methylation lollipop view")
                hap = work.groupby(["region", "haplotype"], as_index=False).apply(lambda g: pd.Series({"weighted_methylation": float(np.average(_num(g["methylation_fraction"]).fillna(0), weights=_num(g["coverage"], 0).clip(lower=1)))}), include_groups=False)
                tables["haplotype_weighted_methylation"] = hap
                figures["haplotype_ribbons"] = px.line(hap, x="region", y="weighted_methylation", color="haplotype", markers=True, title="Haplotype methylation ribbons")
                summary.update({"confidence_dmrs": int(tables.get("coverage_weighted_dmr_confidence", pd.DataFrame()).get("dmr_review", pd.Series(dtype=bool)).sum())})

        elif module_key == "single_cell_long_read_isoforms":
            work = source.copy()
            if {"cluster", "gene", "transcript", "umi_count"}.issubset(work.columns):
                work["umi_count"] = _num(work["umi_count"], 0).clip(lower=0)
                pseudobulk = work.groupby(["cluster", "gene", "transcript"], as_index=False).agg(umis=("umi_count", "sum"), cells=("cell", "nunique") if "cell" in work else ("transcript", "size"), full_length_rate=("full_length", lambda s: float(_bool(s).mean())) if "full_length" in work else ("umi_count", lambda s: float("nan")), median_junctions=("splice_junctions", "median") if "splice_junctions" in work else ("umi_count", lambda s: float("nan")))
                pseudobulk["cluster_gene_total"] = pseudobulk.groupby(["cluster", "gene"])["umis"].transform("sum")
                pseudobulk["usage"] = pseudobulk["umis"] / pseudobulk["cluster_gene_total"].replace(0, np.nan)
                tables["pseudobulk_isoform_usage"] = pseudobulk.sort_values("usage", ascending=False)
                tests: list[dict[str, Any]] = []
                for gene, group in list(pseudobulk.groupby("gene"))[:MAX_STAT_GROUPS]:
                    matrix = group.pivot_table(index="cluster", columns="transcript", values="umis", aggfunc="sum", fill_value=0)
                    if matrix.shape[0] >= 2 and matrix.shape[1] >= 2 and matrix.to_numpy().sum() > 0:
                        try:
                            chi2, p_value, dof, _ = stats.chi2_contingency(matrix.to_numpy() + 0.5)
                        except Exception:
                            chi2, p_value, dof = float("nan"), float("nan"), 0
                        entropy = float(np.mean([stats.entropy(row[row > 0], base=2) for row in matrix.to_numpy() if np.any(row > 0)]))
                        tests.append({"gene": gene, "clusters": matrix.shape[0], "isoforms": matrix.shape[1], "chi_square": chi2, "degrees_freedom": dof, "p_value": p_value, "mean_usage_entropy": entropy})
                usage_tests = pd.DataFrame(tests)
                if not usage_tests.empty:
                    usage_tests["q_value"] = _bh(usage_tests["p_value"])
                    usage_tests["differential_usage_review"] = usage_tests["q_value"] <= 0.05
                    tables["differential_isoform_usage"] = usage_tests.sort_values("q_value")
                top_genes = pseudobulk.groupby("gene")["umis"].sum().nlargest(20).index
                plot = pseudobulk.loc[pseudobulk["gene"].isin(top_genes)]
                figures["isoform_usage_heatmap"] = px.density_heatmap(plot, x="cluster", y="gene", z="usage", histfunc="max", title="Dominant isoform usage by cluster")
                figures["transcript_support_landscape"] = px.scatter(_clean_for_plot(pseudobulk), x="usage", y="full_length_rate", size="cells", color="cluster", hover_name="transcript", facet_col="gene" if len(top_genes) <= 6 else None, title="Transcript usage and full-length support")
                # Flow view for the top genes.
                flow = plot.groupby(["gene", "transcript", "cluster"], as_index=False)["umis"].sum().nlargest(MAX_NETWORK_LINKS, "umis")
                if not flow.empty:
                    labels = list(dict.fromkeys([*flow["gene"].astype(str), *flow["transcript"].astype(str), *flow["cluster"].astype(str)]))
                    index = {label: i for i, label in enumerate(labels)}
                    source_idx = [index[g] for g in flow["gene"].astype(str)] + [index[t] for t in flow["transcript"].astype(str)]
                    target_idx = [index[t] for t in flow["transcript"].astype(str)] + [index[c] for c in flow["cluster"].astype(str)]
                    values = flow["umis"].tolist() + flow["umis"].tolist()
                    figures["isoform_flow"] = go.Figure(go.Sankey(node={"label": labels}, link={"source": source_idx, "target": target_idx, "value": values}))
                    figures["isoform_flow"].update_layout(title="Gene → transcript → cluster isoform flow")
                summary.update({"differential_usage_genes": int(tables.get("differential_isoform_usage", pd.DataFrame()).get("differential_usage_review", pd.Series(dtype=bool)).sum())})

        elif module_key == "biomedical_foundation_model_hub":
            models = output.copy()
            if not models.empty and "parameter_count" in models:
                params = _num(models["parameter_count"], 0).clip(lower=0)
                for label, bytes_per_param in {"fp32": 4.0, "fp16": 2.0, "int8": 1.0, "int4": 0.5}.items():
                    models[f"{label}_weight_gb"] = params * bytes_per_param / 1e9
                models["training_memory_gb_estimate"] = params * 16 / 1e9
                hardware = {"Laptop 8GB": 8, "Workstation 16GB": 16, "GPU 24GB": 24, "GPU 48GB": 48, "GPU 80GB": 80}
                rows: list[dict[str, Any]] = []
                for _, row in models.iterrows():
                    for hardware_name, capacity in hardware.items():
                        rows.append({"model_id": row.get("model_id", "Unknown"), "hardware": hardware_name, "capacity_gb": capacity, "fp16_fit": bool(row["fp16_weight_gb"] * 1.25 <= capacity), "int8_fit": bool(row["int8_weight_gb"] * 1.25 <= capacity), "benchmark_score": row.get("benchmark_score", np.nan), "license": row.get("license", "Unknown")})
                hardware_fit = pd.DataFrame(rows)
                tables["quantisation_memory_profiles"] = models.sort_values("fp16_weight_gb")
                tables["hardware_compatibility_matrix"] = hardware_fit
                objectives = np.column_stack([_num(models.get("benchmark_score", 0), 0), _num(models["fp16_weight_gb"], 0)])
                models["pareto_efficient"] = _pareto_mask(objectives, (True, False))
                tables["model_efficiency_frontier"] = models.sort_values(["pareto_efficient", "benchmark_score"], ascending=[False, False])
                figures["hardware_fit_matrix"] = px.density_heatmap(hardware_fit.assign(fit=hardware_fit["int8_fit"].astype(int)), x="hardware", y="model_id", z="fit", histfunc="max", color_continuous_scale=[[0, "#7f1d1d"], [1, "#14532d"]], title="INT8 hardware compatibility")
                figures["accuracy_memory_frontier"] = px.scatter(models, x="fp16_weight_gb", y="benchmark_score", color="pareto_efficient", symbol="license" if "license" in models else None, hover_name="model_id", size="embedding_dim" if "embedding_dim" in models else None, title="Benchmark score versus FP16 weight memory")
                if {"task", "modality", "license"}.issubset(models.columns):
                    figures["licence_task_map"] = px.sunburst(models, path=["modality", "task", "license"], values="parameter_count", color="benchmark_score", title="Model modality, task and licence map")
                summary.update({"pareto_models": int(models["pareto_efficient"].sum()), "int8_8gb_fit": int(hardware_fit.loc[hardware_fit["hardware"] == "Laptop 8GB", "int8_fit"].sum())})

        elif module_key == "amr_surveillance":
            work = source.copy()
            if not work.empty:
                work["resistant_probability"] = _num(work.get("resistant_probability", 0), 0).clip(0, 1)
                work["predicted_resistant"] = work["resistant_probability"] >= 0.7
                work["observed_resistant"] = work.get("phenotype", pd.Series("", index=work.index)).astype(str).str.lower().eq("resistant")
                confusion = work.groupby(["observed_resistant", "predicted_resistant"], as_index=False).agg(isolates=("sample", "nunique") if "sample" in work else (work.columns[0], "size"))
                tables["genotype_phenotype_confusion"] = confusion
                figures["concordance_matrix"] = px.density_heatmap(confusion, x="predicted_resistant", y="observed_resistant", z="isolates", histfunc="sum", text_auto=True, title="Genotype/phenotype concordance matrix")
                grouped = work.groupby([c for c in ["species", "lineage", "amr_gene", "location"] if c in work.columns], as_index=False).agg(isolates=("sample", "nunique") if "sample" in work else (work.columns[0], "size"), resistant=("observed_resistant", "sum"), resistance_rate=("observed_resistant", "mean"), concordance=("predicted_resistant", lambda s: float((s == work.loc[s.index, "observed_resistant"]).mean())))
                intervals = grouped.apply(lambda row: _wilson(float(row["resistant"]), float(row["isolates"])), axis=1)
                grouped["lower_95"] = [value[0] for value in intervals]
                grouped["upper_95"] = [value[1] for value in intervals]
                grouped["uncertain_resistance"] = (grouped["upper_95"] - grouped["lower_95"]) > 0.35
                tables["resistance_uncertainty"] = grouped.sort_values(["uncertain_resistance", "resistance_rate"], ascending=[False, False])
                if "date" in work.columns:
                    work["date"] = pd.to_datetime(work["date"], errors="coerce")
                    temporal = work.dropna(subset=["date"]).assign(month=lambda d: d["date"].dt.to_period("M").dt.to_timestamp()).groupby(["month", "species"], as_index=False).agg(isolates=("sample", "nunique") if "sample" in work else (work.columns[0], "size"), resistant=("observed_resistant", "sum"), resistance_rate=("observed_resistant", "mean"))
                    if not temporal.empty:
                        ci = temporal.apply(lambda row: _wilson(row["resistant"], row["isolates"]), axis=1)
                        temporal["lower_95"] = [v[0] for v in ci]
                        temporal["upper_95"] = [v[1] for v in ci]
                        temporal["acceleration"] = temporal.groupby("species")["resistance_rate"].diff()
                        temporal["emergence_alert"] = (temporal["acceleration"] >= 0.15) & (temporal["isolates"] >= 5)
                        tables["temporal_emergence_alerts"] = temporal
                        figures["resistance_trend"] = px.line(temporal, x="month", y="resistance_rate", color="species", markers=True, error_y=(temporal["upper_95"] - temporal["resistance_rate"]).clip(lower=0), error_y_minus=(temporal["resistance_rate"] - temporal["lower_95"]).clip(lower=0), title="Resistance trends with Wilson intervals")
                if {"species", "lineage", "amr_gene"}.issubset(work.columns):
                    flow = work.groupby(["species", "lineage", "amr_gene"], as_index=False).size().nlargest(MAX_NETWORK_LINKS, "size")
                    labels = list(dict.fromkeys([*flow["species"].astype(str), *flow["lineage"].astype(str), *flow["amr_gene"].astype(str)]))
                    idx = {label: i for i, label in enumerate(labels)}
                    figures["lineage_gene_flow"] = go.Figure(go.Sankey(node={"label": labels}, link={"source": [idx[x] for x in flow["species"].astype(str)] + [idx[x] for x in flow["lineage"].astype(str)], "target": [idx[x] for x in flow["lineage"].astype(str)] + [idx[x] for x in flow["amr_gene"].astype(str)], "value": flow["size"].tolist() * 2}))
                    figures["lineage_gene_flow"].update_layout(title="Species → lineage → AMR gene flow")
                summary.update({"discordant_isolates": int((work["predicted_resistant"] != work["observed_resistant"]).sum())})

        elif module_key == "spatial_medicine_tme":
            work = source.copy()
            if {"patient", "x", "y", "cell_type"}.issubset(work.columns):
                work["x"] = _num(work["x"])
                work["y"] = _num(work["y"])
                work["expression"] = _num(work.get("expression", 0), 0)
                pair_rows: list[dict[str, Any]] = []
                for patient, group in work.dropna(subset=["x", "y"]).groupby("patient"):
                    if len(group) < 3:
                        continue
                    coordinates = group[["x", "y"]].to_numpy(float)
                    neighbours = min(6, len(group) - 1)
                    _, indices = cKDTree(coordinates).query(coordinates, k=neighbours + 1)
                    cell_types = group["cell_type"].astype(str).to_numpy()
                    proportions = pd.Series(cell_types).value_counts(normalize=True)
                    counts: dict[tuple[str, str], int] = {}
                    for i in range(len(group)):
                        for j in np.atleast_1d(indices[i])[1:]:
                            pair = (cell_types[i], cell_types[int(j)])
                            counts[pair] = counts.get(pair, 0) + 1
                    total_links = max(sum(counts.values()), 1)
                    for (source_type, target_type), observed in counts.items():
                        expected = total_links * float(proportions.get(source_type, 0)) * float(proportions.get(target_type, 0))
                        pair_rows.append({"patient": patient, "source_cell": source_type, "target_cell": target_type, "observed_links": observed, "expected_links": expected, "log2_enrichment": math.log2((observed + 0.5) / (expected + 0.5))})
                neighbourhood = pd.DataFrame(pair_rows)
                tables["cell_neighbourhood_enrichment"] = neighbourhood.sort_values("log2_enrichment", ascending=False) if not neighbourhood.empty else neighbourhood
                immune_labels = {"CD8 T", "Treg", "Macrophage", "B cell", "NK"}
                tumour_mask = work["cell_type"].astype(str).str.lower().str.contains("tumour|tumor")
                immune_mask = work["cell_type"].astype(str).isin(immune_labels) | work["cell_type"].astype(str).str.lower().str.contains("immune|cd8|treg|macro|nk")
                work["compartment_group"] = np.select([tumour_mask, immune_mask], ["Tumour", "Immune"], default="Other")
                tables["spatial_cell_points"] = work
                plot = _clean_for_plot(work, 10_000)
                figures["layered_spatial_map"] = px.scatter(plot, x="x", y="y", color="compartment_group", symbol="cell_type" if plot["cell_type"].nunique() <= 12 else None, size="expression" if "expression" in plot else None, facet_col="patient" if plot["patient"].nunique() <= 4 else None, hover_data=[c for c in ["region", "gene"] if c in plot], title="Layered tumour microenvironment map")
                if not neighbourhood.empty:
                    aggregate = neighbourhood.groupby(["source_cell", "target_cell"], as_index=False)["log2_enrichment"].mean()
                    figures["neighbourhood_enrichment"] = px.density_heatmap(aggregate, x="target_cell", y="source_cell", z="log2_enrichment", histfunc="avg", color_continuous_scale="RdBu_r", title="Cell-neighbourhood enrichment")
                if {"gene", "region"}.issubset(work.columns):
                    expression = work.groupby(["gene", "region"], as_index=False).agg(mean_expression=("expression", "mean"), cells=("cell_type", "size"))
                    tables["region_gene_expression"] = expression
                    figures["region_gene_profile"] = px.density_heatmap(expression, x="region", y="gene", z="mean_expression", histfunc="avg", title="Regional gene-expression profile")
                summary.update({"neighbourhood_pairs": len(neighbourhood), "patients_neighbourhood_tested": int(neighbourhood.get("patient", pd.Series()).nunique())})

        elif module_key == "gene_therapy_vector":
            constructs = output.copy()
            if not constructs.empty:
                limits = {"AAV": 4700, "Lentiviral": 9000, "Adenoviral": 36000, "Non-viral": 15000}
                vector = constructs.get("vector_type", pd.Series("Unknown", index=constructs.index)).astype(str)
                constructs["capacity_limit_bp"] = vector.map(limits).fillna(5000)
                constructs["capacity_utilisation"] = _num(constructs.get("cargo_bp", 0), 0) / constructs["capacity_limit_bp"]
                constructs["capacity_status"] = pd.cut(constructs["capacity_utilisation"], [-np.inf, 0.8, 1.0, np.inf], labels=["Comfortable", "Tight", "Over capacity"])
                if "sequence" in source.columns:
                    seq = source.groupby("construct")["sequence"].first().astype(str).str.upper().str.replace(r"[^ACGT]", "", regex=True)
                    sequence_qc = pd.DataFrame({"construct": seq.index, "sequence_length": seq.str.len().values, "gc_fraction": seq.map(lambda s: (s.count("G") + s.count("C")) / len(s) if s else np.nan).values, "max_homopolymer": seq.map(lambda s: max((len(m.group(0)) for m in re.finditer(r"(A+|C+|G+|T+)", s)), default=0)).values, "cpg_count": seq.str.count("CG").values})
                    sequence_qc["sequence_review"] = (sequence_qc["gc_fraction"] < 0.35) | (sequence_qc["gc_fraction"] > 0.65) | (sequence_qc["max_homopolymer"] >= 8)
                else:
                    sequence_qc = pd.DataFrame({"construct": constructs.get("construct", pd.Series(dtype=str)), "sequence_status": "Not supplied", "sequence_review": True})
                tables["construct_capacity_and_sequence_qc"] = constructs.merge(sequence_qc, on="construct", how="left") if "construct" in constructs else constructs
                element_rows: list[dict[str, Any]] = []
                for _, row in constructs.iterrows():
                    cargo = int(_safe_div(row.get("cargo_bp", 0), 1, 0))
                    promoter_len = min(800, max(200, int(cargo * 0.15)))
                    current = 1
                    for element, length in [("5′ regulatory/ITR", 145), (str(row.get("promoter", "Promoter")), promoter_len), ("Therapeutic cargo", cargo), ("Poly(A)/3′ regulatory", 250)]:
                        element_rows.append({"construct": row.get("construct", "Unknown"), "element": element, "start": current, "end": current + max(length, 1) - 1, "length_bp": max(length, 1), "vector_type": row.get("vector_type", "Unknown")})
                        current += max(length, 1)
                element_map = pd.DataFrame(element_rows)
                tables["construct_element_map"] = element_map
                construct_map = go.Figure()
                for element, group in element_map.groupby("element", sort=False):
                    construct_map.add_trace(go.Bar(
                        x=(group["end"] - group["start"] + 1),
                        y=group["construct"],
                        base=group["start"],
                        orientation="h",
                        name=str(element),
                        customdata=np.column_stack([group["length_bp"], group["vector_type"]]),
                        hovertemplate="%{y}<br>Element: " + str(element) + "<br>Length: %{customdata[0]} bp<br>Vector: %{customdata[1]}<extra></extra>",
                    ))
                construct_map.update_layout(barmode="stack", title="Linear vector construct map", xaxis_title="Construct coordinate (bp)")
                figures["construct_map"] = construct_map
                figures["capacity_gauge"] = px.bar(constructs, x="construct", y="capacity_utilisation", color="capacity_status", hover_data=[c for c in ["cargo_bp", "capacity_limit_bp", "safety_score"] if c in constructs], title="Vector packaging-capacity utilisation")
                risk_columns = [c for c in ["immunogenicity_risk", "integration_risk", "tropism_score"] if c in constructs]
                if risk_columns:
                    risk_long = constructs.melt(id_vars=[c for c in ["construct", "vector_type"] if c in constructs], value_vars=risk_columns, var_name="metric", value_name="value")
                    figures["safety_tropism_matrix"] = px.density_heatmap(risk_long, x="metric", y="construct", z="value", histfunc="avg", color_continuous_scale="RdYlGn_r", title="Construct safety and tropism matrix")
                summary.update({"over_capacity": int((constructs["capacity_utilisation"] > 1).sum()), "sequence_supplied": bool("sequence" in source.columns)})

        elif module_key == "cell_therapy_cart":
            constructs = output.copy()
            if not constructs.empty:
                architecture_rows: list[dict[str, Any]] = []
                for _, row in constructs.iterrows():
                    domains = ["Signal peptide", f"scFv:{row.get('antigen', 'Target')}", "Hinge", "Transmembrane", str(row.get("costim_domain", "Costim")), "CD3ζ"]
                    if str(row.get("safety_switch", "")).strip():
                        domains.append(str(row.get("safety_switch")))
                    for order, domain in enumerate(domains, start=1):
                        architecture_rows.append({"construct": row.get("construct", "Unknown"), "order": order, "domain": domain, "antigen": row.get("antigen", "Unknown"), "costim_domain": row.get("costim_domain", "Unknown")})
                architecture = pd.DataFrame(architecture_rows)
                tables["car_architecture_manifest"] = architecture
                constructs["efficacy_proxy"] = (0.55 * _num(constructs.get("scfv_affinity", 0), 0) + 0.25 * (1 - _num(constructs.get("exhaustion_score", 0), 0)) + 0.20 * _num(constructs.get("manufacturability", 0), 0)).clip(0, 1)
                constructs["safety_proxy"] = (1 - _num(constructs.get("off_tumour_risk", 0), 0)).clip(0, 1)
                constructs["balanced_score"] = np.sqrt(constructs["efficacy_proxy"] * constructs["safety_proxy"])
                tables["efficacy_safety_review"] = constructs.sort_values("balanced_score", ascending=False)
                architecture["start"] = architecture["order"] - 0.45
                architecture["end"] = architecture["order"] + 0.45
                car_architecture = go.Figure()
                for domain, group in architecture.groupby("domain", sort=False):
                    car_architecture.add_trace(go.Bar(
                        x=(group["end"] - group["start"]),
                        y=group["construct"],
                        base=group["start"],
                        orientation="h",
                        name=str(domain),
                        hovertemplate="%{y}<br>Domain: " + str(domain) + "<extra></extra>",
                    ))
                car_architecture.update_layout(barmode="stack", title="CAR construct architecture schematic", xaxis_title="Domain order")
                figures["car_architecture"] = car_architecture
                figures["efficacy_safety_frontier"] = px.scatter(constructs, x="safety_proxy", y="efficacy_proxy", color="costim_domain" if "costim_domain" in constructs else None, size="manufacturability" if "manufacturability" in constructs else None, hover_name="construct", facet_col="antigen" if constructs.get("antigen", pd.Series()).nunique() <= 4 else None, title="CAR efficacy-safety frontier")
                if {"antigen", "costim_domain"}.issubset(constructs.columns):
                    matrix = constructs.groupby(["antigen", "costim_domain"], as_index=False).agg(score=("balanced_score", "mean"), constructs=("construct", "nunique"))
                    figures["antigen_domain_matrix"] = px.density_heatmap(matrix, x="costim_domain", y="antigen", z="score", histfunc="avg", title="Antigen and signalling-domain balance")
                summary.update({"balanced_candidates": int((constructs["balanced_score"] >= 0.65).sum())})

        elif module_key == "federated_biomedical_ai":
            rounds = output.copy()
            sites = secondary.copy() if isinstance(secondary, pd.DataFrame) else pd.DataFrame()
            raw = source.copy()
            if not rounds.empty:
                rounds = rounds.sort_values("round")
                rounds["metric_delta"] = _num(rounds.get("global_metric", 0), 0).diff()
                rounds["rolling_stability"] = _num(rounds.get("global_metric", 0), 0).rolling(3, min_periods=2).std()
                rounds["converged_round"] = (rounds["metric_delta"].abs() < 0.002) & (rounds["rolling_stability"] < 0.005)
                epsilon = _num(rounds.get("max_epsilon", 0), 0).clip(lower=0)
                delta = 1e-5
                k = np.arange(1, len(rounds) + 1)
                cumulative_sq = np.cumsum(epsilon.to_numpy(float) ** 2)
                rounds["epsilon_basic_upper"] = np.cumsum(epsilon)
                rounds["epsilon_advanced_screen"] = np.sqrt(2 * np.log(1 / delta) * cumulative_sq) + np.cumsum(epsilon.to_numpy(float) * (np.exp(np.minimum(epsilon.to_numpy(float), 20)) - 1))
                tables["round_convergence_privacy"] = rounds
                figures["round_performance"] = go.Figure()
                figures["round_performance"].add_trace(go.Scatter(x=rounds["round"], y=rounds["global_metric"], mode="lines+markers", name="Global metric"))
                if "mean_drift" in rounds:
                    figures["round_performance"].add_trace(go.Scatter(x=rounds["round"], y=rounds["mean_drift"], mode="lines", name="Mean drift", yaxis="y2"))
                    figures["round_performance"].update_layout(yaxis2={"overlaying": "y", "side": "right", "title": "Drift"})
                figures["round_performance"].update_layout(title="Federated convergence and drift")
                figures["privacy_utility"] = px.line(rounds, x="epsilon_basic_upper", y="global_metric", markers=True, hover_data=["round", "epsilon_advanced_screen"], title="Conservative privacy-utility trajectory")
            if not raw.empty and {"site", "round", "metric_value"}.issubset(raw.columns):
                raw["metric_value"] = _num(raw["metric_value"])
                matrix = raw.groupby(["site", "round"], as_index=False)["metric_value"].mean()
                tables["site_round_fairness"] = matrix
                figures["site_round_heatmap"] = px.density_heatmap(matrix, x="round", y="site", z="metric_value", histfunc="avg", title="Site-round performance heatmap")
                final_round = matrix["round"].max()
                final = matrix.loc[matrix["round"] == final_round].copy()
                fairness_gap = float(final["metric_value"].max() - final["metric_value"].min()) if len(final) else float("nan")
            else:
                fairness_gap = float("nan")
            if not sites.empty and "site" in sites:
                theta = np.linspace(0, 2 * np.pi, len(sites), endpoint=False)
                topology = go.Figure()
                for x, y in zip(np.cos(theta), np.sin(theta), strict=False):
                    topology.add_trace(go.Scatter(x=[0, x], y=[0, y], mode="lines", line={"width": 1}, hoverinfo="skip", showlegend=False))
                topology.add_trace(go.Scatter(x=np.cos(theta), y=np.sin(theta), mode="markers+text", text=sites["site"].astype(str), textposition="top center", marker={"size": 14, "color": _num(sites.get("mean_drift", 0), 0), "colorscale": "RdYlGn_r", "showscale": True}, name="Sites"))
                topology.add_trace(go.Scatter(x=[0], y=[0], mode="markers+text", text=["Global"], marker={"size": 22}, name="Global"))
                topology.update_layout(title="Federation topology and site drift", xaxis={"visible": False}, yaxis={"visible": False})
                figures["federation_topology"] = topology
            summary.update({"fairness_gap_final_round": fairness_gap, "converged_rounds": int(rounds.get("converged_round", pd.Series(dtype=bool)).sum()) if not rounds.empty else 0})

        elif module_key == "clinical_biomarker_survival":
            forest, ph, diagnostics = _cox_fit(source)
            if not forest.empty:
                tables["cox_model_screen"] = forest
                figures["cox_forest"] = go.Figure()
                figures["cox_forest"].add_trace(go.Scatter(x=forest["hazard_ratio"], y=forest["covariate"], mode="markers", error_x={"type": "data", "symmetric": False, "array": (forest["upper_95"] - forest["hazard_ratio"]).clip(lower=0), "arrayminus": (forest["hazard_ratio"] - forest["lower_95"]).clip(lower=0)}))
                figures["cox_forest"].add_vline(x=1, line_dash="dash")
                figures["cox_forest"].update_layout(title="Exploratory Cox hazard ratios", xaxis_type="log", xaxis_title="Hazard ratio")
            if not ph.empty:
                tables["proportional_hazards_diagnostic"] = ph
            calibration = diagnostics.pop("calibration", pd.DataFrame())
            patient_risk = diagnostics.pop("patient_risk", pd.DataFrame())
            if isinstance(calibration, pd.DataFrame) and not calibration.empty:
                tables["horizon_calibration"] = calibration
                figures["calibration"] = px.scatter(calibration, x="predicted_risk", y="observed_risk", size="patients", title="Median-horizon risk calibration")
                figures["calibration"].add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Ideal", line={"dash": "dash"}))
            if isinstance(patient_risk, pd.DataFrame) and not patient_risk.empty:
                tables["patient_risk_screen"] = patient_risk.sort_values("predicted_risk", ascending=False)
                figures["patient_risk_waterfall"] = px.bar(patient_risk.sort_values("predicted_risk"), x="patient", y="predicted_risk", color="event", hover_data=["time"], title="Patient risk waterfall")
            km = extra.get("kaplan_meier_curves", pd.DataFrame())
            if isinstance(km, pd.DataFrame) and not km.empty:
                group_cols = [c for c in ["arm", "biomarker_group"] if c in km]
                figures["km_with_risk"] = px.line(km, x="time", y="survival", color=group_cols[0] if group_cols else None, line_dash=group_cols[1] if len(group_cols) > 1 else None, hover_data=[c for c in ["at_risk", "events"] if c in km], title="Kaplan–Meier survival with risk counts")
            summary.update(diagnostics)

        elif module_key == "protein_ligand_codesign":
            candidates = output.copy()
            required = ["protein_score", "ligand_score", "interface_score", "selectivity_risk"]
            if not candidates.empty and all(c in candidates for c in required):
                values = np.column_stack([_num(candidates[c], 0) for c in required])
                candidates["pareto_optimal"] = _pareto_mask(values, (True, True, True, False))
                # Robust score under small deterministic perturbations of objective weights.
                weight_samples = rng.dirichlet(np.ones(4), size=150)
                transformed = values.copy()
                transformed[:, 3] = 1 - transformed[:, 3]
                robust_scores = transformed @ weight_samples.T
                candidates["robust_score_mean"] = robust_scores.mean(axis=1)
                candidates["robust_score_sd"] = robust_scores.std(axis=1)
                candidates["robust_rank_probability"] = (robust_scores >= np.quantile(robust_scores, 0.9, axis=0)).mean(axis=1)
                tables["robust_pareto_candidates"] = candidates.sort_values(["pareto_optimal", "robust_rank_probability", "robust_score_mean"], ascending=False)
                # Greedy diverse shortlist in objective space.
                scaled = (transformed - transformed.min(axis=0)) / np.where(np.ptp(transformed, axis=0) == 0, 1, np.ptp(transformed, axis=0))
                selected: list[int] = [int(np.argmax(candidates["robust_score_mean"].to_numpy()))]
                while len(selected) < min(12, len(candidates)):
                    distances = np.min(np.linalg.norm(scaled[:, None, :] - scaled[selected][None, :, :], axis=2), axis=1)
                    distances[selected] = -1
                    selected.append(int(np.argmax(distances)))
                diverse = candidates.iloc[selected].copy()
                diverse["diversity_selection_order"] = np.arange(1, len(diverse) + 1)
                tables["diverse_design_shortlist"] = diverse
                figures["objective_landscape_3d"] = px.scatter_3d(candidates, x="protein_score", y="ligand_score", z="interface_score", color="selectivity_risk", symbol="pareto_optimal", size="robust_rank_probability", hover_name="candidate", title="Protein–ligand objective landscape")
                figures["parallel_objectives"] = px.parallel_coordinates(candidates, dimensions=required + ["robust_score_mean"], color="robust_score_mean", title="Parallel objective coordinates")
                if {"protein_variant", "ligand"}.issubset(candidates.columns):
                    figures["variant_ligand_heatmap"] = px.density_heatmap(candidates, x="ligand", y="protein_variant", z="robust_score_mean", histfunc="max", title="Variant–ligand robust score matrix")
                summary.update({"pareto_optimal": int(candidates["pareto_optimal"].sum()), "diverse_shortlist": len(diverse)})

        elif module_key == "pangenome_population_medicine":
            work = output.copy()
            if not work.empty and {"population", "variant", "allele_frequency"}.issubset(work.columns):
                matrix = work.pivot_table(index="variant", columns="population", values="allele_frequency", aggfunc="mean")
                fst_rows: list[dict[str, Any]] = []
                for variant, row in matrix.iterrows():
                    values = row.dropna().to_numpy(float)
                    if len(values) < 2:
                        continue
                    pbar = float(np.mean(values))
                    denominator = pbar * (1 - pbar)
                    fst_like = float(np.var(values, ddof=1) / denominator) if denominator > 0 else 0.0
                    fst_rows.append({"variant": variant, "populations": len(values), "mean_af": pbar, "af_range": float(np.ptp(values)), "fst_like": min(max(fst_like, 0), 1)})
                differentiation = pd.DataFrame(fst_rows)
                tables["population_differentiation"] = differentiation.sort_values("fst_like", ascending=False) if not differentiation.empty else differentiation
                if "path" in work:
                    path_rows: list[dict[str, Any]] = []
                    for population, group in work.groupby("population"):
                        counts = group.groupby("path")["samples"].sum() if "samples" in group else group["path"].value_counts()
                        probabilities = counts / counts.sum() if counts.sum() else counts
                        entropy = float(stats.entropy(probabilities[probabilities > 0], base=2)) if len(probabilities) else 0.0
                        path_rows.append({"population": population, "paths": int(len(counts)), "path_entropy": entropy, "dominant_path_fraction": float(probabilities.max()) if len(probabilities) else np.nan})
                    tables["population_path_diversity"] = pd.DataFrame(path_rows)
                    flow = work.groupby(["population", "path", "variant"], as_index=False).agg(weight=("samples", "sum") if "samples" in work else ("allele_frequency", "sum")).nlargest(MAX_NETWORK_LINKS, "weight")
                    labels = list(dict.fromkeys([*flow["population"].astype(str), *flow["path"].astype(str), *flow["variant"].astype(str)]))
                    idx = {label: i for i, label in enumerate(labels)}
                    figures["population_path_flow"] = go.Figure(go.Sankey(node={"label": labels}, link={"source": [idx[x] for x in flow["population"].astype(str)] + [idx[x] for x in flow["path"].astype(str)], "target": [idx[x] for x in flow["path"].astype(str)] + [idx[x] for x in flow["variant"].astype(str)], "value": flow["weight"].tolist() * 2}))
                    figures["population_path_flow"].update_layout(title="Population → graph path → variant flow")
                melted = matrix.reset_index().melt(id_vars="variant", var_name="population", value_name="allele_frequency")
                figures["allele_frequency_heatmap"] = px.density_heatmap(melted, x="population", y="variant", z="allele_frequency", histfunc="avg", title="Population allele-frequency matrix")
                if not differentiation.empty:
                    figures["differentiation_profile"] = px.bar(differentiation.head(50), x="variant", y="fst_like", color="af_range", title="Population differentiation screening profile")
                summary.update({"high_differentiation_variants": int((differentiation.get("fst_like", pd.Series(dtype=float)) >= 0.15).sum())})

        elif module_key == "pharmacovigilance_intelligence":
            cases = source.copy()
            signals = output.copy()
            if not cases.empty:
                normalised = cases.copy()
                normalised["drug_normalised"] = normalised.get("drug", pd.Series("", index=normalised.index)).astype(str).str.upper().str.replace(r"[^A-Z0-9]+", " ", regex=True).str.strip()
                normalised["event_normalised"] = normalised.get("event", pd.Series("", index=normalised.index)).astype(str).str.upper().str.replace(r"[^A-Z0-9]+", " ", regex=True).str.strip()
                fingerprint_cols = [c for c in ["drug_normalised", "event_normalised", "age", "sex", "outcome"] if c in normalised]
                normalised["case_fingerprint"] = pd.util.hash_pandas_object(normalised[fingerprint_cols].astype(str), index=False).astype(str)
                normalised["duplicate_fingerprint"] = normalised.duplicated("case_fingerprint", keep=False)
                normalised["duplicate_report_id"] = normalised.duplicated("report_id", keep=False) if "report_id" in normalised else False
                tables["case_duplicate_and_coding_review"] = normalised.loc[normalised["duplicate_fingerprint"] | normalised["duplicate_report_id"]].copy()
            if not signals.empty and {"drug", "event", "reports"}.issubset(signals.columns):
                total = max(len(cases), 1)
                rows: list[dict[str, Any]] = []
                for _, row in signals.iterrows():
                    drug, event = row["drug"], row["event"]
                    a = int(row["reports"])
                    b = int((cases.get("drug", pd.Series(dtype=str)) == drug).sum()) - a
                    c = int((cases.get("event", pd.Series(dtype=str)) == event).sum()) - a
                    d = max(total - a - b - c, 0)
                    odds, fisher_p = stats.fisher_exact([[a, max(b, 0)], [max(c, 0), d]], alternative="greater")
                    expected = max(((a + b) * (a + c)) / total, 1e-9)
                    alpha, beta = 1.0, 1.0
                    ebgm = (a + alpha) / (expected + beta)
                    eb05 = float(stats.gamma.ppf(0.05, a + alpha, scale=1 / (expected + beta)))
                    ic = float(row.get("information_component", math.log2((a + 0.5) / (expected + 0.5))))
                    ic025 = ic - 1.96 / (math.log(2) * math.sqrt(a + 0.5))
                    rows.append({"drug": drug, "event": event, "reports": a, "fisher_p_value": fisher_p, "fisher_odds_ratio": odds, "ebgm_screen": ebgm, "eb05_screen": eb05, "ic": ic, "ic025_screen": ic025, "shrinkage_signal": bool(a >= 3 and eb05 > 1 and ic025 > 0), "serious_rate": row.get("serious_rate", np.nan)})
                shrinkage = pd.DataFrame(rows)
                shrinkage["q_value"] = _bh(shrinkage["fisher_p_value"])
                tables["shrinkage_signal_review"] = shrinkage.sort_values(["shrinkage_signal", "eb05_screen"], ascending=[False, False])
                plot = shrinkage.copy()
                plot["minus_log10_q"] = -np.log10(_num(plot["q_value"], 1).clip(lower=1e-300))
                figures["disproportionality_volcano"] = px.scatter(plot, x=np.log2(_num(plot["ebgm_screen"], 1).clip(lower=1e-9)), y="minus_log10_q", color="shrinkage_signal", size="reports", hover_name="event", hover_data=["drug", "eb05_screen", "ic025_screen"], labels={"x": "log2 EBGM-like shrinkage"}, title="Shrinkage disproportionality volcano")
                figures["drug_event_signal_matrix"] = px.density_heatmap(shrinkage, x="event", y="drug", z="eb05_screen", histfunc="max", title="Drug-event lower-bound signal matrix")
            if not cases.empty and {"drug", "outcome"}.issubset(cases.columns):
                outcome = cases.groupby(["drug", "outcome"], as_index=False).size()
                figures["outcome_hierarchy"] = px.sunburst(outcome, path=["drug", "outcome"], values="size", title="Drug and reported-outcome hierarchy")
            summary.update({"duplicate_cases": int(tables.get("case_duplicate_and_coding_review", pd.DataFrame()).shape[0]), "shrinkage_signals": int(tables.get("shrinkage_signal_review", pd.DataFrame()).get("shrinkage_signal", pd.Series(dtype=bool)).sum())})

        elif module_key == "synthetic_cohort_trial":
            patients = source.copy()
            if not patients.empty and {"arm", "outcome"}.issubset(patients.columns):
                patients["outcome"] = _num(patients["outcome"], 0).clip(0, 1)
                arms = patients["arm"].astype(str).unique().tolist()
                if len(arms) >= 2:
                    control, treatment = arms[0], arms[-1]
                    control_values = patients.loc[patients["arm"].astype(str) == control, "outcome"].to_numpy(float)
                    treatment_values = patients.loc[patients["arm"].astype(str) == treatment, "outcome"].to_numpy(float)
                    n0, n1 = len(control_values), len(treatment_values)
                    p0, p1 = float(np.mean(control_values)), float(np.mean(treatment_values))
                    simulations = 500
                    rows: list[dict[str, Any]] = []
                    null_significant = 0
                    alternative_significant = 0
                    pooled_null = (p0 + p1) / 2
                    for index in range(simulations):
                        y0 = rng.binomial(1, p0, n0)
                        y1 = rng.binomial(1, p1, n1)
                        rd = float(y1.mean() - y0.mean())
                        se = math.sqrt(max(y0.mean() * (1 - y0.mean()) / max(n0, 1) + y1.mean() * (1 - y1.mean()) / max(n1, 1), 1e-12))
                        z = rd / se
                        significant = abs(z) > stats.norm.ppf(0.975)
                        alternative_significant += int(significant)
                        null0 = rng.binomial(1, pooled_null, n0)
                        null1 = rng.binomial(1, pooled_null, n1)
                        null_rd = float(null1.mean() - null0.mean())
                        null_se = math.sqrt(max(null0.mean() * (1 - null0.mean()) / max(n0, 1) + null1.mean() * (1 - null1.mean()) / max(n1, 1), 1e-12))
                        null_significant += int(abs(null_rd / null_se) > stats.norm.ppf(0.975))
                        rows.append({"simulation": index + 1, "risk_difference": rd, "significant": significant})
                    simulation = pd.DataFrame(rows)
                    tables["monte_carlo_operating_characteristics"] = simulation
                    dropout_rows: list[dict[str, Any]] = []
                    for dropout in [0.0, 0.1, 0.2, 0.3]:
                        effective_n0, effective_n1 = max(2, int(n0 * (1 - dropout))), max(2, int(n1 * (1 - dropout)))
                        se = math.sqrt(max(p0 * (1 - p0) / effective_n0 + p1 * (1 - p1) / effective_n1, 1e-12))
                        z_effect = abs(p1 - p0) / se
                        approximate_power = float(stats.norm.cdf(z_effect - stats.norm.ppf(0.975)))
                        dropout_rows.append({"dropout_fraction": dropout, "control_n": effective_n0, "treatment_n": effective_n1, "approximate_power": approximate_power})
                    dropout_table = pd.DataFrame(dropout_rows)
                    tables["dropout_power_sensitivity"] = dropout_table
                    figures["risk_difference_distribution"] = px.histogram(simulation, x="risk_difference", color="significant", nbins=45, marginal="box", title="Monte Carlo risk-difference distribution")
                    figures["dropout_power_curve"] = px.line(dropout_table, x="dropout_fraction", y="approximate_power", markers=True, title="Approximate power under dropout")
                    summary.update({"observed_power_screen": alternative_significant / simulations, "null_type1_screen": null_significant / simulations, "simulations": simulations})
                balance = extra.get("covariate_balance", pd.DataFrame())
                if isinstance(balance, pd.DataFrame) and not balance.empty:
                    tables["covariate_balance"] = balance
                    figures["love_plot"] = px.scatter(balance, x="smd", y="covariate", color="balanced", title="Covariate balance Love plot")
                if "time" in patients:
                    # Simple recruitment trajectory from sorted index when no enrolment dates are present.
                    ordered = patients.reset_index(drop=True).copy()
                    ordered["recruitment_month"] = np.arange(len(ordered)) // max(1, math.ceil(len(ordered) / 12)) + 1
                    recruitment = ordered.groupby(["recruitment_month", "arm"], as_index=False).size()
                    recruitment["cumulative_patients"] = recruitment.groupby("arm")["size"].cumsum()
                    figures["recruitment_trajectory"] = px.line(recruitment, x="recruitment_month", y="cumulative_patients", color="arm", markers=True, title="Synthetic recruitment trajectory")

        elif module_key == "autonomous_lab_planner":
            plan = output.copy()
            if not plan.empty:
                factorial = _factorial_design(plan)
                tables["recommended_factorial_design"] = factorial
                effect_size = float(_num(source.get("expected_effect_size", pd.Series([0.8])), 0.8).dropna().median()) if "expected_effect_size" in source else 0.8
                effect_size = max(abs(effect_size), 0.1)
                alpha = 0.05
                target_power = 0.8
                z_alpha = stats.norm.ppf(1 - alpha / 2)
                z_power = stats.norm.ppf(target_power)
                n_per_group = int(math.ceil(2 * ((z_alpha + z_power) / effect_size) ** 2))
                power_table = pd.DataFrame([{ "standardised_effect": effect_size, "alpha": alpha, "target_power": target_power, "approximate_n_per_group": n_per_group, "total_two_group_n": 2 * n_per_group, "method": "Normal approximation; confirm with endpoint-specific model" }])
                tables["sample_size_screen"] = power_table
                plate = _plate_layout(plan)
                tables["adjacency_aware_plate_layout"] = plate
                if not plate.empty:
                    plate["row_index"] = plate["plate_row"].map({row: index + 1 for index, row in enumerate(sorted(plate["plate_row"].unique()))})
                    figures["plate_map"] = px.scatter(plate, x="plate_column", y="row_index", color="hypothesis" if "hypothesis" in plate else None, symbol="control" if "control" in plate else None, text="well", hover_data=[c for c in ["experiment_id", "factor", "level", "replicates"] if c in plate], title="Adjacency-aware experimental plate layout")
                    figures["plate_map"].update_yaxes(autorange="reversed")
                schedule = extra.get("resource_schedule", pd.DataFrame()).copy()
                if not schedule.empty:
                    schedule["start_hour"] = np.concatenate([[0.0], np.cumsum(_num(schedule["estimated_hours"], 0).to_numpy(float)[:-1])])
                    schedule["end_hour"] = schedule["start_hour"] + _num(schedule["estimated_hours"], 0)
                    tables["resource_schedule_gantt"] = schedule
                    gantt = go.Figure()
                    color_groups = schedule.groupby("review_required", sort=False) if "review_required" in schedule else [("All", schedule)]
                    for status, group in color_groups:
                        gantt.add_trace(go.Bar(
                            x=(group["end_hour"] - group["start_hour"]),
                            y=group["experiment_id"],
                            base=group["start_hour"],
                            orientation="h",
                            name=f"Review required: {status}" if status != "All" else "Scheduled",
                            customdata=group[[c for c in ["hypothesis", "factor", "level", "total_cost"] if c in group]].astype(str).to_numpy(),
                        ))
                    gantt.update_layout(barmode="overlay", title="Resource and experiment schedule", xaxis_title="Elapsed hours")
                    figures["resource_gantt"] = gantt
                design = extra.get("design_matrix", pd.DataFrame())
                if isinstance(design, pd.DataFrame) and not design.empty:
                    figures["factor_level_coverage"] = px.density_heatmap(design, x="level", y="factor", z="experiments", histfunc="sum", title="Factor-level experimental coverage")
                cost = plan.groupby("hypothesis", as_index=False).agg(total_cost=("total_cost", "sum"), experiments=("experiment_id", "count"), review_required=("review_required", "sum")) if "hypothesis" in plan else pd.DataFrame()
                if not cost.empty:
                    figures["cost_waterfall"] = px.bar(cost, x="hypothesis", y="total_cost", color="review_required", hover_data=["experiments"], title="Experiment cost and review burden")
                summary.update({"factorial_runs": len(factorial), "approximate_n_per_group": n_per_group, "plate_assignments": len(plate)})

    except MemoryError:
        summary["safe_error"] = "MemoryError: deep analysis exceeded the safe in-memory limit. Use a smaller cohort or background execution."
    except Exception as exc:  # Every advanced layer must remain isolated from the primary analysis.
        summary["safe_error"] = f"{type(exc).__name__}: {exc}"

    summary.update({
        "scientific_tables": len(tables),
        "specialist_viewers": len(figures),
        "external_boundary": PROFILES[module_key].external_boundary,
    })
    return {"summary": summary, "tables": tables, "figures": figures, "quality": quality}



__all__ = ["build_module_scientific_artifacts"]
