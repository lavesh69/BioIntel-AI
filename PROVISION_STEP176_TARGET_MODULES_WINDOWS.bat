@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo ============================================================
echo BioIntel AI Step 176 - 17 Target Module Provisioning
echo ============================================================
echo.
echo This launcher preserves the classic install/run method.
echo It delegates real engine and reference installation to the
echo existing Step 170 qualification scripts and never marks an
echo external asset qualified without checksum/licence/smoke evidence.
echo.
if exist "PROVISION_STEP170_SCIENTIFIC_RUNTIME_WINDOWS.bat" call "PROVISION_STEP170_SCIENTIFIC_RUNTIME_WINDOWS.bat"
if exist "DOWNLOAD_STEP170_REFERENCE_DATABASES_WINDOWS.bat" call "DOWNLOAD_STEP170_REFERENCE_DATABASES_WINDOWS.bat"
call "VERIFY_STEP176_TARGET_MODULES_WINDOWS.bat"
endlocal
