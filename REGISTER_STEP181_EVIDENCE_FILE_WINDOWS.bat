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
call ".venv\Scripts\python.exe" scripts\step181_register_evidence_file.py --root "%CD%" --module "%~1" --evidence "%~2" --file "%~3"
exit /b %ERRORLEVEL%
:usage
echo Usage: REGISTER_STEP181_EVIDENCE_FILE_WINDOWS.bat module_key evidence_id relative_filename
exit /b 2
