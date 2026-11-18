"""Compact, user-facing canvases for operational JSON payloads.

Platform modules persist rich JSON manifests for provenance and support.  They
are useful, but rendering the entire payload as the first thing a scientist
sees produces a debugger-like screen rather than an understandable workflow.
This module converts those payloads into safe metrics, a small fact table and
an optional redacted technical detail view.
"""

from __future__ import annotations

import html
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

try:  # Keep non-UI helpers importable in CLI and test environments.
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - Streamlit supplies the UI runtime.
    st = None  # type: ignore[assignment]


_SENSITIVE_MARKERS = (
    "password",
    "secret",
    "token",
    "authorization",
    "credential",
    "private_key",
    "api_key",
)
_PATH_MARKERS = ("path", "directory", "folder", "location")
_STRUCTURED_MARKERS = ("_json", "payload", "checkpoint", "manifest", "result")
_PRIMARY_METRICS = (
    "status",
    "progress",
    "records",
    "patients",
    "assets",
    "attempt",
    "rating",
    "runtime",
    "duration",
    "job_id",
    "project_id",
)


def human_label(value: str) -> str:
    """Turn a machine field name into a concise, readable label."""

    return str(value).replace(".", " · ").replace("_", " ").strip().title()


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _short_hash(value: str) -> str:
    return value if len(value) <= 18 else f"{value[:10]}…{value[-6:]}"


def safe_canvas_value(field: str, value: Any) -> str:
    """Redact host paths/secrets and compact verbose machine values."""

    lower = str(field).lower()
    if any(marker in lower for marker in _SENSITIVE_MARKERS):
        return "Redacted"
    if value is None:
        return "—"
    if any(marker in lower for marker in _PATH_MARKERS):
        text = str(value).replace("\\", "/")
        filename = Path(text).name
        return filename or "Local workspace asset"
    if "sha256" in lower or lower.endswith("_hash"):
        return _short_hash(str(value))
    if any(marker in lower for marker in _STRUCTURED_MARKERS):
        return "Structured details available"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return f"{value:,.4g}"
    text = str(value)
    return text if len(text) <= 96 else f"{text[:92]}…"


def _flatten_scalars(
    value: Any,
    *,
    prefix: str = "",
    limit: int = 32,
) -> list[tuple[str, Any]]:
    """Extract stable scalar facts without dumping nested JSON into the UI."""

    rows: list[tuple[str, Any]] = []

    def visit(current: Any, path: str) -> None:
        if len(rows) >= limit:
            return
        if _is_scalar(current):
            if path:
                rows.append((path, current))
            return
        if isinstance(current, Mapping):
            for key, item in current.items():
                next_path = f"{path}.{key}" if path else str(key)
                visit(item, next_path)
                if len(rows) >= limit:
                    return
            return
        if isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)):
            if path:
                rows.append((path, f"{len(current):,} item(s)"))

    visit(value, prefix)
    return rows


def _payload_mapping(payload: Any) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        return {str(key): value for key, value in payload.items()}
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return {"items": list(payload)}
    return {"value": payload}


def canvas_snapshot(payload: Any, *, max_metrics: int = 4) -> dict[str, Any]:
    """Return UI-safe metrics and facts; useful for regression tests as well."""

    normalized = _payload_mapping(payload)
    facts = _flatten_scalars(normalized)
    rendered_facts = [
        {"Field": human_label(field), "Value": safe_canvas_value(field, value), "_field": field}
        for field, value in facts
    ]

    metrics: list[dict[str, str]] = []
    used: set[str] = set()
    for marker in _PRIMARY_METRICS:
        for row, (_, raw_value) in zip(rendered_facts, facts):
            field = str(row["_field"]).lower()
            if marker in field and row["_field"] not in used:
                value = str(row["Value"])
                if marker == "progress" and value not in {"—", ""}:
                    try:
                        numeric = float(raw_value)
                        value = f"{numeric * 100:.0f}%" if numeric <= 1 else f"{numeric:.0f}%"
                    except (TypeError, ValueError):
                        pass
                metrics.append({"label": str(row["Field"]), "value": value})
                used.add(str(row["_field"]))
                break
        if len(metrics) >= max_metrics:
            break
    if len(metrics) < max_metrics:
        for row in rendered_facts:
            if row["_field"] in used:
                continue
            metrics.append({"label": str(row["Field"]), "value": str(row["Value"])})
            used.add(str(row["_field"]))
            if len(metrics) >= max_metrics:
                break
    return {
        "metrics": metrics,
        "facts": [{"Field": row["Field"], "Value": row["Value"]} for row in rendered_facts if row["_field"] not in used][:16],
        "raw": normalized,
    }


