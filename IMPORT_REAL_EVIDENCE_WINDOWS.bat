@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo BioIntel virtual environment not found. Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
echo.
echo BioIntel AI Step 25 Real Evidence Importer
echo Examples:
echo   .venv\Scripts\python.exe scripts\import_real_evidence.py bindingdb "C:\data\BindingDB_All.tsv" --release 2026
echo   .venv\Scripts\python.exe scripts\import_real_evidence.py generic "C:\data\activities.csv" --release lab_v1
echo   .venv\Scripts\python.exe scripts\import_real_evidence.py chembl --target CHEMBL203 --rows 250
echo.
.venv\Scripts\python.exe scripts\import_real_evidence.py --help
pause
