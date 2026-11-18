from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from biointel.api.main import app
from biointel.documents.exporters import export_all, export_xlsx
from biointel.documents.extractor import extract_document
from biointel.documents.history import (
    delete_run,
    get_run,
    history_summary,
    list_outputs,
    list_runs,
)
from biointel.documents.security import DocumentSecurityError, validate_document
from biointel.documents.service import process_document
from biointel.ui.navigation import PAGE_CATALOG


def sample_xlsx(*, formula_like: bool = False) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Results"
    sheet.append(["sample_id", "compound", "score"])
    sheet.append(["S1", "Aspirin", 0.91])
    sheet.append(["S2", "=DANGEROUS()" if formula_like else "Caffeine", 0.77])
    second = workbook.create_sheet("Metadata")
    second.append(["key", "value"])
    second.append(["project", "BioIntel"])
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def sample_docx() -> bytes:
    from docx import Document

    document = Document()
    document.add_heading("Study", level=1)
    document.add_paragraph("A structured biotechnology note.")
    table = document.add_table(rows=3, cols=2)
    table.cell(0, 0).text = "Target"
    table.cell(0, 1).text = "Score"
    table.cell(1, 0).text = "EGFR"
    table.cell(1, 1).text = "0.88"
    table.cell(2, 0).text = "BRAF"
    table.cell(2, 1).text = "0.76"
    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()


def sample_pdf() -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen.canvas import Canvas

    stream = io.BytesIO()
    pdf = Canvas(stream, pagesize=A4)
    pdf.drawString(72, 790, "BioIntel AI document extraction test")
    pdf.drawString(72, 760, "Target: EGFR")
    pdf.showPage()
    pdf.drawString(72, 790, "Second page")
    pdf.save()
    return stream.getvalue()


def test_extract_xlsx_docx_and_pdf() -> None:
    xlsx = extract_document("results.xlsx", sample_xlsx())
    assert xlsx.sheet_count == 2
    assert xlsx.table_count == 2
    assert xlsx.row_count == 3

    docx = extract_document("notes.docx", sample_docx())
    assert docx.paragraph_count >= 2
    assert docx.table_count == 1
    assert "structured biotechnology" in docx.text

    pdf = extract_document("paper.pdf", sample_pdf())
    assert pdf.page_count == 2
    assert "Target: EGFR" in pdf.text


def test_all_download_formats_are_generated() -> None:
    extraction = extract_document("results.xlsx", sample_xlsx())
    outputs = export_all(extraction)
    names = set(outputs)
    assert any(name.endswith(".xlsx") for name in names)
    assert any(name.endswith(".docx") for name in names)
    assert any(name.endswith(".pdf") for name in names)
    assert any(name.endswith(".json") for name in names)
    assert any(name.endswith("_csv_tables.zip") for name in names)
    assert any(name.endswith("_complete_export.zip") for name in names)
    assert all(outputs[name] for name in names)


def test_excel_export_neutralizes_formula_injection() -> None:
    from openpyxl import load_workbook

    from biointel.documents.models import DocumentExtraction, ExtractedTable

    extraction = DocumentExtraction(
        source_name="formula.docx",
        file_type="docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        source_sha256="0" * 64,
        source_size_bytes=1,
        text="formula safety",
        tables=(
            ExtractedTable(
                name="Unsafe strings",
                source="table:1",
                columns=("compound",),
                rows=(("=DANGEROUS()",),),
            ),
        ),
    )
    generated = export_xlsx(extraction)
    workbook = load_workbook(io.BytesIO(generated), data_only=False)
    result_sheets = [sheet for sheet in workbook.worksheets if sheet.title not in {"Summary", "Extracted Text"}]
    values = [cell.value for sheet in result_sheets for row in sheet.iter_rows() for cell in row]
    assert "'=DANGEROUS()" in values
    assert "=DANGEROUS()" not in values


def test_process_document_records_history_and_outputs(tmp_path: Path) -> None:
    processed = process_document(
        "results.xlsx",
        sample_xlsx(),
        project_root=tmp_path,
        keep_source=False,
    )
    history = tmp_path / "reports" / "document_history.sqlite3"
    run = get_run(history, processed.run_id)
    assert run.status == "completed"
    assert run.source_saved_path is None
    assert run.table_count == 2
    outputs = list_outputs(history, processed.run_id)
    assert len(outputs) == 6
    assert all(Path(output.path).is_file() for output in outputs)
    assert history_summary(history)["completed_runs"] == 1
    assert list_runs(history, query="results")

    delete_run(history, processed.run_id)
    assert list_runs(history) == []
    assert not Path(processed.output_directory).exists()


def test_document_security_rejects_type_mismatch_and_macros() -> None:
    with pytest.raises(DocumentSecurityError):
        validate_document("fake.pdf", sample_xlsx())
    with pytest.raises(DocumentSecurityError):
        validate_document("macro.xlsm", sample_xlsx())
    name, extension, _ = validate_document(
        "macro.xlsm",
        sample_xlsx(),
        policy=__import__(
            "biointel.documents.security", fromlist=["DocumentSafetyPolicy"]
        ).DocumentSafetyPolicy(allow_macro_workbooks=True),
    )
    assert name == "macro.xlsm"
    assert extension == ".xlsm"


def test_document_api_history_summary_and_upload(tmp_path: Path, monkeypatch) -> None:
    import biointel.api.main as api_main

    monkeypatch.setattr(api_main, "ROOT", tmp_path)
    client = TestClient(app)
    response = client.post(
        "/documents/extract",
        files={
            "file": (
                "api_results.xlsx",
                sample_xlsx(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"keep_source": "false", "max_rows_per_table": "100"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["extraction"]["table_count"] == 2

    summary = client.get("/documents/history/summary")
    assert summary.status_code == 200
    assert summary.json()["completed_runs"] == 1

    detail = client.get(f"/documents/history/{payload['run_id']}")
    assert detail.status_code == 200
    output_id = detail.json()["outputs"][0]["output_id"]
    download = client.get(f"/documents/outputs/{output_id}/download")
    assert download.status_code == 200
    assert download.content


def test_step26_navigation_catalog() -> None:
    assert len(PAGE_CATALOG) >= 71
    keys = {page.key for page in PAGE_CATALOG}
    assert {"document_intelligence", "document_history"} <= keys
