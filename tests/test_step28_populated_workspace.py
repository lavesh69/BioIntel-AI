from __future__ import annotations

from pathlib import Path

from biointel import __version__
from biointel.data.evidence_registry import registry_summary
from biointel.documents.history import history_summary
from biointel.dti.feature_cache import FeatureCache
from biointel.internet.download_registry import download_summary
from biointel.jobs.local_queue import LocalJobQueue
from biointel.ui.navigation import PAGE_CATALOG

ROOT = Path(__file__).resolve().parents[1]


def test_step28_version_and_navigation() -> None:
    assert __version__ == (ROOT / "VERSION").read_text().strip()
    assert len(PAGE_CATALOG) >= 71
    assert any(page.key == "demo_data_hub" for page in PAGE_CATALOG)
    assert (ROOT / "pages" / "55_Demo_Data_Hub.py").is_file()


def test_populated_document_workspace() -> None:
    summary = history_summary(ROOT / "reports" / "document_history.sqlite3")
    assert summary["total_runs"] >= 60
    assert summary["output_count"] >= 360
    assert summary["indexed_content_records"] >= 120
    assert summary["scientific_entities"] >= 500


def test_populated_evidence_downloads_jobs_and_cache() -> None:
    evidence = registry_summary(ROOT / "reports" / "evidence.sqlite3")["counts"]
    assert evidence["dataset_evidence_links"] >= 600
    assert evidence["evidence_reviews"] >= 400
    assert download_summary(ROOT / "reports" / "internet_downloads.sqlite3")["downloads"] >= 70
    jobs = LocalJobQueue(ROOT / "reports" / "jobs.sqlite3").list(limit=1000)
    assert len(jobs) >= 100
    cache = FeatureCache(ROOT / "reports" / "feature_cache.sqlite3").stats()
    assert cache.entries >= 120
    assert cache.total_hits >= 120


def test_starter_files_are_present() -> None:
    demo = ROOT / "data" / "examples" / "demo_workspace"
    required = {
        "BioIntel_Reference_Research_Report.pdf",
        "BioIntel_Assay_Review_Notes.docx",
        "BioIntel_Demo_Assay_Workbook.xlsx",
        "BioIntel_Demo_Activity_Data.csv",
        "demo_evidence_manifest.json",
        "demo_leakage_train.csv",
        "demo_leakage_test.csv",
    }
    assert required <= {path.name for path in demo.iterdir()}
