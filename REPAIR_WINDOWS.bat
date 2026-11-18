@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
title BioIntel AI 15.6.0 Step220 - Verified Repair
if /I not "%~1"=="/managed" if exist "%LOCALAPPDATA%\BioIntelAI\App\REPAIR_BIOINTEL_ACTIVE.bat" (
  popd
  call "%LOCALAPPDATA%\BioIntelAI\App\REPAIR_BIOINTEL_ACTIVE.bat"
  exit /b
)
set "PYTHON_EXE="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\find_python311_windows.ps1" 2^>nul`) do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE (
  echo ERROR: CPython 3.11.x x64 is required for repair.
  echo Run INSTALL_PYTHON311_WINDOWS.bat, then try again.
  popd
  if /I not "%~1"=="/managed" pause
  exit /b 1
)
for %%P in (1 2 3 4 5) do if not exist ".release_parts\step220_part%%P.ok" (
  echo ERROR: Step220 Part %%P is missing. Extract all five matching ZIPs into one new folder.
  popd
  if /I not "%~1"=="/managed" pause
  exit /b 206
)
"%PYTHON_EXE%" "scripts\step206_release_gate.py" --root "." --deep-hashes --output "%LOCALAPPDATA%\BioIntelAI\UserData\reports\step220-repair-source-gate.json"
if errorlevel 1 (
  echo ERROR: Repair source is incomplete or damaged. Re-extract the five matching release ZIPs.
  popd
  if /I not "%~1"=="/managed" pause
  exit /b 206
)
"%PYTHON_EXE%" "scripts\install_windows_step206.py" --source-root "." --force-repair
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" echo BioIntel AI Step220 repair and post-install verification completed.
popd
if /I not "%~1"=="/managed" pause
exit /b %RC%
