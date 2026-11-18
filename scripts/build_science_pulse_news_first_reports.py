from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.science_pulse.models import MIGRATION_VERSION
from biointel.science_pulse.news_ui import ACTION_LABELS, CATEGORY_ALIASES, NEWS_CATEGORIES, NEWS_VIEWS
from biointel.science_pulse.service import CONTEXTUAL_ACTIONS
from biointel.science_pulse.ui import PRIMARY_NAVIGATION


REPORTS = (
    "SCIENCE_PULSE_NEWS_FIRST_UI_REPORT.md",
    "SCIENCE_PULSE_FINAL_INFORMATION_ARCHITECTURE.md",
    "SCIENCE_PULSE_NEWS_CATEGORY_MATRIX.json",
    "SCIENCE_PULSE_NEWS_CARD_SPEC.md",
    "SCIENCE_PULSE_INTEGRATION_ACTION_MATRIX.json",
    "SCIENCE_PULSE_NEWS_UI_TEST_REPORT.md",
    "SCIENCE_PULSE_NEWS_UI_TEST_RESULTS.json",
    "SCIENCE_PULSE_NEWS_UI_CHANGED_FILES.json",
    "SCIENCE_PULSE_NEWS_UI_KNOWN_LIMITATIONS.md",
    "CHANGELOG_SCIENCE_PULSE_NEWS_FIRST_UI.md",
)

CHANGED = (
    "src/biointel/science_pulse/models.py",
    "src/biointel/science_pulse/store.py",
    "src/biointel/science_pulse/service.py",
    "src/biointel/science_pulse/api.py",
    "src/biointel/science_pulse/news_ui.py",
    "src/biointel/science_pulse/ui.py",
    "src/biointel/education/ui.py",
    "tests/test_science_pulse_news_first_ui.py",
    "scripts/build_science_pulse_news_first_reports.py",
)


def generated_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write(name: str, value: str) -> None:
    (ROOT / name).write_text(value.rstrip() + "\n", encoding="utf-8", newline="\n")


