from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np
import pandas as pd

from .native_integrity import parse_scientific_bool
from .native_workflows import _check, _column, _metric


def platform_demo(family: str, rng: np.random.Generator) -> pd.DataFrame | None:
    if family == "job-orchestration":
        return pd.DataFrame({
            "job_id": [f"J{i:03d}" for i in range(12)],
            "status": ["completed"] * 7 + ["running", "queued", "failed", "retrying", "cancelled"],
            "worker_heartbeat_age_seconds": [0] * 7 + [18, 0, 0, 30, 0],
            "retry_count": [0] * 9 + [2, 1, 0],
            "runtime_seconds": [12, 20, 18, 44, 31, 15, 28, 60, 0, 11, 17, 4],
            "checkpoint": [True] * 12,
            "artifact_count": [2, 1, 3, 2, 1, 2, 2, 0, 0, 0, 1, 0],
        })
    if family == "collaboration-review":
        return pd.DataFrame({"record_id": [f"R{i}" for i in range(8)], "version": ["1.0"] * 4 + ["1.1"] * 4, "reviewer": ["reviewer-a", "reviewer-b"] * 4, "decision": ["approved", "approved", "changes", "approved"] * 2, "conflict_resolved": [True, True, False, True] * 2, "timestamp": pd.date_range("2026-01-01", periods=8).astype(str)})
    if family == "workspace-lineage":
        return pd.DataFrame({"asset_id": [f"A{i}" for i in range(8)], "project_id": ["P1"] * 4 + ["P2"] * 4, "version": ["1.0"] * 8, "sha256": [hashlib.sha256(f"asset-{i}".encode()).hexdigest() for i in range(8)], "parent_asset_id": ["", "A0", "A1", "A2", "", "A4", "A5", "A6"], "locked": [True] * 8})
    if family == "data-lakehouse":
        return pd.DataFrame({"asset_id": [f"D{i}" for i in range(8)], "path": [f"data/study_{i}.parquet" for i in range(8)], "sha256": [hashlib.sha256(f"data-{i}".encode()).hexdigest() for i in range(8)], "schema_version": ["2"] * 8, "access_class": ["research"] * 6 + ["restricted"] * 2, "retention_days": [365] * 8, "indexed": [True] * 8})
    if family == "evidence-citation":
        return pd.DataFrame({"claim_id": [f"C{i}" for i in range(8)], "source_id": [f"PMID:{1000+i}" for i in range(8)], "evidence_strength": ["high", "moderate", "low", "high"] * 2, "exact_claim_support": [True, True, False, True] * 2, "retracted": [False] * 8, "conflict_flag": [False, False, True, False] * 2, "source_version": ["2026-01"] * 8})
    if family == "offline-copilot":
        return pd.DataFrame({"prompt_id": [f"Q{i}" for i in range(8)], "answer_id": [f"A{i}" for i in range(8)], "citation_count": [3, 2, 0, 4, 2, 1, 3, 2], "grounded": [True, True, False, True, True, True, True, True], "conflict_detected": [False, False, True, False, False, False, False, False], "clinical_action_blocked": [True] * 8, "corpus_version": ["local-2026-01"] * 8})
    if family == "plugin-security":
        return pd.DataFrame({"plugin": [f"plugin-{i}" for i in range(6)], "publisher": ["trusted"] * 6, "signature_valid": [True] * 6, "static_scan": ["pass"] * 6, "permission_count": [2, 3, 1, 4, 2, 5], "isolated_environment": [True] * 6, "enabled": [True] * 6})
    if family == "provenance-ledger":
        rows = []
        previous = "0" * 64
        for index in range(8):
            payload = json.dumps({"sequence": index, "event": f"event-{index}"}, sort_keys=True)
            event_hash = hashlib.sha256((previous + payload).encode()).hexdigest()
            rows.append({"sequence": index, "previous_hash": previous, "event_hash": event_hash, "payload": payload, "timestamp": f"2026-01-{index+1:02d}T00:00:00Z"})
            previous = event_hash
        return pd.DataFrame(rows)
    if family == "reference-lifecycle":
        return pd.DataFrame({"asset_id": [f"REF{i}" for i in range(6)], "version": ["2026.1"] * 6, "sha256": [hashlib.sha256(f"ref-{i}".encode()).hexdigest() for i in range(6)], "license_accepted": [True] * 6, "compatibility": ["pass"] * 6, "status": ["active"] * 5 + ["staged"], "rollback_ready": [True] * 6})
    if family == "store-release":
        return pd.DataFrame({"target": ["windows", "android", "ios", "docker"], "signed": [False, False, False, True], "package_hash_present": [True] * 4, "privacy_url_present": [False, False, False, True], "validation_status": ["review", "review", "review", "pass"], "version_aligned": [True] * 4})
    if family == "report-governance":
        return pd.DataFrame({"section": ["Methods", "Results", "Limitations", "References"], "source_traceable": [True] * 4, "method_complete": [True, True, True, True], "version_locked": [True] * 4, "reviewer": ["scientist-a"] * 4, "approved": [True, True, True, False]})
    if family == "file-inspection":
        return pd.DataFrame({"filename": ["sample.vcf.gz", "counts.csv", "image.ome.tiff", "report.pdf"], "extension_type": ["vcf.gz", "csv", "ome.tiff", "pdf"], "magic_type": ["gzip", "text", "tiff", "pdf"], "size_bytes": [1000, 2000, 3000, 4000], "schema_valid": [True] * 4, "corrupted": [False] * 4, "sensitive_data_flag": [True, True, False, True]})
    if family == "workflow-orchestration":
        return pd.DataFrame({"node": ["import", "qc", "analyse", "report"], "depends_on": ["", "import", "qc", "analyse"], "input_type": ["file", "table", "table", "result"], "output_type": ["table", "table", "result", "report"], "status": ["completed", "completed", "running", "queued"], "checkpoint": [True] * 4, "retry_limit": [1, 2, 2, 1]})
    if family == "document-intelligence":
        return pd.DataFrame({"document_id": ["D1"] * 4 + ["D2"] * 4, "page": [1, 2, 3, 4] * 2, "extraction_confidence": [0.98, 0.95, 0.91, 0.88, 0.99, 0.96, 0.92, 0.90], "reviewed": [True, True, True, False] * 2, "citation_traceable": [True] * 8, "table_or_figure": [False, True, False, True] * 2})
    return None


