from __future__ import annotations

import argparse
import compileall
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel import __version__
from biointel.documents.history import (
    history_summary,
    list_entities,
    search_content,
    verify_output,
)
from biointel.documents.service import process_document, process_documents
from biointel.intelligence.data_intelligence import all_database_health
from biointel.training.model_artifact import load_model_artifact
from biointel.ui.navigation import PAGE_CATALOG
from biointel.utils.diagnostics import diagnostic_summary, run_diagnostics


def sample_csv() -> bytes:
    return (
        "canonical_smiles,protein_sequence,standard_value,standard_units,activity_type\n"
        "CCO,MKTIIALSYIFCLVFADYKDDDDK,10,nM,IC50\n"
    ).encode()


def sample_pptx() -> bytes:
    from pptx import Presentation
    from pptx.util import Inches

    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(1))
    box.text = "EGFR inhibition IC50 = 10 nM in Homo sapiens."
    stream = io.BytesIO()
    presentation.save(stream)
    return stream.getvalue()


def sample_scanned_pdf() -> bytes:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (1000, 300), "white")
    ImageDraw.Draw(image).text((40, 100), "EGFR IC50 25 nM", fill="black")
    stream = io.BytesIO()
    image.save(stream, format="PDF", resolution=150)
    return stream.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-only", action="store_true")
    args = parser.parse_args()

    assert __version__ == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert len(PAGE_CATALOG) >= 71
    assert compileall.compile_dir(SRC, quiet=1)

    with tempfile.TemporaryDirectory() as temporary:
        temp_root = Path(temporary)
        batch = process_documents(
            [("activity.csv", sample_csv()), ("study.pptx", sample_pptx())],
            project_root=temp_root,
        )
        assert batch.completed == 2 and batch.failed == 0
        history = temp_root / "reports" / "document_history.sqlite3"
        assert search_content(history, "EGFR")
        assert list_entities(history, entity_type="assay_endpoint")
        first = batch.processed[0]
        assert verify_output(history, first.outputs[0].output_id)["valid"] is True
        duplicate = process_document(
            "activity.csv",
            sample_csv(),
            project_root=temp_root,
            duplicate_policy="reuse",
        )
        assert duplicate.reused_from_run_id == first.run_id
        ocr_status = "not_requested"
        if shutil.which("tesseract"):
            ocr = process_document(
                "scan.pdf",
                sample_scanned_pdf(),
                project_root=temp_root,
                ocr_mode="force",
            )
            assert any(region.kind == "ocr_word" for region in ocr.extraction.regions)
            ocr_status = "passed"
        temporary_summary = history_summary(history)

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
        "temporary_document_verification": temporary_summary,
        "ocr_status": ocr_status,
        "diagnostics": diagnostics,
    }
    output = ROOT / "reports" / "generated" / "step27_release_summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
