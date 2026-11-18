from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from biointel.jobs.local_queue import LocalJobQueue
from biointel.reference_assets.manager import AssetRecord
from biointel.step101.performance import PerformanceEvent, PerformanceRegistry, audit_ui_source
from biointel.step101.reference_lifecycle import ReferenceLifecycleManager, ReleaseRecord
from biointel.step101.reports import UnifiedScientificReportBuilder
from biointel.step101.ui_regression import run_ui_regression

ROOT = Path(__file__).resolve().parents[1]


def test_background_queue_pause_resume_checkpoint_and_recovery(tmp_path: Path):
    queue = LocalJobQueue(tmp_path / "jobs.sqlite3")
    job = queue.submit(
        "system_diagnostics",
        {},
        resources={"cpu_threads": 2, "ram_gb": 4},
        estimated_seconds=120,
    )
    assert job.resources == {"cpu_threads": 2, "ram_gb": 4}
    claimed = queue.claim_next(worker_id="worker-a")
    assert claimed and claimed.status == "running"
    queue.save_checkpoint(job.job_id, {"stage": "half"}, stage="execute")
    queue.request_pause(job.job_id)
    queue.mark_paused(job.job_id, checkpoint={"stage": "half"})
    assert queue.get(job.job_id).status == "paused"
    assert queue.get(job.job_id).checkpoint == {"stage": "half"}
    queue.resume(job.job_id)
    assert queue.get(job.job_id).status == "queued"

    claimed = queue.claim_next(worker_id="worker-a")
    assert claimed
    with sqlite3.connect(queue.path) as connection:
        connection.execute(
            "UPDATE local_jobs SET heartbeat_at_utc='2000-01-01T00:00:00+00:00', updated_at_utc='2000-01-01T00:00:00+00:00' WHERE job_id=?",
            (job.job_id,),
        )
    recovered = queue.recover_orphaned_jobs(stale_after_seconds=30)
    assert recovered["recovered"] == 1
    assert queue.get(job.job_id).status == "queued"


def test_reference_lifecycle_release_verify_snapshot_rollback(tmp_path: Path):
    manager = ReferenceLifecycleManager(tmp_path / "refs")
    source = tmp_path / "asset.fa"
    source.write_text(">x\nACGT\n", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manager.registry.upsert(
        AssetRecord(
            asset_id="genome",
            provider="Provider",
            version="1",
            status="verified",
            source_url="",
            local_path=str(source),
            expected_sha256=digest,
            observed_sha256=digest,
            size_bytes=source.stat().st_size,
            license_name="Test",
            license_accepted=True,
            installed_at_utc=datetime.now(timezone.utc).isoformat(),
        )
    )
    manager.register_release(
        ReleaseRecord(
            asset_id="genome",
            version="1",
            provider="Provider",
            sha256=digest,
            compatibility={"genome_build": "GRCh38"},
        )
    )
    assert manager.verify_installed("genome")["passed"] is True
    snapshot = manager.snapshot("genome")
    source.write_text("corrupt", encoding="utf-8")
    manager.rollback(snapshot["snapshot_id"])
    assert source.read_text(encoding="utf-8") == ">x\nACGT\n"
    assert manager.compatibility_check(
        "genome", {"asset_version": "1", "genome_build": "GRCh38"}
    )["compatible"] is True
    assert manager.storage_summary()["used_bytes"] > 0


def test_unified_report_builder_outputs_all_primary_formats():
    bundle = UnifiedScientificReportBuilder(ROOT).build(
        title="Step 101 Test Report",
        notes="Deterministic report test",
        reviewer="QA",
        sections=["provenance", "limitations"],
    )
    expected = {"report.html", "report.json", "report.pdf", "report.docx", "report.xlsx"}
    assert expected.issubset(bundle.files)
    assert all(bundle.files[name] for name in expected)
    assert len(bundle.manifest["files"]) >= 5
    archive = bundle.zip_bytes()
    assert archive.startswith(b"PK")


def test_ui_regression_static_and_performance_registry(tmp_path: Path):
    result = run_ui_regression(
        ROOT,
        mode="static",
        selected_pages=["111_Windows_UI_Regression_Performance_Center.py"],
        output_dir=tmp_path / "reports",
    )
    assert result["failed"] == 0
    assert result["passed"] == 1
    assert Path(result["artifacts"]["json"]).is_file()

    audit = audit_ui_source(ROOT)
    assert audit["page_count"] >= 112
    registry = PerformanceRegistry(tmp_path / "performance.sqlite3")
    registry.record(PerformanceEvent("ui", "render", 12.5, rows=10, cache_hit=True))
    summary = registry.summary()
    assert summary["event_count"] == 1
    assert registry.recent()[0]["component"] == "ui"
