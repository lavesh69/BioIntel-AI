from __future__ import annotations

from collections import Counter
from io import StringIO
from math import log
from random import Random
from biointel.tools.runtime import resolve_tool, tool_available

import numpy as np
import pandas as pd
from Bio import Phylo
from Bio.Align import PairwiseAligner, substitution_matrices
from Bio.Phylo.BaseTree import Tree
from Bio.Phylo.TreeConstruction import DistanceMatrix, DistanceTreeConstructor

from biointel.genomics.phylogeny import (
    _alignment_kind,
    p_distance,
    validate_alignment,
)


def _pair_alignment(reference: str, query: str, kind: str) -> tuple[str, str]:
    aligner = PairwiseAligner(mode="global")
    aligner.open_gap_score = -5.0
    aligner.extend_gap_score = -0.5
    if kind == "protein":
        aligner.substitution_matrix = substitution_matrices.load("BLOSUM62")
    else:
        aligner.match_score = 2.0
        aligner.mismatch_score = -1.0
    alignment = aligner.align(reference, query)[0]
    coordinates = alignment.coordinates
    ref_parts: list[str] = []
    query_parts: list[str] = []
    for index in range(coordinates.shape[1] - 1):
        r0, r1 = int(coordinates[0, index]), int(coordinates[0, index + 1])
        q0, q1 = int(coordinates[1, index]), int(coordinates[1, index + 1])
        r_length, q_length = r1 - r0, q1 - q0
        if r_length and q_length:
            ref_parts.append(reference[r0:r1])
            query_parts.append(query[q0:q1])
        elif r_length:
            ref_parts.append(reference[r0:r1])
            query_parts.append("-" * r_length)
        elif q_length:
            ref_parts.append("-" * q_length)
            query_parts.append(query[q0:q1])
    return "".join(ref_parts), "".join(query_parts)


def progressive_star_alignment(sequences: dict[str, str]) -> dict[str, str]:
    """Create a deterministic in-process multiple alignment around the longest sequence.

    For large/publication workflows MAFFT/MUSCLE remains preferred; this fallback is fully
    local and useful when those executables are unavailable.
    """
    cleaned = {
        str(name): "".join(str(sequence).upper().split()) for name, sequence in sequences.items()
    }
    if len(cleaned) < 2:
        raise ValueError("At least two sequences are required.")
    reference_name = max(cleaned, key=lambda name: len(cleaned[name]))
    reference = cleaned[reference_name]
    kind = _alignment_kind(cleaned)
    representations: dict[str, tuple[dict[int, str], list[str]]] = {}
    maximum_insertions = [0] * (len(reference) + 1)
    for name, sequence in cleaned.items():
        if name == reference_name:
            insertions = {index: "" for index in range(len(reference) + 1)}
            characters = list(reference)
        else:
            aligned_reference, aligned_query = _pair_alignment(reference, sequence, kind)
            insertions = {index: "" for index in range(len(reference) + 1)}
            characters = ["-"] * len(reference)
            ref_position = 0
            for ref_char, query_char in zip(aligned_reference, aligned_query):
                if ref_char == "-":
                    insertions[ref_position] += query_char
                else:
                    if ref_position < len(reference):
                        characters[ref_position] = query_char
                    ref_position += 1
        for boundary, inserted in insertions.items():
            maximum_insertions[boundary] = max(maximum_insertions[boundary], len(inserted))
        representations[name] = (insertions, characters)
    aligned: dict[str, str] = {}
    for name, (insertions, characters) in representations.items():
        pieces: list[str] = []
        for boundary in range(len(reference) + 1):
            inserted = insertions.get(boundary, "")
            pieces.append(inserted + "-" * (maximum_insertions[boundary] - len(inserted)))
            if boundary < len(reference):
                pieces.append(characters[boundary])
        aligned[name] = "".join(pieces)
    validate_alignment(aligned)
    return aligned


def trim_alignment(
    sequences: dict[str, str],
    *,
    maximum_gap_fraction: float = 0.5,
    minimum_major_fraction: float = 0.0,
) -> tuple[dict[str, str], pd.DataFrame]:
    rows = validate_alignment(sequences)
    if not 0 <= maximum_gap_fraction <= 1 or not 0 <= minimum_major_fraction <= 1:
        raise ValueError("Alignment trimming fractions must be between zero and one.")
    names = list(rows)
    kept_columns: list[int] = []
    audit = []
    for index, column in enumerate(zip(*rows.values()), start=1):
        gap_fraction = sum(value in {"-", "?"} for value in column) / len(column)
        informative = [value for value in column if value not in {"-", "?", "N", "X"}]
        counts = Counter(informative)
        major_fraction = counts.most_common(1)[0][1] / len(informative) if informative else 0.0
        keep = gap_fraction <= maximum_gap_fraction and major_fraction >= minimum_major_fraction
        if keep:
            kept_columns.append(index - 1)
        audit.append(
            {
                "position": index,
                "gap_fraction": gap_fraction,
                "major_fraction": major_fraction,
                "kept": keep,
            }
        )
    if not kept_columns:
        raise ValueError("Alignment trimming removed every column.")
    trimmed = {name: "".join(rows[name][index] for index in kept_columns) for name in names}
    return trimmed, pd.DataFrame(audit)


