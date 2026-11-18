from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from Bio.Align import PairwiseAligner

DNA = set("ACGTRYSWKMBDHVN")


@dataclass(frozen=True)
class GenomeRecord:
    identifier: str
    sequence: str
    description: str = ""


def clean_dna(sequence: str) -> str:
    cleaned = "".join(str(sequence).upper().split())
    if not cleaned:
        raise ValueError("Genome sequence cannot be empty.")
    invalid = sorted(set(cleaned) - DNA)
    if invalid:
        raise ValueError(f"Unsupported nucleotide symbols: {', '.join(invalid)}")
    return cleaned


def parse_fasta(text: str) -> list[GenomeRecord]:
    records: list[GenomeRecord] = []
    identifier = ""
    description = ""
    chunks: list[str] = []
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if identifier:
                records.append(GenomeRecord(identifier, clean_dna("".join(chunks)), description))
            header = line[1:].strip() or f"sequence_{len(records) + 1}"
            identifier, _, description = header.partition(" ")
            chunks = []
        else:
            if not identifier:
                identifier = f"sequence_{len(records) + 1}"
            chunks.append(line)
    if identifier:
        records.append(GenomeRecord(identifier, clean_dna("".join(chunks)), description))
    if not records:
        raise ValueError("No FASTA records were found.")
    identifiers = [record.identifier for record in records]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("FASTA identifiers must be unique.")
    return records


def sequence_profile(record: GenomeRecord, *, k: int = 15) -> dict[str, float | str | int]:
    sequence = clean_dna(record.sequence)
    canonical = "".join(base for base in sequence if base in "ACGT")
    gc = (canonical.count("G") + canonical.count("C")) / max(len(canonical), 1)
    ambiguous = sum(base not in "ACGT" for base in sequence) / max(len(sequence), 1)
    kmers = kmer_set(sequence, k)
    return {
        "genome_id": record.identifier,
        "length_bp": len(sequence),
        "gc_percent": gc * 100,
        "ambiguous_percent": ambiguous * 100,
        "distinct_kmers": len(kmers),
        "description": record.description,
    }


def reverse_complement(sequence: str) -> str:
    complement = str.maketrans(
        "ACGTRYSWKMBDHVN",
        "TGCAYRSWMKVHDBN",
    )
    return clean_dna(sequence).translate(complement)[::-1]


def canonical_kmer(kmer: str) -> str:
    reverse = reverse_complement(kmer)
    return min(kmer, reverse)


def kmer_set(sequence: str, k: int = 15) -> set[str]:
    cleaned = clean_dna(sequence)
    if k < 3 or k > 31:
        raise ValueError("k-mer size must be between 3 and 31.")
    if len(cleaned) < k:
        return {canonical_kmer(cleaned)}
    return {
        canonical_kmer(cleaned[index : index + k])
        for index in range(len(cleaned) - k + 1)
        if set(cleaned[index : index + k]).issubset(set("ACGT"))
    }


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def containment_similarity(query: set[str], reference: set[str]) -> float:
    return len(query & reference) / len(query) if query else 0.0


def compare_genomes(
    queries: Iterable[GenomeRecord],
    references: Iterable[GenomeRecord],
    *,
    k: int = 15,
) -> pd.DataFrame:
    query_records = list(queries)
    reference_records = list(references)
    if not query_records or not reference_records:
        raise ValueError("At least one query and one reference genome are required.")
    reference_kmers = {record.identifier: kmer_set(record.sequence, k) for record in reference_records}
    rows = []
    for query in query_records:
        query_kmers = kmer_set(query.sequence, k)
        query_gc = float(sequence_profile(query, k=k)["gc_percent"])
        for reference in reference_records:
            reference_profile = sequence_profile(reference, k=k)
            reference_set = reference_kmers[reference.identifier]
            jaccard = jaccard_similarity(query_kmers, reference_set)
            query_containment = containment_similarity(query_kmers, reference_set)
            reference_containment = containment_similarity(reference_set, query_kmers)
            gc_difference = abs(query_gc - float(reference_profile["gc_percent"]))
            composition_agreement = 1 - min(gc_difference / 25, 1)
            score = max(
                0.0,
                min(
                    1.0,
                    0.50 * reference_containment
                    + 0.25 * query_containment
                    + 0.20 * jaccard
                    + 0.05 * composition_agreement,
                ),
            )
            rows.append(
                {
                    "query_genome": query.identifier,
                    "reference_genome": reference.identifier,
                    "jaccard_similarity": jaccard,
                    "query_containment": query_containment,
                    "reference_containment": reference_containment,
                    "gc_difference_percent": gc_difference,
                    "screening_score": score,
                    "screening_class": (
                        "High similarity" if score >= 0.72 else "Moderate similarity" if score >= 0.4 else "Low similarity"
                    ),
                }
            )
    frame = pd.DataFrame(rows)
    return frame.sort_values(["query_genome", "screening_score"], ascending=[True, False]).reset_index(drop=True)


