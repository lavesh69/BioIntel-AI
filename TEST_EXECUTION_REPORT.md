# Test Execution Report

Release: `15.6.0-Step220.0-WINDOWS-V20.3`
Execution date: 2026-07-23
Runtime: managed BioIntel CPython 3.11 on Windows

## Passed verification

| Check | Result |
|---|---|
| Full `src`, `pages`, Step220 test, and `app.py` compile | Passed |
| Dedicated Step220 unittest suite | 6/6 passed in 12.916 seconds |
| Clean synthetic scenarios through production engine | 18/18 passed |
| Controlled-failure synthetic scenarios through production engine | 18/18 passed; one expected failed run captured, other scenarios completed with QC findings |
| SQLite schema/integrity/foreign keys/audit chain | Passed, schema version 220 |
| Lifecycle stage gates and conflict behavior | Passed |
| Ingestion schema, duplicate, corrupt ZIP, spaces/Unicode path, traversal checks | Passed |
| Workflow DAG topological order and cycle rejection | Passed |
| PBKDF2 account, session validation/revocation, redaction | Passed |
| Model artifact hashing and two-model comparison | Passed |
| Report rendering | PDF, DOCX, HTML, XLSX, CSV, JSON, reproducibility ZIP passed |
| FastAPI isolated routes | Catalog, synthetic generation, production analysis, and typed 404 passed |
| Root FastAPI import | 311 total routes; 59 Step220 platform routes passed |
| Root CLI delegation | Catalog, project create, and project list passed |
| Python SDK local mode | Project list/create passed |
| Catalog/navigation integrity | 18 modules, 19 stages, 272 catalog entries, Step220 page registered |
| Streamlit AppTest | 7/7 workspace views passed without app exceptions |
| Desktop responsive browser | 1440x900, no horizontal overflow, no console errors |
| Mobile responsive browser | 390x844, document width 390, sidebar collapsed, no console errors |
| Placeholder/filler/fake-citation/patch-artifact scan | 50 Step220 text/code files scanned, no findings |

## Packaging verification

Final ZIP CRC, cross-part uniqueness, exact file-union, byte size, and SHA-256 checks are performed after this in-tree report is frozen. Results are written beside the five archives in `BioIntel-AI-15.6.0-Step220-WINDOWS-V20.3-5PART-MANIFEST.json` and the packaging validation report.

## Environment notes

The managed runtime does not include `pytest`, so the dedicated Step220 regression file uses the Python standard-library `unittest` runner. Historical pytest-style suites were syntax-compiled but not executed by this runtime during this pass. Existing Step219 tests and prior release reports remain preserved.

Nineteen external executables were not present on PATH (`Rscript`, aligners, variant tools, microbiome profilers, mass-spectrometry converters, FastQC/MultiQC, and related tools). They are optional and are reported by the Dependency Manager; their absence was not represented as successful external execution.
