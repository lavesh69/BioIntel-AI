# BioIntel AI Step 196 V8 — Changelog

> Superseded by the current Step 196 V9 four-part release. Retained for release provenance only.

Version 15.3.0 · Windows-first local release · four ZIP parts.

## Safe scientific uploads

- Set the normal scientific-upload ceiling to **1 GB per file** across the reusable upload workflow.
- Files above the 100 MB interactive boundary are stream-hashed, atomically staged to local storage and queued for bounded background inspection rather than copied into an interactive dataframe.
- Retained the original constrained behaviour of the protected DTI Predictor and Lab Instrument Import modules.
- Added streamed local-dossier persistence for Clinical & Pharmaceutical Validation artifacts, including model freeze, blinded predictions, outcomes, analysis, evidence and training files.
- Extended the clinical registry so analysis, evidence and training hashes can be computed from a staged file path without loading a large artifact into RAM.
- Audited all 54 page files that use uploads (108 controls): every one now has shared preflight or an explicit bounded streaming/staging path.

## Scientific canvas and recovery UX

- Replaced the debugger-style JSON walls shown in the supplied screenshots with operational canvases: compact metrics, workflow stages, readable fact tables and a collapsed redacted technical view.
- Applied the canvas to the shared Step 188, 189 and 190 lifecycle renderers, qualification/release centers, native-data viewers, linked-viewer details and module workspace diagnostics.
- Raw host paths, long hashes, secrets and nested payloads are compacted or redacted before display.
- Error paths in the clinical validation upload flow now show a clear local action message rather than surfacing an unhandled Streamlit error screen.

## Release and integrity

- Release revision is now **V8-4PART** while the software version remains **15.3.0** everywhere it is already the current source identity.
- The installer and run launcher remain the only user workflow: `INSTALL_WINDOWS.bat`, then `RUN_BOTH_WINDOWS.bat`.
- The installer continues to perform integrity/preflight checks internally, requires CPython 3.11.9 x64 with a friendly message, supports paths with spaces and refreshes the current-release Desktop shortcut.

## Scientific boundary

- Streamed files, checksums, background inspection and local workflows are implemented software capabilities. They do not constitute clinical certification, regulatory approval, licensed-data access, wet-lab validation or external scientific evidence.

## Protected modules

The following source pages were preserved byte-for-byte from the uploaded canonical archive:

- DTI Predictor
- DTI Validation Evidence Center
- LIMS / ELN / Sample Chain of Custody
- Lab Instrument Import Center
- Instrument Integration Hub
