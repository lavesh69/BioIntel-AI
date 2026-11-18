from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from biointel.projects.cancer_genomics import validate_variant_table
from biointel.projects.comparative_genomics import (
    GenomeRecord,
    pairwise_variant_summary,
    pairwise_variant_table,
)
from biointel.projects.metagenomics_pipeline import (
    beta_dispersion,
    demo_metagenomics_data,
    permanova_screen,
    run_metagenomics_pipeline,
    sample_quality_flags,
)
from biointel.projects.ppi import (
    demo_ppi_pairs,
    load_ppi_model,
    pair_dataset_qc,
    score_candidate_pairs,
    serialize_ppi_model,
    train_and_score_ppi_classifier,
    validate_pair_table,
)
from biointel.projects.single_cell import demo_single_cell_counts, run_single_cell_pipeline


def test_ppi_selected_threshold_is_applied_and_model_is_reusable() -> None:
    training = demo_ppi_pairs(100)
    candidates = training.drop(columns=["label"]).head(12)
    result, scored = train_and_score_ppi_classifier(
        training,
        candidates,
        algorithm="Logistic regression",
        decision_threshold=0.8,
    )
    assert result.decision_threshold == 0.8
    assert (scored["predicted_label"] == (scored["interaction_probability"] >= 0.8).astype(int)).all()
    assert scored["model_fingerprint"].str.len().eq(64).all()

    loaded = load_ppi_model(serialize_ppi_model(result))
    rescored = score_candidate_pairs(loaded, candidates)
    assert np.allclose(scored["interaction_probability"], rescored["interaction_probability"])
    assert scored["predicted_label"].tolist() == rescored["predicted_label"].tolist()


def test_ppi_qc_sees_duplicates_and_training_rejects_conflicting_labels() -> None:
    pairs = demo_ppi_pairs(40)
    duplicate = pairs.iloc[[0]].copy()
    duplicated = pd.concat([pairs, duplicate], ignore_index=True)
    _, summary = pair_dataset_qc(duplicated)
    assert summary["duplicate_pairs"] == 1

    conflict = duplicate.copy()
    conflict["label"] = 1 - conflict["label"]
    conflicting = pd.concat([pairs, conflict], ignore_index=True)
    _, conflict_summary = pair_dataset_qc(conflicting)
    assert conflict_summary["conflicting_label_pairs"] == 1
    with pytest.raises(ValueError, match="Conflicting labels"):
        validate_pair_table(conflicting, require_label=True)


def test_cancer_mixed_vaf_units_are_normalized_per_row() -> None:
    frame = pd.DataFrame(
        {
            "chromosome": ["1", "1", "1"],
            "position": [100, 101, 102],
            "ref": ["A", "C", "G"],
            "alt": ["T", "G", "A"],
            "gene": ["TP53", "KRAS", "BRAF"],
            "consequence": ["missense_variant"] * 3,
            "vaf": [0.20, 20, 100],
            "depth": [100, 100, 100],
        }
    )
    cleaned = validate_variant_table(frame)
    assert np.allclose(cleaned["vaf"], [0.20, 0.20, 1.0])
    assert cleaned["vaf_input_unit"].tolist() == ["fraction", "percent", "percent"]


def test_comparative_variant_calling_handles_single_insertion_without_shift_avalanche() -> None:
    reference = GenomeRecord("ref", "ACGTACGTACGT")
    query = GenomeRecord("query", "ACGTTACGTACGT")
    variants = pairwise_variant_table(query, reference)
    summary = pairwise_variant_summary(query, reference)
    assert len(variants) == 1
    assert variants.iloc[0]["variant_type"] == "Insertion"
    assert summary["insertions"] == 1
    assert summary["substitutions"] == 0


def test_metagenomics_selected_pair_works_with_third_group_and_real_gate_keys() -> None:
    abundance, metadata = demo_metagenomics_data(taxa=40, samples_per_group=4)
    extra = metadata.iloc[:2].copy()
    extra["sample"] = ["OTHER_1", "OTHER_2"]
    extra["group"] = "Other"
    abundance["OTHER_1"] = abundance.iloc[:, 1]
    abundance["OTHER_2"] = abundance.iloc[:, 2]
    metadata = pd.concat([metadata, extra], ignore_index=True)

    result = run_metagenomics_pipeline(abundance, metadata, group_a="Control", group_b="Case")
    assert set(result.ordination["group"].dropna()) == {"Control", "Case"}
    assert result.summary["samples"] == 8
    flags = sample_quality_flags(result.qc)
    assert "qc_status" in flags
    permanova = permanova_screen(result.distance_matrix, metadata[metadata["group"].isin(["Control", "Case"])], permutations=49)
    assert "permutation_p_value" in permanova
    dispersion = beta_dispersion(result.distance_matrix, metadata[metadata["group"].isin(["Control", "Case"])])
    assert "distance_to_group_centroid" in dispersion


def test_single_cell_pipeline_can_exclude_doublets_and_reports_marker_statistics() -> None:
    counts = demo_single_cell_counts(genes=240, cells=84, clusters=3)
    result = run_single_cell_pipeline(
        counts,
        min_counts=10,
        min_genes=5,
        max_mito_percent=60,
        top_variable_genes=100,
        n_clusters=3,
        exclude_doublets=True,
    )
    assert {"doublet_score", "doublet_flag", "pass_qc"}.issubset(result.qc.columns)
    assert {"welch_p_value", "fdr_q_value"}.issubset(result.markers.columns)
    assert result.markers["fdr_q_value"].between(0, 1).all()
