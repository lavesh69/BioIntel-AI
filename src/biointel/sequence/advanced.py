from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import log2
from typing import Iterable

import pandas as pd
from Bio.Align import PairwiseAligner
from Bio.Seq import Seq

from biointel.sequence.alignment import align_sequences
from biointel.sequence.motif_analysis import find_exact_motif, find_iupac_motif
from biointel.sequence.parser import ParsedSequence


@dataclass(frozen=True)
class SequenceQcProfile:
    length: int
    alphabet_size: int
    entropy_bits: float
    dust_like_fraction: float
    longest_homopolymer: int
    ambiguous_fraction: float
    reverse_complement_palindrome_fraction: float


def reverse_complement(sequence: str) -> str:
    return str(Seq("".join(str(sequence).upper().split())).reverse_complement())


def sequence_qc_profile(sequence: str, *, window: int = 12) -> SequenceQcProfile:
    cleaned = "".join(str(sequence).upper().split())
    if not cleaned:
        raise ValueError("Sequence cannot be empty.")
    counts = Counter(cleaned)
    entropy = -sum((count / len(cleaned)) * log2(count / len(cleaned)) for count in counts.values())
    longest = 1
    current = 1
    for left, right in zip(cleaned, cleaned[1:]):
        current = current + 1 if left == right else 1
        longest = max(longest, current)
    windows = [
        cleaned[index : index + window] for index in range(max(1, len(cleaned) - window + 1))
    ]
    low_complexity = 0
    palindromic = 0
    for item in windows:
        if not item:
            continue
        item_counts = Counter(item)
        if max(item_counts.values()) / len(item) >= 0.6 or len(item_counts) <= 2:
            low_complexity += 1
        if set(item).issubset(set("ACGTRYSWKMBDHVN")) and item == reverse_complement(item):
            palindromic += 1
    ambiguity_symbols = set("NXRYSWKMBDHV?")
    ambiguous = sum(char in ambiguity_symbols for char in cleaned)
    return SequenceQcProfile(
        length=len(cleaned),
        alphabet_size=len(counts),
        entropy_bits=entropy,
        dust_like_fraction=low_complexity / max(len(windows), 1),
        longest_homopolymer=longest,
        ambiguous_fraction=ambiguous / len(cleaned),
        reverse_complement_palindrome_fraction=palindromic / max(len(windows), 1),
    )


def motif_search_both_strands(
    sequence: str,
    motif: str,
    *,
    mode: str = "iupac",
    strands: str = "both",
) -> pd.DataFrame:
    if strands not in {"forward", "reverse", "both"}:
        raise ValueError("strands must be forward, reverse or both.")
    sequence = "".join(str(sequence).upper().split())
    search = find_iupac_motif if mode == "iupac" else find_exact_motif
    rows: list[dict[str, object]] = []
    if strands in {"forward", "both"}:
        for row in search(sequence, motif):
            rows.append({**row, "strand": "+"})
    if strands in {"reverse", "both"}:
        reverse = reverse_complement(sequence)
        for row in search(reverse, motif):
            original_start = len(sequence) - int(row["end"]) + 1
            original_end = len(sequence) - int(row["start"]) + 1
            rows.append(
                {
                    **row,
                    "start": original_start,
                    "end": original_end,
                    "strand": "-",
                }
            )
    if not rows:
        return pd.DataFrame(
            columns=["match", "start", "end", "strand", "matched_sequence", "context"]
        )
    frame = pd.DataFrame(rows).sort_values(["start", "strand"]).reset_index(drop=True)
    frame["match"] = range(1, len(frame) + 1)
    return frame


def auto_orient_alignment(
    query: str,
    target: str,
    *,
    sequence_type: str,
    mode: str = "global",
    **kwargs: object,
) -> dict[str, object]:
    direct = align_sequences(query, target, sequence_type, mode=mode, **kwargs)
    if sequence_type.lower() not in {"dna", "rna", "nucleotide"}:
        direct["orientation"] = "forward"
        return direct
    reverse_query = reverse_complement(query.replace("U", "T"))
    reverse = align_sequences(reverse_query, target.replace("U", "T"), "dna", mode=mode, **kwargs)
    if float(reverse["score"]) > float(direct["score"]):
        reverse["orientation"] = "reverse-complement"
        reverse["oriented_query"] = reverse_query
        return reverse
    direct["orientation"] = "forward"
    direct["oriented_query"] = query
    return direct


