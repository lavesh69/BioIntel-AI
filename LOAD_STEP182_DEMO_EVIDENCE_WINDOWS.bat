@echo off
setlocal
cd /d "%~dp0"
call BUILD_STEP182_DEMO_EVIDENCE_WINDOWS.bat
if errorlevel 1 exit /b 1
call VERIFY_STEP182_DEMO_EVIDENCE_WINDOWS.bat
if errorlevel 1 exit /b 1
echo.
echo DEMO DATA READY: 25/25 synthetic packs.
echo REAL EXTERNAL EVIDENCE: 0/25. CONTROLLED RELEASE: BLOCKED.
pause
exit /b 0
