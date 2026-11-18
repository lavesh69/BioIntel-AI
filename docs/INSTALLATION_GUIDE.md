# BioIntel AI 15.6.0 Step206 Windows Installation Guide

## Supported release workflow

1. Keep all five matching `ULTIMATE-PROFESSIONAL-WINDOWS-V19.6-5PART` ZIP files together.
2. Verify them against `SHA256SUMS.txt` when available.
3. Extract all five archives into the same new empty folder. The common `BioIntel-AI-15.6.0-Step206-WINDOWS-V19.6` directory must merge.
4. Run `INSTALL_WINDOWS.bat` as the current Windows user. Administrator rights are not required for the normal LocalAppData installation.
5. Wait for source integrity, wheelhouse, dependency, import, Streamlit, API, worker and native Windows smoke gates to finish.
6. Run `RUN_BOTH_WINDOWS.bat` or the **BioIntel AI** Desktop/Start Menu shortcut.
7. Run `RUN_ULTIMATE_ACCEPTANCE_WINDOWS.bat` for final target-machine software evidence.

The installer requires compatible 64-bit CPython 3.11.x. If it is absent, the controlled Python preparation route is offered. The default dependency installation uses the bundled Windows wheelhouse; `INSTALL_WINDOWS_ONLINE_FALLBACK.bat` is a separate verified fallback.

## Managed locations

- Application: `%LOCALAPPDATA%\BioIntelAI\App\Releases\15.6.0-Step206`
- Projects, settings, reports and local databases: `%LOCALAPPDATA%\BioIntelAI\UserData`
- External tools: `%LOCALAPPDATA%\BioIntelAI\Tools`
- Reference assets: `%LOCALAPPDATA%\BioIntelAI\ReferenceAssets`
- Logs: `%LOCALAPPDATA%\BioIntelAI\UserData\runtime_logs`

Application replacement and user data are deliberately separated. Upgrade or repair does not delete projects, reports, settings or local databases. Known SQLite stores are backed up before migration.

## Lifecycle controls

- `RUN_BOTH_WINDOWS.bat` starts the supervised UI, API and background worker.
- `STOP_BIOINTEL_WINDOWS.bat` requests graceful shutdown and verifies owned child processes before any forced cleanup.
- `RESTART_BIOINTEL_WINDOWS.bat` stops then restarts the active managed release.
- `REPAIR_WINDOWS.bat` deep-verifies the Step206 source and performs a rollback-capable environment repair.
- `DIAGNOSE_WINDOWS.bat` creates a machine-readable diagnostic report and sanitized support bundle; add `/deep` for full source hashing.
- `SAFE_MODE_WINDOWS.bat` starts local-only, offline, low-memory mode with optional external engines disabled.
- `UNINSTALL_BIOINTEL_WINDOWS.bat` requires explicit typed confirmation and preserves UserData.

## Space and Unicode paths

All supported batch and Python entry points quote paths and use LocalAppData-managed short runtime paths. The diagnostic tool performs a real spaces-and-Unicode round trip. If this check fails, use `DIAGNOSE_WINDOWS.bat` and review security software or filesystem policy before analysis.
