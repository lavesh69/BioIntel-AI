from __future__ import annotations

import html
import io
import json
import textwrap
import zipfile
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from .intelligence import infer_entity_column, infer_score_column, utc_now

def audit_visuals(visuals: Sequence[Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    titles: list[str] = []
    for index, visual in enumerate(visuals):
        title = str(getattr(visual, "title", "") or "")
        titles.append(title)
        data = pd.DataFrame(getattr(visual, "data", pd.DataFrame()))
        figure = getattr(visual, "figure", None)
        issues: list[str] = []
        if not title.strip():
            issues.append("Missing title")
        if data.empty:
            issues.append("No underlying data")
        if len(data) > 50_000:
            issues.append("Dense visual; downsampling recommended")
        numeric = data.select_dtypes(include="number")
        if not numeric.empty:
            nonfinite = int((~np.isfinite(numeric.to_numpy(dtype=float, na_value=np.nan))).sum())
            if nonfinite:
                issues.append(f"{nonfinite} non-finite numeric value(s)")
        trace_count = 0
        axis_labels_missing = False
        if figure is None:
            issues.append("Missing figure")
        else:
            try:
                trace_count = len(figure.data)
                if trace_count == 0:
                    issues.append("Figure has no traces")
                x_title = getattr(getattr(figure.layout, "xaxis", None), "title", None)
                y_title = getattr(getattr(figure.layout, "yaxis", None), "title", None)
                x_text = getattr(x_title, "text", None) if x_title is not None else None
                y_text = getattr(y_title, "text", None) if y_title is not None else None
                axis_labels_missing = not bool(x_text or y_text)
                if axis_labels_missing:
                    issues.append("Axis labels not explicit")
            except Exception:
                issues.append("Figure metadata could not be inspected")
        status = "Passed" if not issues else ("Review" if len(issues) <= 2 else "Blocked")
        rows.append({
            "visual_index": index + 1,
            "visual": title or f"Visual {index + 1}",
            "status": status,
            "issues": "; ".join(issues) if issues else "None",
            "records": int(len(data)),
            "traces": trace_count,
            "axis_labels_missing": axis_labels_missing,
        })
    duplicates = {title for title in titles if title and titles.count(title) > 1}
    if duplicates:
        for row in rows:
            if row["visual"] in duplicates:
                row["status"] = "Review"
                row["issues"] = (row["issues"] + "; " if row["issues"] != "None" else "") + "Duplicate visual title"
    return pd.DataFrame(rows)


def build_scientific_story(
    *,
    module_title: str,
    boundary: str,
    run_id: str | None,
    summary: Mapping[str, Any],
    result: pd.DataFrame,
    extras: Mapping[str, pd.DataFrame] | None,
) -> list[dict[str, str]]:
    frame = pd.DataFrame(result)
    entity_column = infer_entity_column(frame)
    score_column = infer_score_column(frame)
    top_entities = []
    if entity_column and not frame.empty:
        ranked = frame.copy()
        if score_column:
            ranked[score_column] = pd.to_numeric(ranked[score_column], errors="coerce")
            ranked = ranked.sort_values(score_column, ascending=False, na_position="last")
        top_entities = ranked[entity_column].astype(str).head(5).tolist()
    warnings = []
    for key, value in dict(summary).items():
        text = str(value).lower()
        if any(token in text for token in ("warning", "review", "blocked", "missing", "not available")):
            warnings.append(f"{key}: {value}")
    return [
        {
            "stage": "Input quality",
            "message": f"The current result contains {len(frame):,} records and {len(frame.columns):,} fields. Run ID: {run_id or 'session-only'}.",
        },
        {
            "stage": "Main observation",
            "message": (
                f"Top prioritised entities: {', '.join(top_entities)}."
                if top_entities else "No stable entity identifier was available for an automatic top-candidate statement."
            ),
        },
        {
            "stage": "Supporting evidence",
            "message": f"The run generated {len(dict(extras or {}))} advanced evidence table(s) and {len(summary)} summary field(s).",
        },
        {
            "stage": "Uncertainty",
            "message": "; ".join(warnings[:5]) if warnings else "No explicit warning was emitted; absence of a warning is not external validation.",
        },
        {
            "stage": "Recommended next action",
            "message": "Review candidates, record a decision, compare against a prior run and hand off approved evidence to the next scientific module.",
        },
        {
            "stage": "Scientific boundary",
            "message": boundary,
        },
    ]


def _publication_svg(title: str, frame: pd.DataFrame) -> str:
    safe_title = html.escape(title)
    numeric_column = infer_score_column(frame)
    entity_column = infer_entity_column(frame)
    if frame.empty or not numeric_column:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="700" viewBox="0 0 1200 700">'
            '<rect width="1200" height="700" fill="white"/><text x="60" y="90" font-size="34" font-family="Arial">'
            + safe_title + '</text><text x="60" y="150" font-size="22" font-family="Arial">No numeric result was available for the vector figure.</text></svg>'
        )
    plot = frame[[numeric_column] + ([entity_column] if entity_column else [])].copy().head(12)
    plot[numeric_column] = pd.to_numeric(plot[numeric_column], errors="coerce")
    plot = plot.dropna(subset=[numeric_column])
    if plot.empty:
        return _publication_svg(title, pd.DataFrame())
    low, high = float(plot[numeric_column].min()), float(plot[numeric_column].max())
    span = high - low if high > low else 1.0
    rows: list[str] = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1000" viewBox="0 0 1600 1000">',
        '<rect width="1600" height="1000" fill="white"/>',
        f'<text x="90" y="90" font-size="42" font-family="Arial" font-weight="700">{safe_title}</text>',
        f'<text x="90" y="140" font-size="22" font-family="Arial">Vector summary of {html.escape(numeric_column.replace("_", " "))}</text>',
    ]
    bar_left, bar_width, top, row_height = 520, 930, 205, 58
    for position, (_, row) in enumerate(plot.iterrows()):
        y = top + position * row_height
        value = float(row[numeric_column])
        norm = (value - low) / span
        width = max(6, norm * bar_width)
        label = str(row[entity_column]) if entity_column else f"Record {position + 1}"
        rows.append(f'<text x="90" y="{y + 24}" font-size="20" font-family="Arial">{html.escape(label[:40])}</text>')
        rows.append(f'<rect x="{bar_left}" y="{y}" width="{width:.1f}" height="32" rx="5" fill="#356FA8"/>')
        rows.append(f'<text x="{bar_left + width + 12:.1f}" y="{y + 24}" font-size="18" font-family="Arial">{value:.4g}</text>')
    rows.append('<text x="90" y="940" font-size="17" font-family="Arial">Generated by BioIntel AI. Interpret with the accompanying evidence boundary and source manifest.</text>')
    rows.append('</svg>')
    return "".join(rows)