def distance_matrix(records: Iterable[GenomeRecord], *, k: int = 15) -> pd.DataFrame:
    items = list(records)
    fingerprints = {record.identifier: kmer_set(record.sequence, k) for record in items}
    matrix = pd.DataFrame(index=[record.identifier for record in items], columns=[record.identifier for record in items], dtype=float)
    for left in items:
        for right in items:
            matrix.loc[left.identifier, right.identifier] = 1.0 - jaccard_similarity(
                fingerprints[left.identifier], fingerprints[right.identifier]
            )
    return matrix


def screen_markers(
    records: Iterable[GenomeRecord],
    markers: pd.DataFrame,
) -> pd.DataFrame:
    required = {"marker", "sequence", "category"}
    if not required.issubset(markers.columns):
        raise ValueError("Marker table requires marker, sequence and category columns.")
    rows = []
    for record in records:
        genome = clean_dna(record.sequence)
        reverse = reverse_complement(genome)
        for marker_row in markers.itertuples(index=False):
            marker_sequence = clean_dna(getattr(marker_row, "sequence"))
            detected = marker_sequence in genome or marker_sequence in reverse
            rows.append(
                {
                    "genome_id": record.identifier,
                    "marker": str(getattr(marker_row, "marker")),
                    "category": str(getattr(marker_row, "category")),
                    "detected": detected,
                    "marker_length": len(marker_sequence),
                    "evidence": "Exact sequence match" if detected else "Not detected",
                }
            )
    return pd.DataFrame(rows)


def demo_reference_panel() -> list[GenomeRecord]:
    # Deterministic synthetic fragments: these are software-validation references, not organism identifiers.
    base = {
        "Demo_Enterobacterales_A": "ATGCGTACGTTACGCGGATCCGATGCTAGCTAGGCTAACCGGTTACGATCGATGGCATCGTACG" * 7,
        "Demo_Enterobacterales_B": "ATGCGTACGTTACGCGGATCCGATGCTAGTTAGGCTAACCGGTTACGATCGTTGGCATCGTACG" * 7,
        "Demo_GramPositive_A": "ATGAAATTTGGGCCCAAATTTGGCGCGTATATATGCGCGGCCATTAACCGGTTTATGCGATGCA" * 7,
        "Demo_Respiratory_A": "ATGCCGATCGTACCGGTTAACTGACGATGATCTCGGATATCGCTAGCATCGGTTACCGATATCG" * 7,
    }
    return [GenomeRecord(identifier=key, sequence=value, description="Synthetic comparison reference") for key, value in base.items()]


def demo_query_panel() -> list[GenomeRecord]:
    references = demo_reference_panel()
    query_a = list(references[0].sequence)
    query_b = list(references[2].sequence)
    for index in range(11, len(query_a), 97):
        query_a[index] = "A" if query_a[index] != "A" else "T"
    for index in range(23, len(query_b), 83):
        query_b[index] = "C" if query_b[index] != "C" else "G"
    return [
        GenomeRecord("Query_Isolate_01", "".join(query_a), "Synthetic isolate"),
        GenomeRecord("Query_Isolate_02", "".join(query_b), "Synthetic isolate"),
    ]


def demo_marker_panel() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"marker": "Demo_virulence_A", "sequence": "GATCCGATGCTAGC", "category": "Virulence proxy"},
            {"marker": "Demo_resistance_A", "sequence": "TTTGGGCCCAAATT", "category": "Resistance proxy"},
            {"marker": "Demo_lineage_A", "sequence": "GACGATGATCTCGG", "category": "Lineage proxy"},
        ]
    )


