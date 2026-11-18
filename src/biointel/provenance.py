from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class DatasetManifest:
    """Reproducibility metadata that never stores raw biological sequences."""

    dataset_name: str
    dataset_version: str
    sha256: str
    row_count: int
    column_names: tuple[str, ...]
    created_at_utc: str
    source_description: str
    activity_type: str | None
    notes: str


def stable_dataframe_sha256(dataframe: pd.DataFrame) -> str:
    """Hash a dataframe using stable column order, row order and LF line endings."""

    normalized = dataframe.copy()
    normalized.columns = [str(column) for column in normalized.columns]
    payload = normalized.to_csv(
        index=False,
        lineterminator="\n",
        na_rep="<NA>",
        float_format="%.17g",
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Return SHA-256 for a local file without loading the full file into memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def create_dataset_manifest(
    dataframe: pd.DataFrame,
    dataset_name: str,
    dataset_version: str,
    source_description: str = "User-provided or local dataset",
    activity_type: str | None = None,
    notes: str = "",
) -> DatasetManifest:
    """Create a privacy-safe dataset manifest."""

    return DatasetManifest(
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        sha256=stable_dataframe_sha256(dataframe),
        row_count=len(dataframe),
        column_names=tuple(map(str, dataframe.columns)),
        created_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        source_description=source_description,
        activity_type=activity_type,
        notes=notes,
    )


def manifest_json(manifest: DatasetManifest) -> str:
    return json.dumps(asdict(manifest), indent=2, sort_keys=True, default=str)
