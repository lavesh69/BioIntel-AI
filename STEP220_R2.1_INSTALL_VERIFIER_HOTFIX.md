# Step220 R2.1 Installation Verifier Hotfix

This build fixes the Windows installation failure where the managed environment was rolled back after `verify_step206_windows_install_run.py` returned exit code 1.

## Root cause

The verifier still required the removed `RUNTIME_DATABASE_RELATIVE_PATHS` symbol even though the R2 installer had moved to recursive UserData database discovery and legacy release database migration. It also checked for exactly CPython 3.11.9 while the active Step220 contract supports CPython 3.11.x x64.

## Fix

- Verify the active recursive UserData backup and legacy SQLite migration implementation.
- Accept any supported CPython 3.11.x x64 patch release.
- Include `failed_checks` in the verifier report for direct diagnostics.
- Preserve Android and mobile source byte-for-byte.
