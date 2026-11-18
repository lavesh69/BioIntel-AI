from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from Bio.Align import PairwiseAligner, substitution_matrices

from biointel.sequence.parser import ParsedSequence

DOMAIN_SIGNATURES = [
    (
        "Protein kinase catalytic core",
        r"VAIK.{8,35}HRD.{5,25}DFG",
        "Catalytic kinase motif constellation",
    ),
    ("P-loop NTPase", r"[AGX]....GK[ST]", "Walker-A/P-loop nucleotide-binding motif"),
    ("Protein tyrosine phosphatase", r"HC.{5}R[STG]", "PTP catalytic-loop motif"),
    ("C2H2 zinc finger", r"C.{2,4}C.{10,16}H.{2,5}H", "Classical C2H2 zinc-binding signature"),
    (
        "C3HC4 RING finger",
        r"C.{2}C.{9,39}C.{1,3}H.{2,3}C.{4,48}C.{2}C",
        "RING-like zinc-binding signature",
    ),
    ("Homeobox DNA-binding", r"WFQNRR", "Conserved homeodomain recognition motif"),
    ("SH2 domain", r"FLVR", "Conserved SH2 phosphotyrosine-recognition motif"),
    ("SH3 domain", r"[YF]..[YF].{8,30}P..P", "Proline-rich ligand recognition pattern"),
    ("EF-hand calcium binding", r"D.{2}D.{2}[DEN].{4}E", "Acidic calcium-binding loop pattern"),
    (
        "Rossmann-like dinucleotide binding",
        r"[TIV].{1,2}[AG].{0,2}G..G",
        "N-terminal glycine-rich dinucleotide motif",
    ),
    ("Serine protease", r"GDSGGP", "Trypsin-like active-site neighbourhood"),
    ("Cysteine protease", r"CG[SC]G", "Cysteine protease active-site neighbourhood"),
    ("HExxH metalloprotease", r"HE..H", "Metal-binding metalloprotease motif"),
    ("Nuclear receptor zinc-binding", r"C.EGCKGFFR", "Nuclear receptor DNA-binding signature"),
    (
        "Death domain interaction motif",
        r"[LIV].{2}[LIV].{2}[DE].{2}[LIV]",
        "Helical interaction-domain propensity",
    ),
]

ENZYME_HINTS = [
    ("EC 2.7.-.- transferase/kinase candidate", ("VAIK", "HRD", "DFG")),
    ("EC 3.4.-.- serine hydrolase/protease candidate", ("GDSG",)),
    ("EC 3.4.-.- metalloprotease candidate", ("HEXXH",)),
    ("EC 3.1.3.- phosphatase candidate", ("HCXAGXXR",)),
    ("EC 1.-.-.- oxidoreductase/Rossmann candidate", ("TGGXGG", "VIGLG")),
]


@dataclass(frozen=True)
class ProteomicsSummary:
    proteins: int
    samples: int
    quantified_values: int
    missing_fraction: float
    median_proteins_per_sample: float
    median_samples_per_protein: float


def scan_domain_signatures(sequence: str) -> pd.DataFrame:
    seq = "".join(str(sequence).upper().split())
    rows = []
    for name, pattern, evidence in DOMAIN_SIGNATURES:
        for match in re.finditer(pattern, seq):
            rows.append(
                {
                    "domain_hint": name,
                    "start": match.start() + 1,
                    "end": match.end(),
                    "matched_sequence": match.group(0),
                    "evidence": evidence,
                    "confidence": "screening",
                }
            )
    return pd.DataFrame(
        rows, columns=["domain_hint", "start", "end", "matched_sequence", "evidence", "confidence"]
    )


def enzyme_class_hints(sequence: str) -> pd.DataFrame:
    seq = "".join(str(sequence).upper().split())
    rows = []
    for label, motifs in ENZYME_HINTS:
        normalized = [motif.replace("X", ".") for motif in motifs]
        hits = [motif for motif in normalized if re.search(motif, seq)]
        if hits:
            rows.append(
                {
                    "enzyme_class_hint": label,
                    "matched_patterns": ", ".join(hits),
                    "evidence_level": "motif-screen",
                }
            )
    return pd.DataFrame(rows, columns=["enzyme_class_hint", "matched_patterns", "evidence_level"])


def _kmer_set(sequence: str, k: int = 4) -> set[str]:
    sequence = str(sequence).upper()
    return {sequence[index : index + k] for index in range(max(1, len(sequence) - k + 1))}


