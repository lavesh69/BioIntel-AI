# Step 149 — Windows Startup Path Safety & Stability Repair

## Root cause confirmed

The Windows launcher introduced in Step 145 passed the project directory as:

```bat
--root "%~dp0"
```

`%~dp0` always ends with a backslash. When that backslash is immediately before the closing command-line quote, Python can receive an unmatched trailing quote. The project root therefore became a value such as:

```text
C:\Users\...\BioIntel-AI"
```

The preflight then attempted to create:

```text
BioIntel-AI"\reports
```

and Windows raised `WinError 123`.

## Historical audit

- Step 136–144 packages: this exact dangerous launcher argument was not present.
- Step 145: the defect was introduced in `RUN_BOTH_WINDOWS.bat`.
- Step 146–148: the same cumulative launcher defect was inherited.
- ZIP parts inspected: 80.
- Confirmed dangerous occurrences: 4.

## Repairs in Step 149

1. `RUN_BOTH_WINDOWS.bat` now changes into the application directory with `PUSHD` and passes `--root "."`.
2. `BIOINTEL_PROJECT_ROOT` is set from the normalized current directory rather than raw `%~dp0`.
3. Python-side path normalization removes accidental leading/trailing quote residue.
4. Existing malformed `BIOINTEL_PROJECT_ROOT`, `BIOINTEL_USER_DATA_DIR`, reference, tool and temp path variables are normalized before use.
5. The preflight catches unexpected failures and writes a diagnostic report instead of crashing with an unhandled traceback.
6. If the project `reports` folder is unavailable, the report safely falls back to UserData, LocalAppData or the system temporary directory.
7. A static audit checks every BAT/CMD/PowerShell launcher for this trailing-backslash quote risk.
8. A separate `RUN_BIOINTEL_PATH_SAFE_WINDOWS.bat` launcher is included.
9. A standalone hotfix launcher is supplied for already extracted Step 145–148 folders.

## Verification completed

- Step 136 regression tests: 48 passed.
- Step 137–138 regression tests: 39 passed.
- Step 139–140 regression tests: 26 passed.
- Step 141–149 regression and focused tests: 78 passed.
- Total selected tests: 191 passed, 0 failures.
- Python syntax compilation: 1,096 files passed.
- Current launcher audit: 160 launchers scanned, 0 dangerous findings.
- Historical Step 136–148 ZIP audit: 80 ZIP parts scanned.
- SQLite integrity: 40/40 databases healthy.
- Rows inspected: 108,493.
- Foreign-key violations: 0.
- Malformed root input such as `."` is repaired and preflight completes successfully.

## Remaining external boundary

The screenshot-specific defect is fixed at both launcher and Python layers. A physical Windows 10/11 machine was not available in this Linux build environment, so antivirus, display scaling, Windows policy and machine-specific driver behavior are not claimed as physically certified here.
