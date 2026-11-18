@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo BioIntel AI Step 62 - Lab Analytics Qualification
echo ============================================================
python scripts\verify_step62_lab_analytics.py --output reports\step62_lab_analytics_qualification.json
set RC=%ERRORLEVEL%
if not "%RC%"=="0" (
  echo.
  echo Qualification failed with exit code %RC%.
  pause
  exit /b %RC%
)
echo.
echo Qualification passed. Report: reports\step62_lab_analytics_qualification.json
pause
exit /b 0
