from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from biointel.data.streaming import iter_dataset_chunks, stream_dataset_shape
from biointel.dti.checkpoints import BatchCheckpointStore
from biointel.dti.predictor import batch_predict_dti
from biointel.training.model_artifact import ModelArtifact


@dataclass(frozen=True)
class BatchJobSummary:
    job_id: str
    input_rows: int
    processed_rows: int
    success_rows: int
    error_rows: int
    chunk_size: int
    started_at_utc: str
    completed_at_utc: str
    checkpoint_path: str | None
    checkpoint_format: str | None = None
    inference_workers: int | None = None
    elapsed_seconds: float = 0.0
    rows_per_second: float = 0.0
    resumed_rows: int = 0
    feature_cache_path: str | None = None


def _sample_keys(dataframe: pd.DataFrame) -> pd.Series:
    if "sample_id" in dataframe.columns:
        values = dataframe["sample_id"].fillna("").astype(str).str.strip()
        if (values == "").any():
            values = values.where(values != "", "row-" + (dataframe.index + 1).astype(str))
        if values.duplicated().any():
            occurrence = values.groupby(values).cumcount()
            values = values + occurrence.map(lambda number: f"#{number + 1}" if number else "")
        return values
    return pd.Series(
        [str(index + 1) for index in range(len(dataframe))],
        index=dataframe.index,
    )


def run_chunked_batch_prediction(
    artifact: ModelArtifact,
    dataframe: pd.DataFrame,
    chunk_size: int = 100,
    max_rows: int = 10_000,
    checkpoint_path: str | Path | None = None,
    resume: bool = True,
    *,
    n_jobs: int | None = 0,
    feature_cache_path: str | Path | None = None,
) -> tuple[pd.DataFrame, BatchJobSummary]:
    if not 1 <= chunk_size <= 5000:
        raise ValueError("chunk_size must be between 1 and 5000")
    if len(dataframe) > max_rows:
        raise ValueError(f"Input contains {len(dataframe)} rows; maximum is {max_rows}.")

    required = {"canonical_smiles", "protein_sequence"}
    missing = required - set(dataframe.columns)
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))

    started = datetime.now(UTC)
    clock_start = time.perf_counter()
    job_id = (
        "batch-" + started.strftime("%Y%m%dT%H%M%SZ") + "-" + artifact.metadata.experiment_id[-8:]
    )

    checkpoint = Path(checkpoint_path).resolve() if checkpoint_path is not None else None
    store = BatchCheckpointStore(checkpoint) if checkpoint is not None else None
    previous = pd.DataFrame()
    completed_keys: set[str] = set()
    if store is not None:
        if not resume:
            store.clear()
        elif store.exists():
            previous = store.load()
            if "sample_id" in previous.columns:
                completed_keys = set(previous["sample_id"].astype(str))

    source = dataframe.copy().reset_index(drop=True)
    source["_batch_sample_key"] = _sample_keys(source)
    pending = source[~source["_batch_sample_key"].isin(completed_keys)].copy()

    outputs: list[pd.DataFrame] = []
    if not previous.empty:
        outputs.append(previous)

    for start in range(0, len(pending), chunk_size):
        chunk = pending.iloc[start : start + chunk_size].copy()
        original_ids = chunk.get("sample_id")
        chunk["sample_id"] = chunk["_batch_sample_key"]
        if original_ids is not None:
            chunk["input_sample_id"] = original_ids
        chunk = chunk.drop(columns=["_batch_sample_key"])
        result = batch_predict_dti(
            artifact,
            chunk,
            max_rows=chunk_size,
            n_jobs=n_jobs,
            feature_cache_path=feature_cache_path,
        )
        outputs.append(result)
        if store is not None:
            store.append(result)

    final = pd.concat(outputs, ignore_index=True) if outputs else pd.DataFrame()
    if not final.empty and "sample_id" in final.columns:
        final = final.drop_duplicates(subset=["sample_id"], keep="last").reset_index(drop=True)

    error_rows = (
        int(final["error"].fillna("").astype(bool).sum())
        if not final.empty and "error" in final.columns
        else 0
    )
    completed = datetime.now(UTC)
    elapsed = max(time.perf_counter() - clock_start, 0.0)
    summary = BatchJobSummary(
        job_id=job_id,
        input_rows=len(dataframe),
        processed_rows=len(final),
        success_rows=max(0, len(final) - error_rows),
        error_rows=error_rows,
        chunk_size=chunk_size,
        started_at_utc=started.isoformat(timespec="seconds"),
        completed_at_utc=completed.isoformat(timespec="seconds"),
        checkpoint_path=str(checkpoint) if checkpoint else None,
        checkpoint_format=store.format if store else None,
        inference_workers=n_jobs,
        elapsed_seconds=round(elapsed, 4),
        rows_per_second=round(len(pending) / elapsed, 3) if elapsed else 0.0,
        resumed_rows=len(previous),
        feature_cache_path=(
            str(Path(feature_cache_path).resolve()) if feature_cache_path is not None else None
        ),
    )

    if checkpoint is not None:
        metadata_path = checkpoint.with_suffix(checkpoint.suffix + ".summary.json")
        metadata_path.write_text(
            json.dumps(asdict(summary), indent=2, sort_keys=True), encoding="utf-8"
        )

    return final, summary


