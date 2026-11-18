@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
title BioIntel AI Step204 - Repair Python and Installation
echo ============================================================
echo BioIntel AI Step204 - Python 3.11.9 and Installation Repair
echo ============================================================
call "INSTALL_PYTHON311_WINDOWS.bat" /auto
if errorlevel 1 goto :failed
call "INSTALL_WINDOWS.bat"
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
:failed
echo Python 3.11.9 repair failed. No BioIntel project data was changed.
popd
pause
exit /b 1
