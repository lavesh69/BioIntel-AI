from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from biointel.utils.constants import DNA_IUPAC, PROTEIN_EXTENDED, RNA_IUPAC


class SequenceType(str, Enum):
    DNA = "DNA"
    RNA = "RNA"
    PROTEIN = "Protein"
    AMBIGUOUS = "Ambiguous"
    INVALID = "Invalid"


@dataclass(frozen=True)
class ValidationResult:
    detected_type: SequenceType
    invalid_symbols: tuple[tuple[int, str], ...]
    message: str


def invalid_positions(sequence: str, allowed: set[str]) -> tuple[tuple[int, str], ...]:
    return tuple((index + 1, char) for index, char in enumerate(sequence) if char not in allowed)


def detect_sequence_type(sequence: str) -> ValidationResult:
    """Detect DNA, RNA, protein, ambiguous, or invalid input."""
    chars = set(sequence.upper())
    universal = DNA_IUPAC | RNA_IUPAC | PROTEIN_EXTENDED
    invalid = invalid_positions(sequence.upper(), universal)
    if invalid:
        return ValidationResult(SequenceType.INVALID, invalid, "Unsupported symbols found.")

    is_dna = chars <= DNA_IUPAC and "U" not in chars
    is_rna = chars <= RNA_IUPAC and "T" not in chars
    is_protein = chars <= PROTEIN_EXTENDED

    if is_dna and is_protein:
        return ValidationResult(
            SequenceType.AMBIGUOUS,
            (),
            "Characters are valid for both nucleotide and protein alphabets; select the type manually.",
        )
    if is_rna and is_protein:
        return ValidationResult(
            SequenceType.AMBIGUOUS,
            (),
            "Characters are valid for both RNA and protein alphabets; select the type manually.",
        )
    if is_dna:
        return ValidationResult(SequenceType.DNA, (), "DNA sequence detected.")
    if is_rna:
        return ValidationResult(SequenceType.RNA, (), "RNA sequence detected.")
    if is_protein:
        return ValidationResult(SequenceType.PROTEIN, (), "Protein sequence detected.")
    return ValidationResult(SequenceType.INVALID, (), "Sequence could not be classified.")


def validate_for_type(sequence: str, sequence_type: SequenceType) -> tuple[tuple[int, str], ...]:
    allowed = {
        SequenceType.DNA: DNA_IUPAC,
        SequenceType.RNA: RNA_IUPAC,
        SequenceType.PROTEIN: PROTEIN_EXTENDED,
    }.get(sequence_type)
    if allowed is None:
        return ()
    return invalid_positions(sequence.upper(), allowed)