def _stream_sample_keys(
    dataframe: pd.DataFrame,
    *,
    row_offset: int,
    occurrences: dict[str, int],
) -> pd.Series:
    if "sample_id" in dataframe.columns:
        raw = dataframe["sample_id"].fillna("").astype(str).str.strip().tolist()
    else:
        raw = [""] * len(dataframe)
    keys: list[str] = []
    for local_index, value in enumerate(raw):
        base = value or f"row-{row_offset + local_index + 1}"
        occurrence = occurrences.get(base, 0)
        occurrences[base] = occurrence + 1
        keys.append(base if occurrence == 0 else f"{base}#{occurrence + 1}")
    return pd.Series(keys, index=dataframe.index, dtype="string")


def run_streaming_batch_prediction(
    artifact: ModelArtifact,
    source_path: str | Path,
    *,
    chunk_size: int = 1000,
    max_rows: int = 250_000,
    checkpoint_path: str | Path,
    resume: bool = True,
    n_jobs: int | None = 0,
    feature_cache_path: str | Path | None = None,
    preview_rows: int = 100,
) -> tuple[pd.DataFrame, BatchJobSummary]:
    """Run file-backed inference into a transactional SQLite checkpoint."""

    if not 100 <= int(chunk_size) <= 5000:
        raise ValueError("chunk_size must be between 100 and 5000")
    if int(max_rows) < 1:
        raise ValueError("max_rows must be positive")
    source = Path(source_path).resolve()
    checkpoint = Path(checkpoint_path).resolve()
    if checkpoint.suffix.lower() not in {".sqlite", ".sqlite3", ".db"}:
        raise ValueError("Streaming prediction requires a .sqlite3 checkpoint.")

    shape = stream_dataset_shape(
        source, chunk_size=max(int(chunk_size), 1000), max_rows=int(max_rows)
    )
    required = {"canonical_smiles", "protein_sequence"}
    missing = required - set(shape["columns"])
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))

    store = BatchCheckpointStore(checkpoint)
    if not resume:
        store.clear()
    resumed_rows = store.count() if resume else 0
    completed_keys = set(store.sample_ids()) if resume and resumed_rows else set()
    started = datetime.now(UTC)
    clock_start = time.perf_counter()
    job_id = (
        "stream-batch-"
        + started.strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + artifact.metadata.experiment_id[-8:]
    )
    occurrences: dict[str, int] = {}
    rows_seen = 0
    newly_processed = 0
    for chunk in iter_dataset_chunks(source, chunk_size=int(chunk_size)):
        chunk = chunk.copy().reset_index(drop=True)
        keys = _stream_sample_keys(chunk, row_offset=rows_seen, occurrences=occurrences)
        rows_seen += len(chunk)
        pending_mask = ~keys.isin(completed_keys)
        if not bool(pending_mask.any()):
            continue
        pending = chunk.loc[pending_mask].copy().reset_index(drop=True)
        pending_keys = keys.loc[pending_mask].reset_index(drop=True)
        if "sample_id" in pending.columns:
            pending["input_sample_id"] = pending["sample_id"]
        pending["sample_id"] = pending_keys
        result = batch_predict_dti(
            artifact,
            pending,
            max_rows=max(len(pending), 1),
            n_jobs=n_jobs,
            feature_cache_path=feature_cache_path,
        )
        store.append(result)
        completed_keys.update(str(value) for value in result["sample_id"].tolist())
        newly_processed += len(result)

    if rows_seen != int(shape["rows"]):
        raise RuntimeError(
            "Input changed between preflight and inference; no release summary was produced."
        )
    total_rows, error_rows = store.result_counts()
    preview = store.preview(max(1, min(int(preview_rows), 1000)))
    completed = datetime.now(UTC)
    elapsed = max(time.perf_counter() - clock_start, 0.0)
    summary = BatchJobSummary(
        job_id=job_id,
        input_rows=int(shape["rows"]),
        processed_rows=total_rows,
        success_rows=max(0, total_rows - error_rows),
        error_rows=error_rows,
        chunk_size=int(chunk_size),
        started_at_utc=started.isoformat(timespec="seconds"),
        completed_at_utc=completed.isoformat(timespec="seconds"),
        checkpoint_path=str(checkpoint),
        checkpoint_format=store.format,
        inference_workers=n_jobs,
        elapsed_seconds=round(elapsed, 4),
        rows_per_second=round(newly_processed / elapsed, 3) if elapsed else 0.0,
        resumed_rows=resumed_rows,
        feature_cache_path=(
            str(Path(feature_cache_path).resolve())
            if feature_cache_path is not None
            else None
        ),
    )
    checkpoint.with_suffix(checkpoint.suffix + ".summary.json").write_text(
        json.dumps(asdict(summary), indent=2, sort_keys=True), encoding="utf-8"
    )
    return preview, summary
