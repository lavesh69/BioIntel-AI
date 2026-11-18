from __future__ import annotations

from typing import Mapping

import pandas as pd

from .scientific_visuals import (
    ScientificVisual,
    _bar,
    _box,
    _correlation_heatmap,
    _frame,
    _group_bar,
    _heatmap,
    _histogram,
    _line,
    _manhattan,
    _network,
    _radar,
    _roc,
    _safe_log10,
    _scatter,
    _spatial,
    _survival,
    _top,
    _waterfall,
)

def _visuals_for_expansion(
    key: str,
    data: pd.DataFrame,
    result: pd.DataFrame,
    secondary: pd.DataFrame,
    extras: Mapping[str, pd.DataFrame],
) -> list[ScientificVisual | None]:
    e = {name: _frame(table) for name, table in extras.items()}
    if key == "epigenomics_chromatin":
        differential = e.get("differential_statistics", result)
        volcano = differential.copy()
        if "p_value" in volcano:
            volcano["minus_log10_p"] = _safe_log10(volcano["p_value"])
        return [
            _scatter(data, x="signal", y="methylation", color="condition", hover=["region", "sample"], title="Regulatory signal versus methylation", interpretation="Highlights regions where chromatin signal and methylation move together or diverge.", method="Signal–methylation scatter"),
            _scatter(volcano, x="log2_fold_change", y="minus_log10_p", color="significant", size="cohen_d", hover=["region", "q_value"], title="Differential accessibility volcano", interpretation="Prioritises regions by effect size and statistical evidence.", method="Welch-style differential screen with FDR"),
            _heatmap(data, row="region", column="condition", value="signal", title="Condition-by-region signal heatmap", interpretation="Compares mean regulatory signal across regions and conditions.", method="Mean aggregation heatmap"),
            _histogram(result, x="methylation_delta", color="significant", title="Methylation-shift distribution", interpretation="Shows the range and direction of condition-associated methylation changes.", method="Distribution with marginal box plot"),
            _bar(_top(result, "priority_score_advanced"), x="region", y="priority_score_advanced", color="significant", title="Top regulatory-region priorities", interpretation="Ranks regions combining statistical effect, methylation shift and replicate balance.", method="Composite transparent priority score"),
        ]
    if key == "metabolomics_lipidomics":
        feature_stats = e.get("feature_statistics", result)
        volcano = feature_stats.copy()
        if "p_value" in volcano:
            volcano["minus_log10_p"] = _safe_log10(volcano["p_value"])
        return [
            _scatter(data, x="intensity", y="blank_intensity", color="group", hover=["feature", "sample"], log_x=True, log_y=True, title="Signal versus blank contamination", interpretation="Separates high-abundance biological features from blank-associated signals.", method="Log-scaled abundance scatter"),
            _scatter(volcano, x="log2_fold_change", y="minus_log10_p", color="significant", size="annotation_confidence", hover=["feature", "q_value"], title="Differential metabolite volcano", interpretation="Combines fold change, FDR and annotation confidence for candidate review.", method="Feature-wise differential statistics"),
            _heatmap(data, row="feature", column="sample", value="intensity", title="Feature abundance heatmap", interpretation="Displays the dominant abundance patterns across samples.", method="Mean intensity heatmap"),
            _scatter(result, x="cv", y="blank_ratio", color="qc_pass", size="annotation_confidence", hover=["feature"], title="Analytical QC landscape", interpretation="Identifies features with high variation or excessive blank contribution.", method="CV and blank-ratio QC"),
            _bar(_top(result, "priority_score_advanced"), x="feature", y="priority_score_advanced", color="significant", title="Top metabolite priorities", interpretation="Ranks reproducible, low-contamination and statistically supported features.", method="Composite feature score"),
        ]
    if key == "immunoinformatics_vaccine":
        promiscuous = e.get("promiscuous_epitopes", pd.DataFrame())
        return [
            _scatter(result, x="binding_score", y="immunogenicity", color="passes_safety_screen", size="conservancy", hover=["peptide", "allele"], title="Epitope evidence landscape", interpretation="Shows binding, immunogenicity, conservancy and safety simultaneously.", method="Multi-criterion epitope screen"),
            _radar(result, label="peptide", metrics=["binding_score", "immunogenicity", "conservancy", "priority_score"], ranking="priority_score", title="Top epitope profiles", interpretation="Compares normalised evidence dimensions for the highest-ranked peptides.", method="Min–max normalised radar"),
            _group_bar(result, category="allele", value="priority_score", color="passes_safety_screen", title="Allele coverage and candidate quality", interpretation="Compares average candidate strength and safety across HLA alleles.", method="Allele-level mean priority"),
            _scatter(result, x="hydrophobic_fraction", y="charged_fraction", color="manufacturability_flag", size="cysteine_count", hover=["peptide"], title="Peptide manufacturability space", interpretation="Flags extreme composition and cysteine burden that may complicate synthesis.", method="Sequence-composition screen"),
            _bar(_top(promiscuous, "promiscuity_score"), x="peptide", y="promiscuity_score", color="allele_count", title="Promiscuous epitope ranking", interpretation="Prioritises peptides supported across multiple alleles.", method="Cross-allele consensus score"),
        ]
    if key == "antibody_biologics":
        return [
            _scatter(result, x="affinity", y="stability", color="developability_flag", size="humanness", hover=["variant", "aggregation_risk", "liability_count"], title="Affinity–stability landscape", interpretation="Identifies candidates balancing binding and physical stability.", method="Multi-attribute candidate scatter"),
            _radar(result, label="variant", metrics=["affinity", "stability", "humanness", "priority_score"], ranking="priority_score", title="Top antibody developability profiles", interpretation="Compares normalised developability dimensions across leading variants.", method="Normalised candidate radar"),
            _scatter(result, x="aggregation_risk", y="liability_count", color="pareto_optimal", size="priority_score", hover=["variant"], title="Liability and aggregation burden", interpretation="Highlights candidates with fewer liabilities and lower aggregation risk.", method="Developability risk screen"),
            _bar(_top(result, "priority_score"), x="variant", y="priority_score", color="pareto_optimal", title="Candidate priority ranking", interpretation="Ranks antibody variants and highlights Pareto-optimal candidates.", method="Composite priority score"),
            _correlation_heatmap(result, columns=["affinity", "stability", "humanness", "aggregation_risk", "liability_count", "priority_score"], title="Antibody property correlation", interpretation="Shows trade-offs and redundant metrics across the candidate panel.", method="Pearson correlation"),
        ]
    if key == "docking_dynamics":
        consensus = e.get("ligand_consensus", secondary)
        return [
            _scatter(result, x="docking_score", y="rmsd", color="pose_quality_flag", size="hbond_occupancy", hover=["ligand", "pose", "strain_energy"], title="Pose score versus structural deviation", interpretation="Surfaces poses combining favourable scores, low RMSD and stable hydrogen bonding.", method="Docking-pose quality review"),
            _box(result, x="ligand", y="docking_score", color="pose_quality_flag", title="Docking-score distribution by ligand", interpretation="Compares pose variability and best-score consistency across ligands.", method="Pose-level box plot"),
            _scatter(result, x="strain_energy", y="hbond_occupancy", color="ligand", size="priority_score", hover=["pose"], title="Strain versus interaction persistence", interpretation="Flags poses with high conformational strain or weak hydrogen-bond occupancy.", method="Pose stability screen"),
            _bar(_top(consensus, "consensus_stability"), x="ligand", y="consensus_stability", color="flagged_poses", title="Ligand consensus ranking", interpretation="Aggregates best score, RMSD, occupancy and flagged-pose burden.", method="Ligand-level consensus score"),
            _correlation_heatmap(result, columns=["docking_score", "rmsd", "hbond_occupancy", "strain_energy", "priority_score"], title="Docking metric correlation", interpretation="Reveals score–stability trade-offs across all poses.", method="Pearson correlation"),
        ]
    if key == "pharmacogenomics":
        return [
            _heatmap(result, row="gene", column="drug", value="review_priority", title="Gene–drug review matrix", interpretation="Shows combinations with the strongest evidence and phenotype risk.", method="Mean review-priority heatmap"),
            _group_bar(result, category="gene", value="review_priority", color="phenotype", title="Pharmacogene evidence profile", interpretation="Compares review burden by gene and metaboliser phenotype.", method="Gene-level mean priority"),
            _group_bar(result, category="evidence_level", value="review_required", agg="sum", title="Evidence-level review burden", interpretation="Counts records requiring review within each evidence tier.", method="Evidence-tier aggregation"),
            _bar(_top(result, "review_priority"), x="variant", y="review_priority", color="curation_status", title="Top variant–drug records", interpretation="Ranks research records while keeping curation status visible.", method="Research-only priority score"),
            _group_bar(result, category="phenotype", value="phenotype_risk", color="drug", title="Phenotype-risk distribution", interpretation="Shows how phenotype risk varies across medicines.", method="Phenotype-level mean risk"),
        ]
    if key == "spatial_omics_pathology":
        region_stats = e.get("region_expression", secondary)
        spatial_stats = e.get("spatial_autocorrelation", pd.DataFrame())
        return [
            _spatial(result, title="Spatial expression map", interpretation="Maps expression and priority across tissue coordinates.", method="Coordinate-linked spot visualisation"),
            _heatmap(region_stats, row="gene", column="region", value="mean_expression", title="Regional expression heatmap", interpretation="Compares gene expression across annotated tissue regions.", method="Region-level mean expression"),
            _bar(_top(spatial_stats, "moran_i"), x="gene", y="moran_i", color="regions", title="Spatial autocorrelation ranking", interpretation="Highlights genes with clustered rather than random spatial patterns.", method="Moran-style spatial autocorrelation"),
            _box(result, x="region", y="expression", color="gene", title="Expression distribution by region", interpretation="Shows within-region variability and potential tissue heterogeneity.", method="Region-wise expression box plot"),
            _bar(_top(result, "priority_score"), x="spot", y="priority_score", color="region", title="Top spatial priority spots", interpretation="Ranks spots with strong regional enrichment and expression.", method="Spot-level composite priority"),
        ]
    if key == "single_cell_trajectory":
        trends = e.get("trajectory_trends", pd.DataFrame())
        network = e.get("communication_network", secondary)
        return [
            _scatter(result, x="pseudotime", y="expression", color="cluster", hover=["cell", "state"], title="Expression along pseudotime", interpretation="Shows state-dependent expression changes across the inferred trajectory.", method="Pseudotime trend scatter"),
            _group_bar(result, category="state", value="communication_score", color="cluster", title="Communication signal by cell state", interpretation="Compares average ligand–receptor activity across inferred states.", method="State-level communication summary"),
            _network(network, source="ligand", target="receptor", weight="mean_score", title="Ligand–receptor network", interpretation="Displays the dominant communication edges identified across clusters.", method="Circular interaction network"),
            _bar(_top(trends, "trajectory_slope"), x="cluster", y="trajectory_slope", color="q_value", title="Cluster trajectory slopes", interpretation="Compares expression trends and statistical support across clusters.", method="Cluster-level linear trend"),
            _heatmap(result, row="ligand", column="receptor", value="communication_score", title="Communication heatmap", interpretation="Summarises ligand–receptor scores across the analysed cells.", method="Mean interaction score"),
        ]
    if key == "bioimage_microscopy":
        image_qc = e.get("image_qc", pd.DataFrame())
        condition_stats = e.get("condition_statistics", pd.DataFrame())
        return [
            _scatter(result, x="area", y="intensity", color="condition", size="circularity", hover=["image_id", "object_id", "quality_flag"], title="Image-derived phenotype space", interpretation="Separates phenotypes by size, intensity, circularity and condition.", method="Object-level morphology scatter"),
            _histogram(result, x="area", color="condition", title="Object-size distribution", interpretation="Shows size heterogeneity and condition-specific shifts.", method="Area distribution"),
            _box(result, x="condition", y="intensity", color="quality_flag", title="Intensity by condition", interpretation="Compares signal distributions while preserving QC flags.", method="Condition-level box plot"),
            _bar(_top(image_qc, "flag_rate"), x="image_id", y="flag_rate", color="image_qc_flag", title="Image QC ranking", interpretation="Identifies images with excessive object-level anomalies.", method="Image-level QC aggregation"),
            _bar(_top(condition_stats, "cohen_d"), x="metric", y="cohen_d", color="comparison_condition", title="Condition effect sizes", interpretation="Compares morphology and intensity shifts across conditions.", method="Cohen's d effect summary"),
        ]
    if key == "biostatistics_design":
        allocation = e.get("allocation_plan", pd.DataFrame())
        return [
            _line(result, x="effect_size", y="total_sample_size", color="design", title="Sample size sensitivity", interpretation="Shows how total recruitment changes with the assumed effect size.", method="Power-based sample-size approximation"),
            _scatter(result, x="power", y="total_sample_size", color="design", size="groups", hover=["alpha", "dropout_rate"], title="Power versus recruitment burden", interpretation="Compares statistical power against the required sample size.", method="Design scenario comparison"),
            _bar(allocation, x="group", y="planned_n", color="design", title="Allocation plan", interpretation="Displays the planned participants per study arm.", method="Balanced allocation summary"),
            _scatter(result, x="dropout_rate", y="n_per_group_with_dropout", color="design", size="effect_size", title="Dropout inflation", interpretation="Shows the recruitment penalty introduced by anticipated attrition.", method="Attrition-adjusted sample size"),
            _bar(_top(result, "design_efficiency"), x="design", y="design_efficiency", color="feasibility_score", title="Design efficiency ranking", interpretation="Ranks scenarios by efficiency and practical feasibility.", method="Composite design score"),
        ]
    if key == "clinical_trial_biomarker":
        roc = e.get("roc_curve", pd.DataFrame())
        km = e.get("kaplan_meier_curve", pd.DataFrame())
        survival = e.get("survival_summary", secondary)
        return [
            _roc(roc, title="Biomarker ROC curve", interpretation="Shows sensitivity–specificity trade-offs across candidate cut-offs.", method="Threshold-based ROC screen"),
            _survival(km, title="Kaplan–Meier screening curves", interpretation="Compares survival trajectories across arm and biomarker strata.", method="Non-parametric survival estimate"),
            _box(result, x="response", y="biomarker", color="arm", title="Biomarker distribution by response", interpretation="Shows whether biomarker levels differ between responders and non-responders.", method="Response-stratified distribution"),
            _scatter(result, x="biomarker", y="time", color="arm", size="priority_score", hover=["patient", "response", "event"], title="Biomarker and time-to-event landscape", interpretation="Combines biomarker magnitude, follow-up time and outcome status.", method="Patient-level outcome scatter"),
            _bar(_top(survival, "response_rate"), x="biomarker_group", y="response_rate", color="arm", title="Response rate by biomarker group", interpretation="Compares response proportions across treatment and biomarker strata.", method="Stratified response summary"),
        ]
    if key == "genome_editing_safety":
        return [
            _scatter(result, x="off_target_count", y="on_target", color="high_risk", size="safety_score_advanced", hover=["guide", "snp_overlap", "bulge_count"], title="Efficiency versus off-target burden", interpretation="Highlights guides balancing on-target activity and genome-wide specificity.", method="Guide safety landscape"),
            _scatter(result, x="gc_content", y="sequence_entropy", color="low_complexity_flag", size="longest_homopolymer", hover=["guide"], title="Guide sequence-quality space", interpretation="Identifies extreme GC, low-complexity and homopolymer liabilities.", method="Sequence-composition QC"),
            _bar(_top(result, "safety_score_advanced"), x="guide", y="safety_score_advanced", color="high_risk", title="Guide safety ranking", interpretation="Ranks candidates using on-target evidence and multiple off-target liabilities.", method="Composite safety score"),
            _group_bar(result, category="max_mismatch", value="off_target_count", color="snp_overlap", title="Off-target burden by mismatch class", interpretation="Shows how predicted off-target counts vary with tolerated mismatches and SNP overlap.", method="Mismatch-level aggregation"),
            _correlation_heatmap(result, columns=["on_target", "off_target_count", "bulge_count", "gc_content", "sequence_entropy", "safety_score_advanced"], title="Guide metric correlation", interpretation="Reveals trade-offs among activity, sequence quality and specificity.", method="Pearson correlation"),
        ]
    if key == "proteogenomics_neoantigen":
        return [
            _scatter(result, x="spectral_score", y="hla_binding", color="multi_layer_support", size="expression", hover=["peptide", "variant", "clonality"], title="Neoantigen evidence landscape", interpretation="Integrates spectral support, HLA binding, expression and clonality.", method="Multi-layer candidate scatter"),
            _radar(result, label="peptide", metrics=["spectral_score", "hla_binding", "expression", "clonality", "priority_score_advanced"], ranking="priority_score_advanced", title="Top neoantigen evidence profiles", interpretation="Compares normalised evidence dimensions for leading peptides.", method="Normalised evidence radar"),
            _scatter(result, x="spectral_fdr_proxy", y="priority_score_advanced", color="manufacturability_flag", size="clonality", hover=["peptide"], title="Spectral confidence versus candidate priority", interpretation="Flags high-priority candidates with weak spectral-confidence proxies.", method="Spectral review screen"),
            _histogram(result, x="peptide_length", color="multi_layer_support", title="Peptide-length distribution", interpretation="Shows candidate size distribution and multi-layer support.", method="Peptide-length QC"),
            _bar(_top(result, "priority_score_advanced"), x="peptide", y="priority_score_advanced", color="multi_layer_support", title="Neoantigen priority ranking", interpretation="Ranks candidates supported across variant, expression, spectral and HLA evidence.", method="Composite neoantigen score"),
        ]
    if key == "bioprocess_fermentation":
        kinetics = e.get("batch_kinetics", secondary)
        return [
            _line(result, x="time", y="product", color="batch", title="Product trajectory by batch", interpretation="Compares product accumulation across process runs.", method="Batch time-series overlay"),
            _line(result, x="time", y="biomass", color="batch", title="Biomass growth trajectory", interpretation="Shows growth dynamics and between-batch consistency.", method="Batch time-series overlay"),
            _line(result, x="time", y="dissolved_oxygen", color="batch", title="Dissolved-oxygen profile", interpretation="Highlights oxygen demand shifts and potential process deviations.", method="Sensor time-series review"),
            _scatter(result, x="biomass", y="product", color="deviation_flag", size="yield", hover=["batch", "time"], title="Biomass–product relationship", interpretation="Shows productivity trade-offs and deviation states.", method="Process-state scatter"),
            _bar(_top(kinetics, "batch_performance_score"), x="batch", y="batch_performance_score", color="deviation_rate", title="Batch performance ranking", interpretation="Combines growth, productivity, yield and deviation burden.", method="Batch-level composite score"),
        ]
    if key == "lims_eln_chain":
        lineage = e.get("lineage_integrity", pd.DataFrame())
        return [
            _group_bar(result, category="status", value="custody_risk", color="alert", title="Sample status and custody risk", interpretation="Shows which operational states carry the greatest review burden.", method="Status-level risk aggregation"),
            _group_bar(result, category="location", value="sample_id", agg="count", color="expiry_status", title="Storage-location occupancy", interpretation="Summarises sample counts and expiry states across storage locations.", method="Inventory count aggregation"),
            _histogram(result, x="days_to_expiry", color="expiry_status", title="Expiry horizon distribution", interpretation="Shows the timing of upcoming sample and reagent expiries.", method="Expiry-window distribution"),
            _scatter(result, x="freeze_thaw", y="custody_risk", color="alert", hover=["sample_id", "location"], title="Freeze–thaw burden and custody risk", interpretation="Identifies samples with repeated handling and elevated operational risk.", method="Sample-risk scatter"),
            _group_bar(lineage, category="orphan_parent", value="sample_id", agg="count", color="self_parent", title="Lineage-integrity findings", interpretation="Counts orphan and self-referential parent relationships requiring correction.", method="Lineage-rule audit"),
        ]
    if key == "causal_perturbation":
        meta = e.get("ivw_meta_analysis", pd.DataFrame())
        return [
            _scatter(result, x="effect", y="standard_error", color="strength_flag", size="instrument_strength", hover=["exposure", "outcome", "p_value"], title="Effect–uncertainty landscape", interpretation="Highlights precise effects supported by stronger instruments.", method="Instrument-level causal screen"),
            _scatter(result, x="instrument_strength", y="priority_score", color="weak_instrument", size="precision", hover=["exposure", "outcome"], title="Instrument strength versus priority", interpretation="Shows how weak instruments reduce confidence in causal hypotheses.", method="Instrument-quality screen"),
            _bar(_top(meta, "ivw_effect"), x="exposure", y="ivw_effect", color="heterogeneity_q", title="IVW meta-analysis effects", interpretation="Summarises pooled causal estimates and heterogeneity across instruments.", method="Inverse-variance weighted aggregation"),
            _waterfall(result, label="exposure", value="effect", title="Causal effect waterfall", interpretation="Orders effect estimates to reveal positive and negative hypotheses.", method="Ordered effect display"),
            _correlation_heatmap(result, columns=["effect", "standard_error", "instrument_strength", "precision", "priority_score"], title="Causal metric correlation", interpretation="Shows relationships among effect magnitude, uncertainty and instrument strength.", method="Pearson correlation"),
        ]
    if key == "explainable_ai_assurance":
        roc = e.get("roc_curve", pd.DataFrame())
        pr = e.get("precision_recall_curve", pd.DataFrame())
        subgroup = e.get("subgroup_assurance", secondary)
        return [
            _scatter(result, x="prediction", y="truth", color="subgroup", size="uncertainty", hover=["sample", "correct"], title="Prediction calibration by subgroup", interpretation="Compares predicted scores with observed outcomes and uncertainty.", method="Sample-level calibration scatter"),
            _roc(roc, title="ROC curve", interpretation="Shows sensitivity–specificity performance over thresholds.", method="Threshold sweep"),
            _line(pr, x="recall", y="precision", title="Precision–recall curve", interpretation="Focuses on performance under class imbalance.", method="Threshold sweep"),
            _bar(_top(subgroup, "accuracy"), x="subgroup", y="accuracy", color="accuracy_gap_from_best", title="Subgroup accuracy audit", interpretation="Compares subgroup performance and highlights gaps from the best-performing group.", method="Subgroup assurance summary"),
            _scatter(result, x="uncertainty", y="absolute_error", color="correct", size="risk_score", hover=["sample", "subgroup"], title="Uncertainty versus error", interpretation="Checks whether uncertainty rises when predictions are wrong or inaccurate.", method="Uncertainty calibration screen"),
        ]
    if key == "multiomics_harmonization":
        pca = e.get("pca_before_after", pd.DataFrame())
        diagnostics = e.get("batch_diagnostics", pd.DataFrame())
        return [
            _scatter(pca, x="pc1", y="pc2", color="stage", hover=["sample"], title="PCA before and after harmonisation", interpretation="Shows whether batch structure is reduced while samples remain distinguishable.", method="Principal-component diagnostic"),
            _box(pd.concat([result.assign(stage="Raw", measurement=result["value"]), result.assign(stage="Harmonised", measurement=result["harmonized_value"])]), x="batch", y="measurement", color="stage", title="Batch distributions before and after correction", interpretation="Compares batch location shifts while retaining raw values.", method="Transparent location correction review"),
            _scatter(result, x="value", y="harmonized_value", color="batch", size="correction_delta", hover=["sample", "feature", "platform"], title="Raw versus harmonised values", interpretation="Highlights features receiving large corrections.", method="Before–after value scatter"),
            _bar(_top(diagnostics, "batch_sd_reduction"), x="feature", y="batch_sd_reduction", title="Batch-effect reduction by feature", interpretation="Ranks features by the reduction in between-batch variability.", method="Between-batch SD diagnostic"),
            _heatmap(result, row="feature", column="batch", value="harmonized_value", title="Harmonised feature heatmap", interpretation="Shows remaining batch-level structure after correction.", method="Mean harmonised value"),
        ]
    if key == "glycomics_glycoproteomics":
        site_stats = e.get("site_resolved_statistics", pd.DataFrame())
        return [
            _scatter(result, x="abundance", y="confidence", color="condition", size="priority_score", hover=["glycopeptide", "site", "glycan"], log_x=True, title="Glycoform abundance and confidence", interpretation="Balances abundance, annotation confidence and condition context.", method="Glycoform evidence scatter"),
            _heatmap(result, row="glycan", column="condition", value="abundance", title="Glycan abundance heatmap", interpretation="Compares glycan abundance across biological conditions.", method="Condition-level mean abundance"),
            _bar(_top(site_stats, "log2_fold_change"), x="site", y="log2_fold_change", color="high_confidence_change", title="Site-resolved glycosylation shifts", interpretation="Ranks sites by condition-associated abundance change and confidence.", method="Site-level differential screen"),
            _box(result, x="condition", y="confidence", color="glycan", title="Annotation confidence by condition", interpretation="Shows confidence distributions and potential condition-specific annotation bias.", method="Confidence distribution"),
            _bar(_top(result, "priority_score"), x="glycopeptide", y="priority_score", color="condition", title="Top glycopeptide priorities", interpretation="Ranks site-specific candidates for expert spectral review.", method="Composite glycopeptide score"),
        ]
    if key == "one_health_environmental":
        weekly = e.get("weekly_outbreak_signals", pd.DataFrame())
        cross_host = e.get("cross_host_summary", pd.DataFrame())
        return [
            _line(weekly, x="week", y="reads", color="pathogen", group="location", title="Surveillance signal over time", interpretation="Tracks pathogen abundance across locations and reporting periods.", method="Weekly aggregated surveillance"),
            _heatmap(result, row="pathogen", column="host", value="read_count", title="Host–pathogen surveillance matrix", interpretation="Shows pathogen signals shared across human, animal and environmental hosts.", method="Mean read-count heatmap"),
            _scatter(weekly, x="rolling_mean", y="outbreak_z", color="outbreak_alert", size="samples", hover=["location", "pathogen", "week"], title="Outbreak signal screen", interpretation="Flags unusually strong signals relative to recent local history.", method="Rolling z-score surveillance"),
            _bar(_top(cross_host, "host_diversity"), x="pathogen", y="host_diversity", color="location", title="Cross-host pathogen diversity", interpretation="Highlights pathogens detected across multiple host categories.", method="Cross-host diversity summary"),
            _group_bar(result, category="location", value="amr_genes", color="host", title="AMR burden by location", interpretation="Compares antimicrobial-resistance signals across sites and host sources.", method="Location-level AMR aggregation"),
        ]
    if key == "synthetic_data_privacy":
        privacy = e.get("privacy_equivalence_classes", pd.DataFrame())
        utility = e.get("distribution_utility", pd.DataFrame())
        return [
            _scatter(result, x="equivalence_class_size", y="measurement", color="privacy_flag", hover=["record_id", "site", "category"], title="Privacy class size versus measurement", interpretation="Shows records with small equivalence classes and potential disclosure risk.", method="k-anonymity screening"),
            _histogram(result, x="equivalence_class_size", color="privacy_flag", title="Equivalence-class distribution", interpretation="Displays the distribution of anonymity-set sizes.", method="k-anonymity distribution"),
            _scatter(privacy, x="l_diversity", y="t_closeness", color="size", size="size", hover=["equivalence_class"], title="Privacy-risk trade-off", interpretation="Compares diversity and distributional distance across equivalence classes.", method="l-diversity and t-closeness screen"),
            _bar(_top(utility, "ks_statistic"), x="column", y="ks_statistic", color="ks_p_value", title="Synthetic-data utility by column", interpretation="Highlights features with the largest source-versus-synthetic distribution shift.", method="Kolmogorov–Smirnov comparison"),
            _correlation_heatmap(result, columns=["age", "measurement", "equivalence_class_size"], title="Synthetic feature correlation", interpretation="Checks whether major numerical relationships remain visible after synthesis.", method="Pearson correlation"),
        ]
    return []

