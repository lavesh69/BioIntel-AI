from __future__ import annotations

# ruff: noqa: E402
import gzip
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel import __version__
from biointel.api.security_store import ApiSecurityStore
from biointel.database.integrity_guards import install_integrity_guards
from biointel.genomics.fastq import (
    decode_fastq_bytes,
    paired_end_qc,
    parse_fastq,
    trim_paired_fastq,
)
from biointel.genomics.variants import (
    decode_vcf_bytes,
    genotype_matrix,
    parse_vcf,
    sample_summary,
    variant_summary,
)
from biointel.integrations.http_client import HttpResponse
from biointel.integrations.public_sync import (
    sync_chembl_activities,
    sync_status,
    sync_uniprot_reviewed,
)
from biointel.jobs.local_queue import LocalJobQueue


def test_step33_version_and_ui_consistency() -> None:
    assert __version__ == (ROOT / "VERSION").read_text().strip()
    pages = [ROOT / "app.py", *sorted((ROOT / "pages").glob("*.py"))]
    assert len(pages) >= 71
    assert all("st.json(" not in page.read_text(encoding="utf-8") for page in pages)
    assert all("st.title(" not in page.read_text(encoding="utf-8") for page in pages)
    def _uses_shared_page_shell(page):
        source = page.read_text(encoding="utf-8")
        return any(
            token in source
            for token in ("hero(", "compact_module_header(", "render_expansion_module(", "render_nextgen_module(")
        )

    assert all(_uses_shared_page_shell(page) for page in pages)


def test_gzip_paired_fastq_and_synchronized_trim() -> None:
    left_text = "@pair/1\nACGTACGT\n+\nIIIIIIII\n"
    right_text = "@pair/2\nTGCATGCA\n+\nIIIIIIII\n"
    decoded = decode_fastq_bytes(gzip.compress(left_text.encode()), filename="reads.fastq.gz")
    left = parse_fastq(decoded)
    right = parse_fastq(right_text)
    qc = paired_end_qc(left, right)
    assert qc.synchronized_pairs == 1
    out_left, out_right, summary = trim_paired_fastq(
        left, right, minimum_quality=20, minimum_length=4
    )
    assert len(out_left) == len(out_right) == 1
    assert summary["retained_pairs"] == 1


def test_vcf_gzip_info_and_genotypes() -> None:
    text = (
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\n"
        "1\t10\t.\tA\tG\t50\tPASS\tDP=20;AF=0.1\tGT:DP\t0/1:20\n"
    )
    frame = parse_vcf(decode_vcf_bytes(gzip.compress(text.encode()), filename="test.vcf.gz"))
    result = variant_summary(frame)
    assert result.mean_depth == 20.0 and result.samples == 1
    assert genotype_matrix(frame).iloc[0]["S1"] == "0/1"
    assert sample_summary(frame).iloc[0]["call_rate_percent"] == 100.0


def test_security_store_roles_rate_and_audit(tmp_path: Path) -> None:
    store = ApiSecurityStore(tmp_path / "security.sqlite3")
    store.register_client(
        client_id="viewer",
        display_name="Viewer",
        role="viewer",
        raw_key="secret",
        quota_per_minute=2,
    )
    identity = store.authenticate("secret")
    assert identity is not None and identity.role == "viewer"
    assert store.authenticate("wrong") is None
    assert store.allow_request("viewer", 2, now_epoch=120)[0]
    assert store.allow_request("viewer", 2, now_epoch=120)[0]
    assert not store.allow_request("viewer", 2, now_epoch=120)[0]
    store.log_request(
        {
            "request_id": "req-1",
            "client_id": "viewer",
            "role": "viewer",
            "method": "GET",
            "path": "/health",
            "query_string": "",
            "status_code": 200,
            "duration_ms": 1.2,
            "request_bytes": 0,
            "response_bytes": 0,
            "client_host": "127.0.0.1",
            "user_agent": "pytest",
            "error_code": "",
            "occurred_at_utc": "2026-07-05T00:00:00+00:00",
        }
    )
    assert store.status()["request_log_count"] == 1


def test_job_dependencies_stages_events_and_artifacts(tmp_path: Path) -> None:
    queue = LocalJobQueue(tmp_path / "jobs.sqlite3")
    parent = queue.submit("prepare", {"x": 1}, stages=["prepare", "validate"])
    child = queue.submit("analyse", {"x": 2}, dependencies=[parent.job_id])
    assert child.status == "blocked"
    claimed = queue.claim_next(worker_id="worker-1")
    assert claimed is not None and claimed.job_id == parent.job_id
    queue.update_progress(parent.job_id, progress_percent=50, stage="prepare", message="half")
    queue.complete(parent.job_id, {"ok": True})
    next_job = queue.claim_next(worker_id="worker-1")
    assert next_job is not None and next_job.job_id == child.job_id
    timeline = queue.timeline(parent.job_id)
    assert timeline["events"] and timeline["stages"]


def test_integrity_guards_block_orphan_dataset_child(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    database = reports / "datasets.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE datasets(dataset_sha256 TEXT PRIMARY KEY);
            CREATE TABLE dataset_files(dataset_sha256 TEXT NOT NULL, relative_path TEXT);
            """
        )
    results = install_integrity_guards(tmp_path)
    assert results["datasets.sqlite3"].trigger_count >= 1
    with sqlite3.connect(database) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO dataset_files(dataset_sha256,relative_path) VALUES('missing','x.csv')"
            )


def test_official_sync_with_fake_transport(tmp_path: Path) -> None:
    def transport(url: str, timeout: float, headers: dict[str, str]) -> HttpResponse:
        if "chembl" in url:
            body = json.dumps(
                {
                    "activities": [
                        {
                            "activity_id": 1,
                            "molecule_chembl_id": "CHEMBL1",
                            "target_chembl_id": "CHEMBL_T1",
                            "assay_chembl_id": "CHEMBL_A1",
                            "document_chembl_id": "CHEMBL_D1",
                            "standard_type": "IC50",
                            "standard_relation": "=",
                            "standard_value": "100",
                            "standard_units": "nM",
                            "pchembl_value": "7",
                            "target_organism": "Homo sapiens",
                            "assay_type": "B",
                            "data_validity_comment": None,
                        }
                    ],
                    "page_meta": {"next": None},
                }
            ).encode()
            return HttpResponse(200, body, "application/json")
        body = (
            "Entry\tEntry Name\tProtein names\tGene Names\tOrganism\tLength\tReviewed\n"
            "P04637\tP53_HUMAN\tCellular tumor antigen p53\tTP53\tHomo sapiens\t393\treviewed\n"
        ).encode()
        return HttpResponse(200, body, "text/tab-separated-values")

    chembl = sync_chembl_activities(tmp_path, maximum_records=1, transport=transport)
    uniprot = sync_uniprot_reviewed(tmp_path, maximum_records=1, transport=transport)
    assert chembl.records == 1 and uniprot.records == 1
    status = sync_status(tmp_path)
    assert status["normalized_records"] == 2
