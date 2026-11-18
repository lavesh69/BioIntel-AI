from __future__ import annotations

import hashlib
import html
import io
import json
import math
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

import numpy as np
import pandas as pd

from biointel.nextgen.intelligence import connect


JOURNAL_PRESETS: dict[str, dict[str, Any]] = {
    "Nature two-column": {"width_mm": 183, "height_mm": 130, "dpi": 600, "columns": 2},
    "Cell full-width": {"width_mm": 178, "height_mm": 140, "dpi": 600, "columns": 2},
    "Science single-column": {"width_mm": 86, "height_mm": 110, "dpi": 600, "columns": 1},
    "A4 landscape": {"width_mm": 277, "height_mm": 190, "dpi": 300, "columns": 3},
    "Presentation 16:9": {"width_mm": 338, "height_mm": 190, "dpi": 220, "columns": 3},
}

ENTITY_HINTS: tuple[str, ...] = (
    "patient_id", "patient", "sample_id", "sample", "slide_id", "slide", "isolate_id",
    "isolate", "candidate_id", "candidate", "gene", "variant", "transcript", "isoform",
    "construct_id", "construct", "drug", "compound", "ligand", "model_id", "model", "event",
)

LOWER_HINTS: tuple[str, ...] = ("lower", "ci_low", "lower_ci", "lcl", "q025", "p025", "min")
UPPER_HINTS: tuple[str, ...] = ("upper", "ci_high", "upper_ci", "ucl", "q975", "p975", "max")


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _safe_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def _ensure_schema(project_root: str | Path, *, path: str | Path | None = None) -> None:
    with connect(project_root, path=path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS selection_history (
                selection_id TEXT PRIMARY KEY,
                module_key TEXT NOT NULL,
                chart_key TEXT NOT NULL,
                column_name TEXT NOT NULL,
                values_json TEXT NOT NULL,
                source TEXT NOT NULL,
                action TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_selection_history_module
                ON selection_history(module_key, created_at_utc DESC);

            CREATE TABLE IF NOT EXISTS visual_provenance (
                provenance_id TEXT PRIMARY KEY,
                module_key TEXT NOT NULL,
                run_id TEXT,
                chart_key TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                source_row_json TEXT NOT NULL,
                transformation_json TEXT NOT NULL,
                figure_refs_json TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_visual_provenance_module
                ON visual_provenance(module_key, created_at_utc DESC);

            CREATE TABLE IF NOT EXISTS review_threads (
                thread_id TEXT PRIMARY KEY,
                module_key TEXT NOT NULL,
                run_id TEXT,
                entity_id TEXT NOT NULL,
                title TEXT NOT NULL,
                assignee TEXT NOT NULL,
                status TEXT NOT NULL,
                due_at_utc TEXT,
                created_by TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_review_threads_module
                ON review_threads(module_key, updated_at_utc DESC);

            CREATE TABLE IF NOT EXISTS review_comments (
                comment_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                author TEXT NOT NULL,
                body TEXT NOT NULL,
                decision TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                FOREIGN KEY(thread_id) REFERENCES review_threads(thread_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_review_comments_thread
                ON review_comments(thread_id, created_at_utc ASC);

            CREATE TABLE IF NOT EXISTS figure_layouts (
                layout_id TEXT PRIMARY KEY,
                module_key TEXT NOT NULL,
                run_id TEXT,
                name TEXT NOT NULL,
                preset TEXT NOT NULL,
                width_mm REAL NOT NULL,
                height_mm REAL NOT NULL,
                dpi INTEGER NOT NULL,
                columns_count INTEGER NOT NULL,
                panel_json TEXT NOT NULL,
                caption TEXT NOT NULL,
                methods TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_figure_layouts_module
                ON figure_layouts(module_key, updated_at_utc DESC);

            CREATE TABLE IF NOT EXISTS viewer_sync_state (
                module_key TEXT PRIMARY KEY,
                state_json TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS visual_fingerprints (
                fingerprint_id TEXT PRIMARY KEY,
                module_key TEXT NOT NULL,
                chart_key TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                approved INTEGER NOT NULL DEFAULT 0,
                created_at_utc TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_visual_fingerprint_unique
                ON visual_fingerprints(module_key, chart_key, fingerprint);
            """
        )
        connection.commit()


@dataclass(frozen=True)
class ProgressiveManifest:
    source_rows: int
    rendered_rows: int
    strategy: str
    entity_column: str | None
    score_column: str | None
    preserved_extrema: int
    seed: int


def infer_entity_column(frame: pd.DataFrame) -> str | None:
    lower = {str(column).lower(): str(column) for column in frame.columns}
    for hint in ENTITY_HINTS:
        if hint in lower:
            return lower[hint]
    for column in frame.columns:
        series = frame[column]
        if not pd.api.types.is_numeric_dtype(series) and 1 < series.nunique(dropna=True) <= 50_000:
            return str(column)
    return None


def infer_score_column(frame: pd.DataFrame) -> str | None:
    candidates: list[tuple[int, str]] = []
    for column in frame.columns:
        numeric = pd.to_numeric(frame[column], errors="coerce")
        if numeric.notna().sum() < 3:
            continue
        name = str(column).lower()
        weight = 0
        for token in ("score", "confidence", "risk", "probability", "priority", "effect", "signal", "utility"):
            if token in name:
                weight += 10
        weight += min(9, int(numeric.nunique(dropna=True) > 10))
        candidates.append((weight, str(column)))
    return max(candidates, default=(0, ""))[1] or None


def progressive_sample(
    frame: pd.DataFrame,
    *,
    limit: int = 5000,
    entity_column: str | None = None,
    score_column: str | None = None,
    selected_values: Sequence[str] | None = None,
    seed: int = 131,
) -> tuple[pd.DataFrame, ProgressiveManifest]:
    """Deterministic level-of-detail sampling that preserves selected rows and extrema.

    It is intentionally dependency-free, works offline and avoids the common `head(n)` bias.
    """
    data = pd.DataFrame(frame).reset_index(drop=False).rename(columns={"index": "__source_row__"})
    source_rows = len(data)
    entity_column = entity_column or infer_entity_column(data)
    score_column = score_column or infer_score_column(data)
    if source_rows <= max(1, int(limit)):
        return data, ProgressiveManifest(source_rows, source_rows, "full", entity_column, score_column, 0, seed)

    keep: set[int] = set()
    selected = {str(value) for value in (selected_values or [])}
    if entity_column and selected and entity_column in data.columns:
        keep.update(data.index[data[entity_column].astype(str).isin(selected)].tolist())

    preserved_extrema = 0
    numeric_columns = [
        str(column) for column in data.columns
        if column != "__source_row__" and pd.to_numeric(data[column], errors="coerce").notna().sum() >= 3
    ]
    ranked = ([score_column] if score_column in numeric_columns else []) + [c for c in numeric_columns if c != score_column]
    for column in ranked[:8]:
        numeric = pd.to_numeric(data[column], errors="coerce")
        valid = numeric.dropna()
        if valid.empty:
            continue
        for index in valid.nsmallest(3).index.tolist() + valid.nlargest(3).index.tolist():
            if index not in keep:
                preserved_extrema += 1
            keep.add(int(index))

    budget = max(0, int(limit) - len(keep))
    remaining = data.drop(index=list(keep), errors="ignore")
    if budget > 0 and not remaining.empty:
        rng = np.random.default_rng(seed)
        if entity_column and entity_column in remaining.columns and remaining[entity_column].nunique(dropna=True) <= 200:
            groups = list(remaining.groupby(entity_column, dropna=False, sort=False))
            per_group = max(1, budget // max(1, len(groups)))
            sampled_parts: list[pd.DataFrame] = []
            for _, group in groups:
                take = min(len(group), per_group)
                if take:
                    sampled_parts.append(group.iloc[rng.choice(len(group), size=take, replace=False)])
            sampled = pd.concat(sampled_parts, ignore_index=False) if sampled_parts else remaining.iloc[0:0]
            if len(sampled) < budget:
                leftover = remaining.drop(index=sampled.index, errors="ignore")
                add = min(budget - len(sampled), len(leftover))
                if add:
                    sampled = pd.concat([sampled, leftover.iloc[rng.choice(len(leftover), size=add, replace=False)]])
        elif score_column and score_column in remaining.columns:
            numeric = pd.to_numeric(remaining[score_column], errors="coerce")
            try:
                bins = pd.qcut(numeric.rank(method="first"), q=min(20, max(2, budget // 50)), duplicates="drop")
                sampled_parts = []
                group_count = max(1, bins.nunique(dropna=True))
                for _, group in remaining.groupby(bins, observed=True, dropna=False):
                    take = min(len(group), max(1, budget // group_count))
                    sampled_parts.append(group.iloc[rng.choice(len(group), size=take, replace=False)])
                sampled = pd.concat(sampled_parts, ignore_index=False).head(budget)
            except Exception:
                sampled = remaining.iloc[rng.choice(len(remaining), size=min(budget, len(remaining)), replace=False)]
        else:
            sampled = remaining.iloc[rng.choice(len(remaining), size=min(budget, len(remaining)), replace=False)]
        keep.update(map(int, sampled.index.tolist()))

    ordered = sorted(keep)[: int(limit)]
    out = data.loc[ordered].sort_values("__source_row__").reset_index(drop=True)
    manifest = ProgressiveManifest(
        source_rows=source_rows,
        rendered_rows=len(out),
        strategy="selected+extrema+stratified",
        entity_column=entity_column,
        score_column=score_column,
        preserved_extrema=preserved_extrema,
        seed=seed,
    )
    return out, manifest


def infer_uncertainty_columns(frame: pd.DataFrame) -> list[dict[str, str]]:
    columns = {str(column).lower(): str(column) for column in frame.columns}
    pairs: list[dict[str, str]] = []
    for column in frame.columns:
        base = str(column)
        lower_name = base.lower()
        if any(token in lower_name for token in LOWER_HINTS + UPPER_HINTS):
            continue
        candidates_low = [f"{lower_name}_{hint}" for hint in LOWER_HINTS] + [f"{hint}_{lower_name}" for hint in LOWER_HINTS]
        candidates_high = [f"{lower_name}_{hint}" for hint in UPPER_HINTS] + [f"{hint}_{lower_name}" for hint in UPPER_HINTS]
        low = next((columns[name] for name in candidates_low if name in columns), None)
        high = next((columns[name] for name in candidates_high if name in columns), None)
        if low and high:
            pairs.append({"estimate": base, "lower": low, "upper": high})
    # Generic lower/upper pair with inferred estimate.
    if not pairs:
        low = next((columns[name] for name in LOWER_HINTS if name in columns), None)
        high = next((columns[name] for name in UPPER_HINTS if name in columns), None)
        if low and high:
            numeric = [str(c) for c in frame.columns if c not in {low, high} and pd.to_numeric(frame[c], errors="coerce").notna().sum() >= 3]
            if numeric:
                pairs.append({"estimate": numeric[0], "lower": low, "upper": high})
    return pairs


def uncertainty_profile(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for pair in infer_uncertainty_columns(frame):
        estimate = pd.to_numeric(frame[pair["estimate"]], errors="coerce")
        lower = pd.to_numeric(frame[pair["lower"]], errors="coerce")
        upper = pd.to_numeric(frame[pair["upper"]], errors="coerce")
        valid = estimate.notna() & lower.notna() & upper.notna() & (upper >= lower)
        width = (upper - lower).where(valid)
        contains = ((estimate >= lower) & (estimate <= upper)).where(valid)
        rows.append({
            "estimate": pair["estimate"],
            "lower": pair["lower"],
            "upper": pair["upper"],
            "valid_intervals": int(valid.sum()),
            "coverage_pct": round(float(valid.mean() * 100), 2) if len(frame) else 0.0,
            "mean_width": float(width.mean()) if width.notna().any() else np.nan,
            "median_width": float(width.median()) if width.notna().any() else np.nan,
            "estimate_inside_pct": round(float(contains.mean() * 100), 2) if contains.notna().any() else np.nan,
        })
    return pd.DataFrame(rows)


def record_selection(
    *, project_root: str | Path, module_key: str, chart_key: str, column_name: str,
    values: Sequence[Any], source: str = "plotly", action: str = "select", path: str | Path | None = None,
) -> str:
    _ensure_schema(project_root, path=path)
    values_list = [str(value) for value in values][:1000]
    selection_id = "SEL-" + uuid4().hex[:16].upper()
    with connect(project_root, path=path) as connection:
        connection.execute(
            "INSERT INTO selection_history VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (selection_id, module_key, chart_key, column_name, _safe_json(values_list), source, action, utc_now()),
        )
        connection.execute(
            """DELETE FROM selection_history WHERE module_key=? AND selection_id NOT IN (
                SELECT selection_id FROM selection_history WHERE module_key=? ORDER BY created_at_utc DESC LIMIT 500
            )""",
            (module_key, module_key),
        )
        connection.commit()
    return selection_id


def list_selection_history(project_root: str | Path, module_key: str | None = None, *, limit: int = 200, path: str | Path | None = None) -> pd.DataFrame:
    _ensure_schema(project_root, path=path)
    with connect(project_root, path=path) as connection:
        if module_key:
            rows = connection.execute(
                "SELECT * FROM selection_history WHERE module_key=? ORDER BY created_at_utc DESC LIMIT ?",
                (module_key, int(limit)),
            ).fetchall()
        else:
            rows = connection.execute("SELECT * FROM selection_history ORDER BY created_at_utc DESC LIMIT ?", (int(limit),)).fetchall()
    records = []
    for row in rows:
        record = dict(row)
        try:
            record["values"] = json.loads(record.pop("values_json"))
        except Exception:
            record["values"] = []
        records.append(record)
    return pd.DataFrame(records)


def save_visual_provenance(
    *, project_root: str | Path, module_key: str, chart_key: str, entity_id: str,
    source_row: Mapping[str, Any], transformations: Mapping[str, Any] | None = None,
    figure_refs: Sequence[str] | None = None, run_id: str | None = None, path: str | Path | None = None,
) -> str:
    _ensure_schema(project_root, path=path)
    source_json = _safe_json(dict(source_row))
    source_hash = hashlib.sha256(source_json.encode("utf-8")).hexdigest()
    provenance_id = "PRV-" + uuid4().hex[:16].upper()
    with connect(project_root, path=path) as connection:
        connection.execute(
            "INSERT INTO visual_provenance VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (provenance_id, module_key, run_id, chart_key, str(entity_id), source_hash, source_json,
             _safe_json(dict(transformations or {})), _safe_json(list(figure_refs or [])), utc_now()),
        )
        connection.commit()
    return provenance_id


def list_visual_provenance(project_root: str | Path, module_key: str | None = None, *, limit: int = 200, path: str | Path | None = None) -> pd.DataFrame:
    _ensure_schema(project_root, path=path)
    with connect(project_root, path=path) as connection:
        if module_key:
            rows = connection.execute(
                "SELECT * FROM visual_provenance WHERE module_key=? ORDER BY created_at_utc DESC LIMIT ?",
                (module_key, int(limit)),
            ).fetchall()
        else:
            rows = connection.execute("SELECT * FROM visual_provenance ORDER BY created_at_utc DESC LIMIT ?", (int(limit),)).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def create_review_thread(
    *, project_root: str | Path, module_key: str, entity_id: str, title: str,
    created_by: str, assignee: str = "", status: str = "Open", due_at_utc: str | None = None,
    run_id: str | None = None, path: str | Path | None = None,
) -> str:
    _ensure_schema(project_root, path=path)
    thread_id = "THR-" + uuid4().hex[:16].upper()
    now = utc_now()
    with connect(project_root, path=path) as connection:
        connection.execute(
            "INSERT INTO review_threads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (thread_id, module_key, run_id, str(entity_id), title.strip() or "Scientific review",
             assignee.strip(), status, due_at_utc, created_by.strip() or "local-reviewer", now, now),
        )
        connection.commit()
    return thread_id


def add_review_comment(
    *, project_root: str | Path, thread_id: str, author: str, body: str,
    decision: str = "Comment", path: str | Path | None = None,
) -> str:
    _ensure_schema(project_root, path=path)
    if not body.strip():
        raise ValueError("Review comment cannot be empty.")
    comment_id = "CMT-" + uuid4().hex[:16].upper()
    now = utc_now()
    with connect(project_root, path=path) as connection:
        exists = connection.execute("SELECT 1 FROM review_threads WHERE thread_id=?", (thread_id,)).fetchone()
        if not exists:
            raise ValueError("Unknown review thread.")
        connection.execute(
            "INSERT INTO review_comments VALUES (?, ?, ?, ?, ?, ?)",
            (comment_id, thread_id, author.strip() or "local-reviewer", body.strip(), decision, now),
        )
        connection.execute("UPDATE review_threads SET updated_at_utc=? WHERE thread_id=?", (now, thread_id))
        connection.commit()
    return comment_id


def update_review_thread(
    *, project_root: str | Path, thread_id: str, status: str | None = None,
    assignee: str | None = None, path: str | Path | None = None,
) -> bool:
    _ensure_schema(project_root, path=path)
    updates: list[str] = []
    values: list[Any] = []
    if status is not None:
        updates.append("status=?"); values.append(status)
    if assignee is not None:
        updates.append("assignee=?"); values.append(assignee)
    if not updates:
        return False
    updates.append("updated_at_utc=?"); values.append(utc_now()); values.append(thread_id)
    with connect(project_root, path=path) as connection:
        cursor = connection.execute(f"UPDATE review_threads SET {', '.join(updates)} WHERE thread_id=?", values)
        connection.commit()
    return bool(cursor.rowcount)


def list_review_threads(project_root: str | Path, module_key: str | None = None, *, path: str | Path | None = None) -> pd.DataFrame:
    _ensure_schema(project_root, path=path)
    with connect(project_root, path=path) as connection:
        if module_key:
            rows = connection.execute(
                """SELECT t.*, COUNT(c.comment_id) AS comment_count
                   FROM review_threads t LEFT JOIN review_comments c ON c.thread_id=t.thread_id
                   WHERE t.module_key=? GROUP BY t.thread_id ORDER BY t.updated_at_utc DESC""",
                (module_key,),
            ).fetchall()
        else:
            rows = connection.execute(
                """SELECT t.*, COUNT(c.comment_id) AS comment_count
                   FROM review_threads t LEFT JOIN review_comments c ON c.thread_id=t.thread_id
                   GROUP BY t.thread_id ORDER BY t.updated_at_utc DESC"""
            ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def list_review_comments(project_root: str | Path, thread_id: str, *, path: str | Path | None = None) -> pd.DataFrame:
    _ensure_schema(project_root, path=path)
    with connect(project_root, path=path) as connection:
        rows = connection.execute(
            "SELECT * FROM review_comments WHERE thread_id=? ORDER BY created_at_utc ASC", (thread_id,)
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def save_viewer_sync_state(
    *, project_root: str | Path, module_key: str, state: Mapping[str, Any], path: str | Path | None = None,
) -> None:
    _ensure_schema(project_root, path=path)
    with connect(project_root, path=path) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO viewer_sync_state(module_key, state_json, updated_at_utc) VALUES (?, ?, ?)",
            (module_key, _safe_json(dict(state)), utc_now()),
        )
        connection.commit()


def get_viewer_sync_state(project_root: str | Path, module_key: str, *, path: str | Path | None = None) -> dict[str, Any]:
    _ensure_schema(project_root, path=path)
    with connect(project_root, path=path) as connection:
        row = connection.execute("SELECT state_json FROM viewer_sync_state WHERE module_key=?", (module_key,)).fetchone()
    if not row:
        return {}
    try:
        return dict(json.loads(row[0]))
    except Exception:
        return {}


def save_figure_layout(
    *, project_root: str | Path, module_key: str, name: str, preset: str,
    panels: Sequence[Mapping[str, Any]], caption: str = "", methods: str = "",
    run_id: str | None = None, width_mm: float | None = None, height_mm: float | None = None,
    dpi: int | None = None, columns_count: int | None = None, path: str | Path | None = None,
) -> str:
    _ensure_schema(project_root, path=path)
    defaults = JOURNAL_PRESETS.get(preset, JOURNAL_PRESETS["Nature two-column"])
    layout_id = "FIG-" + uuid4().hex[:16].upper()
    now = utc_now()
    with connect(project_root, path=path) as connection:
        connection.execute(
            "INSERT INTO figure_layouts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (layout_id, module_key, run_id, name.strip() or "Publication figure", preset,
             float(width_mm or defaults["width_mm"]), float(height_mm or defaults["height_mm"]),
             int(dpi or defaults["dpi"]), int(columns_count or defaults["columns"]),
             _safe_json(list(panels)), caption, methods, now, now),
        )
        connection.commit()
    return layout_id


def list_figure_layouts(project_root: str | Path, module_key: str | None = None, *, path: str | Path | None = None) -> pd.DataFrame:
    _ensure_schema(project_root, path=path)
    with connect(project_root, path=path) as connection:
        if module_key:
            rows = connection.execute("SELECT * FROM figure_layouts WHERE module_key=? ORDER BY updated_at_utc DESC", (module_key,)).fetchall()
        else:
            rows = connection.execute("SELECT * FROM figure_layouts ORDER BY updated_at_utc DESC").fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def _svg_panel(x: float, y: float, width: float, height: float, label: str, title: str, values: Sequence[float]) -> str:
    safe_title = html.escape(title)
    safe_label = html.escape(label)
    bars = []
    numeric = [float(v) for v in values if isinstance(v, (int, float, np.number)) and math.isfinite(float(v))][:20]
    if numeric:
        low, high = min(numeric), max(numeric)
        span = high - low or 1.0
        bar_w = max(1.0, (width - 24) / max(1, len(numeric)))
        for index, value in enumerate(numeric):
            bar_h = max(2.0, (value - low) / span * max(8.0, height - 54))
            bx = x + 12 + index * bar_w
            by = y + height - 16 - bar_h
            bars.append(f'<rect x="{bx:.2f}" y="{by:.2f}" width="{bar_w * .72:.2f}" height="{bar_h:.2f}" rx="1.5" fill="#4f46e5" opacity=".78"/>')
    else:
        bars.append(f'<text x="{x + width/2:.2f}" y="{y + height/2:.2f}" text-anchor="middle" font-size="9" fill="#64748b">No numeric preview</text>')
    return (
        f'<g><rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{height:.2f}" rx="4" fill="#ffffff" stroke="#94a3b8"/>'
        f'<text x="{x + 6:.2f}" y="{y + 13:.2f}" font-size="11" font-weight="700">{safe_label}</text>'
        f'<text x="{x + 24:.2f}" y="{y + 13:.2f}" font-size="8.5" fill="#334155">{safe_title[:70]}</text>'
        f'{"".join(bars)}</g>'
    )


def build_figure_layout_bundle(
    *, module_key: str, layout_name: str, preset: str, panels: Sequence[Mapping[str, Any]],
    caption: str = "", methods: str = "", boundary: str = "Research use only",
) -> bytes:
    defaults = JOURNAL_PRESETS.get(preset, JOURNAL_PRESETS["Nature two-column"])
    width = float(defaults["width_mm"])
    height = float(defaults["height_mm"])
    columns = int(defaults["columns"])
    rows = max(1, math.ceil(max(1, len(panels)) / columns))
    margin = 7.0
    gap = 4.0
    panel_w = (width - 2 * margin - gap * (columns - 1)) / columns
    panel_h = (height - 2 * margin - gap * (rows - 1)) / rows
    svg_panels: list[str] = []
    for index, panel in enumerate(panels):
        row, col = divmod(index, columns)
        x = margin + col * (panel_w + gap)
        y = margin + row * (panel_h + gap)
        values = panel.get("values", []) if isinstance(panel, Mapping) else []
        svg_panels.append(_svg_panel(x, y, panel_w, panel_h, chr(65 + index), str(panel.get("title", f"Panel {index + 1}")), values))
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}">'
        '<rect width="100%" height="100%" fill="#ffffff"/>' + "".join(svg_panels) + '</svg>'
    )
    manifest = {
        "schema": "biointel.figure-layout.v1",
        "module_key": module_key,
        "layout_name": layout_name,
        "preset": preset,
        "dimensions_mm": [width, height],
        "dpi": defaults["dpi"],
        "panels": list(panels),
        "caption": caption,
        "methods": methods,
        "boundary": boundary,
        "created_at_utc": utc_now(),
        "journal_acceptance_claimed": False,
    }
    html_report = f"""<!doctype html><meta charset='utf-8'><title>{html.escape(layout_name)}</title>
    <style>body{{font-family:Arial,sans-serif;max-width:1200px;margin:2rem auto;line-height:1.45}}object{{width:100%;border:1px solid #ddd}}</style>
    <h1>{html.escape(layout_name)}</h1><object data='figure_layout.svg' type='image/svg+xml'></object>
    <h2>Caption</h2><p>{html.escape(caption)}</p><h2>Methods</h2><p>{html.escape(methods)}</p>
    <p><strong>Boundary:</strong> {html.escape(boundary)}</p>"""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("figure/figure_layout.svg", svg)
        archive.writestr("figure/figure_layout.html", html_report)
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False, default=str))
        archive.writestr("README.txt", "Editable SVG multi-panel layout. Verify labels, statistics and scientific claims before submission.\n")
    return output.getvalue()


def visual_fingerprint(figure: Any, data: pd.DataFrame, *, title: str = "") -> str:
    try:
        figure_json = figure.to_json()
    except Exception:
        figure_json = _safe_json(str(figure))
    frame = pd.DataFrame(data).head(20_000).copy()
    for column in frame.columns:
        if frame[column].dtype == "object":
            frame[column] = frame[column].map(lambda value: _safe_json(value) if isinstance(value, (dict, list, tuple)) else str(value))
    data_hash = hashlib.sha256(pd.util.hash_pandas_object(frame, index=True).values.tobytes()).hexdigest() if not frame.empty else "empty"
    return hashlib.sha256(f"{title}|{figure_json}|{data_hash}".encode("utf-8")).hexdigest()


def save_visual_fingerprint(
    *, project_root: str | Path, module_key: str, chart_key: str, fingerprint: str,
    metadata: Mapping[str, Any] | None = None, approved: bool = False, path: str | Path | None = None,
) -> str:
    _ensure_schema(project_root, path=path)
    fingerprint_id = "VFP-" + uuid4().hex[:16].upper()
    with connect(project_root, path=path) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO visual_fingerprints VALUES (?, ?, ?, ?, ?, ?, ?)",
            (fingerprint_id, module_key, chart_key, fingerprint, _safe_json(dict(metadata or {})), int(approved), utc_now()),
        )
        row = connection.execute(
            "SELECT fingerprint_id FROM visual_fingerprints WHERE module_key=? AND chart_key=? AND fingerprint=?",
            (module_key, chart_key, fingerprint),
        ).fetchone()
        connection.commit()
    return str(row[0]) if row else fingerprint_id


def list_visual_fingerprints(project_root: str | Path, module_key: str | None = None, *, path: str | Path | None = None) -> pd.DataFrame:
    _ensure_schema(project_root, path=path)
    with connect(project_root, path=path) as connection:
        if module_key:
            rows = connection.execute("SELECT * FROM visual_fingerprints WHERE module_key=? ORDER BY created_at_utc DESC", (module_key,)).fetchall()
        else:
            rows = connection.execute("SELECT * FROM visual_fingerprints ORDER BY created_at_utc DESC").fetchall()
    return pd.DataFrame([dict(row) for row in rows])
