# BioIntel AI — Milestone 8 Status

## Status

**No-login local edition completed and verified**

## Login removal

- Removed API-key environment variable
- Removed authentication dependency from all FastAPI routes
- Removed authentication headers and sign-in instructions
- Removed authentication configuration from Docker Compose
- Added explicit `no_login_local` health metadata
- Confirmed every API endpoint works without credentials

## Additional Step 8 improvements

- One-click `START_BIOINTEL_NO_LOGIN_WINDOWS.bat`
- Streamlit and FastAPI bound to `127.0.0.1` by default
- Docker ports published only on `127.0.0.1`
- Local Data Manager
- Safe path-constrained file deletion
- Bundled demo models protected from accidental deletion
- Updated documentation and project version `0.8.0`

## Verification performed

- Python compilation: passed
- Pytest: **65 passed**
- Ruff: passed
- Black: passed
- Streamlit AppTest: **19/19 screens passed**
- No-login API health: passed
- Model-status endpoint without credentials: passed
- Sequence-analysis endpoint without credentials: passed
- ZIP integrity verification: passed

## Access model

This release is designed for one user on a local computer. Authentication
is intentionally disabled, so services must remain bound to `127.0.0.1`.
Do not expose ports 8000 or 8501 directly to the public internet.
