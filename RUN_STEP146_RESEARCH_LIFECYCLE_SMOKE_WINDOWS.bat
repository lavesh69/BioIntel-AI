@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title BioIntel AI Step 146 - Research Lifecycle Smoke
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pytest -q tests\test_step146_research_lifecycle_peak.py tests\test_step145_overall_stability.py tests\test_step144_research_planning_specialist_engines.py
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
