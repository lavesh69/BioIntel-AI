@echo off
setlocal
cd /d "%~dp0"
echo.
echo BioIntel AI Step 170 - Production Reference Manager
echo ---------------------------------------------------
echo Default mode is a safe plan. Full databases may require hundreds of GB or TB.
echo Licences are never silently accepted.
echo.
if /I "%~1"=="--execute-small-open" goto execute
python scripts\step170_reference_manager.py --root "%CD%" --max-size-gb 2
exit /b %errorlevel%
:execute
python scripts\step170_reference_manager.py --root "%CD%" --execute --max-size-gb 2 --reference hpo-ontology --reference go-basic --reference reactome-uniprot --reference uniprot-swissprot
exit /b %errorlevel%
