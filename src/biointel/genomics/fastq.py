from __future__ import annotations

import gzip
from collections import Counter
from dataclasses import asdict, dataclass
from io import TextIOBase
from typing import Iterable, Iterator


@dataclass(frozen=True)
class FastqRecord:
    identifier: str
    sequence: str
    quality: str


@dataclass(frozen=True)
class FastqQcResult:
    reads: int
    bases: int
    minimum_length: int
    maximum_length: int
    mean_length: float
    mean_gc_percent: float
    mean_quality: float
    q20_percent: float
    q30_percent: float
    n_percent: float
    duplicate_percent: float
    adapter_hits: dict[str, int]
    per_cycle_quality: list[float]
    per_cycle_gc_percent: list[float]
    quality_histogram: dict[int, int]
    length_histogram: dict[int, int]
    overrepresented_sequences: list[dict[str, int | float | str]]
    warnings: list[str]


@dataclass(frozen=True)
class PairedEndQcResult:
    pairs: int
    synchronized_pairs: int
    mismatched_identifiers: int
    orphan_r1: int
    orphan_r2: int
    r1: FastqQcResult
    r2: FastqQcResult
    warnings: list[str]


DEFAULT_ADAPTERS = {
    "Illumina universal": "AGATCGGAAGAG",
    "Nextera": "CTGTCTCTTATA",
    "Small RNA": "TGGAATTCTCGG",
}


def decode_fastq_bytes(payload: bytes, *, filename: str = "") -> str:
    """Decode plain or gzip-compressed FASTQ bytes without trusting the extension."""
    is_gzip = payload[:2] == b"\x1f\x8b" or filename.lower().endswith(".gz")
    raw = gzip.decompress(payload) if is_gzip else payload
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("FASTQ must be UTF-8 text (optionally gzip-compressed).") from exc


def _canonical_read_id(identifier: str) -> str:
    value = identifier.strip().split()[0]
    if value.endswith("/1") or value.endswith("/2"):
        value = value[:-2]
    return value


def iter_fastq_lines(
    lines: Iterable[str], *, max_records: int = 1_000_000
) -> Iterator[FastqRecord]:
    iterator = iter(lines)
    record_index = 0
    while True:
        try:
            header = next(iterator).rstrip("\r\n")
        except StopIteration:
            break
        if not header.strip():
            continue
        try:
            sequence = next(iterator).rstrip("\r\n")
            plus = next(iterator).rstrip("\r\n")
            quality = next(iterator).rstrip("\r\n")
        except StopIteration as exc:
            raise ValueError("FASTQ must contain complete four-line records.") from exc
        if record_index >= max_records:
            raise ValueError(f"FASTQ exceeds the {max_records:,}-record safety limit.")
        if not header.startswith("@") or not plus.startswith("+"):
            raise ValueError(f"Invalid FASTQ record near record {record_index + 1}.")
        sequence = "".join(sequence.split()).upper()
        if not sequence or any(base not in "ACGTN" for base in sequence):
            raise ValueError(f"Invalid nucleotide symbols near record {record_index + 1}.")
        if len(sequence) != len(quality):
            raise ValueError(f"Sequence/quality length mismatch near record {record_index + 1}.")
        if any(ord(char) < 33 or ord(char) > 126 for char in quality):
            raise ValueError(f"Invalid FASTQ quality encoding near record {record_index + 1}.")
        record_index += 1
        yield FastqRecord(header[1:].strip() or f"read_{record_index}", sequence, quality)
    if record_index == 0:
        raise ValueError("No FASTQ records were found.")


def parse_fastq(text: str, *, max_records: int = 200_000) -> list[FastqRecord]:
    return list(iter_fastq_lines(text.splitlines(keepends=True), max_records=max_records))


def parse_fastq_file(handle: TextIOBase, *, max_records: int = 1_000_000) -> list[FastqRecord]:
    return list(iter_fastq_lines(handle, max_records=max_records))


def phred_scores(quality: str, offset: int = 33) -> list[int]:
    return [ord(char) - offset for char in quality]


