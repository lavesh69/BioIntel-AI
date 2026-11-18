# Step220 Windows Install and Run Fix

This maintenance release fixes the supported `INSTALL_WINDOWS.bat` and `RUN_BOTH_WINDOWS.bat` workflow.

## Fixed

- Enforced exact CPython 3.11.x x64 consistently in both entry points.
- Updated Step220 package preflight to require the current four release parts.
- Replaced hard-coded LocalAppData launch paths with the optional `BIOINTEL_APP_HOME` and `BIOINTEL_USER_DATA_DIR` overrides.
- Forced extracted-source launches through the verified stable managed launcher, even when a stale local `.venv` exists.
- Preserved a healthy managed `.venv` across same-version source hotfixes instead of rebuilding all offline dependencies.
- Added space-safe unattended switches: `/no-pause`, `/preflight-only`, and `/no-browser`.
- Changed installation source verification to the deep SHA-256 release gate.
- Prevented browser launch during automated or headless verification.
- Made graceful STOP work when Windows policy denies `tasklist` or CIM command-line inspection, without weakening verified force-kill safeguards.
- Restored the release-owned `biointel.reports` package required by the API, CLI, and report pages.
- Corrected contextual-research startup ordering and missing `asdict` imports in the population genetics and cell atlas pages.
- Kept desktop and Start Menu shortcuts optional so policy-restricted Windows accounts still complete installation and retain stable managed launchers.
- Synchronized the deep source-integrity manifest with the four-part ZIP policy so mutable `reports/*.sqlite3` runtime databases are not required when they are intentionally omitted from the distributable payload.

## Verification

- Full `INSTALL_WINDOWS.bat /no-pause`: exit code 0.
- Managed `RUN_BOTH_WINDOWS.bat /managed /no-browser /no-pause`: exit code 0.
- Streamlit health: HTTP 200 with `ok`.
- API `/health`: `ok`, version `15.6.0`.
- BioIntel Connect `/api/v1/connect/health`: `healthy`.
- Native Windows smoke test: UI, API, database, and worker ready; cleanup completed successfully.

The broader `/ready` endpoint may remain unavailable when optional databases have not been initialized. Core Windows launch readiness is determined by the verified UI, API `/health`, local runtime database, and worker gates.

## R3 Runtime Error and Screen-Pop Hotfix

- Resolved the Home relationship-integrity failure when older project databases do not yet contain optional tables such as `project_resources`; only absent legacy tables or columns are treated as empty, while other SQLite failures still surface.
- Routed Step183-Step193 demo, assurance, execution, and completion artifacts through the managed `BIOINTEL_USER_DATA_DIR` location instead of release-local `UserData` paths.
- Added missing-only installation seeding for versioned demo and assurance assets. Existing user-owned files are never overwritten.
- Changed Step183 portfolio and Step187 page-assurance panels to show a safe repair state when artifacts are absent or incomplete instead of raising `FileNotFoundError`.
- Restored the missing Step187 assurance hook on `17_Local_Data_Manager.py`.
- Changed Desktop and Start Menu launch shortcuts to a hidden `wscript.exe` wrapper and added `CREATE_NO_WINDOW` to Windows runtime fallback commands to prevent one-to-two-second console flashes.

### R3 Verification

- Runtime error families checked: 32 retained reports grouped into 3 root causes and repaired.
- Full Home Streamlit AppTest: passed with 0 exceptions and 0 visible error elements.
- Missing-artifact UI tests: Step183 and Step187 both rendered repair guidance with 0 exceptions.
- Managed asset seed: 11,836 bundled files copied into a clean external UserData test location; second pass preserved existing files.
- Step183 module demo validation: 80/80 passed.
- Step187 page assurance validation: 177/177 passed.
- Windows install/run source contract: 29/29 checks passed, including no-flash launch and managed UserData seeding.
