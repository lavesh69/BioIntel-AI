@echo off
setlocal
cd /d "%~dp0"
echo [BioIntel AI] Building Step 186 platform completion assurance...
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
%PY% scripts\step186_build_platform_completion.py || exit /b 1
%PY% scripts\step186_verify_platform_completion.py || exit /b 1
echo [BioIntel AI] Step 186 verification passed: 18/18 modules at 10/10 internal/demo platform assurance.
pause
