# BioIntel AI Step 196 V7 — Historical Changelog

> Superseded by the current Step 196 V8 four-part release. Retained for release provenance only.

Version 15.3.0 · Windows-first local release · four-part delivery.

## Delivery and installation

- Rebuilt the active delivery contract from temporary five parts to exactly four matching ZIP parts.
- `INSTALL_WINDOWS.bat` now performs source-manifest, part-marker, dependency-lock and offline-wheelhouse checks before it changes the environment.
- CPython **3.11.9 x64 exactly** is required by the batch launcher, installer and runtime launcher; failures use a friendly instruction rather than a Python traceback.
- The installer creates `%LOCALAPPDATA%\BioIntelAI`, writes an active-release record and refreshes **BioIntel AI.lnk** on the current Desktop to point at the extracted current release.
- Added a native branded Windows `.ico` asset for the managed shortcut.
- The package builder now allocates and verifies four parts correctly, regenerates the flat SHA-256 manifest, ignores SQLite `-wal`/`-shm` runtime sidecars and checks CRC, unsafe paths, duplicates and cross-part completeness.

## Startup, recovery and local safety

- Added current-name runtime entrypoints: `run_biointel_step196_runtime.py` and `step196_runtime_preflight.py`; legacy internals remain only as compatibility shims.
- Removed console traceback dumping from active launch failures. Local diagnostic paths remain available without claiming data recovery or silently deleting project data.
- Launching a current release no longer opens a running session from a different extracted release. It asks the user to stop that release first.
- Added a **Runtime control** tab in Installation & Recovery Center with a guarded Stop local BioIntel services action. It refuses cross-release shutdown and tolerates corrupt runtime-state PID fields.
- Hardened installer/launcher lock release so a process cannot delete a lock file that a later process has replaced.

## Navigation and global UI

- Curated the 17 formerly auto-discovered page records. All 262 page files are now explicitly represented in the 263-entry catalogue (including Home), with no `Unclassified` fallback pages.
- Added session-preserving Back and Forward controls in the module Navigate panel, while retaining category-based previous/next movement.
- Replaced visible emoji module icons in Command Center and Module Catalogue cards with the existing branded SVG icon system; page links use plain accessible labels.
- Preserved the source theme catalogue: 55 available themes (including the established set) and all 11 font options.

## Release records and scientific boundaries

- Updated current release notes, active metadata and installer language to V7/four-part status. The V5 four-part report is explicitly marked historical provenance.
- Kept demo/reference data visibly separate from real inputs and retained existing scientific/clinical/regulatory boundary language.
- No clinical certification, licensed database access, prospective validation, wet-lab validation or regulatory approval is claimed by this release.

## Protected modules

These source pages were not modified:

- DTI Predictor
- DTI Validation Evidence Center
- LIMS / ELN / Sample Chain of Custody
- Lab Instrument Import Center
- Instrument Integration Hub