def semiglobal_alignment(
    query: str,
    target: str,
    *,
    match_score: float = 2.0,
    mismatch_score: float = -1.0,
    gap_open: float = -2.0,
    gap_extend: float = -0.5,
) -> dict[str, object]:
    if not query or not target:
        raise ValueError("Both sequences are required.")
    aligner = PairwiseAligner(mode="global")
    aligner.match_score = match_score
    aligner.mismatch_score = mismatch_score
    aligner.open_gap_score = gap_open
    aligner.extend_gap_score = gap_extend
    aligner.open_left_insertion_score = 0.0
    aligner.extend_left_insertion_score = 0.0
    aligner.open_right_insertion_score = 0.0
    aligner.extend_right_insertion_score = 0.0
    aligner.open_left_deletion_score = 0.0
    aligner.extend_left_deletion_score = 0.0
    aligner.open_right_deletion_score = 0.0
    aligner.extend_right_deletion_score = 0.0
    alignments = aligner.align(query, target)
    if len(alignments) == 0:
        raise ValueError("No semi-global alignment could be produced.")
    alignment = alignments[0]
    coordinates = alignment.coordinates
    aligned_query = str(alignment[0])
    aligned_target = str(alignment[1])
    if len(aligned_query) != len(aligned_target):
        raise RuntimeError("Semi-global alignment returned inconsistent aligned strings.")
    alignment_length = len(aligned_query)
    identities = sum(
        left == right and left != "-"
        for left, right in zip(aligned_query, aligned_target, strict=True)
    )
    gap_columns = sum(
        left == "-" or right == "-"
        for left, right in zip(aligned_query, aligned_target, strict=True)
    )
    mismatch_positions = [
        index
        for index, (left, right) in enumerate(
            zip(aligned_query, aligned_target, strict=True), start=1
        )
        if left != right and left != "-" and right != "-"
    ]
    comparable = max(alignment_length - gap_columns, 1)
    return {
        "score": float(alignment.score),
        "formatted_alignment": str(alignment),
        "aligned_query": aligned_query,
        "aligned_target": aligned_target,
        "alignment_length": alignment_length,
        "identities": identities,
        "identity_percent": 100.0 * identities / comparable,
        "similarity_percent": None,
        "gap_columns": gap_columns,
        "query_coverage_percent": 100.0 * sum(c != "-" for c in aligned_query) / max(len(query), 1),
        "target_coverage_percent": 100.0 * sum(c != "-" for c in aligned_target) / max(len(target), 1),
        "mismatch_positions": mismatch_positions,
        "query_start": int(coordinates[0].min()) + 1,
        "query_end": int(coordinates[0].max()),
        "target_start": int(coordinates[1].min()) + 1,
        "target_end": int(coordinates[1].max()),
        "mode": "semi-global",
    }


def alignment_event_table(aligned_query: str, aligned_target: str) -> pd.DataFrame:
    if len(aligned_query) != len(aligned_target):
        raise ValueError("Aligned strings must have equal length.")
    rows: list[dict[str, object]] = []
    q_pos = 0
    t_pos = 0
    index = 0
    while index < len(aligned_query):
        q_char = aligned_query[index]
        t_char = aligned_target[index]
        if q_char != "-":
            q_pos += 1
        if t_char != "-":
            t_pos += 1
        if q_char == t_char:
            index += 1
            continue
        event_start = index
        start_q = q_pos if q_char != "-" else q_pos + 1
        start_t = t_pos if t_char != "-" else t_pos + 1
        query_allele: list[str] = []
        target_allele: list[str] = []
        event_type = "substitution"
        while index < len(aligned_query) and aligned_query[index] != aligned_target[index]:
            qc = aligned_query[index]
            tc = aligned_target[index]
            if qc == "-":
                event_type = "insertion_in_target"
            elif tc == "-":
                event_type = "deletion_in_target"
            elif event_type != "substitution":
                event_type = "complex"
            if qc != "-":
                query_allele.append(qc)
            if tc != "-":
                target_allele.append(tc)
            index += 1
            if index < len(aligned_query):
                if aligned_query[index] != "-":
                    q_pos += 1
                if aligned_target[index] != "-":
                    t_pos += 1
        rows.append(
            {
                "event": len(rows) + 1,
                "alignment_start": event_start + 1,
                "query_start": start_q,
                "target_start": start_t,
                "event_type": event_type,
                "query_allele": "".join(query_allele) or "-",
                "target_allele": "".join(target_allele) or "-",
                "length": max(len(query_allele), len(target_allele)),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "event",
            "alignment_start",
            "query_start",
            "target_start",
            "event_type",
            "query_allele",
            "target_allele",
            "length",
        ],
    )


