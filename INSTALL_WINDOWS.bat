@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "NO_PAUSE=0"
set "PREFLIGHT_ONLY=0"
set "SHORT_SOURCE_MODE=0"
set "RECOVERED_SOURCE="
if not "%~1"=="" for %%A in (%*) do (
  if /I "%%~A"=="/no-pause" set "NO_PAUSE=1"
  if /I "%%~A"=="/preflight-only" set "PREFLIGHT_ONLY=1"
  if /I "%%~A"=="/short-source" set "SHORT_SOURCE_MODE=1"
)
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
if not defined BIOINTEL_APP_HOME set "BIOINTEL_APP_HOME=%LOCALAPPDATA%\BioIntelAI"
if not defined BIOINTEL_USER_DATA_DIR set "BIOINTEL_USER_DATA_DIR=%BIOINTEL_APP_HOME%\UserData"
pushd "%~dp0" >nul 2>&1 || (
  echo ERROR: BioIntel package folder open nahi ho paya.
  echo EXTRACT_AND_INSTALL_STEP220_WINDOWS.bat ko four ZIPs ke paas run karein.
  call :pause_if_needed
  exit /b 1
)
title BioIntel AI 15.6.0 Step220 V20.5 - Windows Installation

set "BIOINTEL_SOURCE_ROOT=%CD%"
set "NEEDS_SHORT_SOURCE=0"
if not "%BIOINTEL_SOURCE_ROOT:~96,1%"=="" set "NEEDS_SHORT_SOURCE=1"
if not exist "data\step178\target_modules\multiomics_biomarker_discovery\governance_manifest_templates\multiomics_biomarker_discovery-validation-and-acceptance-plan.json" set "NEEDS_SHORT_SOURCE=1"
if "%SHORT_SOURCE_MODE%"=="0" if "%NEEDS_SHORT_SOURCE%"=="1" call :prepare_short_source
if errorlevel 1 goto :SHORT_SOURCE_FAILED
if defined RECOVERED_SOURCE goto :DELEGATE_SHORT_SOURCE
echo ============================================================
echo BioIntel AI 15.6.0 - Step220 V20.5 Windows Installation
echo Biology, Engineered into Intelligence.
echo ============================================================
echo.

if not exist "app.py" (
  echo ERROR: app.py missing hai. Four matching Windows-Fixed ZIP parts ek hi folder mein extract karein.
  echo Extract ke baad BioIntel-Step220\START_HERE_WINDOWS.bat run karein.
  popd
  call :pause_if_needed
  exit /b 220
)
for %%P in (1 2 3 4) do if not exist ".release_parts\step220_part%%P.ok" (
  echo ERROR: Step220 Part %%P marker missing hai.
  echo Matching Windows-Fixed Part1, Part2, Part3 aur Part4 ZIPs ek hi destination mein extract karein.
  echo Extract ke baad BioIntel-Step220\START_HERE_WINDOWS.bat run karein.
  popd
  call :pause_if_needed
  exit /b 220
)
for %%F in ("STEP220_RELEASE.json" "STEP220_SOURCE_MANIFEST_SHA256.json" "scripts\step206_release_gate.py" "scripts\install_windows_step206.py" "scripts\find_python311_windows.ps1" "scripts\install_python311_user.ps1") do if not exist %%F (
  echo ERROR: Critical Step220 file missing hai: %%~F
  popd
  call :pause_if_needed
  exit /b 220
)

set "PYTHON_EXE="
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python311\python.exe" "%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe" "%ProgramFiles%\Python311\python.exe") do if not defined PYTHON_EXE if exist "%%~fP" (
  "%%~fP" -c "import struct,sys;raise SystemExit(0 if sys.version_info[:2]==(3,11) and struct.calcsize('P')*8==64 else 1)" >nul 2>&1 && set "PYTHON_EXE=%%~fP"
)
if not defined PYTHON_EXE for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\find_python311_windows.ps1" 2^>nul`) do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE (
  echo Required 64-bit CPython 3.11.x nahi mila. Official installer route start ho raha hai...
  call "INSTALL_PYTHON311_WINDOWS.bat" /auto
  if errorlevel 1 (
    echo.
    echo PYTHON PREPARATION FAILED.
    echo 64-bit CPython 3.11.x install karke INSTALL_WINDOWS.bat dobara run karein.
    popd
    call :pause_if_needed
    exit /b 1
  )
  for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\find_python311_windows.ps1" 2^>nul`) do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
)
if not defined PYTHON_EXE (
  echo ERROR: 64-bit CPython 3.11.x locate nahi ho paya.
  popd
  call :pause_if_needed
  exit /b 1
)

