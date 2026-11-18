from __future__ import annotations

import math
from collections import Counter

from Bio.Seq import Seq


def sequence_entropy(sequence: str) -> float:
    if not sequence:
        return 0.0
    counts = Counter(sequence)
    length = len(sequence)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def nucleotide_statistics(sequence: str, is_rna: bool = False) -> dict[str, object]:
    seq = sequence.upper()
    bases = "AUGC" if is_rna else "ATGC"
    counts = {base: seq.count(base) for base in bases}
    length = len(seq)
    canonical = sum(counts.values())
    ambiguous = length - canonical
    g = counts.get("G", 0)
    c = counts.get("C", 0)
    a = counts.get("A", 0)
    t_or_u = counts.get("T", counts.get("U", 0))
    gc = (g + c) / canonical * 100 if canonical else 0.0
    at = (a + t_or_u) / canonical * 100 if canonical else 0.0
    return {
        "length": length,
        "counts": counts,
        "percentages": {k: (v / length * 100 if length else 0.0) for k, v in counts.items()},
        "ambiguous_count": ambiguous,
        "gc_percent": gc,
        "at_percent": at,
        "gc_at_ratio": ((g + c) / (a + t_or_u)) if (a + t_or_u) else None,
        "purine_percent": ((a + g) / canonical * 100) if canonical else 0.0,
        "pyrimidine_percent": ((c + t_or_u) / canonical * 100) if canonical else 0.0,
        "entropy_bits": sequence_entropy(seq),
    }


def dna_transformations(sequence: str) -> dict[str, str]:
    seq = Seq(sequence.upper())
    return {
        "complement": str(seq.complement()),
        "reverse": sequence.upper()[::-1],
        "reverse_complement": str(seq.reverse_complement()),
        "mrna": str(seq.transcribe()),
    }


def six_frame_translation(sequence: str, table: int = 1) -> list[dict[str, object]]:
    seq = Seq(sequence.upper())
    results: list[dict[str, object]] = []
    for strand, current in (("+", seq), ("-", seq.reverse_complement())):
        for offset in range(3):
            usable = len(current) - offset
            usable -= usable % 3
            fragment = current[offset : offset + usable]
            protein = str(fragment.translate(table=table, to_stop=False)) if fragment else ""
            results.append(
                {
                    "frame": f"{strand}{offset + 1}",
                    "nucleotide_length": len(fragment),
                    "protein": protein,
                    "protein_length": len(protein),
                }
            )
    return results


def codon_usage(sequence: str) -> list[dict[str, object]]:
    seq = sequence.upper()
    usable = len(seq) - (len(seq) % 3)
    codons = [seq[i : i + 3] for i in range(0, usable, 3)]
    counts = Counter(codons)
    total = len(codons)
    rows = []
    for codon, count in sorted(counts.items()):
        amino_acid = str(Seq(codon).translate()) if set(codon) <= set("ATGC") else "X"
        rows.append(
            {
                "codon": codon,
                "count": count,
                "frequency_percent": count / total * 100 if total else 0.0,
                "amino_acid": amino_acid,
            }
        )
    return rows


def sliding_gc(sequence: str, window: int) -> list[dict[str, float]]:
    if window < 1:
        raise ValueError("Window must be at least 1.")
    seq = sequence.upper()
    if len(seq) < window:
        window = len(seq)
    if not seq:
        return []
    rows = []
    for start in range(0, len(seq) - window + 1):
        chunk = seq[start : start + window]
        canonical = sum(chunk.count(x) for x in "ATGC")
        gc = (chunk.count("G") + chunk.count("C")) / canonical * 100 if canonical else 0.0
        rows.append({"position": start + 1, "gc_percent": gc})
    return rows


def cumulative_gc_skew(sequence: str) -> list[dict[str, float]]:
    """Return cumulative G-minus-C skew across sequence positions."""

    cumulative = 0.0
    rows: list[dict[str, float]] = []
    for index, base in enumerate(sequence.upper(), start=1):
        if base == "G":
            cumulative += 1.0
        elif base == "C":
            cumulative -= 1.0
        rows.append({"position": index, "cumulative_gc_skew": cumulative})
    return rows
