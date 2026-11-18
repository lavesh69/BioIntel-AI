# Step204 Release Test Report

## Scope

Windows installation and startup reliability only. Scientific module behavior was not redesigned. The protected DTI, DTI Validation, LIMS/ELN/Chain of Custody, Lab Instrument Import, and Instrument Integration source files were retained without modification.

## Completed source checks

- All five canonical Step203 ZIP inputs passed ZIP CRC testing before extraction.
- Canonical extraction contained 25,302 unique files with zero duplicate filenames across input parts.
- Python syntax/bytecode compilation passed for `app.py`, `pages`, `scripts`, and `src/biointel`.
- Step204 deep SHA-256 source gate passed.
- Legacy Step196 structural release validation and pre-install contract passed.
- Dependency lock passed: 32 packages, matching lock SHA-256.
- Offline Windows CP311 wheelhouse passed: 102 wheels, zero missing, unexpected, corrupt, unhashed, or hash-mismatched wheels.
- Core imports passed for `biointel` and `biointel.api.main`.
- Focused automated tests passed: 27 tests covering Step204 install/run contract, runtime handover, installer lock recovery, and retained Step202 Neuro/CNS production behavior.
- Static Windows batch/PowerShell contract checks passed for quoted paths, exact CPython 3.11.9 x64 policy, four-part markers, blocking verification, runtime-log creation, shortcut refresh, and optional-service isolation.

## Four-part package and clean-extraction checks

- Final package contains exactly four numbered ZIP files.
- Package verification covered 25,286 source files plus 29 unique release markers.
- Cross-part result: zero missing files, zero extra files, zero duplicate files, zero CRC errors, and zero unsafe archive paths.
- All four parts merged successfully into `BioIntel-AI-15.4.0-Step204-WINDOWS-V17.1`.
- Clean extraction was tested in a folder whose path contains spaces.
- Clean-extracted Step204 deep SHA-256 gate passed.
- Clean-extracted Windows install/run static verifier passed.
- Clean-extracted API import passed and the six Step204 focused tests passed.
- Seventeen protected DTI/instrument/LIMS source files matched the canonical uploaded-source SHA-256 values byte-for-byte.

## Native execution boundary

This build environment is Linux with Python 3.13.5, not Windows. Native execution of `.bat`, PowerShell COM shortcut creation, Python 3.11.9 Windows virtual-environment installation, Streamlit browser launch, and FastAPI/worker process startup must still be confirmed on a real Windows machine. Source and package checks do not replace that target-Windows qualification.
