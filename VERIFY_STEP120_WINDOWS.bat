@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo ============================================================
echo BioIntel AI Step 120 Verification
echo ============================================================
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: .venv not found. Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
set "PYTHONPATH=%CD%\src"
".venv\Scripts\python.exe" scripts\verify_step120_weak_module_depth.py
set "RESULT=%ERRORLEVEL%"
echo.
if "%RESULT%"=="0" (
  echo Step 120 verification passed.
) else (
  echo Step 120 verification found one or more blockers.
)
pause
exit /b %RESULT%
