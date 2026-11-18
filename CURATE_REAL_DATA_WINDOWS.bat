@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Run INSTALL_WINDOWS.bat first.
  exit /b 1
)
if "%~1"=="" (
  echo Usage: CURATE_REAL_DATA_WINDOWS.bat input.csv output.csv [source_database]
  echo Example: CURATE_REAL_DATA_WINDOWS.bat bindingdb_export.csv reports\generated\bindingdb_curated.csv bindingdb
  exit /b 2
)
if "%~2"=="" (
  echo Output CSV path is required.
  exit /b 2
)
set "SOURCE_NAME=%~3"
if "%SOURCE_NAME%"=="" set "SOURCE_NAME=local_import"
".venv\Scripts\python.exe" scripts\curate_real_dataset.py "%~1" "%~2" --source-database "%SOURCE_NAME%"
endlocal
