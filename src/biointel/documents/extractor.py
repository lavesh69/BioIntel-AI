from __future__ import annotations

import csv
import io
import json
import math
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4
from xml.etree import ElementTree

from biointel.documents.models import (
    DocumentExtraction,
    ExtractedRegion,
    ExtractedSection,
    ExtractedTable,
)
from biointel.documents.ocr import ocr_pdf
from biointel.documents.security import DocumentSafetyPolicy, sha256_bytes, validate_document


def _clean_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _normalise_headers(values: Iterable[Any], width: int) -> tuple[str, ...]:
    seen: dict[str, int] = {}
    headers: list[str] = []
    raw = list(values)
    for index in range(width):
        value = raw[index] if index < len(raw) else None
        base = str(value).strip() if value not in (None, "") else f"Column {index + 1}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        headers.append(base if count == 1 else f"{base} ({count})")
    return tuple(headers)


def _table_confidence(rows: list[list[Any]], width: int) -> float:
    if not rows or width < 1:
        return 0.0
    non_empty = sum(value not in (None, "") for row in rows for value in row[:width])
    density = non_empty / max(len(rows) * width, 1)
    consistent = sum(abs(len(row) - width) <= 1 for row in rows) / len(rows)
    header = rows[0][:width]
    header_quality = sum(value not in (None, "") for value in header) / width
    return round(min(1.0, 0.45 * density + 0.35 * consistent + 0.2 * header_quality), 4)


def _rectangular_table(
    name: str,
    source: str,
    raw_rows: Iterable[Iterable[Any]],
    *,
    max_rows: int,
    max_columns: int,
    metadata: dict[str, Any] | None = None,
) -> ExtractedTable | None:
    materialised = [list(row)[:max_columns] for row in raw_rows]
    materialised = [row for row in materialised if any(value not in (None, "") for value in row)]
    if not materialised:
        return None
    width = min(max(len(row) for row in materialised), max_columns)
    if width < 1:
        return None
    headers = _normalise_headers(materialised[0], width)
    data_rows = materialised[1 : max_rows + 1]
    rows: list[tuple[Any, ...]] = []
    for row in data_rows:
        padded = row + [None] * (width - len(row))
        rows.append(tuple(_clean_cell(value) for value in padded[:width]))
    return ExtractedTable(
        name=name,
        source=source,
        columns=headers,
        rows=tuple(rows),
        confidence=_table_confidence(materialised[: max_rows + 1], width),
        metadata=metadata or {},
    )


def _layout_text(words: list[dict[str, Any]], page_width: float) -> str:
    if not words:
        return ""
    # Basic layout-aware ordering: detect a strong central whitespace gap and read columns.
    centers = sorted((float(word["x0"]) + float(word["x1"])) / 2 for word in words)
    largest_gap = (0.0, None)
    for left, right in zip(centers, centers[1:]):
        gap = right - left
        if gap > largest_gap[0]:
            largest_gap = (gap, (left + right) / 2)
    split = largest_gap[1] if largest_gap[0] > page_width * 0.12 else None
    columns = [words]
    if split is not None:
        left_words = [word for word in words if float(word["x0"]) < split]
        right_words = [word for word in words if float(word["x0"]) >= split]
        if left_words and right_words:
            columns = [left_words, right_words]
    blocks: list[str] = []
    for column in columns:
        sorted_words = sorted(column, key=lambda item: (round(float(item["top"]) / 4), float(item["x0"])))
        lines: list[list[dict[str, Any]]] = []
        for word in sorted_words:
            if not lines or abs(float(word["top"]) - float(lines[-1][0]["top"])) > 4:
                lines.append([word])
            else:
                lines[-1].append(word)
        blocks.append(
            "\n".join(
                " ".join(str(word.get("text", "")) for word in sorted(line, key=lambda item: float(item["x0"])))
                for line in lines
            )
        )
    return "\n\n".join(block for block in blocks if block.strip())


def _stitch_pdf_tables(tables: list[ExtractedTable]) -> list[ExtractedTable]:
    if not tables:
        return tables
    stitched: list[ExtractedTable] = []
    current = tables[0]
    for candidate in tables[1:]:
        current_page = int(current.source.split(":")[-1]) if current.source.startswith("page:") else -1
        candidate_page = int(candidate.source.split(":")[-1]) if candidate.source.startswith("page:") else -1
        same_columns = tuple(value.strip().lower() for value in current.columns) == tuple(
            value.strip().lower() for value in candidate.columns
        )
        if same_columns and candidate_page == current_page + 1:
            metadata = dict(current.metadata)
            stitched_from = list(metadata.get("stitched_from", [current.source]))
            stitched_from.append(candidate.source)
            metadata["stitched_from"] = stitched_from
            current = ExtractedTable(
                name=current.name.replace(" Table 1", "") + " (multi-page)",
                source=f"pages:{current_page}-{candidate_page}",
                columns=current.columns,
                rows=current.rows + candidate.rows,
                confidence=round(
                    sum(value for value in (current.confidence, candidate.confidence) if value is not None)
                    / max(sum(value is not None for value in (current.confidence, candidate.confidence)), 1),
                    4,
                ),
                metadata=metadata,
            )
        else:
            stitched.append(current)
            current = candidate
    stitched.append(current)
    return stitched


