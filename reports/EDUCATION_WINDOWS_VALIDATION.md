# Education Windows Validation Report

Environment: Windows, CPython 3.11.9 x64. Final reconstructed release v3 results:

- Four-ZIP reconstruction: 12,574 packaged source files verified; size variance 0.0041%.
- Deep source manifest: 12,573 tracked files, zero mismatches.
- Offline wheelhouse: 121/121 locked wheels; no missing, unexpected, corrupt or hash-mismatched wheel.
- Full `INSTALL_WINDOWS.bat /no-pause`: exit 0. Managed staging, dependency install, migrations and post-install verification passed.
- Native installer-blocking smoke: UI HTTP, API version/database health, worker readiness and graceful cleanup passed.
- Direct `RUN_BOTH_WINDOWS.bat /managed /no-browser /no-pause`: exit 0; API `/health` 200; Streamlit `/_stcore/health` 200.
- `STOP_BIOINTEL_WINDOWS.bat /no-pause`: exit 0.

Two defects were caught and corrected before this pass: stale source hashes and an unexpected test-only coverage wheel. Optional Explorer shortcuts could not be written in the sandbox and produced non-fatal warnings. No clean external Windows 10/11 machine was available; this is a same-host native Windows qualification.
