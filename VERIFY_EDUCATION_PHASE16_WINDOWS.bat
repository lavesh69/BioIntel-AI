@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY if exist "runtime\python\python.exe" set "PY=runtime\python\python.exe"
if not defined PY set "PY=py -3.11"
set "PYTHONPATH=%CD%\src"
echo Running Phase 16 final local-completion qualification...
%PY% scripts\verify_education_phase16.py --output "%CD%\EDUCATION_PHASE16_VERIFICATION.json"
if errorlevel 1 exit /b 1
echo Re-running Phase 15 runtime qualification...
%PY% scripts\verify_education_phase15.py --output "%CD%\EDUCATION_PHASE15_REVERIFICATION.json"
if errorlevel 1 exit /b 1
echo Running Step220 deep source-integrity gate...
%PY% scripts\step206_release_gate.py --root "%CD%" --deep-hashes --allow-builder-python --output "%CD%\EDUCATION_PHASE16_STEP220_GATE.json"
if errorlevel 1 exit /b 1
echo Phase 16 verification passed.
endlocal
