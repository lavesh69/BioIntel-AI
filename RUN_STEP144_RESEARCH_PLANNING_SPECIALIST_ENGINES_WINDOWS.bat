@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "PYTHONPATH=%CD%\src"
echo [BioIntel AI] Running Step 144 Research Planning specialist-engine qualification...
"%PYTHON%" -m pytest -q tests\test_step141_research_planning_suite.py tests\test_step142_connected_research_planning_os.py tests\test_step143_research_planning_feature_peak.py tests\test_step144_research_planning_specialist_engines.py
if errorlevel 1 (
  echo Step 144 qualification failed. Review the messages above.
  exit /b 1
)
"%PYTHON%" -m compileall -q app.py src pages tests
if errorlevel 1 (
  echo Python compilation failed.
  exit /b 1
)
echo Step 144 Research Planning specialist-engine qualification completed successfully.
endlocal
