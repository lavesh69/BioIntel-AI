from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from .core import (
    GENERATOR_ID,
    GENERATOR_VERSION,
    MODULE_SPECS,
    SYNTHETIC_WATERMARK,
    SyntheticDatasetManifest,
    SyntheticGeneratedDataset,
    SyntheticGenerationCancelled,
    SyntheticGenerationConfig,
    SyntheticTruthRecord,
    SyntheticValidationResult,
    contains_forbidden_identifier,
    utc_now,
)

CancelCheck = Callable[[], bool] | None


def _cancelled(check: CancelCheck) -> None:
    if check is not None and check():
        raise SyntheticGenerationCancelled("Synthetic generation was cancelled.")


def _ids(prefix: str, count: int, width: int = 4) -> list[str]:
    return [f"{prefix}-{index + 1:0{width}d}" for index in range(count)]


def _groups(count: int, imbalance: float) -> np.ndarray:
    case_count = int(round(count * min(0.9, max(0.1, imbalance))))
    values = np.array(["synthetic_case"] * case_count + ["synthetic_control"] * (count - case_count), dtype=object)
    return values


def _origin(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    output["data_origin"] = "synthetic"
    output["is_synthetic"] = True
    return output


def _duplicates(frame: pd.DataFrame, rate: float, rng: np.random.Generator) -> pd.DataFrame:
    count = int(round(len(frame) * rate))
    if count <= 0 or frame.empty:
        return frame
    picked = rng.choice(frame.index.to_numpy(), count, replace=True)
    return pd.concat([frame, frame.loc[picked]], ignore_index=True)


def _truth(kind: str, entity: str, value: Any, tolerance: float | None = None) -> SyntheticTruthRecord:
    token = hashlib.sha256(f"{kind}|{entity}|{value}".encode()).hexdigest()[:12].upper()
    return SyntheticTruthRecord(f"SYN-TRUTH-{token}", kind, entity, value, tolerance)


def _recommendation(config: SyntheticGenerationConfig, action: str) -> dict[str, Any]:
    return {
        "title": f"Synthetic {MODULE_SPECS[config.module_id]['title']} recommendation",
        "expected_action": action,
        "scenario": config.scenario,
        "data_origin": "synthetic",
        "scientific_use": "Not permitted",
    }


def _sequencing(config: SyntheticGenerationConfig, rng: np.random.Generator, check: CancelCheck):
    samples, _ = config.dimensions
    positions = np.arange(1, 151)
    degradation = 18 if "degradation" in config.scenario else 0
    quality = 37 - degradation * (positions / 150) ** 4 + rng.normal(0, max(0.2, config.noise_level), 150)
    if "mixed_quality" in config.scenario:
        quality -= 5 * (positions / 150) ** 2
    adapter = 0.24 if "adapter" in config.scenario else 0.01
    duplication = 0.62 if "duplication" in config.scenario else 0.08 + config.duplicate_rate
    depth = 250_000 if "low_sequencing_depth" in config.scenario else 8_000_000
    gc_mean = 0.72 if "gc_bias" in config.scenario else 0.49
    contamination = "sample_contamination" in config.scenario
    summary = pd.DataFrame({
        "sample_id": _ids("SYN-SAMPLE", samples),
        "total_reads": np.maximum(1000, rng.normal(depth, depth * 0.08, samples).astype(int)),
        "mean_quality": rng.normal(float(quality.mean()), 1, samples),
        "adapter_fraction": np.clip(rng.normal(adapter, 0.015, samples), 0, 1),
        "gc_fraction": np.clip(rng.normal(gc_mean, 0.025, samples), 0, 1),
        "read_length_mean": rng.normal(150, 2, samples),
        "duplication_rate": np.clip(rng.normal(duplication, 0.03, samples), 0, 1),
        "n_content": np.clip(rng.normal(0.002, 0.001, samples), 0, 1),
        "overrepresented_sequence": ["SYN-ADAPTER-01" if adapter > 0.1 else "none"] * samples,
        "low_quality_tail": bool(degradation),
        "contamination_flag": contamination,
    })
    profile = pd.DataFrame({
        "position": positions,
        "mean_phred": quality,
        "p10_phred": quality - 4,
        "p90_phred": quality + 3,
        "adapter_content": np.clip(adapter * (positions / 150) ** 5, 0, 1),
        "n_content": np.clip(rng.normal(0.002, 0.001, 150), 0, 1),
    })
    issues = []
    if adapter > 0.1:
        issues.append({"issue": "adapter_contamination", "threshold": 0.05})
    if degradation:
        issues.append({"issue": "low_quality_tail", "threshold": 25})
    if duplication > 0.4:
        issues.append({"issue": "high_duplication", "threshold": 0.4})
    if contamination:
        issues.append({"issue": "sample_contamination"})
    truth = [_truth("mean_quality", "cohort", round(float(quality.mean()), 3), 2), _truth("adapter_fraction", "cohort", adapter, 0.03)]
    tables = {"sequencing_summary.csv": summary, "per_base_quality.csv": profile}
    return tables, truth, issues, [_recommendation(config, "Review synthetic QC warnings and trimming settings.")]


def _alignment(config: SyntheticGenerationConfig, rng: np.random.Generator, check: CancelCheck):
    samples, _ = config.dimensions
    total = rng.integers(1_000_000, 9_000_000, samples)
    mapped_rate, multi_rate, mismatch = 0.95, 0.04, 0.01
    strandness, annotation = "forward", "matched"
    if "wrong_reference" in config.scenario:
        mapped_rate, mismatch, annotation = 0.42, 0.19, "reference_mismatch"
    elif "poor_quality" in config.scenario:
        mapped_rate = 0.55
    elif "multimapping" in config.scenario:
        multi_rate = 0.48
    elif "strandness" in config.scenario:
        strandness = "incorrect"
    elif "index_missing" in config.scenario:
        mapped_rate = 0.0
    elif "low_coverage" in config.scenario:
        total = rng.integers(20_000, 80_000, samples)
    mapped = (total * np.clip(rng.normal(mapped_rate, 0.02, samples), 0, 1)).astype(int)
    multi = (mapped * np.clip(rng.normal(multi_rate, 0.01, samples), 0, 1)).astype(int)
    summary = pd.DataFrame({
        "sample_id": _ids("SYN-SAMPLE", samples), "total_reads": total,
        "mapped_reads": mapped, "uniquely_mapped_reads": np.maximum(0, mapped - multi),
        "multimapped_reads": multi, "mean_mapq": np.clip(rng.normal(48 if mapped_rate > 0.8 else 18, 4, samples), 0, 60),
        "duplicate_rate": np.clip(rng.normal(0.12, 0.03, samples), 0, 1),
        "insert_size_mean": rng.normal(330, 25, samples), "coverage": np.maximum(0, total / 200_000),
        "strandness": strandness, "junction_support": np.maximum(0, rng.normal(mapped_rate * 10000, 900, samples)).astype(int),
        "reference_mismatch": mismatch, "annotation_mismatch": annotation,
    })
    mapq = pd.DataFrame({"mapq": np.arange(61), "read_count": np.maximum(0, rng.normal(1000, 180, 61)).astype(int)})
    issues = [] if config.scenario == "good_mapping" else [{"issue": config.scenario}]
    truth = [_truth("mapping_rate", "cohort", mapped_rate, 0.05), _truth("multimapping_rate", "cohort", multi_rate, 0.04)]
    return {"alignment_summary.csv": summary, "mapq_distribution.csv": mapq}, truth, issues, [_recommendation(config, "Verify reference, index, strandness and coverage before interpretation.")]


def _differential_expression(config: SyntheticGenerationConfig, rng: np.random.Generator, check: CancelCheck):
    samples, features = config.dimensions
    sample_ids = _ids("SYN-SAMPLE", samples)
    groups = _groups(samples, config.class_imbalance)
    rng.shuffle(groups)
    batch = np.where(np.arange(samples) % 2, "SYN-BATCH-01", "SYN-BATCH-02").astype(object)
    if "confounding" in config.scenario:
        batch = np.where(groups == "synthetic_case", "SYN-BATCH-02", "SYN-BATCH-01")
    signal_count = 0 if "no_true" in config.scenario else max(1, int(features * max(0.02, config.signal_sparsity)))
    effect = 0.25 if "weak" in config.scenario else 2.2 if "strong_biological" in config.scenario else config.effect_size
    base = rng.gamma(2, 60, features)
    dispersion = rng.uniform(0.05, 0.35, features)
    counts = np.empty((samples, features), dtype=np.int64)
    for start in range(0, features, 500):
        _cancelled(check)
        stop = min(features, start + 500)
        means = np.tile(base[start:stop], (samples, 1))
        signal_mask = np.arange(start, stop) < signal_count
        means *= np.exp((groups == "synthetic_case")[:, None] * effect * signal_mask)
        if "batch_effect" in config.scenario or "confounding" in config.scenario:
            means *= np.exp((batch == "SYN-BATCH-02")[:, None] * max(0.8, config.batch_effect_strength))
        size = np.maximum(1, 1 / dispersion[start:stop])
        probability = np.maximum(0.01, size / (size + means))
        counts[:, start:stop] = rng.negative_binomial(size, probability)
    if "outlier" in config.scenario:
        counts[0, : max(1, signal_count)] *= 25
    genes = _ids("SYNG", features, 5)
    count_frame = pd.DataFrame(counts, columns=genes)
    count_frame.insert(0, "sample_id", sample_ids)
    normalized = pd.DataFrame(np.log2(counts + 1), columns=genes)
    normalized.insert(0, "sample_id", sample_ids)
    metadata = pd.DataFrame({
        "sample_id": sample_ids, "group": groups, "batch": batch,
        "synthetic_covariate": rng.normal(0, 1, samples),
        "subject_id": _ids("SYN-SUBJECT", samples),
    })
    observed_lfc = np.r_[np.full(signal_count, effect), np.zeros(features - signal_count)]
    observed_lfc += rng.normal(0, 0.18 + config.noise_level * 0.2, features)
    p_value = np.clip(np.exp(-np.abs(observed_lfc) * 5) * rng.uniform(0.4, 1, features), 1e-12, 1)
    fdr = np.minimum(1, p_value * features / np.arange(1, features + 1))
    results = pd.DataFrame({
        "gene": genes, "log2_fold_change": observed_lfc, "p_value": p_value,
        "fdr_bh": fdr, "dispersion": dispersion,
        "is_known_signal": np.arange(features) < signal_count,
        "truth_class": np.where(np.arange(features) < signal_count, "true_positive_candidate", "true_negative_candidate"),
    })
    issues = []
    if "low_sample" in config.scenario:
        issues.append({"issue": "low_sample_size", "observed_samples": samples})
    for token in ("batch_effect", "confounding", "outlier"):
        if token in config.scenario:
            issues.append({"issue": token})
    truth = [_truth("differential_gene", gene, True) for gene in genes[:signal_count]]
    truth.append(_truth("batch_effect", "SYN-BATCH-02", "present" if issues else "minimal"))
    tables = {
        "count_matrix.csv": count_frame,
        "normalized_expression.csv": normalized,
        "sample_metadata.csv": metadata,
        "differential_expression_results.csv": results,
    }
    return tables, truth, issues, [_recommendation(config, "Recover known synthetic genes while controlling FDR and batch effects.")]


def _biomarker(config: SyntheticGenerationConfig, rng: np.random.Generator, check: CancelCheck):
    samples, features = config.dimensions
    labels = (rng.random(samples) < config.class_imbalance).astype(int)
    known = max(2, min(12, int(features * max(0.02, config.signal_sparsity))))
    matrix = rng.normal(0, 1 + config.noise_level, (samples, features))
    matrix[:, :known] += labels[:, None] * config.effect_size
    leakage = "data_leakage" in config.scenario
    if leakage:
        matrix[:, known] = labels
    feature_ids = _ids("SYNBIO", features, 5)
    frame = pd.DataFrame(matrix, columns=feature_ids)
    frame.insert(0, "sample_id", _ids("SYN-SAMPLE", samples))
    frame["outcome_class"] = labels
    frame["synthetic_continuous_outcome"] = matrix[:, :known].mean(axis=1) + rng.normal(0, 0.2, samples)
    frame["split"] = np.where(np.arange(samples) % 5 == 0, "test", "train")
    if leakage:
        frame["SYN_LEAKAGE_LABEL_COPY"] = labels
    external = frame.sample(frac=1, random_state=config.seed).copy()
    external_noise = 0.8 if "weak_external" in config.scenario else 0.2
    external[feature_ids[:known]] += rng.normal(0, external_noise, (samples, known))
    internal_auc = 0.98 if leakage or "overfitting" in config.scenario else min(0.95, 0.65 + config.effect_size * 0.12)
    weak_external = "weak_external" in config.scenario or "unstable" in config.scenario
    external_auc = 0.57 if weak_external else max(0.55, internal_auc - 0.08)
    performance = pd.DataFrame([{
        "model": "SYN-MODEL-01", "internal_auc": internal_auc,
        "external_auc": external_auc,
        "calibration_slope": 0.55 if "poor_calibration" in config.scenario else 0.95,
        "nested_cv": True, "leakage_detected": leakage,
    }])
    issues = [{"issue": "data_leakage"}] if leakage else []
    if "class_imbalance" in config.scenario:
        issues.append({"issue": "class_imbalance"})
    truth = [_truth("predictive_feature", feature, True) for feature in feature_ids[:known]]
    truth.append(_truth("expected_auc_range", "external", [round(external_auc - 0.08, 2), round(external_auc + 0.08, 2)]))
    tables = {
        "biomarker_feature_matrix.csv": frame,
        "external_validation_set.csv": external,
        "model_performance.csv": performance,
    }
    return tables, truth, issues, [_recommendation(config, "Use nested validation, remove leakage and compare internal with external performance.")]


def _variants(config: SyntheticGenerationConfig, rng: np.random.Generator, check: CancelCheck):
    _, features = config.dimensions
    count = min(max(12, features), 1000)
    rows = []
    for index in range(count):
        _cancelled(check)
        high = index == 0
        common = index == 1 or ("common_benign" in config.scenario and index < 4)
        conflict = index == 2 or ("conflicting" in config.scenario and index < 5)
        quality = 8 if "low_quality" in config.scenario and high else float(rng.uniform(35, 99))
        rows.append({
            "variant_id": f"SYNVAR-{index + 1:06d}",
            "chromosome": f"SYNCHR-{index % 22 + 1:02d}",
            "position": 100000 + index * 37,
            "reference_allele": "A", "alternate_allele": ("C", "G", "T")[index % 3],
            "gene": f"SYNG-{index % max(5, count // 4) + 1:04d}",
            "transcript": f"SYNTRANSCRIPT-{index + 1:05d}",
            "consequence": "synthetic_missense_like" if high else "synthetic_intronic_like",
            "allele_frequency": 0.00001 if high else 0.25 if common else float(rng.uniform(0.001, 0.08)),
            "clinvar_like_status": "synthetic_conflicting" if conflict else "synthetic_pathogenic_like" if high else "synthetic_benign_like",
            "pathogenicity_score": 0.96 if high else float(rng.uniform(0.05, 0.65)),
            "conservation_score": 0.94 if high else float(rng.uniform(0.1, 0.8)),
            "splice_prediction": "synthetic_disruptive" if index == 3 else "synthetic_neutral",
            "phenotype_match": 0.92 if high and "missing_phenotype" not in config.scenario else np.nan,
            "phenotype_id": f"SYNPHENO-{index % 8 + 1:02d}",
            "inheritance_pattern": "synthetic_de_novo" if "de_novo" in config.scenario and high else "synthetic_recessive",
            "segregation_status": "synthetic_compound_het_pair" if "compound_heterozygous" in config.scenario and index < 2 else "synthetic_consistent",
            "call_quality": quality, "priority_score": 0.98 if high else float(rng.uniform(0.05, 0.75)),
        })
    issues = [] if config.scenario == "high_priority_research_variant" else [{"issue": config.scenario}]
    truth = [_truth("expected_top_variant", "rank_1", "SYNVAR-000001"), _truth("benign_like_variant", "SYNVAR-000002", True)]
    return {"synthetic_variants.csv": pd.DataFrame(rows)}, truth, issues, [_recommendation(config, "Rank synthetic variants while retaining conflict, phenotype and quality warnings.")]


def _pathways(config: SyntheticGenerationConfig, rng: np.random.Generator, check: CancelCheck):
    _, features = config.dimensions
    genes = _ids("SYNG", features, 5)
    signal_count = max(1, features // 10)
    ranked = pd.DataFrame({
        "gene": genes,
        "rank_statistic": np.r_[rng.normal(2.2, 0.3, signal_count), rng.normal(0, 0.5, features - signal_count)],
    })
    background = pd.DataFrame({"gene": genes, "included_in_background": True})
    terms = min(80, max(8, features // 4))
    rows = []
    for index in range(terms):
        coherent = "strong_coherent" in config.scenario and index < 5
        score = 2.8 - index * 0.04 if coherent else float(rng.normal(0.4, 0.5))
        if "no_significant" in config.scenario:
            score = float(rng.normal(0, 0.15))
        rows.append({
            "pathway_id": f"SYNPATH-{index + 1:04d}",
            "pathway_name": f"Synthetic pathway {index + 1:04d}",
            "enrichment_score": score, "normalized_enrichment_score": score / 1.5,
            "fdr": min(1, np.exp(-abs(score) * 2)),
            "direction": "up" if score >= 0 else "down",
            "leading_edge_genes": ";".join(genes[index:index + 5]),
            "database_origin": "synthetic_pathway_fixture",
            "redundancy_group": index // 3 if "redundant" in config.scenario else index,
        })
    if "incorrect_background" in config.scenario:
        background = background.iloc[: max(2, features // 5)].copy()
    issues = [] if config.scenario == "strong_coherent_signal" else [{"issue": config.scenario}]
    tables = {"ranked_genes.csv": ranked, "background_universe.csv": background, "synthetic_pathway_results.csv": pd.DataFrame(rows)}
    return tables, [_truth("expected_pathway", "rank_1", "SYNPATH-0001")], issues, [_recommendation(config, "Check synthetic pathway coherence, redundancy, direction and background sensitivity.")]


def _multi_omics(config: SyntheticGenerationConfig, rng: np.random.Generator, check: CancelCheck):
    samples, features = config.dimensions
    sample_ids = _ids("SYN-SAMPLE", samples)
    latent = rng.normal(0, 1, samples)
    layers: dict[str, pd.DataFrame] = {}
    per_layer = max(3, features // 4)
    for layer_index, layer in enumerate(("transcriptomics", "proteomics", "metabolomics", "epigenomics")):
        _cancelled(check)
        ids = sample_ids.copy()
        if "mismatched_sample" in config.scenario and layer_index == 2:
            ids = _ids("SYN-MISMATCH", samples)
        values = rng.normal(0, 1 + config.noise_level, (samples, per_layer))
        direction = -1 if "discordant" in config.scenario and layer_index == 2 else 1
        values[:, : min(5, per_layer)] += direction * latent[:, None] * config.effect_size
        if "layer_batch" in config.scenario and layer_index == 1:
            values[samples // 2:] += max(1, config.batch_effect_strength)
        frame = pd.DataFrame(values, columns=_ids(f"SYN-{layer.upper()}", per_layer, 5))
        frame.insert(0, "sample_id", ids)
        if "missing_layers" in config.scenario and layer_index == 3:
            continue
        layers[f"{layer}.csv"] = frame
    metadata = pd.DataFrame({
        "sample_id": sample_ids, "synthetic_phenotype": (latent > 0).astype(int),
        "latent_factor_truth": latent,
        "batch": np.where(np.arange(samples) < samples / 2, "SYN-BATCH-01", "SYN-BATCH-02"),
    })
    issues = [] if config.scenario in {"concordant_layers", "integrated_biomarker"} else [{"issue": config.scenario}]
    truth = [_truth("latent_factor", sid, round(float(value), 6), 0.2) for sid, value in zip(sample_ids[:10], latent[:10])]
    return {**layers, "phenotype_metadata.csv": metadata}, truth, issues, [_recommendation(config, "Recover the synthetic latent factor and report discordance or sample mismatch.")]


def _single_cell(config: SyntheticGenerationConfig, rng: np.random.Generator, check: CancelCheck):
    samples, features = config.dimensions
    cells = min(5000, max(80, samples * 10))
    genes = ["SYN-MT-001", "SYN-MT-002"] + _ids("SYNG", max(0, features - 2), 5)
    types = np.array(["SYN-TYPE-A", "SYN-TYPE-B", "SYN-RARE-TYPE"], dtype=object)
    probabilities = [0.49, 0.49, 0.02] if "rare_cell" in config.scenario else [0.5, 0.5, 0]
    assigned = rng.choice(types, cells, p=probabilities)
    counts = np.empty((cells, features), dtype=np.int32)
    for start in range(0, features, 500):
        _cancelled(check)
        stop = min(features, start + 500)
        counts[:, start:stop] = rng.poisson(0.35, (cells, stop - start))
    marker_count = min(5, features)
    mask_a = assigned == "SYN-TYPE-A"
    counts[mask_a, :marker_count] += rng.poisson(3, (mask_a.sum(), marker_count))
    if features > marker_count:
        mask_b = assigned == "SYN-TYPE-B"
        stop = min(features, marker_count * 2)
        counts[mask_b, marker_count:stop] += rng.poisson(3, (mask_b.sum(), stop - marker_count))
    doublet_rate = 0.28 if "doublet_heavy" in config.scenario else 0.03
    ambient = 0.45 if "ambient_rna" in config.scenario else 0.05
    doublets = rng.random(cells) < doublet_rate
    counts[doublets] *= 2
    if "batch_shifted" in config.scenario:
        counts[cells // 2:] += rng.poisson(1, (cells - cells // 2, features))
    count_frame = pd.DataFrame(counts, columns=genes)
    cell_ids = _ids("SYN-CELL", cells, 6)
    count_frame.insert(0, "cell_id", cell_ids)
    library = counts.sum(axis=1)
    mito = counts[:, : min(2, features)].sum(axis=1) / np.maximum(1, library) * 100
    metadata = pd.DataFrame({
        "cell_id": cell_ids,
        "sample_id": [f"SYN-SAMPLE-{index % samples + 1:04d}" for index in range(cells)],
        "cell_type": assigned,
        "cluster": np.where(assigned == "SYN-TYPE-A", "SYN-CLUSTER-01", "SYN-CLUSTER-02"),
        "doublet_score": np.where(doublets, rng.uniform(0.75, 0.99, cells), rng.uniform(0, 0.25, cells)),
        "ambient_rna_fraction": np.clip(rng.normal(ambient, 0.03, cells), 0, 1),
        "pct_mito": mito, "library_size": library,
        "batch": np.where(np.arange(cells) < cells / 2, "SYN-BATCH-01", "SYN-BATCH-02"),
        "trajectory_state": np.linspace(0, 1, cells) + rng.normal(0, 0.05, cells),
    })
    sample_metadata = pd.DataFrame({
        "sample_id": _ids("SYN-SAMPLE", samples), "group": _groups(samples, 0.5),
        "batch": np.where(np.arange(samples) < samples / 2, "SYN-BATCH-01", "SYN-BATCH-02"),
    })
    issues = [] if config.scenario == "clean_annotated_dataset" else [{"issue": config.scenario}]
    truth = [_truth("cell_type", cell, str(kind)) for cell, kind in zip(cell_ids[:100], assigned[:100])]
    tables = {"cell_by_gene_counts.csv": count_frame, "cell_metadata.csv": metadata, "sample_metadata.csv": sample_metadata}
    return tables, truth, issues, [_recommendation(config, "Recover synthetic cell types and detect doublets, ambient RNA, batches and rare populations.")]


def _proteomics(config: SyntheticGenerationConfig, rng: np.random.Generator, check: CancelCheck):
    samples, features = config.dimensions
    proteins = _ids("SYNPROT", features, 5)
    groups = _groups(samples, 0.5)
    abundance = np.empty((samples, features), dtype=float)
    for start in range(0, features, 500):
        _cancelled(check)
        stop = min(features, start + 500)
        abundance[:, start:stop] = rng.normal(20, 1.5, (samples, stop - start))
    differential = max(1, features // 12)
    abundance[groups == "synthetic_case", :differential] += config.effect_size
    if "batch_drift" in config.scenario:
        abundance += np.linspace(0, 2.5, samples)[:, None]
    missing_rate = 0.35 if "missingness" in config.scenario else config.missing_data_rate
    missing = rng.random(abundance.shape) < missing_rate
    if "mnar" in config.scenario:
        missing |= abundance < np.quantile(abundance, 0.15)
    abundance[missing] = np.nan
    matrix = pd.DataFrame(abundance, columns=proteins)
    matrix.insert(0, "sample_id", _ids("SYN-SAMPLE", samples))
    matrix["group"] = groups
    peptide_count = min(features * 3, 15000)
    peptides = pd.DataFrame({
        "peptide_id": _ids("SYNPEP", peptide_count, 6),
        "protein_group": [proteins[index % features] for index in range(peptide_count)],
        "unique_peptide": np.arange(peptide_count) % 5 != 0,
        "peptide_confidence": np.clip(rng.normal(0.55 if "low_peptide" in config.scenario else 0.95, 0.08, peptide_count), 0, 1),
        "ptm_like": np.where(np.arange(peptide_count) % 13 == 0, "SYN-PTM-LIKE", "none"),
    })
    qc = pd.DataFrame({
        "sample_id": _ids("SYN-SAMPLE", samples),
        "instrument_qc_score": np.clip(rng.normal(0.95, 0.04, samples), 0, 1),
        "technical_replicate": np.arange(samples) % 2,
        "batch": np.where(np.arange(samples) < samples / 2, "SYN-BATCH-01", "SYN-BATCH-02"),
        "run_status": "failed" if "failed_instrument" in config.scenario else "synthetic_pass",
    })
    clean = {"clean_proteomics", "differential_protein_signal", "high_peptide_confidence"}
    issues = [] if config.scenario in clean else [{"issue": config.scenario}]
    truth = [_truth("differential_protein", protein, True) for protein in proteins[:differential]]
    tables = {"protein_abundance.csv": matrix, "peptide_records.csv": peptides, "instrument_qc.csv": qc}
    return tables, truth, issues, [_recommendation(config, "Recover differential synthetic proteins while respecting missingness and peptide ambiguity.")]


def _metabolomics(config: SyntheticGenerationConfig, rng: np.random.Generator, check: CancelCheck):
    samples, features = config.dimensions
    feature_ids = _ids("SYNMET", features, 5)
    groups = _groups(samples, 0.5)
    intensity = np.empty((samples, features), dtype=float)
    for start in range(0, features, 500):
        _cancelled(check)
        stop = min(features, start + 500)
        intensity[:, start:stop] = rng.lognormal(10, 0.7, (samples, stop - start))
    differential = max(1, features // 15)
    intensity[groups == "synthetic_case", :differential] *= np.exp(config.effect_size)
    if "batch_drift" in config.scenario:
        intensity *= np.linspace(0.65, 1.35, samples)[:, None]
    matrix = pd.DataFrame(intensity, columns=feature_ids)
    matrix.insert(0, "sample_id", _ids("SYN-SAMPLE", samples))
    matrix["group"] = groups
    features_frame = pd.DataFrame({
        "feature_id": feature_ids, "mz": rng.uniform(70, 1200, features),
        "retention_time": rng.uniform(0.3, 25, features),
        "peak_quality": np.clip(rng.normal(0.4 if "poor_peak" in config.scenario else 0.9, 0.1, features), 0, 1),
        "blank_intensity": rng.lognormal(9 if "blank_contamination" in config.scenario else 5, 0.8, features),
        "pooled_qc_cv": np.clip(rng.normal(0.12, 0.04, features), 0, 1),
        "internal_standard": np.arange(features) % 50 == 0,
        "adduct_group": [f"SYN-ADDUCT-{index // 3 + 1:04d}" for index in range(features)],
        "isotope_group": [f"SYN-ISOTOPE-{index // 2 + 1:04d}" for index in range(features)],
        "compound_confidence": np.where(np.arange(features) % 5 == 0, "synthetic_level_2_like", "synthetic_unknown"),
    })
    run_order = pd.DataFrame({
        "sample_id": _ids("SYN-SAMPLE", samples), "batch_order": np.arange(1, samples + 1),
        "pooled_qc": np.arange(samples) % 10 == 0,
        "internal_standard_response": 0.1 if "internal_standard_failure" in config.scenario else np.clip(rng.normal(1, 0.06, samples), 0, None),
    })
    clean = {"clean_metabolomics", "strong_biological_signal"}
    issues = [] if config.scenario in clean else [{"issue": config.scenario}]
    truth = [_truth("differential_metabolite", feature, True) for feature in feature_ids[:differential]]
    tables = {"metabolite_intensity_matrix.csv": matrix, "metabolite_features.csv": features_frame, "run_order_qc.csv": run_order}
    return tables, truth, issues, [_recommendation(config, "Detect synthetic drift, blanks, standards and differential features without claiming compound identity.")]


def _microbiome(config: SyntheticGenerationConfig, rng: np.random.Generator, check: CancelCheck):
    samples, features = config.dimensions
    taxa = _ids("SYNTAXON", features, 5)
    sample_ids = _ids("SYN-SAMPLE", samples)
    groups = _groups(samples, 0.5)
    depth = 1500 if "insufficient_depth" in config.scenario else 30000
    proportions = np.empty((samples, features), dtype=float)
    counts = np.empty((samples, features), dtype=np.int64)
    for index in range(samples):
        _cancelled(check)
        proportions[index] = rng.dirichlet(np.ones(features) * 0.4)
        if "differential_abundance" in config.scenario and groups[index] == "synthetic_case":
            proportions[index, : min(4, features)] *= 5
            proportions[index] /= proportions[index].sum()
        sample_depth = max(100, int(rng.normal(depth, depth * 0.1)))
        counts[index] = rng.multinomial(sample_depth, proportions[index])
    negative_count = max(2, samples // 10)
    controls = rng.poisson(1, (negative_count, features))
    if "contamination" in config.scenario:
        controls[:, : min(3, features)] += 200
        counts[:, : min(3, features)] += 120
    count_frame = pd.DataFrame(counts, columns=taxa)
    count_frame.insert(0, "sample_id", sample_ids)
    relative = pd.DataFrame(counts / np.maximum(1, counts.sum(axis=1, keepdims=True)), columns=taxa)
    relative.insert(0, "sample_id", sample_ids)
    metadata = pd.DataFrame({
        "sample_id": sample_ids, "group": groups, "negative_control": False,
        "batch": np.where(np.arange(samples) < samples / 2, "SYN-BATCH-01", "SYN-BATCH-02"),
        "host_covariate": rng.normal(0, 1, samples), "low_biomass": counts.sum(axis=1) < 3000,
    })
    control_frame = pd.DataFrame(controls, columns=taxa)
    control_frame.insert(0, "sample_id", _ids("SYN-NEG-CONTROL", negative_count, 3))
    functional = pd.DataFrame({
        "sample_id": np.repeat(sample_ids, 4),
        "synthetic_pathway": np.tile(_ids("SYNPATH-MICRO", 4, 3), samples),
        "abundance": rng.lognormal(3, 0.6, samples * 4),
    })
    issues = [] if config.scenario == "clean_balanced_cohort" else [{"issue": config.scenario}]
    truth = [_truth("contaminant_taxon", taxa[0], "present" if "contamination" in config.scenario else "absent")]
    tables = {
        "taxonomic_counts.csv": count_frame, "relative_abundance.csv": relative,
        "sample_metadata.csv": metadata, "negative_controls.csv": control_frame,
        "functional_pathways.csv": functional,
    }
    return tables, truth, issues, [_recommendation(config, "Apply compositional methods and inspect synthetic controls and depth.")]


def _structure(config: SyntheticGenerationConfig, rng: np.random.Generator, check: CancelCheck):
    _, features = config.dimensions
    residues = min(max(80, features), 1500)
    index = np.arange(1, residues + 1)
    confidence = np.clip(rng.normal(86, 8, residues), 0, 100)
    if "low_confidence" in config.scenario:
        confidence[residues // 3:residues // 2] = rng.normal(35, 8, residues // 2 - residues // 3)
    uncertainty = np.clip(rng.normal(5, 2, residues), 0, 30)
    if "pae" in config.scenario:
        uncertainty += 15
    disorder = np.clip(rng.beta(2, 8, residues), 0, 1)
    if "disordered" in config.scenario:
        disorder[residues // 2:] = rng.uniform(0.7, 1, residues - residues // 2)
    coverage = 0.45 if "low_structural_coverage" in config.scenario else 0.94
    frame = pd.DataFrame({
        "structure_id": "SYNSTRUCT-001", "residue_index": index,
        "domain": [f"SYN-DOMAIN-{value // 100 + 1:02d}" for value in index],
        "predicted_confidence": confidence, "pae_like_uncertainty": uncertainty,
        "disorder_probability": disorder,
        "pocket_id": [f"SYNPOCKET-{value // 60 + 1:02d}" for value in index],
        "pocket_score": np.clip(rng.normal(0.65, 0.15, residues), 0, 1),
        "mutation_impact_estimate": np.clip(rng.normal(0.35, 0.2, residues), 0, 1),
        "docking_score_example": rng.normal(-6.5, 1, residues),
        "structural_coverage": coverage,
        "metric_notice": "Simulated metrics; not an experimental structure.",
    })
    issues = [] if config.scenario in {"high_confidence_model", "candidate_pocket"} else [{"issue": config.scenario}]
    truth = [_truth("mean_confidence", "SYNSTRUCT-001", round(float(confidence.mean()), 2), 3)]
    return {"structure_summary.csv": frame}, truth, issues, [_recommendation(config, "Interpret only simulated confidence, uncertainty, pockets and coverage.")]


def _drug_target(config: SyntheticGenerationConfig, rng: np.random.Generator, check: CancelCheck):
    _, features = config.dimensions
    count = min(max(12, features), 500)
    rows = []
    for index in range(count):
        essential = "essential_target" in config.scenario and index == 0
        off_target = 0.9 if "off_target" in config.scenario and index == 0 else float(rng.uniform(0.05, 0.45))
        druggability = 0.2 if "weak_druggability" in config.scenario and index == 0 else float(rng.uniform(0.4, 0.95))
        rows.append({
            "target_id": f"SYNTARGET-{index + 1:05d}",
            "genetic_support_score": 0.96 if "strong_genetic" in config.scenario and index == 0 else float(rng.uniform(0.1, 0.8)),
            "tissue_expression_pattern": f"SYN-TISSUE-PATTERN-{index % 6 + 1:02d}",
            "essentiality_value": 0.98 if essential else float(rng.uniform(0, 0.55)),
            "druggability_estimate": druggability,
            "ligand_like_record": f"SYNLIGAND-{index + 1:05d}",
            "safety_flag": "safety_flag" in config.scenario and index == 0,
            "off_target_risk": off_target,
            "validation_readiness": 0.15 if "validation_not_ready" in config.scenario else float(rng.uniform(0.45, 0.9)),
            "regulatory_status": "not_generated", "clinical_trial_status": "not_generated",
            "publication_claim": "not_generated", "evidence_origin": "demo_fixture",
            "evidence_score": float(rng.uniform(0.2, 0.9)),
        })
    issues = [] if config.scenario == "balanced_target_evidence" else [{"issue": config.scenario}]
    truth = [_truth("top_target", "rank_1", "SYNTARGET-00001")]
    return {"synthetic_target_evidence.csv": pd.DataFrame(rows)}, truth, issues, [_recommendation(config, "Review decomposed synthetic target evidence and safety limitations.")]


def _experimental_design(config: SyntheticGenerationConfig, rng: np.random.Generator, check: CancelCheck):
    samples, _ = config.dimensions
    groups = ["SYN-GROUP-CONTROL", "SYN-GROUP-TREATMENT"]
    powered = "underpowered" not in config.scenario
    replicates = max(2, samples // 2 if powered else 2)
    missing_control = "missing_control" in config.scenario
    rows = []
    active_groups = groups[1:] if missing_control else groups
    for group in active_groups:
        for replicate in range(replicates):
            rows.append({
                "study_id": "SYN-STUDY-0001",
                "hypothesis": "Synthetic treatment changes the simulated primary endpoint.",
                "primary_endpoint": "SYN-ENDPOINT-01", "group": group,
                "control_type": "none" if missing_control else "synthetic_vehicle_control",
                "biological_replicate": f"SYN-REPLICATE-{replicate + 1:03d}",
                "effect_size": config.effect_size, "variance": 1 + config.noise_level,
                "power_target": 0.8,
                "batch": "SYN-BATCH-02" if "batch_imbalanced" in config.scenario and group.endswith("TREATMENT") else "SYN-BATCH-01",
                "randomization_order": int(rng.integers(1, max(3, samples + 1))),
                "blinded_label": f"SYN-BLIND-{len(rows) + 1:04d}",
                "failure_condition": config.scenario if config.scenario != "well_powered_design" else "none",
            })
    issues = [] if config.scenario == "well_powered_design" else [{"issue": config.scenario}]
    expected = "adequate" if powered and not issues else "review_required"
    return {"synthetic_study_design.csv": pd.DataFrame(rows)}, [_truth("expected_power_status", "SYN-STUDY-0001", expected)], issues, [_recommendation(config, "Audit power, controls, replicates, randomization and batch balance.")]


def _statistics(config: SyntheticGenerationConfig, rng: np.random.Generator, check: CancelCheck):
    samples, _ = config.dimensions
    predictor = rng.normal(0, 1, samples)
    group = _groups(samples, 0.5)
    outcome = 0.7 * predictor + (group == "synthetic_case") * config.effect_size
    outcome += rng.normal(0, 1 + config.noise_level, samples)
    if "non_normality" in config.scenario:
        outcome = rng.lognormal(0, 1.1, samples)
    if "heteroscedasticity" in config.scenario:
        outcome += rng.normal(0, np.linspace(0.2, 3, samples))
    if "outliers" in config.scenario:
        outcome[: max(1, samples // 15)] += 12
    frame = pd.DataFrame({
        "sample_id": _ids("SYN-SAMPLE", samples), "group": group,
        "predictor_1": predictor,
        "predictor_2": predictor * 0.99 + rng.normal(0, 0.01 if "multicollinearity" in config.scenario else 0.8, samples),
        "continuous_outcome": outcome, "binary_outcome": (outcome > np.median(outcome)).astype(int),
        "time_to_event": rng.exponential(12, samples), "event": rng.integers(0, 2, samples),
        "subject_id": [f"SYN-SUBJECT-{index // 3 + 1:04d}" for index in range(samples)],
        "timepoint": np.arange(samples) % 3,
    })
    if "missingness" in config.scenario:
        for column in ("predictor_1", "continuous_outcome"):
            frame.loc[rng.random(samples) < 0.25, column] = np.nan
    assumptions = pd.DataFrame([{
        "scenario": config.scenario,
        "non_normality": "non_normality" in config.scenario,
        "heteroscedasticity": "heteroscedasticity" in config.scenario,
        "missingness": "missingness" in config.scenario,
        "outliers": "outliers" in config.scenario,
        "multicollinearity": "multicollinearity" in config.scenario,
        "separation": "separation" in config.scenario,
        "non_proportional_hazards": "non_proportional" in config.scenario,
    }])
    standard = {"two_group_clean", "paired_analysis", "multi_group_analysis", "repeated_measures", "linear_regression", "logistic_regression", "survival_analysis", "longitudinal_analysis", "mixed_effects", "non_parametric"}
    issues = [] if config.scenario in standard else [{"issue": config.scenario}]
    truth = [_truth("group_effect", "synthetic_case", config.effect_size, 0.3)]
    return {"statistical_dataset.csv": frame, "assumption_truth.csv": assumptions}, truth, issues, [_recommendation(config, "Select the statistical family and detect injected assumption violations.")]


def _literature(config: SyntheticGenerationConfig, rng: np.random.Generator, check: CancelCheck):
    _, features = config.dimensions
    count = min(max(20, features), 500)
    rows = []
    for index in range(count):
        contradiction = "contradictory" in config.scenario and index % 4 == 0
        duplicate = "SYN-PAPER-0001" if "duplicate" in config.scenario and index in {5, 6} else ""
        retracted = "retracted" in config.scenario and index == 3
        rows.append({
            "synthetic_reference_id": f"SYN-PAPER-{index + 1:04d}",
            "synthetic_doi_label": f"SYN-DOI-NOT-REAL-{index + 1:04d}",
            "title": f"Synthetic study record {index + 1:04d}: simulated mechanism evaluation",
            "study_type": "synthetic_review_like" if "review_like" in config.scenario and index % 5 == 0 else "synthetic_primary_like",
            "finding_direction": "contradictory" if contradiction else "supporting",
            "quality_score": float(rng.uniform(0.2, 0.55) if "low_quality" in config.scenario else rng.uniform(0.55, 0.95)),
            "duplicate_of": duplicate, "retracted_like_demo": retracted,
            "retraction_notice": "Synthetic retracted-like demo record" if retracted else "",
            "research_gap": "synthetic_independent_replication_missing" if index % 7 == 0 else "",
            "external_link": "disabled", "evidence_origin": "demo_fixture",
            "publication_claim": "not_permitted",
        })
    issues = [] if config.scenario in {"balanced_corpus", "supporting_studies"} else [{"issue": config.scenario}]
    supporting = sum(row["finding_direction"] == "supporting" for row in rows)
    return {"synthetic_literature_corpus.csv": pd.DataFrame(rows)}, [_truth("supporting_record_count", "corpus", supporting)], issues, [_recommendation(config, "Retain synthetic contradictions, duplicates, quality limits and research gaps.")]


def _hypotheses(config: SyntheticGenerationConfig, rng: np.random.Generator, check: CancelCheck):
    count = max(4, min(20, config.group_count * 3))
    rows = []
    for index in range(count):
        rows.append({
            "hypothesis_id": f"SYN-HYP-{index + 1:04d}",
            "hypothesis": f"Synthetic hypothesis generated from demo observations. Mechanism {index + 1} changes SYN-ENDPOINT-{index % 3 + 1:02d}.",
            "supporting_evidence": f"SYN-OBS-SUPPORT-{index + 1:04d}",
            "contradictory_evidence": f"SYN-OBS-CONTRADICT-{index + 1:04d}" if "contradictory" in config.scenario else "none",
            "candidate_mechanism": f"SYN-MECHANISM-{index + 1:03d}",
            "competing_hypothesis": f"SYN-COMPETING-{index + 1:03d}",
            "null_hypothesis": "No change in the same synthetic endpoint.",
            "falsification_criteria": "Synthetic endpoint effect remains below the prespecified tolerance.",
            "expected_outcome": config.effect_size,
            "experimental_option": "Synthetic controlled comparison; no assay design claim.",
            "testability_score": float(rng.uniform(0.55, 0.95)),
            "evidence_origin": "demo_fixture",
        })
    issues = [] if config.scenario == "testable_hypothesis" else [{"issue": config.scenario}]
    return {"synthetic_hypotheses.csv": pd.DataFrame(rows)}, [_truth("hypothesis_count", "workspace", count)], issues, [_recommendation(config, "Compare synthetic mechanisms using explicit null and falsification criteria.")]


def _laboratory(config: SyntheticGenerationConfig, rng: np.random.Generator, check: CancelCheck):
    assays = ("qPCR", "ELISA", "Western blot", "Flow cytometry", "CRISPR validation", "Targeted proteomics", "Targeted metabolomics")
    if "failed_validation" in config.scenario:
        status = "synthetic_demo_fail"
    elif "inconclusive" in config.scenario:
        status = "synthetic_demo_inconclusive"
    elif "control_failure" in config.scenario:
        status = "synthetic_control_failure"
    elif "insufficient_replicates" in config.scenario:
        status = "synthetic_insufficient_replicates"
    elif "dynamic_range" in config.scenario:
        status = "synthetic_dynamic_range_failure"
    else:
        status = "synthetic_demo_pass"
    rows = []
    for index, assay in enumerate(assays):
        rows.append({
            "validation_id": f"SYN-VAL-{index + 1:04d}", "assay": assay,
            "candidate_id": f"SYN-CANDIDATE-{index + 1:03d}", "result_status": status,
            "replicates": 1 if "insufficient_replicates" in config.scenario else 4,
            "positive_control": "failed" if "control_failure" in config.scenario else "synthetic_pass",
            "negative_control": "synthetic_pass",
            "dynamic_range_status": "failed" if "dynamic_range" in config.scenario else "synthetic_adequate",
            "expected_signal": config.positive_control_strength,
            "observed_signal": float(rng.normal(config.positive_control_strength, config.measurement_error)),
            "acceptance_criteria": "Synthetic fixture criterion only; not an assay claim.",
            "sequence_or_design": "not_generated", "evidence_origin": "demo_fixture",
            "scientific_validation": "not_permitted",
        })
    issues = [] if config.scenario == "passing_validation" else [{"issue": config.scenario}]
    return {"synthetic_validation_records.csv": pd.DataFrame(rows)}, [_truth("validation_status", "workspace", status)], issues, [_recommendation(config, "Exercise validation states without creating real assay claims.")]


_GENERATORS = {
    "sequencing_quality": _sequencing,
    "alignment_mapping": _alignment,
    "differential_expression": _differential_expression,
    "biomarker_discovery": _biomarker,
    "variant_prioritization": _variants,
    "pathway_enrichment": _pathways,
    "multi_omics": _multi_omics,
    "single_cell": _single_cell,
    "proteomics": _proteomics,
    "metabolomics": _metabolomics,
    "microbiome": _microbiome,
    "structural_biology": _structure,
    "drug_target_discovery": _drug_target,
    "experimental_design": _experimental_design,
    "statistical_analysis": _statistics,
    "literature_discovery": _literature,
    "hypothesis_generation": _hypotheses,
    "laboratory_validation": _laboratory,
}


class SyntheticDatasetGenerator:
    generator_id = GENERATOR_ID
    generator_version = GENERATOR_VERSION

    def generate(self, config: SyntheticGenerationConfig, *, cancel_check: CancelCheck = None) -> SyntheticGeneratedDataset:
        _cancelled(cancel_check)
        rng = np.random.default_rng(config.seed)
        tables, truth, issues, expected = _GENERATORS[config.module_id](config, rng, cancel_check)
        prepared = {name: _duplicates(_origin(pd.DataFrame(table)), config.duplicate_rate, rng) for name, table in tables.items()}
        self.validate_tables(prepared)
        samples, features = config.dimensions
        manifest = SyntheticDatasetManifest(
            generator_id=self.generator_id,
            generator_version=self.generator_version,
            module_id=config.module_id,
            seed=config.seed,
            scenario=config.scenario,
            sample_count=samples,
            feature_count=features,
            injected_signals=[record.to_dict() for record in truth][:200],
            injected_qc_issues=issues,
            expected_findings=[str(record.entity_id) for record in truth[:50]],
            expected_warnings=[str(item.get("issue", "synthetic_warning")) for item in issues],
            created_at=utc_now(),
            expected_behavior="Production recommendation logic should detect declared synthetic patterns and preserve origin restrictions.",
        )
        validations = [
            SyntheticValidationResult("SYN-CHECK-SCHEMA", "schema_and_origin", True, sorted(prepared), "origin-labelled tables", "All generated tables passed schema and origin validation."),
            SyntheticValidationResult("SYN-CHECK-TRUTH", "ground_truth_recorded", bool(truth), len(truth), ">0", "Ground truth is stored separately from researcher-facing tables."),
            SyntheticValidationResult("SYN-CHECK-SEED", "seed_recorded", True, config.seed, "integer", "The random seed is explicit."),
        ]
        tutorial = [
            SYNTHETIC_WATERMARK,
            "Inspect QC warnings, run production analysis and recommendations, then compare expected and observed behavior.",
            "Ground truth is hidden from normal researcher views and available only in Demo Mode developer/testing view.",
            "Reset the demo project before switching scenarios when a clean workspace is required.",
        ]
        return SyntheticGeneratedDataset(config, manifest, prepared, truth, issues, expected, tutorial, validations)

    @staticmethod
    def validate_tables(tables: dict[str, pd.DataFrame]) -> None:
        if not tables:
            raise ValueError("Synthetic generator produced no tables.")
        forbidden_columns = {"patient_name", "email", "phone", "address", "medical_record_number", "mrn"}
        for name, frame in tables.items():
            if frame.empty:
                raise ValueError(f"Synthetic table is empty: {name}")
            if "data_origin" not in frame or not frame["data_origin"].eq("synthetic").all():
                raise ValueError(f"Synthetic origin is missing from table: {name}")
            if "is_synthetic" not in frame or not frame["is_synthetic"].astype(bool).all():
                raise ValueError(f"Synthetic flag is missing from table: {name}")
            columns = {str(column).lower() for column in frame.columns}
            if forbidden_columns.intersection(columns):
                raise ValueError(f"Potential identifying column found in synthetic table: {name}")
            if contains_forbidden_identifier(frame.astype(str).head(100).to_csv(index=False)):
                raise ValueError(f"Valid-looking real-world identifier found in synthetic table: {name}")


def generate_synthetic_dataset(config: SyntheticGenerationConfig, *, cancel_check: CancelCheck = None) -> SyntheticGeneratedDataset:
    return SyntheticDatasetGenerator().generate(config, cancel_check=cancel_check)


__all__ = ["SyntheticDatasetGenerator", "generate_synthetic_dataset"]
