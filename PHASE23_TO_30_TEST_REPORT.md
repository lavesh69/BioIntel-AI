# Phase 23–30 Test Report

Qualification date: 2026-07-30

## New suite

`pytest -q tests/test_education_phase23_30.py --disable-warnings`

Result: **18 passed, 0 failed, 0 skipped**.

Coverage includes migration, registry seeding, pilots, onboarding, CSV/XLSX import/rollback, diagnostics privacy, support, agent safety/approval/evidence, lab calculations/state/notebook/assessment/PDF, mastery explanations/scheduling/cycle control, research provenance/review/retraction, credentials/shares/revocation, API scopes/rate/tenant boundaries, SQL-injection-shaped input, path traversal, file validation, webhooks, plugins, MCP, background jobs, object storage, backup inspection, Unicode paths, Windows scripts, FastAPI/OpenAPI and truthful capability states.

## Regression batch

Education historical tests, `tests/connect`, and Shiro AI tests were executed together. The post-upgrade rerun result is recorded in `PHASE23_TO_30_TEST_RESULTS.json`.

## UI and runtime

- Ruff: all changed Phase 23–30 Python files passed.
- `compileall`: passed.
- Streamlit AppTest: two new pages passed empty-state and authenticated contexts.
- Diagnostic: passed under a Unicode path with spaces.
- Worker `--once`: passed with an empty queue.
- Local load probe: 800 operations, concurrency 32, zero errors; timings measured, virtual-user count simulated, production capacity not verified.

## Historical baseline

Before Phase 23 implementation, the broad inherited repository suite produced **1,914 passed, 278 failed, 28 skipped and 3 errors**. Those failures were not deleted or weakened. They include historical release/version/theme/browser/external/stateful areas and mean the broad inherited suite is not green.

The post-upgrade broad diagnostic ran on a separate disposable copy and produced **1,931 passed, 279 failed, 28 skipped and 3 errors in 761.17 seconds**. No Phase 23–30 test appears in its failure/error summary; the focused Phase 23–30 suite separately passes 18/18. The broad delta is +17 passes and +1 failure, with unchanged skipped/error counts, and remains classified `NOT_GREEN`.
