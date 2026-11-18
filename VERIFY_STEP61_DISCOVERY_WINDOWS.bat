@echo off
setlocal
cd /d "%~dp0"
python scripts\verify_step61_discovery.py
if errorlevel 1 (
  echo Step 61 Discovery qualification FAILED.
  exit /b 1
)
echo Step 61 Discovery qualification PASSED.
endlocal
