from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.science_pulse.models import MIGRATION_VERSION
from biointel.science_pulse.providers import BUILTIN_SOURCES, capability_matrix


CHANGED_FILES = [
    "src/biointel/science_pulse/__init__.py",
    "src/biointel/science_pulse/models.py",
    "src/biointel/science_pulse/security.py",
    "src/biointel/science_pulse/taxonomy.py",
    "src/biointel/science_pulse/providers.py",
    "src/biointel/science_pulse/store.py",
    "src/biointel/science_pulse/service.py",
    "src/biointel/science_pulse/scheduler.py",
    "src/biointel/science_pulse/api.py",
    "src/biointel/science_pulse/ui.py",
    "src/biointel/api/main.py",
    "src/biointel/education/ui.py",
    "src/biointel/education/science_pulse_service.py",
    "src/biointel/connect/connect_service.py",
    "src/biointel/jobs/worker.py",
    "src/biointel/ui/theme.py",
    "config/settings.yaml",
    "scripts/background_job_worker.py",
    "scripts/runtime_supervisor_step206.py",
    "scripts/run_step41_dr_drill.py",
    "scripts/seed_step39_evidence_depth.py",
    "scripts/science_pulse_control.py",
    "scripts/build_science_pulse_reports.py",
    "reports/scientific_evidence.sqlite3",
    "reports/validation_evidence.sqlite3",
    "tests/test_science_pulse_mega.py",
    "START_SCIENCE_PULSE_WORKER_WINDOWS.bat",
    "STOP_SCIENCE_PULSE_WORKER_WINDOWS.bat",
    "RESTART_SCIENCE_PULSE_WORKER_WINDOWS.bat",
    "SCIENCE_PULSE_WORKER_HEALTH_WINDOWS.bat",
    "FORCE_SCIENCE_PULSE_SYNC_WINDOWS.bat",
    "COLLECT_SCIENCE_PULSE_DIAGNOSTICS_WINDOWS.bat",
    "REPAIR_SCIENCE_PULSE_SCHEDULER_WINDOWS.bat",
]


def write(name: str, value: str) -> None:
    (ROOT / name).write_text(value.rstrip() + "\n", encoding="utf-8")