def genome_qc(records: Iterable[GenomeRecord], *, k: int = 15) -> pd.DataFrame:
    rows = []
    for record in records:
        profile = sequence_profile(record, k=k)
        sequence = clean_dna(record.sequence)
        canonical = sequence.replace("N", "")
        mono_fraction = max((canonical.count(base) / max(len(canonical), 1) for base in "ACGT"), default=0.0)
        low_complexity = mono_fraction >= 0.65
        status = "Review" if float(profile["ambiguous_percent"]) > 5 or low_complexity or len(sequence) < max(k * 5, 100) else "Pass"
        rows.append(
            {
                **profile,
                "maximum_single_base_percent": mono_fraction * 100,
                "low_complexity_flag": low_complexity,
                "qc_status": status,
            }
        )
    return pd.DataFrame(rows)


def best_hit_summary(rankings: pd.DataFrame) -> pd.DataFrame:
    required = {"query_genome", "reference_genome", "screening_score"}
    if not required.issubset(rankings.columns):
        raise ValueError("Rankings table is missing required columns.")
    ordered = rankings.sort_values(["query_genome", "screening_score"], ascending=[True, False]).copy()
    rows = []
    for query, group in ordered.groupby("query_genome", sort=False):
        group = group.reset_index(drop=True)
        best = group.iloc[0]
        second_score = float(group.iloc[1]["screening_score"]) if len(group) > 1 else 0.0
        margin = float(best["screening_score"]) - second_score
        rows.append(
            {
                "query_genome": query,
                "best_reference": best["reference_genome"],
                "best_score": float(best["screening_score"]),
                "second_best_score": second_score,
                "identification_margin": margin,
                "screening_class": best.get("screening_class", ""),
                "assignment_confidence": "High" if float(best["screening_score"]) >= 0.72 and margin >= 0.08 else "Review" if float(best["screening_score"]) >= 0.4 else "Low",
            }
        )
    return pd.DataFrame(rows)


def pairwise_variant_table(
    query: GenomeRecord,
    reference: GenomeRecord,
    *,
    limit: int | None = None,
    maximum_alignment_cells: int = 50_000_000,
) -> pd.DataFrame:
    """Call substitutions and normalized indel events from an affine-gap global alignment.

    Exact dynamic-programming alignment is intentionally bounded. For chromosome-scale or
    whole bacterial-genome inputs, use a dedicated aligner such as minimap2/MAFFT and import
    the resulting alignment rather than silently applying an unsuitable heuristic.
    """
    query_sequence = clean_dna(query.sequence)
    reference_sequence = clean_dna(reference.sequence)
    cells = (len(query_sequence) + 1) * (len(reference_sequence) + 1)
    if cells > int(maximum_alignment_cells):
        raise ValueError(
            "Exact global alignment exceeds the in-app safety limit "
            f"({cells:,} DP cells). Use an external genome aligner and import its alignment."
        )

    aligner = PairwiseAligner()
    aligner.mode = "global"
    aligner.match_score = 2.0
    aligner.mismatch_score = -1.0
    aligner.open_gap_score = -5.0
    aligner.extend_gap_score = -1.0
    alignment = aligner.align(reference_sequence, query_sequence)[0]
    coordinates = np.asarray(alignment.coordinates, dtype=int)
    rows: list[dict[str, object]] = []

    def append_variant(
        *,
        reference_position: int,
        query_position: int,
        reference_allele: str,
        query_allele: str,
        variant_type: str,
    ) -> bool:
        transition = (
            "Transition"
            if variant_type == "Substitution"
            and {reference_allele, query_allele} in ({"A", "G"}, {"C", "T"})
            else "Transversion"
            if variant_type == "Substitution"
            and reference_allele in "ACGT"
            and query_allele in "ACGT"
            else "Not applicable"
        )
        event_length = max(len(reference_allele.replace("-", "")), len(query_allele.replace("-", "")), 1)
        rows.append(
            {
                "query_genome": query.identifier,
                "reference_genome": reference.identifier,
                "position_1_based": max(reference_position, 1),
                "reference_position_1_based": max(reference_position, 1),
                "query_position_1_based": max(query_position, 1),
                "reference_base": reference_allele,
                "query_base": query_allele,
                "reference_allele": reference_allele,
                "query_allele": query_allele,
                "event_length": event_length,
                "variant_type": variant_type,
                "transition_transversion": transition,
                "alignment_method": "Needleman-Wunsch global alignment with affine gap penalties",
                "alignment_score": float(alignment.score),
            }
        )
        return limit is not None and len(rows) >= limit

    for segment in range(coordinates.shape[1] - 1):
        ref_start, ref_end = coordinates[0, segment : segment + 2]
        query_start, query_end = coordinates[1, segment : segment + 2]
        ref_advance = int(ref_end - ref_start)
        query_advance = int(query_end - query_start)
        if ref_advance and query_advance:
            ref_fragment = reference_sequence[ref_start:ref_end]
            query_fragment = query_sequence[query_start:query_end]
            if len(ref_fragment) != len(query_fragment):
                raise RuntimeError("Unexpected unequal aligned segment from the global aligner.")
            for offset, (reference_base, query_base) in enumerate(zip(ref_fragment, query_fragment)):
                if reference_base == query_base:
                    continue
                if append_variant(
                    reference_position=int(ref_start + offset + 1),
                    query_position=int(query_start + offset + 1),
                    reference_allele=reference_base,
                    query_allele=query_base,
                    variant_type="Substitution",
                ):
                    return pd.DataFrame(rows)
        elif ref_advance:
            deleted = reference_sequence[ref_start:ref_end]
            if append_variant(
                reference_position=int(ref_start + 1),
                query_position=int(query_start + 1),
                reference_allele=deleted,
                query_allele="-",
                variant_type="Deletion",
            ):
                return pd.DataFrame(rows)
        elif query_advance:
            inserted = query_sequence[query_start:query_end]
            if append_variant(
                reference_position=int(ref_start),
                query_position=int(query_start + 1),
                reference_allele="-",
                query_allele=inserted,
                variant_type="Insertion",
            ):
                return pd.DataFrame(rows)
    return pd.DataFrame(rows)

