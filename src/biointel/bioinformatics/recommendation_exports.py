from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections.abc import Mapping, Sequence
from typing import Any

from biointel.synthetic.core import (
    SYNTHETIC_WATERMARK,
    origin_fields,
    payload_contains_synthetic,
)


def _clean(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_clean(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _rows(record: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    value = record.get(key, [])
    return [dict(row) for row in value if isinstance(row, Mapping)] if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else []


def _flatten(prefix: str, value: Any, output: list[dict[str, Any]]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _flatten(f"{prefix}.{key}" if prefix else str(key), item, output)
    elif isinstance(value, (list, tuple)):
        output.append({"field": prefix, "value": json.dumps(_clean(value), sort_keys=True)})
    else:
        output.append({"field": prefix, "value": value})


def export_parameter_configuration(record: Mapping[str, Any]) -> bytes:
    payload = {
        "recommendation_id": record.get("recommendation_id"),
        "module": record.get("module"),
        "run_id": record.get("run_id"),
        "parameters": record.get("reproducibility", {}).get("parameters", {}),
        "filters": record.get("reproducibility", {}).get("filters", {}),
        "priority_formula": record.get("priority_formula"),
        "priority_components": record.get("priority_components", []),
        "rule_version": record.get("module_analysis", {}).get("rule_version"),
    }
    if payload_contains_synthetic(record):
        payload.update(origin_fields())
        payload["export_watermark"] = SYNTHETIC_WATERMARK
    return json.dumps(_clean(payload), indent=2, sort_keys=True, default=str).encode("utf-8")


def export_audit_report(record: Mapping[str, Any], events: Sequence[Mapping[str, Any]] = ()) -> bytes:
    payload = {
        "recommendation_id": record.get("recommendation_id"),
        "project_id": record.get("project_id"),
        "run_id": record.get("run_id"),
        "module": record.get("module"),
        "status": record.get("status"),
        "created_at_utc": record.get("created_at_utc"),
        "updated_at_utc": record.get("updated_at_utc"),
        "decision_reason": record.get("decision_reason", ""),
        "reviewer_comments": record.get("reviewer_comments", ""),
        "validation_status": record.get("validation_status"),
        "analysis_payload_sha256": record.get("reproducibility", {}).get("analysis_payload_sha256"),
        "events": [_clean(dict(event)) for event in events],
    }
    if payload_contains_synthetic(record):
        payload.update(origin_fields())
        payload["export_watermark"] = SYNTHETIC_WATERMARK
    return json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8")


def _write_sheet(workbook: Any, title: str, rows: Sequence[Mapping[str, Any]]) -> None:
    sheet = workbook.create_sheet(title[:31])
    clean_rows = [dict(row) for row in rows if isinstance(row, Mapping)]
    if not clean_rows:
        sheet.append(["status", "No records"])
        return
    columns = list(dict.fromkeys(str(key) for row in clean_rows for key in row))
    sheet.append(columns)
    for row in clean_rows:
        values = []
        for column in columns:
            value = row.get(column, "")
            if isinstance(value, (dict, list, tuple, set)):
                value = json.dumps(_clean(value), sort_keys=True, default=str)
            values.append(value)
        sheet.append(values)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for cells in sheet.columns:
        width = min(60, max(10, max(len(str(cell.value or "")) for cell in cells) + 2))
        sheet.column_dimensions[cells[0].column_letter].width = width


def export_recommendation_xlsx(record: Mapping[str, Any], events: Sequence[Mapping[str, Any]] = ()) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    workbook = Workbook()
    workbook.remove(workbook.active)
    if payload_contains_synthetic(record):
        notice = workbook.create_sheet("SYNTHETIC NOTICE", 0)
        notice["A1"] = SYNTHETIC_WATERMARK
        notice["A2"] = "Data Origin: Synthetic"
        notice["A3"] = "Scientific Use: Not permitted"
        notice["A4"] = "Clinical Use: Not permitted"
        notice["A5"] = "Publication Use: Not permitted"
        notice.column_dimensions["A"].width = 100
    summary = [{
        "recommendation_id": record.get("recommendation_id"),
        "project_id": record.get("project_id"),
        "run_id": record.get("run_id"),
        "module": record.get("module_label", record.get("module")),
        "title": record.get("title"),
        "priority": record.get("priority"),
        "priority_score": record.get("priority_score"),
        "confidence_score": record.get("confidence_score"),
        "evidence_grade": record.get("evidence_grade"),
        "status": record.get("status"),
        "next_action": record.get("recommended_next_action"),
        "scientific_summary": record.get("scientific_summary"),
        "research_use_disclaimer": record.get("research_use_disclaimer"),
    }]
    _write_sheet(workbook, "Summary", summary)
    sections = {
        "Quality Checks": _rows(record, "quality_checks"),
        "Evidence": _rows(record, "evidence") + _rows(record, "contradictory_evidence"),
        "Module Metrics": _rows(record.get("module_analysis", {}), "metrics"),
        "Module Recommendations": _rows(record.get("module_analysis", {}), "recommendations"),
        "Feature Coverage": _rows(record.get("module_analysis", {}), "feature_coverage"),
        "Ranked Entities": _rows(record.get("module_analysis", {}), "ranked_entities"),
        "Explainability": _rows(record, "explainability"),
        "Alternatives": _rows(record, "alternatives"),
        "Risks": _rows(record, "risks"),
        "Validation": _rows(record, "validation_plan"),
        "Action Plan": _rows(record, "action_plan"),
        "Comparison": _rows(record, "comparison"),
        "What If": _rows(record, "what_if_analysis"),
        "Consensus": _rows(record.get("multi_model_consensus", {}), "models"),
        "Audit": [dict(event) for event in events],
    }
    manifest_rows: list[dict[str, Any]] = []
    _flatten("", record.get("reproducibility", {}), manifest_rows)
    sections["Reproducibility"] = manifest_rows
    for title, rows in sections.items():
        _write_sheet(workbook, title, rows)
    for sheet in workbook.worksheets:
        if payload_contains_synthetic(record):
            sheet.oddHeader.center.text = SYNTHETIC_WATERMARK
            sheet.oddFooter.center.text = "Synthetic demo output - prohibited for scientific or publication use"
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F4E78")
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def _add_table(document: Any, rows: Sequence[Mapping[str, Any]], preferred: Sequence[str] = ()) -> None:
    clean_rows = [dict(row) for row in rows if isinstance(row, Mapping)]
    if not clean_rows:
        document.add_paragraph("No records.")
        return
    columns = [column for column in preferred if any(column in row for row in clean_rows)]
    if not columns:
        columns = list(dict.fromkeys(str(key) for row in clean_rows for key in row))[:8]
    table = document.add_table(rows=1, cols=len(columns))
    table.style = "Table Grid"
    for index, column in enumerate(columns):
        table.rows[0].cells[index].text = column.replace("_", " ").title()
    for row in clean_rows[:200]:
        cells = table.add_row().cells
        for index, column in enumerate(columns):
            value = row.get(column, "")
            if isinstance(value, (dict, list, tuple, set)):
                value = json.dumps(_clean(value), sort_keys=True, default=str)
            cells[index].text = str(value)


def export_recommendation_docx(record: Mapping[str, Any], events: Sequence[Mapping[str, Any]] = ()) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt

    document = Document()
    section = document.sections[0]
    section.top_margin = Inches(0.65)
    section.bottom_margin = Inches(0.65)
    if payload_contains_synthetic(record):
        section.header.paragraphs[0].text = SYNTHETIC_WATERMARK
        notice = document.add_paragraph(SYNTHETIC_WATERMARK)
        notice.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in notice.runs:
            run.bold = True
            run.font.size = Pt(12)
    title = document.add_heading(str(record.get("title", "BioIntel AI Recommendation Report")), 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle = document.add_paragraph(f"{record.get('module_label', record.get('module', ''))} | {record.get('recommendation_id', '')}")
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    summary = document.add_table(rows=2, cols=4)
    summary.style = "Table Grid"
    labels = ("Priority", "Confidence", "Evidence grade", "Status")
    values = (f"{record.get('priority')} ({record.get('priority_score')}/100)", record.get("confidence_score", "Not calculated"), record.get("evidence_grade"), record.get("status"))
    for index, label in enumerate(labels):
        summary.cell(0, index).text = label
        summary.cell(1, index).text = str(values[index])
    sections = (
        ("Scientific Summary", str(record.get("scientific_summary", "")), ()),
        ("Primary Next Action", str(record.get("recommended_next_action", "")), ()),
        ("Data Quality", "", _rows(record, "quality_checks")),
        ("Module-Specific Analysis", "", _rows(record.get("module_analysis", {}), "metrics")),
        ("Module Recommendations", "", _rows(record.get("module_analysis", {}), "recommendations")),
        ("Supporting and Contradictory Evidence", "", _rows(record, "evidence") + _rows(record, "contradictory_evidence")),
        ("Alternatives", "", _rows(record, "alternatives")),
        ("Risks and Limitations", "", _rows(record, "risks")),
        ("Validation Plan", "", _rows(record, "validation_plan")),
        ("Action Plan", "", _rows(record, "action_plan")),
        ("What-If and Stability", "", _rows(record, "what_if_analysis")),
        ("Audit Events", "", [dict(event) for event in events]),
    )
    for heading, text, rows in sections:
        document.add_heading(heading, level=1)
        if text:
            document.add_paragraph(text)
        if rows:
            _add_table(document, rows)
    document.add_heading("Reproducibility", level=1)
    manifest_rows: list[dict[str, Any]] = []
    _flatten("", record.get("reproducibility", {}), manifest_rows)
    _add_table(document, manifest_rows, ("field", "value"))
    boundary = document.add_paragraph(str(record.get("research_use_disclaimer", "")))
    boundary.style = document.styles["Intense Quote"]
    for style_name in ("Normal", "Table Grid"):
        if style_name in document.styles:
            document.styles[style_name].font.name = "Arial"
            document.styles[style_name].font.size = Pt(9)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def export_recommendation_pdf_full(record: Mapping[str, Any], events: Sequence[Mapping[str, Any]] = ()) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    output = io.BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CenterTitle", parent=styles["Title"], alignment=TA_CENTER, textColor=colors.HexColor("#17365D")))
    document = SimpleDocTemplate(output, pagesize=A4, rightMargin=13 * mm, leftMargin=13 * mm, topMargin=12 * mm, bottomMargin=12 * mm, title=str(record.get("title", "Recommendation Report")))
    story: list[Any] = []
    if payload_contains_synthetic(record):
        story.extend([Paragraph(SYNTHETIC_WATERMARK, ParagraphStyle(name="SyntheticNotice", parent=styles["Heading2"], alignment=TA_CENTER, textColor=colors.HexColor("#B42318"))), Spacer(1, 3 * mm)])
    story.extend([Paragraph(str(record.get("title", "Recommendation Report")), styles["CenterTitle"]), Paragraph(f"{record.get('module_label', record.get('module', ''))} | {record.get('recommendation_id', '')}", styles["BodyText"]), Spacer(1, 5 * mm)])
    summary = [
        ["Priority", "Confidence", "Evidence", "Status"],
        [f"{record.get('priority')} ({record.get('priority_score')}/100)", str(record.get("confidence_score", "Not calculated")), str(record.get("evidence_grade", "")), str(record.get("status", ""))],
    ]
    table = Table(summary, repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.extend([table, Spacer(1, 4 * mm), Paragraph("<b>Scientific summary</b>", styles["Heading2"]), Paragraph(str(record.get("scientific_summary", "")), styles["BodyText"]), Paragraph("<b>Primary next action</b>", styles["Heading2"]), Paragraph(str(record.get("recommended_next_action", "")), styles["BodyText"])])
    sections = (
        ("Data Quality", _rows(record, "quality_checks"), ("check", "status", "value", "recommendation")),
        ("Module-Specific Metrics", _rows(record.get("module_analysis", {}), "metrics"), ("metric", "value", "status", "interpretation")),
        ("Module Recommendations", _rows(record.get("module_analysis", {}), "recommendations"), ("feature", "recommendation", "rationale")),
        ("Evidence", _rows(record, "evidence") + _rows(record, "contradictory_evidence"), ("evidence_type", "source", "finding", "strength", "contradictory")),
        ("Alternatives", _rows(record, "alternatives"), ("option", "expected_value", "scientific_strength", "risk", "limitations")),
        ("Risks", _rows(record, "risks"), ("category", "level", "rationale", "mitigation")),
        ("Validation Plan", _rows(record, "validation_plan"), ("validation_type", "status", "acceptance_criteria", "failure_criteria")),
        ("Action Plan", _rows(record, "action_plan"), ("action_title", "owner", "priority", "status", "expected_result")),
        ("What-If Stability", _rows(record, "what_if_analysis"), ("scenario", "candidate_count", "top_entity", "rank_set_stability")),
    )
    for heading, rows, columns in sections:
        story.extend([Spacer(1, 3 * mm), Paragraph(heading, styles["Heading2"])])
        if not rows:
            story.append(Paragraph("No records.", styles["BodyText"]))
            continue
        data = [[Paragraph(column.replace("_", " ").title(), styles["BodyText"]) for column in columns]]
        for row in rows[:100]:
            data.append([Paragraph(str(row.get(column, ""))[:600], styles["BodyText"]) for column in columns])
        section_table = Table(data, repeatRows=1, hAlign="LEFT")
        section_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF7")), ("GRID", (0, 0), (-1, -1), 0.35, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 6.7), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]))
        story.append(section_table)
    story.extend([PageBreak(), Paragraph("Reproducibility and Audit", styles["Heading1"]), Paragraph(f"Analysis hash: {record.get('reproducibility', {}).get('analysis_payload_sha256', '')}", styles["BodyText"]), Paragraph(f"Software: {record.get('reproducibility', {}).get('software_version', '')}", styles["BodyText"]), Paragraph(f"Database versions: {record.get('reproducibility', {}).get('database_versions', {})}", styles["BodyText"]), Spacer(1, 4 * mm), Paragraph(str(record.get("research_use_disclaimer", "")), styles["Italic"])])
    def _page_notice(canvas: Any, _: Any) -> None:
        if not payload_contains_synthetic(record):
            return
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#B42318"))
        canvas.setFont("Helvetica-Bold", 7)
        canvas.drawCentredString(A4[0] / 2, 6 * mm, SYNTHETIC_WATERMARK)
        canvas.restoreState()
    document.build(story, onFirstPage=_page_notice, onLaterPages=_page_notice)
    return output.getvalue()


def _csv_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    clean_rows = [dict(row) for row in rows if isinstance(row, Mapping)]
    if not clean_rows:
        return b"status\r\nNo records\r\n"
    columns = list(dict.fromkeys(str(key) for row in clean_rows for key in row))
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for row in clean_rows:
        writer.writerow({column: json.dumps(_clean(row.get(column)), sort_keys=True, default=str) if isinstance(row.get(column), (dict, list, tuple, set)) else row.get(column, "") for column in columns})
    return output.getvalue().encode("utf-8")


def export_evidence_package(record: Mapping[str, Any], events: Sequence[Mapping[str, Any]] = (), base_exports: Mapping[str, bytes] | None = None) -> bytes:
    recommendation_id = re.sub(r"[^A-Za-z0-9._-]", "_", str(record.get("recommendation_id", "recommendation")))
    files = dict(base_exports or {})
    files.update({
        f"{recommendation_id}.docx": export_recommendation_docx(record, events),
        f"{recommendation_id}.xlsx": export_recommendation_xlsx(record, events),
        f"{recommendation_id}_scientific.pdf": export_recommendation_pdf_full(record, events),
        f"{recommendation_id}_parameters.json": export_parameter_configuration(record),
        f"{recommendation_id}_audit.json": export_audit_report(record, events),
        f"{recommendation_id}_risks.csv": _csv_bytes(_rows(record, "risks")),
        f"{recommendation_id}_alternatives.csv": _csv_bytes(_rows(record, "alternatives")),
        f"{recommendation_id}_validation.csv": _csv_bytes(_rows(record, "validation_plan")),
        f"{recommendation_id}_feature_coverage.csv": _csv_bytes(_rows(record.get("module_analysis", {}), "feature_coverage")),
    })
    if payload_contains_synthetic(record):
        files = {name: (f"# {SYNTHETIC_WATERMARK}\n".encode("utf-8") + data if name.lower().endswith(".csv") and not data.startswith(b"# SYNTHETIC") else data) for name, data in files.items()}
        files["SYNTHETIC_NOTICE.txt"] = (SYNTHETIC_WATERMARK + "\nData Origin: Synthetic\nScientific Use: Not permitted\nClinical Use: Not permitted\nPublication Use: Not permitted\n").encode("utf-8")
    manifest = {name: {"size_bytes": len(data)} for name, data in files.items()}
    if payload_contains_synthetic(record):
        manifest["_synthetic_metadata"] = {"data_origin": "synthetic", "is_synthetic": True, "export_watermark": SYNTHETIC_WATERMARK, "publication_ready": False}
    files["package_manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    return output.getvalue()