def build_publication_bundle(
    *,
    module_key: str,
    module_title: str,
    boundary: str,
    run_id: str | None,
    result: pd.DataFrame,
    summary: Mapping[str, Any],
    story: Sequence[Mapping[str, Any]],
    extras: Mapping[str, pd.DataFrame] | None = None,
) -> bytes:
    from biointel.ui.visual_workspace import _document_bytes

    frame = pd.DataFrame(result).head(500)
    svg = _publication_svg(module_title, frame)
    story_text = "\n".join(f"{item.get('stage')}: {item.get('message')}" for item in story)
    metadata = {
        "Module": module_key,
        "Run ID": run_id or "session-only",
        "Generated at": utc_now(),
        "Result rows": len(result),
        "Scientific boundary": boundary,
    }
    docx_bytes, pptx_bytes, pdf_bytes = _document_bytes(module_title, story_text, metadata, frame.head(30))
    html_report = f"""<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(module_title)}</title>
    <style>body{{font-family:Arial,sans-serif;max-width:1300px;margin:30px auto;line-height:1.5}} table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #bbb;padding:6px}} .boundary{{background:#fff4d6;padding:14px;border-left:5px solid #c77a00}}</style></head><body>
    <h1>{html.escape(module_title)}</h1><p>Run: {html.escape(run_id or 'session-only')}</p>{svg}
    <h2>Scientific story</h2><ol>{''.join(f"<li><b>{html.escape(str(item.get('stage','')))}</b>: {html.escape(str(item.get('message','')))}</li>" for item in story)}</ol>
    <div class='boundary'><b>Boundary:</b> {html.escape(boundary)}</div>
    <h2>Bounded result preview</h2>{frame.head(100).to_html(index=False, escape=True)}</body></html>"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("figure/publication_figure.svg", svg)
        archive.writestr("figure/publication_report.html", html_report)
        archive.writestr("report/publication_report.pdf", pdf_bytes)
        archive.writestr("report/publication_report.docx", docx_bytes)
        archive.writestr("report/publication_report.pptx", pptx_bytes)
        archive.writestr("data/results.csv", pd.DataFrame(result).to_csv(index=False))
        for name, table in dict(extras or {}).items():
            if table is not None and not pd.DataFrame(table).empty:
                archive.writestr(f"data/{name}.csv", pd.DataFrame(table).to_csv(index=False))
        manifest = {
            "schema": "biointel.step130.publication-bundle.v1",
            "module_key": module_key,
            "module_title": module_title,
            "run_id": run_id,
            "generated_at_utc": utc_now(),
            "summary": dict(summary),
            "story": list(story),
            "boundary": boundary,
            "vector_figure": True,
            "external_validation_claimed": False,
        }
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True, default=str))
        archive.writestr(
            "README.txt",
            textwrap.dedent(
                """\
                BioIntel AI publication figure package
                =======================================
                This package includes a vector SVG, HTML report, PDF, DOCX, PPTX,
                result tables and a machine-readable manifest. It is a research
                communication package, not a claim of journal acceptance or external validation.
                """
            ),
        )
    return buffer.getvalue()


__all__ = ["audit_visuals", "build_scientific_story", "build_publication_bundle"]