def pairwise_variant_summary(query: GenomeRecord, reference: GenomeRecord) -> dict[str, float | int | str]:
    variants = pairwise_variant_table(query, reference)
    compared = max(len(query.sequence), len(reference.sequence))
    substitutions = int((variants.get("variant_type", pd.Series(dtype=str)) == "Substitution").sum())
    insertion_events = variants[variants.get("variant_type", pd.Series(dtype=str)) == "Insertion"]
    deletion_events = variants[variants.get("variant_type", pd.Series(dtype=str)) == "Deletion"]
    insertions = int(pd.to_numeric(insertion_events.get("event_length"), errors="coerce").fillna(1).sum()) if not insertion_events.empty else 0
    deletions = int(pd.to_numeric(deletion_events.get("event_length"), errors="coerce").fillna(1).sum()) if not deletion_events.empty else 0
    aligned_differences = substitutions + insertions + deletions
    aligned_columns = max(len(reference.sequence), len(query.sequence)) + min(insertions, deletions)
    identity = 100 * max(aligned_columns - aligned_differences, 0) / max(aligned_columns, 1)
    return {
        "query_genome": query.identifier,
        "reference_genome": reference.identifier,
        "compared_bases": compared,
        "substitutions": substitutions,
        "insertions": insertions,
        "deletions": deletions,
        "positionwise_identity_percent": identity,
        "alignment_identity_percent": identity,
        "alignment_method": "Needleman-Wunsch global alignment with affine gap penalties",
        "length_difference_bp": len(query.sequence) - len(reference.sequence),
    }


def screen_markers_with_tolerance(
    records: Iterable[GenomeRecord],
    markers: pd.DataFrame,
    *,
    maximum_mismatches: int = 0,
) -> pd.DataFrame:
    required = {"marker", "sequence", "category"}
    if not required.issubset(markers.columns):
        raise ValueError("Marker table requires marker, sequence and category columns.")
    if maximum_mismatches < 0 or maximum_mismatches > 5:
        raise ValueError("Maximum mismatches must be between 0 and 5.")
    rows = []
    for record in records:
        genome = clean_dna(record.sequence)
        for marker_row in markers.itertuples(index=False):
            marker = clean_dna(getattr(marker_row, "sequence"))
            reverse_marker = reverse_complement(marker)
            best = None
            for strand, pattern in (("+", marker), ("-", reverse_marker)):
                if len(pattern) > len(genome):
                    continue
                for start in range(len(genome) - len(pattern) + 1):
                    window = genome[start : start + len(pattern)]
                    mismatches = sum(left != right for left, right in zip(window, pattern))
                    candidate = (mismatches, start + 1, strand)
                    if best is None or candidate < best:
                        best = candidate
                        if mismatches == 0:
                            break
                if best and best[0] == 0:
                    break
            detected = best is not None and best[0] <= maximum_mismatches
            rows.append(
                {
                    "genome_id": record.identifier,
                    "marker": str(getattr(marker_row, "marker")),
                    "category": str(getattr(marker_row, "category")),
                    "detected": detected,
                    "mismatches": int(best[0]) if best else None,
                    "position_1_based": int(best[1]) if detected and best else None,
                    "strand": best[2] if detected and best else None,
                    "marker_length": len(marker),
                    "evidence": f"Approximate match ({best[0]} mismatch{'es' if best and best[0] != 1 else ''})" if detected and best else "Not detected",
                }
            )
    return pd.DataFrame(rows)


