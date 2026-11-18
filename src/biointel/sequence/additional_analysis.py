from __future__ import annotations

from collections import Counter

from Bio.SeqUtils import MeltingTemp, gc_fraction, molecular_weight


def kmer_frequency(
    sequence: str,
    k: int = 3,
    top_n: int | None = None,
) -> list[dict[str, float | int | str]]:
    """Count overlapping k-mers with normalized frequencies."""

    cleaned = sequence.upper()
    if not 1 <= k <= 10:
        raise ValueError("k must be between 1 and 10.")
    if len(cleaned) < k:
        return []

    counts = Counter(cleaned[index : index + k] for index in range(len(cleaned) - k + 1))
    total = sum(counts.values())
    rows = [
        {
            "kmer": kmer,
            "count": count,
            "frequency": count / total,
        }
        for kmer, count in counts.most_common()
    ]
    if top_n is not None:
        return rows[: max(1, top_n)]
    return rows


def dna_oligo_properties(
    sequence: str,
    sodium_millimolar: float = 50.0,
    strand_concentration_nanormolar: float = 250.0,
) -> dict[str, float | int | str | None]:
    """Estimate basic DNA-oligo properties for short canonical sequences."""

    cleaned = sequence.upper()
    if not cleaned:
        raise ValueError("DNA oligo sequence is empty.")
    invalid = sorted(set(cleaned) - set("ACGT"))
    if invalid:
        raise ValueError("Oligo calculations require canonical A/C/G/T only.")
    if len(cleaned) > 500:
        raise ValueError("Oligo calculations are limited to 500 nucleotides.")
    if sodium_millimolar <= 0:
        raise ValueError("Sodium concentration must be positive.")
    if strand_concentration_nanormolar <= 0:
        raise ValueError("Strand concentration must be positive.")

    wallace = MeltingTemp.Tm_Wallace(cleaned)
    nearest_neighbor: float | None = None
    nearest_neighbor_warning: str | None = None
    if len(cleaned) >= 8:
        try:
            nearest_neighbor = MeltingTemp.Tm_NN(
                cleaned,
                Na=sodium_millimolar,
                dnac1=strand_concentration_nanormolar,
                dnac2=strand_concentration_nanormolar,
            )
        except (ValueError, KeyError) as exc:
            nearest_neighbor_warning = str(exc)
    else:
        nearest_neighbor_warning = (
            "Nearest-neighbor Tm is not reported for sequences shorter than 8 nt."
        )

    return {
        "length": len(cleaned),
        "gc_percent": gc_fraction(cleaned) * 100,
        "molecular_weight_single_stranded": molecular_weight(
            cleaned,
            seq_type="DNA",
            double_stranded=False,
        ),
        "tm_wallace_celsius": float(wallace),
        "tm_nearest_neighbor_celsius": (
            float(nearest_neighbor) if nearest_neighbor is not None else None
        ),
        "sodium_millimolar": float(sodium_millimolar),
        "strand_concentration_nanormolar": float(strand_concentration_nanormolar),
        "warning": nearest_neighbor_warning,
    }
