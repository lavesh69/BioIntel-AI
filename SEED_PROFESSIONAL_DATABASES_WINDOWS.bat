@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"

if not exist .venv\Scripts\python.exe (
  echo Virtual environment is missing.
  echo Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)

echo.
echo Seeding professional databases and Step 30 scientific reference data...
call .venv\Scripts\python.exe scripts\seed_professional_databases.py
if errorlevel 1 goto :error
call .venv\Scripts\python.exe scripts\seed_step30_scientific_foundation.py
if errorlevel 1 goto :error

echo.
echo Professional databases and scientific reference data are ready.
echo Open Data Intelligence Hub in BioIntel AI.
pause
exit /b 0

:error
echo.
echo Database seeding failed. Review the error above.
pause
exit /b 1
