from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from biointel.documents.models import DocumentExtraction, ExtractedTable


def _safe_stem(value: str) -> str:
    stem = Path(value).stem
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
    return (stem or "document")[:80]


def _safe_sheet_name(value: str, existing: set[str]) -> str:
    candidate = re.sub(r"[\\/*?:\[\]]+", "_", value).strip()[:31] or "Table"
    base = candidate
    counter = 2
    while candidate.lower() in existing:
        suffix = f"_{counter}"
        candidate = base[: 31 - len(suffix)] + suffix
        counter += 1
    existing.add(candidate.lower())
    return candidate


def _excel_safe(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_json(extraction: DocumentExtraction) -> bytes:
    return json.dumps(
        extraction.to_dict(include_rows=True),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def export_csv_zip(extraction: DocumentExtraction) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("extracted_text.txt", extraction.text.encode("utf-8"))
        archive.writestr("metadata.json", export_json(extraction))
        archive.writestr(
            "structured_fields.json",
            json.dumps(extraction.structured_fields, indent=2, ensure_ascii=False, default=str).encode("utf-8"),
        )
        entity_output = io.StringIO(newline="")
        entity_writer = csv.writer(entity_output)
        entity_writer.writerow(["entity_type", "text", "normalized", "source", "confidence"])
        for entity in extraction.entities:
            entity_writer.writerow([entity.entity_type, entity.text, entity.normalized, entity.source, entity.confidence])
        archive.writestr("scientific_entities.csv", entity_output.getvalue().encode("utf-8-sig"))
        region_output = io.StringIO(newline="")
        region_writer = csv.writer(region_output)
        region_writer.writerow(["region_id", "kind", "source", "page_number", "bbox", "confidence", "text"])
        for region in extraction.regions:
            region_writer.writerow([region.region_id, region.kind, region.source, region.page_number, region.bbox, region.confidence, region.text])
        archive.writestr("layout_regions.csv", region_output.getvalue().encode("utf-8-sig"))
        for index, table in enumerate(extraction.tables, start=1):
            output = io.StringIO(newline="")
            writer = csv.writer(output)
            writer.writerow(table.columns)
            writer.writerows(table.rows)
            filename = f"tables/{index:03d}_{_safe_stem(table.name)}.csv"
            archive.writestr(filename, output.getvalue().encode("utf-8-sig"))
    return buffer.getvalue()


def export_xlsx(extraction: DocumentExtraction) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    summary = workbook.active
    summary.title = "Summary"
    title_fill = PatternFill("solid", fgColor="1F4E78")
    heading_fill = PatternFill("solid", fgColor="D9EAF7")
    summary["A1"] = "BioIntel AI - Document Extraction"
    summary["A1"].font = Font(bold=True, color="FFFFFF", size=14)
    summary["A1"].fill = title_fill
    summary.merge_cells("A1:D1")
    summary.append([])
    for key, value in extraction.summary().items():
        summary.append([key.replace("_", " ").title(), _excel_safe(value)])
    summary.append([])
    summary.append(["Warnings"])
    summary[summary.max_row][0].font = Font(bold=True)
    for warning in extraction.warnings:
        summary.append([warning])
    summary.column_dimensions["A"].width = 34
    summary.column_dimensions["B"].width = 70

    text_sheet = workbook.create_sheet("Extracted Text")
    text_sheet.append(["Section", "Source", "Text"])
    for cell in text_sheet[1]:
        cell.fill = title_fill
        cell.font = Font(bold=True, color="FFFFFF")
    if extraction.sections:
        for section in extraction.sections:
            text_sheet.append([section.name, section.source, _excel_safe(section.text)])
    else:
        text_sheet.append(["Document", "document", _excel_safe(extraction.text)])
    text_sheet.freeze_panes = "A2"
    text_sheet.column_dimensions["A"].width = 28
    text_sheet.column_dimensions["B"].width = 24
    text_sheet.column_dimensions["C"].width = 100
    for row in text_sheet.iter_rows(min_row=2):
        row[2].alignment = Alignment(wrap_text=True, vertical="top")

    entity_sheet = workbook.create_sheet("Scientific Entities")
    entity_sheet.append(["Type", "Text", "Normalized", "Source", "Confidence", "Metadata"])
    for cell in entity_sheet[1]:
        cell.fill = title_fill
        cell.font = Font(bold=True, color="FFFFFF")
    for entity in extraction.entities:
        entity_sheet.append([
            entity.entity_type,
            _excel_safe(entity.text),
            _excel_safe(entity.normalized),
            entity.source,
            entity.confidence,
            json.dumps(entity.metadata, sort_keys=True, default=str),
        ])
    entity_sheet.freeze_panes = "A2"

    region_sheet = workbook.create_sheet("Layout Provenance")
    region_sheet.append(["Region ID", "Kind", "Source", "Page", "Bounding Box", "Confidence", "Text"])
    for cell in region_sheet[1]:
        cell.fill = title_fill
        cell.font = Font(bold=True, color="FFFFFF")
    for region in extraction.regions:
        region_sheet.append([
            region.region_id,
            region.kind,
            region.source,
            region.page_number,
            json.dumps(region.bbox) if region.bbox is not None else None,
            region.confidence,
            _excel_safe(region.text),
        ])
    region_sheet.freeze_panes = "A2"

    structured_sheet = workbook.create_sheet("Structured Fields")
    structured_sheet.append(["Field", "Value"])
    for cell in structured_sheet[1]:
        cell.fill = title_fill
        cell.font = Font(bold=True, color="FFFFFF")
    for key, value in extraction.structured_fields.items():
        structured_sheet.append([key, _excel_safe(json.dumps(value, ensure_ascii=False, default=str))])

    existing = {"summary", "extracted text", "scientific entities", "layout provenance", "structured fields"}
    for index, table in enumerate(extraction.tables, start=1):
        sheet = workbook.create_sheet(_safe_sheet_name(f"{index}_{table.name}", existing))
        sheet.append([_excel_safe(value) for value in table.columns])
        for cell in sheet[1]:
            cell.fill = heading_fill
            cell.font = Font(bold=True)
            cell.alignment = Alignment(wrap_text=True)
        for row in table.rows:
            sheet.append([_excel_safe(value) for value in row])
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for column_index, column in enumerate(sheet.iter_cols(), start=1):
            sample = list(column[: min(len(column), 200)])
            width = max((len(str(cell.value or "")) for cell in sample), default=8)
            sheet.column_dimensions[get_column_letter(column_index)].width = min(max(width + 2, 10), 45)
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _table_preview(table: ExtractedTable, maximum_rows: int) -> tuple[list[str], list[list[str]]]:
    headers = [str(value) for value in table.columns]
    rows = [
        ["" if value is None else str(value) for value in row]
        for row in table.rows[:maximum_rows]
    ]
    return headers, rows


def export_docx(extraction: DocumentExtraction) -> bytes:
    from docx import Document
    from docx.shared import Inches, Pt

    document = Document()
    document.add_heading("BioIntel AI - Document Extraction", level=0)
    document.add_paragraph(f"Source: {extraction.source_name}")
    summary = document.add_table(rows=1, cols=2)
    summary.style = "Table Grid"
    summary.rows[0].cells[0].text = "Metric"
    summary.rows[0].cells[1].text = "Value"
    for key, value in extraction.summary().items():
        cells = summary.add_row().cells
        cells[0].text = key.replace("_", " ").title()
        cells[1].text = str(value)
    if extraction.warnings:
        document.add_heading("Warnings", level=1)
        for warning in extraction.warnings:
            document.add_paragraph(warning, style="List Bullet")
    if extraction.entities:
        document.add_heading("Scientific Entities", level=1)
        entity_table = document.add_table(rows=1, cols=4)
        entity_table.style = "Table Grid"
        for index, label in enumerate(("Type", "Text", "Normalized", "Source")):
            entity_table.rows[0].cells[index].text = label
        for entity in extraction.entities[:1000]:
            cells = entity_table.add_row().cells
            cells[0].text = entity.entity_type
            cells[1].text = entity.text
            cells[2].text = entity.normalized
            cells[3].text = entity.source
    if extraction.structured_fields:
        document.add_heading("Structured Research Fields", level=1)
        document.add_paragraph(json.dumps(extraction.structured_fields, indent=2, ensure_ascii=False, default=str))
    document.add_heading("Extracted Text", level=1)
    for section in extraction.sections or ():
        document.add_heading(section.name, level=2)
        document.add_paragraph(section.text or "No text extracted.")
    if not extraction.sections:
        document.add_paragraph(extraction.text or "No text extracted.")
    for index, table in enumerate(extraction.tables, start=1):
        document.add_page_break()
        document.add_heading(f"Table {index}: {table.name}", level=1)
        headers, rows = _table_preview(table, maximum_rows=2_000)
        output_table = document.add_table(rows=1, cols=max(len(headers), 1))
        output_table.style = "Table Grid"
        for column_index, header in enumerate(headers):
            output_table.rows[0].cells[column_index].text = header
        for row in rows:
            cells = output_table.add_row().cells
            for column_index, value in enumerate(row[: len(cells)]):
                cells[column_index].text = value
        if table.row_count > len(rows):
            document.add_paragraph(
                f"DOCX preview truncated: {table.row_count - len(rows)} additional rows are "
                "available in the Excel/CSV exports."
            )
    styles = document.styles
    styles["Normal"].font.name = "Aptos"
    styles["Normal"].font.size = Pt(10)
    for section in document.sections:
        section.top_margin = Inches(0.65)
        section.bottom_margin = Inches(0.65)
        section.left_margin = Inches(0.65)
        section.right_margin = Inches(0.65)
    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()


def export_pdf(extraction: DocumentExtraction) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        LongTable,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    stream = io.BytesIO()
    document = SimpleDocTemplate(
        stream,
        pagesize=landscape(A4),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title="BioIntel AI Document Extraction",
    )
    styles = getSampleStyleSheet()
    story: list[Any] = [
        Paragraph("BioIntel AI - Document Extraction", styles["Title"]),
        Paragraph(f"Source: {extraction.source_name}", styles["Normal"]),
        Spacer(1, 6),
    ]
    summary_rows = [["Metric", "Value"]] + [
        [key.replace("_", " ").title(), str(value)]
        for key, value in extraction.summary().items()
    ]
    summary_table = Table(summary_rows, colWidths=[65 * mm, 180 * mm], repeatRows=1)
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        )
    )
    story.extend([summary_table, Spacer(1, 8)])
    if extraction.warnings:
        story.append(Paragraph("Warnings", styles["Heading1"]))
        for warning in extraction.warnings:
            story.append(Paragraph(f"- {warning}", styles["BodyText"]))
    if extraction.entities:
        story.append(Paragraph("Scientific Entities", styles["Heading1"]))
        entity_rows = [["Type", "Text", "Normalized", "Source"]] + [
            [entity.entity_type, entity.text, entity.normalized, entity.source]
            for entity in extraction.entities[:300]
        ]
        entity_table = LongTable(entity_rows, repeatRows=1)
        entity_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF7")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.2, colors.grey),
        ]))
        story.append(entity_table)
    story.append(Paragraph("Extracted Text", styles["Heading1"]))
    text = extraction.text or "No text extracted."
    for block in text.split("\n\n")[:500]:
        clean = block.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(clean.replace("\n", "<br/>"), styles["BodyText"]))
        story.append(Spacer(1, 3))
    for index, table in enumerate(extraction.tables, start=1):
        story.append(PageBreak())
        story.append(Paragraph(f"Table {index}: {table.name}", styles["Heading1"]))
        headers, rows = _table_preview(table, maximum_rows=300)
        table_data = [headers] + rows
        column_count = max(len(headers), 1)
        available_width = landscape(A4)[0] - 24 * mm
        widths = [available_width / column_count] * column_count
        pdf_table = LongTable(table_data, colWidths=widths, repeatRows=1)
        pdf_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF7")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 6),
                    ("GRID", (0, 0), (-1, -1), 0.2, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(pdf_table)
        if table.row_count > len(rows):
            story.append(
                Paragraph(
                    f"PDF preview truncated. {table.row_count - len(rows)} additional rows are "
                    "available in the Excel/CSV exports.",
                    styles["BodyText"],
                )
            )
    document.build(story)
    return stream.getvalue()


def export_all(extraction: DocumentExtraction) -> dict[str, bytes]:
    stem = _safe_stem(extraction.source_name)
    outputs = {
        f"{stem}_extracted.json": export_json(extraction),
        f"{stem}_extracted.xlsx": export_xlsx(extraction),
        f"{stem}_extracted.docx": export_docx(extraction),
        f"{stem}_extracted.pdf": export_pdf(extraction),
        f"{stem}_csv_tables.zip": export_csv_zip(extraction),
    }
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, data in outputs.items():
            archive.writestr(filename, data)
    outputs[f"{stem}_complete_export.zip"] = bundle.getvalue()
    return outputs
