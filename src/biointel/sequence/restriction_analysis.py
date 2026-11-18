from __future__ import annotations

from Bio.Restriction import AllEnzymes, RestrictionBatch
from Bio.Seq import Seq

COMMON_ENZYMES = (
    "EcoRI",
    "BamHI",
    "HindIII",
    "NotI",
    "XhoI",
    "PstI",
    "SalI",
    "SmaI",
    "KpnI",
    "NcoI",
    "NdeI",
    "BglII",
)


def analyze_restriction_sites(
    sequence: str,
    enzyme_names: list[str] | tuple[str, ...] = COMMON_ENZYMES,
) -> list[dict[str, object]]:
    """Return one-based cut positions for selected restriction enzymes."""

    if not sequence:
        return []

    enzyme_map = {enzyme.__name__: enzyme for enzyme in AllEnzymes}
    unknown = sorted(set(enzyme_names) - set(enzyme_map))
    if unknown:
        raise ValueError("Unknown restriction enzymes: " + ", ".join(unknown))

    batch = RestrictionBatch([enzyme_map[name] for name in enzyme_names])
    analysis = batch.search(Seq(sequence.upper()), linear=True)
    rows: list[dict[str, object]] = []

    for enzyme in sorted(batch, key=lambda item: item.__name__):
        positions = [int(value) for value in analysis.get(enzyme, [])]
        count = len(positions)
        if count == 0:
            classification = "zero-cutter"
        elif count == 1:
            classification = "single-cutter"
        else:
            classification = "multi-cutter"

        rows.append(
            {
                "enzyme": enzyme.__name__,
                "recognition_site": str(enzyme.site),
                "cut_count": count,
                "cut_positions": ", ".join(map(str, positions)),
                "classification": classification,
            }
        )
    return rows
