@echo off
setlocal
cd /d "%~dp0"
set PYTHONPATH=%CD%\src
python scripts\qualify_step84_real_external_validation.py --root .
if errorlevel 1 (
  echo Step 84 qualification failed.
  exit /b 1
)
echo Step 84 real external-validation framework qualification passed.
endlocal
