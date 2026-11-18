@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo ============================================================
echo BioIntel AI Step 120 - Optional Scientific Depth Components
echo ============================================================
echo.
echo This installer adds optional Python analysis packages and then opens
echo the protected specialist-tool installer. Licensed/proprietary tools and
echo reference databases are never downloaded without their own approval.
echo.
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Core BioIntel AI environment not found.
  echo Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade -r requirements-step120-scientific-extras.txt
if errorlevel 1 (
  echo.
  echo WARNING: Some optional Python packages were not installed.
  echo Core BioIntel AI remains usable; check the pip output above.
)
call INSTALL_ADVANCED_TOOLS_WINDOWS.bat
exit /b %ERRORLEVEL%
