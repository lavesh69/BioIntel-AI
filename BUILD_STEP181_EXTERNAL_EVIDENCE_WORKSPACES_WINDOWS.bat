@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment not found. Run INSTALL_WINDOWS.bat first.
  exit /b 1
)
call ".venv\Scripts\python.exe" scripts\step181_build_external_evidence_workspaces.py --root "%CD%"
if errorlevel 1 exit /b 1
echo.
echo Step 181 real-evidence workspaces are ready under UserData\step181\evidence.
echo Add only real permissioned evidence, update SHA-256 values and obtain reviewer sign-off.
endlocal