def kmer_frequency_table(record: GenomeRecord, *, k: int = 4, top_n: int = 30) -> pd.DataFrame:
    sequence = clean_dna(record.sequence)
    if k < 2 or k > 8:
        raise ValueError("Composition k must be between 2 and 8.")
    counts: dict[str, int] = {}
    for index in range(len(sequence) - k + 1):
        token = sequence[index : index + k]
        if "N" in token:
            continue
        canonical = canonical_kmer(token)
        counts[canonical] = counts.get(canonical, 0) + 1
    total = sum(counts.values())
    rows = [
        {"kmer": token, "count": count, "frequency_percent": 100 * count / max(total, 1)}
        for token, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:top_n]
    ]
    return pd.DataFrame(rows)


def upgma_newick(distance: pd.DataFrame) -> str:
    if distance.empty or list(distance.index) != list(distance.columns):
        raise ValueError("Distance matrix must be square with matching labels.")
    clusters: dict[str, dict[str, object]] = {
        str(label): {"members": [str(label)], "newick": str(label), "height": 0.0} for label in distance.index
    }
    matrix = distance.copy().astype(float)
    while len(clusters) > 1:
        labels = list(clusters)
        best_pair = None
        best_distance = float("inf")
        for left_index, left in enumerate(labels):
            for right in labels[left_index + 1 :]:
                members_left = clusters[left]["members"]
                members_right = clusters[right]["members"]
                values = [matrix.loc[a, b] for a in members_left for b in members_right]
                value = float(np.mean(values))
                if value < best_distance:
                    best_distance = value
                    best_pair = (left, right)
        assert best_pair is not None
        left, right = best_pair
        new_height = best_distance / 2
        left_branch = max(new_height - float(clusters[left]["height"]), 0.0)
        right_branch = max(new_height - float(clusters[right]["height"]), 0.0)
        merged_name = f"{left}+{right}"
        merged = {
            "members": [*clusters[left]["members"], *clusters[right]["members"]],
            "newick": f"({clusters[left]['newick']}:{left_branch:.6f},{clusters[right]['newick']}:{right_branch:.6f})",
            "height": new_height,
        }
        del clusters[left]
        del clusters[right]
        clusters[merged_name] = merged
    return f"{next(iter(clusters.values()))['newick']};"


def gc_skew_profile(record: GenomeRecord, *, window: int = 500, step: int = 250) -> pd.DataFrame:
    sequence = clean_dna(record.sequence)
    window = max(50, min(int(window), len(sequence)))
    step = max(10, int(step))
    rows = []
    for start in range(0, max(len(sequence) - window + 1, 1), step):
        fragment = sequence[start : start + window]
        g = fragment.count("G")
        c = fragment.count("C")
        rows.append({"genome_id": record.identifier, "start": start + 1, "end": start + len(fragment), "gc_percent": 100 * (g + c) / max(len(fragment), 1), "gc_skew": (g - c) / max(g + c, 1)})
    return pd.DataFrame(rows)


def predict_orfs(record: GenomeRecord, *, minimum_amino_acids: int = 30) -> pd.DataFrame:
    sequence = clean_dna(record.sequence)
    stops = {"TAA", "TAG", "TGA"}
    rows = []
    for strand, dna in (("+", sequence), ("-", reverse_complement(sequence))):
        for frame in range(3):
            start_index = None
            for position in range(frame, len(dna) - 2, 3):
                codon = dna[position : position + 3]
                if start_index is None and codon == "ATG":
                    start_index = position
                elif start_index is not None and codon in stops:
                    amino_acids = (position - start_index) // 3
                    if amino_acids >= minimum_amino_acids:
                        if strand == "+":
                            genomic_start, genomic_end = start_index + 1, position + 3
                        else:
                            genomic_start, genomic_end = len(sequence) - (position + 3) + 1, len(sequence) - start_index
                        rows.append({"genome_id": record.identifier, "strand": strand, "frame": frame + 1, "start": genomic_start, "end": genomic_end, "length_nt": amino_acids * 3 + 3, "length_aa": amino_acids, "start_codon": "ATG", "stop_codon": codon})
                    start_index = None
    return pd.DataFrame(rows).sort_values("length_aa", ascending=False).reset_index(drop=True) if rows else pd.DataFrame(columns=["genome_id", "strand", "frame", "start", "end", "length_nt", "length_aa", "start_codon", "stop_codon"])


