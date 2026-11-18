from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd

from biointel.synthetic import SyntheticGeneratedDataset

from .models import PlatformValidationError

ADAPTER_VERSION = "Step220.0"
ORIGIN_COLUMNS = {"data_origin", "is_synthetic"}


@dataclass(frozen=True)
class SyntheticAnalysisInput:
    module_id: str
    frame: pd.DataFrame
    parameters: Mapping[str, Any]
    source_tables: tuple[str, ...]
    adapter_version: str = ADAPTER_VERSION


def _table(generated: SyntheticGeneratedDataset, name: str) -> pd.DataFrame:
    table = generated.tables.get(name)
    if not isinstance(table, pd.DataFrame) or table.empty:
        raise PlatformValidationError(f"Synthetic source table is unavailable: {name}")
    return table.copy()


def _wide_to_long(
    frame: pd.DataFrame,
    *,
    id_columns: tuple[str, ...],
    feature_name: str,
    value_name: str,
) -> pd.DataFrame:
    feature_columns = [
        column
        for column in frame.columns
        if column not in set(id_columns).union(ORIGIN_COLUMNS)
        and pd.api.types.is_numeric_dtype(frame[column])
        and not pd.api.types.is_bool_dtype(frame[column])
    ]
    if not feature_columns:
        raise PlatformValidationError("Synthetic table contains no numeric feature columns")
    return frame.melt(
        id_vars=list(id_columns),
        value_vars=feature_columns,
        var_name=feature_name,
        value_name=value_name,
    )


def _sequencing(generated: SyntheticGeneratedDataset) -> tuple[pd.DataFrame, dict[str, Any], tuple[str, ...]]:
    frame = _table(generated, "sequencing_summary.csv")
    frame["reads"] = pd.to_numeric(frame["total_reads"], errors="coerce")
    frame["gc_percent"] = pd.to_numeric(frame["gc_fraction"], errors="coerce") * 100
    frame["duplication_percent"] = pd.to_numeric(frame["duplication_rate"], errors="coerce") * 100
    frame["adapter_percent"] = pd.to_numeric(frame["adapter_fraction"], errors="coerce") * 100
    frame["contamination_percent"] = frame["contamination_flag"].astype(bool).astype(float) * 100
    return frame, {}, ("sequencing_summary.csv",)


def _alignment(generated: SyntheticGeneratedDataset) -> tuple[pd.DataFrame, dict[str, Any], tuple[str, ...]]:
    frame = _table(generated, "alignment_summary.csv")
    mismatch = frame.get("reference_mismatch", pd.Series(False, index=frame.index)).astype(bool)
    frame["reference_build"] = np.where(mismatch, "SYN-REF-MISMATCH", "SYN-REF-1")
    frame["properly_paired"] = pd.to_numeric(frame["uniquely_mapped_reads"], errors="coerce")
    return frame, {"reference_build": "SYN-REF-1"}, ("alignment_summary.csv",)


def _differential(generated: SyntheticGeneratedDataset) -> tuple[pd.DataFrame, dict[str, Any], tuple[str, ...]]:
    values = _table(generated, "normalized_expression.csv")
    metadata = _table(generated, "sample_metadata.csv")
    long = _wide_to_long(
        values, id_columns=("sample_id",), feature_name="feature_id", value_name="value"
    )
    frame = long.merge(metadata[["sample_id", "group"]], on="sample_id", how="left")
    return frame, {"minimum_replicates": 3}, (
        "normalized_expression.csv", "sample_metadata.csv"
    )


def _biomarker(generated: SyntheticGeneratedDataset) -> tuple[pd.DataFrame, dict[str, Any], tuple[str, ...]]:
    frame = _table(generated, "biomarker_feature_matrix.csv").rename(
        columns={"outcome_class": "label"}
    )
    return frame, {"label_column": "label", "outer_folds": 3, "seed": generated.config.seed}, (
        "biomarker_feature_matrix.csv",
    )


