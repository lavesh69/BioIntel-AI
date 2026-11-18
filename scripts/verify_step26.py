from __future__ import annotations

import argparse
import compileall
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel import __version__
from biointel.documents.exporters import export_all
from biointel.documents.extractor import extract_document
from biointel.documents.history import history_summary, initialize_document_history
from biointel.intelligence.data_intelligence import all_database_health
from biointel.training.model_artifact import load_model_artifact
from biointel.ui.navigation import PAGE_CATALOG
from biointel.utils.diagnostics import diagnostic_summary, run_diagnostics


def _sample_xlsx() -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Experiments"
    sheet.append(["sample_id", "compound", "score"])
    sheet.append(["S1", "Aspirin", 0.91])
    sheet.append(["S2", "Caffeine", 0.77])
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _sample_docx() -> bytes:
    from docx import Document

    document = Document()
    document.add_heading("Study Notes", level=1)
    document.add_paragraph("Document extraction verification record.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Target"
    table.cell(0, 1).text = "Value"
    table.cell(1, 0).text = "EGFR"
    table.cell(1, 1).text = "42"
    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()


def _sample_pdf() -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4)
    pdf.drawString(72, 780, "BioIntel AI Step 26 PDF extraction verification")
    pdf.drawString(72, 750, "Compound: Aspirin")
    pdf.save()
    return stream.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-only", action="store_true")
    args = parser.parse_args()

    assert __version__ == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert len(PAGE_CATALOG) >= 71
    assert compileall.compile_dir(SRC, quiet=1)

    samples = {
        "verification.xlsx": _sample_xlsx(),
        "verification.docx": _sample_docx(),
        "verification.pdf": _sample_pdf(),
    }
    extraction_checks = {}
    for filename, data in samples.items():
        extraction = extract_document(filename, data, max_rows_per_table=100)
        outputs = export_all(extraction)
        assert {"xlsx", "docx", "pdf", "json", "zip"} <= {
            Path(name).suffix.lstrip(".") for name in outputs
        }
        extraction_checks[filename] = extraction.summary()

    with tempfile.TemporaryDirectory() as temporary:
        temporary_history = Path(temporary) / "document_history.sqlite3"
        initialize_document_history(temporary_history)
        assert history_summary(temporary_history)["database"]["integrity"] == "ok"

    models = sorted((ROOT / "models").glob("*.joblib"))
    for model in models:
        load_model_artifact(model, trusted_root=ROOT / "models")

    databases = all_database_health(ROOT)
    assert databases["database_count"] >= 13
    assert databases["healthy_count"] == databases["database_count"]
    documents = history_summary(ROOT / "reports" / "document_history.sqlite3")
    assert documents["database"]["integrity"] == "ok"

    diagnostics = {"overall": "CORE_ONLY", "PASS": 0, "WARN": 1, "FAIL": 0, "total": 0}
    if not args.core_only:
        checks = run_diagnostics(ROOT)
        diagnostics = diagnostic_summary(checks)
        if diagnostics["FAIL"]:
            raise SystemExit(f"Diagnostics reported {diagnostics['FAIL']} failure(s).")

    payload = {
        "version": __version__,
        "page_catalog": len(PAGE_CATALOG),
        "models_loaded": len(models),
        "databases": databases,
        "document_history": documents,
        "extraction_checks": extraction_checks,
        "diagnostics": diagnostics,
    }
    output = ROOT / "reports" / "generated" / "step26_release_summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
