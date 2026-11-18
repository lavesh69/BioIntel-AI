# Changelog — Education Phase 12

## Added

- `src/biointel/education/phase12.py`
- `src/biointel/education/phase12_ui.py`
- `pages/350_BioIntel_Final_Completion_and_Qualification_Center.py`
- `scripts/verify_education_phase12.py`
- `scripts/run_education_phase12_worker.py`
- `RUN_EDUCATION_PHASE12_WORKER_WINDOWS.bat`
- `INSTALL_EDUCATION_PHASE12_WORKER_TASK_WINDOWS.bat`
- `REMOVE_EDUCATION_PHASE12_WORKER_TASK_WINDOWS.bat`
- 25 typed Phase 12 API routes
- OIDC PKCE, PostgreSQL migration apply, S3/MinIO transfer, originality, exam governance, AI/RAG governance and delivery-provider contracts

## Fixed

- Corrected examination evaluation SQL placeholder count discovered by executable tests.
- Rebuilt Step220 source manifests after all Phase 12 changes to prevent stale-hash installation failures.
- Preserved historical Phase 10 extraction markers so earlier frontend qualification remains reproducible.

## Preserved

All Phase 2–11 functionality, pages, database migrations, offline wheelhouse and Step220 Windows runtime files remain present.
