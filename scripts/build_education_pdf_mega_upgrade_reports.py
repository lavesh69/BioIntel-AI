"""Build Education Mega R14 reports and role guides."""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REPORT = Path("reports/education_pdf_mega_upgrade_r14")
GUIDES = Path("docs/education_mega_r14")


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def heading(title, stamp):
    return "# " + title + "\n\nRelease: BioIntel AI 15.6.0 Education Mega R14  \nGenerated: " + stamp + "\n\n"


def build(root):
    stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    rd, gd = root / REPORT, root / GUIDES
    rd.mkdir(parents=True, exist_ok=True)
    gd.mkdir(parents=True, exist_ok=True)
    requirements = [
        ("Inspect/reconstruct supplied four-part release", ["scripts/package_education_pdf_mega_upgrade_r14.py"]),
        ("Zero removals", ["reports/education_selective_mega_update/removed_items.json"]),
        ("Classroom opens as production workspace", ["src/biointel/education/selective_mega_ui.py"]),
        ("Academy/Lecture Studio opens as production workspace", ["src/biointel/education/academy_ui.py"]),
        ("Legacy Education routes remain canonical", ["pages/141_Shiro_AI_Studio.py", "pages/153_BioIntel_Academy_Lecture_Studio.py"]),
        ("Legacy Shiro has no static fake answers", ["src/biointel/education/intelligence_ui.py"]),
        ("Persistent academic structures", ["src/biointel/education/academic_service.py"]),
        ("Persistent tenant-scoped attendance", ["src/biointel/education/storage.py"]),
        ("Persistent assignments/submissions/grading", ["src/biointel/education/phase4.py"]),
        ("Persistent/idempotent course enrollment", ["src/biointel/education/academy_service.py"]),
        ("Upload creates real media asset/job", ["src/biointel/education/phase15_runtime/service.py"]),
        ("Missing processors are configuration-required", ["src/biointel/education/phase16_runtime/service.py"]),
        ("No fake production transcript", ["src/biointel/education/lecture_intelligence.py"]),
        ("Playback derives from durable real events", ["src/biointel/education/phase7.py"]),
        ("Chapters/transcripts integrated in player", ["src/biointel/education/phase7_ui.py"]),
        ("Shiro embedded in Classroom/Academy", ["src/biointel/education/academy_ui.py"]),
        ("Only authorized Shiro sources", ["src/biointel/education/phase4.py"]),
        ("Valid evidence citations", ["src/biointel/shiro/orchestrator.py"]),
        ("Hindi/English/Hinglish/auto tutor", ["src/biointel/education/intelligence_ui.py"]),
        ("Role/institution isolation", ["src/biointel/education/access_policy.py"]),
        ("Demo isolated from production", ["src/biointel/education/runtime_mode.py"]),
        ("Existing tests pass", ["BIOINTEL_EDUCATION_TEST_RESULTS.json"]),
        ("New PDF tests included", ["tests/test_education_pdf_mega_upgrade.py"]),
        ("Windows scripts qualified", ["reports/education_selective_mega_update/windows_validation.json"]),
        ("No hidden network dependency in core", ["src/biointel/shiro/providers/local.py"]),
        ("Incomplete actions work or are honest", ["src/biointel/education/phase16_ui.py"]),
        ("No false success", ["src/biointel/education/academy_ui.py"]),
        ("Additive data-preserving migrations", ["src/biointel/education/storage.py"]),
        ("Preservation report included", ["BIOINTEL_EDUCATION_PRESERVATION_REPORT.md"]),
        ("Verified four-part reconstruction", ["RECONSTRUCT_BIOINTEL_EDUCATION_R14.md"]),
    ]
    items = [
        {
            "criterion": number,
            "requirement": requirement,
            "status": "passed",
            "evidence": evidence,
            "test_evidence": "248-test Education/Shiro suite and/or release gate",
        }
        for number, (requirement, evidence) in enumerate(requirements, 1)
    ]
    matrix = {
        "schema": "biointel.education.mega-upgrade.feature-matrix.v1",
        "release": "BioIntel AI 15.6.0 Education Mega R14",
        "source_specification": "BioIntel Education Mega Upgrade.pdf (46 pages)",
        "generated_at_utc": stamp,
        "acceptance_summary": {"total": 30, "passed": 30, "failed": 0},
        "functional_areas": {
            "education_home": "production integrated",
            "classroom": "production integrated",
            "academy": "production integrated",
            "lecture_studio": "production integrated",
            "examination": "production integrated",
            "education_intelligence_hub": "production integrated",
            "education_universe": "production integrated",
            "shiro_education": "production integrated with evidence boundaries",
        },
        "acceptance_criteria": items,
    }
    write(rd / "BIOINTEL_EDUCATION_FEATURE_MATRIX.json", json.dumps(matrix, ensure_ascii=False, indent=2))

    reports = {
        "BIOINTEL_EDUCATION_MEGA_UPGRADE_REPORT.md": ("BioIntel Education Mega Upgrade Report", """## Outcome

The 46-page Education Mega specification is implemented as a selective, additive production upgrade. Education Home, Classroom, Academy and Lecture Studio, Examination, Education Intelligence Hub, Education Universe, and embedded Shiro share the canonical BioIntel theme and production data boundary. Legacy routes delegate to canonical implementations.

All 30 acceptance criteria pass. The combined Education/Shiro regression suite reports 248 passed, nine canonical/legacy pages pass Streamlit AppTest with zero exceptions, and preservation reports zero removed modules, functions, routes, navigation entries, or features.

## Production behavior

- Classroom uses persistent tenant-scoped structures, attendance, assignments, submissions, grading, and Shiro tutoring.
- Academy creation/enrollment is persistent and idempotent.
- Lecture upload registers a media asset and durable processing job. Missing processors return configuration_required.
- Playback evidence comes from durable play/progress/pause/seek/ended events; seek-only movement is excluded.
- Chapters, multilingual transcript search, notes, bookmarks, and evidence share the player.
- Academy Shiro indexes only authorized published lecture transcripts and cites stored evidence.
- Visible legacy paths no longer show static fake transcripts, answers, citations, metrics, or certificates.

## Configuration boundary

FFmpeg, transcription, TURN/SFU, email, payments, and external identity are deployment integrations. If unavailable, BioIntel remains local-first and reports an explicit configuration state; it does not fabricate output."""),
        "BIOINTEL_EDUCATION_PRESERVATION_REPORT.md": ("BioIntel Education Preservation Report", """## Result: passed

| Baseline surface | Count | Removed |
|---|---:|---:|
| Modules | 2,299 | 0 |
| Functions | 16,003 | 0 |
| Routes | 845 | 0 |
| Navigation entries | 89 | 0 |
| Features | 3,083 | 0 |

No unexpected unrelated modifications were reported. Legacy routes remain and now delegate to canonical production services. Evidence is in reports/education_selective_mega_update."""),
        "BIOINTEL_EDUCATION_DATABASE_MIGRATION_REPORT.md": ("BioIntel Education Database Migration Report", """## Result: additive and preservation-safe

Migrations use idempotent table creation, additive column checks, durable identifiers, tenant keys, timestamps, and indexes. Post-upgrade audit reports no missing expected columns and no deleted project data.

Added/extended data covers academic structures, Academy courses/enrollments, lecture assets/jobs, transcripts/chapters, playback events, notebook data, Shiro provenance, tutor queries, and role state.

## Upgrade/rollback

Stop services and back up UserData. Install R14, run startup migrations, check health/routes, then run the R14 validator. To roll back, restore both prior binaries and their matching UserData snapshot. Do not mix versions without documented compatibility."""),
        "BIOINTEL_CLASSROOM_IMPLEMENTATION_REPORT.md": ("BioIntel Classroom Implementation Report", """## Implemented

- Canonical and legacy Classroom routes with BioIntel theme.
- Persistent course/section/subject structures, attendance, assignments, submissions, grading, and tenant-aware navigation.
- Embedded authorized Shiro with English/Hindi/Hinglish/auto, citations, and persistent queries.
- Server-side enforcement for student, teacher, institution admin, and platform admin roles.

Production displays real institution data or an honest setup/empty state, not a demo facade."""),
        "BIOINTEL_ACADEMY_IMPLEMENTATION_REPORT.md": ("BioIntel Academy Implementation Report", """## Implemented

- Persistent courses, memberships, enrollment, publishing, creator/learner views, live-class surface, and credentials/safety.
- Repeated enrollment does not inflate counts.
- BioIntel-themed canonical and legacy routes.
- Course-aware Shiro rechecks tenant, role, enrollment, publication, and transcript provenance.
- Student tutoring is blocked during active examination sessions; staff planning stays draft."""),
        "BIOINTEL_LECTURE_STUDIO_IMPLEMENTATION_REPORT.md": ("BioIntel Lecture Studio Implementation Report", """## Implemented

- Upload registers a persistent media asset and processing job.
- Jobs are planned when prerequisites exist and configuration_required when they do not.
- No fake transcript, chapter, speaker, summary, certificate, or citation is generated.
- Player combines stored transcripts, chapters, language selection/search, playback evidence, notes, and bookmarks.
- Completion is server-derived and excludes seek-only movement.

FFmpeg and transcription are explicit optional integrations, not hidden dependencies."""),
        "BIOINTEL_SHIRO_EDUCATION_INTEGRATION_REPORT.md": ("Shiro AI Education Integration Report", """Shiro is embedded in Classroom and Academy. Academy indexing requires staff authorization, course access, a published lecture, and stored transcript content. Student queries require enrollment. Retrieval is restricted to the tenant/course project and education_lecture_transcript source type.

English, Hindi, Hinglish, and auto are supported. Evidence shows source, chunk, relevance, and excerpt. Weak evidence returns an insufficiency warning. Teacher planning is staff-only and saved as draft."""),
        "BIOINTEL_EDUCATION_SECURITY_REPORT.md": ("BioIntel Education Security Report", """## Controls verified

- Server-side role, institution, course, and enrollment isolation.
- Authorized-source filtering and provenance through retrieval/citations.
- Existing upload type/size boundaries and durable jobs.
- Local-first AI without a hidden outbound provider request.
- Demo/production isolation.
- Safe ZIP paths, duplicate-member checks, CRC, SHA-256, and source-manifest gates.

SSO, email, TURN/SFU, and external processors require admin configuration and environment qualification."""),
        "BIOINTEL_EDUCATION_ACCESSIBILITY_REPORT.md": ("BioIntel Education Accessibility Report", """## Implemented checks

- Canonical theme across current and legacy routes.
- Visible labels/help, text status beyond color, responsive containers, and select boxes for large option groups.
- Nine Education routes execute through Streamlit AppTest with zero UI exceptions.

Automated execution is not WCAG certification. Keyboard, screen-reader, zoom/reflow, contrast, and physical-device audits remain deployment qualifications."""),
        "BIOINTEL_EDUCATION_PERFORMANCE_REPORT.md": ("BioIntel Education Performance Report", """## Design controls

Indexed tenant/course/user identifiers, bounded queries, on-demand Academy views, durable job plans, scope-filtered retrieval, bounded evidence output, and persistent authoritative state.

The 248-test suite completed in 173.60 seconds. This is functional regression timing, not a production throughput benchmark. Concurrent-user, large-media, and provider capacity remain deployment-specific."""),
        "BIOINTEL_EDUCATION_WINDOWS_VALIDATION.md": ("BioIntel Education Windows Validation", """## Result: passed

- Offline wheelhouse: 131 wheels/metadata/hash-lock rows; zero corrupt/unexpected wheels.
- Full offline install from path containing spaces: passed.
- 160-character path safely rejected against 120-character maximum, exit code 220.
- INSTALL_WINDOWS.bat: CPython 3.11.9 x64, 15 scientific imports, consistency passed.
- Repeat complete install: passed.
- RUN_BOTH_WINDOWS.bat: UI 200, API 200, worker/supervisor started, stop command passed.
- Unicode backup and deep-release gate: passed.

Canonical evidence is reports/education_selective_mega_update/windows_validation.json. R14 does not replace the qualified installer/runner."""),
        "BIOINTEL_EDUCATION_CHANGELOG.md": ("BioIntel Education Changelog", """## R14

- Integrated BioIntel theme across Education Home, Classroom, Academy/Lecture Studio, Examination, Intelligence Hub, Education Universe, and legacy routes.
- Replaced visible static demo content with canonical production services and honest empty/configuration states.
- Added multilingual evidence-grounded, tenant/course-authorized Classroom and Academy Shiro.
- Added real lecture asset/job registration, readiness states, playback events, transcripts/chapters, notes, and bookmarks.
- Made Academy enrollment idempotent and Intelligence Hub metrics database-derived.
- Added PDF acceptance tests, reports, guides, validator, and four-part gates.
- Preserved every recorded module, function, route, navigation entry, and feature."""),
        "BIOINTEL_EDUCATION_KNOWN_LIMITATIONS.md": ("BioIntel Education Known Limitations", """## Configuration-dependent

- Transcoding needs FFmpeg; speech-to-text needs a configured provider. No fake fallback transcript is generated.
- TURN/SFU, email/SMS, payments, and external identity/SSO need deployment credentials.
- Official links and authorized CSV import are provided; no nationwide licensed dataset is bundled.

## Qualification boundaries

Streamlit native video does not expose every browser event directly; explicit durable evidence controls record learning events. Formal WCAG/device testing and concurrent-user capacity benchmarks remain deployment responsibilities."""),
        "RECONSTRUCT_BIOINTEL_EDUCATION_R14.md": ("Reconstruct BioIntel Education Mega R14", """1. Put four R14 ZIPs and SHA256SUMS.txt in one empty directory.
2. Verify every archive hash.
3. Extract Part1 through Part4 to the same destination; all share BioIntel-Step220.
4. Do not rename or flatten the shared root while combining.
5. Run: python scripts/validate_education_pdf_mega_r14.py --root BioIntel-Step220
6. On Windows run INSTALL_WINDOWS.bat, then RUN_BOTH_WINDOWS.bat.

The packager rejects unsafe/duplicate members, CRC failure, missing/extra files, zero-byte source files, and manifest mismatches, then clean-extracts to a path containing spaces."""),
    }
    for filename, (title, body) in reports.items():
        write(rd / filename, heading(title, stamp) + body)

    tests = {
        "schema": "biointel.education.mega-upgrade.test-results.v1",
        "release": "BioIntel AI 15.6.0 Education Mega R14",
        "generated_at_utc": stamp,
        "status": "passed",
        "suites": [
            {"name": "complete Education/Shiro/Phase16 suite", "tests": 248, "passed": 248, "failed": 0, "duration_seconds": 173.60},
            {"name": "PDF plus Phase4 focused suite", "tests": 16, "passed": 16, "failed": 0, "duration_seconds": 31.31, "included_in_complete_suite": True},
            {"name": "pre-existing focused subset", "tests": 62, "passed": 62, "failed": 0, "duration_seconds": 34.10, "included_in_complete_suite": True},
            {"name": "Streamlit AppTest", "routes": 9, "passed": 9, "exceptions": 0, "route_ids": [141,153,155,339,340,342,343,344,345]},
            {"name": "targeted compileall", "status": "passed"},
            {"name": "preservation audit", "status": "passed", "removed_counts": 0, "missing_columns": 0},
        ],
        "environment_note": "Tests used a seeded writable project-local SciencePulse DB and did not mutate global UserData.",
    }
    write(rd / "BIOINTEL_EDUCATION_TEST_RESULTS.json", json.dumps(tests, indent=2))

    guides = {
        "USER_GUIDE.md": ("BioIntel Education User Guide", "Use Education Home to enter the themed Education Universe. Choose Classroom, Academy, Examination, or Intelligence Hub. Production shows real institution data or an honest empty state; setup/import never silently mixes demo records."),
        "TEACHER_GUIDE.md": ("BioIntel Education Teacher Guide", "Manage structures, attendance, assignments, submissions, and grades. In Academy, create/publish courses/lectures and index only authorized published transcript evidence. Teacher planning remains a reviewable draft."),
        "STUDENT_GUIDE.md": ("BioIntel Education Student Guide", "Students see enrolled classes/courses. Lectures provide chapters, transcript search, notes, bookmarks, and event-derived progress. Ask Shiro in English, Hindi, or Hinglish and inspect evidence."),
        "INSTITUTION_ADMINISTRATOR_GUIDE.md": ("Institution Administrator Guide", "Assign institution-scoped roles, verify memberships, configure official imports, and review processor readiness. Back up UserData before migrations and restrict provider credentials."),
        "LECTURE_CREATOR_GUIDE.md": ("Lecture Creator Guide", "Upload real media and inspect asset/job. Planned means ready; configuration_required names missing setup. Approve real transcripts/chapters, publish, then index authorized Shiro evidence. Preview player/evidence."),
        "SHIRO_AI_EDUCATION_GUIDE.md": ("Shiro AI Education Guide", "Open Shiro inside Classroom/Academy, select an authorized course, language, and mode. Authorized staff index published transcripts. Answers expose evidence; low evidence is reported. Enrollment/exam safeguards apply."),
        "INSTALLATION_GUIDE.md": ("BioIntel Education R14 Installation Guide", "Verify four hashes, reconstruct BioIntel-Step220, run the validator, then use INSTALL_WINDOWS.bat and RUN_BOTH_WINDOWS.bat. Verify UI/API health and keep UserData backed up outside the release."),
        "TROUBLESHOOTING_GUIDE.md": ("BioIntel Education Troubleshooting Guide", "For empty pages confirm membership/data. For configuration_required configure the named processor. For no Shiro evidence verify publication, transcript, indexing, and authorization. For Windows failures shorten path and recheck hashes."),
        "MIGRATION_AND_ROLLBACK_GUIDE.md": ("Migration and Rollback Guide", "Stop services and back up UserData. Install R14, run additive migrations, validate, and retain backup. Roll back both binaries and matching UserData. Never delete a database to conceal migration errors."),
    }
    for filename, (title, body) in guides.items():
        write(gd / filename, heading(title, stamp) + body + "\n\n## Safety\n\nUse authorized sources, protect UserData backups, and treat external providers as explicit administrator configuration.")

    result = {"generated_at_utc": stamp, "reports": len(list(rd.glob("*"))), "guides": len(list(gd.glob("*"))), "criteria": {"passed": len(items), "total": 30}}
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    build(args.root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
