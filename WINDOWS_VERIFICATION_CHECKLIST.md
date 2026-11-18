# Windows Verification Checklist

Release: `15.6.0-Step220.0-WINDOWS-V20.3`

- [x] Managed Python 3.11 runtime imports the platform package.
- [x] Full source tree compiles with `compileall`.
- [x] FastAPI root application imports with the Step220 router.
- [x] `biointel research-platform --help` executes.
- [x] Local SDK project create/list operations execute.
- [x] Streamlit Discovery Lab page runs at desktop and 390 px mobile widths without horizontal overflow.
- [x] Paths containing spaces and a Unicode directory component pass ingestion tests.
- [x] Path traversal and unsafe archive members are blocked.
- [x] SQLite quick check, foreign-key check, schema version, and audit-chain verification pass.
- [x] All 18 clean and 18 controlled-failure synthetic scenarios execute through production analyses.
- [x] PDF, DOCX, HTML, XLSX, CSV, JSON, and reproducibility ZIP reports render.
- [x] Five release ZIP parts pass CRC checks and cross-part duplicate/missing-file validation.
- [x] SHA-256 hashes and byte sizes are recorded in the release manifest.

External executables are checked by the dependency manager and may remain unavailable in a minimal offline installation.
