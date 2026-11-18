# Changelog — Education Phase 7 Desktop

## Added

- Education Phase 7 service and backward-compatible migration.
- Desktop identity accounts, scrypt PIN authentication and revocable sessions.
- Phase 7 Desktop application page and primary navigation entry.
- Lazy selected-workspace router and desktop command palette.
- Timetable edit/cancel workflows with conflict revalidation.
- Editable gradebook and bulk attendance roster.
- Assignment Kanban, rubric builder, criterion scoring and rubric evidence tables.
- Curriculum builder, lecture chapters, notes, bookmarks and multilingual transcripts.
- Native Shiro chat UI and conversation lifecycle management.
- Interactive mastery graph and scientific visual viewers.
- Configurable exam passing threshold, live monitoring refresh and moderation timeline.
- Twenty-five typed Phase 7 API routes.
- Phase 7 tests, qualification verifier and Windows verification launcher.

## Fixed

- Hardcoded analytical pass threshold replaced by examination-specific policy.
- Heavy all-tabs page execution replaced by selected-workspace execution.
- Raw end-user qualification JSON replaced by status cards with optional evidence detail.
- Assignment scoring can now preserve criterion-level evidence instead of only one total mark.
- Academy lecture evidence can now be searched through governed transcripts.

## Preserved

- Phase 2 academic-integrity hardening.
- Phase 3 secure examination and granular RBAC.
- Phase 4 adaptive learning, Shiro grounding, timetable and notifications.
- Phase 5 institution platform and integration readiness.
- Phase 6 visual command center, worker operations and qualification adapters.
- Existing databases through additive migrations.

## Intentionally excluded

- Mobile-specific redesign and mobile-device qualification, per owner instruction.