def _require(frame: pd.DataFrame, *candidates: str) -> str | None:
    return _column(frame, *candidates)


def _coverage(frame: pd.DataFrame, column: str | None) -> float:
    return float(frame[column].notna().mean()) if column and len(frame) else 0.0


def _jobs(frame, checks, metrics, metadata):
    status = _require(frame, "status", "state")
    heartbeat = _require(frame, "worker_heartbeat_age_seconds", "heartbeat_age_seconds")
    checkpoint = _require(frame, "checkpoint", "checkpoint_available")
    retry = _require(frame, "retry_count", "retries")
    out = frame.copy()
    if status:
        states = out[status].astype(str).str.lower()
        _metric(metrics, "failed_jobs", int(states.eq("failed").sum()), "jobs")
        _check(checks, "Job-state vocabulary", "pass" if states.isin({"queued", "running", "completed", "failed", "retrying", "cancelled"}).all() else "review", f"{states.nunique()} states")
    if heartbeat:
        age = pd.to_numeric(out[heartbeat], errors="coerce")
        out["stale_worker"] = age.gt(float(metadata.get("stale_after_seconds", 120)))
        _check(checks, "Worker heartbeat", "review" if out["stale_worker"].any() else "pass", f"{int(out['stale_worker'].sum())} stale workers")
    if checkpoint:
        coverage = out[checkpoint].map(parse_scientific_bool).mean()
        _check(checks, "Checkpoint coverage", "pass" if coverage >= 0.95 else "review", f"{coverage:.1%}")
    if retry:
        _metric(metrics, "maximum_retry_count", int(pd.to_numeric(out[retry], errors="coerce").max()), "retries")
    return {"job_reliability_audit": out}, ["Use durable worker heartbeats, process-tree cancellation and checkpointed retries for production workloads."]


