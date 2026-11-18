@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title BioIntel AI Step 147 - Research Lifecycle Operational Smoke
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pytest -q tests\test_step147_research_lifecycle_operational_peak.py tests\test_step146_research_lifecycle_peak.py tests\test_step145_overall_stability.py
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
