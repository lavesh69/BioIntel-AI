# Step 149 Historical Startup Path Audit

- ZIP parts scanned: **80**
- Dangerous launcher occurrences: **4**
- Affected releases: **145, 146, 147, 148**
- Root cause introduced in Step 145 and inherited by later cumulative builds.
- Step 149 replaces the risky argument with `--root "."` after changing into the project directory and adds Python-side path repair.

## Findings
- Step 145 · `BioIntel-AI/RUN_BOTH_WINDOWS.bat` line 36: `"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\step145_runtime_preflight.py" --root "%~dp0"`
- Step 146 · `BioIntel-AI/RUN_BOTH_WINDOWS.bat` line 36: `"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\step145_runtime_preflight.py" --root "%~dp0"`
- Step 147 · `BioIntel-AI/RUN_BOTH_WINDOWS.bat` line 36: `"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\step145_runtime_preflight.py" --root "%~dp0"`
- Step 148 · `BioIntel-AI/RUN_BOTH_WINDOWS.bat` line 36: `"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\step145_runtime_preflight.py" --root "%~dp0"`
