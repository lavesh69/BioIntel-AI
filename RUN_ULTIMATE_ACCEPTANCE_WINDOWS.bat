@echo off
setlocal EnableExtensions
title BioIntel AI - Ultimate Acceptance Qualification

set "SOURCE_ROOT=%~dp0"
set "MANAGED_ROOT=%LOCALAPPDATA%\BioIntelAI\App\Releases\15.6.0-Step220"
set "ROOT=%SOURCE_ROOT%"
if exist "%MANAGED_ROOT%\scripts\ultimate_acceptance_step206.py" set "ROOT=%MANAGED_ROOT%\"

set "PY=%ROOT%.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo [FAIL] Managed BioIntel Python environment was not found.
  echo Run INSTALL_WINDOWS.bat successfully before final acceptance qualification.
  echo Expected: %PY%
  pause
  exit /b 1
)

pushd "%ROOT%"
"%PY%" "scripts\ultimate_acceptance_step206.py" --root "%ROOT%" --require-native-windows
set "RC=%ERRORLEVEL%"
popd

if not "%RC%"=="0" (
  echo.
  echo [FAIL] Ultimate acceptance did not pass on this Windows machine.
  echo Review %%LOCALAPPDATA%%\BioIntelAI\UserData\reports\step220-ultimate-acceptance.json
  echo Then run DIAGNOSE_WINDOWS.bat /deep or REPAIR_WINDOWS.bat.
  pause
  exit /b %RC%
)

echo.
echo [PASS] BioIntel AI software and native Windows acceptance gates passed.
echo Evidence: %%LOCALAPPDATA%%\BioIntelAI\UserData\reports\step220-ultimate-acceptance.json
exit /b 0
