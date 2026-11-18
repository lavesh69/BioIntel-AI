@echo off
setlocal
cd /d "%~dp0"
set PYTHONPATH=%CD%\src
python scripts\qualify_step89_independent_validation_accelerator.py
if errorlevel 1 (
  echo Step 89 qualification failed.
  exit /b 1
)
echo Step 89 independent validation accelerator qualification passed.
