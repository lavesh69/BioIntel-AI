@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
title BioIntel Education OS Phase 17-22 Installation
for %%P in (1 2 3 4) do if not exist ".release_parts\education_phase17_22_part%%P.ok" (
  echo ERROR: Education Phase 17-22 release marker %%P is missing.
  echo Extract all four matching ZIP parts into the same folder first.
  popd
  exit /b 220
)
call "INSTALL_WINDOWS.bat" /no-pause
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  popd
  exit /b %RC%
)
call "DIAGNOSE_EDUCATION_PHASE17_TO_22_WINDOWS.bat" /no-pause
set "RC=%ERRORLEVEL%"
popd
if not "%RC%"=="0" echo Installation completed, but Education OS diagnostics reported an error.
exit /b %RC%