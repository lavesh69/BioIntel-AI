from __future__ import annotations

from collections import Counter
from io import StringIO

from Bio import Phylo
from Bio.Phylo.TreeConstruction import DistanceMatrix, DistanceTreeConstructor


def validate_alignment(sequences: dict[str, str]) -> dict[str, str]:
    cleaned = {str(name): "".join(str(seq).split()).upper() for name, seq in sequences.items()}
    if len(cleaned) < 2:
        raise ValueError("At least two aligned sequences are required.")
    lengths = {len(seq) for seq in cleaned.values()}
    if len(lengths) != 1:
        raise ValueError(
            "All aligned sequences must have equal length. Use MAFFT first for unaligned sequences."
        )
    if not next(iter(lengths)):
        raise ValueError("Alignment is empty.")
    allowed = set("ACGTUN-?X") | set("ABCDEFGHIKLMNPQRSTVWY")
    if any(any(char not in allowed for char in seq) for seq in cleaned.values()):
        raise ValueError("Alignment contains unsupported symbols.")
    return cleaned

def _alignment_kind(rows: dict[str, str]) -> str:
    symbols = set().union(*(set(sequence) for sequence in rows.values())) - {"-", "?"}
    nucleotide_symbols = set("ACGTUNRYSWKMBDHVX")
    return "nucleotide" if symbols.issubset(nucleotide_symbols) else "protein"


def _ignored_symbols(kind: str) -> set[str]:
    return {"-", "?", "N", "X"} if kind == "nucleotide" else {"-", "?", "X"}


def consensus_sequence(sequences: dict[str, str], minimum_fraction: float = 0.5) -> str:
    rows = validate_alignment(sequences)
    kind = _alignment_kind(rows)
    ignored = _ignored_symbols(kind)
    ambiguity = "N" if kind == "nucleotide" else "X"
    output = []
    for column in zip(*rows.values()):
        counts = Counter(char for char in column if char not in ignored)
        informative = sum(counts.values())
        if not counts:
            output.append("-")
            continue
        char, count = counts.most_common(1)[0]
        output.append(char if count / max(informative, 1) >= minimum_fraction else ambiguity)
    return "".join(output)


def p_distance(left: str, right: str) -> float:
    kind = _alignment_kind({"left": left, "right": right})
    ignored = _ignored_symbols(kind)
    comparable = [(a, b) for a, b in zip(left, right) if a not in ignored and b not in ignored]
    if not comparable:
        return 1.0
    return sum(a != b for a, b in comparable) / len(comparable)


def distance_matrix(sequences: dict[str, str]) -> dict[str, dict[str, float]]:
    rows = validate_alignment(sequences)
    names = list(rows)
    return {a: {b: round(p_distance(rows[a], rows[b]), 6) for b in names} for a in names}


def upgma_newick(sequences: dict[str, str]) -> str:
    rows = validate_alignment(sequences)
    names = list(rows)
    lower = []
    for i, name in enumerate(names):
        lower.append([p_distance(rows[name], rows[names[j]]) for j in range(i + 1)])
    tree = DistanceTreeConstructor().upgma(DistanceMatrix(names, lower))
    handle = StringIO()
    Phylo.write(tree, handle, "newick")
    return handle.getvalue().strip()
