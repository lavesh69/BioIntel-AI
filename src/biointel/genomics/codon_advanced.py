from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass

from Bio.Data import CodonTable
from Bio.Seq import Seq

STANDARD_TABLE = CodonTable.unambiguous_dna_by_name["Standard"]
AA_CODONS: dict[str, list[str]] = {}
for codon, amino_acid in STANDARD_TABLE.forward_table.items():
    AA_CODONS.setdefault(amino_acid, []).append(codon)
AA_CODONS["*"] = list(STANDARD_TABLE.stop_codons)


HOST_PRIMARY = {
    "ecoli": {"A": "GCG", "R": "CGT", "N": "AAC", "D": "GAT", "C": "TGC", "Q": "CAG", "E": "GAA", "G": "GGC", "H": "CAT", "I": "ATT", "L": "CTG", "K": "AAA", "M": "ATG", "F": "TTT", "P": "CCG", "S": "TCT", "T": "ACC", "W": "TGG", "Y": "TAT", "V": "GTG", "*": "TAA"},
    "human": {"A": "GCC", "R": "CGC", "N": "AAC", "D": "GAC", "C": "TGC", "Q": "CAG", "E": "GAG", "G": "GGC", "H": "CAC", "I": "ATC", "L": "CTG", "K": "AAG", "M": "ATG", "F": "TTC", "P": "CCC", "S": "AGC", "T": "ACC", "W": "TGG", "Y": "TAC", "V": "GTG", "*": "TGA"},
    "yeast": {"A": "GCT", "R": "AGA", "N": "AAT", "D": "GAT", "C": "TGT", "Q": "CAA", "E": "GAA", "G": "GGT", "H": "CAT", "I": "ATT", "L": "TTG", "K": "AAA", "M": "ATG", "F": "TTT", "P": "CCA", "S": "TCT", "T": "ACT", "W": "TGG", "Y": "TAT", "V": "GTT", "*": "TAA"},
    "cho": {"A": "GCC", "R": "CGC", "N": "AAC", "D": "GAC", "C": "TGC", "Q": "CAG", "E": "GAG", "G": "GGC", "H": "CAC", "I": "ATC", "L": "CTG", "K": "AAG", "M": "ATG", "F": "TTC", "P": "CCC", "S": "AGC", "T": "ACC", "W": "TGG", "Y": "TAC", "V": "GTG", "*": "TGA"},
    "hek293": {"A": "GCC", "R": "CGC", "N": "AAC", "D": "GAC", "C": "TGC", "Q": "CAG", "E": "GAG", "G": "GGC", "H": "CAC", "I": "ATC", "L": "CTG", "K": "AAG", "M": "ATG", "F": "TTC", "P": "CCC", "S": "AGC", "T": "ACC", "W": "TGG", "Y": "TAC", "V": "GTG", "*": "TGA"},
    "mouse": {"A": "GCC", "R": "CGC", "N": "AAC", "D": "GAC", "C": "TGC", "Q": "CAG", "E": "GAG", "G": "GGC", "H": "CAC", "I": "ATC", "L": "CTG", "K": "AAG", "M": "ATG", "F": "TTC", "P": "CCC", "S": "AGC", "T": "ACC", "W": "TGG", "Y": "TAC", "V": "GTG", "*": "TGA"},
    "bacillus": {"A": "GCA", "R": "CGT", "N": "AAC", "D": "GAT", "C": "TGT", "Q": "CAA", "E": "GAA", "G": "GGA", "H": "CAT", "I": "ATT", "L": "TTA", "K": "AAA", "M": "ATG", "F": "TTT", "P": "CCA", "S": "TCA", "T": "ACA", "W": "TGG", "Y": "TAT", "V": "GTA", "*": "TAA"},
    "pichia": {"A": "GCT", "R": "AGA", "N": "AAC", "D": "GAT", "C": "TGT", "Q": "CAA", "E": "GAA", "G": "GGT", "H": "CAT", "I": "ATT", "L": "TTG", "K": "AAG", "M": "ATG", "F": "TTT", "P": "CCA", "S": "TCT", "T": "ACT", "W": "TGG", "Y": "TAT", "V": "GTT", "*": "TAA"},
    "insect": {"A": "GCC", "R": "CGC", "N": "AAC", "D": "GAC", "C": "TGC", "Q": "CAG", "E": "GAG", "G": "GGC", "H": "CAC", "I": "ATC", "L": "CTG", "K": "AAG", "M": "ATG", "F": "TTC", "P": "CCC", "S": "TCC", "T": "ACC", "W": "TGG", "Y": "TAC", "V": "GTG", "*": "TAA"},
    "arabidopsis": {"A": "GCT", "R": "AGA", "N": "AAT", "D": "GAT", "C": "TGT", "Q": "CAA", "E": "GAA", "G": "GGT", "H": "CAT", "I": "ATT", "L": "TTG", "K": "AAA", "M": "ATG", "F": "TTT", "P": "CCT", "S": "TCT", "T": "ACT", "W": "TGG", "Y": "TAT", "V": "GTT", "*": "TAA"},
}


