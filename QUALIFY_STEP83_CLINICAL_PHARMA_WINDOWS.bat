@echo off
setlocal
cd /d "%~dp0"
python scripts\qualify_step83_clinical_pharma.py --root . --output reports\generated\step83_clinical_pharma_framework_readiness.json
if errorlevel 1 exit /b 1
python -m pytest -q tests\test_step83_clinical_pharma_validation.py
if errorlevel 1 exit /b 1
echo Step 83 clinical/pharma framework qualification passed.
