# BioIntel Education Phase 11 Changelog

## Added

- `src/biointel/education/phase11.py`
- `src/biointel/education/phase11_ui.py`
- `pages/349_BioIntel_Mega_Production_and_Academic_Center.py`
- `scripts/run_education_phase11_worker.py`
- `scripts/verify_education_phase11.py`
- `tests/test_education_phase11.py`
- TOTP MFA, recovery codes, secure authentication and rate limiting.
- Hash-chained security audit evidence.
- Governed Question Bank and item analytics.
- Grade schemes, transcripts and signed credentials.
- Notification outbox, SMTP adapter and report center.
- Health, incidents, retention and privacy workflows.
- AES-256-GCM full backups and restore rehearsal.
- Typed Phase 11 API routes and role-aware navigation.

## Fixed

- Updated Windows recovery discovery for Phase 7–11 package names.
- Regenerated the authoritative Step220 source manifest from the final Phase 11 source to prevent stale-hash installation failures.

## Preserved

- Existing Phase 2–10 Education, Shiro, Connect, Studio and bioinformatics features.
- Existing database migrations and local-first operation.
- Desktop-first UI scope; no mobile-specific redesign.