@dataclass(frozen=True)
class AdvancedCodonResult:
    host: str
    protein_sequence: str
    optimized_dna: str
    gc_percent: float
    cai_proxy: float
    minimum_window_gc: float
    maximum_window_gc: float
    rare_codon_clusters: int
    removed_motifs: tuple[str, ...]
    unresolved_motifs: tuple[str, ...]
    candidate_index: int
    random_seed: int
    profile_notice: str


def _weights_for_host(host: str) -> dict[str, dict[str, float]]:
    primary = HOST_PRIMARY[host]
    result: dict[str, dict[str, float]] = {}
    for amino_acid, codons in AA_CODONS.items():
        preferred = primary[amino_acid]
        ordered = [preferred, *sorted(codon for codon in codons if codon != preferred)]
        weights = [1.0]
        if len(ordered) > 1:
            weights.extend(max(0.18, 0.62 - 0.08 * index) for index in range(len(ordered) - 1))
        result[amino_acid] = dict(zip(ordered, weights))
    return result


def codon_adaptation_index(dna: str, *, host: str) -> float:
    profile = _weights_for_host(host)
    codons = [dna[index : index + 3] for index in range(0, len(dna), 3)]
    relative = []
    for codon in codons:
        amino_acid = str(Seq(codon).translate())
        weights = profile.get(amino_acid)
        if not weights or codon not in weights:
            continue
        relative.append(weights[codon] / max(weights.values()))
    if not relative:
        return 0.0
    return float(math.exp(sum(math.log(max(value, 1e-12)) for value in relative) / len(relative)))


def _window_gc(dna: str, window: int = 60) -> tuple[float, float]:
    if len(dna) <= window:
        gc = 100 * (dna.count("G") + dna.count("C")) / max(len(dna), 1)
        return gc, gc
    values = [100 * (piece.count("G") + piece.count("C")) / len(piece) for index in range(0, len(dna) - window + 1, 3) if (piece := dna[index : index + window])]
    return min(values), max(values)


def _motifs_present(dna: str, motifs: list[str]) -> list[str]:
    return [motif for motif in motifs if motif and motif.upper() in dna]


