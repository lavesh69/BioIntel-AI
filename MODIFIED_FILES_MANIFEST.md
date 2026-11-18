# Modified Files Manifest

Release: `15.6.0-Step220.0-WINDOWS-V20.3`

## Active metadata and integration

- `VERSION`
- `README.md`
- `src/biointel/cli.py`
- `src/biointel/synthetic/core.py`
- `src/biointel/synthetic/service.py`
- `src/biointel/ui/navigation.py`
- `pages/270_Discovery_Lab_Platform.py`

## New connected platform package

All Python modules under `src/biointel/discovery_platform/` are Step220 platform files, including storage, lifecycle, ingestion, workflow, execution, provenance, analysis engines, analytics, research services, security, operations, reports, synthetic adapter/bridge, API routers/schemas, CLI, SDK, and service facade.

## Tests

- `tests/test_step220_discovery_platform.py`

## Release documentation

- `BIOINTEL_DISCOVERY_PLATFORM_PRE_UPGRADE_AUDIT.md`
- `BIOINTEL_DISCOVERY_PLATFORM_UPGRADE_REPORT.md`
- `TEST_EXECUTION_REPORT.md`
- `KNOWN_LIMITATIONS.md`
- `MIGRATION_NOTES.md`
- `WINDOWS_VERIFICATION_CHECKLIST.md`
- `DEPENDENCY_MATRIX.md`
- `MODULE_COMPLETION_MATRIX.md`
- `MODIFIED_FILES_MANIFEST.md`
- `docs/step220/ARCHITECTURE.md`
- `docs/step220/USER_GUIDE.md`
- `docs/step220/ADMIN_GUIDE.md`
- `docs/step220/API_CLI_SDK_GUIDE.md`
- `docs/step220/SCIENTIFIC_METHODS.md`
- `docs/step220/SECURITY_AND_OFFLINE_GUIDE.md`
- `docs/step220/RELEASE_NOTES_STEP220.md`
- `docs/step220/INSTALLATION_AND_WINDOWS_GUIDE.md`
- `docs/step220/OFFLINE_AND_DEPENDENCY_GUIDE.md`
- `docs/step220/DATA_INGESTION_GUIDE.md`
- `docs/step220/WORKFLOW_GUIDE.md`
- `docs/step220/SCIENTIFIC_MODULE_GUIDE.md`
- `docs/step220/DISCOVERY_RECOMMENDATION_EVIDENCE_VALIDATION_GUIDE.md`
- `docs/step220/SYNTHETIC_DATA_GUIDE.md`
- `docs/step220/API_GUIDE.md`
- `docs/step220/CLI_GUIDE.md`
- `docs/step220/TROUBLESHOOTING_GUIDE.md`
- `docs/step220/RESEARCH_USE_DISCLAIMER.md`

No legacy source file was deleted as part of Step220. Temporary verification artifacts and runtime caches are excluded from release archives.
## Full-screen responsive shell correction

Validation date: `2026-07-23`

Modified:

- `src/biointel/ui/theme.py`
- `pages/270_Discovery_Lab_Platform.py`
- `MODIFIED_FILES_MANIFEST.md`

Added:

- `src/biointel/ui/responsive_layout.css`
- `tests/test_fullscreen_responsive_layout.py`
- `FULLSCREEN_LAYOUT_FIX_REPORT.md`
- `RESPONSIVE_UI_TEST_CHECKLIST.md`

The Discovery page change removes only its conflicting page-local mobile CSS. No application feature, scientific data, model, report, page, or navigation item was deleted.
## Live Workspace Windows backup correction

Validation date: `2026-07-23`

Modified:

- `src/biointel/live_workspace_v210/backup.py`
- `tests/test_step211_live_workspace_peak.py`
- `MODIFIED_FILES_MANIFEST.md`

The automatic SQLite backup now explicitly closes source and snapshot connections before cleanup, uses collision-safe per-operation temporary and archive names, retries transient Windows atomic-publish locks, and treats locked stale-backup cleanup as best effort. Regression checks passed for same-timestamp backups, simulated `WinError 32`, temporary-file cleanup, SQLite integrity, and archive checksums. No application feature or user data was removed.
## Live Workspace Streamlit fragment correction

Validation date: `2026-07-23`

Modified:

- `src/biointel/live_workspace_v210/ui.py`
- `tests/test_step211_live_workspace_peak.py`
- `MODIFIED_FILES_MANIFEST.md`

The auto-refreshing presence fragment is now invoked inside the Streamlit sidebar context and creates its expander within the fragment-owned container. This follows the Streamlit 1.58 fragment/sidebar contract and prevents `FragmentHandledException: Fragments cannot write widgets to outside containers`. AppTest verified the sidebar expander, two text inputs, and activity selector with zero exceptions. No collaboration feature was removed.
## Nested DataFrame visual normalization correction

Validation date: `2026-07-23`

Modified:

- `src/biointel/ui/domain_visual_peak.py`
- `tests/test_step136_non_ai_visual_peak.py`
- `MODIFIED_FILES_MANIFEST.md`

The shared visual suite now replaces infinite values only in numeric columns. Object columns containing nested DataFrames or other structured scientific results are preserved and are no longer compared against scalar infinity values, preventing the recorded `ValueError: The truth value of a DataFrame is ambiguous` across Home, Bioinformatics, Studio, Connected Data Explorer, and Wet-Lab pages. Five selected visual tests passed, including all visual-family generation and the nested-DataFrame regression. No scientific result or feature was removed.
## Wet-Lab one-to-one mapping crash correction

Validation date: `2026-07-23`

Modified:

- `src/biointel/biotech/lab_schema.py`
- `pages/64_Wet_Lab_Biotechnology.py`
- `tests/test_step62_lab_analytics_coverage.py`
- `MODIFIED_FILES_MANIFEST.md`

