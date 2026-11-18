@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" goto usage
if "%~2"=="" goto usage
if "%~3"=="" goto usage
if not exist ".venv\Scripts\python.exe" (
  echo Python environment not found. Run INSTALL_WINDOWS.bat first.
  exit /b 1
)
call ".venv\Scripts\python.exe" scripts\step181_import_evidence_bundle.py --root "%CD%" --bundle "%~1" --module "%~2" --evidence "%~3"
exit /b %ERRORLEVEL%
:usage
echo Usage: IMPORT_STEP181_EVIDENCE_BUNDLE_WINDOWS.bat evidence.zip module_key evidence_id
exit /b 2