"%PYTHON_EXE%" -c "import struct,sys;raise SystemExit(0 if sys.version_info[:2]==(3,11) and struct.calcsize('P')*8==64 else 1)" >nul 2>&1
if errorlevel 1 (
  echo ERROR: Selected Python 3.11.x x64 nahi hai.
  popd
  call :pause_if_needed
  exit /b 1
)

echo Python selected: "%PYTHON_EXE%"
for %%D in ("%BIOINTEL_APP_HOME%" "%BIOINTEL_USER_DATA_DIR%\reports" "%BIOINTEL_USER_DATA_DIR%\runtime_logs" "%BIOINTEL_APP_HOME%\Temp") do if not exist %%D mkdir %%D >nul 2>&1

echo [Preflight] Step220 four-part package aur managed short path check ho raha hai...
"%PYTHON_EXE%" "scripts\step206_release_gate.py" --root "." --quick --output "%BIOINTEL_USER_DATA_DIR%\reports\step220-bootstrap-gate.json"
if errorlevel 1 (
  echo.
  echo PACKAGE PREFLIGHT FAILED.
  echo Report: %BIOINTEL_USER_DATA_DIR%\reports\step220-bootstrap-gate.json
  popd
  call :pause_if_needed
  exit /b 220
)
if "%PREFLIGHT_ONLY%"=="1" (
  echo Step220 package preflight passed.
  popd
  exit /b 0
)

"%PYTHON_EXE%" "scripts\install_windows_step206.py" --source-root "."
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo INSTALLATION FAILED with exit code %RC%.
  echo Logs: %BIOINTEL_USER_DATA_DIR%\runtime_logs
  echo Report: %BIOINTEL_USER_DATA_DIR%\reports\step220-install.json
  popd
  call :pause_if_needed
  exit /b %RC%
)

set "MANAGED_ROOT=%BIOINTEL_APP_HOME%\App\Releases\15.6.0-Step220"
set "MANAGED_PY=%MANAGED_ROOT%\.venv\Scripts\python.exe"
if not exist "%MANAGED_PY%" (
  echo ERROR: Managed Python environment missing after installation.
  popd
  call :pause_if_needed
  exit /b 220
)
"%MANAGED_PY%" "%MANAGED_ROOT%\scripts\verify_step206_windows_install_run.py" --root "%MANAGED_ROOT%" --installed-python "%MANAGED_PY%" --output "%BIOINTEL_USER_DATA_DIR%\reports\step220-install-run-verification.json"
if errorlevel 1 (
  echo INSTALLATION VERIFICATION FAILED.
  echo Report: %BIOINTEL_USER_DATA_DIR%\reports\step220-install-run-verification.json
  popd
  call :pause_if_needed
  exit /b 220
)

echo.
echo ============================================================
echo INSTALLATION COMPLETE
echo Stable app location: %MANAGED_ROOT%
echo App start karne ke liye RUN_BOTH_WINDOWS.bat run karein.
echo ============================================================
popd
call :pause_if_needed
exit /b 0

:DELEGATE_SHORT_SOURCE
echo.
echo Long Windows path detected. Original ZIP short LocalAppData path mein safely re-extract ho gaya.
echo Installation short verified source se continue ho rahi hai:
echo %RECOVERED_SOURCE%
popd
call "%RECOVERED_SOURCE%\INSTALL_WINDOWS.bat" /short-source %*
set "RC=%ERRORLEVEL%"
exit /b %RC%

:SHORT_SOURCE_FAILED
echo.
echo ERROR: Automatic short-path recovery failed.
echo Saare four matching Windows-Fixed ZIP parts extracted folder ke paas rakhein.
echo Phir INSTALL_WINDOWS.bat dobara run karein. Project data delete nahi hua.
popd
call :pause_if_needed
exit /b 220