def reference_similarity_search(
    query: str,
    references: Iterable[ParsedSequence],
    *,
    maximum_hits: int = 10,
    prefilter: int = 40,
) -> pd.DataFrame:
    query = "".join(str(query).upper().split())
    if not query:
        raise ValueError("Query protein cannot be empty.")
    query_kmers = _kmer_set(query)
    candidates = []
    for reference in references:
        reference_sequence = reference.sequence.upper()
        reference_kmers = _kmer_set(reference_sequence)
        union = query_kmers | reference_kmers
        score = len(query_kmers & reference_kmers) / max(len(union), 1)
        candidates.append((score, reference))
    candidates.sort(key=lambda item: item[0], reverse=True)
    aligner = PairwiseAligner(mode="local")
    aligner.substitution_matrix = substitution_matrices.load("BLOSUM62")
    aligner.open_gap_score = -10
    aligner.extend_gap_score = -0.5
    rows = []
    for prefilter_score, reference in candidates[: max(prefilter, maximum_hits)]:
        alignment = aligner.align(query, reference.sequence.upper())[0]
        coordinates = alignment.coordinates
        aligned_query = 0
        aligned_reference = 0
        identity = 0
        for index in range(coordinates.shape[1] - 1):
            q0, q1 = int(coordinates[0, index]), int(coordinates[0, index + 1])
            r0, r1 = int(coordinates[1, index]), int(coordinates[1, index + 1])
            if q1 > q0 and r1 > r0:
                left = query[q0:q1]
                right = reference.sequence.upper()[r0:r1]
                identity += sum(a == b for a, b in zip(left, right))
                aligned_query += len(left)
                aligned_reference += len(right)
        comparable = max(aligned_query, aligned_reference, 1)
        rows.append(
            {
                "reference": reference.header,
                "alignment_score": float(alignment.score),
                "identity_percent": 100 * identity / comparable,
                "query_coverage_percent": 100 * aligned_query / len(query),
                "reference_coverage_percent": 100
                * aligned_reference
                / max(len(reference.sequence), 1),
                "kmer_prefilter": prefilter_score,
                "reference_length": len(reference.sequence),
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values(["alignment_score", "identity_percent"], ascending=False)
        .head(maximum_hits)
        .reset_index(drop=True)
    )


def tryptic_digest(
    sequence: str,
    *,
    missed_cleavages: int = 0,
    minimum_length: int = 6,
    maximum_length: int = 45,
) -> pd.DataFrame:
    seq = "".join(str(sequence).upper().split())
    cleavage = [0]
    for index, amino_acid in enumerate(seq):
        if amino_acid in {"K", "R"} and (index + 1 == len(seq) or seq[index + 1] != "P"):
            cleavage.append(index + 1)
    if cleavage[-1] != len(seq):
        cleavage.append(len(seq))
    rows = []
    for start_index in range(len(cleavage) - 1):
        for missed in range(max(0, int(missed_cleavages)) + 1):
            end_index = start_index + missed + 1
            if end_index >= len(cleavage):
                continue
            start = cleavage[start_index]
            end = cleavage[end_index]
            peptide = seq[start:end]
            if minimum_length <= len(peptide) <= maximum_length:
                rows.append(
                    {
                        "peptide": peptide,
                        "start": start + 1,
                        "end": end,
                        "length": len(peptide),
                        "missed_cleavages": missed,
                        "unique_in_protein": seq.count(peptide) == 1,
                    }
                )
    return pd.DataFrame(rows).drop_duplicates(["peptide", "start", "end"]).reset_index(drop=True)


def peptide_sequence_coverage(
    sequence: str, peptides: Iterable[str]
) -> tuple[pd.DataFrame, dict[str, float | int]]:
    seq = "".join(str(sequence).upper().split())
    peptide_list = [str(value) for value in peptides]
    covered = np.zeros(len(seq), dtype=bool)
    rows = []
    for peptide in peptide_list:
        peptide = "".join(str(peptide).upper().split())
        start = 0
        hits = 0
        while peptide and (index := seq.find(peptide, start)) >= 0:
            covered[index : index + len(peptide)] = True
            rows.append({"peptide": peptide, "start": index + 1, "end": index + len(peptide)})
            hits += 1
            start = index + 1
        if hits == 0:
            rows.append({"peptide": peptide, "start": None, "end": None})
    summary = {
        "protein_length": len(seq),
        "covered_residues": int(covered.sum()),
        "coverage_percent": 100 * float(covered.mean()) if len(seq) else 0.0,
        "peptides_submitted": len(peptide_list),
    }
    return pd.DataFrame(rows), summary


def validate_quantitative_proteomics(
    frame: pd.DataFrame,
    *,
    protein_column: str = "protein",
    sample_column: str = "sample",
    intensity_column: str = "intensity",
) -> pd.DataFrame:
    required = {protein_column, sample_column, intensity_column}
    if not required.issubset(frame.columns):
        raise ValueError("Proteomics table requires protein, sample and intensity columns.")
    output = frame.copy()
    output[protein_column] = output[protein_column].astype(str).str.strip()
    output[sample_column] = output[sample_column].astype(str).str.strip()
    output[intensity_column] = pd.to_numeric(output[intensity_column], errors="coerce")
    if output[protein_column].eq("").any() or output[sample_column].eq("").any():
        raise ValueError("Protein and sample identifiers cannot be empty.")
    duplicates = output.duplicated([protein_column, sample_column], keep=False)
    if duplicates.any():
        output = output.groupby([protein_column, sample_column], as_index=False)[
            intensity_column
        ].mean()
    finite = output[intensity_column].dropna().to_numpy(dtype=float)
    if not np.all(np.isfinite(finite)):
        raise ValueError("Protein intensities must be finite when present.")
    if (finite < 0).any():
        raise ValueError("Protein intensities cannot be negative.")
    if output[intensity_column].notna().sum() == 0:
        raise ValueError("Proteomics table contains no quantified intensities.")
    return output


def proteomics_summary(frame: pd.DataFrame) -> ProteomicsSummary:
    validated = validate_quantitative_proteomics(frame)
    pivot = validated.pivot(index="protein", columns="sample", values="intensity")
    return ProteomicsSummary(
        proteins=pivot.shape[0],
        samples=pivot.shape[1],
        quantified_values=int(pivot.notna().sum().sum()),
        missing_fraction=float(pivot.isna().mean().mean()),
        median_proteins_per_sample=float(pivot.notna().sum(axis=0).median()),
        median_samples_per_protein=float(pivot.notna().sum(axis=1).median()),
    )


def differential_protein_abundance(
    frame: pd.DataFrame,
    metadata: pd.DataFrame,
    *,
    group_a: str,
    group_b: str,
) -> pd.DataFrame:
    from scipy.stats import ttest_ind

    data = validate_quantitative_proteomics(frame)
    if not {"sample", "group"}.issubset(metadata.columns):
        raise ValueError("Metadata requires sample and group columns.")
    groups = dict(zip(metadata["sample"].astype(str), metadata["group"].astype(str)))
    pivot = data.pivot(index="protein", columns="sample", values="intensity")
    a = [sample for sample in pivot.columns if groups.get(sample) == group_a]
    b = [sample for sample in pivot.columns if groups.get(sample) == group_b]
    if len(a) < 2 or len(b) < 2:
        raise ValueError("Each proteomics comparison group needs at least two samples.")
    log_values = np.log2(pivot + 1.0)
    n_a = log_values[a].notna().sum(axis=1)
    n_b = log_values[b].notna().sum(axis=1)
    testable = (n_a >= 2) & (n_b >= 2)
    p_values = np.ones(len(pivot), dtype=float)
    if testable.any():
        tested = ttest_ind(
            log_values.loc[testable, b],
            log_values.loc[testable, a],
            axis=1,
            equal_var=False,
            nan_policy="omit",
        )
        candidate = np.asarray(tested.pvalue, dtype=float)
        candidate = np.where(np.isfinite(candidate), candidate, 1.0)
        p_values[np.flatnonzero(testable.to_numpy())] = np.clip(candidate, 0.0, 1.0)
    result = pd.DataFrame(
        {
            "protein": pivot.index,
            "mean_a": pivot[a].mean(axis=1),
            "mean_b": pivot[b].mean(axis=1),
            "log2_fold_change": log_values[b].mean(axis=1) - log_values[a].mean(axis=1),
            "n_a": n_a.to_numpy(int),
            "n_b": n_b.to_numpy(int),
            "testable": testable.to_numpy(bool),
            "p_value": p_values,
        }
    )
    order = np.argsort(p_values)
    adjusted = np.ones(len(result), dtype=float)
    running = 1.0
    for rank, index in reversed(list(enumerate(order, 1))):
        running = min(running, p_values[index] * len(result) / rank)
        adjusted[index] = min(1.0, running)
    result["fdr_bh"] = adjusted
    return result.sort_values("fdr_bh").reset_index(drop=True)