def _variants(generated: SyntheticGeneratedDataset) -> tuple[pd.DataFrame, dict[str, Any], tuple[str, ...]]:
    frame = _table(generated, "synthetic_variants.csv")
    frame["cadd"] = pd.to_numeric(frame.get("pathogenicity_score"), errors="coerce") * 40
    frame["revel"] = pd.to_numeric(frame.get("conservation_score"), errors="coerce")
    frame["spliceai"] = pd.to_numeric(frame.get("splice_prediction"), errors="coerce")
    frame["phenotype_similarity"] = pd.to_numeric(frame.get("phenotype_match"), errors="coerce")
    frame["inheritance_match"] = frame.get(
        "segregation_status", pd.Series("", index=frame.index)
    ).astype(str).str.lower().isin({"consistent", "matched", "de_novo", "compound_heterozygous"})
    return frame, {}, ("synthetic_variants.csv",)


def _pathways(generated: SyntheticGeneratedDataset) -> tuple[pd.DataFrame, dict[str, Any], tuple[str, ...]]:
    background_table = _table(generated, "background_universe.csv")
    pathways = _table(generated, "synthetic_pathway_results.csv")
    background = background_table.loc[
        background_table["included_in_background"].astype(bool), "gene"
    ].astype(str).tolist()
    rows = []
    for _, pathway in pathways.iterrows():
        leading = {
            item.strip()
            for item in str(pathway.get("leading_edge_genes", "")).split(";")
            if item.strip()
        }
        for gene in background:
            rows.append(
                {
                    "pathway": str(pathway.get("pathway_name") or pathway.get("pathway_id")),
                    "gene": gene,
                    "selected": gene in leading,
                    "in_background": True,
                    "synthetic_expected_fdr": pathway.get("fdr"),
                }
            )
    return pd.DataFrame(rows), {}, (
        "background_universe.csv", "synthetic_pathway_results.csv"
    )


def _multi_omics(generated: SyntheticGeneratedDataset) -> tuple[pd.DataFrame, dict[str, Any], tuple[str, ...]]:
    names = (
        "transcriptomics.csv", "proteomics.csv", "metabolomics.csv", "epigenomics.csv"
    )
    frames = []
    for name in names:
        source = _table(generated, name)
        layer = name.removesuffix(".csv")
        long = _wide_to_long(
            source, id_columns=("sample_id",), feature_name="feature_id", value_name="value"
        )
        long["layer"] = layer
        frames.append(long)
    return pd.concat(frames, ignore_index=True), {
        "seed": generated.config.seed, "maximum_features_per_layer": 200
    }, names


def _single_cell(generated: SyntheticGeneratedDataset) -> tuple[pd.DataFrame, dict[str, Any], tuple[str, ...]]:
    source = _table(generated, "cell_by_gene_counts.csv")
    frame = _wide_to_long(
        source, id_columns=("cell_id",), feature_name="feature_id", value_name="value"
    )
    return frame, {"seed": generated.config.seed, "maximum_cells": 1000}, (
        "cell_by_gene_counts.csv",
    )


def _proteomics(generated: SyntheticGeneratedDataset) -> tuple[pd.DataFrame, dict[str, Any], tuple[str, ...]]:
    source = _table(generated, "protein_abundance.csv")
    frame = _wide_to_long(
        source,
        id_columns=("sample_id", "group"),
        feature_name="protein_id",
        value_name="intensity",
    )
    frame["peptide_q_value"] = 0.005
    frame["protein_q_value"] = 0.005
    return frame, {"minimum_replicates": 3}, ("protein_abundance.csv",)