def _visuals_for_nextgen(
    key: str,
    data: pd.DataFrame,
    result: pd.DataFrame,
    secondary: pd.DataFrame,
    extras: Mapping[str, pd.DataFrame],
) -> list[ScientificVisual | None]:
    e = {name: _frame(table) for name, table in extras.items()}
    if key == "population_gwas":
        return [
            _manhattan(result, title="Genome-wide association overview", interpretation="Shows association evidence across chromosomes with the conventional genome-wide threshold.", method="Variant-level association screen"),
            _scatter(result.assign(minus_log10_p=_safe_log10(result["p_value"])), x="effect", y="minus_log10_p", color="qc_pass", size="maf", hover=["variant", "chrom", "q_value"], title="Association effect volcano", interpretation="Combines effect magnitude, statistical evidence and variant QC.", method="Association effect screen"),
            _scatter(secondary, x="call_rate", y="phenotype", hover=["sample"], title="Sample call rate and phenotype", interpretation="Identifies low-call-rate samples and phenotype outliers.", method="Sample-level QC"),
            _histogram(result, x="maf", color="qc_pass", title="Minor-allele frequency distribution", interpretation="Shows the frequency spectrum and variants failing QC.", method="MAF distribution"),
            _bar(_top(result, "priority_score"), x="variant", y="priority_score", color="qc_pass", title="Top association candidates", interpretation="Ranks variants using effect, p-value and QC evidence.", method="Composite association score"),
        ]
    if key == "structural_variant_repeat":
        return [
            _scatter(result, x="start", y="size_bp", color="sv_type", size="support", hover=["sv_id", "chrom", "gene", "caller"], log_y=True, title="Structural-variant landscape", interpretation="Maps event size, genomic position, type and support.", method="SV event scatter"),
            _group_bar(result, category="sv_type", value="size_bp", color="low_confidence", title="SV burden by type", interpretation="Compares event size and confidence across structural-variant classes.", method="Type-level mean size"),
            _heatmap(result, row="gene", column="sv_type", value="priority_score", title="Gene-impact heatmap", interpretation="Highlights genes repeatedly affected by high-priority SV classes.", method="Mean priority heatmap"),
            _scatter(result, x="quality_norm", y="support_norm", color="low_confidence", size="gene_impact", hover=["sv_id", "caller"], title="Caller evidence and quality", interpretation="Identifies poorly supported or low-quality calls requiring review.", method="Normalised evidence QC"),
            _bar(_top(result, "priority_score"), x="sv_id", y="priority_score", color="sv_type", title="Top structural-variant candidates", interpretation="Ranks variants by support, quality, size and gene impact.", method="Composite SV priority"),
        ]
    if key == "longitudinal_multiomics":
        slopes = e.get("subject_slopes", secondary)
        raw_summary = data.groupby([column for column in ["time", "omics_layer", "group"] if column in data.columns], as_index=False)["value"].mean()
        return [
            _line(raw_summary, x="time", y="value", color="omics_layer", group="group", title="Mean multi-omics trajectories", interpretation="Shows average temporal patterns across omics layers and groups.", method="Time-point mean trajectory"),
            _scatter(slopes, x="baseline", y="slope", color="group", size="visits", hover=["subject", "feature", "omics_layer"], title="Subject-level trajectory slopes", interpretation="Compares individual baseline values and longitudinal change.", method="Per-subject linear slope"),
            _scatter(result, x="slope_difference", y="effect_size", color="omics_layer", size="subjects", hover=["feature", "q_value"], title="Temporal effect landscape", interpretation="Highlights features with strong between-group slope differences.", method="Group trajectory comparison"),
            _heatmap(slopes, row="feature", column="subject", value="slope", title="Subject-by-feature slope heatmap", interpretation="Displays heterogeneous temporal responses across subjects.", method="Slope heatmap"),
            _bar(_top(result, "priority_score"), x="feature", y="priority_score", color="omics_layer", title="Top longitudinal features", interpretation="Ranks features using effect size, slope difference and statistical evidence.", method="Composite temporal priority"),
        ]
    if key == "rna_isoform_splicing":
        return [
            _scatter(result.assign(minus_log10_q=_safe_log10(result["q_value"])), x="delta_usage", y="minus_log10_q", color="supported", size="median_junction_support", hover=["gene", "transcript"], title="Differential isoform-usage volcano", interpretation="Combines usage shift, FDR and junction support.", method="Transcript-usage differential screen"),
            _scatter(result, x="mean_usage", y="median_junction_support", color="supported", size="priority_score", hover=["gene", "transcript"], title="Isoform abundance and junction support", interpretation="Separates well-supported abundant isoforms from weak candidates.", method="Isoform evidence scatter"),
            _heatmap(data, row="transcript", column="group", value="abundance", title="Transcript abundance heatmap", interpretation="Compares transcript usage across biological groups.", method="Group-level mean abundance"),
            _group_bar(secondary, category="gene", value="transcripts", title="Isoform complexity by gene", interpretation="Shows genes with the largest number of represented transcripts.", method="Transcript-count aggregation"),
            _bar(_top(result, "priority_score"), x="transcript", y="priority_score", color="supported", title="Top isoform-switch candidates", interpretation="Ranks transcripts by differential usage and junction evidence.", method="Composite isoform priority"),
        ]
    if key == "epitranscriptomics":
        return [
            _scatter(result.assign(minus_log10_q=_safe_log10(result["q_value"])), x="delta_fraction", y="minus_log10_q", color="qc_pass", size="median_coverage", hover=["site", "transcript"], title="Differential modification volcano", interpretation="Combines modification change, FDR and coverage QC.", method="Site-level differential screen"),
            _scatter(result, x="median_coverage", y="replicate_sd", color="qc_pass", size="priority_score", hover=["site", "transcript"], title="Coverage and replicate consistency", interpretation="Highlights sites with adequate depth and low replicate variability.", method="Site QC scatter"),
            _heatmap(data, row="site", column="condition", value="modified_fraction", title="Modification-fraction heatmap", interpretation="Compares site-level modification fractions across conditions.", method="Condition-level mean fraction"),
            _group_bar(secondary, category="transcript", value="sites", color="mean_fraction", title="Modification burden by transcript", interpretation="Shows transcripts carrying many or highly modified sites.", method="Transcript-level aggregation"),
            _bar(_top(result, "priority_score"), x="site", y="priority_score", color="qc_pass", title="Top modification-site priorities", interpretation="Ranks sites using change, statistical support, depth and consistency.", method="Composite site priority"),
        ]
    if key == "strain_microbiome":
        diversity = e.get("sample_diversity", secondary)
        return [
            _heatmap(data, row="strain", column="sample", value="abundance", title="Strain abundance heatmap", interpretation="Shows strain-level abundance patterns across samples.", method="Sample-by-strain abundance"),
            _box(diversity, x="group", y="shannon", title="Alpha diversity by group", interpretation="Compares within-sample strain diversity across groups.", method="Shannon diversity distribution"),
            _scatter(result.assign(minus_log10_q=_safe_log10(result["q_value"])), x="log2_fold_change", y="minus_log10_q", color="feature_type", size="prevalence", hover=["feature"], title="Differential microbial features", interpretation="Highlights group-associated strains, pathways and resistance features.", method="Feature-level differential screen"),
            _scatter(diversity, x="taxa", y="strains", color="group", size="shannon", hover=["sample"], title="Taxa and strain richness", interpretation="Shows sample-level richness and diversity patterns.", method="Sample diversity scatter"),
            _bar(_top(result, "priority_score"), x="feature", y="priority_score", color="feature_type", title="Top microbiome features", interpretation="Ranks prevalent, differential and statistically supported features.", method="Composite microbiome priority"),
        ]
    if key == "cell_atlas_mapping":
        return [
            _scatter(result, x="similarity", y="marker_agreement", color="reference_label", size="annotation_confidence", hover=["cell", "query_cluster", "batch", "novel_state_flag"], title="Reference mapping confidence", interpretation="Shows agreement between similarity and marker evidence for each cell.", method="Cell-level annotation confidence"),
            _box(result, x="reference_label", y="annotation_confidence", color="novel_state_flag", title="Confidence by transferred label", interpretation="Compares annotation confidence and novelty flags across labels.", method="Label-level confidence distribution"),
            _heatmap(result, row="query_cluster", column="reference_label", value="annotation_confidence", title="Cluster-to-reference mapping matrix", interpretation="Shows the dominant reference labels assigned to query clusters.", method="Mean mapping confidence"),
            _bar(_top(secondary, "novel_fraction"), x="reference_label", y="novel_fraction", color="mean_confidence", title="Novel-state burden by label", interpretation="Highlights labels associated with many low-confidence or novel cells.", method="Label-level novelty summary"),
            _group_bar(result, category="batch", value="batch_shift", color="novel_state_flag", title="Batch-shift diagnostic", interpretation="Shows whether mapping confidence differs systematically across batches.", method="Batch-level shift aggregation"),
        ]
    if key == "phenotypic_screening":
        wells = e.get("normalised_wells", pd.DataFrame())
        return [
            _line(wells, x="dose", y="normalised_response", color="compound", group="plate", title="Dose–response profiles", interpretation="Shows normalised response across dose for each compound.", method="Plate-normalised dose response"),
            _bar(_top(result, "priority_score"), x="compound", y="priority_score", color="dose_response_monotonicity", title="Hit priority ranking", interpretation="Ranks compounds by potency, reproducibility and dose-response consistency.", method="Composite hit score"),
            _scatter(result, x="replicate_cv", y="auc_logdose", color="dose_response_monotonicity", size="wells", hover=["compound"], title="Reproducibility versus response area", interpretation="Separates strong reproducible hits from noisy responses.", method="Compound-level QC scatter"),
            _bar(_top(secondary, "z_prime"), x="plate", y="z_prime", title="Plate Z-prime quality", interpretation="Compares assay separation and identifies weak plates.", method="Control-based Z-prime"),
            _heatmap(wells, row="plate", column="well", value="normalised_response", title="Plate-response heatmap", interpretation="Shows spatial response patterns and potential edge effects.", method="Well-level normalised response"),
        ]
    if key == "organoid_3d":
        raw_trajectory = data.groupby([column for column in ["time", "condition"] if column in data.columns], as_index=False)["area"].mean()
        return [
            _line(raw_trajectory, x="time", y="area", color="condition", title="Organoid growth trajectories", interpretation="Compares mean organoid area over time across conditions.", method="Condition-level growth curve"),
            _scatter(result, x="growth_rate_log_area", y="mean_viability", color="condition", size="final_area", hover=["organoid", "qc_flag"], title="Growth and viability landscape", interpretation="Balances expansion rate, viability and final size.", method="Organoid-level phenotype scatter"),
            _box(result, x="condition", y="mean_circularity", color="qc_flag", title="Morphology by condition", interpretation="Shows shape consistency and QC flags across treatment conditions.", method="Circularity distribution"),
            _bar(_top(secondary, "mean_growth"), x="condition", y="mean_growth", color="mean_viability", title="Condition-level organoid performance", interpretation="Compares growth and viability across experimental conditions.", method="Condition summary"),
            _bar(_top(result, "priority_score"), x="organoid", y="priority_score", color="condition", title="Top organoid responses", interpretation="Ranks organoids by growth, viability and morphology quality.", method="Composite organoid priority"),
        ]
    if key == "protein_language_design":
        mutations = e.get("mutation_proposals", pd.DataFrame())
        return [
            _scatter(result, x="stability_proxy", y="activity_proxy", color="constraint_group", size="sequence_quality_score", hover=["sequence_id", "parent_id", "constraint_flag"], title="Protein design candidate space", interpretation="Shows activity, stability, sequence quality and design constraints.", method="Sequence-level design scatter"),
            _radar(result, label="sequence_id", metrics=["activity_proxy", "stability_proxy", "hydrophobic_fraction", "charged_fraction", "sequence_quality_score", "priority_score"], ranking="priority_score", title="Top sequence profiles", interpretation="Compares normalised design dimensions for leading sequences.", method="Normalised sequence radar"),
            _scatter(result, x="composition_entropy", y="liability_motifs", color="constraint_flag", size="length", hover=["sequence_id"], title="Sequence complexity and liabilities", interpretation="Flags low-complexity or motif-heavy candidates.", method="Sequence-quality screen"),
            _bar(_top(result, "priority_score"), x="sequence_id", y="priority_score", color="constraint_group", title="Protein candidate ranking", interpretation="Ranks sequences by activity, stability and quality proxies.", method="Composite sequence priority"),
            _group_bar(mutations, category="proposal_type", value="mutation", agg="count", color="parent_id", title="Mutation proposal mix", interpretation="Shows the types and parent coverage of generated mutation proposals.", method="Proposal-type aggregation"),
        ]
    if key == "enzyme_pathway_design":
        bottlenecks = e.get("pathway_bottlenecks", pd.DataFrame())
        return [
            _scatter(result, x="activity", y="stability", color="host", size="flux", hover=["enzyme", "variant", "reaction", "cofactor"], title="Enzyme activity–stability landscape", interpretation="Shows enzyme performance and pathway flux across hosts.", method="Variant-level enzyme scatter"),
            _radar(result, label="variant", metrics=["activity_norm", "stability_norm", "flux_norm", "priority_score"], ranking="priority_score", title="Top enzyme variant profiles", interpretation="Compares normalised catalytic and pathway dimensions.", method="Normalised variant radar"),
            _bar(_top(bottlenecks, "bottleneck_score"), x="reaction", y="bottleneck_score", color="hosts", title="Pathway bottleneck ranking", interpretation="Highlights reactions with low flux or weak activity support.", method="Reaction bottleneck score"),
            _heatmap(result, row="reaction", column="host", value="flux", title="Reaction flux by host", interpretation="Compares pathway throughput across host organisms.", method="Mean flux heatmap"),
            _group_bar(result, category="cofactor", value="priority_score", color="host", title="Cofactor and host performance", interpretation="Shows how cofactor usage and host context influence candidate quality.", method="Cofactor-level mean priority"),
        ]
    if key == "host_pathogen_interaction":
        return [
            _scatter(result, x="evidence", y="druggability", color="evidence_gap", size="pathogen_essentiality", hover=["host_protein", "pathogen_protein", "source_count"], title="Host–pathogen target landscape", interpretation="Prioritises essential, druggable and well-supported interactions.", method="Interaction-level evidence scatter"),
            _network(result, source="host_protein", target="pathogen_protein", weight="priority_score", title="Host–pathogen interaction network", interpretation="Displays the dominant cross-species protein interactions.", method="Circular bipartite network"),
            _bar(_top(secondary, "mean_priority"), x="pathogen_protein", y="mean_priority", color="evidence_gaps", title="Pathogen target ranking", interpretation="Ranks pathogen proteins by host-partner support and essentiality.", method="Target-level aggregation"),
            _heatmap(result, row="host_protein", column="pathogen_protein", value="priority_score", title="Interaction-priority heatmap", interpretation="Shows concentrated interaction evidence across host and pathogen proteins.", method="Mean priority matrix"),
            _scatter(result, x="host_effect", y="pathogen_essentiality", color="evidence_gap", size="source_count", hover=["host_protein", "pathogen_protein"], title="Host effect versus pathogen essentiality", interpretation="Highlights interactions combining strong host phenotype and pathogen dependence.", method="Biological relevance screen"),
        ]
    if key == "virology_evolution":
        return [
            _scatter(result, x="position", y="frequency", color="gene", size="priority_score", hover=["sample", "ref", "alt", "lineage_marker"], title="Viral variant-frequency landscape", interpretation="Maps within-sample variant frequencies across the genome.", method="Position-frequency scatter"),
            _heatmap(result, row="sample", column="gene", value="frequency", title="Sample-by-gene variant heatmap", interpretation="Shows gene-level variant burden across samples.", method="Mean frequency heatmap"),
            _bar(_top(secondary, "frequency_entropy"), x="sample", y="frequency_entropy", color="mixed_infection_review", title="Within-sample diversity", interpretation="Highlights samples with heterogeneous viral populations.", method="Frequency entropy summary"),
            _group_bar(result, category="gene", value="minor_variant", agg="sum", color="lineage_marker", title="Minor variants by gene", interpretation="Counts low-frequency variation and lineage-marker status across genes.", method="Gene-level variant count"),
            _bar(_top(result, "priority_score"), x="position", y="priority_score", color="gene", title="Top viral variants", interpretation="Ranks variants by frequency, minor/consensus status and lineage relevance.", method="Composite variant priority"),
        ]
    if key == "rare_variant_family":
        return [
            _scatter(result, x="frequency", y="priority_score", color="impact", size="phenotype_match", hover=["family", "gene", "variant", "inheritance", "inheritance_consistent"], log_x=True, title="Rarity–phenotype prioritisation", interpretation="Shows how rarity, impact, phenotype match and inheritance combine.", method="Family variant prioritisation"),
            _waterfall(result, label="gene", value="priority_score", title="Candidate priority waterfall", interpretation="Orders genes from lower to higher family-specific priority.", method="Ordered priority display"),
            _heatmap(result, row="gene", column="inheritance", value="priority_score", title="Gene-by-inheritance evidence", interpretation="Shows which genes are supported under different inheritance models.", method="Mean priority heatmap"),
            _bar(_top(secondary, "max_priority"), x="gene", y="max_priority", color="consistent_inheritance", title="Family gene-burden ranking", interpretation="Ranks genes by maximum priority and inheritance consistency across families.", method="Gene-level aggregation"),
            _group_bar(result, category="impact", value="manual_review_required", agg="sum", color="inheritance_consistent", title="Manual review burden", interpretation="Counts review-required variants by predicted impact and inheritance consistency.", method="Review-queue summary"),
        ]

    if key == "digital_pathology_foundation":
        drift = e.get("scanner_site_drift", secondary)
        tiles = e.get("slide_tumour_heatmap", data)
        return [
            _scatter(result, x="tissue_fraction", y="tumour_burden", color="qc_flag", size="tiles", hover=["slide_id", "scanner", "site", "ood_risk"], title="Slide tissue–tumour landscape", interpretation="Balances tissue adequacy, tumour burden and slide-level QC.", method="Slide-level whole-slide evidence summary"),
            _box(data, x="scanner", y="embedding_score", color="site", title="Embedding stability by scanner", interpretation="Shows scanner/site shifts that may indicate domain drift.", method="Tile-embedding distribution by acquisition source"),
            _heatmap(tiles, row="slide_id", column="tile_id", value="tumour_probability", title="Tile-level tumour probability heatmap", interpretation="Locates high-probability tiles within each slide for pathologist review.", method="Bounded tile probability matrix"),
            _scatter(drift, x="mean_embedding", y="embedding_drift_score", color="drift_review", size="slides", hover=["site", "scanner", "mean_tumour"], title="Scanner and site drift review", interpretation="Highlights acquisition groups with unusual embedding distributions.", method="Robust median absolute-deviation drift score"),
            _bar(_top(result, "priority_score"), x="slide_id", y="priority_score", color="qc_flag", title="Slide review priority", interpretation="Ranks slides while suppressing low-tissue and out-of-domain evidence.", method="Tumour burden × in-domain quality score"),
        ]
    if key == "long_read_epigenome":
        regions = e.get("region_condition_matrix", pd.DataFrame())
        imbalance = e.get("haplotype_imbalance", secondary)
        volcano = result.copy()
        if "q_value" in volcano:
            volcano["minus_log10_q"] = _safe_log10(volcano["q_value"])
        if "delta_methylation" in volcano:
            volcano["absolute_delta"] = pd.to_numeric(volcano["delta_methylation"], errors="coerce").abs()
        return [
            _scatter(volcano, x="delta_methylation", y="minus_log10_q", color="qc_pass", size="median_coverage", hover=["region", "haplotype", "q_value"], title="Differential methylation volcano", interpretation="Combines methylation change, FDR and coverage readiness.", method="Coverage-gated Welch screen with Benjamini–Hochberg FDR"),
            _heatmap(regions, row="region", column="condition", value="mean_methylation", title="Condition-by-region methylation map", interpretation="Shows regional methylation shifts across biological conditions.", method="Regional mean methylation heatmap"),
            _box(data, x="condition", y="methylation_fraction", color="haplotype", title="Haplotype methylation distributions", interpretation="Compares H1/H2 methylation distributions between conditions.", method="Read-backed haplotype distribution review"),
            _scatter(volcano, x="median_coverage", y="absolute_delta", color="qc_pass", size="samples", hover=["region", "haplotype"], title="Coverage versus methylation effect", interpretation="Separates adequately covered strong effects from unstable low-depth findings.", method="Coverage/effect QC landscape"),
            _bar(_top(imbalance, "allelic_imbalance"), x="region", y="allelic_imbalance", title="Allelic methylation imbalance", interpretation="Ranks loci with the largest H1–H2 methylation differences.", method="Absolute haplotype methylation difference"),
        ]
    if key == "single_cell_long_read_isoforms":
        dominant = e.get("dominant_isoforms", pd.DataFrame())
        return [
            _scatter(result, x="mean_fraction", y="support_score", color="cluster", size="cells", hover=["gene", "transcript", "full_length_rate", "median_junctions"], title="Isoform usage and support", interpretation="Balances cluster usage, cell support, full-length evidence and junction depth.", method="Cluster-level isoform support landscape"),
            _heatmap(result, row="transcript", column="cluster", value="mean_fraction", title="Cluster-specific isoform usage", interpretation="Shows transcript usage shifts across cell populations.", method="Mean within-gene isoform fraction heatmap"),
            _group_bar(result, category="cluster", value="full_length_rate", color="gene", title="Full-length transcript support", interpretation="Compares full-length evidence across clusters and genes.", method="Cluster/gene mean full-length rate"),
            _bar(_top(dominant, "priority_score"), x="transcript", y="priority_score", color="isoform_switch_candidate", title="Dominant isoform-switch candidates", interpretation="Prioritises dominant transcripts that differ across clusters.", method="Dominant-cluster isoform comparison"),
            _scatter(result, x="median_junctions", y="total_umis", color="cluster", size="priority_score", hover=["gene", "transcript"], title="Junction and UMI evidence", interpretation="Identifies transcripts supported by both splice junctions and molecule counts.", method="Junction–UMI evidence screen"),
        ]
    if key == "biomedical_foundation_model_hub":
        coverage = e.get("modality_task_coverage", secondary)
        licences = e.get("licence_review_matrix", pd.DataFrame())
        return [
            _scatter(result, x="parameter_count", y="benchmark_score", color="resource_tier", size="embedding_dim", hover=["model_id", "modality", "task", "license", "local_ready"], log_x=True, title="Performance versus model scale", interpretation="Compares benchmark evidence with parameter count and hardware tier.", method="Model registry performance/resource landscape"),
            _heatmap(coverage, row="modality", column="task", value="mean_benchmark", title="Modality–task benchmark coverage", interpretation="Shows where the local model catalogue has strong or weak benchmark support.", method="Mean benchmark coverage matrix"),
            _group_bar(licences, category="license", value="models", color="modality", title="Licence and modality portfolio", interpretation="Separates permissive and review-required model assets.", method="Licence/modality model counts"),
            _scatter(result, x="benchmark_score", y="readiness_score", color="release_blocked", size="parameter_count", hover=["model_id", "resource_tier", "license"], title="Benchmark and operational readiness", interpretation="Distinguishes high-performing models from assets blocked by licence or local availability.", method="Operational model-readiness score"),
            _bar(_top(result, "priority_score"), x="model_id", y="priority_score", color="modality", title="Deployment-ready model ranking", interpretation="Ranks models with benchmark, local-asset and licence gates combined.", method="Gated foundation-model priority"),
        ]
    if key == "amr_surveillance":
        temporal = e.get("temporal_resistance_trends", pd.DataFrame())
        gene_matrix = e.get("gene_species_matrix", pd.DataFrame())
        return [
            _scatter(result, x="mean_probability", y="concordance", color="review_required", size="isolates", hover=["species", "lineage", "amr_gene", "location"], title="Genotype–phenotype concordance", interpretation="Highlights AMR signals with high predicted resistance but weak phenotypic agreement.", method="Grouped isolate concordance review"),
            _heatmap(gene_matrix, row="species", column="amr_gene", value="resistance_rate", title="Species–AMR gene resistance map", interpretation="Shows resistance burden across species and detected resistance determinants.", method="Species/gene resistance-rate matrix"),
            _group_bar(secondary, category="location", value="resistance_rate", color="species", title="Regional resistance burden", interpretation="Compares resistance rates by location and organism.", method="Location/species surveillance summary"),
            _bar(_top(result, "emergence_score"), x="lineage", y="emergence_score", color="amr_gene", title="Emerging lineage signals", interpretation="Ranks lineages combining isolate count, resistance rate and model support.", method="Transparent emergence score"),
            _heatmap(temporal, row="species", column="month", value="resistance_rate", title="Resistance trend timeline", interpretation="Shows month-level resistance changes across species.", method="Monthly surveillance heatmap"),
        ]
    if key == "spatial_medicine_tme":
        points = e.get("spatial_points", data)
        genes = e.get("gene_region_expression", pd.DataFrame())
        return [
            _spatial(points, title="Spatial tumour microenvironment map", interpretation="Displays cell/spot positions with expression or compartment context.", method="Spatial coordinate scatter with reversed tissue axis"),
            _scatter(result, x="immune", y="tumour", color="region", size="stroma", hover=["patient", "immune_exclusion_score"], title="Immune–tumour compartment balance", interpretation="Shows immune exclusion and stromal context across patient regions.", method="Compartment-fraction landscape"),
            _heatmap(genes, row="gene", column="region", value="mean_expression", title="Regional expression programme", interpretation="Compares mean gene expression between tumour core and margin regions.", method="Gene/region mean-expression heatmap"),
            _bar(_top(result, "immune_exclusion_score"), x="patient", y="immune_exclusion_score", color="region", title="Immune-exclusion priorities", interpretation="Ranks patient regions with high tumour fraction and limited immune presence.", method="Tumour × inverse immune fraction"),
            _group_bar(secondary, category="cell_type", value="mean_expression", color="patient", title="Cell-type expression context", interpretation="Compares cell-type expression profiles across patients.", method="Patient/cell-type mean expression"),
        ]
    if key == "gene_therapy_vector":
        matrix = e.get("promoter_vector_matrix", secondary)
        return [
            _scatter(result, x="cargo_bp", y="packaging_margin_bp", color="vector_type", size="tropism_score", hover=["construct", "promoter", "packaging_pass", "release_blocked"], title="Cargo-capacity landscape", interpretation="Shows construct size, remaining packaging margin and tropism context.", method="Vector-specific packaging-capacity review"),
            _radar(result, label="construct", metrics=["tropism_score", "safety_score", "priority_score"], ranking="priority_score", title="Top vector construct profiles", interpretation="Compares tropism, safety and release-gated priority for leading constructs.", method="Normalised vector evidence radar"),
            _heatmap(matrix, row="vector_type", column="promoter", value="mean_safety", title="Vector–promoter safety matrix", interpretation="Compares safety performance across vector and promoter combinations.", method="Mean safety by vector/promoter"),
            _scatter(result, x="immunogenicity_risk", y="integration_risk", color="release_blocked", size="cargo_bp", hover=["construct", "vector_type", "promoter"], title="Vector safety-risk map", interpretation="Identifies constructs requiring immunogenicity or integration-risk review.", method="Two-axis vector safety screen"),
            _bar(_top(result, "priority_score"), x="construct", y="priority_score", color="vector_type", title="Vector construct ranking", interpretation="Ranks constructs after packaging and safety gates.", method="Release-gated vector priority"),
        ]
    if key == "cell_therapy_cart":
        matrix = e.get("antigen_domain_matrix", secondary)
        return [
            _scatter(result, x="off_tumour_risk", y="exhaustion_score", color="safety_review", size="manufacturability", hover=["construct", "antigen", "costim_domain", "engineering_score"], title="CAR safety and exhaustion landscape", interpretation="Balances off-tumour risk, exhaustion and manufacturing readiness.", method="Construct-level CAR safety screen"),
            _radar(result, label="construct", metrics=["manufacturability", "engineering_score", "priority_score"], ranking="priority_score", title="Top CAR construct profiles", interpretation="Compares engineering and manufacturability dimensions for leading constructs.", method="Normalised CAR candidate radar"),
            _heatmap(matrix, row="antigen", column="costim_domain", value="mean_score", title="Antigen–costimulatory domain matrix", interpretation="Shows which target/domain combinations produce the strongest engineering scores.", method="Mean engineering score matrix"),
            _scatter(result, x="scfv_affinity", y="manufacturability", color="costim_domain", size="engineering_score", hover=["construct", "antigen", "safety_review"], log_x=True, title="Affinity–manufacturability trade-off", interpretation="Highlights constructs that avoid over-optimising affinity at the expense of manufacturability.", method="CAR developability landscape"),
            _bar(_top(result, "priority_score"), x="construct", y="priority_score", color="antigen", title="CAR construct ranking", interpretation="Ranks safety-cleared constructs across antigen targets.", method="Safety-gated engineering priority"),
        ]
    if key == "federated_biomedical_ai":
        rounds = e.get("site_round_metrics", data)
        return [
            _line(result, x="round", y="global_metric", title="Global federated performance", interpretation="Tracks weighted global performance across training rounds.", method="Sample-weighted federated metric trajectory"),
            _scatter(rounds, x="privacy_epsilon", y="metric_value", color="site", size="samples", hover=["round", "drift_score"], title="Privacy–utility frontier", interpretation="Shows the relationship between privacy budget and local-site utility.", method="Site/round privacy-utility landscape"),
            _heatmap(rounds, row="site", column="round", value="metric_value", title="Site performance by round", interpretation="Reveals persistent weak sites and round-specific instability.", method="Site × round metric matrix"),
            _bar(_top(secondary, "mean_metric"), x="site", y="mean_metric", color="site_outlier", title="Site performance and outliers", interpretation="Ranks participating sites and marks large deviations from the federation median.", method="Site-level outlier review"),
            _line(result, x="round", y="mean_drift", title="Federation drift trajectory", interpretation="Tracks cross-site drift across rounds to support governance decisions.", method="Round-level mean drift"),
        ]
    if key == "clinical_biomarker_survival":
        km = e.get("kaplan_meier_curves", pd.DataFrame())
        patient = e.get("patient_risk_waterfall", pd.DataFrame())
        return [
            _survival(km, title="Biomarker-stratified survival", interpretation="Displays exploratory Kaplan–Meier curves by treatment arm and biomarker stratum.", method="Product-limit survival estimate; exploratory only"),
            _scatter(patient, x="biomarker", y="time", color="biomarker_group", size="event", hover=["patient", "arm", "response", "site"], title="Patient biomarker and follow-up", interpretation="Shows patient-level biomarker values, follow-up and event status.", method="Patient-level stratification landscape"),
            _group_bar(result, category="biomarker_group", value="response_rate", color="arm", title="Response by biomarker stratum", interpretation="Compares response rates across treatment and biomarker groups.", method="Stratified response summary"),
            _bar(_top(secondary, "event_rate"), x="site", y="event_rate", color="response_rate", title="Site heterogeneity", interpretation="Shows site-level event and response differences requiring validation review.", method="Site-level outcome summary"),
            _waterfall(patient, label="patient", value="biomarker", title="Patient biomarker waterfall", interpretation="Orders patients by biomarker level while preserving arm and outcome metadata in the data table.", method="Ordered patient biomarker display"),
        ]
    if key == "protein_ligand_codesign":
        matrix = e.get("variant_ligand_matrix", pd.DataFrame())
        return [
            _scatter(result, x="protein_score", y="ligand_score", color="pareto_like", size="interface_score", hover=["candidate", "protein_variant", "ligand", "selectivity_risk"], title="Protein–ligand objective space", interpretation="Shows balanced candidates across protein, ligand and interface objectives.", method="Multi-objective co-design landscape"),
            _scatter(result, x="interface_score", y="joint_score", color="selectivity_review", size="selectivity_risk", hover=["candidate", "protein_variant", "ligand"], title="Interface quality and selectivity risk", interpretation="Highlights strong interfaces that may still require selectivity review.", method="Interface/selectivity risk screen"),
            _heatmap(matrix, row="protein_variant", column="ligand", value="joint_score", title="Protein variant–ligand score matrix", interpretation="Shows compatible variant/ligand pairs across the co-design panel.", method="Mean joint-score matrix"),
            _radar(result, label="candidate", metrics=["protein_score", "ligand_score", "interface_score", "joint_score", "priority_score"], ranking="priority_score", title="Top co-design candidate profiles", interpretation="Compares normalised objective balance for leading pairs.", method="Normalised multi-objective radar"),
            _bar(_top(result, "priority_score"), x="candidate", y="priority_score", color="pareto_like", title="Co-design candidate ranking", interpretation="Ranks selectivity-cleared candidate pairs and highlights Pareto-like solutions.", method="Selectivity-gated joint priority"),
        ]
    if key == "pangenome_population_medicine":
        matrix = e.get("population_allele_matrix", result)
        return [
            _heatmap(matrix, row="variant", column="population", value="allele_frequency", title="Population allele-frequency matrix", interpretation="Shows population-specific allele frequency patterns across graph variants.", method="Population × variant frequency matrix"),
            _scatter(result, x="reference_bias", y="population_delta", color="bias_review", size="clinical_weight", hover=["population", "variant", "path"], title="Reference bias versus population specificity", interpretation="Identifies clinically weighted variants whose population signal may be distorted by reference bias.", method="Population delta/reference-bias screen"),
            _group_bar(secondary, category="population", value="mean_bias", color="population_specific", title="Population reference-bias burden", interpretation="Compares average reference bias and population-specific finding counts.", method="Population-level graph bias summary"),
            _heatmap(result, row="population", column="path", value="reference_bias", title="Population path-bias map", interpretation="Shows graph paths with uneven representation across populations.", method="Population/path mean reference-bias matrix"),
            _bar(_top(result, "priority_score"), x="variant", y="priority_score", color="population", title="Population-specific variant ranking", interpretation="Ranks clinically weighted variants after reference-bias adjustment.", method="Bias-adjusted population priority"),
        ]
    if key == "pharmacovigilance_intelligence":
        outcomes = e.get("serious_outcome_summary", pd.DataFrame())
        return [
            _scatter(result, x="reporting_odds_ratio", y="proportional_reporting_ratio", color="signal_flag", size="reports", hover=["drug", "event", "serious_rate", "information_component"], log_x=True, log_y=True, title="Disproportionality signal landscape", interpretation="Compares ROR and PRR while preserving report counts and seriousness.", method="Continuity-corrected ROR/PRR screen"),
            _heatmap(result, row="drug", column="event", value="information_component", title="Drug–event information component", interpretation="Shows drug–event pairs reported more often than expected.", method="Observed-versus-expected information component matrix"),
            _scatter(result, x="information_component", y="serious_rate", color="signal_flag", size="reports", hover=["drug", "event", "ror_lower_95"], title="Signal strength and seriousness", interpretation="Prioritises statistically supported signals with serious outcomes.", method="Information component/seriousness landscape"),
            _group_bar(outcomes, category="outcome", value="reports", color="drug", title="Safety outcomes by drug", interpretation="Compares reported outcomes and drug-level case volume.", method="Drug/outcome report counts"),
            _bar(_top(result, "priority_score"), x="event", y="priority_score", color="drug", title="Safety-signal review queue", interpretation="Ranks drug–event pairs for expert pharmacovigilance review.", method="Signal/seriousness composite priority"),
        ]
    if key == "synthetic_cohort_trial":
        km = e.get("kaplan_meier_curves", pd.DataFrame())
        balance = e.get("covariate_balance", pd.DataFrame())
        patients = e.get("patient_level_simulation", data)
        return [
            _survival(km, title="Simulated arm survival", interpretation="Displays synthetic time-to-event trajectories for scenario stress-testing.", method="Kaplan–Meier estimate on synthetic outcomes"),
            _scatter(patients, x="baseline_risk", y="outcome", color="arm", size="age", hover=["patient", "site", "time", "event"], title="Baseline risk and simulated outcomes", interpretation="Shows treatment-arm outcome patterns across baseline risk.", method="Patient-level synthetic scenario landscape"),
            _waterfall(balance, label="covariate", value="smd", title="Covariate balance Love plot", interpretation="Shows signed standardised mean differences between the first and last trial arms.", method="Standardised mean difference"),
            _heatmap(patients, row="site", column="arm", value="outcome", title="Site-by-arm outcome map", interpretation="Highlights site heterogeneity in simulated outcomes.", method="Mean synthetic outcome heatmap"),
            _bar(_top(result, "balance_score"), x="arm", y="balance_score", color="outcome_rate", title="Arm balance and outcome summary", interpretation="Compares arm balance and synthetic outcome rates.", method="Arm-level simulation summary"),
        ]
    if key == "autonomous_lab_planner":
        design = e.get("design_matrix", pd.DataFrame())
        schedule = e.get("resource_schedule", pd.DataFrame())
        return [
            _scatter(result, x="total_cost", y="design_completeness", color="review_required", size="replicates", hover=["experiment_id", "hypothesis", "factor", "level"], title="Experiment cost and design completeness", interpretation="Shows which plans are expensive, incomplete or under-replicated.", method="Control/replicate/cost design review"),
            _heatmap(design, row="factor", column="level", value="total_cost", title="Factor–level cost matrix", interpretation="Shows resource concentration across planned experimental factors and levels.", method="Factor/level total-cost matrix"),
            _group_bar(secondary, category="hypothesis", value="total_cost", color="review_required", title="Hypothesis-level resource plan", interpretation="Compares total planned cost and unresolved design reviews.", method="Hypothesis-level plan aggregation"),
            _bar(_top(result, "priority_score"), x="experiment_id", y="priority_score", color="review_required", title="Experiment execution priority", interpretation="Ranks complete, adequately replicated and cost-efficient plans.", method="Human-review-gated experiment priority"),
            _bar(_top(schedule, "estimated_hours"), x="experiment_id", y="estimated_hours", color="review_required", title="Estimated laboratory schedule", interpretation="Shows relative execution time for the current plan queue.", method="Replicate-based bounded duration estimate"),
        ]
    return []

