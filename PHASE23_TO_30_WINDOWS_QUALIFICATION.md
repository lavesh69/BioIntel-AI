# Phase 23–30 Windows Qualification

Target: 64-bit CPython 3.11 on Windows 10/11.

## Verified locally

- Project path contains spaces.
- Diagnostic and database paths containing spaces and Hindi Unicode characters.
- SQLite migration, foreign keys and integrity check.
- Background worker `--once`.
- Two Streamlit pages through Streamlit 1.58 AppTest.
- Online SQLite backup and ZIP inspection.
- Batch scripts preserve `%~dp0`/`%CD%`, quote paths and use `%LOCALAPPDATA%\BioIntelAI\UserData` by default.

## Entry points

- `INSTALL_EDUCATION_PHASE23_TO_30_WINDOWS.bat`
- `EXTRACT_INSTALL_RUN_EDUCATION_PHASE23_TO_30_4PART_WINDOWS.bat`
- `DIAGNOSE_EDUCATION_PHASE23_TO_30_WINDOWS.bat`
- `RUN_EDUCATION_PHASE23_TO_30_WORKER_WINDOWS.bat`
- `RUN_BIOINTEL_MCP_WINDOWS.bat`
- `LOAD_TEST_EDUCATION_PHASE23_TO_30_WINDOWS.bat`
- `BACKUP_EDUCATION_PHASE23_TO_30_WINDOWS.bat`
- `RESTORE_EDUCATION_PHASE23_TO_30_WINDOWS.bat`

## External qualification still required

Real LMS/SSO endpoints, PostgreSQL/Redis/S3 deployment, reverse proxy/TLS, TURN/WebRTC, managed key storage, HA/failover and enterprise antivirus/application-control policies were not present in the local environment.

