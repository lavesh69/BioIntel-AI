@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\step183_verify_portfolio_demos.py
) else (
  py -3 scripts\step183_verify_portfolio_demos.py
)
if errorlevel 1 exit /b 1
echo Step 183 verification passed.
endlocal
