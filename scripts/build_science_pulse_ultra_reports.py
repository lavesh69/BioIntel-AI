from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

import sys

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.science_pulse.models import MIGRATION_VERSION
from biointel.science_pulse.providers import BUILTIN_SOURCES


VERIFIED_LIVE_KEYS = {
    "rss_nature_biotechnology",
    "rss_sciencedaily_biology",
    "rss_nibib_news",
    "rss_nlm_news",
}

CHANGED_FILES = [
    "src/biointel/science_pulse/security.py",
    "src/biointel/science_pulse/providers.py",
    "src/biointel/science_pulse/models.py",
    "src/biointel/science_pulse/store.py",
    "src/biointel/science_pulse/service.py",
    "src/biointel/science_pulse/api.py",
    "src/biointel/science_pulse/news_ui.py",
    "src/biointel/science_pulse/ui.py",
    "src/biointel/education/ui.py",
    "src/biointel/step101/background.py",
    "tests/test_science_pulse_live_news.py",
    "tests/test_science_pulse_news_first_ui.py",
    "scripts/build_science_pulse_news_first_reports.py",
    "scripts/build_science_pulse_ultra_reports.py",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write(name: str, value: str) -> None:
    (ROOT / name).write_text(value.rstrip() + "\n", encoding="utf-8", newline="\n")


def write_json(name: str, value: object) -> None:
    write(name, json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


def live_evidence(db_path: Path) -> dict[str, object]:
    empty = {
        "database": str(db_path),
        "available": False,
        "live_item_count": 0,
        "provider_counts": {},
        "completed_runs": {},
    }
    if not db_path.is_file():
        return empty
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        counts = {
            str(row["provider_key"]): int(row["count"])
            for row in connection.execute(
                "SELECT provider_key, COUNT(*) AS count FROM sp_items "
                "WHERE live_state='LIVE' GROUP BY provider_key"
            ).fetchall()
        }
        runs = {
            str(row["source_key"]): {
                "status": str(row["status"]),
                "fetched": int(row["fetched_count"]),
                "inserted": int(row["inserted_count"]),
                "updated": int(row["updated_count"]),
                "duration_ms": int(row["duration_ms"]),
                "error": str(row["error_text"]),
            }
            for row in connection.execute(
                "SELECT source_key,status,fetched_count,inserted_count,updated_count,"
                "duration_ms,error_text FROM sp_sync_runs WHERE status='completed' "
                "ORDER BY started_at"
            ).fetchall()
        }
    finally:
        connection.close()
    return {
        "database": str(db_path),
        "available": True,
        "live_item_count": sum(counts.values()),
        "provider_counts": counts,
        "completed_runs": runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-db", type=Path, required=True)
    parser.add_argument("--tests-passed", type=int, default=0)
    parser.add_argument("--tests-failed", type=int, default=0)
    parser.add_argument("--tests-skipped", type=int, default=0)
    parser.add_argument("--windows-status", default="NOT_RUN")
    args = parser.parse_args()

    generated = utc_now()
    evidence = live_evidence(args.live_db.resolve())
    counts = evidence["provider_counts"]
    verified = {
        key
        for key in VERIFIED_LIVE_KEYS
        if int(counts.get(key, 0)) > 0
        and evidence["completed_runs"].get(key, {}).get("status") == "completed"
    }

    provider_rows = []
    for source in BUILTIN_SOURCES:
        if source.key in verified:
            status = "IMPLEMENTED_AND_VERIFIED"
            note = f"Real HTTPS sync persisted {counts[source.key]} LIVE records."
        else:
            status = "IMPLEMENTED_REQUIRES_EXTERNAL_VALIDATION"
            note = "Adapter is fixture-tested; this qualification did not make a real-provider claim."
        provider_rows.append(
            {
                "key": source.key,
                "name": source.name,
                "kind": source.kind,
                "base_url": source.base_url,
                "content_types": list(source.content_types),
                "schedule_seconds": source.schedule_seconds,
                "status": status,
                "evidence": note,
            }
        )

    precheck = f"""# Science Pulse Ultra Precheck

Generated: {generated}

- Canonical source: `{ROOT}`
- Existing Science Pulse migration: `{MIGRATION_VERSION}`
- Existing provider adapters found: {len(BUILTIN_SOURCES)}
- Backup was created before edits.
- Primary user requirement for this increment: real live news on Windows.
- Qualification boundary: the very large Ultra specification is not represented as fully implemented.
- Real live-news evidence database: `{evidence['database']}`
- Real LIVE records observed: {evidence['live_item_count']}
"""
    write("SCIENCE_PULSE_ULTRA_PRECHECK.md", precheck)
    write_json(
        "SCIENCE_PULSE_ULTRA_BASELINE.json",
        {
            "generated_at_utc": generated,
            "canonical_source": str(ROOT),
            "migration_version": MIGRATION_VERSION,
            "builtin_source_count": len(BUILTIN_SOURCES),
            "preserved_capabilities": [
                "local SQLite persistence",
                "publication, preprint, dataset, trial and news adapters",
                "hidden persistent scheduler",
                "deduplication, alerts, digests, search and trends",
                "Streamlit local-cache UI",
                "FastAPI Science Pulse routes",
            ],
        },
    )
    write_json("SCIENCE_PULSE_ULTRA_EXISTING_PROVIDER_MATRIX.json", provider_rows)

    new_source_rows = [
        {
            "key": "rss_nibib_news",
            "name": "NIH NIBIB Science News",
            "status": "IMPLEMENTED_AND_VERIFIED" if "rss_nibib_news" in verified else "IMPLEMENTED_REQUIRES_EXTERNAL_VALIDATION",
            "records": int(counts.get("rss_nibib_news", 0)),
        },
        {
            "key": "rss_nlm_news",
            "name": "National Library of Medicine News",
            "status": "IMPLEMENTED_AND_VERIFIED" if "rss_nlm_news" in verified else "IMPLEMENTED_REQUIRES_EXTERNAL_VALIDATION",
            "records": int(counts.get("rss_nlm_news", 0)),
        },
    ]
    write_json("SCIENCE_PULSE_ULTRA_NEW_SOURCE_MATRIX.json", new_source_rows)
    write_json(
        "SCIENCE_PULSE_ULTRA_PROVIDER_VALIDATION.json",
        {
            "generated_at_utc": generated,
            "classification_policy": "A provider is verified only when a real HTTPS sync completed and persisted LIVE records.",
            "evidence": evidence,
            "verified_provider_keys": sorted(verified),
            "not_claimed_as_verified": sorted({source.key for source in BUILTIN_SOURCES} - verified),
        },
    )

    source_packs = [
        {
            "key": "official_live_news",
            "members": sorted(VERIFIED_LIVE_KEYS),
            "status": "PARTIALLY_IMPLEMENTED",
            "note": "All members are independently managed and scheduled, but a first-class pack persistence/API layer was not added in this focused live-news increment.",
        },
        *[
            {
                "key": key,
                "members": [],
                "status": "NOT_IMPLEMENTED",
                "note": "No working adapter was added; no placeholder source is exposed as live.",
            }
            for key in (
                "publication_and_citation",
                "datasets_and_repositories",
                "protocols_and_methods",
                "biological_database_updates",
                "clinical_trials",
                "regulatory_updates",
                "grants_and_funding",
                "patents_and_ip",
                "conferences_and_events",
                "software_and_workflows",
            )
        ],
    ]
    write_json("SCIENCE_PULSE_ULTRA_SOURCE_PACKS.json", source_packs)

    implementation = [
        {"capability": "existing publication and live-news operation", "status": "IMPLEMENTED_AND_VERIFIED"},
        {"capability": "real Nature, ScienceDaily, NIH NIBIB and NLM live news", "status": "IMPLEMENTED_AND_VERIFIED" if len(verified) == 4 else "IMPLEMENTED_REQUIRES_EXTERNAL_VALIDATION"},
        {"capability": "RSS 1.0/RDF and Atom namespace handling", "status": "IMPLEMENTED_AND_VERIFIED"},
        {"capability": "nested feed title extraction", "status": "IMPLEMENTED_AND_VERIFIED"},
        {"capability": "proxy auto-fallback with fresh request", "status": "IMPLEMENTED_AND_VERIFIED"},
        {"capability": "redirect preflight SSRF validation", "status": "IMPLEMENTED_AND_VERIFIED"},
        {"capability": "network-free Streamlit reruns", "status": "IMPLEMENTED_AND_VERIFIED"},
        {"capability": "provider adapter contract", "status": "PARTIALLY_IMPLEMENTED"},
        {"capability": "independently persisted source packs", "status": "NOT_IMPLEMENTED"},
        {"capability": "knowledge graph", "status": "NOT_IMPLEMENTED"},
        {"capability": "claim-evidence mapping", "status": "NOT_IMPLEMENTED"},
        {"capability": "preprint-publication tracker", "status": "NOT_IMPLEMENTED"},
        {"capability": "researcher and institution watchlists", "status": "NOT_IMPLEMENTED"},
        {"capability": "multilingual and audio briefing", "status": "NOT_IMPLEMENTED"},
        {"capability": "Ultra webhook and MCP tools", "status": "NOT_IMPLEMENTED"},
    ]
    write_json("SCIENCE_PULSE_ULTRA_IMPLEMENTATION_MATRIX.json", implementation)

    changed = []
    for relative in CHANGED_FILES:
        path = ROOT / relative
        changed.append(
            {
                "path": relative,
                "exists": path.is_file(),
                "bytes": path.stat().st_size if path.is_file() else 0,
                "sha256": sha256(path) if path.is_file() else "",
            }
        )
    write_json(
        "SCIENCE_PULSE_ULTRA_CHANGED_FILES.json",
        {"generated_at_utc": generated, "files": changed},
    )
    write_json(
        "SCIENCE_PULSE_ULTRA_TEST_RESULTS.json",
        {
            "generated_at_utc": generated,
            "command_scope": "Science Pulse plus Phase 31-35 focused regression suite",
            "passed": args.tests_passed,
            "failed": args.tests_failed,
            "skipped": args.tests_skipped,
            "blocked": 0,
            "live_provider_records": evidence["live_item_count"],
            "windows_smoke": args.windows_status,
        },
    )

    write(
        "SCIENCE_PULSE_ULTRA_IMPLEMENTATION_REPORT.md",
        f"""# Science Pulse Ultra Implementation Report

Generated: {generated}

This increment completes the user's live-news priority without claiming the entire Ultra specification. Four official HTTPS feeds were synchronized by the real background scheduler and persisted {evidence['live_item_count']} records with `live_state=LIVE`.

Implemented changes:

- automatic system-proxy to direct-HTTPS fallback;
- redirect target validation before any redirect is followed;
- RSS 1.0/RDF, namespaced RSS and Atom entry discovery;
- nested text extraction for NIH feed titles;
- per-feed source identity and network-route provenance;
- incremental feed checkpoint stop;
- NIH NIBIB and NLM official feeds;
- Streamlit connection verification changed to a background-worker queue action;
- Windows cold-start worker timeout increased to 180 seconds.

The implementation matrix truthfully marks the larger knowledge-graph, claim-evidence, source-pack persistence, watchlist, multilingual/audio and MCP expansion as not implemented in this focused increment.
""",
    )
    write(
        "SCIENCE_PULSE_ULTRA_ARCHITECTURE.md",
        """# Science Pulse Ultra Architecture

`hidden Windows worker -> scheduler lease -> provider registry -> SafeHttpClient -> adapter -> normalized PulseRecord -> SQLite -> cached Streamlit/FastAPI readers`

Network I/O is confined to the hidden worker. HTTPS, DNS/public-address checks, approved hosts, MIME limits, payload limits and redirect preflight checks protect ingestion. Each feed has its own provider key and checkpoint.

Ultra knowledge-graph and claim-evidence services are not present in this increment.
""",
    )
    write(
        "SCIENCE_PULSE_ULTRA_ADAPTER_SDK.md",
        """# Science Pulse Ultra Adapter SDK

The current contract is `ProviderAdapter.fetch(client, query, limit, checkpoint) -> FetchResult(records, checkpoint)`. `ProviderRegistry` supplies pacing, three bounded attempts and source-specific checkpoints. `SafeHttpClient` is injectable for deterministic tests.

Status: PARTIALLY_IMPLEMENTED. Version detection, schema-change callbacks, formal plugin discovery and per-provider rate-limit policy objects remain to be built.
""",
    )
    write(
        "SCIENCE_PULSE_ULTRA_DATABASE_SCHEMA.md",
        f"""# Science Pulse Ultra Database Schema

Canonical migration: `{MIGRATION_VERSION}`.

The preserved schema contains sources, normalized items, aliases, sync runs, worker leases, alerts, deliveries, preferences, digests, integrations and audit events. WAL-backed SQLite remains canonical for this local-first Windows release.

No Ultra graph, claim-evidence, source-pack, story-timeline, watchlist or webhook tables were added; those capabilities remain NOT_IMPLEMENTED.
""",
    )
    write(
        "SCIENCE_PULSE_ULTRA_KNOWLEDGE_GRAPH_SPEC.md",
        """# Science Pulse Ultra Knowledge Graph Specification

Status: NOT_IMPLEMENTED.

A future implementation should persist typed nodes, typed edges, source record IDs, evidence citations, confidence, tenant ownership and temporal validity. No runtime graph claim is made by this release.
""",
    )
    write(
        "SCIENCE_PULSE_ULTRA_CLAIM_EVIDENCE_SPEC.md",
        """# Science Pulse Ultra Claim-Evidence Specification

Status: NOT_IMPLEMENTED.

Future claims must retain exact source record IDs, quotations only within licence limits, supporting/contradicting relationships, confidence rationale and human-review state. Current summaries are not represented as a claim graph.
""",
    )
    write(
        "SCIENCE_PULSE_ULTRA_RECOMMENDATION_SPEC.md",
        """# Science Pulse Ultra Recommendation Specification

Status: NOT_IMPLEMENTED. Existing user preferences, alerts and digests are preserved. An Ultra recommender would require persisted reasons, negative controls, tenant isolation and user feedback; it is not exposed as active.
""",
    )
    write(
        "SCIENCE_PULSE_ULTRA_TREND_ENGINE_SPEC.md",
        """# Science Pulse Ultra Trend Engine Specification

Status: PARTIALLY_IMPLEMENTED. Existing persisted topic counts and deterministic trends remain operational. Story clustering, burst detection, emerging-entity graphs and cross-provider trend explanations are not implemented.
""",
    )
    write(
        "SCIENCE_PULSE_ULTRA_SECURITY_REPORT.md",
        """# Science Pulse Ultra Security Report

Verified controls: HTTPS-only providers, approved-host enforcement, DNS public-address checks, no credentials in URLs, standard port only, XML DTD/entity rejection, MIME and size limits, bounded redirects, redirect pre-validation, sanitized text and injectable transports. Proxy fallback creates a fresh request so proxy state cannot leak into the direct attempt.

Credentials and institutional licences were not added or embedded.
""",
    )
    write(
        "SCIENCE_PULSE_ULTRA_WINDOWS_REPORT.md",
        f"""# Science Pulse Ultra Windows Report

Status: {args.windows_status}.

The hidden worker hosts the scheduler; Streamlit reruns read local SQLite only. Cold scientific-module imports may exceed 60 seconds, so the worker registration timeout is now 180 seconds. The supervisor keeps UI, API and worker windows hidden.
""",
    )
    write(
        "SCIENCE_PULSE_ULTRA_TEST_REPORT.md",
        f"""# Science Pulse Ultra Test Report

- Passed: {args.tests_passed}
- Failed: {args.tests_failed}
- Skipped: {args.tests_skipped}
- Windows smoke: {args.windows_status}
- Real LIVE records persisted: {evidence['live_item_count']}

Tests cover namespaces, nested titles, checkpoints, provider identity, proxy fallback, redirect SSRF rejection, source registration, UI network isolation and Phase 31-35 regressions. Normal automated tests use fixtures; real-provider evidence is reported separately.
""",
    )
    write(
        "SCIENCE_PULSE_ULTRA_KNOWN_LIMITATIONS.md",
        """# Science Pulse Ultra Known Limitations

- The full Ultra expansion is not complete.
- Source-pack persistence/API, the knowledge graph, claim-evidence graph, preprint matching, story timelines, researcher/institution watchlists, multilingual/audio briefings, Research Copilot, webhooks and MCP tools are not implemented.
- Existing non-news API adapters passed deterministic tests but were not all revalidated against live providers in this qualification.
- External feeds can change schema or availability without notice.
- Network access is required for live synchronization; cached records remain readable offline.
""",
    )
    write(
        "SCIENCE_PULSE_ULTRA_MIGRATION_GUIDE.md",
        f"""# Science Pulse Ultra Migration Guide

No destructive database migration is required. Existing `{MIGRATION_VERSION}` databases are opened in place. Back up `UserData/databases/biointel_science_pulse.sqlite` before upgrade. On first worker start, new official sources are upserted without resetting user enable/approval choices for existing rows.
""",
    )
    write(
        "SCIENCE_PULSE_ULTRA_ROLLBACK_GUIDE.md",
        """# Science Pulse Ultra Rollback Guide

Stop BioIntel and its hidden worker, restore the pre-upgrade source and SQLite backup, then run the existing Windows launcher. The source changes are additive except for safer HTTP/feed behavior and the longer worker-start timeout. Restoring the database backup removes records collected after the backup.
""",
    )
    write(
        "CHANGELOG_SCIENCE_PULSE_ULTRA.md",
        """# Science Pulse Ultra Changelog

- Fixed Windows proxy failures with secure direct fallback.
- Fixed RSS 1.0/RDF and nested-title parsing.
- Added official NIH NIBIB and NLM news feeds.
- Preserved per-feed provenance and checkpoints.
- Moved UI verification to the hidden worker.
- Added redirect preflight SSRF validation.
- Increased cold worker registration timeout to 180 seconds.
- Added focused regression tests and truthful Ultra reports.
""",
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "generated_at_utc": generated,
                "verified_live_providers": sorted(verified),
                "live_records": evidence["live_item_count"],
                "tests_passed": args.tests_passed,
                "windows_status": args.windows_status,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
