@echo off
setlocal EnableExtensions
set "SOURCE=%~dp0BioIntel-Step220"
if exist "%~dp0scripts\verify_education_phase11.py" set "SOURCE=%~dp0"
if not exist "%SOURCE%\scripts\verify_education_phase11.py" (
  echo ERROR: Reconstructed BioIntel-Step220 source was not found.
  exit /b 1
)
cd /d "%SOURCE%"
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY if exist "runtime\python\python.exe" set "PY=runtime\python\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\BioIntelAI\App\.venv\Scripts\python.exe" set "PY=%LOCALAPPDATA%\BioIntelAI\App\.venv\Scripts\python.exe"
if not defined PY set "PY=py -3.11"
set "PYTHONPATH=%CD%\src"
echo Running Phase 11 mega-core qualification...
%PY% scripts\verify_education_phase11.py
if errorlevel 1 exit /b 1
echo Running Step220 deep source-integrity gate...
%PY% scripts\step206_release_gate.py --root "%CD%" --deep-hashes --allow-builder-python --output "%CD%\EDUCATION_PHASE11_STEP220_GATE.json"
if errorlevel 1 exit /b 1
echo Phase 11 verification passed.
endlocal
