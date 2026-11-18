from __future__ import annotations

from dataclasses import dataclass
from biointel.tools.runtime import resolve_tool, tool_available
from typing import Iterable

import numpy as np
import pandas as pd
from Bio.Seq import Seq

from biointel.projects.comparative_genomics import (
    GenomeRecord,
    clean_dna,
    pairwise_variant_table,
    reverse_complement,
)

REFERENCE_PACK_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class AniSummary:
    query: str
    reference: str
    aligned_identity_percent: float
    aligned_reference_coverage_percent: float
    aligned_query_coverage_percent: float
    substitutions: int
    inserted_bases: int
    deleted_bases: int
    interpretation: str


def alignment_ani(
    query: GenomeRecord,
    reference: GenomeRecord,
    *,
    maximum_alignment_cells: int = 50_000_000,
) -> AniSummary:
    variants = pairwise_variant_table(
        query,
        reference,
        maximum_alignment_cells=maximum_alignment_cells,
    )
    substitutions = int(
        (variants.get("variant_type", pd.Series(dtype=str)) == "Substitution").sum()
    )
    insertion_rows = variants[variants.get("variant_type", pd.Series(dtype=str)) == "Insertion"]
    deletion_rows = variants[variants.get("variant_type", pd.Series(dtype=str)) == "Deletion"]
    inserted = (
        int(pd.to_numeric(insertion_rows.get("event_length"), errors="coerce").fillna(1).sum())
        if not insertion_rows.empty
        else 0
    )
    deleted = (
        int(pd.to_numeric(deletion_rows.get("event_length"), errors="coerce").fillna(1).sum())
        if not deletion_rows.empty
        else 0
    )
    reference_length = len(reference.sequence)
    query_length = len(query.sequence)
    aligned_reference = max(reference_length, 1)
    aligned_query = max(query_length, 1)
    difference_bases = substitutions + inserted + deleted
    aligned_columns = max(reference_length + inserted, query_length + deleted, 1)
    identity = 100 * max(aligned_columns - difference_bases, 0) / aligned_columns
    if (
        identity >= 95
        and min(query_length, reference_length) / max(query_length, reference_length) >= 0.65
    ):
        interpretation = "species-level ANI-like range; confirm with accepted ANI software"
    elif identity >= 90:
        interpretation = "related genome; below common species-level screening threshold"
    else:
        interpretation = "distant genome"
    return AniSummary(
        query=query.identifier,
        reference=reference.identifier,
        aligned_identity_percent=identity,
        aligned_reference_coverage_percent=100
        * min(aligned_reference, query_length)
        / aligned_reference,
        aligned_query_coverage_percent=100 * min(aligned_query, reference_length) / aligned_query,
        substitutions=substitutions,
        inserted_bases=inserted,
        deleted_bases=deleted,
        interpretation=interpretation,
    )


def alignment_ani_table(
    queries: Iterable[GenomeRecord],
    references: Iterable[GenomeRecord],
    *,
    best_only: bool = True,
    maximum_alignment_cells: int = 50_000_000,
) -> pd.DataFrame:
    rows = []
    for query in queries:
        query_rows = []
        for reference in references:
            summary = alignment_ani(
                query,
                reference,
                maximum_alignment_cells=maximum_alignment_cells,
            )
            query_rows.append(summary.__dict__)
        query_rows.sort(key=lambda row: row["aligned_identity_percent"], reverse=True)
        rows.extend(query_rows[:1] if best_only else query_rows)
    return pd.DataFrame(rows)