def _extract_pdf(
    data: bytes,
    source_name: str,
    mime_type: str,
    *,
    password: str | None,
    max_rows_per_table: int,
    max_columns: int,
    ocr_mode: str,
    ocr_language: str,
    ocr_confidence_threshold: float,
) -> DocumentExtraction:
    import pdfplumber
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data), strict=False)
    if reader.is_encrypted:
        if not password or reader.decrypt(password) == 0:
            raise ValueError("PDF is encrypted. Provide the correct password.")
    sections: list[ExtractedSection] = []
    page_texts: list[str] = []
    warnings: list[str] = []
    tables: list[ExtractedTable] = []
    regions: list[ExtractedRegion] = []
    ocr_pages: list[int] = []
    page_dimensions: list[dict[str, float]] = []

    with pdfplumber.open(io.BytesIO(data), password=password or None) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            page_dimensions.append({"page": page_index, "width": float(page.width), "height": float(page.height)})
            try:
                words = page.extract_words(use_text_flow=False, keep_blank_chars=False) or []
                text = _layout_text(words, float(page.width)).strip()
                for word in words:
                    regions.append(
                        ExtractedRegion(
                            region_id=uuid4().hex,
                            source=f"page:{page_index}",
                            kind="pdf_word",
                            text=str(word.get("text", "")),
                            page_number=page_index,
                            bbox=(
                                float(word["x0"]) / float(page.width),
                                float(word["top"]) / float(page.height),
                                float(word["x1"]) / float(page.width),
                                float(word["bottom"]) / float(page.height),
                            ),
                            confidence=1.0,
                            metadata={"coordinate_space": "normalized_page"},
                        )
                    )
            except Exception as exc:
                text = ""
                warnings.append(f"Page {page_index}: layout text extraction failed ({exc}).")
            if len(text) < 30 and ocr_mode in {"auto", "force"}:
                ocr_pages.append(page_index)
            page_texts.append(text)
            sections.append(
                ExtractedSection(
                    name=f"Page {page_index}",
                    text=text,
                    source=f"page:{page_index}",
                    confidence=1.0 if text else None,
                    metadata={"extraction_method": "layout_text"},
                )
            )
            try:
                found_tables = page.find_tables() or []
            except Exception as exc:
                warnings.append(f"Page {page_index}: table detection failed ({exc}).")
                found_tables = []
            for table_index, found in enumerate(found_tables, start=1):
                try:
                    raw_table = found.extract()
                    bbox = tuple(map(float, found.bbox))
                except Exception as exc:
                    warnings.append(f"Page {page_index} table {table_index}: extraction failed ({exc}).")
                    continue
                table = _rectangular_table(
                    f"PDF Page {page_index} Table {table_index}",
                    f"page:{page_index}",
                    raw_table,
                    max_rows=max_rows_per_table,
                    max_columns=max_columns,
                    metadata={
                        "bbox": [
                            bbox[0] / float(page.width),
                            bbox[1] / float(page.height),
                            bbox[2] / float(page.width),
                            bbox[3] / float(page.height),
                        ],
                        "coordinate_space": "normalized_page",
                    },
                )
                if table is not None:
                    tables.append(table)
                    regions.append(
                        ExtractedRegion(
                            region_id=uuid4().hex,
                            source=f"page:{page_index}",
                            kind="pdf_table",
                            text=table.name,
                            page_number=page_index,
                            bbox=tuple(table.metadata["bbox"]),
                            confidence=table.confidence,
                            metadata={"table_name": table.name},
                        )
                    )

    if ocr_mode == "force":
        ocr_pages = list(range(1, len(reader.pages) + 1))
    if ocr_pages:
        try:
            ocr_results = ocr_pdf(
                data,
                sorted(set(ocr_pages)),
                language=ocr_language,
                confidence_threshold=ocr_confidence_threshold,
            )
            for result in ocr_results:
                index = result.page_number - 1
                if result.text and (ocr_mode == "force" or len(page_texts[index]) < 30):
                    page_texts[index] = result.text
                    sections[index] = ExtractedSection(
                        name=f"Page {result.page_number}",
                        text=result.text,
                        source=f"page:{result.page_number}",
                        confidence=result.mean_confidence,
                        metadata={"extraction_method": "ocr", "requires_review": result.requires_review},
                    )
                regions.extend(result.regions)
                warnings.extend(result.warnings)
        except Exception as exc:
            warnings.append(f"OCR was requested but could not run ({exc}).")

    tables = _stitch_pdf_tables(tables)
    combined = "\n\n".join(text for text in page_texts if text)
    non_empty_pages = sum(bool(text.strip()) for text in page_texts)
    if reader.pages and non_empty_pages / len(reader.pages) < 0.35:
        warnings.append(
            "Most PDF pages contain little extractable text. Enable reviewed OCR for scanned pages."
        )
    metadata = {
        str(key).lstrip("/"): str(value)
        for key, value in dict(reader.metadata or {}).items()
        if value is not None
    }
    metadata.update(
        {
            "encrypted": bool(reader.is_encrypted),
            "non_empty_text_pages": non_empty_pages,
            "ocr_mode": ocr_mode,
            "ocr_pages": sorted(set(ocr_pages)),
            "page_dimensions": page_dimensions,
            "layout_provenance": "normalized page bounding boxes",
        }
    )
    return DocumentExtraction(
        source_name=source_name,
        file_type="pdf",
        mime_type=mime_type,
        source_sha256=sha256_bytes(data),
        source_size_bytes=len(data),
        text=combined,
        sections=tuple(sections),
        tables=tuple(tables),
        metadata=metadata,
        warnings=tuple(dict.fromkeys(warnings)),
        regions=tuple(regions),
        page_count=len(reader.pages),
    )


