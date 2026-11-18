@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
"%PY%" scripts\step176_verify_target_modules.py --execute-smoke-tests
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo Step 176 internal module upgrade verification passed.
) else (
  echo Step 176 verification found incomplete internal hooks. See reports\step176_target_module_qualification.*
)
pause
exit /b %RC%