def evolutionary_distance(left: str, right: str, *, model: str = "p-distance") -> float:
    p = p_distance(left, right)
    model = model.lower()
    if model == "p-distance":
        return p
    if model == "jukes-cantor":
        if p >= 0.75:
            return 10.0
        return -0.75 * log(max(1.0 - 4.0 * p / 3.0, 1e-12))
    if model == "poisson":
        if p >= 1.0:
            return 10.0
        return -log(max(1.0 - p, 1e-12))
    raise ValueError(f"Unsupported distance model: {model}")


def model_distance_matrix(sequences: dict[str, str], *, model: str = "p-distance") -> pd.DataFrame:
    rows = validate_alignment(sequences)
    names = list(rows)
    matrix = pd.DataFrame(0.0, index=names, columns=names)
    for left_index, left in enumerate(names):
        for right in names[left_index + 1 :]:
            value = evolutionary_distance(rows[left], rows[right], model=model)
            matrix.loc[left, right] = value
            matrix.loc[right, left] = value
    return matrix


def _distance_matrix_biopython(matrix: pd.DataFrame) -> DistanceMatrix:
    names = matrix.index.astype(str).tolist()
    lower = [
        [float(matrix.loc[names[i], names[j]]) for j in range(i + 1)] for i in range(len(names))
    ]
    return DistanceMatrix(names, lower)


def build_tree(
    sequences: dict[str, str],
    *,
    method: str = "neighbor-joining",
    model: str = "p-distance",
) -> tuple[Tree, pd.DataFrame]:
    matrix = model_distance_matrix(sequences, model=model)
    constructor = DistanceTreeConstructor()
    distance = _distance_matrix_biopython(matrix)
    normalized = method.lower()
    if normalized in {"neighbor-joining", "nj"}:
        tree = constructor.nj(distance)
    elif normalized == "upgma":
        tree = constructor.upgma(distance)
    else:
        raise ValueError("Tree method must be neighbor-joining or UPGMA.")
    return tree, matrix


def _clade_key(clade, all_terminals: frozenset[str]) -> frozenset[str] | None:
    members = frozenset(terminal.name for terminal in clade.get_terminals())
    if len(members) <= 1 or members == all_terminals:
        return None
    complement = all_terminals - members
    return members if len(members) <= len(complement) else complement


def bootstrap_tree(
    sequences: dict[str, str],
    *,
    replicates: int = 100,
    method: str = "neighbor-joining",
    model: str = "p-distance",
    random_state: int = 42,
) -> tuple[Tree, pd.DataFrame]:
    rows = validate_alignment(sequences)
    base_tree, _ = build_tree(rows, method=method, model=model)
    names = list(rows)
    length = len(next(iter(rows.values())))
    rng = Random(random_state)
    all_terminals = frozenset(names)
    counts: Counter[frozenset[str]] = Counter()
    for _ in range(max(10, int(replicates))):
        columns = [rng.randrange(length) for _ in range(length)]
        sampled = {name: "".join(rows[name][index] for index in columns) for name in names}
        tree, _ = build_tree(sampled, method=method, model=model)
        for clade in tree.get_nonterminals():
            key = _clade_key(clade, all_terminals)
            if key is not None:
                counts[key] += 1
    support_rows = []
    for clade in base_tree.get_nonterminals():
        key = _clade_key(clade, all_terminals)
        if key is None:
            continue
        support = 100 * counts[key] / max(int(replicates), 1)
        clade.confidence = support
        support_rows.append({"clade": ", ".join(sorted(key)), "bootstrap_support": support})
    return base_tree, pd.DataFrame(support_rows).sort_values("bootstrap_support", ascending=False)


def root_tree(tree: Tree, *, outgroup: str | None = None, midpoint: bool = False) -> Tree:
    if outgroup:
        targets = [terminal for terminal in tree.get_terminals() if terminal.name == outgroup]
        if not targets:
            raise ValueError(f"Outgroup {outgroup!r} was not found in the tree.")
        tree.root_with_outgroup(targets[0])
    elif midpoint:
        tree.root_at_midpoint()
    return tree


def tree_newick(tree: Tree) -> str:
    handle = StringIO()
    Phylo.write(tree, handle, "newick")
    return handle.getvalue().strip()


def codon_partition_audit(sequences: dict[str, str]) -> pd.DataFrame:
    rows = validate_alignment(sequences)
    if any(len(sequence.replace("-", "")) % 3 for sequence in rows.values()):
        raise ValueError(
            "Codon partitioning requires ungapped sequence lengths divisible by three."
        )
    audit = []
    for partition in range(3):
        values = [sequence[partition::3] for sequence in rows.values()]
        pairwise = []
        for left_index, left in enumerate(values):
            for right in values[left_index + 1 :]:
                pairwise.append(p_distance(left, right))
        audit.append(
            {
                "codon_position": partition + 1,
                "sites": len(values[0]) if values else 0,
                "mean_p_distance": float(np.mean(pairwise)) if pairwise else 0.0,
            }
        )
    return pd.DataFrame(audit)


def external_phylogeny_tools() -> pd.DataFrame:
    tools = {
        "MAFFT": "mafft",
        "MUSCLE": "muscle",
        "IQ-TREE": "iqtree2",
        "FastTree": "FastTree",
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
