from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from typing import Any

try:
    import pandas as pd
except ImportError:
    pd = None

from biointel.neuro_cns.catalog import MODULE_BY_KEY
from biointel.neuro_cns.consistency import evaluate_results, result_quality_summary
from biointel.neuro_cns.provenance import RELEASE_LABEL, STEP_VERSION, provenance_block, resource_registry_rows


def _serialise(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return {
            "__type__": "dataframe",
            "columns": [str(column) for column in value.columns],
            "records": value.to_dict(orient="records"),
        }
    if isinstance(value, pd.Series):
        return {"__type__": "series", "name": str(value.name or ""), "values": value.to_list()}
    if hasattr(value, "tolist"):
        try:
            return value.tolist()
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(key): _serialise(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialise(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _result_inventory(results: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, value in results.items():
        spec = MODULE_BY_KEY.get(key)
        rows.append(
            {
                "module_key": key,
                "module_number": spec.number if spec else None,
                "module_title": spec.title if spec else key.replace("_", " ").title(),
                "workspace": spec.workspace if spec else None,
                "result_type": type(value).__name__,
                "record_count": len(value) if isinstance(value, (pd.DataFrame, list, tuple, dict)) else None,
                "scientific_boundary": spec.boundary if spec else "Research output; responsible review required.",
            }
        )
    return rows


def build_result_bundle(
    results: dict[str, Any],
    *,
    project_name: str | None = None,
    analyst: str | None = None,
    notes: str | None = None,
    execution_history: list[dict[str, Any]] | None = None,
    error_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    generated = datetime.now(UTC).isoformat(timespec="seconds")
    consistency = evaluate_results(results)
    provenance = {key: provenance_block(key) for key in results}
    return {
        "schema": "biointel.neuro-cns.result-bundle.v2",
        "step": STEP_VERSION,
        "release_label": RELEASE_LABEL,
        "generated_at_utc": generated,
        "project_name": project_name,
        "analyst": analyst,
        "notes": notes,
        "execution_history": _serialise(execution_history or []),
        "error_records": _serialise(error_records or []),
        "module_count_with_results": len(results),
        "inventory": _result_inventory(results),
        "quality_summary": result_quality_summary(results),
        "consistency_findings": _serialise(consistency),
        "resource_registry": resource_registry_rows(),
        "provenance": provenance,
        "results": _serialise(results),
        "controlled_release_eligible": False,
        "scientific_boundary": (
            "Research software output. Clinical, regulatory and controlled-release eligibility require approved "
            "data bindings, independent validation, expert review and responsible sign-off."
        ),
    }


def bundle_json(results: dict[str, Any], **metadata: Any) -> str:
    return json.dumps(build_result_bundle(results, **metadata), indent=2, sort_keys=True, default=str)


def bundle_markdown(results: dict[str, Any], **metadata: Any) -> str:
    bundle = build_result_bundle(results, **metadata)
    lines = [
        "# BioIntel Neuro/CNS Intelligence Studio Report",
        "",
        f"- **Step:** {bundle['step']} — {bundle['release_label']}",
        f"- **Generated:** {bundle['generated_at_utc']}",
        f"- **Project:** {bundle.get('project_name') or 'Unspecified'}",
        f"- **Analyst:** {bundle.get('analyst') or 'Unspecified'}",
        f"- **Completed modules:** {bundle['module_count_with_results']}",
        f"- **Controlled release eligible:** No",
        "",
        f"> {bundle['scientific_boundary']}",
        "",
        "## Result inventory",
        "",
        "| # | Module | Workspace | Result type |",
        "|---:|---|---|---|",
    ]
    for row in bundle["inventory"]:
        lines.append(f"| {row.get('module_number') or ''} | {row['module_title']} | {row.get('workspace') or ''} | {row['result_type']} |")
    lines.extend(["", "## Cross-module consistency findings", ""])
    findings = bundle["consistency_findings"]
    records = findings.get("records", []) if isinstance(findings, dict) else []
    if records:
        for finding in records:
            lines.append(f"- **{str(finding.get('severity', 'info')).upper()} — {finding.get('rule', '')}:** {finding.get('message', '')}")
    else:
        lines.append("- No configured finding records were produced.")
    if bundle.get("notes"):
        lines.extend(["", "## Notes", "", str(bundle["notes"])])
    lines.extend(["", "## Execution reliability", ""])
    lines.append(f"- Recorded executions: {len(bundle.get('execution_history') or [])}")
    lines.append(f"- Captured isolated errors: {len(bundle.get('error_records') or [])}")
    lines.extend(["", "## Module results", ""])
    for key, value in bundle["results"].items():
        title = MODULE_BY_KEY[key].title if key in MODULE_BY_KEY else key.replace("_", " ").title()
        lines.extend([f"### {title}", "", "```json", json.dumps(value, indent=2, sort_keys=True, default=str), "```", ""])
    return "\n".join(lines)


def bundle_html(results: dict[str, Any], **metadata: Any) -> str:
    bundle = build_result_bundle(results, **metadata)
    cards: list[str] = []
    for key, value in bundle["results"].items():
        title = MODULE_BY_KEY[key].title if key in MODULE_BY_KEY else key.replace("_", " ").title()
        cards.append(
            f"<section><h2>{html.escape(title)}</h2>"
            f"<pre>{html.escape(json.dumps(value, indent=2, sort_keys=True, default=str))}</pre></section>"
        )
    findings = bundle["consistency_findings"]
    finding_records = findings.get("records", []) if isinstance(findings, dict) else []
    finding_html = "".join(
        f"<li><strong>{html.escape(str(row.get('severity', 'info')).upper())} — {html.escape(str(row.get('rule', '')))}</strong>: {html.escape(str(row.get('message', '')))}</li>"
        for row in finding_records
    ) or "<li>No configured conflicts detected.</li>"
    inventory_rows = "".join(
        f"<tr><td>{row.get('module_number') or ''}</td><td>{html.escape(str(row['module_title']))}</td><td>{html.escape(str(row.get('workspace') or ''))}</td><td>{html.escape(str(row['result_type']))}</td></tr>"
        for row in bundle["inventory"]
    )
    return """<!doctype html><html><head><meta charset='utf-8'><title>BioIntel Neuro/CNS Report</title>
<style>body{font-family:Segoe UI,Arial,sans-serif;max-width:1180px;margin:36px auto;padding:0 24px;color:#14231f}header{border-bottom:3px solid #1d5b4f;padding-bottom:16px}.badge{display:inline-block;padding:5px 9px;border-radius:999px;background:#edf6f3;margin-right:7px}section{border:1px solid #d7e3df;border-radius:16px;padding:18px;margin:18px 0;background:#fbfdfc}pre{white-space:pre-wrap;word-break:break-word;background:#f2f7f5;padding:14px;border-radius:10px}small{color:#50645f}table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #d7e3df;text-align:left;padding:8px}aside{background:#fff4db;border-left:5px solid #b67a00;padding:12px 16px;margin:16px 0}</style></head><body>""" + (
        f"<header><h1>BioIntel Neuro/CNS Intelligence Studio</h1>"
        f"<span class='badge'>Step {html.escape(bundle['step'])}</span>"
        f"<span class='badge'>{html.escape(bundle['release_label'])}</span>"
        f"<p>Generated {html.escape(bundle['generated_at_utc'])}</p>"
        f"<small>Project: {html.escape(str(bundle.get('project_name') or 'Unspecified'))} · Analyst: {html.escape(str(bundle.get('analyst') or 'Unspecified'))}</small></header>"
        f"<aside><strong>Scientific boundary:</strong> {html.escape(bundle['scientific_boundary'])}</aside>"
        f"<section><h2>Result inventory</h2><table><thead><tr><th>#</th><th>Module</th><th>Workspace</th><th>Result</th></tr></thead><tbody>{inventory_rows}</tbody></table></section>"
        f"<section><h2>Cross-module consistency</h2><ul>{finding_html}</ul></section>"
        f"<section><h2>Execution reliability</h2><p>Recorded executions: {len(bundle.get('execution_history') or [])} · Captured isolated errors: {len(bundle.get('error_records') or [])}</p></section>"
        + "".join(cards)
        + "</body></html>"
    )


def bundle_pdf(results: dict[str, Any], **metadata: Any) -> bytes:
    """Create a professional, bounded PDF summary for the current Neuro/CNS result bundle."""
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    bundle = build_result_bundle(results, **metadata)
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title="BioIntel Neuro/CNS Intelligence Studio Report",
        author=str(bundle.get("analyst") or "BioIntel AI"),
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Boundary", parent=styles["BodyText"], backColor=colors.HexColor("#FFF4DB"), borderColor=colors.HexColor("#B67A00"), borderWidth=0.6, borderPadding=8, leading=13))
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=7.5, leading=9.5, alignment=TA_LEFT))
    story = [
        Paragraph("BioIntel Neuro/CNS Intelligence Studio", styles["Title"]),
        Paragraph(f"Step {html.escape(str(bundle['step']))} - {html.escape(str(bundle['release_label']))}", styles["Heading2"]),
        Paragraph(f"Generated: {html.escape(str(bundle['generated_at_utc']))}<br/>Project: {html.escape(str(bundle.get('project_name') or 'Unspecified'))}<br/>Analyst/reviewer: {html.escape(str(bundle.get('analyst') or 'Unspecified'))}", styles["BodyText"]),
        Spacer(1, 6 * mm),
        Paragraph(html.escape(str(bundle["scientific_boundary"])), styles["Boundary"]),
        Spacer(1, 5 * mm),
        Paragraph("Executive summary", styles["Heading1"]),
        Paragraph(f"Completed result groups: {bundle['module_count_with_results']}. Controlled release eligible: No. Recorded executions: {len(bundle.get('execution_history') or [])}. Captured isolated errors: {len(bundle.get('error_records') or [])}.", styles["BodyText"]),
        Spacer(1, 4 * mm),
        Paragraph("Result inventory", styles["Heading1"]),
    ]
    inventory_data = [["#", "Module", "Workspace", "Result type"]]
    for row in bundle["inventory"]:
        inventory_data.append([str(row.get("module_number") or ""), str(row["module_title"]), str(row.get("workspace") or ""), str(row["result_type"])])
    inventory = Table(inventory_data, colWidths=[12 * mm, 72 * mm, 55 * mm, 30 * mm], repeatRows=1)
    inventory.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D5B4F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D7E3DF")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F7F5")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([inventory, Spacer(1, 5 * mm), Paragraph("Cross-module consistency", styles["Heading1"])])
    findings = bundle["consistency_findings"]
    records = findings.get("records", []) if isinstance(findings, dict) else []
    if records:
        for row in records[:200]:
            story.append(Paragraph(f"<b>{html.escape(str(row.get('severity', 'info')).upper())} - {html.escape(str(row.get('rule', '')))}</b>: {html.escape(str(row.get('message', '')))}", styles["BodyText"]))
    else:
        story.append(Paragraph("No configured conflict records were produced.", styles["BodyText"]))
    if bundle.get("notes"):
        story.extend([Spacer(1, 4 * mm), Paragraph("Notes", styles["Heading1"]), Paragraph(html.escape(str(bundle["notes"])), styles["BodyText"])])
    story.append(PageBreak())
    story.append(Paragraph("Module result summaries", styles["Heading1"]))
    for key, value in bundle["results"].items():
        title = MODULE_BY_KEY[key].title if key in MODULE_BY_KEY else key.replace("_", " ").title()
        raw = json.dumps(value, indent=2, sort_keys=True, default=str)
        # Bound each section to avoid pathological multi-thousand-page exports.
        if len(raw) > 30_000:
            raw = raw[:30_000] + "\n... [truncated in PDF; full data remains in JSON/HTML/evidence pack]"
        story.extend([
            Paragraph(html.escape(title), styles["Heading2"]),
            Paragraph(f"<font name='Courier'>{html.escape(raw).replace(chr(10), '<br/>')}</font>", styles["Small"]),
            Spacer(1, 4 * mm),
        ])
    story.extend([PageBreak(), Paragraph("Resource and release boundary", styles["Heading1"])])
    resource_data = [["Resource", "Provider", "Validation", "Eligible"]]
    for row in bundle.get("resource_registry", [])[:200]:
        resource_data.append([str(row.get("resource_id", "")), str(row.get("provider", "")), str(row.get("validation_status", "")), "Yes" if row.get("release_eligible") else "No"])
    resources = Table(resource_data, colWidths=[36 * mm, 70 * mm, 48 * mm, 18 * mm], repeatRows=1)
    resources.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D5B4F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D7E3DF")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
    ]))
    story.extend([resources, Spacer(1, 5 * mm), Paragraph("This report is a research-software artifact. It is not a diagnosis, treatment recommendation, medical-device report or controlled scientific release authorization.", styles["Boundary"])])
    document.build(story)
    return buffer.getvalue()
