@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set /p ACTOR=Institution administrator user ID for background jobs: 
if not defined ACTOR (
  echo Administrator user ID is required.
  pause
  exit /b 2
)
set "TASK_NAME=BioIntel Education Phase14 Worker"
set "COMMAND=\"%CD%\RUN_EDUCATION_PHASE14_WORKER_WINDOWS.bat\" \"%ACTOR%\""
schtasks /Create /F /SC ONLOGON /RL LIMITED /TN "%TASK_NAME%" /TR "%COMMAND%"
if errorlevel 1 (
  echo Could not create the current-user worker task.
  pause
  exit /b 1
)
echo Worker task installed. It will start at the current user's next sign-in.
echo Run it now with: schtasks /Run /TN "%TASK_NAME%"
pause
exit /b 0