def _collaboration(frame, checks, metrics, metadata):
    reviewer = _require(frame, "reviewer", "reviewer_id")
    decision = _require(frame, "decision", "status")
    version = _require(frame, "version", "record_version")
    conflict = _require(frame, "conflict_resolved", "resolved")
    rows = []
    for label, column in (("Reviewer identity", reviewer), ("Version-linked review", version), ("Decision record", decision)):
        coverage = _coverage(frame, column)
        rows.append({"requirement": label, "coverage": coverage})
        _check(checks, label, "pass" if coverage >= 0.95 else "review", f"coverage={coverage:.1%}")
    if conflict:
        unresolved = int((~frame[conflict].map(parse_scientific_bool)).sum())
        _check(checks, "Conflict resolution", "review" if unresolved else "pass", f"{unresolved} unresolved")
    return {"review_governance": pd.DataFrame(rows)}, ["Formal electronic signatures require organization-specific identity, retention and validation controls."]


def _workspace(frame, checks, metrics, metadata):
    asset = _require(frame, "asset_id", "artifact")
    sha = _require(frame, "sha256", "checksum")
    parent = _require(frame, "parent_asset_id", "parent")
    out = frame.copy()
    if sha:
        valid = out[sha].astype(str).str.fullmatch(r"[0-9a-fA-F]{64}", na=False)
        _check(checks, "Content identity", "pass" if valid.all() else "fail", f"{int((~valid).sum())} invalid hashes")
    if asset:
        _check(checks, "Unique asset identity", "pass" if not out[asset].duplicated().any() else "review", f"{int(out[asset].duplicated().sum())} duplicates")
    if parent and asset:
        known = set(out[asset].astype(str)) | {""}
        broken = ~out[parent].fillna("").astype(str).isin(known)
        _check(checks, "Lineage edges", "pass" if not broken.any() else "fail", f"{int(broken.sum())} broken parents")
    return {"workspace_lineage_audit": out}, ["Pin external engines and references in every snapshot for exact reruns."]


def _lakehouse(frame, checks, metrics, metadata):
    required = {"sha256": _require(frame, "sha256", "checksum"), "schema": _require(frame, "schema_version", "schema"), "access": _require(frame, "access_class", "access"), "retention": _require(frame, "retention_days", "retention")}
    audit = []
    for label, column in required.items():
        coverage = _coverage(frame, column)
        audit.append({"field": label, "coverage": coverage})
        _check(checks, f"{label.title()} metadata", "pass" if coverage >= 0.95 else "review", f"coverage={coverage:.1%}")
    return {"lakehouse_governance": pd.DataFrame(audit)}, ["Indexing and content hashes do not replace scientific QC or enterprise access controls."]


def _citation(frame, checks, metrics, metadata):
    exact = _require(frame, "exact_claim_support", "claim_supported")
    retracted = _require(frame, "retracted", "is_retracted")
    conflict = _require(frame, "conflict_flag", "conflict")
    out = frame.copy()
    if exact:
        bad = ~out[exact].map(parse_scientific_bool)
        _check(checks, "Exact claim support", "review" if bad.any() else "pass", f"{int(bad.sum())} unsupported claims")
    if retracted:
        flagged = out[retracted].map(parse_scientific_bool)
        _check(checks, "Retraction screen", "fail" if flagged.any() else "pass", f"{int(flagged.sum())} retracted sources")
    if conflict:
        flagged = out[conflict].map(parse_scientific_bool)
        _check(checks, "Evidence conflicts", "review" if flagged.any() else "pass", f"{int(flagged.sum())} conflicts")
    return {"claim_source_audit": out}, ["A citation must support the exact claim and should be reviewed for conflicts, corrections and retractions."]


def _copilot(frame, checks, metrics, metadata):
    grounded = _require(frame, "grounded", "citation_grounded")
    citations = _require(frame, "citation_count", "citations")
    blocked = _require(frame, "clinical_action_blocked", "action_blocked")
    out = frame.copy()
    if grounded:
        rate = out[grounded].map(parse_scientific_bool).mean()
        _check(checks, "Citation grounding", "pass" if rate >= 0.95 else "review", f"{rate:.1%}")
    if citations:
        zero = int(pd.to_numeric(out[citations], errors="coerce").fillna(0).le(0).sum())
        _check(checks, "Citation presence", "review" if zero else "pass", f"{zero} uncited answers")
    if blocked:
        rate = out[blocked].map(parse_scientific_bool).mean()
        _check(checks, "Clinical action blocking", "pass" if rate >= 0.95 else "fail", f"{rate:.1%}")
    return {"copilot_grounding_audit": out}, ["Local-model answers require source review; grounding does not guarantee correctness."]


