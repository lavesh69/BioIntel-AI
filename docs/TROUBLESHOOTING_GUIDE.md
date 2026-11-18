# BioIntel AI Troubleshooting Guide

## Start fails

Run `DIAGNOSE_WINDOWS.bat`. Review the reported JSON file under `%LOCALAPPDATA%\BioIntelAI\UserData\reports` and the sanitized support bundle path. The bundle excludes project datasets, uploaded biomedical files, workspace contents and database contents.

Common recovery sequence:

1. Run `STOP_BIOINTEL_WINDOWS.bat`.
2. Run `SAFE_MODE_WINDOWS.bat` to isolate online providers, LAN hosting and optional external engines.
3. If Safe Mode also fails, run `DIAGNOSE_WINDOWS.bat /deep`.
4. From a freshly extracted set of all five matching ZIPs, run `REPAIR_WINDOWS.bat`.

## Missing Python or wrong version

BioIntel requires exact CPython 3.11.x x64 for the managed Windows environment. Run `INSTALL_PYTHON311_WINDOWS.bat`, then repeat installation or repair. A different Python version is not silently accepted.

## Missing package part or damaged source

Do not combine ZIPs from different builds. Extract all five matching files into a new empty folder. The required `.release_parts\step206_part1.ok` through `step206_part5.ok` markers and source SHA-256 manifest are checked before installation.

## Port conflict or duplicate process

The supervisor chooses free localhost UI ports in 8501–8599 and API ports in 8000–8099. Duplicate starts reuse the healthy existing session. Stale runtime records are cleaned only after PID and application-root checks. Use Stop, then Diagnose, if no free port is available.

## One module fails

The UI runtime guard contains page failures and emits a recovery ID rather than crashing the complete platform. Check the module's registry entry for required engines, reference databases, input formats and limitations. External engines and databases are never reported as bundled merely because an interface exists.

## Large jobs are slow

Use background execution and avoid opening full tables or images when bounded preview is available. Reference databases, whole-slide images, sequencing reads, graph indexes and model weights can require substantial disk/RAM. The Engine Control Center reports runtime availability and qualification separately.

## Repair fails

Repair will not bypass a damaged source gate. Re-extract the five matching release parts and run repair from that verified extraction. Previous verified environments are restored if environment rebuilding fails.