def _redacted_payload(value: Any, *, field: str = "") -> Any:
    if _is_scalar(value):
        return safe_canvas_value(field, value)
    if isinstance(value, Mapping):
        return {str(key): _redacted_payload(item, field=str(key)) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_redacted_payload(item, field=field) for item in list(value)[:100]]
    return safe_canvas_value(field, value)


def _workflow_html(stages: Sequence[str]) -> str:
    items = "".join(
        f'<div class="bio-operational-canvas-stage"><b>{index}</b><span>{html.escape(str(stage))}</span></div>'
        for index, stage in enumerate(stages, start=1)
    )
    return (
        "<style>"
        ".bio-operational-canvas-stages{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:10px 0 14px;}"
        ".bio-operational-canvas-stage{display:flex;align-items:center;gap:8px;padding:9px 10px;border:1px solid rgba(114,142,215,.24);border-radius:12px;background:rgba(82,112,185,.08);min-width:0;}"
        ".bio-operational-canvas-stage b{display:grid;place-items:center;flex:none;width:22px;height:22px;border-radius:50%;background:rgba(83,122,221,.25);font-size:.72rem;}"
        ".bio-operational-canvas-stage span{font-size:.77rem;line-height:1.2;overflow:hidden;text-overflow:ellipsis;}"
        "@media(max-width:850px){.bio-operational-canvas-stages{grid-template-columns:repeat(2,minmax(0,1fr));}}"
        "</style>"
        f'<div class="bio-operational-canvas-stages">{items}</div>'
    )


def render_operational_canvas(
    title: str,
    payload: Any,
    workflow: Sequence[str] = (),
    empty_message: str = "",
    *,
    subtitle: str = "",
    stages: Sequence[str] = (),
    technical_label: str = "Redacted technical details",
    key: str | None = None,
) -> None:
    """Render a clear operational canvas with raw details kept out of the main flow.

    ``workflow`` is retained as a concise compatibility alias for ``stages`` so
    pages can describe their scientific flow in the most natural language.
    """

    if st is None:  # pragma: no cover - rendering requires Streamlit.
        return
    is_empty_collection = (
        isinstance(payload, (Mapping, Sequence))
        and not isinstance(payload, (str, bytes, bytearray))
        and len(payload) == 0
    )
    if payload is None or is_empty_collection:
        st.info(empty_message or "No operational state is available yet.")
        return
    snapshot = canvas_snapshot(payload)
    active_stages = tuple(stages or workflow)
    with st.container(border=True):
        st.markdown(f"#### {html.escape(title)}")
        if subtitle:
            st.caption(subtitle)
        metrics = snapshot["metrics"]
        if metrics:
            columns = st.columns(len(metrics))
            for column, metric in zip(columns, metrics):
                column.metric(metric["label"], metric["value"])
        if active_stages:
            st.markdown(_workflow_html(active_stages), unsafe_allow_html=True)
        facts = snapshot["facts"]
        if facts:
            st.dataframe(
                pd.DataFrame(facts),
                width="stretch",
                hide_index=True,
                height=min(360, 72 + len(facts) * 35),
                key=f"{key}_facts" if key else None,
            )
        with st.expander(technical_label, expanded=False):
            st.code(
                json.dumps(_redacted_payload(snapshot["raw"]), indent=2, default=str),
                language="json",
            )


__all__ = ["canvas_snapshot", "human_label", "render_operational_canvas", "safe_canvas_value"]