def _extract_xlsx(
    data: bytes,
    source_name: str,
    extension: str,
    mime_type: str,
    *,
    max_rows_per_table: int,
    max_columns: int,
) -> DocumentExtraction:
    from openpyxl import load_workbook

    value_workbook = load_workbook(
        io.BytesIO(data), read_only=True, data_only=True, keep_links=False, keep_vba=False
    )
    formula_workbook = load_workbook(
        io.BytesIO(data), read_only=False, data_only=False, keep_links=False, keep_vba=False
    )
    tables: list[ExtractedTable] = []
    sections: list[ExtractedSection] = []
    warnings: list[str] = []
    regions: list[ExtractedRegion] = []
    sheet_metadata: list[dict[str, Any]] = []
    text_lines: list[str] = []
    formula_records: list[tuple[Any, ...]] = []
    formula_sheets = {sheet.title: sheet for sheet in formula_workbook.worksheets}
    for value_sheet in value_workbook.worksheets:
        formula_sheet = formula_sheets[value_sheet.title]
        rows: list[list[Any]] = []
        for row_number, value_row in enumerate(value_sheet.iter_rows(values_only=True), start=1):
            if row_number > max_rows_per_table + 1:
                warnings.append(
                    f"Sheet {value_sheet.title!r} was truncated after {max_rows_per_table} data rows."
                )
                break
            merged_row: list[Any] = []
            for column_number, value in enumerate(value_row[:max_columns], start=1):
                formula_cell = formula_sheet.cell(row=row_number, column=column_number)
                formula = formula_cell.value
                if isinstance(formula, str) and formula.startswith("="):
                    formula_records.append(
                        (
                            value_sheet.title,
                            formula_cell.coordinate,
                            formula,
                            _clean_cell(value),
                            str(formula_cell.number_format or ""),
                        )
                    )
                merged_row.append(value if value is not None else formula)
                if value not in (None, "") or formula not in (None, ""):
                    regions.append(
                        ExtractedRegion(
                            region_id=uuid4().hex,
                            source=f"sheet:{value_sheet.title}",
                            kind="spreadsheet_cell",
                            text=str(value if value is not None else formula),
                            bbox=(float(column_number), float(row_number), float(column_number), float(row_number)),
                            confidence=1.0,
                            metadata={"cell": formula_cell.coordinate, "coordinate_space": "spreadsheet"},
                        )
                    )
            rows.append(merged_row)
        table = _rectangular_table(
            f"Sheet - {value_sheet.title}",
            f"sheet:{value_sheet.title}",
            rows,
            max_rows=max_rows_per_table,
            max_columns=max_columns,
            metadata={"sheet_state": value_sheet.sheet_state},
        )
        preview = ""
        if table is not None:
            tables.append(table)
            preview = "\n".join(
                " | ".join("" if value is None else str(value) for value in row)
                for row in table.rows[:20]
            )
        sections.append(
            ExtractedSection(
                name=value_sheet.title,
                text=preview,
                source=f"sheet:{value_sheet.title}",
                confidence=table.confidence if table else None,
            )
        )
        text_lines.append(f"[{value_sheet.title}]\n{preview}".strip())
        hidden_rows = [index for index, dimension in formula_sheet.row_dimensions.items() if dimension.hidden]
        hidden_columns = [key for key, dimension in formula_sheet.column_dimensions.items() if dimension.hidden]
        comments = []
        hyperlinks = []
        for row in formula_sheet.iter_rows(
            min_row=1,
            max_row=min(formula_sheet.max_row, max_rows_per_table + 1),
            max_col=min(formula_sheet.max_column, max_columns),
        ):
            for cell in row:
                if cell.comment:
                    comments.append({"cell": cell.coordinate, "author": cell.comment.author, "text": cell.comment.text})
                if cell.hyperlink:
                    hyperlinks.append({"cell": cell.coordinate, "target": cell.hyperlink.target or cell.hyperlink.location})
        validations = []
        try:
            for validation in formula_sheet.data_validations.dataValidation:
                validations.append({
                    "type": validation.type,
                    "formula1": validation.formula1,
                    "formula2": validation.formula2,
                    "ranges": str(validation.sqref),
                })
        except Exception:
            pass
        sheet_metadata.append(
            {
                "title": value_sheet.title,
                "state": value_sheet.sheet_state,
                "max_row": value_sheet.max_row,
                "max_column": value_sheet.max_column,
                "merged_ranges": [str(item) for item in formula_sheet.merged_cells.ranges],
                "hidden_rows": hidden_rows,
                "hidden_columns": hidden_columns,
                "comments": comments,
                "hyperlinks": hyperlinks,
                "data_validations": validations,
                "chart_count": len(getattr(formula_sheet, "_charts", [])),
                "table_count": len(formula_sheet.tables),
            }
        )
    if formula_records:
        tables.append(
            ExtractedTable(
                name="Workbook Formula Lineage",
                source="workbook:formulas",
                columns=("Sheet", "Cell", "Formula", "Cached Value", "Number Format"),
                rows=tuple(formula_records),
                confidence=1.0,
                metadata={"purpose": "formula_and_cached_value_dual_storage"},
            )
        )
        warnings.append(
            f"Workbook contains {len(formula_records)} formula cell(s); formulas and cached values "
            "were preserved separately."
        )
    if extension == ".xlsm":
        warnings.append("Workbook macros were ignored and never executed.")
    properties = formula_workbook.properties
    named_ranges = []
    try:
        for name, defined_name in formula_workbook.defined_names.items():
            named_ranges.append({"name": name, "value": defined_name.attr_text})
    except Exception:
        pass
    metadata = {
        "title": properties.title,
        "subject": properties.subject,
        "creator": properties.creator,
        "last_modified_by": properties.lastModifiedBy,
        "created": properties.created.isoformat() if properties.created else None,
        "modified": properties.modified.isoformat() if properties.modified else None,
        "sheets": sheet_metadata,
        "formula_cell_count": len(formula_records),
        "formula_policy": "formula and cached value stored separately",
        "named_ranges": named_ranges,
        "calculation_mode": getattr(formula_workbook.calculation, "calcMode", None),
    }
    value_workbook.close()
    formula_workbook.close()
    return DocumentExtraction(
        source_name=source_name,
        file_type=extension.lstrip("."),
        mime_type=mime_type,
        source_sha256=sha256_bytes(data),
        source_size_bytes=len(data),
        text="\n\n".join(line for line in text_lines if line),
        sections=tuple(sections),
        tables=tuple(tables),
        metadata=metadata,
        warnings=tuple(dict.fromkeys(warnings)),
        regions=tuple(regions),
        sheet_count=len(sheet_metadata),
    )


