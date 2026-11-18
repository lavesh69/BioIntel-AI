@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || (
  echo ERROR: The BioIntel folder could not be opened.
  pause
  exit /b 1
)
title BioIntel AI - Prepare Python 3.11.9 x64
set "AUTO=0"
if /I "%~1"=="/auto" set "AUTO=1"
set "PYTHON_EXE="
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python311\python.exe" "%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe" "%ProgramFiles%\Python311\python.exe") do if not defined PYTHON_EXE if exist "%%~fP" (
  "%%~fP" -c "import struct,sys;raise SystemExit(0 if sys.version_info[:2]==(3,11) and struct.calcsize('P')*8==64 else 1)" >nul 2>&1 && set "PYTHON_EXE=%%~fP"
)
if not defined PYTHON_EXE for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\find_python311_windows.ps1" 2^>nul`) do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if defined PYTHON_EXE goto :found

echo BioIntel AI requires 64-bit CPython 3.11.9 exactly.
echo It was not found. A bundled/cached signed installer is preferred; otherwise the official installer is downloaded when internet is available.
echo Download location: %%LOCALAPPDATA%%\BioIntelAI\Downloads
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\install_python311_user.ps1" -PackageRoot "%CD%"
if errorlevel 1 goto :failed

set "PYTHON_EXE="
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python311\python.exe" "%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe" "%ProgramFiles%\Python311\python.exe") do if not defined PYTHON_EXE if exist "%%~fP" (
  "%%~fP" -c "import struct,sys;raise SystemExit(0 if sys.version_info[:2]==(3,11) and struct.calcsize('P')*8==64 else 1)" >nul 2>&1 && set "PYTHON_EXE=%%~fP"
)
if not defined PYTHON_EXE for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\find_python311_windows.ps1" 2^>nul`) do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE goto :failed

:found
echo.
echo Python ready: "%PYTHON_EXE%"
"%PYTHON_EXE%" --version
popd
if "%AUTO%"=="0" pause
exit /b 0

:failed
echo.
echo ERROR: BioIntel could not prepare 64-bit CPython 3.11.9.
echo Install the official python-3.11.9-amd64.exe from Python Software Foundation,
echo then run INSTALL_WINDOWS.bat again. No BioIntel project data was changed.
popd
if "%AUTO%"=="0" pause
exit /b 1
