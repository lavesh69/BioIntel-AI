from __future__ import annotations

from Bio.Align import PairwiseAligner, substitution_matrices


def _aligned_strings(alignment: object, query: str, target: str) -> tuple[str, str]:
    coordinates = alignment.coordinates
    query_parts: list[str] = []
    target_parts: list[str] = []

    for index in range(coordinates.shape[1] - 1):
        q0 = int(coordinates[0, index])
        q1 = int(coordinates[0, index + 1])
        t0 = int(coordinates[1, index])
        t1 = int(coordinates[1, index + 1])
        query_length = q1 - q0
        target_length = t1 - t0

        if query_length and target_length:
            query_parts.append(query[q0:q1])
            target_parts.append(target[t0:t1])
        elif query_length:
            query_parts.append(query[q0:q1])
            target_parts.append("-" * query_length)
        elif target_length:
            query_parts.append("-" * target_length)
            target_parts.append(target[t0:t1])

    return "".join(query_parts), "".join(target_parts)


def align_sequences(
    query: str,
    target: str,
    sequence_type: str,
    mode: str = "global",
    match_score: float = 2.0,
    mismatch_score: float = -1.0,
    gap_open: float = -2.0,
    gap_extend: float = -0.5,
    substitution_matrix: str = "BLOSUM62",
) -> dict[str, object]:
    """Align compatible sequences and return explicit alignment metrics."""

    if not query or not target:
        raise ValueError("Both sequences are required for alignment.")
    if mode not in {"global", "local"}:
        raise ValueError("mode must be global or local")

    aligner = PairwiseAligner()
    aligner.mode = mode
    aligner.open_gap_score = gap_open
    aligner.extend_gap_score = gap_extend

    protein = sequence_type.lower() == "protein"
    matrix = None
    if protein:
        matrix = substitution_matrices.load(substitution_matrix)
        aligner.substitution_matrix = matrix
    else:
        aligner.match_score = match_score
        aligner.mismatch_score = mismatch_score

    alignments = aligner.align(query, target)
    if len(alignments) == 0:
        raise ValueError("No alignment could be generated.")

    alignment = alignments[0]
    aligned_query, aligned_target = _aligned_strings(alignment, query, target)

    identities = 0
    similarities = 0
    substitutions = 0
    gap_columns = 0
    query_aligned = 0
    target_aligned = 0
    mismatch_positions: list[int] = []

    for position, (query_char, target_char) in enumerate(
        zip(aligned_query, aligned_target), start=1
    ):
        if query_char == "-" or target_char == "-":
            gap_columns += 1
            continue

        query_aligned += 1
        target_aligned += 1
        if query_char == target_char:
            identities += 1
            similarities += 1
        else:
            substitutions += 1
            mismatch_positions.append(position)
            if protein and matrix is not None:
                try:
                    similarities += int(float(matrix[query_char, target_char]) > 0)
                except (IndexError, KeyError, ValueError):
                    continue

    compared = identities + substitutions
    return {
        "score": float(alignment.score),
        "alignment_length": len(aligned_query),
        "identities": identities,
        "substitutions": substitutions,
        "gap_columns": gap_columns,
        "identity_percent": identities / compared * 100 if compared else 0.0,
        "similarity_percent": (similarities / compared * 100 if compared else None),
        "query_coverage_percent": query_aligned / len(query) * 100,
        "target_coverage_percent": target_aligned / len(target) * 100,
        "mismatch_positions": mismatch_positions,
        "aligned_query": aligned_query,
        "aligned_target": aligned_target,
        "formatted_alignment": str(alignment),
    }
