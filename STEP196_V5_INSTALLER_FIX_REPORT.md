# Historical Step 196 V5 — Installer and Online AI Reliability Fix

> Historical provenance record only. It describes the earlier four-part V5
> package and is **not** an installation instruction for the active Step 196
> V7 four-part release. Use `CURRENT_RELEASE.md`, then run only
> `INSTALL_WINDOWS.bat` followed by `RUN_BOTH_WINDOWS.bat`.

## Fixed root causes

1. The pre-install contract no longer imports pandas or the scientific module graph. It is standard-library-only.
2. Scientific imports and mandatory module tests run only after the offline `.venv` has been created.
3. Installer concurrency uses an OS-owned file lock instead of PID age/liveness heuristics.
4. A crashed installer automatically releases the OS lock; leftover lock files do not block installation.
5. Ollama installation and model pull run after core installation in a non-blocking background worker.
6. Ollama/SearXNG setup warnings do not invalidate the core BioIntel installation.
7. The package uses four matching ZIP parts and the normal two-step workflow.

## User workflow

1. Extract all four matching ZIP files into one new empty parent folder.
2. Open `BioIntel-AI-Step196-ONLINE-FINAL-V5`.
3. Run `INSTALL_WINDOWS.bat`.
4. Run `RUN_BOTH_WINDOWS.bat`.

The application can start while the optional Ollama model continues downloading. Progress is written to the UserData runtime log.