def _metabolomics(generated: SyntheticGeneratedDataset) -> tuple[pd.DataFrame, dict[str, Any], tuple[str, ...]]:
    abundance = _table(generated, "metabolite_intensity_matrix.csv")
    run_order = _table(generated, "run_order_qc.csv")
    features = _table(generated, "metabolite_features.csv")
    long = _wide_to_long(
        abundance,
        id_columns=("sample_id", "group"),
        feature_name="feature_id",
        value_name="intensity",
    )
    long = long.merge(
        run_order[["sample_id", "batch_order", "pooled_qc"]], on="sample_id", how="left"
    )
    long["run_order"] = pd.to_numeric(long["batch_order"], errors="coerce")
    long["sample_type"] = np.where(long["pooled_qc"].astype(bool), "qc", "sample")
    blank = features[["feature_id", "blank_intensity"]].copy()
    blank["sample_id"] = [f"SYN-BLANK-{index + 1:04d}" for index in range(len(blank))]
    blank["sample_type"] = "blank"
    blank["run_order"] = 0
    blank["intensity"] = pd.to_numeric(blank["blank_intensity"], errors="coerce")
    frame = pd.concat(
        [
            long[["feature_id", "sample_id", "sample_type", "run_order", "intensity"]],
            blank[["feature_id", "sample_id", "sample_type", "run_order", "intensity"]],
        ],
        ignore_index=True,
    )
    return frame, {}, (
        "metabolite_intensity_matrix.csv", "run_order_qc.csv", "metabolite_features.csv"
    )


def _microbiome(generated: SyntheticGeneratedDataset) -> tuple[pd.DataFrame, dict[str, Any], tuple[str, ...]]:
    counts = _table(generated, "taxonomic_counts.csv")
    metadata = _table(generated, "sample_metadata.csv")
    long = _wide_to_long(
        counts, id_columns=("sample_id",), feature_name="taxon_id", value_name="count"
    )
    frame = long.merge(
        metadata[["sample_id", "group", "negative_control"]], on="sample_id", how="left"
    )
    frame["is_negative_control"] = frame["negative_control"].fillna(False).astype(bool)
    return frame, {}, ("taxonomic_counts.csv", "sample_metadata.csv")


def _structure(generated: SyntheticGeneratedDataset) -> tuple[pd.DataFrame, dict[str, Any], tuple[str, ...]]:
    frame = _table(generated, "structure_summary.csv").rename(
        columns={
            "residue_index": "residue_id",
            "predicted_confidence": "plddt",
            "pae_like_uncertainty": "pae",
            "structural_coverage": "domain_coverage",
        }
    )
    return frame, {}, ("structure_summary.csv",)


def _drug_target(generated: SyntheticGeneratedDataset) -> tuple[pd.DataFrame, dict[str, Any], tuple[str, ...]]:
    frame = _table(generated, "synthetic_target_evidence.csv")
    evidence = pd.to_numeric(frame.get("evidence_score"), errors="coerce").fillna(0)
    druggability = pd.to_numeric(frame.get("druggability_estimate"), errors="coerce").fillna(0)
    frame["genetic_evidence"] = pd.to_numeric(frame.get("genetic_support_score"), errors="coerce")
    frame["disease_evidence"] = evidence
    frame["druggability"] = druggability
    frame["expression_relevance"] = evidence
    frame["tractability"] = druggability
    frame["safety"] = 1 - frame.get("safety_flag", pd.Series(False, index=frame.index)).astype(bool).astype(float)
    frame["competitor_count"] = 0
    return frame, {}, ("synthetic_target_evidence.csv",)


def _experimental(generated: SyntheticGeneratedDataset) -> tuple[pd.DataFrame, dict[str, Any], tuple[str, ...]]:
    frame = _table(generated, "synthetic_study_design.csv")
    effect = pd.to_numeric(frame["effect_size"], errors="coerce").abs().median()
    power = pd.to_numeric(frame["power_target"], errors="coerce").median()
    parameters = {
        "effect_size": max(0.01, float(effect) if np.isfinite(effect) else 0.5),
        "power": min(0.999, max(0.001, float(power) if np.isfinite(power) else 0.8)),
        "groups": max(2, int(frame["group"].nunique())),
        "blocks": max(1, int(frame["batch"].nunique())),
    }
    return frame, parameters, ("synthetic_study_design.csv",)


def _statistics(generated: SyntheticGeneratedDataset) -> tuple[pd.DataFrame, dict[str, Any], tuple[str, ...]]:
    frame = _table(generated, "statistical_dataset.csv").rename(
        columns={"continuous_outcome": "value"}
    )
    return frame, {
        "analysis_type": "two_group",
        "seed": generated.config.seed,
        "bootstrap_iterations": 200,
    }, ("statistical_dataset.csv",)


