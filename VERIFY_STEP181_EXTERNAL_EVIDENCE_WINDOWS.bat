@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment not found. Run INSTALL_WINDOWS.bat first.
  exit /b 1
)
call ".venv\Scripts\python.exe" scripts\step181_verify_external_readiness.py --root "%CD%"
set RC=%ERRORLEVEL%
if %RC% EQU 0 (
  echo Step 181 workflow verification passed. Review reports\step181_external_readiness_*.csv.
) else (
  echo Step 181 verification failed. Review the blockers above.
)
exit /b %RC%
