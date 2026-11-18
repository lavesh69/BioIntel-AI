@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "PYTHONPATH=%CD%\src"
"%PYTHON%" -c "from biointel.research_planning.advanced_profiles import ADVANCED_PROFILES; from biointel.research_planning.catalog import PLANNING_MODULES; assert len(ADVANCED_PROFILES)==18; assert len(PLANNING_MODULES)==16; print('Research Planning profiles: OK')"
if errorlevel 1 exit /b 1
"%PYTHON%" -m pytest -q tests\test_step142_connected_research_planning_os.py
if errorlevel 1 exit /b 1
echo Research Planning smoke checks passed.
endlocal
