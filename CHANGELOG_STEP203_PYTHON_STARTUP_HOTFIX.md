# Step203 Python Startup Hotfix

- Directly detects the standard per-user Python 3.11 path before using PowerShell.
- Accepts any CPython 3.11.x x64 runtime; the safe fallback installs Python 3.11.9.
- Removes the failing repeated curl-to-%TEMP% workflow.
- Downloads only to `%LOCALAPPDATA%\BioIntelAI\Downloads` and verifies the Python Software Foundation signature.
- Adds one-click `FIX_PYTHON_STARTUP_WINDOWS.bat`.
- Adds Step203 extraction markers, repair flow and startup verification.
- Paths containing spaces are quoted throughout.
