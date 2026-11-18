# BioIntel Education Phase 2 Rollback

Phase 2 is additive. Before rollback, back up the Education SQLite database and media directory under the configured BioIntel UserData root.

## Code rollback

Restore the pre-Phase-2 versions of:

- `src/biointel/education/__init__.py`
- `src/biointel/education/ui.py`
- `src/biointel/education/universe_ui.py`

Remove only the Phase 2 additions:

- `src/biointel/education/phase2.py`
- `src/biointel/education/phase2_ui.py`
- `src/biointel/education/components/`
- `tests/test_education_phase2.py`

## Database rollback

The additive tables are `education_dashboard_preferences`, `education_institution_branding`, `education_saved_reports`, and `education_presentation_runs`. Leaving them in place is safe for a code rollback. Drop them only after a verified backup and only when stored preferences, branding, saved reports and presentation audit history are intentionally being deleted.

Do not delete the shared Education database, existing Phase 1 tables, demo provenance tables or institutional media as part of a Phase 2 rollback.