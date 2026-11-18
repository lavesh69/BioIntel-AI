@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
python scripts\verify_education_integrity_v2.py
if errorlevel 1 exit /b 1
python -m unittest discover -s tests -p "test_education*.py"
if errorlevel 1 exit /b 1
python -m unittest tests.test_dragon_universe_theme
if errorlevel 1 exit /b 1
echo Education Phase 2 integrity verification passed.
endlocal
