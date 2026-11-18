from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pandas as pd


def iter_dataset_chunks(
    path: str | Path,
    *,
    chunk_size: int = 10_000,
    columns: list[str] | None = None,
) -> Iterator[pd.DataFrame]:
    """Stream CSV/TSV/Parquet datasets without loading the whole file."""

    source = Path(path).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if not 100 <= chunk_size <= 1_000_000:
        raise ValueError("chunk_size must be between 100 and 1,000,000")
    suffix = source.suffix.lower()
    if suffix == ".csv":
        yield from pd.read_csv(source, usecols=columns, chunksize=chunk_size, low_memory=False)
        return
    if suffix in {".tsv", ".txt"}:
        yield from pd.read_csv(
            source,
            sep="\t",
            usecols=columns,
            chunksize=chunk_size,
            low_memory=False,
        )
        return
    if suffix in {".parquet", ".pq"}:
        try:
            dataframe = pd.read_parquet(source, columns=columns)
        except ImportError as exc:
            raise RuntimeError("Parquet streaming requires pyarrow or fastparquet.") from exc
        for start in range(0, len(dataframe), chunk_size):
            yield dataframe.iloc[start : start + chunk_size].copy()
        return
    raise ValueError("Supported streaming formats: .csv, .tsv, .txt, .parquet")


def stream_dataset_summary(
    path: str | Path,
    *,
    chunk_size: int = 50_000,
) -> dict[str, object]:
    rows = 0
    columns: list[str] = []
    null_counts: dict[str, int] = {}
    for chunk in iter_dataset_chunks(path, chunk_size=chunk_size):
        rows += len(chunk)
        if not columns:
            columns = list(chunk.columns)
        for name, count in chunk.isna().sum().items():
            null_counts[str(name)] = null_counts.get(str(name), 0) + int(count)
    return {
        "path": str(Path(path).resolve()),
        "rows": rows,
        "columns": columns,
        "null_counts": null_counts,
    }


def stream_dataset_shape(
    path: str | Path,
    *,
    chunk_size: int = 50_000,
    max_rows: int | None = None,
) -> dict[str, object]:
    """Count rows and columns using bounded memory and enforce a hard row cap."""

    rows = 0
    columns: list[str] = []
    for chunk in iter_dataset_chunks(path, chunk_size=chunk_size):
        if not columns:
            columns = [str(column) for column in chunk.columns]
        rows += int(len(chunk))
        if max_rows is not None and rows > int(max_rows):
            raise ValueError(
                f"Input contains more than {int(max_rows)} rows; maximum is {int(max_rows)}."
            )
    return {"path": str(Path(path).resolve()), "rows": rows, "columns": columns}
