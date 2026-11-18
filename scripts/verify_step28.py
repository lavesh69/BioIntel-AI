from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel import __version__
from biointel.data.evidence_registry import registry_summary
from biointel.documents.history import history_summary
from biointel.internet.download_registry import download_summary
from biointel.jobs.local_queue import LocalJobQueue
from biointel.ui.navigation import PAGE_CATALOG


def main() -> None:
    assert __version__ == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert len(PAGE_CATALOG) >= 71
    assert (ROOT / "pages" / "55_Demo_Data_Hub.py").is_file()
    assert (ROOT / "LOAD_DEMO_WORKSPACE_WINDOWS.bat").is_file()
    documents = history_summary(ROOT / "reports" / "document_history.sqlite3")
    evidence = registry_summary(ROOT / "reports" / "evidence.sqlite3")
    downloads = download_summary(ROOT / "reports" / "internet_downloads.sqlite3")
    jobs = LocalJobQueue(ROOT / "reports" / "jobs.sqlite3").list(limit=1000)
    assert documents["total_runs"] >= 60
    assert documents["output_count"] >= 360
    assert documents["scientific_entities"] >= 500
    assert evidence["counts"]["dataset_evidence_links"] >= 600
    assert evidence["counts"]["evidence_reviews"] >= 400
    assert downloads["downloads"] >= 70
    assert len(jobs) >= 100
    demo_files = [
        path
        for path in (ROOT / "data" / "examples" / "demo_workspace").rglob("*")
        if path.is_file()
    ]
    assert len(demo_files) >= 60
    with sqlite3.connect(ROOT / "reports" / "document_history.sqlite3") as connection:
        assert (
            int(connection.execute("SELECT COUNT(*) FROM document_ocr_corrections").fetchone()[0])
            >= 25
        )
    with sqlite3.connect(ROOT / "reports" / "projects.sqlite3") as connection:
        assert int(connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]) >= 30
        assert (
            int(connection.execute("SELECT COUNT(*) FROM project_milestones").fetchone()[0]) >= 100
        )
    with sqlite3.connect(ROOT / "reports" / "datasets.sqlite3") as connection:
        assert int(connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]) >= 30
    payload = {
        "version": __version__,
        "screens": len(PAGE_CATALOG),
        "documents": documents,
        "evidence": evidence,
        "downloads": downloads,
        "jobs": len(jobs),
        "demo_files": len(demo_files),
    }
    output = ROOT / "reports" / "generated" / "step28_verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
