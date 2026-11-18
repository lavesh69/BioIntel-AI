# BioIntel AI Windows Script Audit & Consolidation Strategy

## 1. Script Inventory Breakdown (Total: 287 Root .bat Files)
- **Installers (12):** INSTALL_WINDOWS.bat, INSTALL_PYTHON311_WINDOWS.bat, REPAIR_INSTALL_WINDOWS.bat, etc.
- **Launchers (68):** RUN_BOTH_WINDOWS.bat, RUN_APP_WINDOWS.bat, RUN_API_WINDOWS.bat, START_BIOINTEL_OFFLINE_WINDOWS.bat, etc.
- **Verifiers (108):** VERIFY_STEP24_WINDOWS.bat through VERIFY_STEP220_WINDOWS.bat, VERIFY_LATEST_WINDOWS.bat, etc.
- **Repairs & Recovery (10):** REPAIR_WINDOWS.bat, REPAIR_BIOINTEL_WINDOWS.bat, ROLLBACK_STEP97_WINDOWS.bat, etc.
- **Historical Developer Scripts (89):** Domain-specific test runners, stress matrices, and peak regression runners.

## 2. Consolidation Plan
We will establish 5 primary canonical Windows launchers in the root directory:
1. INSTALL_WINDOWS.bat - Handles non-admin LocalAppData setup, CPython 3.11.9 x64 verification, wheelhouse installation, and shortcuts.
2. RUN_BOTH_WINDOWS.bat - Launches FastAPI backend, Streamlit frontend, and resident supervisor with process cleanup.
3. REPAIR_WINDOWS.bat - Restores virtual environments, fixes corrupted databases, and preserves UserData.
4. DIAGNOSE_WINDOWS.bat - Runs release gate preflight and generates sanitized health reports.
5. UNINSTALL_BIOINTEL_WINDOWS.bat - Removes shortcuts and LocalAppData release files while offering UserData preservation options.

All historical step verifiers and developer scripts will be organized with deprecation redirects pointing to the canonical launchers.
