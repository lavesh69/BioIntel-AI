@echo off
setlocal EnableExtensions
set "PROJECT_ROOT=%~dp0"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
cd /d "%PROJECT_ROOT%" || exit /b 1
set "PYTHONDONTWRITEBYTECODE=1"
if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
) else (
  set "PYTHON_EXE=python"
)
"%PYTHON_EXE%" "%PROJECT_ROOT%\scripts\step157_target_qualification.py" --root "%PROJECT_ROOT%" --ui
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo.
  echo Step 157 target qualification found blocking issues. Review reports\step157_target_qualification.json
  pause
  exit /b %EXIT_CODE%
)
echo.
echo Step 157 target qualification passed. Report: reports\step157_target_qualification.json
pause
exit /b 0
