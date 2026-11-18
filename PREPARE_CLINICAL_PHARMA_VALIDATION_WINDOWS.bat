@echo off
setlocal
cd /d "%~dp0"
python scripts\build_clinical_pharma_validation_pack.py --root . --output data\clinical_pharma\templates
if errorlevel 1 exit /b 1
echo Clinical/pharma controlled template pack prepared.
