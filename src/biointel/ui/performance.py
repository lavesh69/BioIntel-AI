from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from biointel.database.core import connect, database_file_signature
from biointel.utils.runtime_cache import file_signature

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None


def _cache_data(*, ttl: int = 120, max_entries: int = 128):
    if st is None:
        def decorator(func):
            return func
        return decorator
    return st.cache_data(ttl=ttl, max_entries=max_entries, show_spinner=False)


def _cache_resource(*, max_entries: int = 32):
    if st is None:
        def decorator(func):
            return func
        return decorator
    return st.cache_resource(max_entries=max_entries, show_spinner=False)



@_cache_data(ttl=300, max_entries=96)
def _read_csv_signature(signature: tuple[str, int, int, int, str], kwargs_json: str) -> pd.DataFrame:
    path = signature[0]
    kwargs = json.loads(kwargs_json)
    return pd.read_csv(path, **kwargs)


def read_csv_cached(path: str | Path, **kwargs: Any) -> pd.DataFrame:
    return _read_csv_signature(file_signature(path), json.dumps(kwargs, sort_keys=True, default=str)).copy()


@_cache_data(ttl=120, max_entries=128)
def _read_sql_signature(
    path_text: str,
    signature: tuple[int, int, int, int, int, int],
    query: str,
    params_json: str,
) -> pd.DataFrame:
    del signature
    params = json.loads(params_json)
    with connect(path_text, read_only=True) as connection:
        return pd.read_sql_query(query, connection, params=params)


def read_sql_cached(
    database_path: str | Path,
    query: str,
    params: tuple[Any, ...] | list[Any] | None = None,
) -> pd.DataFrame:
    resolved = Path(database_path).resolve()
    return _read_sql_signature(
        str(resolved),
        database_file_signature(resolved),
        query,
        json.dumps(list(params or []), default=str),
    ).copy(deep=True)


@_cache_data(ttl=300, max_entries=96)
def _read_text_signature(signature: tuple[str, int, int, int, str], encoding: str) -> str:
    path = signature[0]
    return Path(path).read_text(encoding=encoding)


def read_text_cached(path: str | Path, *, encoding: str = "utf-8") -> str:
    return _read_text_signature(file_signature(path), encoding)


@_cache_data(ttl=300, max_entries=96)
def _read_json_signature(signature: tuple[str, int, int, int, str]) -> Any:
    path = signature[0]
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_json_cached(path: str | Path) -> Any:
    return _read_json_signature(file_signature(path))


@_cache_resource(max_entries=24)
def load_joblib_cached(signature: tuple[str, int, int, int, str]):
    import joblib
    return joblib.load(signature[0])


def load_model_cached(path: str | Path):
    return load_joblib_cached(file_signature(path))


def clear_ui_caches() -> None:
    if st is not None:
        st.cache_data.clear()
        st.cache_resource.clear()


def frame_fingerprint(frame: pd.DataFrame, *, parameters: Any | None = None, sample_rows: int = 512) -> str:
    """Return a stable bounded fingerprint for cache invalidation.

    Only the schema plus evenly spaced rows are hashed, preventing large omics
    tables from being copied solely to derive a cache key.
    """
    import hashlib
    import numpy as np

    digest = hashlib.sha256()
    digest.update(str(frame.shape).encode("utf-8"))
    digest.update("|".join(map(str, frame.columns)).encode("utf-8"))
    digest.update("|".join(map(str, frame.dtypes)).encode("utf-8"))
    if not frame.empty:
        cap = max(1, min(int(sample_rows), len(frame)))
        indices = np.linspace(0, len(frame) - 1, num=cap, dtype=np.int64)
        sample = frame.iloc[indices].copy()
        for column in sample.columns:
            if sample[column].dtype == "object":
                sample[column] = sample[column].map(
                    lambda value: json.dumps(value, sort_keys=True, default=str)
                    if isinstance(value, (dict, list, tuple, set))
                    else str(value)
                )
        digest.update(pd.util.hash_pandas_object(sample, index=True).values.tobytes())
    digest.update(json.dumps(parameters, sort_keys=True, default=str).encode("utf-8"))
    return digest.hexdigest()


def bounded_frame_for_display(
    frame: pd.DataFrame,
    *,
    max_rows: int = 50_000,
    max_cells: int = 2_000_000,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Bound an interactive table without biasing toward the first rows."""
    import numpy as np

    rows, columns = frame.shape
    row_cap = max(1, int(max_rows))
    if columns:
        row_cap = min(row_cap, max(1, int(max_cells) // int(columns)))
    sampled = rows > row_cap
    if not sampled:
        return frame, {
            "sampled": False,
            "source_rows": int(rows),
            "display_rows": int(rows),
            "columns": int(columns),
        }
    indices = np.linspace(0, rows - 1, num=row_cap, dtype=np.int64)
    return frame.iloc[indices], {
        "sampled": True,
        "source_rows": int(rows),
        "display_rows": int(row_cap),
        "columns": int(columns),
        "sampling": "deterministic evenly spaced",
    }


def dataframe_memory_mb(frame: pd.DataFrame | None) -> float:
    if frame is None:
        return 0.0
    try:
        return round(float(frame.memory_usage(index=True, deep=True).sum()) / (1024 * 1024), 3)
    except Exception:
        return 0.0
