@echo off
setlocal
pushd "%~dp0" || exit /b 1
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "scripts\step193_build_mandatory_completion.py" --root "."
set RC=%ERRORLEVEL%
popd
if not "%RC%"=="0" pause
exit /b %RC%
