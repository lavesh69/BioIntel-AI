# BioIntel Education Upgrade Rollback

This rollback is manual and intentionally non-destructive. Back up any real `UserData` first. Never remove `UserData` as part of source rollback.

## Source rollback

Restore these modified files from the original BioIntel AI 15.6.0 four-part archives:

- `.streamlit/config.toml`
- `src/biointel/education/api.py`
- `src/biointel/education/ui.py`

Remove these files/directories only if reverting this upgrade:

- `src/biointel/education/paths.py`
- `src/biointel/education/universe_ui.py`
- `src/biointel/education/demo/`
- `scripts/seed_biointel_education_demo.py`
- `scripts/reset_biointel_education_demo.py`
- `SEED_EDUCATION_DEMO_WINDOWS.bat`
- `RESET_EDUCATION_DEMO_WINDOWS.bat`
- `tests/test_education_demo.py`
- the six Education upgrade reports/changelog added by this release

The final ZIP manifest contains hashes for delivered archives. The original four archives are not modified.

## Demo data rollback

Use `RESET_EDUCATION_DEMO_WINDOWS.bat` or `python scripts/reset_biointel_education_demo.py`. This removes only:

- `education-demo.sqlite3`
- `demo-media`

It does not remove `education.sqlite3` or production media. The reset implementation refuses unexpected paths.

## Database compatibility

The demo metadata/manifest tables exist only inside the isolated demo database. Existing production Education migrations and Universe tables are not dropped by this release. `EducationUniverse.rollback()` remains an explicit development-only method and is never called by startup, seed, reset, or this rollback procedure.