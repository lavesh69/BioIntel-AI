from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass

from Bio.Data import CodonTable

HOST_PREFERENCES = {
    "ecoli": {
        "A": "GCG",
        "R": "CGT",
        "N": "AAC",
        "D": "GAT",
        "C": "TGC",
        "Q": "CAG",
        "E": "GAA",
        "G": "GGC",
        "H": "CAT",
        "I": "ATT",
        "L": "CTG",
        "K": "AAA",
        "M": "ATG",
        "F": "TTT",
        "P": "CCG",
        "S": "TCT",
        "T": "ACC",
        "W": "TGG",
        "Y": "TAT",
        "V": "GTG",
        "*": "TAA",
    },
    "human": {
        "A": "GCC",
        "R": "CGC",
        "N": "AAC",
        "D": "GAC",
        "C": "TGC",
        "Q": "CAG",
        "E": "GAG",
        "G": "GGC",
        "H": "CAC",
        "I": "ATC",
        "L": "CTG",
        "K": "AAG",
        "M": "ATG",
        "F": "TTC",
        "P": "CCC",
        "S": "AGC",
        "T": "ACC",
        "W": "TGG",
        "Y": "TAC",
        "V": "GTG",
        "*": "TGA",
    },
    "yeast": {
        "A": "GCT",
        "R": "AGA",
        "N": "AAT",
        "D": "GAT",
        "C": "TGT",
        "Q": "CAA",
        "E": "GAA",
        "G": "GGT",
        "H": "CAT",
        "I": "ATT",
        "L": "TTG",
        "K": "AAA",
        "M": "ATG",
        "F": "TTT",
        "P": "CCA",
        "S": "TCT",
        "T": "ACT",
        "W": "TGG",
        "Y": "TAT",
        "V": "GTT",
        "*": "TAA",
    },
}


@dataclass(frozen=True)
class CodonOptimizationResult:
    host: str
    protein_sequence: str
    optimized_dna: str
    gc_percent: float
    codon_count: int
    removed_sites: list[str]


def optimize_protein(
    protein_sequence: str, *, host: str = "ecoli", avoid_sites: list[str] | None = None
) -> CodonOptimizationResult:
    protein = "".join(protein_sequence.split()).upper()
    prefs = HOST_PREFERENCES.get(host.lower())
    if prefs is None:
        raise ValueError("Host must be ecoli, human or yeast.")
    if not protein or any(aa not in prefs for aa in protein):
        raise ValueError("Protein sequence contains unsupported symbols.")
    dna = "".join(prefs[aa] for aa in protein)
    removed = []
    alternatives = {
        aa: [
            codon
            for codon, translated in CodonTable.unambiguous_dna_by_name[
                "Standard"
            ].forward_table.items()
            if translated == aa
        ]
        for aa in set(protein) - {"*"}
    }
    for site in avoid_sites or []:
        site = site.upper()
        while site and site in dna:
            index = dna.index(site)
            codon_index = min(len(protein) - 1, index // 3)
            aa = protein[codon_index]
            choices = [
                c
                for c in alternatives.get(aa, [])
                if c != dna[codon_index * 3 : codon_index * 3 + 3]
            ]
            if not choices:
                break
            dna = dna[: codon_index * 3] + choices[0] + dna[codon_index * 3 + 3 :]
            removed.append(site)
    gc = 100 * (dna.count("G") + dna.count("C")) / len(dna)
    return CodonOptimizationResult(host.lower(), protein, dna, round(gc, 2), len(protein), removed)


def codon_usage(dna_sequence: str) -> dict[str, int]:
    dna = "".join(dna_sequence.split()).upper().replace("U", "T")
    if len(dna) % 3:
        raise ValueError("Coding sequence length must be divisible by three.")
    return dict(Counter(dna[i : i + 3] for i in range(0, len(dna), 3)))


def result_dict(result):
    return asdict(result)
