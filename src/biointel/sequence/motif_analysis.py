from __future__ import annotations

import re

IUPAC_NUCLEOTIDE_REGEX = {
    "A": "A",
    "C": "C",
    "G": "G",
    "T": "T",
    "U": "U",
    "R": "[AG]",
    "Y": "[CTU]",
    "S": "[GC]",
    "W": "[ATU]",
    "K": "[GTU]",
    "M": "[AC]",
    "B": "[CGTU]",
    "D": "[AGTU]",
    "H": "[ACTU]",
    "V": "[ACG]",
    "N": "[ACGTU]",
}


def find_exact_motif(sequence: str, motif: str) -> list[dict[str, object]]:
    """Find overlapping exact motif occurrences using one-based coordinates."""

    seq = sequence.upper()
    target = motif.upper().strip()
    if not target:
        return []

    compiled = re.compile(f"(?=({re.escape(target)}))")
    rows: list[dict[str, object]] = []
    for match in compiled.finditer(seq):
        start = match.start(1)
        end = match.end(1)
        rows.append(
            {
                "match": len(rows) + 1,
                "start": start + 1,
                "end": end,
                "matched_sequence": match.group(1),
                "context": seq[max(0, start - 10) : min(len(seq), end + 10)],
            }
        )
        if len(rows) >= 1000:
            break
    return rows


def find_iupac_motif(sequence: str, motif: str) -> list[dict[str, object]]:
    """Find an IUPAC nucleotide motif, including overlapping matches."""

    target = motif.upper().strip()
    if not target:
        return []

    invalid = sorted(set(target) - set(IUPAC_NUCLEOTIDE_REGEX))
    if invalid:
        raise ValueError("Invalid IUPAC motif symbols: " + ", ".join(invalid))

    regex = "".join(IUPAC_NUCLEOTIDE_REGEX[symbol] for symbol in target)
    compiled = re.compile(f"(?=({regex}))", flags=re.IGNORECASE)
    rows: list[dict[str, object]] = []

    for match in compiled.finditer(sequence):
        start = match.start(1)
        end = match.end(1)
        rows.append(
            {
                "match": len(rows) + 1,
                "start": start + 1,
                "end": end,
                "matched_sequence": match.group(1),
                "context": sequence[max(0, start - 10) : min(len(sequence), end + 10)],
            }
        )
        if len(rows) >= 1000:
            break
    return rows


def _reject_risky_regex(pattern: str) -> None:
    """Reject common catastrophic-backtracking patterns before compilation."""

    if len(pattern) > 100:
        raise ValueError("Pattern is too long; maximum is 100 characters.")

    risky = [
        r"\([^)]*[+*][^)]*\)[+*{]",
        r"\.\*[+*{]",
        r"\.\+[+*{]",
    ]
    if any(re.search(check, pattern) for check in risky):
        raise ValueError("Pattern contains a potentially unsafe nested quantifier.")


def find_regex_motif(sequence: str, pattern: str) -> list[dict[str, object]]:
    """Run a bounded advanced regex search after basic ReDoS screening."""

    _reject_risky_regex(pattern)
    try:
        compiled = re.compile(pattern, flags=re.IGNORECASE)
    except re.error as exc:
        raise ValueError(f"Invalid regular expression: {exc}") from exc

    rows: list[dict[str, object]] = []
    for match in compiled.finditer(sequence):
        rows.append(
            {
                "match": len(rows) + 1,
                "start": match.start() + 1,
                "end": match.end(),
                "matched_sequence": match.group(0),
                "context": sequence[
                    max(0, match.start() - 10) : min(len(sequence), match.end() + 10)
                ],
            }
        )
        if len(rows) >= 1000:
            break
    return rows