def _extract_xls(
    data: bytes,
    source_name: str,
    mime_type: str,
    *,
    max_rows_per_table: int,
    max_columns: int,
) -> DocumentExtraction:
    try:
        import pandas as pd
        import xlrd  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Legacy XLS support requires xlrd. Convert to XLSX or install Step 27 requirements."
        ) from exc
    excel = pd.ExcelFile(io.BytesIO(data), engine="xlrd")
    tables: list[ExtractedTable] = []
    sections: list[ExtractedSection] = []
    warnings: list[str] = []
    for sheet_name in excel.sheet_names:
        frame = pd.read_excel(excel, sheet_name=sheet_name, header=None, nrows=max_rows_per_table + 1)
        if frame.shape[1] > max_columns:
            frame = frame.iloc[:, :max_columns]
            warnings.append(f"Sheet {sheet_name!r} was truncated to {max_columns} columns.")
        table = _rectangular_table(
            f"Sheet - {sheet_name}",
            f"sheet:{sheet_name}",
            frame.where(frame.notna(), None).values.tolist(),
            max_rows=max_rows_per_table,
            max_columns=max_columns,
        )
        preview = ""
        if table is not None:
            tables.append(table)
            preview = "\n".join(
                " | ".join("" if value is None else str(value) for value in row)
                for row in table.rows[:20]
            )
        sections.append(ExtractedSection(sheet_name, preview, f"sheet:{sheet_name}"))
    return DocumentExtraction(
        source_name=source_name,
        file_type="xls",
        mime_type=mime_type,
        source_sha256=sha256_bytes(data),
        source_size_bytes=len(data),
        text="\n\n".join(section.text for section in sections if section.text),
        sections=tuple(sections),
        tables=tuple(tables),
        metadata={"sheets": excel.sheet_names, "legacy_format": True},
        warnings=tuple(warnings),
        sheet_count=len(excel.sheet_names),
    )


