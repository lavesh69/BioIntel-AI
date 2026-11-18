# BioIntel AI Step 158 — Release Surface Hardening

## Purpose

Step 158 removes ambiguity between the current product release and the large historical engineering archive. It does not replace Step 157 scientific or regression work; it hardens how users, installers and diagnostics identify and verify the current package.

## Completed improvements

- Replaced the stale Step 126 root README with an accurate Step 158 guide.
- Added `CURRENT_RELEASE.md` as the single human-readable current-release source.
- Added `STEP158_RELEASE.json` as the machine-readable release source.
- Added `VERIFY_LATEST_WINDOWS.bat` so users no longer need to know a step-specific verifier name.
- Added `RUN_RELEASE_DOCTOR_WINDOWS.bat` and `scripts/step158_release_doctor.py`.
- Added SQLite integrity, runtime-residue, version, entry-point and stale-document checks.
- Preserved historical reports and verifiers for traceability while clearly separating them from current entry points.
- Added automated tests that fail if current-facing documentation becomes stale again.

## Inherited Step 157 baseline

- 229/229 Streamlit screens qualified.
- 1,315 tests passed, 27 environment-gated tests skipped, 0 failed.
- 80 scientific profiles and 49 native workflow families.
- 76 registered specialist engines and 78 protected execution plans.
- 40 release SQLite databases healthy with no foreign-key violations.

## Boundary

This release hardens internal software and release communication. It does not create external clinical, regulatory, licensed-data, physical-instrument or wet-lab evidence.
