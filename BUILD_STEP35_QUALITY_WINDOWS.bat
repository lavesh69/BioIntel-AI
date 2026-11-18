@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)
%PYTHON% scripts\upgrade_step35.py
if errorlevel 1 goto :error
%PYTHON% scripts\verify_step35.py
if errorlevel 1 goto :error
echo.
echo Step 35 quality hardening completed successfully.
pause
exit /b 0
:error
echo.
echo Step 35 verification failed. Review the output above.
pause
exit /b 1
