@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
if exist "%LOCALAPPDATA%\BioIntelAI\App\ACTIVE_RELEASE.json" if exist "%LOCALAPPDATA%\BioIntelAI\App\RUN_BIOINTEL_ACTIVE.bat" (
  echo Engine Control Center BioIntel app ke andar available hai.
  call "%LOCALAPPDATA%\BioIntelAI\App\RUN_BIOINTEL_ACTIVE.bat"
  popd
  exit /b %ERRORLEVEL%
)
set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo ERROR: Pehle INSTALL_WINDOWS.bat run karein.
  popd
  pause
  exit /b 1
)
"%PY%" "scripts\step213_engine_platform.py" health
set "RC=%ERRORLEVEL%"
popd
pause
exit /b %RC%
