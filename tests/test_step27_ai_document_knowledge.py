from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from biointel.api.main import app
from biointel.documents.bridge import register_table_as_dataset
from biointel.documents.extractor import extract_document
from biointel.documents.history import (
    get_run,
    list_entities,
    list_runs,
    restore_run,
    search_content,
    soft_delete_run,
    verify_output,
)
from biointel.documents.intelligence import compare_extractions
from biointel.documents.service import process_document, process_documents
from biointel.ui.navigation import PAGE_CATALOG


def sample_csv() -> bytes:
    return (
        "canonical_smiles,protein_sequence,standard_value,standard_units,activity_type\n"
        "CCO,MKTIIALSYIFCLVFADYKDDDDK,10,nM,IC50\n"
        "CCN,GAVLIPFYWSTCMNQDEKRH,120,nM,Ki\n"
    ).encode()


def sample_xlsx() -> bytes:
    from openpyxl import Workbook
    from openpyxl.comments import Comment

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Results"
    sheet.append(["Target", "Value", "Formula"])
    sheet.append(["EGFR", 10, "=B2*2"])
    sheet["A2"].comment = Comment("Reviewed target", "Scientist")
    sheet["A2"].hyperlink = "https://example.org/egfr"
    sheet.merge_cells("A4:B4")
    sheet["A4"] = "Merged heading"
    sheet.row_dimensions[5].hidden = True
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def sample_pptx() -> bytes:
    from pptx import Presentation
    from pptx.util import Inches

    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    textbox = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1))
    textbox.text = "EGFR inhibition IC50 = 12 nM in Homo sapiens."
    table = slide.shapes.add_table(2, 2, Inches(1), Inches(2), Inches(5), Inches(2)).table
    table.cell(0, 0).text = "Target"
    table.cell(0, 1).text = "Score"
    table.cell(1, 0).text = "EGFR"
    table.cell(1, 1).text = "0.91"
    stream = io.BytesIO()
    presentation.save(stream)
    return stream.getvalue()


def test_new_input_formats_and_scientific_entities() -> None:
    csv_extraction = extract_document("activity.csv", sample_csv())
    assert csv_extraction.table_count == 1
    assert csv_extraction.row_count == 2

    json_extraction = extract_document(
        "study.json",
        json.dumps({"target": "EGFR", "result": {"IC50": "10 nM"}}).encode(),
    )
    assert json_extraction.table_count == 1

    pptx_extraction = extract_document("slides.pptx", sample_pptx())
    assert pptx_extraction.page_count == 1
    assert pptx_extraction.table_count == 1
    assert "EGFR inhibition" in pptx_extraction.text


def test_excel_formula_lineage_and_metadata() -> None:
    extraction = extract_document("formula.xlsx", sample_xlsx())
    formula_tables = [table for table in extraction.tables if "Formula Lineage" in table.name]
    assert formula_tables
    assert formula_tables[0].rows[0][2] == "=B2*2"
    sheet = extraction.metadata["sheets"][0]
    assert sheet["merged_ranges"] == ["A4:B4"]
    assert sheet["comments"][0]["author"] == "Scientist"
    assert sheet["hyperlinks"][0]["cell"] == "A2"


def test_process_indexes_entities_search_duplicate_and_soft_delete(tmp_path: Path) -> None:
    first = process_document("activity.csv", sample_csv(), project_root=tmp_path)
    assert first.extraction.entity_count >= 2
    history = tmp_path / "reports" / "document_history.sqlite3"
    hits = search_content(history, "IC50", limit=20)
    assert hits
    entities = list_entities(history, run_id=first.run_id)
    assert any(entity["entity_type"] == "assay_endpoint" for entity in entities)

    reused = process_document(
        "activity.csv",
        sample_csv(),
        project_root=tmp_path,
        duplicate_policy="reuse",
    )
    assert reused.reused_from_run_id == first.run_id
    assert reused.run_id == first.run_id

    output = first.outputs[0]
    assert verify_output(history, output.output_id)["valid"] is True
    soft_delete_run(history, first.run_id)
    assert list_runs(history) == []
    assert get_run(history, first.run_id).deleted_at_utc
    restore_run(history, first.run_id)
    assert len(list_runs(history)) == 1


def test_batch_processing_and_dataset_bridge(tmp_path: Path) -> None:
    result = process_documents(
        [("activity.csv", sample_csv()), ("slides.pptx", sample_pptx())],
        project_root=tmp_path,
    )
    assert result.completed == 2
    assert result.failed == 0
    csv_run = next(item for item in result.processed if item.extraction.file_type == "csv")
    record = register_table_as_dataset(
        tmp_path,
        run_id=csv_run.run_id,
        table_index=0,
        dataset_name="Document activity table",
        dataset_version="1.0",
    )
    assert record["row_count"] == 2
    assert record["metadata"]["step27_document_bridge"] is True


def test_document_comparison_detects_shared_entities() -> None:
    left_extraction = extract_document("left.txt", b"EGFR IC50 = 10 nM in human cancer.")
    right_extraction = extract_document("right.txt", b"EGFR IC50 = 200 nM in Homo sapiens cancer.")
    from biointel.documents.intelligence import enrich_extraction

    comparison = compare_extractions(
        enrich_extraction(left_extraction),
        enrich_extraction(right_extraction),
    )
    assert any(item["normalized"] == "egfr" for item in comparison["shared_entities"])
    assert comparison["possible_numeric_contradictions"]


def test_step27_api_batch_search_and_organization(tmp_path: Path, monkeypatch) -> None:
    import biointel.api.main as api_main

    monkeypatch.setattr(api_main, "ROOT", tmp_path)
    client = TestClient(app)
    response = client.post(
        "/documents/batch-extract",
        files=[
            ("files", ("activity.csv", sample_csv(), "text/csv")),
            (
                "files",
                (
                    "notes.txt",
                    b"EGFR is a kinase target. IC50 = 15 nM.",
                    "text/plain",
                ),
            ),
        ],
        data={"ocr_mode": "off"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["completed"] == 2
    run_id = payload["processed"][0]["run_id"]

    search = client.get("/documents/search", params={"q": "EGFR"})
    assert search.status_code == 200
    assert search.json()["results"]

    organize = client.post(
        f"/documents/history/{run_id}/organize",
        json={"tags": ["paper", "egfr"], "project_code": "P-27", "notes": "Reviewed"},
    )
    assert organize.status_code == 200
    assert organize.json()["run"]["project_code"] == "P-27"

    question = client.post("/documents/ask", json={"question": "What is the EGFR IC50?"})
    assert question.status_code == 200
    assert question.json()["citations"]


def test_optional_ocr_on_image_pdf() -> None:
    if not shutil.which("tesseract"):
        pytest.skip("Tesseract binary is not installed in this environment.")
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (1000, 300), "white")
    ImageDraw.Draw(image).text((40, 100), "EGFR IC50 25 nM", fill="black")
    stream = io.BytesIO()
    image.save(stream, format="PDF", resolution=150)
    extraction = extract_document("scan.pdf", stream.getvalue(), ocr_mode="force")
    assert extraction.page_count == 1
    assert any(region.kind == "ocr_word" for region in extraction.regions)


def test_step27_navigation_catalog() -> None:
    assert len(PAGE_CATALOG) >= 71
    keys = {page.key for page in PAGE_CATALOG}
    assert {
        "ocr_layout_review",
        "batch_document_processor",
        "document_knowledge_search",
        "document_evidence_bridge",
    } <= keys