A shared mapping-readiness guard now requires every mandatory canonical field and a unique source column for every selected field before qPCR, ELISA, enzyme, or bioprocess analysis starts. Invalid duplicate selections remain visibly blocked by the existing scientific schema error instead of reaching `apply_column_mapping` and crashing the Streamlit page. Compilation and focused complete/missing/duplicate mapping tests passed across all four workflows. No validation rule or assay feature was removed.
## Windows background-worker lifecycle correction

Validation date: `2026-07-23`

Modified:

- `src/biointel/step101/background.py`
- `tests/test_step105_windows_upload_hotfix.py`
- `MODIFIED_FILES_MANIFEST.md`

The worker launcher now closes its parent-side binary log handle immediately after process creation, preventing handle accumulation and persistent Windows log locks across automatic restarts. Startup also requires the new worker identity to register with the local queue within the existing bounded window; a merely alive but unregistered PID can no longer be reported as ready. Focused launch and timeout regressions passed without starting a real process. No queued job, worker feature, or recovery behavior was removed.
## Native visual-workbench regression classification correction

Validation date: `2026-07-23`

Modified:

- `tests/test_step136_non_ai_visual_peak.py`
- `MODIFIED_FILES_MANIFEST.md`

The visual regression classifier now recognizes the Neuro CNS Studio, advanced feature centers, Synthetic/Demo workspace, and Discovery Lab Platform as native visual workbenches. This prevents false "missing visual hook" failures while preserving their dedicated renderers and scientific workflows. All six no-argument visual-peak regression tests passed. No runtime feature, page, data, or scientific workflow was removed.
## Current-release Windows control correction

Validation date: `2026-07-23`

Modified:

- `src/biointel/release_readiness_v216.py`
- `scripts/diagnose_windows_step206.py`
- `scripts/ultimate_acceptance_step206.py`
- `DIAGNOSE_WINDOWS.bat`
- `RUN_ULTIMATE_ACCEPTANCE_WINDOWS.bat`
- `SAFE_MODE_WINDOWS.bat`
- `UNINSTALL_BIOINTEL_WINDOWS.bat`
- `tests/test_step203_windows_python_startup.py`
- `tests/test_step216_release_readiness.py`
- `tests/test_ultimate_professional_release.py`
- `MODIFIED_FILES_MANIFEST.md`

The retained compatibility-named Windows controls now validate and report the current Step220/V20.3 contract, markers, manifest, managed install directory, diagnostic output, and acceptance evidence. This prevents diagnostics from silently validating legacy Step206 artifacts and prevents ultimate acceptance from switching to an older managed Step206 installation when Step220 is the active package. Stale Step203 and Step216 assertions now verify the current contract without weakening Python, package, or qualification checks. No runtime feature, user data, scientific workflow, or legacy compatibility entrypoint was removed.
## Restricted-Windows inference and support-control correction

Validation date: `2026-07-23`

Modified:

- `src/biointel/dti/predictor.py`
- `src/biointel/engineering/quality_gates.py`
- `src/biointel/engineering/repository_audit.py`
- `scripts/step206_support_bundle.py`
- `CREATE_STEP206_SUPPORT_BUNDLE_WINDOWS.bat`
- `VERIFY_STEP216_RELEASE_READINESS_WINDOWS.bat`
- `RUN_BOTH_WINDOWS.bat`
- `RUN_BIOINTEL_PATH_SAFE_WINDOWS.bat`
- `tests/test_step16_ml_suite.py`
- `tests/test_step43_final_assurance.py`
- `tests/test_step206_windows_install_run.py`
- `MODIFIED_FILES_MANIFEST.md`

DTI estimator inference now uses one estimator worker under a lock and restores the original estimator configuration after each call, preventing reproducible Windows access-denied failures without changing model features, thresholds, or outputs. The support-bundle compatibility entrypoint now targets Step220 and collects current release markers and reports. Windows root arguments no longer carry a trailing-backslash quote risk, and the path-safe compatibility launcher routes to the current startup contract. Engineering checks now parse UTF-8 BOM Python correctly and distinguish a header-only adversarial safety probe from a complete PEM private-key block. No application feature, model, user data, or scientific workflow was removed.
## Shared module canvas rendering correction

Validation date: `2026-07-23`

Modified:

- `src/biointel/ui/premium_visuals.py`
- `tests/test_step124_premium_visual_system.py`
- `MODIFIED_FILES_MANIFEST.md`

The shared module hero now emits one continuous HTML fragment, preventing an empty optional chip row from ending Streamlit's raw-HTML block and exposing the remaining SVG canvas and workflow markup as Markdown code. Live browser checks confirmed rendered SVG artwork and workflow ribbons with no raw hero code or browser errors, and the registered-module audit passed for all 272 modules. No module, canvas, workflow, scientific feature, or user data was removed.
## Windows worker cold-start handshake correction

Validation date: `2026-07-23`

Modified:

- `src/biointel/step101/background.py`
- `scripts/background_job_worker.py`
- `tests/test_step105_windows_upload_hotfix.py`
- `MODIFIED_FILES_MANIFEST.md`

The background worker now publishes a lightweight `starting` heartbeat before importing the full scientific job stack, and the shared launcher allows a bounded 60-second cold-start window while still requiring the exact worker identity to reach `online`. This removes the intermittent 10-second installer and `RUN_BOTH_WINDOWS` false failure seen under cold Windows imports or security scanning without weakening readiness. Three complete worker/API/UI smoke cycles, graceful cleanup, the Windows install/run verifier, Python compilation, and the focused regression passed. No queue, job, scientific feature, project data, or strict readiness check was removed.