def window_reference_assignment(
    query: GenomeRecord,
    references: Iterable[GenomeRecord],
    *,
    k: int = 11,
    window: int = 1000,
    step: int = 500,
) -> pd.DataFrame:
    refs = list(references)
    reference_kmers = {record.identifier: kmer_set(record.sequence, k=k) for record in refs}
    sequence = clean_dna(query.sequence)
    window = max(k * 3, min(int(window), len(sequence)))
    rows = []
    for start in range(0, max(len(sequence) - window + 1, 1), max(int(step), 1)):
        fragment = sequence[start : start + window]
        query_kmers = kmer_set(fragment, k=k)
        scores = [(identifier, jaccard_similarity(query_kmers, kmers)) for identifier, kmers in reference_kmers.items()]
        scores.sort(key=lambda item: item[1], reverse=True)
        best = scores[0] if scores else ("unassigned", 0.0)
        second = scores[1] if len(scores) > 1 else ("none", 0.0)
        rows.append({"query_id": query.identifier, "start": start + 1, "end": start + len(fragment), "best_reference": best[0], "best_similarity": best[1], "second_reference": second[0], "assignment_margin": best[1] - second[1]})
    return pd.DataFrame(rows)


def assignment_bootstrap_stability(
    queries: Iterable[GenomeRecord],
    references: Iterable[GenomeRecord],
    *,
    k: int = 15,
    repeats: int = 100,
    fraction: float = 0.7,
    random_state: int = 42,
) -> pd.DataFrame:
    refs = list(references)
    ref_sets = {record.identifier: sorted(kmer_set(record.sequence, k=k)) for record in refs}
    rng = np.random.default_rng(random_state)
    rows = []
    for query in queries:
        query_values = sorted(kmer_set(query.sequence, k=k))
        winners: list[str] = []
        margins: list[float] = []
        for _ in range(max(int(repeats), 20)):
            sample_size = max(5, int(len(query_values) * fraction))
            sampled = set(rng.choice(query_values, size=min(sample_size, len(query_values)), replace=False).tolist())
            scores = sorted(((identifier, jaccard_similarity(sampled, set(values))) for identifier, values in ref_sets.items()), key=lambda item: item[1], reverse=True)
            if not scores:
                continue
            winners.append(scores[0][0])
            margins.append(scores[0][1] - (scores[1][1] if len(scores) > 1 else 0.0))
        winner = pd.Series(winners).value_counts()
        rows.append({"query_id": query.identifier, "consensus_reference": winner.index[0] if len(winner) else "unassigned", "bootstrap_support_percent": 100 * float(winner.iloc[0]) / max(len(winners), 1) if len(winner) else 0.0, "mean_assignment_margin": float(np.mean(margins)) if margins else 0.0, "bootstrap_repeats": len(winners)})
    return pd.DataFrame(rows)


def pangenome_kmer_presence(records: Iterable[GenomeRecord], *, k: int = 11, maximum_kmers: int = 5000) -> tuple[pd.DataFrame, pd.DataFrame]:
    items = list(records)
    sets = {record.identifier: kmer_set(record.sequence, k=k) for record in items}
    prevalence: dict[str, int] = {}
    for values in sets.values():
        for value in values:
            prevalence[value] = prevalence.get(value, 0) + 1
    selected = sorted(prevalence, key=lambda value: (-prevalence[value], value))[:maximum_kmers]
    matrix = pd.DataFrame({"kmer": selected, **{identifier: [int(kmer in values) for kmer in selected] for identifier, values in sets.items()}})
    summary = pd.DataFrame([{"category": "core", "kmer_count": sum(count == len(items) for count in prevalence.values())}, {"category": "shell", "kmer_count": sum(1 < count < len(items) for count in prevalence.values())}, {"category": "unique", "kmer_count": sum(count == 1 for count in prevalence.values())}, {"category": "total", "kmer_count": len(prevalence)}])
    return matrix, summary