def deduplicate_records(
    records: Iterable[ParsedSequence],
) -> tuple[pd.DataFrame, list[ParsedSequence]]:
    seen: dict[str, str] = {}
    unique: list[ParsedSequence] = []
    rows: list[dict[str, object]] = []
    for record in records:
        sequence = "".join(record.sequence.upper().split())
        representative = seen.get(sequence)
        if representative is None:
            seen[sequence] = record.header
            unique.append(record)
            representative = record.header
            duplicate = False
        else:
            duplicate = True
        rows.append(
            {
                "header": record.header,
                "length": len(sequence),
                "duplicate": duplicate,
                "representative": representative,
            }
        )
    return pd.DataFrame(rows), unique


def near_duplicate_clusters(
    records: Iterable[ParsedSequence], *, identity_threshold: float = 0.98, k: int = 7
) -> pd.DataFrame:
    """Cluster records by exact k-mer Jaccard similarity using an inverted index.

    The former implementation compared every pair and built set unions repeatedly,
    which made the default 800-record page appear frozen. Candidate pairs are now
    generated only when records share at least one k-mer; the final Jaccard decision
    remains mathematically identical to the brute-force calculation.
    """

    records = list(records)
    if not 0 < identity_threshold <= 1:
        raise ValueError("identity_threshold must be in (0, 1].")
    if k < 1:
        raise ValueError("k must be at least 1.")

    fingerprints: list[set[str]] = []
    for record in records:
        sequence = "".join(str(record.sequence).upper().split())
        if not sequence:
            fingerprints.append(set())
        elif len(sequence) < k:
            fingerprints.append({sequence})
        else:
            fingerprints.append({sequence[i : i + k] for i in range(len(sequence) - k + 1)})

    parent = list(range(len(records)))

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[b] = a

    inverted: dict[str, list[int]] = {}
    empty_indices: list[int] = []
    for right, right_fp in enumerate(fingerprints):
        if not right_fp:
            for left in empty_indices:
                if identity_threshold <= 1.0:
                    union(left, right)
            empty_indices.append(right)
            continue

        intersections: Counter[int] = Counter()
        for token in right_fp:
            for left in inverted.get(token, ()):  # only possible non-zero intersections
                intersections[left] += 1
        for left, intersection_size in intersections.items():
            left_fp = fingerprints[left]
            union_size = len(left_fp) + len(right_fp) - intersection_size
            similarity = intersection_size / union_size if union_size else 1.0
            if similarity >= identity_threshold:
                union(left, right)
        for token in right_fp:
            inverted.setdefault(token, []).append(right)

    roots: dict[int, int] = {}
    rows = []
    for index, record in enumerate(records):
        root = find(index)
        cluster = roots.setdefault(root, len(roots) + 1)
        rows.append({"header": record.header, "cluster": cluster, "length": len(record.sequence)})
    frame = pd.DataFrame(rows)
    if not frame.empty:
        counts = frame["cluster"].value_counts()
        frame["cluster_size"] = frame["cluster"].map(counts)
    return frame


def circular_restriction_fragments(length: int, cut_positions: Iterable[int]) -> list[int]:
    positions = sorted(
        {int(position) for position in cut_positions if 1 <= int(position) <= length}
    )
    if length <= 0:
        raise ValueError("Sequence length must be positive.")
    if not positions:
        return [length]
    fragments = []
    for left, right in zip(positions, positions[1:]):
        fragments.append(right - left)
    fragments.append(length - positions[-1] + positions[0])
    return sorted(fragments, reverse=True)
