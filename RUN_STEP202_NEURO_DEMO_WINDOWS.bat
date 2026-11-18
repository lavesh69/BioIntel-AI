@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
title BioIntel AI Step202 - Run 23-Module Synthetic Demo
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: BioIntel environment is missing. Run INSTALL_WINDOWS.bat first.
  popd
  pause
  exit /b 1
)
for %%P in (1 2 3 4 5) do if not exist ".release_parts\step202_part%%P.ok" (
  echo ERROR: Missing Step202 Part %%P. Extract all five matching Step202 ZIPs into one NEW empty folder.
  popd
  pause
  exit /b 202
)
".venv\Scripts\python.exe" "scripts\run_step202_neuro_demo.py"
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" (
  echo.
  echo Demo complete. Reports are in:
  echo %LOCALAPPDATA%\BioIntelAI\UserData\reports\step202-neuro-demo
) else (
  echo Demo failed. Run VERIFY_STEP202_NEURO_CNS_WINDOWS.bat for diagnostics.
)
popd
pause
exit /b %RC%