def _xml_text_from_zip(data: bytes, path: str) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if path not in archive.namelist():
                return ""
            root = ElementTree.fromstring(archive.read(path))
            return "\n".join(
                text.strip()
                for text in root.itertext()
                if text and text.strip()
            )
    except Exception:
        return ""


def _extract_docx(
    data: bytes,
    source_name: str,
    mime_type: str,
    *,
    max_rows_per_table: int,
    max_columns: int,
) -> DocumentExtraction:
    from docx import Document

    document = Document(io.BytesIO(data))
    paragraphs: list[str] = []
    sections: list[ExtractedSection] = []
    regions: list[ExtractedRegion] = []
    current_heading = "Document"
    current_text: list[str] = []
    warnings: list[str] = []
    for index, paragraph in enumerate(document.paragraphs, start=1):
        text = paragraph.text.strip()
        if not text:
            continue
        style_name = str(paragraph.style.name or "")
        regions.append(
            ExtractedRegion(
                region_id=uuid4().hex,
                source=f"paragraph:{index}",
                kind="docx_paragraph",
                text=text,
                bbox=None,
                confidence=1.0,
                metadata={"style": style_name, "paragraph_index": index},
            )
        )
        if style_name.lower().startswith("heading"):
            if current_text:
                sections.append(
                    ExtractedSection(
                        name=current_heading,
                        text="\n".join(current_text),
                        source=f"heading:{current_heading}",
                        confidence=1.0,
                    )
                )
            current_heading = text
            current_text = []
        else:
            current_text.append(text)
        paragraphs.append(text)
    if current_text or not sections:
        sections.append(
            ExtractedSection(
                name=current_heading,
                text="\n".join(current_text),
                source=f"heading:{current_heading}",
                confidence=1.0,
            )
        )
    tables: list[ExtractedTable] = []
    for index, source_table in enumerate(document.tables, start=1):
        raw_rows = [
            [cell.text.strip() for cell in row.cells[:max_columns]]
            for row in source_table.rows[: max_rows_per_table + 1]
        ]
        if len(source_table.rows) > max_rows_per_table + 1:
            warnings.append(f"DOCX table {index} was truncated after {max_rows_per_table} rows.")
        table = _rectangular_table(
            f"DOCX Table {index}",
            f"table:{index}",
            raw_rows,
            max_rows=max_rows_per_table,
            max_columns=max_columns,
            metadata={"table_index": index},
        )
        if table is not None:
            tables.append(table)
    headers, footers = [], []
    for section_index, section in enumerate(document.sections, start=1):
        header = "\n".join(paragraph.text.strip() for paragraph in section.header.paragraphs if paragraph.text.strip())
        footer = "\n".join(paragraph.text.strip() for paragraph in section.footer.paragraphs if paragraph.text.strip())
        if header:
            headers.append({"section": section_index, "text": header})
        if footer:
            footers.append({"section": section_index, "text": footer})
    footnotes = _xml_text_from_zip(data, "word/footnotes.xml")
    endnotes = _xml_text_from_zip(data, "word/endnotes.xml")
    comments = _xml_text_from_zip(data, "word/comments.xml")
    tracked_insertions = tracked_deletions = embedded_objects = 0
    image_names: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
            tracked_insertions = document_xml.count("<w:ins")
            tracked_deletions = document_xml.count("<w:del")
            image_names = [name for name in archive.namelist() if name.startswith("word/media/")]
            embedded_objects = sum(name.startswith("word/embeddings/") for name in archive.namelist())
    except Exception:
        pass
    properties = document.core_properties
    metadata = {
        "title": properties.title,
        "subject": properties.subject,
        "author": properties.author,
        "last_modified_by": properties.last_modified_by,
        "keywords": properties.keywords,
        "comments_property": properties.comments,
        "created": properties.created.isoformat() if properties.created else None,
        "modified": properties.modified.isoformat() if properties.modified else None,
        "headers": headers,
        "footers": footers,
        "footnotes": footnotes,
        "endnotes": endnotes,
        "review_comments": comments,
        "tracked_insertions": tracked_insertions,
        "tracked_deletions": tracked_deletions,
        "embedded_objects": embedded_objects,
        "image_names": image_names,
    }
    if tracked_insertions or tracked_deletions:
        warnings.append(
            f"Document contains tracked changes ({tracked_insertions} insertions, "
            f"{tracked_deletions} deletions); review the revision history."
        )
    if comments:
        warnings.append("Document contains reviewer comments; comments were extracted to metadata.")
    return DocumentExtraction(
        source_name=source_name,
        file_type="docx",
        mime_type=mime_type,
        source_sha256=sha256_bytes(data),
        source_size_bytes=len(data),
        text="\n\n".join(paragraphs),
        sections=tuple(sections),
        tables=tuple(tables),
        metadata=metadata,
        warnings=tuple(dict.fromkeys(warnings)),
        regions=tuple(regions),
        paragraph_count=len(paragraphs),
        image_count=max(len(document.inline_shapes), len(image_names)),
    )