def _rare_clusters(dna: str, *, host: str, threshold: float = 0.35, window_codons: int = 6) -> int:
    profile = _weights_for_host(host)
    codons = [dna[index : index + 3] for index in range(0, len(dna), 3)]
    rare = []
    for codon in codons:
        amino_acid = str(Seq(codon).translate())
        weights = profile.get(amino_acid, {})
        relative = weights.get(codon, 0) / max(weights.values(), default=1)
        rare.append(relative < threshold)
    return sum(1 for index in range(max(0, len(rare) - window_codons + 1)) if sum(rare[index : index + window_codons]) >= max(3, window_codons // 2))


def optimize_protein_advanced(
    protein_sequence: str,
    *,
    host: str = "ecoli",
    avoid_motifs: list[str] | None = None,
    target_gc_percent: float | None = None,
    minimum_window_gc: float = 30.0,
    maximum_window_gc: float = 70.0,
    candidates: int = 5,
    random_seed: int = 42,
    append_stop: bool = False,
) -> list[AdvancedCodonResult]:
    protein = "".join(protein_sequence.split()).upper()
    host = host.lower()
    if host not in HOST_PRIMARY:
        raise ValueError("Unknown host. Available: " + ", ".join(sorted(HOST_PRIMARY)))
    valid_amino_acids = set(AA_CODONS)
    if not protein or any(amino_acid not in valid_amino_acids - {"*"} for amino_acid in protein):
        raise ValueError("Protein sequence contains unsupported amino-acid symbols.")
    if append_stop and not protein.endswith("*"):
        protein += "*"
    motifs = [motif.upper().replace("U", "T") for motif in (avoid_motifs or []) if motif]
    profile = _weights_for_host(host)
    outputs: list[AdvancedCodonResult] = []
    target_gc = target_gc_percent if target_gc_percent is not None else (55.0 if host in {"human", "cho", "hek293", "mouse", "insect"} else 45.0)
    for candidate_index in range(max(1, candidates)):
        rng = random.Random(random_seed + candidate_index)
        codons = []
        for amino_acid in protein:
            weights = profile[amino_acid]
            options = list(weights)
            option_weights = [weights[codon] ** 3 for codon in options]
            codons.append(rng.choices(options, weights=option_weights, k=1)[0])
        dna = "".join(codons)
        removed = []
        for _ in range(max(100, len(protein) * 3)):
            present = _motifs_present(dna, motifs)
            min_gc, max_gc = _window_gc(dna)
            overall_gc = 100 * (dna.count("G") + dna.count("C")) / len(dna)
            gc_problem = min_gc < minimum_window_gc or max_gc > maximum_window_gc or abs(overall_gc - target_gc) > 12
            if not present and not gc_problem:
                break
            if present:
                motif = present[0]
                index = dna.find(motif) // 3
            else:
                index = rng.randrange(len(codons))
            amino_acid = protein[index]
            current = codons[index]
            choices = [codon for codon in profile[amino_acid] if codon != current]
            if not choices:
                break
            best = None
            for choice in choices:
                trial_codons = codons.copy()
                trial_codons[index] = choice
                trial = "".join(trial_codons)
                trial_min, trial_max = _window_gc(trial)
                trial_gc = 100 * (trial.count("G") + trial.count("C")) / len(trial)
                penalty = 100 * len(_motifs_present(trial, motifs)) + abs(trial_gc - target_gc) + max(0, minimum_window_gc - trial_min) + max(0, trial_max - maximum_window_gc) - 5 * codon_adaptation_index(trial, host=host)
                if best is None or penalty < best[0]:
                    best = (penalty, choice, trial)
            if best is None:
                break
            codons[index] = best[1]
            dna = best[2]
            if present and motif not in dna:
                removed.append(motif)
        minimum_gc, maximum_gc = _window_gc(dna)
        unresolved = _motifs_present(dna, motifs)
        outputs.append(
            AdvancedCodonResult(
                host=host,
                protein_sequence=protein,
                optimized_dna=dna,
                gc_percent=round(100 * (dna.count("G") + dna.count("C")) / len(dna), 2),
                cai_proxy=round(codon_adaptation_index(dna, host=host), 4),
                minimum_window_gc=round(minimum_gc, 2),
                maximum_window_gc=round(maximum_gc, 2),
                rare_codon_clusters=_rare_clusters(dna, host=host),
                removed_motifs=tuple(dict.fromkeys(removed)),
                unresolved_motifs=tuple(unresolved),
                candidate_index=candidate_index + 1,
                random_seed=random_seed + candidate_index,
                profile_notice="Bundled engineering codon profile; validate against the intended expression system and current host-specific references.",
            )
        )
    return sorted(outputs, key=lambda item: (len(item.unresolved_motifs), -item.cai_proxy, abs(item.gc_percent - target_gc)))


def result_dict(result: AdvancedCodonResult) -> dict:
    return asdict(result)