def validate_marker_reference_pack(markers: pd.DataFrame) -> pd.DataFrame:
    output = markers.copy()
    aliases = {
        "marker_id": "marker",
        "marker_name": "marker_name",
        "marker_type": "category",
        "source_version": "release",
        "review_status": "evidence",
    }
    for source, target in aliases.items():
        if target not in output.columns and source in output.columns:
            output[target] = output[source]
    required = {"marker", "sequence", "category"}
    if not required.issubset(output.columns):
        raise ValueError(
            "Marker pack requires marker/marker_id, sequence and category/marker_type columns."
        )
    for optional, default in {
        "source": "user/local",
        "release": "unversioned",
        "evidence": "sequence-screen",
        "organism": "unspecified",
    }.items():
        if optional not in output:
            output[optional] = default
    output["marker"] = output["marker"].astype(str).str.strip()
    output["sequence"] = (
        output["sequence"].astype(str).str.upper().str.replace(r"\s+", "", regex=True)
    )
    output["category"] = output["category"].astype(str).str.strip()
    invalid = output["sequence"].map(lambda value: bool(set(value) - set("ACGTRYSWKMBDHVN")))
    if invalid.any():
        raise ValueError("Marker pack contains unsupported nucleotide symbols.")
    if output["marker"].eq("").any() or output["sequence"].str.len().lt(8).any():
        raise ValueError(
            "Marker identifiers cannot be empty and marker sequences must be at least 8 bases."
        )
    provenance_columns = ["source", "release", "evidence", "organism"]
    output["provenance_complete"] = output[provenance_columns].apply(
        lambda row: all(str(value).strip() not in {"", "none", "nan", "unversioned"} for value in row),
        axis=1,
    )
    conflicts = output.groupby("marker")["sequence"].nunique()
    if (conflicts > 1).any():
        raise ValueError("Marker pack contains identifiers assigned to conflicting sequences.")
    return output.drop_duplicates(["marker", "sequence", "category"]).reset_index(drop=True)


def _translate_orfs(
    record: GenomeRecord,
    *,
    minimum_amino_acids: int = 30,
    start_codons: set[str] | None = None,
) -> pd.DataFrame:
    sequence = clean_dna(record.sequence)
    start_codons = start_codons or {"ATG", "GTG", "TTG"}
    stops = {"TAA", "TAG", "TGA"}
    rows = []
    for strand, dna in (("+", sequence), ("-", reverse_complement(sequence))):
        for frame in range(3):
            start = None
            start_codon = None
            for position in range(frame, len(dna) - 2, 3):
                codon = dna[position : position + 3]
                if start is None and codon in start_codons:
                    start, start_codon = position, codon
                elif start is not None and codon in stops:
                    coding = dna[start:position]
                    protein = str(Seq(coding).translate(to_stop=False))
                    if len(protein) >= minimum_amino_acids:
                        if strand == "+":
                            genomic_start, genomic_end = start + 1, position + 3
                        else:
                            genomic_start = len(sequence) - (position + 3) + 1
                            genomic_end = len(sequence) - start
                        rows.append(
                            {
                                "genome_id": record.identifier,
                                "orf_id": f"{record.identifier}|{strand}|{genomic_start}-{genomic_end}",
                                "strand": strand,
                                "frame": frame + 1,
                                "start": genomic_start,
                                "end": genomic_end,
                                "length_aa": len(protein),
                                "start_codon": start_codon,
                                "stop_codon": codon,
                                "protein_sequence": protein,
                            }
                        )
                    start, start_codon = None, None
    return pd.DataFrame(rows)


def _protein_kmers(sequence: str, k: int = 5) -> set[str]:
    sequence = str(sequence).upper()
    return {sequence[index : index + k] for index in range(max(1, len(sequence) - k + 1))}


