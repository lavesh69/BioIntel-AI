@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "MANAGED_MODE=0"
set "NO_PAUSE=0"
if not "%~1"=="" for %%A in (%*) do (
  if /I "%%~A"=="/managed" set "MANAGED_MODE=1"
  if /I "%%~A"=="/no-pause" set "NO_PAUSE=1"
)
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
if not defined BIOINTEL_APP_HOME set "BIOINTEL_APP_HOME=%LOCALAPPDATA%\BioIntelAI"
if not defined BIOINTEL_USER_DATA_DIR set "BIOINTEL_USER_DATA_DIR=%BIOINTEL_APP_HOME%\UserData"
pushd "%~dp0" >nul 2>&1 || exit /b 1
if "%MANAGED_MODE%"=="0" if exist "%BIOINTEL_APP_HOME%\App\RESTART_BIOINTEL_ACTIVE.bat" (
  popd
  call "%BIOINTEL_APP_HOME%\App\RESTART_BIOINTEL_ACTIVE.bat" %*
  exit /b %ERRORLEVEL%
)
set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo ERROR: Managed BioIntel environment missing hai. INSTALL_WINDOWS.bat run karein.
  popd
  call :pause_if_needed
  exit /b 1
)
"%PY%" "scripts\runtime_control_step206.py" restart --root "."
set "RC=%ERRORLEVEL%"
popd
call :pause_if_needed
exit /b %RC%

:pause_if_needed
if "%NO_PAUSE%"=="0" if "%MANAGED_MODE%"=="0" pause
exit /b 0