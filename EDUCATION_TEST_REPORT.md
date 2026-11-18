# Education Phase 17–22 Test Report

## Passing acceptance suites

| Command/suite | Result |
|---|---:|
| Education, Shiro and Connect regression (`test_education*.py`, `test_shiro*.py`, `tests/connect`) | 206 passed |
| `tests/test_education_phase17_22.py` | 8 passed |
| Phase 11 verifier | 37/37 controls |
| Phase 12 verifier | 36/36 controls |
| Phase 13 verifier | 27/27 controls |
| Phase 14 verifier | 29/29 controls |
| Phase 15 verifier | 30/30 controls |
| Phase 16 verifier | 30/30 controls |
| Python `compileall` for source/pages/scripts/tests | passed |
| Ruff for new/modified Phase 17–22 surfaces | passed |
| Windows wheelhouse verifier | 122 wheels, passed |
| Dependency-lock verifier | passed |
| Unicode diagnostics + one-pass worker | passed |

The target suite is deterministic and does not call paid APIs or require the internet.
Provider parsers use explicitly local fixtures.

## Coverage represented by the target suite

- Repeatable migrations and SQLite integrity.
- Canonical roles, resource RBAC and tenant isolation.
- End-to-end persistent learning workflow and restart.
- Shiro citations, insufficient evidence and cross-scope denial.
- Connect persistence, outbox delivery and unread recovery.
- Submission idempotency conflict behavior.
- Explainability, minimum-data status and human review.
- Studio optimistic concurrency, review, publication and export truthfulness.
- Science Pulse DOI/title deduplication and provider failure paths.
- API OpenAPI/schema and safe 403 mapping.
- Windows `.cmd` executable verification.
- Bundled FFmpeg lecture/media behavior.
- Spaces, Unicode and duplicate-worker PID lease.

## Broad historical suite diagnostic

Command: complete repository `pytest -q`, with a writable `BIOINTEL_USER_DATA_DIR`.

Observed summary before the 20-minute command limit:

- 1,913 passed
- 279 failed
- 28 skipped
- 3 errors

This run is not claimed green. Major failure classes were:

- historical Step 7–220 release assertions tied to earlier exact manifests/versions;
- stateful legacy tests that generate or rewrite source/data artifacts;
- Windows sandbox denial for joblib named pipes;
- browser/visual tests requiring installed Playwright browser binaries and running services;
- historical tests expecting a five-part Education release while this requested deliverable is four parts;
- external-engine/provider qualification that is intentionally fail-closed.

The release tree was restored from the four canonical ZIPs after this diagnostic, retaining
only the Phase 17–22 change set, and the 206-test target suite was rerun successfully.

