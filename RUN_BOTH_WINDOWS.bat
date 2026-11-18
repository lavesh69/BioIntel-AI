@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "MANAGED_MODE=0"
set "PREFLIGHT_ONLY=0"
set "NO_PAUSE=0"
set "NO_BROWSER=0"
if not "%~1"=="" for %%A in (%*) do (
  if /I "%%~A"=="/managed" set "MANAGED_MODE=1"
  if /I "%%~A"=="/preflight-only" set "PREFLIGHT_ONLY=1"
  if /I "%%~A"=="/no-pause" set "NO_PAUSE=1"
  if /I "%%~A"=="/no-browser" set "NO_BROWSER=1"
)
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
if not defined BIOINTEL_APP_HOME set "BIOINTEL_APP_HOME=%LOCALAPPDATA%\BioIntelAI"
if not defined BIOINTEL_USER_DATA_DIR set "BIOINTEL_USER_DATA_DIR=%BIOINTEL_APP_HOME%\UserData"
if "%NO_BROWSER%"=="1" set "BIOINTEL_NO_BROWSER=1"
pushd "%~dp0" >nul 2>&1 || (
  echo ERROR: BioIntel application folder open nahi ho paya.
  call :pause_if_needed
  exit /b 1
)
title BioIntel AI 15.6.0 Step220 V20.5 - Start

if "%PREFLIGHT_ONLY%"=="1" if "%MANAGED_MODE%"=="0" goto :RUN_PREFLIGHT
if "%MANAGED_MODE%"=="0" goto :ENSURE_AND_DELEGATE

if "%MANAGED_MODE%"=="1" if not exist "%CD%\.venv\Scripts\python.exe" (
  echo Managed mode source folder se request hua; verified installed release locate/repair ho rahi hai...
  set "MANAGED_MODE=0"
  goto :ENSURE_AND_DELEGATE
)
set "BIOINTEL_PROJECT_ROOT=%CD%"
set "PY=%CD%\.venv\Scripts\python.exe"
set "LOGDIR=%BIOINTEL_USER_DATA_DIR%\runtime_logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1
if not exist "%BIOINTEL_USER_DATA_DIR%\reports" mkdir "%BIOINTEL_USER_DATA_DIR%\reports" >nul 2>&1
if not exist "%PY%" (
  echo ERROR: Managed BioIntel Python environment missing hai.
  echo INSTALL_WINDOWS.bat se verified repair run karein.
  popd
  call :pause_if_needed
  exit /b 1
)
"%PY%" -c "import struct,sys;raise SystemExit(0 if sys.version_info[:2]==(3,11) and struct.calcsize('P')*8==64 else 1)" >nul 2>&1
if errorlevel 1 (
  echo ERROR: BioIntel environment 64-bit CPython 3.11.x nahi hai.
  echo INSTALL_WINDOWS.bat se verified repair run karein.
  popd
  call :pause_if_needed
  exit /b 1
)
for %%P in (1 2 3 4) do if not exist ".release_parts\step220_part%%P.ok" (
  echo ERROR: Managed Step220 Part %%P marker missing hai.
  echo Four matching Windows-Fixed ZIP parts ek folder mein extract karke START_HERE_WINDOWS.bat run karein.
  popd
  call :pause_if_needed
  exit /b 220
)
"%PY%" "scripts\step206_release_gate.py" --root "." --quick > "%LOGDIR%\step220-start-preflight.log" 2>&1
if errorlevel 1 (
  echo ERROR: Managed Step220 startup preflight failed.
  echo Log: %LOGDIR%\step220-start-preflight.log
  echo INSTALL_WINDOWS.bat dobara run karein.
  popd
  call :pause_if_needed
  exit /b 220
)
set "COMPAT_LOG=%LOGDIR%\step220-windows-runtime-compatibility.log"
"%PY%" "scripts\verify_windows_runtime_compatibility_step206.py" --root "." --strict-python --output "%BIOINTEL_USER_DATA_DIR%\reports\step220-windows-runtime-compatibility.json" > "%COMPAT_LOG%" 2>&1
if errorlevel 1 (
  echo ERROR: Windows scientific runtime compatibility check failed.
  echo Log: %COMPAT_LOG%
  echo INSTALL_WINDOWS.bat se verified repair run karein.
  popd
  call :pause_if_needed
  exit /b 1
)

echo BioIntel AI Step220 start ho raha hai...
"%PY%" "scripts\run_biointel_step206.py"
set "RC=%ERRORLEVEL%"
popd
if not "%RC%"=="0" (
  echo.
  echo BioIntel AI start nahi hua. Exit code %RC%.
  echo Logs: %LOGDIR%
  echo INSTALL_WINDOWS.bat ya REPAIR_WINDOWS.bat se repair karein.
  call :pause_if_needed
)
exit /b %RC%

:RUN_PREFLIGHT
popd
call "%~dp0INSTALL_WINDOWS.bat" /short-source /preflight-only /no-pause
exit /b %ERRORLEVEL%

:ENSURE_AND_DELEGATE
call :ENSURE_CURRENT_INSTALL
if errorlevel 1 (
  popd
  call :pause_if_needed
  exit /b 220
)
popd
call "%BIOINTEL_APP_HOME%\App\RUN_BIOINTEL_ACTIVE.bat" %*
exit /b %ERRORLEVEL%

:ENSURE_CURRENT_INSTALL
set "SOURCE_MANIFEST=%CD%\release\SOURCE_MANIFEST_SHA256.json"
set "TARGET_MANIFEST=%BIOINTEL_APP_HOME%\App\Releases\15.6.0-Step220\release\SOURCE_MANIFEST_SHA256.json"
set "STABLE_LAUNCHER=%BIOINTEL_APP_HOME%\App\RUN_BIOINTEL_ACTIVE.bat"
if not exist "%STABLE_LAUNCHER%" goto INSTALL_CURRENT_RELEASE
if not exist "%SOURCE_MANIFEST%" goto INSTALL_CURRENT_RELEASE
if not exist "%TARGET_MANIFEST%" goto INSTALL_CURRENT_RELEASE
fc /b "%SOURCE_MANIFEST%" "%TARGET_MANIFEST%" >nul 2>&1
if not errorlevel 1 exit /b 0

:INSTALL_CURRENT_RELEASE
echo New, repaired, or incomplete release detected. Verified Step220 installation start ho rahi hai...
call "%~dp0INSTALL_WINDOWS.bat" /no-pause
if errorlevel 1 exit /b 220
if not exist "%STABLE_LAUNCHER%" (
  echo ERROR: Stable launcher installation ke baad create nahi hua.
  exit /b 220
)
exit /b 0

:pause_if_needed
if "%NO_PAUSE%"=="0" pause
exit /b 0
