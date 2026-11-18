@echo off
setlocal
cd /d "%~dp0"
python scripts\verify_step64_final.py --workers 4
if errorlevel 1 (
  echo Step 64 qualification failed.
  exit /b 1
)
echo Step 64 qualification passed.
endlocal