def fastq_qc(
    records: Iterable[FastqRecord], adapters: dict[str, str] | None = None
) -> FastqQcResult:
    rows = list(records)
    if not rows:
        raise ValueError("At least one FASTQ record is required.")
    adapters = adapters or DEFAULT_ADAPTERS
    lengths = [len(row.sequence) for row in rows]
    total_bases = sum(lengths)
    sequence_counts = Counter(row.sequence for row in rows)
    all_scores = [score for row in rows for score in phred_scores(row.quality)]
    gc = sum(row.sequence.count("G") + row.sequence.count("C") for row in rows)
    n_count = sum(row.sequence.count("N") for row in rows)
    duplicates = sum(count - 1 for count in sequence_counts.values() if count > 1)
    max_len = max(lengths)
    per_q: list[float] = []
    per_gc: list[float] = []
    for position in range(max_len):
        cycle = [row for row in rows if len(row.sequence) > position]
        cycle_scores = [ord(row.quality[position]) - 33 for row in cycle]
        per_q.append(round(sum(cycle_scores) / len(cycle_scores), 3))
        per_gc.append(
            round(100 * sum(row.sequence[position] in "GC" for row in cycle) / len(cycle), 3)
        )
    adapter_hits = {
        name: sum(sequence.upper() in row.sequence for row in rows)
        for name, sequence in adapters.items()
    }
    mean_q = sum(all_scores) / max(len(all_scores), 1)
    q20 = 100 * sum(score >= 20 for score in all_scores) / len(all_scores)
    q30 = 100 * sum(score >= 30 for score in all_scores) / len(all_scores)
    duplicate_percent = 100 * duplicates / len(rows)
    warnings: list[str] = []
    if mean_q < 25:
        warnings.append("Mean read quality is below Q25.")
    if q20 < 80:
        warnings.append("Less than 80% of bases are Q20 or better.")
    if n_count / max(total_bases, 1) > 0.01:
        warnings.append("More than 1% of bases are ambiguous N calls.")
    if duplicate_percent > 20:
        warnings.append("Duplicate read fraction exceeds 20%.")
    if any(adapter_hits.values()):
        warnings.append("Known adapter sequence was detected.")
    overrepresented = [
        {
            "sequence": sequence,
            "count": count,
            "percent": round(100 * count / len(rows), 4),
        }
        for sequence, count in sequence_counts.most_common(20)
        if count > 1
    ]
    return FastqQcResult(
        reads=len(rows),
        bases=total_bases,
        minimum_length=min(lengths),
        maximum_length=max(lengths),
        mean_length=round(sum(lengths) / len(lengths), 3),
        mean_gc_percent=round(100 * gc / total_bases, 3),
        mean_quality=round(mean_q, 3),
        q20_percent=round(q20, 3),
        q30_percent=round(q30, 3),
        n_percent=round(100 * n_count / total_bases, 4),
        duplicate_percent=round(duplicate_percent, 3),
        adapter_hits=adapter_hits,
        per_cycle_quality=per_q,
        per_cycle_gc_percent=per_gc,
        quality_histogram=dict(sorted(Counter(all_scores).items())),
        length_histogram=dict(sorted(Counter(lengths).items())),
        overrepresented_sequences=overrepresented,
        warnings=warnings,
    )


def paired_end_qc(
    r1_records: Iterable[FastqRecord],
    r2_records: Iterable[FastqRecord],
    *,
    adapters: dict[str, str] | None = None,
) -> PairedEndQcResult:
    r1 = list(r1_records)
    r2 = list(r2_records)
    pair_count = min(len(r1), len(r2))
    mismatches = sum(
        _canonical_read_id(left.identifier) != _canonical_read_id(right.identifier)
        for left, right in zip(r1, r2)
    )
    warnings: list[str] = []
    if len(r1) != len(r2):
        warnings.append("R1 and R2 contain different numbers of reads.")
    if mismatches:
        warnings.append(f"{mismatches:,} paired identifiers do not match.")
    return PairedEndQcResult(
        pairs=pair_count,
        synchronized_pairs=pair_count - mismatches,
        mismatched_identifiers=mismatches,
        orphan_r1=max(len(r1) - len(r2), 0),
        orphan_r2=max(len(r2) - len(r1), 0),
        r1=fastq_qc(r1, adapters),
        r2=fastq_qc(r2, adapters),
        warnings=warnings,
    )


def trim_record(
    record: FastqRecord,
    *,
    adapter: str | None = None,
    minimum_quality: int = 20,
    minimum_length: int = 30,
) -> FastqRecord | None:
    sequence = record.sequence
    quality = record.quality
    if adapter:
        index = sequence.find(adapter.upper())
        if index >= 0:
            sequence, quality = sequence[:index], quality[:index]
    scores = phred_scores(quality)
    end = len(scores)
    while end > 0 and scores[end - 1] < minimum_quality:
        end -= 1
    start = 0
    while start < end and scores[start] < minimum_quality:
        start += 1
    sequence, quality = sequence[start:end], quality[start:end]
    if len(sequence) < minimum_length:
        return None
    return FastqRecord(record.identifier, sequence, quality)


