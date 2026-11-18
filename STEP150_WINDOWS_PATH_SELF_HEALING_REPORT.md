# Step 150 — Windows Path Self-Healing & Mixed-Extraction Protection

## Root cause

The WinError 123 startup failure was introduced in Step 145 by passing the batch directory as a quoted standalone argument:

```bat
--root "%~dp0"
```

`%~dp0` ends with a backslash. On the affected Windows command-line path the closing quote could survive as filename text, creating a malformed destination such as:

```text
BioIntel-AI"\reports
```

The same launcher/preflight pair was inherited by Steps 146, 147 and 148. Step 136–144 did not contain this exact defect.

The Step 149 archives contain corrected files, but the user screenshot shows an extracted folder still running the Step 145 title and the old 34-line preflight. That proves the folder was mixed, partially extracted, or Windows extraction skipped existing files.

## Step 150 fixes

- Relative `--root "."` startup contract.
- `pushd`-based project-root handling.
- Python-side quote-residue repair for CLI and path environment variables.
- Four ZIP-part sentinel checks.
- SHA-256 verification of critical launcher, installer and preflight files.
- Refusal to run stale Step 145 files.
- Self-healing hotfix for already extracted Steps 145–149.
- Clean four-part extractor/installer to prevent mixed folders.
- Safe report fallback to LocalAppData/temp when the project reports directory is unavailable.

## Verification completed

- Historical archives scanned: 84 across Steps 136–149.
- Focused Step 145–150 tests: 44 passed.
- Step 149–150 path tests: 10 passed.
- Python compilation: 1,098 files, 0 failures.
- SQLite databases: 40/40 healthy.
- Database rows inspected: 108,493.
- Foreign-key violations: 0.
- Source installation validator: passed.

## Usage

For an existing affected folder, extract and run:

```text
APPLY_STEP150_REPAIR_AND_RUN.bat
```

For a clean installation, keep the four Step 150 ZIPs and `EXTRACT_INSTALL_RUN_STEP150_WINDOWS.bat` in one folder, then run the extractor.
