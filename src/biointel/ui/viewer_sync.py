from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import hashlib
import json
import sqlite3
from biointel.database.core import managed_connect
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import numpy as np
import pandas as pd
import streamlit as st

from biointel.ui.operational_canvas import render_operational_canvas


@dataclass(frozen=True)
class ViewerSelection:
    event_id: str
    project_key: str
    source_viewer: str
    entity_type: str
    entity_ids: tuple[str, ...]
    coordinates: Mapping[str, Any]
    filters: Mapping[str, Any]
    analysis_run_id: str
    created_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["entity_ids"] = list(self.entity_ids)
        result["coordinates"] = dict(self.coordinates)
        result["filters"] = dict(self.filters)
        return result


class ViewerSyncStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = managed_connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS viewer_selection_events(
                    event_id TEXT PRIMARY KEY,
                    project_key TEXT NOT NULL,
                    source_viewer TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_ids_json TEXT NOT NULL,
                    coordinates_json TEXT NOT NULL DEFAULT '{}',
                    filters_json TEXT NOT NULL DEFAULT '{}',
                    analysis_run_id TEXT NOT NULL DEFAULT '',
                    created_at_utc TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_viewer_selection_project_time
                    ON viewer_selection_events(project_key, created_at_utc DESC);
                CREATE TABLE IF NOT EXISTS viewer_state_snapshots(
                    snapshot_id TEXT PRIMARY KEY,
                    project_key TEXT NOT NULL,
                    viewer_key TEXT NOT NULL,
                    state_hash TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    UNIQUE(project_key, viewer_key, state_hash)
                );
                """
            )

    def publish(self, selection: ViewerSelection) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO viewer_selection_events(
                    event_id, project_key, source_viewer, entity_type, entity_ids_json,
                    coordinates_json, filters_json, analysis_run_id, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    selection.event_id,
                    selection.project_key,
                    selection.source_viewer,
                    selection.entity_type,
                    json.dumps(list(selection.entity_ids), sort_keys=True),
                    json.dumps(dict(selection.coordinates), sort_keys=True, default=str),
                    json.dumps(dict(selection.filters), sort_keys=True, default=str),
                    selection.analysis_run_id,
                    selection.created_at_utc,
                ),
            )

    def latest(self, project_key: str, *, exclude_viewer: str | None = None) -> ViewerSelection | None:
        query = "SELECT * FROM viewer_selection_events WHERE project_key=?"
        parameters: list[Any] = [project_key]
        if exclude_viewer:
            query += " AND source_viewer<>?"
            parameters.append(exclude_viewer)
        query += " ORDER BY created_at_utc DESC LIMIT 1"
        with self._connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        if row is None:
            return None
        return ViewerSelection(
            event_id=str(row["event_id"]),
            project_key=str(row["project_key"]),
            source_viewer=str(row["source_viewer"]),
            entity_type=str(row["entity_type"]),
            entity_ids=tuple(json.loads(row["entity_ids_json"])),
            coordinates=json.loads(row["coordinates_json"]),
            filters=json.loads(row["filters_json"]),
            analysis_run_id=str(row["analysis_run_id"]),
            created_at_utc=str(row["created_at_utc"]),
        )

    def history(self, project_key: str, limit: int = 100) -> pd.DataFrame:
        with self._connect() as connection:
            frame = pd.read_sql_query(
                "SELECT * FROM viewer_selection_events WHERE project_key=? ORDER BY created_at_utc DESC LIMIT ?",
                connection,
                params=(project_key, int(limit)),
            )
        if not frame.empty:
            frame["entity_count"] = frame["entity_ids_json"].map(lambda value: len(json.loads(value)))
        return frame

    def save_state(self, *, project_key: str, viewer_key: str, state: Mapping[str, Any]) -> str:
        serialized = json.dumps(dict(state), sort_keys=True, default=str)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        snapshot_id = "vstate-" + uuid4().hex
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT snapshot_id FROM viewer_state_snapshots WHERE project_key=? AND viewer_key=? AND state_hash=?",
                (project_key, viewer_key, digest),
            ).fetchone()
            if existing:
                return str(existing["snapshot_id"])
            connection.execute(
                "INSERT INTO viewer_state_snapshots(snapshot_id, project_key, viewer_key, state_hash, state_json, created_at_utc) VALUES (?, ?, ?, ?, ?, ?)",
                (snapshot_id, project_key, viewer_key, digest, serialized, datetime.now(UTC).isoformat(timespec="seconds")),
            )
        return snapshot_id

    def states(self, project_key: str, viewer_key: str | None = None, limit: int = 100) -> pd.DataFrame:
        query = "SELECT * FROM viewer_state_snapshots WHERE project_key=?"
        params: list[Any] = [project_key]
        if viewer_key:
            query += " AND viewer_key=?"
            params.append(viewer_key)
        query += " ORDER BY created_at_utc DESC LIMIT ?"
        params.append(int(limit))
        with self._connect() as connection:
            return pd.read_sql_query(query, connection, params=params)


def _default_store() -> ViewerSyncStore:
    root = Path(__file__).resolve().parents[3]
    return ViewerSyncStore(runtime_database_path(root, "viewer_sync.sqlite3"))


def active_project_key() -> str:
    return str(st.session_state.get("active_project_name") or st.session_state.get("active_project") or "default-project")


def _infer_coordinates(selected: pd.DataFrame) -> dict[str, Any]:
    lower = {str(column).lower(): str(column) for column in selected.columns}
    coordinates: dict[str, Any] = {}
    chrom = next((lower[key] for key in ("chrom", "chromosome", "reference") if key in lower), None)
    start = next((lower[key] for key in ("start", "position", "pos") if key in lower), None)
    end = next((lower[key] for key in ("end",) if key in lower), None)
    if chrom:
        values = selected[chrom].dropna().astype(str).unique().tolist()
        if values:
            coordinates["chrom"] = values[0]
    if start:
        values = pd.to_numeric(selected[start], errors="coerce").dropna()
        if not values.empty:
            coordinates["start"] = float(values.min())
            coordinates["position"] = float(values.median())
    if end:
        values = pd.to_numeric(selected[end], errors="coerce").dropna()
        if not values.empty:
            coordinates["end"] = float(values.max())
    for canonical, aliases in {
        "x": ("x", "umap_1", "x_umap_1", "x_umap_1"),
        "y": ("y", "umap_2", "x_umap_2", "x_umap_2"),
        "z": ("z",),
        "latitude": ("lat", "latitude"),
        "longitude": ("lon", "lng", "longitude"),
        "mz": ("mz",),
        "time": ("time", "scan_time", "timestamp"),
    }.items():
        column = next((lower[alias] for alias in aliases if alias in lower), None)
        if column:
            values = pd.to_numeric(selected[column], errors="coerce").dropna()
            if not values.empty:
                coordinates[canonical] = float(values.median())
                coordinates[f"{canonical}_min"] = float(values.min())
                coordinates[f"{canonical}_max"] = float(values.max())
    return coordinates


def _infer_filters(selected: pd.DataFrame) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    for column in selected.columns:
        if pd.api.types.is_numeric_dtype(selected[column]):
            continue
        values = selected[column].dropna().astype(str).unique().tolist()
        if 0 < len(values) <= 10:
            filters[str(column)] = values
        if len(filters) >= 5:
            break
    return filters


def publish_selection(
    *,
    source_viewer: str,
    selected: pd.DataFrame,
    entity_type: str = "record",
    id_column: str | None = None,
    coordinates: Mapping[str, Any] | None = None,
    filters: Mapping[str, Any] | None = None,
    analysis_run_id: str = "",
    store: ViewerSyncStore | None = None,
) -> ViewerSelection | None:
    if selected is None or selected.empty:
        return None
    ids: list[str]
    if id_column and id_column in selected.columns:
        ids = selected[id_column].astype(str).tolist()
    else:
        candidates = [column for column in selected.columns if str(column).lower() in {"id", "variant_id", "sample", "cell_id", "read_id", "record_id", "well", "node", "peptide", "residue_number"}]
        if candidates:
            ids = selected[candidates[0]].astype(str).tolist()
        else:
            ids = selected.index.astype(str).tolist()
    selection = ViewerSelection(
        event_id="vsel-" + uuid4().hex,
        project_key=active_project_key(),
        source_viewer=source_viewer,
        entity_type=entity_type,
        entity_ids=tuple(ids[:10_000]),
        coordinates=dict(coordinates or _infer_coordinates(selected)),
        filters=dict(filters or _infer_filters(selected)),
        analysis_run_id=analysis_run_id,
        created_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    (store or _default_store()).publish(selection)
    st.session_state["_biointel_latest_viewer_selection"] = selection.to_dict()
    return selection


def consume_latest(*, target_viewer: str, store: ViewerSyncStore | None = None) -> ViewerSelection | None:
    session = st.session_state.get("_biointel_latest_viewer_selection")
    if isinstance(session, dict) and session.get("source_viewer") != target_viewer:
        return ViewerSelection(
            event_id=str(session["event_id"]),
            project_key=str(session["project_key"]),
            source_viewer=str(session["source_viewer"]),
            entity_type=str(session["entity_type"]),
            entity_ids=tuple(session.get("entity_ids") or ()),
            coordinates=dict(session.get("coordinates") or {}),
            filters=dict(session.get("filters") or {}),
            analysis_run_id=str(session.get("analysis_run_id", "")),
            created_at_utc=str(session.get("created_at_utc", "")),
        )
    return (store or _default_store()).latest(active_project_key(), exclude_viewer=target_viewer)


def apply_selection_to_visual(
    figure: Any,
    data: pd.DataFrame,
    selection: ViewerSelection | None,
) -> tuple[Any, pd.DataFrame, str | None]:
    """Apply a linked selection as a non-destructive visual focus/highlight."""
    if selection is None:
        return figure, data, None
    try:
        import plotly.graph_objects as go

        linked_figure = go.Figure(figure)
    except Exception:
        linked_figure = figure
    linked_data = data.copy()
    note_parts: list[str] = []
    coordinates = dict(selection.coordinates)
    if coordinates.get("start") is not None:
        start = float(coordinates["start"])
        end = float(coordinates.get("end", start))
        if end <= start:
            end = start + max(abs(start) * 0.05, 1.0)
        padding = max((end - start) * 0.15, 1.0)
        try:
            linked_figure.update_xaxes(range=[start - padding, end + padding])
            note_parts.append("genomic/numeric x-range focused")
        except Exception:
            pass
    if coordinates.get("latitude") is not None and coordinates.get("longitude") is not None:
        try:
            linked_figure.update_geos(center={"lat": float(coordinates["latitude"]), "lon": float(coordinates["longitude"])})
            note_parts.append("geographic centre synchronized")
        except Exception:
            pass
    id_candidates = [column for column in linked_data.columns if str(column).lower() in {"id", "variant_id", "sample", "cell_id", "read_id", "record_id", "well", "node", "peptide", "residue_number", "individual_id"}]
    matched = pd.Series(False, index=linked_data.index)
    if id_candidates and selection.entity_ids:
        target = set(map(str, selection.entity_ids))
        for column in id_candidates:
            matched |= linked_data[column].astype(str).isin(target)
        linked_data["_linked_selection"] = matched
        if matched.any():
            note_parts.append(f"{int(matched.sum())} matching record(s) highlighted")
            try:
                first_trace = linked_figure.data[0] if linked_figure.data else None
                if first_trace is not None and getattr(first_trace, "x", None) is not None and getattr(first_trace, "y", None) is not None:
                    positions = np.flatnonzero(matched.to_numpy())
                    x_values = np.asarray(first_trace.x)
                    y_values = np.asarray(first_trace.y)
                    positions = positions[positions < min(len(x_values), len(y_values))]
                    if len(positions):
                        linked_figure.add_trace(go.Scatter(
                            x=x_values[positions], y=y_values[positions], mode="markers",
                            marker={"size": 14, "symbol": "circle-open", "line": {"width": 3}},
                            name="Linked selection", hoverinfo="skip",
                        ))
            except Exception:
                pass
    note = "; ".join(note_parts) if note_parts else f"Selection from {selection.source_viewer} is available in the linked-selection panel"
    return linked_figure, linked_data, note


def render_sync_status(target_viewer: str, *, key_prefix: str) -> ViewerSelection | None:
    incoming = consume_latest(target_viewer=target_viewer)
    if incoming is None:
        st.caption("No linked selection is currently available from another scientific viewer.")
        return None
    with st.expander(f"Linked selection from {incoming.source_viewer}", expanded=False):
        st.write(f"**Entity type:** {incoming.entity_type}")
        st.write(f"**Selected entities:** {len(incoming.entity_ids):,}")
        if incoming.coordinates:
            render_operational_canvas(
                "Linked coordinates",
                dict(incoming.coordinates),
                workflow=("Source selection", "Coordinate transfer", "Viewer focus"),
            )
        if incoming.filters:
            render_operational_canvas(
                "Linked filters",
                dict(incoming.filters),
                workflow=("Source selection", "Filter transfer", "Viewer focus"),
            )
        st.download_button(
            "Download linked selection",
            data=json.dumps(incoming.to_dict(), indent=2),
            file_name=f"{key_prefix}_linked_selection.json",
            mime="application/json",
            key=f"{key_prefix}_sync_download",
        )
    return incoming


__all__ = [
    "ViewerSelection",
    "ViewerSyncStore",
    "active_project_key",
    "apply_selection_to_visual",
    "consume_latest",
    "publish_selection",
    "render_sync_status",
]
