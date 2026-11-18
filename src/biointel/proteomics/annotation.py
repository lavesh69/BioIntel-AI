from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from Bio.SeqUtils.ProtParam import ProteinAnalysis

HYDROPHOBIC = set("AILMFWVY")


@dataclass(frozen=True)
class ProteinAnnotation:
    length: int
    molecular_weight: float
    isoelectric_point: float
    signal_peptide_score: float
    transmembrane_helices: list[tuple[int, int, float]]
    disorder_regions: list[tuple[int, int, float]]
    phosphorylation_sites: dict[str, list[int]]
    glycosylation_sites: list[int]
    family_hints: list[str]
    localization_hints: list[str]
    warnings: list[str]


def _windows(sequence: str, size: int, score):
    return [
        (i, i + size, score(sequence[i : i + size])) for i in range(0, len(sequence) - size + 1)
    ]


def annotate_protein(sequence: str) -> ProteinAnnotation:
    seq = "".join(sequence.split()).upper()
    if not seq or any(aa not in "ACDEFGHIKLMNPQRSTVWY" for aa in seq):
        raise ValueError("Protein sequence contains unsupported symbols.")
    analysis = ProteinAnalysis(seq)
    signal_window = seq[:30]
    signal = 100 * sum(aa in HYDROPHOBIC for aa in signal_window) / max(len(signal_window), 1)
    tm = []
    for start, end, hydro in _windows(
        seq, 19, lambda w: sum(aa in HYDROPHOBIC for aa in w) / len(w)
    ):
        if hydro >= 0.68 and (not tm or start > tm[-1][1] + 5):
            tm.append((start + 1, end, round(hydro, 3)))
    disorder = []
    disorder_residues = set("PESTQKRG")
    for start, end, value in _windows(
        seq, 25, lambda w: sum(aa in disorder_residues for aa in w) / len(w)
    ):
        if value >= 0.6 and (not disorder or start > disorder[-1][1]):
            disorder.append((start + 1, end, round(value, 3)))
    phosphorylation = {
        "serine": [i + 1 for i, aa in enumerate(seq) if aa == "S"],
        "threonine": [i + 1 for i, aa in enumerate(seq) if aa == "T"],
        "tyrosine": [i + 1 for i, aa in enumerate(seq) if aa == "Y"],
    }
    glyco = [
        i + 1
        for i in range(len(seq) - 2)
        if seq[i] == "N" and seq[i + 1] != "P" and seq[i + 2] in "ST"
    ]
    families = []
    if all(motif in seq for motif in ("VAIK", "HRD", "DFG")):
        families.append("protein kinase-like motifs")
    if len(tm) >= 6:
        families.append("multi-pass membrane / GPCR-like topology")
    if re.search(r"HGG.H", seq):
        families.append("metalloprotease-like motif")
    if re.search(r"G.S.G", seq):
        families.append("serine hydrolase-like motif")
    localization = []
    if signal >= 60:
        localization.append("secretory pathway candidate")
    if len(tm):
        localization.append("membrane-associated candidate")
    if any(cluster in seq for cluster in ("KKKR", "KRKK", "RRRK")):
        localization.append("nuclear localization candidate")
    warnings = []
    if not families:
        warnings.append(
            "No high-confidence family motif was identified; use InterPro/Pfam for validated annotation."
        )
    return ProteinAnnotation(
        len(seq),
        round(analysis.molecular_weight(), 3),
        round(analysis.isoelectric_point(), 3),
        round(signal, 2),
        tm,
        disorder,
        phosphorylation,
        glyco,
        families,
        localization,
        warnings,
    )


def annotation_dict(result):
    return asdict(result)
