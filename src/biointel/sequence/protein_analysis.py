from __future__ import annotations

from collections import Counter

from Bio.SeqUtils.ProtParam import ProteinAnalysis

from biointel.utils.constants import AA_GROUPS, KYTE_DOOLITTLE, PROTEIN_STANDARD


def protein_statistics(sequence: str) -> dict[str, object]:
    seq = sequence.upper().replace("*", "")
    counts = Counter(seq)
    length = len(seq)
    ambiguous = sorted(set(seq) - PROTEIN_STANDARD)
    composition = {
        aa: {
            "count": counts.get(aa, 0),
            "percentage": counts.get(aa, 0) / length * 100 if length else 0.0,
        }
        for aa in sorted(PROTEIN_STANDARD)
    }
    grouped = {
        name: sum(counts.get(aa, 0) for aa in residues) / length * 100 if length else 0.0
        for name, residues in AA_GROUPS.items()
    }

    result: dict[str, object] = {
        "length": length,
        "composition": composition,
        "groups_percent": grouped,
        "ambiguous_residues": ambiguous,
        "warning": None,
    }
    if not seq:
        result["warning"] = "Protein sequence is empty after removing stop symbols."
        return result
    if ambiguous:
        result["warning"] = (
            "Physicochemical properties are disabled because ambiguous/special residues are present: "
            + ", ".join(ambiguous)
        )
        return result

    analysis = ProteinAnalysis(seq)
    helix, turn, sheet = analysis.secondary_structure_fraction()
    reduced, oxidized = analysis.molar_extinction_coefficient()
    result.update(
        {
            "molecular_weight": analysis.molecular_weight(),
            "isoelectric_point": analysis.isoelectric_point(),
            "aromaticity": analysis.aromaticity(),
            "instability_index": analysis.instability_index(),
            "gravy": analysis.gravy(),
            "secondary_structure": {"helix": helix, "turn": turn, "sheet": sheet},
            "positive_residues": counts.get("K", 0) + counts.get("R", 0) + counts.get("H", 0),
            "negative_residues": counts.get("D", 0) + counts.get("E", 0),
            "extinction_coefficient_reduced": reduced,
            "extinction_coefficient_oxidized": oxidized,
        }
    )
    return result


def hydropathy_profile(sequence: str, window: int = 9) -> list[dict[str, float]]:
    seq = sequence.upper().replace("*", "")
    if window < 1:
        raise ValueError("Window must be at least 1.")
    if len(seq) < window:
        window = len(seq)
    if not seq:
        return []
    rows = []
    for start in range(0, len(seq) - window + 1):
        chunk = seq[start : start + window]
        known = [KYTE_DOOLITTLE[aa] for aa in chunk if aa in KYTE_DOOLITTLE]
        value = sum(known) / len(known) if known else 0.0
        rows.append({"position": start + (window + 1) / 2, "hydropathy": value})
    return rows
