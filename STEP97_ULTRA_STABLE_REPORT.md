# Step 97 Ultra-Stable Reliability, Upload and UI Optimization Report

## Scope

BioIntel AI Step 96 was upgraded to version 9.7.0 with a focused reliability program covering upload handling, model imports, startup, runtime crash recovery, expensive reruns, UI responsiveness and transactional Windows installation.

## Implemented fixes

### Universal upload reliability

A shared parser now handles:

- CSV, TSV, TXT, TAB and MAF
- gzip-compressed CSV/TSV/TXT/MAF
- XLSX, XLSM, XLS and ODS
- ZIP archives containing exactly one supported table

Controls include encoding fallback, delimiter detection, duplicate headers, malformed row rejection, archive path safety, member and decompression limits, compression-ratio checks, maximum columns and maximum interactive cells. Bad rows are never silently skipped.

### Model reliability

- Missing models raise a BioIntel `ModelNotFoundError` rather than a raw filesystem exception.
- Corrupt or incompatible artifacts return a clear schema/compatibility error.
- PPI model export uses a manifest-bound ZIP package with SHA-256 verification.
- Raw legacy Joblib loading is disabled unless a user explicitly marks a trusted local file.
- Expensive model deserialization is deferred until the user requests analysis.

### Performance and smoothness

- System Diagnostics quick mode uses dependency discovery instead of importing every scientific package.
- Release Readiness and Evidence Package pages no longer trigger full model/dependency diagnostics during every render.
- Multi-Omics, External Validation and Audit/Release operations execute only after an explicit run action.
- Streamlit development file watching is disabled for the packaged desktop runtime.
- Startup chooses a free local port and validates UserData, disk, version and core dependencies first.

### Runtime recovery

- Uncaught page errors remain converted to a safe user-facing reference ID.
- Full local diagnostics are written under persistent UserData.
- Tokens, passwords and common secret fields are redacted from stored messages and tracebacks.
- Runtime report retention is bounded to 200 files / 50 MB.

### Windows installation

- Four ZIP parts are verified against hashes embedded in the single auto-installer.
- Python 3.11 x64 is discovered or prepared through the official Python Software Foundation installer with Authenticode validation.
- Extraction uses a short staging path.
- Activation is transactional and preserves an exact SHA-256 UserData backup.
- Environment installation, wheelhouse verification and post-install self-test must pass before completion.
- Failed activation invokes rollback automatically.

## Qualification results

| Check | Result |
|---|---:|
| Product version | 9.7.0 |
| Python files compiled | 682/682 |
| Focused/regression tests | 57 passed |
| Streamlit pages default-loaded | 111/111 |
| Main app default-loaded | Passed |
| Source reliability self-test | 7/7 passed |
| SQLite databases | 23/23 healthy |
| Indexed database rows | 107,477 |
| Offline wheelhouse | 102/102 verified |
| Advanced tools retained | 44 |
| Model files retained | 25 |

## Remaining external validation

The build environment is Linux with supported Python 3.13 for source qualification. The shipped Windows installer is strict about Python 3.11 x64, matching the bundled Windows wheelhouse. A clean physical Windows 10 and Windows 11 installation run, code-signed EXE/MSIX production packaging, third-party command-line tool licensing, reference database downloads and independent scientific/clinical evidence remain external release activities and are not fabricated by this report.
