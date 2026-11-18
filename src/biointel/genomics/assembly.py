from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class AssemblyMetrics:
    sequences: int
    total_bases: int
    minimum_length: int
    maximum_length: int
    mean_length: float
    median_length: float
    n50: int
    l50: int
    n90: int
    l90: int
    gc_percent: float
    ambiguous_percent: float


def _nx(lengths: list[int], fraction: float) -> tuple[int, int]:
    target = sum(lengths) * fraction
    running = 0
    for index, length in enumerate(sorted(lengths, reverse=True), 1):
        running += length
        if running >= target:
            return length, index
    return 0, 0


def assembly_metrics(sequences: Iterable[str]) -> AssemblyMetrics:
    rows = ["".join(str(s).split()).upper() for s in sequences if str(s).strip()]
    if not rows:
        raise ValueError("At least one sequence is required.")
    if any(any(base not in "ACGTN" for base in row) for row in rows):
        raise ValueError("Assembly contains unsupported symbols.")
    lengths = sorted(len(row) for row in rows)
    n50, l50 = _nx(lengths, 0.5)
    n90, l90 = _nx(lengths, 0.9)
    total = sum(lengths)
    gc = sum(row.count("G") + row.count("C") for row in rows)
    ambiguous = sum(row.count("N") for row in rows)
    mid = len(lengths) // 2
    median = lengths[mid] if len(lengths) % 2 else (lengths[mid - 1] + lengths[mid]) / 2
    return AssemblyMetrics(
        len(rows),
        total,
        min(lengths),
        max(lengths),
        round(total / len(rows), 3),
        round(median, 3),
        n50,
        l50,
        n90,
        l90,
        round(100 * gc / total, 3),
        round(100 * ambiguous / total, 4),
    )


def metrics_dict(result: AssemblyMetrics) -> dict:
    return asdict(result)