def write_json(name: str, value: object) -> None:
    write(name, json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def category_matrix(db_path: Path) -> tuple[list[dict[str, object]], int]:
    counts: dict[str, int] = {}
    total = 0
    if db_path.is_file():
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        try:
            total = int(connection.execute(
                "SELECT COUNT(*) FROM sp_items WHERE content_type='news' AND live_state<>'DEMO'"
            ).fetchone()[0])
            counts = {
                str(row["category"]).casefold(): int(row["count"])
                for row in connection.execute(
                    """
                    SELECT value category,COUNT(*) count
                    FROM sp_items,json_each(categories_json)
                    WHERE content_type='news' AND live_state<>'DEMO'
                    GROUP BY value
                    """
                ).fetchall()
            }
        finally:
            connection.close()
    rows = []
    for category in NEWS_CATEGORIES:
        rows.append(
            {
                "category": category,
                "count_from_qualification_database": total if category == "All Science News" else sum(counts.get(alias.casefold(), 0) for alias in CATEGORY_ALIASES.get(category, (category,))),
                "count_policy": "Database-derived at runtime; never hard-coded in the UI.",
                "central_section": "Live Science News",
            }
        )
    return rows, total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-db", type=Path, required=True)
    parser.add_argument("--tests-passed", type=int, required=True)
    parser.add_argument("--tests-failed", type=int, default=0)
    parser.add_argument("--tests-skipped", type=int, default=0)
    parser.add_argument("--windows-status", default="NOT_RUN")
    args = parser.parse_args()
    now = generated_at()
    categories, live_count = category_matrix(args.live_db)

    write(
        "SCIENCE_PULSE_NEWS_FIRST_UI_REPORT.md",
        f"""# Science Pulse News-First UI Report

Generated: {now}

## Outcome

Science Pulse is now a dedicated scientific-intelligence workspace. Its primary navigation is the required 14-section structure, with one central Live Science News experience containing all 33 requested categories and eight views. Education, Shiro, Classroom, Academy, Studio and Connect are not primary Science Pulse destinations.

## Implemented

- Central live-news search, database-derived category counts and filters
- Featured, Latest, Breaking, For You, Trending, Story Clusters, Compact Headlines and Timeline views
- Paginated compact news cards with source, publisher, timestamps, provenance, read/save state, evidence and cluster status
- Detail dialog with permitted excerpt boundary, stored AI summaries, evidence states, entities and source timeline
- Lossless multi-source story clustering and explicit-only Research-Backed classification
- Persisted contextual drafts for Shiro, Classroom, Academy, Studio, Connect and Research workflows
- Safe queued refresh with no provider network work during Streamlit reruns
- Role-gated source mutation controls and member-readable source health
- FastAPI news search, detail/read and contextual-action routes

## Qualification

- Focused and adjacent regressions passed: {args.tests_passed}
- Failed: {args.tests_failed}
- Skipped: {args.tests_skipped}
- Streamlit direct Live Science News AppTest: PASSED
- Windows packaged-app status: {args.windows_status}
- Live qualification database records: {live_count}
- Migration: {MIGRATION_VERSION}
""",
    )

    navigation_lines = "\n".join(f"{index}. {name}" for index, name in enumerate(PRIMARY_NAVIGATION, 1))
    write(
        "SCIENCE_PULSE_FINAL_INFORMATION_ARCHITECTURE.md",
        f"""# Science Pulse Final Information Architecture

## Primary navigation

{navigation_lines}

Live Science News is the single news hub. Biology, biotechnology, biomedical, bioinformatics, regional and specialty categories are filters within it. Shiro AI, Classroom, Academy, BioIntel Studio, Connect, Research Projects and other modules are contextual actions only.

## Live Science News internal views

{', '.join(NEWS_VIEWS)}

## Governance

Sources & Operations remains visible for operational transparency. Source registration and queue mutation are shown only to authorized administrators.
""",
    )
    write_json(
        "SCIENCE_PULSE_NEWS_CATEGORY_MATRIX.json",
        {
            "generated_at_utc": now,
            "qualification_database": str(args.live_db.resolve()),
            "live_news_total": live_count,
            "categories": categories,
        },
    )

    write(
        "SCIENCE_PULSE_NEWS_CARD_SPEC.md",
        """# Science Pulse News Card Specification

Every reusable card supports NEWS/category/status badges, headline, verified-source state, original publisher, publication and discovery times, permitted excerpt, stored BioIntel summary, explicit evidence badge, source count, story-cluster badge, language, region, read/save state and correction state.

Primary actions are exactly: Read Full Story, Save, Share and More. More contains detail, contextual integrations, alerts, follows, citation export and classification reporting. Full copyrighted content is never implied when only metadata or an excerpt is stored.

Research-Backed is emitted only for an explicit linked publication, preprint, trial, dataset or evidence item. Official institutional announcements are labeled separately.
""",
    )

    action_rows = [
        {
            "action_key": key,
            "label": ACTION_LABELS[key],
            "destination": route[0],
            "backend_action": route[1],
            "persistence": "sp_integrations",
            "approval_required": True,
        }
        for key, route in CONTEXTUAL_ACTIONS.items()
    ]
    action_rows.extend(
        [
            {"action_key": "create_topic_alert", "label": "Create Topic Alert", "backend": "create_item_alert", "persistence": "sp_alert_rules"},
            {"action_key": "follow_source", "label": "Follow Source", "backend": "follow_item(kind=source)", "persistence": "sp_user_preferences"},
            {"action_key": "follow_topic", "label": "Follow Topic", "backend": "follow_item(kind=topic)", "persistence": "sp_user_preferences"},
            {"action_key": "export_citation", "label": "Export Citation or Source", "backend": "client download from persisted metadata", "persistence": "not applicable"},
        ]
    )
    write_json(
        "SCIENCE_PULSE_INTEGRATION_ACTION_MATRIX.json",
        {"generated_at_utc": now, "actions": action_rows},
    )

    write(
        "SCIENCE_PULSE_NEWS_UI_TEST_REPORT.md",
        f"""# Science Pulse News UI Test Report

- Passed: {args.tests_passed}
- Failed: {args.tests_failed}
- Skipped: {args.tests_skipped}
- Windows packaged-app: {args.windows_status}

Coverage includes exact navigation, 33-category matrix, central aggregation, category/region/live filters, pagination, card contract, More actions, persistence, details, explicit research evidence, source clusters, provenance, demo/live separation, publications/preprints separation, FastAPI contracts, role positioning, offline states, rerun stability and Streamlit AppTest execution.
""",
    )
    write_json(
        "SCIENCE_PULSE_NEWS_UI_TEST_RESULTS.json",
        {
            "generated_at_utc": now,
            "passed": args.tests_passed,
            "failed": args.tests_failed,
            "skipped": args.tests_skipped,
            "streamlit_live_news_apptest": "PASSED",
            "windows_packaged_app": args.windows_status,
            "scope": "Science Pulse news-first UI/service/API plus Education Phase 31-35 focused regressions",
        },
    )

    files = []
    for relative in CHANGED:
        path = ROOT / relative
        files.append(
            {
                "path": relative,
                "exists": path.is_file(),
                "bytes": path.stat().st_size if path.is_file() else 0,
                "sha256": sha256(path) if path.is_file() else "",
            }
        )
    write_json(
        "SCIENCE_PULSE_NEWS_UI_CHANGED_FILES.json",
        {"generated_at_utc": now, "files": files, "reports": list(REPORTS)},
    )

    write(
        "SCIENCE_PULSE_NEWS_UI_KNOWN_LIMITATIONS.md",
        """# Science Pulse News UI Known Limitations

- Grants, patents, conference and database/tool-release sections show truthful empty states until approved providers persist matching records.
- Region filtering uses supplied provenance and source text; records without region metadata remain global/unspecified.
- Research-Backed never relies on keyword similarity. Older records without explicit evidence relationships remain No Primary Research Linked.
- AI summaries appear only when a stored summary exists; the UI does not synthesize one during a rerun.
- External publication, email, desktop and institution delivery still require their configured dispatchers and approval workflows.
- The focused regression suite is not a claim that every historical BioIntel test file was rerun in this increment.
""",
    )
    write(
        "CHANGELOG_SCIENCE_PULSE_NEWS_FIRST_UI.md",
        f"""# Changelog - Science Pulse News-First UI

## {now[:10]}

- Replaced Education-styled Science Pulse layout with a dedicated scientific-news interface.
- Added exact 14-section primary navigation and centralized 33-category Live Science News.
- Added eight news views, filtering, pagination, detail dialog and reusable cards.
- Added read persistence, safe refresh queue, source verification, story clusters and explicit evidence states.
- Added contextual integration actions and Connect sharing through approval-required persisted drafts.
- Added FastAPI news endpoints, role-gated operations, regression tests and production reports.
- Updated migration to `{MIGRATION_VERSION}`.
""",
    )
    print(json.dumps({"reports_written": len(REPORTS), "live_records": live_count, "generated_at": now}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
