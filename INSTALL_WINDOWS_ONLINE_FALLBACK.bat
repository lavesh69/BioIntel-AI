@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || (
  echo ERROR: BioIntel package folder open nahi ho paya.
  pause
  exit /b 1
)
title BioIntel AI 15.6.0 Step220 V20.3 - Online Fallback
set "PYTHON_EXE="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\find_python311_windows.ps1" 2^>nul`) do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE (
  echo ERROR: 64-bit CPython 3.11.x nahi mila.
  echo Pehle INSTALL_PYTHON311_WINDOWS.bat run karein.
  popd
  pause
  exit /b 1
)
"%PYTHON_EXE%" -c "import struct,sys;raise SystemExit(0 if sys.version_info[:2]==(3,11) and struct.calcsize('P')*8==64 else 1)" >nul 2>&1
if errorlevel 1 (
  echo ERROR: Selected Python CPython 3.11.x x64 nahi hai.
  popd
  pause
  exit /b 1
)
echo BioIntel AI Step220 managed online fallback installation start ho rahi hai...
"%PYTHON_EXE%" "scripts\install_windows_step206.py" --source-root "." --force-repair --online
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo Online installation failed. Internet/proxy access aur installer report check karke retry karein.
  echo Report: %LOCALAPPDATA%\BioIntelAI\UserData\reports\step220-install.json
  popd
  pause
  exit /b %RC%
)
echo Installation completed and V20.3 runtime compatibility verified.
echo Ab RUN_BOTH_WINDOWS.bat run karein.
popd
pause
exit /b 0
