@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
if not defined BIOINTEL_USER_DATA_DIR set "BIOINTEL_USER_DATA_DIR=%LOCALAPPDATA%\BioIntelAI\UserData"
if not exist "%BIOINTEL_USER_DATA_DIR%\backups" mkdir "%BIOINTEL_USER_DATA_DIR%\backups" >nul 2>&1
set "PY=%CD%\.venv\Scripts\python.exe"
set "PYARGS="
if not exist "%PY%" (
  set "PY=py"
  set "PYARGS=-3.11"
)
set "STAMP=%DATE:~-4%%DATE:~4,2%%DATE:~7,2%-%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%"
set "STAMP=%STAMP: =0%"
set "OUTPUT=%BIOINTEL_USER_DATA_DIR%\backups\education-phase23-30-%STAMP%.zip"
set "PYTHONPATH=%CD%\src"
"%PY%" %PYARGS% "scripts\phase23_30_backup_restore.py" --root "%CD%" backup --output "%OUTPUT%"
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" echo Backup created: %OUTPUT%
popd
if /I not "%~1"=="/no-pause" pause
exit /b %RC%
