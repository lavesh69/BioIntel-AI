@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY if exist "runtime\python\python.exe" set "PY=runtime\python\python.exe"
if not defined PY set "PY=py -3.11"
set "PYTHONPATH=%CD%\src"
echo Running Phase 14 academic-quality and intelligence qualification...
%PY% scripts\verify_education_phase14.py --output "%CD%\EDUCATION_PHASE14_VERIFICATION.json"
if errorlevel 1 exit /b 1
echo Running Step220 deep source-integrity gate...
%PY% scripts\step206_release_gate.py --root "%CD%" --deep-hashes --allow-builder-python --output "%CD%\EDUCATION_PHASE14_STEP220_GATE.json"
if errorlevel 1 exit /b 1
echo Phase 14 verification passed.
endlocal
