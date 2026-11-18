@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "PYTHONPATH=%CD%\src"
"%PYTHON%" -c "from biointel.research_planning.feature_density import PEAK_FEATURE_PROFILES; from biointel.research_planning.specialist_engines import SPECIALIST_ENGINE_CATALOG; assert len(PEAK_FEATURE_PROFILES)==20; assert len(SPECIALIST_ENGINE_CATALOG)==10; print('Step 144 profiles and specialist engines: OK')"
if errorlevel 1 exit /b 1
"%PYTHON%" -m pytest -q tests\test_step144_research_planning_specialist_engines.py
if errorlevel 1 exit /b 1
echo Step 144 Research Planning smoke checks passed.
endlocal
