# BioIntel AI 15.6.0 Step206 V19.6 — Professional Hardening Report

This build is a non-destructive hardening release. No module or product feature was removed. Existing scientific safety boundaries and fail-closed release controls remain intact.

## Completed improvements

- Reconstructed and CRC-validated all five source archives before editing.
- Corrected a missing subprocess import in raw-read metagenomics timeout handling.
- Added deterministic multivariable Cox regression fallback behavior when the optional Statsmodels runtime is unavailable.
- Repaired legacy H5AD observation metadata recovery for older AnnData/HDF5 layouts.
- Regenerated all 47 declared module starter-kit ZIPs and validated their manifests.
- Rebuilt all 80 synthetic module-demo bundles; the previously empty Strain-Resolved Microbiome input is now valid and reproducible.
- Promoted BioIntel Live Workspace and Engine Control Center into the primary navigation, role, workflow and home-page discovery paths.
- Preserved the complete legacy scientific-review experience inside a cleaner progressive-disclosure workspace.
- Added consistent theme/bootstrap behavior to Engine Control Center and safe handling for missing page links.
- Added temporary-upload cleanup to the engine-pack workflow.
- Migrated 62 UI source files from deprecated Streamlit width APIs and replaced deprecated HTML component embeds.
- Synchronized desktop, mobile and CodeMeta release identities to 15.6.0.
- Regenerated portable desktop dependency locking and repaired invalid mobile lock metadata; private build-registry URLs were removed.
- Excluded development-only `node_modules` trees from source manifests and release ZIPs.
- Restored Step160 and Step161 legacy extraction compatibility markers in the current four-part packager.

## Verification summary

- Python syntax compilation: passed across app, pages, source and scripts.
- Critical Ruff checks (`E9`, `F63`, `F7`, `F82`): passed.
- Current backend, API, scientific, module, Windows, Live Workspace, Engine Platform and Neuro regression set: 321 passed.
- Streamlit UI static validation: 269/269 pages passed.
- Streamlit AppTest: 538/538 static and runtime checks passed, zero page exceptions.
- Module starter kits: 47/47 available.
- Portfolio demo bundles: 80/80 ready.
- Desktop clean dependency install: passed.
- Mobile clean dependency install, TypeScript check and production Vite build: passed.
- Production dependency audit: zero reported vulnerabilities for desktop and mobile runtime dependencies.

## Supported Windows workflow

1. Extract all four matching ZIP parts into one folder.
2. Run `INSTALL_WINDOWS.bat`.
3. Run `RUN_BOTH_WINDOWS.bat`.

The managed Windows runtime remains pinned to 64-bit CPython 3.11.9. External scientific engines, licensed reference databases, real cohorts, instruments, independent validation and regulatory approval remain separately qualified inputs; synthetic demos do not claim those forms of evidence.