def _plugin(frame, checks, metrics, metadata):
    signature = _require(frame, "signature_valid", "signed")
    publisher = _require(frame, "publisher", "publisher_trusted")
    isolated = _require(frame, "isolated_environment", "isolated")
    out = frame.copy()
    if signature:
        invalid = ~out[signature].map(parse_scientific_bool)
        _check(checks, "Plugin signature", "fail" if invalid.any() else "pass", f"{int(invalid.sum())} invalid signatures")
    if publisher:
        untrusted = ~out[publisher].astype(str).str.lower().isin({"trusted", "approved", "verified", "true", "1"})
        _check(checks, "Trusted publisher", "fail" if untrusted.any() else "pass", f"{int(untrusted.sum())} untrusted publishers")
    if isolated:
        rate = out[isolated].map(parse_scientific_bool).mean()
        _check(checks, "Environment isolation", "pass" if rate == 1 else "fail", f"{rate:.1%}")
    return {"plugin_supply_chain_audit": out}, ["Untrusted plugins must stay disabled and execute only in isolated, permission-bounded environments."]


def _ledger(frame, checks, metrics, metadata):
    sequence = _require(frame, "sequence", "event_sequence")
    previous = _require(frame, "previous_hash", "prev_hash")
    event_hash = _require(frame, "event_hash", "hash")
    payload = _require(frame, "payload", "payload_json")
    out = frame.copy().sort_values(sequence) if sequence else frame.copy()
    broken = 0
    if previous and event_hash and payload:
        prior = "0" * 64
        for _, row in out.iterrows():
            expected = hashlib.sha256((prior + str(row[payload])).encode()).hexdigest()
            if str(row[previous]) != prior or str(row[event_hash]) != expected:
                broken += 1
            prior = str(row[event_hash])
        _check(checks, "Hash-chain integrity", "pass" if broken == 0 else "fail", f"{broken} broken events")
    else:
        _check(checks, "Hash-chain integrity", "review", "Required ledger columns not supplied")
    return {"ledger_integrity_audit": out}, ["Local hash chaining is tamper-evident but is not independent timestamping or a regulated audit trail."]


def _reference(frame, checks, metrics, metadata):
    sha = _require(frame, "sha256", "observed_sha256")
    licence = _require(frame, "license_accepted", "licence_accepted")
    compatibility = _require(frame, "compatibility", "compatibility_status")
    out = frame.copy()
    if sha:
        valid = out[sha].astype(str).str.fullmatch(r"[0-9a-fA-F]{64}", na=False)
        _check(checks, "Reference checksums", "pass" if valid.all() else "fail", f"{int((~valid).sum())} invalid")
    if licence:
        accepted = out[licence].map(parse_scientific_bool)
        _check(checks, "Licence acceptance", "pass" if accepted.all() else "fail", f"{int((~accepted).sum())} not accepted")
    if compatibility:
        compatible = out[compatibility].astype(str).str.lower().isin({"pass", "compatible", "verified"})
        _check(checks, "Compatibility validation", "pass" if compatible.all() else "review", f"{int((~compatible).sum())} unresolved")
    return {"reference_release_audit": out}, ["Activate only checksum-verified, licensed and build-compatible reference releases; retain rollback evidence."]


def _store(frame, checks, metrics, metadata):
    signed = _require(frame, "signed", "signature_valid")
    privacy = _require(frame, "privacy_url_present", "privacy_url")
    aligned = _require(frame, "version_aligned", "version_match")
    out = frame.copy()
    for label, column in (("Package signing", signed), ("Privacy URL", privacy), ("Version alignment", aligned)):
        if column:
            rate = out[column].map(parse_scientific_bool).mean()
            _check(checks, label, "pass" if rate == 1 else "review", f"{rate:.1%}")
    return {"store_target_readiness": out}, ["Store approval, publisher identity and reputation are external outcomes and cannot be created by repository tests."]


