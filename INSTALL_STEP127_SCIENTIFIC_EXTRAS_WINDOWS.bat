@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
echo [BioIntel AI Step 127] Installing optional scientific Python packages...
%PY% -m pip install --no-index --find-links "%CD%\wheelhouse" -r requirements-step127-scientific-extras.txt
if errorlevel 1 (
  echo.
  echo Offline wheel installation was incomplete. No existing modules were removed.
  echo Open Scientific Depth Command Center to review missing optional packages and external tools.
  exit /b 1
)
echo Optional Step 127 scientific packages installed successfully.
exit /b 0
