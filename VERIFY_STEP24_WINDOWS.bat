@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Run INSTALL_WINDOWS.bat first.
  exit /b 1
)
set "PYTHONPATH=%CD%\src"
".venv\Scripts\python.exe" scripts\verify_release.py || exit /b 1
".venv\Scripts\python.exe" scripts\smoke_test.py || exit /b 1
".venv\Scripts\python.exe" scripts\diagnose.py || exit /b 1
".venv\Scripts\python.exe" scripts\performance_qualification.py || exit /b 1
echo Step 24 verification completed successfully.
endlocal
