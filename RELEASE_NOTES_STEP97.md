# BioIntel AI 9.7.0 — Ultra-Stable Reliability & Optimization

Release date: 2026-07-09

## Reliability and crash fixes

- Added one bounded upload pipeline for CSV, TSV, TXT, MAF, gzip, Excel, ODS and safe single-table ZIP inputs.
- Added encoding and delimiter detection, duplicate-header rejection, malformed-row errors, archive traversal protection, decompression limits, column limits and cell-count limits.
- Reworked high-risk upload pages so failed or changed files cannot silently reuse stale results.
- Converted expensive model, validation and evidence operations to explicit run-on-demand actions.
- Added a checksum-bound `.bioippimodel` package for PPI models and blocked unsafe raw Joblib imports by default.
- Added actionable domain errors for missing or corrupt model artifacts.
- Fixed slow governance readiness screens that previously ran full dependency/model diagnostics on every rerun.
- Moved runtime crash reports to persistent UserData, added secret redaction and bounded report rotation.
- Added dynamic local-port selection and startup preflight to prevent launch failures when port 8501 is occupied.

## Smoothness and UI improvements

- Added the Reliability & Optimization Center.
- Reduced unnecessary reruns for Multi-Omics Biomarker Discovery, External Validation and Audit/Release workflows.
- Added upload previews, normalized export, cache recovery, quick health information and support-diagnostic export.
- Disabled development file watching in the installed runtime and bounded interactive upload/message limits.
- Preserved all prior themes, fonts, modules and scientific tools.

## Installation and recovery

- Step 97 uses four SHA-256-verified ZIP parts and one external auto-installer BAT.
- Installation happens in a short staging path before activation.
- Persistent `data`, `reports`, `workspace`, `exports` and `projects` remain separated from application code.
- A complete UserData backup and rollback journal are created before activation.
- The installer validates the 102-wheel offline dependency package and runs a seven-check post-install self-test.
- A dedicated repair launcher can rebuild the local environment from the verified wheelhouse.

## Verification completed

- 682 Python files compiled successfully.
- 57 focused and regression tests passed.
- 111/111 Streamlit page default-load smoke checks passed.
- `app.py` default-load smoke check passed.
- 23/23 discovered SQLite databases passed integrity checks.
- 102/102 offline Windows CPython 3.11 wheels passed manifest, hash and archive validation.
- Seven source self-test checks passed.

## Honest boundary

This release fixes the reproducible source, upload, model-loading, UI-rerun, startup and installer defects exercised during qualification. No software test can prove that every future input, third-party tool, driver or physical Windows configuration will never fail. Final publisher code signing, physical Windows 10/11 certification, licensed external tools, large reference databases and independent scientific/clinical validation remain separate external activities.