def trim_fastq(
    records: Iterable[FastqRecord], **kwargs: object
) -> tuple[list[FastqRecord], dict[str, int]]:
    rows = list(records)
    output: list[FastqRecord] = []
    dropped = 0
    for record in rows:
        trimmed = trim_record(record, **kwargs)
        if trimmed is None:
            dropped += 1
        else:
            output.append(trimmed)
    return output, {
        "input_reads": len(rows),
        "retained_reads": len(output),
        "dropped_reads": dropped,
    }


def trim_paired_fastq(
    r1_records: Iterable[FastqRecord],
    r2_records: Iterable[FastqRecord],
    **kwargs: object,
) -> tuple[list[FastqRecord], list[FastqRecord], dict[str, int]]:
    r1 = list(r1_records)
    r2 = list(r2_records)
    out_r1: list[FastqRecord] = []
    out_r2: list[FastqRecord] = []
    identifier_mismatches = 0
    dropped_pairs = 0
    for left, right in zip(r1, r2):
        if _canonical_read_id(left.identifier) != _canonical_read_id(right.identifier):
            identifier_mismatches += 1
            dropped_pairs += 1
            continue
        left_trimmed = trim_record(left, **kwargs)
        right_trimmed = trim_record(right, **kwargs)
        if left_trimmed is None or right_trimmed is None:
            dropped_pairs += 1
            continue
        out_r1.append(left_trimmed)
        out_r2.append(right_trimmed)
    return (
        out_r1,
        out_r2,
        {
            "input_pairs": min(len(r1), len(r2)),
            "retained_pairs": len(out_r1),
            "dropped_pairs": dropped_pairs,
            "identifier_mismatches": identifier_mismatches,
            "orphan_r1": max(len(r1) - len(r2), 0),
            "orphan_r2": max(len(r2) - len(r1), 0),
        },
    )


def fastq_text(records: Iterable[FastqRecord]) -> str:
    return "".join(
        f"@{record.identifier}\n{record.sequence}\n+\n{record.quality}\n" for record in records
    )


def qc_dict(result: FastqQcResult | PairedEndQcResult) -> dict[str, object]:
    return asdict(result)


def detect_phred_offset(records: Iterable[FastqRecord]) -> dict[str, object]:
    """Infer likely FASTQ quality encoding from observed ASCII range.

    Modern Illumina data are normally Phred+33. Ambiguous ranges are reported
    rather than silently forcing a legacy encoding.
    """
    rows = list(records)
    if not rows:
        raise ValueError("At least one FASTQ record is required.")
    codes = [ord(char) for row in rows for char in row.quality]
    minimum = min(codes)
    maximum = max(codes)
    if minimum < 59:
        offset = 33
        label = "Phred+33"
        confidence = "high"
    elif minimum >= 64 and maximum > 74:
        offset = 64
        label = "Phred+64 (legacy)"
        confidence = "moderate"
    else:
        offset = 33
        label = "Ambiguous; interpreted as Phred+33"
        confidence = "low"
    scores = [value - offset for value in codes]
    return {
        "offset": offset,
        "encoding": label,
        "confidence": confidence,
        "minimum_ascii": minimum,
        "maximum_ascii": maximum,
        "minimum_phred": min(scores),
        "maximum_phred": max(scores),
    }


def expected_errors(quality: str, *, offset: int = 33) -> float:
    """Return the sum of base error probabilities for a read."""
    return float(sum(10 ** (-(ord(char) - offset) / 10) for char in quality))


def read_level_metrics(
    records: Iterable[FastqRecord], *, offset: int | None = None, maximum_rows: int = 100_000
):
    """Return per-read metrics for interactive QC and filtering."""
    import pandas as pd

    rows = list(records)
    if not rows:
        raise ValueError("At least one FASTQ record is required.")
    if offset is None:
        offset = int(detect_phred_offset(rows)["offset"])
    output = []
    for record in rows[:maximum_rows]:
        scores = phred_scores(record.quality, offset=offset)
        output.append(
            {
                "read_id": record.identifier,
                "length": len(record.sequence),
                "gc_percent": 100
                * (record.sequence.count("G") + record.sequence.count("C"))
                / max(len(record.sequence), 1),
                "mean_quality": sum(scores) / max(len(scores), 1),
                "minimum_quality": min(scores) if scores else 0,
                "expected_errors": expected_errors(record.quality, offset=offset),
                "n_count": record.sequence.count("N"),
            }
        )
    return pd.DataFrame(output)


