from __future__ import annotations

from pathlib import Path

import pandas as pd

from biointel.training.active_learning import prioritize_active_learning
from biointel.training.group_calibration import fit_group_thresholds
from biointel.training.label_noise import detect_label_noise
from biointel.training.prospective_validation import ProspectiveValidationRegistry


def test_active_learning_prioritizes_uncertain_diverse_candidates() -> None:
    frame = pd.DataFrame(
        {
            "canonical_smiles": ["CCO", "CCN", "c1ccccc1", "CC(=O)O"],
            "positive_probability": [0.51, 0.49, 0.95, 0.10],
        }
    )
    selected = prioritize_active_learning(frame, batch_size=2)
    assert len(selected) == 2
    assert selected["selection_rank"].tolist() == [1, 2]
    assert selected["active_learning_score"].notna().all()
    assert set(selected["canonical_smiles"]).issubset(set(frame["canonical_smiles"]))


def test_label_noise_detects_duplicate_conflicts_and_model_disagreement() -> None:
    frame = pd.DataFrame(
        {
            "canonical_smiles": ["CCO", "CCO", "CCN"],
            "protein_sequence": ["ACDE", "ACDE", "ACDF"],
            "interaction_label": [1, 0, 1],
            "positive_probability": [0.95, 0.95, 0.02],
        }
    )
    flagged = detect_label_noise(frame)
    assert len(flagged) == 3
    assert flagged["duplicate_conflict"].sum() == 2
    assert flagged["model_disagreement"].sum() == 2


def test_group_specific_thresholds_include_fallback() -> None:
    rows = []
    for index in range(40):
        rows.append(
            {
                "family": "kinase",
                "interaction_label": index % 2,
                "positive_probability": 0.8 if index % 2 else 0.2,
            }
        )
    rows.extend(
        [
            {
                "family": "rare",
                "interaction_label": 1,
                "positive_probability": 0.7,
            }
            for _ in range(3)
        ]
    )
    thresholds = fit_group_thresholds(pd.DataFrame(rows), group_column="family")
    lookup = {item.group: item for item in thresholds}
    assert lookup["kinase"].fallback_used is False
    assert lookup["rare"].fallback_used is True


def test_prospective_registry_freezes_before_outcomes(tmp_path: Path) -> None:
    registry = ProspectiveValidationRegistry(tmp_path / "prospective.sqlite3")
    predictions = pd.DataFrame(
        {
            "sample_id": ["a", "b"],
            "prediction": [0.8, 0.2],
            "positive_probability": [0.8, 0.2],
        }
    )
    study = registry.freeze(
        name="Prospective test",
        model_filename="model.joblib",
        model_sha256="abc123",
        predictions=predictions,
    )
    assert study.status == "frozen"
    assert study.prediction_count == 2
    updated = registry.record_outcomes(
        study.study_id,
        pd.DataFrame({"sample_id": ["a", "b"], "observed_value": [1, 0]}),
    )
    assert updated.status == "outcomes_recorded"
    assert updated.outcome_count == 2
    joined = registry.joined_results(study.study_id)
    assert joined["observed_value"].tolist() == [1.0, 0.0]
