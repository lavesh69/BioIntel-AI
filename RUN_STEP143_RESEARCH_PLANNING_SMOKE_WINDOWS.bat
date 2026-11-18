@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "PYTHONPATH=%CD%\src"
"%PYTHON%" -c "from biointel.research_planning.catalog import PLANNING_MODULES; from biointel.research_planning.feature_density import get_peak_profile; keys={m.key for m in PLANNING_MODULES}|{'biostatistics_design','synthetic_cohort_trial','research_planning_command_center','research_budget_participant_burden'}; assert len(keys)==20; assert all(get_peak_profile(k).feature_count>=32 for k in keys); print('Step 143 peak profiles: OK')"
if errorlevel 1 exit /b 1
"%PYTHON%" -m pytest -q tests\test_step143_research_planning_feature_peak.py
if errorlevel 1 exit /b 1
echo Step 143 Research Planning smoke checks passed.
endlocal
