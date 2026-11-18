@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
title BioIntel AI - P0 P1 P2 Scientific Integration Setup

if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
set "TOOLS_HOME=%LOCALAPPDATA%\BioIntelAI\Tools"
set "RUNTIME_ROOT=%LOCALAPPDATA%\BioIntelAI\ScientificRuntimes"
set "USER_DATA=%LOCALAPPDATA%\BioIntelAI\UserData"
set "LOG_DIR=%USER_DATA%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"`) do set "STAMP=%%T"
if not defined STAMP set "STAMP=latest"
set "LOG_FILE=%LOG_DIR%\biointel-scientific-setup-%STAMP%.log"
set "ACTION=%~1"
set "RC=0"

where powershell.exe >nul 2>&1
if errorlevel 1 (
  echo ERROR: Windows PowerShell is required for BioIntel scientific setup.
  popd
  pause
  exit /b 1
)

if /I "%ACTION%"=="P0" goto INSTALL_P0
if /I "%ACTION%"=="P1" goto INSTALL_P1
if /I "%ACTION%"=="P2" goto INSTALL_P2
if /I "%ACTION%"=="All" goto INSTALL_ALL
if /I "%ACTION%"=="Native" goto INSTALL_P1
if /I "%ACTION%"=="Complete" goto INSTALL_ALL
if /I "%ACTION%"=="Verify" goto VERIFY_ONLY
if /I "%ACTION%"=="Open" goto OPEN_CENTER
if /I "%ACTION%"=="Shiro" goto SHIRO_SETUP

:MENU
cls
echo ============================================================
echo       BIOINTEL P0 + P1 + P2 SCIENTIFIC INTEGRATION SETUP
echo ============================================================
echo.
echo  1. Install or repair P0 core scientific integrations
echo  2. Install or repair P1 advanced scientific integrations
echo  3. Install or repair P2 model and pipeline integrations
echo  4. Install or repair P0 + P1 + P2 together
echo  5. Verify all BioIntel scientific integrations
echo  6. Open BioIntel Scientific Integration Center
echo  7. Configure Shiro AI local and free model providers
echo  8. Exit
echo.
echo Heavy runtimes are isolated from the core BioIntel app.
echo Model assets and reference databases remain qualification-gated.
echo.
set /p CHOICE=Choose 1-8: 
if "%CHOICE%"=="1" goto INSTALL_P0
if "%CHOICE%"=="2" goto INSTALL_P1
if "%CHOICE%"=="3" goto INSTALL_P2
if "%CHOICE%"=="4" goto INSTALL_ALL
if "%CHOICE%"=="5" goto VERIFY_ONLY
if "%CHOICE%"=="6" goto OPEN_CENTER
if "%CHOICE%"=="7" goto SHIRO_SETUP
if "%CHOICE%"=="8" goto DONE
goto MENU

:INSTALL_P0
call :RUN_SETUP P0 "BioIntel P0 core scientific integrations"
goto FINISH

:INSTALL_P1
call :RUN_SETUP P1 "BioIntel P1 advanced scientific integrations"
goto FINISH

:INSTALL_P2
call :RUN_SETUP P2 "BioIntel P2 model and pipeline integrations"
goto FINISH

:INSTALL_ALL
call :RUN_SETUP All "BioIntel P0, P1 and P2 scientific integrations"
goto FINISH

:RUN_SETUP
set "MODE=%~1"
set "LABEL=%~2"
echo.
echo Preparing %LABEL%...
echo Detailed dependency output is retained in the protected BioIntel log.
echo Log: %LOG_FILE%
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\install_scientific_integrations_windows.ps1" -AppRoot "%CD%" -RuntimeRoot "%RUNTIME_ROOT%" -ToolsHome "%TOOLS_HOME%" -Priority "%MODE%" >"%LOG_FILE%" 2>&1
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo ERROR: BioIntel %MODE% scientific setup did not complete.
  echo Review the protected log: %LOG_FILE%
  exit /b %RC%
)
echo BioIntel %MODE% scientific setup completed.
exit /b 0

:VERIFY_ONLY
echo.
echo Verifying P0, P1 and P2 BioIntel scientific integrations...
powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\verify_scientific_integrations_windows.ps1" -AppRoot "%CD%" -RuntimeRoot "%RUNTIME_ROOT%" -ToolsHome "%TOOLS_HOME%" -Priority All >"%LOG_FILE%" 2>&1
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" (
  echo BioIntel scientific integration verification passed.
) else (
  echo Some optional BioIntel integrations still require setup.
  echo Review the protected log: %LOG_FILE%
)
goto FINISH

:SHIRO_SETUP
call "%CD%\SETUP_SHIRO_AI_WINDOWS.bat"
set "RC=%ERRORLEVEL%"
goto FINISH

:OPEN_CENTER
if exist "%LOCALAPPDATA%\BioIntelAI\App\RUN_BIOINTEL_ACTIVE.bat" (
  call "%LOCALAPPDATA%\BioIntelAI\App\RUN_BIOINTEL_ACTIVE.bat"
  set "RC=%ERRORLEVEL%"
) else (
  call "%CD%\RUN_BOTH_WINDOWS.bat"
  set "RC=%ERRORLEVEL%"
)
goto FINISH

:FINISH
echo.
if "%RC%"=="0" (
  echo BioIntel scientific engine operation completed successfully.
) else (
  echo BioIntel scientific engine operation finished with code %RC%.
)
echo.
pause
popd
exit /b %RC%

:DONE
popd
exit /b 0
