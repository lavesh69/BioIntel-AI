from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np
from Bio.SeqUtils.ProtParam import ProteinAnalysis

from biointel.utils.constants import PROTEIN_STANDARD
from biointel.utils.exceptions import InvalidSequenceError

AMINO_ACIDS = tuple("ACDEFGHIKLMNPQRSTVWY")
DIPEPTIDES = tuple("".join(pair) for pair in product(AMINO_ACIDS, repeat=2))
BASIC_FEATURE_NAMES = (
    "protein_length",
    "protein_molecular_weight",
    "protein_isoelectric_point",
    "protein_aromaticity",
    "protein_instability_index",
    "protein_gravy",
)


@dataclass(frozen=True)
class ProteinFeatureSet:
    """A fixed-order numeric representation of a protein sequence."""

    values: np.ndarray
    names: tuple[str, ...]
    sequence_length: int
    include_dipeptides: bool


def clean_protein_sequence(sequence: str) -> str:
    """Normalize and validate a protein sequence for model feature extraction."""

    cleaned = "".join(sequence.split()).upper()
    if not cleaned:
        raise InvalidSequenceError("Protein sequence is empty.")
    invalid = sorted(set(cleaned) - PROTEIN_STANDARD)
    if invalid:
        raise InvalidSequenceError(
            "DTI features require the 20 standard amino acids. Invalid/ambiguous symbols: "
            + ", ".join(invalid)
        )
    return cleaned


def amino_acid_composition(sequence: str) -> np.ndarray:
    """Return normalized frequencies for the 20 amino acids in a fixed order."""

    length = len(sequence)
    return np.array([sequence.count(aa) / length for aa in AMINO_ACIDS], dtype=float)


def dipeptide_composition(sequence: str) -> np.ndarray:
    """Return normalized frequencies for all 400 dipeptides in a fixed order."""

    denominator = max(len(sequence) - 1, 1)
    counts = {dipeptide: 0 for dipeptide in DIPEPTIDES}
    for index in range(len(sequence) - 1):
        counts[sequence[index : index + 2]] += 1
    return np.array([counts[item] / denominator for item in DIPEPTIDES], dtype=float)


def extract_protein_features(
    sequence: str,
    include_dipeptides: bool = False,
) -> ProteinFeatureSet:
    """Generate basic ProtParam, amino-acid and optional dipeptide features."""

    cleaned = clean_protein_sequence(sequence)
    analysis = ProteinAnalysis(cleaned)
    basic_values = np.array(
        [
            len(cleaned),
            analysis.molecular_weight(),
            analysis.isoelectric_point(),
            analysis.aromaticity(),
            analysis.instability_index(),
            analysis.gravy(),
        ],
        dtype=float,
    )
    aa_values = amino_acid_composition(cleaned)
    names = BASIC_FEATURE_NAMES + tuple(f"aa_comp_{aa}" for aa in AMINO_ACIDS)
    arrays = [basic_values, aa_values]

    if include_dipeptides:
        arrays.append(dipeptide_composition(cleaned))
        names += tuple(f"dipep_{pair}" for pair in DIPEPTIDES)

    values = np.concatenate(arrays)
    if not np.isfinite(values).all():
        raise ValueError("Protein feature extraction produced a non-finite value.")
    return ProteinFeatureSet(values, names, len(cleaned), include_dipeptides)
