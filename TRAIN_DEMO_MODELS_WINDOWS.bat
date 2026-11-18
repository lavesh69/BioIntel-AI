@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo The virtual environment is missing.
  echo Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\python.exe scripts\generate_demo_dataset.py
if errorlevel 1 goto :error
call .venv\Scripts\python.exe scripts\train_demo_models.py
if errorlevel 1 goto :error
echo.
echo Synthetic demo models were regenerated successfully.
pause
exit /b 0
:error
echo.
echo Demo model training failed. Read the error shown above.
pause
exit /b 1
