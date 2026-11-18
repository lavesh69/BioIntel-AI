from __future__ import annotations

import hashlib
import io
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pandas as pd


MAX_INTERACTIVE_BYTES = 100 * 1024 * 1024
MAX_STAGED_BYTES = 1024 * 1024 * 1024
DEFAULT_PREVIEW_ROWS = 5000


@dataclass(frozen=True)
class TabularPayload:
    frame: pd.DataFrame
    filename: str
    size_bytes: int
    sha256: str
    separator: str
    encoding: str
    staged_path: str | None
    preview_only: bool
    preview_rows: int

    def metadata(self) -> dict[str, object]:
        return {
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "separator": self.separator,
            "encoding": self.encoding,
            "staged_path": self.staged_path,
            "preview_only": self.preview_only,
            "preview_rows": self.preview_rows,
        }


def _separator(filename: str) -> str:
    return "\t" if str(filename).lower().endswith((".tsv", ".txt")) else ","


def _read_frame(source: io.BytesIO | str | Path, *, separator: str, nrows: int | None = None) -> tuple[pd.DataFrame, str]:
    errors: list[str] = []
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            if hasattr(source, "seek"):
                source.seek(0)
            frame = pd.read_csv(source, sep=separator, encoding=encoding, nrows=nrows, low_memory=False)
            return frame, encoding
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
        except pd.errors.ParserError as exc:
            errors.append(f"{encoding}: {exc}")
            break
    raise ValueError("Tabular file could not be parsed. Check delimiter, quoting and encoding. " + " | ".join(errors[:2]))


def read_tabular_bytes(
    data: bytes,
    filename: str,
    *,
    preview_rows: int = DEFAULT_PREVIEW_ROWS,
    interactive_limit_bytes: int = MAX_INTERACTIVE_BYTES,
    hard_limit_bytes: int = MAX_STAGED_BYTES,
    stage_directory: str | Path | None = None,
) -> TabularPayload:
    size = len(data)
    if size == 0:
        raise ValueError("Uploaded file is empty.")
    if size > int(hard_limit_bytes):
        raise ValueError(
            f"Uploaded file is {size / (1024 ** 3):.2f} GB; the current staged-ingestion limit is "
            f"{hard_limit_bytes / (1024 ** 3):.2f} GB."
        )
    separator = _separator(filename)
    digest = hashlib.sha256(data).hexdigest()
    if size <= int(interactive_limit_bytes):
        frame, encoding = _read_frame(io.BytesIO(data), separator=separator)
        frame.attrs["biointel_upload"] = {
            "filename": filename,
            "size_bytes": size,
            "sha256": digest,
            "preview_only": False,
        }
        return TabularPayload(frame, filename, size, digest, separator, encoding, None, False, len(frame))

    directory = Path(stage_directory) if stage_directory else Path(tempfile.gettempdir()) / "biointel_neuro_uploads"
    directory.mkdir(parents=True, exist_ok=True)
    safe_suffix = Path(filename).suffix or ".csv"
    staged = directory / f"{digest[:20]}{safe_suffix}"
    staged.write_bytes(data)
    frame, encoding = _read_frame(staged, separator=separator, nrows=max(100, int(preview_rows)))
    frame.attrs["biointel_upload"] = {
        "filename": filename,
        "size_bytes": size,
        "sha256": digest,
        "preview_only": True,
        "staged_path": str(staged),
    }
    return TabularPayload(frame, filename, size, digest, separator, encoding, str(staged), True, len(frame))


def iter_tabular_chunks(payload: TabularPayload, *, chunksize: int = 50_000) -> Iterator[pd.DataFrame]:
    if payload.staged_path:
        source: str | Path | io.BytesIO = payload.staged_path
    else:
        raise ValueError("Chunk iteration requires a staged file path.")
    for chunk in pd.read_csv(
        source,
        sep=payload.separator,
        encoding=payload.encoding,
        chunksize=max(1000, int(chunksize)),
        low_memory=False,
    ):
        yield chunk