def _report(frame, checks, metrics, metadata):
    source = _require(frame, "source_traceable", "citation_traceable")
    method = _require(frame, "method_complete", "methods_complete")
    locked = _require(frame, "version_locked", "locked")
    approved = _require(frame, "approved", "reviewed")
    out = frame.copy()
    for label, column, fail_closed in (("Source traceability", source, True), ("Method completeness", method, False), ("Version locking", locked, True), ("Reviewer approval", approved, False)):
        rate = out[column].map(parse_scientific_bool).mean() if column else 0.0
        state = "pass" if rate == 1 else ("fail" if fail_closed and rate < 0.8 else "review")
        _check(checks, label, state, f"{rate:.1%}")
    return {"report_completeness_audit": out}, ["Release reports only after claim-source, methods, version and reviewer checks are complete."]


def _file(frame, checks, metrics, metadata):
    extension = _require(frame, "extension_type", "extension")
    magic = _require(frame, "magic_type", "detected_type")
    corrupt = _require(frame, "corrupted", "is_corrupt")
    schema = _require(frame, "schema_valid", "valid_schema")
    out = frame.copy()
    if corrupt:
        bad = out[corrupt].map(parse_scientific_bool)
        _check(checks, "Corruption screen", "fail" if bad.any() else "pass", f"{int(bad.sum())} corrupt files")
    if schema:
        good = out[schema].map(parse_scientific_bool)
        _check(checks, "Schema validation", "pass" if good.all() else "review", f"{int((~good).sum())} invalid schemas")
    if extension and magic:
        mismatches = out[extension].astype(str).str.lower().str.split(".").str[-1] != out[magic].astype(str).str.lower().str.split("/").str[-1]
        _check(checks, "Extension/magic consistency", "review" if mismatches.any() else "pass", f"{int(mismatches.sum())} mismatches")
    return {"file_safety_audit": out}, ["Use bounded previews, decompression limits, path traversal protection and sensitive-data warnings before analysis."]


def _workflow(frame, checks, metrics, metadata):
    node = _require(frame, "node", "node_id")
    dependency = _require(frame, "depends_on", "dependencies")
    checkpoint = _require(frame, "checkpoint", "checkpointable")
    out = frame.copy()
    if node:
        duplicate = out[node].astype(str).duplicated()
        _check(checks, "Unique nodes", "fail" if duplicate.any() else "pass", f"{int(duplicate.sum())} duplicates")
    if node and dependency:
        known = set(out[node].astype(str)) | {""}
        broken = ~out[dependency].fillna("").astype(str).isin(known)
        _check(checks, "Dependency integrity", "fail" if broken.any() else "pass", f"{int(broken.sum())} broken dependencies")
    if checkpoint:
        rate = out[checkpoint].map(parse_scientific_bool).mean()
        _check(checks, "Checkpointability", "pass" if rate >= 0.95 else "review", f"{rate:.1%}")
    return {"workflow_dag_audit": out}, ["A valid DAG still requires scientifically qualified nodes, pinned tools and compatible data contracts."]


def _document(frame, checks, metrics, metadata):
    confidence = _require(frame, "extraction_confidence", "ocr_confidence")
    reviewed = _require(frame, "reviewed", "human_reviewed")
    citation = _require(frame, "citation_traceable", "source_traceable")
    out = frame.copy()
    if confidence:
        values = pd.to_numeric(out[confidence], errors="coerce")
        _check(checks, "Extraction confidence", "pass" if values.ge(0.90).mean() >= 0.95 else "review", f"median={values.median():.3f}")
    if reviewed:
        rate = out[reviewed].map(parse_scientific_bool).mean()
        _check(checks, "Human review", "pass" if rate == 1 else "review", f"{rate:.1%}")
    if citation:
        rate = out[citation].map(parse_scientific_bool).mean()
        _check(checks, "Page/source traceability", "pass" if rate == 1 else "fail", f"{rate:.1%}")
    return {"document_extraction_audit": out}, ["Review tables, figures and low-confidence OCR against the original source page before scientific use."]


PLATFORM_HANDLERS = {
    "job-orchestration": _jobs,
    "collaboration-review": _collaboration,
    "workspace-lineage": _workspace,
    "data-lakehouse": _lakehouse,
    "evidence-citation": _citation,
    "offline-copilot": _copilot,
    "plugin-security": _plugin,
    "provenance-ledger": _ledger,
    "reference-lifecycle": _reference,
    "store-release": _store,
    "report-governance": _report,
    "file-inspection": _file,
    "workflow-orchestration": _workflow,
    "document-intelligence": _document,
}
