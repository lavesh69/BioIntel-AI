# BioIntel Education Windows Qualification

Date: 2026-07-28

## Supported launch paths

- Existing project Streamlit launcher remains unchanged.
- `SEED_EDUCATION_DEMO_WINDOWS.bat` uses `%~dp0`, supports paths containing spaces, prefers `.venv\Scripts\python.exe`, and falls back to `python`.
- `RESET_EDUCATION_DEMO_WINDOWS.bat` uses the same quoted-path behavior.
- Both batch files return the Python command exit code.

## Verified Windows behavior

- Source archives with a user path containing spaces were inspected and assembled safely.
- Seed/reset CLI paths containing spaces passed automated tests.
- Streamlit 1.58.0 loaded all four Education pages.
- The isolated demo database passed SQLite integrity checking.
- Native `.streamlit/config.toml` parsed successfully.
- A hidden local Streamlit server started on Windows, rendered in the in-app browser, and was stopped by its exact recorded PID after QA.

## Data path priority

1. `BIOINTEL_USER_DATA_DIR` when explicitly configured.
2. Existing legacy `<project>/UserData` when a prior Education database exists.
3. `%LOCALAPPDATA%\BioIntelAI\UserData` for a new installation.
4. Legacy project-local fallback when LocalAppData is unavailable.

The Streamlit pages and Education FastAPI router now use the same resolver.