from __future__ import annotations

import numpy as np
import pytest

from biointel.dti.feature_combiner import FeatureSchema
from biointel.sequence.additional_analysis import (
    dna_oligo_properties,
    kmer_frequency,
)
from biointel.training.explainability import (
    extract_global_feature_importance,
)
from biointel.training.model_artifact import (
    ARTIFACT_VERSION,
    ModelArtifact,
    ModelMetadata,
)


def test_kmer_frequency_counts_overlapping_windows() -> None:
    rows = kmer_frequency("AAAA", k=2)
    assert rows[0]["kmer"] == "AA"
    assert rows[0]["count"] == 3
    assert rows[0]["frequency"] == pytest.approx(1.0)


def test_dna_oligo_properties() -> None:
    result = dna_oligo_properties(
        "ATGCGTACGTAG",
        sodium_millimolar=50,
        strand_concentration_nanormolar=250,
    )
    assert result["length"] == 12
    assert result["molecular_weight_single_stranded"] > 0
    assert result["tm_wallace_celsius"] is not None
    assert result["tm_nearest_neighbor_celsius"] is not None


def test_dna_oligo_rejects_ambiguous_symbols() -> None:
    with pytest.raises(ValueError, match="canonical"):
        dna_oligo_properties("ATGCN")


class DummyEstimator:
    feature_importances_ = np.array([0.1, 0.7, 0.2])


def _artifact() -> ModelArtifact:
    metadata = ModelMetadata(
        artifact_version=ARTIFACT_VERSION,
        experiment_id="exp-importance",
        model_version="1.0.0",
        model_name="dummy",
        task_type="classification",
        trained_at_utc="2026-07-04T00:00:00+00:00",
        dataset_name="unit",
        dataset_version="1.0",
        dataset_sha256="b" * 64,
        split_strategy="random_pair",
        threshold_strategy="fixed",
        calibration_method="none",
        decision_threshold=0.5,
        positive_class_name="interaction_positive",
        activity_type=None,
        synthetic_demo=True,
        train_rows=10,
        validation_rows=4,
        test_rows=4,
        metrics={"accuracy": 0.5},
        validation_metrics={"accuracy": 0.5},
        confidence_intervals={},
        data_quality_summary={},
        training_config={},
        software_versions={"python": "3.11"},
    )
    schema = FeatureSchema(
        schema_version="2.0.0",
        feature_count=3,
        feature_hash="hash",
        fingerprint_radius=2,
        fingerprint_bits=3,
        use_chirality=True,
        include_dipeptides=False,
        drug_feature_count=3,
        protein_feature_count=0,
    )
    return ModelArtifact(
        estimator=DummyEstimator(),
        feature_schema=schema,
        feature_names=("a", "b", "c"),
        metadata=metadata,
        applicability_statistics={},
    )


def test_feature_importance_ranking() -> None:
    importance = extract_global_feature_importance(
        _artifact(),
        top_n=3,
    )
    assert importance.iloc[0]["feature"] == "b"
    assert importance.iloc[0]["rank"] == 1
    assert importance["importance"].sum() == pytest.approx(1.0)