:prepare_short_source
set "RECOVERED_SOURCE="
set "SINGLE_ZIP="
set "FOUR_DIR="
set "FOUR_PREFIX="
for %%Z in ("%~dp0BioIntel-AI-15.6.0-FULL-INTEGRATED-WINDOWS-HOTFIX2.zip" "%~dp0..\BioIntel-AI-15.6.0-FULL-INTEGRATED-WINDOWS-HOTFIX2.zip" "%~dp0..\..\BioIntel-AI-15.6.0-FULL-INTEGRATED-WINDOWS-HOTFIX2.zip") do if not defined SINGLE_ZIP if exist "%%~fZ" set "SINGLE_ZIP=%%~fZ"
for %%Z in ("%~dp0BioIntel-AI-15.6.0-FULL-INTEGRATED-WINDOWS-HOTFIX2*.zip" "%~dp0..\BioIntel-AI-15.6.0-FULL-INTEGRATED-WINDOWS-HOTFIX2*.zip" "%~dp0..\..\BioIntel-AI-15.6.0-FULL-INTEGRATED-WINDOWS-HOTFIX2*.zip") do if not defined SINGLE_ZIP if exist "%%~fZ" set "SINGLE_ZIP=%%~fZ"
for %%Z in ("%~dp0BioIntel-AI-15.6.0-FULL-INTEGRATED-WINDOWS*.zip" "%~dp0..\BioIntel-AI-15.6.0-FULL-INTEGRATED-WINDOWS*.zip" "%~dp0..\..\BioIntel-AI-15.6.0-FULL-INTEGRATED-WINDOWS*.zip") do if not defined SINGLE_ZIP if exist "%%~fZ" set "SINGLE_ZIP=%%~fZ"
for %%D in ("%~dp0." "%~dp0.." "%~dp0..\..") do for %%N in (BioIntel-AI-15.6.0-Phase31-to-35-Windows-Fixed BioIntel-AI-15.6.0-EDUCATION-PHASE23-TO-30-ENTERPRISE-R1 BioIntel-AI-15.6.0-EDUCATION-PHASE17-TO-22-MEGA-FIXED-R1 BioIntel-AI-15.6.0-EDUCATION-PHASE11 BioIntel-AI-15.6.0-EDUCATION-PHASE10-HOTFIX1 BioIntel-AI-15.6.0-EDUCATION-PHASE10 BioIntel-AI-15.6.0-EDUCATION-PHASE9 BioIntel-AI-15.6.0-EDUCATION-PHASE8 BioIntel-AI-15.6.0-EDUCATION-PHASE7 BioIntel-AI-15.6.0-EDUCATION-PHASE6 BioIntel-AI-15.6.0-EDUCATION-PHASE5 BioIntel-AI-15.6.0-EDUCATION-PHASE4 BioIntel-AI-15.6.0-EDUCATION-PHASE3 BioIntel-AI-15.6.0-EDUCATION-PHASE2 BioIntel-AI-15.6.0-EDUCATION-SCIENCE-ACADEMY BioIntel-AI-15.6.0-EDUCATION-UNIVERSE) do if not defined FOUR_DIR if exist "%%~fD\%%N-Part1.zip" if exist "%%~fD\%%N-Part2.zip" if exist "%%~fD\%%N-Part3.zip" if exist "%%~fD\%%N-Part4.zip" (
  set "FOUR_DIR=%%~fD"
  set "FOUR_PREFIX=%%N"
)
if not defined SINGLE_ZIP if not defined FOUR_DIR exit /b 2
set "TAR_EXE=%SystemRoot%\System32\tar.exe"
if not exist "%TAR_EXE%" exit /b 3
set "SINGLE_STAGE=%BIOINTEL_APP_HOME%\Src"
if not exist "%SINGLE_STAGE%" mkdir "%SINGLE_STAGE%" >nul 2>&1
if not exist "%SINGLE_STAGE%" exit /b 4
if defined SINGLE_ZIP goto :prepare_extract_single
if defined FOUR_DIR goto :prepare_extract_four
exit /b 2

:prepare_extract_single
echo.
echo Windows Explorer long-path truncation detected.
echo Verified single ZIP short path mein re-extract ho raha hai...
echo ZIP: %SINGLE_ZIP%
echo Target: %SINGLE_STAGE%
"%TAR_EXE%" -xf "%SINGLE_ZIP%" -C "%SINGLE_STAGE%"
if errorlevel 1 exit /b 5
goto :prepare_verify_recovered

:prepare_extract_four
echo.
echo Windows Explorer long-path truncation detected.
echo Four matching ZIP parts short path mein re-extract ho rahe hain...
echo ZIP folder: %FOUR_DIR%
echo Target: %SINGLE_STAGE%
for %%P in (1 2 3 4) do (
  "%TAR_EXE%" -xf "%FOUR_DIR%\%FOUR_PREFIX%-Part%%P.zip" -C "%SINGLE_STAGE%"
  if errorlevel 1 exit /b 5
)

:prepare_verify_recovered
set "RECOVERED_SOURCE=%SINGLE_STAGE%\BioIntel-Step220"
if not exist "%RECOVERED_SOURCE%\INSTALL_WINDOWS.bat" exit /b 6
if not exist "%RECOVERED_SOURCE%\data\step178\target_modules\multiomics_biomarker_discovery\governance_manifest_templates\multiomics_biomarker_discovery-validation-and-acceptance-plan.json" exit /b 7
for %%P in (1 2 3 4) do if not exist "%RECOVERED_SOURCE%\.release_parts\step220_part%%P.ok" exit /b 8
exit /b 0
:pause_if_needed
if "%NO_PAUSE%"=="0" pause
exit /b 0