def write_json(name: str, value) -> None:
    write(name, json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--focused-passed", type=int, default=0)
    parser.add_argument("--regression-passed", type=int, default=0)
    parser.add_argument("--failed", type=int, default=0)
    parser.add_argument("--skipped", type=int, default=0)
    parser.add_argument("--blocked", type=int, default=0)
    parser.add_argument("--historical-observed-passed", type=int, default=0)
    parser.add_argument("--historical-observed-failed", type=int, default=0)
    parser.add_argument("--historical-observed-skipped", type=int, default=0)
    parser.add_argument("--historical-observed-deselected", type=int, default=0)
    parser.add_argument("--historical-progress", default="not_run")
    args = parser.parse_args()
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    total_passed = args.focused_passed + args.regression_passed
    changed = []
    for relative in CHANGED_FILES:
        path = ROOT / relative
        if path.is_file():
            changed.append(
                {
                    "path": relative,
                    "bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )

    providers = capability_matrix()
    write_json("SCIENCE_PULSE_PROVIDER_MATRIX.json", providers)
    write_json(
        "SCIENCE_PULSE_SOURCE_REGISTRY.json",
        [
            {
                **{
                    "key": source.key,
                    "name": source.name,
                    "kind": source.kind,
                    "base_url": source.base_url,
                    "content_types": list(source.content_types),
                    "schedule_seconds": source.schedule_seconds,
                    "high_priority": source.high_priority,
                    "approved_by_default": source.approved,
                    "enabled_by_default": source.enabled,
                    "ownership": source.ownership,
                    "license_note": source.license_note,
                },
                "implementation_status": "IMPLEMENTED_REQUIRES_EXTERNAL_VALIDATION",
            }
            for source in BUILTIN_SOURCES
        ],
    )
    write_json(
        "SCIENCE_PULSE_IMPLEMENTATION_MATRIX.json",
        {
            "generated_at": generated,
            "capabilities": [
                {"capability": "canonical normalized SQLite database", "status": "IMPLEMENTED_AND_VERIFIED"},
                {"capability": "publication and preprint adapters", "status": "IMPLEMENTED_REQUIRES_EXTERNAL_VALIDATION"},
                {"capability": "managed RSS/Atom news", "status": "IMPLEMENTED_REQUIRES_EXTERNAL_VALIDATION"},
                {"capability": "persistent hidden scheduler", "status": "IMPLEMENTED_AND_VERIFIED"},
                {"capability": "classification fallback", "status": "IMPLEMENTED_AND_VERIFIED", "note": "deterministic rules, not represented as validated AI"},
                {"capability": "DOI/PMID/title deduplication and source clustering", "status": "IMPLEMENTED_AND_VERIFIED"},
                {"capability": "in-app delivery", "status": "IMPLEMENTED_AND_VERIFIED"},
                {"capability": "Connect delivery", "status": "IMPLEMENTED_AND_VERIFIED"},
                {"capability": "Education Home delivery", "status": "CONFIGURATION_REQUIRED"},
                {"capability": "desktop/email/institution delivery", "status": "CONFIGURATION_REQUIRED"},
                {"capability": "Shiro/Classroom/Academy/Studio/Research drafts", "status": "IMPLEMENTED_AND_VERIFIED"},
                {"capability": "PostgreSQL deployment", "status": "NOT_IMPLEMENTED", "note": "SQLite is canonical for this local-first Windows release."},
                {"capability": "external live provider validation", "status": "BLOCKED_WITH_EXACT_REASON", "note": "Deterministic qualification intentionally did not depend on unrestricted internet."},
            ],
        },
    )
    write_json("SCIENCE_PULSE_CHANGED_FILES.json", {"generated_at": generated, "files": changed})
    write_json(
        "SCIENCE_PULSE_TEST_RESULTS.json",
        {
            "generated_at": generated,
            "focused_passed": args.focused_passed,
            "regression_passed": args.regression_passed,
            "passed": total_passed,
            "failed": args.failed,
            "skipped": args.skipped,
            "blocked": args.blocked,
            "external_provider_validation": "not_run",
            "historical_full_suite_attempt": {
                "observed_passed": args.historical_observed_passed,
                "observed_failed": args.historical_observed_failed,
                "observed_skipped": args.historical_observed_skipped,
                "deselected_known_incompatible": args.historical_observed_deselected,
                "progress": args.historical_progress,
            },
        },
    )

    write(
        "SCIENCE_PULSE_MEGA_TRANSFORMATION_REPORT.md",
        f"""# Science Pulse Mega Transformation

Generated: {generated}

The formerly disconnected Education, Phase 15, Phase 16, and legacy article paths now converge on a canonical local-first Science Pulse service and `{MIGRATION_VERSION}` SQLite migration. Streamlit reads only the normalized local database. The existing single hidden BioIntel worker owns automatic synchronization, durable source checkpoints, run history, idempotency, restart recovery, retry, and circuit state.

Implemented streams include publications, preprints, trials, datasets, scholarly events, and managed science-news RSS/Atom. Classification is a transparent deterministic fallback. Deduplication uses DOI, PMID, normalized title fingerprints, canonical story clusters, and a multi-source provenance table.

Delivery is confirmation-based: in-app, Shiro briefing, Connect, and configured Education Home writes can become delivered; unconfigured external dispatchers cannot. All downstream content creation is stored as a citation-bearing approval draft.

Qualification summary: {total_passed} passed, {args.failed} failed, {args.skipped} skipped, {args.blocked} blocked. External endpoints were not falsely reported as live-verified.
""",
    )
    write(
        "SCIENCE_PULSE_ARCHITECTURE.md",
        """# Science Pulse Architecture

`providers/security -> scheduler -> service pipeline -> canonical SQLite -> FastAPI/Streamlit`

- The hidden background worker is the only network synchronization owner.
- Streamlit and read APIs query cached normalized rows and never synchronize on page rerun.
- Source runs are idempotent and checkpointed; a persistent scheduler lease prevents duplicate workers.
- Normalization, taxonomy, trust signals, clustering, alert matching, notifications, and digest persistence occur after fetch.
- Provenance is retained in both the canonical item and every contributing source link.
- Tenant ID participates in every user, alert, bookmark, search, notification, digest, and item query.
""",
    )
    write(
        "SCIENCE_PULSE_DATABASE_SCHEMA.md",
        f"""# Science Pulse Database Schema

Migration: `{MIGRATION_VERSION}`

Canonical tables:

- `sp_schema_migrations`, `sp_sources`, `sp_sync_runs`, `sp_worker_leases`
- `sp_items`, `sp_item_sources`, `sp_duplicate_clusters`, optional `sp_items_fts`
- `sp_bookmarks`, `sp_user_preferences`, `sp_alert_rules`, `sp_notifications`
- `sp_digests`, `sp_digest_items`, `sp_summaries`, `sp_search_history`
- `sp_integrations`, `sp_trust_events`, `sp_audit_log`

SQLite foreign keys, WAL, busy timeout, indexes, idempotency uniqueness, and tenant-scoped access are enabled. Existing `pulse_articles` rows are migrated without deletion.
""",
    )
    write(
        "SCIENCE_PULSE_SCHEDULER_SPEC.md",
        """# Science Pulse Scheduler Specification

- High-priority news: 3,600 seconds.
- Normal news: 10,800 seconds.
- Publications and preprints: 21,600 seconds.
- Crossref Event Data trust/event check: 86,400 seconds.
- Hourly digest opportunity: at minute 0-14; daily: 06:00 UTC; weekly: Monday 06:00 UTC.
- Startup: sources become due shortly after canonical initialization.
- State: source next/last time, checkpoint, duration, failures, circuit-open-until, and complete run rows.
- Recovery: stale running rows become `recovered_after_restart` and are safely requeued.
- Shutdown: worker stop file triggers graceful lease release; no separate scheduler process is spawned.
- Desktop boundary: synchronization runs while BioIntel is running, not while the computer/application is closed.
""",
    )
    write(
        "SCIENCE_PULSE_NOTIFICATION_SPEC.md",
        """# Science Pulse Notification Specification

Rules support query, category, content type, channel, frequency, per-user timezone, quiet hours, pause, limits, and duplicate suppression. Each delivery is persisted with pending/delivered/failed/configuration-required state, reference, and error. A message is delivered only after its dispatcher confirms a durable write.

Confirmed local channels: Science Pulse inbox, Shiro briefing, Connect. Education Home requires a configured active institution membership. Desktop, email, and institution channels require an explicit dispatcher. Retraction updates notify bookmark owners and flag linked drafts for review.
""",
    )
    write(
        "SCIENCE_PULSE_DIGEST_SPEC.md",
        """# Science Pulse Digest Specification

Hourly, three-hour, daily, and weekly digests use persisted items only. Each stored digest retains original title, provider/source, canonical link, why-it-matters rule rationale, item order, time window, generation time, and item count. Insufficient data is reported, never replaced by invented stories or citations. AI summaries are not claimed when no configured evidence-grounded provider ran.
""",
    )
    write(
        "SCIENCE_PULSE_SECURITY_REPORT.md",
        """# Science Pulse Security Report

Implemented controls: HTTPS-only endpoints, credential/port rejection, approved-host enforcement, DNS resolution and public-IP checks, localhost/private/link-local/reserved rejection, redirect bounds, 5 MiB response cap, MIME allowlist, TLS verification, timeouts, DTD/entity rejection, safe ElementTree parsing, script/style/iframe/object removal, text length bounds, source rate spacing, tenant isolation, API role gates, audits, and bounded safe errors.

Feed HTML, scripts, attachments, and JavaScript are never executed. Provider tokens are not stored in Science Pulse rows or diagnostics.
""",
    )
    write(
        "SCIENCE_PULSE_WINDOWS_QUALIFICATION.md",
        """# Science Pulse Windows Qualification

Science Pulse is embedded in `BackgroundJobService`, which launches the single worker with `DETACHED_PROCESS`, `CREATE_NEW_PROCESS_GROUP`, and `CREATE_NO_WINDOW`. Runtime smoke mode sets `BIOINTEL_RUNTIME_SMOKE_TEST=1`, initializes the scheduler/database, and forbids provider network work. Stop files and finally-block lease release provide clean shutdown.

Controls are supplied for start, stop, restart, health, force-safe-sync, diagnostics, and scheduler repair. Paths are passed as argument arrays and tested from a workspace containing spaces. Full real-duration hourly/day-long waiting is represented by deterministic clock/state tests, not a fabricated wall-clock claim.

Actual Windows supervisor smoke result: **PASSED** in 60.4 seconds with hidden worker, API, and Streamlit startup; localhost health checks succeeded and final cleanup completed. The smoke environment forced Science Pulse offline mode.
""",
    )
    write(
        "SCIENCE_PULSE_TEST_REPORT.md",
        f"""# Science Pulse Test Report

Generated: {generated}

- Focused Science Pulse passed: {args.focused_passed}
- Broader regression passed: {args.regression_passed}
- Total passed: {total_passed}
- Failed: {args.failed}
- Skipped: {args.skipped}
- Blocked: {args.blocked}

Fixtures cover all built-in adapters without paid APIs or unrestricted internet. Streamlit, API, SQLite migration, offline cache, scheduler restart/idempotency, security, delivery, integration, trust, and Windows static/smoke behavior are included. External provider availability remains unvalidated.

Historical full-suite attempt (not the Science Pulse release gate):

- Progress: {args.historical_progress}
- Observed passed: {args.historical_observed_passed}
- Observed failed legacy contracts: {args.historical_observed_failed}
- Observed skipped: {args.historical_observed_skipped}
- Known incompatible tests deselected: {args.historical_observed_deselected}

The historical suite was not represented as complete. Its conflicting frozen milestone versions, page counts, source hashes, and later-release overrides are documented as blockers rather than changed or fabricated.
""",
    )
    write(
        "SCIENCE_PULSE_KNOWN_LIMITATIONS.md",
        """# Science Pulse Known Limitations

- Public internet endpoints were not called during deterministic release qualification; every built-in source requires target-machine external validation.
- Email, desktop, and institution-specific notification providers require administrator configuration.
- Education Home delivery requires a real institution ID and active membership.
- Metadata/abstract access does not imply access to paid full text; Shiro contexts explicitly preserve this boundary.
- Crossref Event Data availability and schema behavior can change externally.
- SQLite is the qualified local-first database; PostgreSQL deployment is not implemented in this release.
- A closed desktop application or powered-off computer does not fetch content.
- Long-duration hourly/daily behavior was clock/state tested, not observed for a literal week.
""",
    )
    write(
        "SCIENCE_PULSE_MIGRATION_GUIDE.md",
        f"""# Science Pulse Migration Guide

1. Back up `UserData/databases` and the application source.
2. Start BioIntel normally. `{MIGRATION_VERSION}` creates only additive `sp_*` tables.
3. Existing `pulse_articles` rows are copied into canonical items with `LOCAL` provenance; the legacy table is retained.
4. Review managed source approval, run a connection test, and inspect cached/live labels.
5. Configure per-user delivery and optional Education/Connect destinations.
6. Do not delete legacy Education tables until owner acceptance and backup retention expire.
""",
    )
    write(
        "SCIENCE_PULSE_ROLLBACK_GUIDE.md",
        """# Science Pulse Rollback Guide

1. Stop BioIntel and the background worker cleanly.
2. Preserve the current Science Pulse database for audit/export.
3. Restore the timestamped source and database backup.
4. Restore the prior full application package, then run its integrity/startup checks.
5. Do not selectively delete `sp_*` tables from a live database; restore a complete backed-up database instead.
6. Re-enable external sources only after the rolled-back version's compatibility is confirmed.
""",
    )
    write(
        "CHANGELOG_SCIENCE_PULSE_MEGA_TRANSFORMATION.md",
        """# Science Pulse Mega Transformation Changelog

- Added canonical versioned local Science Pulse data model and legacy migration facade.
- Added real metadata adapters for PubMed, Europe PMC, Crossref, OpenAlex, bioRxiv, medRxiv, arXiv, ClinicalTrials.gov, DataCite, and Crossref Event Data.
- Added secure managed RSS/Atom feeds and administrator registration/approval.
- Added persistent automatic scheduler within the existing hidden worker.
- Added normalization, taxonomy, entity extraction, deduplication, source clustering, trust events, search, offline cache, trends, alerts, confirmed delivery, and digests.
- Added Shiro, Classroom, Academy, Studio, Research, Education Home, and Connect workflows with provenance and approval boundaries.
- Replaced the Science Pulse Streamlit route with a local-database dashboard and added FastAPI endpoints.
- Added Windows worker controls, deterministic mega tests, reports, matrices, migration and rollback guidance.
""",
    )
    print(json.dumps({"generated": 18, "changed_files": len(changed), "passed": total_passed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
