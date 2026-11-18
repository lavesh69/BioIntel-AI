@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "PYTHONPATH=%CD%\src"
echo [BioIntel AI] Running Step 142 Research Planning qualification...
"%PYTHON%" -m pytest -q tests\test_step142_connected_research_planning_os.py tests\test_step141_research_planning_suite.py
if errorlevel 1 (
  echo Qualification failed. Review the messages above.
  exit /b 1
)
"%PYTHON%" -m compileall -q app.py src pages tests
if errorlevel 1 (
  echo Python compilation failed.
  exit /b 1
)
echo Step 142 qualification completed successfully.
endlocal
