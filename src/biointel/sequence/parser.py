from __future__ import annotations

import re
from dataclasses import dataclass

from biointel.utils.exceptions import InvalidSequenceError


@dataclass(frozen=True)
class ParsedSequence:
    """One parsed biological sequence and its display header."""

    header: str
    sequence: str


def _clean_sequence_lines(lines: list[str]) -> str:
    """Clean copied sequence text while preserving biologically relevant symbols."""

    cleaned_lines: list[str] = []
    for line in lines:
        # Remove only common standalone position numbers at line boundaries.
        line = re.sub(r"^\s*\d+\s+", "", line)
        line = re.sub(r"\s+\d+\s*$", "", line)
        cleaned_lines.append(line)

    cleaned = re.sub(r"\s+", "", "".join(cleaned_lines)).upper()
    if not cleaned:
        raise InvalidSequenceError("No sequence characters were found.")
    return cleaned


def parse_sequences_text(text: str, max_records: int = 100) -> list[ParsedSequence]:
    """Parse raw sequence text or one/more FASTA records."""

    if not text or not text.strip():
        raise InvalidSequenceError("Sequence input is empty.")
    if max_records < 1:
        raise ValueError("max_records must be at least 1")

    lines = text.replace("\r", "").split("\n")
    has_header = any(line.lstrip().startswith(">") for line in lines if line.strip())
    if not has_header:
        return [ParsedSequence(header="sequence", sequence=_clean_sequence_lines(lines))]

    records: list[ParsedSequence] = []
    header: str | None = None
    sequence_lines: list[str] = []

    for line in lines:
        if line.lstrip().startswith(">"):
            if header is not None:
                records.append(ParsedSequence(header, _clean_sequence_lines(sequence_lines)))
                if len(records) >= max_records:
                    raise InvalidSequenceError(
                        f"FASTA contains more than the allowed {max_records} records."
                    )
            header = line.lstrip()[1:].strip() or f"sequence_{len(records) + 1}"
            sequence_lines = []
        elif header is None:
            if line.strip():
                raise InvalidSequenceError("Text before the first FASTA header is not supported.")
        else:
            sequence_lines.append(line)

    if header is None:
        raise InvalidSequenceError("No FASTA header was found.")

    records.append(ParsedSequence(header, _clean_sequence_lines(sequence_lines)))
    if len(records) > max_records:
        raise InvalidSequenceError(f"FASTA contains more than the allowed {max_records} records.")
    return records


def parse_sequence_text(text: str) -> ParsedSequence:
    """Parse exactly one raw or FASTA sequence record."""

    records = parse_sequences_text(text, max_records=2)
    if len(records) != 1:
        raise InvalidSequenceError(
            "Multiple FASTA records were found. Use batch mode or select one record."
        )
    return records[0]
