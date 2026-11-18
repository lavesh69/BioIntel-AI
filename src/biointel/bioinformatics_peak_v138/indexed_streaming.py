from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import gzip
from pathlib import Path
from typing import Iterator

import pandas as pd


@dataclass(frozen=True)
class GenomicRegion:
    reference: str
    start: int
    end: int

    def __post_init__(self) -> None:
        if not self.reference.strip() or self.start < 0 or self.end <= self.start:
            raise ValueError("Region must satisfy reference != empty and 0 <= start < end.")

    @classmethod
    def parse(cls, text: str) -> "GenomicRegion":
        reference, interval = text.replace(",", "").split(":", 1)
        start_text, end_text = interval.split("-", 1)
        return cls(reference.strip(), int(start_text), int(end_text))


def companion_indexes(path: str | Path) -> list[Path]:
    target = Path(path)
    candidates = [
        Path(str(target) + suffix) for suffix in (".tbi", ".csi", ".bai", ".crai", ".fai")
    ]
    if target.suffix.lower() in {".bam", ".cram"}:
        candidates.extend([target.with_suffix(target.suffix + ".bai"), target.with_suffix(target.suffix + ".crai")])
    return sorted({item for item in candidates if item.exists()})


def index_status(path: str | Path) -> dict[str, object]:
    target = Path(path)
    indexes = companion_indexes(target)
    suffix = target.name.lower()
    requires = suffix.endswith((".vcf.gz", ".bed.gz", ".gff.gz", ".gtf.gz", ".bam", ".cram"))
    return {
        "path": str(target),
        "requires_index_for_random_access": requires,
        "index_files": [str(item) for item in indexes],
        "random_access_ready": bool(indexes) if requires else True,
    }


def _open_text(path: Path):
    return gzip.open(path, "rt", encoding="utf-8", errors="replace") if path.suffix.lower() == ".gz" else path.open("rt", encoding="utf-8", errors="replace")


def _iter_interval_rows(path: Path, region: GenomicRegion) -> Iterator[dict[str, object]]:
    name = path.name.lower()
    with _open_text(path) as handle:
        for raw in handle:
            if not raw.strip() or raw.startswith("##"):
                continue
            if raw.startswith("#CHROM"):
                continue
            parts = raw.rstrip("\n\r").split("\t")
            try:
                if ".vcf" in name:
                    reference, start = parts[0], int(parts[1]) - 1
                    end = start + max(1, len(parts[3]))
                    row = {"chrom": reference, "start": start, "end": end, "id": parts[2], "ref": parts[3], "alt": parts[4], "qual": parts[5] if len(parts) > 5 else ""}
                elif any(token in name for token in (".gff", ".gtf")):
                    reference, start, end = parts[0], int(parts[3]) - 1, int(parts[4])
                    row = {"chrom": reference, "start": start, "end": end, "feature": parts[2], "attributes": parts[8] if len(parts) > 8 else ""}
                else:
                    reference, start, end = parts[0], int(parts[1]), int(parts[2])
                    row = {"chrom": reference, "start": start, "end": end, "name": parts[3] if len(parts) > 3 else ""}
            except Exception:
                continue
            normalized_ref = str(reference).removeprefix("chr")
            target_ref = region.reference.removeprefix("chr")
            if normalized_ref == target_ref and start < region.end and end > region.start:
                yield row


@lru_cache(maxsize=512)
def _query_cached(path_text: str, size: int, mtime_ns: int, reference: str, start: int, end: int, max_records: int) -> tuple[tuple[tuple[str, object], ...], ...]:
    path = Path(path_text)
    rows = []
    for row in _iter_interval_rows(path, GenomicRegion(reference, start, end)):
        rows.append(tuple(row.items()))
        if len(rows) >= max_records:
            break
    return tuple(rows)


def query_region(path: str | Path, region: GenomicRegion | str, *, max_records: int = 5000) -> pd.DataFrame:
    target = Path(path).resolve()
    if not target.is_file():
        raise FileNotFoundError(target)
    if max_records < 1 or max_records > 100_000:
        raise ValueError("max_records must be between 1 and 100,000.")
    parsed = GenomicRegion.parse(region) if isinstance(region, str) else region
    if target.name.lower().endswith((".bam", ".cram", ".bcf", ".bw", ".bigwig")):
        try:
            import pysam  # type: ignore
        except Exception as exc:
            raise RuntimeError("Indexed binary regional access requires optional pysam/pyBigWig support.") from exc
        if target.suffix.lower() in {".bam", ".cram"}:
            rows = []
            with pysam.AlignmentFile(str(target), "rb") as alignment:
                for read in alignment.fetch(parsed.reference, parsed.start, parsed.end):
                    rows.append({"read_name": read.query_name, "chrom": parsed.reference, "start": read.reference_start, "end": read.reference_end, "mapping_quality": read.mapping_quality, "flag": read.flag})
                    if len(rows) >= max_records:
                        break
            return pd.DataFrame(rows)
        raise RuntimeError("This binary format requires its qualified optional indexed reader.")
    stat = target.stat()
    packed = _query_cached(str(target), stat.st_size, stat.st_mtime_ns, parsed.reference, parsed.start, parsed.end, max_records)
    return pd.DataFrame([dict(row) for row in packed])


def progressive_tiles(region: GenomicRegion, *, tile_size: int = 1_000_000) -> list[GenomicRegion]:
    if tile_size < 100:
        raise ValueError("tile_size must be at least 100 bases.")
    tiles = []
    cursor = region.start
    while cursor < region.end:
        boundary = min(region.end, cursor + tile_size)
        tiles.append(GenomicRegion(region.reference, cursor, boundary))
        cursor = boundary
    return tiles


__all__ = ["GenomicRegion", "companion_indexes", "index_status", "query_region", "progressive_tiles"]