def _trim_poly_x(
    sequence: str, quality: str, *, minimum_run: int = 10
) -> tuple[str, str, str | None]:
    if not sequence:
        return sequence, quality, None
    tail_base = sequence[-1]
    run = 1
    for char in reversed(sequence[:-1]):
        if char != tail_base:
            break
        run += 1
    if run >= minimum_run:
        return sequence[:-run], quality[:-run], tail_base
    return sequence, quality, None


def trim_record_advanced(
    record: FastqRecord,
    *,
    adapter: str | None = None,
    adapter_mismatches: int = 1,
    minimum_quality: int = 20,
    sliding_window: int = 4,
    minimum_mean_window_quality: float = 20.0,
    minimum_length: int = 30,
    maximum_expected_errors: float | None = None,
    trim_poly_x: bool = True,
    poly_x_minimum_run: int = 10,
    offset: int = 33,
) -> tuple[FastqRecord | None, dict[str, object]]:
    """Quality, adapter, poly-X and expected-error aware trimming."""
    sequence = record.sequence
    quality = record.quality
    audit: dict[str, object] = {
        "read_id": record.identifier,
        "input_length": len(sequence),
        "adapter_trimmed": False,
        "poly_x_trimmed": None,
        "quality_trimmed_bases": 0,
        "drop_reason": None,
    }

    if adapter:
        adapter = adapter.upper()
        best_index: int | None = None
        minimum_match = max(6, len(adapter) // 2)
        for index in range(len(sequence)):
            overlap = min(len(adapter), len(sequence) - index)
            if overlap < minimum_match:
                continue
            mismatches = sum(sequence[index + j] != adapter[j] for j in range(overlap))
            if mismatches <= adapter_mismatches:
                best_index = index
                break
        if best_index is not None:
            sequence, quality = sequence[:best_index], quality[:best_index]
            audit["adapter_trimmed"] = True

    if trim_poly_x:
        sequence, quality, base = _trim_poly_x(
            sequence, quality, minimum_run=max(2, int(poly_x_minimum_run))
        )
        audit["poly_x_trimmed"] = base

    scores = phred_scores(quality, offset=offset)
    original_length = len(sequence)
    # Trim low-quality terminal bases.
    start = 0
    end = len(scores)
    while start < end and scores[start] < minimum_quality:
        start += 1
    while end > start and scores[end - 1] < minimum_quality:
        end -= 1
    sequence = sequence[start:end]
    quality = quality[start:end]
    scores = scores[start:end]

    # Sliding-window trim from the first failing window onward.
    if sliding_window > 0 and len(scores) >= sliding_window:
        for index in range(0, len(scores) - sliding_window + 1):
            window = scores[index : index + sliding_window]
            if sum(window) / len(window) < minimum_mean_window_quality:
                sequence = sequence[:index]
                quality = quality[:index]
                scores = scores[:index]
                break
    audit["quality_trimmed_bases"] = original_length - len(sequence)

    if len(sequence) < minimum_length:
        audit["drop_reason"] = "below_minimum_length"
        audit["output_length"] = len(sequence)
        return None, audit
    if maximum_expected_errors is not None:
        errors = expected_errors(quality, offset=offset)
        audit["expected_errors"] = errors
        if errors > maximum_expected_errors:
            audit["drop_reason"] = "expected_errors"
            audit["output_length"] = len(sequence)
            return None, audit
    audit["output_length"] = len(sequence)
    return FastqRecord(record.identifier, sequence, quality), audit


def trim_fastq_advanced(
    records: Iterable[FastqRecord], **kwargs: object
) -> tuple[list[FastqRecord], dict[str, object], list[dict[str, object]]]:
    rows = list(records)
    output: list[FastqRecord] = []
    audit_rows: list[dict[str, object]] = []
    for record in rows:
        trimmed, audit = trim_record_advanced(record, **kwargs)
        audit_rows.append(audit)
        if trimmed is not None:
            output.append(trimmed)
    reasons = Counter(str(row["drop_reason"]) for row in audit_rows if row.get("drop_reason"))
    summary = {
        "input_reads": len(rows),
        "retained_reads": len(output),
        "dropped_reads": len(rows) - len(output),
        "retained_percent": 100 * len(output) / max(len(rows), 1),
        "drop_reasons": dict(reasons),
        "adapter_trimmed_reads": sum(bool(row.get("adapter_trimmed")) for row in audit_rows),
        "poly_x_trimmed_reads": sum(bool(row.get("poly_x_trimmed")) for row in audit_rows),
    }
    return output, summary, audit_rows