def _literature(generated: SyntheticGeneratedDataset) -> tuple[pd.DataFrame, dict[str, Any], tuple[str, ...]]:
    frame = _table(generated, "synthetic_literature_corpus.csv").rename(
        columns={
            "synthetic_reference_id": "identifier",
            "finding_direction": "direction",
            "retracted_like_demo": "retraction_state",
        }
    )
    frame["pmid"] = ""
    frame["doi"] = ""
    return frame, {"search_strategy": {"source": "synthetic fixture"}}, (
        "synthetic_literature_corpus.csv",
    )


def _hypotheses(generated: SyntheticGeneratedDataset) -> tuple[pd.DataFrame, dict[str, Any], tuple[str, ...]]:
    source = _table(generated, "synthetic_hypotheses.csv")
    rows = []
    for _, item in source.iterrows():
        rows.append({"observation": item["supporting_evidence"], "direction": "support"})
        contradiction = str(item.get("contradictory_evidence", "")).strip()
        if contradiction and contradiction.lower() != "none":
            rows.append({"observation": contradiction, "direction": "oppose"})
    first = source.iloc[0]
    parameters = {
        "exposure": "Synthetic modeled exposure",
        "outcome": "Synthetic endpoint",
        "mechanism": str(first.get("candidate_mechanism", "")),
        "competing_explanations": source["competing_hypothesis"].astype(str).head(10).tolist(),
        "falsification_criteria": source["falsification_criteria"].astype(str).head(10).tolist(),
    }
    return pd.DataFrame(rows), parameters, ("synthetic_hypotheses.csv",)


def _laboratory(generated: SyntheticGeneratedDataset) -> tuple[pd.DataFrame, dict[str, Any], tuple[str, ...]]:
    frame = _table(generated, "synthetic_validation_records.csv").rename(
        columns={"validation_id": "result_id", "observed_signal": "observed_value"}
    )
    expected = pd.to_numeric(frame.get("expected_signal"), errors="coerce")
    tolerance = max(0.1, float(expected.abs().median()) * 0.5)
    center = float(expected.median()) if expected.notna().any() else 0.0
    return frame, {
        "assay": "Synthetic validation fixture",
        "acceptance_minimum": center - tolerance,
        "acceptance_maximum": center + tolerance,
    }, ("synthetic_validation_records.csv",)


ADAPTERS = {
    "sequencing_quality": _sequencing,
    "alignment_mapping": _alignment,
    "differential_expression": _differential,
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
    "experimental_design": _experimental,
    "statistical_analysis": _statistics,
    "literature_discovery": _literature,
    "hypothesis_generation": _hypotheses,
    "laboratory_validation": _laboratory,
}


def adapt_generated_dataset(generated: SyntheticGeneratedDataset) -> SyntheticAnalysisInput:
    if not generated.is_synthetic or generated.data_origin != "synthetic":
        raise PlatformValidationError("Only an origin-labelled synthetic dataset can be adapted")
    module_id = generated.config.module_id
    adapter = ADAPTERS.get(module_id)
    if adapter is None:
        raise PlatformValidationError(f"No synthetic analysis adapter exists for {module_id}")
    frame, parameters, source_tables = adapter(generated)
    if frame.empty:
        raise PlatformValidationError("Synthetic analysis adapter produced no rows")
    clean_parameters = dict(parameters)
    clean_parameters["synthetic_adapter"] = {
        "adapter_version": ADAPTER_VERSION,
        "module_id": module_id,
        "scenario": generated.config.scenario,
        "source_tables": list(source_tables),
    }
    return SyntheticAnalysisInput(
        module_id=module_id,
        frame=frame,
        parameters=clean_parameters,
        source_tables=source_tables,
    )


__all__ = [
    "ADAPTER_VERSION",
    "SyntheticAnalysisInput",
    "adapt_generated_dataset",
]
