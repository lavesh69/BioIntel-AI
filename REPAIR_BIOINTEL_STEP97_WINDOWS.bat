@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title BioIntel AI Step 97 - Repair V2
call "%~dp0INSTALL_WINDOWS.bat" --force-repair
exit /b %ERRORLEVEL%
