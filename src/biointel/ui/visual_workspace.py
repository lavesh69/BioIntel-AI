from __future__ import annotations

import hashlib
import io
import json
import sqlite3
from biointel.database.core import managed_connect
import textwrap
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import plotly.graph_objects as go

PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DB_PATH = PROJECT_ROOT / "workspace" / "visual_workspace.sqlite3"

ACCESSIBILITY_PRESETS: tuple[str, ...] = (
    "Standard",
    "High contrast",
    "Colour-blind safe",
    "Print / grayscale",
)

_EVIDENCE_LABELS = {
    "demo": "Demonstration data",
    "synthetic": "Synthetic data",
    "reference": "Reference data",
    "real_imported": "Imported real data",
    "internal_validation": "Internally validated",
    "external_validation": "Externally validated",
    "prospective_validation": "Prospectively validated",
    "unspecified": "Source status not declared",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect(path: Path | None = None) -> sqlite3.Connection:
    target = Path(path or _DB_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = managed_connect(target, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS visual_views (
            view_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            module_key TEXT NOT NULL,
            chart_key TEXT NOT NULL,
            title TEXT NOT NULL,
            evidence_status TEXT NOT NULL,
            configuration_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_visual_views_module ON visual_views(module_key, updated_at_utc DESC);
        CREATE TABLE IF NOT EXISTS visual_annotations (
            annotation_id TEXT PRIMARY KEY,
            module_key TEXT NOT NULL,
            chart_key TEXT NOT NULL,
            visual_title TEXT NOT NULL,
            note TEXT NOT NULL,
            selected_rows_json TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_visual_annotations_chart ON visual_annotations(module_key, chart_key, created_at_utc DESC);
        CREATE TABLE IF NOT EXISTS visual_errors (
            error_id TEXT PRIMARY KEY,
            module_key TEXT NOT NULL,
            chart_key TEXT NOT NULL,
            error_type TEXT NOT NULL,
            error_message TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );
        """
    )
    return connection


def evidence_label(value: str | None) -> str:
    key = str(value or "unspecified").strip().lower()
    return _EVIDENCE_LABELS.get(key, str(value or _EVIDENCE_LABELS["unspecified"]))


def infer_evidence_status(data: pd.DataFrame | None, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    frame = pd.DataFrame() if data is None else pd.DataFrame(data)
    if frame.empty:
        return "unspecified"
    for column in ("evidence_status", "source_kind", "data_status", "scientific_status"):
        if column in frame.columns:
            values = " ".join(frame[column].dropna().astype(str).head(20)).lower()
            if "prospective" in values:
                return "prospective_validation"
            if "external" in values or "independent" in values:
                return "external_validation"
            if "internal" in values or "validated" in values:
                return "internal_validation"
            if "real" in values or "import" in values or "public" in values:
                return "real_imported"
            if "synthetic" in values:
                return "synthetic"
            if "demo" in values:
                return "demo"
            if "reference" in values:
                return "reference"
    for column in ("synthetic_demo", "is_synthetic"):
        if column in frame.columns and frame[column].fillna(False).astype(bool).any():
            return "synthetic"
    return "unspecified"


def apply_accessibility_preset(figure: Any, preset: str) -> go.Figure:
    fig = go.Figure(figure)
    preset = preset if preset in ACCESSIBILITY_PRESETS else "Standard"
    if preset == "High contrast":
        colorway = ["#FFFFFF", "#FFD60A", "#00E5FF", "#FF4D6D", "#7CFF6B", "#C77DFF"]
        fig.update_layout(
            template="plotly_dark",
            colorway=colorway,
            paper_bgcolor="#000000",
            plot_bgcolor="#000000",
            font={"color": "#FFFFFF", "size": 15},
        )
        fig.update_xaxes(showgrid=True, gridcolor="#606060", zerolinecolor="#FFFFFF")
        fig.update_yaxes(showgrid=True, gridcolor="#606060", zerolinecolor="#FFFFFF")
    elif preset == "Colour-blind safe":
        colorway = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#D55E00", "#56B4E9", "#F0E442"]
        fig.update_layout(colorway=colorway)
        marker_symbols = ["circle", "square", "diamond", "cross", "triangle-up", "triangle-down", "x"]
        for index, trace in enumerate(fig.data):
            if hasattr(trace, "marker"):
                try:
                    trace.marker.symbol = marker_symbols[index % len(marker_symbols)]
                except (AttributeError, ValueError):
                    pass
    elif preset == "Print / grayscale":
        grays = ["#111111", "#404040", "#707070", "#9A9A9A", "#BDBDBD", "#D9D9D9"]
        fig.update_layout(
            template="plotly_white",
            colorway=grays,
            paper_bgcolor="#FFFFFF",
            plot_bgcolor="#FFFFFF",
            font={"color": "#111111"},
        )
        for index, trace in enumerate(fig.data):
            if hasattr(trace, "line"):
                try:
                    trace.line.dash = ["solid", "dash", "dot", "dashdot"][index % 4]
                except (AttributeError, ValueError):
                    pass
    return fig


def visual_text_summary(data: pd.DataFrame | None, title: str) -> str:
    frame = pd.DataFrame() if data is None else pd.DataFrame(data)
    if frame.empty:
        return f"{title}. No underlying records are available for a numerical summary."
    parts = [f"{title} contains {len(frame):,} displayed record(s) across {len(frame.columns):,} field(s)."]
    numeric = frame.select_dtypes(include="number")
    if not numeric.empty:
        column = numeric.columns[0]
        values = pd.to_numeric(numeric[column], errors="coerce").dropna()
        if not values.empty:
            parts.append(
                f"{column.replace('_', ' ')} ranges from {values.min():.4g} to {values.max():.4g}, with a median of {values.median():.4g}."
            )
    categorical = [column for column in frame.columns if column not in numeric.columns]
    if categorical:
        column = categorical[0]
        counts = frame[column].astype(str).value_counts(dropna=False)
        if not counts.empty:
            parts.append(f"The most frequent {column.replace('_', ' ')} is {counts.index[0]} ({int(counts.iloc[0])} record(s)).")
    missing = int(frame.isna().sum().sum())
    if missing:
        parts.append(f"The displayed data contain {missing:,} missing cell(s).")
    return " ".join(parts)


def save_view(
    *,
    name: str,
    module_key: str,
    chart_key: str,
    title: str,
    evidence_status: str,
    configuration: Mapping[str, Any],
    path: Path | None = None,
) -> str:
    payload = json.dumps(dict(configuration), sort_keys=True, default=str)
    view_id = hashlib.sha256(f"{module_key}|{chart_key}|{name}|{payload}".encode("utf-8")).hexdigest()[:24]
    now = utc_now()
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO visual_views(view_id, name, module_key, chart_key, title, evidence_status,
                                     configuration_json, created_at_utc, updated_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(view_id) DO UPDATE SET
                name=excluded.name,
                title=excluded.title,
                evidence_status=excluded.evidence_status,
                configuration_json=excluded.configuration_json,
                updated_at_utc=excluded.updated_at_utc
            """,
            (view_id, name, module_key, chart_key, title, evidence_status, payload, now, now),
        )
        connection.commit()
    return view_id


def list_views(module_key: str, path: Path | None = None) -> pd.DataFrame:
    with _connect(path) as connection:
        rows = connection.execute(
            """SELECT view_id, name, chart_key, title, evidence_status, configuration_json,
                      created_at_utc, updated_at_utc
               FROM visual_views WHERE module_key=? ORDER BY updated_at_utc DESC LIMIT 100""",
            (module_key,),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def save_annotation(
    *,
    module_key: str,
    chart_key: str,
    visual_title: str,
    note: str,
    selected_rows: list[int],
    created_by: str = "local-user",
    path: Path | None = None,
) -> str:
    now = utc_now()
    seed = f"{module_key}|{chart_key}|{note}|{selected_rows}|{now}"
    annotation_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    with _connect(path) as connection:
        connection.execute(
            """INSERT INTO visual_annotations(annotation_id, module_key, chart_key, visual_title,
                      note, selected_rows_json, created_by, created_at_utc)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (annotation_id, module_key, chart_key, visual_title, note,
             json.dumps(selected_rows), created_by, now),
        )
        connection.commit()
    return annotation_id


def list_annotations(module_key: str, chart_key: str, path: Path | None = None) -> pd.DataFrame:
    with _connect(path) as connection:
        rows = connection.execute(
            """SELECT annotation_id, note, selected_rows_json, created_by, created_at_utc
               FROM visual_annotations WHERE module_key=? AND chart_key=?
               ORDER BY created_at_utc DESC LIMIT 100""",
            (module_key, chart_key),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def record_visual_error(
    *, module_key: str, chart_key: str, error: Exception, path: Path | None = None
) -> str:
    now = utc_now()
    seed = f"{module_key}|{chart_key}|{type(error).__name__}|{error}|{now}"
    error_id = "VIS-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12].upper()
    with _connect(path) as connection:
        connection.execute(
            """INSERT OR REPLACE INTO visual_errors(error_id, module_key, chart_key, error_type,
                      error_message, created_at_utc) VALUES (?, ?, ?, ?, ?, ?)""",
            (error_id, module_key, chart_key, type(error).__name__, str(error)[:2000], now),
        )
        connection.commit()
    return error_id


def _document_bytes(title: str, summary: str, metadata: Mapping[str, Any], data: pd.DataFrame) -> tuple[bytes, bytes, bytes]:
    # These formats are intentionally text/table based so the report works without Kaleido.
    from docx import Document
    from pptx import Presentation
    from pptx.util import Inches
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib import colors

    doc = Document()
    doc.add_heading(title, level=1)
    doc.add_paragraph(summary)
    for key, value in metadata.items():
        doc.add_paragraph(f"{key}: {value}")
    if not data.empty:
        table = doc.add_table(rows=1, cols=min(len(data.columns), 8))
        columns = list(data.columns[:8])
        for index, column in enumerate(columns):
            table.rows[0].cells[index].text = str(column)
        for _, row in data.head(30).iterrows():
            cells = table.add_row().cells
            for index, column in enumerate(columns):
                cells[index].text = str(row[column])[:120]
    doc_buf = io.BytesIO()
    doc.save(doc_buf)

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = title
    box = slide.shapes.add_textbox(Inches(0.7), Inches(1.4), Inches(8.6), Inches(5.3))
    text_frame = box.text_frame
    text_frame.text = summary
    for key, value in metadata.items():
        paragraph = text_frame.add_paragraph()
        paragraph.text = f"{key}: {value}"
    ppt_buf = io.BytesIO()
    prs.save(ppt_buf)

    pdf_buf = io.BytesIO()
    styles = getSampleStyleSheet()
    story: list[Any] = [Paragraph(title, styles["Title"]), Spacer(1, 12), Paragraph(summary, styles["BodyText"]), Spacer(1, 12)]
    for key, value in metadata.items():
        story.append(Paragraph(f"<b>{key}</b>: {value}", styles["BodyText"]))
    if not data.empty:
        columns = list(data.columns[:6])
        rows = [columns] + [[str(value)[:60] for value in row] for row in data[columns].head(25).itertuples(index=False, name=None)]
        table = Table(rows, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE8F8")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
        ]))
        story.extend([Spacer(1, 12), table])
    SimpleDocTemplate(pdf_buf, pagesize=A4).build(story)
    return doc_buf.getvalue(), ppt_buf.getvalue(), pdf_buf.getvalue()


def build_visual_report_bundle(
    *,
    title: str,
    interpretation: str,
    method: str | None,
    units: str | None,
    evidence_status: str,
    figure: Any,
    data: pd.DataFrame | None,
    configuration: Mapping[str, Any] | None = None,
) -> bytes:
    frame = pd.DataFrame() if data is None else pd.DataFrame(data)
    metadata = {
        "Evidence status": evidence_label(evidence_status),
        "Method": method or "Not specified",
        "Units": units or "Not specified",
        "Displayed records": len(frame),
        "Generated at": utc_now(),
    }
    summary = visual_text_summary(frame, title)
    buffer = io.BytesIO()
    figure_json = go.Figure(figure).to_json()
    html = go.Figure(figure).to_html(full_html=True, include_plotlyjs="cdn")
    docx_bytes, pptx_bytes, pdf_bytes = _document_bytes(title, summary, metadata, frame)
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("visual/interactive_chart.html", html)
        archive.writestr("visual/figure.json", figure_json)
        archive.writestr("data/displayed_records.csv", frame.to_csv(index=False))
        archive.writestr("report/visual_report.docx", docx_bytes)
        archive.writestr("report/visual_report.pptx", pptx_bytes)
        archive.writestr("report/visual_report.pdf", pdf_bytes)
        manifest = {
            "schema": "biointel.visual-report.v1",
            "title": title,
            "interpretation": interpretation,
            "summary": summary,
            "metadata": metadata,
            "configuration": dict(configuration or {}),
        }
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True, default=str))
        archive.writestr(
            "README.txt",
            textwrap.dedent(
                f"""\
                BioIntel AI visual report bundle
                ================================
                Title: {title}
                Evidence: {evidence_label(evidence_status)}

                Open visual/interactive_chart.html for the interactive chart.
                The PDF, DOCX and PPTX reports contain the interpretation, provenance and a bounded data preview.
                """
            ),
        )
    return buffer.getvalue()


def list_all_views(path: Path | None = None) -> pd.DataFrame:
    with _connect(path) as connection:
        rows = connection.execute(
            """SELECT view_id, name, module_key, chart_key, title, evidence_status,
                      configuration_json, created_at_utc, updated_at_utc
               FROM visual_views ORDER BY updated_at_utc DESC LIMIT 1000"""
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def list_all_annotations(path: Path | None = None) -> pd.DataFrame:
    with _connect(path) as connection:
        rows = connection.execute(
            """SELECT annotation_id, module_key, chart_key, visual_title, note,
                      selected_rows_json, created_by, created_at_utc
               FROM visual_annotations ORDER BY created_at_utc DESC LIMIT 1000"""
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def list_visual_errors(path: Path | None = None) -> pd.DataFrame:
    with _connect(path) as connection:
        rows = connection.execute(
            """SELECT error_id, module_key, chart_key, error_type, error_message, created_at_utc
               FROM visual_errors ORDER BY created_at_utc DESC LIMIT 1000"""
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def delete_view(view_id: str, path: Path | None = None) -> bool:
    with _connect(path) as connection:
        cursor = connection.execute("DELETE FROM visual_views WHERE view_id=?", (view_id,))
        connection.commit()
    return bool(cursor.rowcount)

_LINKED_ENTITY_COLUMNS: tuple[str, ...] = (
    "patient_id", "patient", "subject", "sample_id", "sample", "slide_id", "slide",
    "isolate_id", "isolate", "cell", "cluster", "region", "candidate_id", "candidate",
    "variant_id", "variant", "gene", "transcript", "isoform", "construct_id", "construct",
    "model_id", "model", "drug", "compound", "ligand", "event", "path", "population",
)


def _linked_key(module_key: str) -> str:
    return f"biointel_linked_selection_{module_key}"


def _linked_history_key(module_key: str) -> str:
    return f"biointel_linked_selection_history_{module_key}"


def _linked_redo_key(module_key: str) -> str:
    return f"biointel_linked_selection_redo_{module_key}"


def _push_linked_history(module_key: str, value: dict[str, Any] | None) -> None:
    import streamlit as st

    if not isinstance(value, dict):
        return
    history = list(st.session_state.get(_linked_history_key(module_key), []))
    if not history or history[-1] != value:
        history.append(dict(value))
    st.session_state[_linked_history_key(module_key)] = history[-50:]
    st.session_state[_linked_redo_key(module_key)] = []


def publish_linked_selection(
    module_key: str, selected: pd.DataFrame, *, source_chart: str = ""
) -> dict[str, Any] | None:
    """Publish a chart selection with bounded undo/redo and durable audit history."""
    import streamlit as st

    frame = pd.DataFrame(selected)
    if frame.empty:
        return None
    lower_map = {str(column).lower(): str(column) for column in frame.columns}
    column = next((lower_map[name] for name in _LINKED_ENTITY_COLUMNS if name in lower_map), None)
    if column is None:
        candidates = [
            str(column_name)
            for column_name in frame.columns
            if not pd.api.types.is_numeric_dtype(frame[column_name])
            and 0 < frame[column_name].nunique(dropna=True) <= 500
        ]
        column = candidates[0] if candidates else None
    if column is None:
        return None
    values = frame[column].dropna().astype(str).drop_duplicates().head(500).tolist()
    if not values:
        return None
    previous = st.session_state.get(_linked_key(module_key))
    _push_linked_history(module_key, dict(previous) if isinstance(previous, dict) else None)
    context = {
        "column": column,
        "values": values,
        "source": "plotly_selection",
        "source_chart": str(source_chart),
        "updated_at_utc": utc_now(),
    }
    st.session_state[_linked_key(module_key)] = context
    try:
        from biointel.nextgen.interaction_v131 import record_selection
        from pathlib import Path

        project_root = Path(__file__).resolve().parents[3]
        record_selection(
            project_root=project_root, module_key=module_key, chart_key=str(source_chart or "unknown"),
            column_name=column, values=values, source="plotly", action="select",
        )
    except Exception:
        pass
    return context


def get_linked_selection(module_key: str) -> dict[str, Any] | None:
    import streamlit as st

    value = st.session_state.get(_linked_key(module_key))
    return dict(value) if isinstance(value, dict) else None


def linked_selection_history(module_key: str) -> list[dict[str, Any]]:
    import streamlit as st

    return [dict(item) for item in st.session_state.get(_linked_history_key(module_key), []) if isinstance(item, dict)]


def undo_linked_selection(module_key: str) -> dict[str, Any] | None:
    import streamlit as st

    history = list(st.session_state.get(_linked_history_key(module_key), []))
    if not history:
        return get_linked_selection(module_key)
    current = st.session_state.get(_linked_key(module_key))
    redo = list(st.session_state.get(_linked_redo_key(module_key), []))
    if isinstance(current, dict):
        redo.append(dict(current))
    restored = history.pop()
    st.session_state[_linked_history_key(module_key)] = history
    st.session_state[_linked_redo_key(module_key)] = redo[-50:]
    st.session_state[_linked_key(module_key)] = restored
    return dict(restored)


def redo_linked_selection(module_key: str) -> dict[str, Any] | None:
    import streamlit as st

    redo = list(st.session_state.get(_linked_redo_key(module_key), []))
    if not redo:
        return get_linked_selection(module_key)
    current = st.session_state.get(_linked_key(module_key))
    history = list(st.session_state.get(_linked_history_key(module_key), []))
    if isinstance(current, dict):
        history.append(dict(current))
    restored = redo.pop()
    st.session_state[_linked_history_key(module_key)] = history[-50:]
    st.session_state[_linked_redo_key(module_key)] = redo
    st.session_state[_linked_key(module_key)] = restored
    return dict(restored)


def clear_linked_selection(module_key: str) -> None:
    import streamlit as st

    current = st.session_state.get(_linked_key(module_key))
    _push_linked_history(module_key, dict(current) if isinstance(current, dict) else None)
    st.session_state.pop(_linked_key(module_key), None)
