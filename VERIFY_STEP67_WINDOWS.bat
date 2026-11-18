@echo off
setlocal
cd /d "%~dp0"
set PYTHONPATH=%CD%\src
python scripts\verify_step67_theme_font.py
if errorlevel 1 (
  echo.
  echo Step 67 qualification FAILED.
  exit /b 1
)
echo.
echo Step 67 qualification PASSED.
endlocal
