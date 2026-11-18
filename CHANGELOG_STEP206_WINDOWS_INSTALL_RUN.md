# Step206 Windows Install and Run Changelog

## Managed installation

- Installs the verified application into `%LOCALAPPDATA%\BioIntelAI\App\Releases\15.6.0-Step206` instead of depending on the extracted download folder.
- Copies into a staging release, verifies SHA-256 integrity, and activates atomically with rollback of an invalid prior target.
- Preserves user projects and evidence under `%LOCALAPPDATA%\BioIntelAI\UserData`.
- Backs up UserData SQLite databases and migrates known release-local job, API-security, tenant, cache and biotechnology-run databases after a clean shutdown.
- Stops a verified older runtime before taking a timestamped SQLite backup and changing the active release.
- Refreshes stable Desktop and Start Menu Start/Stop/Restart shortcuts and removes managed stale BioIntel shortcuts.

## Python and dependencies

- Requires exact CPython 3.11.9 x64 and reports a friendly error instead of a traceback.
- Prefers a packaged or cached official Python installer, validates its Windows signature, and otherwise uses the existing official-download fallback.
- Installs scientific dependencies from the bundled SHA-256-verified offline wheelhouse once Python is available.
- Reuses a healthy environment and rolls back to the previous environment if rebuilding fails.

## Startup and recovery

- Adds a resident supervisor for Streamlit UI, FastAPI, and the background worker.
- Adds a blocking Streamlit `AppTest` home-page execution gate to catch redacted app exceptions before shortcut activation.
- Uses exact HTTP 200/version checks, Streamlit health, a local SQLite read/write probe, and worker heartbeat before declaring the app ready.
- Adds bounded automatic restart recovery and crash-loop protection.
- Changes ports and retries after a process or port failure.
- Cleans up UI, API, and worker processes after any startup failure.
- Adds graceful Stop and Restart controls, duplicate-start prevention, legacy-runtime handoff, browser fallback URL, clipboard copy, logs, and status reports.
- Adds sanitized automatic support bundles without project datasets, uploaded biomedical files, evidence packages, workspace files, or database contents.
- Runs a blocking native Windows startup/shutdown smoke test during installation before shortcuts are activated.

## Compatibility and scope

- The supported non-technical workflow remains `INSTALL_WINDOWS.bat` followed by `RUN_BOTH_WINDOWS.bat`.
- The current physical delivery is four matching ZIP parts; installer, runner, manifests, diagnostics and release gates require all 5/5 markers.
- Historical Step196 launcher filenames remain as thin compatibility delegates to Step206.
- DTI, LIMS/ELN, Lab Instrument Import, and Instrument Integration protected modules were not modified.
- Optional Ollama, SearXNG, and provider services remain isolated from core offline install and launch.