def _decode_text(data: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1252", "latin-1"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8-replace"


def _extract_delimited(
    data: bytes,
    source_name: str,
    extension: str,
    mime_type: str,
    *,
    max_rows_per_table: int,
    max_columns: int,
) -> DocumentExtraction:
    text, encoding = _decode_text(data)
    delimiter = "\t" if extension == ".tsv" else None
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(text[:20_000], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = []
    warnings = []
    for index, row in enumerate(reader):
        if index > max_rows_per_table:
            warnings.append(f"Delimited file was truncated after {max_rows_per_table} data rows.")
            break
        rows.append(row[:max_columns])
    table = _rectangular_table(
        "Delimited Data",
        "document",
        rows,
        max_rows=max_rows_per_table,
        max_columns=max_columns,
        metadata={"delimiter": delimiter, "encoding": encoding},
    )
    return DocumentExtraction(
        source_name=source_name,
        file_type=extension.lstrip("."),
        mime_type=mime_type,
        source_sha256=sha256_bytes(data),
        source_size_bytes=len(data),
        text=text,
        sections=(ExtractedSection("Document", text, "document", 1.0),),
        tables=(table,) if table else (),
        metadata={"encoding": encoding, "delimiter": delimiter},
        warnings=tuple(warnings),
    )


def _flatten_mapping(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(_flatten_mapping(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            rows.extend(_flatten_mapping(child, f"{prefix}[{index}]"))
    else:
        rows.append((prefix or "$", _clean_cell(value)))
    return rows


def _extract_structured(
    data: bytes,
    source_name: str,
    extension: str,
    mime_type: str,
    *,
    max_rows_per_table: int,
    max_columns: int,
) -> DocumentExtraction:
    text, encoding = _decode_text(data)
    if extension == ".json":
        parsed = json.loads(text)
    elif extension in {".yaml", ".yml"}:
        import yaml

        parsed = yaml.safe_load(text)
    else:
        root = ElementTree.fromstring(text)

        def convert(element: ElementTree.Element) -> dict[str, Any]:
            children = list(element)
            payload: dict[str, Any] = {"@attributes": dict(element.attrib)} if element.attrib else {}
            if children:
                grouped: dict[str, list[Any]] = {}
                for child in children:
                    grouped.setdefault(child.tag.split("}")[-1], []).append(convert(child))
                payload.update({key: values[0] if len(values) == 1 else values for key, values in grouped.items()})
            if element.text and element.text.strip():
                payload["#text"] = element.text.strip()
            return payload

        parsed = {root.tag.split("}")[-1]: convert(root)}
    flattened = _flatten_mapping(parsed)[: max_rows_per_table]
    table = ExtractedTable(
        name="Structured Data",
        source="document",
        columns=("Path", "Value"),
        rows=tuple(flattened),
        confidence=1.0,
        metadata={"encoding": encoding},
    )
    return DocumentExtraction(
        source_name=source_name,
        file_type=extension.lstrip("."),
        mime_type=mime_type,
        source_sha256=sha256_bytes(data),
        source_size_bytes=len(data),
        text=text,
        sections=(ExtractedSection("Document", text, "document", 1.0),),
        tables=(table,),
        metadata={"encoding": encoding, "root_type": type(parsed).__name__},
        warnings=(),
    )


def _extract_text_or_html(
    data: bytes,
    source_name: str,
    extension: str,
    mime_type: str,
    *,
    max_rows_per_table: int,
    max_columns: int,
) -> DocumentExtraction:
    text, encoding = _decode_text(data)
    tables: list[ExtractedTable] = []
    metadata: dict[str, Any] = {"encoding": encoding}
    if extension in {".html", ".htm"}:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(text, "html.parser")
        for node in soup(["script", "style", "noscript"]):
            node.decompose()
        clean_text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
        metadata.update(
            {
                "title": soup.title.string.strip() if soup.title and soup.title.string else None,
                "link_count": len(soup.find_all("a")),
                "image_count": len(soup.find_all("img")),
            }
        )
        try:
            import pandas as pd

            for index, frame in enumerate(pd.read_html(io.StringIO(text)), start=1):
                rows = [list(frame.columns)] + frame.where(frame.notna(), None).values.tolist()
                table = _rectangular_table(
                    f"HTML Table {index}",
                    f"table:{index}",
                    rows,
                    max_rows=max_rows_per_table,
                    max_columns=max_columns,
                )
                if table:
                    tables.append(table)
        except (ValueError, ImportError):
            pass
        text = clean_text
    return DocumentExtraction(
        source_name=source_name,
        file_type=extension.lstrip("."),
        mime_type=mime_type,
        source_sha256=sha256_bytes(data),
        source_size_bytes=len(data),
        text=text,
        sections=(ExtractedSection("Document", text, "document", 1.0),),
        tables=tuple(tables),
        metadata=metadata,
        warnings=(),
        image_count=int(metadata.get("image_count", 0)),
    )


def _extract_pptx(
    data: bytes,
    source_name: str,
    mime_type: str,
    *,
    max_rows_per_table: int,
    max_columns: int,
) -> DocumentExtraction:
    from pptx import Presentation

    presentation = Presentation(io.BytesIO(data))
    sections: list[ExtractedSection] = []
    tables: list[ExtractedTable] = []
    regions: list[ExtractedRegion] = []
    image_count = 0
    notes_count = 0
    for slide_index, slide in enumerate(presentation.slides, start=1):
        slide_text: list[str] = []
        for shape_index, shape in enumerate(slide.shapes, start=1):
            if getattr(shape, "has_text_frame", False):
                value = shape.text.strip()
                if value:
                    slide_text.append(value)
                    regions.append(
                        ExtractedRegion(
                            region_id=uuid4().hex,
                            source=f"slide:{slide_index}",
                            kind="pptx_text",
                            text=value,
                            bbox=(float(shape.left), float(shape.top), float(shape.left + shape.width), float(shape.top + shape.height)),
                            confidence=1.0,
                            metadata={"coordinate_space": "emu", "shape_index": shape_index},
                        )
                    )
            if getattr(shape, "has_table", False):
                raw = [
                    [cell.text for cell in list(row.cells)[:max_columns]]
                    for row in list(shape.table.rows)[: max_rows_per_table + 1]
                ]
                table = _rectangular_table(
                    f"Slide {slide_index} Table",
                    f"slide:{slide_index}",
                    raw,
                    max_rows=max_rows_per_table,
                    max_columns=max_columns,
                )
                if table:
                    tables.append(table)
            if getattr(shape, "shape_type", None) == 13:
                image_count += 1
        try:
            notes = slide.notes_slide.notes_text_frame.text.strip()
        except Exception:
            notes = ""
        if notes:
            notes_count += 1
            slide_text.append(f"[Speaker notes]\n{notes}")
        sections.append(
            ExtractedSection(
                name=f"Slide {slide_index}",
                text="\n".join(slide_text),
                source=f"slide:{slide_index}",
                confidence=1.0,
            )
        )
    return DocumentExtraction(
        source_name=source_name,
        file_type="pptx",
        mime_type=mime_type,
        source_sha256=sha256_bytes(data),
        source_size_bytes=len(data),
        text="\n\n".join(section.text for section in sections if section.text),
        sections=tuple(sections),
        tables=tuple(tables),
        metadata={"slide_count": len(presentation.slides), "speaker_notes_slides": notes_count},
        warnings=(),
        regions=tuple(regions),
        page_count=len(presentation.slides),
        image_count=image_count,
    )


def _extract_open_document(
    data: bytes,
    source_name: str,
    extension: str,
    mime_type: str,
    *,
    max_rows_per_table: int,
    max_columns: int,
) -> DocumentExtraction:
    if extension == ".odt":
        from odf import teletype
        from odf.opendocument import load
        from odf.text import H, P

        document = load(io.BytesIO(data))
        paragraphs = [teletype.extractText(node).strip() for node in document.getElementsByType(P)]
        headings = [teletype.extractText(node).strip() for node in document.getElementsByType(H)]
        text = "\n\n".join(value for value in paragraphs if value)
        return DocumentExtraction(
            source_name=source_name,
            file_type="odt",
            mime_type=mime_type,
            source_sha256=sha256_bytes(data),
            source_size_bytes=len(data),
            text=text,
            sections=(ExtractedSection("Document", text, "document", 1.0),),
            metadata={"headings": headings},
            warnings=(),
            paragraph_count=len([value for value in paragraphs if value]),
        )
    import pandas as pd

    frames = pd.read_excel(io.BytesIO(data), sheet_name=None, engine="odf")
    tables, sections = [], []
    for name, frame in frames.items():
        rows = [list(frame.columns)] + frame.where(frame.notna(), None).values.tolist()
        table = _rectangular_table(
            f"Sheet - {name}",
            f"sheet:{name}",
            rows,
            max_rows=max_rows_per_table,
            max_columns=max_columns,
        )
        if table:
            tables.append(table)
            sections.append(ExtractedSection(name, "\n".join(" | ".join(map(str, row)) for row in table.rows[:20]), f"sheet:{name}"))
    return DocumentExtraction(
        source_name=source_name,
        file_type="ods",
        mime_type=mime_type,
        source_sha256=sha256_bytes(data),
        source_size_bytes=len(data),
        text="\n\n".join(section.text for section in sections),
        sections=tuple(sections),
        tables=tuple(tables),
        metadata={"sheets": list(frames)},
        warnings=(),
        sheet_count=len(frames),
    )


def extract_document(
    filename: str,
    data: bytes,
    *,
    password: str | None = None,
    max_rows_per_table: int = 50_000,
    max_columns: int = 256,
    policy: DocumentSafetyPolicy | None = None,
    ocr_mode: str = "off",
    ocr_language: str = "eng",
    ocr_confidence_threshold: float = 70.0,
) -> DocumentExtraction:
    if max_rows_per_table < 1 or max_rows_per_table > 250_000:
        raise ValueError("max_rows_per_table must be between 1 and 250,000.")
    if max_columns < 1 or max_columns > 2_000:
        raise ValueError("max_columns must be between 1 and 2,000.")
    if ocr_mode not in {"off", "auto", "force"}:
        raise ValueError("ocr_mode must be off, auto or force.")
    source_name, extension, mime_type = validate_document(filename, data, policy=policy)
    if extension == ".pdf":
        return _extract_pdf(
            data,
            source_name,
            mime_type,
            password=password,
            max_rows_per_table=max_rows_per_table,
            max_columns=max_columns,
            ocr_mode=ocr_mode,
            ocr_language=ocr_language,
            ocr_confidence_threshold=ocr_confidence_threshold,
        )
    if extension in {".xlsx", ".xlsm"}:
        return _extract_xlsx(data, source_name, extension, mime_type, max_rows_per_table=max_rows_per_table, max_columns=max_columns)
    if extension == ".xls":
        return _extract_xls(data, source_name, mime_type, max_rows_per_table=max_rows_per_table, max_columns=max_columns)
    if extension == ".docx":
        return _extract_docx(data, source_name, mime_type, max_rows_per_table=max_rows_per_table, max_columns=max_columns)
    if extension in {".csv", ".tsv"}:
        return _extract_delimited(data, source_name, extension, mime_type, max_rows_per_table=max_rows_per_table, max_columns=max_columns)
    if extension in {".json", ".xml", ".yaml", ".yml"}:
        return _extract_structured(data, source_name, extension, mime_type, max_rows_per_table=max_rows_per_table, max_columns=max_columns)
    if extension in {".txt", ".md", ".html", ".htm"}:
        return _extract_text_or_html(data, source_name, extension, mime_type, max_rows_per_table=max_rows_per_table, max_columns=max_columns)
    if extension == ".pptx":
        return _extract_pptx(data, source_name, mime_type, max_rows_per_table=max_rows_per_table, max_columns=max_columns)
    if extension in {".odt", ".ods"}:
        return _extract_open_document(data, source_name, extension, mime_type, max_rows_per_table=max_rows_per_table, max_columns=max_columns)
    raise ValueError(f"Unsupported document extension: {Path(source_name).suffix}")