def gene_pangenome(
    records: Iterable[GenomeRecord],
    *,
    minimum_amino_acids: int = 30,
    similarity_threshold: float = 0.65,
    maximum_orfs: int = 20_000,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    genomes = list(records)
    orf_tables = [
        _translate_orfs(record, minimum_amino_acids=minimum_amino_acids) for record in genomes
    ]
    orfs = (
        pd.concat([table for table in orf_tables if not table.empty], ignore_index=True)
        if any(not table.empty for table in orf_tables)
        else pd.DataFrame()
    )
    if orfs.empty:
        return orfs, pd.DataFrame(), pd.DataFrame()
    if len(orfs) > maximum_orfs:
        raise ValueError(f"Predicted ORFs exceed the {maximum_orfs:,} safety limit.")
    representatives: list[dict[str, object]] = []
    assignments = []
    for row in orfs.itertuples(index=False):
        signature = _protein_kmers(row.protein_sequence)
        best_index = None
        best_similarity = 0.0
        for index, representative in enumerate(representatives):
            other = representative["signature"]
            union = signature | other
            similarity = len(signature & other) / max(len(union), 1)
            if similarity > best_similarity:
                best_similarity = similarity
                best_index = index
        if best_index is None or best_similarity < similarity_threshold:
            representatives.append(
                {
                    "cluster": len(representatives) + 1,
                    "representative_orf": row.orf_id,
                    "representative_sequence": row.protein_sequence,
                    "signature": signature,
                }
            )
            cluster = len(representatives)
            best_similarity = 1.0
        else:
            cluster = int(representatives[best_index]["cluster"])
        assignments.append(
            {
                "genome_id": row.genome_id,
                "orf_id": row.orf_id,
                "gene_cluster": f"GC{cluster:05d}",
                "similarity_to_representative": best_similarity,
                "length_aa": row.length_aa,
            }
        )
    assignment_table = pd.DataFrame(assignments)
    presence = (
        assignment_table.assign(present=1)
        .pivot_table(
            index="gene_cluster", columns="genome_id", values="present", aggfunc="max", fill_value=0
        )
        .reset_index()
    )
    genome_columns = [column for column in presence.columns if column != "gene_cluster"]
    prevalence = presence[genome_columns].sum(axis=1)
    total = max(len(genome_columns), 1)
    summary = presence[["gene_cluster"]].copy()
    summary["genomes_present"] = prevalence
    summary["prevalence_percent"] = 100 * prevalence / total
    summary["category"] = np.select(
        [prevalence == total, prevalence == 1, prevalence >= max(2, int(np.ceil(0.5 * total)))],
        ["core", "singleton", "shell"],
        default="cloud",
    )
    return assignment_table, presence, summary


def window_divergence_scan(
    query: GenomeRecord,
    reference: GenomeRecord,
    *,
    window: int = 1000,
    step: int = 500,
) -> pd.DataFrame:
    left = clean_dna(query.sequence)
    right = clean_dna(reference.sequence)
    length = min(len(left), len(right))
    window = max(50, min(int(window), length))
    step = max(10, int(step))
    rows = []
    for start in range(0, max(length - window + 1, 1), step):
        q = left[start : start + window]
        r = right[start : start + window]
        comparable = [(a, b) for a, b in zip(q, r) if a in "ACGT" and b in "ACGT"]
        divergence = sum(a != b for a, b in comparable) / max(len(comparable), 1)
        rows.append(
            {
                "query": query.identifier,
                "reference": reference.identifier,
                "start": start + 1,
                "end": start + len(q),
                "divergence": divergence,
                "identity_percent": 100 * (1 - divergence),
                "comparable_bases": len(comparable),
            }
        )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        median = float(frame["divergence"].median())
        mad = float((frame["divergence"] - median).abs().median())
        threshold = median + 3 * 1.4826 * mad if mad > 0 else median + 0.02
        frame["divergence_outlier"] = frame["divergence"] > threshold
    return frame


def pathogen_tool_availability() -> pd.DataFrame:
    tools = {
        "Mash": "mash",
        "sourmash": "sourmash",
        "FastANI": "fastANI",
        "minimap2": "minimap2",
        "Bakta": "bakta",
        "Prokka": "prokka",
        "AMRFinderPlus": "amrfinder",
        "MLST": "mlst",
        "QUAST": "quast.py",
    }
    return pd.DataFrame(
        [
            {
                "tool": label,
                "executable": executable,
                "available": tool_available(executable),
                "path": resolve_tool(executable).executable,
            }
            for label, executable in tools.items()
        ]
    )
