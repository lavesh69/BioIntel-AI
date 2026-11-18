from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from biointel.dti.activity import standardize_activity
from biointel.dti.dataset_validation import validate_dti_dataset
from biointel.sequence.alignment import align_sequences
from biointel.sequence.motif_analysis import (
    find_iupac_motif,
    find_regex_motif,
)
from biointel.sequence.parser import (
    parse_sequence_text,
    parse_sequences_text,
)
from biointel.sequence.restriction_analysis import (
    analyze_restriction_sites,
)
from biointel.training.evaluation import optimize_binary_threshold
from biointel.training.model_artifact import load_model_artifact
from biointel.training.scaffold import murcko_scaffold_smiles
from biointel.utils.exceptions import (
    InvalidSequenceError,
    ModelNotFoundError,
)


def test_multi_record_fasta_parser() -> None:
    records = parse_sequences_text(">one\nATG TAA\n>two\nMKWVTF")
    assert len(records) == 2
    assert records[0].header == "one"
    assert records[0].sequence == "ATGTAA"
    assert records[1].header == "two"


def test_single_parser_rejects_multi_record_fasta() -> None:
    with pytest.raises(InvalidSequenceError):
        parse_sequence_text(">one\nATG\n>two\nATG")


def test_iupac_motif_supports_overlapping_matches() -> None:
    matches = find_iupac_motif("AGAGA", "RGR")
    assert [(match["start"], match["end"]) for match in matches] == [(1, 3), (3, 5)]


def test_risky_regex_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsafe"):
        find_regex_motif("A" * 100, "(A+)+$")


def test_restriction_site_analysis() -> None:
    rows = analyze_restriction_sites("AAAAGAATTCTTTT", ["EcoRI"])
    assert rows[0]["enzyme"] == "EcoRI"
    assert rows[0]["cut_count"] == 1
    assert rows[0]["classification"] == "single-cutter"


def test_activity_standardization() -> None:
    result = standardize_activity("IC50", 1000, "nM")
    assert result.molar_value == pytest.approx(1e-6)
    assert result.p_activity == pytest.approx(6.0)


def test_dataset_quality_finds_duplicates_and_conflicts() -> None:
    dataframe = pd.DataFrame(
        {
            "canonical_smiles": ["CCO", "CCO", "CCO", "CCN"],
            "protein_sequence": ["ACDE", "ACDE", "ACDE", "ACDE"],
            "label": [1, 1, 0, 0],
        }
    )
    report = validate_dti_dataset(dataframe, "classification")
    assert report.duplicate_rows == 1
    assert report.conflicting_groups == 1
    assert report.valid_rows == 1


def test_scaffold_group_is_stable() -> None:
    first = murcko_scaffold_smiles("c1ccccc1O")
    second = murcko_scaffold_smiles("Oc1ccccc1")
    assert first == second
    assert first == "c1ccccc1"


def test_validation_threshold_optimization() -> None:
    y_true = np.array([0, 0, 1, 1])
    probabilities = np.array([0.05, 0.20, 0.45, 0.80])
    threshold, score = optimize_binary_threshold(y_true, probabilities, objective="f1")
    assert 0.20 < threshold <= 0.45
    assert score == pytest.approx(1.0)


def test_alignment_reports_substitutions_and_gap_columns() -> None:
    result = align_sequences(
        "ACGT",
        "AGT",
        sequence_type="DNA",
        mode="global",
    )
    assert result["identities"] == 3
    assert result["gap_columns"] == 1
    assert result["substitutions"] == 0
    assert result["query_coverage_percent"] == pytest.approx(75.0)
    assert result["target_coverage_percent"] == pytest.approx(100.0)


def test_trusted_model_root_rejects_outside_path(
    tmp_path: Path,
) -> None:
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    outside = tmp_path / "outside.joblib"
    outside.write_bytes(b"not a model")
    with pytest.raises(ModelNotFoundError, match="outside"):
        load_model_artifact(
            outside,
            trusted_root=trusted,
        )
